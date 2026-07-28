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

    private let convertedModelsDir = "/Users/motonishikoudai/Projects/verantyx-cli/converted_models"

    private init() {}

    enum ChatError: Error, LocalizedError {
        case notLoaded
        case metaNotFound(String)
        case tokenizerPathMissing(String)

        var errorDescription: String? {
            switch self {
            case .notLoaded:
                return "No JGEN model loaded -- load one in Settings → JGEN first."
            case .metaNotFound(let path):
                return "Missing .meta.json sidecar for \(path) -- was this .jgen produced by jgen_forge.py?"
            case .tokenizerPathMissing(let path):
                return "\(path).meta.json has no \"tokenizer\" field -- this model was converted without a known tokenizer (e.g. --parts lexicon)."
            }
        }
    }

    /// Loads `modelFileName` (e.g. "qwen2_5_0_5b_router_full.jgen") from
    /// verantyx-cli's converted_models/, plus the tokenizer its .meta.json
    /// sidecar points at. Does real weight I/O -- call from a background
    /// context, never assume it's fast.
    func load(modelFileName: String) async throws {
        let jgenPath = "\(convertedModelsDir)/\(modelFileName)"
        let metaPath = jgenPath + ".meta.json"

        guard let metaData = FileManager.default.contents(atPath: metaPath),
              let meta = try? JSONSerialization.jsonObject(with: metaData) as? [String: Any] else {
            throw ChatError.metaNotFound(modelFileName)
        }
        guard let tokenizerPath = meta["tokenizer"] as? String else {
            throw ChatError.tokenizerPathMissing(modelFileName)
        }

        let newEngine = try JCrossEngine(path: jgenPath)
        let tokenizerFolder = URL(fileURLWithPath: tokenizerPath).deletingLastPathComponent()
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
}
