import Foundation
import Network

/// Milestone N4 — the IDE's half of "Vera as harness, IDE as tool provider".
///
/// Vera-alpha's `vera_server.py` (Milestone N2) runs Agent.run()'s ReAct
/// loop as the primary controller; its `llm` callback normally talks
/// straight to Ollama, but when a request sets `"backend": "jgen"`, Vera's
/// daemon instead POSTs to this server so it can use JGEN (JCrossEngine)
/// as a subordinate tool -- something Vera-alpha's own Python process has
/// no way to reach on its own (JGEN only exists in-process here, wrapped
/// by `JCrossChatManager`).
///
/// Deliberately the IDE's first-ever server role (every prior local
/// integration -- `OllamaClient`, `MCPEngine` -- has been a client). Kept
/// intentionally minimal: one endpoint, no chunked bodies, loopback-only,
/// no auth (matches vera_server.py's own "local-only, no auth" v1 stance).
actor JGenAgentServer {
    static let shared = JGenAgentServer()

    private var listener: NWListener?
    private(set) var port: UInt16 = 0
    private(set) var isRunning = false

    private init() {}

    enum ServerError: Error, LocalizedError {
        case noPortAvailable
        var errorDescription: String? { "JGenAgentServer: no free port in the fallback range" }
    }

    /// Binds 127.0.0.1 starting at `preferredPort`, falling back to the
    /// next few ports if taken (mirrors the plan's "fallback on conflict"
    /// requirement without a full port-registry mechanism).
    func start(preferredPort: UInt16 = 8766) async throws {
        guard !isRunning else { return }
        var lastError: Error?
        for candidate in preferredPort..<(preferredPort + 8) {
            do {
                try await bind(port: candidate)
                port = candidate
                isRunning = true
                return
            } catch {
                lastError = error
            }
        }
        throw lastError ?? ServerError.noPortAvailable
    }

    func stop() {
        listener?.cancel()
        listener = nil
        isRunning = false
        port = 0
    }

    private func bind(port: UInt16) async throws {
        let params = NWParameters.tcp
        guard let nwPort = NWEndpoint.Port(rawValue: port) else { throw ServerError.noPortAvailable }
        let listener = try NWListener(using: params, on: nwPort)
        // Loopback-only: no auth, so never accept beyond 127.0.0.1 (the
        // listener itself has no interface filter, but callers other than
        // vera_server.py's own local process have no reason to know the
        // port -- see the class doc's "local-only, no auth" note).
        listener.newConnectionHandler = { [weak self] connection in
            Task { await self?.handle(connection: connection) }
        }
        listener.start(queue: .global(qos: .userInitiated))
        self.listener = listener
        // Give the listener a moment to actually bind before declaring success.
        try await Task.sleep(nanoseconds: 100_000_000)
        switch listener.state {
        case .failed, .cancelled:
            throw ServerError.noPortAvailable
        default:
            break
        }
    }

    private func handle(connection: NWConnection) async {
        connection.start(queue: .global(qos: .userInitiated))
        guard let request = await Self.readRequest(connection: connection) else {
            connection.cancel()
            return
        }
        guard request.method == "POST" else {
            await Self.writeResponse(connection: connection, status: 404, body: ["ok": false, "error": "not_found"])
            connection.cancel()
            return
        }
        switch request.path {
        case "/jgen/generate":
            await handleJGenGenerate(request: request, connection: connection)
        case "/browser/fetch":
            await handleBrowserFetch(request: request, connection: connection)
        default:
            await Self.writeResponse(connection: connection, status: 404, body: ["ok": false, "error": "not_found"])
        }
        connection.cancel()
    }

    /// Vera-alpha's fetch_url (agent_tools.py) prefers this over its own
    /// urllib scrape when a browser endpoint is configured -- real WKWebView
    /// rendering handles JS-heavy pages (and gives BrowserBridge's own
    /// markdown extraction, which doesn't drown in raw HTML chrome the way
    /// a naive tag-strip does on pages like GitHub's repo view).
    private func handleBrowserFetch(request: ParsedRequest, connection: NWConnection) async {
        guard
            let data = request.body,
            let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let url = obj["url"] as? String
        else {
            await Self.writeResponse(connection: connection, status: 400, body: ["ok": false, "error": "bad_request"])
            return
        }
        do {
            let markdown = try await BrowserBridge.shared.fetch(url)
            await Self.writeResponse(connection: connection, status: 200, body: ["ok": true, "url": url, "markdown": markdown])
        } catch {
            await Self.writeResponse(connection: connection, status: 502, body: ["ok": false, "error": "\(error)"])
        }
    }

    private func handleJGenGenerate(request: ParsedRequest, connection: NWConnection) async {
        guard
            let data = request.body,
            let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let prompt = obj["prompt"] as? String
        else {
            await Self.writeResponse(connection: connection, status: 400, body: ["ok": false, "error": "bad_request"])
            return
        }
        let system = obj["system"] as? String

        guard await JCrossChatManager.shared.isLoaded else {
            await Self.writeResponse(connection: connection, status: 503, body: ["ok": false, "error": "jgen_not_loaded"])
            return
        }

        var conversation: [(role: String, content: String)] = []
        if let system, !system.isEmpty {
            conversation.append((role: "system", content: system))
        }
        conversation.append((role: "user", content: prompt))

        do {
            let text = try await JCrossChatManager.shared.generate(conversation: conversation, maxTokens: 512)
            await Self.writeResponse(connection: connection, status: 200, body: ["ok": true, "text": text])
        } catch {
            await Self.writeResponse(connection: connection, status: 500, body: ["ok": false, "error": "\(error)"])
        }
    }

    // MARK: - Minimal HTTP/1.1 parsing (GET/POST, Content-Length only, no chunked)

    private struct ParsedRequest {
        let method: String
        let path: String
        let body: Data?
    }

    private static func readRequest(connection: NWConnection) async -> ParsedRequest? {
        var buffer = Data()
        while true {
            let chunk: Data? = await withCheckedContinuation { cont in
                connection.receive(minimumIncompleteLength: 1, maximumLength: 65536) { data, _, _, error in
                    if let data, !data.isEmpty {
                        cont.resume(returning: data)
                    } else {
                        cont.resume(returning: nil)
                    }
                }
            }
            guard let chunk else { break }
            buffer.append(chunk)
            guard let headerEndRange = buffer.range(of: Data("\r\n\r\n".utf8)) else { continue }

            let headerData = buffer[..<headerEndRange.lowerBound]
            guard let headerText = String(data: headerData, encoding: .utf8) else { return nil }
            let lines = headerText.components(separatedBy: "\r\n")
            guard let requestLine = lines.first else { return nil }
            let parts = requestLine.split(separator: " ")
            guard parts.count >= 2 else { return nil }
            let method = String(parts[0])
            let path = String(parts[1])

            var contentLength = 0
            for line in lines.dropFirst() {
                if line.lowercased().hasPrefix("content-length:") {
                    let value = line.split(separator: ":", maxSplits: 1)[1].trimmingCharacters(in: .whitespaces)
                    contentLength = Int(value) ?? 0
                }
            }

            let bodyStart = headerEndRange.upperBound
            while buffer.count - bodyStart < contentLength {
                let more: Data? = await withCheckedContinuation { cont in
                    connection.receive(minimumIncompleteLength: 1, maximumLength: 65536) { data, _, _, _ in
                        cont.resume(returning: data)
                    }
                }
                guard let more, !more.isEmpty else { break }
                buffer.append(more)
            }
            let body = contentLength > 0 ? buffer[bodyStart..<min(bodyStart + contentLength, buffer.count)] : nil
            return ParsedRequest(method: method, path: path, body: body.map { Data($0) })
        }
        return nil
    }

    private static func writeResponse(connection: NWConnection, status: Int, body: [String: Any]) async {
        let data = (try? JSONSerialization.data(withJSONObject: body)) ?? Data()
        let statusText = status == 200 ? "OK" : status == 400 ? "Bad Request"
            : status == 404 ? "Not Found" : status == 503 ? "Service Unavailable" : "Internal Server Error"
        var response = "HTTP/1.1 \(status) \(statusText)\r\n"
        response += "Content-Type: application/json\r\n"
        response += "Content-Length: \(data.count)\r\n"
        response += "Connection: close\r\n\r\n"
        var out = Data(response.utf8)
        out.append(data)
        await withCheckedContinuation { (cont: CheckedContinuation<Void, Never>) in
            connection.send(content: out, completion: .contentProcessed { _ in cont.resume() })
        }
    }
}
