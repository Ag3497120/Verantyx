import SwiftUI

/// The chip row sitting directly above the chat input: model selection,
/// auditor toggle, backend badge, operation mode.
///
/// Extracted from `AgentChatView.modelSelectorBar` so it has room to cover
/// all four local backends. Previously the picker only knew MLX and Ollama,
/// which meant:
///   - a loaded JGEN model had to be selected from Settings and then showed
///     up in the badge as "MLX" (the badge only distinguished Ollama vs
///     everything-else)
///   - BitNet model selection lived in `ModelPickerView`, a 600-line view
///     with zero call sites -- users could not reach it at all
/// Both are now reachable from here. Stop/Send stay in `AgentChatView` so
/// this file never touches `inputText`/`sendMessage`.
struct ModelSelectorBarView: View {
    @EnvironmentObject var app: AppState
    @ObservedObject private var jgen = JGenConverter.shared
    @ObservedObject private var bitnet = BitNetEngineManager.shared

    /// Models Ollama currently holds in VRAM, with an eject action. Carried
    /// over from the deleted `ModelPickerView` -- it was the only way to see
    /// or free VRAM, and that view had no call sites, so this capability was
    /// unreachable in practice.
    @State private var loadedModels: [OllamaClient.RunningModel] = []
    @State private var ejectingModel: String?
    @State private var showVRAM = false

    @ObservedObject private var council = CouncilSettingsStore.shared
    @ObservedObject private var cloudCatalog = CloudModelCatalog.shared
    @State private var agentSDKAvailable = false
    @State private var showJGenOptions = false
    @State private var showModelRoles = false
    /// LM Studio's Local Server can be off while the app itself is running,
    /// and it can be started at any time after the IDE. A single probe when the
    /// bar appears therefore answers a question whose answer keeps changing —
    /// and because the section was hidden whenever the answer was "no", the
    /// user saw LM Studio running and no way to select it, with nothing on
    /// screen saying why or offering to fix it.
    @State private var lmStudioModels: [String] = []
    @State private var lmStudioState: LMStudioAvailability = .unknown
    @State private var lmStudioStarting = false
    @State private var showPendingToolCalls = false
    @State private var showReasoningTimeline = false

    /// One selectable entry across every local backend. A plain `Picker` over
    /// `String` (what this used to be) can't express per-row spinners, size
    /// subtitles, or rows disabled with an explanation -- JGEN needs all
    /// three, so this is a `Menu` over a typed value instead.
    private enum SelectableModel: Hashable {
        case mlx(String)
        case ollama(String)
        case bitnet(String)
        case jgen(String)
        case lmStudio(String)
        /// A model served by a cloud provider. Keys were configurable long
        /// before this existed, so the API could be set up and then never
        /// chosen — the menu simply had no row for it.
        case cloud(CloudProvider, String)
        /// Claude via the Agent SDK, on the user's Claude Code login. No API
        /// key is involved, which is why it is not a `.cloud` case.
        case claudeAgent(String)
    }

    private var currentSelection: SelectableModel? {
        switch app.modelStatus {
        case .mlxReady(let m), .mlxDownloading(let m): return .mlx(m)
        case .ollamaReady(let m): return .ollama(m)
        case .bitnetReady(let m): return .bitnet(m)
        case .jcrossReady(let m): return .jgen(m)
        case .lmStudioReady(let m): return .lmStudio(m)
        case .anthropicReady(let m, _): return .cloud(app.activeCloudProvider, m)
        case .claudeAgentReady(let m): return .claudeAgent(m)
        default: return nil
        }
    }

    private var currentLabel: String {
        switch currentSelection {
        case .mlx(let m), .ollama(let m), .bitnet(let m), .jgen(let m), .lmStudio(let m):
            return m
        case .cloud(_, let m), .claudeAgent(let m):
            return m
        case nil:
            // Nothing loaded yet -- fall back to whatever Gatekeeper has
            // configured, matching the old picker's behavior.
            let cmd = GatekeeperModeState.shared.commanderModel
            return cmd.contains("mlx") ? app.activeMlxModel : app.getOllamaModel()
        }
    }

    private func select(_ model: SelectableModel) {
        switch model {
        case .mlx(let m):
            GatekeeperModeState.shared.commanderModel = m
            app.activeMlxModel = m
            app.loadMLXModel(model: m)
        case .ollama(let m):
            GatekeeperModeState.shared.commanderModel = m
            app.setOllamaModel(m)
            app.connectOllama()
        case .bitnet(let name):
            if let cfg = bitnet.installedConfigs.first(where: { $0.modelName == name }) {
                bitnet.activate(cfg)
                app.addSystemMessage("⚡ BitNet \(name) を有効化しました")
            }
        case .jgen(let name):
            app.loadJGenModel(name)
        case .lmStudio(let name):
            GatekeeperModeState.shared.commanderModel = name
            app.activeLMStudioModel = name
            app.modelStatus = .lmStudioReady(model: name)
        case .cloud(let provider, let name):
            GatekeeperModeState.shared.commanderModel = name
            app.selectCloudModel(provider: provider, model: name)
        case .claudeAgent(let name):
            GatekeeperModeState.shared.commanderModel = name
            app.selectClaudeAgentModel(name)
        }
    }

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                // The Gatekeeper chip is the door to every non-chat
                // surface: a menu whose picks swap the CENTER surface
                // (MCP/model settings, Vera-a settings, growth,
                // self-evolution) — plus the Vera-a mode switch it always
                // carried. Selections land in HumanPriorityModeView
                // through `app.fullSurface`, the one route these screens
                // have.
                Menu {
                    Button(app.isVeraAMode
                           ? app.t("Leave Vera-a mode", "Vera-aモードを終了")
                           : app.t("Vera-a mode (audit screen)", "Vera-aモード（監査画面）")) {
                        app.fullSurface = nil
                        app.isVeraAMode.toggle()
                    }
                    Divider()
                    // Each surface takes the FULL window (like the Vera-a
                    // audit screen), not a pane beside the chat.
                    Button(app.t("MCP / external operation", "MCP・外部運用")) {
                        app.isVeraAMode = false
                        app.fullSurface = .mcp
                    }
                    Button(app.t("Model / API settings", "モデル・API設定")) {
                        app.showSettingsRequested = true
                    }
                    Button(app.t("Vera-a settings", "Vera-a設定")) {
                        app.isVeraAMode = false
                        app.fullSurface = .veraSettings
                    }
                    Button(app.t("Learning / Growth", "学習（成長）")) {
                        app.isVeraAMode = false
                        app.fullSurface = .growth
                    }
                    Button(app.t("Self-evolution", "自己進化")) {
                        app.isVeraAMode = false
                        app.fullSurface = .evolution
                    }
                } label: {
                    Text(app.isVeraAMode ? "Vera-a" : "Gatekeeper")
                        .font(.system(size: 11, weight: .bold))
                        .foregroundStyle(app.isVeraAMode ? Color.purple : Color.green)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 4)
                        .background((app.isVeraAMode ? Color.purple : Color.green).opacity(0.1))
                        .cornerRadius(4)
                }
                .menuStyle(.borderlessButton)
                .menuIndicator(.hidden)
                .fixedSize()
                .help(app.t("Mode & surfaces: Vera-a, MCP, model settings, learning",
                             "モードと画面: Vera-a・MCP・モデル設定・学習"))

                modelMenu

                // ── Model roles: 会話用 / 記憶用 / Vera-a用 ──────────
                Button {
                    showModelRoles = true
                } label: {
                    Image(systemName: "square.stack.3d.up")
                        .font(.system(size: 11))
                        .foregroundStyle(Color(red: 0.55, green: 0.8, blue: 1.0))
                }
                .buttonStyle(.plain)
                .help(app.t("Model roles: chat / memory organ / Vera-a composer",
                             "モデルの役割: 会話用・記憶用・Vera-a用"))
                .popover(isPresented: $showModelRoles) { modelRolesPopover }

                // JGEN-only: the memory sources and layer knobs only mean
                // anything when the hidden-state engine is actually driving
                // the model, so this chip appears only for .jcrossReady.
                if case .jcrossReady = app.modelStatus {
                    Button {
                        showJGenOptions = true
                    } label: {
                        Image(systemName: "slider.horizontal.3")
                            .font(.system(size: 11))
                            .foregroundStyle(Color(red: 1.0, green: 0.72, blue: 0.35))
                    }
                    .buttonStyle(.plain)
                    .help(app.t("JGEN memory & layer options", "JGENの記憶・層オプション"))
                    .popover(isPresented: $showJGenOptions) { jgenOptionsPopover }
                    .sheet(isPresented: $showPendingToolCalls) { PendingToolCallsView() }
                    .sheet(isPresented: $showReasoningTimeline) { ReasoningTimelineView() }
                }

                Divider().frame(height: 16).opacity(0.5)

                auditorControls

                Divider().frame(height: 16).opacity(0.5)

                backendBadge

                if app.isMultimodalModel {
                    Text("👁")
                        .font(.system(size: 10))
                        .help("Multimodal — images supported")
                }

                Divider().frame(height: 16).opacity(0.5)

                // ── Operation Mode Picker ──
                // Gatekeeper is deliberately absent here: it is retired
                // from the normal workflow (its IR round-trip costs
                // accuracy for a risk enterprises now cover by contract).
                // The mode still exists in the enum and remains settable
                // via `applySetting(key: "operation_mode", ...)` so any
                // user who had it enabled keeps a working escape hatch.
                Picker("", selection: $app.operationMode) {
                    Text(OperationMode.automatic.displayName).tag(OperationMode.automatic)
                    Text(OperationMode.detailed.displayName).tag(OperationMode.detailed)
                }
                .labelsHidden()
                .frame(width: 100)
                .help("Agent Operation Mode")

                RateLimitStatusView()
            }
        }
        // The one row that must never disappear: at the 900×600 minimum the
        // surrounding VStack used to squeeze this to zero height, hiding the
        // model picker entirely. A fixed height + layoutPriority makes the
        // TRANSCRIPT give way instead; horizontal overflow already scrolls.
        .frame(height: 34)
        .layoutPriority(1)
        .task {
            // BitNet models are discovered from disk sidecars; without this
            // the section would stay empty until the user opened Settings.
            if bitnet.installedConfigs.isEmpty { await bitnet.checkInstallation() }
            jgen.refreshConvertedModelsList()
            // Is the claude CLI actually installed? Asked once, so the
            // subscription section appears only when it can be selected.
            agentSDKAvailable = await ClaudeAgentSDKClient.shared.probe()?.usable ?? false
            // Cheap and bounded (2 s timeout): if LM Studio's Local Server is
            // off this returns nothing and the section simply does not appear,
            // rather than showing a section that fails on click.
            await refreshLMStudio(autoStart: true)
            // The server may come up after the IDE did. Keep looking — slowly
            // while it is down, slower still once it is up. A refused
            // connection returns immediately, so this costs almost nothing.
            while !Task.isCancelled {
                try? await Task.sleep(
                    nanoseconds: lmStudioState == .ready ? 30_000_000_000 : 6_000_000_000)
                if Task.isCancelled { break }
                await refreshLMStudio(autoStart: false)
            }
        }
    }

    /// Ask LM Studio what it can do, and — when the only thing missing is the
    /// server — start it. The CLI that starts it ships inside LM Studio itself,
    /// so sending the user to a menu to do by hand what this can do is friction
    /// for nothing. Auto-start is attempted on the first probe only; the
    /// periodic re-probe never starts anything the user has since stopped.
    private func refreshLMStudio(autoStart: Bool) async {
        func adopt(_ diagnosis: LMStudioClient.Diagnosis) async {
            switch diagnosis {
            case .ready:
                lmStudioModels = await LMStudioClient.shared.listModels()
                lmStudioState = lmStudioModels.isEmpty ? .noModels : .ready
            case .noModels:
                lmStudioModels = []
                lmStudioState = .noModels
            case .notInstalled:
                lmStudioModels = []
                lmStudioState = .notInstalled
            case .serverOff(let canStart):
                lmStudioModels = []
                lmStudioState = .serverOff(canStart: canStart)
            case .badEndpoint:
                // Reachable but the wrong shape — a hand-edited endpoint. Not
                // something starting the server fixes, so it is reported as off
                // with the start offer intact rather than silently retried.
                lmStudioModels = []
                lmStudioState = .serverOff(canStart: LMStudioClient.lmsBinary() != nil)
            }
        }

        await adopt(await LMStudioClient.shared.diagnose())

        guard autoStart, !lmStudioStarting,
              case .serverOff(let canStart) = lmStudioState, canStart else { return }
        lmStudioStarting = true
        _ = await LMStudioClient.shared.startServer()
        lmStudioStarting = false
        await adopt(await LMStudioClient.shared.diagnose())
    }

    /// Always present, even with nothing to offer. A section that disappears
    /// when the answer is "no" leaves the user with no way to tell a missing
    /// install from a stopped server from an empty one — three different
    /// problems with three different fixes.
    @ViewBuilder
    private var lmStudioSection: some View {
        Section("LM Studio (Local Server)") {
            if !lmStudioModels.isEmpty {
                ForEach(lmStudioModels, id: \.self) { m in
                    Button(m) { select(.lmStudio(m)) }
                }
            } else {
                switch lmStudioState {
                case .unknown, .ready:
                    Button(app.t("Checking…", "確認中…")) {}.disabled(true)
                case .noModels:
                    Button(app.t("No model loaded — load one in LM Studio",
                                 "モデル未読込 — LM Studio で読み込んでください")) {}
                        .disabled(true)
                case .serverOff(let canStart) where canStart:
                    Button(lmStudioStarting
                           ? app.t("Starting server…", "サーバーを起動中…")
                           : app.t("Start Local Server", "ローカルサーバーを起動")) {
                        Task { await refreshLMStudio(autoStart: true) }
                    }
                    .disabled(lmStudioStarting)
                case .serverOff:
                    Button(app.t("Server off — LM Studio ▸ Developer ▸ Start Server",
                                 "サーバー停止中 — LM Studio ▸ Developer ▸ Start Server")) {}
                        .disabled(true)
                case .notInstalled:
                    Button(app.t("LM Studio not found", "LM Studio が見つかりません")) {}
                        .disabled(true)
                }
            }
        }
    }

    // MARK: - Model roles popover (会話用 / 記憶用 / Vera-a用)

    @ViewBuilder
    private var modelRolesPopover: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(app.t("Model roles", "モデルの役割"))
                .font(.system(size: 12, weight: .bold))

            // 会話用 — the same menu as the bar, reused.
            HStack(spacing: 8) {
                Text(app.t("Chat", "会話用"))
                    .font(.system(size: 11)).frame(width: 70, alignment: .leading)
                modelMenu
            }

            // 記憶用 — loads the ENGINE only; the chat backend stays put.
            HStack(spacing: 8) {
                Text(app.t("Memory", "記憶用"))
                    .font(.system(size: 11)).frame(width: 70, alignment: .leading)
                Menu {
                    ForEach(jgen.convertedModels, id: \.self) { name in
                        Button(name) { selectMemoryOrgan(name) }
                            .disabled(!jgen.isArchSupported(name))
                    }
                    if jgen.convertedModels.isEmpty {
                        Text(app.t("No converted JGEN — convert one in MCP / external operation",
                                   "変換済みJGENなし — MCP・外部運用で変換してください"))
                    }
                } label: {
                    Text(app.memoryOrganModel.isEmpty
                         ? app.t("(pin decides)", "（ピン任せ）")
                         : app.memoryOrganModel)
                        .font(.system(size: 10, design: .monospaced))
                        .lineLimit(1).truncationMode(.middle)
                }
                .menuStyle(.borderlessButton)
                .frame(maxWidth: 220, alignment: .leading)
            }
            Text(app.t(
                "Small JGEN recommended (autoloads at launch, ≤9 GB). Loads the engine only — chat is untouched. Note: JGEN chat shares this one engine slot.",
                "小型JGEN推奨（起動時に自動ロード・9GB以下）。エンジンのみロードし、会話モデルには触れません。注: 会話にJGENを使う場合はこの1エンジンを共有します。"
            ))
            .font(.system(size: 9)).foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)

            // Vera-a用 — who composes under the verdict.
            HStack(spacing: 8) {
                Text("Vera-a")
                    .font(.system(size: 11)).frame(width: 70, alignment: .leading)
                Menu {
                    Button(app.t("Follow chat model (auto)", "会話用に従う（自動）")) {
                        app.veraAComposerModel = "auto"
                    }
                    if !lmStudioModels.isEmpty {
                        Section("LM Studio") {
                            ForEach(lmStudioModels, id: \.self) { m in
                                Button(m) { app.veraAComposerModel = "lmstudio:\(m)" }
                            }
                        }
                    }
                    if !app.ollamaModels.isEmpty {
                        Section("Ollama") {
                            ForEach(app.ollamaModels, id: \.self) { m in
                                Button(m) { app.veraAComposerModel = "ollama:\(m)" }
                            }
                        }
                    }
                } label: {
                    Text(app.veraAComposerModel == "auto"
                         ? app.t("auto (chat model)", "自動（会話用と同じ）")
                         : app.veraAComposerModel
                             .replacingOccurrences(of: "lmstudio:", with: "LM Studio: ")
                             .replacingOccurrences(of: "ollama:", with: "Ollama: "))
                        .font(.system(size: 10, design: .monospaced))
                        .lineLimit(1).truncationMode(.middle)
                }
                .menuStyle(.borderlessButton)
                .frame(maxWidth: 220, alignment: .leading)
            }
            Text(app.t(
                "Composes the conversational part of Vera-a mode, under the verbatim verdict.",
                "Vera-aモードで型付き判定の下に会話文を合成するモデルです。"
            ))
            .font(.system(size: 9)).foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)
        }
        .padding(14)
        .frame(width: 330)
    }

    /// Loads the chosen JGEN as the memory organ — engine only, chat
    /// backend untouched. The store pin still guards writes: picking a
    /// model that differs from an existing pin surfaces the notice
    /// instead of mixing spaces.
    private func selectMemoryOrgan(_ name: String) {
        app.memoryOrganModel = name
        Task {
            do {
                try await JCrossChatManager.shared.load(modelFileName: name)
                await MainActor.run {
                    app.addSystemMessage(app.t(
                        "🧠 Memory organ loaded: \(name)",
                        "🧠 記憶器官をロード: \(name)"))
                }
            } catch {
                await MainActor.run {
                    app.addSystemMessage(app.t(
                        "❌ Memory organ load failed: \(error.localizedDescription)",
                        "❌ 記憶器官のロード失敗: \(error.localizedDescription)"))
                }
            }
        }
    }

    // MARK: - Model menu

    /// Claude on the user's existing Claude Code subscription login. Shown
    /// only when the CLI is actually installed — the row would otherwise
    /// promise something that fails on selection.
    @ViewBuilder
    private var agentSDKSection: some View {
        if agentSDKAvailable {
            Section("Claude Agent SDK（サブスク）") {
                ForEach(ClaudeAgentSDKClient.models, id: \.self) { m in
                    Button(m) { select(.claudeAgent(m)) }
                }
            }
        }
    }

    /// Cloud providers with a key configured. Listing one without a key would
    /// offer a choice that fails the moment it is used.
    @ViewBuilder
    private var cloudSections: some View {
        ForEach(configuredProviders, id: \.self) { provider in
            Section(provider.rawValue) {
                ForEach(cloudModels(provider), id: \.self) { m in
                    Button(m) { select(.cloud(provider, m)) }
                }
            }
        }
    }

    private var configuredProviders: [CloudProvider] {
        CloudProvider.allCases.filter { cloudCatalog.hasKey($0) }
    }

    private func cloudModels(_ p: CloudProvider) -> [String] {
        Array(cloudCatalog.options(for: p, including: p.defaultModel).prefix(40))
    }

    private var modelMenu: some View {
        Menu {
            if !MLXRunner.popularModels.isEmpty {
                Section("MLX (Native)") {
                    ForEach(MLXRunner.popularModels) { m in
                        Button(m.displayName) { select(.mlx(m.id)) }
                    }
                }
            }
            if !app.ollamaModels.isEmpty {
                Section("Ollama (Local)") {
                    ForEach(app.ollamaModels, id: \.self) { m in
                        Button(m) { select(.ollama(m)) }
                    }
                }
            }
            if !bitnet.installedConfigs.isEmpty {
                Section("BitNet (1-bit)") {
                    ForEach(bitnet.installedConfigs, id: \.modelName) { cfg in
                        Button(cfg.modelName) { select(.bitnet(cfg.modelName)) }
                    }
                }
            }
            if !jgen.convertedModels.isEmpty {
                Section("JGEN (hidden-state)") {
                    ForEach(jgen.convertedModels, id: \.self) { name in
                        // Architectures the Rust engine can't run forward
                        // (hybrid SSM etc.) still convert as a static weight
                        // lexicon, so they appear here but must not be
                        // loadable for chat -- same rule and wording as the
                        // JGEN settings section.
                        Button(name) { select(.jgen(name)) }
                            .disabled(!jgen.isArchSupported(name))
                    }
                }
            }
            lmStudioSection
            agentSDKSection
            cloudSections
            if app.ollamaModels.isEmpty && jgen.convertedModels.isEmpty && bitnet.installedConfigs.isEmpty {
                Section("Ollama (Not Connected)") {
                    Button("gemma4:26b") { select(.ollama("gemma4:26b")) }
                }
            }
        } label: {
            HStack(spacing: 4) {
                if app.jgenLoadingModel != nil {
                    ProgressView().controlSize(.mini)
                }
                Text(currentLabel)
                    .font(.system(size: 11, design: .monospaced))
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
            .frame(minWidth: 90, maxWidth: 170, alignment: .leading)
        }
        .menuStyle(.borderlessButton)
        .help(app.jgenLoadError.map { "JGEN load failed: \($0)" }
              ?? app.t("Select a model (MLX / Ollama / BitNet / JGEN)",
                       "モデルを選択 (MLX / Ollama / BitNet / JGEN)"))
    }

    // MARK: - Auditor

    @ViewBuilder
    private var auditorControls: some View {
        Toggle(isOn: $app.isAuditorEnabled) {
            Text(L("Auditor", "監視 (Auditor)"))
                .font(.system(size: 11, weight: .bold))
                .foregroundStyle(app.isAuditorEnabled ? Color.yellow : Color.gray)
        }
        .toggleStyle(.checkbox)

        if app.isAuditorEnabled {
            if app.ollamaModels.isEmpty {
                TextField("llama3.1:8b", text: $app.activeAuditorModel)
                    .textFieldStyle(.roundedBorder)
                    .font(.system(size: 11, design: .monospaced))
                    .frame(width: 110)
            } else {
                Picker("", selection: $app.activeAuditorModel) {
                    ForEach(app.ollamaModels, id: \.self) { m in
                        Text(m).tag(m)
                    }
                }
                .labelsHidden()
                .frame(width: 120)
            }
        }
    }

    // MARK: - Backend badge

    /// Previously this only asked "is it Ollama?" and labeled everything else
    /// "MLX", so a loaded JGEN or BitNet model was actively mislabeled.
    private var backendBadge: some View {
        let (label, color): (String, Color) = {
            switch app.modelStatus {
            case .ollamaReady:
                return ("OLLAMA", Color(red: 0.45, green: 0.9, blue: 0.6))
            case .mlxReady, .mlxDownloading:
                return ("MLX", Color(red: 0.65, green: 0.5, blue: 1.0))
            case .bitnetReady:
                return ("BITNET", Color(red: 0.4, green: 0.75, blue: 1.0))
            case .jcrossReady:
                return ("JGEN", Color(red: 1.0, green: 0.72, blue: 0.35))
            case .claudeAgentReady:
                return ("AGENT SDK", Color(red: 0.85, green: 0.55, blue: 0.95))
            case .lmStudioReady:
                return ("LMSTUDIO", Color(red: 0.35, green: 0.8, blue: 0.85))
            case .anthropicReady:
                return ("API", Color(red: 0.9, green: 0.6, blue: 0.4))
            case .ready:
                return ("LOCAL", Color(red: 0.7, green: 0.7, blue: 0.75))
            case .connecting, .downloading:
                return ("…", Color(red: 0.6, green: 0.6, blue: 0.65))
            case .error:
                return ("ERROR", Color(red: 0.95, green: 0.45, blue: 0.45))
            case .none:
                return ("—", Color(red: 0.5, green: 0.5, blue: 0.55))
            }
        }()
        return Button {
            showVRAM = true
            Task { loadedModels = await OllamaClient.shared.loadedModels() }
        } label: {
            Text(label)
                .font(.system(size: 10, weight: .bold, design: .monospaced))
                .foregroundStyle(Color(red: 0.15, green: 0.15, blue: 0.18))
                .padding(.horizontal, 6).padding(.vertical, 2)
                .background(color, in: RoundedRectangle(cornerRadius: 3))
        }
        .buttonStyle(.plain)
        .help(app.t("Active backend — click for VRAM usage",
                    "使用中のバックエンド — クリックでVRAM使用状況"))
        .popover(isPresented: $showVRAM) { vramPopover }
    }

    private var vramPopover: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Label(app.t("Loaded in VRAM", "VRAMに読み込み中"), systemImage: "memorychip")
                    .font(.system(size: 11, weight: .semibold))
                Spacer()
                Button {
                    Task { loadedModels = await OllamaClient.shared.loadedModels() }
                } label: {
                    Image(systemName: "arrow.clockwise").font(.system(size: 10))
                }
                .buttonStyle(.plain)
            }

            if loadedModels.isEmpty {
                Text(app.t("No models currently held in VRAM.",
                           "現在VRAMに保持されているモデルはありません。"))
                    .font(.system(size: 10))
                    .foregroundStyle(.secondary)
            } else {
                ForEach(loadedModels, id: \.name) { running in
                    let isActive = app.activeOllamaModel == running.name
                    HStack(spacing: 8) {
                        Circle().fill(isActive ? Color.green : Color.orange)
                            .frame(width: 6, height: 6)
                        VStack(alignment: .leading, spacing: 1) {
                            Text(running.name)
                                .font(.system(size: 10, design: .monospaced)).lineLimit(1)
                            Text(String(format: "%.2f GB", running.sizeGB))
                                .font(.system(size: 9)).foregroundStyle(.tertiary)
                        }
                        Spacer()
                        Button {
                            Task { await eject(running.name) }
                        } label: {
                            if ejectingModel == running.name {
                                ProgressView().controlSize(.mini)
                            } else {
                                Image(systemName: "eject.fill").font(.system(size: 10))
                            }
                        }
                        .buttonStyle(.plain)
                        .disabled(ejectingModel != nil || isActive)
                        .help(isActive
                              ? app.t("Cannot unload the active model", "アクティブなモデルはアンロードできません")
                              : app.t("Unload from VRAM", "VRAMからアンロード"))
                    }
                    .padding(.horizontal, 6).padding(.vertical, 4)
                    .background(RoundedRectangle(cornerRadius: 5).fill(Color.orange.opacity(0.07)))
                }
            }
        }
        .padding(12)
        .frame(width: 280)
    }

    // MARK: - JGEN options (4-layer)

    private var jgenOptionsPopover: some View {
        JGenVeraSettingsPanelView(
            showPendingToolCalls: $showPendingToolCalls,
            showReasoningTimeline: $showReasoningTimeline,
            onDismiss: { showJGenOptions = false }
        )
        .frame(width: 330, height: 520)
    }

    @MainActor
    private func eject(_ model: String) async {
        ejectingModel = model
        let ok = await OllamaClient.shared.unloadModel(model)
        ejectingModel = nil
        if ok {
            app.addSystemMessage("⏏️ Unloaded \(model) from VRAM")
            if app.activeOllamaModel == model { app.modelStatus = .none }
        } else {
            app.addSystemMessage("⚠️ Failed to unload \(model)")
        }
        loadedModels = await OllamaClient.shared.loadedModels()
    }
}


/// What LM Studio can currently do for us. Kept apart from the model list so
/// "no models" and "no server" stay distinguishable — they read the same in an
/// empty array and need opposite fixes.
private enum LMStudioAvailability: Equatable {
    case unknown
    case notInstalled
    case serverOff(canStart: Bool)
    case noModels
    case ready
}
