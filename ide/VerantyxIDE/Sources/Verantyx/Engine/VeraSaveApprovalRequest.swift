import Foundation

// MARK: - VeraSaveApprovalMode

/// Settings > Vera-α: how the save-preview popup behaves.
enum VeraSaveApprovalMode: String, CaseIterable, Identifiable {
    /// Original behavior: the agent loop suspends every turn until this
    /// turn's save is approved or rejected.
    case perTurn = "per_turn"
    /// Requests queue in AppState.pendingVeraSaveQueue instead of
    /// blocking; the agent keeps working, the human reviews in bulk later.
    case batched = "batched"

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .perTurn: return "Ask every turn"
        case .batched: return "Queue and review later"
        }
    }

    var description: String {
        switch self {
        case .perTurn:
            return "The agent pauses after every turn until you approve or discard that turn's save."
        case .batched:
            return "The agent keeps working without pausing; saves queue up for you to review whenever you check back."
        }
    }
}

// MARK: - VeraSaveApprovalRequest
// Vera-α layer gate — suspends AgentLoop via CheckedContinuation until the
// user taps "保存" or "破棄" in the save-preview sheet. Same pattern as
// FileApprovalRequest (see that file); this one gates a Vera memory write
// instead of a file write.
//
// Usage (AgentLoop / VeraMemoryBridge):
//   let req = VeraSaveApprovalRequest(userPrompt: p, aiResponse: r)
//   await MainActor.run { AppState.shared?.pendingVeraSave = req }
//   let approved = await req.waitForDecision()   // suspends here
//   if approved { /* remember(p) + propose_ai_facts(r) */ }

final class VeraSaveApprovalRequest: Identifiable, @unchecked Sendable {

    let id = UUID()
    let userPrompt: String
    let aiResponse: String

    private var continuation: CheckedContinuation<Bool, Never>?

    init(userPrompt: String, aiResponse: String) {
        self.userPrompt = userPrompt
        self.aiResponse = aiResponse
    }

    /// User tapped "保存".
    func approve() {
        continuation?.resume(returning: true)
        continuation = nil
    }

    /// User tapped "破棄".
    func reject() {
        continuation?.resume(returning: false)
        continuation = nil
    }

    /// Suspends AgentLoop until the user makes a decision.
    func waitForDecision() async -> Bool {
        await withCheckedContinuation { cont in
            self.continuation = cont
        }
    }
}
