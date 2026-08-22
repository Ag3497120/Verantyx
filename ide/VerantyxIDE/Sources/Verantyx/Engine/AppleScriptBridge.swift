import Foundation
import AppKit

// MARK: - AppleScriptBridge
// Controls Safari and Chrome via AppleScript / osascript.
// This gives the AI access to the user's authenticated browser sessions —
// Gmail, GitHub, corporate SSO, etc. — without needing API keys or login automation.
//
// Architecture:
//   Swift → osascript → Safari/Chrome
//   Chrome response → String → AI context

actor AppleScriptBridge {

    static let shared = AppleScriptBridge()

    enum SystemBrowser: String, CaseIterable {
        case safari = "Safari"
        case chrome = "Google Chrome"
        case arc    = "Arc"
        case brave  = "Brave Browser"

        var isRunning: Bool {
            let ws = NSRunningApplication.runningApplications(withBundleIdentifier: bundleId)
            return !ws.isEmpty
        }

        var bundleId: String {
            switch self {
            case .safari: return "com.apple.Safari"
            case .chrome: return "com.google.Chrome"
            case .arc:    return "company.thebrowser.Browser"
            case .brave:  return "com.brave.Browser"
            }
        }
    }

    // MARK: - Open URL

    func open(_ url: String, in browser: SystemBrowser = .safari) async throws -> String {
        let tabSpecifier = (browser == .safari) ? "current tab" : "active tab"
        let script = """
        tell application "\(browser.rawValue)"
            activate
            open location "\(url.escapedForAppleScript)"
            delay 2
            return URL of \(tabSpecifier) of front window
        end tell
        """
        return try await runAppleScript(script)
    }

    // MARK: - Get page title

    func getTitle(from browser: SystemBrowser = .safari) async throws -> String {
        let script: String
        if browser == .safari {
            script = """
            tell application "Safari"
                return name of current tab of front window
            end tell
            """
        } else {
            script = """
            tell application "\(browser.rawValue)"
                return title of active tab of front window
            end tell
            """
        }
        return try await runAppleScript(script)
    }

    // MARK: - Get page source (as Markdown via html2md-alike)

    func getPageText(from browser: SystemBrowser = .safari) async throws -> String {
        let js = "document.body.innerText.substring(0, 8000)"
        let rawText = try await runJS(js, in: browser)
        return rawText
    }

    // MARK: - Execute JavaScript in browser tab

    func runJS(_ script: String, in browser: SystemBrowser = .safari) async throws -> String {
        let escapedScript = script.escapedForAppleScript
        let appleScript: String

        if browser == .safari {
            appleScript = """
            tell application "Safari"
                return do JavaScript "\(escapedScript)" in current tab of front window
            end tell
            """
        } else {
            // Chrome/Arc/Brave use WebDriver protocol via extension or CDP
            // For AppleScript, we use the execute script handler
            appleScript = """
            tell application "\(browser.rawValue)"
                tell active tab of front window
                    execute javascript "\(escapedScript)"
                end tell
            end tell
            """
        }
        return try await runAppleScript(appleScript)
    }

    // MARK: - Search via browser

    func search(_ query: String, engine: SearchEngine = .google, in browser: SystemBrowser = .safari) async throws -> String {
        let encodedQuery = query.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? query
        let searchURL = engine.searchURL(for: encodedQuery)
        _ = try await open(searchURL, in: browser)

        // Wait for page load, then extract text
        try await Task.sleep(nanoseconds: 3_000_000_000)
        return try await getPageText(from: browser)
    }

    // MARK: - Get current URL

    func getCurrentURL(from browser: SystemBrowser = .safari) async throws -> String {
        let script: String
        if browser == .safari {
            script = "tell application \"Safari\" to return URL of current tab of front window"
        } else {
            script = "tell application \"\(browser.rawValue)\" to return URL of active tab of front window"
        }
        return try await runAppleScript(script)
    }

    // MARK: - Click element by JS selector

    func click(selector: String, in browser: SystemBrowser = .safari) async throws -> String {
        let js = "document.querySelector('\(selector)')?.click(); 'clicked'"
        return try await runJS(js, in: browser)
    }

    // MARK: - Fill form field

    func fillField(selector: String, value: String, in browser: SystemBrowser = .safari) async throws -> String {
        let escapedValue = value.replacingOccurrences(of: "\"", with: "\\\"")
        let js = """
        var el = document.querySelector('\(selector)');
        if (el) { el.value = '\(escapedValue)'; el.dispatchEvent(new Event('input', {bubbles:true})); 'ok'; } else { 'not found'; }
        """
        return try await runJS(js, in: browser)
    }

    // MARK: - Available browsers

    func installedBrowsers() -> [SystemBrowser] {
        SystemBrowser.allCases.filter { $0.isRunning || FileManager.default.fileExists(atPath: "/Applications/\($0.rawValue).app") }
    }

    /// For callers that need a one-off script this bridge has no verb for
    /// (window geometry, for instance) without each of them re-inventing
    /// the osascript plumbing.
    @discardableResult
    func runScriptPublic(_ script: String) async throws -> String {
        try await runAppleScript(script)
    }

    // MARK: - Safari scripting access
    //
    // "Allow JavaScript from Apple Events" decides whether page text can
    // be read from the DOM at all; without it every browse falls back to
    // screen OCR, which misses everything off-screen.
    //
    // The obvious implementation — read the preference at launch — does
    // not work and would be worse than nothing. Safari keeps it in a
    // TCC-protected container: CFPreferencesCopyAppValue returns nil and
    // the plist is unreadable REGARDLESS of the actual setting (verified
    // on this machine). A check built on that would tell everyone their
    // setting was off, including the people who had already turned it on.
    //
    // So the signal is behavioural, not declarative: the flag is set when
    // Safari actually refuses a script (AppleScript error 37:126) and
    // cleared the moment a DOM read succeeds. The guidance then shows at
    // launch while the block is real, and stops by itself once it is
    // fixed — no dismissal to remember, and nothing written to Safari.
    enum SafariScriptingAccess {
        private static let blockedKey = "safari_js_blocked"

        static var isKnownBlocked: Bool {
            UserDefaults.standard.bool(forKey: blockedKey)
        }

        static func recordBlocked() {
            UserDefaults.standard.set(true, forKey: blockedKey)
        }

        /// A DOM read worked, so whatever was blocking it is gone.
        static func recordWorking() {
            guard UserDefaults.standard.bool(forKey: blockedKey) else { return }
            UserDefaults.standard.set(false, forKey: blockedKey)
        }

        static func guidance() -> String {
            AppLanguage.shared.t(
                "🧩 Safari is blocking scripted page reads, so browsing falls back to screen OCR "
                + "(anything off-screen is invisible). Enable it once — Verantyx will not change "
                + "another app's security setting for you: Safari → Settings → Advanced → "
                + "\"Show features for web developers\", then Develop → \"Allow JavaScript from "
                + "Apple Events\". This notice disappears by itself once a page reads correctly.",
                "🧩 Safari がスクリプトからのページ取得を拒否しているため、閲覧は画面OCRに頼っています"
                + "（画面外の内容は取得できません）。1度だけ有効化してください — 他アプリのセキュリティ設定を"
                + "Verantyxが代わりに変更することはしません: Safari → 設定 → 詳細 →「Webデベロッパ用の機能を表示」、"
                + "その後 開発メニュー →「Apple EventsからのJavaScriptを許可」。"
                + "ページが正しく読めた時点で、この案内は自動的に出なくなります。")
        }
    }

    // MARK: - Core AppleScript runner

    @discardableResult
    private func runAppleScript(_ script: String) async throws -> String {
        return try await withCheckedThrowingContinuation { continuation in
            DispatchQueue.global(qos: .userInitiated).async {
                let process = Process()
                process.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
                process.arguments = ["-e", script]

                let outPipe = Pipe()
                process.standardOutput = outPipe
                process.standardError  = outPipe   // ⚠️ 同一パイプ — dual-pipe deadlock 防止

                do {
                    try process.run()

                    let outData = outPipe.fileHandleForReading.readDataToEndOfFile()

                    process.waitUntilExit()

                    if process.terminationStatus != 0 {
                        let errMsg = String(data: outData, encoding: .utf8) ?? "unknown error"
                        continuation.resume(throwing: AppleScriptError.scriptFailed(errMsg))
                    } else {
                        let result = (String(data: outData, encoding: .utf8) ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
                        continuation.resume(returning: result)
                    }
                } catch {
                    continuation.resume(throwing: error)
                }
            }
        }
    }
}

// MARK: - SearchEngine

enum SearchEngine: String, CaseIterable {
    case duckduckgo     = "DuckDuckGo"
    case duckduckgoHTML = "DuckDuckGoHTML"
    case google         = "Google"
    case bing           = "Bing"

    func searchURL(for query: String) -> String {
        switch self {
        case .duckduckgo:     return "https://duckduckgo.com/?q=\(query)"
        case .duckduckgoHTML: return "https://html.duckduckgo.com/html/?q=\(query)"
        case .google:         return "https://www.google.com/search?q=\(query)"
        case .bing:           return "https://www.bing.com/search?q=\(query)"
        }
    }
}

// MARK: - AppleScriptError

enum AppleScriptError: Error, LocalizedError {
    case scriptFailed(String)
    case browserNotFound(String)

    var errorDescription: String? {
        switch self {
        case .scriptFailed(let m):    return "AppleScript error: \(m)"
        case .browserNotFound(let b): return "\(b) is not installed or running."
        }
    }
}

// MARK: - String Helpers

private extension String {
    var escapedForAppleScript: String {
        self
            .replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "\"", with: "\\\"")
            .replacingOccurrences(of: "\n", with: "\\n")
            .replacingOccurrences(of: "\r", with: "\\r")
    }
}
