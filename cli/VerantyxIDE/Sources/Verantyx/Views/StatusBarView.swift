import SwiftUI

// MARK: - StatusBarView
// The bottom bar.

struct StatusBarView: View {
    @EnvironmentObject var app: AppState
    @ObservedObject var terminal: TerminalRunner
    @ObservedObject private var vault = OSAssetMemoryVault.shared
    @ObservedObject private var l25Engine = L25IndexEngine.shared
    @ObservedObject private var gkOrchestrator = GatekeeperPipelineOrchestrator.shared

    var body: some View {
        HStack(spacing: 0) {

            // ── Left: version + workspace ─────────────────────────────
            HStack(spacing: 6) {
                Text("VX")
                    .font(.system(size: 10, weight: .bold, design: .monospaced))
                    .foregroundStyle(Color(red: 0.4, green: 0.9, blue: 0.6))
                Text(appVersion)
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(.secondary)
            }
            .padding(.horizontal, 10)

            divider

            // ── Center: Progress Indicators ───────────────────────────────────
            Spacer()

            HStack(spacing: 12) {
                // OS Asset L3.5 scan progress
                if vault.isScanning {
                    HStack(spacing: 6) {
                        Text("L3.5")
                            .font(.system(size: 9, weight: .bold, design: .monospaced))
                            .foregroundStyle(.cyan)
                        ProgressView().controlSize(.small).scaleEffect(0.7).tint(.cyan)
                        Text(vault.scanProgress)
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(.cyan)
                            .lineLimit(1)
                    }
                }

                if l25Engine.isIndexing {
                    if vault.isScanning { divider }
                    HStack(spacing: 6) {
                        Text("L2.5")
                            .font(.system(size: 9, weight: .bold, design: .monospaced))
                            .foregroundStyle(Color(red: 0.4, green: 0.85, blue: 0.6))
                        ProgressView(value: l25Engine.indexingProgress)
                            .progressViewStyle(LinearProgressViewStyle(tint: Color(red: 0.4, green: 0.85, blue: 0.6)))
                            .frame(width: 40)
                        Text("\(Int(l25Engine.indexingProgress * 100))%")
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(Color(red: 0.4, green: 0.85, blue: 0.6))
                    }
                }

                if gkOrchestrator.isRunning {
                    if vault.isScanning || l25Engine.isIndexing { divider }
                    HStack(spacing: 6) {
                        Text("GK")
                            .font(.system(size: 9, weight: .bold, design: .monospaced))
                            .foregroundStyle(Color(red: 0.9, green: 0.6, blue: 0.2))
                        ProgressView().controlSize(.small).scaleEffect(0.7).tint(Color(red: 0.9, green: 0.6, blue: 0.2))
                        Text(gkPhaseString(gkOrchestrator.phase))
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(Color(red: 0.9, green: 0.6, blue: 0.2))
                            .lineLimit(1)
                    }
                }
            }
            .padding(.horizontal, 10)

            Spacer()

            // ── Right: TOKEN SPEED METER ──────────────────────────────
            HStack(spacing: 8) {

                // Session total tokens
                if app.totalTokensGenerated > 0 {
                    Text("\(app.totalTokensGenerated) tok")
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(Color(red: 0.5, green: 0.5, blue: 0.6))

                    divider
                }

                // Terminal running indicator
                if terminal.isRunning {
                    HStack(spacing: 3) {
                        Circle().fill(.orange).frame(width: 5, height: 5)
                        Text("exec")
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(.orange)
                    }
                    divider
                }



                // Model status dot
                HStack(spacing: 4) {
                    Circle().fill(app.statusColor).frame(width: 6, height: 6)
                    Text(app.statusLabel)
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
                .padding(.trailing, 10)
            }
        }
        .frame(height: 28)
        .background(Color(red: 0.08, green: 0.08, blue: 0.11))
    }

    // MARK: - Computed

    private var appVersion: String {
        let version = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "unknown"
        return "v\(version)"
    }

    private var modelLabel: String {
        switch app.modelStatus {
        case .ollamaReady(let m):    return m.components(separatedBy: ":").first ?? m
        case .mlxReady(let m):       return (m.components(separatedBy: "/").last ?? m)
        case .ready(let n):          return n
        case .connecting:            return "connecting…"
        case .mlxDownloading(let m): return "↓ \(m.components(separatedBy: "/").last ?? m)"
        default:                     return "no model"
        }
    }

    private var modelIcon: String {
        switch app.modelStatus {
        case .mlxReady:    return "cpu"
        case .ollamaReady: return "externaldrive"
        default:           return "circle.dashed"
        }
    }

    private var divider: some View {
        Rectangle()
            .fill(Color.white.opacity(0.1))
            .frame(width: 1, height: 16)
    }

    private func gkPhaseString(_ phase: GatekeeperPipelineOrchestrator.PipelinePhase) -> String {
        switch phase {
        case .idle: return "Idle"
        case .fragmenting: return "Fragmenting..."
        case .registeringSession: return "Registering..."
        case .sendingToWorker(let f, let t): return "Sending (\(f)/\(t))"
        case .awaitingPatch: return "Awaiting Patch"
        case .validatingPatch: return "Validating..."
        case .bonsaiReview: return "Bonsai Review"
        case .reverseTranspiling: return "Transpiling..."
        case .applyingToSource: return "Applying..."
        case .archiving: return "Archiving..."
        case .done: return "Done"
        case .failed: return "Failed"
        }
    }
}
