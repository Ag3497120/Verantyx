import Foundation
import SwiftUI

/// The single source of truth for the JGEN council / 4-layer setup.
///
/// Before this existed, the council configuration lived only as ~10 loose
/// `@State` vars inside `VectorLabView`, which meant (a) it was forgotten on
/// every relaunch and (b) nothing outside that one view could read it -- so
/// the council could never be driven from normal chat. Both the Vector Lab
/// and the model-selector bar's JGEN options popover now bind to this.
///
/// Layer mapping (the user's 4-layer architecture):
///   - Layer 0 memory     → `config.useVeraMemory` / `zoneLayers` / `useEternalMemory`
///   - Layer 1 council    → `config.roleCount` / `roundsCap` / `injectionPolicy`
///   - Layer 2 execution  → `executionModel` (a tool-using agent, see ExecutionAgent)
///   - Layer 3 escalation → `config.escalateOnLowConfidence` / threshold / `escalationModel`
@MainActor
final class CouncilSettingsStore: ObservableObject {

    static let shared = CouncilSettingsStore()

    private static let configKey = "council_config_v1"
    private static let templateKey = "council_template_id"
    private static let useForChatKey = "council_use_for_chat"
    private static let executionModelKey = "council_execution_model"
    private static let executionUseJGENKey = "council_execution_use_jgen"
    private static let useVisualMemoryKey = "council_use_visual_memory"
    private static let useVeraHarnessKey = "council_use_vera_harness"
    private static let cognitionModeKey = "council_cognition_mode"

    @Published var config: CouncilOrchestrator.Config {
        didSet { persistConfig() }
    }

    /// Id of the architecture template this config came from, or "custom"
    /// once any field is hand-edited.
    @Published var templateId: String {
        didSet { UserDefaults.standard.set(templateId, forKey: Self.templateKey) }
    }

    /// When true (and a JGEN model is loaded), a normal chat turn runs the
    /// full layered pipeline instead of the plain agent loop.
    @Published var useCouncilForChat: Bool {
        didSet { UserDefaults.standard.set(useCouncilForChat, forKey: Self.useForChatKey) }
    }

    /// Layer 2's model. Deliberately separate from `AppState.activeOllamaModel`
    /// (the chat model): the execution agent is a different role, and
    /// clobbering the user's chat model when a template is applied would be a
    /// surprising regression.
    @Published var executionModel: String {
        didSet { UserDefaults.standard.set(executionModel, forKey: Self.executionModelKey) }
    }

    /// **Beta / experimental.** When true, Layer 2 runs on the same JGEN
    /// model doing Layer 1's deliberation instead of `executionModel`
    /// (Ollama) -- the whole council + execution path stays on one model,
    /// so screen-understanding steps go through `VisualHiddenStateBridge`'s
    /// hidden-state injection instead of a second model's multimodal
    /// image attach. `executionModel` is left untouched and simply ignored
    /// while this is on, so turning it back off restores the previous
    /// Ollama execution model with no reconfiguration needed. Requires a
    /// JGEN model to already be loaded (same requirement Layer 1 has);
    /// `LayeredRunOrchestrator` falls back to `executionModel` if JGEN
    /// isn't actually loaded when a run starts.
    @Published var executionUseJGEN: Bool {
        didSet { UserDefaults.standard.set(executionUseJGEN, forKey: Self.executionUseJGENKey) }
    }

    /// Milestone L: pseudo-multimodal visual memory (Vision feature-print
    /// recall). Kept as a top-level property rather than a `Config` field
    /// because `AgentLoop.swift`'s plain (non-Council) chat path never
    /// receives a `CouncilOrchestrator.Config` -- it reads this singleton
    /// directly instead of needing a new parameter threaded through
    /// `AgentLoop.run`. Opt-in default (`false`): a live window capture +
    /// Vision request every qualifying turn is real per-turn cost, unlike
    /// text memory.
    @Published var useVisualMemory: Bool {
        didSet { UserDefaults.standard.set(useVisualMemory, forKey: Self.useVisualMemoryKey) }
    }

    /// Milestone N: "Vera as harness" mode. When true, a chat turn is
    /// handed to Vera-alpha's own Agent.run() ReAct loop (via
    /// VeraAgentClient -> vera_server.py's HTTP+SSE daemon) instead of
    /// this app's normal AgentLoop/CouncilOrchestrator -- Vera becomes the
    /// controller, not a tool called from here. Requires `vera serve` to
    /// be running (started as a subprocess the same way vera-memory's MCP
    /// mode already is). Opt-in default (`false`): this is a structural
    /// inversion of who drives the turn, not a drop-in toggle.
    @Published var useVeraHarnessForChat: Bool {
        didSet { UserDefaults.standard.set(useVeraHarnessForChat, forKey: Self.useVeraHarnessKey) }
    }

    /// Milestone O: normal (default, no gap nodes ever created) / experiment
    /// (persists a GapNode whenever Vera hits a typed UNKNOWN, never auto-
    /// resolves) / sleep (experiment + heartbeat attempts quarantine-gated
    /// resolution of open-domain gaps -- nothing is ever promoted to the
    /// trusted store without a human accept, see ai_ingest.propose_raw on
    /// the Python side). Only takes effect when `useVeraHarnessForChat` is
    /// on -- it's sent per-request to vera_server.py's /agent/run, not a
    /// separate connection. Independent toggle (not nested under
    /// useVeraHarnessForChat) so turning the harness off doesn't silently
    /// discard the user's chosen cognition mode.
    enum CognitionMode: String, CaseIterable, Identifiable {
        case normal, experiment, sleep
        var id: String { rawValue }
        var title: String {
            switch self {
            case .normal: return "Normal"
            case .experiment: return "Experiment"
            case .sleep: return "Sleep"
            }
        }
        var titleJA: String {
            switch self {
            case .normal: return "通常"
            case .experiment: return "実験"
            case .sleep: return "Sleep"
            }
        }
    }
    @Published var cognitionMode: CognitionMode {
        didSet { UserDefaults.standard.set(cognitionMode.rawValue, forKey: Self.cognitionModeKey) }
    }

    private init() {
        let ud = UserDefaults.standard
        if let data = ud.data(forKey: Self.configKey),
           let decoded = try? JSONDecoder().decode(CouncilOrchestrator.Config.self, from: data) {
            config = decoded
        } else {
            config = CouncilOrchestrator.Config()
        }
        templateId = ud.string(forKey: Self.templateKey) ?? "custom"
        useCouncilForChat = ud.bool(forKey: Self.useForChatKey)
        executionModel = ud.string(forKey: Self.executionModelKey) ?? ""
        executionUseJGEN = ud.bool(forKey: Self.executionUseJGENKey)
        useVisualMemory = ud.bool(forKey: Self.useVisualMemoryKey)
        useVeraHarnessForChat = ud.bool(forKey: Self.useVeraHarnessKey)
        cognitionMode = CognitionMode(rawValue: ud.string(forKey: Self.cognitionModeKey) ?? "normal") ?? .normal
    }

    private func persistConfig() {
        guard let data = try? JSONEncoder().encode(config) else { return }
        UserDefaults.standard.set(data, forKey: Self.configKey)
    }

    /// Marks the config as hand-edited. Call from any UI control that mutates
    /// a single field, so the template label stops claiming a preset the
    /// settings no longer match.
    func markCustom() {
        if templateId != "custom" { templateId = "custom" }
    }
}
