import SwiftUI

// MARK: - GatekeeperPipelineSettingsView
//
// Gatekeeperパイプラインの設定を縦フロー形式で表示するビュー。
// 各ステップを順番に設定でき、全体の動作フローを一覧できる。

struct GatekeeperPipelineSettingsView: View {

    @EnvironmentObject var app: AppState
    @ObservedObject private var state = GatekeeperPipelineState.shared
    @State private var expandedStep: PipelineSettingStep? = .intentEngine

    enum PipelineSettingStep: String, CaseIterable {
        case commander     = "🧠 Commander（ローカルLLM）"
        case intentEngine  = "③ 意図翻訳エンジン"
        case cloudProvider = "⑤ Cloud LLM プロバイダー"
        case security      = "🔐 セキュリティ設定"
        case test          = "🧪 テスト実行"
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 0) {
                headerView
                pipelineFlowView
                    .padding(.horizontal, 20)
                    .padding(.top, 24)
                settingsSectionView
                    .padding(.horizontal, 20)
                    .padding(.top, 24)
                    .padding(.bottom, 40)
            }
        }
        .background(Color(nsColor: .windowBackgroundColor))
    }

    // MARK: - Header

    private var headerView: some View {
        VStack(spacing: 6) {
            HStack {
                Image(systemName: "lock.shield.fill")
                    .font(.system(size: 22))
                    .foregroundColor(.cyan)
                Text("Gatekeeper Pipeline")
                    .font(.system(size: 20, weight: .bold, design: .monospaced))
                    .foregroundColor(.white)
                Spacer()
                Toggle("", isOn: $state.config.enabled)
                    .toggleStyle(SwitchToggleStyle(tint: .cyan))
                    .labelsHidden()
                    .onChange(of: state.config.enabled) { _ in state.saveConfig() }
                Text(state.config.enabled ? "ON" : "OFF")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundColor(state.config.enabled ? .cyan : .gray)
            }
            Text(AppLanguage.shared.t("Send zero-semantic IR to Cloud LLM, protecting semantics in local Vault", "意味ゼロのIRをCloud LLMへ送り、セマンティクスをローカルVaultで保護します"))
                .font(.system(size: 11))
                .foregroundColor(.gray)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 16)
        .background(Color.black.opacity(0.3))
    }

    // MARK: - Pipeline Flow Diagram

    private var pipelineFlowView: some View {
        VStack(spacing: 0) {
            Text(AppLanguage.shared.t("Processing Flow", "処理フロー"))
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(.gray)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.bottom, 12)

            VStack(spacing: 0) {
                pipelineNode(
                    icon: "text.alignleft",
                    step: "①",
                    title: "自然言語指示",
                    detail: "「このコードをRustに変換して」",
                    color: .white,
                    isLocal: true,
                    isActive: state.currentStep == nil && !state.isRunning
                )
                connector(label: "ユーザー入力")

                pipelineNode(
                    icon: "arrow.triangle.branch",
                    step: "②",
                    title: "JCross IR 生成",
                    detail: "ソースを6軸IR化 + 実値をVaultへ",
                    color: .blue,
                    isLocal: true,
                    isActive: state.currentStep == .irGeneration
                )
                connector(label: "意味を切り離す")

                // ── Commander ノード (ローカルLLM) ───────────────────────────────
                pipelineNode(
                    icon: "brain.head.profile",
                    step: "🧠",
                    title: commanderNodeLabel,
                    detail: "役割: 意図解析 / ファイル選択 / IRクエリ生成 / バリデーション指示",
                    color: .mint,
                    isLocal: true,
                    isActive: state.currentStep == .irGeneration  // Commander は IR 生成と同期
                )
                connector(label: "Commander が構造コマンドを生成")

                pipelineNode(
                    icon: "brain",
                    step: "③",
                    title: intentEngineLabel,
                    detail: "自然言語 → 構造コマンド（意味ゼロ）",
                    color: .purple,
                    isLocal: true,
                    isActive: state.currentStep == .intentTranslate
                )
                connector(label: "構造コマンド化")

                pipelineNode(
                    icon: "building.columns",
                    step: "④",
                    title: "Gatekeeper Prompt Build",
                    detail: "X/Y/Z/W/V軸のみ公開（U軸=意味は除外）",
                    color: .orange,
                    isLocal: true,
                    isActive: state.currentStep == .promptBuild
                )
                connector(label: "意味ゼロプロンプト")

                pipelineNode(
                    icon: "cloud.fill",
                    step: "⑤",
                    title: cloudProviderLabel,
                    detail: "構造パズルを解く盲目ソルバー",
                    color: .cyan,
                    isLocal: false,
                    isActive: state.currentStep == .llmCall
                )
                connector(label: "GraphPatch JSON")

                pipelineNode(
                    icon: "wrench.and.screwdriver",
                    step: "⑥",
                    title: "GraphPatch 解析",
                    detail: "Cloud LLMの構造パッチを解析",
                    color: .yellow,
                    isLocal: true,
                    isActive: state.currentStep == .patchParse
                )
                connector(label: "実値を注入")

                pipelineNode(
                    icon: "key.fill",
                    step: "⑦",
                    title: "Vault 注入・復元",
                    detail: "ローカルVaultで実コードに変換",
                    color: .green,
                    isLocal: true,
                    isActive: state.currentStep == .vaultRehydrate
                )
            }
            .padding(16)
            .background(
                RoundedRectangle(cornerRadius: 12)
                    .fill(Color.black.opacity(0.4))
                    .overlay(
                        RoundedRectangle(cornerRadius: 12)
                            .stroke(Color.white.opacity(0.08), lineWidth: 1)
                    )
            )
        }
    }

    private func pipelineNode(
        icon: String, step: String, title: String, detail: String,
        color: Color, isLocal: Bool, isActive: Bool
    ) -> some View {
        HStack(spacing: 12) {
            // ステップバッジ
            ZStack {
                Circle()
                    .fill(isActive ? color : color.opacity(0.15))
                    .frame(width: 36, height: 36)
                    .overlay(
                        Circle().stroke(color.opacity(isActive ? 1 : 0.4), lineWidth: 1.5)
                    )
                    .shadow(color: isActive ? color.opacity(0.5) : .clear, radius: 6)

                if isActive && state.isRunning {
                    // アクティブ時のアニメーション
                    Circle()
                        .stroke(color.opacity(0.3), lineWidth: 2)
                        .frame(width: 44, height: 44)
                        .scaleEffect(isActive ? 1.1 : 1)
                        .animation(.easeInOut(duration: 0.8).repeatForever(autoreverses: true), value: isActive)
                }

                Image(systemName: icon)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(isActive ? .white : color.opacity(0.7))
            }

            // ラベル部分
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(step)
                        .font(.system(size: 10, weight: .bold, design: .monospaced))
                        .foregroundColor(color.opacity(0.8))
                    Text(title)
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(isActive ? .white : Color(nsColor: .labelColor))
                    Spacer()
                    // Local/Cloud バッジ
                    Text(isLocal ? "LOCAL" : "CLOUD")
                        .font(.system(size: 9, weight: .bold))
                        .padding(.horizontal, 5)
                        .padding(.vertical, 2)
                        .background(
                            Capsule().fill(isLocal ? Color.green.opacity(0.2) : Color.cyan.opacity(0.2))
                        )
                        .foregroundColor(isLocal ? .green : .cyan)
                        .overlay(Capsule().stroke(isLocal ? Color.green.opacity(0.4) : Color.cyan.opacity(0.4), lineWidth: 1))
                }
                Text(detail)
                    .font(.system(size: 10))
                    .foregroundColor(.gray)
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 8)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(isActive ? color.opacity(0.08) : Color.clear)
        )
        .animation(.easeInOut(duration: 0.2), value: isActive)
    }

    private func connector(label: String) -> some View {
        HStack(spacing: 0) {
            Spacer().frame(width: 26)
            Rectangle()
                .fill(Color.white.opacity(0.12))
                .frame(width: 2, height: 18)
            Text(label)
                .font(.system(size: 9))
                .foregroundColor(.gray)
                .padding(.leading, 8)
            Spacer()
        }
        .padding(.horizontal, 8)
    }

    // MARK: - Settings Sections

    private var settingsSectionView: some View {
        VStack(spacing: 12) {
            ForEach(PipelineSettingStep.allCases, id: \.self) { step in
                settingsSectionCard(for: step)
            }
        }
    }

    @ViewBuilder
    private func settingsSectionCard(for step: PipelineSettingStep) -> some View {
        VStack(spacing: 0) {
            // ヘッダー（タップで展開）
            Button(action: {
                withAnimation(.easeInOut(duration: 0.2)) {
                    expandedStep = expandedStep == step ? nil : step
                }
            }) {
                HStack {
                    Text(step.rawValue)
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(.white)
                    Spacer()
                    stepBadge(for: step)
                    Image(systemName: expandedStep == step ? "chevron.up" : "chevron.down")
                        .font(.system(size: 10))
                        .foregroundColor(.gray)
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 12)
            }
            .buttonStyle(.plain)

            if expandedStep == step {
                Divider().opacity(0.2)
                VStack(spacing: 14) {
                    switch step {
                    case .commander:     commanderSettings
                    case .intentEngine:  intentEngineSettings
                    case .cloudProvider: cloudProviderSettings
                    case .security:      securitySettings
                    case .test:          testRunSettings
                    }
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 14)
            }
        }
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(Color.black.opacity(0.35))
                .overlay(
                    RoundedRectangle(cornerRadius: 10)
                        .stroke(Color.white.opacity(0.08), lineWidth: 1)
                )
        )
    }

    // MARK: - Commander Settings

    private var commanderSettings: some View {
        VStack(alignment: .leading, spacing: 10) {
            // 役割説明
            Text(AppLanguage.shared.t("Commander Role", "Commander の役割"))
                .font(.system(size: 11, weight: .semibold)).foregroundColor(.gray)

            VStack(alignment: .leading, spacing: 6) {
                ForEach([
                    ("brain.head.profile", Color.mint,   "意図解析",         "ユーザーの自然言語を構造コマンドに変換"),
                    ("folder.badge.gearshape", Color.blue, "ファイル選択",     "Vault の索引から変換対象を特定"),
                    ("doc.text.magnifyingglass", Color.purple, "IRクエリ生成", "Cloud LLMへ送る JCross IR を組み立て"),
                    ("checkmark.shield", Color.orange, "バリデーション",      "Cloud LLM の応答を検証し、失敗時は再送を指示"),
                    ("lock.doc", Color.green, "セキュリティゲート",           "送信前に実値が含まれていないか最終確認"),
                ], id: \.0) { icon, color, title, detail in
                    infoRow(icon: icon, color: color, title: title, detail: detail)
                }
            }

            Divider().opacity(0.15)

            // Commander モデル表示（Privacy 設定の Commander と連動）
            HStack {
                Image(systemName: "cpu").foregroundColor(.mint)
                Text(AppLanguage.shared.t("Current Commander Model", "現在の Commander モデル"))
                    .font(.system(size: 11)).foregroundColor(.secondary)
                Spacer()
                Text(GatekeeperModeState.shared.commanderModel.isEmpty
                     ? "未設定 → Privacy設定で選択"
                     : GatekeeperModeState.shared.commanderModel)
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundColor(.mint)
                    .lineLimit(1)
            }
            .padding(10)
            .background(RoundedRectangle(cornerRadius: 8).fill(Color.mint.opacity(0.06))
                .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.mint.opacity(0.2), lineWidth: 1)))

            Text(AppLanguage.shared.t("💡 Commander model size does not affect conversion quality. Since it only handles intent analysis (classification), a small ~7B model is sufficient. Quality is determined by the Cloud LLM (⑤).", "💡 Commander のモデルサイズは変換品質に影響しません。意図解析（分類タスク）のみを担当するため、7B程度の小モデルで十分です。変換品質は Cloud LLM（⑤）が決定します。"))
                .font(.system(size: 9))
                .foregroundColor(.gray)
                .padding(.top, 4)
        }
    }

    // MARK: - Intent Engine Settings

    private var intentEngineSettings: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(AppLanguage.shared.t("Intent Translation Engine (BitNet equivalent)", "意図翻訳エンジン（BitNet相当）"))
                .font(.system(size: 11, weight: .semibold))
                .foregroundColor(.gray)

            ForEach(GatekeeperIntentEngine.allCases, id: \.self) { engine in
                Button(action: {
                    state.config.intentEngine = engine
                    state.saveConfig()
                }) {
                    HStack(spacing: 10) {
                        Image(systemName: state.config.intentEngine == engine
                              ? "checkmark.circle.fill" : "circle")
                            .foregroundColor(state.config.intentEngine == engine ? .cyan : .gray)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(engine.rawValue)
                                .font(.system(size: 12, weight: .medium))
                                .foregroundColor(.white)
                            Text(engine.description)
                                .font(.system(size: 10))
                                .foregroundColor(.gray)
                        }
                        Spacer()
                    }
                }
                .buttonStyle(.plain)
                .padding(10)
                .background(
                    RoundedRectangle(cornerRadius: 8)
                        .fill(state.config.intentEngine == engine ? Color.cyan.opacity(0.08) : Color.clear)
                        .overlay(
                            RoundedRectangle(cornerRadius: 8)
                                .stroke(state.config.intentEngine == engine ? Color.cyan.opacity(0.4) : Color.white.opacity(0.05), lineWidth: 1)
                        )
                )
            }

            if state.config.intentEngine == .ollama {
                VStack(alignment: .leading, spacing: 4) {
                    Text(AppLanguage.shared.t("Ollama Model", "Ollamaモデル"))
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundColor(.gray)
                    
                    if app.ollamaModels.isEmpty {
                        TextField("gemma4:26b", text: $state.config.intentOllamaModel)
                            .textFieldStyle(.plain)
                            .font(.system(size: 12, design: .monospaced))
                            .padding(8)
                            .background(
                                RoundedRectangle(cornerRadius: 6)
                                    .fill(Color.black.opacity(0.3))
                                    .overlay(RoundedRectangle(cornerRadius: 6).stroke(Color.white.opacity(0.1), lineWidth: 1))
                            )
                            .onChange(of: state.config.intentOllamaModel) { _ in 
                                state.saveConfig()
                                if app.operationMode == .gatekeeper {
                                    app.activeOllamaModel = state.config.intentOllamaModel
                                }
                            }
                    } else {
                        Picker("", selection: $state.config.intentOllamaModel) {
                            ForEach(app.ollamaModels, id: \.self) { m in
                                Text(m).tag(m)
                            }
                        }
                        .pickerStyle(.menu)
                        .onChange(of: state.config.intentOllamaModel) { _ in 
                            state.saveConfig()
                            if app.operationMode == .gatekeeper {
                                app.activeOllamaModel = state.config.intentOllamaModel
                            }
                        }
                    }
                }
            }
        }
    }

    // MARK: - Cloud Provider Settings

    private var cloudProviderSettings: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(AppLanguage.shared.t("Cloud LLM Provider (Structural Solver)", "Cloud LLMプロバイダー（構造ソルバー）"))
                .font(.system(size: 11, weight: .semibold))
                .foregroundColor(.gray)

            // プロバイダー選択
            Picker("プロバイダー", selection: $state.config.cloudProvider) {
                ForEach(GatekeeperCloudProvider.allCases, id: \.self) { provider in
                    Text(provider.rawValue).tag(provider)
                }
            }
            .pickerStyle(.menu)
            .onChange(of: state.config.cloudProvider) { provider in
                state.config.cloudModel = provider.defaultModel
                state.saveConfig()
            }

            // モデルとAPIキーはメインの「API Keys」設定を自動参照する
            switch state.config.cloudProvider {
            case .anthropic:
                Text(AppLanguage.shared.t("Anthropic API key and model use the 'API Keys' settings", "AnthropicのAPIキーとモデルは「API Keys」設定を使用します"))
                    .font(.system(size: 10))
                    .foregroundColor(.gray)
            case .openRouter:
                labeledField("OpenRouterモデル", text: $state.config.cloudModel,
                             placeholder: "anthropic/claude-3.5-sonnet", onChange: { state.saveConfig() })
                secureField("OpenRouter APIキー", text: $state.config.openRouterApiKey,
                            placeholder: "sk-or-...", onChange: { state.saveConfig() })
            case .deepSeek:
                Text(AppLanguage.shared.t("DeepSeek API key and model use the 'API Keys' settings", "DeepSeekのAPIキーとモデルは「API Keys」設定を使用します"))
                    .font(.system(size: 10))
                    .foregroundColor(.gray)
            case .ollama:
                Text(AppLanguage.shared.t("Ollama model uses the 'API Keys' or local settings", "Ollamaのモデルは「API Keys」またはローカル設定を使用します"))
                    .font(.system(size: 10))
                    .foregroundColor(.gray)
            }

            // max tokens
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(AppLanguage.shared.t("Max Tokens", "最大トークン"))
                        .font(.system(size: 11))
                        .foregroundColor(.gray)
                    Spacer()
                    Text("\(state.config.maxTokens)")
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundColor(.cyan)
                }
                Slider(value: Binding(
                    get: { Double(state.config.maxTokens) },
                    set: { state.config.maxTokens = Int($0); state.saveConfig() }
                ), in: 512...8192, step: 512)
                .accentColor(.cyan)
            }
        }
    }

    // MARK: - Security Settings

    private var securitySettings: some View {
        VStack(alignment: .leading, spacing: 10) {
            infoRow(icon: "lock.shield.fill", color: .green,
                    title: "Semantic Zero（U軸隔離）",
                    detail: "変数名・関数名・数値定数はすべてVaultに隔離。Cloud LLMには届かない。")
            infoRow(icon: "eye.slash.fill", color: .cyan,
                    title: "構造のみ公開（X/Y/Z/W/V軸）",
                    detail: "制御フロー・データフロー・型カテゴリの抽象情報のみ送信。")
            infoRow(icon: "arrow.triangle.2.circlepath", color: .orange,
                    title: "決定論的逆変換",
                    detail: "VaultPatcherはAIを使わない固定テンプレート。ハルシネーション不可能。")
            infoRow(icon: "number.circle.fill", color: .red,
                    title: "数値定数の完全隔離",
                    detail: "gus_massa原則: round(x*1.21, 2) の1.21はVaultのみに存在。")
        }
    }

    // MARK: - Test Run Settings

    private var testRunSettings: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(AppLanguage.shared.t("Connection Test", "接続テスト"))
                .font(.system(size: 11, weight: .semibold))
                .foregroundColor(.gray)

            Button(action: {
                Task {
                    let config = state.config
                    let testPrompt = "[GATEKEEPER TEST] Respond with: {\"status\": \"ok\", \"newControlFlow\": \"CTRL:test\"}"
                    let _ = await GatekeeperUniversalLLMClient.shared.complete(
                        prompt: testPrompt, config: config
                    )
                }
            }) {
                HStack {
                    Image(systemName: "play.circle.fill")
                    Text(AppLanguage.shared.t("Cloud LLM Connection Test", "Cloud LLM 接続テスト"))
                }
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(.white)
                .padding(.horizontal, 16)
                .padding(.vertical, 8)
                .background(Capsule().fill(Color.cyan.opacity(0.25)))
                .overlay(Capsule().stroke(Color.cyan.opacity(0.5), lineWidth: 1))
            }
            .buttonStyle(.plain)

            if !state.stepLog.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text(AppLanguage.shared.t("Recent Logs", "直近のログ"))
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundColor(.gray)
                    ForEach(state.stepLog.suffix(5), id: \.timestamp) { entry in
                        HStack(alignment: .top, spacing: 6) {
                            Text(entry.step)
                                .font(.system(size: 9, weight: .bold, design: .monospaced))
                                .foregroundColor(.cyan)
                                .frame(width: 60, alignment: .leading)
                            Text(entry.detail)
                                .font(.system(size: 9))
                                .foregroundColor(.gray)
                                .lineLimit(2)
                                // テキスト震え防止: 出力更新時のアニメーション干渉を排除
                                .transaction { t in t.animation = nil }
                        }
                    }
                }
                .padding(10)
                .background(
                    RoundedRectangle(cornerRadius: 6)
                        .fill(Color.black.opacity(0.3))
                )
                // ログ追加時の一瞬消え・震えを防ぐ
                .transaction { t in t.animation = nil }
            }
        }
    }

    // MARK: - Computed Labels

    private var commanderNodeLabel: String {
        let model = GatekeeperModeState.shared.commanderModel
        if model.isEmpty { return "Commander（未設定）" }
        return "Commander: " + (model.components(separatedBy: "/").last ?? model)
    }

    private var intentEngineLabel: String {
        switch state.config.intentEngine {
        case .ruleBased: return "ルールベース翻訳"
        case .ollama:    return "Ollama 意図翻訳"
        case .mlx:       return "MLX 意図翻訳"
        case .bitNet:    return "BitNet 意図翻訳"
        }
    }

    private var cloudProviderLabel: String {
        "\(state.config.cloudProvider.rawValue) / \(state.config.cloudModel)"
    }

    // MARK: - Step Badge

    private func stepBadge(for step: PipelineSettingStep) -> some View {
        let label: String
        let color: Color
        switch step {
        case .commander:
            let model = GatekeeperModeState.shared.commanderModel
            label = model.isEmpty ? "未設定" : String(model.components(separatedBy: "/").last ?? model).prefix(12).description
            color = .mint
        case .intentEngine:
            label = state.config.intentEngine == .ruleBased ? "ルール" : "LLM"
            color = .purple
        case .cloudProvider:
            label = state.config.cloudProvider == .ollama ? "ローカル" : "クラウド"
            color = state.config.cloudProvider == .ollama ? .green : .cyan
        case .security:
            label = "Semantic Zero"
            color = .green
        case .test:
            label = state.isRunning ? "実行中…" : "待機中"
            color = state.isRunning ? .orange : .gray
        }

        return Text(label)
            .font(.system(size: 9, weight: .bold))
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(Capsule().fill(color.opacity(0.2)))
            .foregroundColor(color)
            .overlay(Capsule().stroke(color.opacity(0.4), lineWidth: 1))
    }

    // MARK: - Helper Views

    private func labeledField(
        _ label: String, text: Binding<String>, placeholder: String, onChange: @escaping () -> Void
    ) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.system(size: 10, weight: .semibold))
                .foregroundColor(.gray)
            TextField(placeholder, text: text)
                .textFieldStyle(.plain)
                .font(.system(size: 12, design: .monospaced))
                .padding(8)
                .background(
                    RoundedRectangle(cornerRadius: 6)
                        .fill(Color.black.opacity(0.3))
                        .overlay(RoundedRectangle(cornerRadius: 6).stroke(Color.white.opacity(0.1), lineWidth: 1))
                )
                .onChange(of: text.wrappedValue) { _ in onChange() }
        }
    }

    private func secureField(
        _ label: String, text: Binding<String>, placeholder: String, onChange: @escaping () -> Void
    ) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.system(size: 10, weight: .semibold))
                .foregroundColor(.gray)
            SecureField(placeholder, text: text)
                .textFieldStyle(.plain)
                .font(.system(size: 12, design: .monospaced))
                .padding(8)
                .background(
                    RoundedRectangle(cornerRadius: 6)
                        .fill(Color.black.opacity(0.3))
                        .overlay(RoundedRectangle(cornerRadius: 6).stroke(Color.orange.opacity(0.2), lineWidth: 1))
                )
                .onChange(of: text.wrappedValue) { _ in onChange() }
        }
    }

    private func infoRow(icon: String, color: Color, title: String, detail: String) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: icon)
                .foregroundColor(color)
                .font(.system(size: 14))
                .frame(width: 20)
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(.white)
                Text(detail)
                    .font(.system(size: 10))
                    .foregroundColor(.gray)
            }
        }
        .padding(10)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(color.opacity(0.06))
                .overlay(RoundedRectangle(cornerRadius: 8).stroke(color.opacity(0.15), lineWidth: 1))
        )
    }
}
