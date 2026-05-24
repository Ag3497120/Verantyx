import Foundation

// MARK: - PrivacyProxy
// The core of the "Privacy Shield" architecture.
//
// Phase 1 (MVP) : Regex-based deterministic masking
//   - Extracts project-specific identifiers (functions, classes, vars, strings)
//   - Maps them to anonymous codes (FUNC_001, CLASS_001, VAR_001, STR_001)
//   - Stores mapping table in CortexEngine for reversal
//   - Unmasking reverses the mapping after cloud returns
//
// Phase 2 (coming): Gemma-semantic masking
//   - Ask local Gemma to intelligently identify "sensitive" identifiers
//   - More context-aware than pure regex

// MARK: - MaskingMap

struct MaskingMap: Codable {
    var funcMap: [String: String] = [:]   // realName → FUNC_001
    var classMap: [String: String] = [:]
    var varMap: [String: String] = [:]
    var stringMap: [String: String] = [:]
    var pathMap: [String: String] = [:]

    // Reverse: FUNC_001 → realName
    var reverseFunc: [String: String] { Dictionary(uniqueKeysWithValues: funcMap.map { ($1, $0) }) }
    var reverseClass: [String: String] { Dictionary(uniqueKeysWithValues: classMap.map { ($1, $0) }) }
    var reverseVar: [String: String] { Dictionary(uniqueKeysWithValues: varMap.map { ($1, $0) }) }
    var reverseString: [String: String] { Dictionary(uniqueKeysWithValues: stringMap.map { ($1, $0) }) }
    var reversePath: [String: String] { Dictionary(uniqueKeysWithValues: pathMap.map { ($1, $0) }) }

    var totalMasked: Int { funcMap.count + classMap.count + varMap.count + stringMap.count + pathMap.count }
}

// MARK: - MaskingStats (for UI display)

struct MaskingStats {
    let functions: Int
    let classes: Int
    let variables: Int
    let strings: Int
    let paths: Int
    var total: Int { functions + classes + variables + strings + paths }
    var privacyScore: Int { min(100, total * 3) } // rough score
}

// MARK: - PrivacyProxy

actor PrivacyProxy {

    static let shared = PrivacyProxy()

    // Language stdlib identifiers — these are NOT masked (would break code)
    private static let swiftStdlib: Set<String> = [
        "Int", "String", "Bool", "Double", "Float", "Array", "Dictionary", "Set",
        "Optional", "Result", "Error", "Never", "Void", "Any", "AnyObject",
        "print", "debugPrint", "dump", "assert", "precondition", "fatalError",
        "super", "self", "Self", "true", "false", "nil",
        "func", "class", "struct", "enum", "protocol", "extension", "import",
        "var", "let", "if", "else", "for", "while", "return", "guard", "switch",
        "case", "default", "break", "continue", "throw", "try", "catch", "do",
        "async", "await", "actor", "init", "deinit", "get", "set", "willSet", "didSet",
        "static", "override", "final", "open", "public", "internal", "private", "fileprivate",
        "mutating", "nonmutating", "lazy", "weak", "unowned", "inout", "some", "any",
        "URL", "Data", "Date", "UUID", "Foundation", "SwiftUI", "AppKit", "UIKit",
        "View", "Text", "Button", "HStack", "VStack", "ZStack", "List", "NavigationView",
        "Task", "MainActor", "ObservableObject", "Published", "StateObject", "EnvironmentObject",
        "NSObject", "NSString", "NSArray", "NSDictionary",
        "Int8", "Int16", "Int32", "Int64", "UInt", "UInt8", "UInt16", "UInt32", "UInt64",
        "Float16", "Float32", "Float64", "Character", "Substring",
        "map", "filter", "reduce", "forEach", "compactMap", "flatMap",
        "append", "remove", "contains", "isEmpty", "count",
    ]

    private static let pythonStdlib: Set<String> = [
        "int", "str", "bool", "float", "list", "dict", "set", "tuple", "bytes",
        "print", "len", "range", "type", "isinstance", "hasattr", "getattr", "setattr",
        "None", "True", "False", "self", "cls",
        "if", "else", "elif", "for", "while", "def", "class", "import", "from",
        "return", "yield", "break", "continue", "pass", "raise", "try", "except",
        "finally", "with", "as", "lambda", "global", "nonlocal", "del", "assert",
        "and", "or", "not", "in", "is", "async", "await",
        "os", "sys", "json", "math", "re", "time", "datetime", "pathlib",
        "open", "input", "super", "__init__", "__str__", "__repr__", "__main__",
    ]

    private static let jsStdlib: Set<String> = [
        "const", "let", "var", "function", "class", "extends", "import", "export",
        "if", "else", "for", "while", "do", "switch", "case", "default", "break",
        "continue", "return", "throw", "try", "catch", "finally", "async", "await",
        "this", "super", "new", "delete", "typeof", "instanceof", "void", "null",
        "undefined", "true", "false", "console", "log", "error", "warn", "info",
        "String", "Number", "Boolean", "Array", "Object", "Promise", "Map", "Set",
        "JSON", "Math", "Date", "Error", "parseInt", "parseFloat", "isNaN",
        "document", "window", "fetch", "setTimeout", "setInterval", "clearTimeout",
    ]

    private func stdlib(for language: Language) -> Set<String> {
        switch language {
        case .swift:                        return Self.swiftStdlib
        case .python:                       return Self.pythonStdlib
        case .javascript, .typescript:      return Self.jsStdlib
        default:                            return []
        }
    }

    enum Language: String {
        case swift, python, javascript, typescript, rust, go, cpp, unknown
    }

    // MARK: - Main: Mask code

    func mask(
        code: String,
        language: Language,
        fileName: String,
        maskStrings: Bool = true,
        maskPaths: Bool = true
    ) -> (masked: String, map: MaskingMap, stats: MaskingStats) {
        var map = MaskingMap()
        var result = code
        let stdlib = self.stdlib(for: language)

        var funcCounter = 1
        var classCounter = 1
        var varCounter = 1
        var stringCounter = 1

        // ── 1. Mask function/method names ─────────────────────────────
        let funcPatterns: [(lang: Language, pattern: String)] = [
            (.swift,      #"(?<=func\s)([a-zA-Z_][a-zA-Z0-9_]*)"#),
            (.python,     #"(?<=def\s)([a-zA-Z_][a-zA-Z0-9_]*)"#),
            (.javascript, #"(?<=function\s)([a-zA-Z_][a-zA-Z0-9_]*)"#),
            (.typescript, #"(?<=function\s)([a-zA-Z_][a-zA-Z0-9_]*)"#),
            (.rust,       #"(?<=fn\s)([a-zA-Z_][a-zA-Z0-9_]*)"#),
            (.go,         #"(?<=func\s)([a-zA-Z_][a-zA-Z0-9_]*)"#),
        ]

        let funcPattern = funcPatterns.first { $0.lang == language }?.pattern
            ?? #"(?<=func\s|def\s|fn\s)([a-zA-Z_][a-zA-Z0-9_]*)"#

        if let regex = try? NSRegularExpression(pattern: funcPattern) {
            let matches = regex.matches(in: code, range: NSRange(code.startIndex..., in: code))
            let names = Set(matches.compactMap { m -> String? in
                Range(m.range(at: 1), in: code).map { String(code[$0]) }
            })
            for name in names.sorted() where !stdlib.contains(name) && !name.isEmpty {
                let token = "FUNC_\(String(format: "%03d", funcCounter))"
                funcCounter += 1
                map.funcMap[name] = token
            }
        }

        // ── 2. Mask class/struct names ─────────────────────────────────
        let classPattern: String
        switch language {
        case .swift:     classPattern = #"(?<=class\s|struct\s|enum\s|actor\s|protocol\s)([A-Z][a-zA-Z0-9_]*)"#
        case .python:    classPattern = #"(?<=class\s)([A-Z][a-zA-Z0-9_]*)"#
        default:         classPattern = #"(?<=class\s)([A-Z][a-zA-Z0-9_]*)"#
        }

        if let regex = try? NSRegularExpression(pattern: classPattern) {
            let matches = regex.matches(in: code, range: NSRange(code.startIndex..., in: code))
            let names = Set(matches.compactMap { m -> String? in
                Range(m.range(at: 1), in: code).map { String(code[$0]) }
            })
            for name in names.sorted() where !stdlib.contains(name) && !name.isEmpty {
                let token = "CLASS_\(String(format: "%03d", classCounter))"
                classCounter += 1
                map.classMap[name] = token
            }
        }

        // ── 3. Mask variable/constant declarations ────────────────────
        let varPattern: String
        switch language {
        case .swift:     varPattern = #"(?<=var\s|let\s)([a-z_][a-zA-Z0-9_]{2,})"#
        case .python:    varPattern = #"^([a-z_][a-zA-Z0-9_]{2,})(?=\s*=)"#
        default:         varPattern = #"(?<=var\s|let\s|const\s)([a-z_][a-zA-Z0-9_]{2,})"#
        }

        if let regex = try? NSRegularExpression(pattern: varPattern, options: .anchorsMatchLines) {
            let matches = regex.matches(in: code, range: NSRange(code.startIndex..., in: code))
            let names = Set(matches.compactMap { m -> String? in
                let r = m.numberOfRanges > 1 ? m.range(at: 1) : m.range
                return Range(r, in: code).map { String(code[$0]) }
            })
            for name in names.sorted() where !stdlib.contains(name) && name.count > 2 {
                // Skip if already mapped as a function
                if map.funcMap[name] != nil { continue }
                let token = "VAR_\(String(format: "%03d", varCounter))"
                varCounter += 1
                map.varMap[name] = token
            }
        }

        // ── 4. Mask string literals (potential secrets) ───────────────
        if maskStrings {
            // Match strings that look like secrets (keys, tokens, URLs, passwords)
            let secretPattern = #"\"(?:sk[-_]|pk[-_]|Bearer\s|password|secret|token|key|api)[^\"]{4,}\""#
            if let regex = try? NSRegularExpression(pattern: secretPattern, options: .caseInsensitive) {
                let matches = regex.matches(in: code, range: NSRange(code.startIndex..., in: code))
                let literals = Set(matches.compactMap { m -> String? in
                    Range(m.range, in: code).map { String(code[$0]) }
                })
                for literal in literals.sorted() {
                    let token = "\"REDACTED_\(String(format: "%03d", stringCounter))\""
                    stringCounter += 1
                    map.stringMap[literal] = token
                }
            }
        }

        // ── 5. Apply masking (longest first to avoid partial replacements) ──
        // Apply in order: strings first, then classes, then functions, then vars
        // (to avoid masking tokens we just created)

        // Strings
        for (original, token) in map.stringMap.sorted(by: { $0.key.count > $1.key.count }) {
            result = result.replacingOccurrences(of: original, with: token)
        }
        // Classes (before functions/vars since they're capitalized)
        for (original, token) in map.classMap.sorted(by: { $0.key.count > $1.key.count }) {
            result = replaceWholeWord(result, word: original, replacement: token)
        }
        // Functions
        for (original, token) in map.funcMap.sorted(by: { $0.key.count > $1.key.count }) {
            result = replaceWholeWord(result, word: original, replacement: token)
        }
        // Variables
        for (original, token) in map.varMap.sorted(by: { $0.key.count > $1.key.count }) {
            result = replaceWholeWord(result, word: original, replacement: token)
        }

        let stats = MaskingStats(
            functions: map.funcMap.count,
            classes: map.classMap.count,
            variables: map.varMap.count,
            strings: map.stringMap.count,
            paths: map.pathMap.count
        )

        return (result, map, stats)
    }

    // MARK: - Main: Unmask code

    func unmask(maskedCode: String, map: MaskingMap) -> String {
        var result = maskedCode

        // Unmask in reverse order: vars first, then functions, then classes, then strings
        for (token, original) in map.reverseVar.sorted(by: { $0.key < $1.key }) {
            result = result.replacingOccurrences(of: token, with: original)
        }
        for (token, original) in map.reverseFunc.sorted(by: { $0.key < $1.key }) {
            result = result.replacingOccurrences(of: token, with: original)
        }
        for (token, original) in map.reverseClass.sorted(by: { $0.key < $1.key }) {
            result = result.replacingOccurrences(of: token, with: original)
        }
        for (token, original) in map.reverseString.sorted(by: { $0.key < $1.key }) {
            result = result.replacingOccurrences(of: token, with: original)
        }
        return result
    }

    // MARK: - Helper

    private func replaceWholeWord(_ text: String, word: String, replacement: String) -> String {
        let escaped = NSRegularExpression.escapedPattern(for: word)
        let pattern = #"\b"# + escaped + #"\b"#
        guard let regex = try? NSRegularExpression(pattern: pattern) else {
            return text.replacingOccurrences(of: word, with: replacement)
        }
        var result = text
        let range = NSRange(text.startIndex..., in: text)
        let matches = regex.matches(in: text, range: range)
        for match in matches.reversed() {
            if let r = Range(match.range, in: result) {
                result.replaceSubrange(r, with: replacement)
            }
        }
        return result
    }

    // MARK: - Store mapping in Cortex

    func storeMapping(_ map: MaskingMap, for sessionId: UUID, in cortex: CortexEngine) async {
        guard let data = try? JSONEncoder().encode(map),
              let json = String(data: data, encoding: .utf8)
        else { return }
        await cortex.remember(
            key: "masking_map_\(sessionId.uuidString.prefix(8))",
            value: json,
            importance: 1.0,
            zone: .front
        )
    }

    func recoverMapping(sessionId: UUID, from cortex: CortexEngine) async -> MaskingMap? {
        let nodes = await cortex.recall(for: "masking_map_\(sessionId.uuidString.prefix(8))", topK: 1)
        guard let node = nodes.first,
              let data = node.value.data(using: .utf8),
              let map = try? JSONDecoder().decode(MaskingMap.self, from: data)
        else { return nil }
        return map
    }

    // MARK: - Detect language

    func language(for url: URL) -> Language {
        switch url.pathExtension.lowercased() {
        case "swift":                   return .swift
        case "py":                      return .python
        case "ts", "tsx":               return .typescript
        case "js", "jsx", "mjs":        return .javascript
        case "rs":                      return .rust
        case "go":                      return .go
        case "cpp", "cc", "h", "hpp":   return .cpp
        default:                        return .unknown
        }
    }
}
