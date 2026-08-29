import Foundation
import Metal
import simd

/// Optional Metal foundation for the cross-cloth solver.
///
/// This backend deliberately implements only deterministic, six-neighbour,
/// compliance-based Jacobi projection.  It is not asserted to be numerically
/// equivalent to the CPU solver and it is not a high-fidelity cloth solver.
/// Callers must retain the CPU implementation as the authoritative fallback.
public final class CrossClothMetalBackend {
    public static let neighbourSlots = 6

    public enum FallbackReason: Equatable, Sendable, CustomStringConvertible {
        case metalUnavailable
        case unsupportedGPU(String)
        case commandQueueUnavailable
        case kernelLibraryUnavailable
        case kernelUnavailable(String)
        case invalidInput(String)
        case allocationFailed(String)
        case commandFailed(String)
        case nonFiniteOutput

        public var description: String {
            switch self {
            case .metalUnavailable:
                return "Metal is unavailable; use the CPU cross-cloth solver."
            case .unsupportedGPU(let detail):
                return "GPU capability check failed (\(detail)); use the CPU cross-cloth solver."
            case .commandQueueUnavailable:
                return "Metal command queue creation failed; use the CPU cross-cloth solver."
            case .kernelLibraryUnavailable:
                return "CrossClothKernels is not in the app Metal library; use the CPU cross-cloth solver."
            case .kernelUnavailable(let name):
                return "Required Metal kernel '\(name)' is unavailable; use the CPU cross-cloth solver."
            case .invalidInput(let detail):
                return "Metal input was refused (\(detail)); use the CPU cross-cloth solver after validation."
            case .allocationFailed(let label):
                return "Metal buffer allocation failed for \(label); use the CPU cross-cloth solver."
            case .commandFailed(let detail):
                return "Metal execution failed (\(detail)); discard GPU state and use the CPU cross-cloth solver."
            case .nonFiniteOutput:
                return "Metal produced non-finite state; discard GPU state and use the CPU cross-cloth solver."
            }
        }
    }

    public enum Capability: Equatable, Sendable {
        case available(deviceName: String)
        case cpuFallback(FallbackReason)

        public var canExecuteOnGPU: Bool {
            if case .available = self { return true }
            return false
        }

        public var fallbackReason: FallbackReason? {
            if case .cpuFallback(let reason) = self { return reason }
            return nil
        }
    }

    public struct Particle: Equatable, Sendable {
        public var position: SIMD3<Float>
        public var velocity: SIMD3<Float>
        public var inverseMass: Float

        public init(position: SIMD3<Float>, velocity: SIMD3<Float> = .zero, inverseMass: Float) {
            self.position = position
            self.velocity = velocity
            self.inverseMass = inverseMass
        }
    }

    /// Six entries per vertex, in the fixed order +X, -X, +Y, -Y, +Z, -Z.
    /// A missing arm is encoded as -1.  Rest lengths and compliance use the
    /// same flattened index, so signal meanings are never mixed.
    public struct Lattice: Sendable {
        public var particles: [Particle]
        public var neighbourIndices: [Int32]
        public var restLengths: [Float]
        public var compliance: [Float]

        public init(
            particles: [Particle],
            neighbourIndices: [Int32],
            restLengths: [Float],
            compliance: [Float]
        ) {
            self.particles = particles
            self.neighbourIndices = neighbourIndices
            self.restLengths = restLengths
            self.compliance = compliance
        }
    }

    public struct Configuration: Equatable, Sendable {
        public var timeStep: Float
        public var substeps: Int
        public var projectionIterations: Int
        public var gravity: SIMD3<Float>
        public var velocityDamping: Float
        public var relaxation: Float

        public init(
            timeStep: Float,
            substeps: Int = 1,
            projectionIterations: Int = 8,
            gravity: SIMD3<Float> = SIMD3<Float>(0, -9.80665, 0),
            velocityDamping: Float = 0.999,
            relaxation: Float = 1
        ) {
            self.timeStep = timeStep
            self.substeps = substeps
            self.projectionIterations = projectionIterations
            self.gravity = gravity
            self.velocityDamping = velocityDamping
            self.relaxation = relaxation
        }
    }

    public struct Diagnostics: Equatable, Sendable {
        public let deviceName: String
        public let vertexCount: Int
        public let substeps: Int
        public let projectionIterations: Int
        public let usesSameOldStateDoubleBuffers: Bool
        public let claimsCPUParity: Bool
    }

    public struct Output: Equatable, Sendable {
        public let particles: [Particle]
        public let diagnostics: Diagnostics
    }

    public enum ExecutionResult: Equatable, Sendable {
        /// This case is returned only after `MTLCommandBuffer.status` is `.completed`
        /// and every output particle has passed finite-value validation.
        case gpuCompleted(Output)
        case cpuFallback(FallbackReason)

        public var completedOnGPU: Bool {
            if case .gpuCompleted = self { return true }
            return false
        }

        public var fallbackReason: FallbackReason? {
            if case .cpuFallback(let reason) = self { return reason }
            return nil
        }
    }

    private struct MetalParticle {
        var positionAndInverseMass: SIMD4<Float>
        var velocity: SIMD4<Float>
    }

    /// Kept as three 16-byte vectors so Swift and Metal have an unambiguous ABI.
    private struct KernelParameters {
        var counts: SIMD4<UInt32>
        var scalars: SIMD4<Float>
        var gravity: SIMD4<Float>
    }

    private let device: MTLDevice
    private let queue: MTLCommandQueue
    private let predictPipeline: MTLComputePipelineState
    private let projectPipeline: MTLComputePipelineState
    private let finalizePipeline: MTLComputePipelineState

    private init(
        device: MTLDevice,
        queue: MTLCommandQueue,
        predictPipeline: MTLComputePipelineState,
        projectPipeline: MTLComputePipelineState,
        finalizePipeline: MTLComputePipelineState
    ) {
        self.device = device
        self.queue = queue
        self.predictPipeline = predictPipeline
        self.projectPipeline = projectPipeline
        self.finalizePipeline = finalizePipeline
    }

    /// Creates the optional backend only after all capabilities and kernels are
    /// present.  Failure is a typed CPU fallback, never a partially usable GPU.
    public static func make(bundle: Bundle = .main) -> (backend: CrossClothMetalBackend?, capability: Capability) {
        guard let device = MTLCreateSystemDefaultDevice() else {
            return (nil, .cpuFallback(.metalUnavailable))
        }
        guard device.supportsFamily(.common3) else {
            return (nil, .cpuFallback(.unsupportedGPU("Metal common3 is required")))
        }
        guard device.maxBufferLength >= 1 << 20 else {
            return (nil, .cpuFallback(.unsupportedGPU("maxBufferLength is below 1 MiB")))
        }
        guard let queue = device.makeCommandQueue() else {
            return (nil, .cpuFallback(.commandQueueUnavailable))
        }

        let library = (try? device.makeDefaultLibrary(bundle: bundle)) ?? device.makeDefaultLibrary()
        guard let library else {
            return (nil, .cpuFallback(.kernelLibraryUnavailable))
        }

        let names = ["crossClothPredict", "crossClothProjectSixArm", "crossClothFinalize"]
        var pipelines: [MTLComputePipelineState] = []
        for name in names {
            guard let function = library.makeFunction(name: name) else {
                return (nil, .cpuFallback(.kernelUnavailable(name)))
            }
            do {
                pipelines.append(try device.makeComputePipelineState(function: function))
            } catch {
                return (nil, .cpuFallback(.kernelUnavailable("\(name): \(error.localizedDescription)")))
            }
        }

        let backend = CrossClothMetalBackend(
            device: device,
            queue: queue,
            predictPipeline: pipelines[0],
            projectPipeline: pipelines[1],
            finalizePipeline: pipelines[2]
        )
        return (backend, .available(deviceName: device.name))
    }

    /// Runs a synchronous GPU step.  Every stage reads one immutable old buffer
    /// and writes a distinct next buffer.  A failed command or invalid result is
    /// discarded in full; callers then run their CPU solver from the original input.
    public func step(lattice: Lattice, configuration: Configuration) -> ExecutionResult {
        if let refusal = Self.validate(lattice: lattice, configuration: configuration) {
            return .cpuFallback(refusal)
        }

        let count = lattice.particles.count
        let metalParticles = lattice.particles.map {
            MetalParticle(
                positionAndInverseMass: SIMD4<Float>($0.position.x, $0.position.y, $0.position.z, $0.inverseMass),
                velocity: SIMD4<Float>($0.velocity.x, $0.velocity.y, $0.velocity.z, 0)
            )
        }

        guard var particleOld = makeBuffer(metalParticles, label: "cross-cloth particle old") else {
            return .cpuFallback(.allocationFailed("particle old"))
        }
        guard var particleNext = makeBuffer(metalParticles, label: "cross-cloth particle next") else {
            return .cpuFallback(.allocationFailed("particle next"))
        }
        guard var projectionOld = makeBuffer(
            metalParticles.map(\.positionAndInverseMass), label: "cross-cloth projection old"
        ) else {
            return .cpuFallback(.allocationFailed("projection old"))
        }
        guard var projectionNext = makeBuffer(
            metalParticles.map(\.positionAndInverseMass), label: "cross-cloth projection next"
        ) else {
            return .cpuFallback(.allocationFailed("projection next"))
        }
        guard let neighbours = makeBuffer(lattice.neighbourIndices, label: "cross-cloth neighbours"),
              let restLengths = makeBuffer(lattice.restLengths, label: "cross-cloth rest lengths"),
              let compliance = makeBuffer(lattice.compliance, label: "cross-cloth compliance") else {
            return .cpuFallback(.allocationFailed("six-arm constraints"))
        }

        guard let commandBuffer = queue.makeCommandBuffer() else {
            return .cpuFallback(.commandFailed("command buffer creation failed"))
        }
        commandBuffer.label = "Cross-cloth XPBD-style Jacobi step"

        let substepTime = configuration.timeStep / Float(configuration.substeps)
        var parameters = KernelParameters(
            counts: SIMD4<UInt32>(UInt32(count), UInt32(Self.neighbourSlots), 0, 0),
            scalars: SIMD4<Float>(substepTime, configuration.velocityDamping, configuration.relaxation, 1e-7),
            gravity: SIMD4<Float>(configuration.gravity.x, configuration.gravity.y, configuration.gravity.z, 0)
        )

        for _ in 0..<configuration.substeps {
            guard let predict = commandBuffer.makeComputeCommandEncoder() else {
                return .cpuFallback(.commandFailed("prediction encoder creation failed"))
            }
            predict.label = "Cross-cloth predict (old -> predicted)"
            predict.setComputePipelineState(predictPipeline)
            predict.setBuffer(particleOld, offset: 0, index: 0)
            predict.setBuffer(projectionOld, offset: 0, index: 1)
            predict.setBytes(&parameters, length: MemoryLayout<KernelParameters>.stride, index: 2)
            dispatch(predict, pipeline: predictPipeline, count: count)
            predict.endEncoding()

            for iteration in 0..<configuration.projectionIterations {
                parameters.counts.z = UInt32(iteration)
                guard let project = commandBuffer.makeComputeCommandEncoder() else {
                    return .cpuFallback(.commandFailed("projection encoder creation failed"))
                }
                project.label = "Cross-cloth six-arm Jacobi \(iteration)"
                project.setComputePipelineState(projectPipeline)
                project.setBuffer(projectionOld, offset: 0, index: 0)
                project.setBuffer(projectionNext, offset: 0, index: 1)
                project.setBuffer(particleOld, offset: 0, index: 2)
                project.setBuffer(neighbours, offset: 0, index: 3)
                project.setBuffer(restLengths, offset: 0, index: 4)
                project.setBuffer(compliance, offset: 0, index: 5)
                project.setBytes(&parameters, length: MemoryLayout<KernelParameters>.stride, index: 6)
                dispatch(project, pipeline: projectPipeline, count: count)
                project.endEncoding()
                swap(&projectionOld, &projectionNext)
            }

            guard let finalize = commandBuffer.makeComputeCommandEncoder() else {
                return .cpuFallback(.commandFailed("finalization encoder creation failed"))
            }
            finalize.label = "Cross-cloth finalize (old + projected -> next)"
            finalize.setComputePipelineState(finalizePipeline)
            finalize.setBuffer(particleOld, offset: 0, index: 0)
            finalize.setBuffer(projectionOld, offset: 0, index: 1)
            finalize.setBuffer(particleNext, offset: 0, index: 2)
            finalize.setBytes(&parameters, length: MemoryLayout<KernelParameters>.stride, index: 3)
            dispatch(finalize, pipeline: finalizePipeline, count: count)
            finalize.endEncoding()
            swap(&particleOld, &particleNext)
        }

        commandBuffer.commit()
        commandBuffer.waitUntilCompleted()
        guard commandBuffer.status == .completed else {
            return .cpuFallback(.commandFailed(commandBuffer.error?.localizedDescription ?? "unknown command status"))
        }

        let pointer = particleOld.contents().bindMemory(to: MetalParticle.self, capacity: count)
        let output = (0..<count).map { index -> Particle in
            let value = pointer[index]
            return Particle(
                position: SIMD3<Float>(value.positionAndInverseMass.x, value.positionAndInverseMass.y, value.positionAndInverseMass.z),
                velocity: SIMD3<Float>(value.velocity.x, value.velocity.y, value.velocity.z),
                inverseMass: value.positionAndInverseMass.w
            )
        }
        guard output.allSatisfy(Self.isFinite) else {
            return .cpuFallback(.nonFiniteOutput)
        }

        return .gpuCompleted(Output(
            particles: output,
            diagnostics: Diagnostics(
                deviceName: device.name,
                vertexCount: count,
                substeps: configuration.substeps,
                projectionIterations: configuration.projectionIterations,
                usesSameOldStateDoubleBuffers: true,
                claimsCPUParity: false
            )
        ))
    }

    private static func validate(lattice: Lattice, configuration: Configuration) -> FallbackReason? {
        let count = lattice.particles.count
        guard count > 0, count <= Int(UInt32.max) / neighbourSlots else {
            return .invalidInput("vertex count is empty or exceeds deterministic UInt32 indexing")
        }
        let expectedSlots = count * neighbourSlots
        guard lattice.neighbourIndices.count == expectedSlots,
              lattice.restLengths.count == expectedSlots,
              lattice.compliance.count == expectedSlots else {
            return .invalidInput("six flattened neighbour arrays must each contain vertexCount * 6 entries")
        }
        guard configuration.timeStep.isFinite, configuration.timeStep > 0,
              configuration.substeps > 0, configuration.substeps <= 1_024,
              configuration.projectionIterations > 0, configuration.projectionIterations <= 65_535,
              configuration.velocityDamping.isFinite, (0...1).contains(configuration.velocityDamping),
              configuration.relaxation.isFinite, configuration.relaxation > 0, configuration.relaxation <= 1,
              configuration.gravity.x.isFinite, configuration.gravity.y.isFinite, configuration.gravity.z.isFinite else {
            return .invalidInput("time step, iteration counts, damping, relaxation, or gravity is outside its safe range")
        }
        guard lattice.particles.allSatisfy(isFinite),
              lattice.restLengths.allSatisfy({ $0.isFinite && $0 >= 0 }),
              lattice.compliance.allSatisfy({ $0.isFinite && $0 >= 0 }) else {
            return .invalidInput("particle or constraint data contains a non-finite or negative value")
        }
        for neighbour in lattice.neighbourIndices where neighbour < -1 || neighbour >= Int32(count) {
            return .invalidInput("neighbour index \(neighbour) is outside [-1, vertexCount)")
        }
        return nil
    }

    private static func isFinite(_ particle: Particle) -> Bool {
        particle.position.x.isFinite && particle.position.y.isFinite && particle.position.z.isFinite &&
        particle.velocity.x.isFinite && particle.velocity.y.isFinite && particle.velocity.z.isFinite &&
        particle.inverseMass.isFinite && particle.inverseMass >= 0
    }

    private func makeBuffer<T>(_ values: [T], label: String) -> MTLBuffer? {
        let length = values.count * MemoryLayout<T>.stride
        guard length > 0, length <= device.maxBufferLength else { return nil }
        let buffer = values.withUnsafeBytes { bytes in
            device.makeBuffer(bytes: bytes.baseAddress!, length: length, options: .storageModeShared)
        }
        buffer?.label = label
        return buffer
    }

    private func dispatch(_ encoder: MTLComputeCommandEncoder, pipeline: MTLComputePipelineState, count: Int) {
        let width = min(pipeline.maxTotalThreadsPerThreadgroup, max(1, pipeline.threadExecutionWidth))
        encoder.dispatchThreads(
            MTLSize(width: count, height: 1, depth: 1),
            threadsPerThreadgroup: MTLSize(width: width, height: 1, depth: 1)
        )
    }
}
