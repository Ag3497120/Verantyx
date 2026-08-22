import Foundation

// MARK: - SimpleJCrossTranspiler
//
// バックグラウンドスレッドで安全に動作する同期変換器。
// @MainActor 依存なし・Sendable・URLSession 不使用。
// JCrossCodeTranspiler（@MainActor）の軽量代替として一括変換専用に使う。

final class SimpleJCrossTranspiler: @unchecked Sendable {

    private var counter: Int = 0
    private var symbolMap: [String: String] = [:]

    // MARK: - Static Regexes to prevent memory leaks

    private static let secretRegexes: [NSRegularExpression] = {
        let patterns = [
            #"sk_live_[a-zA-Z0-9]{20,}"#,
            #"sk_test_[a-zA-Z0-9]{20,}"#,
            #"AKIA[0-9A-Z]{16}"#,
            #"ghp_[a-zA-Z0-9]{36}"#,
            #"eyJ[a-zA-Z0-9_-]{20,}\.[a-zA-Z0-9_-]{20,}\.[a-zA-Z0-9_-]{20,}"#,
        ]
        return patterns.compactMap { try? NSRegularExpression(pattern: $0) }
    }()

    private static let identifierRegex: NSRegularExpression? = {
        try? NSRegularExpression(pattern: #"\b[a-zA-Z_][a-zA-Z0-9_]{2,}\b"#)
    }()

    // 変換結果: (jcrossContent, nodeCount, secretCount, sessionID)
    func transpile(_ source: String, fileExtension ext: String) -> (String, Int, Int, String) {
        counter = 0
        symbolMap = [:]

        let sessionID = UUID().uuidString
        let lang      = langName(for: ext)
        let keywords  = keywordSet(for: ext)

        var outputLines: [String] = []
        outputLines.append("// JCROSS_BEGIN")
        outputLines.append("// lang:\(lang) ver:1.0 enc:kanji-topology")
        outputLines.append("// ⚠️ Verantyx JCross Intermediate Representation")
        outputLines.append("")

        var secretCount = 0
        let lines = source.components(separatedBy: "\n")

        for line in lines {
            let trimmed = line.trimmingCharacters(in: .whitespaces)

            // コメント行は省略（情報漏洩防止）
            if trimmed.hasPrefix("//") || trimmed.hasPrefix("#") ||
               trimmed.hasPrefix("--") || trimmed.hasPrefix("*") {
                outputLines.append("// [omit]")
                continue
            }

            if trimmed.isEmpty {
                outputLines.append("")
                continue
            }

            // センシティブパターンを先に検出・除去
            var processed = line
            for regex in Self.secretRegexes {
                let ns = processed as NSString
                let matches = regex.matches(in: processed, range: NSRange(location: 0, length: ns.length))
                for match in matches.reversed() {
                    let id = nextID(prefix: "S")
                    processed = (processed as NSString)
                        .replacingCharacters(in: match.range, with: "「\(id)」")
                    secretCount += 1
                }
            }

            // 識別子をノード ID に置換
            if let regex = Self.identifierRegex {
                let ns = processed as NSString
                let matches = regex.matches(in: processed,
                                            range: NSRange(location: 0, length: ns.length))
                var offset = 0
                for match in matches {
                    let range = NSRange(location: match.range.location + offset,
                                       length: match.range.length)
                    guard let swiftRange = Range(range, in: processed) else { continue }
                    let word = String(processed[swiftRange])

                    if keywords.contains(word) { continue }

                    let nodeID: String
                    if let existing = symbolMap[word] {
                        nodeID = existing
                    } else {
                        nodeID = nextID(prefix: kanjiPrefix(for: word))
                        symbolMap[word] = nodeID
                    }

                    let replacement = "⟨\(nodeID)⟩"
                    processed.replaceSubrange(swiftRange, with: replacement)
                    offset += replacement.count - word.count
                }
            }

            outputLines.append(processed)
        }

        outputLines.append("// JCROSS_END")
        let jcross   = outputLines.joined(separator: "\n")
        let nodeCount = symbolMap.count

        return (jcross, nodeCount, secretCount, sessionID)
    }

    // MARK: - Helpers

    private func nextID(prefix: String) -> String {
        counter += 1
        return "\(prefix)\(counter)"
    }

    private func kanjiPrefix(for word: String) -> String {
        let lower = word.lowercased()
        if lower.hasPrefix("get") || lower.hasPrefix("set") ||
           lower.hasPrefix("fetch") || lower.hasPrefix("send") ||
           lower.hasSuffix("Manager") || lower.hasSuffix("Engine") ||
           lower.hasSuffix("Handler") || lower.hasSuffix("Service") {
            return "F"
        }
        if lower.contains("url") || lower.contains("http") ||
           lower.contains("api") || lower.contains("request") {
            return "N"
        }
        if lower.contains("key") || lower.contains("secret") ||
           lower.contains("token") || lower.contains("password") {
            return "S"
        }
        if lower.hasPrefix("is") || lower.hasPrefix("has") ||
           lower.hasPrefix("should") || lower.hasPrefix("can") {
            return "B"
        }
        return "V"
    }

    private func langName(for ext: String) -> String {
        switch ext {
        case "swift":           return "swift"
        case "py":              return "python"
        case "ts", "tsx":       return "typescript"
        case "js", "jsx":       return "javascript"
        case "rs":              return "rust"
        case "go":              return "go"
        case "kt":              return "kotlin"
        case "java":            return "java"
        case "cpp", "cc", "c":  return "cpp"
        case "rb":              return "ruby"
        default:                return "plain"
        }
    }

    private func keywordSet(for ext: String) -> Set<String> {
        switch ext {
        case "swift":
            return ["if","else","for","while","func","var","let","class","struct","enum",
                    "return","guard","switch","case","in","self","super","init","deinit",
                    "import","true","false","nil","async","await","throws","try","catch",
                    "static","final","private","public","internal","open","protocol",
                    "extension","where","as","is","do","repeat","break","continue"]
        case "py":
            return ["if","else","elif","for","while","def","class","return","import",
                    "from","as","with","pass","break","continue","True","False","None",
                    "and","or","not","in","is","async","await","yield","lambda","del",
                    "raise","except","finally","try","global","nonlocal","assert"]
        case "ts","tsx","js","jsx":
            return ["if","else","for","while","function","const","let","var","class",
                    "return","import","export","async","await","true","false","null",
                    "undefined","new","this","typeof","instanceof","in","of","do",
                    "switch","case","break","continue","throw","try","catch","finally",
                    "interface","type","extends","implements","super","static","public",
                    "private","protected","abstract","readonly","enum","namespace"]
        case "rs":
            return ["if","else","for","while","fn","let","mut","struct","enum","impl",
                    "match","return","use","mod","pub","true","false","self","Self",
                    "super","crate","in","where","as","ref","move","async","await",
                    "trait","type","const","static","unsafe","extern","loop","break",
                    "continue","dyn","box","loop"]
        default:
            return []
        }
    }
}
