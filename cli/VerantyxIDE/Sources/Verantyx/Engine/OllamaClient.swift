import Foundation

// MARK: - LLMStreamEvent
// openclaw/pi-agent-core の StreamFn パターンを Swift に移植。
// ollama-stream.ts の `for await (const chunk of parseNdjsonStream(reader))` に対応。

public enum LLMStreamEvent: Sendable {
    case token(String)
    case thinking(String)
    case toolCall(name: String, args: String)
    case done(stopReason: StopReason)
    case error(String)
}

public enum StopReason: String, Sendable {
    case endTurn   = "stop"
    case toolUse   = "tool_calls"
    case maxTokens = "length"
    case error     = "error"
}

// MARK: - OllamaClient
// openclaw の ollama-stream.ts から設計を学んで改修。
// 変更点:
//   - generate() が token-by-token streaming に変更（stream: true + /api/chat NDJSON）
//   - streamConversation() で会話履歴をそのまま渡せるようにした
//   - multi-turn messages array 対応（AgentLoop が渡す conversation のため）
//   - num_ctx=65536 デフォルト（ollama の 4096 デフォルトは小さすぎる）
//   - thinking コンテンツの分離抽出

public actor OllamaClient {

    public static let shared = OllamaClient()
    private func getBaseURL() async -> String {
        return await MainActor.run {
            if let state = AppState.shared, state.exoEnabled, !state.exoEndpoint.isEmpty {
                return state.exoEndpoint
            }
            return AppState.shared?.ollamaEndpoint ?? "http://127.0.0.1:11434"
        }
    }
    private var _available: Bool? = nil
    private var _availableTime: Date? = nil

    /// URLSession with no timeout — used for all streaming inference calls.
    /// Ollama /api/chat is a long-lived NDJSON stream that can run for hours
    /// on large context windows. URLSession's default 60s resource timeout
    /// would kill mid-generation. This session has both intervals set to ∞.
    private static let noTimeoutSession: URLSession = {
        let cfg = URLSessionConfiguration.default
        cfg.timeoutIntervalForRequest  = .infinity
        cfg.timeoutIntervalForResource = .infinity
        return URLSession(configuration: cfg)
    }()

    // MARK: - Availability (5s TTL cache)

    public func isAvailable() async -> Bool {
        if let t = _availableTime, Date().timeIntervalSince(t) < 5, let c = _available { return c }
        let ok = await probe()
        _available = ok; _availableTime = Date()
        return ok
    }

    private func probe() async -> Bool {
        let baseURL = await getBaseURL()
        guard let url = URL(string: "\(baseURL)/api/tags") else { return false }
        var req = URLRequest(url: url)
        req.timeoutInterval = 1.5
        do {
            let (_, resp) = try await URLSession.shared.data(for: req)
            return (resp as? HTTPURLResponse)?.statusCode == 200
        } catch { return false }
    }

    // MARK: - Keep model warm (GPU アイドル防止)
    //
    // Ollamaはデフォルトで5分間アクセスがないとモデルをVRAMから解放する。
    // AgentLoopの長いツール実行ターンの合間に呼ぶことでモデルをVRAM上に保持する。
    // keep_alive: "-1" は「永続」を意味する (Ollama v0.1.24+)。

    public func keepModelWarm(model: String) async {
        let baseURL = await getBaseURL()
        guard let url = URL(string: "\(baseURL)/api/chat") else { return }
        var req = URLRequest(url: url)
        req.httpMethod  = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.timeoutInterval = 5

        // Empty generate with keep_alive=-1 to pin the model in VRAM
        let body: [String: Any] = [
            "model":      model,
            "messages":   [],
            "stream":     false,
            "keep_alive": "-1"     // 永久に解放しない
        ]
        guard let bodyData = try? JSONSerialization.data(withJSONObject: body) else { return }
        req.httpBody = bodyData
        _ = try? await URLSession.shared.data(for: req)  // fire-and-forget
    }

    // MARK: - Unload model (LM Studio "Eject" equivalent)
    //
    // Sending keep_alive: 0 to /api/chat with an empty messages array tells
    // Ollama to immediately evict the model from GPU/Metal memory.
    // Works on Ollama v0.1.24+.

    public func unloadModel(_ model: String) async -> Bool {
        let baseURL = await getBaseURL()
        guard let url = URL(string: "\(baseURL)/api/chat") else { return false }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.timeoutInterval = 10

        let body: [String: Any] = [
            "model":      model,
            "messages":   [],
            "stream":     false,
            "keep_alive": 0   // 0 = unload immediately
        ]
        guard let bodyData = try? JSONSerialization.data(withJSONObject: body) else { return false }
        req.httpBody = bodyData

        do {
            let (_, resp) = try await URLSession.shared.data(for: req)
            let ok = (resp as? HTTPURLResponse)?.statusCode == 200
            if ok { print("[OllamaClient] ✅ Unloaded model: \(model)") }
            return ok
        } catch {
            print("[OllamaClient] ❌ Failed to unload \(model): \(error)")
            return false
        }
    }

    // MARK: - Running models (/api/ps)
    //
    // Returns models currently loaded in VRAM with their memory usage.

    public struct RunningModel: Sendable {
        public let name: String
        public let sizeBytes: Int64   // VRAM usage in bytes
        public var sizeGB: Double { Double(sizeBytes) / 1_073_741_824 }
    }

    public func loadedModels() async -> [RunningModel] {
        let baseURL = await getBaseURL()
        guard let url = URL(string: "\(baseURL)/api/ps") else { return [] }
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let models = json["models"] as? [[String: Any]] else { return [] }
            return models.compactMap { m -> RunningModel? in
                guard let name = m["name"] as? String else { return nil }
                let size = (m["size"] as? Int64) ?? Int64((m["size"] as? Int) ?? 0)
                return RunningModel(name: name, sizeBytes: size)
            }
        } catch { return [] }
    }

    // MARK: - Model list

    public func listModels() async -> [String] {
        let baseURL = await getBaseURL()
        guard let url = URL(string: "\(baseURL)/api/tags") else { return [] }
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let models = json["models"] as? [[String: Any]] else { return [] }
            return models.compactMap { $0["name"] as? String }
        } catch { return [] }
    }

    // MARK: - Pull Model (Method 3: HuggingFace via Ollama API)
    // URLSession を用いて進捗をストリーミングで取得する

    public struct PullProgress: Sendable {
        public let status: String
        public let completed: Int64
        public let total: Int64
        public var percent: Double {
            guard total > 0 else { return 0 }
            return Double(completed) / Double(total)
        }
    }

    nonisolated public func pullModel(name: String) -> AsyncThrowingStream<PullProgress, Error> {
        return AsyncThrowingStream { continuation in
            Task {
                let baseURL = await self.getBaseURL()
                guard let url = URL(string: "\(baseURL)/api/pull") else {
                    continuation.finish()
                    return
                }
                var req = URLRequest(url: url)
                req.httpMethod = "POST"
                req.setValue("application/json", forHTTPHeaderField: "Content-Type")
                req.timeoutInterval = .infinity

                let body: [String: Any] = ["name": name, "stream": true]
                guard let bodyData = try? JSONSerialization.data(withJSONObject: body) else {
                    continuation.finish()
                    return
                }
                req.httpBody = bodyData

                do {
                    let (stream, resp) = try await OllamaClient.noTimeoutSession.bytes(for: req)
                    guard let httpResp = resp as? HTTPURLResponse, httpResp.statusCode == 200 else {
                        continuation.yield(.init(status: "HTTP Error \((resp as? HTTPURLResponse)?.statusCode ?? -1)", completed: 0, total: 0))
                        continuation.finish()
                        return
                    }

                    for try await line in stream.lines {
                        guard !line.isEmpty,
                              let data = line.data(using: .utf8),
                              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
                        else { continue }

                        let status = json["status"] as? String ?? "downloading"
                        let completed = (json["completed"] as? Int64) ?? 0
                        let total = (json["total"] as? Int64) ?? 0
                        
                        continuation.yield(PullProgress(status: status, completed: completed, total: total))
                        
                        if status == "success" {
                            break
                        }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }

    // MARK: - generate() — streaming token-by-token (replaces batch mode)
    // openclaw: ollama-stream.ts の createOllamaStreamFn() を参考に実装。
    // Ollamaは stream:true 時に NDJSON チャンクを逐次返す。
    // ここでは AgentLoop 互換のシグネチャを保ちつつ、内部はストリームで受信する。

    public func generate(
        model: String,
        prompt: String,
        maxTokens: Int = 2048,
        temperature: Double = 0.15,
        onToken: (@Sendable (String) -> Void)? = nil   // NEW: per-token callback
    ) async -> String? {
        // シングルユーザーメッセージをmulti-turn形式に変換
        let messages: [[String: Any]] = [["role": "user", "content": prompt]]
        return await streamChat(
            model: model,
            messages: messages,
            maxTokens: maxTokens,
            temperature: temperature,
            onToken: onToken
        )
    }

    // MARK: - generateConversation() — multi-turn対応（AgentLoop用）
    // openclaw: convertToOllamaMessages() と同様にロールをそのまま渡す

    public func generateConversation(
        model: String,
        messages: [(role: String, content: String)],
        imagesForLastUserMessage: [String]? = nil,
        maxTokens: Int = 2048,
        temperature: Double = 0.15,
        onToken: (@Sendable (String) -> Void)? = nil
    ) async -> String? {
        var ollamaMessages: [[String: Any]] = messages.map { ["role": $0.role, "content": $0.content] }
        
        if let images = imagesForLastUserMessage, !images.isEmpty {
            if let lastIdx = ollamaMessages.lastIndex(where: { $0["role"] as? String == "user" }) {
                ollamaMessages[lastIdx]["images"] = images
            }
        }
        
        return await streamChat(
            model: model,
            messages: ollamaMessages,
            maxTokens: maxTokens,
            temperature: temperature,
            onToken: onToken
        )
    }

    // MARK: - Core: streamChat()
    // openclaw の NDJSON ストリーム解析ロジックをそのまま Swift で再現。
    // done:true チャンクを受け取るまでトークンを結合。
    //
    // 既知の nil-response 原因と対策:
    //   1. keep_alive が String "−1" → Ollama Go parser が拒否 → HTTP 400 → nil
    //      Fix: Int -1 を送る（負数 = 永続ロード）
    //   2. num_ctx が大きすぎる → HTTP 400/500 → nil
    //      Fix: 失敗したら 8192 に下げてリトライ
    //   3. HTTP 非200 を黙って捨てる → エラーが UI に届かない
    //      Fix: エラーボディを読んで progressHandler に流す

    private func streamChat(
        model: String,
        messages: [[String: Any]],
        maxTokens: Int,
        temperature: Double,
        onToken: (@Sendable (String) -> Void)? = nil,
        onError: (@Sendable (String) -> Void)? = nil
    ) async -> String? {
        // まず大きいコンテキストで試み、失敗したら小さくリトライ（MacのVRAM制約への適応）
        // 65536は27Bモデル等で即死OOMを引く確率が高いため、最大32768スタートとする
        let ctxSizes = [32768, 16384, 8192, 4096]
        for (attempt, numCtx) in ctxSizes.enumerated() {
            if let result = await streamChatAttempt(
                model: model,
                messages: messages,
                maxTokens: maxTokens,
                temperature: temperature,
                numCtx: numCtx,
                onToken: onToken,
                onError: attempt < ctxSizes.count - 1 ? nil : onError  // エラーは最終試行時のみ上流へ
            ) {
                if attempt > 0 {
                    print("[OllamaClient] Succeeded with reduced num_ctx=\(numCtx)")
                }
                return result
            }
            // 最後の試行が失敗したら nil を返す
            if attempt == ctxSizes.count - 1 { return nil }
            print("[OllamaClient] Retrying with smaller num_ctx=\(ctxSizes[attempt + 1])…")
        }
        return nil
    }

    private func streamChatAttempt(
        model: String,
        messages: [[String: Any]],
        maxTokens: Int,
        temperature: Double,
        numCtx: Int,
        onToken: (@Sendable (String) -> Void)? = nil,
        onError: (@Sendable (String) -> Void)?
    ) async -> String? {
        let baseURL = await getBaseURL()
        guard let url = URL(string: "\(baseURL)/api/chat") else { return nil }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        // No timeout — large models / long contexts can generate for many minutes.
        // noTimeoutSession already sets both intervals to ∞; this belt-and-suspenders
        // value covers any URLRequest-level override.
        req.timeoutInterval = .infinity

        // keep_alive: -1 (Int) = 永続ロード。
        // !! 文字列 "-1" は Go の duration parser が reject → HTTP 400 になる !!
        let body: [String: Any] = [
            "model":      model,
            "messages":   messages,
            "stream":     true,
            "keep_alive": -1,          // Int -1 = stay loaded indefinitely (Ollama v0.1.24+)
            "options": [
                "num_ctx":       numCtx,
                "num_predict":   max(maxTokens, 512),
                "temperature":   temperature,
                "top_p":         0.9,
                "repeat_penalty": 1.05
            ]
        ]
        guard let bodyData = try? JSONSerialization.data(withJSONObject: body) else {
            print("[OllamaClient] ❌ Failed to serialize request body")
            return nil
        }
        req.httpBody = bodyData

        var accumulated      = ""
        var accumulatedThink = ""

        do {
            let (stream, resp) = try await OllamaClient.noTimeoutSession.bytes(for: req)
            let statusCode = (resp as? HTTPURLResponse)?.statusCode ?? -1

            guard statusCode == 200 else {
                // エラーボディを読んで上流へ渡す（UI に表示するため）
                var errBody = ""
                for try await line in stream.lines { errBody += line; if errBody.count > 500 { break } }
                let errMsg = "[OllamaClient] HTTP \(statusCode) from /api/chat — model='\(model)' num_ctx=\(numCtx)\n  body: \(errBody.isEmpty ? "(empty)" : errBody)"
                print(errMsg)
                onError?(errMsg)
                return nil
            }

            // openclaw: parseNdjsonStream(reader) — 1行 = 1 JSONオブジェクト
            for try await line in stream.lines {
                if Task.isCancelled { break }
                
                guard !line.isEmpty,
                      let data = line.data(using: .utf8),
                      let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
                else { continue }

                if let message = json["message"] as? [String: Any] {
                    if let token = message["content"] as? String, !token.isEmpty {
                        accumulated += token
                        onToken?(token)
                    }
                    if let think = message["thinking"] as? String, !think.isEmpty {
                        accumulatedThink += think
                    }
                }

                // Ollamaのエラーフィールド（ストリーム中に来ることがある）
                if let ollamaErr = json["error"] as? String {
                    let msg = "[OllamaClient] Stream error from Ollama: \(ollamaErr)"
                    print(msg); onError?(msg)
                    return nil
                }

                if json["done"] as? Bool == true { break }
            }

            let result = accumulated.trimmingCharacters(in: .whitespacesAndNewlines)
            if result.isEmpty && !accumulatedThink.isEmpty {
                // Gemma-4 thinking-only mode フォールバック
                return accumulatedThink.trimmingCharacters(in: .whitespacesAndNewlines)
            }
            if result.isEmpty {
                let msg = "[OllamaClient] ⚠️ Empty response from model '\(model)' (num_ctx=\(numCtx), stream completed with no tokens)"
                print(msg); onError?(msg)
                return nil
            }
            return result

        } catch {
            let msg = "[OllamaClient] ❌ Stream error: \(error.localizedDescription)"
            print(msg); onError?(msg)
            return nil
        }
    }

    // MARK: - streamGenerate() — AsyncThrowingStream (chat UI用, 既存互換)

    nonisolated public func streamGenerate(
        model: String,
        messages: [(role: String, content: String)],
        maxTokens: Int = 2048,
        temperature: Double = 0.7
    ) -> AsyncThrowingStream<LLMStreamEvent, Error> {
        return AsyncThrowingStream { continuation in
            Task {
                let baseURL = await self.getBaseURL()
                guard let url = URL(string: "\(baseURL)/api/chat") else {
                    continuation.finish(); return
                }
                var req = URLRequest(url: url)
                req.httpMethod = "POST"
                req.setValue("application/json", forHTTPHeaderField: "Content-Type")
                req.timeoutInterval = .infinity

                let ollamaMessages = messages.map { ["role": $0.role, "content": $0.content] }
                let body: [String: Any] = [
                    "model":      model,
                    "messages":   ollamaMessages,
                    "stream":     true,
                    "keep_alive": -1,      // Int -1 = stay loaded indefinitely
                    "options": [
                        "num_ctx":     32768,
                        "num_predict": max(maxTokens, 512),
                        "temperature": temperature
                    ]
                ]
                guard let bodyData = try? JSONSerialization.data(withJSONObject: body) else {
                    continuation.finish(); return
                }
                req.httpBody = bodyData

                do {
                    let (stream, _) = try await OllamaClient.noTimeoutSession.bytes(for: req)
                    for try await line in stream.lines {
                        if Task.isCancelled { break }
                        
                        guard !line.isEmpty,
                              let data = line.data(using: .utf8),
                              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
                        else { continue }

                        if let msg = json["message"] as? [String: Any] {
                            if let token = msg["content"] as? String, !token.isEmpty {
                                continuation.yield(.token(token))
                            }
                            if let think = msg["thinking"] as? String, !think.isEmpty {
                                continuation.yield(.thinking(think))
                            }
                        }
                        if json["done"] as? Bool == true {
                            continuation.yield(.done(stopReason: .endTurn))
                            continuation.finish()
                            return
                        }
                    }
                    continuation.yield(.done(stopReason: .endTurn))
                    continuation.finish()
                } catch {
                    continuation.yield(.error(error.localizedDescription))
                    continuation.finish(throwing: error)
                }
            }
        }
    }

    public func resetAvailability() { _available = nil; _availableTime = nil }
}

// MARK: - AnthropicClient
// openclaw/src/agents/ の Anthropic Messages API 実装を参考に Swift で実装。
// claw-code の claude-cli-runner.ts + openai-ws-stream.ts の設計を踏襲。
//
// 設計原則 (openclaw から学んだこと):
//   1. messages array 形式（system は最上位パラメータ）
//   2. stream: true で Server-Sent Events を受信
//   3. "content_block_delta" → "text_delta" でトークンを逐次処理
//   4. "message_stop" で終了
//   5. stopReason: "end_turn" / "tool_use" / "max_tokens"

public actor AnthropicClient {

    public static let shared = AnthropicClient()

    var apiKey: String = ""  // internal: Task 内で await AnthropicClient.shared.apiKey で取得
    private let baseURL = "https://api.anthropic.com/v1"
    private let anthropicVersion = "2023-06-01"
    private let betaHeader = "interleaved-thinking-2025-05-14"  // thinking beta

    // MARK: - Configuration

    public func configure(apiKey: String) {
        self.apiKey = apiKey
    }

    public var isConfigured: Bool { !apiKey.isEmpty }

    // MARK: - Available models

    public static let models: [(id: String, displayName: String)] = [
        ("claude-opus-4-5",      "Claude Opus 4.5"),
        ("claude-sonnet-4-5",    "Claude Sonnet 4.5"),
        ("claude-haiku-4-5",     "Claude Haiku 4.5"),
        ("claude-3-7-sonnet-20250219", "Claude 3.7 Sonnet (Thinking)"),
        ("claude-opus-4-0",      "Claude Opus 4"),
        ("claude-sonnet-4-0",    "Claude Sonnet 4"),
    ]

    // MARK: - Privacy Firewall (Hard Block)
    
    /// Removes <PRIVATE_OS_MEM> blocks so they NEVER reach the cloud model.
    nonisolated public func applyHardFirewall(to content: String) -> String {
        var safeContent = content
        while let startRange = safeContent.range(of: "<PRIVATE_OS_MEM>"),
              let endRange = safeContent.range(of: "</PRIVATE_OS_MEM>") {
            let fullRange = startRange.lowerBound..<endRange.upperBound
            safeContent.removeSubrange(fullRange)
        }
        return safeContent
    }

    // MARK: - generate() — streaming (token-by-token)
    // openclaw: anthropic-payload-log.ts + pi-embedded-runner の SSE 処理を参考に実装

    public func generate(
        model: String,
        systemPrompt: String,
        messages: [(role: String, content: String)],
        imagesForLastUserMessage: [String]? = nil,
        maxTokens: Int = 8096,
        temperature: Double = 0.15,
        enableThinking: Bool = false,      // claude-3-7-sonnet 以降でサポート
        budgetTokens: Int = 10000,
        onToken: (@Sendable (String) -> Void)? = nil,
        onThinking: (@Sendable (String) -> Void)? = nil
    ) async -> String? {
        guard !apiKey.isEmpty else {
            print("[AnthropicClient] API key not configured")
            return nil
        }

        guard let url = URL(string: "\(baseURL)/messages") else { return nil }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue(apiKey, forHTTPHeaderField: "x-api-key")
        req.setValue(anthropicVersion, forHTTPHeaderField: "anthropic-version")
        req.timeoutInterval = 600

        // Thinking beta header
        if enableThinking {
            req.setValue(betaHeader, forHTTPHeaderField: "anthropic-beta")
        }

        // openclaw: Anthropic messages format
        var anthropicMessages: [[String: Any]] = messages.map { msg in
            // User と assistant のみ — system は最上位パラメータ
            let safeContent = applyHardFirewall(to: msg.content)
            return ["role": msg.role, "content": safeContent]
        }
        
        if let images = imagesForLastUserMessage, !images.isEmpty {
            if let lastIdx = anthropicMessages.lastIndex(where: { $0["role"] as? String == "user" }),
               let originalText = anthropicMessages[lastIdx]["content"] as? String {
                var contentArray: [[String: Any]] = []
                for imgBase64 in images {
                    contentArray.append([
                        "type": "image",
                        "source": [
                            "type": "base64",
                            "media_type": "image/png",
                            "data": imgBase64
                        ]
                    ])
                }
                contentArray.append([
                    "type": "text",
                    "text": originalText
                ])
                anthropicMessages[lastIdx]["content"] = contentArray
            }
        }

        var body: [String: Any] = [
            "model":      model,
            "system":     applyHardFirewall(to: systemPrompt),
            "messages":   anthropicMessages,
            "max_tokens": max(maxTokens, 1024),
            "stream":     true
        ]

        if temperature != 1.0 && !enableThinking {
            // thinking が有効な場合 temperature=1 が必須（Anthropic制約）
            body["temperature"] = temperature
        }

        // Extended thinking (claude-3-7-sonnet+)
        if enableThinking {
            body["thinking"] = ["type": "enabled", "budget_tokens": budgetTokens]
        }

        guard let bodyData = try? JSONSerialization.data(withJSONObject: body) else { return nil }
        req.httpBody = bodyData

        return await parseAnthropicSSE(req: req, onToken: onToken, onThinking: onThinking)
    }

    // MARK: - SSE Parser
    // openclaw の stream event 処理を参考:
    //   "content_block_delta" { delta: { type: "text_delta", text: "..." } }
    //   "content_block_delta" { delta: { type: "thinking_delta", thinking: "..." } }
    //   "message_stop" → done

    private func parseAnthropicSSE(
        req: URLRequest,
        onToken: (@Sendable (String) -> Void)?,
        onThinking: (@Sendable (String) -> Void)?
    ) async -> String? {
        var accumulated      = ""
        var accumulatedThink = ""

        do {
            let (stream, resp) = try await URLSession.shared.bytes(for: req)
            guard (resp as? HTTPURLResponse)?.statusCode == 200 else {
                // エラーレスポンスをログ
                print("[AnthropicClient] HTTP error: \((resp as? HTTPURLResponse)?.statusCode ?? -1)")
                return nil
            }

            for try await line in stream.lines {
                if Task.isCancelled { break }
                
                // SSE format: "data: {...}" or "event: ..."
                guard line.hasPrefix("data: ") else { continue }
                let jsonStr = String(line.dropFirst(6))  // "data: " の6文字を削除
                guard jsonStr != "[DONE]",
                      let data = jsonStr.data(using: .utf8),
                      let event = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
                else { continue }

                let eventType = event["type"] as? String ?? ""

                switch eventType {
                case "content_block_delta":
                    guard let delta = event["delta"] as? [String: Any] else { continue }
                    let deltaType = delta["type"] as? String ?? ""

                    if deltaType == "text_delta", let text = delta["text"] as? String, !text.isEmpty {
                        accumulated += text
                        onToken?(text)   // ← UI にリアルタイム配信

                    } else if deltaType == "thinking_delta",
                              let think = delta["thinking"] as? String, !think.isEmpty {
                        accumulatedThink += think
                        onThinking?(think)
                    }

                case "message_stop":
                    break  // ストリーム終了

                case "error":
                    let err = (event["error"] as? [String: Any])?["message"] as? String ?? "unknown"
                    print("[AnthropicClient] API error: \(err)")
                    return nil

                default:
                    break
                }
            }

            let result = accumulated.trimmingCharacters(in: .whitespacesAndNewlines)
            return result.isEmpty ? nil : result

        } catch {
            print("[AnthropicClient] SSE error: \(error)")
            return nil
        }
    }

    // MARK: - streamGenerate() — AsyncThrowingStream (chat UI用)

    nonisolated public func streamGenerate(
        model: String,
        systemPrompt: String,
        messages: [(role: String, content: String)],
        maxTokens: Int = 8096,
        temperature: Double = 0.15,
        enableThinking: Bool = false
    ) -> AsyncThrowingStream<LLMStreamEvent, Error> {
        // actor-isolated プロパティは nonisolated コンテキストから参照不可——キーをコピーして渡す
        let capturedBaseURL = baseURL
        let capturedVersion = anthropicVersion
        let capturedBeta    = betaHeader

        return AsyncThrowingStream { continuation in
            Task {
                let apiKey = await AnthropicClient.shared.apiKey  // actor コンテキストから取得
                guard !apiKey.isEmpty else {
                    continuation.yield(.error("Anthropic API key not configured"))
                    continuation.finish(); return
                }
                guard let url = URL(string: "\(capturedBaseURL)/messages") else {
                    continuation.finish(); return
                }
                var req = URLRequest(url: url)
                req.httpMethod = "POST"
                req.setValue("application/json", forHTTPHeaderField: "Content-Type")
                req.setValue(apiKey, forHTTPHeaderField: "x-api-key")
                req.setValue(capturedVersion, forHTTPHeaderField: "anthropic-version")
                req.timeoutInterval = 600
                if enableThinking {
                    req.setValue(capturedBeta, forHTTPHeaderField: "anthropic-beta")
                }

                let anthropicMessages = messages.map { msg -> [String: Any] in
                    // In a static/closure context, we re-instantiate or just parse.
                    // But since we are inside AsyncThrowingStream which is a closure, we can duplicate the logic or call a static helper.
                    var safeContent = msg.content
                    while let startRange = safeContent.range(of: "<PRIVATE_OS_MEM>"),
                          let endRange = safeContent.range(of: "</PRIVATE_OS_MEM>") {
                        safeContent.removeSubrange(startRange.lowerBound..<endRange.upperBound)
                    }
                    return ["role": msg.role, "content": safeContent]
                }
                
                var safeSystem = systemPrompt
                while let startRange = safeSystem.range(of: "<PRIVATE_OS_MEM>"),
                      let endRange = safeSystem.range(of: "</PRIVATE_OS_MEM>") {
                    safeSystem.removeSubrange(startRange.lowerBound..<endRange.upperBound)
                }
                
                var body: [String: Any] = [
                    "model": model, "system": safeSystem,
                    "messages": anthropicMessages,
                    "max_tokens": max(maxTokens, 1024), "stream": true
                ]
                if !enableThinking { body["temperature"] = temperature }
                if enableThinking { body["thinking"] = ["type": "enabled", "budget_tokens": 10000] }

                guard let bodyData = try? JSONSerialization.data(withJSONObject: body) else {
                    continuation.finish(); return
                }
                req.httpBody = bodyData

                do {
                    let (stream, _) = try await URLSession.shared.bytes(for: req)
                    for try await line in stream.lines {
                        if Task.isCancelled { break }
                        
                        guard line.hasPrefix("data: ") else { continue }
                        let jsonStr = String(line.dropFirst(6))
                        guard jsonStr != "[DONE]",
                              let data = jsonStr.data(using: .utf8),
                              let event = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
                        else { continue }

                        switch event["type"] as? String ?? "" {
                        case "content_block_delta":
                            if let delta = event["delta"] as? [String: Any] {
                                if let text = delta["text"] as? String, !text.isEmpty {
                                    continuation.yield(.token(text))
                                } else if let think = delta["thinking"] as? String, !think.isEmpty {
                                    continuation.yield(.thinking(think))
                                }
                            }
                        case "message_stop":
                            continuation.yield(.done(stopReason: .endTurn))
                            continuation.finish(); return
                        case "error":
                            let msg = (event["error"] as? [String: Any])?["message"] as? String ?? "error"
                            continuation.yield(.error(msg)); continuation.finish(); return
                        default: break
                        }
                    }
                    continuation.yield(.done(stopReason: .endTurn))
                    continuation.finish()
                } catch {
                    continuation.yield(.error(error.localizedDescription))
                    continuation.finish(throwing: error)
                }
            }
        }
    }
}
