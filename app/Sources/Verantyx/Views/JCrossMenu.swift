import SwiftUI

// MARK: - The plus menu, opened in the shape of the structure
//
// A plus button hiding the rarely-used actions is the standard move, and every
// implementation of it opens the same way: a rectangle fades in. That is a
// perfectly good menu and it says nothing about the product it belongs to.
//
// This one opens as the structure the project is built on. Two readings of the
// same object, because they say different things and it is not obvious which is
// right until you live with them:
//
//   接続   the node puts out arms and each one lands on an item. The structure
//          REACHES — it says these things are connected to the centre.
//
//   見取り図 the plane the arms lie in is raised into view, like a drawing being
//          tilted up off the table. The structure UNFOLDS — it says here is the
//          whole layout at once.
//
// Both are switchable and the choice is remembered, because an animation you
// see twenty times a day is not a thing to be decided once by whoever wrote it.

enum JCrossMenuStyle: String, CaseIterable, Identifiable {
    case connect
    case unfold

    var id: String { rawValue }

    func label(japanese: Bool) -> String {
        switch self {
        case .connect: return japanese ? "接続" : "Connect"
        case .unfold:  return japanese ? "見取り図" : "Unfold"
        }
    }
}

struct JCrossMenuItem: Identifiable {
    let id = UUID()
    let icon: String
    let title: String
    var shortcut: String? = nil
    let action: () -> Void
}

struct JCrossMenu: View {

    let items: [JCrossMenuItem]
    var japanese: Bool = true

    @AppStorage("jcross_menu_style") private var styleRaw = JCrossMenuStyle.connect.rawValue
    @State private var open = false
    /// 0…1. Drives both animations from one value so they stay in step with the
    /// button's own turn.
    @State private var reveal: Double = 0
    @State private var hovering = false

    private var style: JCrossMenuStyle {
        JCrossMenuStyle(rawValue: styleRaw) ?? .connect
    }

    private let rowHeight: CGFloat = 30
    private let panelWidth: CGFloat = 226

    var body: some View {
        JCrossGlyph(phase: 0.035 + reveal * 0.25,
                    tint: open ? Theme.sel
                               : Theme.dim,
                    thickness: 1.8)
            .frame(width: 15, height: 15)
            .padding(5)
            .background(Circle().fill(Color.white.opacity(hovering ? 0.08 : 0)))
            .contentShape(Circle())
            .onHover { hovering = $0 }
            .onTapGesture { toggle() }
            .overlay(alignment: .bottomLeading) { panel }
    }

    private func toggle() {
        open.toggle()
        withAnimation(open
            ? .spring(response: 0.44, dampingFraction: 0.78)
            : .easeInOut(duration: 0.18)) {
            reveal = open ? 1 : 0
        }
    }

    // MARK: The panel

    @ViewBuilder
    private var panel: some View {
        if open {
            ZStack(alignment: .bottomLeading) {
                if style == .connect { connectors }
                rows
            }
            .frame(width: panelWidth,
                   height: CGFloat(items.count) * rowHeight + 44,
                   alignment: .topLeading)
            // Sits above the button, since the composer lives at the bottom of
            // the window and a menu opening downward would leave the screen.
            .offset(x: 14, y: -CGFloat(items.count) * rowHeight - 46)
            .modifier(UnfoldEffect(active: style == .unfold, reveal: reveal))
            .opacity(reveal)
        }
    }

    private var rows: some View {
        VStack(alignment: .leading, spacing: 0) {
            ForEach(Array(items.enumerated()), id: \.element.id) { index, item in
                row(item, index: index)
            }
            Divider().overlay(Color.white.opacity(0.08)).padding(.vertical, 3)
            styleSwitch
        }
        .padding(.vertical, 5)
        .background(
            RoundedRectangle(cornerRadius: 11, style: .continuous)
                .fill(Theme.panel2)
                .shadow(color: .black.opacity(0.45), radius: 14, y: 6)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 11, style: .continuous)
                .strokeBorder(Color.white.opacity(0.10), lineWidth: 1)
        )
    }

    private func row(_ item: JCrossMenuItem, index: Int) -> some View {
        // Items arrive in order, each a little after the one before, so the eye
        // is led down the list rather than hit with all of it.
        let step = Double(index) * 0.09
        let local = max(0, min(1, (reveal - step) / max(0.001, 1 - step)))
        return Button {
            item.action()
            open = false
            withAnimation(.easeInOut(duration: 0.16)) { reveal = 0 }
        } label: {
            HStack(spacing: 9) {
                Image(systemName: item.icon)
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
                    .frame(width: 16)
                Text(item.title)
                    .font(.system(size: 12))
                    .foregroundStyle(.primary.opacity(0.92))
                Spacer(minLength: 6)
                if let shortcut = item.shortcut {
                    Text(shortcut)
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(.tertiary)
                }
            }
            .padding(.horizontal, 11)
            .frame(height: rowHeight)
            .contentShape(Rectangle())
        }
        .buttonStyle(JCrossRowStyle())
        .opacity(local)
        // In `接続` the item slides in along the arm that reached for it; in
        // `見取り図` the whole plane is already moving, so an extra slide per row
        // would be two motions arguing.
        .offset(x: style == .connect ? (1 - local) * -14 : 0)
    }

    /// A choice made twenty times a day belongs next to the thing it changes,
    /// not three screens away in Settings.
    private var styleSwitch: some View {
        HStack(spacing: 6) {
            Text(japanese ? "開き方" : "Opening")
                .font(.system(size: 10))
                .foregroundStyle(.tertiary)
            ForEach(JCrossMenuStyle.allCases) { candidate in
                Button {
                    styleRaw = candidate.rawValue
                } label: {
                    Text(candidate.label(japanese: japanese))
                        .font(.system(size: 10, weight: style == candidate ? .semibold : .regular))
                        .foregroundStyle(style == candidate
                                         ? Theme.sel
                                         : Color.secondary)
                        .padding(.horizontal, 7).padding(.vertical, 2)
                        .background(
                            Capsule().fill(Color.white.opacity(style == candidate ? 0.09 : 0)))
                }
                .buttonStyle(.plain)
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 11)
        .padding(.bottom, 2)
    }

    // MARK: 接続 — arms reaching from the node to each item

    private var connectors: some View {
        Canvas { context, size in
            let node = CGPoint(x: 2, y: size.height - 4)
            for index in items.indices {
                let step = Double(index) * 0.09
                let local = max(0, min(1, (reveal - step) / max(0.001, 1 - step)))
                guard local > 0.01 else { continue }
                let target = CGPoint(
                    x: 13,
                    y: 5 + CGFloat(index) * rowHeight + rowHeight / 2)
                // Drawn as the arm extends, so the line arrives with the row
                // rather than waiting for it.
                let tip = CGPoint(x: node.x + (target.x - node.x) * local,
                                  y: node.y + (target.y - node.y) * local)
                var path = Path()
                path.move(to: node)
                path.addLine(to: tip)
                context.stroke(
                    path,
                    with: .color(Theme.sel.opacity(0.30 * local)),
                    style: StrokeStyle(lineWidth: 1, lineCap: .round))
            }
            context.fill(
                Path(ellipseIn: CGRect(x: node.x - 2, y: node.y - 2, width: 4, height: 4)),
                with: .color(Theme.sel.opacity(0.55 * reveal)))
        }
        .allowsHitTesting(false)
    }
}

// MARK: - 見取り図 — the plane raised into view

private struct UnfoldEffect: ViewModifier {
    let active: Bool
    let reveal: Double

    func body(content: Content) -> some View {
        if active {
            content
                // Tipped up from its bottom edge, the way a drawing is lifted
                // off the table to be read. Anchored at the bottom because that
                // is where the node is.
                .rotation3DEffect(
                    .degrees((1 - reveal) * -74),
                    axis: (x: 1, y: 0, z: 0),
                    anchor: .bottom,
                    perspective: 0.55)
                .scaleEffect(x: 0.94 + 0.06 * reveal, y: 1, anchor: .bottomLeading)
        } else {
            content
        }
    }
}

private struct JCrossRowStyle: ButtonStyle {
    @State private var hovering = false
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .background(
                RoundedRectangle(cornerRadius: 6, style: .continuous)
                    .fill(Color.white.opacity(configuration.isPressed ? 0.10
                                              : (hovering ? 0.06 : 0)))
                    .padding(.horizontal, 5))
            .onHover { hovering = $0 }
    }
}
