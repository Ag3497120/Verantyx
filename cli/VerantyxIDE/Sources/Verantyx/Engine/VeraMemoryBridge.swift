import Foundation

/// The Vera model's own engine process — NATIVE, owned by the mode.
///
/// The MCP registry route died three different deaths in one evening
/// (a sanitizer rewriting the command, a dev build without the embed
/// phase, a stale vendored binary), and every death silenced every
/// Vera door at once. This actor removes the registry from the path:
/// it spawns the bundled `vera-memory` engine directly, speaks the
/// same stdio JSON-RPC, and owns the process lifecycle. Switching
/// models (VERA_PUBLISHED_DB) IS a process restart here — never a
/// silent reload — and the picker's semantics become literal.
actor VeraModelProcess {
    static let shared = VeraModelProcess()

    private var process: Process?
    private var stdinPipe: Pipe?
    private var stdoutPipe: Pipe?
    private var buffer = Data()
    private var nextId = 10
    /// Absolute path of the pinned release db; "" = the engine default.
    private(set) var pinnedDB: String = ""

    /// Kill and relaunch pinned to a release db (or the default when
    /// nil). The next call relaunches lazily.
    func switchModel(dbPath: String?) {
        pinnedDB = dbPath ?? ""
        terminate()
    }

    func terminate() {
        process?.terminate()
        process = nil
        stdinPipe = nil
        stdoutPipe = nil
        buffer.removeAll()
    }

    private func ensureRunning() -> Bool {
        if let p = process, p.isRunning { return true }
        guard let binary = VeraMemoryPaths.resolveBundledBinary() else {
            return false
        }
        let p = Process()
        p.executableURL = binary
        p.arguments = ["--store", VeraMemoryPaths.storeFile.path, "mcp"]
        var env = ProcessInfo.processInfo.environment
        if !pinnedDB.isEmpty { env["VERA_PUBLISHED_DB"] = pinnedDB }
        p.environment = env
        let inPipe = Pipe(); let outPipe = Pipe()
        p.standardInput = inPipe
        p.standardOutput = outPipe
        p.standardError = FileHandle.nullDevice
        do { try p.run() } catch { return false }
        process = p; stdinPipe = inPipe; stdoutPipe = outPipe
        buffer.removeAll()
        // MCP handshake: initialize, then the initialized notification.
        _ = requestSync(method: "initialize", params: [
            "protocolVersion": "2024-11-05", "capabilities": [:],
            "clientInfo": ["name": "verantyx-ide-native", "version": "1"],
        ], timeout: 30)
        send(["jsonrpc": "2.0",
              "method": "notifications/initialized", "params": [:]])
        return true
    }

    /// Call a tool; returns the parsed JSON object from its text
    /// content, or nil (engine missing, tool missing, timeout).
    func call(_ tool: String, _ args: [String: Any],
              timeout: TimeInterval = 90) -> [String: Any]? {
        guard ensureRunning() else { return nil }
        guard let resp = requestSync(
            method: "tools/call",
            params: ["name": tool, "arguments": args],
            timeout: timeout)
        else { return nil }
        // result.content[0].text carries the tool's JSON string.
        guard let result = resp["result"] as? [String: Any],
              let content = result["content"] as? [[String: Any]],
              let text = content.first?["text"] as? String,
              let data = text.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data)
                as? [String: Any]
        else { return nil }
        return obj
    }

    private func send(_ obj: [String: Any]) {
        guard let data = try? JSONSerialization.data(withJSONObject: obj),
              let stdin = stdinPipe
        else { return }
        stdin.fileHandleForWriting.write(data)
        stdin.fileHandleForWriting.write(Data([0x0A]))
    }

    private func requestSync(
        method: String, params: [String: Any], timeout: TimeInterval
    ) -> [String: Any]? {
        nextId += 1
        let id = nextId
        send(["jsonrpc": "2.0", "id": id,
              "method": method, "params": params])
        guard let out = stdoutPipe else { return nil }
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            // Scan buffered lines for our id; availableData blocks only
            // while the engine is quiet, and the engine answers in order.
            while let nl = buffer.firstIndex(of: 0x0A) {
                let line = buffer.subdata(in: buffer.startIndex..<nl)
                buffer.removeSubrange(buffer.startIndex...nl)
                guard let obj = try? JSONSerialization.jsonObject(with: line)
                        as? [String: Any] else { continue }
                if (obj["id"] as? Int) == id { return obj }
            }
            let chunk = out.fileHandleForReading.availableData
            if chunk.isEmpty {  // engine exited
                terminate()
                return nil
            }
            buffer.append(chunk)
        }
        return nil
    }
}

// MARK: - VeraMemoryBridge
//
// Bridges the "Vera-α" `JCrossLayer` option to Vera's own deterministic,
// typed-verdict knowledge store, run as its own MCP server ("vera-memory",
// auto-registered in `MCPEngine.loadServers()` — `python3.11 -m
// verantyx.cli mcp` against the Verantyx-Vera-alpha checkout).
//
// Deliberately NOT wired through CortexEngine or SessionMemoryArchiver's
// existing l1/l1.5/l2/l3 machinery — those read/write .jcross node files;
// Vera reads/writes its own store instead. Selecting "Vera-α" as a
// session's `activeLayer` routes memory through here at the exact call
// sites in `AgentLoop.run()` that would otherwise call
// `SessionMemoryArchiver.semanticSearch(layer:)` — same position as
// l1/l1.5/l2/l3, mutually exclusive per session, never both at once. This
// is also why it's opt-in per session rather than always-on: an earlier
// pass wired Vera into CortexEngine's always-called `buildMemoryPrompt`/
// `extractAndStore`, which paid the MCP round-trip cost on every single
// turn in every mode — reverted in favor of this, which only runs for
// sessions that actually selected the Vera-α layer.
//
// Saving is unconditional application code that runs regardless of what
// the model does — not an LLM tool-call the model has to decide to make.
// A forced system-prompt instruction ("please remember this") is
// unreliable, especially for small local models, which is exactly why
// this exists instead of just exposing Vera's MCP tools to the model's
// own tool-calling loop and hoping it calls them.
@MainActor
enum VeraMemoryBridge {

    private static let serverName = "vera-memory"

    /// Called once per completed turn (after the AI's response is ready).
    /// Shows a preview popup — `VeraSaveApprovalView`, fed by
    /// `AppState.pendingVeraSave`/`pendingVeraSaveQueue` — and only calls
    /// Vera at all if the human taps "Save". This is still application
    /// code, not an LLM-decided tool call. On "Save": the user's prompt
    /// goes straight into Vera's trusted store (`remember`); the AI's
    /// response goes through Vera's AI-output quarantine
    /// (`propose_ai_facts`) — never auto-promoted, still needs a later,
    /// separate human accept/reject via `vera review-ai-facts`. This
    /// popup is only the "queue it at all" gate, not that final review
    /// step.
    ///
    /// Behavior depends on `AppState.veraSaveApprovalMode`:
    ///   .perTurn (default) — blocks this turn until the human decides,
    ///     exactly like the original implementation.
    ///   .batched — enqueues and returns immediately; the agent loop
    ///     keeps running uninterrupted, and the actual Vera calls happen
    ///     later in the background once the human reviews the queue.
    ///     Chosen for long, largely-unattended runs (e.g. a multi-file
    ///     rewrite) where blocking on a popup every turn would otherwise
    ///     stall the whole task at turn 1 until someone notices and clicks.
    static func requestSaveApproval(userPrompt: String, aiResponse: String) async {
        // Vera-a mode prepends injected background ([VERIFIED MEMORY] /
        // [ETERNAL MEMORY] / [WEB EVIDENCE]) with a "[TASK]" marker before
        // the user's real words. Only the real words are the memory — a
        // real run saved the whole injection block and even forged a skill
        // named after it.
        var stripped = userPrompt
        if let r = stripped.range(of: "[TASK]\n", options: .backwards) {
            stripped = String(stripped[r.upperBound...])
        }
        let prompt = stripped.trimmingCharacters(in: .whitespacesAndNewlines)

        // Control/meta output is not memory. A real run saved
        // "[内部知識の評価]: No … [アクション]: [SEARCH]" three times and
        // minted skills named 検索を行なって and search from it — plumbing
        // must never reach the store, with or without approval.
        let metaMarkers = ["[内部知識の評価]", "[アクション]", "[SEARCH",
                           "SEARCH_GATE", "[MEM:", "[CTRL"]
        if metaMarkers.contains(where: { aiResponse.contains($0) }) { return }

        // A transport failure is not an utterance. "claude CLI: API Error: 529
        // Overloaded." is the CLI reporting that the request never reached a
        // model: there is no claim in it to ground, nothing about the world to
        // remember, and no reviewer should be asked to approve it. Sending it
        // through the annotator also mangled the one part the user needed —
        // the status URL came back as "https://status.（未検証）claude.com".
        //
        // Same category error as the stray-tag detector firing on [AX_ERROR]:
        // tool and transport output is machinery reporting on itself, and the
        // discipline that applies to model prose does not apply to it.
        let transportMarkers = ["API Error:", "claude CLI:", "[AX_ERROR]",
                                "Model returned nil", "が終了コード"]
        if aiResponse.hasPrefix("⚠️")
            || transportMarkers.contains(where: { aiResponse.contains($0) }) { return }
        // A bare command with no content ("検索を行なって", "SEARCH") is an
        // instruction to the agent, not a fact about the world.
        if prompt.count <= 12,
           prompt.lowercased().contains("search") || prompt.contains("検索") { return }
        var response = aiResponse.trimmingCharacters(in: .whitespacesAndNewlines)

        // ── Separate facts by origin before any of them can be stored ──
        // The AI half of a turn mixes claims this turn actually grounded
        // with claims recited from training data — a real run received
        // fresh evidence about Claude and still wrote "100K tokens".
        // ClaimGrounding classifies each sentence against the sources the
        // turn carried (and Vera's own store) and only the backed ones go
        // on to `propose_ai_facts`; the rest are reported, not stored.
        if !response.isEmpty {
            let sources = ClaimGrounding.sources(fromInjectedPrompt: userPrompt)
            let classified = await ClaimGrounding.classify(reply: response, sources: sources)
            let summary = ClaimGrounding.summary(
                classified, japanese: AppLanguage.shared.isJapanese)
            if !summary.isEmpty {
                await MainActor.run {
                    AppState.shared?.addSystemMessage("<think>\n🧾 " + summary + "\n</think>")
                }
            }

            // The AI half of the dialog was empty on every ordinary turn, and
            // the cause is a category error rather than a formatting one.
            //
            // An ordinary chat turn injects no web block and no recall block,
            // so `sources` is empty — and with nothing to check against,
            // NOTHING can be grounded. The reply was then dropped as
            // ungrounded, so the queue the human is asked to review was always
            // empty. An absence of sources was being read as evidence of
            // fabrication, which is the one inference vera-a's own discipline
            // forbids: UNKNOWN_NO_EVIDENCE is not a negative answer.
            //
            // And the drop was redundant besides. propose_ai_facts IS the
            // quarantine — it queues without trusting. Filtering before it
            // does the quarantine's job twice and leaves nothing to approve.
            if sources.isEmpty {
                // Nothing to check against. Keep the text, labelled honestly,
                // and let the human be the check — which is the entire reason
                // this dialog exists.
                response = "（このターンには照合できる出典がありませんでした — 未検証）\n" + response
            } else {
                let grounded = ClaimGrounding.groundedText(from: classified)
                let annotated = ClaimGrounding.annotated(response, results: classified)
                // Ungrounded sentences still reach quarantine, marked. A
                // reviewer cannot approve what they were never shown.
                response = grounded.isEmpty ? annotated : grounded
            }
        }

        guard !prompt.isEmpty || !response.isEmpty else { return }

        let req = VeraSaveApprovalRequest(userPrompt: prompt, aiResponse: response)
        let mode = AppState.shared?.veraSaveApprovalMode ?? .perTurn
        AppState.shared?.enqueueVeraSave(req)

        switch mode {
        case .perTurn:
            guard await req.waitForDecision() else { return }
            await performSave(req)
        case .batched:
            Task {
                guard await req.waitForDecision() else { return }
                await performSave(req)
            }
        }
    }

    private static func performSave(_ req: VeraSaveApprovalRequest) async {
        // A claim travelling to memory takes the same road: the cross
        // reads 記憶へ while it lands, then goes still. Nothing is
        // inserted into memory from the side of the picture.
        await MainActor.run { VeraRouteState.shared.stored() }
        // Collect the REAL core keys the store actually saved under (as
        // returned by `remember`/`record_code_change`), not a guess derived
        // from the raw prompt text -- graph_snapshot ranks cores by pour
        // count, so a just-taught fact (count 1) would otherwise never
        // appear in a store with thousands of long-accumulated cores ahead
        // of it. These keys are passed as `focus_cores` so the new node is
        // guaranteed to be in the next snapshot the graph view fetches.
        var newCoreKeys: [String] = []

        if !req.userPrompt.isEmpty {
            let raw = await MCPEngine.shared.callTool(
                serverName: serverName, toolName: "remember",
                arguments: ["sentence": String(req.userPrompt.prefix(500))],
                mode: .human
            )
            if let data = raw.data(using: .utf8),
               let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let key = obj["remembered"] as? String, !key.isEmpty {
                newCoreKeys.append(key)
            }
        }
        if !req.aiResponse.isEmpty {
            _ = await MCPEngine.shared.callTool(
                serverName: serverName, toolName: "propose_ai_facts",
                arguments: ["text": req.aiResponse, "source": "verantyx_ide_vera_layer"],
                mode: .human
            )
        }

        // Code changes go through `record_code_change`, NOT
        // `propose_ai_facts` — see extractCodeChanges' doc comment for why
        // (its sentence-splitter mangles diff/patch syntax).
        for change in extractCodeChanges(from: req.aiResponse) {
            let raw = await MCPEngine.shared.callTool(
                serverName: serverName, toolName: "record_code_change",
                arguments: ["file_path": change.file, "description": change.description],
                mode: .human
            )
            if let data = raw.data(using: .utf8),
               let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let key = obj["recorded"] as? String, !key.isEmpty {
                newCoreKeys.append(key)
            }
        }

        // ── vera-a governs the vector space (mechanisms 1–4) ──────────
        // The approved save is the moment vera-a's symbolic structure
        // reaches into eternal memory: the ask verdict tags recent nodes
        // with their core (cluster seed) and quarantines contradictions;
        // older same-core nodes cool so the fresh fact outranks them; and
        // the approval itself becomes a supervision pair — the
        // model-independent ground truth a retrieval projector can be
        // (re)trained from after any model swap.
        if let primaryCore = newCoreKeys.first, !req.userPrompt.isEmpty {
            let askRaw = await MCPEngine.shared.callTool(
                serverName: serverName, toolName: "ask",
                arguments: ["query": String(req.userPrompt.prefix(300))],
                mode: .human
            )
            var verdict = "ANSWER"
            var contradiction = 0
            if let data = askRaw.data(using: .utf8),
               let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                verdict = (obj["verdict"] as? String) ?? verdict
                contradiction = (obj["contradiction"] as? Int) ?? 0
            }
            let store = EternalMemoryStore.shared
            await store.applyVeraJudgment(
                promptPrefix: req.userPrompt, core: primaryCore,
                verdict: verdict, contradiction: contradiction)
            await store.coolCore(primaryCore, before: Date().timeIntervalSince1970)
            await store.recordSupervisionPair(
                kind: "approved", textA: req.userPrompt,
                textB: req.aiResponse.isEmpty ? req.userPrompt : req.aiResponse,
                core: primaryCore)
            if contradiction > 0 {
                await MainActor.run {
                    AppState.shared?.addSystemMessage(L(
                        "🧿 Vera reported a contradiction — related eternal memories quarantined pending review.",
                        "🧿 Veraが矛盾を検知 — 関連する永遠記憶を検疫し、レビュー待ちにしました。"))
                }
            }
        }

        // If the stereo-cross 3D graph demo is active, trigger its
        // "connection" animation for this save instead of (or in addition
        // to) the ordinary system message -- StereoCrossGraphView observes
        // this and clears it back to nil once the animation plays.
        if AppState.shared?.showStereoCrossGraph == true {
            let label = !req.userPrompt.isEmpty ? req.userPrompt : req.aiResponse
            AppState.shared?.pendingGraphFocusCores = newCoreKeys
            AppState.shared?.pendingGraphConnection = String(label.prefix(60))
        }
    }

    /// Fire-and-forget archival of a compression pass's L2 facts into Vera's
    /// verified store, so they persist beyond this session too -- this is a
    /// system-triggered background write (like CortexEngine's own
    /// `remember`), not a user-authored save, so it bypasses the
    /// save-approval popup entirely. Coexists with, rather than replaces,
    /// the inline OP.FACT L2 summary and JCross front-zone archive:
    /// short-lived in-context facts stay in the rolling compression
    /// summary; this just also gives them a verified, cross-session home.
    static func archiveCompressionFacts(task: String, modifiedFiles: [String], userIntents: [String], lastResponse: String) {
        var sentences: [String] = []
        if !task.isEmpty {
            sentences.append("Worked on task: \(task).")
        }
        for file in modifiedFiles {
            sentences.append("Modified file \(file).")
        }
        for intent in userIntents {
            sentences.append("User asked for: \(intent).")
        }
        if !lastResponse.isEmpty {
            sentences.append("Last response summary: \(lastResponse).")
        }
        guard !sentences.isEmpty else { return }

        Task {
            for sentence in sentences {
                _ = await MCPEngine.shared.callTool(
                    serverName: serverName, toolName: "remember",
                    arguments: ["sentence": String(sentence.prefix(500))],
                    mode: .human
                )
            }
        }
    }

    /// Best-effort single-sentence teach into Vera CrossStore — used by
    /// `EternalVeraBridge` for short Act/forge facts. Never shows the
    /// save-approval popup; Act must not fail if MCP is down.
    static func rememberShortFact(_ sentence: String) {
        let clipped = sentence.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clipped.isEmpty else { return }
        Task {
            _ = await MCPEngine.shared.callTool(
                serverName: serverName, toolName: "remember",
                arguments: ["sentence": String(clipped.prefix(500))],
                mode: .human
            )
        }
    }

    // MARK: - Verified URL registry

    /// Registers a human- or agent-confirmed URL for a named destination
    /// (e.g. name: "Gemini", url: "https://gemini.google.com/") via the
    /// `record_verified_url` MCP tool -- stored as a direct facet, not run
    /// through `remember`'s sentence-splitting quarantine (a URL's periods
    /// would get mangled the same way diffs do). Pairs with
    /// `lookupVerifiedURL`, which reads it back deterministically.
    @discardableResult
    static func recordVerifiedURL(name: String, url: String) async -> Bool {
        let trimmedName = name.trimmingCharacters(in: .whitespacesAndNewlines)
        let trimmedURL = url.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedName.isEmpty, !trimmedURL.isEmpty else { return false }
        let raw = await MCPEngine.shared.callTool(
            serverName: serverName, toolName: "record_verified_url",
            arguments: ["name": trimmedName, "url": trimmedURL],
            mode: .human
        )
        guard let data = raw.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return false }
        return obj["recorded"] != nil
    }

    /// Deterministic lookup for a URL registered via `recordVerifiedURL` --
    /// bypasses `ask`'s consensus/agreement threshold entirely (a single
    /// registration is enough), unlike the stricter `[VERA MEMORY]`
    /// section `recall(for:)` builds. Returns nil if nothing's registered
    /// under that name.
    static func lookupVerifiedURL(name: String) async -> String? {
        let trimmedName = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedName.isEmpty else { return nil }
        let raw = await MCPEngine.shared.callTool(
            serverName: serverName, toolName: "lookup_verified_url",
            arguments: ["name": trimmedName],
            mode: .human
        )
        guard let data = raw.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              obj["verdict"] as? String == "ANSWER" else { return nil }
        guard let url = obj["url"] as? String else { return nil }
        // A URL the human verified is a real destination, so BROWSE may
        // use it — the invented-URL refusal must not block it.
        await MainActor.run { BrowserSession.shared.register(urls: [url]) }
        return url
    }

    // MARK: - Verified UI element registry (for the manual re-verification pass)

    /// Registers a confirmed UI element location within `app`'s window, as
    /// (x, y) normalized to 0-1000 relative to the window's own bounds --
    /// matching HiddenWindowAutomation.clickInWindow's coordinate
    /// convention, so a registered element can be clicked directly next
    /// time without a fresh screenshot + vision pass. Automatically stamps
    /// the app's CURRENT bundle version (via HiddenWindowAutomation), so a
    /// later lookup can detect that the app has since been updated and the
    /// cached location may need re-verification -- no external "UI change"
    /// feed exists for this, but a version bump is a cheap, reliable,
    /// fully-local proxy signal.
    @discardableResult
    static func recordVerifiedUIElement(app: String, element: String, x: Double, y: Double) async -> Bool {
        let trimmedApp = app.trimmingCharacters(in: .whitespacesAndNewlines)
        let trimmedElement = element.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedApp.isEmpty, !trimmedElement.isEmpty else { return false }
        let version = await HiddenWindowAutomation.shared.currentAppVersion(appName: trimmedApp) ?? ""
        let raw = await MCPEngine.shared.callTool(
            serverName: serverName, toolName: "record_verified_ui_element",
            arguments: ["app": trimmedApp, "element": trimmedElement, "x": x, "y": y, "version": version],
            mode: .human
        )
        guard let data = raw.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return false }
        return obj["recorded"] != nil
    }

    // MARK: - Milestone Y: typed build/CI failures + capacity review

    /// Sends a failed build/conversion log to Vera-alpha's typed-failure
    /// classifier. The verdict (UNKNOWN_SIGNING / UNKNOWN_DEPENDENCY /
    /// UNKNOWN_MODEL_GEOMETRY / ...) accumulates in the same growth-signal
    /// store as every other typed unknown, so recurrences surface through
    /// `failureStats` with no IDE-side bookkeeping. Returns the verdict
    /// string, or nil if the bridge was unavailable — callers treat this
    /// as fire-and-forget; a failure to record must never matter to the
    /// build path that produced the log.
    @discardableResult
    static func recordBuildFailure(source: String, logExcerpt: String) async -> String? {
        let raw = await MCPEngine.shared.callTool(
            serverName: serverName, toolName: "record_build_failure",
            arguments: ["source": source, "log_excerpt": logExcerpt], mode: .human
        )
        guard let data = raw.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let verdict = obj["verdict"] as? String else { return nil }
        return verdict
    }

    /// The "which kind of failure dominates" view: verdict histogram plus
    /// the boundary classifier's current reading of each bucket. Raw JSON
    /// string; the console renders it.
    static func failureStats() async -> String {
        await MCPEngine.shared.callTool(
            serverName: serverName, toolName: "failure_stats",
            arguments: [:], mode: .human
        )
    }

    // MARK: - Multi-source documents (deep search)

    /// Ingest several sources about one event, preserving their
    /// disagreements. `documents` is [(source, text)] — the source label is
    /// what a disputed claim gets cited to, so it must be something a
    /// reader can act on (outlet, agency, URL), not "doc1".
    @discardableResult
    /// Same as `registerDomain`, for text that arrived without a file —
    /// a paste wrapped in ⟨verantyx⟩ tags. It goes through the same door
    /// and the same gates, so a paste cannot enter on easier terms than a
    /// document.
    static func registerDomainText(_ name: String, text: String) async -> String {
        let obj = await callDoor("vera_domain_text",
                                 ["name": name, "text": text])
        guard let obj else { return "登録できませんでした(扉が応答しません)。" }
        if let v = obj["verdict"] as? String, v != "WROTE" {
            return "🚫 \(v) — \(obj["note"] as? String ?? "")"
        }
        return "🗂 分野「\(name)」として登録(動詞 \(obj["verbs"] as? Int ?? 0)"
            + "・枠 \(obj["slots"] as? Int ?? 0))。文法は共有のまま、語彙だけ。"
    }

    /// Register a document's vocabulary as a domain — words, not facts.
    ///
    /// Measured across an encyclopedia, the Civil Code, the Labour
    /// Standards Act and a two-page brief, grammar transfers (0.735–0.857
    /// agreement against a 0.28 control) while vocabulary does not. So a
    /// domain costs its nouns and the shared map is left alone; nothing
    /// here votes, and `frames` is never written.
    static func registerDomain(_ name: String, path: String) async -> String {
        let obj = await callDoor("vera_domain",
                                 ["name": name, "path": path])
        guard let obj else { return "登録できませんでした(扉が応答しません)。" }
        if let v = obj["verdict"] as? String, v != "WROTE" {
            return "🚫 \(v) — \(obj["note"] as? String ?? "")"
        }
        let verbs = obj["verbs"] as? Int ?? 0
        let slots = obj["slots"] as? Int ?? 0
        return "🗂 分野「\(name)」として登録しました(動詞 \(verbs)・枠 \(slots))。"
            + "文法は共有のまま、この文書の語彙だけが足されています。"
    }

    static func ingestDocuments(_ documents: [(source: String, text: String)]) async -> String {
        let payload = documents.map { ["source": $0.source, "text": $0.text] }
        guard let data = try? JSONSerialization.data(withJSONObject: payload),
              let json = String(data: data, encoding: .utf8) else { return "" }
        return await MCPEngine.shared.callTool(
            serverName: serverName, toolName: "ingest_documents",
            arguments: ["documents_json": json], mode: .human)
    }

    /// Settled / disputed / missing for a topic. The three stay unblended:
    /// a responder needs to know which parts are agreed, which are contested
    /// and by whom, and which nobody checked — a summary erases exactly that.
    static func deepReport(topic: String) async -> String {
        await MCPEngine.shared.callTool(
            serverName: serverName, toolName: "deep_report",
            arguments: ["topic": topic], mode: .human)
    }

    /// The six-question completeness checklist for a topic.
    static func armCompleteness(topic: String) async -> String {
        await MCPEngine.shared.callTool(
            serverName: serverName, toolName: "arm_completeness",
            arguments: ["topic": topic], mode: .human)
    }

    // MARK: - Failure-domain packs (the research-platform surface)

    /// Every registered pack with its maturity, provenance per verdict, and
    /// whether it is data-defined (editable) or built into code. Also
    /// carries `load_errors`: a pack an expert edited into an invalid state
    /// is reported, never silently missing.
    static func listFailureDomains() async -> String {
        await MCPEngine.shared.callTool(
            serverName: serverName, toolName: "list_failure_domains",
            arguments: [:], mode: .human)
    }

    /// Run a pack over real log samples. Coverage is the number that
    /// matters — a seeded taxonomy that types almost nothing real is not a
    /// taxonomy of that field yet.
    static func testFailurePack(pack: String, logSamples: String) async -> String {
        await MCPEngine.shared.callTool(
            serverName: serverName, toolName: "test_failure_pack",
            arguments: ["pack": pack, "log_samples": logSamples], mode: .human)
    }

    /// Propose a verdict FROM EXAMPLES. The author pastes real failure lines
    /// and counter-examples; the pattern is derived and refused, with the
    /// offending counter-example, if it would claim anything else. Only a
    /// proposal that passes every check is queued.
    static func proposeFailureVerdict(
        pack: String, verdict: String, note: String,
        positives: String, negatives: String,
        remedyKind: String, remedyOwner: String, verify: String, author: String
    ) async -> String {
        await MCPEngine.shared.callTool(
            serverName: serverName, toolName: "propose_failure_verdict",
            arguments: ["pack": pack, "verdict": verdict, "note": note,
                        "positive_examples": positives,
                        "negative_examples": negatives,
                        "remedy_kind": remedyKind, "remedy_owner": remedyOwner,
                        "verify": verify, "author": author], mode: .human)
    }

    static func listPendingPackVerdicts() async -> String {
        await MCPEngine.shared.callTool(
            serverName: serverName, toolName: "list_pending_pack_verdicts",
            arguments: [:], mode: .human)
    }

    /// The only path from a proposal to a live classifier: writes the pack
    /// into the overlay directory and reloads the registry.
    static func acceptPackVerdict(index: Int) async -> String {
        await MCPEngine.shared.callTool(
            serverName: serverName, toolName: "accept_pack_verdict",
            arguments: ["index": index], mode: .human)
    }

    static func rejectPackVerdict(index: Int) async -> String {
        await MCPEngine.shared.callTool(
            serverName: serverName, toolName: "reject_pack_verdict",
            arguments: ["index": index], mode: .human)
    }

    /// Calibrated limit increases awaiting review — each carries the probe
    /// evidence (which failing queries were re-run, at which multipliers).
    static func listPendingCapacityLimits() async -> String {
        await MCPEngine.shared.callTool(
            serverName: serverName, toolName: "list_pending_capacity_limits",
            arguments: [:], mode: .human
        )
    }

    /// The ONLY path by which a proposed limit becomes a running limit —
    /// same human-approval contract as facts and generated modules.
    static func acceptCapacityLimit(index: Int) async -> String {
        await MCPEngine.shared.callTool(
            serverName: serverName, toolName: "accept_capacity_limit",
            arguments: ["index": index], mode: .human
        )
    }

    static func rejectCapacityLimit(index: Int) async -> String {
        await MCPEngine.shared.callTool(
            serverName: serverName, toolName: "reject_capacity_limit",
            arguments: ["index": index], mode: .human
        )
    }

    /// Milestone S: the first wire between the IDE's "body" (UI-automation
    /// action/observation, already recorded to UITestVectorTrace at the
    /// same call site) and Vera-alpha's "mind" (GapGraph). Unlike
    /// UITestVectorTrace's embedding (JGEN-backend-only), this writes to
    /// Vera-alpha's model-independent GapGraph -- it survives a model
    /// swap. Respects the normal/experiment/sleep contract server-side
    /// (a no-op in "normal" mode, matching every other GapNode-creating
    /// path); `cognitionMode` is passed through rather than decided here.
    @discardableResult
    static func recordUITransition(sessionId: String, actionLabel: String, changed: Bool, cognitionMode: String) async -> Bool {
        let trimmedLabel = actionLabel.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !sessionId.isEmpty, !trimmedLabel.isEmpty else { return false }
        let raw = await MCPEngine.shared.callTool(
            serverName: serverName, toolName: "record_ui_transition",
            arguments: ["session_id": sessionId, "action_label": trimmedLabel, "changed": changed, "cognition_mode": cognitionMode],
            mode: .human
        )
        guard let data = raw.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return false }
        return obj["ok"] as? Bool ?? false
    }

    /// Act-loop convenience: record a gap observation using the session cognition mode.
    /// Best-effort — never throws; local ActGapController remains the loop driver.
    @discardableResult
    static func recordActGapObservation(sessionId: String, actionLabel: String, changed: Bool) async -> Bool {
        let mode = CouncilSettingsStore.shared.cognitionMode.rawValue
        return await recordUITransition(
            sessionId: sessionId,
            actionLabel: actionLabel,
            changed: changed,
            cognitionMode: mode
        )
    }

    /// Milestone R2: structure an unfamiliar Act/harness mission into GapNodes.
    /// Returns the first gap_id when present, else nil. Never blocks the Act loop.
    /// `cognitionMode` is forwarded as-is — the Python tool itself is the one
    /// that enforces "normal" as a guaranteed no-op (same contract as
    /// `recordUITransition`/Milestone S), so callers must not bypass this by
    /// gating on unrelated state (e.g. which memory layer is selected).
    static func bootstrapUnknownTask(
        name: String,
        description: String = "",
        userGoal: String = "",
        availableTools: String = "",
        successCriteria: String = "",
        constraints: String = "",
        cognitionMode: String = "normal"
    ) async -> String? {
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        var args: [String: Any] = ["name": trimmed, "cognition_mode": cognitionMode]
        if !description.isEmpty { args["description"] = description }
        if !userGoal.isEmpty { args["user_goal"] = userGoal }
        if !availableTools.isEmpty { args["available_tools"] = availableTools }
        if !successCriteria.isEmpty { args["success_criteria"] = successCriteria }
        if !constraints.isEmpty { args["constraints"] = constraints }
        let raw = await MCPEngine.shared.callTool(
            serverName: serverName, toolName: "bootstrap_unknown_task",
            arguments: args,
            mode: .human
        )
        guard let data = raw.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
        if let ids = obj["gap_ids"] as? [String], let first = ids.first, !first.isEmpty {
            return first
        }
        if let id = obj["gap_id"] as? String, !id.isEmpty { return id }
        return nil
    }

    struct VerifiedUIElementLookup {
        let x: Double
        let y: Double
        let registeredVersion: String
        /// True when the app's current version differs from what was
        /// recorded at registration time -- the coordinate may be stale
        /// and worth re-verifying rather than trusted outright.
        let possiblyStale: Bool
    }

    /// Deterministic lookup for one element registered via
    /// `recordVerifiedUIElement`, flagging staleness by comparing the
    /// stored version against the app's current one.
    static func lookupVerifiedUIElement(app: String, element: String) async -> VerifiedUIElementLookup? {
        let raw = await MCPEngine.shared.callTool(
            serverName: serverName, toolName: "lookup_verified_ui_element",
            arguments: ["app": app, "element": element],
            mode: .human
        )
        guard let data = raw.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              obj["verdict"] as? String == "ANSWER",
              let x = obj["x"] as? Double, let y = obj["y"] as? Double else { return nil }
        let registeredVersion = (obj["version"] as? String) ?? ""
        var stale = false
        if !registeredVersion.isEmpty,
           let currentVersion = await HiddenWindowAutomation.shared.currentAppVersion(appName: app),
           currentVersion != registeredVersion {
            stale = true
        }
        return VerifiedUIElementLookup(x: x, y: y, registeredVersion: registeredVersion, possiblyStale: stale)
    }

    struct RegisteredUIElement: Identifiable {
        let element: String
        let x: Double
        let y: Double
        let version: String
        var id: String { element }
    }

    /// Lists every element registered for `app` -- drives the manual
    /// "re-verify now" pass (task #25's v1) without needing element names
    /// known ahead of time.
    static func listVerifiedUIElements(app: String) async -> [RegisteredUIElement] {
        let raw = await MCPEngine.shared.callTool(
            serverName: serverName, toolName: "list_verified_ui_elements",
            arguments: ["app": app],
            mode: .human
        )
        guard let data = raw.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let elements = obj["elements"] as? [[String: Any]] else { return [] }
        return elements.compactMap { entry in
            guard let name = entry["element"] as? String,
                  let x = entry["x"] as? Double, let y = entry["y"] as? Double else { return nil }
            let version = (entry["version"] as? String) ?? ""
            return RegisteredUIElement(element: name, x: x, y: y, version: version)
        }
    }

    // MARK: - Graph snapshot (stereo-cross 3D visualization)

    struct GraphFacet: Decodable { let facet: String; let count: Int }
    struct GraphNode: Decodable { let core: String; let pour_count: Int; let facets: [GraphFacet] }
    struct GraphSnapshot: Decodable { let nodes: [GraphNode]; let total_cores: Int }

    /// Fetches a structural snapshot of Vera's CrossStore for
    /// `StereoCrossGraphView` -- read-only, not used for grounded QA
    /// (that's `askRaw`/`recall`/`tryDirectAnswer` above).
    static func fetchGraphSnapshot(limit: Int = 24, facetsPerCore: Int = 6, focusCores: [String] = []) async -> GraphSnapshot? {
        var arguments: [String: Any] = ["limit": limit, "facets_per_core": facetsPerCore]
        if !focusCores.isEmpty {
            arguments["focus_cores"] = focusCores.joined(separator: ",")
        }
        let raw = await MCPEngine.shared.callTool(
            serverName: serverName, toolName: "graph_snapshot",
            arguments: arguments,
            mode: .human
        )
        guard let data = raw.data(using: .utf8) else { return nil }
        return try? JSONDecoder().decode(GraphSnapshot.self, from: data)
    }

    /// Same bracket-tag markers CortexEngine.extractAndStore already
    /// scans for (`[WRITE: ...]`, `[PATCH_FILE: ...]`, `[APPLY_PATCH: ...]`)
    /// — reused here rather than re-deriving them, and routed to
    /// `record_code_change` instead of the sentence-splitting
    /// `propose_ai_facts`: a unified diff or a bracket tag like
    /// `[WRITE: billing.py]` contains no real sentence terminators except
    /// stray periods in file extensions/decimals, so Vera's `.`/`!`/`?`
    /// sentence splitter chops it at nonsensical points instead of
    /// dropping or preserving it cleanly.
    private static func extractCodeChanges(from response: String) -> [(file: String, description: String)] {
        let patterns = [
            (#"\[WRITE:\s*([^\]]+)\]"#, "written"),
            (#"\[PATCH_FILE:\s*([^\]]+)\]"#, "patched"),
            (#"\[APPLY_PATCH:\s*([^\]]+)\]"#, "patch applied"),
        ]
        var results: [(file: String, description: String)] = []
        for (pattern, verb) in patterns {
            guard let regex = try? NSRegularExpression(pattern: pattern) else { continue }
            let matches = regex.matches(in: response, range: NSRange(response.startIndex..., in: response))
            for m in matches {
                guard let r = Range(m.range(at: 1), in: response) else { continue }
                let file = String(response[r]).trimmingCharacters(in: .whitespaces)
                guard !file.isEmpty else { continue }
                results.append((file: file, description: verb))
            }
        }
        return results
    }

    // MARK: - ask() — single source of truth for every Vera query

    struct AskResult {
        let verdict: String
        let core: String?
        let text: String?
        let agreeFrac: Double?
        /// Grain band — how many cut-varied staircase settings agreed on
        /// an item, out of how many. Attached by the MCP `ask` tool as a
        /// `grain` object BESIDE the verdict. The band annotates and never
        /// votes: `tryDirectAnswer`'s gate stays on `agree_frac` alone,
        /// because pooling structure (grain) with evidence (consensus
        /// agreement) is the measured mistake the Vera side refuses.
        let grainAgree: Int?
        let grainOf: Int?

        /// ", grain 3/6"-style suffix for display strings; empty when the
        /// server sent no band (older server, or nothing to count).
        var grainBadge: String {
            guard let agree = grainAgree, let of = grainOf else { return "" }
            return ", grain \(agree)/\(of)"
        }
    }

    /// Every other function in this bridge that reads from Vera goes
    /// through this one call site. Shape from
    /// `verantyx.consensus.Verdict.as_dict()` via the `ask` MCP tool:
    /// {"verdict": "ANSWER"|"UNKNOWN_*", "core": str, "text": str,
    /// "agree_frac": float, ...} — verified against a live
    /// `python3.11 -m verantyx.cli mcp` process, not guessed. `grain`
    /// ({"agree": int, "of": int, ...}) is optional: newer servers attach
    /// it beside the verdict (fork GRAIN_BAND_ANNOTATES_NEVER_VOTES on
    /// the Vera side pins that attaching it changes no verdict), older
    /// servers simply omit it and every path here tolerates its absence.
    private static func askRaw(_ query: String) async -> AskResult {
        // The verdict path lights the cross like every other door: the
        // question enters the routing, and only then does an answer
        // reach the transcript.
        await MainActor.run { VeraRouteState.shared.began(door: "ask") }
        defer { }
        let raw = await MCPEngine.shared.callTool(
            serverName: serverName, toolName: "ask",
            arguments: ["query": query], mode: .human
        )
        if let d = raw.data(using: .utf8),
           let o = try? JSONSerialization.jsonObject(with: d) as? [String: Any] {
            await MainActor.run {
                VeraRouteState.shared.finished(door: "ask", payload: o)
            }
        } else {
            await MainActor.run {
                VeraRouteState.shared.finished(door: "ask", payload: nil)
            }
        }
        guard
            let data = raw.data(using: .utf8),
            let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let verdict = obj["verdict"] as? String
        else {
            return AskResult(verdict: "UNKNOWN_CALL_FAILED", core: nil, text: nil,
                             agreeFrac: nil, grainAgree: nil, grainOf: nil)
        }

        let grain = obj["grain"] as? [String: Any]
        let result = AskResult(
            verdict: verdict,
            core: obj["core"] as? String,
            text: obj["text"] as? String,
            agreeFrac: obj["agree_frac"] as? Double,
            grainAgree: grain?["agree"] as? Int,
            grainOf: grain?["of"] as? Int
        )
        if verdict == "ANSWER", let core = result.core {
            await VeraSkillForge.recordAnswerAndMaybeForge(core: core)
        }
        return result
    }

    /// Same position as `SessionMemoryArchiver.semanticSearch(layer:)` for
    /// l1/l1.5/l2/l3 — call this instead when a session's `activeLayer` is
    /// `.vera`. Only injects a section when Vera itself returns a typed
    /// ANSWER verdict; UNKNOWN_* or any call failure (server not yet
    /// connected) contributes nothing, same fail-open behavior every other
    /// layer already has on an empty match — never a hard error in the
    /// agent loop.
    static func recall(for query: String) async -> String {
        let r = await askRaw(query)
        guard r.verdict == "ANSWER", let core = r.core else { return "" }
        let text = r.text ?? ""
        let agreeFrac = r.agreeFrac.map { String(format: "%.2f", $0) } ?? "?"

        return """

        [VERA MEMORY — deterministic, typed-verdict store (ANSWER, not a guess)]
          🧩 \(core): \(text)  (agreement: \(agreeFrac)\(r.grainBadge))
        [/VERA MEMORY]
        """
    }

    /// Minimum `agree_frac` required to skip the LLM entirely. Deliberately
    /// high — this trades a rarer fast-path for never confidently
    /// short-circuiting on a shaky verdict. Below this, the normal path
    /// (LLM call, with Vera's answer injected as context via `recall`)
    /// still runs — this is a strict ADDITION to the existing path, never
    /// a replacement for it.
    static let directAnswerThreshold = 0.9

    /// Skips the local LLM call entirely for a high-confidence, already-
    /// grounded ANSWER. Returns nil (meaning: fall through to the normal
    /// LLM turn) on anything less than a clean, confident ANSWER —
    /// UNKNOWN_*, a call failure, or an ANSWER below `directAnswerThreshold`
    /// all fall through rather than risk answering wrong with false
    /// confidence.
    static func tryDirectAnswer(for query: String) async -> String? {
        let r = await askRaw(query)
        guard
            r.verdict == "ANSWER",
            let core = r.core, let text = r.text,
            let agree = r.agreeFrac, agree >= directAnswerThreshold
        else { return nil }

        return """
        🧩 \(text)

        (Vera direct answer — core: \(core), agreement: \(String(format: "%.2f", agree))\(r.grainBadge) — no LLM call was made)
        """
    }

    // MARK: - The three hand-off doors (diff / intent / typo)

    /// Raw-JSON call for the `vera_*` doors. The Vera model's own NATIVE
    /// process answers first (no MCP registry, no sanitizer, no config to
    /// go stale); the MCP path remains as the fallback for builds without
    /// the bundled engine. An engine without the tool returns unparseable
    /// output and every band tolerates that as nil — a band that errors
    /// is worse than no band.
    static func callDoor(
        _ tool: String, _ args: [String: Any]
    ) async -> [String: Any]? {
        // The cross is lit from HERE, the one road every Vera door
        // takes — so the light on screen and the work in the engine
        // are the same event, never a timer imitating one.
        await MainActor.run { VeraRouteState.shared.began(door: tool) }
        let obj = await callDoorRaw(tool, args)
        await MainActor.run {
            VeraRouteState.shared.finished(door: tool, payload: obj)
        }
        return obj
    }

    private static func callDoorRaw(
        _ tool: String, _ args: [String: Any]
    ) async -> [String: Any]? {
        if let native = await VeraModelProcess.shared.call(tool, args) {
            return native
        }
        let raw = await MCPEngine.shared.callTool(
            serverName: serverName, toolName: tool,
            arguments: args, mode: .human
        )
        guard let data = raw.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data)
                as? [String: Any]
        else { return nil }
        return obj
    }

    /// 「AとBの違い」-shaped questions get a structural answer with no
    /// LLM call: shared / A-only / B-only from the `vera_diff` door.
    /// Two lines are load-bearing and mirror the Vera-side guards:
    /// "Aのみ" always reads "Bについては実測なし" — never a negative
    /// claim about B — and the abstained layers are named, not hidden.
    /// The output is marked 構成的 so a reader can tell selection from
    /// testimony, exactly like EXPLAINED_BY_UNITS.
    static func tryDiffAnswer(for query: String) async -> String? {
        let q = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let tail = q.range(of: "の違い") else { return nil }
        let head = String(q[q.startIndex..<tail.lowerBound])
        let parts = head.components(separatedBy: "と")
        guard parts.count == 2 else { return nil }
        let a = parts[0].trimmingCharacters(in: .whitespaces)
        let b = parts[1].trimmingCharacters(in: .whitespaces)
        guard !a.isEmpty, !b.isEmpty, a.count <= 12, b.count <= 12
        else { return nil }

        guard let obj = await callDoor("vera_diff", ["a": a, "b": b])
        else { return nil }
        // A diff that abstains has a BETTER refusal than the generic one
        // the ask path would give: it names which side was ambiguous and
        // lists the senses the encyclopedia itself wrote down. Throwing
        // that away and letting UNKNOWN_NOT_PRESENT win was a wiring bug
        // — 「りんごとみかんの違い」 got a wall where it should have got
        // a menu. The abstention is still a refusal; it just says enough
        // for the asker's next question to succeed.
        if obj["verdict"] as? String != "DIFF" {
            return renderDiffAbstention(a: a, b: b, obj: obj)
        }

        func bundle(_ key: String) -> [String] {
            guard let rows = obj[key] as? [[String: Any]] else { return [] }
            return rows.compactMap { $0["token"] as? String }
        }
        let shared = bundle("shared")
        let onlyA = bundle("only_a")
        let onlyB = bundle("only_b")
        guard !(shared.isEmpty && onlyA.isEmpty && onlyB.isEmpty)
        else { return nil }

        var lines: [String] = ["🧭 \(a) と \(b) の構造差分"]
        if !shared.isEmpty {
            lines.append("共有: " + shared.prefix(8).joined(separator: "・"))
        }
        if !onlyA.isEmpty {
            lines.append("\(a)のみ実測: " + onlyA.prefix(8).joined(separator: "・")
                         + "(\(b)については実測なし)")
        }
        if !onlyB.isEmpty {
            lines.append("\(b)のみ実測: " + onlyB.prefix(8).joined(separator: "・")
                         + "(\(a)については実測なし)")
        }
        if let abstain = obj["abstain"] as? [String], !abstain.isEmpty {
            lines.append("棄権した層: " + abstain.joined(separator: "・"))
        }
        lines.append("")
        lines.append("(Vera structural diff — 構成的比較・証言ではない — no LLM call was made)")
        return lines.joined(separator: "\n")
    }

    /// A diff abstention, rendered so the next question can succeed:
    /// which side stopped it, the senses Wikipedia itself lists, and
    /// the bare-title target when the surface hopped to a 曖昧さ回避
    /// page. Nil for abstentions with nothing useful to say — then the
    /// ask path's own refusal is the honest one.
    private static func renderDiffAbstention(
        a: String, b: String, obj: [String: Any]
    ) -> String? {
        let verdict = (obj["verdict"] as? String) ?? ""
        guard let senses = obj["senses"] as? [String: Any] else { return nil }
        var lines: [String] = ["🚫 \(verdict) — \(a) と \(b) の比較は成立しません"]
        var said = false
        for (key, label) in [("a", a), ("b", b)] {
            guard let side = senses[key] as? [String: Any],
                  (side["verdict"] as? String) == "AMBIGUOUS_SENSE"
            else { continue }
            said = true
            lines.append("「\(label)」は曖昧さ回避 — どの語義かが決まりません。")
            if let list = side["senses"] as? [[String: Any]] {
                let names = list.compactMap { $0["core"] as? String }
                if !names.isEmpty {
                    lines.append("候補: " + names.prefix(5).joined(separator: "・"))
                }
            }
            if let base = side["base_target"] as? String {
                lines.append("素の見出し語の行き先: \(base)(この名前で訊けば比較できます)")
            }
        }
        if !said, let cov = obj["coverage"] as? [String: Any] {
            // Thin side: say which one and how thin, not just "no".
            for (key, label) in [("a", a), ("b", b)] {
                if let c = cov[key] as? [String: Any],
                   let p = c["predicates"] as? Int, p == 0 {
                    lines.append("「\(label)」は述語プロファイルが空 — 比べる面がありません。")
                    said = true
                }
            }
        }
        guard said else { return nil }
        lines.append("")
        lines.append("(型付き拒否 — 実測のない差異は作りません)")
        return lines.joined(separator: "\n")
    }

    /// The instruction's structural reading, when the measured frame
    /// table covers it. INTENT frames become a one-line band the LLM
    /// and the reader both see; UNKNOWN_INTENT stays silent — the
    /// refusal IS the routing (the model takes the utterance).
    static func intentBand(for text: String) async -> String? {
        guard let obj = await callDoor("vera_intent", ["text": text]),
              obj["verdict"] as? String == "INTENT",
              let op = obj["op"] as? String
        else { return nil }
        let args = (obj["args"] as? [String: Any]) ?? [:]
        let rendered = args
            .sorted { $0.key < $1.key }
            .map { "\($0.key)=\($0.value)" }
            .joined(separator: ", ")
        return "[VERA INTENT] \(op)(\(rendered)) — 47動詞×28操作の実測表による構造読み。表外なら出ない。\n"
    }

    /// Typo candidates for a refused single-term query. Fires only
    /// beside a typed unknown (the caller gates it), only on short
    /// particle-free terms, and NEVER rewrites — the band shows the
    /// evidence (shared units, edit distance) and the reader decides.
    static func typoBand(for query: String) async -> String? {
        var term = query.trimmingCharacters(in: .whitespacesAndNewlines)
        for suffix in ["について", "ですか", "とは", "？", "?"] {
            if term.hasSuffix(suffix) {
                term = String(term.dropLast(suffix.count))
            }
        }
        guard (2...8).contains(term.count),
              !term.contains(" "), !term.contains("　"),
              !["は", "が", "を", "の", "に"].contains(where: term.contains)
        else { return nil }

        guard let obj = await callDoor("vera_typo", ["term": term]),
              obj["verdict"] as? String == "TYPO_CANDIDATE",
              let cands = obj["candidates"] as? [[String: Any]], !cands.isEmpty
        else { return nil }
        let rendered = cands.prefix(3).compactMap { c -> String? in
            guard let w = c["word"] as? String else { return nil }
            let d = (c["edit_distance"] as? Int).map { "距離\($0)" } ?? ""
            return "\(w)(\(d))"
        }.joined(separator: "・")
        guard !rendered.isEmpty else { return nil }
        return "[VERA TYPO] 「\(term)」は語彙に実測なし。近傍の実証語: \(rendered) — 書き換えは行っていない。\n"
    }

    /// Constructed explanation via meaning descent (`vera_explain`):
    /// the term's units grounded in sourced definition sentences, or nil
    /// when the descent abstains. The marker line is not decoration —
    /// it is the type: constructed, never testimony about the term.
    static func explainBand(for query: String) async -> String? {
        var term = query.trimmingCharacters(in: .whitespacesAndNewlines)
        for suffix in ["について", "ですか", "とは", "って何", "？", "?"] {
            if term.hasSuffix(suffix) {
                term = String(term.dropLast(suffix.count))
            }
        }
        guard (2...12).contains(term.count), !term.contains(" ") else { return nil }
        guard let obj = await callDoor("vera_explain", ["term": term]),
              obj["verdict"] as? String == "EXPLAINED_BY_UNIT_DEFS",
              let units = obj["units"] as? [[String: Any]]
        else { return nil }
        var lines: [String] = []
        if let split = obj["split"] as? [String] {
            lines.append("「\(term)」は \(split.joined(separator: " と ")) に分解される。")
        }
        for u in units {
            guard let name = u["unit"] as? String,
                  let def = u["definition"] as? String, !def.isEmpty
            else { continue }
            let src = (u["source"] as? String).map { "(\($0))" } ?? ""
            lines.append("・\(name): \(def.prefix(90))\(src)")
        }
        guard lines.count > 1 else { return nil }
        lines.append("(構成的説明 — 証言ではない)")
        return lines.joined(separator: "\n")
    }

    /// The pure-Vera turn: the store itself is the responder and no LLM
    /// runs anywhere. 違い questions get the structural diff; everything
    /// else gets the full stack's verdict VERBATIM — an answer with its
    /// route, or a typed refusal wearing whatever honest hand-offs apply
    /// (typo evidence, constructed explanation, the remedy). This is the
    /// IDE's version of the 3D page's ASK, and like it, it never guesses.
    /// 検索 → 一時空間で引用 → 破棄。
    ///
    /// IDE が持つ検索(WebSearchEngine)で頁を取り、vera_fresh に渡す。
    /// サーバ側は関数の中だけに索引して逐語引用で答え、店にも文書にも
    /// 会話にも一行も書かずに消える — 「最新を取り、必要以上に取り込ま
    /// ない」の実装。破棄は方針でなく構造で、直後に同じ主題を聞けば
    /// ABSENT が返ることで追試できる。
    static func veraFreshTurn(for query: String) async -> String? {
        let result = await WebSearchEngine.shared.search(query: query)
        let text = String(result.markdown.prefix(18_000))
        guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
        let sources: [[String: String]] = [[
            "url": result.url, "title": result.query, "text": text,
        ]]
        guard let data = try? JSONSerialization.data(withJSONObject: sources),
              let json = String(data: data, encoding: .utf8),
              let obj = await callDoor("vera_fresh",
                                       ["query": query, "sources_json": json])
        else { return nil }
        let verdict = (obj["verdict"] as? String) ?? ""
        guard verdict.hasPrefix("DOCUMENT") else { return nil }
        var lines: [String] = []
        if let t = obj["reply"] as? String, !t.isEmpty { lines.append("🌐 \(t)") }
        if let src = obj["source"] as? String, !src.isEmpty {
            lines.append("出典: \(src)")
        }
        lines.append("(⏳ 一時知識 — 検索結果は返答と同時に破棄されました。店には入っていません)")
        return lines.joined(separator: "\n")
    }

    static func veraModelTurn(
        for query: String, trail: String? = nil, storeFirst: Bool = false
    ) async -> (reply: String, core: String?) {
        // One door. This function used to hold the ordering itself — the
        // diff short-circuit, then `vera_ask`, then a context retry — and
        // `VeraDialogueScreen` held a second copy of the same three steps.
        // Two compositions of one engine drift, and the one that drifts
        // behind quietly becomes a smaller product. The order now lives in
        // `engine.ask`, which also runs the organs neither copy called:
        // typo repair, arithmetic, the mathlib witness, the gap ledger,
        // frame composition.
        //
        // What stays here is presentation, which is genuinely this side's
        // job: what a reader sees beside a verdict.
        // `storeFirst` picks which of the two spaces gets to be THE
        // answer when both have one: the documents loaded on this machine,
        // or the published federation. They are never merged. Measured on
        // a contest PDF: 「入力フォームとは」 answers from jawiki's privacy
        // article under the federation and from the loaded PDF under the
        // store — both true about different things, which is exactly why
        // the person chooses rather than a score.
        // vera_chat is vera_engine plus what a CONVERSATION needs, held on
        // the server so every client shares one memory: the turn enters the
        // conversation space (recallable later, no window), last_core rides
        // server-side so 「その刑は」 resolves without this file keeping a
        // trail, and every reply is audited beside the answer — covenants
        // set in this conversation, and drift against what it already
        // settled. No model is called anywhere in the turn, and MCP
        // sampling is never requested — there is nothing to sample.
        //
        // The older binary has no vera_chat; falling back to vera_engine
        // keeps the mode alive there, minus memory and audits.
        var obj0 = await callDoor(
            "vera_chat",
            ["text": query, "store_first": storeFirst])
        if obj0 == nil {
            obj0 = await callDoor(
                "vera_engine",
                ["query": query, "last_core": trail ?? "", "domain": "",
                 "store_first": storeFirst])
        }
        guard var obj = obj0 else {
            return ("⚠️ vera-memory サーバに接続できません(設定 › MCP を確認してください)", nil)
        }
        // vera_chat speaks in `reply`; the presentation below reads `text`.
        if obj["text"] == nil, let rep = obj["reply"] { obj["text"] = rep }
        let verdict = (obj["verdict"] as? String) ?? "UNKNOWN"
        let refused = verdict.hasPrefix("UNKNOWN")
            || verdict.hasPrefix("ABSTAIN") || verdict.hasPrefix("AMBIGUOUS")

        var lines: [String] = []

        // Every stage that CHANGED the question is printed. An invisible
        // context resolution is the same shape of lie as an invisible
        // ingest — and now typo repair and staging become visible on the
        // same rule, rather than only the one step this file implemented.
        let stages = (obj["stages"] as? [[String: Any]]) ?? []
        for st in stages where (st["changed"] as? Bool) == true {
            guard let name = st["stage"] as? String,
                  let note = st["note"] as? String, !note.isEmpty
            else { continue }
            lines.append("🧭 \(name): \(note)")
        }

        if !refused {
            if let t = obj["text"] as? String, !t.isEmpty {
                lines.append("🧩 \(t)")
            }
            var footer: [String] = ["verdict: \(verdict)"]
            if let door = obj["door"] as? String, !door.isEmpty {
                footer.append(door == "store" ? "扉: 端末の文書" : "扉: \(door)")
            }
            if let core = obj["core"] as? String, !core.isEmpty {
                footer.append("core: \(core)")
            }
            // The engine gathers these under one key, from whichever
            // convention the answering door uses.
            if let r = obj["readings"] as? [String: Any] {
                if let tier = r["tier"] as? String { footer.append("tier: \(tier)") }
                if let g = r["grain"] as? String { footer.append("grain \(g)") }
                if let w = r["witnesses"] as? Int { footer.append("witnesses \(w)") }
            }
            if let origins = obj["origins"] as? [String], !origins.isEmpty {
                footer.append("出典: " + origins.prefix(3).joined(separator: ", "))
            }
            lines.append("(\(footer.joined(separator: " · ")) — Vera単体・LLM不使用)")
        } else {
            lines.append("🚫 \(verdict)")
            if let note = obj["note"] as? String, !note.isEmpty { lines.append(note) }
            if let missing = obj["missing"] as? String, !missing.isEmpty {
                lines.append("欠けているもの: \(missing)")
            }
            // The gap ledger is consulted by the engine on every refusal
            // now, so a known ticket appears without this side asking.
            for st in stages where (st["stage"] as? String) == "gaps" {
                if let n = st["note"] as? String, n.hasPrefix("既知の欠落") {
                    lines.append(n)
                }
            }
            if let remedy = obj["remedy"] as? String, !remedy.isEmpty {
                lines.append("解消するには: \(remedy)")
            }
            lines.append("(型付き拒否 — Vera単体は知らないことを推測しません)")
            // 店が知らないときだけ、検索の一時知識を隣に置く。推測では
            // なく出典つきの引用で、返答と同時に破棄される。ユーザーの
            // 検索トグルが門 — 黙って外に出ることはない。
            if await MainActor.run(body: { AppState.shared?.toolWebSearchEnabled ?? false }) {
                if let fresh = await veraFreshTurn(for: query) {
                    lines.append(fresh)
                }
            }
        }
        // The audits ride BESIDE the reply, never as a gate — display the
        // ones that actually fired and stay silent otherwise.
        if let audits = obj["audits"] as? [String: Any] {
            if let cov = audits["covenants"] as? [String: Any],
               (cov["verdict"] as? String) == "BROKEN",
               let broken = cov["violations"] as? [[String: Any]] {
                for v in broken.prefix(2) {
                    if let name = v["covenant"] as? String {
                        lines.append("⚖️ 誓約違反の疑い: \(name)")
                    }
                }
            }
            if let drift = audits["context_drift"] as? [String: Any],
               (drift["verdict"] as? String) == "COLLAPSED" {
                lines.append("🌀 文脈崩れの疑い — この会話で確定済みの内容と接続がありません")
            }
        }
        let core = obj["core"] as? String
        return (lines.joined(separator: "\n\n"), refused ? nil : core)
    }

    /// Veraぼっと: the app answering about itself.
    ///
    /// `settings_lookup` names the exact tab and field. When it cannot,
    /// `settings_search` offers ranked candidates rather than a dead
    /// end — an "I don't know" about your own settings screen is a
    /// worse failure than an "I don't know" about the world, because
    /// the answer is right there in the registry. Both doors read the
    /// same registry the guide is generated from, so the reply and the
    /// document cannot drift apart, and neither is a model recalling a
    /// menu it saw once.
    static func settingsAnswer(for question: String) async -> String {
        guard let hit = await callDoor("settings_lookup",
                                       ["question": question]) else {
            return "⚠️ 設定レジストリに接続できません。"
        }
        let verdict = (hit["verdict"] as? String) ?? ""
        if verdict == "ANSWER" {
            var lines: [String] = []
            if let tab = hit["tab"] as? String, let field = hit["field"] as? String {
                lines.append("⚙️ 設定 › \(tab) › \(field)")
            } else if let name = hit["setting"] as? String {
                lines.append("⚙️ \(name)")
            }
            if let what = hit["what"] as? String, !what.isEmpty { lines.append(what) }
            if let now = hit["current"] as? String, !now.isEmpty {
                lines.append("現在: \(now)")
            }
            lines.append("")
            lines.append("(設定レジストリより — 推測ではありません)")
            return lines.joined(separator: "\n")
        }

        guard let near = await callDoor("settings_search",
                                        ["question": question, "limit": 6]),
              let rows = near["matches"] as? [[String: Any]] ?? near["results"] as? [[String: Any]],
              !rows.isEmpty else {
            return "🚫 \(verdict.isEmpty ? "UNKNOWN_NO_SETTING" : verdict)\n\n"
                + "その設定は登録簿にありません。近いものも見つからないので、"
                + "候補を作らずに黙ります。\n\n(型付き拒否 — 設定を発明しません)"
        }
        var lines = ["🔎 近い設定の候補:"]
        for r in rows.prefix(6) {
            let name = (r["field"] as? String) ?? (r["setting"] as? String) ?? "?"
            let tab = (r["tab"] as? String).map { "\($0) › " } ?? ""
            lines.append("・\(tab)\(name)")
        }
        lines.append("")
        lines.append("(候補は登録簿の近傍 — どれかを名指せば確定します)")
        return lines.joined(separator: "\n")
    }

    // MARK: - Typed unknowns as control signals

    /// A refusal, typed, with the action branch its type selects. Other
    /// agents' "わからない" is a silent blank; Vera's refusal carries its
    /// own next move. The branch NEVER invents an answer — it routes.
    struct TypedUnknown: Sendable {
        let verdict: String
        let branch: String
        let remedy: String
    }

    /// verdict -> action branch. The mapping is small on purpose: four
    /// branches cover every refusal type, and an unmapped type routes to
    /// the gap ledger rather than guessing.
    private static func branchFor(_ verdict: String) -> String {
        switch verdict {
        case "UNKNOWN_NO_EVIDENCE", "UNKNOWN_NOT_PRESENT",
             "UNKNOWN_SUBJECT_TOO_THIN":
            return "gather-evidence"
        case "UNKNOWN_INSUFFICIENT_EVIDENCE", "UNKNOWN_UNDERDETERMINED",
             "UNKNOWN_UNRESOLVED_CONTRADICTION":
            return "ask-user"
        case "UNKNOWN_TIME_DEPENDENT":
            return "resolve-time"
        default:
            return "record-gap"
        }
    }

    /// Asks Vera; on a typed refusal, records the HAND-OFF to a branch
    /// before anything tries to resolve it. The ordering is the point: a
    /// refusal an agent later auto-resolves must already be on the
    /// ledger, or the demand queue silently loses exactly the entries
    /// the system handled best (the invisible-ingestion lie, relocated).
    static func typedUnknown(for query: String) async -> TypedUnknown? {
        let r = await askRaw(query)
        guard r.verdict.hasPrefix("UNKNOWN"),
              r.verdict != "UNKNOWN_CALL_FAILED" else { return nil }
        let branch = branchFor(r.verdict)
        // The refusal states its own repair (how_to_resolve); best-effort.
        let remedy = await MCPEngine.shared.callTool(
            serverName: serverName, toolName: "how_to_resolve",
            arguments: ["verdict": r.verdict, "subject": query], mode: .human
        )
        _ = await MCPEngine.shared.callTool(
            serverName: serverName, toolName: "record_refusal_outcome",
            arguments: ["query": query, "verdict": r.verdict,
                        "branch": branch, "resolved": false], mode: .human
        )
        return TypedUnknown(verdict: r.verdict, branch: branch,
                            remedy: String(remedy.prefix(400)))
    }

    /// The prompt block a typed refusal becomes. Instructions per branch,
    /// not knowledge: the block routes the agent's next action and never
    /// supplies content the store does not hold. Pure string assembly,
    /// hence nonisolated.
    nonisolated static func unknownSection(_ u: TypedUnknown) -> String {
        let action: String
        switch u.branch {
        case "gather-evidence":
            action = """
            Vera has no evidence on this subject. GATHER EVIDENCE FIRST: \
            read the relevant files / run grep / run the command, and state \
            only what you observed. If you verified a durable fact, record \
            it (quarantined until a human approves) so this refusal can close.
            """
        case "ask-user":
            action = """
            Vera holds insufficient or conflicting evidence. ASK THE USER \
            to disambiguate before asserting anything.
            """
        case "resolve-time":
            action = """
            The answer depends on WHEN this is asked and the store has no \
            clock. Resolve the date/time first, then re-ask with it stated.
            """
        default:
            action = """
            This is a mapped gap. Say plainly that it is not known here; \
            do not improvise an answer.
            """
        }
        return """

        [VERA UNKNOWN — a typed refusal, not a blank]
          verdict: \(u.verdict) → branch: \(u.branch)
          \(action)
          remedy(server): \(u.remedy)
        [/VERA UNKNOWN]
        """
    }

    /// The one honest oracle for "resolved": Vera answers NOW. Re-asks
    /// the original query after the turn and records the outcome either
    /// way — never the agent's say-so, and never removing the refusal.
    static func closeRefusalIfResolved(query: String, unknown: TypedUnknown) async {
        let after = await askRaw(query)
        _ = await MCPEngine.shared.callTool(
            serverName: serverName, toolName: "record_refusal_outcome",
            arguments: ["query": query, "verdict": unknown.verdict,
                        "branch": unknown.branch,
                        "resolved": after.verdict == "ANSWER"], mode: .human
        )
    }

    // MARK: - Covenant audit of the final answer

    /// One covenant break, shaped for display. The audit is the
    /// vera-memory `check_reply` tool — the register of things the user
    /// SETTLED (「実装言語はTypeScriptを用いる」), checked against the
    /// reply with the question as the scope. Measured before wiring
    /// (tools/measure_check_reply.py on the Vera side): zero false
    /// positives on out-of-scope and covenant-free replies; the one
    /// noisy shape (an empty reply to an in-scope question reads
    /// BROKEN) is fenced by the caller's !saveAnswer.isEmpty guard.
    struct ReplyAudit: Sendable {
        let covenant: String
        let detail: String
        let inject: String
    }

    /// Audits a final answer against the registered covenants. Returns
    /// nil when the register keeps silent (KEPT, no covenants, or the
    /// call failed) — an audit that cannot run must be silent, never a
    /// false alarm. BROKEN is a finding about the REPLY, never about
    /// the user: the rule may have been superseded one turn ago, which
    /// is why this only ever DISPLAYS and never gates or rewrites.
    static func auditReply(reply: String, asked: String) async -> ReplyAudit? {
        let raw = await MCPEngine.shared.callTool(
            serverName: serverName, toolName: "check_reply",
            arguments: ["reply": String(reply.prefix(2000)),
                        "asked": String(asked.prefix(500))], mode: .human
        )
        guard
            let data = raw.data(using: .utf8),
            let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            (obj["verdict"] as? String) == "BROKEN",
            let violations = obj["violations"] as? [[String: Any]],
            let first = violations.first,
            let covenant = first["covenant"] as? String
        else { return nil }

        var parts: [String] = []
        if let used = first["forbidden_used"] as? [String], !used.isEmpty {
            parts.append("禁止語を使用: \(used.joined(separator: "、"))")
        }
        if let missing = first["required_missing"] as? [String], !missing.isEmpty {
            parts.append("必須語が不在: \(missing.joined(separator: "、"))")
        }
        if let subs = first["substituted"] as? [[String: Any]], !subs.isEmpty,
           let s = subs.first, let io = s["instead_of"] as? String,
           let used = s["used"] as? String {
            parts.append("推定代替: \(io) の代わりに \(used)")
        }
        return ReplyAudit(
            covenant: covenant,
            detail: String(parts.joined(separator: " / ").prefix(300)),
            inject: (first["inject"] as? String) ?? covenant
        )
    }

    /// The dispute block, appended to the answer message (one .done —
    /// a second one would re-fire the UI's end-of-turn path). Pure
    /// string assembly, hence nonisolated.
    nonisolated static func auditSection(_ a: ReplyAudit) -> String {
        return """

        ⚖️ [VERA AUDIT — 誓約検査]
        破られた誓約: \(a.covenant)
        \(a.detail)
        再注入候補: 「\(a.inject)」
        (これは表示であって判定ではない — 回答は差し替えない。誓約が既に更新されている可能性もある)
        """
    }

    // MARK: - AI-fact quarantine (Milestone M companion)

    struct PendingAiFact: Identifiable {
        let index: Int
        let text: String
        let source: String
        let timestamp: String
        var id: Int { index }
    }

    static func listPendingAiFacts() async -> [PendingAiFact] {
        let raw = await MCPEngine.shared.callTool(
            serverName: serverName, toolName: "list_pending_ai_facts",
            arguments: [:], mode: .human
        )
        guard let data = raw.data(using: .utf8),
              let arr = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]]
        else { return [] }
        return arr.enumerated().compactMap { offset, entry in
            let index = (entry["index"] as? Int) ?? offset
            let text = (entry["text"] as? String) ?? (entry["fact"] as? String) ?? ""
            guard !text.isEmpty else { return nil }
            let source = (entry["source"] as? String) ?? ""
            let timestamp = (entry["timestamp"] as? String)
                ?? (entry["ts"] as? String)
                ?? ""
            return PendingAiFact(index: index, text: text, source: source, timestamp: timestamp)
        }
    }

    static func acceptAiFact(index: Int) async -> Bool {
        let raw = await MCPEngine.shared.callTool(
            serverName: serverName, toolName: "accept_ai_fact",
            arguments: ["index": index], mode: .human
        )
        guard let data = raw.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return false }
        return (obj["ok"] as? Bool) ?? true
    }

    static func rejectAiFact(index: Int) async -> Bool {
        let raw = await MCPEngine.shared.callTool(
            serverName: serverName, toolName: "reject_ai_fact",
            arguments: ["index": index], mode: .human
        )
        guard let data = raw.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return false }
        return (obj["ok"] as? Bool) ?? true
    }

    // MARK: - Milestone M: self-growth domain-module review
    //
    // Mirrors `list_verified_ui_elements`'s JSON-parsing pattern above.
    // Unlike `propose_ai_facts` (write-only from the IDE today, reviewed
    // via Vera-alpha's own CLI), these 4 tools are round-trip: the IDE can
    // both list pending LLM-drafted modules and cast the human accept/
    // reject vote itself. `accept`/`reject` are the ONLY path to activating
    // a generated module -- calling `heartbeat` alone never does.

    struct PendingDomainModule: Identifiable {
        let index: Int
        let name: String
        let sourceCode: String
        let candidateSummary: String
        let testReport: String  // pretty-printed JSON, shown as-is for review
        var id: Int { index }
    }

    static func listPendingDomainModules() async -> [PendingDomainModule] {
        let raw = await MCPEngine.shared.callTool(
            serverName: serverName, toolName: "list_pending_domain_modules",
            arguments: [:], mode: .human
        )
        guard let data = raw.data(using: .utf8),
              let arr = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]]
        else { return [] }
        return arr.compactMap { entry in
            guard let index = entry["index"] as? Int,
                  let name = entry["name"] as? String,
                  let source = entry["source_code"] as? String else { return nil }
            let summary = (entry["candidate_summary"] as? String) ?? ""
            var reportText = ""
            if let report = entry["test_report"],
               let reportData = try? JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted]) {
                reportText = String(data: reportData, encoding: .utf8) ?? ""
            }
            return PendingDomainModule(
                index: index, name: name, sourceCode: source,
                candidateSummary: summary, testReport: reportText
            )
        }
    }

    /// Only ever fires from an explicit human tap in the review UI --
    /// never called automatically after `heartbeat`.
    static func acceptDomainModule(index: Int) async -> Bool {
        let raw = await MCPEngine.shared.callTool(
            serverName: serverName, toolName: "accept_domain_module",
            arguments: ["index": index], mode: .human
        )
        guard let data = raw.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return false }
        return (obj["ok"] as? Bool) ?? false
    }

    static func rejectDomainModule(index: Int) async -> Bool {
        let raw = await MCPEngine.shared.callTool(
            serverName: serverName, toolName: "reject_domain_module",
            arguments: ["index": index], mode: .human
        )
        guard let data = raw.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return false }
        return (obj["ok"] as? Bool) ?? false
    }

    /// Triggers one growth-loop tick manually from the IDE (in addition to
    /// Vera-alpha's own daily cron/launchd path). `llmModel` empty = report
    /// growth candidates only, without drafting. `cognitionMode: "sleep"`
    /// (Milestone O) additionally attempts quarantine-gated resolution of
    /// open-domain GapNodes -- "normal"/"experiment" only run the existing
    /// closed-domain module-growth pass.
    static func triggerHeartbeat(llmModel: String = "", cognitionMode: String = "normal") async -> String {
        await MCPEngine.shared.callTool(
            serverName: serverName, toolName: "heartbeat",
            arguments: ["llm_model": llmModel, "cognition_mode": cognitionMode], mode: .human
        )
    }

    /// Milestone O: "what changed while you were away" -- resolved/still-
    /// open/blocked GapNodes since `sinceSeconds` ago, plus a pointer at
    /// how many items are waiting in the existing fact/module review
    /// queues (list_pending_ai_facts / list_pending_domain_modules).
    static func wakeSummary(sinceSeconds: Double = 43200) async -> String {
        await MCPEngine.shared.callTool(
            serverName: serverName, toolName: "wake_summary",
            arguments: ["since_seconds": sinceSeconds], mode: .human
        )
    }

    // MARK: - Milestone R4: mutating tool-call approval queue
    //
    // The Vera-harness HTTP chat path (vera_server.py -> Agent.run()) has
    // no interactive approver reachable across the request/response
    // boundary, so every mutating tool call (write_file, run_command,
    // vera_remember, vera_code_ingest, ...) gets queued instead of denied
    // -- same propose/pending/accept/reject shape as domain modules above,
    // reused rather than inventing a second mechanism. Nothing here ever
    // runs a tool automatically; accept/reject are the only two ways a
    // queued entry ever leaves "pending".

    struct PendingToolCall: Identifiable {
        let index: Int
        let callId: String
        let toolName: String
        let argsText: String     // pretty-printed JSON
        let reason: String       // the LLM's own "thought" when it proposed this call
        let task: String         // the originating chat task
        var id: Int { index }
    }

    static func listPendingToolCalls() async -> [PendingToolCall] {
        let raw = await MCPEngine.shared.callTool(
            serverName: serverName, toolName: "list_pending_tool_calls",
            arguments: [:], mode: .human
        )
        guard let data = raw.data(using: .utf8),
              let arr = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]]
        else { return [] }
        return arr.compactMap { entry in
            guard let index = entry["index"] as? Int,
                  let callId = entry["call_id"] as? String,
                  let toolName = entry["tool_name"] as? String else { return nil }
            var argsText = "{}"
            if let args = entry["args"],
               let argsData = try? JSONSerialization.data(withJSONObject: args, options: [.prettyPrinted]) {
                argsText = String(data: argsData, encoding: .utf8) ?? "{}"
            }
            let reason = (entry["reason"] as? String) ?? ""
            let task = (entry["task"] as? String) ?? ""
            return PendingToolCall(index: index, callId: callId, toolName: toolName,
                                    argsText: argsText, reason: reason, task: task)
        }
    }

    /// Actually RUNS the queued tool call now, with Vera's current state
    /// -- not a replay of state from when it was proposed. Returns the
    /// tool's own result JSON (pretty-printed) for display, or nil on
    /// failure to reach the server at all.
    static func acceptToolCall(index: Int) async -> String? {
        let raw = await MCPEngine.shared.callTool(
            serverName: serverName, toolName: "accept_tool_call",
            arguments: ["index": index], mode: .human
        )
        guard let data = raw.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) else { return nil }
        guard let pretty = try? JSONSerialization.data(withJSONObject: obj, options: [.prettyPrinted]) else { return raw }
        return String(data: pretty, encoding: .utf8) ?? raw
    }

    static func rejectToolCall(index: Int) async -> Bool {
        let raw = await MCPEngine.shared.callTool(
            serverName: serverName, toolName: "reject_tool_call",
            arguments: ["index": index], mode: .human
        )
        guard let data = raw.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return false }
        return (obj["ok"] as? Bool) ?? false
    }
}
