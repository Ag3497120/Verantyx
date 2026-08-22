import Foundation

// MARK: - BitNet Intent Translator
//
// 【役割】ユーザーの自然言語の「意図」を、意味論ゼロの「構造命令」に翻訳する。
//
// gus_massa (HackerNews) の洞察に基づく設計:
//   "e.g., calculateTax() becomes [Symbol_A]()"
//   → Cloud LLMはシンボルを見ても意味が分からない。
//   → しかし BitNet がローカルで「Symbol_A = ASYNC_IO系の関数」と翻訳すれば
//     Cloud LLM は意味を知らずに構造パズルを解ける。
//
// 処理フロー:
//   ユーザー自然言語指示
//       ↓ intentToStructuralCommand()
//   VaultLookup（FUNC名→ノードID逆引き）
//       ↓
//   CategoryAnnotation（機能ドメインタグ付与）
//       ↓
//   StructuralCommand（Cloud LLMへの純粋グラフ命令）
//       ↓ GatekeeperPromptBuilder へ渡す

// MARK: - Structural Command（Cloud LLMへ送る命令の型）

/// Cloud LLMへの「意味なし・構造あり」命令。
/// 具体的な変数名・関数名・数値は一切含まない。
struct StructuralCommand: Codable {
    /// 操作の種類
    let operation: Operation
    /// 対象ノードID（Vaultでマッピング済み）
    let targetNodeID: String
    /// 挿入・修正する制御フローの種類
    let controlFlowKind: ControlFlowKind?
    /// ターゲット関数の機能カテゴリ（セマンティクスなし抽象タグ）
    let domainCategory: DomainCategory
    /// 追加パラメータ（TYPE:opaqueで値を隠蔽）
    let parameters: [String: OpaqueParameter]
    /// 分岐先ノードID（エラーハンドリング等）
    let branchTargetNodeID: String?

    enum Operation: String, Codable {
        case insertNode       // 新しいノードを挿入
        case wrapNode         // 既存ノードをラップ
        case replaceNode      // ノードを置換
        case connectNodes     // ノード間にエッジを追加
        case removeNode       // ノードを削除
    }

    enum ControlFlowKind: String, Codable {
        case loop             // リトライ / ループ
        case timeout_wrapper  // タイムアウト
        case error_boundary   // エラーハンドリング
        case condition        // 条件分岐
        case async_await      // 非同期待機
        case lock             // 排他制御
    }

    enum DomainCategory: String, Codable {
        case async_io         // ネットワーク / 非同期I/O
        case ui_render        // UIレンダリング
        case compute          // 純粋計算
        case storage          // ファイル / DB
        case security         // 認証 / 暗号
        case ipc              // プロセス間通信（AppleScriptなど）
        case unknown
    }

    /// TYPE:opaque — 具体値を隠蔽したパラメータ
    struct OpaqueParameter: Codable {
        let typeCategory: String  // "int", "float", "string", "duration"
        let placeholder: String   // Vaultキー（ローカル側で実値に解決）
    }
}

// MARK: - Intent Classifier（自然言語→操作種別）

private struct IntentClassifier {

    /// キーワードベースの意図分類（BitNetへの委譲前の高速ルールベース）
    static func classify(_ text: String) -> (StructuralCommand.Operation, StructuralCommand.ControlFlowKind?) {
        let lower = text.lowercased()

        // リトライ・繰り返し
        if lower.contains("リトライ") || lower.contains("retry") || lower.contains("繰り返") {
            return (.wrapNode, .loop)
        }
        // タイムアウト
        if lower.contains("タイムアウト") || lower.contains("timeout") {
            return (.wrapNode, .timeout_wrapper)
        }
        // エラーハンドリング
        if lower.contains("エラー") || lower.contains("error") || lower.contains("失敗") {
            return (.insertNode, .error_boundary)
        }
        // 非同期
        if lower.contains("非同期") || lower.contains("async") || lower.contains("await") {
            return (.wrapNode, .async_await)
        }
        // 条件分岐
        if lower.contains("条件") || lower.contains("if") || lower.contains("チェック") {
            return (.insertNode, .condition)
        }
        // 削除
        if lower.contains("削除") || lower.contains("remove") || lower.contains("消して") {
            return (.removeNode, nil)
        }
        return (.insertNode, nil)
    }
}

// MARK: - Vault Lookup（FUNC名 → NodeID 逆引き）

private struct VaultLookup {

    /// Vault から自然言語キーワードに最も近い FunctionNode を逆引きする。
    /// 例: 「AppleScript」→ vault 内 "runAppleScript" → FUNC[0xA6D5]
    static func findNodeID(
        for keyword: String,
        in vault: JCrossIRVault
    ) -> (nodeID: String, category: StructuralCommand.DomainCategory) {
        let lower = keyword.lowercased()
        let entries = vault.allEntries()

        // MemoryConcrete の variableName を検索
        for entry in entries {
            guard let mem = entry.memoryConcrete else { continue }
            let name = mem.variableName.lowercased()
            if name.contains(lower) || lower.contains(name) {
                let cat = categorize(typeName: entry.typeConcrete?.semanticRole ?? "")
                return (entry.nodeID.raw, cat)
            }
        }

        // マッチしない場合は最初のFUNCノードを返す（フォールバック）
        if let first = entries.first {
            return (first.nodeID.raw, .unknown)
        }
        return ("NODE_UNKNOWN", .unknown)
    }

    private static func categorize(typeName: String) -> StructuralCommand.DomainCategory {
        let lower = typeName.lowercased()
        if lower.contains("async") || lower.contains("network") || lower.contains("fetch") { return .async_io }
        if lower.contains("view") || lower.contains("ui") || lower.contains("render") { return .ui_render }
        if lower.contains("script") || lower.contains("ipc") || lower.contains("applescript") { return .ipc }
        if lower.contains("file") || lower.contains("store") || lower.contains("db") { return .storage }
        if lower.contains("auth") || lower.contains("crypt") || lower.contains("sign") { return .security }
        return .compute
    }
}

// MARK: - BitNetIntentTranslator（メインAPI）

/// ユーザーの自然言語指示 → StructuralCommand（意味なし・構造あり）への翻訳エンジン。
///
/// BitNet がローカルで稼働している場合は BitNet に委譲し、
/// そうでない場合はルールベースで処理する（フォールバック）。
final class BitNetIntentTranslator {

    static let shared = BitNetIntentTranslator()
    private init() {}

    /// 変換のメインエントリポイント。
    ///
    /// - Parameters:
    ///   - userInstruction: ユーザーの自然言語指示（例: 「AppleScriptの実行関数にリトライを追加して」）
    ///   - vault: ローカルVault（関数名→NodeID の逆引きに使用）
    ///   - ir: 対象IRドキュメント（構造参照に使用）
    /// - Returns: Cloud LLM への StructuralCommand（意味ゼロ・構造フル）
    func translate(
        userInstruction: String,
        vault: JCrossIRVault,
        ir: JCrossIRDocument
    ) async -> StructuralCommand {

        // Step 1: 意図分類（キーワードルールベース → 将来BitNet委譲）
        let (operation, cfKind) = IntentClassifier.classify(userInstruction)

        // Step 2: 対象ノードをVaultで逆引き
        let keyword = extractKeyword(from: userInstruction)
        let (nodeID, category) = VaultLookup.findNodeID(for: keyword, in: vault)

        // Step 3: エラーハンドリング分岐先ノードを解決
        let branchTarget = findErrorBoundaryNode(in: ir)

        // Step 4: Opaqueパラメータを構築（具体値はVaultキーで参照）
        var params: [String: StructuralCommand.OpaqueParameter] = [:]
        if cfKind == .loop {
            // 「何回リトライするか」の具体値はVaultに隔離
            params["retry_count"] = .init(typeCategory: "int", placeholder: "VAULT:retry_count_default")
        }
        if cfKind == .timeout_wrapper {
            params["timeout_duration"] = .init(typeCategory: "duration", placeholder: "VAULT:timeout_default_seconds")
        }

        return StructuralCommand(
            operation: operation,
            targetNodeID: nodeID,
            controlFlowKind: cfKind,
            domainCategory: category,
            parameters: params,
            branchTargetNodeID: branchTarget
        )
    }

    // MARK: - Helpers

    private func extractKeyword(from text: String) -> String {
        // 日本語: 「〜の〜関数」パターンから対象を抽出
        let patterns = [
            #"「(.+?)」"#,                          // 鍵括弧内
            #"(\w+)の.*(関数|メソッド|処理)"#,     // 〇〇の関数
            #"(AppleScript|URLSession|CoreData|SwiftData|Combine|async)"#  // 既知フレームワーク
        ]
        for pattern in patterns {
            if let regex = try? NSRegularExpression(pattern: pattern),
               let match = regex.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)) {
                for i in 1..<match.numberOfRanges {
                    if let range = Range(match.range(at: i), in: text) {
                        return String(text[range])
                    }
                }
            }
        }
        // フォールバック: テキスト全体を渡す
        return text
    }

    private func findErrorBoundaryNode(in ir: JCrossIRDocument) -> String? {
        // IRの中から CTRL:error_boundary 相当のノードを探す
        for (id, node) in ir.nodes {
            if node.nodeKind == .controlBlock,
               node.controlFlow?.kind == .conditionalBranch {
                return id.raw
            }
        }
        return nil
    }
}
