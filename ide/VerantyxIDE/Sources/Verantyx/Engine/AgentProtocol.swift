import Foundation

// MARK: - AgentMessage
//
// BitNet Commander ↔ Gemma Worker 間のメッセージプロトコル。
// 全通信はこの型で行われる。直接メモリ共有は行わない。

enum AgentMessage: Codable {

    // ── BitNet → Gemma ─────────────────────────────────────────────

    /// ワークスペース準備完了。L2.5地図 + 索引を渡す。TODO作成を依頼。
    case workspaceReady(l25Map: String, index: String, userTask: String)

    /// Gemmaが要求したファイルを渡す。
    /// L3生ソース + そのファイルのL2.5要約 + BitNetが選んだ記憶層コンテキスト
    case fileDelivery(path: String, content: String, l25Summary: String, memoryContext: String)

    /// ビルド検証結果をGemmaに通知
    case buildResult(path: String, success: Bool, errors: [String])

    /// BitNetがGemmaに注入する追加記憶 (L1/L1.5/L2の中から最も必要なもの)
    case memoryInjection(layer: String, content: String)

    // ── Gemma → BitNet ─────────────────────────────────────────────

    /// 計画フェーズ完了。TODO リストを渡す。
    case todoListReady([AgentTodoItem])

    /// ファイルを要求する
    case requestFile(path: String, reason: String)

    /// ファイルを修正/新規作成した。ビルド+L2.5更新を依頼。
    case fileModified(path: String, content: String, l25Summary: String, isBuildRequired: Bool)

    /// TODOを更新する (ビルドエラー対応・計画変更)
    case todoUpdate([AgentTodoItem])

    /// タスク完了。サマリーをユーザーに提示してループ終了。
    case summary(text: String)

    /// エラー報告 (Gemmaが自分でエラーを検知した場合)
    case errorReport(path: String, error: String, suggestedFix: String)
}

// MARK: - AgentTodoItem

struct AgentTodoItem: Codable, Identifiable {
    let id: String
    let action: Action
    let targetPath: String        // 対象ファイルパス
    let sourcePath: String?       // 変換元 (変換タスクの場合)
    let description: String       // Gemmaが作った説明
    let dependsOn: [String]       // 依存するTodoのid
    var status: Status

    enum Action: String, Codable {
        case createFile     // 新規ファイル作成
        case modifyFile     // 既存ファイル変更
        case deleteFile     // ファイル削除
        case buildVerify    // ビルド検証のみ
        case runTest        // テスト実行
    }

    enum Status: String, Codable {
        case pending, inProgress, succeeded, failed, skipped, waitingDependency
    }
}

// MARK: - AgentMailbox
//
// BitNet と Gemma が非同期に通信するためのメッセージキュー。
// actor で thread-safe に実装。

actor AgentMailbox {

    private var toGemma: [AgentMessage] = []
    private var toBitNet: [AgentMessage] = []

    // 送信
    func sendToGemma(_ msg: AgentMessage) { toGemma.append(msg) }
    func sendToBitNet(_ msg: AgentMessage) { toBitNet.append(msg) }

    // 受信 (FIFO)
    func receiveForGemma() -> AgentMessage? {
        guard !toGemma.isEmpty else { return nil }
        return toGemma.removeFirst()
    }

    func receiveForBitNet() -> AgentMessage? {
        guard !toBitNet.isEmpty else { return nil }
        return toBitNet.removeFirst()
    }

    func hasMessageForGemma() -> Bool { !toGemma.isEmpty }
    func hasMessageForBitNet() -> Bool { !toBitNet.isEmpty }
    func clearAll() { toGemma.removeAll(); toBitNet.removeAll() }
}
