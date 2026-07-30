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

    private init() {}

    /// `JGenConverter.convertedModels` (what Settings shows) is a union of
    /// the Application Support location (bundled binary, the default) and
    /// a custom verantyx-cli checkout's `converted_models/` (only if that
    /// advanced override is on) -- so loading has to check both locations
    /// too, in the same order, or a model converted under the override
    /// wouldn't be found here.
    private func resolvedJGenPath(for modelFileName: String) async -> String {
        let appSupportPath = JGenPaths.convertedModelsDir.appendingPathComponent(modelFileName).path
        if FileManager.default.fileExists(atPath: appSupportPath) { return appSupportPath }
        let (useCustom, repoPath) = await MainActor.run {
            (JGenConverter.shared.useCustomRepo, JGenConverter.shared.repoPath)
        }
        if useCustom, !repoPath.isEmpty {
            let customPath = "\(repoPath)/converted_models/\(modelFileName)"
            if FileManager.default.fileExists(atPath: customPath) { return customPath }
        }
        return appSupportPath
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
                return "\(model) is architecture \"\(arch)\" -- JCrossEngine's Rust forward pass only supports \"standard\"/\"moe_standard\" architectures. jgen_forge still converted it as a static weight lexicon (usable in the Vector Lab's project/resynthesize), but it can't be loaded here for chat/encode/council -- pick a different (standard-architecture) model instead."
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
        let jgenPath = await resolvedJGenPath(for: modelFileName)
        let metaPath = jgenPath + ".meta.json"

        guard let metaData = FileManager.default.contents(atPath: metaPath),
              let meta = try? JSONSerialization.jsonObject(with: metaData) as? [String: Any] else {
            throw ChatError.metaNotFound(modelFileName)
        }

        // jgen_forge still converts architectures its own inference engine
        // can't run (e.g. hybrid_ssm MoE like qwen35moe) -- as a static
        // weight lexicon only. Catch that here with a clear explanation
        // rather than letting it fail confusingly on the tokenizer step
        // (a lexicon-only conversion's "tokenizer" is often just a raw
        // GGUF vocab sidecar, not a real one).
        if let arch = meta["arch"] as? String, !["standard", "moe_standard"].contains(arch) {
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

        let newEngine = try JCrossEngine(path: jgenPath)
        let newTokenizer = try await AutoTokenizer.from(modelFolder: tokenizerFolder)

        self.engine = newEngine
        self.tokenizer = newTokenizer
        self.loadedModelName = modelFileName
    }

    func unload() {
        engine = nil
        tokenizer = nil
        loadedModelName = nil
    }

    /// Non-streaming single-shot generation (Milestone B v1). Streaming is
    /// a fast-follow per the integration plan -- jcross_engine_generate
    /// returns a full token buffer in one call, not a per-token callback,
    /// so real token-by-token streaming needs an encode+sample loop that
    /// isn't built yet.
    ///
    /// Prompt formatting is deliberately plain ("role: content" per turn)
    /// rather than a model-specific chat template -- good enough to prove
    /// Milestone B's "does it generate coherent text end to end" bar;
    /// template-aware formatting can follow once that's confirmed working.
    func generate(conversation: [(role: String, content: String)], maxTokens: Int) throws -> String {
        guard let engine, let tokenizer else { throw ChatError.notLoaded }
        let prompt = conversation.map { "\($0.role): \($0.content)" }.joined(separator: "\n") + "\nassistant:"
        let promptTokens = tokenizer.encode(text: prompt).map { UInt32($0) }
        engine.reset()
        let outputTokens = try engine.generate(prompt: promptTokens, maxTokens: maxTokens)
        return tokenizer.decode(tokens: outputTokens.map { Int($0) }, skipSpecialTokens: true)
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
    func encodeText(_ text: String) throws -> [Float] {
        guard let engine, let tokenizer else { throw ChatError.notLoaded }
        let tokens = tokenizer.encode(text: text).map { UInt32($0) }
        engine.reset()
        return try engine.encode(tokens: tokens)
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
        let promptTokens = tokenizer.encode(text: prompt).map { UInt32($0) }
        let injections: [(layer: Int, vector: [Float], alpha: Float)] = try interventions.map { iv in
            (layer: iv.layer, vector: try encodeText(iv.textLabel), alpha: iv.alpha)
        }
        engine.reset()
        let snapshots = try engine.injectMultiLayer(
            tokens: promptTokens, injections: injections, observeLayers: observeLayers
        )
        var out: [Int: (text: String, entropy: Float)] = [:]
        for (layer, vector) in snapshots {
            let result = try engine.puzzleInference(layerName: "lm_head", vector: vector)
            let text = tokenizer.decode(tokens: [Int(result.token)], skipSpecialTokens: true)
            out[layer] = (text, result.entropy)
        }
        return out
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
        let tokens = tokenizer.encode(text: text).map { UInt32($0) }
        engine.reset()
        return try engine.encodeSoft(softVectors: softVectors, tokens: tokens)
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
        engine.reset()
        return try engine.encodeSoft(softVectors: softVectors, tokens: tokens)
    }

    /// Forwards pre-tokenized `tokens` through the full model, returning the
    /// final-token hidden state -- same as `encodeText`, but for callers
    /// that already tokenized (Council's round-0 `role_tokens()` prompts).
    func encodeTokens(_ tokens: [UInt32]) throws -> [Float] {
        guard let engine else { throw ChatError.notLoaded }
        engine.reset()
        return try engine.encode(tokens: tokens)
    }
}
