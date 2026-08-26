import SwiftUI

/// Small ring/gauge button for the chat input row -- tapping expands a
/// Claude.ai-usage-style popover, but scoped to what's actually meaningful
/// for this local-model IDE: not SaaS plan-limit/5-hour-reset/credits
/// (no equivalent here), but a per-turn breakdown by memory-injection
/// source (L2 zone memory, Vera, skills, eternal/vector memory, system
/// prompt, conversation history) plus compression events -- so a long
/// task's memory features are visibly pulling their weight (or visibly
/// not, as a dev diagnostic). Backed entirely by `ContextUsageTracker`,
/// which is populated at the exact points those strings already get built
/// in `AgentLoop.swift` -- no new estimation logic here, just display.
struct ContextUsageIndicator: View {
    @ObservedObject private var tracker = ContextUsageTracker.shared
    @EnvironmentObject var app: AppState
    @State private var showPopover = false

    private var usageFraction: Double {
        guard tracker.contextWindowCharBudget > 0 else { return 0 }
        return min(Double(tracker.current.totalInjectionChars) / Double(tracker.contextWindowCharBudget), 1.0)
    }

    private var ringColor: Color {
        if usageFraction > 0.85 { return Theme.bad }
        if usageFraction > 0.6  { return Theme.warn }
        return Color(red: 0.4, green: 0.8, blue: 1.0)
    }

    var body: some View {
        Button {
            showPopover = true
        } label: {
            ZStack {
                Circle()
                    .stroke(Theme.faint, lineWidth: 2.5)
                    .frame(width: 22, height: 22)
                Circle()
                    .trim(from: 0, to: usageFraction)
                    .stroke(ringColor, style: StrokeStyle(lineWidth: 2.5, lineCap: .round))
                    .rotationEffect(.degrees(-90))
                    .frame(width: 22, height: 22)
            }
            .frame(width: 26, height: 26)
        }
        .contentShape(Rectangle())
        .buttonStyle(.plain)
        .help(app.t("Context usage", "コンテキスト使用状況"))
        .popover(isPresented: $showPopover) {
            ContextUsageDetailView()
                .environmentObject(app)
        }
    }
}

private struct ContextUsageDetailView: View {
    @ObservedObject private var tracker = ContextUsageTracker.shared
    @EnvironmentObject var app: AppState

    private var usage: ContextUsageTracker.InjectionUsage { tracker.current }

    /// Real tokens when the active backend reported a `usage` field this
    /// turn; otherwise a `/4` char estimate, clearly labeled as such below
    /// rather than presented as exact.
    private var totalTokensDisplay: (value: Int, isEstimate: Bool) {
        if let input = usage.realInputTokens, let output = usage.realOutputTokens {
            return (input + output, false)
        }
        if let input = usage.realInputTokens {
            return (input, false)
        }
        return (usage.estimatedTotalTokens, true)
    }

    private var budgetTokens: Int { max(tracker.contextWindowCharBudget / 4, 1) }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(app.t("Context Usage", "コンテキスト使用状況"))
                .font(.system(size: 13, weight: .bold))

            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(app.t("This turn", "今回のターン"))
                        .font(.system(size: 10))
                        .foregroundStyle(.secondary)
                    Spacer()
                    Text("\(totalTokensDisplay.value.formatted()) / \(budgetTokens.formatted())" + (totalTokensDisplay.isEstimate ? " (\(app.t("estimate", "推定")))" : ""))
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(.secondary)
                }
                usageBar(fraction: Double(totalTokensDisplay.value) / Double(budgetTokens), height: 8)
            }

            Divider()

            VStack(alignment: .leading, spacing: 8) {
                Text(app.t("Breakdown by source", "内訳(ソース別)"))
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(.secondary)

                breakdownRow(app.t("System prompt", "システムプロンプト"), chars: usage.systemPromptChars, color: Theme.dim)
                breakdownRow(app.t("Conversation history", "会話履歴"), chars: usage.conversationHistoryChars, color: Theme.sel)
                breakdownRow(app.t("L2 zone memory (L1-L3)", "L2ゾーン記憶(L1-L3)"), chars: usage.l2ZoneChars, color: Theme.ok)
                breakdownRow(app.t("Vera-α", "Vera-α"), chars: usage.veraChars, color: Theme.warn)
                breakdownRow(app.t("Skills", "スキル"), chars: usage.skillChars, color: Theme.accent)
                breakdownRow(app.t("Eternal/vector memory", "永遠記憶(ベクトル)"), chars: usage.eternalMemoryChars, color: Color(red: 1.0, green: 0.55, blue: 0.75))
            }

            Divider()

            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Text(app.t("Context window", "コンテキストウィンドウ"))
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(.secondary)
                    Spacer()
                    if let model = app.activeModelName {
                        Text(app.t(
                            "Model max: \(ContextBudgetManager.budget(for: model).maxTokens.formatted()) tok",
                            "モデル上限: \(ContextBudgetManager.budget(for: model).maxTokens.formatted())トークン"
                        ))
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(.tertiary)
                    }
                }
                Picker("", selection: Binding(
                    get: { app.contextWindowOverride },
                    set: { app.contextWindowOverride = $0 }
                )) {
                    Text(app.t("Auto (by model size)", "自動(モデルサイズ基準)")).tag(0)
                    Text("~8K chars").tag(8_000)
                    Text("~16K chars").tag(16_000)
                    Text("~32K chars").tag(32_000)
                    Text("~64K chars").tag(64_000)
                    Text("~128K chars").tag(128_000)
                }
                .labelsHidden()
                .frame(maxWidth: .infinity)
            }

            Divider()

            HStack {
                Text(app.t("Compression this session", "今セッションの圧縮"))
                    .font(.system(size: 10))
                    .foregroundStyle(.secondary)
                Spacer()
                Text(app.t(
                    "\(tracker.compressionEventsThisSession)× · \(tracker.charsSavedByCompressionThisSession.formatted()) chars saved",
                    "\(tracker.compressionEventsThisSession)回 · \(tracker.charsSavedByCompressionThisSession.formatted())文字削減"
                ))
                .font(.system(size: 10, design: .monospaced))
                .foregroundStyle(.secondary)
            }

            Text(app.t(
                "Token counts are real API usage when the active backend reports one; otherwise a ~4 chars/token estimate. \"Context window\" itself is a character budget under the hood (see Settings).",
                "トークン数は、使用中のバックエンドがusageを返す場合は実数、それ以外は約4文字/トークンの推定値です。「コンテキストウィンドウ」自体は内部的には文字数ベースの予算です(Settings参照)。"
            ))
            .font(.system(size: 9))
            .foregroundStyle(Theme.dim)
            .frame(width: 280, alignment: .leading)
        }
        .padding(14)
        .frame(width: 300)
    }

    private func breakdownRow(_ label: String, chars: Int, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(label)
                    .font(.system(size: 10))
                Spacer()
                Text("\(chars.formatted()) chars (~\(chars / 4) tok)")
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(.secondary)
            }
            usageBar(fraction: usage.totalInjectionChars > 0 ? Double(chars) / Double(max(usage.totalInjectionChars, 1)) : 0, height: 4, color: color)
        }
    }

    private func usageBar(fraction: Double, height: CGFloat, color: Color = Color(red: 0.4, green: 0.8, blue: 1.0)) -> some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                RoundedRectangle(cornerRadius: height / 2)
                    .fill(Color.white.opacity(0.08))
                RoundedRectangle(cornerRadius: height / 2)
                    .fill(color)
                    .frame(width: geo.size.width * min(max(fraction, 0), 1))
            }
        }
        .frame(height: height)
    }
}
