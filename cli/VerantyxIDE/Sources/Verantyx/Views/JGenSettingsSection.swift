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
    @State private var pullName: String = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            sectionHeader(app.t("JGEN Model Conversion", "JGENモデル変換"), icon: "shippingbox")

            card {
                VStack(alignment: .leading, spacing: 10) {
                    Text(app.t(
                        "Convert a model to .jgen for JCrossEngine (hidden-state read/inject). No manual arguments -- point at a name or drop a model in.",
                        "JCrossEngine(隠れ状態の読み取り/介入)用に、モデルを.jgenへ変換します。手動の引数は不要 — 名前を指定するか、モデルを置くだけです。"
                    ))
                    .font(.system(size: 10))
                    .foregroundStyle(.secondary)

                    Divider().opacity(0.2)

                    // ── Pull by name (Ollama/LM Studio/HF cache) ──
                    Text(app.t("Pull by name (like `ollama pull`)", "名前で取得（`ollama pull`と同様）"))
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(.white)
                    HStack(spacing: 8) {
                        TextField(app.t("e.g. qwen2.5:0.5b", "例: qwen2.5:0.5b"), text: $pullName)
                            .textFieldStyle(.roundedBorder)
                        Button {
                            let name = pullName
                            Task { await converter.pull(name) }
                        } label: {
                            Text(app.t("Pull & Convert", "取得して変換"))
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(Color(red: 1.0, green: 0.6, blue: 0.3))
                        .disabled(converter.isRunning || pullName.trimmingCharacters(in: .whitespaces).isEmpty)
                    }
                    Text(app.t(
                        "Finds a model already in Ollama, LM Studio, or the HF cache by name and converts it -- nothing new to download.",
                        "Ollama・LM Studio・HFキャッシュに既にあるモデルを名前で探して変換します。新規ダウンロードは不要です。"
                    ))
                    .font(.system(size: 9))
                    .foregroundStyle(Color(red: 0.55, green: 0.55, blue: 0.6))

                    Divider().opacity(0.2)

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
                    VStack(alignment: .leading, spacing: 6) {
                        ForEach(converter.convertedModels, id: \.self) { name in
                            HStack(spacing: 6) {
                                Circle().fill(Color(red: 0.4, green: 0.9, blue: 0.5)).frame(width: 6, height: 6)
                                Text(name)
                                    .font(.system(size: 11, design: .monospaced))
                                    .foregroundStyle(Color(red: 0.85, green: 0.85, blue: 0.9))
                            }
                        }
                    }
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
        .onAppear { converter.refreshConvertedModelsList() }
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
