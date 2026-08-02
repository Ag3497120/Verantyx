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

        let system = """
        You are Verantyx's JGEN body. One complete tool tag per turn (closing ]). \
        Schema: SENSE → ACT → observe → on MISMATCH try alternate → DONE. \
        Allowed:
        [OPEN_APP: Safari]
        [DESKTOP_SNAPSHOT]
        [DESKTOP_ACT: click X Y]
        [AX_ACT: #btn1 click]
        [PASTE_PAYLOAD]
        [WAIT_UNTIL_STABLE]
        [DONE: short status in the user's language]
        SENSE with DESKTOP_SNAPSHOT/AX map. ACT with AX/click. \
        If [PAYLOAD] ready: focus an editable text field (AX preferred), then [PASTE_PAYLOAD]. \
        Never dump long text via DESKTOP_ACT type. Never invent coords. Never prose without a tag. \
        On MISMATCH / NO VISUAL CHANGE / DESKTOP_BLOCKED: try a different AX target or DONE. \
        Never repeat the same click.
        """

        var finalAnswer = ""
        var toolCount = 0
        var identicalErrorStreak = 0
        var lastErrorFingerprint = ""
        var lastActionKey = ""
        var identicalActionStreak = 0
        // Enough steps for open → type search → read/click results → done.
        let turnsCap = max(8, min(max(maxTurns, 8), 18))

        await executor.resetLoopGuards()

        // Tiny models cannot plan Safari UI. Bootstrap: open → snapshot →
        // type the user's query into the Smart Search field (⌘L) → Return →
        // snapshot again, then let the model continue (click / summarize).
        // Translate intent only reaches a named URL destination — no site-
        // specific paste/click bootstrap; the loop discovers focus + PASTE_PAYLOAD.
        if toolCount == 0, Self.goalNeedsBrowser(goal) {
            toolCount = await Self.runBootstrapTool(
                .openApp(name: "Safari"),
                label: "bootstrapping [OPEN_APP: Safari]…",
                labelJA: "先に [OPEN_APP: Safari] を実行…",
                executor: executor,
                workspaceURL: workspaceURL,
                sessionId: sid,
                observations: &observations,
                toolCount: toolCount,
                onProgress: onProgress
            )
            lastObservations = observations

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
            if toolCount == 0 {
                hint = "First required tag is [OPEN_APP: Safari]."
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
                break
            }

            // Refuse DESKTOP_ACT before any app open when goal needs a browser.
            if case .desktopAct = tool, toolCount == 0, Self.goalNeedsBrowser(goal) {
                observations.append("(blocked DESKTOP_ACT before OPEN_APP — open Safari first)")
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
            observations.append(Self.stampObservation(
                toolLabel: call.displayLabel,
                result: trimmed,
                selfAction: call.displayLabel
            ))
            lastObservations = observations
            await onProgress(.toolResult(AgentToolCall(tool: tool, result: trimmed, succeeded: !result.contains("ERROR"))))

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

        return t.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
