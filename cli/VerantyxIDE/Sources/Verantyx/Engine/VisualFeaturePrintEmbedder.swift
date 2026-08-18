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
/// This is a *different* vector space from JGEN's hidden states, with no
/// trained projection between them. The original design here kept them
/// fully separate -- recall only ever re-entering a prompt as text (see
/// `VisualMemoryStore.recallBlock`) -- specifically to avoid feeding an
/// unaligned vector into `JCrossEngine.injectAtLayer`/`injectMultiLayer`.
/// `VisualHiddenStateBridge` now does exactly that anyway, as an explicit,
/// clearly-labeled experiment (padded/truncated to `hiddenDim`, not
/// projected) requested to test whether direct hidden-state injection lets
/// JGEN understand a live screen without routing through a vision-capable
/// Ollama/escalation model. Both paths coexist: `VisualMemoryStore` for
/// ordinary text-recall memory, `VisualHiddenStateBridge` for this
/// experiment.
enum VisualFeaturePrintEmbedder {

    /// The words actually on the screen, read on-device by Vision.
    ///
    /// Measured 2026-08-18, 12 screens sharing one layout and differing
    /// only in wording, queried with a rescaled + scrolled + slightly
    /// faded render of each: the feature print alone retrieved 7/12, and
    /// the same vector re-ranked by the overlap of these strings retrieved
    /// 12/12. The vector knows two screens are *different* — it does not
    /// know *what they say*, and recall was handing the model only a
    /// label. This is that missing half.
    ///
    /// No model is loaded and nothing leaves the machine: `VNRecognizeText`
    /// is Apple's on-device recogniser. Spaces are dropped because the
    /// recogniser is inconsistent about them in Japanese
    /// (「上限は 10,000 円」→「上限は10,000円」), and comparing on content
    /// rather than on spacing is the same normalisation the document side
    /// already uses.
    static func readText(base64Image: String) -> [String] {
        guard let data = Data(base64Encoded: base64Image),
              let cg = NSImage(data: data)?.cgImage(forProposedRect: nil, context: nil, hints: nil)
        else { return [] }
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.recognitionLanguages = ["ja-JP", "en-US"]
        req.usesLanguageCorrection = true
        guard (try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])) != nil
        else { return [] }
        return (req.results ?? []).compactMap { obs -> String? in
            guard let c = obs.topCandidates(1).first else { return nil }
            // 低信頼の読みは、読めなかったことより悪い。書かれていない語を
            // 「画面にこう書いてあった」として記憶に残すことになる。
            guard c.confidence >= 0.5 else { return nil }
            let t = c.string.replacingOccurrences(of: " ", with: "")
                            .trimmingCharacters(in: .whitespacesAndNewlines)
            guard !t.isEmpty, !isSecret(t) else { return nil }
            return t
        }
    }

    /// Screen text is not curated. A recogniser pointed at a real desktop
    /// will read tokens and keys off whatever window is open, and this
    /// store is written without anyone approving each line. Anything that
    /// looks like a credential is dropped before it can reach disk —
    /// dropping a harmless line costs a little recall, keeping a secret
    /// costs something that cannot be taken back.
    static func isSecret(_ t: String) -> Bool {
        let lower = t.lowercased()
        for k in ["password", "passwd", "secret", "api key", "apikey",
                  "token", "bearer", "private key",
                  // 実測で素通しした形: 「APIキー」は英字と片仮名で綴られ、
                  // 英語の綴りだけを見ていた門に掛からなかった。
                  "apiキー", "アクセスキー", "トークン", "認証情報",
                  "パスワード", "秘密鍵"]
        where lower.contains(k) { return true }
        if t.hasPrefix("sk-") || t.hasPrefix("ghp_") || t.hasPrefix("xox") { return true }
        // 長い、区切りの無い、英数混在の連 — 文ではなく鍵の形。
        if t.count >= 24, t.allSatisfy({ $0.isLetter || $0.isNumber || $0 == "_" || $0 == "-" }),
           t.contains(where: \.isNumber), t.contains(where: \.isLetter) { return true }
        return false
    }

    /// 文字の重なりを測るための2字組。語の切れ目に依らないので、
    /// 認識ゆれ(「1歳6か月」/「1歳6ヶ月」)があっても部分的に一致する。
    static func bigrams(_ lines: [String]) -> Set<String> {
        var out = Set<String>()
        for line in lines {
            let c = Array(line)
            guard c.count >= 2 else { if c.count == 1 { out.insert(line) }; continue }
            for i in 0..<(c.count - 1) { out.insert(String(c[i ... i + 1])) }
        }
        return out
    }

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
