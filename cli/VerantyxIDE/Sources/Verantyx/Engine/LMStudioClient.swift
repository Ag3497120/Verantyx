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
        let trimmed = configured.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? Self.defaultEndpoint : trimmed
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
        let body: [String: Any] = [
            "model": model,
            "messages": messages.map { ["role": $0.role, "content": $0.content] },
            "max_tokens": maxTokens,
            "temperature": temperature,
            "stream": true,
        ]
        req.httpBody = try? JSONSerialization.data(withJSONObject: body)

        var accumulated = ""
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
                      let delta = choices.first?["delta"] as? [String: Any],
                      let content = delta["content"] as? String,
                      !content.isEmpty
                else { continue }
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
        return accumulated.isEmpty ? nil : accumulated
    }
}
