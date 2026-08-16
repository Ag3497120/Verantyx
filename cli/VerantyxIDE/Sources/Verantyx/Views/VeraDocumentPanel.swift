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

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("語彙として入れると、この文書の言葉でVeraが話せるようになります。"
                 + "文法は共有のまま、票は持ちません。")
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
                Spacer()
                if !app.veraDomain.isEmpty {
                    Toggle("この分野だけで答える", isOn: $app.veraDomainOnly)
                        .toggleStyle(.checkbox)
                        .font(.system(size: 10))
                }
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
