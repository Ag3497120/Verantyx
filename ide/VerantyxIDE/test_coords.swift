import Cocoa

for (i, screen) in NSScreen.screens.enumerated() {
    print("Screen \(i): frame=\(screen.frame), visibleFrame=\(screen.visibleFrame)")
}
