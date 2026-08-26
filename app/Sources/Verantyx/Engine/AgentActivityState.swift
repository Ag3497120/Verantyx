import SwiftUI

// MARK: - What the agent is doing, as one value
//
// The first version of the glow read `isGenerating || isAgentControllingMouse`.
// That collapses four different situations into one light: planning, streaming
// tokens, searching the web, and driving another app all looked identical, and
// "waiting for you" looked the same as idle — which is the one distinction the
// user actually needs, because in that state nothing will happen until they
// act.
//
// So the UI does not read booleans any more. It reads this, and this is
// advanced from the loop's own events. One state machine, one source, and
// every indicator — window edge, composer, menu bar icon — agrees by
// construction rather than by three separate conditions being kept in sync.
enum AgentState: Equatable {
    case idle
    case thinking            // between turns: planning, choosing a tool
    case generating          // tokens arriving
    case exploring           // web search / reading pages
    case operatingApp        // driving another Mac app: mouse, keys, AX
    case waitingUser         // will not proceed until the user acts
    case completed           // just finished; settles to idle
    case error(String)

    /// Whether the window edge lights at all. Idle and completed do not: a
    /// light that is always on stops carrying information.
    var glows: Bool {
        switch self {
        case .idle, .completed: return false
        default: return true
        }
    }

    /// Steady rather than breathing. A pulse says "working"; a solid edge says
    /// "stopped, look at me" — so error and waiting hold still.
    var pulses: Bool {
        switch self {
        case .thinking, .generating, .exploring, .operatingApp: return true
        default: return false
        }
    }

    var color: Color {
        switch self {
        case .idle, .completed: return .clear
        case .thinking:      return Theme.sel  // indigo
        case .generating:    return Color(red: 0.35, green: 0.85, blue: 1.00)  // cyan
        case .exploring:     return Theme.ok  // green
        case .operatingApp:  return Theme.warn  // amber
        case .waitingUser:   return Theme.warn  // yellow
        case .error:         return Theme.bad  // red
        }
    }

    var icon: String {
        switch self {
        case .idle:          return "circle"
        case .thinking:      return "brain"
        case .generating:    return "text.cursor"
        case .exploring:     return "globe"
        case .operatingApp:  return "cursorarrow.rays"
        case .waitingUser:   return "hand.raised"
        case .completed:     return "checkmark.circle"
        case .error:         return "exclamationmark.triangle"
        }
    }

    var label: String {
        switch self {
        case .idle:         return AppLanguage.shared.t("Idle", "待機中")
        case .thinking:     return AppLanguage.shared.t("Planning", "考え中")
        case .generating:   return AppLanguage.shared.t("Generating", "生成中")
        case .exploring:    return AppLanguage.shared.t("Exploring the web", "Web探索中")
        case .operatingApp: return AppLanguage.shared.t("Operating your Mac", "Mac操作中")
        case .waitingUser:  return AppLanguage.shared.t("Waiting for you", "入力待ち")
        case .completed:    return AppLanguage.shared.t("Done", "完了")
        case .error(let e): return AppLanguage.shared.t("Stopped: \(e)", "停止: \(e)")
        }
    }

    /// Shown where there is room for a sentence. Only the states where the
    /// user has to understand something have one.
    var hint: String? {
        switch self {
        case .operatingApp:
            return AppLanguage.shared.t(
                "The agent has the screen — clicking elsewhere may interrupt it.",
                "エージェントが画面を操作しています — 別の場所をクリックすると中断することがあります。")
        case .waitingUser:
            return AppLanguage.shared.t(
                "Type to continue — nothing will happen until you do.",
                "操作を続けるには入力してください — 入力するまで先へ進みません。")
        case .error(let e):
            return e
        default:
            return nil
        }
    }
}

// MARK: - The one place it changes

@MainActor
final class AgentActivityCenter: ObservableObject {

    static let shared = AgentActivityCenter()

    @Published private(set) var state: AgentState = .idle

    /// Coarse activity log for `AgentActivityStreamView` — one entry per
    /// state transition, not per tool call. The view was built for
    /// per-tool-call granularity and had no producer at all before this;
    /// this is real (every entry is a genuine `set()` transition, the same
    /// ones that already drive the composer glow and the window edge), just
    /// coarser than the view's own comments describe. A finer feed would
    /// need `enter(for:)` to carry the tool's own start/finish, which it
    /// does not yet report back.
    @Published private(set) var log: [AgentActivity] = []

    private var settleTask: Task<Void, Never>?

    /// A run that stops to ask the user still reports `.done` — the loop
    /// returns, because it cannot proceed. Without this the pause would show
    /// as "completed" and the light would go out, which is precisely backwards:
    /// that is the one state where the user has to do something.
    ///
    /// Set immediately before emitting the pause, consumed by the .done
    /// handler. One-shot, so a later ordinary finish is unaffected.
    private var userGatePending = false

    func expectUserGate() { userGatePending = true }

    /// What `.done` should mean right now.
    func finish() {
        if userGatePending {
            userGatePending = false
            set(.waitingUser)
        } else {
            set(.completed)
        }
    }

    func set(_ next: AgentState) {
        settleTask?.cancel()
        guard state != next else { return }
        let previous = state
        state = next

        // The screen-change detector runs while the agent is out driving the
        // machine, and only then. It is the independent check on claims about
        // the screen — deliberately separate from anything the model produces,
        // so "the page loaded" can be tested rather than believed.
        if next == .operatingApp || next == .exploring {
            ScreenChangeMonitor.shared.start()
        } else if !next.glows {
            ScreenChangeMonitor.shared.stop()
        }
        NotificationCenter.default.post(name: .veraRunStateChanged, object: nil)
        recordTransition(from: previous, to: next)

        // "Done" is a moment, not a state to sit in.
        if case .completed = next {
            settleTask = Task { [weak self] in
                try? await Task.sleep(nanoseconds: 1_800_000_000)
                guard !Task.isCancelled else { return }
                self?.set(.idle)
            }
        }
    }

    /// Closes the previous row (if it was still `.running`) and opens a new
    /// one for `next`. Idle never gets a row of its own — nothing is
    /// happening, so there is nothing to log.
    private func recordTransition(from previous: AgentState, to next: AgentState) {
        if !log.isEmpty, log[log.count - 1].state == .running {
            // 直す前は `previous`（閉じる行そのもの）を見ていたが、それは常に
            // .exploring 等の実行中状態で、.error になるのは `next` 側。
            // 一段遅れて次の遷移で誤って別の行を failed にしていたバグの修正。
            let failed: Bool
            if case .error = next { failed = true } else { failed = false }
            log[log.count - 1].state = failed ? .failed : .succeeded
        }
        guard next.glows else { return }
        let kind: AgentActivity.Kind
        switch next {
        case .exploring:    kind = .observation
        case .operatingApp: kind = .tool
        case .generating:   kind = .command
        default:            kind = .thought
        }
        log.append(AgentActivity(label: next.label, detail: next.hint, state: .running, kind: kind))
        if log.count > 300 { log.removeFirst(log.count - 300) }
    }

    /// Derive the state from a tool about to run. What the agent is *doing* is
    /// the tool it picked — asking the tool is more honest than tracking a
    /// separate flag that has to be set and cleared correctly everywhere.
    func enter(for tool: AgentTool) {
        switch tool {
        case .browse, .search, .searchMulti, .searchPage, .clickLink, .scrollFind,
             .visionBrowse, .visionSearchFlow, .evalJS, .openSafari, .openChrome:
            set(.exploring)
        case .useApp, .desktopAct, .desktopSnapshot, .axAct, .visionAct, .visionSnapshot,
             .openApp, .osascript, .pastePayload, .registerUIElement, .waitUntilStable:
            set(.operatingApp)
        case .askHuman:
            set(.waitingUser)
        default:
            set(.thinking)
        }
    }
}
