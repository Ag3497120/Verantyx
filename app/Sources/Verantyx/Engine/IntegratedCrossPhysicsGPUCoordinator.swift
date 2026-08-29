import Foundation

/// Typed GPU/CPU boundary for the integrated garment-physics workflow.
///
/// The existing Metal backend can execute the six-arm XPBD projection.  The
/// remaining high-fidelity stages have CPU reference kernels in the Python MCP
/// process and are deliberately reported as continuations.  Returning a GPU
/// checkpoint plus an explicit continuation list prevents a successful XPBD
/// command buffer from being misreported as an all-GPU industrial solve.
public final class IntegratedCrossPhysicsGPUCoordinator {
    public enum Stage: String, CaseIterable, Codable, Sendable {
        case fluidImpulse
        case xpbd
        case nonlinearShell
        case continuousCollision
        case yarnNeedleTopology
        case seamCalibration
        case wearerComfort
    }

    public enum ExecutionSite: String, Codable, Sendable {
        case metal
        case cpuReference
        case reviewOnly
    }

    public struct StageDisposition: Equatable, Codable, Sendable {
        public let stage: Stage
        public let site: ExecutionSite
        public let implemented: Bool
        public let reason: String
    }

    public struct Request: Sendable {
        public let lattice: CrossClothMetalBackend.Lattice
        public let configuration: CrossClothMetalBackend.Configuration
        public let requestedStages: [Stage]

        public init(
            lattice: CrossClothMetalBackend.Lattice,
            configuration: CrossClothMetalBackend.Configuration,
            requestedStages: [Stage] = Stage.allCases
        ) {
            self.lattice = lattice
            self.configuration = configuration
            self.requestedStages = requestedStages
        }
    }

    public struct GPUCheckpoint: Equatable, Sendable {
        public let particles: [CrossClothMetalBackend.Particle]
        public let diagnostics: CrossClothMetalBackend.Diagnostics
        public let completedStages: [Stage]
        public let cpuContinuation: [Stage]
        public let dispositions: [StageDisposition]
        public let industrialCompletion: Bool
    }

    public enum Result: Equatable, Sendable {
        case checkpoint(GPUCheckpoint)
        case cpuContinuation(
            reason: CrossClothMetalBackend.FallbackReason?,
            stages: [Stage],
            dispositions: [StageDisposition]
        )
    }

    private let backend: CrossClothMetalBackend?
    public let capability: CrossClothMetalBackend.Capability

    public init(bundle: Bundle = .main) {
        let made = CrossClothMetalBackend.make(bundle: bundle)
        backend = made.backend
        capability = made.capability
    }

    /// Execute every currently supported Metal stage, preserving a typed CPU
    /// continuation for every other requested stage.
    public func run(_ request: Request) -> Result {
        let requested = Self.canonical(request.requestedStages)
        let dispositions = requested.map(Self.disposition)
        let gpuStages = requested.filter { Self.disposition($0).site == .metal }
        let continuation = requested.filter { Self.disposition($0).site != .metal }

        guard gpuStages.contains(.xpbd) else {
            return .cpuContinuation(
                reason: nil, stages: continuation, dispositions: dispositions)
        }
        guard let backend else {
            return .cpuContinuation(
                reason: capability.fallbackReason,
                stages: requested,
                dispositions: dispositions)
        }

        switch backend.step(lattice: request.lattice,
                            configuration: request.configuration) {
        case .gpuCompleted(let output):
            return .checkpoint(GPUCheckpoint(
                particles: output.particles,
                diagnostics: output.diagnostics,
                completedStages: [.xpbd],
                cpuContinuation: continuation,
                dispositions: dispositions,
                industrialCompletion: false
            ))
        case .cpuFallback(let reason):
            return .cpuContinuation(
                reason: reason, stages: requested, dispositions: dispositions)
        }
    }

    /// This table is the public capability contract used by UI and logging.
    /// Only XPBD is currently encoded into a completed Metal command buffer.
    public static func disposition(_ stage: Stage) -> StageDisposition {
        switch stage {
        case .xpbd:
            return StageDisposition(
                stage: stage, site: .metal, implemented: true,
                reason: "six-arm same-old-state Jacobi Metal kernels")
        case .wearerComfort:
            return StageDisposition(
                stage: stage, site: .reviewOnly, implemented: true,
                reason: "typed wearer comparison remains REVIEW and is not a GPU equation")
        case .fluidImpulse:
            return StageDisposition(
                stage: stage, site: .cpuReference, implemented: true,
                reason: "fluid coupling and pressure projection are CPU reference kernels")
        case .nonlinearShell:
            return StageDisposition(
                stage: stage, site: .cpuReference, implemented: true,
                reason: "global nonlinear solve requires CPU continuation")
        case .continuousCollision:
            return StageDisposition(
                stage: stage, site: .cpuReference, implemented: true,
                reason: "broad phase and bounded narrow phase require CPU continuation")
        case .yarnNeedleTopology:
            return StageDisposition(
                stage: stage, site: .cpuReference, implemented: true,
                reason: "topology-changing event log requires CPU continuation")
        case .seamCalibration:
            return StageDisposition(
                stage: stage, site: .cpuReference, implemented: true,
                reason: "measurement calibration is a CPU provenance-bound solve")
        }
    }

    private static func canonical(_ stages: [Stage]) -> [Stage] {
        let requested = Set(stages)
        return Stage.allCases.filter(requested.contains)
    }
}
