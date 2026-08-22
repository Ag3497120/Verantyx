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
    @StateObject private var intake = AtelierIntake()
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

    /// 中央。工程によって何を見せるかが変わる。由来と再設計を figure と
    /// 同じ面に重ねないのは、**見た事**と**どこから来たか**と**作る事**が
    /// 別の台帳だからで、一枚に混ぜると設計を触った瞬間に観測が
    /// 書き換わったように見える。
    @ViewBuilder
    private var workspace: some View {
        switch m.step {
        case "Sources":    SourcesPanel(m: m, an: an, intake: intake)
                               .environmentObject(app)
        case "Provenance": ProvenancePanel(m: m).environmentObject(app)
        case "Re-design":  DesignPanel(m: m).environmentObject(app)
        case "Pattern":    MeasurePanel(m: m).environmentObject(app)
        default:           figureWorkspace
        }
    }

    private var figureWorkspace: some View {
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
                // 裁つ前に**どれを確かめ直せるか**。確定の本数だけでは、
                // 誰も開けない出典と、開ける出典が同じ顔になる。
                HStack(spacing: 4) {
                    Text(app.t("of which re-openable",
                               "うち見に行けるもの"))
                        .font(.system(size: 9)).foregroundStyle(AT.faint)
                    Spacer(minLength: 0)
                    Text("\(m.counts["verifiable"] ?? 0)")
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(AT.faint)
                }
                .padding(.horizontal, 14).padding(.bottom, 4)
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
                // 裁つ前に**どれを確かめ直せるか**。付いていないことは
                // 見ていないことではないので、そう書く。
                HStack(spacing: 5) {
                    Text(s.verifiable ? "◉" : "○").font(.system(size: 9))
                        .foregroundStyle(s.verifiable ? AT.ok : AT.faint)
                    Text(s.verifiable
                         ? app.t("can be re-opened", "見に行ける")
                         : (s.unverifiableReason.isEmpty
                            ? app.t("no pointer attached", "参照なし")
                            : s.unverifiableReason))
                        .font(.system(size: 9))
                        .foregroundStyle(s.verifiable ? AT.ok : AT.faint)
                }
                ForEach(Array(s.refs.enumerated()), id: \.offset) { _, r in
                    if !r.path.isEmpty || !r.url.isEmpty {
                        Text("↳ "
                             + (r.path.isEmpty ? r.url
                                : (r.path as NSString).lastPathComponent)
                             + (r.mark.isEmpty ? "" : " @ \(r.mark)"))
                            .font(.system(size: 9, design: .monospaced))
                            .foregroundStyle(
                                r.status == "VERIFIABLE" ? AT.dim : AT.warn)
                    }
                }
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
    @State private var refPath = ""
    @State private var refMark = ""

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
            // 参照は観測にだけ付ける。推論を「見に行く」ことはできない。
            if kind == "observation" {
                HStack(spacing: 6) {
                    Button(refPath.isEmpty
                           ? app.t("attach file…", "参照ファイル…")
                           : (refPath as NSString).lastPathComponent) {
                        pickFile()
                    }
                    .font(.system(size: 10)).lineLimit(1)
                    TextField(app.t("mark (0:12:05 / f182 / p.12)",
                                    "位置 (0:12:05 / f182 / p.12)"),
                              text: $refMark)
                        .textFieldStyle(.roundedBorder)
                        .font(.system(size: 10))
                    if !refPath.isEmpty {
                        Button("×") { refPath = "" }.font(.system(size: 10))
                    }
                }
                Text(app.t("Attaching one lets anyone re-open it later. "
                           + "The same frame read twice still counts once.",
                           "付けると後から誰でも同じものを開けます。"
                           + "同じコマを二度読んでも1件のままです。"))
                    .font(.system(size: 9)).foregroundStyle(AT.faint)
            }
            Button(app.t("Place", "置く")) {
                Task {
                    await m.add(part: m.selected,
                                aspect: aspect.isEmpty
                                    ? (m.aspects(of: m.selected).first ?? "")
                                    : aspect,
                                kind: kind, value: value, source: source,
                                note: note, refPath: refPath,
                                refMark: refMark)
                    value = ""; source = ""; note = ""
                    refMark = ""
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

    /// 参照するファイルを選ぶ。**コピーしない** — 元の場所を指すだけで、
    /// 台帳が素材を抱え込むと、後から本物と写しの区別がつかなくなる。
    private func pickFile() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = false
        panel.message = AppLanguage.shared.t(
            "Pick the film, photo or document this observation came from",
            "この観測の元になった映像・写真・資料を選ぶ")
        if panel.runModal() == .OK, let url = panel.url {
            refPath = url.path
        }
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
    @State private var lmHost = ""

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
                    group("LM Studio") {
                        // **別の機体を指せる。** 手元のRAMで載らないものを
                        // 隣の機体に載せて、結果だけ台帳に入れる — 出所は
                        // どちらで走らせても同じように残る。
                        HStack(spacing: 6) {
                            TextField("http://127.0.0.1:1234/v1",
                                      text: $lmHost)
                                .textFieldStyle(.roundedBorder)
                                .font(.system(size: 10, design: .monospaced))
                            Button(app.t("Point here", "ここに向ける")) {
                                let v = lmHost.trimmingCharacters(
                                    in: .whitespaces)
                                guard !v.isEmpty else { return }
                                app.lmStudioEndpoint = v
                                Task { await an.refresh(app: app) }
                            }.font(.system(size: 10))
                        }
                        .padding(.horizontal, 14).padding(.bottom, 4)
                        if an.lmStudioModels.isEmpty {
                            empty(app.t("LM Studio's server is not answering "
                                        + "at \(an.lmStudioEndpoint)",
                                        "LM Studio のサーバーが答えません "
                                        + "(\(an.lmStudioEndpoint))"))
                        } else {
                            ForEach(an.lmStudioModels, id: \.self) { name in
                                row(.lmStudio(name), an.lmStudioEndpoint)
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
        .frame(width: 560, height: 560)
        .background(AT.bg)
        .onAppear { if lmHost.isEmpty { lmHost = app.lmStudioEndpoint } }
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

// MARK: - 由来

/// 由来の面。**この面に「作ってよい」は出ない。**
///
/// 出せるのは、何を見たか・何を見ていないか・どこから来たか まで。
/// 一番効いているのは一般/実例の線引きで、「ノッチドラペル」のような
/// 何千着に共通する構造と、一つの作品に辿れる組み合わせを分けて数える。
private struct ProvenancePanel: View {
    @ObservedObject var m: AtelierModel
    @EnvironmentObject var app: AppState
    @State private var claim = "specific"
    @State private var text = ""
    @State private var note = ""
    @State private var aspect = ""
    @State private var said = ""

    private static let intents = [
        ("personal", "自分用"), ("cosplay", "コスプレ"),
        ("study", "学習・研究"), ("costume", "衣装制作"),
        ("commercial", "商用利用")]

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Divider().opacity(0.25)
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    worklist
                    Divider().opacity(0.2)
                    rows
                }
            }
            Divider().opacity(0.25)
            recorder
        }
        .background(AT.bg)
        .task { await m.loadRights() }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack(spacing: 10) {
                Text(app.t("Provenance", "由来")).font(
                    .system(size: 13, weight: .semibold))
                Spacer()
                Button(app.t("May I make this?", "作ってよいか訊く")) {
                    Task { await m.askLegal() }
                }.font(.system(size: 11))
            }
            HStack(spacing: 6) {
                Text(app.t("use", "用途")).font(.system(size: 10))
                    .foregroundStyle(AT.faint)
                ForEach(Self.intents, id: \.0) { key, label in
                    Text(label).font(.system(size: 11))
                        .padding(.horizontal, 9).padding(.vertical, 2)
                        .background(Capsule().stroke(
                            m.intent == key ? AT.sel : AT.line, lineWidth: 1))
                        .foregroundStyle(m.intent == key ? AT.fg : AT.dim)
                        .onTapGesture { Task { await m.setIntent(key) } }
                }
            }
            // 用途を切り替えても由来は変わらない。ここを書いておかないと
            // 「自分用にすれば消える」と読まれる。
            Text(app.t("Choosing a use is not a permit: no origin changes, "
                       + "only the homework list does.",
                       "用途は許可証ではありません。どの由来も変わらず、"
                       + "変わるのは宿題の一覧だけです。"))
                .font(.system(size: 10)).foregroundStyle(AT.faint)
            if !m.legalAnswer.isEmpty {
                Text(m.legalAnswer).font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(AT.warn).textSelection(.enabled)
                    .padding(8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(RoundedRectangle(cornerRadius: 5)
                        .fill(AT.warn.opacity(0.10)))
            }
        }
        .padding(14)
        .background(AT.panel)
    }

    private var worklist: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text(app.t("HOMEWORK", "宿題")).railHead()
                Spacer()
                Text("\(m.rightsWorklist.count)")
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(AT.faint).padding(.trailing, 14)
            }
            if m.rightsWorklist.isEmpty {
                Text(app.t("nothing flagged — which is not the same as clear",
                           "挙がっているものはありません（問題が無いという"
                           + "意味ではありません）"))
                    .font(.system(size: 11)).foregroundStyle(AT.faint)
                    .padding(.horizontal, 14).padding(.bottom, 8)
            }
            ForEach(Array(m.rightsWorklist.enumerated()), id: \.offset) { _, r in
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 8) {
                        Text("\(r.part) / \(r.aspect)")
                            .font(.system(size: 11, design: .monospaced))
                        stateChip(r.state)
                        Spacer(minLength: 0)
                    }
                    Text(r.why).font(.system(size: 10))
                        .foregroundStyle(AT.dim)
                }
                .padding(.horizontal, 14).padding(.vertical, 5)
                .contentShape(Rectangle())
                .onTapGesture { m.selected = r.part; aspect = r.aspect }
            }
        }
        .padding(.top, 8)
    }

    private var rows: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(app.t("EVERY ASPECT", "全側面")).railHead().padding(.top, 10)
            ForEach(m.rights.keys.sorted(), id: \.self) { key in
                let r = m.rights[key]!
                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 8) {
                        Text(key).font(.system(size: 11, design: .monospaced))
                            .foregroundStyle(AT.dim)
                        stateChip(r.state)
                        Spacer(minLength: 0)
                    }
                    if !r.specificSources.isEmpty {
                        line("実例", r.specificSources, AT.bad)
                    }
                    if !r.genericSources.isEmpty {
                        line("一般", r.genericSources, AT.ok)
                    }
                    if !r.searchedScopes.isEmpty {
                        line("探した範囲", r.searchedScopes, AT.dim)
                    }
                    if !r.declaredBy.isEmpty {
                        line("名乗り", r.declaredBy, AT.sel)
                    }
                    if !r.howToClose.isEmpty {
                        Text("→ " + r.howToClose).font(.system(size: 10))
                            .foregroundStyle(AT.warn)
                    }
                }
                .padding(.horizontal, 14).padding(.vertical, 6)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(m.selected == r.part ? AT.panel2 : .clear)
                .contentShape(Rectangle())
                .onTapGesture { m.selected = r.part; aspect = r.aspect }
                Divider().opacity(0.12)
            }
        }
    }

    private func line(_ label: String, _ items: [String],
                      _ colour: Color) -> some View {
        HStack(alignment: .top, spacing: 6) {
            Text(label).font(.system(size: 9)).foregroundStyle(AT.faint)
                .frame(width: 56, alignment: .leading)
            Text(items.joined(separator: " / "))
                .font(.system(size: 10, design: .monospaced))
                .foregroundStyle(colour)
        }
    }

    private var recorder: some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack(spacing: 6) {
                Text(app.t("record for", "記録する"))
                    .font(.system(size: 10)).foregroundStyle(AT.faint)
                Text(m.selected).font(.system(size: 11, weight: .semibold))
                Picker("", selection: $aspect) {
                    ForEach(m.aspects(of: m.selected), id: \.self) {
                        Text($0).tag($0)
                    }
                }.labelsHidden().frame(width: 130)
                Picker("", selection: $claim) {
                    Text(app.t("traceable to one work", "実例（作品に辿れる）"))
                        .tag("specific")
                    Text(app.t("common construction", "一般構造")).tag("generic")
                    Text(app.t("searched, no match", "探したが無かった"))
                        .tag("no_match")
                    Text(app.t("declared mine", "自分の設計だと名乗る"))
                        .tag("declared")
                }.labelsHidden().frame(width: 200)
                Spacer(minLength: 0)
            }
            TextField(fieldHint, text: $text)
                .textFieldStyle(.roundedBorder).font(.system(size: 11))
            HStack(spacing: 8) {
                TextField(app.t("note", "注記"), text: $note)
                    .textFieldStyle(.roundedBorder).font(.system(size: 11))
                Button(app.t("Place", "置く")) {
                    Task {
                        let a = aspect.isEmpty
                            ? (m.aspects(of: m.selected).first ?? "") : aspect
                        said = await m.addRights(
                            part: m.selected, aspect: a, claim: claim,
                            text: text, note: note)
                        if said == "ANSWER" { text = ""; note = "" }
                    }
                }
                .font(.system(size: 11))
                .disabled(text.trimmingCharacters(in: .whitespaces).isEmpty)
            }
            if !said.isEmpty && said != "ANSWER" {
                Text(said).font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(AT.bad)
            }
            // 一般は2本要る、という規律を押す前に出しておく。
            Text(app.t("A construction counts as common only with two "
                       + "independent named sources.",
                       "「一般構造」は、名前の付いた独立した出典が2本"
                       + "揃って初めて成立します。"))
                .font(.system(size: 9)).foregroundStyle(AT.faint)
        }
        .padding(13)
        .background(AT.panel)
        .onAppear { if aspect.isEmpty {
            aspect = m.aspects(of: m.selected).first ?? "" } }
        .onChange(of: m.selected) { _ in
            aspect = m.aspects(of: m.selected).first ?? "" }
    }

    private var fieldHint: String {
        switch claim {
        case "no_match": return app.t("what you searched (the scope)",
                                      "探した範囲（これが本体）")
        case "declared": return app.t("who is declaring", "名乗る人の名前")
        default: return app.t("source (work, page, URL)",
                              "出典（作品名・資料・URL）")
        }
    }

    private func stateChip(_ state: String) -> some View {
        Text(RIGHTS.short(state)).font(.system(size: 9, weight: .semibold))
            .padding(.horizontal, 6).padding(.vertical, 1)
            .background(Capsule().stroke(RIGHTS.colour(state), lineWidth: 1))
            .foregroundStyle(RIGHTS.colour(state))
    }
}

enum RIGHTS {
    static func colour(_ s: String) -> Color {
        switch s {
        case "SPECIFIC_TO_SOURCE": return AT.bad
        case "CONTESTED_ORIGIN": return AT.bad
        case "GENERIC_CONSTRUCTION": return AT.ok
        case "DECLARED_BY": return AT.sel
        case "UNKNOWN_NO_MATCH_IN": return AT.warn
        default: return AT.dim
        }
    }

    /// **「オリジナル」に相当する短縮形は無い。** 探した範囲の中に
    /// 無かったことは、無いことではない。
    static func short(_ s: String) -> String {
        switch s {
        case "SPECIFIC_TO_SOURCE": return "実例"
        case "CONTESTED_ORIGIN": return "割れている"
        case "GENERIC_CONSTRUCTION": return "一般"
        case "DECLARED_BY": return "名乗りのみ"
        case "UNKNOWN_NO_MATCH_IN": return "範囲内に無し"
        default: return "未調査"
        }
    }
}

// MARK: - 再設計

/// 作る面。**観測台帳を書き換える手段をこの面は持たない。**
///
/// kept はそのまま、changed は観測から変えた、new は観測に由来しない。
/// 値を変えた後も派生元は消えない — 「Xから変えた」ことが由来である。
private struct DesignPanel: View {
    @ObservedObject var m: AtelierModel
    @EnvironmentObject var app: AppState
    @State private var action = "change"
    @State private var value = ""
    @State private var by = ""
    @State private var note = ""
    @State private var aspect = ""
    @State private var said = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            VStack(alignment: .leading, spacing: 5) {
                Text(app.t("Re-design", "再設計"))
                    .font(.system(size: 13, weight: .semibold))
                Text(app.t("The source stays as observed. What you build is "
                           + "a separate ledger, and each row says where it "
                           + "came from.",
                           "原作品は観測されたまま動きません。作る側は別の"
                           + "台帳で、各行にどこから来たかが付きます。"))
                    .font(.system(size: 10)).foregroundStyle(AT.faint)
                HStack(spacing: 12) {
                    counter("そのまま", m.designCounts["kept"] ?? 0, AT.dim)
                    counter("変えた", m.designCounts["changed"] ?? 0, AT.warn)
                    counter("新しく決めた", m.designCounts["new"] ?? 0, AT.ok)
                }
            }
            .padding(14)
            .background(AT.panel)
            Divider().opacity(0.25)

            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    if m.designRows.isEmpty {
                        Text(app.t("Nothing designed yet.",
                                   "まだ何も設計していません。"))
                            .font(.system(size: 11))
                            .foregroundStyle(AT.faint).padding(14)
                    }
                    ForEach(Array(m.designRows.enumerated()),
                            id: \.offset) { _, r in
                        VStack(alignment: .leading, spacing: 2) {
                            HStack(spacing: 8) {
                                Text("\(r.part) / \(r.aspect)")
                                    .font(.system(size: 11,
                                                  design: .monospaced))
                                    .foregroundStyle(AT.dim)
                                Text(kindLabel(r.kind))
                                    .font(.system(size: 9, weight: .semibold))
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 1)
                                    .background(Capsule()
                                        .stroke(kindColour(r.kind),
                                                lineWidth: 1))
                                    .foregroundStyle(kindColour(r.kind))
                                Spacer(minLength: 0)
                                Text(r.by).font(.system(size: 9))
                                    .foregroundStyle(AT.faint)
                            }
                            Text(r.value)
                                .font(.system(size: 12, weight: .semibold))
                            if !r.originalValue.isEmpty {
                                // 変えた事実が由来。消さない。
                                Text("← \(r.originalValue)  (\(r.derivedFrom))")
                                    .font(.system(size: 10,
                                                  design: .monospaced))
                                    .foregroundStyle(AT.faint)
                            } else if !r.derivedFrom.isEmpty {
                                Text("← \(r.derivedFrom)")
                                    .font(.system(size: 10,
                                                  design: .monospaced))
                                    .foregroundStyle(AT.faint)
                            }
                        }
                        .padding(.horizontal, 14).padding(.vertical, 6)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        Divider().opacity(0.12)
                    }
                }
            }

            Divider().opacity(0.25)
            VStack(alignment: .leading, spacing: 5) {
                HStack(spacing: 6) {
                    Text(m.selected).font(.system(size: 11, weight: .semibold))
                    Picker("", selection: $aspect) {
                        ForEach(m.aspects(of: m.selected), id: \.self) {
                            Text($0).tag($0)
                        }
                    }.labelsHidden().frame(width: 130)
                    Picker("", selection: $action) {
                        Text(app.t("keep as observed", "観測のまま"))
                            .tag("keep")
                        Text(app.t("change it", "変える")).tag("change")
                        Text(app.t("new, not derived", "新しく決める"))
                            .tag("new")
                    }.labelsHidden().frame(width: 150)
                    Spacer(minLength: 0)
                }
                if action != "keep" {
                    TextField(app.t("new value", "新しい値"), text: $value)
                        .textFieldStyle(.roundedBorder)
                        .font(.system(size: 11))
                }
                HStack(spacing: 8) {
                    TextField(app.t("who decides (kept in the ledger)",
                                    "決めた人の名前（台帳に残ります）"),
                              text: $by)
                        .textFieldStyle(.roundedBorder)
                        .font(.system(size: 11))
                    Button(app.t("Place", "置く")) {
                        Task {
                            let a = aspect.isEmpty
                                ? (m.aspects(of: m.selected).first ?? "")
                                : aspect
                            said = await m.design(action, part: m.selected,
                                                  aspect: a, value: value,
                                                  by: by, note: note)
                            if said == "ANSWER" { value = ""; note = "" }
                        }
                    }
                    .font(.system(size: 11))
                    .disabled(by.trimmingCharacters(in: .whitespaces).isEmpty
                              || (action != "keep"
                                  && value.trimmingCharacters(
                                      in: .whitespaces).isEmpty))
                }
                if !said.isEmpty && said != "ANSWER" {
                    Text(said).font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(AT.bad)
                }
                Text(app.t("Only confirmed observations can be kept or "
                           + "changed — an uncertain value must not be cut.",
                           "そのまま／変える は確定した観測にしか使えません。"
                           + "定まっていない値を裁つことになるためです。"))
                    .font(.system(size: 9)).foregroundStyle(AT.faint)
            }
            .padding(13)
            .background(AT.panel)
        }
        .background(AT.bg)
        .task { await m.loadDesign() }
        .onAppear { if aspect.isEmpty {
            aspect = m.aspects(of: m.selected).first ?? "" } }
        .onChange(of: m.selected) { _ in
            aspect = m.aspects(of: m.selected).first ?? "" }
    }

    private func counter(_ label: String, _ n: Int,
                         _ colour: Color) -> some View {
        HStack(spacing: 5) {
            Text("\(n)").font(.system(size: 13, weight: .semibold,
                                      design: .monospaced))
                .foregroundStyle(colour)
            Text(label).font(.system(size: 10)).foregroundStyle(AT.dim)
        }
    }

    private func kindLabel(_ k: String) -> String {
        switch k {
        case "kept": return "そのまま"
        case "changed": return "変えた"
        default: return "新規"
        }
    }

    private func kindColour(_ k: String) -> Color {
        switch k {
        case "kept": return AT.dim
        case "changed": return AT.warn
        default: return AT.ok
        }
    }
}

// MARK: - 素材を入れる

/// 入れる → 割る → 読ませる → 照らす。
///
/// 四つを別の操作にしてあるのは、それぞれ性質が違うからです。割るのは
/// 計算、読むのはモデル(出力は提案)、照らすのは距離(判断ではない)、
/// 記録するのは Vera(どの扉から来たかで決まる)。ひとつのボタンに
/// まとめると、どこで推測が入ったのかが後から見えなくなります。
private struct SourcesPanel: View {
    @ObservedObject var m: AtelierModel
    @ObservedObject var an: AtelierAnalyst
    @ObservedObject var intake: AtelierIntake
    @EnvironmentObject var app: AppState
    @State private var simPart = "collar"
    @State private var simAspect = "shape"

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Divider().opacity(0.25)
            HSplit
            Divider().opacity(0.25)
            logStrip
        }
        .background(AT.bg)
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack(spacing: 10) {
                Text(app.t("Sources", "素材")).font(
                    .system(size: 13, weight: .semibold))
                if intake.busy {
                    ProgressView().controlSize(.small)
                    Text(intake.stage).font(.system(size: 10))
                        .foregroundStyle(AT.dim)
                }
                Spacer()
                Text(app.t("frames", "コマ数")).font(.system(size: 10))
                    .foregroundStyle(AT.faint)
                Stepper(value: $intake.frameCount, in: 1...60) {
                    Text("\(intake.frameCount)")
                        .font(.system(size: 11, design: .monospaced))
                }.labelsHidden().frame(width: 60)
                Button(app.t("Add film or photo…", "映像・写真を入れる…")) {
                    Task { await intake.pickAndIngest() }
                }
                .font(.system(size: 11)).disabled(intake.busy)
            }
            Text(app.t("Splitting is arithmetic. Reading is a model, and "
                       + "whatever it reads becomes a proposal. Matching is "
                       + "a distance, not a verdict.",
                       "割るのは計算です。読むのはモデルで、何を読んでも"
                       + "提案にしかなりません。照らすのは距離であって"
                       + "判断ではありません。"))
                .font(.system(size: 10)).foregroundStyle(AT.faint)
        }
        .padding(14)
        .background(AT.panel)
    }

    @ViewBuilder
    private var HSplit: some View {
        HStack(spacing: 0) {
            clipList.frame(width: 210)
            Divider().opacity(0.2)
            detail.frame(maxWidth: .infinity)
        }
    }

    private var clipList: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                if intake.clips.isEmpty {
                    Text(app.t("No material yet.", "まだ素材がありません。"))
                        .font(.system(size: 11)).foregroundStyle(AT.faint)
                        .padding(14)
                }
                ForEach(intake.clips) { c in
                    HStack(spacing: 8) {
                        thumb(c.path, side: 34)
                        VStack(alignment: .leading, spacing: 1) {
                            Text(c.mark)
                                .font(.system(size: 10, design: .monospaced))
                            Text(String(format: "%.2f s", c.seconds))
                                .font(.system(size: 9))
                                .foregroundStyle(AT.faint)
                        }
                        Spacer(minLength: 0)
                    }
                    .padding(.horizontal, 10).padding(.vertical, 4)
                    .background(intake.selectedClip?.path == c.path
                                ? AT.panel2 : .clear)
                    .contentShape(Rectangle())
                    .onTapGesture { intake.selectedClip = c }
                }
            }
            .padding(.vertical, 6)
        }
        .background(AT.panel)
    }

    @ViewBuilder
    private var detail: some View {
        if let c = intake.selectedClip {
            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    thumb(c.path, side: 260)
                        .frame(maxWidth: .infinity, alignment: .center)
                    HStack(spacing: 8) {
                        Button(app.t("Read this frame", "このコマを読ませる")) {
                            Task { await intake.read(clip: c, model: an.pick,
                                                     into: m) }
                        }.font(.system(size: 11)).disabled(intake.busy)
                        Text(an.pick.label).font(.system(size: 10))
                            .foregroundStyle(AT.dim).lineLimit(1)
                        Spacer(minLength: 0)
                    }
                    Button(app.t("Find similar frames", "似ているコマを照らす")) {
                        Task { await intake.findSimilar(to: c,
                                                        among: intake.clips) }
                    }.font(.system(size: 11)).disabled(intake.busy)

                    if !intake.matches.isEmpty {
                        Text(app.t("CLOSEST FIRST — a distance, not a verdict",
                                   "距離順 — 判断ではありません")).railHead()
                        HStack(spacing: 6) {
                            Picker("", selection: $simPart) {
                                ForEach(m.parts.keys.sorted(), id: \.self) {
                                    Text($0).tag($0)
                                }
                            }.labelsHidden().frame(width: 110)
                            Picker("", selection: $simAspect) {
                                ForEach(m.aspects(of: simPart), id: \.self) {
                                    Text($0).tag($0)
                                }
                            }.labelsHidden().frame(width: 130)
                            Spacer(minLength: 0)
                        }
                        ForEach(intake.matches) { mt in
                            HStack(spacing: 8) {
                                thumb(mt.path, side: 44)
                                VStack(alignment: .leading, spacing: 1) {
                                    Text(mt.mark)
                                        .font(.system(size: 10,
                                                      design: .monospaced))
                                    Text(String(format: "距離 %.3f",
                                                mt.distance))
                                        .font(.system(size: 9))
                                        .foregroundStyle(AT.faint)
                                }
                                Spacer(minLength: 0)
                                Button(app.t("propose", "提案として置く")) {
                                    Task {
                                        await intake.proposeSimilarity(
                                            mt, part: simPart,
                                            aspect: simAspect, into: m)
                                    }
                                }.font(.system(size: 10))
                            }
                            .padding(.vertical, 3)
                        }
                    }
                }
                .padding(14)
            }
        } else {
            VStack {
                Spacer()
                Text(app.t("Pick a frame on the left.",
                           "左でコマを選んでください。"))
                    .font(.system(size: 11)).foregroundStyle(AT.faint)
                Spacer()
            }
            .frame(maxWidth: .infinity)
        }
    }

    private var logStrip: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 1) {
                ForEach(Array(intake.log.enumerated().reversed()),
                        id: \.offset) { _, line in
                    Text(line).font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(AT.dim)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            .padding(.horizontal, 14).padding(.vertical, 6)
        }
        .frame(height: 84)
        .background(AT.panel)
    }

    private func thumb(_ path: String, side: CGFloat) -> some View {
        Group {
            if let img = NSImage(contentsOfFile: path) {
                Image(nsImage: img).resizable().scaledToFit()
            } else {
                RoundedRectangle(cornerRadius: 3).fill(AT.panel2)
            }
        }
        .frame(maxWidth: side, maxHeight: side)
    }
}

// MARK: - 寸法

/// 寸法の面。**映像から採寸はできない。**
///
/// 一枚の絵に長さの基準が映っていなければ袖丈は出ない。「肘下12cm相当」は
/// 比率の読みであって観測ではなく、基準が実測で入るまで長さにならない。
/// 計算された長さは `derived` に立ち、実測と同じ欄には入らない — 比率から
/// 出した数字が実寸の顔で型紙に乗るのが、この段で一番起きやすい事故。
private struct MeasurePanel: View {
    @ObservedObject var m: AtelierModel
    @EnvironmentObject var app: AppState
    @State private var spot = "body_length"
    @State private var kind = "measured"
    @State private var value = ""
    @State private var unit = "cm"
    @State private var basis = "body_length"
    @State private var source = ""
    @State private var by = ""
    @State private var said = ""

    private var spots: [String] {
        m.measureRows.map(\.spot)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            VStack(alignment: .leading, spacing: 6) {
                Text(app.t("Measurements", "寸法"))
                    .font(.system(size: 13, weight: .semibold))
                Text(app.t("A frame cannot be measured. Without a length of "
                           + "known size in the shot, a ratio stays a ratio.",
                           "映像から採寸はできません。長さの基準が映って"
                           + "いなければ、比率は比率のままです。"))
                    .font(.system(size: 10)).foregroundStyle(AT.faint)
                HStack(spacing: 12) {
                    counter(app.t("measured", "実測"),
                            m.measureCounts["measured"] ?? 0, AT.ok)
                    counter(app.t("derived", "計算値"),
                            m.measureCounts["derived"] ?? 0, AT.warn)
                    counter(app.t("not taken", "未取得"),
                            m.measureCounts["open"] ?? 0, AT.dim)
                }
            }
            .padding(14).background(AT.panel)
            Divider().opacity(0.25)

            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(Array(m.measureRows.enumerated()),
                            id: \.offset) { _, r in
                        VStack(alignment: .leading, spacing: 2) {
                            HStack(spacing: 8) {
                                Text(r.name).font(.system(size: 12))
                                Text(r.spot)
                                    .font(.system(size: 9,
                                                  design: .monospaced))
                                    .foregroundStyle(AT.faint)
                                Spacer(minLength: 0)
                                stateChip(r.state)
                            }
                            if let v = r.value {
                                Text("\(v, specifier: "%.1f") \(r.unit)")
                                    .font(.system(size: 14, weight: .semibold))
                                    .foregroundStyle(r.state == "DERIVED"
                                                     ? AT.warn : AT.fg)
                            }
                            if !r.from.isEmpty {
                                // 計算値は、どこから出たかを必ず伴う。
                                Text("← \(r.from)")
                                    .font(.system(size: 10,
                                                  design: .monospaced))
                                    .foregroundStyle(AT.faint)
                            }
                            if !r.source.isEmpty {
                                Text(r.source).font(.system(size: 9))
                                    .foregroundStyle(AT.faint)
                            }
                            if !r.howToClose.isEmpty {
                                Text("→ " + r.howToClose)
                                    .font(.system(size: 10))
                                    .foregroundStyle(AT.warn)
                            }
                        }
                        .padding(.horizontal, 14).padding(.vertical, 6)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        Divider().opacity(0.12)
                    }
                }
            }

            Divider().opacity(0.25)
            recorder
        }
        .background(AT.bg)
        .task { await m.loadMeasures() }
    }

    private var recorder: some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack(spacing: 6) {
                Picker("", selection: $spot) {
                    ForEach(spots, id: \.self) { Text($0).tag($0) }
                }.labelsHidden().frame(width: 150)
                Picker("", selection: $kind) {
                    Text(app.t("measured", "実測")).tag("measured")
                    Text(app.t("ratio", "比率")).tag("ratio")
                }.labelsHidden().frame(width: 90)
                TextField(kind == "measured"
                          ? app.t("length", "長さ")
                          : app.t("×", "倍率"), text: $value)
                    .textFieldStyle(.roundedBorder).font(.system(size: 11))
                    .frame(width: 80)
                if kind == "measured" {
                    Picker("", selection: $unit) {
                        ForEach(["cm", "mm", "inch"], id: \.self) {
                            Text($0).tag($0)
                        }
                    }.labelsHidden().frame(width: 70)
                } else {
                    Picker("", selection: $basis) {
                        ForEach(["body_length", "chest", "shoulder"],
                                id: \.self) { Text($0).tag($0) }
                    }.labelsHidden().frame(width: 120)
                }
                Spacer(minLength: 0)
            }
            HStack(spacing: 8) {
                TextField(app.t("source", "出典"), text: $source)
                    .textFieldStyle(.roundedBorder).font(.system(size: 11))
                if kind == "measured" {
                    TextField(app.t("who measured", "測った人"), text: $by)
                        .textFieldStyle(.roundedBorder)
                        .font(.system(size: 11)).frame(width: 130)
                }
                Button(app.t("Place", "置く")) {
                    Task {
                        guard let v = Double(value) else {
                            said = "UNKNOWN_NOT_A_NUMBER"; return
                        }
                        said = kind == "measured"
                            ? await m.addMeasure(spot: spot, value: v,
                                                 unit: unit, source: source,
                                                 by: by)
                            : await m.addRatio(spot: spot, value: v,
                                               basis: basis, source: source)
                        if said == "ANSWER" { value = "" }
                    }
                }
                .font(.system(size: 11))
                .disabled(value.trimmingCharacters(in: .whitespaces).isEmpty)
            }
            if !said.isEmpty && said != "ANSWER" {
                Text(said).font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(AT.bad)
            }
            Text(app.t("A ratio is not a length until its basis is measured.",
                       "比率は、基準が実測で入るまで長さになりません。"))
                .font(.system(size: 9)).foregroundStyle(AT.faint)
        }
        .padding(13).background(AT.panel)
    }

    private func counter(_ label: String, _ n: Int,
                         _ colour: Color) -> some View {
        HStack(spacing: 5) {
            Text("\(n)").font(.system(size: 13, weight: .semibold,
                                      design: .monospaced))
                .foregroundStyle(colour)
            Text(label).font(.system(size: 10)).foregroundStyle(AT.dim)
        }
    }

    private func stateChip(_ state: String) -> some View {
        let (label, colour): (String, Color) = {
            switch state {
            case "MEASURED": return ("実測", AT.ok)
            case "DERIVED": return ("計算値", AT.warn)
            case "UNKNOWN_NO_BASIS": return ("基準待ち", AT.warn)
            default: return ("未取得", AT.dim)
            }
        }()
        return Text(label).font(.system(size: 9, weight: .semibold))
            .padding(.horizontal, 6).padding(.vertical, 1)
            .background(Capsule().stroke(colour, lineWidth: 1))
            .foregroundStyle(colour)
    }
}
