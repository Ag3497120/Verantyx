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
        case settings, memory, cross, audit, modes, model, licences, screen, jgen
        var id: String { rawValue }

        var title: String {
            switch self {
            case .settings: return "設定"
            case .memory:   return "記憶"
            case .cross:    return "立体十字構造体"
            case .audit:    return "監査"
            case .modes:    return "モード"
            case .model:    return "モデル"
            case .licences: return "免許"
            case .screen:   return "画面"
            case .jgen:     return "JGEN"
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
        // The app-delegation licence book. Named 免許 because that is what
        // it is — a permission to perform a specific act, revocable, and
        // separate from whether the act is technically possible.
        "免許": .licences, "めんきょ": .licences, "licence": .licences,
        "license": .licences, "権限": .licences, "アプリ": .licences,
        "許可": .licences,
        "画面": .screen, "がめん": .screen, "screen": .screen,
        "前面": .screen, "スクショ": .screen, "window": .screen,
        // 「jgen」単体は合議モードが取る（modes が先に照合される）ので、
        // パネルには衝突しない語だけを与える。
        "jgen設定": .jgen, "エンジン": .jgen, "層": .jgen, "レイヤ": .jgen,
        "engine": .jgen, "layers": .jgen, "jgen options": .jgen,
    ]

    /// Full-window surfaces, formerly the rail's icons.
    private static let surfaces: [String: AppState.FullSurface] = [
        "mcp": .mcp, "外部運用": .mcp, "外部": .mcp,
        "vera-a設定": .veraSettings, "vera設定": .veraSettings,
        "ドック": .veraSettings,
        "成長": .growth, "学習": .growth, "growth": .growth,
        "進化": .evolution, "自己進化": .evolution, "evolution": .evolution,
    ]

    /// Actions. `設定` is here rather than in `surfaces` because model
    /// and API settings open as a sheet, not as a surface.
    private static let commands: [String: Command] = [
        "ファイル": .files, "files": .files, "エクスプローラ": .files,
        "explorer": .files,
        "git": .git, "ギット": .git, "差分": .git,
        "検索": .search, "search": .search,
        "マップ": .projectMap, "地図": .projectMap, "map": .projectMap,
        "パイプライン": .pipeline, "pipeline": .pipeline,
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

    /// A surface that takes the whole window. These used to be the left
    /// icon rail's job. The rail was five permanent icons teaching a
    /// sixth vocabulary, and four of them opened screens nobody visits
    /// mid-sentence — so they are named now, like everything else.
    /// The ones that stayed reachable are the ones you actually reach
    /// for: files, git, search.

    /// Something to DO rather than a surface to show. Kept separate
    /// because "パイプライン" starting a run and "設定" opening a panel
    /// are different promises, and one table hiding both would make the
    /// safe half unsafe.
    enum Command: String {
        case files, git, search, projectMap, pipeline

        var notification: Notification.Name {
            Notification.Name("VeraSummon." + rawValue)
        }
    }

    /// A panel written into the conversation.
    ///
    /// Bot mode is a chat, so what it produces belongs in the log: you
    /// asked for 設定, so 設定 is what sits under your line, and 記憶
    /// lands under the next one instead of replacing it. Storing the
    /// panel AS a message means the ordering, the scrollback and the
    /// history all come from the same place the text does — there is no
    /// second timeline to keep in step.
    ///
    /// The marker is a system message, so every other transcript already
    /// hides it (`visibleMessages` filters system by default) and no
    /// path can print it as text.
    static func marker(_ panel: Panel) -> String { "⟦panel:\(panel.rawValue)⟧" }

    static func panel(fromMarker content: String) -> Panel? {
        guard content.hasPrefix("⟦panel:"), content.hasSuffix("⟧") else { return nil }
        return Panel(rawValue: String(content.dropFirst(7).dropLast()))
    }

    enum Consent { case yes, no, unrelated }

    /// Consent read from a closed table, like everything else here. A
    /// document entering the store forever is exactly the decision that
    /// must not be inferred from an enthusiastic-sounding sentence.
    static func resolveConsent(_ raw: String) -> Consent {
        let s = raw.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if ["はい", "うん", "入れる", "いれる", "取り込む", "追加",
            "yes", "y", "ok", "お願い", "おねがい"].contains(s) { return .yes }
        if ["いいえ", "いや", "やめる", "入れない", "no", "n",
            "不要", "けっこう"].contains(s) { return .no }
        return .unrelated
    }

    struct Resolution {
        var panel: Panel?
        var mode: AppState.VeraEngineMode?
        var surface: AppState.FullSurface?
        var opensSettings = false
        var command: Command?
    }

    // MARK: - Commanding an app by name
    //
    // 「~/Documents/report.pdf をプレビューで開いて」 is a request to act, not
    // a request to navigate the UI — so unlike the panel table it works in
    // every mode. What keeps it safe is not the mode, it is that three
    // things must be present at once, all of them written by the person:
    //
    //   1. an explicit path (starts with / or ~/ or ./)
    //   2. an app named from a closed alias table
    //   3. a licence for that app and that verb
    //
    // Miss any one and nothing happens and the line falls through to the
    // model untouched. No inference about which file was probably meant, no
    // guessing at the app from the extension: a delegation Vera worked out
    // for itself is a delegation the person never authorised.

    private static let appAliases: [String: DelegatedApp] = [
        "vscode": .editor, "vs code": .editor, "code": .editor,
        "エディタ": .editor, "editor": .editor,
        "finder": .finder, "ファインダ": .finder, "ファインダー": .finder,
        "preview": .preview, "プレビュー": .preview,
        "notes": .notes, "メモ": .notes,
        "xcode": .xcode,
        "safari": .browser, "サファリ": .browser, "ブラウザ": .browser,
        "browser": .browser,
    ]

    /// A path the person typed, or nil. Deliberately literal — a bare word
    /// that happens to name a file in the workspace is not a path, it is a
    /// word, and resolving it would be Vera choosing the target.
    private static func explicitPath(in raw: String) -> String? {
        for token in raw.split(whereSeparator: { " 　\n\t、,".contains($0) }) {
            let t = token.trimmingCharacters(in: CharacterSet(charactersIn: "「」\"'"))
            if t.hasPrefix("/") || t.hasPrefix("~/") || t.hasPrefix("./") {
                return (t as NSString).expandingTildeInPath
            }
        }
        return nil
    }

    /// The request, when all three parts are there. Origin is `.user`
    /// because this is only ever called on a line the person typed; a model
    /// proposing an act goes through the tool path, which stamps its own.
    static func resolveDelegation(_ raw: String, goal: String) -> DelegationRequest? {
        guard let path = explicitPath(in: raw) else { return nil }
        let lower = raw.lowercased()
        // Longest alias first, so "vs code" is not read as "code".
        let named = appAliases.keys.sorted { $0.count > $1.count }
            .first { lower.contains($0) }
        guard let key = named, let app = appAliases[key] else { return nil }
        let verb: LicenceVerb = (app == .finder && !lower.contains("開")
                                 && !lower.contains("open")) ? .read : .open
        guard app.verbs.contains(verb) else { return nil }
        return DelegationRequest(app: app, verb: verb, payload: path,
                                 goal: goal, origin: .user)
    }

    /// Called only from Bot mode (see AppState.sendMessage). The table
    /// keeps every mode name so the way OUT of Bot is a word too — you
    /// should never have to reach for the pull-down to leave the mode
    /// that exists for reaching things by name.
    ///
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
        if let m = modes[s] { return Resolution(mode: m) }
        if let f = surfaces[s] { return Resolution(surface: f) }
        if let c = commands[s] { return Resolution(command: c) }
        if s == "モデル設定" || s == "api設定" || s == "api" {
            return Resolution(opensSettings: true)
        }
        if let p = table[s] { return Resolution(panel: p) }
        return nil
    }
}
