import SwiftUI

/// 取得 — the first screen a new user needs, and the one that was missing.
///
/// Installing the app used to leave you with an engine and nothing to ask it
/// about: the knowledge store lives outside the bundle (it is ~209 MB), and
/// the only way to get one was a terminal. This screen closes that, and keeps
/// the engine's rule while doing it — **nothing downloads implicitly**. The
/// status is answered first, in the same typed shape every absence uses here
/// (`UNKNOWN_NO_STORE` + how to close it), and the download happens because a
/// person pressed a button.
///
/// It deliberately shows what the base store *is* before offering it. A reader
/// who benchmarks English film prose as domain knowledge concludes the engine
/// is bad; a reader who was told first concludes the corpus is wrong, which is
/// the truth.
struct StoreBootstrapView: View {
    @EnvironmentObject var app: AppState

    @State private var status: [String: Any] = [:]
    @State private var available: [[String: Any]] = []
    @State private var listVerdict = ""
    @State private var selected = ""
    @State private var stats: [String: Any] = [:]
    @State private var busy = false
    @State private var message = ""
    @State private var loadError: String? = nil

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            header
            if let err = loadError {
                unavailable(err)
            } else {
                statusCard
                if !hasStore { offerCard }
                pourCard
            }
            Spacer(minLength: 0)
        }
        .padding(14)
        .task { await load() }
    }

    private var hasStore: Bool {
        (status["verdict"] as? String) == "ANSWER"
    }

    private var header: some View {
        HStack(spacing: 8) {
            Text(app.t("Knowledge store", "知識エンジンの取得"))
                .font(.system(size: 12, weight: .semibold))
            if busy { ProgressView().controlSize(.small) }
            Spacer()
            Button(app.t("Reload", "再読込")) { Task { await load() } }
                .font(.system(size: 10))
                .disabled(busy)
        }
    }

    private func unavailable(_ err: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(app.t("The engine did not answer.", "エンジンが答えませんでした。"))
                .font(.system(size: 11, weight: .semibold))
            Text(err).font(.system(size: 9, design: .monospaced))
                .foregroundStyle(.secondary).textSelection(.enabled)
        }
    }

    // MARK: - status

    private var statusCard: some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack(spacing: 8) {
                Circle().fill(hasStore ? Color.green : Color.orange)
                    .frame(width: 7, height: 7)
                Text(hasStore
                     ? app.t("A store is loaded", "店があります")
                     : app.t("No store on this machine yet",
                             "この機械にはまだ店がありません"))
                    .font(.system(size: 11, weight: .medium))
            }
            if hasStore {
                let bytes = (status["bytes"] as? Int) ?? 0
                Text("\(status["path"] as? String ?? "") · "
                     + ByteCountFormatter.string(fromByteCount: Int64(bytes),
                                                 countStyle: .file))
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(.secondary)
                if let cores = stats["cores"] as? Int {
                    Text(app.t("\(cores) cores · \(stats["facet_links"] as? Int ?? 0) facet links",
                               "核 \(cores) ・ 面のつながり \(stats["facet_links"] as? Int ?? 0)"))
                        .font(.system(size: 10))
                }
            } else {
                // 不在は不在として型で出す。空欄で誤魔化さない。
                Text(status["verdict"] as? String ?? "—")
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(.orange)
            }
            if !message.isEmpty {
                Text(message).font(.system(size: 10))
                    .foregroundStyle(message.hasPrefix("UNKNOWN")
                                     || message.hasPrefix("error") ? .orange : .green)
            }
        }
    }

    // MARK: - offer

    private var offerCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(app.t("Option A — download a published store",
                       "方法A — 公開されている店を取得する"))
                .font(.system(size: 11, weight: .semibold))
            // 版が増えても画面を直さなくて済むよう、固定するのは配布元の
            // アカウントだけ。一覧は毎回読む。
            if listVerdict == "UNKNOWN_OFFLINE" {
                Text(app.t("Cannot list right now — no network. A store "
                           + "already on disk does not need this.",
                           "いま一覧できません(網に繋がらない)。手元に店が"
                           + "あるならこれは要りません。"))
                    .font(.system(size: 10)).foregroundStyle(.orange)
            } else if available.isEmpty {
                Text(listVerdict.isEmpty
                     ? app.t("Reading the published list…", "公開一覧を読んでいます…")
                     : listVerdict)
                    .font(.system(size: 10)).foregroundStyle(.secondary)
            }
            ForEach(Array(available.enumerated()), id: \.offset) { _, st in
                let repo = st["repo"] as? String ?? ""
                let bytes = (st["bytes"] as? Int) ?? 0
                Button {
                    selected = repo
                } label: {
                    HStack(alignment: .top, spacing: 8) {
                        Image(systemName: selected == repo
                              ? "largecircle.fill.circle" : "circle")
                            .font(.system(size: 11))
                        VStack(alignment: .leading, spacing: 1) {
                            Text(repo).font(.system(size: 10, weight: .medium))
                            Text((bytes > 0
                                  ? ByteCountFormatter.string(
                                      fromByteCount: Int64(bytes),
                                      countStyle: .file) + " · "
                                  : "")
                                 + String((st["last_modified"] as? String ?? "")
                                          .prefix(10)))
                                .font(.system(size: 9, design: .monospaced))
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                    }
                }
                .buttonStyle(.plain)
            }
            Text(app.t("The base store is English film and biography prose "
                       + "(889,241 cores): enough to watch the engine answer "
                       + "and refuse honestly, and measurably NOT domain "
                       + "knowledge — in it, 'print' means printed matter.",
                       "基礎の店は英語の映画・人物の散文(核 889,241)です。"
                       + "エンジンが答え、正直に断る様子を見るには十分ですが、"
                       + "**分野知識ではありません** — この店の print は"
                       + "「印刷物」の意味です。"))
                .font(.system(size: 9)).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            HStack(spacing: 8) {
                Button(app.t("Download", "取得する")) {
                    Task { await fetch(selected) }
                }
                .font(.system(size: 10))
                .disabled(busy || selected.isEmpty)
                if let url = (available.first { ($0["repo"] as? String) == selected }?["url"]) as? String,
                   let u = URL(string: url) {
                    Link(app.t("dataset card", "データセットカード"), destination: u)
                        .font(.system(size: 10))
                }
                Button(app.t("Refresh list", "一覧を再読込")) {
                    Task { await loadList() }
                }
                .font(.system(size: 10)).disabled(busy)
            }
            if busy {
                Text(app.t("Downloading — a few minutes on a first run, and "
                           + "nothing is kept until it finishes.",
                           "取得中 — 初回は数分かかります。完了するまで途中"
                           + "結果は残りません。"))
                    .font(.system(size: 9)).foregroundStyle(.secondary)
            }
        }
    }

    // MARK: - pour your own

    private var pourCard: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(app.t("Option B — pour your own documents (what real work needs)",
                       "方法B — 自分の文書を注ぐ(実務はこちら)"))
                .font(.system(size: 11, weight: .semibold))
            Text(app.t("The 文書 tab loads PDF, Word, HTML, CSV, JSON and text, "
                       + "and a folder is walked. Answers then quote your own "
                       + "documents, and anything you did not load is refused.",
                       "「文書」タブから PDF・Word・HTML・CSV・JSON・テキストを"
                       + "読み込めます(フォルダ可)。以後は自分の文書を引用して"
                       + "答え、入れていないことは断ります。"))
                .font(.system(size: 9))
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    // MARK: - doors

    private func parse(_ raw: String) -> [String: Any]? {
        guard let data = raw.data(using: .utf8) else { return nil }
        return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
    }

    private func call(_ tool: String,
                      _ args: [String: Any] = [:]) async -> String {
        await MCPEngine.shared.callTool(serverName: "vera-memory",
                                        toolName: tool, arguments: args)
    }

    private func load() async {
        let raw = await call("store_status")
        guard let obj = parse(raw) else {
            loadError = String(raw.prefix(200))
            return
        }
        loadError = nil
        status = obj
        if (obj["verdict"] as? String) == "ANSWER" {
            stats = parse(await call("stats")) ?? [:]
        } else {
            await loadList()
        }
    }

    private func loadList() async {
        let raw = await call("list_base_stores", ["verify": true])
        let obj = parse(raw) ?? [:]
        listVerdict = obj["verdict"] as? String ?? ""
        available = obj["stores"] as? [[String: Any]] ?? []
        if selected.isEmpty {
            selected = (obj["default"] as? String)
                ?? (available.first?["repo"] as? String ?? "")
        }
    }

    private func fetch(_ repo: String) async {
        busy = true
        message = app.t("Downloading…", "取得しています…")
        defer { busy = false }
        let raw = await call("fetch_base_store", ["repo": repo])
        let obj = parse(raw) ?? [:]
        if (obj["ok"] as? Bool) == true {
            message = app.t("Store downloaded.", "店を取得しました。")
        } else {
            message = (obj["error"] as? String) ?? String(raw.prefix(160))
        }
        await load()
    }
}
