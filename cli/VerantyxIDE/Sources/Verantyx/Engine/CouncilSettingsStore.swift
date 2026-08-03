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
    private static let allowKeyframeEyeKey = "council_allow_keyframe_eye"
    private static let keyframeEyePrivacyAcknowledgedKey = "council_keyframe_eye_privacy_ack"
    /// Sense path: AX / text / vectors only — no screen JPEG into the model.
    nonisolated static let vectorOnlySenseKey = "council_vector_only_sense"
    /// JGEN Act exploration turn budget (positive int). `0`/`-1` also mean unlimited.
    nonisolated static let actMaxTurnsKey = "council_act_max_turns"
    /// When true, Act uses a very high practical ceiling instead of `actMaxTurns`.
    nonisolated static let actUnlimitedTurnsKey = "council_act_unlimited_turns"
    /// Default Act turn budget (matches the former hard ceiling).
    nonisolated static let actMaxTurnsDefault = 18
    /// Practical ceiling when unlimited is on (safety stop, not a product limit).
    nonisolated static let actUnlimitedPracticalCap = 10_000

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

    /// When true (default), the agent sense path never retains or injects
    /// screen pixels into LLM context: AX semantic map + vector stamps only.
    /// Act mirror UI may still capture for the human; those frames must not
    /// be copied into conversation / `CognitiveAnchorEngine.lastVisionScreenshot`.
    /// Opt-out restores legacy vision_browse / screenshot-inject behaviour.
    @Published var vectorOnlySense: Bool {
        didSet {
            UserDefaults.standard.set(vectorOnlySense, forKey: Self.vectorOnlySenseKey)
            if vectorOnlySense { SensePixelPolicy.resetOnceLog() }
        }
    }

    /// 1fps keyframe eye (Vera-a-V): explicit user permission. Default OFF.
    /// Real capture also requires privacy ack + agent running + HiddenWindow target.
    @Published var allowKeyframeEye: Bool {
        didSet { UserDefaults.standard.set(allowKeyframeEye, forKey: Self.allowKeyframeEyeKey) }
    }

    /// User confirmed the privacy warning before enabling keyframe eye.
    @Published var keyframeEyePrivacyAcknowledged: Bool {
        didSet { UserDefaults.standard.set(keyframeEyePrivacyAcknowledged, forKey: Self.keyframeEyePrivacyAcknowledgedKey) }
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

    /// JGEN Act max exploration turns (Layer 2 desktop/AX loop). Default 18.
    /// Ignored while `actUnlimitedTurns` is on. Values `≤ 0` also mean unlimited.
    @Published var actMaxTurns: Int {
        didSet { UserDefaults.standard.set(actMaxTurns, forKey: Self.actMaxTurnsKey) }
    }

    /// When true, Act exploration uses `actUnlimitedPracticalCap` (10_000)
    /// instead of a small turn budget. Safety brakes (identical-action streak,
    /// DONE, user cancel) still apply.
    @Published var actUnlimitedTurns: Bool {
        didSet { UserDefaults.standard.set(actUnlimitedTurns, forKey: Self.actUnlimitedTurnsKey) }
    }

    /// Effective turn budget passed to `JGenActAgent.run(maxTurns:)`.
    var resolvedActMaxTurns: Int { Self.resolveActMaxTurns(unlimited: actUnlimitedTurns, stored: actMaxTurns) }

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
        // Default ON: missing key → vector-only (AX/text/vectors, no pixel inject).
        vectorOnlySense = (ud.object(forKey: Self.vectorOnlySenseKey) as? Bool) ?? true
        allowKeyframeEye = ud.bool(forKey: Self.allowKeyframeEyeKey)
        keyframeEyePrivacyAcknowledged = ud.bool(forKey: Self.keyframeEyePrivacyAcknowledgedKey)
        useVeraHarnessForChat = ud.bool(forKey: Self.useVeraHarnessKey)
        cognitionMode = CognitionMode(rawValue: ud.string(forKey: Self.cognitionModeKey) ?? "normal") ?? .normal
        let storedTurns = ud.object(forKey: Self.actMaxTurnsKey) as? Int
        actMaxTurns = storedTurns ?? Self.actMaxTurnsDefault
        actUnlimitedTurns = ud.bool(forKey: Self.actUnlimitedTurnsKey)
            || (storedTurns.map { $0 <= 0 } ?? false)
    }

    /// Thread-safe read for actors / non-MainActor call sites (UserDefaults).
    nonisolated static var isVectorOnlySense: Bool {
        (UserDefaults.standard.object(forKey: vectorOnlySenseKey) as? Bool) ?? true
    }

    /// Thread-safe Act turn budget for orchestrator / agents.
    nonisolated static var resolvedActMaxTurns: Int {
        let ud = UserDefaults.standard
        let stored = (ud.object(forKey: actMaxTurnsKey) as? Int) ?? actMaxTurnsDefault
        let unlimited = ud.bool(forKey: actUnlimitedTurnsKey) || stored <= 0
        return resolveActMaxTurns(unlimited: unlimited, stored: stored)
    }

    nonisolated static func resolveActMaxTurns(unlimited: Bool, stored: Int) -> Int {
        if unlimited || stored <= 0 { return actUnlimitedPracticalCap }
        return max(1, stored)
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

// MARK: - Sense pixel policy (vector-only gate)

/// Central gate for “do not keep / inject screen pixels into the model”.
/// Aligns with `JGenGPUSafety`: fewer WindowServer captures while JGEN runs.
enum SensePixelPolicy {
    private static let lock = NSLock()
    private static var didLogVectorOnly = false

    static var isVectorOnly: Bool { CouncilSettingsStore.isVectorOnlySense }

    /// Log once per enablement window (process, or after toggling back on).
    static func logVectorOnlyOnce() {
        lock.lock()
        defer { lock.unlock() }
        guard !didLogVectorOnly else { return }
        didLogVectorOnly = true
        print("📐 [Sense] vector-only — pixels not retained for model")
    }

    static func resetOnceLog() {
        lock.lock()
        didLogVectorOnly = false
        lock.unlock()
    }

    /// Drop any pending screen JPEG that would otherwise be multimodal-injected.
    static func clearModelPixelBuffers() async {
        await CognitiveAnchorEngine.shared.clearVisionScreenshot()
        await MainActor.run {
            AppState.shared?.lastVideoFrames = nil
            AppState.shared?.lastDesktopChangedRegion = nil
        }
    }
}
