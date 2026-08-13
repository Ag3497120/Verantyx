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
struct DemonstrationSettingsView: View {

    @EnvironmentObject var app: AppState
    @State private var stats: EternalMemoryStore.DemonstrationStats?
    @State private var recording = false
    @State private var lastAdded = false
    @State private var confirmClear = false

    private var human: Int { stats?.human ?? 0 }
    private var target: Int { EternalMemoryStore.DemonstrationStats.enoughHuman }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {

            // ── Where the dataset stands ─────────────────────────────────
            HStack(spacing: 10) {
                Image(systemName: "hand.draw")
                    .font(.system(size: 15))
                    .foregroundStyle(sufficient ? Color(red: 0.3, green: 0.9, blue: 0.5)
                                                : Color(red: 1.0, green: 0.75, blue: 0.2))
                VStack(alignment: .leading, spacing: 2) {
                    Text("人間の操作データ")
                        .font(.system(size: 13, weight: .semibold)).foregroundStyle(.white)
                    Text(sufficient
                         ? "十分に集まっています。エージェントは人間の軌跡を真似ます。"
                         : "あと \(max(0, target - human)) 件。不足のあいだはエージェント自身の軌跡を使います。")
                        .font(.system(size: 10)).foregroundStyle(.secondary)
                }
                Spacer()
                Text("\(human) / \(target)")
                    .font(.system(size: 12, weight: .bold, design: .monospaced))
                    .foregroundStyle(sufficient ? Color(red: 0.3, green: 0.9, blue: 0.5)
                                                : Color(red: 1.0, green: 0.75, blue: 0.2))
            }

            ProgressView(value: Double(min(human, target)), total: Double(target))
                .tint(sufficient ? Color(red: 0.3, green: 0.9, blue: 0.5)
                                 : Color(red: 1.0, green: 0.75, blue: 0.2))

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
                    recording = true
                } label: {
                    Label("データを追加（パズルを解く）", systemImage: "plus.circle")
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)

                if lastAdded {
                    Button {
                        EternalMemoryStore.shared.deleteLastDemonstration()
                        lastAdded = false
                        refresh()
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
            パズルを解くと、そのときのマウスの軌跡が1件保存されます。普段どおりに動かしてください — \
            速すぎても遅すぎても、それがあなたの動きなら有効なデータです。うまく動かせなかったときは \
            「直前を取り消す」で消せます。
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
        .sheet(isPresented: $recording) {
            VStack(spacing: 12) {
                Text("いつも通りにマウスを動かしてください")
                    .font(.system(size: 13, weight: .semibold))
                HumanProofPuzzleView { entropy, duration, frames in
                    let pts = entropy.map { (x: Double($0.x), y: Double($0.y)) }
                    let screen = NSScreen.main?.frame.size ?? .zero
                    Task {
                        await EternalMemoryStore.shared.recordHumanDemonstration(
                            points: pts,
                            screenW: Double(screen.width), screenH: Double(screen.height))
                        await MainActor.run {
                            lastAdded = true
                            recording = false
                            refresh()
                        }
                    }
                    _ = duration; _ = frames
                }
                .frame(width: 520, height: 380)
                Button("やめる") { recording = false }
                    .buttonStyle(.bordered).controlSize(.small)
            }
            .padding(20)
        }
        .alert("人間の操作データを全て消しますか？", isPresented: $confirmClear) {
            Button("消去", role: .destructive) {
                EternalMemoryStore.shared.deleteAllDemonstrations()
                lastAdded = false
                refresh()
            }
            Button("やめる", role: .cancel) {}
        } message: {
            Text("\(human) 件が削除されます。エージェント自身の軌跡は残ります（消すと代替が無くなるため）。")
        }
    }

    private var sufficient: Bool { stats?.sufficient ?? false }

    private func refresh() {
        Task {
            let s = EternalMemoryStore.shared.demonstrationStats()
            await MainActor.run { stats = s }
        }
    }
}
