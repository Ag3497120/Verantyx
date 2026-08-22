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

    /// Hard cap on tokenized length for encode / encodeSoft / council role
    /// forwards — long ChatML + memoryPrefix still OOMs after char truncate.
    static let maxEncodeTokens = 768

    /// Bound for council/agent memory prefixes spliced into every role prompt.
    static let maxMemoryPrefixChars = 2_400

    /// System-turn budget inside ChatML (gatekeeper / handoff blobs).
    static let maxSystemChars = 2_400

    /// DeepL translator landing page — prefer URL navigation over dumping an
    /// essay into Safari Smart Search.
    static let deepLTranslatorURL = "https://www.deepl.com/translator"

    /// Cap for mission payload held outside ChatML (clipboard paste limb).
    /// Large enough for essays; never embedded into prompts as full body.
    static let maxPayloadChars = 50_000

    /// Cap for text persisted into EternalMemory / UI-trace nodes (not ChatML).
    static let maxStoredMemoryChars = 4_000

    // MARK: - Mission payload (held object)

    /// Strip task-intent / translate-instruction lines and return the remaining
    /// body to hold as a mission payload (paste later via `[PASTE_PAYLOAD]`).
    /// Returns `nil` when nothing substantive remains after stripping intent.
    static func extractMissionPayload(from text: String) -> String? {
        let cleaned = dedupeRepeatedParagraphs(text)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleaned.isEmpty else { return nil }

        let lines = cleaned
            .components(separatedBy: .newlines)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }

        let intentLine = extractTaskIntentLine(from: cleaned)?
            .trimmingCharacters(in: .whitespacesAndNewlines)

        func isIntentLine(_ line: String) -> Bool {
            guard !line.isEmpty else { return true }
            if let intentLine, line == intentLine { return true }
            if line.count <= 200 {
                let lower = line.lowercased()
                if taskMarkers.contains(where: { lower.contains($0) }) { return true }
                if isTranslateIntent(line) { return true }
            }
            return false
        }

        let bodyLines = lines.filter { !isIntentLine($0) }
        var body = bodyLines.joined(separator: "\n")
            .trimmingCharacters(in: .whitespacesAndNewlines)

        // Fallback: if intent was only a prefix/suffix of a single blob,
        // strip the known intent line substring once.
        if body.isEmpty, let intentLine, !intentLine.isEmpty,
           let range = cleaned.range(of: intentLine) {
            body = cleaned
            body.removeSubrange(range)
            body = body.trimmingCharacters(in: .whitespacesAndNewlines)
        }

        // Drop leading essay markers that often precede the body.
        for marker in ["下記を", "以下を", "次を", "下記の", "以下の", "the following:"] {
            if body.lowercased().hasPrefix(marker.lowercased()) {
                body = String(body.dropFirst(marker.count))
                    .trimmingCharacters(in: .whitespacesAndNewlines)
            }
        }

        guard body.count >= 20 else { return nil }
        if body.count > maxPayloadChars {
            return String(body.prefix(maxPayloadChars))
        }
        return body
    }

    /// Short preview for observation / PAYLOAD stamps (never the full body).
    static func payloadPreview(_ payload: String, maxChars: Int = 120) -> String {
        let trimmed = payload
            .replacingOccurrences(of: "\n", with: " ")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.count > maxChars else { return trimmed }
        return String(trimmed.prefix(maxChars)) + "…"
    }

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

    /// Bound conversation turns before ChatML / streaming generate — mirrors
    /// `JCrossChatManager.generate` so streaming callers cannot bypass caps.
    static func boundConversation(
        _ conversation: [(role: String, content: String)]
    ) -> [(role: String, content: String)] {
        conversation.map { role, content in
            let cap = role.lowercased() == "system" ? maxSystemChars : maxQuestionChars
            return (role, truncateForModel(content, maxChars: cap))
        }
    }

    /// Keep head+tail of a long tokenized prompt so encode does not hold a
    /// multi-k KV/hidden residency window (council role prompts).
    static func capEncodeTokens(_ tokens: [UInt32], max: Int = maxEncodeTokens) -> [UInt32] {
        guard tokens.count > max, max > 32 else {
            return tokens.count > max ? Array(tokens.prefix(max)) : tokens
        }
        let head = (max * 3) / 4
        let tail = max - head
        return Array(tokens.prefix(head)) + Array(tokens.suffix(tail))
    }

    // MARK: - Search / navigate intent

    /// Markers that identify a short imperative / task line inside a paste.
    private static let taskMarkers: [String] = [
        "safari", "chrome", "firefox", "ブラウザ", "browser",
        "検索", "search", "調べ", "google", "ニュース", "news",
        "翻訳", "translate", "deepl", "下記を", "英訳", "和訳",
        "開いて", "開け", "起動", "url", "http",
    ]

    /// Markers that mean the text is a multi-step UI procedure, not a search query.
    /// Host must NOT dump these into Safari Smart Search.
    private static let proceduralMarkers: [String] = [
        "を入力", "入力して", "入力し",
        "選択する", "を選択", "選択して",
        "を送る", "送信する", "送信して", "を送信",
        "そして", "その後", "次に",
        "then click", "then type", "then press", "and then",
        "click on", "type into",
    ]

    /// Residue that must never appear inside a typed Smart Search string.
    private static let searchRejectMarkers: [String] = [
        "→", "->", "⇒", "➜",
        "開く", "開いて", "開け", "起動",
        "入力", "選択", "送る", "送信",
        "そして", "その後",
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

    /// True when `text` is a multi-step / procedural mission (arrows, UI verbs,
    /// numbered steps, open+type clauses) rather than a short search query.
    /// Bootstrap must open + snapshot only — never dump the procedure into the address bar.
    static func isProceduralMission(_ text: String) -> Bool {
        let cleaned = dedupeRepeatedParagraphs(text)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleaned.isEmpty else { return false }

        // Arrow-separated steps: 「A→B→C」 / "A -> B"
        if cleaned.contains("→") || cleaned.contains("⇒") || cleaned.contains("➜")
            || cleaned.contains("->") {
            return true
        }

        let lower = cleaned.lowercased()

        // Explicit step verbs / connectors.
        if proceduralMarkers.contains(where: { lower.contains($0.lowercased()) || cleaned.contains($0) }) {
            return true
        }

        // Numbered multi-step lists: "1. … 2. …" / "1) … 2)"
        if let re = try? NSRegularExpression(
            pattern: #"(?:^|\n)\s*(?:1[\.\)、]|①)"#,
            options: []
        ) {
            let ns = cleaned as NSString
            if re.firstMatch(in: cleaned, options: [], range: NSRange(location: 0, length: ns.length)) != nil {
                if cleaned.range(of: #"(?:^|\n)\s*(?:2[\.\)、]|②)"#, options: .regularExpression) != nil {
                    return true
                }
            }
        }

        // Compound open + type/select clauses in one mission.
        let hasOpen = cleaned.contains("開いて") || cleaned.contains("開く") || cleaned.contains("開け")
            || cleaned.contains("起動") || lower.contains("open ")
        let hasUIType = cleaned.contains("入力") || cleaned.contains("タイプ")
            || lower.contains("type ") || lower.contains("enter ")
        let hasSelect = cleaned.contains("選択") || lower.contains("select ") || lower.contains("click ")
        if hasOpen && (hasUIType || hasSelect) {
            return true
        }

        return false
    }

    /// Short, clean token safe to type into a browser search field — or `nil`
    /// when the mission is procedural / instructional and must not be dumped.
    static func safeSearchQuery(from text: String, maxChars: Int = maxSearchQueryChars) -> String? {
        let cleaned = dedupeRepeatedParagraphs(text)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleaned.isEmpty else { return nil }
        if isProceduralMission(cleaned) { return nil }
        if isTranslateIntent(cleaned) { return nil }

        // Prefer explicit 「〜を検索」 / "search for …"
        if let explicit = extractExplicitSearchTerm(from: cleaned) {
            return sanitizeSearchToken(explicit, maxChars: maxChars)
        }

        // Single quoted term 「…」 / "…" / '…'
        if let quoted = extractSingleQuotedTerm(from: cleaned) {
            return sanitizeSearchToken(quoted, maxChars: maxChars)
        }

        // Derive from a short intent line, then reject anything instruction-shaped.
        let intent = extractTaskIntentLine(from: cleaned) ?? cleaned
        var t = stripSearchBoilerplate(intent)
        for marker in ["下記を", "以下を", "次を", "the following", "下記の", "以下の"] {
            if let range = t.range(of: marker, options: .caseInsensitive) {
                t = String(t[..<range.lowerBound])
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                break
            }
        }
        if t.isEmpty || t == "ニュース" || t.lowercased() == "news" {
            if cleaned.contains("ニュース") || cleaned.contains("今日") {
                t = "今日のニュース"
            } else if cleaned.lowercased().contains("news") {
                t = "today's news"
            }
        }
        if t == "ニュースを" || (t.hasSuffix("ニュース") && t.count <= 8) {
            t = "今日のニュース"
        }
        return sanitizeSearchToken(t, maxChars: maxChars)
    }

    /// Pull the term from 「Xを検索」 / "search for X" / "X を調べて".
    private static func extractExplicitSearchTerm(from text: String) -> String? {
        let patterns = [
            #"(?:Safari|safari|Chrome|chrome|Firefox|ブラウザ)?(?:で|を開いて|を開く)?\s*([^\n→]{1,60}?)を検索"#,
            #"([^\n→]{1,60}?)を調べ"#,
            #"(?i)search\s+(?:for\s+)?([^\n.!?→]{1,60})"#,
            #"(?i)look\s+up\s+([^\n.!?→]{1,60})"#,
            #"(?i)google\s+([^\n.!?→]{1,60})"#,
        ]
        for pattern in patterns {
            guard let re = try? NSRegularExpression(pattern: pattern, options: []) else { continue }
            let ns = text as NSString
            guard let m = re.firstMatch(in: text, options: [], range: NSRange(location: 0, length: ns.length)),
                  m.numberOfRanges >= 2 else { continue }
            let raw = ns.substring(with: m.range(at: 1))
                .trimmingCharacters(in: .whitespacesAndNewlines)
            if !raw.isEmpty { return raw }
        }
        return nil
    }

    /// First single quoted / bracketed term when the whole paste is short.
    private static func extractSingleQuotedTerm(from text: String) -> String? {
        // Only treat quotes as the search token when the surrounding text is short
        // (avoids pulling essay quotes).
        guard text.count <= 160 else { return nil }
        let patterns = [
            #"「([^」]{1,80})」"#,
            #"『([^』]{1,80})』"#,
            #""([^"]{1,80})""#,
            #"'([^']{1,80})'"#,
        ]
        for pattern in patterns {
            guard let re = try? NSRegularExpression(pattern: pattern, options: []) else { continue }
            let ns = text as NSString
            guard let m = re.firstMatch(in: text, options: [], range: NSRange(location: 0, length: ns.length)),
                  m.numberOfRanges >= 2 else { continue }
            let raw = ns.substring(with: m.range(at: 1))
                .trimmingCharacters(in: .whitespacesAndNewlines)
            if !raw.isEmpty { return raw }
        }
        return nil
    }

    /// Strip browser/open/search boilerplate prefixes/suffixes from an intent line.
    private static func stripSearchBoilerplate(_ intent: String) -> String {
        var t = intent.trimmingCharacters(in: .whitespacesAndNewlines)
        let prefixStrips: [String] = [
            "Safariを開いて", "safariを開いて", "Safariで", "safariで",
            "ブラウザを開いて", "ブラウザで",
            "open safari and ", "open safari ", "please ",
            "search for ", "search ",
        ]
        for s in prefixStrips {
            if t.lowercased().hasPrefix(s.lowercased()) {
                t = String(t.dropFirst(s.count))
                    .trimmingCharacters(in: .whitespacesAndNewlines)
            }
        }
        let suffixStrips = [
            "してください", "してくれ", "検索して", "を検索", "検索",
            "調べて", "して", "を開いて", "開いて",
        ]
        for s in suffixStrips {
            if t.hasSuffix(s) {
                t = String(t.dropLast(s.count))
                    .trimmingCharacters(in: .whitespacesAndNewlines)
            }
        }
        while t.hasPrefix("を") || t.hasPrefix("で") || t.hasPrefix("の") {
            t = String(t.dropFirst()).trimmingCharacters(in: .whitespacesAndNewlines)
        }
        return t
    }

    /// Return a capped token, or `nil` when it still looks like instructions.
    private static func sanitizeSearchToken(_ raw: String, maxChars: Int) -> String? {
        var t = raw
            .replacingOccurrences(of: "\n", with: " ")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        t = t.trimmingCharacters(in: CharacterSet(charactersIn: "「」『』\"'"))
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard !t.isEmpty else { return nil }
        if isProceduralMission(t) { return nil }
        if searchRejectMarkers.contains(where: { t.contains($0) }) { return nil }
        let lower = t.lowercased()
        if lower.contains("safari") || lower.contains("chrome") || lower.contains("firefox") {
            return nil
        }
        // Long multi-clause sentences are instructions, not queries.
        if t.count > 60, t.contains("。") || t.contains("、") || t.contains(",") {
            return nil
        }
        if t.count > maxChars {
            t = String(t.prefix(maxChars))
                .trimmingCharacters(in: .whitespacesAndNewlines)
        }
        guard !t.isEmpty else { return nil }
        if searchRejectMarkers.contains(where: { t.contains($0) }) { return nil }
        return t
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
    /// Returns empty for procedural multi-step missions so callers skip Smart Search typing.
    static func searchSeed(from text: String, maxChars: Int = searchSeedChars) -> String {
        if isProceduralMission(text) { return "" }
        if let intent = extractTaskIntentLine(from: text) {
            if isProceduralMission(intent) { return "" }
            return String(intent.prefix(maxChars))
        }
        let trimmed = dedupeRepeatedParagraphs(text)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.count > maxChars else { return trimmed }
        // Last resort: head only (still capped) — never the full paste.
        return String(trimmed.prefix(maxChars))
    }

    /// Cap a derived search query so Safari never receives a multi-k paste
    /// or a multi-step procedure dump. Returns empty when unsafe.
    static func capSearchQuery(_ query: String, maxChars: Int = maxSearchQueryChars) -> String {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return "" }
        if isProceduralMission(trimmed) { return "" }
        if searchRejectMarkers.contains(where: { trimmed.contains($0) }) { return "" }
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
