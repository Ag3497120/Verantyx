import SwiftUI

// MARK: - The status line inside the window
//
// The edge glow used to be drawn here, around the IDE window. That was wrong
// for the one case it existed to cover: the agent brings Safari forward, the
// IDE goes behind it, and a window-bound indicator disappears exactly when it
// is needed. The glow now lives on the display's rim — see ScreenEdgeGlow —
// above every app and visible whatever is in front.
//
// What stays here is the sentence, for when the IDE *is* on screen: a colour
// tells you something is happening, but not that clicking elsewhere will
// interrupt it. Both read AgentState and nothing else, so they cannot
// disagree with the rim or the menu-bar icon.
struct AgentPerimeterGlow: ViewModifier {

    @ObservedObject private var activity = AgentActivityCenter.shared

    func body(content: Content) -> some View {
        content
            .overlay(alignment: .top) {
                if let hint = activity.state.hint {
                    statusBadge(hint)
                        .padding(.top, 8)
                        .transition(.move(edge: .top).combined(with: .opacity))
                }
            }
            .animation(.easeInOut(duration: 0.25), value: activity.state)
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
}

extension View {
    /// Show the agent-state line when there is something to say.
    func agentPerimeterGlow() -> some View { modifier(AgentPerimeterGlow()) }
}
