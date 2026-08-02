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
    static let searchSeedChars = 280

    /// Max characters typed into a browser search field.
    static let maxSearchQueryChars = 100

    /// Bound for `encodeText` / eternal-memory embed (CPU forward on long
    /// token sequences is the Vera-a / GPU-idle OOM hotspot).
    static let maxEncodeChars = 1_200

    /// DeepL translator landing page — prefer URL navigation over dumping an
    /// essay into Safari Smart Search.
    static let deepLTranslatorURL = "https://www.deepl.com/translator"

    // MARK: - Truncation

    /// Collapse duplicated paragraphs (common in long pasted essays) before
    /// budgeting, so repeated blocks do not inflate head/tail windows.
    static func dedupeRepeatedParagraphs(_ text: String) -> String {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return trimmed }

        let paragraphs = trimmed
            .components(separatedBy: "\n\n")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }

        guard paragraphs.count > 1 else {
            return dedupeConsecutiveLines(trimmed)
        }

        var seen = Set<String>()
        var kept: [String] = []
        for p in paragraphs {
            let key = p.lowercased()
            if seen.contains(key) { continue }
            seen.insert(key)
            kept.append(p)
        }
        return dedupeConsecutiveLines(kept.joined(separator: "\n\n"))
    }

    private static func dedupeConsecutiveLines(_ text: String) -> String {
        var last: String?
        var out: [String] = []
        for line in text.components(separatedBy: "\n") {
            let t = line.trimmingCharacters(in: .whitespaces)
            if let last, !t.isEmpty, t == last { continue }
            out.append(line)
            if !t.isEmpty { last = t }
        }
        return out.joined(separator: "\n")
    }

    /// Truncate `text` for model prompts. Returns the original string when
    /// already within budget. Mid-string ellipsis marks omitted content.
    static func truncateForModel(
        _ text: String,
        maxChars: Int = maxQuestionChars,
        headChars: Int = headChars,
        tailChars: Int = tailChars
    ) -> String {
        let trimmed = dedupeRepeatedParagraphs(text)
            .trimmingCharacters(in: .whitespacesAndNewlines)
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

    /// Bound used by `encodeText` / memory embed — never forward a multi-k
    /// essay through a CPU JGEN pass when the GPU is idle.
    static func truncateForEncode(_ text: String) -> String {
        truncateForModel(text, maxChars: maxEncodeChars, headChars: 800, tailChars: 300)
    }

    // MARK: - Search / navigate intent

    /// Markers that identify a short imperative / task line inside a paste.
    private static let taskMarkers: [String] = [
        "safari", "chrome", "firefox", "ブラウザ", "browser",
        "検索", "search", "調べ", "google", "ニュース", "news",
        "翻訳", "translate", "deepl", "下記を", "英訳", "和訳",
        "開いて", "開け", "起動", "url", "http",
    ]

    /// True when the user wants translation (DeepL / 翻訳 / 下記を…英語に).
    static func isTranslateIntent(_ text: String) -> Bool {
        let t = text.lowercased()
        if t.contains("deepl") { return true }
        if t.contains("翻訳") || t.contains("translate") || t.contains("英訳") || t.contains("和訳") {
            return true
        }
        // 「下記を英語に」 without the word 翻訳
        if t.contains("下記を") || t.contains("以下を") {
            if t.contains("英語") || t.contains("日本語") || t.contains("中国語")
                || t.contains("english") || t.contains("japanese") {
                return true
            }
        }
        return false
    }

    /// Pull a short imperative line from head *and* tail of a long paste.
    /// Essays often come first with 「Safariを開いてdeeplで…」 at the end
    /// (or vice versa) — prefix-only seeds then dump the essay body into
    /// Safari Smart Search.
    static func extractTaskIntentLine(from text: String) -> String? {
        let cleaned = dedupeRepeatedParagraphs(text)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleaned.isEmpty else { return nil }

        let lines = cleaned
            .components(separatedBy: .newlines)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }

        func score(_ line: String) -> Int {
            guard line.count <= 200 else { return -1 }
            let lower = line.lowercased()
            var s = 0
            for m in taskMarkers where lower.contains(m) { s += 2 }
            if isTranslateIntent(line) { s += 3 }
            if line.count <= 80 { s += 1 }
            return s
        }

        // Prefer short marker-bearing lines anywhere; bias toward early + late.
        var best: (score: Int, line: String)?
        for (idx, line) in lines.enumerated() {
            var s = score(line)
            if s < 0 { continue }
            if idx < 3 || idx >= lines.count - 3 { s += 1 }
            if best == nil || s > best!.score {
                best = (s, line)
            }
        }
        if let best, best.score > 0 {
            return String(best.line.prefix(searchSeedChars))
        }

        // Fallback: scan a head+tail char window for a sentence with markers.
        let head = String(cleaned.prefix(400))
        let tail = cleaned.count > 400 ? String(cleaned.suffix(400)) : ""
        for window in [tail, head] where !window.isEmpty {
            let lower = window.lowercased()
            if taskMarkers.contains(where: { lower.contains($0) }) {
                // Take up to first newline or 160 chars of that window.
                let firstLine = window
                    .split(whereSeparator: \.isNewline)
                    .map(String.init)
                    .first { score($0) > 0 }
                if let firstLine { return String(firstLine.prefix(searchSeedChars)) }
                return String(window.prefix(min(160, searchSeedChars)))
            }
        }
        return nil
    }

    /// Seed for desktop search-query / navigate derivation.
    /// Prefers an imperative task line over a raw prefix of the essay body.
    static func searchSeed(from text: String, maxChars: Int = searchSeedChars) -> String {
        if let intent = extractTaskIntentLine(from: text) {
            return String(intent.prefix(maxChars))
        }
        let trimmed = dedupeRepeatedParagraphs(text)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.count > maxChars else { return trimmed }
        // Last resort: head only (still capped) — never the full paste.
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
        dedupeRepeatedParagraphs(text)
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .count > maxChars
    }
}
