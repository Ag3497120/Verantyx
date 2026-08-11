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

    private enum Tab { case gaps, edit }

    var body: some View {
        HStack(spacing: 0) {
            // Run side — the published page, live.
            VStack(spacing: 0) {
                HStack(spacing: 8) {
                    Text(app.t("Live: verantyx.ai/vera3d",
                               "本番: verantyx.ai/vera3d"))
                        .font(.system(size: 11, weight: .semibold))
                    Spacer()
                    Button(app.t("Reload live", "本番を再読込")) {
                        web = AuditWebRequest(
                            url: URL(string: "https://verantyx.ai/vera3d/")!,
                            stamp: web.stamp + 1)
                    }
                    .font(.system(size: 10))
                    Button(app.t("Exit Vera-a", "Vera-a を終了")) {
                        app.isVeraAMode = false
                    }
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
                }
                .pickerStyle(.segmented)
                .padding(8)

                switch tab {
                case .gaps: gapsPanel
                case .edit: editPanel
                }
            }
            .frame(width: 380)
            .background(Color(red: 0.11, green: 0.11, blue: 0.14))
        }
        .task { await refreshDemand() }
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
                    }
                    .font(.system(size: 10))
                }
            }
            .listStyle(.plain)

            if !demandNote.isEmpty {
                Text(demandNote).font(.system(size: 10))
                    .foregroundStyle(.secondary).padding(.horizontal, 10)
            }
            HStack {
                Button(app.t("Refresh", "更新")) {
                    Task { await refreshDemand() }
                }
                .font(.system(size: 10.5))
                Spacer()
            }
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
            DispatchQueue.main.async { busy = false }
        }
    }

    private func appendLog(_ line: String) {
        DispatchQueue.main.async { gitLog = line + "\n" + gitLog }
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
