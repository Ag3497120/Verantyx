import Foundation
import SwiftUI
import AppKit

class DesktopVisionBridge {
    static let shared = DesktopVisionBridge()

    /// Landings at the same neighbourhood before the approach stops being
    /// rehearsed (no calibration hop, no animated path — straight there).
    /// Low on purpose: the route is re-verified on every use, so a wrong
    /// guess costs one click, while the animation costs a second of
    /// pointer theatre on every click forever.
    static let directRouteAfter = 3

    func takeScreenshot() async throws -> String {
        if !ScreenCapturePermission.isGranted {
            ScreenCapturePermission.request()
        }

        let mainDisplay = CGMainDisplayID()
        let logicalWidth = Double(CGDisplayPixelsWide(mainDisplay))
        let logicalHeight = Double(CGDisplayPixelsHigh(mainDisplay))

        guard let image = CGDisplayCreateImage(mainDisplay) else {
            throw BrowserError.ioError(ScreenCapturePermission.shortError)
        }

        let pixelWidth = Double(image.width)
        let pixelHeight = Double(image.height)
        let scaleX = pixelWidth / logicalWidth
        let scaleY = pixelHeight / logicalHeight

        let nsImage = NSImage(cgImage: image, size: NSSize(width: pixelWidth, height: pixelHeight))
        nsImage.lockFocus()

        // --- GRID AND WATERMARKS ---
        let watermarkText = "VERANTYX DESKTOP" as NSString
        let watermarkFont = NSFont.boldSystemFont(ofSize: 48)
        let watermarkAttributes: [NSAttributedString.Key: Any] = [
            .font: watermarkFont,
            .foregroundColor: NSColor.blue.withAlphaComponent(0.15)
        ]
        for wx in stride(from: 0, to: pixelWidth, by: 400.0) {
            for wy in stride(from: 0, to: pixelHeight, by: 300.0) {
                watermarkText.draw(at: NSPoint(x: wx, y: wy), withAttributes: watermarkAttributes)
            }
        }
        
        // Draw Double Grid Lines (10x10)
        NSColor.yellow.withAlphaComponent(0.5).setStroke()
        let path = NSBezierPath()
        let stepX = pixelWidth / 10.0
        let stepY = pixelHeight / 10.0
        
        let labelFont = NSFont.monospacedSystemFont(ofSize: 24, weight: .bold)
        let labelAttrs: [NSAttributedString.Key: Any] = [
            .font: labelFont,
            .foregroundColor: NSColor.yellow.withAlphaComponent(0.8),
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
                let labelText = "[\(j*100), \((10-i)*100)]" as NSString
                labelText.draw(at: NSPoint(x: interX + 5, y: vy + 5), withAttributes: labelAttrs)
            }
        }
        path.lineWidth = 1.0
        path.stroke()

        // Mouse location logic
        let mouseLoc = NSEvent.mouseLocation
        let screenHeight = NSScreen.screens.first?.frame.height ?? 0
        let topYMouse = screenHeight - mouseLoc.y

        if mouseLoc.x >= 0 && mouseLoc.x <= logicalWidth && topYMouse >= 0 && topYMouse <= logicalHeight {
            let pxX = mouseLoc.x * scaleX
            let nsImageMouseY = pixelHeight - (topYMouse * scaleY)

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

    func hidClick(x: Double, y: Double) async throws {
        let mainDisplay = CGMainDisplayID()
        let logicalWidth = Double(CGDisplayPixelsWide(mainDisplay))
        let logicalHeight = Double(CGDisplayPixelsHigh(mainDisplay))

        guard let image = CGDisplayCreateImage(mainDisplay) else {
            throw BrowserError.ioError("Failed to create image for coordinate calc")
        }
        
        let pixelWidth = Double(image.width)
        let pixelHeight = Double(image.height)
        
        let logicalClickX: Double
        let logicalClickY: Double
        
        if x <= 1000 && y <= 1000 && (pixelWidth >= 1000 || pixelHeight >= 1000) {
            logicalClickX = (x / 1000.0) * logicalWidth
            logicalClickY = (y / 1000.0) * logicalHeight
        } else {
            let scaleX = pixelWidth / logicalWidth
            let scaleY = pixelHeight / logicalHeight
            logicalClickX = x / scaleX
            logicalClickY = y / scaleY
        }

        await MainActor.run { AppState.shared?.isAgentControllingMouse = true }

        let calibStartPoint = NSEvent.mouseLocation
        let screenHeight = NSScreen.screens.first?.frame.height ?? 0
        let currentPoint = CGPoint(x: calibStartPoint.x, y: screenHeight - calibStartPoint.y)

        let app = await MainActor.run {
            NSWorkspace.shared.frontmostApplication?.localizedName ?? "unknown"
        }
        let cell = "\(Int(x / 50))_\(Int(y / 50))"
        let hint = await EternalMemoryStore.shared.mouseHint(
            app: app, cell: cell, screenW: logicalWidth, screenH: logicalHeight)
        let successes = await EternalMemoryStore.shared.mouseSuccessCount(
            app: app, cell: cell, screenW: logicalWidth, screenH: logicalHeight)

        // ── Established route: stop rehearsing it ─────────────────────
        // Every click otherwise pays for a calibration probe (a visible
        // 50pt hop and back) plus a ~30-step human-like approach — a
        // second of pointer theatre, repeated on a target this Mac has
        // already hit reliably. Once the same neighbourhood in the same
        // app on the same display has landed `directRouteAfter` times, go
        // straight there. The trace is still recorded and still verified,
        // so a route that stops working stops being trusted.
        if successes >= Self.directRouteAfter, let hint {
            let target = CGPoint(x: hint.reachedX, y: hint.reachedY)
            if let move = CGEvent(mouseEventSource: nil, mouseType: .mouseMoved,
                                  mouseCursorPosition: target, mouseButton: .left) {
                move.post(tap: .cghidEventTap)
            }
            try? await Task.sleep(nanoseconds: 30_000_000)
            let landedAt = NSEvent.mouseLocation
            let reached = CGPoint(x: landedAt.x, y: screenHeight - landedAt.y)
            let ok = hypot(reached.x - target.x, reached.y - target.y) <= 4.0

            if ok, let down = CGEvent(mouseEventSource: nil, mouseType: .leftMouseDown,
                                      mouseCursorPosition: target, mouseButton: .left),
               let up = CGEvent(mouseEventSource: nil, mouseType: .leftMouseUp,
                                mouseCursorPosition: target, mouseButton: .left) {
                down.post(tap: .cghidEventTap)
                try? await Task.sleep(nanoseconds: 50_000_000)
                up.post(tap: .cghidEventTap)
            }
            await EternalMemoryStore.shared.recordMouseTrace(
                app: app, cell: cell,
                screenW: logicalWidth, screenH: logicalHeight,
                reqX: x, reqY: y,
                reachedX: reached.x, reachedY: reached.y,
                calibX: hint.calibX, calibY: hint.calibY,
                path: "\(Int(target.x)),\(Int(target.y))", ok: ok)
            await MainActor.run {
                AppState.shared?.isAgentControllingMouse = false
                AppState.shared?.addSystemMessage(AppLanguage.shared.t(
                    ok ? "<think>\n🖱 Established route (\(successes) landings) — approach animation skipped\n</think>"
                       : "<think>\n🖱 Established route failed to land; the next click re-measures from scratch\n</think>",
                    ok ? "<think>\n🖱 確立した経路（成功\(successes)回）— 接近アニメーションを省略しました\n</think>"
                       : "<think>\n🖱 確立経路が着地せず。次回は最初から測り直します\n</think>"))
            }
            if ok { return }
            // Fall through to the full measured approach on failure.
            await MainActor.run { AppState.shared?.isAgentControllingMouse = true }
        }

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
        
        // ── Calibration, with vera-a's remembered trajectories as backup ──
        // The probe measures how far the cursor ACTUALLY moved for a known
        // synthetic delta. When the system swallows the motion (the very
        // "the agent cannot move the mouse" failure), both deltas come back
        // ~0, the guard below fails, and the scale used to stay a blind
        // 1.0 — putting the click somewhere else entirely. A calibration
        // that verifiably worked on this display is a far better default
        // than 1.0, so the memory is consulted first and the fresh probe
        // overrides it only when the probe actually measured something.
        var fallbackCalib: (Double, Double)? = hint.map { ($0.calibX, $0.calibY) }
        if fallbackCalib == nil {
            fallbackCalib = await EternalMemoryStore.shared.lastGoodCalibration(
                screenW: logicalWidth, screenH: logicalHeight)
        }

        var calibScaleX: Double = fallbackCalib?.0 ?? 1.0
        var calibScaleY: Double = fallbackCalib?.1 ?? 1.0
        var calibratedNow = false

        if abs(actualDx) > 1.0 && abs(actualDy) > 1.0 {
            calibScaleX = calibDelta / actualDx
            calibScaleY = calibDelta / actualDy
            calibratedNow = true
        } else if fallbackCalib != nil {
            await MainActor.run {
                AppState.shared?.addSystemMessage(AppLanguage.shared.t(
                    "<think>\n🖱 Calibration probe measured nothing — using a trajectory vera-a remembers working here\n</think>",
                    "<think>\n🖱 校正プローブが反応なし — vera-aが覚えている成功時の軌跡を使用します\n</think>"))
            }
        }
        
        if let retEvent = CGEvent(mouseEventSource: nil, mouseType: .mouseMoved, mouseCursorPosition: currentPoint, mouseButton: .left) {
            retEvent.post(tap: .cghidEventTap)
        }
        try? await Task.sleep(nanoseconds: 20_000_000)

        var targetPoint = CGPoint(
            x: currentPoint.x + (logicalClickX - currentPoint.x) * calibScaleX,
            y: currentPoint.y + (logicalClickY - currentPoint.y) * calibScaleY
        )
        // Strongest hint available: a click at this very neighbourhood that
        // previously LANDED. Trusted only when the probe could not measure —
        // a live measurement always beats a remembered one.
        if !calibratedNow, let hint {
            targetPoint = CGPoint(x: hint.reachedX, y: hint.reachedY)
        }
        
        let entropy = await MainActor.run { AppState.shared?.lastEntropy }
        
        var path: [CGPoint] = []
        if let ent = entropy, ent.count > 5 {
            path.append(currentPoint)
            let dx = targetPoint.x - currentPoint.x
            let dy = targetPoint.y - currentPoint.y
            
            let entStart = ent.first!
            let entEnd = ent.last!
            let entDx = entEnd.x - entStart.x
            let entDy = entEnd.y - entStart.y
            let entDist = sqrt(entDx*entDx + entDy*entDy)
            
            for i in 1..<(ent.count - 1) {
                let p = ent[i]
                let pctX = entDist > 0 ? (p.x - entStart.x) / entDist : Double(i)/Double(ent.count)
                let pctY = entDist > 0 ? (p.y - entStart.y) / entDist : Double(i)/Double(ent.count)
                
                let px = currentPoint.x + dx * pctX
                let py = currentPoint.y + dy * pctY
                path.append(CGPoint(x: px, y: py))
            }
            path.append(targetPoint)
        } else {
            path.append(currentPoint)
            // Human uncertainty, measured instead of assumed. ±50pt was a
            // guess about how far a pointer strays; vera-a has every
            // trajectory this Mac actually drove, so the stray is computed
            // from them (peak deviation ÷ distance travelled) and scaled to
            // THIS move's length. Falls back to the old constant until
            // enough trajectories exist to measure.
            let model = await EternalMemoryStore.shared.motionModel(
                screenW: logicalWidth, screenH: logicalHeight)
            let span = hypot(targetPoint.x - currentPoint.x, targetPoint.y - currentPoint.y)
            // jitterRatio is peak deviation ÷ distance, so × span puts it
            // back in points. A quadratic Bézier peaks at half its control
            // offset, hence the doubling.
            let stray = model.map { $0.jitterRatio * span * 2.0 } ?? 50.0
            let bounded = min(max(stray, 4.0), 120.0)
            let steps = model?.steps ?? 30
            let cx = (currentPoint.x + targetPoint.x) / 2.0 + Double.random(in: -bounded...bounded)
            let cy = (currentPoint.y + targetPoint.y) / 2.0 + Double.random(in: -bounded...bounded)
            for i in 1..<steps {
                let t = Double(i) / Double(steps)
                let inv = 1.0 - t
                let px = inv * inv * currentPoint.x + 2 * inv * t * cx + t * t * targetPoint.x
                let py = inv * inv * currentPoint.y + 2 * inv * t * cy + t * t * targetPoint.y
                path.append(CGPoint(x: px, y: py))
            }
            path.append(targetPoint)
        }
        
        for p in path {
            if let moveEvent = CGEvent(mouseEventSource: nil, mouseType: .mouseMoved, mouseCursorPosition: p, mouseButton: .left) {
                moveEvent.post(tap: .cghidEventTap)
            }
            try? await Task.sleep(nanoseconds: 10_000_000)
        }

        try? await Task.sleep(nanoseconds: 50_000_000)

        // ── Did the cursor actually get there? ────────────────────────
        // Read the real position back rather than assuming the posted
        // events took effect — that assumption is exactly what makes a
        // failed move look like a successful click. The verdict decides
        // whether this trajectory is worth remembering as a hint.
        let afterPoint = NSEvent.mouseLocation
        let reached = CGPoint(x: afterPoint.x, y: screenHeight - afterPoint.y)
        let drift = hypot(reached.x - targetPoint.x, reached.y - targetPoint.y)
        let landed = drift <= 4.0
        let traceString = path.suffix(24)
            .map { "\(Int($0.x)),\(Int($0.y))" }
            .joined(separator: ";")
        await EternalMemoryStore.shared.recordMouseTrace(
            app: app, cell: cell,
            screenW: logicalWidth, screenH: logicalHeight,
            reqX: x, reqY: y,
            reachedX: reached.x, reachedY: reached.y,
            calibX: calibScaleX, calibY: calibScaleY,
            path: traceString, ok: landed)
        if !landed {
            await MainActor.run {
                AppState.shared?.addSystemMessage(AppLanguage.shared.t(
                    "<think>\n🖱 Cursor stopped \(Int(drift))pt short of the target — recorded as a failed trajectory, not offered as a hint\n</think>",
                    "<think>\n🖱 カーソルが目標から\(Int(drift))pt ずれて停止 — 失敗軌跡として記録し、ヒントには使いません\n</think>"))
            }
        }
        
        guard let mouseDown = CGEvent(mouseEventSource: nil, mouseType: .leftMouseDown, mouseCursorPosition: targetPoint, mouseButton: .left),
              let mouseUp = CGEvent(mouseEventSource: nil, mouseType: .leftMouseUp, mouseCursorPosition: targetPoint, mouseButton: .left) else {
            await MainActor.run { AppState.shared?.isAgentControllingMouse = false }
            throw BrowserError.ioError("Failed to create CGEvent")
        }

        mouseDown.post(tap: .cghidEventTap)
        try? await Task.sleep(nanoseconds: 50_000_000)
        mouseUp.post(tap: .cghidEventTap)
        
        await MainActor.run { AppState.shared?.isAgentControllingMouse = false }
    }

    func typeText(_ text: String) async throws {
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

    func scroll(direction: String) async throws {
        let scrollAmount = direction == "up" ? 10 : -10
        for _ in 0..<10 {
            if let scrollEvent = CGEvent(scrollWheelEvent2Source: nil, units: .line, wheelCount: 1, wheel1: Int32(scrollAmount), wheel2: 0, wheel3: 0) {
                scrollEvent.post(tap: .cghidEventTap)
            }
            try? await Task.sleep(nanoseconds: 20_000_000)
        }
    }
}
