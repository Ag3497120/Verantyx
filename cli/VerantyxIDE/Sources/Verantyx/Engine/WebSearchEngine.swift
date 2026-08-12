import Foundation
#if canImport(AppKit)
import AppKit
#endif

// MARK: - WebSearchEngine
// High-level search/browse interface for the AI agent.
// Chooses between verantyx-browser (stealth WebKit) and AppleScript (Safari/Chrome)
// based on user settings and what's available.

struct WebSearchResult {
    var query:    String
    var url:      String
    var markdown: String
    var source:   BrowseSource
    var truncated: Bool
    /// HTTP ステータスコード（0 = 不明 / JS レンダリング済み）
    var httpStatus: Int = 0
    /// 構造的に数えられた検索ヒット件数。DuckDuckGo HTML を URLSession で
    /// 取った場合のみ得られる（Safari で開いて本文を抜く主要経路では nil）。
    /// 分かるときは最も強い信号なので優先して使う。
    var resultCount: Int? = nil

    /// ReAct エンジンが失敗と判定するか（通信レベルのみ）
    ///
    /// "404" / "not found" は**先頭部分だけ**を見る。以前は markdown 全体に
    /// contains を掛けていたため、検索結果の本文にこれらの語が現れるだけで
    /// 通信失敗と誤判定していた（"not found" を含む問い合わせでは確実に誤爆
    /// する）。エラーページなら該当文言は必ず冒頭に出るので、先頭に限定して
    /// も検出力は落ちない。
    ///
    /// 「通信は成功したが中身が無関係」の判定はここではなく `verdict` が行う。
    var isFailure: Bool {
        if httpStatus >= 400 { return true }
        let lower = markdown.lowercased()
        if lower.hasPrefix("❌") { return true }
        if lower.contains("(empty page)") || lower.contains("(empty response)") { return true }
        let head = String(lower.prefix(512))
        return head.contains("404") || head.contains("not found")
    }

    /// 失敗理由の短い説明（再思考プロンプト用）
    var failureReason: String {
        // 500 番台を 400 番台より先に見る。順序が逆だと >= 400 に先取りされて
        // 500 の分岐へ到達できない。
        if httpStatus == 404 { return "HTTP 404 Not Found" }
        if httpStatus >= 500 { return "HTTP \(httpStatus) Server Error" }
        if httpStatus >= 400 { return "HTTP \(httpStatus) Error" }
        if markdown.contains("(empty page)") { return "ページが空でした" }
        if markdown.contains("(empty response)") { return "レスポンスが空でした" }
        if markdown.hasPrefix("❌") { return String(markdown.prefix(120)) }
        return "コンテンツを取得できませんでした"
    }

    var contextSnippet: String {
        let limit = 6000
        if markdown.count <= limit { return markdown }
        return String(markdown.prefix(limit)) + "\n\n[… content truncated at 6000 chars …]"
    }

    // MARK: - 関連性の判定

    enum SearchVerdict {
        case ok
        case transportFailure(String)
        /// 通信は成功したが、探していたものが見つかっていない。
        /// 付随する文字列は再検索プロンプトへ渡す「見つからなかった語」。
        case noRelevantResults(reason: String, missingTerm: String?)
    }

    /// 「200番で長いHTMLが返ってきたが中身は0件」を検出する。
    ///
    /// 未公開の固有名詞で検索すると、検索エンジンは正常なページを返すので
    /// `isFailure` では捕まらず、再検索が一度も走らなかった。これがその穴を
    /// 埋める判定。**空振りの再検索は高くつくので意図的に保守的**にしてある:
    /// 弱い信号(語のカバレッジ・本文の短さ)は単独では失敗と見なさず、同時に
    /// 成立したときだけ。
    var verdict: SearchVerdict {
        if isFailure { return .transportFailure(failureReason) }

        let text = markdown
        let lower = text.lowercased()

        // 1) 明示的な0件マーカー。本文中の引用で誤爆しないよう先頭のみ見る。
        let head = String(lower.prefix(1500))
        let zeroMarkers = [
            "did not match any documents",
            "did not match any",
            "に一致する情報は見つかりませんでした",
            "に一致する情報は、見つかりませんでした",
            "no results found for",
            "no results found",
            "見つかりませんでした",
        ]
        if let hit = zeroMarkers.first(where: { head.contains($0) }) {
            return .noRelevantResults(reason: "検索エンジンが0件と報告 (\(hit))",
                                      missingTerm: Self.mostDistinctiveTerm(of: query))
        }

        // 2) 構造的に数えられたなら、それが最も強い。
        if let count = resultCount, count == 0 {
            return .noRelevantResults(reason: "検索結果0件",
                                      missingTerm: Self.mostDistinctiveTerm(of: query))
        }

        // 3)(弱)クエリ語のカバレッジ / 4)(弱)有効本文の短さ
        let terms = Self.contentTerms(of: query)
        let distinctive = Self.mostDistinctiveTerm(of: query)
        let present = terms.filter { lower.contains($0.lowercased()) }.count
        let coverage = terms.isEmpty ? 1.0 : Double(present) / Double(terms.count)
        let usefulLength = Self.usefulTextLength(text)

        // 安全弁: 十分な長さがあり語も拾えているなら、表現が違うだけとみなす。
        if usefulLength > 1500 && coverage >= 0.5 { return .ok }

        let distinctiveMissing = distinctive.map { !lower.contains($0.lowercased()) } ?? false
        if distinctiveMissing && coverage < 0.34 && usefulLength < 200 {
            return .noRelevantResults(
                reason: String(format: "語の一致率 %.0f%% / 有効本文 %d文字", coverage * 100, usefulLength),
                missingTerm: distinctive)
        }
        return .ok
    }

    /// クエリを内容語に分解する。日本語は空白で切れないので、空白トークンが
    /// 1つしか取れない場合に限り2-gramへ落とす。
    static func contentTerms(of query: String) -> [String] {
        let stop: Set<String> = [
            "の", "を", "に", "は", "が", "で", "と", "から", "まで", "へ", "や",
            "方法", "とは", "する", "した", "して", "教えて", "調べて", "ください",
            "how", "to", "the", "a", "an", "of", "for", "in", "on", "is", "and",
            "what", "setup", "set", "up", "guide", "example", "使い方",
        ]
        let raw = query
            .components(separatedBy: CharacterSet.whitespacesAndNewlines.union(.punctuationCharacters))
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { $0.count >= 2 && !stop.contains($0.lowercased()) }
        if raw.count >= 2 { return raw }

        // 空白で割れなかった（日本語の連続など）→ 2-gram
        let joined = query.filter { !$0.isWhitespace }
        guard joined.count >= 4 else { return raw }
        let chars = Array(joined)
        var grams: [String] = []
        var i = 0
        while i + 1 < chars.count {
            let g = String(chars[i...i+1])
            if !stop.contains(g) { grams.append(g) }
            i += 2
        }
        return grams.isEmpty ? raw : grams
    }

    /// 一番「珍しそうな」語。固有名詞である可能性が高く、これが本文に一度も
    /// 出ないことが「そんなものは無い」の最も分かりやすい徴候になる。
    static func mostDistinctiveTerm(of query: String) -> String? {
        contentTerms(of: query).max(by: { $0.count < $1.count })
    }

    /// ナビゲーションや定型文を除いた、実質的な本文の長さ。
    static func usefulTextLength(_ text: String) -> Int {
        let chrome = [
            "Images", "Videos", "News", "Shopping", "Maps", "Tools", "Settings",
            "Privacy", "Terms", "Sign in", "すべて", "画像", "動画", "ニュース",
            "地図", "設定", "プライバシー", "規約", "ログイン",
        ]
        var s = text
        for c in chrome { s = s.replacingOccurrences(of: c, with: " ") }
        return s.trimmingCharacters(in: .whitespacesAndNewlines)
                .replacingOccurrences(of: "\n", with: " ")
                .replacingOccurrences(of: "  ", with: " ")
                .count
    }
}

enum BrowseSource {

    case safari
    case chrome
    case arc
    case fetch              // URLSession fallback (no JS)
    case firefoxBridge      // Python script for Stealth Browser
}

// MARK: - WebSearchEngine

actor WebSearchEngine {

    static let shared = WebSearchEngine()


    private let applescript = AppleScriptBridge.shared

    // MARK: - Main: search

    func search(
        query: String,
        engine: SearchEngine = .google,
        preferredSource: BrowseSource = .safari,
        entropy: [[Double]]? = nil,
        keyboardEntropy: [Double]? = nil,
        videoFrames: [String]? = nil
    ) async -> WebSearchResult {

        // AIがクエリ全体をダブルクォーテーションで囲んで出力した場合の完全一致検索（検索失敗）を防ぐ
        var cleanQuery = query.trimmingCharacters(in: .whitespacesAndNewlines)
        if cleanQuery.hasPrefix("\"") && cleanQuery.hasSuffix("\"") && cleanQuery.count >= 2 {
            cleanQuery = String(cleanQuery.dropFirst().dropLast())
        }
        
        // シングルクォーテーションの場合も同様に除去
        if cleanQuery.hasPrefix("'") && cleanQuery.hasSuffix("'") && cleanQuery.count >= 2 {
            cleanQuery = String(cleanQuery.dropFirst().dropLast())
        }

        let encodedQuery = cleanQuery.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? cleanQuery

        // ── DuckDuckGo HTML first ────────────────────────────────────────
        // The Safari→Google route fetches the SERP itself, and in this
        // environment Google answers with a JS/consent shell — a real run
        // searched twice, injected that shell, and the model honestly
        // reported "no information obtained" while the same query in
        // html.duckduckgo.com returned rich results. DDG's HTML endpoint
        // needs no JS and no browser: one URLSession GET, parsed titles +
        // snippets. Safari/Google remains the fallback, not the default.
        if let ddg = await duckDuckGoHTMLSearch(query: cleanQuery, encoded: encodedQuery) {
            return ddg
        }

        let searchURL = engine.searchURL(for: encodedQuery)
        return await browse(url: searchURL, preferredSource: preferredSource, originalQuery: cleanQuery, entropy: entropy, keyboardEntropy: keyboardEntropy, videoFrames: videoFrames)
    }

    /// One GET against html.duckduckgo.com, no JS, no browser. Returns nil
    /// when the fetch fails or yields fewer than two substantive results —
    /// the caller then falls back to the browser route.
    private func duckDuckGoHTMLSearch(query: String, encoded: String) async -> WebSearchResult? {
        guard let url = URL(string: "https://html.duckduckgo.com/html/?q=\(encoded)") else { return nil }
        var req = URLRequest(url: url)
        req.timeoutInterval = 12
        req.setValue("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Version/17.0 Safari/605.1.15",
                     forHTTPHeaderField: "User-Agent")
        guard let (data, resp) = try? await URLSession.shared.data(for: req),
              (resp as? HTTPURLResponse)?.statusCode == 200,
              let html = String(data: data, encoding: .utf8) else { return nil }

        func strip(_ s: String) -> String {
            var t = s.replacingOccurrences(of: "<[^>]+>", with: "", options: .regularExpression)
            for (ent, ch) in [("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                              ("&quot;", "\""), ("&#x27;", "'"), ("&nbsp;", " ")] {
                t = t.replacingOccurrences(of: ent, with: ch)
            }
            return t.trimmingCharacters(in: .whitespacesAndNewlines)
        }

        // result__a carries the title (and the redirect href), result__snippet
        // the summary — stable for years on the html endpoint.
        let titleRe = try? NSRegularExpression(
            pattern: #"<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>([\s\S]*?)</a>"#)
        let snippetRe = try? NSRegularExpression(
            pattern: #"class="result__snippet"[^>]*>([\s\S]*?)</a>"#)
        let range = NSRange(html.startIndex..., in: html)
        let titles = (titleRe?.matches(in: html, range: range) ?? []).compactMap { m -> (String, String)? in
            guard let hr = Range(m.range(at: 1), in: html),
                  let tr = Range(m.range(at: 2), in: html) else { return nil }
            var href = String(html[hr])
            // uddg redirect → the real URL is in the uddg= parameter.
            if let r = href.range(of: "uddg="),
               let decoded = String(href[r.upperBound...])
                    .components(separatedBy: "&").first?
                    .removingPercentEncoding {
                href = decoded
            }
            return (strip(String(html[tr])), href)
        }
        let snippets = (snippetRe?.matches(in: html, range: range) ?? []).compactMap { m -> String? in
            guard let sr = Range(m.range(at: 1), in: html) else { return nil }
            return strip(String(html[sr]))
        }

        var lines: [String] = []
        for (i, t) in titles.prefix(5).enumerated() where !t.0.isEmpty {
            let snippet = i < snippets.count ? snippets[i] : ""
            lines.append("[\(i + 1)] \(t.0)\n    \(t.1)\n    \(snippet)")
        }
        guard lines.count >= 2 else { return nil }

        return WebSearchResult(
            query: query,
            url: "https://html.duckduckgo.com/html/?q=\(encoded)",
            markdown: lines.joined(separator: "\n\n"),
            source: .fetch,
            truncated: false,
            httpStatus: 200,
            resultCount: lines.count
        )
    }

    // MARK: - Main: browse URL

    func browse(
        url: String,
        preferredSource: BrowseSource = .safari,
        originalQuery: String? = nil,
        entropy: [[Double]]? = nil,
        keyboardEntropy: [Double]? = nil,
        videoFrames: [String]? = nil
    ) async -> WebSearchResult {
        
        var finalEntropy = entropy
        var finalTarget: [Double]? = nil
        var currentVideoFrames = videoFrames
        var currentKeyboardEntropy = keyboardEntropy
        
        // ── 🧩 Biometric Entropy Collection & Fully Automatic Mode 🧩 ──
        let (isAutoMode, isEntropyStale) = await MainActor.run { () -> (Bool, Bool) in
            let savedSamplesCount = UserDefaults.standard.integer(forKey: "bio_samples_count")
            if savedSamplesCount >= 200 {
                return (true, false)
            } else {
                if let ts = AppState.shared?.lastEntropyTimestamp {
                    return (false, Date().timeIntervalSince(ts) > 300)
                } else {
                    return (false, true)
                }
            }
        }
        
        if isAutoMode {
            print("Telemetry: Fully Automatic Mode (200+ samples). Biometric lock bypassed.")
            // Try to use any remaining recent entropy anyway, but do not wait
            let (points, frames, kb) = await MainActor.run {
                (AppState.shared?.lastEntropy, AppState.shared?.lastVideoFrames, AppState.shared?.lastKeyboardEntropy)
            }
            if finalEntropy == nil, let pts = points {
                let mapped = pts.map { [Double($0.x), Double($0.y)] }
                finalEntropy = stride(from: 0, to: mapped.count, by: max(1, mapped.count / 100)).prefix(100).map { mapped[$0] }
            }
            if currentVideoFrames == nil { currentVideoFrames = frames }
            if currentKeyboardEntropy == nil { currentKeyboardEntropy = kb }
            
        } else if isEntropyStale {
            print("Telemetry: Biometric entropy stale or missing. Triggering puzzle.")
            await MainActor.run { 
                AppState.shared?.requiresHumanPuzzle = true
                #if os(macOS)
                NSApp.requestUserAttention(.criticalRequest)
                #endif
            }
            var waitingForPuzzle = await MainActor.run { AppState.shared?.requiresHumanPuzzle == true }
            while waitingForPuzzle {
                // Unlimited wait time for biometric entropy as requested
                try? await Task.sleep(nanoseconds: 200_000_000)
                waitingForPuzzle = await MainActor.run { AppState.shared?.requiresHumanPuzzle == true }
            }
            
            // Retrieve the freshly captured entropy
            let (newPoints, newFrames, newKb) = await MainActor.run {
                (AppState.shared?.lastEntropy, AppState.shared?.lastVideoFrames, AppState.shared?.lastKeyboardEntropy)
            }
            if let pts = newPoints {
                let mapped = pts.map { [Double($0.x), Double($0.y)] }
                finalEntropy = stride(from: 0, to: mapped.count, by: max(1, mapped.count / 100)).prefix(100).map { mapped[$0] }
            }
            currentVideoFrames = newFrames
            currentKeyboardEntropy = newKb
            
            // Increment sample count
            let newCount = UserDefaults.standard.integer(forKey: "bio_samples_count") + 1
            UserDefaults.standard.set(newCount, forKey: "bio_samples_count")
            print("Telemetry: Biometric sample saved. Total: \(newCount)/200 for Auto Mode")
        } else if finalEntropy == nil {
            // Fresh entropy available but not passed in directly
            let (points, frames, kb) = await MainActor.run {
                (AppState.shared?.lastEntropy, AppState.shared?.lastVideoFrames, AppState.shared?.lastKeyboardEntropy)
            }
            if let pts = points {
                let mapped = pts.map { [Double($0.x), Double($0.y)] }
                finalEntropy = stride(from: 0, to: mapped.count, by: max(1, mapped.count / 100)).prefix(100).map { mapped[$0] }
            }
            if currentVideoFrames == nil { currentVideoFrames = frames }
            if currentKeyboardEntropy == nil { currentKeyboardEntropy = kb }
        }
        
        // ── COMPLETE VERSION: Qwen3.6-27B Video Analysis Pipeline ──
        if let frames = currentVideoFrames, !frames.isEmpty {
            if let extracted = await QwenVideoAnalyzer.shared.extractEntropyFromVideo(base64Frames: frames) {
                finalEntropy = extracted
            }
            if let target = await QwenVideoAnalyzer.shared.identifyTargetCoordinates(screenshotBase64: frames) {
                finalTarget = target
            }
        }


        let result: WebSearchResult
        switch preferredSource {


        case .safari:
            result = await browseWithAppleScript(url: url, browser: .safari, query: originalQuery)

        case .chrome:
            result = await browseWithAppleScript(url: url, browser: .chrome, query: originalQuery)

        case .arc:
            result = await browseWithAppleScript(url: url, browser: .arc, query: originalQuery)

        case .firefoxBridge:
            result = await browseWithFirefoxBridge(url: url, query: originalQuery)

        case .fetch:
            result = await browseWithFetch(url: url, query: originalQuery)
        }
        
        // Handle entropy invalidation and rate limits
        if !result.isFailure {
            print("Telemetry: Biometric entropy successfully consumed for search. [\(url)]")
            await MainActor.run {
                AppState.shared?.lastEntropy = nil
                AppState.shared?.lastEntropyTimestamp = nil
                AppState.shared?.lastVideoFrames = nil
                AppState.shared?.lastKeyboardEntropy = nil
            }
        } else if result.httpStatus == 429 || result.markdown.contains("429") || result.markdown.contains("Rate limit") {
            print("Telemetry: Search provider rate limit (429) detected. Triggering 60s cooldown.")
            await MainActor.run {
                AppState.shared?.searchCooldownUntil = Date().addingTimeInterval(60) // 1 min cooldown
            }
        }
        
        return result
    }





    // MARK: - AppleScript (Safari / Chrome)

    private func browseWithAppleScript(url: String, browser: AppleScriptBridge.SystemBrowser, query: String?) async -> WebSearchResult {
        do {
            _ = try await applescript.open(url, in: browser)
            try await Task.sleep(nanoseconds: 4_000_000_000) // wait for load
            let text = try await applescript.getPageText(from: browser)
            let currentURL = (try? await applescript.getCurrentURL(from: browser)) ?? url

            return WebSearchResult(
                query: query ?? url,
                url: currentURL,
                markdown: text.isEmpty ? "(empty page)" : text,
                source: browser == .safari ? .safari : .safari,
                truncated: text.count > 6000
            )
        } catch {
            return WebSearchResult(
                query: query ?? url,
                url: url,
                markdown: "❌ \(browser.rawValue) error: \(error.localizedDescription)",
                source: browser == .safari ? .safari : .safari,
                truncated: false
            )
        }
    }

    // MARK: - Firefox Bridge (Python)

    private func browseWithFirefoxBridge(url: String, query: String?) async -> WebSearchResult {
        let actualQuery = query ?? url
        do {
            let bridgePath = "/Users/motonishikoudai/verantyx-cli/firefox_agent_bridge.py"
            guard FileManager.default.fileExists(atPath: bridgePath) else {
                return WebSearchResult(query: actualQuery, url: url, markdown: "❌ firefox_agent_bridge.py not found at \(bridgePath)", source: .firefoxBridge, truncated: false)
            }
            
            let proc = Process()
            proc.executableURL = URL(fileURLWithPath: "/usr/bin/env")
            proc.arguments = ["python3", bridgePath, "--search", actualQuery]
            proc.environment = [
                "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:/Library/Frameworks/Python.framework/Versions/3.13/bin:/Library/Frameworks/Python.framework/Versions/3.12/bin"
            ]
            
            let pipe = Pipe()
            proc.standardOutput = pipe
            proc.standardError = pipe
            
            try proc.run()
            proc.waitUntilExit()
            
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            let output = String(data: data, encoding: .utf8) ?? ""
            
            if proc.terminationStatus != 0 {
                return WebSearchResult(query: actualQuery, url: url, markdown: "❌ Firefox Bridge Error: \(output)", source: .firefoxBridge, truncated: false)
            }
            
            let text = stripHTML(output)
            return WebSearchResult(query: actualQuery, url: url, markdown: text, source: .firefoxBridge, truncated: text.count > 6000)
        } catch {
            return WebSearchResult(query: actualQuery, url: url, markdown: "❌ Firefox Bridge Exception: \(error.localizedDescription)", source: .firefoxBridge, truncated: false)
        }
    }

    // MARK: - URLSession fallback (no JS, visible headers)

    private func browseWithFetch(url: String, query: String?, note: String? = nil) async -> WebSearchResult {
        do {
            guard let reqURL = URL(string: url) else {
                return WebSearchResult(query: query ?? url, url: url,
                                      markdown: "❌ 無効なURL: \(url)",
                                      source: .fetch, truncated: false, httpStatus: 0)
            }
            var request = URLRequest(url: reqURL)
            request.setValue("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36", forHTTPHeaderField: "User-Agent")
            request.setValue("text/html,application/xhtml+xml", forHTTPHeaderField: "Accept")
            request.timeoutInterval = 15

            let (data, response) = try await URLSession.shared.data(for: request)
            // ── HTTP ステータスを捕捉 ────────────────────────────────────
            let httpStatus = (response as? HTTPURLResponse)?.statusCode ?? 0

            // 4xx / 5xx は即座に失敗として返す
            if httpStatus >= 400 {
                return WebSearchResult(
                    query: query ?? url,
                    url: url,
                    markdown: "❌ HTTP \(httpStatus): \(url)",
                    source: .fetch,
                    truncated: false,
                    httpStatus: httpStatus
                )
            }

            let html = String(data: data, encoding: .utf8) ?? ""
            
            var text = ""
            // 構造的に数えられるのはこの経路だけ。数えられた件数は verdict が
            // 最優先で使う（他経路では nil のまま）。
            var snippetCount: Int? = nil
            // Specific parsing for DuckDuckGo HTML to avoid massive country list clutter
            if url.contains("duckduckgo.com/html"), let snippetRegex = try? NSRegularExpression(pattern: "class=\"result__snippet\"[^>]*>(.*?)</a>", options: [.dotMatchesLineSeparators, .caseInsensitive]) {
                let ns = NSRange(html.startIndex..., in: html)
                let snippets = snippetRegex.matches(in: html, range: ns).compactMap { m -> String? in
                    guard let r = Range(m.range(at: 1), in: html) else { return nil }
                    return String(html[r])
                }
                snippetCount = snippets.count
                if !snippets.isEmpty {
                    text = stripHTML(snippets.joined(separator: "\n\n"))
                } else {
                    text = stripHTML(html)
                }
            } else {
                text = stripHTML(html)
            }
            
            var result = text
            if let note = note {
                result = note + "\n\n" + text
            }

            return WebSearchResult(
                query: query ?? url,
                url: url,
                markdown: result.isEmpty ? "(empty response)" : result,
                source: .fetch,
                truncated: result.count > 6000,
                httpStatus: httpStatus,
                resultCount: snippetCount
            )
        } catch {
            return WebSearchResult(
                query: query ?? url,
                url: url,
                markdown: "❌ Fetch error: \(error.localizedDescription)",
                source: .fetch,
                truncated: false,
                httpStatus: 0
            )
        }
    }

    // MARK: - Helpers

    private func stripHTML(_ html: String) -> String {
        // Remove scripts, styles, then tags
        var text = html
        let patterns = [
            "<script[^>]*>[\\s\\S]*?</script>",
            "<style[^>]*>[\\s\\S]*?</style>",
            "<!--[\\s\\S]*?-->",
            "<[^>]+>"
        ]
        for pattern in patterns {
            if let regex = try? NSRegularExpression(pattern: pattern, options: .caseInsensitive) {
                text = regex.stringByReplacingMatches(in: text, range: NSRange(text.startIndex..., in: text), withTemplate: " ")
            }
        }
        
        // Remove DuckDuckGo UI clutter (country list, date filters) that takes up ~800 chars
        if let ddgRegex = try? NSRegularExpression(pattern: "All Regions\\s+Argentina\\s+Australia.*?(Past Year)", options: [.dotMatchesLineSeparators, .caseInsensitive]) {
            text = ddgRegex.stringByReplacingMatches(in: text, range: NSRange(text.startIndex..., in: text), withTemplate: "")
        }
        
        // Collapse whitespace
        text = text.components(separatedBy: .whitespacesAndNewlines)
            .filter { !$0.isEmpty }
            .joined(separator: " ")

        // Decode common HTML entities
        text = text
            .replacingOccurrences(of: "&amp;",  with: "&")
            .replacingOccurrences(of: "&lt;",   with: "<")
            .replacingOccurrences(of: "&gt;",   with: ">")
            .replacingOccurrences(of: "&quot;", with: "\"")
            .replacingOccurrences(of: "&#39;",  with: "'")
            .replacingOccurrences(of: "&nbsp;", with: " ")

        return String(text.prefix(12000))
    }
}
