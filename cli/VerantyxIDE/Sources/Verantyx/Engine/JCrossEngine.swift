import Foundation

/// Thin Swift wrapper over the jcross_engine_glm Rust C-ABI (see
/// jcross_engine.h / Verantyx-Bridging-Header.h), mirroring
/// verantyx-cli's Python `RustBrain` class method-for-method. This is
/// Milestone A of the JGEN/RustBrain integration plan: prove the FFI
/// bridge works before wiring it in as a selectable chat backend
/// (Milestone B) or using it for vector-injection memory (Milestone C).
///
/// Not thread-safe: the Rust side uses interior mutability with no
/// locking, so calls against the same `JCrossEngine` instance must be
/// serialized by the caller (e.g. confine each instance to one actor/
/// serial queue, as OllamaClient/MLXRunner already do for their own
/// state).
final class JCrossEngine {
    enum JCrossError: Error, LocalizedError {
        case loadFailed(path: String)
        case negativeDimension
        case ffiError(function: String, code: Int32)

        var errorDescription: String? {
            switch self {
            case .loadFailed(let path):
                return "jcross_engine_create failed to load: \(path)"
            case .negativeDimension:
                return "jcross_engine returned a negative hidden_dim/num_layers"
            case .ffiError(let function, let code):
                return "\(function) failed with code \(code)\(Self.hint(for: code))"
            }
        }

        /// エラーコードだけでは何が起きたか分からないので、Rust側が返す
        /// 意味を添える。
        ///
        /// Rust は本当のエラー文を `eprintln!` で **stderr** に出しているが、
        /// GUIから起動したアプリではそれが誰にも見えない。数字だけを見せる
        /// のは調査の手掛かりを捨てているのと同じなので、少なくとも意味と
        /// 次の一手を示す。
        private static func hint(for code: Int32) -> String {
            switch code {
            case -1:
                return " — 引数がnull(エンジン未初期化の可能性)"
            case -2:
                return " — エンジン内部エラー。よくある原因: gemma4系で"
                     + "per-layer embeddings(PLE)の有無がメタ情報と実際の"
                     + "テンソルで食い違っている(再変換で直る)。"
                     + "正確な理由はターミナルから "
                     + "/Applications/Verantyx.app/Contents/MacOS/Verantyx "
                     + "で起動すると [Rust Engine] の行に出る"
            case -3:
                return " — 出力次元の不一致(モデルとエンジンの想定が違う)"
            default:
                return ""
            }
        }
    }

    private let handle: UnsafeMutableRawPointer
    let hiddenDim: Int
    let numLayers: Int

    /// Loads a .jgen model file. Throws if the file can't be found/parsed
    /// (check stderr for the Rust-side diagnostic in that case) or if the
    /// engine reports an invalid hidden_dim/num_layers.
    init(path: String) throws {
        guard let ptr = path.withCString({ jcross_engine_create($0) }) else {
            throw JCrossError.loadFailed(path: path)
        }
        self.handle = ptr

        let dim = jcross_engine_hidden_dim(ptr)
        let layers = jcross_engine_num_layers(ptr)
        guard dim > 0, layers > 0 else {
            jcross_engine_destroy(ptr)
            throw JCrossError.negativeDimension
        }
        self.hiddenDim = Int(dim)
        self.numLayers = Int(layers)
    }

    deinit {
        jcross_engine_destroy(handle)
    }

    /// Clears the KV-cache. Call before each independent generate/encode
    /// sequence that shouldn't see a prior turn's cached state.
    func reset() {
        jcross_engine_reset(handle)
    }

    /// Releases composed weight caches + KV-cache, dropping RAM back to
    /// ~mmap only. Weights recompose lazily on next use.
    func trim() {
        jcross_engine_trim(handle)
    }

    /// Greedy-generates up to `maxTokens` token ids continuing `prompt`.
    func generate(prompt: [UInt32], maxTokens: Int) throws -> [UInt32] {
        var promptCopy = prompt
        var out = [UInt32](repeating: 0, count: maxTokens)
        let written: Int32 = promptCopy.withUnsafeMutableBufferPointer { promptBuf in
            out.withUnsafeMutableBufferPointer { outBuf in
                jcross_engine_generate(
                    handle,
                    promptBuf.baseAddress, promptBuf.count,
                    maxTokens,
                    outBuf.baseAddress, outBuf.count
                )
            }
        }
        guard written >= 0 else {
            throw JCrossError.ffiError(function: "jcross_engine_generate", code: written)
        }
        return Array(out.prefix(Int(written)))
    }

    /// Same generation as `generate(prompt:maxTokens:)` -- same CPU/GPU code
    /// path, same KV-cache reuse, no performance difference -- but calls
    /// `onToken` synchronously after each token is decided, so a caller can
    /// show real per-token progress instead of blocking silently until the
    /// whole (possibly very long) generation finishes. Return `false` from
    /// `onToken` to stop generation early.
    func generateStreaming(prompt: [UInt32], maxTokens: Int, onToken: @escaping (UInt32) -> Bool) throws -> [UInt32] {
        var promptCopy = prompt
        var out = [UInt32](repeating: 0, count: maxTokens)

        // Bridges the Swift closure to the C function-pointer callback: box
        // it so a single opaque `ctx` pointer can carry it across the FFI
        // boundary, and unbox inside a non-capturing `@convention(c)`
        // trampoline (C function pointers cannot capture Swift context
        // directly).
        final class CallbackBox { let onToken: (UInt32) -> Bool; init(_ f: @escaping (UInt32) -> Bool) { onToken = f } }
        let box = CallbackBox(onToken)
        let ctx = Unmanaged.passRetained(box).toOpaque()
        defer { Unmanaged<CallbackBox>.fromOpaque(ctx).release() }

        let trampoline: @convention(c) (UnsafeMutableRawPointer?, UInt32) -> Int32 = { ctxPtr, token in
            guard let ctxPtr else { return 1 }
            let box = Unmanaged<CallbackBox>.fromOpaque(ctxPtr).takeUnretainedValue()
            return box.onToken(token) ? 1 : 0
        }

        let written: Int32 = promptCopy.withUnsafeMutableBufferPointer { promptBuf in
            out.withUnsafeMutableBufferPointer { outBuf in
                jcross_engine_generate_streaming(
                    handle,
                    promptBuf.baseAddress, promptBuf.count,
                    maxTokens,
                    trampoline, ctx,
                    outBuf.baseAddress, outBuf.count
                )
            }
        }
        guard written >= 0 else {
            throw JCrossError.ffiError(function: "jcross_engine_generate_streaming", code: written)
        }
        return Array(out.prefix(Int(written)))
    }

    /// Forwards `tokens` through the full model, returning the final-token,
    /// post-final-norm hidden state (length == hiddenDim).
    func encode(tokens: [UInt32]) throws -> [Float] {
        var tokensCopy = tokens
        var out = [Float](repeating: 0, count: hiddenDim)
        let code: Int32 = tokensCopy.withUnsafeMutableBufferPointer { tokBuf in
            out.withUnsafeMutableBufferPointer { outBuf in
                jcross_engine_encode(handle, tokBuf.baseAddress, tokBuf.count, outBuf.baseAddress, outBuf.count)
            }
        }
        guard code == 0 else {
            throw JCrossError.ffiError(function: "jcross_engine_encode", code: code)
        }
        return out
    }

    /// Same as `encode`, but prepends `softVectors` (each of length
    /// hiddenDim) as virtual "soft tokens" before `tokens` -- the vector-
    /// communication injection path used for Milestone C's memory
    /// blending, letting accumulated context enter as embedding-space
    /// vectors instead of text tokens.
    func encodeSoft(softVectors: [[Float]], tokens: [UInt32]) throws -> [Float] {
        var flatSoft = softVectors.flatMap { $0 }
        var tokensCopy = tokens
        var out = [Float](repeating: 0, count: hiddenDim)
        let code: Int32 = flatSoft.withUnsafeMutableBufferPointer { softBuf in
            tokensCopy.withUnsafeMutableBufferPointer { tokBuf in
                out.withUnsafeMutableBufferPointer { outBuf in
                    jcross_engine_encode_soft(
                        handle,
                        softBuf.baseAddress, softVectors.count, hiddenDim,
                        tokBuf.baseAddress, tokBuf.count,
                        outBuf.baseAddress, outBuf.count
                    )
                }
            }
        }
        guard code == 0 else {
            throw JCrossError.ffiError(function: "jcross_engine_encode_soft", code: code)
        }
        return out
    }

    /// Dumps the last-token hidden state after each of `layers` (a layer
    /// index equal to numLayers means post-final-norm). Returns one
    /// hiddenDim-length vector per requested layer, in the same order.
    func encodeLayers(tokens: [UInt32], layers: [Int]) throws -> [[Float]] {
        var tokensCopy = tokens
        var layersCopy = layers.map { UInt32($0) }
        var out = [Float](repeating: 0, count: layers.count * hiddenDim)
        let code: Int32 = tokensCopy.withUnsafeMutableBufferPointer { tokBuf in
            layersCopy.withUnsafeMutableBufferPointer { layerBuf in
                out.withUnsafeMutableBufferPointer { outBuf in
                    jcross_engine_encode_layers(
                        handle,
                        tokBuf.baseAddress, tokBuf.count,
                        layerBuf.baseAddress, layerBuf.count,
                        outBuf.baseAddress, outBuf.count
                    )
                }
            }
        }
        guard code == 0 else {
            throw JCrossError.ffiError(function: "jcross_engine_encode_layers", code: code)
        }
        return (0..<layers.count).map { i in
            Array(out[(i * hiddenDim)..<((i + 1) * hiddenDim)])
        }
    }

    /// Blends `vector` (length hiddenDim) into the residual stream
    /// immediately before `layer`, continues the forward pass to the
    /// final norm, and returns the resulting last-token hidden state.
    /// `alpha` = 1.0 replaces the residual at that point; 0.0 is a no-op.
    /// This is the "surgical" hidden-state intervention path used for
    /// Milestone C's memory blending as an alternative to `encodeSoft`.
    func injectAtLayer(tokens: [UInt32], layer: Int, vector: [Float], alpha: Float = 1.0) throws -> [Float] {
        var tokensCopy = tokens
        var vectorCopy = vector
        var out = [Float](repeating: 0, count: hiddenDim)
        let code: Int32 = tokensCopy.withUnsafeMutableBufferPointer { tokBuf in
            vectorCopy.withUnsafeMutableBufferPointer { vecBuf in
                out.withUnsafeMutableBufferPointer { outBuf in
                    jcross_engine_inject_at_layer(
                        handle,
                        tokBuf.baseAddress, tokBuf.count,
                        UInt32(layer),
                        vecBuf.baseAddress, vecBuf.count,
                        alpha,
                        outBuf.baseAddress, outBuf.count
                    )
                }
            }
        }
        guard code == 0 else {
            throw JCrossError.ffiError(function: "jcross_engine_inject_at_layer", code: code)
        }
        return out
    }

    /// Milestone P: blends MULTIPLE (layer, vector, alpha) injections into
    /// ONE forward pass, and returns the residual snapshot at each
    /// requested observe layer -- the primitive behind Vera's hidden-state
    /// "reflection" tool (see JGenAgentServer's /jgen/inject_multi_layer).
    /// `injections` may be empty to just observe without injecting.
    /// Returns a dictionary keyed by observe layer index (not an array --
    /// callers shouldn't need to track index<->layer correspondence
    /// themselves).
    func injectMultiLayer(
        tokens: [UInt32],
        injections: [(layer: Int, vector: [Float], alpha: Float)],
        observeLayers: [Int]
    ) throws -> [Int: [Float]] {
        guard !observeLayers.isEmpty else { return [:] }
        var tokensCopy = tokens
        var injectLayersCopy = injections.map { UInt32($0.layer) }
        var injectVecsFlat = injections.flatMap { $0.vector }
        var alphasCopy = injections.map { $0.alpha }
        var observeLayersCopy = observeLayers.map { UInt32($0) }
        var out = [Float](repeating: 0, count: observeLayers.count * hiddenDim)

        let code: Int32 = tokensCopy.withUnsafeMutableBufferPointer { tokBuf in
            injectLayersCopy.withUnsafeMutableBufferPointer { injLayerBuf in
                injectVecsFlat.withUnsafeMutableBufferPointer { injVecBuf in
                    alphasCopy.withUnsafeMutableBufferPointer { alphaBuf in
                        observeLayersCopy.withUnsafeMutableBufferPointer { obsBuf in
                            out.withUnsafeMutableBufferPointer { outBuf in
                                jcross_engine_inject_multi_layer(
                                    handle,
                                    tokBuf.baseAddress, tokBuf.count,
                                    injections.isEmpty ? nil : injLayerBuf.baseAddress,
                                    injections.isEmpty ? nil : injVecBuf.baseAddress,
                                    injections.isEmpty ? nil : alphaBuf.baseAddress,
                                    injLayerBuf.count,
                                    obsBuf.baseAddress, obsBuf.count,
                                    outBuf.baseAddress, outBuf.count
                                )
                            }
                        }
                    }
                }
            }
        }
        guard code == 0 else {
            throw JCrossError.ffiError(function: "jcross_engine_inject_multi_layer", code: code)
        }
        var result: [Int: [Float]] = [:]
        for (i, layer) in observeLayers.enumerated() {
            result[layer] = Array(out[(i * hiddenDim)..<((i + 1) * hiddenDim)])
        }
        return result
    }

    /// SVD-projects `vector` (length hiddenDim) through `layerName`'s
    /// low-rank factors -- a lightweight transformation/comparison in the
    /// model's own learned subspace, without a full forward pass.
    func project(layerName: String, vector: [Float]) throws -> [Float] {
        var vectorCopy = vector
        var out = [Float](repeating: 0, count: hiddenDim)
        let code: Int32 = layerName.withCString { namePtr in
            vectorCopy.withUnsafeMutableBufferPointer { vecBuf in
                out.withUnsafeMutableBufferPointer { outBuf in
                    jcross_engine_project(handle, namePtr, vecBuf.baseAddress, vecBuf.count, outBuf.baseAddress, outBuf.count)
                }
            }
        }
        guard code == 0 else {
            throw JCrossError.ffiError(function: "jcross_engine_project", code: code)
        }
        return out
    }

    /// "Telepathic resonance": iteratively projects `vector` toward the
    /// token manifold via `layerName` (typically "lm_head") -- decodes an
    /// arbitrary vector (not necessarily one that came from a real forward
    /// pass, e.g. a blended/optimized "thought") back into the model's
    /// concept space.
    func resynthesize(layerName: String = "lm_head", vector: [Float], temperature: Float = 1.0) throws -> [Float] {
        var vectorCopy = vector
        var out = [Float](repeating: 0, count: hiddenDim)
        let code: Int32 = layerName.withCString { namePtr in
            vectorCopy.withUnsafeMutableBufferPointer { vecBuf in
                out.withUnsafeMutableBufferPointer { outBuf in
                    jcross_engine_resynthesize(handle, namePtr, vecBuf.baseAddress, vecBuf.count, temperature, outBuf.baseAddress, outBuf.count)
                }
            }
        }
        guard code == 0 else {
            throw JCrossError.ffiError(function: "jcross_engine_resynthesize", code: code)
        }
        return out
    }

    struct PuzzleResult {
        let token: UInt32
        let entropy: Float
    }

    /// "Entropy lock": the single most-likely token `vector` decodes to via
    /// `layerName`, plus the distribution's entropy (lower = more
    /// confident). Use to gate whether a vector is confident enough to
    /// turn into text before ever calling `resynthesize`/`generate`.
    func puzzleInference(layerName: String, vector: [Float]) throws -> PuzzleResult {
        var vectorCopy = vector
        var outToken: UInt32 = 0
        var outEntropy: Float = 0
        let code: Int32 = layerName.withCString { namePtr in
            vectorCopy.withUnsafeMutableBufferPointer { vecBuf in
                jcross_engine_puzzle_inference(handle, namePtr, vecBuf.baseAddress, vecBuf.count, &outToken, &outEntropy)
            }
        }
        guard code == 0 else {
            throw JCrossError.ffiError(function: "jcross_engine_puzzle_inference", code: code)
        }
        return PuzzleResult(token: outToken, entropy: outEntropy)
    }

    /// "Latent gradient descent": refines `vector` in place, up to
    /// `maxSteps` steps at learning rate `lr`, to minimize entropy at
    /// `layerName` -- optimizes directly in embedding space toward a more
    /// confident "thought" rather than sampling tokens one at a time.
    /// Returns the refined vector and the final entropy.
    func optimizeThoughtInPlace(layerName: String, vector: [Float], maxSteps: Int, lr: Float, temperature: Float = 1.0) throws -> (vector: [Float], entropy: Float) {
        var vectorCopy = vector
        var outEntropy: Float = 0
        let code: Int32 = layerName.withCString { namePtr in
            vectorCopy.withUnsafeMutableBufferPointer { vecBuf in
                jcross_engine_optimize_thought_in_place(handle, namePtr, vecBuf.baseAddress, vecBuf.count, maxSteps, lr, temperature, &outEntropy)
            }
        }
        guard code == 0 else {
            throw JCrossError.ffiError(function: "jcross_engine_optimize_thought_in_place", code: code)
        }
        return (vectorCopy, outEntropy)
    }

    struct TopKEntry {
        let tokenId: UInt32
        let prob: Float
    }

    /// Full top-K vocabulary distribution (softmax over `layerName`'s
    /// logits) -- for Council's divergence-packet claims, dissent-key
    /// extraction, and soft-sequence construction, all of which need more
    /// than `puzzleInference`'s single argmax token.
    func topKDistribution(layerName: String, vector: [Float], k: Int) throws -> [TopKEntry] {
        var vectorCopy = vector
        var outIds = [UInt32](repeating: 0, count: k)
        var outProbs = [Float](repeating: 0, count: k)
        var outCount: Int = 0
        let code: Int32 = layerName.withCString { namePtr in
            vectorCopy.withUnsafeMutableBufferPointer { vecBuf in
                outIds.withUnsafeMutableBufferPointer { idBuf in
                    outProbs.withUnsafeMutableBufferPointer { probBuf in
                        jcross_engine_topk_distribution(
                            handle, namePtr, vecBuf.baseAddress, vecBuf.count, k,
                            idBuf.baseAddress, probBuf.baseAddress, &outCount
                        )
                    }
                }
            }
        }
        guard code == 0 else {
            throw JCrossError.ffiError(function: "jcross_engine_topk_distribution", code: code)
        }
        return (0..<outCount).map { TopKEntry(tokenId: outIds[$0], prob: outProbs[$0]) }
    }

    /// A single token's raw input-embedding row (length hiddenDim) -- used
    /// by `dist_to_soft_sequence`-style soft-token construction, which
    /// needs arbitrary candidate tokens' embedding rows rather than a
    /// forward pass.
    func embeddingRow(tokenId: UInt32) throws -> [Float] {
        var out = [Float](repeating: 0, count: hiddenDim)
        let code: Int32 = out.withUnsafeMutableBufferPointer { outBuf in
            jcross_engine_embedding_row(handle, tokenId, outBuf.baseAddress, outBuf.count)
        }
        guard code == 0 else {
            throw JCrossError.ffiError(function: "jcross_engine_embedding_row", code: code)
        }
        return out
    }
}
