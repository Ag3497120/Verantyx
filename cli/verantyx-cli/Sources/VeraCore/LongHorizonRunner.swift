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
        /// Where tools operate. Separate from `memoryDirectory` so a run cannot
        /// edit its own memory through the file tools.
        public var workspace: URL
        public var toolPolicy: ToolPolicy
        /// Names this runner in shared memory.
        ///
        /// Subagents pointed at the same `--memory` directory and the same
        /// model share one vector space by construction — same hidden space,
        /// same store, so what one learns the next can recall. This field
        /// records who wrote a memory; it deliberately does **not** partition
        /// the store, because partitioning it would defeat the sharing.
        public var agentId: String?

        public init(
            modelPath: String,
            memoryDirectory: URL,
            maxTurns: Int = 8,
            maxTokensPerTurn: Int = 96,
            useVectorMemory: Bool = true,
            workspace: URL = URL(fileURLWithPath: FileManager.default.currentDirectoryPath),
            toolPolicy: ToolPolicy = .readOnly,
            agentId: String? = nil
        ) {
            self.modelPath = modelPath
            self.memoryDirectory = memoryDirectory
            self.maxTurns = maxTurns
            self.maxTokensPerTurn = maxTokensPerTurn
            self.useVectorMemory = useVectorMemory
            self.workspace = workspace
            self.toolPolicy = toolPolicy
            self.agentId = agentId
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
    private let tools: ToolExecutor

    public init(config: Config, sink: VeraEventSink) async throws {
        self.config = config
        self.sink = sink
        self.backend = try JGenBackend(modelPath: config.modelPath)
        self.gaps = try GapStore(directory: config.memoryDirectory)
        self.tools = ToolExecutor(workspace: config.workspace, policy: config.toolPolicy)

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

    /// Migrates vector memory written by a previous model into the currently
    /// loaded model's space. `GapStore` needs no equivalent — it is text.
    @discardableResult
    public func reembedMemory() throws -> VectorMemory.ReembedResult? {
        guard let memory else { return nil }
        let before = memory.foreignRecordCount
        let result = try memory.reembed(using: { try self.encodeText($0) })
        _ = sink.emit(.policy, summary: "vector memory re-embedded for model swap", turn: 0, detail: [
            "foreign_before": String(before),
            "migrated": String(result.migrated),
            "kept": String(result.kept),
            "failed": String(result.failed),
            "model": URL(fileURLWithPath: config.modelPath).lastPathComponent,
        ], tags: ["memory", "model-swap"])
        return result
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
                // Recall is judged by shape as well as similarity: a memory of
                // the same failure shape stays reachable however old it is.
                let recalled = try memory.recallBlock(
                    vector: probe, k: 3, against: StructuralSignature(gap: current)
                )
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

            // ── Act, if the turn proposed a tool ──────────────────────────
            // The observation — not the model's prose about it — is what gets
            // stored and recalled. A step is only "experience" once something
            // outside the model confirmed it.
            var observation: String? = nil
            if let tool = CLIToolParser.parseFirst(reply), !Self.isDone(tool) {
                let result = tools.execute(tool)
                observation = result.text
                _ = sink.emit(.result, summary: String(result.text.prefix(200)), turn: turn,
                              detail: ["tool": tool.label,
                                       "ok": result.ok ? "yes" : "no",
                                       "refused": result.refused ? "yes" : "no"],
                              tags: result.ok ? ["tool"] : ["tool", "mismatch"])
                if !result.ok {
                    try gaps.recordAttempt(goalGapId, strategy: tool.label,
                                           failureType: result.refused ? "refused_by_policy" : "tool_failed")
                    if let memory {
                        let vector = try encodeText("\(tool.label) -> \(result.text)")
                        try memory.add(
                            text: "\(tool.label) -> \(result.text.prefix(200))",
                            kind: "failure", vector: vector,
                            signature: gaps.get(goalGapId).map(StructuralSignature.init(gap:)),
                            agentId: config.agentId
                        )
                    }
                    continue
                }
            }

            if let memory {
                let record = observation.map { "\(reply)\n-> \($0.prefix(300))" } ?? reply
                let vector = try encodeText(record)
                try memory.add(
                    text: record, kind: observation == nil ? "step" : "observation",
                    vector: vector,
                    signature: gaps.get(goalGapId).map(StructuralSignature.init(gap:)),
                    agentId: config.agentId
                )
            }

            if Self.looksComplete(reply, goal: goal) {
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
    Do not repeat an approach listed as already tried.

    Emit exactly one tool call per turn:
    [READ_FILE: path]
    [LIST_DIR: path]
    [WRITE_FILE: path
    <content>]
    [MAKE_DIR: path]
    [RUN: shell command]

    When the goal is genuinely achieved, reply with DONE: followed by what you \
    actually found. Restating the goal is not a result.
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

    /// Only an explicit marker *carrying a new result* counts as completion.
    ///
    /// Three ways a small model fakes completion, all rejected here:
    ///   1. a bare `DONE:` — the token echoed out of the system prompt
    ///   2. `DONE:` followed by the instruction text ("state one concrete…")
    ///   3. `DONE:` followed by the goal restated verbatim — observed in a real
    ///      run as "DONE: Trace the cause of the CI packaging failure", which
    ///      reports the task as its own outcome
    ///
    /// A genuine completion has to say something the goal does not already say.
    /// Inferring success from prose is how agents come to report work they
    /// never did.
    static func looksComplete(_ reply: String, goal: String) -> Bool {
        let upper = reply.uppercased()
        guard upper.hasPrefix("DONE:") else { return false }
        let payload = reply.dropFirst("DONE:".count)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard payload.count >= 12 else { return false }

        let lowered = payload.lowercased()
        let instructionEcho = ["state one concrete next step", "short result line"]
        if instructionEcho.contains(where: { lowered.contains($0) }) { return false }

        // Reject when the payload adds essentially nothing to the goal.
        let goalWords = Set(Self.words(goal))
        let payloadWords = Set(Self.words(payload))
        guard !payloadWords.isEmpty else { return false }
        let novel = payloadWords.subtracting(goalWords)
        return Double(novel.count) / Double(payloadWords.count) >= 0.4
    }

    static func isDone(_ tool: CLITool) -> Bool {
        if case .done = tool { return true }
        return false
    }

    static func words(_ text: String) -> [String] {
        text.lowercased()
            .split { !$0.isLetter && !$0.isNumber }
            .map(String.init)
            .filter { $0.count > 2 }
    }

    /// Short signature of an approach, used to keep a resumed run from
    /// re-proposing something already recorded as tried.
    static func strategyKey(_ reply: String) -> String {
        let firstLine = reply.split(whereSeparator: \.isNewline).first.map(String.init) ?? reply
        return String(firstLine.prefix(60))
    }
}
