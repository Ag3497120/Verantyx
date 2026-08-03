import Foundation

/// Layer 2 **act** path for jgen-vector-bus: same JGEN as the council drives
/// desktop/AX tools **without** `AgentLoop` / Nano Gatekeeper prompts.
///
/// Loop: short ChatML generate → parse one bracket tool call →
/// `AgentToolExecutor` → observation stamped onto the vector bus → repeat
/// until `[DONE: …]` or maxTurns.
///
/// Tiny models often emit one tool then prose (or a broken tag). That must
/// **not** end the loop — only `[DONE:…]` or the turn cap should.
actor JGenActAgent {
    static let shared = JGenActAgent()

    private let executor = AgentToolExecutor()

    /// Survives across chat turns so 「続けて」 can resume the same act goal.
    private var lastGoal: String = ""
    private var lastObservations: [String] = []
    /// Mission body held outside ChatML (essay / paste object). Kept on 「続けて」.
    private var lastPayload: String = ""

    private init() {}

    struct Outcome: Sendable {
        let text: String
        let turns: Int
        let toolCount: Int
    }

    func run(
        handoff: CouncilOrchestrator.Handoff,
        question: String,
        useEternalMemory: Bool,
        maxTurns: Int,
        sessionId: String?,
        workspaceURL: URL?,
        searchQuerySeed: String? = nil,
        missionPayload: String? = nil,
        onProgress: @escaping @Sendable (LoopEvent) async -> Void
    ) async -> Outcome {

        let chat = JCrossChatManager.shared
        guard await chat.isLoaded else {
            let msg = "JGEN is not loaded — cannot run jgen-only act loop."
            await onProgress(.error(msg))
            return Outcome(text: msg, turns: 0, toolCount: 0)
        }

        await onProgress(.systemLog(AppLanguage.shared.t(
            "🛠 [L2 JGEN Act] same-engine tool loop (no AgentLoop / no Nano)…",
            "🛠 [L2 JGEN操作] 同一エンジンのツールループ（AgentLoop・Nanoなし）…")))

        let sid: String
        if let sessionId, !sessionId.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            sid = sessionId
        } else if let fromApp = await MainActor.run(body: { AppState.shared?.vxChatSessionId }),
                  !fromApp.isEmpty {
            sid = fromApp
        } else {
            sid = JGenVectorBusMemory.fallbackSessionId
        }

        // Never put a multi-k essay into every act turn's [GOAL].
        let boundedQuestion = PromptBudget.truncateForModel(question)
        let continuing = Self.isContinueRequest(boundedQuestion)
        let goal: String
        var observations: [String]
        if continuing, !lastGoal.isEmpty {
            goal = lastGoal
            observations = lastObservations
            // Keep lastPayload on resume.
            await onProgress(.systemLog(AppLanguage.shared.t(
                "🔁 [L2 JGEN Act] resuming prior goal (\(observations.count) observations)…",
                "🔁 [L2 JGEN操作] 前回の目標を再開（観測 \(observations.count) 件）…")))
        } else {
            goal = boundedQuestion
            observations = []
            lastGoal = boundedQuestion
            lastObservations = []
            let incoming = missionPayload?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            if !incoming.isEmpty {
                lastPayload = incoming
            } else {
                lastPayload = PromptBudget.extractMissionPayload(from: question) ?? ""
            }
        }

        await executor.setMissionPayload(lastPayload)
        if !lastPayload.isEmpty {
            await onProgress(.systemLog(AppLanguage.shared.t(
                "📦 [L2 JGEN Act] mission payload held (\(lastPayload.count) chars, preview=\"\(PromptBudget.payloadPreview(lastPayload))\") — not embedded in ChatML.",
                "📦 [L2 JGEN操作] 任務ペイロード保持（\(lastPayload.count) 文字、preview=\"\(PromptBudget.payloadPreview(lastPayload))\"）— ChatMLには埋め込みません。")))
        }

        let requiredOpenApp = Self.extractOpenAppName(from: goal)
        let needsOpenApp = requiredOpenApp != nil || Self.goalHasOpenAppIntent(goal)
        let needsBrowser = Self.goalNeedsBrowser(goal)

        // ── Infinite exploration assets: recall prior success paths ─────────
        var narrator = ExplorationNarrator(goal: goal)
        let priorAssets = await ExplorationAssetStore.recall(for: goal, topK: 2)
        let priorAsset = priorAssets.first
        let priorAssetBlock: String? = priorAsset.map { ExplorationAssetStore.formatPriorAsset($0) }
        if let prior = priorAsset {
            await onProgress(.systemLog(narrator.recallAnnounce(skillName: prior.name)))
        }

        let system = """
        You are Verantyx's JGEN body. One complete tool tag per turn (closing ]). \
        Schema: OPEN_APP (if named) → SENSE → ACT → observe → on MISMATCH try alternate → DONE. \
        Allowed:
        [OPEN_APP: AppName]
        [DESKTOP_SNAPSHOT]
        [DESKTOP_ACT: click 120 340]
        [AX_ACT: #btn1 click]
        [PASTE_PAYLOAD]
        [WAIT_UNTIL_STABLE]
        [DONE: short status in the user's language]
        If the goal names an app, [OPEN_APP: that app] before any click. \
        SENSE with DESKTOP_SNAPSHOT/AX map. ACT with AX/click. \
        If [PAYLOAD] ready: focus an editable text field (AX preferred), then [PASTE_PAYLOAD]. \
        Never dump long text via DESKTOP_ACT type. Never invent coords. \
        Never emit literal X Y (schema placeholders). Never prose without a tag. \
        On MISMATCH / NO VISUAL CHANGE / DESKTOP_BLOCKED: try a different AX target or DONE. \
        Never repeat the same click. \
        If [PRIOR_ASSET] is present, prefer that learned tool sequence (adapt AX ids if UI shifted).
        """

        var finalAnswer = ""
        var toolCount = 0
        var identicalErrorStreak = 0
        var lastErrorFingerprint = ""
        var lastActionKey = ""
        var identicalActionStreak = 0
        /// True after a successful OPEN_APP (bootstrap or model) for this run.
        var openAppSucceeded = false
        /// Successful tool tags collected for forge-on-DONE (exploration asset).
        var successfulTags: [String] = []
        var completedWithDone = false
        // Enough steps for open → type search → read/click results → done.
        let turnsCap = max(8, min(max(maxTurns, 8), 18))

        await executor.resetLoopGuards()

        // Prefer an already-bound automation target (e.g. 「続けて」) so we
        // do not re-OPEN when the session already owns that app.
        if let required = requiredOpenApp {
            let current = await MainActor.run { HiddenWindowAutomation.shared.targetAppName }
            if Self.appNamesMatch(current, required) {
                openAppSucceeded = true
            }
        }

        // Tiny models cannot plan Safari UI. Bootstrap: open → snapshot →
        // type the user's query into the Smart Search field (⌘L) → Return →
        // snapshot again, then let the model continue (click / summarize).
        // Translate intent only reaches a named URL destination — no site-
        // specific paste/click bootstrap; the loop discovers focus + PASTE_PAYLOAD.
        //
        // Non-browser 「〜を開いて」 goals take the general OPEN_APP + SNAPSHOT
        // path below. Named Chrome/Firefox/Edge open THAT browser (never force
        // Safari). Safari Smart Search / DeepL UI is Safari-only.
        let namedBrowser = requiredOpenApp.flatMap { Self.isBrowserAppName($0) ? $0 : nil }
        let safariSearchBootstrap = needsBrowser
            && (requiredOpenApp == nil || Self.isSafariFamilyBrowser(namedBrowser ?? ""))
        if toolCount == 0, safariSearchBootstrap {
            let browserName = namedBrowser ?? "Safari"
            toolCount = await Self.runBootstrapTool(
                .openApp(name: browserName),
                label: "bootstrapping [OPEN_APP: \(browserName)]…",
                labelJA: "先に [OPEN_APP: \(browserName)] を実行…",
                executor: executor,
                workspaceURL: workspaceURL,
                sessionId: sid,
                observations: &observations,
                toolCount: toolCount,
                onProgress: onProgress
            )
            lastObservations = observations
            if Self.observationLooksLikeOpenSuccess(observations.last) {
                openAppSucceeded = true
            }

            toolCount = await Self.runBootstrapTool(
                .desktopSnapshot,
                label: "bootstrapping [DESKTOP_SNAPSHOT]…",
                labelJA: "先に [DESKTOP_SNAPSHOT] を実行…",
                executor: executor,
                workspaceURL: workspaceURL,
                sessionId: sid,
                observations: &observations,
                toolCount: toolCount,
                onProgress: onProgress
            )
            lastObservations = observations

            // Prefer seed from original paste (intent line in head *or* tail),
            // not the middle-truncated goal — essays often precede 「Safariで…」.
            let seed = searchQuerySeed?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            let querySource = seed.isEmpty ? goal : seed
            let translate = PromptBudget.isTranslateIntent(querySource)
                || PromptBudget.isTranslateIntent(goal)

            if translate {
                // Named destination only: open translator URL. Autonomous loop
                // must discover the editable field and emit PASTE_PAYLOAD.
                let url = PromptBudget.deepLTranslatorURL
                await onProgress(.systemLog(AppLanguage.shared.t(
                    "🛠 [L2 JGEN Act] translate intent → navigating Safari to \(url)…",
                    "🛠 [L2 JGEN操作] 翻訳意図 → Safari で \(url) を開く…")))
                let opened = await HiddenWindowAutomation.shared.openURLInTargetBrowser(url)
                toolCount += 1
                observations.append(Self.stampObservation(
                    toolLabel: "navigate",
                    result: opened,
                    selfAction: "navigate \(url)"
                ))
                lastObservations = observations
                await onProgress(.systemLog(opened))
                await JGenVectorBusMemory.stampObservation(
                    label: "jgen_act",
                    detail: "navigate → \(opened)",
                    sessionId: sid,
                    stepIndex: toolCount,
                    actionLabel: "navigate",
                    changedRegion: nil,
                    concepts: ["ui-observe", "bug-repro", "jgen-act", "translate", "deepl"]
                )

                toolCount = await Self.runBootstrapTool(
                    .desktopSnapshot,
                    label: "snapshot after named-destination navigate…",
                    labelJA: "到達後に [DESKTOP_SNAPSHOT]…",
                    executor: executor,
                    workspaceURL: workspaceURL,
                    sessionId: sid,
                    observations: &observations,
                    toolCount: toolCount,
                    onProgress: onProgress
                )
                lastObservations = observations
            } else if Self.goalNeedsWebSearch(goal) || Self.goalNeedsWebSearch(querySource) {
                let query = PromptBudget.capSearchQuery(Self.searchQuery(from: querySource))
                // URL-shaped queries (e.g. deepl.com/…) navigate; else type search.
                if Self.looksLikeURL(query) {
                    await onProgress(.systemLog(AppLanguage.shared.t(
                        "🛠 [L2 JGEN Act] navigating Safari → \(query)…",
                        "🛠 [L2 JGEN操作] Safari で \(query) を開く…")))
                    let opened = await HiddenWindowAutomation.shared.openURLInTargetBrowser(query)
                    toolCount += 1
                    observations.append(Self.stampObservation(
                        toolLabel: "navigate",
                        result: opened,
                        selfAction: "navigate \(query)"
                    ))
                    lastObservations = observations
                    await onProgress(.systemLog(opened))
                    await JGenVectorBusMemory.stampObservation(
                        label: "jgen_act",
                        detail: "navigate → \(opened)",
                        sessionId: sid,
                        stepIndex: toolCount,
                        actionLabel: "navigate",
                        changedRegion: nil,
                        concepts: ["ui-observe", "bug-repro", "jgen-act", "web-nav"]
                    )
                } else {
                    await onProgress(.systemLog(AppLanguage.shared.t(
                        "🛠 [L2 JGEN Act] typing search query into Safari: \"\(query)\"…",
                        "🛠 [L2 JGEN操作] Safari の検索欄に「\(query)」と入力…")))
                    let typed = await HiddenWindowAutomation.shared.focusAddressBarAndSearch(query)
                    toolCount += 1
                    observations.append(Self.stampObservation(
                        toolLabel: "search_bar",
                        result: typed,
                        selfAction: "search_bar"
                    ))
                    lastObservations = observations
                    await onProgress(.systemLog(typed))
                    await JGenVectorBusMemory.stampObservation(
                        label: "jgen_act",
                        detail: "search_bar → \(typed)",
                        sessionId: sid,
                        stepIndex: toolCount,
                        actionLabel: "search_bar",
                        changedRegion: nil,
                        concepts: ["ui-observe", "bug-repro", "jgen-act", "web-search"]
                    )
                }

                toolCount = await Self.runBootstrapTool(
                    .desktopSnapshot,
                    label: "snapshot after search…",
                    labelJA: "検索後に [DESKTOP_SNAPSHOT]…",
                    executor: executor,
                    workspaceURL: workspaceURL,
                    sessionId: sid,
                    observations: &observations,
                    toolCount: toolCount,
                    onProgress: onProgress
                )
                lastObservations = observations
            }
        } else if toolCount == 0, let appName = requiredOpenApp {
            // General substrate: open the named app → sense → then model acts.
            // Do not hardcode in-app navigation (Teams issues, Slack channels, …).
            if !openAppSucceeded {
                toolCount = await Self.runBootstrapTool(
                    .openApp(name: appName),
                    label: "bootstrapping [OPEN_APP: \(appName)]…",
                    labelJA: "先に [OPEN_APP: \(appName)] を実行…",
                    executor: executor,
                    workspaceURL: workspaceURL,
                    sessionId: sid,
                    observations: &observations,
                    toolCount: toolCount,
                    onProgress: onProgress
                )
                lastObservations = observations
                if Self.observationLooksLikeOpenSuccess(observations.last) {
                    openAppSucceeded = true
                }
            }

            let alreadySnapshotted = observations.contains {
                $0.contains("desktop_snapshot") || $0.contains("DESKTOP_SNAPSHOT")
                    || $0.contains("UI MAP") || $0.localizedCaseInsensitiveContains("semantic")
            }
            if !alreadySnapshotted {
                toolCount = await Self.runBootstrapTool(
                    .desktopSnapshot,
                    label: "bootstrapping [DESKTOP_SNAPSHOT]…",
                    labelJA: "先に [DESKTOP_SNAPSHOT] を実行…",
                    executor: executor,
                    workspaceURL: workspaceURL,
                    sessionId: sid,
                    observations: &observations,
                    toolCount: toolCount,
                    onProgress: onProgress
                )
                lastObservations = observations
            }
        }

        // Seed exploration path with bootstrap successes (open / snapshot).
        if openAppSucceeded {
            let appName = requiredOpenApp
                ?? (safariSearchBootstrap ? (namedBrowser ?? "Safari") : nil)
            if let appName {
                let openTag = "[OPEN_APP: \(appName)]"
                if !successfulTags.contains(openTag) {
                    successfulTags.append(openTag)
                }
            }
        }
        let bootSnap = observations.contains {
            $0.contains("desktop_snapshot") || $0.contains("DESKTOP_SNAPSHOT")
                || $0.contains("UI MAP") || $0.localizedCaseInsensitiveContains("semantic")
        }
        if bootSnap, !successfulTags.contains("[DESKTOP_SNAPSHOT]") {
            successfulTags.append("[DESKTOP_SNAPSHOT]")
        }

        for turn in 1...turnsCap {
            let memory = await JGenVectorBusMemory.recallBundle(
                for: goal, sessionId: sid, useEternal: useEternalMemory, k: 3
            )
            var userParts: [String] = []
            if !memory.isEmpty { userParts.append(memory) }
            let councilLine = handoff.conclusion.trimmingCharacters(in: .whitespacesAndNewlines)
            if councilLine.count > 2, !JGenSpeakActRouter.isLowSignalHandoff(handoff) {
                userParts.append("[COUNCIL]\n\(councilLine)")
            }
            if !handoff.detail.isEmpty, !JCrossChatManager.isPhraseLooping(handoff.detail),
               handoff.detail.count > 8 {
                userParts.append("[DETAIL]\n\(JCrossChatManager.collapsePhraseRepetition(handoff.detail))")
            }
            userParts.append("[GOAL]\n\(goal)")
            if let priorBlock = priorAssetBlock {
                userParts.append(priorBlock)
            }
            if !lastPayload.isEmpty {
                let preview = PromptBudget.payloadPreview(lastPayload)
                userParts.append(
                    "[PAYLOAD] ready chars=\(lastPayload.count) preview=\"\(preview)\" — after focusing a text field, emit [PASTE_PAYLOAD]"
                )
            }
            if continuing {
                userParts.append("[NOTE]\nUser asked to continue the unfinished desktop task.")
            }
            if !observations.isEmpty {
                let recent = observations.suffix(6).joined(separator: "\n---\n")
                userParts.append("[OBSERVATIONS]\n\(recent)")
            }
            let hint: String
            let payloadReady = !lastPayload.isEmpty
            let recentJoined = observations.suffix(4).joined(separator: "\n")
            let sawNavigateOrSnap = recentJoined.contains("navigate")
                || recentJoined.contains("desktop_snapshot")
                || recentJoined.contains("DESKTOP_SNAPSHOT")
                || recentJoined.localizedCaseInsensitiveContains("semantic")
                || recentJoined.contains("UI MAP")
            if let priorHint = ExplorationAssetStore.hintFromPriorAsset(priorAsset),
               turn <= 3, openAppSucceeded || !needsOpenApp {
                hint = priorHint
            } else if !openAppSucceeded, needsOpenApp || needsBrowser {
                let appHint = requiredOpenApp
                    ?? (needsBrowser ? "Safari" : "AppName")
                hint = "First required tag is [OPEN_APP: \(appHint)]. Do not click yet."
            } else if observations.last?.localizedCaseInsensitiveContains("opened") == true
                        || observations.last?.localizedCaseInsensitiveContains("open_app") == true
                        || observations.last?.contains("open -a") == true {
                hint = "Next required tag is [DESKTOP_SNAPSHOT]."
            } else if payloadReady, sawNavigateOrSnap,
                      !observations.contains(where: { $0.contains("paste_payload") || $0.contains("PASTE_PAYLOAD") }) {
                hint = "PAYLOAD ready. Focus an editable text field via [AX_ACT: … click] (or click), then [PASTE_PAYLOAD]. Do not type the body via DESKTOP_ACT."
            } else if observations.contains(where: { $0.contains("search_bar") }) {
                hint = "Search was typed. Click a relevant result, take [DESKTOP_SNAPSHOT], or [DONE: short summary of what you see]."
            } else if observations.last?.localizedCaseInsensitiveContains("NO VISUAL CHANGE") == true
                        || observations.last?.localizedCaseInsensitiveContains("DESKTOP_BLOCKED") == true
                        || observations.last?.contains("MISMATCH") == true {
                hint = "MISMATCH — do NOT repeat. Prefer a different [AX_ACT: …] target, [DESKTOP_SNAPSHOT], or [DONE: …]."
            } else if observations.last?.localizedCaseInsensitiveContains("NO SCREENSHOT") == true
                        || observations.last.map(ScreenCapturePermission.looksLikeDenied) == true {
                hint = "Screenshot blocked. Prefer [AX_ACT: …] or [DONE: …]. Do not repeat the same click."
            } else {
                hint = "Emit one valid NEW tool tag, or [DONE: …] if finished. Never repeat a previous click."
            }
            userParts.append("Turn \(turn)/\(turnsCap). \(hint)")

            // Occasional 現状説明 / 独り言 (same channel as Act systemLog).
            let lastObs = observations.last
            let mismatchNow = lastObs.map { ExplorationAssetStore.looksLikeFailure($0) } ?? false
            if let status = narrator.statusIfDue(
                turn: turn,
                openAppSucceeded: openAppSucceeded,
                appHint: requiredOpenApp,
                lastObservation: lastObs,
                force: mismatchNow && turn > 1
            ) {
                await onProgress(.systemLog(status))
            }
            if let mutter = narrator.mutterIfDue(
                turn: turn,
                hadMismatch: mismatchNow,
                hadPriorAsset: priorAsset != nil,
                force: false
            ) {
                await onProgress(.systemLog(mutter))
            }

            let conversation: [(role: String, content: String)] = [
                ("system", system),
                ("user", userParts.joined(separator: "\n\n"))
            ]

            let raw: String
            do {
                var streamed = ""
                raw = try await chat.generateStreaming(
                    conversation: conversation,
                    maxTokens: 96
                ) { delta in
                    streamed += delta
                    Task { await onProgress(.streamToken(delta)) }
                    // Stop early once a complete tag is visible — cuts off
                    // trailing junk from 0.5B models.
                    if Self.hasCompleteToolTag(streamed) { return false }
                    if JCrossChatManager.isPhraseLooping(streamed) { return false }
                    return true
                }
            } catch {
                let msg = "JGEN act generate failed: \(error.localizedDescription)"
                await onProgress(.error(msg))
                lastObservations = observations
                return Outcome(text: msg, turns: turn, toolCount: toolCount)
            }

            let cleaned = JCrossChatManager.collapsePhraseRepetition(
                raw.trimmingCharacters(in: .whitespacesAndNewlines)
            )
            let repaired = Self.repairLooseToolTags(cleaned)
            let tools = Self.filterAllowed(AgentToolParser.parse(from: repaired).toolCalls)

            if tools.isEmpty {
                // Already ran tools: do not treat prose / broken tags as DONE.
                if toolCount > 0 {
                    observations.append(
                        "(turn \(turn) invalid tool `\(String(cleaned.prefix(100)))` — need a complete [TAG: …])"
                    )
                    lastObservations = observations
                    continue
                }
                if !cleaned.isEmpty, !JCrossChatManager.isPhraseLooping(cleaned),
                   !Self.looksLikeToolAttempt(cleaned) {
                    // Pure first-turn prose with no tool attempt — soft fail into nudge.
                    observations.append("(turn \(turn) prose without tool — retrying)")
                    lastObservations = observations
                    continue
                }
                observations.append("(turn \(turn) no tool parsed)")
                lastObservations = observations
                continue
            }

            let tool = tools[0]
            if case .done(let message) = tool {
                finalAnswer = JCrossChatManager.collapsePhraseRepetition(message)
                completedWithDone = true
                break
            }

            // Reject schema-placeholder clicks (literal X Y) — never execute.
            if case .desktopAct(let action) = tool, Self.isPlaceholderDesktopAct(action) {
                let appHint = requiredOpenApp ?? (needsBrowser ? "Safari" : nil)
                let nudge = appHint.map { " Prefer [OPEN_APP: \($0)] then [DESKTOP_SNAPSHOT]/[AX_ACT]." }
                    ?? " Prefer [OPEN_APP]/[DESKTOP_SNAPSHOT]/[AX_ACT]; never invent coords."
                observations.append(
                    "(rejected placeholder DESKTOP_ACT `\(action)` — literal X/Y are not coordinates.\(nudge))"
                )
                lastObservations = observations
                continue
            }

            // Refuse DESKTOP_ACT before OPEN_APP when the goal requires opening an app.
            if case .desktopAct = tool, !openAppSucceeded, needsOpenApp || needsBrowser {
                let appHint = requiredOpenApp ?? (needsBrowser ? "Safari" : "AppName")
                observations.append("(blocked DESKTOP_ACT before OPEN_APP — open \(appHint) first)")
                lastObservations = observations
                continue
            }

            let actionKey = Self.actionKey(tool)
            if !actionKey.isEmpty, actionKey == lastActionKey {
                identicalActionStreak += 1
            } else {
                identicalActionStreak = 1
                lastActionKey = actionKey
            }
            if identicalActionStreak >= 2 {
                observations.append(
                    "(blocked repeated action \(actionKey) ×\(identicalActionStreak) — try a different tool or DONE)"
                )
                lastObservations = observations
                if identicalActionStreak >= 3 {
                    finalAnswer = AppLanguage.shared.t(
                        "Stopped: the model kept repeating \(actionKey). Open the hidden-window mirror to continue manually, or retry with a larger JGEN.",
                        "停止: モデルが \(actionKey) を繰り返し続けました。隠れ窓ミラーで手動継続するか、より大きな JGEN で再試行してください。"
                    )
                    break
                }
                continue
            }

            let call = AgentToolCall(tool: tool)
            await onProgress(.toolCall(call))
            let result = await executor.execute(tool, workspaceURL: workspaceURL)
            toolCount += 1
            let trimmed = result.count > 1500 ? String(result.prefix(1500)) + "…" : result
            let stamped = Self.stampObservation(
                toolLabel: call.displayLabel,
                result: trimmed,
                selfAction: call.displayLabel
            )
            observations.append(stamped)
            lastObservations = observations
            if case .openApp = tool, Self.observationLooksLikeOpenSuccess(observations.last) {
                openAppSucceeded = true
            }
            await onProgress(.toolResult(AgentToolCall(tool: tool, result: trimmed, succeeded: !result.contains("ERROR"))))

            // Exploration asset: log failures; collect successful tags for forge-on-DONE.
            if ExplorationAssetStore.looksLikeFailure(stamped) {
                await ExplorationAssetStore.logFailure(
                    goal: goal,
                    actionTried: call.displayLabel,
                    result: trimmed,
                    turn: turn,
                    sessionId: sid
                )
                await onProgress(.systemLog(narrator.failAnnounce(action: call.displayLabel)))
                if let mutter = narrator.mutterIfDue(
                    turn: turn,
                    hadMismatch: true,
                    hadPriorAsset: priorAsset != nil,
                    force: true
                ) {
                    await onProgress(.systemLog(mutter))
                }
            } else if let tag = ExplorationAssetStore.toolTag(tool) {
                if !successfulTags.contains(tag) {
                    successfulTags.append(tag)
                }
            }

            await JGenVectorBusMemory.stampObservation(
                label: "jgen_act",
                detail: "\(call.displayLabel) → \(String(trimmed.prefix(500)))",
                sessionId: sid,
                stepIndex: toolCount,
                actionLabel: call.displayLabel,
                changedRegion: nil,
                concepts: ["ui-observe", "bug-repro", "jgen-act"]
            )

            // Stop hammering the same failing click when Screen Recording TCC is dead.
            if ScreenCapturePermission.looksLikeDenied(trimmed),
               trimmed.localizedCaseInsensitiveContains("DESKTOP ERROR") {
                finalAnswer = AppLanguage.shared.t(
                    "Stopped: Screen Recording permission is not active for this Verantyx process.\n\n\(ScreenCapturePermission.recoveryMessage)",
                    "中断: この Verantyx プロセスに画面収録権限が付与されていません。\n\n\(ScreenCapturePermission.recoveryMessage)"
                )
                await MainActor.run { ScreenCapturePermission.openSystemSettings() }
                break
            }

            let fingerprint = Self.errorFingerprint(trimmed)
            if !fingerprint.isEmpty {
                if fingerprint == lastErrorFingerprint {
                    identicalErrorStreak += 1
                } else {
                    identicalErrorStreak = 1
                    lastErrorFingerprint = fingerprint
                }
                if identicalErrorStreak >= 2 {
                    finalAnswer = AppLanguage.shared.t(
                        "Stopped repeating the same failing action (\(identicalErrorStreak)×). Last error:\n\(String(trimmed.prefix(500)))\n\nSay 「続けて」 after changing strategy, or use a larger JGEN.",
                        "同じ失敗操作を \(identicalErrorStreak) 回繰り返したため停止しました。最後のエラー:\n\(String(trimmed.prefix(500)))\n\n方針を変えて「続けて」か、より大きな JGEN を使ってください。"
                    )
                    break
                }
            } else {
                identicalErrorStreak = 0
                lastErrorFingerprint = ""
            }
        }

        if finalAnswer.isEmpty {
            finalAnswer = observations.last.map {
                "Act loop paused after \(toolCount) tools (say 「続けて」 to resume). Last: \(String($0.prefix(400)))"
            } ?? (handoff.detail.isEmpty ? handoff.asText : handoff.detail)
            finalAnswer = JCrossChatManager.collapsePhraseRepetition(finalAnswer)
        } else {
            // Completed with DONE — clear continuation buffer.
            lastGoal = ""
            lastObservations = []
            lastPayload = ""
            await executor.clearMissionPayload()
        }

        // Forge exploration asset on clear DONE success (or open + useful progress + DONE).
        if completedWithDone, !successfulTags.isEmpty {
            // Include bootstrap opens/snaps already in observations if missing from tags.
            if openAppSucceeded, let app = requiredOpenApp {
                let openTag = "[OPEN_APP: \(app)]"
                if !successfulTags.contains(where: { $0.hasPrefix("[OPEN_APP:") }) {
                    successfulTags.insert(openTag, at: 0)
                }
            }
            if let forged = await ExplorationAssetStore.forgeOnSuccess(
                goal: goal,
                appHint: requiredOpenApp,
                successfulTags: successfulTags,
                notes: String(finalAnswer.prefix(120))
            ) {
                await onProgress(.systemLog(narrator.forgeAnnounce(skillName: forged.name)))
                if let prior = priorAsset, prior.name == forged.name {
                    await SkillLibrary.shared.recordSuccess(name: forged.name)
                }
            }
        }

        if useEternalMemory, !finalAnswer.isEmpty, !JCrossChatManager.isPhraseLooping(finalAnswer) {
            let stamp = "Q: \(goal.prefix(120))\nA: \(finalAnswer.prefix(400))"
            try? await EternalMemoryStore.shared.add(text: String(stamp), concepts: ["jgen-act", "bug-repro"])
        }

        await onProgress(.done(message: finalAnswer, workspace: workspaceURL))
        return Outcome(text: finalAnswer, turns: min(turnsCap, max(toolCount, 1)), toolCount: toolCount)
    }

    /// Lightweight causal labels on observation strings for the next turn.
    nonisolated static func stampObservation(
        toolLabel: String,
        result: String,
        selfAction: String
    ) -> String {
        let upper = result.uppercased()
        let isError = upper.contains("ERROR") || upper.contains("BLOCKED")
            || upper.contains("NO VISUAL CHANGE") || upper.contains("FAILED")
        let external: String
        if result.contains("SEMANTIC UI MAP") || result.localizedCaseInsensitiveContains("UI MAP") {
            external = "EXTERNAL_CHANGE: AX/UI map updated"
        } else if result.contains("screenshot") || result.contains("Screenshot")
                    || result.contains("mirror") {
            external = "EXTERNAL_CHANGE: screen refreshed"
        } else if result.hasPrefix("✓") || upper.contains("PASTED") || upper.contains("OPENED") {
            external = "EXTERNAL_CHANGE: ok"
        } else {
            external = "EXTERNAL_CHANGE: observed"
        }
        if isError {
            return "SELF_ACTION: \(selfAction)\nMISMATCH: \(result)\nRESULT: \(toolLabel) → \(result)"
        }
        return "SELF_ACTION: \(selfAction)\n\(external)\nRESULT: \(toolLabel) → \(result)"
    }

    private static func filterAllowed(_ tools: [AgentTool]) -> [AgentTool] {
        tools.filter { tool in
            switch tool {
            case .openApp, .desktopSnapshot, .desktopAct, .axAct, .pastePayload, .waitUntilStable, .done:
                return true
            default:
                return false
            }
        }
    }

    nonisolated static func isContinueRequest(_ question: String) -> Bool {
        let t = question.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let keys = ["続けて", "つづけて", "続行", "再開", "continue", "keep going", "resume", "次へ", "つづき"]
        return keys.contains { t == $0 || t.hasPrefix($0) }
    }

    nonisolated static func goalNeedsBrowser(_ goal: String) -> Bool {
        let t = goal.lowercased()
        let keys = [
            "safari", "ブラウザ", "chrome", "firefox", "ニュース", "news",
            "検索", "search", "web", "url", "http",
            "deepl", "翻訳", "translate", "英訳", "和訳",
        ]
        return keys.contains { t.contains($0) }
    }

    /// True when the goal asks to open/launch something (even if we cannot
    /// yet resolve a concrete `.app` name).
    nonisolated static func goalHasOpenAppIntent(_ goal: String) -> Bool {
        let t = goal.lowercased()
        let keys = [
            "開いて", "開け", "起動", "立ち上げ",
            "open ", "open\t", "launch ", "start ",
        ]
        return keys.contains { t.contains($0) }
    }

    /// Browser bundle names (any vendor) — used to classify a resolved OPEN_APP.
    nonisolated static func isBrowserAppName(_ name: String) -> Bool {
        let n = name.lowercased()
        return n == "safari" || n == "chrome" || n == "google chrome"
            || n == "firefox" || n == "microsoft edge" || n == "edge"
            || n.contains("browser") || n == "ブラウザ"
    }

    /// Safari (only) gets Smart Search / DeepL address-bar bootstrap UI.
    /// Named Chrome/Firefox/Edge use the general OPEN_APP + SNAPSHOT path.
    nonisolated static func isSafariFamilyBrowser(_ name: String) -> Bool {
        let n = name.lowercased()
        return n == "safari" || n == "ブラウザ"
    }

    nonisolated static func appNamesMatch(_ a: String?, _ b: String) -> Bool {
        guard let a, !a.isEmpty else { return false }
        let x = a.lowercased()
        let y = b.lowercased()
        return x == y || x.contains(y) || y.contains(x)
    }

    nonisolated static func observationLooksLikeOpenSuccess(_ obs: String?) -> Bool {
        guard let obs else { return false }
        let u = obs.uppercased()
        if u.contains("MISMATCH") || u.contains("ERROR") || u.contains("COULD NOT") { return false }
        return u.contains("OPENED") || u.contains("OPEN_APP") || obs.contains("open -a")
            || u.contains("FRONTMOST")
    }

    /// Literal schema placeholders / non-numeric click targets from tiny models.
    nonisolated static func isPlaceholderDesktopAct(_ action: String) -> Bool {
        let a = action.trimmingCharacters(in: .whitespacesAndNewlines)
        let lower = a.lowercased()
        // Exact schema echo: "click X Y" / "click x y"
        if lower.range(of: #"^click\s+[xy]\s+[xy]\b"#, options: .regularExpression) != nil {
            return true
        }
        if lower.range(of: #"^click\s+[xy]\b"#, options: .regularExpression) != nil {
            return true
        }
        guard lower.hasPrefix("click") else { return false }
        let parts = a.split(whereSeparator: { $0.isWhitespace }).map(String.init)
        guard parts.count >= 3 else { return true }
        // Require real numbers — reject "click foo bar", "click X 100", etc.
        return Double(parts[1]) == nil || Double(parts[2]) == nil
    }

    /// Pull a concrete app name from 「Notionを開いて…」 / 「open Spotify and…」.
    /// Returns a resolved installed `.app` name only when one exists on disk.
    nonisolated static func extractOpenAppName(from goal: String) -> String? {
        let intent = PromptBudget.extractTaskIntentLine(from: goal) ?? goal
        let clipped = PromptBudget.truncateForModel(intent, maxChars: 240, headChars: 180, tailChars: 40)
        var candidates: [String] = []

        // Japanese: Appを開いて / 開く / 起動 / 起動して / 立ち上げ / 立ち上げて
        if let re = try? NSRegularExpression(
            pattern: #"([A-Za-z0-9][A-Za-z0-9 .+\-]{0,40}?|[一-龯ぁ-んァ-ヶー]{2,20})を(?:開いて|開け|開く|起動して|起動|立ち上げて|立ち上げ)"#,
            options: []
        ) {
            let ns = clipped as NSString
            let matches = re.matches(in: clipped, options: [], range: NSRange(location: 0, length: ns.length))
            for m in matches where m.numberOfRanges >= 2 {
                let raw = ns.substring(with: m.range(at: 1))
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                if !raw.isEmpty { candidates.append(raw) }
            }
        }

        // Japanese loose: App 起動して / App起動 (optional を + whitespace)
        if candidates.isEmpty {
            if let re = try? NSRegularExpression(
                // Exclude particles を/は/が/の from the JP name class so we
                // never capture 「メモ帳を」 as the token.
                pattern: #"([A-Za-z][A-Za-z0-9 .+\-]{1,40}?|[一-龯ぁ-んァ-ヶー&&[^をはがのにへでも]]{2,20})\s*(?:を\s*)?(?:起動して|起動|立ち上げて|立ち上げ|開いて|開く)"#,
                options: []
            ) {
                let ns = clipped as NSString
                let matches = re.matches(in: clipped, options: [], range: NSRange(location: 0, length: ns.length))
                for m in matches where m.numberOfRanges >= 2 {
                    let raw = ns.substring(with: m.range(at: 1))
                        .trimmingCharacters(in: .whitespacesAndNewlines)
                    if !raw.isEmpty { candidates.append(raw) }
                }
            }
        }

        // English: open/launch/start [the] AppName (stop before and/then/…)
        if let re = try? NSRegularExpression(
            pattern: #"(?i)\b(?:open|launch|start)\s+(?:the\s+)?([A-Za-z][A-Za-z0-9+\-]*(?:\s+(?!and\b|then\b|to\b|for\b|with\b)[A-Za-z][A-Za-z0-9+\-]*){0,3})(?=\s+(?:and|then|to|for|with)\b|\s*[,.!?]|\s*$)"#,
            options: []
        ) {
            let ns = clipped as NSString
            let matches = re.matches(in: clipped, options: [], range: NSRange(location: 0, length: ns.length))
            for m in matches where m.numberOfRanges >= 2 {
                let raw = ns.substring(with: m.range(at: 1))
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                if !raw.isEmpty { candidates.append(raw) }
            }
        }

        // Loose: leading token + で (Safariで検索 / Chromeで…) — open-intent or browser word.
        if candidates.isEmpty, goalHasOpenAppIntent(clipped) || goalNeedsBrowser(clipped) {
            if let re = try? NSRegularExpression(
                pattern: #"^([A-Za-z][A-Za-z0-9 .+\-]{1,30}?|[一-龯ぁ-んァ-ヶー]{2,20})で"#,
                options: []
            ) {
                let ns = clipped as NSString
                if let m = re.firstMatch(in: clipped, options: [], range: NSRange(location: 0, length: ns.length)),
                   m.numberOfRanges >= 2 {
                    candidates.append(ns.substring(with: m.range(at: 1)))
                }
            }
        }

        let stop: Set<String> = [
            "app", "apps", "アプリ", "application", "the", "a", "an",
            "window", "ウィンドウ", "desktop", "デスクトップ",
            "please", "it", "this", "that", "recent", "最近",
            "これ", "それ", "あれ", "何か", "なにか",
        ]

        for raw in candidates {
            var token = raw.trimmingCharacters(in: CharacterSet(charactersIn: "「」『』\"'"))
                .trimmingCharacters(in: .whitespacesAndNewlines)
            // Strip trailing JP particles if a loose pattern ate them.
            while let last = token.last, "をはがのにへでも".contains(last) {
                token.removeLast()
            }
            token = token.trimmingCharacters(in: .whitespacesAndNewlines)
            guard token.count >= 2 else { continue }
            if stop.contains(token.lowercased()) { continue }
            if let resolved = Self.resolveExistingAppName(token) {
                return resolved
            }
        }
        return nil
    }

    /// Resolve against installed apps (cached Applications scan + thin aliases).
    /// Returns nil when nothing installed matches — never bootstrap a bad name.
    nonisolated static func resolveExistingAppName(_ input: String) -> String? {
        AgentToolParser.resolveInstalledAppName(input)
    }

    nonisolated static func applicationExists(_ name: String) -> Bool {
        AgentToolParser.resolveInstalledAppName(name) != nil
    }

    nonisolated static func goalNeedsWebSearch(_ goal: String) -> Bool {
        // Translate is handled by DeepL URL navigation, not Smart Search.
        if PromptBudget.isTranslateIntent(goal) { return false }
        let t = goal.lowercased()
        return t.contains("ニュース") || t.contains("news")
            || t.contains("検索") || t.contains("search")
            || t.contains("調べ") || t.contains("look up") || t.contains("google")
    }

    nonisolated static func looksLikeURL(_ text: String) -> Bool {
        let t = text.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return t.hasPrefix("http://") || t.hasPrefix("https://")
            || t.hasPrefix("www.")
            || t.contains(".com/") || t.contains(".co.jp/")
    }

    /// Derive what to type into Safari's Smart Search field from the user goal.
    /// Must stay tiny and task-shaped — never the essay body after 「下記を」.
    nonisolated static func searchQuery(from goal: String) -> String {
        if PromptBudget.isTranslateIntent(goal) {
            return PromptBudget.deepLTranslatorURL
        }

        // Prefer a short imperative line over the raw (possibly essay) blob.
        let intent = PromptBudget.extractTaskIntentLine(from: goal)
            ?? PromptBudget.searchSeed(from: goal)
        var t = intent.trimmingCharacters(in: .whitespacesAndNewlines)

        // Strip known *prefixes* only — never global replace of "して" (that
        // mutilates Japanese essay bodies and still leaves thousands of chars).
        let prefixStrips: [String] = [
            "Safariを開いて", "safariを開いて", "Safariで", "safariで",
            "ブラウザを開いて", "ブラウザで",
            "open safari and ", "open safari ", "please ",
            "search for ", "search ",
        ]
        for s in prefixStrips {
            if t.lowercased().hasPrefix(s.lowercased()) {
                t = String(t.dropFirst(s.count))
                    .trimmingCharacters(in: .whitespacesAndNewlines)
            }
        }
        // Trailing polite / imperative endings (once, at end).
        let suffixStrips = ["してください", "してくれ", "検索して", "調べて", "して", "を開いて", "開いて"]
        for s in suffixStrips {
            if t.hasSuffix(s) {
                t = String(t.dropLast(s.count))
                    .trimmingCharacters(in: .whitespacesAndNewlines)
            }
        }
        while t.hasPrefix("を") || t.hasPrefix("で") || t.hasPrefix("の") {
            t = String(t.dropFirst()).trimmingCharacters(in: .whitespacesAndNewlines)
        }

        // Drop everything after 「下記を」 / "the following" — that is the essay body.
        for marker in ["下記を", "以下を", "次を", "the following", "下記の", "以下の"] {
            if let range = t.range(of: marker, options: .caseInsensitive) {
                t = String(t[..<range.lowerBound])
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                break
            }
        }

        if t.isEmpty || t == "ニュース" || t.lowercased() == "news" {
            return goal.contains("ニュース") || goal.contains("今日") ? "今日のニュース" : "today's news"
        }
        if t == "ニュースを" || (t.hasSuffix("ニュース") && t.count <= 8) {
            return "今日のニュース"
        }
        // DeepL without full translate phrasing still in the seed.
        if t.lowercased().contains("deepl") {
            return PromptBudget.deepLTranslatorURL
        }
        return PromptBudget.capSearchQuery(t)
    }

    nonisolated static func actionKey(_ tool: AgentTool) -> String {
        switch tool {
        case .desktopAct(let action):
            return "desktop_act:\(action.trimmingCharacters(in: .whitespacesAndNewlines).lowercased())"
        case .openApp(let name):
            return "open_app:\(name.lowercased())"
        case .desktopSnapshot:
            return "desktop_snapshot"
        case .axAct(let action):
            return "ax_act:\(action)"
        case .pastePayload:
            return "paste_payload"
        default:
            return ""
        }
    }

    private static func runBootstrapTool(
        _ tool: AgentTool,
        label: String,
        labelJA: String,
        executor: AgentToolExecutor,
        workspaceURL: URL?,
        sessionId: String,
        observations: inout [String],
        toolCount: Int,
        onProgress: @escaping @Sendable (LoopEvent) async -> Void
    ) async -> Int {
        let call = AgentToolCall(tool: tool)
        await onProgress(.systemLog(AppLanguage.shared.t(
            "🛠 [L2 JGEN Act] \(label)",
            "🛠 [L2 JGEN操作] \(labelJA)")))
        await onProgress(.toolCall(call))
        let result = await executor.execute(tool, workspaceURL: workspaceURL)
        let next = toolCount + 1
        let trimmed = result.count > 1500 ? String(result.prefix(1500)) + "…" : result
        observations.append(stampObservation(
            toolLabel: call.displayLabel,
            result: trimmed,
            selfAction: call.displayLabel
        ))
        await onProgress(.toolResult(AgentToolCall(tool: tool, result: trimmed, succeeded: !result.contains("ERROR"))))
        await JGenVectorBusMemory.stampObservation(
            label: "jgen_act",
            detail: "\(call.displayLabel) → \(String(trimmed.prefix(500)))",
            sessionId: sessionId,
            stepIndex: next,
            actionLabel: call.displayLabel,
            changedRegion: nil,
            concepts: ["ui-observe", "bug-repro", "jgen-act"]
        )
        return next
    }

    /// Collapse retryable failure text so identical spam can be detected.
    nonisolated static func errorFingerprint(_ text: String) -> String {
        let u = text.lowercased()
        guard u.contains("error") || u.contains("no screenshot") || u.contains("blocked")
                || u.contains("no visual change")
                || ScreenCapturePermission.looksLikeDenied(text) else {
            return ""
        }
        // Keep action + error class, drop volatile suffixes.
        let clipped = String(text.prefix(180))
            .replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
        return clipped
    }

    nonisolated static func hasCompleteToolTag(_ text: String) -> Bool {
        let patterns = [
            #"\[OPEN_APP:\s*[^\]]+\]"#,
            #"\[DESKTOP_SNAPSHOT\]"#,
            #"\[DESKTOP_ACT:\s*[^\]]+\]"#,
            #"\[AX_ACT:\s*[^\]]+\]"#,
            #"\[PASTE_PAYLOAD:?\s*\]"#,
            #"\[WAIT_UNTIL_STABLE(?::[^\]]*)?\]"#,
            #"\[DONE[:\s]*[^\]]*\]"#,
        ]
        return patterns.contains { pat in
            text.range(of: pat, options: .regularExpression) != nil
        }
    }

    nonisolated static func looksLikeToolAttempt(_ text: String) -> Bool {
        let u = text.uppercased()
        return u.contains("OPEN_APP") || u.contains("DESKTOP_") || u.contains("AX_ACT")
            || u.contains("PASTE_PAYLOAD") || u.contains("DONE") || text.contains("[")
    }

    /// Fix common 0.5B tag mangling before `AgentToolParser`.
    nonisolated static func repairLooseToolTags(_ text: String) -> String {
        var t = text.trimmingCharacters(in: .whitespacesAndNewlines)

        // Strip trailing "(score: 0.73)" junk first.
        if let scoreRe = try? NSRegularExpression(pattern: #"\s*\(score:\s*[0-9.]+\)"#, options: [.caseInsensitive]) {
            t = scoreRe.stringByReplacingMatches(
                in: t, options: [], range: NSRange(t.startIndex..., in: t), withTemplate: ""
            )
        }

        // Unclosed [OPEN_APP: Safari
        if t.range(of: #"\[OPEN_APP:\s*[^\]\n]+$"#, options: .regularExpression) != nil,
           !t.contains("]") {
            t += "]"
        }

        // [DESKTOP_ACT] click x 100 400  →  [DESKTOP_ACT: click 100 400]
        if let xy = try? NSRegularExpression(
            pattern: #"\[DESKTOP_ACT\]\s*click\s+x?\s*(\d+)\s+(\d+)"#,
            options: [.caseInsensitive]
        ) {
            t = xy.stringByReplacingMatches(
                in: t, options: [], range: NSRange(t.startIndex..., in: t),
                withTemplate: "[DESKTOP_ACT: click $1 $2]"
            )
        }
        // [DESKTOP_ACT] click x 100  →  [DESKTOP_ACT: click 100 400]
        if let xOnly = try? NSRegularExpression(
            pattern: #"\[DESKTOP_ACT\]\s*click\s+x?\s*(\d+)\b"#,
            options: [.caseInsensitive]
        ) {
            t = xOnly.stringByReplacingMatches(
                in: t, options: [], range: NSRange(t.startIndex..., in: t),
                withTemplate: "[DESKTOP_ACT: click $1 400]"
            )
        }

        // Leave literal schema placeholders intact so the act loop can reject
        // them with an OPEN_APP / SNAPSHOT nudge (do not invent fake coords).

        return t.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
