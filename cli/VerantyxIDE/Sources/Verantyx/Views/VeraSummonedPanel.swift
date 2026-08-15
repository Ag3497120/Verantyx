import SwiftUI

/// A summoned surface, rendered inside the chat rather than beside it.
///
/// The panel arrives where the person was already looking — under the
/// last thing they read, above the line they type — because a surface
/// that opens somewhere else makes them hunt for what they just asked
/// for. It carries its own name and one way to dismiss it, and nothing
/// else: the chrome was removed to stop teaching a second vocabulary,
/// and rebuilding it inside the card would undo the point.
struct VeraSummonedPanel: View {
    @EnvironmentObject var app: AppState
    let panel: VeraSummon.Panel

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 8) {
                Text(panel.title)
                    .font(.system(size: 11, weight: .semibold, design: .monospaced))
                    .tracking(1.8)
                    .foregroundStyle(.secondary)
                Spacer()
                Button {
                    app.summonedPanel = nil
                } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 10, weight: .medium))
                }
                .buttonStyle(.plain)
                .foregroundStyle(.tertiary)
                .help("閉じる — もう一度名前を言えば戻ります")
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 9)

            Divider().opacity(0.3)

            content
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .background(.quaternary.opacity(0.28), in: RoundedRectangle(cornerRadius: 6))
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .strokeBorder(Color.primary.opacity(0.10), lineWidth: 0.8)
        )
        .frame(maxHeight: 420)
    }

    @ViewBuilder
    private var content: some View {
        switch panel {
        case .settings:
            SettingsView().environmentObject(app)
        case .memory:
            MemoryConsoleView().environmentObject(app)
        case .audit:
            // AuditRibbonView renders one run's summary; without a run
            // there is nothing to show, and inventing a summary here
            // would be the first fabricated evidence on the screen.
            Text("直近の監査サマリはありません。実行後に現れます。")
                .font(.system(size: 11))
                .foregroundStyle(.secondary)
                .padding(12)
        case .cross:
            StereoCrossView(span: 300, showsLabels: true)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
        case .modes:
            modeList
        case .model:
            modelList
        }
    }

    /// Modes as a list rather than a segmented control: the person got
    /// here by naming a mode or naming "モード", and a list says what
    /// the other names are.
    private var modeList: some View {
        VStack(alignment: .leading, spacing: 0) {
            ForEach(AppState.VeraEngineMode.allCases, id: \.self) { mode in
                Button {
                    app.veraEngineMode = mode
                    app.summonedPanel = nil
                } label: {
                    HStack(spacing: 8) {
                        Circle()
                            .fill(app.veraEngineMode == mode
                                  ? VeraInk.verified : Color.clear)
                            .frame(width: 5, height: 5)
                        Text(label(for: mode))
                            .font(.system(size: 12))
                        Spacer()
                        Text(say(for: mode))
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(.tertiary)
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 7)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.vertical, 4)
    }

    private var modelList: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("モデルの切り替えは入力欄のモデル名から行えます。")
                .font(.system(size: 11))
                .foregroundStyle(.secondary)
            Text("Vera の版は「ローカル」ピッカー、会話モデルは Gatekeeper の隣。")
                .font(.system(size: 11))
                .foregroundStyle(.tertiary)
        }
        .padding(12)
    }

    private func label(for m: AppState.VeraEngineMode) -> String {
        switch m {
        case .council:    return "jgen 合議"
        case .standalone: return "Vera-a(併用)"
        case .veraModel:  return "Vera(単体・LLM不使用)"
        case .veraBot:    return "Veraぼっと(設定・UIの案内)"
        case .localLLM:   return "LLM"
        }
    }

    /// What to type to get here without opening anything.
    private func say(for m: AppState.VeraEngineMode) -> String {
        switch m {
        case .council:    return "合議"
        case .standalone: return "vera-a"
        case .veraModel:  return "vera"
        case .veraBot:    return "ぼっと"
        case .localLLM:   return "llm"
        }
    }
}
