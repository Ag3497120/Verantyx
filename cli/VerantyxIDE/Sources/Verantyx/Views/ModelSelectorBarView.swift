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
    @State private var showJGenOptions = false
    /// LM Studio's server is not started automatically, so this stays empty --
    /// and the section stays hidden -- until the user turns it on. Refreshed
    /// when the bar appears rather than polled.
    @State private var lmStudioModels: [String] = []
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
    }

    private var currentSelection: SelectableModel? {
        switch app.modelStatus {
        case .mlxReady(let m), .mlxDownloading(let m): return .mlx(m)
        case .ollamaReady(let m): return .ollama(m)
        case .bitnetReady(let m): return .bitnet(m)
        case .jcrossReady(let m): return .jgen(m)
        case .lmStudioReady(let m): return .lmStudio(m)
        default: return nil
        }
    }

    private var currentLabel: String {
        switch currentSelection {
        case .mlx(let m), .ollama(let m), .bitnet(let m), .jgen(let m), .lmStudio(let m):
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
        }
    }

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                // Milestone T: tap to switch into Vera-a mode (chat
                // full-screen + a feature side panel, no file browser --
                // see HumanPriorityModeView.veraAModeLayout). Label/color
                // swap is the only visual change; nothing else in this
                // bar's behavior differs based on the mode.
                Button {
                    app.isVeraAMode.toggle()
                } label: {
                    Text(app.isVeraAMode ? "Vera-a" : "Gatekeeper")
                        .font(.system(size: 11, weight: .bold))
                        .foregroundStyle(app.isVeraAMode ? Color.purple : Color.green)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 4)
                        .background((app.isVeraAMode ? Color.purple : Color.green).opacity(0.1))
                        .cornerRadius(4)
                }
                .buttonStyle(.plain)
                .help(app.t("Switch to Vera-a mode (full-screen chat + feature panel)",
                             "Vera-aモードへ切り替え(チャット全画面+機能パネル)"))

                modelMenu

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
        .task {
            // BitNet models are discovered from disk sidecars; without this
            // the section would stay empty until the user opened Settings.
            if bitnet.installedConfigs.isEmpty { await bitnet.checkInstallation() }
            jgen.refreshConvertedModelsList()
            // Cheap and bounded (2 s timeout): if LM Studio's Local Server is
            // off this returns nothing and the section simply does not appear,
            // rather than showing a section that fails on click.
            lmStudioModels = await LMStudioClient.shared.listModels()
        }
    }

    // MARK: - Model menu

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
            if !lmStudioModels.isEmpty {
                Section("LM Studio (Local Server)") {
                    ForEach(lmStudioModels, id: \.self) { m in
                        Button(m) { select(.lmStudio(m)) }
                    }
                }
            }
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
            .frame(width: 170, alignment: .leading)
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
            Text("監視 (Auditor)")
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
