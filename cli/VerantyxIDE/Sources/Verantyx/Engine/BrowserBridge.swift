import Foundation
import AppKit
import Vision

// MARK: - BrowserBridge
//
// verantyx-browser (Rust/WKWebView) を JSON IPC (stdin/stdout) で制御する。
//
// ── 改善点 (v2) ──────────────────────────────────────────────────────────
//   ・リクエスト ID 対応: 全コマンドに UInt64 ID を付与、レスポンスで照合
//   ・lastResponse ポーリング廃止 → CheckedContinuation マップで即時 resolve
//   ・"navigating" レスポンスを中間状態として扱い "hitl_done" を最終完了とする
//   ・ping コマンドによるヘルスチェック
//   ・自動再接続: クラッシュ時に次のリクエストで再 launch を試みる

// MARK: - Data types

struct BrowserCommand: Codable {
    var cmd:  String
    var url:  String?
    var text: String?
    var id:   UInt64?
    var entropy: [[Double]]?
    var keyboard_entropy: [Double]?
    var target: [Double]?
}

struct BrowserResponse: Codable {
    var id:       UInt64?   // ← Rust 側からエコーバックされる
    var status:   String
    var message:  String?
    var url:      String?
    var markdown: String?
    var title:    String?
}

enum BrowserState: Equatable {
    case idle
    case launching
    case ready
    case navigating(String)
    case error(String)
}

// MARK: - Pending request types

private enum PendingKind {
    case markdown   // HITL_DONE / DOM → markdown を返す
    case eval       // EVAL_RES / EVAL_ERR → message を返す
    case pong       // ping → status == "pong"
}

private struct PendingRequest {
    let kind: PendingKind
    let continuation: CheckedContinuation<BrowserResponse, Error>
}

// MARK: - BrowserBridge Actor

actor BrowserBridge {

    static let shared = BrowserBridge()

    // ── プロセス状態 ────────────────────────────────────────────────────────
    private var process:      Process?
    private var stdinPipe:    Pipe?
    private var stdoutPipe:   Pipe?
    private var readerTask:   Task<Void, Never>?

    // ── リクエスト管理 ───────────────────────────────────────────────────────
    private var nextID:    UInt64 = 1
    private var pending:   [UInt64: PendingRequest] = [:]
    /// PAGE_READY 待ち専用 Continuation（穎動中に最大1個）
    private var readyCont: CheckedContinuation<Void, Error>?

    private(set) var state: BrowserState = .idle

    // ── バイナリパス ────────────────────────────────────────────────────────
    //
    // 解決順序（配信時・開発時の両方に対応）:
    //   1. Bundle.main の MacOS/ フォルダ内（配信 .app パッケージ）
    //   2. Bundle.main の Resources/ フォルダ内（XcodeGen 経由でコピーされる）
    //   3. Cargo debug ビルド出力（開発専用）
    //   4. Cargo release ビルド出力（開発専用）
    var binaryPath: String {
        // ① アプリバンドル内を最優先（配信時は必ずここにある）
        let bundleMacOS = Bundle.main.bundleURL
            .appendingPathComponent("Contents/MacOS/verantyx-browser").path
        if FileManager.default.fileExists(atPath: bundleMacOS) { return bundleMacOS }

        // ② Bundle.main forResource（Resources/ にコピーされたケース）
        if let bundleRes = Bundle.main.path(forResource: "verantyx-browser", ofType: nil) {
            return bundleRes
        }

        // ③④ 開発時 Cargo ビルド出力
        let root    = projectRoot
        let debug   = "\(root)/VerantyxIDE/verantyx-browser/target/debug/verantyx-browser"
        let release = "\(root)/VerantyxIDE/verantyx-browser/target/release/verantyx-browser"
        let fallbackDebug = "\(root)/verantyx-browser/target/debug/verantyx-browser"
        let fallbackRelease = "\(root)/verantyx-browser/target/release/verantyx-browser"

        if FileManager.default.fileExists(atPath: debug)   { return debug }
        if FileManager.default.fileExists(atPath: release) { return release }
        if FileManager.default.fileExists(atPath: fallbackDebug)   { return fallbackDebug }
        if FileManager.default.fileExists(atPath: fallbackRelease) { return fallbackRelease }

        // フォールバック（起動失敗エラーで詳細パスをログ出力させる）
        return debug
    }

    private var projectRoot: String {
        var url = Bundle.main.bundleURL
        
        // 1. バンドル階層から親を辿る（標準構成用）
        for _ in 0..<8 {
            url = url.deletingLastPathComponent()
            if FileManager.default.fileExists(atPath: url.appendingPathComponent("verantyx-browser").path) {
                return url.path
            }
            if FileManager.default.fileExists(atPath: url.appendingPathComponent("VerantyxIDE/verantyx-browser").path) {
                return url.path
            }
        }
        
        // 2. #fileマクロベースの相対位置（ソースファイルからの相対位置）
        let srcPath = URL(fileURLWithPath: #file)
        var parent = srcPath
        for _ in 0..<8 {
            parent = parent.deletingLastPathComponent()
            if FileManager.default.fileExists(atPath: parent.appendingPathComponent("verantyx-browser").path) {
                return parent.path
            }
            if FileManager.default.fileExists(atPath: parent.appendingPathComponent("VerantyxIDE/verantyx-browser").path) {
                return parent.path
            }
        }
        
        // 3. ハードコードフォールバック（開発時の確実な代替手段）
        return "/Users/motonishikoudai/verantyx-cli"
    }

    // MARK: - Launch

    func launch(visible: Bool = true) async throws {
        // .error(...) は内容問わず再起動を許可（空文字列のみ一致していたバグを修正）
        if case .launching = state { return }
        if case .ready     = state { return }
        state = .launching

        let path = binaryPath
        guard FileManager.default.fileExists(atPath: path) else {
            let msg = "Binary not found: \(path)"
            state = .error(msg)
            throw BrowserError.binaryNotFound(path)
        }

        let proc   = Process()
        let stdin  = Pipe()
        let stdout = Pipe()
        let stderr = Pipe()

        proc.executableURL     = URL(fileURLWithPath: path)
        proc.arguments         = ["--bridge"] + (visible ? ["--visible"] : [])
        proc.standardInput     = stdin
        proc.standardOutput    = stdout
        proc.standardError     = stderr
        proc.qualityOfService  = .userInitiated

        try proc.run()
        
        if visible {
            let pid = proc.processIdentifier
            Task { @MainActor in
                try? await Task.sleep(nanoseconds: 500_000_000) // 0.5s wait
                if let app = NSRunningApplication(processIdentifier: pid) {
                    app.activate(options: [.activateIgnoringOtherApps])
                }
            }
        }

        self.process   = proc
        self.stdinPipe = stdin
        self.stdoutPipe = stdout

        // ── stdout リーダータスク ──────────────────────────────────────────
        readerTask = Task.detached(priority: .high) { [weak self] in
            let handle = stdout.fileHandleForReading
            var buffer = ""
            while true {
                let data = handle.availableData
                if data.isEmpty {
                    try? await Task.sleep(nanoseconds: 10_000_000)
                    if Task.isCancelled { break }
                    continue
                }
                guard let chunk = String(data: data, encoding: .utf8) else { continue }
                buffer += chunk
                while let nl = buffer.range(of: "\n") {
                    let line = String(buffer[..<nl.lowerBound]).trimmingCharacters(in: .whitespaces)
                    buffer.removeSubrange(..<nl.upperBound)
                    guard !line.isEmpty else { continue }
                    if let resp = try? JSONDecoder().decode(BrowserResponse.self, from: Data(line.utf8)) {
                        await self?.handleResponse(resp)
                    }
                }
                if Task.isCancelled { break }
            }
        }

        // PAGE_READY を待つ（最大 6 秒）
        try await waitForReady(timeout: 6)
        state = .ready
    }

    // MARK: - Public API

    /// URL に移動して Markdown を返す（HITL_DONE 待ち）
    func fetch(_ url: String, entropy: [[Double]]? = nil, keyboardEntropy: [Double]? = nil, target: [Double]? = nil) async throws -> String {
        try await ensureRunning()
        
        // --- Activate the browser window before injecting trajectory ---
        if let pid = self.process?.processIdentifier {
            await MainActor.run {
                if let app = NSRunningApplication(processIdentifier: pid) {
                    app.activate(options: [.activateIgnoringOtherApps])
                }
            }
            // Give macOS a tiny fraction of a second to bring the window forward
            try? await Task.sleep(nanoseconds: 100_000_000)
        }
        
        let id = makeID()
        let resp: BrowserResponse = try await withCheckedThrowingContinuation { cont in
            pending[id] = PendingRequest(kind: .markdown, continuation: cont)
            try? send(BrowserCommand(cmd: "navigate", url: url, id: id, entropy: entropy, keyboard_entropy: keyboardEntropy, target: target))
            // タイムアウト: 20秒
            Task { try? await Task.sleep(nanoseconds: 20_000_000_000); self.expire(id: id) }
        }
        return resp.markdown ?? ""
    }

    /// 現在ページを Markdown で取得
    func getPage() async throws -> String {
        try await ensureRunning()
        let id = makeID()
        let resp: BrowserResponse = try await withCheckedThrowingContinuation { cont in
            pending[id] = PendingRequest(kind: .markdown, continuation: cont)
            try? send(BrowserCommand(cmd: "get_page", id: id))
            Task { try? await Task.sleep(nanoseconds: 12_000_000_000); self.expire(id: id) }
        }
        return resp.markdown ?? ""
    }

    /// JavaScript を実行して結果を返す
    func evalJS(_ script: String) async throws -> String {
        try await ensureRunning()
        let id = makeID()
        let resp: BrowserResponse = try await withCheckedThrowingContinuation { cont in
            pending[id] = PendingRequest(kind: .eval, continuation: cont)
            try? send(BrowserCommand(cmd: "eval_js", text: script, id: id))
            Task { try? await Task.sleep(nanoseconds: 12_000_000_000); self.expire(id: id) }
        }
        return resp.message ?? ""
    }

    /// テキストをキーボードエントロピー（タイピングリズム）に従って入力する
    func typeText(_ text: String, keyboardEntropy: [Double]? = nil) async throws {
        try await ensureRunning()
        
        // Activate browser window to ensure it has focus before typing
        if let pid = self.process?.processIdentifier {
            await MainActor.run {
                if let app = NSRunningApplication(processIdentifier: pid) {
                    app.activate(options: [.activateIgnoringOtherApps])
                }
            }
            try? await Task.sleep(nanoseconds: 100_000_000)
        }
        
        let id = makeID()
        let _: BrowserResponse = try await withCheckedThrowingContinuation { cont in
            pending[id] = PendingRequest(kind: .eval, continuation: cont)
            try? send(BrowserCommand(cmd: "type_text", text: text, id: id, keyboard_entropy: keyboardEntropy))
            // The rust binary might not return anything for type_text, but we send it anyway.
            // Wait, we previously modified this to fire-and-forget. Let's keep it fire-and-forget.
            pending.removeValue(forKey: id)
            cont.resume(returning: BrowserResponse(id: id, status: "ok", message: "type_started"))
        }
    }

    /// Performs a hardware-level click at the given relative (x, y) coordinates within the browser window.
    func hidClick(x: Double, y: Double) async throws {
        guard let proc = process, proc.isRunning else { throw BrowserError.notRunning }
        let pid = proc.processIdentifier

        let options = CGWindowListOption(arrayLiteral: .optionOnScreenOnly, .excludeDesktopElements)
        guard let windowList = CGWindowListCopyWindowInfo(options, kCGNullWindowID) as? [[String: Any]],
              let windowInfo = windowList.first(where: { ($0[kCGWindowOwnerPID as String] as? Int32) == pid }),
              let boundsDict = windowInfo[kCGWindowBounds as String] as? [String: Any],
              let windowX = boundsDict["X"] as? Double,
              let windowY = boundsDict["Y"] as? Double else {
            throw BrowserError.ioError("Could not find window bounds for HID click")
        }

        // Ensure browser is active
        await MainActor.run {
            if let app = NSRunningApplication(processIdentifier: pid) {
                app.activate(options: [.activateIgnoringOtherApps])
            }
        }
        try? await Task.sleep(nanoseconds: 100_000_000)

        // --- Coordinate Calibration Phase ---
        let calibStartPoint = NSEvent.mouseLocation
        let screenHeight = NSScreen.screens.first?.frame.height ?? 0
        let currentPoint = CGPoint(x: calibStartPoint.x, y: screenHeight - calibStartPoint.y)

        let calibDelta: Double = 50.0
        let calibTest = CGPoint(x: currentPoint.x + calibDelta, y: currentPoint.y + calibDelta)
        
        if let moveEvent = CGEvent(mouseEventSource: nil, mouseType: .mouseMoved, mouseCursorPosition: calibTest, mouseButton: .left) {
            moveEvent.post(tap: .cghidEventTap)
        }
        try? await Task.sleep(nanoseconds: 30_000_000)
        
        let calibEndPoint = NSEvent.mouseLocation
        let actualPoint = CGPoint(x: calibEndPoint.x, y: screenHeight - calibEndPoint.y)
        
        let actualDx = actualPoint.x - currentPoint.x
        let actualDy = actualPoint.y - currentPoint.y
        
        var calibScaleX: Double = 1.0
        var calibScaleY: Double = 1.0
        
        if abs(actualDx) > 1.0 && abs(actualDy) > 1.0 {
            calibScaleX = calibDelta / actualDx
            calibScaleY = calibDelta / actualDy
        }
        
        // Return cursor to start
        if let retEvent = CGEvent(mouseEventSource: nil, mouseType: .mouseMoved, mouseCursorPosition: currentPoint, mouseButton: .left) {
            retEvent.post(tap: .cghidEventTap)
        }
        try? await Task.sleep(nanoseconds: 20_000_000)

        // Apply Calibration
        let uncalibratedScreenX = windowX + x
        let uncalibratedScreenY = windowY + y
        let targetPoint = CGPoint(
            x: currentPoint.x + (uncalibratedScreenX - currentPoint.x) * calibScaleX,
            y: currentPoint.y + (uncalibratedScreenY - currentPoint.y) * calibScaleY
        )

        // Dispatch HID events
        guard let mouseDown = CGEvent(mouseEventSource: nil, mouseType: .leftMouseDown, mouseCursorPosition: targetPoint, mouseButton: .left),
              let mouseUp = CGEvent(mouseEventSource: nil, mouseType: .leftMouseUp, mouseCursorPosition: targetPoint, mouseButton: .left) else {
            throw BrowserError.ioError("Failed to create CGEvent")
        }

        mouseDown.post(tap: .cghidEventTap)
        try? await Task.sleep(nanoseconds: 50_000_000) // 50ms click hold
        mouseUp.post(tap: .cghidEventTap)
    }

    /// ヘルスチェック（プロセスが生きているか確認）
    func ping() async -> Bool {
        guard let proc = process, proc.isRunning else { return false }
        let id = makeID()
        do {
            return try await withCheckedThrowingContinuation { cont in
                pending[id] = PendingRequest(kind: .pong, continuation: cont)
                try? send(BrowserCommand(cmd: "ping", id: id))
                Task {
                    try? await Task.sleep(nanoseconds: 3_000_000_000)
                    self.expire(id: id)
                }
            }.status == "pong"
        } catch {
            return false
        }
    }

    /// プロセスを終了する
    func quit() {
        try? send(BrowserCommand(cmd: "quit"))
        process?.terminate()
        process    = nil
        readerTask?.cancel()
        readerTask = nil
        state      = .idle
        // 残 pending をすべてキャンセル
        for (_, req) in pending {
            req.continuation.resume(throwing: BrowserError.notRunning)
        }
        pending.removeAll()
    }

    // MARK: - Private: response routing

    private func handleResponse(_ resp: BrowserResponse) {
        // PAGE_READY → readyCont を優先して resume
        if resp.status == "ok", resp.message == "ready" || resp.message == "ready_timeout" {
            if let cont = readyCont {
                readyCont = nil
                cont.resume(returning: ())
                return
            }
        }

        guard let id = resp.id, let req = pending[id] else { return }

        switch req.kind {
        case .markdown:
            // "navigating" は中間状態 — hitl_done / ok (with markdown) が最終
            if resp.status == "navigating" { return }
            pending.removeValue(forKey: id)
            req.continuation.resume(returning: resp)
        case .eval:
            guard resp.status == "eval_ok" || resp.status == "eval_err" else { return }
            pending.removeValue(forKey: id)
            if resp.status == "eval_err" {
                req.continuation.resume(throwing: BrowserError.jsError(resp.message ?? "unknown"))
            } else {
                req.continuation.resume(returning: resp)
            }
        case .pong:
            guard resp.status == "pong" else { return }
            pending.removeValue(forKey: id)
            req.continuation.resume(returning: resp)
        }
    }

    // MARK: - Private: helpers

    private func makeID() -> UInt64 {
        let id = nextID
        nextID &+= 1
        return id
    }

    private func send(_ cmd: BrowserCommand) throws {
        guard let pipe = stdinPipe else { throw BrowserError.notRunning }
        let data = try JSONEncoder().encode(cmd)
        var line = data
        line.append(0x0A)  // newline delimiter

        // SIGPIPE-safe write: fileHandleForWriting.write() は SIGPIPE を
        // 内部で握り潰さず、かつ SIG_IGN 無効時にクラッシュする。
        // FileHandle の fileDescriptor に直接 write(2) することで
        // EPIPE エラーをキャッチして BrowserError.notRunning を投げる。
        let fd = pipe.fileHandleForWriting.fileDescriptor
        var remaining = line.count
        var offset = 0
        
        while remaining > 0 {
            let result = line.withUnsafeBytes { ptr -> Int in
                Darwin.write(fd, ptr.baseAddress! + offset, remaining)
            }
            if result < 0 {
                let code = errno
                throw code == EPIPE
                    ? BrowserError.notRunning                          // プロセスが既に死んでいる
                    : BrowserError.ioError("write(2) errno=\(code)")  // その他 I/O エラー
            }
            remaining -= result
            offset += result
        }
    }

    private func expire(id: UInt64) {
        guard let req = pending[id] else { return }
        pending.removeValue(forKey: id)
        req.continuation.resume(throwing: BrowserError.timeout)
        self.quit() // Forcefully terminate the stuck process so it restarts on next fetch
    }

    private func waitForReady(timeout: Double) async throws {
        // Void Continuation で PAGE_READY を待つ（型安全）
        try await withCheckedThrowingContinuation { (cont: CheckedContinuation<Void, Error>) in
            self.readyCont = cont
            Task {
                try? await Task.sleep(nanoseconds: UInt64(timeout * 1_000_000_000))
                if self.readyCont != nil {
                    self.readyCont = nil
                    cont.resume(returning: ())
                }
            }
        }
    }

    func ensureRunning() async throws {
        if let proc = process, proc.isRunning { return }
        state = .idle
        try await launch()
    }

    /// Captures a screenshot of the verantyx-browser window.
    func takeScreenshot() async throws -> String {
        guard let proc = process, proc.isRunning else { throw BrowserError.notRunning }
        let pid = proc.processIdentifier

        // Get window list
        let options = CGWindowListOption(arrayLiteral: .optionOnScreenOnly, .excludeDesktopElements)
        guard let windowList = CGWindowListCopyWindowInfo(options, kCGNullWindowID) as? [[String: Any]] else {
            throw BrowserError.ioError("Failed to get window list")
        }

        // Find window for this process
        guard let windowInfo = windowList.first(where: { ($0[kCGWindowOwnerPID as String] as? Int32) == pid }),
              let windowID = windowInfo[kCGWindowNumber as String] as? CGWindowID else {
            throw BrowserError.ioError("Could not find window for PID \(pid)")
        }

        // Create image
        guard let image = CGWindowListCreateImage(.null, .optionIncludingWindow, windowID, .boundsIgnoreFraming) else {
            throw BrowserError.ioError("Failed to create image from window")
        }

        let bitmapRep = NSBitmapImageRep(cgImage: image)
        guard let jpegData = bitmapRep.representation(using: .jpeg, properties: [.compressionFactor: 0.8]) else {
            throw BrowserError.ioError("Failed to encode image to JPEG")
        }

        return jpegData.base64EncodedString()
    }
}

// MARK: - BrowserError

enum BrowserError: Error, LocalizedError {
    case binaryNotFound(String)
    case notRunning
    case timeout
    case jsError(String)
    case ioError(String)           // write(2) / pipe I/O failure

    var errorDescription: String? {
        switch self {
        case .binaryNotFound(let p): return "verantyx-browser not found at \(p). Run: cargo build -p vx-browser"
        case .notRunning:            return "Browser not running."
        case .timeout:               return "Browser operation timed out."
        case .jsError(let e):        return "JS error: \(e)"
        case .ioError(let e):        return "Browser I/O error: \(e)"
        }
    }
}

// MARK: - SafariVisionBridge

class SafariVisionBridge {
    static let shared = SafariVisionBridge()

    private let appName = "Safari"
    private var initialBounds: [String: Double]? = nil

    private func enforceSafariBounds() async throws {
        let options = CGWindowListOption(arrayLiteral: .optionOnScreenOnly, .excludeDesktopElements)
        guard let windowList = CGWindowListCopyWindowInfo(options, kCGNullWindowID) as? [[String: Any]],
              let windowInfo = windowList.first(where: { info in
                  guard (info[kCGWindowOwnerName as String] as? String) == appName else { return false }
                  guard let layer = info[kCGWindowLayer as String] as? Int, layer == 0 else { return false }
                  guard let bounds = info[kCGWindowBounds as String] as? [String: Any],
                        let height = bounds["Height"] as? Double, height > 100 else { return false }
                  return true
              }),
              let boundsDict = windowInfo[kCGWindowBounds as String] as? [String: Any] else {
            return
        }

        if initialBounds == nil {
            // First time we see it, save its initial position
            initialBounds = [
                "X": boundsDict["X"] as! Double,
                "Y": boundsDict["Y"] as! Double,
                "Width": boundsDict["Width"] as! Double,
                "Height": boundsDict["Height"] as! Double
            ]
        } else if let target = initialBounds {
            // Enforce bounds if moved
            let currentX = boundsDict["X"] as! Double
            let currentY = boundsDict["Y"] as! Double
            let currentW = boundsDict["Width"] as! Double
            let currentH = boundsDict["Height"] as! Double

            if abs(currentX - target["X"]!) > 5 || abs(currentY - target["Y"]!) > 5 ||
               abs(currentW - target["Width"]!) > 5 || abs(currentH - target["Height"]!) > 5 {
                
                let script = """
                tell application "Safari"
                    set bounds of window 1 to {\(Int(target["X"]!)), \(Int(target["Y"]!)), \(Int(target["X"]! + target["Width"]!)), \(Int(target["Y"]! + target["Height"]!))}
                end tell
                """
                try? await runAppleScript(script)
                try? await Task.sleep(nanoseconds: 300_000_000)
            }
        }
    }

    func navigate(_ url: String) async throws {
        let script = """
        tell application "Safari"
            activate
            if (count every document) = 0 then
                make new document
            end if
            set URL of document 1 to "\(url)"
        end tell
        """
        try await runAppleScript(script)
        try await Task.sleep(nanoseconds: 2_000_000_000) // Wait for load
        try await enforceSafariBounds()
    }

    func scrollDown() async throws {
        let script = """
        tell application "Safari"
            do JavaScript "window.scrollBy({top: window.innerHeight * 0.8, behavior: 'smooth'});" in current tab of front window
        end tell
        """
        try await runAppleScript(script)
    }

    func takeMultiFrameScreenshot(frameCount: Int = 4) async throws -> [String] {
        var frames: [String] = []
        for i in 0..<frameCount {
            let base64 = try await takeScreenshot()
            frames.append(base64)
            if i < frameCount - 1 {
                try await scrollDown()
                try await Task.sleep(nanoseconds: 1_000_000_000) // wait for smooth scroll to finish
            }
        }
        return frames
    }

    func takeScreenshot(enforceSafari: Bool = true) async throws -> String {
        // Preflight can lag behind a fresh grant (and is unreliable for
        // ad-hoc DMG builds). Always request when denied, then still attempt
        // capture once — only fail if the CG image is nil.
        if !ScreenCapturePermission.isGranted {
            ScreenCapturePermission.request()
        }

        if enforceSafari {
            try await enforceSafariBounds()
        }

        // Capture entire main screen instead of just Safari window
        let mainDisplay = CGMainDisplayID()
        let logicalWidth = Double(CGDisplayBounds(mainDisplay).width)
        let logicalHeight = Double(CGDisplayBounds(mainDisplay).height)
        let windowX: Double = 0.0
        let windowY: Double = 0.0

        guard let image = await DisplayCapture.mainDisplay() else {
            throw BrowserError.ioError(DisplayCapture.failureReason)
        }

        let pixelWidth = Double(image.width)
        let pixelHeight = Double(image.height)
        let scaleX = pixelWidth / logicalWidth
        let scaleY = pixelHeight / logicalHeight

        let nsImage = NSImage(cgImage: image, size: NSSize(width: pixelWidth, height: pixelHeight))
        nsImage.lockFocus()

        // --- GRID AND WATERMARKS ---
        // Draw Watermarks
        let watermarkText = "VERANTYX" as NSString
        let watermarkFont = NSFont.boldSystemFont(ofSize: 48)
        let watermarkAttributes: [NSAttributedString.Key: Any] = [
            .font: watermarkFont,
            .foregroundColor: NSColor.red.withAlphaComponent(0.15)
        ]
        for wx in stride(from: 0, to: pixelWidth, by: 400.0) {
            for wy in stride(from: 0, to: pixelHeight, by: 300.0) {
                watermarkText.draw(at: NSPoint(x: wx, y: wy), withAttributes: watermarkAttributes)
            }
        }
        
        // Draw Double Grid Lines (10x10)
        NSColor.green.withAlphaComponent(0.5).setStroke()
        let path = NSBezierPath()
        let stepX = pixelWidth / 10.0
        let stepY = pixelHeight / 10.0
        
        let labelFont = NSFont.monospacedSystemFont(ofSize: 24, weight: .bold)
        let labelAttrs: [NSAttributedString.Key: Any] = [
            .font: labelFont,
            .foregroundColor: NSColor.green.withAlphaComponent(0.8),
            .backgroundColor: NSColor.black.withAlphaComponent(0.5)
        ]
        
        for i in 1...9 {
            let vx = Double(i) * stepX
            path.move(to: NSPoint(x: vx - 2, y: 0))
            path.line(to: NSPoint(x: vx - 2, y: pixelHeight))
            path.move(to: NSPoint(x: vx + 2, y: 0))
            path.line(to: NSPoint(x: vx + 2, y: pixelHeight))
            
            let vy = Double(i) * stepY
            path.move(to: NSPoint(x: 0, y: vy - 2))
            path.line(to: NSPoint(x: pixelWidth, y: vy - 2))
            path.move(to: NSPoint(x: 0, y: vy + 2))
            path.line(to: NSPoint(x: pixelWidth, y: vy + 2))
            
            // Draw coordinate labels at intersections
            for j in 1...9 {
                let interX = Double(j) * stepX
                // logical coordinate equivalent (0-1000 normalized)
                let labelText = "[\(j*100), \((10-i)*100)]" as NSString
                labelText.draw(at: NSPoint(x: interX + 5, y: vy + 5), withAttributes: labelAttrs)
            }
        }
        path.lineWidth = 1.0
        path.stroke()

        // Mouse location logic
        let mouseLoc = NSEvent.mouseLocation
        let screenHeight = NSScreen.screens.first?.frame.height ?? 0
        let topYMouse = screenHeight - mouseLoc.y // Convert to top-left coordinate system

        // Calculate relative to the window
        let relativeX = mouseLoc.x - windowX
        let relativeY = topYMouse - windowY

        // If the mouse is inside the window
        if relativeX >= 0 && relativeX <= logicalWidth && relativeY >= 0 && relativeY <= logicalHeight {
            let pxX = relativeX * scaleX
            // In nsImage context, origin is BOTTOM-LEFT.
            let nsImageMouseY = pixelHeight - (relativeY * scaleY) // Invert Y for NSImage

            let circleRect = NSRect(x: pxX - 10, y: nsImageMouseY - 10, width: 20, height: 20)
            NSColor.red.setFill()
            let path = NSBezierPath(ovalIn: circleRect)
            path.fill()
            
            NSColor.white.setStroke()
            path.lineWidth = 2
            path.stroke()
        }

        nsImage.unlockFocus()

        guard let tiffData = nsImage.tiffRepresentation,
              let bitmapRep = NSBitmapImageRep(data: tiffData),
              let jpegData = bitmapRep.representation(using: .jpeg, properties: [.compressionFactor: 0.8]) else {
            throw BrowserError.ioError("Failed to encode image to JPEG")
        }

        return jpegData.base64EncodedString()
    }

    /// Safari's click, delegated to the one implementation that learns.
    ///
    /// This was a second, older copy of the whole click routine — its own
    /// calibration probe, its own synthetic path — and it is the copy the
    /// agent actually calls. Every improvement made to clicking (the
    /// remembered calibration, the trajectory recorded in vera-a, the
    /// human-demonstrated motion, the read-back that proves the pointer
    /// arrived) lived in DesktopVisionBridge and never ran. Keeping two
    /// implementations is how that happens, so there is now one: Safari's
    /// window is brought into bounds here, and the click itself is the
    /// shared path.
    func hidClick(x: Double, y: Double, enforceSafari: Bool = true) async throws {
        if enforceSafari {
            try await enforceSafariBounds()
        }
        try await DesktopVisionBridge.shared.hidClick(x: x, y: y)
    }

    func typeText(_ text: String) async throws {
        // OS-Level: type wherever the cursor currently is, no forced app activation
        try? await Task.sleep(nanoseconds: 100_000_000)

        let kEntropy = await MainActor.run { AppState.shared?.lastKeyboardEntropy }
        
        let source = CGEventSource(stateID: .hidSystemState)
        for (i, char) in text.enumerated() {
            let s = String(char)
            var buf = [UInt16](repeating: 0, count: s.utf16.count)
            let _ = s.utf16.map { $0 }.withUnsafeBufferPointer { ptr in
                for i in 0..<ptr.count { buf[i] = ptr[i] }
            }

            if let eventDown = CGEvent(keyboardEventSource: source, virtualKey: 0, keyDown: true) {
                eventDown.keyboardSetUnicodeString(stringLength: buf.count, unicodeString: buf)
                eventDown.post(tap: .cghidEventTap)
            }
            
            // keystroke hold delay
            let holdMs: UInt64
            if let ke = kEntropy, !ke.isEmpty {
                let e = ke[(i * 2) % ke.count]
                holdMs = UInt64(10 + e * 40)
            } else {
                holdMs = UInt64(Int.random(in: 15...35))
            }
            try? await Task.sleep(nanoseconds: holdMs * 1_000_000)
            
            if let eventUp = CGEvent(keyboardEventSource: source, virtualKey: 0, keyDown: false) {
                eventUp.keyboardSetUnicodeString(stringLength: buf.count, unicodeString: buf)
                eventUp.post(tap: .cghidEventTap)
            }
            
            // keystroke interval delay
            let intervalMs: UInt64
            if let ke = kEntropy, !ke.isEmpty {
                let e = ke[(i * 2 + 1) % ke.count]
                intervalMs = UInt64(20 + e * 130)
            } else {
                intervalMs = UInt64(Int.random(in: 30...100))
            }
            try? await Task.sleep(nanoseconds: intervalMs * 1_000_000)
        }
    }

    private func runAppleScript(_ script: String) async throws {
        return try await withCheckedThrowingContinuation { cont in
            DispatchQueue.global(qos: .userInitiated).async {
                if let appleScript = NSAppleScript(source: script) {
                    var errorInfo: NSDictionary?
                    appleScript.executeAndReturnError(&errorInfo)
                    if let err = errorInfo {
                        // Real bug found live: interpolating the raw NSDictionary
                        // dumped an unreadable blob starting with
                        // NSAppleScriptErrorRange (e.g. "37:126: ..."), and the
                        // chat log's line-length limit cut it off before the
                        // actual NSAppleScriptErrorMessage ever appeared -- so
                        // neither the user nor the model ever saw why the
                        // script failed. Extract the real message explicitly.
                        let message = (err[NSAppleScript.errorMessage] as? String)
                            ?? (err[NSAppleScript.errorBriefMessage] as? String)
                            ?? "\(err)"
                        let number = err[NSAppleScript.errorNumber] as? Int
                        let detail = number != nil ? "\(message) (code \(number!))" : message
                        cont.resume(throwing: BrowserError.ioError("AppleScript error: \(detail)"))
                    } else {
                        cont.resume(returning: ())
                    }
                } else {
                    cont.resume(throwing: BrowserError.ioError("Failed to compile AppleScript"))
                }
            }
        }
    }

    func computeVisualSimilarity(base64A: String, base64B: String) -> Float {
        guard let dataA = Data(base64Encoded: base64A),
              let dataB = Data(base64Encoded: base64B),
              let imgA = NSImage(data: dataA)?.cgImage(forProposedRect: nil, context: nil, hints: nil),
              let imgB = NSImage(data: dataB)?.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
            return 100.0
        }
        
        let requestA = VNGenerateImageFeaturePrintRequest()
        let requestB = VNGenerateImageFeaturePrintRequest()
        
        let handlerA = VNImageRequestHandler(cgImage: imgA, options: [:])
        let handlerB = VNImageRequestHandler(cgImage: imgB, options: [:])
        
        try? handlerA.perform([requestA])
        try? handlerB.perform([requestB])
        
        guard let obsA = requestA.results?.first as? VNFeaturePrintObservation,
              let obsB = requestB.results?.first as? VNFeaturePrintObservation else {
            return 100.0
        }
        
        var distance: Float = 0
        try? obsA.computeDistance(&distance, to: obsB)
        return distance
    }
}

