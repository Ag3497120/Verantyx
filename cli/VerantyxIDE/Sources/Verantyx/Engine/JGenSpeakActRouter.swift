import Foundation

/// Tiny L2 router: same loaded JGEN decides SPEAK vs ACT in one short generate.
/// Keyword heuristics remain only as fallback when the model output is unparsable.
enum JGenSpeakActRouter {

    enum Route: String, Sendable {
        case speak
        case act
    }

    /// Classifies whether Layer 2 should talk (`speak`) or drive desktop tools (`act`).
    /// - Returns `nil` when JGEN is unloaded or the reply cannot be parsed.
    static func classify(
        question: String,
        handoff: CouncilOrchestrator.Handoff
    ) async -> Route? {
        let chat = JCrossChatManager.shared
        guard await chat.isLoaded else { return nil }

        if JCrossChatManager.isSimpleGreeting(question) {
            return .speak
        }

        let handoffClip = String((handoff.conclusion.isEmpty ? handoff.asText : handoff.conclusion)
            .prefix(400))
        let detailClip = String(handoff.detail.prefix(200))
        let nextClip = String(handoff.nextAction.prefix(200))

        let system = """
        You are a router. Reply with exactly one token: ACT or SPEAK.
        ACT = the user wants the Mac operated (open app, browser, click, type, search on screen, UI bug repro).
        SPEAK = answer in chat only (explain, chat, opinions, no desktop control).
        No punctuation, no other words.
        """
        let user = """
        [USER]
        \(String(question.prefix(500)))

        [COUNCIL]
        \(handoffClip)
        [DETAIL] \(detailClip)
        [NEXT] \(nextClip)
        """

        do {
            let raw = try await chat.generate(
                conversation: [
                    ("system", system),
                    ("user", user),
                ],
                maxTokens: 8
            )
            return parse(raw)
        } catch {
            return nil
        }
    }

    /// Parse model text into a route. Accepts leading junk / ChatML bleed.
    static func parse(_ raw: String) -> Route? {
        let collapsed = JCrossChatManager.collapsePhraseRepetition(raw)
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .uppercased()
        // Prefer the first clear label anywhere in a short reply.
        if let actRange = collapsed.range(of: "ACT"),
           let speakRange = collapsed.range(of: "SPEAK") {
            return actRange.lowerBound < speakRange.lowerBound ? .act : .speak
        }
        if collapsed.contains("ACT") { return .act }
        if collapsed.contains("SPEAK") { return .speak }
        // Japanese aliases some small models emit
        let lower = collapsed.lowercased()
        if lower.contains("操作") || lower.contains("実行") { return .act }
        if lower.contains("発話") || lower.contains("回答") { return .speak }
        return nil
    }
}
