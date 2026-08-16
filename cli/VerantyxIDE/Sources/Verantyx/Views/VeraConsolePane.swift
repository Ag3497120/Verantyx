import SwiftUI

/// The right pane as a console, not a chat.
///
/// A transcript of bubbles makes every answer look like the same kind of
/// thing. Vera's answers are not: one carries evidence with named
/// sources, one is a typed refusal that says which evidence is missing,
/// one is a dispute with both sides held. The console gives each of
/// those its own section, so the shape of the reply is visible before a
/// word of it is read.
///
/// A refusal is a GAP, never an error. The engine did not fail when it
/// declined to answer — declining IS the answer, and the console shows
/// what would close it. Rendering that in red next to a warning triangle
/// would teach the reader that Vera's most valuable behaviour is a
/// malfunction.
struct VeraConsolePane: View {
    @EnvironmentObject var app: AppState
    @ObservedObject private var route = VeraRouteState.shared
    @State private var draft: String = ""
    @State private var history: [Entry] = []

    /// One settled turn. Deliberately small: the console re-reads the live
    /// detail from `VeraRouteState`, and keeping a full copy of every
    /// payload would make the pane a second store.
    struct Entry: Identifiable {
        let id = UUID()
        let subject: String
        let verdict: String
        let text: String
        let refused: Bool
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Divider().opacity(0.35)

            ScrollViewReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    if history.isEmpty && route.verdict.isEmpty {
                        Text("問いを入力してください。")
                            .font(.system(size: 12))
                            .foregroundStyle(.tertiary)
                            .padding(.top, 6)
                    }
                    // Answers accumulate. The console used to render one
                    // verdict and replace it, so a second question erased
                    // the first — and a refusal that names what is missing
                    // is exactly the thing a person wants to keep beside
                    // the answer that followed it.
                    ForEach(history) { past in
                        pastEntry(past)
                        Divider().opacity(0.2)
                    }
                    if !route.verdict.isEmpty {
                        if route.phase == .refused || route.verdict.hasPrefix("UNKNOWN") {
                            gapSection
                        } else {
                            answerSection
                            evidenceSection
                        }
                        if route.contested { conflictSection }
                    }
                    Color.clear.frame(height: 1).id("tail")
                }
                .padding(14)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .onChange(of: route.verdict) { _, new in
                // A settled verdict is pushed back before the next one
                // arrives; the live section always shows the newest.
                if !new.isEmpty, route.phase != .routing {
                    let e = Entry(subject: route.subject,
                                  verdict: route.verdict,
                                  text: route.answerText,
                                  refused: route.phase == .refused
                                           || new.hasPrefix("UNKNOWN"))
                    if history.last?.verdict != e.verdict
                        || history.last?.subject != e.subject {
                        history.append(e)
                        if history.count > 40 { history.removeFirst() }
                    }
                }
                withAnimation { proxy.scrollTo("tail", anchor: .bottom) }
            }
            }

        }
        .background(.background.opacity(0.35))
    }

    // MARK: - header

    private var header: some View {
        HStack(spacing: 8) {
            Text("VERA")
                .font(.system(size: 11, weight: .semibold, design: .monospaced))
                .tracking(2.2)
            Circle()
                .fill(route.phase == .idle ? VeraInk.quiet : VeraInk.working)
                .frame(width: 5, height: 5)
            Text(route.phase == .idle ? "READY" : "WORKING")
                .font(.system(size: 10, design: .monospaced))
                .foregroundStyle(.secondary)
            Spacer()
            Text("LLM 不使用")
                .font(.system(size: 10, design: .monospaced))
                .foregroundStyle(.tertiary)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
    }

    // MARK: - sections

    private var answerSection: some View {
        section("ANSWER", tint: VeraInk.verified) {
            VStack(alignment: .leading, spacing: 6) {
                Text(route.answerText.isEmpty ? route.subject : route.answerText)
                    .font(.system(size: 13))
                    .textSelection(.enabled)
                HStack(spacing: 10) {
                    reading(route.verdict)
                    if let a = route.grainAgree, let o = route.grainOf {
                        reading("grain \(a)/\(o)")
                    }
                    if let w = route.witnesses { reading("witnesses \(w)") }
                }
            }
        }
    }

    private var evidenceSection: some View {
        section("EVIDENCE", tint: VeraInk.verified) {
            if route.origins.isEmpty {
                Text("出典の記録なし — この判定は面の出所を持ちません。")
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
            } else {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(route.origins, id: \.self) { o in
                        HStack(spacing: 6) {
                            Image(systemName: "checkmark")
                                .font(.system(size: 9, weight: .semibold))
                                .foregroundStyle(VeraInk.verified)
                            Text(o)
                                .font(.system(size: 11, design: .monospaced))
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                        }
                    }
                }
            }
        }
    }

    private var gapSection: some View {
        section("GAP", tint: VeraInk.unsettled) {
            VStack(alignment: .leading, spacing: 6) {
                Text(route.verdict)
                    .font(.system(size: 12, weight: .medium, design: .monospaced))
                Text("これは失敗ではありません。証拠が無いことを、型を付けて述べています。")
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
                if !route.gaps.isEmpty {
                    Text("既知の欠落: " + route.gaps.prefix(4).joined(separator: "・"))
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(.secondary)
                }
                if !route.remedy.isEmpty {
                    Text("閉じるには: \(route.remedy)")
                        .font(.system(size: 11))
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    private var conflictSection: some View {
        section("CONFLICT", tint: VeraInk.contested) {
            Text("同一の相に両極が質量を持っています。どちらの側も出典つきで保持され、判定は降格されました。")
                .font(.system(size: 11))
                .foregroundStyle(.secondary)
        }
    }

    @ViewBuilder
    private func pastEntry(_ e: Entry) -> some View {
        section(e.refused ? "GAP" : "ANSWER",
                tint: e.refused ? VeraInk.unsettled : VeraInk.verified) {
            VStack(alignment: .leading, spacing: 4) {
                Text(e.text.isEmpty ? e.subject : e.text)
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
                reading(e.verdict)
            }
        }
    }

    // MARK: - chrome

    private func section<C: View>(_ title: String, tint: Color,
                                  @ViewBuilder content: () -> C) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack(spacing: 6) {
                Rectangle().fill(tint).frame(width: 2, height: 10)
                Text(title)
                    .font(.system(size: 10, weight: .semibold, design: .monospaced))
                    .tracking(1.6)
                    .foregroundStyle(.secondary)
            }
            content()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func reading(_ s: String) -> some View {
        Text(s)
            .font(.system(size: 10, design: .monospaced))
            .monospacedDigit()
            .foregroundStyle(.tertiary)
    }

    private var composer: some View {
        HStack(spacing: 8) {
            TextField("問いを入力…", text: $draft)
                .textFieldStyle(.plain)
                .font(.system(size: 12))
                .onSubmit(send)
            Button(action: send) {
                Image(systemName: "return")
                    .font(.system(size: 11, weight: .medium))
            }
            .buttonStyle(.plain)
            .foregroundStyle(draft.isEmpty ? .tertiary : .secondary)
            .disabled(draft.isEmpty)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
    }

    private func send() {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        draft = ""
        app.sendMessage(with: text)
    }
}

/// The instrument's own readout: what the store holds, right now.
/// Real counts from the engine — a status line with invented numbers
/// would be the first lie on a screen built to refuse them.
@MainActor
final class VeraStatusModel: ObservableObject {
    @Published private(set) var cores: Int?
    @Published private(set) var gaps: Int?

    func load() async {
        if let obj = await VeraMemoryBridge.callDoor("vera_sovereigns", [:]) {
            if let n = obj["cores"] as? Int { cores = n }
            else if let leaves = obj["leaves"] as? [String: Any] {
                cores = leaves.values.compactMap { ($0 as? [String: Any])?["cores"] as? Int }
                    .reduce(0, +)
            }
        }
        if let g = await VeraMemoryBridge.callDoor("find_similar_gaps", ["limit": 1]),
           let n = g["total"] as? Int { gaps = n }
    }
}

struct VeraStatusStrip: View {
    @ObservedObject var status: VeraStatusModel
    @ObservedObject private var route = VeraRouteState.shared

    var body: some View {
        HStack(spacing: 16) {
            Text("VERA-A")
                .font(.system(size: 10, weight: .semibold, design: .monospaced))
                .tracking(1.8)
            item(route.phase == .idle ? "READY" : "WORKING",
                 dot: route.phase == .idle ? VeraInk.quiet : VeraInk.working)
            if let c = status.cores { item("\(c.formatted()) NODES") }
            item("\(route.origins.count) EVIDENCE")
            item("\(route.contested ? 1 : 0) CONFLICTS",
                 dot: route.contested ? VeraInk.contested : nil)
            if !route.gaps.isEmpty { item("\(route.gaps.count) GAPS", dot: VeraInk.unsettled) }
            Spacer()
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 7)
        .background(.quaternary.opacity(0.25))
    }

    private func item(_ s: String, dot: Color? = nil) -> some View {
        HStack(spacing: 5) {
            if let dot { Circle().fill(dot).frame(width: 5, height: 5) }
            Text(s)
                .font(.system(size: 10, design: .monospaced))
                .monospacedDigit()
                .foregroundStyle(.secondary)
        }
    }
}
