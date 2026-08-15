import SwiftUI

/// A summoned surface, rendered inside the chat rather than beside it.
///
/// The panel arrives where the person was already looking — under the
/// last thing they read, above the line they type — because a surface
/// that opens somewhere else makes them hunt for what they just asked
/// for. It carries its own name and one way to dismiss it, and nothing
/// else: the chrome was removed to stop teaching a second vocabulary,
/// and rebuilding it inside the card would undo the point.
struct VeraSummonedPanel: View {
    @EnvironmentObject var app: AppState
    let panel: VeraSummon.Panel
    /// False for every copy but the newest of its kind. A frozen copy is
    /// still a LIVE view — it reads the same AppState and the same
    /// defaults, so a change made in the newest one shows up here — it
    /// simply cannot be typed into. Two editable copies of one setting is
    /// two answers to "what is it set to", and the loser is whichever one
    /// the user happened to be looking at.
    var editable: Bool = true
    var onClose: () -> Void = {}

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 8) {
                Text(panel.title)
                    .font(.system(size: 11, weight: .semibold, design: .monospaced))
                    .tracking(1.8)
                    .foregroundStyle(.secondary)
                Spacer()
                if !editable {
                    Text("読み取り専用 — 操作は下の新しい方で")
                        .font(.system(size: 10))
                        .foregroundStyle(.tertiary)
                }
                Button {
                    onClose()
                } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 10, weight: .medium))
                }
                .buttonStyle(.plain)
                .foregroundStyle(.tertiary)
                .help("閉じる — もう一度名前を言えば戻ります")
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 9)

            Divider().opacity(0.3)

            content
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .background(.quaternary.opacity(0.28), in: RoundedRectangle(cornerRadius: 6))
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .strokeBorder(Color.primary.opacity(0.10), lineWidth: 0.8)
        )
        // No height clamp. SettingsView is a fixed 680x560 modal, and a
        // 420pt cap simply cut it off — the panel was showing two thirds
        // of a screen with the rest unreachable.
        .opacity(editable ? 1 : 0.72)
        .disabled(!editable)
    }

    @ViewBuilder
    private var content: some View {
        switch panel {
        case .settings:
            // At its own 680x560 and no wider. Wrapping it in a scroll
            // view that filled the card looked harmless and was not: that
            // scroller covered the whole row, so a wheel anywhere near the
            // panel scrolled ITS contents and the transcript underneath
            // could never be scrolled past it. SettingsView already
            // scrolls its own body; the margin beside it belongs to the
            // conversation.
            SettingsView().environmentObject(app)
                .fixedSize()
                .padding(.vertical, 2)
        case .memory:
            // Both halves of memory in one place: the ledger that was
            // parked in the left column (with its 承認 buttons) over the
            // console's capacity proposals.
            VStack(spacing: 0) {
                MemoryLedgerList().frame(maxHeight: 150)
                Divider().opacity(0.3)
                MemoryConsoleView().environmentObject(app)
            }
        case .audit:
            // The strip that used to sit above every conversation. Its
            // numbers are real (nodes, evidence, conflicts, gaps) — they
            // just do not need to be on screen while you type.
            VStack(alignment: .leading, spacing: 0) {
                AuditSummonHeader()
                Text("直近の監査サマリはありません。実行後に現れます。")
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
                    .padding(12)
            }
        case .cross:
            StereoCrossView(span: 300, showsLabels: true)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
        case .modes:
            modeList
        case .model:
            modelList
        }
    }

    /// Modes as a list rather than a segmented control: the person got
    /// here by naming a mode or naming "モード", and a list says what
    /// the other names are.
    private var modeList: some View {
        VStack(alignment: .leading, spacing: 0) {
            ForEach(AppState.VeraEngineMode.allCases, id: \.self) { mode in
                Button {
                    app.veraEngineMode = mode
                    onClose()
                } label: {
                    HStack(spacing: 8) {
                        Circle()
                            .fill(app.veraEngineMode == mode
                                  ? VeraInk.verified : Color.clear)
                            .frame(width: 5, height: 5)
                        Text(label(for: mode))
                            .font(.system(size: 12))
                        Spacer()
                        Text(say(for: mode))
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(.tertiary)
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 7)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.vertical, 4)
    }

    private var modelList: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("モデルの切り替えは入力欄のモデル名から行えます。")
                .font(.system(size: 11))
                .foregroundStyle(.secondary)
            Text("Vera の版は「ローカル」ピッカー、会話モデルは Gatekeeper の隣。")
                .font(.system(size: 11))
                .foregroundStyle(.tertiary)
        }
        .padding(12)
    }

    private func label(for m: AppState.VeraEngineMode) -> String {
        switch m {
        case .council:    return "jgen 合議"
        case .standalone: return "Vera-a(併用)"
        case .veraModel:  return "Vera(単体・LLM不使用)"
        case .veraBot:    return "Vera Bot(設定・UIの案内)"
        case .localLLM:   return "LLM"
        }
    }

    /// What to type to get here without opening anything.
    private func say(for m: AppState.VeraEngineMode) -> String {
        switch m {
        case .council:    return "合議"
        case .standalone: return "vera-a"
        case .veraModel:  return "vera"
        case .veraBot:    return "bot"
        case .localLLM:   return "llm"
        }
    }
}


/// The old VERA-A strip, given a home instead of a residence.
private struct AuditSummonHeader: View {
    @StateObject private var status = VeraStatusModel()

    var body: some View {
        VeraStatusStrip(status: status)
            .task { await status.load() }
    }
}


// MARK: - Bot mode's transcript: text and panels in one log

/// Bot mode is a chat, so it reads as one. Your line, then whatever it
/// produced under it — a settings screen is a reply like any other, and
/// asking for the next thing puts that below rather than replacing what
/// you already opened.
///
/// The ordinary transcript is an NSTextView (one text storage, so
/// selection crosses messages), which is the right thing for prose and
/// cannot hold a live control. This one is the other half: the same
/// `app.messages`, rendered as views, for the one mode whose replies are
/// screens.
struct VeraBotTranscript: View {
    @EnvironmentObject var app: AppState

    private struct Entry: Identifiable {
        let id: UUID
        let message: ChatMessage
        let panel: VeraSummon.Panel?
        /// The newest copy of its kind is the one you can touch.
        let editable: Bool
    }

    private var entries: [Entry] {
        // Which index is the newest of each panel kind — computed once,
        // not per row, so this stays linear as the log grows.
        var newest: [VeraSummon.Panel: Int] = [:]
        for (i, m) in app.messages.enumerated() {
            if let p = VeraSummon.panel(fromMarker: m.content) { newest[p] = i }
        }
        return app.messages.enumerated().compactMap { i, m in
            if let p = VeraSummon.panel(fromMarker: m.content) {
                return Entry(id: m.id, message: m, panel: p, editable: newest[p] == i)
            }
            // System chatter stays out: in Bot mode the panel IS the
            // acknowledgement, and a "▸ 召喚: 設定" line under a settings
            // screen is the app narrating what you can already see.
            guard m.role != .system, !m.isSpotlight,
                  !m.content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            else { return nil }
            return Entry(id: m.id, message: m, panel: nil, editable: true)
        }
    }

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 12) {
                    ForEach(entries) { entry in
                        row(entry).id(entry.id)
                    }
                    Color.clear.frame(height: 1).id("bottom")
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 12)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .onChange(of: app.messages.count) { _, _ in
                withAnimation(.spring(response: 0.35, dampingFraction: 0.86)) {
                    proxy.scrollTo("bottom", anchor: .bottom)
                }
            }
        }
    }

    @ViewBuilder
    private func row(_ entry: Entry) -> some View {
        if let panel = entry.panel {
            VeraSummonedPanel(panel: panel, editable: entry.editable) {
                app.messages.removeAll { $0.id == entry.id }
            }
            .environmentObject(app)
            .transition(.opacity.combined(with: .move(edge: .bottom)))
        } else if entry.message.role == .user {
            Text(entry.message.content)
                .font(.system(size: 12.5))
                .foregroundStyle(.primary.opacity(0.92))
                .padding(.horizontal, 11).padding(.vertical, 7)
                .background(.quaternary.opacity(0.35),
                            in: RoundedRectangle(cornerRadius: 9))
                .frame(maxWidth: .infinity, alignment: .trailing)
        } else {
            Text(entry.message.content)
                .font(.system(size: 12.5))
                .foregroundStyle(.primary.opacity(0.88))
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}
