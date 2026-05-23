import Foundation
import SwiftUI
import AppKit
import WebKit

// MARK: - Core data models

struct ChatMessage: Identifiable, Equatable, Codable {
    var id: UUID
    var role: Role
    var content: String
    var timestamp = Date()
    /// 推論中のプロセスログのスナップショット（折りたたみ可能な Thinking ブロックに表示）
    var thinkingLog: [ThinkingLogEntry] = []

    init(id: UUID = UUID(), role: Role, content: String, thinkingLog: [ThinkingLogEntry] = []) {
        self.id = id
        self.role = role
        self.content = content
        self.thinkingLog = thinkingLog
    }

    enum Role: String, Codable { case user, assistant, system }

    // ProcessLogEntry の Codable スナップショット（Color は保存しないためシンプル化）
    struct ThinkingLogEntry: Identifiable, Codable, Equatable {
        var id = UUID()
        var timestamp: Date
        var text: String
        var kind: String    // "memory" | "tool" | "browser" | "thinking" | "system" | "perf"
    }
}


struct FileDiff: Identifiable, Equatable {
    let id = UUID()
    let fileURL: URL
    let originalContent: String
    let modifiedContent: String
    var hunks: [DiffHunk]

    var hasChanges: Bool { originalContent != modifiedContent }

    // Equatable: same identity ↔ same diff (new FileDiff always has new UUID)
    static func == (lhs: FileDiff, rhs: FileDiff) -> Bool { lhs.id == rhs.id }
}

struct DiffHunk: Identifiable {
    let id = UUID()
    var lines: [DiffLine]
}

struct DiffLine: Identifiable {
    let id = UUID()
    var kind: Kind
    var text: String

    enum Kind { case context, added, removed }
}

// MARK: - AppState

@MainActor
final class AppState: ObservableObject {

    // ── Global weak reference — set at launch so AgentToolExecutor can call
    // ingestArtifact() from actor context without importing the full SwiftUI stack.
    @MainActor static weak var shared: AppState?

    // Workspace
    @Published var activeWebViews: [String: WKWebView] = [:]
    @Published var workspaceURL: URL?
    @Published var workspaceFiles: [URL] = []
    @Published var selectedFile: URL? {
        didSet {
            // Notify Extension Host that a new document was opened
            if let file = selectedFile {
                ExtensionHostManager.shared.sendNotification(method: "workspace.didOpenTextDocument", params: [
                    "uri": file.path,
                    "languageId": file.pathExtension,
                    "version": 1,
                    "text": selectedFileContent
                ])
            }
        }
    }
    @Published var selectedFileContent: String = "" {
        didSet {
            // Notify Extension Host that the document content changed
            if let file = selectedFile {
                ExtensionHostManager.shared.sendNotification(method: "workspace.didChangeTextDocument", params: [
                    "uri": file.path,
                    "text": selectedFileContent,
                    "range": [
                        "startLine": 0,
                        "endLine": max(0, oldValue.filter { $0 == "\n" }.count)
                    ]
                ])
            }
        }
    }

    // Model
    @Published var modelStatus: ModelStatus = .none
    @Published var ollamaModels: [String] = []
    // activeOllamaModel は下記(L412付近)でdidSetつきで宣言済み
    @Published var anthropicApiKey: String = "" {
        didSet {
            // Anthropic API キーを AnthropicClient に反映
            Task { await AnthropicClient.shared.configure(apiKey: anthropicApiKey) }
            UserDefaults.standard.set(anthropicApiKey, forKey: "anthropic_api_key")
        }
    }
    @Published var activeAnthropicModel: String = {
        UserDefaults.standard.string(forKey: "anthropic_model") ?? "claude-sonnet-4-5"
    }() {
        didSet { UserDefaults.standard.set(activeAnthropicModel, forKey: "anthropic_model") }
    }
    @Published var activeOpenAIModel: String = {
        UserDefaults.standard.string(forKey: "openai_model") ?? "gpt-4o"
    }() {
        didSet { UserDefaults.standard.set(activeOpenAIModel, forKey: "openai_model") }
    }
    @Published var activeGeminiModel: String = {
        UserDefaults.standard.string(forKey: "gemini_model") ?? "gemini-3.1-pro"
    }() {
        didSet { UserDefaults.standard.set(activeGeminiModel, forKey: "gemini_model") }
    }
    @Published var activeDeepSeekModel: String = {
        UserDefaults.standard.string(forKey: "deepseek_model") ?? "deepseek-coder"
    }() {
        didSet { UserDefaults.standard.set(activeDeepSeekModel, forKey: "deepseek_model") }
    }
    @Published var customHFRepoId: String = "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit"
    @Published var downloadProgress: Double = 0

    // Chat
    @Published var messages: [ChatMessage] = []
    @Published var inputText: String = ""
    @Published var isGenerating = false

    // Self-Fix mode — when true, next message(s) target IDE self-modification
    // Must be explicitly toggled by user pressing the "Self Fix" button.
    @Published var selfFixMode: Bool = false
    /// Set to true when the AI calls [RESTART_IDE] — triggers a restart alert in the UI.
    @Published var showRestartAlert: Bool = false
    @Published var requiresHumanPuzzle: Bool = false
    @Published var isAgentControllingMouse: Bool = false
    @Published var lastEntropy: [CGPoint]? = nil
    @Published var lastVideoFrames: [String]? = nil
    @Published var lastKeyboardEntropy: [Double]? = nil
    @Published var lastEntropyTimestamp: Date? = nil
    @Published var searchCooldownUntil: Date? = nil
    var lastKeystrokeTime: Date? = nil

    // Attachments (images + files for multimodal inference)
    @Published var attachedImages: [AttachedImage] = []
    @Published var attachedFiles: [URL] = []

    // Inference task handle (for cancellation)
    private var inferenceTask: Task<Void, Never>? = nil

    // UUID of the assistant message bubble currently receiving streaming tokens.
    // Elevated to instance-level so restoreSession() can nil it on session switch,
    // preventing stale UUIDs from corrupting a newly-loaded session's first stream.
    var streamingMsgId: UUID? = nil

    // ── Performance metrics (the "Apple Silicon violence" numbers) ──
    @Published var tokensPerSecond: Double = 0       // live tok/s display
    @Published var totalTokensGenerated: Int = 0     // session total
    @Published var streamingText: String = ""        // current token buffer for live render
    @Published var inferenceMs: Int = 0              // last response latency ms

    // ── Process log ("what is the AI thinking right now") ──
    @MainActor
    final class ProcessLogStore: ObservableObject {
        @Published var entries: [ProcessLogEntry] = []
    }
    let logStore = ProcessLogStore()
    
    @Published var showProcessLog: Bool = true

    struct ProcessLogEntry: Identifiable {
        let id = UUID()
        let timestamp: Date
        var text: String
        var kind: Kind

        enum Kind: String { case memory, tool, browser, thinking, system, perf }

        var prefix: String {
            switch kind {
            case .memory:   return "→ MEM  "
            case .tool:     return "→ TOOL "
            case .browser:  return "→ DOM  "
            case .thinking: return "▶ THINK"
            case .system:   return "⋯ SYS  "
            case .perf:     return "⚡ PERF "
            }
        }

        var color: Color {
            switch kind {
            case .memory:   return Color(red: 0.4, green: 0.9, blue: 0.6)
            case .tool:     return Color(red: 0.4, green: 0.8, blue: 1.0)
            case .browser:  return Color(red: 0.9, green: 0.7, blue: 0.3)
            case .thinking: return Color(red: 0.8, green: 0.8, blue: 1.0)
            case .system:   return Color(red: 0.6, green: 0.6, blue: 0.6)
            case .perf:     return Color(red: 0.3, green: 1.0, blue: 0.5)
            }
        }
    }

    // Diff
    @Published var pendingDiff: FileDiff?
    @Published var showDiff = false

    // Human Mode: file write / create / edit approval
    @Published var pendingFileApproval: FileApprovalRequest? = nil

    // Active tab in the center chat panel — driven by AppState so
    // SessionHistoryView can programmatically switch to .workspace
    // after restoring a session (the tab @State lives in AgentChatView).
    @Published var activeChatTab: Int = 0   // 0=workspace, 1=history, 2=thinking

    // Operation Mode (AI Priority vs Human)
    @Published var operationMode: OperationMode = .human {
        didSet {
            UserDefaults.standard.set(operationMode.rawValue, forKey: "operation_mode")
            // Sync MCPEngine execution mode
            let mcpMode: MCPServerConfig.ExecutionMode = operationMode == .aiPriority ? .ai : .human
            Task { MCPEngine.shared.setMode(mcpMode) }
            
            // Auto-toggle JCross view and Gatekeeper State
            if operationMode == .gatekeeper {
                GatekeeperModeState.shared.isEnabled = true
                showGatekeeperRawCode = false
            } else {
                GatekeeperModeState.shared.isEnabled = false
                showGatekeeperRawCode = true
            }
            
            // Sync editing mode
            if editingMode != operationMode {
                editingMode = operationMode
            }
            
            // L2.5 変換の制御 (人間優先モードでのみ有効にする)
            if operationMode == .human {
                if L25IndexEngine.shared.hasPausedMap || L25IndexEngine.shared.isStopped {
                    L25IndexEngine.shared.resumeIndexing()
                } else if let ws = workspaceURL, !L25IndexEngine.shared.isIndexing {
                    Task { @MainActor in
                        await L25IndexEngine.shared.loadAndIncrementalUpdate(workspaceURL: ws)
                    }
                }
            } else {
                if L25IndexEngine.shared.isIndexing {
                    L25IndexEngine.shared.cancelIndexing()
                }
            }
        }
    }

    // Artifacts (Claude-style live preview)
    @Published var currentArtifact: Artifact? = nil
    @Published var artifactHistory: [Artifact] = []
    @Published var showArtifactPanel: Bool = false

    // Privacy Shield / Hybrid mode
    @Published var inferenceMode: InferenceMode = .localOnly {
        didSet { UserDefaults.standard.set(inferenceMode.rawValue, forKey: "inference_mode") }
    }
    @Published var cloudProvider: CloudProvider = .claude {
        didSet { UserDefaults.standard.set(cloudProvider.rawValue, forKey: "cloud_provider") }
    }
    @Published var lastMaskingStats: MaskingStats?
    @Published var privacySteps: [String] = []
    @Published var paranoiaLogLines: [ParanoiaEngine.ParanoiaLogLine] = []  // Paranoia Mode live log

    // ── Model configuration (all persisted via UserDefaults) ──
    @Published var temperature: Double = 0.1 {
        didSet { UserDefaults.standard.set(temperature, forKey: "model_temperature") }
    }
    @Published var maxTokensOllama: Int = 2048 {
        didSet { UserDefaults.standard.set(maxTokensOllama, forKey: "max_tokens_ollama") }
    }
    @Published var maxTokensMLX: Int = 4096 {
        didSet { UserDefaults.standard.set(maxTokensMLX, forKey: "max_tokens_mlx") }
    }
    @Published var ollamaEndpoint: String = "http://localhost:11434" {
        didSet { UserDefaults.standard.set(ollamaEndpoint, forKey: "ollama_endpoint") }
    }
    
    // ── Exo Cluster ──
    @Published var exoEnabled: Bool = {
        let v = UserDefaults.standard.bool(forKey: "exo_enabled")
        return v
    }() {
        didSet {
            UserDefaults.standard.set(exoEnabled, forKey: "exo_enabled")
            if exoEnabled {
                Task { @MainActor in ExoEngine.shared.start() }
            } else {
                Task { @MainActor in ExoEngine.shared.stop() }
            }
        }
    }
    @Published var exoEndpoint: String = {
        UserDefaults.standard.string(forKey: "exo_endpoint") ?? ""
    }() {
        didSet { UserDefaults.standard.set(exoEndpoint, forKey: "exo_endpoint") }
    }

    @Published var systemPrompt: String = "You are Verantyx, an expert AI coding assistant running on Apple Silicon. Be concise and precise. Prefer code over prose." {
        didSet { UserDefaults.standard.set(systemPrompt, forKey: "system_prompt") }
    }
    @Published var streamingEnabled: Bool = true {
        didSet { UserDefaults.standard.set(streamingEnabled, forKey: "streaming_enabled") }
    }

    // ── Tool toggles ──
    @Published var toolBrowserEnabled: Bool = true {
        didSet { UserDefaults.standard.set(toolBrowserEnabled, forKey: "tool_browser") }
    }
    @Published var toolWebSearchEnabled: Bool = true {
        didSet { UserDefaults.standard.set(toolWebSearchEnabled, forKey: "tool_web_search") }
    }
    @Published var toolTerminalEnabled: Bool = true {
        didSet { UserDefaults.standard.set(toolTerminalEnabled, forKey: "tool_terminal") }
    }
    @Published var toolDiffEnabled: Bool = true {
        didSet { UserDefaults.standard.set(toolDiffEnabled, forKey: "tool_diff") }
    }
    @Published var toolJCrossEnabled: Bool = true {
        didSet { UserDefaults.standard.set(toolJCrossEnabled, forKey: "tool_jcross") }
    }

    // ── Privacy Gateway: Gemma semantic masking ──
    /// Gemmaによるセマンティックマスキング (Phase 2) の有効/無効
    /// OFF時は Phase 1 正規表現マスキングのみ使用（高速、Gemma不要）
    @Published var gemmaSemanticMaskingEnabled: Bool = true {
        didSet { UserDefaults.standard.set(gemmaSemanticMaskingEnabled, forKey: "gemma_semantic_masking") }
    }

    // ── UI Language ──
    enum UILanguage: String, CaseIterable, Codable {
        case system  = "System"
        case english = "English"
        case japanese = "日本語"

        var localeIdentifier: String {
            switch self {
            case .system:   return Locale.current.identifier
            case .english:  return "en"
            case .japanese: return "ja"
            }
        }

        var flag: String {
            switch self {
            case .system:   return "🌐"
            case .english:  return "🇺🇸"
            case .japanese: return "🇯🇵"
            }
        }
    }

    @Published var appLanguage: UILanguage = {
        let raw = UserDefaults.standard.string(forKey: "app_language") ?? UILanguage.system.rawValue
        return UILanguage(rawValue: raw) ?? .system
    }() {
        didSet {
            UserDefaults.standard.set(appLanguage.rawValue, forKey: "app_language")
            // Keep global AppLanguage singleton in sync for NSTextView/NSMenuItem code
            let isJA: Bool
            switch appLanguage {
            case .japanese: isJA = true
            case .english:  isJA = false
            case .system:   isJA = Locale.current.language.languageCode?.identifier == "ja"
            }
            AppLanguage.shared.isJapanese = isJA
        }
    }

    // MARK: - Localized string helper
    func t(_ en: String, _ ja: String) -> String {
        switch appLanguage {
        case .japanese: return ja
        case .english:  return en
        case .system:
            return Locale.current.language.languageCode?.identifier == "ja" ? ja : en
        }
    }

    // MARK: - UI Preferences

    @Published var codeFontSize: Int = {
        let v = UserDefaults.standard.integer(forKey: "code_font_size")
        return v > 0 ? v : 12
    }() {
        didSet { UserDefaults.standard.set(codeFontSize, forKey: "code_font_size") }
    }

    @Published var notifyOnDiffApply: Bool = UserDefaults.standard.bool(forKey: "notify_diff_apply") {
        didSet { UserDefaults.standard.set(notifyOnDiffApply, forKey: "notify_diff_apply") }
    }

    @Published var notifyOnError: Bool = {
        let v = UserDefaults.standard.object(forKey: "notify_error") as? Bool
        return v ?? true
    }() {
        didSet { UserDefaults.standard.set(notifyOnError, forKey: "notify_error") }
    }

    // ── Multimodal capability detection ──
    var isMultimodalModel: Bool {
        switch modelStatus {
        case .ollamaReady(let m):
            let mm = m.lowercased()
            return mm.contains("llava") || mm.contains("vision")
                || mm.contains("gemma") || mm.contains("qwen") && mm.contains("vl")
                || mm.contains("minicpm") || mm.contains("moondream")
                || mm.contains("bakllava") || mm.contains("cogvlm")
        case .mlxReady(let m):
            let mm = m.lowercased()
            return mm.contains("vision") || mm.contains("gemma-4")
                || mm.contains("qwen-vl") || mm.contains("llava") || mm.contains("llm3.2")
        default: return false
        }
    }

    enum ModelStatus: Equatable {
        case none
        case connecting
        case downloading(progress: Double)
        case ready(name: String)
        case ollamaReady(model: String)
        case anthropicReady(model: String, maskedKey: String)  // Anthropic API
        case mlxReady(model: String)          // MLX server running at localhost:8080
        case mlxDownloading(model: String)    // mlx_lm download in progress
        case bitnetReady(model: String)       // BitNet local subprocess
        case error(String)
    }

    // Workspace manager (lazy)
    private let workspace = WorkspaceManager()
    let agent = AgentEngine()
    let terminal = TerminalRunner()
    let cortex = CortexEngine()
    let sessions = SessionStore()

    // MARK: - Dirty state (close/quit guard)

    /// True when there is active work that should be saved before quitting.
    var isDirty: Bool {
        (workspaceURL != nil && (pendingDiff != nil || messages.count > 2))
        || isGenerating
    }

    // MARK: - Self-Admin API
    // AI agent calls this to modify IDE settings directly from chat instructions.
    // AllowList design: only known keys are accepted; unknown keys warn but don't crash.
    @discardableResult
    func applySetting(key: String, value: String) -> String {
        switch key {
        case "system_prompt":
            systemPrompt = value
        case "operation_mode":
            if value == "aiPriority" || value == "ai" { operationMode = .aiPriority }
            else if value == "humanPriority" || value == "Human Priority" { operationMode = .humanPriority }
            else { operationMode = .human }
        case "temperature":
            if let d = Double(value) { temperature = max(0.0, min(2.0, d)) }
            else { return "⚠️ Invalid temperature: \(value) (expected 0.0–2.0)" }
        case "max_tokens_ollama":
            if let i = Int(value) { maxTokensOllama = max(64, min(32768, i)) }
            else { return "⚠️ Invalid max_tokens_ollama: \(value)" }
        case "max_tokens_mlx":
            if let i = Int(value) { maxTokensMLX = max(64, min(32768, i)) }
            else { return "⚠️ Invalid max_tokens_mlx: \(value)" }
        case "ollama_endpoint":
            ollamaEndpoint = value
        case "inference_mode":
            if let m = InferenceMode(rawValue: value) { inferenceMode = m }
            else { return "⚠️ Unknown inference_mode: \(value). Valid: localOnly, cloudDirect, privacyShield, paranoiaMode" }
        case "agent_loop_enabled":
            agentLoopEnabled = (value == "true" || value == "1" || value == "yes")
        case "streaming_enabled":
            streamingEnabled = (value == "true" || value == "1" || value == "yes")
        case "anthropic_api_key":
            anthropicApiKey = value
        case "active_ollama_model":
            activeOllamaModel = value
            modelStatus = .ollamaReady(model: value)
        default:
            return "⚠️ Unknown setting key: '\(key)'. Valid keys: system_prompt, operation_mode, temperature, max_tokens_ollama, max_tokens_mlx, ollama_endpoint, inference_mode, agent_loop_enabled, streaming_enabled, anthropic_api_key, active_ollama_model"
        }
        return "✓ \(key) = \(value.prefix(80))"
    }

    // MLX state
    @Published var activeMlxModel: String = {
        UserDefaults.standard.string(forKey: "active_mlx_model")
            ?? "mlx-community/gemma-4-26b-a4b-it-4bit"
    }() {
        didSet { UserDefaults.standard.set(activeMlxModel, forKey: "active_mlx_model") }
    }
    @Published var mlxServerLogs: [String] = []

    // Agent loop
    @Published var agentLoopEnabled: Bool = true {
        didSet { UserDefaults.standard.set(agentLoopEnabled, forKey: "agent_loop_enabled") }
    }

    // ── VX-Loop: Chat session-level persistent ID for VXTimeline ─────────
    // nano/small モデル使用時、全ターンで同一IDを共有することで
    // VXTimeline内の履歴記録を次のターンで参照できる。
    // newChatSession() でリセットされる。
    var vxChatSessionId: String = String(UUID().uuidString.prefix(8))

    // nano/small モデル選択時に AI Priority を強制するフラグ
    @Published var isNanoSmallModelActive: Bool = false

    // MARK: - Mode & Model Sync

    @Published var editingMode: OperationMode = .human

    func getOllamaModel(for mode: OperationMode) -> String {
        if mode == .gatekeeper {
            return GatekeeperPipelineState.shared.config.intentOllamaModel
        }
        return UserDefaults.standard.string(forKey: "model_for_\(mode.rawValue)") ?? UserDefaults.standard.string(forKey: "active_ollama_model") ?? "gemma4:26b"
    }

    func setOllamaModel(_ model: String, for mode: OperationMode) {
        if mode == .gatekeeper {
            var config = GatekeeperPipelineState.shared.config
            config.intentOllamaModel = model
            GatekeeperPipelineState.shared.config = config
            config.save()
        } else {
            UserDefaults.standard.set(model, forKey: "model_for_\(mode.rawValue)")
        }
        
        if mode == operationMode && activeOllamaModel != model {
            activeOllamaModel = model
        }
    }

    func switchModeAndEjectOldModel(to mode: OperationMode) {
        Task {
            let loaded = await OllamaClient.shared.loadedModels()
            for m in loaded {
                await OllamaClient.shared.unloadModel(m.name)
            }
            
            await MainActor.run {
                operationMode = mode
                let targetModel = getOllamaModel(for: mode)
                if activeOllamaModel != targetModel {
                    activeOllamaModel = targetModel
                }
                connectOllama()
            }
        }
    }

    // モデル変更時: nano/small → AI Priority 強制、large/giant → human に復帰
    @Published var activeOllamaModel: String = {
        UserDefaults.standard.string(forKey: "active_ollama_model") ?? "gemma4:26b"
    }() {
        didSet {
            UserDefaults.standard.set(activeOllamaModel, forKey: "active_ollama_model")
            
            // Sync current model back to the current operation mode configuration
            if operationMode == .gatekeeper {
                var config = GatekeeperPipelineState.shared.config
                config.intentOllamaModel = activeOllamaModel
                GatekeeperPipelineState.shared.config = config
                config.save()
            } else {
                UserDefaults.standard.set(activeOllamaModel, forKey: "model_for_\(operationMode.rawValue)")
            }

            let tier = ModelProfileDetector.detect(modelId: activeOllamaModel).tier
            let isSmall = (tier == .nano || tier == .small)
            let wasSmall = isNanoSmallModelActive
            isNanoSmallModelActive = isSmall

            if isSmall && operationMode != .aiPriority {
                operationMode = .aiPriority
                addSystemMessage(
                    "🧠 [Nano Cortex] \(tier.displayName) モデルを検出。" +
                    "AI Priority + VX-Loop + ConfusionDetector を自動有効化しました"
                )
            } else if !isSmall && wasSmall && operationMode == .aiPriority {
                operationMode = .human
                addSystemMessage(
                    "💬 [モード復帰] \(tier.displayName) モデルに切り替えました。Human モードに戻りました"
                )
            }
        }
    }

    // MARK: - Workspace actions

    func openWorkspace() {
        guard let url = workspace.pickFolder() else { return }
        workspaceURL = url
        workspaceFiles = []
        selectedFile = nil
        selectedFileContent = ""
        terminal.workingDirectory = url
        // 再起動後も最後のワークスペースを復元できるよう保存
        UserDefaults.standard.set(url.path, forKey: "last_workspace_path")
        addSystemMessage("📂 Workspace: \(url.lastPathComponent)")
        SelfEvolutionEngine.shared.setWorkspaceHint(url)
        GatekeeperModeState.shared.configure(workspaceURL: url)
        refreshFiles()
        // ── ワークスペース追加時に L2.5 地図を自動生成 ───────────────────
        // @MainActor な buildProjectMap を Task で安全に呼び出す
        if operationMode == .human {
            Task { @MainActor in
                await L25IndexEngine.shared.buildProjectMap(workspaceURL: url)
                let count = L25IndexEngine.shared.projectMap?.fileCount ?? 0
                self.addSystemMessage(AppLanguage.shared.t("🗺️ L2.5 map generation complete: \(count) files", "🗺️ L2.5 地図生成完了: \(count) ファイル"))
            }
        }
    }

    /// Progressive directory scan — yields partial results as they arrive.
    /// First batch appears in ~200ms for most workspaces. Tree shows before scan completes.
    func refreshFiles() {
        guard let root = workspaceURL else { return }

        // Broader extension set so all relevant source/config files appear
        let exts: Set<String> = [
            // Apple
            "swift", "m", "mm", "xib", "storyboard", "plist",
            // Python
            "py", "pyw", "pyi", "ipynb",
            // JS / TS / Web
            "ts", "tsx", "js", "jsx", "mjs", "cjs", "vue", "svelte",
            "html", "htm", "css", "scss", "sass", "less",
            // Rust
            "rs", "toml",
            // Go
            "go",
            // JVM
            "kt", "kts", "java", "scala", "gradle",
            // C family
            "c", "cpp", "cc", "cxx", "h", "hpp",
            // Ruby / PHP
            "rb", "rake", "gemspec", "php",
            // Shell
            "sh", "bash", "zsh", "fish", "ps1",
            // Docs / Config
            "md", "mdx", "markdown", "txt", "rst",
            "json", "jsonc", "yaml", "yml",
            "xml", "csv", "sql", "graphql",
            "env", "lock",
            // Bare filenames (extension-less) — handled by name match in _scanDirectory
            "makefile", "dockerfile", "gitignore", "gitattributes",
            "procfile", "rakefile",
        ]

        // Use non-detached Task so MainActor isolation is inherited and `workspace`
        // (a @MainActor property) can be accessed safely. The async for-await iterator
        // yields control between snapshots so UI rendering is not blocked.
        Task(priority: .userInitiated) { [weak self] in
            guard let self else { return }
            for await snapshot in self.workspace.scanStreaming(in: root, extensions: exts) {
                self.workspaceFiles = snapshot
            }
        }
    }


    /// Helper to safely read and truncate file content for UI preview
    nonisolated private func safePreview(for url: URL) -> String {
        do {
            let attr = try FileManager.default.attributesOfItem(atPath: url.path)
            if let size = attr[.size] as? UInt64, size > 2_000_000 { // >2MB is too big for SwiftUI Text
                return ";;; ⚠️ File is too large to preview (\(size / 1_000_000) MB)"
            }
            let text = try String(contentsOf: url, encoding: .utf8)
            return truncatePreview(text: text)
        } catch {
            if let text = try? String(contentsOf: url, encoding: .isoLatin1) {
                return truncatePreview(text: text)
            }
            return ";;; ⚠️ Unable to read file content (binary or unknown encoding)"
        }
    }

    nonisolated private func truncatePreview(text: String) -> String {
        let maxChars = 100_000 // Safe limit for SwiftUI Text
        if text.count > maxChars {
            return String(text.prefix(maxChars)) + "\n\n... (File truncated for preview limit) ..."
        }
        return text
    }

    @Published var showGatekeeperRawCode: Bool = {
        let raw = UserDefaults.standard.string(forKey: "operation_mode") ?? OperationMode.human.rawValue
        let mode = OperationMode(rawValue: raw) ?? .human
        return mode != .gatekeeper
    }() {
        didSet {
            if let file = selectedFile { selectFile(file) }
        }
    }

    /// Instant selection — show name immediately, read content async.
    func selectFile(_ url: URL) {
        selectedFile = url          // highlight instantly (no wait)
        selectedFileContent = ""    // clear old content immediately

        // ── Gatekeeper Mode: Vault の JCross IR を表示 ────────────────
        // 有効な場合は実コードの代わりに JCross 変換済みコンテンツを表示する。
        // Vault 未登録ファイルは実コード + 警告バナーで表示。
        let gatekeeperEnabled = GatekeeperModeState.shared.isEnabled
        if gatekeeperEnabled && !showGatekeeperRawCode {
            let relativePath: String
            if let wsPath = workspaceURL?.path,
               url.path.hasPrefix(wsPath + "/") {
                relativePath = String(url.path.dropFirst(wsPath.count + 1))
            } else {
                relativePath = url.lastPathComponent
            }

            Task.detached { [weak self] in
                guard let self else { return }
                let vault = await MainActor.run { GatekeeperModeState.shared.vault }
                let result = await MainActor.run { vault.read(relativePath: relativePath) }

                await MainActor.run {
                    guard self.selectedFile == url else { return }
                    if let vaultResult = result {
                        // JCross IR を表示（先頭にバナーを付ける）
                        let banner = """
                        ;;; 🛡️ GATEKEEPER MODE — JCross IR View
                        ;;; Real identifiers have been replaced with node IDs.
                        ;;; Schema: \(vaultResult.entry.schemaSessionID.prefix(12))
                        ;;; Nodes: \(vaultResult.entry.nodeCount) | Secrets redacted: \(vaultResult.entry.secretCount)
                        ;;; Source: \(relativePath)
                        ;;; 
                        ;;; (To view raw code, toggle "Show Raw Code" above)
                        ;;;
                        """
                        self.selectedFileContent = banner + "\n" + self.truncatePreview(text: vaultResult.jcrossContent)
                    } else {
                        // Vault 未変換: 実コードを読み込み + 警告バナー
                        let raw = self.safePreview(for: url)
                        let warning = """
                        ;;; ⚠️ GATEKEEPER MODE — このファイルはまだ JCross 変換されていません
                        ;;; [Gatekeeper 設定] → [一括変換を開始] でVaultを更新してください
                        ;;; ※ 以下は実コードです。このビューは一時的なものです
                        ;;;
                        
                        """
                        self.selectedFileContent = warning + raw
                    }
                }
            }
            return
        }

        // ── 通常モード: 実ファイルを読み込む ─────────────────────────
        Task.detached { [weak self] in
            guard let self else { return }
            // Read on background thread — never blocks UI
            let content = self.safePreview(for: url)
            await MainActor.run {
                // Only update if this file is still selected
                guard self.selectedFile == url else { return }
                self.selectedFileContent = content
            }
        }
    }

    // MARK: - Session management

    /// Save the current chat to the session store.
    func saveCurrentSession() {
        if sessions.activeSessionId == nil, messages.count > 1 {
            _ = sessions.newSession(messages: messages, workspacePath: workspaceURL?.path)
        } else {
            sessions.updateActiveSession(messages: messages, workspacePath: workspaceURL?.path)
        }
    }

    /// Start a fresh chat  (old session saved automatically).
    func newChatSession() {
        // 新規セッション開始時は常にフォルダ選択ダイアログを開く
        openWorkspace()

        // Before clearing, archive the current session progressively
        if let currentId = sessions.activeSessionId,
           let current = sessions.sessions.first(where: { $0.id == currentId }),
           !current.messages.filter({ $0.role != .system }).isEmpty {
            SessionMemoryArchiver.shared.archiveProgressively(session: current)
        }

        saveCurrentSession()
        messages.removeAll()
        pendingDiff = nil
        showDiff    = false
        // 新セッション開始時に VXTimeline ID をリセット
        vxChatSessionId = String(UUID().uuidString.prefix(8))
        let newSession = sessions.newSession(messages: [], workspacePath: workspaceURL?.path)

        // ── Cross-session memory injection ───────────────────────────
        // Inject past sessions' JCross memory at the correct layer depth.
        let currentId = newSession.id
        let layer = sessions.activeSession?.activeLayer ?? .l2
        Task {
            let injection = SessionMemoryArchiver.shared.buildCrossSessionInjection(
                topK: 5,
                layer: layer,
                excludingSessionId: currentId
            )
            if !injection.isEmpty {
                await MainActor.run {
                    self.messages.insert(
                        ChatMessage(role: .system, content: injection),
                        at: 0
                    )
                    self.addSystemMessage(self.t("🧠 Injected memory from past session (\\(layer.rawValue) layer)", "🧠 過去セッションの記憶を注入しました (\\(layer.rawValue) レイヤー)"))
                }
            }
        }
    }

    /// Restore a past session by its ID (loads messages + memory injection).
    func restoreSession(_ sessionId: UUID) {
        guard let session = sessions.sessions.first(where: { $0.id == sessionId }) else { return }

        // ── Cancel any in-flight inference from the previous session ────
        // This ensures: (a) isGenerating is reset, (b) no stale onToken
        // callbacks write into the newly-restored messages array.
        inferenceTask?.cancel()
        inferenceTask = nil
        isGenerating  = false
        // ⚠️ MUST nil streamingMsgId BEFORE replacing messages.
        // If it remains non-nil, the next .streamToken will search for the
        // old UUID in the restored session's messages, fail to find it,
        // and create a NEW orphan bubble instead of tracking correctly.
        self.streamingMsgId = nil

        saveCurrentSession()
        sessions.selectSession(sessionId)

        // Restore messages — filter out any empty assistant bubbles that were
        // saved mid-stream before a previous fix (corrupt streaming artifacts).
        messages    = session.messages.filter { msg in
            !(msg.role == .assistant && msg.content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        }
        pendingDiff = nil
        showDiff    = false
        if let path = session.workspacePath {
            let url = URL(fileURLWithPath: path)
            if workspaceURL != url {
                workspaceURL = url
                terminal.workingDirectory = url
                refreshFiles()
            }
        }
        // Inject JCross memory for this session in background
        Task {
            let injection = await sessions.buildMemoryInjection(for: sessionId)
            if !injection.isEmpty {
                await MainActor.run {
                    self.messages.insert(ChatMessage(role: .system, content: injection), at: 0)
                }
            }
        }
        addSystemMessage(self.t("📂 Restored session '\\(session.title)'", "📂 セッション「\\(session.title)」を復元しました"))
        activeChatTab = 0
    }

    // MARK: - Agent actions

    func sendMessage(with overrideText: String? = nil) {
        let text = (overrideText ?? inputText).trimmingCharacters(in: .whitespacesAndNewlines)
        let hasAttachments = !attachedImages.isEmpty || !attachedFiles.isEmpty
        guard !text.isEmpty || hasAttachments, !isGenerating else { return }
        inputText = ""

        // Build the user message (with attachment summary if present)
        var displayContent = text
        if !attachedImages.isEmpty {
            displayContent += attachedImages.count == 1
                ? "\n📎 [Image: \(attachedImages[0].name)]"
                : "\n📎 [\(attachedImages.count) images attached]"
        }
        if !attachedFiles.isEmpty {
            for f in attachedFiles { displayContent += "\n📎 [File: \(f.lastPathComponent)]" }
        }

        let snapshotImages = attachedImages
        let snapshotFiles  = attachedFiles
        attachedImages.removeAll()
        attachedFiles.removeAll()

        messages.append(ChatMessage(role: .user, content: displayContent))
        isGenerating = true

        // Auto-create session if there isn't one yet
        if sessions.activeSessionId == nil {
            _ = sessions.newSession(messages: messages, workspacePath: workspaceURL?.path)
        }

        inferenceTask = Task {
            // ── BENCHMARK INTEGRATION ────────────────────────────────────────
            if text.starts(with: "/benchmark") {
                let parts = text.split(separator: " ")
                
                if parts.count >= 2 && parts[1] == "status" {
                    await MainActor.run { self.addSystemMessage("📊 取得中: Benchmark Status...") }
                    let result = await MCPEngine.shared.callTool(
                        serverName: "verantyx-compiler",
                        toolName: "benchmark_status",
                        arguments: [:]
                    )
                    await MainActor.run {
                        self.isGenerating = false
                        self.messages.append(ChatMessage(role: .assistant, content: "📈 Benchmark Status:\n\n\(result)"))
                        self.saveCurrentSession()
                    }
                    return
                }
                
                await MainActor.run { self.addSystemMessage("🚀 起動中: LongMemEval Benchmark...") }
                
                // Parse arguments like "/benchmark batch=5 total=10"
                var args: [String: Any] = [:]
                for part in parts.dropFirst() {
                    let kv = part.split(separator: "=")
                    if kv.count == 2, let v = Int(String(kv[1])) {
                        args[String(kv[0])] = v
                    }
                }
                
                let result = await MCPEngine.shared.callTool(
                    serverName: "verantyx-compiler",
                    toolName: "solve_all",
                    arguments: args
                )
                
                await MainActor.run {
                    self.isGenerating = false
                    self.messages.append(ChatMessage(role: .assistant, content: "📈 Benchmark Result:\n\n\(result)"))
                    self.saveCurrentSession()
                }
                return
            }

            // ── PIPELINE INTENT DETECTION ───────────────────────────────────
            // NOTE: Gatekeeper Mode ON の場合は CommanderOrchestrator が全処理を担うため
            //       ここでの旧フロー (BitNetCommanderLoop) ルーティングは完全に廃止しました。

            // ── SYSTEM STATUS INJECTION ──────────────────────────────────────
            // 状態確認系の質問 or バックグラウンドプロセスが動いているとき、
            // AI の systemPrompt にリアルタイムの状態ブロックを注入する。
            // → AI は「L2.5 が今 45% 完了」などを自律的に答えられる。
            let statusBlock = await MainActor.run {
                SystemStatusProvider.shared.systemStatusBlock()
            }
            if let status = statusBlock {
                await MainActor.run { self.systemPrompt += "\n\n" + status }
                // 返答後にステータスブロックを除去 (永続汚染しない)
                defer {
                    Task { @MainActor in
                        if let range = self.systemPrompt.range(of: "\n\n[SYSTEM STATUS") {
                            self.systemPrompt = String(self.systemPrompt[..<range.lowerBound])
                        }
                    }
                }
            }
            // 状態確認系の質問なら fullStatusReport を先にチャットに挿入
            if SystemStatusProvider.isStatusQuery(text) {
                let report = await MainActor.run {
                    SystemStatusProvider.shared.fullStatusReport()
                }
                await MainActor.run {
                    self.addSystemMessage(AppLanguage.shared.t("📊 System state snapshot:\n\(report)", "📊 システム状態スナップショット:\n\(report)"))
                }
            }
            // ── END STATUS INJECTION ─────────────────────────────────────────

            // Compress context if needed (Cortex anti-Alzheimer's)
            let trimmed = cortex.compressIfNeeded(messages: messages)
            if trimmed.count < messages.count {
                await MainActor.run { self.messages = trimmed }
            }

            // Route: Gatekeeper Mode → 新フロー (6軸IR → GraphPatch JSON → Vault復元)
            if await MainActor.run(body: { GatekeeperModeState.shared.isEnabled }) {
                // GatekeeperChatBridge が isGenerating = false まで責任を持つ
                await GatekeeperChatBridge.shared.run(instruction: text, appState: self)
            } else if inferenceMode == .cloudDirect || inferenceMode == .privacyShield || inferenceMode == .paranoiaMode {
                await runHybrid(instruction: text)
            } else if agentLoopEnabled {
                if editingMode == .human {
                    await MainActor.run { self.requiresHumanPuzzle = true }
                }
                
                // Pass images to agent loop so the model can see them
                let history = Array(self.messages.dropLast())
                await runAgentLoop(instruction: text,
                                   images: snapshotImages,
                                   files: snapshotFiles,
                                   previousMessages: history)
            } else {
                await runSinglePass(instruction: text,
                                    images: snapshotImages,
                                    files: snapshotFiles)
            }

            // Persist session after each exchange
            sessions.updateActiveSession(messages: messages, workspacePath: workspaceURL?.path)
        }
    }

    // MARK: - Pipeline Intent Classifier

    /// チャット入力がパイプラインタスク (変換・生成・ビルド系) かどうかを判定する。
    /// BitNet が使える場合は1.58bモデルで高速分類。
    /// BitNet 未インストールの場合はキーワードルールで判定。
    private func isPipelineIntent(text: String) async -> Bool {
        // LanguageDetector が言語非依存で判定 (BitNet 優先 → ルールベースフォールバック)
        if LanguageDetector.isPipelineIntent(text) { return true }
        // BitNet による追加分類
        if BitNetConfig.load()?.isValid == true {
            let classifyPrompt = """
            ### Instruction:
            Classify this user message. Reply ONLY with "pipeline" or "chat".
            "pipeline" = code transpilation, conversion, build, generate/port files from one language to another
            "chat" = question, explanation, review, discussion, anything else
            Message: \(text.prefix(200))
            ### Response:
            """
            if let result = await BitNetCommanderEngine.shared.generate(
                prompt: classifyPrompt, systemPrompt: ""
            ) {
                return result.lowercased().contains("pipeline")
            }
        }
        return false
    }

    // (sendMessage本体のクロージングブレースはここに続く)
    // MARK: - Cancel generation
    func cancelGeneration() {
        inferenceTask?.cancel()
        inferenceTask = nil
        isGenerating = false
        addSystemMessage(self.t("⏹ Inference aborted", "⏹ 推論を中断しました"))
    }

    // MARK: - Hybrid Engine (Privacy Shield / Cloud Direct)

    private func runHybrid(instruction: String) async {
        let context = selectedFileContent.isEmpty ? nil : selectedFileContent
        let contextFile = selectedFile
        await MainActor.run { self.privacySteps = [] }

        let snap_mode     = inferenceMode
        let snap_provider = cloudProvider
        let snap_model    = activeOllamaModel
        let snap_status   = modelStatus

        // ── Privacy Shield / Paranoia Mode: PrivacyGateway (Phase 1 + Phase 2 + JCross) ──
        // cloudDirect: HybridEngine (マスキングなし、直接送信)
        // paranoiaMode: PrivacyGateway → ParanoiaEngine (AST-surgical phase 3)
        if (snap_mode == .privacyShield || snap_mode == .paranoiaMode),
           let fileContent = context, let fileName = contextFile?.lastPathComponent {

            let snap_gemma = gemmaSemanticMaskingEnabled

            let gatewayResult = await PrivacyGateway.shared.processWithGateway(
                instruction: instruction,
                fileContent: fileContent,
                fileName: fileName,
                fileURL: contextFile,
                modelStatus: snap_status,
                activeModel: snap_model,
                provider: snap_provider,
                cortex: cortex,
                useGemmaSemanticMasking: snap_gemma
            ) { [weak self] step in
                guard let self else { return }
                await MainActor.run {
                    self.privacySteps.append(step)
                    self.messages.append(ChatMessage(role: .system, content: step))
                }
            }

            await MainActor.run {
                isGenerating = false
                // GatewayStats → MaskingStats 変換 (UI表示用)
                lastMaskingStats = MaskingStats(
                    functions: gatewayResult.maskingStats.phase1RegexMasked,
                    classes:   0,
                    variables: gatewayResult.maskingStats.phase2SemanticMasked,
                    strings:   gatewayResult.maskingStats.secretsBlocked,
                    paths:     gatewayResult.maskingStats.pathsProtected
                )
                messages.append(ChatMessage(role: .assistant, content: gatewayResult.explanation))
                if let code = gatewayResult.restoredCode, !code.isEmpty, let fileURL = contextFile {
                    let diff = FileDiff(
                        fileURL: fileURL,
                        originalContent: selectedFileContent,
                        modifiedContent: code,
                        hunks: DiffEngine.compute(original: selectedFileContent, modified: code)
                    )
                    if operationMode == .aiPriority { autoApplyDiff(diff) }
                    else { pendingDiff = diff; showDiff = true }
                }
            }
            return
        }

        // ── Cloud Direct (or no file selected in Shield mode): HybridEngine ──
        let result = await HybridEngine.shared.process(
            instruction: instruction,
            fileContent: context,
            fileName: contextFile?.lastPathComponent,
            fileURL: contextFile,
            mode: snap_mode,
            modelStatus: snap_status,
            activeOllamaModel: snap_model,
            cloudProvider: snap_provider,
            cortex: cortex
        ) { [weak self] step in
            guard let self else { return }
            await MainActor.run {
                self.privacySteps.append(step)
                self.messages.append(ChatMessage(role: .system, content: step))
            }
        }

        await MainActor.run {
            isGenerating = false
            lastMaskingStats = result.maskingStats
            let rawContent = result.explanation
            // Strip artifact tags from chat display
            let displayContent = ArtifactParser.stripArtifactTags(from: rawContent)
            messages.append(ChatMessage(role: .assistant, content: displayContent))

            // Artifact detection
            if let artifact = ArtifactParser.extract(from: rawContent) {
                ingestArtifact(artifact)
            }

            if let code = result.modifiedCode, !code.isEmpty, let fileURL = contextFile {
                let diff = FileDiff(
                    fileURL: fileURL,
                    originalContent: selectedFileContent,
                    modifiedContent: code,
                    hunks: DiffEngine.compute(original: selectedFileContent, modified: code)
                )
                if operationMode == .aiPriority {
                    // AI Priority: auto-apply without confirmation
                    autoApplyDiff(diff)
                } else {
                    pendingDiff = diff
                    showDiff = true
                }
            }
        }
    }

    /// Apply a diff immediately (AI Priority mode — no confirmation).
    func autoApplyDiff(_ diff: FileDiff) {
        do {
            try diff.modifiedContent.write(to: diff.fileURL, atomically: true, encoding: .utf8)
            selectedFileContent = diff.modifiedContent
            addSystemMessage(self.t("⚡ [AI Priority] Auto-applied diff: \\(diff.fileURL.lastPathComponent)", "⚡ [AI Priority] 差分を自動適用: \\(diff.fileURL.lastPathComponent)"))
        } catch {
            addSystemMessage(self.t("❌ Auto-apply failed: \\(error.localizedDescription)", "❌ 自動適用失敗: \\(error.localizedDescription)"))
        }
        pendingDiff = nil
        showDiff = false
    }

    /// Save artifact and show panel.
    func ingestArtifact(_ artifact: Artifact) {
        currentArtifact = artifact
        artifactHistory.insert(artifact, at: 0)
        showArtifactPanel = true
    }

    // MARK: - Agent Loop (multi-turn, scaffolding)

    private func runAgentLoop(instruction: String,
                              images: [AttachedImage] = [],
                              files: [URL] = [],
                              previousMessages: [ChatMessage] = []) async {
        let context = selectedFileContent.isEmpty ? nil : selectedFileContent
        let contextFile = selectedFile
        let snap_workspace = workspaceURL
        let snap_model = activeOllamaModel
        let snap_status = modelStatus

        // selfFixMode persists until the user explicitly toggles it off.
        // We only snapshot the current value to pass into AgentLoop.
        let snap_selfFix = selfFixMode

        // nano/small モデルはユーザーが operationMode を手動変更していても
        // 常に AI Priority ループで動作させる（VX-Loop + ConfusionDetector が必須なため）
        let snap_operationMode = isNanoSmallModelActive ? .aiPriority : operationMode

        // Build image context suffix so models that read text still see the filename
        var imageContext = ""
        if !images.isEmpty {
            imageContext = "\n\n[Attached images: " +
                images.map { $0.name }.joined(separator: ", ") + "]"
        }
        let fullInstruction = instruction + imageContext

        // ── Per-turn streaming message tracker ─────────────────────────
        // Reset at the start of each agent loop run so previous sessions'
        // stale UUIDs are never carried forward.
        streamingMsgId = nil

        await AgentLoop.shared.run(
            instruction: fullInstruction,
            contextFile: context,
            contextFileName: contextFile?.lastPathComponent,
            workspaceURL: snap_workspace,
            modelStatus: snap_status,
            activeModel: snap_model,
            cortex: cortex,
            selfFixMode: snap_selfFix,
            operationMode: snap_operationMode,
            memoryLayer: sessions.activeSession?.activeLayer ?? .l2,
            chatSessionId: vxChatSessionId,
            previousMessages: previousMessages
        ) { [weak self] event in
            guard let self else { return }
            await MainActor.run {
                switch event {
                case .start:
                    // Reset per-turn streaming ID when a new loop turn starts
                    self.streamingMsgId = nil

                case .streamToken(let token):
                    if let sid = self.streamingMsgId,
                       let idx = self.messages.firstIndex(where: { $0.id == sid }) {
                        // Append token to the tracked streaming message
                        self.messages[idx].content += token
                    } else {
                        // First token of this turn — create a new message and track it
                        let msg = ChatMessage(role: .assistant, content: token)
                        self.streamingMsgId = msg.id
                        self.messages.append(msg)
                    }

                case .thinking(let t):
                    if t > 1 {
                        self.messages.append(ChatMessage(role: .system,
                            content: "<think>\n🔄 Agent loop turn \(t)…\n</think>"))
                    }

                case .aiMessage(let text):
                    if !text.isEmpty {
                        // Detect PATCH_FILE blocks → register in SelfEvolutionEngine
                        let patches = PatchFileParser.extract(from: text)
                        for (relPath, content) in patches {
                            SelfEvolutionEngine.shared.registerPatch(for: relPath, newContent: content)
                        }
                        // Detect <artifact> tags
                        if let artifact = ArtifactParser.extract(from: text) {
                            self.ingestArtifact(artifact)
                        }
                        // Strip patch/artifact markup from display text
                        let stripped = PatchFileParser.strip(
                            from: ArtifactParser.stripArtifactTags(from: text)
                        ).trimmingCharacters(in: .whitespacesAndNewlines)

                        if !stripped.isEmpty {
                            // ── UUID-based anti-duplicate guard ─────────────
                            // Find the exact streaming message by its UUID.
                            // This is safe even when tool/system messages follow
                            // the streaming message ("last role" check would fail).

                            // Snapshot processLog → thinkingLog for post-completion display
                            let logSnapshot = self.logStore.entries.map { e in
                                ChatMessage.ThinkingLogEntry(
                                    timestamp: e.timestamp,
                                    text:      e.text,
                                    kind:      e.kind.rawValue
                                )
                            }

                            if let sid = self.streamingMsgId,
                               let idx = self.messages.firstIndex(where: { $0.id == sid }) {
                                // Finalise in-place with the clean stripped version
                                self.messages[idx].content      = stripped
                                self.messages[idx].thinkingLog  = logSnapshot
                            } else {
                                // No streaming message for this turn → new bubble
                                var msg = ChatMessage(role: .assistant, content: stripped)
                                msg.thinkingLog = logSnapshot
                                self.streamingMsgId = msg.id
                                self.messages.append(msg)
                            }
                            // Reset ID after finalising so next turn starts fresh
                            self.streamingMsgId = nil
                        }
                        // Notify if patches detected
                        if !patches.isEmpty {
                            self.addSystemMessage(self.t("🧬 Detected \(patches.count) patches — check Self-Evolution panel", "🧬 \(patches.count) 個のパッチを検出 — Self-Evolution パネルで確認できます"))
                        }
                    }

                case .toolCall(let call):
                    self.messages.append(ChatMessage(role: .system,
                        content: "<think>\n⚙️ \(call.displayLabel)\n</think>"))
                    if case .runCommand(let cmd) = call.tool {
                        Task { await self.terminal.run(cmd, in: self.workspaceURL, initiatedByAI: true) }
                    }

                case .toolResult(let call):
                    if !call.result.isEmpty {
                        let icon = call.succeeded ? "✅" : "❌"
                        self.messages.append(ChatMessage(role: .system,
                            content: "<think>\n\(icon) \(call.result.prefix(120))\n</think>"))
                    }

                case .workspaceChanged(let url):
                    self.workspaceURL = url
                    self.terminal.workingDirectory = url
                    self.refreshFiles()
                    self.addSystemMessage("📂 Workspace: \(url.lastPathComponent)")

                case .done(let msg, let ws):
                    self.isGenerating = false
                    if let ws = ws, self.workspaceURL == nil {
                        self.workspaceURL = ws
                        self.terminal.workingDirectory = ws
                        self.refreshFiles()
                    }
                    // ── Anti-duplicate guard ────────────────────────────────
                    // If a streaming message exists (streamingMsgId != nil),
                    // the content is already displayed — do NOT add another bubble.
                    // Only show .done text when there was no streaming at all
                    // (e.g. non-streaming model or tool-only turns with no text).
                    if !msg.isEmpty && self.streamingMsgId == nil {
                        let lastContent = self.messages.last?.content ?? ""
                        if !lastContent.hasSuffix(msg) {
                            self.messages.append(ChatMessage(role: .assistant,
                                content: "✅ \(msg)"))
                        }
                    }
                    self.streamingMsgId = nil  // Always reset at turn end

                case .error(let err):
                    self.isGenerating = false
                    self.addSystemMessage("❌ Agent error: \(err)")
                }
            }
        }

        await MainActor.run { self.isGenerating = false }
    }

    // MARK: - Single pass (original behavior)

    // MARK: - Single pass (streaming)
    // Streams tokens directly into the chat bubble in real-time.
    // Tracks tok/s and emits process log entries.

    private func runSinglePass(instruction: String,
                               images: [AttachedImage] = [],
                               files: [URL] = []) async {
        let context = selectedFileContent.isEmpty ? nil : selectedFileContent
        let contextFile = selectedFile

        let snap_status = modelStatus

        // Build prompt (same as AgentEngine)
        let fileSection = context.map { content in
            let name = contextFile?.lastPathComponent ?? "file"
            return "FILE: \(name)\n```\n\(content.prefix(8000))\n```\n\n"
        } ?? ""

        let prompt = """
        You are Verantyx, an expert AI coding assistant running on Apple Silicon.

        \(fileSection)USER: \(instruction)

        ASSISTANT:
        """

        // Reset streaming state
        streamingText = ""
        tokensPerSecond = 0
        var tokenCount = 0
        let startTime = Date()
        var lastPerfLog = Date()

        logProcess("inference start [", kind: .system)
        logProcess("prompt \(prompt.count) chars", kind: .system)

        // Build the stream based on active model — use live settings
        switch snap_status {

        // ── Ollama path (unchanged) ─────────────────────────────────────────
        case .ollamaReady(let model):
            logProcess("Ollama/\(model)  temp=\(temperature)  maxTok=\(maxTokensOllama)", kind: .system)
            let msgId = UUID()
            messages.append(ChatMessage(id: msgId, role: .assistant, content: ""))
            let simpleMessages: [(role: String, content: String)] = [(role: "user", content: prompt)]
            let stream = OllamaClient.shared.streamGenerate(
                model: model,
                messages: simpleMessages,
                maxTokens: maxTokensOllama,
                temperature: temperature
            )
            do {
                // トークンをバッファして ~25fps (40ms) で UI を更新—※messagesの @Published 発火回数を 1/5 に削減
                var tokenBuffer = ""
                var lastUIFlush = Date.distantPast
                for try await event in stream {
                    guard case .token(let token) = event else { continue }
                    tokenCount += 1; totalTokensGenerated += 1
                    tokenBuffer += token
                    let now = Date()
                    let elapsed = now.timeIntervalSince(startTime)
                    // 40ms ごとにバッチフラッシュ（ポーリング連続で同一スレッドなので Date() で OK）
                    if now.timeIntervalSince(lastUIFlush) >= 0.04 {
                        if let idx = self.messages.firstIndex(where: { $0.id == msgId }) {
                            self.messages[idx].content += tokenBuffer
                        }
                        if elapsed > 0.1 { tokensPerSecond = Double(tokenCount) / elapsed }
                        tokenBuffer = ""
                        lastUIFlush = now
                    }
                    if now.timeIntervalSince(lastPerfLog) > 2 {
                        logProcess(String(format: "%.1f tok/s  │  %d tokens",
                                         Double(tokenCount)/max(elapsed,0.001), tokenCount), kind: .perf)
                        lastPerfLog = now
                    }
                }
                // 末尾バッファをフラッシュ
                if !tokenBuffer.isEmpty,
                   let idx = self.messages.firstIndex(where: { $0.id == msgId }) {
                    self.messages[idx].content += tokenBuffer
                }
            } catch { logProcess("stream error: \(error.localizedDescription)", kind: .system) }

            let elapsed1 = Date().timeIntervalSince(startTime)
            inferenceMs = Int(elapsed1 * 1000); tokensPerSecond = Double(tokenCount)/max(elapsed1,0.001)
            logProcess(String(format: "done  %.1f tok/s  │  %d tok  │  %.1fs",
                              tokensPerSecond, tokenCount, elapsed1), kind: .perf)
            let finalContent1 = messages.first(where: { $0.id == msgId })?.content ?? ""
            if agentLoopEnabled {
                let (toolCalls, _) = AgentToolParser.parse(from: finalContent1)
                let executor = AgentToolExecutor()
                for tool in toolCalls {
                    logProcess("\(tool)", kind: .tool)
                    let result = await executor.execute(tool, workspaceURL: workspaceURL)
                    if case .setWorkspace(let path) = tool {
                        let url = URL(fileURLWithPath: path)
                        workspaceURL = url; terminal.workingDirectory = url; refreshFiles()
                    }
                    addSystemMessage(result)
                }
            }

        // ── MLX direct in-process (new) ─────────────────────────────────────
        case .mlxReady:
            let m = activeMlxModel.components(separatedBy: "/").last ?? activeMlxModel
            logProcess("MLX/\(m) (direct)  temp=\(temperature)  maxTok=\(maxTokensMLX)", kind: .system)
            let msgId = UUID()
            messages.append(ChatMessage(id: msgId, role: .assistant, content: ""))
            // Nonisolated counter captured by ref via class box
            let counter = Counter()

            do {
                // MLX: nonisolated バッファ + 40ms ゲートで MainActor dispatch 回数を削減
                // 毎トークンに Task{@MainActor} を作るのは 40tok/s で 40 Tasks/s が生まれ非効率
                final class TokenBatch: @unchecked Sendable {
                    var buffer = ""
                    var lastFlush = Date.distantPast
                    let lock = NSLock()
                }
                let batch = TokenBatch()

                try await MLXRunner.shared.streamGenerateTokens(
                    prompt: prompt,
                    maxTokens: maxTokensMLX,
                    temperature: temperature,
                    onToken: { @Sendable [weak self] piece in
                        guard let self else { return }
                        counter.increment()
                        batch.lock.lock()
                        batch.buffer += piece
                        let shouldFlush = Date().timeIntervalSince(batch.lastFlush) >= 0.04
                        if shouldFlush { batch.lastFlush = Date() }
                        let flushed = shouldFlush ? batch.buffer : ""
                        if shouldFlush { batch.buffer = "" }
                        batch.lock.unlock()

                        guard shouldFlush, !flushed.isEmpty else { return }
                        Task { @MainActor in
                            if let idx = self.messages.firstIndex(where: { $0.id == msgId }) {
                                self.messages[idx].content += flushed
                            }
                            self.totalTokensGenerated += flushed.count  // approximate
                            let elapsed = Date().timeIntervalSince(startTime)
                            if elapsed > 0.1 {
                                self.tokensPerSecond = Double(counter.value) / elapsed
                            }
                        }
                    },
                    onFinish: { @Sendable [weak self] fullText in
                        guard let self else { return }
                        Task { @MainActor in
                            // 残バッファをフラッシュ
                            // NSLock は async コンテキストで使用不可 (Swift 6)。
                            // onFinish は全 onToken 完了後に呼ばれるため、
                            // この時点で concurrent アクセスは発生しない → lock 不要。
                            let remaining = batch.buffer
                            batch.buffer = ""
                            if !remaining.isEmpty,
                               let idx = self.messages.firstIndex(where: { $0.id == msgId }) {
                                self.messages[idx].content += remaining
                            }
                            let elapsed = Date().timeIntervalSince(startTime)
                            self.inferenceMs = Int(elapsed * 1000)
                            self.tokensPerSecond = Double(counter.value) / max(elapsed, 0.001)
                            self.logProcess(String(format: "done  %.1f tok/s  │  %d tok  │  %.1fs",
                                                   self.tokensPerSecond, counter.value, elapsed), kind: .perf)
                            // Agent tool parsing (same as Ollama path)
                            if self.agentLoopEnabled {
                                let (toolCalls, _) = AgentToolParser.parse(from: fullText)
                                let executor = AgentToolExecutor()
                                for tool in toolCalls {
                                    self.logProcess("\(tool)", kind: .tool)
                                    let result = await executor.execute(tool, workspaceURL: self.workspaceURL)
                                    if case .setWorkspace(let path) = tool {
                                        let url = URL(fileURLWithPath: path)
                                        self.workspaceURL = url
                                        self.terminal.workingDirectory = url
                                        self.refreshFiles()
                                    }
                                    self.addSystemMessage(result)
                                }
                            }
                            self.isGenerating = false
                        }
                    }
                )
            } catch {
                logProcess("MLX error: \(error.localizedDescription)", kind: .system)
                messages.append(ChatMessage(role: .assistant,
                    content: "⚠️ MLX error: \(error.localizedDescription)"))
            }

            isGenerating = false
            return

        default:
            messages.append(ChatMessage(role: .assistant,
                content: "⚠️ No model loaded. Load an MLX model or connect Ollama first."))
            isGenerating = false
            return
        }
        isGenerating = false
    }

    // MARK: - Process log helpers

    func logProcess(_ text: String, kind: ProcessLogEntry.Kind) {
        let entry = ProcessLogEntry(timestamp: Date(), text: text, kind: kind)
        Task { @MainActor in
            if self.logStore.entries.count > 500 { self.logStore.entries.removeFirst(100) }
            self.logStore.entries.append(entry)
        }
    }

    func clearProcessLog() { logStore.entries.removeAll() }

    func applyDiff() {
        guard let diff = pendingDiff else { return }
        do {
            try diff.modifiedContent.write(to: diff.fileURL, atomically: true, encoding: .utf8)
            selectedFileContent = diff.modifiedContent
            addSystemMessage("✅ Applied changes to \(diff.fileURL.lastPathComponent)")
        } catch {
            addSystemMessage("❌ Failed to write: \(error.localizedDescription)")
        }
        pendingDiff = nil
        showDiff = false
    }

    func skipDiff() {
        pendingDiff = nil
        showDiff = false
        addSystemMessage("⏭ Changes discarded.")
    }

    // MARK: - Human Mode: File write approval

    /// User tapped "承認" — resume the AgentLoop continuation so the write executes.
    func approveFileWrite() {
        guard let req = pendingFileApproval else { return }
        pendingFileApproval = nil
        req.approve()
        addSystemMessage(self.t("✅ Approved: \\(req.displayFileName)", "✅ 承認しました: \\(req.displayFileName)"))
    }

    /// User tapped "拒否" — resume the AgentLoop continuation with false, skip write.
    func rejectFileWrite() {
        guard let req = pendingFileApproval else { return }
        let name = req.displayFileName
        pendingFileApproval = nil
        req.reject()
        addSystemMessage(self.t("⏸ Rejected: \\(name)", "⏸ 拒否しました: \\(name)"))
    }



    // MARK: - Model actions

    func connectOllama() {
        // Wire CI/CD error → agent auto-reply loop (once)
        registerCIErrorHook()
        Task {
            modelStatus = .connecting
            let models = await OllamaClient.shared.listModels()
            await MainActor.run {
                ollamaModels = models
                if models.contains(activeOllamaModel) {
                    modelStatus = .ollamaReady(model: activeOllamaModel)
                    ToastManager.shared.show("\(activeOllamaModel) ready", icon: "checkmark.circle.fill", color: .green)
                } else if models.contains("gemma4:26b") {
                    activeOllamaModel = "gemma4:26b"
                    modelStatus = .ollamaReady(model: "gemma4:26b")
                    ToastManager.shared.show("gemma4:26b ready", icon: "checkmark.circle.fill", color: .green)
                } else if !models.isEmpty {
                    let m = models.first!
                    activeOllamaModel = m
                    modelStatus = .ollamaReady(model: m)
                    ToastManager.shared.show("\(m) ready", icon: "checkmark.circle.fill", color: .green)
                } else {
                    modelStatus = .error("No Ollama models found")
                    ToastManager.shared.show("No Ollama models. Run: ollama pull gemma4:26b",
                                            icon: "exclamationmark.triangle.fill", color: .orange, duration: 4.5)
                }
            }
        }
    }

    // MARK: - Model Eject (from LoadedModelPanel)

    /// Unload the currently active model, freeing all memory.
    ///
    /// • MLX: releases ModelContainer via MLXRunner.unloadModel() → deinit path frees GPU/ANE.
    /// • Ollama: sends DELETE /api/delete or keep-alive=0 to unload from RAM.
    ///
    /// After ejection, modelStatus → .none and a Deep→Front topology alias is persisted
    /// so the cognitive engine remembers which models have been used.
    func ejectModel() {
        let snap = modelStatus
        switch snap {
        case .mlxReady(let m), .mlxDownloading(let m):
            modelStatus = .none
            addSystemMessage(self.t("⏏ Ejected MLX Model: \(m)", "⏏ MLX モデルをリジェクト: \(m)"))
            Task.detached(priority: .userInitiated) {
                await MLXRunner.shared.unloadModel()
                // Write a topology alias into front/ for future reference
                Task.detached(priority: .utility) {
                    SessionMemoryArchiver.shared.writeDeepAlias(
                        modelId: m,
                        backend: "MLX",
                        kanjiTags: "[技:1.0] [速:0.8] [軽:0.7]"
                    )
                }
            }
        case .ollamaReady(let m):
            modelStatus = .none
            addSystemMessage(self.t("⏏ Ejected Ollama Model: \(m)", "⏏ Ollama モデルをリジェクト: \(m)"))
            let endpoint = ollamaEndpoint   // capture on MainActor before detaching
            Task.detached(priority: .userInitiated) {
                // Ollama: unload via generate API with keep_alive=0
                if let url = URL(string: "\(endpoint)/api/generate") {
                    var req = URLRequest(url: url)
                    req.httpMethod = "POST"
                    req.setValue("application/json", forHTTPHeaderField: "Content-Type")
                    req.httpBody = try? JSONSerialization.data(withJSONObject: [
                        "model": m, "keep_alive": 0
                    ])
                    _ = try? await URLSession.shared.data(for: req)
                }
                Task.detached(priority: .utility) {
                    SessionMemoryArchiver.shared.writeDeepAlias(
                        modelId: m,
                        backend: "Ollama",
                        kanjiTags: "[技:1.0] [通:0.8] [外:0.6]"
                    )
                }
            }
        default:
            // Nothing loaded — just reset
            modelStatus = .none
        }
        // Toast notification
        ToastManager.shared.show(
            self.t("Model ejected", "モデルをリジェクトしました"),
            icon: "eject.fill",
            color: Color(red: 1.0, green: 0.55, blue: 0.2)
        )
    }


    // MARK: - Helpers

    func addSystemMessage(_ text: String) {
        // Only show agent-loop tool events — NOT model load events (those use Toast)
        guard !text.hasPrefix("🟢") && !text.hasPrefix("🔌") else { return }
        messages.append(ChatMessage(role: .system, content: text))
    }

    // MARK: - Settings Persistence (Startup Restore)
    //
    // activeOllamaModel と activeMlxModel は宣言時のデフォルト値として
    // UserDefaults から直接復元される（上記の ={ UserDefaults... }() パターン）。
    // その他の設定も同様に didSet で自動保存されるが、
    // 起動時のデフォルト値が UserDefaults を参照していない項目をここで補完する。

    func loadPersistedSettings() {
        let ud = UserDefaults.standard

        // ── Workspace ──────────────────────────────────────────────────────
        if let path = ud.string(forKey: "last_workspace_path") {
            let url = URL(fileURLWithPath: path)
            var isDir: ObjCBool = false
            if FileManager.default.fileExists(atPath: path, isDirectory: &isDir), isDir.boolValue {
                workspaceURL = url
                terminal.workingDirectory = url
                GatekeeperModeState.shared.configure(workspaceURL: url)
                refreshFiles()
                // ⚠️ L2.5インデックスの起動は VerantyxApp.onAppear (0.3秒後) で一元管理。
                // ここで呼ぶと onAppear 側と二重起動になり MainActor デッドロックが発生する。
            }

        }

        // ── Anthropic ──────────────────────────────────────────────────────
        if let key = ud.string(forKey: "anthropic_api_key"), !key.isEmpty {
            anthropicApiKey = key                       // didSet → AnthropicClient.configure
        }
        if let model = ud.string(forKey: "anthropic_model"), !model.isEmpty {
            activeAnthropicModel = model
        }

        // ── Model config ───────────────────────────────────────────────────
        // temperature/maxTokens/systemPrompt 等は宣言時のデフォルトが UD を見ていない
        // ため、ここで上書きする（didSet による二重保存は無害）。
        if let t = ud.object(forKey: "model_temperature") as? Double { temperature = t }
        if let n = ud.object(forKey: "max_tokens_ollama") as? Int    { maxTokensOllama = n }
        if let n = ud.object(forKey: "max_tokens_mlx") as? Int       { maxTokensMLX = n }
        if let e = ud.string(forKey: "ollama_endpoint"), !e.isEmpty  { ollamaEndpoint = e }
        if let s = ud.string(forKey: "system_prompt"), !s.isEmpty    { systemPrompt = s }

        // ── Toggles ────────────────────────────────────────────────────────
        if let v = ud.object(forKey: "agent_loop_enabled") as? Bool  { agentLoopEnabled = v }
        if let v = ud.object(forKey: "streaming_enabled")  as? Bool  { streamingEnabled = v }
        if let v = ud.object(forKey: "tool_browser")       as? Bool  { toolBrowserEnabled = v }
        if let v = ud.object(forKey: "tool_web_search")    as? Bool  { toolWebSearchEnabled = v }
        if let v = ud.object(forKey: "tool_terminal")      as? Bool  { toolTerminalEnabled = v }
        if let v = ud.object(forKey: "tool_diff")          as? Bool  { toolDiffEnabled = v }
        if let v = ud.object(forKey: "tool_jcross")        as? Bool  { toolJCrossEnabled = v }
        if let v = ud.object(forKey: "gemma_semantic_masking") as? Bool { gemmaSemanticMaskingEnabled = v }

        // ── Modes ──────────────────────────────────────────────────────────
        if let raw = ud.string(forKey: "inference_mode"),
           let m = InferenceMode(rawValue: raw) { inferenceMode = m }
        if let raw = ud.string(forKey: "cloud_provider"),
           let p = CloudProvider(rawValue: raw) { cloudProvider = p }
        if let raw = ud.string(forKey: "operation_mode"),
           let o = OperationMode(rawValue: raw) {
            operationMode = o
            editingMode = o
        }

        // ── Notification ───────────────────────────────────────────────────
        if let v = ud.object(forKey: "notify_diff_apply") as? Bool { notifyOnDiffApply = v }
        if let v = ud.object(forKey: "notify_error")      as? Bool { notifyOnError = v }
    }

    // MARK: - CI/CD Auto-Reply Hook
    //
    // When CIValidationEngine detects a compile error after an AI-generated patch,
    // it broadcasts selfEvolutionCIError. We automatically feed the error digest
    // back to the agent as a new user message, so the agent self-corrects.

    func registerCIErrorHook() {
        NotificationCenter.default.addObserver(
            forName: .selfEvolutionCIError,
            object: nil,
            queue: .main
        ) { [weak self] notification in
            guard let self,
                  let digest = notification.userInfo?["digest"] as? String else { return }

            // Hop to MainActor for all @MainActor-isolated mutations.
            // sendMessage is a sync func that internally spawns a Task — no await needed.
            Task { @MainActor [weak self] in
                guard let self else { return }
                self.messages.append(ChatMessage(
                    role: .system,
                    content: "🔬 CI エラー検出 — AI が自動修正を試みます"
                ))
                self.sendMessage(with: digest)
            }
        }
    }

    /// Subscribe to the [RESTART_IDE] agent event.
    /// Call from VerantyxApp.onAppear once.
    func registerRestartHook() {
        NotificationCenter.default.addObserver(
            forName: .agentRequestsRestart,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            // Wrap in Task { @MainActor } so Swift 6 sees the mutation as actor-safe.
            Task { @MainActor [weak self] in
                self?.showRestartAlert = true
            }
        }
    }

    /// Apply pending patches then quit; rebuild.sh relaunches the app.
    func performRestart() {
        try? SelfEvolutionEngine.shared.applyAllPatches()
        let rebuildScript = NSHomeDirectory() + "/verantyx-cli/VerantyxIDE/rebuild.sh"
        if FileManager.default.fileExists(atPath: rebuildScript) {
            Task.detached {
                let process = Process()
                process.executableURL = URL(fileURLWithPath: "/bin/zsh")
                process.arguments = ["-c", "sleep 0.5 && bash '\(rebuildScript)'"]
                try? process.run()
            }
        }
        NSApplication.shared.terminate(nil)
    }

    var isReady: Bool {
        switch modelStatus {
        case .ready, .ollamaReady, .mlxReady, .bitnetReady: return true
        default: return false
        }
    }

    var statusLabel: String {
        switch modelStatus {
        case .none:                          return "No model"
        case .connecting:                    return "Connecting…"
        case .downloading(let p):            return "Downloading \(Int(p * 100))%"
        case .ready(let n):                  return n
        case .ollamaReady(let m):            return "Ollama: \(m.components(separatedBy: ":").first ?? m)"
        case .anthropicReady(let m, _):      return "Claude: \(m)"
        case .mlxReady(let m):              return "MLX: \(m.components(separatedBy: "/").last ?? m)"
        case .mlxDownloading(let m):        return "⏬ \(m.components(separatedBy: "/").last ?? m)"
        case .bitnetReady(let m):           return "BitNet: \(m)"
        case .error(let e):                  return "Error: \(e)"
        }
    }

    var statusColor: Color {
        switch modelStatus {
        case .ready, .ollamaReady, .mlxReady, .anthropicReady, .bitnetReady: return .green
        case .error:                           return .red
        case .downloading, .connecting,
             .mlxDownloading:                  return .orange
        case .none:                            return .gray
        }
    }


    // MARK: - MLX Actions (Direct in-process — no HTTP server)

    func loadMLXModel(model: String? = nil) {
        let modelId = model ?? activeMlxModel
        modelStatus = .connecting
        mlxServerLogs.removeAll()

        Task {
            do {
                try await MLXRunner.shared.loadModel(id: modelId) { @Sendable log in
                    Task { @MainActor in
                        self.mlxServerLogs.append(log)
                        self.logProcess(log, kind: .system)
                    }
                }
                await MainActor.run {
                    self.modelStatus = .mlxReady(model: modelId)
                    self.activeMlxModel = modelId
                    ToastManager.shared.show(
                        "MLX: \(modelId.components(separatedBy: "/").last ?? modelId) ready 🚀",
                        icon: "cpu",
                        color: Color(red: 0.4, green: 0.85, blue: 0.6)
                    )
                }
            } catch {
                await MainActor.run {
                    self.modelStatus = .error(error.localizedDescription)
                    ToastManager.shared.show(
                        "MLX error: \(error.localizedDescription)",
                        icon: "exclamationmark.triangle.fill",
                        color: .orange, duration: 5
                    )
                }
            }
        }
    }

    /// Legacy alias so old call sites keep compiling.
    @available(*, deprecated, renamed: "loadMLXModel")
    func startMLXServer(model: String? = nil) { loadMLXModel(model: model) }

    func downloadMLXModel(repoId: String) {
        modelStatus = .mlxDownloading(model: repoId)
        mlxServerLogs.removeAll()

        Task {
            do {
                try await MLXRunner.shared.downloadModel(repoId: repoId) { @Sendable log in
                    Task { @MainActor in
                        self.mlxServerLogs.append(log)
                    }
                }
                await MainActor.run {
                    ToastManager.shared.show(
                        "Downloaded: \(repoId.components(separatedBy: "/").last ?? repoId)",
                        icon: "checkmark.circle.fill",
                        color: .green, duration: 4
                    )
                    self.loadMLXModel(model: repoId)
                }
            } catch {
                await MainActor.run {
                    self.modelStatus = .error("Download failed: \(error.localizedDescription)")
                }
            }
        }
    }
}
