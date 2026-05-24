import SwiftUI

// MARK: - CortexOnboardingSheet
//
// アプリ起動時に表示される Verantyx Cortex 紹介ポップアップ。
// UserDefaults key: "cortex_onboarding_dismissed" が true なら表示しない。

struct CortexOnboardingSheet: View {

    @Binding var isPresented: Bool

    // "もう表示しない" トグル — バインド先は UserDefaults
    @State private var neverShowAgain: Bool = false

    // GitHub repo URL for Verantyx Cortex
    private let githubURL = URL(string: "https://github.com/Ag3497120/verantyx-cortex")!
    // npm install one-liner (copied to clipboard / shown in terminal)
    private let npmCommand = "npx -y @verantyx/cortex setup"

    var body: some View {
        ZStack {
            // ── Background ──────────────────────────────────────────────
            backgroundGradient

            VStack(spacing: 0) {
                // ── Header ───────────────────────────────────────────────
                headerSection

                Divider()
                    .background(Color.white.opacity(0.08))

                // ── Feature list ─────────────────────────────────────────
                featureSection
                    .padding(.horizontal, 36)
                    .padding(.top, 24)

                Spacer()

                // ── Terminal preview ─────────────────────────────────────
                terminalBadge
                    .padding(.horizontal, 36)

                Spacer()

                Divider()
                    .background(Color.white.opacity(0.08))

                // ── Footer: toggle + buttons ─────────────────────────────
                footerSection
                    .padding(.horizontal, 28)
                    .padding(.vertical, 20)
            }
        }
        .frame(width: 620, height: 560)
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }

    // MARK: - Background

    private var backgroundGradient: some View {
        ZStack {
            Color(red: 0.08, green: 0.09, blue: 0.13)

            // Subtle radial glow top-left (brand color)
            RadialGradient(
                colors: [
                    Color(red: 0.20, green: 0.45, blue: 0.90).opacity(0.18),
                    Color.clear
                ],
                center: .topLeading,
                startRadius: 0,
                endRadius: 340
            )

            // Subtle radial glow bottom-right (teal accent)
            RadialGradient(
                colors: [
                    Color(red: 0.10, green: 0.75, blue: 0.65).opacity(0.10),
                    Color.clear
                ],
                center: .bottomTrailing,
                startRadius: 0,
                endRadius: 280
            )
        }
    }

    // MARK: - Header

    private var headerSection: some View {
        VStack(spacing: 12) {
            // Icon row
            HStack(spacing: 14) {
                // App icon placeholder
                ZStack {
                    RoundedRectangle(cornerRadius: 14)
                        .fill(
                            LinearGradient(
                                colors: [
                                    Color(red: 0.25, green: 0.50, blue: 1.00),
                                    Color(red: 0.10, green: 0.75, blue: 0.65)
                                ],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            )
                        )
                        .frame(width: 56, height: 56)
                    Text("🧠")
                        .font(.system(size: 28))
                }

                Image(systemName: "arrow.right")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundStyle(Color.white.opacity(0.35))

                ZStack {
                    RoundedRectangle(cornerRadius: 14)
                        .fill(Color.white.opacity(0.06))
                        .frame(width: 56, height: 56)
                    Text("⚡️")
                        .font(.system(size: 28))
                }
            }
            .padding(.top, 28)

            Text(AppLanguage.shared.t("Supercharge with Verantyx Cortex", "Verantyx Cortex でさらに強力に"))
                .font(.system(size: 22, weight: .bold, design: .rounded))
                .foregroundStyle(.white)

            Text(AppLanguage.shared.t("Combined with our MCP server that persists AI memory,\nVerantyx IDE evolves into a true long-term cognitive agent.", "AI の記憶を永続化する MCP サーバーと組み合わせると、\nVerantyx IDE が真の長期記憶エージェントに進化します。"))
                .font(.system(size: 13.5))
                .foregroundStyle(Color.white.opacity(0.60))
                .multilineTextAlignment(.center)
                .lineSpacing(3)
                .padding(.bottom, 20)
        }
        .padding(.horizontal, 36)
    }

    // MARK: - Feature list

    private var featureSection: some View {
        VStack(spacing: 10) {
            featureRow(
                icon: "memorychip",
                color: Color(red: 0.40, green: 0.70, blue: 1.00),
                title: AppLanguage.shared.t("Cross-session Long-term Memory", "セッションを超えた長期記憶"),
                detail: AppLanguage.shared.t("Persists conversations, decisions, and patterns to JCross nodes", "会話・決定・コードパターンを JCross ノードに永続保存")
            )
            featureRow(
                icon: "arrow.triangle.2.circlepath",
                color: Color(red: 0.35, green: 0.85, blue: 0.70),
                title: AppLanguage.shared.t("Share with Claude / Cursor", "Claude / Cursor / Antigravity と共有"),
                detail: AppLanguage.shared.t("Distill skills from cloud models to local environment", "distill_skill でクラウドモデルのスキルをローカルに蒸留")
            )
            featureRow(
                icon: "sparkles",
                color: Color(red: 0.75, green: 0.50, blue: 1.00),
                title: AppLanguage.shared.t("Auto-inject Memory at Startup", "起動時に記憶を自動注入"),
                detail: AppLanguage.shared.t("Instantly restore previous context via boot() / guide()", "boot() / guide() で前回の作業コンテキストを即座に復元")
            )
        }
    }

    private func featureRow(
        icon: String,
        color: Color,
        title: String,
        detail: String
    ) -> some View {
        HStack(alignment: .top, spacing: 14) {
            ZStack {
                Circle()
                    .fill(color.opacity(0.15))
                    .frame(width: 36, height: 36)
                Image(systemName: icon)
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(color)
            }

            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(.white)
                Text(detail)
                    .font(.system(size: 11.5))
                    .foregroundStyle(Color.white.opacity(0.50))
            }
            Spacer()
        }
    }

    // MARK: - Terminal badge

    private var terminalBadge: some View {
        HStack(spacing: 10) {
            Image(systemName: "terminal")
                .font(.system(size: 12))
                .foregroundStyle(Color(red: 0.40, green: 0.85, blue: 0.60))

            Text(npmCommand)
                .font(.system(size: 12, design: .monospaced))
                .foregroundStyle(Color(red: 0.40, green: 0.85, blue: 0.60))

            Spacer()

            // Copy to clipboard button
            Button {
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(npmCommand, forType: .string)
            } label: {
                Image(systemName: "doc.on.doc")
                    .font(.system(size: 11))
                    .foregroundStyle(Color.white.opacity(0.45))
            }
            .contentShape(Rectangle())
            .buttonStyle(.plain)
            .help(AppLanguage.shared.t("Copy to clipboard", "クリップボードにコピー"))
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(Color.white.opacity(0.05))
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(Color(red: 0.40, green: 0.85, blue: 0.60).opacity(0.25), lineWidth: 1)
                )
        )
    }

    // MARK: - Footer

    private var footerSection: some View {
        VStack(spacing: 14) {
            // "もう表示しない" toggle
            HStack {
                Toggle(isOn: $neverShowAgain) {
                    Text(AppLanguage.shared.t("Don't show again", "次回から表示しない"))
                        .font(.system(size: 12))
                        .foregroundStyle(Color.white.opacity(0.50))
                }
                .toggleStyle(.checkbox)
                .tint(Color(red: 0.40, green: 0.70, blue: 1.00))
                Spacer()
            }

            // Action buttons
            HStack(spacing: 12) {
                // Dismiss
                Button {
                    dismiss()
                } label: {
                    Text(AppLanguage.shared.t("Close", "閉じる"))
                        .font(.system(size: 13, weight: .medium))
                        .foregroundStyle(Color.white.opacity(0.55))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 9)
                        .background(
                            RoundedRectangle(cornerRadius: 8)
                                .fill(Color.white.opacity(0.07))
                        )
                }
                .contentShape(Rectangle())
                .buttonStyle(.plain)

                // GitHub
                Button {
                    NSWorkspace.shared.open(githubURL)
                    dismiss()
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: "arrow.up.right.square")
                            .font(.system(size: 12, weight: .semibold))
                        Text(AppLanguage.shared.t("View on GitHub", "GitHub で見る"))
                            .font(.system(size: 13, weight: .semibold))
                    }
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 9)
                    .background(
                        RoundedRectangle(cornerRadius: 8)
                            .fill(
                                LinearGradient(
                                    colors: [
                                        Color(red: 0.25, green: 0.50, blue: 1.00),
                                        Color(red: 0.15, green: 0.65, blue: 0.90)
                                    ],
                                    startPoint: .leading,
                                    endPoint: .trailing
                                )
                            )
                    )
                }
                .contentShape(Rectangle())
                .buttonStyle(.plain)
            }
        }
    }

    // MARK: - Helpers

    private func dismiss() {
        if neverShowAgain {
            UserDefaults.standard.set(true, forKey: "cortex_onboarding_dismissed")
        }
        withAnimation(.easeOut(duration: 0.2)) {
            isPresented = false
        }
    }
}

// MARK: - Preview

#Preview {
    CortexOnboardingSheet(isPresented: .constant(true))
        .preferredColorScheme(.dark)
}
