import SwiftUI

/// Growth — the "what the system does not know" screens, in one place.
///
/// The growth signals (typed UNKNOWN buckets), the gap graph's wake summary,
/// and the approval queues were scattered across panels, which buried the
/// property this whole system is built around: it KNOWS what it does not
/// know, in types, with counts. A reader who cannot see the unknowns in one
/// view has no way to watch them shrink — and watching them shrink is what
/// "the system is learning" honestly means here. No model, no vibes: every
/// number on this screen is a count of typed failures or pending reviews.
struct GrowthDashboardView: View {
    @EnvironmentObject var app: AppState

    @State private var verdicts: [(String, Int)] = []
    @State private var buckets: [[String: Any]] = []
    @State private var wake: [String: Any] = [:]
    @State private var pending: [(String, Int)] = []
    @State private var loadError: String? = nil
    @State private var loading = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Divider().opacity(0.2)
            if let err = loadError {
                unavailable(err)
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        verdictSection
                        bucketSection
                        wakeSection
                        pendingSection
                    }
                    .padding(14)
                }
            }
        }
        .task { await load() }
    }

    private var header: some View {
        HStack {
            VStack(alignment: .leading, spacing: 3) {
                Text(app.t("Growth — what the system does not know",
                           "Growth — システムが知らないこと"))
                    .font(.system(size: 14, weight: .bold))
                Text(app.t(
                    "Typed unknowns, the gap graph, and the review queues. "
                    + "Learning here means these numbers shrink.",
                    "型付き未知・ギャップグラフ・承認待ち。ここの数字が減ることが、"
                    + "この系での「学習」の正直な意味です。"))
                    .font(.system(size: 10.5)).foregroundStyle(.secondary)
            }
            Spacer()
            Button {
                Task { await load() }
            } label: {
                Image(systemName: "arrow.clockwise")
            }
            .disabled(loading)
        }
        .padding(12)
    }

    // MARK: - Sections

    private var verdictSection: some View {
        card(title: app.t("Typed failures", "型付き失敗の内訳"),
             icon: "chart.bar.fill") {
            if verdicts.isEmpty {
                Text(app.t("No typed failures recorded yet.",
                           "記録された型付き失敗はまだありません。"))
                    .font(.system(size: 11)).foregroundStyle(.secondary)
            }
            let maxN = max(verdicts.map(\.1).max() ?? 1, 1)
            ForEach(verdicts, id: \.0) { name, n in
                HStack(spacing: 8) {
                    Text(name)
                        .font(.system(size: 10.5, design: .monospaced))
                        .frame(width: 230, alignment: .leading)
                    GeometryReader { geo in
                        RoundedRectangle(cornerRadius: 2)
                            .fill(name.contains("UNCLASSIFIED")
                                  ? Color.orange : Color.accentColor.opacity(0.75))
                            .frame(width: max(3, geo.size.width
                                              * CGFloat(n) / CGFloat(maxN)))
                    }
                    .frame(height: 10)
                    Text("\(n)")
                        .font(.system(size: 10.5, design: .monospaced))
                        .frame(width: 34, alignment: .trailing)
                }
            }
        }
    }

    private var bucketSection: some View {
        card(title: app.t("Recurring unknown buckets", "繰り返す未知のバケット"),
             icon: "tray.2") {
            if buckets.isEmpty {
                Text(app.t("No recurring buckets.", "繰り返しはありません。"))
                    .font(.system(size: 11)).foregroundStyle(.secondary)
            }
            ForEach(Array(buckets.prefix(10).enumerated()), id: \.offset) { _, b in
                VStack(alignment: .leading, spacing: 2) {
                    Text((b["normalized"] as? String ?? "?").prefix(70))
                        .font(.system(size: 11, weight: .semibold))
                    HStack(spacing: 10) {
                        Text("×\(b["total"] as? Int ?? 0)")
                        Text(b["dominant"] as? String ?? "")
                            .font(.system(size: 10, design: .monospaced))
                        Text(b["classification"] as? String ?? "")
                            .foregroundStyle(Color.accentColor)
                    }
                    .font(.system(size: 10)).foregroundStyle(.secondary)
                }
                .padding(6)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.white.opacity(0.04))
                .clipShape(RoundedRectangle(cornerRadius: 5))
            }
        }
    }

    private var wakeSection: some View {
        card(title: app.t("Gap graph — wake summary",
                          "ギャップグラフ — 覚醒サマリ"),
             icon: "point.3.connected.trianglepath.dotted") {
            if wake.isEmpty {
                Text(app.t("No gap activity in the window.",
                           "期間内のギャップ活動はありません。"))
                    .font(.system(size: 11)).foregroundStyle(.secondary)
            } else {
                ForEach(wake.keys.sorted(), id: \.self) { key in
                    HStack {
                        Text(key).font(.system(size: 10.5, design: .monospaced))
                        Spacer()
                        Text(shortValue(wake[key]))
                            .font(.system(size: 10.5))
                            .foregroundStyle(.secondary)
                            .lineLimit(2)
                    }
                }
            }
        }
    }

    private var pendingSection: some View {
        card(title: app.t("Awaiting your review", "あなたの承認待ち"),
             icon: "person.crop.circle.badge.questionmark") {
            ForEach(pending, id: \.0) { name, n in
                HStack {
                    Text(name).font(.system(size: 11))
                    Spacer()
                    Text("\(n)")
                        .font(.system(size: 11, weight: .bold, design: .monospaced))
                        .foregroundStyle(n > 0 ? Color.orange : .secondary)
                }
            }
            Text(app.t(
                "Quarantined proposals never act on their own — growth that "
                + "bypassed you would not be growth you can trust.",
                "隔離された提案は勝手には効きません。あなたを迂回した成長は、"
                + "信頼できる成長ではないからです。"))
                .font(.system(size: 10)).foregroundStyle(.tertiary)
                .padding(.top, 4)
        }
    }

    // MARK: - Plumbing

    private func card<Content: View>(title: String, icon: String,
                                     @ViewBuilder _ content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(title, systemImage: icon)
                .font(.system(size: 12, weight: .bold))
            content()
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.white.opacity(0.05))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    private func unavailable(_ why: String) -> some View {
        VStack(spacing: 8) {
            Image(systemName: "exclamationmark.triangle")
                .font(.system(size: 20)).foregroundStyle(.orange)
            Text(app.t("Growth data is unavailable — check Settings › MCP.",
                       "Growth データを取得できません。設定 › MCP を確認してください。"))
                .font(.system(size: 12))
            Text(why).font(.system(size: 10)).foregroundStyle(.secondary)
            Button(app.t("Retry", "再試行")) { Task { await load() } }
                .controlSize(.small)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(20)
    }

    private func shortValue(_ v: Any?) -> String {
        if let n = v as? Int { return "\(n)" }
        if let s = v as? String { return s }
        if let a = v as? [Any] { return "\(a.count) 件" }
        if let d = v as? [String: Any] { return "\(d.count) keys" }
        return v.map { "\($0)" } ?? "—"
    }

    private func parse(_ raw: String) -> [String: Any]? {
        guard let data = raw.data(using: .utf8) else { return nil }
        return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
    }

    private func load() async {
        loading = true
        defer { loading = false }
        let statsRaw = await MCPEngine.shared.callTool(
            serverName: "vera-memory", toolName: "failure_stats", arguments: [:])
        guard let stats = parse(statsRaw) else {
            loadError = String(statsRaw.prefix(160))
            return
        }
        loadError = nil
        let vh = stats["verdicts"] as? [String: Int] ?? [:]
        verdicts = vh.sorted { $0.value > $1.value }.map { ($0.key, $0.value) }
        buckets = stats["buckets"] as? [[String: Any]] ?? []

        let wakeRaw = await MCPEngine.shared.callTool(
            serverName: "vera-memory", toolName: "wake_summary", arguments: [:])
        wake = parse(wakeRaw) ?? [:]

        // Queue lengths, each from its list tool; a queue that fails to
        // answer shows as absent rather than as zero, because "empty" and
        // "unreachable" must not look alike.
        var q: [(String, Int)] = []
        for (label, tool, key) in [
            (app.t("AI facts", "AI 提案の事実"), "list_pending_ai_facts", "pending"),
            (app.t("Capacity limits", "容量上限の変更"), "list_pending_capacity_limits", "pending"),
            (app.t("Pack verdicts", "パック判定"), "list_pending_pack_verdicts", "pending"),
            (app.t("Domain modules", "ドメインモジュール"), "list_pending_domain_modules", "pending"),
            (app.t("Tool calls", "ツール実行"), "list_pending_tool_calls", "pending"),
        ] {
            let raw = await MCPEngine.shared.callTool(
                serverName: "vera-memory", toolName: tool, arguments: [:])
            if let obj = parse(raw) {
                if let arr = obj[key] as? [Any] { q.append((label, arr.count)) }
                else if let n = obj["count"] as? Int { q.append((label, n)) }
                else { q.append((label, (obj.values.first as? [Any])?.count ?? 0)) }
            }
        }
        pending = q
    }
}
