import Foundation

let path = "Sources/Verantyx/Engine/TalkieModel.swift"
var content = try! String(contentsOfFile: path, encoding: .utf8)

// 1. Remove fileprivate from classes
content = content.replacingOccurrences(of: "fileprivate class ActGain", with: "class ActGain")
content = content.replacingOccurrences(of: "fileprivate class HeadGain", with: "class HeadGain")
content = content.replacingOccurrences(of: "fileprivate class WeightGain", with: "class WeightGain")
content = content.replacingOccurrences(of: "fileprivate class TalkieRoPE", with: "class TalkieRoPE")
content = content.replacingOccurrences(of: "fileprivate class TalkieAttention", with: "class TalkieAttention")
content = content.replacingOccurrences(of: "fileprivate class TalkieMLP", with: "class TalkieMLP")
content = content.replacingOccurrences(of: "fileprivate class TalkieBlock", with: "class TalkieBlock")

// 2. Add LoRAModel conformance
let loraExtension = """

extension TalkieModel: LoRAModel {
    public func loraLinearLayers() -> LoRALinearLayers {
        blocks.map { layer in
            (layer.attn, ["attn_query", "attn_key", "attn_value", "attn_resid"])
        }
    }
}
"""
content.append(loraExtension)

try! content.write(toFile: path, atomically: true, encoding: .utf8)
