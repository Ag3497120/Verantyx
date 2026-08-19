import SwiftUI

/// Bot mode as an operator's console — dense on purpose.
///
/// Every other surface in this app was stripped: the chrome went so that
/// a person would not have to learn a second vocabulary beside the one
/// they type. That was right for the modes where the work is a
/// conversation.
///
/// Bot mode is not one of those. It is the mode ABOUT the app, and the
/// person in it is configuring, registering and inspecting rather than
/// asking. For that work a clean screen is an obstacle: forty-nine
/// persisted settings exist and most have never had a control, so the
/// only way to see one has been to know its key. A console that shows
/// them all is not clutter here — it is the subject.
///
/// So the rule stays intact and its scope is named: chrome is absent from
/// the conversation surfaces, and present on the one surface whose
/// subject is the machine.
struct VeraOperatorConsole: View {
    @EnvironmentObject var app: AppState
    @StateObject private var model = OperatorConsoleModel()
    @State private var filter: String = ""
    @State private var section: Section = .domains

    enum Section: String, CaseIterable, Identifiable {
        case domains = "分野"
        case documents = "文書"
        case ingest = "投入"
        case settings = "設定"
        case engine = "エンジン"
        var id: String { rawValue }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Divider().opacity(0.35)
            ScrollView {
                switch section {
                case .domains:   domainsBody
                case .documents: documentsBody
                case .ingest:    ingestBody
                case .settings:  settingsBody
                case .engine:    engineBody
                }
            }
        }
        .task { await model.refresh() }
    }

    // MARK: - chrome

    private var header: some View {
        HStack(spacing: 10) {
            Text("OPERATOR")
                .font(.system(size: 11, weight: .semibold, design: .monospaced))
                .tracking(2.0)
                .foregroundStyle(.secondary)
            Picker("", selection: $section) {
                ForEach(Section.allCases) { Text($0.rawValue).tag($0) }
            }
            .pickerStyle(.segmented)
            .frame(width: 240)
            Spacer()
            // The settings button people asked for. It does not open a
            // second surface — it moves this one, because a console with a
            // modal on top of it is two places to look for one thing.
            Button {
                section = .settings
            } label: {
                Label("設定", systemImage: "slider.horizontal.3")
                    .font(.system(size: 11))
            }
            .buttonStyle(.bordered)
            .help("Vera の永続設定をすべて表示")
            TextField("絞り込み", text: $filter)
                .textFieldStyle(.roundedBorder)
                .frame(width: 180)
            Button {
                Task { await model.refresh() }
            } label: {
                Image(systemName: "arrow.clockwise").font(.system(size: 11))
            }
            .buttonStyle(.plain)
            .help("読み直す")
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 9)
    }

    // MARK: - 分野

    private var domainsBody: some View {
        VStack(alignment: .leading, spacing: 12) {
            docDomainExplainer
            // The switch an enterprise deployment actually sets. Layering
            // lets the shared vocabulary answer whenever a domain is
            // silent, which is right for reach and wrong the moment a
            // reader takes the sentence as the organisation's own.
            Toggle(isOn: $app.veraDomainOnly) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("この分野の外に出ない").font(.system(size: 12))
                    Text("共有語彙に落ちず UNKNOWN_NOT_IN_DOMAIN で断る。"
                         + "業務導入ではこちらが安全側")
                        .font(.system(size: 10)).foregroundStyle(.secondary)
                }
            }
            .toggleStyle(.switch)

            row("使用中の分野", app.veraDomain.isEmpty ? "（共有のみ）" : app.veraDomain)

            if model.domains.isEmpty {
                Text("登録された分野はありません。文書を添付し「分野」と答えると"
                     + "その語彙が登録されます（文法は共有のまま）。")
                    .font(.system(size: 11)).foregroundStyle(.secondary)
            } else {
                // 複数分野の同時接続(2026-08-19)。カンマ区切りで持ち、
                // エンジン側は「順に試して最初の当たり」の層 — 表は
                // 混ぜない。並び順=優先順。
                let active = app.veraDomain.split(separator: ",").map(String.init)
                ForEach(model.domains, id: \.self) { d in
                    HStack {
                        Circle()
                            .fill(active.contains(d) ? VeraInk.verified : .clear)
                            .frame(width: 5, height: 5)
                        Text(d).font(.system(size: 12, design: .monospaced))
                        if let idx = active.firstIndex(of: d), active.count > 1 {
                            Text("優先\(idx + 1)")
                                .font(.system(size: 9)).foregroundStyle(.tertiary)
                        }
                        Spacer()
                        Button(active.contains(d) ? "解除" : "接続") {
                            var a = active
                            if let i = a.firstIndex(of: d) { a.remove(at: i) }
                            else { a.append(d) }
                            app.veraDomain = a.joined(separator: ",")
                        }
                        .buttonStyle(.link).font(.system(size: 11))
                    }
                }
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: - 共通の投入フォーム (文書/分野の両タブに同じものを置く)
    //
    // 投入面はこれ一つ(2026-08-19、ユーザ指示で集約)。旧経路 — 召喚
    // 「投入」、dockの投入タブ、<verantyx>タグ — は全て廃止した。
    // どちらへ入れるかはトグル: 文書のみ・分野のみ・両方。

    @State private var ingestURL: URL?
    @State private var ingestName = ""
    @State private var ingestToDocs = true
    @State private var ingestToDomain = false
    @State private var ingestWorking = false
    @State private var ingestNote = ""

    private var ingestForm: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("投入")
                .font(.system(size: 11, weight: .semibold))
            HStack(spacing: 8) {
                Button("ファイルを選ぶ…") {
                    let p = NSOpenPanel()
                    p.allowsMultipleSelection = false
                    p.canChooseDirectories = false
                    if p.runModal() == .OK, let u = p.url {
                        ingestURL = u
                        if ingestName.isEmpty {
                            ingestName = u.deletingPathExtension().lastPathComponent
                                .lowercased()
                                .replacingOccurrences(of: "[^a-z0-9_]", with: "_",
                                                      options: .regularExpression)
                        }
                    }
                }.font(.system(size: 11))
                if let u = ingestURL {
                    Text(u.lastPathComponent)
                        .font(.system(size: 10, design: .monospaced))
                        .lineLimit(1).truncationMode(.middle)
                        .foregroundStyle(.secondary)
                }
            }
            HStack(spacing: 14) {
                Toggle("文書に入れる（逐語引用の棚）", isOn: $ingestToDocs)
                    .toggleStyle(.checkbox).font(.system(size: 10))
                Toggle("分野に入れる（Writerの語彙）", isOn: $ingestToDomain)
                    .toggleStyle(.checkbox).font(.system(size: 10))
            }
            if ingestToDomain {
                TextField("分野名（英数字と _ のみ）", text: $ingestName)
                    .textFieldStyle(.roundedBorder)
                    .font(.system(size: 11))
                    .frame(maxWidth: 260)
            }
            Button(ingestWorking ? "投入中…" : "投入する") {
                guard let u = ingestURL else { return }
                ingestWorking = true
                let name = ingestName
                let toDocs = ingestToDocs, toDomain = ingestToDomain
                Task {
                    var out: [String] = []
                    if toDocs {
                        out.append(await VeraMemoryBridge.loadDocuments(paths: [u.path]))
                    }
                    if toDomain, !name.isEmpty {
                        out.append(await VeraMemoryBridge.registerDomain(name, path: u.path))
                    }
                    await MainActor.run {
                        ingestNote = out.joined(separator: "\n")
                        ingestWorking = false
                        Task {
                            docs = await VeraMemoryBridge.documentShelfFull()
                            await model.refresh()
                        }
                    }
                }
            }
            .disabled(ingestWorking || ingestURL == nil
                      || (!ingestToDocs && !ingestToDomain)
                      || (ingestToDomain && ingestName.isEmpty))
            .font(.system(size: 11))
            if !ingestNote.isEmpty {
                Text(ingestNote).font(.system(size: 10))
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(10)
        .background(.quaternary.opacity(0.15),
                    in: RoundedRectangle(cornerRadius: 6))
    }

    /// 投入タブ — 投入画面はここ一つ(2026-08-19、ユーザ指示で独立タブに)。
    /// チェックで行き先を選ぶ: 文書のみ・分野のみ・両方。
    private var ingestBody: some View {
        VStack(alignment: .leading, spacing: 12) {
            docDomainExplainer
            ingestForm
            Text("投入した後は、文書タブ(接続・優先度・構造)と分野タブ"
                 + "(接続)でそれぞれ配線を確認できます。")
                .font(.system(size: 10)).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// 文書と分野の違い — 両タブに同じ説明を置く(日本語)。
    private var docDomainExplainer: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text("文書と分野の違い")
                .font(.system(size: 10, weight: .semibold))
            Text("""
            ・文書 = 原文をそのまま保つ棚。質問には文書の行を逐語で引用して答え、\
            書かれていないことは「明記なし」と型で断ります。節・行・辺(同じ行に\
            書かれた語の対)の構造で保持され、判定に使われます。
            ・分野 = 文書から言葉だけを取り出した語彙。Veraが文を紡ぐときの\
            言葉になります(文法は共有のまま)。事実としては数えられず、票も\
            持ちません — 内容の根拠は常に文書側です。
            同じファイルを両方に入れられます: 文書に入れると「引用できる」、\
            分野に入れると「その言葉で話せる」ようになります。
            """)
                .font(.system(size: 9.5)).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(8)
        .background(.quaternary.opacity(0.1),
                    in: RoundedRectangle(cornerRadius: 6))
    }

    // MARK: - 文書 (棚と配線 — 分野の画面と同じ作法)

    @State private var docs: [VeraMemoryBridge.DocumentInfo] = []
    @State private var docNote = ""

    private var documentsBody: some View {
        VStack(alignment: .leading, spacing: 12) {
            docDomainExplainer
            Text("一度取り込んだ文書はここに残ります。「切断」は接続を切る"
                 + "だけでデータは保持され、いつでも再接続できます。優先度が"
                 + "高い文書から先に照合されます(企業の複数文書の配線)。"
                 + "本当に消すのは「削除」だけです。")
                .font(.system(size: 10)).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            HStack {
                Text("取り込み済み \(docs.count) 件"
                     + "（接続中 \(docs.filter { !$0.detached }.count)）")
                    .font(.system(size: 11, weight: .semibold))
                Spacer()
                Button("更新") { Task { docs = await VeraMemoryBridge.documentShelfFull() } }
                    .font(.system(size: 10))
            }

            if docs.isEmpty {
                Text("まだありません。投入タブの「文書として取り込む」で"
                     + "入れたものがここに現れます。")
                    .font(.system(size: 11)).foregroundStyle(.secondary)
            }
            ForEach(docs) { d in
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 8) {
                        Circle()
                            .fill(d.detached ? Color.secondary.opacity(0.3)
                                             : VeraInk.verified)
                            .frame(width: 6, height: 6)
                        Text(d.source)
                            .font(.system(size: 12, design: .monospaced))
                            .foregroundStyle(d.detached ? .secondary : .primary)
                            .lineLimit(1).truncationMode(.middle)
                        Text("節\(d.sections)・行\(d.lines)"
                             + (d.priority != 0 ? "・優先\(d.priority)" : ""))
                            .font(.system(size: 9)).foregroundStyle(.tertiary)
                        Spacer()
                        Button("▲") { Task {
                            await VeraMemoryBridge.setDocumentPriority(d.source, d.priority + 1)
                            docs = await VeraMemoryBridge.documentShelfFull()
                        } }.buttonStyle(.plain).font(.system(size: 9))
                            .help("優先度を上げる — 先に照合される")
                        Button("▼") { Task {
                            await VeraMemoryBridge.setDocumentPriority(d.source, d.priority - 1)
                            docs = await VeraMemoryBridge.documentShelfFull()
                        } }.buttonStyle(.plain).font(.system(size: 9))
                            .help("優先度を下げる — 判断を弱める")
                        Button(d.detached ? "再接続" : "切断") { Task {
                            docNote = d.detached
                                ? await VeraMemoryBridge.attachDocument(d.source)
                                : await VeraMemoryBridge.forgetDocument(d.source)
                            docs = await VeraMemoryBridge.documentShelfFull()
                        } }.buttonStyle(.link).font(.system(size: 11))
                        Button("削除") { Task {
                            docNote = await VeraMemoryBridge.purgeDocument(d.source)
                            docs = await VeraMemoryBridge.documentShelfFull()
                        } }.buttonStyle(.link).font(.system(size: 11))
                            .foregroundStyle(.red)
                            .help("完全削除 — こちらだけが本当に消します")
                    }
                    // 階層の可視化: 文書 → 節(行数・辺数)。モデルが実際に
                    // 保持している構造そのもの — 辺は同一文共起の実測。
                    DisclosureGroup {
                        VStack(alignment: .leading, spacing: 2) {
                            ForEach(Array(d.tree.enumerated()), id: \.offset) { _, s in
                                HStack(spacing: 6) {
                                    Text("└")
                                        .font(.system(size: 9))
                                        .foregroundStyle(.tertiary)
                                    Text(s.heading)
                                        .font(.system(size: 10, design: .monospaced))
                                        .lineLimit(1)
                                    Text("行\(s.lines)・辺\(s.edges)")
                                        .font(.system(size: 9))
                                        .foregroundStyle(.tertiary)
                                }
                            }
                        }.padding(.leading, 14)
                    } label: {
                        Text("構造(\(d.sections)節)")
                            .font(.system(size: 9)).foregroundStyle(.secondary)
                    }
                }
                .padding(8)
                .background(.quaternary.opacity(d.detached ? 0.08 : 0.18),
                            in: RoundedRectangle(cornerRadius: 6))
            }
            if !docNote.isEmpty {
                Text(docNote).font(.system(size: 10)).foregroundStyle(.secondary)
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .task { docs = await VeraMemoryBridge.documentShelfFull() }
    }

    // MARK: - 設定

    /// 使い分けチュートリアル — 場面から引ける形で設定画面に常置。
    private var usageTutorial: some View {
        DisclosureGroup {
            VStack(alignment: .leading, spacing: 6) {
                Group {
                    Text("📄 文書に入れる場面").font(.system(size: 10, weight: .semibold))
                    Text("""
                    ・社内規程や契約書を入れて「第5条には何と書いてある?」と\
                    条文どおりに引用してほしいとき
                    ・「書かれていないことは書かれていないと言ってほしい」とき\
                    (明記なしの型付き拒否が欲しい業務用途)
                    ・複数の規程を入れて、どれが答えたか出典を確かめたいとき
                    """).font(.system(size: 9.5)).foregroundStyle(.secondary)
                }
                Group {
                    Text("🗣 分野に入れる場面").font(.system(size: 10, weight: .semibold))
                    Text("""
                    ・専門用語だらけの資料を読ませて、その言葉づかいで文を\
                    紡いでほしいとき(医療・法務・社内略語など)
                    ・引用は要らないが「その分野の語彙で話せる」状態にしたい\
                    とき — 事実としては数えられず、票も持ちません
                    """).font(.system(size: 9.5)).foregroundStyle(.secondary)
                }
                Group {
                    Text("📄+🗣 両方に入れる場面(最も多い)").font(.system(size: 10, weight: .semibold))
                    Text("""
                    ・業務マニュアルを入れて「引用もしてほしいし、その用語で\
                    自然に説明もしてほしい」とき → 投入タブで両方にチェック
                    """).font(.system(size: 9.5)).foregroundStyle(.secondary)
                }
                Group {
                    Text("迷ったら").font(.system(size: 10, weight: .semibold))
                    Text("""
                    まず文書だけに入れてください。引用と型付き拒否はそれで\
                    全部動きます。話し方が固い・語彙が足りないと感じたら、\
                    同じファイルを分野にも足すのが安全な順番です。\
                    (分野を先に入れても内容の根拠は増えません — 根拠は常に文書側)
                    """).font(.system(size: 9.5)).foregroundStyle(.secondary)
                }
            }.padding(.top, 4)
        } label: {
            Text("📖 文書と分野の使い分け(チュートリアル)")
                .font(.system(size: 11, weight: .semibold))
        }
        .padding(10)
        .background(.quaternary.opacity(0.15),
                    in: RoundedRectangle(cornerRadius: 6))
        .padding(.bottom, 10)
    }

    private var settingsBody: some View {
        VStack(alignment: .leading, spacing: 0) {
            usageTutorial
            // ── 不足知識時のウェブ検索(2026-08-19) ─────────────────
            // 発火条件は一つ: Veraモードで型付き拒否(UNKNOWN*)が出たとき
            // だけ。答えが立った質問で外に出ることは構造上ない。
            VStack(alignment: .leading, spacing: 6) {
                Text("ウェブ検索(不足知識のとき)")
                    .font(.system(size: 11, weight: .semibold))
                Toggle(isOn: $app.toolWebSearchEnabled) {
                    VStack(alignment: .leading, spacing: 1) {
                        Text("ウェブ検索を認める").font(.system(size: 11))
                        Text("Veraが型付き拒否を出したときだけ発火。結果は"
                             + "一時知識(出典つき・返答と同時に破棄)")
                            .font(.system(size: 9)).foregroundStyle(.secondary)
                    }
                }.toggleStyle(.switch)
                if app.toolWebSearchEnabled {
                    Toggle(isOn: $app.veraWebAskFirst) {
                        VStack(alignment: .leading, spacing: 1) {
                            Text("実行前に確認する").font(.system(size: 11))
                            Text("ONなら拒否時に案内だけ出し、「検索して」で実行")
                                .font(.system(size: 9)).foregroundStyle(.secondary)
                        }
                    }.toggleStyle(.switch)
                    Stepper(value: $app.veraWebMaxPages, in: 1...4) {
                        Text("開くページ数の上限: \(app.veraWebMaxPages)")
                            .font(.system(size: 11))
                    }.frame(maxWidth: 280)
                    Toggle(isOn: $app.veraWebPropose) {
                        VStack(alignment: .leading, spacing: 1) {
                            Text("抜粋を承認キューへ提案する").font(.system(size: 11))
                            Text("人が accept するまで ask には見えない。"
                                 + "黙って構造に入る経路は無い")
                                .font(.system(size: 9)).foregroundStyle(.secondary)
                        }
                    }.toggleStyle(.switch)
                }
            }
            .padding(10)
            .background(.quaternary.opacity(0.15),
                        in: RoundedRectangle(cornerRadius: 6))
            .padding(.bottom, 10)

            Text("永続設定 \(shown.count) / \(model.settings.count) 件 — "
                 + "画面を持たないものも含めて全て")
                .font(.system(size: 10)).foregroundStyle(.secondary)
                .padding(.bottom, 8)
            ForEach(shown, id: \.key) { s in
                HStack(alignment: .top, spacing: 8) {
                    Text(s.key)
                        .font(.system(size: 11, design: .monospaced))
                        .frame(width: 230, alignment: .leading)
                        .textSelection(.enabled)
                    // A key holding a secret is shown as present, never as
                    // its value: this console is for operating the app, not
                    // for reading credentials off a shared screen.
                    Text(s.masked ? (s.value.isEmpty ? "—" : "●●●● (設定済み)")
                                  : (s.value.isEmpty ? "—" : s.value))
                        .font(.system(size: 11))
                        .foregroundStyle(s.value.isEmpty ? .tertiary : .primary)
                        .textSelection(.enabled)
                    Spacer()
                    Text(s.type)
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(.tertiary)
                }
                .padding(.vertical, 3)
                Divider().opacity(0.15)
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var shown: [OperatorConsoleModel.Setting] {
        let f = filter.trimmingCharacters(in: .whitespaces).lowercased()
        return f.isEmpty ? model.settings
            : model.settings.filter { $0.key.lowercased().contains(f) }
    }

    // MARK: - エンジン

    private var engineBody: some View {
        VStack(alignment: .leading, spacing: 8) {
            row("核", model.cores.map { fmt($0) } ?? "—")
            row("面リンク", model.facets.map { fmt($0) } ?? "—")
            row("文", model.sentences.map { fmt($0) } ?? "—")
            row("出所", model.source.isEmpty ? "—" : model.source)
            row("モード", String(describing: app.veraEngineMode))
            Text(model.note).font(.system(size: 10))
                .foregroundStyle(.secondary).padding(.top, 6)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func fmt(_ n: Int) -> String {
        let f = NumberFormatter(); f.numberStyle = .decimal
        return f.string(from: NSNumber(value: n)) ?? String(n)
    }

    private func row(_ k: String, _ v: String) -> some View {
        HStack {
            Text(k).font(.system(size: 11)).foregroundStyle(.secondary)
                .frame(width: 130, alignment: .leading)
            Text(v).font(.system(size: 12, design: .monospaced))
                .textSelection(.enabled)
            Spacer()
        }
    }
}

/// Reads what the console shows. Numbers come from the engine or from
/// UserDefaults; nothing here is invented, and a value the engine did not
/// return stays nil and renders as「—」rather than as a zero.
@MainActor
final class OperatorConsoleModel: ObservableObject {
    struct Setting: Hashable {
        let key: String
        let value: String
        let type: String
        let masked: Bool
    }

    @Published private(set) var domains: [String] = []
    @Published private(set) var settings: [Setting] = []
    @Published private(set) var doors: Int?
    @Published private(set) var cores: Int?
    @Published private(set) var facets: Int?
    @Published private(set) var sentences: Int?
    @Published private(set) var source: String = ""
    @Published private(set) var note: String = ""

    /// Substrings that mark a value as a secret. Closed and matched on the
    /// KEY, because a value that looks harmless today may not tomorrow.
    private static let secret = ["api_key", "token", "secret", "password"]

    func refresh() async {
        settings = Self.readDefaults()
        if let obj = await VeraMemoryBridge.callDoor("vera_domains", [:]),
           let list = obj["domains"] as? [String] {
            domains = list
        }
        if let obj = await VeraMemoryBridge.callDoor("stats", [:]) {
            // Measured against the live engine: the door returns
            // n_cores / n_facet_links / n_sentences / source. Reading
            // "cores" and "facets" got nil and rendered as 「—」, which
            // looked exactly like an engine that had not answered.
            cores = obj["n_cores"] as? Int
            facets = obj["n_facet_links"] as? Int
            sentences = obj["n_sentences"] as? Int
            source = (obj["source"] as? String) ?? ""
            note = ""
        } else {
            note = "エンジンが応答しません。数値は表示しません（0とは書きません）。"
        }
    }

    private static func readDefaults() -> [Setting] {
        let d = UserDefaults.standard.dictionaryRepresentation()
        // Apple's own domains are in here too; the console is about this
        // app, so anything that is plainly system-owned is left out rather
        // than shown as if the operator could meaningfully change it.
        let skip = ["NS", "Apple", "com.apple", "AK", "WebKit", "PK"]
        return d.keys
            .filter { k in !skip.contains { k.hasPrefix($0) } }
            .sorted()
            .map { k in
                let v = d[k]
                return Setting(
                    key: k,
                    value: String(describing: v ?? "").prefix(120).description,
                    type: String(describing: type(of: v ?? "")),
                    masked: secret.contains { k.lowercased().contains($0) })
            }
    }
}
