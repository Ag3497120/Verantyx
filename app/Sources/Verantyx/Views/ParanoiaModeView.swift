import SwiftUI

// MARK: - ParanoiaModeView
//
// Paranoia Mode専用のターミナルスタイルLogパネル。
// PrivacyShieldViewと共存し、Paranoia Modeが有効なときにアクティビティログを表示する。
//
// ┌──────────────────────────────────────────────────────┐
// │  🔴 PARANOIA MODE                                    │
// │  ─────────────────────────────────────────────────── │
// │  [PHASE 1] tree-sitter AST extraction              ✓  │
// │  Extracted 47 symbols from VerantyxCoreAuth.swift     │
// │  ─────────────────────────────────────────────────── │
// │  [PHASE 2] Gemma 4 sensitivity classification      ✓  │
// │  🔴 VerantyxCoreAuth  →  Alpha__1                    │
// │  🔴 internalApiKey    →  Beta__2                     │
// │  🟢 viewDidLoad       →  [safe, kept]                │
// │  ─────────────────────────────────────────────────── │
// │  [PHASE 3] Rust surgical masking                   ✓  │
// │  [PHASE 4] JCross vault stored                     ✓  │
// │  ✅ READY — 12 secrets masked · 0 transmitted         │
// └──────────────────────────────────────────────────────┘

struct ParanoiaModeView: View {

    @EnvironmentObject var appState: AppState
    @State private var isExpanded: Bool = true

    var body: some View {
        VStack(spacing: 0) {
            // ─── Header ──────────────────────────────────────────────────────
            header

            // ─── Log terminal ─────────────────────────────────────────────────
            if isExpanded {
                terminalLog
                    .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
        .animation(.spring(duration: 0.25), value: isExpanded)
        .background(Theme.bg)
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .stroke(
                    appState.inferenceMode == .paranoiaMode
                        ? Theme.bad.opacity(0.7)
                        : Color.gray.opacity(0.15),
                    lineWidth: 1
                )
        )
        .shadow(color: .black.opacity(0.4), radius: 8, y: 4)
    }

    // MARK: - Header

    private var header: some View {
        Button(action: { isExpanded.toggle() }) {
            HStack(spacing: 10) {
                // Mode badge
                HStack(spacing: 6) {
                    Image(systemName: "eye.slash.circle.fill")
                        .foregroundStyle(Theme.bad)
                        .symbolEffect(.pulse, isActive: appState.inferenceMode == .paranoiaMode)

                    Text("PARANOIA MODE")
                        .font(.system(size: 11, weight: .bold, design: .monospaced))
                        .foregroundStyle(Theme.bad)
                }

                Spacer()

                // Stats pill
                if let stats = appState.lastMaskingStats, appState.inferenceMode == .paranoiaMode {
                    Text("\(stats.total) protected")
                        .font(.system(size: 10, weight: .semibold, design: .monospaced))
                        .padding(.horizontal, 8)
                        .padding(.vertical, 2)
                        .background(Theme.bad.opacity(0.15))
                        .foregroundStyle(Theme.bad)
                        .clipShape(Capsule())
                }

                // Running indicator
                if ParanoiaEngine.shared.isRunning {
                    ProgressView()
                        .scaleEffect(0.6)
                        .tint(Theme.bad)
                }

                Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                    .font(.system(size: 10, weight: .medium))
                    .foregroundStyle(.secondary)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
        }
        .contentShape(Rectangle())
        .buttonStyle(.plain)
        .background(Theme.bg)
    }

    // MARK: - Terminal Log

    private var terminalLog: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 3) {
                    if ParanoiaEngine.shared.logLines.isEmpty {
                        emptyStateView
                    } else {
                        ForEach(ParanoiaEngine.shared.logLines) { line in
                            logRow(line)
                                .id(line.id)
                        }
                    }
                    Color.clear.frame(height: 1).id("bottom")
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
            }
            .frame(maxHeight: 280)
            .onChange(of: ParanoiaEngine.shared.logLines.count) { _, _ in
                withAnimation { proxy.scrollTo("bottom") }
            }
        }
    }

    @ViewBuilder
    private func logRow(_ line: ParanoiaEngine.ParanoiaLogLine) -> some View {
        HStack(alignment: .top, spacing: 8) {
            // Timestamp
            Text(line.timestamp.formatted(date: .omitted, time: .shortened))
                .font(.system(size: 9, design: .monospaced))
                .foregroundStyle(.quaternary)
                .frame(width: 50, alignment: .trailing)

            // Content
            Text(line.text)
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(lineColor(line.kind))
                .textSelection(.enabled)
                .lineLimit(nil)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.vertical, 1)
        .background(
            line.kind == .phase
                ? Theme.bad.opacity(0.04)
                : Color.clear,
            in: RoundedRectangle(cornerRadius: 3)
        )
    }

    private func lineColor(_ kind: ParanoiaEngine.LogKind) -> Color {
        switch kind {
        case .phase:    return Theme.bad
        case .info:     return Color(red: 0.7, green: 0.7, blue: 0.75)
        case .masked:   return Theme.bad
        case .safe:     return Theme.ok
        case .success:  return Theme.ok
        case .error:    return Theme.bad
        case .ready:    return Theme.ok
        }
    }

    private var emptyStateView: some View {
        VStack(spacing: 8) {
            Image(systemName: "eye.slash")
                .font(.system(size: 24))
                .foregroundStyle(Theme.bad.opacity(0.4))

            Text("Paranoia Mode is armed.")
                .font(.system(size: 12, weight: .semibold, design: .monospaced))
                .foregroundStyle(.secondary)

            Text("Send a message with a file selected.\nEvery symbol will be classified before transmission.")
                .font(.system(size: 10, design: .monospaced))
                .foregroundStyle(.tertiary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 24)
    }
}

// MARK: - ParanoiaModeToggle
//
// Compact toggle that can be embedded in SettingsView / PrivacyShieldView.

struct ParanoiaModeToggle: View {
    @EnvironmentObject var appState: AppState

    var body: some View {
        HStack(spacing: 12) {
            // Icon
            ZStack {
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .fill(
                        appState.inferenceMode == .paranoiaMode
                            ? Theme.bad.opacity(0.2)
                            : Color.white.opacity(0.05)
                    )
                    .frame(width: 36, height: 36)

                Image(systemName: "eye.slash.circle.fill")
                    .font(.system(size: 18))
                    .foregroundStyle(
                        appState.inferenceMode == .paranoiaMode
                            ? Theme.bad
                            : .secondary
                    )
            }

            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text("Paranoia Mode")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(
                            appState.inferenceMode == .paranoiaMode
                                ? Theme.bad
                                : .primary
                        )

                    if appState.inferenceMode == .paranoiaMode {
                        Text("ACTIVE")
                            .font(.system(size: 9, weight: .bold, design: .monospaced))
                            .padding(.horizontal, 6)
                            .padding(.vertical, 1)
                            .background(Theme.bad.opacity(0.2))
                            .foregroundStyle(Theme.bad)
                            .clipShape(Capsule())
                    }
                }

                Text("AST-precise · Gemma 4 classification · Rust byte-offset masking")
                    .font(.system(size: 10))
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }

            Spacer()

            Toggle("", isOn: Binding(
                get: { appState.inferenceMode == .paranoiaMode },
                set: { on in
                    appState.inferenceMode = on ? .paranoiaMode : .privacyShield
                }
            ))
            .toggleStyle(.switch)
            .tint(Theme.bad)
            .scaleEffect(0.85)
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .fill(Color.white.opacity(0.03))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .stroke(
                    appState.inferenceMode == .paranoiaMode
                        ? Theme.bad.opacity(0.3)
                        : Color.white.opacity(0.06),
                    lineWidth: 1
                )
        )
    }
}

// MARK: - Preview

#Preview {
    ParanoiaModeView()
        .environmentObject(AppState())
        .frame(width: 420)
        .padding()
        .background(Theme.bg)
}
