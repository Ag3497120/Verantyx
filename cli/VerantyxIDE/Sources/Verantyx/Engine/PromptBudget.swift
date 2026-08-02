import Foundation

/// Caps user text before it is copied into ChatML / role prompts / encode /
/// memory paths. A multi-thousand-character paste (e.g. a Japanese essay)
/// multiplied across council roles and rounds will OOM the device during
/// tokenize + hidden-state encode — long before any meaningful reply.
///
/// Strategy: keep a short head window (task / search intent) and a short tail
/// window (closing ask), drop the middle, and never re-embed the full paste
/// into every role prompt.
enum PromptBudget {

    /// Soft cap for text embedded into council / L2 / escalation prompts.
    static let maxQuestionChars = 1_600

    /// Head window: instructions and desktop/search intent usually live here.
    static let headChars = 1_000

    /// Tail window: closing question / "please do X" often lands at the end.
    static let tailChars = 400

    /// Bound used when deriving a Safari / desktop search query from a paste.
    static let searchSeedChars = 240

    /// Max characters typed into a browser search field.
    static let maxSearchQueryChars = 120

    /// Truncate `text` for model prompts. Returns the original string when
    /// already within budget. Mid-string ellipsis marks omitted content.
    static func truncateForModel(
        _ text: String,
        maxChars: Int = maxQuestionChars,
        headChars: Int = headChars,
        tailChars: Int = tailChars
    ) -> String {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.count > maxChars else { return trimmed }

        let headBudget = min(headChars, max(0, maxChars - 40))
        let tailBudget = min(tailChars, max(0, maxChars - headBudget - 40))
        let head = String(trimmed.prefix(headBudget))
        let tail = tailBudget > 0 ? String(trimmed.suffix(tailBudget)) : ""
        let omitted = trimmed.count - head.count - (tailBudget > 0 ? tail.count : 0)
        if tail.isEmpty {
            return head + "\n\n[… truncated \(omitted) chars …]"
        }
        return head
            + "\n\n[… truncated \(omitted) chars …]\n\n"
            + tail
    }

    /// First-window seed for desktop search-query derivation — taken from the
    /// original paste *before* middle truncation so a leading
    /// 「Safariで…検索」 survives even when the body is huge.
    static func searchSeed(from text: String, maxChars: Int = searchSeedChars) -> String {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.count > maxChars else { return trimmed }
        return String(trimmed.prefix(maxChars))
    }

    /// Cap a derived search query so Safari never receives a multi-k paste.
    static func capSearchQuery(_ query: String, maxChars: Int = maxSearchQueryChars) -> String {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.count > maxChars else { return trimmed }
        return String(trimmed.prefix(maxChars))
    }

    /// True when truncation would drop characters.
    static func needsTruncate(_ text: String, maxChars: Int = maxQuestionChars) -> Bool {
        text.trimmingCharacters(in: .whitespacesAndNewlines).count > maxChars
    }
}
