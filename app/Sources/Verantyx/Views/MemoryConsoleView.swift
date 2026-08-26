import SwiftUI

/// The Gatekeeper screen's memory console: what memory actually did this turn,
/// and a way to reach into the model's residual stream directly.
///
/// **The boundary this panel exists to make visible.** Two different mechanisms
/// get called "JGEN memory" and they are not the same thing:
///
///  - Ordinary chat *retrieves* by vector — `EternalMemoryStore` embeds text
///    through JGEN's own `encode` and ranks by cosine similarity — but then
///    *injects the result as text*, prepended to the prompt like any other
///    context. That is what the upper half measures.
///  - Real residual-stream injection (`encodeSoft` / `injectMultiLayer`) runs
///    only in Council rounds, `JGenSpeakAgent`'s steering, and Vera's
///    `jgen_reflect`. A normal chat turn never touches it.
///
/// So the lower half is labelled a probe, not a setting. It operates on the
/// residual stream for real, and it is deliberately not dressed up as
/// configuration for something chat is already doing — because chat is not.
/// Implying otherwise would make every number in the upper half unreadable.
struct MemoryConsoleView: View {

    @EnvironmentObject var app: AppState
    @ObservedObject private var usage = ContextUsageTracker.shared

    /// Only a JGEN model exposes hidden states; every other backend is reached
    /// over HTTP and has none to reach into.
    private var isJGenLoaded: Bool {
        if case .jcrossReady = app.modelStatus { return true }
        return false
    }

    @State private var recallQuery = ""
    @State private var recallHits: [(text: String, score: Float)] = []
    @State private var searching = false

    @State private var probePrompt = "The answer is"
    @State private var probeLabel = ""
    @State private var probeLayer = 8
    @State private var probeAlpha = 0.3
    @State private var probeResult: [(layer: Int, text: String, entropy: Float)] = []
    @State private var probing = false
    @State private var probeError: String?

    // Milestone Y: the failure taxonomy and its review queue, surfaced where
    // the person already looks. Raw counts from Vera's failure_stats plus the
    // pending capacity proposals with their probe evidence — the approve
    // button here is the human half of the loop; nothing below it applies a
    // limit on its own.
    @State private var failureVerdicts: [(String, Int)] = []
    @State private var failureClasses: [(String, Int)] = []
    @State private var capacityPending: [CapacityProposal] = []
    @State private var failureLoading = false
    @State private var capacityActionResult: String?

    struct CapacityProposal: Identifiable {
        let id: Int
        let parameter: String
        let current: Int
        let proposed: Int
        let reason: String
        let probeCount: Int
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                thisTurnSection
                Divider().opacity(0.2)
                recallSection
                Divider().opacity(0.2)
                probeSection
                Divider().opacity(0.2)
                failureSection
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .background(Theme.panel2)
        .task { await refreshFailures() }
    }

    // MARK: - Failure taxonomy + capacity review

    private var failureSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                header("失敗の型 (Vera-α)", icon: "waveform.path.ecg")
                Spacer()
                Button {
                    Task { await refreshFailures() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .buttonStyle(.plain)
                .disabled(failureLoading)
            }

            if failureVerdicts.isEmpty && capacityPending.isEmpty {
                Text(failureLoading ? "読み込み中…"
                     : "記録された型付き失敗はまだありません。ビルド・変換の失敗は自動でここに集まります。")
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
            }

            ForEach(failureVerdicts, id: \.0) { verdict, count in
                HStack(spacing: 8) {
                    Text(verdict)
                        .font(.system(size: 11, design: .monospaced))
                    Spacer()
                    Text("\(count)")
                        .font(.system(size: 11, weight: .semibold, design: .monospaced))
                }
            }

            if !capacityPending.isEmpty {
                Text(L("Proposed limit increases (awaiting approval)", "限界値の引き上げ提案(承認待ち)"))
                    .font(.system(size: 11, weight: .semibold))
                    .padding(.top, 4)
                ForEach(capacityPending) { p in
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text("\(p.parameter): \(p.current) → \(p.proposed)")
                                .font(.system(size: 11, weight: .semibold, design: .monospaced))
                            Spacer()
                            Button(L("Approve", "承認")) { Task { await actOnCapacity(p.id, accept: true) } }
                                .font(.system(size: 10))
                            Button(L("Reject", "却下")) { Task { await actOnCapacity(p.id, accept: false) } }
                                .font(.system(size: 10))
                        }
                        // The evidence, not just the number: what was re-run
                        // and that it answered. A reviewer approving a bare
                        // integer is not reviewing anything.
                        Text(L("\(p.reason) — re-run, with \(p.probeCount) pieces of evidence", "\(p.reason) — 再実行 \(p.probeCount) 件の証拠つき"))
                            .font(.system(size: 10))
                            .foregroundStyle(.secondary)
                    }
                    .padding(6)
                    .background(Color.white.opacity(0.05), in: RoundedRectangle(cornerRadius: 6))
                }
            }

            if let msg = capacityActionResult {
                Text(msg).font(.system(size: 10)).foregroundStyle(.secondary)
            }
        }
    }

    private func refreshFailures() async {
        failureLoading = true
        defer { failureLoading = false }
        let statsRaw = await VeraMemoryBridge.failureStats()
        if let data = statsRaw.data(using: .utf8),
           let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            let verdicts = (obj["verdicts"] as? [String: Int]) ?? [:]
            failureVerdicts = verdicts.sorted { $0.value > $1.value }.map { ($0.key, $0.value) }
            let classes = (obj["classifications"] as? [String: Int]) ?? [:]
            failureClasses = classes.sorted { $0.value > $1.value }.map { ($0.key, $0.value) }
        }
        let pendRaw = await VeraMemoryBridge.listPendingCapacityLimits()
        if let data = pendRaw.data(using: .utf8),
           let arr = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]] {
            capacityPending = arr.compactMap { e in
                guard let idx = e["index"] as? Int,
                      let param = e["parameter"] as? String,
                      let cur = e["current"] as? Int,
                      let prop = e["proposed"] as? Int else { return nil }
                return CapacityProposal(
                    id: idx, parameter: param, current: cur, proposed: prop,
                    reason: (e["reason"] as? String) ?? "",
                    probeCount: ((e["probes"] as? [[String: Any]]) ?? []).count)
            }
        }
    }

    private func actOnCapacity(_ index: Int, accept: Bool) async {
        let raw = accept
            ? await VeraMemoryBridge.acceptCapacityLimit(index: index)
            : await VeraMemoryBridge.rejectCapacityLimit(index: index)
        capacityActionResult = raw.count > 200 ? String(raw.prefix(200)) : raw
        await refreshFailures()
    }

    // MARK: - Upper half: what memory contributed

    private var thisTurnSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            header(app.t("What memory added to this turn", "このターンで記憶が足したもの"),
                   icon: "tray.full")

            let u = usage.current
            let total = max(u.totalInjectionChars, 1)

            // Characters, not tokens, and said so. The underlying budget is a
            // character count with a /4 fudge factor everywhere in this app;
            // presenting it as tokens would be inventing precision.
            ForEach(sources(u), id: \.label) { s in
                VStack(alignment: .leading, spacing: 2) {
                    HStack {
                        Circle().fill(s.color).frame(width: 5, height: 5)
                        Text(s.label).font(.system(size: 10))
                        Spacer()
                        Text(s.chars == 0 ? "—" : "\(s.chars)")
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(s.chars == 0 ? .tertiary : .secondary)
                    }
                    GeometryReader { geo in
                        RoundedRectangle(cornerRadius: 1.5)
                            .fill(s.color.opacity(0.7))
                            .frame(width: geo.size.width * CGFloat(s.chars) / CGFloat(total))
                    }
                    .frame(height: 3)
                }
            }

            HStack {
                Text(app.t("Total injected", "注入合計"))
                    .font(.system(size: 10, weight: .medium))
                Spacer()
                Text("\(u.totalInjectionChars) "
                     + app.t("chars (~\(u.estimatedTotalTokens) tokens, estimated)",
                             "文字 (推定 \(u.estimatedTotalTokens) トークン)"))
                    .font(.system(size: 10, design: .monospaced)).foregroundStyle(.secondary)
            }
            .padding(.top, 2)

            if let inTok = u.realInputTokens {
                Text(app.t("Backend reported \(inTok) input tokens for real.",
                           "バックエンドの実測入力トークン: \(inTok)"))
                    .font(.system(size: 9)).foregroundStyle(.tertiary)
            }
            if usage.compressionEventsThisSession > 0 {
                Text(app.t("Compressed \(usage.compressionEventsThisSession)× this session, ~\(usage.charsSavedByCompressionThisSession) chars saved.",
                           "このセッションで \(usage.compressionEventsThisSession) 回圧縮、約 \(usage.charsSavedByCompressionThisSession) 文字削減。"))
                    .font(.system(size: 9)).foregroundStyle(.tertiary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if u.totalInjectionChars == 0 {
                Text(app.t("Nothing yet — send a message and this fills in.",
                           "まだ何もありません。メッセージを送ると埋まります。"))
                    .font(.system(size: 9)).foregroundStyle(.tertiary)
            }
        }
    }

    private struct Source { let label: String; let chars: Int; let color: Color }

    private func sources(_ u: ContextUsageTracker.InjectionUsage) -> [Source] {
        [
            Source(label: app.t("Eternal (vector recall)", "永遠記憶(ベクトル検索)"),
                   chars: u.eternalMemoryChars, color: Theme.warn),
            Source(label: app.t("Vera facts", "Vera事実"),
                   chars: u.veraChars, color: Theme.ok),
            Source(label: app.t("Zone L1–L3", "ゾーン L1〜L3"),
                   chars: u.l2ZoneChars, color: Theme.accent),
            Source(label: app.t("Skills", "スキル"),
                   chars: u.skillChars, color: Theme.sel),
            Source(label: app.t("System prompt", "システムプロンプト"),
                   chars: u.systemPromptChars, color: Theme.dim),
            Source(label: app.t("Conversation", "会話履歴"),
                   chars: u.conversationHistoryChars, color: Theme.dim),
        ]
    }

    // MARK: - Middle: what recall actually returns

    private var recallSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            header(app.t("Ask memory directly", "記憶に直接聞く"), icon: "magnifyingglass")
            Text(app.t(
                "Same search a chat turn runs: the query is embedded through JGEN's encode and ranked by cosine similarity. The result reaches the model as text.",
                "チャットのターンが実行するのと同じ検索です。問い合わせをJGENのencodeでベクトル化しコサイン類似で順位付けします。結果はテキストとしてモデルに渡ります。"))
                .font(.system(size: 9)).foregroundStyle(.tertiary)
                .fixedSize(horizontal: false, vertical: true)

            HStack(spacing: 6) {
                TextField(app.t("query", "問い合わせ"), text: $recallQuery)
                    .textFieldStyle(.roundedBorder).font(.system(size: 11))
                Button(app.t("Search", "検索")) { Task { await search() } }
                    .buttonStyle(.bordered).controlSize(.small)
                    .disabled(searching || recallQuery.isEmpty)
                if searching { ProgressView().controlSize(.mini) }
            }

            ForEach(Array(recallHits.enumerated()), id: \.offset) { _, hit in
                VStack(alignment: .leading, spacing: 2) {
                    HStack {
                        Text(String(format: "%.3f", hit.score))
                            .font(.system(size: 9, design: .monospaced))
                            .foregroundStyle(Theme.warn)
                        Spacer()
                        Button(app.t("Use as probe label", "プローブに使う")) {
                            probeLabel = hit.text
                        }
                        .buttonStyle(.plain)
                        .font(.system(size: 9))
                        .foregroundStyle(Theme.sel)
                    }
                    Text(hit.text)
                        .font(.system(size: 10)).foregroundStyle(.secondary)
                        .lineLimit(3).fixedSize(horizontal: false, vertical: true)
                }
                .padding(8)
                .background(RoundedRectangle(cornerRadius: 6).fill(Color.white.opacity(0.04)))
            }
            if !searching && recallHits.isEmpty && !recallQuery.isEmpty {
                Text(app.t("No hits.", "該当なし。")).font(.system(size: 9)).foregroundStyle(.tertiary)
            }
        }
    }

    // MARK: - Lower half: the residual-stream probe

    private var probeSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            header(app.t("Residual-stream probe", "残差ストリーム・プローブ"), icon: "waveform.path")

            // The boundary, stated where it cannot be missed. Everything above
            // measures text injection; this does something categorically
            // different, and it is not part of a chat turn.
            HStack(alignment: .top, spacing: 7) {
                Image(systemName: "info.circle")
                    .font(.system(size: 10))
                    .foregroundStyle(Theme.sel)
                Text(app.t(
                    "Chat does not do this. Everything above reaches the model as text; this blends a vector straight into the residual stream and shows what the model's internal state decodes to afterwards. Council rounds and Vera's reflect tool use this path — an ordinary chat turn never does.",
                    "チャットはこれをしていません。上の項目はすべてテキストとしてモデルに届きます。ここではベクトルを残差ストリームに直接混ぜ、その後のモデル内部状態が何に復号されるかを見ます。この経路を使うのは合議ラウンドとVeraのreflectツールだけで、通常のチャットのターンは通りません。"))
                    .font(.system(size: 9))
                    .fixedSize(horizontal: false, vertical: true)
                Spacer()
            }
            .padding(9)
            .background(RoundedRectangle(cornerRadius: 6).fill(Color.blue.opacity(0.08)))

            if !isJGenLoaded {
                Text(app.t("Load a JGEN model to use this — the probe runs inside the engine, so it has nothing to reach into otherwise.",
                           "使用するにはJGENモデルをロードしてください。プローブはエンジン内部で動くため、モデルが無いと触れる対象がありません。"))
                    .font(.system(size: 9)).foregroundStyle(.orange)
                    .fixedSize(horizontal: false, vertical: true)
            }

            labelled(app.t("Prompt", "プロンプト")) {
                TextField("", text: $probePrompt)
                    .textFieldStyle(.roundedBorder).font(.system(size: 11))
            }
            labelled(app.t("Inject", "注入する内容")) {
                TextField(app.t("a memory or a short label", "記憶または短いラベル"),
                          text: $probeLabel)
                    .textFieldStyle(.roundedBorder).font(.system(size: 11))
            }
            labelled(app.t("Layer", "層")) {
                HStack(spacing: 6) {
                    Stepper(value: $probeLayer, in: 0...63) {
                        Text("\(probeLayer)").font(.system(size: 11, design: .monospaced))
                    }
                }
            }
            labelled(app.t("Strength", "強さ")) {
                HStack(spacing: 6) {
                    Slider(value: $probeAlpha, in: 0...1)
                    Text(String(format: "%.2f", probeAlpha))
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(.secondary)
                }
            }
            // The injection is norm-matched, not additive — worth saying, since
            // "strength" otherwise reads as "how much extra".
            Text(app.t(
                "The vector is rescaled to the residual's own magnitude before blending, so strength is a mix ratio, not an amount added.",
                "ベクトルは混ぜる前に残差自身の大きさに合わせて再スケールされます。強さは混合比であって加算量ではありません。"))
                .font(.system(size: 9)).foregroundStyle(.tertiary)
                .fixedSize(horizontal: false, vertical: true)

            HStack(spacing: 6) {
                Button(app.t("Run probe", "プローブ実行")) { Task { await probe() } }
                    .buttonStyle(.borderedProminent).controlSize(.small)
                    .disabled(probing || probeLabel.isEmpty)
                if probing { ProgressView().controlSize(.mini) }
            }

            if let probeError {
                Text(probeError).font(.system(size: 9)).foregroundStyle(.orange)
                    .fixedSize(horizontal: false, vertical: true)
            }

            if !probeResult.isEmpty {
                Text(app.t("Internal state, decoded to its nearest token",
                           "内部状態を最も近いトークンに復号"))
                    .font(.system(size: 10, weight: .medium))
                ForEach(probeResult, id: \.layer) { r in
                    HStack(spacing: 8) {
                        Text("L\(r.layer)")
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(.tertiary).frame(width: 28, alignment: .leading)
                        Text(r.text.isEmpty ? "·" : r.text)
                            .font(.system(size: 11, design: .monospaced))
                        Spacer()
                        // Entropy is the honest confidence signal here: a single
                        // decoded token from a mid-stack residual means little on
                        // its own.
                        Text(String(format: "H=%.2f", r.entropy))
                            .font(.system(size: 9, design: .monospaced)).foregroundStyle(.tertiary)
                    }
                    .padding(.vertical, 2)
                }
            }
        }
    }

    // MARK: - Bits

    private func header(_ title: String, icon: String) -> some View {
        HStack(spacing: 5) {
            Image(systemName: icon).font(.system(size: 10))
                .foregroundStyle(Theme.sel)
            Text(title).font(.system(size: 12, weight: .semibold))
        }
    }

    private func labelled<C: View>(_ label: String, @ViewBuilder _ content: () -> C) -> some View {
        HStack(spacing: 8) {
            Text(label).font(.system(size: 10)).foregroundStyle(.secondary)
                .frame(width: 74, alignment: .leading)
            content()
        }
    }

    // MARK: - Actions

    private func search() async {
        searching = true
        defer { searching = false }
        recallHits = (try? await EternalMemoryStore.shared.search(query: recallQuery, k: 5)) ?? []
    }

    private func probe() async {
        probing = true; probeError = nil
        defer { probing = false }
        // Observe around the injection point: one layer before, the layer
        // itself, and a couple after, so the effect can be seen propagating
        // rather than just landing.
        let observe = [max(probeLayer - 1, 0), probeLayer, probeLayer + 2, probeLayer + 4]
        do {
            let out = try await JCrossChatManager.shared.reflect(
                prompt: probePrompt,
                interventions: [(layer: probeLayer, textLabel: probeLabel, alpha: Float(probeAlpha))],
                observeLayers: observe)
            probeResult = out.map { (layer: $0.key, text: $0.value.text, entropy: $0.value.entropy) }
                .sorted { $0.layer < $1.layer }
        } catch {
            probeResult = []
            probeError = error.localizedDescription
        }
    }
}
