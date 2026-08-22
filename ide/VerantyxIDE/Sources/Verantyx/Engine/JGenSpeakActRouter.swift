import Foundation

/// Tiny L2 router: same loaded JGEN decides SPEAK vs ACT in one short generate.
/// Keyword heuristics remain as (1) parse-failure fallback and (2) override when
/// a tiny model mis-labels a clear desktop request as SPEAK.
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

        // Tiny models often collapse L1 to "m" / "pam". Feeding that into the
        // router pollutes the decision — prefer the user utterance then.
        let junkHandoff = isLowSignalHandoff(handoff)
        let handoffClip: String
        let detailClip: String
        let nextClip: String
        if junkHandoff {
            handoffClip = "(council handoff unusable — classify from USER only)"
            detailClip = ""
            nextClip = ""
        } else {
            handoffClip = String((handoff.conclusion.isEmpty ? handoff.asText : handoff.conclusion)
                .prefix(400))
            detailClip = String(handoff.detail.prefix(200))
            nextClip = String(handoff.nextAction.prefix(200))
        }

        let system = """
        You are a router. Reply with exactly one word: ACT or SPEAK.
        ACT = operate the Mac (open Safari/Chrome/app, click, type, on-screen search, UI repro).
        SPEAK = chat/answer only, no desktop control.
        Output ONLY: ACT
        or ONLY: SPEAK
        """
        let user = """
        [USER]
        \(String(question.prefix(500)))

        [COUNCIL]
        \(handoffClip)
        [DETAIL] \(detailClip)
        [NEXT] \(nextClip)

        Answer with ACT or SPEAK:
        """

        do {
            let raw = try await chat.generate(
                conversation: [
                    ("system", system),
                    ("user", user),
                ],
                maxTokens: 8,
                keepThinking: false   // one-word routing verdict only
            )
            return parse(raw)
        } catch {
            return nil
        }
    }

    /// True when council text is too degenerate to trust for routing.
    static func isLowSignalHandoff(_ handoff: CouncilOrchestrator.Handoff) -> Bool {
        let c = handoff.conclusion.trimmingCharacters(in: .whitespacesAndNewlines)
        if c.count <= 2 { return true }
        let letters = c.filter { $0.isLetter || ($0.unicodeScalars.first.map { (0x3040...0x30FF).contains($0.value) } ?? false) }
        if letters.count <= 2 { return true }
        // Repeated single-token junk: "m m m", "akan"
        let uniq = Set(c.lowercased().split{ $0.isWhitespace || $0.isPunctuation }.map(String.init).filter { !$0.isEmpty })
        if uniq.count <= 2, (uniq.first?.count ?? 0) <= 4 { return true }
        return false
    }

    /// Parse model text into a route. Accepts leading junk / ChatML bleed.
    static func parse(_ raw: String) -> Route? {
        let collapsed = JCrossChatManager.collapsePhraseRepetition(raw)
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .uppercased()
        // Prefer the first clear label anywhere in a short reply.
        if let actRange = collapsed.range(of: #"\bACT\b"#, options: .regularExpression),
           let speakRange = collapsed.range(of: #"\bSPEAK\b"#, options: .regularExpression) {
            return actRange.lowerBound < speakRange.lowerBound ? .act : .speak
        }
        if collapsed.range(of: #"\bACT\b"#, options: .regularExpression) != nil { return .act }
        if collapsed.range(of: #"\bSPEAK\b"#, options: .regularExpression) != nil { return .speak }
        // Loose contains as last resort (models sometimes emit "ACTION")
        if collapsed.hasPrefix("ACT") || collapsed.contains(" ACT") { return .act }
        if collapsed.hasPrefix("SPEAK") || collapsed.contains(" SPEAK") { return .speak }
        return nil
    }
}
