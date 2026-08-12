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
        let fromLoopback = Self.isLoopback(connection)

        // `/pipe/*` is the only surface a peer Mac may reach. Everything else
        // exposes this machine's own model to whoever asks.
        //
        // This gate is new and it closes a real hole rather than guarding a
        // hypothetical one: the listener has never had an interface filter, so
        // `/jgen/generate` was already reachable from the LAN by anyone who
        // guessed the port. The class comment called it "loopback-only", but
        // that was a convention, not an enforcement. Advertising the port over
        // Bonjour would have turned "guessed the port" into "was told the port",
        // so it is enforced now.
        if !fromLoopback && !request.path.hasPrefix("/pipe/") {
            await Self.writeResponse(connection: connection, status: 403,
                                     body: ["ok": false, "error": "local_only"])
            connection.cancel()
            return
        }

        // Model transfer routes carry query strings, which the exact-match
        // switch below cannot see past. Prefix-dispatch them first.
        if request.path.hasPrefix("/pipe/model/") {
            await handleModelRoute(request: request, connection: connection)
            connection.cancel()
            return
        }

        switch (request.method, request.path) {
        // GET is new: the server was POST-only, and a liveness probe that has to
        // POST cannot be issued by curl or a browser without ceremony.
        case ("GET", "/pipe/hello"):
            await handlePipeHello(connection: connection)
        case ("POST", "/pipe/pair"):
            await handlePipePair(request: request, connection: connection, fromLoopback: fromLoopback)
        case ("POST", "/pipe/unpair"):
            await handlePipeUnpair(request: request, connection: connection)
        case ("GET", "/pipe/models"), ("POST", "/pipe/models"):
            await handlePipeModels(connection: connection)
        case ("GET", "/pipe/state"), ("POST", "/pipe/state"):
            await handlePipeState(request: request, connection: connection)
        case ("POST", "/pipe/split"):
            await handlePipeSplit(request: request, connection: connection)

        case ("POST", "/mcp"):
            await handleMCP(request: request, connection: connection)

        case ("POST", "/jgen/generate"):
            await handleJGenGenerate(request: request, connection: connection)
        case ("POST", "/browser/fetch"):
            await handleBrowserFetch(request: request, connection: connection)
        case ("POST", "/jgen/inject_multi_layer"):
            await handleInjectMultiLayer(request: request, connection: connection)
        default:
            await Self.writeResponse(connection: connection, status: 404, body: ["ok": false, "error": "not_found"])
        }
        connection.cancel()
    }

    /// True when the peer address is 127.0.0.1 / ::1.
    ///
    /// Note this is *not* an authentication mechanism — anything on this Mac can
    /// reach loopback. It only separates "same machine" from "over the network",
    /// which is the distinction the endpoint split above needs.
    private static func isLoopback(_ connection: NWConnection) -> Bool {
        guard let remote = connection.currentPath?.remoteEndpoint ?? Optional(connection.endpoint) else {
            return false
        }
        if case let .hostPort(host, _) = remote {
            switch host {
            case .ipv4(let a): return a.isLoopback
            case .ipv6(let a): return a.isLoopback
            case .name(let n, _): return n == "localhost"
            @unknown default: return false
            }
        }
        return false
    }

    /// Milestone P: Vera's "reflection" tool (agent_tools.py's jgen_reflect)
    /// calls this to inject its own state (as short text labels, vectorized
    /// via JCrossChatManager.encodeText) into JGEN's hidden states at
    /// specific layers, and get back what JGEN's internal representation
    /// looks like afterward -- decoded to text, never a raw vector, matching
    /// Milestone L's "never pass JGEN's raw vectors to another process"
    /// principle.
    ///
    /// body: {"prompt": str, "interventions": [{"layer": int, "text_label": str, "alpha": float}], "observe_layers": [int]}
    private func handleInjectMultiLayer(request: ParsedRequest, connection: NWConnection) async {
        guard
            let data = request.body,
            let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let prompt = obj["prompt"] as? String,
            let observeLayersRaw = obj["observe_layers"] as? [Any]
        else {
            await Self.writeResponse(connection: connection, status: 400, body: ["ok": false, "error": "bad_request"])
            return
        }
        let observeLayers = Array(observeLayersRaw.compactMap { ($0 as? NSNumber)?.intValue }.prefix(8))
        guard !observeLayers.isEmpty else {
            await Self.writeResponse(connection: connection, status: 400, body: ["ok": false, "error": "empty_observe_layers"])
            return
        }
        let interventionsRaw = (obj["interventions"] as? [[String: Any]]) ?? []
        // Hard-cap intervention fan-out — each label is a full JGEN encode.
        let interventions: [(layer: Int, textLabel: String, alpha: Float)] = interventionsRaw.prefix(4).compactMap { d in
            guard let layer = (d["layer"] as? NSNumber)?.intValue,
                  let textLabel = d["text_label"] as? String else { return nil }
            let alpha = (d["alpha"] as? NSNumber)?.floatValue ?? 1.0
            return (layer, PromptBudget.truncateForEncode(textLabel), alpha)
        }

        guard await JCrossChatManager.shared.isLoaded else {
            await Self.writeResponse(connection: connection, status: 503, body: ["ok": false, "error": "jgen_not_loaded"])
            return
        }
        do {
            let observations = try await JCrossChatManager.shared.reflect(
                prompt: PromptBudget.truncateForModel(prompt),
                interventions: interventions,
                observeLayers: observeLayers
            )
            var observationsJSON: [String: Any] = [:]
            for (layer, obs) in observations {
                observationsJSON[String(layer)] = ["text": obs.text, "entropy": obs.entropy]
            }
            await JCrossChatManager.shared.trimMemory()
            await Self.writeResponse(connection: connection, status: 200, body: ["ok": true, "observations": observationsJSON])
        } catch {
            await Self.writeResponse(connection: connection, status: 500, body: ["ok": false, "error": "\(error)"])
        }
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
        // Real bug found live: this was a hardcoded 512, which silently
        // truncated Vera's forced-synthesis answer mid-sentence (and
        // mid-JSON) on a real "analyze this project" run -- the model
        // needs enough budget to both wrap its answer in the requested
        // {"thought":..., "final":...} JSON AND write a real summary,
        // especially in Japanese, which tokenizes less densely per
        // character than English. Raised the default and let a caller
        // (e.g. a longer forced-synthesis turn) ask for more — then
        // re-capped under JGenGPUSafety so tight Macs cannot OOM.
        let requestedMax = (obj["max_tokens"] as? Int) ?? 2048
        let maxTokens = JGenGPUSafety.cappedMaxTokens(requestedMax)

        guard await JCrossChatManager.shared.isLoaded else {
            await Self.writeResponse(connection: connection, status: 503, body: ["ok": false, "error": "jgen_not_loaded"])
            return
        }

        var conversation: [(role: String, content: String)] = []
        if let system, !system.isEmpty {
            conversation.append((role: "system", content: PromptBudget.truncateForModel(
                system, maxChars: PromptBudget.maxSystemChars
            )))
        }
        conversation.append((role: "user", content: PromptBudget.truncateForModel(prompt)))

        do {
            let text = try await JCrossChatManager.shared.generate(
                conversation: conversation, maxTokens: maxTokens,
                keepThinking: false)   // machine consumer: answer-only
            await JCrossChatManager.shared.trimMemory()
            await Self.writeResponse(connection: connection, status: 200, body: ["ok": true, "text": text])
        } catch {
            await Self.writeResponse(connection: connection, status: 500, body: ["ok": false, "error": "\(error)"])
        }
    }

    // MARK: - Distributed inference control plane (Milestone U4)
    //
    // Low-frequency JSON only: pairing, roles, model inventory, split ratio.
    // Per-token hidden states never come through here — one TCP handshake and a
    // JSON encode of 5120 floats per decode step would cost more than the layer
    // arithmetic. That traffic gets its own persistent binary channel (U5).

    /// Liveness plus everything a peer needs to decide whether pairing is even
    /// possible, so a version mismatch is reported before any state changes.
    ///
    /// Every `/pipe/*` handler reads `PipeStore` and never hops to the main
    /// actor. That is not a style choice: the first version did hop, and a
    /// permission dialog at launch parked the main thread in `[NSAlert runModal]`
    /// — connections were accepted and then answered with nothing until the
    /// client timed out. A peer must not be able to tell whether this Mac's user
    /// has a modal open.
    private func handlePipeHello(connection: NWConnection) async {
        let store = PipeStore.shared
        let v = store.localVersion()
        let s = store.snapshot()
        await Self.writeResponse(connection: connection, status: 200, body: [
            "ok": true,
            "protocol_version": v.protocolVersion,
            "app_version": v.appVersion,
            "engine_build": v.engineBuild,
            "device_id": store.localDeviceId,
            "device_name": store.deviceName,
            "ram_gb": store.ramGB,
            "free_disk_gb": PipeStore.freeDiskGB(),
            "role": s.role.rawValue,
            "paired": s.isPaired,
            "peer_name": s.peer?.deviceName ?? "",
        ])
    }

    /// The caller declares itself master; this Mac answers with the role it took.
    /// Deliberately the only way a role is ever assigned — nothing infers one
    /// from a Bonjour record.
    private func handlePipePair(request: ParsedRequest, connection: NWConnection, fromLoopback: Bool) async {
        guard let body = request.body,
              let json = try? JSONSerialization.jsonObject(with: body) as? [String: Any],
              let incomingSession = json["session_id"] as? String,
              let deviceId = json["device_id"] as? String
        else {
            await Self.writeResponse(connection: connection, status: 400,
                                     body: ["ok": false, "error": "bad_request"])
            return
        }
        let store = PipeStore.shared
        let remote = PipeStore.PeerInfo(
            deviceId: deviceId,
            deviceName: json["device_name"] as? String ?? "Mac",
            appVersion: json["app_version"] as? String ?? "?",
            engineBuild: json["engine_build"] as? String ?? "?",
            protocolVersion: json["protocol_version"] as? Int ?? 0,
            ramGB: json["ram_gb"] as? Int ?? 0,
            freeDiskGB: json["free_disk_gb"] as? Double ?? 0,
            host: json["host"] as? String ?? (fromLoopback ? "127.0.0.1" : ""),
            controlPort: UInt16(json["control_port"] as? Int ?? 0)
        )

        switch store.acceptPairing(from: remote, sessionId: incomingSession, local: store.localVersion()) {
        case .accepted(let role):
            await Self.writeResponse(connection: connection, status: 200, body: [
                "ok": true,
                "role": role.rawValue,
                "device_id": store.localDeviceId,
                "device_name": store.deviceName,
                "ram_gb": store.ramGB,
                "free_disk_gb": PipeStore.freeDiskGB(),
                "models": Self.encode(store.localModels()),
            ])
        case .tiebreakWon(let reason):
            // Not a failure: the asker becomes worker instead. Kept distinct from
            // a refusal so the UI can name the winner rather than just reporting
            // that something went wrong.
            await Self.writeResponse(connection: connection, status: 409, body: [
                "ok": false, "error": "tiebreak_lost", "reason": reason,
                "winner_device_id": store.localDeviceId,
            ])
        case .rejected(let reason):
            await Self.writeResponse(connection: connection, status: 403,
                                     body: ["ok": false, "error": "rejected", "reason": reason])
        }
    }

    private func handlePipeUnpair(request: ParsedRequest, connection: NWConnection) async {
        PipeStore.shared.unpair()
        await Self.writeResponse(connection: connection, status: 200, body: ["ok": true])
    }

    private func handlePipeModels(connection: NWConnection) async {
        await Self.writeResponse(connection: connection, status: 200,
                                 body: ["ok": true, "models": Self.encode(PipeStore.shared.localModels())])
    }

    /// GET reports the resolved split; POST accepts one pushed by the master.
    private func handlePipeState(request: ParsedRequest, connection: NWConnection) async {
        if request.method == "POST", let body = request.body,
           let json = try? JSONSerialization.jsonObject(with: body) as? [String: Any] {
            let mode = PipeStore.SplitMode(rawValue: json["mode"] as? String ?? "auto") ?? .auto
            PipeStore.shared.applyRemoteState(mode: mode, k: json["k"] as? Int ?? 0)
        }
        let s = PipeStore.shared.snapshot()
        await Self.writeResponse(connection: connection, status: 200, body: [
            "ok": true, "role": s.role.rawValue, "session_id": s.sessionId,
            "mode": s.splitMode.rawValue, "k": s.splitK,
            "peer_name": s.peer?.deviceName ?? "",
        ])
    }

    /// A worker asking the master to change the split. The master is the only
    /// writer, so this is a request, not an assignment.
    private func handlePipeSplit(request: ParsedRequest, connection: NWConnection) async {
        guard let body = request.body,
              let json = try? JSONSerialization.jsonObject(with: body) as? [String: Any],
              let k = json["k"] as? Int
        else {
            await Self.writeResponse(connection: connection, status: 400,
                                     body: ["ok": false, "error": "bad_request"])
            return
        }
        let mode = PipeStore.SplitMode(rawValue: json["mode"] as? String ?? "manual") ?? .manual
        guard PipeStore.shared.setSplit(mode: mode, k: k) else {
            await Self.writeResponse(connection: connection, status: 409, body: [
                "ok": false, "error": "not_master", "reason": "Only the Master resolves the split.",
            ])
            return
        }
        let s = PipeStore.shared.snapshot()
        await Self.writeResponse(connection: connection, status: 200,
                                 body: ["ok": true, "mode": s.splitMode.rawValue, "k": s.splitK])
    }

    private static func encode(_ models: [PipeStore.ModelEntry]) -> [[String: Any]] {
        models.map { m in
            var d: [String: Any] = [
                "name": m.name,
                // As a string so no JSON parser can hand it back as a Double.
                // Belt-and-braces rather than a fix for an observed problem: the
                // sizes here (tens of GB, ~6e10) are five orders of magnitude
                // below 2^53, so a Double would represent them exactly anyway.
                "size_bytes": String(m.sizeBytes),
                "structural_hash": m.structuralHash,
                "meta_hash": m.metaHash,
                "arch_supported": m.archSupported,
            ]
            if let c = m.contentHash { d["content_hash"] = c }
            if let k = m.contentHashKind { d["content_hash_kind"] = k }
            return d
        }
    }

    // MARK: - Model transfer (in-app, receiver pulls)
    //
    // The shape ModelTransfer's doc promised but nothing implemented: the
    // control plane negotiates over JSON, and the weights go out as a raw
    // streamed response that never exists in memory as one Data. Three routes:
    //
    //   GET  /pipe/model/manifest?name=X          sender: files + sizes + hashes
    //   GET  /pipe/model/file?name=X&rel=R&off=N  sender: raw bytes from offset
    //   POST /pipe/model/pull {name, host, port}  receiver: start pulling from
    //                                             the named sender ("send" on
    //                                             the UI is really "please pull
    //                                             from me" — the receiver knows
    //                                             its own free space and resume
    //                                             offsets, the sender does not)
    //   GET  /pipe/model/pull_status              receiver: progress, so the
    //                                             Mac whose button was pressed
    //                                             can show a real bar

    private func handleModelRoute(request: ParsedRequest, connection: NWConnection) async {
        guard let comps = URLComponents(string: "http://x\(request.path)") else {
            await Self.writeResponse(connection: connection, status: 400,
                                     body: ["ok": false, "error": "bad_path"])
            return
        }
        let q: [String: String] = (comps.queryItems ?? []).reduce(into: [:]) { $0[$1.name] = $1.value }

        // Weights only move inside an established pairing. Every /pipe/model
        // route (except the progress readout, which carries no model data)
        // must present the session id both machines agreed on in /pipe/pair —
        // without this, anything on the LAN that guessed a model's name could
        // download it. The id is a bearer secret shared over the local link;
        // for a paired two-Mac setup that is the right size of lock.
        if comps.path != "/pipe/model/pull_status" {
            let sid = PipeStore.shared.snapshot().sessionId
            let presented = q["sid"]
                ?? (request.body.flatMap {
                    (try? JSONSerialization.jsonObject(with: $0) as? [String: Any])
                        .flatMap { $0?["sid"] as? String }
                })
            guard !sid.isEmpty, presented == sid else {
                await Self.writeResponse(connection: connection, status: 403,
                                         body: ["ok": false, "error": "not_paired"])
                return
            }
        }

        switch (request.method, comps.path) {
        case ("GET", "/pipe/model/manifest"):
            guard let name = q["name"], !name.contains("/"),
                  let manifest = try? ModelTransfer.buildManifest(for: name),
                  let data = try? JSONEncoder().encode(manifest),
                  let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
            else {
                await Self.writeResponse(connection: connection, status: 404,
                                         body: ["ok": false, "error": "no_such_model"])
                return
            }
            await Self.writeResponse(connection: connection, status: 200,
                                     body: ["ok": true, "manifest": obj])

        case ("GET", "/pipe/model/file"):
            guard let name = q["name"], !name.contains("/"),
                  let rel = q["rel"], !rel.contains("..") else {
                await Self.writeResponse(connection: connection, status: 400,
                                         body: ["ok": false, "error": "bad_request"])
                return
            }
            let url = ModelTransfer.sourceURL(name: name, relPath: rel)
            let offset = UInt64(q["off"] ?? "0") ?? 0
            await Self.writeFileResponse(connection: connection, url: url, offset: offset)

        case ("POST", "/pipe/model/pull"):
            guard let body = request.body,
                  let json = try? JSONSerialization.jsonObject(with: body) as? [String: Any],
                  let name = json["name"] as? String, !name.contains("/"),
                  let host = json["host"] as? String,
                  let port = (json["port"] as? Int).map({ UInt16($0) }) ?? nil
            else {
                await Self.writeResponse(connection: connection, status: 400,
                                         body: ["ok": false, "error": "bad_request"])
                return
            }
            let started = await MainActor.run { TransferProgress.shared.beginIfIdle(name: name) }
            guard started else {
                await Self.writeResponse(connection: connection, status: 409,
                                         body: ["ok": false, "error": "transfer_in_progress"])
                return
            }
            Task.detached(priority: .utility) {
                await ModelTransfer.shared.pull(name: name, host: host, port: port)
            }
            await Self.writeResponse(connection: connection, status: 200, body: ["ok": true])

        case ("GET", "/pipe/model/pull_status"):
            let st = await MainActor.run { TransferProgress.shared.snapshot() }
            await Self.writeResponse(connection: connection, status: 200, body: st)

        default:
            await Self.writeResponse(connection: connection, status: 404,
                                     body: ["ok": false, "error": "not_found"])
        }
    }

    /// Streams a file as an HTTP response in 4 MB reads. This exists because
    /// `writeResponse` (and `readRequest` on the other side) hold the whole
    /// body in one Data — fine for JSON, memory-fatal for 16 GB of weights.
    private static func writeFileResponse(connection: NWConnection, url: URL, offset: UInt64) async {
        guard let fh = try? FileHandle(forReadingFrom: url),
              let total = try? FileManager.default.attributesOfItem(atPath: url.path)[.size] as? UInt64,
              offset <= total
        else {
            await writeResponse(connection: connection, status: 404,
                                body: ["ok": false, "error": "no_such_file"])
            return
        }
        defer { try? fh.close() }
        try? fh.seek(toOffset: offset)
        let remaining = total - offset

        let header = "HTTP/1.1 200 OK\r\n"
            + "Content-Type: application/octet-stream\r\n"
            + "Content-Length: \(remaining)\r\n"
            + "Connection: close\r\n\r\n"
        let sentHeader: Bool = await withCheckedContinuation { cont in
            connection.send(content: Data(header.utf8), completion: .contentProcessed { err in
                cont.resume(returning: err == nil)
            })
        }
        guard sentHeader else { return }

        var left = remaining
        while left > 0 {
            let chunkLen = Int(min(left, 4 << 20))
            guard let chunk = try? fh.read(upToCount: chunkLen), !chunk.isEmpty else { return }
            let ok: Bool = await withCheckedContinuation { cont in
                connection.send(content: chunk, completion: .contentProcessed { err in
                    cont.resume(returning: err == nil)
                })
            }
            guard ok else { return }   // receiver went away; it can resume later
            left -= UInt64(chunk.count)
        }
    }

    // MARK: - MCP over HTTP (the memory organ as tools)
    //
    // POST /mcp speaks JSON-RPC per the MCP streamable-HTTP transport, so
    // external agents (OpenCode, Claude Code, Cursor) can use THIS Mac's
    // pinned small JGEN as their memory organ — the dual setup "chat with
    // anything, remember with one JGEN" turned into a protocol.
    //
    // Deliberately text-in/text-out only (Milestone L: JGEN's raw vectors
    // never leave the process): `eternal_recall` returns remembered TEXTS,
    // `eternal_remember` accepts text. The embed_model pin inside
    // EternalMemoryStore still governs — with the wrong JGEN loaded these
    // tools answer with the pin notice instead of mixing spaces. Loopback
    // gate applies (the /mcp path is not under /pipe/).
    private func handleMCP(request: ParsedRequest, connection: NWConnection) async {
        guard let body = request.body,
              let obj = try? JSONSerialization.jsonObject(with: body) as? [String: Any] else {
            await Self.writeResponse(connection: connection, status: 400,
                                     body: ["ok": false, "error": "bad_json"])
            return
        }
        let method = (obj["method"] as? String) ?? ""
        let id = obj["id"]   // Int or String; absent for notifications

        func reply(result: [String: Any]) async {
            var out: [String: Any] = ["jsonrpc": "2.0", "result": result]
            if let id { out["id"] = id }
            await Self.writeResponse(connection: connection, status: 200, body: out)
        }
        func replyError(_ code: Int, _ message: String) async {
            var out: [String: Any] = ["jsonrpc": "2.0",
                                      "error": ["code": code, "message": message]]
            if let id { out["id"] = id }
            await Self.writeResponse(connection: connection, status: 200, body: out)
        }

        switch method {
        case "initialize":
            let requested = ((obj["params"] as? [String: Any])?["protocolVersion"] as? String)
                ?? "2024-11-05"
            await reply(result: [
                "protocolVersion": requested,
                "capabilities": ["tools": [String: Any]()],
                "serverInfo": ["name": "verantyx-jgen-memory", "version": "1.0.0"],
            ])

        case "notifications/initialized", "notifications/cancelled":
            // Notifications carry no id and expect no JSON-RPC reply.
            await Self.writeResponse(connection: connection, status: 202, body: [:])

        case "ping":
            await reply(result: [:])

        case "tools/list":
            await reply(result: ["tools": [
                [
                    "name": "eternal_recall",
                    "description": "Recall from this Mac's eternal memory (3 years of "
                        + "JGEN hidden-state experience, gravity-ordered). Returns the "
                        + "remembered texts with similarity scores.",
                    "inputSchema": [
                        "type": "object",
                        "properties": [
                            "query": ["type": "string"],
                            "k": ["type": "integer", "description": "top-K, default 3"],
                        ],
                        "required": ["query"],
                    ],
                ],
                [
                    "name": "eternal_remember",
                    "description": "Store one text into eternal memory through the pinned "
                        + "memory-organ JGEN. Subject to the same governance as IDE-side "
                        + "writes (vera core tags, quarantine).",
                    "inputSchema": [
                        "type": "object",
                        "properties": ["text": ["type": "string"]],
                        "required": ["text"],
                    ],
                ],
            ]])

        case "tools/call":
            let params = (obj["params"] as? [String: Any]) ?? [:]
            let name = (params["name"] as? String) ?? ""
            let args = (params["arguments"] as? [String: Any]) ?? [:]
            func toolText(_ text: String, isError: Bool = false) async {
                await reply(result: [
                    "content": [["type": "text", "text": text]],
                    "isError": isError,
                ])
            }
            guard await JCrossChatManager.shared.isLoaded else {
                await toolText("No JGEN model is loaded in Verantyx — the memory organ "
                               + "is offline. Load the pinned model in the IDE first.",
                               isError: true)
                return
            }
            switch name {
            case "eternal_recall":
                let query = (args["query"] as? String) ?? ""
                let k = (args["k"] as? Int) ?? 3
                guard !query.isEmpty else { await toolText("query is required", isError: true); return }
                let hits = (try? await EternalMemoryStore.shared.search(
                    query: query, k: max(1, min(k, 10)))) ?? []
                if hits.isEmpty {
                    await toolText("(no eternal memory matched — possibly the pinned "
                                   + "memory model is not the one loaded)")
                } else {
                    let lines = hits.map {
                        String(format: "[%.2f] %@", $0.score, $0.text)
                    }.joined(separator: "\n")
                    await toolText(lines)
                }
            case "eternal_remember":
                let text = (args["text"] as? String) ?? ""
                guard !text.isEmpty else { await toolText("text is required", isError: true); return }
                do {
                    try await EternalMemoryStore.shared.add(text: text, concepts: [])
                    await toolText("remembered")
                } catch {
                    await toolText("store refused: \(error.localizedDescription)", isError: true)
                }
            default:
                await replyError(-32602, "unknown tool: \(name)")
            }

        default:
            await replyError(-32601, "method not supported: \(method)")
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
