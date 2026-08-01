import Foundation

/// Milestone P.5 (experimental): lets JGEN "look at" the current screen via
/// direct hidden-state injection instead of the two paths that currently
/// exist for screen understanding:
///   1. `CognitiveAnchorEngine.setVisionScreenshot` -- attaches the raw
///      screenshot as a real multimodal image to whatever model is active.
///      JGEN is text-only and can't consume this at all; for any other
///      backend (Ollama, the Council's escalation model) it's slow and adds
///      real context (not vector) weight every turn.
///   2. `VisualMemoryStore.recallBlock` -- text-only recall of *past*
///      similar screens, not a read of the *current* one.
///
/// **Preferred on jgen-vector-bus:** `JGenVectorBusMemory.reflectCurrentScreenAligned`
/// (AX semantic map → `encodeText` → inject) — aligned JGEN spaces.
/// This bridge remains the **weak-signal fallback**: Vision feature-print
/// pad/truncate into residual space. Use only when AX is unavailable.
enum VisualHiddenStateBridge {

    /// Layer chosen to match `ROLE_LAYER_HINTS`-style mid-depth placement
    /// used elsewhere for structural interventions (Vera-alpha's
    /// `cognitive_interventions.py`), not tuned specifically for vision.
    static let defaultInjectLayer = 6
    static let defaultAlpha: Float = 0.15
    static let defaultObserveLayers = [4, 8, 12]

    /// Returns a short, human-readable summary of what JGEN's hidden
    /// states look like after the injection -- never a raw vector, per
    /// this codebase's "never pass JGEN's raw vectors to another process"
    /// convention (see `JGenAgentServer.swift`'s `/jgen/inject_multi_layer`
    /// doc comment). `nil` means either JGEN isn't loaded, the screenshot
    /// couldn't be embedded, or the injection itself failed -- callers
    /// should fall back to the existing text-recall or image-attach paths
    /// rather than block on this.
    static func reflectOnScreen(
        base64Image: String,
        prompt: String = "Describe what is happening on screen.",
        layer: Int = defaultInjectLayer,
        alpha: Float = defaultAlpha,
        observeLayers: [Int] = defaultObserveLayers
    ) async -> String? {
        guard await JCrossChatManager.shared.isLoaded else { return nil }
        guard let raw = VisualFeaturePrintEmbedder.embed(base64Image: base64Image) else { return nil }
        do {
            let results = try await JCrossChatManager.shared.reflectRawVector(
                prompt: prompt, layer: layer, vector: raw, alpha: alpha, observeLayers: observeLayers
            )
            guard !results.isEmpty else { return nil }
            let lines = results.sorted { $0.key < $1.key }.map { entry in
                "L\(entry.key): \"\(entry.value.text)\" (entropy \(String(format: "%.2f", entry.value.entropy)))"
            }
            return "[VISUAL_HIDDEN_STATE_REFLECT — experimental, unaligned vector space, treat as a weak signal]\n"
                + lines.joined(separator: "\n")
        } catch {
            return nil
        }
    }
}
