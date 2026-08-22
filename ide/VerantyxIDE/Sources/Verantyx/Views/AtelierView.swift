import SwiftUI

/// Vera Atelier — 服飾のワークベンチ。IDE の作業面をこれに替える。
///
/// **チャットではありません。** 中央は服そのもの、右は構造インスペクタ、
/// 下は証拠の時系列。作業者が見るのは 画像 → 証拠 → 構造 → 推定 → 未知 →
/// 設計 で、Vera は画面に出てくる登場人物ではなく、その裏で状態を持って
/// いる構造エンジンです。
///
/// 情報整理は必ず Vera を通ります。台帳への入口は MCP の扉
/// (`garment_observe` / `garment_infer` / `garment_propose` /
/// `garment_adopt`)しか無く、**モデルが「事実」を直接書ける道はありません。**
/// クラウドの AI もローカルの LLM も置けるのは提案までで、採用は人の行為、
/// 採用者の名前が残ります。モデルの選択欄(上のモデルピッカー)は、
/// のちに「どの AI に解析させるか」を選ぶ場所になります。
struct AtelierView: View {
    @EnvironmentObject var app: AppState
    @StateObject private var m = AtelierModel()
    @StateObject private var an = AtelierAnalyst()
    @State private var showAnalyst = false

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider().opacity(0.35)
            if let err = m.engineError { engineBanner(err) }
            HStack(spacing: 0) {
                rail.frame(width: 168)
                Divider().opacity(0.25)
                workspace.frame(maxWidth: .infinity)
                Divider().opacity(0.25)
                inspector.frame(width: 300)
            }
            Divider().opacity(0.35)
            bottom.frame(height: 168)
        }
        .background(AT.bg)
        .task {
            await m.load()
            await an.refresh(app: app)
        }
        .sheet(isPresented: $m.showTechPack) { TechPackSheet(m: m) }
        .sheet(isPresented: $showAnalyst) {
            AnalystSheet(an: an, m: m).environmentObject(app)
        }
    }

    // MARK: - engine が答えなかったとき

    /// 台帳が空なのではなく、**engine に届かなかった**。この二つを同じ
    /// 見え方にすると、動いているエンジンを前にして壊れて見える。
    private func engineBanner(_ err: String) -> some View {
        HStack(spacing: 10) {
            Text("UNKNOWN_ENGINE_UNREACHABLE")
                .font(.system(size: 10, weight: .semibold, design: .monospaced))
                .foregroundStyle(AT.bad)
            Text(app.t("The ledger below is not empty — it is unread.",
                       "下の台帳は空ではなく、読めていません。"))
                .font(.system(size: 10)).foregroundStyle(AT.dim)
            Text(err).font(.system(size: 9, design: .monospaced))
                .foregroundStyle(AT.faint).lineLimit(1)
            Spacer(minLength: 0)
            Button(app.t("Reconnect", "接続し直す")) {
                Task { await m.reconnect() }
            }.font(.system(size: 10))
        }
        .padding(.horizontal, 14).padding(.vertical, 6)
        .background(AT.bad.opacity(0.12))
    }

    // MARK: - 上帯

    private var header: some View {
        HStack(spacing: 12) {
            Text("Vera Atelier").font(.system(size: 13, weight: .semibold))
            Text("Project: \(m.projectName)")
                .font(.system(size: 11)).foregroundStyle(AT.dim)
            if m.loading { ProgressView().controlSize(.small) }
            Spacer()
            Button(m.anime ? app.t("Film Mode", "実写モード")
                           : app.t("Anime Mode", "アニメモード")) {
                m.anime.toggle()
            }.font(.system(size: 11))
            Button(app.t("Send to Maker", "縫製師に渡す")) {
                Task { await m.loadTechPack() }
            }.font(.system(size: 11))
        }
        .padding(.horizontal, 14).padding(.vertical, 9)
        .background(AT.panel)
    }

    // MARK: - 左: 工程

    private var rail: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                Text("PROJECT").railHead()
                ForEach(Array(AtelierModel.steps.enumerated()), id: \.offset) {
                    i, s in
                    HStack(spacing: 8) {
                        Text(String(format: "%02d", i + 1))
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(AT.faint)
                        Text(s).font(.system(size: 12))
                        Spacer(minLength: 0)
                    }
                    .padding(.horizontal, 14).padding(.vertical, 5)
                    .background(m.step == s ? AT.panel2 : .clear)
                    .overlay(alignment: .leading) {
                        Rectangle().fill(m.step == s ? AT.sel : .clear)
                            .frame(width: 2)
                    }
                    .foregroundStyle(m.step == s ? AT.fg : AT.dim)
                    .contentShape(Rectangle())
                    .onTapGesture {
                        m.step = s
                        if s == "Tech Pack" { Task { await m.loadTechPack() } }
                    }
                }
                Text("GARMENTS").railHead().padding(.top, 10)
                HStack(spacing: 8) {
                    Text("001").font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(AT.faint)
                    Text(m.projectName).font(.system(size: 12))
                }
                .padding(.horizontal, 14).padding(.vertical, 5)
                .background(AT.panel2)

                // 解析に使う AI。ここが LLM のパイプの行き先で、
                // 選んだ相手が台帳に触れる口は提案だけ。
                Text("ANALYSIS AI").railHead().padding(.top, 10)
                VStack(alignment: .leading, spacing: 3) {
                    Text(an.pick.label).font(.system(size: 11))
                        .foregroundStyle(AT.fg).lineLimit(2)
                    Text(app.t("writes proposals only",
                               "書けるのは提案だけ"))
                        .font(.system(size: 9)).foregroundStyle(AT.faint)
                }
                .padding(.horizontal, 14).padding(.vertical, 6)
                .frame(maxWidth: .infinity, alignment: .leading)
                .contentShape(Rectangle())
                .onTapGesture { showAnalyst = true }
            }
            .padding(.vertical, 10)
        }
        .background(AT.panel)
    }

    // MARK: - 中央: 服そのもの

    private var workspace: some View {
        VStack(spacing: 0) {
            HStack(spacing: 6) {
                ForEach(["Film", "Search", "3D"], id: \.self) { t in
                    Text(t).font(.system(size: 11))
                        .padding(.horizontal, 12).padding(.vertical, 4)
                        .background(Capsule().stroke(
                            m.tab == t ? AT.sel : AT.line, lineWidth: 1))
                        .foregroundStyle(m.tab == t ? AT.fg : AT.dim)
                        .onTapGesture { m.tab = t }
                }
                Spacer()
                if m.tab == "3D" {
                    // 無いものを「準備中」と言わない。まだ観測が要る段だと言う。
                    Text(app.t("no 3D yet — evidence first",
                               "3Dはまだ。先に証拠を集める段です"))
                        .font(.system(size: 10)).foregroundStyle(AT.faint)
                }
            }
            .padding(.horizontal, 14).padding(.top, 10)

            Spacer(minLength: 0)
            if m.anime { animeTriptych } else { figure(scale: 1.0) }
            Spacer(minLength: 0)

            HStack(spacing: 8) {
                ForEach(["Front", "Side", "Back"], id: \.self) { v in
                    Text(v).font(.system(size: 11))
                        .padding(.horizontal, 10).padding(.vertical, 2)
                        .background(RoundedRectangle(cornerRadius: 4)
                            .fill(m.view == v ? AT.panel2 : .clear))
                        .foregroundStyle(m.view == v ? AT.fg : AT.faint)
                        .onTapGesture { m.view = v }
                }
            }
            HStack(spacing: 8) {
                ForEach(m.nonSpatial, id: \.self) { mat in
                    let st = m.partState(mat)
                    Text("\(AT.symbol(st)) \(mat)")
                        .font(.system(size: 11))
                        .padding(.horizontal, 11).padding(.vertical, 2)
                        .background(Capsule().stroke(
                            m.selected == mat ? AT.sel : AT.line, lineWidth: 1))
                        .foregroundStyle(AT.color(st))
                        .onTapGesture { m.selected = mat }
                }
                Text(app.t("these have no place on the body",
                           "これらは場所を持たないので図に載せない"))
                    .font(.system(size: 10)).foregroundStyle(AT.faint)
            }
            .padding(.top, 6)
            Text(app.t("green confirmed · red contested · amber inferred · grey unobserved",
                       "緑=確定 / 赤=割れている / 橙=推論 / 灰=未観測。"
                       + "クリックで右の構造インスペクタが変わります"))
                .font(.system(size: 10)).foregroundStyle(AT.faint)
                .padding(.vertical, 10)
        }
    }

    private func figure(scale: CGFloat) -> some View {
        GarmentFigure(view: m.view, selected: m.selected,
                      stateOf: { m.partState($0) },
                      onPick: { m.selected = $0 })
            .frame(width: 300 * scale, height: 360 * scale)
    }

    /// アニメ: 原画 → 解釈 → 実現。**中央だけが Vera の持ち物**で、
    /// 左右はまだ無い/外にあるものだと分かるように薄くする。
    private var animeTriptych: some View {
        HStack(spacing: 18) {
            VStack(spacing: 4) {
                Text("Original artwork").font(.system(size: 10))
                    .foregroundStyle(AT.faint)
                figure(scale: 0.52).opacity(0.35)
                Text(app.t("設定画 / screenshot", "設定画・スクリーンショット"))
                    .font(.system(size: 9)).foregroundStyle(AT.faint)
            }
            VStack(spacing: 4) {
                Text("Interpretation").font(.system(size: 10))
                    .foregroundStyle(AT.dim)
                figure(scale: 0.85)
                Text(app.t("what Vera holds", "Veraが持っている構造"))
                    .font(.system(size: 9)).foregroundStyle(AT.faint)
            }
            VStack(spacing: 4) {
                Text("Realization").font(.system(size: 10))
                    .foregroundStyle(AT.faint)
                figure(scale: 0.52).opacity(0.22)
                Text(app.t("not generated", "実際に作れる服(未生成)"))
                    .font(.system(size: 9)).foregroundStyle(AT.faint)
            }
        }
    }

    // MARK: - 右: 構造インスペクタ

    /// 右の柱。**記録するところは畳まない** — 側面が増えると
    /// 一番使う口が折り返しの下に隠れて、押せなくなる(実地で踏んだ)。
    /// 読むもの(側面)だけを巻き取り、書く口は下に固定する。
    private var inspector: some View {
        VStack(spacing: 0) {
            inspectorScroll
            Divider().opacity(0.25)
            RecordForm(m: m)
        }
        .background(AT.panel)
    }

    private var inspectorScroll: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                VStack(alignment: .leading, spacing: 1) {
                    Text(m.selected.uppercased())
                        .font(.system(size: 14, weight: .semibold))
                    Text(app.t("\(m.aspects(of: m.selected).count) aspects · "
                               + "the weakest aspect sets the part",
                               "\(m.aspects(of: m.selected).count) 側面 ・ "
                               + "状態は最も弱い側面に合わせる"))
                        .font(.system(size: 11)).foregroundStyle(AT.dim)
                }
                .padding(.horizontal, 13).padding(.top, 11).padding(.bottom, 8)
                Divider().opacity(0.25)

                ForEach(m.aspects(of: m.selected), id: \.self) { aspect in
                    AspectRow(m: m, part: m.selected, aspect: aspect)
                    Divider().opacity(0.2)
                }
            }
        }
        .frame(maxHeight: .infinity)
    }

    // MARK: - 下: 証拠の時系列と配分

    private var bottom: some View {
        HStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    if m.timeline.isEmpty {
                        Text(app.t("No evidence yet.",
                                   "証拠がまだありません。右から記録してください。"))
                            .font(.system(size: 11)).foregroundStyle(AT.faint)
                            .padding(12)
                    }
                    ForEach(Array(m.timeline.enumerated()), id: \.offset) { _, r in
                        HStack(spacing: 10) {
                            Text(r.at.isEmpty ? "—" : r.at)
                                .font(.system(size: 11, design: .monospaced))
                                .foregroundStyle(AT.sel).frame(width: 62,
                                                               alignment: .leading)
                            Text("\(r.part) / \(r.aspect)")
                                .font(.system(size: 11, design: .monospaced))
                                .foregroundStyle(AT.dim)
                                .frame(width: 150, alignment: .leading)
                            Text(r.value).font(.system(size: 12))
                            Text(r.kind).font(.system(size: 9))
                                .foregroundStyle(AT.kindColor(r.kind))
                            Spacer()
                            Text(r.source).font(.system(size: 10))
                                .foregroundStyle(AT.faint)
                        }
                        .padding(.horizontal, 12).padding(.vertical, 3)
                        .contentShape(Rectangle())
                        .onTapGesture { m.selected = r.part }
                        Divider().opacity(0.12)
                    }
                }
            }
            Divider().opacity(0.25)
            VStack(alignment: .leading, spacing: 7) {
                bar("OBSERVED", m.counts["confirmed"] ?? 0, AT.ok)
                bar("CONTESTED", m.counts["contested"] ?? 0, AT.bad)
                bar("INFERRED", m.counts["inferred"] ?? 0, AT.warn)
                // 提案は open の内訳。別の帯にするのは、提案が
                // 何かを閉じたように見えないようにするため。
                bar("UNKNOWN", m.counts["unobserved"] ?? m.counts["open"] ?? 0,
                    AT.line)
                bar("PROPOSED", m.counts["proposed"] ?? 0, AT.sel)
                Text(app.t("confidence here is how many independent readings "
                           + "agreed — never a model's own score. UNKNOWN is "
                           + "not a failure; it is what to look for next.",
                           "確度はモデルの点数ではなく、独立した観測が何本"
                           + "一致したかです。UNKNOWN は失敗ではなく、次に"
                           + "探すもの。"))
                    .font(.system(size: 10)).foregroundStyle(AT.faint)
                Spacer(minLength: 0)
            }
            .padding(12).frame(width: 300)
        }
        .background(AT.panel)
    }

    private func bar(_ name: String, _ n: Int, _ c: Color) -> some View {
        let total = max(1, m.counts.values.reduce(0, +))
        return VStack(alignment: .leading, spacing: 3) {
            HStack {
                Text(name).font(.system(size: 11)).foregroundStyle(AT.dim)
                Spacer()
                Text("\(n)").font(.system(size: 11)).foregroundStyle(AT.dim)
            }
            GeometryReader { g in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 3).fill(AT.panel2)
                    RoundedRectangle(cornerRadius: 3).fill(c)
                        .frame(width: g.size.width * CGFloat(n)
                               / CGFloat(total))
                }
            }
            .frame(height: 6)
        }
    }
}

// MARK: - 側面ひとつ

private struct AspectRow: View {
    @EnvironmentObject var app: AppState
    @ObservedObject var m: AtelierModel
    let part: String
    let aspect: String

    var body: some View {
        let s = m.state(part, aspect)
        VStack(alignment: .leading, spacing: 3) {
            HStack(spacing: 6) {
                Text(aspect).font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(AT.dim)
                Text("\(AT.symbol(s.state)) \(AT.short(s.state))")
                    .font(.system(size: 10))
                    .padding(.horizontal, 7).padding(.vertical, 1)
                    .background(Capsule().stroke(AT.color(s.state),
                                                 lineWidth: 1))
                    .foregroundStyle(AT.color(s.state))
                Spacer()
            }
            switch s.state {
            case "OBSERVED":
                Text(s.value).font(.system(size: 13, weight: .semibold))
                Text(app.t("\(s.agreed) independent readings agree",
                           "\(s.agreed) 件の独立した観測が一致")
                     + (s.adoptedBy.isEmpty ? ""
                        : app.t(" · adopted by \(s.adoptedBy)",
                                " ・ 採用: \(s.adoptedBy)")))
                    .font(.system(size: 11)).foregroundStyle(AT.dim)
                Text(s.sources.joined(separator: " · "))
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(AT.faint)
            case "CONTESTED":
                ForEach(Array(s.sides.enumerated()), id: \.offset) { _, side in
                    HStack(spacing: 6) {
                        Text(side.value).font(.system(size: 13, weight: .semibold))
                        Text("← " + side.sources.joined(separator: " · "))
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(AT.faint)
                    }
                }
                Text(app.t("readings disagree — neither side wins here; "
                           + "a person decides",
                           "観測が食い違っている。片方を勝たせていない — 人が決める"))
                    .font(.system(size: 11)).foregroundStyle(AT.dim)
            case "INFERRED":
                Text(s.value).font(.system(size: 13, weight: .semibold))
                Text(app.t("reasoned from structure (not observed)",
                           "構造から推した(観測ではない)"))
                    .font(.system(size: 11)).foregroundStyle(AT.dim)
                Text(app.t("basis: ", "根拠: ") + s.basis.joined(separator: " · "))
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(AT.faint)
            default:
                Text("—").font(.system(size: 13)).foregroundStyle(AT.dim)
                Text(app.t("no direct observation", "直接の観測が無い"))
                    .font(.system(size: 11)).foregroundStyle(AT.dim)
                // UNKNOWN はエラーではなく次の探索対象。だから閉じ方を出す。
                VStack(alignment: .leading, spacing: 2) {
                    Text(app.t("what would close it", "次に何をすれば閉じるか"))
                        .font(.system(size: 11)).foregroundStyle(AT.warn)
                    ForEach(s.howToClose.components(separatedBy: " / "),
                            id: \.self) { line in
                        Text("• " + line).font(.system(size: 11))
                            .foregroundStyle(AT.dim)
                    }
                }
                .padding(7)
                .background(RoundedRectangle(cornerRadius: 5)
                    .stroke(AT.line, style: StrokeStyle(lineWidth: 1,
                                                        dash: [3, 3])))
            }
            ForEach(Array(s.proposals.enumerated()), id: \.offset) { _, p in
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Text(app.t("proposal", "提案")).font(.system(size: 10))
                            .foregroundStyle(AT.faint)
                        Text(p.value).font(.system(size: 12, weight: .semibold))
                    }
                    Text(p.source + (p.note.isEmpty ? ""
                        : " · \(p.note)" + app.t(" (the source's own claim, not a fact)",
                                                 "(出所の申告であって事実ではない)")))
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(AT.faint)
                    Button(app.t("Accept as evidence", "証拠として採用")) {
                        m.pendingAdopt = .init(part: part, aspect: aspect,
                                               value: p.value)
                    }
                    .font(.system(size: 10))
                }
                .padding(7)
                .background(RoundedRectangle(cornerRadius: 5)
                    .stroke(AT.line, style: StrokeStyle(lineWidth: 1,
                                                        dash: [3, 3])))
            }
        }
        .padding(.horizontal, 13).padding(.vertical, 9)
        .frame(maxWidth: .infinity, alignment: .leading)
        .sheet(item: $m.pendingAdopt) { req in AdoptSheet(m: m, req: req) }
    }
}

// MARK: - 記録フォーム

private struct RecordForm: View {
    @EnvironmentObject var app: AppState
    @ObservedObject var m: AtelierModel
    @State private var value = ""
    @State private var source = ""
    @State private var note = ""
    @State private var aspect = ""
    @State private var kind = "observation"

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(app.t("Record", "記録する")).font(.system(size: 10))
                .foregroundStyle(AT.faint)
            HStack(spacing: 5) {
                Picker("", selection: $aspect) {
                    ForEach(m.aspects(of: m.selected), id: \.self) {
                        Text($0).tag($0)
                    }
                }.labelsHidden().frame(width: 120)
                Picker("", selection: $kind) {
                    Text(app.t("observed", "観測")).tag("observation")
                    Text(app.t("inferred", "推論")).tag("inference")
                    Text(app.t("proposed", "提案")).tag("proposal")
                }.labelsHidden().frame(width: 100)
            }
            TextField(app.t("value", "値"), text: $value)
                .textFieldStyle(.roundedBorder).font(.system(size: 11))
            TextField(app.t("source (cut 0:12:05 / URL)", "出典 (cut 0:12:05 / URL)"),
                      text: $source)
                .textFieldStyle(.roundedBorder).font(.system(size: 11))
            TextField(app.t("note (a model's score goes here)",
                            "注記(モデルの点数はここ)"), text: $note)
                .textFieldStyle(.roundedBorder).font(.system(size: 11))
            Button(app.t("Place", "置く")) {
                Task {
                    await m.add(part: m.selected,
                                aspect: aspect.isEmpty
                                    ? (m.aspects(of: m.selected).first ?? "")
                                    : aspect,
                                kind: kind, value: value, source: source,
                                note: note)
                    value = ""; source = ""; note = ""
                }
            }
            .font(.system(size: 11))
            .disabled(value.trimmingCharacters(in: .whitespaces).isEmpty)
        }
        .padding(13)
        .onAppear { if aspect.isEmpty {
            aspect = m.aspects(of: m.selected).first ?? "" } }
        .onChange(of: m.selected) { _ in
            aspect = m.aspects(of: m.selected).first ?? "" }
    }
}

// MARK: - 採用(名前が要る)

private struct AdoptSheet: View {
    @EnvironmentObject var app: AppState
    @ObservedObject var m: AtelierModel
    let req: AtelierModel.AdoptRequest
    @State private var by = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(app.t("Accept as evidence", "証拠として採用する"))
                .font(.system(size: 13, weight: .semibold))
            Text("\(req.part) / \(req.aspect) — \(req.value)")
                .font(.system(size: 12)).foregroundStyle(AT.dim)
            // 採用者の名前が残らない採用は受け付けない。裁った後に
            // 「誰が通したか」を辿れないと、間違いの責任が消える。
            Text(app.t("Adoption is a human act and the name is stored.",
                       "採用は人の行為です。名前が台帳に残ります。"))
                .font(.system(size: 11)).foregroundStyle(AT.faint)
            TextField(app.t("your name", "採用する人の名前"), text: $by)
                .textFieldStyle(.roundedBorder)
            HStack {
                Button(app.t("Cancel", "やめる")) { m.pendingAdopt = nil }
                Spacer()
                Button(app.t("Accept", "採用")) {
                    Task { await m.adopt(req, by: by) }
                }
                .disabled(by.trimmingCharacters(in: .whitespaces).isEmpty)
            }
        }
        .padding(18).frame(width: 380)
    }
}

// MARK: - Tech Pack

private struct TechPackSheet: View {
    @EnvironmentObject var app: AppState
    @ObservedObject var m: AtelierModel

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text("GARMENT TECH PACK")
                    .font(.system(size: 14, weight: .semibold))
                Spacer()
                Button(app.t("Close", "閉じる")) { m.showTechPack = false }
            }
            .padding(.bottom, 6)
            Text(m.techPackNote).font(.system(size: 10))
                .foregroundStyle(AT.faint)
            Divider().padding(.vertical, 8)
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    ForEach(Array(m.techPack.enumerated()), id: \.offset) {
                        _, sec in
                        VStack(alignment: .leading, spacing: 4) {
                            Text("\(sec.no)  \(sec.name)")
                                .font(.system(size: 12, weight: .semibold))
                                .foregroundStyle(AT.dim)
                            Divider().opacity(0.3)
                            if sec.rows.isEmpty {
                                Text(app.t("none", "なし"))
                                    .font(.system(size: 11))
                                    .foregroundStyle(AT.faint)
                            }
                            ForEach(Array(sec.rows.enumerated()),
                                    id: \.offset) { _, r in
                                HStack(alignment: .top, spacing: 10) {
                                    Text(r.label)
                                        .font(.system(size: 11,
                                                      design: .monospaced))
                                        .foregroundStyle(AT.dim)
                                        .frame(width: 210, alignment: .leading)
                                    Text(r.value).font(.system(size: 12))
                                    Spacer()
                                    if !r.state.isEmpty {
                                        Text(AT.symbol(r.state))
                                            .foregroundStyle(AT.color(r.state))
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        .padding(20).frame(width: 720, height: 560)
    }
}

// MARK: - 服の図(Swift で描く)

private struct GarmentFigure: View {
    let view: String
    let selected: String
    let stateOf: (String) -> String
    let onPick: (String) -> Void

    /// 図に載せるのは**空間的な部位だけ**。fabric と lining は場所を
    /// 持たないので載せない — 存在しない場所を指させると、読み手は
    /// 「そこを見た」と誤解する。
    private var parts: [(String, [CGPoint], CGPoint)] {
        switch view {
        case "Back":
            return [("back", bodyShell, CGPoint(x: 150, y: 180)),
                    ("collar", backCollar, CGPoint(x: 150, y: 46)),
                    ("sleeve", leftSleeve, CGPoint(x: 70, y: 160)),
                    ("sleeve", rightSleeve, CGPoint(x: 230, y: 160))]
        case "Side":
            return [("body", sideBody, CGPoint(x: 156, y: 180)),
                    ("collar", sideCollar, CGPoint(x: 150, y: 44)),
                    ("sleeve", sideSleeve, CGPoint(x: 96, y: 160)),
                    ("pocket", sidePocket, CGPoint(x: 152, y: 236))]
        default:
            return [("body", bodyShell, CGPoint(x: 150, y: 180)),
                    ("collar", leftLapel, CGPoint(x: 150, y: 44)),
                    ("collar", rightLapel, CGPoint(x: 0, y: 0)),
                    ("sleeve", leftSleeve, CGPoint(x: 70, y: 160)),
                    ("sleeve", rightSleeve, CGPoint(x: 230, y: 160)),
                    ("pocket", pockets, CGPoint(x: 150, y: 236))]
        }
    }

    var body: some View {
        GeometryReader { g in
            let s = min(g.size.width / 300, g.size.height / 320)
            ZStack {
                ForEach(Array(parts.enumerated()), id: \.offset) { _, p in
                    let (name, pts, label) = p
                    let st = stateOf(name)
                    Path { path in
                        guard let first = pts.first else { return }
                        path.move(to: CGPoint(x: first.x * s, y: first.y * s))
                        for pt in pts.dropFirst() {
                            path.addLine(to: CGPoint(x: pt.x * s, y: pt.y * s))
                        }
                        path.closeSubpath()
                    }
                    .fill(AT.fill(st))
                    .overlay(
                        Path { path in
                            guard let first = pts.first else { return }
                            path.move(to: CGPoint(x: first.x * s,
                                                  y: first.y * s))
                            for pt in pts.dropFirst() {
                                path.addLine(to: CGPoint(x: pt.x * s,
                                                         y: pt.y * s))
                            }
                            path.closeSubpath()
                        }
                        .stroke(selected == name ? AT.sel : AT.color(st),
                                lineWidth: selected == name ? 2.2 : 1.4)
                    )
                    .contentShape(Rectangle())
                    .onTapGesture { onPick(name) }
                    if label != .zero {
                        Text("\(name) \(AT.symbol(st))")
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(AT.dim)
                            .position(x: label.x * s, y: label.y * s)
                            .allowsHitTesting(false)
                    }
                }
            }
        }
    }

    // 座標は 300x320 の設計空間。SVG 版と同じ形。
    private var bodyShell: [CGPoint] {
        [.init(x: 104, y: 74), .init(x: 92, y: 262), .init(x: 208, y: 262),
         .init(x: 196, y: 74)]
    }
    private var sideBody: [CGPoint] {
        [.init(x: 126, y: 74), .init(x: 116, y: 262), .init(x: 196, y: 262),
         .init(x: 188, y: 74)]
    }
    private var leftLapel: [CGPoint] {
        [.init(x: 126, y: 52), .init(x: 150, y: 86), .init(x: 118, y: 110),
         .init(x: 106, y: 74)]
    }
    private var rightLapel: [CGPoint] {
        [.init(x: 174, y: 52), .init(x: 150, y: 86), .init(x: 182, y: 110),
         .init(x: 194, y: 74)]
    }
    private var backCollar: [CGPoint] {
        [.init(x: 120, y: 54), .init(x: 180, y: 54), .init(x: 188, y: 80),
         .init(x: 112, y: 80)]
    }
    private var sideCollar: [CGPoint] {
        [.init(x: 134, y: 52), .init(x: 172, y: 66), .init(x: 160, y: 100),
         .init(x: 128, y: 80)]
    }
    private var leftSleeve: [CGPoint] {
        [.init(x: 104, y: 74), .init(x: 78, y: 84), .init(x: 60, y: 224),
         .init(x: 94, y: 236), .init(x: 100, y: 150)]
    }
    private var rightSleeve: [CGPoint] {
        [.init(x: 196, y: 74), .init(x: 222, y: 84), .init(x: 240, y: 224),
         .init(x: 206, y: 236), .init(x: 200, y: 150)]
    }
    private var sideSleeve: [CGPoint] {
        [.init(x: 126, y: 74), .init(x: 100, y: 86), .init(x: 86, y: 224),
         .init(x: 120, y: 236), .init(x: 126, y: 150)]
    }
    private var pockets: [CGPoint] {
        [.init(x: 110, y: 196), .init(x: 144, y: 196), .init(x: 144, y: 222),
         .init(x: 110, y: 222)]
    }
    private var sidePocket: [CGPoint] {
        [.init(x: 132, y: 196), .init(x: 172, y: 196), .init(x: 172, y: 222),
         .init(x: 132, y: 222)]
    }
}

// MARK: - 色と記号

enum AT {
    static let bg = Color(red: 0.063, green: 0.063, blue: 0.086)
    static let panel = Color(red: 0.086, green: 0.086, blue: 0.122)
    static let panel2 = Color(red: 0.106, green: 0.106, blue: 0.149)
    static let line = Color(red: 0.157, green: 0.157, blue: 0.212)
    static let fg = Color(red: 0.914, green: 0.914, blue: 0.949)
    static let dim = Color(red: 0.541, green: 0.541, blue: 0.616)
    static let faint = Color(red: 0.357, green: 0.357, blue: 0.431)
    static let ok = Color(red: 0.349, green: 0.753, blue: 0.541)
    static let warn = Color(red: 0.851, green: 0.635, blue: 0.290)
    static let bad = Color(red: 0.878, green: 0.392, blue: 0.373)
    static let sel = Color(red: 0.357, green: 0.561, blue: 0.839)

    static func color(_ state: String) -> Color {
        switch state {
        case "OBSERVED": return ok
        case "CONTESTED": return bad
        case "INFERRED": return warn
        default: return dim
        }
    }

    static func fill(_ state: String) -> Color {
        color(state).opacity(state == "UNKNOWN_NOT_OBSERVED" ? 0.06 : 0.18)
    }

    static func symbol(_ state: String) -> String {
        switch state {
        case "OBSERVED": return "✓"
        case "CONTESTED": return "×"
        case "INFERRED": return "△"
        case "PROPOSED": return "·"
        default: return "?"
        }
    }

    static func short(_ state: String) -> String {
        state.replacingOccurrences(of: "_NOT_OBSERVED", with: "")
    }

    static func kindColor(_ kind: String) -> Color {
        switch kind {
        case "observation": return ok
        case "inference": return warn
        default: return dim
        }
    }
}

private extension Text {
    func railHead() -> some View {
        self.font(.system(size: 10)).tracking(1.2)
            .foregroundStyle(AT.faint)
            .padding(.horizontal, 14).padding(.bottom, 5)
    }
}

// MARK: - 解析に使う AI を選ぶ

/// LLM のパイプの行き先。ローカルもクラウドも同じ一覧に並び、
/// **どれを選んでも台帳に書ける口は提案だけ**という一行を、
/// 選択肢の上に置いてあります。UIの注意書きではなく、扉の側で
/// 閉じている事実の説明です。
private struct AnalystSheet: View {
    @ObservedObject var an: AtelierAnalyst
    @ObservedObject var m: AtelierModel
    @EnvironmentObject var app: AppState
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text(app.t("Analysis AI", "解析に使う AI"))
                    .font(.system(size: 13, weight: .semibold))
                if an.busy { ProgressView().controlSize(.small) }
                Spacer()
                Button(app.t("Refresh", "一覧を取り直す")) {
                    Task { await an.refresh(app: app) }
                }.font(.system(size: 11))
                Button(app.t("Close", "閉じる")) { dismiss() }
                    .font(.system(size: 11))
            }
            .padding(14)
            .background(AT.panel)

            Text(app.t("Whatever you pick can only write PROPOSED entries. "
                       + "A proposal becomes fact only when a person adopts "
                       + "it under their name.",
                       "どれを選んでも、書けるのは提案の欄だけです。"
                       + "提案が事実になるのは、人が名前を書いて採用した"
                       + "ときだけです。"))
                .font(.system(size: 10)).foregroundStyle(AT.warn)
                .padding(.horizontal, 14).padding(.vertical, 8)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(AT.warn.opacity(0.10))

            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    group(app.t("Structure only", "構造のみ")) {
                        row(.vera, app.t("no model is called",
                                         "モデルを呼びません"))
                    }
                    group("Ollama") {
                        if an.ollamaModels.isEmpty {
                            empty(app.t("Ollama is not serving anything",
                                        "Ollama が何も出していません"))
                        } else {
                            ForEach(an.ollamaModels, id: \.self) { name in
                                row(.ollama(name), app.t("on this machine",
                                                         "この機体の中"))
                            }
                        }
                    }
                    group("JGEN") {
                        if an.jgenModels.isEmpty {
                            empty(app.t("no converted JGEN can run forward",
                                        "前向きに走らせられる変換済み JGEN が"
                                        + "ありません"))
                        } else {
                            ForEach(an.jgenModels, id: \.self) { name in
                                row(.jgen(name), app.t("on this machine",
                                                       "この機体の中"))
                            }
                        }
                    }
                    group(app.t("Cloud", "クラウド")) {
                        if an.cloudModels.isEmpty {
                            empty(app.t("no provider has a key",
                                        "鍵の入っているプロバイダがありません"))
                        } else {
                            ForEach(Array(an.cloudModels.keys.sorted {
                                $0.rawValue < $1.rawValue
                            }), id: \.self) { p in
                                ForEach(an.cloudModels[p] ?? [], id: \.self) {
                                    name in
                                    row(.cloud(p, name), p.rawValue)
                                }
                            }
                        }
                    }
                }
                .padding(.vertical, 8)
            }

            Divider().opacity(0.3)
            HStack(spacing: 10) {
                Button(app.t("Ask about the open aspects",
                             "空いている側面を訊く")) {
                    Task { await an.analyze(model: m, app: app) }
                }
                .font(.system(size: 11))
                .disabled(an.busy)
                if !an.lastRun.isEmpty {
                    Text(an.lastRun).font(.system(size: 10))
                        .foregroundStyle(an.lastProposals > 0 ? AT.warn : AT.dim)
                        .lineLimit(2)
                }
                Spacer(minLength: 0)
            }
            .padding(14)
            .background(AT.panel)
        }
        .frame(width: 560, height: 520)
        .background(AT.bg)
    }

    private func group<T: View>(_ title: String,
                                @ViewBuilder _ body: () -> T) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(title.uppercased())
                .font(.system(size: 9, weight: .semibold, design: .monospaced))
                .foregroundStyle(AT.faint)
                .padding(.horizontal, 14).padding(.top, 10).padding(.bottom, 4)
            body()
        }
    }

    private func empty(_ s: String) -> some View {
        Text(s).font(.system(size: 11)).foregroundStyle(AT.faint)
            .padding(.horizontal, 14).padding(.vertical, 5)
    }

    private func row(_ p: AtelierAnalyst.Pick, _ sub: String) -> some View {
        let on = an.pick == p
        return HStack(spacing: 8) {
            Text(on ? "●" : "○").font(.system(size: 10))
                .foregroundStyle(on ? AT.sel : AT.faint)
            VStack(alignment: .leading, spacing: 1) {
                Text(p.label).font(.system(size: 12))
                    .foregroundStyle(on ? AT.fg : AT.dim)
                Text(sub).font(.system(size: 9)).foregroundStyle(AT.faint)
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 14).padding(.vertical, 5)
        .background(on ? AT.panel2 : .clear)
        .contentShape(Rectangle())
        .onTapGesture { an.pick = p }
    }
}
