import Foundation
import SwiftUI
import AppKit

class DesktopVisionBridge {
    static let shared = DesktopVisionBridge()

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
        
        if let retEvent = CGEvent(mouseEventSource: nil, mouseType: .mouseMoved, mouseCursorPosition: currentPoint, mouseButton: .left) {
            retEvent.post(tap: .cghidEventTap)
        }
        try? await Task.sleep(nanoseconds: 20_000_000)

        let targetPoint = CGPoint(
            x: currentPoint.x + (logicalClickX - currentPoint.x) * calibScaleX,
            y: currentPoint.y + (logicalClickY - currentPoint.y) * calibScaleY
        )
        
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
            let steps = 30
            let cx = (currentPoint.x + targetPoint.x) / 2.0 + Double.random(in: -50...50)
            let cy = (currentPoint.y + targetPoint.y) / 2.0 + Double.random(in: -50...50)
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
