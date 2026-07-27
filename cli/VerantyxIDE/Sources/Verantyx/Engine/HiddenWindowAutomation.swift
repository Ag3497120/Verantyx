import Foundation
import AppKit
import CoreGraphics

/// Runs OS-agent automation (OPEN_APP + DESKTOP_ACT) against a target app's
/// window while keeping it off the user's visible screen and Verantyx
/// frontmost -- so the agent can drive another app without visually
/// stealing focus or covering the IDE.
///
/// Why not NSRunningApplication.hide()? A truly hidden app can't reliably
/// receive coordinate-based mouse clicks (DesktopVisionBridge/
/// SafariVisionBridge post CGEvents at absolute screen coordinates, which
/// the window server hit-tests against whatever's actually on screen).
/// Instead the target window is relocated far off-screen -- it stays a
/// normal running app, visible in the Dock, just parked outside the
/// physical display bounds:
///   - Screenshots use CGWindowListCreateImage keyed to the window's ID,
///     which captures content directly from the window server regardless
///     of on-screen position.
///   - Mouse clicks are posted via the same CGEvent HID-tap mechanism used
///     for on-screen automation, just at the window's real (off-screen)
///     coordinates -- the window server hit-tests by screen location, so
///     this reaches the parked window whether or not it's frontmost.
///   - Keyboard input, unlike clicks, has no coordinate -- it always goes
///     to the current frontmost app's key window. Since Verantyx is kept
///     frontmost deliberately, keystrokes are instead delivered straight
///     to the target process via CGEventPostToPid, which does not require
///     that process to be frontmost.
@MainActor
final class HiddenWindowAutomation: ObservableObject {
    static let shared = HiddenWindowAutomation()

    @Published private(set) var targetAppName: String?
    @Published private(set) var lastMirrorImage: String?
    private(set) var targetWindowFrame: CGRect?
    private var targetPID: pid_t?
    private var targetWindowID: CGWindowID?
    private var frontmostObserver: NSObjectProtocol?

    private let offscreenOrigin = CGPoint(x: -8000, y: 0)

    private init() {}

    // MARK: - Session lifecycle

    /// Activates `appName` briefly (so its window exists and System Events
    /// can address it by process name), relocates its frontmost window
    /// off-screen, then immediately hands focus back to Verantyx and
    /// starts guarding it. Returns the window's real off-screen frame, or
    /// nil if the app/window couldn't be found.
    @discardableResult
    func beginOffscreenSession(appName: String) async -> CGRect? {
        _ = await runOsascript("tell application \"\(appName)\" to activate")
        try? await Task.sleep(nanoseconds: 500_000_000)

        let moveScript = """
        tell application "System Events"
            tell process "\(appName)"
                set position of window 1 to {\(Int(offscreenOrigin.x)), \(Int(offscreenOrigin.y))}
                set p to position of window 1
                set s to size of window 1
                return (item 1 of p as text) & "," & (item 2 of p as text) & "," & (item 1 of s as text) & "," & (item 2 of s as text)
            end tell
        end tell
        """
        let result = await runOsascript(moveScript)

        NSApp.activate(ignoringOtherApps: true)
        targetAppName = appName
        targetPID = NSWorkspace.shared.runningApplications.first(where: { $0.localizedName == appName })?.processIdentifier
        targetWindowFrame = parseFrame(from: result)
            ?? CGRect(origin: offscreenOrigin, size: CGSize(width: 1280, height: 800))
        targetWindowID = findWindowID(ownerName: appName)
        startGuardingFrontmost()
        return targetWindowFrame
    }

    /// Moves the target window back on-screen and stops guarding
    /// Verantyx's frontmost status. Call when automation finishes or the
    /// user turns the feature off.
    func endOffscreenSession() async {
        if let appName = targetAppName {
            let restoreScript = """
            tell application "System Events"
                tell process "\(appName)"
                    set position of window 1 to {120, 80}
                end tell
            end tell
            """
            _ = await runOsascript(restoreScript)
        }
        stopGuardingFrontmost()
        targetAppName = nil
        targetPID = nil
        targetWindowFrame = nil
        targetWindowID = nil
        lastMirrorImage = nil
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

    // MARK: - Capture (works regardless of on-screen position)

    /// Captures the target window's live content directly from the window
    /// server via its CGWindowID. Also stashes the result on
    /// `lastMirrorImage` for HiddenWindowMirrorView to display.
    @discardableResult
    func captureWindowImage() async -> String? {
        guard let frame = targetWindowFrame else { return nil }
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

    // MARK: - Input (mouse by off-screen coordinate, keyboard by PID)

    /// Posts a click at a point relative to the target window's own
    /// bounds (0-1000 normalized, matching DesktopVisionBridge's on-screen
    /// convention), translated into the window's real off-screen global
    /// coordinates.
    func clickInWindow(relativeX: Double, relativeY: Double) async {
        guard let frame = targetWindowFrame else { return }
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

    /// Types text directly into the target process via CGEventPostToPid,
    /// which — unlike clicks — does not require the process to be
    /// frontmost/key window.
    func typeInWindow(_ text: String) async {
        guard let pid = targetPID, let source = CGEventSource(stateID: .hidSystemState) else { return }
        for char in text {
            guard let scalar = char.unicodeScalars.first else { continue }
            let utf16 = Array(String(scalar).utf16)
            guard let down = CGEvent(keyboardEventSource: source, virtualKey: 0, keyDown: true),
                  let up = CGEvent(keyboardEventSource: source, virtualKey: 0, keyDown: false) else { continue }
            down.keyboardSetUnicodeString(stringLength: utf16.count, unicodeString: utf16)
            up.keyboardSetUnicodeString(stringLength: utf16.count, unicodeString: utf16)
            // Delivers directly to the target process regardless of
            // frontmost/key-window status -- unlike .post(tap:), which
            // relies on the window server's normal event routing.
            down.postToPid(pid)
            try? await Task.sleep(nanoseconds: 15_000_000)
            up.postToPid(pid)
        }
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
