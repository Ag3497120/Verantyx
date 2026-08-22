import Foundation
import CoreGraphics
import AppKit
import ScreenCaptureKit

// MARK: - An oracle the model cannot write
//
// The failure this exists for: with no stop sequence, the model wrote its own
// tool results — a full accessibility map of a Reddit page it never reached —
// and then dismissed the one true observation it had ("the page did NOT
// change") as a system error, because its invention was more coherent.
//
// Stop sequences and truncation stop it producing that text. Neither gives
// anyone a way to CHECK a claim. This does: a small, continuous, non-LLM
// detector that answers one question — has the screen changed since a given
// moment — from pixels, in a process the model has no access to.
//
// Deliberately not a vision model. A multimodal read of the screen is another
// judgement that can be wrong or talked into agreement; the point here is a
// measurement that cannot be. It has no vocabulary, no notion of Reddit or
// Safari, and cannot be persuaded that a page loaded. It reports a number.
//
// Cheap by construction: one display capture downsampled to a 32×32 luminance
// grid, a few times a second. That is 1024 bytes per frame and a subtraction.
@MainActor
final class ScreenChangeMonitor: ObservableObject {

    static let shared = ScreenChangeMonitor()

    /// A moment the screen visibly changed, and by how much (0…1).
    struct Change {
        let at: Date
        let magnitude: Double
    }

    @Published private(set) var running = false
    @Published private(set) var lastChange: Date?
    @Published private(set) var lastMagnitude: Double = 0

    /// Whether capture is actually producing frames.
    ///
    /// This is the distinction the whole feature turns on. "The screen did not
    /// change" and "I cannot see the screen" are different findings, and
    /// conflating them is worse than having no detector: a blind monitor
    /// reports stillness forever and would contradict navigation that really
    /// happened, teaching the model to distrust the one honest signal it has.
    /// Same rule as vera-a's ANSWER versus UNKNOWN_NO_EVIDENCE.
    @Published private(set) var canSee = false
    @Published private(set) var blindReason: String?

    /// Below this, the difference is noise: a caret blinking, a clock digit,
    /// antialiasing. Calibrated to be well under a page navigation and well
    /// over a cursor moving across a static background.
    static let changeThreshold = 0.012

    private var timer: Timer?
    private var previous: [Double]?
    private var history: [Change] = []
    private let side = 32

    // MARK: Lifecycle

    func start() {
        guard !running else { return }
        guard ScreenCapturePermission.isGranted else {
            canSee = false
            blindReason = "画面収録が許可されていません"
            return
        }
        running = true
        previous = nil
        timer = Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated { self?.sample() }
        }
    }

    func stop() {
        timer?.invalidate()
        timer = nil
        running = false
        previous = nil
    }

    // MARK: The question worth asking

    /// Has the screen changed since `moment`? The whole point of the class.
    func changed(since moment: Date) -> Bool {
        history.contains { $0.at > moment && $0.magnitude >= Self.changeThreshold }
    }

    /// How long the screen has been still. A run that believes it is
    /// navigating while this keeps growing is a run describing a fiction.
    var stillFor: TimeInterval {
        guard let last = lastChange else { return .infinity }
        return Date().timeIntervalSince(last)
    }

    /// A sentence for the turn, when the model's claim and the pixels differ.
    /// Returns nil when there is nothing to contradict.
    func contradictionNote(claimedNavigation: Bool, since moment: Date) -> String? {
        // Never contradict on an absence of evidence. Without working capture
        // the detector knows nothing, and silence is the only honest output.
        guard running, canSee, claimedNavigation, !changed(since: moment) else { return nil }
        return """
        ⚠️ 画面は変化していません（\(String(format: "%.1f", stillFor))秒間静止）。
        遷移や操作が成功したという記述は、実際の画面と一致していません。
        次は必ず [DESKTOP_SNAPSHOT] で現在の状態を取得してから続けてください。
        """
    }

    // MARK: Sampling

    private func sample() {
        Task { @MainActor in
            guard let image = await DisplayCapture.mainDisplay() else {
                if canSee || blindReason == nil {
                    canSee = false
                    blindReason = DisplayCapture.failureReason
                }
                return
            }
            if !canSee { canSee = true; blindReason = nil }
            compare(image)
        }
    }

    private func compare(_ image: CGImage) {
        guard let grid = captureLuminanceGrid(image) else { return }
        defer { previous = grid }
        guard let prev = previous, prev.count == grid.count else { return }

        // Mean absolute difference over the grid. Not a perceptual hash: a
        // hash answers "is this the same image", and the question here is
        // "how much moved", which survives compression and small shifts
        // better and needs no bit-twiddling to interpret.
        var total = 0.0
        for i in 0..<grid.count { total += abs(grid[i] - prev[i]) }
        let magnitude = total / Double(grid.count)

        lastMagnitude = magnitude
        guard magnitude >= Self.changeThreshold else { return }
        let change = Change(at: Date(), magnitude: magnitude)
        lastChange = change.at
        history.append(change)
        // A couple of minutes is all any verification asks about.
        if history.count > 240 { history.removeFirst(history.count - 240) }
    }

    /// One display, downsampled to `side`×`side` normalized luminance.
    ///
    /// CGDisplayCreateImage is obsoleted as of macOS 15 and this app only
    /// compiles it because it targets 14.0 — on a newer system it returns
    /// nothing. CGWindowListCreateImage is deprecated but still functioning,
    /// and is what the rest of this codebase already captures with.
    private func captureLuminanceGrid(_ full: CGImage) -> [Double]? {

        let n = side
        var pixels = [UInt8](repeating: 0, count: n * n)
        guard let ctx = CGContext(data: &pixels, width: n, height: n,
                                  bitsPerComponent: 8, bytesPerRow: n,
                                  space: CGColorSpaceCreateDeviceGray(),
                                  bitmapInfo: CGImageAlphaInfo.none.rawValue)
        else { return nil }
        ctx.interpolationQuality = .low          // averaging is the point
        ctx.draw(full, in: CGRect(x: 0, y: 0, width: n, height: n))
        return pixels.map { Double($0) / 255.0 }
    }
}

// MARK: - Capturing the display, on an OS that removed the old way
//
// Both CoreGraphics capture APIs carry SCREEN_CAPTURE_OBSOLETE(10.5, 14.0,
// 15.0): deprecated in macOS 14, GONE in 15. This app targets 14.0, so they
// still COMPILE and return nothing at runtime on anything newer — and three
// call sites reported that as "screen capture permission", which is the wrong
// diagnosis and sends the user to a settings pane that was already correct.
//
// The first attempt at this swapped CGDisplayCreateImage for
// CGWindowListCreateImage. That was no fix: they are obsoleted by the same
// macro on the same version. ScreenCaptureKit is the only path that works,
// and SCScreenshotManager is available from macOS 14.0 — exactly this app's
// deployment target, so there is no version fork to maintain.
//
// One helper, so the next time this moves there is one place to change.
enum DisplayCapture {

    /// The whole main display. Async because ScreenCaptureKit is.
    static func mainDisplay() async -> CGImage? {
        guard #available(macOS 14.0, *) else { return nil }
        do {
            // excludingDesktopWindows: false keeps the wallpaper, so a
            // luminance diff still sees a window opening over an empty desktop.
            let content = try await SCShareableContent.excludingDesktopWindows(
                false, onScreenWindowsOnly: true)
            guard let display = content.displays.first else { return nil }

            let filter = SCContentFilter(display: display, excludingWindows: [])
            let config = SCStreamConfiguration()
            config.width = display.width
            config.height = display.height
            config.captureResolution = .best
            config.showsCursor = true

            return try await SCScreenshotManager.captureImage(
                contentFilter: filter, configuration: config)
        } catch {
            lastError = error.localizedDescription
            return nil
        }
    }

    nonisolated(unsafe) private static var lastError: String?

    /// Why a capture came back empty. Permission is the usual cause but not
    /// the only one, and reporting it as the only one is how a working
    /// permission gets toggled pointlessly.
    static var failureReason: String {
        if !ScreenCapturePermission.isGranted { return ScreenCapturePermission.shortError }
        if let e = lastError { return "画面をキャプチャできませんでした: \(e)" }
        return "画面をキャプチャできませんでした（権限は許可済み）"
    }
}
