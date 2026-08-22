import AppKit

let width = 400.0
let height = 300.0
let nsImage = NSImage(size: NSSize(width: width, height: height))
nsImage.lockFocus()
NSColor.blue.setFill()
NSRect(x: 0, y: 0, width: width, height: height).fill()
nsImage.unlockFocus()

// Now draw overlay
nsImage.lockFocus()
NSColor.red.setFill()
NSBezierPath(ovalIn: NSRect(x: 190, y: 140, width: 20, height: 20)).fill()
nsImage.unlockFocus()

if let tiff = nsImage.tiffRepresentation {
    print("Success, bytes: \(tiff.count)")
} else {
    print("Fail")
}
