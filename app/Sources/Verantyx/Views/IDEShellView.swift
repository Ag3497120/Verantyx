import SwiftUI

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
    @ObservedObject private var activity = AgentActivityCenter.shared

    // Per-file-tab editor buffer. One buffer, matching `app.selectedFile` —
    // see the note on `EditorBufferView` for why tabs here are a switchable
    // MRU over the existing single-document pipeline (Gatekeeper's vault
    // translation lives on that single path) rather than N independent
    // unsaved buffers.
    @State private var editorContent: String = ""
    @State private var editorLanguage: String = "swift"
    @State private var hasUnsavedChanges = false
    @State private var editorScrollCommand: EditorScrollCommand? = nil

    var body: some View {
        Group {
            if let tab = shell.activeTab, tab.kind == .garment, shell.garmentExpanded {
                garmentFullWidthLayout
            } else {
                normalLayout
            }
        }
        .onChange(of: app.selectedFile) { _, url in loadFileIntoEditor(url: url) }
        .onChange(of: app.showGatekeeperRawCode) { _, _ in loadFileIntoEditor(url: app.selectedFile) }
        .onAppear { loadFileIntoEditor(url: app.selectedFile) }
        // ── オファー: エージェントが動いている間、活動ログを申し出る ──
        // 強制はしない — 空いている側に一度だけ申し出て、断られたら
        // そのパネルがどこかに実際に開くまで黙る。
        .onChange(of: activity.state.glows) { _, glowing in
            guard glowing else { return }
            shell.requestMount(.agentActivity,
                               reasonEN: "An agent is running — show its activity?",
                               reasonJA: "エージェントが動いています — 活動を表示しますか？",
                               suggestedSide: shell.rightPanel == nil ? .right : .left)
        }
        // ── オファー: 立体十字が動いた（Vera-α の保存が来た）───────────
        .onChange(of: app.pendingVeraSave?.id) { _, newId in
            guard newId != nil else { return }
            shell.requestMount(.stereoCross,
                               reasonEN: "A save just landed in the graph — show it?",
                               reasonJA: "台帳への保存が届きました — 立体十字を表示しますか？",
                               suggestedSide: shell.leftPanel == nil ? .left : .right)
        }
    }

    // MARK: - Full-width garment layout

    private var garmentFullWidthLayout: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                Button {
                    shell.toggleGarmentExpanded()
                } label: {
                    Label(app.t("Collapse", "折りたたむ"), systemImage: "arrow.down.right.and.arrow.up.left")
                        .font(.system(size: 11, weight: .semibold))
                }
                .buttonStyle(.plain)
                .foregroundStyle(Theme.sel)
                Text(app.t("Garment — full width", "服飾 — 全幅"))
                    .font(.system(size: 12, weight: .bold))
                    .foregroundStyle(Theme.dim)
                Spacer()
            }
            .padding(.horizontal, 12).padding(.vertical, 8)
            .background(Theme.panel)
            Divider().opacity(0.3)

            AtelierView()
                .environmentObject(app)
                .frame(maxWidth: .infinity, maxHeight: .infinity)

            UnifiedComposerView()
                .environmentObject(app)
        }
        .background(Theme.panel2)
        .clipped()
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
                    activeTabContent
                    // **画面の下に固定された入力欄は置かない。** 以前は窓枠に
                    // 貼り付いていて、それを消すのがこの作り直しの一番はっきりした
                    // 要求だった。中央の列へ移しただけでは、どのタブの下にも同じ帯が
                    // 出るので、見た目は消えていない。
                    //
                    // 会話のための欄は会話に属する。文書(服・ファイル・パネル)には
                    // 属さない — Claude デスクトップと同じ扱い。空の画面では
                    // emptyState が同じ composer を主役として出すので、最小構成の
                    // ときはそれ自体がアプリになる。
                    if shell.activeTab?.kind == .chat {
                        UnifiedComposerView()
                            .environmentObject(app)
                    }
                }
            }
            // **中央は潰れてはいけない。** 側面が幅を奪って中央が0に近づくと、
            // 文字が1文字ずつ縦に折り返され、内容が枠の外へ描かれる。下限を
            // 置き、はみ出しを切る。
            .frame(minWidth: 360, maxWidth: .infinity, maxHeight: .infinity)
            .clipped()

            if let right = shell.rightPanel {
                Divider().opacity(0.2)
                sidePanelColumn(kind: right, side: .right)
            }
        }
        .background(Theme.panel2)
    }

    // MARK: - Left rail

    private var leftRail: some View {
        VStack(spacing: 4) {
            railButton(icon: "folder", help: app.t("Explorer", "エクスプローラー")) {
                if let ws = app.workspaceURL {
                    shell.openTab(.folder(path: ws.path))
                } else {
                    app.openWorkspace()
                }
            }
            railButton(icon: "tshirt", help: app.t("Garment", "服飾")) {
                shell.openTab(.garment)
            }
            railButton(icon: "bubble.left.and.bubble.right", help: app.t("Chat", "チャット")) {
                shell.openTab(.chat)
            }

            Divider().frame(width: 26).opacity(0.25).padding(.vertical, 3)

            ForEach(MountablePanelKind.surfacedCases) { kind in
                railButton(icon: kind.icon,
                          help: kind.title(japanese: AppLanguage.shared.isJapanese),
                          active: shell.leftPanel == kind) {
                    shell.toggleRail(.left, default: kind)
                }
            }

            Spacer()

            if !shell.isEmpty {
                railButton(icon: "xmark.square", help: app.t("Close all tabs", "すべてのタブを閉じる")) {
                    shell.closeAllTabs()
                }
            }
        }
        .padding(.vertical, 8)
        .frame(width: 44)
        .background(Theme.panel)
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
        case .garment:       return app.t("Garment", "服飾")
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
                    garmentTabContent
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

    private var garmentTabContent: some View {
        VStack(spacing: 0) {
            HStack {
                Spacer()
                Button {
                    shell.toggleGarmentExpanded()
                } label: {
                    Label(app.t("Expand", "全幅にする"), systemImage: "arrow.up.left.and.arrow.down.right")
                        .font(.system(size: 10.5, weight: .semibold))
                }
                .buttonStyle(.plain)
                .foregroundStyle(Theme.sel)
            }
            .padding(.horizontal, 10).padding(.vertical, 4)
            .background(Theme.panel2)
            AtelierView().environmentObject(app)
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

            HStack(spacing: 14) {
                emptyStateLink(app.t("Open a folder", "フォルダーを開く"), icon: "folder") {
                    app.openWorkspace()
                }
                emptyStateLink(app.t("Garment", "服飾"), icon: "tshirt") {
                    shell.openTab(.garment)
                }
                emptyStateLink(app.t("Chat", "チャット"), icon: "bubble.left.and.bubble.right") {
                    shell.openTab(.chat)
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
