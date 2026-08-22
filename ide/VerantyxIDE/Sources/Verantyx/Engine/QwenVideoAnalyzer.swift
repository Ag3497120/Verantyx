import Foundation
import CoreGraphics
import AppKit

/// Qwen3.6-27B (or similar Qwen-VL models) natively supports multi-image/video sequences.
/// This engine performs BOTH phases of the Trajectory Cloning architecture:
/// 1. Harvesting Phase: Takes a sequence of video frames of the puzzle to extract human entropy.
/// 2. Targeting Phase: Takes a screenshot of the target Web Browser and returns the target coordinate.
actor QwenVideoAnalyzer {
    static let shared = QwenVideoAnalyzer()

    /// Video (frames) -> Trajectory JSON extraction (Harvesting Phase)
    func extractEntropyFromVideo(base64Frames: [String], model: String = "qwen2.5-vl:27b") async -> [[Double]]? {
        let prompt = """
        You are a highly advanced video analysis engine.
        The user has provided a sequence of video frames showing a human solving a slider puzzle.
        Analyze the frames in order. Track the position (X, Y) of the slider piece as it moves.
        Extract the biometric mouse trajectory (human jitter and acceleration).
        Output ONLY a valid JSON array of coordinate pairs: [[x1, y1], [x2, y2], ...]
        Do not output any markdown formatting or explanations.
        """
        
        let messages: [(role: String, content: String)] = [
            (role: "user", content: prompt)
        ]
        
        print("[QwenVideoAnalyzer] Sending \(base64Frames.count) frames to \(model) for trajectory extraction...")
        
        guard let jsonString = await OllamaClient.shared.generateConversation(
            model: model,
            messages: messages,
            imagesForLastUserMessage: base64Frames,
            maxTokens: 4096,
            temperature: 0.1
        ) else {
            return nil
        }
        
        let cleaned = jsonString
            .replacingOccurrences(of: "```json", with: "")
            .replacingOccurrences(of: "```", with: "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
            
        guard let data = cleaned.data(using: .utf8),
              let array = try? JSONSerialization.jsonObject(with: data) as? [[Double]] else {
            print("[QwenVideoAnalyzer] Failed to parse Qwen output as JSON array: \(cleaned.prefix(100))...")
            return nil
        }
        
        print("[QwenVideoAnalyzer] Successfully extracted \(array.count) trajectory points from video via Qwen!")
        return array
    }
    
    /// Screenshot -> Target Coordinate extraction (Targeting Phase)
    func identifyTargetCoordinates(screenshotBase64: [String], targetDescription: String = "Search Box or Input Field", model: String = "qwen2.5-vl:27b") async -> [Double]? {
        let prompt = """
        You are a high-precision Vision model analyzing a sequence of web browser screenshots (scrolling frames).
        Find the exact coordinates (X, Y) of the '\(targetDescription)' in the LAST frame, or the most relevant frame if it's stationary.
        Output ONLY a valid JSON array representing the center coordinate: [x, y]
        Do not output any markdown formatting or explanations.
        """
        
        let messages: [(role: String, content: String)] = [
            (role: "user", content: prompt)
        ]
        
        print("[QwenVideoAnalyzer] Analyzing \(screenshotBase64.count) frames for '\(targetDescription)' using \(model)...")
        
        guard let jsonString = await OllamaClient.shared.generateConversation(
            model: model,
            messages: messages,
            imagesForLastUserMessage: screenshotBase64,
            maxTokens: 128,
            temperature: 0.1
        ) else {
            return nil
        }
        
        let cleaned = jsonString
            .replacingOccurrences(of: "```json", with: "")
            .replacingOccurrences(of: "```", with: "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
            
        guard let data = cleaned.data(using: .utf8),
              let array = try? JSONSerialization.jsonObject(with: data) as? [Double],
              array.count == 2 else {
            print("[QwenVideoAnalyzer] Failed to parse coordinate: \(cleaned)")
            return nil
        }
        
        print("[QwenVideoAnalyzer] Identified target at: \(array)")
        return array
    }
    
    /// Helper: Capture Screen to Base64 (Targeting Phase helper)
    @MainActor
    func captureMainScreen() -> String? {
        guard let windowID = NSApp.mainWindow?.windowNumber else { return nil }
        guard let cgImage = CGWindowListCreateImage(.null, .optionIncludingWindow, UInt32(windowID), .boundsIgnoreFraming) else {
            return nil
        }
        let bitmapRep = NSBitmapImageRep(cgImage: cgImage)
        guard let pngData = bitmapRep.representation(using: .png, properties: [:]) else { return nil }
        return pngData.base64EncodedString()
    }
}
