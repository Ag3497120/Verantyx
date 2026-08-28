import SwiftUI
import SceneKit

// MARK: - PatternRunSection
//
// Task S の brief そのもの: 「判断リスト」「着せた形」「平らな型紙」を
// 並べて見せる。この三つは engine 側に既にある――
//
//   photoloset/decisions.py     collect(result) が measured/inferred/
//                                proposed/blocked を、basis と path 付きで返す
//   photoloset/repairs.py       make_sewable() が縫えるまでの記録を返す
//   mannequin.dress / pattern   3D の人台と平らな型紙、どちらも既存の扉
//
// **ここでは photoloset (Python) を一切触っていない。** 触れて分かった
// こと三つ:
//
//   1. `photo_to_pattern.py` は既に `result["decisions"]` に
//      `decisions.collect(result)` を埋め込んでいる (`_p2p.run` を実測
//      して確認)。`mcp.py` の `photo_pattern` はその dict をそのまま
//      json にして返すので、**判断リストは今日から呼べる** ――
//      新しい扉を足す必要が無かった。この画面が初めてそれを呼ぶ。
//   2. `repairs.py`(修復の記録)はどの `@tool` からも一度も呼ばれて
//      いない。台帳を経由する `ledger_bridge.py` の `land_structure` /
//      `land_photo_to_pattern` も同じく、どこからも呼ばれていない ――
//      だから「提案を選ぶ」は台帳に届かない。ここで嘘の緑を出さず、
//      その二つを正直に「まだ配線されていない」と言う(brief 自身の
//      逃げ道: 「never a dead control that looks live」)。
//   3. `mannequin_dress` と `GarmentOutline`(輪郭抽出)はこのアプリの
//      どこからも呼ばれていなかった――この画面が初めて使う、正真正銘
//      動く経路。
//
// 三段の色は `AttentionOverviewView.Card.Kind` をそのまま使う――
// 四色目は発明しない(owner の brief の指示通り)。
struct PatternRunSection: View {
    @EnvironmentObject var app: AppState
    @ObservedObject var m: AtelierModel
    @StateObject private var intake = AtelierIntake.shared

    @State private var selectedClipPath: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            header
            photoPicker
            runStatus
            if m.patternRunVerdict == "ANSWER" { decisionList }
            repairTranscriptCard
            sideBySide
        }
        .task {
            await intake.restore()
            if selectedClipPath == nil { selectedClipPath = intake.clips.first?.path }
            await m.loadDressedForm()
        }
    }

    // MARK: - Header + photo picker

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(app.t("Pattern run", "型紙の実行"))
                .font(.system(size: 15, weight: .bold))
                .foregroundStyle(Theme.fg)
            Text(app.t(
                "Pick a photo — the engine reads its outline through structure → silhouette → panels. Below: what it decided, what it's still asking, the last repair attempt, and the dressed form next to the flat pattern.",
                "写真を選ぶと、engine が輪郭を構造 → シルエット → パネルまで読みます。下には、決まったこと・まだ聞いていること・直近の修復・着せた形と平らな型紙を並べて出します。"))
                .font(.system(size: 11.5))
                .foregroundStyle(Theme.dim)
        }
    }

    private var photoPicker: some View {
        VStack(alignment: .leading, spacing: 6) {
            if intake.clips.isEmpty {
                Button(app.t("Add a photo…", "写真を追加…")) {
                    Task {
                        await intake.pickAndIngest()
                        if selectedClipPath == nil {
                            selectedClipPath = intake.clips.first?.path
                        }
                    }
                }
                .buttonStyle(.plain)
                .font(.system(size: 11.5, weight: .semibold))
                .foregroundStyle(Theme.sel)
            } else {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(intake.clips) { clip in
                            Button {
                                selectedClipPath = clip.path
                                Task { await m.runPatternDecisions(imagePath: clip.path) }
                            } label: {
                                Text((clip.sourcePath as NSString).lastPathComponent
                                     + (clip.mark.isEmpty ? "" : " · \(clip.mark)"))
                                    .font(.system(size: 10.5,
                                                 weight: selectedClipPath == clip.path ? .bold : .regular))
                                    .padding(.horizontal, 8).padding(.vertical, 4)
                                    .background(selectedClipPath == clip.path
                                                ? Theme.sel.opacity(0.18) : Theme.panel,
                                               in: RoundedRectangle(cornerRadius: 6))
                                    .foregroundStyle(selectedClipPath == clip.path
                                                     ? Theme.sel : Theme.dim)
                            }
                            .buttonStyle(.plain)
                        }
                        Button(app.t("+ Add", "+ 追加")) {
                            Task { await intake.pickAndIngest() }
                        }
                        .buttonStyle(.plain)
                        .font(.system(size: 10.5))
                        .foregroundStyle(Theme.faint)
                    }
                }
            }
        }
    }

    // MARK: - Run status / refusal

    @ViewBuilder
    private var runStatus: some View {
        if !m.patternRunOutlineVerdict.isEmpty {
            refusalBanner(app.t("The photo didn't yield an outline.",
                                "この写真からは輪郭が取れませんでした。"),
                          m.patternRunOutlineVerdict, m.patternRunHowToClose, nil)
        } else if m.patternRunBusy {
            HStack(spacing: 8) {
                ProgressView().controlSize(.small)
                Text(app.t("Reading the photo through structure → pattern…",
                           "写真を構造 → 型紙まで読んでいます…"))
                    .font(.system(size: 11.5))
                    .foregroundStyle(Theme.dim)
            }
        } else if !m.patternRunVerdict.isEmpty && m.patternRunVerdict != "ANSWER" {
            refusalBanner(app.t("The pattern run stopped.", "型紙の実行が止まりました。"),
                          m.patternRunVerdict, m.patternRunHowToClose, m.patternRunFailedHop)
        }
    }

    private func refusalBanner(_ title: String, _ verdict: String,
                               _ howToClose: String, _ failedHop: String?) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 6) {
                Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(Theme.bad)
                Text(title).font(.system(size: 12, weight: .semibold)).foregroundStyle(Theme.fg)
            }
            Text(verdict).font(.system(size: 10, design: .monospaced)).foregroundStyle(Theme.faint)
                .textSelection(.enabled)
            if let failedHop, !failedHop.isEmpty {
                Text(app.t("stopped at: ", "止まった場所: ") + failedHop)
                    .font(.system(size: 10.5)).foregroundStyle(Theme.faint)
            }
            if !howToClose.isEmpty {
                Text(howToClose).font(.system(size: 11.5)).foregroundStyle(Theme.dim)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.bad.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
    }

    // MARK: - Decision list (photoloset/decisions.py, read verbatim)

    private var decisionList: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(app.t("What this run found", "この実行が見つけたこと"))
                    .font(.system(size: 13, weight: .bold)).foregroundStyle(Theme.fg)
                Spacer()
            }
            if !m.decisionCounts.isEmpty {
                HStack(spacing: 10) {
                    ForEach(["blocked", "defects", "proposed", "inferred", "measured"],
                           id: \.self) { key in
                        if let c = m.decisionCounts[key], c > 0 {
                            Text("\(tierWord(for: key)): \(c)")
                                .font(.system(size: 9.5, design: .monospaced))
                                .foregroundStyle(Theme.faint)
                        }
                    }
                }
            }
            if !m.decisionNote.isEmpty {
                Text(m.decisionNote).font(.system(size: 10.5)).foregroundStyle(Theme.faint)
            }
            if m.decisionRows.isEmpty {
                Text(app.t(
                    "Nothing landed in any tier — every landmark this run touched resolved from geometry alone, with nothing this list classifies as assumed, blocked, or contract-broken.",
                    "どの段にも何もありません — この実行が触れた landmark は全て幾何だけで解決し、このリストが「仮定した」「止まった」「契約違反」に分類するものはありませんでした。"))
                    .font(.system(size: 11.5)).foregroundStyle(Theme.dim)
            } else {
                ForEach(m.decisionRows) { row in decisionCard(row) }
            }
        }
    }

    private func kind(for tier: AtelierModel.DecisionRow.Tier) -> AttentionOverviewView.Card.Kind {
        switch tier {
        case .blocked, .defect: return .needsCheck
        case .proposed, .inferred: return .estimated
        case .measured: return .confirmed
        }
    }

    private func tierWord(_ tier: AtelierModel.DecisionRow.Tier) -> String {
        switch tier {
        case .blocked: return app.t("NEEDS CHECK", "要確認")
        case .defect: return app.t("CONTRACT ISSUE", "契約不備")
        case .proposed: return app.t("PROPOSED", "未決")
        case .inferred: return app.t("ESTIMATED", "推定")
        case .measured: return app.t("AUTO-CHECKED", "自動確認")
        }
    }

    /// `decisions.collect()` の counts のキー("blocked"/"defects"/…、
    /// 複数形のものもある)を、行の tier と同じ言葉に合わせるだけ。
    private func tierWord(for countsKey: String) -> String {
        switch countsKey {
        case "blocked": return tierWord(.blocked)
        case "defects": return tierWord(.defect)
        case "proposed": return tierWord(.proposed)
        case "inferred": return tierWord(.inferred)
        case "measured": return tierWord(.measured)
        default: return countsKey
        }
    }

    @ViewBuilder
    private func decisionCard(_ row: AtelierModel.DecisionRow) -> some View {
        let k = kind(for: row.tier)
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                Image(systemName: k.icon).font(.system(size: 10, weight: .bold))
                Text(tierWord(row.tier)).font(.system(size: 9, weight: .bold)).tracking(0.4)
            }
            .foregroundStyle(k.color)

            Text(row.title).font(.system(size: 12.5, weight: .semibold)).foregroundStyle(Theme.fg)

            if !row.verdict.isEmpty {
                Text(row.verdict).font(.system(size: 9.5, design: .monospaced))
                    .foregroundStyle(Theme.faint).textSelection(.enabled)
            }
            if !row.why.isEmpty {
                Text(row.why).font(.system(size: 11.5)).foregroundStyle(Theme.dim)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if row.tier == .defect {
                // **契約違反そのもの。** engine が言った理由をそのまま出す
                // ――ここで「大丈夫です」に丸めない。
                if !row.reason.isEmpty {
                    Text(row.reason).font(.system(size: 11)).foregroundStyle(Theme.bad)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if !row.module.isEmpty {
                    Text(app.t("from ", "由来: ") + row.module)
                        .font(.system(size: 10)).foregroundStyle(Theme.faint)
                }
            }
            if row.tier == .inferred {
                if !row.assumedValue.isEmpty {
                    Text(app.t("Derived value: ", "推定値: ") + row.assumedValue)
                        .font(.system(size: 12, weight: .semibold)).foregroundStyle(Theme.warn)
                        .textSelection(.enabled)
                }
                if !row.basis.isEmpty {
                    Text(row.basis).font(.system(size: 11)).foregroundStyle(Theme.dim)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            if row.tier == .proposed {
                proposedQuestion(row)
            }
            if row.tier == .measured, !row.assumedValue.isEmpty {
                Text(row.assumedValue).font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Theme.ok).textSelection(.enabled)
            }
            if !row.howToClose.isEmpty {
                Text(app.t("How to close it: ", "閉じるには: ") + row.howToClose)
                    .font(.system(size: 10.5)).foregroundStyle(Theme.faint)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if !row.rawText.isEmpty {
                Text(row.rawText).font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(Theme.faint).textSelection(.enabled).lineLimit(6)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.panel, in: RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(k.color.opacity(0.3), lineWidth: 1))
    }

    /// 「一つの質問、選択肢はボタン」――owner の brief そのまま。
    /// **選んでも台帳には届かない**: `ledger_bridge.land_photo_to_pattern`
    /// をどの `@tool` も呼んでいないので、この提案は台帳の外にある。
    /// `garment_adopt` を黙って呼んで何も起きないボタンにはしない――
    /// 押したら正直にそう言う(brief の逃げ道をそのまま使う)。
    @ViewBuilder
    private func proposedQuestion(_ row: AtelierModel.DecisionRow) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(app.t("Which is it?", "どちらですか?"))
                .font(.system(size: 11.5, weight: .semibold)).foregroundStyle(Theme.fg)
            ForEach(row.alternatives) { alt in
                VStack(alignment: .leading, spacing: 2) {
                    Button {
                        m.attemptAdopt(row, value: alt.value)
                    } label: {
                        HStack(alignment: .top, spacing: 6) {
                            Image(systemName: "circle").font(.system(size: 9))
                                .foregroundStyle(Theme.warn)
                            VStack(alignment: .leading, spacing: 1) {
                                Text(alt.value).font(.system(size: 12, weight: .medium))
                                    .foregroundStyle(Theme.fg)
                                if !alt.basis.isEmpty {
                                    Text(alt.basis).font(.system(size: 10))
                                        .foregroundStyle(Theme.faint)
                                        .fixedSize(horizontal: false, vertical: true)
                                }
                            }
                        }
                    }
                    .buttonStyle(.plain)
                    if m.decisionAdoptAttempt == "\(row.id)::\(alt.value)" {
                        Text(app.t(
                            "Not wired to the ledger yet — geometric proposals from this photo run aren't placed in the ledger by the engine (ledger_bridge is never called), so choosing here can't adopt anything.",
                            "台帳にはまだ配線されていません — この写真の実行から出た提案は engine 側で台帳へ置かれていない(ledger_bridge がどこからも呼ばれていない)ので、ここで選んでも採用にはなりません。"))
                            .font(.system(size: 10)).foregroundStyle(Theme.warn)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
        }
        .padding(.top, 2)
    }

    // MARK: - Repair transcript (photoloset/repairs.py — not wired yet)

    private var repairTranscriptCard: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                Image(systemName: "circle.dashed").font(.system(size: 11, weight: .bold))
                Text(app.t("NOT CONNECTED", "未接続"))
                    .font(.system(size: 9.5, weight: .bold)).tracking(0.4)
            }
            .foregroundStyle(Theme.faint)
            Text(app.t("Repair transcript", "修復の記録"))
                .font(.system(size: 13, weight: .bold)).foregroundStyle(Theme.fg)
            Text(app.t(
                "The engine has a repair catalogue (repairs.py: diagnose / make_sewable) that changes a pattern until it's sewable and records every round it takes — what fired, what changed, what it cost. It isn't exposed as a tool over this app's engine connection yet, so there is nothing real to show here. When it is, each line here will name the round, what changed, and what it cost, in order.",
                "engine には型紙が縫えるまで変え、その全過程を記録する修復のカタログ(repairs.py の diagnose / make_sewable — 何が発火し、何を変え、何を払ったか)がありますが、このアプリの engine 接続にはまだ扉として出ていません。ここに出す実物はまだありません。配線されたら、各回・変えたこと・払った代償をここに順番に出します。"))
                .font(.system(size: 11)).foregroundStyle(Theme.dim)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.panel, in: RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(Theme.faint.opacity(0.3), lineWidth: 1))
    }

    // MARK: - Dressed form + flat pattern, side by side

    /// **`ViewThatFits` に選ばせる.** 自前の GeometryReader + @State で
    /// 幅を測って HStack/VStack を切り替える版を先に書いたが、実機で
    /// 測定値が 0 に落ち着いて動かなくなる自己参照を踏んだ――測る側と
    /// 測られて形を変える側が同じビューの木の中にあると、SceneKit /
    /// GeometryReader を持つ子の「望ましい幅」の問い合わせが絡んで
    /// 安定しなかった。`ViewThatFits` は SwiftUI 自身が「この案は
    /// 入るか」を候補ごとに聞く組み込みの仕組みで、自前の状態を持たない
    /// ――各ペインに `minWidth` を与える(伸縮しか言わない裸の
    /// GeometryReader/NSViewRepresentable には判定基準の「望ましい幅」
    /// が無いので)だけで安定して動く。
    private var sideBySide: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(app.t("The dressed form and the flat pattern", "着せた形と平らな型紙"))
                .font(.system(size: 13, weight: .bold)).foregroundStyle(Theme.fg)
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .top, spacing: 12) {
                    dressedPane.frame(maxWidth: .infinity)
                    patternPane.frame(maxWidth: .infinity)
                }
                VStack(alignment: .leading, spacing: 12) {
                    dressedPane
                    patternPane
                }
            }
        }
    }

    private func fmt(_ v: Double) -> String { String(format: "%.1f", v) }

    private var dressedPane: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(app.t("Dressed form", "着せた形"))
                .font(.system(size: 11.5, weight: .semibold)).foregroundStyle(Theme.fg)
            if m.dressedBusy {
                ProgressView().frame(maxWidth: .infinity, minHeight: 260)
            } else if m.dressedVerdict.isEmpty {
                Text(app.t("Not loaded yet.", "まだ読み込んでいません。"))
                    .font(.system(size: 11)).foregroundStyle(Theme.faint)
                    .frame(minHeight: 260, alignment: .top)
            } else if m.dressedVerdict != "ANSWER" {
                VStack(alignment: .leading, spacing: 4) {
                    Text(m.dressedVerdict).font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(Theme.bad)
                    if !m.dressedHowToClose.isEmpty {
                        Text(m.dressedHowToClose).font(.system(size: 11)).foregroundStyle(Theme.dim)
                    }
                }
                .frame(minHeight: 260, alignment: .topLeading)
            } else {
                DressedFormSceneView(points: m.dressedPoints, owner: m.dressedOwner,
                                     edges: m.dressedEdges)
                    .frame(minWidth: 200, maxWidth: .infinity, minHeight: 260)
                    .background(Theme.panel2, in: RoundedRectangle(cornerRadius: 8))
                Text(app.t(
                    "A picture, not a fit — every point is pushed to the form's surface plus a \(fmt(m.dressedGapCm))cm gap. Read fit from mannequin_clearance, not this.",
                    "写像であってフィットではありません — 全点を人台表面 + \(fmt(m.dressedGapCm))cm の空気層へ押し出しています。フィットは mannequin_clearance で読んでください。"))
                    .font(.system(size: 10)).foregroundStyle(Theme.faint)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private var patternPane: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(app.t("Flat pattern", "平らな型紙"))
                .font(.system(size: 11.5, weight: .semibold)).foregroundStyle(Theme.fg)
            if m.patternPieces.isEmpty {
                Text(app.t("Not loaded yet.", "まだ読み込んでいません。"))
                    .font(.system(size: 11)).foregroundStyle(Theme.faint)
                    .frame(minHeight: 260, alignment: .top)
            } else {
                FlatPatternMiniView(pieces: m.patternPieces)
                    .frame(minWidth: 200, maxWidth: .infinity, minHeight: 260)
                    .background(Theme.panel2, in: RoundedRectangle(cornerRadius: 8))
                Text(app.t(
                    "\(m.patternPieces.count) pieces, \(fmt(m.patternTotalArea)) cm² total.",
                    "\(m.patternPieces.count) ピース、合計 \(fmt(m.patternTotalArea)) cm²。"))
                    .font(.system(size: 10)).foregroundStyle(Theme.faint)
            }
        }
    }
}

// MARK: - FlatPatternMiniView
//
// `AtelierView.swift` の `PatternFigure` は private で、辺・合印・裁ち切り
// 線まで描く重い版 ―― ここではその全部を作り直さない(既存ファイルは
// 触らない)。輪郭だけを並べる軽い版。エンジンが返した座標をそのまま引く
// ―― ここで作図し直さない。
private struct FlatPatternMiniView: View {
    let pieces: [AtelierModel.PatternPiece]

    var body: some View {
        GeometryReader { g in
            let laid = layout()
            let s = min(g.size.width / max(laid.width, 1),
                       g.size.height / max(laid.height, 1))
            ZStack(alignment: .topLeading) {
                ForEach(Array(laid.shapes.enumerated()), id: \.offset) { _, pts in
                    poly(pts, s).stroke(Theme.dim, lineWidth: 0.9)
                }
            }
        }
        .padding(8)
    }

    private func poly(_ pts: [CGPoint], _ s: CGFloat) -> Path {
        Path { p in
            guard let first = pts.first else { return }
            p.move(to: CGPoint(x: first.x * s, y: first.y * s))
            for pt in pts.dropFirst() { p.addLine(to: CGPoint(x: pt.x * s, y: pt.y * s)) }
            p.closeSubpath()
        }
    }

    private func layout() -> (shapes: [[CGPoint]], width: CGFloat, height: CGFloat) {
        var x: CGFloat = 4
        var out: [[CGPoint]] = []
        var maxY: CGFloat = 0
        for p in pieces {
            guard !p.outline.isEmpty else { continue }
            let minX = p.outline.map(\.x).min() ?? 0
            let maxX = p.outline.map(\.x).max() ?? 0
            let shift = x - minX
            let moved = p.outline.map { CGPoint(x: $0.x + shift, y: $0.y + 4) }
            out.append(moved)
            x += (maxX - minX) + 8
            maxY = max(maxY, (p.outline.map(\.y).max() ?? 0) + 8)
        }
        return (out, x, maxY)
    }
}

// MARK: - DressedFormSceneView
//
// `AtelierView.swift` の `SewnView` と同じ考え方の軽い版(そちらは
// private で新しいファイルからは使えない、既存ファイルは触らない)。
// `mannequin_dress` は座標だけを返す(辺を持たない) ―― `sew_and_drape`
// の辺は**同じ fabric・同じ iterations で呼んで点数が一致した時だけ**
// 借りる(`AtelierModel.loadDressedForm` 参照)。一致しなければ edges は
// 空のまま渡ってくるので、ここは点だけを描く。
private struct DressedFormSceneView: NSViewRepresentable {
    let points: [[Double]]
    let owner: [String]
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
        defer { v.scene = scene }
        let colours: [String: NSColor] = [
            "前身頃": NSColor(red: 0.55, green: 0.72, blue: 0.95, alpha: 1),
            "後身頃": NSColor(red: 0.95, green: 0.72, blue: 0.55, alpha: 1),
            "袖": NSColor(red: 0.62, green: 0.90, blue: 0.68, alpha: 1),
        ]
        let ys = points.compactMap { $0.count > 1 ? $0[1] : nil }
        guard let lo = ys.min(), let hi = ys.max() else { return }
        let scale = 2.2 / CGFloat(max(hi - lo, 1))
        let mid = CGFloat((lo + hi) / 2)
        let root = SCNNode()
        if edges.isEmpty {
            for (i, p) in points.enumerated() where p.count == 3 {
                let dot = SCNSphere(radius: 0.035 / scale)
                let mat = SCNMaterial()
                mat.diffuse.contents = colours[i < owner.count ? owner[i] : ""] ?? NSColor.gray
                dot.materials = [mat]
                let node = SCNNode(geometry: dot)
                node.position = SCNVector3(CGFloat(p[0]), CGFloat(p[1]), CGFloat(p[2]))
                root.addChildNode(node)
            }
        } else {
            var byPiece: [String: [Int32]] = [:]
            for e in edges where e.count == 2 {
                let a = e[0], b = e[1]
                guard a < points.count, b < points.count else { continue }
                let name = a < owner.count ? owner[a] : ""
                byPiece[name, default: []] += [Int32(a), Int32(b)]
            }
            let verts = points.compactMap {
                $0.count == 3 ? SCNVector3(CGFloat($0[0]), CGFloat($0[1]), CGFloat($0[2])) : nil
            }
            guard verts.count == points.count else { return }
            let source = SCNGeometrySource(vertices: verts)
            for (name, idx) in byPiece {
                let data = Data(bytes: idx, count: idx.count * MemoryLayout<Int32>.size)
                let element = SCNGeometryElement(
                    data: data, primitiveType: .line,
                    primitiveCount: idx.count / 2, bytesPerIndex: MemoryLayout<Int32>.size)
                let geo = SCNGeometry(sources: [source], elements: [element])
                let mat = SCNMaterial()
                mat.diffuse.contents = colours[name] ?? NSColor.gray
                mat.lightingModel = .constant
                geo.materials = [mat]
                root.addChildNode(SCNNode(geometry: geo))
            }
        }
        root.position = SCNVector3(0, -mid * scale, 0)
        root.scale = SCNVector3(scale, scale, scale)
        scene.rootNode.addChildNode(root)
    }
}
