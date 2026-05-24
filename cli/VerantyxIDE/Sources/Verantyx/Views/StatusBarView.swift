import SwiftUI

// MARK: - TokenSpeedMeter
// リアルタイム tok/s メーター。最大60サンプルのスパークライン波形を表示する。

struct TokenSpeedMeter: View {
    @EnvironmentObject var app: AppState

    // ── サンプル履歴（最大 N ポイント） ──────────────────────────────────
    @State private var samples: [Double] = Array(repeating: 0, count: 60)
    @State private var sampleTimer: Timer? = nil
    @State private var pulse  = false

    // 速度ゾーン（M1 Max 基準）
    private let fastThreshold: Double = 20   // 緑
    private let midThreshold:  Double = 8    // 黄
    private let sampleCap:     Int    = 60
    private let barWidth:      CGFloat = 2.5
    private let barGap:        CGFloat = 0.8
    private let meterHeight:   CGFloat = 18

    var body: some View {
        HStack(spacing: 8) {

            // ── パルスドット ─────────────────────────────────────────
            ZStack {
                Circle()
                    .fill(speedColor.opacity(0.25))
                    .frame(width: 12, height: 12)
                    .scaleEffect(pulse && app.isGenerating ? 1.6 : 1.0)
                    .animation(
                        app.isGenerating
                            ? .easeInOut(duration: 0.6).repeatForever(autoreverses: true)
                            : .default,
                        value: pulse
                    )
                Circle()
                    .fill(app.isGenerating ? speedColor : speedColor.opacity(0.4))
                    .frame(width: 6, height: 6)
            }

            // ── スパークライン波形 ────────────────────────────────────
            SparklineView(
                samples:       samples,
                maxValue:      max(1, peakSample * 1.15),
                activeColor:   speedColor,
                height:        meterHeight,
                barWidth:      barWidth,
                barGap:        barGap
            )
            .frame(width: CGFloat(sampleCap) * (barWidth + barGap), height: meterHeight)

            // ── 数値読み取り ──────────────────────────────────────────
            VStack(alignment: .trailing, spacing: 0) {
                Text(currentLabel)
                    .font(.system(size: 11, weight: .semibold, design: .monospaced))
                    .foregroundStyle(speedColor)
                    .contentTransition(.numericText(countsDown: false))
                    .animation(.easeOut(duration: 0.2), value: app.tokensPerSecond)

                if peakSample > 0 {
                    Text(String(format: "pk %.0f", peakSample))
                        .font(.system(size: 8, design: .monospaced))
                        .foregroundStyle(.secondary.opacity(0.6))
                }
            }
        }
        .onAppear  { startSampling(); pulse = true }
        .onDisappear { stopSampling() }
    }

    // MARK: - Sampling

    private func startSampling() {
        sampleTimer?.invalidate()
        sampleTimer = Timer.scheduledTimer(withTimeInterval: 0.25, repeats: true) { _ in
            Task { @MainActor in
                self.samples.append(max(0, app.tokensPerSecond))
                if self.samples.count > sampleCap {
                    self.samples.removeFirst(self.samples.count - sampleCap)
                }
            }
        }
    }

    private func stopSampling() {
        sampleTimer?.invalidate()
        sampleTimer = nil
    }

    // MARK: - Computed

    private var peakSample: Double { samples.max() ?? 0 }

    private var currentLabel: String {
        guard app.isGenerating || app.tokensPerSecond > 0 else { return "── tok/s" }
        if app.isGenerating && app.tokensPerSecond < 0.5 { return "start…" }
        return String(format: "%.1f tok/s", app.tokensPerSecond)
    }

    private var speedColor: Color {
        let s = app.tokensPerSecond
        if s >= fastThreshold { return Color(red: 0.2, green: 1.0, blue: 0.5) }   // 緑
        if s >= midThreshold  { return Color(red: 1.0, green: 0.75, blue: 0.1) }  // 黄
        if s > 0              { return Color(red: 1.0, green: 0.45, blue: 0.3) }  // 赤
        return Color.white.opacity(0.25)
    }
}

// MARK: - SparklineView
// Canvas でバーグラフを描画する（Path アニメーション対応）。

struct SparklineView: View {
    let samples:     [Double]
    let maxValue:    Double
    let activeColor: Color
    let height:      CGFloat
    let barWidth:    CGFloat
    let barGap:      CGFloat

    var body: some View {
        Canvas { ctx, size in
            let n     = samples.count
            let barH  = size.height
            let total = barWidth + barGap

            for (i, val) in samples.enumerated() {
                let x     = CGFloat(i) * total
                let ratio = maxValue > 0 ? min(val / maxValue, 1.0) : 0.0
                let h     = max(1.5, CGFloat(ratio) * barH)
                let rect  = CGRect(x: x, y: barH - h, width: barWidth, height: h)

                // 高いバーほど不透明
                let alpha = 0.2 + 0.8 * ratio
                // 最新サンプルは最も明るく
                let isLatest = i == n - 1
                let color    = isLatest ? activeColor : activeColor.opacity(alpha * 0.7)

                ctx.fill(Path(roundedRect: rect, cornerRadius: 0.8), with: .color(color))
            }
        }
        .animation(.easeOut(duration: 0.15), value: samples.count)
        .clipShape(RoundedRectangle(cornerRadius: 3))
    }
}

// MARK: - StatusBarView
// The bottom bar. The only number that matters: tok/s.

struct StatusBarView: View {
    @EnvironmentObject var app: AppState
    @ObservedObject var terminal: TerminalRunner

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

            HStack(spacing: 4) {
                Image(systemName: "folder")
                    .font(.system(size: 9))
                Text(app.workspaceURL?.lastPathComponent ?? "no workspace")
                    .font(.system(size: 10, design: .monospaced))
            }
            .foregroundStyle(.secondary)
            .padding(.horizontal, 8)

            // ── Center: model label ───────────────────────────────────
            Spacer()

            HStack(spacing: 6) {
                Image(systemName: modelIcon)
                    .font(.system(size: 9))
                Text(modelLabel)
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(app.statusColor)
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

                // ★ メーター本体
                TokenSpeedMeter()
                    .padding(.horizontal, 6)

                divider

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
        .frame(height: 28)  // メーター追加のため高さを 22→28 に拡張
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
}
