import Foundation
import SwiftUI

/// Applies a setting on the user's behalf — or says, in a typed way, that it
/// cannot.
///
/// The obvious implementation is to write the UserDefaults key that Vera's
/// registry already knows. It is also wrong. Every one of these settings is
/// owned by an `@Published` property with a `didSet` that writes the default;
/// writing the default directly leaves the in-memory value untouched, so the
/// app keeps behaving the old way while the stored value says otherwise. The
/// setting reads as changed and is not, which is worse than never having
/// offered to change it.
///
/// So each case routes through the property that owns it. That means the
/// mapping is hand-written and incomplete by construction — and incomplete is
/// fine, as long as it is honest. Anything not listed returns
/// `.notApplicable`, and the caller offers to open the screen instead.
///
/// API keys are deliberately absent. Nothing but the person should type a
/// credential, and a helper that offered to fill one in would be promising
/// something it must not do.
@MainActor
enum SettingsApplier {

    enum Result: Equatable {
        case applied(String)              // human-readable "what changed"
        /// The app will not set this one. Carries the reason, which is shown —
        /// a silent no-op here is indistinguishable from success.
        case notApplicable(String)
        case badValue(String)
    }

    /// `key` is a settings-registry key ("model.ollama") or "mode:<group>".
    static func apply(key: String, value: String, app: AppState) -> Result {
        switch key {

        // ── Modes ────────────────────────────────────────────────────────
        case "mode:inference":
            guard let mode = InferenceMode(rawValue: rawInference(value)) else {
                return .badValue("unknown inference mode '\(value)'")
            }
            app.inferenceMode = mode
            return .applied(L("Inference route → \(mode.rawValue)",
                              "推論経路 → \(mode.rawValue)"))

        case "mode:operation":
            guard let mode = OperationMode(rawValue: rawOperation(value)) else {
                return .badValue("unknown operation mode '\(value)'")
            }
            app.operationMode = mode
            return .applied(L("Operation mode → \(mode.rawValue)",
                              "動作モード → \(mode.rawValue)"))

        case "mode:memory_layer":
            guard let mode = GatekeeperModeState.MemoryLayerMode(rawValue: value) else {
                return .badValue("unknown memory layer mode '\(value)'")
            }
            GatekeeperModeState.shared.bitnetMemoryLayerMode = mode
            return .applied(L("BitNet memory depth → \(value)",
                              "BitNet 記憶の深さ → \(value)"))

        // ── Plain settings ───────────────────────────────────────────────
        case "model.ollama":
            app.activeOllamaModel = value
            return .applied(L("Ollama model → \(value)", "Ollama モデル → \(value)"))

        case "model.ollama_endpoint":
            app.ollamaEndpoint = value
            return .applied(L("Ollama endpoint → \(value)",
                              "Ollama エンドポイント → \(value)"))

        case "agent.system_prompt":
            app.systemPrompt = value
            return .applied(L("System prompt updated", "システムプロンプトを更新"))

        case "agent.loop":
            guard let on = boolValue(value) else { return .badValue(value) }
            app.agentLoopEnabled = on
            return .applied(L("Agent loop → \(on ? "on" : "off")",
                              "エージェントループ → \(on ? "オン" : "オフ")"))

        case "agent.gatekeeper":
            guard let on = boolValue(value) else { return .badValue(value) }
            GatekeeperModeState.shared.isEnabled = on
            return .applied(L("Gatekeeper → \(on ? "on" : "off")",
                              "ゲートキーパー → \(on ? "オン" : "オフ")"))

        case "tools.diff":
            guard let on = boolValue(value) else { return .badValue(value) }
            app.toolDiffEnabled = on
            return .applied(L("Diff tool → \(on ? "on" : "off")",
                              "差分ツール → \(on ? "オン" : "オフ")"))

        case "privacy.masking":
            guard let on = boolValue(value) else { return .badValue(value) }
            app.gemmaSemanticMaskingEnabled = on
            return .applied(L("Semantic masking → \(on ? "on" : "off")",
                              "セマンティックマスキング → \(on ? "オン" : "オフ")"))

        case "memory.cortex":
            guard let on = boolValue(value) else { return .badValue(value) }
            // CortexEngine.shared is optional — it exists only once the engine
            // has been brought up. Reporting that is the point: silently
            // succeeding while nothing was set is the failure mode this whole
            // type exists to prevent.
            guard let cortex = CortexEngine.shared else {
                return .notApplicable(L(
                    "Cortex is not running yet — open Settings › Memory and "
                    + "enable it there.",
                    "Cortex がまだ起動していません。設定 › Memory を開いて"
                    + "そちらで有効にしてください。"))
            }
            cortex.isEnabled = on
            return .applied(L("Cortex memory → \(on ? "on" : "off")",
                              "Cortex 記憶 → \(on ? "オン" : "オフ")"))

        case "memory.external_llm":
            guard let on = boolValue(value) else { return .badValue(value) }
            GatekeeperModeState.shared.allowExternalLLMForCommander = on
            return .applied(L("External LLM for commander → \(on ? "allowed" : "blocked")",
                              "コマンダーの外部 LLM → \(on ? "許可" : "禁止")"))

        default:
            return .notApplicable(L(
                "This one is not set from here — open the screen and change it.",
                "これはここからは変更できません。画面を開いて変更してください。"))
        }
    }

    /// True when a step can be applied without opening anything. Used to
    /// decide which button a step gets, so the UI never offers an Apply that
    /// would immediately report notApplicable.
    static func canApply(key: String) -> Bool {
        switch key {
        case "mode:inference", "mode:operation", "mode:memory_layer",
             "model.ollama", "model.ollama_endpoint", "agent.system_prompt",
             "agent.loop", "agent.gatekeeper", "tools.diff",
             "privacy.masking", "memory.cortex", "memory.external_llm":
            return true
        default:
            return false
        }
    }

    // MARK: - Value coercion
    //
    // Vera speaks in enum case names ("localOnly"); the Swift enums are keyed
    // by display strings ("Local Only"). Translating here keeps the registry
    // in the vocabulary of the source enums rather than of one UI's labels.

    private static func rawInference(_ v: String) -> String {
        switch v {
        case "localOnly":     return "Local Only"
        case "cloudDirect":   return "Cloud Direct"
        case "privacyShield": return "Privacy Shield"
        case "paranoiaMode":  return "Paranoia Mode"
        default:              return v
        }
    }

    private static func rawOperation(_ v: String) -> String {
        switch v {
        case "gatekeeper": return "Gatekeeper"
        case "automatic":  return "Automatic"
        case "detailed":   return "Detailed"
        default:           return v
        }
    }

    private static func boolValue(_ v: String) -> Bool? {
        switch v.lowercased() {
        case "true", "1", "on", "yes":  return true
        case "false", "0", "off", "no": return false
        default: return nil
        }
    }
}
