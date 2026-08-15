import SwiftUI

/// The Vera screen as the sketch drew it: memory and a free window down
/// the left, the stereo cross in the middle, the chat on the right.
///
/// The cross is the middle because it IS the middle — every answer and
/// every save takes that road (`VeraRouteState` publishes from the one
/// call site all doors pass through). Putting it beside the transcript
/// would make it an ornament next to the work; putting it between the
/// panes makes the picture and the route the same thing.
///
/// ## Narrowing is a reflow, not a shrink
///
/// The cross scales down with the window, and past a measured width it
/// stops being its own column: it folds into the left stack between 記憶
/// and 自由ウィンドウ as a compact band, and the chat takes the space it
/// left. Below that again the left stack goes away and the band rides
/// with the chat. Nothing is hidden without moving somewhere a reader
/// can still find it — a control that vanishes at a breakpoint is a
/// control the reader stops trusting.
struct VeraSovereignLayout<Content: View>: View {
    /// What fills the main area — Vera's console in Vera mode, the
    /// ordinary transcript in the LLM and dual-path modes. The frame is
    /// shared because Vera runs under all three; only the reply differs,
    /// and pretending an LLM's answer is a structured verdict would be
    /// the one dishonesty this screen exists to avoid.
    @ViewBuilder var content: () -> Content

    @EnvironmentObject var app: AppState
    @ObservedObject private var route = VeraRouteState.shared
    @StateObject private var ledger = MemoryLedgerModel()

    /// Where the cross lives at this width.
    private enum Fold { case column, leftStack, withChat }

    private func fold(_ w: CGFloat) -> Fold {
        // Measured against the real pane, not a guessed desktop: the
        // Vera pane is the right half of the window, so the column
        // layout has to arrive at a width the divider can actually
        // reach. 880 gives three readable columns; below 620 the left
        // stack itself stops fitting and the cross rides with the chat.
        if w >= 880 { return .column }
        if w >= 620 { return .leftStack }
        return .withChat
    }

    private func crossSpan(_ w: CGFloat) -> CGFloat {
        // Scales with the window, floored so the arms stay legible and
        // capped so it never becomes the loudest thing on screen.
        min(260, max(96, w * 0.19))
    }

    @StateObject private var status = VeraStatusModel()

    var body: some View {
        VStack(spacing: 0) {
            VeraStatusStrip(status: status)
            layout
        }
        .task { await status.load() }
    }

    private var layout: some View {
        GeometryReader { geo in
            let showsColumn = geo.size.width >= 620
            ZStack {
                HStack(spacing: 10) {
                    if showsColumn {
                        VStack(spacing: 10) {
                            memoryPane
                            freeWindowPane
                        }
                        .frame(width: max(220, min(300, geo.size.width * 0.24)))
                    }
                    content()
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
                .padding(10)

                // ── 立体十字, as a watermark ──────────────────────
                // A whole column for the instrument was the wrong trade:
                // the structure is the ground everything else sits on,
                // not a neighbour competing for width. It reads across
                // the panes at a weight you notice only when it moves,
                // takes no clicks, and brightens a little while a call
                // is out — so the route is still visible without the
                // screen spending a third of itself on it.
                StereoCrossView(
                    span: min(geo.size.width, geo.size.height) * 0.66,
                    showsLabels: true
                )
                .opacity(route.phase == .idle ? 0.07 : 0.16)
                .allowsHitTesting(false)
                .animation(.easeInOut(duration: 0.6), value: route.phase)
            }
            .animation(.easeInOut(duration: 0.28), value: showsColumn)
        }
    }

    // MARK: - 記憶

    private var memoryPane: some View {
        pane(title: "記憶", trailing: "\(ledger.rows.count)件") {
            ScrollView {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(ledger.rows) { row in
                        MemoryRowView(row: row) {
                            Task { await ledger.approve(row) }
                        }
                    }
                    if ledger.rows.isEmpty {
                        Text(ledger.loaded ? "まだ何も保持していません" : "読み込み中…")
                            .font(.system(size: 10))
                            .foregroundStyle(.tertiary)
                    }
                }
            }
        }
    }

    // MARK: - 自由ウィンドウ

    private var freeWindowPane: some View {
        pane(title: "自由ウィンドウ", trailing: nil) {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 5) {
                    ForEach(["エディタ", "3D", "台帳", "端末"], id: \.self) { name in
                        Text(name)
                            .font(.system(size: 10, design: .monospaced))
                            .padding(.horizontal, 6).padding(.vertical, 2)
                            .overlay(RoundedRectangle(cornerRadius: 3)
                                .strokeBorder(name == "エディタ"
                                              ? VeraInk.verified.opacity(0.8)
                                              : Color.white.opacity(0.12),
                                              lineWidth: 0.8))
                            .foregroundStyle(name == "エディタ"
                                             ? VeraInk.verified : Color.secondary)
                    }
                }
                Text("""
                def ask(q):
                    lang = route(q)
                    band = grain(q)
                """)
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(.tertiary)
                Spacer(minLength: 0)
            }
        }
    }

    // MARK: - shared chrome

    private func pane<C: View>(title: String, trailing: String?,
                               dashed: Bool = false,
                               @ViewBuilder content: () -> C) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(title)
                    .font(.system(size: 10, weight: .medium, design: .monospaced))
                    .tracking(1.6)
                    .foregroundStyle(.secondary)
                Spacer()
                if let trailing {
                    Text(trailing)
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(.tertiary)
                }
            }
            content()
            Spacer(minLength: 0)
        }
        .padding(12)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(
            RoundedRectangle(cornerRadius: 4)
                .fill(dashed ? Color.clear : Color.white.opacity(0.03))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 4)
                .strokeBorder(style: StrokeStyle(lineWidth: 0.8,
                                                 dash: dashed ? [4, 4] : []))
                .foregroundStyle(Color.white.opacity(0.10))
        )
    }
}

// MARK: - memory rows

struct MemoryLedgerRow: Identifiable, Equatable {
    let core: String
    let facets: [String]
    var state: String
    var id: String { core }
    var isProofed: Bool { state.contains("校正") }
}

/// Reads the engine's own ledger door. Nothing here is local state
/// pretending to be memory: the rows are what the store actually holds,
/// and an approval goes back through the same door.
@MainActor
final class MemoryLedgerModel: ObservableObject {
    @Published private(set) var rows: [MemoryLedgerRow] = []
    @Published private(set) var loaded = false

    func load() async {
        guard let obj = await VeraMemoryBridge.callDoor(
            "memory_ledger", ["limit": 12]),
              let raw = obj["rows"] as? [[String: Any]] else {
            loaded = true; return
        }
        rows = raw.compactMap { r in
            guard let core = r["core"] as? String else { return nil }
            return MemoryLedgerRow(
                core: core,
                facets: (r["facets"] as? [String]) ?? [],
                state: (r["state"] as? String) ?? "証言")
        }
        loaded = true
    }

    /// The user's approval: the row is marked, and from then on an
    /// agent reading it sees the ユーザーの校正 label rather than raw
    /// testimony.
    func approve(_ row: MemoryLedgerRow) async {
        _ = await VeraMemoryBridge.callDoor(
            "memory_review", ["core": row.core, "state": "ユーザーの校正"])
        if let i = rows.firstIndex(where: { $0.id == row.id }) {
            rows[i].state = "ユーザーの校正"
        }
    }
}

private struct MemoryRowView: View {
    let row: MemoryLedgerRow
    let approve: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 5) {
                Text(row.state)
                    .font(.system(size: 9, design: .monospaced))
                    .padding(.horizontal, 4).padding(.vertical, 1)
                    .overlay(RoundedRectangle(cornerRadius: 2)
                        .strokeBorder(tint.opacity(0.8), lineWidth: 0.8))
                    .foregroundStyle(tint)
                Text(row.core)
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(row.isProofed ? VeraInk.verified : .primary)
                    .lineLimit(1)
                Spacer(minLength: 0)
                if !row.isProofed {
                    Button(action: approve) {
                        Text("承認")
                            .font(.system(size: 9, design: .monospaced))
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(VeraInk.verified)
                    .help("この記憶に「ユーザーの校正」ラベルを付け、エージェントに渡す")
                }
            }
            if !row.facets.isEmpty {
                Text(row.facets.prefix(4).joined(separator: " · "))
                    .font(.system(size: 9.5))
                    .foregroundStyle(.tertiary)
                    .lineLimit(2)
            }
        }
        .padding(.horizontal, 7).padding(.vertical, 5)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.white.opacity(row.isProofed ? 0.05 : 0.025))
        .overlay(Rectangle().frame(width: 2).foregroundStyle(tint),
                 alignment: .leading)
    }

    private var tint: Color {
        row.isProofed ? VeraInk.verified : Color.secondary.opacity(0.6)
    }
}


