import Foundation

/// Summoning a surface by name, from a CLOSED table.
///
/// The chrome is being removed on purpose: a settings gear, a mode
/// picker and a memory tab are three buttons teaching three different
/// vocabularies, when the person already has one — the words they were
/// going to type anyway. Say 設定 and the settings arrive in the chat.
///
/// The table is closed and the match is exact, for the same reason the
/// intent frames are: a guessed summon is worse than no summon. 「設定を
/// 変えたい理由なんだけど」 is a sentence about settings, not a request
/// to open them, and a fuzzy matcher that opens a panel on it teaches
/// the person to distrust their own typing. Anything not in this table
/// falls through untouched to the normal path — the fall-through is the
/// feature, not the leftover case.
///
/// This lives in Swift rather than in the engine because it is UI
/// vocabulary, not language: the words name panels this app happens to
/// have, and the engine must not learn them. But it keeps the engine's
/// discipline — closed inventory, exact match, silent fall-through.
enum VeraSummon {
    enum Panel: String, Identifiable, CaseIterable {
        case settings, memory, cross, audit, modes, model
        var id: String { rawValue }

        var title: String {
            switch self {
            case .settings: return "設定"
            case .memory:   return "記憶"
            case .cross:    return "立体十字構造体"
            case .audit:    return "監査"
            case .modes:    return "モード"
            case .model:    return "モデル"
            }
        }
    }

    /// What the person can say. Every row is deliberate; nothing is
    /// generated from the enum, because a name that works must be a
    /// name someone chose.
    private static let table: [String: Panel] = [
        "設定": .settings, "せってい": .settings, "settings": .settings,
        "記憶": .memory, "きおく": .memory, "memory": .memory,
        "記憶パネル": .memory,
        "十字": .cross, "立体十字": .cross, "立体十字構造体": .cross,
        "構造": .cross, "cross": .cross,
        "監査": .audit, "audit": .audit,
        "モード": .modes, "モード切替": .modes, "modes": .modes,
        "モデル": .model, "model": .model, "モデル切替": .model,
    ]

    /// Switching the engine mode by name. Same closed discipline.
    private static let modes: [String: AppState.VeraEngineMode] = [
        "veraモード": .veraModel, "vera": .veraModel,
        "vera-aモード": .standalone, "vera-a": .standalone,
        "llmモード": .localLLM, "llm": .localLLM,
        "jgen合議": .council, "合議": .council, "jgen": .council,
        "veraぼっと": .veraBot, "ぼっと": .veraBot, "bot": .veraBot,
        "verabot": .veraBot, "vera bot": .veraBot,
    ]

    struct Resolution {
        var panel: Panel?
        var mode: AppState.VeraEngineMode?
    }

    /// Exact match on the trimmed line, case-folded, with a trailing
    /// 「を開いて」/「を出して」 allowed because those are the same
    /// request said politely — and nothing else. No prefix matching, no
    /// contains, no distance.
    static func resolve(_ raw: String) -> Resolution? {
        var s = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
        guard s.count <= 24 else { return nil }
        for tail in ["を開いて", "をひらいて", "を出して", "をだして",
                     "を表示", "を見せて", "にして", "に切り替え", "открыть"] {
            if s.hasSuffix(tail) { s = String(s.dropLast(tail.count)); break }
        }
        s = s.trimmingCharacters(in: .whitespaces)
        if let m = modes[s] { return Resolution(panel: nil, mode: m) }
        if let p = table[s] { return Resolution(panel: p, mode: nil) }
        return nil
    }
}
