import SwiftUI
import AppKit

/// A summoned surface: its own name, one way to dismiss it, nothing else.
///
/// Originally rendered inside the chat, under the line that asked for
/// it — that mount point was Bot mode's transcript (VeraBotTranscript,
/// removed 2026-08-26 with Bot mode itself; see the note below). The
/// one caller left is SettingsView's "All Screens" list, which presents
/// this as a sheet instead: same view, same content switch, a plainer
/// way in. The chrome-free shape (no second vocabulary of its own,
/// nothing rebuilt inside the card) is still the point either way.
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
        case .document:
            VeraDocumentPanel().environmentObject(app)
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
        case .licences:
            AppLicenceView()
        case .screen:
            VeraScreenPresenceView()
        case .jgen:
            // The engine's own knobs — memory layers, the council core, the
            // execution agent. It was reachable only from a rail that no
            // longer exists.
            JGenVeraSettingsPanelView(
                showPendingToolCalls: .constant(false),
                showReasoningTimeline: .constant(false))
                .environmentObject(app)
                .frame(minWidth: 560, minHeight: 420)
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
                    app.selectEngineMode(mode)
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
        case .atelier:    return "Vera Atelier(服飾)"
        case .localLLM:   return "LLM"
        }
    }

    /// What to type to get here without opening anything.
    private func say(for m: AppState.VeraEngineMode) -> String {
        switch m {
        case .atelier:    return "atelier"
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


// MARK: - Bot mode's transcript: removed with Bot mode (2026-08-26)
//
// VeraBotTranscript used to render app.messages as views (settings
// screens summoned mid-conversation are live controls, not text — the
// ordinary NSTextView transcript cannot hold one). It read entries by
// scanning app.messages for VeraSummon.marker(...) system messages,
// which only AppState.sendMessage's Bot-mode "Summon by name" block
// ever wrote. That block is gone with Bot mode, so this view had zero
// producers left and was deleted rather than kept compiling with
// nothing to show. VeraSummonedPanel (above) is not part of that
// deletion — it is still mounted from SettingsView's "All Screens" list.


// MARK: - 前面に居ながら、写らない
//
// Two properties that sound related and are not, and the pair is what makes
// an agent that drives the screen usable.
//
// **常に前面** is for the person. While Vera works, the window they are
// reading from keeps getting buried by the app Vera just brought forward.
// `.floating` keeps it above ordinary windows so they can watch.
//
// **写らない** is for Vera. Every screenshot the agent takes of another app
// had Verantyx sitting on top of it — its own window in its own evidence.
// The existing answer was to move the window out of the way and put it back,
// which is visible, slow, and races with whatever the user is doing.
// `NSWindow.sharingType = .none` is the real answer: the window keeps its
// position, stays visible to the person, and is excluded from capture at the
// window-server level, so it is absent from CGWindowList and ScreenCaptureKit
// alike. Nothing to move, nothing to restore, nothing to race.
//
// They are separate switches because they have separate costs. Excluding the
// window from capture also excludes it from the user's OWN screen recordings
// and from screen sharing — which is exactly wrong when they are demonstrating
// the app to someone. So it is a choice, defaulted to the agent's need and
// reversible in one click.
@MainActor
final class VeraWindowPresence: ObservableObject {

    static let shared = VeraWindowPresence()

    @Published var alwaysOnTop: Bool {
        didSet {
            UserDefaults.standard.set(alwaysOnTop, forKey: "vera_window_on_top")
            apply()
        }
    }

    @Published var hiddenFromCapture: Bool {
        didSet {
            UserDefaults.standard.set(hiddenFromCapture, forKey: "vera_window_hidden_capture")
            apply()
        }
    }

    private init() {
        let d = UserDefaults.standard
        alwaysOnTop = d.bool(forKey: "vera_window_on_top")
        // Defaulted ON: the agent's screenshots are evidence, and this app
        // appearing in its own evidence is the first thing to remove. A
        // person who wants to record the app turns it off and sees why.
        hiddenFromCapture = d.object(forKey: "vera_window_hidden_capture") as? Bool ?? true
    }

    /// Applied to every window the app owns, including ones opened later —
    /// a setting that holds for the main window and quietly fails for a
    /// panel is worse than no setting, because the leak is the exception.
    func apply() {
        for window in NSApp.windows {
            // Overlays that deliberately live above everything (the edge
            // glow at .screenSaver) keep their own level.
            if window.level.rawValue < NSWindow.Level.screenSaver.rawValue {
                window.level = alwaysOnTop ? .floating : .normal
            }
            window.sharingType = hiddenFromCapture ? .none : .readOnly
        }
    }

    /// True when the window server currently reports every app window as
    /// excluded. Read back rather than assumed: `sharingType` is a request,
    /// and a window created after the last apply() would not carry it.
    var appliedEverywhere: Bool {
        let windows = NSApp.windows.filter { $0.isVisible }
        guard !windows.isEmpty else { return false }
        return windows.allSatisfy {
            ($0.sharingType == .none) == hiddenFromCapture
        }
    }
}

// MARK: - The panel for it

struct VeraScreenPresenceView: View {
    @ObservedObject private var presence = VeraWindowPresence.shared
    @State private var verified: Bool?

    private func t(_ en: String, _ ja: String) -> String {
        AppLanguage.shared.t(en, ja)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Toggle(isOn: $presence.alwaysOnTop) {
                VStack(alignment: .leading, spacing: 1) {
                    Text(t("Always in front", "常に前面"))
                        .font(.system(size: 12))
                    Text(t("Stays above other windows, so you can watch while Vera works.",
                           "他のウィンドウより前に居続けます。Veraが作業している間も読めます。"))
                        .font(.system(size: 10)).foregroundStyle(.tertiary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .toggleStyle(.switch).controlSize(.mini)

            Toggle(isOn: $presence.hiddenFromCapture) {
                VStack(alignment: .leading, spacing: 1) {
                    Text(t("Not in screenshots", "スクショに写さない"))
                        .font(.system(size: 12))
                    Text(t("Excluded from capture at the window server, so Vera's own "
                           + "screenshots show the app it is operating and not this one. "
                           + "Also excludes it from YOUR recordings and screen sharing.",
                           "ウィンドウサーバ側で捕捉から除外します。Vera自身のスクショには"
                           + "操作対象のアプリだけが写り、このウィンドウは写りません。"
                           + "あなた自身の画面収録・画面共有からも外れます。"))
                        .font(.system(size: 10)).foregroundStyle(.tertiary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .toggleStyle(.switch).controlSize(.mini)

            Divider().opacity(0.2)

            // Read back from the window server rather than echoing the
            // switch: this is the one claim on the panel that could be
            // false while the switch says true.
            HStack(spacing: 6) {
                Circle()
                    .fill(verified == true ? Theme.ok
                          : (verified == false ? Theme.bad
                                               : Color.secondary))
                    .frame(width: 5, height: 5)
                Text(verified == nil
                     ? t("Not checked yet.", "未確認")
                     : (verified! ? t("Every open window matches the setting.",
                                      "開いている全ウィンドウが設定どおりです")
                                  : t("A window does not match — reapplying.",
                                      "設定と違うウィンドウがあります — 再適用します")))
                    .font(.system(size: 10)).foregroundStyle(.tertiary)
                Spacer()
                Button(t("Check", "確認")) { check() }
                    .buttonStyle(.plain).font(.system(size: 10))
                    .foregroundStyle(Theme.sel)
            }
        }
        .padding(12)
        .onAppear { presence.apply(); check() }
    }

    private func check() {
        let ok = presence.appliedEverywhere
        if !ok { presence.apply() }
        verified = presence.appliedEverywhere
    }
}
