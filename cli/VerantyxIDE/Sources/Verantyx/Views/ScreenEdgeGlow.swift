import SwiftUI
import AppKit

// MARK: - The display's rim, not the window's
//
// The first version lit the edge of the IDE window. That is invisible in the
// only situation it was built for: the agent brings Safari to the front, the
// IDE goes behind it, and the indicator goes with it. A window-bound signal
// loses for the same reason the window-bound controls did.
//
// So the glow is its own borderless overlay window, one per display, sitting
// above every application — including full-screen ones — and passing every
// click straight through. It is never focusable and never takes a keystroke.
// The screen itself reports who is holding it.
@MainActor
final class ScreenEdgeGlowController {

    static let shared = ScreenEdgeGlowController()

    private var windows: [NSWindow] = []
    private var observer: NSObjectProtocol?
    private var stateObserver: NSObjectProtocol?

    func start() {
        guard observer == nil else { return }

        // Displays come and go — a laptop lid closing, a monitor unplugged.
        // Rebuild rather than leave a glow on a screen that no longer exists.
        observer = NotificationCenter.default.addObserver(
            forName: NSApplication.didChangeScreenParametersNotification,
            object: nil, queue: .main
        ) { _ in
            MainActor.assumeIsolated { ScreenEdgeGlowController.shared.rebuild() }
        }

        stateObserver = NotificationCenter.default.addObserver(
            forName: .veraRunStateChanged, object: nil, queue: .main
        ) { _ in
            MainActor.assumeIsolated { ScreenEdgeGlowController.shared.sync() }
        }

        sync()
    }

    private func sync() {
        if AgentActivityCenter.shared.state.glows {
            if windows.isEmpty { rebuild() }
        } else {
            tearDown()
        }
    }

    private func rebuild() {
        tearDown()
        guard AgentActivityCenter.shared.state.glows else { return }

        for screen in NSScreen.screens {
            let window = GlowWindow(
                contentRect: screen.frame,
                styleMask: [.borderless],
                backing: .buffered,
                defer: false)

            window.isOpaque = false
            window.backgroundColor = .clear
            window.hasShadow = false
            // Above ordinary windows and above full-screen apps. The agent is
            // frequently driving something full-screen; an indicator that
            // hides behind it would be worse than none.
            window.level = .screenSaver
            window.collectionBehavior = [.canJoinAllSpaces, .stationary,
                                         .fullScreenAuxiliary, .ignoresCycle]
            // Never intercept the user OR the agent's own synthetic clicks:
            // this covers the whole screen, so anything less would break
            // every click the agent makes.
            window.ignoresMouseEvents = true
            window.isReleasedWhenClosed = false

            window.contentView = NSHostingView(rootView: ScreenEdgeGlowView())
            window.setFrame(screen.frame, display: true)
            window.orderFrontRegardless()
            windows.append(window)
        }
    }

    private func tearDown() {
        for w in windows { w.orderOut(nil) }
        windows.removeAll()
    }
}

/// Borderless windows can still become key by default, which would steal the
/// user's focus every time the agent started working.
private final class GlowWindow: NSWindow {
    override var canBecomeKey: Bool { false }
    override var canBecomeMain: Bool { false }
}

// MARK: - What is drawn

struct ScreenEdgeGlowView: View {

    @ObservedObject private var activity = AgentActivityCenter.shared
    @State private var pulse = false

    /// Modern Macs have rounded display corners; a square glow reads as a
    /// misaligned rectangle rather than the edge of the screen.
    private let cornerRadius: CGFloat = 14

    var body: some View {
        ZStack {
            // Layered strokes make the light look like it comes from off-screen
            // rather than like a drawn border: wide and faint outside, tight
            // and bright at the edge.
            RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                .strokeBorder(activity.state.color.opacity(intensity * 0.22), lineWidth: 26)
                .blur(radius: 12)

            RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                .strokeBorder(activity.state.color.opacity(intensity * 0.45), lineWidth: 10)
                .blur(radius: 4)

            RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                .strokeBorder(activity.state.color.opacity(intensity * 0.95), lineWidth: 3)
        }
        .allowsHitTesting(false)
        .ignoresSafeArea()
        .animation(.easeInOut(duration: 0.3), value: activity.state)
        .onAppear { if activity.state.pulses { startPulse() } }
        .onChange(of: activity.state) { _, s in
            if s.pulses { startPulse() } else { stopPulse() }
        }
    }

    /// Pulsing means working; steady means stopped and waiting on the user.
    /// Same rule the rest of the indicators follow.
    private var intensity: Double {
        guard activity.state.pulses else { return 0.85 }
        return pulse ? 1.0 : 0.45
    }

    private func startPulse() {
        withAnimation(.easeInOut(duration: 1.3).repeatForever(autoreverses: true)) {
            pulse = true
        }
    }

    private func stopPulse() {
        withAnimation(.easeOut(duration: 0.3)) { pulse = false }
    }
}
