import Foundation
import SwiftUI

// MARK: - GatekeeperChatBridge
//
// Phase 1 (IR変換): JCrossVault.bulkConvert() が担当。ワークスペース選択時に自動実行。
// Phase 2 (チャット): CommanderOrchestrator.handleUserMessage() へ委譲。
//   → Vault に保存済みの .jcross を読むだけ。IR再生成なし。
//
// デッドロック防止:
//   このクラスは @MainActor を持たない (Sendable)。
//   CommanderOrchestrator は @MainActor。
//   直接 await するとインスタンスの inferenceTask (MainActor Task) が
//   MainActor をホールドしたまま Commander の再ホップを待ちデッドロックする。
//   → Task { @MainActor in } で Commander を独立したタスクとして起動し
//     inferenceTask 側はその完了を await せず isGenerating だけ管理する。

final class GatekeeperChatBridge: Sendable {

    static let shared = GatekeeperChatBridge()
    private init() {}

    func run(instruction: String, images: [String] = [], appState: AppState) async {
        let vaultStatus = await MainActor.run {
            GatekeeperModeState.shared.vault.vaultStatus
        }

        switch vaultStatus {

        // ── Vault 準備完了 → Commander を独立タスクで起動 ────────────────
        case .ready(let fileCount, _):
            await MainActor.run {
                appState.logProcess(
                    "🛡️ Gatekeeper Phase 2 — Commander 起動 (Vault: \(fileCount) ファイル)",
                    kind: .system
                )
                // ⚠️ Commander が isGenerating=true を前提とするUI（動画スピナー等）のために
                // ここでは isGenerating を false に戻さず維持する。
                // 完了後は Commander または大元の onSubmit 等でリセットされる必要があるが、
                // 取り急ぎスピナーを表示し続けるために維持する。
            }

            // CommanderOrchestrator は @MainActor。
            // inferenceTask (MainActor Task) から直接 await すると
            // MainActor を手放さないままデッドロックするため、
            // 独立した MainActor Task として起動する。
            let capturedInstruction = instruction
            let capturedImages = images
            Task { @MainActor in
                await CommanderOrchestrator.shared.handleUserMessage(capturedInstruction, images: capturedImages)
                appState.isGenerating = false
            }

        // ── 変換中 → 待機メッセージ ──────────────────────────────────────
        case .converting(let progress, let currentFile):
            let pct = Int(progress * 100)
            await MainActor.run {
                appState.messages.append(ChatMessage(
                    role: .system,
                    content: "⏳ Vault 変換中 (\(pct)%) — \(currentFile)\n完了後にもう一度送信してください。"
                ))
                appState.isGenerating = false
            }

        // ── 未初期化 → ガイドメッセージ ──────────────────────────────────
        case .notInitialized:
            let hasWorkspace = await MainActor.run { appState.workspaceURL != nil }
            await MainActor.run {
                let msg = hasWorkspace
                    ? "🛡️ Vault 未初期化 — 設定 → 「変換」ボタンを押してください（数秒で完了）。"
                    : "🛡️ ワークスペースが未選択です — 📁 アイコンでフォルダを開くと自動変換が始まります。"
                appState.messages.append(ChatMessage(role: .system, content: msg))
                appState.isGenerating = false
            }

        // ── エラー ────────────────────────────────────────────────────────
        case .error(let message):
            await MainActor.run {
                appState.messages.append(ChatMessage(
                    role: .system,
                    content: "❌ Vault エラー: \(message)\n設定 → 「再変換」で復旧できます。"
                ))
                appState.isGenerating = false
            }
        }
    }
}
