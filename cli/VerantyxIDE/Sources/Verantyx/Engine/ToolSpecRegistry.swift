import Foundation

// MARK: - The declarations, and everything derived from them
//
// Adding a tool means adding one entry here. The documentation the model sees
// and the parser that reads its reply both come from that entry, so they
// cannot disagree — and `selfCheck()` proves it on every launch rather than
// waiting for a user to notice the word "text" in an address bar.
//
// Migration is deliberately partial. These specs run FIRST; anything they do
// not claim falls through to the existing chain in AgentToolParser untouched.
// The tools declared here are the ones whose shape actually caused bugs:
// free-text arguments and verb-plus-argument grammars. The rest can move over
// as they are touched, without a flag day.
enum ToolSpecRegistry {

    /// The delegation catalogue, GENERATED from the licence book.
    ///
    /// This is the same argument the file already makes about docs and
    /// parsers, applied one level out: what the model may ask for and what
    /// the user may grant are two hand-written lists that have to agree,
    /// and nothing would check that they did. Deriving both from
    /// `DelegatedApp` means a new app becomes callable and grantable in one
    /// edit, and a verb that exists in only one of the two places cannot be
    /// expressed.
    ///
    /// `.run` is excluded on purpose: [RUN:] and [OSASCRIPT:] already carry
    /// it, and two ways to do one thing is how a model ends up choosing by
    /// coin-flip.
    private static var delegationVerbs: [VerbSpec] {
        DelegatedApp.allCases.flatMap { app in
            app.verbs.filter { $0 != .run }.map { verb -> VerbSpec in
                VerbSpec(verb: "\(app.rawValue).\(verb.rawValue)",
                         argument: Self.delegationArgument(app: app, verb: verb),
                         ja: Self.delegationHint(app: app, verb: verb))
            }
        }
    }

    private static func delegationArgument(app: DelegatedApp,
                                           verb: LicenceVerb) -> ArgShape {
        switch (app, verb) {
        case (.browser, .open): return .freeText(ja: "URL", en: "URL")
        case (.browser, .read): return .none
        default:                return .path(ja: "ファイルの場所", en: "path")
        }
    }

    private static func delegationHint(app: DelegatedApp,
                                       verb: LicenceVerb) -> String {
        switch (app, verb) {
        case (.finder, .read):  return "フォルダの中身を一覧する"
        case (.finder, .open):  return "Finderで場所を表示する"
        case (.finder, .move):  return "ファイルを移動する"
        case (.editor, .open):  return "コードやテキストをVS Codeで開く"
        case (.browser, .open): return "URLをSafariで開く"
        case (.browser, .read): return "いま開いているページの本文を読む"
        case (.preview, .open): return "PDFや画像をプレビューで開く"
        case (.notes, .open):   return "メモで開く"
        case (.xcode, .open):   return "Xcodeで開く"
        default:                return "\(app.displayName)に渡す"
        }
    }

    static let specs: [ToolSpec] = [

        // The tool the whole app-delegation design exists for: Vera does not
        // reimplement Preview, it hands the PDF to Preview. What the model
        // decides is WHICH app, and it says so in the argument.
        ToolSpec(
            name: "DELEGATE",
            shape: .verbs(Self.delegationVerbs),
            ja: "そのファイルを扱えるアプリに渡す（免許が要る・結果は証拠として残る）",
            build: { arg in
                let payload = Self.unwrapVerbPayload(arg)
                let parts = arg.trimmingCharacters(in: .whitespaces)
                    .split(separator: " ", maxSplits: 1).map(String.init)
                guard let head = parts.first else { return nil }
                let pair = head.split(separator: ".").map(String.init)
                guard pair.count == 2,
                      let app = DelegatedApp(rawValue: pair[0]),
                      let verb = LicenceVerb(rawValue: pair[1]),
                      app.verbs.contains(verb) else { return nil }
                let target = parts.count > 1
                    ? Placeholder.unwrap(parts[1]).trimmingCharacters(in: .whitespaces)
                    : ""
                // Read needs no target; everything else without one would
                // be Vera choosing the file, which is the one inference
                // this design refuses to make.
                if target.isEmpty && !(app == .browser && verb == .read) {
                    return nil
                }
                _ = payload
                return .delegate(app: app, verb: verb,
                                 target: (target as NSString).expandingTildeInPath)
            }
        ),


        // The tool that produced the "type text" bug. Its verbs are data now,
        // so the rendered documentation cannot contain a word the parser does
        // not know — which is exactly what `text` was.
        ToolSpec(
            name: "DESKTOP_ACT",
            shape: .verbs([
                VerbSpec(verb: "click", argument: .freeText(ja: "x座標 y座標", en: "x y"),
                         ja: "画面座標を押す"),
                VerbSpec(verb: "type", argument: .freeText(ja: "打ち込む文字", en: "the characters to type"),
                         ja: "キーボード入力"),
                VerbSpec(verb: "scroll", argument: .freeText(ja: "up|down", en: "up|down"),
                         ja: "スクロール"),
            ]),
            ja: "画面全体を直接操作する",
            build: { arg in .desktopAct(action: Self.unwrapVerbPayload(arg)) }
        ),

        ToolSpec(
            name: "VISION_ACT",
            shape: .verbs([
                VerbSpec(verb: "click", argument: .freeText(ja: "x座標 y座標", en: "x y"),
                         ja: "座標を押してスクショ"),
                VerbSpec(verb: "type", argument: .freeText(ja: "打ち込む文字", en: "the characters to type"),
                         ja: "入力してスクショ"),
                VerbSpec(verb: "scroll", argument: .freeText(ja: "up|down", en: "up|down"),
                         ja: "スクロールしてスクショ"),
            ]),
            ja: "操作して結果を撮影する",
            build: { arg in .visionAct(action: Self.unwrapVerbPayload(arg)) }
        ),

        // The answer to an app with no accessibility tree. Declared here so
        // the model is TOLD it exists — the run that needed it had to derive
        // the whole approach itself, install PyObjC, and write a throwaway
        // OCR script, because nothing in the documentation said the app could
        // already do this.
        ToolSpec(
            name: "READ_SCREEN",
            shape: .none,
            ja: "取り付けたアプリの画面を文字として読む（AXが空のときに使う・座標つきで返る）",
            build: { _ in .readScreen }
        ),

        ToolSpec(
            name: "MENU",
            shape: .pathList(ja: "メニュー ▸ 項目", en: "Menu > Item"),
            ja: "アプリが公開しているメニュー命令を実行（座標不要・最も確実）",
            build: { arg in .menu(path: arg) }
        ),

        ToolSpec(
            name: "KEYS",
            shape: .freeText(ja: "cmd+s のようなキー", en: "a key combination"),
            ja: "取り付けたアプリにキー操作を送る",
            build: { arg in .keys(combo: arg) }
        ),

        ToolSpec(
            name: "APP_CAPS",
            shape: .none,
            ja: "そのアプリがどの方法で操作できるかを先に調べる",
            build: { _ in .appCaps }
        ),

        ToolSpec(
            name: "USE_APP",
            shape: .optionalText(ja: "アプリ名", en: "app name"),
            ja: "ユーザーが今開いているアプリに取り付く（省略時は直前のアプリ）",
            build: { arg in .useApp(name: arg.isEmpty ? nil : arg) }
        ),

        ToolSpec(
            name: "CLICK_LINK",
            shape: .freeText(ja: "画面に見えている文字", en: "the visible text"),
            ja: "その文字の要素をマウスで押す",
            build: { arg in .clickLink(text: arg) }
        ),

        ToolSpec(
            name: "SCROLL_FIND",
            shape: .freeText(ja: "探す文字", en: "text to find"),
            ja: "画面外ならスクロールしながら探す",
            build: { arg in .scrollFind(text: arg) }
        ),
    ]

    private static let byName: [String: ToolSpec] = {
        // Publish every rendered label so the placeholder check is derived
        // from the declarations rather than duplicating them.
        var labels = Set<String>()
        func collect(_ shape: ArgShape) {
            switch shape {
            case .none: break
            case .freeText(let ja, let en), .optionalText(let ja, let en),
                 .path(let ja, let en), .pathList(let ja, let en):
                labels.insert(ja.lowercased()); labels.insert(en.lowercased())
            case .verbs(let vs):
                for v in vs { collect(v.argument) }
            }
        }
        for s in specs { collect(s.shape) }
        Placeholder.knownLabels = labels
        return Dictionary(uniqueKeysWithValues: specs.map { ($0.name, $0) })
    }()

    /// "type ⟨ChatGPT⟩" → "type ChatGPT". The verb stays; only its payload
    /// carries the brackets the model copied from the rendered form.
    static func unwrapVerbPayload(_ arg: String) -> String {
        let parts = arg.split(separator: " ", maxSplits: 1, omittingEmptySubsequences: true)
        guard parts.count == 2 else { return arg }
        return "\(parts[0]) \(Placeholder.unwrap(String(parts[1])))"
    }

    // MARK: - Documentation, generated

    /// The block handed to the model. Never edited by hand.
    static func docBlock() -> String {
        // The first line is placed by the literal's own indentation; the rest
        // carry theirs, so the block lines up under the TOOLS heading.
        specs.map(\.docLine).joined(separator: "\n    ")
    }

    /// What is licensed RIGHT NOW, generated from the same book the grants
    /// are kept in.
    ///
    /// The model is told, rather than left to discover it by being refused,
    /// because those produce different behaviour: a model that knows asks
    /// the person for the licence, and a model that finds out asks the
    /// machine again. The line is generated for the same reason the tool
    /// docs are — a hand-written summary of a live set is a summary that
    /// will be wrong on the day it matters.
    @MainActor
    static func licenceBlock() -> String {
        let store = AppLicenceStore.shared
        var lines: [String] = []
        for app in DelegatedApp.allCases {
            let granted = app.verbs.filter { store.isGranted(app, $0) }
            guard !granted.isEmpty else { continue }
            lines.append("    \(app.rawValue): "
                         + granted.map(\.rawValue).joined(separator: ", "))
        }
        if lines.isEmpty {
            return "    （現在ゼロ。アプリを動かす操作はすべて拒否されます。"
                 + "必要なら、ユーザーに「免許」と入力して許可するよう頼んでください。）"
        }
        return lines.joined(separator: "\n")
            + "\n    上に無いものは拒否されます。必要なら、ユーザーに「免許」と入力して"
            + "許可するよう頼んでください — 自分で回避しようとしないでください。"
    }

    // MARK: - Parsing, from the same declarations

    /// Read one line. Returns a verdict, never a silent nothing.
    static func parse(line: String) -> ParseVerdict {
        let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let re = try? NSRegularExpression(pattern: #"\[([A-Z][A-Z0-9_]{1,30})(?::\s*([^\]]*))?\]"#),
              let m = re.firstMatch(in: trimmed,
                                    range: NSRange(trimmed.startIndex..., in: trimmed))
        else { return .notATool }

        let ns = trimmed as NSString
        let name = ns.substring(with: m.range(at: 1))
        let rawArg = m.range(at: 2).location == NSNotFound
            ? "" : ns.substring(with: m.range(at: 2)).trimmingCharacters(in: .whitespaces)

        guard let spec = byName[name] else {
            // Not ours — the legacy chain may still know it. Only tags that
            // look like tools but belong to nobody are reported as unknown,
            // and that judgement is made by the caller which sees both.
            return .notATool
        }

        // 判定 — the placeholder check comes first, because a placeholder that
        // reaches the executor is the failure mode this whole file exists for.
        if !rawArg.isEmpty, Placeholder.isUnfilled(rawArg) {
            return .placeholderLeftIn(tool: name, placeholder: rawArg)
        }

        switch spec.shape {
        case .none:
            guard rawArg.isEmpty else {
                return .malformed(tool: name, why: "引数は取りません",
                                  expected: "[\(name)]")
            }

        case .freeText, .path, .pathList:
            guard !rawArg.isEmpty else {
                return .malformed(tool: name, why: "引数がありません",
                                  expected: spec.docLine.trimmingCharacters(in: .whitespaces))
            }

        case .optionalText:
            break

        case .verbs(let verbs):
            let head = rawArg.split(separator: " ", maxSplits: 1,
                                    omittingEmptySubsequences: true).first.map(String.init) ?? ""
            guard let verb = verbs.first(where: { $0.verb.caseInsensitiveCompare(head) == .orderedSame })
            else {
                return .malformed(
                    tool: name,
                    why: head.isEmpty ? "動作が書かれていません" : "「\(head)」という動作はありません",
                    expected: "[\(name): " + verbs.map(\.verb).joined(separator: " | ") + " …]")
            }
            // The verb's own argument gets the same placeholder judgement.
            // This is the specific check that would have caught `type text …`
            // at the door instead of at the address bar.
            let verbArg = rawArg.dropFirst(head.count).trimmingCharacters(in: .whitespaces)
            if case .none = verb.argument {
                break
            }
            guard !verbArg.isEmpty else {
                return .malformed(tool: name, why: "\(verb.verb) の内容がありません",
                                  expected: "[\(name): \(verb.verb) …]")
            }
            if Placeholder.isUnfilled(verbArg) {
                return .placeholderLeftIn(tool: name, placeholder: verbArg)
            }
            if let firstWord = verbArg.split(separator: " ").first.map(String.init),
               Placeholder.isUnfilled(firstWord) {
                return .placeholderLeftIn(tool: name, placeholder: firstWord)
            }
        }

        // A bracketed real value is accepted with the brackets removed.
        let cleanArg = Placeholder.unwrap(rawArg)
        guard let tool = spec.build(cleanArg) else {
            return .malformed(tool: name, why: "引数を解釈できません",
                              expected: spec.docLine.trimmingCharacters(in: .whitespaces))
        }
        return .tool(tool)
    }

    // MARK: - Proving the two halves agree

    /// Every spec's own example must parse back to a tool, and every rendered
    /// documentation line must NOT — because its placeholders are unfillable
    /// by construction.
    ///
    /// Two properties, one consequence: what the model is shown can never be
    /// copied verbatim into a working-looking call, and what the parser
    /// accepts is always something the docs can express. Run at launch, so a
    /// broken tool is loud immediately rather than after a user watches it
    /// type a placeholder into a browser.
    /// The last result, kept so the check is READABLE rather than merely
    /// performed. It ran at launch and wrote to NSLog, which on an ad-hoc
    /// build reaches nobody — a check whose outcome you cannot see is a
    /// check you have to take on faith, which is the thing this project is
    /// against.
    nonisolated(unsafe) static var lastSelfCheck: [String] = []
    nonisolated(unsafe) static var selfCheckRan = false

    static func selfCheck() -> [String] {
        var problems: [String] = []

        for spec in specs {
            switch parse(line: spec.roundTripExample) {
            case .tool:
                break
            case let other:
                problems.append("\(spec.name): 例 \(spec.roundTripExample) が解釈できません "
                                + "(\(other.correction ?? "unknown"))")
            }

            // Pull the usage form out of the generated doc line and confirm
            // that copying it verbatim is REFUSED rather than executed.
            if let usage = spec.docLine.split(separator: " ").first.map(String.init),
               usage.contains(Placeholder.open) {
                if case .tool = parse(line: usage) {
                    problems.append("\(spec.name): 説明文をそのまま書くと実行されてしまいます "
                                    + "— プレースホルダが素通りしています")
                }
            }
        }

        // Names must be unique, or `byName` silently drops one.
        let names = specs.map(\.name)
        if names.count != Set(names).count {
            problems.append("重複したツール名があります: \(names)")
        }
        lastSelfCheck = problems
        selfCheckRan = true
        return problems
    }
}
