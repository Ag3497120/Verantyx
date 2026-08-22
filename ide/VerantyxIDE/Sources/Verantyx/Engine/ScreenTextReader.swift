import Foundation
import CoreGraphics
import Vision
import ScreenCaptureKit
import AppKit

// MARK: - Reading a window that refuses to publish itself
//
// Accessibility is the good path: exact strings, exact frames, no guessing.
// It is also absent more often than the design assumed. A real run against
// Microsoft Teams got a window title and three unnamed buttons — no text at
// all — and `AXManualAccessibility`, the documented way to ask a Chromium app
// to publish anyway, came back -25205 (kAXErrorAttributeUnsupported) on all
// six processes: the current Teams is WebView2, not Electron, and does not
// implement the attribute. DuckDuckGo results inside Safari fail the same way,
// arriving as empty groups with no titles.
//
// So the agent, mid-task, installed PyObjC, wrote a Vision OCR script to /tmp,
// wrote a CGEvent click helper next to it, and read the screen that way. It
// worked — and it is the wrong outcome twice over: the tooling evaporates on
// reboot, and it gets rebuilt from scratch on the next run by a model that has
// to rediscover the whole problem first.
//
// ── The thing that run discovered, which is worth keeping ─────────────────
//
// Vision's `usesLanguageCorrection` makes prose better and identifiers worse.
// Measured on that screen: "IA22" came back as "1A22", "IH22" as "1|H22", and
// "ajax" as "aijax". Course codes and file names are exactly what a task like
// this turns on, so a single corrected pass silently destroys the answer —
// and the agent then accused ITSELF of fabricating the correct strings it had
// inferred, which is the expensive kind of wrong.
//
// Running both passes costs one extra Vision call over the same image and
// tells you something neither pass knows alone: where they disagree, one of
// them is wrong, and which one is predictable from the shape of the string.
enum ScreenTextReader {

    // MARK: - What comes back

    struct Line {
        let text: String
        /// Centre of the text, in global screen coordinates — ready to click,
        /// no conversion left for the caller to get wrong.
        let screenX: Double
        let screenY: Double
        let confidence: Float
        /// The two passes read this differently. Kept as a flag rather than
        /// hidden, because a disputed course code is worth a second look and
        /// silently picking one is how the last run went wrong.
        let disputed: Bool
    }

    struct Reading {
        let app: String
        let windowTitle: String
        let lines: [Line]
        let disputes: Int

        var isEmpty: Bool { lines.isEmpty }

        /// The block handed to the model. Coordinates are included on every
        /// line because the reason to read a window like this is to act on it,
        /// and a second round trip to ask "where is that" is a round trip the
        /// agent will spend guessing instead.
        var rendered: String {
            var out = ["[SCREEN_TEXT] \(app) — \(windowTitle)",
                       "画面から読み取った文字と、その中心の画面座標です。"
                       + "クリックには [DESKTOP_ACT: click x y] を使ってください。"]
            if disputes > 0 {
                out.append("⚠️ \(disputes) 行で2つの読み取りが不一致でした（⁇ 印）。"
                           + "英数字コードは補正なしの読みを採用しています。")
            }
            for l in lines {
                let mark = l.disputed ? " ⁇" : ""
                out.append("  (\(Int(l.screenX)), \(Int(l.screenY)))  \(l.text)\(mark)")
            }
            return out.joined(separator: "\n")
        }
    }

    // MARK: - Reading

    /// OCR the largest on-screen window belonging to `app`.
    static func read(app: String) async -> Reading? {
        guard #available(macOS 14.0, *) else { return nil }
        guard let (image, frame, title) = await capture(app: app) else { return nil }

        // Same image, two interpretations. Correction on is better at Japanese
        // prose; correction off is the only one that can be trusted on codes.
        async let corrected = recognise(image, correcting: true)
        async let literal   = recognise(image, correcting: false)
        let (a, b) = await (corrected, literal)
        guard !a.isEmpty || !b.isEmpty else { return nil }

        var lines: [Line] = []
        var disputes = 0

        for obs in (a.isEmpty ? b : a) {
            let partner = nearest(to: obs, in: a.isEmpty ? a : b)
            let literalText = a.isEmpty ? obs.text : (partner?.text ?? obs.text)
            let correctedText = a.isEmpty ? (partner?.text ?? obs.text) : obs.text

            let disagreed = literalText != correctedText
            if disagreed { disputes += 1 }
            let chosen = disagreed ? preferred(corrected: correctedText, literal: literalText)
                                   : correctedText

            // Vision's origin is bottom-left of the image and normalised;
            // screen space is top-left of the main display and in points.
            let box = obs.box
            lines.append(Line(
                text: chosen,
                screenX: frame.minX + box.midX * frame.width,
                screenY: frame.minY + (1 - box.midY) * frame.height,
                confidence: obs.confidence,
                disputed: disagreed))
        }

        // Reading order, not detection order: top to bottom, then left to
        // right. A list the user would read down should arrive that way.
        lines.sort { $0.screenY == $1.screenY ? $0.screenX < $1.screenX : $0.screenY < $1.screenY }

        return Reading(app: app, windowTitle: title, lines: lines, disputes: disputes)
    }

    /// Which reading to believe when the two passes differ.
    ///
    /// The literal one. Where the passes AGREE — which is most lines — that
    /// agreement is used and this never runs; a disagreement is direct
    /// evidence that correction changed something, and every instance measured
    /// so far was correction making it worse:
    ///
    ///     corrected   literal    truth
    ///     1A22        IA22       IA22
    ///     1|H22       IH22       IH22
    ///     aijax       ajax       ajax
    ///
    /// A first draft of this preferred the literal reading only for strings
    /// carrying digits, which gets the first two right and "aijax" wrong —
    /// correction had inserted a letter into an ordinary lowercase word. There
    /// is no property of "ajax" that marks it as an identifier; what marks it
    /// is that the two passes disagreed at all.
    ///
    /// Three measurements is a thin basis and this is worth revisiting with
    /// more. The asymmetry of the errors is what justifies it in the meantime:
    /// a wrong course code silently sends the agent to the wrong assignment,
    /// while slightly rougher Japanese on a disputed line costs nothing.
    static func preferred(corrected: String, literal: String) -> String {
        // Unless the literal pass returned so much less that it clearly failed
        // to read the line rather than read it differently.
        guard literal.count * 2 >= corrected.count, !literal.isEmpty else { return corrected }
        return literal
    }

    // MARK: - Vision

    private struct Observed {
        let text: String
        let box: CGRect
        let confidence: Float
    }

    private static func recognise(_ image: CGImage, correcting: Bool) async -> [Observed] {
        await withCheckedContinuation { cont in
            let request = VNRecognizeTextRequest()
            request.recognitionLevel = .accurate
            request.recognitionLanguages = ["ja-JP", "en-US"]
            request.usesLanguageCorrection = correcting
            let handler = VNImageRequestHandler(cgImage: image, options: [:])
            guard (try? handler.perform([request])) != nil else {
                cont.resume(returning: []); return
            }
            let out = (request.results ?? []).compactMap { obs -> Observed? in
                guard let top = obs.topCandidates(1).first else { return nil }
                return Observed(text: top.string, box: obs.boundingBox, confidence: top.confidence)
            }
            cont.resume(returning: out)
        }
    }

    /// The observation in `others` covering the same place on screen. Matching
    /// by position rather than by index: the two passes do not always split
    /// lines identically, and a shifted index pairs unrelated strings.
    private static func nearest(to obs: Observed, in others: [Observed]) -> Observed? {
        var best: Observed?
        var bestDistance = Double.greatestFiniteMagnitude
        for o in others {
            let d = hypot(o.box.midX - obs.box.midX, o.box.midY - obs.box.midY)
            if d < bestDistance { bestDistance = d; best = o }
        }
        // A quarter of a percent of the frame. Beyond that they are not the
        // same line and pairing them would invent a disagreement.
        return bestDistance < 0.02 ? best : nil
    }

    // MARK: - Capture
    //
    // ScreenCaptureKit, not CGWindowListCreateImage. That call carries
    // SCREEN_CAPTURE_OBSOLETE(10.5, 14.0, 15.0): it still compiles against
    // this app's 14.0 target and returns nothing at runtime on macOS 15, which
    // is why the in-app OCR appeared to do nothing while `screencapture` from
    // a shell worked fine.

    @available(macOS 14.0, *)
    private static func capture(app: String) async -> (CGImage, CGRect, String)? {
        do {
            let content = try await SCShareableContent.excludingDesktopWindows(
                true, onScreenWindowsOnly: true)

            // The LARGEST window, not the first. Popovers, panels and toolbars
            // all belong to the same app, and a real run OCR'd Safari's
            // downloads popover and reported it as the page.
            let windows = content.windows.filter {
                $0.owningApplication?.applicationName == app
                    && $0.frame.width * $0.frame.height > 200_000
            }
            guard let win = windows.max(by: {
                $0.frame.width * $0.frame.height < $1.frame.width * $1.frame.height
            }) else { return nil }

            let filter = SCContentFilter(desktopIndependentWindow: win)
            let config = SCStreamConfiguration()
            // Capture at backing scale. Retina pixels are most of the accuracy
            // on small text, and a point-sized capture throws half of it away.
            let scale = NSScreen.main?.backingScaleFactor ?? 2
            config.width = Int(win.frame.width * scale)
            config.height = Int(win.frame.height * scale)
            config.captureResolution = .best
            config.showsCursor = false

            let image = try await SCScreenshotManager.captureImage(
                contentFilter: filter, configuration: config)
            return (image, win.frame, win.title ?? "")
        } catch {
            lastError = error.localizedDescription
            return nil
        }
    }

    nonisolated(unsafe) private static var lastError: String?

    /// Why a read came back with nothing. "No text" and "no picture" need
    /// different responses, and reporting the second as the first sends the
    /// user to a permission pane that was already correct.
    static var failureReason: String {
        if !ScreenCapturePermission.isGranted { return ScreenCapturePermission.shortError }
        if let e = lastError { return "ウィンドウを撮影できませんでした: \(e)" }
        return "対象アプリの十分な大きさのウィンドウが見つかりませんでした"
    }
}
