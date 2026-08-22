import Foundation

// MARK: - CloudAPIClient
// Multi-provider cloud API client.
// API keys are stored in UserDefaults (Keychain in production).
// Supports: Anthropic Claude, OpenAI GPT, Google Gemini

// MARK: - CloudProvider

/// How a provider expects to be talked to. Almost everyone shipping an API
/// today speaks OpenAI's wire format, so this is three shapes rather than one
/// per vendor — which is what makes adding a provider one line instead of a
/// new request builder, a new parser and four new switch cases.
enum CloudWire {
    case openAICompatible   // /chat/completions, Bearer, {choices:[{message}]}
    case anthropic          // /messages, x-api-key, {content:[blocks]}
    case gemini             // :generateContent, ?key=, {candidates:[...]}
}

/// Everything that differs between providers, declared once.
struct CloudProviderSpec {
    let display: String
    let icon: String
    /// Root of the API, no trailing slash: "https://api.x.ai/v1"
    let baseURL: String
    let wire: CloudWire
    /// UserDefaults key holding the API key.
    let keyDefaults: String
    /// Stand-in until `listModels` asks the provider what it actually serves.
    let fallbackModel: String
    let maxTokens: Int
    /// Where the user gets a key. Shown in settings so it is not a search.
    let consoleURL: String
}

enum CloudProvider: String, CaseIterable, Codable {
    // The original four keep their raw values: they are persisted in
    // UserDefaults and appear in saved settings, so renaming them would
    // silently drop the user's existing configuration.
    case claude     = "Claude (Anthropic)"
    case openai     = "GPT (OpenAI)"
    case gemini     = "Gemini (Google)"
    case deepseek   = "DeepSeek"
    // Added because the wire format made it nearly free to do so.
    case xai        = "Grok (xAI)"
    case qwen       = "Qwen (Alibaba)"
    case moonshot   = "Kimi (Moonshot)"
    case openrouter = "OpenRouter"
    case groq       = "Groq"
    case mistral    = "Mistral"
    case together   = "Together AI"
    case fireworks  = "Fireworks AI"
    case cerebras   = "Cerebras"
    case perplexity = "Perplexity"
    case zhipu      = "GLM (Zhipu)"

    var spec: CloudProviderSpec {
        switch self {
        case .claude:
            return .init(display: rawValue, icon: "sparkles",
                         baseURL: "https://api.anthropic.com/v1", wire: .anthropic,
                         keyDefaults: "anthropic_api_key", fallbackModel: "claude-sonnet-5",
                         maxTokens: 8192, consoleURL: "https://console.anthropic.com/settings/keys")
        case .openai:
            return .init(display: rawValue, icon: "circlebadge.2",
                         baseURL: "https://api.openai.com/v1", wire: .openAICompatible,
                         keyDefaults: "openai_api_key", fallbackModel: "gpt-4o",
                         maxTokens: 4096, consoleURL: "https://platform.openai.com/api-keys")
        case .gemini:
            return .init(display: rawValue, icon: "star.circle",
                         baseURL: "https://generativelanguage.googleapis.com/v1beta", wire: .gemini,
                         keyDefaults: "gemini_api_key", fallbackModel: "gemini-3.1-pro",
                         maxTokens: 8192, consoleURL: "https://aistudio.google.com/apikey")
        case .deepseek:
            return .init(display: rawValue, icon: "waveform.circle",
                         baseURL: "https://api.deepseek.com", wire: .openAICompatible,
                         keyDefaults: "api_key_DeepSeek", fallbackModel: "deepseek-chat",
                         maxTokens: 8192, consoleURL: "https://platform.deepseek.com/api_keys")
        case .xai:
            return .init(display: rawValue, icon: "x.circle",
                         baseURL: "https://api.x.ai/v1", wire: .openAICompatible,
                         keyDefaults: "xai_api_key", fallbackModel: "grok-4",
                         maxTokens: 8192, consoleURL: "https://console.x.ai")
        case .qwen:
            return .init(display: rawValue, icon: "q.circle",
                         baseURL: "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
                         wire: .openAICompatible,
                         keyDefaults: "qwen_api_key", fallbackModel: "qwen-max",
                         maxTokens: 8192, consoleURL: "https://bailian.console.alibabacloud.com")
        case .moonshot:
            return .init(display: rawValue, icon: "moon.circle",
                         baseURL: "https://api.moonshot.ai/v1", wire: .openAICompatible,
                         keyDefaults: "moonshot_api_key", fallbackModel: "kimi-k2-0905-preview",
                         maxTokens: 8192, consoleURL: "https://platform.moonshot.ai/console/api-keys")
        case .openrouter:
            return .init(display: rawValue, icon: "arrow.triangle.branch",
                         baseURL: "https://openrouter.ai/api/v1", wire: .openAICompatible,
                         keyDefaults: "openrouter_api_key", fallbackModel: "openai/gpt-4o",
                         maxTokens: 8192, consoleURL: "https://openrouter.ai/keys")
        case .groq:
            return .init(display: rawValue, icon: "bolt.circle",
                         baseURL: "https://api.groq.com/openai/v1", wire: .openAICompatible,
                         keyDefaults: "groq_api_key", fallbackModel: "llama-3.3-70b-versatile",
                         maxTokens: 8192, consoleURL: "https://console.groq.com/keys")
        case .mistral:
            return .init(display: rawValue, icon: "wind",
                         baseURL: "https://api.mistral.ai/v1", wire: .openAICompatible,
                         keyDefaults: "mistral_api_key", fallbackModel: "mistral-large-latest",
                         maxTokens: 8192, consoleURL: "https://console.mistral.ai/api-keys")
        case .together:
            return .init(display: rawValue, icon: "square.stack.3d.up",
                         baseURL: "https://api.together.xyz/v1", wire: .openAICompatible,
                         keyDefaults: "together_api_key",
                         fallbackModel: "deepseek-ai/DeepSeek-V3",
                         maxTokens: 8192, consoleURL: "https://api.together.ai/settings/api-keys")
        case .fireworks:
            return .init(display: rawValue, icon: "flame",
                         baseURL: "https://api.fireworks.ai/inference/v1", wire: .openAICompatible,
                         keyDefaults: "fireworks_api_key",
                         fallbackModel: "accounts/fireworks/models/deepseek-v3",
                         maxTokens: 8192, consoleURL: "https://fireworks.ai/account/api-keys")
        case .cerebras:
            return .init(display: rawValue, icon: "cpu",
                         baseURL: "https://api.cerebras.ai/v1", wire: .openAICompatible,
                         keyDefaults: "cerebras_api_key", fallbackModel: "llama-3.3-70b",
                         maxTokens: 8192, consoleURL: "https://cloud.cerebras.ai")
        case .perplexity:
            return .init(display: rawValue, icon: "magnifyingglass.circle",
                         baseURL: "https://api.perplexity.ai", wire: .openAICompatible,
                         keyDefaults: "perplexity_api_key", fallbackModel: "sonar-pro",
                         maxTokens: 8192, consoleURL: "https://www.perplexity.ai/settings/api")
        case .zhipu:
            return .init(display: rawValue, icon: "z.circle",
                         baseURL: "https://open.bigmodel.cn/api/paas/v4", wire: .openAICompatible,
                         keyDefaults: "zhipu_api_key", fallbackModel: "glm-4.6",
                         maxTokens: 8192, consoleURL: "https://open.bigmodel.cn/usercenter/apikeys")
        }
    }

    var icon: String { spec.icon }
    var maxTokens: Int { spec.maxTokens }
    var consoleURL: String { spec.consoleURL }

    var modelDefaultsKey: String {
        // The original four keep their historical keys so an existing
        // selection survives this refactor.
        switch self {
        case .claude:   return "anthropic_model"
        case .openai:   return "openai_model"
        case .gemini:   return "gemini_model"
        case .deepseek: return "deepseek_model"
        default:        return "model_\(spec.keyDefaults)"
        }
    }

    /// The saved choice, or a fallback. A model id compiled into a build is
    /// stale the day the provider ships the next one — which is why
    /// `CloudAPIClient.listModels` asks what it currently serves, and these
    /// only stand in until it answers once.
    var defaultModel: String {
        if let saved = UserDefaults.standard.string(forKey: modelDefaultsKey), !saved.isEmpty {
            return saved
        }
        return spec.fallbackModel
    }

    /// Where the provider publishes what it is serving today.
    var modelsEndpoint: String { "\(spec.baseURL)/models" }

    /// Where a chat completion is posted.
    var chatEndpoint: String {
        switch spec.wire {
        case .openAICompatible: return "\(spec.baseURL)/chat/completions"
        case .anthropic:        return "\(spec.baseURL)/messages"
        case .gemini:           return spec.baseURL     // model goes in the path
        }
    }
}

// MARK: - CloudAPIClient

actor CloudAPIClient {

    static let shared = CloudAPIClient()

    // MARK: - Retrieve API key

    func apiKey(for provider: CloudProvider) -> String? {
        UserDefaults.standard.string(forKey: provider.spec.keyDefaults)
    }

    // MARK: - What the provider is serving today
    //
    // The model list was a switch statement, so every new release made
    // the app wrong until someone edited it and shipped a build. Each
    // provider publishes what it currently serves; asking costs one GET
    // and removes the maintenance entirely. Returns [] rather than
    // guessing when there is no key or the call fails — an empty list
    // means "could not ask", and the caller keeps the saved value.
    func listModels(for provider: CloudProvider) async -> [String] {
        guard let key = apiKey(for: provider)?.trimmingCharacters(in: .whitespaces),
              !key.isEmpty else { return [] }

        var urlString = provider.modelsEndpoint
        if provider.spec.wire == .gemini { urlString += "?key=\(key)" }
        guard let url = URL(string: urlString) else { return [] }

        var request = URLRequest(url: url)
        request.timeoutInterval = 12
        switch provider.spec.wire {
        case .anthropic:
            request.setValue(key, forHTTPHeaderField: "x-api-key")
            request.setValue("2023-06-01", forHTTPHeaderField: "anthropic-version")
        case .openAICompatible:
            request.setValue("Bearer \(key)", forHTTPHeaderField: "Authorization")
        case .gemini:
            break   // key travels in the query string
        }

        guard let (data, response) = try? await URLSession.shared.data(for: request),
              (response as? HTTPURLResponse)?.statusCode == 200,
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return [] }

        // Anthropic, OpenAI and DeepSeek answer with `data: [{id: …}]`;
        // Gemini with `models: [{name: "models/…"}]`.
        var ids: [String] = []
        if let items = json["data"] as? [[String: Any]] {
            ids = items.compactMap { $0["id"] as? String }
        } else if let items = json["models"] as? [[String: Any]] {
            ids = items.compactMap { item in
                guard let name = item["name"] as? String else { return nil }
                return name.hasPrefix("models/") ? String(name.dropFirst(7)) : name
            }
        }
        // Embedding, moderation and TTS entries are not chat models and
        // only make the picker harder to read.
        let noise = ["embed", "moderation", "tts", "whisper", "dall-e", "aqa", "imagen", "veo"]
        return ids
            .filter { id in !noise.contains { id.lowercased().contains($0) } }
            .sorted()
    }

    func setAPIKey(_ key: String, for provider: CloudProvider) {
        UserDefaults.standard.set(key.trimmingCharacters(in: .whitespaces),
                                  forKey: provider.spec.keyDefaults)
    }

    func hasAPIKey(for provider: CloudProvider) -> Bool {
        guard let key = apiKey(for: provider) else { return false }
        return !key.isEmpty
    }

    // MARK: - Main: send message

    func send(
        systemPrompt: String,
        userMessage: String,
        imageBase64: String? = nil,
        provider: CloudProvider,
        modelOverride: String? = nil
    ) async -> Result<String, CloudError> {

        guard let key = apiKey(for: provider), !key.isEmpty else {
            return .failure(.noAPIKey(provider))
        }

        let model = modelOverride ?? provider.defaultModel

        // Dispatch on the wire format, not the vendor. Adding a provider that
        // speaks OpenAI's shape needs no code here at all — which is the point
        // of the spec table above.
        switch provider.spec.wire {
        case .anthropic:
            return await callClaude(systemPrompt: systemPrompt, userMessage: userMessage,
                                    imageBase64: imageBase64, model: model, apiKey: key,
                                    provider: provider)
        case .openAICompatible:
            return await callOpenAI(systemPrompt: systemPrompt, userMessage: userMessage,
                                    imageBase64: imageBase64, model: model, apiKey: key,
                                    provider: provider)
        case .gemini:
            return await callGemini(systemPrompt: systemPrompt, userMessage: userMessage,
                                    imageBase64: imageBase64, model: model, apiKey: key,
                                    provider: provider)
        }
    }

    // MARK: - Anthropic Claude

    private func callClaude(systemPrompt: String, userMessage: String, imageBase64: String?,
                            model: String, apiKey: String,
                            provider: CloudProvider) async -> Result<String, CloudError> {
        guard let url = URL(string: provider.chatEndpoint) else { return .failure(.invalidResponse) }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue(apiKey, forHTTPHeaderField: "x-api-key")
        request.setValue("2023-06-01", forHTTPHeaderField: "anthropic-version")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 120

        var userContent: [[String: Any]] = [["type": "text", "text": userMessage]]
        if let img = imageBase64 {
            userContent.append(["type": "image", "source": ["type": "base64", "media_type": "image/jpeg", "data": img]])
        }

        let body: [String: Any] = [
            "model": model,
            "max_tokens": provider.maxTokens,
            "system": systemPrompt,
            "messages": [
                ["role": "user", "content": userContent]
            ]
        ]

        do {
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
            let (data, response) = try await URLSession.shared.data(for: request)

            guard let httpResponse = response as? HTTPURLResponse else {
                return .failure(.invalidResponse)
            }
            guard httpResponse.statusCode == 200 else {
                let errStr = String(data: data, encoding: .utf8) ?? "unknown"
                return .failure(.apiError(httpResponse.statusCode, errStr.prefix(200).description))
            }

            guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let content = json["content"] as? [[String: Any]]
            else { return .failure(.parseError) }

            // Only the text blocks. Reading `content.first` failed outright on
            // any model that puts a thinking or tool_use block first.
            let text = content
                .filter { ($0["type"] as? String) == "text" }
                .compactMap { $0["text"] as? String }
                .joined(separator: "\n")
            guard !text.isEmpty else { return .failure(.parseError) }

            return .success(text)
        } catch {
            return .failure(.networkError(error.localizedDescription))
        }
    }

    // MARK: - OpenAI GPT

    private func callOpenAI(systemPrompt: String, userMessage: String, imageBase64: String?,
                            model: String, apiKey: String,
                            provider: CloudProvider) async -> Result<String, CloudError> {
        guard let url = URL(string: provider.chatEndpoint) else { return .failure(.invalidResponse) }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 120

        let userContent: Any
        if let img = imageBase64 {
            userContent = [
                ["type": "text", "text": userMessage],
                ["type": "image_url", "image_url": ["url": "data:image/jpeg;base64,\(img)"]]
            ]
        } else {
            userContent = userMessage
        }

        // The reasoning models (o1, o3, gpt-5 …) reject `max_tokens` outright
        // with a 400 and want `max_completion_tokens`, and take the system text
        // as a `developer` message. Sending the older shape to them fails the
        // request, so pick the shape from the model id.
        let isReasoning = model.hasPrefix("o1") || model.hasPrefix("o3")
            || model.hasPrefix("o4") || model.hasPrefix("gpt-5")
        let tokenKey = isReasoning ? "max_completion_tokens" : "max_tokens"
        let systemRole = isReasoning ? "developer" : "system"

        let body: [String: Any] = [
            "model": model,
            tokenKey: provider.maxTokens,
            "messages": [
                ["role": systemRole, "content": systemPrompt],
                ["role": "user",     "content": userContent]
            ]
        ]

        do {
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
            let (data, response) = try await URLSession.shared.data(for: request)

            guard let httpResponse = response as? HTTPURLResponse else {
                return .failure(.invalidResponse)
            }
            guard httpResponse.statusCode == 200 else {
                let errStr = String(data: data, encoding: .utf8) ?? "unknown"
                return .failure(.apiError(httpResponse.statusCode, errStr.prefix(200).description))
            }

            guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let choices = json["choices"] as? [[String: Any]],
                  let first = choices.first,
                  let message = first["message"] as? [String: Any],
                  let text = message["content"] as? String
            else { return .failure(.parseError) }

            return .success(text)
        } catch {
            return .failure(.networkError(error.localizedDescription))
        }
    }

    // MARK: - Google Gemini

    private func callGemini(systemPrompt: String, userMessage: String, imageBase64: String?,
                            model: String, apiKey: String,
                            provider: CloudProvider) async -> Result<String, CloudError> {
        guard let url = URL(string: "\(provider.spec.baseURL)/models/\(model):generateContent?key=\(apiKey)")
        else { return .failure(.invalidResponse) }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 120

        var parts: [[String: Any]] = [["text": userMessage]]
        if let img = imageBase64 {
            parts.append(["inlineData": ["mimeType": "image/jpeg", "data": img]])
        }

        let body: [String: Any] = [
            "system_instruction": ["parts": [["text": systemPrompt]]],
            "contents": [
                ["role": "user", "parts": parts]
            ],
            "generationConfig": [
                "maxOutputTokens": provider.maxTokens,
                "temperature": 0.1
            ]
        ]

        do {
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
            let (data, response) = try await URLSession.shared.data(for: request)

            guard let httpResponse = response as? HTTPURLResponse else {
                return .failure(.invalidResponse)
            }
            guard httpResponse.statusCode == 200 else {
                let errStr = String(data: data, encoding: .utf8) ?? "unknown"
                return .failure(.apiError(httpResponse.statusCode, errStr.prefix(200).description))
            }

            guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let candidates = json["candidates"] as? [[String: Any]],
                  let first = candidates.first,
                  let content = first["content"] as? [String: Any],
                  let parts = content["parts"] as? [[String: Any]]
            else { return .failure(.parseError) }

            // Skip parts flagged as thought; `parts.first` returned the
            // model's reasoning (or nil) on the thinking-capable models.
            let text = parts
                .filter { ($0["thought"] as? Bool) != true }
                .compactMap { $0["text"] as? String }
                .joined(separator: "\n")
            guard !text.isEmpty else { return .failure(.parseError) }

            return .success(text)
        } catch {
            return .failure(.networkError(error.localizedDescription))
        }
    }

    // MARK: - DeepSeek

    private func callDeepSeek(systemPrompt: String, userMessage: String, model: String, apiKey: String) async -> Result<String, CloudError> {
        let url = URL(string: "https://api.deepseek.com/chat/completions")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 120

        let body: [String: Any] = [
            "model": model,
            "max_tokens": CloudProvider.deepseek.maxTokens,
            "messages": [
                ["role": "system", "content": systemPrompt],
                ["role": "user",   "content": userMessage]
            ]
        ]

        do {
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
            let (data, response) = try await URLSession.shared.data(for: request)

            guard let httpResponse = response as? HTTPURLResponse else {
                return .failure(.invalidResponse)
            }
            guard httpResponse.statusCode == 200 else {
                let errStr = String(data: data, encoding: .utf8) ?? "unknown"
                return .failure(.apiError(httpResponse.statusCode, errStr.prefix(200).description))
            }

            guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let choices = json["choices"] as? [[String: Any]],
                  let first = choices.first,
                  let message = first["message"] as? [String: Any],
                  let text = message["content"] as? String
            else { return .failure(.parseError) }

            return .success(text)
        } catch {
            return .failure(.networkError(error.localizedDescription))
        }
    }
}

// MARK: - CloudError

enum CloudError: Error, LocalizedError {
    case noAPIKey(CloudProvider)
    case invalidResponse
    case apiError(Int, String)
    case parseError
    case networkError(String)

    var errorDescription: String? {
        switch self {
        case .noAPIKey(let p):         return "No API key for \(p.rawValue). Add it in Settings → Cloud APIs."
        case .invalidResponse:         return "Invalid HTTP response from cloud API."
        case .apiError(let code, let msg): return "API error \(code): \(msg)"
        case .parseError:              return "Failed to parse cloud API response."
        case .networkError(let msg):   return "Network error: \(msg)"
        }
    }
}
import Foundation

// A helper for CloudAPIClient to support multi-turn Agentic Tool use (currently only Anthropic)
actor CloudAgenticClient {
    static let shared = CloudAgenticClient()
    
    func runAgenticLoop(
        systemPrompt: String,
        userMessage: String,
        provider: CloudProvider,
        onStep: @escaping @Sendable (String) async -> Void
    ) async -> String {
        guard provider == .claude else {
            // Fallback for non-claude models
            switch await CloudAPIClient.shared.send(systemPrompt: systemPrompt, userMessage: userMessage, provider: provider) {
            case .success(let text): return text
            case .failure(let err): return "❌ Error: \(err.localizedDescription)"
            }
        }
        
        guard let apiKey = await CloudAPIClient.shared.apiKey(for: .claude), !apiKey.isEmpty else {
            return "❌ Error: No Anthropic API Key"
        }
        
        let mcpTools = await MainActor.run { MCPEngine.shared.connectedTools }
        let claudeTools = mcpTools.compactMap { t -> [String: Any]? in
            guard let schemaData = try? JSONEncoder().encode(t.inputSchema),
                  let schemaDict = try? JSONSerialization.jsonObject(with: schemaData) as? [String: Any] else {
                return nil
            }
            return [
                "name": "\(t.serverName)__\(t.name)".replacingOccurrences(of: "-", with: "_"),
                "description": t.description,
                "input_schema": [
                    "type": "object",
                    "properties": schemaDict
                ]
            ]
        }
        
        var messages: [[String: Any]] = [
            ["role": "user", "content": userMessage]
        ]
        
        var finalResponse = ""
        let model = UserDefaults.standard.string(forKey: "anthropic_model") ?? "claude-sonnet-4-5"
        
        for turn in 1...10 {
            await onStep("☁️ Anthropic Agent Turn \(turn)...")
            
            var body: [String: Any] = [
                "model": model,
                "max_tokens": 8192,
                "system": systemPrompt,
                "messages": messages
            ]
            if !claudeTools.isEmpty {
                body["tools"] = claudeTools
            }
            
            let url = URL(string: "https://api.anthropic.com/v1/messages")!
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.setValue(apiKey, forHTTPHeaderField: "x-api-key")
            request.setValue("2023-06-01", forHTTPHeaderField: "anthropic-version")
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.timeoutInterval = 120
            request.httpBody = try? JSONSerialization.data(withJSONObject: body)
            
            do {
                let (data, response) = try await URLSession.shared.data(for: request)
                guard let httpRes = response as? HTTPURLResponse, httpRes.statusCode == 200 else {
                    let errStr = String(data: data, encoding: .utf8) ?? ""
                    return "❌ API Error: \(errStr)"
                }
                
                guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                      let content = json["content"] as? [[String: Any]] else {
                    return "❌ Parse Error"
                }
                
                messages.append(["role": "assistant", "content": content])
                
                // Check if tool use
                let toolUses = content.filter { $0["type"] as? String == "tool_use" }
                if toolUses.isEmpty {
                    // Done
                    finalResponse = content.compactMap { $0["text"] as? String }.joined(separator: "\n")
                    break
                }
                
                // Execute tools
                var toolResults: [[String: Any]] = []
                for toolUse in toolUses {
                    guard let toolUseId = toolUse["id"] as? String,
                          let toolNameRaw = toolUse["name"] as? String,
                          let toolInput = toolUse["input"] as? [String: Any] else { continue }
                    
                    // Decode serverName__toolName
                    let parts = toolNameRaw.components(separatedBy: "__")
                    let serverName = parts.count > 1 ? parts[0].replacingOccurrences(of: "_", with: "-") : parts[0]
                    let toolName = parts.count > 1 ? parts.dropFirst().joined(separator: "__").replacingOccurrences(of: "_", with: "-") : toolNameRaw
                    
                    await onStep("🔧 Executing Tool: \(serverName)/\(toolName)")
                    
                    let resultText = await MCPEngine.shared.callTool(serverName: serverName, toolName: toolName, arguments: toolInput, mode: .ai)

                    toolResults.append([
                        "type": "tool_result",
                        "tool_use_id": toolUseId,
                        "content": resultText
                    ])
                }
                
                messages.append([
                    "role": "user",
                    "content": toolResults
                ])
                
            } catch {
                return "❌ Network Error: \(error.localizedDescription)"
            }
        }
        
        return finalResponse
    }
}
