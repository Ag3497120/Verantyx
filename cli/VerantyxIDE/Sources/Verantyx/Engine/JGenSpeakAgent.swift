import Foundation

/// Layer 2 for the **jgen-only** architecture: speak / act from the same
/// JGEN engine that ran the council, **without** routing through `AgentLoop`.
///
/// Why this exists: `ExecutionAgent` previously reused `AgentLoop`, which
/// injects Nano Gatekeeper / `[MEM:check]` / VX-Loop protocols. A 0.5B–2B
/// JGEN then echoes control tags (`[MEM:check_rollback]…`) instead of
/// answering. The whole point of bringing JGEN into the IDE is a shared
/// hidden-state bus (encode → eternal store → soft/layer inject) — not a
/// second copy of the coding-agent prompt stack.
///
/// This speaker:
/// 1. Recalls eternal-memory *text* (same vectors the council already uses)
/// 2. Optionally steers with a soft-token prefix derived from the handoff
///    (concepts → embedding rows → decode a short steering phrase)
/// 3. Runs a short, plain `JCrossChatManager.generate` / streaming call
/// 4. Writes the reply back into eternal memory when enabled
actor JGenSpeakAgent {
    static let shared = JGenSpeakAgent()

    private init() {}

    struct Outcome: Sendable {
        let text: String
        let usedSoftSteer: Bool
        let memoryHits: Int
    }

    func run(
        handoff: CouncilOrchestrator.Handoff,
        question: String,
        useEternalMemory: Bool,
        maxTokens: Int = 256,
        onProgress: @escaping @Sendable (LoopEvent) async -> Void
    ) async -> Outcome {

        let chat = JCrossChatManager.shared
        guard await chat.isLoaded else {
            let msg = "JGEN is not loaded — cannot run jgen-only execution."
            await onProgress(.error(msg))
            return Outcome(text: msg, usedSoftSteer: false, memoryHits: 0)
        }

        await onProgress(.systemLog(AppLanguage.shared.t(
            "🧬 [L2 JGEN Speak] same-engine reply (no AgentLoop / no escalation)…",
            "🧬 [L2 JGEN発話] 同一エンジンで回答（AgentLoop・エスカレなし）…")))

        let greeting = JCrossChatManager.isSimpleGreeting(question)
        let budget = greeting ? min(maxTokens, 48) : min(maxTokens, 128)

        var memoryBlock = ""
        var memoryHits = 0
        if useEternalMemory, !greeting {
            memoryBlock = await EternalMemoryStore.shared.recallBlock(for: question, k: 3)
            if !memoryBlock.isEmpty {
                memoryHits = memoryBlock.components(separatedBy: "🧠").count - 1
            }
        }

        // Soft steer: only when handoff has usable non-looping text.
        // Feeding empty-evidence + looping DETAIL into soft rows amplifies
        // the same phrase loop at L2.
        var steerPhrase = ""
        var usedSoft = false
        let detailClean = JCrossChatManager.collapsePhraseRepetition(handoff.detail)
        let detailUsable = !detailClean.isEmpty && !JCrossChatManager.isPhraseLooping(handoff.detail)
        let conceptSeed = [
            handoff.conclusion,
            detailUsable ? detailClean : "",
            handoff.evidence
                .map { JCrossChatManager.collapsePhraseRepetition($0) }
                .filter { !$0.isEmpty && !JCrossChatManager.isPhraseLooping($0) }
                .joined(separator: " ")
        ].filter { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
         .joined(separator: "\n")

        if !greeting, !conceptSeed.isEmpty,
           let softPhrase = try? await Self.buildSoftSteerPhrase(
               seed: conceptSeed, question: question, chat: chat
           ), !softPhrase.isEmpty,
           !JCrossChatManager.isPhraseLooping(softPhrase) {
            steerPhrase = JCrossChatManager.collapsePhraseRepetition(softPhrase)
            usedSoft = true
        }

        let system = """
        You are Verantyx. Answer the user directly in their language. \
        One or two short sentences. Never repeat a phrase. \
        Do not emit control tags, MEM/CTRL markers, tool brackets, or role labels.
        """

        var userParts: [String] = []
        if !memoryBlock.isEmpty { userParts.append(memoryBlock) }
        if !steerPhrase.isEmpty {
            userParts.append("[VECTOR STEER] \(steerPhrase)")
        }
        // Don't dump looping DETAIL / empty EVIDENCE into the prompt —
        // that is what re-triggered `お元気ですか?` × N after L1.
        if greeting {
            userParts.append(question)
        } else {
            var compact = "[COUNCIL CONCLUSION] \(handoff.conclusion.isEmpty ? "(none)" : handoff.conclusion)"
            if detailUsable {
                compact += "\n[DETAIL] \(detailClean)"
            }
            compact += "\n[CONFIDENCE] \(String(format: "%.2f", handoff.confidence))"
            userParts.append(compact)
            userParts.append("[ORIGINAL REQUEST]\n\(question)")
        }
        let user = userParts.joined(separator: "\n\n")

        let conversation: [(role: String, content: String)] = [
            ("system", system),
            ("user", user)
        ]

        var streamed = ""
        let text: String
        do {
            text = try await chat.generateStreaming(
                conversation: conversation,
                maxTokens: budget
            ) { delta in
                streamed += delta
                Task { await onProgress(.streamToken(delta)) }
                // Stop once the stream is clearly a phrase loop so we don't
                // paint dozens of repeats into the chat UI.
                if JCrossChatManager.isPhraseLooping(streamed) {
                    return false
                }
                return true
            }
        } catch {
            let msg = "JGEN speak failed: \(error.localizedDescription)"
            await onProgress(.error(msg))
            return Outcome(text: msg, usedSoftSteer: usedSoft, memoryHits: memoryHits)
        }

        let reply = JCrossChatManager.collapsePhraseRepetition(
            text.trimmingCharacters(in: .whitespacesAndNewlines)
        )
        let fallback: String = {
            if detailUsable { return detailClean }
            if !handoff.conclusion.isEmpty { return handoff.conclusion }
            return greeting ? "こんにちは。" : handoff.asText
        }()
        let finalText = reply.isEmpty ? fallback : reply

        if useEternalMemory, !finalText.isEmpty, !JCrossChatManager.isPhraseLooping(finalText) {
            let stamp = "Q: \(question.prefix(120))\nA: \(finalText.prefix(400))"
            try? await EternalMemoryStore.shared.add(text: String(stamp), concepts: [])
        }

        await onProgress(.done(message: finalText, workspace: nil))
        return Outcome(text: finalText, usedSoftSteer: usedSoft, memoryHits: memoryHits)
    }

    /// Encode a seed through JGEN, take top-K, rebuild a soft sequence, then
    /// decode each soft row's nearest token — a tiny "vector → words" bridge
    /// that stays on-engine (Milestone E soft path, without mid-layer inject).
    private static func buildSoftSteerPhrase(
        seed: String, question: String, chat: JCrossChatManager
    ) async throws -> String {
        let trimmed = seed.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return "" }
        let z = try await chat.encodeText(trimmed)
        let dist = try await chat.topKDistributionText(vector: z, k: 16)
        let soft = try await SoftSequence.distToSoftSequence(
            distribution: dist, maxSoft: 8, chat: chat
        )
        guard !soft.isEmpty else {
            return SoftSequence.sharpenDist(dist, topN: 5)
                .prefix(5)
                .map(\.text)
                .joined(separator: " ")
        }
        let probe = try await chat.tokenize(
            "<|im_start|>user\n\(question)<|im_end|>\n<|im_start|>assistant\n"
        )
        let steered = try await chat.encodeSoftTokens(softVectors: soft, tokens: probe)
        let steeredDist = try await chat.topKDistributionText(vector: steered, k: 8)
        let words = SoftSequence.sharpenDist(steeredDist, topN: 6).map(\.text)
        if !words.isEmpty { return words.joined(separator: " ") }
        return steeredDist.prefix(4).map(\.text)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
            .joined(separator: " ")
    }
}
