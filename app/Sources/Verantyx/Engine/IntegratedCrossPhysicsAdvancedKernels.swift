import Foundation

/// Orchestration contracts for advanced cross-physics stages.
///
/// The app currently links Metal kernels only for the six-arm XPBD foundation
/// managed by ``IntegratedCrossPhysicsGPUCoordinator``.  This type deliberately
/// does not invent shell, CCD, fluid, yarn, seam, or comfort GPU completion.
/// Instead it records the completed XPBD dispatch (when one occurred) and emits
/// a typed continuation checkpoint for every requested advanced stage.
public final class IntegratedCrossPhysicsAdvancedKernels {
    public enum Stage: String, CaseIterable, Codable, Sendable {
        case nonlinearShell
        case continuousCollision
        case fluidCoupling
        case yarnNeedleTopology
        case seamCalibration
        case wearerComfort
    }

    /// The site at which the current build can truthfully complete a stage.
    public enum DeclaredExecutionSite: String, Codable, Sendable {
        case metalCompute
        case cpuReference
        case reviewOnly
    }

    public enum CheckpointPolicy: String, Codable, Sendable {
        case immutableStateBoundary
        case topologyEventBoundary
        case provenanceDigestBoundary
        case namedHumanReviewBoundary
    }

    /// Public capability contract. `linkedMetalFunctions` contains only
    /// functions verified to be part of the current app contract; an empty list
    /// means no advanced Metal dispatch may be claimed for that stage.
    public struct Contract: Equatable, Codable, Sendable {
        public let stage: Stage
        public let declaredSite: DeclaredExecutionSite
        public let linkedMetalFunctions: [String]
        public let checkpointPolicy: CheckpointPolicy
        public let mutatesTopology: Bool
        public let requiresCalibrationDigest: Bool
        public let requiresNamedHumanReview: Bool
        public let implementedInCurrentBuild: Bool
        public let limitation: String

        public var canDispatchMetalInCurrentBuild: Bool {
            declaredSite == .metalCompute
                && implementedInCurrentBuild
                && !linkedMetalFunctions.isEmpty
        }
    }

    /// A continuation is not a completed CPU fallback.  It is a request for the
    /// existing CPU/MCP reference implementation to resume from this boundary.
    public enum StageStatus: String, Codable, Sendable {
        case metalDispatchCompleted
        case cpuContinuationRequired
        case namedHumanReviewRequired
    }

    public struct StageCheckpoint: Equatable, Codable, Sendable {
        public let stage: Stage
        public let status: StageStatus
        public let declaredSite: DeclaredExecutionSite
        public let actualMetalDispatch: Bool
        public let metalCommandBufferCompleted: Bool
        public let cpuFallbackExecuted: Bool
        public let upstreamXPBDMetalCompleted: Bool
        public let checkpointPolicy: CheckpointPolicy
        public let reason: String

        public init(
            stage: Stage,
            status: StageStatus,
            declaredSite: DeclaredExecutionSite,
            actualMetalDispatch: Bool,
            metalCommandBufferCompleted: Bool,
            cpuFallbackExecuted: Bool,
            upstreamXPBDMetalCompleted: Bool,
            checkpointPolicy: CheckpointPolicy,
            reason: String
        ) {
            self.stage = stage
            self.status = status
            self.declaredSite = declaredSite
            self.actualMetalDispatch = actualMetalDispatch
            self.metalCommandBufferCompleted = metalCommandBufferCompleted
            self.cpuFallbackExecuted = cpuFallbackExecuted
            self.upstreamXPBDMetalCompleted = upstreamXPBDMetalCompleted
            self.checkpointPolicy = checkpointPolicy
            self.reason = reason
        }
    }

    public struct Request: Sendable {
        public let foundation: IntegratedCrossPhysicsGPUCoordinator.Request
        public let requestedStages: [Stage]

        public init(
            foundation: IntegratedCrossPhysicsGPUCoordinator.Request,
            requestedStages: [Stage] = Stage.allCases
        ) {
            self.foundation = foundation
            self.requestedStages = requestedStages
        }
    }

    public enum FoundationCheckpoint: Equatable, Sendable {
        /// Returned only after the backend observed a completed Metal command
        /// buffer and validated finite output particles.
        case metalDispatchCompleted(
            IntegratedCrossPhysicsGPUCoordinator.GPUCheckpoint
        )

        /// No GPU completion occurred. The original input remains authoritative.
        case cpuContinuationRequired(
            reason: CrossClothMetalBackend.FallbackReason?,
            stages: [IntegratedCrossPhysicsGPUCoordinator.Stage]
        )

        public var actualMetalDispatchCompleted: Bool {
            if case .metalDispatchCompleted = self { return true }
            return false
        }
    }

    public struct Checkpoint: Equatable, Sendable {
        public let foundation: FoundationCheckpoint
        public let advancedStages: [StageCheckpoint]

        /// True only if every requested advanced stage actually completed.
        /// This is false in the current build because these contracts expose
        /// continuations rather than pretending to run absent Metal kernels.
        public let advancedPipelineCompleted: Bool

        public var actualMetalDispatchOccurred: Bool {
            foundation.actualMetalDispatchCompleted
                || advancedStages.contains(where: { $0.actualMetalDispatch })
        }

        public var requiresCPUContinuation: Bool {
            advancedStages.contains(where: { $0.status == .cpuContinuationRequired })
        }

        public var requiresHumanReview: Bool {
            advancedStages.contains(where: { $0.status == .namedHumanReviewRequired })
        }
    }

    private let foundationCoordinator: IntegratedCrossPhysicsGPUCoordinator

    public init(bundle: Bundle = .main) {
        foundationCoordinator = IntegratedCrossPhysicsGPUCoordinator(bundle: bundle)
    }

    /// Runs the linked XPBD Metal foundation and creates explicit boundaries
    /// for advanced CPU/review stages. This method never executes a CPU solver.
    public func run(_ request: Request) -> Checkpoint {
        let foundationResult = foundationCoordinator.run(request.foundation)
        let foundation: FoundationCheckpoint
        switch foundationResult {
        case .checkpoint(let completed):
            foundation = .metalDispatchCompleted(completed)
        case .cpuContinuation(let reason, let stages, _):
            foundation = .cpuContinuationRequired(reason: reason, stages: stages)
        }

        let xpbdCompleted = foundation.actualMetalDispatchCompleted
        let stages = Self.canonical(request.requestedStages).map {
            Self.continuationCheckpoint(for: $0, xpbdCompleted: xpbdCompleted)
        }
        return Checkpoint(
            foundation: foundation,
            advancedStages: stages,
            advancedPipelineCompleted: !stages.isEmpty && stages.allSatisfy {
                $0.status == .metalDispatchCompleted && $0.actualMetalDispatch
            }
        )
    }

    /// Stable capability ordering for UI, logs, and regression checks.
    public static func capabilities() -> [Contract] {
        Stage.allCases.map(contract)
    }

    public static func contract(for stage: Stage) -> Contract {
        switch stage {
        case .nonlinearShell:
            return Contract(
                stage: stage,
                declaredSite: .cpuReference,
                linkedMetalFunctions: [],
                checkpointPolicy: .immutableStateBoundary,
                mutatesTopology: false,
                requiresCalibrationDigest: true,
                requiresNamedHumanReview: false,
                implementedInCurrentBuild: true,
                limitation: "nonlinear shell assembly and global solve are CPU/MCP reference work"
            )
        case .continuousCollision:
            return Contract(
                stage: stage,
                declaredSite: .cpuReference,
                linkedMetalFunctions: [],
                checkpointPolicy: .immutableStateBoundary,
                mutatesTopology: false,
                requiresCalibrationDigest: false,
                requiresNamedHumanReview: false,
                implementedInCurrentBuild: true,
                limitation: "continuous broad/narrow phase has no linked Metal kernel"
            )
        case .fluidCoupling:
            return Contract(
                stage: stage,
                declaredSite: .cpuReference,
                linkedMetalFunctions: [],
                checkpointPolicy: .immutableStateBoundary,
                mutatesTopology: false,
                requiresCalibrationDigest: true,
                requiresNamedHumanReview: false,
                implementedInCurrentBuild: true,
                limitation: "fluid pressure projection and cloth coupling remain CPU reference work"
            )
        case .yarnNeedleTopology:
            return Contract(
                stage: stage,
                declaredSite: .cpuReference,
                linkedMetalFunctions: [],
                checkpointPolicy: .topologyEventBoundary,
                mutatesTopology: true,
                requiresCalibrationDigest: true,
                requiresNamedHumanReview: false,
                implementedInCurrentBuild: true,
                limitation: "topology-changing yarn and needle events require an auditable CPU event log"
            )
        case .seamCalibration:
            return Contract(
                stage: stage,
                declaredSite: .cpuReference,
                linkedMetalFunctions: [],
                checkpointPolicy: .provenanceDigestBoundary,
                mutatesTopology: false,
                requiresCalibrationDigest: true,
                requiresNamedHumanReview: false,
                implementedInCurrentBuild: true,
                limitation: "measured seam regression is provenance-bound CPU work, not a GPU dynamics kernel"
            )
        case .wearerComfort:
            return Contract(
                stage: stage,
                declaredSite: .reviewOnly,
                linkedMetalFunctions: [],
                checkpointPolicy: .namedHumanReviewBoundary,
                mutatesTopology: false,
                requiresCalibrationDigest: true,
                requiresNamedHumanReview: true,
                implementedInCurrentBuild: true,
                limitation: "wearer-specific comfort produces REVIEW only and makes no medical safety claim"
            )
        }
    }

    private static func continuationCheckpoint(
        for stage: Stage,
        xpbdCompleted: Bool
    ) -> StageCheckpoint {
        let capability = contract(for: stage)
        let status: StageStatus = capability.declaredSite == .reviewOnly
            ? .namedHumanReviewRequired : .cpuContinuationRequired
        return StageCheckpoint(
            stage: stage,
            status: status,
            declaredSite: capability.declaredSite,
            actualMetalDispatch: false,
            metalCommandBufferCompleted: false,
            cpuFallbackExecuted: false,
            upstreamXPBDMetalCompleted: xpbdCompleted,
            checkpointPolicy: capability.checkpointPolicy,
            reason: capability.limitation
        )
    }

    private static func canonical(_ stages: [Stage]) -> [Stage] {
        let requested = Set(stages)
        return Stage.allCases.filter(requested.contains)
    }
}
