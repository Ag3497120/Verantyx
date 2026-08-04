import Foundation
import Tokenizers

/// Owns the loaded JCrossEngine + tokenizer for the currently-selected JGEN
/// chat backend (Milestone B of the JGEN/RustBrain integration plan). All
/// calls into the engine/tokenizer are serialized here (actor isolation)
/// since JCrossEngine's Rust side has no internal locking of its own.
///
/// Uses swift-transformers' `AutoTokenizer` (already a linked dependency
/// via the `Transformers` package product, used elsewhere for MLX) to load
/// the same HuggingFace-format tokenizer.json/tokenizer_config.json that
/// jgen_forge.py recorded in the model's .meta.json sidecar at conversion
/// time -- no new tokenizer implementation needed.
actor JCrossChatManager {
    static let shared = JCrossChatManager()

    private var engine: JCrossEngine?
    private var tokenizer: Tokenizer?
    private(set) var loadedModelName: String?
    /// Last load's device decision (Metal vs CPU) for UI / diagnostics.
    private(set) var lastLoadDeviceLabel: String?
    private(set) var lastLoadReasonEN: String?
    private(set) var lastLoadReasonJA: String?

    private init() {}

    /// Loads from Application Support (`JGenPaths.convertedModelsDir`).
    private func resolvedJGenPath(for modelFileName: String) async -> String {
        JGenPaths.convertedModelsDir.appendingPathComponent(modelFileName).path
    }

    /// Run a JGEN forward while asking the Act mirror to stop hitting WindowServer.
    private func withCapturePaused<T>(_ body: () throws -> T) rethrows -> T {
        JGenGPUSafety.beginCriticalGPUWork()
        defer { JGenGPUSafety.endCriticalGPUWork() }
        return try body()
    }

    enum ChatError: Error, LocalizedError {
        case notLoaded
        case metaNotFound(String)
        case tokenizerPathMissing(String)
        case architectureUnsupported(model: String, arch: String)
        case noRealTokenizer(model: String)

        var errorDescription: String? {
            switch self {
            case .notLoaded:
                return "No JGEN model loaded -- load one in Settings → JGEN first."
            case .metaNotFound(let path):
                return "Missing .meta.json sidecar for \(path) -- was this .jgen produced by jgen_forge.py?"
            case .tokenizerPathMissing(let path):
                return "\(path).meta.json has no \"tokenizer\" field -- this model was converted without a known tokenizer (e.g. --parts lexicon)."
            case .architectureUnsupported(let model, let arch):
                return "\(model) is architecture \"\(arch)\" -- JCrossEngine's Rust forward pass only supports \"standard\"/\"moe_standard\"/\"hybrid_ssm\" architectures. jgen_forge still converted it as a static weight lexicon (usable in the Vector Lab's project/resynthesize), but it can't be loaded here for chat/encode/council -- pick a different (supported-architecture) model instead."
            case .noRealTokenizer(let model):
                return "\(model) has no real HuggingFace tokenizer -- jgen_forge fell back to a GGUF vocabulary sidecar (not a full tokenizer.json/config.json), which JCrossChatManager can't load directly. Convert with --tokenizer pointing at a matching HF tokenizer folder, or pick a model whose tokenizer was auto-discovered."
            }
        }
    }

    /// Loads `modelFileName` (e.g. "qwen2_5_0_5b_router_full.jgen") from
    /// wherever it was actually converted to (see `resolvedJGenPath`), plus
    /// the tokenizer its .meta.json sidecar points at. Does real weight
    /// I/O -- call from a background context, never assume it's fast.
    func load(modelFileName: String) async throws {
        JGenGPUSafety.beginModelLoad()
        defer { JGenGPUSafety.endModelLoad() }

        // Drop any previous engine's Metal weight/KV caches before mmap'ing
        // another model — otherwise two .jgen residency windows overlap.
        if engine != nil {
            engine?.trim()
            engine = nil
            tokenizer = nil
            loadedModelName = nil
        }

        let jgenPath = await resolvedJGenPath(for: modelFileName)
        let metaPath = jgenPath + ".meta.json"

        guard let metaData = FileManager.default.contents(atPath: metaPath),
              let meta = try? JSONSerialization.jsonObject(with: metaData) as? [String: Any] else {
            throw ChatError.metaNotFound(modelFileName)
        }

        // Lexicon-only converts lack transformer weights — not runnable for chat.
        if let parts = meta["parts"] as? String, parts == "lexicon" {
            throw ChatError.architectureUnsupported(model: modelFileName, arch: "lexicon")
        }
        // Unsupported arches still get a .jgen + meta from forge; reject here.
        // hybrid_ssm (Ornith / Qwen3.5 GDN) is supported on the CPU path.
        if let arch = meta["arch"] as? String, !["standard", "moe_standard", "hybrid_ssm"].contains(arch) {
            throw ChatError.architectureUnsupported(model: modelFileName, arch: arch)
        }

        guard let tokenizerPath = meta["tokenizer"] as? String else {
            throw ChatError.tokenizerPathMissing(modelFileName)
        }
        // AutoTokenizer.from(modelFolder:) hard-requires config.json to
        // exist (swift-transformers' LanguageModelConfigurationFromHub.
        // loadConfig checks for it unconditionally, before anything else --
        // confirmed by reading that source directly). tokenizer_config.json
        // is a SEPARATE, optional file, not interchangeable with
        // config.json despite the similar name -- an earlier version of
        // this check treated them as either/or, which let folders through
        // that were missing config.json and still failed inside
        // AutoTokenizer.from with the same "missing config.json" error this
        // check exists to catch. jgen_forge's GGUF-vocab fallback (no real
        // tokenizer found at all) writes neither file.
        let tokenizerFolder = URL(fileURLWithPath: tokenizerPath).deletingLastPathComponent()
        let hasRealTokenizer = FileManager.default.fileExists(atPath: tokenizerFolder.appendingPathComponent("config.json").path)
        guard hasRealTokenizer else {
            throw ChatError.noRealTokenizer(model: modelFileName)
        }

        let mirrorWatching = await MainActor.run {
            HiddenWindowAutomation.shared.isMirrorWatching
        }
        // Settings-driven escape hatch for JGenGPUSafety's CPU-safety default
        // (see CouncilSettingsStore.forceJGenMetal) — equivalent to setting
        // JCROSS_FORCE_METAL=1 by hand, just reachable from the UI.
        if CouncilSettingsStore.isForceJGenMetal {
            setenv("JCROSS_FORCE_METAL", "1", 1)
        } else if ProcessInfo.processInfo.environment["JCROSS_FORCE_METAL"] == "1" {
            unsetenv("JCROSS_FORCE_METAL")
        }
        let decision = JGenGPUSafety.prepareEnvironmentForLoad(
            modelFileName: modelFileName,
            mirrorWatching: mirrorWatching
        )
        lastLoadDeviceLabel = decision.deviceLabel
        lastLoadReasonEN = decision.reasonEN
        lastLoadReasonJA = decision.reasonJA

        let newEngine = try JCrossEngine(path: jgenPath)
        let newTokenizer = try await AutoTokenizer.from(modelFolder: tokenizerFolder)

        self.engine = newEngine
        self.tokenizer = newTokenizer
        self.loadedModelName = modelFileName
    }

    func unload() {
        // Purge composed CPU f32 + GPU caches before dropping the handle so
        // Metal buffers are released promptly (not only at last autorelease).
        engine?.trim()
        engine = nil
        tokenizer = nil
        loadedModelName = nil
        lastLoadDeviceLabel = nil
        lastLoadReasonEN = nil
        lastLoadReasonJA = nil
        JGenGPUSafety.clearRemembered()
    }

    /// ChatML (Qwen / many instruct models). Plain `role: content` caused
    /// small JGENs to ignore turn boundaries and fall into greedy phrase
    /// loops (`お元気ですか?` × N) on Japanese greetings.
    private static func formatChatML(_ conversation: [(role: String, content: String)]) -> String {
        var parts: [String] = []
        for turn in conversation {
            let role: String
            switch turn.role.lowercased() {
            case "system": role = "system"
            case "assistant": role = "assistant"
            default: role = "user"
            }
            parts.append("<|im_start|>\(role)\n\(turn.content)<|im_end|>")
        }
        parts.append("<|im_start|>assistant\n")
        return parts.joined(separator: "\n")
    }

    /// Collapse immediate phrase loops from greedy decode
    /// (`お元気ですか? お元気ですか? …` → one copy). Engine only stops on
    /// identical *token-id* runs; multi-token phrases still loop.
    nonisolated static func collapsePhraseRepetition(_ text: String) -> String {
        var result = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard result.count >= 6 else { return result }
        for _ in 0..<6 {
            let previous = result
            if let regex = try? NSRegularExpression(pattern: #"(.{3,48}?)\1{2,}"#, options: []) {
                let range = NSRange(result.startIndex..., in: result)
                result = regex.stringByReplacingMatches(
                    in: result, options: [], range: range, withTemplate: "$1")
            }
            if let regex = try? NSRegularExpression(
                pattern: #"(.{3,48}?)(?:[ \t\n\r]+?\1){2,}"#, options: []
            ) {
                let range = NSRange(result.startIndex..., in: result)
                result = regex.stringByReplacingMatches(
                    in: result, options: [], range: range, withTemplate: "$1")
            }
            result = result.trimmingCharacters(in: .whitespacesAndNewlines)
            if result == previous { break }
        }
        return result
    }

    /// True when collapsing removes most of the string (generation is looping).
    nonisolated static func isPhraseLooping(_ text: String) -> Bool {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.count >= 24 else { return false }
        let collapsed = collapsePhraseRepetition(trimmed)
        return collapsed.count * 3 <= trimmed.count
    }

    // MARK: - Reasoning models (`<think>…</think>`)

    /// Qwen3 / Qwen3.5 / Qwen3.6 reason before answering. Treating that stream
    /// as the reply is what produced `매우!!!!!!` from qwen3-4b, with council
    /// conclusions of `:` and `is` — mid-thought tokens shown as answers.
    ///
    /// Mirrors `VeraCore.ThinkingFilter` in verantyx-cli. Duplicated rather
    /// than shared because the IDE is an Xcode target and VeraCore is an SPM
    /// package; the standing plan is to link VeraCore here and delete this
    /// copy, and until then a change to one has to be made to both.
    nonisolated static let thinkOpenTags = ["<think>", "<thinking>", "<reasoning>"]
    nonisolated static let thinkCloseTags = ["</think>", "</thinking>", "</reasoning>"]

    nonisolated static func containsThinking(_ text: String) -> Bool {
        let lower = text.lowercased()
        return thinkOpenTags.contains { lower.contains($0) }
    }

    /// Splits reasoning from reply.
    ///
    /// `truncated` means the block never closed: the model was still thinking
    /// when the budget ran out, so **no answer exists**. Returning the partial
    /// thought as a reply would be inventing one, so callers get an empty
    /// answer and the truncated flag instead.
    nonisolated static func extractAnswer(_ raw: String) -> (answer: String, truncated: Bool) {
        let lower = raw.lowercased()

        // Prefer the last close tag: a model occasionally reopens thinking and
        // only the final segment is addressed to the user.
        var closeEnd: String.Index? = nil
        for tag in thinkCloseTags {
            var from = lower.startIndex
            while let r = lower.range(of: tag, range: from..<lower.endIndex) {
                closeEnd = r.upperBound
                from = r.upperBound
            }
        }
        if let closeEnd {
            let answer = String(raw[closeEnd...]).trimmingCharacters(in: .whitespacesAndNewlines)
            // Closed with nothing after it is still an unfinished turn.
            return (answer, answer.isEmpty)
        }
        for tag in thinkOpenTags where lower.contains(tag) {
            return ("", true)
        }
        return (raw.trimmingCharacters(in: .whitespacesAndNewlines), false)
    }

    /// A budget sized for a direct reply is spent entirely inside the thinking
    /// block, so the turn can never reach an answer — 96 tokens on qwen3-4b
    /// produced only `<think>`.
    nonisolated static func expandedThinkingBudget(_ base: Int) -> Int {
        max(base * 6, 512)
    }

    /// Set once a `<think>` tag is seen from the loaded model, so subsequent
    /// calls get a budget that can actually reach an answer. Learned at runtime
    /// rather than inferred from the model name.
    private(set) var isReasoningModel = false

    /// Short social openers where a full council handoff dump hurts more than
    /// it helps on 0.5B–2B models.
    nonisolated static func isSimpleGreeting(_ question: String) -> Bool {
        let t = question.trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
            .trimmingCharacters(in: .punctuationCharacters)
        let roots = [
            "こんにちは", "こんばんは", "おはよう", "おはようございます",
            "はじめまして", "やあ", "ハロー",
            "hello", "hi", "hey", "good morning", "good evening", "good afternoon"
        ]
        return roots.contains { t == $0 || (t.hasPrefix($0) && t.count <= $0.count + 8) }
    }

    /// Non-streaming generation with ChatML + phrase-loop collapse.
    func generate(conversation: [(role: String, content: String)], maxTokens: Int) throws -> String {
        guard let engine, let tokenizer else { throw ChatError.notLoaded }
        // Bound each turn — council/act already truncate, but VectorLab /
        // Vera harness callers may still pass a huge paste into ChatML.
        let bounded = PromptBudget.boundConversation(conversation)
        let requested = isReasoningModel ? Self.expandedThinkingBudget(maxTokens) : maxTokens
        let cappedMax = JGenGPUSafety.cappedMaxTokens(requested)
        let prompt = Self.formatChatML(bounded)
        let promptTokens = tokenizer.encode(text: prompt).map { UInt32($0) }
        return try withCapturePaused {
            engine.reset()
            defer { if MachineProfile.current().totalRAMGB <= 24 { engine.trim() } }
            let outputTokens = try engine.generate(prompt: promptTokens, maxTokens: cappedMax)
            let raw = tokenizer.decode(tokens: outputTokens.map { Int($0) }, skipSpecialTokens: true)
            return finishReply(raw)
        }
    }

    /// Shared tail for both generate paths: learn whether this model reasons,
    /// drop the thinking, and collapse loops in whatever answer remains.
    private func finishReply(_ raw: String) -> String {
        if !isReasoningModel, Self.containsThinking(raw) {
            isReasoningModel = true
        }
        let (answer, truncated) = Self.extractAnswer(raw)
        // Still reasoning when the budget ran out — there is no answer to
        // report, and a fragment of the thought is not one.
        if truncated { return "" }
        return Self.collapsePhraseRepetition(answer)
    }

    /// Streaming generation with ChatML. Callers should return `false` from
    /// `onToken` when `isPhraseLooping` on the accumulated text — this path
    /// also collapses the final string before return.
    func generateStreaming(
        conversation: [(role: String, content: String)], maxTokens: Int,
        onToken: @escaping (String) -> Bool
    ) throws -> String {
        guard let engine, let tokenizer else { throw ChatError.notLoaded }
        // Same turn budgets as `generate` — AgentLoop / Act used to bypass
        // PromptBudget via this path and re-introduce the paste × ChatML OOM.
        let bounded = PromptBudget.boundConversation(conversation)
        let requested = isReasoningModel ? Self.expandedThinkingBudget(maxTokens) : maxTokens
        let cappedMax = JGenGPUSafety.cappedMaxTokens(requested)
        let prompt = Self.formatChatML(bounded)
        let promptTokens = tokenizer.encode(text: prompt).map { UInt32($0) }

        return try withCapturePaused {
            engine.reset()
            defer { if MachineProfile.current().totalRAMGB <= 24 { engine.trim() } }
            var allTokens: [Int] = []
            var lastDecoded = ""
            // Suppress streaming while inside a thinking block: the chat bubble
            // should not fill with private reasoning that is not the reply.
            var insideThinking = false
            let outputTokens = try engine.generateStreaming(prompt: promptTokens, maxTokens: cappedMax) { token in
                allTokens.append(Int(token))
                let decoded = tokenizer.decode(tokens: allTokens, skipSpecialTokens: true)
                guard decoded.count > lastDecoded.count else { return true }
                let delta = String(decoded.dropFirst(lastDecoded.count))
                lastDecoded = decoded
                let (_, stillThinking) = Self.extractAnswer(decoded)
                if stillThinking {
                    insideThinking = true
                    return true
                }
                // First tokens after `</think>` — the answer starts here.
                if insideThinking {
                    insideThinking = false
                }
                return onToken(delta)
            }
            let raw = tokenizer.decode(tokens: outputTokens.map { Int($0) }, skipSpecialTokens: true)
            return finishReply(raw)
        }
    }

    // MARK: - Vector Lab (project/resynthesize/puzzle_inference/optimize_thought_in_place)
    //
    // Text-in/text-out conveniences over JCrossEngine's raw vector API, for
    // VectorLabView -- exploring what the model's hidden-state vectors
    // actually correspond to, independent of the normal chat/generate path.

    var isLoaded: Bool { engine != nil && tokenizer != nil }

    /// Tokenizes and forwards `text` through the full model, returning its
    /// final-token hidden state (a "thought vector" the rest of the Lab
    /// operates on).
    ///
    /// Long pastes are truncated first — a multi-k essay through CPU encode
    /// (GPU idle / Vera-a path) is the memory-explosion hotspot.
    func encodeText(_ text: String) throws -> [Float] {
        guard let engine, let tokenizer else { throw ChatError.notLoaded }
        let bounded = PromptBudget.truncateForEncode(text)
        let tokens = PromptBudget.capEncodeTokens(
            tokenizer.encode(text: bounded).map { UInt32($0) }
        )
        return try withCapturePaused {
            engine.reset()
            return try engine.encode(tokens: tokens)
        }
    }

    /// Decodes a vector (from `encodeText`, `optimizeVector`, or anything
    /// else) back into the single nearest token, as text.
    func resynthesizeToText(vector: [Float], layerName: String = "lm_head", temperature: Float = 1.0) throws -> String {
        guard let engine, let tokenizer else { throw ChatError.notLoaded }
        let resonated = try engine.resynthesize(layerName: layerName, vector: vector, temperature: temperature)
        let result = try engine.puzzleInference(layerName: layerName, vector: resonated)
        return tokenizer.decode(tokens: [Int(result.token)], skipSpecialTokens: true)
    }

    /// Milestone P: text-in/text-out convenience over `JCrossEngine.
    /// injectMultiLayer` -- tokenizes `prompt`, encodes each intervention's
    /// `textLabel` into a vector via `encodeText` (this is the "shared
    /// basis": Vera has no embedding space of its own, so its state
    /// descriptions get turned into vectors by asking JGEN itself), injects
    /// them all in one forward pass, and decodes each observed layer's
    /// snapshot back to its nearest token via `puzzleInferenceText` so the
    /// caller gets human-readable text, never a raw vector.
    func reflect(
        prompt: String,
        interventions: [(layer: Int, textLabel: String, alpha: Float)],
        observeLayers: [Int]
    ) throws -> [Int: (text: String, entropy: Float)] {
        guard let engine, let tokenizer else { throw ChatError.notLoaded }
        // Cap prompt + intervention fan-out — Vera reflect used to encode
        // many labels + a huge prompt back-to-back without a trim.
        let boundedPrompt = PromptBudget.truncateForModel(prompt)
        let cappedIVs = Array(interventions.prefix(4)).map { iv in
            (layer: iv.layer,
             textLabel: PromptBudget.truncateForEncode(iv.textLabel),
             alpha: iv.alpha)
        }
        let promptTokens = PromptBudget.capEncodeTokens(
            tokenizer.encode(text: boundedPrompt).map { UInt32($0) }
        )
        let injections: [(layer: Int, vector: [Float], alpha: Float)] = try cappedIVs.map { iv in
            (layer: iv.layer, vector: try encodeText(iv.textLabel), alpha: iv.alpha)
        }
        return try withCapturePaused {
            engine.reset()
            let snapshots = try engine.injectMultiLayer(
                tokens: promptTokens, injections: injections, observeLayers: Array(observeLayers.prefix(8))
            )
            var out: [Int: (text: String, entropy: Float)] = [:]
            for (layer, vector) in snapshots {
                let result = try engine.puzzleInference(layerName: "lm_head", vector: vector)
                let text = tokenizer.decode(tokens: [Int(result.token)], skipSpecialTokens: true)
                out[layer] = (text, result.entropy)
            }
            if MachineProfile.current().totalRAMGB <= 24 { engine.trim() }
            return out
        }
    }

    /// Milestone P.5 (experimental): same shape as `reflect()`, but for a
    /// single already-computed raw vector instead of a text label -- used
    /// to inject a Vision feature-print vector (see
    /// `VisualHiddenStateBridge`) directly into JGEN's hidden states, so
    /// screen understanding doesn't have to route through a vision-capable
    /// Ollama/escalation model. Vision feature-print space and JGEN's own
    /// hidden-state space were never trained against each other -- there is
    /// no projection between them, only a pad/truncate to make the
    /// dimensions line up. This is an explicit experiment in whether
    /// injecting anyway still nudges JGEN's output toward something
    /// screen-relevant, not a claim that the spaces are aligned.
    func reflectRawVector(
        prompt: String, layer: Int, vector: [Float], alpha: Float,
        observeLayers: [Int]
    ) throws -> [Int: (text: String, entropy: Float)] {
        guard let engine, let tokenizer else { throw ChatError.notLoaded }
        let boundedPrompt = PromptBudget.truncateForModel(prompt)
        let promptTokens = PromptBudget.capEncodeTokens(
            tokenizer.encode(text: boundedPrompt).map { UInt32($0) }
        )
        var fitted = vector
        if fitted.count > engine.hiddenDim {
            fitted = Array(fitted.prefix(engine.hiddenDim))
        } else if fitted.count < engine.hiddenDim {
            fitted += [Float](repeating: 0, count: engine.hiddenDim - fitted.count)
        }
        return try withCapturePaused {
            engine.reset()
            let snapshots = try engine.injectMultiLayer(
                tokens: promptTokens, injections: [(layer: layer, vector: fitted, alpha: alpha)],
                observeLayers: Array(observeLayers.prefix(8))
            )
            var out: [Int: (text: String, entropy: Float)] = [:]
            for (layer, vec) in snapshots {
                let result = try engine.puzzleInference(layerName: "lm_head", vector: vec)
                let text = tokenizer.decode(tokens: [Int(result.token)], skipSpecialTokens: true)
                out[layer] = (text, result.entropy)
            }
            if MachineProfile.current().totalRAMGB <= 24 { engine.trim() }
            return out
        }
    }

    /// The "entropy lock": the single most-confident token a vector
    /// currently decodes to, plus how confident (lower entropy = more
    /// confident), as text + a raw entropy number for a UI to display.
    func puzzleInferenceText(vector: [Float], layerName: String = "lm_head") throws -> (text: String, entropy: Float) {
        guard let engine, let tokenizer else { throw ChatError.notLoaded }
        let result = try engine.puzzleInference(layerName: layerName, vector: vector)
        let text = tokenizer.decode(tokens: [Int(result.token)], skipSpecialTokens: true)
        return (text, result.entropy)
    }

    /// Refines a vector via latent gradient descent, returning the refined
    /// vector alongside its decoded text and final entropy so a UI can
    /// show before/after in one call.
    func optimizeVector(_ vector: [Float], layerName: String = "lm_head", maxSteps: Int, lr: Float) throws -> (vector: [Float], text: String, entropy: Float) {
        guard let engine, let tokenizer else { throw ChatError.notLoaded }
        let (refined, entropy) = try engine.optimizeThoughtInPlace(layerName: layerName, vector: vector, maxSteps: maxSteps, lr: lr)
        let result = try engine.puzzleInference(layerName: layerName, vector: refined)
        let text = tokenizer.decode(tokens: [Int(result.token)], skipSpecialTokens: true)
        return (refined, text, entropy)
    }

    // MARK: - Council (Milestone D)

    /// Tokenizes `text` and forwards it with `softVectors` prepended as
    /// virtual embedding-space tokens (`encode_soft`) -- used by
    /// `CouncilOrchestrator` to re-inject a consensus (and optionally a
    /// "stolen plan") vector into a role for the next deliberation round,
    /// instead of that role starting fresh from plain text each time.
    func encodeSoftText(softVectors: [[Float]], text: String) throws -> [Float] {
        guard let engine, let tokenizer else { throw ChatError.notLoaded }
        let bounded = PromptBudget.truncateForEncode(text)
        let tokens = PromptBudget.capEncodeTokens(
            tokenizer.encode(text: bounded).map { UInt32($0) }
        )
        // Soft vectors themselves can balloon residency — keep a small prefix.
        let soft = Array(softVectors.prefix(16))
        return try withCapturePaused {
            engine.reset()
            return try engine.encodeSoft(softVectors: soft, tokens: tokens)
        }
    }

    // MARK: - Milestone E: full Council port primitives

    struct TopKText {
        let tokenId: UInt32
        let text: String
        let prob: Float
    }

    /// Decoded top-K vocabulary distribution for `vector` -- the primitive
    /// `DivergencePacket`/`DivergenceExchange`/`SoftSequence` are all built
    /// on, since a faithful Council port needs more than the single argmax
    /// token `puzzleInferenceText` returns.
    func topKDistributionText(vector: [Float], layerName: String = "lm_head", k: Int = 16) throws -> [TopKText] {
        guard let engine, let tokenizer else { throw ChatError.notLoaded }
        let entries = try engine.topKDistribution(layerName: layerName, vector: vector, k: k)
        return entries.map { entry in
            TopKText(
                tokenId: entry.tokenId,
                text: tokenizer.decode(tokens: [Int(entry.tokenId)], skipSpecialTokens: true),
                prob: entry.prob
            )
        }
    }

    /// Tokenizes `text` into raw token ids without running a forward pass --
    /// used by `role_tokens()`-style prompt construction and by
    /// `dist_to_soft_sequence`, which needs to tokenize candidate strings to
    /// look up their embedding rows.
    func tokenize(_ text: String) throws -> [UInt32] {
        guard let tokenizer else { throw ChatError.notLoaded }
        return tokenizer.encode(text: text).map { UInt32($0) }
    }

    /// A single token's raw input-embedding row, for soft-token sequence
    /// construction.
    func embeddingRow(tokenId: UInt32) throws -> [Float] {
        guard let engine else { throw ChatError.notLoaded }
        return try engine.embeddingRow(tokenId: tokenId)
    }

    /// Forwards `tokens` through the model with `softVectors` prepended as
    /// virtual embedding-space tokens -- the same primitive as
    /// `encodeSoftText`, but taking pre-tokenized ids (Council's
    /// `role_tokens()`-built prompts) instead of re-tokenizing a text
    /// string each round.
    func encodeSoftTokens(softVectors: [[Float]], tokens: [UInt32]) throws -> [Float] {
        guard let engine else { throw ChatError.notLoaded }
        let capped = PromptBudget.capEncodeTokens(tokens)
        let soft = Array(softVectors.prefix(16))
        return try withCapturePaused {
            engine.reset()
            return try engine.encodeSoft(softVectors: soft, tokens: capped)
        }
    }

    /// Forwards pre-tokenized `tokens` through the full model, returning the
    /// final-token hidden state -- same as `encodeText`, but for callers
    /// that already tokenized (Council's round-0 `role_tokens()` prompts).
    func encodeTokens(_ tokens: [UInt32]) throws -> [Float] {
        guard let engine else { throw ChatError.notLoaded }
        let capped = PromptBudget.capEncodeTokens(tokens)
        return try withCapturePaused {
            engine.reset()
            return try engine.encode(tokens: capped)
        }
    }

    /// Release composed weight caches without unloading the model (between
    /// council rounds / after a heavy Vera-a turn).
    // MARK: - Pipeline segments (Milestone U)

    /// Clears this side's KV and GDN state. Called by the worker on RESET.
    ///
    /// The engine's own `reset` already clears `kv_cache`, `metal_kv_cache`,
    /// `gpu_kv` and `hybrid_state`, which is exactly right for a machine holding
    /// only part of the stack: the containers are per-layer indexed and the
    /// unused slots were empty to begin with.
    func resetEngine() {
        engine?.reset()
    }

    /// Runs layers `[startLayer, endLayer)` over a residual received from the
    /// other machine.
    ///
    /// `rawFlags` is passed through from the wire rather than re-derived, so the
    /// master decides once whether this segment ends in a token or a hidden
    /// state and both sides cannot disagree about it.
    func runSegment(
        hidden: [[Float]], startLayer: Int, endLayer: Int, startPos: Int, rawFlags: UInt32
    ) throws -> JCrossEngine.SegmentResult {
        guard let engine else { throw ChatError.notLoaded }
        return try engine.segment(
            hidden: hidden, startLayer: startLayer, endLayer: endLayer,
            startPos: startPos, flags: JCrossEngine.SegmentFlags(rawValue: rawFlags))
    }

    /// Master half: tokens in, residual (or token) out.
    func runSegment(
        tokens: [UInt32], startLayer: Int, endLayer: Int, startPos: Int, rawFlags: UInt32
    ) throws -> JCrossEngine.SegmentResult {
        guard let engine else { throw ChatError.notLoaded }
        return try engine.segment(
            tokens: tokens, startLayer: startLayer, endLayer: endLayer,
            startPos: startPos, flags: JCrossEngine.SegmentFlags(rawValue: rawFlags))
    }

    /// Layer count of the loaded model, for the split planner.
    var loadedLayerCount: Int { engine?.numLayers ?? 0 }

    /// Releases composed-weight caches and the KV cache.
    ///
    /// Refuses while a pipeline turn is in flight. `trim` clears `kv_cache`,
    /// `gpu_kv` and `hybrid_state` — which is correct between turns and
    /// catastrophic during one: this machine's slice of the KV cache vanishes
    /// and every subsequent token is computed against an empty cache, producing
    /// fluent, wrong text with no error and no crash. It is the second of the
    /// two silent-corruption modes in this design (the first being a turn that
    /// starts without a RESET ack), and unlike that one it is entirely internal
    /// — no network involved, so nothing else would surface it.
    ///
    /// Skipping a trim costs memory that gets reclaimed at the next turn
    /// boundary. Performing one mid-turn costs the answer.
    @discardableResult
    func trimMemory() -> Bool {
        guard pipelineTurnsInFlight == 0 else { return false }
        engine?.trim()
        return true
    }

    // MARK: - Pipeline turn guard

    private var pipelineTurnsInFlight = 0

    /// Marks a distributed turn as running. Counted rather than boolean because
    /// a Council round and a chat turn can overlap on the same engine.
    func beginPipelineTurn() { pipelineTurnsInFlight += 1 }
    func endPipelineTurn() { pipelineTurnsInFlight = max(0, pipelineTurnsInFlight - 1) }
    var isPipelineTurnInFlight: Bool { pipelineTurnsInFlight > 0 }
}
