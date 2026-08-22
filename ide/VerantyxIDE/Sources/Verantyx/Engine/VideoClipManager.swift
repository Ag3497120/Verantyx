import Foundation
import CoreGraphics
import AppKit

/// Phase 2: Lightweight "Eye" that captures a short burst of frames
/// This is used to record the human puzzle interaction for Qwen-VL analysis
class VideoClipManager {
    static let shared = VideoClipManager()
    
    private var timer: Timer?
    private(set) var frames: [String] = []
    
    @MainActor
    func startRecording() {
        frames.removeAll()
        timer?.invalidate()
        // Record at ~10 FPS to save memory while preserving human jitter
        timer = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { _ in
            if let frame = self.captureMainScreen() {
                self.frames.append(frame)
            }
        }
    }
    
    @MainActor
    func stopRecording() -> [String] {
        timer?.invalidate()
        timer = nil
        let result = frames
        frames.removeAll()
        return result
    }
    
    @MainActor
    private func captureMainScreen() -> String? {
        guard let windowID = NSApp.mainWindow?.windowNumber else { return nil }
        guard let cgImage = CGWindowListCreateImage(.null, .optionIncludingWindow, UInt32(windowID), .boundsIgnoreFraming) else {
            return nil
        }
        let bitmapRep = NSBitmapImageRep(cgImage: cgImage)
        // High compression to keep payload small for LLM
        guard let jpegData = bitmapRep.representation(using: .jpeg, properties: [.compressionFactor: 0.5]) else { return nil }
        return jpegData.base64EncodedString()
    }
}
