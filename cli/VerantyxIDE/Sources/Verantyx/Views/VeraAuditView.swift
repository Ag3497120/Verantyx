import SwiftUI
import WebKit

// Vera-a audit screen — the mode's whole new body (Milestone U).
//
// The previous Vera-a layout was a chat about the engine; this is the
// ENGINE ITSELF, twice over: the exact page published at
// https://verantyx.ai/vera3d/ running live in a WKWebView (run side), and
// the same page's source checked out from verantyx-v6, editable and
// publishable by git push (edit side). One screen, both directions —
// an audit surface in the literal sense: what the world sees, and the
// lever that changes it, with nothing in between.
//
// Gap resolution rides the page's own governed flow: the demand list
// (refused subjects, ranked by how many people asked) loads each subject
// into the page, whose offer → preview → approve pipeline does the actual
// ingestion. The IDE adds no second ingestion path — a second path is how
// two readers of one corpus begin to disagree.
//
// Contributor permission is GitHub permission: publish is `git push` to
// verantyx-v6, so whoever the owner adds as a collaborator can publish,
// and nobody else can. No parallel auth system to get wrong.

// MARK: - Web view wrapper

private struct AuditWebView: NSViewRepresentable {
    @Binding var request: AuditWebRequest

    func makeNSView(context: Context) -> WKWebView {
        let cfg = WKWebViewConfiguration()
        let v = WKWebView(frame: .zero, configuration: cfg)
        v.load(URLRequest(url: request.url))
        context.coordinator.lastStamp = request.stamp
        return v
    }

    func updateNSView(_ v: WKWebView, context: Context) {
        guard context.coordinator.lastStamp != request.stamp else { return }
        context.coordinator.lastStamp = request.stamp
        if let html = request.html {
            v.loadHTMLString(html, baseURL: request.url)
        } else {
            v.load(URLRequest(url: request.url))
        }
    }

    func makeCoordinator() -> Coord { Coord() }
    final class Coord { var lastStamp = 0 }
}

private struct AuditWebRequest {
    var url: URL
    var html: String? = nil
    var stamp: Int = 0
}

// MARK: - Demand row

private struct DemandRow: Identifiable, Decodable {
    var id: String { subject }
    let subject: String
    let count: Int
}

private struct DemandReply: Decodable {
    let ok: Bool
    let demand: [DemandRow]?
}

// MARK: - The audit screen

struct VeraAuditView: View {
    @EnvironmentObject var app: AppState

    @StateObject private var engine = LocalVeraServer.shared
    @State private var showSettings = false
    @State private var showPair = false
    @State private var web = AuditWebRequest(
        url: URL(string: "https://verantyx.ai/vera3d/")!)
    @State private var demand: [DemandRow] = []
    @State private var demandNote = ""
    @State private var repoPath =
        NSString(string: "~/Projects/verantyx-v6").expandingTildeInPath
    @State private var editorText = ""
    @State private var editorLoaded = false
    @State private var gitLog = ""
    @State private var commitMessage = "vera3d: audited edit"
    @State private var busy = false
    @State private var tab: Tab = .gaps
    @State private var memory = AuditMemory.load(task: "verantyx-ai-vera3d")
    @State private var jgenModel = "qwen3.5:4b"
    @State private var editRequest = ""
    @State private var jgenBusy = false
    @State private var jgenNote = ""
    @State private var distNote = ""
    @State private var vecHits: [VectorHit] = []
    @State private var vecBasis = ""
    @State private var vecNote = ""
    @State private var peerHost = ""
    @State private var shardProc: Process?

    private enum Tab { case gaps, edit, memory }

    var body: some View {
        HStack(spacing: 0) {
            // Run side — the published page, live.
            VStack(spacing: 0) {
                HStack(spacing: 8) {
                    Circle()
                        .fill(engineColor).frame(width: 7, height: 7)
                    Text(engineLabel).font(.system(size: 11, weight: .semibold))
                    Spacer()
                    // Pair launch only — the configuration itself stays in
                    // Settings. A screen that both configures and launches
                    // invites half-configured launches.
                    Button(app.t("2-Mac", "2台で動かす")) { showPair = true }
                        .font(.system(size: 10))
                    Button(app.t("Local", "ローカル")) { useLocal() }
                        .font(.system(size: 10))
                    Button(app.t("Live site", "本番")) {
                        web = AuditWebRequest(
                            url: URL(string: "https://verantyx.ai/vera3d/")!,
                            stamp: web.stamp + 1)
                    }
                    .font(.system(size: 10))
                    // Vera-a had no way to reach Settings at all; this mode
                    // replaces the whole layout, activity bar included.
                    Button { showSettings = true } label: {
                        Image(systemName: "gearshape")
                    }
                    .font(.system(size: 10))
                    Button(app.t("Exit", "終了")) { app.isVeraAMode = false }
                        .font(.system(size: 10))
                }
                .padding(.horizontal, 10).padding(.vertical, 6)
                Divider().opacity(0.3)
                AuditWebView(request: $web)
            }
            .frame(minWidth: 480, maxWidth: .infinity)

            Divider().opacity(0.3)

            // Audit side — gaps to resolve, source to edit, lever to publish.
            VStack(spacing: 0) {
                Picker("", selection: $tab) {
                    Text(app.t("Gaps", "欠落の解消")).tag(Tab.gaps)
                    Text(app.t("Edit & publish", "編集と公開")).tag(Tab.edit)
                    Text(app.t("Memory", "永遠の記憶")).tag(Tab.memory)
                }
                .pickerStyle(.segmented)
                .padding(8)

                switch tab {
                case .gaps:   gapsPanel
                case .edit:   editPanel
                case .memory: memoryPanel
                }
            }
            .frame(width: 380)
            .background(Color(red: 0.11, green: 0.11, blue: 0.14))
        }
        .task {
            await refreshDemand()
            // Native host, native engine: start it and point the view at
            // it. No download, no boot button, and the SSE channel the
            // browser build cannot have.
            engine.start()
        }
        .onChange(of: engine.state) { st in
            if case .ready = st, let u = engine.url {
                web = AuditWebRequest(url: u, stamp: web.stamp + 1)
            }
        }
        .sheet(isPresented: $showSettings) {
            SettingsView().environmentObject(app)
                .frame(minWidth: 720, minHeight: 520)
        }
        .sheet(isPresented: $showPair) {
            PipeConnectSheet().environmentObject(app)
        }
    }

    private var engineLabel: String {
        switch engine.state {
        case .idle:      return app.t("engine idle", "エンジン停止中")
        case .starting:  return app.t("engine starting…", "エンジン起動中…")
        case .ready:     return app.t("local engine — full artifact, live trace",
                                      "ローカルエンジン — 完全版・推論を実況")
        case .failed(let m): return app.t("live site (local: \(m))",
                                          "本番表示(ローカル: \(m))")
        }
    }
    private var engineColor: Color {
        switch engine.state {
        case .ready: return .green
        case .starting: return .orange
        case .failed: return .secondary
        case .idle: return .secondary
        }
    }
    private func useLocal() {
        if let u = engine.url {
            web = AuditWebRequest(url: u, stamp: web.stamp + 1)
        } else {
            engine.start()
        }
    }

    // MARK: Gaps — the demand ranking, resolved through the page itself

    private var gapsPanel: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(app.t(
                "Subjects the world asked for and Vera refused, most-asked "
                + "first. Opening one drives the page's own offer → preview "
                + "→ approve flow — the IDE adds no second ingestion path.",
                "世界が訊いて Vera が拒否した主題(要望順)。開くとページ自身の"
                + "提案→プレビュー→承認の流れで解消します — IDE は第二の"
                + "取り込み経路を作りません。"))
                .font(.system(size: 10.5))
                .foregroundStyle(.secondary)
                .padding(.horizontal, 10)

            List(demand) { row in
                HStack {
                    Text(row.subject).font(.system(size: 12))
                    Spacer()
                    Text("×\(row.count)")
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(.secondary)
                    Button(app.t("Resolve", "解消する")) {
                        var c = URLComponents(
                            string: "https://verantyx.ai/vera3d/")!
                        c.queryItems = [.init(name: "q",
                                              value: "取得 " + row.subject)]
                        web = AuditWebRequest(url: c.url!,
                                              stamp: web.stamp + 1)
                        memory.remember(kind: "gap_resolved",
                                        subject: row.subject,
                                        detail: "opened in page for approval")
                    }
                    .font(.system(size: 10))
                }
            }
            .listStyle(.plain)

            if !demandNote.isEmpty {
                Text(demandNote).font(.system(size: 10))
                    .foregroundStyle(.secondary).padding(.horizontal, 10)
            }
            Divider().opacity(0.2)
            // Vector index — jgen's own encoder ranks which pending gaps a
            // document actually resolves. The basis is always shown: a
            // similarity whose basis is unknown is worse than none.
            Text(app.t("Which gaps does a document resolve?",
                       "この文書はどの欠落を埋めるか"))
                .font(.system(size: 10, weight: .semibold))
                .padding(.horizontal, 10)
            HStack(spacing: 6) {
                TextField(app.t("paste text or a subject…", "文章か主題を貼る…"),
                          text: $editRequest)
                    .textFieldStyle(.roundedBorder).font(.system(size: 10.5))
                Button(app.t("Rank", "順位")) { rankGaps() }
                    .font(.system(size: 10)).disabled(editRequest.isEmpty)
            }
            .padding(.horizontal, 10)
            if !vecNote.isEmpty {
                Text(vecNote).font(.system(size: 9.5))
                    .foregroundStyle(.secondary).padding(.horizontal, 10)
            }
            ForEach(vecHits) { h in
                HStack {
                    Text(h.subject).font(.system(size: 10.5))
                    Spacer()
                    Text(String(format: "%.3f", h.score))
                        .font(.system(size: 9.5, design: .monospaced))
                        .foregroundStyle(.secondary)
                }
                .padding(.horizontal, 12)
            }

            HStack {
                Button(app.t("Refresh", "更新")) {
                    Task { await refreshDemand() }
                }
                Button(app.t("Index gaps", "欠落を索引化")) { indexGaps() }
                .font(.system(size: 10.5))
                Spacer()
            }
            .font(.system(size: 10.5))
            .padding(10)
        }
    }

    private func refreshDemand() async {
        do {
            let (data, _) = try await URLSession.shared.data(
                from: URL(string: "https://verantyx.ai/api/vera/demand")!)
            let d = try JSONDecoder().decode(DemandReply.self, from: data)
            demand = d.demand ?? []
            demandNote = demand.isEmpty
                ? app.t("No pending requests.", "未処理の要望はありません。") : ""
        } catch {
            demandNote = app.t("Demand inlet unreachable.",
                               "要望APIに届きません。")
        }
    }

    // MARK: Edit — the same page's source, and the push that publishes it

    private var pagePath: String { repoPath + "/public/vera3d/index.html" }

    private var editPanel: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                TextField("~/Projects/verantyx-v6", text: $repoPath)
                    .textFieldStyle(.roundedBorder)
                    .font(.system(size: 11, design: .monospaced))
                Button(app.t("Open", "読込")) { loadEditor() }
                    .font(.system(size: 10.5))
            }
            .padding(.horizontal, 10)

            if !FileManager.default.fileExists(atPath: repoPath) {
                Button(app.t("Clone verantyx-v6 here", "ここに verantyx-v6 をクローン")) {
                    runGit(["clone",
                            "https://github.com/Ag3497120/verantyx-v6",
                            repoPath], in: nil)
                }
                .font(.system(size: 10.5)).padding(.horizontal, 10)
            }

            TextEditor(text: $editorText)
                .font(.system(size: 10, design: .monospaced))
                .frame(maxHeight: .infinity)
                .padding(.horizontal, 6)
                .overlay(alignment: .center) {
                    if !editorLoaded {
                        Text(app.t("Open the checkout to edit the page "
                                   + "source.",
                                   "読込を押すとページのソースを編集できます。"))
                            .font(.system(size: 11))
                            .foregroundStyle(.secondary)
                    }
                }

            HStack(spacing: 6) {
                Button(app.t("Preview edit", "編集をプレビュー")) {
                    // The edited HTML previews against the LIVE origin, so
                    // relative fetches (view3d.json, versions/) resolve to
                    // production — what you see is what a visitor gets.
                    web = AuditWebRequest(
                        url: URL(string: "https://verantyx.ai/vera3d/")!,
                        html: editorText, stamp: web.stamp + 1)
                }
                Button(app.t("Save", "保存")) { saveEditor() }
                Spacer()
            }
            .font(.system(size: 10.5))
            .padding(.horizontal, 10)

            // jgen draft: plain-language edit request -> HTML patch, which
            // the human then PREVIEWS and publishes. jgen shapes, the
            // person decides — the model never reaches the push.
            HStack(spacing: 6) {
                TextField(app.t("describe the edit for jgen…",
                                "編集内容を jgen に説明…"), text: $editRequest)
                    .textFieldStyle(.roundedBorder)
                    .font(.system(size: 10.5))
                Button(jgenBusy ? "…" : app.t("Draft", "下書き")) {
                    draftWithJGen()
                }
                .disabled(jgenBusy || !editorLoaded || editRequest.isEmpty)
                .font(.system(size: 10))
            }
            .padding(.horizontal, 10)
            if !jgenNote.isEmpty {
                Text(jgenNote).font(.system(size: 9.5))
                    .foregroundStyle(.secondary).padding(.horizontal, 10)
            }

            TextField(app.t("commit message", "コミットメッセージ"),
                      text: $commitMessage)
                .textFieldStyle(.roundedBorder)
                .font(.system(size: 11))
                .padding(.horizontal, 10)

            Button(busy ? app.t("Publishing…", "公開中…")
                        : app.t("Publish (commit & push)", "公開 (commit & push)")) {
                publish()
            }
            .disabled(busy || !editorLoaded)
            .font(.system(size: 11, weight: .semibold))
            .padding(.horizontal, 10)

            Text(app.t("Publishing is git push to verantyx-v6 — collaborator "
                       + "permission IS contributor permission; there is no "
                       + "second account system to get wrong.",
                       "公開は verantyx-v6 への git push です — GitHub の"
                       + "コラボレータ権限がそのまま貢献者権限。第二の認証は"
                       + "作りません。"))
                .font(.system(size: 9.5)).foregroundStyle(.secondary)
                .padding(.horizontal, 10)

            ScrollView {
                Text(gitLog)
                    .font(.system(size: 9.5, design: .monospaced))
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .textSelection(.enabled)
            }
            .frame(height: 110)
            .background(Color.black.opacity(0.25))
            .padding(10)
        }
    }

    private func loadEditor() {
        if let t = try? String(contentsOfFile: pagePath, encoding: .utf8) {
            editorText = t
            editorLoaded = true
            gitLog = "loaded \(pagePath)\n" + gitLog
        } else {
            gitLog = "cannot read \(pagePath)\n" + gitLog
        }
    }

    private func saveEditor() {
        do {
            try editorText.write(toFile: pagePath, atomically: true,
                                 encoding: .utf8)
            // The static export mirrors public/ — keep both in step so a
            // no-build deploy serves the same bytes.
            let outPath = repoPath + "/out/vera3d/index.html"
            try? editorText.write(toFile: outPath, atomically: true,
                                  encoding: .utf8)
            gitLog = "saved public/ and out/\n" + gitLog
        } catch {
            gitLog = "save failed: \(error.localizedDescription)\n" + gitLog
        }
    }

    private func publish() {
        busy = true
        let msg = commitMessage.isEmpty ? "vera3d: audited edit" : commitMessage
        DispatchQueue.global().async {
            let steps: [[String]] = [
                ["add", "public/vera3d", "out/vera3d"],
                ["commit", "-m", msg],
                ["push", "origin", "main"],
            ]
            for s in steps { runGitSync(s, in: repoPath, log: appendLog) }
            DispatchQueue.main.async {
                busy = false
                memory.remember(kind: "edit_applied", subject: "vera3d/index.html",
                                detail: msg)
            }
        }
    }

    private func appendLog(_ line: String) {
        DispatchQueue.main.async { gitLog = line + "\n" + gitLog }
    }

    private func draftWithJGen() {
        jgenBusy = true
        jgenNote = app.t("jgen drafting the edit…", "jgen が編集を下書き中…")
        let req = editRequest, cur = editorText, model = jgenModel
        let ep = app.ollamaEndpoint
        Task {
            if let out = await AuditJGen.draftEdit(endpoint: ep, request: req,
                                                   currentHTML: cur, model: model) {
                await MainActor.run {
                    editorText = out
                    jgenNote = app.t("Drafted — preview before publishing.",
                                     "下書き完了 — 公開前にプレビューを。")
                    jgenBusy = false
                }
            } else {
                await MainActor.run {
                    jgenNote = app.t("jgen unavailable (is ollama running?).",
                                     "jgen 未応答(ollama は起動していますか?)。")
                    jgenBusy = false
                }
            }
        }
    }

    // MARK: Memory — the task's context, forever

    private var memoryPanel: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(app.t(
                "Everlasting task memory. Every gap resolved and edit "
                + "published is recorded in a durable file and survives "
                + "restarts — the audit context is never lost, and re-reading "
                + "yields the same state (the memory is data).",
                "このタスクの永遠の記憶。解消した欠落と公開した編集はすべて"
                + "耐久ファイルに記録され、再起動しても失われません — 監査の"
                + "文脈は消えず、読み直せば同じ状態になります(記憶はデータ)。"))
                .font(.system(size: 10.5)).foregroundStyle(.secondary)
                .padding(.horizontal, 10)

            List(Array(memory.entries.reversed())) { e in
                VStack(alignment: .leading, spacing: 2) {
                    HStack {
                        Text(e.kind).font(.system(size: 9.5, weight: .semibold))
                            .foregroundStyle(kindColor(e.kind))
                        Text(e.subject).font(.system(size: 11))
                        Spacer()
                        Text(e.at, style: .time)
                            .font(.system(size: 9, design: .monospaced))
                            .foregroundStyle(.secondary)
                    }
                    if !e.detail.isEmpty {
                        Text(e.detail).font(.system(size: 9.5))
                            .foregroundStyle(.secondary).lineLimit(2)
                    }
                }
            }
            .listStyle(.plain)

            // Distributed jgen — declared, not faked. This machine has one
            // node; a 27B model across two Thunderbolt-linked Macs needs the
            // second node and its endpoint. The field is where that endpoint
            // goes, and until it answers, the panel says so instead of
            // pretending a large model is loaded.
            Divider().opacity(0.2)
            Text(app.t("Distributed jgen (2-Mac / Thunderbolt)",
                       "分散 jgen(2台Mac / Thunderbolt)"))
                .font(.system(size: 10, weight: .semibold)).padding(.horizontal, 10)
            // The IDE already discovers the other Mac (PipeDiscovery /
            // PipeConnectSheet, Bonjour over Thunderbolt). This panel used
            // to ask for the host again — a second path to the same peer,
            // which is exactly the duplication this project keeps refusing.
            // Prefer the paired peer; the field remains for the case
            // discovery cannot route.
            if let paired = PipeSession.shared.peer?.host, !paired.isEmpty {
                Text(app.t("paired peer: \(paired)", "接続中のピア: \(paired)"))
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 10)
                    .onAppear { if peerHost.isEmpty { peerHost = paired } }
            }
            HStack(spacing: 6) {
                TextField(app.t("peer host (or pair in Vera-a → connect)",
                                "ピアのホスト(または Vera-a の接続画面でペア)"),
                          text: $peerHost)
                    .textFieldStyle(.roundedBorder)
                    .font(.system(size: 10, design: .monospaced))
                Button(app.t("Check", "点検")) { checkSharding() }
                    .font(.system(size: 10))
                Button(shardProc == nil ? app.t("Start 27B", "27B起動")
                                        : app.t("Stop", "停止")) {
                    toggleShard()
                }
                .font(.system(size: 10))
            }
            .padding(.horizontal, 10)
            if !distNote.isEmpty {
                Text(distNote).font(.system(size: 9.5))
                    .foregroundStyle(.secondary).padding(.horizontal, 10)
                    .padding(.bottom, 8)
            }
        }
    }

    private func kindColor(_ k: String) -> Color {
        switch k {
        case "gap_resolved": return .green
        case "edit_applied": return .orange
        default:             return .secondary
        }
    }

    // MARK: Vector index — jgen's encoder over the pending gaps

    private func indexGaps() {
        let subjects = demand.map(\.subject)
        guard !subjects.isEmpty else {
            vecNote = app.t("Nothing to index yet.", "索引化する欠落がありません。")
            return
        }
        vecNote = app.t("indexing…", "索引化中…")
        Task {
            await AuditVectorIndex.shared.load()
            let n = await AuditVectorIndex.shared.index(subjects: subjects,
                                                        preferJGen: true)
            let basis = await AuditVectorIndex.shared.currentBasis()
            let total = await AuditVectorIndex.shared.count()
            await MainActor.run {
                vecBasis = basis.label
                vecNote = app.t("indexed \(n) new, \(total) total — basis: \(basis.label)",
                                "新規 \(n) 件・計 \(total) 件を索引化 — 基底: \(basis.label)")
            }
        }
    }

    private func rankGaps() {
        let q = editRequest
        vecNote = app.t("ranking…", "順位付け中…")
        Task {
            await AuditVectorIndex.shared.load()
            let (hits, basis) = await AuditVectorIndex.shared
                .nearest(to: q, limit: 8, preferJGen: true)
            await MainActor.run {
                vecHits = hits
                vecBasis = basis.label
                vecNote = hits.isEmpty
                    ? app.t("No ranking: index empty, or query and index are "
                            + "in different spaces (index the gaps first).",
                            "順位なし: 索引が空か、問いと索引の空間が違います"
                            + "(先に欠落を索引化してください)。")
                    : app.t("basis: \(basis.label)", "基底: \(basis.label)")
            }
        }
    }

    // MARK: Sharded jgen across two Macs

    private func checkSharding() {
        distNote = app.t("checking…", "点検中…")
        let host = peerHost
        Task {
            let r = await DistributedJGen.check(peerHost: host)
            await MainActor.run {
                if r.canShard {
                    distNote = app.t(
                        "Ready to shard: bridge \(r.bridge?.device ?? "-") "
                        + "\(r.bridge?.address ?? ""), peer up, mlx both sides.",
                        "分散可能: bridge \(r.bridge?.device ?? "-") "
                        + "\(r.bridge?.address ?? "")・ピア稼働・両側 mlx あり。")
                } else {
                    distNote = r.notes.joined(separator: "\n")
                }
            }
        }
    }

    private func toggleShard() {
        if let p = shardProc {
            p.terminate()
            shardProc = nil
            distNote = app.t("sharded server stopped", "分散サーバを停止しました")
            return
        }
        guard let bridge = DistributedJGen.thunderboltBridge() else {
            distNote = app.t("No Thunderbolt Bridge address — check first.",
                             "Thunderbolt Bridge のアドレスがありません — 先に点検を。")
            return
        }
        guard !peerHost.isEmpty else {
            distNote = app.t("Set the peer host first.", "先にピアのホストを設定してください。")
            return
        }
        if let p = DistributedJGen.launchSharded(
            model: "mlx-community/Qwen3-27B-4bit",
            local: bridge.address, peer: peerHost) {
            shardProc = p
            app.ollamaEndpoint = "http://127.0.0.1:8081"
            distNote = app.t(
                "Sharded server starting on the ring; drafting now points at "
                + "127.0.0.1:8081. First load takes minutes.",
                "リング上で分散サーバを起動中。下書きは 127.0.0.1:8081 を"
                + "使います。初回ロードは数分かかります。")
            memory.remember(kind: "note", subject: "sharded jgen",
                            detail: "ring \(bridge.address) + \(peerHost)")
        } else {
            distNote = app.t("Launch failed — is python3 -m mlx_lm.launch available?",
                             "起動に失敗 — python3 -m mlx_lm.launch はありますか?")
        }
    }

    private func probePeer() {
        distNote = app.t("probing…", "確認中…")
        Task {
            guard let url = URL(string: app.ollamaEndpoint + "/api/tags") else { return }
            if let (data, _) = try? await URLSession.shared.data(from: url),
               let s = String(data: data, encoding: .utf8) {
                let big = s.contains("27b") || s.contains("32b") || s.contains("70b")
                await MainActor.run {
                    distNote = big
                        ? app.t("peer up, large model present — set jgen model to it",
                                "ピア稼働・大型モデルあり — jgen モデルに指定してください")
                        : app.t("peer up; no ≥27B model listed there yet",
                                "ピア稼働・27B以上のモデルは未登録")
                }
            } else {
                await MainActor.run {
                    distNote = app.t(
                        "no peer at that endpoint. Link two Macs by "
                        + "Thunderbolt, run `OLLAMA_HOST=0.0.0.0 ollama serve` "
                        + "on the peer, pull qwen3.6:27b there, and point here.",
                        "そのエンドポイントにピアがいません。2台をThunderboltで"
                        + "接続し、ピア側で `OLLAMA_HOST=0.0.0.0 ollama serve` を"
                        + "実行、qwen3.6:27b を pull してここに指定してください。")
                }
            }
        }
    }

    private func runGit(_ args: [String], in dir: String?) {
        DispatchQueue.global().async {
            runGitSync(args, in: dir, log: appendLog)
        }
    }
}

private func runGitSync(_ args: [String], in dir: String?,
                        log: @escaping (String) -> Void) {
    let p = Process()
    p.executableURL = URL(fileURLWithPath: "/usr/bin/git")
    p.arguments = args
    if let dir { p.currentDirectoryURL = URL(fileURLWithPath: dir) }
    let pipe = Pipe()
    p.standardOutput = pipe
    p.standardError = pipe
    do {
        try p.run()
        p.waitUntilExit()
        let out = String(data: pipe.fileHandleForReading.readDataToEndOfFile(),
                         encoding: .utf8) ?? ""
        log("$ git \(args.joined(separator: " "))\n"
            + out.trimmingCharacters(in: .whitespacesAndNewlines)
            + (p.terminationStatus == 0 ? "" : "\n(exit \(p.terminationStatus))"))
    } catch {
        log("git failed: \(error.localizedDescription)")
    }
}
