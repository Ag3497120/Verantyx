import SwiftUI

/// Settings UI for JGenConverter: an "Ollama pull"-simple way to get a
/// model ready for JCrossEngine (Milestone A of the JGEN/RustBrain
/// integration) -- either name a model already known to Ollama/LM Studio/
/// the HF cache, or drop a model folder/.gguf into the dropzone folder.
/// No manual conversion arguments needed either way; jgen_forge.py
/// (verantyx-cli) handles format detection and conversion end to end.
struct JGenSettingsSection: View {
    @EnvironmentObject var app: AppState
    @ObservedObject private var converter = JGenConverter.shared
    @State private var isLoading: String?
    @State private var loadedModel: String?
    @State private var loadError: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            sectionHeader(app.t("JGEN Model Conversion", "JGENモデル変換"), icon: "shippingbox")

            card {
                VStack(alignment: .leading, spacing: 10) {
                    Text(app.t(
                        "Convert a model to .jgen for JCrossEngine (hidden-state read/inject). Models already in Ollama/LM Studio/the HF cache are detected automatically below -- just click Convert, no typing needed.",
                        "JCrossEngine(隠れ状態の読み取り/介入)用に、モデルを.jgenへ変換します。Ollama・LM Studio・HFキャッシュにあるモデルは下に自動検出されるので、入力不要でConvertを押すだけです。"
                    ))
                    .font(.system(size: 10))
                    .foregroundStyle(.secondary)

                    Divider().opacity(0.2)
                    Toggle(app.t(
                        "Advanced: use a verantyx-cli checkout instead of the built-in converter",
                        "上級者向け: 内蔵の変換ツールの代わりにverantyx-cliのチェックアウトを使う"
                    ), isOn: $converter.useCustomRepo)
                        .toggleStyle(.checkbox)
                        .font(.system(size: 10))

                    if converter.useCustomRepo && !converter.repoPathValid {
                        HStack(spacing: 8) {
                            Image(systemName: "exclamationmark.triangle.fill")
                                .font(.system(size: 11))
                                .foregroundStyle(Color(red: 1.0, green: 0.7, blue: 0.3))
                            VStack(alignment: .leading, spacing: 2) {
                                Text(app.t(
                                    "No verantyx-cli checkout selected yet.",
                                    "verantyx-cliのチェックアウトがまだ選択されていません。"
                                ))
                                .font(.system(size: 10))
                                .foregroundStyle(Color(red: 1.0, green: 0.7, blue: 0.3))
                            }
                            Spacer()
                            Button {
                                converter.pickRepoFolder()
                            } label: {
                                Text(app.t("Locate…", "場所を指定…"))
                            }
                            .buttonStyle(.bordered)
                            .controlSize(.small)
                        }
                    } else if converter.useCustomRepo {
                        Text(converter.repoPath)
                            .font(.system(size: 9, design: .monospaced))
                            .foregroundStyle(Color(red: 0.55, green: 0.55, blue: 0.6))
                    }

                    Divider().opacity(0.2)
                }
            }

            // ── Auto-discovered models (Ollama/LM Studio/HF cache) ──
            // No typing needed: this lists what jgen_forge.py's own
            // `sources --json` already finds on disk, and Convert calls
            // `pull` with the exact discovered name (never an ambiguous
            // hand-typed substring).
            HStack(spacing: 6) {
                sectionHeader(app.t("Detected Models", "検出済みモデル"), icon: "magnifyingglass")
                if converter.isDiscovering {
                    ProgressView().controlSize(.mini)
                }
                Spacer()
                Button {
                    Task { await converter.refreshDiscoveredSources() }
                } label: {
                    Image(systemName: "arrow.clockwise").font(.system(size: 10))
                }
                .buttonStyle(.plain)
                .foregroundStyle(Color(red: 0.6, green: 0.6, blue: 0.7))
            }
            card {
                if converter.discoveredSources.isEmpty {
                    Text(app.t(
                        "No models found yet in Ollama / LM Studio / the HF cache.",
                        "Ollama・LM Studio・HFキャッシュにまだモデルが見つかっていません。"
                    ))
                    .font(.system(size: 10))
                    .foregroundStyle(.secondary)
                } else {
                    VStack(alignment: .leading, spacing: 8) {
                        ForEach(converter.discoveredSources) { src in
                            HStack(spacing: 8) {
                                Image(systemName: sourceIcon(src.source))
                                    .font(.system(size: 10))
                                    .foregroundStyle(Color(red: 0.6, green: 0.6, blue: 0.7))
                                    .frame(width: 14)
                                VStack(alignment: .leading, spacing: 1) {
                                    Text(src.name)
                                        .font(.system(size: 11, design: .monospaced))
                                        .foregroundStyle(Color(red: 0.9, green: 0.9, blue: 0.95))
                                    Text("\(src.source) · \(String(format: "%.2f", src.sizeGB))GB")
                                        .font(.system(size: 9))
                                        .foregroundStyle(Color(red: 0.55, green: 0.55, blue: 0.6))
                                }
                                Spacer()
                                if src.converted {
                                    Label(app.t("Converted", "変換済み"), systemImage: "checkmark.circle.fill")
                                        .font(.system(size: 9, weight: .semibold))
                                        .foregroundStyle(Color(red: 0.4, green: 0.9, blue: 0.5))
                                } else {
                                    Button {
                                        Task { await converter.convert(src) }
                                    } label: {
                                        Text(app.t("Convert", "変換"))
                                    }
                                    .buttonStyle(.borderedProminent)
                                    .tint(Color(red: 1.0, green: 0.6, blue: 0.3))
                                    .controlSize(.small)
                                    .disabled(converter.isRunning)
                                }
                            }
                        }
                    }
                }
            }

            card {
                VStack(alignment: .leading, spacing: 10) {

                    // ── Drop into dropzone ──
                    Text(app.t("Or just drop a model in", "またはモデルを置くだけ"))
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(.white)
                    HStack(spacing: 8) {
                        Button {
                            converter.revealDropzoneInFinder()
                        } label: {
                            Label(app.t("Open Dropzone Folder", "ドロップ用フォルダを開く"), systemImage: "folder")
                        }
                        .buttonStyle(.bordered)
                        Button {
                            Task { await converter.scanDropzone() }
                        } label: {
                            Text(app.t("Scan & Convert New", "新規を検出して変換"))
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(Color(red: 1.0, green: 0.6, blue: 0.3))
                        .disabled(converter.isRunning)
                    }
                    Text(app.t(
                        "Drag a HuggingFace model folder (with .safetensors) or a .gguf file into the folder, then scan.",
                        "safetensorsを含むHuggingFaceモデルフォルダ、または.ggufファイルをそのフォルダにドラッグしてからスキャンしてください。"
                    ))
                    .font(.system(size: 9))
                    .foregroundStyle(Color(red: 0.55, green: 0.55, blue: 0.6))

                    if converter.isRunning {
                        HStack(spacing: 6) {
                            ProgressView().controlSize(.small)
                            Text(app.t("Converting…", "変換中…"))
                                .font(.system(size: 10))
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }

            if !converter.convertedModels.isEmpty {
                sectionHeader(app.t("Converted Models", "変換済みモデル"), icon: "checkmark.seal")
                card {
                    VStack(alignment: .leading, spacing: 8) {
                        ForEach(converter.convertedModels, id: \.self) { name in
                            HStack(spacing: 6) {
                                Circle().fill(Color(red: 0.4, green: 0.9, blue: 0.5)).frame(width: 6, height: 6)
                                Text(name)
                                    .font(.system(size: 11, design: .monospaced))
                                    .foregroundStyle(Color(red: 0.85, green: 0.85, blue: 0.9))
                                    .lineLimit(1)
                                    .truncationMode(.middle)
                                Spacer()
                                if loadedModel == name {
                                    Label(app.t("Active", "使用中"), systemImage: "bolt.fill")
                                        .font(.system(size: 9, weight: .semibold))
                                        .foregroundStyle(Color(red: 1.0, green: 0.6, blue: 0.3))
                                } else if isLoading == name {
                                    ProgressView().controlSize(.mini)
                                } else {
                                    Button {
                                        loadModel(name)
                                    } label: {
                                        Text(app.t("Load", "読み込む"))
                                    }
                                    .buttonStyle(.bordered)
                                    .controlSize(.small)
                                }
                            }
                        }
                    }
                }
                if let loadError {
                    Text(loadError)
                        .font(.system(size: 10))
                        .foregroundStyle(Color(red: 1.0, green: 0.4, blue: 0.4))
                }
            }

            if !converter.log.isEmpty {
                sectionHeader(app.t("Log", "ログ"), icon: "terminal")
                card {
                    ScrollView {
                        Text(converter.log)
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(Color(red: 0.8, green: 0.8, blue: 0.85))
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .frame(maxHeight: 200)
                }
            }
        }
        .onAppear {
            converter.refreshConvertedModelsList()
            Task { await converter.refreshDiscoveredSources() }
        }
    }

    /// Loads `name` (a .jgen filename under converted_models/) into
    /// JCrossChatManager and, on success, sets app.modelStatus so
    /// AgentLoop.callModel routes chat through the .jcrossReady case
    /// (Milestone B). Heavy weight I/O -- runs off the main actor.
    private func loadModel(_ name: String) {
        isLoading = name
        loadError = nil
        Task {
            do {
                try await JCrossChatManager.shared.load(modelFileName: name)
                await MainActor.run {
                    loadedModel = name
                    isLoading = nil
                    app.modelStatus = .jcrossReady(model: name)
                }
            } catch {
                await MainActor.run {
                    isLoading = nil
                    loadError = error.localizedDescription
                }
            }
        }
    }

    private func sourceIcon(_ source: String) -> String {
        switch source {
        case "ollama":   return "cube.fill"
        case "lmstudio": return "desktopcomputer"
        case "hf-cache": return "shippingbox.fill"
        default:         return "questionmark.circle"
        }
    }

    // Mirrors SettingsView's private sectionHeader/settingsCard helpers
    // (can't reference those directly across files -- same visual language).
    private func sectionHeader(_ title: String, icon: String) -> some View {
        HStack(spacing: 6) {
            Image(systemName: icon).font(.system(size: 11))
            Text(title).font(.system(size: 11, weight: .semibold))
        }
        .foregroundStyle(Color(red: 1.0, green: 0.6, blue: 0.3))
    }

    private func card<Content: View>(@ViewBuilder content: () -> Content) -> some View {
        content()
            .padding(14)
            .background(Color.white.opacity(0.03), in: RoundedRectangle(cornerRadius: 10))
            .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(Color.white.opacity(0.06), lineWidth: 1))
    }
}
