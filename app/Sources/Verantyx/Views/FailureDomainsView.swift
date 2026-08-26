import SwiftUI

/// The research-platform surface: what Vera knows about failure, where each
/// piece of that knowledge came from, and how to correct it.
///
/// The screen is built around one uncomfortable fact and refuses to hide it.
/// Most of this taxonomy is seeded — written by a model, not confirmed
/// against incidents in any of these fields — and a UI that displays a
/// seeded verdict the same way it displays one anchored to a real, diagnosed
/// failure would be lying by layout. So maturity and provenance are not
/// buried in a detail pane; they are on every row, and the "seeded" state
/// reads as an invitation to correct rather than as a defect.
///
/// The correction path is the reason the screen exists. A domain expert does
/// not write regular expressions here — three patterns in this registry were
/// wrong for exactly that reason, each written by someone who knew the
/// domain fact and mis-typed the syntax. They paste real failure lines,
/// choose a verdict, and a pattern is proposed and checked against their own
/// counter-examples and every existing fixture before it can be queued.
struct FailureDomainsView: View {
    @EnvironmentObject var app: AppState

    @State private var packs: [Pack] = []
    @State private var loadErrors: [String] = []
    @State private var selected: String?
    @State private var loading = false

    // Coverage probe: paste real logs, see what the pack actually types.
    @State private var probeLogs = ""
    @State private var probeResult: Probe?

    // Authoring: examples in, proposal out.
    @State private var newVerdict = ""
    @State private var newNote = ""
    @State private var positives = ""
    @State private var negatives = ""
    @State private var remedyKind = "fix_content"
    @State private var remedyOwner = ""
    @State private var verifyMethod = "rerun"
    @State private var author = ""
    @State private var proposalReport: String?
    @State private var proposalOK: Bool?

    @State private var pendingVerdicts: [PendingVerdict] = []

    struct Pack: Identifiable {
        let id: String
        let maturity: String
        let description: String
        let editable: Bool
        let verdicts: [Verdict]
    }
    struct Verdict: Identifiable {
        var id: String { verdict }
        let verdict: String
        let note: String
        let provenance: String
        let remedyKind: String
        let remedyOwner: String
        let verify: String
        let autoCalibratable: Bool
    }
    struct Probe {
        let total: Int
        let coverage: Double
        let unclassified: Int
        let counts: [(String, Int)]
    }
    struct PendingVerdict: Identifiable {
        let id: Int
        let pack: String
        let verdict: String
        let author: String
        let positives: [String]
        let pattern: String
        let shadowed: [String]
    }

    private static let remedyKinds = [
        "add_facts", "add_rule_or_module", "raise_limit", "add_data_source",
        "fix_content", "fix_upstream", "request_input", "human_judgment", "fix_code",
    ]
    private static let verifyMethods = ["rerun", "rerun_larger_limit", "replay", "manual"]

    var body: some View {
        HSplitView {
            packList.frame(minWidth: 210, idealWidth: 240, maxWidth: 320)
            detail.frame(minWidth: 320)
        }
        .background(Theme.panel2)
        .task { await refresh() }
    }

    // MARK: - Left: the registry

    private var packList: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text(app.t("Failure domains", "失敗の分野"))
                    .font(.system(size: 12, weight: .semibold))
                Spacer()
                Button { Task { await refresh() } } label: { Image(systemName: "arrow.clockwise") }
                    .buttonStyle(.plain).disabled(loading)
            }
            .padding(.horizontal, 10).padding(.vertical, 8)

            // A pack the loader rejected must be visible. Absent and broken
            // look identical otherwise, and the expert who broke it is the
            // one person who can fix it.
            if !loadErrors.isEmpty {
                VStack(alignment: .leading, spacing: 3) {
                    Label(app.t("Packs rejected at load", "読み込み時に拒否されたパック"),
                          systemImage: "exclamationmark.triangle.fill")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(.orange)
                    ForEach(loadErrors, id: \.self) { e in
                        Text(e).font(.system(size: 9, design: .monospaced))
                            .foregroundStyle(.secondary)
                    }
                }
                .padding(8)
                .background(Color.orange.opacity(0.10), in: RoundedRectangle(cornerRadius: 6))
                .padding(.horizontal, 8).padding(.bottom, 6)
            }

            ScrollView {
                VStack(alignment: .leading, spacing: 2) {
                    ForEach(packs) { p in
                        Button { selected = p.id; probeResult = nil; proposalReport = nil } label: {
                            HStack(spacing: 6) {
                                maturityDot(p.maturity)
                                VStack(alignment: .leading, spacing: 1) {
                                    Text(p.id).font(.system(size: 11, weight: .medium))
                                    Text("\(p.verdicts.count) " + app.t("verdicts", "型"))
                                        .font(.system(size: 9)).foregroundStyle(.secondary)
                                }
                                Spacer()
                                if !p.editable {
                                    Image(systemName: "lock.fill")
                                        .font(.system(size: 8)).foregroundStyle(.secondary)
                                        .help(app.t("Defined in code, not editable here",
                                                    "コード定義のため、ここでは編集できません"))
                                }
                            }
                            .padding(.horizontal, 8).padding(.vertical, 5)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(RoundedRectangle(cornerRadius: 5)
                                .fill(selected == p.id ? Color.white.opacity(0.08) : .clear))
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.horizontal, 6)
            }

            if !pendingVerdicts.isEmpty {
                Divider().opacity(0.2)
                Text("\(pendingVerdicts.count) " + app.t("awaiting review", "件が査読待ち"))
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(Color(red: 0.55, green: 0.8, blue: 1.0))
                    .padding(8)
            }
        }
    }

    private func maturityDot(_ maturity: String) -> some View {
        Circle()
            .fill(maturity == "verified" ? Color.green : Color.orange)
            .frame(width: 6, height: 6)
            .help(maturity == "verified"
                  ? app.t("Validated against confirmed incidents",
                          "確定した実事件で検証済み")
                  : app.t("Seeded taxonomy — no confirmed incident yet; classifies and counts, may not calibrate",
                          "種の分類 — 確定事件はまだ無い。分類と集計はするが、較正はしない"))
    }

    // MARK: - Right

    private var detail: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if let p = packs.first(where: { $0.id == selected }) {
                    packHeader(p)
                    verdictTable(p)
                    Divider().opacity(0.2)
                    coverageProbe(p)
                    if p.editable {
                        Divider().opacity(0.2)
                        authoring(p)
                    }
                } else {
                    Text(app.t("Select a domain.", "分野を選んでください。"))
                        .font(.system(size: 11)).foregroundStyle(.secondary)
                }
                if !pendingVerdicts.isEmpty {
                    Divider().opacity(0.2)
                    reviewQueue
                }
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func packHeader(_ p: Pack) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack(spacing: 6) {
                Text(p.id).font(.system(size: 14, weight: .semibold))
                maturityDot(p.maturity)
                Text(p.maturity).font(.system(size: 10)).foregroundStyle(.secondary)
            }
            Text(p.description).font(.system(size: 11)).foregroundStyle(.secondary)
            if p.maturity == "seeded" {
                Text(app.t("This taxonomy has not been confirmed against real incidents in this field. It classifies and counts; it is not allowed to propose limit changes. Correcting it below is the intended use.",
                           "この分類は、この分野の実事件で確認されていません。分類と集計は行いますが、限界値の変更は提案できません。下で修正することが想定された使い方です。"))
                    .font(.system(size: 10))
                    .foregroundStyle(.orange)
                    .padding(7)
                    .background(Color.orange.opacity(0.08), in: RoundedRectangle(cornerRadius: 5))
            }
        }
    }

    private func verdictTable(_ p: Pack) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            ForEach(p.verdicts) { v in
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Text(v.verdict).font(.system(size: 11, weight: .semibold, design: .monospaced))
                        if v.autoCalibratable {
                            Text(app.t("calibratable", "較正可"))
                                .font(.system(size: 8))
                                .padding(.horizontal, 4).padding(.vertical, 1)
                                .background(Color.green.opacity(0.18), in: Capsule())
                        }
                        Spacer()
                        // Provenance on the row, not in a detail pane: who to
                        // ask, and whether an expert has looked at it yet.
                        Text(v.provenance)
                            .font(.system(size: 9, design: .monospaced))
                            .foregroundStyle(v.provenance.hasPrefix("human:")
                                             ? Color.green : Color.secondary)
                    }
                    Text(v.note).font(.system(size: 10)).foregroundStyle(.secondary)
                    Text("→ \(v.remedyKind) · \(v.remedyOwner) · \(app.t("verify", "検証")): \(v.verify)")
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(Color(red: 0.55, green: 0.8, blue: 1.0).opacity(0.8))
                }
                .padding(7)
                .background(Color.white.opacity(0.04), in: RoundedRectangle(cornerRadius: 5))
            }
        }
    }

    // MARK: - Coverage probe

    private func coverageProbe(_ p: Pack) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(app.t("Test against real logs", "実ログで試す"))
                .font(.system(size: 12, weight: .semibold))
            Text(app.t("Paste real failure lines, one per line. The number that matters is coverage: a taxonomy that types 3 of 200 real failures is not yet a taxonomy of this field, however tidy it reads.",
                       "実際の失敗行を1行ずつ貼ってください。重要なのは被覆率です — 実failure 200件のうち3件しか型付けできない分類は、どれだけ整って見えてもまだこの分野の分類ではありません。"))
                .font(.system(size: 10)).foregroundStyle(.secondary)
            TextEditor(text: $probeLogs)
                .font(.system(size: 10, design: .monospaced))
                .frame(height: 70)
                .background(Color.black.opacity(0.25), in: RoundedRectangle(cornerRadius: 5))
            Button(app.t("Run", "実行")) { Task { await runProbe(p.id) } }
                .disabled(probeLogs.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            if let r = probeResult {
                HStack(spacing: 10) {
                    Text(String(format: app.t("coverage %.0f%%", "被覆率 %.0f%%"), r.coverage * 100))
                        .font(.system(size: 12, weight: .semibold, design: .monospaced))
                        .foregroundStyle(r.coverage >= 0.8 ? Color.green
                                         : r.coverage >= 0.5 ? Color.orange : Color.red)
                    Text("\(r.unclassified)/\(r.total) " + app.t("unclassified", "未分類"))
                        .font(.system(size: 10)).foregroundStyle(.secondary)
                }
                ForEach(r.counts, id: \.0) { verdict, n in
                    HStack {
                        Text(verdict).font(.system(size: 10, design: .monospaced))
                        Spacer()
                        Text("\(n)").font(.system(size: 10, design: .monospaced))
                    }
                }
            }
        }
    }

    // MARK: - Authoring from examples

    private func authoring(_ p: Pack) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(app.t("Add a verdict from examples", "例から型を追加する"))
                .font(.system(size: 12, weight: .semibold))
            Text(app.t("You do not write a regular expression. Paste real lines that should get this verdict, and counter-examples that should not. The pattern is proposed from what they share and refused — with the counter-example — if it would also claim something else.",
                       "正規表現は書きません。この型になるべき実際の行と、なってはいけない反例を貼ってください。共通部分からパターンを提案し、他のものまで拾ってしまう場合は反例つきで拒否します。"))
                .font(.system(size: 10)).foregroundStyle(.secondary)

            labelled(app.t("Verdict name", "型の名前")) {
                TextField("UNKNOWN_...", text: $newVerdict).font(.system(size: 11, design: .monospaced))
            }
            labelled(app.t("What it means", "意味")) {
                TextField("", text: $newNote).font(.system(size: 11))
            }
            Text(app.t("Positive examples (one per line)", "肯定例(1行ずつ)"))
                .font(.system(size: 10, weight: .semibold))
            TextEditor(text: $positives)
                .font(.system(size: 10, design: .monospaced)).frame(height: 55)
                .background(Color.black.opacity(0.25), in: RoundedRectangle(cornerRadius: 5))
            Text(app.t("Counter-examples (one per line)", "反例(1行ずつ)"))
                .font(.system(size: 10, weight: .semibold))
            TextEditor(text: $negatives)
                .font(.system(size: 10, design: .monospaced)).frame(height: 40)
                .background(Color.black.opacity(0.25), in: RoundedRectangle(cornerRadius: 5))

            HStack(spacing: 8) {
                Picker(app.t("Fix kind", "処方"), selection: $remedyKind) {
                    ForEach(Self.remedyKinds, id: \.self) { Text($0).tag($0) }
                }.frame(width: 190)
                Picker(app.t("Verify", "検証"), selection: $verifyMethod) {
                    ForEach(Self.verifyMethods, id: \.self) { Text($0).tag($0) }
                }.frame(width: 175)
            }
            .font(.system(size: 10))
            labelled(app.t("Owned by", "担当")) {
                TextField(app.t("which team or subsystem acts on it", "誰が直すか"), text: $remedyOwner)
                    .font(.system(size: 11))
            }
            labelled(app.t("Your name", "あなたの名前")) {
                TextField(app.t("stamped into provenance", "出所として記録されます"), text: $author)
                    .font(.system(size: 11))
            }

            Button(app.t("Propose", "提案する")) { Task { await propose(p.id) } }
                .disabled(newVerdict.isEmpty || positives.isEmpty || author.isEmpty)

            if let report = proposalReport {
                Text(report)
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(proposalOK == true ? Color.green : Color.orange)
                    .padding(7)
                    .background((proposalOK == true ? Color.green : Color.orange).opacity(0.08),
                                in: RoundedRectangle(cornerRadius: 5))
            }
        }
    }

    // MARK: - Review queue

    private var reviewQueue: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(app.t("Awaiting review", "査読待ち"))
                .font(.system(size: 12, weight: .semibold))
            ForEach(pendingVerdicts) { pv in
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text("\(pv.pack).\(pv.verdict)")
                            .font(.system(size: 11, weight: .semibold, design: .monospaced))
                        Spacer()
                        Text("human:\(pv.author)").font(.system(size: 9, design: .monospaced))
                            .foregroundStyle(.secondary)
                    }
                    Text(app.t("pattern", "パターン") + ": \(pv.pattern)")
                        .font(.system(size: 10, design: .monospaced))
                    // The examples are the evidence. A reviewer shown only a
                    // regex is not reviewing anything.
                    ForEach(pv.positives.prefix(3), id: \.self) { ex in
                        Text("· \(ex)").font(.system(size: 9, design: .monospaced))
                            .foregroundStyle(.secondary).lineLimit(1)
                    }
                    if !pv.shadowed.isEmpty {
                        Text(app.t("also claims: ", "他にも拾う: ") + pv.shadowed.joined(separator: ", "))
                            .font(.system(size: 9)).foregroundStyle(.orange)
                    }
                    HStack {
                        Button(app.t("Accept", "承認")) { Task { await act(pv.id, accept: true) } }
                        Button(app.t("Reject", "却下")) { Task { await act(pv.id, accept: false) } }
                    }.font(.system(size: 10))
                }
                .padding(8)
                .background(Color.white.opacity(0.05), in: RoundedRectangle(cornerRadius: 6))
            }
        }
    }

    private func labelled<C: View>(_ label: String, @ViewBuilder _ content: () -> C) -> some View {
        HStack(spacing: 6) {
            Text(label).font(.system(size: 10)).foregroundStyle(.secondary).frame(width: 110, alignment: .leading)
            content()
        }
    }

    // MARK: - Data

    private func refresh() async {
        loading = true
        defer { loading = false }
        let raw = await VeraMemoryBridge.listFailureDomains()
        if let data = raw.data(using: .utf8),
           let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            loadErrors = (obj["load_errors"] as? [String]) ?? []
            packs = ((obj["packs"] as? [[String: Any]]) ?? []).compactMap { p in
                guard let name = p["name"] as? String else { return nil }
                let vs = ((p["verdicts"] as? [[String: Any]]) ?? []).compactMap { v -> Verdict? in
                    guard let verdict = v["verdict"] as? String else { return nil }
                    return Verdict(
                        verdict: verdict, note: (v["note"] as? String) ?? "",
                        provenance: (v["provenance"] as? String) ?? "?",
                        remedyKind: (v["remedy_kind"] as? String) ?? "",
                        remedyOwner: (v["remedy_owner"] as? String) ?? "",
                        verify: (v["verify"] as? String) ?? "",
                        autoCalibratable: (v["auto_calibratable"] as? Bool) ?? false)
                }
                return Pack(id: name, maturity: (p["maturity"] as? String) ?? "seeded",
                            description: (p["description"] as? String) ?? "",
                            editable: (p["editable"] as? Bool) ?? false, verdicts: vs)
            }
            if selected == nil { selected = packs.first?.id }
        }
        await refreshPending()
    }

    private func refreshPending() async {
        let raw = await VeraMemoryBridge.listPendingPackVerdicts()
        guard let data = raw.data(using: .utf8),
              let arr = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]]
        else { pendingVerdicts = []; return }
        pendingVerdicts = arr.compactMap { e in
            guard let i = e["index"] as? Int, let pack = e["pack_name"] as? String,
                  let v = e["verdict"] as? String else { return nil }
            let report = (e["report"] as? [String: Any]) ?? [:]
            return PendingVerdict(
                id: i, pack: pack, verdict: v,
                author: (e["author"] as? String) ?? "?",
                positives: (e["positives"] as? [String]) ?? [],
                pattern: (report["pattern"] as? String) ?? "",
                shadowed: (report["shadowed_fixtures"] as? [String]) ?? [])
        }
    }

    private func runProbe(_ pack: String) async {
        let raw = await VeraMemoryBridge.testFailurePack(pack: pack, logSamples: probeLogs)
        guard let data = raw.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return }
        let counts = (obj["counts"] as? [String: Int]) ?? [:]
        probeResult = Probe(
            total: (obj["total"] as? Int) ?? 0,
            coverage: (obj["coverage"] as? Double) ?? 0,
            unclassified: (obj["unclassified"] as? Int) ?? 0,
            counts: counts.sorted { $0.value > $1.value }.map { ($0.key, $0.value) })
    }

    private func propose(_ pack: String) async {
        let raw = await VeraMemoryBridge.proposeFailureVerdict(
            pack: pack, verdict: newVerdict, note: newNote,
            positives: positives, negatives: negatives,
            remedyKind: remedyKind, remedyOwner: remedyOwner,
            verify: verifyMethod, author: author)
        guard let data = raw.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { proposalReport = raw; proposalOK = false; return }
        let ok = (obj["ok"] as? Bool) ?? false
        proposalOK = ok
        if ok {
            let queued = (obj["queued"] as? Bool) ?? false
            proposalReport = app.t("Proposed pattern: ", "提案パターン: ")
                + ((obj["pattern"] as? String) ?? "")
                + (queued ? "\n" + app.t("Queued for review.", "査読待ちに入りました。")
                          : "\n" + ((obj["queued_note"] as? String) ?? ""))
            newVerdict = ""; newNote = ""; positives = ""; negatives = ""
            await refreshPending()
        } else {
            // The refusal carries the counter-example. That is the whole
            // point: "invalid" is not actionable, "it also matches this
            // other line" is.
            var lines: [String] = []
            if let e = obj["error"] as? String { lines.append(e) }
            for p in (obj["problems"] as? [String]) ?? [] { lines.append(p) }
            for c in (obj["contract_errors"] as? [String]) ?? [] { lines.append(c) }
            proposalReport = lines.joined(separator: "\n")
        }
    }

    private func act(_ index: Int, accept: Bool) async {
        _ = accept ? await VeraMemoryBridge.acceptPackVerdict(index: index)
                   : await VeraMemoryBridge.rejectPackVerdict(index: index)
        await refresh()
    }
}
