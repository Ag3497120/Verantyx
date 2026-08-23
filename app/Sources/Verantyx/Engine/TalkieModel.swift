//
//  TalkieModel.swift
//  Verantyx
//
//  Custom MLX-Swift Implementation for the Talkie-1930 architecture.
//

import Foundation
import MLX
import MLXNN
import MLXFast
import MLXLMCommon
import MLXLLM

// MARK: - Configuration

public struct TalkieConfiguration: Codable, Sendable {
    public var modelType: String = "talkie"
    public var vocabSize: Int = 65536
    public var nLayer: Int = 40
    public var nHead: Int = 40
    public var nKvHead: Int = 40
    public var nEmbd: Int = 5120
    public var headDim: Int = 128
    
    public struct QuantizationConfig: Codable, Sendable {
        public var groupSize: Int?
        public var bits: Int?
        
        enum CodingKeys: String, CodingKey {
            case groupSize = "group_size"
            case bits = "bits"
        }
    }
    public var quantizationConfig: QuantizationConfig?
    
    enum CodingKeys: String, CodingKey {
        case modelType = "model_type"
        case vocabSize = "vocab_size"
        case nLayer = "num_hidden_layers"
        case nHead = "num_attention_heads"
        case nKvHead = "num_key_value_heads"
        case nEmbd = "hidden_size"
        case headDim = "head_dim"
        case quantizationConfig = "quantization_config"
    }
    
    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.modelType = try container.decodeIfPresent(String.self, forKey: .modelType) ?? "talkie"
        self.vocabSize = try container.decodeIfPresent(Int.self, forKey: .vocabSize) ?? 65536
        self.nLayer = try container.decodeIfPresent(Int.self, forKey: .nLayer) ?? 40
        self.nHead = try container.decodeIfPresent(Int.self, forKey: .nHead) ?? 40
        self.nKvHead = try container.decodeIfPresent(Int.self, forKey: .nKvHead) ?? 40
        self.nEmbd = try container.decodeIfPresent(Int.self, forKey: .nEmbd) ?? 5120
        self.headDim = try container.decodeIfPresent(Int.self, forKey: .headDim) ?? 128
        self.quantizationConfig = try container.decodeIfPresent(QuantizationConfig.self, forKey: .quantizationConfig)
    }
}

// MARK: - Utilities

private func rmsNorm(_ x: MLXArray, eps: Float = 1e-5) -> MLXArray {
    return x * rsqrt(x.square().mean(axes: [-1], keepDims: true) + eps)
}

private func createTalkieCausalMask(_ N: Int, offset: Int = 0, dtype: DType = .float32) -> MLXArray {
    let maskBool = createCausalMask(n: N, offset: offset)
    let zero = MLXArray(0, dtype: dtype)
    let neginf = MLXArray(-Float.infinity, dtype: dtype)
    return MLX.where(maskBool, zero, neginf)
}

// MARK: - Modules

class ActGain: Module {
    @ParameterInfo(key: "a_g") var aG: MLXArray

    init(_ initValue: Float) {
        self._aG.wrappedValue = MLXArray([initValue])
        super.init()
    }

    func callAsFunction(_ x: MLXArray) -> MLXArray {
        return x * aG
    }
}

class HeadGain: Module {
    @ParameterInfo(key: "head_g") var headG: MLXArray

    init(nHead: Int) {
        self._headG.wrappedValue = MLX.ones([nHead])
        super.init()
    }

    func callAsFunction(_ x: MLXArray) -> MLXArray {
        return x * headG.reshaped(1, -1, 1, 1)
    }
}

class WeightGain: Module {
    @ParameterInfo(key: "w_g") var wG: MLXArray

    override init() {
        self._wG.wrappedValue = MLXArray([1.0])
        super.init()
    }

    func callAsFunction(_ w: MLXArray) -> MLXArray {
        return w * wG
    }
}

class TalkieRoPE: Module {
    let dims: Int
    let base: Float

    init(dims: Int, base: Float = 1000000.0) {
        self.dims = dims
        self.base = base
    }

    func callAsFunction(_ x: MLXArray, offset: Int = 0) -> MLXArray {
        let seqLen = x.dim(2)
        let dtype = x.dtype
        let xFloat = x.asType(.float32)
        
        let d = dims / 2
        let x1 = xFloat[0..., 0..., 0..., 0..<d]
        let x2 = xFloat[0..., 0..., 0..., d...]
        
        let t = MLXArray(stride(from: Float(offset), to: Float(offset + seqLen), by: 1.0))
        let channelRange = MLXArray(stride(from: 0.0, to: Float(dims), by: 2.0))
        let invFreq = 1.0 / pow(base, channelRange / Float(dims))
        
        let freqs = matmul(t.expandedDimensions(axis: 1), invFreq.expandedDimensions(axis: 0))
        let cos = MLX.cos(freqs).reshaped(1, 1, seqLen, d)
        let sin = MLX.sin(freqs).reshaped(1, 1, seqLen, d)
        
        let y1 = x1 * cos + x2 * sin
        let y2 = x1 * (-sin) + x2 * cos
        
        return concatenated([y1, y2], axis: -1).asType(dtype)
    }
}

class TalkieAttention: Module {
    let nHead: Int
    let nKvHead: Int
    let headDim: Int
    
    @ModuleInfo(key: "attn_query") var attnQuery: Linear
    @ModuleInfo(key: "attn_key") var attnKey: Linear
    @ModuleInfo(key: "attn_value") var attnValue: Linear
    @ModuleInfo(key: "attn_resid") var attnResid: Linear
    @ModuleInfo(key: "head_gain") var headGain: HeadGain
    let rope: TalkieRoPE

    init(_ config: TalkieConfiguration) {
        self.nHead = config.nHead
        self.nKvHead = config.nKvHead
        self.headDim = config.headDim
        let nState = config.nEmbd

        self._attnQuery.wrappedValue = Linear(nState, config.nHead * config.headDim, bias: false)
        self._attnKey.wrappedValue = Linear(nState, config.nKvHead * config.headDim, bias: false)
        self._attnValue.wrappedValue = Linear(nState, config.nKvHead * config.headDim, bias: false)
        self._attnResid.wrappedValue = Linear(config.nHead * config.headDim, nState, bias: false)
        self._headGain.wrappedValue = HeadGain(nHead: config.nHead)
        self.rope = TalkieRoPE(dims: config.headDim, base: 1000000.0)
        super.init()
    }

    func callAsFunction(_ x: MLXArray, mask: MLXArray?, cache: KVCache? = nil) -> MLXArray {
        let B = x.dim(0)
        let L = x.dim(1)
        let nH = self.nHead
        let nKv = self.nKvHead
        let hD = self.headDim

        var q = attnQuery(x).reshaped(B, L, nH, hD).transposed(axes: [0, 2, 1, 3])
        var k = attnKey(x).reshaped(B, L, nKv, hD).transposed(axes: [0, 2, 1, 3])
        var v = attnValue(x).reshaped(B, L, nKv, hD).transposed(axes: [0, 2, 1, 3])
        if let cache {
            q = rope(q, offset: cache.offset)
            k = rope(k, offset: cache.offset)
            let updated = cache.update(keys: k, values: v)
            k = updated.0
            v = updated.1
        } else {
            q = rope(q)
            k = rope(k)
        }

        q = rmsNorm(q, eps: 1e-5)
        k = rmsNorm(k, eps: 1e-5)
        q = headGain(q)

        if nKv < nH {
            let repeats = nH / nKv
            k = tiled(k, repetitions: [1, repeats, 1, 1])
            v = tiled(v, repetitions: [1, repeats, 1, 1])
        }

        let smScale = pow(Float(hD), -0.5)

        // Using standard MLXFast scaledDotProductAttention for high performance
        let vHat = MLXFast.scaledDotProductAttention(
            queries: q, keys: k, values: v,
            scale: smScale,
            mask: mask
        )

        let out = attnResid(vHat.transposed(axes: [0, 2, 1, 3]).reshaped(B, L, -1))
        return out
    }
}

class TalkieMLP: Module {
    @ModuleInfo(key: "mlp_gate") var mlpGate: Linear
    @ModuleInfo(key: "mlp_linear") var mlpLinear: Linear
    @ModuleInfo(key: "mlp_resid") var mlpResid: Linear

    init(_ config: TalkieConfiguration) {
        let nState = config.nEmbd
        let nMlp = Int(round(((8.0 / 3.0) * Float(nState)) / 128.0) * 128.0)

        self._mlpGate.wrappedValue = Linear(nState, nMlp, bias: false)
        self._mlpLinear.wrappedValue = Linear(nState, nMlp, bias: false)
        self._mlpResid.wrappedValue = Linear(nMlp, nState, bias: false)
        super.init()
    }

    func callAsFunction(_ x: MLXArray) -> MLXArray {
        let gate = mlpGate(x).asType(.float32)
        let linear = mlpLinear(x).asType(.float32)
        let hidden = MLXNN.silu(gate) * linear
        return mlpResid(hidden.asType(x.dtype))
    }
}

class TalkieBlock: Module {
    let layerIdx: Int
    
    @ModuleInfo(key: "attn") var attn: TalkieAttention
    @ModuleInfo(key: "attn_gain") var attnGain: ActGain
    @ModuleInfo(key: "mlp") var mlp: TalkieMLP
    @ModuleInfo(key: "mlp_gain") var mlpGain: ActGain
    @ModuleInfo(key: "embed_skip") var embedSkip: ActGain

    init(_ config: TalkieConfiguration, layerIdx: Int) {
        self.layerIdx = layerIdx
        self._attn.wrappedValue = TalkieAttention(config)
        self._attnGain.wrappedValue = ActGain(pow(Float(2 * config.nLayer), -0.5))
        self._mlp.wrappedValue = TalkieMLP(config)
        self._mlpGain.wrappedValue = ActGain(pow(Float(2 * config.nLayer), -0.5))
        self._embedSkip.wrappedValue = ActGain(0.0)
        super.init()
    }

    func callAsFunction(_ eX: MLXArray, _ x: MLXArray, mask: MLXArray?, cache: KVCache? = nil) -> MLXArray {
        var out = x
        let attnOut = attn(rmsNorm(out, eps: 1e-5), mask: mask, cache: cache)
        out = out + attnGain(attnOut)
        
        let mlpOut = mlp(rmsNorm(out, eps: 1e-5))
        out = out + mlpGain(mlpOut)
        out = out + embedSkip(eX)
        
        return out
    }
}

// MARK: - Main Model

public class TalkieModel: Module, LLMModel, KVCacheDimensionProvider {
    public let modelType: String
    public let vocabularySize: Int
    public let kvHeads: [Int]

    @ModuleInfo(key: "embed") var embedTokens: Embedding
    @ModuleInfo(key: "blocks") var blocks: [TalkieBlock]
    @ParameterInfo(key: "lm_head") var lmHead: MLXArray
    @ModuleInfo(key: "lm_head_gain") var lmHeadGain: WeightGain

    private let config: TalkieConfiguration

    public init(_ config: TalkieConfiguration) {
        self.config = config
        self.modelType = config.modelType
        self.vocabularySize = config.vocabSize
        self.kvHeads = Array(repeating: config.nKvHead, count: config.nLayer)

        self._embedTokens.wrappedValue = Embedding(embeddingCount: config.vocabSize, dimensions: config.nEmbd)
        self._blocks.wrappedValue = (0..<config.nLayer).map { TalkieBlock(config, layerIdx: $0) }
        
        // Ensure lm_head tensor defaults to zeros for updating
        self._lmHead.wrappedValue = MLX.zeros([config.vocabSize, config.nEmbd])
        self._lmHeadGain.wrappedValue = WeightGain()
        
        super.init()
        
        if let qConfig = config.quantizationConfig, let groupSize = qConfig.groupSize, let bits = qConfig.bits {
            MLXNN.quantize(model: self, groupSize: groupSize, bits: bits)
        }
    }

    public func callAsFunction(_ inputs: MLXArray, cache: [KVCache]? = nil) -> MLXArray {
        var x = embedTokens(inputs).asType(.float32)
        x = rmsNorm(x, eps: 1e-5)
        let eX = x

        let seqLen = x.dim(1)
        let cache: [KVCache?] = cache ?? Array(repeating: nil, count: blocks.count)

        var mask: MLXArray? = nil
        if cache[0] == nil || cache[0]!.offset == 0 {
            if seqLen > 1 {
                mask = createTalkieCausalMask(seqLen, dtype: x.dtype)
            }
        }

        for (i, block) in blocks.enumerated() {
            x = block(eX, x, mask: mask, cache: cache[i])
        }

        x = rmsNorm(x, eps: 1e-5)

        // Select the last token for text generation optimization if not prompting
        let lastX = x[0..., -1, 0...].expandedDimensions(axis: 1)
        let w = lmHeadGain(lmHead).transposed()
        let logits = matmul(lastX, w)
        return logits
    }
    
    // Conformance to LanguageModel sanitize method if needed
    public func sanitize(weights: [String : MLXArray]) -> [String : MLXArray] {
        return weights
    }

    public func newCache(parameters: GenerateParameters?) -> [any KVCache] {
        return (0..<config.nLayer).map { _ in StandardKVCache() }
    }
}

extension TalkieModel: LoRAModel {
    public func loraLinearLayers() -> LoRALinearLayers {
        blocks.map { layer in
            (layer.attn, ["attn_query", "attn_key", "attn_value", "attn_resid"])
        }
    }
}