import SwiftUI

/// Vera's palette: an instrument, not a sign.
///
/// Semantic only — a colour means a state, never a brand. Saturation is
/// held low and there is no glow anywhere: the reference is a scientific
/// display under room light, where a reading is legible because it is
/// placed well, not because it shines.
enum VeraInk {
    static let verified  = Theme.ok  // 証拠あり
    static let unsettled = Theme.warn  // 未確定・GAP
    static let contested = Theme.bad  // 係争
    static let working   = Theme.sel  // 検索中
    static let structure = Color.primary.opacity(0.22)                // 構造線
    static let quiet     = Color.primary.opacity(0.45)
}

/// The stereo cross, drawn as an instrument face.
///
/// The six directions are labelled because they are the engine's own —
/// support/oppose, cause/effect, general/instance — so the picture
/// teaches the structure instead of decorating it. An arm carries its
/// name at all times and its colour only when the answer evidenced it;
/// an arm with no cue stays grey, which is the engine's rule that a fact
/// without a surface cue has no arm, kept visible rather than smoothed
/// over.
///
/// Evidence orbits: each named source behind the shown facets is one
/// small mark on the ring. Count is information — four marks is four
/// sources — so they are placed, not animated.
struct StereoCrossView: View {
    @ObservedObject var route = VeraRouteState.shared
    var span: CGFloat = 34
    var showsLabels: Bool = false

    private var active: Bool { route.phase != .idle }

    private var tint: Color {
        if route.contested { return VeraInk.contested }
        switch route.phase {
        case .idle:      return VeraInk.quiet
        case .refused:   return VeraInk.unsettled
        case .routing,
             .saving,
             .recalling: return VeraInk.working
        case .answered:  return VeraInk.verified
        }
    }

    /// Screen offsets, isometric. The pairs sit opposite each other so
    /// the duality reads as a duality.
    private static let vectors: [(VeraRouteState.CrossArm, CGPoint)] = [
        (.general,  CGPoint(x: 0,     y: -1)),
        (.instance, CGPoint(x: 0,     y: 1)),
        (.support,  CGPoint(x: -0.88, y: 0.48)),
        (.oppose,   CGPoint(x: 0.88,  y: -0.48)),
        (.cause,    CGPoint(x: -0.88, y: -0.48)),
        (.effect,   CGPoint(x: 0.88,  y: 0.48)),
    ]

    // The body was one expression — a Canvas closure of CGPoint/CGRect
    // arithmetic plus a GeometryReader of the same — and the type checker
    // gave up on it. Locally that meant a slow build; on CI it meant
    // "unable to type-check this expression in reasonable time", which is
    // an ERROR, so every release build has been failing on it.
    //
    // Split into three, with the arithmetic given explicit types. The
    // drawing is a method rather than a closure because a method's
    // parameter types are declared instead of inferred, which is most of
    // what the checker was searching for.
    var body: some View {
        ZStack {
            Canvas { ctx, size in draw(ctx, size: size) }
            if showsLabels { labels }
        }
        .frame(width: span, height: span)
        .animation(.easeInOut(duration: 0.4), value: route.pulse)
        .animation(.easeInOut(duration: 0.4), value: route.phase)
        .accessibilityLabel("立体十字 — \(route.summary)")
    }

    // MARK: - The instrument itself

    private func draw(_ ctx: GraphicsContext, size: CGSize) {
        let c = CGPoint(x: size.width / 2, y: size.height / 2)
        let inset: CGFloat = showsLabels ? 26 : 3
        let r: CGFloat = min(size.width, size.height) / 2 - inset

        // evidence orbit — one mark per named source
        if showsLabels, !route.origins.isEmpty {
            let ring: CGFloat = r + 14
            var circle = Path()
            circle.addEllipse(in: CGRect(x: c.x - ring, y: c.y - ring,
                                         width: ring * 2, height: ring * 2))
            ctx.stroke(circle, with: .color(VeraInk.structure.opacity(0.5)),
                       lineWidth: 0.5)
            for i in route.origins.indices {
                let a: Double = (-Double.pi / 2) + (Double(i) / 8.0) * 2 * Double.pi
                let px: CGFloat = c.x + ring * CGFloat(cos(a))
                let py: CGFloat = c.y + ring * CGFloat(sin(a))
                let dot = CGRect(x: px - 2.2, y: py - 2.2, width: 4.4, height: 4.4)
                ctx.fill(Path(ellipseIn: dot), with: .color(VeraInk.verified))
            }
        }

        for (arm, v) in Self.vectors {
            let end = CGPoint(x: c.x + v.x * r, y: c.y + v.y * r)
            var path = Path()
            path.move(to: c)
            path.addLine(to: end)
            let lit: Bool = active && route.arms.contains(arm)
            ctx.stroke(path,
                       with: .color(lit ? tint : VeraInk.structure),
                       lineWidth: lit ? 1.6 : 0.9)
            if lit {
                let cap = CGRect(x: end.x - 2.6, y: end.y - 2.6,
                                 width: 5.2, height: 5.2)
                ctx.fill(Path(ellipseIn: cap), with: .color(tint))
            }
        }

        let hub = CGRect(x: c.x - 3.4, y: c.y - 3.4, width: 6.8, height: 6.8)
        ctx.fill(Path(ellipseIn: hub), with: .color(active ? tint : VeraInk.quiet))
    }

    private var labels: some View {
        GeometryReader { geo in
            let c = CGPoint(x: geo.size.width / 2, y: geo.size.height / 2)
            let r: CGFloat = min(geo.size.width, geo.size.height) / 2 - 26
            let reach: CGFloat = r + 24
            ForEach(Self.vectors, id: \.0) { arm, v in
                Text(arm.label)
                    .font(.system(size: 10, weight: .medium))
                    .monospacedDigit()
                    .foregroundStyle(active && route.arms.contains(arm)
                                     ? tint : Color.secondary)
                    .position(x: c.x + v.x * reach, y: c.y + v.y * reach)
            }
        }
    }
}

/// A compact reading for places that cannot hold the instrument.
struct VeraRouteBand: View {
    @ObservedObject var route = VeraRouteState.shared

    var body: some View {
        HStack(spacing: 7) {
            StereoCrossView(span: 22)
            Text(route.summary)
                .font(.system(size: 10.5, design: .monospaced))
                .foregroundStyle(.secondary)
                .lineLimit(1)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 3)
        .background(.quaternary.opacity(0.4), in: Capsule())
    }
}
