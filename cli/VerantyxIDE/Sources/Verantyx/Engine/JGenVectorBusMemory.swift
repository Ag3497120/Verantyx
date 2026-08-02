import Foundation
import CoreGraphics

/// Shared **JGEN-space** memory bus for the jgen-vector-bus architecture.
///
/// Vision / AX / desktop tools are adapters: they produce text (or an
/// experimental unaligned Vision feature-print). Everything that must
/// survive into council / speak / act is carved into JGEN hidden-state
/// space via `EternalMemoryStore` + `UITestVectorTrace` — never by handing
/// the turn to another LLM.
enum JGenVectorBusMemory {

    /// Session id used when the caller has no chat session yet (Vector Lab,
    /// one-shot tool harness). Stable per process so traces accumulate.
    static let fallbackSessionId = "jgen-vector-bus"

    /// Dual-write a UI/AX observation into eternal JGEN vectors (+ optional
    /// step into the UI test vector trace). Safe no-op when JGEN is unloaded.
    static func stampObservation(
        label: String,
        detail: String,
        sessionId: String?,
        stepIndex: Int?,
        actionLabel: String?,
        changedRegion: CGRect?,
        concepts: [String] = ["ui-observe", "bug-repro"]
    ) async {
        guard await JCrossChatManager.shared.isLoaded else { return }

        let clipped = String(detail.prefix(1200))
        let stamp = "UI observe: \(label)\n\(clipped)"
        try? await EternalMemoryStore.shared.add(text: stamp, concepts: concepts)

        if let actionLabel {
            let sid: String
            if let sessionId {
                let trimmed = sessionId.trimmingCharacters(in: .whitespacesAndNewlines)
                sid = trimmed.isEmpty ? fallbackSessionId : trimmed
            } else {
                sid = fallbackSessionId
            }
            let step: Int
            if let stepIndex {
                step = stepIndex
            } else {
                let moments = await UITestVectorTrace.shared.trace(sessionId: sid)
                step = moments.count + 1
            }
            try? await UITestVectorTrace.shared.recordMoment(
                sessionId: sid,
                stepIndex: step,
                actionLabel: actionLabel,
                changedRegion: changedRegion
            )
        }
    }

    /// One multimodal UI step when JGEN is loaded: carve text into JGEN
    /// eternal space + UI-trace (aligned), while Vision feature-prints stay
    /// in `VisualMemoryStore` (separate dim). Call alongside Milestone S
    /// GapGraph writes — those remain model-independent.
    static func stampMultimodalUIStep(
        label: String,
        sessionId: String,
        stepIndex: Int,
        changedRegion: CGRect?,
        nearbyElements: [String] = []
    ) async {
        guard await JCrossChatManager.shared.isLoaded else { return }
        var detailParts: [String] = [
            "step=\(stepIndex)",
            "changed=\(changedRegion != nil)",
        ]
        if let r = changedRegion {
            detailParts.append(String(format: "region=(%.0f,%.0f,%.0fx%.0f)",
                                      r.origin.x, r.origin.y, r.width, r.height))
        }
        if !nearbyElements.isEmpty {
            detailParts.append("nearby: " + nearbyElements.prefix(12).joined(separator: ", "))
        }
        await stampObservation(
            label: label,
            detail: detailParts.joined(separator: "; "),
            sessionId: sessionId,
            stepIndex: stepIndex,
            actionLabel: label,
            changedRegion: changedRegion,
            concepts: ["ui-observe", "bug-repro", "multimodal-ui", "jgen-space"]
        )
    }

    /// Status for Growth Console / CapabilityRegistry — counts only, no vectors.
    static func multimodalStatus() async -> [String: Any] {
        let jgenLoaded = await JCrossChatManager.shared.isLoaded
        let model = await JCrossChatManager.shared.loadedModelName ?? ""
        let visualOn = await MainActor.run { CouncilSettingsStore.shared.useVisualMemory }
        let visualCount = await VisualMemoryStore.shared.nodeCount()
        let sid = await MainActor.run { AppState.shared?.vxChatSessionId } ?? fallbackSessionId
        let traceCount = await UITestVectorTrace.shared.trace(sessionId: sid).count
        return [
            "ok": true,
            "jgen_loaded": jgenLoaded,
            "jgen_model": model,
            "visual_memory_enabled": visualOn,
            "visual_memory_nodes": visualCount,
            "ui_trace_moments": traceCount,
            "keyframe_eye": await VisualKeyframePump.shared.statusMap(),
            "paths": [
                "aligned": "AX/text → encodeText → inject / EternalMemoryStore",
                "vision_store": "VNFeaturePrint → VisualMemoryStore (text recall to prompt)",
                "vision_inject": "VisualHiddenStateBridge (experimental, unaligned)",
                "gap": "record_ui_transition → GapGraph (model-independent)",
                "keyframe_eye": "1fps Vera-a-V ring (opt-in; agent+HiddenWindow only)",
            ],
        ]
    }

    /// Assemble recall blocks for L1/L2: eternal (JGEN) + recent visual
    /// **text labels** + recent UI-trace moments. Never injects Vision dims.
    static func recallBundle(
        for query: String,
        sessionId: String?,
        useEternal: Bool,
        k: Int = 3
    ) async -> String {
        var parts: [String] = []
        if useEternal {
            let eternal = await EternalMemoryStore.shared.recallBlock(for: query, k: k)
            if !eternal.isEmpty { parts.append(eternal) }
        }
        let visual = await VisualMemoryStore.shared.recallRecentLabelsBlock(k: k)
        if !visual.isEmpty { parts.append(visual) }

        let sid = (sessionId?.trimmingCharacters(in: .whitespacesAndNewlines)).flatMap {
            $0.isEmpty ? nil : $0
        } ?? fallbackSessionId
        let trace = await UITestVectorTrace.shared.recallRecentBlock(sessionId: sid, k: 8)
        if !trace.isEmpty { parts.append(trace) }

        return parts.joined(separator: "\n")
    }

    /// Preferred “current screen” path for jgen-only: AX semantic map →
    /// JGEN `encodeText` → mid-layer inject (aligned spaces). Returns a
    /// short human-readable reflection, or nil on failure.
    static func reflectCurrentScreenAligned(
        axSemanticXML: String,
        prompt: String = "What UI is on screen and which controls matter for the user's task?"
    ) async -> String? {
        guard await JCrossChatManager.shared.isLoaded else { return nil }
        let clipped = String(axSemanticXML.prefix(1800))
        guard !clipped.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
        let label = "AX screen map:\n\(clipped)"
        do {
            let results = try await JCrossChatManager.shared.reflect(
                prompt: prompt,
                interventions: [(
                    layer: VisualHiddenStateBridge.defaultInjectLayer,
                    textLabel: label,
                    alpha: VisualHiddenStateBridge.defaultAlpha
                )],
                observeLayers: VisualHiddenStateBridge.defaultObserveLayers
            )
            guard !results.isEmpty else { return nil }
            let lines = results.sorted { $0.key < $1.key }.map { entry in
                "L\(entry.key): \"\(entry.value.text)\" (entropy \(String(format: "%.2f", entry.value.entropy)))"
            }
            return "[AX_HIDDEN_STATE_REFLECT — JGEN-aligned encode→inject]\n"
                + lines.joined(separator: "\n")
        } catch {
            return nil
        }
    }
}
