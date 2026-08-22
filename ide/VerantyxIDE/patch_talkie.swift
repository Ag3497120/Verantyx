import Foundation

let path = "Sources/Verantyx/Engine/TalkieModel.swift"
var content = try! String(contentsOfFile: path)

// 1. Add MLXLLM import
content = content.replacingOccurrences(of: "import MLXLMCommon", with: "import MLXLMCommon\nimport MLXLLM")

// 2. Fix access levels
content = content.replacingOccurrences(of: "private class ActGain", with: "fileprivate class ActGain")
content = content.replacingOccurrences(of: "private class HeadGain", with: "fileprivate class HeadGain")
content = content.replacingOccurrences(of: "private class WeightGain", with: "fileprivate class WeightGain")
content = content.replacingOccurrences(of: "private class TalkieRoPE", with: "fileprivate class TalkieRoPE")
content = content.replacingOccurrences(of: "private class TalkieAttention", with: "fileprivate class TalkieAttention")
content = content.replacingOccurrences(of: "private class TalkieMLP", with: "fileprivate class TalkieMLP")
content = content.replacingOccurrences(of: "private class TalkieBlock", with: "fileprivate class TalkieBlock")

// 3. Fix override init
content = content.replacingOccurrences(of: "init() {\n        self._wG.wrappedValue = MLXArray([1.0])\n        super.init()\n    }", with: "override init() {\n        self._wG.wrappedValue = MLXArray([1.0])\n        super.init()\n    }")

// 4. Fix createCausalMask
content = content.replacingOccurrences(of: "MLX.createCausalMask", with: "createCausalMask")

// 5. Fix xFloat slicing
content = content.replacingOccurrences(of: "xFloat[..., 0 ..< d]", with: "xFloat[.ellipsis, 0 ..< d]")
content = content.replacingOccurrences(of: "xFloat[..., d ..< dims]", with: "xFloat[.ellipsis, d ..< dims]")

// 6. Fix tuple .keys/.values
content = content.replacingOccurrences(of: "k = updated.keys", with: "k = updated.0")
content = content.replacingOccurrences(of: "v = updated.values", with: "v = updated.1")

// 7. Fix KVCache array
content = content.replacingOccurrences(of: "let cache = cache ?? Array(repeating: nil, count: blocks.count)", with: "let cache: [KVCache?] = cache ?? Array(repeating: nil, count: blocks.count)")

// 8. Fix lastX slicing
content = content.replacingOccurrences(of: "let lastX = x[0..., -1..., 0...]", with: "let lastX = x[.ellipsis, -1].expandedDimensions(axis: 1)")

try! content.write(toFile: path, atomically: true, encoding: .utf8)
