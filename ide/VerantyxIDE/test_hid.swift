import Cocoa
import CoreGraphics

func testCalib() {
    let calibStartPoint = NSEvent.mouseLocation
    let screenHeight = NSScreen.screens.first?.frame.height ?? 0
    let currentPoint = CGPoint(x: calibStartPoint.x, y: screenHeight - calibStartPoint.y)

    let calibDelta: Double = 50.0
    let calibTest = CGPoint(x: currentPoint.x + calibDelta, y: currentPoint.y + calibDelta)
    
    if let moveEvent = CGEvent(mouseEventSource: nil, mouseType: .mouseMoved, mouseCursorPosition: calibTest, mouseButton: .left) {
        moveEvent.post(tap: .cghidEventTap)
    }
    Thread.sleep(forTimeInterval: 0.1)
    
    let calibEndPoint = NSEvent.mouseLocation
    let actualPoint = CGPoint(x: calibEndPoint.x, y: screenHeight - calibEndPoint.y)
    
    let actualDx = actualPoint.x - currentPoint.x
    let actualDy = actualPoint.y - currentPoint.y
    
    var calibScaleX: Double = 1.0
    var calibScaleY: Double = 1.0
    
    if abs(actualDx) > 1.0 && abs(actualDy) > 1.0 {
        calibScaleX = calibDelta / actualDx
        calibScaleY = calibDelta / actualDy
        print("Expected (\(calibDelta), \(calibDelta)), Got (\(actualDx), \(actualDy)) -> Adjust (\(calibScaleX), \(calibScaleY))")
    } else {
        print("Move failed or was zero: (\(actualDx), \(actualDy)). Keeping scale 1.0")
    }
}

testCalib()
