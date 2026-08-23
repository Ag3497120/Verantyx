import SwiftUI

// MARK: - GatekeeperDashboardView
//
// Gatekeeper Pipeline のリアルタイム進捗ダッシュボード。
// 外部LLMへ送ったフラグメント数・ダミー比・パッチ承認率を可視化する。

@MainActor
struct GatekeeperDashboardView: View {

    @StateObject private var vm = GatekeeperDashboardViewModel()

    var body: some View {
        NavigationStack {
            ZStack {
                // Background gradient
                LinearGradient(
                    colors: [Color(hex: "0D0F1A"), Color(hex: "111827")],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
                .ignoresSafeArea()

                ScrollView {
                    VStack(spacing: 20) {
                        headerSection
                        statusBadge
                        metricsGrid
                        fragmentProgressSection
                        patchSummarySection
                        securityInsightsSection
                        sessionHistorySection
                    }
                    .padding(.horizontal, 20)
                    .padding(.bottom, 40)
                }
            }
            .navigationTitle("")
            .toolbar { toolbarContent }
        }
        .preferredColorScheme(.dark)
        .task { await vm.loadCurrentSession() }
    }

    // MARK: - Header

    private var headerSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Image(systemName: "shield.lefthalf.filled")
                    .font(.system(size: 28, weight: .bold))
                    .foregroundStyle(
                        LinearGradient(colors: [.cyan, .blue], startPoint: .top, endPoint: .bottom)
                    )
                VStack(alignment: .leading, spacing: 2) {
                    Text("Gatekeeper Mode")
                        .font(.system(size: 22, weight: .bold, design: .rounded))
                        .foregroundColor(.white)
                    Text("Secure JCross Pipeline Monitor")
                        .font(.caption)
                        .foregroundColor(.gray)
                }
                Spacer()
                Circle()
                    .fill(vm.pipelineState == .idle ? Color.gray : Color.green)
                    .frame(width: 10, height: 10)
                    .shadow(color: vm.pipelineState == .idle ? .clear : .green, radius: 4)
                    .animation(.easeInOut(duration: 1).repeatForever(), value: vm.pipelineState)
            }
        }
        .padding(.top, 16)
    }

    // MARK: - Status Badge

    private var statusBadge: some View {
        HStack(spacing: 8) {
            Image(systemName: vm.pipelineState.icon)
                .foregroundColor(vm.pipelineState.color)
            Text(vm.pipelineState.label)
                .font(.system(size: 13, weight: .semibold, design: .monospaced))
                .foregroundColor(vm.pipelineState.color)
            Spacer()
            if let sessionID = vm.currentSessionID {
                Text("Session: \(sessionID.prefix(10))…")
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundColor(.gray)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(vm.pipelineState.color.opacity(0.08))
                .overlay(
                    RoundedRectangle(cornerRadius: 12)
                        .strokeBorder(vm.pipelineState.color.opacity(0.3), lineWidth: 1)
                )
        )
    }

    // MARK: - Metrics Grid

    private var metricsGrid: some View {
        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
            MetricCard(
                icon: "square.stack.3d.up",
                label: "Fragments Sent",
                value: "\(vm.totalFragmentsSent)",
                subValue: "\(vm.realFragmentCount) real · \(vm.dummyFragmentCount) dummy",
                accent: .cyan
            )
            MetricCard(
                icon: "checkmark.shield",
                label: "Patches Accepted",
                value: "\(vm.acceptedPatchCount)",
                subValue: String(format: "%.0f%% acceptance", vm.acceptanceRate * 100),
                accent: .green
            )
            MetricCard(
                icon: "waveform.badge.exclamationmark",
                label: "Noise Ratio",
                value: String(format: "%.0f%%", vm.noiseRatio * 100),
                subValue: vm.currentDomain.map { "Domain: \($0)" } ?? "No domain",
                accent: .orange
            )
            MetricCard(
                icon: "xmark.shield",
                label: "Threats Blocked",
                value: "\(vm.dummyPatchBlocked + vm.hallucinatedPatchCount)",
                subValue: "\(vm.dummyPatchBlocked) dummy · \(vm.hallucinatedPatchCount) hallucinated",
                accent: .red
            )
        }
    }

    // MARK: - Fragment Progress

    private var fragmentProgressSection: some View {
        DashboardCard(title: "Fragment Transmission", icon: "paperplane.fill", accent: .cyan) {
            VStack(spacing: 12) {
                SegmentedProgressBar(
                    real: vm.realFragmentCount,
                    dummy: vm.dummyFragmentCount,
                    label: "Transmission Mix"
                )
                HStack(spacing: 16) {
                    LegendDot(color: .cyan, label: "Task Fragments")
                    LegendDot(color: .orange.opacity(0.8), label: "Camouflage Decoys")
                    Spacer()
                }
                if let domain = vm.currentDomain {
                    HStack {
                        Image(systemName: "theatermask.and.paintbrush")
                            .foregroundColor(.orange)
                            .font(.caption)
                        Text("Camouflage domain: \(domain)")
                            .font(.caption)
                            .foregroundColor(.gray)
                        Spacer()
                    }
                }
            }
        }
    }

    // MARK: - Patch Summary

    private var patchSummarySection: some View {
        DashboardCard(title: "Patch Validation", icon: "checkmark.seal.fill", accent: .green) {
            VStack(spacing: 10) {
                PatchRow(label: "Accepted", count: vm.acceptedPatchCount, color: .green, icon: "checkmark.circle.fill")
                PatchRow(label: "Dummy Blocked", count: vm.dummyPatchBlocked, color: .orange, icon: "nosign")
                PatchRow(label: "Hallucinated", count: vm.hallucinatedPatchCount, color: .red, icon: "exclamationmark.triangle.fill")
                PatchRow(label: "Malformed", count: vm.malformedPatchCount, color: .gray, icon: "doc.badge.minus")

                Divider().background(Color.white.opacity(0.1))

                // Acceptance rate bar
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text("Acceptance Rate")
                            .font(.caption2)
                            .foregroundColor(.gray)
                        Spacer()
                        Text(String(format: "%.1f%%", vm.acceptanceRate * 100))
                            .font(.caption2.bold())
                            .foregroundColor(vm.acceptanceRate > 0.7 ? .green : .orange)
                    }
                    GeometryReader { geo in
                        ZStack(alignment: .leading) {
                            RoundedRectangle(cornerRadius: 4)
                                .fill(Color.white.opacity(0.08))
                            RoundedRectangle(cornerRadius: 4)
                                .fill(vm.acceptanceRate > 0.7 ? Color.green : Color.orange)
                                .frame(width: geo.size.width * vm.acceptanceRate)
                                .animation(.spring(duration: 0.6), value: vm.acceptanceRate)
                        }
                    }
                    .frame(height: 6)
                }
            }
        }
    }

    // MARK: - Security Insights

    private var securityInsightsSection: some View {
        DashboardCard(title: "Security Insights", icon: "lock.shield.fill", accent: .purple) {
            VStack(spacing: 8) {
                ForEach(vm.securityInsights, id: \.self) { insight in
                    HStack(alignment: .top, spacing: 8) {
                        Image(systemName: "info.circle.fill")
                            .foregroundColor(.purple)
                            .font(.caption)
                            .frame(width: 16)
                        Text(insight)
                            .font(.caption)
                            .foregroundColor(.gray)
                            .fixedSize(horizontal: false, vertical: true)
                        Spacer()
                    }
                }
                if vm.securityInsights.isEmpty {
                    Text("No active session — start a pipeline run to see insights.")
                        .font(.caption)
                        .foregroundColor(.gray.opacity(0.6))
                        .frame(maxWidth: .infinity, alignment: .center)
                        .padding(.vertical, 8)
                }
            }
        }
    }

    // MARK: - Session History

    private var sessionHistorySection: some View {
        DashboardCard(title: "Session History", icon: "clock.arrow.circlepath", accent: .blue) {
            if vm.sessionHistory.isEmpty {
                Text("No completed sessions")
                    .font(.caption)
                    .foregroundColor(.gray.opacity(0.6))
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(.vertical, 8)
            } else {
                VStack(spacing: 8) {
                    ForEach(vm.sessionHistory.prefix(5)) { entry in
                        SessionHistoryRow(entry: entry)
                    }
                }
            }
        }
    }

    // MARK: - Toolbar

    @ToolbarContentBuilder
    private var toolbarContent: some ToolbarContent {
        ToolbarItem(placement: .primaryAction) {
            Button {
                Task { await vm.refresh() }
            } label: {
                Image(systemName: "arrow.clockwise")
                    .foregroundColor(.cyan)
            }
        }
        ToolbarItem(placement: .destructiveAction) {
            if vm.pipelineState != .idle {
                Button {
                    vm.requestAbort()
                } label: {
                    Label("Abort", systemImage: "stop.fill")
                        .foregroundColor(.red)
                }
            }
        }
    }
}

// MARK: - Sub-Components

private struct MetricCard: View {
    let icon: String
    let label: String
    let value: String
    let subValue: String
    let accent: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: icon)
                    .foregroundColor(accent)
                    .font(.system(size: 13, weight: .semibold))
                Text(label)
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(.gray)
            }
            Text(value)
                .font(.system(size: 28, weight: .bold, design: .rounded))
                .foregroundColor(.white)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
            Text(subValue)
                .font(.system(size: 10))
                .foregroundColor(accent.opacity(0.8))
                .lineLimit(2)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 14)
                .fill(Color.white.opacity(0.04))
                .overlay(
                    RoundedRectangle(cornerRadius: 14)
                        .strokeBorder(accent.opacity(0.2), lineWidth: 1)
                )
        )
    }
}

private struct DashboardCard<Content: View>: View {
    let title: String
    let icon: String
    let accent: Color
    @ViewBuilder let content: () -> Content

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 6) {
                Image(systemName: icon)
                    .foregroundColor(accent)
                    .font(.system(size: 13, weight: .semibold))
                Text(title)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(.white.opacity(0.9))
            }
            content()
        }
        .padding(16)
        .background(
            RoundedRectangle(cornerRadius: 16)
                .fill(Color.white.opacity(0.04))
                .overlay(
                    RoundedRectangle(cornerRadius: 16)
                        .strokeBorder(accent.opacity(0.15), lineWidth: 1)
                )
        )
    }
}

private struct SegmentedProgressBar: View {
    let real: Int
    let dummy: Int
    let label: String

    var total: Int { max(real + dummy, 1) }
    var realRatio: CGFloat { CGFloat(real) / CGFloat(total) }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            GeometryReader { geo in
                HStack(spacing: 2) {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(Color.cyan)
                        .frame(width: max(geo.size.width * realRatio - 1, 0))
                    RoundedRectangle(cornerRadius: 4)
                        .fill(Color.orange.opacity(0.75))
                }
                .animation(.spring(duration: 0.6), value: real)
                .animation(.spring(duration: 0.6), value: dummy)
            }
            .frame(height: 8)
            .clipShape(RoundedRectangle(cornerRadius: 4))
        }
    }
}

private struct LegendDot: View {
    let color: Color
    let label: String

    var body: some View {
        HStack(spacing: 5) {
            Circle().fill(color).frame(width: 7, height: 7)
            Text(label).font(.caption2).foregroundColor(.gray)
        }
    }
}

private struct PatchRow: View {
    let label: String
    let count: Int
    let color: Color
    let icon: String

    var body: some View {
        HStack {
            Image(systemName: icon).foregroundColor(color).font(.caption)
            Text(label).font(.caption).foregroundColor(.gray)
            Spacer()
            Text("\(count)")
                .font(.system(size: 13, weight: .bold, design: .monospaced))
                .foregroundColor(count > 0 ? color : .gray.opacity(0.4))
        }
    }
}

private struct SessionHistoryRow: View {
    let entry: GatekeeperDashboardViewModel.SessionHistoryEntry

    var body: some View {
        HStack(spacing: 10) {
            Circle()
                .fill(entry.wasSuccessful ? Color.green.opacity(0.2) : Color.red.opacity(0.2))
                .frame(width: 28, height: 28)
                .overlay(
                    Image(systemName: entry.wasSuccessful ? "checkmark" : "xmark")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundColor(entry.wasSuccessful ? .green : .red)
                )
            VStack(alignment: .leading, spacing: 2) {
                Text(entry.sourcePath)
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(.white.opacity(0.85))
                Text("\(entry.fragmentCount) frags · \(String(format: "%.0f%%", entry.acceptanceRate * 100)) accepted · \(entry.domain)")
                    .font(.system(size: 10))
                    .foregroundColor(.gray)
            }
            Spacer()
            Text(entry.relativeDate)
                .font(.system(size: 10))
                .foregroundColor(.gray.opacity(0.6))
        }
        .padding(.vertical, 4)
    }
}

// MARK: - Color Extension

private extension Color {
    init(hex: String) {
        let hex = hex.trimmingCharacters(in: .alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&int)
        let r = Double((int >> 16) & 0xFF) / 255
        let g = Double((int >> 8)  & 0xFF) / 255
        let b = Double(int         & 0xFF) / 255
        self.init(red: r, green: g, blue: b)
    }
}
