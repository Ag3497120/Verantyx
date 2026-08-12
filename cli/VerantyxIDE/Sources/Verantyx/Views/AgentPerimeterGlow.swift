import SwiftUI

// MARK: - The window edge as an operating-rights indicator
//
// Not decoration. When the agent is driving the Mac, the thing the user most
// needs to know is that this is not their turn at the keyboard — and the
// composer glow cannot say that, because by then the window is behind Safari.
// The edge of the window says it from the corner of the eye, and the colour
// says which kind of work is happening.
//
// Everything here reads AgentState and nothing else. No `isGenerating`, no
// `isAgentControllingMouse` — one source, so the edge, the composer and the
// menu-bar icon cannot disagree.
struct AgentPerimeterGlow: ViewModifier {

    @ObservedObject private var activity = AgentActivityCenter.shared
    @State private var pulse = false

    func body(content: Content) -> some View {
        content
            .overlay {
                if activity.state.glows {
                    GeometryReader { _ in
                        RoundedRectangle(cornerRadius: 10, style: .continuous)
                            .strokeBorder(
                                activity.state.color.opacity(
                                    activity.state.pulses ? (pulse ? 0.95 : 0.35) : 0.85),
                                lineWidth: activity.state.pulses ? (pulse ? 3 : 2) : 2.5)
                            .shadow(color: activity.state.color.opacity(
                                activity.state.pulses ? (pulse ? 0.55 : 0.15) : 0.4),
                                    radius: activity.state.pulses ? (pulse ? 14 : 5) : 8)
                    }
                    .allowsHitTesting(false)      // never eats a click
                    .ignoresSafeArea()
                    .transition(.opacity)
                }
            }
            .overlay(alignment: .top) {
                if let hint = activity.state.hint {
                    statusBadge(hint)
                        .padding(.top, 8)
                        .transition(.move(edge: .top).combined(with: .opacity))
                }
            }
            .animation(.easeInOut(duration: 0.25), value: activity.state)
            .onChange(of: activity.state) { _, s in
                if s.pulses { startPulse() } else { stopPulse() }
            }
            .onAppear { if activity.state.pulses { startPulse() } }
    }

    /// A line of text only where one is needed — operating, waiting, error.
    /// The other states are legible from the colour alone and a banner on each
    /// of them would become furniture the user stops reading.
    private func statusBadge(_ hint: String) -> some View {
        HStack(spacing: 6) {
            Image(systemName: activity.state.icon).font(.system(size: 10, weight: .semibold))
            Text(activity.state.label).font(.system(size: 11, weight: .semibold))
            Text("—").font(.system(size: 11)).opacity(0.5)
            Text(hint).font(.system(size: 11)).lineLimit(1)
        }
        .foregroundStyle(activity.state.color)
        .padding(.horizontal, 12).padding(.vertical, 6)
        .background(.ultraThinMaterial, in: Capsule())
        .overlay(Capsule().strokeBorder(activity.state.color.opacity(0.35), lineWidth: 0.5))
        .allowsHitTesting(false)
    }

    private func startPulse() {
        withAnimation(.easeInOut(duration: 1.1).repeatForever(autoreverses: true)) {
            pulse = true
        }
    }

    private func stopPulse() {
        withAnimation(.easeOut(duration: 0.25)) { pulse = false }
    }
}

extension View {
    /// Light the window edge according to what the agent is doing.
    func agentPerimeterGlow() -> some View { modifier(AgentPerimeterGlow()) }
}
