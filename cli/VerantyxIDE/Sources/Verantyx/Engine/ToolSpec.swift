import Foundation

// MARK: - One declaration per tool; docs and parser both derived from it
//
// Every bug of this shape in this file came from the same structural fact:
// the tool documentation and the tool parser are two separate hand-written
// artifacts that have to agree, and nothing checks that they do. The record is
// in the comments — kanji shorthand no regex ever matched, inline OSASCRIPT
// that silently never ran, [RUN:] truncated at the first `]`, and most
// recently `"type text"`, where a placeholder in the docs was read as a
// literal and the word "text" was typed into Chrome's address bar.
//
// Each was found by a person noticing something wrong on screen. Each was
// fixed by editing one of the two artifacts. None of the fixes made the next
// one less likely, because the structure that produced them was untouched.
//
// So: declare a tool once. Generate the documentation from the declaration,
// and parse with the same declaration. Drift stops being a thing that
// discipline prevents and becomes a thing that cannot be expressed.
//
// The two ideas are vera-a's:
//
//   分離 — separate the parts that were tangled. A tool's NAME, its ARGUMENT
//          SHAPE, and how it is RENDERED to the model are three different
//          things. The old docs mixed all three into one prose string, which
//          is how a placeholder became indistinguishable from a keyword.
//
//   判定 — return a typed verdict, never a silent fallthrough. A line either
//          IS a tool call, or is malformed in a way we can name, or is not a
//          tool at all. "Nothing matched, treat it as prose" is what turned a
//          dropped tool call into a finished answer.

// MARK: - Argument shape

/// What a tool takes. Deliberately a small closed set: every shape here has to
/// be renderable as documentation AND checkable by the parser, and a shape
/// that cannot do both is a shape that will drift.
indirect enum ArgShape {
    /// No arguments: `[APP_CAPS]`
    case none
    /// Everything after the colon, as-is: `[SEARCH: …]`
    case freeText(ja: String, en: String)
    /// Optional free text: `[USE_APP]` or `[USE_APP: Chrome]`
    case optionalText(ja: String, en: String)
    /// A path-like argument, so docs can say so and the parser can expand ~.
    case path(ja: String, en: String)
    /// A hierarchy: `[MENU: File > Save]`
    case pathList(ja: String, en: String)
    /// A verb followed by its own arguments: `[DESKTOP_ACT: click 100 200]`.
    ///
    /// This case exists specifically because of the "type text" bug. The verb
    /// and its argument used to be one undifferentiated string documented by
    /// example, so the example's placeholder looked like part of the syntax.
    /// Here the verb list is data and each verb declares its own argument, so
    /// the rendered example cannot contain a word the parser does not know.
    case verbs([VerbSpec])
}

struct VerbSpec {
    let verb: String
    let argument: ArgShape
    let ja: String
}

// MARK: - Placeholders
//
// A placeholder must be impossible to mistake for a literal. Two properties do
// that, and both are needed:
//
//   1. It does not look like a word. `⟨入力する文字列⟩` is not something anyone
//      types on purpose; `text` is.
//   2. The parser KNOWS the placeholder, and says so when it sees one, instead
//      of passing it through as data. A model that copies the example verbatim
//      gets told what to replace, not a run that fails three steps later.

enum Placeholder {
    static let open = "⟨"
    static let close = "⟩"

    static func render(_ label: String) -> String { "\(open)\(label)\(close)" }

    /// True when a value is still the example rather than a real argument.
    static func isUnfilled(_ value: String) -> Bool {
        let v = value.trimmingCharacters(in: .whitespaces)
        guard v.contains(open) || v.contains(close) else {
            // The old docs' bare placeholders, which some models learned.
            return ["text", "action", "path", "url", "query", "combo",
                    "入力する文字列", "文字列"].contains(v.lowercased())
        }
        return true
    }
}

// MARK: - The verdict
//
// Mirrors how vera-a answers: a definite result, or a named reason there is
// none. What is banned is the fourth option the old parser used — falling
// through with no result and no reason.

enum ParseVerdict {
    /// A real tool call.
    case tool(AgentTool)
    /// A known tool whose argument is still the documented placeholder.
    case placeholderLeftIn(tool: String, placeholder: String)
    /// A known tool written in a shape it does not accept.
    case malformed(tool: String, why: String, expected: String)
    /// Tag-shaped, but no such tool.
    case unknownTool(String)
    /// Not a tool call at all — ordinary prose.
    case notATool

    /// Text to hand back to the model. Every non-success verdict says what to
    /// do differently, because a verdict the model cannot act on is a stall.
    var correction: String? {
        switch self {
        case .tool, .notATool:
            return nil
        case .placeholderLeftIn(let tool, let ph):
            return "[\(tool)] の引数が説明文のままです（\(ph)）。"
                + "そこは実際に使う値に置き換えてください。"
        case .malformed(let tool, let why, let expected):
            return "[\(tool)] の書式が違います: \(why)\n正しい形: \(expected)"
        case .unknownTool(let name):
            return "[\(name)] というツールはありません。ツール一覧から選び直してください。"
        }
    }
}

// MARK: - A tool, declared once

struct ToolSpec {
    let name: String
    let shape: ArgShape
    let ja: String
    /// Builds the tool from the validated argument. Returning nil means the
    /// argument passed shape checks but is still unusable — reported as
    /// malformed rather than dropped.
    let build: (String) -> AgentTool?

    /// The documentation line, generated. Nobody writes this by hand, so it
    /// cannot disagree with what the parser accepts.
    var docLine: String {
        let usage: String
        switch shape {
        case .none:
            usage = "[\(name)]"
        case .freeText(let ja, _), .path(let ja, _), .pathList(let ja, _):
            usage = "[\(name): \(Placeholder.render(ja))]"
        case .optionalText(let ja, _):
            usage = "[\(name)] または [\(name): \(Placeholder.render(ja))]"
        case .verbs(let verbs):
            let forms = verbs.map { v -> String in
                switch v.argument {
                case .none: return v.verb
                case .freeText(let ja, _), .path(let ja, _),
                     .pathList(let ja, _), .optionalText(let ja, _):
                    return "\(v.verb) \(Placeholder.render(ja))"
                case .verbs: return v.verb
                }
            }
            usage = "[\(name): \(forms.joined(separator: " | "))]"
        }
        return "\(usage.padding(toLength: max(usage.count, 42), withPad: " ", startingAt: 0))  \(ja)"
    }

    /// An example that must parse back to this tool. Used by the self-check,
    /// not shown to the model — the model gets `docLine`, whose placeholders
    /// are deliberately unfillable.
    var roundTripExample: String {
        switch shape {
        case .none:               return "[\(name)]"
        case .freeText:           return "[\(name): sample]"
        case .optionalText:       return "[\(name): sample]"
        case .path:               return "[\(name): /tmp/sample.txt]"
        case .pathList:           return "[\(name): File > Save]"
        case .verbs(let verbs):
            guard let first = verbs.first else { return "[\(name)]" }
            switch first.argument {
            case .none: return "[\(name): \(first.verb)]"
            default:    return "[\(name): \(first.verb) sample]"
            }
        }
    }
}
