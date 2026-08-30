import SwiftUI

/// Shared geometry for the beginner conversation surface and the main
/// macOS window. Keeping these values in one place is intentional: if the
/// transcript width and the window floor drift apart, AppKit can again offer
/// a size at which the conversation is clipped or rewrapped.
enum BeginnerChatLayout {
    static let canvasWidth: CGFloat = 920
    static let outerGutter: CGFloat = 24
    static let primarySidebarWidth: CGFloat = 210
    static let dividerWidth: CGFloat = 1
    static let minimumMainColumnWidth = canvasWidth + (outerGutter * 2)
    static let minimumWindowContentWidth = primarySidebarWidth
        + dividerWidth
        + minimumMainColumnWidth
    static let minimumWindowContentHeight: CGFloat = 600
}

// MARK: - IDEShellView
//
// The IDE shell: left rail, centre tabs, right panel — the Claude-desktop
// reference the owner had open while writing the brief. Three slots, two of
// them independently closable, the centre carrying tabs with an × each.
// Closing everything leaves the composer alone in a blank window, which is
// the legitimate empty state, not a bug to route around.
//
// One asymmetry, by name: the garment screen is the only tab allowed to
// cover the whole shell, the way Claude desktop lets only its document pane
// go full-width and never the rail or the side panel.
//
// All of the "what's open where" state lives in `app.shell`
// (ShellLayoutState) — this view reads and writes it, it does not own a
// second copy of it in local @State.
struct IDEShellView: View {
    @EnvironmentObject var app: AppState
    // Passed in explicitly rather than read from `AppState.shared` inside
    // `init()` — that static ref is only assigned in an `.onAppear` further
    // up the tree, AFTER this view's own `init()` already ran once, so
    // reading it here raced its own assignment and could silently observe
    // a disconnected, throwaway ShellLayoutState on first launch. The
    // caller already has a live `app` in ITS body, so it just hands over
    // `app.shell` directly.
    @ObservedObject var shell: ShellLayoutState

    // Per-file-tab editor buffer. One buffer, matching `app.selectedFile` —
    // see the note on `EditorBufferView` for why tabs here are a switchable
    // MRU over the existing single-document pipeline (Gatekeeper's vault
    // translation lives on that single path) rather than N independent
    // unsaved buffers.
    @State private var editorContent: String = ""
    @State private var editorLanguage: String = "swift"
    @State private var hasUnsavedChanges = false
    @State private var editorScrollCommand: EditorScrollCommand? = nil

    /// 名前を付け替えている最中の会話と、その入力欄の中身。
    /// 新規作成は名前を訊かずに作る(押した瞬間に始められる方が速い)ので、
    /// **名前は後から付ける** — その入口がこれ。
    @State private var renamingSessionId: UUID? = nil
    @State private var renameText: String = ""

    var body: some View {
        normalLayout
        .onChange(of: app.selectedFile) { _, url in loadFileIntoEditor(url: url) }
        .onChange(of: app.showGatekeeperRawCode) { _, _ in loadFileIntoEditor(url: app.selectedFile) }
        .onAppear { loadFileIntoEditor(url: app.selectedFile) }
        // ── オファー: 立体十字が動いた（Vera-α の保存が来た）───────────
        .onChange(of: app.pendingVeraSave?.id) { _, newId in
            guard newId != nil else { return }
            shell.requestMount(.stereoCross,
                               reasonEN: "A save just landed in the graph — show it?",
                               reasonJA: "台帳への保存が届きました — 立体十字を表示しますか？",
                               suggestedSide: shell.leftPanel == nil ? .left : .right)
        }
    }

    // MARK: - Normal 3-slot layout

    private var normalLayout: some View {
        HStack(spacing: 0) {
            leftRail
            Divider().opacity(0.2)

            if let left = shell.leftPanel {
                sidePanelColumn(kind: left, side: .left)
                Divider().opacity(0.2)
            }

            VStack(spacing: 0) {
                topBar
                // L2.5 の索引状態の帯はここから外した。あれは BitNet が
                // コードを地図にする進捗で、服を作る人には一行も関係がない。
                // 基盤としては動き続けるが、画面には出さない。
                Divider().opacity(0.25)
                if let req = shell.pendingMountRequest {
                    mountRequestBanner(req)
                    Divider().opacity(0.2)
                }
                if shell.isEmpty {
                    emptyState
                } else {
                    tabStrip
                    Divider().opacity(0.25)
                    if activeTabUsesChatFirstCanvas {
                        beginnerChatCanvas
                    } else {
                        activeTabContent
                    }
                }
            }
            // **中央は潰れてはいけない。** 側面が幅を奪って中央が0に近づくと、
            // 文字が1文字ずつ縦に折り返され、内容が枠の外へ描かれる。下限を
            // 置き、はみ出しを切る。
            .frame(minWidth: BeginnerChatLayout.minimumMainColumnWidth,
                   maxWidth: .infinity, maxHeight: .infinity)
            .clipped()

            if let right = shell.rightPanel {
                Divider().opacity(0.2)
                sidePanelColumn(kind: right, side: .right)
            }
        }
        .background(Theme.panel2)
    }

    /// Atelier has one surface, not separate beginner/expert screens. A
    /// garment project therefore opens the same Chat-first canvas as chat;
    /// 3D, pattern, structure, evidence and direct tools are disclosed by the
    /// contextual card inside that canvas.
    private var activeTabUsesChatFirstCanvas: Bool {
        guard let kind = shell.activeTab?.kind else { return false }
        if kind == .chat { return true }
        return app.veraEngineMode == .atelier && kind == .garment
    }

    /// Beginner chat has one fixed readable measure. The two flexible
    /// spacers receive the same proposal from HStack, so a larger window adds
    /// symmetric outer gutters instead of changing text wrapping. Transcript
    /// and composer live inside the same fixed canvas and therefore cannot
    /// acquire independent widths.
    private var beginnerChatCanvas: some View {
        HStack(spacing: 0) {
            Spacer(minLength: BeginnerChatLayout.outerGutter)

            VStack(spacing: 0) {
                AgentChatView(showsOwnComposer: false)
                    .environmentObject(app)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)

                UnifiedComposerView()
                    .environmentObject(app)
            }
            .frame(width: BeginnerChatLayout.canvasWidth)
            .frame(maxHeight: .infinity)
            .background(Theme.panel2)

            Spacer(minLength: BeginnerChatLayout.outerGutter)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Theme.panel2)
    }

    // MARK: - Left rail
    //
    // **服飾もチャットも「プロジェクト」— 名前・種類・作成日を持ち、
    // タブとして開く。** レールはそれを一覧で並べる、参照アプリと同じ形。
    // 上の小さなアイコン列だけが唯一モードで中身を変える場所 —
    // フォルダの位置にあるボタンは、LLM では既存のエクスプローラーの
    // まま、Atelier では「新しいプロジェクト」に差し替わる。同じ位置、
    // 同じ見た目、違う動詞、というのが owner の言葉どおりの実装。

    private var leftRail: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 4) {
                if app.veraEngineMode == .atelier {
                    // **同じ位置・同じ見た目、違う動詞。** LLM ではフォルダを
                    // 開く場所に、Atelier では新しいプロジェクトを作る場所を置く
                    // — コードの木を Atelier に持ち込まない、という owner の
                    // 明言のとおり。
                    railButton(icon: "folder.badge.plus",
                              help: app.t("New project", "新しいプロジェクト")) {
                        createProject()
                    }
                    railButton(icon: "tshirt", help: "Atelier",
                              active: shell.activeTab?.kind == .garment) {
                        shell.openTab(.garment)
                    }
                } else {
                    railButton(icon: "folder", help: app.t("Explorer", "エクスプローラー")) {
                        if let ws = app.workspaceURL {
                            shell.openTab(.folder(path: ws.path))
                        } else {
                            app.openWorkspace()
                        }
                    }
                }
                if app.veraEngineMode == .localLLM {
                    railButton(icon: "bubble.left.and.bubble.right", help: app.t("Chat", "チャット"),
                              active: shell.activeTab?.kind == .chat) {
                        shell.openTab(.chat)
                    }
                }

                ForEach(MountablePanelKind.surfacedCases) { kind in
                    railButton(icon: kind.icon,
                              help: kind.title(japanese: AppLanguage.shared.isJapanese),
                              active: shell.leftPanel == kind) {
                        shell.toggleRail(.left, default: kind)
                    }
                }

                Divider().frame(height: 26).opacity(0.25).padding(.horizontal, 3)

                // ── 設定: モードごとに別の画面を開く ────────────────────────
                // Atelier と LLM は別の設定を持つ(AppState.swift の
                // atelierDefaultUnit/atelierOperatorName vs SettingsView の
                // 既存設定) — このスイッチがその分岐そのもの。ボタン自体は
                // 1個、開く画面がモードで変わる。
                switch app.veraEngineMode {
                case .atelier:
                    railButton(icon: "gearshape", help: app.t("Atelier settings", "服飾の設定")) {
                        app.showAtelierSettingsRequested = true
                    }
                case .localLLM:
                    railButton(icon: "gearshape", help: app.t("Settings", "設定")) {
                        app.showSettingsRequested = true
                    }
                }

                Spacer(minLength: 0)
            }
            .padding(.horizontal, 6).padding(.vertical, 6)

            Divider().opacity(0.2)
            // **ScrollView に高さを決めさせない。** 中身が伸びるだけ伸びる
            // ScrollView を Spacer と並べると、Spacer ではなくこちらが
            // 中身の分だけ膨らみ、下のボタン列を窓の外へ押し出す —
            // house rule 2(clip and constrain)と同じ壊れ方。ここで
            // 明示的に残りの縦幅を割り当てる。
            projectsSection
                .frame(maxHeight: .infinity)

            Divider().opacity(0.2)
            VStack(spacing: 2) {
                // **選び直す道。** 一度選んだあとも消えない — 起動時の一回
                // きりでは「間違えて押した」を取り返せない。
                Button {
                    app.showModeChooser = true
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: "arrow.triangle.2.circlepath")
                            .font(.system(size: 11))
                        Text(app.t("Switch mode", "モードを選び直す"))
                            .font(.system(size: 10.5, weight: .medium))
                        Spacer(minLength: 0)
                    }
                    .foregroundStyle(Theme.faint)
                    .padding(.horizontal, 10).padding(.vertical, 5)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)

                if !shell.isEmpty {
                    Button {
                        shell.closeAllTabs()
                    } label: {
                        HStack(spacing: 6) {
                            Image(systemName: "xmark.square")
                                .font(.system(size: 11))
                            Text(app.t("Close all tabs", "すべてのタブを閉じる"))
                                .font(.system(size: 10.5, weight: .medium))
                            Spacer(minLength: 0)
                        }
                        .foregroundStyle(Theme.faint)
                        .padding(.horizontal, 10).padding(.vertical, 5)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.vertical, 4)
        }
        .frame(width: 210)
        .background(Theme.panel)
        .clipped()
    }

    // MARK: - Projects section
    //
    // 服飾も会話も同じ形(名前・種類・作成日)で並ぶ、同じ行ビュー。
    // データの実体は違う ── チャット側は `app.sessions`(本物の、
    // 各セッション独立の履歴)、服飾側は `app.garmentProjects` / `activeGarment`
    // (名前の一覧と、いま前面に出す名前 ── Vera 側の台帳自体は共有の
    // ままで、行を選んでも台帳が服ごとに分かれるわけではない。これは
    // この一覧が作ったものではなく、この一覧が初めて可視化した既存の姿)。

    private struct RailProject: Identifiable {
        enum Kind { case garment, chat }
        let id: String
        let name: String
        let kind: Kind
        let createdAt: Date
        let isActive: Bool
    }

    private var projectRows: [RailProject] {
        switch app.veraEngineMode {
        case .atelier:
            return app.garmentProjects.map { name in
                RailProject(id: name, name: name, kind: .garment,
                           createdAt: app.createdDate(forGarment: name),
                           isActive: name == app.activeGarment)
            }
        case .localLLM:
            return app.sessions.sessions
                .sorted { $0.createdAt > $1.createdAt }
                .map { s in
                    RailProject(id: s.id.uuidString,
                               name: s.title.isEmpty
                                     ? app.t("Untitled chat", "名前のないチャット")
                                     : s.title,
                               kind: .chat, createdAt: s.createdAt,
                               isActive: s.id == app.sessions.activeSessionId)
                }
        }
    }

    private var projectsSection: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 4) {
                Text(app.t("PROJECTS", "プロジェクト"))
                    .font(.system(size: 9.5, weight: .bold))
                    .tracking(0.5)
                    .foregroundStyle(Theme.faint)
                Spacer()
                Button {
                    createProject()
                } label: {
                    Image(systemName: "plus")
                        .font(.system(size: 10, weight: .bold))
                }
                .buttonStyle(.plain)
                .foregroundStyle(Theme.sel)
                .help(app.t("New project", "新しいプロジェクト"))
            }
            .padding(.horizontal, 10).padding(.top, 8).padding(.bottom, 4)

            if projectRows.isEmpty {
                Text(app.t("No projects yet", "まだプロジェクトがありません"))
                    .font(.system(size: 10.5))
                    .foregroundStyle(Theme.faint)
                    .padding(.horizontal, 10).padding(.vertical, 4)
            } else {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 1) {
                        ForEach(projectRows) { row in
                            projectRowButton(row)
                        }
                    }
                    .padding(.bottom, 4)
                }
            }
        }
        .background(renameSessionAlert)
    }

    private func projectRowButton(_ row: RailProject) -> some View {
        Button {
            openProject(row)
        } label: {
            HStack(spacing: 7) {
                Image(systemName: row.kind == .garment ? "tshirt" : "bubble.left.and.bubble.right")
                    .font(.system(size: 10))
                    .foregroundStyle(row.isActive ? Theme.sel : Theme.faint)
                    .frame(width: 14)
                VStack(alignment: .leading, spacing: 1) {
                    Text(row.name)
                        .font(.system(size: 11.5, weight: row.isActive ? .semibold : .regular))
                        .foregroundStyle(row.isActive ? Theme.fg : Theme.dim)
                        .lineLimit(1)
                    Text(Self.relativeDate(row.createdAt))
                        .font(.system(size: 9))
                        .foregroundStyle(Theme.faint)
                }
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 10).padding(.vertical, 5)
            .background(row.isActive ? Theme.sel.opacity(0.12) : .clear,
                       in: RoundedRectangle(cornerRadius: 5))
            .padding(.horizontal, 4)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .contextMenu {
            if row.kind == .chat, let id = UUID(uuidString: row.id) {
                Button(app.t("Rename…", "名前を変更…")) {
                    let current = app.sessions.sessions.first(where: { $0.id == id })
                    renameText = current?.title ?? ""
                    renamingSessionId = id
                }
            }
        }
    }

    /// 名前を付ける入口。**新規作成では訊かない** — 押した瞬間に会話を
    /// 始められる方が速く、名前は服を送れば特徴から付く。人が先に付けたい
    /// ときと、付いた名前を直したいときのために、ここを開けておく。
    private var renameSessionAlert: some View {
        EmptyView()
            .alert(app.t("Rename chat", "チャットの名前を変更"),
                  isPresented: Binding(
                      get: { renamingSessionId != nil },
                      set: { if !$0 { renamingSessionId = nil } }
                  )) {
                TextField(app.t("Name", "名前"), text: $renameText)
                Button(app.t("Cancel", "取消"), role: .cancel) {
                    renamingSessionId = nil
                }
                Button(app.t("Save", "保存")) {
                    if let id = renamingSessionId {
                        app.sessions.rename(id, to: renameText)
                    }
                    renamingSessionId = nil
                }
            } message: {
                Text(app.t("This name stays — it is not overwritten by the conversation or by the garment.",
                          "ここで付けた名前は残ります。会話や服の特徴で上書きされません。"))
            }
    }

    /// 一つの行を選ぶ ── 服飾なら前面の名前を替えて服飾タブを開く、
    /// 会話なら本物のセッションを復元してチャットタブを開く。
    private func openProject(_ row: RailProject) {
        switch row.kind {
        case .garment:
            app.activateGarmentProject(row.name)
            shell.openTab(.garment)
        case .chat:
            if let id = UUID(uuidString: row.id) {
                app.restoreSession(id)
            }
            shell.openTab(.chat)
        }
    }

    /// 「+」も、Atelier のフォルダ位置ボタンも、ここに集まる ── 同じ
    /// 行為の入口が二つあるだけで、行為そのものは一つ。
    private func createProject() {
        switch app.veraEngineMode {
        case .atelier:
            app.newGarmentProject()
            shell.openTab(.garment)
        case .localLLM:
            app.newChatSession()
            shell.openTab(.chat)
        }
    }

    private static let relativeDateFormatter: RelativeDateTimeFormatter = {
        let f = RelativeDateTimeFormatter()
        f.unitsStyle = .abbreviated
        return f
    }()

    private static func relativeDate(_ date: Date) -> String {
        relativeDateFormatter.localizedString(for: date, relativeTo: Date())
    }

    private func railButton(icon: String, help: String, active: Bool = false,
                            action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: icon)
                .font(.system(size: 15))
                .foregroundStyle(active
                    ? Theme.sel
                    : Color(red: 0.5, green: 0.5, blue: 0.6))
                .frame(width: 32, height: 30)
                .background(RoundedRectangle(cornerRadius: 6)
                    .fill(active ? Color.white.opacity(0.08) : .clear))
        }
        .buttonStyle(.plain)
        .help(help)
    }

    // MARK: - Top bar

    private var topBar: some View {
        HStack(spacing: 10) {
            // **コードの作業フォルダ名を出さない。** ここには
            // "Verantyx-Vera-alpha" のような、この道具を作っている側の
            // リポジトリ名が出ていた。使う人が見たいのは自分の服の名前。
            Text(shell.activeTab.map { tabTitle($0.kind) } ?? "photoloset")
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(Color(red: 0.8, green: 0.8, blue: 0.88))
                .lineLimit(1)
            Spacer()

            if !MountablePanelKind.surfacedCases.isEmpty {
                Menu {
                    ForEach(MountablePanelKind.surfacedCases) { kind in
                        Button(kind.title(japanese: AppLanguage.shared.isJapanese)) {
                            shell.mount(kind, in: shell.rightPanel == nil ? .right : .left)
                        }
                    }
                } label: {
                    Image(systemName: "plus.rectangle.on.rectangle")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(Color(red: 0.6, green: 0.6, blue: 0.72))
                }
                .buttonStyle(.plain)
                .menuStyle(.borderlessButton)
                .frame(width: 20)
                .help(app.t("Show a panel", "パネルを表示"))
            }
        }
        .padding(.horizontal, 12)
        .frame(height: 34)
        .background(Color(red: 0.11, green: 0.11, blue: 0.15))
    }

    // MARK: - Mount-request banner
    //
    // 申し出るだけ — 受け入れるかは人が決める。

    private func mountRequestBanner(_ req: PanelMountRequest) -> some View {
        HStack(spacing: 10) {
            Image(systemName: req.panel.icon)
                .font(.system(size: 11))
                .foregroundStyle(Theme.sel)
            Text(app.t(req.reasonEN, req.reasonJA))
                .font(.system(size: 11.5))
                .foregroundStyle(Color(red: 0.8, green: 0.8, blue: 0.88))
            Spacer()
            Button(app.t("Show", "表示")) { shell.acceptPendingRequest() }
                .buttonStyle(.plain)
                .font(.system(size: 11.5, weight: .semibold))
                .foregroundStyle(Color(red: 0.4, green: 0.85, blue: 0.55))
            Button {
                shell.dismissPendingRequest()
            } label: {
                Image(systemName: "xmark").font(.system(size: 10, weight: .semibold))
            }
            .buttonStyle(.plain)
            .foregroundStyle(Color(red: 0.55, green: 0.55, blue: 0.65))
        }
        .padding(.horizontal, 12).padding(.vertical, 6)
        .background(Color(red: 0.13, green: 0.16, blue: 0.20))
    }

    // MARK: - Side panel column (left or right)

    private func sidePanelColumn(kind: MountablePanelKind, side: ShellSide) -> some View {
        VStack(spacing: 0) {
            HStack(spacing: 6) {
                Image(systemName: kind.icon).font(.system(size: 10))
                Text(kind.title(japanese: AppLanguage.shared.isJapanese))
                    .font(.system(size: 11, weight: .semibold))
                Spacer()
                Button {
                    shell.unmount(side)
                } label: {
                    Image(systemName: "xmark").font(.system(size: 9, weight: .semibold))
                }
                .buttonStyle(.plain)
            }
            .foregroundStyle(Color(red: 0.7, green: 0.7, blue: 0.8))
            .padding(.horizontal, 10).padding(.vertical, 6)
            .background(Theme.panel2)
            Divider().opacity(0.25)

            PanelRegistry.view(for: kind)
                .environmentObject(app)
                // **パネルの内容に幅を決めさせない。** ここに幅の制約が無かった
                // ため、内寸の大きいパネル(群れの監視など)が列を丸ごと押し広げ、
                // 中央がほぼ0幅まで潰れた。潰れた列では文字が1文字ずつ縦に
                // 折り返され、画面全体が崩れて見える。実際に起きた壊れ方。
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .clipped()
        }
        .frame(width: 300)
        .clipped()
        .background(Color(red: 0.09, green: 0.09, blue: 0.12))
    }

    // MARK: - Tab strip

    private var tabStrip: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 4) {
                ForEach(shell.tabs) { tab in
                    tabChip(tab)
                }
            }
            .padding(.horizontal, 8).padding(.vertical, 4)
        }
        .frame(height: 30)
        .background(Theme.panel2)
    }

    private func tabChip(_ tab: ShellTab) -> some View {
        let isActive = shell.activeTabID == tab.id
        return HStack(spacing: 5) {
            Image(systemName: tabIcon(tab.kind)).font(.system(size: 9.5))
            Text(tabTitle(tab.kind))
                .font(.system(size: 11, weight: isActive ? .semibold : .regular))
                .lineLimit(1)
            Button { shell.closeTab(tab.id) } label: {
                Image(systemName: "xmark").font(.system(size: 8, weight: .semibold))
            }
            .buttonStyle(.plain)
        }
        .foregroundStyle(isActive
            ? Color.white
            : Color(red: 0.55, green: 0.55, blue: 0.65))
        .padding(.horizontal, 9).padding(.vertical, 4)
        .background(RoundedRectangle(cornerRadius: 5)
            .fill(isActive ? Color.white.opacity(0.10) : .clear))
        .contentShape(Rectangle())
        .onTapGesture {
            shell.activate(tab.id)
            // The editor buffer follows `app.selectedFile`, not the shell
            // tab — without this, clicking BACK to a file tab left the
            // buffer showing whatever the LAST-selected file was, which is
            // a tab that looks clickable and does nothing. File tabs are
            // the one kind where activating the tab must also re-point the
            // single shared buffer.
            if case .file(let p) = tab.kind {
                let url = URL(fileURLWithPath: p)
                if app.selectedFile != url { app.selectFile(url) }
            }
        }
    }

    private func tabIcon(_ kind: ShellTabKind) -> String {
        switch kind {
        case .file:    return "doc.text"
        case .folder:  return "folder"
        case .garment: return "tshirt"
        case .chat:    return "bubble.left.and.bubble.right"
        case .panel(let k): return k.icon
        case .terminal: return "terminal"
        case .diff:    return "arrow.left.arrow.right"
        case .artifact: return "shippingbox"
        case .memory:  return "brain"
        case .search:  return "magnifyingglass"
        case .aiPanel: return "note.text"
        }
    }

    private func tabTitle(_ kind: ShellTabKind) -> String {
        switch kind {
        case .file(let p):   return URL(fileURLWithPath: p).lastPathComponent
        case .folder(let p): return URL(fileURLWithPath: p).lastPathComponent
        case .garment:       return "Atelier"
        case .chat:          return app.t("Chat", "チャット")
        case .panel(let k):  return k.title(japanese: AppLanguage.shared.isJapanese)
        case .terminal:      return app.t("Terminal", "ターミナル")
        case .diff:          return "diff"
        case .artifact:      return app.stageArtifactTitle.isEmpty
                                  ? app.t("Artifact", "成果物") : app.stageArtifactTitle
        case .memory:        return app.t("Memory", "記憶")
        case .search:        return app.t("Search", "検索")
        case .aiPanel(let id): return app.aiPanels.first(where: { $0.id == id })?.title ?? "…"
        }
    }

    // MARK: - Active tab content

    @ViewBuilder
    private var activeTabContent: some View {
        if let tab = shell.activeTab {
            Group {
                switch tab.kind {
                case .file(let p):
                    EditorBufferView(url: URL(fileURLWithPath: p),
                                     content: $editorContent, language: $editorLanguage,
                                     hasUnsavedChanges: $hasUnsavedChanges,
                                     scrollCommand: $editorScrollCommand)
                case .folder:
                    FileTreeView().environmentObject(app)
                case .garment:
                    beginnerChatCanvas
                case .chat:
                    AgentChatView(showsOwnComposer: false).environmentObject(app)
                case .panel(let kind):
                    PanelRegistry.view(for: kind).environmentObject(app)
                case .terminal:
                    TerminalPanelView(terminal: app.terminal).environmentObject(app)
                case .diff:
                    ScrollView {
                        Text(app.stageDiff)
                            .font(.system(size: 11, design: .monospaced))
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(10)
                    }
                case .artifact:
                    ScrollView {
                        Text(app.stageArtifactText)
                            .font(.system(size: 12))
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(12)
                    }
                case .memory:
                    MemoryConsoleView()
                case .search:
                    GlobalSearchView().environmentObject(app)
                case .aiPanel(let id):
                    ScrollView {
                        Text(app.aiPanels.first(where: { $0.id == id })?.text ?? "")
                            .font(.system(size: 12))
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(12)
                    }
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    // MARK: - Empty state
    //
    // 何もかも閉じても、この画面は「壊れて」いない。書けば始まる。

    private var emptyState: some View {
        VStack(spacing: 20) {
            Spacer()
            UnifiedComposerView()
                .environmentObject(app)
                .frame(maxWidth: 640)

            // **空の画面が差し出すものもモードで変わる。** 服を作る人に
            // 「フォルダーを開く」を見せない ── コードの木を Atelier に
            // 持ち込まない、という owner の明言はこの画面にも及ぶ。
            HStack(spacing: 14) {
                if app.veraEngineMode == .atelier {
                    emptyStateLink(app.t("New project", "新しいプロジェクト"), icon: "folder.badge.plus") {
                        createProject()
                    }
                    emptyStateLink("Atelier", icon: "tshirt") {
                        shell.openTab(.garment)
                    }
                } else {
                    emptyStateLink(app.t("Open a folder", "フォルダーを開く"), icon: "folder") {
                        app.openWorkspace()
                    }
                    emptyStateLink(app.t("Chat", "チャット"), icon: "bubble.left.and.bubble.right") {
                        shell.openTab(.chat)
                    }
                }
            }
            Spacer()
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func emptyStateLink(_ title: String, icon: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 6) {
                Image(systemName: icon).font(.system(size: 11))
                Text(title).font(.system(size: 11.5, weight: .medium))
            }
            .foregroundStyle(Color(red: 0.6, green: 0.75, blue: 0.95))
            .padding(.horizontal, 12).padding(.vertical, 6)
            .background(RoundedRectangle(cornerRadius: 7).fill(Color.white.opacity(0.06)))
        }
        .buttonStyle(.plain)
    }

    // MARK: - Editor buffer loading
    //
    // One buffer, mirroring `app.selectedFile` — see the struct's own
    // header comment for why this is a switchable view over the existing
    // single-document pipeline rather than N independent unsaved buffers.

    private func loadFileIntoEditor(url: URL?) {
        guard let url = url else { return }
        let gatekeeper = GatekeeperModeState.shared
        if gatekeeper.isEnabled && !app.showGatekeeperRawCode {
            let relativePath: String
            if let wsPath = app.workspaceURL?.path, url.path.hasPrefix(wsPath + "/") {
                relativePath = String(url.path.dropFirst(wsPath.count + 1))
            } else {
                relativePath = url.lastPathComponent
            }
            Task {
                let vault = gatekeeper.vault
                let result = vault.read(relativePath: relativePath)
                await MainActor.run {
                    if let vaultResult = result {
                        let banner = """
                        ;;; 🛡️ GATEKEEPER MODE — JCross IR View
                        ;;; Schema: \(vaultResult.entry.schemaSessionID.prefix(12))
                        ;;; Nodes: \(vaultResult.entry.nodeCount) | Secrets redacted: \(vaultResult.entry.secretCount)
                        ;;; Source: \(relativePath)
                        ;;;
                        """
                        editorContent = banner + "\n" + vaultResult.jcrossContent
                        editorLanguage = "jcross"
                    } else {
                        // vault.read() が nil のとき、以前は「まだJCross変換
                        // されていない」旨の案内バナーを先頭に付けていた —
                        // shell 化のときに黙って生コードだけ出すようになって
                        // いた(なぜ生コードが出ているのか説明がなくなる
                        // 退行)ので、元の文面のまま復元する。
                        let raw = (try? String(contentsOf: url, encoding: .utf8)) ?? ""
                        let warning = app.t("""
                        ;;; ⚠️ GATEKEEPER MODE — This file is not yet converted to JCross
                        ;;; Please update the Vault via [Gatekeeper Settings] -> [Start Batch Conversion]
                        ;;; * The following is the raw source code. This view is temporary.
                        ;;;

                        """, """
                        ;;; ⚠️ GATEKEEPER MODE — このファイルはまだ JCross 変換されていません
                        ;;; [Gatekeeper 設定] → [一括変換を開始] でVaultを更新してください
                        ;;; ※ 以下は実コードです。このビューは一時的なものです
                        ;;;

                        """)
                        editorContent = warning + raw
                        editorLanguage = "jcross"
                    }
                    hasUnsavedChanges = false
                }
            }
        } else {
            do {
                editorContent = try String(contentsOf: url, encoding: .utf8)
                editorLanguage = Self.language(forExtension: url.pathExtension)
                hasUnsavedChanges = false
            } catch {
                editorContent = ""
            }
        }
    }

    static func language(forExtension ext: String) -> String {
        switch ext.lowercased() {
        case "swift":        return "swift"
        case "ts", "tsx":    return "typescript"
        case "js", "jsx":    return "javascript"
        case "py":           return "python"
        case "json":         return "json"
        case "md":           return "markdown"
        case "html", "htm":  return "html"
        case "css":          return "css"
        case "sh":           return "bash"
        case "yml", "yaml":  return "yaml"
        case "rs":           return "rust"
        case "go":           return "go"
        case "kt":           return "kotlin"
        default:             return ext.isEmpty ? "text" : ext
        }
    }
}

// MARK: - PanelRegistry
//
// One place mapping a `MountablePanelKind` to the view it mounts —
// mountable in the left/right slot AND openable as a centre tab, same
// registry either way.
@MainActor
enum PanelRegistry {
    @ViewBuilder
    static func view(for kind: MountablePanelKind) -> some View {
        switch kind {
        case .agentActivity:
            ScrollView {
                AgentActivityStreamView(activities: AgentActivityCenter.shared.log,
                                        japanese: AppLanguage.shared.isJapanese)
                    .padding(10)
            }
        case .stereoCross:
            StereoCrossGraphView()
        case .memoryLayer:
            MemoryLayerInspectorView()
        case .failureDomains:
            FailureDomainsView()
        case .swarmMonitor:
            SwarmMonitorView()
        case .git:
            GitPanelView()
        case .mcp:
            MCPView()
        }
    }
}

// MARK: - EditorBufferView
//
// Wraps the existing editable `CodeEditorView` (Highlightr, ⌘S save) with a
// small header. Switching file tabs re-reads from disk through
// `loadFileIntoEditor` the same way the single-document editor this
// replaced always did — there is one editor buffer, not one per tab, so an
// unsaved edit in a file you switch away from and back to survives (the
// state lives in the shell, not in this view), but a file closed and
// reopened re-reads from disk. Building N independent buffers would mean
// re-deriving the Gatekeeper vault-translation path per tab; not done here.
struct EditorBufferView: View {
    @EnvironmentObject var app: AppState
    let url: URL
    @Binding var content: String
    @Binding var language: String
    @Binding var hasUnsavedChanges: Bool
    @Binding var scrollCommand: EditorScrollCommand?

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                Text(url.lastPathComponent)
                    .font(.system(size: 11, weight: .medium, design: .monospaced))
                    .foregroundStyle(Theme.dim)
                if hasUnsavedChanges {
                    Circle().fill(Color(red: 0.9, green: 0.7, blue: 0.3)).frame(width: 5, height: 5)
                }
                Spacer()
                // shell 化で editorTabBar ごと消えた「Gatekeeper View」ピッカーの
                // 代わり。app.showGatekeeperRawCode を切り替える唯一の生きた
                // コントロールが無くなっていた(旧UIのレビューで指摘)ので、
                // ここに復元する。JCross IR / Source File の二択のみ。
                if GatekeeperModeState.shared.isEnabled {
                    Picker("Gatekeeper View", selection: $app.showGatekeeperRawCode) {
                        Text("JCross IR").tag(false)
                        Text("Source File").tag(true)
                    }
                    .pickerStyle(.segmented)
                    .labelsHidden()
                    .frame(width: 160)
                    .controlSize(.small)
                }
                if hasUnsavedChanges {
                    Button(action: save) {
                        Text(app.t("Save", "保存"))
                            .font(.system(size: 10.5, weight: .semibold))
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(Color(red: 0.4, green: 0.85, blue: 0.55))
                    .keyboardShortcut("s", modifiers: .command)
                }
            }
            .padding(.horizontal, 10).padding(.vertical, 5)
            .background(Color(red: 0.11, green: 0.11, blue: 0.15))
            Divider().opacity(0.25)

            // scrollCommand は前から CodeEditorView まで配線されていたが、
            // 発火させるボタンが shell 化のときに落ちていた(配線だけの
            // 死んだ状態は「押して何も起きない」より悪い一歩手前 —
            // ボタンごと消えていたので機能自体が失われていた)。
            // 旧 editorBody のオーバーレイをそのまま復元する。
            ZStack(alignment: .bottomTrailing) {
                CodeEditorView(
                    content: $content,
                    language: language,
                    isEditable: !(GatekeeperModeState.shared.isEnabled && !app.showGatekeeperRawCode),
                    onEdit: { hasUnsavedChanges = true },
                    scrollCommand: $scrollCommand
                )
                .frame(maxWidth: .infinity, maxHeight: .infinity)

                VStack(spacing: 6) {
                    Button {
                        scrollCommand = .top
                    } label: {
                        Image(systemName: "arrow.up.to.line")
                            .font(.system(size: 11, weight: .semibold))
                            .frame(width: 24, height: 24)
                    }
                    .help(app.t("Scroll to top", "先頭へスクロール"))
                    Button {
                        scrollCommand = .bottom
                    } label: {
                        Image(systemName: "arrow.down.to.line")
                            .font(.system(size: 11, weight: .semibold))
                            .frame(width: 24, height: 24)
                    }
                    .help(app.t("Scroll to bottom", "末尾へスクロール"))
                }
                .buttonStyle(.plain)
                .foregroundStyle(Theme.dim)
                .padding(6)
                .background(Color.black.opacity(0.5), in: RoundedRectangle(cornerRadius: 8))
                .padding(14)
            }
        }
    }

    private func save() {
        guard hasUnsavedChanges else { return }
        do {
            try content.write(to: url, atomically: true, encoding: .utf8)
            hasUnsavedChanges = false
            app.selectedFileContent = content
            ToastManager.shared.show(
                "Saved \(url.lastPathComponent)",
                icon: "checkmark.circle.fill",
                color: Color(red: 0.3, green: 0.9, blue: 0.5)
            )
        } catch {
            ToastManager.shared.show("Save failed: \(error.localizedDescription)",
                                     icon: "xmark.circle.fill", color: .red)
        }
    }
}
