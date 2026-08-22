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
