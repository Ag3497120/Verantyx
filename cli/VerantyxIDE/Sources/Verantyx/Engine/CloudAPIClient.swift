import Foundation

// MARK: - CloudAPIClient
// Multi-provider cloud API client.
// API keys are stored in UserDefaults (Keychain in production).
// Supports: Anthropic Claude, OpenAI GPT, Google Gemini

// MARK: - CloudProvider

enum CloudProvider: String, CaseIterable, Codable {
    case claude   = "Claude (Anthropic)"
    case openai   = "GPT-4 (OpenAI)"
    case gemini   = "Gemini (Google)"
    case deepseek = "DeepSeek"

    var icon: String {
        switch self {
        case .claude:   return "sparkles"
        case .openai:   return "circlebadge.2"
        case .gemini:   return "star.circle"
        case .deepseek: return "waveform.circle"
        }
    }

    var modelDefaultsKey: String {
        switch self {
        case .claude:   return "anthropic_model"
        case .openai:   return "openai_model"
        case .gemini:   return "gemini_model"
        case .deepseek: return "deepseek_model"
        }
    }

    /// The saved choice, or a fallback. A model id compiled into a build
    /// is stale the day the provider ships the next one — which is why
    /// `CloudAPIClient.listModels` asks the provider what it currently
    /// serves, and these only stand in until it answers once.
    var defaultModel: String {
        if let saved = UserDefaults.standard.string(forKey: modelDefaultsKey), !saved.isEmpty {
            return saved
        }
        switch self {
        case .claude:   return "claude-sonnet-5"
        case .openai:   return "gpt-4o"
        case .gemini:   return "gemini-3.1-pro"
        case .deepseek: return "deepseek-chat"
        }
    }

    /// Where the provider publishes what it is serving today.
    var modelsEndpoint: String {
        switch self {
        case .claude:   return "https://api.anthropic.com/v1/models"
        case .openai:   return "https://api.openai.com/v1/models"
        case .gemini:   return "https://generativelanguage.googleapis.com/v1beta/models"
        case .deepseek: return "https://api.deepseek.com/models"
        }
    }

    var maxTokens: Int {
        switch self {
        case .claude:   return 8192
        case .openai:   return 4096
        case .gemini:   return 8192
        case .deepseek: return 8192
        }
    }
}

// MARK: - CloudAPIClient

actor CloudAPIClient {

    static let shared = CloudAPIClient()

    // MARK: - Retrieve API key

    func apiKey(for provider: CloudProvider) -> String? {
        switch provider {
        case .claude:   return UserDefaults.standard.string(forKey: "anthropic_api_key")
        case .openai:   return UserDefaults.standard.string(forKey: "openai_api_key")
        case .gemini:   return UserDefaults.standard.string(forKey: "gemini_api_key")
        case .deepseek: return UserDefaults.standard.string(forKey: "api_key_DeepSeek")
        }
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
        if provider == .gemini { urlString += "?key=\(key)" }
        guard let url = URL(string: urlString) else { return [] }

        var request = URLRequest(url: url)
        request.timeoutInterval = 12
        switch provider {
        case .claude:
            request.setValue(key, forHTTPHeaderField: "x-api-key")
            request.setValue("2023-06-01", forHTTPHeaderField: "anthropic-version")
        case .openai, .deepseek:
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
        let trimmed = key.trimmingCharacters(in: .whitespaces)
        switch provider {
        case .claude:   UserDefaults.standard.set(trimmed, forKey: "anthropic_api_key")
        case .openai:   UserDefaults.standard.set(trimmed, forKey: "openai_api_key")
        case .gemini:   UserDefaults.standard.set(trimmed, forKey: "gemini_api_key")
        case .deepseek: UserDefaults.standard.set(trimmed, forKey: "api_key_DeepSeek")
        }
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

        switch provider {
        case .claude:   return await callClaude(systemPrompt: systemPrompt, userMessage: userMessage, imageBase64: imageBase64, model: model, apiKey: key)
        case .openai:   return await callOpenAI(systemPrompt: systemPrompt, userMessage: userMessage, imageBase64: imageBase64, model: model, apiKey: key)
        case .gemini:   return await callGemini(systemPrompt: systemPrompt, userMessage: userMessage, imageBase64: imageBase64, model: model, apiKey: key)
        case .deepseek: return await callDeepSeek(systemPrompt: systemPrompt, userMessage: userMessage, model: model, apiKey: key)
        }
    }

    // MARK: - Anthropic Claude

    private func callClaude(systemPrompt: String, userMessage: String, imageBase64: String?, model: String, apiKey: String) async -> Result<String, CloudError> {
        let url = URL(string: "https://api.anthropic.com/v1/messages")!
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
            "max_tokens": CloudProvider.claude.maxTokens,
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

    private func callOpenAI(systemPrompt: String, userMessage: String, imageBase64: String?, model: String, apiKey: String) async -> Result<String, CloudError> {
        let url = URL(string: "https://api.openai.com/v1/chat/completions")!
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
            tokenKey: CloudProvider.openai.maxTokens,
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

    private func callGemini(systemPrompt: String, userMessage: String, imageBase64: String?, model: String, apiKey: String) async -> Result<String, CloudError> {
        let url = URL(string: "https://generativelanguage.googleapis.com/v1beta/models/\(model):generateContent?key=\(apiKey)")!
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
                "maxOutputTokens": CloudProvider.gemini.maxTokens,
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
