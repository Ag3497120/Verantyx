import Foundation
import SwiftUI

// MARK: - OllamaNEREngine
//
// Ollama ローカルサーバー経由で NER を実行する BitNetTranspilerInterface 実装。
// JCross トランスパイルの「センシティブ識別子抽出」タスクに特化。
//
// 優先モデル選択:
//   1. qwen2.5:1.5b  — 最軽量・低レイテンシ (~100ms/request)
//   2. gemma4:e2b    — バランス型 (5.1B)
//   3. gemma4:26b    — 高精度 (インストール済み最大)
//
// フォールバック:
//   Ollama が応答しない場合 → RuleBaseNEREngine に自動切替

final class OllamaNEREngine: BitNetTranspilerInterface, @unchecked Sendable {

    // MARK: - Properties

    private let baseURL: String
    private let preferredModel: String
    private let fallbackModels: [String]
    private let session: URLSession

    static let nerSystem = """
    You are a code security analyzer specialized in detecting sensitive identifiers.
    Your ONLY task: identify identifiers that should be anonymized before sending code to an external AI.

    Sensitive identifiers include:
    - API keys, secrets, tokens, passwords, credentials
    - Proprietary function/class names that reveal business logic
    - Internal variable names with domain-specific meaning
    - File paths, IP addresses, hostnames
    - Database names, table names, schema names

    Output ONLY a compact JSON array of strings. No explanation, no markdown, no comments.
    Example output: ["processStripePayment","apiKey","serverIP","AuthTokenGenerator"]
    """

    // MARK: - Init

    init(
        baseURL: String = "http://localhost:11434",
        preferredModel: String = "hf.co/bakrianto/Bonsai-8B-gguf",
        fallbackModels: [String] = ["qwen2.5:1.5b", "gemma4:e2b", "gemma4:26b", "verantyx-gemma:latest"]
    ) {
        self.baseURL      = baseURL
        self.preferredModel = preferredModel
        self.fallbackModels = fallbackModels

        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest  = 30
        config.timeoutIntervalForResource = 60
        self.session = URLSession(configuration: config)
    }

    // MARK: - BitNetTranspilerInterface

    func extractSensitiveIdentifiers(from code: String) async -> [String] {
        // 最初に利用可能なモデルを選択
        guard let model = await resolveModel() else {
            // Ollama 応答なし → BitNetフォールバック → ルールベースフォールバック
            if let bitnetConfig = BitNetConfig.load(), bitnetConfig.isValid {
                print("⚠️ Ollama not available, falling back to BitNet for NER")
                return await BitNetNEREngine(config: bitnetConfig).extractSensitiveIdentifiers(from: code)
            }
            return await RuleBaseNEREngine().extractSensitiveIdentifiers(from: code)
        }

        let snippet = String(code.prefix(6000))

        let userPrompt = """
        Analyze this code and output ONLY a JSON array of sensitive identifiers:

        ```
        \(snippet)
        ```

        JSON array only:
        """

        do {
            let result = try await callOllama(model: model, prompt: userPrompt)
            let parsed = parseJSONArray(from: result)

            // Ollama の結果が空なら RuleBase で補完
            if parsed.isEmpty {
                let ruleBase = await RuleBaseNEREngine().extractSensitiveIdentifiers(from: code)
                return ruleBase
            }

            // RuleBase との結果をマージ（より多く検出）
            let ruleBase = await RuleBaseNEREngine().extractSensitiveIdentifiers(from: code)
            return Array(Set(parsed + ruleBase))

        } catch {
            if let bitnetConfig = BitNetConfig.load(), bitnetConfig.isValid {
                print("⚠️ Ollama error, falling back to BitNet for NER")
                return await BitNetNEREngine(config: bitnetConfig).extractSensitiveIdentifiers(from: code)
            }
            return await RuleBaseNEREngine().extractSensitiveIdentifiers(from: code)
        }
    }

    // MARK: - Model Resolution

    private func resolveModel() async -> String? {
        // 利用可能なモデル一覧を取得
        guard let available = await fetchAvailableModels() else { return nil }

        // ユーザー設定のデフォルトモデルを最優先に追加
        let userModel = await MainActor.run { AppState.shared?.activeOllamaModel ?? "" }
        var candidates = [preferredModel] + fallbackModels
        if !userModel.isEmpty {
            candidates.insert(userModel, at: 0)
        }

        // 優先モデルから順番に確認
        for candidate in candidates {
            if available.contains(where: { $0.hasPrefix(candidate.components(separatedBy: ":").first ?? candidate) }) {
                return candidate
            }
        }

        // 何もなければ最初のモデルを使用
        return available.first
    }

    private func fetchAvailableModels() async -> [String]? {
        guard let url = URL(string: "\(baseURL)/api/tags") else { return nil }
        do {
            let (data, _) = try await session.data(from: url)
            let response  = try JSONDecoder().decode(OllamaTagsResponse.self, from: data)
            return response.models.map { $0.name }
        } catch {
            return nil
        }
    }

    // MARK: - Ollama API Call (Generate)

    private func callOllama(model: String, prompt: String) async throws -> String {
        guard let url = URL(string: "\(baseURL)/api/generate") else {
            throw OllamaError.invalidURL
        }

        let body = OllamaGenerateRequest(
            model: model,
            prompt: prompt,
            system: Self.nerSystem,
            stream: false,
            options: OllamaOptions(
                temperature: 0.05,
                numPredict: 256,
                numCtx: 4096,
                stop: ["\n\n", "```"]
            )
        )

        let bodyData = try JSONEncoder().encode(body)
        var request  = URLRequest(url: url)
        request.httpMethod  = "POST"
        request.httpBody    = bodyData
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let (data, response) = try await session.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              (200..<300).contains(httpResponse.statusCode)
        else { throw OllamaError.badStatus }

        let decoded = try JSONDecoder().decode(OllamaGenerateResponse.self, from: data)
        return decoded.response
    }

    // MARK: - JSON Array Parser

    private func parseJSONArray(from text: String) -> [String] {
        // まず ``` で囲まれたコードブロックを取り除く
        let cleaned = text
            .replacingOccurrences(of: "```json", with: "")
            .replacingOccurrences(of: "```",     with: "")
            .trimmingCharacters(in: .whitespacesAndNewlines)

        // JSON 配列を抽出
        guard let start = cleaned.firstIndex(of: "["),
              let end   = cleaned.lastIndex(of: "]"),
              start <= end
        else { return [] }

        let jsonStr = String(cleaned[start...end])
        guard let data = jsonStr.data(using: .utf8),
              let array = try? JSONDecoder().decode([String].self, from: data)
        else { return [] }

        return array.filter { str in
            str.count >= 3 &&
            str.allSatisfy { $0.isLetter || $0.isNumber || $0 == "_" }
        }
    }

    // MARK: - Error

    enum OllamaError: Error {
        case invalidURL
        case badStatus
        case noModel
    }
}

// MARK: - Ollama API Models

private struct OllamaTagsResponse: Decodable {
    struct Model: Decodable { let name: String }
    let models: [Model]
}

private struct OllamaGenerateRequest: Encodable {
    let model:   String
    let prompt:  String
    let system:  String
    let stream:  Bool
    let options: OllamaOptions
}

private struct OllamaOptions: Encodable {
    let temperature: Double
    let numPredict:  Int
    let numCtx:      Int
    let stop:        [String]

    enum CodingKeys: String, CodingKey {
        case temperature
        case numPredict  = "num_predict"
        case numCtx      = "num_ctx"
        case stop
    }
}

private struct OllamaGenerateResponse: Decodable {
    let response: String
}

// MARK: - OllamaNEREngineManager (ObservableObject)

@MainActor
final class OllamaNEREngineManager: ObservableObject {

    static let shared = OllamaNEREngineManager()

    enum Status: Equatable {
        case unknown
        case checking
        case ready(model: String, allModels: [String])
        case notRunning
        case error(String)
    }

    @Published var status: Status = .checking
    @Published var selectedModel: String = "qwen2.5:1.5b"
    @Published var engine: OllamaNEREngine?

    // NER テスト用
    @Published var testResult: [String] = []
    @Published var isTesting = false
    @Published var lastTestDuration: Double = 0

    // モデルダウンロード用
    @Published var isDownloadingBonsai = false
    @Published var bonsaiDownloadProgress: Double = 0.0
    @Published var bonsaiDownloadStatus: String = ""

    private init() {
        Task { await refresh() }
    }

    func refresh() async {
        status = .checking
        do {
            let base = AppState.shared?.exoEnabled == true && !(AppState.shared?.exoEndpoint.isEmpty ?? true)
                ? AppState.shared!.exoEndpoint : "http://localhost:11434"
            let url = URL(string: "\(base)/api/tags")!
            let (data, _) = try await URLSession.shared.data(from: url)

            struct TagsResp: Decodable {
                struct Model: Decodable { let name: String }
                let models: [Model]
            }
            let resp = try JSONDecoder().decode(TagsResp.self, from: data)
            let names = resp.models.map { $0.name }

            // NER 向け最適モデルを自動選択
            let preferred = pickBestNERModel(from: names)
            selectedModel = preferred
            engine = OllamaNEREngine(baseURL: base, preferredModel: preferred)

            status = .ready(model: preferred, allModels: names)
        } catch {
            status = .notRunning
            // フォールバックエンジン（ルールベース）を使用
            engine = nil
        }
    }

    /// NER タスクに最適なモデルを選択
    /// - 優先: 小さい・高速・instruction tuned
    private func pickBestNERModel(from available: [String]) -> String {
        // ユーザーがカスタムしたモデル（デフォルト）を最優先
        let userModel = AppState.shared?.activeOllamaModel ?? ""
        if !userModel.isEmpty && available.contains(userModel) {
            return userModel
        }

        let priority = [
            "bitnet_b1_58-large",
            "bonsai:8b",
            "qwen2.5:1.5b",
            "qwen2.5:7b-instruct",
            "gemma4:e2b",
            "nemotron-orchestrator:latest",
            "gemma4:26b",
            "verantyx-gemma:latest",
        ]
        for candidate in priority {
            if available.contains(candidate) { return candidate }
        }
        return available.first ?? "qwen2.5:1.5b"
    }

    // MARK: - Test NER

    func runTest(code: String = #"""
        let stripeKey = "sk_live_4xKf2nPqR7mWsT9vY3hZ"
        let serverIP = "192.168.1.45"
        func processStripePayment(amount: Double) async -> Bool { ... }
        class AuthTokenGenerator { ... }
        """#) async {
        guard let eng = engine else { return }
        isTesting = true
        let start = Date()
        testResult = await eng.extractSensitiveIdentifiers(from: code)
        lastTestDuration = Date().timeIntervalSince(start)
        isTesting = false
    }

    // MARK: - Download Bonsai-8B

    func downloadBonsai8B() async {
        isDownloadingBonsai = true
        bonsaiDownloadProgress = 0.0
        bonsaiDownloadStatus = "Starting download..."

        // 実際のHuggingFace上に存在するBonsai-8BのGGUFリポジトリを指定（Ollama 0.3.0+ の hf.co/ 形式）
        let modelRepo = "hf.co/bakrianto/Bonsai-8B-gguf"
        let stream = OllamaClient.shared.pullModel(name: modelRepo)
        
        do {
            for try await progress in stream {
                await MainActor.run {
                    self.bonsaiDownloadStatus = progress.status.capitalized
                    self.bonsaiDownloadProgress = progress.percent
                }
            }
            await MainActor.run {
                self.bonsaiDownloadStatus = "Completed"
            }
            // リフレッシュしてプルダウンに反映
            await refresh()
        } catch {
            await MainActor.run {
                self.bonsaiDownloadStatus = "Failed: \(error.localizedDescription)"
            }
        }
        await MainActor.run {
            self.isDownloadingBonsai = false
        }
    }
}

// MARK: - OllamaNERStatusView

struct OllamaNERStatusView: View {
    @ObservedObject private var mgr = OllamaNEREngineManager.shared
    @State private var showModelPicker = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {

            // Header
            HStack {
                Image(systemName: "brain.head.profile")
                    .foregroundStyle(GatekeeperModeState.shared.useOllamaNER ? .blue : .secondary)
                Text(AppLanguage.shared.t("Ollama NER Engine", "Ollama NER エンジン"))
                    .font(.headline)
                Spacer()
                if GatekeeperModeState.shared.useOllamaNER {
                    Button { Task { await mgr.refresh() } } label: {
                        Image(systemName: "arrow.clockwise")
                    }.buttonStyle(.borderless)
                }
            }

            Divider()

            if !GatekeeperModeState.shared.useOllamaNER {
                Label(AppLanguage.shared.t("Ollama NER is disabled in Privacy settings.", "プライバシー設定で Ollama NER が無効化されています。"), systemImage: "bolt.slash.fill")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                switch mgr.status {
            case .checking:
                HStack { ProgressView().scaleEffect(0.7); Text(AppLanguage.shared.t("Checking connection...", "接続確認中...")).font(.caption) }

            case .ready(let model, let allModels):
                readyView(model: model, allModels: allModels)

            case .notRunning:
                notRunningView

            case .error(let msg):
                Label(msg, systemImage: "xmark.circle").foregroundStyle(.red).font(.caption)

            case .unknown:
                EmptyView()
            }
            } // end else
        }
        .padding()
        .background(.ultraThinMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    // MARK: - Ready View

    private func readyView(model: String, allModels: [String]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Label(AppLanguage.shared.t("Ollama Running", "Ollama 稼働中"), systemImage: "checkmark.circle.fill")
                    .foregroundStyle(.green)
                    .font(.subheadline.bold())
                Spacer()
            }

            // モデル選択
            HStack {
                Text(AppLanguage.shared.t("NER Model", "NER モデル"))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Picker("", selection: $mgr.selectedModel) {
                    ForEach(allModels, id: \.self) { name in
                        HStack {
                            Image(systemName: modelIcon(name))
                            Text(name)
                        }.tag(name)
                    }
                }
                .pickerStyle(.menu)
                .onChange(of: mgr.selectedModel) { newModel in
                    mgr.engine = OllamaNEREngine(preferredModel: newModel)
                }
            }

            // モデル詳細
            if let detail = modelDetail(mgr.selectedModel) {
                Text(detail)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .padding(6)
                    .background(Color.blue.opacity(0.08))
                    .clipShape(RoundedRectangle(cornerRadius: 6))
            }

            // NER 向け推奨モデル (Bonsai-8B) のダウンロード提案
            if !allModels.contains(where: { $0.contains("Bonsai") || $0.contains("bonsai") }) {
                Divider()
                VStack(alignment: .leading, spacing: 8) {
                    HStack(spacing: 4) {
                        Image(systemName: "sparkles")
                        Text("Recommended: Bonsai-8B (Optimized for NER)")
                    }
                    .font(.caption.bold())
                    .foregroundStyle(.blue)
                    
                    if mgr.isDownloadingBonsai {
                        VStack(alignment: .leading, spacing: 4) {
                            HStack {
                                Text(mgr.bonsaiDownloadStatus).font(.caption2).foregroundStyle(.secondary)
                                Spacer()
                                Text("\(Int(mgr.bonsaiDownloadProgress * 100))%")
                                    .font(.caption2.monospacedDigit())
                            }
                            ProgressView(value: mgr.bonsaiDownloadProgress)
                                .progressViewStyle(.linear)
                                .tint(.blue)
                        }
                        .padding(.vertical, 4)
                    } else {
                        Button {
                            Task { await mgr.downloadBonsai8B() }
                        } label: {
                            Label(AppLanguage.shared.t("Download Bonsai-8B", "Bonsai-8B をダウンロード"), systemImage: "arrow.down.circle.fill")
                        }
                        .buttonStyle(.borderedProminent)
                        .controlSize(.small)
                        .tint(.blue)
                    }
                }
            }

            Divider()

            // NER テスト
            HStack {
                Button {
                    Task { await mgr.runTest() }
                } label: {
                    if mgr.isTesting {
                        HStack(spacing: 4) {
                            ProgressView().scaleEffect(0.6)
                            Text(AppLanguage.shared.t("Testing NER...", "NER 実行中..."))
                        }
                    } else {
                        Label(AppLanguage.shared.t("Test NER", "NER テスト"), systemImage: "play.fill")
                    }
                }
                .buttonStyle(.bordered)
                .disabled(mgr.isTesting)

                if mgr.lastTestDuration > 0 {
                    Text(String(format: "%.1f秒", mgr.lastTestDuration))
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }

            if !mgr.testResult.isEmpty {
                VStack(alignment: .leading, spacing: 3) {
                    Text(AppLanguage.shared.t("Detected Sensitive Identifiers:", "検出した感度識別子:")).font(.caption.bold())
                    ForEach(mgr.testResult.prefix(10), id: \.self) { token in
                        Label(token, systemImage: "lock.fill")
                            .font(.caption.monospaced())
                            .foregroundStyle(.orange)
                    }
                }
                .padding(8)
                .background(Color.orange.opacity(0.08))
                .clipShape(RoundedRectangle(cornerRadius: 8))
            }
        }
    }

    // MARK: - Not Running View

    private var notRunningView: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(AppLanguage.shared.t("Ollama is not running", "Ollama が起動していません"), systemImage: "exclamationmark.triangle")
                .foregroundStyle(.orange)
                .font(.subheadline)
            Text(AppLanguage.shared.t("Run `ollama serve` in the terminal.", "ターミナルで `ollama serve` を実行してください。"))
                .font(.caption)
                .foregroundStyle(.secondary)
            Button(AppLanguage.shared.t("Retry", "再確認")) {
                Task { await mgr.refresh() }
            }.buttonStyle(.bordered)
        }
    }

    // MARK: - Helpers

    private func modelIcon(_ name: String) -> String {
        if name.contains("1.5b") || name.contains("e2b") { return "hare.fill" }
        if name.contains("26b") || name.contains("31b")  { return "tortoise.fill" }
        return "brain"
    }

    private func modelDetail(_ name: String) -> String? {
        let map: [String: String] = [
            "bitnet_b1_58-large":      AppLanguage.shared.t("⚡️ BitNet: 1-bit LLM Recommended — Ultra-fast JCross conversion", "⚡️ BitNet: 1-bit LLM 推奨 — 超高速 JCross 変換"),
            "bonsai:8b":               AppLanguage.shared.t("🌳 Bonsai 8B: Optimized NER inference and pattern recognition", "🌳 Bonsai 8B: 最適化された NER 推論とパターン認識"),
            "qwen2.5:1.5b":            AppLanguage.shared.t("⚡️ 1.5B — Fastest・Ideal for NER", "⚡️ 1.5B — 最速・NER に最適"),
            "qwen2.5:7b-instruct":     AppLanguage.shared.t("🎯 7.6B — High precision instruction tuning", "🎯 7.6B — 高精度 instruction tuning"),
            "gemma4:e2b":              AppLanguage.shared.t("🔥 5.1B — Google Gemma4 Balanced", "🔥 5.1B — Google Gemma4 バランス型"),
            "gemma4:26b":              AppLanguage.shared.t("🧠 25.8B — Highest precision (Slow)", "🧠 25.8B — 最高精度（低速）"),
            "verantyx-gemma:latest":   AppLanguage.shared.t("🔮 Verantyx Custom Gemma4", "🔮 Verantyx カスタム Gemma4"),
            "nemotron-orchestrator:latest": AppLanguage.shared.t("🎮 8.2B Qwen3 Base", "🎮 8.2B Qwen3 ベース"),
            "gpt-oss:20b":             AppLanguage.shared.t("🏢 20.9B OpenAI OSS", "🏢 20.9B OpenAI OSS"),
        ]
        return map[name]
    }
}
