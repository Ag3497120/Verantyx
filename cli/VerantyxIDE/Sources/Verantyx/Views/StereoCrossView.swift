import SwiftUI

/// The stereo cross, drawn as the router it is.
///
/// Resting is the design: thin structure lines, no motion, no colour.
/// A call lights the hub and only the arms the ANSWER reported — an arm
/// with no evidence stays grey, because the engine's rule is that a
/// fact without a surface cue has no arm, and a picture that fills all
/// six would be inventing the very thing the gate exists to refuse.
///
/// Isometric on purpose: three axes read as a solid without a 3D scene
/// to keep running, so the structure can sit permanently in a header
/// without costing a frame budget. It expands only when asked.
struct StereoCrossView: View {
    @ObservedObject var route = VeraRouteState.shared
    /// Point-to-point size of one arm. The header uses a small one.
    var span: CGFloat = 34
    var showsLabels: Bool = false

    private var active: Bool { route.phase != .idle }

    private var accent: Color {
        switch route.phase {
        case .idle:      return Color.secondary.opacity(0.45)
        case .refused:   return Color(red: 0.90, green: 0.69, blue: 0.37)
        case .saving:    return Color(red: 0.34, green: 0.90, blue: 0.81)
        case .recalling: return Color(red: 0.34, green: 0.90, blue: 0.81)
        default:         return Color(red: 0.34, green: 0.90, blue: 0.81)
        }
    }

    /// Screen offsets for the six arms, isometric.
    private static let vectors: [VeraRouteState.CrossArm: CGPoint] = [
        .general:  CGPoint(x: 0,     y: -1),
        .instance: CGPoint(x: 0,     y: 1),
        .support:  CGPoint(x: -0.88, y: 0.48),
        .oppose:   CGPoint(x: 0.88,  y: -0.48),
        .cause:    CGPoint(x: -0.88, y: -0.48),
        .effect:   CGPoint(x: 0.88,  y: 0.48),
    ]

    var body: some View {
        ZStack {
            Canvas { ctx, size in
                let c = CGPoint(x: size.width / 2, y: size.height / 2)
                let r = min(size.width, size.height) / 2 - 2
                for (arm, v) in Self.vectors {
                    let end = CGPoint(x: c.x + v.x * r, y: c.y + v.y * r)
                    var path = Path()
                    path.move(to: c)
                    path.addLine(to: end)
                    let lit = active && route.arms.contains(arm)
                    ctx.stroke(
                        path,
                        with: .color(lit ? accent : Color.secondary.opacity(0.32)),
                        lineWidth: lit ? 1.8 : 1.0
                    )
                }
                let hub = CGRect(x: c.x - 3.2, y: c.y - 3.2, width: 6.4, height: 6.4)
                ctx.fill(Path(ellipseIn: hub),
                         with: .color(active ? accent : Color.secondary.opacity(0.5)))
            }
            .frame(width: span, height: span)
            .animation(.easeOut(duration: 0.45), value: route.pulse)
            .animation(.easeOut(duration: 0.45), value: route.phase)

            if active {
                Circle()
                    .stroke(accent.opacity(0.5), lineWidth: 1)
                    .frame(width: span * 0.92, height: span * 0.92)
                    .scaleEffect(1.0)
                    .opacity(0.0)
                    .modifier(PulseRing(trigger: route.pulse, tint: accent,
                                        size: span * 0.92))
            }
        }
        .accessibilityLabel("立体十字 — \(route.summary)")
        .help(helpText)
    }

    private var helpText: String {
        var lines = ["立体十字ルーティング — \(route.summary)"]
        if !route.arms.isEmpty {
            lines.append("腕: " + route.arms
                .sorted { $0.rawValue < $1.rawValue }
                .map { $0.label }.joined(separator: "・"))
        } else if active {
            lines.append("腕: 手掛かりなし(未タグ)")
        }
        if !route.origins.isEmpty {
            lines.append("出典: " + route.origins.prefix(3).joined(separator: ", "))
        }
        return lines.joined(separator: "\n")
    }
}

/// One ring per completed call. Not a loop: the cross must be still
/// when nothing is being asked.
private struct PulseRing: ViewModifier, Animatable {
    var trigger: Int
    var tint: Color
    var size: CGFloat
    @State private var run: CGFloat = 0

    func body(content: Content) -> some View {
        content.overlay(
            Circle()
                .stroke(tint.opacity(0.55 * (1 - run)), lineWidth: 1)
                .frame(width: size * (1 + run * 0.9),
                       height: size * (1 + run * 0.9))
                .allowsHitTesting(false)
        )
        .onChange(of: trigger) { _ in
            run = 0
            withAnimation(.easeOut(duration: 0.9)) { run = 1 }
        }
    }
}

/// The header strip: the cross, the live reading, and nothing else.
/// It is a band — it reports, it never decides.
struct VeraRouteBand: View {
    @ObservedObject var route = VeraRouteState.shared

    var body: some View {
        HStack(spacing: 8) {
            StereoCrossView(span: 26)
            Text(route.summary)
                .font(.system(size: 10.5, weight: .medium, design: .monospaced))
                .foregroundStyle(route.phase == .idle
                                 ? Color.secondary
                                 : Color.primary.opacity(0.85))
                .lineLimit(1)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 3)
        .background(
            RoundedRectangle(cornerRadius: 6)
                .fill(Color.primary.opacity(0.04))
        )
    }
}
