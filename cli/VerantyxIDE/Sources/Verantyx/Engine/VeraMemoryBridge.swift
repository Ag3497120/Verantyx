import Foundation

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
        let prompt = userPrompt.trimmingCharacters(in: .whitespacesAndNewlines)
        let response = aiResponse.trimmingCharacters(in: .whitespacesAndNewlines)
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
        return obj["url"] as? String
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
    }

    /// Every other function in this bridge that reads from Vera goes
    /// through this one call site. Shape from
    /// `verantyx.consensus.Verdict.as_dict()` via the `ask` MCP tool:
    /// {"verdict": "ANSWER"|"UNKNOWN_*", "core": str, "text": str,
    /// "agree_frac": float, ...} — verified against a live
    /// `python3.11 -m verantyx.cli mcp` process, not guessed.
    private static func askRaw(_ query: String) async -> AskResult {
        let raw = await MCPEngine.shared.callTool(
            serverName: serverName, toolName: "ask",
            arguments: ["query": query], mode: .human
        )
        guard
            let data = raw.data(using: .utf8),
            let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let verdict = obj["verdict"] as? String
        else { return AskResult(verdict: "UNKNOWN_CALL_FAILED", core: nil, text: nil, agreeFrac: nil) }

        let result = AskResult(
            verdict: verdict,
            core: obj["core"] as? String,
            text: obj["text"] as? String,
            agreeFrac: obj["agree_frac"] as? Double
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
          🧩 \(core): \(text)  (agreement: \(agreeFrac))
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

        (Vera direct answer — core: \(core), agreement: \(String(format: "%.2f", agree)) — no LLM call was made)
        """
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
    /// growth candidates only, without drafting.
    static func triggerHeartbeat(llmModel: String = "") async -> String {
        await MCPEngine.shared.callTool(
            serverName: serverName, toolName: "heartbeat",
            arguments: ["llm_model": llmModel], mode: .human
        )
    }
}
