import Foundation

// MARK: - AtelierChatRouter
//
// UI B (「チャット画面プラス服飾ui」— owner's spec): the whole garment
// workbench stays on screen, and the chat pane beside it decides where to
// look. This is the "where to look" decision, and only that — it never
// writes to the ledger, never proposes a value, never talks to an LLM.
//
// **The destination must come from something the engine can resolve, not
// from a model guessing** (owner's words, verbatim in the brief). Two
// resolution paths, both grounded:
//
//   1. A number span ("30番から35番", "30 to 35") is sent to the real
//      `pattern_span` MCP tool, the same door `AtelierModel` itself calls
//      for `pattern_where`/`pattern_numbers`. If it refuses (crosses
//      edges, unregistered number), that refusal is the answer; the
//      router does not fall back to guessing a step instead. This calls
//      MCPEngine directly rather than through an `AtelierModel` instance
//      — the chat pane in UI B sits OUTSIDE AtelierView's subtree and has
//      no reference to its private `@StateObject` model (see
//      `AtelierNavigator`'s doc comment), and the call needs nothing from
//      that instance beyond the door itself.
//   2. Anything else is checked against a fixed lexicon whose right-hand
//      side is always the literal name of a step in `AtelierModel.steps`
//      — the same array the step rail itself iterates. There is no way
//      to add a destination here that the rail cannot also reach by hand,
//      because the answer IS the rail's own list, not an invented one.
//
// Neither path calls a model. When neither matches, `resolve` returns
// `.none` and the caller must not move the view — a workbench that jumps
// somewhere arbitrary because a model felt like it is worse than one that
// stays put (owner's words).
@MainActor
enum AtelierChatRouter {

    struct Destination {
        let step: String
        let reasonEN: String
        let reasonJA: String
    }

    enum Resolution {
        /// A real address was found; move to `Destination.step`.
        case moved(Destination)
        /// The engine was asked (a number span went to `pattern_span`)
        /// and it refused — a typed answer, not a guess, so it is shown
        /// as-is and the view does not move.
        case refused(String)
        /// Nothing in the message named a place the engine or the step
        /// list can resolve. The view stays exactly where it is.
        case none
    }

    /// Right-hand side is always a member of `AtelierModel.steps` —
    /// `Self.validateLexicon()` below asserts that in DEBUG builds, so a
    /// typo here fails fast during development rather than silently
    /// routing nowhere in the field.
    private static let lexicon: [(words: [String], step: String)] = [
        (["生地", "素材", "布", "fabric", "material", "materials", "drape", "垂れ"],
         "Materials"),
        (["証拠", "根拠", "出典", "evidence", "witness"],
         "Evidence"),
        (["構造", "衿", "襟", "袖", "後ろ", "後身頃", "前身頃", "ポケット", "見返し",
          "collar", "sleeve", "pocket", "back panel", "structure"],
         "Structure"),
        (["由来", "権利", "オリジナル", "provenance", "rights", "origin"],
         "Provenance"),
        (["作り直", "変更案", "リデザイン", "re-design", "redesign"],
         "Re-design"),
        (["型紙", "裁断", "ノッチ", "縫い代", "パターン", "pattern", "notch",
          "seam allowance"],
         "Pattern"),
        (["立体", "ゆとり", "サイズ展開", "グレーディング", "ease", "grade",
          "solid", "mannequin", "マネキン"],
         "Solid"),
        (["仕様書", "テックパック", "tech pack", "techpack", "spec sheet"],
         "Tech Pack"),
        (["パーツ", "部位一覧", "garments", "parts list"],
         "Garments"),
        (["動画", "映像", "クリップ", "取り込み", "clip", "footage", "intake"],
         "Sources"),
    ]

    /// 「30番から35番」「30 to 35」「30-35」— 数字二つを繋ぐ語の**両側**
    /// に数字がある形だけを番号区間として読む。片方だけの数字("96cm"の
    /// ような実測値)を区間と誤読しないための境目。
    private static func numberSpan(in text: String) -> (Int, Int)? {
        let pattern = #"(\d+)\s*番?\s*(?:から|〜|~|-|–|to)\s*(\d+)\s*番?"#
        guard let re = try? NSRegularExpression(pattern: pattern) else { return nil }
        let ns = text as NSString
        guard let m = re.firstMatch(in: text, range: NSRange(location: 0, length: ns.length)),
              m.numberOfRanges == 3,
              let first = Int(ns.substring(with: m.range(at: 1))),
              let last = Int(ns.substring(with: m.range(at: 2)))
        else { return nil }
        return (first, last)
    }

    private static func stepNumber(_ step: String) -> Int {
        (AtelierModel.steps.firstIndex(of: step) ?? 0) + 1
    }

    /// Makes the doc comment on `lexicon` true: every right-hand side must
    /// name a real step. Called once from `resolve` under `#if DEBUG` —
    /// cheap (10 entries) and only runs in debug builds, so it costs
    /// nothing in release.
    private static func validateLexicon() {
        for (_, step) in lexicon {
            assert(AtelierModel.steps.contains(step),
                   "AtelierChatRouter.lexicon points at unknown step \"\(step)\"")
        }
    }

    /// Same door `AtelierModel`'s own private `call(_:_:)` uses — copied
    /// rather than shared because that one is `private` to the model and
    /// this router deliberately holds no reference to a model instance.
    private static func callDoor(_ tool: String, _ args: [String: Any]) async -> [String: Any] {
        let raw = await MCPEngine.shared.callTool(
            serverName: "vera-memory", toolName: tool, arguments: args)
        guard let d = raw.data(using: .utf8),
              let o = (try? JSONSerialization.jsonObject(with: d)) as? [String: Any]
        else { return ["verdict": "UNKNOWN_ENGINE_UNREACHABLE"] }
        return o
    }

    static func resolve(_ message: String) async -> Resolution {
        #if DEBUG
        validateLexicon()
        #endif
        let text = message.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return .none }

        if let (lo, hi) = numberSpan(in: text) {
            let d = await callDoor("pattern_span", ["first": lo, "last": hi])
            if (d["verdict"] as? String) == "ANSWER",
               let piece = d["piece"] as? String, let edge = d["edge"] as? String {
                let n = stepNumber("Pattern")
                let where_ = "\(piece)/\(edge)"
                return .moved(Destination(
                    step: "Pattern",
                    reasonEN: String(format: "→ %02d Pattern — %@", n, where_),
                    reasonJA: String(format: "→ %02d Pattern — %@", n, where_)))
            }
            // pattern_span itself answered — just not with a place
            // ("UNKNOWN_SPAN_CROSSES_EDGES" etc). That refusal is the
            // honest thing to show; inventing a step here would be
            // exactly the guess the owner's brief rules out.
            if let close = d["how_to_close"] as? String, !close.isEmpty {
                return .refused(close)
            }
            let verdict = (d["verdict"] as? String) ?? "UNKNOWN_ENGINE_UNREACHABLE"
            return .refused(verdict)
        }

        let lower = text.lowercased()
        for (words, step) in lexicon where words.contains(where: { lower.contains($0.lowercased()) }) {
            let n = stepNumber(step)
            let label = String(format: "→ %02d %@", n, step)
            return .moved(Destination(step: step, reasonEN: label, reasonJA: label))
        }
        return .none
    }
}
