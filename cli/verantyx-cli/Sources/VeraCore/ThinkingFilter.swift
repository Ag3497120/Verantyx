import Foundation

/// Separates a reasoning model's private thinking from its actual answer.
///
/// Qwen3 (and Qwen3.5/3.6, the published target) emit `<think>…</think>`
/// before the reply. Treating that stream as the answer produces exactly the
/// symptoms observed on qwen3-4b: a "reply" of `<think>`, council conclusions
/// of `:` or `is`, and fragments like `매우!!!!!!` — mid-thought tokens shown
/// as a final answer.
///
/// The distinction that matters is between *finished* and *unfinished*:
///
///  - closed block → the answer is whatever follows `</think>`
///  - open block   → the model is still reasoning and the budget ran out.
///    There is no answer yet. Reporting the truncated thinking as a reply
///    would be inventing one, so this case is surfaced as its own outcome and
///    the caller retries with more room.
public enum ThinkingFilter {

    public struct Result: Sendable, Equatable {
        /// Text to treat as the model's reply. Empty when still thinking.
        public let answer: String
        /// The reasoning, if any — kept for traces, never used as the answer.
        public let thinking: String
        /// True when a `<think>` block was opened and never closed.
        public let truncatedThinking: Bool

        public var hasAnswer: Bool { !answer.isEmpty }
    }

    static let openTags = ["<think>", "<thinking>", "<reasoning>"]
    static let closeTags = ["</think>", "</thinking>", "</reasoning>"]

    /// True when `text` looks like it came from a reasoning model, whether or
    /// not the block is closed.
    public static func containsThinking(_ text: String) -> Bool {
        let lower = text.lowercased()
        return openTags.contains { lower.contains($0) }
    }

    public static func split(_ raw: String) -> Result {
        let text = raw
        let lower = text.lowercased()

        // A closed block: everything after the last close tag is the answer.
        // "Last" rather than "first" because a model occasionally reopens
        // thinking, and only the final segment is addressed to the user.
        var closeEnd: String.Index? = nil
        for tag in closeTags {
            var searchFrom = lower.startIndex
            while let r = lower.range(of: tag, range: searchFrom..<lower.endIndex) {
                closeEnd = r.upperBound
                searchFrom = r.upperBound
            }
        }

        if let closeEnd {
            let answer = String(text[closeEnd...]).trimmingCharacters(in: .whitespacesAndNewlines)
            var thinking = String(text[text.startIndex..<closeEnd])
            for tag in openTags + closeTags {
                thinking = thinking.replacingOccurrences(
                    of: tag, with: "", options: .caseInsensitive
                )
            }
            return Result(
                answer: answer,
                thinking: thinking.trimmingCharacters(in: .whitespacesAndNewlines),
                // A closed block with nothing after it is still an unfinished
                // turn: the model stopped at the boundary without answering.
                truncatedThinking: answer.isEmpty
            )
        }

        // An open block with no close: still reasoning, no answer exists.
        for tag in openTags {
            if let r = lower.range(of: tag) {
                let thinking = String(text[r.upperBound...])
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                return Result(answer: "", thinking: thinking, truncatedThinking: true)
            }
        }

        return Result(
            answer: text.trimmingCharacters(in: .whitespacesAndNewlines),
            thinking: "",
            truncatedThinking: false
        )
    }

    /// Token budget for a model that reasons before answering.
    ///
    /// A budget sized for a direct reply is spent entirely inside the thinking
    /// block, so the turn can never reach an answer — which is what happened
    /// at 96 tokens on qwen3-4b. Raised once on detection rather than always,
    /// so non-reasoning models keep the cheaper budget.
    public static func expandedBudget(_ base: Int) -> Int {
        max(base * 6, 512)
    }
}
