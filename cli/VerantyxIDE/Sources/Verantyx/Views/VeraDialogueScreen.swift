import SwiftUI

/// Asking Vera — a ledger of queries, not a thread of messages.
///
/// Six things make this different from a chat window, and each is a
/// property of the engine rather than a preference about layout.
///
/// **Two kinds of asking, and a chat window has only one.** `vera_ask`
/// answers from the store and does not read the conversation; the
/// conversation has its OWN memory — `add_conversation_turn` puts an
/// utterance into a space rather than a window, so it is retrieved by
/// relevance instead of recency and never falls out; overflow freezes a
/// layer and says FROZEN rather than dropping it silently. Asking the
/// store and asking the conversation are different questions with
/// different answers, so the composer names which one is being asked
/// instead of blurring them into a thread.
///
/// The earlier version of this file claimed every question was independent
/// and that a thread would draw a dependency that did not exist. That was
/// half wrong: the dependency exists, it simply lives behind its own door.
///
/// **A refusal is the answer.** `UNKNOWN_NO_EVIDENCE` is the most valuable
/// thing this engine does; rendering it beside a red warning triangle
/// would teach the reader that its best behaviour is a malfunction. Gaps
/// get their own ink and say what would close them.
///
/// **Origins are not folded away.** Every facet carries a witness, so the
/// sources sit next to the claim instead of behind a disclosure arrow.
///
/// **The layer is named.** Whether the organisation's own vocabulary
/// answered, or the shared map did, can matter more than the sentence —
/// and nothing on a normal chat screen would ever show it.
///
/// **Re-asking means something else here.** Regenerating an LLM reply asks
/// for a different answer. Re-running a Vera query asks whether the answer
/// is still the same one, so the button says 再実行 and the row records
/// how many times it held.
///
/// **No persona.** Nothing writes 「〜だと思います」. Vera holds no
/// opinions and the surface should not lend it any.
struct VeraDialogueScreen: View {
    @EnvironmentObject var app: AppState
    @ObservedObject private var route = VeraRouteState.shared
    @State private var entries: [Entry] = []
    @State private var draft: String = ""
    @State private var running = false
    @State private var source: Source = .store
    /// A = the whole query rides to later layers, B = only the previous
    /// answer (which can drift, and says UNKNOWN_DRIFT when it does),
    /// C = the intent head. Exposed because B's drift is a real behaviour
    /// a reader should be able to cause deliberately, not stumble into.
    @State private var carry: String = "A"

    enum Source: String, CaseIterable, Identifiable {
        case store = "店に訊く"
        case conversation = "会話に訊く"
        var id: String { rawValue }
    }

    struct Entry: Identifiable {
        let id = UUID()
        let n: Int
        let question: String
        var verdict: String
        var answer: String
        var origins: [String]
        var layer: String
        var door: String
        var runs: Int = 1
        var held: Bool = true          // every re-run agreed
        var refused: Bool { verdict.hasPrefix("UNKNOWN")
                            || verdict.hasPrefix("AMBIGUOUS") }
    }

    var body: some View {
        VStack(spacing: 0) {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 0) {
                        if entries.isEmpty { empty }
                        ForEach(entries) { e in
                            row(e)
                            Divider().opacity(0.18)
                        }
                        Color.clear.frame(height: 1).id("tail")
                    }
                    .padding(.vertical, 6)
                }
                .onChange(of: entries.count) { _, _ in
                    withAnimation { proxy.scrollTo("tail", anchor: .bottom) }
                }
            }
            Divider().opacity(0.35)
            composer
        }
    }

    private var empty: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("問いを入力してください。")
                .font(.system(size: 12)).foregroundStyle(.secondary)
            Text("答えられないときは、答えられないと型で返ります。"
                 + "同じ問いには同じ答えが返ります。")
                .font(.system(size: 10)).foregroundStyle(.tertiary)
        }
        .padding(.horizontal, 16).padding(.vertical, 14)
    }

    // MARK: - one entry

    @ViewBuilder
    private func row(_ e: Entry) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text("#\(e.n)")
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(.tertiary)
                Text(e.question)
                    .font(.system(size: 13, weight: .medium))
                    .textSelection(.enabled)
                Spacer()
                // Re-running asks whether the answer HELD, not for a
                // different one. That is only a meaningful button because
                // the engine is deterministic.
                Button {
                    rerun(e)
                } label: {
                    Label(e.runs > 1 ? "×\(e.runs)" : "再実行",
                          systemImage: "arrow.clockwise")
                        .font(.system(size: 10))
                }
                .buttonStyle(.plain)
                .foregroundStyle(e.held ? Color.secondary.opacity(0.6)
                                        : VeraInk.contested)
                .help(e.held ? "同じ答えが返るかを確かめる"
                             : "再実行で答えが変わりました — 記録されています")
            }

            HStack(spacing: 6) {
                Rectangle()
                    .fill(e.refused ? VeraInk.unsettled : VeraInk.verified)
                    .frame(width: 2, height: 11)
                Text(e.verdict)
                    .font(.system(size: 10, weight: .medium, design: .monospaced))
                    .foregroundStyle(.secondary)
                if !e.door.isEmpty {
                    Text(e.door)
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(.tertiary)
                }
                if !e.layer.isEmpty {
                    Text(e.layer)
                        .font(.system(size: 9))
                        .padding(.horizontal, 5).padding(.vertical, 1)
                        .background(.quaternary.opacity(0.5), in: Capsule())
                }
            }

            if !e.answer.isEmpty {
                Text(e.answer)
                    .font(.system(size: 13))
                    .textSelection(.enabled)
                    .fixedSize(horizontal: false, vertical: true)
            }

            if e.refused {
                Text("これは失敗ではありません。証拠が無いことを、型を付けて述べています。")
                    .font(.system(size: 10)).foregroundStyle(.secondary)
            }

            // Origins sit with the claim rather than behind a disclosure —
            // a source you have to open is a source most readers never see.
            if !e.origins.isEmpty {
                VStack(alignment: .leading, spacing: 2) {
                    ForEach(e.origins.prefix(6), id: \.self) { o in
                        HStack(spacing: 5) {
                            Image(systemName: "checkmark")
                                .font(.system(size: 8, weight: .semibold))
                                .foregroundStyle(VeraInk.verified)
                            Text(o)
                                .font(.system(size: 10, design: .monospaced))
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                        }
                    }
                    if e.origins.count > 6 {
                        Text("ほか \(e.origins.count - 6) 件")
                            .font(.system(size: 9)).foregroundStyle(.tertiary)
                    }
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 11)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: - composer

    private var composer: some View {
        HStack(spacing: 8) {
            Picker("", selection: $source) {
                ForEach(Source.allCases) { Text($0.rawValue).tag($0) }
            }
            .pickerStyle(.segmented)
            .frame(width: 190)
            if source == .conversation {
                Picker("", selection: $carry) {
                    Text("A 問い全体").tag("A")
                    Text("B 前の答え").tag("B")
                    Text("C 意図の頭").tag("C")
                }
                .frame(width: 120)
                .help("B は漂流しうる — その場合 UNKNOWN_DRIFT を返します")
            }
            TextField(source == .store ? "店に質問" : "これまでの会話に質問",
                      text: $draft)
                .textFieldStyle(.plain)
                .font(.system(size: 13))
                .onSubmit(ask)
            if running {
                ProgressView().controlSize(.small)
            } else {
                Button(action: ask) {
                    Image(systemName: "return").font(.system(size: 11))
                }
                .buttonStyle(.plain)
                .disabled(draft.trimmingCharacters(in: .whitespaces).isEmpty)
                .foregroundStyle(.secondary)
            }
        }
        .padding(.horizontal, 16).padding(.vertical, 11)
    }

    // MARK: - asking

    private func ask() {
        let q = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !q.isEmpty, !running else { return }
        draft = ""
        running = true
        let n = entries.count + 1
        Task {
            let e = await query(q, n: n)
            await MainActor.run { entries.append(e); running = false }
        }
    }

    private func rerun(_ e: Entry) {
        guard !running else { return }
        running = true
        Task {
            let fresh = await query(e.question, n: e.n)
            await MainActor.run {
                if let i = entries.firstIndex(where: { $0.id == e.id }) {
                    // A verdict that changed is kept visible rather than
                    // overwritten: determinism is a claim this surface
                    // makes, so its exceptions have to be reportable.
                    entries[i].held = entries[i].verdict == fresh.verdict
                    entries[i].runs += 1
                    entries[i].verdict = fresh.verdict
                    entries[i].answer = fresh.answer
                    entries[i].origins = fresh.origins
                    entries[i].layer = fresh.layer
                }
                running = false
            }
        }
    }

    private func query(_ q: String, n: Int) async -> Entry {
        let door = source == .store ? "vera_ask" : "recall_conversation"
        let args: [String: Any] = source == .store
            ? ["query": q]
            : ["query": q, "carry": carry]
        let obj = await VeraMemoryBridge.callDoor(door, args)
        guard let obj else {
            return Entry(n: n, question: q, verdict: "UNKNOWN_ENGINE_SILENT",
                         answer: "", origins: [], layer: "", door: door)
        }
        let e = Entry(
            n: n, question: q,
            verdict: (obj["verdict"] as? String) ?? "UNKNOWN",
            answer: (obj["answer"] as? String)
                ?? (obj["text"] as? String) ?? "",
            origins: (obj["origins"] as? [String])
                ?? (obj["witnesses"] as? [String]) ?? [],
            layer: source == .conversation
                ? "会話" + (carry == "A" ? "" : " carry:" + carry)
                : (app.veraDomain.isEmpty ? "共有" : app.veraDomain),
            door: door)

        // The turn goes into the conversation's space either way, so what
        // was asked here is consultable later. It is stored as an
        // utterance, never as a fact that votes.
        _ = await VeraMemoryBridge.callDoor(
            "add_conversation_turn", ["speaker": "user", "text": q])
        if !e.answer.isEmpty {
            _ = await VeraMemoryBridge.callDoor(
                "add_conversation_turn",
                ["speaker": "vera", "text": e.answer])
        }
        return e
    }
}
