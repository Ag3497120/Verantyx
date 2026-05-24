import SwiftUI

// MARK: - GatekeeperModeView
//
// Gatekeeper Mode のメインUI。
// • モード有効化スイッチ
// • Vault 変換プログレス
// • Commander モデル選択
// • リアルタイムアクセスログ（外部APIに何を見せたか）

struct GatekeeperModeView: View {
    @ObservedObject private var state       = GatekeeperModeState.shared
    @ObservedObject private var orchestrator = CommanderOrchestrator.shared
    @State private var availableModels: [String] = []
    @State private var showAccessLog = false

    @EnvironmentObject var app: AppState
    @Environment(\.dismiss) var dismiss

    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {

                    // ─── Header ───────────────────────────────────────────────
                    headerSection

                    Divider()

                    // ─── Architecture Diagram ─────────────────────────────────
                    architectureCard

                    // ─── Vault Status ─────────────────────────────────────
                    GatekeeperVaultCard(state: state, vault: state.vault)

                    // ─── Access Log ───────────────────────────────────────
                    accessLogCard
                }
                .padding()
            }

            // ─── Token Speed Meter ────────────────────────────────────────────
            StatusBarView(terminal: app.terminal)
        }
        .frame(minWidth: 520, minHeight: 700)
        .task { await loadModels() }
    }

    // MARK: - Header

    private var headerSection: some View {
        HStack {
            Button(action: { dismiss() }) {
                Image(systemName: "chevron.left")
                    .font(.body.bold())
            }
            .buttonStyle(.plain)
            .padding(.trailing, 8)

            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 8) {
                    Image(systemName: "shield.lefthalf.filled")
                        .font(.title2)
                        .foregroundStyle(state.isEnabled ? .green : .secondary)
                    Text("Gatekeeper Mode")
                        .font(.title2.bold())
                }
                Text(AppLanguage.shared.t("Local LLM acts as Commander — External API only sees JCross IR", "ローカル LLM が司令官 — 外部 API は JCross IR しか見えない"))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            // Phase indicator
            phaseIndicator
        }
    }

    @ViewBuilder
    private var phaseIndicator: some View {
        switch state.phase {
        case .idle:
            Label(AppLanguage.shared.t("Standby", "スタンバイ"), systemImage: "circle.fill")
                .font(.caption)
                .foregroundStyle(state.isEnabled ? .green : .secondary)
        case .commanderPlanning(let step):
            Label(step, systemImage: "brain")
                .font(.caption)
                .foregroundStyle(.blue)
        case .fetchingVault(let file):
            Label("Vault: \(file.components(separatedBy: "/").last ?? file)", systemImage: "folder")
                .font(.caption)
                .foregroundStyle(.orange)
        case .workerCalling, .workerThinking:
            Label(AppLanguage.shared.t("Worker processing...", "Worker 処理中..."), systemImage: "arrow.triangle.2.circlepath")
                .font(.caption)
                .foregroundStyle(.purple)
        case .reverseTranspiling:
            Label(AppLanguage.shared.t("Reverse converting...", "逆変換中..."), systemImage: "arrow.left.arrow.right")
                .font(.caption)
                .foregroundStyle(.teal)
        case .writingToDisk(let file):
            Label(AppLanguage.shared.t("Writing: ", "書き込み: ") + "\(file.components(separatedBy: "/").last ?? file)", systemImage: "pencil")
                .font(.caption)
                .foregroundStyle(.yellow)
        case .done:
            Label(AppLanguage.shared.t("Done", "完了"), systemImage: "checkmark.circle.fill")
                .font(.caption)
                .foregroundStyle(.green)
        case .error(let msg):
            Label(msg.prefix(30), systemImage: "xmark.circle.fill")
                .font(.caption)
                .foregroundStyle(.red)
        }
    }

    // MARK: - Architecture Card

    private var isUserActive: Bool {
        state.phase == .idle || state.phase == .done
    }

    private var isCommanderActive: Bool {
        switch state.phase {
        case .commanderPlanning, .fetchingVault, .reverseTranspiling, .writingToDisk: return true
        default: return false
        }
    }

    private var isWorkerActive: Bool {
        switch state.phase {
        case .workerCalling, .workerThinking: return true
        default: return false
        }
    }

    private var commanderModelName: String {
        if state.commanderModel.isEmpty { return "Ollama" }
        return state.commanderModel.components(separatedBy: "/").last ?? state.commanderModel
    }

    private var workerName: String {
        state.workerProvider.rawValue
    }

    private var architectureCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("動作フローとデータの位置", systemImage: "arrow.triangle.branch")
                .font(.subheadline.bold())
                .foregroundStyle(.secondary)

            HStack(spacing: 0) {
                roleBox(
                    icon: "person.fill",
                    title: "User",
                    color: .blue,
                    desc: "自然言語で要求",
                    isActive: isUserActive
                )
                arrowLabel(isCommanderActive ? "▶︎" : "→", isActive: isCommanderActive)
                roleBox(
                    icon: "cpu",
                    title: "Commander\n(\(commanderModelName.prefix(12)))",
                    color: .green,
                    desc: "実ファイル参照\n意図解析",
                    isActive: isCommanderActive
                )
                arrowLabel(isWorkerActive ? "JCross IR\n▶︎" : "JCross IR\n→", isActive: isWorkerActive)
                roleBox(
                    icon: "cloud",
                    title: "Worker\n(\(workerName))",
                    color: .purple,
                    desc: "JCrossのみ\n実ファイル不可",
                    isActive: isWorkerActive
                )
            }
            .padding(12)
            .background(Color.primary.opacity(0.04))
            .clipShape(RoundedRectangle(cornerRadius: 10))

            HStack {
                Text("Worker Provider:").font(.caption).foregroundStyle(.secondary)
                Picker("", selection: $state.workerProvider) {
                    Text("Claude").tag(CloudProvider.claude)
                    Text("OpenAI").tag(CloudProvider.openai)
                    Text("Gemini").tag(CloudProvider.gemini)
                    Text("DeepSeek").tag(CloudProvider.deepseek)
                }
                .pickerStyle(.segmented)
                .labelsHidden()
            }
            .padding(.top, 4)
        }
        .cardStyle()
    }

    private func roleBox(icon: String, title: String, color: Color, desc: String, isActive: Bool = false) -> some View {
        VStack(spacing: 4) {
            Image(systemName: icon)
                .font(.title3)
                .foregroundStyle(isActive ? .white : color)
                .padding(8)
                .background(isActive ? color : color.opacity(0.1))
                .clipShape(Circle())
                .shadow(color: isActive ? color.opacity(0.5) : .clear, radius: isActive ? 6 : 0)
                .scaleEffect(isActive ? 1.05 : 1.0)
                .animation(.easeInOut(duration: 0.2), value: isActive)
                
            Text(title)
                .font(.caption.bold())
                .multilineTextAlignment(.center)
            Text(desc)
                .font(.caption2)
                .foregroundStyle(isActive ? .primary : .secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
    }

    private func arrowLabel(_ text: String, isActive: Bool = false) -> some View {
        Text(text)
            .font(.caption2.bold())
            .foregroundStyle(isActive ? .primary : .secondary)
            .multilineTextAlignment(.center)
            .frame(width: 50)
            .scaleEffect(isActive ? 1.1 : 1.0)
            .animation(.easeInOut(duration: 0.2), value: isActive)
    }



    // MARK: - Access Log

    private var accessLogCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Label("アクセスログ", systemImage: "eye.slash.fill")
                    .font(.subheadline.bold())
                    .foregroundStyle(.red)
                Spacer()
                Text(AppLanguage.shared.t("JCross Info Exposed to External APIs", "外部 API に公開した JCross 情報"))
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }

            if state.accessLog.isEmpty {
                Text(AppLanguage.shared.t("No access yet", "まだアクセスなし"))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .padding(8)
            } else {
                ForEach(state.accessLog.prefix(8)) { entry in
                    HStack(spacing: 8) {
                        Image(systemName: toolIcon(entry.tool))
                            .font(.caption)
                            .foregroundStyle(entry.isHighRisk ? .red : .blue)
                            .frame(width: 16)

                        VStack(alignment: .leading, spacing: 1) {
                            Text(entry.path)
                                .font(.caption2.monospaced())
                                .lineLimit(1)
                            Text("\(entry.nodesExposed) nodes exposed, \(entry.secretsRedacted) secrets redacted")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }

                        Spacer()
                        Text(entry.timestamp.formatted(.dateTime.hour().minute().second()))
                            .font(.caption2.monospaced())
                            .foregroundStyle(.secondary)
                    }
                    .padding(6)
                    .background(entry.isHighRisk ? Color.red.opacity(0.08) : Color.clear)
                    .clipShape(RoundedRectangle(cornerRadius: 6))
                }
            }
        }
        .cardStyle()
    }

    // MARK: - Helpers

    private func loadModels() async {
        struct TagsResp: Decodable {
            struct Model: Decodable { let name: String }
            let models: [Model]
        }
        var loadedModels: [String] = []
        
        // 1. Ollama モデルの取得
        if let url = URL(string: "http://localhost:11434/api/tags"),
           let (data, _) = try? await URLSession.shared.data(from: url),
           let json = try? JSONDecoder().decode(TagsResp.self, from: data) {
            loadedModels.append(contentsOf: json.models.map { $0.name })
        }
        
        // 2. MLX モデルの取得
        loadedModels.append(contentsOf: MLXRunner.popularModels.map { $0.id })
        
        self.availableModels = loadedModels
        
        // 保存されているモデルが存在しない場合のみデフォルトを設定
        if !availableModels.contains(state.commanderModel) {
            if availableModels.contains("qwen2.5:1.5b") {
                state.commanderModel = "qwen2.5:1.5b"
            } else if let first = availableModels.first {
                state.commanderModel = first
            }
        }
    }

    private func toolIcon(_ tool: String) -> String {
        switch tool {
        case "read_file", "commander_fetch": return "doc.text"
        case "list_directory":               return "folder"
        case "search_code":                  return "magnifyingglass"
        case "write_diff":                   return "pencil"
        default:                             return "questionmark"
        }
    }

    private func modelTip(_ model: String) -> String {
        switch model {
        case "bitnet_b1_58-large": return "⚡️ BitNet: 1-bit LLM 推奨 — 超高速・省メモリでの JCross 変換"
        case "bonsai:8b":          return "🌳 Bonsai 8B: 最適化された NER 推論とパターン認識"
        case "qwen2.5:1.5b":       return "⚡️ 軽量・高速 — Commander として最適"
        case "qwen2.5:7b-instruct":return "🎯 高精度 instruction tuning — 複雑な要求に対応"
        case "gemma4:e2b":         return "🔥 5.1B — Google Gemma4 バランス型"
        case "gemma4:26b":         return "🧠 最高精度 (低速) — 複雑なコード分析に"
        case "verantyx-gemma:latest": return "🔮 Verantyx カスタムモデル"
        default:                   return ""
        }
    }
}

// MARK: - GatekeeperVaultCard

struct GatekeeperVaultCard: View {
    @ObservedObject var state: GatekeeperModeState
    @ObservedObject var vault: JCrossVault

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("JCross Vault", systemImage: "externaldrive.fill")
                .font(.subheadline.bold())
                .foregroundStyle(.orange)

            switch vault.vaultStatus {
            case .notInitialized:
                VStack(alignment: .leading, spacing: 8) {
                    Text(AppLanguage.shared.t("Vault uninitialized — Converting all workspace files to JCross", "Vault が未初期化です — ワークスペースの全ファイルを JCross 変換します"))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Button {
                        Task { await state.initializeVault() }
                    } label: {
                        Label("一括変換を開始", systemImage: "arrow.clockwise")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(.orange)
                }

            case .converting(let progress, let currentFile):
                VStack(alignment: .leading, spacing: 6) {
                    ProgressView(value: progress)
                        .tint(.orange)
                    HStack {
                        Text(currentFile)
                            .font(.caption2.monospaced())
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                        Spacer()
                        Text("\(Int(progress * 100))%")
                            .font(.caption2)
                    }
                    // ログ
                    if !vault.conversionLog.isEmpty {
                        ScrollView {
                            LazyVStack(alignment: .leading) {
                                ForEach(vault.conversionLog.suffix(8), id: \.self) { line in
                                    Text(line)
                                        .font(.caption2.monospaced())
                                        .foregroundStyle(line.contains("✓") ? .green : .primary)
                                }
                            }
                            .padding(6)
                        }
                        .frame(height: 100)
                        .background(Color.black.opacity(0.6))
                        .clipShape(RoundedRectangle(cornerRadius: 6))
                    }
                }

            case .ready(let fileCount, let lastConverted):
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Label("\(fileCount) ファイル変換済み", systemImage: "checkmark.circle.fill")
                            .foregroundStyle(.green)
                            .font(.caption.bold())
                        Text(AppLanguage.shared.t("Last Updated: \(lastConverted.formatted(.relative(presentation: .named)))", "最終更新: \(lastConverted.formatted(.relative(presentation: .named)))"))
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button {
                        Task { await vault.rebuildVault() }
                    } label: {
                        Label("再変換", systemImage: "arrow.triangle.2.circlepath")
                    }
                    .buttonStyle(.bordered)
                    .tint(.red)
                    .font(.caption)
                    
                    Button {
                        Task { await vault.updateDelta() }
                    } label: {
                        Label("差分更新", systemImage: "arrow.clockwise")
                    }
                    .buttonStyle(.bordered)
                    .font(.caption)
                }

            case .error(let msg):
                Label(msg, systemImage: "exclamationmark.triangle")
                    .foregroundStyle(.red)
                    .font(.caption)
            }
            
            Divider()
            
            // NER / 変換モデル設定
            OllamaNERStatusView()
                .padding(.top, 4)
        }
        .cardStyle()
    }
}

// MARK: - CardStyle ViewModifier

private extension View {
    func cardStyle() -> some View {
        self
            .padding(14)
            .background(.ultraThinMaterial)
            .clipShape(RoundedRectangle(cornerRadius: 12))
    }
}
