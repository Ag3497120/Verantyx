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

    /// Lazily launches `vera-memory ... serve` (same bundled binary
    /// Milestone H already embeds for MCP mode, see MCPEngine.swift's
    /// `bundledVeraMemory`/`VeraMemoryPaths`) if the daemon isn't already
    /// reachable. Idempotent WITHIN a running app instance -- a health
    /// check runs first so calling this repeatedly across chat turns
    /// doesn't spawn duplicate processes.
    ///
    /// Real bug found live: this used to trust ANY reachable server on
    /// the port, including one left over from a previous app run (Process
    /// objects don't die with their parent on macOS -- a normal quit that
    /// predates this fix, a force-quit, or a crash all leave `vera-memory
    /// serve` running forever). Every rebuild/redeploy of the binary was
    /// silently talking to that stale process instead of the new one,
    /// which is exactly why a real Python-side fix appeared to "do
    /// nothing" on retry. Now: if we don't already own a live
    /// `launchedProcess` from THIS app session, anything already on the
    /// port gets killed first, then a fresh process is always launched --
    /// covers the clean-quit case AND leftover orphans from before this
    /// fix existed, not just app-quit cleanup (see `stop()` below, which
    /// only helps the well-behaved-quit case).
    func ensureServerRunning() async {
        if let p = launchedProcess, p.isRunning, await isReachable() { return }

        killAnyProcessOnPort(8765)

        let bundled = VeraMemoryPaths.resolveBundledBinary()
        guard let bundled else { return }
        try? FileManager.default.createDirectory(at: VeraMemoryPaths.appSupportDir, withIntermediateDirectories: true)
        let storePath = VeraMemoryPaths.storeFile.path

        let process = Process()
        process.executableURL = bundled
        process.arguments = ["--store", storePath, "serve", "--port", "8765"]
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

    /// Called from AppDelegate's shutdown sequence -- the well-behaved
    /// half of the fix (killAnyProcessOnPort above is the fallback for
    /// when this never got the chance to run).
    func stop() {
        if let p = launchedProcess, p.isRunning {
            p.terminate()
        }
        launchedProcess = nil
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
