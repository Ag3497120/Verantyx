import SwiftUI
import Foundation

// MARK: - SyntaxHighlighter
// Regex-based tokenizer for Tier 1 + Tier 2 languages.
// Zero dependencies. Returns AttributedString for SwiftUI Text().
//
// Tier 1: Swift, Python, TypeScript, JavaScript, Rust
// Tier 2: Go, C, C++, JSON, YAML, Markdown

public struct SyntaxHighlighter {

    // MARK: - Language detection

    public static func language(for url: URL) -> Language {
        switch url.pathExtension.lowercased() {
        case "swift":                   return .swift
        case "py", "pyw":               return .python
        case "ts", "tsx":               return .typescript
        case "js", "jsx", "mjs":        return .javascript
        case "rs":                      return .rust
        case "go":                      return .go
        case "c", "h":                  return .c
        case "cpp", "cc", "cxx", "hpp": return .cpp
        case "json":                    return .json
        case "yaml", "yml":             return .yaml
        case "md", "markdown":          return .markdown
        case "jcross":                  return .jcross
        default:                        return .plain
        }
    }

    public enum Language: String {
        case swift, python, typescript, javascript, rust, go, c, cpp
        case json, yaml, markdown, jcross, plain
    }

    // MARK: - Token kinds + colors

    public enum TokenKind {
        case keyword, keyword2          // blue / purple
        case string                     // orange/red
        case comment                    // green
        case number                     // cyan
        case type                       // yellow
        case function_                  // teal
        case attribute                  // gray-blue
        case operator_                  // white
        case punctuation                // secondary
        case plain                      // primary

        var color: Color {
            switch self {
            case .keyword:    return Color(red: 0.42, green: 0.62, blue: 0.99)  // blue
            case .keyword2:   return Color(red: 0.73, green: 0.52, blue: 0.99)  // purple
            case .string:     return Color(red: 0.99, green: 0.50, blue: 0.40)  // coral
            case .comment:    return Color(red: 0.44, green: 0.68, blue: 0.44)  // green
            case .number:     return Color(red: 0.34, green: 0.90, blue: 0.80)  // cyan
            case .type:       return Color(red: 0.99, green: 0.85, blue: 0.42)  // yellow
            case .function_:  return Color(red: 0.40, green: 0.85, blue: 0.80)  // teal
            case .attribute:  return Color(red: 0.75, green: 0.75, blue: 0.90)  // muted purple
            case .operator_:  return Color(red: 0.95, green: 0.95, blue: 0.95)
            case .punctuation:return Color(red: 0.70, green: 0.70, blue: 0.70)
            case .plain:      return Color(red: 0.92, green: 0.92, blue: 0.92)
            }
        }
    }

    public struct Token {
        public let kind: TokenKind
        public let text: String
    }

    // MARK: - Main tokenize entry

    public static func tokenize(_ source: String, language: Language) -> [Token] {
        switch language {
        case .swift:       return tokenize(source, spec: swiftSpec)
        case .python:      return tokenize(source, spec: pythonSpec)
        case .typescript:  return tokenize(source, spec: tsSpec)
        case .javascript:  return tokenize(source, spec: jsSpec)
        case .rust:        return tokenize(source, spec: rustSpec)
        case .go:          return tokenize(source, spec: goSpec)
        case .c:           return tokenize(source, spec: cSpec)
        case .cpp:         return tokenize(source, spec: cppSpec)
        case .json:        return tokenize(source, spec: jsonSpec)
        case .yaml:        return tokenize(source, spec: yamlSpec)
        case .markdown:    return tokenize(source, spec: markdownSpec)
        case .jcross:      return tokenize(source, spec: jcrossSpec)
        case .plain:       return [Token(kind: .plain, text: source)]
        }
    }

    // MARK: - AttributedString output

    public static func highlight(_ source: String, language: Language) -> AttributedString {
        let tokens = tokenize(source, language: language)
        var result = AttributedString()
        for token in tokens {
            var part = AttributedString(token.text)
            part.foregroundColor = token.kind.color
            if token.kind == .keyword || token.kind == .keyword2 {
                part.font = .system(.callout, design: .monospaced).weight(.semibold)
            } else {
                part.font = .system(.callout, design: .monospaced)
            }
            result += part
        }
        return result
    }

    // MARK: - Generic tokenizer engine

    private struct Rule {
        let pattern: String
        let kind: TokenKind
        let group: Int  // regex capture group containing the token text
        let regex: NSRegularExpression

        init(pattern: String, kind: TokenKind, group: Int) {
            self.pattern = pattern
            self.kind = kind
            self.group = group
            self.regex = try! NSRegularExpression(pattern: pattern, options: [])
        }
    }

    private struct LangSpec {
        let rules: [Rule]           // ordered: first match wins
        let keywords: Set<String>   // plain words to promote to .keyword
        let keywords2: Set<String>  // secondary keywords → .keyword2
        let types: Set<String>      // type names
    }

    private static func tokenize(_ source: String, spec: LangSpec) -> [Token] {
        var tokens: [Token] = []
        var index = source.startIndex

        // Build combined regex — try each rule in order
        while index < source.endIndex {
            var matched = false
            for rule in spec.rules {
                let searchRange = NSRange(index..., in: source)
                guard let m = rule.regex.firstMatch(in: source, options: .anchored, range: searchRange) else { continue }
                let captureRange = rule.group < m.numberOfRanges
                    ? Range(m.range(at: rule.group), in: source)
                    : Range(m.range, in: source)
                guard let range = captureRange ?? Range(m.range, in: source) else { continue }

                let text = String(source[range])
                let kind = resolveKind(text: text, base: rule.kind, spec: spec)
                tokens.append(Token(kind: kind, text: text))
                index = range.upperBound
                matched = true
                break
            }
            if !matched {
                // Consume one character as plain
                let end = source.index(after: index)
                tokens.append(Token(kind: .plain, text: String(source[index..<end])))
                index = end
            }
        }
        return tokens
    }

    private static func resolveKind(text: String, base: TokenKind, spec: LangSpec) -> TokenKind {
        if base == .plain {
            if spec.keywords.contains(text)  { return .keyword  }
            if spec.keywords2.contains(text) { return .keyword2 }
            if spec.types.contains(text)     { return .type     }
        }
        return base
    }

    // MARK: - Language Specs

    // Common rules shared across C-family
    private static let blockComment = Rule(pattern: #"/\*[\s\S]*?\*/"#,  kind: .comment, group: 0)
    private static let lineComment  = Rule(pattern: #"//[^\n]*"#,        kind: .comment, group: 0)
    private static let dqString     = Rule(pattern: #""(?:[^"\\]|\\.)*""#, kind: .string, group: 0)
    private static let sqString     = Rule(pattern: #"'(?:[^'\\]|\\.)*'"#, kind: .string, group: 0)
    private static let numberRule   = Rule(pattern: #"\b0x[0-9a-fA-F]+\b|\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b"#, kind: .number, group: 0)
    private static let identRule    = Rule(pattern: #"\b[a-zA-Z_][a-zA-Z0-9_]*\b"#, kind: .plain, group: 0)
    private static let punctRule    = Rule(pattern: #"[{}()\[\];,.]"#, kind: .punctuation, group: 0)
    private static let opRule       = Rule(pattern: #"[+\-*/%=<>!&|^~?:]+"#, kind: .operator_, group: 0)
    private static let wsRule       = Rule(pattern: #"\s+"#, kind: .plain, group: 0)

    // MARK: Swift
    private static let swiftSpec = LangSpec(
        rules: [
            blockComment, lineComment,
            Rule(pattern: #""""[\s\S]*?""""#, kind: .string, group: 0),          // multi-line
            Rule(pattern: #""(?:[^"\\]|\\.)*""#, kind: .string, group: 0),
            Rule(pattern: #"@\w+"#, kind: .attribute, group: 0),                 // @discardableResult
            Rule(pattern: #"`\w+`"#, kind: .plain, group: 0),
            numberRule, identRule, punctRule, opRule, wsRule
        ],
        keywords: ["if","else","guard","switch","case","default","for","while","repeat","break","continue","return",
                   "func","let","var","class","struct","enum","protocol","extension","import","typealias",
                   "in","is","as","try","throw","throws","catch","do","defer","init","deinit","subscript",
                   "static","override","final","open","public","internal","fileprivate","private","mutating",
                   "nonmutating","lazy","weak","unowned","async","await","actor","nonisolated","some","any",
                   "@main","where","inout","operator","precedencegroup","associativity","willSet","didSet",
                   "get","set","_","super","self","Self","true","false","nil"],
        keywords2: ["Sendable","Codable","Hashable","Equatable","Comparable","Identifiable","ObservableObject"],
        types: ["Int","Int8","Int16","Int32","Int64","UInt","UInt8","UInt16","UInt32","UInt64",
                "Float","Double","Bool","String","Character","Void","Optional","Array","Dictionary",
                "Set","Tuple","Result","Error","Never","Any","AnyObject","Data","URL","Date"]
    )

    // MARK: Python
    private static let pythonSpec = LangSpec(
        rules: [
            Rule(pattern: #"#[^\n]*"#, kind: .comment, group: 0),
            Rule(pattern: #"\"\"\"[\s\S]*?\"\"\"|'''[\s\S]*?'''"#, kind: .string, group: 0),    // docstrings
            Rule(pattern: #"[fFrRbBuU]?"(?:[^"\\]|\\.)*"|[fFrRbBuU]?'(?:[^'\\]|\\.)*'"#, kind: .string, group: 0),
            Rule(pattern: #"@\w+"#, kind: .attribute, group: 0),
            numberRule, identRule, punctRule, opRule, wsRule
        ],
        keywords: ["if","elif","else","for","while","break","continue","return","yield","pass",
                   "def","class","import","from","as","with","try","except","finally","raise",
                   "and","or","not","in","is","lambda","global","nonlocal","del","assert",
                   "async","await","True","False","None","print","len","range","type","super"],
        keywords2: ["self","cls","__init__","__str__","__repr__","__len__","__main__"],
        types: ["int","float","str","bool","list","dict","set","tuple","bytes","bytearray",
                "complex","frozenset","object","type","None","Any","Optional","Union","List","Dict"]
    )

    // MARK: TypeScript (superset of JS keywords)
    private static let tsSpec = LangSpec(
        rules: [
            blockComment, lineComment,
            Rule(pattern: #"`(?:[^`\\]|\\.)*`"#, kind: .string, group: 0),       // template literal
            dqString, sqString,
            numberRule, identRule, punctRule, opRule, wsRule
        ],
        keywords: ["if","else","for","while","do","break","continue","return","switch","case","default",
                   "function","const","let","var","class","extends","implements","import","export","from",
                   "as","in","of","instanceof","typeof","typeof","new","delete","void","throw","try",
                   "catch","finally","async","await","yield","static","get","set","super","this",
                   "true","false","null","undefined","abstract","override","declare","namespace","module",
                   "type","interface","enum","readonly","private","protected","public","keyof","infer"],
        keywords2: ["React","useState","useEffect","useRef","useCallback","useMemo","Props"],
        types: ["string","number","boolean","object","any","unknown","never","void","symbol","bigint",
                "Array","Promise","Record","Partial","Required","Readonly","Map","Set","Date","Error"]
    )

    // MARK: JavaScript (TS subset without type keywords)
    private static let jsSpec = LangSpec(
        rules: tsSpec.rules,
        keywords: ["if","else","for","while","do","break","continue","return","switch","case","default",
                   "function","const","let","var","class","extends","import","export","from","as",
                   "in","of","instanceof","typeof","new","delete","void","throw","try","catch","finally",
                   "async","await","yield","static","get","set","super","this","true","false","null","undefined"],
        keywords2: [],
        types: ["Array","Promise","Map","Set","Date","Error","Object","Function","Number","String","Boolean"]
    )

    // MARK: Rust
    private static let rustSpec = LangSpec(
        rules: [
            blockComment, lineComment,
            Rule(pattern: #"r\"[^\"]*\""#, kind: .string, group: 0),              // raw strings (simplified)
            dqString, sqString,
            Rule(pattern: #"#\[[\s\S]*?\]"#, kind: .attribute, group: 0),        // #[derive(...)]
            Rule(pattern: #"'[a-zA-Z_][a-zA-Z0-9_]*\b"#, kind: .attribute, group: 0),  // lifetimes
            numberRule,
            Rule(pattern: #"\b[A-Z][A-Z0-9_]+\b"#, kind: .type, group: 0),      // CONSTANTS
            identRule, punctRule, opRule, wsRule
        ],
        keywords: ["if","else","match","for","while","loop","break","continue","return",
                   "fn","let","mut","const","static","struct","enum","trait","impl","use",
                   "mod","pub","crate","super","self","Self","type","where","in","as","ref",
                   "move","async","await","unsafe","extern","dyn","box","true","false",
                   "Some","None","Ok","Err"],
        keywords2: ["pub","mut","ref","dyn","unsafe","extern","crate","move"],
        types: ["i8","i16","i32","i64","i128","isize","u8","u16","u32","u64","u128","usize",
                "f32","f64","bool","char","str","String","Vec","Option","Result","Box","Arc",
                "Rc","Cell","RefCell","Mutex","RwLock","HashMap","HashSet","BTreeMap","BTreeSet"]
    )

    // MARK: Go
    private static let goSpec = LangSpec(
        rules: [lineComment, blockComment, dqString, sqString, numberRule, identRule, punctRule, opRule, wsRule],
        keywords: ["if","else","for","range","switch","case","default","break","continue","return",
                   "func","var","const","type","struct","interface","map","chan","go","select",
                   "defer","goto","import","package","true","false","nil","make","new","len","cap",
                   "append","copy","delete","close","panic","recover","print","println"],
        keywords2: ["goroutine","go"],
        types: ["int","int8","int16","int32","int64","uint","uint8","uint16","uint32","uint64","uintptr",
                "float32","float64","complex64","complex128","bool","byte","rune","string","error","any"]
    )

    // MARK: C
    private static let cSpec = LangSpec(
        rules: [
            blockComment, lineComment,
            Rule(pattern: #"#\s*\w+[^\n]*"#, kind: .attribute, group: 0),        // #include, #define
            dqString, sqString, numberRule, identRule, punctRule, opRule, wsRule
        ],
        keywords: ["if","else","for","while","do","break","continue","return","switch","case","default",
                   "goto","typedef","struct","union","enum","sizeof","const","static","extern","register",
                   "volatile","inline","restrict","_Bool","NULL","true","false"],
        keywords2: [],
        types: ["int","char","short","long","float","double","unsigned","signed","void","size_t",
                "uint8_t","uint16_t","uint32_t","uint64_t","int8_t","int16_t","int32_t","int64_t","FILE"]
    )

    // MARK: C++
    private static let cppSpec = LangSpec(
        rules: cSpec.rules,
        keywords: Set(cSpec.keywords).union(["class","public","private","protected","virtual","override",
            "final","template","typename","namespace","using","new","delete","throw","try","catch",
            "operator","explicit","friend","inline","mutable","constexpr","consteval","constinit",
            "decltype","auto","nullptr","this","true","false","noexcept","static_assert","concept","requires"]),
        keywords2: ["std","endl"],
        types: Set(cSpec.types).union(["string","vector","map","unordered_map","set","pair","tuple",
            "optional","variant","any","shared_ptr","unique_ptr","weak_ptr","array","deque","queue",
            "stack","bitset","thread","mutex","condition_variable","future","promise","function"])
    )

    // MARK: JSON
    private static let jsonSpec = LangSpec(
        rules: [dqString, numberRule, identRule, punctRule, wsRule],
        keywords: ["true","false","null"],
        keywords2: [],
        types: []
    )

    // MARK: YAML
    private static let yamlSpec = LangSpec(
        rules: [
            Rule(pattern: #"#[^\n]*"#, kind: .comment, group: 0),
            Rule(pattern: #"(^|\n)(\s*#[^\n]*)"#, kind: .comment, group: 2),
            dqString, sqString, numberRule,
            Rule(pattern: #"^\s*[\w\-]+(?=\s*:)"#, kind: .type, group: 0),      // keys
            identRule, wsRule
        ],
        keywords: ["true","false","null","yes","no","on","off"],
        keywords2: [],
        types: []
    )

    // MARK: Markdown
    private static let markdownSpec = LangSpec(
        rules: [
            Rule(pattern: #"^#{1,6}\s.+"#, kind: .keyword, group: 0),            // headings
            Rule(pattern: #"```[\s\S]*?```"#, kind: .string, group: 0),          // code blocks
            Rule(pattern: #"`[^`]+`"#, kind: .string, group: 0),                // inline code
            Rule(pattern: #"\*\*[^*]+\*\*"#, kind: .type, group: 0),            // bold
            Rule(pattern: #"\*[^*]+\*"#, kind: .comment, group: 0),             // italic
            Rule(pattern: #"\[[^\]]+\]\([^)]+\)"#, kind: .function_, group: 0), // links
            Rule(pattern: #"^[-*+]\s"#, kind: .keyword2, group: 0),              // list markers
            Rule(pattern: #"^\d+\.\s"#, kind: .keyword2, group: 0),
            Rule(pattern: #"."#, kind: .plain, group: 0),
            wsRule
        ],
        keywords: [], keywords2: [], types: []
    )

    // MARK: JCross IR
    private static let jcrossSpec = LangSpec(
        rules: [
            Rule(pattern: #";;;[^\n]*"#, kind: .comment, group: 0),
            Rule(pattern: #"//[^\n]*"#, kind: .comment, group: 0),
            Rule(pattern: #"\[[A-Za-z0-9_\-\.]+\]"#, kind: .type, group: 0),      // Node IDs e.g. [VAR_1]
            Rule(pattern: #""(?:[^"\\]|\\.)*""#, kind: .string, group: 0),
            numberRule, identRule, punctRule, opRule, wsRule
        ],
        keywords: ["true", "false", "null", "nil"],
        keywords2: ["SCHEMA", "NODE", "EDGE", "MEM", "REF", "OP", "FACT", "ENTITY", "STATE", "TENSION", "VOID", "SOUL", "FRONT", "NEAR", "MID", "DEEP"],
        types: []
    )
}
