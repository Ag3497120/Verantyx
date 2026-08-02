import SwiftUI

/// Settings UI for in-app JGEN conversion (forge + engine ship in the app).
/// Detect Ollama / LM Studio / HF cache models, Convert, Load — no external
/// repo or Terminal.
struct JGenSettingsSection: View {
    @EnvironmentObject var app: AppState
    @ObservedObject private var converter = JGenConverter.shared
    @State private var isLoading: String?
    @State private var loadedModel: String?
    @State private var loadError: String?
    /// Optional tokenizer override (HF repo id or local folder), keyed by
    /// DiscoveredSource.name — same capability as forge `--tokenizer`.
    @State private var tokenizerOverrides: [String: String] = [:]

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            sectionHeader(app.t("JGEN Model Conversion", "JGENモデル変換"), icon: "shippingbox")

            card {
                VStack(alignment: .leading, spacing: 10) {
                    Text(app.t(
                        "Convert → Load → chat here. Hybrid (Ornith / Qwen3.5) and dense GGUF support ships inside Verantyx — no separate CLI install.",
                        "ここで変換→読み込み→チャット。ハイブリッド(Ornith / Qwen3.5)とDense GGUF対応は Verantyx に同梱済みです（別CLIのインストール不要）。"
                    ))
                    .font(.system(size: 10))
                    .foregroundStyle(.secondary)

                    HStack(spacing: 6) {
                        Image(systemName: "shippingbox.fill")
                            .font(.system(size: 10))
                            .foregroundStyle(Color(red: 0.4, green: 0.85, blue: 0.55))
                        Text(app.t("Converter & engine included in this app",
                                   "コンバータとエンジンはこのアプリに含まれています"))
                            .font(.system(size: 9, weight: .semibold))
                            .foregroundStyle(Color(red: 0.7, green: 0.85, blue: 0.75))
                        Spacer()
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
                            VStack(alignment: .leading, spacing: 4) {
                                HStack(spacing: 8) {
                                    Image(systemName: sourceIcon(src.source))
                                        .font(.system(size: 10))
                                        .foregroundStyle(Color(red: 0.6, green: 0.6, blue: 0.7))
                                        .frame(width: 14)
                                    VStack(alignment: .leading, spacing: 1) {
                                        HStack(spacing: 6) {
                                            Text(src.name)
                                                .font(.system(size: 11, design: .monospaced))
                                                .foregroundStyle(Color(red: 0.9, green: 0.9, blue: 0.95))
                                            if src.looksHybrid {
                                                Text("hybrid")
                                                    .font(.system(size: 8, weight: .bold))
                                                    .foregroundStyle(Color(red: 0.35, green: 0.75, blue: 0.95))
                                                    .padding(.horizontal, 5)
                                                    .padding(.vertical, 1)
                                                    .background(Color(red: 0.2, green: 0.35, blue: 0.45).opacity(0.5))
                                                    .clipShape(RoundedRectangle(cornerRadius: 3))
                                            }
                                        }
                                        Text("\(src.source) · \(String(format: "%.2f", src.sizeGB))GB")
                                            .font(.system(size: 9))
                                            .foregroundStyle(Color(red: 0.55, green: 0.55, blue: 0.6))
                                    }
                                    Spacer()
                                    if src.converted {
                                        Label(app.t("Converted", "変換済み"), systemImage: "checkmark.circle.fill")
                                            .font(.system(size: 9, weight: .semibold))
                                            .foregroundStyle(Color(red: 0.4, green: 0.9, blue: 0.5))
                                        // Re-convert: picks up jgen_forge fixes
                                        // (e.g. the tokenizer-synthesis change)
                                        // without deleting/renaming the old
                                        // .jgen by hand first -- `pull` just
                                        // overwrites the same output path.
                                        Button {
                                            Task { await converter.convert(src, tokenizer: tokenizerOverrides[src.name]) }
                                        } label: {
                                            Image(systemName: "arrow.triangle.2.circlepath")
                                                .font(.system(size: 10))
                                        }
                                        .buttonStyle(.plain)
                                        .foregroundStyle(Color(red: 0.6, green: 0.6, blue: 0.7))
                                        .disabled(converter.isRunning)
                                        .help(app.t("Re-convert (e.g. after a jgen_forge update)", "再変換(jgen_forge更新後など)"))
                                    } else {
                                        Button {
                                            Task { await converter.convert(src, tokenizer: tokenizerOverrides[src.name]) }
                                        } label: {
                                            Text(app.t("Convert", "変換"))
                                        }
                                        .buttonStyle(.borderedProminent)
                                        .tint(Color(red: 1.0, green: 0.6, blue: 0.3))
                                        .controlSize(.small)
                                        .disabled(converter.isRunning)
                                    }
                                }
                                // Explicit tokenizer override: Ollama only ever
                                // hands over raw GGUF weights, so when a GGUF's
                                // own embedded tokenizer metadata is broken or
                                // incomplete, this is the only reliable fix --
                                // point at the real HF repo (or a local
                                // tokenizer folder) instead of relying on
                                // automatic vocab-size matching or synthesis.
                                TextField(
                                    app.t("Tokenizer override (HF repo id or path, optional)", "トークナイザー指定(HFリポジトリIDまたはパス、任意)"),
                                    text: Binding(
                                        get: { tokenizerOverrides[src.name] ?? "" },
                                        set: { tokenizerOverrides[src.name] = $0 }
                                    )
                                )
                                .textFieldStyle(.plain)
                                .font(.system(size: 9, design: .monospaced))
                                .foregroundStyle(Color(red: 0.7, green: 0.7, blue: 0.75))
                                .padding(.leading, 22)
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
                          VStack(alignment: .leading, spacing: 3) {
                            HStack(spacing: 6) {
                                Circle().fill(Color(red: 0.4, green: 0.9, blue: 0.5)).frame(width: 6, height: 6)
                                Text(name)
                                    .font(.system(size: 11, design: .monospaced))
                                    .foregroundStyle(Color(red: 0.85, green: 0.85, blue: 0.9))
                                    .lineLimit(1)
                                    .truncationMode(.middle)
                                if let badge = converter.archBadge(for: name) {
                                    Text(badge)
                                        .font(.system(size: 8, weight: .bold))
                                        .foregroundStyle(
                                            badge == "Hybrid" ? Color(red: 0.35, green: 0.75, blue: 0.95)
                                            : badge == "Lexicon" ? Color(red: 0.75, green: 0.65, blue: 0.35)
                                            : Color(red: 0.7, green: 0.7, blue: 0.75)
                                        )
                                }
                                Spacer()
                                if loadedModel == name {
                                    Label(app.t("Active", "使用中"), systemImage: "bolt.fill")
                                        .font(.system(size: 9, weight: .semibold))
                                        .foregroundStyle(Color(red: 1.0, green: 0.6, blue: 0.3))
                                } else if isLoading == name {
                                    ProgressView().controlSize(.mini)
                                } else if !converter.isArchSupported(name) {
                                    Label(app.t("Unsupported arch (lexicon only)", "非対応アーキ(辞書のみ)"), systemImage: "exclamationmark.triangle")
                                        .font(.system(size: 9))
                                        .foregroundStyle(Color(red: 0.7, green: 0.7, blue: 0.4))
                                        .help(app.t(
                                            "This architecture isn't runnable in JCrossEngine yet (lexicon / Vector Lab only).",
                                            "このアーキテクチャはまだJCrossEngineで推論できません（辞書/Vector Labのみ）。"
                                        ))
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

                            // 本物のトークナイザが無い(語彙サイドカーに落ちた)
                            // モデルには、指定すべきHFリポジトリを提案する。
                            // 実在確認に通ったものだけ出し、押さない限り入らない。
                            if converter.needsRealTokenizer(name) {
                                tokenizerSuggestionRow(for: name)
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

    /// 語彙サイドカーに落ちたモデル用の、トークナイザー候補の行。
    ///
    /// 候補は「ローカル小型モデル + 検索1回」で拾い、**HuggingFace上に
    /// tokenizer.json が実在することをHTTPで確認できたものだけ**表示する。
    /// この確認が無いと、存在しないリポジトリ名をそのまま渡してしまう。
    @ViewBuilder
    private func tokenizerSuggestionRow(for name: String) -> some View {
        HStack(spacing: 6) {
            Image(systemName: "questionmark.circle")
                .font(.system(size: 9))
                .foregroundStyle(Color(red: 1.0, green: 0.75, blue: 0.35))

            if let repo = converter.tokenizerSuggestions[name] {
                Text(app.t("Suggested tokenizer: ", "トークナイザー候補: ") + repo)
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(Color(red: 0.75, green: 0.75, blue: 0.8))
                    .textSelection(.enabled)
                Text(app.t("(verified)", "(実在確認済み)"))
                    .font(.system(size: 8))
                    .foregroundStyle(Color(red: 0.4, green: 0.85, blue: 0.5))
                Spacer()
                Button(app.t("Use", "使う")) {
                    // 入れるだけ。再変換は自動で走らせない。
                    if let src = converter.discoveredSources.first(where: {
                        name.contains(JGenSettingsSection.sanitizedName($0.name))
                    }) {
                        tokenizerOverrides[src.name] = repo
                    }
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
            } else if converter.suggestingTokenizerFor == name {
                Text(app.t("Looking up a tokenizer repo…", "トークナイザーのリポジトリを照会中…"))
                    .font(.system(size: 9)).foregroundStyle(.tertiary)
                ProgressView().controlSize(.mini)
                Spacer()
            } else {
                Text(app.t("No real tokenizer — chat can't load this.",
                           "本物のトークナイザーが無く、チャットで読み込めません。"))
                    .font(.system(size: 9))
                    .foregroundStyle(Color(red: 0.7, green: 0.7, blue: 0.45))
                Spacer()
                Button(app.t("Find one", "候補を探す")) {
                    let src = converter.discoveredSources.first(where: {
                        name.contains(JGenSettingsSection.sanitizedName($0.name))
                    })
                    converter.suggestTokenizerRepo(for: name, sourceName: src?.name ?? name)
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .disabled(converter.suggestingTokenizerFor != nil)
            }
        }
        .padding(.leading, 12)
    }

    /// `pull` が .jgen 名を作るときと同じ正規化（":"/"/" を "_" に）
    static func sanitizedName(_ s: String) -> String {
        s.replacingOccurrences(of: ":", with: "_").replacingOccurrences(of: "/", with: "_")
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
