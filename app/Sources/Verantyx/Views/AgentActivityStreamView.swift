import SwiftUI

// MARK: - The run, while it is still running
//
// Activity currently lands as `<think>` lines inside the transcript's
// NSTextView, all of them, permanently. That has two costs. Every step stays at
// full weight forever, so a finished twenty-step run reads as twenty equally
// important lines with the answer buried at the bottom. And while the run is in
// flight nothing moves except text arriving, so there is no difference between
// "working" and "stuck" — the state the user actually wants to read.
//
// This is the other half of the split the audit ribbon started. Prose belongs in
// the transcript. The run's own progress is a live, collapsing surface beside
// it: one line moving while it works, folded into a count when it is done.
//
//   ▸ 実行済み 7件のコマンド, 使用済み 1個のツール      ← finished, folded, quiet
//   ✳ Checking the leaf shape build expects            ← now, moving
//   ✳ 2m 49s · 3.9k tokens                             ← what it cost
//
// Motion is spent where it carries information: the spinner says work is
// happening, the label says what, and the token figure — real, from TurnUsage —
// says what it took. Completed rows do not move at all.

struct AgentActivity: Identifiable, Equatable {
    enum State: Equatable { case running, succeeded, failed }
    enum Kind: Equatable { case command, tool, thought, observation }

    let id = UUID()
    var label: String
    var detail: String?
    var state: State
    var kind: Kind

    var isFinished: Bool { state != .running }
}

struct AgentActivityStreamView: View {

    /// Oldest first. The last entry may still be running.
    let activities: [AgentActivity]
    /// Seconds since the run started; nil hides the footer's clock.
    var elapsed: TimeInterval?
    /// Real measured tokens for the turn, when the backend reported them.
    var tokens: Int?
    var japanese: Bool = true

    @State private var expandedGroups: Set<Int> = []

    private func t(_ en: String, _ ja: String) -> String { japanese ? ja : en }

    // Consecutive finished activities fold into one row; a running one always
    // stands alone. Folding by RUN rather than by kind keeps the order the work
    // actually happened in, which is what makes the collapsed line readable as
    // a sentence rather than a tally.
    private var runs: [[AgentActivity]] {
        var out: [[AgentActivity]] = []
        for activity in activities {
            if activity.isFinished, var last = out.last, last.first?.isFinished == true {
                last.append(activity)
                out[out.count - 1] = last
            } else {
                out.append([activity])
            }
        }
        return out
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            ForEach(Array(runs.enumerated()), id: \.offset) { index, run in
                if run.count == 1, let only = run.first, !only.isFinished {
                    LiveActivityRow(activity: only)
                        .transition(.asymmetric(
                            insertion: .move(edge: .bottom).combined(with: .opacity),
                            removal: .opacity))
                } else {
                    foldedRun(run, index: index)
                }
            }
            if elapsed != nil || tokens != nil { footer }
        }
        .animation(.spring(response: 0.36, dampingFraction: 0.85), value: activities)
        .animation(.spring(response: 0.32, dampingFraction: 0.86), value: expandedGroups)
    }

    // MARK: Finished work, folded

    private func foldedRun(_ run: [AgentActivity], index: Int) -> some View {
        let open = expandedGroups.contains(index)
        return VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 5) {
                Image(systemName: "chevron.right")
                    .font(.system(size: 8, weight: .semibold))
                    .foregroundStyle(.tertiary)
                    .rotationEffect(.degrees(open ? 90 : 0))
                Text(foldedLabel(run))
                    .font(.system(size: 11.5))
                    .foregroundStyle(.secondary)
                if run.contains(where: { $0.state == .failed }) {
                    Image(systemName: "exclamationmark.circle.fill")
                        .font(.system(size: 9))
                        .foregroundStyle(Color(red: 1.0, green: 0.45, blue: 0.4))
                }
            }
            .contentShape(Rectangle())
            .onTapGesture {
                if open { expandedGroups.remove(index) } else { expandedGroups.insert(index) }
            }

            if open {
                VStack(alignment: .leading, spacing: 3) {
                    ForEach(run) { item in FinishedActivityRow(activity: item) }
                }
                .padding(.leading, 14)
                .transition(.asymmetric(
                    insertion: .move(edge: .top).combined(with: .opacity),
                    removal: .opacity))
            }
        }
    }

    private func foldedLabel(_ run: [AgentActivity]) -> String {
        let commands = run.filter { $0.kind == .command }.count
        let tools = run.filter { $0.kind == .tool }.count
        var parts: [String] = []
        if commands > 0 { parts.append(t("\(commands) commands", "\(commands)件のコマンド")) }
        if tools > 0 { parts.append(t("\(tools) tools", "\(tools)個のツール")) }
        if parts.isEmpty { parts.append(t("\(run.count) steps", "\(run.count)件のステップ")) }
        return t("Ran ", "実行済み ") + parts.joined(separator: ", ")
    }

    // MARK: Footer — what the run actually cost

    private var footer: some View {
        HStack(spacing: 6) {
            SparkGlyph(animated: activities.last?.isFinished == false)
            if let elapsed {
                Text(Self.clock(elapsed))
                    .font(.system(size: 11, design: .monospaced))
                    .contentTransition(.numericText())
            }
            if elapsed != nil && tokens != nil {
                Text("·").font(.system(size: 11))
            }
            if let tokens {
                // Real, from the backend's own accounting — not an estimate.
                Text(Self.compact(tokens) + " tokens")
                    .font(.system(size: 11, design: .monospaced))
                    .contentTransition(.numericText())
            }
        }
        .foregroundStyle(.tertiary)
        .padding(.top, 2)
    }

    static func clock(_ seconds: TimeInterval) -> String {
        let s = Int(seconds.rounded())
        return s < 60 ? "\(s)s" : "\(s / 60)m \(s % 60)s"
    }

    static func compact(_ n: Int) -> String {
        n < 1000 ? "\(n)" : String(format: "%.1fk", Double(n) / 1000)
    }
}

// MARK: - The one line that is moving

private struct LiveActivityRow: View {
    let activity: AgentActivity
    @State private var shimmer = false

    var body: some View {
        HStack(spacing: 6) {
            SparkGlyph(animated: true)
            Text(activity.label)
                .font(.system(size: 11.5))
                .foregroundStyle(.primary.opacity(0.85))
                // A slow highlight travelling across the label. Subtle on
                // purpose: it should read as "alive", not as a progress bar
                // pretending to know how far along it is.
                .overlay(
                    LinearGradient(
                        colors: [.clear, .white.opacity(0.35), .clear],
                        startPoint: .leading, endPoint: .trailing)
                    .frame(width: 70)
                    .offset(x: shimmer ? 220 : -90)
                    .blendMode(.plusLighter)
                    .allowsHitTesting(false)
                )
                .mask(Text(activity.label).font(.system(size: 11.5)))
                // The label is replaced as the step changes rather than
                // appended, so it crossfades in place instead of jumping.
                .id(activity.label)
                .transition(.opacity.combined(with: .move(edge: .bottom)))
            Spacer(minLength: 0)
        }
        .onAppear {
            withAnimation(.linear(duration: 1.9).repeatForever(autoreverses: false)) {
                shimmer = true
            }
        }
    }
}

private struct FinishedActivityRow: View {
    let activity: AgentActivity

    private var tint: Color {
        activity.state == .failed
            ? Color(red: 1.0, green: 0.45, blue: 0.4)
            : Color.secondary
    }

    var body: some View {
        HStack(alignment: .top, spacing: 6) {
            Image(systemName: activity.state == .failed
                  ? "xmark.circle.fill" : "checkmark.circle")
                .font(.system(size: 9))
                .foregroundStyle(tint.opacity(activity.state == .failed ? 1 : 0.55))
                .padding(.top, 1.5)
            VStack(alignment: .leading, spacing: 1) {
                Text(activity.label)
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
                if let detail = activity.detail, !detail.isEmpty {
                    Text(detail)
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(.tertiary)
                        .lineLimit(2)
                }
            }
            Spacer(minLength: 0)
        }
    }
}

// MARK: - The spinner
//
// One glyph doing two jobs: it turns while work is in flight and holds still
// when it is not, so "working" and "finished" are distinguishable at a glance
// without reading anything.

private struct SparkGlyph: View {
    let animated: Bool
    @State private var spin = false
    @State private var breathe = false

    var body: some View {
        Image(systemName: "sparkle")
            .font(.system(size: 10, weight: .medium))
            .foregroundStyle(
                animated
                    ? Color(red: 1.0, green: 0.55, blue: 0.35)
                    : Color.secondary.opacity(0.6))
            .rotationEffect(.degrees(spin ? 360 : 0))
            .scaleEffect(breathe ? 1.12 : 0.94)
            .onChange(of: animated) { _, isAnimated in
                isAnimated ? start() : stop()
            }
            .onAppear { if animated { start() } }
    }

    private func start() {
        withAnimation(.linear(duration: 2.6).repeatForever(autoreverses: false)) {
            spin = true
        }
        withAnimation(.easeInOut(duration: 1.1).repeatForever(autoreverses: true)) {
            breathe = true
        }
    }

    private func stop() {
        withAnimation(.easeOut(duration: 0.25)) {
            spin = false
            breathe = false
        }
    }
}
