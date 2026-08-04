import Foundation
import Tokenizers
import Hub

/// The claim this runtime exists to demonstrate, made operational:
///
///   The model forgets every turn. The agent does not.
///
/// Every turn is an independent short forward pass — `JGenBackend.reset()` is
/// called before each one, so no KV cache, no conversation history and no
/// hidden state survives it. What survives is on disk: open gaps in
/// `GapStore`, and recalled experience in `VectorMemory`. A turn's prompt is
/// rebuilt from those two sources alone.
///
/// The practical consequence is that per-turn cost stays flat instead of
/// growing with mission length, and that a mission can be killed and resumed
/// in a new process — see `resume(...)`, which starts from an empty model and
/// reconstructs purpose from the store.
public final class LongHorizonRunner {

    public struct Config: Sendable {
        public var modelPath: String
        public var memoryDirectory: URL
        public var maxTurns: Int
        public var maxTokensPerTurn: Int
        /// Set false to measure the counterfactual: same loop, same gaps, no
        /// vector recall. This is the A/B the release plan asks for.
        public var useVectorMemory: Bool

        public init(
            modelPath: String,
            memoryDirectory: URL,
            maxTurns: Int = 8,
            maxTokensPerTurn: Int = 96,
            useVectorMemory: Bool = true
        ) {
            self.modelPath = modelPath
            self.memoryDirectory = memoryDirectory
            self.maxTurns = maxTurns
            self.maxTokensPerTurn = maxTokensPerTurn
            self.useVectorMemory = useVectorMemory
        }
    }

    public struct Outcome: Sendable {
        public let turns: Int
        public let openGaps: Int
        public let resolvedGaps: Int
        public let totalPromptTokens: Int
        /// Prompt tokens per turn. Flat-ish here is the whole point; a rising
        /// series would mean context is leaking back in.
        public let promptTokensPerTurn: [Int]
    }

    private let config: Config
    private let backend: JGenBackend
    private let tokenizer: any Tokenizer
    private let gaps: GapStore
    private let memory: VectorMemory?
    private let sink: VeraEventSink

    public init(config: Config, sink: VeraEventSink) async throws {
        self.config = config
        self.sink = sink
        self.backend = try JGenBackend(modelPath: config.modelPath)
        self.gaps = try GapStore(directory: config.memoryDirectory)

        // Tokenizer comes from the sidecar meta written at conversion time —
        // the model file itself carries no vocabulary.
        let metaPath = config.modelPath + ".meta.json"
        guard let metaData = FileManager.default.contents(atPath: metaPath),
              let meta = try? JSONSerialization.jsonObject(with: metaData) as? [String: Any],
              let tokenizerPath = meta["tokenizer"] as? String else {
            throw RunnerError.tokenizerMissing(metaPath)
        }
        let folder = URL(fileURLWithPath: tokenizerPath).deletingLastPathComponent()
        guard FileManager.default.fileExists(
            atPath: folder.appendingPathComponent("config.json").path
        ) else {
            throw RunnerError.tokenizerIncomplete(folder.path)
        }
        self.tokenizer = try await AutoTokenizer.from(modelFolder: folder)

        // Vectors are only comparable within one model's hidden space, so the
        // store is keyed by the model that wrote them.
        let modelId = URL(fileURLWithPath: config.modelPath).lastPathComponent
        self.memory = config.useVectorMemory
            ? try VectorMemory(directory: config.memoryDirectory,
                               dim: backend.hiddenDim, modelId: modelId)
            : nil
    }

    public enum RunnerError: Error, CustomStringConvertible {
        case tokenizerMissing(String)
        case tokenizerIncomplete(String)

        public var description: String {
            switch self {
            case .tokenizerMissing(let path):
                return "no tokenizer recorded in \(path) — re-run jgen_forge with --tokenizer"
            case .tokenizerIncomplete(let path):
                return "tokenizer folder \(path) has no config.json — the conversion fell back to a synthesized vocab"
            }
        }
    }

    // MARK: - Mission entry points

    /// Starts (or continues) work on `goal`. Safe to call against a memory
    /// directory that already has gaps: the `(scope, subject)` identity means
    /// the same goal reopens the same gap rather than duplicating it.
    @discardableResult
    public func run(goal: String, scope: String = "mission") async throws -> Outcome {
        let gap = try gaps.open(
            gapType: "MISSION", subject: goal, scope: scope, severity: .quality
        )
        _ = sink.emit(.mission, summary: goal, turn: 0, detail: [
            "model": URL(fileURLWithPath: config.modelPath).lastPathComponent,
            "engine": backend.enginePath,
            "hidden_dim": String(backend.hiddenDim),
            "gap_id": gap.gapId,
            "vector_memory": config.useVectorMemory ? "on" : "off",
            "memory_dir": config.memoryDirectory.path,
        ], tags: ["mission"])

        if let memory, memory.needsReembed {
            _ = sink.emit(.policy,
                summary: "\(memory.foreignRecordCount) vectors were written by a different model — excluded from recall",
                turn: 0,
                detail: ["reason": "hidden spaces are not comparable across models"],
                tags: ["memory", "model-swap"])
        }

        return try await loop(goalGapId: gap.gapId, goal: goal, resumed: false)
    }

    /// Restart continuation: no goal is supplied. Purpose is reconstructed
    /// from the store, with an empty KV cache and no chat history — the
    /// demonstration that experience is owned by the agent, not the model.
    @discardableResult
    public func resume() async throws -> Outcome? {
        guard let gap = gaps.openGaps.first(where: { $0.gapType == "MISSION" })
                ?? gaps.openGaps.first else {
            _ = sink.emit(.result, summary: "nothing to resume — no open gaps", turn: 0,
                          tags: ["resume"])
            return nil
        }
        _ = sink.emit(.mission, summary: "RESUMED: \(gap.subject)", turn: 0, detail: [
            "gap_id": gap.gapId,
            "kv_cache": "empty",
            "chat_history": "not loaded",
            "recovered_from": gaps.path,
            "already_tried": gap.attemptedStrategies.joined(separator: " | "),
        ], tags: ["mission", "resume"])

        return try await loop(goalGapId: gap.gapId, goal: gap.subject, resumed: true)
    }

    // MARK: - Turn loop

    private func loop(goalGapId: String, goal: String, resumed: Bool) async throws -> Outcome {
        var promptTokensPerTurn: [Int] = []

        for turn in 1...max(1, config.maxTurns) {
            if Task.isCancelled {
                _ = sink.emit(.result, summary: "stopped by user", turn: turn, tags: ["cancel"])
                break
            }
            guard let current = gaps.get(goalGapId), current.status.isOpen else {
                break
            }

            // ── Rebuild the entire working context from disk ──────────────
            // Nothing here comes from a previous turn's model state.
            var blocks: [String] = []
            let purpose = gaps.purposeBlock()
            if !purpose.isEmpty { blocks.append(purpose) }

            if let memory {
                let probe = try encodeText(goal + " " + (current.failureType ?? ""))
                let recalled = try memory.recallBlock(vector: probe, k: 3)
                if !recalled.isEmpty {
                    blocks.append(recalled)
                    _ = sink.emit(.skill_recall, summary: "recalled prior experience",
                                  turn: turn, detail: ["block": String(recalled.prefix(200))],
                                  tags: ["memory"])
                }
            }
            blocks.append("[GOAL] \(goal)")
            blocks.append("[TURN] \(turn)/\(config.maxTurns). State one concrete next step, then a short result line.")

            let prompt = Self.chatML(system: Self.systemPrompt, user: blocks.joined(separator: "\n\n"))
            let promptTokens = tokenizer.encode(text: prompt).map { UInt32($0) }
            promptTokensPerTurn.append(promptTokens.count)

            _ = sink.emit(.observation, summary: "context rebuilt from store", turn: turn, detail: [
                "prompt_tokens": String(promptTokens.count),
                "open_gaps": String(gaps.openGaps.count),
                "kv_cache": "reset",
            ], tags: ["context"])

            // ── Independent forward pass ──────────────────────────────────
            backend.reset()
            let outputTokens = try backend.generate(
                promptTokens: promptTokens, maxTokens: config.maxTokensPerTurn
            )
            let reply = Self.cleanReply(
                tokenizer.decode(tokens: outputTokens.map { Int($0) }, skipSpecialTokens: true)
            )

            _ = sink.emit(.proposed_action, summary: String(reply.prefix(200)), turn: turn,
                          detail: ["output_tokens": String(outputTokens.count)],
                          tags: ["model"])

            // ── Settle or record the attempt ──────────────────────────────
            // Honesty rule carried over from ActDNA: a turn that produced
            // nothing usable is a failed attempt, never a quiet success.
            if reply.isEmpty {
                try gaps.recordAttempt(goalGapId, strategy: "turn \(turn)", failureType: "empty_output")
                _ = sink.emit(.result, summary: "no usable output", turn: turn,
                              detail: ["gap": "still open"], tags: ["mismatch"])
                continue
            }

            if let memory {
                let vector = try encodeText(reply)
                try memory.add(text: reply, kind: "step", vector: vector)
            }

            if Self.looksComplete(reply) {
                try gaps.resolve(goalGapId, note: String(reply.prefix(400)))
                _ = sink.emit(.result, summary: "gap RESOLVED", turn: turn,
                              detail: ["gap_id": goalGapId], tags: ["resolved"])
                break
            }

            try gaps.recordAttempt(
                goalGapId,
                strategy: Self.strategyKey(reply),
                failureType: "not_yet_complete"
            )
            _ = sink.emit(.gap, summary: gaps.get(goalGapId)?.briefLine() ?? "", turn: turn,
                          tags: ["gap"])
        }

        let outcome = Outcome(
            turns: promptTokensPerTurn.count,
            openGaps: gaps.openGaps.count,
            resolvedGaps: gaps.resolvedGaps.count,
            totalPromptTokens: promptTokensPerTurn.reduce(0, +),
            promptTokensPerTurn: promptTokensPerTurn
        )
        _ = sink.emit(.result, summary: "mission window ended", turn: outcome.turns, detail: [
            "open_gaps": String(outcome.openGaps),
            "resolved_gaps": String(outcome.resolvedGaps),
            "prompt_tokens_per_turn": promptTokensPerTurn.map(String.init).joined(separator: ","),
            "resumed": resumed ? "yes" : "no",
        ], tags: ["summary"])
        return outcome
    }

    // MARK: - Helpers

    private func encodeText(_ text: String) throws -> [Float] {
        backend.reset()
        // PromptEOL framing: same trick the IDE's EternalMemoryStore uses to
        // pull a sentence-level vector out of a causal LM.
        let wrapped = "This sentence: \"\(text.prefix(400))\" means in one word:\""
        let tokens = tokenizer.encode(text: wrapped).map { UInt32($0) }
        return try backend.encode(tokens: tokens)
    }

    static let systemPrompt = """
    You are a long-horizon agent. You have no memory of previous turns; \
    everything you know is in the blocks below, recovered from persistent storage. \
    Do not repeat an approach listed as already tried. \
    Answer with one concrete next step. \
    When the goal is genuinely achieved, begin your reply with DONE:
    """

    static func chatML(system: String, user: String) -> String {
        "<|im_start|>system\n\(system)<|im_end|>\n"
        + "<|im_start|>user\n\(user)<|im_end|>\n"
        + "<|im_start|>assistant\n"
    }

    /// Strips ChatML scaffolding a small model echoes back, and keeps only the
    /// first turn's worth of text. Without this, a 0.5B reply that re-emits
    /// `<|im_start|>` blocks gets stored as "experience" and recalled forever.
    static func cleanReply(_ raw: String) -> String {
        var text = raw
        for marker in ["<|im_end|>", "<|im_start|>", "<|endoftext|>"] {
            text = text.replacingOccurrences(of: marker, with: "\n")
        }
        // Keep the first non-empty paragraph: everything after the model's
        // first stop is continuation noise, not a second proposal.
        let lines = text.split(whereSeparator: \.isNewline)
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
        return (lines.first ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// Only an explicit marker *carrying a result* counts as completion.
    ///
    /// A bare `DONE:` is rejected on purpose: small models routinely echo the
    /// completion token straight out of the system prompt, and accepting that
    /// would mark a mission solved on the strength of the instruction that
    /// described how to end it. Inferring success from prose is how agents come
    /// to report work they never did.
    static func looksComplete(_ reply: String) -> Bool {
        let upper = reply.uppercased()
        guard upper.hasPrefix("DONE:") else { return false }
        let payload = reply.dropFirst("DONE:".count)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        // Needs real content, and must not just parrot the instruction text.
        guard payload.count >= 12 else { return false }
        let instructionEcho = ["state one concrete next step", "short result line"]
        let lowered = payload.lowercased()
        return !instructionEcho.contains { lowered.contains($0) }
    }

    /// Short signature of an approach, used to keep a resumed run from
    /// re-proposing something already recorded as tried.
    static func strategyKey(_ reply: String) -> String {
        let firstLine = reply.split(whereSeparator: \.isNewline).first.map(String.init) ?? reply
        return String(firstLine.prefix(60))
    }
}
