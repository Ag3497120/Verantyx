import Foundation

// MARK: - EternalVeraBridge
//
// Thin API sync between two **separate** memory stores — never merge binary
// formats:
//
//   Eternal (JGEN cosine):  ~/.verantyx_chrono_swift/
//                           cortex.vectors (fp16) + cortex.nodes.jsonl
//
//   Vera CrossStore:        Application Support via vera-memory MCP
//                           (deterministic typed cores / facets)
//
// Only short typed facts cross the bridge: goal_short, skill:name,
// MISSION outcome one-liners, gap subjects. Huge payloads stay put.
// Best-effort — Act / forge never fail if MCP or JGEN is down.

enum EternalVeraBridge {

    /// Human-readable path notes (settings / Growth Console / docs).
    static let storePaths: [String: String] = [
        "eternal": "~/.verantyx_chrono_swift/ (JGEN fp16 + JSONL)",
        "vera": "Vera CrossStore via vera-memory MCP (Application Support)",
        "sync": "API text-fact sync only — no binary merge",
    ]

    enum FactKind: String, Sendable {
        case directive
        case exploreForge = "explore_forge"
        case exploreFail = "explore_fail"
        case actDone = "act_done"
        case gap
    }

    /// Share a short fact into Vera's CrossStore.
    /// - Parameter always: when false, only sync if the active session layer is Vera-α.
    static func shareToVera(
        _ sentence: String,
        kind: FactKind,
        always: Bool = false
    ) {
        let clipped = String(sentence
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .prefix(280))
        guard !clipped.isEmpty else { return }

        Task { @MainActor in
            let isVera = AppState.shared?.sessions.activeSession?.activeLayer == .vera
            guard always || isVera else { return }
            let tagged = "[\(kind.rawValue)] \(clipped)"
            VeraMemoryBridge.rememberShortFact(String(tagged.prefix(500)))
        }
    }

    /// Vera `ask`/`recall` path used by the IDE: optionally splice a short
    /// Eternal `recallBlock` when JGEN is loaded. Keeps eternal lines clipped.
    static func recallMerged(for query: String) async -> String {
        let vera = await VeraMemoryBridge.recall(for: query)
        guard await JCrossChatManager.shared.isLoaded else { return vera }
        let eternal = await EternalMemoryStore.shared.recallBlock(
            for: PromptBudget.truncateForEncode(query),
            k: 2
        )
        let clipped = clipEternalBlock(eternal, maxChars: 480)
        if vera.isEmpty { return clipped }
        if clipped.isEmpty { return vera }
        return vera + "\n" + clipped
    }

    /// Wake / CapabilityRegistry path — Vera wake first, then a one-line
    /// eternal nudge when JGEN is up (never dumps vectors).
    static func wakeMerged(sinceSeconds: Double = 43200) async -> String {
        let wake = await VeraMemoryBridge.wakeSummary(sinceSeconds: sinceSeconds)
        guard await JCrossChatManager.shared.isLoaded else { return wake }
        let eternal = await EternalMemoryStore.shared.recallBlock(
            for: "DIRECTIVE act explore_forge",
            k: 1
        )
        let clipped = clipEternalBlock(eternal, maxChars: 200)
        if clipped.isEmpty { return wake }
        if wake.isEmpty { return clipped }
        return wake + "\n" + clipped
    }

    /// Clip an eternal recall block down to short fact lines.
    nonisolated static func clipEternalBlock(_ block: String, maxChars: Int) -> String {
        let trimmed = block.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return "" }
        if trimmed.count <= maxChars { return trimmed }
        return String(trimmed.prefix(maxChars)) + "…"
    }
}
