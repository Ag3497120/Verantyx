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
// MARK: - Every settings screen, declared once
//
// The settings were in five different kinds of place: eight tabs inside
// SettingsView, panels that only a typed word could raise, surfaces that took
// the whole window, tabs buried inside the Vera dock, and one switch
// (`jcross_menu_style`) living in the footer of a menu with no home at all.
//
// Five kinds of place means five things to remember, and the person who wants
// to change something has to already know which kind it is. Worse, the two
// lists that SHOULD exist — "everything you can configure" and "everything you
// can say" — were about to be written by hand twice, which is the drift this
// codebase keeps paying for (docs vs parser, tool list vs licence book).
//
// So: one declaration per screen, and both lists derived from it. A screen
// added here appears in Settings AND becomes summonable in the same edit; a
// screen present in only one of the two cannot be expressed.
enum VeraSettingsRegistry {

    /// Where a screen lives. Not a style choice — these behave differently
    /// and the reader should be able to tell which one they are getting.
    enum Destination {
        /// Rendered into the conversation, under the line that asked.
        case panel(VeraSummon.Panel)
        /// Takes the whole window, with a way back.
        case full(AppState.FullSurface)
        /// A tab inside the Vera dock, opened directly on that tab.
        case dock(String)
        /// A tab of the SettingsView sheet.
        case settingsTab(String)
    }

    struct Screen: Identifiable {
        let id: String
        let ja: String
        let en: String
        /// What it decides — written as the consequence, so the row is worth
        /// reading to someone who does not already know the name.
        let blurbJa: String
        let words: [String]
        let destination: Destination

        var title: String { AppLanguage.shared.t(en, ja) }
        /// The shortest word that reaches it, for the list.
        var say: String { words.first ?? id }
    }

    static let screens: [Screen] = [

        // ── 会話に出るもの ────────────────────────────────────────
        Screen(id: "settings", ja: "設定", en: "Settings",
               blurbJa: "モデル・API鍵・道具・記憶・プライバシーの本体",
               words: ["設定", "せってい", "settings", "setting"],
               destination: .panel(.settings)),
        Screen(id: "screen", ja: "画面", en: "Screen",
               blurbJa: "常に前面にするか、スクショに写すか、メニューの開き方",
               words: ["画面", "がめん", "screen", "前面", "スクショ", "window"],
               destination: .panel(.screen)),
        Screen(id: "licences", ja: "免許", en: "Licences",
               blurbJa: "どのアプリの、どの行為をVeraに許すか。実行の記録つき",
               words: ["免許", "めんきょ", "licence", "license", "権限", "許可", "アプリ"],
               destination: .panel(.licences)),
        Screen(id: "jgen", ja: "JGEN層", en: "JGEN layers",
               blurbJa: "記憶層・合議核・実行エージェント・エスカレーション",
               words: ["jgen設定", "engine", "エンジン", "層", "レイヤ", "layers"],
               destination: .panel(.jgen)),
        Screen(id: "memory", ja: "記憶", en: "Memory",
               blurbJa: "台帳の承認と、限界値の引き上げ提案",
               words: ["記憶", "きおく", "memory", "記憶パネル"],
               destination: .panel(.memory)),
        Screen(id: "modes", ja: "モード", en: "Modes",
               blurbJa: "どの性格が答えるか。Atelier / Vera / Bot / LLM",
               words: ["モード", "modes", "モード切替"],
               destination: .panel(.modes)),
        Screen(id: "model", ja: "モデル", en: "Model",
               blurbJa: "会話に使うモデルの切り替え先の案内",
               words: ["モデル", "model", "モデル切替"],
               destination: .panel(.model)),
        Screen(id: "cross", ja: "立体十字", en: "Stereo cross",
               blurbJa: "答えが通った経路の図",
               words: ["十字", "立体十字", "立体十字構造体", "構造", "cross"],
               destination: .panel(.cross)),
        Screen(id: "audit", ja: "監査", en: "Audit",
               blurbJa: "直近の実行の要約と、証拠・矛盾・欠落の数",
               words: ["監査", "audit"],
               destination: .panel(.audit)),
        // 「投入」の召喚は廃止(2026-08-19): 投入は OPERATOR の文書/分野
        // 画面の共通フォーム一つに集約された。言葉で開く入口が別に残ると
        // 投入面が二つになり、二つの面は漂流する。

        // ── 全画面を取るもの ──────────────────────────────────────
        Screen(id: "mcp", ja: "外部運用", en: "External operation",
               blurbJa: "記憶ストア・JGENの選択・MCPサーバー一覧",
               words: ["mcp", "外部運用", "外部"],
               destination: .full(.mcp)),
        Screen(id: "veraSettings", ja: "Vera 設定", en: "Vera settings",
               blurbJa: "Vera 機能のドック全体",
               words: ["vera設定", "vera設定", "ドック", "dock"],
               destination: .full(.veraSettings)),
        Screen(id: "growth", ja: "学習（成長）", en: "Learning",
               blurbJa: "何を覚え、何が隔離されたか",
               words: ["成長", "学習", "growth"],
               destination: .full(.growth)),
        Screen(id: "evolution", ja: "自己進化", en: "Self-evolution",
               blurbJa: "IDE自身のソース改変とPR",
               words: ["進化", "自己進化", "evolution"],
               destination: .full(.evolution)),

        // ── ドックの中に埋まっていたもの ────────────────────────
        Screen(id: "research", ja: "失敗の型", en: "Failure types",
               blurbJa: "どの種類の失敗を、何回踏んだか",
               words: ["失敗", "失敗の型", "failures"],
               destination: .dock("research")),
        Screen(id: "distributed", ja: "2台構成", en: "Two Macs",
               blurbJa: "もう一台への接続と役割分担",
               words: ["2台", "二台", "2台構成", "pipe"],
               destination: .dock("distributed")),
        Screen(id: "stereoCross", ja: "立体十字グラフ", en: "3D graph",
               blurbJa: "格子そのものを回して見る",
               words: ["3d", "グラフ", "graph"],
               destination: .dock("stereoCross")),
        Screen(id: "vectorLab", ja: "ベクトルラボ", en: "Vector lab",
               blurbJa: "ベクトル空間を直接触る",
               words: ["ベクトル", "ラボ", "vectorlab"],
               destination: .dock("vectorLab")),

        // ── 設定シートのタブ ──────────────────────────────────────
        Screen(id: "tab.model", ja: "モデル設定", en: "Model settings",
               blurbJa: "エンドポイント・温度・最大トークン",
               words: ["モデル設定", "推論", "temperature"],
               destination: .settingsTab("Model")),
        Screen(id: "tab.apiKeys", ja: "API鍵", en: "API keys",
               blurbJa: "クラウド各社の鍵と接続確認",
               words: ["api", "api設定", "鍵", "apikey"],
               destination: .settingsTab("API Keys")),
        Screen(id: "tab.tools", ja: "道具", en: "Tools",
               blurbJa: "エージェントに許す道具の有効・無効",
               words: ["道具", "ツール", "tools"],
               destination: .settingsTab("Tools")),
        Screen(id: "tab.agent", ja: "エージェント", en: "Agent",
               blurbJa: "実演・パイプライン・振る舞い",
               words: ["エージェント", "agent", "実演"],
               destination: .settingsTab("Agent")),
        Screen(id: "tab.privacy", ja: "プライバシー", en: "Privacy",
               blurbJa: "外へ出す前に何を伏せるか",
               words: ["プライバシー", "privacy", "秘匿"],
               destination: .settingsTab("Privacy")),
        Screen(id: "tab.general", ja: "一般", en: "General",
               blurbJa: "言語・更新・その他",
               words: ["一般", "general"],
               destination: .settingsTab("General")),
    ]

    /// The word tables, generated. Both halves of the answer to "where do I
    /// change this" come from `screens` above, so a screen cannot be in the
    /// settings list without being sayable, or sayable without being listed.
    static var wordToScreen: [String: Screen] {
        var out: [String: Screen] = [:]
        for screen in screens {
            for word in screen.words where out[word] == nil {
                out[word] = screen
            }
        }
        return out
    }
}

enum VeraSummon {
    enum Panel: String, Identifiable, CaseIterable {
        case settings, memory, cross, audit, modes, model, licences, screen, jgen
        case document
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
            case .document: return "投入"
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
        // 「投入」系の語は表から外した(2026-08-19) — 投入は OPERATOR の
        // 文書/分野画面の共通フォームだけが行う。
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
        "vera設定": .veraSettings, "vera設定": .veraSettings,
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
        "llmモード": .localLLM, "llm": .localLLM,
        "atelier": .atelier, "アトリエ": .atelier, "服飾": .atelier,
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

    /// `.domain` is a THIRD answer, not a flavour of yes. Ingesting a
    /// document into the store and registering its vocabulary as a domain
    /// are different acts with different consequences: the first adds
    /// facts that vote, the second adds words that only speak. Folding
    /// them into one 「はい」 would make the cheaper answer carry the
    /// heavier one.
    enum Consent { case yes, no, domain, unrelated }

    /// Consent read from a closed table, like everything else here. A
    /// document entering the store forever is exactly the decision that
    /// must not be inferred from an enthusiastic-sounding sentence.
    static func resolveConsent(_ raw: String) -> Consent {
        let s = raw.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if ["はい", "うん", "入れる", "いれる", "取り込む", "追加",
            "yes", "y", "ok", "お願い", "おねがい"].contains(s) { return .yes }
        if ["いいえ", "いや", "やめる", "入れない", "no", "n",
            "不要", "けっこう"].contains(s) { return .no }
        // Exact match, like every other table here: 「分野にしたいんだけど」
        // is a sentence ABOUT registering, not a request to register.
        if ["分野", "ぶんや", "語彙", "domain", "分野にする",
            "分野として"].contains(s) { return .domain }
        return .unrelated
    }

    struct Resolution {
        var panel: Panel?
        var mode: AppState.VeraEngineMode?
        var surface: AppState.FullSurface?
        var opensSettings = false
        var command: Command?
        /// Which tab the surface or sheet should land on, when the word named
        /// something more specific than the screen that holds it.
        var dockTab: String?
        var settingsTab: String?
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
        // Modes first: a word that names a mode has always meant the mode,
        // and the registry must not quietly take one over.
        if let m = modes[s] { return Resolution(mode: m) }
        // Commands next: starting a run and opening a screen are different
        // promises, and the table that hides both would make the safe half
        // unsafe.
        if let c = commands[s] { return Resolution(command: c) }
        // Then every settings screen, from the one declaration.
        if let screen = VeraSettingsRegistry.wordToScreen[s] {
            switch screen.destination {
            case .panel(let p):        return Resolution(panel: p)
            case .full(let f):         return Resolution(surface: f)
            case .dock(let tab):       return Resolution(surface: .veraSettings,
                                                         dockTab: tab)
            case .settingsTab(let t):  return Resolution(opensSettings: true,
                                                         settingsTab: t)
            }
        }
        if let p = table[s] { return Resolution(panel: p) }
        return nil
    }
}
