import SwiftUI

// MARK: - AIModeLayoutView
// Full-screen 2-pane layout for AI Priority mode.
//
//  ┌─────────────────────────────┬──────────────────────────────┐
//  │  AI Chat (left)             │  Artifact Preview (right)    │
//  │  Gemini-style               │  HTML / Mermaid / Code / MD  │
//  │  full chat history          │  WKWebView live render       │
//  │  no file tree, no IDE       │  + Diff view tab             │
//  └─────────────────────────────┴──────────────────────────────┘
//
// Red banner at top announces AI Priority mode is active.
// Switch back to Human mode via the banner button or toolbar.

struct AIModeLayoutView: View {
    @EnvironmentObject var app: AppState


    var body: some View {
        VStack(spacing: 0) {

            // ── AI Priority banner ────────────────────────────────────
            aiPriorityBanner

            Divider()
                .overlay(Color(red: 1.0, green: 0.35, blue: 0.20).opacity(0.7))

            // ── 2-pane: Chat | Artifact (always visible) ──────────────
            ResizableHSplit(
                minLeft: 340, maxLeft: 99999, minRight: 300, initialLeft: 520
            ) {
                // Left: Full-screen chat
                fullChatPanel
            } right: {
                // Right: Artifact panel (always on in AI Mode) + optional Terminal
                VStack(spacing: 0) {
                    ArtifactPanelView()
                        .environmentObject(app)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)

                    if app.showProcessLog {
                        Divider().opacity(0.4)
                        TerminalPanelView(terminal: app.terminal)
                            .environmentObject(app)
                            .frame(height: 180)
                    }
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)

            // ── Loaded Model Panel — shows when model is active ───────
            Group {
                switch app.modelStatus {
                case .mlxReady, .ollamaReady, .bitnetReady:
                    LoadedModelPanel()
                        .environmentObject(app)
                default:
                    EmptyView()
                }
            }
            .animation(.spring(response: 0.32, dampingFraction: 0.78), value: app.modelStatus)

            // ── Status bar ─────────────────────────────────────────────
            Divider().opacity(0.4)
            StatusBarView(terminal: app.terminal)
        }
        .background(Color(red: 0.09, green: 0.09, blue: 0.12))
        .toastOverlay()
    }

    // MARK: - AI Priority Banner (always-red, pulsing)

    private var aiPriorityBanner: some View {
        HStack(spacing: 10) {
            // Pulsing red dot
            PulsingDot(color: Color(red: 1.0, green: 0.25, blue: 0.15))

            VStack(alignment: .leading, spacing: 1) {
                Text("AI PRIORITY MODE")
                    .font(.system(size: 11, weight: .black, design: .monospaced))
                    .foregroundStyle(Color(red: 1.0, green: 0.45, blue: 0.30))
                Text(app.t("No approvals · Auto-write · Artifacts auto-show", "承認なし · 自律書き込み · Artifact自動表示"))
                    .font(.system(size: 9, weight: .medium))
                    .foregroundStyle(Color(red: 0.75, green: 0.42, blue: 0.32))
            }

            Spacer()




        }
        .padding(.horizontal, 16)
        .padding(.vertical, 7)
        .background(
            LinearGradient(
                colors: [
                    Color(red: 0.22, green: 0.08, blue: 0.06),
                    Color(red: 0.12, green: 0.09, blue: 0.10)
                ],
                startPoint: .leading, endPoint: .trailing
            )
        )
    }

    // MARK: - Full Chat Panel (left side)

    private var fullChatPanel: some View {
        VStack(spacing: 0) {
            // Minimal chat header
            HStack(spacing: 8) {
                Image(systemName: "atom")
                    .font(.system(size: 11))
                    .foregroundStyle(Color(red: 0.4, green: 0.7, blue: 1.0))
                Text("VerantyxAgent")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Color(red: 0.85, green: 0.85, blue: 0.92))
                Spacer()

                // Terminal toggle only (artifact panel is always visible in AI Mode)
                Button {
                    withAnimation { app.showProcessLog.toggle() }
                } label: {
                    Image(systemName: "terminal")
                        .symbolVariant(app.showProcessLog ? .fill : .none)
                        .font(.system(size: 11))
                        .foregroundStyle(app.showProcessLog
                                         ? Color(red: 0.3, green: 1.0, blue: 0.5)
                                         : .secondary)
                }
                .contentShape(Rectangle())
                .buttonStyle(.plain)
                .help(AppLanguage.shared.t("Terminal", "ターミナル"))
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 8)
            .background(Color(red: 0.11, green: 0.11, blue: 0.15))

            Divider().opacity(0.3)

            // Chat messages fill the space
            AgentChatView()
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    private var shortModel: String {
        switch app.modelStatus {
        case .ollamaReady(let m): return m.components(separatedBy: ":").first ?? m
        case .mlxReady(let m):   return "MLX/" + (m.components(separatedBy: "/").last ?? m)
        case .bitnetReady(let m): return "⚡" + m.components(separatedBy: "-").prefix(3).joined(separator: "-")
        default:                  return "no model"
        }
    }
}

// MARK: - PulsingDot
// Animated red dot used in the AI Priority banner to signal live autonomous execution.

struct PulsingDot: View {
    let color: Color
    @State private var pulse = false

    var body: some View {
        ZStack {
            Circle()
                .fill(color.opacity(pulse ? 0.20 : 0.0))
                .frame(width: 18, height: 18)
                .scaleEffect(pulse ? 1.6 : 0.9)

            Circle()
                .fill(color)
                .frame(width: 8, height: 8)
        }
        .onAppear {
            withAnimation(
                .easeInOut(duration: 1.1).repeatForever(autoreverses: true)
            ) { pulse = true }
        }
    }
}
