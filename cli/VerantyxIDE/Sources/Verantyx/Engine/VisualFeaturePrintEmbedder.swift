import Foundation
import AppKit
import Vision

/// Turns a screenshot into a fixed-length float vector using Apple's
/// on-device Vision framework, so that "what a screen looked like" can be
/// stored and recalled through the same fp16-vector + JSONL-sidecar
/// mechanism `EternalMemoryStore` already uses for text -- without JGEN
/// ever needing to understand images.
///
/// `SafariVisionBridge.computeVisualSimilarity` (`Engine/BrowserBridge.swift:
/// 970-995`) already runs `VNGenerateImageFeaturePrintRequest` on exactly
/// this kind of base64 screenshot, but only calls `.computeDistance` on the
/// resulting `VNFeaturePrintObservation` and discards the vector itself.
/// This type does the one additional step: decode `.data` into `[Float]` so
/// it can be persisted, not just compared in the moment.
///
/// This is deliberately a *different* vector space from JGEN's hidden
/// states -- it must never be fed into `JCrossEngine.injectAtLayer`/
/// `encodeSoft`. Recall only ever re-enters a prompt as text (see
/// `VisualMemoryStore.recallBlock`).
enum VisualFeaturePrintEmbedder {

    /// Runs `VNGenerateImageFeaturePrintRequest` on a base64 JPEG/PNG (the
    /// same shape `HiddenWindowAutomation.captureWindowImage()` returns) and
    /// returns the observation's raw feature vector.
    static func embed(base64Image: String) -> [Float]? {
        guard let data = Data(base64Encoded: base64Image),
              let cgImage = NSImage(data: data)?.cgImage(forProposedRect: nil, context: nil, hints: nil)
        else { return nil }

        let request = VNGenerateImageFeaturePrintRequest()
        let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
        do {
            try handler.perform([request])
        } catch {
            return nil
        }
        guard let observation = request.results?.first as? VNFeaturePrintObservation else {
            return nil
        }
        return decode(observation)
    }

    /// Decodes `.data` according to `.elementType`/`.elementCount` --
    /// `VNFeaturePrintObservation` never exposes its vector as `[Float]`
    /// directly, only as an opaque `Data` blob plus a type/count descriptor.
    ///
    /// `.elementCount` is read at runtime rather than assumed: it is not
    /// documented to be a fixed constant across macOS versions, and this
    /// codebase has never decoded it before this file existed, so there is
    /// no prior value to anchor to. `VisualMemoryStore` pads/truncates
    /// whatever length comes back to its own fixed storage `dim`, the same
    /// way `EternalMemoryStore.fitVec` already handles JGEN vectors that
    /// don't match its `dim` exactly.
    private static func decode(_ observation: VNFeaturePrintObservation) -> [Float]? {
        let count = observation.elementCount
        guard count > 0 else { return nil }
        let data = observation.data

        switch observation.elementType {
        case .float:
            guard data.count >= count * MemoryLayout<Float>.size else { return nil }
            return data.withUnsafeBytes { raw -> [Float] in
                Array(raw.bindMemory(to: Float.self).prefix(count))
            }
        case .double:
            guard data.count >= count * MemoryLayout<Double>.size else { return nil }
            return data.withUnsafeBytes { raw -> [Float] in
                raw.bindMemory(to: Double.self).prefix(count).map { Float($0) }
            }
        default:
            // Unknown/unsupported element type (e.g. a future revision)
            // -- fail closed rather than reinterpret bytes incorrectly.
            return nil
        }
    }
}
