import SwiftUI

// MARK: - EngineModeChooserView
//
// 何も開いていない起動時、いちばん最初に出る画面。**トグルではなく画面。**
// 服飾か LLM か、両方の下に何が変わるかを一言添えて、大きく二枚出す。
//
// 一度選べば `AppState.selectEngineMode` が覚え、次回はここを通らず
// 前回いた場所に着地する — `hasChosenEngineMode` がその記憶そのもの。
// 選び直したい人のための「戻る道」はここではなく左レール側
// (`app.showModeChooser = true`)に置いてある。ここは選ぶだけの画面で、
// 選んだ後に自分で消える。
struct EngineModeChooserView: View {
    @EnvironmentObject var app: AppState

    var body: some View {
        ZStack {
            Theme.bg.ignoresSafeArea()

            VStack(spacing: 28) {
                Spacer()

                VStack(spacing: 8) {
                    Text(app.t("Verantyx", "Verantyx"))
                        .font(.system(size: 15, weight: .bold, design: .rounded))
                        .foregroundStyle(Theme.dim)
                    Text(app.t("What are you here to do?", "何をしに来ましたか"))
                        .font(.system(size: 22, weight: .bold))
                        .foregroundStyle(Theme.fg)
                }

                HStack(spacing: 18) {
                    modeCard(
                        icon: "tshirt",
                        titleEN: "Atelier", titleJA: "Atelier（服飾）",
                        bodyEN: "A garment workbench. What you see is the state of the piece — evidence, structure, measurements — not a conversation.",
                        bodyJA: "服飾の作業面。画面に出るのは会話ではなく、服そのものの状態 — 証拠・構造・寸法です。",
                        mode: .atelier)

                    modeCard(
                        icon: "bubble.left.and.bubble.right",
                        titleEN: "LLM", titleJA: "LLM",
                        bodyEN: "A plain conversation with a model — code, files, a terminal alongside it. Nothing routed through the garment ledger.",
                        bodyJA: "モデルとの素の会話。コード・ファイル・ターミナルが並びます。服飾の台帳は通りません。",
                        mode: .localLLM)
                }
                .frame(maxWidth: 640)

                Spacer()
                Spacer()
            }
            .padding(40)
        }
    }

    private func modeCard(icon: String, titleEN: String, titleJA: String,
                          bodyEN: String, bodyJA: String,
                          mode: AppState.VeraEngineMode) -> some View {
        Button {
            app.selectEngineMode(mode)
        } label: {
            VStack(alignment: .leading, spacing: 14) {
                Image(systemName: icon)
                    .font(.system(size: 26, weight: .medium))
                    .foregroundStyle(Theme.sel)
                    .frame(width: 44, height: 44)
                    .background(Theme.sel.opacity(0.12), in: RoundedRectangle(cornerRadius: 10))

                Text(app.t(titleEN, titleJA))
                    .font(.system(size: 16, weight: .bold))
                    .foregroundStyle(Theme.fg)

                Text(app.t(bodyEN, bodyJA))
                    .font(.system(size: 12))
                    .foregroundStyle(Theme.dim)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)

                Spacer(minLength: 0)

                HStack(spacing: 5) {
                    Text(app.t("Start", "はじめる"))
                        .font(.system(size: 12, weight: .semibold))
                    Image(systemName: "arrow.right")
                        .font(.system(size: 10, weight: .semibold))
                }
                .foregroundStyle(Theme.sel)
            }
            .padding(20)
            .frame(width: 290, height: 210, alignment: .topLeading)
            .background(Theme.panel, in: RoundedRectangle(cornerRadius: 14))
            .overlay(RoundedRectangle(cornerRadius: 14).stroke(Theme.line, lineWidth: 1))
        }
        .buttonStyle(.plain)
    }
}
