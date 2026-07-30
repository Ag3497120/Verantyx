import Foundation

/// Milestone N5 — client for Vera-alpha's `vera_server.py` (N2) HTTP+SSE
/// daemon. This is the "Vera as harness" chat path: instead of the IDE's
/// normal `AgentLoop`/`CouncilOrchestrator` driving the turn, the task is
/// handed to Vera's own `Agent.run()` ReAct loop, and progress streams
/// back over Server-Sent Events -- mirrors `OllamaClient.pullModel`'s
/// `.bytes(for:)` + `.lines` streaming pattern above, just against a
/// different local daemon.
///
/// Does not replace `VeraMemoryBridge`'s MCP-tool calls (ask/remember/
/// heartbeat/etc stay on MCP, unchanged) -- this is purely the new,
/// additive transport for the specific "let Vera run the whole turn"
/// mode, gated by `CouncilSettingsStore.useVeraHarnessForChat`.
actor VeraAgentClient {
    static let shared = VeraAgentClient()

    private init() {}

    var baseURL: String = "http://127.0.0.1:8765"
    private var launchedProcess: Process?

    /// Lazily launches `vera-memory ... serve` (same bundled binary
    /// Milestone H already embeds for MCP mode, see MCPEngine.swift's
    /// `bundledVeraMemory`/`VeraMemoryPaths`) if the daemon isn't already
    /// reachable. Idempotent -- a health check runs first so calling this
    /// repeatedly across chat turns doesn't spawn duplicate processes.
    func ensureServerRunning() async {
        if await isReachable() { return }

        let bundled = Bundle.main.executableURL?.deletingLastPathComponent().appendingPathComponent("vera-memory")
        guard let bundled, FileManager.default.fileExists(atPath: bundled.path) else { return }
        try? FileManager.default.createDirectory(at: VeraMemoryPaths.appSupportDir, withIntermediateDirectories: true)
        let storePath = VeraMemoryPaths.storeFile.path

        let process = Process()
        process.executableURL = bundled
        process.arguments = ["--store", storePath, "serve", "--port", "8765"]
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice
        do {
            try process.run()
            launchedProcess = process
        } catch {
            return
        }

        // Give the daemon a moment to bind before the first real request.
        // The frozen PyInstaller binary's own import/startup cost (not
        // just socket bind time) measured ~5-6s cold on this machine --
        // confirmed by direct standalone testing of the binary Milestone N
        // actually ships (`dist/vera-memory ... serve`, timed via curl
        // retries) -- so this polls for up to 12s, not a token 3s guess.
        for _ in 0..<40 {
            if await isReachable() { return }
            try? await Task.sleep(nanoseconds: 300_000_000)
        }
    }

    private func isReachable() async -> Bool {
        guard let url = URL(string: "\(baseURL)/agent/run/__health_check__") else { return false }
        var req = URLRequest(url: url)
        req.timeoutInterval = 2
        guard let (_, resp) = try? await URLSession.shared.data(for: req),
              let http = resp as? HTTPURLResponse
        else { return false }
        return http.statusCode == 404 || http.statusCode == 200  // any real HTTP reply means the daemon is up
    }

    struct AgentStepEvent: Sendable {
        let raw: [String: Any]
        var source: String? { raw["source"] as? String }
        var isTerminal: Bool { raw["final"] != nil }
    }

    enum ClientError: Error, LocalizedError {
        case badResponse(String)
        var errorDescription: String? {
            switch self {
            case .badResponse(let s): return "VeraAgentClient: \(s)"
            }
        }
    }

    /// Starts a run and streams every `on_step` event Vera-alpha's
    /// `Agent.run(task, on_step=...)` (N1) pushes, ending with the event
    /// that carries a `"final"` key. Callers typically feed `onEvent` into
    /// the same kind of `LoopEvent`-shaped UI update `ExecutionAgent`/
    /// `CouncilOrchestrator` already drive (see ModelSelectorBarView's
    /// harness toggle wiring).
    func runAgent(
        task: String, model: String = "", backend: String = "ollama",
        cognitionMode: String = "normal",
        onEvent: @escaping (AgentStepEvent) -> Void
    ) async throws -> [String: Any] {
        guard let startURL = URL(string: "\(baseURL)/agent/run") else {
            throw ClientError.badResponse("invalid_base_url")
        }
        var req = URLRequest(url: startURL)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let body: [String: Any] = [
            "task": task, "model": model, "backend": backend,
            "cognition_mode": cognitionMode,
        ]
        req.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (startData, startResp) = try await URLSession.shared.data(for: req)
        guard let http = startResp as? HTTPURLResponse, http.statusCode == 202,
              let startObj = try? JSONSerialization.jsonObject(with: startData) as? [String: Any],
              let runId = startObj["run_id"] as? String
        else {
            let text = String(data: startData, encoding: .utf8) ?? ""
            throw ClientError.badResponse("start_failed: \(text)")
        }

        guard let eventsURL = URL(string: "\(baseURL)/events?run_id=\(runId)") else {
            throw ClientError.badResponse("invalid_events_url")
        }
        var eventsReq = URLRequest(url: eventsURL)
        eventsReq.timeoutInterval = .infinity

        let (stream, eventsResp) = try await URLSession.shared.bytes(for: eventsReq)
        guard let eventsHTTP = eventsResp as? HTTPURLResponse, eventsHTTP.statusCode == 200 else {
            throw ClientError.badResponse("events_stream_failed")
        }

        for try await line in stream.lines {
            guard line.hasPrefix("data: ") else { continue }
            let payload = String(line.dropFirst("data: ".count))
            guard let data = payload.data(using: .utf8),
                  let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
            else { continue }
            if obj.isEmpty { break }  // the terminal "event: done\ndata: {}" marker
            onEvent(AgentStepEvent(raw: obj))
        }

        // SSE stream closed after the terminal marker -- fetch the
        // authoritative final result rather than trusting the last event
        // (mirrors vera_server.py's own "/agent/run/<id> is the source of
        // truth" design, the SSE stream is a progress convenience only).
        guard let resultURL = URL(string: "\(baseURL)/agent/run/\(runId)") else {
            throw ClientError.badResponse("invalid_result_url")
        }
        let (resultData, _) = try await URLSession.shared.data(from: resultURL)
        guard let resultObj = try? JSONSerialization.jsonObject(with: resultData) as? [String: Any],
              let result = resultObj["result"] as? [String: Any]
        else {
            throw ClientError.badResponse("no_result")
        }
        return result
    }
}
