import Foundation
import Darwin   // kill(), SIGTERM, SIGKILL

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
    /// Endpoint we passed as `--jgen-endpoint` when launching serve.
    /// Restart is required when the IDE's JGenAgentServer port changes or
    /// when we previously launched without a JGEN bridge and now need one.
    private var launchedJgenEndpoint: String?

    enum EnsureResult: Sendable, Equatable {
        case ready
        case binaryMissing
        case launchFailed(String)
        case notReachable

        var isReady: Bool {
            if case .ready = self { return true }
            return false
        }
    }

    enum ClientError: Error, LocalizedError {
        case badResponse(String)
        case serverUnavailable(EnsureResult)

        var errorDescription: String? {
            switch self {
            case .badResponse(let s): return "VeraAgentClient: \(s)"
            case .serverUnavailable(let r):
                switch r {
                case .ready: return "VeraAgentClient: unexpected"
                case .binaryMissing:
                    return "Vera HTTP が起動できません — MCP/同梱バイナリを確認"
                case .launchFailed(let detail):
                    return "Vera HTTP が起動できません — \(detail)"
                case .notReachable:
                    return "Vera HTTP が起動できません — :8765 に応答なし（serve.log / 同梱 vera-memory を確認）"
                }
            }
        }
    }

    /// Lazily launches `vera-memory ... serve` (same bundled binary
    /// Milestone H already embeds for MCP mode, see MCPEngine.swift's
    /// `bundledVeraMemory`/`VeraMemoryPaths`) if the daemon isn't already
    /// reachable. Idempotent WITHIN a running app instance -- a health
    /// check runs first so calling this repeatedly across chat turns
    /// doesn't spawn duplicate processes.
    ///
    /// Real bug found live: this used to trust ANY reachable server on the
    /// port, including one left over from a previous app run. Now: if we
    /// don't already own a live `launchedProcess` from THIS app session,
    /// anything already on the port gets killed first, then a fresh
    /// process is always launched. Also restarts when `jgenEndpoint`
    /// changes so `"backend": "jgen"` can reach JGenAgentServer.
    @discardableResult
    func ensureServerRunning(jgenEndpoint: String? = nil) async -> EnsureResult {
        let wantEndpoint = Self.normalizedEndpoint(jgenEndpoint)
        if let p = launchedProcess, p.isRunning,
           launchedJgenEndpoint == wantEndpoint,
           await isReachable() {
            return .ready
        }

        // Endpoint / ownership mismatch → reclaim and relaunch.
        stopOwnedProcess()
        killAnyProcessOnPort(8765)

        let bundled = VeraMemoryPaths.resolveBundledBinary()
        guard let bundled else { return .binaryMissing }

        if VeraMemoryPaths.missingLibraryValidationEntitlement(at: bundled) {
            return .launchFailed(VeraMemoryPaths.outdatedHardenedRuntimeMessage)
        }

        try? FileManager.default.createDirectory(at: VeraMemoryPaths.appSupportDir, withIntermediateDirectories: true)
        let storePath = VeraMemoryPaths.storeFile.path

        let process = Process()
        process.executableURL = bundled
        var args = ["--store", storePath, "serve", "--port", "8765"]
        if let wantEndpoint {
            args += ["--jgen-endpoint", wantEndpoint]
        }
        process.arguments = args
        // Real bug found live: stdout/stderr went to /dev/null, so a real
        // hang (0% CPU, no response) had no way to be diagnosed from
        // outside -- no Python traceback, no Rust println! progress line,
        // nothing. Redirect to a log file instead; harmless when nothing
        // goes wrong (the file just grows slowly), essential when it does.
        let logURL = VeraMemoryPaths.appSupportDir.appendingPathComponent("serve.log")
        FileManager.default.createFile(atPath: logURL.path, contents: nil)
        if let logHandle = try? FileHandle(forWritingTo: logURL) {
            process.standardOutput = logHandle
            process.standardError = logHandle
        } else {
            process.standardOutput = FileHandle.nullDevice
            process.standardError = FileHandle.nullDevice
        }
        do {
            try process.run()
            launchedProcess = process
            launchedJgenEndpoint = wantEndpoint
        } catch {
            let annotated = VeraMemoryPaths.annotateLaunchFailure(error.localizedDescription)
            return .launchFailed(annotated)
        }

        // Give the daemon a moment to bind before the first real request.
        // The frozen PyInstaller binary's own import/startup cost (not
        // just socket bind time) measured ~5-6s cold on this machine --
        // confirmed by direct standalone testing of the binary Milestone N
        // actually ships (`dist/vera-memory ... serve`, timed via curl
        // retries) -- so this polls for up to 12s, not a token 3s guess.
        for _ in 0..<40 {
            if await isReachable() { return .ready }
            if let p = launchedProcess, !p.isRunning {
                let annotated = VeraMemoryPaths.annotateLaunchFailure(
                    "vera-memory serve exited early (see \(logURL.path))"
                )
                return .launchFailed(annotated)
            }
            try? await Task.sleep(nanoseconds: 300_000_000)
        }
        return .notReachable
    }

    /// `lsof -ti:<port>` + SIGTERM (then SIGKILL if it's still alive after
    /// a beat) -- the only reliable cross-launch way to reclaim a port
    /// held by a process this app instance doesn't have a handle to.
    /// Best-effort: failures here just mean the subsequent bind attempt
    /// fails too, which `ensureServerRunning`'s reachability polling
    /// already surfaces as "server never came up" rather than crashing.
    private func killAnyProcessOnPort(_ port: Int) {
        let lsof = Process()
        lsof.executableURL = URL(fileURLWithPath: "/usr/sbin/lsof")
        lsof.arguments = ["-ti", ":\(port)"]
        let pipe = Pipe()
        lsof.standardOutput = pipe
        lsof.standardError = FileHandle.nullDevice
        guard (try? lsof.run()) != nil else { return }
        lsof.waitUntilExit()
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        guard let text = String(data: data, encoding: .utf8) else { return }
        let pids = text.split(separator: "\n").compactMap { Int32($0.trimmingCharacters(in: .whitespaces)) }
        for pid in pids {
            kill(pid, SIGTERM)
        }
        if !pids.isEmpty {
            Thread.sleep(forTimeInterval: 0.3)
            for pid in pids where kill(pid, 0) == 0 {  // still alive
                kill(pid, SIGKILL)
            }
        }
    }

    private func stopOwnedProcess() {
        if let p = launchedProcess, p.isRunning {
            p.terminate()
            // Brief wait so the port is free before relaunch / killAnyProcessOnPort.
            Thread.sleep(forTimeInterval: 0.2)
            if p.isRunning { p.terminate() }
        }
        launchedProcess = nil
        launchedJgenEndpoint = nil
    }

    /// Called from AppDelegate's shutdown sequence -- the well-behaved
    /// half of the fix (killAnyProcessOnPort above is the fallback for
    /// when this never got the chance to run).
    func stop() {
        stopOwnedProcess()
        killAnyProcessOnPort(8765)
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

    private static func normalizedEndpoint(_ endpoint: String?) -> String? {
        guard let endpoint else { return nil }
        let trimmed = endpoint.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    struct AgentStepEvent: Sendable {
        let raw: [String: Any]
        var source: String? { raw["source"] as? String }
        var isTerminal: Bool { raw["final"] != nil }
    }

    /// Starts a run and streams every `on_step` event Vera-alpha's
    /// `Agent.run(task, on_step=...)` (N1) pushes, ending with the event
    /// that carries a `"final"` key. Callers typically feed `onEvent` into
    /// the same kind of `LoopEvent`-shaped UI update `ExecutionAgent`/
    /// `CouncilOrchestrator` already drive (see ModelSelectorBarView's
    /// harness toggle wiring).
    ///
    /// `backend` has **no** default — callers (AppState.runVeraHarness) must
    /// pick `"jgen"` or `"ollama"` from settings. A silent `"ollama"` default
    /// is what caused Connection refused to :11434 when Ollama was off /
    /// L2-JGEN was on.
    func runAgent(
        task: String, model: String = "", backend: String,
        cognitionMode: String = "normal",
        onEvent: @escaping (AgentStepEvent) -> Void
    ) async throws -> [String: Any] {
        let backend = backend.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard backend == "jgen" || backend == "ollama" else {
            throw ClientError.badResponse("backend must be \"jgen\" or \"ollama\", got \"\(backend)\"")
        }
        if backend == "jgen", launchedJgenEndpoint == nil {
            throw ClientError.badResponse(
                "backend \"jgen\" requires ensureServerRunning(jgenEndpoint:) first"
            )
        }
        // One auto-retry after a short re-ensure if the first POST fails
        // with a transport error (serve still warming / port race).
        do {
            return try await runAgentOnce(
                task: task, model: model, backend: backend,
                cognitionMode: cognitionMode, onEvent: onEvent
            )
        } catch let urlError as URLError where Self.isTransportFailure(urlError) {
            let ensure = await ensureServerRunning(jgenEndpoint: launchedJgenEndpoint)
            guard ensure.isReady else { throw ClientError.serverUnavailable(ensure) }
            return try await runAgentOnce(
                task: task, model: model, backend: backend,
                cognitionMode: cognitionMode, onEvent: onEvent
            )
        }
    }

    private func runAgentOnce(
        task: String, model: String, backend: String,
        cognitionMode: String,
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

    /// True when a URLError means loopback HTTP never answered (serve down /
    /// Ollama down / JGenAgentServer down) — not a semantic Vera answer.
    static func isTransportFailure(_ error: URLError) -> Bool {
        switch error.code {
        case .cannotConnectToHost, .networkConnectionLost, .timedOut,
             .cannotFindHost, .dnsLookupFailed, .notConnectedToInternet:
            return true
        default:
            return false
        }
    }

    /// Detects Vera LLM-step failures that are connectivity, not task
    /// content (Ollama :11434 refused, JGEN bridge refused, etc.).
    static func isLLMConnectivityFailure(_ message: String) -> Bool {
        let lower = message.lowercased()
        let markers = [
            "connection refused",
            "errno 61",
            "urlerror",
            "jgen_endpoint_error",
            "failed to connect",
            "could not connect",
            "nodename nor servname",
            "connection reset",
        ]
        return markers.contains { lower.contains($0) }
    }
}
