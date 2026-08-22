import Foundation

let path = "Sources/Verantyx/Engine/TalkieModel.swift"
var content = try! String(contentsOfFile: path, encoding: .utf8)

// Add nKvHead to TalkieConfiguration
content = content.replacingOccurrences(of: "public var nHead: Int = 40\n    public var nEmbd: Int = 5120", with: "public var nHead: Int = 40\n    public var nKvHead: Int = 40\n    public var nEmbd: Int = 5120")
content = content.replacingOccurrences(of: "case nHead = \"n_head\"\n        case nEmbd = \"n_embd\"", with: "case nHead = \"num_attention_heads\"\n        case nKvHead = \"num_key_value_heads\"\n        case nEmbd = \"hidden_size\"")

// Wait, the config uses different names: num_attention_heads, num_key_value_heads, hidden_size, num_hidden_layers!
// Let's replace the whole TalkieConfiguration!
