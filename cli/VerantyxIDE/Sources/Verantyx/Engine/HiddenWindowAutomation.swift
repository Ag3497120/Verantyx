import Foundation
import AppKit
import CoreGraphics

/// Tracks an OS-agent automation session (OPEN_APP + DESKTOP_ACT) against a
/// target app window and optionally mirrors it into the IDE.
///
/// ## Frontmost policy (default: visible front window)
/// During Act / desktop automation the target app stays **restored and
/// frontmost** so HID clicks hit the real on-screen window. Verantyx is
/// **not** activated on every snapshot/click — only when IDE-side UI truly
/// needs focus (settings, permission sheets, chat the user must see).
///
/// An earlier design minimized the target to the Dock and stole focus back
/// to Verantyx after every restore. That caused:
///   - minimize ↔ restore races that cancelled in-flight Act work
///     (`Swift.CancellationError`)
///   - clicks landing on the wrong surface / NO VISUAL CHANGE
///   - OPEN_APP never leaving Teams (etc.) usable in front
///
/// Mirror preview still works via `CGWindowListCreateImage` against the
/// visible front window (Screen Recording TCC required). The optional
/// "park minimized" path remains available via
/// `automationUsesVisibleFrontWindow = false` for experiments only.
@MainActor
final class HiddenWindowAutomation: ObservableObject {
    static let shared = HiddenWindowAutomation()

    enum MirrorCaptureStatus: Equatable {
        case idle
        case ok
        case noTarget
        case noWindow
        case permissionDenied
        case blank
        case failed
    }

    /// When `true` (default), Act keeps the target restored + frontmost and
    /// never remimimizes / re-activates Verantyx mid-automation.
    var automationUsesVisibleFrontWindow: Bool = true

    @Published private(set) var targetAppName: String?
    @Published private(set) var lastMirrorImage: String?
    @Published private(set) var lastCaptureStatus: MirrorCaptureStatus = .idle
    private(set) var targetWindowFrame: CGRect?
    private var targetPID: pid_t?
    private var targetWindowID: CGWindowID?
    private var frontmostObserver: NSObjectProtocol?
    /// Refcount of open HiddenWindowMirrorView instances. Used to avoid
    /// remimimize when the legacy park policy is on; under the visible
    /// front policy the target stays restored regardless.
    private var mirrorWatchCount = 0
    /// Serializes restore/click/capture so mirror refresh cannot cancel or
    /// interleave a remimimize under the legacy park policy.
    private var actionGate: Int = 0

    private init() {}

    private var keepTargetVisible: Bool {
        automationUsesVisibleFrontWindow || mirrorWatchCount > 0
    }

    // MARK: - Session lifecycle

    /// Activates `appName`, records its on-screen frame / window id, and
    /// (default) leaves it visible + frontmost for Act. Legacy park mode
    /// still minimizes and returns focus to Verantyx.
    @discardableResult
    func beginOffscreenSession(appName: String) async -> CGRect? {
        _ = await runOsascript("tell application \"\(appName)\" to activate")
        try? await Task.sleep(nanoseconds: 500_000_000)

        let readScript = """
        tell application "System Events"
            tell process "\(appName)"
                set p to position of window 1
                set s to size of window 1
                return (item 1 of p as text) & "," & (item 2 of p as text) & "," & (item 1 of s as text) & "," & (item 2 of s as text)
            end tell
        end tell
        """
        let result = await runOsascript(readScript)

        targetAppName = appName
        targetPID = NSWorkspace.shared.runningApplications.first(where: { $0.localizedName == appName })?.processIdentifier
        targetWindowFrame = parseFrame(from: result)
            ?? CGRect(origin: .zero, size: CGSize(width: 1280, height: 800))
        targetWindowID = findWindowID(ownerName: appName)

        if automationUsesVisibleFrontWindow {
            // Leave the target frontmost and usable. Do not steal focus back
            // to Verantyx and do not install a focus-stealing guard.
            await setMinimized(false, appName: appName)
            stopGuardingFrontmost()
            await activateTargetApp()
        } else {
            if mirrorWatchCount == 0 {
                await setMinimized(true, appName: appName)
            }
            NSApp.activate(ignoringOtherApps: true)
            startGuardingFrontmost()
        }
        VisualKeyframePump.shared.reconcile()
        return targetWindowFrame
    }

    /// Clears session state. Under visible-front policy the target window
    /// is left as the user sees it (already restored). Legacy park mode
    /// restores from the Dock first.
    func endOffscreenSession() async {
        if let appName = targetAppName, !automationUsesVisibleFrontWindow {
            await setMinimized(false, appName: appName)
        }
        stopGuardingFrontmost()
        targetAppName = nil
        targetPID = nil
        targetWindowFrame = nil
        targetWindowID = nil
        lastMirrorImage = nil
        lastCaptureStatus = .idle
        VisualKeyframePump.shared.reconcile()
    }

    /// Mirror views call this on appear so capture can run against a
    /// stably restored window.
    func beginMirrorWatch() async {
        mirrorWatchCount += 1
        guard mirrorWatchCount == 1, let appName = targetAppName else { return }
        await restoreForMirror(appName: appName)
    }

    func endMirrorWatch() async {
        mirrorWatchCount = max(0, mirrorWatchCount - 1)
        guard mirrorWatchCount == 0, let appName = targetAppName else { return }
        // Visible-front Act policy: never remimimize when the mirror closes —
        // that race blanked clicks and cancelled in-flight DESKTOP_ACT work.
        guard !automationUsesVisibleFrontWindow else { return }
        await setMinimized(true, appName: appName)
        NSApp.activate(ignoringOtherApps: true)
    }

    /// Called when the target app changes while a mirror view is already open.
    /// Does not bump the watch refcount.
    func ensureMirrorTargetRestored() async {
        guard mirrorWatchCount > 0, let appName = targetAppName else { return }
        await restoreForMirror(appName: appName)
    }

    private func restoreForMirror(appName: String) async {
        await setMinimized(false, appName: appName)
        try? await Task.sleep(nanoseconds: 350_000_000)
        await refreshWindowGeometry(appName: appName)
        // Do not activate Verantyx — mirror is an IDE-side preview of the
        // target; stealing focus fights Act and blanked captures.
        if automationUsesVisibleFrontWindow {
            await activateTargetApp()
        }
    }

    /// Ensures the target is restored + frontmost, runs `body`, then either
    /// leaves it visible (default Act policy) or remimimizes under legacy
    /// park mode. Never cancels in-flight work from a concurrent mirror
    /// refresh: callers share this gate.
    private func withTargetReadyForAction<T>(_ body: () async -> T) async -> T {
        guard let appName = targetAppName else { return await body() }
        actionGate += 1
        defer { actionGate = max(0, actionGate - 1) }

        let leaveVisible = keepTargetVisible
        if !leaveVisible {
            await setMinimized(false, appName: appName)
            try? await Task.sleep(nanoseconds: 350_000_000)
            await refreshWindowGeometry(appName: appName)
        } else {
            await setMinimized(false, appName: appName)
            await refreshWindowGeometry(appName: appName)
            await activateTargetApp()
            try? await Task.sleep(nanoseconds: 120_000_000)
        }
        let result = await body()
        if !leaveVisible {
            // Legacy park only — and never while another action is nested.
            if actionGate <= 1 {
                await setMinimized(true, appName: appName)
                NSApp.activate(ignoringOtherApps: true)
            }
        }
        // Visible-front: leave target frontmost; do not activate Verantyx.
        return result
    }

    private func refreshWindowGeometry(appName: String) async {
        let readScript = """
        tell application "System Events"
            tell process "\(appName)"
                set p to position of window 1
                set s to size of window 1
                return (item 1 of p as text) & "," & (item 2 of p as text) & "," & (item 1 of s as text) & "," & (item 2 of s as text)
            end tell
        end tell
        """
        let result = await runOsascript(readScript)
        if let parsed = parseFrame(from: result) {
            targetWindowFrame = parsed
        }
        targetWindowID = findWindowID(ownerName: appName)
    }

    private func setMinimized(_ minimized: Bool, appName: String) async {
        let script = """
        tell application "System Events"
            tell process "\(appName)"
                set minimized of window 1 to \(minimized ? "true" : "false")
            end tell
        end tell
        """
        _ = await runOsascript(script)
    }

    /// Bring the tracked target app (not Verantyx) to the front.
    @discardableResult
    func activateTargetApp() async -> Bool {
        guard let appName = targetAppName else { return false }
        // Prefer AppleScript activate: NSRunningApplication.activate() no
        // longer reliably steals frontmost on macOS 14+ (ignoringOtherApps
        // is a deprecated no-op).
        _ = await runOsascript("tell application \"\(appName)\" to activate")
        if let running = NSWorkspace.shared.runningApplications.first(where: {
            $0.localizedName == appName
        }) {
            running.activate()
        }
        return true
    }

    // MARK: - Frontmost guarding (legacy park mode only)

    /// Under legacy park policy, if the target activates itself (e.g. a
    /// dialog), hand focus back to Verantyx. Disabled when Act uses the
    /// visible front window — stealing focus is exactly the bug.
    private func startGuardingFrontmost() {
        stopGuardingFrontmost()
        guard !automationUsesVisibleFrontWindow else { return }
        frontmostObserver = NSWorkspace.shared.notificationCenter.addObserver(
            forName: NSWorkspace.didActivateApplicationNotification,
            object: nil, queue: .main
        ) { [weak self] note in
            guard let self else { return }
            let app = note.userInfo?[NSWorkspace.applicationUserInfoKey] as? NSRunningApplication
            let name = app?.localizedName
            Task { @MainActor [weak self] in
                guard let self,
                      !self.automationUsesVisibleFrontWindow,
                      let target = self.targetAppName,
                      name == target else { return }
                NSApp.activate(ignoringOtherApps: true)
            }
        }
    }

    private func stopGuardingFrontmost() {
        if let observer = frontmostObserver {
            NSWorkspace.shared.notificationCenter.removeObserver(observer)
            frontmostObserver = nil
        }
    }

    // MARK: - Capture

    /// Captures the target window via CGWindowID. Under visible-front
    /// policy (or while a mirror is watching) this does **not** run a
    /// minimize↔restore cycle.
    @discardableResult
    func captureWindowImage() async -> String? {
        guard targetAppName != nil else {
            lastCaptureStatus = .noTarget
            return nil
        }
        if keepTargetVisible {
            if let appName = targetAppName {
                await refreshWindowGeometry(appName: appName)
            }
            return encodeWindowJPEG()
        }
        guard targetWindowFrame != nil else {
            lastCaptureStatus = .noWindow
            return nil
        }
        return await withTargetReadyForAction { [self] in
            encodeWindowJPEG()
        }
    }

    /// 1fps pump path: capture without forcing activate/minimize.
    @discardableResult
    func captureWindowImageQuiet() async -> String? {
        guard targetAppName != nil else { return nil }
        return encodeWindowJPEG()
    }

    private func encodeWindowJPEG() -> String? {
        if !ScreenCapturePermission.isGranted {
            ScreenCapturePermission.request()
        }

        let windowID = targetWindowID ?? findWindowID(ownerName: targetAppName ?? "")
        guard let windowID else {
            lastCaptureStatus = .noWindow
            return nil
        }
        targetWindowID = windowID

        // Use CGRectNull like BrowserBridge / VideoClipManager — capturing
        // against a stale AX frame often intersects nothing and yields blank.
        guard let image = CGWindowListCreateImage(
            .null,
            .optionIncludingWindow,
            windowID,
            [.boundsIgnoreFraming]
        ) else {
            lastCaptureStatus = ScreenCapturePermission.isGranted ? .failed : .permissionDenied
            return nil
        }

        if image.width < 2 || image.height < 2 || Self.isVisuallyBlank(image) {
            lastCaptureStatus = ScreenCapturePermission.isGranted ? .blank : .permissionDenied
            return nil
        }

        let nsImage = NSImage(cgImage: image, size: NSSize(width: image.width, height: image.height))
        guard let tiff = nsImage.tiffRepresentation,
              let bitmap = NSBitmapImageRep(data: tiff),
              let jpeg = bitmap.representation(using: .jpeg, properties: [.compressionFactor: 0.8]) else {
            lastCaptureStatus = .failed
            return nil
        }
        let base64 = jpeg.base64EncodedString()
        lastMirrorImage = base64
        lastCaptureStatus = .ok
        return base64
    }

    /// Cheap luminance probe: Screen Recording denial often yields an
    /// all-black frame of the right size rather than a nil CGImage.
    private static func isVisuallyBlank(_ image: CGImage) -> Bool {
        let sampleW = min(32, image.width)
        let sampleH = min(32, image.height)
        guard sampleW > 0, sampleH > 0 else { return true }
        guard let ctx = CGContext(
            data: nil,
            width: sampleW,
            height: sampleH,
            bitsPerComponent: 8,
            bytesPerRow: sampleW * 4,
            space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
        ) else { return false }
        ctx.interpolationQuality = .low
        ctx.draw(image, in: CGRect(x: 0, y: 0, width: sampleW, height: sampleH))
        guard let data = ctx.data else { return false }
        let ptr = data.bindMemory(to: UInt8.self, capacity: sampleW * sampleH * 4)
        var sum = 0
        let count = sampleW * sampleH
        for i in 0..<count {
            let o = i * 4
            sum += Int(ptr[o]) + Int(ptr[o + 1]) + Int(ptr[o + 2])
        }
        let mean = Double(sum) / Double(count * 3)
        return mean < 2.0
    }

    // MARK: - Input

    /// Posts a click at a point relative to the target window's own
    /// bounds (0-1000 normalized), after ensuring the target is visible
    /// and frontmost under the Act policy.
    func clickInWindow(relativeX: Double, relativeY: Double) async {
        await withTargetReadyForAction {
            guard let frame = self.targetWindowFrame else { return }
            let point = CGPoint(
                x: frame.origin.x + (relativeX / 1000.0) * frame.width,
                y: frame.origin.y + (relativeY / 1000.0) * frame.height
            )
            guard let mouseDown = CGEvent(mouseEventSource: nil, mouseType: .leftMouseDown, mouseCursorPosition: point, mouseButton: .left),
                  let mouseUp = CGEvent(mouseEventSource: nil, mouseType: .leftMouseUp, mouseCursorPosition: point, mouseButton: .left) else {
                return
            }
            mouseDown.post(tap: .cghidEventTap)
            try? await Task.sleep(nanoseconds: 50_000_000)
            mouseUp.post(tap: .cghidEventTap)
        }
    }

    /// Types text directly into the target process via CGEventPostToPid
    /// while the window is restored / frontmost for Act.
    func typeInWindow(_ text: String) async {
        guard let pid = targetPID, let source = CGEventSource(stateID: .hidSystemState) else { return }
        await withTargetReadyForAction {
            Self.postUnicode(text, to: pid, source: source)
        }
    }

    /// Paste held mission payload into the currently focused control of the
    /// target window: write `text` to the general pasteboard, then send ⌘V.
    func pasteIntoTargetWindow(_ text: String) async -> String {
        guard let pid = targetPID, let source = CGEventSource(stateID: .hidSystemState) else {
            return "ERROR: no automation target — OPEN_APP first"
        }
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return "ERROR: empty paste payload" }

        let board = NSPasteboard.general
        let previous = board.string(forType: .string)
        board.clearContents()
        board.setString(trimmed, forType: .string)

        await withTargetReadyForAction {
            Self.postKey(0x09 /* V */, flags: .maskCommand, to: pid, source: source)
        }
        try? await Task.sleep(nanoseconds: 400_000_000)

        if let previous {
            board.clearContents()
            board.setString(previous, forType: .string)
        }

        let preview = PromptBudget.payloadPreview(trimmed, maxChars: 80)
        return "✓ Pasted \(trimmed.count) chars into target window (preview=\"\(preview)\")"
    }

    /// Safari/Chrome-style search: focus the address/search field (⌘L),
    /// replace contents, type `query`, press Return.
    func focusAddressBarAndSearch(_ query: String) async -> String {
        guard let pid = targetPID, let source = CGEventSource(stateID: .hidSystemState) else {
            return "ERROR: no automation target — OPEN_APP first"
        }
        let trimmed = PromptBudget.capSearchQuery(
            query.trimmingCharacters(in: .whitespacesAndNewlines)
        )
        guard !trimmed.isEmpty else { return "ERROR: empty search query" }

        await withTargetReadyForAction {
            Self.postKey(0x25 /* L */, flags: .maskCommand, to: pid, source: source)
            try? await Task.sleep(nanoseconds: 350_000_000)
            Self.postKey(0x00 /* A */, flags: .maskCommand, to: pid, source: source)
            try? await Task.sleep(nanoseconds: 120_000_000)
            Self.postUnicode(trimmed, to: pid, source: source)
            try? await Task.sleep(nanoseconds: 200_000_000)
            Self.postKey(0x24 /* Return */, flags: [], to: pid, source: source)
        }
        try? await Task.sleep(nanoseconds: 2_500_000_000)
        return "✓ Typed into Safari search/address bar: \"\(trimmed)\" → Return"
    }

    private static func postKey(
        _ keyCode: CGKeyCode,
        flags: CGEventFlags,
        to pid: pid_t,
        source: CGEventSource
    ) {
        guard let down = CGEvent(keyboardEventSource: source, virtualKey: keyCode, keyDown: true),
              let up = CGEvent(keyboardEventSource: source, virtualKey: keyCode, keyDown: false) else { return }
        down.flags = flags
        up.flags = flags
        down.postToPid(pid)
        up.postToPid(pid)
    }

    private static func postUnicode(_ text: String, to pid: pid_t, source: CGEventSource) {
        for char in text {
            guard let scalar = char.unicodeScalars.first else { continue }
            let utf16 = Array(String(scalar).utf16)
            guard let down = CGEvent(keyboardEventSource: source, virtualKey: 0, keyDown: true),
                  let up = CGEvent(keyboardEventSource: source, virtualKey: 0, keyDown: false) else { continue }
            down.keyboardSetUnicodeString(stringLength: utf16.count, unicodeString: utf16)
            up.keyboardSetUnicodeString(stringLength: utf16.count, unicodeString: utf16)
            down.postToPid(pid)
            Thread.sleep(forTimeInterval: 0.015)
            up.postToPid(pid)
        }
    }

    /// Navigate Safari (or another AppleScript-scriptable browser) to `url`.
    /// Under visible-front policy, activates the browser so the load is usable.
    func openURLInTargetBrowser(_ url: String) async -> String {
        let app = targetAppName ?? "Safari"
        let escaped = url
            .replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "\"", with: "\\\"")
        let script = """
        tell application "\(app)"
            if (count of windows) = 0 then
                make new document with properties {URL:"\(escaped)"}
            else
                try
                    set URL of current tab of front window to "\(escaped)"
                on error
                    make new document with properties {URL:"\(escaped)"}
                end try
            end if
        end tell
        """
        let out = await runOsascript(script)
        if automationUsesVisibleFrontWindow {
            await activateTargetApp()
        }
        try? await Task.sleep(nanoseconds: 2_000_000_000)
        if out.lowercased().contains("error") {
            return "ERROR opening URL in \(app): \(out)"
        }
        return "✓ Opened URL in \(app): \(url)"
    }

    // MARK: - App version (for staleness detection on registered UI elements)

    func currentAppVersion(appName: String) async -> String? {
        if let running = NSWorkspace.shared.runningApplications.first(where: { $0.localizedName == appName }),
           let bundleURL = running.bundleURL,
           let bundle = Bundle(url: bundleURL),
           let version = bundle.infoDictionary?["CFBundleShortVersionString"] as? String {
            return version
        }
        let path = await Task.detached(priority: .userInitiated) { () -> String? in
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/usr/bin/mdfind")
            process.arguments = ["kMDItemFSName == '\(appName).app'"]
            let pipe = Pipe()
            process.standardOutput = pipe
            do { try process.run() } catch { return nil }
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            process.waitUntilExit()
            return String(data: data, encoding: .utf8)?.split(separator: "\n").first.map(String.init)
        }.value
        guard let path,
              let bundle = Bundle(path: path),
              let version = bundle.infoDictionary?["CFBundleShortVersionString"] as? String else { return nil }
        return version
    }

    // MARK: - Helpers

    private func findWindowID(ownerName: String) -> CGWindowID? {
        guard let list = CGWindowListCopyWindowInfo(.excludeDesktopElements, kCGNullWindowID) as? [[String: Any]] else {
            return nil
        }
        for entry in list {
            guard let owner = entry[kCGWindowOwnerName as String] as? String, owner == ownerName else { continue }
            if let num = entry[kCGWindowNumber as String] as? Int { return CGWindowID(num) }
        }
        return nil
    }

    private func parseFrame(from result: String) -> CGRect? {
        let nums = result.split(separator: ",").compactMap { Double($0.trimmingCharacters(in: .whitespaces)) }
        guard nums.count >= 4 else { return nil }
        return CGRect(x: nums[0], y: nums[1], width: nums[2], height: nums[3])
    }

    private func runOsascript(_ script: String) async -> String {
        // Prefer cooperative cancellation over hard CancellationError: if the
        // parent Act task is cancelled mid-osascript, return empty rather than
        // throwing through DESKTOP_ACT.
        let handle = Task.detached(priority: .userInitiated) { () -> String in
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
            process.arguments = ["-e", script]
            let pipe = Pipe()
            process.standardOutput = pipe
            process.standardError = pipe
            do { try process.run() } catch { return "" }
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            process.waitUntilExit()
            return String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        }
        // Detached Task.value is non-throwing (Failure == Never). Soft-cancel
        // so parent Act cancellation does not surface as DESKTOP_ERROR.
        if Task.isCancelled {
            handle.cancel()
            return ""
        }
        return await withTaskCancellationHandler {
            await handle.value
        } onCancel: {
            handle.cancel()
        }
    }
}
