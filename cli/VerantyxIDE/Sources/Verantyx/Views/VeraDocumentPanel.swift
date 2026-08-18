import SwiftUI
import UniformTypeIdentifiers

/// 投入 — a document becomes a vocabulary Vera can speak in.
///
/// This is the one thing the short-lived standalone Vera window had that
/// the mature screen did not: an entry for the document itself. Everything
/// else that window offered already lived here (the console answers, the
/// stereo cross draws the route, the operator console opens from the agent
/// screen, `<verantyx>…</verantyx>` injects text mid-conversation), so the
/// window was two surfaces for one product — and two surfaces drift.
///
/// ## What registering does, and what it deliberately does not
///
/// It writes `fillers__<name>` and `patterns__<name>`: the words this
/// document uses and the case patterns its verbs were observed in. It
/// never touches `frames`. **Grammar stays shared, vocabulary is layered**
/// — measured, grammar transfers across domains (0.735–0.857 dominant-case
/// agreement against a 0.28 shuffled control) and vocabulary does not.
///
/// A registered domain casts no vote. It gives the composer words to build
/// a sentence from; the verdict still comes from the federation.
///
/// The gate is the engine's, not this screen's: fewer than five verbs or
/// five slots and `vera_domain` refuses, because a handful of sentences
/// makes a vocabulary that is mostly one document's accidents.
struct VeraDocumentPanel: View {
    @EnvironmentObject var app: AppState
    @State private var name = ""
    @State private var text = ""
    @State private var picked: URL?
    @State private var result = ""
    @State private var working = false
    @State private var compareTopic = ""
    @State private var shelf: [(source: String, sections: Int, labels: Int, lines: Int)] = []

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("入れ方は二つ。**語彙**はこの文書の言葉で話せるようになるもの"
                 + "(文法は共有のまま・票は持たない)。**文書**は原文をそのまま"
                 + "引用して答えられるようになるもの — 規程や仕様の窓口はこちら。")
                .font(.system(size: 11))
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            TextField("分野名（英数字と _ のみ）", text: $name)
                .textFieldStyle(.roundedBorder)

            // A document is OFFERED, never swallowed. The file is chosen
            // here and registered on an explicit press — the same rule the
            // ingest path has everywhere else, because an invisible ingest
            // is the one thing a store like this cannot come back from.
            HStack(spacing: 8) {
                Button("ファイルを選ぶ…") { choose() }
                if let p = picked {
                    Text(p.lastPathComponent)
                        .font(.system(size: 10, design: .monospaced))
                        .lineLimit(1).truncationMode(.middle)
                        .foregroundStyle(.secondary)
                }
            }

            Text("または本文を直接")
                .font(.system(size: 10)).foregroundStyle(.tertiary)
            TextEditor(text: $text)
                .font(.system(size: 11, design: .monospaced))
                .frame(minHeight: 110)
                .overlay(RoundedRectangle(cornerRadius: 4)
                    .strokeBorder(Color.primary.opacity(0.12)))

            HStack(spacing: 8) {
                Button(working ? "登録中…" : "語彙として登録") { register() }
                    .disabled(working || name.isEmpty
                              || (picked == nil && text.count < 40))
                // 逐語引用の経路。語彙登録とは別の扉で、こちらが「宿泊費の
                // 上限は」に原文の行を返す側。ファイルが要る — 構造索引は
                // 見出しと行を読むので、貼り付け本文には出典が無い。
                Button(working ? "取り込み中…" : "文書として取り込む") { ingest() }
                    .disabled(working || picked == nil)
                Spacer()
                if !app.veraDomain.isEmpty {
                    Toggle("この分野だけで答える", isOn: $app.veraDomainOnly)
                        .toggleStyle(.checkbox)
                        .font(.system(size: 10))
                }
            }

            // 分野の棚に文書は現れない。二つは別の店で、合体させないと
            // 決めてある — だが見えないのは別物であることの帰結ではなく、
            // 棚を出していないだけだった。これがその棚。
            Divider()
            HStack(spacing: 6) {
                Text("取り込み済みの文書")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(.secondary)
                Spacer()
                Button("更新") { Task { shelf = await VeraMemoryBridge.documentShelf() } }
                    .font(.system(size: 10))
            }
            if shelf.isEmpty {
                Text("まだありません。上の「文書として取り込む」で入れたものがここに残ります。")
                    .font(.system(size: 10)).foregroundStyle(.tertiary)
            } else {
                ForEach(shelf, id: \.source) { d in
                    HStack(spacing: 8) {
                        Text(d.source)
                            .font(.system(size: 11, design: .monospaced))
                            .lineLimit(1).truncationMode(.middle)
                        Text("節\(d.sections)・項目\(d.labels)・行\(d.lines)")
                            .font(.system(size: 9)).foregroundStyle(.tertiary)
                        Spacer()
                        Button("外す") {
                            Task {
                                result = await VeraMemoryBridge.forgetDocument(d.source)
                                shelf = await VeraMemoryBridge.documentShelf()
                            }
                        }
                        .font(.system(size: 10))
                    }
                }
            }

            Divider()
            HStack(spacing: 8) {
                TextField("主題（社内文書と一般知識を比べる）", text: $compareTopic)
                    .textFieldStyle(.roundedBorder)
                Button("比較") { compare() }
                    .disabled(working || compareTopic.isEmpty)
            }

            if !result.isEmpty {
                Text(result)
                    .font(.system(size: 11))
                    .textSelection(.enabled)
                    .padding(9)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(.quaternary.opacity(0.25),
                                in: RoundedRectangle(cornerRadius: 5))
            }
        }
        .padding(14)
        .task { shelf = await VeraMemoryBridge.documentShelf() }
    }

    private func choose() {
        let p = NSOpenPanel()
        p.allowsMultipleSelection = false
        p.canChooseDirectories = false
        p.allowedContentTypes = [.pdf, .plainText, .xml, .html]
        if p.runModal() == .OK, let url = p.url {
            picked = url
            if name.isEmpty {
                // A suggestion, not a decision: the engine's name rule is
                // ASCII and the person may want something else entirely.
                name = url.deletingPathExtension().lastPathComponent
                    .lowercased()
                    .replacingOccurrences(of: "[^a-z0-9_]",
                                          with: "_", options: .regularExpression)
            }
        }
    }

    private func ingest() {
        guard let url = picked else { return }
        working = true
        Task {
            let r = await VeraMemoryBridge.loadDocuments(paths: [url.path])
            await MainActor.run { result = r; working = false }
        }
    }

    private func compare() {
        working = true
        let t = compareTopic
        Task {
            let r = await VeraMemoryBridge.compareSpaces(topic: t)
            await MainActor.run { result = r; working = false }
        }
    }

    private func register() {
        working = true
        let n = name, t = text, url = picked
        Task {
            let r: String
            if let url {
                r = await VeraMemoryBridge.registerDomain(n, path: url.path)
            } else {
                r = await VeraMemoryBridge.registerDomainText(n, text: t)
            }
            await MainActor.run {
                result = r
                if r.hasPrefix("🗂") { app.veraDomain = n }
                working = false
            }
        }
    }
}
