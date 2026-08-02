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

        let continuing = Self.isContinueRequest(question)
        let goal: String
        var observations: [String]
        if continuing, !lastGoal.isEmpty {
            goal = lastGoal
            observations = lastObservations
            await onProgress(.systemLog(AppLanguage.shared.t(
                "🔁 [L2 JGEN Act] resuming prior goal (\(observations.count) observations)…",
                "🔁 [L2 JGEN操作] 前回の目標を再開（観測 \(observations.count) 件）…")))
        } else {
            goal = question
            observations = []
            lastGoal = question
            lastObservations = []
        }

        let system = """
        You are Verantyx's JGEN execution layer. Operate the Mac to finish the goal. \
        Each turn output EXACTLY one complete tool tag and nothing else. \
        Tags must include the closing bracket ]. \
        Allowed:
        [OPEN_APP: Safari]
        [DESKTOP_SNAPSHOT]
        [DESKTOP_ACT: click 500 400]
        [DESKTOP_ACT: type today's news]
        [AX_ACT: #btn1 click]
        [WAIT_UNTIL_STABLE]
        [DONE: short status in the user's language]
        After OPEN_APP always emit DESKTOP_SNAPSHOT next. \
        Never invent scores. Never write prose without a tag. \
        Never repeat a phrase.
        """

        var finalAnswer = ""
        var toolCount = 0
        // Give small models enough steps for open → snapshot → search → done.
        let turnsCap = max(6, min(max(maxTurns, 6), 16))

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
            if continuing {
                userParts.append("[NOTE]\nUser asked to continue the unfinished desktop task.")
            }
            if !observations.isEmpty {
                let recent = observations.suffix(6).joined(separator: "\n---\n")
                userParts.append("[OBSERVATIONS]\n\(recent)")
            }
            let hint: String
            if toolCount == 0 {
                hint = "First step: [OPEN_APP: Safari] (complete tag with ])."
            } else if observations.last?.contains("open -a") == true
                        || observations.last?.localizedCaseInsensitiveContains("open_app") == true
                        || observations.last?.localizedCaseInsensitiveContains("opened") == true {
                hint = "Next required: [DESKTOP_SNAPSHOT]"
            } else {
                hint = "Emit one valid tool tag to progress the search, or [DONE: …] if finished."
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

            let call = AgentToolCall(tool: tool)
            await onProgress(.toolCall(call))
            let result = await executor.execute(tool, workspaceURL: workspaceURL)
            toolCount += 1
            let trimmed = result.count > 1500 ? String(result.prefix(1500)) + "…" : result
            observations.append("\(call.displayLabel) → \(trimmed)")
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
        }

        if useEternalMemory, !finalAnswer.isEmpty, !JCrossChatManager.isPhraseLooping(finalAnswer) {
            let stamp = "Q: \(goal.prefix(120))\nA: \(finalAnswer.prefix(400))"
            try? await EternalMemoryStore.shared.add(text: String(stamp), concepts: ["jgen-act", "bug-repro"])
        }

        await onProgress(.done(message: finalAnswer, workspace: workspaceURL))
        return Outcome(text: finalAnswer, turns: min(turnsCap, max(toolCount, 1)), toolCount: toolCount)
    }

    private static func filterAllowed(_ tools: [AgentTool]) -> [AgentTool] {
        tools.filter { tool in
            switch tool {
            case .openApp, .desktopSnapshot, .desktopAct, .axAct, .waitUntilStable, .done:
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

    nonisolated static func hasCompleteToolTag(_ text: String) -> Bool {
        let patterns = [
            #"\[OPEN_APP:\s*[^\]]+\]"#,
            #"\[DESKTOP_SNAPSHOT\]"#,
            #"\[DESKTOP_ACT:\s*[^\]]+\]"#,
            #"\[AX_ACT:\s*[^\]]+\]"#,
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
            || u.contains("DONE") || text.contains("[")
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
