import SwiftUI

// MARK: - LoadedModelPanel
//
// モデルがロード（mlxReady / ollamaReady）されている間だけ表示される
// フローティング情報パネル。ステータスバーの真上に固定表示し、
// ワンクリックでモデルをリジェクトできる。
//
// 表示条件:
//   • app.modelStatus が .mlxReady / .ollamaReady の時のみ
//   • app.isLoadedModelPanelVisible == true の時のみ
//
// Deep→Front トポロジーエイリアスは ejectModel() 内で自動書き込まれる。

struct LoadedModelPanel: View {
    @EnvironmentObject var app: AppState

    @State private var ejectConfirm = false
    @State private var isHoveringEject = false

    var body: some View {
        Group {
            if let info = loadedModelInfo {
                panelBody(info: info)
                    .transition(.asymmetric(
                        insertion: .move(edge: .bottom).combined(with: .opacity),
                        removal:   .move(edge: .bottom).combined(with: .opacity)
                    ))
            }
        }
        .animation(.spring(response: 0.32, dampingFraction: 0.78), value: loadedModelInfo != nil)
    }

    // MARK: - Panel Body

    private func panelBody(info: ModelInfo) -> some View {
        HStack(spacing: 0) {

            // ── Backend badge ──────────────────────────────────────────────
            backendBadge(info: info)
                .padding(.leading, 10)

            // ── Model name + meta ──────────────────────────────────────────
            VStack(alignment: .leading, spacing: 2) {
                Text(info.displayName)
                    .font(.system(size: 11, weight: .semibold, design: .monospaced))
                    .foregroundStyle(Theme.fg)
                    .lineLimit(1)


            }
            .padding(.horizontal, 10)

            Spacer()

            // ── Kanji topology tags (mid/ alias preview) ──────────────────
            HStack(spacing: 4) {
                ForEach(info.kanjiTags, id: \.self) { tag in
                    Text(tag)
                        .font(.system(size: 9, weight: .medium, design: .monospaced))
                        .foregroundStyle(Theme.ok.opacity(0.8))
                        .padding(.horizontal, 5).padding(.vertical, 2)
                        .background(
                            RoundedRectangle(cornerRadius: 4)
                                .fill(Theme.ok.opacity(0.1))
                                .overlay(
                                    RoundedRectangle(cornerRadius: 4)
                                        .strokeBorder(
                                            Theme.ok.opacity(0.25),
                                            lineWidth: 0.5
                                        )
                                )
                        )
                }
            }
            .padding(.horizontal, 8)
            .padding(.trailing, 10)
        }
        .frame(height: 36)
        .background(
            ZStack {
                // Dark glassmorphism base
                Theme.bg
                // Subtle gradient tint matching backend color
                LinearGradient(
                    colors: [info.accentColor.opacity(0.06), .clear],
                    startPoint: .leading,
                    endPoint: .trailing
                )
            }
        )
        // Top border — subtle active indicator
        .overlay(
            Rectangle()
                .fill(
                    LinearGradient(
                        colors: [info.accentColor.opacity(0.6), info.accentColor.opacity(0.15)],
                        startPoint: .leading,
                        endPoint: .trailing
                    )
                )
                .frame(height: 1),
            alignment: .top
        )
        // Polling removed
    }

    // MARK: - Backend Badge

    private func backendBadge(info: ModelInfo) -> some View {
        HStack(spacing: 4) {
            Image(systemName: info.backendIcon)
                .font(.system(size: 9, weight: .bold))
            Text(info.backendLabel)
                .font(.system(size: 8, weight: .bold, design: .monospaced))
        }
        .foregroundStyle(info.accentColor)
        .padding(.horizontal, 6).padding(.vertical, 3)
        .background(
            RoundedRectangle(cornerRadius: 4)
                .fill(info.accentColor.opacity(0.12))
                .overlay(
                    RoundedRectangle(cornerRadius: 4)
                        .strokeBorder(info.accentColor.opacity(0.35), lineWidth: 0.8)
                )
        )
    }

    // MARK: - Computed

    private struct ModelInfo: Equatable {
        let displayName: String
        let backendLabel: String
        let backendIcon: String
        let accentColor: Color
        let kanjiTags: [String]
    }

    private var loadedModelInfo: ModelInfo? {
        switch app.modelStatus {
        case .mlxReady(let m):
            let name = m.components(separatedBy: "/").last ?? m
            return ModelInfo(
                displayName: name,
                backendLabel: "MLX",
                backendIcon: "cpu",
                accentColor: Theme.ok,
                kanjiTags: ["技", "速", "軽"]
            )
        case .ollamaReady(let m):
            let name = m.components(separatedBy: ":").first ?? m
            return ModelInfo(
                displayName: name,
                backendLabel: "Ollama",
                backendIcon: "externaldrive",
                accentColor: Theme.sel,
                kanjiTags: ["技", "通", "外"]
            )
        default:
            return nil
        }
    }


}

// MARK: - Preview

#if DEBUG
struct LoadedModelPanel_Previews: PreviewProvider {
    static var previews: some View {
        let app = AppState()
        app.modelStatus = .mlxReady(model: "mlx-community/gemma-3-27b-it-4bit")
        return ZStack(alignment: .bottom) {
            Theme.panel2
            VStack(spacing: 0) {
                Spacer()
                LoadedModelPanel()
                    .environmentObject(app)
                Rectangle()
                    .fill(Theme.panel)
                    .frame(height: 28)
            }
        }
        .frame(width: 800, height: 200)
        .preferredColorScheme(.dark)
    }
}
#endif
