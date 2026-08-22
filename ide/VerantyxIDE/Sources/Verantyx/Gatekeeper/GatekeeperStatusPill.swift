import SwiftUI

// MARK: - GatekeeperStatusPill
//
// Gatekeeper Mode 有効時に画面上部中央に表示する小型ステータスバー。
// クリックで GatekeeperModeView をシート表示。

struct GatekeeperStatusPill: View {
    @ObservedObject private var gk = GatekeeperModeState.shared
    @State private var showDetail = false
    @State private var pulse = false

    var body: some View {
        Button { showDetail = true } label: {
            HStack(spacing: 6) {
                // Pulsing shield dot
                ZStack {
                    Circle()
                        .fill(Color.green.opacity(pulse ? 0.3 : 0.0))
                        .frame(width: 18, height: 18)
                        .animation(.easeInOut(duration: 1.2).repeatForever(autoreverses: true), value: pulse)
                    Image(systemName: "shield.lefthalf.filled")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(Color(red: 0.2, green: 1.0, blue: 0.5))
                }

                Text("Gatekeeper")
                    .font(.system(size: 10, weight: .bold, design: .monospaced))
                    .foregroundStyle(Color(red: 0.2, green: 1.0, blue: 0.5))

                Divider()
                    .frame(height: 10)
                    .background(Color.green.opacity(0.4))

                // Phase indicator
                phaseLabel

                // Vault quick-status
                vaultDot
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(
                Capsule()
                    .fill(Color(red: 0.05, green: 0.15, blue: 0.08).opacity(0.92))
                    .overlay(
                        Capsule()
                            .strokeBorder(Color(red: 0.2, green: 0.9, blue: 0.45).opacity(0.6), lineWidth: 1)
                    )
            )
            .shadow(color: Color(red: 0.1, green: 0.8, blue: 0.4).opacity(0.4), radius: 6, x: 0, y: 2)
        }
        .buttonStyle(.plain)
        .onAppear { pulse = true }
        .sheet(isPresented: $showDetail) {
            GatekeeperModeView()
                .frame(width: 540, height: 750)
        }
    }

    // MARK: - Phase label

    @ViewBuilder
    private var phaseLabel: some View {
        switch gk.phase {
        case .idle:
            Text("Ready")
                .font(.system(size: 9, design: .monospaced))
                .foregroundStyle(Color.green.opacity(0.8))

        case .commanderPlanning(let step):
            HStack(spacing: 3) {
                ProgressView().scaleEffect(0.5).frame(width: 10, height: 10)
                Text(step.prefix(20))
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(.yellow)
            }

        case .fetchingVault(let file):
            HStack(spacing: 3) {
                ProgressView().scaleEffect(0.5).frame(width: 10, height: 10)
                Text("Vault: \(file.components(separatedBy: "/").last ?? file)".prefix(24))
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(.orange)
            }

        case .workerCalling, .workerThinking:
            HStack(spacing: 3) {
                ProgressView().scaleEffect(0.5).frame(width: 10, height: 10)
                Text("Worker…")
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(.purple)
            }

        case .reverseTranspiling:
            HStack(spacing: 3) {
                ProgressView().scaleEffect(0.5).frame(width: 10, height: 10)
                Text("Reverse IR…")
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(.teal)
            }

        case .writingToDisk(let f):
            Text("Writing \(f.components(separatedBy: "/").last ?? f)".prefix(24))
                .font(.system(size: 9, design: .monospaced))
                .foregroundStyle(.yellow)

        case .done:
            Text("Done ✓")
                .font(.system(size: 9, design: .monospaced))
                .foregroundStyle(.green)

        case .error(let msg):
            Text("⚠ \(msg.prefix(20))")
                .font(.system(size: 9, design: .monospaced))
                .foregroundStyle(.red)
        }
    }

    // MARK: - Vault status dot

    @ViewBuilder
    private var vaultDot: some View {
        switch gk.vault.vaultStatus {
        case .notInitialized:
            Image(systemName: "externaldrive.badge.exclamationmark")
                .font(.system(size: 9))
                .foregroundStyle(.orange)
        case .converting(let p, _):
            Text("\(Int(p * 100))%")
                .font(.system(size: 8, design: .monospaced))
                .foregroundStyle(.orange)
        case .ready(let n, _):
            HStack(spacing: 2) {
                Image(systemName: "externaldrive.fill")
                    .font(.system(size: 9))
                    .foregroundStyle(.green)
                Text("\(n)")
                    .font(.system(size: 8, design: .monospaced))
                    .foregroundStyle(.green.opacity(0.8))
            }
        case .error:
            Image(systemName: "externaldrive.badge.xmark")
                .font(.system(size: 9))
                .foregroundStyle(.red)
        }
    }
}
