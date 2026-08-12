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
                self.refreshIcon(running: appState.isGenerating || appState.isAgentControllingMouse)
            }
        }
    }

    private func refreshIcon(running: Bool) {
        guard let button = statusItem?.button else { return }
        button.image = NSImage(
            systemSymbolName: running ? "circle.hexagongrid.circle.fill" : "circle.hexagongrid.fill",
            accessibilityDescription: "Verantyx")
        button.image?.isTemplate = true
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

    private var running: Bool { app.isGenerating || app.isAgentControllingMouse }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {

            // ── Run state ────────────────────────────────────────────────
            HStack(spacing: 8) {
                Circle()
                    .fill(running ? Color(red: 0.35, green: 0.85, blue: 1.0)
                                  : Color.secondary.opacity(0.4))
                    .frame(width: 8, height: 8)
                Text(running
                     ? AppLanguage.shared.t("Running", "実行中")
                     : AppLanguage.shared.t("Idle", "待機中"))
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

            // ── Into the window ──────────────────────────────────────────
            Button {
                MenuBarController.shared.closePanel()
                NSApp.activate(ignoringOtherApps: true)
                IDEWindowMonitor.ideWindow()?.makeKeyAndOrderFront(nil)
                app.fullSurface = .veraSettings
            } label: {
                HStack(spacing: 8) {
                    Image(systemName: "slider.horizontal.3").font(.system(size: 11))
                    Text(AppLanguage.shared.t("Open all settings", "すべての設定を開く"))
                        .font(.system(size: 12))
                    Spacer()
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .padding(.horizontal, 14).padding(.vertical, 10)
        }
        .frame(width: 320)
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
