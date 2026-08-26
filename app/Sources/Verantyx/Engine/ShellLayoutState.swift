import Foundation
import SwiftUI

// MARK: - ShellLayoutState
//
// The IDE shell's layout — which tabs are open in the centre, what is
// mounted in the left/right slots, and whether the garment screen is
// expanded to full width — used to be view-local `@State` scattered across
// HumanPriorityModeView (`activitySection`), AppState (`stageMode`,
// `aiPanels`, `fullSurface`) and a handful of other places. Each read a
// different piece of "what is on screen right now" and none of them agreed,
// which is why closing everything never quite left a blank window — some
// piece of state always kept a pane alive.
//
// This is the one model. Every door in the shell (rail buttons, tab ×,
// panel-mount offers, the garment expand toggle) goes through here, and
// it persists across launches the same way a real IDE's window layout does.
//
// 置く場所は一つ。ここを読めば「今何が開いているか」が全部わかる。

/// The seven panels that exist as views but, before this, were only
/// reachable by being left mounted somewhere permanent. Each can be opened
/// as a centre tab OR mounted into the left/right slot — the registry is
/// what the rail buttons and the mount-request banner both read.
enum MountablePanelKind: String, Codable, CaseIterable, Identifiable {
    case agentActivity
    case stereoCross
    case memoryLayer
    case failureDomains
    case swarmMonitor
    case git
    case mcp

    var id: String { rawValue }

    /// **表に出すか。** このアプリは服飾の道具で、Verantyx のエージェント
    /// 基盤はその下で動いているだけ。基盤の内部を見る窓（記憶層・故障領域・
    /// 群れの監視・git・MCP）は**使うが、服を作る人の目の前には置かない**。
    ///
    /// 消してはいない — ``mount(_:in:)`` は今も全種類を受ける。レールと
    /// 「パネルを表示」の一覧に出ないだけで、基盤を呼ぶ側からは今までどおり
    /// 開ける。**表に出さないことと、無いことは違う。**
    var surfaced: Bool {
        switch self {
        // 服を作る作業そのものに属するもの。エージェントが動いている間、
        // 「働いている」と「詰まっている」の区別がつくのはここだけ。
        case .agentActivity: return true
        // **立体十字のグラフは、この道具の台帳を描いていない。** 自分の
        // docstring がそう書いている — "Live 3D visualization of Vera's
        // CrossStore … `graph_snapshot` MCP tool, Verantyx-Vera-alpha's
        // mcp_server.py"。別のサーバの記憶を描く窓で、服の台帳とは無関係。
        // もう一方の表示(UIテスト・トレース)はバグ再現の可視化で、これも
        // 服を作る人には要らない。**概念としての立体十字は photoloset の
        // 中核だが、この画面はそれを描いていない。**
        case .stereoCross: return false
        // 基盤の内部。下で動いていればよい。
        case .memoryLayer, .failureDomains, .swarmMonitor, .git, .mcp:
            return false
        }
    }

    /// 表に出す種類だけ。レールと「+」の一覧はこれを読む。
    static var surfacedCases: [MountablePanelKind] {
        allCases.filter(\.surfaced)
    }

    var icon: String {
        switch self {
        case .agentActivity: return "waveform.path.ecg"
        case .stereoCross:   return "cube.transparent"
        case .memoryLayer:   return "square.stack.3d.up"
        case .failureDomains: return "list.bullet.rectangle"
        case .swarmMonitor:  return "person.3.sequence"
        case .git:           return "arrow.triangle.branch"
        case .mcp:           return "point.3.connected.trianglepath.dotted"
        }
    }

    func title(japanese: Bool) -> String {
        switch self {
        case .agentActivity: return japanese ? "エージェント活動" : "Agent Activity"
        case .stereoCross:   return japanese ? "立体十字構造体" : "Stereo Cross"
        case .memoryLayer:   return japanese ? "記憶レイヤー" : "Memory Layers"
        case .failureDomains: return japanese ? "失敗の型" : "Failure Domains"
        case .swarmMonitor:  return japanese ? "スウォーム" : "Swarm"
        case .git:           return japanese ? "Git" : "Git"
        case .mcp:           return japanese ? "MCP" : "MCP"
        }
    }
}

/// Which side slot a panel (or a mount offer) targets.
enum ShellSide: String, Codable {
    case left, right
}

/// One tab in the centre. Files/folders carry a path; everything else is a
/// singleton kind — opening it twice activates the existing tab rather than
/// duplicating it, the same way a real IDE does not let you open the same
/// file in two tabs by accident.
enum ShellTabKind: Equatable, Codable, Hashable {
    case file(path: String)
    case folder(path: String)
    case garment
    case chat
    case panel(MountablePanelKind)
    case terminal
    case diff
    case artifact
    case memory
    case search
    case aiPanel(id: String)

    /// Two tabs of the same singleton kind are the same tab; two file tabs
    /// are the same tab only when the path matches.
    var identityKey: String {
        switch self {
        case .file(let p):   return "file:\(p)"
        case .folder(let p): return "folder:\(p)"
        case .garment:       return "garment"
        case .chat:          return "chat"
        case .panel(let k):  return "panel:\(k.rawValue)"
        case .terminal:      return "terminal"
        case .diff:          return "diff"
        case .artifact:      return "artifact"
        case .memory:        return "memory"
        case .search:        return "search"
        case .aiPanel(let id): return "aiPanel:\(id)"
        }
    }
}

extension ShellTabKind {
    /// Whether this tab kind can exist while the shell is in `mode`. The
    /// two modes are not a label on the same shell — the owner's brief is
    /// explicit that the pattern differs: a garment person never sees a
    /// code-editor affordance, an LLM user never sees 服飾. This is the one
    /// place that answers "can this tab exist here", read by both
    /// ``ShellLayoutState/pruneTabs(incompatibleWith:)`` (mode switches,
    /// restore) and the rail (what it offers to open in the first place).
    func isAllowed(in mode: AppState.VeraEngineMode) -> Bool {
        switch mode {
        case .atelier:
            // コードエディタの道具立て。服を作る人には邪魔で、AI が
            // 読み込む先にもなり得る、と owner が明言している一群。
            switch self {
            case .file, .folder, .terminal, .diff, .search: return false
            default: return true
            }
        case .localLLM:
            // 服飾は atelier だけの面。LLM モードの人が服飾タブを
            // 一度も持ったことがなくても、モード切替の直後に前回の
            // 服飾タブが持ち越されて出てくることはあり得る。
            switch self {
            case .garment: return false
            default: return true
            }
        }
    }
}

struct ShellTab: Identifiable, Equatable, Codable {
    let id: UUID
    var kind: ShellTabKind

    init(kind: ShellTabKind) {
        self.id = UUID()
        self.kind = kind
    }
}

/// An agent (or the stereo cross, when a save lands) OFFERING a panel — never
/// forcing one. The shell shows this as a small dismissible strip; accepting
/// it is the only thing that actually mounts anything.
struct PanelMountRequest: Identifiable, Equatable {
    let id = UUID()
    let panel: MountablePanelKind
    let reasonEN: String
    let reasonJA: String
    let suggestedSide: ShellSide
}

@MainActor
final class ShellLayoutState: ObservableObject {

    /// Mirrors `AppState.veraEngineMode` — kept in sync from its `didSet`.
    /// `openTab` reads this so **every** door into a tab (rail clicks, the
    /// composer, an agent proposing to open a file, a 名前で呼ぶ summon)
    /// is stopped at the one gate, not just the rail buttons this pass
    /// happened to touch. Defaults to `.atelier` to match
    /// `AppState.veraEngineMode`'s own default; nothing observes this
    /// before `AppState` finishes constructing (see `pruneTabs` for why
    /// restore-time filtering still needs its own separate call).
    var currentMode: AppState.VeraEngineMode = .atelier

    @Published var leftPanel: MountablePanelKind?
    @Published var rightPanel: MountablePanelKind?
    @Published var tabs: [ShellTab] = []
    @Published var activeTabID: UUID?
    /// Only meaningful while the active tab is `.garment` — the one screen
    /// allowed to cover the whole shell, per the owner's Claude-desktop
    /// reference (the document pane, never the rail or the side panel).
    @Published var garmentExpanded: Bool = false
    /// The current offer, if any. Set only by `requestMount`, cleared by
    /// accepting or dismissing it.
    @Published private(set) var pendingMountRequest: PanelMountRequest?

    /// Guards against the same offer re-appearing every time the agent
    /// re-enters the same state (e.g. every tool call while exploring) —
    /// once a person has dismissed an offer for a panel, it stays quiet
    /// until that panel actually gets mounted or unmounted again.
    private var dismissedKinds: Set<MountablePanelKind> = []

    private static let defaultsKey = "shell_layout_state_v1"

    var activeTab: ShellTab? {
        guard let id = activeTabID else { return nil }
        return tabs.first { $0.id == id }
    }

    var isEmpty: Bool { tabs.isEmpty }

    init() {
        restore()
    }

    // MARK: - Tabs

    /// Opens a tab for `kind`, or activates the existing one if a tab of
    /// the same identity is already open — same as every editor's "already
    /// open" behaviour.
    @discardableResult
    func openTab(_ kind: ShellTabKind) -> UUID? {
        // このモードに存在できない種類は、どの呼び出し口から来ても開かない
        // — レールのボタンはすでにモードごとに絞ってあるが、エージェントの
        // 提案や 名前で呼ぶ summon はレールを経由しない。ここが唯一の門。
        // 開けなかった場合は nil を返す(以前は activeTabID ?? UUID() という
        // 意味のないダミー ID を返していた — 呼び出し側が将来その値を
        // 「実際に開いたタブの id」と誤読すると、存在しないタブを指す
        // 宙ぶらりんの id を掴むことになる。nil ならその誤読自体ができない)。
        guard kind.isAllowed(in: currentMode) else {
            return nil
        }
        if let existing = tabs.first(where: { $0.kind.identityKey == kind.identityKey }) {
            activeTabID = existing.id
            save()
            return existing.id
        }
        let tab = ShellTab(kind: kind)
        tabs.append(tab)
        activeTabID = tab.id
        save()
        return tab.id
    }

    func closeTab(_ id: UUID) {
        guard let idx = tabs.firstIndex(where: { $0.id == id }) else { return }
        let wasGarment = tabs[idx].kind == .garment
        tabs.remove(at: idx)
        if wasGarment { garmentExpanded = false }
        if activeTabID == id {
            // Land on a neighbour rather than nothing, the way every tabbed
            // editor does — but if that was the last tab, this legitimately
            // becomes the empty state, not a bug to work around.
            if tabs.isEmpty {
                activeTabID = nil
            } else {
                let landIdx = min(idx, tabs.count - 1)
                activeTabID = tabs[landIdx].id
            }
        }
        save()
    }

    /// Drops every open tab whose kind cannot exist in `mode` — called once
    /// `AppState.loadPersistedSettings()` knows the real restored mode, and
    /// again on every live mode switch (``AppState/selectEngineMode(_:)``).
    ///
    /// This can't happen inside ``restore()`` itself: `shell` is built
    /// before `AppState`'s other stored properties finish their own default
    /// initialization (`let shell = ShellLayoutState()` runs ahead of
    /// `veraEngineMode`'s persisted value being read), so at restore time
    /// there is no real mode to prune against yet — the same reason
    /// ``restore()`` already drops `surfaced == false` panels rather than
    /// trusting whatever was mounted last. Leaving this step out would mean
    /// a saved garment tab quietly reappearing in the LLM shell, or a file
    /// tab in Atelier — the exact regression this mirrors.
    func pruneTabs(incompatibleWith mode: AppState.VeraEngineMode) {
        let before = tabs.count
        tabs.removeAll { !$0.kind.isAllowed(in: mode) }
        guard tabs.count != before else { return }
        if let active = activeTabID, !tabs.contains(where: { $0.id == active }) {
            activeTabID = tabs.first?.id
        }
        save()
    }

    func closeAllTabs() {
        tabs.removeAll()
        activeTabID = nil
        garmentExpanded = false
        save()
    }

    func activate(_ id: UUID) {
        guard tabs.contains(where: { $0.id == id }) else { return }
        activeTabID = id
        save()
    }

    func toggleGarmentExpanded() {
        guard activeTab?.kind == .garment else { return }
        garmentExpanded.toggle()
        save()
    }

    // MARK: - Side panels

    func mount(_ kind: MountablePanelKind, in side: ShellSide) {
        switch side {
        case .left:  leftPanel = kind
        case .right: rightPanel = kind
        }
        save()
    }

    func unmount(_ side: ShellSide) {
        switch side {
        case .left:  leftPanel = nil
        case .right: rightPanel = nil
        }
        save()
    }

    func toggleRail(_ side: ShellSide, default kind: MountablePanelKind) {
        switch side {
        case .left:
            leftPanel = (leftPanel == nil) ? kind : nil
        case .right:
            rightPanel = (rightPanel == nil) ? kind : nil
        }
        save()
    }

    // MARK: - Mount requests (offer, never force)
    //
    // 「奪う」ではなく「申し出る」。実際にマウントするのは accept だけ。

    func requestMount(_ kind: MountablePanelKind, reasonEN: String, reasonJA: String,
                       suggestedSide: ShellSide) {
        guard leftPanel != kind, rightPanel != kind else { return }
        guard !dismissedKinds.contains(kind) else { return }
        guard pendingMountRequest?.panel != kind else { return }
        pendingMountRequest = PanelMountRequest(panel: kind, reasonEN: reasonEN,
                                                reasonJA: reasonJA, suggestedSide: suggestedSide)
    }

    func acceptPendingRequest() {
        guard let req = pendingMountRequest else { return }
        mount(req.panel, in: req.suggestedSide)
        dismissedKinds.remove(req.panel)
        pendingMountRequest = nil
    }

    func dismissPendingRequest() {
        guard let req = pendingMountRequest else { return }
        dismissedKinds.insert(req.panel)
        pendingMountRequest = nil
    }

    // MARK: - Persistence

    private struct Snapshot: Codable {
        var leftPanel: MountablePanelKind?
        var rightPanel: MountablePanelKind?
        var tabs: [ShellTab]
        var activeTabID: UUID?
        var garmentExpanded: Bool
    }

    private func save() {
        let snap = Snapshot(leftPanel: leftPanel, rightPanel: rightPanel, tabs: tabs,
                            activeTabID: activeTabID, garmentExpanded: garmentExpanded)
        guard let data = try? JSONEncoder().encode(snap) else { return }
        UserDefaults.standard.set(data, forKey: Self.defaultsKey)
    }

    private func restore() {
        guard let data = UserDefaults.standard.data(forKey: Self.defaultsKey),
              let snap = try? JSONDecoder().decode(Snapshot.self, from: data) else { return }
        // **表に出さないと決めたパネルは、保存された配置からも外す。**
        // ``surfaced`` はレールと一覧を絞るだけなので、前回の起動でマウント
        // されていた基盤の内部パネル(群れの監視など)が、そのまま復元されて
        // 画面に居座った。実際にそうなった。
        leftPanel = snap.leftPanel.flatMap { $0.surfaced ? $0 : nil }
        rightPanel = snap.rightPanel.flatMap { $0.surfaced ? $0 : nil }
        tabs = snap.tabs
        activeTabID = snap.activeTabID
        garmentExpanded = snap.garmentExpanded
    }
}
