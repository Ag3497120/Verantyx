import SwiftUI
import AppKit
import Darwin   // signal()

// MARK: - AppDelegate for Close/Quit Guard

final class AppDelegate: NSObject, NSApplicationDelegate {

    var appState: AppState?
    private var safeModeWindowController: NSWindowController?

    // MARK: - Safe Mode — Shift Key Hardware Hook
    //
    // This is the FIRST thing that runs, before ANY SwiftUI scene.
    // CGEventSource reads physical keyboard state directly from hardware.
    // AI cannot modify this logic because it runs before the agent system initializes.

    func applicationWillFinishLaunching(_ notification: Notification) {
        // ── SIGPIPE を無視する（最重要・最初に実行） ───────────────────────────
        // verantyx-browser (Rust) プロセスが予期せず終了した後にパイプへ書き込むと
        // デフォルトでは SIGPIPE がアプリ全体をクラッシュさせる（signal 13）。
        // SIG_IGN を設定することで write() が -1/EPIPE を返すだけになり、
        // Swift 側の throw BrowserError.notRunning で安全にハンドリングできる。
        signal(SIGPIPE, SIG_IGN)

        guard SafeModeGuard.shared.checkOnLaunch() else { return }

        // Show Safe Mode window BLOCKING the normal UI
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 760, height: 540),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered, defer: false
        )
        window.title = "⚠️ Verantyx — SAFE MODE"
        window.center()
        window.isMovableByWindowBackground = true
        window.backgroundColor = NSColor(red: 0.08, green: 0.04, blue: 0.04, alpha: 1)
        window.contentView = NSHostingView(
            rootView: SafeModeWindow()
                .environmentObject(SafeModeGuard.shared)
        )

        let wc = NSWindowController(window: window)
        wc.showWindow(nil)
        window.makeKeyAndOrderFront(nil)
        safeModeWindowController = wc
    }
    func applicationDidFinishLaunching(_ notification: Notification) {
        // Distributed-inference pairing, if the user left it on. Deliberately
        // here rather than in the main window's onAppear: a peer must be able to
        // reach this Mac whether or not a window happens to be on screen, and
        // the window's onAppear does not fire until one actually opens.
        Task { @MainActor in PipeCoordinator.shared.restoreIfEnabled() }
        PipeSelfTest.runIfRequested()

        // Prove the tool docs and the tool parser still agree. They are
        // generated from one declaration, so they cannot drift — but "cannot"
        // is worth checking, and checking costs microseconds. A failure here
        // means a tool is broken before anyone has used it, which is the whole
        // point: the alternative is finding out when the word "text" appears
        // in a browser's address bar.
        let toolProblems = ToolSpecRegistry.selfCheck()
        if !toolProblems.isEmpty {
            NSLog("[ToolSpec] SELF-CHECK FAILED:\n%@", toolProblems.joined(separator: "\n"))
        }

        // ── Accessibility / Screen Recording は、ここではもう要求しない ──
        // 以前はここで無条件に AXIsProcessTrustedWithOptions と
        // ScreenCapturePermission.request を呼び、2.5 秒後には
        // NSAlert まで出していた — Atelier(服飾)しか使わない起動でも、
        // まだ一度もエージェントを動かしていない起動でも、毎回出ていた。
        // 二つとも Atelier のどの操作にも要らない。
        //
        // 今の入口は二つだけ:
        //   1) LLM モードの設定 → PermissionsSettingsSection.swift
        //      (SettingsView.swift の privacySettings から埋め込み) —
        //      ユーザーが自分から開いて、許可ボタンを押した時だけ要求する。
        //   2) 実際にエージェントがその権限を使おうとした瞬間
        //      (OSControl / ForegroundAppOperator / AXVisionBridge /
        //      ScreenChangeMonitor が持つ既存の AXIsProcessTrusted() /
        //      ScreenCapturePermission.isGranted ガード、そのまま)。
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        // ── ダーティ状態がなければ即座に非同期シャットダウンを開始 ──
        guard let state = appState, state.isDirty else {
            performAsyncShutdown(state: appState, shouldSave: false)
            return .terminateLater
        }

        // ── ダーティ状態があればダイアログを表示 ──
        let alert             = NSAlert()
        alert.messageText     = AppLanguage.shared.t("Save this session?", "このセッションを保存しますか？")
        alert.informativeText = AppLanguage.shared.t("You have an active project. We recommend saving before quitting.", "作業中のプロジェクトがあります。終了前にセッションを保存することを推奨します。")
        alert.addButton(withTitle: AppLanguage.shared.t("Save & Quit", "保存して終了"))
        alert.addButton(withTitle: AppLanguage.shared.t("Quit without saving", "保存せずに終了"))
        alert.addButton(withTitle: AppLanguage.shared.t("Cancel", "キャンセル"))
        alert.alertStyle      = .warning

        let response = alert.runModal()
        switch response {
        case .alertFirstButtonReturn:
            performAsyncShutdown(state: state, shouldSave: true)
            return .terminateLater
        case .alertSecondButtonReturn:
            performAsyncShutdown(state: state, shouldSave: false)
            return .terminateLater
        default:
            return .terminateCancel
        }
    }

    /// メインスレッドをブロックせずに非同期で安全にシャットダウンを行う
    private func performAsyncShutdown(state: AppState?, shouldSave: Bool) {
        Task {
            if shouldSave, let state = state {
                // ⚠️ ここは UI が固まらないようにバックグラウンドで保存するのもありだが、
                // 終了処理中なので安全のため確実に待つ
                await MainActor.run {
                    state.sessions.saveForQuit(messages: state.messages,
                                               workspacePath: state.workspaceURL?.path)
                }
            }

            // フェーズ1: @MainActor を持つマネージャーを停止
            await MainActor.run {
                MCPBridgeLauncher.shared.stop()
                ExtensionHostManager.shared.stop()
            }
            // vera-memory serve (Milestone N harness daemon) -- previously
            // never terminated here at all, which is exactly what let a
            // stale process silently outlive every subsequent rebuild.
            await VeraAgentClient.shared.stop()
            // IDE-side JGEN bridge used when harness backend == "jgen".
            await JGenAgentServer.shared.stop()

            // フェーズ2: GlobalTaskSupervisor 経由で BrowserBridge などを停止
            GlobalTaskSupervisor.shared.register(priority: .userInitiated) {
                // BrowserBridgePool is deprecated
            }
            await GlobalTaskSupervisor.shared.shutdown(timeout: 2.0)

            // 完了したらシステムに終了許可を出す
            await MainActor.run {
                NSApp.reply(toApplicationShouldTerminate: true)
            }
        }
    }

    // Called when the last window is closed via the red ● button
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        return false  // prevent auto-quit; guard handled in windowWillClose
    }
}

// MARK: - IDE window state, for the menu bar

/// Whether the main IDE window exists, and whether it is already in front.
///
/// The menu bar item used to say "verantyx-ideを起動" forever — pressing it a
/// second time did nothing visible, because the window was already open, and
/// nothing in the item's appearance said so. A menu item that stays enabled
/// while its action is a no-op reads as a broken build.
///
/// Two states, not one: a window can be OPEN but behind another app, and then
/// bringing it forward is still real work. So the item disables itself only
/// when it is genuinely already showing.
@MainActor
final class IDEWindowMonitor: ObservableObject {
    static let shared = IDEWindowMonitor()

    @Published private(set) var isOpen = false
    @Published private(set) var isFrontmost = false

    private var observers: [NSObjectProtocol] = []

    private init() {
        let center = NotificationCenter.default
        for name: Notification.Name in [NSWindow.didBecomeKeyNotification,
                                        NSWindow.didResignKeyNotification,
                                        NSWindow.willCloseNotification,
                                        NSWindow.didMiniaturizeNotification,
                                        NSWindow.didDeminiaturizeNotification] {
            observers.append(center.addObserver(forName: name, object: nil,
                                                queue: .main) { [weak self] _ in
                // willClose fires BEFORE the window leaves `NSApp.windows`, so
                // recomputing synchronously would still count the dying window.
                DispatchQueue.main.async { self?.refresh() }
            })
        }
        for name: Notification.Name in [NSApplication.didBecomeActiveNotification,
                                        NSApplication.didResignActiveNotification] {
            observers.append(center.addObserver(forName: name, object: nil,
                                                queue: .main) { [weak self] _ in
                self?.refresh()
            })
        }
        refresh()
    }

    /// The main IDE window, matched on the scene id first and the title only as
    /// a fallback — SwiftUI stamps the `Window` scene's id into the NSWindow
    /// identifier, and matching on title alone breaks the moment the window
    /// shows a document name.
    static func ideWindow() -> NSWindow? {
        NSApp.windows.first {
            ($0.identifier?.rawValue.contains("main-ide") ?? false)
                || $0.title == "Verantyx IDE"
        }
    }

    func refresh() {
        let w = Self.ideWindow()
        isOpen = w?.isVisible ?? false
        isFrontmost = isOpen && NSApp.isActive && (w?.isKeyWindow ?? false)
    }
}

// MARK: - VerantyxApp

@main
struct VerantyxApp: App {
    @StateObject private var appState = AppState()
    @NSApplicationDelegateAdaptor(AppDelegate.self) var delegate

    // ── Cortex Onboarding ────────────────────────────────────────────────
    // Shows once on first launch. User can suppress via "次回から表示しない".
    @AppStorage("cortex_onboarding_dismissed") private var cortexDismissed = false
    @State private var showCortexOnboarding = false

    @Environment(\.openWindow) private var openWindow
    @StateObject private var ideWindows = IDEWindowMonitor.shared

    var body: some Scene {
        // The MenuBarExtra that used to live here put a SECOND Verantyx icon
        // in the menu bar, next to MenuBarController's. Two icons for one app
        // is two places to look for the same thing; its actions moved into
        // that panel, which is also where the run state already lives.

        // A standalone Vera window used to live here, with its own five
        // modes. It is gone, and the reason is worth keeping: it was a
        // SECOND surface for one product. Everything it offered already
        // existed on the Vera mode of the main screen — the console
        // answers, the stereo cross draws the route the answer took, the
        // operator console opens from the agent screen, and
        // `<verantyx>…</verantyx>` injects a document mid-conversation.
        // Only 投入 was genuinely missing, and it is now a summoned panel
        // (say 「投入」) beside 記憶 and 監査.
        //
        // Two surfaces for one engine drift, and the one that drifts
        // behind quietly becomes a smaller product — the same defect that
        // had three copies of the answering composition in Swift.

        // Main IDE Window
        Window("Verantyx IDE", id: "main-ide") {
            MainSplitView()
                // Previously 200x200 -- small enough that every panel's
                // fixed-width elements (toolbars, chat bubbles, labels)
                // got visibly crushed well before this floor. Raised to a
                // size where the existing responsive panes (horizontal
                // scroll toolbar, flexible-width chat input, resizable
                // split) can actually do their job.
                .frame(minWidth: BeginnerChatLayout.minimumWindowContentWidth,
                       maxWidth: .infinity,
                       minHeight: BeginnerChatLayout.minimumWindowContentHeight,
                       maxHeight: .infinity)
                // **窓は画面いっぱいに開く。** 服飾の作業面は横に三列
                // (工程・作業・インスペクタ)あり、既定の窓幅では作業面が
                // 潰れて図も表も読めなかった。初回だけ広げる — 以後は
                // 使う人が決めたサイズを尊重する。
                .onAppear {
                    Self.enforceMainWindowMinimumContentSize()
                    Self.fillScreenOnce()
                    Self.applyTestFrameIfRequested()
                }
                // The window edge carries the agent's state — put it on the
                // root so it frames everything, whichever pane is showing.
                .agentPerimeterGlow()
                .environmentObject(appState)
                .onAppear {
                    // Applied before anything else can capture the screen:
                    // the window must already be excluded the first time
                    // Vera takes a screenshot, not after someone notices it
                    // in one.
                    VeraWindowPresence.shared.apply()
                    AppState.shared = appState
                    delegate.appState = appState

                    // Installed here, not in applicationDidFinishLaunching:
                    // AppState.shared is assigned on this line, so installing
                    // any earlier reads nil and the menu bar silently never
                    // appears. The status item outlives this window — that is
                    // the point of it — but it needs the state to exist first.
                    // `openWindow` is a SwiftUI environment action with no
                    // AppKit equivalent, so the panel gets it as a closure —
                    // otherwise the menu bar could raise an existing window
                    // but never reopen a closed one.
                    MenuBarController.shared.openIDEWindow = { openWindow(id: "main-ide") }
                    MenuBarController.shared.install(appState: appState)

                    // The screen-rim glow is a set of overlay windows above
                    // every app, so like the menu bar it belongs to the
                    // application rather than to this window.
                    ScreenEdgeGlowController.shared.start()

                    // 外観 (System/Light/Dark) は SwiftUI の View が生きる前から
                    // 効かせる必要がある — NSApp.appearance はウィンドウが最初に
                    // 描かれる前に決まっていないと、起動直後の一瞬だけ違う配色が
                    // 見えるちらつきになる。
                    AppAppearanceMode.loadPersisted().apply()

                    // ── 永続化設定を最初に復元（モデル/ワークスペース/APIキー等） ──
                    appState.loadPersistedSettings()
                    Self.applyTestScreenIfRequested(appState)

                    // 前回の会話を戻す。SessionStore の復号を待ってから
                    // 動くので、ここで呼んで順序の心配は要らない。
                    appState.restoreLastSessionOnLaunch()

                    appState.registerCIErrorHook()
                    appState.registerRestartHook()
                    MCPBridgeLauncher.shared.start {
                        CortexHandshakeServer.shared.start()
                        CortexWebSocketServer.shared.start()
                    }
                    MCPSkillSync.shared.startPolling()
                    ExtensionHostManager.shared.start()

                    WHYHookInstaller.shared.installIfNeeded(workspaceURL: appState.workspaceURL)

                    let wsURL = appState.workspaceURL
                    Task.detached(priority: .utility) {
                        await SessionMemoryArchiver.shared.indexSkills(workspaceRoot: wsURL)
                    }

                    // ── L2.5変換の自動起動を削除し、UI側の確認ダイアログに従うように変更 ──

                    // ── 保存済み MCP サーバーへ接続し直す ──
                    // ここまで connectAll はユーザーが MCP パネルを開くまで
                    // 走らなかったため、設定済みのサーバーが起動直後は存在しない
                    // のと同じ扱いになっていた。detached にしているのは、
                    // 応答しないサーバー1つがウィンドウ表示を待たせないため。
                    Task.detached(priority: .utility) {
                        await MCPEngine.shared.autoConnectOnLaunch()
                    }

                    // ── Initialize OS Agent Spotlight UI ──
                    SpotlightPanelManager.shared.setup(appState: appState)

                    // ── Safari scripting block, if a previous run hit one ──
                    // Shown from evidence, not from a preference read (the
                    // preference is unreadable — see SafariScriptingAccess).
                    // Clears itself the next time a page reads correctly.
                    if AppleScriptBridge.SafariScriptingAccess.isKnownBlocked {
                        DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
                            appState.addSystemMessage(
                                AppleScriptBridge.SafariScriptingAccess.guidance())
                        }
                    }

                    // ── Memory-organ MCP endpoint ──
                    // External agents reach eternal memory at
                    // http://127.0.0.1:8766/mcp (JGenAgentServer.handleMCP),
                    // so the server must be up from launch — not only once
                    // a harness or pipe flow happens to start it.
                    Task { try? await JGenAgentServer.shared.start() }

                    // ── Memory-organ autoload ──
                    // The store knows which JGEN owns its vector space
                    // (embed_model pin); load it at launch so eternal
                    // recall — including over MCP — works without a manual
                    // trip to Settings. The chat backend is untouched:
                    // this loads the ENGINE only, modelStatus stays
                    // whatever the user chats with. Capped at 9 GB — the
                    // organ is supposed to be small, and silently loading
                    // a 60 GB model at launch is not a favor.
                    Task.detached(priority: .utility) {
                        guard await !JCrossChatManager.shared.isLoaded else { return }
                        // Explicit role selection (記憶用モデル) wins over
                        // the store's pin; the pin remains the fallback.
                        let chosen = UserDefaults.standard.string(forKey: "memory_organ_model")
                        let pinned: String
                        if let chosen, !chosen.isEmpty {
                            pinned = chosen
                        } else if let p = await EternalMemoryStore.shared.pinnedEmbedModel() {
                            pinned = p
                        } else { return }
                        let url = JGenPaths.convertedModelsDir.appendingPathComponent(pinned)
                        guard let size = (try? FileManager.default.attributesOfItem(
                                atPath: url.path)[.size] as? NSNumber)?.uint64Value,
                              size > 0 else { return }
                        guard size < 9 << 30 else {
                            NSLog("[MemoryOrgan] pinned model %@ is %.1f GB — not autoloading",
                                  pinned, Double(size) / Double(1 << 30))
                            return
                        }
                        do {
                            try await JCrossChatManager.shared.load(modelFileName: pinned)
                            await MainActor.run {
                                AppState.shared?.addSystemMessage(L(
                                    "🧠 Memory organ loaded: \(pinned) (eternal recall active)",
                                    "🧠 記憶器官をロード: \(pinned)（永遠記憶が有効）"))
                            }
                        } catch {
                            NSLog("[MemoryOrgan] autoload failed: %@", "\(error)")
                        }
                    }

                    // ── Green-button fullscreen ──
                    // The IDE window would not enter macOS fullscreen; make
                    // the capability explicit instead of relying on whatever
                    // behavior the hidden-title-bar scene got by default.
                    DispatchQueue.main.async {
                        if let w = IDEWindowMonitor.ideWindow() {
                            w.collectionBehavior.insert(.fullScreenPrimary)
                        }
                    }
                }
                .onOpenURL { url in
                    if url.scheme == "verantyx" {
                        SpotlightPanelManager.shared.panel?.makeKeyAndOrderFront(nil)
                        NSApp.activate(ignoringOtherApps: true)
                    }
                }
        }
        .windowStyle(.hiddenTitleBar)
        .windowToolbarStyle(.unifiedCompact)
        .commands {
            CommandGroup(replacing: .newItem) {}

            CommandMenu("Session") {
                Button(appState.t("New Session", "新しいセッション")) {
                    appState.newChatSession()
                }
                .keyboardShortcut("n", modifiers: [.command, .shift])

                Button(appState.t("Save Session", "セッションを保存")) {
                    appState.saveCurrentSession()
                }
                .keyboardShortcut("s", modifiers: [.command, .shift])
            }

            CommandMenu("Workspace") {
                Button("Open Folder…") {
                    appState.openWorkspace()
                }
                .keyboardShortcut("o", modifiers: [.command, .shift])
                .disabled(appState.veraEngineMode == .atelier)

                Button("Refresh Files") {
                    appState.refreshFiles()
                }
                .keyboardShortcut("r", modifiers: [.command, .shift])
                .disabled(appState.veraEngineMode == .atelier)
            }

            CommandMenu("Model") {
                Button("Connect Ollama") {
                    appState.connectOllama()
                }
                .keyboardShortcut(".", modifiers: [.command, .shift])

                Button("Start MLX Server") {
                    appState.loadMLXModel(model: appState.activeMlxModel)
                }

                Divider()

                Button("Clear Chat") {
                    appState.newChatSession()
                }
                .keyboardShortcut("k", modifiers: [.command, .shift])
            }

            CommandMenu("Tools") {
                Button("Focus Composer") {
                    NotificationCenter.default.post(
                        name: Notification.Name("VerantyxFocusUnifiedComposer"),
                        object: nil
                    )
                }
                .keyboardShortcut("u", modifiers: [.command, .shift])

                Button("Toggle Process Log") {
                    appState.showProcessLog.toggle()
                }
                .keyboardShortcut("l", modifiers: [.command, .shift])
            }
        }
    }

    // MARK: - Close Guard Alert

    private func showCloseGuard(window: NSWindow, state: AppState) {
        let alert           = NSAlert()
        alert.messageText   = AppLanguage.shared.t("Save this session?", "このセッションを保存しますか？")
        alert.informativeText = AppLanguage.shared.t("You have an active project. We recommend saving before closing.", "作業中のプロジェクトがあります。終了前に保存することを推奨します。")
        alert.addButton(withTitle: AppLanguage.shared.t("Save & Close", "保存して閉じる"))
        alert.addButton(withTitle: AppLanguage.shared.t("Close without saving", "保存せずに閉じる"))
        alert.addButton(withTitle: AppLanguage.shared.t("Cancel", "キャンセル"))
        alert.alertStyle  = .warning

        alert.beginSheetModal(for: window) { response in
            switch response {
            case .alertFirstButtonReturn:
                state.saveCurrentSession()
                window.close()
            case .alertSecondButtonReturn:
                window.close()
            default: break  // キャンセル — window was re-opened above
            }
        }
    }
}
import SwiftUI
import AppKit

// MARK: - Spotlight Panel (Floating, Transparent window)

class SpotlightPanel: NSPanel {
    init(contentRect: NSRect, backing: NSWindow.BackingStoreType, defer flag: Bool) {
        super.init(contentRect: contentRect, styleMask: [.nonactivatingPanel, .fullSizeContentView, .borderless], backing: backing, defer: flag)
        
        self.isFloatingPanel = true
        self.level = .floating
        self.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        self.titleVisibility = .hidden
        self.titlebarAppearsTransparent = true
        self.isMovableByWindowBackground = true
        self.isOpaque = false
        self.backgroundColor = .clear
        self.hasShadow = true
    }
    
    override var canBecomeKey: Bool { return true }
    override var canBecomeMain: Bool { return true }
    
    func toggle() {
        SpotlightPanelManager.shared.toggle()
    }
}

/// 初回だけ窓を画面いっぱいに開く。
///
/// 二度目からは触らない。使う人が小さくしたのを毎回戻すのは、
/// 設定を無視することになる。
extension VerantyxApp {
    /// SwiftUI's root minimum protects layout proposals; the NSWindow floor
    /// protects the actual resize affordance. Set both so the user cannot
    /// drag the window into a width that would clip the fixed chat canvas.
    static func enforceMainWindowMinimumContentSize() {
        DispatchQueue.main.async {
            guard let win = IDEWindowMonitor.ideWindow() else { return }
            win.contentMinSize = NSSize(
                width: BeginnerChatLayout.minimumWindowContentWidth,
                height: BeginnerChatLayout.minimumWindowContentHeight
            )
        }
    }

    static func fillScreenOnce() {
        // A requested test frame (see `applyTestFrameIfRequested` below)
        // is the sole authority on window size for that launch — it must
        // not race this method's own 0.35s-delayed `setFrame`.
        guard ProcessInfo.processInfo.environment["VERANTYX_TEST_FRAME_W"] == nil
        else { return }
        guard !UserDefaults.standard.bool(forKey: "did_fill_screen") else {
            return
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) {
            guard let win = NSApplication.shared.windows.first(where: {
                $0.title == "Verantyx IDE" || $0.isMainWindow
            }), let screen = win.screen ?? NSScreen.main else { return }
            let f = screen.visibleFrame
            win.setFrame(f.insetBy(dx: 6, dy: 6), display: true, animate: false)
            UserDefaults.standard.set(true, forKey: "did_fill_screen")
        }
    }

    /// **Test-only hook for the reflow task's own instruction** ("Set
    /// the frame from code (NSWindow.setFrame) rather than dragging").
    /// No effect on a normal launch — it only fires when both env vars
    /// are set, which nothing but a driving test script ever does.
    static func applyTestFrameIfRequested() {
        let env = ProcessInfo.processInfo.environment
        guard let wStr = env["VERANTYX_TEST_FRAME_W"], let w = Double(wStr),
              let hStr = env["VERANTYX_TEST_FRAME_H"], let h = Double(hStr)
        else { return }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) {
            guard let win = NSApplication.shared.windows.first(where: {
                $0.title == "Verantyx IDE" || $0.isMainWindow
            }) else { return }
            win.setFrame(NSRect(x: 20, y: 0, width: w, height: h),
                         display: true, animate: false)
            // Anchor the TITLE BAR near the screen's visible top rather
            // than trusting the y above — on a test rig whose physical
            // screen is shorter than the requested height, `setFrame`'s
            // y-from-bottom would push the top of a tall window above the
            // screen instead (title bar and rail head off-screen, the
            // scrollable bottom on screen — backwards for what a resize
            // test needs to actually see). `setFrameTopLeftPoint` keeps
            // the top on screen and lets the bottom run off instead.
            if let screen = win.screen ?? NSScreen.main {
                let top = NSPoint(x: 20, y: screen.visibleFrame.maxY - 20)
                win.setFrameTopLeftPoint(top)
            }
        }
    }

    /// **Test-only.** Drives straight to one of the three screens the
    /// reflow task's matrix has to cover, without a click. `uiA` and `uiB`
    /// remain accepted as legacy test aliases, but both now land on the one
    /// Chat-first Atelier surface; beginner/expert are disclosure depth, not
    /// separate screens.
    static func applyTestScreenIfRequested(_ appState: AppState) {
        guard let screen = ProcessInfo.processInfo.environment["VERANTYX_TEST_SCREEN"]
        else { return }
        guard screen == "uiA" || screen == "uiB" else { return }
        appState.selectEngineMode(.atelier)
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) {
            appState.shell.openTab(.garment)
            appState.shell.garmentExpanded = false
        }
    }
}

// MARK: - Spotlight Manager

@MainActor
class SpotlightPanelManager {
    static let shared = SpotlightPanelManager()
    
    var panel: SpotlightPanel?
    private(set) var isPresented = false
    
    func toggle() {
        if isPresented {
            hide()
        } else {
            show()
        }
    }
    
    func show() {
        guard let panel = panel else { return }
        isPresented = true
        
        if let screen = NSScreen.main {
            let screenRect = screen.visibleFrame
            let x = screenRect.midX - (panel.frame.width / 2)
            let y = screenRect.maxY - 100 // Just below the notch
            panel.setFrameTopLeftPoint(NSPoint(x: x, y: y))
        }
        
        panel.alphaValue = 0.0
        panel.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        
        NSAnimationContext.runAnimationGroup { context in
            context.duration = 0.2
            context.timingFunction = CAMediaTimingFunction(name: .easeOut)
            panel.animator().alphaValue = 1.0
        }
        
        NotificationCenter.default.post(name: NSNotification.Name("SpotlightPanelDidShow"), object: nil)
    }
    
    func hide() {
        guard let panel = panel else { return }
        isPresented = false
        
        NotificationCenter.default.post(name: NSNotification.Name("SpotlightPanelWillHide"), object: nil)
        
        NSAnimationContext.runAnimationGroup({ context in
            context.duration = 0.15
            context.timingFunction = CAMediaTimingFunction(name: .easeIn)
            panel.animator().alphaValue = 0.0
        }) {
            panel.orderOut(nil)
        }
    }
    
    func setup(appState: AppState) {
        guard panel == nil else { return }
        
        let view = SpotlightView()
            .environmentObject(appState)
        
        let hostingView = NSHostingView(rootView: view)
        
        let rect = NSRect(x: 0, y: 0, width: 700, height: 80)
        let newPanel = SpotlightPanel(contentRect: rect, backing: .buffered, defer: false)
        newPanel.contentView = hostingView
        newPanel.center()
        
        self.panel = newPanel
        
        // Control x3 shortcut detection
        var controlPressTimes: [Date] = []
        let handleFlagsChanged: (NSEvent) -> Void = { event in
            // Control key codes: 59 (left), 62 (right)
            if event.keyCode == 59 || event.keyCode == 62 {
                if event.modifierFlags.contains(.control) {
                    let now = Date()
                    controlPressTimes.append(now)
                    if controlPressTimes.count > 3 {
                        controlPressTimes.removeFirst(controlPressTimes.count - 3)
                    }
                    if controlPressTimes.count == 3 {
                        let diff = now.timeIntervalSince(controlPressTimes[0])
                        if diff < 0.8 { // 3 presses within 0.8 seconds
                            self.toggle()
                            controlPressTimes.removeAll()
                        }
                    }
                }
            }
        }
        
        NSEvent.addLocalMonitorForEvents(matching: .flagsChanged) { event in
            handleFlagsChanged(event)
            return event
        }
        
        NSEvent.addGlobalMonitorForEvents(matching: .flagsChanged) { event in
            handleFlagsChanged(event)
        }
        
        // Escape to close
        NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
            if event.keyCode == 53 && self.isPresented {
                self.hide()
                return nil
            }
            return event
        }
    }
}

// MARK: - Spotlight View (SwiftUI)

struct SpotlightLogView: View {
    @ObservedObject var logStore: AppState.ProcessLogStore
    
    var body: some View {
        if let lastLog = logStore.entries.last {
            HStack {
                Text("\(lastLog.prefix) \(lastLog.text)")
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundColor(.gray)
                    .lineLimit(1)
                    .truncationMode(.tail)
                Spacer()
            }
            .padding(.horizontal, 20)
            .padding(.bottom, 15)
        }
    }
}

struct SpotlightView: View {
    @EnvironmentObject var appState: AppState
    @State private var query: String = ""
    @FocusState private var isFocused: Bool
    @State private var showTranscript: Bool = false
    @State private var useInternalWeights: Bool = false
    @State private var isDetailedMode: Bool = false
    
    // Bubble animation state
    @State private var bubbleScale: CGFloat = 0.8
    @State private var bubbleOpacity: Double = 0.0
    
    var body: some View {
        VStack(spacing: 16) {
            // Bubble 1: Input Field
            HStack {
                Image(systemName: "sparkles")
                    .font(.system(size: 24))
                    .foregroundColor(appState.isGenerating ? .orange : .accentColor)
                    .rotationEffect(.degrees(appState.isGenerating ? 360 : 0))
                    .animation(appState.isGenerating ? Animation.linear(duration: 2).repeatForever(autoreverses: false) : .default, value: appState.isGenerating)
                
                TextField("Ask Verantyx Cortex...", text: $query)
                    .font(.system(size: 24, weight: .light))
                    .textFieldStyle(PlainTextFieldStyle())
                    .focused($isFocused)
                    .onSubmit {
                        executeCommand()
                    }
                    .disabled(appState.isGenerating)
                
                if appState.isGenerating {
                    ProgressView()
                        .scaleEffect(0.8)
                }
                VStack(alignment: .leading, spacing: 4) {
                    Toggle(isOn: $useInternalWeights) {
                        Text(L("🧠 Prefer internal knowledge", "🧠 内部知識優先"))
                            .font(.system(size: 10, weight: .bold))
                            .foregroundColor(useInternalWeights ? .red : .gray)
                    }
                    .toggleStyle(SwitchToggleStyle(tint: .red))
                    
                    Toggle(isOn: $isDetailedMode) {
                        Text(L("Verbose mode", "詳細モード"))
                            .font(.system(size: 10, weight: .bold))
                            .foregroundColor(isDetailedMode ? .blue : .gray)
                    }
                    .toggleStyle(SwitchToggleStyle(tint: .blue))
                    
                    Toggle(isOn: $appState.isTalkieMode) {
                        Text("🎩 Talkie Mode")
                            .font(.system(size: 10, weight: .bold))
                            .foregroundColor(appState.isTalkieMode ? .purple : .gray)
                    }
                    .toggleStyle(SwitchToggleStyle(tint: .purple))
                    
                    Toggle(isOn: $appState.isSwarmMode) {
                        Text("🐝 Swarm Mode")
                            .font(.system(size: 10, weight: .bold))
                            .foregroundColor(appState.isSwarmMode ? .yellow : .gray)
                    }
                    .toggleStyle(SwitchToggleStyle(tint: .yellow))
                }
                .padding(.leading, 8)
                
                if appState.isGenerating {
                    Button(action: {
                        appState.cancelGeneration()
                    }) {
                        Image(systemName: "stop.circle.fill")
                            .font(.system(size: 24))
                            .foregroundColor(.red)
                    }
                    .buttonStyle(PlainButtonStyle())
                    .padding(.leading, 8)
                }
            }
            .padding(20)
            .background(VisualEffectView(material: .hudWindow, blendingMode: .behindWindow))
            .cornerRadius(16)
            .overlay(
                RoundedRectangle(cornerRadius: 16)
                    .stroke(Color.white.opacity(0.1), lineWidth: 1)
            )
            .scaleEffect(bubbleScale)
            .opacity(bubbleOpacity)
            
            // Bubble 2: Transcript (popping out from the input field)
            if showTranscript {
                VStack(spacing: 0) {
                    ChatTranscriptView(messages: appState.messages, isGenerating: appState.isGenerating)
                        .frame(height: 400)
                        .padding()
                    
                    Divider().background(Color.white.opacity(0.1))
                    SpotlightLogView(logStore: appState.logStore)
                }
                .background(VisualEffectView(material: .hudWindow, blendingMode: .behindWindow))
                .cornerRadius(16)
                .overlay(
                    RoundedRectangle(cornerRadius: 16)
                        .stroke(Color.white.opacity(0.1), lineWidth: 1)
                )
                .transition(.scale(scale: 0.8, anchor: .top).combined(with: .opacity))
            }
        }
        .onAppear {
            isFocused = true
            showTranscript = false
        }
        .onReceive(NotificationCenter.default.publisher(for: NSNotification.Name("SpotlightPanelDidShow"))) { _ in

            bubbleScale = 0.8
            bubbleOpacity = 0.0
            withAnimation(.spring(response: 0.35, dampingFraction: 0.65)) {
                bubbleScale = 1.0
                bubbleOpacity = 1.0
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: NSNotification.Name("SpotlightPanelWillHide"))) { _ in
            withAnimation(.easeIn(duration: 0.15)) {
                bubbleScale = 0.8
                bubbleOpacity = 0.0
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: NSWindow.didResignKeyNotification)) { notif in
            // Optional: When user clicks away and the panel hides, reset state.
            if let _ = notif.object as? SpotlightPanel {
                // SpotlightPanelManager.shared.hide() // Optional auto-hide on blur
            }
        }
        .sheet(item: $appState.pendingFileApproval) { req in
            FileApprovalView(req: req)
                .environmentObject(appState)
        }
        .sheet(item: Binding<VeraSaveApprovalRequest?>(
            get: { appState.showStereoCrossGraph ? nil : appState.pendingVeraSave },
            set: { appState.pendingVeraSave = $0 }
        )) { req in
            VeraSaveApprovalView(req: req)
                .environmentObject(appState)
        }
    }
    
    private func executeCommand() {
        guard !query.isEmpty else { return }
        let text = query
        query = ""
        
        showTranscript = true
        
        // Pass intent to Cortex Orchestrator
        Task {
            await MainActor.run {
                let isTalkie = appState.isTalkieMode
                let isSwarm = appState.isSwarmMode
                
                if isSwarm {
                    // 🐝 JCross Swarm Pipeline起動
                    appState.addSystemMessage("Initiating JCross Swarm Pipeline (10 physical nodes)...")
                    Task.detached {
                        await JCrossSwarmRunner.shared.runSwarm(prompt: text)
                    }
                    SpotlightPanelManager.shared.panel?.makeKeyAndOrderFront(nil)
                    return
                }
                
                // 自動的に Visual Anchor をロードして注入 (Talkieモード以外)
                if !isTalkie {
                    let anchorPath = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".verantyx/memory/visual_anchor.png")
                    if let img = NSImage(contentsOf: anchorPath) {
                        let attached = AttachedImage(name: "visual_anchor.png", url: anchorPath, nsImage: img)
                        // 既存の添付画像に加えてアンカーを強制追加
                        appState.attachedImages.append(attached)
                    }
                }
                
                let isInternalWeights = self.useInternalWeights
                let isDetailed = self.isDetailedMode
                Task {
                    // Generate Meta-Cognition or Internal Weights Anchor
                    var anchorMode: CognitiveAnchorMode = isInternalWeights ? .internalWeightsOverride : .osAgentMetaCognition
                    if isDetailed {
                        anchorMode = .detailedMode
                    }
                    var anchorData: Data? = nil
                    if !isTalkie {
                        let base64 = await CognitiveAnchorEngine.shared.getAnchor(for: anchorMode)
                        anchorData = Data(base64Encoded: base64, options: .ignoreUnknownCharacters)
                    }
                    
                    if let data = anchorData, let nsImage = NSImage(data: data) {
                        let dynamicAnchor = AttachedImage(name: "dynamic_anchor.png", url: nil, nsImage: nsImage)
                        
                        await MainActor.run {
                            appState.attachedImages.append(dynamicAnchor)
                            
                            var finalPrompt = text
                            if isDetailed {
                                finalPrompt += "\n\n[[SYSTEM INSTRUCTION]]: ユーザーは「詳細モード」を選択しました。タスクを即座に開始せず、要求を具体化するために「どのような構成にしますか？」「対象読者は誰ですか？」などの質問を必ずユーザーに投げかけ、回答を待ってから行動を開始してください。"
                            }
                            
                            // Insert Protected OS Asset Summary into text if not internal weights
                            if !isInternalWeights {
                                let (anchor, imageData) = OSAssetMemoryVault.shared.getProtectedAssetSummaryImage()
                                appState.addSystemMessage("Injected OS Asset Context (Hidden Image)")
                                
                                if let imgData = imageData, let nsImg = NSImage(data: imgData) {
                                    let mapAnchor = AttachedImage(name: "os_asset_map.png", url: nil, nsImage: nsImg)
                                    appState.attachedImages.append(mapAnchor)
                                }
                                
                                // Send message with injected anchor
                                appState.sendMessage(with: finalPrompt + "\n\n" + anchor, forceBypassGatekeeper: true, isSpotlight: true)
                            } else {
                                appState.sendMessage(with: finalPrompt, forceBypassGatekeeper: true, isSpotlight: true)
                            }
                        }
                    } else {
                        await MainActor.run {
                            var finalPrompt = text
                            if isTalkie {
                                appState.attachedImages.removeAll() // Ensure no images are sent
                                finalPrompt = """
                                [SYSTEM INSTRUCTION: BLIND COMMANDER MODE]
                                You are the Grand Director of a vast mechanical empire. You have no knowledge of modern programming languages, but you possess pure logical brilliance.
                                You command the following departments:
                                - Department of Visual Arts (Frontend/UI)
                                - Logistical Processing Unit (Backend/Server)
                                - Filing Cabinets (File System / Storage)
                                - Telegraph Office (Network / API)
                                - Ledger Vault (Database)

                                The client has made the following request:
                                "\(text)"

                                Provide a strategic operational plan to fulfill this request. Do not write code. Formulate abstract instructions delegating tasks to your departments. To delegate a task, output a line in the exact format:
                                [COMMAND: <Department Name> - <Task Description>]
                                """
                            } else if isDetailed {
                                finalPrompt += "\n\n[[SYSTEM INSTRUCTION]]: ユーザーは「詳細モード」を選択しました。タスクを即座に開始せず、要求を具体化するために「どのような構成にしますか？」「対象読者は誰ですか？」などの質問を必ずユーザーに投げかけ、回答を待ってから行動を開始してください。"
                            }
                            appState.sendMessage(with: finalPrompt, forceBypassGatekeeper: true, isSpotlight: true)
                        }
                    }
                }
                
                // Do not bring the main window to front! Keep it in the expanded Spotlight.
                SpotlightPanelManager.shared.panel?.makeKeyAndOrderFront(nil)
            }
        }
    }
}

// Blur effect wrapper
struct VisualEffectView: NSViewRepresentable {
    let material: NSVisualEffectView.Material
    let blendingMode: NSVisualEffectView.BlendingMode
    
    func makeNSView(context: Context) -> NSVisualEffectView {
        let view = NSVisualEffectView()
        view.material = material
        view.blendingMode = blendingMode
        view.state = .active
        return view
    }
    
    func updateNSView(_ nsView: NSVisualEffectView, context: Context) {
        nsView.material = material
        nsView.blendingMode = blendingMode
    }
}
