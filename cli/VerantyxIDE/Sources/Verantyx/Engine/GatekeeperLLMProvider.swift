import Foundation

// MARK: - GatekeeperLLMProvider
//
// Gatekeeperパイプラインで使用するCloud LLMのプロバイダーと
// 意図翻訳エンジン（BitNet相当）のバックエンドを定義する。

/// Cloud LLMプロバイダー（構造パッチを解く盲目ソルバー側）
enum GatekeeperCloudProvider: String, CaseIterable, Codable, Sendable {
    case anthropic   = "Anthropic (Claude)"
    case openRouter  = "OpenRouter"
    case deepSeek    = "DeepSeek"
    case ollama      = "Ollama (Local)"

    var baseURL: String {
        switch self {
        case .anthropic:  return "https://api.anthropic.com/v1"
        case .openRouter: return "https://openrouter.ai/api/v1"
        case .deepSeek:   return "https://api.deepseek.com/v1"
        case .ollama:     return "http://127.0.0.1:11434"
        }
    }

    var defaultModel: String {
        switch self {
        case .anthropic:  return "claude-sonnet-4-5"
        case .openRouter: return "anthropic/claude-3.5-sonnet"
        case .deepSeek:   return "deepseek-chat"
        case .ollama:     return "gemma4:26b"
        }
    }

    var supportsOpenAIFormat: Bool {
        switch self {
        case .anthropic: return false
        case .openRouter, .deepSeek, .ollama: return true
        }
    }
}

/// 意図翻訳エンジン（自然言語 → StructuralCommand、BitNet相当）
enum GatekeeperIntentEngine: String, CaseIterable, Codable, Sendable {
    case ruleBased  = "ルールベース (高速・オフライン)"
    case ollama     = "Ollama (ローカルLLM)"
    case mlx        = "MLX (Apple Silicon)"
    case bitNet     = "BitNet (超軽量1bit)"

    var description: String {
        switch self {
        case .ruleBased: return "キーワードマッチングによる高速変換。オフライン動作。"
        case .ollama:    return "ローカルOllamaモデルで意図を解析。より自然な指示に対応。"
        case .mlx:       return "Apple SiliconのMLXエンジンで推論。高速・プライベート。"
        case .bitNet:    return "1-bit量子化の超軽量モデル。最小メモリで動作。"
        }
    }
}

// MARK: - GatekeeperConfig

/// GatekeeperPipelineの設定（永続化対象）
struct GatekeeperConfig: Codable, Sendable {
    var cloudProvider: GatekeeperCloudProvider = .anthropic
    var cloudModel: String = "claude-sonnet-4-5"
    var cloudApiKey: String = ""
    var openRouterApiKey: String = ""
    var deepSeekApiKey: String = ""

    var intentEngine: GatekeeperIntentEngine = .ruleBased
    var intentOllamaModel: String = "gemma4:27b"

    var maxTokens: Int = 4096
    var enabled: Bool = false

    static let userDefaultsKey = "gatekeeper_config_v2"

    static func load() -> GatekeeperConfig {
        guard let data = UserDefaults.standard.data(forKey: userDefaultsKey),
              let config = try? JSONDecoder().decode(GatekeeperConfig.self, from: data)
        else { return GatekeeperConfig() }
        return config
    }

    func save() {
        if let data = try? JSONEncoder().encode(self) {
            UserDefaults.standard.set(data, forKey: GatekeeperConfig.userDefaultsKey)
        }
    }
}

// MARK: - GatekeeperUniversalLLMClient

/// Anthropic / OpenRouter / DeepSeek / Ollama を統一インターフェースで呼び出すクライアント。
actor GatekeeperUniversalLLMClient {

    static let shared = GatekeeperUniversalLLMClient()
    private init() {}

    func complete(
        prompt: String,
        config: GatekeeperConfig,
        systemPrompt: String = "[GATEKEEPER] You are a structural graph solver. Return only valid JSON."
    ) async -> String? {
        switch config.cloudProvider {
        case .anthropic:
            let model = UserDefaults.standard.string(forKey: "anthropic_model") ?? "claude-sonnet-4-5"
            let apiKey = UserDefaults.standard.string(forKey: "anthropic_api_key") ?? ""
            return await callAnthropic(prompt: prompt, config: config, systemPrompt: systemPrompt, model: model, apiKey: apiKey)
        case .openRouter:
            let model = config.cloudModel.isEmpty ? "anthropic/claude-3.5-sonnet" : config.cloudModel
            return await callOpenAIFormat(
                prompt: prompt, config: config, systemPrompt: systemPrompt,
                baseURL: GatekeeperCloudProvider.openRouter.baseURL,
                apiKey: config.openRouterApiKey,
                model: model
            )
        case .deepSeek:
            let model = UserDefaults.standard.string(forKey: "deepseek_model") ?? "deepseek-chat"
            let apiKey = UserDefaults.standard.string(forKey: "api_key_DeepSeek") ?? ""
            return await callOpenAIFormat(
                prompt: prompt, config: config, systemPrompt: systemPrompt,
                baseURL: GatekeeperCloudProvider.deepSeek.baseURL,
                apiKey: apiKey,
                model: model
            )
        case .ollama:
            let model = UserDefaults.standard.string(forKey: "active_ollama_model") ?? "gemma4:26b"
            return await callOllama(prompt: prompt, config: config, systemPrompt: systemPrompt, model: model)
        }
    }

    // MARK: - Anthropic

    private func callAnthropic(
        prompt: String, config: GatekeeperConfig, systemPrompt: String, model: String, apiKey: String
    ) async -> String? {
        guard !apiKey.isEmpty else {
            print("[GatekeeperLLM] ❌ Anthropic API key not set"); return nil
        }
        return await AnthropicClient.shared.generate(
            model: model,
            systemPrompt: systemPrompt,
            messages: [("user", prompt)],
            maxTokens: config.maxTokens,
            temperature: 0.1   // 構造変換は低温度で決定論的に
        )
    }

    // MARK: - OpenAI互換 (OpenRouter / DeepSeek)

    private func callOpenAIFormat(
        prompt: String, config: GatekeeperConfig, systemPrompt: String,
        baseURL: String, apiKey: String, model: String
    ) async -> String? {
        guard !apiKey.isEmpty else {
            print("[GatekeeperLLM] ❌ API key not set for \(baseURL)"); return nil
        }
        guard let url = URL(string: "\(baseURL)/chat/completions") else { return nil }

        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        req.timeoutInterval = 120

        let body: [String: Any] = [
            "model": model,
            "messages": [
                ["role": "system", "content": systemPrompt],
                ["role": "user",   "content": prompt]
            ],
            "max_tokens": config.maxTokens,
            "temperature": 0.1,
            "stream": false
        ]

        guard let bodyData = try? JSONSerialization.data(withJSONObject: body) else { return nil }
        req.httpBody = bodyData

        do {
            let (data, resp) = try await URLSession.shared.data(for: req)
            guard (resp as? HTTPURLResponse)?.statusCode == 200 else {
                let body = String(data: data, encoding: .utf8) ?? ""
                print("[GatekeeperLLM] ❌ HTTP error: \((resp as? HTTPURLResponse)?.statusCode ?? -1) — \(body.prefix(200))")
                return nil
            }
            guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let choices = json["choices"] as? [[String: Any]],
                  let message = choices.first?["message"] as? [String: Any],
                  let content = message["content"] as? String
            else { return nil }
            return content.trimmingCharacters(in: .whitespacesAndNewlines)
        } catch {
            print("[GatekeeperLLM] ❌ Request failed: \(error)"); return nil
        }
    }

    // MARK: - Ollama (as Cloud Solver)

    private func callOllama(
        prompt: String, config: GatekeeperConfig, systemPrompt: String, model: String
    ) async -> String? {
        let fullPrompt = "\(systemPrompt)\n\n\(prompt)"
        return await OllamaClient.shared.generate(
            model: model,
            prompt: fullPrompt,
            maxTokens: config.maxTokens,
            temperature: 0.1
        )
    }
}

// MARK: - GatekeeperIntentClient

/// 意図翻訳エンジンのクライアント（BitNet相当の役割）
/// ルールベース / Ollama / MLX から設定に応じて切り替える。
actor GatekeeperIntentClient {

    static let shared = GatekeeperIntentClient()
    private init() {}

    /// 自然言語の意図を StructuralCommand に翻訳する。
    /// - Parameter config: Gatekeeperの設定
    /// - Returns: 翻訳された StructuralCommand
    func translate(
        userInstruction: String,
        vault: JCrossIRVault,
        ir: JCrossIRDocument,
        config: GatekeeperConfig
    ) async -> StructuralCommand {
        switch config.intentEngine {
        case .ruleBased:
            // 現在のルールベース実装（BitNetIntentTranslator）
            return await BitNetIntentTranslator.shared.translate(
                userInstruction: userInstruction, vault: vault, ir: ir
            )

        case .ollama:
            // OllamaのLLMで意図解析（より自然な指示に対応）
            if let ollamaResult = await translateWithOllama(
                instruction: userInstruction, vault: vault, ir: ir, model: config.intentOllamaModel
            ) {
                return ollamaResult
            }
            // フォールバック: ルールベース
            print("[GatekeeperIntent] Ollama failed, falling back to rule-based")
            return await BitNetIntentTranslator.shared.translate(
                userInstruction: userInstruction, vault: vault, ir: ir
            )

        case .mlx:
            // MLXはAPIが異なるため、現状はルールベースにフォールバック
            // (MLXRunner.shared.streamGenerateTokens の同期版が必要)
            print("[GatekeeperIntent] MLX intent translation not yet implemented, using rule-based")
            return await BitNetIntentTranslator.shared.translate(
                userInstruction: userInstruction, vault: vault, ir: ir
            )

        case .bitNet:
            // BitNetが設定されている場合もルールベースにフォールバック
            // (BitNetのSwift APIが確立次第ここに実装)
            return await BitNetIntentTranslator.shared.translate(
                userInstruction: userInstruction, vault: vault, ir: ir
            )
        }
    }

    // MARK: - Ollama Intent Translation

    private func translateWithOllama(
        instruction: String,
        vault: JCrossIRVault,
        ir: JCrossIRDocument,
        model: String
    ) async -> StructuralCommand? {
        let vaultSummary = vault.allEntries().prefix(10)
            .map { "  NODE[\($0.nodeID.raw)]: \($0.memoryConcrete?.variableName ?? "?")" }
            .joined(separator: "\n")

        let prompt = """
        [INTENT TRANSLATOR]
        ユーザー指示: \(instruction)

        IRの主要ノード（Vault参照）:
        \(vaultSummary)

        以下のJSONのみを返せ（説明不要）:
        {
          "operation": "wrapNode|insertNode|removeNode|connectNodes|replaceNode",
          "targetKeyword": "対象の関数名・クラス名のキーワード",
          "controlFlow": "loop|timeout_wrapper|error_boundary|condition|async_await|lock|null",
          "domainCategory": "async_io|ui_render|compute|storage|security|ipc|unknown"
        }
        """

        guard let response = await OllamaClient.shared.generate(
            model: model, prompt: prompt, maxTokens: 256, temperature: 0.1
        ) else { return nil }

        // JSONを抽出してStructuralCommandに変換
        return parseOllamaIntentResponse(response, vault: vault, ir: ir)
    }

    private func parseOllamaIntentResponse(
        _ response: String,
        vault: JCrossIRVault,
        ir: JCrossIRDocument
    ) -> StructuralCommand? {
        // JSON部分を抽出
        guard let start = response.firstIndex(of: "{"),
              let end = response.lastIndex(of: "}") else { return nil }
        let jsonStr = String(response[start...end])
        guard let data = jsonStr.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return nil }

        let operationStr = json["operation"] as? String ?? "insertNode"
        let keyword = json["targetKeyword"] as? String ?? ""
        let cfStr = json["controlFlow"] as? String ?? ""
        let domainStr = json["domainCategory"] as? String ?? "unknown"

        let operation = StructuralCommand.Operation(rawValue: operationStr) ?? .insertNode
        let cf = cfStr == "null" ? nil : StructuralCommand.ControlFlowKind(rawValue: cfStr)
        let domain = StructuralCommand.DomainCategory(rawValue: domainStr) ?? .unknown

        // Vaultからノードを逆引き
        let entries = vault.allEntries()
        var nodeID = "NODE_UNKNOWN"
        if !keyword.isEmpty {
            let lower = keyword.lowercased()
            for entry in entries {
                if let name = entry.memoryConcrete?.variableName.lowercased(),
                   name.contains(lower) || lower.contains(name) {
                    nodeID = entry.nodeID.raw
                    break
                }
            }
        }

        return StructuralCommand(
            operation: operation,
            targetNodeID: nodeID,
            controlFlowKind: cf,
            domainCategory: domain,
            parameters: [:],
            branchTargetNodeID: nil
        )
    }
}
