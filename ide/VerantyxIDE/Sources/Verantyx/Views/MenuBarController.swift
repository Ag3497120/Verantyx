import SwiftUI
import AppKit

// MARK: - The one surface the agent cannot bury
//
// Everything else in this app lives in a window, and a window loses. The
// moment the agent brings Safari or anything else to the front — which is the
// whole point of it driving the screen — the IDE goes behind it, and with it
// every control for the thing that is currently running.
//
// The macOS menu bar does not lose. A status item is drawn above every
// application window, always reachable, no matter what the agent is doing to
// the window order. So the controls you need *while a run is happening* live
// here: is it running, stop it, which model, is the phone relay up, and which
// input the relay is waiting on. Full settings still open in the window,
// because that is where there is room for them.
@MainActor
final class MenuBarController: NSObject {

    static let shared = MenuBarController()

    private var statusItem: NSStatusItem?
    private var popover: NSPopover?

    /// Supplied by the SwiftUI scene, which is the only place `openWindow`
    /// exists. Without it the panel could raise a window that is already open
    /// but never reopen one the user had closed.
    var openIDEWindow: (() -> Void)?

    func install(appState: AppState) {
        guard statusItem == nil else { return }

        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        if let button = item.button {
            button.image = NSImage(systemSymbolName: "circle.hexagongrid.fill",
                                   accessibilityDescription: "Verantyx")
            button.image?.isTemplate = true
            button.target = self
            button.action = #selector(toggle(_:))
        }
        statusItem = item

        let pop = NSPopover()
        pop.behavior = .transient
        pop.contentSize = NSSize(width: 320, height: 300)
        pop.contentViewController = NSHostingController(
            rootView: MenuBarPanel().environmentObject(appState)
        )
        popover = pop

        // The icon reflects run state, so a covered window still tells you
        // whether anything is happening.
        Task { @MainActor in
            for await _ in NotificationCenter.default.notifications(named: .veraRunStateChanged) {
                self.refreshIcon(AgentActivityCenter.shared.state)
            }
        }
    }

    /// The icon is the run indicator that survives the window being buried,
    /// so it carries the state rather than a running/not-running boolean.
    private func refreshIcon(_ state: AgentState) {
        guard let button = statusItem?.button else { return }
        button.image = NSImage(systemSymbolName: state == .idle
                               ? "circle.hexagongrid.fill" : state.icon,
                               accessibilityDescription: "Verantyx — \(state.label)")
        button.image?.isTemplate = true
        button.toolTip = "Verantyx — \(state.label)"
    }

    @objc private func toggle(_ sender: Any?) {
        guard let pop = popover, let button = statusItem?.button else { return }
        if pop.isShown {
            pop.performClose(sender)
        } else {
            pop.show(relativeTo: button.bounds, of: button, preferredEdge: .minY)
            pop.contentViewController?.view.window?.makeKey()
        }
    }

    func closePanel() { popover?.performClose(nil) }
}

extension Notification.Name {
    static let veraRunStateChanged = Notification.Name("veraRunStateChanged")
}

// MARK: - What drops down

struct MenuBarPanel: View {

    @EnvironmentObject var app: AppState
    @ObservedObject private var relay = ClipboardChatRelay.shared

    @ObservedObject private var activity = AgentActivityCenter.shared
    @ObservedObject private var ideWindows = IDEWindowMonitor.shared
    @State private var showMore = false
    private var running: Bool { activity.state.glows }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {

            // ── Run state ────────────────────────────────────────────────
            HStack(spacing: 8) {
                Image(systemName: activity.state.icon)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(running ? activity.state.color : Color.secondary)
                Text(activity.state.label)
                    .font(.system(size: 12, weight: .semibold))
                Spacer()
                if running {
                    Button(AppLanguage.shared.t("Stop", "停止")) {
                        app.cancelGeneration()
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                }
            }
            .padding(.horizontal, 14).padding(.top, 12).padding(.bottom, 10)

            Divider()

            // ── Model ────────────────────────────────────────────────────
            row(icon: "cpu",
                title: AppLanguage.shared.t("Model", "モデル"),
                value: app.activeModelName ?? "—")

            // ── Phone relay ──────────────────────────────────────────────
            row(icon: "iphone.gen3.radiowaves.left.and.right",
                title: AppLanguage.shared.t("Phone relay", "iPhoneリレー"),
                value: relay.isRunning
                    ? (relay.lastEvent.isEmpty ? "ON" : relay.lastEvent)
                    : "OFF")

            if relay.isRunning && !relay.sessionId.isEmpty {
                Text("[VX:\(relay.sessionId)#\(relay.expectedInputId)]")
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(.tertiary)
                    .padding(.horizontal, 14).padding(.bottom, 8)
            }

            HStack(spacing: 8) {
                Button(relay.isRunning
                       ? AppLanguage.shared.t("Stop relay", "リレー停止")
                       : AppLanguage.shared.t("Start relay", "リレー開始")) {
                    if relay.isRunning {
                        relay.stop()
                    } else {
                        relay.onUserMessage = { text in
                            AppState.shared?.sendMessage(with: text)
                        }
                        relay.start()
                    }
                }
                .buttonStyle(.bordered)
                .controlSize(.small)

                if relay.isRunning && relay.chunks.count > 1 {
                    Button(AppLanguage.shared.t("Next", "次へ")) { relay.advance() }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                        .disabled(relay.cursor + 1 >= relay.chunks.count)
                }
                Spacer()
            }
            .padding(.horizontal, 14).padding(.bottom, 10)

            Divider()

            // ── Open the IDE ─────────────────────────────────────────────
            action(icon: "macwindow",
                   title: ideWindows.isFrontmost
                        ? AppLanguage.shared.t("verantyx-ide is in front", "verantyx-ide は前面です")
                        : ideWindows.isOpen
                          ? AppLanguage.shared.t("Bring verantyx-ide to front", "verantyx-ide を前面に")
                          : AppLanguage.shared.t("Open verantyx-ide", "verantyx-ide を開く"),
                   disabled: ideWindows.isFrontmost) {
                openIDE()
            }

            action(icon: "slider.horizontal.3",
                   title: AppLanguage.shared.t("Settings in the IDE", "IDEで設定を開く")) {
                openIDE()
                app.fullSurface = .veraSettings
            }

            // ── More ─────────────────────────────────────────────────────
            // Everything below is occasionally useful and never urgent, so it
            // stays folded: a panel that opens during a run should show the
            // run, not a list of commands.
            Button {
                withAnimation(.easeInOut(duration: 0.15)) { showMore.toggle() }
            } label: {
                HStack(spacing: 8) {
                    Image(systemName: showMore ? "chevron.down" : "chevron.right")
                        .font(.system(size: 9, weight: .bold))
                    Text(AppLanguage.shared.t("More", "もっと表示"))
                        .font(.system(size: 12))
                    Spacer()
                }
                .contentShape(Rectangle())
                .foregroundStyle(.secondary)
            }
            .buttonStyle(.plain)
            .padding(.horizontal, 14).padding(.vertical, 8)

            if showMore {
                Divider()
                action(icon: "sparkle.magnifyingglass",
                       title: AppLanguage.shared.t("Spotlight (Control ×3)", "Spotlight（Control×3）")) {
                    SpotlightPanelManager.shared.panel?.toggle()
                }
                action(icon: "brain",
                       title: AppLanguage.shared.t("Vera-α audit", "Vera-α 監査画面")) {
                    openIDE()
                    app.fullSurface = .growth
                }
                action(icon: "network",
                       title: AppLanguage.shared.t("MCP / external ops", "MCP・外部運用")) {
                    openIDE()
                    app.fullSurface = .mcp
                }
                Divider()
                action(icon: "power",
                       title: AppLanguage.shared.t("Quit Verantyx", "Verantyx を終了")) {
                    NSApp.terminate(nil)
                }
            }
        }
        .frame(width: 320)
    }

    /// Raise the IDE, opening it first when the user had closed it.
    private func openIDE() {
        MenuBarController.shared.closePanel()
        if !ideWindows.isOpen { MenuBarController.shared.openIDEWindow?() }
        NSApp.activate(ignoringOtherApps: true)
        IDEWindowMonitor.ideWindow()?.makeKeyAndOrderFront(nil)
        DispatchQueue.main.async { ideWindows.refresh() }
    }

    private func action(icon: String, title: String, disabled: Bool = false,
                        _ run: @escaping () -> Void) -> some View {
        Button(action: run) {
            HStack(spacing: 8) {
                Image(systemName: icon).font(.system(size: 11)).frame(width: 16)
                Text(title).font(.system(size: 12))
                Spacer()
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(disabled)
        .foregroundStyle(disabled ? AnyShapeStyle(.tertiary) : AnyShapeStyle(.primary))
        .padding(.horizontal, 14).padding(.vertical, 8)
    }

    private func row(icon: String, title: String, value: String) -> some View {
        HStack(spacing: 8) {
            Image(systemName: icon).font(.system(size: 11)).foregroundStyle(.secondary)
                .frame(width: 16)
            Text(title).font(.system(size: 11)).foregroundStyle(.secondary)
            Spacer()
            Text(value)
                .font(.system(size: 11, weight: .medium))
                .lineLimit(1).truncationMode(.middle)
                .frame(maxWidth: 180, alignment: .trailing)
        }
        .padding(.horizontal, 14).padding(.vertical, 7)
    }
}
