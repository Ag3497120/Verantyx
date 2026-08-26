import SwiftUI

// MARK: - Human motion data, collected on purpose
//
// The puzzle used to appear mid-run as an overlay, because the agent had
// reached something it wanted a human trajectory for. That design assumes the
// IDE is on screen and a person is sitting in front of it — the assumption
// everything else removed. The agent takes the screen now, the window is
// deliberately not held in front, and the conversation may be on a phone. An
// overlay nobody is looking at is not a prompt; it is a stall.
//
// So collection lives here, where the user comes on purpose with time set
// aside. That turns the demonstrations into a dataset rather than an
// interruption — and a dataset is something whose size you can see, add to
// deliberately, and remove bad samples from.
//
// ── Why capture is continuous ─────────────────────────────────────────────
//
// Collecting one sample per sheet meant four clicks of overhead per drag, and
// the target is dozens of drags. Nobody reaches forty that way, which made the
// dataset permanently too small to switch the gate off — so the gate kept
// interrupting, which was the complaint that started this. Continuous capture
// re-arms straight after each solve; forty samples is a few minutes.
struct DemonstrationSettingsView: View {

    @EnvironmentObject var app: AppState
    @State private var stats: EternalMemoryStore.DemonstrationStats?
    @State private var recording = false
    @State private var sessionCount = 0
    @State private var lastAdded = false
    @State private var confirmClear = false

    private var human: Int { stats?.human ?? 0 }
    private var imitationTarget: Int { EternalMemoryStore.DemonstrationStats.enoughHuman }
    private var autonomyTarget: Int { EternalMemoryStore.DemonstrationStats.enoughForAutonomy }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {

            // ── Where the dataset stands ─────────────────────────────────
            HStack(spacing: 10) {
                Image(systemName: "hand.draw")
                    .font(.system(size: 15))
                    .foregroundStyle(autonomous ? Theme.ok
                                                : Theme.warn)
                VStack(alignment: .leading, spacing: 2) {
                    Text("人間の操作データ")
                        .font(.system(size: 13, weight: .semibold)).foregroundStyle(.white)
                    Text(statusLine)
                        .font(.system(size: 10)).foregroundStyle(.secondary)
                }
                Spacer()
                Text("\(human) / \(autonomyTarget)")
                    .font(.system(size: 12, weight: .bold, design: .monospaced))
                    .foregroundStyle(autonomous ? Theme.ok
                                                : Theme.warn)
            }

            ProgressView(value: Double(min(human, autonomyTarget)), total: Double(autonomyTarget))
                .tint(autonomous ? Theme.ok
                                 : Theme.warn)

            // Two thresholds do different jobs and conflating them hid the
            // second one entirely — the user could pass 8, see "sufficient",
            // and still be interrupted by the gate every five minutes.
            VStack(alignment: .leading, spacing: 3) {
                thresholdRow(reached: human >= imitationTarget,
                             at: imitationTarget,
                             text: "エージェントが人間の軌跡を真似る")
                thresholdRow(reached: autonomous,
                             at: autonomyTarget,
                             text: "実行中のパズル確認が出なくなる")
            }

            if let s = stats, !s.screens.isEmpty {
                // Trajectories only compare within one screen geometry, so the
                // count that matters is per resolution, not the total.
                Text("解像度ごと: " + s.screens.joined(separator: " / "))
                    .font(.system(size: 10, design: .monospaced)).foregroundStyle(.tertiary)
            }
            if let s = stats, s.agent > 0 {
                Text("エージェント自身の軌跡: \(s.agent) 件（人間データが無いときの代替）")
                    .font(.system(size: 10)).foregroundStyle(.tertiary)
            }

            Divider().opacity(0.2)

            // ── Add ──────────────────────────────────────────────────────
            HStack(spacing: 8) {
                Button {
                    sessionCount = 0
                    recording = true
                } label: {
                    Label("連続で記録する", systemImage: "record.circle")
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)

                if lastAdded {
                    Button {
                        Task {
                            await EternalMemoryStore.shared.deleteLastDemonstration()
                            await MainActor.run { lastAdded = false }
                            refresh()
                        }
                    } label: {
                        Label("直前を取り消す", systemImage: "arrow.uturn.backward")
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                }

                Spacer()

                Button(role: .destructive) {
                    confirmClear = true
                } label: {
                    Label("全消去", systemImage: "trash")
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .disabled(human == 0)
            }

            Text("""
            ノードを的まで運ぶたびに軌跡が1件保存され、すぐ次の的が出ます。普段どおりに動かしてください — \
            速すぎても遅すぎても、それがあなたの動きなら有効なデータです。的に届かなかった試行は記録されません。
            """)
                .font(.system(size: 10)).foregroundStyle(.tertiary).lineSpacing(2)

            Text("""
            なぜ必要か: エージェントがマウスを瞬間移動させると、画面を撮って読み取る側が \
            変化を追えず、誤検出や遅延が起きます。人間の軌跡があると、その揺らぎを真似た動きになります。\
            データが無いあいだはエージェント自身の軌跡で代用しますが、それは自分の癖を自分で強化することになります。
            """)
                .font(.system(size: 10)).foregroundStyle(.tertiary).lineSpacing(2)
        }
        .onAppear { refresh() }
        .sheet(isPresented: $recording) { captureSheet }
        .alert("人間の操作データを全て消しますか？", isPresented: $confirmClear) {
            Button("消去", role: .destructive) {
                Task {
                    await EternalMemoryStore.shared.deleteAllDemonstrations()
                    await MainActor.run { lastAdded = false }
                    refresh()
                }
            }
            Button("やめる", role: .cancel) {}
        } message: {
            Text("\(human) 件が削除されます。エージェント自身の軌跡は残ります（消すと代替が無くなるため）。")
        }
    }

    // MARK: - Capture session

    private var captureSheet: some View {
        VStack(spacing: 12) {
            HStack {
                Text("いつも通りにマウスを動かしてください")
                    .font(.system(size: 13, weight: .semibold))
                Spacer()
                Text("この回で \(sessionCount) 件 ・ 合計 \(human) / \(autonomyTarget)")
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(.secondary)
            }

            HumanProofPuzzleView(continuous: true) { entropy, _, _ in
                let pts = entropy.map { (x: Double($0.x), y: Double($0.y)) }
                let screen = NSScreen.main?.frame.size ?? .zero
                Task {
                    await EternalMemoryStore.shared.recordHumanDemonstration(
                        points: pts,
                        screenW: Double(screen.width), screenH: Double(screen.height))
                    await MainActor.run {
                        sessionCount += 1
                        lastAdded = true
                    }
                    refresh()
                }
            }
            .frame(width: 520, height: 380)

            HStack(spacing: 8) {
                // Undo stays reachable DURING the session. A bad sample is
                // noticed the moment it is drawn, and a session that can only
                // be corrected after it ends will not be corrected.
                Button {
                    Task {
                        await EternalMemoryStore.shared.deleteLastDemonstration()
                        await MainActor.run { sessionCount = max(0, sessionCount - 1) }
                        refresh()
                    }
                } label: {
                    Label("直前を取り消す", systemImage: "arrow.uturn.backward")
                }
                .buttonStyle(.bordered).controlSize(.small)
                .disabled(sessionCount == 0)

                Spacer()

                if autonomous {
                    Label("実行中の確認はもう出ません", systemImage: "checkmark.seal.fill")
                        .font(.system(size: 11))
                        .foregroundStyle(Theme.ok)
                }

                Button("終了") { recording = false }
                    .buttonStyle(.borderedProminent).controlSize(.small)
            }
        }
        .padding(20)
    }

    // MARK: - Bits

    private func thresholdRow(reached: Bool, at n: Int, text: String) -> some View {
        HStack(spacing: 6) {
            Image(systemName: reached ? "checkmark.circle.fill" : "circle")
                .font(.system(size: 9))
                .foregroundStyle(reached ? Theme.ok : .secondary)
            Text("\(n) 件 — \(text)")
                .font(.system(size: 10))
                .foregroundStyle(reached ? .secondary : .tertiary)
        }
    }

    private var autonomous: Bool { stats?.autonomous ?? false }

    private var statusLine: String {
        if autonomous { return "十分です。実行を中断してパズルを出すことはありません。" }
        if human >= imitationTarget {
            return "軌跡の模倣には足りています。あと \(autonomyTarget - human) 件で実行中の確認が不要になります。"
        }
        return "あと \(max(0, imitationTarget - human)) 件でエージェントが人間の軌跡を使い始めます。"
    }

    private func refresh() {
        Task {
            let s = await EternalMemoryStore.shared.demonstrationStats()
            await MainActor.run { stats = s }
        }
    }
}
