import Foundation

/// Layer 2 **act** path for jgen-vector-bus: same JGEN as the council drives
/// desktop/AX tools **without** `AgentLoop` / Nano Gatekeeper prompts.
///
/// Loop: short ChatML generate → parse one bracket tool call →
/// `AgentToolExecutor` → observation stamped onto the vector bus → repeat
/// until `[DONE: …]` or maxTurns.
actor JGenActAgent {
    static let shared = JGenActAgent()

    private let executor = AgentToolExecutor()

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

        let system = """
        You are Verantyx's JGEN execution layer. Reproduce UI bugs by operating \
        the desktop like the user. Use exactly ONE tool tag per turn, then stop. \
        Allowed tools only:
        [OPEN_APP: AppName]
        [DESKTOP_SNAPSHOT]
        [DESKTOP_ACT: click x y] or [DESKTOP_ACT: type text]
        [AX_ACT: #id click] or [AX_ACT: #id type "text"]
        [DONE: short conclusion in the user's language]
        Never emit MEM/CTRL tags, role labels, or multiple tools in one reply. \
        Prefer [AX_ACT] when the semantic UI map has element ids. \
        Never repeat a phrase.
        """

        var observations: [String] = []
        var finalAnswer = ""
        var toolCount = 0
        let turnsCap = max(1, min(maxTurns, 16))

        for turn in 1...turnsCap {
            let memory = await JGenVectorBusMemory.recallBundle(
                for: question, sessionId: sid, useEternal: useEternalMemory, k: 3
            )
            var userParts: [String] = []
            if !memory.isEmpty { userParts.append(memory) }
            userParts.append("[COUNCIL]\n\(handoff.conclusion.isEmpty ? handoff.asText : handoff.conclusion)")
            if !handoff.detail.isEmpty, !JCrossChatManager.isPhraseLooping(handoff.detail) {
                userParts.append("[DETAIL]\n\(JCrossChatManager.collapsePhraseRepetition(handoff.detail))")
            }
            userParts.append("[ORIGINAL REQUEST]\n\(question)")
            if !observations.isEmpty {
                let recent = observations.suffix(4).joined(separator: "\n---\n")
                userParts.append("[OBSERVATIONS]\n\(recent)")
            }
            userParts.append("Turn \(turn)/\(turnsCap). Emit exactly one tool tag now.")

            let conversation: [(role: String, content: String)] = [
                ("system", system),
                ("user", userParts.joined(separator: "\n\n"))
            ]

            let raw: String
            do {
                var streamed = ""
                raw = try await chat.generateStreaming(
                    conversation: conversation,
                    maxTokens: 128
                ) { delta in
                    streamed += delta
                    Task { await onProgress(.streamToken(delta)) }
                    if JCrossChatManager.isPhraseLooping(streamed) { return false }
                    return true
                }
            } catch {
                let msg = "JGEN act generate failed: \(error.localizedDescription)"
                await onProgress(.error(msg))
                return Outcome(text: msg, turns: turn, toolCount: toolCount)
            }

            let cleaned = JCrossChatManager.collapsePhraseRepetition(
                raw.trimmingCharacters(in: .whitespacesAndNewlines)
            )
            let parsed = AgentToolParser.parse(from: cleaned)
            let tools = Self.filterAllowed(parsed.toolCalls)

            if tools.isEmpty {
                // Model answered in prose — treat as done if non-empty.
                if !cleaned.isEmpty, !JCrossChatManager.isPhraseLooping(cleaned) {
                    finalAnswer = cleaned
                    break
                }
                observations.append("(no tool parsed on turn \(turn))")
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
            await onProgress(.toolResult(AgentToolCall(tool: tool, result: trimmed, succeeded: !result.contains("ERROR"))))

            // Dual-write is also done inside desktop tools; stamp a compact
            // act-loop line so council can recall the attempt sequence.
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
                "Act loop finished after \(toolCount) tools. Last: \(String($0.prefix(400)))"
            } ?? (handoff.detail.isEmpty ? handoff.asText : handoff.detail)
            finalAnswer = JCrossChatManager.collapsePhraseRepetition(finalAnswer)
        }

        if useEternalMemory, !finalAnswer.isEmpty, !JCrossChatManager.isPhraseLooping(finalAnswer) {
            let stamp = "Q: \(question.prefix(120))\nA: \(finalAnswer.prefix(400))"
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
}
