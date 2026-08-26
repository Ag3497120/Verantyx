import SwiftUI

// MARK: - The mark: a cross with three axes, seen at an angle
//
// Every tool in this category has a mark that stands for nothing — a sparkle, a
// cube, an asterisk. This one can stand for something it actually has. JCross
// is the structure the project is built on, so the mark is that structure drawn
// honestly: three orthogonal axes meeting at one node.
//
// It is drawn as a projection rather than as a flat plus, because the thing
// being drawn is three-dimensional and a flat plus is a different object. The
// vertical axis is the axis of rotation and never foreshortens; the two
// horizontal axes sweep an ellipse as the structure turns, each arm shortening
// as it swings away from the viewer and lengthening as it comes back. Depth is
// carried by weight and brightness — the arm pointing away is thin and dim, the
// one pointing forward is thick and lit — so the rotation reads as rotation and
// not as a wobble.
//
// That gives one glyph three jobs. Still, it is an icon. Turning, it is a
// spinner that says work is happening. Struck once, it is a send.
struct JCrossGlyph: View {

    /// Rotation about the vertical axis, in turns. 0…1 is one full revolution.
    ///
    /// The resting value is deliberately NOT a symmetric one. At a quarter-ish
    /// phase both horizontal axes foreshorten equally, the four arms come out
    /// the same length, and the mark collapses into an asterisk — the exact
    /// generic glyph it exists to avoid. Just off-axis, one arm runs nearly
    /// full width while the other is barely open, and the asymmetry is what
    /// makes it read as a solid seen from three-quarters.
    var phase: Double = 0.035
    var tint: Color = Theme.sel
    /// How far the horizontal plane is tilted away from edge-on. 0 would draw a
    /// flat plus; a shallow angle keeps the arms readable while still reading
    /// as depth.
    var tilt: Double = 0.52
    var thickness: CGFloat = 1.7

    var body: some View {
        Canvas { context, size in
            let centre = CGPoint(x: size.width / 2, y: size.height / 2)
            let radius = min(size.width, size.height) / 2 - thickness
            let turn = phase * 2 * .pi
            let sinTilt = sin(tilt)
            let cosTilt = cos(tilt)

            // Four arms: two horizontal axes, two directions each.
            struct Arm { let end: CGPoint; let depth: Double }
            var arms: [Arm] = []
            for index in 0..<4 {
                let angle = turn + Double(index) * .pi / 2
                arms.append(Arm(
                    end: CGPoint(x: centre.x + cos(angle) * radius,
                                 y: centre.y + sin(angle) * radius * sinTilt),
                    // +1 toward the viewer, -1 away.
                    depth: sin(angle) * cosTilt))
            }

            // Farthest first, so the near arms cross over them the way solid
            // bars would.
            for arm in arms.sorted(by: { $0.depth < $1.depth }) {
                let nearness = (arm.depth + 1) / 2          // 0…1
                var path = Path()
                path.move(to: centre)
                path.addLine(to: arm.end)
                context.stroke(
                    path,
                    with: .color(tint.opacity(0.30 + 0.70 * nearness)),
                    style: StrokeStyle(lineWidth: thickness * (0.62 + 0.55 * nearness),
                                       lineCap: .round))
            }

            // The vertical axis is the axis of rotation: always full length,
            // always in front, so the mark keeps its identity at every phase.
            var upright = Path()
            upright.move(to: CGPoint(x: centre.x, y: centre.y - radius))
            upright.addLine(to: CGPoint(x: centre.x, y: centre.y + radius))
            context.stroke(upright, with: .color(tint),
                           style: StrokeStyle(lineWidth: thickness * 1.15, lineCap: .round))

            // The node. Everything in this structure meets at one point, and
            // the mark should say so.
            let node = thickness * 1.5
            context.fill(
                Path(ellipseIn: CGRect(x: centre.x - node / 2, y: centre.y - node / 2,
                                       width: node, height: node)),
                with: .color(tint))
        }
    }
}

// MARK: - Turning, it means work is happening

struct JCrossSpinner: View {
    var active: Bool
    var tint: Color = Theme.warn
    var size: CGFloat = 14

    @State private var phase: Double = 0.035

    var body: some View {
        JCrossGlyph(phase: phase, tint: active ? tint : Color.secondary.opacity(0.55))
            .frame(width: size, height: size)
            .onChange(of: active) { _, isActive in isActive ? start() : stop() }
            .onAppear { if active { start() } }
    }

    private func start() {
        // Rotation is the whole signal, so it turns at a readable pace rather
        // than a fast one: a mark spinning too quickly reads as an error state.
        withAnimation(.linear(duration: 3.2).repeatForever(autoreverses: false)) {
            phase = 1.035
        }
    }

    private func stop() {
        withAnimation(.easeOut(duration: 0.35)) { phase = 0.035 }
    }
}

// MARK: - Struck once, it means send

struct JCrossSendButton: View {
    let enabled: Bool
    let action: () -> Void

    @State private var strike = false
    @State private var hovering = false

    private var tint: Color {
        enabled ? Theme.sel
                : Theme.dim
    }

    var body: some View {
        Button {
            guard enabled else { return }
            // One turn on send. The mark completing a revolution is the
            // acknowledgement — nothing else needs to flash.
            withAnimation(.spring(response: 0.55, dampingFraction: 0.72)) { strike = true }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.55) { strike = false }
            action()
        } label: {
            JCrossGlyph(phase: strike ? 1.035 : 0.035, tint: tint, thickness: 1.9)
                .frame(width: 17, height: 17)
                .padding(6)
                .background(
                    Circle().fill(tint.opacity(hovering && enabled ? 0.16 : 0.0))
                )
        }
        .buttonStyle(.plain)
        .contentShape(Circle())
        .disabled(!enabled)
        .onHover { hovering = $0 }
        .help("Send")
    }
}
