import SceneKit
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
    /// 証拠帯を開いているか。**面をまたいで覚える** — 面を変えるたびに
    /// 開き直されると、畳んだ意味がありません。
    @AppStorage("atelier_evidence_open") private var evidenceOpen = false

    @EnvironmentObject var app: AppState
    @StateObject private var m = AtelierModel()
    // `.shared`, not a fresh instance — the composer's own "Analysis AI"
    // chip (UnifiedComposerView) reads and opens the SAME object, so a
    // pick made from either place is the pick the other one sees. See the
    // comment on `AtelierAnalyst.shared`.
    @StateObject private var an = AtelierAnalyst.shared
    @StateObject private var intake = AtelierIntake.shared
    @State private var showAnalyst = false
    // UI B: the chat pane beside this view (`AtelierChatPaneView`) has no
    // reference to `m` — it asks through here instead. See
    // `AtelierNavigator`'s doc comment for why this is the write side of
    // the same mirror `AtelierContext` already is for `projectName`.
    @StateObject private var nav = AtelierNavigator.shared

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
            // **証拠帯は畳める。** どの面でも 168pt を占めていて、
            // 型紙も生地台帳も下が切れていました。畳んでも「ある」ことは
            // 見出しに残します — 消すのではなく、しまう。
            HStack(spacing: 6) {
                Button {
                    withAnimation(.easeInOut(duration: 0.15)) {
                        evidenceOpen.toggle()
                    }
                } label: {
                    HStack(spacing: 5) {
                        Text(evidenceOpen ? "▾" : "▸")
                            .font(.system(size: 9))
                        Text(app.t("EVIDENCE", "証拠"))
                            .font(.system(size: 10, weight: .semibold))
                        Text("\(m.timeline.count)")
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(Theme.faint)
                    }
                }
                .buttonStyle(.plain)
                .foregroundStyle(Theme.dim)
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 12).padding(.vertical, 3)
            .background(Theme.panel)
            if evidenceOpen {
                Divider().opacity(0.25)
                bottom.frame(height: 168)
            }
        }
        .background(Theme.bg)
        .task {
            await m.load()
            await intake.restore()
            await an.refresh(app: app)
        }
        .sheet(isPresented: $m.showTechPack) { TechPackSheet(m: m) }
        .sheet(isPresented: $showAnalyst) {
            AnalystSheet(an: an, m: m).environmentObject(app)
        }
        // UI B の誘導。**人が工程をクリックすれば、それが常に勝つ** —
        // このハンドラは chat が新しく解決したときだけ発火し(token が
        // 上がる)、クリックの直後に古い要求が追いかけて上書くことはない。
        // 次に chat が送られたときは、その新しい行き先が今度は人の直前の
        // クリックより後に来た指示として勝つ — 「最後の行為が勝つ」の
        // 一本の規則で、クリックと chat のどちらが偉いという特別扱いはない。
        .onChange(of: nav.request) { _, req in
            guard let req else { return }
            m.step = req.step
            if req.step == "Tech Pack" { Task { await m.loadTechPack() } }
        }
    }

    // MARK: - engine が答えなかったとき

    /// 台帳が空なのではなく、**engine に届かなかった**。この二つを同じ
    /// 見え方にすると、動いているエンジンを前にして壊れて見える。
    private func engineBanner(_ err: String) -> some View {
        HStack(spacing: 10) {
            Text("UNKNOWN_ENGINE_UNREACHABLE")
                .font(.system(size: 10, weight: .semibold, design: .monospaced))
                .foregroundStyle(Theme.bad)
            Text(app.t("The ledger below is not empty — it is unread.",
                       "下の台帳は空ではなく、読めていません。"))
                .font(.system(size: 10)).foregroundStyle(Theme.dim)
            Text(err).font(.system(size: 9, design: .monospaced))
                .foregroundStyle(Theme.faint).lineLimit(1)
            Spacer(minLength: 0)
            Button(app.t("Reconnect", "接続し直す")) {
                Task { await m.reconnect() }
            }.font(.system(size: 10))
        }
        .padding(.horizontal, 14).padding(.vertical, 6)
        .background(Theme.bad.opacity(0.12))
    }

    // MARK: - 上帯

    private var header: some View {
        HStack(spacing: 12) {
            Text("Vera Atelier").font(.system(size: 13, weight: .semibold))
            Text("Project: \(m.projectName)")
                .font(.system(size: 11)).foregroundStyle(Theme.dim)
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
        .background(Theme.panel)
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
                            .foregroundStyle(Theme.faint)
                        Text(s).font(.system(size: 12))
                        Spacer(minLength: 0)
                    }
                    .padding(.horizontal, 14).padding(.vertical, 5)
                    .background(m.step == s ? Theme.panel2 : .clear)
                    .overlay(alignment: .leading) {
                        Rectangle().fill(m.step == s ? Theme.sel : .clear)
                            .frame(width: 2)
                    }
                    .foregroundStyle(m.step == s ? Theme.fg : Theme.dim)
                    .contentShape(Rectangle())
                    .onTapGesture {
                        m.step = s
                        if s == "Tech Pack" { Task { await m.loadTechPack() } }
                    }
                }
                Text("GARMENTS").railHead().padding(.top, 10)
                HStack(spacing: 8) {
                    Text("001").font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(Theme.faint)
                    Text(m.projectName).font(.system(size: 12))
                }
                .padding(.horizontal, 14).padding(.vertical, 5)
                .background(Theme.panel2)

                // 解析に使う AI。ここが LLM のパイプの行き先で、
                // 選んだ相手が台帳に触れる口は提案だけ。
                Text("ANALYSIS AI").railHead().padding(.top, 10)
                VStack(alignment: .leading, spacing: 3) {
                    Text(an.pick.label).font(.system(size: 11))
                        .foregroundStyle(Theme.fg).lineLimit(2)
                    Text(app.t("writes proposals only",
                               "書けるのは提案だけ"))
                        .font(.system(size: 9)).foregroundStyle(Theme.faint)
                }
                .padding(.horizontal, 14).padding(.vertical, 6)
                .frame(maxWidth: .infinity, alignment: .leading)
                .contentShape(Rectangle())
                .onTapGesture { showAnalyst = true }
            }
            .padding(.vertical, 10)
        }
        .background(Theme.panel)
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
        case "Garments":   DrawingPanel(m: m).environmentObject(app)
        case "Evidence":   EvidencePanel(m: m).environmentObject(app)
        case "Materials":  MaterialsPanel(m: m).environmentObject(app)
        case "Solid":      SolidPanel(m: m).environmentObject(app)
        default:           figureWorkspace
        }
    }

    private var figureWorkspace: some View {
        VStack(spacing: 0) {
            HStack(spacing: 6) {
                // **押して何も起きないものを置かない。** Search は
                // 実装が 01 Sources にあるので、そこへ連れて行く。
                // 無言のタブは「壊れている」と「まだ無い」の区別が
                // つかず、読み手は前者だと思う。
                ForEach(["Film", "Search", "3D"], id: \.self) { t in
                    Text(t).font(.system(size: 11))
                        .padding(.horizontal, 12).padding(.vertical, 4)
                        .background(Capsule().stroke(
                            m.tab == t ? Theme.sel : Theme.line, lineWidth: 1))
                        .foregroundStyle(m.tab == t ? Theme.fg : Theme.dim)
                        .onTapGesture {
                            if t == "Search" { m.step = "Sources" }
                            else if t == "3D" { m.step = "Solid" }
                            else { m.tab = t }
                        }
                }
                Spacer()
                if m.tab == "3D" {
                    Text(app.t("solid & ease live in 09-ish — press to go",
                               "立体とゆとりは別の面です。押すと移動します"))
                        .font(.system(size: 10)).foregroundStyle(Theme.faint)
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
                            .fill(m.view == v ? Theme.panel2 : .clear))
                        .foregroundStyle(m.view == v ? Theme.fg : Theme.faint)
                        .onTapGesture { m.view = v }
                }
            }
            HStack(spacing: 8) {
                ForEach(m.nonSpatial, id: \.self) { mat in
                    let st = m.partState(mat)
                    Text("\(Theme.symbol(st)) \(mat)")
                        .font(.system(size: 11))
                        .padding(.horizontal, 11).padding(.vertical, 2)
                        .background(Capsule().stroke(
                            m.selected == mat ? Theme.sel : Theme.line, lineWidth: 1))
                        .foregroundStyle(Theme.color(st))
                        .onTapGesture { m.selected = mat }
                }
                Text(app.t("these have no place on the body",
                           "これらは場所を持たないので図に載せない"))
                    .font(.system(size: 10)).foregroundStyle(Theme.faint)
            }
            .padding(.top, 6)
            Text(app.t("green confirmed · red contested · amber inferred · grey unobserved",
                       "緑=確定 / 赤=割れている / 橙=推論 / 灰=未観測。"
                       + "クリックで右の構造インスペクタが変わります"))
                .font(.system(size: 10)).foregroundStyle(Theme.faint)
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
    /// 三面。**左は原作、中はVeraの構造、右は作ったもの。**
    ///
    /// ここは以前、三面とも Vera の図を透明度違いで並べ、左に
    /// 「Original artwork / 設定画」と書いていた。**Veraの構造を
    /// 原作の設定画と名乗る**のは、この製品が禁じてきたことそのもの。
    /// 左は取り込んだコマの実物を出し、無ければ無いと言う。右は
    /// 作図した設計図で、それも無ければ無いと言う。
    private var animeTriptych: some View {
        HStack(alignment: .top, spacing: 18) {
            VStack(spacing: 4) {
                Text(app.t("Original artwork", "原作"))
                    .font(.system(size: 10)).foregroundStyle(Theme.faint)
                if let clip = intake.selectedClip ?? intake.clips.first,
                   let img = NSImage(contentsOfFile: clip.path) {
                    Image(nsImage: img).resizable().scaledToFit()
                        .frame(maxWidth: 150, maxHeight: 190)
                    Text(clip.mark).font(.system(size: 9,
                                                 design: .monospaced))
                        .foregroundStyle(Theme.faint)
                } else {
                    placeholder(app.t("no material taken in yet",
                                      "まだ素材を入れていません"),
                                app.t("01 Sources", "01 Sources で入れる"))
                }
            }
            .frame(width: 170)

            VStack(spacing: 4) {
                Text(app.t("Interpretation", "Veraが持っている構造"))
                    .font(.system(size: 10)).foregroundStyle(Theme.dim)
                figure(scale: 0.85)
                Text(app.t("observed / split / inferred / unknown",
                           "確定・割れ・推論・未確定"))
                    .font(.system(size: 9)).foregroundStyle(Theme.faint)
            }

            VStack(spacing: 4) {
                Text(app.t("Realization", "作るもの"))
                    .font(.system(size: 10)).foregroundStyle(Theme.faint)
                if m.drawShapes.isEmpty {
                    placeholder(app.t("nothing drawn yet",
                                      "まだ作図していません"),
                                app.t("02 Garments", "02 Garments で描く"))
                } else {
                    FlatFigure(shapes: m.drawShapes, canvas: m.drawCanvas)
                        .frame(width: 130,
                               height: 130 * m.drawCanvas.height
                                   / max(m.drawCanvas.width, 1))
                        .padding(8)
                        .background(RoundedRectangle(cornerRadius: 3)
                            .fill(Color.white))
                    Text(app.t("drafted, not generated", "作図。生成ではない"))
                        .font(.system(size: 9)).foregroundStyle(Theme.faint)
                }
            }
            .frame(width: 170)
        }
        .task { await m.loadDrawing() }
    }

    /// 無いものを、他のもので埋めない。
    private func placeholder(_ what: String, _ where_: String) -> some View {
        VStack(spacing: 4) {
            Text(what).font(.system(size: 10)).foregroundStyle(Theme.faint)
            Text(where_).font(.system(size: 9)).foregroundStyle(Theme.warn)
        }
        .frame(maxWidth: .infinity, minHeight: 150)
        .background(RoundedRectangle(cornerRadius: 4)
            .stroke(Theme.line, style: StrokeStyle(lineWidth: 1, dash: [3, 3])))
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
        .background(Theme.panel)
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
                        .font(.system(size: 11)).foregroundStyle(Theme.dim)
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
                            .font(.system(size: 11)).foregroundStyle(Theme.faint)
                            .padding(12)
                    }
                    ForEach(Array(m.timeline.enumerated()), id: \.offset) { _, r in
                        HStack(spacing: 10) {
                            Text(r.at.isEmpty ? "—" : r.at)
                                .font(.system(size: 11, design: .monospaced))
                                .foregroundStyle(Theme.sel).frame(width: 62,
                                                               alignment: .leading)
                            Text("\(r.part) / \(r.aspect)")
                                .font(.system(size: 11, design: .monospaced))
                                .foregroundStyle(Theme.dim)
                                .frame(width: 150, alignment: .leading)
                            Text(r.value).font(.system(size: 12))
                            Text(r.kind).font(.system(size: 9))
                                .foregroundStyle(Theme.kindColor(r.kind))
                            Spacer()
                            Text(r.source).font(.system(size: 10))
                                .foregroundStyle(Theme.faint)
                        }
                        .padding(.horizontal, 12).padding(.vertical, 3)
                        .contentShape(Rectangle())
                        .onTapGesture { m.selected = r.part }
                        Divider().opacity(0.12)
                    }
                }
            }
            Divider().opacity(0.25)
            ScrollView {
            VStack(alignment: .leading, spacing: 7) {
                bar("OBSERVED", m.counts["confirmed"] ?? 0, Theme.ok)
                // 裁つ前に**どれを確かめ直せるか**。確定の本数だけでは、
                // 誰も開けない出典と、開ける出典が同じ顔になる。
                HStack(spacing: 4) {
                    Text(app.t("of which re-openable",
                               "うち見に行けるもの"))
                        .font(.system(size: 9)).foregroundStyle(Theme.faint)
                    Spacer(minLength: 0)
                    Text("\(m.counts["verifiable"] ?? 0)")
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(Theme.faint)
                }
                .padding(.horizontal, 14).padding(.bottom, 4)
                bar("CONTESTED", m.counts["contested"] ?? 0, Theme.bad)
                bar("INFERRED", m.counts["inferred"] ?? 0, Theme.warn)
                // 提案は open の内訳。別の帯にするのは、提案が
                // 何かを閉じたように見えないようにするため。
                bar("UNKNOWN", m.counts["unobserved"] ?? m.counts["open"] ?? 0,
                    Theme.line)
                bar("PROPOSED", m.counts["proposed"] ?? 0, Theme.sel)
                Text(app.t("confidence here is how many independent readings "
                           + "agreed — never a model's own score. UNKNOWN is "
                           + "not a failure; it is what to look for next.",
                           "確度はモデルの点数ではなく、独立した観測が何本"
                           + "一致したかです。UNKNOWN は失敗ではなく、次に"
                           + "探すもの。"))
                    .font(.system(size: 10)).foregroundStyle(Theme.faint)

                // **「次に探すもの」を実際に並べる。** 数だけ出して
                // 一覧が無いと、UNKNOWN は数え上げで終わってしまう。
                Divider().opacity(0.2).padding(.vertical, 2)
                HStack(spacing: 6) {
                    Text(app.t("BEFORE CUTTING", "裁つ前に潰すこと"))
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(Theme.dim)
                    Spacer(minLength: 0)
                    Text("\(m.worklist.count)")
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(Theme.faint)
                }
                // **空欄を「無い」と読ませない。** 引けていないのか、
                // 本当に片付いているのかは、別のことです。
                if m.worklist.isEmpty {
                    Text(m.counts.isEmpty
                         ? app.t("not read yet", "まだ引けていません")
                         : app.t("nothing open", "開いている項目はありません"))
                        .font(.system(size: 9)).foregroundStyle(Theme.faint)
                }
                if !m.worklist.isEmpty {
                    VStack(alignment: .leading, spacing: 6) {
                        Group {
                            ForEach(m.worklist) { w in
                                VStack(alignment: .leading, spacing: 2) {
                                    HStack(spacing: 5) {
                                        Text("\(w.part) / \(w.aspect)")
                                            .font(.system(size: 10,
                                                design: .monospaced))
                                            .foregroundStyle(Theme.dim)
                                        Spacer(minLength: 0)
                                    }
                                    if !w.howToClose.isEmpty {
                                        Text("→ " + w.howToClose)
                                            .font(.system(size: 9))
                                            .foregroundStyle(Theme.warn)
                                            .fixedSize(
                                                horizontal: false,
                                                vertical: true)
                                    }
                                }
                                .contentShape(Rectangle())
                                .onTapGesture { m.selected = w.part }
                            }
                        }
                    }
                }
                Spacer(minLength: 0)
            }
            .padding(12).frame(width: 300)
            }
            .frame(width: 300)
        }
        .background(Theme.panel)
    }

    private func bar(_ name: String, _ n: Int, _ c: Color) -> some View {
        let total = max(1, m.counts.values.reduce(0, +))
        return VStack(alignment: .leading, spacing: 3) {
            HStack {
                Text(name).font(.system(size: 11)).foregroundStyle(Theme.dim)
                Spacer()
                Text("\(n)").font(.system(size: 11)).foregroundStyle(Theme.dim)
            }
            GeometryReader { g in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 3).fill(Theme.panel2)
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
                    .foregroundStyle(Theme.dim)
                Text("\(Theme.symbol(s.state)) \(Theme.short(s.state))")
                    .font(.system(size: 10))
                    .padding(.horizontal, 7).padding(.vertical, 1)
                    .background(Capsule().stroke(Theme.color(s.state),
                                                 lineWidth: 1))
                    .foregroundStyle(Theme.color(s.state))
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
                    .font(.system(size: 11)).foregroundStyle(Theme.dim)
                Text(s.sources.joined(separator: " · "))
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(Theme.faint)
                // 裁つ前に**どれを確かめ直せるか**。付いていないことは
                // 見ていないことではないので、そう書く。
                HStack(spacing: 5) {
                    Text(s.verifiable ? "◉" : "○").font(.system(size: 9))
                        .foregroundStyle(s.verifiable ? Theme.ok : Theme.faint)
                    Text(s.verifiable
                         ? app.t("can be re-opened", "見に行ける")
                         : (s.unverifiableReason.isEmpty
                            ? app.t("no pointer attached", "参照なし")
                            : s.unverifiableReason))
                        .font(.system(size: 9))
                        .foregroundStyle(s.verifiable ? Theme.ok : Theme.faint)
                }
                ForEach(Array(s.refs.enumerated()), id: \.offset) { _, r in
                    if !r.path.isEmpty || !r.url.isEmpty {
                        Text("↳ "
                             + (r.path.isEmpty ? r.url
                                : (r.path as NSString).lastPathComponent)
                             + (r.mark.isEmpty ? "" : " @ \(r.mark)"))
                            .font(.system(size: 9, design: .monospaced))
                            .foregroundStyle(
                                r.status == "VERIFIABLE" ? Theme.dim : Theme.warn)
                    }
                }
            case "CONTESTED":
                ForEach(Array(s.sides.enumerated()), id: \.offset) { _, side in
                    HStack(spacing: 6) {
                        Text(side.value).font(.system(size: 13, weight: .semibold))
                        Text("← " + side.sources.joined(separator: " · "))
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(Theme.faint)
                    }
                }
                Text(app.t("readings disagree — neither side wins here; "
                           + "a person decides",
                           "観測が食い違っている。片方を勝たせていない — 人が決める"))
                    .font(.system(size: 11)).foregroundStyle(Theme.dim)
            case "INFERRED":
                Text(s.value).font(.system(size: 13, weight: .semibold))
                Text(app.t("reasoned from structure (not observed)",
                           "構造から推した(観測ではない)"))
                    .font(.system(size: 11)).foregroundStyle(Theme.dim)
                Text(app.t("basis: ", "根拠: ") + s.basis.joined(separator: " · "))
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(Theme.faint)
            default:
                Text("—").font(.system(size: 13)).foregroundStyle(Theme.dim)
                Text(app.t("no direct observation", "直接の観測が無い"))
                    .font(.system(size: 11)).foregroundStyle(Theme.dim)
                // UNKNOWN はエラーではなく次の探索対象。だから閉じ方を出す。
                VStack(alignment: .leading, spacing: 2) {
                    Text(app.t("what would close it", "次に何をすれば閉じるか"))
                        .font(.system(size: 11)).foregroundStyle(Theme.warn)
                    ForEach(s.howToClose.components(separatedBy: " / "),
                            id: \.self) { line in
                        Text("• " + line).font(.system(size: 11))
                            .foregroundStyle(Theme.dim)
                    }
                }
                .padding(7)
                .background(RoundedRectangle(cornerRadius: 5)
                    .stroke(Theme.line, style: StrokeStyle(lineWidth: 1,
                                                        dash: [3, 3])))
            }
            ForEach(Array(s.proposals.enumerated()), id: \.offset) { _, p in
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Text(app.t("proposal", "提案")).font(.system(size: 10))
                            .foregroundStyle(Theme.faint)
                        Text(p.value).font(.system(size: 12, weight: .semibold))
                    }
                    Text(p.source + (p.note.isEmpty ? ""
                        : " · \(p.note)" + app.t(" (the source's own claim, not a fact)",
                                                 "(出所の申告であって事実ではない)")))
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(Theme.faint)
                    Button(app.t("Accept as evidence", "証拠として採用")) {
                        m.pendingAdopt = .init(part: part, aspect: aspect,
                                               value: p.value)
                    }
                    .font(.system(size: 10))
                }
                .padding(7)
                .background(RoundedRectangle(cornerRadius: 5)
                    .stroke(Theme.line, style: StrokeStyle(lineWidth: 1,
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
                .foregroundStyle(Theme.faint)
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
                    .font(.system(size: 9)).foregroundStyle(Theme.faint)
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
                .font(.system(size: 12)).foregroundStyle(Theme.dim)
            // 採用者の名前が残らない採用は受け付けない。裁った後に
            // 「誰が通したか」を辿れないと、間違いの責任が消える。
            Text(app.t("Adoption is a human act and the name is stored.",
                       "採用は人の行為です。名前が台帳に残ります。"))
                .font(.system(size: 11)).foregroundStyle(Theme.faint)
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
        // 設定 › 服飾の設定 の「台帳に残す名前」を初期値にする — 毎回
        // 空欄から打ち直さずに済む。すでに何か入っていれば上書きしない。
        .onAppear { if by.isEmpty { by = app.atelierOperatorName } }
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
                Button(app.t("Export…", "書き出す…")) { export() }
                Button(app.t("Close", "閉じる")) { m.showTechPack = false }
            }
            .padding(.bottom, 6)
            Text(m.techPackNote).font(.system(size: 10))
                .foregroundStyle(Theme.faint)
            Divider().padding(.vertical, 8)
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    ForEach(Array(m.techPack.enumerated()), id: \.offset) {
                        _, sec in
                        VStack(alignment: .leading, spacing: 4) {
                            Text("\(sec.no)  \(sec.name)")
                                .font(.system(size: 12, weight: .semibold))
                                .foregroundStyle(Theme.dim)
                            Divider().opacity(0.3)
                            if sec.rows.isEmpty {
                                Text(app.t("none", "なし"))
                                    .font(.system(size: 11))
                                    .foregroundStyle(Theme.faint)
                            }
                            ForEach(Array(sec.rows.enumerated()),
                                    id: \.offset) { _, r in
                                HStack(alignment: .top, spacing: 10) {
                                    Text(r.label)
                                        .font(.system(size: 11,
                                                      design: .monospaced))
                                        .foregroundStyle(Theme.dim)
                                        .frame(width: 210, alignment: .leading)
                                    Text(r.value).font(.system(size: 12))
                                    Spacer()
                                    if !r.state.isEmpty {
                                        Text(Theme.symbol(r.state))
                                            .foregroundStyle(Theme.color(r.state))
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

    /// 縫製師に渡せる形で書き出す。**画面で見えるだけでは渡せない。**
    ///
    /// 出すのは素の文字で、AI の内部構造は出さない。ただし各項目の
    /// 状態(確定 / 割れている / 推論 / 未確定 / 計算値)は必ず残す —
    /// 落とすと、受け取った側は全部を確定として読む。
    private func export() {
        var out = "GARMENT TECH PACK\n"
        out += String(repeating: "=", count: 40) + "\n"
        out += m.techPackNote.isEmpty ? "" : m.techPackNote + "\n"
        out += "\n"
        for sec in m.techPack {
            out += "\n[\(sec.no)] \(sec.name)\n"
            out += String(repeating: "-", count: 40) + "\n"
            if sec.rows.isEmpty { out += "  (なし)\n" }
            for r in sec.rows {
                let mark = TechPackSheet.mark(r.state)
                // ラベルと値を同じ行に置く。分けると、紙に出したとき
                // どの値がどの項目のものか追えない。
                let label = r.label.padding(toLength: max(r.label.count, 28),
                                            withPad: " ", startingAt: 0)
                out += "  \(mark) \(label)\(r.value)\n"
            }
        }
        out += "\n" + String(repeating: "=", count: 40) + "\n"
        out += "確定(✓)以外を裁断の根拠にしないこと。\n"
        out += "計算値(≈)は比率から出した数字で、実測ではない。\n"
        out += "未確定(?)は空欄ではなく、まだ分かっていないという意味。\n"

        let panel = NSSavePanel()
        panel.nameFieldStringValue = "tech-pack.txt"
        panel.message = AppLanguage.shared.t(
            "Save the pack the maker will read",
            "縫製師が読む資料を保存する")
        guard panel.runModal() == .OK, let url = panel.url else { return }
        try? out.write(to: url, atomically: true, encoding: .utf8)
    }

    /// 状態の印。**受け取る側が一目で読める形**にする。
    static func mark(_ state: String) -> String {
        switch state {
        case "OBSERVED", "MEASURED": return "[✓]"
        case "CONTESTED", "CONTESTED_ORIGIN": return "[×]"
        case "INFERRED": return "[△]"
        case "DERIVED": return "[≈]"
        case "": return "   "
        default: return "[?]"
        }
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
                    .fill(Theme.fill(st))
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
                        .stroke(selected == name ? Theme.sel : Theme.color(st),
                                lineWidth: selected == name ? 2.2 : 1.4)
                    )
                    .contentShape(Rectangle())
                    .onTapGesture { onPick(name) }
                    if label != .zero {
                        Text("\(name) \(Theme.symbol(st))")
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(Theme.dim)
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
//
// この配色 (背景・文字・状態色) と OBSERVED/CONTESTED/INFERRED/PROPOSED/
// UNKNOWN_NOT_OBSERVED の色対応は、Theme.swift (Sources/Verantyx/Theme.swift)
// に昇格した — 台帳の状態色は AtelierView だけでなく全画面で同じ意味を
// 持つべきものだったが、以前はこの enum が private 相当で他の 87 画面から
// 参照できなかった (実測 0 件)。ここでの呼び出しは全て Theme.* に直接置き換え済み。

private extension Text {
    func railHead() -> some View {
        self.font(.system(size: 10)).tracking(1.2)
            .foregroundStyle(Theme.faint)
            .padding(.horizontal, 14).padding(.bottom, 5)
    }
}

// MARK: - 解析に使う AI を選ぶ

/// LLM のパイプの行き先。ローカルもクラウドも同じ一覧に並び、
/// **どれを選んでも台帳に書ける口は提案だけ**という一行を、
/// 選択肢の上に置いてあります。UIの注意書きではなく、扉の側で
/// 閉じている事実の説明です。
// Not `private` — the composer (UnifiedComposerView, a different file)
// presents this same sheet for its own "Analysis AI" chip rather than
// forking a second picker that could drift from this one. `m` is optional
// for exactly that call site: the composer has no `AtelierModel` of its
// own (that is AtelierView's per-screen ledger reader, not a singleton),
// so it has nothing to hand the "ask about open aspects" action below —
// picking a model still works without it, running that action does not.
struct AnalystSheet: View {
    @ObservedObject var an: AtelierAnalyst
    var m: AtelierModel? = nil
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
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.panel)

            Text(app.t("Whatever you pick can only write PROPOSED entries. "
                       + "A proposal becomes fact only when a person adopts "
                       + "it under their name.",
                       "どれを選んでも、書けるのは提案の欄だけです。"
                       + "提案が事実になるのは、人が名前を書いて採用した"
                       + "ときだけです。"))
                .font(.system(size: 10)).foregroundStyle(Theme.warn)
                .padding(.horizontal, 14).padding(.vertical, 8)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Theme.warn.opacity(0.10))

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

            // `m` is only present when AtelierView opened this sheet — the
            // composer's chip has no ledger to ask about, and offering a
            // button that would crash or silently no-op there is worse
            // than not offering it.
            if let m {
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
                            .foregroundStyle(an.lastProposals > 0 ? Theme.warn : Theme.dim)
                            .lineLimit(2)
                    }
                    Spacer(minLength: 0)
                }
                .padding(14)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Theme.panel)
            }
        }
        .frame(width: 560, height: 560)
        .background(Theme.bg)
        .onAppear { if lmHost.isEmpty { lmHost = app.lmStudioEndpoint } }
        .task {
            // AtelierView also refreshes `an` on its own appear, but the
            // composer's chip can open this sheet without AtelierView ever
            // having been on screen (mode switched, garment tab never
            // opened) — an empty list there would read as "nothing is
            // available" instead of "not asked yet".
            await an.refresh(app: app)
        }
    }

    private func group<T: View>(_ title: String,
                                @ViewBuilder _ body: () -> T) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(title.uppercased())
                .font(.system(size: 9, weight: .semibold, design: .monospaced))
                .foregroundStyle(Theme.faint)
                .padding(.horizontal, 14).padding(.top, 10).padding(.bottom, 4)
            body()
        }
    }

    private func empty(_ s: String) -> some View {
        Text(s).font(.system(size: 11)).foregroundStyle(Theme.faint)
            .padding(.horizontal, 14).padding(.vertical, 5)
    }

    private func row(_ p: AtelierAnalyst.Pick, _ sub: String) -> some View {
        let on = an.pick == p
        return HStack(spacing: 8) {
            Text(on ? "●" : "○").font(.system(size: 10))
                .foregroundStyle(on ? Theme.sel : Theme.faint)
            VStack(alignment: .leading, spacing: 1) {
                Text(p.label).font(.system(size: 12))
                    .foregroundStyle(on ? Theme.fg : Theme.dim)
                Text(sub).font(.system(size: 9)).foregroundStyle(Theme.faint)
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 14).padding(.vertical, 5)
        .background(on ? Theme.panel2 : .clear)
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
        .background(Theme.bg)
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
                    .foregroundStyle(Theme.faint)
                ForEach(Self.intents, id: \.0) { key, label in
                    Text(label).font(.system(size: 11))
                        .padding(.horizontal, 9).padding(.vertical, 2)
                        .background(Capsule().stroke(
                            m.intent == key ? Theme.sel : Theme.line, lineWidth: 1))
                        .foregroundStyle(m.intent == key ? Theme.fg : Theme.dim)
                        .onTapGesture { Task { await m.setIntent(key) } }
                }
            }
            // 用途を切り替えても由来は変わらない。ここを書いておかないと
            // 「自分用にすれば消える」と読まれる。
            Text(app.t("Choosing a use is not a permit: no origin changes, "
                       + "only the homework list does.",
                       "用途は許可証ではありません。どの由来も変わらず、"
                       + "変わるのは宿題の一覧だけです。"))
                .font(.system(size: 10)).foregroundStyle(Theme.faint)
            if !m.legalAnswer.isEmpty {
                Text(m.legalAnswer).font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(Theme.warn).textSelection(.enabled)
                    .padding(8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(RoundedRectangle(cornerRadius: 5)
                        .fill(Theme.warn.opacity(0.10)))
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.panel)
    }

    private var worklist: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text(app.t("HOMEWORK", "宿題")).railHead()
                Spacer()
                Text("\(m.rightsWorklist.count)")
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(Theme.faint).padding(.trailing, 14)
            }
            if m.rightsWorklist.isEmpty {
                Text(app.t("nothing flagged — which is not the same as clear",
                           "挙がっているものはありません（問題が無いという"
                           + "意味ではありません）"))
                    .font(.system(size: 11)).foregroundStyle(Theme.faint)
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
                        .foregroundStyle(Theme.dim)
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
                            .foregroundStyle(Theme.dim)
                        stateChip(r.state)
                        Spacer(minLength: 0)
                    }
                    if !r.specificSources.isEmpty {
                        line("実例", r.specificSources, Theme.bad)
                    }
                    if !r.genericSources.isEmpty {
                        line("一般", r.genericSources, Theme.ok)
                    }
                    if !r.searchedScopes.isEmpty {
                        line("探した範囲", r.searchedScopes, Theme.dim)
                    }
                    if !r.declaredBy.isEmpty {
                        line("名乗り", r.declaredBy, Theme.sel)
                    }
                    if !r.howToClose.isEmpty {
                        Text("→ " + r.howToClose).font(.system(size: 10))
                            .foregroundStyle(Theme.warn)
                    }
                }
                .padding(.horizontal, 14).padding(.vertical, 6)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(m.selected == r.part ? Theme.panel2 : .clear)
                .contentShape(Rectangle())
                .onTapGesture { m.selected = r.part; aspect = r.aspect }
                Divider().opacity(0.12)
            }
        }
    }

    private func line(_ label: String, _ items: [String],
                      _ colour: Color) -> some View {
        HStack(alignment: .top, spacing: 6) {
            Text(label).font(.system(size: 9)).foregroundStyle(Theme.faint)
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
                    .font(.system(size: 10)).foregroundStyle(Theme.faint)
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
                    .foregroundStyle(Theme.bad)
            }
            // 一般は2本要る、という規律を押す前に出しておく。
            Text(app.t("A construction counts as common only with two "
                       + "independent named sources.",
                       "「一般構造」は、名前の付いた独立した出典が2本"
                       + "揃って初めて成立します。"))
                .font(.system(size: 9)).foregroundStyle(Theme.faint)
        }
        .padding(13)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.panel)
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
        case "SPECIFIC_TO_SOURCE": return Theme.bad
        case "CONTESTED_ORIGIN": return Theme.bad
        case "GENERIC_CONSTRUCTION": return Theme.ok
        case "DECLARED_BY": return Theme.sel
        case "UNKNOWN_NO_MATCH_IN": return Theme.warn
        default: return Theme.dim
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
                    .font(.system(size: 10)).foregroundStyle(Theme.faint)
                HStack(spacing: 12) {
                    counter("そのまま", m.designCounts["kept"] ?? 0, Theme.dim)
                    counter("変えた", m.designCounts["changed"] ?? 0, Theme.warn)
                    counter("新しく決めた", m.designCounts["new"] ?? 0, Theme.ok)
                }
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.panel)
            Divider().opacity(0.25)

            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    if m.designRows.isEmpty {
                        Text(app.t("Nothing designed yet.",
                                   "まだ何も設計していません。"))
                            .font(.system(size: 11))
                            .foregroundStyle(Theme.faint).padding(14)
                    }
                    ForEach(Array(m.designRows.enumerated()),
                            id: \.offset) { _, r in
                        VStack(alignment: .leading, spacing: 2) {
                            HStack(spacing: 8) {
                                Text("\(r.part) / \(r.aspect)")
                                    .font(.system(size: 11,
                                                  design: .monospaced))
                                    .foregroundStyle(Theme.dim)
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
                                    .foregroundStyle(Theme.faint)
                            }
                            Text(r.value)
                                .font(.system(size: 12, weight: .semibold))
                            if !r.originalValue.isEmpty {
                                // 変えた事実が由来。消さない。
                                Text("← \(r.originalValue)  (\(r.derivedFrom))")
                                    .font(.system(size: 10,
                                                  design: .monospaced))
                                    .foregroundStyle(Theme.faint)
                            } else if !r.derivedFrom.isEmpty {
                                Text("← \(r.derivedFrom)")
                                    .font(.system(size: 10,
                                                  design: .monospaced))
                                    .foregroundStyle(Theme.faint)
                            }

                            // **原作品 → 観測 → 設計 の全段を出す。**
                            // 一つ前だけでは、二度変えた値の出どころが
                            // 消えます。開いたときだけ引きます。
                            let key = "\(r.part)/\(r.aspect)"
                            if let trail = m.designTrail[key] {
                                ForEach(trail) { st in
                                    HStack(spacing: 6) {
                                        Text(st.stage)
                                            .font(.system(size: 9,
                                                weight: .semibold))
                                            .foregroundStyle(Theme.dim)
                                            .frame(width: 76,
                                                   alignment: .leading)
                                        Text(st.value)
                                            .font(.system(size: 9,
                                                design: .monospaced))
                                        if !st.source.isEmpty {
                                            Text(st.source)
                                                .font(.system(size: 9))
                                                .foregroundStyle(Theme.faint)
                                        }
                                        Spacer(minLength: 0)
                                    }
                                }
                                .padding(.leading, 10).padding(.top, 2)
                            } else {
                                Button(app.t("where did this come from?",
                                             "どこから来たか")) {
                                    Task {
                                        await m.loadDesignTrail(
                                            part: r.part, aspect: r.aspect)
                                    }
                                }
                                .buttonStyle(.plain)
                                .font(.system(size: 9))
                                .foregroundStyle(Theme.sel)
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
                        .foregroundStyle(Theme.bad)
                }
                Text(app.t("Only confirmed observations can be kept or "
                           + "changed — an uncertain value must not be cut.",
                           "そのまま／変える は確定した観測にしか使えません。"
                           + "定まっていない値を裁つことになるためです。"))
                    .font(.system(size: 9)).foregroundStyle(Theme.faint)
            }
            .padding(13)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.panel)
        }
        .background(Theme.bg)
        .task { await m.loadDesign() }
        .onAppear {
            if aspect.isEmpty { aspect = m.aspects(of: m.selected).first ?? "" }
            // 設定 › 服飾の設定 の「台帳に残す名前」を初期値にする。
            if by.isEmpty { by = app.atelierOperatorName }
        }
        .onChange(of: m.selected) { _ in
            aspect = m.aspects(of: m.selected).first ?? "" }
    }

    private func counter(_ label: String, _ n: Int,
                         _ colour: Color) -> some View {
        HStack(spacing: 5) {
            Text("\(n)").font(.system(size: 13, weight: .semibold,
                                      design: .monospaced))
                .foregroundStyle(colour)
            Text(label).font(.system(size: 10)).foregroundStyle(Theme.dim)
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
        case "kept": return Theme.dim
        case "changed": return Theme.warn
        default: return Theme.ok
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
        .background(Theme.bg)
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack(spacing: 10) {
                Text(app.t("Sources", "素材")).font(
                    .system(size: 13, weight: .semibold))
                if intake.busy {
                    ProgressView().controlSize(.small)
                    Text(intake.stage).font(.system(size: 10))
                        .foregroundStyle(Theme.dim)
                }
                Spacer()
                Text(app.t("frames", "コマ数")).font(.system(size: 10))
                    .foregroundStyle(Theme.faint)
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
                .font(.system(size: 10)).foregroundStyle(Theme.faint)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.panel)
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
                        .font(.system(size: 11)).foregroundStyle(Theme.faint)
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
                                .foregroundStyle(Theme.faint)
                        }
                        Spacer(minLength: 0)
                    }
                    .padding(.horizontal, 10).padding(.vertical, 4)
                    .background(intake.selectedClip?.path == c.path
                                ? Theme.panel2 : .clear)
                    .contentShape(Rectangle())
                    .onTapGesture { intake.selectedClip = c }
                }
            }
            .padding(.vertical, 6)
        }
        .background(Theme.panel)
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
                            .foregroundStyle(Theme.dim).lineLimit(1)
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
                                        .foregroundStyle(Theme.faint)
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
                    .font(.system(size: 11)).foregroundStyle(Theme.faint)
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
                        .foregroundStyle(Theme.dim)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            .padding(.horizontal, 14).padding(.vertical, 6)
        }
        .frame(height: 84)
        .background(Theme.panel)
    }

    private func thumb(_ path: String, side: CGFloat) -> some View {
        Group {
            if let img = NSImage(contentsOfFile: path) {
                Image(nsImage: img).resizable().scaledToFit()
            } else {
                RoundedRectangle(cornerRadius: 3).fill(Theme.panel2)
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
                    .font(.system(size: 10)).foregroundStyle(Theme.faint)
                HStack(spacing: 12) {
                    counter(app.t("measured", "実測"),
                            m.measureCounts["measured"] ?? 0, Theme.ok)
                    counter(app.t("derived", "計算値"),
                            m.measureCounts["derived"] ?? 0, Theme.warn)
                    counter(app.t("contested", "食い違い"),
                            m.measureCounts["contested"] ?? 0, Theme.bad)
                    counter(app.t("not taken", "未取得"),
                            m.measureCounts["open"] ?? 0, Theme.dim)
                }
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.panel)
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
                                    .foregroundStyle(Theme.faint)
                                Spacer(minLength: 0)
                                stateChip(r.state)
                            }
                            if let v = r.value {
                                Text("\(v, specifier: "%.1f") \(r.unit)")
                                    .font(.system(size: 14, weight: .semibold))
                                    .foregroundStyle(r.state == "DERIVED"
                                                     ? Theme.warn : Theme.fg)
                            }
                            // **食い違いは両方出す。** どちらかを選んで
                            // 見せると、選んだのが誰なのか分からなくなる。
                            ForEach(r.sides) { side in
                                HStack(spacing: 8) {
                                    Text(String(format: "%.1f %@",
                                                side.value, side.unit))
                                        .font(.system(size: 14,
                                                      weight: .semibold))
                                        .foregroundStyle(Theme.bad)
                                    Text(side.source)
                                        .font(.system(size: 9))
                                        .foregroundStyle(Theme.faint)
                                    if !side.by.isEmpty {
                                        Text("測: " + side.by)
                                            .font(.system(size: 9))
                                            .foregroundStyle(Theme.faint)
                                    }
                                    Spacer(minLength: 0)
                                }
                            }
                            if !r.why.isEmpty {
                                Text(r.why).font(.system(size: 10))
                                    .foregroundStyle(Theme.bad)
                            }
                            if !r.from.isEmpty {
                                // 計算値は、どこから出たかを必ず伴う。
                                Text("← \(r.from)")
                                    .font(.system(size: 10,
                                                  design: .monospaced))
                                    .foregroundStyle(Theme.faint)
                            }
                            if !r.source.isEmpty {
                                Text(r.source).font(.system(size: 9))
                                    .foregroundStyle(Theme.faint)
                            }
                            if !r.howToClose.isEmpty {
                                Text("→ " + r.howToClose)
                                    .font(.system(size: 10))
                                    .foregroundStyle(Theme.warn)
                            }
                        }
                        .padding(.horizontal, 14).padding(.vertical, 6)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        Divider().opacity(0.12)
                    }
                    Divider().opacity(0.2).padding(.top, 10)
                    patternSection
                }
            }

            Divider().opacity(0.25)
            recorder
        }
        .background(Theme.bg)
        .task {
            await m.loadMeasures()
            await m.loadPattern()
        }
        .onAppear {
            // 設定 › 服飾の設定 の既定単位・既定の名前を初期値にする。
            unit = app.atelierDefaultUnit
            if by.isEmpty { by = app.atelierOperatorName }
        }
    }

    // MARK: 型紙

    /// 型紙の節。**足りない寸法を既定で埋めない。**
    ///
    /// 立体(見るもの)は既定の比率で補ってよいが、型紙は裁つものなので、
    /// 無い寸法は無いと言って引きません。
    @ViewBuilder
    private var patternSection: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text(app.t("PATTERN", "型紙")).railHead()
                Spacer()
                if m.patternVerdict == "ANSWER" {
                    Text(String(format: "%.0f cm²", m.patternTotalArea))
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(Theme.faint)
                    Button(app.t("Save SVG…", "SVGで書き出す…")) {
                        savePattern()
                    }.font(.system(size: 10))
                }
            }
            .padding(.top, 8).padding(.trailing, 14)

            if m.patternVerdict != "ANSWER" {
                VStack(alignment: .leading, spacing: 4) {
                    Text(app.t("cannot draft yet — missing: ",
                               "まだ引けません。足りない寸法: ")
                         + m.patternMissing.joined(separator: "、"))
                        .font(.system(size: 11)).foregroundStyle(Theme.warn)
                    Text("→ " + m.patternHowToClose)
                        .font(.system(size: 10)).foregroundStyle(Theme.warn)
                    Text(app.t("A pattern is cut from. Missing measurements "
                               + "are not filled with defaults here.",
                               "型紙は裁つものなので、足りない寸法を既定で"
                               + "埋めません。"))
                        .font(.system(size: 9)).foregroundStyle(Theme.faint)
                }
                .padding(.horizontal, 14).padding(.vertical, 8)
            } else {
                PatternFigure(pieces: m.patternPieces)
                    .frame(height: 210)
                    .padding(10)
                    .frame(maxWidth: .infinity)
                    .background(RoundedRectangle(cornerRadius: 4)
                        .fill(Color.white))
                    .padding(.horizontal, 14)

                if !m.patternSleeveMissing.isEmpty {
                    Text(app.t("sleeve not drafted — missing: ",
                               "袖は引いていない。足りない寸法: ")
                         + m.patternSleeveMissing.joined(separator: "、"))
                        .font(.system(size: 10)).foregroundStyle(Theme.warn)
                        .padding(.horizontal, 14).padding(.top, 4)
                }

                Text(app.t("solid = sew line · dashed = cut line · "
                           + "green = grain · dots = notches "
                           + "(large = double, the back)",
                           "実線=出来上がり線 / 破線=裁ち切り線 / "
                           + "緑=布目線 / 点=合印（大きい方が双＝後ろ）"))
                    .font(.system(size: 9)).foregroundStyle(Theme.faint)
                    .padding(.horizontal, 14).padding(.top, 4)

                // **合印はいせを運ぶ。** 区間ごとの数字を出さないと、
                // 「印が付いた」だけで中身が見えない。
                if !m.easeSegments.isEmpty {
                    HStack(spacing: 8) {
                        Text(app.t("EASE BY NOTCH SEGMENT",
                                   "いせの配分 — 合印で区切った区間"))
                            .railHead()
                        Spacer(minLength: 0)
                        Text(app.t("\(m.notchPairCount) pairs · "
                                   + "\(m.notchUnpaired) unpaired",
                                   "\(m.notchPairCount) 対 ・ "
                                   + "相手なし \(m.notchUnpaired)"))
                            .font(.system(size: 9))
                            .foregroundStyle(m.notchUnpaired == 0
                                             ? Theme.faint : Theme.bad)
                            .padding(.trailing, 14)
                    }
                    .padding(.top, 10)
                    ForEach(m.easeSegments) { e in
                        HStack(spacing: 8) {
                            Text("\(e.from) → \(e.to)")
                                .font(.system(size: 10))
                                .frame(width: 130, alignment: .leading)
                            Text(String(format: "%.2f / %.2f",
                                        e.capCm, e.armholeCm))
                                .font(.system(size: 9,
                                              design: .monospaced))
                                .foregroundStyle(Theme.faint)
                            Text(String(format: "%+.2fcm", e.easeCm))
                                .font(.system(size: 11, weight: .semibold))
                                // 脇の下のいせ 0 は正しい姿。
                                .foregroundStyle(abs(e.easeCm) < 0.05
                                                 ? Theme.dim : Theme.ok)
                            if abs(e.easeCm) < 0.05 {
                                Text(app.t("no ease (armpit)",
                                           "いせ無し（脇の下）"))
                                    .font(.system(size: 9))
                                    .foregroundStyle(Theme.faint)
                            }
                            Spacer(minLength: 0)
                        }
                        .padding(.horizontal, 14).padding(.vertical, 2)
                    }
                }

                if !m.allowanceRows.isEmpty {
                    Text(app.t("SEAM ALLOWANCE — by edge",
                               "縫い代 — 辺ごと")).railHead()
                        .padding(.top, 10)
                    ForEach(m.allowanceRows) { r in
                        HStack(spacing: 8) {
                            Text(r.edge).font(.system(size: 10))
                                .frame(width: 90, alignment: .leading)
                            Text(String(format: "%.2fcm", r.cm))
                                .font(.system(size: 11, weight: .semibold))
                                .foregroundStyle(r.cm == 0 ? Theme.faint : Theme.dim)
                            Text(r.imperial)
                                .font(.system(size: 9,
                                              design: .monospaced))
                                .foregroundStyle(Theme.faint)
                            Text(r.why).font(.system(size: 9))
                                .foregroundStyle(Theme.faint)
                            Spacer(minLength: 0)
                        }
                        .padding(.horizontal, 14).padding(.vertical, 2)
                    }
                    if !m.marksStandardNote.isEmpty {
                        Text(m.marksStandardNote)
                            .font(.system(size: 9))
                            .foregroundStyle(Theme.faint)
                            .padding(.horizontal, 14).padding(.top, 3)
                    }
                }

                // **縫い合わせの差を必ず出す。** 合っていることを主張
                // するのではなく、差を見せる。
                Text(app.t("SEAM CHECK — the difference, not a verdict",
                           "縫い合わせの検算 — 差を出す")).railHead()
                    .padding(.top, 10)
                ForEach(m.patternChecks) { c in
                    VStack(alignment: .leading, spacing: 2) {
                        HStack(spacing: 8) {
                            Text(c.label).font(.system(size: 11,
                                                       weight: .semibold))
                            Text(String(format: "%.2f vs %.2f",
                                        c.lengthA, c.lengthB))
                                .font(.system(size: 10,
                                              design: .monospaced))
                                .foregroundStyle(Theme.faint)
                            Text(String(format: "%+.2fcm", c.difference))
                                .font(.system(size: 12, weight: .semibold))
                                .foregroundStyle(c.sewable ? Theme.ok : Theme.bad)
                            Text(c.sewable ? app.t("sewable", "縫える")
                                           : app.t("does not sew",
                                                   "このままでは縫えない"))
                                .font(.system(size: 10))
                                .foregroundStyle(c.sewable ? Theme.ok : Theme.bad)
                            Spacer(minLength: 0)
                        }
                        Text(c.why).font(.system(size: 9))
                            .foregroundStyle(Theme.faint)
                    }
                    .padding(.horizontal, 14).padding(.vertical, 5)
                    Divider().opacity(0.1)
                }

                VStack(alignment: .leading, spacing: 3) {
                    Text(m.patternSeamAllowance).font(.system(size: 10))
                        .foregroundStyle(Theme.bad)
                    Text(m.patternNotPublished).font(.system(size: 9))
                        .foregroundStyle(Theme.faint)
                    // 式を全部見せる。名前だけ借りると監査できない。
                    DisclosureGroup(app.t("formulas used",
                                          "使った式（全部）")) {
                        ForEach(Array(m.patternFormulas.enumerated()),
                                id: \.offset) { _, f in
                            HStack(alignment: .top, spacing: 8) {
                                Text(f.0).font(.system(size: 10))
                                    .foregroundStyle(Theme.dim)
                                    .frame(width: 150, alignment: .leading)
                                Text(f.1).font(.system(size: 10,
                                                       design: .monospaced))
                                Spacer(minLength: 0)
                            }
                        }
                    }
                    .font(.system(size: 10))
                }
                .padding(.horizontal, 14).padding(.vertical, 8)
            }
        }
    }

    private func savePattern() {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = "pattern.svg"
        panel.message = AppLanguage.shared.t(
            "Save the pattern (finished lines; no seam allowance)",
            "型紙を保存する（出来上がり線。縫い代は入っていません）")
        guard panel.runModal() == .OK, let url = panel.url else { return }
        Task { said = await m.savePattern(to: url.path) }
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
                    .foregroundStyle(Theme.bad)
            }
            Text(app.t("A ratio is not a length until its basis is measured.",
                       "比率は、基準が実測で入るまで長さになりません。"))
                .font(.system(size: 9)).foregroundStyle(Theme.faint)
        }
        .padding(13)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.panel)
    }

    private func counter(_ label: String, _ n: Int,
                         _ colour: Color) -> some View {
        HStack(spacing: 5) {
            Text("\(n)").font(.system(size: 13, weight: .semibold,
                                      design: .monospaced))
                .foregroundStyle(colour)
            Text(label).font(.system(size: 10)).foregroundStyle(Theme.dim)
        }
    }

    private func stateChip(_ state: String) -> some View {
        let (label, colour): (String, Color) = {
            switch state {
            case "MEASURED": return ("実測", Theme.ok)
            case "DERIVED": return ("計算値", Theme.warn)
            case "UNKNOWN_NO_BASIS": return ("基準待ち", Theme.warn)
            default: return ("未取得", Theme.dim)
            }
        }()
        return Text(label).font(.system(size: 9, weight: .semibold))
            .padding(.horizontal, 6).padding(.vertical, 1)
            .background(Capsule().stroke(colour, lineWidth: 1))
            .foregroundStyle(colour)
    }
}

// MARK: - 設計図

/// 設計図の面。**作図であって生成ではない。**
///
/// モデルに「このコートを描いて」と言うと、台帳に無いものが絵に入る。
/// その絵を縫製師が見れば、台帳に無いものまで指示として読む。ここが
/// 描くのは確定した項目と寸法だけで、同じ台帳からは必ず同じ図が出る。
private struct DrawingPanel: View {
    @ObservedObject var m: AtelierModel
    @EnvironmentObject var app: AppState
    @State private var said = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 10) {
                    Text(app.t("Technical flat", "設計図"))
                        .font(.system(size: 13, weight: .semibold))
                    Spacer()
                    Button(app.t("Redraw", "描き直す")) {
                        Task { await m.loadDrawing() }
                    }.font(.system(size: 11))
                    Button(app.t("Save…", "書き出す…")) { saveSVG() }
                        .font(.system(size: 11))
                        .disabled(m.drawSVG.isEmpty)
                }
                Text(app.t("Drawn from the ledger, not generated. The same "
                           + "ledger always draws the same figure.",
                           "台帳から作図しています。生成ではありません。"
                           + "同じ台帳からは必ず同じ図が出ます。"))
                    .font(.system(size: 10)).foregroundStyle(Theme.faint)
                if !m.drawSkipped.isEmpty {
                    // **描かなかったものを、図の外でも言う。**
                    Text(app.t("not drawn (nothing confirmed): ",
                               "未確定のため描いていない: ")
                         + m.drawSkipped.joined(separator: "、"))
                        .font(.system(size: 10)).foregroundStyle(Theme.bad)
                }
                if !m.drawDefaulted.isEmpty {
                    Text(app.t("drawn from default ratios: ",
                               "既定の比率で描いた寸法: ")
                         + m.drawDefaulted.joined(separator: "、"))
                        .font(.system(size: 10)).foregroundStyle(Theme.warn)
                }
                if !said.isEmpty {
                    Text(said).font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(said == "ANSWER" ? Theme.ok : Theme.bad)
                }
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.panel)
            Divider().opacity(0.25)

            ScrollView {
                if m.drawShapes.isEmpty {
                    Text(app.t("Nothing confirmed yet — nothing to draw.",
                               "確定した項目がまだありません。"))
                        .font(.system(size: 11)).foregroundStyle(Theme.faint)
                        .padding(24)
                } else {
                    // **白い紙の上の黒い線。** 設計図は印刷して使う。
                    VStack(alignment: .leading, spacing: 6) {
                        // 画面の図は**プレビュー**。原本は書き出す SVG
                        // なので、注記まで一画面に収まる大きさにする。
                        // 図だけ大きくして注記が枠外に出ると、「未確定の
                        // ため描いていない」が読まれない — それが読まれ
                        // ないと、空白が完成した設計に見える。
                        FlatFigure(shapes: m.drawShapes,
                                   canvas: m.drawCanvas)
                            .frame(width: 150, height: 150
                                   * m.drawCanvas.height
                                   / max(m.drawCanvas.width, 1))
                            .frame(maxWidth: .infinity)
                        // 図に載る文字。**紙と同じ順で、同じ紙の上に。**
                        // 絶対座標で置いた版は画面に出なかった(実地)。
                        ForEach(m.drawLabels) { lab in
                            Text(lab.text)
                                .font(.system(size: 11))
                                .foregroundStyle(labelColour(lab.tone))
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                    .padding(14)
                    .background(RoundedRectangle(cornerRadius: 4)
                        .fill(Color.white))
                    .padding(12)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .background(Theme.bg)
        .task { await m.loadDrawing() }
    }

    /// SVG を描画する。**元の SVG を保持したまま**表示だけ画像にする —
    /// 書き出すのは画像ではなく SVG で、そちらが原本。
    private func image(from svg: String) -> NSImage? {
        guard let data = svg.data(using: .utf8) else { return nil }
        return NSImage(data: data)
    }

    private func labelColour(_ tone: String) -> Color {
        switch tone {
        case "warn": return Color(red: 0.69, green: 0.05, blue: 0.27)
        case "quiet": return Color(white: 0.40)
        default: return .black
        }
    }

    private func saveSVG() {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = "technical-flat.svg"
        panel.message = AppLanguage.shared.t(
            "Save the flat (marked as generated — it cannot be read back "
            + "as evidence)",
            "設計図を保存する（生成物の印が付き、観測の出典にはできません）")
        guard panel.runModal() == .OK, let url = panel.url else { return }
        Task { said = await m.saveDrawing(to: url.path) }
    }
}

/// 設計図の線を描く。**エンジンが返した座標をそのまま引く** — ここで
/// 形を足したり整えたりしない。足した線は誰も観測していない線になる。
private struct FlatFigure: View {
    let shapes: [AtelierModel.DrawShape]
    let canvas: CGSize

    var body: some View {
        GeometryReader { g in
            let s = min(g.size.width / max(canvas.width, 1),
                        g.size.height / max(canvas.height, 1))
            ZStack {
                ForEach(shapes) { shape in
                    Path { p in
                        guard let first = shape.points.first else { return }
                        p.move(to: CGPoint(x: first.x * s, y: first.y * s))
                        for pt in shape.points.dropFirst() {
                            p.addLine(to: CGPoint(x: pt.x * s, y: pt.y * s))
                        }
                        p.closeSubpath()
                    }
                    .stroke(Color.black, lineWidth: 1.4)
                }
            }
        }
    }

}

// MARK: - 証拠

/// 証拠の面。**開けるものは開ける。**
///
/// 台帳は「◉ 見に行ける」と出しているのに、押しても行けなかった。
/// 確かめられると言って確かめさせないのは、確かめられないより悪い —
/// 読み手は確かめた気になる。ここは参照を実際に開く。
private struct EvidencePanel: View {
    @ObservedObject var m: AtelierModel
    @EnvironmentObject var app: AppState
    @State private var onlyOpenable = false

    private var rows: [AtelierModel.Evidence] {
        onlyOpenable ? m.timeline.filter { $0.refStatus == "VERIFIABLE" }
                     : m.timeline
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 10) {
                    Text(app.t("Evidence", "証拠"))
                        .font(.system(size: 13, weight: .semibold))
                    Text("\(m.timeline.count)")
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(Theme.faint)
                    Spacer()
                    Toggle(app.t("only what can be re-opened",
                                 "見に行けるものだけ"),
                           isOn: $onlyOpenable)
                        .toggleStyle(.checkbox).font(.system(size: 11))
                }
                Text(app.t("Every reading is kept — nothing is deleted. "
                           + "Repeated reads of one frame are folded only in "
                           + "the pack handed to the maker.",
                           "読みは全部残しています（何も消しません）。"
                           + "同じコマの繰り返しを畳むのは、縫製師に渡す"
                           + "資料の中だけです。"))
                    .font(.system(size: 10)).foregroundStyle(Theme.faint)
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.panel)
            Divider().opacity(0.25)

            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    if rows.isEmpty {
                        Text(app.t("Nothing recorded yet.",
                                   "まだ何も記録されていません。"))
                            .font(.system(size: 11))
                            .foregroundStyle(Theme.faint).padding(14)
                    }
                    ForEach(rows) { r in
                        VStack(alignment: .leading, spacing: 3) {
                            HStack(spacing: 8) {
                                Text(r.at.isEmpty ? "—" : r.at)
                                    .font(.system(size: 11,
                                                  design: .monospaced))
                                    .foregroundStyle(Theme.dim)
                                    .frame(width: 52, alignment: .leading)
                                Text("\(r.part) / \(r.aspect)")
                                    .font(.system(size: 11,
                                                  design: .monospaced))
                                    .foregroundStyle(Theme.dim)
                                Text(r.value)
                                    .font(.system(size: 12, weight: .semibold))
                                Spacer(minLength: 0)
                                kindChip(r.kind)
                            }
                            HStack(spacing: 8) {
                                Text(r.source)
                                    .font(.system(size: 10,
                                                  design: .monospaced))
                                    .foregroundStyle(Theme.faint)
                                if !r.adoptedBy.isEmpty {
                                    Text(app.t("adopted by ", "採用: ")
                                         + r.adoptedBy)
                                        .font(.system(size: 10))
                                        .foregroundStyle(Theme.ok)
                                }
                                Spacer(minLength: 0)
                                reference(r)
                            }
                            if !r.note.isEmpty {
                                Text(r.note).font(.system(size: 10))
                                    .foregroundStyle(Theme.faint)
                            }
                        }
                        .padding(.horizontal, 14).padding(.vertical, 7)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        Divider().opacity(0.12)
                    }
                }
            }
        }
        .background(Theme.bg)
        .task { await m.load() }
    }

    @ViewBuilder
    private func reference(_ r: AtelierModel.Evidence) -> some View {
        switch r.refStatus {
        case "VERIFIABLE":
            VStack(alignment: .leading, spacing: 1) {
                Button {
                    open(r)
                } label: {
                    HStack(spacing: 4) {
                        Text("◉").font(.system(size: 9))
                        Text(shortRef(r)).font(.system(size: 10,
                                                       design: .monospaced))
                    }
                }
                .buttonStyle(.link)
                .foregroundStyle(Theme.ok)

                // **コマの出どころ。** ファイル名だけでは、どの素材の
                // どこを見たのかが残らない。紐づいていなければそう言う。
                if !r.refPath.isEmpty {
                    if let o = m.clipOrigins[r.refPath] {
                        Text(o.hasPrefix("UNKNOWN")
                             ? app.t("not tied to a source",
                                     "元の素材に紐づいていません")
                             : o)
                            .font(.system(size: 9))
                            .foregroundStyle(o.hasPrefix("UNKNOWN")
                                             ? Theme.warn : Theme.faint)
                    } else {
                        Button(app.t("which source?", "どの素材から？")) {
                            Task { await m.loadClipOrigin(r.refPath) }
                        }
                        .buttonStyle(.plain)
                        .font(.system(size: 9))
                        .foregroundStyle(Theme.sel)
                    }
                }
            }
        case "UNKNOWN_SOURCE_NOT_FOUND":
            // **「手元に無い」であって「無い」ではない。** 外付けを
            // 繋げば開ける。消えたものと同じ顔にしない。
            HStack(spacing: 4) {
                Text("○").font(.system(size: 9))
                Text(app.t("not on this machine", "この機体には無い"))
                    .font(.system(size: 10))
            }
            .foregroundStyle(Theme.warn)
            .help(r.refPath)
        default:
            Text(app.t("no pointer", "参照なし"))
                .font(.system(size: 10)).foregroundStyle(Theme.faint)
        }
    }

    private func shortRef(_ r: AtelierModel.Evidence) -> String {
        let name = r.refPath.isEmpty
            ? r.refURL : (r.refPath as NSString).lastPathComponent
        return r.refMark.isEmpty ? name : "\(name) @ \(r.refMark)"
    }

    /// 参照を開く。**その場所を指すだけで、複製は作らない。**
    private func open(_ r: AtelierModel.Evidence) {
        if !r.refPath.isEmpty {
            NSWorkspace.shared.activateFileViewerSelecting(
                [URL(fileURLWithPath: r.refPath)])
        } else if let u = URL(string: r.refURL), !r.refURL.isEmpty {
            NSWorkspace.shared.open(u)
        }
    }

    private func kindChip(_ kind: String) -> some View {
        let (label, colour): (String, Color) = {
            switch kind {
            case "observation": return (app.t("observed", "観測"), Theme.ok)
            case "inference": return (app.t("inferred", "推論"), Theme.warn)
            default: return (app.t("proposal", "提案"), Theme.sel)
            }
        }()
        return Text(label).font(.system(size: 9, weight: .semibold))
            .padding(.horizontal, 6).padding(.vertical, 1)
            .background(Capsule().stroke(colour, lineWidth: 1))
            .foregroundStyle(colour)
    }
}

// MARK: - 素材

/// 素材の面。**場所を持たないものを、図の上に置かない。**
///
/// fabric と lining は身体のどこかにあるものではないので、コートの図に
/// 印を打てない。図に載せると、読み手は「そこを見た」と誤解する。
/// ここは素材だけを、由来と一緒に並べる面。
///
/// 由来を隣に置くのは、素材が**最も外から来やすい**側面だからです。
/// 生地は映像から読めないことが多く、類似品検索やモデルの推測が
/// 入りやすい。どこから来た値かが同じ画面に無いと、採用の判断ができない。
private struct MaterialsPanel: View {
    @ObservedObject var m: AtelierModel
    @EnvironmentObject var app: AppState
    @State private var newFabric = ""
    @State private var newProp = "weight"
    @State private var newValue = ""
    @State private var newSource = ""
    @State private var said = ""
    @State private var inner = ""
    @State private var outer = ""
    @State private var layers = ""
    @State private var tryFabric = ""

    private var materialParts: [String] { m.nonSpatial }

    private var fabricNames: [String] {
        Array(Set(m.fabricRows.filter { $0.state != "UNKNOWN_NOT_RECORDED" }
            .map(\.fabric))).sorted()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            VStack(alignment: .leading, spacing: 6) {
                Text(app.t("Materials", "素材"))
                    .font(.system(size: 13, weight: .semibold))
                Text(app.t("Materials have no place on the body, so they are "
                           + "not marked on the figure. Where a value came "
                           + "from sits next to it — fabric is the aspect "
                           + "most often supplied from outside.",
                           "素材は身体のどこかにあるものではないので、図に"
                           + "印を打ちません。どこから来た値かを隣に置いて"
                           + "います — 生地は外から入りやすい側面です。"))
                    .font(.system(size: 10)).foregroundStyle(Theme.faint)
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.panel)
            Divider().opacity(0.25)

            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(materialParts, id: \.self) { part in
                        Text(part.uppercased()).railHead().padding(.top, 8)
                        ForEach(m.aspects(of: part), id: \.self) { aspect in
                            row(part, aspect)
                            Divider().opacity(0.12)
                        }
                    }
                    if materialParts.isEmpty {
                        Text(app.t("The engine has not answered yet.",
                                   "engine がまだ答えていません。"))
                            .font(.system(size: 11))
                            .foregroundStyle(Theme.faint).padding(14)
                    }
                    Divider().opacity(0.2).padding(.top, 10)
                    fabricLibrary
                    Divider().opacity(0.2)
                    stack
                }
                .padding(.bottom, 12)
            }
        }
        .background(Theme.bg)
        .task {
            await m.load()
            await m.loadFabrics()
        }
    }

    // MARK: 生地台帳（立体十字に載る）

    /// 生地の性質。**出典が食い違えば片方を勝たせない。**
    ///
    /// ここが立体十字の一番素直な使い所です。同じ「メルトン」でも一社が
    /// 420g/m²、別の資料が 450g/m² と書く。どちらかが嘘なのではなく、
    /// 別のものを指している可能性がある。一つに丸めると、選んだことが
    /// 消えます。
    private var fabricLibrary: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text(app.t("FABRIC LIBRARY", "生地台帳")).railHead()
                Spacer()
                Text("\(m.fabricCounts["contested"] ?? 0)"
                     + app.t(" split", " 件が割れている"))
                    .font(.system(size: 10))
                    .foregroundStyle((m.fabricCounts["contested"] ?? 0) > 0
                                     ? Theme.bad : Theme.faint)
                    .padding(.trailing, 14)
            }
            .padding(.top, 8)
            // **型紙の前に、生地だけを落としてみる。** 生地の物性が
            // おかしければ縫っても直らないので、先に切り分けられる。
            HStack(spacing: 8) {
                Text(app.t("DROP A PLAIN 40×40 SQUARE",
                           "平らな 40×40 の布を落としてみる"))
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(Theme.dim)
                Spacer(minLength: 0)
                Picker("", selection: $tryFabric) {
                    Text(app.t("pick", "生地")).tag("")
                    ForEach(fabricNames, id: \.self) { Text($0).tag($0) }
                }.labelsHidden().frame(width: 130)
                if m.drapeBusy { ProgressView().controlSize(.small) }
                Button(app.t("Drop", "落とす")) {
                    Task { await m.drapeValidate(fabric: tryFabric) }
                }
                .font(.system(size: 11))
                .disabled(tryFabric.isEmpty || m.drapeBusy)
            }
            .padding(.horizontal, 14).padding(.top, 8)

            if !m.drapeVerdict.isEmpty {
                ForEach(m.drapeChecks) { c in
                    HStack(spacing: 8) {
                        Text(c.name).font(.system(size: 10,
                                                  design: .monospaced))
                            .foregroundStyle(Theme.dim)
                            .frame(width: 70, alignment: .leading)
                        Text(c.verdict == "ANSWER"
                             ? app.t("passed", "通った") : c.verdict)
                            .font(.system(size: 10, weight: .semibold))
                            .foregroundStyle(c.verdict == "ANSWER"
                                             ? Theme.ok : Theme.bad)
                        if let d = c.difference {
                            Text(String(format: "%.3f", d)
                                 + (c.tolerance.map {
                                     String(format: " / %.2f", $0) } ?? ""))
                                .font(.system(size: 9,
                                              design: .monospaced))
                                .foregroundStyle(Theme.faint)
                        }
                        if !c.detail.isEmpty {
                            Text(c.detail).font(.system(size: 9,
                                                        design: .monospaced))
                                .foregroundStyle(Theme.faint)
                        }
                        Spacer(minLength: 0)
                    }
                    .padding(.horizontal, 14).padding(.vertical, 2)
                }
                if !m.drapeAssumed.isEmpty {
                    ForEach(m.drapeAssumed.sorted { $0.key < $1.key },
                            id: \.key) { k, v in
                        HStack(alignment: .top, spacing: 6) {
                            Text(k == "why"
                                 ? app.t("why", "なぜ")
                                 : app.t("assumed", "仮定"))
                                .font(.system(size: 9, weight: .semibold))
                                .foregroundStyle(Theme.warn)
                                .frame(width: 34, alignment: .leading)
                            Text(v).font(.system(size: 9))
                                .foregroundStyle(Theme.warn)
                                .fixedSize(horizontal: false, vertical: true)
                            Spacer(minLength: 0)
                        }
                        .padding(.horizontal, 14)
                    }
                }
                if !m.drapeWhyNoShape.isEmpty {
                    Text(m.drapeWhyNoShape).font(.system(size: 10))
                        .foregroundStyle(Theme.warn)
                        .padding(.horizontal, 14).padding(.bottom, 4)
                }
            }
            Divider().opacity(0.15).padding(.vertical, 6)

            ForEach(m.fabricRows.filter { $0.state != "UNKNOWN_NOT_RECORDED" }) { r in
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 8) {
                        Text(r.fabric).font(.system(size: 11,
                                                    weight: .semibold))
                        Text(r.prop).font(.system(size: 10,
                                                  design: .monospaced))
                            .foregroundStyle(Theme.dim)
                        Spacer(minLength: 0)
                        if r.state == "CONTESTED" {
                            Text(app.t("split", "割れている"))
                                .font(.system(size: 9, weight: .semibold))
                                .padding(.horizontal, 6).padding(.vertical, 1)
                                .background(Capsule().stroke(Theme.bad,
                                                             lineWidth: 1))
                                .foregroundStyle(Theme.bad)
                        }
                    }
                    if r.state == "CONTESTED" {
                        // **両方見せる。** どちらかを選ぶのは人。
                        ForEach(Array(r.sides.enumerated()),
                                id: \.offset) { _, side in
                            HStack(spacing: 6) {
                                Text(side.value)
                                    .font(.system(size: 12,
                                                  weight: .semibold))
                                Text("← " + side.sources
                                        .joined(separator: " · "))
                                    .font(.system(size: 9,
                                                  design: .monospaced))
                                    .foregroundStyle(Theme.faint)
                            }
                        }
                        Text("→ " + r.howToClose).font(.system(size: 10))
                            .foregroundStyle(Theme.warn)
                    } else {
                        HStack(spacing: 6) {
                            Text(r.value).font(.system(size: 12,
                                                       weight: .semibold))
                            Text(r.sources.joined(separator: " · "))
                                .font(.system(size: 9,
                                              design: .monospaced))
                                .foregroundStyle(Theme.faint)
                        }
                    }
                }
                .padding(.horizontal, 14).padding(.vertical, 5)
                .frame(maxWidth: .infinity, alignment: .leading)
                Divider().opacity(0.1)
            }
            recorder
        }
    }

    private var recorder: some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack(spacing: 6) {
                TextField(app.t("fabric", "生地名"), text: $newFabric)
                    .textFieldStyle(.roundedBorder).font(.system(size: 11))
                    .frame(width: 120)
                Picker("", selection: $newProp) {
                    Text("weight (g/m²)").tag("weight")
                    Text("thickness (mm)").tag("thickness")
                    Text("width (cm)").tag("width")
                    Text(app.t("composition", "組成")).tag("composition")
                }.labelsHidden().frame(width: 140)
                TextField(app.t("value", "値"), text: $newValue)
                    .textFieldStyle(.roundedBorder).font(.system(size: 11))
                    .frame(width: 80)
            }
            HStack(spacing: 8) {
                TextField(app.t("source (required)", "出典（必須）"),
                          text: $newSource)
                    .textFieldStyle(.roundedBorder).font(.system(size: 11))
                Button(app.t("Place", "置く")) {
                    Task {
                        said = await m.addFabric(fabric: newFabric,
                                                 prop: newProp,
                                                 value: newValue,
                                                 source: newSource)
                        if said == "ANSWER" { newValue = "" }
                    }
                }
                .font(.system(size: 11))
                .disabled(newFabric.trimmingCharacters(in: .whitespaces).isEmpty
                          || newValue.trimmingCharacters(in: .whitespaces).isEmpty)
            }
            if !said.isEmpty && said != "ANSWER" {
                Text(said).font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(Theme.bad)
            }
            Text(app.t("A property with no source is refused — an unsourced "
                       + "weight is not even a number somebody said.",
                       "出典の無い性質は断ります。出典の無い目付は、"
                       + "誰かが言った数字ですらありません。"))
                .font(.system(size: 9)).foregroundStyle(Theme.faint)
        }
        .padding(13)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.panel)
    }

    // MARK: 重ね着（引き算）

    /// 重ねて入るか。**布の落ち方は計算していない。**
    private var stack: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(app.t("LAYERING — subtraction, not drape",
                       "重ね着 — 引き算であって着装計算ではない")).railHead()
                .padding(.top, 8)
            HStack(spacing: 6) {
                TextField(app.t("inner girth", "内側の外周"), text: $inner)
                    .textFieldStyle(.roundedBorder).font(.system(size: 11))
                    .frame(width: 100)
                TextField(app.t("outer girth", "外側の内周"), text: $outer)
                    .textFieldStyle(.roundedBorder).font(.system(size: 11))
                    .frame(width: 100)
                TextField(app.t("layers (comma)", "層の生地（カンマ）"),
                          text: $layers)
                    .textFieldStyle(.roundedBorder).font(.system(size: 11))
                Button(app.t("Check", "見る")) {
                    Task {
                        await m.loadLayerFit(
                            inner: Double(inner) ?? 0,
                            outer: Double(outer) ?? 0,
                            fabrics: layers.split(separator: ",")
                                .map { $0.trimmingCharacters(in: .whitespaces) })
                    }
                }.font(.system(size: 11))
            }
            if let r = m.layerResult {
                if r.verdict == "ANSWER", let slack = r.slack {
                    HStack(spacing: 8) {
                        Text(String(format: "%+.1fcm", slack))
                            .font(.system(size: 16, weight: .semibold))
                            // **負を丸めない。** 入らない服は入らない。
                            .foregroundStyle(slack < 0 ? Theme.bad : Theme.ok)
                        Text(r.fits ? app.t("goes over", "入る")
                                    : app.t("does not go over", "入らない"))
                            .font(.system(size: 11))
                            .foregroundStyle(slack < 0 ? Theme.bad : Theme.ok)
                        Text(String(format: app.t("(layers add %.1fcm)",
                                                  "（層が %.1fcm 足す）"),
                                    r.thicknessAdds))
                            .font(.system(size: 10)).foregroundStyle(Theme.faint)
                    }
                    ForEach(Array(r.layers.enumerated()), id: \.offset) { _, l in
                        Text("· \(l.fabric): "
                             + (l.thickness.map { String(format: "%.1fmm", $0) }
                                ?? app.t("thickness unknown", "厚み不明"))
                             + (l.state == "CONTESTED"
                                ? app.t(" (split)", "（割れている）") : ""))
                            .font(.system(size: 10))
                            .foregroundStyle(l.thickness == nil ? Theme.warn
                                                                : Theme.dim)
                    }
                } else {
                    Text(r.missing.joined(separator: "、")
                         + app.t(" missing", " が足りません"))
                        .font(.system(size: 11)).foregroundStyle(Theme.warn)
                    Text("→ " + r.howToClose).font(.system(size: 10))
                        .foregroundStyle(Theme.warn)
                }
                Text(r.disclaimer).font(.system(size: 9))
                    .foregroundStyle(Theme.faint)
            }
        }
        .padding(.horizontal, 14).padding(.bottom, 10)
    }

    private func row(_ part: String, _ aspect: String) -> some View {
        let s = m.state(part, aspect)
        let o = m.rightsState(part, aspect)
        return VStack(alignment: .leading, spacing: 3) {
            HStack(spacing: 8) {
                Text(aspect).font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(Theme.dim)
                Text(Theme.symbol(s.state)).font(.system(size: 10))
                    .foregroundStyle(Theme.color(s.state))
                Text(s.value.isEmpty ? "—" : s.value)
                    .font(.system(size: 13, weight: .semibold))
                Spacer(minLength: 0)
                // 由来を同じ行に。**外から来た値ほどここが要る。**
                Text(RIGHTS.short(o.state))
                    .font(.system(size: 9, weight: .semibold))
                    .padding(.horizontal, 6).padding(.vertical, 1)
                    .background(Capsule().stroke(RIGHTS.colour(o.state),
                                                 lineWidth: 1))
                    .foregroundStyle(RIGHTS.colour(o.state))
            }
            if !s.sources.isEmpty {
                Text(s.sources.joined(separator: " · "))
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(Theme.faint)
            }
            if !s.adoptedBy.isEmpty {
                Text(app.t("adopted by ", "採用: ") + s.adoptedBy)
                    .font(.system(size: 10)).foregroundStyle(Theme.ok)
            }
            ForEach(Array(s.proposals.enumerated()), id: \.offset) { _, p in
                HStack(spacing: 6) {
                    Text(app.t("proposal", "提案")).font(.system(size: 9))
                        .foregroundStyle(Theme.faint)
                    Text(p.value).font(.system(size: 11))
                    Text(p.source).font(.system(size: 9,
                                                design: .monospaced))
                        .foregroundStyle(Theme.faint)
                    Button(app.t("adopt", "採用")) {
                        m.pendingAdopt = .init(part: part, aspect: aspect,
                                               value: p.value)
                    }.font(.system(size: 9))
                }
            }
            if !s.howToClose.isEmpty {
                Text("→ " + s.howToClose).font(.system(size: 10))
                    .foregroundStyle(Theme.warn)
            }
        }
        .padding(.horizontal, 14).padding(.vertical, 7)
        .frame(maxWidth: .infinity, alignment: .leading)
        .sheet(item: $m.pendingAdopt) { req in AdoptSheet(m: m, req: req) }
    }
}

// MARK: - 立体・ゆとり・サイズ展開

/// 立体の面。**着せない。比べる。**
///
/// 本当の着装は型紙を裁って縫い、生地の重さと曲げ剛性で落とす計算です。
/// 台帳には型紙が無く、生地の重さも未取得です。その状態で人台に巻きつけた
/// 絵を出せば、それは生成された見た目で、「こう着られる」と読まれます。
///
/// 代わりに引き算を出します。ゆとり = 服の周囲 − 体の周囲。作り手が実際に
/// 見る数字で、布の挙動を一切主張しません。
private struct SolidPanel: View {
    @ObservedObject var m: AtelierModel
    @EnvironmentObject var app: AppState
    @State private var said = ""
    @State private var sewFabric = ""

    private static let sizes = ["S", "M", "L", "XL"]

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Divider().opacity(0.25)
            HStack(spacing: 0) {
                solid.frame(width: 260)
                Divider().opacity(0.2)
                ScrollView {
                    VStack(alignment: .leading, spacing: 0) {
                        sewSection
                        Divider().opacity(0.2)
                        easeSection
                        Divider().opacity(0.2)
                        gradeSection
                    }
                }
            }
        }
        .background(Theme.bg)
        .task {
            await m.loadSolid()
            await m.loadEase()
            await m.loadBodyRef()
            await m.loadGrade()
            await m.loadFabrics()
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 10) {
                Text(app.t("Solid & ease", "立体とゆとり"))
                    .font(.system(size: 13, weight: .semibold))
                Spacer()
                Text(app.t("reference body", "基準体"))
                    .font(.system(size: 10)).foregroundStyle(Theme.faint)
                ForEach(Self.sizes, id: \.self) { s in
                    Text(s).font(.system(size: 11))
                        .padding(.horizontal, 9).padding(.vertical, 2)
                        .background(Capsule().stroke(
                            m.bodySize == s ? Theme.sel : Theme.line, lineWidth: 1))
                        .foregroundStyle(m.bodySize == s ? Theme.fg : Theme.dim)
                        .onTapGesture {
                            m.bodySize = s
                            Task { await m.loadEase() }
                        }
                }
                Button(app.t("Export OBJ…", "OBJで書き出す…")) { saveOBJ() }
                    .font(.system(size: 11))
                    .disabled(m.solidVertices.isEmpty)
            }
            // **知らないことを言わない。** ここが一番効く一行。
            if !m.solidDisclaimer.isEmpty {
                Text(m.solidDisclaimer).font(.system(size: 10))
                    .foregroundStyle(Theme.warn)
            }
            if !said.isEmpty {
                Text(said).font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(said == "ANSWER" ? Theme.ok : Theme.bad)
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.panel)
    }

    @ViewBuilder
    private var solid: some View {
        VStack(alignment: .leading, spacing: 8) {
            if m.solidVertices.isEmpty {
                Text(app.t("Nothing confirmed — no surface to build.",
                           "確定した項目がありません。面を作れません。"))
                    .font(.system(size: 11)).foregroundStyle(Theme.faint)
                    .padding(14)
            } else {
                SolidView(vertices: m.solidVertices, faces: m.solidFaces)
                    .frame(height: 300)
                VStack(alignment: .leading, spacing: 4) {
                    if !m.solidSkipped.isEmpty {
                        Text(app.t("not built (nothing confirmed): ",
                                   "確定が無いため作っていない: ")
                             + m.solidSkipped.joined(separator: "、"))
                            .font(.system(size: 10)).foregroundStyle(Theme.bad)
                    }
                    // **仮定を黙って形にしない。**
                    Text(app.t("depth is an assumed ratio of ",
                               "奥行きは仮定の比 ")
                         + String(format: "%.2f", m.solidAssumedDepth)
                         + app.t(" — not measured", "（実測ではない）"))
                        .font(.system(size: 10)).foregroundStyle(Theme.warn)
                    Text(m.solidAssumedWhy).font(.system(size: 9))
                        .foregroundStyle(Theme.faint)
                }
                .padding(.horizontal, 14)
            }
            Spacer(minLength: 0)
        }
    }

    // MARK: 縫って落とす

    /// **型紙を縫い合わせて落とす。** ここまでで唯一、この一着を落とす面。
    ///
    /// 立体(寸法から作る塊)は見るためのもので、この一着ではありません。
    /// ここは型紙の名前付き辺を縫って、実際に落とします。
    /// 検査に通らなければ**形を返しません**。
    @ViewBuilder
    private var sewSection: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 8) {
                Text(app.t("SEW & DRAPE — this garment",
                           "縫って落とす — この一着")).railHead()
                Spacer()
                Picker("", selection: $sewFabric) {
                    Text(app.t("pick a fabric", "生地を選ぶ")).tag("")
                    ForEach(fabricNames, id: \.self) { Text($0).tag($0) }
                }.labelsHidden().frame(width: 150)
                if m.sewBusy { ProgressView().controlSize(.small) }
                Button(app.t("Sew", "縫う")) {
                    Task { await m.sewAndDrape(fabric: sewFabric) }
                }
                .font(.system(size: 11))
                .disabled(sewFabric.isEmpty || m.sewBusy)
            }
            .padding(.top, 10).padding(.trailing, 14)

            Text(app.t("Seams come from the pattern's named edges — not from "
                       + "proximity. The shape is withheld unless the checks "
                       + "pass.",
                       "縫い目は型紙の名前付き辺から決まります（近さでは"
                       + "決めません）。検査に通らなければ形は返しません。"))
                .font(.system(size: 10)).foregroundStyle(Theme.faint)
                .padding(.horizontal, 14).padding(.top, 2)

            if !m.sewVerdict.isEmpty {
                ForEach(m.sewSeams) { s in
                    HStack(spacing: 8) {
                        Text(s.seam).font(.system(size: 10,
                                                  design: .monospaced))
                            .foregroundStyle(Theme.dim)
                        Text(s.state == "SEWN"
                             ? app.t("\(s.stitches) stitches",
                                     "\(s.stitches) 針")
                             : s.state)
                            .font(.system(size: 10))
                            .foregroundStyle(s.state == "SEWN" ? Theme.ok : Theme.bad)
                        if let a = s.lengthA, let b = s.lengthB {
                            Text(String(format: "%.1f / %.1f cm", a, b))
                                .font(.system(size: 9,
                                              design: .monospaced))
                                .foregroundStyle(Theme.faint)
                        }
                        Spacer(minLength: 0)
                    }
                    .padding(.horizontal, 14).padding(.vertical, 3)
                }

                ForEach(m.sewChecks) { c in
                    HStack(spacing: 8) {
                        Text(checkLabel(c.name))
                            .font(.system(size: 11)).frame(width: 110,
                                                           alignment: .leading)
                        Text(c.verdict == "ANSWER"
                             ? app.t("passed", "通った") : c.verdict)
                            .font(.system(size: 10, weight: .semibold))
                            .foregroundStyle(c.verdict == "ANSWER"
                                             ? Theme.ok : Theme.bad)
                        if let d = c.difference {
                            Text(String(format: "%.2f", d)
                                 + (c.tolerance.map {
                                     String(format: " / 許容 %.2f", $0) } ?? ""))
                                .font(.system(size: 9,
                                              design: .monospaced))
                                .foregroundStyle(Theme.faint)
                        }
                        if !c.detail.isEmpty {
                            Text(c.detail).font(.system(size: 9,
                                                        design: .monospaced))
                                .foregroundStyle(Theme.faint)
                        }
                        Spacer(minLength: 0)
                    }
                    .padding(.horizontal, 14).padding(.vertical, 3)

                    if !c.toleranceFrom.isEmpty {
                        Text(app.t("tolerance: \(c.toleranceFrom)",
                                   "許容の出どころ: \(c.toleranceFrom)"))
                            .font(.system(size: 9)).foregroundStyle(Theme.faint)
                            .padding(.leading, 132)
                    }
                    // **揺れと別形を分けて言う。** 「合わない」だけでは
                    // 次に何を触ればよいか分からない。
                    if let same = c.sameShapeMoved {
                        Text(same
                             ? app.t("the same shape, moved", "同じ形が動いた")
                             : app.t("a different shape — not a swing "
                                     + "(inner distances differ by "
                                     + String(format: "%.1f", c.shapeDifference ?? 0)
                                     + " cm)",
                                     "別の形です。揺れではありません"
                                     + "（形の中の距離が "
                                     + String(format: "%.1f", c.shapeDifference ?? 0)
                                     + " cm 違う）"))
                            .font(.system(size: 9))
                            .foregroundStyle(same ? Theme.dim : Theme.warn)
                            .padding(.leading, 132)
                    }
                    if !c.byPiece.isEmpty {
                        Text(c.byPiece.sorted { $0.key < $1.key }
                            .map { String(format: "%@ %.1f", $0.key, $0.value) }
                            .joined(separator: "   "))
                            .font(.system(size: 9, design: .monospaced))
                            .foregroundStyle(Theme.faint)
                            .padding(.leading, 132)
                    }
                }

                if !m.sewPoints.isEmpty {
                    SewnView(points: m.sewPoints, owner: m.sewOwner,
                             edges: m.sewEdges)
                        .frame(height: 220)
                        .padding(.horizontal, 14).padding(.top, 6)
                } else if !m.sewWhyNoShape.isEmpty {
                    // **形を返していない理由を書く。** 空欄は「まだ押して
                    // いない」と読まれる。
                    Text(m.sewWhyNoShape).font(.system(size: 10))
                        .foregroundStyle(Theme.warn)
                        .padding(.horizontal, 14).padding(.top, 4)
                    if !m.sewShapes.isEmpty {
                        Text(app.t("all \(m.sewShapes.count) shapes are "
                                   + "returned — none is chosen",
                                   "\(m.sewShapes.count) つの形を全部返して"
                                   + "います。どれも選んでいません"))
                            .font(.system(size: 10)).foregroundStyle(Theme.dim)
                            .padding(.horizontal, 14)
                        HStack(spacing: 10) {
                            ForEach(Array(m.sewShapes.enumerated()),
                                    id: \.offset) { i, sh in
                                VStack(spacing: 2) {
                                    SewnView(points: sh, owner: m.sewOwner,
                                              edges: m.sewEdges)
                                        .frame(width: 140, height: 150)
                                    Text(app.t("start \(i + 1)",
                                               "始点 \(i + 1)"))
                                        .font(.system(size: 9))
                                        .foregroundStyle(Theme.faint)
                                }
                            }
                        }
                        .padding(.horizontal, 14).padding(.top, 4)
                    }
                }
            }
        }
        .padding(.bottom, 8)
    }

    private var fabricNames: [String] {
        Array(Set(m.fabricRows.filter { $0.state != "UNKNOWN_NOT_RECORDED" }
            .map(\.fabric))).sorted()
    }

    private func checkLabel(_ key: String) -> String {
        switch key {
        case "seam_closed": return app.t("seam closes", "縫い目が閉じる")
        case "order": return app.t("order invariant", "順序不変")
        case "starts": return app.t("multi-start", "多点始動")
        default: return key
        }
    }

    private var easeSection: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(app.t("EASE — garment minus body", "ゆとり — 服 − 体"))
                .railHead().padding(.top, 10)
            Text(m.easeDisclaimer).font(.system(size: 10))
                .foregroundStyle(Theme.warn)
                .padding(.horizontal, 14).padding(.bottom, 6)
            // **何から引いた差なのかを画面に出す。** 基準体が見えないと、
            // ゆとりは出どころの無い数字になる。
            if !m.bodyRef.isEmpty {
                Text(m.bodyRef.sorted { $0.key < $1.key }
                    .map { String(format: "%@ %.1f", $0.key, $0.value) }
                    .joined(separator: "   "))
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(Theme.faint)
                    .padding(.horizontal, 14)
                Text(m.bodyRefNote).font(.system(size: 9))
                    .foregroundStyle(Theme.faint)
                    .padding(.horizontal, 14).padding(.bottom, 6)
            }
            ForEach(m.easeRows) { r in
                HStack(spacing: 10) {
                    Text(r.spot).font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(Theme.dim)
                        .frame(width: 110, alignment: .leading)
                    if let e = r.ease, let g = r.garment {
                        Text(String(format: "%.1f − %.1f", g, r.body))
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(Theme.faint)
                        Text(String(format: "%+.1f%@", e, r.unit))
                            .font(.system(size: 13, weight: .semibold))
                            // 負のゆとりは丸めない。入らない服は入らない。
                            .foregroundStyle(e < 0 ? Theme.bad : Theme.ok)
                        if r.fromDerived {
                            Text(app.t("(from a derived length)",
                                       "（計算値の上のゆとり）"))
                                .font(.system(size: 9))
                                .foregroundStyle(Theme.warn)
                        }
                    } else {
                        Text(app.t("no basis", "基準なし"))
                            .font(.system(size: 11)).foregroundStyle(Theme.faint)
                        Text("→ " + r.howToClose).font(.system(size: 10))
                            .foregroundStyle(Theme.warn)
                    }
                    Spacer(minLength: 0)
                }
                .padding(.horizontal, 14).padding(.vertical, 5)
                Divider().opacity(0.12)
            }
        }
    }

    private var gradeSection: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(app.t("GRADED SIZES — not measurements",
                       "サイズ展開 — 実測ではない")).railHead().padding(.top, 12)
            ForEach(m.gradeSizes, id: \.self) { size in
                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 8) {
                        Text(size).font(.system(size: 12, weight: .semibold))
                        if size == m.gradeBase {
                            Text(app.t("base (measured)", "基準（実測）"))
                                .font(.system(size: 9))
                                .foregroundStyle(Theme.ok)
                        }
                        Spacer(minLength: 0)
                    }
                    ForEach(m.gradeTable[size] ?? []) { r in
                        HStack(spacing: 8) {
                            Text(r.name.isEmpty ? r.spot : r.name)
                                .font(.system(size: 10))
                                .foregroundStyle(Theme.dim)
                                .frame(width: 90, alignment: .leading)
                            if let v = r.value {
                                Text(String(format: "%.1f%@", v, r.unit))
                                    .font(.system(size: 11,
                                                  weight: .semibold))
                                    .foregroundStyle(r.state == "MEASURED"
                                                     ? Theme.fg : Theme.warn)
                                Text(Theme.symbol(r.state))
                                    .font(.system(size: 9))
                                    .foregroundStyle(Theme.color(r.state))
                                if !r.from.isEmpty {
                                    Text("← " + r.from)
                                        .font(.system(size: 9,
                                                      design: .monospaced))
                                        .foregroundStyle(Theme.faint)
                                }
                            } else {
                                Text("→ " + r.howToClose)
                                    .font(.system(size: 10))
                                    .foregroundStyle(Theme.warn)
                            }
                            Spacer(minLength: 0)
                        }
                    }
                }
                .padding(.horizontal, 14).padding(.vertical, 6)
                Divider().opacity(0.12)
            }
        }
        .padding(.bottom, 14)
    }

    private func saveOBJ() {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = "proportion-block.obj"
        panel.message = AppLanguage.shared.t(
            "Save the block (marked as generated; not a drape simulation)",
            "立体を保存する（生成物の印が付きます。着装計算ではありません）")
        guard panel.runModal() == .OK, let url = panel.url else { return }
        Task { said = await m.saveSolid(to: url.path) }
    }
}

/// 立体を描く。**エンジンが返した頂点と面をそのまま置く。**
/// ここで滑らかにしたり穴を塞いだりしない — 足した面は誰も観測していない面。
private struct SolidView: NSViewRepresentable {
    let vertices: [[Double]]
    let faces: [[Int]]

    func makeNSView(context: Context) -> SCNView {
        let v = SCNView()
        v.allowsCameraControl = true
        v.autoenablesDefaultLighting = true
        v.backgroundColor = .clear
        return v
    }

    func updateNSView(_ v: SCNView, context: Context) {
        let scene = SCNScene()
        if let node = node() { scene.rootNode.addChildNode(node) }
        v.scene = scene
    }

    private func node() -> SCNNode? {
        guard !vertices.isEmpty, !faces.isEmpty else { return nil }
        let points = vertices.map {
            SCNVector3(CGFloat($0[0]), CGFloat($0[1]), CGFloat($0[2]))
        }
        var indices: [Int32] = []
        for f in faces where f.count == 3 {
            indices.append(contentsOf: f.map { Int32($0) })
        }
        let source = SCNGeometrySource(vertices: points)
        let element = SCNGeometryElement(
            data: Data(bytes: indices,
                       count: indices.count * MemoryLayout<Int32>.size),
            primitiveType: .triangles,
            primitiveCount: indices.count / 3,
            bytesPerIndex: MemoryLayout<Int32>.size)
        let geometry = SCNGeometry(sources: [source], elements: [element])
        let mat = SCNMaterial()
        mat.diffuse.contents = NSColor(white: 0.72, alpha: 1)
        mat.isDoubleSided = true          // 服は筒。裏からも見える
        geometry.materials = [mat]
        let node = SCNNode(geometry: geometry)
        // 原点まわりに収める。**形は変えない** — 見る位置を変えるだけ。
        let ys = vertices.map { $0[1] }
        node.position = SCNVector3(0, CGFloat(-(ys.min()! + ys.max()!) / 2), 0)
        let scale = 2.4 / CGFloat(max(ys.max()! - ys.min()!, 1))
        node.scale = SCNVector3(scale, scale, scale)
        return node
    }
}

/// 型紙のピースを並べて描く。**エンジンが返した座標をそのまま引く。**
private struct PatternFigure: View {
    let pieces: [AtelierModel.PatternPiece]
    /// 辺の折れ線は engine が返したものをそのまま使う。**輪郭のどこが
    /// その辺かを画面側で引き直さない** — 引き直せば必ずずれる。
    private func edgePoints(_ p: AtelierModel.PatternPiece,
                            _ edge: String, _ shift: CGFloat) -> [CGPoint] {
        (p.edges[edge] ?? []).map {
            CGPoint(x: $0.x + shift, y: $0.y + 4)
        }
    }

    var body: some View {
        GeometryReader { g in
            let laid = layout()
            let s = min(g.size.width / max(laid.width, 1),
                        g.size.height / max(laid.height, 1))
            ZStack(alignment: .topLeading) {
                ForEach(Array(laid.shapes.enumerated()), id: \.offset) { _, sh in
                    // 裁ち切り線は破線。**裁つのはこちら。**
                    if !sh.cut.isEmpty {
                        poly(sh.cut, s)
                            .stroke(Theme.bad,
                                    style: StrokeStyle(lineWidth: 0.6,
                                                       dash: [3, 2]))
                    }
                    poly(sh.points, s).stroke(Theme.dim, lineWidth: 0.9)
                    if sh.grain.count == 2 {
                        Path { p in
                            p.move(to: CGPoint(x: sh.grain[0].x * s,
                                               y: sh.grain[0].y * s))
                            p.addLine(to: CGPoint(x: sh.grain[1].x * s,
                                                  y: sh.grain[1].y * s))
                        }.stroke(Theme.ok, lineWidth: 0.8)
                    }
                    // **合印は実物 2.5mm。** 画面ではそのままだと見えない
                    // ので、印の位置に丸を打つ。深さは表で出す。
                    ForEach(Array(sh.notches.enumerated()),
                            id: \.offset) { _, n in
                        Circle()
                            .fill(n.double ? Theme.sel : Color(Theme.line))
                            .frame(width: n.double ? 5 : 3.5,
                                   height: n.double ? 5 : 3.5)
                            .position(x: n.at.x * s, y: n.at.y * s)
                    }
                }
            }
        }
    }

    private struct NotchDot { var at: CGPoint; var double: Bool }
    private struct Placed {
        var points: [CGPoint]
        var cut: [CGPoint] = []
        var grain: [CGPoint] = []
        var notches: [NotchDot] = []
    }

    private func poly(_ pts: [CGPoint], _ s: CGFloat) -> Path {
        Path { p in
            guard let first = pts.first else { return }
            p.move(to: CGPoint(x: first.x * s, y: first.y * s))
            for pt in pts.dropFirst() {
                p.addLine(to: CGPoint(x: pt.x * s, y: pt.y * s))
            }
            p.closeSubpath()
        }
    }

    /// 合印の弧長を、辺の折れ線上の点に直す。
    private func point(on pts: [CGPoint], arc: CGFloat) -> CGPoint? {
        guard pts.count >= 2 else { return nil }
        var run: CGFloat = 0
        for (a, b) in zip(pts, pts.dropFirst()) {
            let d = hypot(b.x - a.x, b.y - a.y)
            if run + d >= arc || b == pts.last {
                let t = d == 0 ? 0 : min(max((arc - run) / d, 0), 1)
                return CGPoint(x: a.x + (b.x - a.x) * t,
                               y: a.y + (b.y - a.y) * t)
            }
            run += d
        }
        return pts.last
    }

    /// 横に並べる。**形は変えない** — 置く位置だけ動かす。
    private func layout() -> (shapes: [Placed], width: CGFloat,
                              height: CGFloat) {
        var x: CGFloat = 4
        var out: [Placed] = []
        var maxY: CGFloat = 0
        for p in pieces {
            guard !p.outline.isEmpty else { continue }
            let minX = p.outline.map(\.x).min() ?? 0
            let maxX = p.outline.map(\.x).max() ?? 0
            let shift = x - minX
            func move(_ q: [CGPoint]) -> [CGPoint] {
                q.map { CGPoint(x: $0.x + shift, y: $0.y + 4) }
            }
            let moved = move(p.outline)
            // 合印は辺ごとの弧長。ここでは輪郭上の弧長として置き直す。
            var dots: [NotchDot] = []
            for n in p.notches {
                if let q = point(on: edgePoints(p, n.edge, shift),
                                 arc: CGFloat(n.arcCm)) {
                    dots.append(NotchDot(at: q, double: n.kind == "double"))
                }
            }
            out.append(Placed(points: moved, cut: move(p.cutLine),
                              grain: move(p.grain), notches: dots))
            x += (maxX - minX) + 8
            maxY = max(maxY, ((p.cutLine.isEmpty ? p.outline : p.cutLine)
                .map(\.y).max() ?? 0) + 8)
        }
        return (out, x, maxY)
    }
}

/// 縫って落とした服を描く。**ピースごとに色を変える** — どの型紙が
/// どこに来たかが分からないと、直すときに触る先が決まらない。
private struct SewnView: NSViewRepresentable {
    let points: [[Double]]
    let owner: [String]
    /// メッシュの辺。**布は面なので、点だけでは読めない。**
    var edges: [[Int]] = []

    func makeNSView(context: Context) -> SCNView {
        let v = SCNView()
        v.allowsCameraControl = true
        v.autoenablesDefaultLighting = true
        v.backgroundColor = .clear
        return v
    }

    func updateNSView(_ v: SCNView, context: Context) {
        let scene = SCNScene()
        let colours: [String: NSColor] = [
            "前身頃": NSColor(red: 0.55, green: 0.72, blue: 0.95, alpha: 1),
            "後身頃": NSColor(red: 0.95, green: 0.72, blue: 0.55, alpha: 1),
            "袖": NSColor(red: 0.62, green: 0.90, blue: 0.68, alpha: 1),
        ]
        let ys = points.compactMap { $0.count > 1 ? $0[1] : nil }
        guard let lo = ys.min(), let hi = ys.max() else { return }
        let scale = 2.2 / CGFloat(max(hi - lo, 1))
        let mid = CGFloat((lo + hi) / 2)
        if edges.isEmpty {
            for (i, p) in points.enumerated() where p.count == 3 {
                let dot = SCNSphere(radius: 0.035 / scale)
                let mat = SCNMaterial()
                mat.diffuse.contents = colours[i < owner.count ? owner[i] : ""]
                    ?? NSColor.gray
                dot.materials = [mat]
                let node = SCNNode(geometry: dot)
                node.position = SCNVector3(CGFloat(p[0]), CGFloat(p[1]),
                                           CGFloat(p[2]))
                scene.rootNode.addChildNode(node)
            }
        } else {
            // ピースごとに線でまとめて描く。色は出身のまま —
            // どの型紙がどこに来たかが分からないと直せない。
            var byPiece: [String: [Int32]] = [:]
            for e in edges where e.count == 2 {
                let a = e[0], b = e[1]
                guard a < points.count, b < points.count else { continue }
                let name = a < owner.count ? owner[a] : ""
                byPiece[name, default: []] += [Int32(a), Int32(b)]
            }
            let verts = points.filter { $0.count == 3 }.map {
                SCNVector3(CGFloat($0[0]), CGFloat($0[1]), CGFloat($0[2]))
            }
            guard verts.count == points.count else { return }
            let source = SCNGeometrySource(vertices: verts)
            for (name, idx) in byPiece {
                let data = Data(bytes: idx,
                                count: idx.count * MemoryLayout<Int32>.size)
                let element = SCNGeometryElement(
                    data: data, primitiveType: .line,
                    primitiveCount: idx.count / 2,
                    bytesPerIndex: MemoryLayout<Int32>.size)
                let geo = SCNGeometry(sources: [source], elements: [element])
                let mat = SCNMaterial()
                mat.diffuse.contents = colours[name] ?? NSColor.gray
                mat.lightingModel = .constant
                geo.materials = [mat]
                scene.rootNode.addChildNode(SCNNode(geometry: geo))
            }
        }
        let root = SCNNode()
        for child in scene.rootNode.childNodes { root.addChildNode(child) }
        scene.rootNode.childNodes.forEach { $0.removeFromParentNode() }
        root.position = SCNVector3(0, -mid * scale, 0)
        root.scale = SCNVector3(scale, scale, scale)
        scene.rootNode.addChildNode(root)
        v.scene = scene
    }
}
