import Foundation

// MARK: - ClaimGrounding
//
// Where did this sentence come from?
//
// Vera already separates facts four ways: claims from non-claims
// (`propose_ai_facts` drops hedges and meta-commentary), trusted from
// quarantined, ANSWER from UNKNOWN_*, and current from superseded. The
// separation it could not make is by ORIGIN — whether a stated claim is
// grounded in something this system actually holds, or recited from the
// model's training data. A real run received fresh web evidence about
// Claude and still wrote "100K tokens": confident, unhedged, and
// supported by nothing the turn carried.
//
// This classifier answers that question the way Vera answers every other
// one: deterministically, with a typed verdict that names its source, and
// with refusal (`.ungrounded`) as a first-class outcome rather than a
// silent pass. No model is asked to grade its own honesty — the check is
// lexical against the sources the turn actually carried, plus Vera's own
// `ask` for the trusted store.
//
// Deliberately source-agnostic: a source is (kind, label, text), so web
// evidence, eternal recall, file contents and tool output all classify
// through one path, and a new source kind costs a case rather than a
// parallel implementation. Callers decide what to do with the verdicts —
// mark a reply, filter what reaches memory, or report a ratio.
//
// It errs toward `.ungrounded`. A grounded claim whose wording shares
// little vocabulary with its source gets marked unverified; the opposite
// error would let a fabrication into the store, which is the failure this
// exists to prevent.
enum ClaimGrounding {

    // MARK: - Types

    struct Source {
        enum Kind: String {
            case veraStore   // deterministic verdict text
            case web         // fetched page / search results
            case eternal     // JGEN hidden-state recall
            case file        // workspace file content
            case tool        // any other tool output
        }
        let kind: Kind
        /// Host, path or tool name — what a citation would point at.
        let label: String
        let text: String
    }

    /// Typed, like Vera's own verdicts: a claim is grounded in a named
    /// place or it is not. There is no "probably".
    enum Verdict: Equatable {
        /// Not a factual assertion: header, question, hedge, meta.
        case notAClaim(reason: String)
        /// Vera's trusted store answers for it (provenance-backed).
        case groundedStore(core: String)
        /// Supported by a source this turn carried.
        case groundedEvidence(label: String)
        /// Neither. Stated, but nothing here backs it.
        case ungrounded

        var isGrounded: Bool {
            switch self {
            case .groundedStore, .groundedEvidence: return true
            case .notAClaim, .ungrounded:           return false
            }
        }
    }

    struct Classified {
        let text: String
        let verdict: Verdict
    }

    /// Share of distinctive tokens a sentence must have in common with a
    /// source before it counts as supported by it.
    private static let lexicalThreshold = 0.6
    /// Below this many distinctive tokens there is nothing to match on,
    /// so lexical grounding abstains and the store gets asked instead.
    private static let minTokensToJudge = 2

    // MARK: - Splitting

    /// Sentence-ish claim candidates. Fenced code is dropped whole (its
    /// contents are not assertions about the world), table rows keep their
    /// cells — a fabricated price hides in a table more readily than in
    /// prose.
    static func claims(in reply: String) -> [String] {
        var text = reply
        if let re = try? NSRegularExpression(pattern: "```[\\s\\S]*?```") {
            text = re.stringByReplacingMatches(
                in: text, range: NSRange(text.startIndex..., in: text), withTemplate: " ")
        }
        var out: [String] = []
        for rawLine in text.components(separatedBy: .newlines) {
            let line = rawLine
                .replacingOccurrences(of: "|", with: " ")
                .replacingOccurrences(of: "*", with: "")
                .trimmingCharacters(in: .whitespaces)
            guard !line.isEmpty else { continue }
            // Table rules and horizontal rules carry no claim.
            if line.allSatisfy({ "-–—=: ".contains($0) }) { continue }
            var buffer = ""
            for ch in line {
                buffer.append(ch)
                if "。！？".contains(ch) || (".!?".contains(ch) && buffer.count > 24) {
                    out.append(buffer.trimmingCharacters(in: .whitespaces))
                    buffer = ""
                }
            }
            let tail = buffer.trimmingCharacters(in: .whitespaces)
            if !tail.isEmpty { out.append(tail) }
        }
        return out.filter { $0.count >= 4 }
    }

    // MARK: - Non-claims
    //
    // Mirrors what `propose_ai_facts` already refuses to quarantine, so a
    // sentence that would never become a fact is not reported as an
    // ungrounded one either.

    private static let hedges = [
        "かもしれ", "おそらく", "可能性が高い", "可能性があり", "と思われ", "でしょう",
        "推測", "might ", "probably", "perhaps", "i think", "may be", "likely ",
    ]
    private static let metaPhrases = [
        "確認します", "検索します", "調べます", "以下の通り", "まとめます",
        "let me ", "i'll check", "searching", "here is", "here's",
    ]

    static func nonClaimReason(_ sentence: String) -> String? {
        let s = sentence.trimmingCharacters(in: .whitespaces)
        let lower = s.lowercased()
        if s.count < 8                                { return "too short" }
        if s.hasPrefix("#") || s.hasPrefix(">")       { return "heading" }
        if s.hasSuffix("?") || s.hasSuffix("？")       { return "question" }
        if s.hasSuffix(":") || s.hasSuffix("：")       { return "label" }
        if hedges.contains(where: { lower.contains($0) })      { return "hedge" }
        if metaPhrases.contains(where: { lower.contains($0) }) { return "meta" }
        return nil
    }

    // MARK: - Tokens

    private static func matches(_ pattern: String, in text: String) -> [String] {
        guard let re = try? NSRegularExpression(pattern: pattern) else { return [] }
        return re.matches(in: text, range: NSRange(text.startIndex..., in: text))
            .compactMap { Range($0.range, in: text).map { r in String(text[r]) } }
    }

    /// Numbers, versions, prices and dates — normalized so "32,000" and
    /// "32000" compare equal, and "100K" and "100k" do.
    static func numericTokens(_ text: String) -> Set<String> {
        let raw = matches(#"[$¥]?\d[\d,\.]*\s?[kKmMbB%]?"#, in: text)
        return Set(raw.map {
            $0.replacingOccurrences(of: ",", with: "")
              .replacingOccurrences(of: " ", with: "")
              .lowercased()
        }.filter { $0.count >= 2 })
    }

    /// Language-invariant anchors: product names, identifiers, acronyms.
    /// These survive translation — a Japanese sentence about English
    /// evidence still says "Claude", "Fable", "Anthropic".
    static func anchorTokens(_ text: String) -> Set<String> {
        Set(matches(#"[A-Za-z][A-Za-z0-9._\-]{2,}"#, in: text).map { $0.lowercased() })
    }

    /// Content words in the reply's own language — used only when a
    /// sentence carries too few anchors to judge by.
    static func lexicalTokens(_ text: String) -> Set<String> {
        var out = Set<String>()
        out.formUnion(matches(#"[ァ-ヴー]{3,}"#, in: text))
        out.formUnion(matches(#"[一-龯]{2,}"#, in: text))
        return out
    }

    // MARK: - Lexical grounding

    /// The source that supports this sentence, if any.
    ///
    /// Two rules, in order of sharpness:
    ///
    /// 1. **Figures must be real.** Every numeric token in the sentence
    ///    must appear in the source. This is the rule that catches "100K
    ///    tokens": the prose around it matched the evidence perfectly
    ///    well, and the number appeared nowhere. Hallucinations
    ///    concentrate in versions, prices, dates and benchmark scores, so
    ///    this is where the strictness belongs.
    ///
    /// 2. **Topic must overlap.** Judged on anchors (latin identifiers,
    ///    product names) when the sentence has enough of them, because a
    ///    Japanese sentence about English evidence shares only those; on
    ///    the reply's own content words otherwise. An early version
    ///    judged CJK tokens against English sources and marked every
    ///    correct sentence unverified.
    ///
    /// This is topical grounding, not entailment: "Claude Code is
    /// dangerous" passes rule 2 against evidence about Claude Code. Rule
    /// 1 is the load-bearing one; rule 2 keeps off-topic invention out.
    static func lexicalSupport(_ sentence: String, sources: [Source]) -> Source? {
        let nums = numericTokens(sentence)
        let anchors = anchorTokens(sentence)
        let words = lexicalTokens(sentence)
        let useAnchors = anchors.count >= minTokensToJudge
        let judged = useAnchors ? anchors : words
        guard judged.count >= minTokensToJudge || !nums.isEmpty else { return nil }

        for source in sources {
            let haystack = source.text.lowercased()
            if !nums.isEmpty {
                guard nums.isSubset(of: numericTokens(source.text)) else { continue }
            }
            guard !judged.isEmpty else { return source }   // figures alone, all present
            let hits = judged.filter { haystack.contains($0) }.count
            if Double(hits) / Double(judged.count) >= lexicalThreshold { return source }
        }
        return nil
    }

    // MARK: - Classification

    /// Classify without touching Vera — pure, synchronous, testable.
    /// Sentences that fail lexical grounding come back `.ungrounded`;
    /// `classify(reply:sources:)` upgrades those the store can answer.
    static func classifyLexically(reply: String, sources: [Source]) -> [Classified] {
        claims(in: reply).map { sentence in
            if let reason = nonClaimReason(sentence) {
                return Classified(text: sentence, verdict: .notAClaim(reason: reason))
            }
            if let source = lexicalSupport(sentence, sources: sources) {
                return Classified(text: sentence,
                                  verdict: .groundedEvidence(label: "\(source.kind.rawValue):\(source.label)"))
            }
            return Classified(text: sentence, verdict: .ungrounded)
        }
    }

    /// Full classification: lexical first, then Vera's `ask` for the
    /// sentences nothing in this turn supported. The store probe is
    /// bounded — it is an MCP round trip per sentence, and a reply with
    /// forty ungrounded lines is already answered by the first few.
    @MainActor
    static func classify(reply: String,
                         sources: [Source],
                         maxStoreProbes: Int = 6) async -> [Classified] {
        var results = classifyLexically(reply: reply, sources: sources)
        var probes = 0
        for (i, item) in results.enumerated() where item.verdict == .ungrounded {
            guard probes < maxStoreProbes else { break }
            probes += 1
            let raw = await MCPEngine.shared.callTool(
                serverName: "vera-memory", toolName: "ask",
                arguments: ["query": String(item.text.prefix(200))])
            guard let d = raw.data(using: .utf8),
                  let obj = try? JSONSerialization.jsonObject(with: d) as? [String: Any],
                  (obj["verdict"] as? String) == "ANSWER" else { continue }
            let core = (obj["core"] as? String) ?? ""
            results[i] = Classified(text: item.text, verdict: .groundedStore(core: core))
        }
        return results
    }

    // MARK: - Using the verdicts

    /// Only the claims something actually backs — what may reach memory.
    static func groundedText(from results: [Classified]) -> String {
        results.filter { $0.verdict.isGrounded }
            .map(\.text)
            .joined(separator: "\n")
    }

    /// The reply with unverified assertions marked in place, so a reader
    /// can see which sentences the system stands behind.
    static func annotated(_ reply: String, results: [Classified]) -> String {
        var out = reply
        for item in results where item.verdict == .ungrounded {
            guard let r = out.range(of: item.text) else { continue }
            out.replaceSubrange(r, with: item.text + "（未検証）")
        }
        return out
    }

    /// One line for the chat: how much of this reply was actually backed.
    static func summary(_ results: [Classified], japanese: Bool) -> String {
        let claims = results.filter { if case .notAClaim = $0.verdict { return false }; return true }
        guard !claims.isEmpty else { return "" }
        let store = claims.filter { if case .groundedStore = $0.verdict { return true }; return false }.count
        let evidence = claims.filter { if case .groundedEvidence = $0.verdict { return true }; return false }.count
        let ungrounded = claims.filter { $0.verdict == .ungrounded }.count
        return japanese
            ? "接地: Vera \(store)件・証拠 \(evidence)件 / 未検証 \(ungrounded)件"
            : "grounded: \(store) store, \(evidence) evidence / \(ungrounded) unverified"
    }

    // MARK: - Reading the turn's own background

    /// Pulls the blocks Vera-a prepends to a task back out as sources, so
    /// the classifier can be run anywhere the instruction is in hand
    /// without threading a separate parameter through every call site.
    static func sources(fromInjectedPrompt prompt: String) -> [Source] {
        var out: [Source] = []
        func block(start: String, end: String, kind: Source.Kind, label: String) {
            guard let s = prompt.range(of: start) else { return }
            let rest = prompt[s.upperBound...]
            let body = rest.range(of: end).map { String(rest[..<$0.lowerBound]) } ?? String(rest)
            let trimmed = body.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmed.isEmpty else { return }
            // The web block names its source line; use the host as the label.
            var resolved = label
            if kind == .web,
               let line = trimmed.components(separatedBy: .newlines)
                    .first(where: { $0.hasPrefix("Source: ") }),
               let host = URL(string: String(line.dropFirst("Source: ".count)))?.host {
                resolved = host
            }
            out.append(Source(kind: kind, label: resolved, text: trimmed))
        }
        block(start: "[WEB EVIDENCE", end: "[END WEB EVIDENCE]", kind: .web, label: "web")
        block(start: "[ETERNAL MEMORY", end: "[/ETERNAL MEMORY]", kind: .eternal, label: "eternal")
        block(start: "[VERIFIED MEMORY", end: "[TASK]", kind: .veraStore, label: "vera")
        return out
    }
}
