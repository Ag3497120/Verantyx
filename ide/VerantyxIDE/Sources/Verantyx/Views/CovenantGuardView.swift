import SwiftUI

/// 番人 — the covenant guard, as a screen.
///
/// The guard is the one place this engine beats a language model outright:
/// it holds what the user settled, checks a reply against it deterministically,
/// and names the promises whose compliance is DROPPING. None of that is
/// visible from a terminal hook, and what nobody can see, nobody trusts.
///
/// Every number here comes from a door; this view owns no state of its own.
/// Two rules it inherits from the engine and must not soften:
///
/// * **What a regex read cannot block.** Covenants extracted from an
///   instruction land in quarantine — they are shadow-checked and shown, but
///   only what the person adopted can stop a reply. So candidates appear in
///   their own section with an explicit adopt, never auto-promoted.
/// * **Retirement is an entry, not a deletion.** Releasing a covenant keeps
///   it in the ledger; the button says 退役 for that reason.
struct CovenantGuardView: View {
    @EnvironmentObject var app: AppState

    @State private var health: [String: Any] = [:]
    @State private var covenants: [[String: Any]] = []
    @State private var candidates: [[String: Any]] = []
    @State private var fading: [[String: Any]] = []
    @State private var queues: [[String: Any]] = []
    @State private var waitingTotal = 0
    @State private var newQuote = ""
    @State private var newForbids = ""
    @State private var newRequires = ""
    @State private var newTopic = ""
    @State private var registerResult = ""
    @State private var indexQuery = ""
    @State private var indexHits: [[String: Any]] = []
    @State private var indexVerdict = ""
    @State private var loadError: String? = nil
    @State private var loading = false
    @State private var busy: String? = nil

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Divider().opacity(0.2)
            if let err = loadError {
                unavailable(err)
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        healthSection
                        registerSection
                        covenantSection
                        candidateSection
                        fadingSection
                        pendingSection
                        indexSection
                    }
                    .padding(14)
                }
            }
        }
        .task { await load() }
    }

    // MARK: - header

    private var header: some View {
        HStack(spacing: 8) {
            Text(app.t("Covenant guard", "番人 — 約束の台帳"))
                .font(.system(size: 12, weight: .semibold))
            if loading || busy != nil {
                ProgressView().controlSize(.small)
            }
            Spacer()
            Button(app.t("Reload", "再読込")) { Task { await load() } }
                .font(.system(size: 10))
        }
        .padding(.horizontal, 12).padding(.vertical, 8)
    }

    private func unavailable(_ err: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(app.t("The guard did not answer.",
                       "番人が答えませんでした。"))
                .font(.system(size: 11, weight: .semibold))
            // 「答えない」と「守るものが無い」を同じ顔にしない。
            Text(app.t("This is not the same as 'nothing to enforce' — the "
                       + "vera-memory server is unreachable or out of date.",
                       "これは「守る約束が無い」とは別です — vera-memory が"
                       + "届いていないか、古い版です。"))
                .font(.system(size: 10))
                .foregroundStyle(.secondary)
            Text(err).font(.system(size: 9, design: .monospaced))
                .foregroundStyle(.secondary).textSelection(.enabled)
            // 実地で踏んだ: ビルドで実体が入れ替わった瞬間に接続が失敗すると、
            // その失敗が残り続ける。画面から繋ぎ直せないと、動いている
            // エンジンを前にして「壊れている」ようにしか見えない。
            HStack(spacing: 8) {
                Button(app.t("Reconnect vera-memory", "vera-memory に接続し直す")) {
                    Task { await reconnect() }
                }
                .font(.system(size: 10))
                .disabled(busy != nil)
                if busy == "reconnect" { ProgressView().controlSize(.small) }
            }
            .padding(.top, 4)
        }
        .padding(14)
    }

    /// 繋ぎ直して読み直す。落ちたままの接続は、engine の故障と区別が
    /// つかない見え方をするので、ここで一手で解けるようにしておく。
    private func reconnect() async {
        busy = "reconnect"
        defer { busy = nil }
        let engine = MCPEngine.shared
        if let server = engine.servers.first(where: {
            $0.name == "vera-memory"
        }) {
            engine.disconnect(serverId: server.id)
            await engine.connect(server: server)
        }
        await load()
    }

    private func section<T: View>(_ title: String, _ subtitle: String,
                                  @ViewBuilder _ content: () -> T) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title).font(.system(size: 11, weight: .semibold))
            if !subtitle.isEmpty {
                Text(subtitle).font(.system(size: 9))
                    .foregroundStyle(.secondary)
            }
            content()
        }
    }

    // MARK: - health

    private var healthSection: some View {
        let verdict = health["verdict"] as? String ?? "—"
        let guardFace = (health["guard"] as? [String: Any])?["verdict"]
            as? String ?? "—"
        let standalone = (health["standalone"] as? [String: Any])?["verdict"]
            as? String ?? "—"
        let wiring = (health["wiring"] as? [String: Any])?["verdict"]
            as? String ?? "—"
        let problems = (health["wiring"] as? [String: Any])?["problems"]
            as? [String] ?? []
        return section(app.t("Health", "健康"),
                       app.t("re-run here and now, not a stored result",
                             "保存された結果ではなく、今この場で走らせた結果")) {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 10) {
                    badge(verdict, color: verdictColor(verdict))
                    Text(app.t("guard \(guardFace) · standalone \(standalone)"
                               + " · wiring \(wiring)",
                               "番人 \(guardFace) ・ 単体 \(standalone)"
                               + " ・ 配線 \(wiring)"))
                        .font(.system(size: 10))
                        .foregroundStyle(.secondary)
                }
                // 配線の問題は黙って飲み込まない — 素通しになっていても
                // 画面は平常に見えるのが、この装置の一番危ない壊れ方。
                ForEach(problems.prefix(4), id: \.self) { p in
                    Text("· \(p)").font(.system(size: 9))
                        .foregroundStyle(.orange)
                }
            }
        }
    }

    private func verdictColor(_ v: String) -> Color {
        switch v {
        case "OK": return .green
        case "DEGRADED": return .orange
        case "BROKEN": return .red
        default: return .secondary
        }
    }

    private func badge(_ text: String, color: Color) -> some View {
        Text(text)
            .font(.system(size: 9, weight: .bold))
            .padding(.horizontal, 6).padding(.vertical, 2)
            .background(RoundedRectangle(cornerRadius: 4)
                .fill(color.opacity(0.18)))
            .foregroundStyle(color)
    }

    // MARK: - register (フックが読む前に、人が約束を置く場所)

    /// **執行に入るのはここで登録したものだけ**。指示文から規則が読んだ
    /// ものは隔離席に入り、遮断はできない(誤読が作業を止めないため)。
    /// だから「守らせたい」と本気で思ったことは、人がここに置く。
    private var registerSection: some View {
        section(app.t("Register a covenant", "約束を登録する"),
                app.t("only what you register here can stop a reply",
                      "返答を止められるのは、ここで登録したものだけ")) {
            VStack(alignment: .leading, spacing: 6) {
                TextField(app.t("your own sentence, quoted back on breach",
                                "あなたの言葉のまま(破ったときそのまま示す)"),
                          text: $newQuote)
                    .textFieldStyle(.roundedBorder).font(.system(size: 10))
                HStack(spacing: 6) {
                    TextField(app.t("forbid (comma separated)",
                                    "禁止(カンマ区切り)"), text: $newForbids)
                        .textFieldStyle(.roundedBorder).font(.system(size: 10))
                    TextField(app.t("require (comma separated)",
                                    "要求(カンマ区切り)"), text: $newRequires)
                        .textFieldStyle(.roundedBorder).font(.system(size: 10))
                }
                HStack(spacing: 6) {
                    TextField(app.t("scope terms — empty means always on",
                                    "適用範囲の語 — 空なら常時"),
                              text: $newTopic)
                        .textFieldStyle(.roundedBorder).font(.system(size: 10))
                    Button(app.t("Register", "登録")) {
                        Task { await register() }
                    }
                    .font(.system(size: 10))
                    .disabled(busy != nil || newQuote.trimmingCharacters(
                        in: .whitespaces).isEmpty
                        || (newForbids.trimmingCharacters(in: .whitespaces)
                            .isEmpty
                            && newRequires.trimmingCharacters(in: .whitespaces)
                            .isEmpty))
                }
                // 範囲を空にすると、その話でない返答にも発火する。
                // 毎ターン鳴る番人は二日で切られる、が実地の教訓。
                Text(app.t("A covenant with no scope fires on replies that "
                           + "were never about it.",
                           "範囲が空の約束は、その話でない返答にも発火します。"))
                    .font(.system(size: 9)).foregroundStyle(.secondary)
                if !registerResult.isEmpty {
                    Text(registerResult).font(.system(size: 9))
                        .foregroundStyle(registerResult.hasPrefix("UNKNOWN")
                                         ? .orange : .green)
                }
            }
        }
    }

    // MARK: - covenants in force

    private var covenantSection: some View {
        let live = covenants.filter {
            ($0["retired"] as? Bool) != true
                && (($0["status"] as? String) ?? "adopted") == "adopted"
        }
        return section(app.t("In force (\(live.count))",
                             "執行中 (\(live.count))"),
                       app.t("only these can block a reply",
                             "返答を遮断できるのはこれだけ")) {
            if live.isEmpty {
                Text(app.t("Nothing registered yet.", "まだ登録がありません。"))
                    .font(.system(size: 10)).foregroundStyle(.secondary)
            }
            ForEach(Array(live.enumerated()), id: \.offset) { _, c in
                HStack(alignment: .top, spacing: 8) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(quote(c)).font(.system(size: 10))
                        Text(terms(c)).font(.system(size: 9, design: .monospaced))
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button(app.t("Retire", "退役")) {
                        Task { await retire(name(c)) }
                    }
                    .font(.system(size: 9))
                    .disabled(busy != nil)
                }
                .padding(.vertical, 3)
                Divider().opacity(0.12)
            }
        }
    }

    // MARK: - quarantine

    private var candidateSection: some View {
        section(app.t("Quarantine (\(candidates.count))",
                      "隔離席 (\(candidates.count))"),
                app.t("read by rule, never enforced until adopted",
                      "規則が読んだ候補。採用するまで執行されない")) {
            if candidates.isEmpty {
                Text(app.t("No candidates waiting.", "待っている候補はありません。"))
                    .font(.system(size: 10)).foregroundStyle(.secondary)
            }
            ForEach(Array(candidates.enumerated()), id: \.offset) { _, c in
                HStack(alignment: .top, spacing: 8) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(c["quote"] as? String
                             ?? c["covenant"] as? String ?? "—")
                            .font(.system(size: 10))
                        let checks = c["checks"] as? Int ?? 0
                        let hits = c["hits"] as? Int ?? 0
                        Text("\(c["verdict"] as? String ?? "") · "
                             + app.t("checked \(checks), fired \(hits)",
                                     "照合 \(checks) 回・発火 \(hits) 回"))
                            .font(.system(size: 9))
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    // 推薦は自動採用ではない。門は人のまま。
                    Button(app.t("Adopt", "採用")) {
                        Task { await adopt(c["covenant"] as? String ?? "") }
                    }
                    .font(.system(size: 9))
                    .disabled(busy != nil)
                }
                .padding(.vertical, 3)
                Divider().opacity(0.12)
            }
        }
    }

    // MARK: - fading

    private var fadingSection: some View {
        section(app.t("Fading (\(fading.count))", "薄れている (\(fading.count))"),
                app.t("compliance is dropping against its own past — these "
                      + "are the ones worth re-sending",
                      "自分の過去と比べて守れなくなっている約束。再注入する"
                      + "価値があるのはこれだけ")) {
            if fading.isEmpty {
                Text(app.t("Nothing is fading.", "薄れている約束はありません。"))
                    .font(.system(size: 10)).foregroundStyle(.secondary)
            }
            ForEach(Array(fading.enumerated()), id: \.offset) { _, f in
                let before = f["kept_before"] as? Double ?? 0
                let now = f["kept_recently"] as? Double ?? 0
                HStack(spacing: 8) {
                    Text(f["quote"] as? String
                         ?? f["covenant"] as? String ?? "—")
                        .font(.system(size: 10))
                    Spacer()
                    Text(String(format: "%.0f%% → %.0f%%", before * 100,
                                now * 100))
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(.orange)
                }
                .padding(.vertical, 2)
            }
        }
    }

    // MARK: - pending decisions

    private var pendingSection: some View {
        section(app.t("Waiting for a person (\(waitingTotal))",
                      "人の判断待ち (\(waitingTotal))"),
                app.t("every queue that owns items, and the door that closes it",
                      "各待ち行列と、それを閉じる扉")) {
            ForEach(Array(queues.enumerated()), id: \.offset) { _, q in
                let n = q["waiting"] as? Int
                HStack(spacing: 8) {
                    Text(q["kind"] as? String ?? "—")
                        .font(.system(size: 10, design: .monospaced))
                    Spacer()
                    Text(n.map { "\($0)" } ?? "UNKNOWN")
                        .font(.system(size: 10, weight: n ?? 0 > 0
                                      ? .bold : .regular))
                        .foregroundStyle(n ?? 0 > 0 ? .primary : .secondary)
                }
                .padding(.vertical, 1)
            }
        }
    }

    // MARK: - capability index

    private var indexSection: some View {
        section(app.t("Does it already exist?", "それは既に在るか"),
                app.t("search the doors, commands, modules, forks and papers "
                      + "before building anything",
                      "作る前に、扉・命令・モジュール・fork・事前登録を引く")) {
            HStack(spacing: 6) {
                TextField(app.t("e.g. retire a covenant", "例: 約束 破棄"),
                          text: $indexQuery)
                    .textFieldStyle(.roundedBorder)
                    .font(.system(size: 10))
                    .onSubmit { Task { await searchIndex() } }
                Button(app.t("Search", "検索")) {
                    Task { await searchIndex() }
                }
                .font(.system(size: 10))
            }
            if indexVerdict == "UNKNOWN_NOT_FOUND" {
                // 無いものに似た名前を返さない、をそのまま画面にも出す。
                Text(app.t("Nothing here matches — that is an answer, not a "
                           + "failure: it is not built yet.",
                           "一致するものはありません。これは失敗ではなく答え"
                           + "です — まだ在りません。"))
                    .font(.system(size: 10)).foregroundStyle(.orange)
            }
            ForEach(Array(indexHits.enumerated()), id: \.offset) { _, h in
                HStack(alignment: .top, spacing: 6) {
                    Text(h["kind"] as? String ?? "")
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(.secondary)
                        .frame(width: 58, alignment: .leading)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(h["name"] as? String ?? "")
                            .font(.system(size: 10, weight: .medium))
                        Text(h["where"] as? String ?? "")
                            .font(.system(size: 9, design: .monospaced))
                            .foregroundStyle(.secondary)
                    }
                }
                .padding(.vertical, 1)
            }
        }
    }

    // MARK: - doors

    private func name(_ c: [String: Any]) -> String {
        c["name"] as? String ?? ""
    }

    private func quote(_ c: [String: Any]) -> String {
        let q = c["quote"] as? String ?? ""
        return q.isEmpty ? name(c) : q
    }

    private func terms(_ c: [String: Any]) -> String {
        let forbids = (c["forbids"] as? [String] ?? []).joined(separator: ", ")
        let requires = (c["requires"] as? [String] ?? []).joined(separator: ", ")
        var parts: [String] = []
        if !forbids.isEmpty { parts.append("禁止: \(forbids)") }
        if !requires.isEmpty { parts.append("要求: \(requires)") }
        return parts.joined(separator: "  ")
    }

    private func parse(_ raw: String) -> [String: Any]? {
        guard let data = raw.data(using: .utf8) else { return nil }
        return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
    }

    private func parseArray(_ raw: String) -> [[String: Any]]? {
        guard let data = raw.data(using: .utf8) else { return nil }
        return (try? JSONSerialization.jsonObject(with: data))
            as? [[String: Any]]
    }

    private func call(_ tool: String,
                      _ args: [String: Any] = [:]) async -> String {
        await MCPEngine.shared.callTool(serverName: "vera-memory",
                                        toolName: tool, arguments: args)
    }

    private func load() async {
        loading = true
        defer { loading = false }

        let doctorRaw = await call("vera_doctor")
        guard let doctor = parse(doctorRaw) else {
            loadError = String(doctorRaw.prefix(200))
            return
        }
        loadError = nil
        health = doctor

        let listRaw = await call("list_covenants")
        covenants = parseArray(listRaw)
            ?? (parse(listRaw)?["covenants"] as? [[String: Any]] ?? [])

        let revRaw = await call("review_candidates")
        candidates = (parse(revRaw)?["rows"] as? [[String: Any]] ?? [])

        let fadeRaw = await call("fading_covenants")
        fading = (parse(fadeRaw)?["fading"] as? [[String: Any]] ?? [])

        let pendRaw = await call("pending_decisions")
        let pend = parse(pendRaw) ?? [:]
        queues = pend["queues"] as? [[String: Any]] ?? []
        waitingTotal = pend["waiting_total"] as? Int ?? 0
    }

    private func register() async {
        let quote = newQuote.trimmingCharacters(in: .whitespaces)
        guard !quote.isEmpty else { return }
        busy = "register"
        defer { busy = nil }
        // 名前は引用の頭を使う(人が後で見て分かる名前になる)。
        let name = String(quote.prefix(40))
        let raw = await call("set_covenant", [
            "name": name,
            "forbids": newForbids.trimmingCharacters(in: .whitespaces),
            "requires": newRequires.trimmingCharacters(in: .whitespaces),
            "topic": newTopic.trimmingCharacters(in: .whitespaces),
            "quote": quote,
        ])
        let obj = parse(raw) ?? [:]
        let verdict = obj["verdict"] as? String ?? "?"
        let inForce = obj["in_force"] as? Int ?? 0
        registerResult = verdict == "ANSWER"
            ? app.t("registered · in force \(inForce)",
                    "登録しました ・ 執行中 \(inForce) 件")
            : String(raw.prefix(120))
        if verdict == "ANSWER" {
            newQuote = ""; newForbids = ""; newRequires = ""; newTopic = ""
        }
        await load()
    }

    private func adopt(_ name: String) async {
        guard !name.isEmpty else { return }
        busy = name
        defer { busy = nil }
        _ = await call("adopt_covenant", ["name": name])
        await load()
    }

    private func retire(_ name: String) async {
        guard !name.isEmpty else { return }
        busy = name
        defer { busy = nil }
        _ = await call("retire_covenant",
                       ["name": name,
                        "quote": app.t("released from the IDE",
                                       "IDE から解除")])
        await load()
    }

    private func searchIndex() async {
        let q = indexQuery.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !q.isEmpty else { return }
        busy = "index"
        defer { busy = nil }
        let raw = await call("capability_index", ["query": q, "limit": 8])
        let obj = parse(raw) ?? [:]
        indexVerdict = obj["verdict"] as? String ?? ""
        indexHits = obj["hits"] as? [[String: Any]] ?? []
    }
}
