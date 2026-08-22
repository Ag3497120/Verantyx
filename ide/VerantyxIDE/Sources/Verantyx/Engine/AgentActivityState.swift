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
        case .thinking:      return Color(red: 0.55, green: 0.60, blue: 0.95)  // indigo
        case .generating:    return Color(red: 0.35, green: 0.85, blue: 1.00)  // cyan
        case .exploring:     return Color(red: 0.40, green: 0.85, blue: 0.55)  // green
        case .operatingApp:  return Color(red: 1.00, green: 0.65, blue: 0.20)  // amber
        case .waitingUser:   return Color(red: 0.95, green: 0.85, blue: 0.30)  // yellow
        case .error:         return Color(red: 1.00, green: 0.35, blue: 0.35)  // red
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

        // "Done" is a moment, not a state to sit in.
        if case .completed = next {
            settleTask = Task { [weak self] in
                try? await Task.sleep(nanoseconds: 1_800_000_000)
                guard !Task.isCancelled else { return }
                self?.set(.idle)
            }
        }
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
