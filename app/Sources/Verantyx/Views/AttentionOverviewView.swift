import SwiftUI

// MARK: - AttentionOverviewView (UI A)
//
// owner の brief (verbatim): 「服飾を知らない人用に服飾uiを触ることなく
// 現在見てもらう必要な値をveraとllmの組み合わせが画面にクリックできる形で
// 表示してクリックすることでその現状を確認できるようにするui」
//
// **服飾のワークベンチ(AtelierView)はここに出さない。** 代わりに、
// 台帳のうち「いま人の判断を待っているもの」だけを抜き出し、
// クリックできるカードとして並べる。どれがカードになるかは Vera の
// 五状態(と 145 の型付き拒否の howToClose)が決める — このビューは
// それを言い換えるだけで、選びはしない:
//
//   CONTESTED                 二つの読みが食い違う。人が選ぶ。
//   UNKNOWN_* + how_to_close  何かが詰まっていて、閉じ方が分かっている。
//   PROPOSED                  機械が提案した。まだ誰も採用していない。
//   OBSERVED                  片付いている。カードにしない。
//
// 並び順は「何をいちばん塞いでいるか」— 型紙が引けない原因になる
// 採寸の欠落は、襟についた採用前の提案より先に出る。その順序は
// この画面が発明するのではなく、engine 自身の `garment_worklist`
// (裁断前に潰すことの一覧、engine 側の優先順)をそのまま使う。
//
// **モデルが無くても動く。** 見出しと「閉じるには」は台帳の生の値から
// この画面自身が組み立てる、モデルを一切呼ばない文面 — これが既定で
// 常に出る。詳細を開いたときだけ、`AtelierAnalyst.shared.pick`
// (服飾側の「解析に使う相手」— 別の選択欄をここには作らない)が
// モデルを指していれば、そのモデルに平易な言い換えを頼み、届いたら
// 生の文面の上に添える。届かなくても、待っている間も、生の文面は
// ずっと画面にある — 消えるのは足された方だけ。画面がモデル無しで
// 空白になる向きには作らない。
//
// AtelierModel は AtelierView と同じもの(engine への扉は
// `garment_spec` / `garment_worklist` / `rights_report` /
// `measure_sheet`)を読むだけで、ここから台帳へは一切書かない —
// このビューはクリックして見るだけの画面で、書く道は
// ワークベンチ(UI B, `onOpenWorkbench`)に委ねる。
//
// **UI A / UI B の切り替え(この画面の外、IDEShellView 側)についての
// 前提:** 同じ服飾タブの中身を選ぶだけの表示状態として
// `@AppStorage("atelier_overview_shown")` に持たせ、既定は Overview
// (UI A)。ShellLayoutState には持ち込んでいない — タブの構成
// (どのタブが開いているか)の話ではなく、開いている服飾タブの
// 中身をどちらの面で見せるかの話だから。他のワークフローが同じ
// 切り替えを別の形で作っていたら、そこは合わせ直しが要る。
struct AttentionOverviewView: View {
    @EnvironmentObject var app: AppState
    @StateObject private var m = AtelierModel()

    /// 「作業台で開く」を押したときの委譲。IDEShellView が
    /// UI A ⇄ UI B の切り替えそのものを持っているので、ここは
    /// 呼ぶだけ。
    var onOpenWorkbench: () -> Void = {}

    @State private var selected: Card?
    /// モデルが言い換えた文面。card.id をキーに持つ — 生の文面を
    /// 上書きせず、届いたら添えるだけなのでここは補助のキャッシュ。
    @State private var phrased: [String: String] = [:]
    @State private var phrasing: Set<String> = []

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                header
                if let err = m.engineError {
                    errorBanner(err)
                } else if m.loading && cards.isEmpty {
                    ProgressView()
                        .frame(maxWidth: .infinity)
                        .padding(.top, 48)
                } else {
                    content
                }
            }
            .padding(20)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .background(Theme.bg)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .task {
            await m.load()
            await m.loadWorklist()
            await m.loadRights()
            await m.loadMeasures()
        }
        .sheet(item: $selected) { card in
            CardDetailView(card: card, phrased: phrased[card.id],
                           isPhrasing: phrasing.contains(card.id),
                           onOpenWorkbench: { selected = nil; onOpenWorkbench() },
                           onClose: { selected = nil })
                .environmentObject(app)
                .task(id: card.id) { await requestPhrase(for: card) }
        }
    }

    // MARK: - Header

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(app.t("What needs a decision", "いま判断が要ること"))
                    .font(.system(size: 18, weight: .bold))
                    .foregroundStyle(Theme.fg)
                Spacer()
                Button {
                    Task {
                        await m.reconnect()
                        await m.loadWorklist()
                        await m.loadRights()
                        await m.loadMeasures()
                    }
                } label: {
                    Image(systemName: "arrow.clockwise")
                        .font(.system(size: 12, weight: .semibold))
                }
                .buttonStyle(.plain)
                .foregroundStyle(Theme.dim)
                .help(app.t("Refresh", "更新"))
            }
            Text(app.t(
                "\(m.projectName.isEmpty ? "This piece" : m.projectName) — click a card to see its state and how to close it.",
                "\(m.projectName.isEmpty ? "この服" : m.projectName) — カードをクリックすると状態と閉じ方が出ます。"))
                .font(.system(size: 12))
                .foregroundStyle(Theme.dim)
        }
    }

    private func errorBanner(_ err: String) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "bolt.slash")
                .foregroundStyle(Theme.bad)
            VStack(alignment: .leading, spacing: 2) {
                Text(app.t("The engine didn't answer.", "engine から応答がありません。"))
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Theme.fg)
                Text(err)
                    .font(.system(size: 10.5, design: .monospaced))
                    .foregroundStyle(Theme.faint)
                    .textSelection(.enabled)
            }
            Spacer(minLength: 8)
            Button(app.t("Retry", "再試行")) { Task { await m.reconnect() } }
                .buttonStyle(.plain)
                .font(.system(size: 11.5, weight: .semibold))
                .foregroundStyle(Theme.sel)
        }
        .padding(12)
        .background(Theme.bad.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
    }

    // MARK: - Body content

    @ViewBuilder
    private var content: some View {
        let list = cards
        if list.isEmpty {
            allClear
        } else if isBrandNew {
            // **正直な空の場合。** 新規プロジェクトはほとんど全部が
            // UNKNOWN — そのまま並べると壁になる。何も確定・食い違い・
            // 提案が無いなら、いちばん最初の一枚だけを意図して出す。
            VStack(alignment: .leading, spacing: 10) {
                Text(app.t(
                    "Nothing has been recorded for this piece yet. Start with the first thing it needs:",
                    "この服はまだ何も記録されていません。まず必要なのはこれです:"))
                    .font(.system(size: 12))
                    .foregroundStyle(Theme.dim)
                cardView(list[0])
                    .frame(maxWidth: 420, alignment: .leading)
            }
        } else {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 260, maximum: 340), spacing: 12)],
                     alignment: .leading, spacing: 12) {
                ForEach(list) { cardView($0) }
            }
        }
    }

    private var allClear: some View {
        VStack(alignment: .leading, spacing: 6) {
            Image(systemName: "checkmark.circle")
                .font(.system(size: 20))
                .foregroundStyle(Theme.ok)
            Text(app.t("Nothing is waiting on a decision right now.",
                       "いま判断待ちのものはありません。"))
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(Theme.fg)
            Text(app.t("Everything the ledger knows is either settled or hasn't been reached yet.",
                       "台帳が知っていることは、決着しているか、まだ届いていないかのどちらかです。"))
                .font(.system(size: 11.5))
                .foregroundStyle(Theme.faint)
        }
        .padding(.top, 8)
    }

    private func cardView(_ c: Card) -> some View {
        Button { selected = c } label: {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 6) {
                    Image(systemName: c.kind.icon)
                        .font(.system(size: 11, weight: .bold))
                    Text(c.kind.label(app))
                        .font(.system(size: 9.5, weight: .bold))
                        .tracking(0.4)
                }
                .foregroundStyle(c.kind.color)

                Text(displayTitle(c))
                    .font(.system(size: 13.5, weight: .semibold))
                    .foregroundStyle(Theme.fg)
                    .lineLimit(2)

                Text(plainStatus(c))
                    .font(.system(size: 11.5))
                    .foregroundStyle(Theme.dim)
                    .lineLimit(3)
                    .fixedSize(horizontal: false, vertical: true)

                Spacer(minLength: 0)

                HStack(spacing: 4) {
                    Text(app.t("View", "見る"))
                        .font(.system(size: 10.5, weight: .semibold))
                    Image(systemName: "chevron.right").font(.system(size: 8, weight: .bold))
                }
                .foregroundStyle(c.kind.color)
            }
            .padding(14)
            .frame(minHeight: 128, alignment: .topLeading)
            .frame(maxWidth: .infinity, alignment: .topLeading)
            .background(Theme.panel, in: RoundedRectangle(cornerRadius: 10))
            .overlay(RoundedRectangle(cornerRadius: 10).stroke(c.kind.color.opacity(0.35), lineWidth: 1))
        }
        .buttonStyle(.plain)
    }

    // MARK: - Card model

    struct Card: Identifiable {
        enum Kind {
            case contested, blocked, proposed

            var icon: String {
                switch self {
                case .contested: return "exclamationmark.triangle.fill"
                case .blocked:   return "questionmark.circle.fill"
                case .proposed:  return "sparkles"
                }
            }
            var color: Color {
                switch self {
                case .contested: return Theme.bad
                case .blocked:   return Theme.warn
                case .proposed:  return Theme.sel
                }
            }
            @MainActor
            func label(_ app: AppState) -> String {
                switch self {
                case .contested: return app.t("DISAGREEMENT", "食い違い")
                case .blocked:   return app.t("MISSING", "不明")
                case .proposed:  return app.t("SUGGESTED", "提案")
                }
            }
        }

        let id: String
        let kind: Kind
        let part: String
        let aspect: String
        let rawState: String
        let howToClose: String
        let value: String
        let sources: [String]
        let sides: [(value: String, sources: [String])]
        let proposalValue: String
        let proposalSource: String
        let proposalNote: String
    }

    // MARK: - Ranking
    //
    // Vera が「どれがカードか」を決め、順序も engine 自身の
    // garment_worklist が決める。ここは抜き出して並べるだけ。

    private var cards: [Card] {
        var used = Set<String>()
        var out: [Card] = []

        // Tier 0 — CONTESTED: 二つの読みが食い違う。人がいま選ぶ。
        for key in m.states.keys.sorted() {
            guard let s = m.states[key], s.state == "CONTESTED" else { continue }
            used.insert(key)
            out.append(makeCard(key: key, kind: .contested, state: s))
        }

        // Tier 1 — 実際に何かを塞いでいるもの。engine 自身の
        // 「裁断前に潰す」順(garment_worklist)→ そこに出ない採寸→
        // 由来の未決着、の順。この tier 内の順序は engine が決める。
        var blocked: [Card] = []
        for w in m.worklist {
            let key = "\(w.part)/\(w.aspect)"
            guard !used.contains(key) else { continue }
            used.insert(key)
            blocked.append(Card(id: key, kind: .blocked, part: w.part, aspect: w.aspect,
                                rawState: w.state, howToClose: w.howToClose,
                                value: "", sources: [], sides: [],
                                proposalValue: "", proposalSource: "", proposalNote: ""))
        }
        for r in m.measureRows where r.state.hasPrefix("UNKNOWN") && !r.howToClose.isEmpty {
            let key = "measure/\(r.spot)"
            guard !used.contains(key) else { continue }
            used.insert(key)
            blocked.append(Card(id: key, kind: .blocked,
                                part: r.name.isEmpty ? r.spot : r.name, aspect: "",
                                rawState: r.state, howToClose: r.howToClose,
                                value: "", sources: [], sides: [],
                                proposalValue: "", proposalSource: "", proposalNote: ""))
        }
        for r in m.rightsWorklist {
            let key = "rights/\(r.part)/\(r.aspect)"
            guard !used.contains(key) else { continue }
            used.insert(key)
            blocked.append(Card(id: key, kind: .blocked, part: r.part, aspect: r.aspect,
                                rawState: r.state, howToClose: r.howToClose,
                                value: "", sources: [], sides: [],
                                proposalValue: "", proposalSource: "", proposalNote: ""))
        }
        out.append(contentsOf: blocked)

        // Tier 2 — PROPOSED: 機械が提案しただけで、まだ誰も採用して
        // いない。何かを実際に塞いでいるものより後ろ — 「型紙を止めて
        // いる採寸の欠落は、襟の未採用の提案より先」という owner の
        // 例そのまま。
        for key in m.states.keys.sorted() {
            guard let s = m.states[key], s.state.hasPrefix("UNKNOWN"),
                  !s.proposals.isEmpty, !used.contains(key) else { continue }
            used.insert(key)
            out.append(makeCard(key: key, kind: .proposed, state: s))
        }
        return out
    }

    private func makeCard(key: String, kind: Card.Kind,
                          state s: AtelierModel.AspectState) -> Card {
        let bits = key.split(separator: "/", maxSplits: 1).map(String.init)
        let part = bits.first ?? key
        let aspect = bits.count > 1 ? bits[1] : ""
        let p = s.proposals.first
        return Card(id: key, kind: kind, part: part, aspect: aspect,
                   rawState: s.state, howToClose: s.howToClose, value: s.value,
                   sources: s.sources,
                   sides: s.sides.map { (value: $0.value, sources: $0.sources) },
                   proposalValue: p?.value ?? "", proposalSource: p?.source ?? "",
                   proposalNote: p?.note ?? "")
    }

    /// 何も確定も食い違いも提案も無いなら、素の新規プロジェクト。
    private var isBrandNew: Bool {
        (m.counts["confirmed"] ?? 0) == 0 &&
        (m.counts["contested"] ?? 0) == 0 &&
        (m.counts["proposed"] ?? 0) == 0
    }

    // MARK: - Plain wording (no model — this is the default, always on)

    private func plain(_ raw: String) -> String {
        raw.replacingOccurrences(of: "_", with: " ").capitalized
    }

    private func displayTitle(_ c: Card) -> String {
        c.aspect.isEmpty ? plain(c.part) : "\(plain(c.part)) — \(plain(c.aspect))"
    }

    private func plainStatus(_ c: Card) -> String {
        switch c.kind {
        case .contested:
            return app.t("Two readings disagree — someone needs to pick one.",
                         "二つの読みが食い違っています。人が選ぶ必要があります。")
        case .blocked:
            return app.t("Not known yet.", "まだわかっていません。")
        case .proposed:
            let v = c.proposalValue.isEmpty ? "…" : c.proposalValue
            return app.t("A model suggested “\(v)”. Nobody has accepted it.",
                         "AI が「\(v)」を提案しました。まだ誰も採用していません。")
        }
    }

    // MARK: - Model phrasing (optional — the screen already works without it)

    private func requestPhrase(for card: Card) async {
        guard phrased[card.id] == nil, !phrasing.contains(card.id) else { return }
        let pick = AtelierAnalyst.shared.pick
        if case .vera = pick { return }   // モデルを呼ばない選択 — 生の文面のまま
        phrasing.insert(card.id)
        defer { phrasing.remove(card.id) }
        if let text = await Self.askModel(pick: pick, card: card,
                                          japanese: AppLanguage.shared.isJapanese) {
            phrased[card.id] = text
        }
    }

    private static func askModel(pick: AtelierAnalyst.Pick, card: Card,
                                 japanese: Bool) async -> String? {
        let prompt = """
        \(japanese
            ? "服飾を知らない人に、1〜2文の平易な言葉で説明してください。専門語は避けてください。"
            : "Explain this in 1-2 short plain sentences for someone who has never done garment-making. Avoid jargon.")

        \(japanese ? "対象" : "item"): \(card.part)\(card.aspect.isEmpty ? "" : " / \(card.aspect)")
        \(japanese ? "現在の値" : "current value"): \(card.value.isEmpty ? "—" : card.value)
        \(japanese ? "生の状態" : "raw status"): \(card.rawState)
        \(japanese ? "閉じるには" : "how to close it"): \(card.howToClose.isEmpty ? "—" : card.howToClose)
        """
        var raw: String?
        switch pick {
        case .vera:
            return nil
        case .ollama(let name):
            raw = await OllamaClient.shared.generate(model: name, prompt: prompt, maxTokens: 220)
        case .jgen(let name):
            let mgr = JCrossChatManager.shared
            if await mgr.loadedModelName != name {
                guard (try? await mgr.load(modelFileName: name)) != nil else { return nil }
            }
            raw = try? await mgr.generate(conversation: [("user", prompt)],
                                          maxTokens: 220, keepThinking: false)
        case .lmStudio(let name):
            raw = await LMStudioClient.shared.generateConversation(
                model: name, messages: [("user", prompt)], maxTokens: 220, temperature: 0.2)
        case .cloud(let p, let name):
            let r = await CloudAPIClient.shared.send(
                systemPrompt: japanese
                    ? "服飾台帳の状態を、専門知識のない人向けに平易に言い換える。前置きなしで本文のみ返す。"
                    : "You explain garment-ledger states in plain language for a beginner. Reply with only the explanation, no preamble.",
                userMessage: prompt, provider: p, modelOverride: name)
            if case .success(let text) = r { raw = text }
        }
        guard let text = raw?.trimmingCharacters(in: .whitespacesAndNewlines),
              !text.isEmpty else { return nil }
        return text
    }
}

// MARK: - Card detail sheet
//
// クリックした一枚の「いまの状態」と「閉じるには」だけを見せる。
// ワークベンチ全体ではない — それが要るなら `onOpenWorkbench` で
// UI B に渡す。

private struct CardDetailView: View {
    @EnvironmentObject var app: AppState
    let card: AttentionOverviewView.Card
    let phrased: String?
    let isPhrasing: Bool
    var onOpenWorkbench: () -> Void
    var onClose: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                HStack(spacing: 6) {
                    Image(systemName: card.kind.icon)
                    Text(card.kind.label(app))
                        .font(.system(size: 10, weight: .bold))
                        .tracking(0.4)
                }
                .foregroundStyle(card.kind.color)
                Spacer()
                Button(action: onClose) {
                    Image(systemName: "xmark.circle.fill")
                }
                .buttonStyle(.plain)
                .foregroundStyle(Theme.faint)
            }

            Text(title)
                .font(.system(size: 17, weight: .bold))
                .foregroundStyle(Theme.fg)

            // モデルの言い換え、あれば。**生の文面を置き換えない** —
            // 上に添えるだけ。モデルが無い・答えない・まだ待っている
            // 間は、この段が無いだけで下の生の段は常にある。
            if isPhrasing {
                HStack(spacing: 6) {
                    ProgressView().controlSize(.small)
                    Text(app.t("Asking the model to put this in plain words…",
                               "モデルに平易な言い換えを頼んでいます…"))
                        .font(.system(size: 11))
                        .foregroundStyle(Theme.faint)
                }
            } else if let phrased {
                VStack(alignment: .leading, spacing: 3) {
                    Text(phrased)
                        .font(.system(size: 13))
                        .foregroundStyle(Theme.fg)
                        .fixedSize(horizontal: false, vertical: true)
                    Text("— \(AtelierAnalyst.shared.pick.label)")
                        .font(.system(size: 9.5))
                        .foregroundStyle(Theme.faint)
                }
            }

            Divider().opacity(0.3)

            currentState

            if !card.howToClose.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text(app.t("HOW TO CLOSE IT", "閉じるには"))
                        .font(.system(size: 10, weight: .bold))
                        .tracking(0.5)
                        .foregroundStyle(Theme.faint)
                    Text(card.howToClose)
                        .font(.system(size: 12.5))
                        .foregroundStyle(Theme.fg)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            Divider().opacity(0.3)

            HStack(alignment: .top) {
                Text(app.t("Raw state: ", "生の状態: ") + card.rawState)
                    .font(.system(size: 9.5, design: .monospaced))
                    .foregroundStyle(Theme.faint)
                    .textSelection(.enabled)
                Spacer(minLength: 8)
                Button(app.t("Open in the workbench", "作業台で開く"), action: onOpenWorkbench)
                    .buttonStyle(.plain)
                    .font(.system(size: 11.5, weight: .semibold))
                    .foregroundStyle(Theme.sel)
            }
        }
        .padding(20)
        .frame(width: 420)
        .background(Theme.panel2)
    }

    private var title: String {
        card.aspect.isEmpty ? plain(card.part) : "\(plain(card.part)) — \(plain(card.aspect))"
    }

    private func plain(_ raw: String) -> String {
        raw.replacingOccurrences(of: "_", with: " ").capitalized
    }

    @ViewBuilder
    private var currentState: some View {
        switch card.kind {
        case .contested:
            VStack(alignment: .leading, spacing: 6) {
                Text(app.t("Two readings disagree:", "二つの読みが食い違っています:"))
                    .font(.system(size: 11.5, weight: .semibold))
                    .foregroundStyle(Theme.fg)
                if card.sides.isEmpty {
                    Text(card.value.isEmpty ? "—" : card.value)
                        .font(.system(size: 12))
                        .foregroundStyle(Theme.dim)
                } else {
                    ForEach(Array(card.sides.enumerated()), id: \.offset) { _, side in
                        HStack(alignment: .top, spacing: 6) {
                            Text("•").foregroundStyle(Theme.bad)
                            VStack(alignment: .leading, spacing: 1) {
                                Text(side.value)
                                    .font(.system(size: 12, weight: .medium))
                                    .foregroundStyle(Theme.fg)
                                if !side.sources.isEmpty {
                                    Text(side.sources.joined(separator: ", "))
                                        .font(.system(size: 10))
                                        .foregroundStyle(Theme.faint)
                                }
                            }
                        }
                    }
                }
            }
        case .blocked:
            Text(app.t("Not known yet.", "まだわかっていません。"))
                .font(.system(size: 12.5))
                .foregroundStyle(Theme.dim)
        case .proposed:
            VStack(alignment: .leading, spacing: 4) {
                Text(app.t("Suggested value:", "提案された値:"))
                    .font(.system(size: 11.5, weight: .semibold))
                    .foregroundStyle(Theme.fg)
                Text(card.proposalValue.isEmpty ? "—" : card.proposalValue)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(Theme.sel)
                if !card.proposalSource.isEmpty {
                    Text(app.t("by ", "提案元: ") + card.proposalSource)
                        .font(.system(size: 10.5))
                        .foregroundStyle(Theme.faint)
                }
                if !card.proposalNote.isEmpty {
                    Text(card.proposalNote)
                        .font(.system(size: 11))
                        .foregroundStyle(Theme.dim)
                }
                Text(app.t("Nobody has accepted this yet — it does not appear in the design.",
                           "まだ誰も採用していません — 設計には入っていません。"))
                    .font(.system(size: 10.5))
                    .foregroundStyle(Theme.faint)
            }
        }
    }
}
