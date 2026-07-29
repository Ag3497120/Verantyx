import Foundation

/// Layer 2 of the 4-layer architecture: the execution agent ("subagent").
///
/// The council (Layer 1) deliberates in vector space and produces one short
/// structured handoff. This layer takes that handoff and *acts* on it --
/// running tools, reading and writing files, browsing, iterating -- on a
/// model that can be entirely different from the JGEN model doing the
/// deliberation.
///
/// It deliberately does **not** implement a new ReAct loop. `AgentLoop`
/// already has one, with tool dispatch, permission gates, history
/// compression and UI-trace recording, and its `run(...)` takes
/// `modelStatus`/`activeModel` as parameters — so pointing a second instance
/// at a different backend is all that is required. The one thing that must
/// not happen is reusing `AgentLoop.shared`: it is an `actor`, so a nested
/// call would serialize behind the chat loop that started it.
actor ExecutionAgent {

    static let shared = ExecutionAgent()

    /// A dedicated loop instance, distinct from `AgentLoop.shared`.
    private let loop = AgentLoop()

    private init() {}

    struct Spec: Sendable {
        var modelStatus: AppState.ModelStatus
        var activeModel: String
        var workspaceURL: URL?
        var operationMode: OperationMode = .automatic
        var memoryLayer: JCrossLayer = .l2
        var chatSessionId: String?
    }

    enum Outcome: Sendable {
        case completed(String)
        case failed(String)

        var text: String {
            switch self {
            case .completed(let s): return s
            case .failed(let s):    return s
            }
        }
        var isFailure: Bool {
            if case .failed = self { return true }
            return false
        }
    }

    /// Runs the handoff to completion. `onProgress` receives the same
    /// `LoopEvent` stream the main chat loop uses, so the caller can render
    /// tool calls and streamed tokens with a Layer-2 label.
    func run(
        handoff: CouncilOrchestrator.Handoff,
        question: String,
        spec: Spec,
        cortex: CortexEngine?,
        onProgress: @escaping @Sendable (LoopEvent) async -> Void
    ) async -> Outcome {

        let instruction = """
        You are the execution layer. A council of models has already deliberated on the
        request below and handed you its conclusion — do not re-debate it. Carry it out:
        use your tools to gather what you still need, make the changes, and verify them.
        If the handoff is wrong or unworkable, say so plainly instead of forcing it.

        \(handoff.asText)

        [ORIGINAL REQUEST] \(question)
        """

        // The loop reports terminally via .done or .error; capture whichever
        // arrives, forwarding every event to the caller either way.
        let box = OutcomeBox()

        await loop.run(
            instruction: instruction,
            workspaceURL: spec.workspaceURL,
            modelStatus: spec.modelStatus,
            activeModel: spec.activeModel,
            cortex: cortex,
            operationMode: spec.operationMode,
            memoryLayer: spec.memoryLayer,
            chatSessionId: spec.chatSessionId,
            onProgress: { event in
                switch event {
                case .done(let message, _): await box.set(.completed(message))
                case .error(let message):   await box.set(.failed(message))
                default: break
                }
                await onProgress(event)
            }
        )

        return await box.value
            ?? .failed("Execution agent ended without producing a result.")
    }
}

/// Small actor box so the `@Sendable` progress closure can hand a terminal
/// outcome back out of the loop.
private actor OutcomeBox {
    private(set) var value: ExecutionAgent.Outcome?
    func set(_ outcome: ExecutionAgent.Outcome) {
        // Keep the first terminal event; a later one would be noise.
        if value == nil { value = outcome }
    }
}
