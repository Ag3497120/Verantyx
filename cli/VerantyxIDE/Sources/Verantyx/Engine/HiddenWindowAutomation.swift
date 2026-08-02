import Foundation
import AppKit
import CoreGraphics

/// Runs OS-agent automation (OPEN_APP + DESKTOP_ACT) against a target app's
/// window while keeping it out of the user's way and Verantyx frontmost --
/// so the agent can drive another app without visually stealing focus or
/// covering the IDE.
///
/// Earlier version of this parked the target window at a large negative
/// screen coordinate (e.g. x: -8000). That doesn't actually work: macOS's
/// window server refuses to let a window sit entirely outside every
/// connected display (a "lost window" guard), and silently clamps the
/// position back near the nearest display's edge -- which is exactly why,
/// on a real machine, the "hidden" window kept showing up pinned in a
/// corner, overlapping the IDE. There is no public API to assign a window
/// to a different macOS Space either (that requires private SkyLight/CGS
/// calls, which is a real-risk, real-scope decision to make deliberately,
/// not something to reach for silently).
///
/// Public-API-only fix: keep the target window genuinely minimized to the
/// Dock (`AXMinimized`, via System Events, same mechanism as clicking the
/// yellow traffic light) whenever nothing is actively happening. A
/// minimized window has no on-screen frame, so it's not just visually out
/// of the way, it's actually gone from the screen. For the brief instant an
/// action needs a real on-screen frame -- taking a screenshot, or posting a
/// coordinate-based click -- the window is unminimized, the action runs,
/// and it's immediately reminimized. This does mean a short flash of the
/// target app becoming visible per action; that's the accepted tradeoff for
/// staying on public APIs.
///   - Screenshots use CGWindowListCreateImage keyed to the window's ID,
///     taken right after a restore (a minimized window's cached content
///     isn't reliably live).
///   - Mouse clicks are posted via the same CGEvent HID-tap mechanism used
///     for on-screen automation, at the window's real restored coordinates
///     -- clicks need real on-screen pixels to hit-test against.
///   - Keyboard input, unlike clicks, has no coordinate -- it always goes
///     to the current frontmost app's key window. Since Verantyx is kept
///     frontmost deliberately, keystrokes are instead delivered straight
///     to the target process via CGEventPostToPid, which does not require
///     that process to be frontmost OR unminimized.
@MainActor
final class HiddenWindowAutomation: ObservableObject {
    static let shared = HiddenWindowAutomation()

    @Published private(set) var targetAppName: String?
    @Published private(set) var lastMirrorImage: String?
    private(set) var targetWindowFrame: CGRect?
    private var targetPID: pid_t?
    private var targetWindowID: CGWindowID?
    private var frontmostObserver: NSObjectProtocol?

    private init() {}

    // MARK: - Session lifecycle

    /// Activates `appName` briefly (so its window exists and System Events
    /// can address it by process name), records its real on-screen frame,
    /// then minimizes it to the Dock and hands focus back to Verantyx.
    /// Returns the window's frame (as it was before minimizing -- used to
    /// map relative click coordinates), or nil if the app/window couldn't
    /// be found.
    @discardableResult
    func beginOffscreenSession(appName: String) async -> CGRect? {
        _ = await runOsascript("tell application \"\(appName)\" to activate")
        try? await Task.sleep(nanoseconds: 500_000_000)

        // Read the frame BEFORE minimizing -- a minimized window's
        // position/size query can return stale or zeroed values.
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

        await setMinimized(true, appName: appName)
        NSApp.activate(ignoringOtherApps: true)
        startGuardingFrontmost()
        VisualKeyframePump.shared.reconcile()
        return targetWindowFrame
    }

    /// Restores the target window to normal (un-minimized) and stops
    /// guarding Verantyx's frontmost status. Call when automation finishes
    /// or the user turns the feature off.
    func endOffscreenSession() async {
        if let appName = targetAppName {
            await setMinimized(false, appName: appName)
        }
        stopGuardingFrontmost()
        targetAppName = nil
        targetPID = nil
        targetWindowFrame = nil
        targetWindowID = nil
        lastMirrorImage = nil
        VisualKeyframePump.shared.reconcile()
    }

    /// Briefly un-minimizes the target window, runs `body` (which needs a
    /// real on-screen frame -- a screenshot or a coordinate click), then
    /// re-minimizes it and hands focus straight back to Verantyx. This is
    /// the one place the target app becomes visible/frontmost at all.
    private func withRestoredWindow<T>(_ body: () async -> T) async -> T {
        guard let appName = targetAppName else { return await body() }
        await setMinimized(false, appName: appName)
        try? await Task.sleep(nanoseconds: 200_000_000)
        let result = await body()
        await setMinimized(true, appName: appName)
        NSApp.activate(ignoringOtherApps: true)
        return result
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

    // MARK: - Frontmost guarding

    /// The target window sits off-screen, so a human cannot click it into
    /// focus -- any activation of it must be programmatic (its own
    /// internal logic reacting to our simulated input, e.g. a dialog
    /// calling `activate`). Whenever that happens, hand focus straight
    /// back to Verantyx. Activation of any OTHER app (the user actually
    /// switching away) is left alone, per "until the user activates
    /// another window, the IDE stays frontmost."
    private func startGuardingFrontmost() {
        stopGuardingFrontmost()
        frontmostObserver = NSWorkspace.shared.notificationCenter.addObserver(
            forName: NSWorkspace.didActivateApplicationNotification,
            object: nil, queue: .main
        ) { [weak self] note in
            guard let self, let target = self.targetAppName,
                  let app = note.userInfo?[NSWorkspace.applicationUserInfoKey] as? NSRunningApplication,
                  app.localizedName == target else { return }
            NSApp.activate(ignoringOtherApps: true)
        }
    }

    private func stopGuardingFrontmost() {
        if let observer = frontmostObserver {
            NSWorkspace.shared.notificationCenter.removeObserver(observer)
            frontmostObserver = nil
        }
    }

    // MARK: - Capture (briefly restores the window, since a minimized
    // window's cached content isn't reliably live)

    /// Captures the target window's live content directly from the window
    /// server via its CGWindowID. Also stashes the result on
    /// `lastMirrorImage` for HiddenWindowMirrorView to display.
    @discardableResult
    func captureWindowImage() async -> String? {
        guard let frame = targetWindowFrame else { return nil }
        return await withRestoredWindow { [self] in
            encodeWindowJPEG(frame: frame)
        }
    }

    /// 1fps pump path: capture **without** un-minimizing. May return nil
    /// when the window server has no live backing store for a minimized
    /// window — callers must treat that as skip-this-tick, not an error.
    @discardableResult
    func captureWindowImageQuiet() async -> String? {
        guard let frame = targetWindowFrame else { return nil }
        return encodeWindowJPEG(frame: frame)
    }

    private func encodeWindowJPEG(frame: CGRect) -> String? {
        let windowID = targetWindowID ?? findWindowID(ownerName: targetAppName ?? "")
        guard let windowID else { return nil }
        targetWindowID = windowID

        guard let image = CGWindowListCreateImage(frame, .optionIncludingWindow, windowID, [.boundsIgnoreFraming]) else {
            return nil
        }
        let nsImage = NSImage(cgImage: image, size: NSSize(width: image.width, height: image.height))
        guard let tiff = nsImage.tiffRepresentation,
              let bitmap = NSBitmapImageRep(data: tiff),
              let jpeg = bitmap.representation(using: .jpeg, properties: [.compressionFactor: 0.8]) else {
            return nil
        }
        let base64 = jpeg.base64EncodedString()
        lastMirrorImage = base64
        return base64
    }

    // MARK: - Input (mouse needs a brief restore, keyboard goes by PID)

    /// Posts a click at a point relative to the target window's own
    /// bounds (0-1000 normalized, matching DesktopVisionBridge's on-screen
    /// convention), translated into the window's real (briefly restored)
    /// screen coordinates.
    func clickInWindow(relativeX: Double, relativeY: Double) async {
        guard let frame = targetWindowFrame else { return }
        await withRestoredWindow { [self] in
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

    /// Types text directly into the target process via CGEventPostToPid.
    /// That delivery mechanism doesn't need the process to be frontmost --
    /// but it was never verified against a genuinely *minimized* window
    /// (the old off-screen-but-not-minimized design never needed to answer
    /// that question). Rather than ship an untested assumption, this wraps
    /// the same restore/re-minimize used for clicks and screenshots, so
    /// keystrokes are always delivered while the window is in its normal,
    /// on-screen responder-chain state.
    func typeInWindow(_ text: String) async {
        guard let pid = targetPID, let source = CGEventSource(stateID: .hidSystemState) else { return }
        await withRestoredWindow {
            Self.postUnicode(text, to: pid, source: source)
        }
    }

    /// Safari/Chrome-style search: focus the address/search field (⌘L),
    /// replace contents, type `query`, press Return — real keystrokes into
    /// the target process, not a hard-coded news portal URL.
    func focusAddressBarAndSearch(_ query: String) async -> String {
        guard let pid = targetPID, let source = CGEventSource(stateID: .hidSystemState) else {
            return "ERROR: no hidden-window target — OPEN_APP first"
        }
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return "ERROR: empty search query" }

        await withRestoredWindow {
            // ⌘L — focus Smart Search / address field
            Self.postKey(0x25 /* L */, flags: .maskCommand, to: pid, source: source)
            try? await Task.sleep(nanoseconds: 350_000_000)
            // ⌘A — select existing text
            Self.postKey(0x00 /* A */, flags: .maskCommand, to: pid, source: source)
            try? await Task.sleep(nanoseconds: 120_000_000)
            Self.postUnicode(trimmed, to: pid, source: source)
            try? await Task.sleep(nanoseconds: 200_000_000)
            // Return — submit search / navigate
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

    /// Navigate Safari (or another AppleScript-scriptable browser) to `url`
    /// without forcing it frontmost — keeps the HiddenWindow park intact.
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
        try? await Task.sleep(nanoseconds: 2_000_000_000)
        if out.lowercased().contains("error") {
            return "ERROR opening URL in \(app): \(out)"
        }
        return "✓ Opened URL in \(app): \(url)"
    }

    // MARK: - App version (for staleness detection on registered UI elements)

    /// Reads `appName`'s bundle version (CFBundleShortVersionString),
    /// preferring the running instance's own bundle URL (works even if
    /// installed outside /Applications) and falling back to Spotlight's
    /// metadata index. Used to stamp registrations made via
    /// `record_verified_ui_element` and to detect, on lookup, whether the
    /// app has since been updated and the cached location may be stale.
    func currentAppVersion(appName: String) async -> String? {
        if let running = NSWorkspace.shared.runningApplications.first(where: { $0.localizedName == appName }),
           let bundleURL = running.bundleURL,
           let bundle = Bundle(url: bundleURL),
           let version = bundle.infoDictionary?["CFBundleShortVersionString"] as? String {
            return version
        }
        // Not currently running (or no accessible bundle) -- try Spotlight.
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
        // Deliberately NOT .optionOnScreenOnly -- the target window is
        // parked off-screen on purpose and must still be found.
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
        await Task.detached(priority: .userInitiated) {
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
        }.value
    }
}
