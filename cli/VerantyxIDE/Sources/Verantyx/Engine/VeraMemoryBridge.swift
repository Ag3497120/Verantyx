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
        let raw = await MCPEngine.shared.callTool(
            serverName: serverName, toolName: "ask",
            arguments: ["query": query], mode: .human
        )
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
