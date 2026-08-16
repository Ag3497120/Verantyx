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
        /// The tokens the verdict stood on. `vera_ask` has no `origins`
        /// field — measured against the live engine, it returns `tokens`
        /// plus two readings, and calling those "sources" would dress a
        /// quorum up as a citation.
        var tokens: [String]
        var agree: Double?
        var eMin: Int?
        var layer: String
        var door: String
        var runs: Int = 1
        var held: Bool = true          // every re-run agreed
        var core: String = ""
        /// What would close the gap. The engine returns it and the earlier
        /// draft of this screen threw it away, which left a refusal with
        /// nothing to do about it.
        var remedy: String = ""
        /// `vera_explain` keeps its provenance per unit, not in
        /// `facet_origin`.
        var origins: [String] = []
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
                // The two readings the engine actually returns. `agree` is
                // how much of the federation agreed; `e_min` is the
                // thinnest evidence any of them stood on. Both are shown
                // because a high agreement over thin evidence is a
                // different thing from the same number over thick.
                if let a = e.agree {
                    Text("一致 " + String(format: "%.0f%%", a * 100))
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(.tertiary)
                }
                if let m = e.eMin {
                    Text("証拠 \(m)")
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(.tertiary)
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
                if !e.remedy.isEmpty {
                    Text("閉じるには: \(e.remedy)")
                        .font(.system(size: 10)).foregroundStyle(.secondary)
                }
            }
            if !e.origins.isEmpty {
                ForEach(e.origins.prefix(4), id: \.self) { o in
                    HStack(spacing: 5) {
                        Image(systemName: "checkmark")
                            .font(.system(size: 8, weight: .semibold))
                            .foregroundStyle(VeraInk.verified)
                        Text(o).font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(.secondary).lineLimit(1)
                    }
                }
            }

            // The tokens the answer was built from, beside the answer
            // rather than behind a disclosure — evidence you have to open
            // is evidence most readers never see.
            if !e.tokens.isEmpty {
                HStack(spacing: 5) {
                    ForEach(e.tokens.prefix(8), id: \.self) { t in
                        Text(t)
                            .font(.system(size: 10, design: .monospaced))
                            .padding(.horizontal, 5).padding(.vertical, 1)
                            .background(.quaternary.opacity(0.4),
                                        in: RoundedRectangle(cornerRadius: 3))
                    }
                    if e.tokens.count > 8 {
                        Text("+\(e.tokens.count - 8)")
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

    private func plain(_ door: String, _ args: [String: Any],
                       _ q: String, _ n: Int) async -> Entry {
        guard let obj = await VeraMemoryBridge.callDoor(door, args) else {
            return Entry(n: n, question: q, verdict: "UNKNOWN_ENGINE_SILENT",
                         answer: "", tokens: [], agree: nil, eMin: nil,
                         layer: "", door: door)
        }
        return Entry(n: n, question: q,
                     verdict: (obj["verdict"] as? String) ?? "UNKNOWN",
                     answer: (obj["text"] as? String) ?? "",
                     tokens: (obj["tokens"] as? [String]) ?? [],
                     agree: obj["agree_frac"] as? Double,
                     eMin: obj["e_min"] as? Int,
                     layer: "会話" + (carry == "A" ? "" : " carry:" + carry),
                     door: door)
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
                    entries[i].tokens = fresh.tokens
                    entries[i].agree = fresh.agree
                    entries[i].eMin = fresh.eMin
                    entries[i].layer = fresh.layer
                }
                running = false
            }
        }
    }

    /// One door. The ordering lives in the engine, not here.
    ///
    /// This function used to BE the composition: it called `vera_ask`,
    /// decided in Swift when a follow-up needed the last core, and fell
    /// through to `vera_explain` when the census had nothing. That worked,
    /// and it was still wrong — every other client had to re-derive the
    /// same four steps, and each one that derived fewer made the same
    /// engine look like a smaller product. Measured: the answering path
    /// used three of a hundred doors, leaving seventeen organs outside
    /// every question anyone asked here.
    ///
    /// `vera_engine` now carries that order, plus the organs Swift never
    /// called — typo repair, arithmetic, the mathlib witness, the
    /// difference short-circuit, the gap ledger, frame composition. What
    /// stays on this side is presentation: which stages to show a reader,
    /// and how.
    private func query(_ q: String, n: Int) async -> Entry {
        if source == .conversation {
            return await plain("recall_conversation",
                               ["query": q, "carry": carry], q, n)
        }
        let lastCore = entries.last(where: { !$0.refused })?.core ?? ""
        let obj = await VeraMemoryBridge.callDoor(
            "vera_engine",
            ["query": q, "last_core": lastCore, "domain": app.veraDomain])

        guard let obj else {
            return Entry(n: n, question: q, verdict: "UNKNOWN_ENGINE_SILENT",
                         answer: "", tokens: [], agree: nil, eMin: nil,
                         layer: "", door: "vera_engine")
        }

        // The stages that CHANGED the question are printed. An invisible
        // context resolution is the same shape of lie as an invisible
        // ingest, and the engine now reports typo repair and staging in
        // the same place — so all of them become visible at once instead
        // of only the one this screen happened to implement.
        let stages = (obj["stages"] as? [[String: Any]]) ?? []
        let acted = stages.filter { ($0["changed"] as? Bool) == true }
            .compactMap { st -> String? in
                guard let name = st["stage"] as? String,
                      let note = st["note"] as? String, !note.isEmpty
                else { return nil }
                return "\(name): \(note)"
            }

        var body = (obj["text"] as? String) ?? ""
        if !acted.isEmpty {
            body = "🧭 " + acted.joined(separator: " / ") + "\n" + body
        }

        var e = Entry(
            n: n, question: q,
            verdict: (obj["verdict"] as? String) ?? "UNKNOWN",
            answer: body,
            tokens: (obj["tokens"] as? [String]) ?? [],
            agree: obj["agree_frac"] as? Double,
            eMin: obj["e_min"] as? Int,
            layer: app.veraDomain.isEmpty ? "共有" : app.veraDomain,
            door: (obj["door"] as? String) ?? "vera_engine")
        e.core = (obj["core"] as? String) ?? ""
        e.remedy = (obj["remedy"] as? String) ?? ""
        // The engine gathers provenance from every door's own convention
        // (`facet_origin` for the census, per-unit `source` for a
        // descent). Reading only one of them is why a console once showed
        // 「出典の記録なし」 over an answer that named its source.
        e.origins = (obj["origins"] as? [String]) ?? []

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
