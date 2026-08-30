import AppKit
import CryptoKit
import Foundation

/// Deterministic foreman for the Atelier sewing-factory loop.
///
/// The language model is a proposal mouth, never the loop controller.  This
/// type reads the persisted Python `garment.factory.v1` state after every
/// action and chooses the next permitted action from a closed table.  The
/// model cannot name tools, approve candidates, claim convergence, or extend
/// the iteration budget.
@MainActor
public final class GarmentFactoryReactController: ObservableObject {
    public static let shared = GarmentFactoryReactController()
    /// The persisted MCP state is the ReAct harness. The LLM never owns this
    /// state and cannot replace it with conversational memory.
    static let harnessSchema = "garment.factory.v1"

    enum ActionKind: String, Sendable {
        case callEngine
        case askModel
        case waitForImage
        case waitForRetrieval
        case waitForHuman
        case waitForSimulationInput
        case waitForSewingCorpus
        case converged
        case stopped
    }

    /// Initial image-review policy. Both routes use the same deterministic
    /// factory state machine; only the authority ceiling of the first visible
    /// inventory/foreground gates differs.
    enum InitialAuditMode: String, CaseIterable, Identifiable, Sendable {
        case humanAudit = "HUMAN_AUDIT"
        case autoProposed = "AUTO_PROPOSED"

        var id: String { rawValue }
        var title: String {
            switch self {
            case .humanAudit: return "人が確認"
            case .autoProposed: return "自動プレビュー"
            }
        }
        var detail: String {
            switch self {
            case .humanAudit:
                return "可視部品とCAD削除結果を人が採用してから進みます"
            case .autoProposed:
                return "AIマスクをPROPOSEDのまま採用し、製造承認なしで比較3Dまで進みます"
            }
        }
    }

    struct DeterministicAction: Sendable, Equatable {
        let kind: ActionKind
        let eventType: String?
        let modelTask: String?
        let code: String
        let message: String
    }

    struct Report: Sendable, Equatable {
        let verdict: String
        let phase: String
        let message: String
        let iterations: Int
        let modelCalls: Int
    }

    /// A closed set of ways an unresolved factory obligation may be handled.
    /// UNKNOWN is not an instruction and must never be the only thing exposed
    /// to the Atelier UI.  Each pause is therefore converted into one or more
    /// of these typed actions.  Only `typedStop` is terminal.
    enum ResolutionActionKind: String, Sendable, Codable, CaseIterable, Hashable {
        case humanInput = "HUMAN_INPUT"
        case humanGeometryEdit = "HUMAN_GEOMETRY_EDIT"
        case connectProvider = "CONNECT_PROVIDER"
        case allowOneTimeLLMProposal = "LLM_PROPOSAL_WITH_CONSENT"
        case compareBoundedAlternatives = "COMPARE_BOUNDED_ALTERNATIVES"
        case typedStop = "TYPED_STOP"
    }

    /// Exact `cross_workflow_harness.resolve_request` vocabulary.  The UI
    /// action labels above are presentation choices; only these values may be
    /// sent to Python's RESOLVE_CROSS_OBLIGATION event.
    public enum CrossResolutionPath: String, Sendable, Equatable, Hashable {
        case humanInput = "HUMAN_INPUT"
        case measuredInput = "MEASURED_INPUT"
        case humanEdit = "HUMAN_EDIT"
        case connectProvider = "CONNECT_PROVIDER"
        case consentedLLMProposal = "CONSENTED_LLM_PROPOSAL"
        case boundedAlternatives = "BOUNDED_ALTERNATIVES"
        case typedStop = "TYPED_STOP"
    }

    /// Result returned to AppState after the controller has checked both the
    /// event response and the persisted cross-workflow ledger.  `accepted`
    /// never means that a proposal became observed or manufacturing-ready.
    public struct ResolutionEventOutcome: Sendable, Equatable {
        public let accepted: Bool
        public let verdict: String
        public let requestID: String
        public let message: String
        public let consentDigest: String?
        public let boundWorkflowDigest: String?
        public let resolutionStatus: String?

        static func rejected(
            _ verdict: String, requestID: String, message: String
        ) -> Self {
            .init(accepted: false, verdict: verdict, requestID: requestID,
                  message: message, consentDigest: nil,
                  boundWorkflowDigest: nil, resolutionStatus: nil)
        }
    }

    struct ResolutionOption: Identifiable, Sendable, Equatable {
        let id: String
        let kind: ResolutionActionKind
        let title: String
        let detail: String
        let requiresExplicitConsent: Bool
        let resultAuthority: String
    }

    /// UI-facing continuation request emitted by the deterministic harness.
    /// The provenance digest binds any later consent to this exact unresolved
    /// state, so permission from an older image or candidate cannot leak into
    /// a new run.
    struct FactoryResolutionRequest: Identifiable, Sendable, Equatable {
        let id: String
        let code: String
        let stage: String
        let title: String
        let explanation: String
        let missingFields: [String]
        let options: [ResolutionOption]
        let provenanceDigest: String
        let authority: String
        let terminal: Bool
    }

    /// One-shot, actor-named permission for the model to propose values at a
    /// single unresolved boundary.  It never authorizes OBSERVED/MEASURED
    /// promotion, approval, manufacturing certification, or reuse in another
    /// request.
    struct LLMProposalConsentArtifact: Sendable, Equatable {
        let schema: String
        let requestID: String
        let projectName: String
        let stage: String
        let grantedBy: String
        let subjectDigest: String
        let engineConsentDigest: String
        let boundWorkflowDigest: String
        let authorityCeiling: String
        let maximumUses: Int
        var remainingUses: Int
    }

    struct TraceEntry: Identifiable, Sendable, Equatable {
        let id = UUID()
        let round: Int
        let actor: String
        let action: String
        let verdict: String
    }

    struct Candidate: Identifiable, Sendable, Equatable {
        let id: String
        let digest: String
        let title: String
        let detail: String
    }

    /// UI-safe status for an image-model construction proposal.  A successful
    /// deterministic geometry check does not promote the proposal: it only
    /// changes `executionStatus` from pending to MCP-validated.
    struct VisionPatternOperationStatus: Identifiable, Sendable, Equatable {
        var id: String { "\(candidateID):\(operationID)" }
        let candidateID: String
        let operationID: String
        let kind: String
        let target: String
        let authority: String
        let disposition: String
        let executionStatus: String
        let detail: String
    }

    /// The pixel-seeing pass, kept independently from 3D topology. These rows
    /// are the visible-front target inventory for same-camera reprojection.
    /// They remain AI proposals until a person confirms their image regions;
    /// rear shape, material identity and sewing are never stored here.
    struct VisibleFrontInventoryItem: Identifiable, Sendable, Equatable {
        let id: String
        let label: String
        let sourceKind: String
        let normalizedKind: String
        let visibleColor: String?
        let layer: Int
        let side: String?
        let garmentUnit: String
        let proposedParent: String?
        let visibleBasis: String
        let state: String
    }

    /// A user-selected game-style preview body. These dimensions are a
    /// chosen design target, never measurements inferred from the garment
    /// photograph. The avatar digest is locked across reconstruction,
    /// dressing and same-camera comparison.
    struct BaseAvatarProfile: Identifiable, Sendable, Equatable {
        let id: String
        let title: String
        let heightCM: Double
        let chestCM: Double
        let waistCM: Double
        let hipCM: Double
        let geometryDigest: String
        let authority: String
    }

    struct TargetCleanupRegion: Identifiable, Sendable, Equatable {
        let id: String
        let label: String
        let regionClass: String
        let state: String
        let removable: Bool
        let removed: Bool
        let occludesGarment: Bool
    }

    /// Editable fused target shown in the beginner CAD surface. External
    /// single-view providers may replace the fallback mesh at this boundary;
    /// either source remains a PROPOSED visual envelope until the user adopts
    /// their own brush edits.
    struct TargetSculptSurface: Sendable, Equatable {
        let source: String
        let state: String
        let surfaceMode: String
        let verticesCM: [[Double]]
        let textureCoordinates: [[Double]]
        let faces: [[Int]]
        let faceRegionIDs: [String]
        let faceComponentIDs: [String]
        let limitations: [String]
    }

    struct TargetSculptClearancePreview: Sendable, Equatable {
        let verdict: String
        let method: String
        let resolvedVerticesCM: [[Double]]
        let collisionFaceIndices: [Int]
        let faceClearances: [TargetSculptFaceClearance]
        let movedVertexCount: Int
        let minimumClearanceBeforeMM: Double
        let minimumClearanceAfterMM: Double
        let digest: String
        let limitations: [String]
    }

    /// Per-face geometric spacing for the CAD heat map. This is deliberately
    /// not named pressure/fit: the deterministic boundary has no material or
    /// comfort measurements and publishes only avatar-envelope clearance.
    struct TargetSculptFaceClearance: Identifiable, Sendable, Equatable {
        var id: Int { faceIndex }
        let faceIndex: Int
        let minimumBeforeMM: Double
        let minimumAfterMM: Double
        let meanAfterMM: Double
        let band: String
    }

    /// A web result found autonomously beside the local FashionSigLIP/corpus
    /// route. It remains a review-only lead until source rights and the actual
    /// page content are checked; snippets never become garment facts.
    struct GarmentWebReference: Identifiable, Sendable, Equatable {
        let id: String
        let scope: String
        let title: String
        let url: String
        let snippet: String
        let authority: String
        let rightsState: String
    }

    struct TargetSculptModifierStatus: Sendable, Equatable {
        let kind: String
        let verdict: String
        let movedVertexCount: Int
        let revision: Int
        let digest: String
        let undoParentDigest: String
        let limitations: [String]
    }

    struct TargetSameCameraComparison: Sendable, Equatable {
        let verdict: String
        let convergenceStatus: String
        let silhouetteIOU: Double?
        let proposalCount: Int
        let comparisonDigest: String
        let referenceAuthority: String
    }

    /// Typed visual target between a single-view 3D provider and the Vera
    /// pattern loop. It cannot claim rear truth or manufacturing readiness.
    struct TargetReconstructionArtifact: Sendable, Equatable {
        let targetDigest: String
        let sourceKind: String
        let providerConnected: Bool
        let stage: String
        let cameraDigest: String
        let baseAvatarID: String
        let regions: [TargetCleanupRegion]
        let occlusionHoleCount: Int
        let proposedCompletionCount: Int
        let reviewCodes: [String]
        let garmentExtractionReady: Bool
        let sculptSurface: TargetSculptSurface?
        let garmentComponentSurface: TargetSculptSurface?
    }

    struct PreviewPiece: Identifiable, Sendable, Equatable {
        let id: String
        let name: String
        let outline: [[Double]]
    }

    /// A proposal-only artifact which can be shown before a manufacturing
    /// approval exists.  It is deliberately separate from `shape_approval`:
    /// beginner mode may explore and render automatically, but it may not
    /// silently turn the selected back or material into an approved fact.
    struct PreviewArtifact: Sendable, Equatable {
        let state: String
        let attempt: Int
        let method: String
        let points: [[Double]]
        let faces: [[Int]]
        let edges: [[Int]]
        let pieces: [PreviewPiece]
        let assumptions: [String]
        let repairSummary: String
        /// True only when the displayed front triangles are copied from the
        /// adopted image target. Generic semantic proxy garments must not be
        /// rendered over that front because they would hide its asymmetry and
        /// disconnected upper/lower components.
        let preservesSourceFront: Bool
    }

    typealias Door = @MainActor (_ action: String, _ request: [String: Any]) async -> [String: Any]
    typealias Proposer = @MainActor (_ prompt: String) async -> String?
    /// Optional pixel-seeing proposal mouth.  Its output has exactly the same
    /// authority as a text proposal: it may open hypotheses, never approve one.
    typealias VisionProposer = @MainActor (_ prompt: String, _ imagePath: String) async -> String?
    typealias ToolDoor = @MainActor (_ tool: String, _ arguments: [String: Any]) async -> [String: Any]

    @Published private(set) var phase = "EMPTY"
    @Published private(set) var busy = false
    @Published private(set) var lastReport: Report?
    @Published private(set) var trace: [TraceEntry] = []
    /// Non-nil while the deterministic loop is paused for a resolvable
    /// obligation.  The progressive sidebar observes this property directly;
    /// no floating window and no conversational string parsing is required.
    @Published private(set) var pendingResolutionRequest:
        FactoryResolutionRequest?
    @Published private(set) var activeLLMProposalConsent:
        LLMProposalConsentArtifact?
    /// Resolution permissions are project-scoped even though the Python MCP
    /// project is selected through a separate canonical activation call.
    @Published private(set) var activeResolutionProject = "Black Coat"
    @Published private(set) var resolutionEventInFlight = false
    @Published private(set) var shapeCandidates: [Candidate] = []
    @Published private(set) var materialCandidates: [Candidate] = []
    /// True only when the persisted append-only factory journal has an active
    /// human structure decision which can be compensated.  The UI must not
    /// infer this from a visible preview or from its own local history.
    @Published private(set) var canUndoShapeDecision = false
    @Published private(set) var visionPatternOperations: [VisionPatternOperationStatus] = []
    @Published private(set) var visibleFrontInventory: [VisibleFrontInventoryItem] = []
    /// Automatic image analysis is an AI proposal, not a confirmed garment
    /// inventory.  Beginner mode must obtain this explicit human audit and the
    /// editable foreground-target approval before compiling parts into 3D and
    /// flat patterns.
    @Published private(set) var visibleFrontInventoryAuditRequired = false
    @Published private(set) var visibleFrontInventoryAuditConfirmed = false
    @Published private(set) var visibleFrontInventoryAuthority = "UNREVIEWED"
    @Published private(set) var selectedAuditMode: InitialAuditMode = .humanAudit
    @Published private(set) var activeAuditMode: InitialAuditMode = .humanAudit
    /// A chat request to inspect an inferred rear is queued across the two
    /// mandatory human gates. It never restarts image intake and never turns
    /// the unobserved rear into an OBSERVED fact.
    @Published private(set) var pendingBack3DRequest = false
    @Published private(set) var baseAvatarProfiles: [BaseAvatarProfile] =
        GarmentFactoryReactController.defaultBaseAvatarProfiles
    @Published private(set) var selectedBaseAvatarID = "preview-balanced-170"
    /// Digest of the bounded image-relative avatar fit currently used by the
    /// candidate renderer. Pixels control only pose/scale/translation; this is
    /// never presented as a measurement of the photographed wearer.
    @Published private(set) var imageRelativeBodyFitDigest: String?
    @Published private(set) var targetReconstruction: TargetReconstructionArtifact?
    @Published private(set) var targetCleanupAuthority = "UNSELECTED"
    @Published private(set) var targetCleanupConfirmed = false {
        didSet {
            if !targetCleanupConfirmed { targetCleanupAuthority = "UNSELECTED" }
        }
    }
    @Published private(set) var targetSculptRemovedFaces = Set<Int>()
    @Published private(set) var targetSculptUndoStack: [Set<Int>] = []
    @Published private(set) var targetSculptThicknessMM = 1.0
    @Published private(set) var targetSculptRevision: UInt64 = 0
    @Published private(set) var targetSculptClearancePreview:
        TargetSculptClearancePreview?
    @Published private(set) var targetSculptModifierStatus:
        TargetSculptModifierStatus?
    @Published private(set) var targetSameCameraComparison:
        TargetSameCameraComparison?
    @Published private(set) var rearWebReferences: [GarmentWebReference] = []
    @Published private(set) var sewingWebReferences: [GarmentWebReference] = []
    @Published private(set) var rearReferenceSearchStatus = "IDLE"
    @Published private(set) var sewingReferenceSearchStatus = "IDLE"
    @Published private(set) var previewArtifact: PreviewArtifact? {
        didSet {
            if previewArtifact != nil, targetCleanupConfirmed {
                scheduleTargetSameCameraComparison()
            }
        }
    }
    /// The legacy outline -> photo-pattern -> mannequin path is useful as a
    /// numerical calibration baseline, but it is not a candidate-specific 3D
    /// reconstruction of the photographed garment. Keep it out of the normal
    /// preview channel so a generic dress/cape cannot visually replace the
    /// audited image parts while the vision/rear ensemble is still running.
    @Published private(set) var outlineCalibrationBaseline: PreviewArtifact?
    /// Compact proposal-only cutting data for the currently previewed image
    /// candidate. Beginner UI reads this directly before human approval.
    @Published private(set) var candidateManufacturingPreview: [String: Any]?
    @Published private(set) var candidateSewingPlan: [String: Any]?
    /// Material previews never replace the approved structure or flat pattern.
    /// This envelope binds one PROPOSED material profile (or a typed REVIEW)
    /// to those fixed artifacts so UI callers cannot accidentally route a
    /// material candidate through the structure compiler.
    @Published private(set) var candidateMaterialPreview: [String: Any]?
    /// User-entered size/ease values and node-address ambiguities remain
    /// visible beside the generated artifacts. They are requests, not image
    /// measurements or manufacturing approval.
    @Published private(set) var designRequirementReviewItems: [[String: Any]] = []
    /// Pixel-model parsing/topology failures are visible in beginner mode.
    /// A geometric silhouette fallback is useful, but it must never look like
    /// the requested semantic garment was understood successfully.
    @Published private(set) var visionPipelineReviewItems: [[String: Any]] = []
    @Published private(set) var previewAttempts = 0

    private let door: Door
    private let toolDoor: ToolDoor
    private let hardRoundLimit: Int
    private let liveExternalEffectsEnabled: Bool
    private var pendingProceduralHypotheses: [[String: Any]] = []
    private var pendingVisionHypotheses: [[String: Any]] = []
    private var activeBodyImageSeparationEnvelope: [String: Any]?
    private var activeBodyRequestedMeasurements: [String: Any] = [:]
    private var activeImageRelativeBodyFit: [String: Any]?
    private var activeInitialFashionRetrieval: [String: Any]?
    private var activeGeometricAtelierWorkflow: [String: Any]?
    private var geometricRearCandidateArtifacts: [String: PreviewArtifact] = [:]
    private var geometricRearCandidateArtifactsInOrder: [PreviewArtifact] = []
    /// Candidate artifacts produced by the same deterministic parts pipeline
    /// that validates the image model proposal.  Keeping these outside the
    /// persisted proposal sheet prevents its authority scrubber from changing
    /// engine ANSWER fields while still binding both views to one digest.
    private var visionPipelineArtifacts: [String: [String: Any]] = [:]
    private var totalModelCalls = 0
    private var rawPreviewPattern: [String: Any]?
    /// Immutable comparison baseline captured from the approved structure.
    /// Material candidates always restart from this rest state rather than
    /// from a previously deformed material preview.
    private var materialPreviewBasePattern: [String: Any]?
    private var materialPreviewBaseArtifact: PreviewArtifact?
    private var shapeCandidatePayloads: [String: [String: Any]] = [:]
    private var materialCandidatePayloads: [String: [String: Any]] = [:]
    private var activeShapeDecisionID: String?
    private var consumedImageSelectionRevision: UInt64?
    private var consumedImageSelectionPath: String?
    private var activeDesignRequirements: [GarmentCommandIR.Requirement] = []
    private var activeDesignRequirementProfile:
        GarmentDesignRequirementProfileBridge.ValidatedProfile?
    private var activeTargetOutline: [String: Any]?
    private var activeTargetImagePath: String?
    /// Populated only by HumanConfirmedFrontEvidenceGate.  AI hypotheses may
    /// describe proposed parts, but cannot create or mutate this evidence.
    private var activeHumanConfirmedFrontEvidence:
        HumanConfirmedFrontEvidenceGate.Evidence?
    private var pendingHumanAuditedVisionRows: [[String: Any]] = []
    private var pendingHumanAuditUserRequest = ""
    private var pendingHumanAuditProposer: Proposer?
    private var initialHumanReviewResumeInFlight = false
    private var activeVisibleAnalysisDigest: String?
    private var persistedForegroundCleanupDigest: String?
    private var hasPersistedForegroundCleanup = false
    private var recordedVeraFrontTargetDigests = Set<String>()
    private var targetRemovedRegionIDs = Set<String>()
    private var targetSculptModifierVertices: [[Double]]?
    private var targetSculptModifierRevision = 0
    private var targetSculptModifierDigest: String?
    private var targetSculptModifierUndoStack:
        [(vertices: [[Double]]?, revision: Int, digest: String?)] = []
    private var targetSculptClearanceTask: Task<Void, Never>?
    private var targetSameCameraTask: Task<Void, Never>?
    private var referenceSearchTasks: [String: Task<Void, Never>] = [:]
    private var referenceSearchQueries: [String: String] = [:]
    private var selectedResolutionAction: ResolutionActionKind?
    private var locallyRevokedConsentDigests = Set<String>()

    var selectedBaseAvatar: BaseAvatarProfile {
        baseAvatarProfiles.first { $0.id == selectedBaseAvatarID }
            ?? Self.defaultBaseAvatarProfiles[1]
    }

    var targetSculptDisplayVertices: [[Double]] {
        if let preview = targetSculptClearancePreview,
           preview.resolvedVerticesCM.count
            == targetReconstruction?.sculptSurface?.verticesCM.count {
            return preview.resolvedVerticesCM
        }
        if let vertices = targetSculptModifierVertices { return vertices }
        guard let vertices = targetReconstruction?.sculptSurface?.verticesCM else {
            return []
        }
        return vertices
    }

    /// The source photograph is presentation input for the editable fused
    /// target. Exposing the already-selected path avoids duplicating image
    /// state in SwiftUI; it never changes the target's PROPOSED authority.
    var targetSculptSourceImagePath: String? { activeTargetImagePath }

    var targetSculptDigest: String? {
        guard let target = targetReconstruction,
              target.sculptSurface != nil else { return nil }
        let payload: [String: Any] = [
            "target_digest": target.targetDigest,
            "avatar_id": selectedBaseAvatarID,
            "removed_face_indices": targetSculptRemovedFaces.sorted(),
            "cloth_thickness_mm": targetSculptThicknessMM,
            "modifier_digest": targetSculptModifierDigest ?? "BASE_SURFACE",
            "modifier_revision": targetSculptModifierRevision,
            "revision": targetSculptRevision,
        ]
        guard let text = Self.jsonString(payload) else { return nil }
        return Self.sha256(Data(text.utf8))
    }

    private static let defaultBaseAvatarProfiles: [BaseAvatarProfile] = [
        .init(id: "preview-straight-170", title: "170 · 86 / 70 / 90 cm",
              heightCM: 170, chestCM: 86, waistCM: 70, hipCM: 90,
              geometryDigest: "parametric-avatar-straight-v1",
              authority: "PROPOSED_PREVIEW"),
        .init(id: "preview-balanced-170", title: "170 · 92 / 76 / 98 cm",
              heightCM: 170, chestCM: 92, waistCM: 76, hipCM: 98,
              geometryDigest: "parametric-avatar-balanced-v1",
              authority: "PROPOSED_PREVIEW"),
        .init(id: "preview-curved-165", title: "165 · 96 / 78 / 104 cm",
              heightCM: 165, chestCM: 96, waistCM: 78, hipCM: 104,
              geometryDigest: "parametric-avatar-curved-v1",
              authority: "PROPOSED_PREVIEW"),
        .init(id: "preview-petite-155", title: "155 · 78 / 62 / 84 cm",
              heightCM: 155, chestCM: 78, waistCM: 62, hipCM: 84,
              geometryDigest: "parametric-avatar-petite-155-v1",
              authority: "PROPOSED_PREVIEW"),
        .init(id: "preview-compact-160", title: "160 · 84 / 66 / 90 cm",
              heightCM: 160, chestCM: 84, waistCM: 66, hipCM: 90,
              geometryDigest: "parametric-avatar-compact-160-v1",
              authority: "PROPOSED_PREVIEW"),
        .init(id: "preview-straight-165", title: "165 · 88 / 70 / 94 cm",
              heightCM: 165, chestCM: 88, waistCM: 70, hipCM: 94,
              geometryDigest: "parametric-avatar-straight-165-v1",
              authority: "PROPOSED_PREVIEW"),
        .init(id: "preview-balanced-175", title: "175 · 94 / 78 / 100 cm",
              heightCM: 175, chestCM: 94, waistCM: 78, hipCM: 100,
              geometryDigest: "parametric-avatar-balanced-175-v1",
              authority: "PROPOSED_PREVIEW"),
        .init(id: "preview-tall-180", title: "180 · 98 / 82 / 102 cm",
              heightCM: 180, chestCM: 98, waistCM: 82, hipCM: 102,
              geometryDigest: "parametric-avatar-tall-180-v1",
              authority: "PROPOSED_PREVIEW"),
        .init(id: "preview-broad-175", title: "175 · 104 / 88 / 106 cm",
              heightCM: 175, chestCM: 104, waistCM: 88, hipCM: 106,
              geometryDigest: "parametric-avatar-broad-175-v1",
              authority: "PROPOSED_PREVIEW"),
        .init(id: "preview-tall-185", title: "185 · 100 / 84 / 104 cm",
              heightCM: 185, chestCM: 100, waistCM: 84, hipCM: 104,
              geometryDigest: "parametric-avatar-tall-185-v1",
              authority: "PROPOSED_PREVIEW"),
    ]

    /// Select or create the body proxy from values the user explicitly gave.
    /// Visible clothing pixels are deliberately not converted into body
    /// circumferences here: a loose blouse or wide trousers cannot measure the
    /// hidden wearer. A future pose/SMPL provider may add a separate PROPOSED
    /// body candidate, but it must pass the same human selection gate.
    private func selectBodyProxy(
        from requirements: [GarmentCommandIR.Requirement]
    ) {
        func cm(_ item: GarmentCommandIR.Requirement) -> Double? {
            guard let value = item.value, let unit = item.unit else { return nil }
            switch unit {
            case .cm: return value
            case .mm: return value / 10.0
            case .m: return value * 100.0
            }
        }
        func token(_ value: String) -> String {
            value.lowercased()
                .replacingOccurrences(of: "_", with: "")
                .replacingOccurrences(of: "-", with: "")
                .replacingOccurrences(of: " ", with: "")
        }
        var requested: [String: Double] = [:]
        for item in requirements where item.kind == .bodyMeasurement {
            guard let value = cm(item) else { continue }
            let key = token(item.target)
            if ["height", "stature", "身長"].contains(key) {
                requested["height"] = value
            } else if ["chest", "bust", "chestbust", "胸囲", "バスト"].contains(key) {
                requested["chest"] = value
            } else if ["waist", "ウエスト", "胴囲"].contains(key) {
                requested["waist"] = value
            } else if ["hip", "hips", "ヒップ", "腰囲"].contains(key) {
                requested["hip"] = value
            }
        }
        guard !requested.isEmpty else { return }
        let closest = Self.defaultBaseAvatarProfiles.min { left, right in
            func score(_ profile: BaseAvatarProfile) -> Double {
                pow((requested["height"] ?? profile.heightCM) - profile.heightCM, 2)
                + pow((requested["chest"] ?? profile.chestCM) - profile.chestCM, 2) * 0.7
                + pow((requested["waist"] ?? profile.waistCM) - profile.waistCM, 2) * 0.7
                + pow((requested["hip"] ?? profile.hipCM) - profile.hipCM, 2) * 0.7
            }
            return score(left) < score(right)
        } ?? Self.defaultBaseAvatarProfiles[1]
        let height = requested["height"] ?? closest.heightCM
        let chest = requested["chest"] ?? closest.chestCM
        let waist = requested["waist"] ?? closest.waistCM
        let hip = requested["hip"] ?? closest.hipCM
        let digestSource = [height, chest, waist, hip]
            .map { String(format: "%.3f", $0) }.joined(separator: "|")
        let digest = Self.sha256(Data(digestSource.utf8))
        let custom = BaseAvatarProfile(
            id: "requested-\(digest.prefix(12))",
            title: String(format: "要求体型 %.0f · %.0f / %.0f / %.0f cm",
                          height, chest, waist, hip),
            heightCM: height, chestCM: chest, waistCM: waist, hipCM: hip,
            geometryDigest: "requested-parametric-avatar-\(digest)",
            authority: "REQUESTED_NOT_MEASURED")
        baseAvatarProfiles = [custom]
            + Self.defaultBaseAvatarProfiles.filter { $0.id != custom.id }
        selectedBaseAvatarID = custom.id
    }

    /// Normalise the front-image separation before body-proxy generation.
    /// Apple Vision contributes proposed 2-D pose plus a low-authority clothed
    /// subject envelope, while RegionPicker contributes typed GARMENT regions.
    /// The envelope is not anatomy or a measurement; HAIR/BACKGROUND remain
    /// UNKNOWN. Even AUTO_PROPOSED only selects a preview candidate and cannot
    /// observe the rear or open manufacturing gates.
    private func prepareBodyImageSeparation(
        outline: [String: Any], imagePath: String, evidenceState: String
    ) async -> [String: Any]? {
        let imageDigest: String
        if let bytes = try? Data(contentsOf: URL(fileURLWithPath: imagePath)) {
            imageDigest = Self.sha256(bytes)
        } else {
            imageDigest = Self.sha256(Data(imagePath.utf8))
        }
        let outlineText = Self.jsonString(outline) ?? "{}"
        let outlineDigest = Self.sha256(Data(outlineText.utf8))
        let garmentOutline = (outline["fused_target_outline"] as? [[Double]])
            ?? (outline["outline"] as? [[Double]])
            ?? (outline["points"] as? [[Double]]) ?? []

        var source: [String: Any] = [
            "image_digest": imageDigest,
            "image_id": URL(fileURLWithPath: imagePath).lastPathComponent,
            "orientation": "UP",
        ]
        var camera: [String: Any] = [
            "orientation": "UP",
            "view": "FRONT",
            "state": "OBSERVED",
            "authority": "OBSERVED",
        ]
        if let representation = NSImage(contentsOfFile: imagePath)?
            .representations.max(by: {
                $0.pixelsWide * $0.pixelsHigh < $1.pixelsWide * $1.pixelsHigh
            }), representation.pixelsWide > 0, representation.pixelsHigh > 0 {
            source["width"] = representation.pixelsWide
            source["height"] = representation.pixelsHigh
            camera["width_px"] = representation.pixelsWide
            camera["height_px"] = representation.pixelsHigh
        }

        var fallback: [String: Any] = [
            "provider_id": "verantyx-front-outline",
            "provider_kind": "DETERMINISTIC_FRONT_OUTLINE_ADAPTER",
            "authority": evidenceState.uppercased() == "OBSERVED"
                ? "OBSERVED" : "PROPOSED",
            "camera": camera,
        ]
        if garmentOutline.count >= 3 {
            fallback["masks"] = [[
                "mask_id": "front-garment-outline",
                "class": "GARMENT",
                "mask_digest": outlineDigest,
                "outline": garmentOutline,
                "confidence": evidenceState.uppercased() == "OBSERVED"
                    ? 1.0 : 0.55,
                "authority": evidenceState.uppercased() == "OBSERVED"
                    ? "OBSERVED" : "PROPOSED",
            ]]
        }
        let provider = await withCheckedContinuation {
            (continuation: CheckedContinuation<[String: Any], Never>) in
            DispatchQueue.global(qos: .userInitiated).async {
                continuation.resume(returning:
                    GarmentOutline.bodyImageSeparationProvider(
                        fileURL: URL(fileURLWithPath: imagePath),
                        garmentEvidence: outline,
                        evidenceState: evidenceState))
            }
        }
        let providerMasks = provider["masks"] as? [[String: Any]] ?? []
        let providerPose = provider["pose_keypoints"] as? [[String: Any]] ?? []
        let providerUsable = provider["provider_id"] != nil
            && (!providerMasks.isEmpty || !providerPose.isEmpty)
        trace.append(.init(
            round: 0, actor: "APPLE_VISION_LOCAL_PROVIDER",
            action: "PROPOSE_PERSON_POSE_AND_CLOTHED_SUBJECT_ENVELOPE",
            verdict: providerUsable
                ? "PROPOSED_LOCAL_BODY_GARMENT_EVIDENCE"
                : (provider["verdict"] as? String
                   ?? "UNKNOWN_LOCAL_BODY_GARMENT_EVIDENCE")))
        if providerUsable {
            visionPipelineReviewItems = Self.uniqueRequirementItems(
                visionPipelineReviewItems + [[
                    "code": "REVIEW_CLOTHED_SUBJECT_PROXY_NOT_BODY_MEASUREMENT",
                    "state": "REVIEW",
                    "why": "Apple Visionの人物輪郭は服・髪を含む比較用BODY候補です。裸身形状、実寸、背面観測、縫製入力ではありません。",
                    "rear_state": "UNKNOWN_UNOBSERVED",
                    "manufacturing_ready": false,
                ]])
        }

        var request: [String: Any] = [
            "schema": "garment.body-image-separation.request.v1",
            "source": source,
            "selection_mode": activeAuditMode == .autoProposed
                ? "AUTO_PROPOSED" : "HUMAN_APPROVAL",
            "camera": camera,
        ]
        if providerUsable {
            request["provider_outputs"] = [provider]
        } else {
            request["local_fallback"] = fallback
        }
        guard let jsonText = Self.jsonString(request) else { return nil }
        let response = await toolDoor(
            "garment_body_image_separation_propose", ["json_text": jsonText])
        let verdict = response["verdict"] as? String
            ?? "UNKNOWN_BODY_IMAGE_SEPARATION_MCP"
        trace.append(.init(
            round: 0, actor: "VERA_BODY_IMAGE_SEPARATION_MCP",
            action: "NORMALISE_FRONT_BODY_GARMENT_CHANNELS",
            verdict: verdict))

        let reviews = (response["review_items"] as? [[String: Any]] ?? []).map {
            row -> [String: Any] in
            var review = row
            review["state"] = "REVIEW"
            review["rear_state"] = "UNKNOWN_UNOBSERVED"
            review["manufacturing_ready"] = false
            return review
        }
        visionPipelineReviewItems = Self.uniqueRequirementItems(
            visionPipelineReviewItems + reviews)
        guard verdict == "PROPOSED_BODY_GARMENT_SEPARATION_CANDIDATES",
              let candidates = response["candidates"] as? [[String: Any]],
              !candidates.isEmpty else {
            visionPipelineReviewItems = Self.uniqueRequirementItems(
                visionPipelineReviewItems + [[
                    "code": verdict,
                    "state": "REVIEW",
                    "why": response["why"] as? String
                        ?? "人体・服・髪・背景の分離候補を準備できませんでした。",
                    "rear_state": "UNKNOWN_UNOBSERVED",
                    "manufacturing_ready": false,
                ]])
            return nil
        }

        let selection = response["selection"] as? [String: Any]
        let selectedID = selection?["selected_candidate_id"] as? String
        let selected = candidates.first { row in
            (row["candidate_id"] as? String) == selectedID
        } ?? candidates[0]
        if activeAuditMode == .humanAudit {
            visionPipelineReviewItems = Self.uniqueRequirementItems(
                visionPipelineReviewItems + [[
                    "code": "REVIEW_BODY_GARMENT_SEPARATION_SELECTION_REQUIRED",
                    "state": "REVIEW",
                    "why": "先頭の分離候補は人体プレビュー準備にだけ使われます。可視部品と削除結果を人が採用するまで事実・製造入力にはなりません。",
                    "candidate_count": candidates.count,
                    "manufacturing_ready": false,
                ]])
        }
        return selected
    }

    /// Ask the deterministic body-proxy boundary for several image-bound
    /// preview mannequins. The request deliberately contains no centimetres
    /// inferred from clothing pixels: the typed separation may constrain a
    /// visual proposal, but it cannot measure the hidden wearer. Explicit chat
    /// dimensions remain REQUESTED_NOT_MEASURED.
    private func prepareBodyProxyCandidates(
        outline: [String: Any], imagePath: String,
        requirements: [GarmentCommandIR.Requirement], evidenceState: String
    ) async {
        func centimetres(_ item: GarmentCommandIR.Requirement) -> Double? {
            guard let value = item.value, let unit = item.unit else { return nil }
            switch unit {
            case .cm: return value
            case .mm: return value / 10.0
            case .m: return value * 100.0
            }
        }
        func canonicalDimension(_ value: String) -> String? {
            let token = value.lowercased()
                .replacingOccurrences(of: "_", with: "")
                .replacingOccurrences(of: "-", with: "")
                .replacingOccurrences(of: " ", with: "")
            if ["height", "stature", "身長"].contains(token) { return "height" }
            if ["chest", "bust", "chestbust", "胸囲", "バスト"].contains(token) {
                return "chest_bust"
            }
            if ["waist", "ウエスト", "胴囲"].contains(token) { return "waist" }
            if ["hip", "hips", "ヒップ", "腰囲"].contains(token) { return "hip" }
            return nil
        }
        func number(_ value: Any?) -> Double? {
            if let value = value as? Double { return value }
            if let value = value as? Int { return Double(value) }
            if let value = value as? NSNumber { return value.doubleValue }
            return nil
        }
        var imageFittedAvatarID: String?

        let separation = await prepareBodyImageSeparation(
            outline: outline, imagePath: imagePath,
            evidenceState: evidenceState)
        let imageDigest: String
        if let bytes = try? Data(contentsOf: URL(fileURLWithPath: imagePath)) {
            imageDigest = Self.sha256(bytes)
        } else {
            imageDigest = Self.sha256(Data(imagePath.utf8))
        }
        let outlineText = Self.jsonString(outline) ?? "{}"
        let outlineDigest = Self.sha256(Data(outlineText.utf8))
        let garmentOutline = (outline["fused_target_outline"] as? [[Double]])
            ?? (outline["outline"] as? [[Double]])
            ?? (outline["points"] as? [[Double]]) ?? []

        var dimensions: [String: Any] = [:]
        for item in requirements where item.kind == .bodyMeasurement {
            guard let key = canonicalDimension(item.target),
                  let value = centimetres(item) else { continue }
            dimensions[key] = [
                "value": value,
                "unit": "cm",
                "authority": "REQUESTED",
                "source": [
                    "kind": "USER_REQUEST",
                    "reference": "garment.command.v1",
                ],
            ]
        }

        var source: [String: Any] = [
            "image_digest": imageDigest,
            "image_id": URL(fileURLWithPath: imagePath).lastPathComponent,
            "orientation": "UP",
        ]
        var camera: [String: Any] = [
            "orientation": "UP",
            "state": "OBSERVED_IMAGE_METADATA",
            "authority": "OBSERVED_IMAGE_METADATA",
        ]
        if let representation = NSImage(contentsOfFile: imagePath)?
            .representations.max(by: {
                $0.pixelsWide * $0.pixelsHigh < $1.pixelsWide * $1.pixelsHigh
            }), representation.pixelsWide > 0, representation.pixelsHigh > 0 {
            source["width"] = representation.pixelsWide
            source["height"] = representation.pixelsHigh
            camera["width_px"] = representation.pixelsWide
            camera["height_px"] = representation.pixelsHigh
        }

        // Preserve the exact selected separation as the common evidence
        // envelope for body fitting, second-skin construction and rear
        // candidates. The fallback contains only a front garment outline and
        // therefore remains PROPOSED; it never invents a hidden body or rear.
        var selectedSeparation = separation ?? [
            "candidate_id": "front-outline-separation",
            "state": "PROPOSED",
            "authority": "PROPOSED",
            "coordinate_space": "PIXELS",
            "camera": camera,
            "masks": garmentOutline.count >= 3 ? [[
                "mask_id": "front-garment-outline",
                "class": "GARMENT",
                "mask_digest": outlineDigest,
                "outline": garmentOutline,
                "confidence": evidenceState.uppercased() == "OBSERVED" ? 1.0 : 0.55,
                "authority": evidenceState.uppercased() == "OBSERVED"
                    ? "OBSERVED" : "PROPOSED",
            ]] : [],
        ]
        let selectedSeparationID = selectedSeparation["candidate_id"] as? String
            ?? "selected-front-separation"
        selectedSeparation["candidate_id"] = selectedSeparationID
        if selectedSeparation["camera"] == nil {
            selectedSeparation["camera"] = camera
        }
        let separationEnvelope: [String: Any] = [
            "schema": "garment.body-image-separation.v1",
            "source": source,
            "candidates": [selectedSeparation],
            "selection": ["selected_candidate_id": selectedSeparationID],
            "rear_state": "UNKNOWN_UNOBSERVED",
            "manufacturing_ready": false,
        ]
        activeBodyImageSeparationEnvelope = separationEnvelope
        activeBodyRequestedMeasurements = dimensions

        var fitRequest: [String: Any] = [
            "schema": "garment.body-avatar-fit.request.v1",
            "separation": separationEnvelope,
            "requested_measurements": dimensions,
            "interpolation": [
                "method": "LINEAR_BOUNDED",
                "allowed_dimensions": dimensions.keys.sorted(),
            ],
        ]
        if let targetDigest = targetSculptDigest {
            fitRequest["human_edit_digest"] = targetDigest
        }
        if let fitText = Self.jsonString(fitRequest) {
            let fit = await toolDoor(
                "garment_body_avatar_fit", ["json_text": fitText])
            let fitVerdict = fit["verdict"] as? String
                ?? "UNKNOWN_BODY_AVATAR_FIT_MCP"
            trace.append(.init(
                round: 0, actor: "VERA_BODY_AVATAR_FIT_MCP",
                action: "FIT_BOUNDED_AVATAR_TO_FRONT_IMAGE",
                verdict: fitVerdict))
            if fitVerdict == "PROPOSED_IMAGE_RELATIVE_BODY_AVATAR_FIT",
               let avatar = fit["selected_avatar"] as? [String: Any],
               let avatarID = avatar["avatar_id"] as? String,
               let geometryDigest = avatar["geometry_digest"] as? String,
               let controls = avatar["dimensions_cm"] as? [String: Any],
               let height = number(controls["height"]),
               let chest = number(controls["chest_bust"]),
               let waist = number(controls["waist"]),
               let hip = number(controls["hip"]) {
                let profile = BaseAvatarProfile(
                    id: avatarID,
                    title: String(format: "画像位置合わせ %.0f · %.0f / %.0f / %.0f cm",
                                  height, chest, waist, hip),
                    heightCM: height, chestCM: chest, waistCM: waist, hipCM: hip,
                    geometryDigest: geometryDigest,
                    authority: "PROPOSED_IMAGE_RELATIVE_PREVIEW")
                baseAvatarProfiles = [profile] + baseAvatarProfiles.filter {
                    $0.id != profile.id
                }
                selectedBaseAvatarID = profile.id
                imageFittedAvatarID = profile.id
                activeImageRelativeBodyFit = fit
                imageRelativeBodyFitDigest = fit["contract_digest"] as? String
            }
        }

        var request: [String: Any] = [
            "schema": "garment.body-proxy.request.v1",
            "source": source,
            "selection_mode": activeAuditMode == .autoProposed
                ? "AUTO_PROPOSED" : "HUMAN_APPROVAL",
            "camera": camera,
            "dimensions": dimensions,
        ]
        var separationMasks: [[String: Any]] = []
        if let masks = separation?["masks"] as? [[String: Any]] {
            separationMasks = masks.compactMap { row in
                guard let maskID = row["mask_id"] as? String,
                      let kind = row["class"] as? String,
                      ["BODY", "GARMENT"].contains(kind.uppercased()) else {
                    return nil
                }
                let maskDigest = row["mask_digest"] as? String
                let maskOutline = row["outline"] as? [[Double]] ?? []
                guard maskDigest?.isEmpty == false || maskOutline.count >= 3 else {
                    return nil
                }
                var bridged: [String: Any] = [
                    "candidate_id": maskID,
                    "kind": kind.uppercased(),
                    "outline": maskOutline,
                    "confidence": number(row["confidence"]) ?? 0.0,
                    "state": row["authority"] as? String ?? "PROPOSED",
                ]
                if let maskDigest, !maskDigest.isEmpty {
                    bridged["mask_digest"] = maskDigest
                }
                return bridged
            }
            if let pose = separation?["pose_keypoints"] as? [[String: Any]],
               !pose.isEmpty {
                request["pose_keypoints_2d"] = pose
            }
            if let skin = separation?["exposed_skin_contours"]
                as? [[String: Any]], !skin.isEmpty {
                request["exposed_skin_contours"] = skin
            }
        }
        if !separationMasks.isEmpty {
            request["mask_candidates"] = separationMasks
        } else if garmentOutline.count >= 3 {
            request["mask_candidates"] = [[
                "candidate_id": "front-garment-outline",
                "kind": "GARMENT",
                "mask_digest": outlineDigest,
                "outline": garmentOutline,
                "confidence": evidenceState.uppercased() == "OBSERVED" ? 1.0 : 0.55,
                "state": evidenceState.uppercased() == "OBSERVED"
                    ? "OBSERVED" : "PROPOSED",
            ]]
        }
        guard let jsonText = Self.jsonString(request) else { return }
        let response = await toolDoor(
            "garment_body_proxy_propose", ["json_text": jsonText])
        let verdict = response["verdict"] as? String
            ?? "UNKNOWN_BODY_PROXY_MCP"
        trace.append(.init(
            round: 0, actor: "VERA_BODY_PROXY_MCP",
            action: "PROPOSE_IMAGE_BOUND_BODY_ALTERNATIVES",
            verdict: verdict))

        let reviews = (response["review_items"] as? [[String: Any]] ?? []).map {
            row -> [String: Any] in
            var review = row
            review["state"] = "REVIEW"
            review["manufacturing_ready"] = false
            return review
        }
        visionPipelineReviewItems = Self.uniqueRequirementItems(
            visionPipelineReviewItems + reviews)
        guard verdict == "PROPOSED_BODY_PROXY_CANDIDATES",
              let candidates = response["candidates"] as? [[String: Any]] else {
            visionPipelineReviewItems = Self.uniqueRequirementItems(
                visionPipelineReviewItems + [[
                    "code": verdict,
                    "state": "REVIEW",
                    "why": response["why"] as? String
                        ?? "画像に拘束した人体候補を準備できませんでした。",
                    "manufacturing_ready": false,
                ]])
            return
        }

        var profiles: [BaseAvatarProfile] = []
        var avatarForCandidate: [String: String] = [:]
        for row in candidates {
            guard let candidateID = row["candidate_id"] as? String,
                  let avatar = row["avatar_binding"] as? [String: Any],
                  let avatarID = avatar["avatar_id"] as? String,
                  let geometryDigest = avatar["geometry_digest"] as? String,
                  let measurements = avatar["measurements_cm"] as? [String: Any],
                  let height = number(measurements["height"]),
                  let chest = number(measurements["chest_bust"]),
                  let waist = number(measurements["waist"]),
                  let hip = number(measurements["hip"]) else { continue }
            let label = row["label"] as? String ?? "BODY_PROXY"
            profiles.append(.init(
                id: avatarID,
                title: String(format: "%@ %.0f · %.0f / %.0f / %.0f cm",
                              label, height, chest, waist, hip),
                heightCM: height, chestCM: chest, waistCM: waist, hipCM: hip,
                geometryDigest: geometryDigest,
                authority: "PROPOSED_BODY_PROXY"))
            avatarForCandidate[candidateID] = avatarID
        }
        guard !profiles.isEmpty else { return }
        baseAvatarProfiles = profiles + baseAvatarProfiles.filter {
            !$0.id.hasPrefix("avatar:body-proxy:")
        }
        if activeAuditMode == .autoProposed,
           let selection = response["selection"] as? [String: Any],
           let candidateID = selection["selected_candidate_id"] as? String,
           let avatarID = avatarForCandidate[candidateID] {
            selectedBaseAvatarID = avatarID
        }
        // The image-relative fit and the second-skin engine share this exact
        // avatar geometry. The older body-proxy alternatives remain selectable
        // but may not silently replace it merely because AUTO_PROPOSED ran.
        if let imageFittedAvatarID {
            selectedBaseAvatarID = imageFittedAvatarID
        }
    }

    init(hardRoundLimit: Int = 8, door: Door? = nil, toolDoor: ToolDoor? = nil) {
        self.hardRoundLimit = max(1, hardRoundLimit)
        self.liveExternalEffectsEnabled = door == nil && toolDoor == nil
        self.door = door ?? { action, request in
            var payload = request
            payload["action"] = action
            guard JSONSerialization.isValidJSONObject(payload),
                  let data = try? JSONSerialization.data(
                    withJSONObject: payload, options: [.sortedKeys]),
                  let text = String(data: data, encoding: .utf8) else {
                return ["verdict": "UNKNOWN_FACTORY_REQUEST_ENCODING"]
            }
            let raw = await MCPEngine.shared.callTool(
                serverName: "vera-memory", toolName: "garment_factory",
                arguments: ["json_text": text, "action": action])
            guard let resultData = raw.data(using: .utf8),
                  let object = try? JSONSerialization.jsonObject(with: resultData),
                  let dictionary = object as? [String: Any] else {
                return ["verdict": "UNKNOWN_FACTORY_ENGINE_UNREACHABLE"]
            }
            return dictionary
        }
        self.toolDoor = toolDoor ?? { tool, arguments in
            let raw = await MCPEngine.shared.callTool(
                serverName: "vera-memory", toolName: tool, arguments: arguments)
            guard let data = raw.data(using: .utf8),
                  let object = try? JSONSerialization.jsonObject(with: data),
                  let dictionary = object as? [String: Any] else {
                return ["verdict": "UNKNOWN_FACTORY_ENGINE_UNREACHABLE"]
            }
            return dictionary
        }
    }

    /// Canonical project activation hook used by AppState. A pending request
    /// or consent from one garment must never be actionable in another.
    func activateResolutionProject(_ name: String) {
        let normalized = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !normalized.isEmpty else { return }
        guard normalized != activeResolutionProject else { return }
        activeResolutionProject = normalized
        pendingResolutionRequest = nil
        activeLLMProposalConsent = nil
        selectedResolutionAction = nil
    }

    /// Selects the review policy for the next image run. An active run keeps
    /// its captured mode so a UI click cannot silently change provenance in
    /// the middle of the append-only factory journal.
    func selectInitialAuditMode(_ mode: InitialAuditMode) {
        selectedAuditMode = mode
        if phase == "EMPTY" || phase == "IMAGE_PREVIEW_WARMUP"
            || phase == "IMAGE_PREVIEW_READY" {
            activeAuditMode = mode
        }
        trace.append(.init(
            round: 0, actor: "HUMAN_AUDIT_MODE_SELECTION",
            action: "USE_\(mode.rawValue)_FOR_NEXT_IMAGE",
            verdict: mode == .humanAudit
                ? "HUMAN_REVIEW_REQUIRED" : "AUTO_ACCEPTED_FOR_PREVIEW_ONLY"))
    }

    /// Persist an explicit one-shot proposal grant through Python's
    /// GRANT_LLM_PROPOSAL_CONSENT event.  A local checkbox is not consent: the
    /// returned artifact must also exist in the persisted cross-workflow.
    public func grantOneTimeLLMProposalConsent(
        requestID: String, provenanceDigest: String, projectName: String,
        by actor: String
    ) async -> ResolutionEventOutcome {
        guard !resolutionEventInFlight else {
            return .rejected(
                "UNKNOWN_RESOLUTION_EVENT_IN_FLIGHT", requestID: requestID,
                message: "別の解決イベントを検証中です。")
        }
        guard let request = validatedPendingRequest(
            requestID: requestID, provenanceDigest: provenanceDigest,
            projectName: projectName,
            requiredAction: .allowOneTimeLLMProposal) else {
            return .rejected(
                "UNKNOWN_STALE_RESOLUTION_REQUEST", requestID: requestID,
                message: "request、provenance digest、またはprojectが現在の要求と一致しません。")
        }
        let namedActor = actor.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !namedActor.isEmpty, !Self.isModelResolutionActor(namedActor) else {
            return .rejected(
                "UNKNOWN_INVALID_CONSENT_GRANTOR", requestID: requestID,
                message: "一回限りのLLM提案許可には、モデルではない名前付きの許可者が必要です。")
        }

        resolutionEventInFlight = true
        defer { resolutionEventInFlight = false }
        let inspected = await door("inspect", [:])
        guard let inspectedState = state(from: inspected),
              let workflow = inspectedState["cross_workflow"] as? [String: Any],
              let revision = Self.integer(workflow["revision"]),
              Self.hasOpenObligation(requestID, in: workflow) else {
            return .rejected(
                "UNKNOWN_STALE_CROSS_OBLIGATION", requestID: requestID,
                message: "永続工場に同じOPEN obligationがありません。")
        }
        guard requestStillMatches(request, projectName: projectName) else {
            return .rejected(
                "UNKNOWN_STALE_RESOLUTION_REQUEST", requestID: requestID,
                message: "検証中にprojectまたは要求が更新されました。")
        }

        let event: [String: Any] = [
            "type": "GRANT_LLM_PROPOSAL_CONSENT",
            "scope": request.stage,
            "fields": request.missingFields,
            "granted_by": namedActor,
            "expires_after_revision": revision + 1,
            "request_id": request.id,
        ]
        let response = await advance(event: event)
        let verdict = response["verdict"] as? String
            ?? "UNKNOWN_FACTORY_ENGINE_RESPONSE"
        guard verdict == "CONSENT_RECORDED",
              let artifact = response["consent_artifact"] as? [String: Any],
              let consentDigest = artifact["consent_digest"] as? String,
              !consentDigest.isEmpty,
              let boundWorkflowDigest = artifact["bound_workflow_digest"] as? String,
              !boundWorkflowDigest.isEmpty,
              artifact["request_id"] as? String == request.id,
              artifact["scope"] as? String == request.stage,
              artifact["granted_by"] as? String == namedActor,
              (artifact["authority_ceiling"] as? String)?.uppercased() == "PROPOSED",
              artifact["may_promote_to_observed"] as? Bool == false,
              Self.stringSet(artifact["fields"]) == Set(request.missingFields),
              let persisted = state(from: response),
              Self.persistedConsent(
                consentDigest, requestID: request.id,
                projectRequest: request, actor: namedActor, in: persisted) != nil
        else {
            return .rejected(
                verdict, requestID: requestID,
                message: refusalText(response).isEmpty
                    ? "工場がdigest付き同意を永続化したことを確認できませんでした。"
                    : refusalText(response))
        }
        guard requestStillMatches(request, projectName: projectName) else {
            locallyRevokedConsentDigests.insert(consentDigest)
            return .rejected(
                "UNKNOWN_STALE_PROJECT_AFTER_CONSENT", requestID: requestID,
                message: "同意記録中にprojectが切り替わったため、このクライアントでは同意を失効扱いにしました。")
        }

        locallyRevokedConsentDigests.remove(consentDigest)
        activeLLMProposalConsent = .init(
            schema: artifact["schema"] as? String
                ?? "cross.workflow.consent.v1",
            requestID: request.id, projectName: projectName,
            stage: request.stage, grantedBy: namedActor,
            subjectDigest: request.provenanceDigest,
            engineConsentDigest: consentDigest,
            boundWorkflowDigest: boundWorkflowDigest,
            authorityCeiling: "PROPOSED", maximumUses: 1,
            remainingUses: 1)
        selectedResolutionAction = .allowOneTimeLLMProposal
        trace.append(.init(
            round: max(1, trace.count), actor: namedActor,
            action: "GRANT_LLM_PROPOSAL_CONSENT_\(request.stage)",
            verdict: "CONSENT_RECORDED_PROPOSAL_ONLY"))
        return .init(
            accepted: true, verdict: verdict, requestID: request.id,
            message: "一回限りのPROPOSED権限を永続工場へ記録しました。",
            consentDigest: consentDigest,
            boundWorkflowDigest: boundWorkflowDigest,
            resolutionStatus: nil)
    }

    func revokeLLMProposalConsent() {
        guard let consent = activeLLMProposalConsent else { return }
        locallyRevokedConsentDigests.insert(consent.engineConsentDigest)
        trace.append(.init(
            round: max(1, trace.count), actor: consent.grantedBy,
            action: "REVOKE_LLM_PROPOSAL_CONSENT_\(consent.stage)",
            verdict: "CONSENT_REVOKED"))
        activeLLMProposalConsent = nil
        if selectedResolutionAction == .allowOneTimeLLMProposal {
            selectedResolutionAction = nil
        }
    }

    /// Record a non-LLM resolution route selected in the progressive sidebar.
    /// Human input/edit routes remain pending until the corresponding typed
    /// engine event succeeds; choosing a bounded preview may dismiss the card
    /// without pretending the hidden value became known.
    @discardableResult
    func selectResolutionAction(
        _ kind: ResolutionActionKind, requestID: String, by actor: String
    ) -> Bool {
        guard let request = pendingResolutionRequest,
              request.id == requestID,
              request.options.contains(where: { $0.kind == kind }),
              kind != .allowOneTimeLLMProposal else { return false }
        selectedResolutionAction = kind
        trace.append(.init(
            round: max(1, trace.count),
            actor: actor.trimmingCharacters(in: .whitespacesAndNewlines)
                .isEmpty ? "HUMAN" : actor,
            action: "RESOLUTION_\(kind.rawValue)_\(request.stage)",
            verdict: kind == .typedStop ? request.code : "RESOLUTION_SELECTED"))
        return true
    }

    /// Called only after a typed human-input/CAD/provider event has succeeded.
    /// A UI click by itself must not clear the obligation.
    func acknowledgeResolvedRequest(_ requestID: String) {
        guard pendingResolutionRequest?.id == requestID else { return }
        pendingResolutionRequest = nil
        selectedResolutionAction = nil
    }

    /// Persist and verify a typed resolution through Python's
    /// RESOLVE_CROSS_OBLIGATION event.  This is the only sidebar boundary that
    /// can close a request.  A UI selection or chat marker cannot call this
    /// method without the exact request id, provenance digest and project.
    public func resolveCrossObligation(
        requestID: String, provenanceDigest: String, projectName: String,
        path: CrossResolutionPath, values: [String: Any] = [:],
        actor: String, consentDigest: String? = nil,
        resumeAfterAcceptance: Bool = true,
        resumeRequest: String = "Continue the garment factory from the accepted typed resolution."
    ) async -> ResolutionEventOutcome {
        guard !resolutionEventInFlight else {
            return .rejected(
                "UNKNOWN_RESOLUTION_EVENT_IN_FLIGHT", requestID: requestID,
                message: "別の解決イベントを検証中です。")
        }
        let requiredAction = Self.actionKind(for: path)
        guard let request = validatedPendingRequest(
            requestID: requestID, provenanceDigest: provenanceDigest,
            projectName: projectName, requiredAction: requiredAction) else {
            return .rejected(
                "UNKNOWN_STALE_RESOLUTION_REQUEST", requestID: requestID,
                message: "request、provenance digest、またはprojectが現在の要求と一致しません。")
        }
        let namedActor = actor.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !namedActor.isEmpty else {
            return .rejected(
                "UNKNOWN_RESOLUTION_ACTOR_REQUIRED", requestID: requestID,
                message: "解決イベントには名前付きの実行者が必要です。")
        }

        let valuePaths: Set<CrossResolutionPath> = [
            .humanInput, .measuredInput, .humanEdit,
            .consentedLLMProposal, .boundedAlternatives,
        ]
        let expectedFields = Set(request.missingFields)
        let suppliedFields = Set(values.keys)
        if valuePaths.contains(path) {
            guard !values.isEmpty, suppliedFields == expectedFields else {
                return .rejected(
                    "UNKNOWN_RESOLUTION_FIELD_MISMATCH", requestID: requestID,
                    message: "値は要求に列挙された全項目だけを埋める必要があります。")
            }
        } else if !values.isEmpty {
            return .rejected(
                "UNKNOWN_UNEXPECTED_RESOLUTION_VALUES", requestID: requestID,
                message: "この解決経路は値を受け取りません。")
        }

        var verifiedConsentDigest: String?
        var verifiedBoundWorkflowDigest: String?
        if path == .consentedLLMProposal {
            guard let consent = activeLLMProposalConsent,
                  consent.requestID == request.id,
                  consent.projectName == projectName,
                  consent.subjectDigest == request.provenanceDigest,
                  consent.remainingUses > 0,
                  consent.authorityCeiling == "PROPOSED",
                  !locallyRevokedConsentDigests.contains(
                    consent.engineConsentDigest),
                  consentDigest == nil
                    || consentDigest == consent.engineConsentDigest else {
                return .rejected(
                    "UNKNOWN_MODEL_CONSENT_REQUIRED", requestID: requestID,
                    message: "このrequest/digest/projectに束縛された未使用の同意がありません。")
            }
            verifiedConsentDigest = consent.engineConsentDigest
            verifiedBoundWorkflowDigest = consent.boundWorkflowDigest
        } else if Self.isModelResolutionActor(namedActor) {
            return .rejected(
                "UNKNOWN_MODEL_RESOLUTION_PATH", requestID: requestID,
                message: "モデル出力はCONSENTED_LLM_PROPOSAL以外の解決経路を実行できません。")
        }

        var provenance: [String: Any] = [
            "request_provenance_digest": request.provenanceDigest,
            "project_name": projectName,
            "authority_ceiling": path == .consentedLLMProposal
                || path == .boundedAlternatives ? "PROPOSED" : "HUMAN_SCOPED",
            "source_type": Self.sourceType(for: path),
            "may_promote_model_output_to_observed": false,
        ]
        if path == .humanInput {
            provenance["not_image_observed"] = true
        }
        var event: [String: Any] = [
            "type": "RESOLVE_CROSS_OBLIGATION",
            "request_id": request.id,
            "choice": path.rawValue,
            "actor": namedActor,
            "provenance": provenance,
        ]
        if !values.isEmpty { event["values"] = values }
        if let verifiedConsentDigest {
            event["consent_digest"] = verifiedConsentDigest
        }

        resolutionEventInFlight = true
        defer { resolutionEventInFlight = false }
        let response = await advance(event: event)
        let verdict = response["verdict"] as? String
            ?? "UNKNOWN_FACTORY_ENGINE_RESPONSE"
        guard let persistedState = state(from: response),
              let persistedResolution = Self.persistedResolution(
                request: request, projectName: projectName, path: path,
                actor: namedActor, values: values,
                consentDigest: verifiedConsentDigest, in: persistedState),
              let status = persistedResolution["status"] as? String else {
            return .rejected(
                verdict, requestID: requestID,
                message: refusalText(response).isEmpty
                    ? "工場の永続resolutions台帳に一致するイベントがありません。"
                    : refusalText(response))
        }
        let isProviderPartial = path == .connectProvider
            && status == "PARTIALLY_RESOLVED"
            && verdict == "UNKNOWN_PARTIAL_RESOLUTION"
        let expectedVerdict = path == .typedStop ? "TYPED_STOP" : "ANSWER"
        guard verdict == expectedVerdict || isProviderPartial else {
            return .rejected(
                verdict, requestID: requestID,
                message: refusalText(response).isEmpty
                    ? "工場は解決イベントを受理しませんでした。" : refusalText(response))
        }
        guard requestStillMatches(request, projectName: projectName) else {
            return .rejected(
                "UNKNOWN_STALE_PROJECT_AFTER_RESOLUTION", requestID: requestID,
                message: "イベント記録中にprojectまたは要求が切り替わりました。")
        }

        trace.append(.init(
            round: max(1, trace.count), actor: namedActor,
            action: "RESOLVE_CROSS_OBLIGATION_\(path.rawValue)",
            verdict: status))
        selectedResolutionAction = requiredAction
        if path == .typedStop {
            pendingResolutionRequest = .init(
                id: request.id, code: request.code, stage: request.stage,
                title: "型付き停止", explanation: request.explanation,
                missingFields: request.missingFields,
                options: [Self.resolutionOption(
                    .typedStop, code: request.code, stage: request.stage)],
                provenanceDigest: request.provenanceDigest,
                authority: "TYPED_STOP_NO_RESULT_CLAIM", terminal: true)
            activeLLMProposalConsent = nil
        } else if isProviderPartial {
            // Connecting is a recorded action, not fabricated evidence. Keep
            // the request visible until a provider artifact closes its fields.
            pendingResolutionRequest = request
        } else {
            pendingResolutionRequest = nil
            selectedResolutionAction = nil
            activeLLMProposalConsent = nil
        }

        let baseMessage = isProviderPartial
            ? "接続要求を永続化しました。資料が届くまで不足項目はOPENのままです。"
            : "\(path.rawValue)を永続工場へ記録しました。"
        if resumeAfterAcceptance, !isProviderPartial, path != .typedStop {
            let resumed = await runUntilPause(
                userRequest: resumeRequest, proposer: nil)
            return .init(
                accepted: true, verdict: verdict, requestID: request.id,
                message: "\(baseMessage) 次の停止: \(resumed.verdict)",
                consentDigest: verifiedConsentDigest,
                boundWorkflowDigest: verifiedBoundWorkflowDigest,
                resolutionStatus: status)
        }
        return .init(
            accepted: true, verdict: verdict, requestID: request.id,
            message: baseMessage, consentDigest: verifiedConsentDigest,
            boundWorkflowDigest: verifiedBoundWorkflowDigest,
            resolutionStatus: status)
    }

    /// Invalidate only analysis/UI state when the user performs a new image
    /// selection. The intake ledger and source path are deliberately untouched:
    /// selecting the same file again is a new operation, not duplicate evidence.
    func consumeImageSelection(revision: UInt64, imagePath: String) {
        consumedImageSelectionRevision = revision
        consumedImageSelectionPath = imagePath
        phase = "EMPTY"
        lastReport = nil
        pendingResolutionRequest = nil
        activeLLMProposalConsent = nil
        selectedResolutionAction = nil
        trace.removeAll()
        shapeCandidates.removeAll()
        materialCandidates.removeAll()
        canUndoShapeDecision = false
        visionPatternOperations.removeAll()
        visibleFrontInventory.removeAll()
        visibleFrontInventoryAuditRequired = false
        visibleFrontInventoryAuditConfirmed = false
        visibleFrontInventoryAuthority = "UNREVIEWED"
        activeAuditMode = selectedAuditMode
        pendingBack3DRequest = false
        pendingHumanAuditedVisionRows = []
        pendingHumanAuditUserRequest = ""
        pendingHumanAuditProposer = nil
        initialHumanReviewResumeInFlight = false
        activeVisibleAnalysisDigest = nil
        activeDesignRequirements = []
        persistedForegroundCleanupDigest = nil
        hasPersistedForegroundCleanup = false
        recordedVeraFrontTargetDigests = []
        previewArtifact = nil
        outlineCalibrationBaseline = nil
        candidateManufacturingPreview = nil
        candidateSewingPlan = nil
        candidateMaterialPreview = nil
        previewAttempts = 0
        rawPreviewPattern = nil
        materialPreviewBasePattern = nil
        materialPreviewBaseArtifact = nil
        pendingProceduralHypotheses = []
        pendingVisionHypotheses = []
        activeBodyImageSeparationEnvelope = nil
        activeBodyRequestedMeasurements = [:]
        activeImageRelativeBodyFit = nil
        imageRelativeBodyFitDigest = nil
        activeInitialFashionRetrieval = nil
        activeGeometricAtelierWorkflow = nil
        geometricRearCandidateArtifacts = [:]
        geometricRearCandidateArtifactsInOrder = []
        visionPipelineArtifacts = [:]
        totalModelCalls = 0
        shapeCandidatePayloads = [:]
        materialCandidatePayloads = [:]
        activeShapeDecisionID = nil
        targetReconstruction = nil
        resetTargetSculptModifierState()
        targetCleanupConfirmed = false
        targetSculptRemovedFaces = []
        targetSculptUndoStack = []
        targetSculptThicknessMM = 1.0
        targetSculptRevision = 0
        targetSculptClearancePreview = nil
        targetSameCameraComparison = nil
        targetSculptClearanceTask?.cancel()
        targetSculptClearanceTask = nil
        targetSameCameraTask?.cancel()
        targetSameCameraTask = nil
        referenceSearchTasks.values.forEach { $0.cancel() }
        referenceSearchTasks = [:]
        referenceSearchQueries = [:]
        rearWebReferences = []
        sewingWebReferences = []
        rearReferenceSearchStatus = "IDLE"
        sewingReferenceSearchStatus = "IDLE"
        activeTargetOutline = nil
        activeTargetImagePath = nil
        activeHumanConfirmedFrontEvidence = nil
        targetRemovedRegionIDs = []
    }

    /// Show an explicitly uncommitted second-skin / flat-pattern exploration
    /// while the free-language planner is still composing its reply.  This is
    /// presentation-only warm-up: it does not start the persisted factory,
    /// approve a hypothesis, or convert an automatic outline into OBSERVED.
    func prepareProposedImagePreview(outline: [String: Any], imagePath: String) async {
        guard phase == "EMPTY" || phase == "IMAGE_PREVIEW_WARMUP" else { return }
        guard consumedImageSelectionPath == nil
                || consumedImageSelectionPath == imagePath else { return }
        busy = true
        phase = "IMAGE_PREVIEW_WARMUP"
        lastReport = Report(
            verdict: "PROPOSED", phase: phase,
            message: "制作モデルの自由応答と並行して、第二皮膚・3D人台・型紙の未承認プレビューを生成しています。",
            iterations: 0, modelCalls: 0)
        trace.append(.init(
            round: 0, actor: "VERA_PREVIEW_WARMUP",
            action: "SECOND_SKIN_WHILE_LANGUAGE_MODEL_PLANS",
            verdict: "PROPOSED"))
        await prepareTargetReconstruction(outline: outline, imagePath: imagePath)
        await buildGeometricPreview(outline: outline)
        guard consumedImageSelectionPath == nil
                || consumedImageSelectionPath == imagePath else {
            busy = false
            return
        }
        phase = "IMAGE_PREVIEW_READY"
        if outlineCalibrationBaseline == nil {
            _ = finish(
                "UNKNOWN_PREVIEW_GEOMETRY", phase: phase,
                message: "先行プレビューを構成できませんでした。入力画像の確認、前景編集、または今回限りのAI提案許可を選べます。",
                rounds: previewAttempts, modelCalls: 0,
                context: [
                    "stage": "IMAGE_PREVIEW_READY",
                    "missing_fields": [
                        "second_skin_preview",
                        "same_camera_target_geometry",
                    ],
                    "allowed_resolution_kinds": [
                        ResolutionActionKind.humanGeometryEdit.rawValue,
                        ResolutionActionKind.allowOneTimeLLMProposal.rawValue,
                        ResolutionActionKind.typedStop.rawValue,
                    ],
                    "authority": "UNRESOLVED_FRONT_GEOMETRY",
                ])
        } else {
            lastReport = Report(
                verdict: "PROPOSED", phase: phase,
                message: "輪郭校正ベースラインを内部で準備しました。候補固有3Dは画像部品の監査後に表示します。",
                iterations: previewAttempts, modelCalls: 0)
        }
        busy = false
    }

    /// The closed transition table.  It is pure and therefore testable
    /// without a model, MCP server, UI, or mutable singleton state.
    static func decide(state: [String: Any]) -> DeterministicAction {
        let phase = state["phase"] as? String ?? "EMPTY"
        switch phase {
        case "EMPTY":
            return .init(kind: .waitForImage, eventType: nil, modelTask: nil,
                         code: "UNKNOWN_IMAGE_CONFIRMATION_REQUIRED",
                         message: "服領域を確認した画像が必要です。")
        case "REGIONS_CONFIRMED":
            return .init(kind: .waitForRetrieval, eventType: nil, modelTask: nil,
                         code: "UNKNOWN_RETRIEVAL_BACKEND",
                         message: "部位別類似度検索結果を待っています。LLMで検索結果を捏造しません。")
        case "HUMAN_GARMENT_AUDIT_REQUIRED":
            return .init(kind: .waitForHuman, eventType: nil, modelTask: nil,
                         code: "UNKNOWN_HUMAN_GARMENT_AUDIT_REQUIRED",
                         message: "AIが提案した正面の衣服数・層・可視部品の人間監査を待っています。")
        case "FOREGROUND_CLEANUP_REQUIRED":
            return .init(kind: .waitForHuman, eventType: nil, modelTask: nil,
                         code: "UNKNOWN_FOREGROUND_CLEANUP_REQUIRED",
                         message: "背景・髪・人体・別衣服を除いた前面ターゲットの採用を待っています。")
        case "FRONT_FACTS_RECORDED":
            return .init(kind: .waitForHuman, eventType: nil, modelTask: nil,
                         code: "FRONT_FACTS_RECORDED",
                         message: "人間監査済みの正面事実を記録しました。背面・素材・縫製は未観測です。")
        case "RETRIEVAL_READY":
            return .init(kind: .askModel, eventType: "SUBMIT_HYPOTHESES",
                         modelTask: "structure_hypotheses", code: "PROPOSE_STRUCTURE",
                         message: "検索候補から複数の背面・構造案を提案します。")
        case "BACK_CANDIDATES_READY", "STRUCTURE_CANDIDATES_READY":
            return .init(kind: .waitForHuman, eventType: nil, modelTask: nil,
                         code: "UNKNOWN_SHAPE_APPROVAL_REQUIRED",
                         message: "3D構造候補の選択とdigest承認を待っています。")
        case "STRUCTURE_APPROVED":
            return .init(kind: .callEngine, eventType: "GENERATE_PATTERN", modelTask: nil,
                         code: "GENERATE_PATTERN", message: "承認構造に結び付けた基礎型紙を生成します。")
        case "PATTERN_READY":
            return .init(kind: .callEngine, eventType: "REPAIR_PATTERN", modelTask: nil,
                         code: "REPAIR_PATTERN", message: "決定論的な縫製可能性修復を実行します。")
        case "PATTERN_REPAIRED":
            return .init(kind: .askModel, eventType: "SUBMIT_MATERIAL_CANDIDATES",
                         modelTask: "material_candidates", code: "PROPOSE_MATERIALS",
                         message: "物性値を明示した素材候補を提案します。")
        case "MATERIAL_CANDIDATES_READY":
            return .init(kind: .waitForHuman, eventType: nil, modelTask: nil,
                         code: "UNKNOWN_MATERIAL_APPROVAL_REQUIRED",
                         message: "素材候補の選択とdigest承認を待っています。")
        case "MATERIAL_APPROVED":
            if findDictionary(named: "simulation_input", in: state) != nil {
                return .init(kind: .callEngine, eventType: "SIMULATE", modelTask: nil,
                             code: "SIMULATE", message: "承認済み物性で布シミュレーションを実行します。")
            }
            return .init(kind: .waitForSimulationInput, eventType: nil, modelTask: nil,
                         code: "UNKNOWN_SIMULATION_INPUT_REQUIRED",
                         message: "型付きメッシュ・材料・境界条件が必要です。")
        case "SIMULATION_READY":
            if state["sewing"] == nil || state["sewing"] is NSNull {
                return .init(kind: .waitForSewingCorpus, eventType: nil, modelTask: nil,
                             code: "UNKNOWN_NO_SEWING_CORPUS",
                             message: "権利・系譜付き縫製コーパスを待っています。")
            }
            return .init(kind: .callEngine, eventType: "ITERATE", modelTask: nil,
                         code: "CHECK_CONVERGENCE", message: "決定論的収束条件を検査します。")
        case "SEWING_CANDIDATES_READY", "ITERATING":
            return .init(kind: .callEngine, eventType: "ITERATE", modelTask: nil,
                         code: "CHECK_CONVERGENCE", message: "不足工程と反復上限を検査します。")
        case "CONVERGED_REVIEW":
            return .init(kind: .converged, eventType: nil, modelTask: nil,
                         code: "CONVERGED_REVIEW", message: "工学レビュー可能な状態へ収束しました。")
        default:
            return .init(kind: .stopped, eventType: nil, modelTask: nil,
                         code: "UNKNOWN_FACTORY_PHASE", message: "未対応の工程状態です: \(phase)")
        }
    }

    /// Start/restart the per-project factory from an explicitly confirmed
    /// clothing outline.  Existing image pixels never become a garment claim;
    /// only the confirmed outline and region address enter OBSERVED state.
    func beginConfirmedImage(outline: [String: Any], imagePath: String,
                             userRequest: String,
                             designRequirements: [GarmentCommandIR.Requirement] = [],
                             proposer: Proposer? = nil,
                             visionProposer: VisionProposer? = nil,
                             initialFashionRetrieval: [String: Any]? = nil,
                             evidenceState: String = "OBSERVED") async -> Report {
        busy = true
        defer { busy = false }
        // Freeze the user's policy at job start. Changing the picker later is
        // explicitly a next-image choice and cannot rewrite this run's audit.
        activeAuditMode = selectedAuditMode
        trace.removeAll()
        previewArtifact = nil
        outlineCalibrationBaseline = nil
        candidateManufacturingPreview = nil
        candidateSewingPlan = nil
        candidateMaterialPreview = nil
        previewAttempts = 0
        rawPreviewPattern = nil
        materialPreviewBasePattern = nil
        materialPreviewBaseArtifact = nil
        pendingProceduralHypotheses = []
        pendingVisionHypotheses = []
        activeBodyImageSeparationEnvelope = nil
        activeBodyRequestedMeasurements = [:]
        activeImageRelativeBodyFit = nil
        imageRelativeBodyFitDigest = nil
        activeInitialFashionRetrieval = nil
        activeGeometricAtelierWorkflow = nil
        activeHumanConfirmedFrontEvidence = nil
        geometricRearCandidateArtifacts = [:]
        geometricRearCandidateArtifactsInOrder = []
        visionPipelineArtifacts = [:]
        totalModelCalls = 0
        shapeCandidatePayloads = [:]
        materialCandidatePayloads = [:]
        canUndoShapeDecision = false
        activeShapeDecisionID = nil
        activeDesignRequirements = designRequirements
        activeDesignRequirementProfile = nil
        designRequirementReviewItems = []
        visionPipelineReviewItems = []
        visibleFrontInventory = []
        visibleFrontInventoryAuditRequired = false
        visibleFrontInventoryAuditConfirmed = false
        visibleFrontInventoryAuthority = "UNREVIEWED"
        pendingBack3DRequest = false
        pendingHumanAuditedVisionRows = []
        pendingHumanAuditUserRequest = userRequest
        pendingHumanAuditProposer = proposer
        initialHumanReviewResumeInFlight = false
        activeVisibleAnalysisDigest = nil
        persistedForegroundCleanupDigest = nil
        hasPersistedForegroundCleanup = false
        recordedVeraFrontTargetDigests = []
        referenceSearchTasks.values.forEach { $0.cancel() }
        referenceSearchTasks = [:]
        referenceSearchQueries = [:]
        rearWebReferences = []
        sewingWebReferences = []
        rearReferenceSearchStatus = "IDLE"
        sewingReferenceSearchStatus = "IDLE"
        // A new append-only factory run must explicitly adopt the target under
        // its own audit mode. Keep same-image edits, but never carry authority.
        targetCleanupConfirmed = false
        if activeTargetImagePath != imagePath {
            targetRemovedRegionIDs = []
            targetCleanupConfirmed = false
            targetSculptRemovedFaces = []
            targetSculptUndoStack = []
            targetSculptThicknessMM = 1.0
            targetSculptRevision = 0
            targetSculptClearancePreview = nil
            targetSameCameraComparison = nil
            targetSculptClearanceTask?.cancel()
            targetSculptClearanceTask = nil
            targetSameCameraTask?.cancel()
            targetSameCameraTask = nil
        }
        selectBodyProxy(from: designRequirements)
        await prepareBodyProxyCandidates(
            outline: outline, imagePath: imagePath,
            requirements: designRequirements, evidenceState: evidenceState)
        if !designRequirements.isEmpty {
            do {
                let prepared = try GarmentDesignRequirementProfileBridge.prepare(
                    requirements: designRequirements)
                let response = await toolDoor(
                    GarmentDesignRequirementProfileBridge.toolName,
                    prepared.arguments)
                let profile = try GarmentDesignRequirementProfileBridge.validate(
                    response: response, prepared: prepared)
                activeDesignRequirementProfile = profile
                designRequirementReviewItems = Self.uniqueRequirementItems(
                    profile.reviewItems
                    + Self.requestedNotMeasuredItems(from: profile.requirements))
                trace.append(.init(
                    round: 0, actor: "VERA_DESIGN_REQUIREMENT_PROFILE",
                    action: "COMPILE_REQUESTED_PREVIEW_DIMENSIONS",
                    verdict: profile.verdict))
            } catch let failure as GarmentDesignRequirementProfileBridge.Failure {
                designRequirementReviewItems = [[
                    "code": failure.code,
                    "state": "REVIEW",
                    "why": failure.detail,
                    "requested_values_applied": false,
                    "manufacturing_ready": false,
                ]]
                trace.append(.init(
                    round: 0, actor: "VERA_DESIGN_REQUIREMENT_PROFILE",
                    action: "COMPILE_REQUESTED_PREVIEW_DIMENSIONS",
                    verdict: failure.code))
            } catch {
                designRequirementReviewItems = [[
                    "code": "UNKNOWN_REQUIREMENT_PROFILE_BRIDGE",
                    "state": "REVIEW",
                    "why": error.localizedDescription,
                    "requested_values_applied": false,
                    "manufacturing_ready": false,
                ]]
            }
        }
        // Build the fused target only after explicit wearer dimensions have
        // selected the body proxy. The old order always reconstructed against
        // the default body and read the user's height/size afterwards.
        await prepareTargetReconstruction(outline: outline, imagePath: imagePath)
        let started = await door("start", [
            "job_id": GarmentGenerationJob.shared.jobID,
            "max_iterations": hardRoundLimit,
            "audit_mode": activeAuditMode.rawValue,
        ])
        guard state(from: started) != nil else {
            return finish("UNKNOWN_CROSS_HARNESS_SCHEMA", phase: "EMPTY",
                          message: "立体十字MCPハーネスを開始できませんでした。",
                          rounds: 0, modelCalls: 0)
        }
        let confirmedRegions = outline["regions"] as? [[String: Any]]
        let event: [String: Any] = [
            "type": "CONFIRM_IMAGE",
            "audit_mode": activeAuditMode.rawValue,
            "outline": outline,
            "regions": confirmedRegions ?? [["region_id": "confirmed-clothing",
                                               "part_id": "garment",
                                               "state": evidenceState]],
            "front_only": true,
            "evidence_state": evidenceState == "OBSERVED" ? "OBSERVED" : "PROPOSED",
            "source": ["image_path": imagePath,
                       "confirmation": evidenceState == "OBSERVED"
                           ? "named user region selection"
                           : "automatic region proposal for preview only"],
        ]
        let result = await advance(event: event)
        guard state(from: result) != nil else {
            return finish(result["verdict"] as? String ?? "UNKNOWN_FACTORY_START",
                          phase: "EMPTY", message: refusalText(result), rounds: 1, modelCalls: 0)
        }
        phase = "REGIONS_CONFIRMED"
        lastReport = Report(verdict: "PROPOSED", phase: phase,
                            message: "画像から第二皮膚と型紙の候補を反復生成しています。",
                            iterations: 0, modelCalls: 0)
        if let visionProposer {
            totalModelCalls += 1
            lastReport = Report(verdict: "PROPOSED", phase: phase,
                                message: "制作モデルが画像の部位・重なり・装飾を構造候補として読んでいます。",
                                iterations: 0, modelCalls: 1)
            // Start the expensive pixel proposal, then build the deterministic
            // second-skin preview while it is running.  A slow or reasoning-
            // heavy vision model must not leave beginner mode as an empty chat
            // canvas for several minutes.  The preview remains PROPOSED and is
            // not allowed to approve the model result when it eventually lands.
            async let rawProposal = visionProposer(
                Self.visionProposalPrompt(userRequest: userRequest), imagePath)
            async let fashionRetrieval = resolvedInitialFashionRetrieval(
                initialFashionRetrieval, imagePath: imagePath)
            await buildGeometricPreview(outline: outline)
            let requiresInitialHumanAudit = activeAuditMode == .humanAudit
            var outcome = await compileVisionProposal(
                await rawProposal,
                deferForHumanAudit: requiresInitialHumanAudit)
            if outcome.rows == nil {
                // One bounded repair turn is cheaper and more reliable than
                // asking a vision model for the full construction ontology in
                // one response. The second call sees the pixels again, but it
                // still only proposes a compact visible-parts IR.
                totalModelCalls += 1
                trace.append(.init(
                    round: 0, actor: "VISION_LLM_PROPOSAL_GATE",
                    action: "RETRY_COMPACT_VISIBLE_PARTS_IR",
                    verdict: outcome.code))
                lastReport = Report(
                    verdict: "PROPOSED_VISION_RETRY", phase: phase,
                    message: "画像の部品JSONを短い契約で一度だけ再取得しています。",
                    iterations: 0, modelCalls: totalModelCalls)
                let repaired = await visionProposer(
                    Self.visionRepairPrompt(
                        userRequest: userRequest, failureCode: outcome.code),
                    imagePath)
                outcome = await compileVisionProposal(
                    repaired,
                    deferForHumanAudit: requiresInitialHumanAudit)
            }
            let retrievalResult = await fashionRetrieval
            activeInitialFashionRetrieval = retrievalResult
            publishInitialFashionRetrieval(retrievalResult)
            if let compiled = outcome.rows {
                await publishInitialImageAnalysisEnsemble(
                    hypotheses: compiled, retrieval: retrievalResult,
                    imagePath: imagePath)
                await prepareGeometricAtelierPreview(
                    from: compiled, retrieval: retrievalResult,
                    humanConfirmed: false)
                var recordEvent: [String: Any] = [
                    "type": "RECORD_AI_VISIBLE_ANALYSIS",
                    "assertions": Self.visibleFrontAssertions(from: compiled),
                    "model": [
                        "authority": "AI_GENERATED_PROPOSAL",
                        "route": "configured local-or-cloud multimodal model",
                    ],
                    "retrieval": retrievalResult,
                ]
                if !requiresInitialHumanAudit {
                    guard let targetDigest = targetSculptDigest else {
                        return finish(
                            "UNKNOWN_AUTO_FOREGROUND_TARGET_REQUIRED",
                            phase: phase,
                            message: "自動モード用の前面ターゲットを構成できませんでした。人体や背景を服として採用せず停止しました。人が確認モードで削除編集するか、分離モデルを接続してください。",
                            rounds: 0, modelCalls: totalModelCalls)
                    }
                    recordEvent["foreground_cleanup"] = [
                        "target_digest": targetDigest,
                        "target_revision": Int(targetSculptRevision),
                        "removed_region_ids": targetRemovedRegionIDs.sorted(),
                        "removed_face_indices": targetSculptRemovedFaces.sorted(),
                        "undo_parent_digests": [],
                    ]
                }
                let recorded = await advance(event: recordEvent)
                guard let recordedState = state(from: recorded),
                      let analysis = recordedState["visible_ai_analysis"]
                        as? [String: Any],
                      let analysisDigest = analysis["analysis_digest"]
                        as? String else {
                    let code = recorded["verdict"] as? String
                        ?? "UNKNOWN_AI_VISIBLE_ANALYSIS_PERSISTENCE"
                    return finish(
                        code, phase: phase,
                        message: refusalText(recorded).isEmpty
                            ? "AIの可視部品提案をVera状態機械へ記録できませんでした。"
                            : refusalText(recorded),
                        rounds: 0, modelCalls: totalModelCalls)
                }
                activeVisibleAnalysisDigest = analysisDigest
                if requiresInitialHumanAudit {
                    guard let recordedState = state(from: recorded),
                          recordedState["phase"] as? String
                            == "HUMAN_GARMENT_AUDIT_REQUIRED",
                          recordedState["audit_mode"] as? String
                            == InitialAuditMode.humanAudit.rawValue else {
                        let code = recorded["verdict"] as? String
                            ?? "UNKNOWN_AI_VISIBLE_ANALYSIS_PERSISTENCE"
                        return finish(
                            code, phase: phase,
                            message: refusalText(recorded).isEmpty
                                ? "AIの可視部品提案をVera状態機械へ記録できませんでした。"
                                : refusalText(recorded),
                            rounds: 0, modelCalls: totalModelCalls)
                    }
                    pendingHumanAuditedVisionRows = compiled
                    visibleFrontInventoryAuditRequired = true
                    visibleFrontInventoryAuditConfirmed = false
                    visibleFrontInventoryAuthority = "AI_GENERATED_PROPOSAL"
                    phase = recordedState["phase"] as? String
                        ?? "HUMAN_GARMENT_AUDIT_REQUIRED"
                    visionPipelineReviewItems = Self.uniqueRequirementItems(
                        visionPipelineReviewItems + [[
                            "code": "HUMAN_VISIBLE_GARMENT_AUDIT_REQUIRED",
                            "state": "REVIEW",
                            "why": "AIが提案した正面の衣服数・層・部品境界を人が確認し、融合前景の不要部分を削って採用するまで3D・型紙へ進みません。",
                            "rear_hidden_observed": false,
                            "material_identity_observed": false,
                            "manufacturing_ready": false,
                        ]])
                    trace.append(.init(
                        round: 0, actor: "VERA_INITIAL_HUMAN_REVIEW_GATE",
                        action: "WAIT_FOR_VISIBLE_INVENTORY_AND_FOREGROUND_CLEANUP",
                        verdict: "HUMAN_GARMENT_AUDIT_REQUIRED"))
                    return finish(
                        "HUMAN_GARMENT_AUDIT_REQUIRED", phase: phase,
                        message: "AIの可視部品台帳を確認し、融合3Dから背景・髪・人体・別衣服を削って比較目標を採用してください。背面と素材は未観測のままです。",
                        rounds: 0, modelCalls: totalModelCalls,
                        context: [
                            "stage": "VISIBLE_FRONT_AUDIT",
                            "missing_fields": [
                                "human_reviewed_visible_inventory",
                                "approved_foreground_target",
                            ],
                            "allowed_resolution_kinds": [
                                ResolutionActionKind.humanInput.rawValue,
                                ResolutionActionKind.humanGeometryEdit.rawValue,
                                ResolutionActionKind.typedStop.rawValue,
                            ],
                            "authority": "AI_GENERATED_PROPOSAL_REQUIRES_HUMAN_REVIEW",
                        ])
                }

                guard recordedState["phase"] as? String
                        == "FRONT_FACTS_RECORDED",
                      recordedState["audit_mode"] as? String
                        == InitialAuditMode.autoProposed.rawValue,
                      let compiledText = Self.jsonString(compiled) else {
                    let code = recorded["verdict"] as? String
                        ?? "UNKNOWN_AUTO_PROPOSED_FRONT_ADOPTION"
                    return finish(
                        code, phase: phase,
                        message: refusalText(recorded).isEmpty
                            ? "AI可視部品と前面マスクをPROPOSED権限で採用できませんでした。"
                            : refusalText(recorded),
                        rounds: 0, modelCalls: totalModelCalls)
                }
                let opened = await advance(event: [
                    "type": "OPEN_RETRIEVAL_AFTER_FRONT_REVIEW",
                    "compiled_front_digest": Self.sha256(Data(compiledText.utf8)),
                    "candidate_count": compiled.count,
                ])
                guard let openedState = state(from: opened),
                      openedState["phase"] as? String == "REGIONS_CONFIRMED" else {
                    let code = opened["verdict"] as? String
                        ?? "UNKNOWN_AUTO_PROPOSED_FRONT_COMPILATION"
                    return finish(
                        code, phase: phase,
                        message: refusalText(opened).isEmpty
                            ? "自動提案の正面部品を候補固有3D工程へ結合できませんでした。"
                            : refusalText(opened),
                        rounds: 0, modelCalls: totalModelCalls)
                }
                visibleFrontInventoryAuditRequired = false
                visibleFrontInventoryAuditConfirmed = false
                visibleFrontInventoryAuthority = "AUTO_ACCEPTED_FOR_PREVIEW"
                targetCleanupAuthority = "AUTO_ACCEPTED_FOR_PREVIEW"
                targetCleanupConfirmed = true
                phase = openedState["phase"] as? String ?? "REGIONS_CONFIRMED"
                trace.append(.init(
                    round: 0, actor: "VERA_AUTO_AUDIT",
                    action: "ADOPT_VISIBLE_PARTS_AND_FOREGROUND_FOR_PREVIEW_ONLY",
                    verdict: "AUTO_ACCEPTED_FOR_PREVIEW"))
                pendingVisionHypotheses = compiled
                publishVisionPatternOperations(from: compiled)
                visionPipelineReviewItems = Self.uniqueRequirementItems(
                    visionPipelineReviewItems + [[
                    "code": "AUTO_PROPOSED_PIXEL_PARTS_BOUND",
                    "state": "AUTO_ACCEPTED_FOR_PREVIEW",
                    "authority": "AUTO_ACCEPTED_FOR_PREVIEW",
                    "why": "画像モデルの可視部品と前面マスクをプレビュー専用として採用し、候補固有の3D・型紙へ同一digestで結合しました。観測事実、背面、素材、実寸、縫製、製造承認には昇格していません。",
                    "candidate_count": compiled.count,
                    "fallback_used": false,
                    "fact_promotions": 0,
                    "manufacturing_ready": false,
                    "manufacturing_certified": false,
                ]])
                trace.append(.init(
                    round: 0, actor: "VERA_PARTS_TOPOLOGY_MCP",
                    action: "ATTACHED_TO_TO_TYPED_CONSTRUCTION",
                    verdict: "PROPOSED_\(compiled.count)"))
                trace.append(.init(
                    round: 0, actor: "VERA_PARTS_PIPELINE_MCP",
                    action: "PARTS_TO_BOUND_3D_AND_FLAT_PATTERN",
                    verdict: "PROPOSED_\(compiled.count)"))
                trace.append(.init(round: 0, actor: "VISION_LLM_PROPOSAL_GATE",
                                   action: "OPEN_PIXEL_GROUNDED_STRUCTURE_ALTERNATIVES",
                                   verdict: "PROPOSED_\(compiled.count)"))
            } else {
                let summary: [String: Any] = [
                    "code": outcome.code,
                    "state": "REVIEW",
                    "why": "画像の可視部品を候補固有の3D・型紙へ結合できなかったため、表示中の輪郭型紙は意味部品を保証しない暫定シルエットです。",
                    "fallback_used": true,
                    "fallback_scope": "front silhouette only",
                    "manufacturing_ready": false,
                    "manufacturing_certified": false,
                ]
                visionPipelineReviewItems = Self.uniqueRequirementItems(
                    visionPipelineReviewItems + [summary])
                trace.append(.init(round: 0, actor: "VISION_LLM_PROPOSAL_GATE",
                                   action: "OPEN_PIXEL_GROUNDED_STRUCTURE_ALTERNATIVES",
                                   verdict: outcome.code))
            }
        } else {
            let retrievalResult = await resolvedInitialFashionRetrieval(
                initialFashionRetrieval, imagePath: imagePath)
            activeInitialFashionRetrieval = retrievalResult
            publishInitialFashionRetrieval(retrievalResult)
            await buildGeometricPreview(outline: outline)
        }
        return await runUntilPause(userRequest: userRequest, proposer: proposer)
    }

    /// Start the fashion-specific retrieval proposal beside the ordinary VLM.
    /// Nothing is downloaded implicitly. A configured local HTTP endpoint,
    /// local-only model plus rights-reviewed JSON index, or precomputed result
    /// file must be supplied explicitly through the environment. Absence is a
    /// typed REVIEW value and never blocks the independent vision proposal.
    func proposeInitialFashionSimilarity(imagePath: String) async -> [String: Any] {
        let environment = ProcessInfo.processInfo.environment
        let endpoint = environment["PHOTOLOSET_FASHION_SIGLIP_ENDPOINT"]?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let modelPath = environment["PHOTOLOSET_FASHION_SIGLIP_MODEL_PATH"]?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let indexPath = environment["PHOTOLOSET_FASHION_RETRIEVAL_INDEX_PATH"]?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let resultPath = environment["PHOTOLOSET_FASHION_RETRIEVAL_RESULTS_PATH"]?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let indexID = environment["PHOTOLOSET_FASHION_RETRIEVAL_INDEX_ID"]?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        var config: [String: Any] = [
            "model_id": "Marqo/marqo-fashionSigLIP",
            "model_license": "Apache-2.0",
            "top_k": 8,
            "index_id": (indexID?.isEmpty == false) ? indexID! : "UNCONFIGURED",
        ]
        var request: [String: Any] = [
            "action": "run",
            "image_ref": imagePath,
            "query": ["image_ref": imagePath, "view": "FRONT_ONLY"],
        ]

        if let resultPath, !resultPath.isEmpty,
           let result = Self.readJSONObject(at: resultPath) {
            config["mode"] = "precomputed"
            request["precomputed_result"] = result
        } else if let endpoint, !endpoint.isEmpty {
            config["mode"] = "local_http"
            config["endpoint"] = endpoint
            config["allow_http"] = true
            config["timeout_seconds"] = 8
        } else if let modelPath, !modelPath.isEmpty {
            config["mode"] = "local_model"
            config["model_path"] = modelPath
            if let indexPath, !indexPath.isEmpty,
               let index = Self.readJSONObject(at: indexPath) {
                request["index"] = index
            }
        } else {
            config["mode"] = "precomputed"
        }
        request["config"] = config
        guard let jsonText = Self.jsonString(request) else {
            return ["verdict": "UNKNOWN_FASHION_RETRIEVAL_REQUEST_ENCODING"]
        }
        return await toolDoor(
            "marqo_fashion_siglip_runtime", ["json_text": jsonText])
    }

    private func resolvedInitialFashionRetrieval(
        _ supplied: [String: Any]?, imagePath: String
    ) async -> [String: Any] {
        if let supplied { return supplied }
        return await proposeInitialFashionSimilarity(imagePath: imagePath)
    }

    private func publishInitialFashionRetrieval(_ result: [String: Any]) {
        let verdict = result["verdict"] as? String
            ?? "UNKNOWN_FASHION_RETRIEVAL_BACKEND"
        let matches = result["matches"] as? [[String: Any]] ?? []
        let successful = !matches.isEmpty && !verdict.hasPrefix("UNKNOWN_")
        visionPipelineReviewItems = Self.uniqueRequirementItems(
            visionPipelineReviewItems + [[
                "code": successful
                    ? "PROPOSED_FASHION_SIGLIP_RETRIEVAL"
                    : verdict,
                "state": successful ? "PROPOSED_RETRIEVAL" : "REVIEW",
                "why": successful
                    ? "FashionSigLIPの近傍候補を取得しました。類似度は事実・正解・縫製権限ではなく、人間監査用の提案です。"
                    : (result["why"] as? String
                        ?? "FashionSigLIP検索基盤は未設定です。VLMの可視部品提案だけで監査まで継続します。"),
                "match_count": matches.count,
                "non_blocking": true,
                "rear_hidden_observed": false,
                "manufacturing_ready": false,
            ]])
        trace.append(.init(
            round: 0, actor: "MARQO_FASHION_SIGLIP_PROPOSER",
            action: "PARALLEL_FRONT_IMAGE_RETRIEVAL", verdict: verdict))
    }

    private func publishInitialImageAnalysisEnsemble(
        hypotheses: [[String: Any]], retrieval: [String: Any], imagePath: String
    ) async {
        guard let vision = Self.visionEnsemblePayload(from: hypotheses) else {
            return
        }
        var request: [String: Any] = [
            "schema": "garment.image-analysis-ensemble.request.v1",
            "analysis_id": Self.sha256(Data(imagePath.utf8)),
            "image": ["reference": imagePath, "front_only": true],
            "vision": ["result": vision],
            "provider_config": [
                "vision": ["provider_id": "selected-multimodal-model"],
                "retrieval": [
                    "provider_id": "marqo",
                    "model_id": "Marqo/marqo-fashionSigLIP",
                    "license_id": "Apache-2.0",
                ],
            ],
        ]
        if let matches = retrieval["matches"] as? [[String: Any]],
           !matches.isEmpty {
            request["retrieval"] = ["result": retrieval]
        }
        guard let jsonText = Self.jsonString(request) else { return }
        let ensemble = await toolDoor(
            "garment_image_analysis_ensemble", ["json_text": jsonText])
        let verdict = ensemble["verdict"] as? String
            ?? "UNKNOWN_GARMENT_ANALYSIS_ENSEMBLE"
        let agreements = ensemble["agreements"] as? [[String: Any]] ?? []
        let contested = ensemble["contested"] as? [[String: Any]] ?? []
        visionPipelineReviewItems = Self.uniqueRequirementItems(
            visionPipelineReviewItems + [[
                "code": verdict.hasPrefix("UNKNOWN_")
                    ? verdict : "PROPOSED_VLM_FASHION_SIGLIP_ENSEMBLE",
                "state": contested.isEmpty ? "PROPOSED" : "CONTESTED",
                "why": "VLMとFashionSigLIPを別々の提案源として照合しました。一致も観測事実には昇格せず、不一致は平均せず人間監査へ残します。",
                "agreement_count": agreements.count,
                "contested_count": contested.count,
                "fact_promotions": 0,
                "rear_hidden_observed": false,
                "manufacturing_ready": false,
            ]])
        trace.append(.init(
            round: 0, actor: "VERA_IMAGE_ANALYSIS_ENSEMBLE",
            action: "MERGE_WITHOUT_FACT_PROMOTION", verdict: verdict))
    }

    /// Compile the audited/proposed visible ledger into the geometry-first
    /// second-skin harness. Garment names are copied only as labels: layer,
    /// side, quantity, ownership and front outlines select geometry. The
    /// resulting rear alternatives preserve exactly the same front vertices.
    private func prepareGeometricAtelierPreview(
        from hypotheses: [[String: Any]], retrieval: [String: Any]?,
        humanConfirmed: Bool
    ) async {
        guard let separation = activeBodyImageSeparationEnvelope,
              let source = hypotheses.first,
              let structure = source["structure"] as? [String: Any],
              let nodes = structure["nodes"] as? [[String: Any]],
              !nodes.isEmpty else { return }

        func number(_ raw: Any?) -> Double? {
            if let value = raw as? Double { return value }
            if let value = raw as? Int { return Double(value) }
            if let value = raw as? NSNumber { return value.doubleValue }
            return nil
        }
        func pointRows(_ raw: Any?) -> [[Double]]? {
            guard let rows = raw as? [Any] else { return nil }
            let parsed = rows.compactMap { row -> [Double]? in
                guard let values = row as? [Any] else { return nil }
                let numbers = values.compactMap(number)
                return numbers.count == values.count ? numbers : nil
            }
            return parsed.count == rows.count ? parsed : nil
        }
        func indexRows(_ raw: Any?) -> [[Int]]? {
            guard let rows = raw as? [Any] else { return nil }
            let parsed = rows.compactMap { row -> [Int]? in
                guard let values = row as? [Any] else { return nil }
                let indices = values.compactMap { value -> Int? in
                    if let value = value as? Int { return value }
                    if let value = value as? NSNumber { return value.intValue }
                    return nil
                }
                return indices.count == values.count ? indices : nil
            }
            return parsed.count == rows.count ? parsed : nil
        }

        let proposedGraphParts: [[String: Any]] = nodes.enumerated().compactMap {
            index, node in
            guard let nodeID = node["node_id"] as? String else { return nil }
            let attributes = node["attributes"] as? [String: Any] ?? [:]
            var part: [String: Any] = [
                "part_id": nodeID,
                "kind": node["kind"] as? String ?? "UNKNOWN_VISIBLE_SURFACE",
                "layer": node["layer"] as? Int ?? 0,
                "garment_unit": attributes["garment_unit"] as? String
                    ?? attributes["instance_id"] as? String
                    ?? "visible-unit-\(index)",
                "side": attributes["side"] as? String ?? "CENTER",
                "state": "PROPOSED",
            ]
            if let maskID = attributes["mask_id"] as? String {
                part["mask_id"] = maskID
            }
            if let outline = pointRows(
                node["outline"] ?? attributes["outline"]
                    ?? attributes["outline_px"]) {
                part["outline"] = outline
                part["coordinate_space"] = attributes["coordinate_space"]
                    as? String ?? "PIXELS"
            }
            if let quantity = attributes["quantity"] as? Int,
               (1...4).contains(quantity) {
                part["component_count"] = quantity
            }
            return part
        }
        guard proposedGraphParts.count == nodes.count else { return }

        let graphParts: [[String: Any]]
        let graphRelations: [[String: Any]]
        if humanConfirmed, let evidence = activeHumanConfirmedFrontEvidence {
            graphParts = evidence.regions.enumerated().compactMap { index, row in
                guard let regionID = row["region_id"] as? String,
                      let outline = pointRows(row["outline"]),
                      outline.count >= 3 else { return nil }
                let partID = row["part_id"] as? String
                    ?? "human-part:\(regionID)"
                return [
                    "part_id": partID,
                    "kind": "HUMAN_OBSERVED_VISIBLE_REGION",
                    "layer": row["layer"] as? Int ?? 0,
                    "garment_unit": "human-visible-unit:\(regionID)",
                    "side": "CENTER",
                    "state": "OBSERVED",
                    "mask_id": regionID,
                    "outline": outline,
                    "coordinate_space": "PIXELS",
                    "source_region_id": regionID,
                    "source_region_state": "OBSERVED",
                    "layer_source": row["layer_source"] as? String
                        ?? "UNKNOWN_UNORDERED_VISIBLE_REGION",
                    "human_region_index": index,
                ]
            }
            guard graphParts.count == evidence.regions.count else { return }
            let partIDByRegionID = Dictionary(uniqueKeysWithValues:
                graphParts.compactMap { part -> (String, String)? in
                    guard let regionID = part["source_region_id"] as? String,
                          let partID = part["part_id"] as? String else {
                        return nil
                    }
                    return (regionID, partID)
                })
            graphRelations = evidence.layerRelations.compactMap { row in
                guard let relationID = row["relation_id"] as? String,
                      let behindRegionID = row["behind_region_id"] as? String,
                      let frontRegionID = row["front_region_id"] as? String,
                      let behindPartID = partIDByRegionID[behindRegionID],
                      let frontPartID = partIDByRegionID[frontRegionID] else {
                    return nil
                }
                return [
                    "relation_id": relationID,
                    "kind": "LAYER",
                    "parent_id": behindPartID,
                    "child_id": frontPartID,
                    "attachment_port": "human-visible-order:\(behindRegionID)->\(frontRegionID)",
                    "attachment_side": "CENTER",
                    // The computational relation remains a proposal.  Its
                    // source relation is the separately preserved human fact.
                    "state": "PROPOSED",
                    "source_state": "OBSERVED",
                    "source": "HUMAN_EXPLICIT_FRONT_ORDER",
                    "behind_region_id": behindRegionID,
                    "front_region_id": frontRegionID,
                ]
            }
            guard graphRelations.count == evidence.layerRelations.count else {
                return
            }
        } else {
            graphParts = proposedGraphParts
            graphRelations = structure["relations"] as? [[String: Any]] ?? []
        }
        let graph: [String: Any] = [
            "graph_id": structure["structure_digest"] as? String
                ?? source["candidate_id"] as? String
                ?? "visible-front-graph",
            "parts": graphParts,
            "relations": graphRelations,
            "authority": humanConfirmed
                ? "HUMAN_REVIEWED_VISIBLE_FRONT" : "AI_GENERATED_PROPOSAL",
        ]
        let multimodal: [[String: Any]] = hypotheses.enumerated().map {
            index, row in
            let candidateID = row["candidate_id"] as? String
                ?? "multimodal-\(index)"
            let candidateStructure = row["structure"] as? [String: Any] ?? [:]
            return [
                "proposal_id": candidateID,
                "model_id": "selected-local-or-api-multimodal-model",
                "rear_structure": [
                    "back_design": row["back_design"] as? String
                        ?? "unobserved rear alternative",
                    "structure": candidateStructure,
                ],
                "parts": candidateStructure["nodes"] as? [[String: Any]] ?? [],
                "seams": candidateStructure["relations"] as? [[String: Any]] ?? [],
            ]
        }
        var request: [String: Any] = [
            "schema": "garment.geometric-atelier-workflow.request.v1",
            "separation": separation,
            "visible_part_graph": graph,
            "audit_mode": humanConfirmed ? "HUMAN_AUDIT" : "AUTO_PROPOSED",
            "requested_measurements": activeBodyRequestedMeasurements,
            "interpolation": [
                "method": "LINEAR_BOUNDED",
                "allowed_dimensions": activeBodyRequestedMeasurements.keys.sorted(),
            ],
            "multimodal_proposals": ["proposals": multimodal],
            "resolution": ["angular_segments": 16, "height_steps": 8],
            "repair_config": ["max_rounds": 3, "repair_gain": 1.0],
        ]
        if let retrieval, !(retrieval["matches"] as? [[String: Any]] ?? []).isEmpty {
            request["fashion_siglip_hits"] = retrieval
        }
        if humanConfirmed, let editDigest = targetSculptDigest {
            request["front_audit"] = [
                "decision": "ACCEPT",
                "reviewer": Self.localHumanReviewer(),
            ]
            request["human_edit_digest"] = editDigest
        }
        guard let requestText = Self.jsonString(request) else { return }
        let result = await toolDoor(
            "garment_geometric_atelier_workflow", ["json_text": requestText])
        let verdict = result["verdict"] as? String
            ?? "UNKNOWN_GEOMETRIC_ATELIER_WORKFLOW"
        trace.append(.init(
            round: 0, actor: "VERA_GEOMETRIC_ATELIER_MCP",
            action: "FRONT_TO_SECOND_SKIN_REAR_CANDIDATES",
            verdict: verdict))
        guard verdict == "PROPOSED" else {
            visionPipelineReviewItems = Self.uniqueRequirementItems(
                visionPipelineReviewItems + [[
                    "code": verdict, "state": "REVIEW",
                    "why": result["why"] as? String
                        ?? "第二皮膚・背面候補の統合フローが型付きで停止しました。",
                    "manufacturing_ready": false,
                ]])
            return
        }
        activeGeometricAtelierWorkflow = result
        activeInitialFashionRetrieval = retrieval
        if let fit = result["body_avatar_fit"] as? [String: Any] {
            activeImageRelativeBodyFit = fit
            imageRelativeBodyFitDigest = fit["contract_digest"] as? String
            if let avatar = fit["selected_avatar"] as? [String: Any],
               let avatarID = avatar["avatar_id"] as? String,
               let geometryDigest = avatar["geometry_digest"] as? String,
               let dimensions = avatar["dimensions_cm"] as? [String: Any],
               let height = number(dimensions["height"]),
               let chest = number(dimensions["chest_bust"]),
               let waist = number(dimensions["waist"]),
               let hip = number(dimensions["hip"]) {
                let profile = BaseAvatarProfile(
                    id: avatarID,
                    title: String(format: "画像位置合わせ %.0f · %.0f / %.0f / %.0f cm",
                                  height, chest, waist, hip),
                    heightCM: height, chestCM: chest, waistCM: waist, hipCM: hip,
                    geometryDigest: geometryDigest,
                    authority: "PROPOSED_IMAGE_RELATIVE_PREVIEW")
                baseAvatarProfiles = [profile] + baseAvatarProfiles.filter {
                    $0.id != profile.id
                }
                selectedBaseAvatarID = profile.id
            }
        }

        let repair = result["candidate_3d_repair"] as? [String: Any]
        let repairedRows = repair?["candidates"] as? [[String: Any]] ?? []
        let inputRows = result["candidate_inputs"] as? [[String: Any]] ?? []
        let frontInvariant = (result["candidate_front_invariant"]
            as? [String: Any])?["all_candidates_preserve_identical_front"]
            as? Bool ?? false
        let hypothesisIDs = hypotheses.compactMap { $0["candidate_id"] as? String }
        var artifactByID: [String: PreviewArtifact] = [:]
        var orderedArtifacts: [PreviewArtifact] = []
        // Rear alternatives are owned by the geometry ensemble, not by the
        // number of VLM front ledgers. A single accepted front hypothesis can
        // still yield several genuinely different rear candidates; iterating
        // the front hypotheses here used to drop candidate 2+ and let those
        // approvals fall back to the old generic semantic preview.
        let geometryCandidateCount = max(repairedRows.count, inputRows.count)
        for index in 0..<geometryCandidateCount {
            let repaired = index < repairedRows.count ? repairedRows[index] : [:]
            let input = index < inputRows.count ? inputRows[index] : [:]
            let geometry = repaired["candidate_geometry"] as? [String: Any]
                ?? input["mesh"] as? [String: Any]
                ?? [:]
            guard let points = pointRows(geometry["vertices"]),
                  let faces = indexRows(geometry["faces"]),
                  !points.isEmpty, !faces.isEmpty else { continue }
            let sourceCandidateID = repaired["candidate_id"] as? String
                ?? input["candidate_id"] as? String ?? "rear-\(index + 1)"
            let artifact = PreviewArtifact(
                state: "PROPOSED", attempt: 1,
                method: "image-relative body → typed second skin → candidate-specific rear \(index + 1)",
                points: points, faces: faces, edges: Self.meshEdges(faces),
                pieces: [],
                assumptions: [
                    "正面頂点は全候補で同一です: \(frontInvariant ? "YES" : "REVIEW")",
                    "背面候補 \(sourceCandidateID) はAI・検索・幾何によるPROPOSEDで、写真観測ではありません。",
                    "部品境界が単一前景マスクを共有する場合はプレビュー足場であり、型紙境界ではありません。",
                    "素材、縫い目、縫い代、強度、快適性は未確定です。",
                ],
                repairSummary: repaired["verdict"] as? String
                    ?? "PROPOSED_CANDIDATE_PREVIEW_ONLY",
                preservesSourceFront: frontInvariant)
            artifactByID[sourceCandidateID] = artifact
            if index < hypothesisIDs.count {
                artifactByID[hypothesisIDs[index]] = artifact
            }
            orderedArtifacts.append(artifact)
        }
        guard !orderedArtifacts.isEmpty else { return }
        geometricRearCandidateArtifacts = artifactByID
        geometricRearCandidateArtifactsInOrder = orderedArtifacts
        previewArtifact = orderedArtifacts[0]
        previewAttempts = max(1, previewAttempts)
        if let skin = result["second_skin"] as? [String: Any],
           var pattern = skin["pattern_interface"] as? [String: Any] {
            pattern["schema"] = "garment.second-skin-pattern-handoff-preview.v1"
            pattern["state"] = "PROPOSED"
            pattern["manufacturing_ready"] = false
            candidateManufacturingPreview = pattern
        }
        let shared = (result["visible_part_graph"] as? [String: Any])?["parts"]
            as? [[String: Any]] ?? []
        let sharedCount = shared.filter {
            $0["outline_binding"] as? String
                == "SHARED_AGGREGATE_FRONT_MASK_PROPOSAL"
        }.count
        if sharedCount > 0 {
            visionPipelineReviewItems = Self.uniqueRequirementItems(
                visionPipelineReviewItems + [[
                    "code": "REVIEW_SHARED_FRONT_MASK_PART_BOUNDARIES",
                    "state": "REVIEW", "part_count": sharedCount,
                    "why": "AIの部品台帳は単一の監査前景を共有して3D化されています。見た目比較には使えますが、各部品の境界・縫い目・型紙境界はまだ観測されていません。",
                    "manufacturing_ready": false,
                ]])
        }
    }

    private static func visionEnsemblePayload(
        from hypotheses: [[String: Any]]
    ) -> [String: Any]? {
        guard let rows = hypotheses.first?["visible_front_inventory"]
                as? [[String: Any]], !rows.isEmpty else { return nil }
        let groups = Dictionary(grouping: rows) {
            ($0["garment_unit"] as? String) ?? "candidate"
        }
        let instances: [[String: Any]] = groups.keys.sorted().map { unit in
            let parts = groups[unit] ?? []
            let layer = parts.compactMap { ($0["layer"] as? NSNumber)?.intValue }
                .min() ?? 0
            let labels = parts.compactMap {
                ($0["semantic_role"] as? String)
                    ?? ($0["source_kind"] as? String)?.lowercased()
            }
            let partRows: [[String: Any]] = parts.compactMap { row in
                guard let partID = row["inventory_part_id"] as? String else {
                    return nil
                }
                return [
                    "part_id": partID,
                    "name": (row["semantic_role"] as? String)
                        ?? (row["source_kind"] as? String)?.lowercased()
                        ?? "visible part",
                ]
            }
            return [
                "instance_id": unit,
                "layer": layer,
                "garment_name": labels.joined(separator: " + "),
                "parts": partRows,
                "visible_observations": parts.compactMap {
                    $0["visible_basis"] as? String
                },
                "rear_structure": ["state": "UNKNOWN_FRONT_ONLY"],
            ]
        }
        return [
            "garment_instances": instances,
            "provenance": ["authority": "PROPOSED_VISION_UNCONFIRMED"],
        ]
    }

    private static func readJSONObject(at path: String) -> Any? {
        guard let data = try? Data(contentsOf: URL(fileURLWithPath: path)) else {
            return nil
        }
        return try? JSONSerialization.jsonObject(with: data)
    }

    /// Parse, authority-scrub and deterministically compile one image-model
    /// response. A non-nil return means every published candidate has bound
    /// candidate-specific artifacts; callers must not infer success from a
    /// generic silhouette preview.
    private func compileVisionProposal(
        _ raw: String?, deferForHumanAudit: Bool = false
    ) async -> (rows: [[String: Any]]?, code: String) {
        guard let raw,
              !raw.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            return (nil, "UNKNOWN_VISION_RESPONSE_EMPTY")
        }
        guard let proposal = Self.parseVisionProposal(raw),
              let rows = proposal["hypotheses"] as? [[String: Any]],
              rows.count >= 2 else {
            return (nil, "UNKNOWN_VISION_VISIBLE_PARTS_SCHEMA")
        }
        publishVisibleFrontInventory(from: rows)
        let requestedRows = applyDesignRequirements(to: rows)
        publishVisionPatternOperations(from: requestedRows)
        if deferForHumanAudit {
            return (requestedRows, "HUMAN_GARMENT_AUDIT_REQUIRED")
        }
        guard let compiled = await runVisionPartsPipeline(requestedRows),
              compiled.count >= 2 else {
            return (nil, "UNKNOWN_VISION_PARTS_TO_ARTIFACT_PIPELINE")
        }
        return (compiled, "PROPOSED_\(compiled.count)")
    }

    /// Accepts only the visible-front inventory.  It does not approve the
    /// back, hidden construction, material identity, dimensions or sewing
    /// method.  Compilation resumes only when the independently editable
    /// foreground target has also been adopted by the human reviewer.
    func confirmVisibleFrontInventoryAudit(
        confirmedOutline: [String: Any], imagePath: String
    ) async -> Report? {
        guard !busy else { return lastReport }
        guard activeAuditMode == .humanAudit,
              visibleFrontInventoryAuditRequired,
              !pendingHumanAuditedVisionRows.isEmpty,
              !visibleFrontInventory.isEmpty,
              let analysisDigest = activeVisibleAnalysisDigest else {
            return lastReport
        }
        guard let humanEvidence =
                HumanConfirmedFrontEvidenceGate.humanConfirmedFrontEvidence(
                    confirmedOutline,
                    activeImagePath: activeTargetImagePath,
                    submittedImagePath: imagePath) else {
            return finish(
                "UNKNOWN_HUMAN_CONFIRMED_FRONT_REQUIRED", phase: phase,
                message: "同じ画像上で人が衣服に3〜5点を置き、正面の衣服領域を確認してください。AIの自動マスクだけでは監査を完了できません。",
                rounds: 0, modelCalls: totalModelCalls,
                context: [
                    "missing_fields": [
                        "matching_image_path", "observed_clothing_regions",
                        "three_to_five_human_seeds",
                    ],
                    "rear_state": "UNKNOWN_UNOBSERVED",
                    "material_state": "UNKNOWN_UNOBSERVED",
                ])
        }

        // Keep the exact gate output for the later parts→second-skin call.
        // This is cleared at every new image/job and has no AI write path.
        activeHumanConfirmedFrontEvidence = humanEvidence

        busy = true
        defer { busy = false }

        // Rebuild every image-bound geometric input from the exact seeded
        // clothing boundary.  This replaces the earlier PROPOSED automatic
        // mask, but does not observe depth, the rear, material or construction.
        targetCleanupConfirmed = false
        persistedForegroundCleanupDigest = nil
        targetRemovedRegionIDs = []
        targetSculptRemovedFaces = []
        targetSculptUndoStack = []
        targetSculptRevision &+= 1
        await prepareBodyProxyCandidates(
            outline: confirmedOutline, imagePath: imagePath,
            requirements: activeDesignRequirements, evidenceState: "OBSERVED")
        await prepareTargetReconstruction(
            outline: confirmedOutline, imagePath: imagePath)
        guard targetReconstruction?.sculptSurface != nil,
              targetSculptDigest != nil else {
            return finish(
                "UNKNOWN_HUMAN_FRONT_TARGET_RECONSTRUCTION", phase: phase,
                message: "人が確認した正面輪郭から比較用ターゲットを構成できませんでした。背面を捏造せず停止します。",
                rounds: 0, modelCalls: totalModelCalls,
                context: [
                    "confirmed_region_count": humanEvidence.regions.count,
                    "human_seed_count": humanEvidence.seeds.count,
                    "rear_state": "UNKNOWN_UNOBSERVED",
                ])
        }
        let decisions: [[String: Any]] = visibleFrontInventory.map { row in
            ["assertion_id": row.id, "action": "ACCEPT"]
        }
        let persisted = await advance(event: [
            "type": "SUBMIT_HUMAN_VISIBLE_AUDIT",
            "reviewer": Self.localHumanReviewer(),
            "analysis_digest": analysisDigest,
            "decisions": decisions,
            "confirmed_outline": confirmedOutline,
            "confirmed_regions": humanEvidence.regions,
            "human_seed_provenance": humanEvidence.seeds,
            "confirmed_layer_relations": humanEvidence.layerRelations,
        ])
        guard let next = state(from: persisted),
              next["phase"] as? String == "FOREGROUND_CLEANUP_REQUIRED" else {
            let code = persisted["verdict"] as? String
                ?? "UNKNOWN_HUMAN_GARMENT_AUDIT_PERSISTENCE"
            return finish(
                code, phase: phase,
                message: refusalText(persisted).isEmpty
                    ? "正面部品の監査結果をVera状態機械へ記録できませんでした。"
                    : refusalText(persisted),
                rounds: 0, modelCalls: totalModelCalls,
                context: persisted)
        }
        visibleFrontInventoryAuditRequired = false
        visibleFrontInventoryAuditConfirmed = true
        visibleFrontInventoryAuthority = "HUMAN_REVIEWED_VISIBLE_SOURCE"
        trace.append(.init(
            round: 0, actor: "HUMAN_VISIBLE_GARMENT_AUDIT",
            action: "ACCEPT_SEEDED_VISIBLE_FRONT_INVENTORY_AND_TARGET",
            verdict: "OBSERVED_BY_HUMAN_REVIEW"))

        // The seeded picker exported clothing regions only, so the same human
        // action is an explicit adoption of this initial front comparison
        // target.  It is not an observation of the generated depth or rear.
        targetCleanupAuthority = "HUMAN_CONFIRMED_REGION_SELECTION"
        targetCleanupConfirmed = true
        trace.append(.init(
            round: Int(targetSculptRevision), actor: "HUMAN_REGION_PICKER",
            action: "ADOPT_SEEDED_FRONT_COMPARISON_TARGET",
            verdict: "HUMAN_EDIT_ACCEPTED_FOR_COMPARISON"))
        scheduleTargetSameCameraComparison()
        await persistForegroundCleanupAndResume()
        return lastReport
    }

    /// Bind the adopted CAD target to the same persisted audit.  A local UI
    /// boolean is not authority: only this revision/digest-bound event opens
    /// the parts→3D→pattern continuation.
    private func persistForegroundCleanupAndResume() async {
        guard visibleFrontInventoryAuditConfirmed,
              targetCleanupConfirmed,
              let targetDigest = targetSculptDigest else { return }
        if persistedForegroundCleanupDigest == targetDigest {
            await resumeAfterInitialHumanReviewIfReady()
            return
        }
        let revisingExistingTarget = hasPersistedForegroundCleanup
        let undoDigests: [String] = targetSculptUndoStack.enumerated().compactMap {
            index, removedFaces in
            guard let text = Self.jsonString([
                "ordinal": index,
                "removed_face_indices": removedFaces.sorted(),
            ]) else { return nil }
            return Self.sha256(Data(text.utf8))
        }
        let persisted = await advance(event: [
            "type": "SUBMIT_FOREGROUND_CLEANUP",
            "reviewer": Self.localHumanReviewer(),
            "target_digest": targetDigest,
            "target_revision": Int(targetSculptRevision),
            "removed_region_ids": targetRemovedRegionIDs.sorted(),
            "removed_face_indices": targetSculptRemovedFaces.sorted(),
            "undo_parent_digests": undoDigests,
        ])
        guard let next = state(from: persisted),
              next["phase"] as? String == "FRONT_FACTS_RECORDED" else {
            let code = persisted["verdict"] as? String
                ?? "UNKNOWN_FOREGROUND_CLEANUP_PERSISTENCE"
            _ = finish(
                code, phase: phase,
                message: refusalText(persisted).isEmpty
                    ? "前面ターゲット編集をVera状態機械へ記録できませんでした。"
                    : refusalText(persisted),
                rounds: 0, modelCalls: totalModelCalls,
                context: persisted)
            return
        }
        persistedForegroundCleanupDigest = targetDigest
        hasPersistedForegroundCleanup = true
        phase = next["phase"] as? String ?? "FRONT_FACTS_RECORDED"
        if revisingExistingTarget {
            shapeCandidates = []
            materialCandidates = []
            shapeCandidatePayloads = [:]
            materialCandidatePayloads = [:]
            visionPipelineArtifacts = [:]
            clearCandidatePreviewArtifacts()
            trace.append(.init(
                round: Int(targetSculptRevision), actor: "VERA_CAD_ITERATION",
                action: "INVALIDATE_PATTERN_SIMULATION_AND_REDRESS",
                verdict: "FRONT_FACTS_RECORDED"))
        }
        if liveExternalEffectsEnabled,
           recordedVeraFrontTargetDigests.insert(targetDigest).inserted {
            let inventory = visibleFrontInventory.map { item in
                "L\(item.layer) \(item.garmentUnit) \(item.label) [\(item.normalizedKind)]"
            }
            let stored = await VeraMemoryBridge
                .recordHumanReviewedGarmentFrontFacts(
                    reviewer: Self.localHumanReviewer(),
                    analysisDigest: activeVisibleAnalysisDigest ?? "unknown",
                    targetDigest: targetDigest,
                    inventory: inventory)
            if !stored {
                recordedVeraFrontTargetDigests.remove(targetDigest)
            }
            trace.append(.init(
                round: Int(targetSculptRevision),
                actor: "VERA_STEREO_CROSS_MEMORY",
                action: "RECORD_HUMAN_REVIEWED_FRONT_FACTS",
                verdict: stored ? "ANSWER" : "UNKNOWN_VERA_MEMORY_UNAVAILABLE"))
        }
        await resumeAfterInitialHumanReviewIfReady()
    }

    private func resumeAfterInitialHumanReviewIfReady() async {
        guard visibleFrontInventoryAuditConfirmed,
              targetCleanupConfirmed,
              persistedForegroundCleanupDigest == targetSculptDigest,
              !pendingHumanAuditedVisionRows.isEmpty,
              !initialHumanReviewResumeInFlight else { return }
        initialHumanReviewResumeInFlight = true
        defer { initialHumanReviewResumeInFlight = false }
        phase = "FRONT_FACTS_RECORDED"
        let reviewedRows = pendingHumanAuditedVisionRows
        guard let compiled = await runVisionPartsPipeline(reviewedRows),
              compiled.count >= 2 else {
            let code = "UNKNOWN_REVIEWED_VISION_PARTS_TO_ARTIFACT_PIPELINE"
            visionPipelineReviewItems = Self.uniqueRequirementItems(
                visionPipelineReviewItems + [[
                    "code": code, "state": "REVIEW",
                    "why": "人が確認した正面部品を候補固有3D・型紙へ結合できませんでした。背面や縫い目を捏造せず停止します。",
                    "manufacturing_ready": false,
                ]])
            _ = finish(
                code, phase: phase,
                message: "確認済みの正面部品を3D・型紙へ結合できないため停止しました。",
                rounds: 0, modelCalls: totalModelCalls,
                context: [
                    "why": "人が確認した正面部品を候補固有3D・型紙へ結合できませんでした。",
                    "missing_fields": ["candidate_bound_3d", "flat_pattern"],
                ])
            return
        }
        guard let compiledText = Self.jsonString(compiled) else {
            _ = finish(
                "UNKNOWN_REVIEWED_FRONT_COMPILATION_ENCODING", phase: phase,
                message: "監査済み正面候補のdigestを生成できませんでした。",
                rounds: 0, modelCalls: totalModelCalls)
            return
        }
        let opened = await advance(event: [
            "type": "OPEN_RETRIEVAL_AFTER_FRONT_REVIEW",
            "compiled_front_digest": Self.sha256(Data(compiledText.utf8)),
            "candidate_count": compiled.count,
        ])
        guard let openedState = state(from: opened),
              openedState["phase"] as? String == "REGIONS_CONFIRMED" else {
            let code = opened["verdict"] as? String
                ?? "UNKNOWN_REVIEWED_FRONT_FACTORY_TRANSITION"
            _ = finish(
                code, phase: phase,
                message: refusalText(opened).isEmpty
                    ? "監査済み正面部品から検索・背面候補工程を開けませんでした。"
                    : refusalText(opened),
                rounds: 0, modelCalls: totalModelCalls,
                context: opened)
            return
        }
        // Retain the audited proposal rows as immutable source lineage. A
        // later human CAD revision reuses exactly these reviewed front parts,
        // invalidates every downstream artifact in the persisted factory, and
        // recompiles/redresses instead of silently keeping the old pattern.
        pendingVisionHypotheses = compiled
        publishVisionPatternOperations(from: compiled)
        await prepareGeometricAtelierPreview(
            from: compiled, retrieval: activeInitialFashionRetrieval,
            humanConfirmed: true)
        visionPipelineReviewItems = Self.uniqueRequirementItems(
            visionPipelineReviewItems + [[
                "code": "HUMAN_REVIEWED_FRONT_PARTS_BOUND",
                "state": "OBSERVED_BY_HUMAN_REVIEW",
                "why": "人が確認したのは正面の衣服数・層・可視部品だけです。候補3D、背面、奥行き、素材、寸法、縫製はPROPOSEDです。",
                "rear_hidden_observed": false,
                "material_identity_observed": false,
                "manufacturing_ready": false,
            ]])
        trace.append(.init(
            round: 0, actor: "VERA_PARTS_PIPELINE_MCP",
            action: "HUMAN_REVIEWED_FRONT_TO_BOUND_3D_AND_PATTERN",
            verdict: "PROPOSED_\(compiled.count)"))
        phase = openedState["phase"] as? String ?? "REGIONS_CONFIRMED"
        lastReport = await runUntilPause(
            userRequest: pendingHumanAuditUserRequest,
            proposer: pendingHumanAuditProposer)
        await fulfillPendingBack3DRequestIfPossible()
    }

    /// Continue the current image job toward a proposed rear-view comparison.
    /// The request is intentionally durable across the visible-parts audit and
    /// foreground cleanup. The caller gets an exact next action instead of the
    /// old behaviour which silently re-ran GENERATE_FROM_IMAGE and returned to
    /// the beginning of the same gate.
    func requestBack3DPreview(
        userRequest: String, proposer: Proposer?
    ) async -> Report {
        pendingBack3DRequest = true
        if !userRequest.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            pendingHumanAuditUserRequest = userRequest
        }
        if let proposer { pendingHumanAuditProposer = proposer }

        if visibleFrontInventoryAuditRequired {
            return finish(
                "HUMAN_GARMENT_AUDIT_REQUIRED", phase: phase,
                message: "背面3D要求を保持しました。まず正面の衣服数・重なり・可視部品を確認してください。確認後も要求は失われず、背面だけをPROPOSED候補として生成します。",
                rounds: 0, modelCalls: totalModelCalls)
        }
        if visibleFrontInventoryAuditConfirmed, !targetCleanupConfirmed {
            return finish(
                "FOREGROUND_CLEANUP_REQUIRED", phase: phase,
                message: "背面3D要求を保持しました。正面画像から人体・髪・背景・別衣服を削り、比較目標として採用してください。採用後に承認済み正面を固定して背面候補を表示します。",
                rounds: 0, modelCalls: totalModelCalls)
        }
        if !shapeCandidates.isEmpty {
            await fulfillPendingBack3DRequestIfPossible()
            return lastReport ?? Report(
                verdict: "PROPOSED_BACK_3D_READY", phase: phase,
                message: "背面候補3Dを表示しました。背面は未観測のAI/幾何提案です。",
                iterations: 0, modelCalls: totalModelCalls)
        }
        let report = await runUntilPause(
            userRequest: pendingHumanAuditUserRequest,
            proposer: pendingHumanAuditProposer)
        await fulfillPendingBack3DRequestIfPossible()
        return lastReport ?? report
    }

    private func fulfillPendingBack3DRequestIfPossible() async {
        guard pendingBack3DRequest, let candidate = shapeCandidates.first else {
            return
        }
        guard await previewShape(candidate) else {
            _ = finish(
                "REVIEW_BACK_3D_PREVIEW_UNAVAILABLE", phase: phase,
                message: "背面候補は得られましたが、承認済み正面に結合した3Dを生成できませんでした。汎用台形への置換は行っていません。",
                rounds: max(1, previewAttempts), modelCalls: totalModelCalls,
                context: [
                    "why": "承認済み正面に候補固有の背面サーフェスを結合できませんでした。",
                    "missing_fields": ["candidate_bound_rear_surface"],
                ])
            return
        }
        pendingBack3DRequest = false
        pendingResolutionRequest = nil
        activeLLMProposalConsent = nil
        selectedResolutionAction = nil
        let frontAuthority = targetCleanupAuthority
        lastReport = Report(
            verdict: "PROPOSED_BACK_3D_READY", phase: phase,
            message: "正面ターゲット（\(frontAuthority)）を固定し、未観測の背面だけを候補として補った3Dを表示しました。背面・奥行きはAI/幾何によるPROPOSEDで、観測事実ではありません。",
            iterations: max(1, previewAttempts), modelCalls: totalModelCalls)
    }

    /// Preserve every validated user request in the beginner UI even when it
    /// was applied successfully and therefore produced no REVIEW error. These
    /// rows describe requested design intent, never image/body observations.
    private static func requestedNotMeasuredItems(
        from requirements: [[String: Any]]
    ) -> [[String: Any]] {
        requirements.map { source in
            var row = source
            row["code"] = "REQUESTED_NOT_MEASURED"
            row["state"] = "REQUESTED_NOT_MEASURED"
            row["authority"] = "REQUESTED_NOT_MEASURED"
            row["not_measured_from_image"] = true
            row["preview_only"] = true
            row["observed"] = false
            row["manufacturing_ready"] = false
            row["manufacturing_certified"] = false
            return row
        }
    }

    private static func uniqueRequirementItems(
        _ items: [[String: Any]]
    ) -> [[String: Any]] {
        var seen = Set<String>()
        return items.filter { row in
            let key = Self.jsonString(row) ?? String(describing: row)
            return seen.insert(key).inserted
        }
    }

    private static func localHumanReviewer() -> String {
        let fullName = NSFullUserName()
            .trimmingCharacters(in: .whitespacesAndNewlines)
        if !fullName.isEmpty { return fullName }
        let account = NSUserName()
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return account.isEmpty ? "Local human reviewer" : account
    }

    /// Apply only the already validated deterministic requirement profile.
    /// The LLM never receives a geometry mutation door, and a failed address
    /// match leaves the image candidate unchanged with an explicit REVIEW.
    private func applyDesignRequirements(
        to hypotheses: [[String: Any]]
    ) -> [[String: Any]] {
        guard let profile = activeDesignRequirementProfile else {
            return hypotheses
        }
        var accumulatedReviews = designRequirementReviewItems
        let appliedRows: [[String: Any]] = hypotheses.map { source in
            do {
                let applied = try GarmentDesignRequirementProfileBridge.apply(
                    profile, to: source)
                accumulatedReviews.append(contentsOf: applied.applicationReviewItems)
                var candidate = applied.candidate
                var assumptions = (candidate["assumptions"] as? [Any] ?? [])
                    .compactMap { $0 as? String }
                assumptions.append(
                    "ユーザー指定寸法はREQUESTEDの候補プレビューへ適用されています。画像からの実測値ではありません。")
                for review in applied.applicationReviewItems {
                    let code = review["code"] as? String ?? "REVIEW_REQUIREMENT_ADDRESS"
                    assumptions.append("\(code): 対象部位が曖昧なため値を変更していません。")
                }
                candidate["assumptions"] = assumptions
                candidate["requested_dimension_fields_applied"] = applied.appliedFieldCount
                return candidate
            } catch let failure as GarmentDesignRequirementProfileBridge.Failure {
                accumulatedReviews.append([
                    "code": failure.code,
                    "state": "REVIEW",
                    "why": failure.detail,
                    "requested_values_applied": false,
                ])
                return source
            } catch {
                accumulatedReviews.append([
                    "code": "UNKNOWN_REQUIREMENT_PROFILE_APPLICATION",
                    "state": "REVIEW",
                    "why": error.localizedDescription,
                    "requested_values_applied": false,
                ])
                return source
            }
        }
        var seen = Set<String>()
        designRequirementReviewItems = accumulatedReviews.filter { review in
            let key = Self.jsonString(review) ?? String(describing: review)
            return seen.insert(key).inserted
        }
        return appliedRows
    }

    /// Continue until a deterministic pause, convergence, refusal, or hard
    /// budget.  A model call never counts as an accepted transition by itself;
    /// its parsed proposal must pass the Python factory gate on the next line.
    func runUntilPause(userRequest: String, proposer: Proposer? = nil) async -> Report {
        busy = true
        defer { busy = false }
        var modelCalls = totalModelCalls
        for round in 1...hardRoundLimit {
            let inspected = await door("inspect", [:])
            guard let current = state(from: inspected) else {
                return finish(inspected["verdict"] as? String ?? "UNKNOWN_FACTORY_STATE",
                              phase: phase, message: refusalText(inspected),
                              rounds: round, modelCalls: modelCalls,
                              context: inspected)
            }
            phase = current["phase"] as? String ?? "EMPTY"
            publishCandidates(from: current)
            let action = Self.decide(state: current)
            lastReport = Report(verdict: action.code, phase: phase,
                                message: action.message, iterations: round,
                                modelCalls: modelCalls)
            trace.append(.init(round: round, actor: "VERA_CROSS_HARNESS",
                               action: action.code, verdict: phase))
            switch action.kind {
            case .waitForRetrieval:
                let retrieval = await runAutomaticRetrieval(
                    state: current, userRequest: userRequest)
                let verdict = retrieval["verdict"] as? String ?? "UNKNOWN_RETRIEVAL_BACKEND"
                trace.append(.init(round: round, actor: "VERA_HYBRID_RETRIEVAL",
                                   action: "REGION_GEOMETRY_CORPUS", verdict: verdict))
                if verdict.hasPrefix("UNKNOWN_") {
                    return finish(verdict, phase: phase, message: refusalText(retrieval),
                                  rounds: round, modelCalls: modelCalls,
                                  context: retrieval)
                }
                continue
            case .waitForSimulationInput:
                guard let input = simulationInput(from: current) else {
                    return finish(action.code, phase: phase, message: action.message,
                                  rounds: round, modelCalls: modelCalls,
                                  context: current)
                }
                let result = await advance(event: ["type": "SIMULATE", "input": input])
                let verdict = result["verdict"] as? String ?? "UNKNOWN_FACTORY_RESULT"
                trace.append(.init(round: round, actor: "VERA_CROSS_CLOTH",
                                   action: "SIMULATE", verdict: verdict))
                if verdict.hasPrefix("UNKNOWN_") {
                    return finish(verdict, phase: phase, message: refusalText(result),
                                  rounds: round, modelCalls: modelCalls,
                                  context: result)
                }
                continue
            case .waitForSewingCorpus:
                let result = await runAutomaticSewingSearch(state: current)
                let verdict = result["verdict"] as? String ?? "UNKNOWN_NO_SEWING_CORPUS"
                trace.append(.init(round: round, actor: "VERA_CONSTRUCTION_SEARCH",
                                   action: "STRUCTURE_TO_SEWING", verdict: verdict))
                if verdict.hasPrefix("UNKNOWN_") {
                    return finish(verdict, phase: phase, message: refusalText(result),
                                  rounds: round, modelCalls: modelCalls,
                                  context: result)
                }
                continue
            case .waitForImage, .waitForHuman, .stopped:
                return finish(action.code, phase: phase, message: action.message,
                              rounds: round, modelCalls: modelCalls,
                              context: current)
            case .converged:
                return finish("CONVERGED", phase: phase, message: action.message,
                              rounds: round, modelCalls: modelCalls)
            case .callEngine:
                guard let eventType = action.eventType else {
                    return finish("UNKNOWN_FACTORY_EVENT", phase: phase,
                                  message: "決定論的eventがありません。",
                                  rounds: round, modelCalls: modelCalls)
                }
                var event: [String: Any] = ["type": eventType]
                if eventType == "GENERATE_PATTERN" { event["preview_mannequin"] = true }
                if eventType == "REPAIR_PATTERN" { event["budget"] = 8 }
                if eventType == "SIMULATE",
                   let input = Self.findDictionary(named: "simulation_input", in: current) {
                    event["input"] = input
                }
                let result = await advance(event: event)
                let verdict = result["verdict"] as? String ?? "UNKNOWN_FACTORY_RESULT"
                trace.append(.init(round: round, actor: "VERA_ENGINE",
                                   action: eventType, verdict: verdict))
                if verdict.hasPrefix("UNKNOWN_") || verdict.hasPrefix("ESCALATE_") {
                    return finish(verdict, phase: phase, message: refusalText(result),
                                  rounds: round, modelCalls: modelCalls,
                                  context: result)
                }
                guard let next = state(from: result) else {
                    return finish("UNKNOWN_FACTORY_ENGINE_RESPONSE", phase: phase,
                                  message: refusalText(result), rounds: round,
                                  modelCalls: modelCalls, context: result)
                }
                if eventType == "GENERATE_PATTERN",
                   let pattern = next["pattern"] as? [String: Any] {
                    publishPatternArtifact(pattern, repairSummary:
                        "承認した構造候補から3Dと型紙を再生成しました。縫製修復は次工程です。")
                } else if eventType == "REPAIR_PATTERN",
                          let repair = next["repair"] as? [String: Any],
                          var pattern = repair["pattern"] as? [String: Any] {
                    let sewable = repair["sewable"] as? Bool == true
                    if let manufacturing = repair["manufacturing_preview"] {
                        pattern["manufacturing_preview"] = manufacturing
                    }
                    if let sewingPlan = repair["topology_sewing_plan"] {
                        pattern["topology_sewing_plan"] = sewingPlan
                    }
                    if let engineering = repair["engineering_review"] {
                        pattern["engineering_review"] = engineering
                    }
                    if let package = repair["export_package"] {
                        pattern["export_package"] = package
                    }
                    if let verification = repair["export_verification"] {
                        pattern["export_verification"] = verification
                    }
                    publishPatternArtifact(
                        pattern,
                        repairSummary: sewable
                            ? "決定論的な幾何縫製検査を通過しました（製造保証ではありません）。"
                            : "修復後も未解決の縫製検査があります。ログを確認してください。")
                }
                let nextPhase = next["phase"] as? String ?? phase
                if eventType == "ITERATE", verdict == "CONTINUE",
                   phase == "ITERATING", nextPhase == phase {
                    // ITERATING is the one intentional same-phase transition.
                    // The Python harness increments its persisted iteration on
                    // every accepted CONTINUE; this Swift loop remains bounded
                    // by hardRoundLimit and may only exit through convergence
                    // or a typed budget escalation.
                    continue
                }
                guard nextPhase != phase else {
                    let stoppedVerdict = verdict == "ANSWER"
                        ? "UNKNOWN_FACTORY_NO_PROGRESS" : verdict
                    let reason = refusalText(result)
                    return finish(stoppedVerdict, phase: phase,
                                  message: reason.isEmpty
                                    ? "\(eventType) は状態を進めませんでした。再試行せず停止します。"
                                    : reason,
                                  rounds: round, modelCalls: modelCalls,
                                  context: result)
                }
            case .askModel:
                guard let task = action.modelTask, let eventType = action.eventType else {
                    return finish("UNKNOWN_MODEL_TASK", phase: phase,
                                  message: "候補生成工程が不正です。",
                                  rounds: round, modelCalls: modelCalls)
                }
                var event: [String: Any]?
                if task == "structure_hypotheses",
                   pendingVisionHypotheses.count >= 2 {
                    event = ["hypotheses": pendingVisionHypotheses,
                             "front_only": true,
                             "proposal_route": "pixel-seeing vision LLM; proposal only"]
                }
                // The image model has already had one pixel-grounded turn.
                // If its richer parts proposal did not compile, prefer the
                // geometry-derived alternatives opened by retrieval instead
                // of blocking the same user request on a second, text-only
                // multi-minute model call.  The LLM remains the proposal mouth
                // for visible structure and later material alternatives; Vera
                // owns this deterministic fallback and labels it explicitly.
                if event == nil, task == "structure_hypotheses",
                   pendingProceduralHypotheses.count >= 2 {
                    event = ["hypotheses": pendingProceduralHypotheses,
                             "front_only": true,
                             "proposal_route": "procedural geometry fallback"]
                    trace.append(.init(
                        round: round, actor: "VERA_GEOMETRY_FALLBACK",
                        action: "OPEN_STRUCTURE_ALTERNATIVES_WITHOUT_SECOND_MODEL_WAIT",
                        verdict: "PROPOSED_\(pendingProceduralHypotheses.count)"))
                }
                if event == nil, let proposer {
                    let prompt = Self.proposalPrompt(task: task, state: current,
                                                     userRequest: userRequest)
                    modelCalls += 1
                    totalModelCalls = modelCalls
                    if let raw = await proposer(prompt),
                       let payload = Self.parseProposal(raw, task: task) {
                        if task != "material_candidates"
                            || Self.hasTypedMaterialParameters(payload) {
                            event = payload
                        }
                    } else {
                        trace.append(.init(round: round, actor: "LLM_PROPOSAL_GATE",
                                           action: task, verdict: "RETRY_PROCEDURAL_FALLBACK"))
                    }
                }
                if event == nil, task == "material_candidates" {
                    event = ["candidates": Self.proceduralMaterialCandidates(),
                             "proposal_route": "typed material-range fallback"]
                }
                guard var event else {
                    return finish("UNKNOWN_MODEL_PROPOSAL", phase: phase,
                                  message: "モデル候補も幾何フォールバックも構成できませんでした。",
                                  rounds: round, modelCalls: modelCalls)
                }
                // The controller owns the verb. Any model-supplied type,
                // approval, verdict or selection is overwritten or removed.
                event["type"] = eventType
                event.removeValue(forKey: "approval_id")
                event.removeValue(forKey: "approver")
                event.removeValue(forKey: "selected")
                event.removeValue(forKey: "by")
                let result = await advance(event: event)
                let verdict = result["verdict"] as? String ?? "UNKNOWN_FACTORY_RESULT"
                trace.append(.init(round: round, actor: "LLM_PROPOSAL_GATE",
                                   action: eventType, verdict: verdict))
                if verdict.hasPrefix("UNKNOWN_"), task == "structure_hypotheses",
                   pendingProceduralHypotheses.count >= 2,
                   (event["proposal_route"] as? String) != "procedural geometry fallback" {
                    let fallback = await advance(event: [
                        "type": eventType, "front_only": true,
                        "hypotheses": pendingProceduralHypotheses,
                        "proposal_route": "procedural geometry retry",
                    ])
                    let fallbackVerdict = fallback["verdict"] as? String ?? "UNKNOWN_FACTORY_RESULT"
                    trace.append(.init(round: round, actor: "VERA_GEOMETRY_RETRY",
                                       action: eventType, verdict: fallbackVerdict))
                    if !fallbackVerdict.hasPrefix("UNKNOWN_") { continue }
                    return finish(fallbackVerdict, phase: phase,
                                  message: refusalText(fallback), rounds: round,
                                  modelCalls: modelCalls, context: fallback)
                }
                if verdict.hasPrefix("UNKNOWN_") {
                    return finish(verdict, phase: phase, message: refusalText(result),
                                  rounds: round, modelCalls: modelCalls,
                                  context: result)
                }
            }
        }
        return finish("ESCALATE_HUMAN_REACT_BUDGET", phase: phase,
                      message: "服飾ReActループが固定上限に達しました。",
                      rounds: hardRoundLimit, modelCalls: modelCalls)
    }

    func submitRetrieval(source: [String: Any], hits: [[String: Any]],
                         userRequest: String, proposer: Proposer?) async -> Report {
        let result = await advance(event: ["type": "SUBMIT_RETRIEVAL",
                                           "source": source, "hits": hits])
        let verdict = result["verdict"] as? String ?? "UNKNOWN_FACTORY_RESULT"
        guard !verdict.hasPrefix("UNKNOWN_") else {
            return finish(verdict, phase: phase, message: refusalText(result),
                          rounds: 1, modelCalls: 0)
        }
        return await runUntilPause(userRequest: userRequest, proposer: proposer)
    }

    func approveShape(_ candidate: Candidate, by: String, userRequest: String,
                      proposer: Proposer?) async -> Report {
        let result = await advance(event: [
            "type": "APPROVE_HYPOTHESIS", "candidate_id": candidate.id,
            "digest": candidate.digest, "by": by,
        ])
        let verdict = result["verdict"] as? String ?? "UNKNOWN_FACTORY_RESULT"
        guard verdict == "APPROVED" else {
            return finish(verdict, phase: phase, message: refusalText(result),
                          rounds: 1, modelCalls: 0)
        }
        return await runUntilPause(userRequest: userRequest, proposer: proposer)
    }

    /// Record an explicit human rejection against the exact candidate digest.
    /// Rejection does not select another candidate and does not let a model act
    /// for the human; it leaves the comparison open for a later choice.
    func rejectShape(_ candidate: Candidate, by: String,
                     reason: String) async -> Report {
        let result = await advance(event: [
            "type": "REJECT_HYPOTHESIS", "candidate_id": candidate.id,
            "digest": candidate.digest, "by": by, "reason": reason,
        ])
        let verdict = result["verdict"] as? String ?? "UNKNOWN_FACTORY_RESULT"
        guard verdict == "REJECTED", let next = state(from: result) else {
            return finish(verdict, phase: phase, message: refusalText(result),
                          rounds: 1, modelCalls: 0)
        }
        phase = next["phase"] as? String ?? phase
        publishCandidates(from: next)
        clearCandidatePreviewArtifacts()
        trace.append(.init(round: max(1, trace.count), actor: "NAMED_HUMAN",
                           action: "REJECT_HYPOTHESIS", verdict: verdict))
        return finish(verdict, phase: phase,
                      message: "候補をdigest付きで却下しました。比較は開いたままです。",
                      rounds: 1, modelCalls: 0)
    }

    /// Compensate the latest active structure approval/rejection in the
    /// persisted factory journal.  Python invalidates every downstream
    /// artifact bound to an undone approval; the Swift projection mirrors that
    /// invalidation instead of continuing to display stale pattern data.
    func undoShapeDecision(by: String) async -> Report {
        guard let decisionID = activeShapeDecisionID else {
            return finish("UNKNOWN_NOTHING_TO_UNDO", phase: phase,
                          message: "取り消せる候補判断がありません。",
                          rounds: 1, modelCalls: 0)
        }
        let commandID = "undo-shape-\(decisionID)"
        let result = await advance(event: [
            "type": "UNDO_HYPOTHESIS_DECISION", "by": by,
            "decision_id": decisionID, "command_id": commandID,
        ])
        let verdict = result["verdict"] as? String ?? "UNKNOWN_FACTORY_RESULT"
        guard verdict == "ANSWER", let next = state(from: result) else {
            return finish(verdict, phase: phase, message: refusalText(result),
                          rounds: 1, modelCalls: 0)
        }
        phase = next["phase"] as? String ?? phase
        publishCandidates(from: next)
        clearCandidatePreviewArtifacts()
        trace.append(.init(round: max(1, trace.count), actor: "NAMED_HUMAN",
                           action: "UNDO_HYPOTHESIS_DECISION", verdict: verdict))
        return finish(verdict, phase: phase,
                      message: "直前の候補判断を取り消し、依存成果物を失効しました。",
                      rounds: 1, modelCalls: 0)
    }

    func approveMaterial(_ candidate: Candidate, by: String, userRequest: String,
                         proposer: Proposer?) async -> Report {
        let result = await advance(event: [
            "type": "APPROVE_MATERIAL", "candidate_id": candidate.id,
            "digest": candidate.digest, "by": by,
        ])
        let verdict = result["verdict"] as? String ?? "UNKNOWN_FACTORY_RESULT"
        guard verdict == "APPROVED" else {
            return finish(verdict, phase: phase, message: refusalText(result),
                          rounds: 1, modelCalls: 0)
        }
        return await runUntilPause(userRequest: userRequest, proposer: proposer)
    }

    /// Render the exact candidate named by the UI without approving it.
    /// Both 3D and flat pieces come from the same structure digest, so the
    /// comparison button cannot silently keep showing the generic body block.
    @discardableResult
    func previewShape(_ candidate: Candidate) async -> Bool {
        // Older/free-window callers use one preview action for both domains.
        // Dispatch a material row to the material path before looking for a
        // structure payload; a material candidate is not a structure graph.
        if phase == "MATERIAL_CANDIDATES_READY"
            || materialCandidatePayloads[candidate.id] != nil {
            return await previewMaterial(candidate)
        }
        // Prefer the geometry-first artifact bound to the audited image. This
        // path keeps the same front vertices across rear alternatives and
        // prevents the older semantic BODY_SHELL/cape preview from replacing
        // a layered or asymmetric source garment.
        if let artifact = geometricRearCandidateArtifacts[candidate.id] {
            previewArtifact = artifact
            rawPreviewPattern = nil
            candidateSewingPlan = nil
            trace.append(.init(
                round: max(1, previewAttempts),
                actor: "VERA_GEOMETRIC_ATELIER_MCP",
                action: "PREVIEW_IMAGE_BOUND_REAR_\(candidate.id)",
                verdict: "PROPOSED_FRONT_FIXED_REAR_INFERRED"))
            return true
        }
        guard let payload = shapeCandidatePayloads[candidate.id],
              let structure = payload["structure"] as? [String: Any] else {
            return false
        }
        if let artifacts = visionPipelineArtifacts[candidate.id],
           let preview = artifacts["preview"] as? [String: Any],
           let pattern = artifacts["flat_pattern"] as? [String: Any],
           let manufacturing = artifacts["manufacturing_preview"] as? [String: Any],
           let sewing = artifacts["sewing_plan"] as? [String: Any],
           let binding = artifacts["artifact_binding"] as? [String: Any],
           binding["same_structure_digest"] as? Bool == true,
           binding["all_downstream_artifacts_bound"] as? Bool == true,
           binding["structure_digest"] as? String
                == structure["structure_digest"] as? String {
            if await publishTargetBoundBackPreview(candidate: candidate,
                structurePreview: preview,
                pattern: pattern, manufacturing: manufacturing,
                sewingPlan: sewing
            ) {
                trace.append(.init(
                    round: max(1, previewAttempts),
                    actor: "VERA_TARGET_BOUND_CANDIDATE_MCP",
                    action: "PREVIEW_\(candidate.id)",
                    verdict: "PROPOSED_FRONT_FIXED_REAR_INFERRED"))
                return true
            }
            guard publishPreview(
                candidate: candidate, preview: preview, pattern: pattern,
                manufacturing: manufacturing, sewingPlan: sewing,
                method: "image parts IR → deterministic topology → bound 3D + flat pattern"
            ) else { return false }
            trace.append(.init(round: max(1, previewAttempts),
                               actor: "VERA_PARTS_PIPELINE_MCP",
                               action: "PREVIEW_\(candidate.id)", verdict: "PROPOSED"))
            return true
        }
        let proposalSource = (payload["proposal_source"] as? String ?? "")
            .lowercased()
        let isPixelSemanticCandidate = proposalSource.contains("pixel")
            || payload["pipeline_source"] != nil
            || payload["visible_structure_source_candidate_id"] != nil
        if isPixelSemanticCandidate {
            visionPipelineReviewItems = [[
                "code": "REVIEW_CANDIDATE_ARTIFACT_BINDING_REQUIRED",
                "state": "REVIEW",
                "why": "この画像候補の可視部品グラフに結合した3D・型紙・縫製順序が見つかりません。旧3ピース型紙へ置換せず停止しました。",
                "candidate_id": candidate.id,
                "fallback_used": false,
                "manufacturing_ready": false,
                "manufacturing_certified": false,
            ]]
            trace.append(.init(
                round: max(1, previewAttempts),
                actor: "VERA_PARTS_PIPELINE_MCP",
                action: "REFUSE_GENERIC_PREVIEW_\(candidate.id)",
                verdict: "REVIEW_CANDIDATE_ARTIFACT_BINDING_REQUIRED"))
            return false
        }
        return await previewProceduralShape(
            candidate, structure: structure)
    }

    /// Outline/retrieval-only candidates have no pixel-semantic parts claim.
    /// They may still use the legacy graph preview as an explicitly scoped
    /// silhouette comparison, never as evidence that the pictured garment was
    /// decomposed into manufacturing parts.
    private func previewProceduralShape(
        _ candidate: Candidate, structure: [String: Any]
    ) async -> Bool {
        let request: [String: Any] = [
            "candidate_id": candidate.id,
            "structure": structure,
            "candidate_state": "PROPOSED",
        ]
        guard let json = Self.jsonString(request) else { return false }
        let pattern = await toolDoor("garment_structure_pattern", ["json_text": json])
        let preview = await toolDoor("garment_structure_preview", ["json_text": json])
        if await publishTargetBoundBackPreview(
            candidate: candidate, structurePreview: preview, pattern: pattern,
            manufacturing: nil, sewingPlan: nil
        ) {
            trace.append(.init(
                round: max(1, previewAttempts),
                actor: "VERA_TARGET_BOUND_CANDIDATE_MCP",
                action: "PREVIEW_\(candidate.id)",
                verdict: "PROPOSED_FRONT_FIXED_REAR_INFERRED"))
            return true
        }
        guard publishPreview(candidate: candidate, preview: preview,
                             pattern: pattern,
                             manufacturing: nil, sewingPlan: nil,
                             method: "outline-only structure graph → provisional silhouette and flat pieces")
        else { return false }
        let outlineOnlyReview: [String: Any] = [
            "code": "PROPOSED_OUTLINE_ONLY_PREVIEW",
            "state": "REVIEW",
            "why": "画像の意味部品ではなく確認輪郭から作った暫定比較です。可視袖・層・装飾の再現を保証しません。",
            "candidate_id": candidate.id,
            "fallback_used": true,
            "fallback_scope": "front silhouette only",
            "manufacturing_ready": false,
            "manufacturing_certified": false,
        ]
        // Previewing the silhouette fallback must not erase the typed reason
        // why candidate-bound image parts failed.  The user needs both facts:
        // the current visual is outline-only, and the exact engine refusal
        // that prevented the richer 3D/pattern artifact from being published.
        visionPipelineReviewItems = Self.uniqueRequirementItems(
            visionPipelineReviewItems + [outlineOnlyReview])
        trace.append(.init(round: max(1, previewAttempts),
                           actor: "VERA_STRUCTURE_PREVIEW",
                           action: "PREVIEW_\(candidate.id)", verdict: "PROPOSED"))
        return true
    }

    /// Preserve the adopted source-view target instead of replacing it
    /// with a generic BODY_SHELL/cape primitive. Only vertices belonging to
    /// the unobserved rear surface are moved behind a selected/proposed body
    /// proxy. This is a visual comparison bridge, not a claim that one image
    /// measured the wearer's body or revealed the back construction.
    private func publishTargetBoundBackPreview(
        candidate: Candidate, structurePreview: [String: Any],
        pattern: [String: Any], manufacturing: [String: Any]?,
        sewingPlan: [String: Any]?
    ) async -> Bool {
        guard targetCleanupConfirmed,
              (pattern["verdict"] as? String) == "ANSWER",
              (structurePreview["verdict"] as? String) == "ANSWER",
              let target = targetReconstruction else { return false }

        // Automatic/component-aware intake can use the garment-only front
        // surface directly.  If a human has brush-edited the fused target,
        // retain those edits instead. Both remain source-view proposals.
        let useComponentFront = target.garmentComponentSurface != nil
            && (targetSculptRemovedFaces.isEmpty
                || targetCleanupAuthority == "AUTO_ACCEPTED_FOR_PREVIEW")
        guard let surface = useComponentFront
                ? target.garmentComponentSurface : target.sculptSurface,
              surface.faces.count == surface.faceRegionIDs.count else {
            return false
        }
        let vertices = useComponentFront
            ? surface.verticesCM : targetSculptDisplayVertices
        guard !vertices.isEmpty else { return false }
        let removedFaces = useComponentFront
            ? [] : targetSculptRemovedFaces.sorted()
        let avatar = selectedBaseAvatar
        let request: [String: Any] = [
            "schema": "garment.target-bound-candidate-preview.request.v1",
            "candidate_id": candidate.id,
            "front_target": [
                "vertices_cm": vertices,
                "faces": surface.faces,
                "face_region_ids": surface.faceRegionIDs,
                "face_component_ids": surface.faceComponentIDs,
                "texture_coordinates": surface.textureCoordinates,
                "removed_face_indices": removedFaces,
                "authority": targetCleanupAuthority,
                "digest": targetSculptDigest ?? target.targetDigest,
            ],
            "candidate_preview": structurePreview,
            "base_avatar": [
                "avatar_id": avatar.id,
                "kind": "PARAMETRIC_GAME_AVATAR",
                "authority": avatar.authority,
                "geometry_digest": avatar.geometryDigest,
                "measurements_cm": [
                    "height": avatar.heightCM,
                    "chest_bust": avatar.chestCM,
                    "waist": avatar.waistCM,
                    "hip": avatar.hipCM,
                ],
            ],
        ]
        guard let json = Self.jsonString(request) else { return false }
        let preview = await toolDoor(
            "garment_target_bound_candidate_preview", ["json_text": json])
        guard (preview["verdict"] as? String) == "ANSWER",
              let binding = preview["binding"] as? [String: Any],
              binding["front_fixed"] as? Bool == true,
              binding["rear_observed"] as? Bool == false,
              let boundFrontAuthority = binding["front_authority"] as? String,
              boundFrontAuthority == targetCleanupAuthority else { return false }
        let reviews: [[String: Any]] = [[
            "code": "PROPOSED_TARGET_BOUND_REAR_PREVIEW",
            "state": "REVIEW",
            "why": "正面は採用済み写真由来ターゲット（\(boundFrontAuthority)）を保持し、背面奥行きだけを選択体型と候補構造から生成しました。体型・背面・縫い目は実測または観測ではありません。",
            "candidate_id": candidate.id,
            "front_target_fixed": true,
            "front_fixed": true,
            "front_authority": boundFrontAuthority,
            "rear_observed": false,
            "body_proxy_authority": selectedBaseAvatar.authority,
            "manufacturing_ready": false,
            "manufacturing_certified": false,
        ]]
        guard publishPreview(
            candidate: candidate, preview: preview, pattern: pattern,
            manufacturing: manufacturing, sewingPlan: sewingPlan,
            method: "image-specific source front + candidate geometry + PROPOSED body-constrained rear",
            assumptions: [
                "正面形状は写真由来ターゲットで、採用権限は\(targetCleanupAuthority)です。",
                "背面と奥行きは未観測で、選択体型プロキシと候補構造から生成したPROPOSEDです。",
                "表示3Dと暫定型紙はまだ幾何収束しておらず、製造可能性を保証しません。",
            ],
            surfaceSource: "image-specific adopted front (\(targetCleanupAuthority)) + candidate-specific proposed rear")
        else { return false }
        visionPipelineReviewItems = Self.uniqueRequirementItems(
            visionPipelineReviewItems + reviews)
        return true
    }

    /// Compare one material proposal on the already approved structure and
    /// flat pattern. The material stays PROPOSED even when the numerical
    /// reference step succeeds; no image observation or manufacturing claim
    /// is created by this preview.
    @discardableResult
    func previewMaterial(_ candidate: Candidate) async -> Bool {
        guard let payload = materialCandidatePayloads[candidate.id],
              payload["digest"] as? String == candidate.digest else {
            return publishMaterialPreviewReview(
                candidate: candidate,
                code: "REVIEW_MATERIAL_CANDIDATE_BINDING_REQUIRED",
                message: "素材候補のIDとdigestを現在の比較表へ結び直してください。")
        }
        guard let basePattern = materialPreviewBasePattern ?? rawPreviewPattern,
              let baseArtifact = materialPreviewBaseArtifact ?? previewArtifact else {
            return publishMaterialPreviewReview(
                candidate: candidate,
                code: "REVIEW_APPROVED_STRUCTURE_PREVIEW_REQUIRED",
                message: "承認済み構造と固定型紙がないため、素材比較は実行できません。")
        }
        guard let input = simulationInput(
            materialCandidate: payload, materialID: candidate.id,
            basePattern: basePattern, baseArtifact: baseArtifact),
              let inputJSON = Self.jsonString(input) else {
            return publishMaterialPreviewReview(
                candidate: candidate,
                code: "REVIEW_MATERIAL_PARAMETERS_OR_FIXED_MESH_REQUIRED",
                message: "素材の型付きSI物性、または承認構造の固定メッシュが不足しています。")
        }

        let simulated = await toolDoor(
            "industrial_cloth_simulate", ["json_text": inputJSON])
        guard simulated["verdict"] as? String == "ANSWER",
              let state = simulated["state"] as? [String: Any],
              let positions = state["positions"] as? [[Double]],
              let rest = input["rest_positions"] as? [[Double]],
              positions.count == rest.count,
              positions.count == baseArtifact.points.count else {
            let reason = simulated["why"] as? String
                ?? "numerical result did not return a mesh bound to the fixed structure"
            return publishMaterialPreviewReview(
                candidate: candidate,
                code: "REVIEW_MATERIAL_SIMULATION_COMPARISON_UNAVAILABLE",
                message: "素材比較を生成できませんでした: \(reason)",
                payload: payload)
        }

        let displacements = zip(rest, positions).map { before, after -> Double in
            guard before.count >= 3, after.count >= 3 else { return 0 }
            return sqrt(
                pow(after[0] - before[0], 2)
                + pow(after[1] - before[1], 2)
                + pow(after[2] - before[2], 2))
        }
        let meanDisplacement = displacements.isEmpty
            ? 0 : displacements.reduce(0, +) / Double(displacements.count)
        let maxDisplacement = displacements.max() ?? 0
        let resolved = ((input["materials"] as? [String: Any])?["xpbd"]
            as? [String: Any])?[candidate.id] as? [String: Any] ?? [:]
        let source: Any = payload["source"]
            ?? "proposal source not supplied; material remains unmeasured"
        let fixedBinding: [String: Any] = [
            "structure_fixed": true,
            "flat_pattern_fixed": true,
            "rest_mesh_fixed": true,
            "structure_candidate_id": basePattern["candidate_id"]
                ?? basePattern["source_candidate_id"] ?? "approved-structure",
            "structure_digest": basePattern["structure_digest"]
                ?? basePattern["source_structure_digest"] ?? "not-exposed-by-engine",
            "pattern_digest": basePattern["digest"]
                ?? basePattern["pattern_digest"] ?? "not-exposed-by-engine",
        ]
        let proposal: [String: Any] = [
            "schema": "garment.material-preview.v1",
            "candidate_id": candidate.id,
            "candidate_digest": candidate.digest,
            "state": "PROPOSED",
            "authority": "PROPOSED",
            "observed": false,
            "manufacturing_ready": false,
            "manufacturing_certified": false,
            "parameters": (payload["xpbd"] as? [String: Any])
                ?? (payload["material_ranges"] as? [String: Any]) ?? [:],
            "resolved_reference_parameters": resolved,
            "provenance": [
                "source": source,
                "candidate_payload_digest": candidate.digest,
                "parameter_authority": "PROPOSED_NOT_MEASURED",
                "range_resolution": "nominal or midpoint for comparison only",
            ],
            "fixed_artifact_binding": fixedBinding,
            "simulation_comparison": [
                "verdict": "ANSWER",
                "state": "PROPOSED",
                "mean_displacement_m": meanDisplacement,
                "max_displacement_m": maxDisplacement,
                "same_rest_mesh_required_across_candidates": true,
                "industrial_completion": simulated["industrial_completion"] as? Bool
                    ?? false,
                "truth_contract": simulated["truth_contract"] as? [String: Any] ?? [:],
            ],
        ]
        candidateMaterialPreview = proposal
        var attachedPattern = basePattern
        attachedPattern["material_preview"] = proposal
        rawPreviewPattern = attachedPattern
        previewArtifact = PreviewArtifact(
            state: "PROPOSED", attempt: baseArtifact.attempt,
            method: "fixed approved structure + fixed flat pattern → PROPOSED material reference simulation",
            points: positions.map { point in point.map { $0 * 100.0 } },
            faces: baseArtifact.faces, edges: baseArtifact.edges,
            pieces: baseArtifact.pieces,
            assumptions: baseArtifact.assumptions + [
                "素材物性はPROPOSEDで、画像からの実測値ではありません。",
                "構造・型紙・rest meshを固定した候補間の参照比較です。",
                "この数値計算は製造保証・素材同定・観測事実ではありません。",
            ],
            repairSummary: "\(candidate.title) の参照挙動を表示中。素材の採用は別の人間承認です。",
            preservesSourceFront: baseArtifact.preservesSourceFront)
        lastReport = Report(
            verdict: "PROPOSED_MATERIAL_SIMULATION_COMPARISON", phase: phase,
            message: "承認済み構造と型紙を固定し、\(candidate.title) の未実測物性で参照比較しました。",
            iterations: max(1, previewAttempts), modelCalls: totalModelCalls)
        trace.append(.init(
            round: max(1, previewAttempts), actor: "VERA_MATERIAL_PREVIEW",
            action: "COMPARE_\(candidate.id)_ON_FIXED_ARTIFACTS",
            verdict: "PROPOSED"))
        return true
    }

    @discardableResult
    private func publishMaterialPreviewReview(
        candidate: Candidate, code: String, message: String,
        payload: [String: Any]? = nil
    ) -> Bool {
        candidateMaterialPreview = [
            "schema": "garment.material-preview.v1",
            "candidate_id": candidate.id,
            "candidate_digest": candidate.digest,
            "state": "REVIEW",
            "authority": "PROPOSED",
            "observed": false,
            "manufacturing_ready": false,
            "manufacturing_certified": false,
            "code": code,
            "message": message,
            "provenance": [
                "source": payload?["source"]
                    ?? "candidate binding or simulation evidence unavailable",
                "parameter_authority": "PROPOSED_NOT_MEASURED",
            ],
        ]
        _ = finish(
            code, phase: phase, message: message,
            rounds: max(1, previewAttempts), modelCalls: totalModelCalls,
            context: [
                "stage": "MATERIAL_PREVIEW",
                "missing_fields": [
                    "measured_material_properties",
                    "calibrated_material_binding",
                ],
                "allowed_resolution_kinds": [
                    ResolutionActionKind.humanInput.rawValue,
                    ResolutionActionKind.connectProvider.rawValue,
                    ResolutionActionKind.allowOneTimeLLMProposal.rawValue,
                    ResolutionActionKind.compareBoundedAlternatives.rawValue,
                    ResolutionActionKind.typedStop.rawValue,
                ],
                "authority": "PROPOSED_NOT_MEASURED",
                "provider_payload": payload ?? [:],
            ])
        trace.append(.init(
            round: max(1, previewAttempts), actor: "VERA_MATERIAL_PREVIEW",
            action: "MATERIAL_PREVIEW_REVIEW_\(candidate.id)", verdict: code))
        return false
    }

    private func publishPreview(candidate: Candidate,
                                preview: [String: Any],
                                pattern: [String: Any],
                                manufacturing: [String: Any]?,
                                sewingPlan: [String: Any]?,
                                method: String,
                                assumptions: [String]? = nil,
                                surfaceSource: String = "selected PROPOSED structure preview") -> Bool {
        guard (preview["verdict"] as? String) == "ANSWER",
              (pattern["verdict"] as? String) == "ANSWER",
              let mesh = preview["mesh"] as? [String: Any],
              let points = mesh["vertices"] as? [[Double]],
              let faces = mesh["faces"] as? [[Int]] else { return false }
        let displayedRows = (manufacturing?["pieces"] as? [[String: Any]])
            ?? (pattern["pieces"] as? [[String: Any]]) ?? []
        let pieces = displayedRows.enumerated().map {
            index, row in
            PreviewPiece(id: (row["piece_id"] as? String) ?? "piece-\(index)",
                         name: (row["name"] as? String)
                            ?? (row["piece_id"] as? String) ?? "piece \(index + 1)",
                         outline: (row["cut_line"] as? [[Double]])
                            ?? (row["outline"] as? [[Double]]) ?? [])
        }
        var simulationPattern = pattern
        if let manufacturing {
            simulationPattern["manufacturing_preview"] = manufacturing
        }
        if let sewingPlan {
            simulationPattern["topology_sewing_plan"] = sewingPlan
        }
        simulationPattern["garment_surface"] = [
            "verdict": "ANSWER", "units": "cm", "verts": points,
            "faces": faces, "source": surfaceSource,
        ]
        rawPreviewPattern = simulationPattern
        materialPreviewBasePattern = nil
        materialPreviewBaseArtifact = nil
        candidateMaterialPreview = nil
        candidateManufacturingPreview = manufacturing
        candidateSewingPlan = sewingPlan
        let preservesSourceFront =
            (preview["binding"] as? [String: Any])?["front_fixed"] as? Bool
            ?? false
        previewArtifact = PreviewArtifact(
            state: "PROPOSED", attempt: 1,
            method: method,
            points: points, faces: faces, edges: Self.meshEdges(faces), pieces: pieces,
            assumptions: assumptions ?? [
                "この候補の背面・奥行き・構造はAI/幾何によるPROPOSEDで、観測事実ではありません。",
                "3Dと型紙は同じstructure digestから生成されています。",
                "採用・身体寸法・素材・縫製検証はまだ完了していません。",
            ],
            repairSummary: "候補比較用。採用ボタンを押すまで工場工程へは反映されません。",
            preservesSourceFront: preservesSourceFront)
        return true
    }

    private func advance(event: [String: Any]) async -> [String: Any] {
        await door("advance", ["event": event])
    }

    /// Convert the deliberately small image-model vocabulary back to the
    /// typed parts IR, then run deterministic completion, topology, 3D and
    /// flat-pattern compilation as one MCP gate. The LLM only proposes parts;
    /// it never chooses engine tools or raises a proposal to an approval.
    func runVisionPartsPipeline(
        _ hypotheses: [[String: Any]]
    ) async -> [[String: Any]]? {
        let candidates: [[String: Any]] = hypotheses.compactMap { hypothesis in
            guard let structure = hypothesis["structure"] as? [String: Any],
                  let nodes = structure["nodes"] as? [[String: Any]],
                  !nodes.isEmpty,
                  let candidateID = hypothesis["candidate_id"] as? String else {
                return nil
            }
            let typedOrnaments = hypothesis["typed_ornament_proposals"]
                as? [[String: Any]] ?? []
            let routedPreviewNodeIDs = Set(typedOrnaments.compactMap {
                $0["normalized_preview_node_id"] as? String
            })
            // Newer parsing routes BOW/RIBBON/ROSETTE/TIE/FLAP directly to
            // the typed ornament compiler and intentionally does not append a
            // structural BAND/OVERLAY alias. Older persisted hypotheses may
            // still contain that alias. Count only aliases that are actually
            // present in this candidate; subtracting every ornament id made a
            // valid ornament-only route fail before it reached the MCP.
            let structuralNodeIDs = Set(nodes.compactMap {
                $0["node_id"] as? String
            })
            let presentRoutedPreviewNodeIDs = routedPreviewNodeIDs
                .intersection(structuralNodeIDs)
            let parts: [[String: Any]] = nodes.compactMap { node in
                guard let partID = node["node_id"] as? String,
                      let kind = node["kind"] as? String,
                      let dimensions = node["dimensions"] as? [String: Any]
                else { return nil }
                // The Python completion boundary owns true ornament geometry.
                // Do not send its rectangular Swift preview alias as a second
                // base part; append the original typed ornament below instead.
                if presentRoutedPreviewNodeIDs.contains(partID) { return nil }
                let attributes = node["attributes"] as? [String: Any] ?? [:]
                let visibleText = attributes["visible_basis"] as? String
                    ?? "vision model proposed this visible part from the front image"
                var submittedDimensions = dimensions
                if let requested = node["dimension_provenance"] as? [String: Any] {
                    for (field, rawRecord) in requested {
                        guard let record = rawRecord as? [String: Any],
                              record["state"] as? String == "REQUESTED",
                              record["not_measured_from_image"] as? Bool == true,
                              let value = dimensions[field] else { continue }
                        let targets = record["source_requirement_targets"]
                            as? [String] ?? []
                        submittedDimensions[field] = [
                            "value_cm": value,
                            "state": "PROPOSED",
                            "basis": "explicit user-requested preview dimension (\(targets.joined(separator: ", "))); USER_EXPLICIT_REQUEST_NOT_MEASUREMENT_CERTIFICATE",
                            "breaks_when": "the user changes the request, a measurement source is supplied, or candidate topology changes",
                        ]
                    }
                }
                var part: [String: Any] = [
                    "part_id": partID,
                    "kind": kind,
                    "layer": node["layer"] as? Int ?? 0,
                    "placement": attributes["placement"] as? String ?? "unspecified garment region",
                    "visible_basis": [
                        "state": "PROPOSED",
                        "basis": visibleText,
                        "breaks_when": "a rear/side observation or human review rejects this image-model proposal",
                    ],
                    "dimensions": submittedDimensions,
                ]
                for name in ["garment_unit", "attached_to", "side", "shape",
                             "detail_role", "construction_role",
                             "attachment_relation", "quantity", "closure_detail",
                             "opening_topology", "waist_join_mode",
                             "waist_join_state", "waist_join_provenance",
                             "sleeve_join_mode", "sleeve_join_state",
                             "sleeve_join_provenance",
                             "waist_stack_state", "waist_stack_parent",
                             "waist_stack_id", "waist_stack_order",
                             "waist_stack_construction_mode"]
                    where attributes[name] != nil {
                    part[name] = attributes[name]
                }
                return part
            }
            guard parts.count == nodes.count - presentRoutedPreviewNodeIDs.count else {
                return nil
            }
            let routedOrnaments: [[String: Any]] = typedOrnaments.compactMap { row in
                var ornament = row
                guard let visibleText = ornament["visible_basis"] as? String else {
                    return nil
                }
                ornament["visible_basis"] = [
                    "state": "PROPOSED",
                    "basis": visibleText,
                    "breaks_when": "another view or construction review rejects this image-model ornament proposal",
                ]
                ornament.removeValue(forKey: "normalized_preview_node_id")
                ornament.removeValue(forKey: "authority")
                ornament["state"] = "PROPOSED"
                return ornament
            }
            guard routedOrnaments.count == typedOrnaments.count else { return nil }
            return ["candidate_id": candidateID, "state": "PROPOSED",
                    "parts": parts + routedOrnaments]
        }
        guard candidates.count == hypotheses.count, candidates.count >= 2 else {
            return nil
        }
        let partsIR: [String: Any] = [
            "schema": "garment.parts-ir.v1",
            "state": "PROPOSED",
            "candidates": candidates,
        ]
        let operationEnvelope: [[String: Any]] = hypotheses.compactMap { hypothesis in
            guard let candidateID = hypothesis["candidate_id"] as? String else { return nil }
            return [
                "candidate_id": candidateID,
                "state": "PROPOSED",
                "operations": hypothesis["pattern_operation_proposals"] as? [[String: Any]] ?? [],
            ]
        }
        guard let json = Self.jsonString([
            "parts_ir": partsIR,
            "use_bounded_preview_profile": true,
            "candidate_count": candidates.count,
            // The parts pipeline deliberately ignores this audit envelope.
            // It is still sent across the MCP boundary so the exact proposal
            // set is bound to the call record; executable transforms are sent
            // separately only after compiled piece/edge resolution below.
            "vision_pattern_operation_proposals": operationEnvelope,
        ]) else {
            return nil
        }
        let result = await toolDoor(
            "garment_parts_ir_pipeline", ["json_text": json])
        guard let pipelineVerdict = result["verdict"] as? String,
              ["PROPOSED", "UNRESOLVED"].contains(pipelineVerdict),
              let typed = result["candidates"] as? [[String: Any]],
              typed.count == hypotheses.count else { return nil }
        let byID: [String: [String: Any]] = Dictionary(
            uniqueKeysWithValues: typed.compactMap { candidate in
                guard let id = candidate["candidate_id"] as? String else {
                    return nil
                }
                return (id, candidate)
            })
        guard byID.count == hypotheses.count else { return nil }
        var mergedHypotheses: [[String: Any]] = []
        var siblingReviews: [[String: Any]] = []
        for hypothesis in hypotheses {
            guard let id = hypothesis["candidate_id"] as? String,
                  let pipeline = byID[id] else { return nil }
            guard pipeline["execution_status"] as? String == "SUCCEEDED",
                  let structure = pipeline["structure"] as? [String: Any],
                  let binding = pipeline["artifact_binding"] as? [String: Any],
                  binding["same_structure_digest"] as? Bool == true else {
                let failures = pipeline["failures"] as? [[String: Any]] ?? []
                let failureText = failures.prefix(4).map { failure in
                    let code = failure["code"] as? String
                        ?? failure["verdict"] as? String
                        ?? "UNKNOWN_PARTS_PIPELINE_FAILURE"
                    let why = failure["why"] as? String
                        ?? failure["message"] as? String ?? ""
                    return why.isEmpty ? code : "\(code): \(why)"
                }.joined(separator: " · ")
                siblingReviews.append([
                    "code": failures.first?["code"] as? String
                        ?? failures.first?["verdict"] as? String
                        ?? "UNKNOWN_PARTS_PIPELINE_CANDIDATE_REFUSAL",
                    "candidate_id": id,
                    "state": "REVIEW",
                    "authority": "PROPOSED",
                    "execution_status": pipeline["execution_status"] as? String
                        ?? "REFUSED",
                    "verdict": pipeline["verdict"] as? String
                        ?? "UNKNOWN_PARTS_PIPELINE_CANDIDATE_REFUSAL",
                    "failures": pipeline["failures"] as? [[String: Any]] ?? [],
                    "why": failureText.isEmpty
                        ? "候補固有の部品→3D→型紙パイプラインが拒否しました。"
                        : failureText,
                    "manufacturing_ready": false,
                    "manufacturing_certified": false,
                ])
                continue
            }
            var merged = hypothesis
            merged["structure"] = structure
            merged["topology_state"] = "PROPOSED"
            merged["topology_source"] = "garment_parts_ir_topology MCP"
            merged["pipeline_state"] = "PROPOSED"
            merged["pipeline_source"] = "garment_parts_ir_pipeline MCP"
            merged["artifact_binding"] = binding
            let proposals = hypothesis["pattern_operation_proposals"]
                as? [[String: Any]] ?? []
            let audited = await validateVisionPatternOperations(
                proposals, pipeline: pipeline, candidateID: id)
            merged["pattern_operation_proposals"] = audited
            merged["pattern_operation_bridge"] = [
                "state": "PROPOSED",
                "source": "pixel-seeing vision LLM; proposal only",
                "mcp_tool": "garment_pattern_transform",
                "validated_count": audited.filter {
                    (($0["execution"] as? [String: Any])?["status"] as? String)
                        == "MCP_VALIDATED_PROPOSAL"
                }.count,
                "review_count": audited.filter {
                    (($0["review"] as? [String: Any])?["required"] as? Bool) == true
                }.count,
                "canonical_pattern_mutated": false,
                "why_not_applied": "human review is required before an image-model transform changes the canonical candidate",
            ]
            visionPipelineArtifacts[id] = pipeline
            mergedHypotheses.append(merged)
        }
        guard mergedHypotheses.count >= 2 else {
            visionPipelineReviewItems = siblingReviews.isEmpty ? [[
                "code": "UNKNOWN_PARTS_PIPELINE_ALL_CANDIDATES_REFUSED",
                "state": "REVIEW",
                "why": "全ての画像構造候補が候補固有アーティファクトの生成前に拒否されました。",
                "manufacturing_ready": false,
                "manufacturing_certified": false,
            ]] : siblingReviews
            return nil
        }
        if !siblingReviews.isEmpty {
            for index in mergedHypotheses.indices {
                mergedHypotheses[index]["sibling_pipeline_reviews"] = siblingReviews
                mergedHypotheses[index]["all_model_candidates_succeeded"] = false
            }
        }
        return mergedHypotheses
    }

    /// Resolve a typed image-model operation against the exact compiled flat
    /// pattern.  Ambiguous node expansion or semantic edge names never reach
    /// the transform MCP.  Successful calls remain independent PROPOSED
    /// previews and do not mutate the candidate used by 3D/pattern binding.
    private func validateVisionPatternOperations(
        _ proposals: [[String: Any]], pipeline: [String: Any], candidateID: String
    ) async -> [[String: Any]] {
        guard let flatPattern = pipeline["flat_pattern"] as? [String: Any],
              let pieces = flatPattern["pieces"] as? [[String: Any]] else {
            return proposals.map {
                Self.withVisionOperationReview(
                    $0, code: "UNKNOWN_VISION_OPERATION_PATTERN_MISSING",
                    why: "candidate flat pattern is unavailable for deterministic target resolution")
            }
        }
        var results: [[String: Any]] = []
        for proposal in proposals {
            if ((proposal["review"] as? [String: Any])?["required"] as? Bool) == true {
                results.append(proposal)
                continue
            }
            guard let resolution = Self.resolveVisionOperationTarget(
                proposal, pieces: pieces) else {
                results.append(Self.withVisionOperationReview(
                    proposal, code: "UNKNOWN_VISION_OPERATION_TARGET_AMBIGUOUS",
                    why: "piece and semantic edge did not resolve to exactly one compiled pattern address"))
                continue
            }
            guard var operation = proposal["parameters"] as? [String: Any],
                  let kind = proposal["kind"] as? String else {
                results.append(Self.withVisionOperationReview(
                    proposal, code: "UNKNOWN_VISION_OPERATION_PARAMETERS",
                    why: "typed operation parameters are unavailable"))
                continue
            }
            if kind == "GATHER", operation["finished_length_cm"] == nil {
                guard let ratio = operation["ratio"] as? Double,
                      let cutLength = Self.compiledPatternEdgeLength(
                        piece: resolution.piece, edge: resolution.edge),
                      cutLength.isFinite, cutLength > 0 else {
                    results.append(Self.withVisionOperationReview(
                        proposal, code: "UNKNOWN_VISION_GATHER_TARGET_LENGTH",
                        why: "ratio-only GATHER needs one resolved compiled edge length"))
                    continue
                }
                operation["finished_length_cm"] = cutLength / ratio
                operation["finished_length_source"] =
                    "DERIVED_AFTER_EXACT_COMPILED_TARGET_RESOLUTION"
            }
            operation["kind"] = kind
            operation["edge"] = resolution.edge
            guard let json = Self.jsonString([
                "pattern": resolution.piece,
                "operation": operation,
                "proposal_context": [
                    "candidate_id": candidateID,
                    "operation_id": proposal["operation_id"] as? String ?? "",
                    "state": "PROPOSED",
                    "authority": "PROPOSED",
                ],
            ]) else {
                results.append(Self.withVisionOperationReview(
                    proposal, code: "UNKNOWN_VISION_OPERATION_ENCODING",
                    why: "typed operation could not be encoded for MCP"))
                continue
            }
            let transformed = await toolDoor(
                "garment_pattern_transform", ["json_text": json])
            guard transformed["verdict"] as? String == "ANSWER" else {
                results.append(Self.withVisionOperationReview(
                    proposal,
                    code: transformed["verdict"] as? String
                        ?? "UNKNOWN_VISION_OPERATION_MCP_REFUSAL",
                    why: transformed["why"] as? String
                        ?? "deterministic pattern transform refused the proposal"))
                continue
            }
            var validated = proposal
            validated["resolved_target"] = [
                "piece_id": resolution.piece["piece_id"] as? String ?? "",
                "edge": resolution.edge,
                "resolution": "EXACTLY_ONE_COMPILED_ADDRESS",
            ]
            validated["resolved_parameters"] = operation
            validated["execution"] = [
                "eligible": true,
                "status": "MCP_VALIDATED_PROPOSAL",
                "tool": "garment_pattern_transform",
                "canonical_pattern_mutated": false,
                "result_digest": transformed["after_digest"] as? String ?? "",
            ]
            validated["mcp_validation"] = transformed
            results.append(validated)
        }
        return results
    }

    private func runAutomaticRetrieval(state: [String: Any],
                                       userRequest: String) async -> [String: Any] {
        let evidence = state["image_evidence"] as? [String: Any] ?? [:]
        startAutonomousReferenceSearch(
            scope: "REAR",
            query: referenceSearchQuery(
                suffix: "garment back view rear construction official product reference",
                userRequest: userRequest))
        // Always open a corpus-free, geometry-derived topology search space.
        // It prevents a missing/non-vision LLM from collapsing every image to
        // the same BODY_SHELL while keeping every interpretation PROPOSED.
        var outlineHypotheses: [[String: Any]] = []
        if let outline = evidence["outline"] as? [String: Any],
           let cueJSON = Self.jsonString([
                "outline": outline,
                "regions": evidence["regions"] as? [[String: Any]] ?? [],
                "source_id": (evidence["source"] as? [String: Any])?["image_path"]
                    as? String ?? "confirmed-front",
           ]) {
            let cueResult = await toolDoor(
                "garment_front_outline_hypotheses", ["json_text": cueJSON])
            outlineHypotheses = cueResult["hypotheses"] as? [[String: Any]] ?? []
            if outlineHypotheses.count >= 2 {
                trace.append(.init(round: 1, actor: "VERA_FRONT_GEOMETRY",
                                   action: "OPEN_TOPOLOGY_ALTERNATIVES",
                                   verdict: cueResult["verdict"] as? String ?? "PROPOSED"))
            }
        }
        let request: [String: Any] = [
            "image_evidence": evidence,
            "request": userRequest,
            "strategy": "region + geometry + structure + rights",
        ]
        var retrieval: [String: Any] = [:]
        if let json = Self.jsonString(request) {
            retrieval = await toolDoor("garment_hybrid_retrieve", ["json_text": json])
        }
        if outlineHypotheses.count >= 2 {
            pendingProceduralHypotheses = outlineHypotheses
        } else if let hypotheses = retrieval["hypotheses"] as? [[String: Any]],
                  hypotheses.count >= 2 {
            pendingProceduralHypotheses = hypotheses
        }
        let source = retrieval["source"] as? [String: Any]
        let hits = retrieval["hits"] as? [[String: Any]]
        if source == nil || hits == nil || hits?.isEmpty == true {
            let fallback = Self.proceduralRetrieval(evidence: evidence)
            retrieval = fallback
            if pendingProceduralHypotheses.count < 2 {
                pendingProceduralHypotheses = fallback["hypotheses"] as? [[String: Any]] ?? []
            }
        }
        guard let acceptedSource = retrieval["source"] as? [String: Any],
              let acceptedHits = retrieval["hits"] as? [[String: Any]] else {
            return ["verdict": "UNKNOWN_RETRIEVAL_BACKEND",
                    "why": "hybrid retrieval returned no typed source/hits"]
        }
        return await advance(event: ["type": "SUBMIT_RETRIEVAL",
                                     "source": acceptedSource, "hits": acceptedHits])
    }

    private func runAutomaticSewingSearch(state: [String: Any]) async -> [String: Any] {
        guard let approval = state["shape_approval"] as? [String: Any],
              let approvalID = approval["approval_id"] as? String,
              !approvalID.isEmpty else {
            return ["verdict": "UNKNOWN_SHAPE_APPROVAL_REQUIRED"]
        }
        startAutonomousReferenceSearch(
            scope: "SEWING",
            query: referenceSearchQuery(
                suffix: "garment sewing construction order pattern tutorial",
                userRequest: ""))
        // The saved factory state is the authority boundary.  Never send a
        // caller-supplied state blob to a convenience sewing tool: a forged
        // blob could otherwise manufacture its own approval record.  The MCP
        // factory loads the current state and verifies its digest internally.
        let searched = await advance(event: ["type": "HYBRID_SEWING_SEARCH",
                                             "corpora": [],
                                             "require_commercial": true])
        let verdict = searched["verdict"] as? String ?? "UNKNOWN_NO_SEWING_CORPUS"
        guard verdict == "UNKNOWN_NO_SEWING_CORPUS" else { return searched }

        // A missing precedent corpus must not erase the deterministic order
        // already derived from the approved pattern topology. Continue with
        // that order as a PROPOSED workshop plan while retaining the corpus
        // gap, review requirements and non-certification flags in state.
        let repair = state["repair"] as? [String: Any]
        let pattern = state["pattern"] as? [String: Any]
        guard let plan = (repair?["topology_sewing_plan"] as? [String: Any])
                ?? (pattern?["topology_sewing_plan"] as? [String: Any]) else {
            return searched
        }
        let fallback = await advance(event: [
            "type": "USE_PROCEDURAL_SEWING_PLAN", "plan": plan,
        ])
        trace.append(.init(
            round: max(1, trace.count), actor: "VERA_PROCEDURAL_SEWING",
            action: "TOPOLOGY_ORDER_WITHOUT_CORPUS",
            verdict: fallback["verdict"] as? String ?? "UNKNOWN"))
        return fallback
    }

    /// Search is deliberately parallel and advisory. Local FashionSigLIP and
    /// rights-gated corpus retrieval remain the deterministic candidate route;
    /// the web agent supplies URLs for rear/sewing review and never injects a
    /// snippet as geometry, a licence, or a manufacturing fact.
    private func startAutonomousReferenceSearch(scope: String, query: String) {
        guard liveExternalEffectsEnabled else { return }
        let key = scope.uppercased()
        let cleaned = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleaned.isEmpty,
              referenceSearchQueries[key] != cleaned else { return }
        referenceSearchTasks[key]?.cancel()
        referenceSearchQueries[key] = cleaned
        if key == "REAR" { rearReferenceSearchStatus = "SEARCHING" }
        else { sewingReferenceSearchStatus = "SEARCHING" }
        referenceSearchTasks[key] = Task { [weak self] in
            guard let self else { return }
            let result = await WebSearchEngine.shared.search(query: cleaned)
            guard !Task.isCancelled,
                  self.referenceSearchQueries[key] == cleaned else { return }
            let rows = Self.parseGarmentReferenceListings(
                result.contextSnippet, scope: key)
            let status: String
            if result.isFailure {
                status = "UNKNOWN_REFERENCE_SEARCH_TRANSPORT"
            } else if rows.isEmpty {
                status = "REVIEW_NO_TYPED_REFERENCE_LISTINGS"
            } else {
                status = "PROPOSED_REFERENCES_READY"
            }
            if key == "REAR" {
                self.rearWebReferences = rows
                self.rearReferenceSearchStatus = status
            } else {
                self.sewingWebReferences = rows
                self.sewingReferenceSearchStatus = status
            }
            self.trace.append(.init(
                round: max(1, self.trace.count),
                actor: "VERA_AUTONOMOUS_REFERENCE_AGENT",
                action: "SEARCH_\(key)_REFERENCES",
                verdict: status))
        }
    }

    private func referenceSearchQuery(
        suffix: String, userRequest: String
    ) -> String {
        var terms = visibleFrontInventory.flatMap { item in
            [item.label, item.normalizedKind, item.garmentUnit]
        }
        let request = userRequest.trimmingCharacters(in: .whitespacesAndNewlines)
        if !request.isEmpty { terms.append(String(request.prefix(120))) }
        var seen = Set<String>()
        let unique = terms.compactMap { raw -> String? in
            let value = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            guard value.count >= 2 else { return nil }
            let key = value.lowercased()
            return seen.insert(key).inserted ? value : nil
        }
        return (Array(unique.prefix(10)) + [suffix]).joined(separator: " ")
    }

    private static func parseGarmentReferenceListings(
        _ markdown: String, scope: String
    ) -> [GarmentWebReference] {
        var rows: [GarmentWebReference] = []
        var seen = Set<String>()
        for block in markdown.components(separatedBy: "\n\n") {
            let lines = block.split(separator: "\n", omittingEmptySubsequences: true)
                .map { String($0).trimmingCharacters(in: .whitespaces) }
            guard let heading = lines.first, heading.hasPrefix("["),
                  let close = heading.firstIndex(of: "]"),
                  close < heading.index(before: heading.endIndex),
                  let urlIndex = lines.firstIndex(where: {
                      $0.hasPrefix("https://") || $0.hasPrefix("http://")
                  }) else { continue }
            let titleStart = heading.index(after: close)
            let title = String(heading[titleStart...])
                .trimmingCharacters(in: .whitespaces)
            let url = lines[urlIndex]
            guard !title.isEmpty, seen.insert(url).inserted else { continue }
            let snippet = lines.dropFirst(urlIndex + 1).joined(separator: " ")
            rows.append(GarmentWebReference(
                id: sha256(Data("\(scope):\(url)".utf8)),
                scope: scope, title: title, url: url,
                snippet: String(snippet.prefix(360)),
                authority: "PROPOSED_WEB_REFERENCE",
                rightsState: "RIGHTS_AND_PAGE_CONTENT_REVIEW_REQUIRED"))
            if rows.count == 5 { break }
        }
        return rows
    }

    private func buildGeometricPreview(outline: [String: Any]) async {
        guard let outlineJSON = Self.jsonString(outline) else { return }
        let variants: [(Int, Int, Double)] = [(4, 650, 0.22), (6, 850, 0.30), (8, 1050, 0.38)]
        var best: (score: Int, pattern: [String: Any], repair: [String: Any], attempt: Int)?
        for (index, variant) in variants.enumerated() {
            previewAttempts = index + 1
            lastReport = Report(
                verdict: "PROPOSED", phase: "REGIONS_CONFIRMED",
                message: "第二皮膚→型紙→修復を試行中（\(index + 1)/\(variants.count)）",
                iterations: index + 1, modelCalls: 0)
            let pattern = await toolDoor("photo_pattern", [
                "json_text": outlineJSON, "n_panels": variant.0,
                "iterations": variant.1, "dart_depth_ratio": variant.2,
                "preview_mannequin": true,
            ])
            var repair: [String: Any] = [:]
            if (pattern["verdict"] as? String) == "ANSWER",
               let patternJSON = Self.jsonString(pattern) {
                repair = await toolDoor("photo_pattern_repair", [
                    "json_text": patternJSON, "budget": 8,
                ])
            }
            let sewable = repair["sewable"] as? Bool == true
            let pieces = pattern["pieces"] as? [[String: Any]] ?? []
            let score = (sewable ? 10_000 : 0) + pieces.count * 10 - index
            trace.append(.init(round: index + 1, actor: "VERA_PREVIEW_FACTORY",
                               action: "PATTERN_RETRY_\(variant.0)_PANELS",
                               verdict: pattern["verdict"] as? String ?? "UNKNOWN"))
            if (pattern["verdict"] as? String) == "ANSWER",
               best == nil || score > best!.score {
                best = (score, pattern, repair, index + 1)
            }
            await Task.yield()
        }
        guard let best else { return }
        rawPreviewPattern = best.pattern
        var points: [[Double]] = []
        var faces: [[Int]] = []
        var edges: [[Int]] = []
        if let surface = best.pattern["garment_surface"],
           let garmentJSON = Self.jsonString(["garment_surface": surface]) {
            let dressed = await toolDoor("mannequin_dress", [
                "garment_json": garmentJSON, "fabric": "jersey knit",
                "iterations": 400,
            ])
            points = dressed["points"] as? [[Double]] ?? []
            edges = dressed["edges"] as? [[Int]] ?? []
            faces = (surface as? [String: Any])?["faces"] as? [[Int]] ?? []
        }
        let pieces = (best.pattern["pieces"] as? [[String: Any]] ?? []).enumerated().map {
            index, row in
            PreviewPiece(id: (row["piece_id"] as? String) ?? "piece-\(index)",
                         name: (row["name"] as? String) ??
                               (row["piece_id"] as? String) ?? "piece \(index + 1)",
                         outline: row["outline"] as? [[Double]] ?? [])
        }
        let assumptions = [
            "正面一枚から見えない背面と奥行きはAI/幾何候補であり観測事実ではありません。",
            "標準人台はPROPOSEDプレビューで、製造前に実測値へ置換します。",
            "この表示は承認前の探索結果であり、製造承認ではありません。",
        ]
        let repairSummary = (best.repair["sewable"] as? Bool == true)
            ? "幾何的な縫製可能性修復を通過" : "修復候補を保持（製造保証ではありません）"
        outlineCalibrationBaseline = PreviewArtifact(
            state: "PROPOSED", attempt: best.attempt,
            method: "outline calibration only: second-skin → silhouette → panels → bounded repair",
            points: points, faces: faces, edges: edges, pieces: pieces,
            assumptions: assumptions, repairSummary: repairSummary,
            preservesSourceFront: false)
        trace.append(.init(
            round: best.attempt, actor: "VERA_OUTLINE_CALIBRATION_BASELINE",
            action: "KEEP_OUT_OF_CANDIDATE_3D_CHANNEL",
            verdict: "PROPOSED_BASELINE_NOT_A_GARMENT_CANDIDATE"))
    }

    private func simulationInput(from state: [String: Any]) -> [String: Any]? {
        guard let approval = state["material_approval"] as? [String: Any],
              let sheet = state["material_sheet"] as? [String: Any],
              let rows = sheet["candidates"] as? [[String: Any]],
              let selected = rows.first(where: {
                  ($0["candidate_id"] as? String) == (approval["candidate_id"] as? String)
              }) else { return nil }
        let materialID = approval["candidate_id"] as? String
            ?? "approved-preview-material"
        return simulationInput(
            materialCandidate: selected, materialID: materialID,
            basePattern: materialPreviewBasePattern ?? rawPreviewPattern,
            baseArtifact: materialPreviewBaseArtifact ?? previewArtifact)
    }

    private func simulationInput(
        materialCandidate selected: [String: Any], materialID: String,
        basePattern: [String: Any]?, baseArtifact: PreviewArtifact?
    ) -> [String: Any]? {
        let surface = basePattern?["garment_surface"] as? [String: Any]
        let raw = (surface?["verts"] as? [[Double]]) ?? baseArtifact?.points ?? []
        let facesRaw = (surface?["faces"] as? [[Int]]) ?? baseArtifact?.faces ?? []
        guard raw.count >= 3, !facesRaw.isEmpty else { return nil }
        let rest = raw.map { point -> [Double] in
            guard point.count >= 3 else { return [0, 0, 0] }
            return [point[0] / 100.0, point[1] / 100.0, point[2] / 100.0]
        }
        var triangles: [[Int]] = []
        for face in facesRaw where face.count >= 3 {
            for index in 1..<(face.count - 1) { triangles.append([face[0], face[index], face[index + 1]]) }
        }
        guard !triangles.isEmpty else { return nil }
        let profile = (selected["xpbd"] as? [String: Any])
            ?? (selected["material_ranges"] as? [String: Any]) ?? selected
        func number(_ key: String) -> Double? {
            if let value = profile[key] as? Double, value.isFinite { return value }
            if let value = profile[key] as? Int { return Double(value) }
            if let range = profile[key] as? [String: Any] {
                if let nominal = range["nominal"] as? Double { return nominal }
                if let lo = range["min"] as? Double, let hi = range["max"] as? Double {
                    return (lo + hi) / 2
                }
            }
            return nil
        }
        guard let density = number("areal_density_kg_m2"),
              let warp = number("warp_stiffness_n_m"),
              let weft = number("weft_stiffness_n_m"),
              let shear = number("shear_stiffness_n_m"),
              let bending = number("bending_stiffness_n_m"),
              let damping = number("damping_ratio") else { return nil }
        return [
            "schema": "garment.industrial-cloth-step.v1",
            "rest_positions": rest, "faces": triangles,
            "face_material_ids": Array(repeating: materialID, count: triangles.count),
            "materials": ["xpbd": [materialID: [
                "areal_density_kg_m2": density,
                "warp_stiffness_n_m": warp, "weft_stiffness_n_m": weft,
                "shear_stiffness_n_m": shear, "bending_stiffness_n_m": bending,
                "damping_ratio": damping,
            ]]],
            "time_step_s": 1.0 / 60.0,
            "fixed_vertices": Array(0..<min(2, rest.count)),
            "xpbd": ["steps": 4, "solver_iterations": 8],
        ]
    }

    /// Select the body before target fusion. Changing it invalidates cleanup
    /// approval and rebuilds the same-camera target with a new avatar digest.
    func selectBaseAvatar(_ profileID: String) async {
        guard baseAvatarProfiles.contains(where: { $0.id == profileID }) else {
            trace.append(.init(
                round: 0, actor: "VERA_TARGET_RECONSTRUCTION",
                action: "SELECT_BASE_AVATAR",
                verdict: "UNKNOWN_BASE_AVATAR_ID"))
            return
        }
        selectedBaseAvatarID = profileID
        targetCleanupConfirmed = false
        targetSculptRemovedFaces = []
        targetSculptUndoStack = []
        targetSculptRevision &+= 1
        targetSculptClearancePreview = nil
        targetSameCameraComparison = nil
        guard let outline = activeTargetOutline,
              let imagePath = activeTargetImagePath else { return }
        await prepareTargetReconstruction(outline: outline, imagePath: imagePath)
    }

    /// Reversible cleanup. The Python contract decides whether removing a
    /// region creates an UNKNOWN occlusion hole or a display-only body mask.
    func toggleTargetCleanupRegion(_ regionID: String) async {
        guard let artifact = targetReconstruction,
              let region = artifact.regions.first(where: { $0.id == regionID }),
              region.removable else { return }
        if targetRemovedRegionIDs.contains(regionID) {
            targetRemovedRegionIDs.remove(regionID)
        } else {
            targetRemovedRegionIDs.insert(regionID)
        }
        // Region edits rebuild the fused target and therefore need their own
        // monotonically increasing persisted revision. Without this bump the
        // factory would correctly refuse a new digest under an old revision.
        targetSculptRevision &+= 1
        targetCleanupConfirmed = false
        persistedForegroundCleanupDigest = nil
        targetSameCameraComparison = nil
        guard let outline = activeTargetOutline,
              let imagePath = activeTargetImagePath else { return }
        await prepareTargetReconstruction(outline: outline, imagePath: imagePath)
    }

    func confirmTargetCleanup() {
        confirmTargetSculpt()
    }

    /// A brush stroke is one reversible human-authored CAD operation. It only
    /// hides/restores faces in the visual target; it does not rewrite the AI
    /// proposal's provenance or assert that a hidden rear surface was seen.
    func applyTargetSculptFaces(_ faceIndices: Set<Int>, removing: Bool) {
        guard let surface = targetReconstruction?.sculptSurface,
              !faceIndices.isEmpty else { return }
        let valid = Set(faceIndices.filter { surface.faces.indices.contains($0) })
        guard !valid.isEmpty else { return }
        var next = targetSculptRemovedFaces
        if removing { next.formUnion(valid) }
        else { next.subtract(valid) }
        guard next != targetSculptRemovedFaces else { return }
        targetSculptUndoStack.append(targetSculptRemovedFaces)
        if targetSculptUndoStack.count > 80 {
            targetSculptUndoStack.removeFirst(
                targetSculptUndoStack.count - 80)
        }
        targetSculptRemovedFaces = next
        targetSculptRevision &+= 1
        targetCleanupConfirmed = false
        targetSameCameraComparison = nil
        trace.append(.init(
            round: Int(targetSculptRevision), actor: "HUMAN_TARGET_SCULPT",
            action: removing ? "ERASE_3D_FACES" : "RESTORE_3D_FACES",
            verdict: "HUMAN_EDIT_RECORDED"))
        scheduleTargetSculptClearanceSimulation()
    }

    func undoTargetSculptStroke() {
        guard let previous = targetSculptUndoStack.popLast() else { return }
        targetSculptRemovedFaces = previous
        targetSculptRevision &+= 1
        targetCleanupConfirmed = false
        targetSameCameraComparison = nil
        trace.append(.init(
            round: Int(targetSculptRevision), actor: "HUMAN_TARGET_SCULPT",
            action: "UNDO_3D_BRUSH_STROKE", verdict: "HUMAN_EDIT_RECORDED"))
        scheduleTargetSculptClearanceSimulation()
    }

    func resetTargetSculpt() {
        guard !targetSculptRemovedFaces.isEmpty else { return }
        targetSculptUndoStack.append(targetSculptRemovedFaces)
        targetSculptRemovedFaces = []
        targetSculptRevision &+= 1
        targetCleanupConfirmed = false
        targetSameCameraComparison = nil
        scheduleTargetSculptClearanceSimulation()
    }

    /// Apply one bounded proposal-only CAD operation through the typed MCP
    /// modifier.  The operation creates an immutable child mesh revision and
    /// never claims cloth physics, pressure, fit, or manufacturing validity.
    func applyTargetSculptModifier(
        _ kind: String,
        vertexIndices requestedVertexIndices: [Int]? = nil,
        pickedVertexIndex: Int? = nil,
        dragVectorCM requestedDragVectorCM: [Double]? = nil
    ) async {
        guard let surface = targetReconstruction?.sculptSurface else { return }
        let vertices = targetSculptModifierVertices ?? surface.verticesCM
        let keptFaces = surface.faces.indices.filter {
            !targetSculptRemovedFaces.contains($0)
        }
        guard !vertices.isEmpty, !keptFaces.isEmpty else { return }
        let keptVertices = Set(keptFaces.flatMap { faceIndex in
            surface.faces.indices.contains(faceIndex)
                ? surface.faces[faceIndex] : []
        })
        let explicitVertices = Array(Set(requestedVertexIndices ?? []))
            .filter { vertices.indices.contains($0) && keptVertices.contains($0) }
            .sorted()
        let dragVectorCM: [Double]? = {
            guard let vector = requestedDragVectorCM,
                  vector.count == 3,
                  vector.allSatisfy({ $0.isFinite }) else { return nil }
            let length = sqrt(vector.reduce(0) { $0 + $1 * $1 })
            guard length > 1.0e-8 else { return nil }
            let scale = min(8.0 / length, 1.0)
            return vector.map { $0 * scale }
        }()
        let upperKind = kind.uppercased()
        let selection: [String: Any] = explicitVertices.isEmpty
            ? ["face_indices": keptFaces]
            : ["vertex_indices": explicitVertices]
        var modifier: [String: Any] = [
            "kind": upperKind,
            "selection": selection,
        ]
        switch upperKind {
        case "PULL":
            if let dragVectorCM {
                modifier["vector_cm"] = dragVectorCM
            } else {
                modifier["direction"] = "LOCAL_NORMAL"
                modifier["distance_cm"] = 0.6
            }
        case "STRETCH":
            guard explicitVertices.count >= 2,
                  let dragVectorCM,
                  let pickedVertexIndex,
                  explicitVertices.contains(pickedVertexIndex),
                  vertices.indices.contains(pickedVertexIndex),
                  vertices[pickedVertexIndex].count >= 3 else { return }

            var centroid = [0.0, 0.0, 0.0]
            for vertexIndex in explicitVertices {
                guard vertices[vertexIndex].count >= 3 else { continue }
                for axis in 0..<3 {
                    centroid[axis] += vertices[vertexIndex][axis]
                }
            }
            let count = Double(explicitVertices.count)
            centroid = centroid.map { $0 / count }
            let radial = (0..<3).map {
                vertices[pickedVertexIndex][$0] - centroid[$0]
            }
            let radialLength = sqrt(radial.reduce(0) { $0 + $1 * $1 })
            let dragLength = sqrt(dragVectorCM.reduce(0) { $0 + $1 * $1 })
            let outwardDot = zip(dragVectorCM, radial)
                .reduce(0.0) { $0 + $1.0 * $1.1 }
            let shrinking = radialLength > 1.0e-8 && outwardDot < 0
            let axisVector = shrinking ? radial : dragVectorCM
            let axisLength = sqrt(axisVector.reduce(0) { $0 + $1 * $1 })
            guard axisLength > 1.0e-8 else { return }
            let unitAxis = axisVector.map { $0 / axisLength }
            let projected = explicitVertices.compactMap { vertexIndex
                -> (index: Int, value: Double)? in
                guard vertices[vertexIndex].count >= 3 else { return nil }
                return (vertexIndex, (0..<3).reduce(0.0) {
                    $0 + vertices[vertexIndex][$1] * unitAxis[$1]
                })
            }
            guard let minimum = projected.min(by: { $0.value < $1.value }),
                  let maximum = projected.max(by: { $0.value < $1.value })
            else { return }
            let span = max(maximum.value - minimum.value, 0.5)
            let delta = min(0.45, max(0.01, dragLength / span))
            modifier["axis_vector"] = unitAxis
            modifier["anchor_vertex_index"] = minimum.index
            modifier["scale_factor"] = shrinking ? 1.0 - delta : 1.0 + delta
        case "WIND_PREVIEW":
            modifier.removeValue(forKey: "selection")
            modifier["wind_vector_m_s"] = [2.5, 0.0, 0.0]
            modifier["preview_gain_cm_per_m_s"] = 0.08
        default:
            return
        }
        var sculptSurface: [String: Any] = [
            "vertices_cm": vertices,
            "faces": surface.faces,
            "revision": targetSculptModifierRevision,
        ]
        if let targetSculptModifierDigest {
            sculptSurface["digest"] = targetSculptModifierDigest
        }
        var request: [String: Any] = [
            "schema": "garment.target-sculpt-modifier.request.v1",
            "sculpt_surface": sculptSurface,
            "expected_revision": targetSculptModifierRevision,
            "modifier": modifier,
        ]
        if let targetSculptModifierDigest {
            request["expected_digest"] = targetSculptModifierDigest
        }
        guard let jsonText = Self.jsonString(request) else { return }
        let response = await toolDoor(
            "garment_target_sculpt_modifier", ["json_text": jsonText])
        guard response["verdict"] as? String == "PROPOSED_CAD_MODIFIER",
              let child = response["sculpt_surface"] as? [String: Any],
              let nextVertices = child["vertices_cm"] as? [[Double]],
              let nextRevision = child["revision"] as? Int,
              let nextDigest = child["digest"] as? String else {
            let code = response["verdict"] as? String
                ?? "UNKNOWN_TARGET_SCULPT_MODIFIER"
            trace.append(.init(
                round: Int(targetSculptRevision), actor: "VERA_CAD_MODIFIER_MCP",
                action: upperKind, verdict: code))
            return
        }
        targetSculptModifierUndoStack.append((
            vertices: targetSculptModifierVertices,
            revision: targetSculptModifierRevision,
            digest: targetSculptModifierDigest))
        if targetSculptModifierUndoStack.count > 40 {
            targetSculptModifierUndoStack.removeFirst(
                targetSculptModifierUndoStack.count - 40)
        }
        targetSculptModifierVertices = nextVertices
        targetSculptModifierRevision = nextRevision
        targetSculptModifierDigest = nextDigest
        let statistics = response["statistics"] as? [String: Any] ?? [:]
        targetSculptModifierStatus = TargetSculptModifierStatus(
            kind: upperKind,
            verdict: response["verdict"] as? String
                ?? "PROPOSED_CAD_MODIFIER",
            movedVertexCount: statistics["moved_vertex_count"] as? Int ?? 0,
            revision: nextRevision,
            digest: nextDigest,
            undoParentDigest: response["undo_parent_digest"] as? String ?? "",
            limitations: response["limitations"] as? [String] ?? [])
        targetSculptRevision &+= 1
        targetCleanupConfirmed = false
        persistedForegroundCleanupDigest = nil
        targetSameCameraComparison = nil
        trace.append(.init(
            round: Int(targetSculptRevision), actor: "VERA_CAD_MODIFIER_MCP",
            action: upperKind, verdict: "PROPOSED_CAD_MODIFIER"))
        scheduleTargetSculptClearanceSimulation()
    }

    func undoTargetSculptModifier() {
        guard let previous = targetSculptModifierUndoStack.popLast() else {
            return
        }
        targetSculptModifierVertices = previous.vertices
        targetSculptModifierRevision = previous.revision
        targetSculptModifierDigest = previous.digest
        targetSculptModifierStatus = nil
        targetSculptRevision &+= 1
        targetCleanupConfirmed = false
        persistedForegroundCleanupDigest = nil
        targetSameCameraComparison = nil
        scheduleTargetSculptClearanceSimulation()
    }

    var canUndoTargetSculptModifier: Bool {
        !targetSculptModifierUndoStack.isEmpty
    }

    func setTargetSculptThickness(_ millimetres: Double) {
        let bounded = min(12.0, max(0.1, millimetres))
        guard abs(bounded - targetSculptThicknessMM) > 1.0e-9 else { return }
        targetSculptThicknessMM = bounded
        targetSculptRevision &+= 1
        targetCleanupConfirmed = false
        targetSameCameraComparison = nil
        trace.append(.init(
            round: Int(targetSculptRevision), actor: "VERA_THICKNESS_PREVIEW",
            action: "OFFSET_SHELL_\(String(format: "%.2f", bounded))MM",
            verdict: "PROPOSED_GEOMETRIC_CLEARANCE_PREVIEW"))
        scheduleTargetSculptClearanceSimulation()
    }

    func confirmTargetSculpt() {
        guard targetReconstruction?.sculptSurface != nil else { return }
        targetCleanupAuthority = "HUMAN_APPROVED_FOR_FRONT_COMPARISON"
        targetCleanupConfirmed = true
        trace.append(.init(
            round: Int(targetSculptRevision), actor: "HUMAN_TARGET_SCULPT",
            action: "ADOPT_EDITED_FUSED_TARGET_\(targetSculptDigest?.prefix(12) ?? "unknown")",
            verdict: "HUMAN_EDIT_ACCEPTED_FOR_COMPARISON"))
        scheduleTargetSameCameraComparison()
        Task { @MainActor in
            await persistForegroundCleanupAndResume()
        }
    }

    /// Debounce slider/brush traffic before asking the typed deterministic
    /// engine for body penetration and thickness clearance. A stale response
    /// can never overwrite a newer human stroke revision.
    private func scheduleTargetSculptClearanceSimulation() {
        targetSculptClearanceTask?.cancel()
        targetSculptClearancePreview = nil
        guard targetReconstruction?.sculptSurface != nil else { return }
        let expectedRevision = targetSculptRevision
        targetSculptClearanceTask = Task { [weak self] in
            try? await Task.sleep(for: .milliseconds(160))
            guard !Task.isCancelled, let self,
                  self.targetSculptRevision == expectedRevision else { return }
            await self.simulateTargetSculptClearance(
                expectedRevision: expectedRevision)
        }
    }

    private func simulateTargetSculptClearance(
        expectedRevision: UInt64
    ) async {
        guard let surface = targetReconstruction?.sculptSurface,
              targetSculptRevision == expectedRevision else { return }
        let simulationVertices = targetSculptModifierVertices
            ?? surface.verticesCM
        let avatar = selectedBaseAvatar
        let request: [String: Any] = [
            "schema": "garment.target-sculpt-clearance.request.v1",
            "sculpt_surface": [
                "surface_mode": surface.surfaceMode,
                "vertices_cm": simulationVertices,
                "faces": surface.faces,
            ],
            "avatar_measurements_cm": [
                "height": avatar.heightCM,
                "chest_bust": avatar.chestCM,
                "waist": avatar.waistCM,
                "hip": avatar.hipCM,
            ],
            "cloth_thickness_mm": targetSculptThicknessMM,
            "removed_face_indices": targetSculptRemovedFaces.sorted(),
        ]
        guard let jsonText = Self.jsonString(request) else { return }
        let response = await toolDoor(
            "garment_target_sculpt_clearance_simulate",
            ["json_text": jsonText])
        guard !Task.isCancelled,
              targetSculptRevision == expectedRevision,
              response["verdict"] as? String
                == "PROPOSED_GEOMETRIC_CLEARANCE",
              let resolved = response["resolved_vertices_cm"] as? [[Double]],
              resolved.count == surface.verticesCM.count,
              let statistics = response["statistics"] as? [String: Any]
        else { return }
        let faceClearances = (response["face_clearances"]
            as? [[String: Any]] ?? []).compactMap {
                row -> TargetSculptFaceClearance? in
                guard let faceIndex = (row["face_index"] as? NSNumber)?.intValue,
                      let before = (row["minimum_before_mm"]
                        as? NSNumber)?.doubleValue,
                      let after = (row["minimum_after_mm"]
                        as? NSNumber)?.doubleValue,
                      let mean = (row["mean_after_mm"]
                        as? NSNumber)?.doubleValue,
                      let band = row["band"] as? String else { return nil }
                return TargetSculptFaceClearance(
                    faceIndex: faceIndex, minimumBeforeMM: before,
                    minimumAfterMM: after, meanAfterMM: mean, band: band)
            }
        targetSculptClearancePreview = TargetSculptClearancePreview(
            verdict: response["verdict"] as? String
                ?? "PROPOSED_GEOMETRIC_CLEARANCE",
            method: response["method"] as? String
                ?? "AVATAR_ELLIPTIC_CLEARANCE_V1",
            resolvedVerticesCM: resolved,
            collisionFaceIndices:
                response["collision_face_indices"] as? [Int] ?? [],
            faceClearances: faceClearances,
            movedVertexCount: statistics["moved_vertex_count"] as? Int ?? 0,
            minimumClearanceBeforeMM:
                statistics["minimum_clearance_before_mm"] as? Double ?? 0,
            minimumClearanceAfterMM:
                statistics["minimum_clearance_after_mm"] as? Double ?? 0,
            digest: response["clearance_digest"] as? String ?? "",
            limitations: response["limitations"] as? [String] ?? [])
        trace.append(.init(
            round: Int(expectedRevision), actor: "VERA_CLEARANCE_MCP",
            action: "BODY_PENETRATION_AND_THICKNESS",
            verdict: "PROPOSED_GEOMETRIC_CLEARANCE"))
    }

    private func scheduleTargetSameCameraComparison() {
        targetSameCameraTask?.cancel()
        targetSameCameraComparison = nil
        guard targetCleanupConfirmed, previewArtifact != nil,
              targetSculptDigest != nil else { return }
        let expectedRevision = targetSculptRevision
        targetSameCameraTask = Task { [weak self] in
            try? await Task.sleep(for: .milliseconds(80))
            guard !Task.isCancelled, let self,
                  self.targetCleanupConfirmed,
                  self.targetSculptRevision == expectedRevision else { return }
            await self.compareHumanTargetToCurrentPreview(
                expectedRevision: expectedRevision)
        }
    }

    private func compareHumanTargetToCurrentPreview(
        expectedRevision: UInt64
    ) async {
        guard targetCleanupConfirmed,
              targetSculptRevision == expectedRevision,
              let target = targetReconstruction,
              let outline = activeTargetOutline,
              let targetOutline = (outline["outline"] as? [[Double]])
                ?? (outline["points"] as? [[Double]]),
              targetOutline.count >= 3,
              let width = (outline["width_px"] as? NSNumber)?.doubleValue
                ?? (outline["width"] as? NSNumber)?.doubleValue,
              let height = (outline["height_px"] as? NSNumber)?.doubleValue
                ?? (outline["height"] as? NSNumber)?.doubleValue,
              let humanEditDigest = targetSculptDigest,
              let candidate = previewArtifact,
              !candidate.points.isEmpty, !candidate.faces.isEmpty
        else { return }
        let avatar = selectedBaseAvatar
        let request: [String: Any] = [
            "schema": "garment.same-camera-projection.request.v1",
            "camera_digest": target.cameraDigest,
            "base_avatar": [
                "avatar_id": avatar.id,
                "geometry_digest": avatar.geometryDigest,
            ],
            "target": [
                "target_digest": target.targetDigest,
                "state": "HUMAN_CONFIRMED_TARGET",
                "human_edit_digest": humanEditDigest,
                "width_px": width,
                "height_px": height,
                "outline": targetOutline,
            ],
            "candidate": [
                "candidate_id": "current-preview-\(candidate.attempt)",
                "vertices": candidate.points,
                "faces": candidate.faces,
            ],
            "raster_size": 64,
            "round_index": 1,
        ]
        guard let jsonText = Self.jsonString(request) else { return }
        let response = await toolDoor(
            "garment_same_camera_projection_prepare", ["json_text": jsonText])
        guard !Task.isCancelled,
              targetCleanupConfirmed,
              targetSculptRevision == expectedRevision,
              response["verdict"] as? String
                == "PROPOSED_SAME_CAMERA_COMPARISON",
              let evaluation = response["evaluation"] as? [String: Any],
              let convergence = evaluation["convergence"] as? [String: Any]
        else { return }
        let axes = evaluation["axes"] as? [String: Any]
        let silhouette = axes?["silhouette"] as? [String: Any]
        targetSameCameraComparison = TargetSameCameraComparison(
            verdict: response["verdict"] as? String
                ?? "PROPOSED_SAME_CAMERA_COMPARISON",
            convergenceStatus: convergence["status"] as? String ?? "UNKNOWN",
            silhouetteIOU: silhouette?["iou"] as? Double,
            proposalCount: (evaluation["proposals"] as? [Any])?.count ?? 0,
            comparisonDigest: response["comparison_digest"] as? String ?? "",
            referenceAuthority: evaluation["reference_authority"] as? String
                ?? "HUMAN_CONFIRMED_TARGET")
        trace.append(.init(
            round: Int(expectedRevision), actor: "VERA_SAME_CAMERA_MCP",
            action: "COMPARE_HUMAN_TARGET_TO_CURRENT_3D",
            verdict: convergence["status"] as? String ?? "UNKNOWN"))
    }

    /// External providers plug in above this boundary by supplying a mesh
    /// artifact digest. The first implementation deliberately uses the
    /// deterministic silhouette fallback; provider absence never turns into
    /// a fabricated high-detail mesh.
    private func prepareTargetReconstruction(
        outline: [String: Any], imagePath: String,
        externalMesh: [String: Any]? = nil,
        externalProvider: String? = nil
    ) async {
        activeTargetOutline = outline
        activeTargetImagePath = imagePath
        let imageDigest: String
        if let bytes = try? Data(contentsOf: URL(fileURLWithPath: imagePath)) {
            imageDigest = Self.sha256(bytes)
        } else {
            imageDigest = Self.sha256(Data(imagePath.utf8))
        }
        let outlineText = Self.jsonString(outline) ?? "{}"
        let outlineDigest = Self.sha256(Data(outlineText.utf8))
        let cameraDigest = (outline["camera_digest"] as? String)
            ?? Self.sha256(Data("front-camera:\(imageDigest)".utf8))
        let avatar = selectedBaseAvatar
        let fusedTargetOutline = outline["fused_target_outline"] as? [[Double]]
        let hasFusedForegroundTarget = (fusedTargetOutline?.count ?? 0) >= 3

        var regions: [[String: Any]] = [
            ["id": "background", "label": "背景", "class": "BACKGROUND",
             "state": "OBSERVED"],
            ["id": "hair", "label": "髪", "class": "HAIR",
             "state": "PROPOSED", "occludes_garment": true,
             "overlap_part_ids": ["front-garment-surface"]],
            ["id": "source-body", "label": "元画像の身体", "class": "BODY",
             "state": "PROPOSED", "occludes_garment": false],
            ["id": "front-garment-surface", "label": "服の目標表面",
             "class": "GARMENT", "state": "PROPOSED"],
        ]
        if let observed = outline["regions"] as? [[String: Any]] {
            let labels = observed.compactMap {
                ($0["label"] as? String)?.lowercased()
                    ?? ($0["part_id"] as? String)?.lowercased()
            }
            if labels.contains(where: { $0.contains("hair") || $0.contains("髪") }) {
                regions[1]["state"] = "OBSERVED"
            }

            // The old fused-target bridge kept only the combined horizontal
            // envelope.  That joined a blouse, two trouser legs and an
            // asymmetric overlay across empty pixels and produced the large
            // cyan cage seen when the target was rotated.  Preserve each
            // RegionPicker component as its own PROPOSED/OBSERVED front
            // surface.  The Python geometry boundary still decides whether a
            // loop is valid; Swift never promotes a proposed component here.
            for (index, component) in observed.enumerated() {
                guard let componentOutline = component["outline"] as? [[Double]],
                      componentOutline.count >= 3 else { continue }
                let sourceID = (component["region_id"] as? String)
                    ?? (component["id"] as? String)
                    ?? "region-\(index)"
                let state = (component["state"] as? String)?.uppercased()
                    ?? "PROPOSED"
                var row: [String: Any] = [
                    "id": "front-garment-component:\(sourceID)",
                    "label": (component["label"] as? String) ?? sourceID,
                    "class": "GARMENT",
                    "state": state == "OBSERVED" ? "OBSERVED" : "PROPOSED",
                    "outline": componentOutline,
                    "part_id": (component["part_id"] as? String) ?? sourceID,
                    "side": (component["side"] as? String) ?? "unspecified",
                    "layer": (component["layer"] as? Int) ?? 0,
                ]
                if let garmentUnit = component["garment_unit"] as? String {
                    row["garment_unit"] = garmentUnit
                }
                if let semanticRole = (component["semantic_role"] as? String)
                    ?? (component["detail_role"] as? String) {
                    row["semantic_role"] = semanticRole
                }
                if let rgba = component["average_rgba"] as? [String: Any] {
                    row["average_rgba"] = rgba
                }
                regions.append(row)
            }
        }
        let reconstruction: [String: Any]
        if let externalMesh {
            reconstruction = [
                "provider": externalProvider ?? "external-single-view-provider",
                "mesh": externalMesh,
            ]
        } else {
            let fallbackOutline = hasFusedForegroundTarget
                ? (fusedTargetOutline ?? [])
                : ((outline["outline"] as? [[Double]])
                    ?? (outline["points"] as? [[Double]]) ?? [])
            let fallbackWidth = hasFusedForegroundTarget
                ? (outline["fused_target_width_px"] ?? outline["width_px"] ?? 1)
                : (outline["width_px"] ?? 1)
            let fallbackHeight = hasFusedForegroundTarget
                ? (outline["fused_target_height_px"] ?? outline["height_px"] ?? 1)
                : (outline["height_px"] ?? 1)
            reconstruction = [
                "fallback": [
                    "silhouette_digest": outlineDigest,
                    "point_count": fallbackOutline.count,
                    "outline": fallbackOutline,
                    "width_px": fallbackWidth,
                    "height_px": fallbackHeight,
                    "target_role": hasFusedForegroundTarget
                        ? "FUSED_PERSON_AND_GARMENT_CAD_TARGET"
                        : "GARMENT_COMPONENT_PROPOSAL",
                    "selection_mode": hasFusedForegroundTarget
                        ? "FOREGROUND_SUBJECT_MASK"
                        : "DETERMINISTIC_GARMENT_COMPONENT_RANKING",
                    "authority": "PROPOSED",
                    "source": hasFusedForegroundTarget
                        ? (outline["fused_target_source"]
                            ?? "salient foreground subject mask")
                        : (outline["source"] ?? "proposed garment component mask"),
                ],
            ]
        }
        let request: [String: Any] = [
            "schema": "garment.target-reconstruction.request.v1",
            "source": ["image_digest": imageDigest],
            "camera_digest": cameraDigest,
            "base_avatar": [
                "avatar_id": avatar.id,
                "kind": "PARAMETRIC_GAME_AVATAR",
                "authority": avatar.authority,
                "geometry_digest": avatar.geometryDigest,
                "measurements_cm": [
                    "height": avatar.heightCM, "chest_bust": avatar.chestCM,
                    "waist": avatar.waistCM, "hip": avatar.hipCM,
                ],
                "render_lod": "HIGH",
            ],
            "reconstruction": reconstruction,
            "regions": regions,
            "edits": ["remove_region_ids": targetRemovedRegionIDs.sorted()],
            "body_garment_boundary_state": "UNKNOWN",
        ]
        guard let jsonText = Self.jsonString(request) else { return }
        let response = await toolDoor(
            "garment_target_reconstruction_prepare", ["json_text": jsonText])
        guard (response["verdict"] as? String) == "PROPOSED_TARGET_RECONSTRUCTION",
              let responseRegions = response["regions"] as? [[String: Any]],
              let targetDigest = response["target_digest"] as? String,
              let stage = response["stage"] as? String else {
            targetReconstruction = nil
            resetTargetSculptModifierState()
            visionPipelineReviewItems = Self.uniqueRequirementItems(
                visionPipelineReviewItems + [[
                    "code": response["verdict"] as? String
                        ?? "UNKNOWN_TARGET_RECONSTRUCTION",
                    "state": "REVIEW",
                    "why": response["why"] as? String
                        ?? "融合目標立体を準備できませんでした。",
                    "manufacturing_ready": false,
                ]])
            return
        }
        resetTargetSculptModifierState()
        let reconstructionResponse = response["reconstruction"] as? [String: Any] ?? [:]
        let reviewRows = response["review_items"] as? [[String: Any]] ?? []
        func parsedSurface(_ value: Any?) -> TargetSculptSurface? {
            guard let row = value as? [String: Any],
                  let vertices = row["vertices_cm"] as? [[Double]],
                  let faces = row["faces"] as? [[Int]],
                  !vertices.isEmpty, !faces.isEmpty else { return nil }
            return TargetSculptSurface(
                source: row["source"] as? String ?? "PROPOSED_TARGET_SURFACE",
                state: row["state"] as? String ?? "PROPOSED",
                surfaceMode: row["surface_mode"] as? String
                    ?? "AVATAR_ENVELOPE",
                verticesCM: vertices,
                textureCoordinates:
                    row["texture_coordinates"] as? [[Double]] ?? [],
                faces: faces,
                faceRegionIDs: row["face_region_ids"] as? [String] ?? [],
                faceComponentIDs:
                    row["face_component_ids"] as? [String] ?? [],
                limitations: row["limitations"] as? [String] ?? [])
        }
        let sculptSurface = parsedSurface(response["sculpt_surface"])
        let garmentComponentSurface = parsedSurface(
            response["garment_component_surface"])
        targetReconstruction = TargetReconstructionArtifact(
            targetDigest: targetDigest,
            sourceKind: reconstructionResponse["source_kind"] as? String
                ?? "GEOMETRIC_FRONT_FALLBACK",
            providerConnected: reconstructionResponse["provider_connected"] as? Bool
                ?? false,
            stage: stage,
            cameraDigest: response["camera_digest"] as? String ?? cameraDigest,
            baseAvatarID: (response["base_avatar"] as? [String: Any])?["avatar_id"]
                as? String ?? avatar.id,
            regions: responseRegions.compactMap { row in
                guard let id = row["id"] as? String,
                      let label = row["label"] as? String,
                      let regionClass = row["class"] as? String else { return nil }
                return TargetCleanupRegion(
                    id: id, label: label, regionClass: regionClass,
                    state: row["state"] as? String ?? "PROPOSED",
                    removable: row["removable"] as? Bool ?? false,
                    removed: row["removed"] as? Bool ?? false,
                    occludesGarment: row["occludes_garment"] as? Bool ?? false)
            },
            occlusionHoleCount: (response["occlusion_holes"] as? [Any])?.count ?? 0,
            proposedCompletionCount:
                (response["completion_proposals"] as? [Any])?.count ?? 0,
            reviewCodes: reviewRows.compactMap { $0["code"] as? String },
            garmentExtractionReady: response["garment_extraction_ready"] as? Bool
                ?? false,
            sculptSurface: sculptSurface,
            garmentComponentSurface: garmentComponentSurface)
        trace.append(.init(
            round: 0, actor: "VERA_TARGET_RECONSTRUCTION_MCP",
            action: "AVATAR_FUSE_CLEANUP_TARGET",
            verdict: stage))
        scheduleTargetSculptClearanceSimulation()
    }

    private func resetTargetSculptModifierState() {
        targetSculptModifierVertices = nil
        targetSculptModifierRevision = 0
        targetSculptModifierDigest = nil
        targetSculptModifierUndoStack = []
        targetSculptModifierStatus = nil
    }

    private static func sha256(_ data: Data) -> String {
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }

    private static func jsonString(_ value: Any) -> String? {
        guard JSONSerialization.isValidJSONObject(value),
              let data = try? JSONSerialization.data(withJSONObject: value,
                                                     options: [.sortedKeys]) else { return nil }
        return String(data: data, encoding: .utf8)
    }

    private static func proceduralRetrieval(evidence: [String: Any]) -> [String: Any] {
        let structureA: [String: Any] = [
            "schema": "garment.structure.v1",
            "nodes": [["node_id": "second-skin-shell", "kind": "BODY_SHELL",
                       "dimensions": ["height_cm": 95.0, "circumference_cm": 96.0],
                       "attributes": ["back_design": "center-back opening"]]],
            "operations": [],
        ]
        let structureB: [String: Any] = [
            "schema": "garment.structure.v1",
            "nodes": [
                ["node_id": "second-skin-shell", "kind": "BODY_SHELL",
                 "dimensions": ["height_cm": 95.0, "circumference_cm": 96.0],
                 "attributes": ["back_design": "closed back"]],
                ["node_id": "back-overlay", "kind": "OVERLAY",
                 "dimensions": ["height_cm": 58.0, "width_cm": 52.0],
                 "attributes": ["placement": "back", "layer": "outer"]],
            ], "operations": [],
        ]
        let assumptions = ["背面は正面画像から観測できないためPROPOSED", "寸法は仮人台に基づく"]
        return [
            "verdict": "ANSWER",
            "source": [
                "name": "photoloset:procedural-geometry-v1",
                "modality": "structure_embedding",
                "license": "project-generated procedural output; no third-party corpus record",
                "lineage": ["photoloset-second-skin", "human-confirmed-outline"],
                "rights": ["commercial": true, "derivatives": true,
                           "external_copyrighted_record": false],
            ],
            "hits": [
                ["part_id": "garment", "region_id": "confirmed-clothing",
                 "reference": "procedural:second-skin-opening", "score": 1.0,
                 "visual_cues": ["route": "confirmed outline + second skin"]],
                ["part_id": "garment", "region_id": "confirmed-clothing",
                 "reference": "procedural:second-skin-overlay", "score": 0.95,
                 "visual_cues": ["route": "confirmed outline + geometric overlay"]],
            ],
            "hypotheses": [
                ["candidate_id": "procedural-opening-back",
                 "back_design": "center-back opening", "structure": structureA,
                 "assumptions": assumptions, "evidence_scope": evidence["front_only"] ?? true],
                ["candidate_id": "procedural-overlay-back",
                 "back_design": "closed back with overlay", "structure": structureB,
                 "assumptions": assumptions, "evidence_scope": evidence["front_only"] ?? true],
            ],
        ]
    }

    private static func hasTypedMaterialParameters(_ payload: [String: Any]) -> Bool {
        guard let rows = payload["candidates"] as? [[String: Any]], rows.count >= 2 else {
            return false
        }
        let required = ["areal_density_kg_m2", "warp_stiffness_n_m",
                        "weft_stiffness_n_m", "shear_stiffness_n_m",
                        "bending_stiffness_n_m", "damping_ratio"]
        return rows.allSatisfy { row in
            let profile = (row["xpbd"] as? [String: Any])
                ?? (row["material_ranges"] as? [String: Any]) ?? row
            return required.allSatisfy { profile[$0] is NSNumber
                || profile[$0] is [String: Any] }
        }
    }

    private static func proceduralMaterialCandidates() -> [[String: Any]] {
        [
            ["candidate_id": "jersey-like-preview", "label": "jersey-like",
             "state": "PROPOSED", "source": "engineering preview range; not measured",
             "xpbd": ["areal_density_kg_m2": 0.20,
                      "warp_stiffness_n_m": 420.0, "weft_stiffness_n_m": 360.0,
                      "shear_stiffness_n_m": 65.0, "bending_stiffness_n_m": 0.010,
                      "damping_ratio": 0.045]],
            ["candidate_id": "melton-like-preview", "label": "melton-like",
             "state": "PROPOSED", "source": "engineering preview range; not measured",
             "xpbd": ["areal_density_kg_m2": 0.48,
                      "warp_stiffness_n_m": 1150.0, "weft_stiffness_n_m": 980.0,
                      "shear_stiffness_n_m": 180.0, "bending_stiffness_n_m": 0.065,
                      "damping_ratio": 0.075]],
        ]
    }

    /// Consume the consent only when the proposal call is about to be made.
    /// Returning this envelope does not clear the unresolved request: only a
    /// validated engine result may acknowledge it.
    func consumeOneTimeLLMProposalConsent(
        requestID: String
    ) -> [String: Any]? {
        guard var consent = activeLLMProposalConsent,
              consent.requestID == requestID,
              consent.projectName == activeResolutionProject,
              consent.remainingUses > 0,
              !locallyRevokedConsentDigests.contains(
                consent.engineConsentDigest),
              pendingResolutionRequest?.provenanceDigest
                == consent.subjectDigest else { return nil }
        consent.remainingUses -= 1
        activeLLMProposalConsent = consent.remainingUses > 0 ? consent : nil
        return [
            "schema": consent.schema,
            "request_id": consent.requestID,
            "stage": consent.stage,
            "by": consent.grantedBy,
            "subject_digest": consent.subjectDigest,
            "consent_digest": consent.engineConsentDigest,
            "bound_workflow_digest": consent.boundWorkflowDigest,
            "authority_ceiling": consent.authorityCeiling,
            "maximum_uses": consent.maximumUses,
            "fact_promotions": [],
            "may_claim_observed": false,
            "may_claim_measured": false,
            "may_approve": false,
        ]
    }

    private func validatedPendingRequest(
        requestID: String, provenanceDigest: String, projectName: String,
        requiredAction: ResolutionActionKind
    ) -> FactoryResolutionRequest? {
        guard projectName == activeResolutionProject,
              let request = pendingResolutionRequest,
              request.id == requestID,
              request.provenanceDigest == provenanceDigest,
              request.options.contains(where: { $0.kind == requiredAction })
        else { return nil }
        return request
    }

    private func requestStillMatches(
        _ request: FactoryResolutionRequest, projectName: String
    ) -> Bool {
        activeResolutionProject == projectName
            && pendingResolutionRequest?.id == request.id
            && pendingResolutionRequest?.provenanceDigest
                == request.provenanceDigest
    }

    private static func actionKind(
        for path: CrossResolutionPath
    ) -> ResolutionActionKind {
        switch path {
        case .humanInput, .measuredInput: return .humanInput
        case .humanEdit: return .humanGeometryEdit
        case .connectProvider: return .connectProvider
        case .consentedLLMProposal: return .allowOneTimeLLMProposal
        case .boundedAlternatives: return .compareBoundedAlternatives
        case .typedStop: return .typedStop
        }
    }

    private static func sourceType(for path: CrossResolutionPath) -> String {
        switch path {
        case .humanInput: return "HUMAN_ENTERED_NOT_IMAGE_OBSERVED"
        case .measuredInput: return "HUMAN_MEASUREMENT"
        case .humanEdit: return "HUMAN_GEOMETRY_EDIT"
        case .connectProvider: return "HUMAN_PROVIDER_CONNECTION_REQUEST"
        case .consentedLLMProposal: return "LLM"
        case .boundedAlternatives: return "HUMAN_BOUNDED_ALTERNATIVES"
        case .typedStop: return "HUMAN_TYPED_STOP"
        }
    }

    private static func isModelResolutionActor(_ actor: String) -> Bool {
        let token = actor.uppercased()
        return ["LLM", "MODEL", "AGENT", "QWEN", "GPT", "CLAUDE",
                "GEMINI", "OLLAMA", "LM STUDIO"]
            .contains { token.contains($0) }
    }

    private static func integer(_ value: Any?) -> Int? {
        if let value = value as? Int { return value }
        if let value = value as? NSNumber { return value.intValue }
        return nil
    }

    private static func stringSet(_ value: Any?) -> Set<String> {
        if let values = value as? [String] { return Set(values) }
        if let values = value as? [Any] {
            return Set(values.compactMap { $0 as? String })
        }
        return []
    }

    private static func hasOpenObligation(
        _ requestID: String, in workflow: [String: Any]
    ) -> Bool {
        (workflow["obligations"] as? [[String: Any]] ?? []).contains { row in
            row["request_id"] as? String == requestID
                && (row["status"] as? String ?? "OPEN").uppercased() == "OPEN"
        }
    }

    private static func persistedConsent(
        _ consentDigest: String, requestID: String,
        projectRequest request: FactoryResolutionRequest, actor: String,
        in state: [String: Any]
    ) -> [String: Any]? {
        guard let workflow = state["cross_workflow"] as? [String: Any] else {
            return nil
        }
        return (workflow["consents"] as? [[String: Any]] ?? []).first { row in
            row["consent_digest"] as? String == consentDigest
                && row["request_id"] as? String == requestID
                && row["scope"] as? String == request.stage
                && row["granted_by"] as? String == actor
                && (row["authority_ceiling"] as? String)?.uppercased()
                    == "PROPOSED"
                && row["may_promote_to_observed"] as? Bool == false
                && stringSet(row["fields"]) == Set(request.missingFields)
        }
    }

    private static func persistedResolution(
        request: FactoryResolutionRequest, projectName: String,
        path: CrossResolutionPath, actor: String, values: [String: Any],
        consentDigest: String?, in state: [String: Any]
    ) -> [String: Any]? {
        guard let workflow = state["cross_workflow"] as? [String: Any] else {
            return nil
        }
        return (workflow["resolutions"] as? [[String: Any]] ?? []).last { row in
            guard row["request_id"] as? String == request.id,
                  row["resolution_path"] as? String == path.rawValue,
                  row["actor"] as? String == actor,
                  let resolutionDigest = row["resolution_digest"] as? String,
                  !resolutionDigest.isEmpty,
                  let provenance = row["provenance"] as? [String: Any],
                  provenance["request_provenance_digest"] as? String
                    == request.provenanceDigest,
                  provenance["project_name"] as? String == projectName else {
                return false
            }
            if !values.isEmpty,
               stringSet(row["fields"]) != Set(values.keys) {
                return false
            }
            guard let consentDigest else { return true }
            return row["consent_digest"] as? String == consentDigest
        }
    }

    private static func resolutionKind(_ raw: Any?) -> ResolutionActionKind? {
        guard let token = raw as? String else { return nil }
        switch token.uppercased() {
        case "HUMAN_INPUT", "MEASURED_INPUT", "MEASURE", "ENTER_VALUE":
            return .humanInput
        case "HUMAN_GEOMETRY_EDIT", "HUMAN_EDIT", "CAD_EDIT", "EDIT_GEOMETRY":
            return .humanGeometryEdit
        case "CONNECT_PROVIDER", "PROVIDER_CONNECT": return .connectProvider
        case "LLM_PROPOSAL_WITH_CONSENT", "CONSENTED_LLM_PROPOSAL",
             "ALLOW_LLM_PROPOSAL": return .allowOneTimeLLMProposal
        case "COMPARE_BOUNDED_ALTERNATIVES", "BOUNDED_ALTERNATIVES", "KEEP_UNKNOWN",
             "USE_BOUNDED_CANDIDATES": return .compareBoundedAlternatives
        case "TYPED_STOP", "STOP": return .typedStop
        default: return nil
        }
    }

    private static func resolutionOption(
        _ kind: ResolutionActionKind, code: String, stage: String
    ) -> ResolutionOption {
        let title: String
        let detail: String
        let authority: String
        switch kind {
        case .humanInput:
            title = "値を入力・計測する"
            detail = "画像から測れない値を人が入力します。入力値は画像実測とは区別して記録されます。"
            authority = "USER_SUPPLIED_NOT_IMAGE_MEASURED"
        case .humanGeometryEdit:
            title = "3D/CADで形を直す"
            detail = "点・面・輪郭を人が編集し、編集結果を新しい比較目標として再検証します。"
            authority = "HUMAN_EDITED_TARGET"
        case .connectProvider:
            title = "検索・解析プロバイダを接続する"
            detail = "実在資料や外部解析を使う場合は、到達性・権利・系譜を確認して接続します。"
            authority = "PROVIDER_EVIDENCE_SUBJECT_TO_RIGHTS_GATE"
        case .allowOneTimeLLMProposal:
            title = "今回だけAIの推測案を許可する"
            detail = "AIは候補だけを生成します。観測・実測・承認・製造保証には昇格しません。"
            authority = "PROPOSED_UNOBSERVED_ONLY"
        case .compareBoundedAlternatives:
            title = "不明のまま候補を比較する"
            detail = "本当の値を確定せず、範囲付きの複数候補として3D・型紙・シミュレーションを比較します。"
            authority = "PROPOSED_UNOBSERVED_ALTERNATIVES"
        case .typedStop:
            title = "ここで停止する"
            detail = "解けなかった工程・不足値・根拠を型付きで保存して停止します（\(code) / \(stage)）。"
            authority = "TYPED_STOP_NO_RESULT_CLAIM"
        }
        return .init(
            id: "\(stage):\(code):\(kind.rawValue)", kind: kind,
            title: title, detail: detail,
            requiresExplicitConsent: kind == .allowOneTimeLLMProposal,
            resultAuthority: authority)
    }

    private func inferredResolutionKinds(
        code: String, stage: String
    ) -> [ResolutionActionKind] {
        let token = "\(code)_\(stage)".uppercased()
        let engineFailure = ["SCHEMA", "ENCODING", "ENGINE_RESPONSE",
                             "FACTORY_PHASE", "NO_PROGRESS", "STALE_DIGEST"]
            .contains { token.contains($0) }
        if engineFailure { return [.typedStop] }
        if token.contains("IMAGE") && token.contains("CONFIRM") {
            return [.humanInput, .typedStop]
        }
        if token.contains("AUDIT") || token.contains("APPROVAL") {
            return [.humanInput, .compareBoundedAlternatives, .typedStop]
        }
        if token.contains("FOREGROUND") || token.contains("CLEANUP")
            || token.contains("CAD") || token.contains("GEOMETRY")
            || token.contains("TARGET") {
            return [.humanGeometryEdit, .allowOneTimeLLMProposal,
                    .compareBoundedAlternatives, .typedStop]
        }
        if token.contains("RETRIEVAL") || token.contains("CORPUS")
            || token.contains("PROVIDER") || token.contains("SEARCH")
            || token.contains("FASHION") {
            return [.connectProvider, .allowOneTimeLLMProposal,
                    .compareBoundedAlternatives, .typedStop]
        }
        if token.contains("MATERIAL") || token.contains("SIMULATION")
            || token.contains("DIMENSION") || token.contains("MEASUREMENT")
            || token.contains("UNIT") || token.contains("BODY") {
            return [.humanInput, .allowOneTimeLLMProposal,
                    .compareBoundedAlternatives, .typedStop]
        }
        if token.contains("MODEL") {
            return [.connectProvider, .allowOneTimeLLMProposal, .typedStop]
        }
        if token.contains("BUDGET") || token.contains("UNSUPPORTED") {
            return [.typedStop]
        }
        return [.humanInput, .allowOneTimeLLMProposal,
                .compareBoundedAlternatives, .typedStop]
    }

    private func resolutionRequest(
        verdict: String, stage: String, message: String,
        context: [String: Any]?
    ) -> FactoryResolutionRequest? {
        let embedded = Self.openResolutionEnvelope(in: context)
        let shouldPause = verdict.hasPrefix("UNKNOWN_")
            || verdict.hasPrefix("ESCALATE_")
            || verdict.hasPrefix("REVIEW_")
            || verdict.contains("REQUIRED")
            || embedded != nil
            || verdict == "FRONT_FACTS_RECORDED"
        guard shouldPause else { return nil }

        let code = embedded?["verdict"] as? String
            ?? embedded?["code"] as? String ?? verdict
        let resolvedStage = embedded?["stage"] as? String ?? stage
        var missing = Self.stringArray(embedded?["missing_fields"])
        if missing.isEmpty {
            missing = Self.stringArray(context?["missing_fields"])
        }
        if missing.isEmpty {
            missing = Self.stringArray(context?["required_fields"])
        }
        var kinds = (embedded?["resolution_paths"] as? [[String: Any]] ?? [])
            .compactMap { Self.resolutionKind($0["path"]) }
        if kinds.isEmpty {
            kinds = (embedded?["choices"] as? [[String: Any]] ?? [])
                .compactMap { Self.resolutionKind($0["choice"]) }
        }
        if kinds.isEmpty {
            kinds = (embedded?["options"] as? [[String: Any]] ?? [])
            .compactMap { Self.resolutionKind($0["action"] ?? $0["kind"]) }
        }
        if kinds.isEmpty {
            kinds = ((embedded?["allowed_resolution_kinds"] as? [String])
                ?? (context?["allowed_resolution_kinds"] as? [String]) ?? [])
                .compactMap { Self.resolutionKind($0) }
        }
        if kinds.isEmpty {
            kinds = inferredResolutionKinds(code: code, stage: resolvedStage)
        }
        // Deterministic de-duplication preserves the engine's preferred order.
        var seen = Set<ResolutionActionKind>()
        kinds = kinds.filter { seen.insert($0).inserted }
        if kinds.isEmpty { kinds = [.typedStop] }

        let requestIDSeed = embedded?["request_id"] as? String ?? ""
        let provenanceText = Self.jsonString(
            embedded?["provenance"] as? [String: Any] ?? [:]) ?? "{}"
        let fallbackUpstreamDigest = (context?["provenance_digest"] as? String)
            ?? (context?["state_digest"] as? String)
            ?? (context?["digest"] as? String)
            ?? activeVisibleAnalysisDigest ?? targetSculptDigest
            ?? "NO_UPSTREAM_DIGEST"
        let digestInput = [requestIDSeed, resolvedStage, code,
                           provenanceText, fallbackUpstreamDigest]
            .joined(separator: "|")
        let computedDigest = Self.sha256(Data(digestInput.utf8))
        let digest = embedded?["provenance_digest"] as? String
            ?? computedDigest
        let requestID = requestIDSeed.isEmpty
            ? "resolution-\(computedDigest.prefix(20))" : requestIDSeed
        let options = kinds.map {
            Self.resolutionOption($0, code: code, stage: resolvedStage)
        }
        return .init(
            id: requestID,
            code: code,
            stage: resolvedStage,
            title: embedded?["title"] as? String ?? "次の工程に必要な確認",
            explanation: embedded?["reason"] as? String
                ?? embedded?["why"] as? String
                ?? embedded?["explanation"] as? String
                ?? context?["why"] as? String
                ?? message,
            missingFields: missing.sorted(),
            options: options,
            provenanceDigest: digest,
            authority: embedded?["authority"] as? String
                ?? "UNRESOLVED_WITH_TYPED_CONTINUATIONS",
            terminal: options.allSatisfy { $0.kind == .typedStop })
    }

    private static func openResolutionEnvelope(
        in context: [String: Any]?
    ) -> [String: Any]? {
        guard let context else { return nil }
        for key in ["resolution_request", "typed_resolution_request"] {
            if let row = context[key] as? [String: Any], !row.isEmpty {
                return row
            }
        }
        let root = context["state"] as? [String: Any] ?? context
        guard let workflow = root["cross_workflow"] as? [String: Any] else {
            return nil
        }
        return (workflow["obligations"] as? [[String: Any]] ?? [])
            .last { row in
                (row["status"] as? String ?? "OPEN").uppercased() == "OPEN"
            }
    }

    private static func stringArray(_ value: Any?) -> [String] {
        if let values = value as? [String] { return values }
        if let values = value as? [Any] {
            return values.compactMap { $0 as? String }
        }
        return []
    }

    private func finish(_ verdict: String, phase: String, message: String,
                        rounds: Int, modelCalls: Int,
                        context: [String: Any]? = nil) -> Report {
        self.phase = phase
        pendingResolutionRequest = resolutionRequest(
            verdict: verdict, stage: phase, message: message, context: context)
        if pendingResolutionRequest == nil {
            activeLLMProposalConsent = nil
            selectedResolutionAction = nil
        } else if activeLLMProposalConsent?.subjectDigest
                    != pendingResolutionRequest?.provenanceDigest {
            // A one-shot consent is never transferable to another obligation.
            activeLLMProposalConsent = nil
        }
        let report = Report(verdict: verdict, phase: phase, message: message,
                            iterations: rounds, modelCalls: modelCalls)
        lastReport = report
        return report
    }

    private func clearCandidatePreviewArtifacts() {
        previewArtifact = nil
        candidateManufacturingPreview = nil
        candidateSewingPlan = nil
        candidateMaterialPreview = nil
        rawPreviewPattern = nil
        materialPreviewBasePattern = nil
        materialPreviewBaseArtifact = nil
    }

    private func publishCandidates(from state: [String: Any]) {
        if let sheet = state["hypothesis_sheet"] as? [String: Any],
           let rows = sheet["candidates"] as? [[String: Any]] {
            shapeCandidatePayloads = Dictionary(uniqueKeysWithValues: rows.compactMap { row in
                guard let id = row["candidate_id"] as? String else { return nil }
                return (id, row)
            })
        } else {
            shapeCandidatePayloads = [:]
        }
        if let sheet = state["material_sheet"] as? [String: Any],
           let rows = sheet["candidates"] as? [[String: Any]] {
            materialCandidatePayloads = Dictionary(
                uniqueKeysWithValues: rows.compactMap { row in
                    guard let id = row["candidate_id"] as? String else { return nil }
                    return (id, row)
                })
        } else {
            materialCandidatePayloads = [:]
        }
        shapeCandidates = Self.candidates(
            sheet: state["hypothesis_sheet"], titleKey: "back_design")
        // The persisted factory sheet owns approval, while the image-bound
        // geometry harness owns the richer preview. Bind them by original id
        // when possible and by deterministic candidate order otherwise.
        for (index, candidate) in shapeCandidates.enumerated()
            where geometricRearCandidateArtifacts[candidate.id] == nil
                && index < geometricRearCandidateArtifactsInOrder.count {
            geometricRearCandidateArtifacts[candidate.id] =
                geometricRearCandidateArtifactsInOrder[index]
        }
        materialCandidates = Self.candidates(
            sheet: state["material_sheet"], titleKey: "candidate_id")

        let hypothesisSheet = state["hypothesis_sheet"] as? [String: Any]
        let comparisonDigest = hypothesisSheet?["comparison_digest"] as? String
        let decisions = state["shape_decisions"] as? [[String: Any]] ?? []
        let compensated = Set(decisions.compactMap { row -> String? in
            guard row["action"] as? String == "UNDO" else { return nil }
            return row["compensates_decision_id"] as? String
        })
        let active = decisions.reversed().first { row in
            guard let action = row["action"] as? String,
                  action == "APPROVE" || action == "REJECT",
                  let decisionID = row["decision_id"] as? String,
                  !compensated.contains(decisionID) else { return false }
            guard let comparisonDigest else { return false }
            return row["comparison_digest"] as? String == comparisonDigest
        }
        activeShapeDecisionID = active?["decision_id"] as? String
        canUndoShapeDecision = activeShapeDecisionID != nil
    }

    private func publishVisionPatternOperations(from hypotheses: [[String: Any]]) {
        visionPatternOperations = hypotheses.flatMap {
            hypothesis -> [VisionPatternOperationStatus] in
            let candidateID = hypothesis["candidate_id"] as? String ?? "candidate"
            let rows = hypothesis["pattern_operation_proposals"] as? [[String: Any]] ?? []
            return rows.compactMap { row -> VisionPatternOperationStatus? in
                guard let operationID = row["operation_id"] as? String,
                      let kind = row["kind"] as? String else { return nil }
                let target = row["target"] as? [String: Any] ?? [:]
                let piece = target["piece_id"] as? String ?? "?"
                let edge = target["semantic_edge"] as? String ?? "?"
                let review = row["review"] as? [String: Any] ?? [:]
                let execution = row["execution"] as? [String: Any] ?? [:]
                let disposition = (review["required"] as? Bool) == true
                    ? "REVIEW" : "PROPOSED"
                let detail = review["why"] as? String
                    ?? row["basis"] as? String
                    ?? "image-model construction proposal"
                return VisionPatternOperationStatus(
                    candidateID: candidateID, operationID: operationID,
                    kind: kind, target: "\(piece) / \(edge)",
                    authority: "PROPOSED", disposition: disposition,
                    executionStatus: execution["status"] as? String
                        ?? "PENDING_MCP_TARGET_RESOLUTION",
                    detail: detail)
            }
        }
    }

    private func publishVisibleFrontInventory(from hypotheses: [[String: Any]]) {
        guard let source = hypotheses.first,
              let rows = source["visible_front_inventory"] as? [[String: Any]]
        else {
            visibleFrontInventory = []
            return
        }
        visibleFrontInventory = rows.compactMap { row in
            guard let id = row["inventory_part_id"] as? String,
                  let sourceKind = row["source_kind"] as? String,
                  let normalizedKind = row["normalized_kind"] as? String,
                  let unit = row["garment_unit"] as? String,
                  let basis = row["visible_basis"] as? String else { return nil }
            return VisibleFrontInventoryItem(
                id: id,
                label: row["semantic_role"] as? String
                    ?? row["placement"] as? String ?? sourceKind.lowercased(),
                sourceKind: sourceKind,
                normalizedKind: normalizedKind,
                visibleColor: row["visible_color"] as? String,
                layer: row["layer"] as? Int ?? 0,
                side: row["side"] as? String,
                garmentUnit: unit,
                proposedParent: row["proposed_parent"] as? String,
                visibleBasis: basis,
                state: row["state"] as? String
                    ?? "PROPOSED_VISION_UNCONFIRMED")
        }.sorted {
            ($0.layer, $0.garmentUnit, $0.id) <
                ($1.layer, $1.garmentUnit, $1.id)
        }
    }

    /// Convert only the visible-front inventory to the persisted audit
    /// vocabulary.  The original candidate rows may contain rear alternatives;
    /// those are deliberately excluded from this human observation boundary.
    private static func visibleFrontAssertions(
        from hypotheses: [[String: Any]]
    ) -> [[String: Any]] {
        guard let source = hypotheses.first else { return [] }
        if let rows = source["visible_front_inventory"] as? [[String: Any]],
           !rows.isEmpty {
            return rows.enumerated().map { index, sourceRow in
                var row = sourceRow
                let assertionID = row["inventory_part_id"] as? String
                    ?? row["part_id"] as? String
                    ?? "visible-front-\(index + 1)"
                row["assertion_id"] = assertionID
                row["field"] = "visible_garment_part"
                row["category"] = "visible_front_inventory"
                row["evidence_scope"] = "VISIBLE_FRONT"
                row["state"] = "PROPOSED"
                row["rear_inference_performed"] = false
                return row
            }
        }
        let structure = source["structure"] as? [String: Any]
        let nodes = structure?["nodes"] as? [[String: Any]] ?? []
        return nodes.enumerated().map { index, node in
            let nodeID = node["node_id"] as? String
                ?? "visible-node-\(index + 1)"
            return [
                "assertion_id": nodeID,
                "part_id": nodeID,
                "field": "visible_garment_part",
                "category": "visible_front_inventory",
                "kind": node["kind"] as? String ?? "UNKNOWN_VISIBLE_PART",
                "evidence_scope": "VISIBLE_FRONT",
                "state": "PROPOSED",
                "rear_inference_performed": false,
            ]
        }
    }

    private static func candidates(sheet: Any?, titleKey: String) -> [Candidate] {
        guard let sheet = sheet as? [String: Any],
              let rows = sheet["candidates"] as? [[String: Any]] else { return [] }
        return rows.compactMap { row in
            guard let id = row["candidate_id"] as? String, !id.isEmpty,
                  let digest = row["digest"] as? String, !digest.isEmpty else { return nil }
            let title = (row[titleKey] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? id
            let detail: String
            if let assumptions = row["assumptions"] as? [String], !assumptions.isEmpty {
                detail = assumptions.joined(separator: " · ")
            } else if let validation = row["geometry_validation"] as? [String: Any] {
                detail = validation["verdict"] as? String ?? "PROPOSED"
            } else {
                detail = "PROPOSED"
            }
            return Candidate(id: id, digest: digest, title: title, detail: detail)
        }
    }

    private func state(from response: [String: Any]) -> [String: Any]? {
        guard let state = response["state"] as? [String: Any],
              state["schema"] as? String == Self.harnessSchema,
              state["phase"] is String else { return nil }
        return state
    }

    private func refusalText(_ response: [String: Any]) -> String {
        [response["verdict"] as? String, response["why"] as? String,
         response["how_to_close"] as? String]
            .compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: "\n")
    }

    private static func proposalPrompt(task: String, state: [String: Any],
                                       userRequest: String) -> String {
        let stateText: String
        if JSONSerialization.isValidJSONObject(state),
           let data = try? JSONSerialization.data(withJSONObject: state,
                                                  options: [.sortedKeys]),
           let text = String(data: data, encoding: .utf8) {
            stateText = text
        } else { stateText = "{}" }
        if task == "structure_hypotheses" {
            return """
            You are a garment-structure proposal worker inside a deterministic factory.
            Return JSON only: {"hypotheses":[...]}. For a front-only image provide at
            least two distinct named back_design alternatives. Every hypothesis needs
            candidate_id, back_design, assumptions, and a complete garment.structure.v1
            object with explicit positive dimensions. Never output approval, ANSWER,
            OBSERVED, tool calls, sewing methods, or claims of fact.
            USER REQUEST: \(userRequest)
            FACTORY STATE: \(stateText)
            """
        }
        return """
        You are a material-candidate proposal worker inside a deterministic factory.
        Return JSON only: {"candidates":[...]}. Give at least two candidates with a
        candidate_id and explicit SI material parameters or documented unknown ranges.
        Never output approval, ANSWER, OBSERVED, tool calls, medical comfort claims,
        or claims of fact.
        USER REQUEST: \(userRequest)
        FACTORY STATE: \(stateText)
        """
    }

    /// First-stage perception contract. The vision model describes only what
    /// it can see; Swift supplies bounded preview dimensions, expands unseen
    /// rear alternatives, and sends the typed parts to deterministic geometry.
    /// Keeping this prompt compact avoids spending the model's output budget on
    /// ontology instructions before it reaches the actual visible components.
    private static func visionProposalPrompt(userRequest: String) -> String {
        """
        Inspect the attached FRONT garment image. Return ONE compact JSON object
        only, with no markdown and no reasoning:
        {"candidates":[{"candidate_id":"visible-front",
        "back_design":"PROPOSED; rear not visible",
        "assumptions":["rear, depth, material, dimensions and sewing are not observed"],
        "parts":[{"part_id":"stable-id","kind":"BODY_SHELL","layer":0,
        "semantic_role":"visible role such as blouse or cropped vest",
        "visible_color":"front-pixel colour only, not material identity",
        "placement":"where visible","garment_unit":"one-sewn-object-id",
        "attached_to":null,"attachment_relation":null,
        "visible_basis":"short pixel-visible cue",
        "dimensions":{}}]}]}

        Output exactly one visible-front candidate. Software will create three
        rear/closure alternatives without changing these visible parts. Include
        every visible GARMENT component separately: torso shell; symmetric or
        asymmetric sleeves; independently wearable top and bottom; trouser legs;
        underlayer; overskirt/cape/overlay; flare or panel; collar and yoke as
        separate parts; opening/cutout; belt; ribbon; bow; rosette; tie or
        tassel-like strip; flap; ruffle/frill. Exclude hair, skin, body, footwear,
        weapons and props.

        Pick exactly one kind per part—never join names with "|". Allowed kinds:
        BODY_SHELL, TUBE, FLARE, FRUSTUM, SLEEVE, BAND, OVERLAY, COLLAR,
        YOKE, GORE, GUSSET, OPENING, DRAPE_ANCHOR, BOW, RIBBON, ROSETTE,
        TIE, FLAP, RUFFLE, FRILL. A top/bodice/coat is BODY_SHELL; a skirt is
        FLARE/FRUSTUM; each trouser or legging leg is one TUBE; a cape is
        OVERLAY. Never use BODY_SHELL for legs and never use TUBE for boots.

        BODY_SHELL is the root of each sewn garment_unit. Every visible sewn
        non-root part should name its likely parent in attached_to. For a
        symmetric sleeve pair, prefer one SLEEVE with side="bilateral" and
        quantity=2 attached to the torso. Emit separate left/right sleeves only
        for visible asymmetry. Separately wearable layers use different
        garment_unit ids and no cross-unit attachment. Two trouser TUBEs share
        one garment_unit and should include side left/right and shape
        "trouser_leg"; a center GUSSET may connect both. These attachment and
        ownership values are only PROPOSED and may be rejected by geometry.
        If and only if a SLEEVE is attached to another SLEEVE, set
        attachment_relation to JOIN for a lower sewn extension or LAYER for an
        outer oversleeve. Otherwise use null. LAYER requires a strictly higher
        layer number than its parent. Do not guess this relation when unclear.

        semantic_role and visible_color are required for each visible part.
        They describe only the front pixels (for example blouse, cropped vest,
        left trouser leg, right trouser leg, asymmetric overskirt; ivory, navy,
        red, translucent teal). They form the target inventory for a later
        same-camera 3D reprojection check, not garment taxonomy or material
        identity. An independently wearable sleeveless vest or jacket is a
        separate BODY_SHELL in its own garment_unit, not an OVERLAY on the
        blouse. A sheer wrap or overskirt over visible trousers is a separate
        OVERLAY; it must not replace either trouser TUBE even when its outline
        resembles a skirt.

        Do not infer centimetres from pixels. dimensions may be {}. If you do
        supply values, use positive *_cm values only. visible_basis must describe
        a visible cue, not a class guess. Do not claim OBSERVED, APPROVED,
        ANSWER, CERTIFIED, manufacturing readiness, comfort, strength, a corpus
        match, or a sewing method. Do not add pattern operations in this first
        stage. Preserve visible layers, asymmetry, cutouts and decorations even
        if construction is uncertain.

        USER REQUEST: \(userRequest)
        """
    }

    /// One and only one bounded repair attempt after either JSON parsing or the
    /// deterministic parts/artifact boundary rejects the first proposal.
    private static func visionRepairPrompt(
        userRequest: String, failureCode: String
    ) -> String {
        """
        Retry the attached FRONT garment image as a minimal visible-parts JSON.
        The previous proposal failed with \(failureCode). Return JSON only:
        {"candidates":[{"candidate_id":"visible-front-retry",
        "back_design":"PROPOSED rear not visible",
        "assumptions":["all hidden construction is unknown"],"parts":[...]}]}
        Return exactly one candidate and at most 24 parts. Each part requires:
        part_id, exactly one allowed kind, semantic_role, visible_color, layer,
        placement, garment_unit, attached_to, visible_basis, and dimensions:{}.
        Allowed kinds are BODY_SHELL,TUBE,FLARE,FRUSTUM,SLEEVE,BAND,OVERLAY,
        COLLAR,YOKE,GORE,GUSSET,OPENING,DRAPE_ANCHOR,BOW,RIBBON,ROSETTE,TIE,
        FLAP,RUFFLE,FRILL. Never combine kinds with a bar or slash. Use one
        BODY_SHELL root per sewn garment_unit and attach its sewn children to
        that root; use a different garment_unit for separately wearable layers.
        If a SLEEVE truly targets another SLEEVE, include attachment_relation
        JOIN for a lower extension or LAYER for an oversleeve; LAYER must use a
        higher layer number. Otherwise attach the sleeve to its BODY_SHELL root.
        Include every visible sleeve, layer, asymmetric panel, opening/cutout,
        belt, ribbon, bow, rosette, tie/tassel and ruffle/frill. Exclude footwear,
        hair, skin and props. Do not include centimetres or pattern operations.
        Keep independently wearable upper layers as separate BODY_SHELL units.
        Keep two trouser legs as left/right TUBEs and any sheer wrap or overskirt
        above them as a separate OVERLAY; never replace the trousers with it.
        Never claim hidden facts, approval, observation or manufacturability.
        USER REQUEST: \(userRequest)
        """
    }

    /// Retained as a detailed reference contract for expert diagnostics. It is
    /// intentionally not the first-stage perception prompt: asking a local
    /// vision model to satisfy all construction rules at once caused valid
    /// visible parts to be lost before the deterministic compiler could help.
    private static func visionDetailedProposalPrompt(userRequest: String) -> String {
        """
        Inspect the attached front garment image and return JSON only:
        {"candidates":[...]}. Decompose visible geometry instead of forcing a
        garment-class label. Return 1-4 pixel-grounded visible-structure
        candidates. If the front image supports only one visible structure,
        return that one rather than inventing visible differences; Swift will
        deterministically expand it into multiple PROPOSED rear/closure
        alternatives. Use exactly this candidate shape:
        {"candidate_id":"short-id","back_design":"PROPOSED rear description",
         "assumptions":["rear is not visible"],"parts":[
          {"part_id":"torso","kind":"BODY_SHELL","layer":0,
           "placement":"torso","garment_unit":"base",
           "attached_to":null,
           "visible_basis":"what in the image supports it",
           "dimensions":{"height_cm":45,"circumference_cm":92}}
         ],"pattern_operations":[
          {"operation_id":"pleat-1","kind":"PLEAT",
           "target":{"piece_id":"skirt","semantic_edge":"hem"},
           "parameters":{"count":6,"depth_cm":2.0,"style":"knife"},
           "basis":"visible repeated fold rhythm; exact construction is uncertain"}
         ]}

        Allowed structural primitive kinds: BODY_SHELL, TUBE, FRUSTUM, FLARE,
        GORE, GUSSET, YOKE, COLLAR, HOOD, SLEEVE, BAND, OVERLAY, OPENING,
        DRAPE_ANCHOR. The visual ornament kinds BOW, RIBBON, ROSETTE, TIE and
        FLAP are also accepted input syntax because the existing geometric
        pipeline can represent them without adding garment-class enums. Swift
        records the source kind and deterministically lowers BOW/ROSETTE/FLAP
        to OVERLAY and RIBBON/TIE to BAND with
        alias_state=PROPOSED_NORMALIZATION. RUFFLE and FRILL are visible
        gathered-strip geometry and lower to BAND in the same proposal-only
        way. Use BODY_SHELL for a fitted torso base, one TUBE per
        trouser leg, FRUSTUM/FLARE for skirt volumes, SLEEVE for each visible
        sleeve, and OVERLAY/BAND/GORE for layers, frills and panels. Every node
        should have positive centimetre preview dimensions using these keys:
        BODY_SHELL(height_cm,circumference_cm);
        TUBE(length_cm,circumference_cm);
        FRUSTUM/FLARE(height_cm,top_circumference_cm,bottom_circumference_cm);
        GORE(length_cm,top_width_cm,bottom_width_cm);
        GUSSET(length_cm,width_cm); YOKE(height_cm,width_cm);
        COLLAR(length_cm,width_cm); HOOD(height_cm,width_cm,depth_cm);
        SLEEVE(length_cm,upper_circumference_cm,cuff_circumference_cm);
        BAND(length_cm,width_cm); OVERLAY(height_cm,width_cm);
        OPENING(length_cm); DRAPE_ANCHOR(no dimensions).
        Ornament preview dimensions use these source keys before geometric
        normalization: BOW(body_length_cm,body_width_cm,knot_length_cm,
        knot_width_cm); RIBBON(length_cm,width_cm);
        ROSETTE(strip_length_cm,strip_width_cm,finished_inner_length_cm);
        TIE(length_cm,top_width_cm,tip_width_cm);
        FLAP(attachment_width_cm,depth_cm,outer_width_cm); and
        RUFFLE/FRILL(length_cm,width_cm), where length is the ungathered strip
        and must exceed its proposed attachment boundary. These names describe
        visible construction geometry, not a garment classification.
        Do not invent another garment-class kind name. Map bodice/top/jacket/coat to
        BODY_SHELL, skirt to FLARE or FRUSTUM, each trouser/legging leg to
        TUBE, belt/waistband to BAND, cape to OVERLAY, and ruffle/frill to
        BAND. Do not omit a visible garment decoration merely because its kind
        is outside this list: emit the visual part with its literal kind,
        placement, attachment and proposed dimensions so Swift retains it in
        uncompiled_visual_parts for REVIEW. Identify footwear honestly with a
        footwear/shoes/boots garment_unit or an explicit footwear placement.
        Swift retains it as PROPOSED_EXCLUDED_NON_GARMENT and excludes it from
        garment structure nodes; never describe a boot as a TUBE garment leg.
        Omit only other non-garment props rather than changing the primitive
        vocabulary.
        Dimensions are proposed mannequin-scale values, never measurements from
        pixels. If a required dimension is uncertain, omit only that value: the
        deterministic compiler will fill it from the explicitly labelled
        bounded preview mannequin, not from an imagined pixel measurement.
        ``garment_unit`` is topology, not a class name: parts sewn into one
        object share a unit (for example ``dress``); independently wearable
        top and bottom use distinct units. ``attached_to`` may name another
        part, or an array of part ids for a gusset, only when the image supports
        a likely attachment. It remains a PROPOSED relation and the
        deterministic compiler may reject it. Boundaries proposed as directly
        sewn must have the same preview length: a skirt/TUBE top equals its
        BODY_SHELL bottom_circumference_cm (or circumference_cm); a COLLAR
        length equals neck_circumference_cm. A ruffle BAND must be longer than
        the boundary it gathers onto. For trousers emit exactly two TUBE nodes
        with shape=trouser_leg, side=left/right, quantity=1 and the same
        garment_unit, plus one center GUSSET with detail_role=trouser_gusset,
        side=center, quantity=1, attached_to=[left-leg-id,right-leg-id]. Both
        legs attach_to the same BODY_SHELL when they are a jumpsuit; for
        separately wearable trousers omit attached_to on both legs and leave
        the open waist for a later waistband/facing operation. Never merge two
        legs into one TUBE.
        A left/right set-in sleeve pair may be emitted as two visible SLEEVE
        parts. Swift merges it into one bilateral quantity=2 SLEEVE only when
        both parts target the same BODY_SHELL and their proposed drafting
        dimensions agree within a bounded tolerance; asymmetric sleeves remain
        explicit REVIEW and are never averaged as if symmetric.
        If a skirt/overskirt and exactly two trouser/legging TUBEs are visible
        below one BODY_SHELL, describe all visible pieces honestly. Swift will
        create separate outer-garment and underlayer topology alternatives so
        three lower parts are never sewn to one waist. It may add a PROPOSED
        center GUSSET because the rear crotch is not observed. A visual belt
        BAND whose proposed length differs from the target waist is an
        accessory/contact proposal, not a sewn JOIN; never alter either length
        merely to make that JOIN pass.
        For an OPENING, set attached_to to the affected garment part. You may
        add closure_detail and opening_topology as either a short string or a
        JSON object with state="PROPOSED". A rear zip, side opening, placket,
        lacing or pull-on construction inferred from this front-only image is
        always a candidate, never an observation. Omit those fields when even
        a bounded construction alternative cannot be stated.
        Preserve visible asymmetry and separate top/bottom/layers. Do not emit
        graph ports or executable structure operations: the deterministic
        compiler derives those. You may freely propose zero or more typed
        ``pattern_operations`` for visible PLEAT, GATHER, DART, or FOLD construction.
        These are JSON proposals, not natural-language commands. Each needs a
        stable operation_id, kind, target.piece_id naming exactly one part in
        this candidate, target.semantic_edge (for example hem, waist, cuff,
        neckline, left_side, right_side, or an exact eN address), finite typed
        parameters, and a short visual basis. PLEAT parameters are count,
        depth_cm and optional style knife/box/inverted_box. DART parameters are
        t, intake_cm, and either depth_cm or a finite [x,y] toward point. FOLD
        parameters are finite [x,y] start/end and direction
        mountain/valley/either. GATHER parameters contain finished_length_cm,
        ratio, or both. Both must be finite and positive, and ratio must be
        greater than 1 and no more than 8. When only ratio is proposed, Swift
        derives finished_length_cm only after target.piece_id and semantic_edge
        resolve to exactly one compiled edge, then asks garment_pattern_transform
        to validate it. If the piece or edge cannot be named without
        guessing, still describe the idea in assumptions but omit the
        operation. Never claim an image-derived operation is observed,
        approved, applied, or manufacturing-ready. Swift will overwrite any
        authority vocabulary, resolve the compiled piece/edge, and send only
        unambiguous typed proposals to the deterministic MCP geometry check.

        The rear, depth, material and sewing method are not visible. Make at
        least two falsifiable rear alternatives and say in assumptions that
        they are PROPOSED. Never emit approval, ANSWER, OBSERVED, a tool call,
        corpus claim, manufacturing guarantee, or comfort/strength claim.

        USER REQUEST: \(userRequest)
        """
    }

    /// Compile the model's deliberately small visual IR into the full graph
    /// vocabulary. Missing dimensions are projected from one explicit bounded
    /// preview mannequin profile and retain per-field PROPOSED provenance. They
    /// are never described as measurements from the image or target wearer.
    /// Malformed supplied values still reject the candidate. When the image
    /// model returns one valid pixel-grounded visible structure, the parser
    /// preserves it and deterministically creates three PROPOSED rear/closure
    /// alternatives; multi-candidate model output is never expanded here.
    static func parseVisionProposal(_ raw: String) -> [String: Any]? {
        let required: [String: [String]] = [
            "BODY_SHELL": ["height_cm", "circumference_cm"],
            "TUBE": ["length_cm", "circumference_cm"],
            "FRUSTUM": ["height_cm", "top_circumference_cm", "bottom_circumference_cm"],
            "FLARE": ["height_cm", "top_circumference_cm", "bottom_circumference_cm"],
            "GORE": ["length_cm", "top_width_cm", "bottom_width_cm"],
            "GUSSET": ["length_cm", "width_cm"],
            "YOKE": ["height_cm", "width_cm"],
            "COLLAR": ["length_cm", "width_cm"],
            "HOOD": ["height_cm", "width_cm", "depth_cm"],
            "SLEEVE": ["length_cm", "upper_circumference_cm", "cuff_circumference_cm"],
            "BAND": ["length_cm", "width_cm"],
            "OVERLAY": ["height_cm", "width_cm"],
            "OPENING": ["length_cm"],
            "DRAPE_ANCHOR": [],
        ]
        // These are only the preview mannequin's drafting values.  They close
        // the typed geometry contract when a vision model identifies a part but
        // honestly cannot infer real-world scale from a single uncalibrated
        // image. Target measurements replace them before manufacturing export.
        let previewDefaults: [String: [String: Double]] = [
            "BODY_SHELL": ["height_cm": 42, "circumference_cm": 92],
            "TUBE": ["length_cm": 62, "circumference_cm": 42],
            "FRUSTUM": ["height_cm": 62, "top_circumference_cm": 74,
                         "bottom_circumference_cm": 156],
            "FLARE": ["height_cm": 62, "top_circumference_cm": 74,
                       "bottom_circumference_cm": 156],
            "GORE": ["length_cm": 62, "top_width_cm": 15,
                      "bottom_width_cm": 32],
            "GUSSET": ["length_cm": 15, "width_cm": 12],
            "YOKE": ["height_cm": 14, "width_cm": 46],
            "COLLAR": ["length_cm": 42, "width_cm": 8],
            "HOOD": ["height_cm": 38, "width_cm": 32, "depth_cm": 28],
            "SLEEVE": ["length_cm": 58, "upper_circumference_cm": 34,
                       "cuff_circumference_cm": 20],
            "BAND": ["length_cm": 74, "width_cm": 6],
            "OVERLAY": ["height_cm": 42, "width_cm": 48],
            "OPENING": ["length_cm": 35],
            "DRAPE_ANCHOR": [:],
        ]
        let primitiveAliases: [String: String] = [
            "BODICE": "BODY_SHELL", "TOP": "BODY_SHELL",
            "TORSO": "BODY_SHELL", "JACKET": "BODY_SHELL",
            "COAT": "BODY_SHELL", "CORSET": "BODY_SHELL",
            "DRESS": "BODY_SHELL", "SKIRT": "FLARE",
            "SKIRT_PANEL": "GORE", "PANEL": "GORE",
            "BELT": "BAND", "WAISTBAND": "BAND",
            "BOW": "OVERLAY", "RIBBON": "BAND",
            "ROSETTE": "OVERLAY", "TIE": "BAND",
            "FLAP": "OVERLAY", "RUFFLE": "BAND",
            "FRILL": "BAND", "FLOUNCE": "BAND",
            "CAPE": "OVERLAY", "MANTLE": "OVERLAY",
        ]
        let visualGeometryAliases = Set([
            "BOW", "RIBBON", "ROSETTE", "TIE", "FLAP",
            "RUFFLE", "FRILL", "FLOUNCE",
        ])
        let routedOrnamentKinds = Set(["BOW", "RIBBON", "ROSETTE", "TIE", "FLAP"])
        // The pixel model deliberately returns no centimetre measurements for
        // an uncalibrated front image. Ornament expansion still needs complete
        // local 2D geometry before it can emit real cut pieces. Complete only
        // the preview dimensions here from one explicit bounded construction
        // profile. Every value remains PROPOSED and carries a break condition;
        // none becomes an observation or a target-wearer measurement.
        let ornamentPreviewDefaults: [String: [String: Double]] = [
            "BOW": ["body_length_cm": 22, "body_width_cm": 10,
                    "knot_length_cm": 5, "knot_width_cm": 4],
            "RIBBON": ["length_cm": 32, "width_cm": 4],
            "ROSETTE": ["strip_length_cm": 40, "strip_width_cm": 4,
                        "finished_inner_length_cm": 10],
            "TIE": ["length_cm": 34, "top_width_cm": 6,
                    "tip_width_cm": 2],
            "FLAP": ["attachment_width_cm": 12, "depth_cm": 8,
                     "outer_width_cm": 10],
        ]
        let ornamentDimensionAliases: [String: [String: [String]]] = [
            "BOW": [
                "body_length_cm": ["body_length_cm", "width_cm"],
                "body_width_cm": ["body_width_cm", "height_cm"],
                "knot_length_cm": ["knot_length_cm"],
                "knot_width_cm": ["knot_width_cm"],
            ],
            "RIBBON": [
                "length_cm": ["length_cm", "body_length_cm"],
                "width_cm": ["width_cm", "body_width_cm"],
            ],
            "ROSETTE": [
                "strip_length_cm": ["strip_length_cm"],
                "strip_width_cm": ["strip_width_cm", "width_cm"],
                "finished_inner_length_cm": ["finished_inner_length_cm"],
            ],
            "TIE": [
                "length_cm": ["length_cm"],
                "top_width_cm": ["top_width_cm", "width_cm"],
                "tip_width_cm": ["tip_width_cm"],
            ],
            "FLAP": [
                "attachment_width_cm": ["attachment_width_cm", "width_cm"],
                "depth_cm": ["depth_cm", "height_cm"],
                "outer_width_cm": ["outer_width_cm", "width_cm"],
            ],
        ]
        for encoded in balancedJSONObjects(in: raw) {
            guard let data = encoded.data(using: .utf8),
                  let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let candidates = object["candidates"] as? [[String: Any]] else {
                continue
            }
            var hypotheses: [[String: Any]] = []
            var usedCandidateIDs = Set<String>()
            for (candidateIndex, candidate) in candidates.prefix(4).enumerated() {
                guard let parts = candidate["parts"] as? [[String: Any]],
                      !parts.isEmpty, parts.count <= 32 else { continue }
                let back = boundedString(candidate["back_design"], limit: 240)
                    ?? "PROPOSED rear construction; not visible in the front image"
                var proposedBack = back
                for forbidden in ["OBSERVED", "ANSWER", "APPROVED", "CERTIFIED"] {
                    proposedBack = proposedBack.replacingOccurrences(
                        of: forbidden, with: "PROPOSED", options: [.caseInsensitive])
                }
                let proposedID = boundedString(candidate["candidate_id"], limit: 80)
                    ?? "vision-candidate-\(candidateIndex + 1)"
                let candidateID = stableIdentifier(proposedID,
                    fallback: "vision-candidate-\(candidateIndex + 1)")
                guard usedCandidateIDs.insert(candidateID).inserted else { continue }
                var nodes: [[String: Any]] = []
                var unsupportedParts: [[String: Any]] = []
                var typedOrnamentProposals: [[String: Any]] = []
                var visibleFrontInventory: [[String: Any]] = []
                var normalizationRecords: [[String: Any]] = []
                var normalizationAssumptions: [String] = []
                var usedNodeIDs = Set<String>()
                var valid = true
                for (partIndex, part) in parts.enumerated() {
                    guard let rawKind = boundedString(part["kind"], limit: 32) else {
                        valid = false; break
                    }
                    let namedKind = rawKind.uppercased()
                    let footwearTerms = Set(["footwear", "shoe", "shoes", "boot", "boots"])
                    func containsFootwearTerm(_ value: Any?) -> Bool {
                        guard let text = boundedString(value, limit: 120) else { return false }
                        let words = text.lowercased().split { character in
                            !character.isLetter && !character.isNumber
                        }.map(String.init)
                        return !footwearTerms.isDisjoint(with: words)
                    }
                    if containsFootwearTerm(part["garment_unit"])
                        || containsFootwearTerm(part["placement"]) {
                        var excluded: [String: Any] = [
                            "part_id": boundedString(part["part_id"], limit: 80)
                                ?? "part-\(partIndex + 1)",
                            "model_kind": namedKind,
                            "placement": boundedString(part["placement"], limit: 120)
                                ?? "footwear",
                            "state": "PROPOSED_EXCLUDED_NON_GARMENT",
                            "authority": "PROPOSED",
                            "why": "garment_unit or placement explicitly identifies footwear; it must not be normalized into a garment leg primitive",
                            "excluded_from_structure_nodes": true,
                            "manufacturing_ready": false,
                            "manufacturing_certified": false,
                        ]
                        if let unit = boundedString(part["garment_unit"], limit: 80) {
                            excluded["garment_unit"] = unit
                        }
                        if let basis = boundedString(part["visible_basis"], limit: 300) {
                            excluded["visible_basis"] = basis
                        }
                        if let rawDimensions = part["dimensions"] as? [String: Any] {
                            let retainedDimensions = rawDimensions.compactMapValues {
                                value -> Double? in
                                guard let number = value as? NSNumber,
                                      CFGetTypeID(number) != CFBooleanGetTypeID(),
                                      number.doubleValue.isFinite,
                                      number.doubleValue > 0,
                                      number.doubleValue <= 500 else { return nil }
                                return number.doubleValue
                            }
                            if !retainedDimensions.isEmpty {
                                excluded["proposed_dimensions"] = retainedDimensions
                                excluded["dimensions_not_measured_from_image"] = true
                            }
                        }
                        unsupportedParts.append(excluded)
                        continue
                    }
                    let kind = primitiveAliases[namedKind] ?? namedKind
                    guard let requiredDimensions = required[kind],
                          let defaults = previewDefaults[kind] else {
                        var unsupported: [String: Any] = [
                            "part_id": boundedString(part["part_id"], limit: 80)
                                ?? "part-\(partIndex + 1)",
                            "model_kind": namedKind,
                            "placement": boundedString(part["placement"], limit: 120)
                                ?? "unspecified",
                            "state": "PROPOSED_UNCOMPILED",
                            "authority": "PROPOSED",
                            "why": "no deterministic garment primitive compiler is registered",
                            "manufacturing_ready": false,
                            "manufacturing_certified": false,
                        ]
                        if let basis = boundedString(part["visible_basis"], limit: 300) {
                            unsupported["visible_basis"] = basis
                        }
                        if let unit = boundedString(part["garment_unit"], limit: 80) {
                            unsupported["garment_unit"] = stableIdentifier(
                                unit, fallback: "candidate")
                        }
                        if let attached = boundedString(part["attached_to"], limit: 80) {
                            unsupported["attached_to"] = stableIdentifier(
                                attached, fallback: "unresolved")
                            unsupported["attachment_state"] = "PROPOSED"
                        }
                        if let rawDimensions = part["dimensions"] as? [String: Any] {
                            let retainedDimensions = rawDimensions.compactMapValues {
                                value -> Double? in
                                guard let number = value as? NSNumber,
                                      CFGetTypeID(number) != CFBooleanGetTypeID(),
                                      number.doubleValue.isFinite,
                                      number.doubleValue > 0,
                                      number.doubleValue <= 500 else { return nil }
                                return number.doubleValue
                            }
                            if !retainedDimensions.isEmpty {
                                unsupported["proposed_dimensions"] = retainedDimensions
                                unsupported["dimensions_not_measured_from_image"] = true
                            }
                        }
                        unsupportedParts.append(unsupported)
                        continue
                    }
                    let supplied = part["dimensions"] as? [String: Any] ?? [:]
                    var sourceDimensions: [String: Double] = [:]
                    for (name, value) in supplied {
                        guard name.hasSuffix("_cm") || name.hasSuffix("_angle_deg"),
                              let number = value as? NSNumber,
                              CFGetTypeID(number) != CFBooleanGetTypeID(),
                              number.doubleValue.isFinite,
                              (name.hasSuffix("_angle_deg") || number.doubleValue > 0),
                              (name.hasSuffix("_angle_deg")
                                ? abs(number.doubleValue) <= 360
                                : number.doubleValue <= 500) else {
                            valid = false; break
                        }
                        sourceDimensions[name] = number.doubleValue
                    }
                    guard valid else { break }
                    var dimensions = sourceDimensions
                    var normalizationSources: [String: String] = [:]
                    func firstDimension(_ names: [String]) -> (Double, String)? {
                        for name in names {
                            if let value = sourceDimensions[name], value > 0 {
                                return (value, name)
                            }
                        }
                        return nil
                    }
                    func mappedDimension(_ target: String, _ names: [String],
                                         into output: inout [String: Double]) {
                        guard let (value, source) = firstDimension(names) else { return }
                        output[target] = value
                        normalizationSources[target] = source
                    }
                    if visualGeometryAliases.contains(namedKind) {
                        var mapped: [String: Double] = [:]
                        switch namedKind {
                        case "BOW":
                            mappedDimension("height_cm", [
                                "body_width_cm", "height_cm", "knot_length_cm",
                            ], into: &mapped)
                            mappedDimension("width_cm", [
                                "body_length_cm", "width_cm",
                            ], into: &mapped)
                        case "RIBBON":
                            mappedDimension("length_cm", [
                                "length_cm", "body_length_cm",
                            ], into: &mapped)
                            mappedDimension("width_cm", [
                                "width_cm", "body_width_cm",
                            ], into: &mapped)
                        case "ROSETTE":
                            if let (stripWidth, source) = firstDimension([
                                "strip_width_cm", "width_cm",
                            ]) {
                                mapped["height_cm"] = stripWidth * 2.0
                                normalizationSources["height_cm"] = "2*\(source)"
                                mapped["width_cm"] = stripWidth * 2.0
                                normalizationSources["width_cm"] = "2*\(source)"
                            }
                            if let (inner, source) = firstDimension([
                                "finished_inner_length_cm", "strip_length_cm",
                            ]) {
                                let diameter = inner / Double.pi
                                if diameter > (mapped["width_cm"] ?? 0) {
                                    mapped["width_cm"] = diameter
                                    normalizationSources["width_cm"] = "\(source)/pi"
                                }
                            }
                        case "TIE":
                            mappedDimension("length_cm", ["length_cm"], into: &mapped)
                            mappedDimension("width_cm", [
                                "top_width_cm", "width_cm", "tip_width_cm",
                            ], into: &mapped)
                        case "FLAP":
                            mappedDimension("height_cm", [
                                "depth_cm", "height_cm",
                            ], into: &mapped)
                            mappedDimension("width_cm", [
                                "attachment_width_cm", "outer_width_cm", "width_cm",
                            ], into: &mapped)
                        case "RUFFLE", "FRILL", "FLOUNCE":
                            mappedDimension("length_cm", [
                                "length_cm", "strip_length_cm", "gathered_length_cm",
                                "sweep_cm", "finished_length_cm",
                            ], into: &mapped)
                            mappedDimension("width_cm", [
                                "width_cm", "strip_width_cm", "depth_cm",
                                "ruffle_depth_cm",
                            ], into: &mapped)
                        default:
                            break
                        }
                        dimensions = mapped
                    }
                    var dimensionProvenance: [String: [String: Any]] = [:]
                    for name in dimensions.keys.sorted() {
                        let normalizedFrom = normalizationSources[name]
                        dimensionProvenance[name] = [
                            "state": "PROPOSED",
                            "dimension_source": normalizedFrom == nil
                                ? "MODEL_SUPPLIED_PROPOSAL"
                                : "PROPOSED_NORMALIZATION_FROM_MODEL_GEOMETRY",
                            "basis": normalizedFrom == nil
                                ? "vision model proposed a mannequin-scale preview value; pixels were not converted to centimetres"
                                : "deterministic geometry normalization from proposed source dimension \(normalizedFrom!); pixels were not measured",
                            "breaks_when": "target wearer measurements or calibrated multi-view scale are supplied",
                            "not_measured_from_image": true,
                            "model_supplied": true,
                            "completed": false,
                        ]
                    }
                    for name in requiredDimensions where dimensions[name] == nil {
                        guard let fallback = defaults[name] else {
                            valid = false; break
                        }
                        dimensions[name] = fallback
                        dimensionProvenance[name] = [
                            "state": "PROPOSED",
                            "dimension_source": "BOUNDED_PREVIEW_MANNEQUIN_DERIVED_PROPOSAL",
                            "basis": "explicit bounded preview mannequin profile; no image pixels were converted to centimetres",
                            "breaks_when": "target wearer measurements are supplied",
                            "not_measured_from_image": true,
                            "model_supplied": false,
                            "completed": true,
                        ]
                    }
                    guard valid,
                          requiredDimensions.allSatisfy({ dimensions[$0] != nil }) else {
                        valid = false; break
                    }
                    let proposedPartID = boundedString(part["part_id"], limit: 80)
                        ?? "part-\(partIndex + 1)"
                    var nodeID = stableIdentifier(proposedPartID,
                        fallback: "part-\(partIndex + 1)")
                    if !usedNodeIDs.insert(nodeID).inserted {
                        nodeID += "-\(partIndex + 1)"
                        guard usedNodeIDs.insert(nodeID).inserted else {
                            valid = false; break
                        }
                    }
                    let layer = max(0, min((part["layer"] as? NSNumber)?.intValue ?? 0, 15))
                    var attributes: [String: Any] = [
                        "proposal_source": "pixel-seeing vision model",
                        "back_design": proposedBack,
                        "dimension_provenance": dimensionProvenance,
                        "preview_dimensions_only": true,
                    ]
                    if namedKind != kind {
                        attributes["model_kind"] = namedKind
                        attributes["primitive_alias"] = kind
                        attributes["alias_state"] = "PROPOSED_NORMALIZATION"
                        attributes["source_dimension_proposals"] = sourceDimensions
                        attributes["normalization_dimension_map"] = normalizationSources
                        attributes["normalization_not_measurement"] = true
                        if part["detail_role"] == nil {
                            // Topology consumes detail_role as a closed typed
                            // token.  Keep ruffle/frill roles exact so their
                            // longer edge is compiled as GATHER rather than an
                            // impossible equal-length BAND join.  The fuller
                            // normalization description remains separate.
                            attributes["detail_role"] = Set([
                                "RUFFLE", "FRILL", "FLOUNCE",
                            ]).contains(namedKind)
                                ? namedKind.lowercased()
                                : "\(namedKind.lowercased()) visual geometry normalized to \(kind)"
                            attributes["visual_geometry_normalization_role"] =
                                "\(namedKind.lowercased()) visual geometry normalized to \(kind)"
                        }
                    }
                    if let placement = boundedString(part["placement"], limit: 120) {
                        attributes["placement"] = placement
                    }
                    if let unit = boundedString(part["garment_unit"], limit: 80) {
                        attributes["garment_unit"] = stableIdentifier(
                            unit, fallback: "candidate")
                    }
                    if let attached = boundedString(part["attached_to"], limit: 80) {
                        let marker = attached.lowercased()
                            .trimmingCharacters(in: .whitespacesAndNewlines)
                        let noReferenceMarkers: Set<String> = [
                            "none", "null", "nil", "unknown", "n/a", "na",
                            "not applicable", "no parent", "unattached",
                        ]
                        if !noReferenceMarkers.contains(marker) {
                            attributes["attached_to"] = stableIdentifier(
                                attached, fallback: "unresolved")
                            attributes["attachment_state"] = "PROPOSED"
                        } else {
                            attributes["attachment_normalization"] =
                                "MODEL_NULL_SENTINEL_TO_ABSENT_PROPOSED_REFERENCE"
                        }
                    } else if let attached = part["attached_to"] as? [Any] {
                        let rawReferences = attached.compactMap {
                            boundedString($0, limit: 80)
                        }
                        let noReferenceMarkers: Set<String> = [
                            "none", "null", "nil", "unknown", "n/a", "na",
                        ]
                        let meaningfulReferences = rawReferences.filter {
                            !noReferenceMarkers.contains($0.lowercased()
                                .trimmingCharacters(in: .whitespacesAndNewlines))
                        }
                        let ids = meaningfulReferences.map {
                            stableIdentifier($0, fallback: "unresolved")
                        }
                        if !ids.isEmpty, ids.count <= 8,
                           Set(ids).count == ids.count {
                            attributes["attached_to"] = ids
                            attributes["attachment_state"] = "PROPOSED"
                        } else if !attached.isEmpty && meaningfulReferences.isEmpty
                                    && rawReferences.count == attached.count {
                            attributes["attachment_normalization"] =
                                "MODEL_NULL_SENTINELS_TO_ABSENT_PROPOSED_REFERENCE"
                        } else if !attached.isEmpty {
                            valid = false; break
                        }
                    }
                    for name in ["side", "shape", "detail_role"] {
                        if let value = boundedString(part[name], limit: 80) {
                            attributes[name] = value
                        }
                    }
                    if let relation = boundedString(
                            part["attachment_relation"], limit: 16)?.uppercased(),
                       ["JOIN", "LAYER"].contains(relation) {
                        attributes["attachment_relation"] = relation
                        attributes["attachment_relation_state"] = "PROPOSED"
                    }
                    for name in ["closure_detail", "opening_topology"] {
                        if let value = boundedString(part[name], limit: 240) {
                            attributes[name] = value
                        } else if let value = part[name] as? [String: Any],
                                  JSONSerialization.isValidJSONObject(value) {
                            attributes[name] = value
                        }
                    }
                    if let quantity = part["quantity"] as? NSNumber,
                       CFGetTypeID(quantity) != CFBooleanGetTypeID(),
                       quantity.intValue >= 1, quantity.intValue <= 8 {
                        attributes["quantity"] = quantity.intValue
                    }
                    if let basis = boundedString(part["visible_basis"], limit: 300) {
                        attributes["visible_basis"] = basis
                    }
                    if let semanticRole = boundedString(
                            part["semantic_role"], limit: 120) {
                        attributes["semantic_role"] = semanticRole
                    }
                    if let visibleColor = boundedString(
                            part["visible_color"], limit: 80) {
                        attributes["visible_color"] = visibleColor
                    }
                    let inventoryBasis = attributes["visible_basis"] as? String
                        ?? "AI proposed this visible component; image region confirmation is still required"
                    var inventoryRow: [String: Any] = [
                        "inventory_part_id": nodeID,
                        "source_kind": namedKind,
                        "normalized_kind": kind,
                        "semantic_role": attributes["semantic_role"] as? String
                            ?? attributes["detail_role"] as? String
                            ?? attributes["placement"] as? String
                            ?? namedKind.lowercased(),
                        "placement": attributes["placement"] as? String
                            ?? "visible front",
                        "garment_unit": attributes["garment_unit"] as? String
                            ?? "candidate",
                        "layer": layer,
                        "visible_basis": inventoryBasis,
                        "state": "PROPOSED_VISION_UNCONFIRMED",
                        "front_only": true,
                        "rear_observed": false,
                        "material_identity_observed": false,
                        "manufacturing_ready": false,
                    ]
                    if let color = attributes["visible_color"] as? String {
                        inventoryRow["visible_color"] = color
                    }
                    if let side = attributes["side"] as? String {
                        inventoryRow["side"] = side
                    }
                    if let parent = attributes["attached_to"] as? String {
                        inventoryRow["proposed_parent"] = parent
                    }
                    visibleFrontInventory.append(inventoryRow)
                    if routedOrnamentKinds.contains(namedKind) {
                        let proposedGrain = boundedString(
                            part["grain_direction"], limit: 32)?.uppercased()
                        let grain = Set([
                            "LENGTHWISE", "CROSSWISE", "BIAS_45",
                            "BIAS_-45", "NO_GRAIN",
                        ]).contains(proposedGrain ?? "")
                            ? proposedGrain! : "BIAS_45"
                        let proposedAllowance = (part["seam_allowance_cm"]
                            as? NSNumber)?.doubleValue
                        let allowance = proposedAllowance?.isFinite == true
                            && proposedAllowance! > 0 && proposedAllowance! <= 5
                            ? proposedAllowance! : 1.0
                        guard let ornamentDefaults = ornamentPreviewDefaults[namedKind],
                              let ornamentAliases = ornamentDimensionAliases[namedKind]
                        else { valid = false; break }
                        var ornamentDimensions: [String: Any] = [:]
                        for field in ornamentDefaults.keys.sorted() {
                            let aliases = ornamentAliases[field] ?? [field]
                            let supplied: (String, Double)? = aliases.compactMap { alias in
                                sourceDimensions[alias].map { value in (alias, value) }
                            }.first
                            let value = supplied?.1 ?? ornamentDefaults[field]!
                            let sourceField = supplied?.0
                            ornamentDimensions[field] = [
                                "value_cm": value,
                                "state": "PROPOSED",
                                "basis": sourceField == nil
                                    ? "bounded ornament preview profile; no image pixels were converted to centimetres"
                                    : "vision-model \(sourceField!) proposal normalized to \(field); not measured from image pixels",
                                "breaks_when": "target wearer scale, calibrated multi-view geometry, or human ornament dimensions are supplied",
                                "not_measured_from_image": true,
                                "dimension_source": sourceField == nil
                                    ? "BOUNDED_PREVIEW_MANNEQUIN_DERIVED_PROPOSAL"
                                    : "MODEL_SUPPLIED_PROPOSAL",
                                "completed": sourceField == nil,
                            ]
                        }
                        var ornament: [String: Any] = [
                            "part_id": nodeID,
                            "kind": namedKind,
                            "layer": layer,
                            "placement": boundedString(part["placement"], limit: 120)
                                ?? "front ornament",
                            "visible_basis": boundedString(
                                part["visible_basis"], limit: 300)
                                ?? "vision model proposed visible ornament geometry",
                            "dimensions": ornamentDimensions,
                            "quantity": attributes["quantity"] as? Int ?? 1,
                            "grain_direction": grain,
                            "seam_allowance_cm": allowance,
                            "state": "PROPOSED",
                            "authority": "PROPOSED",
                            "normalized_preview_node_id": nodeID,
                            "dimensions_not_measured_from_image": true,
                            "construction_defaults_require_review": true,
                        ]
                        if let attached = attributes["attached_to"] {
                            ornament["attached_to"] = attached
                        }
                        if let targetPort = boundedString(
                                part["target_port_id"] ?? part["target_edge"],
                                limit: 80) {
                            ornament["target_port_id"] = targetPort
                        }
                        if namedKind == "RIBBON" {
                            let proposedMode = boundedString(
                                part["attachment_mode"], limit: 32)?.uppercased()
                            ornament["attachment_mode"] = Set([
                                "END", "CENTER", "LONG_EDGE",
                            ]).contains(proposedMode ?? "")
                                ? proposedMode! : "CENTER"
                        }
                        typedOrnamentProposals.append(ornament)
                        // BOW/RIBBON/ROSETTE/TIE/FLAP are compiled by the
                        // typed ornament pipeline into their own cut pieces
                        // and attachment ports. Keeping the visual alias as a
                        // second BODY/WAIST BAND or OVERLAY node makes a chest
                        // ribbon look like an ambiguous structural boundary.
                        // RUFFLE/FRILL/FLOUNCE are intentionally not in
                        // routedOrnamentKinds: those remain structural BANDs
                        // so their explicit GATHER boundary is validated.
                        continue
                    }
                    nodes.append(["node_id": nodeID, "kind": kind,
                                  "dimensions": dimensions, "ports": [],
                                  "layer": layer, "attributes": attributes])
                }
                guard valid, !nodes.isEmpty else { continue }
                let attachmentAliasNormalization =
                    normalizeVisionAttachmentAliases(nodes: &nodes)
                normalizationRecords.append(
                    contentsOf: attachmentAliasNormalization.records)
                normalizationAssumptions.append(
                    contentsOf: attachmentAliasNormalization.assumptions)
                let bodyLayerAnchorNormalization =
                    normalizeVisionBodyLayerAnchors(nodes: &nodes)
                normalizationRecords.append(
                    contentsOf: bodyLayerAnchorNormalization.records)
                normalizationAssumptions.append(
                    contentsOf: bodyLayerAnchorNormalization.assumptions)
                let goreOverlayNormalization =
                    normalizeVisionAttachedGoreOverlays(nodes: &nodes)
                normalizationRecords.append(
                    contentsOf: goreOverlayNormalization.records)
                normalizationAssumptions.append(
                    contentsOf: goreOverlayNormalization.assumptions)
                let waistAnchorNormalization = normalizeVisionWaistAnchors(
                    nodes: &nodes)
                normalizationRecords.append(
                    contentsOf: waistAnchorNormalization.records)
                normalizationAssumptions.append(
                    contentsOf: waistAnchorNormalization.assumptions)
                let sharedWaistStackNormalization =
                    normalizeVisionSharedWaistStacks(nodes: &nodes)
                normalizationRecords.append(
                    contentsOf: sharedWaistStackNormalization.records)
                normalizationAssumptions.append(
                    contentsOf: sharedWaistStackNormalization.assumptions)
                let mergedTrouserPairNormalization =
                    normalizeMergedVisionTrouserPairs(nodes: &nodes)
                normalizationRecords.append(
                    contentsOf: mergedTrouserPairNormalization.records)
                normalizationAssumptions.append(
                    contentsOf: mergedTrouserPairNormalization.assumptions)
                if candidates.count >= 2 {
                    let candidateText = "\(candidateID) \(proposedBack)".lowercased()
                    let directVariant = candidateText.contains("closed") &&
                        candidateText.contains("stretch")
                        ? "closed-back-stretch" : "direct-front-proposal"
                    let layeredWaistNormalization = normalizeLayeredWaistCandidate(
                        nodes: &nodes, variantID: directVariant)
                    normalizationRecords.append(
                        contentsOf: layeredWaistNormalization.records)
                    normalizationAssumptions.append(
                        contentsOf: layeredWaistNormalization.assumptions)
                }
                let waistBoundaryNormalization =
                    reconcileBoundedPreviewWaistJoinBoundaries(nodes: &nodes)
                normalizationRecords.append(
                    contentsOf: waistBoundaryNormalization.records)
                normalizationAssumptions.append(
                    contentsOf: waistBoundaryNormalization.assumptions)
                let sleeveAnchorNormalization = normalizeVisionSleeveAnchors(
                    nodes: &nodes)
                normalizationRecords.append(
                    contentsOf: sleeveAnchorNormalization.records)
                normalizationAssumptions.append(
                    contentsOf: sleeveAnchorNormalization.assumptions)
                let sleeveBoundaryNormalization =
                    reconcileBoundedPreviewSleeveJoinBoundaries(nodes: &nodes)
                normalizationRecords.append(
                    contentsOf: sleeveBoundaryNormalization.records)
                normalizationAssumptions.append(
                    contentsOf: sleeveBoundaryNormalization.assumptions)
                let sleeveNormalization = normalizeVisionSleevePair(
                    nodes: &nodes,
                    typedOrnaments: &typedOrnamentProposals,
                    unsupportedParts: &unsupportedParts)
                normalizationRecords.append(contentsOf: sleeveNormalization.records)
                normalizationAssumptions.append(contentsOf: sleeveNormalization.assumptions)
                let limbBandNormalization = separateVisionLimbBandContacts(
                    nodes: &nodes)
                normalizationRecords.append(
                    contentsOf: limbBandNormalization.records)
                normalizationAssumptions.append(
                    contentsOf: limbBandNormalization.assumptions)
                let beltNormalization = separateMismatchedVisionBeltContacts(
                    nodes: &nodes, unsupportedParts: &unsupportedParts)
                normalizationRecords.append(contentsOf: beltNormalization.records)
                normalizationAssumptions.append(contentsOf: beltNormalization.assumptions)
                let gatheredBandNormalization =
                    reconcileBoundedPreviewGatheredBandBoundaries(nodes: &nodes)
                normalizationRecords.append(
                    contentsOf: gatheredBandNormalization.records)
                normalizationAssumptions.append(
                    contentsOf: gatheredBandNormalization.assumptions)
                let bandBoundaryNormalization =
                    reconcileBoundedPreviewBandBoundaries(nodes: &nodes)
                normalizationRecords.append(
                    contentsOf: bandBoundaryNormalization.records)
                normalizationAssumptions.append(
                    contentsOf: bandBoundaryNormalization.assumptions)
                // A vision model may already return two or more rear
                // candidates. Those candidates do not pass through
                // expandSingleVisibleVisionCandidate, so complete the exact
                // same-unit left/right trouser pair here as well. The helper
                // is deliberately a no-op for one leg, duplicate sides,
                // branched groups, or non-trouser TUBEs.
                let standaloneTrouserNormalization =
                    normalizeStandaloneTrouserTopology(nodes: &nodes)
                normalizationRecords.append(
                    contentsOf: standaloneTrouserNormalization.records)
                normalizationAssumptions.append(
                    contentsOf: standaloneTrouserNormalization.assumptions)
                let visibleSideAttachmentNormalization =
                    normalizeVisionVisibleSideAttachments(nodes: &nodes)
                normalizationRecords.append(
                    contentsOf: visibleSideAttachmentNormalization.records)
                normalizationAssumptions.append(
                    contentsOf: visibleSideAttachmentNormalization.assumptions)
                guard !nodes.isEmpty else { continue }
                // ``attached_to`` is still a proposal, but it cannot coexist
                // with a contradictory declaration that the child is a
                // separately wearable object. Normalise ownership only; the
                // Python compiler must still create and validate an actual
                // seam/layer relation before connectivity passes.
                let unitByNode: [String: String] = Dictionary(
                    uniqueKeysWithValues: nodes.compactMap { node in
                        guard let id = node["node_id"] as? String,
                              let attributes = node["attributes"] as? [String: Any],
                              let unit = attributes["garment_unit"] as? String
                        else { return nil }
                        return (id, unit)
                    })
                let parentByNode: [String: String] = Dictionary(
                    uniqueKeysWithValues: nodes.compactMap { node in
                        guard let id = node["node_id"] as? String,
                              let attributes = node["attributes"] as? [String: Any],
                              let parent = attributes["attached_to"] as? String
                        else { return nil }
                        return (id, parent)
                    })
                func inheritedUnit(for nodeID: String) -> String? {
                    var current = nodeID
                    var visited = Set<String>()
                    while let parent = parentByNode[current] {
                        guard visited.insert(current).inserted,
                              unitByNode[parent] != nil else { return nil }
                        current = parent
                    }
                    return unitByNode[current] ?? unitByNode[nodeID]
                }
                for index in nodes.indices {
                    guard var attributes = nodes[index]["attributes"] as? [String: Any],
                          let nodeID = nodes[index]["node_id"] as? String,
                          let parent = attributes["attached_to"] as? String else {
                        continue
                    }
                    guard let parentUnit = inheritedUnit(for: nodeID) else {
                        attributes["attachment_resolution"] =
                            "PROPOSED_UNRESOLVED_OR_CYCLIC"
                        attributes["unresolved_parent"] = parent
                        nodes[index]["attributes"] = attributes
                        continue
                    }
                    if let modelUnit = attributes["garment_unit"] as? String,
                       modelUnit != parentUnit {
                        attributes["model_garment_unit"] = modelUnit
                        attributes["garment_unit_normalization"] =
                            "attached_to parent; PROPOSED topology only"
                    }
                    attributes["garment_unit"] = parentUnit
                    nodes[index]["attributes"] = attributes
                }
                // Typed ornaments do not remain rectangular structure aliases,
                // but their real cut pieces are still emitted by the Python
                // artifact pipeline.  Keep their stable part ids addressable
                // by deferred PLEAT/GATHER/DART/FOLD proposals; validation
                // still happens only after the compiled piece and edge exist.
                let ornamentPartIDs = Set(typedOrnamentProposals.compactMap {
                    $0["part_id"] as? String
                })
                let nodeIDs = Set(nodes.compactMap {
                    $0["node_id"] as? String
                }).union(ornamentPartIDs)
                let operationProposals = parseVisionPatternOperations(
                    candidate, candidateID: candidateID, nodeIDs: nodeIDs)
                let assumptions = (candidate["assumptions"] as? [Any] ?? [])
                    .compactMap { boundedString($0, limit: 300) }.prefix(12)
                hypotheses.append([
                    "candidate_id": candidateID, "back_design": proposedBack,
                    "assumptions": Array(assumptions) + normalizationAssumptions + [
                        "vision model output is PROPOSED and unapproved",
                        "centimetre dimensions are model or bounded preview-mannequin proposals, not image measurements",
                        "target wearer measurements are required before manufacturing export",
                    ],
                    "structure": ["schema": "garment.structure.v1",
                                  "nodes": nodes, "operations": []],
                    "pattern_operation_proposals": operationProposals,
                    "proposal_source": "pixel-seeing vision LLM",
                    "normalization_records": normalizationRecords,
                    "visible_front_inventory": visibleFrontInventory,
                    "typed_ornament_proposals": typedOrnamentProposals,
                    "uncompiled_visual_parts": unsupportedParts,
                    "representation_complete": !unsupportedParts.contains {
                        $0["state"] as? String == "PROPOSED_UNCOMPILED"
                    },
                    "rear_authority": "PROPOSED",
                    "material_authority": "UNKNOWN",
                    "requires_human_approval": true,
                    "manufacturing_ready": false,
                    "manufacturing_certified": false,
                ])
            }
            if hypotheses.count >= 2 { return ["hypotheses": hypotheses] }
            if candidates.count == 1, let visible = hypotheses.first {
                let expanded = expandSingleVisibleVisionCandidate(visible)
                if expanded.count >= 2 { return ["hypotheses": expanded] }
            }
        }
        return nil
    }

    /// Small vision models sometimes place a garment-unit label in
    /// ``attached_to`` even though that field is a node address. Resolve the
    /// label only when it names exactly one BODY_SHELL root. This is a typed
    /// address normalization: it never chooses among multiple bodies and it
    /// preserves the model token as proposal provenance. A visible garter or
    /// strap aimed at a multi-node leg unit is instead retained as a detached
    /// contact accessory; choosing one leg would fabricate a sewn relation.
    private static func normalizeVisionAttachmentAliases(
        nodes: inout [[String: Any]]
    ) -> (records: [[String: Any]], assumptions: [String]) {
        let nodeIDs = Set(nodes.compactMap { $0["node_id"] as? String })
        var bodyIDsByUnit: [String: [String]] = [:]
        var nodeIDsByUnit: [String: [String]] = [:]
        for node in nodes {
            guard let nodeID = node["node_id"] as? String,
                  let attributes = node["attributes"] as? [String: Any],
                  let unit = attributes["garment_unit"] as? String,
                  !unit.isEmpty else { continue }
            nodeIDsByUnit[unit, default: []].append(nodeID)
        }
        for node in nodes where node["kind"] as? String == "BODY_SHELL" {
            guard let nodeID = node["node_id"] as? String,
                  let attributes = node["attributes"] as? [String: Any],
                  let unit = attributes["garment_unit"] as? String,
                  !unit.isEmpty else { continue }
            bodyIDsByUnit[unit, default: []].append(nodeID)
        }

        var records: [[String: Any]] = []
        var assumptions: [String] = []
        func semanticWords(_ text: String) -> Set<String> {
            Set(text.lowercased().split {
                !$0.isLetter && !$0.isNumber
            }.map(String.init))
        }
        func carrierFamily(words: Set<String>, kind: String? = nil) -> String? {
            if !words.isDisjoint(with: ["skirt", "overskirt", "petticoat"]) ||
                ["FLARE", "FRUSTUM"].contains(kind ?? "") {
                return "SKIRT"
            }
            if !words.isDisjoint(with: ["bodice", "body", "torso", "top"]) ||
                kind == "BODY_SHELL" {
                return "BODY_SHELL"
            }
            if !words.isDisjoint(with: ["sleeve", "gauntlet", "forearm"]) ||
                kind == "SLEEVE" {
                return "SLEEVE"
            }
            if !words.isDisjoint(with: ["waistband", "belt", "yoke"]) ||
                ["BAND", "YOKE"].contains(kind ?? "") {
                return "WAIST_CARRIER"
            }
            if !words.isDisjoint(with: ["cape", "mantle"]) {
                return "CAPE"
            }
            return nil
        }
        for index in nodes.indices {
            guard var attributes = nodes[index]["attributes"] as? [String: Any],
                  let nodeID = nodes[index]["node_id"] as? String,
                  let rawTarget = attributes["attached_to"] as? String,
                  !nodeIDs.contains(rawTarget) else { continue }
            if let matches = bodyIDsByUnit[rawTarget], matches.count == 1,
               let resolved = matches.first {
                attributes["model_attached_to"] = rawTarget
                attributes["attached_to"] = resolved
                attributes["attachment_address_normalization"] = [
                    "state": "PROPOSED_NORMALIZATION",
                    "model_target_token": rawTarget,
                    "resolved_node_id": resolved,
                    "resolution_rule": "unique BODY_SHELL garment_unit alias",
                    "not_observed_from_front": true,
                    "breaks_when": "the unit has zero or multiple BODY_SHELL roots, or an explicit node id is supplied",
                ]
                nodes[index]["attributes"] = attributes
                records.append([
                    "kind": "ATTACHMENT_UNIT_ALIAS_NORMALIZATION",
                    "state": "PROPOSED_NORMALIZATION",
                    "source_part_id": nodeID,
                    "model_target_token": rawTarget,
                    "resolved_node_id": resolved,
                    "not_observed_from_front": true,
                ])
                assumptions.append(
                    "\(nodeID).attached_to used the unique BODY_SHELL garment_unit alias \(rawTarget) and was re-addressed to \(resolved); no seam was observed")
                continue
            }

            // A unit alias may name one non-body carrier (for example a
            // skirt unit used by a visible OVERLAY). Resolve it only when the
            // unit contains exactly one other node. Multiple panels or legs
            // remain ambiguous and continue to fail closed downstream.
            if let matches = nodeIDsByUnit[rawTarget]?.filter({ $0 != nodeID }),
               matches.count == 1, let resolved = matches.first {
                attributes["model_attached_to"] = rawTarget
                attributes["attached_to"] = resolved
                attributes["attachment_address_normalization"] = [
                    "state": "PROPOSED_NORMALIZATION",
                    "model_target_token": rawTarget,
                    "resolved_node_id": resolved,
                    "resolution_rule": "unique garment_unit node alias",
                    "not_observed_from_front": true,
                    "breaks_when": "the unit contains zero or multiple nodes, or an explicit node id is supplied",
                ]
                nodes[index]["attributes"] = attributes
                records.append([
                    "kind": "ATTACHMENT_UNIT_NODE_ALIAS_NORMALIZATION",
                    "state": "PROPOSED_NORMALIZATION",
                    "source_part_id": nodeID,
                    "model_target_token": rawTarget,
                    "resolved_node_id": resolved,
                    "not_observed_from_front": true,
                ])
                assumptions.append(
                    "\(nodeID).attached_to used the unique garment_unit alias \(rawTarget) and was re-addressed to \(resolved); the proposed attachment is not observed")
                continue
            }

            // Some image models invent an address such as `skirt-unit-01`
            // without assigning that token as garment_unit. A semantic alias
            // is still deterministic only when one lower-layer carrier of
            // that family exists inside the child's own garment unit.
            let rawFamily = carrierFamily(words: semanticWords(rawTarget))
            let childUnit = attributes["garment_unit"] as? String
            let childLayer = nodes[index]["layer"] as? Int ?? 0
            if let rawFamily, let childUnit, !childUnit.isEmpty {
                let compatible = nodes.compactMap { candidate -> String? in
                    guard let candidateID = candidate["node_id"] as? String,
                          candidateID != nodeID,
                          let candidateAttributes = candidate["attributes"]
                            as? [String: Any],
                          candidateAttributes["garment_unit"] as? String == childUnit,
                          (candidate["layer"] as? Int ?? 0) < childLayer else {
                        return nil
                    }
                    let candidateText = [
                        candidateID,
                        candidateAttributes["placement"] as? String ?? "",
                        candidateAttributes["shape"] as? String ?? "",
                        candidateAttributes["detail_role"] as? String ?? "",
                        candidateAttributes["model_kind"] as? String ?? "",
                    ].joined(separator: " ")
                    let family = carrierFamily(
                        words: semanticWords(candidateText),
                        kind: candidate["kind"] as? String)
                    return family == rawFamily ? candidateID : nil
                }
                if compatible.count == 1, let resolved = compatible.first {
                    attributes["model_attached_to"] = rawTarget
                    attributes["attached_to"] = resolved
                    attributes["attachment_address_normalization"] = [
                        "state": "PROPOSED_NORMALIZATION",
                        "model_target_token": rawTarget,
                        "resolved_node_id": resolved,
                        "semantic_family": rawFamily,
                        "garment_unit": childUnit,
                        "resolution_rule": "unique lower-layer semantic carrier in source garment_unit",
                        "not_observed_from_front": true,
                        "breaks_when": "the garment unit has zero or multiple compatible lower-layer carriers, or an explicit node id is supplied",
                    ]
                    nodes[index]["attributes"] = attributes
                    records.append([
                        "kind": "ATTACHMENT_SEMANTIC_ALIAS_NORMALIZATION",
                        "state": "PROPOSED_NORMALIZATION",
                        "source_part_id": nodeID,
                        "model_target_token": rawTarget,
                        "resolved_node_id": resolved,
                        "semantic_family": rawFamily,
                        "not_observed_from_front": true,
                    ])
                    assumptions.append(
                        "\(nodeID).attached_to used unresolved semantic alias \(rawTarget) and was re-addressed to the only lower-layer \(rawFamily) carrier \(resolved) in \(childUnit); this is a falsifiable proposal, not an observed seam")
                    continue
                }
            }

            let semanticWords = Set([
                attributes["placement"] as? String,
                attributes["shape"] as? String,
                attributes["detail_role"] as? String,
                nodeID,
            ].compactMap { $0 }.joined(separator: " ").lowercased().split {
                !$0.isLetter && !$0.isNumber
            }.map(String.init))
            let contactWords: Set<String> = [
                "garter", "strap", "thigh", "armband", "armlet",
            ]
            guard nodes[index]["kind"] as? String == "BAND",
                  !semanticWords.isDisjoint(with: contactWords),
                  let unitNodes = nodeIDsByUnit[rawTarget] else { continue }
            let possibleTargets = unitNodes.filter { $0 != nodeID }
            guard
                  !possibleTargets.isEmpty else { continue }
            let previousRole = attributes["detail_role"] as? String
            attributes.removeValue(forKey: "attached_to")
            attributes["model_attached_to"] = rawTarget
            if let previousRole { attributes["model_detail_role"] = previousRole }
            attributes["detail_role"] = "standalone_garter"
            attributes["garment_unit"] = stableIdentifier(
                "standalone-contact-\(nodeID)", fallback: "standalone-contact")
            attributes["attachment_state"] = "PROPOSED_STANDALONE_CONTACT"
            attributes["contact_target_provenance"] = [
                "state": "PROPOSED",
                "model_target_token": rawTarget,
                "possible_target_node_ids": possibleTargets.sorted(),
                "sewn_join_created": false,
                "not_observed_from_front": true,
                "basis": "a unit alias addresses multiple possible limb targets",
                "breaks_when": "a side-specific node address or reviewed attachment is supplied",
            ]
            nodes[index]["attributes"] = attributes
            records.append([
                "kind": "AMBIGUOUS_UNIT_BAND_CONTACT",
                "state": "PROPOSED_NORMALIZATION",
                "source_part_id": nodeID,
                "model_target_token": rawTarget,
                "possible_target_node_ids": possibleTargets.sorted(),
                "join_created": false,
                "not_observed_from_front": true,
            ])
            assumptions.append(
                "\(nodeID) remains a standalone garter/strap CONTACT proposal because \(rawTarget) addresses multiple limb nodes; no leg or seam was selected")
        }
        return (records, assumptions)
    }

    /// Repairs only typed BODY_SHELL address mistakes made by a vision model.
    ///
    /// A layered shell may only own another shell in the same garment unit at
    /// a lower layer.  An independently wearable shell is instead a root of
    /// its own unit.  The model sometimes points either case at a sleeve,
    /// waistband or another visible child.  This normalizer never reasons from
    /// garment names and never invents a seam: it re-addresses only to the one
    /// lower BODY_SHELL in the same typed unit, or detaches an explicit
    /// cross-unit non-body address.  Every change remains PROPOSED and keeps
    /// the original model token.  Ambiguous same-unit cases are left untouched
    /// so the deterministic topology validator still refuses them.
    private static func normalizeVisionBodyLayerAnchors(
        nodes: inout [[String: Any]]
    ) -> (records: [[String: Any]], assumptions: [String]) {
        let indexByID: [String: Int] = Dictionary(
            uniqueKeysWithValues: nodes.indices.compactMap { index
                -> (String, Int)? in
                guard let nodeID = nodes[index]["node_id"] as? String else {
                    return nil
                }
                return (nodeID, index)
            })
        var records: [[String: Any]] = []
        var assumptions: [String] = []

        for index in nodes.indices {
            guard nodes[index]["kind"] as? String == "BODY_SHELL",
                  let nodeID = nodes[index]["node_id"] as? String,
                  var attributes = nodes[index]["attributes"] as? [String: Any],
                  let modelTarget = attributes["attached_to"] as? String,
                  let parentIndex = indexByID[modelTarget],
                  nodes[parentIndex]["kind"] as? String != "BODY_SHELL" else {
                continue
            }

            let childUnit = attributes["garment_unit"] as? String
            let childLayer = nodes[index]["layer"] as? Int ?? 0
            let parentAttributes = nodes[parentIndex]["attributes"]
                as? [String: Any]
            let parentUnit = parentAttributes?["garment_unit"] as? String

            let lowerBodyIDs = nodes.compactMap { candidate -> String? in
                guard candidate["kind"] as? String == "BODY_SHELL",
                      let candidateID = candidate["node_id"] as? String,
                      candidateID != nodeID,
                      let candidateAttributes = candidate["attributes"]
                        as? [String: Any],
                      let childUnit,
                      !childUnit.isEmpty,
                      candidateAttributes["garment_unit"] as? String == childUnit,
                      (candidate["layer"] as? Int ?? 0) < childLayer else {
                    return nil
                }
                return candidateID
            }

            if lowerBodyIDs.count == 1, let resolved = lowerBodyIDs.first {
                attributes["model_attached_to"] = modelTarget
                attributes["attached_to"] = resolved
                attributes["body_layer_anchor_normalization"] = [
                    "state": "PROPOSED_NORMALIZATION",
                    "model_target_node_id": modelTarget,
                    "resolved_body_shell_node_id": resolved,
                    "resolution_rule": "unique lower-layer BODY_SHELL in the same garment_unit",
                    "sewn_join_observed": false,
                    "not_observed_from_front": true,
                    "breaks_when": "zero or multiple lower BODY_SHELL candidates exist",
                ]
                nodes[index]["attributes"] = attributes
                records.append([
                    "kind": "BODY_LAYER_ANCHOR_NORMALIZATION",
                    "state": "PROPOSED_NORMALIZATION",
                    "source_part_id": nodeID,
                    "model_target_node_id": modelTarget,
                    "resolved_body_shell_node_id": resolved,
                    "not_observed_from_front": true,
                    "sewn_join_observed": false,
                ])
                assumptions.append(
                    "\(nodeID) was aimed at non-BODY_SHELL \(modelTarget) and was re-addressed to the only lower BODY_SHELL \(resolved) in \(childUnit ?? "the same unit"); this is proposed topology, not an observed seam")
                continue
            }

            if let childUnit, !childUnit.isEmpty,
               let parentUnit, !parentUnit.isEmpty,
               childUnit != parentUnit {
                attributes["model_attached_to"] = modelTarget
                attributes.removeValue(forKey: "attached_to")
                attributes["attachment_state"] =
                    "PROPOSED_SEPARATE_BODY_SHELL_ROOT"
                attributes["body_layer_anchor_normalization"] = [
                    "state": "PROPOSED_NORMALIZATION",
                    "model_target_node_id": modelTarget,
                    "resolution_rule": "cross-unit BODY_SHELL remains an independently wearable root",
                    "sewn_join_created": false,
                    "not_observed_from_front": true,
                    "breaks_when": "human review or evidence establishes a layered seam/ownership relation",
                ]
                nodes[index]["attributes"] = attributes
                records.append([
                    "kind": "SEPARATE_BODY_SHELL_ROOT_NORMALIZATION",
                    "state": "PROPOSED_NORMALIZATION",
                    "source_part_id": nodeID,
                    "model_target_node_id": modelTarget,
                    "source_garment_unit": childUnit,
                    "target_garment_unit": parentUnit,
                    "join_created": false,
                    "not_observed_from_front": true,
                ])
                assumptions.append(
                    "\(nodeID) remains an independent BODY_SHELL root because its model target \(modelTarget) belongs to another garment unit; no cross-garment seam was created")
            }
        }
        return (records, assumptions)
    }

    /// A front-image model may choose the geometric primitive ``GORE`` for a
    /// one-sided overskirt or floating pleated panel but omit the construction
    /// word ``overlay``.  Geometry can close that vocabulary gap only when the
    /// graph already contains one exact carrier, a strictly higher layer and
    /// non-structural surface/asymmetry evidence.  The result remains a
    /// PROPOSED LAYER relation; it never invents adjacent gore seams or turns a
    /// structural panel into an approved overlay.
    private static func normalizeVisionAttachedGoreOverlays(
        nodes: inout [[String: Any]]
    ) -> (records: [[String: Any]], assumptions: [String]) {
        let indexByID: [String: Int] = Dictionary(
            uniqueKeysWithValues: nodes.indices.compactMap { index
                -> (String, Int)? in
                guard let id = nodes[index]["node_id"] as? String else {
                    return nil
                }
                return (id, index)
            })
        let supportedCarrierKinds: Set<String> = [
            "BODY_SHELL", "FLARE", "FRUSTUM", "TUBE", "OVERLAY",
        ]
        let structuralWords: Set<String> = [
            "structural", "join", "joined", "seam", "seamed",
        ]
        let directOverlayWords: Set<String> = [
            "overlay", "overskirt", "decorative", "ornamental",
            "applique", "appliqué", "floating", "overlayer",
        ]
        let sideSurfaceWords: Set<String> = [
            "skirt", "panel", "surface", "pleat", "pleated", "drape",
            "draped", "sheer", "hip", "hem", "asymmetric",
            "asymmetrical",
        ]
        func words(_ attributes: [String: Any]) -> Set<String> {
            Set([
                "placement", "shape", "detail_role", "visible_basis",
                "model_kind", "construction_role",
            ].compactMap { attributes[$0] as? String }
                .joined(separator: " ").lowercased().split {
                    !$0.isLetter && !$0.isNumber
                }.map(String.init))
        }

        var records: [[String: Any]] = []
        var assumptions: [String] = []
        for index in nodes.indices where nodes[index]["kind"] as? String == "GORE" {
            guard let nodeID = nodes[index]["node_id"] as? String,
                  var attributes = nodes[index]["attributes"]
                    as? [String: Any],
                  let parentID = attributes["attached_to"] as? String,
                  let parentIndex = indexByID[parentID],
                  supportedCarrierKinds.contains(
                    nodes[parentIndex]["kind"] as? String ?? ""),
                  let childLayer = nodes[index]["layer"] as? Int,
                  let parentLayer = nodes[parentIndex]["layer"] as? Int,
                  childLayer > parentLayer else { continue }

            let relation = (attributes["attachment_relation"] as? String)?
                .trimmingCharacters(in: .whitespacesAndNewlines)
                .uppercased() ?? ""
            let semanticWords = words(attributes)
            guard relation != "JOIN",
                  semanticWords.isDisjoint(with: structuralWords) else {
                continue
            }
            let explicitSide = explicitVisionSide(nodes[index])
            let directOverlay = !semanticWords.isDisjoint(
                with: directOverlayWords)
            let sideSurface = explicitSide != nil &&
                !semanticWords.isDisjoint(with: sideSurfaceWords)
            guard relation == "LAYER" || directOverlay || sideSurface else {
                continue
            }

            let previousRole = attributes["detail_role"] as? String
            if let previousRole, previousRole != "gore_overlay" {
                attributes["model_detail_role"] = previousRole
            }
            attributes["detail_role"] = "gore_overlay"
            attributes["construction_role"] = "PROPOSED_GORE_OVERLAY"
            attributes["attachment_relation"] = "LAYER"
            attributes["attachment_relation_state"] = "PROPOSED"
            var normalization: [String: Any] = [
                "state": "PROPOSED_NORMALIZATION",
                "source_part_id": nodeID,
                "target_part_id": parentID,
                "source_layer": childLayer,
                "target_layer": parentLayer,
                "dimensions_changed": false,
                "seam_join_created": false,
                "not_observed_from_front": true,
                "basis": "one exact lower-layer carrier plus non-structural overlay/asymmetry surface semantics",
                "breaks_when": "layer order, carrier, side, visible surface semantics, or reviewed panel topology changes",
            ]
            if let explicitSide {
                normalization["physical_instance_side"] = explicitSide
            }
            if let previousRole {
                normalization["model_detail_role"] = previousRole
            }
            attributes["gore_overlay_normalization"] = normalization
            nodes[index]["attributes"] = attributes
            var record: [String: Any] = [
                "kind": "PROPOSED_ATTACHED_GORE_OVERLAY_NORMALIZATION",
                "state": "PROPOSED_NORMALIZATION",
                "source_part_id": nodeID,
                "target_part_id": parentID,
                "source_layer": childLayer,
                "target_layer": parentLayer,
                "dimensions_changed": false,
                "seam_join_created": false,
                "not_observed_from_front": true,
            ]
            if let explicitSide {
                record["physical_instance_side"] = explicitSide
            }
            records.append(record)
            assumptions.append(
                "\(nodeID) was retained as a separate PROPOSED GORE overlay on \(parentID); no structural gore seam, rear extent, or approval was inferred")
        }
        return (records, assumptions)
    }

    /// FLARE/FRUSTUM/TUBE are drafted against a BODY_SHELL waist boundary.
    /// A vision proposal may instead name an intervening visible waistband or
    /// yoke. Follow only its explicit acyclic attached_to chain. If that chain
    /// ends at one BODY_SHELL, re-address the waist child while retaining the
    /// visible carrier as contact provenance; otherwise leave it unresolved so
    /// deterministic topology fails closed.
    private static func normalizeVisionWaistAnchors(
        nodes: inout [[String: Any]]
    ) -> (records: [[String: Any]], assumptions: [String]) {
        let indexByID: [String: Int] = Dictionary(
            uniqueKeysWithValues: nodes.indices.compactMap { index
                -> (String, Int)? in
                guard let id = nodes[index]["node_id"] as? String else {
                    return nil
                }
                return (id, index)
            })
        var records: [[String: Any]] = []
        var assumptions: [String] = []
        for index in nodes.indices where
            Set(["FLARE", "FRUSTUM", "TUBE"])
                .contains(nodes[index]["kind"] as? String ?? "") {
            guard var attributes = nodes[index]["attributes"] as? [String: Any],
                  let nodeID = nodes[index]["node_id"] as? String,
                  let proposedParent = attributes["attached_to"] as? String,
                  let immediateIndex = indexByID[proposedParent],
                  nodes[immediateIndex]["kind"] as? String != "BODY_SHELL"
            else { continue }

            var current = proposedParent
            var visited = Set<String>()
            var resolvedBody: String?
            while let currentIndex = indexByID[current],
                  visited.insert(current).inserted {
                if nodes[currentIndex]["kind"] as? String == "BODY_SHELL" {
                    resolvedBody = current
                    break
                }
                guard let currentAttributes = nodes[currentIndex]["attributes"]
                        as? [String: Any],
                      let next = currentAttributes["attached_to"] as? String
                else { break }
                current = next
            }
            guard let bodyID = resolvedBody else { continue }
            let bodyIndex = indexByID[bodyID] ?? immediateIndex
            let bodyNode = nodes[bodyIndex]
            let bodyAttributes = bodyNode["attributes"] as? [String: Any] ?? [:]
            if let childUnit = attributes["garment_unit"] as? String,
               let bodyUnit = bodyAttributes["garment_unit"] as? String,
               childUnit != bodyUnit {
                continue
            }
            attributes["model_attached_to"] = proposedParent
            attributes["attached_to"] = bodyID
            attributes["attachment_state"] =
                "PROPOSED_WAIST_CARRIER_NORMALIZATION"
            attributes["waist_anchor_normalization"] = [
                "state": "PROPOSED_NORMALIZATION",
                "model_target_id": proposedParent,
                "resolved_body_shell_id": bodyID,
                "explicit_chain": visited.sorted(),
                "not_observed_from_front": true,
                "basis": "explicit acyclic attached_to chain reaches one BODY_SHELL",
                "breaks_when": "the carrier chain, garment unit, or reviewed waist topology changes",
            ]
            nodes[index]["attributes"] = attributes
            records.append([
                "kind": "WAIST_CARRIER_NORMALIZATION",
                "state": "PROPOSED_NORMALIZATION",
                "source_part_id": nodeID,
                "model_target_id": proposedParent,
                "resolved_body_shell_id": bodyID,
                "not_observed_from_front": true,
            ])
            assumptions.append(
                "\(nodeID) was re-addressed from visible waist carrier \(proposedParent) to BODY_SHELL \(bodyID) through an explicit chain; the actual sewing stack remains unobserved")
        }
        return (records, assumptions)
    }

    /// Annotate two or more proposed skirt/lower layers that directly name one
    /// BODY_SHELL waist with the Python parallel-waist contract before the
    /// visible-parts gate. Every child remains attached to the same body and in
    /// its garment unit; `(layer, node_id)` supplies a stable 1-based order.
    ///
    /// This is proposal metadata only: no dimension, visible evidence, or
    /// authority is changed. Explicit trouser TUBEs are excluded. If any leg
    /// semantics attached to the same body cannot be partitioned into exact
    /// left/right `(garment_unit, layer)` pairs, the whole body is left
    /// untouched so the typed topology gate can fail closed.
    private static func normalizeVisionSharedWaistStacks(
        nodes: inout [[String: Any]]
    ) -> (records: [[String: Any]], assumptions: [String]) {
        func words(for index: Int) -> Set<String> {
            let attributes = nodes[index]["attributes"] as? [String: Any] ?? [:]
            return Set([
                nodes[index]["node_id"] as? String,
                attributes["placement"] as? String,
                attributes["shape"] as? String,
                attributes["detail_role"] as? String,
            ].compactMap { $0 }.joined(separator: " ").lowercased().split {
                !$0.isLetter && !$0.isNumber
            }.map(String.init))
        }
        let legWords: Set<String> = [
            "trouser", "trousers", "pant", "pants", "leg", "legging",
            "leggings",
        ]
        func hasExplicitLegSemantics(_ index: Int) -> Bool {
            explicitVisionSide(nodes[index]) != nil ||
                !words(for: index).isDisjoint(with: legWords)
        }
        func number(_ dimensions: [String: Any], _ field: String) -> Double? {
            guard let value = dimensions[field] as? NSNumber,
                  CFGetTypeID(value) != CFBooleanGetTypeID(),
                  value.doubleValue.isFinite, value.doubleValue > 0 else {
                return nil
            }
            return value.doubleValue
        }

        let bodyIndices = nodes.indices.filter {
            nodes[$0]["kind"] as? String == "BODY_SHELL"
        }.sorted {
            (nodes[$0]["node_id"] as? String ?? "") <
                (nodes[$1]["node_id"] as? String ?? "")
        }
        var records: [[String: Any]] = []
        var assumptions: [String] = []

        for bodyIndex in bodyIndices {
            guard let bodyID = nodes[bodyIndex]["node_id"] as? String,
                  let bodyAttributes = nodes[bodyIndex]["attributes"]
                    as? [String: Any],
                  let bodyUnit = bodyAttributes["garment_unit"] as? String,
                  !bodyUnit.isEmpty else { continue }
            let directLowerIndices = nodes.indices.filter { index in
                guard ["FLARE", "FRUSTUM", "TUBE"].contains(
                        nodes[index]["kind"] as? String ?? ""),
                      let attributes = nodes[index]["attributes"]
                        as? [String: Any]
                else { return false }
                return attributes["attached_to"] as? String == bodyID
            }
            let legIndices = directLowerIndices.filter {
                nodes[$0]["kind"] as? String == "TUBE" &&
                    hasExplicitLegSemantics($0)
            }
            let nonTubeLegSemantics = directLowerIndices.contains { index in
                nodes[index]["kind"] as? String != "TUBE" &&
                    hasExplicitLegSemantics(index)
            }

            var legGroups: [String: [Int]] = [:]
            var legTopologyIsAmbiguous = nonTubeLegSemantics
            for index in legIndices {
                let attributes = nodes[index]["attributes"] as? [String: Any] ?? [:]
                guard let unit = attributes["garment_unit"] as? String,
                      !unit.isEmpty,
                      explicitVisionSide(nodes[index]) != nil else {
                    legTopologyIsAmbiguous = true
                    continue
                }
                let layer = nodes[index]["layer"] as? Int ?? 0
                legGroups["\(unit)\u{1f}\(layer)", default: []].append(index)
            }
            if legGroups.values.contains(where: { indices in
                indices.count != 2 || Set(indices.compactMap {
                    explicitVisionSide(nodes[$0])
                }) != Set(["left", "right"])
            }) {
                legTopologyIsAmbiguous = true
            }
            guard !legTopologyIsAmbiguous else { continue }

            let skirtIndices = directLowerIndices.filter { index in
                let kind = nodes[index]["kind"] as? String ?? ""
                return kind == "FLARE" || kind == "FRUSTUM" ||
                    (kind == "TUBE" && !hasExplicitLegSemantics(index))
            }.sorted { lhs, rhs in
                let leftLayer = nodes[lhs]["layer"] as? Int ?? 0
                let rightLayer = nodes[rhs]["layer"] as? Int ?? 0
                if leftLayer != rightLayer { return leftLayer < rightLayer }
                return (nodes[lhs]["node_id"] as? String ?? "") <
                    (nodes[rhs]["node_id"] as? String ?? "")
            }
            guard (2...8).contains(skirtIndices.count) else { continue }
            let orderedIDs = skirtIndices.compactMap {
                nodes[$0]["node_id"] as? String
            }
            guard orderedIDs.count == skirtIndices.count else { continue }
            let stackID = stableIdentifier(
                "waist-stack-\(bodyID)", fallback: "waist-stack")
            guard let bodyDimensions = nodes[bodyIndex]["dimensions"]
                    as? [String: Any],
                  let parentField = [
                    "bottom_circumference_cm", "waist_circumference_cm",
                    "circumference_cm",
                  ].first(where: { number(bodyDimensions, $0) != nil }),
                  let parentWaist = number(bodyDimensions, parentField)
            else { continue }
            var constructionModeByIndex: [Int: String] = [:]
            for index in skirtIndices {
                let kind = nodes[index]["kind"] as? String ?? ""
                let childField = kind == "TUBE"
                    ? "circumference_cm" : "top_circumference_cm"
                guard let dimensions = nodes[index]["dimensions"]
                        as? [String: Any],
                      let childWaist = number(dimensions, childField) else {
                    constructionModeByIndex.removeAll()
                    break
                }
                let tolerance = max(0.5, max(childWaist, parentWaist) * 0.01)
                constructionModeByIndex[index] = childWaist > parentWaist + tolerance
                    ? "GATHER" : "JOIN"
            }
            guard constructionModeByIndex.count == skirtIndices.count else {
                continue
            }

            for (zeroBasedOrder, index) in skirtIndices.enumerated() {
                var attributes = nodes[index]["attributes"]
                    as? [String: Any] ?? [:]
                let order = zeroBasedOrder + 1
                let mode = constructionModeByIndex[index] ?? "JOIN"
                let contract: [String: Any] = [
                    "state": "PROPOSED",
                    "waist_stack_state": "PROPOSED",
                    "waist_stack_parent": bodyID,
                    "waist_stack_id": stackID,
                    "waist_stack_order": order,
                    "waist_stack_construction_mode": mode,
                    "dimensions_changed": false,
                    "observed_authority_changed": false,
                    "not_observed_from_front": true,
                    "breaks_when": "rear/side evidence, a reviewed waistband/yoke, or an explicit multi-layer seam topology is supplied",
                ]
                var provenance = attributes["waist_join_provenance"]
                    as? [String: Any] ?? [:]
                provenance["state"] = "PROPOSED"
                provenance["waist_stack_state"] = "PROPOSED"
                provenance["waist_stack_parent"] = bodyID
                provenance["waist_stack_id"] = stackID
                provenance["waist_stack_order"] = order
                provenance["waist_stack_construction_mode"] = mode
                provenance["waist_stack"] = contract
                provenance["dimensions_changed"] = false
                provenance["observed_authority_changed"] = false
                provenance["not_observed_from_front"] = true
                attributes["waist_stack_state"] = "PROPOSED"
                attributes["waist_stack_parent"] = bodyID
                attributes["waist_stack_id"] = stackID
                attributes["waist_stack_order"] = order
                attributes["waist_stack_construction_mode"] = mode
                attributes["attached_to"] = bodyID
                attributes["garment_unit"] = bodyUnit
                attributes["attachment_state"] = "PROPOSED"
                if mode == "GATHER" {
                    attributes["waist_join_mode"] = "GATHER"
                } else {
                    // The parts-IR contract represents an ordinary JOIN by
                    // absence; only the exceptional GATHER mode is explicit.
                    attributes.removeValue(forKey: "waist_join_mode")
                }
                attributes["waist_join_state"] = "PROPOSED"
                attributes["waist_join_provenance"] = provenance
                nodes[index]["attributes"] = attributes
            }

            records.append([
                "kind": "PROPOSED_SHARED_WAIST_STACK_NORMALIZATION",
                "state": "PROPOSED_NORMALIZATION",
                "waist_stack_id": stackID,
                "waist_stack_parent": bodyID,
                "ordered_child_ids": orderedIDs,
                "order_rule": "layer_then_node_id",
                "construction_modes": orderedIDs.enumerated().reduce(
                    into: [String: String]()) { result, pair in
                        result[pair.element] = constructionModeByIndex[
                            skirtIndices[pair.offset]] ?? "JOIN"
                    },
                "dimensions_changed": false,
                "observed_authority_changed": false,
                "not_observed_from_front": true,
            ])
            assumptions.append(
                "\(orderedIDs.joined(separator: ", ")) form the bounded PROPOSED parallel waist stack \(stackID) at \(bodyID); all dimensions and direct BODY_SHELL attachments are preserved")
        }
        return (records, assumptions)
    }

    /// Resolve a proposed BODY_SHELL-to-skirt waist without pretending that
    /// unequal model dimensions are equal. Parser fallbacks may be replaced by
    /// the explicit opposite boundary. If both values came from the model and
    /// the skirt edge is longer, retain both values and type the relation as a
    /// PROPOSED GATHER. A shorter skirt edge remains unresolved.
    private static func reconcileBoundedPreviewWaistJoinBoundaries(
        nodes: inout [[String: Any]]
    ) -> (records: [[String: Any]], assumptions: [String]) {
        let indexByID: [String: Int] = Dictionary(
            uniqueKeysWithValues: nodes.indices.compactMap { index
                -> (String, Int)? in
                guard let id = nodes[index]["node_id"] as? String else {
                    return nil
                }
                return (id, index)
            })
        func number(_ dimensions: [String: Any], _ field: String) -> Double? {
            guard let value = dimensions[field] as? NSNumber,
                  CFGetTypeID(value) != CFBooleanGetTypeID(),
                  value.doubleValue.isFinite, value.doubleValue > 0 else {
                return nil
            }
            return value.doubleValue
        }
        func parserFallback(_ provenance: [String: Any]?) -> Bool {
            guard let provenance else { return false }
            return provenance["model_supplied"] as? Bool == false &&
                provenance["completed"] as? Bool == true &&
                provenance["dimension_source"] as? String ==
                    "BOUNDED_PREVIEW_MANNEQUIN_DERIVED_PROPOSAL"
        }

        var records: [[String: Any]] = []
        var assumptions: [String] = []
        for childIndex in nodes.indices {
            let childKind = nodes[childIndex]["kind"] as? String ?? ""
            guard ["FLARE", "FRUSTUM", "TUBE"].contains(childKind),
                  let childID = nodes[childIndex]["node_id"] as? String,
                  var childAttributes = nodes[childIndex]["attributes"]
                    as? [String: Any],
                  let parentID = childAttributes["attached_to"] as? String,
                  let parentIndex = indexByID[parentID],
                  nodes[parentIndex]["kind"] as? String == "BODY_SHELL",
                  var parentAttributes = nodes[parentIndex]["attributes"]
                    as? [String: Any],
                  var childDimensions = nodes[childIndex]["dimensions"]
                    as? [String: Any],
                  var parentDimensions = nodes[parentIndex]["dimensions"]
                    as? [String: Any],
                  var childProvenance = childAttributes["dimension_provenance"]
                    as? [String: [String: Any]],
                  var parentProvenance = parentAttributes["dimension_provenance"]
                    as? [String: [String: Any]]
            else { continue }
            // A straight skirt is often represented by the compact image
            // model as TUBE rather than FLARE.  It has one circumference
            // boundary and is still a valid waist child.  Explicit leg-sided
            // or trouser-typed TUBEs remain owned by the trouser normalizer;
            // they must never be converted into gathered skirts here.
            if childKind == "TUBE" {
                let text = [
                    childAttributes["placement"] as? String,
                    childAttributes["shape"] as? String,
                    childAttributes["detail_role"] as? String,
                ].compactMap { $0 }.joined(separator: " ").lowercased()
                let words = Set(text.split {
                    !$0.isLetter && !$0.isNumber
                }.map(String.init))
                let trouserWords: Set<String> = [
                    "trouser", "trousers", "pant", "pants", "leg",
                    "legging", "leggings",
                ]
                if explicitVisionSide(nodes[childIndex]) != nil ||
                    !words.isDisjoint(with: trouserWords) {
                    continue
                }
            }
            let childField = childKind == "TUBE"
                ? "circumference_cm" : "top_circumference_cm"
            guard let childWaist = number(childDimensions, childField) else {
                continue
            }
            let parentField = [
                "bottom_circumference_cm", "waist_circumference_cm",
                "circumference_cm",
            ].first { number(parentDimensions, $0) != nil }
            guard let parentField,
                  let parentWaist = number(parentDimensions, parentField) else {
                continue
            }
            let tolerance = max(0.5, max(childWaist, parentWaist) * 0.01)
            guard abs(childWaist - parentWaist) > tolerance else { continue }
            let childIsFallback = parserFallback(
                childProvenance[childField])
            let parentIsFallback = parserFallback(parentProvenance[parentField])

            if childIsFallback || parentIsFallback {
                let targetNodeID: String
                let targetField: String
                let sourceNodeID: String
                let sourceField: String
                let previous: Double
                let resolved: Double
                if childIsFallback {
                    targetNodeID = childID
                    targetField = childField
                    sourceNodeID = parentID
                    sourceField = parentField
                    previous = childWaist
                    resolved = parentWaist
                    childDimensions[targetField] = resolved
                    childProvenance[targetField] = [
                        "state": "PROPOSED",
                        "dimension_source": "PROPOSED_RELATION_DERIVED",
                        "basis": "explicit waist attachment plus one shared preview boundary; only a parser-completed value was replaced",
                        "breaks_when": "the attachment, reviewed waist seam, or calibrated dimensions change",
                        "source_node_id": sourceNodeID,
                        "source_dimension": sourceField,
                        "replaced_fallback_value_cm": previous,
                        "not_measured_from_image": true,
                        "model_supplied": false,
                        "completed": true,
                    ]
                    childAttributes["dimension_provenance"] = childProvenance
                    nodes[childIndex]["dimensions"] = childDimensions
                    nodes[childIndex]["attributes"] = childAttributes
                } else {
                    targetNodeID = parentID
                    targetField = parentField
                    sourceNodeID = childID
                    sourceField = childField
                    previous = parentWaist
                    resolved = childWaist
                    parentDimensions[targetField] = resolved
                    parentProvenance[targetField] = [
                        "state": "PROPOSED",
                        "dimension_source": "PROPOSED_RELATION_DERIVED",
                        "basis": "explicit waist attachment plus one shared preview boundary; only a parser-completed value was replaced",
                        "breaks_when": "the attachment, reviewed waist seam, or calibrated dimensions change",
                        "source_node_id": sourceNodeID,
                        "source_dimension": sourceField,
                        "replaced_fallback_value_cm": previous,
                        "not_measured_from_image": true,
                        "model_supplied": false,
                        "completed": true,
                    ]
                    parentAttributes["dimension_provenance"] = parentProvenance
                    nodes[parentIndex]["dimensions"] = parentDimensions
                    nodes[parentIndex]["attributes"] = parentAttributes
                }
                records.append([
                    "kind": "BOUNDED_WAIST_JOIN_BOUNDARY_NORMALIZATION",
                    "state": "PROPOSED_NORMALIZATION",
                    "source_part_id": sourceNodeID,
                    "target_part_id": targetNodeID,
                    "source_dimension": sourceField,
                    "target_dimension": targetField,
                    "previous_preview_value_cm": previous,
                    "resolved_preview_value_cm": resolved,
                    "not_measured_from_image": true,
                    "model_values_changed": false,
                ])
                assumptions.append(
                    "\(targetNodeID).\(targetField) parser fallback was matched to the explicit \(sourceNodeID).\(sourceField) waist boundary; no model value was changed")
                continue
            }

            let ratio = childWaist / parentWaist
            guard childWaist > parentWaist, ratio > 1, ratio <= 8 else {
                continue
            }
            childAttributes["waist_join_mode"] = "GATHER"
            childAttributes["waist_join_state"] = "PROPOSED"
            var gatherProvenance = childAttributes["waist_join_provenance"]
                as? [String: Any] ?? [:]
            gatherProvenance.merge([
                "state": "PROPOSED",
                "basis": "the model-proposed skirt top is longer than the model-proposed attached BODY_SHELL waist; GATHER is one falsifiable construction candidate",
                "breaks_when": "a reviewed pleat, dart, ease, separate waistband, calibrated dimension, or different attachment is supplied",
                "source_length_cm": childWaist,
                "target_length_cm": parentWaist,
                "fullness_cm": childWaist - parentWaist,
                "ratio": ratio,
                "not_observed_from_front": true,
                "dimensions_changed": false,
            ]) { _, gatheredValue in gatheredValue }
            childAttributes["waist_join_provenance"] = gatherProvenance
            nodes[childIndex]["attributes"] = childAttributes
            records.append([
                "kind": "PROPOSED_WAIST_GATHER_RELATION",
                "state": "PROPOSED_NORMALIZATION",
                "source_part_id": childID,
                "target_part_id": parentID,
                "source_length_cm": childWaist,
                "target_length_cm": parentWaist,
                "fullness_cm": childWaist - parentWaist,
                "ratio": ratio,
                "not_observed_from_front": true,
                "dimensions_changed": false,
            ])
            assumptions.append(
                "\(childID) retains its \(childWaist)cm proposed top edge and uses a PROPOSED GATHER to the \(parentWaist)cm \(parentID) waist; pleat/ease/waistband alternatives remain unobserved")
        }
        return (records, assumptions)
    }

    private static func explicitVisionSide(_ node: [String: Any]) -> String? {
        let attributes = node["attributes"] as? [String: Any] ?? [:]
        if let side = boundedString(attributes["side"], limit: 24)?.lowercased(),
           side == "left" || side == "right" { return side }
        let text = [node["node_id"] as? String,
                    attributes["placement"] as? String]
            .compactMap { $0 }.joined(separator: " ").lowercased()
        let words = Set(text.split { !$0.isLetter && !$0.isNumber }.map(String.init))
        let hasLeft = words.contains("left")
        let hasRight = words.contains("right")
        if hasLeft != hasRight { return hasLeft ? "left" : "right" }
        return nil
    }

    /// A front view can visibly establish that a singular surface sits over
    /// one side of an already typed left/right carrier even though it cannot
    /// establish how that surface is sewn at the rear. Compact vision models
    /// commonly address the pre-expansion trouser pair, which becomes two
    /// ``attached_to`` targets after pair normalization, or omit the address
    /// altogether. Preserve the visible side as geometry and select a carrier
    /// only when exactly one lower-layer node has that same explicit side.
    ///
    /// This closes an address, not a construction fact: the selected relation
    /// remains PROPOSED, the original model value/unit is retained, and a rear
    /// view or human construction choice can replace it. Centre/bilateral or
    /// otherwise ambiguous surfaces continue to fail closed downstream.
    private static func normalizeVisionVisibleSideAttachments(
        nodes: inout [[String: Any]]
    ) -> (records: [[String: Any]], assumptions: [String]) {
        let nodeIDs = Set(nodes.compactMap { $0["node_id"] as? String })
        var records: [[String: Any]] = []
        var assumptions: [String] = []

        for index in nodes.indices {
            guard nodes[index]["kind"] as? String == "OVERLAY",
                  let nodeID = nodes[index]["node_id"] as? String,
                  let side = explicitVisionSide(nodes[index]),
                  var attributes = nodes[index]["attributes"] as? [String: Any]
            else { continue }

            let childLayer = nodes[index]["layer"] as? Int ?? 0
            let rawAttached = attributes["attached_to"]
            let addressedTargets: [String]
            if let target = rawAttached as? String {
                addressedTargets = [target]
            } else if let targets = rawAttached as? [String] {
                addressedTargets = targets
            } else if let targets = rawAttached as? [Any] {
                addressedTargets = targets.compactMap { $0 as? String }
            } else {
                addressedTargets = []
            }

            let eligibleKinds: Set<String> = [
                "TUBE", "BODY_SHELL", "FLARE", "FRUSTUM", "YOKE", "BAND",
            ]
            let candidates = nodes.compactMap { candidate -> String? in
                guard let candidateID = candidate["node_id"] as? String,
                      candidateID != nodeID,
                      nodeIDs.contains(candidateID),
                      eligibleKinds.contains(candidate["kind"] as? String ?? ""),
                      (candidate["layer"] as? Int ?? 0) < childLayer,
                      explicitVisionSide(candidate) == side else { return nil }
                if !addressedTargets.isEmpty,
                   !addressedTargets.contains(candidateID) { return nil }
                return candidateID
            }
            guard candidates.count == 1, let resolved = candidates.first else {
                continue
            }
            if addressedTargets.count == 1,
               addressedTargets.first == resolved { continue }

            if let rawAttached {
                attributes["model_attached_to"] = rawAttached
            } else {
                attributes["model_attached_to"] = NSNull()
            }
            if let modelUnit = attributes["garment_unit"] as? String {
                attributes["model_garment_unit"] = modelUnit
            }
            attributes["attached_to"] = resolved
            attributes["attachment_state"] =
                "PROPOSED_VISIBLE_SIDE_CARRIER"
            attributes["attachment_provenance"] = [
                "state": "PROPOSED",
                "visible_side": side,
                "resolved_node_id": resolved,
                "basis": "exactly one explicitly same-side lower-layer carrier remains after typed pair expansion",
                "breaks_when": "a rear/inside view, reviewed detachable-wrap construction, different layer ownership, or explicit attachment target is supplied",
                "front_visible_geometry_preserved": true,
                "sewn_join_observed": false,
                "rear_construction_observed": false,
                "requires_human_approval": true,
            ]
            nodes[index]["attributes"] = attributes
            records.append([
                "kind": "VISIBLE_SIDE_ATTACHMENT_NORMALIZATION",
                "state": "PROPOSED_NORMALIZATION",
                "source_part_id": nodeID,
                "visible_side": side,
                "resolved_node_id": resolved,
                "model_target_count": addressedTargets.count,
                "sewn_join_observed": false,
                "rear_construction_observed": false,
                "requires_human_approval": true,
            ])
            assumptions.append(
                "\(nodeID) is visibly \(side)-sided and has exactly one lower-layer \(side) carrier, \(resolved); the address is a PROPOSED front-geometry relation, not an observed seam or rear construction")
        }
        return (records, assumptions)
    }

    /// A compact vision model sometimes attaches a visible sleeve to the
    /// visible yoke, shoulder overlay or trim that visually surrounds its
    /// armhole. The drafting bridge needs the BODY_SHELL armhole root. Follow
    /// only an explicit, acyclic attached_to chain to one BODY_SHELL and
    /// preserve the model target as PROPOSED provenance. Detached sleeves and
    /// ambiguous multi-body candidates remain unresolved.
    private static func normalizeVisionSleeveAnchors(
        nodes: inout [[String: Any]]
    ) -> (records: [[String: Any]], assumptions: [String]) {
        let indexByID: [String: Int] = Dictionary(
            uniqueKeysWithValues: nodes.indices.compactMap { index
                -> (String, Int)? in
                guard let id = nodes[index]["node_id"] as? String else {
                    return nil
                }
                return (id, index)
            })
        let bodyIDs = nodes.compactMap { node -> String? in
            guard node["kind"] as? String == "BODY_SHELL" else { return nil }
            return node["node_id"] as? String
        }
        var records: [[String: Any]] = []
        var assumptions: [String] = []
        for index in nodes.indices where nodes[index]["kind"] as? String == "SLEEVE" {
            guard var attributes = nodes[index]["attributes"] as? [String: Any],
                  let nodeID = nodes[index]["node_id"] as? String,
                  let proposedParent = attributes["attached_to"] as? String,
                  let parentIndex = indexByID[proposedParent]
            else { continue }
            let shape = (attributes["shape"] as? String ?? "").lowercased()
            if shape == "detached" { continue }
            let parentKind = nodes[parentIndex]["kind"] as? String ?? ""
            if parentKind == "BODY_SHELL" || parentKind == "SLEEVE" { continue }

            var current = proposedParent
            var visited = Set<String>()
            var resolvedBody: String?
            while let currentIndex = indexByID[current],
                  visited.insert(current).inserted {
                if nodes[currentIndex]["kind"] as? String == "BODY_SHELL" {
                    resolvedBody = current
                    break
                }
                guard let currentAttributes = nodes[currentIndex]["attributes"]
                        as? [String: Any],
                      let next = currentAttributes["attached_to"] as? String
                else { break }
                current = next
            }
            if resolvedBody == nil, bodyIDs.count == 1 {
                resolvedBody = bodyIDs[0]
            }
            guard let bodyID = resolvedBody else { continue }
            attributes["model_attached_to"] = proposedParent
            attributes["attached_to"] = bodyID
            attributes["attachment_state"] =
                "PROPOSED_ARMHOLE_CARRIER_NORMALIZATION"
            attributes["sleeve_anchor_normalization"] = [
                "state": "PROPOSED_NORMALIZATION",
                "model_target_id": proposedParent,
                "model_target_kind": parentKind,
                "resolved_body_shell_id": bodyID,
                "not_observed_from_front": true,
                "basis": "explicit acyclic attachment chain or the only BODY_SHELL in this front candidate",
                "breaks_when": "another BODY_SHELL, a detached-sleeve anchor, or reviewed armhole topology is supplied",
            ]
            nodes[index]["attributes"] = attributes
            records.append([
                "kind": "SLEEVE_ARMHOLE_CARRIER_NORMALIZATION",
                "state": "PROPOSED_NORMALIZATION",
                "source_part_id": nodeID,
                "model_target_id": proposedParent,
                "model_target_kind": parentKind,
                "resolved_body_shell_id": bodyID,
                "not_observed_from_front": true,
            ])
            assumptions.append(
                "\(nodeID) was re-addressed from visible carrier \(proposedParent) to BODY_SHELL \(bodyID) for the proposed armhole bridge; this is not an observed seam")
        }
        return (records, assumptions)
    }

    /// A segmented sleeve has one physical seam boundary: the parent cuff and
    /// the child upper edge. Parser fallbacks may be replaced by the explicit
    /// relation. Two model-supplied values remain separate when the child can
    /// be gathered into the cuff; otherwise only the PROPOSED child preview is
    /// redrafted, retaining the model value and evidence in provenance.
    private static func reconcileBoundedPreviewSleeveJoinBoundaries(
        nodes: inout [[String: Any]]
    ) -> (records: [[String: Any]], assumptions: [String]) {
        let indexByID: [String: Int] = Dictionary(
            uniqueKeysWithValues: nodes.indices.compactMap { index
                -> (String, Int)? in
                guard let id = nodes[index]["node_id"] as? String else {
                    return nil
                }
                return (id, index)
            })
        func number(_ dimensions: [String: Any], _ field: String) -> Double? {
            guard let value = dimensions[field] as? NSNumber,
                  CFGetTypeID(value) != CFBooleanGetTypeID(),
                  value.doubleValue.isFinite, value.doubleValue > 0 else {
                return nil
            }
            return value.doubleValue
        }
        func isParserFallback(_ value: [String: Any]?) -> Bool {
            guard let value else { return false }
            return value["model_supplied"] as? Bool == false &&
                value["completed"] as? Bool == true &&
                value["dimension_source"] as? String ==
                    "BOUNDED_PREVIEW_MANNEQUIN_DERIVED_PROPOSAL"
        }
        func isObserved(_ value: [String: Any]?) -> Bool {
            guard let value else { return false }
            return ["state", "authority", "verdict", "kind"].contains {
                (value[$0] as? String)?.uppercased() == "OBSERVED"
            }
        }

        var records: [[String: Any]] = []
        var assumptions: [String] = []
        for childIndex in nodes.indices
            where nodes[childIndex]["kind"] as? String == "SLEEVE" {
            guard let childID = nodes[childIndex]["node_id"] as? String,
                  var childAttributes = nodes[childIndex]["attributes"]
                    as? [String: Any],
                  let parentID = childAttributes["attached_to"] as? String,
                  let parentIndex = indexByID[parentID],
                  nodes[parentIndex]["kind"] as? String == "SLEEVE",
                  var parentAttributes = nodes[parentIndex]["attributes"]
                    as? [String: Any],
                  var childDimensions = nodes[childIndex]["dimensions"]
                    as? [String: Any],
                  var parentDimensions = nodes[parentIndex]["dimensions"]
                    as? [String: Any],
                  var childProvenance = childAttributes["dimension_provenance"]
                    as? [String: [String: Any]],
                  var parentProvenance = parentAttributes["dimension_provenance"]
                    as? [String: [String: Any]],
                  let childUpper = number(childDimensions,
                    "upper_circumference_cm"),
                  let parentCuff = number(parentDimensions,
                    "cuff_circumference_cm")
            else { continue }

            // Keep this gate aligned with parts_ir_topology.py. The vision
            // model often says "lower sleeve" without spelling out JOIN;
            // topology already treats that as an extension. Reconcile the
            // shared boundary before serialization instead of letting the
            // later Python inference discover an uncorrected length mismatch.
            let typedRelation = (childAttributes["attachment_relation"]
                as? String)?.trimmingCharacters(in: .whitespacesAndNewlines)
                .uppercased() ?? ""
            let relationText = [
                "placement", "shape", "detail_role", "visible_basis",
            ]
                .compactMap { childAttributes[$0] as? String }
                .joined(separator: " ").lowercased()
            let explicitExtension = [
                "lower sleeve", "sleeve extension", "cuff extension",
                "gauntlet", "forearm",
            ].contains { relationText.contains($0) }
            guard typedRelation == "JOIN" ||
                    (typedRelation.isEmpty && explicitExtension) else {
                continue
            }
            if typedRelation.isEmpty {
                childAttributes["attachment_relation"] = "JOIN"
                childAttributes["attachment_relation_state"] = "PROPOSED"
                nodes[childIndex]["attributes"] = childAttributes
                records.append([
                    "kind": "PROPOSED_SLEEVE_EXTENSION_RELATION_DERIVED",
                    "state": "PROPOSED",
                    "source_part_id": childID,
                    "target_part_id": parentID,
                    "attachment_relation": "JOIN",
                    "dimensions_changed": false,
                    "not_observed_from_front": true,
                ])
                assumptions.append(
                    "\(childID) was typed as a PROPOSED sleeve-extension JOIN from lower-sleeve placement semantics; the relation is not observed")
            }

            let childIsFallback = isParserFallback(
                childProvenance["upper_circumference_cm"])
            let parentIsFallback = isParserFallback(
                parentProvenance["cuff_circumference_cm"])
            let tolerance = max(0.5, max(childUpper, parentCuff) * 0.01)
            guard abs(childUpper - parentCuff) > tolerance else { continue }

            if !childIsFallback && !parentIsFallback {
                let ratio = childUpper / parentCuff
                if childUpper > parentCuff, ratio <= 3 {
                    let provenance: [String: Any] = [
                        "state": "PROPOSED",
                        "authority": "PROPOSED_RELATION_DERIVED",
                        "relation": "GATHER",
                        "source_node_id": childID,
                        "source_dimension": "upper_circumference_cm",
                        "source_length_cm": childUpper,
                        "target_node_id": parentID,
                        "target_dimension": "cuff_circumference_cm",
                        "target_length_cm": parentCuff,
                        "ratio": ratio,
                        "dimensions_changed": false,
                        "not_observed_from_front": true,
                        "not_measured_from_image": true,
                        "construction_alternatives_unobserved": [
                            "PLEAT", "CUFF_YOKE",
                        ],
                        "basis": "the child upper edge is longer than the parent cuff and fits the bounded gather ratio; both boundary values and their original evidence are retained",
                        "breaks_when": "an observed seam, reviewed pattern edge, material limit, or calibrated circumference rejects the proposed gather",
                    ]
                    childAttributes["attachment_relation"] = "GATHER"
                    childAttributes["attachment_relation_state"] = "PROPOSED"
                    childAttributes["sleeve_join_mode"] = "GATHER"
                    childAttributes["sleeve_join_state"] = "PROPOSED"
                    childAttributes["sleeve_join_provenance"] = provenance
                    nodes[childIndex]["attributes"] = childAttributes
                    records.append([
                        "kind": "PROPOSED_SLEEVE_GATHER_RELATION",
                        "state": "PROPOSED",
                        "source_part_id": childID,
                        "target_part_id": parentID,
                        "source_length_cm": childUpper,
                        "target_length_cm": parentCuff,
                        "ratio": ratio,
                        "dimensions_changed": false,
                        "not_observed_from_front": true,
                    ])
                    assumptions.append(
                        "\(childID) upper edge remains \(childUpper)cm and is PROPOSED as a \(ratio)x GATHER into \(parentID) cuff \(parentCuff)cm; the relation is not observed and neither boundary value was changed")
                    continue
                }

                let originalProvenance = childProvenance[
                    "upper_circumference_cm"] ?? [:]
                if isObserved(originalProvenance) {
                    childAttributes["sleeve_join_mode"] =
                        "OBSERVED_BOUNDARY_REQUIRES_REVIEW"
                    childAttributes["sleeve_join_state"] = "REVIEW"
                    childAttributes["sleeve_join_provenance"] = [
                        "state": "REVIEW",
                        "authority": "OBSERVED_PRESERVED",
                        "source_node_id": childID,
                        "source_length_cm": childUpper,
                        "target_node_id": parentID,
                        "target_length_cm": parentCuff,
                        "dimensions_changed": false,
                        "not_observed_from_front": false,
                        "why": "the child boundary is OBSERVED and cannot be changed by preview relation repair",
                    ]
                    nodes[childIndex]["attributes"] = childAttributes
                    records.append([
                        "kind": "OBSERVED_SLEEVE_JOIN_MISMATCH_REQUIRES_REVIEW",
                        "state": "REVIEW",
                        "source_part_id": childID,
                        "target_part_id": parentID,
                        "source_length_cm": childUpper,
                        "target_length_cm": parentCuff,
                        "dimensions_changed": false,
                    ])
                    assumptions.append(
                        "\(childID).upper_circumference_cm is OBSERVED and was not changed to satisfy the proposed SLEEVE relation")
                    continue
                }

                childDimensions["upper_circumference_cm"] = parentCuff
                childProvenance["upper_circumference_cm"] = [
                    "state": "PROPOSED",
                    "authority": "PROPOSED_RELATION_DERIVED",
                    "dimension_source": "PROPOSED_RELATION_DERIVED",
                    "basis": "preview-only redraft of the child upper edge to the parent cuff after the proposed model boundaries could not form a bounded gather",
                    "breaks_when": "an observed seam, reviewed GATHER/PLEAT/CUFF_YOKE construction, or calibrated boundary is supplied",
                    "source_node_id": parentID,
                    "source_dimension": "cuff_circumference_cm",
                    "original_model_value_cm": childUpper,
                    "original_model_provenance": originalProvenance,
                    "resolved_preview_value_cm": parentCuff,
                    "not_measured_from_image": true,
                    "model_supplied": false,
                    "completed": true,
                ]
                let provenance: [String: Any] = [
                    "state": "PROPOSED",
                    "authority": "PROPOSED_RELATION_DERIVED",
                    "relation": "JOIN",
                    "source_node_id": childID,
                    "source_dimension": "upper_circumference_cm",
                    "original_source_length_cm": childUpper,
                    "target_node_id": parentID,
                    "target_dimension": "cuff_circumference_cm",
                    "target_length_cm": parentCuff,
                    "resolved_source_length_cm": parentCuff,
                    "original_model_provenance": originalProvenance,
                    "dimensions_changed": true,
                    "changed_dimension": "upper_circumference_cm",
                    "not_observed_from_front": true,
                    "not_measured_from_image": true,
                    "construction_alternatives_unobserved": [
                        "GATHER", "PLEAT", "CUFF_YOKE",
                    ],
                    "basis": "preview relation repair only; construction choice is unobserved",
                    "breaks_when": "a reviewed sleeve construction or calibrated seam boundary is supplied",
                ]
                childAttributes["attachment_relation"] = "JOIN"
                childAttributes["attachment_relation_state"] = "PROPOSED"
                childAttributes["sleeve_join_mode"] =
                    "PROPOSED_RELATION_DERIVED"
                childAttributes["sleeve_join_state"] = "PROPOSED"
                childAttributes["sleeve_join_provenance"] = provenance
                childAttributes["dimension_provenance"] = childProvenance
                nodes[childIndex]["dimensions"] = childDimensions
                nodes[childIndex]["attributes"] = childAttributes
                records.append([
                    "kind": "PROPOSED_SLEEVE_JOIN_PREVIEW_REDRAFT",
                    "state": "PROPOSED",
                    "source_part_id": childID,
                    "target_part_id": parentID,
                    "original_source_length_cm": childUpper,
                    "resolved_source_length_cm": parentCuff,
                    "target_length_cm": parentCuff,
                    "ratio": ratio,
                    "dimensions_changed": true,
                    "changed_dimension": "upper_circumference_cm",
                    "construction_alternatives_unobserved": [
                        "GATHER", "PLEAT", "CUFF_YOKE",
                    ],
                    "not_observed_from_front": true,
                ])
                assumptions.append(
                    "\(childID).upper_circumference_cm was redrafted from the retained model proposal \(childUpper)cm to the parent cuff \(parentCuff)cm for a PROPOSED preview JOIN; GATHER, PLEAT, and CUFF_YOKE remain unobserved alternatives")
                continue
            }

            let targetNodeID: String
            let targetField: String
            let sourceNodeID: String
            let sourceField: String
            let previous: Double
            let resolved: Double
            if childIsFallback {
                // If both are fallbacks, the already-rooted parent cuff is the
                // deterministic carrier boundary for the extension.
                targetNodeID = childID
                targetField = "upper_circumference_cm"
                sourceNodeID = parentID
                sourceField = "cuff_circumference_cm"
                previous = childUpper
                resolved = parentCuff
                childDimensions[targetField] = resolved
                childProvenance[targetField] = [
                    "state": "PROPOSED",
                    "dimension_source": "PROPOSED_RELATION_DERIVED",
                    "basis": "explicit SLEEVE JOIN has one shared parent-cuff/child-upper boundary; only a parser-completed preview value was replaced",
                    "breaks_when": "the JOIN, reviewed pattern edge, calibrated measurement, or model-supplied boundary changes",
                    "source_node_id": sourceNodeID,
                    "source_dimension": sourceField,
                    "replaced_fallback_value_cm": previous,
                    "not_measured_from_image": true,
                    "model_supplied": false,
                    "completed": true,
                ]
                childAttributes["dimension_provenance"] = childProvenance
                nodes[childIndex]["dimensions"] = childDimensions
                nodes[childIndex]["attributes"] = childAttributes
            } else {
                targetNodeID = parentID
                targetField = "cuff_circumference_cm"
                sourceNodeID = childID
                sourceField = "upper_circumference_cm"
                previous = parentCuff
                resolved = childUpper
                parentDimensions[targetField] = resolved
                parentProvenance[targetField] = [
                    "state": "PROPOSED",
                    "dimension_source": "PROPOSED_RELATION_DERIVED",
                    "basis": "explicit SLEEVE JOIN has one shared parent-cuff/child-upper boundary; only a parser-completed preview value was replaced",
                    "breaks_when": "the JOIN, reviewed pattern edge, calibrated measurement, or model-supplied boundary changes",
                    "source_node_id": sourceNodeID,
                    "source_dimension": sourceField,
                    "replaced_fallback_value_cm": previous,
                    "not_measured_from_image": true,
                    "model_supplied": false,
                    "completed": true,
                ]
                parentAttributes["dimension_provenance"] = parentProvenance
                nodes[parentIndex]["dimensions"] = parentDimensions
                nodes[parentIndex]["attributes"] = parentAttributes
            }
            let detail: [String: Any] = [
                "state": "PROPOSED_NORMALIZATION",
                "target_node_id": targetNodeID,
                "target_dimension": targetField,
                "source_node_id": sourceNodeID,
                "source_dimension": sourceField,
                "previous_preview_value_cm": previous,
                "resolved_preview_value_cm": resolved,
                "not_measured_from_image": true,
                "model_values_changed": false,
            ]
            if targetNodeID == childID {
                childAttributes = nodes[childIndex]["attributes"]
                    as? [String: Any] ?? childAttributes
                childAttributes["sleeve_join_boundary_normalization"] = detail
                nodes[childIndex]["attributes"] = childAttributes
            } else {
                parentAttributes = nodes[parentIndex]["attributes"]
                    as? [String: Any] ?? parentAttributes
                parentAttributes["sleeve_join_boundary_normalization"] = detail
                nodes[parentIndex]["attributes"] = parentAttributes
            }
            records.append([
                "kind": "BOUNDED_SLEEVE_JOIN_BOUNDARY_NORMALIZATION",
                "source_part_id": sourceNodeID,
                "target_part_id": targetNodeID,
                "source_dimension": sourceField,
                "target_dimension": targetField,
                "previous_preview_value_cm": previous,
                "resolved_preview_value_cm": resolved,
                "state": "PROPOSED_NORMALIZATION",
                "not_measured_from_image": true,
                "model_values_changed": false,
            ])
            assumptions.append(
                "(targetNodeID).(targetField) parser fallback was matched to the explicit (sourceNodeID).(sourceField) SLEEVE JOIN boundary; no model value or image measurement was changed")
        }
        return (records, assumptions)
    }

    /// The pattern bridge expands one bilateral sleeve node. Merge only an
    /// explicit left/right pair on one BODY_SHELL when all three drafting
    /// dimensions agree within a small preview tolerance. Unsafe pairs leave
    /// the graph and remain typed REVIEW artifacts instead of crashing every
    /// otherwise usable candidate downstream.
    private static func normalizeVisionSleevePair(
        nodes: inout [[String: Any]],
        typedOrnaments: inout [[String: Any]],
        unsupportedParts: inout [[String: Any]]
    ) -> (records: [[String: Any]], assumptions: [String]) {
        let sleeveIndices = nodes.indices.filter {
            nodes[$0]["kind"] as? String == "SLEEVE"
        }
        guard sleeveIndices.count == 2 else { return ([], []) }
        let source = sleeveIndices.map { nodes[$0] }
        let sleeveIDs = Set(source.compactMap { $0["node_id"] as? String })
        let hasSleeveToSleeveRelation = source.contains { node in
            guard let attributes = node["attributes"] as? [String: Any],
                  let parent = attributes["attached_to"] as? String else {
                return false
            }
            return sleeveIDs.contains(parent)
        }
        // Two nodes can be two physical segments of one sleeve. They are not
        // an unresolved left/right pair and must reach the typed JOIN/LAYER
        // compiler unchanged.
        if hasSleeveToSleeveRelation { return ([], []) }
        let parentIDs = source.compactMap {
            ($0["attributes"] as? [String: Any])?["attached_to"] as? String
        }
        let sides = source.compactMap(explicitVisionSide)
        let dimensions = source.compactMap { $0["dimensions"] as? [String: Double] }
        let keys = ["length_cm", "upper_circumference_cm", "cuff_circumference_cm"]
        let oneParent = parentIDs.count == 2 && Set(parentIDs).count == 1
            && nodes.contains {
                $0["node_id"] as? String == parentIDs.first
                    && $0["kind"] as? String == "BODY_SHELL"
            }
        let bilateral = sides.count == 2 && Set(sides) == Set(["left", "right"])
        let comparable = dimensions.count == 2 && keys.allSatisfy { key in
            guard let left = dimensions[0][key], let right = dimensions[1][key] else {
                return false
            }
            let tolerance = max(1.5, max(abs(left), abs(right)) * 0.05)
            return abs(left - right) <= tolerance
        }
        guard oneParent, bilateral, comparable, let parentID = parentIDs.first else {
            let sourceIDs = source.compactMap { $0["node_id"] as? String }
            for node in source {
                let attributes = node["attributes"] as? [String: Any] ?? [:]
                unsupportedParts.append([
                    "part_id": node["node_id"] as? String ?? "unresolved-sleeve",
                    "model_kind": "SLEEVE",
                    "placement": attributes["placement"] as? String ?? "arm",
                    "visible_basis": attributes["visible_basis"] as? String
                        ?? "vision model proposed one side of a sleeve pair",
                    "proposed_dimensions": node["dimensions"] as? [String: Any] ?? [:],
                    "dimensions_not_measured_from_image": true,
                    "state": "PROPOSED_UNCOMPILED",
                    "authority": "PROPOSED",
                    "review_code": "ASYMMETRIC_OR_UNRESOLVED_SLEEVE_PAIR",
                    "why": "left/right sleeves were not safely equivalent on one BODY_SHELL; they were not collapsed into a bilateral manufacturing node",
                    "source_part_ids": sourceIDs,
                    "manufacturing_ready": false,
                    "manufacturing_certified": false,
                ])
            }
            for index in sleeveIndices.sorted(by: >) { nodes.remove(at: index) }
            return ([[
                "kind": "SLEEVE_PAIR_REVIEW", "state": "PROPOSED",
                "source_part_ids": sourceIDs,
                "result": "UNCOMPILED_ASYMMETRIC_OR_UNRESOLVED",
            ]], [
                "the visible sleeve pair was not symmetric enough for the bilateral bridge and remains REVIEW-only",
            ])
        }

        let sourceIDs = source.compactMap { $0["node_id"] as? String }
        var mergedDimensions: [String: Double] = [:]
        var dimensionProvenance: [String: [String: Any]] = [:]
        for key in keys {
            guard let left = dimensions[0][key], let right = dimensions[1][key] else {
                continue
            }
            mergedDimensions[key] = (left + right) / 2.0
            dimensionProvenance[key] = [
                "state": "PROPOSED",
                "dimension_source": "PROPOSED_BILATERAL_SLEEVE_NORMALIZATION",
                "source_values_cm": [left, right],
                "source_part_ids": sourceIDs,
                "not_measured_from_image": true,
                "completed": false,
                "basis": "left/right model proposals agree within max(1.5cm, 5%) preview tolerance",
                "breaks_when": "asymmetric drafting or calibrated sleeve measurements are supplied",
            ]
        }
        let body = nodes.first { $0["node_id"] as? String == parentID }
        let bodyAttributes = body?["attributes"] as? [String: Any] ?? [:]
        let sourceBases = source.compactMap {
            ($0["attributes"] as? [String: Any])?["visible_basis"] as? String
        }
        var attributes = source[0]["attributes"] as? [String: Any] ?? [:]
        attributes["attached_to"] = parentID
        attributes["attachment_state"] = "PROPOSED"
        attributes["side"] = "bilateral"
        attributes["quantity"] = 2
        attributes["placement"] = "bilateral arms"
        attributes["visible_basis"] = sourceBases.joined(separator: "; ")
        attributes["detail_role"] = "bilateral_set_in_sleeve"
        attributes["dimension_provenance"] = dimensionProvenance
        if let unit = bodyAttributes["garment_unit"] as? String {
            attributes["garment_unit"] = unit
        }
        let mergedID = stableIdentifier(
            "bilateral-sleeve-\(parentID)", fallback: "bilateral-sleeve")
        let layer = source.compactMap { $0["layer"] as? Int }.max() ?? 0
        let merged: [String: Any] = [
            "node_id": mergedID, "kind": "SLEEVE",
            "dimensions": mergedDimensions, "ports": [], "layer": layer,
            "attributes": attributes,
        ]

        // Collapsing two visual left/right sleeves into one quantity=2 source
        // changes their graph address.  Any decoration or typed ornament that
        // explicitly named one source sleeve must follow that address change;
        // leaving the old id behind creates a dangling parent and makes an
        // otherwise valid candidate fail at topology.  Preserve the addressed
        // physical side as proposal provenance so an asymmetric cuff ruffle,
        // bow or flap does not silently become bilateral.
        let sideBySourceID: [String: String] = Dictionary(
            uniqueKeysWithValues: source.compactMap { sleeve in
                guard let sourceID = sleeve["node_id"] as? String,
                      let side = explicitVisionSide(sleeve) else { return nil }
                return (sourceID, side)
            })
        var remappedChildren: [[String: Any]] = []
        for index in nodes.indices where !sleeveIndices.contains(index) {
            guard var childAttributes = nodes[index]["attributes"]
                    as? [String: Any],
                  let oldParent = childAttributes["attached_to"] as? String,
                  sleeveIDs.contains(oldParent) else { continue }
            let side = sideBySourceID[oldParent] ?? "unresolved"
            childAttributes["model_attached_to"] = oldParent
            childAttributes["attached_to"] = mergedID
            childAttributes["parent_instance_address"] = [
                "state": "PROPOSED_NORMALIZATION",
                "source_parent_node_id": oldParent,
                "normalized_parent_node_id": mergedID,
                "physical_instance_side": side,
                "not_observed_from_front": true,
                "basis": "the explicitly addressed sleeve was normalized into one bilateral quantity=2 sleeve source",
                "breaks_when": "the sleeve pair is drafted asymmetrically or the child attachment is reviewed",
            ]
            nodes[index]["attributes"] = childAttributes
            remappedChildren.append([
                "child_part_id": nodes[index]["node_id"] as? String
                    ?? "unresolved-child",
                "source_parent_node_id": oldParent,
                "normalized_parent_node_id": mergedID,
                "physical_instance_side": side,
            ])
        }
        for index in typedOrnaments.indices {
            guard let oldParent = typedOrnaments[index]["attached_to"] as? String,
                  sleeveIDs.contains(oldParent) else { continue }
            let side = sideBySourceID[oldParent] ?? "unresolved"
            typedOrnaments[index]["model_attached_to"] = oldParent
            typedOrnaments[index]["attached_to"] = mergedID
            typedOrnaments[index]["parent_instance_address"] = [
                "state": "PROPOSED_NORMALIZATION",
                "source_parent_node_id": oldParent,
                "normalized_parent_node_id": mergedID,
                "physical_instance_side": side,
                "not_observed_from_front": true,
                "basis": "the explicitly addressed sleeve was normalized into one bilateral quantity=2 sleeve source",
                "breaks_when": "the sleeve pair is drafted asymmetrically or the ornament attachment is reviewed",
            ]
            remappedChildren.append([
                "child_part_id": typedOrnaments[index]["part_id"] as? String
                    ?? "unresolved-ornament",
                "source_parent_node_id": oldParent,
                "normalized_parent_node_id": mergedID,
                "physical_instance_side": side,
            ])
        }
        let insertionIndex = sleeveIndices.min() ?? nodes.endIndex
        for index in sleeveIndices.sorted(by: >) { nodes.remove(at: index) }
        nodes.insert(merged, at: min(insertionIndex, nodes.endIndex))
        return ([[
            "kind": "BILATERAL_SLEEVE_NORMALIZATION",
            "state": "PROPOSED_NORMALIZATION",
            "source_part_ids": sourceIDs,
            "result_part_id": mergedID,
            "side": "bilateral", "quantity": 2,
            "remapped_child_addresses": remappedChildren,
            "dimensions_not_measured_from_image": true,
        ]], [
            "left/right sleeve proposals were normalized to one bilateral quantity=2 SLEEVE; source ids, side-specific child addresses and values remain in normalization provenance",
        ])
    }

    /// Garter/thigh/arm bands seen in a front image express visual contact,
    /// not evidence of a sewn seam to the mannequin body or a limb panel.
    /// Preserve the band as a cuttable standalone accessory and keep the model
    /// target solely as PROPOSED contact provenance. This avoids inventing a
    /// waist JOIN when a model addresses a thigh strap to the BODY_SHELL.
    private static func separateVisionLimbBandContacts(
        nodes: inout [[String: Any]]
    ) -> (records: [[String: Any]], assumptions: [String]) {
        func words(_ values: [Any?]) -> Set<String> {
            Set(values.compactMap { $0 as? String }
                .joined(separator: " ").lowercased().split {
                    !$0.isLetter && !$0.isNumber
                }.map(String.init))
        }
        let contactWords: Set<String> = [
            "garter", "thigh", "armband", "armlet",
        ]
        var records: [[String: Any]] = []
        var assumptions: [String] = []
        for index in nodes.indices where nodes[index]["kind"] as? String == "BAND" {
            guard let nodeID = nodes[index]["node_id"] as? String,
                  var attributes = nodes[index]["attributes"] as? [String: Any],
                  let parentID = attributes["attached_to"] as? String else {
                continue
            }
            let address = words([
                nodeID, attributes["placement"], attributes["shape"],
                attributes["detail_role"],
            ])
            let saysStrap = address.contains("strap") &&
                !address.isDisjoint(with: ["thigh", "arm", "leg"])
            guard !address.isDisjoint(with: contactWords) || saysStrap else {
                continue
            }
            let parentKind = nodes.first {
                $0["node_id"] as? String == parentID
            }?["kind"] as? String ?? "UNKNOWN"
            let previousRole = attributes["detail_role"] as? String
            attributes.removeValue(forKey: "attached_to")
            attributes["model_attached_to"] = parentID
            if let previousRole { attributes["model_detail_role"] = previousRole }
            attributes["detail_role"] = address.contains("armband") ||
                address.contains("armlet")
                ? "standalone_armband" : "standalone_garter"
            attributes["garment_unit"] = stableIdentifier(
                "standalone-contact-\(nodeID)", fallback: "standalone-contact")
            attributes["attachment_state"] = "PROPOSED_STANDALONE_CONTACT"
            attributes["contact_target_provenance"] = [
                "state": "PROPOSED",
                "model_target_id": parentID,
                "model_target_kind": parentKind,
                "sewn_join_created": false,
                "not_observed_from_front": true,
                "basis": "front-image limb band indicates contact but does not reveal a sewn attachment",
                "breaks_when": "reviewed construction explicitly identifies a seam or integral casing",
            ]
            nodes[index]["attributes"] = attributes
            records.append([
                "kind": "LIMB_BAND_CONTACT_ACCESSORY",
                "state": "PROPOSED_NORMALIZATION",
                "source_part_id": nodeID,
                "contact_target_id": parentID,
                "contact_target_kind": parentKind,
                "detail_role": attributes["detail_role"] as? String ?? "",
                "join_created": false,
                "dimensions_changed": false,
                "not_observed_from_front": true,
            ])
            assumptions.append(
                "\(nodeID) remains a standalone limb-band CONTACT proposal; the front image does not establish a sewn JOIN to \(parentID)")
        }
        return (records, assumptions)
    }

    /// A visually separate belt whose proposed length does not match the typed
    /// waist cannot become a sewn BAND JOIN. Retain the belt and its attached
    /// decorations as a CONTACT/accessory review group without changing either
    /// dimension, allowing the garment structure itself to compile.
    private static func separateMismatchedVisionBeltContacts(
        nodes: inout [[String: Any]], unsupportedParts: inout [[String: Any]]
    ) -> (records: [[String: Any]], assumptions: [String]) {
        _ = unsupportedParts
        var records: [[String: Any]] = []
        var assumptions: [String] = []
        for index in nodes.indices where nodes[index]["kind"] as? String == "BAND" {
            let node = nodes[index]
            guard let nodeID = node["node_id"] as? String,
                  var attributes = node["attributes"] as? [String: Any],
                  attributes["model_kind"] == nil,
                  let placement = attributes["placement"] as? String,
                  !Set(placement.lowercased().split {
                    !$0.isLetter && !$0.isNumber
                  }.map(String.init)).isDisjoint(with: ["waist", "belt"]),
                  let parentID = attributes["attached_to"] as? String,
                  let parent = nodes.first(where: {
                    $0["node_id"] as? String == parentID
                        && $0["kind"] as? String == "BODY_SHELL"
                  }),
                  let bandDimensions = node["dimensions"] as? [String: Double],
                  let beltLength = bandDimensions["length_cm"],
                  let bodyDimensions = parent["dimensions"] as? [String: Double],
                  let waistLength = bodyDimensions["bottom_circumference_cm"]
                    ?? bodyDimensions["waist_circumference_cm"]
                    ?? bodyDimensions["circumference_cm"],
                  abs(beltLength - waistLength) > 0.5 else { continue }
            attributes.removeValue(forKey: "attached_to")
            attributes["attachment_state"] = "PROPOSED_STANDALONE_CONTACT"
            attributes["detail_role"] = "standalone_belt"
            attributes["garment_unit"] = stableIdentifier(
                "standalone-belt-\(nodeID)", fallback: "standalone-belt")
            attributes["contact_target_provenance"] = [
                "state": "PROPOSED",
                "target_node_id": parentID,
                "source": "model attached_to retained as contact provenance only",
                "sewn_join_created": false,
            ]
            nodes[index]["attributes"] = attributes
            records.append([
                "kind": "BELT_CONTACT_ACCESSORY",
                "state": "PROPOSED_NORMALIZATION",
                "source_part_id": nodeID,
                "contact_target_id": parentID,
                "standalone_garment_unit": attributes["garment_unit"] as? String ?? "",
                "belt_length_cm": beltLength,
                "target_waist_length_cm": waistLength,
                "detail_role": "standalone_belt",
                "join_created": false,
                "dimensions_changed": false,
            ])
            assumptions.append(
                "\(nodeID) remains an independent belt/accessory CONTACT proposal because its proposed length \(beltLength)cm does not match the \(waistLength)cm waist; no JOIN or silent resizing was performed")
        }
        return (records, assumptions)
    }

    /// A visible RUFFLE/FRILL/FLOUNCE is not an ordinary equal-length BAND.
    /// It needs one finished attachment boundary and a longer cut edge. Compact
    /// vision models frequently return only "sleeve ruffle" or "skirt frill"
    /// and may put the finished circumference in ``length_cm``. Preserve that
    /// model value, select a bounded preview alternative, and draft a longer
    /// proposal-only strip. The selected boundary and redraft remain explicit,
    /// falsifiable candidates; neither is promoted to observation or approval.
    private static func reconcileBoundedPreviewGatheredBandBoundaries(
        nodes: inout [[String: Any]]
    ) -> (records: [[String: Any]], assumptions: [String]) {
        func words(_ values: [Any?]) -> Set<String> {
            Set(values.compactMap { $0 as? String }
                .joined(separator: " ").lowercased().split {
                    !$0.isLetter && !$0.isNumber
                }.map(String.init))
        }
        func number(_ dimensions: [String: Any], _ names: [String]) -> Double? {
            for name in names {
                guard let value = dimensions[name] as? NSNumber,
                      CFGetTypeID(value) != CFBooleanGetTypeID(),
                      value.doubleValue.isFinite, value.doubleValue > 0 else {
                    continue
                }
                return value.doubleValue
            }
            return nil
        }
        func isObserved(_ value: [String: Any]?) -> Bool {
            guard let value else { return false }
            return ["state", "authority", "verdict", "kind"].contains {
                (value[$0] as? String)?.uppercased() == "OBSERVED"
            }
        }

        let byID: [String: [String: Any]] = Dictionary(
            uniqueKeysWithValues: nodes.compactMap { node
                -> (String, [String: Any])? in
                guard let id = node["node_id"] as? String else { return nil }
                return (id, node)
            })
        let gatherWords: Set<String> = [
            "ruffle", "ruffled", "frill", "frilled", "flounce",
            "flounced", "gather", "gathered",
        ]
        var records: [[String: Any]] = []
        var assumptions: [String] = []

        for index in nodes.indices where nodes[index]["kind"] as? String == "BAND" {
            guard let nodeID = nodes[index]["node_id"] as? String,
                  var attributes = nodes[index]["attributes"] as? [String: Any],
                  let parentID = attributes["attached_to"] as? String,
                  let parent = byID[parentID],
                  let parentKind = parent["kind"] as? String,
                  let parentDimensions = parent["dimensions"] as? [String: Any],
                  var dimensions = nodes[index]["dimensions"] as? [String: Any],
                  let previous = (dimensions["length_cm"] as? NSNumber)?.doubleValue,
                  previous.isFinite, previous > 0
            else { continue }

            let semanticWords = words([
                attributes["model_kind"], attributes["detail_role"],
                attributes["shape"], attributes["placement"], nodeID,
            ])
            guard !semanticWords.isDisjoint(with: gatherWords) else { continue }

            let lower = !semanticWords.isDisjoint(with: [
                "cuff", "wrist", "hem", "bottom", "lower",
            ])
            let upper = !semanticWords.isDisjoint(with: [
                "upper", "cap", "armhole", "shoulder", "top", "waist",
            ])
            var target: (length: Double, role: String)?
            var selectionRule = "EXPLICIT_TYPED_BOUNDARY"
            var unselectedRoles: [String] = []

            switch parentKind {
            case "BODY_SHELL":
                target = number(parentDimensions, [
                    "bottom_circumference_cm", "waist_circumference_cm",
                    "circumference_cm",
                ]).map { ($0, "body-boundary") }
            case "SLEEVE":
                if lower != upper {
                    target = lower
                        ? number(parentDimensions, ["cuff_circumference_cm"])
                            .map { ($0, "cuff") }
                        : number(parentDimensions, ["upper_circumference_cm"])
                            .map { ($0, "upper-sleeve") }
                } else if !lower && !upper {
                    // This is candidate geometry, not a hidden fact. The cuff
                    // is candidate A because it is the terminal sleeve edge;
                    // the armhole alternative remains explicitly unresolved.
                    target = number(parentDimensions, ["cuff_circumference_cm"])
                        .map { ($0, "cuff") }
                    selectionRule = "PROPOSED_TERMINAL_EDGE_ALTERNATIVE"
                    unselectedRoles = ["upper-sleeve"]
                }
            case "FLARE", "FRUSTUM":
                if lower != upper {
                    target = lower
                        ? number(parentDimensions, ["bottom_circumference_cm"])
                            .map { ($0, "hem") }
                        : number(parentDimensions, ["top_circumference_cm"])
                            .map { ($0, "waist") }
                } else if !lower && !upper {
                    target = number(parentDimensions, ["bottom_circumference_cm"])
                        .map { ($0, "hem") }
                    selectionRule = "PROPOSED_TERMINAL_EDGE_ALTERNATIVE"
                    unselectedRoles = ["waist"]
                }
            case "TUBE":
                target = number(parentDimensions, ["circumference_cm"])
                    .map { ($0, "tube-loop") }
            case "OVERLAY":
                target = number(parentDimensions, ["width_cm"])
                    .map { ($0, "overlay-edge") }
            case "BAND", "COLLAR":
                target = number(parentDimensions, ["length_cm"])
                    .map { ($0, "long-edge") }
            case "GORE":
                if lower != upper {
                    target = lower
                        ? number(parentDimensions, ["bottom_width_cm"])
                            .map { ($0, "gore-bottom") }
                        : number(parentDimensions, ["top_width_cm"])
                            .map { ($0, "gore-top") }
                }
            default:
                target = nil
            }
            guard let target else { continue }

            var provenance = attributes["dimension_provenance"]
                as? [String: [String: Any]] ?? [:]
            let originalProvenance = provenance["length_cm"] ?? [:]
            if isObserved(originalProvenance) { continue }

            let existingRatio = previous / target.length
            let needsRedraft = previous <= target.length || existingRatio > 8
            var resolved = previous
            if needsRedraft {
                resolved = target.length * 1.75
                guard resolved.isFinite, resolved > target.length,
                      resolved <= 500 else { continue }
                dimensions["length_cm"] = resolved
                provenance["length_cm"] = [
                    "state": "PROPOSED",
                    "authority": "PROPOSED_RELATION_DERIVED",
                    "dimension_source": "PROPOSED_GATHER_CUT_LENGTH_REDRAFT",
                    "basis": "bounded 1.75x preview gather ratio after the front proposal did not provide a longer cut edge",
                    "breaks_when": "a reviewed gather ratio, calibrated finished boundary, pattern edge, material limit, pleat construction, or ungathered treatment is supplied",
                    "source_node_id": parentID,
                    "target_role": target.role,
                    "target_length_cm": target.length,
                    "original_model_or_fallback_value_cm": previous,
                    "original_provenance": originalProvenance,
                    "not_measured_from_image": true,
                    "model_supplied": false,
                    "completed": true,
                ]
            }

            let previousPlacement = attributes["placement"] as? String
            attributes["model_placement"] = previousPlacement ?? ""
            attributes["placement"] = "\(target.role) PROPOSED gather boundary"
            attributes["detail_role"] = "ruffle"
            attributes["gather_target_role"] = target.role
            attributes["gather_boundary_state"] = "PROPOSED"
            attributes["gather_boundary_provenance"] = [
                "state": "PROPOSED",
                "authority": "PROPOSED_RELATION_DERIVED",
                "selection_rule": selectionRule,
                "source_part_id": nodeID,
                "target_part_id": parentID,
                "target_role": target.role,
                "target_length_cm": target.length,
                "unselected_target_roles": unselectedRoles,
                "approval_required": !unselectedRoles.isEmpty,
                "observed": false,
                "approved": false,
                "manufacturing_ready": false,
                "not_observed_from_front": true,
                "basis": selectionRule == "EXPLICIT_TYPED_BOUNDARY"
                    ? "visible placement semantics select one typed parent boundary"
                    : "the model named an exact parent but omitted which terminal edge; one bounded preview alternative is selected and the other remains listed",
                "breaks_when": "placement review, another view, an exact pattern edge, or user selection changes the attachment boundary",
            ]
            attributes["dimension_provenance"] = provenance
            nodes[index]["dimensions"] = dimensions
            nodes[index]["attributes"] = attributes

            records.append([
                "kind": "PROPOSED_GATHERED_BAND_BOUNDARY_NORMALIZATION",
                "state": "PROPOSED_NORMALIZATION",
                "source_part_id": nodeID,
                "target_part_id": parentID,
                "target_role": target.role,
                "target_length_cm": target.length,
                "original_source_length_cm": previous,
                "resolved_source_length_cm": resolved,
                "ratio": resolved / target.length,
                "selection_rule": selectionRule,
                "unselected_target_roles": unselectedRoles,
                "approval_required": !unselectedRoles.isEmpty,
                "dimensions_changed": needsRedraft,
                "not_measured_from_image": true,
                "not_observed_from_front": true,
            ])
            assumptions.append(
                "\(nodeID) is a PROPOSED gathered strip targeting \(parentID).\(target.role); its cut edge is \(resolved)cm for the \(target.length)cm finished boundary. Unselected alternatives \(unselectedRoles) remain unresolved and approval is required when present")
        }
        return (records, assumptions)
    }

    /// A BAND with no calibrated/model-supplied length receives a generic
    /// bounded preview value during parsing. When the child names one parent
    /// and its placement/shape/role selects exactly one typed parent boundary,
    /// replace only that fallback value with the parent boundary length.
    ///
    /// ``WAISTBAND`` is the one structural model alias admitted here even when
    /// the compact vision model supplied a length. A waistband is itself the
    /// seam boundary, unlike a removable BELT/contact: keeping two different
    /// proposed lengths makes the typed JOIN impossible. Redraft only the
    /// candidate preview, retain the model value in provenance, and require
    /// approval. This is topology completion at PROPOSED authority, never an
    /// image measurement or a manufacturing claim.
    private static func reconcileBoundedPreviewBandBoundaries(
        nodes: inout [[String: Any]]
    ) -> (records: [[String: Any]], assumptions: [String]) {
        func words(_ values: [Any?]) -> Set<String> {
            Set(values.compactMap { $0 as? String }
                .joined(separator: " ").lowercased().split {
                    !$0.isLetter && !$0.isNumber
                }.map(String.init))
        }
        func number(_ dimensions: [String: Any], _ names: [String]) -> Double? {
            for name in names {
                guard let value = dimensions[name] as? NSNumber,
                      CFGetTypeID(value) != CFBooleanGetTypeID(),
                      value.doubleValue.isFinite, value.doubleValue > 0 else {
                    continue
                }
                return value.doubleValue
            }
            return nil
        }

        let byID: [String: [String: Any]] = Dictionary(
            uniqueKeysWithValues: nodes.compactMap { node
                -> (String, [String: Any])? in
            guard let id = node["node_id"] as? String else { return nil }
            return (id, node)
        })
        var records: [[String: Any]] = []
        var assumptions: [String] = []
        for index in nodes.indices where nodes[index]["kind"] as? String == "BAND" {
            guard let nodeID = nodes[index]["node_id"] as? String,
                  var attributes = nodes[index]["attributes"] as? [String: Any],
                  let parentID = attributes["attached_to"] as? String,
                  let parent = byID[parentID],
                  let parentKind = parent["kind"] as? String,
                  let parentDimensions = parent["dimensions"] as? [String: Any],
                  var dimensions = nodes[index]["dimensions"] as? [String: Any],
                  var provenance = attributes["dimension_provenance"]
                    as? [String: [String: Any]],
                  let lengthProvenance = provenance["length_cm"]
            else { continue }

            let modelKind = (attributes["model_kind"] as? String)?
                .uppercased()
            let parserFallback =
                lengthProvenance["completed"] as? Bool == true &&
                lengthProvenance["model_supplied"] as? Bool == false &&
                lengthProvenance["dimension_source"] as? String ==
                    "BOUNDED_PREVIEW_MANNEQUIN_DERIVED_PROPOSAL"
            let structuralAliasRedraft = modelKind == "WAISTBAND"
            guard parserFallback || structuralAliasRedraft else { continue }

            // Gathered strips intentionally have a longer cut edge. They are
            // reconciled above and must never be collapsed to the equal-length
            // rule used for belts, cuffs, neckbands and other ordinary BANDs.
            let gatheredWords = words([
                attributes["model_kind"], attributes["detail_role"],
                attributes["shape"], attributes["placement"], nodeID,
            ])
            guard gatheredWords.isDisjoint(with: [
                "ruffle", "ruffled", "frill", "frilled", "flounce",
                "flounced", "gather", "gathered",
            ]) else { continue }

            let address = words([
                attributes["model_kind"], attributes["placement"], attributes["shape"],
                attributes["detail_role"],
            ])
            let waist = !address.isDisjoint(with: ["waist", "belt", "sash"])
            let neck = !address.isDisjoint(with: ["neck", "neckline", "collar"])
            let hem = !address.isDisjoint(with: ["hem", "bottom", "lower"])
            let top = !address.isDisjoint(with: ["top", "upper"])
            let cuff = !address.isDisjoint(with: ["cuff", "wrist"])
            let armhole = !address.isDisjoint(with: ["armhole", "cap"])

            let resolved: (Double, String)?
            switch parentKind {
            case "BODY_SHELL" where waist != neck:
                resolved = waist
                    ? number(parentDimensions, [
                        "bottom_circumference_cm", "waist_circumference_cm",
                        "circumference_cm",
                    ]).map { ($0, "waist") }
                    : number(parentDimensions, ["neck_circumference_cm"])
                        .map { ($0, "neck") }
            case "SLEEVE" where (cuff || hem) != (armhole || top):
                resolved = (cuff || hem)
                    ? number(parentDimensions, ["cuff_circumference_cm"])
                        .map { ($0, "cuff") }
                    : number(parentDimensions, ["upper_circumference_cm"])
                        .map { ($0, "upper-sleeve") }
            case "FLARE" where (waist || top) != hem,
                 "FRUSTUM" where (waist || top) != hem:
                resolved = (waist || top)
                    ? number(parentDimensions, ["top_circumference_cm"])
                        .map { ($0, "waist") }
                    : number(parentDimensions, ["bottom_circumference_cm"])
                        .map { ($0, "hem") }
            case "TUBE":
                resolved = number(parentDimensions, ["circumference_cm"])
                    .map { ($0, "tube-loop") }
            case "OVERLAY":
                resolved = number(parentDimensions, ["width_cm"])
                    .map { ($0, "overlay-edge") }
            case "BAND", "COLLAR":
                resolved = number(parentDimensions, ["length_cm"])
                    .map { ($0, "long-edge") }
            default:
                resolved = nil
            }
            guard let (targetLength, targetRole) = resolved else { continue }
            guard let previous = (dimensions["length_cm"] as? NSNumber)?.doubleValue,
                  previous.isFinite, previous > 0 else { continue }
            dimensions["length_cm"] = targetLength
            var resolvedProvenance: [String: Any] = [
                "state": "PROPOSED",
                "dimension_source": structuralAliasRedraft
                    ? "PROPOSED_STRUCTURAL_BAND_SEAM_REDRAFT"
                    : "PROPOSED_RELATION_DERIVED",
                "basis": structuralAliasRedraft
                    ? "WAISTBAND denotes a structural seam and explicit attached_to selects one typed parent boundary; the model value is retained but cannot be used as a mismatched JOIN"
                    : "explicit attached_to plus one unambiguous typed parent boundary",
                "breaks_when": "attachment, parent boundary, placement, shape, detail_role, or calibrated dimensions change",
                "source_node_id": parentID,
                "target_role": targetRole,
                "not_measured_from_image": true,
                "model_supplied": false,
                "completed": true,
                "approval_required": structuralAliasRedraft,
            ]
            if structuralAliasRedraft {
                resolvedProvenance["source_model_kind"] = modelKind
                resolvedProvenance["original_model_value_cm"] = previous
            }
            provenance["length_cm"] = resolvedProvenance
            attributes["dimension_provenance"] = provenance
            var bandNormalization: [String: Any] = [
                "state": "PROPOSED_NORMALIZATION",
                "parent_node_id": parentID,
                "target_role": targetRole,
                "previous_preview_length_cm": previous,
                "resolved_preview_length_cm": targetLength,
                "observed": false,
                "approved": false,
                "approval_required": structuralAliasRedraft,
            ]
            if let modelKind {
                bandNormalization["source_model_kind"] = modelKind
            }
            attributes["band_boundary_normalization"] = bandNormalization
            nodes[index]["dimensions"] = dimensions
            nodes[index]["attributes"] = attributes
            records.append([
                "kind": structuralAliasRedraft
                    ? "PROPOSED_STRUCTURAL_BAND_SEAM_REDRAFT"
                    : "BOUNDED_BAND_BOUNDARY_NORMALIZATION",
                "state": "PROPOSED_NORMALIZATION",
                "source_part_id": nodeID,
                "target_node_id": parentID,
                "target_role": targetRole,
                "previous_preview_length_cm": previous,
                "resolved_preview_length_cm": targetLength,
                "not_measured_from_image": true,
                "approval_required": structuralAliasRedraft,
                "model_values_changed_in_preview": structuralAliasRedraft,
            ])
            assumptions.append(structuralAliasRedraft
                ? "\(nodeID) WAISTBAND was redrafted from its retained \(previous)cm model proposal to the explicit \(parentID) \(targetRole) boundary \(targetLength)cm for this unapproved preview; it is not an image measurement"
                : "\(nodeID) fallback BAND length was matched to the explicit \(parentID) \(targetRole) preview boundary; the value remains PROPOSED and is not an image measurement")
        }
        return (records, assumptions)
    }

    /// Resolve the explicit front-layer combination that otherwise creates
    /// three waist children. Two alternatives use standalone underlayer
    /// trousers; the stretch alternative retains a jumpsuit hypothesis and
    /// makes the skirt an overskirt. No circumference is silently edited.
    private static func normalizeLayeredWaistCandidate(
        nodes: inout [[String: Any]], variantID: String
    ) -> (records: [[String: Any]], assumptions: [String]) {
        let bodyIndices = nodes.indices.filter {
            nodes[$0]["kind"] as? String == "BODY_SHELL"
        }
        guard bodyIndices.count == 1,
              let bodyID = nodes[bodyIndices[0]]["node_id"] as? String else {
            return ([], [])
        }
        let skirtIndices = nodes.indices.filter { index in
            guard ["FLARE", "FRUSTUM"].contains(nodes[index]["kind"] as? String ?? ""),
                  let attributes = nodes[index]["attributes"] as? [String: Any]
            else { return false }
            return attributes["attached_to"] as? String == bodyID
        }
        let legIndices = nodes.indices.filter { index in
            guard nodes[index]["kind"] as? String == "TUBE",
                  let attributes = nodes[index]["attributes"] as? [String: Any]
            else { return false }
            return attributes["attached_to"] as? String == bodyID
                && explicitVisionSide(nodes[index]) != nil
        }
        guard !skirtIndices.isEmpty, legIndices.count == 2 else { return ([], []) }
        let sides = legIndices.compactMap { explicitVisionSide(nodes[$0]) }
        guard Set(sides) == Set(["left", "right"]) else { return ([], []) }
        let legIDs = legIndices.compactMap { nodes[$0]["node_id"] as? String }
        guard legIDs.count == 2 else { return ([], []) }
        let bodyAttributes = nodes[bodyIndices[0]]["attributes"] as? [String: Any] ?? [:]
        let bodyUnit = bodyAttributes["garment_unit"] as? String ?? "outer-body"
        let standaloneUnderlayer = variantID != "closed-back-stretch"
        let legUnit = standaloneUnderlayer
            ? stableIdentifier("underlayer-\(bodyID)", fallback: "underlayer")
            : bodyUnit
        for index in legIndices {
            var attributes = nodes[index]["attributes"] as? [String: Any] ?? [:]
            let side = explicitVisionSide(nodes[index]) ?? "unresolved"
            attributes["side"] = side
            attributes["shape"] = "trouser_leg"
            attributes["detail_role"] = "trouser_leg"
            attributes["quantity"] = 1
            attributes["garment_unit"] = legUnit
            if standaloneUnderlayer {
                attributes.removeValue(forKey: "attached_to")
                attributes["attachment_state"] = "PROPOSED_STANDALONE_UNDERLAYER"
            } else {
                attributes["attached_to"] = bodyID
                attributes["attachment_state"] = "PROPOSED_JUMPSUIT_ALTERNATIVE"
            }
            nodes[index]["attributes"] = attributes
        }

        var assumptions: [String] = []
        var records: [[String: Any]] = [[
            "kind": "LAYERED_WAIST_NORMALIZATION",
            "state": "PROPOSED_NORMALIZATION",
            "body_id": bodyID, "skirt_ids": skirtIndices.compactMap {
                nodes[$0]["node_id"] as? String
            },
            "leg_ids": legIDs,
            "mode": standaloneUnderlayer
                ? "OUTER_BODY_SKIRT_PLUS_STANDALONE_UNDERLAYER"
                : "JUMPSUIT_PLUS_OVERSKIRT",
            "dimensions_changed": false,
        ]]
        if standaloneUnderlayer {
            assumptions.append(
                "the visible left/right leg TUBEs are treated as a separately wearable underlayer; both body attachments were removed before topology validation")
        } else {
            assumptions.append(
                "the left/right leg TUBEs remain a PROPOSED jumpsuit alternative while the visible skirt is treated as an independent overskirt")
        }

        let bodyDimensions = nodes[bodyIndices[0]]["dimensions"] as? [String: Double] ?? [:]
        let bodyWaist = bodyDimensions["bottom_circumference_cm"]
            ?? bodyDimensions["waist_circumference_cm"]
            ?? bodyDimensions["circumference_cm"]
        for (offset, index) in skirtIndices.enumerated() {
            var attributes = nodes[index]["attributes"] as? [String: Any] ?? [:]
            // The explicit parallel-waist contract is already a complete,
            // bounded topology proposal. Rear variants must preserve all of
            // its direct BODY_SHELL children instead of reverting to the old
            // one-skirt-plus-detached-overskirt fallback.
            if attributes["waist_stack_state"] as? String == "PROPOSED",
               attributes["waist_stack_parent"] as? String == bodyID {
                attributes["attached_to"] = bodyID
                attributes["garment_unit"] = bodyUnit
                nodes[index]["attributes"] = attributes
                continue
            }
            let skirtDimensions = nodes[index]["dimensions"] as? [String: Double] ?? [:]
            let skirtWaist = skirtDimensions["top_circumference_cm"]
            let gatherableFullness = bodyWaist != nil && skirtWaist != nil &&
                skirtWaist! > bodyWaist! + 0.5 &&
                skirtWaist! / bodyWaist! <= 8
            let mustDetach = !standaloneUnderlayer || offset > 0
                || bodyWaist == nil || skirtWaist == nil
                || (abs((bodyWaist ?? 0) - (skirtWaist ?? 0)) > 0.5 &&
                    !gatherableFullness)
            if mustDetach {
                attributes.removeValue(forKey: "attached_to")
                attributes["attachment_state"] = "PROPOSED_SEPARATE_OUTER_SKIRT_REVIEW"
                attributes["garment_unit"] = stableIdentifier(
                    "overskirt-\(nodes[index]["node_id"] as? String ?? "skirt")",
                    fallback: "overskirt")
                assumptions.append(
                    "\(nodes[index]["node_id"] as? String ?? "skirt") remains a separate outer skirt because its proposed waist was not silently resized or because this is the overskirt alternative")
                records.append([
                    "kind": "SKIRT_WAIST_REVIEW", "state": "PROPOSED",
                    "skirt_id": nodes[index]["node_id"] as? String ?? "",
                    "body_waist_cm": bodyWaist as Any,
                    "skirt_waist_cm": skirtWaist as Any,
                    "join_created": false, "dimensions_changed": false,
                ])
            } else {
                attributes["attached_to"] = bodyID
                attributes["garment_unit"] = bodyUnit
            }
            nodes[index]["attributes"] = attributes
        }

        let existingGussets = nodes.indices.filter { index in
            guard nodes[index]["kind"] as? String == "GUSSET",
                  let attributes = nodes[index]["attributes"] as? [String: Any]
            else { return false }
            let role = (attributes["detail_role"] as? String ?? "").lowercased()
            let attached = attributes["attached_to"] as? [String] ?? []
            return role.contains("trouser") || Set(attached) == Set(legIDs)
        }
        var gussetID: String
        if let index = existingGussets.first,
           let existingID = nodes[index]["node_id"] as? String {
            gussetID = existingID
            var attributes = nodes[index]["attributes"] as? [String: Any] ?? [:]
            attributes["side"] = "center"
            attributes["shape"] = "trousers"
            attributes["detail_role"] = "trouser_gusset"
            attributes["quantity"] = 1
            attributes["attached_to"] = legIDs
            attributes["garment_unit"] = legUnit
            attributes["attachment_state"] = "PROPOSED_NORMALIZATION"
            nodes[index]["attributes"] = attributes
        } else {
            gussetID = stableIdentifier(
                "trouser-gusset-\(bodyID)", fallback: "trouser-gusset")
            let circumferences = legIndices.compactMap {
                (nodes[$0]["dimensions"] as? [String: Double])?["circumference_cm"]
            }
            let average = circumferences.isEmpty
                ? 40.0 : circumferences.reduce(0, +) / Double(circumferences.count)
            let length = max(8.0, min(18.0, average * 0.30))
            let width = max(6.0, min(14.0, average * 0.22))
            let provenance: [String: [String: Any]] = [
                "length_cm": [
                    "state": "PROPOSED",
                    "dimension_source": "DETERMINISTIC_TROUSER_TOPOLOGY_COMPLETION",
                    "not_measured_from_image": true,
                    "basis": "bounded 0.30 of proposed mean leg circumference",
                    "breaks_when": "a drafted crotch seam or body measurement is supplied",
                ],
                "width_cm": [
                    "state": "PROPOSED",
                    "dimension_source": "DETERMINISTIC_TROUSER_TOPOLOGY_COMPLETION",
                    "not_measured_from_image": true,
                    "basis": "bounded 0.22 of proposed mean leg circumference",
                    "breaks_when": "a drafted crotch seam or body measurement is supplied",
                ],
            ]
            nodes.append([
                "node_id": gussetID, "kind": "GUSSET",
                "dimensions": ["length_cm": length, "width_cm": width],
                "ports": [], "layer": legIndices.compactMap {
                    nodes[$0]["layer"] as? Int
                }.max() ?? 0,
                "attributes": [
                    "proposal_source": "deterministic layered-waist normalization",
                    "placement": "center crotch underlayer",
                    "garment_unit": legUnit,
                    "attached_to": legIDs,
                    "attachment_state": "PROPOSED_NORMALIZATION",
                    "side": "center", "shape": "trousers",
                    "detail_role": "trouser_gusset", "quantity": 1,
                    "visible_basis": "not visible; explicit PROPOSED geometry required by the typed two-leg topology",
                    "dimension_provenance": provenance,
                    "preview_dimensions_only": true,
                ],
            ])
        }
        records.append([
            "kind": "TROUSER_GUSSET_COMPLETION",
            "state": "PROPOSED_NORMALIZATION",
            "gusset_id": gussetID, "source_leg_ids": legIDs,
            "not_observed_from_front": true,
        ])
        assumptions.append(
            "a center GUSSET is PROPOSED topology-completion geometry, not a front-image observation")
        return (records, assumptions)
    }

    /// Complete a separately wearable two-leg trouser/legging unit with the
    /// one hidden center GUSSET required by the typed topology. The front
    /// image cannot observe this piece, so completion is allowed only for an
    /// exact same-unit left/right pair whose own semantics say trouser leg.
    /// Ambiguous or branched leg sets remain untouched and fail downstream.
    private static func normalizeStandaloneTrouserTopology(
        nodes: inout [[String: Any]]
    ) -> (records: [[String: Any]], assumptions: [String]) {
        func semanticText(_ attributes: [String: Any]) -> String {
            ["shape", "detail_role", "placement"].compactMap {
                attributes[$0] as? String
            }.joined(separator: " ").lowercased()
        }
        func number(_ raw: Any?) -> Double? {
            guard let value = raw as? NSNumber,
                  CFGetTypeID(value) != CFBooleanGetTypeID(),
                  value.doubleValue.isFinite, value.doubleValue > 0 else {
                return nil
            }
            return value.doubleValue
        }

        var groups: [String: [Int]] = [:]
        for index in nodes.indices where nodes[index]["kind"] as? String == "TUBE" {
            guard let attributes = nodes[index]["attributes"] as? [String: Any],
                  let unit = attributes["garment_unit"] as? String,
                  !unit.isEmpty,
                  explicitVisionSide(nodes[index]) != nil else { continue }
            let text = semanticText(attributes)
            guard ["trouser", "pants", "legging"].contains(where: text.contains)
            else { continue }
            groups[unit, default: []].append(index)
        }

        var usedIDs = Set(nodes.compactMap { $0["node_id"] as? String })
        var records: [[String: Any]] = []
        var assumptions: [String] = []
        for unit in groups.keys.sorted() {
            guard let indices = groups[unit], indices.count == 2 else { continue }
            let sides = indices.compactMap { explicitVisionSide(nodes[$0]) }
            guard Set(sides) == Set(["left", "right"]), sides.count == 2 else {
                continue
            }
            let legIDs = indices.compactMap { nodes[$0]["node_id"] as? String }
            guard legIDs.count == 2 else { continue }
            let existing = nodes.contains { node in
                guard node["kind"] as? String == "GUSSET",
                      let attributes = node["attributes"] as? [String: Any]
                else { return false }
                let attached = attributes["attached_to"] as? [String] ?? []
                return Set(attached) == Set(legIDs)
                    || ((attributes["garment_unit"] as? String) == unit
                        && semanticText(attributes).contains("trouser"))
            }
            if existing { continue }

            var gussetID = stableIdentifier(
                "trouser-gusset-\(unit)", fallback: "trouser-gusset")
            var suffix = 2
            while usedIDs.contains(gussetID) {
                gussetID = stableIdentifier(
                    "trouser-gusset-\(unit)-\(suffix)",
                    fallback: "trouser-gusset-\(suffix)")
                suffix += 1
            }
            usedIDs.insert(gussetID)
            let circumferences = indices.compactMap { index in
                let dimensions = nodes[index]["dimensions"] as? [String: Any]
                return number(dimensions?["circumference_cm"])
            }
            let average = circumferences.isEmpty
                ? 40.0 : circumferences.reduce(0, +) / Double(circumferences.count)
            let length = max(8.0, min(18.0, average * 0.30))
            let width = max(6.0, min(14.0, average * 0.22))
            let provenance: [String: [String: Any]] = [
                "length_cm": [
                    "state": "PROPOSED",
                    "dimension_source": "DETERMINISTIC_TROUSER_TOPOLOGY_COMPLETION",
                    "not_measured_from_image": true,
                    "basis": "bounded 0.30 of the proposed same-unit mean leg circumference",
                    "breaks_when": "a drafted crotch seam or wearer measurement is supplied",
                ],
                "width_cm": [
                    "state": "PROPOSED",
                    "dimension_source": "DETERMINISTIC_TROUSER_TOPOLOGY_COMPLETION",
                    "not_measured_from_image": true,
                    "basis": "bounded 0.22 of the proposed same-unit mean leg circumference",
                    "breaks_when": "a drafted crotch seam or wearer measurement is supplied",
                ],
            ]
            nodes.append([
                "node_id": gussetID, "kind": "GUSSET",
                "dimensions": ["length_cm": length, "width_cm": width],
                "ports": [], "layer": indices.compactMap {
                    nodes[$0]["layer"] as? Int
                }.max() ?? 0,
                "attributes": [
                    "proposal_source": "deterministic standalone-trouser topology completion",
                    "placement": "center crotch",
                    "garment_unit": unit,
                    "attached_to": legIDs,
                    "attachment_state": "PROPOSED_NORMALIZATION",
                    "side": "center", "shape": "trousers",
                    "detail_role": "trouser_gusset", "quantity": 1,
                    "visible_basis": "not visible; PROPOSED hidden construction required by the exact typed two-leg topology",
                    "dimension_provenance": provenance,
                    "preview_dimensions_only": true,
                ],
            ])
            records.append([
                "kind": "STANDALONE_TROUSER_GUSSET_COMPLETION",
                "state": "PROPOSED_NORMALIZATION",
                "gusset_id": gussetID,
                "garment_unit": unit,
                "source_leg_ids": legIDs,
                "not_observed_from_front": true,
            ])
            assumptions.append(
                "\(gussetID) is hidden PROPOSED topology-completion geometry for the exact \(unit) left/right leg pair, not a front-image observation")
        }
        return (records, assumptions)
    }

    /// Expand one explicitly *paired* trouser volume proposed by a compact
    /// vision model into the two TUBE nodes required by the typed topology.
    /// This is not a generic "one leg means two" repair: a singular
    /// trouser_leg with no side remains unresolved. Expansion is allowed only
    /// when the model itself supplied a pair/plural marker (quantity=2,
    /// bilateral/both/pair side, or plural trouser/pants/leggings semantics).
    /// The original dimensions are copied, never inferred from pixels, and
    /// every created relation stays PROPOSED_NORMALIZATION.
    private static func normalizeMergedVisionTrouserPairs(
        nodes: inout [[String: Any]]
    ) -> (records: [[String: Any]], assumptions: [String]) {
        let parentUnits: [String: String] = Dictionary(
            uniqueKeysWithValues: nodes.compactMap { node in
                guard let id = node["node_id"] as? String,
                      let attributes = node["attributes"] as? [String: Any],
                      let unit = attributes["garment_unit"] as? String,
                      !unit.isEmpty else { return nil }
                return (id, unit)
            })
        var usedIDs = Set(nodes.compactMap { $0["node_id"] as? String })
        var output: [[String: Any]] = []
        var records: [[String: Any]] = []
        var assumptions: [String] = []
        var expandedTargetsBySource: [String: [String]] = [:]

        func uniqueID(_ proposed: String, fallback: String) -> String {
            var candidate = stableIdentifier(proposed, fallback: fallback)
            var suffix = 2
            while usedIDs.contains(candidate) {
                candidate = stableIdentifier(
                    "\(proposed)-\(suffix)", fallback: "\(fallback)-\(suffix)")
                suffix += 1
            }
            usedIDs.insert(candidate)
            return candidate
        }

        for node in nodes {
            guard node["kind"] as? String == "TUBE",
                  explicitVisionSide(node) == nil,
                  let sourceID = node["node_id"] as? String else {
                output.append(node)
                continue
            }
            let attributes = node["attributes"] as? [String: Any] ?? [:]
            let semanticText = [
                attributes["shape"] as? String,
                attributes["detail_role"] as? String,
                attributes["placement"] as? String,
                sourceID,
            ].compactMap { $0 }.joined(separator: " ").lowercased()
            let rawSide = (attributes["side"] as? String)?
                .trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            let quantity = (attributes["quantity"] as? NSNumber)?.intValue
            let explicitPairMarker = quantity == 2
                || ["bilateral", "both", "pair", "paired"].contains(rawSide ?? "")
                || ["trousers", "pants", "leggings", "leg pair", "both legs",
                    "two legs"].contains(where: semanticText.contains)
            guard explicitPairMarker else {
                output.append(node)
                continue
            }

            let parentID = attributes["attached_to"] as? String
            let unit = (parentID.flatMap { parentUnits[$0] })
                ?? (attributes["garment_unit"] as? String)
                ?? stableIdentifier("lower-\(sourceID)", fallback: "lower")
            var createdIDs: [String] = []
            for side in ["left", "right"] {
                let newID = uniqueID("\(sourceID)-\(side)",
                                     fallback: "trouser-\(side)")
                createdIDs.append(newID)
                var expanded = node
                var expandedAttributes = attributes
                expanded["node_id"] = newID
                expandedAttributes["garment_unit"] = unit
                expandedAttributes["side"] = side
                expandedAttributes["shape"] = "trouser_leg"
                expandedAttributes["detail_role"] = "trouser_leg"
                expandedAttributes["quantity"] = 1
                expandedAttributes["merged_pair_source_node_id"] = sourceID
                expandedAttributes["pair_expansion_state"] =
                    "PROPOSED_NORMALIZATION"
                expandedAttributes["visible_basis"] =
                    "the vision model proposed one explicitly paired/plural lower TUBE; this \(side) leg is deterministic proposal geometry, not a separately observed side"
                expanded["attributes"] = expandedAttributes
                output.append(expanded)
            }
            records.append([
                "kind": "MERGED_TROUSER_PAIR_EXPANSION",
                "state": "PROPOSED_NORMALIZATION",
                "source_node_id": sourceID,
                "created_leg_node_ids": createdIDs,
                "garment_unit": unit,
                "dimensions_changed": false,
                "not_observed_as_separate_sides": true,
            ])
            expandedTargetsBySource[sourceID] = createdIDs
            assumptions.append(
                "\(sourceID) was an explicitly paired/plural trouser proposal and was expanded to \(createdIDs.joined(separator: ", ")); left/right separation remains PROPOSED, not observed")
        }

        // A child may legitimately point at the compact pair node supplied by
        // the model. Once that pair is expanded, leaving the old id behind
        // turns a valid proposal into a misleading TARGET_MISSING refusal.
        // Remap only explicit references. Paired children are duplicated onto
        // the two typed legs; a GUSSET keeps one node and names both legs. A
        // singular child remains multi-parent and therefore reaches the
        // topology layer as an explicit ambiguity instead of being assigned
        // to a side that was never observed.
        var remappedOutput: [[String: Any]] = []
        for node in output {
            var attributes = node["attributes"] as? [String: Any] ?? [:]
            let rawAttached = attributes["attached_to"]
            let attachedIDs: [String]
            if let attached = rawAttached as? String {
                attachedIDs = [attached]
            } else if let attached = rawAttached as? [String] {
                attachedIDs = attached
            } else {
                remappedOutput.append(node)
                continue
            }
            let expandedSources = attachedIDs.filter {
                expandedTargetsBySource[$0] != nil
            }
            guard !expandedSources.isEmpty else {
                remappedOutput.append(node)
                continue
            }

            let nodeID = node["node_id"] as? String ?? "paired-child"
            let kind = node["kind"] as? String ?? ""
            let semanticText = [
                attributes["shape"] as? String,
                attributes["detail_role"] as? String,
                attributes["placement"] as? String,
                nodeID,
            ].compactMap { $0 }.joined(separator: " ").lowercased()
            let rawSide = (attributes["side"] as? String)?
                .trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            let quantity = (attributes["quantity"] as? NSNumber)?.intValue
            let explicitlyPairedChild = quantity == 2
                || ["bilateral", "both", "pair", "paired"].contains(
                    rawSide ?? "")
                || ["both ", "pair", "paired", "bilateral",
                    "left and right"].contains(where: semanticText.contains)

            let remappedAttached = attachedIDs.flatMap { sourceID in
                expandedTargetsBySource[sourceID] ?? [sourceID]
            }.reduce(into: [String]()) { result, targetID in
                if !result.contains(targetID) { result.append(targetID) }
            }
            if kind != "GUSSET", explicitlyPairedChild,
               expandedSources.count == 1,
               let targets = expandedTargetsBySource[expandedSources[0]],
               targets.count == 2 {
                var createdChildIDs: [String] = []
                for (side, targetID) in zip(["left", "right"], targets) {
                    var child = node
                    var childAttributes = attributes
                    let childID = uniqueID(
                        "\(nodeID)-\(side)", fallback: "paired-child-\(side)")
                    createdChildIDs.append(childID)
                    child["node_id"] = childID
                    childAttributes["attached_to"] = targetID
                    childAttributes["side"] = side
                    childAttributes["quantity"] = 1
                    childAttributes["pair_expansion_source_node_id"] = nodeID
                    childAttributes["attachment_state"] =
                        "PROPOSED_NORMALIZATION"
                    childAttributes["visible_basis"] =
                        "the model explicitly proposed a paired child attached to a paired lower volume; this \(side) attachment is deterministic proposal geometry, not a separately observed side"
                    child["attributes"] = childAttributes
                    remappedOutput.append(child)
                }
                records.append([
                    "kind": "MERGED_PAIR_CHILD_ATTACHMENT_EXPANSION",
                    "state": "PROPOSED_NORMALIZATION",
                    "source_node_id": nodeID,
                    "source_target_node_id": expandedSources[0],
                    "created_child_node_ids": createdChildIDs,
                    "created_target_node_ids": targets,
                    "not_observed_as_separate_sides": true,
                ])
                assumptions.append(
                    "\(nodeID) explicitly described a paired child of \(expandedSources[0]) and was expanded onto the left/right proposal legs; side ownership remains PROPOSED")
                continue
            }

            var remapped = node
            attributes["attached_to"] = remappedAttached
            attributes["attachment_state"] = "PROPOSED_NORMALIZATION"
            attributes["pair_target_expansion_source_node_ids"] =
                expandedSources
            remapped["attributes"] = attributes
            remappedOutput.append(remapped)
            records.append([
                "kind": "MERGED_PAIR_ATTACHMENT_REFERENCE_REMAP",
                "state": "PROPOSED_NORMALIZATION",
                "node_id": nodeID,
                "source_target_node_ids": expandedSources,
                "created_target_node_ids": remappedAttached,
                "side_assignment_inferred": false,
            ])
            assumptions.append(
                "\(nodeID).attached_to was remapped from the compact pair id to its explicit proposal legs; no unobserved single-side ownership was invented")
        }
        output = remappedOutput
        nodes = output
        return (records, assumptions)
    }

    /// A single front view can ground visible geometry but cannot distinguish
    /// rear construction. Keep pixel-grounded source ids and visible bases
    /// equivalent while varying PROPOSED rear/closure semantics. The closure
    /// attributes pass through the parts IR, so downstream structure and
    /// artifact digests remain distinct without inventing observed geometry.
    private static func expandSingleVisibleVisionCandidate(
        _ visible: [String: Any]
    ) -> [[String: Any]] {
        guard let baseID = visible["candidate_id"] as? String,
              let structure = visible["structure"] as? [String: Any],
              let sourceNodes = structure["nodes"] as? [[String: Any]],
              !sourceNodes.isEmpty else { return [] }
        let alternatives: [[String: Any]] = [
            [
                "variant_id": "center-back-opening",
                "back_design": "PROPOSED center-back opening",
                "closure_detail": [
                    "state": "PROPOSED", "location": "center_back",
                    "method": "zip_or_fastener_candidate",
                    "not_observed_from_front": true,
                ],
                "opening_topology": [
                    "state": "PROPOSED", "location": "center_back",
                    "construction": "opening",
                    "geometry_cut_created": false,
                ],
                "assumption": "center-back access is one unobserved construction alternative",
            ],
            [
                "variant_id": "side-opening-closed-back",
                "back_design": "PROPOSED closed back with side opening",
                "closure_detail": [
                    "state": "PROPOSED", "location": "side",
                    "method": "side_zip_or_fastener_candidate",
                    "not_observed_from_front": true,
                ],
                "opening_topology": [
                    "state": "PROPOSED", "location": "side",
                    "construction": "opening_with_closed_back",
                    "geometry_cut_created": false,
                ],
                "assumption": "a side opening with a closed back is one unobserved construction alternative",
            ],
            [
                "variant_id": "closed-back-stretch",
                "back_design": "PROPOSED closed-back stretch entry",
                "closure_detail": [
                    "state": "PROPOSED", "location": "none",
                    "method": "pull_on_stretch_candidate",
                    "material_requirement": "UNKNOWN_STRETCH_MATERIAL_REQUIRES_REVIEW",
                    "not_observed_from_front": true,
                ],
                "opening_topology": [
                    "state": "PROPOSED", "location": "none",
                    "construction": "closed_back_stretch_entry",
                    "geometry_cut_created": false,
                ],
                "assumption": "closed-back pull-on construction is possible only if a later material choice supplies sufficient stretch",
            ],
        ]
        let anchorIndex = sourceNodes.firstIndex {
            $0["kind"] as? String == "BODY_SHELL"
        } ?? sourceNodes.startIndex
        return alternatives.compactMap { alternative in
            guard let variantID = alternative["variant_id"] as? String,
                  let back = alternative["back_design"] as? String,
                  let closure = alternative["closure_detail"] as? [String: Any],
                  let opening = alternative["opening_topology"] as? [String: Any],
                  let assumption = alternative["assumption"] as? String else {
                return nil
            }
            var candidate = visible
            let candidateID = stableIdentifier(
                "rear-\(variantID)-\(baseID)", fallback: "rear-\(variantID)")
            candidate["candidate_id"] = candidateID
            candidate["back_design"] = back
            candidate["rear_alternative_id"] = variantID
            candidate["rear_alternative_source"] =
                "DETERMINISTIC_FRONT_ONLY_EXPANSION"
            candidate["visible_structure_source_candidate_id"] = baseID
            candidate["visible_structure_shared_source"] =
                "one pixel-grounded model candidate; visible nodes, dimensions and visible_basis are preserved"
            candidate["rear_difference"] = [
                "state": "PROPOSED",
                "authority": "PROPOSED",
                "closure_detail": closure,
                "opening_topology": opening,
                "not_observed_from_front": true,
            ]
            var assumptions = candidate["assumptions"] as? [String] ?? []
            assumptions.append(assumption)
            assumptions.append(
                "rear and closure differ only as a deterministic PROPOSED alternative; visible structure remains shared")
            var nodes = sourceNodes
            let mergedTrouserPairs = normalizeMergedVisionTrouserPairs(
                nodes: &nodes)
            for index in nodes.indices {
                var attributes = nodes[index]["attributes"] as? [String: Any] ?? [:]
                attributes["back_design"] = back
                if index == anchorIndex {
                    attributes["closure_detail"] = closure
                    attributes["opening_topology"] = opening
                }
                nodes[index]["attributes"] = attributes
            }
            // Rear alternatives are executable candidates in their own right.
            // Re-run the deterministic waist-stack gate before any boundary
            // reconciliation. It is intentionally idempotent after the direct
            // parsed candidate has already separated secondary skirt layers.
            let sharedWaistStack = normalizeVisionSharedWaistStacks(
                nodes: &nodes)
            let waistBoundary = reconcileBoundedPreviewWaistJoinBoundaries(
                nodes: &nodes)
            let layered = normalizeLayeredWaistCandidate(
                nodes: &nodes, variantID: variantID)
            assumptions.append(contentsOf: sharedWaistStack.assumptions)
            assumptions.append(contentsOf: waistBoundary.assumptions)
            assumptions.append(contentsOf: layered.assumptions)
            assumptions.append(contentsOf: mergedTrouserPairs.assumptions)
            let standaloneTrousers = normalizeStandaloneTrouserTopology(
                nodes: &nodes)
            assumptions.append(contentsOf: standaloneTrousers.assumptions)
            candidate["assumptions"] = assumptions
            var records = candidate["normalization_records"]
                as? [[String: Any]] ?? []
            records.append(contentsOf: sharedWaistStack.records)
            records.append(contentsOf: waistBoundary.records)
            records.append(contentsOf: layered.records)
            records.append(contentsOf: mergedTrouserPairs.records)
            records.append(contentsOf: standaloneTrousers.records)
            candidate["normalization_records"] = records
            var variantStructure = structure
            variantStructure["nodes"] = nodes
            candidate["structure"] = variantStructure
            if var operations = candidate["pattern_operation_proposals"]
                as? [[String: Any]] {
                for index in operations.indices {
                    operations[index]["candidate_id"] = candidateID
                }
                candidate["pattern_operation_proposals"] = operations
            }
            candidate["rear_authority"] = "PROPOSED"
            candidate["material_authority"] = "UNKNOWN"
            candidate["requires_human_approval"] = true
            candidate["manufacturing_ready"] = false
            candidate["manufacturing_certified"] = false
            return candidate
        }
    }

    /// Accept free-form candidate JSON from the image model, then reduce only
    /// PLEAT/GATHER/DART/FOLD records to a typed proposal envelope. Model-supplied
    /// authority is never copied. A malformed or unresolved record is retained
    /// as REVIEW so it cannot silently disappear or execute.
    private static func parseVisionPatternOperations(
        _ candidate: [String: Any], candidateID: String, nodeIDs: Set<String>
    ) -> [[String: Any]] {
        let raw = (candidate["pattern_operations"] as? [[String: Any]])
            ?? (candidate["operations"] as? [[String: Any]]) ?? []
        var used = Set<String>()
        return raw.prefix(24).enumerated().map { index, operation in
            let rawID = boundedString(operation["operation_id"], limit: 80)
                ?? boundedString(operation["id"], limit: 80)
                ?? "vision-operation-\(index + 1)"
            var operationID = stableIdentifier(
                rawID, fallback: "vision-operation-\(index + 1)")
            if !used.insert(operationID).inserted {
                operationID += "-\(index + 1)"
                _ = used.insert(operationID)
            }
            let rawKind = boundedString(operation["kind"], limit: 24)
                ?? boundedString(operation["type"], limit: 24) ?? "UNSPECIFIED"
            let kind = rawKind.uppercased()
            let target = operation["target"] as? [String: Any] ?? [:]
            let rawPiece = boundedString(target["piece_id"], limit: 80)
                ?? boundedString(operation["target_piece_id"], limit: 80)
                ?? boundedString(operation["piece_id"], limit: 80)
            let pieceID = rawPiece.map {
                stableIdentifier($0, fallback: "unresolved")
            }
            let semanticEdge = boundedString(target["semantic_edge"], limit: 80)
                ?? boundedString(operation["semantic_edge"], limit: 80)
                ?? boundedString(operation["edge_role"], limit: 80)
            let basis = boundedString(operation["basis"], limit: 400)
                ?? "image model proposed this construction from visible appearance"
            let authorityKeys = ["state", "authority", "verdict", "approval_id",
                                 "approver", "approved", "observed", "selected"]
                .filter { operation[$0] != nil }
            var proposal: [String: Any] = [
                "operation_id": operationID,
                "candidate_id": candidateID,
                "kind": kind,
                "state": "PROPOSED",
                "authority": "PROPOSED",
                "target": [
                    "piece_id": pieceID ?? "",
                    "semantic_edge": semanticEdge ?? "",
                ],
                "basis": basis,
                "provenance": [
                    "source": "pixel-seeing vision LLM",
                    "source_kind": "IMAGE_MODEL_PROPOSAL",
                    "image_derived": true,
                    "observed": false,
                    "approved": false,
                    "model_authority_claims_removed": authorityKeys,
                ],
                "review": ["required": false, "code": "NONE"],
                "execution": [
                    "eligible": false,
                    "status": "PENDING_MCP_TARGET_RESOLUTION",
                    "canonical_pattern_mutated": false,
                ],
            ]
            guard ["PLEAT", "GATHER", "DART", "FOLD"].contains(kind) else {
                return withVisionOperationReview(
                    proposal, code: "UNKNOWN_VISION_OPERATION_KIND",
                    why: "only typed PLEAT, GATHER, DART, and FOLD proposals are supported")
            }
            guard let pieceID, nodeIDs.contains(pieceID), semanticEdge != nil else {
                return withVisionOperationReview(
                    proposal, code: "UNKNOWN_VISION_OPERATION_TARGET_AMBIGUOUS",
                    why: "the proposal must name one existing part and one semantic edge")
            }
            guard let parameters = typedVisionOperationParameters(
                kind: kind, operation: operation) else {
                return withVisionOperationReview(
                    proposal, code: "UNKNOWN_VISION_OPERATION_PARAMETERS",
                    why: "operation parameters are missing, non-finite, or outside the typed preview contract")
            }
            proposal["parameters"] = parameters
            proposal["execution"] = [
                "eligible": true,
                "status": "PENDING_MCP_TARGET_RESOLUTION",
                "canonical_pattern_mutated": false,
            ]
            return proposal
        }
    }

    private static func typedVisionOperationParameters(
        kind: String, operation: [String: Any]
    ) -> [String: Any]? {
        let nested = operation["parameters"] as? [String: Any] ?? [:]
        func value(_ name: String) -> Any? { nested[name] ?? operation[name] }
        func finite(_ name: String, positive: Bool = false) -> Double? {
            guard let number = value(name) as? NSNumber,
                  CFGetTypeID(number) != CFBooleanGetTypeID(),
                  number.doubleValue.isFinite,
                  !positive || number.doubleValue > 0,
                  abs(number.doubleValue) <= 1000 else { return nil }
            return number.doubleValue
        }
        func point(_ name: String) -> [Double]? {
            guard let raw = value(name) as? [Any], raw.count == 2 else { return nil }
            let numbers = raw.compactMap { item -> Double? in
                guard let number = item as? NSNumber,
                      CFGetTypeID(number) != CFBooleanGetTypeID(),
                      number.doubleValue.isFinite,
                      abs(number.doubleValue) <= 1000 else { return nil }
                return number.doubleValue
            }
            return numbers.count == 2 ? numbers : nil
        }
        switch kind {
        case "PLEAT":
            guard let countNumber = value("count") as? NSNumber,
                  CFGetTypeID(countNumber) != CFBooleanGetTypeID(),
                  countNumber.doubleValue == Double(countNumber.intValue),
                  (1...64).contains(countNumber.intValue),
                  let depth = finite("depth_cm", positive: true), depth <= 50 else {
                return nil
            }
            let style = boundedString(value("style"), limit: 32) ?? "knife"
            guard ["knife", "box", "inverted_box"].contains(style) else { return nil }
            var result: [String: Any] = [
                "count": countNumber.intValue, "depth_cm": depth, "style": style,
            ]
            if value("finished_length_cm") != nil {
                guard let finished = finite("finished_length_cm", positive: true) else {
                    return nil
                }
                result["finished_length_cm"] = finished
            }
            return result
        case "GATHER":
            var result: [String: Any] = [:]
            if value("finished_length_cm") != nil {
                guard let finished = finite("finished_length_cm", positive: true),
                      finished <= 500 else { return nil }
                result["finished_length_cm"] = finished
            }
            if value("ratio") != nil {
                guard let ratio = finite("ratio", positive: true),
                      ratio > 1, ratio <= 8 else { return nil }
                result["ratio"] = ratio
            }
            return result.isEmpty ? nil : result
        case "DART":
            guard let t = finite("t"), t > 0, t < 1,
                  let intake = finite("intake_cm", positive: true), intake <= 50 else {
                return nil
            }
            var result: [String: Any] = ["t": t, "intake_cm": intake]
            if let toward = point("toward") {
                result["toward"] = toward
            } else if let depth = finite("depth_cm", positive: true), depth <= 100 {
                result["depth_cm"] = depth
            } else {
                return nil
            }
            result["role"] = boundedString(value("role"), limit: 80) ?? "dart"
            return result
        case "FOLD":
            guard let start = point("start"), let end = point("end"), start != end,
                  let direction = boundedString(value("direction"), limit: 24),
                  ["mountain", "valley", "either"].contains(direction) else {
                return nil
            }
            return ["start": start, "end": end, "direction": direction]
        default:
            return nil
        }
    }

    /// Read one exact edge length from the already-resolved compiled piece.
    /// This completes ratio-only GATHER proposals after address resolution;
    /// it does not edit the piece or the canonical pattern.
    private static func compiledPatternEdgeLength(
        piece: [String: Any], edge: String
    ) -> Double? {
        guard edge.first == "e", let index = Int(edge.dropFirst()),
              let outline = piece["outline"] as? [[Double]], outline.count >= 2,
              outline.indices.contains(index) else { return nil }
        let next = (index + 1) % outline.count
        guard outline[index].count >= 2, outline[next].count >= 2 else { return nil }
        let dx = outline[next][0] - outline[index][0]
        let dy = outline[next][1] - outline[index][1]
        let length = hypot(dx, dy)
        return length.isFinite && length > 0 ? length : nil
    }

    static func resolveVisionOperationTarget(
        _ proposal: [String: Any], pieces: [[String: Any]]
    ) -> (piece: [String: Any], edge: String)? {
        guard let target = proposal["target"] as? [String: Any],
              let pieceID = target["piece_id"] as? String, !pieceID.isEmpty,
              let semantic = target["semantic_edge"] as? String, !semantic.isEmpty else {
            return nil
        }
        let matches = pieces.filter {
            ($0["node_id"] as? String) == pieceID || ($0["piece_id"] as? String) == pieceID
        }
        guard matches.count == 1, let piece = matches.first,
              let edges = piece["edges"] as? [String: Any] else { return nil }
        let normalized = semantic.lowercased()
            .replacingOccurrences(of: "-", with: "_")
            .replacingOccurrences(of: " ", with: "_")
        if normalized.range(of: #"^e[0-9]+$"#, options: .regularExpression) != nil,
           edges[normalized] != nil {
            return (piece, normalized)
        }
        if let groups = piece["boundary_edge_groups"] as? [String: Any] {
            let groupMatches = groups.compactMap { name, value -> String? in
                let key = name.lowercased().replacingOccurrences(of: "-", with: "_")
                guard key == normalized,
                      let rows = value as? [Any], rows.count == 1,
                      let edge = rows.first as? String, edges[edge] != nil else { return nil }
                return edge
            }
            if groupMatches.count == 1 { return (piece, groupMatches[0]) }
        }
        let aliases: [String: String] = [
            "top": "e2", "upper": "e2", "neck": "e2", "neckline": "e2",
            "waist": "e2", "waistline": "e2", "bottom": "e0", "lower": "e0",
            "hem": "e0", "hemline": "e0", "cuff": "e0",
            "right_side": "e1", "side_right": "e1",
            "left_side": "e3", "side_left": "e3",
        ]
        guard let edge = aliases[normalized], edges[edge] != nil else { return nil }
        return (piece, edge)
    }

    private static func withVisionOperationReview(
        _ proposal: [String: Any], code: String, why: String
    ) -> [String: Any] {
        var reviewed = proposal
        reviewed["state"] = "PROPOSED"
        reviewed["authority"] = "PROPOSED"
        reviewed["review"] = ["required": true, "code": code, "why": why]
        reviewed["execution"] = [
            "eligible": false,
            "status": "NOT_EXECUTED_REVIEW",
            "canonical_pattern_mutated": false,
        ]
        return reviewed
    }

    private static func boundedString(_ value: Any?, limit: Int) -> String? {
        guard let value = value as? String else { return nil }
        let clean = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return clean.isEmpty ? nil : String(clean.prefix(limit))
    }

    private static func stableIdentifier(_ raw: String, fallback: String) -> String {
        let mapped = raw.lowercased().map { character -> Character in
            character.isLetter || character.isNumber || character == "-" || character == "_"
                ? character : "-"
        }
        let clean = String(mapped).split(separator: "-", omittingEmptySubsequences: true)
            .joined(separator: "-")
        return clean.isEmpty ? fallback : String(clean.prefix(80))
    }

    static func parseProposal(_ raw: String, task: String) -> [String: Any]? {
        let key = task == "structure_hypotheses" ? "hypotheses" : "candidates"
        for encoded in balancedJSONObjects(in: raw) {
            guard let data = encoded.data(using: .utf8),
                  var object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let rows = object[key] as? [[String: Any]], rows.count >= 2 else {
                continue
            }
            // Authority-shaped top-level fields are not even forwarded for
            // audit; nested authority vocabulary is demoted again by the
            // persisted Python garment_factory gate.
            for name in ["approval_id", "approver", "selected", "by", "verdict", "state"] {
                object.removeValue(forKey: name)
            }
            return object
        }
        return nil
    }

    private static func balancedJSONObjects(in raw: String) -> [String] {
        var result: [String] = []
        var start: String.Index?
        var depth = 0
        var quoted = false
        var escaped = false
        for index in raw.indices {
            let character = raw[index]
            if quoted {
                if escaped { escaped = false }
                else if character == "\\" { escaped = true }
                else if character == "\"" { quoted = false }
                continue
            }
            if character == "\"", depth > 0 { quoted = true }
            else if character == "{" {
                if depth == 0 { start = index }
                depth += 1
            } else if character == "}", depth > 0 {
                depth -= 1
                if depth == 0, let objectStart = start {
                    result.append(String(raw[objectStart...index]))
                    start = nil
                }
            }
        }
        return result
    }

    private static func findDictionary(named key: String, in value: Any) -> [String: Any]? {
        if let dictionary = value as? [String: Any] {
            if let found = dictionary[key] as? [String: Any] { return found }
            for child in dictionary.values {
                if let found = findDictionary(named: key, in: child) { return found }
            }
        } else if let array = value as? [Any] {
            for child in array {
                if let found = findDictionary(named: key, in: child) { return found }
            }
        }
        return nil
    }

    private static func meshEdges(_ faces: [[Int]]) -> [[Int]] {
        var seen = Set<String>()
        var result: [[Int]] = []
        for face in faces where face.count >= 3 {
            for index in face.indices {
                let a = face[index]
                let b = face[(index + 1) % face.count]
                let lo = min(a, b), hi = max(a, b)
                let key = "\(lo):\(hi)"
                if seen.insert(key).inserted { result.append([lo, hi]) }
            }
        }
        return result
    }

    private func publishPatternArtifact(_ pattern: [String: Any],
                                        repairSummary: String) {
        rawPreviewPattern = pattern
        let manufacturing = pattern["manufacturing_preview"] as? [String: Any]
        let candidatePreview = pattern["candidate_preview"] as? [String: Any]
        let mesh = candidatePreview?["mesh"] as? [String: Any]
        let surface = pattern["garment_surface"] as? [String: Any]
        let points = (mesh?["vertices"] as? [[Double]])
            ?? (surface?["verts"] as? [[Double]]) ?? []
        let faces = (mesh?["faces"] as? [[Int]])
            ?? (surface?["faces"] as? [[Int]]) ?? []
        let displayedPieces = (manufacturing?["pieces"] as? [[String: Any]])
            ?? (pattern["pieces"] as? [[String: Any]]) ?? []
        let pieces = displayedPieces.enumerated().map {
            index, row in
            PreviewPiece(id: (row["piece_id"] as? String) ?? "piece-\(index)",
                         name: (row["name"] as? String)
                            ?? (row["piece_id"] as? String) ?? "piece \(index + 1)",
                         outline: (row["cut_line"] as? [[Double]])
                            ?? (row["outline"] as? [[Double]]) ?? [])
        }
        guard !points.isEmpty || !pieces.isEmpty else { return }
        previewArtifact = PreviewArtifact(
            state: pattern["candidate_state"] as? String ?? "PROPOSED",
            attempt: max(1, previewAttempts),
            method: "approved structure graph → candidate 3D → candidate flat pattern",
            points: points, faces: faces, edges: Self.meshEdges(faces), pieces: pieces,
            assumptions: [
                "背面など正面から見えない構造は、人が採用したPROPOSED仮説です。",
                "標準人台寸法は実測身体寸法ではありません。",
                "製造可否は縫い代・素材・強度・着脱・縫製順序の全ゲート後にのみ判定します。",
            ], repairSummary: repairSummary,
            preservesSourceFront:
                (candidatePreview?["binding"] as? [String: Any])?["front_fixed"]
                    as? Bool ?? false)
        materialPreviewBasePattern = pattern
        materialPreviewBaseArtifact = previewArtifact
        candidateMaterialPreview = nil
    }
}

/// Uses the model selected in Atelier settings as the proposal mouth.  It has
/// no MCP handle and therefore cannot act even if prompted to do so.
@MainActor
enum GarmentFactoryModelMouth {
    static func proposer(
        for pick: AtelierAnalyst.Pick,
        responseFormat: [String: Any]? = nil
    ) -> GarmentFactoryReactController.Proposer? {
        if case .vera = pick { return nil }
        let compatibility = GarmentModelCompatibility.profile(
            sourceName: pick.sourceName)
        guard compatibility.languageEnvelope,
              compatibility.qualification != .unsupported else { return nil }
        return { prompt in
            let harnessedPrompt = GarmentModelCompatibility.harnessPrefix(
                sourceName: pick.sourceName,
                operation: .factoryProposal) + "\n\n" + prompt
            switch pick {
            case .vera:
                return nil
            case .ollama(let name):
                return await OllamaClient.shared.generate(
                    model: name, prompt: harnessedPrompt,
                    maxTokens: 2400, temperature: 0.15)
            case .jgen(let name):
                let manager = JCrossChatManager.shared
                if await manager.loadedModelName != name {
                    do { try await manager.load(modelFileName: name) }
                    catch { return nil }
                }
                return try? await manager.generate(
                    conversation: [("user", harnessedPrompt)], maxTokens: 2400,
                    keepThinking: false)
            case .lmStudio(let name):
                return await LMStudioClient.shared.generateCompleteConversation(
                    model: name, messages: [("user", harnessedPrompt)],
                    maxTokens: 4000, temperature: 0.15,
                    responseFormat: responseFormat)
            case .cloud(let provider, let name):
                let result = await CloudAPIClient.shared.send(
                    systemPrompt: "Garment proposal worker. JSON only. No tool use or approval.",
                    userMessage: harnessedPrompt, provider: provider,
                    modelOverride: name)
                if case .success(let text) = result { return text }
                return nil
            }
        }
    }

    /// Gives the selected vision-capable model the actual pixels. Text-only
    /// models fail closed and the geometry path remains available.
    static func visionProposer(
        for pick: AtelierAnalyst.Pick
    ) -> GarmentFactoryReactController.VisionProposer? {
        let compatibility = GarmentModelCompatibility.profile(
            sourceName: pick.sourceName)
        guard compatibility.visionInput,
              compatibility.qualification != .unsupported else { return nil }
        switch pick {
        case .vera, .jgen:
            return nil
        case .ollama, .lmStudio, .cloud:
            break
        }
        return { prompt, imagePath in
            guard let base64 = jpegBase64(at: imagePath) else { return nil }
            let harnessedPrompt = GarmentModelCompatibility.harnessPrefix(
                sourceName: pick.sourceName,
                operation: .visionStructure) + "\n\n" + prompt
            switch pick {
            case .vera, .jgen:
                return nil
            case .ollama(let name):
                return await OllamaClient.shared.generateConversation(
                    model: name, messages: [("user", harnessedPrompt)],
                    imagesForLastUserMessage: [base64], allowImageFallback: false,
                    maxTokens: 4000,
                    temperature: 0.10)
            case .lmStudio(let name):
                return await LMStudioClient.shared.generateWithImage(
                    model: name,
                    systemPrompt: "Garment structure proposal worker. JSON only. No approval or tool use.",
                    userText: harnessedPrompt, imageBase64: base64,
                    mimeType: "image/jpeg", temperature: 0.10, maxTokens: 5000)
            case .cloud(let provider, let name):
                let result = await CloudAPIClient.shared.send(
                    systemPrompt: "Garment structure proposal worker. JSON only. No approval or tool use.",
                    userMessage: harnessedPrompt, imageBase64: base64,
                    provider: provider, modelOverride: name)
                if case .success(let text) = result { return text }
                return nil
            }
        }
    }

    private static func jpegBase64(at path: String) -> String? {
        guard let image = NSImage(contentsOfFile: path),
              let tiff = image.tiffRepresentation,
              let bitmap = NSBitmapImageRep(data: tiff),
              let jpeg = bitmap.representation(
                using: .jpeg, properties: [.compressionFactor: 0.88]) else {
            return nil
        }
        return jpeg.base64EncodedString()
    }
}
