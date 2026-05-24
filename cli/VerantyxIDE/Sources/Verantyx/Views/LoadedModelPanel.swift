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

    // KVカウンターのリアルタイム表示（1秒ポーリング）
    @State private var kvConsumed: Int = 0
    @State private var kvTimer: Timer? = nil
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
                    .foregroundStyle(Color(red: 0.90, green: 0.90, blue: 0.98))
                    .lineLimit(1)

                HStack(spacing: 8) {
                    // KV consumption bar
                    kvBar(consumed: kvConsumed, threshold: 8000)

                    Text(kvLabel(consumed: kvConsumed))
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(kvColor(consumed: kvConsumed))
                }
            }
            .padding(.horizontal, 10)

            Spacer()

            // ── Kanji topology tags (mid/ alias preview) ──────────────────
            HStack(spacing: 4) {
                ForEach(info.kanjiTags, id: \.self) { tag in
                    Text(tag)
                        .font(.system(size: 9, weight: .medium, design: .monospaced))
                        .foregroundStyle(Color(red: 0.4, green: 0.85, blue: 0.6).opacity(0.8))
                        .padding(.horizontal, 5).padding(.vertical, 2)
                        .background(
                            RoundedRectangle(cornerRadius: 4)
                                .fill(Color(red: 0.4, green: 0.85, blue: 0.6).opacity(0.1))
                                .overlay(
                                    RoundedRectangle(cornerRadius: 4)
                                        .strokeBorder(
                                            Color(red: 0.4, green: 0.85, blue: 0.6).opacity(0.25),
                                            lineWidth: 0.5
                                        )
                                )
                        )
                }
            }
            .padding(.horizontal, 8)

            divider

            // ── Eject button ───────────────────────────────────────────────
            ejectButton
                .padding(.horizontal, 10)
        }
        .frame(height: 36)
        .background(
            ZStack {
                // Dark glassmorphism base
                Color(red: 0.08, green: 0.09, blue: 0.14)
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
        .onAppear {
            startKVPolling()
        }
        .onDisappear {
            stopKVPolling()
        }
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

    // MARK: - KV Bar

    private func kvBar(consumed: Int, threshold: Int) -> some View {
        let ratio = min(1.0, Double(consumed) / Double(threshold))
        return GeometryReader { geo in
            ZStack(alignment: .leading) {
                RoundedRectangle(cornerRadius: 2)
                    .fill(Color.white.opacity(0.07))
                RoundedRectangle(cornerRadius: 2)
                    .fill(kvColor(consumed: consumed).opacity(0.7))
                    .frame(width: geo.size.width * CGFloat(ratio))
                    .animation(.easeOut(duration: 0.3), value: consumed)
            }
        }
        .frame(width: 56, height: 4)
    }

    // MARK: - Eject Button

    private var ejectButton: some View {
        Button {
            if ejectConfirm {
                app.ejectModel()
                ejectConfirm = false
            } else {
                withAnimation(.easeOut(duration: 0.12)) { ejectConfirm = true }
                // Auto-cancel confirmation after 3s
                Task {
                    try? await Task.sleep(for: .seconds(3))
                    await MainActor.run {
                        withAnimation { ejectConfirm = false }
                    }
                }
            }
        } label: {
            HStack(spacing: 5) {
                Image(systemName: ejectConfirm ? "exclamationmark.triangle.fill" : "eject.fill")
                    .font(.system(size: 10, weight: .semibold))
                    .symbolEffect(.bounce, value: ejectConfirm)
                Text(ejectConfirm
                     ? app.t("Confirm?", "確認?")
                     : app.t("Eject", "リジェクト"))
                    .font(.system(size: 10, weight: .semibold, design: .monospaced))
            }
            .foregroundStyle(
                ejectConfirm
                    ? Color(red: 1.0, green: 0.4, blue: 0.3)
                    : Color(red: 0.75, green: 0.75, blue: 0.88)
            )
            .padding(.horizontal, 9).padding(.vertical, 4)
            .background(
                RoundedRectangle(cornerRadius: 5)
                    .fill(ejectConfirm
                          ? Color(red: 1.0, green: 0.4, blue: 0.3).opacity(0.14)
                          : Color.white.opacity(0.06))
                    .overlay(
                        RoundedRectangle(cornerRadius: 5)
                            .strokeBorder(
                                ejectConfirm
                                    ? Color(red: 1.0, green: 0.4, blue: 0.3).opacity(0.5)
                                    : Color.white.opacity(0.12),
                                lineWidth: 0.8
                            )
                    )
            )
            .scaleEffect(isHoveringEject ? 1.04 : 1.0)
            .animation(.easeOut(duration: 0.12), value: isHoveringEject)
        }
        .contentShape(Rectangle())
        .buttonStyle(.plain)
        .onHover { isHoveringEject = $0 }
        .help(app.t("Unload model from memory (frees GPU/ANE resources)",
                    "モデルをメモリから解放します（GPU/ANEリソースを回収）"))
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
                accentColor: Color(red: 0.3, green: 0.85, blue: 0.55),
                kanjiTags: ["技", "速", "軽"]
            )
        case .ollamaReady(let m):
            let name = m.components(separatedBy: ":").first ?? m
            return ModelInfo(
                displayName: name,
                backendLabel: "Ollama",
                backendIcon: "externaldrive",
                accentColor: Color(red: 0.4, green: 0.65, blue: 1.0),
                kanjiTags: ["技", "通", "外"]
            )
        default:
            return nil
        }
    }

    // MARK: - KV Polling

    private func startKVPolling() {
        kvTimer?.invalidate()
        kvTimer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { _ in
            Task {
                let val = await MLXRunner.shared.kvTokensConsumed
                await MainActor.run { kvConsumed = val }
            }
        }
    }

    private func stopKVPolling() {
        kvTimer?.invalidate()
        kvTimer = nil
    }

    private func kvLabel(consumed: Int) -> String {
        guard consumed > 0 else { return "KV: 0" }
        if consumed >= 1000 {
            return String(format: "KV: %.1fk", Double(consumed) / 1000.0)
        }
        return "KV: \(consumed)"
    }

    private func kvColor(consumed: Int) -> Color {
        let ratio = Double(consumed) / 8000.0
        if ratio >= 0.85 { return Color(red: 1.0, green: 0.35, blue: 0.3) }   // 赤: 危険
        if ratio >= 0.6  { return Color(red: 1.0, green: 0.75, blue: 0.2) }   // 黄: 注意
        return Color(red: 0.3, green: 0.85, blue: 0.55)                        // 緑: 安全
    }

    private var divider: some View {
        Rectangle()
            .fill(Color.white.opacity(0.1))
            .frame(width: 1, height: 20)
    }
}

// MARK: - Preview

#if DEBUG
struct LoadedModelPanel_Previews: PreviewProvider {
    static var previews: some View {
        let app = AppState()
        app.modelStatus = .mlxReady(model: "mlx-community/gemma-3-27b-it-4bit")
        return ZStack(alignment: .bottom) {
            Color(red: 0.1, green: 0.1, blue: 0.14)
            VStack(spacing: 0) {
                Spacer()
                LoadedModelPanel()
                    .environmentObject(app)
                Rectangle()
                    .fill(Color(red: 0.08, green: 0.08, blue: 0.11))
                    .frame(height: 28)
            }
        }
        .frame(width: 800, height: 200)
        .preferredColorScheme(.dark)
    }
}
#endif
