import Foundation

/// LM Studio as an ordinary chat backend.
///
/// LM Studio was already scanned for JGEN conversion sources but could not be
/// used to actually talk to a model — so a user who kept their models there had
/// to install them a second time under Ollama just to chat. That gap became the
/// whole story once Ollama was dropped as a conversion source: LM Studio ships
/// the original safetensors and a real `config.json`, which is exactly what makes
/// its models convert cleanly, and it would be perverse to recommend it for
/// conversion while refusing to chat with it.
///
/// It exposes an OpenAI-compatible server (default `http://127.0.0.1:1234/v1`),
/// so this is the same request/SSE shape `MLXRunner.streamGenerateTokens` already
/// speaks — `data: ` lines carrying `choices[0].delta.content`, terminated by
/// `data: [DONE]`.
///
/// One real difference from Ollama worth knowing: **LM Studio does not start its
/// server automatically**. If "Local Server" is not running in the app, every
/// call here fails with a connection error — which is why `isAvailable()` exists
/// and why the settings UI leads with it rather than showing an empty model list.
actor LMStudioClient {

    static let shared = LMStudioClient()

    static let defaultEndpoint = "http://127.0.0.1:1234/v1"

    private func baseURL() async -> String {
        let configured = await MainActor.run { AppState.shared?.lmStudioEndpoint ?? "" }
        return Self.normalized(configured)
    }

    /// What the user typed, turned into a URL that actually works.
    ///
    /// Every one of these forms was reachable in the UI and every one of them
    /// failed silently, because the string was concatenated with "/models" and
    /// handed to `URL(string:)`:
    ///
    ///   `127.0.0.1:1234`        → `URL(string:)` reads "127.0.0.1" as the SCHEME
    ///   `localhost:1234/v1`     → same, and `localhost` may resolve to `::1`
    ///                              first while LM Studio binds IPv4 loopback
    ///   `http://127.0.0.1:1234` → `…:1234/models`, which is not a route
    ///   `…/v1/`                 → `…/v1//models`, likewise
    ///
    /// So: force a scheme, force IPv4 loopback for the loopback names, force
    /// exactly one `/v1`, and strip the trailing slash. Left as a pure static
    /// function so the settings screen can show the result of the rewrite —
    /// a silent correction the user cannot see is its own kind of bug.
    nonisolated static func normalized(_ raw: String) -> String {
        var t = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        if t.isEmpty { return defaultEndpoint }
        if !t.contains("://") { t = "http://" + t }
        while t.hasSuffix("/") { t.removeLast() }
        // `localhost` is not a synonym here: LM Studio listens on 127.0.0.1,
        // and a `::1`-first resolution gives "Connection refused" with no clue.
        t = t.replacingOccurrences(of: "://localhost", with: "://127.0.0.1")
        if t.hasSuffix("/v1") { return t }
        if let r = t.range(of: "/v1/") { return String(t[t.startIndex..<r.upperBound].dropLast()) }
        return t + "/v1"
    }

    // MARK: - Diagnosis

    /// Why LM Studio is not answering — with the remedy attached.
    ///
    /// `isAvailable() -> Bool` could only ever produce "not running", which is
    /// the same sentence for four different situations: the app is not
    /// installed, the app is closed, the app is open with its server off, and
    /// the server is up but the endpoint points somewhere else. The remedies
    /// are all different, and three of the four are one press.
    enum Diagnosis: Equatable {
        case ready(models: Int)
        /// Server answered, but no chat model is loaded or loadable.
        case noModels
        case serverOff(canStart: Bool)
        case notInstalled
        /// Reachable, wrong shape — usually a hand-edited endpoint.
        case badEndpoint(status: Int, resolved: String)

        var isReady: Bool { if case .ready = self { return true }; return false }
    }

    static let appPath = "/Applications/LM Studio.app"

    /// LM Studio's own CLI, which ships inside the app's data directory.
    nonisolated static func lmsBinary() -> String? {
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        for p in ["\(home)/.lmstudio/bin/lms",
                  "/usr/local/bin/lms",
                  "/opt/homebrew/bin/lms"] where FileManager.default.isExecutableFile(atPath: p) {
            return p
        }
        return nil
    }

    func diagnose() async -> Diagnosis {
        let base = await baseURL()
        guard let url = URL(string: "\(base)/models") else {
            return .badEndpoint(status: 0, resolved: base)
        }
        var req = URLRequest(url: url)
        req.timeoutInterval = 3
        do {
            let (data, resp) = try await URLSession.shared.data(for: req)
            guard let http = resp as? HTTPURLResponse else {
                return .badEndpoint(status: 0, resolved: base)
            }
            guard http.statusCode == 200 else {
                return .badEndpoint(status: http.statusCode, resolved: base)
            }
            let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
            let items = (json?["data"] as? [[String: Any]]) ?? []
            let chat = items.compactMap { $0["id"] as? String }.filter { !isEmbeddingModel($0) }
            return chat.isEmpty ? .noModels : .ready(models: chat.count)
        } catch {
            // Nothing listening. Separate "no LM Studio at all" from "LM Studio
            // is there and its server is off", because only the second one has
            // a button.
            guard FileManager.default.fileExists(atPath: Self.appPath)
                    || Self.lmsBinary() != nil else { return .notInstalled }
            return .serverOff(canStart: Self.lmsBinary() != nil)
        }
    }

    /// Starts the local server through LM Studio's CLI. Returns nil on success.
    ///
    /// `lms server start` launches the app headlessly if it is not already
    /// running, so this covers "closed" and "open but server off" with one
    /// action. Polls afterwards rather than trusting the exit code: the CLI
    /// returns before the port is accepting.
    func startServer() async -> String? {
        guard let lms = Self.lmsBinary() else {
            return "LM Studio's `lms` CLI was not found. Open LM Studio → Developer → Start Server."
        }
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: lms)
        proc.arguments = ["server", "start"]
        let pipe = Pipe()
        proc.standardOutput = pipe
        proc.standardError = pipe
        do { try proc.run() } catch { return error.localizedDescription }
        proc.waitUntilExit()
        for _ in 0..<20 {
            if await diagnose().isReady { return nil }
            if case .noModels = await diagnose() { return nil }
            try? await Task.sleep(nanoseconds: 500_000_000)
        }
        let out = String(data: pipe.fileHandleForReading.readDataToEndOfFile(),
                         encoding: .utf8) ?? ""
        return out.isEmpty
            ? "The server did not come up within 10 seconds."
            : out.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// No timeout — a large local model can spend minutes on one reply, and the
    /// default 60 s would cut it off mid-sentence. Same reasoning as
    /// `OllamaClient`'s streaming session.
    private let session: URLSession = {
        let c = URLSessionConfiguration.default
        c.timeoutIntervalForRequest = .infinity
        c.timeoutIntervalForResource = .infinity
        return URLSession(configuration: c)
    }()

    // MARK: - Discovery

    /// True when LM Studio's local server is actually accepting connections.
    /// Short timeout: this gates UI, so it must not hang when the server is off.
    func isAvailable() async -> Bool {
        guard let url = URL(string: "\(await baseURL())/models") else { return false }
        var req = URLRequest(url: url)
        req.timeoutInterval = 2
        guard let (_, resp) = try? await URLSession.shared.data(for: req),
              let http = resp as? HTTPURLResponse else { return false }
        return http.statusCode == 200
    }

    /// Model ids currently loaded or loadable in LM Studio.
    ///
    /// Embedding models are filtered out: LM Studio lists them alongside chat
    /// models in the same array, and picking one produces a confusing failure at
    /// generation time rather than at selection time.
    func listModels() async -> [String] {
        guard let url = URL(string: "\(await baseURL())/models") else { return [] }
        var req = URLRequest(url: url)
        req.timeoutInterval = 5
        guard let (data, _) = try? await URLSession.shared.data(for: req),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let items = json["data"] as? [[String: Any]] else { return [] }
        return items
            .compactMap { $0["id"] as? String }
            .filter { !isEmbeddingModel($0) }
            .sorted()
    }

    nonisolated func isEmbeddingModel(_ id: String) -> Bool {
        let l = id.lowercased()
        return l.contains("embed") || l.contains("bge-") || l.contains("gte-")
    }

    // MARK: - Chat

    /// Streams a reply and returns the accumulated text.
    ///
    /// Returns the locally accumulated string rather than a separate final field
    /// because the OpenAI streaming shape has no authoritative "full text" event
    /// — the deltas *are* the answer.
    /// 一枚の画像と一つの問いを送って、返事を丸ごと受け取る。
    ///
    /// 既存の `generateConversation` は content を文字列で送るので画像を
    /// 運べない。OpenAI 互換の視覚形式は content が配列になるため、
    /// 既存の経路を触らず別の口として足してある(共有の経路を書き換えると、
    /// 画像と関係ない会話まで形が変わる)。
    ///
    /// 流さないのは、呼び手が一回分の答えしか要らないため。
    func generateWithImage(
        model: String,
        systemPrompt: String,
        userText: String,
        imageBase64: String,
        mimeType: String = "image/jpeg",
        temperature: Double = 0.15,
        // 900 では足りません。**enable_thinking を解さないサーバがあり**、
        // 思考だけで枠を使い切って本文が空で返ります(2026-08-23 実測:
        // qwen3.6-35b-a3b @ LM Studio, reasoning_tokens 1799 / content 0)。
        // 4000 は同じ組で本文が出た値。上限なしは別の壊れ方(15分返らない)
        // をするので外しません。
        maxTokens: Int = 4000,
        noThink: Bool = true
    ) async -> String? {
        guard let url = URL(string: "\(await baseURL())/chat/completions")
        else { return nil }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.timeoutInterval = 300
        // LM Studio accepts ``chat_template_kwargs`` but some Qwen-derived
        // templates silently ignore it.  In the Atelier vision worker this
        // previously spent the complete 5k-token budget on hidden reasoning
        // and returned an empty body, so the real pixel proposal was discarded
        // and every image fell back to the same outline-only candidates.
        // ``/no_think`` is the template-level equivalent; ``reasoning_effort``
        // covers OpenAI-compatible runtimes that understand that spelling.
        let finalUserText = noThink ? "/no_think\n" + userText : userText
        let finalSystemPrompt = noThink
            ? "/no_think\nReturn the requested final result immediately. Do not emit reasoning.\n"
                + systemPrompt
            : systemPrompt
        let content: [[String: Any]] = [
            ["type": "text", "text": finalUserText],
            ["type": "image_url",
             "image_url": ["url": "data:\(mimeType);base64,\(imageBase64)"]],
        ]
        var messages: [[String: Any]] = []
        if !finalSystemPrompt.isEmpty {
            messages.append(["role": "system", "content": finalSystemPrompt])
        }
        messages.append(["role": "user", "content": content])
        // **上限を外さない。** 会話用の経路は -1(モデルが止まるまで)で
        // よいが、ここは推論するモデルに一枚の絵を渡す口で、実測では
        // 上限なしだと考え続けて15分経っても返らなかった。求めているのは
        // 短い JSON 配列一つなので、届かない長さで切る。
        var payload: [String: Any] = [
            "model": model, "messages": messages,
            "max_tokens": maxTokens, "temperature": temperature,
            "stream": false,
        ]
        if noThink {
            // 推論するモデルは上限を思考で使い切り、本文を出さずに終わる
            // (実測: Qwen3.8-27B が 200 秒かけて JSON 無し)。ここで
            // 欲しいのは短い配列一つで、途中の考えではない。
            // この鍵を解さないモデルは無視するだけなので、付けて損はない。
            payload["chat_template_kwargs"] = ["enable_thinking": false]
            payload["reasoning_effort"] = "none"
        }
        req.httpBody = try? JSONSerialization.data(withJSONObject: payload)

        guard let (data, response) = try? await session.data(for: req) else {
            return nil
        }
        if let http = response as? HTTPURLResponse, http.statusCode != 200 {
            // 視覚に対応していないモデルを選ぶと 400 が返る。黙って空を
            // 返すと「モデルが何も言わなかった」と読めてしまうので、
            // 何が起きたかをそのまま渡す。
            let body = String(data: data, encoding: .utf8) ?? ""
            return "LM Studio error: HTTP \(http.statusCode) "
                + body.prefix(300)
        }
        guard let json = try? JSONSerialization.jsonObject(with: data)
                as? [String: Any],
              let choices = json["choices"] as? [[String: Any]],
              let first = choices.first,
              let msg = first["message"] as? [String: Any]
        else { return nil }
        let text = (msg["content"] as? String) ?? ""
        if text.isEmpty {
            // **「考えの途中で切った」と「何も言わなかった」を区別する。**
            // 混ぜると、枠が足りないだけなのに「モデルが答えない」と
            // 読めてしまい、直す先を間違えます。
            let reason = first["finish_reason"] as? String ?? ""
            let usage = json["usage"] as? [String: Any] ?? [:]
            let detail = (usage["completion_tokens_details"]
                          as? [String: Any]) ?? [:]
            let think = detail["reasoning_tokens"] as? Int ?? 0
            if reason == "length" || think > 0 {
                return "LM Studio: 本文が空です。思考に \(think) トークン"
                    + " 使い、上限 \(maxTokens) で切れました"
                    + "(finish_reason=\(reason))。上限を上げてください"
            }
            return nil
        }
        return text
    }

    /// Receives one complete text turn for proposal-only workers.
    ///
    /// The ordinary chat path streams reasoning and content until EOS.  That
    /// is useful for a visible chat transcript, but it is the wrong transport
    /// for Atelier's model mouth: a proxy can close a long reasoning stream
    /// after the request was accepted, and the resulting URL error used to be
    /// displayed as if it were model-authored garment advice.  This bounded,
    /// non-streaming path asks LM Studio for final content only.  Transport and
    /// HTTP failures return nil, so Vera can render them as system state rather
    /// than unverified AI speech.
    func generateCompleteConversation(
        model: String,
        messages: [(role: String, content: String)],
        maxTokens: Int = 4000,
        temperature: Double = 0.15,
        responseFormat: [String: Any]? = nil
    ) async -> String? {
        // Proposal workers need the bounded final JSON, not a long hidden
        // reasoning turn.  Some Qwen templates ignore enable_thinking=false;
        // the template command and OpenAI-compatible flag close the same gap
        // already observed on the pixel worker.
        let finalMessages = messages.map { message -> [String: String] in
            let prefix = message.role == "user"
                ? "/no_think\nReturn the requested final JSON object immediately. Do not emit reasoning.\n"
                : ""
            return ["role": message.role, "content": prefix + message.content]
        }
        guard let url = URL(string: "\(await baseURL())/chat/completions")
        else { return nil }

        func requestOnce(_ format: [String: Any]?) async -> String? {
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.timeoutInterval = 300
            var body: [String: Any] = [
                "model": model,
                "messages": finalMessages,
                "max_tokens": max(256, maxTokens),
                "temperature": temperature,
                "stream": false,
                "chat_template_kwargs": ["enable_thinking": false],
                "reasoning_effort": "none",
            ]
            if let format { body["response_format"] = format }
            guard let encoded = try? JSONSerialization.data(withJSONObject: body)
            else { return nil }
            request.httpBody = encoded
            do {
                let (data, response) = try await session.data(for: request)
                guard let http = response as? HTTPURLResponse,
                      (200..<300).contains(http.statusCode),
                      let json = try? JSONSerialization.jsonObject(with: data)
                        as? [String: Any],
                      let choices = json["choices"] as? [[String: Any]],
                      let message = choices.first?["message"] as? [String: Any],
                      let content = message["content"] as? String else {
                    return nil
                }
                let trimmed = content.trimmingCharacters(in: .whitespacesAndNewlines)
                return trimmed.isEmpty ? nil : trimmed
            } catch {
                return nil
            }
        }

        if let exact = await requestOnce(responseFormat) { return exact }
        // OpenAI-compatible servers differ in how much JSON Schema they
        // implement.  A transport-level schema rejection must not masquerade
        // as an unreachable model: retry once without server-side grammar and
        // let Atelier's decoder plus Vera capability gate validate the same
        // closed envelope.  This does not grant the model any extra action.
        guard responseFormat != nil else { return nil }
        return await requestOnce(nil)
    }

    func generateConversation(
        model: String,
        messages: [(role: String, content: String)],
        maxTokens: Int,
        temperature: Double,
        onToken: (@Sendable (String) -> Void)? = nil
    ) async -> String? {
        guard let url = URL(string: "\(await baseURL())/chat/completions") else { return nil }

        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        // No token budget: -1 is LM Studio's "generate until the model stops".
        // A fixed budget turned every long-thinking turn into a failure
        // ("spent its whole budget thinking"); the reply now runs to EOS, the
        // same behavior as LM Studio's own chat window. `maxTokens` is kept in
        // the signature so callers don't churn, but it no longer caps anything.
        _ = maxTokens
        let body: [String: Any] = [
            "model": model,
            "messages": messages.map { ["role": $0.role, "content": $0.content] },
            "max_tokens": -1,
            "temperature": temperature,
            "stream": true,
        ]
        req.httpBody = try? JSONSerialization.data(withJSONObject: body)

        var accumulated = ""
        var inReasoning = false
        do {
            let (stream, response) = try await session.bytes(for: req)
            if let http = response as? HTTPURLResponse, http.statusCode != 200 {
                return "LM Studio error: HTTP \(http.statusCode). Is the Local Server running?"
            }
            for try await line in stream.lines {
                guard line.hasPrefix("data: ") else { continue }
                let payload = String(line.dropFirst(6))
                if payload == "[DONE]" { break }
                guard let d = payload.data(using: .utf8),
                      let json = try? JSONSerialization.jsonObject(with: d) as? [String: Any],
                      let choices = json["choices"] as? [[String: Any]],
                      let delta = choices.first?["delta"] as? [String: Any]
                else { continue }
                // Reasoning models (muse-glimmer, qwen3.x) stream their
                // thinking as `reasoning_content`, not `content`. Show it —
                // wrapped in <think> tags so the transcript styles it as
                // reasoning — instead of silently dropping it and then
                // reporting an all-thinking turn as a failure.
                if let r = delta["reasoning_content"] as? String, !r.isEmpty {
                    if !inReasoning {
                        inReasoning = true
                        accumulated += "<think>"
                        onToken?("<think>")
                    }
                    accumulated += r
                    onToken?(r)
                }
                guard let content = delta["content"] as? String, !content.isEmpty
                else { continue }
                if inReasoning {
                    inReasoning = false
                    accumulated += "</think>\n"
                    onToken?("</think>\n")
                }
                accumulated += content
                onToken?(content)
            }
        } catch {
            // Distinguish "server is off" from a genuine failure — this is the
            // single most likely thing to go wrong, and it has a one-step fix.
            if let urlErr = error as? URLError,
               urlErr.code == .cannotConnectToHost || urlErr.code == .networkConnectionLost {
                return "Cannot reach LM Studio at \(await baseURL()). "
                     + "Open LM Studio → Developer → start the Local Server."
            }
            return "LM Studio error: \(error.localizedDescription)"
        }
        // Stream ended mid-thought (stop button, disconnect): close the tag so
        // the transcript still styles what did arrive as reasoning.
        if inReasoning {
            accumulated += "</think>"
            onToken?("</think>")
        }
        return accumulated.isEmpty ? nil : accumulated
    }
}
