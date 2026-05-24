import SwiftUI

// MARK: - ModelPickerView
// Popover for selecting Ollama model or entering HuggingFace Repo ID.

struct ModelPickerView: View {
    @EnvironmentObject var app: AppState
    @State private var tab: Tab = .ollama

    enum Tab: String, CaseIterable {
        case ollama      = "Ollama"
        case mlx         = "MLX 🚀"
        case bitnet      = "BitNet ⚡"
        case huggingface = "HuggingFace"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Tab picker
            Picker("Source", selection: $tab) {
                ForEach(Tab.allCases, id: \.self) { t in
                    Text(t.rawValue).tag(t)
                }
            }
            .pickerStyle(.segmented)
            .padding(12)

            Divider()

            switch tab {
            case .ollama:      ollamaTab
            case .mlx:         mlxTab
            case .bitnet:      bitnetTab
            case .huggingface: huggingFaceTab
            }
        }
        .padding(.bottom, 8)
    }

    // MARK: - MLX tab

    private var mlxTab: some View {
        VStack(alignment: .leading, spacing: 12) {

            // Status badge
            HStack(spacing: 8) {
                Circle().fill(app.statusColor).frame(width: 8, height: 8)
                Text(app.statusLabel).font(.callout).lineLimit(1)
                    .foregroundStyle(app.statusColor)
                Spacer()
                if case .mlxReady = app.modelStatus {
                    Label("Running", systemImage: "checkmark.circle.fill")
                        .font(.caption).foregroundStyle(.green)
                }
            }

            Divider()

            Text(app.t("Model Selection", "モデル選択")).font(.caption2).foregroundStyle(.tertiary)

            // Model list
            ScrollView {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(MLXRunner.popularModels) { model in
                        Button {
                            app.activeMlxModel = model.id
                        } label: {
                            HStack(alignment: .top) {
                                Image(systemName: app.activeMlxModel == model.id
                                      ? "checkmark.circle.fill" : "circle")
                                    .foregroundStyle(app.activeMlxModel == model.id
                                                     ? Color.accentColor : .secondary)
                                    .frame(width: 16)
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(model.displayName)
                                        .font(.caption)
                                        .foregroundStyle(.primary)
                                    Text("\(String(format: "%.1f", model.sizeGB)) GB  •  \(model.tags.joined(separator: ", "))")
                                        .font(.caption2)
                                        .foregroundStyle(.tertiary)
                                }
                                Spacer()
                                if model.id == "mlx-community/gemma-4-26b-a4b-it-4bit" {
                                    Text(app.t("Recommended", "推奨"))
                                        .font(.caption2)
                                        .padding(.horizontal, 5).padding(.vertical, 2)
                                        .background(Color.accentColor.opacity(0.2), in: Capsule())
                                        .foregroundStyle(Color.accentColor)
                                }
                            }
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            .frame(maxHeight: 180)

            Divider()

            // Action buttons
            HStack(spacing: 8) {
                Button {
                    app.startMLXServer()
                } label: {
                    Label("Start MLX", systemImage: "play.fill")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .disabled({
                    if case .connecting = app.modelStatus { return true }
                    if case .mlxReady(let m) = app.modelStatus { return m == app.activeMlxModel }
                    return false
                }())

                Button {
                    app.downloadMLXModel(repoId: app.activeMlxModel)
                } label: {
                    Label("Download", systemImage: "arrow.down.circle")
                }
                .buttonStyle(.bordered)
                .disabled({
                    if case .mlxDownloading = app.modelStatus { return true }
                    return false
                }())
            }

            // MLX Server Log (last 5 lines)
            if !app.mlxServerLogs.isEmpty {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Server log").font(.caption2).foregroundStyle(.tertiary)
                    let recent = Array(app.mlxServerLogs.suffix(5))
                    let startIdx = app.mlxServerLogs.count - recent.count
                    ForEach(Array(recent.enumerated()), id: \.offset) { i, log in
                        Text(log)
                            .font(.system(size: 9, design: .monospaced))
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                            .tag(startIdx + i)
                    }
                }
                .padding(6)
                .background(Color(red: 0.1, green: 0.1, blue: 0.12), in: RoundedRectangle(cornerRadius: 6))
            }

            // Download tip
            Text(app.t("First-time use — run in Terminal:\n/usr/local/bin/python3 -m mlx_lm download \\\n  --model mlx-community/gemma-4-26b-a4b-it-4bit",
                       "初回はターミナルで:\n/usr/local/bin/python3 -m mlx_lm download \\\n  --model mlx-community/gemma-4-26b-a4b-it-4bit"))
                .font(.system(size: 9, design: .monospaced))
                .foregroundStyle(.tertiary)
                .padding(6)
                .background(Color(red: 0.1, green: 0.1, blue: 0.12), in: RoundedRectangle(cornerRadius: 6))
        }
        .padding(12)
    }

    // MARK: - Ollama tab

    @State private var loadedModels: [OllamaClient.RunningModel] = []
    @State private var ejectingModel: String? = nil
    @State private var hasLoadedOnce = false

    private var ollamaTab: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Status row
            HStack {
                Circle().fill(app.statusColor).frame(width: 8, height: 8)
                Text(app.statusLabel).font(.callout).lineLimit(1)
                Spacer()
                Button("Refresh") {
                    app.modelStatus = .none
                    Task {
                        await OllamaClient.shared.resetAvailability()
                        await refreshLoadedModels()
                    }
                    app.connectOllama()
                }
                .buttonStyle(.borderless).font(.callout)
            }

            vramSection

            installedModelsSection

            Button {
                app.modelStatus = .none
                app.connectOllama()
                Task { await refreshLoadedModels() }
            } label: {
                Label("Connect Ollama", systemImage: "link").frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.regular)
        }
        .padding(12)
        .task {
            if !hasLoadedOnce { hasLoadedOnce = true; await refreshLoadedModels() }
        }
    }

    // ── VRAM 読み込み中モデル ─────────────────────────────────────────────

    @ViewBuilder
    private var vramSection: some View {
        if !loadedModels.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Label(app.t("Loading into VRAM", "VRAM に読み込み中"), systemImage: "memorychip")
                        .font(.caption2).foregroundStyle(.orange)
                    Spacer()
                    Text("\(loadedModels.count) " + app.t("model(s)", "モデル")).font(.caption2).foregroundStyle(.tertiary)
                }
                ForEach(loadedModels, id: \.name) { running in
                    vramRow(running)
                }
            }
            Divider()
        }
    }

    private func vramRow(_ running: OllamaClient.RunningModel) -> some View {
        let isActive    = app.activeOllamaModel == running.name
        let isEjecting  = ejectingModel == running.name
        return HStack(spacing: 8) {
            Circle().fill(isActive ? Color.green : Color.orange).frame(width: 6, height: 6)
            VStack(alignment: .leading, spacing: 1) {
                Text(running.name).font(.system(.caption, design: .monospaced)).lineLimit(1)
                Text(String(format: "%.2f GB", running.sizeGB))
                    .font(.caption2).foregroundStyle(.tertiary)
            }
            Spacer()
            Button { Task { await eject(running.name) } } label: {
                if isEjecting {
                    ProgressView().scaleEffect(0.6).frame(width: 22, height: 22)
                } else {
                    Image(systemName: "eject.fill")
                        .font(.caption)
                        .foregroundStyle(isActive ? AnyShapeStyle(.tertiary) : AnyShapeStyle(Color.orange))
                }
            }
            .buttonStyle(.borderless)
            .disabled(isEjecting || isActive)
            .help(isActive
                  ? app.t("Cannot unload active model", "アクティブなモデルはアンロードできません")
                  : app.t("Unload model from VRAM", "モデルを VRAM からアンロード"))
        }
        .padding(.horizontal, 8).padding(.vertical, 5)
        .background(RoundedRectangle(cornerRadius: 6).fill(Color.orange.opacity(0.07)))
    }

    // ── インストール済みモデル ────────────────────────────────────────────

    @ViewBuilder
    private var installedModelsSection: some View {
        if app.ollamaModels.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                Text("No models found. Install Ollama and run:")
                    .font(.caption).foregroundStyle(.secondary)
                Text("ollama pull gemma4:26b")
                    .font(.system(.caption, design: .monospaced))
                    .padding(6)
                    .background(Color(nsColor: .textBackgroundColor), in: RoundedRectangle(cornerRadius: 6))
            }
        } else {
            Text(app.t("Installed models:", "インストール済みモデル:")).font(.caption).foregroundStyle(.secondary)
            ScrollView {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(app.ollamaModels, id: \.self) { model in
                        installedModelRow(model)
                    }
                }
            }
            .frame(maxHeight: 160)
        }
    }

    private func installedModelRow(_ model: String) -> some View {
        let isActive  = app.activeOllamaModel == model
        let isInVRAM  = loadedModels.contains(where: { $0.name == model })
        return Button {
            app.activeOllamaModel = model
            app.modelStatus = .ollamaReady(model: model)
            app.addSystemMessage("🟢 Switched to \(model)")
        } label: {
            HStack {
                Image(systemName: isActive ? "checkmark.circle.fill" : "circle")
                    .foregroundStyle(isActive ? Color.accentColor : Color.secondary)
                Text(model).font(.system(.callout, design: .monospaced)).lineLimit(1)
                Spacer()
                if isInVRAM {
                    Text("VRAM")
                        .font(.system(size: 9, weight: .semibold))
                        .padding(.horizontal, 5).padding(.vertical, 2)
                        .background(Color.orange.opacity(0.2), in: Capsule())
                        .foregroundStyle(.orange)
                }
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }


    // MARK: - BitNet tab

    @State private var bitnetConfig: BitNetConfig? = nil
    @State private var bitnetChecked = false

    private var bitnetTab: some View {
        VStack(alignment: .leading, spacing: 12) {

            // ステータス行
            HStack(spacing: 8) {
                Circle()
                    .fill(bitnetConfig?.isValid == true ? Color.green : Color.gray)
                    .frame(width: 8, height: 8)
                Text(bitnetConfig?.isValid == true
                     ? app.t("BitNet ready", "BitNet 準備完了")
                     : app.t("BitNet not installed", "BitNet 未インストール"))
                    .font(.callout)
                    .foregroundStyle(bitnetConfig?.isValid == true ? .green : .secondary)
                Spacer()
                if case .bitnetReady = app.modelStatus {
                    Label(app.t("Active", "稼働中"),
                          systemImage: "checkmark.circle.fill")
                        .font(.caption).foregroundStyle(.green)
                }
            }

            Divider()

            if let cfg = bitnetConfig, cfg.isValid {
                // インストール済みビュー
                VStack(alignment: .leading, spacing: 6) {
                    Label(cfg.modelName, systemImage: "cpu")
                        .font(.subheadline.bold())
                        .foregroundStyle(.primary)

                    Group {
                        infoRow("モデル", value: cfg.modelPath.components(separatedBy: "/").last ?? cfg.modelPath)
                        infoRow("バイナリ", value: cfg.binaryPath.components(separatedBy: "/").last ?? cfg.binaryPath)
                        infoRow("Max tokens", value: "\(cfg.maxTokens)")
                        infoRow("Temp", value: String(format: "%.2f", cfg.temperature))
                    }
                }
                .padding(10)
                .background(Color.green.opacity(0.07), in: RoundedRectangle(cornerRadius: 8))

                // 起動 / 停止ボタン
                HStack(spacing: 8) {
                    if case .bitnetReady = app.modelStatus {
                        Button {
                            app.modelStatus = .none
                            app.addSystemMessage("⏹️ BitNet を停止しました")
                        } label: {
                            Label(app.t("Stop BitNet", "BitNet 停止"),
                                  systemImage: "stop.circle.fill")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.bordered)
                        .tint(.red)
                    } else {
                        Button {
                            app.modelStatus = .bitnetReady(model: cfg.modelName)
                            app.addSystemMessage("⚡ BitNet \(cfg.modelName) を有効化しました")
                        } label: {
                            Label(app.t("Use BitNet", "BitNet を使用"),
                                  systemImage: "play.fill")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(Color(red: 0.3, green: 0.7, blue: 1.0))
                    }
                }

            } else {
                // 未インストールガイド
                VStack(alignment: .leading, spacing: 8) {
                    Label(app.t("BitNet is not set up yet.",
                                "BitNet はまだセットアップされていません。"),
                          systemImage: "exclamationmark.triangle.fill")
                        .font(.caption)
                        .foregroundStyle(.orange)

                    Text(app.t("Install BitNet from Settings → BitNet, then return here to activate.",
                               "設定 → BitNet からインストールし、再度ここに戻ってください。"))
                        .font(.caption2)
                        .foregroundStyle(.secondary)

                    Text("# Quick install (Terminal):\n" +
                         "git clone https://github.com/microsoft/BitNet.git ~/BitNet\n" +
                         "cd ~/BitNet && python setup_env.py -md Llama3.2-3B")
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(.secondary)
                        .padding(8)
                        .background(Color.black.opacity(0.3),
                                    in: RoundedRectangle(cornerRadius: 6))
                }

                Button {
                    Task { await recheckBitNet() }
                } label: {
                    Label(app.t("Check Again", "再検査"), systemImage: "arrow.clockwise")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
            }
        }
        .padding(12)
        .task {
            if !bitnetChecked { bitnetChecked = true; await recheckBitNet() }
        }
    }

    private func infoRow(_ label: String, value: String) -> some View {
        HStack {
            Text(label)
                .font(.caption2)
                .foregroundStyle(.tertiary)
                .frame(width: 70, alignment: .leading)
            Text(value)
                .font(.system(.caption2, design: .monospaced))
                .lineLimit(1)
                .truncationMode(.middle)
        }
    }

    @MainActor
    private func recheckBitNet() async {
        bitnetConfig = BitNetConfig.load()
    }


    // MARK: - Helpers

    @MainActor
    private func refreshLoadedModels() async {
        loadedModels = await OllamaClient.shared.loadedModels()
    }

    @MainActor
    private func eject(_ model: String) async {
        ejectingModel = model
        let ok = await OllamaClient.shared.unloadModel(model)
        ejectingModel = nil
        if ok {
            app.addSystemMessage("⏏️ Unloaded \(model) from VRAM")
            // If we unloaded the active model, clear status
            if app.activeOllamaModel == model {
                app.modelStatus = .none
            }
        } else {
            app.addSystemMessage("⚠️ Failed to unload \(model)")
        }
        await refreshLoadedModels()
    }


    // MARK: - HuggingFace tab

    private var huggingFaceTab: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Enter a HuggingFace MLX model Repo ID to download and use locally.")
                .font(.caption)
                .foregroundStyle(.secondary)

            TextField("mlx-community/Qwen2.5-Coder-7B-Instruct-4bit",
                      text: $app.customHFRepoId)
                .textFieldStyle(.roundedBorder)
                .font(.system(.callout, design: .monospaced))

            // Popular models quick-pick
            VStack(alignment: .leading, spacing: 6) {
                Text("Popular models:")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)

                ForEach(popularModels, id: \.self) { repo in
                    Button {
                        app.customHFRepoId = repo
                    } label: {
                        HStack {
                            Image(systemName: "cube.box")
                                .font(.caption)
                            Text(repo.components(separatedBy: "/").last ?? repo)
                                .font(.caption)
                                .lineLimit(1)
                            Spacer()
                        }
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(.secondary)
                }
            }

            if case .mlxDownloading(let m) = app.modelStatus {
                ProgressView()
                    .scaleEffect(0.8)
                Text("Downloading \(m.components(separatedBy: "/").last ?? m)…")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Button {
                downloadModel()
            } label: {
                Label(
                    downloadLabel,
                    systemImage: "arrow.down.circle"
                )
                .frame(maxWidth: .infinity)
                .fontWeight(.semibold)
            }
            .buttonStyle(.borderedProminent)
            .disabled(app.customHFRepoId.isEmpty || {
                if case .mlxDownloading = app.modelStatus { return true }
                if case .connecting    = app.modelStatus { return true }
                return false
            }())
        }
        .padding(12)
    }

    private var downloadLabel: String {
        if case .mlxDownloading = app.modelStatus { return "Downloading…" }
        return "Download & Use"
    }

    private func downloadModel() {
        let repoId = app.customHFRepoId.trimmingCharacters(in: .whitespaces)
        guard !repoId.isEmpty else { return }
        // Wire to AppState.downloadMLXModel() — downloads via MLXRunner then auto-loads
        app.downloadMLXModel(repoId: repoId)
    }

    private let popularModels = [
        "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit",
        "mlx-community/gemma-3-12b-it-4bit",
        "mlx-community/Phi-4-mini-instruct-4bit",
        "mlx-community/Mistral-7B-Instruct-v0.3-4bit",
    ]
}
