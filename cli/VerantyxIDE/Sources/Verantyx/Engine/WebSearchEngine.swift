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

    /// ReAct エンジンが失敗と判定するか
    var isFailure: Bool {
        // 4xx/5xx エラー or 明示的なエラーマーカー
        if httpStatus >= 400 { return true }
        let lower = markdown.lowercased()
        return lower.hasPrefix("❌") ||
               lower.contains("404") ||
               lower.contains("not found") ||
               lower.contains("(empty page)") ||
               lower.contains("(empty response)")
    }

    /// 失敗理由の短い説明（再思考プロンプト用）
    var failureReason: String {
        if httpStatus == 404 { return "HTTP 404 Not Found" }
        if httpStatus >= 400 { return "HTTP \(httpStatus) Error" }
        if httpStatus >= 500 { return "HTTP \(httpStatus) Server Error" }
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
        let searchURL = engine.searchURL(for: encodedQuery)

        return await browse(url: searchURL, preferredSource: preferredSource, originalQuery: cleanQuery, entropy: entropy, keyboardEntropy: keyboardEntropy, videoFrames: videoFrames)
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
            // Specific parsing for DuckDuckGo HTML to avoid massive country list clutter
            if url.contains("duckduckgo.com/html"), let snippetRegex = try? NSRegularExpression(pattern: "class=\"result__snippet\"[^>]*>(.*?)</a>", options: [.dotMatchesLineSeparators, .caseInsensitive]) {
                let ns = NSRange(html.startIndex..., in: html)
                let snippets = snippetRegex.matches(in: html, range: ns).compactMap { m -> String? in
                    guard let r = Range(m.range(at: 1), in: html) else { return nil }
                    return String(html[r])
                }
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
                httpStatus: httpStatus
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
