import Foundation

// MARK: - HierarchicalExploreGate
//
// Policy gate for **hierarchical exploration with user choice**.
// When ON (default), Act / AgentLoop must not auto-navigate the first
// destination guess after a sense that yields a list of navigable candidates
// (search results, link lists, destination rows). Instead: show a numbered
// list in chat, pause, wait for the user's pick, then resume with
// `DIRECTIVE selected: …` — same branch-point spirit as human approval.
//
// General heuristics only (AX roles / titles / markdown links). No site-
// specific DOM hardcoding.

enum HierarchicalExploreGate {

    /// UserDefaults key (`council_hierarchical_explore`). Default **true**.
    nonisolated static let settingsKey = "council_hierarchical_explore"

    /// Minimum distinct destination-like items before we ask the user.
    nonisolated static let minCandidates = 2
    /// Prefer asking when we have at least this many (stronger list signal).
    nonisolated static let preferredCandidates = 3

    nonisolated static var isEnabled: Bool {
        (UserDefaults.standard.object(forKey: settingsKey) as? Bool) ?? true
    }

    // MARK: - Candidate

    struct Candidate: Sendable, Equatable, Identifiable {
        let id: Int
        /// Human-readable label shown in the choice list.
        let title: String
        /// AX short id when known (`#link3`, `#btn2`, …).
        let axId: String?
        /// Absolute URL when known (web search / markdown).
        let url: String?
        /// Coarse role hint: link / button / cell / result / app.
        let role: String
        /// Where this came from (ax_map / search / observation).
        let source: String

        var displayLine: String {
            var parts = ["\(id). \(title)"]
            if let axId, !axId.isEmpty { parts.append("[\(axId)]") }
            if let url, !url.isEmpty {
                let short = url.count > 60 ? String(url.prefix(57)) + "…" : url
                parts.append("(\(short))")
            }
            return parts.joined(separator: " ")
        }
    }

    struct PendingState: Sendable {
        var candidates: [Candidate]
        var goal: String
        var observationSnippet: String
        var pausedAt: Date
    }

    // MARK: - Extraction

    /// Parse navigable candidates from an observation / AX map / search dump.
    nonisolated static func extractCandidates(from text: String, limit: Int = 12) -> [Candidate] {
        var found: [Candidate] = []
        var seenTitles = Set<String>()
        var seenURLs = Set<String>()

        func push(title raw: String, axId: String?, url: String?, role: String, source: String) {
            let title = normalizeTitle(raw)
            guard isUsableTitle(title) else { return }
            // The result page's own "Source: https://…search?q=…" line was
            // being offered as candidate 1, and picking it re-opened the
            // search instead of a result. A search URL is never a
            // destination.
            if let url, isSearchEngineURL(url) { return }
            if title.lowercased().hasPrefix("source") && (url?.isEmpty == false) { return }
            // Real listings repeat the same destination under different
            // titles ("Official site" and the full site name both pointing
            // at zenn.dev). One destination, one candidate.
            if let url {
                let key = normalizeURLKey(url)
                guard !seenURLs.contains(key) else { return }
                seenURLs.insert(key)
            }
            let key = title.lowercased()
            guard !seenTitles.contains(key) else { return }
            seenTitles.insert(key)
            found.append(Candidate(
                id: found.count + 1,
                title: title,
                axId: axId,
                url: url,
                role: role,
                source: source
            ))
        }

        // 1) AX semantic map: <link id="#link1" title="…"/> / button / cell / …
        if let re = try? NSRegularExpression(
            pattern: #"<([a-z0-9_]+)\s+[^>]*id=\"(#[a-z0-9]+)\"[^>]*(?:title|value)=\"([^\"]+)\""#,
            options: [.caseInsensitive]
        ) {
            let ns = text as NSString
            re.enumerateMatches(in: text, options: [], range: NSRange(location: 0, length: ns.length)) { match, _, stop in
                guard let match, match.numberOfRanges >= 4 else { return }
                let role = ns.substring(with: match.range(at: 1)).lowercased()
                let axId = ns.substring(with: match.range(at: 2))
                let title = ns.substring(with: match.range(at: 3))
                guard isDestinationRole(role) || axId.hasPrefix("#link") else { return }
                push(title: title, axId: axId, url: nil, role: role, source: "ax_map")
                if found.count >= limit { stop.pointee = true }
            }
        }

        // Alternate attribute order: title before id
        if found.count < limit, let re = try? NSRegularExpression(
            pattern: #"<([a-z0-9_]+)\s+[^>]*(?:title|value)=\"([^\"]+)\"[^>]*id=\"(#[a-z0-9]+)\""#,
            options: [.caseInsensitive]
        ) {
            let ns = text as NSString
            re.enumerateMatches(in: text, options: [], range: NSRange(location: 0, length: ns.length)) { match, _, stop in
                guard let match, match.numberOfRanges >= 4 else { return }
                let role = ns.substring(with: match.range(at: 1)).lowercased()
                let title = ns.substring(with: match.range(at: 2))
                let axId = ns.substring(with: match.range(at: 3))
                guard isDestinationRole(role) || axId.hasPrefix("#link") else { return }
                push(title: title, axId: axId, url: nil, role: role, source: "ax_map")
                if found.count >= limit { stop.pointee = true }
            }
        }

        // 2) Markdown links: [title](url)
        if found.count < min(limit, preferredCandidates + 4),
           let re = try? NSRegularExpression(
            pattern: #"\[([^\]]{2,120})\]\((https?://[^)\s]+)\)"#,
            options: []
           ) {
            let ns = text as NSString
            re.enumerateMatches(in: text, options: [], range: NSRange(location: 0, length: ns.length)) { match, _, stop in
                guard let match, match.numberOfRanges >= 3 else { return }
                let title = ns.substring(with: match.range(at: 1))
                let url = ns.substring(with: match.range(at: 2))
                guard !isChromeLinkTitle(title) else { return }
                push(title: title, axId: nil, url: url, role: "result", source: "search")
                if found.count >= limit { stop.pointee = true }
            }
        }

        // 3) Numbered / bulleted result rows: "1. Title — https://…" / "- Title (https://…)"
        if found.count < preferredCandidates,
           let re = try? NSRegularExpression(
            pattern: #"(?m)^(?:\d+[\.\)]\s+|[-*•]\s+)(.{4,100}?)(?:\s+[—\-–]\s+|\s+\(|\s+)(https?://\S+)"#,
            options: []
           ) {
            let ns = text as NSString
            re.enumerateMatches(in: text, options: [], range: NSRange(location: 0, length: ns.length)) { match, _, stop in
                guard let match, match.numberOfRanges >= 3 else { return }
                let title = ns.substring(with: match.range(at: 1))
                var url = ns.substring(with: match.range(at: 2))
                url = url.trimmingCharacters(in: CharacterSet(charactersIn: ")。、,)]"))
                push(title: title, axId: nil, url: url, role: "result", source: "search")
                if found.count >= limit { stop.pointee = true }
            }
        }

        // 4) Bare https lines with a nearby title on the same line
        if found.count < minCandidates,
           let re = try? NSRegularExpression(
            pattern: #"(?m)^(.{4,80}?)\s+(https?://[^\s]+)$"#,
            options: []
           ) {
            let ns = text as NSString
            re.enumerateMatches(in: text, options: [], range: NSRange(location: 0, length: ns.length)) { match, _, stop in
                guard let match, match.numberOfRanges >= 3 else { return }
                let title = ns.substring(with: match.range(at: 1))
                let url = ns.substring(with: match.range(at: 2))
                guard !title.lowercased().hasPrefix("http") else { return }
                push(title: title, axId: nil, url: url, role: "result", source: "observation")
                if found.count >= limit { stop.pointee = true }
            }
        }

        // Re-number after dedupe order.
        return found.enumerated().map { idx, c in
            Candidate(id: idx + 1, title: c.title, axId: c.axId, url: c.url, role: c.role, source: c.source)
        }
    }

    /// Search-result pages are how candidates are FOUND; they are never
    /// one of the candidates.
    nonisolated static func isSearchEngineURL(_ url: String) -> Bool {
        let u = url.lowercased()
        if u.contains("duckduckgo.com") { return true }
        for engine in ["google.", "bing.com", "search.yahoo", "ecosia.org", "startpage.com"]
        where u.contains(engine) && (u.contains("/search") || u.contains("?q=") || u.contains("&q=")) {
            return true
        }
        return false
    }

    /// Scheme, "www." and a trailing slash are not differences in
    /// destination.
    nonisolated static func normalizeURLKey(_ url: String) -> String {
        var u = url.lowercased()
        for prefix in ["https://", "http://"] where u.hasPrefix(prefix) {
            u = String(u.dropFirst(prefix.count))
        }
        if u.hasPrefix("www.") { u = String(u.dropFirst(4)) }
        while u.hasSuffix("/") { u.removeLast() }
        return u
    }

    /// True when observation looks like a **list of destinations** worth asking about.
    nonisolated static func shouldAskUser(_ candidates: [Candidate]) -> Bool {
        guard isEnabled else { return false }
        let links = candidates.filter { $0.role == "link" || $0.role == "result" || $0.axId?.hasPrefix("#link") == true }
        if links.count >= preferredCandidates { return true }
        if links.count >= minCandidates { return true }
        // Fallback: several titled actionable destinations (not chrome buttons).
        let dest = candidates.filter { isDestinationRole($0.role) }
        return dest.count >= preferredCandidates
    }

    /// Observation text that typically yields destination lists.
    nonisolated static func observationLooksLikeListSurface(_ text: String) -> Bool {
        let u = text.uppercased()
        if u.contains("SEARCH RESULTS") || u.contains("[END SEARCH RESULTS]") { return true }
        if u.contains("SEMANTIC UI MAP") || u.contains("UI MAP") || u.contains("<DESKTOP_APP") { return true }
        if u.contains("VISION_SEARCH_FLOW") { return true }
        if text.contains("#link") || text.localizedCaseInsensitiveContains("<link ") { return true }
        if text.contains("search_bar") || text.contains("bootstrap") { return false }
        return false
    }

    // MARK: - Prompt / match

    nonisolated static func formatChoicePrompt(_ candidates: [Candidate], japanese: Bool = true) -> String {
        let lines = candidates.prefix(12).map(\.displayLine).joined(separator: "\n")
        if japanese {
            return """
            🧭 [階層探索] 候補が見つかりました。どれを開きますか？番号または名前で指示してください。
            （「おまかせ」「1番」でも可。オフにする場合は設定の階層探索を無効化。）

            \(lines)
            """
        }
        return """
        🧭 [Hierarchical explore] Candidates found. Which should I open? Reply with a number or name.
        (\"おまかせ\" / \"1\" also works. Turn off Hierarchical explore in settings for legacy auto-click.)

        \(lines)
        """
    }

    /// Autopilot phrases → first candidate (or goal-fuzzy best).
    nonisolated static func isAutopilotChoice(_ message: String) -> Bool {
        let t = message.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let keys = ["おまかせ", "お任せ", "任せる", "どれでも", "適当", "auto", "autopilot", "you choose", "your choice", "適当に"]
        return keys.contains { t == $0 || t.hasPrefix($0) }
    }

    /// Match user reply to a candidate (1-based number, ordinal JP, fuzzy title).
    /// ０-９ → 0-9. A Japanese keyboard produces full-width digits by
    /// default, `Int("１")` is nil, and every numeric branch below fell
    /// through — "１番" re-showed the same list instead of selecting.
    /// Only digits are folded: full-width katakana must survive for the
    /// title matching further down.
    nonisolated static func halfwidthDigits(_ s: String) -> String {
        String(s.map { ch -> Character in
            guard let scalar = ch.unicodeScalars.first,
                  ch.unicodeScalars.count == 1,
                  scalar.value >= 0xFF10, scalar.value <= 0xFF19,
                  let ascii = UnicodeScalar(scalar.value - 0xFF10 + 48) else { return ch }
            return Character(ascii)
        })
    }

    nonisolated static func matchChoice(_ message: String, in candidates: [Candidate], goalHint: String? = nil) -> Candidate? {
        guard !candidates.isEmpty else { return nil }
        let t = halfwidthDigits(message.trimmingCharacters(in: .whitespacesAndNewlines))
        guard !t.isEmpty else { return nil }

        if isAutopilotChoice(t) {
            return bestForGoal(candidates, goal: goalHint ?? "")
        }

        // Pure number / 「1番」「第2」
        let lower = t.lowercased()
        if let n = Int(t), n >= 1, n <= candidates.count {
            return candidates[n - 1]
        }
        if let re = try? NSRegularExpression(pattern: #"^(\d+)\s*(番|つめ|つ目|番目)?$"#, options: []),
           let m = re.firstMatch(in: t, options: [], range: NSRange(location: 0, length: (t as NSString).length)),
           m.numberOfRanges >= 2 {
            let num = (t as NSString).substring(with: m.range(at: 1))
            if let n = Int(num), n >= 1, n <= candidates.count {
                return candidates[n - 1]
            }
        }
        // 「1番を開いて」
        if let re = try? NSRegularExpression(pattern: #"(\d+)\s*番"#, options: []),
           let m = re.firstMatch(in: t, options: [], range: NSRange(location: 0, length: (t as NSString).length)),
           m.numberOfRanges >= 2 {
            let num = (t as NSString).substring(with: m.range(at: 1))
            if let n = Int(num), n >= 1, n <= candidates.count {
                return candidates[n - 1]
            }
        }

        // Exact / contains title match
        let folded = lower
        if let exact = candidates.first(where: { $0.title.lowercased() == folded }) {
            return exact
        }
        let byContain = candidates.filter { folded.contains($0.title.lowercased()) || $0.title.lowercased().contains(folded) }
        if byContain.count == 1 { return byContain[0] }
        if let best = byContain.max(by: { $0.title.count < $1.title.count }) { return best }

        // Fuzzy token overlap
        let tokens = folded.split(whereSeparator: { $0.isWhitespace || "、。,./".contains($0) }).map(String.init)
            .filter { $0.count >= 2 }
        if !tokens.isEmpty {
            var scored: [(Candidate, Int)] = []
            for c in candidates {
                let ct = c.title.lowercased()
                let score = tokens.reduce(0) { $0 + (ct.contains($1) ? $1.count : 0) }
                if score > 0 { scored.append((c, score)) }
            }
            if let top = scored.max(by: { $0.1 < $1.1 }) {
                return top.0
            }
        }

        // Continue / resume without pick → autopilot
        if JGenActAgent.isContinueRequest(t) {
            return bestForGoal(candidates, goal: goalHint ?? "")
        }

        return nil
    }

    nonisolated static func selectedDirectiveLine(_ candidate: Candidate) -> String {
        var parts = ["selected: \(candidate.title)"]
        if let axId = candidate.axId { parts.append("ax: \(axId)") }
        if let url = candidate.url { parts.append("url: \(url)") }
        return parts.joined(separator: " | ")
    }

    nonisolated static func bestForGoal(_ candidates: [Candidate], goal: String) -> Candidate {
        guard !goal.isEmpty else { return candidates[0] }
        let g = goal.lowercased()
        if let hit = candidates.first(where: { g.contains($0.title.lowercased()) || $0.title.lowercased().contains(whereGoalToken: g) }) {
            return hit
        }
        var best = candidates[0]
        var bestScore = 0
        for c in candidates {
            let score = g.split(separator: " ").reduce(0) { acc, tok in
                let t = String(tok)
                guard t.count >= 3 else { return acc }
                return acc + (c.title.lowercased().contains(t) ? t.count : 0)
            }
            if score > bestScore {
                bestScore = score
                best = c
            }
        }
        return best
    }

    // MARK: - Heuristics

    nonisolated static func isDestinationRole(_ role: String) -> Bool {
        let r = role.lowercased()
        return r == "link" || r == "result" || r == "cell" || r == "row"
            || r.contains("link")
    }

    nonisolated static func normalizeTitle(_ raw: String) -> String {
        var t = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        t = t.replacingOccurrences(of: "\n", with: " ")
        if t.count > 80 { t = String(t.prefix(77)) + "…" }
        return t
    }

    nonisolated static func isUsableTitle(_ title: String) -> Bool {
        let t = title.trimmingCharacters(in: .whitespacesAndNewlines)
        guard t.count >= 2 else { return false }
        if isChromeLinkTitle(t) { return false }
        // Skip pure punctuation / single glyphs
        let alnum = t.unicodeScalars.filter { CharacterSet.alphanumerics.contains($0) || (0x3040...0x30FF).contains($0.value) || (0x4E00...0x9FFF).contains($0.value) }
        return alnum.count >= 2
    }

    /// Browser / window chrome that is not a destination.
    nonisolated static func isChromeLinkTitle(_ title: String) -> Bool {
        let t = title.lowercased()
        let chrome = [
            "back", "forward", "reload", "refresh", "share", "tab", "close", "cancel",
            "ok", "done", "search", "address", "smart search", "new tab", "downloads",
            "bookmarks", "history", "reader", "sidebar", "show tabs", "previous", "next",
            "戻る", "進む", "再読み込み", "共有", "タブ", "閉じる", "キャンセル", "検索",
            "アドレス", "ダウンロード", "ブックマーク", "履歴",
        ]
        return chrome.contains { t == $0 || t.hasPrefix($0 + " ") }
    }
}

private extension String {
    func contains(whereGoalToken g: String) -> Bool {
        // True if any substantial token of `g` appears in self (self is already lowercased title).
        let tokens = g.split(whereSeparator: { $0.isWhitespace }).map(String.init).filter { $0.count >= 3 }
        return tokens.contains { self.contains($0) }
    }
}
