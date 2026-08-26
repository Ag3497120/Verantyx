import SwiftUI

/// The Vera screen's main area: whatever `content` is for the current
/// mode, filling the pane. It used to also carry the stereo cross as a
/// translucent watermark behind that content (see git history) — that
/// was the leftover ghost readers kept seeing through the garment and
/// every other screen, so it was removed. The cross itself is not gone;
/// it is reachable as a real, clickable panel (VeraSummonedPanel's
/// `.cross` case) — via Settings › All Screens › Open, same as 記憶 and
/// 設定 (see SettingsView.open(); the older "say the word in chat" path
/// went with Bot mode, 2026-08-26).
struct VeraSovereignLayout<Content: View>: View {
    /// What fills the main area — Vera's console in Vera mode, the
    /// ordinary transcript in the LLM and dual-path modes. The frame is
    /// shared because Vera runs under all three; only the reply differs,
    /// and pretending an LLM's answer is a structured verdict would be
    /// the one dishonesty this screen exists to avoid.
    @ViewBuilder var content: () -> Content

    @EnvironmentObject var app: AppState

    var body: some View {
        // VeraStatusStrip (VERA-A / READY / NODES / EVIDENCE …) is off the
        // chat. It reported real numbers, which is why it earns a place —
        // but not a permanent band above every conversation. It is the 監査
        // panel's header now, summoned by 監査.
        layout
    }

    private var layout: some View {
        // The left column is gone. 記憶 was a real pane and it
        // moved into the summoned 記憶 panel — the ledger with its
        // 承認 buttons is the same object, just called by name.
        // 自由ウィンドウ was a mock: four tab labels and three lines
        // of code that never came from anywhere. A pane holding a
        // drawing of a feature is worse than no pane, in a product
        // whose whole claim is that what is on screen was measured.
        //
        // 立体十字 no longer rides here as a translucent watermark
        // behind the content — that ghost (原因/反論/一般/支持/結果
        // barely visible at 0.07–0.16 opacity) was the leftover the
        // owner was seeing through every screen. The instrument still
        // exists and still has a real, clickable home: the 十字 panel
        // (VeraSummonedPanel's `.cross` case), same as 記憶 and 設定 —
        // all three now open from Settings › All Screens › Open rather
        // than by being said in chat (that path was Bot mode's, removed
        // 2026-08-26 along with VeraBotTranscript).
        HStack(spacing: 10) {
            content()
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .padding(10)
    }

    // MARK: - 記憶



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




// MARK: - 記憶台帳, now summoned rather than parked

/// The left column's 記憶 pane, lifted out so it can appear inside the
/// summoned 記憶 panel. Same model, same 承認 action — moving a control
/// is only safe if it is the same control.
struct MemoryLedgerList: View {
    @StateObject private var ledger = MemoryLedgerModel()

    var body: some View {
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
            .padding(10)
        }
    }
}
