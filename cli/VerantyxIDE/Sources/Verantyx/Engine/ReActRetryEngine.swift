import Foundation

// MARK: - ReActRetryEngine
//
// ReAct パターン拡張 — 検索失敗時の自律リトライ制御エンジン
//
// フロー:
//   1. Action:      エージェントが [SEARCH] / [BROWSE] / [SEARCH_MULTI] を実行
//   2. Observation: ツール結果を評価 → isSearchFailure() でチェック
//   3. Evaluation:  失敗していれば "なぜ失敗したか" を分析
//   4. Re-thought:  LLM に新しい検索クエリを生成させる
//   5. Retry:       新クエリで再試行 (最大 maxRetries 回)
//   6. Fail-safe:   maxRetries 超過 → ユーザーへ明確な失敗報告
//
// 設計方針:
//   • AgentLoop の tool 実行ループに軽量なフックとして注入する。
//   • ReAct 処理は AgentLoop の既存の while ループとは独立したサブループ。
//   • URL 直叩きをやめ SEARCH_MULTI 一本化を「Re-thought」プロンプトで強制。
//   • max_retries = 3 はバックエンド側で管理 (LLM に委任しない)。

// MARK: - ReActOutcome

enum ReActOutcome: Sendable {
    /// 成功 — 最終的な結果文字列
    case success(result: String)
    /// リトライ — 新しいクエリで再試行すべき
    case retry(newQuery: String, reason: String)
    /// 上限超過 — フェイルセーフ報告文を返す
    case exhausted(report: String)
}

// MARK: - SearchAttempt

struct SearchAttempt: Sendable {
    let attemptNumber: Int   // 1-indexed
    let query: String
    let toolResult: String
    let failureReason: String?
}

// MARK: - ReActRetryEngine

actor ReActRetryEngine {

    static let shared = ReActRetryEngine()

    /// 最大リトライ回数 (これを超えたら exhausted)
    nonisolated let maxRetries: Int = 3

    // MARK: - Public API

    /// 検索ツールの結果が失敗かどうかを判定する
    /// AgentLoop の tool 実行ループから呼ばれる
    func isSearchFailure(tool: AgentTool, result: String) -> Bool {
        // 検索・ブラウズ系ツールのみ対象
        guard isSearchTool(tool) else { return false }
        return detectFailure(in: result)
    }

    /// メインの ReAct ループ実行
    /// - Parameters:
    ///   - originalTool: 最初に失敗したツール
    ///   - firstResult:  最初のツール実行結果
    ///   - conversation: 現在の会話履歴
    ///   - callModel:    LLM 呼び出しクロージャ
    ///   - executeSearch: 新しいクエリで検索を再実行するクロージャ
    ///   - onProgress:   進捗イベント通知
    /// - Returns: 最終的な ReActOutcome
    func run(
        originalTool: AgentTool,
        firstResult: String,
        userInstruction: String,
        conversation: [(role: String, content: String)],
        callModel: @escaping @Sendable ([(role: String, content: String)]) async -> String?,
        executeSearch: @escaping @Sendable (String) async -> String,
        onProgress: @escaping @Sendable (String) async -> Void
    ) async -> ReActOutcome {

        var attempts: [SearchAttempt] = []
        var currentResult = firstResult
        var currentQuery = extractQueryFromTool(originalTool)

        for attempt in 1...maxRetries {
            let failure = detectFailure(in: currentResult) ? analyzeFailure(result: currentResult) : nil

            attempts.append(SearchAttempt(
                attemptNumber: attempt,
                query: currentQuery,
                toolResult: currentResult,
                failureReason: failure
            ))

            // 成功していれば即返却
            if failure == nil {
                return .success(result: currentResult)
            }

            // 上限に達したらフェイルセーフ
            if attempt == maxRetries {
                let report = buildExhaustionReport(
                    userInstruction: userInstruction,
                    attempts: attempts
                )
                return .exhausted(report: report)
            }

            // ── Re-thought: LLM に新クエリを生成させる ──────────────────────
            await onProgress("🔄 [ReAct] 試行 \(attempt)/\(maxRetries) 失敗: \(failure ?? "不明"). 再計画中...")

            let newQuery = await generateRethoughtQuery(
                originalInstruction: userInstruction,
                failedAttempts: attempts,
                conversation: conversation,
                callModel: callModel
            )

            await onProgress("🔍 [ReAct] 再クエリ: \"\(String(newQuery.prefix(60)))\"")

            // ── Retry: 新クエリで再実行 ─────────────────────────────────────
            currentQuery = newQuery
            currentResult = await executeSearch(newQuery)
        }

        // ここには通常到達しないが型安全のために用意
        return .exhausted(report: buildExhaustionReport(
            userInstruction: userInstruction,
            attempts: attempts
        ))
    }

    // MARK: - Failure Detection

    private func detectFailure(in result: String) -> Bool {
        let lower = result.lowercased()
        // 明示的な HTTP 4xx/5xx
        if lower.contains("http 4") || lower.contains("http 5") { return true }
        if lower.contains("❌ http") { return true }
        // 404 という文字列
        if lower.contains("404") && lower.contains("not found") { return true }
        if lower.contains("404") && lower.contains("http") { return true }
        // 空ページ
        if lower.contains("(empty page)") || lower.contains("(empty response)") { return true }
        // 汎用エラー
        if lower.hasPrefix("❌") { return true }
        // 有益な内容がない（極端に短い）
        let trimmed = result.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.count < 30 && !trimmed.isEmpty { return true }
        return false
    }

    private func analyzeFailure(result: String) -> String {
        let lower = result.lowercased()
        if lower.contains("❌ http 404") || (lower.contains("404") && lower.contains("not found")) {
            return "HTTP 404 Not Found — URLが無効またはリンク切れ"
        }
        if lower.contains("❌ http 4") { return "HTTP 4xx クライアントエラー" }
        if lower.contains("❌ http 5") { return "HTTP 5xx サーバーエラー" }
        if lower.contains("(empty page)") { return "ページが空でした" }
        if lower.contains("(empty response)") { return "レスポンスが空でした" }
        if lower.hasPrefix("❌") { return String(result.prefix(100)) }
        return "コンテンツを取得できませんでした"
    }

    // MARK: - Re-thought Query Generation

    /// LLM を使って新しい検索クエリを生成する
    /// URL直叩きを禁止し、一般キーワード検索に誘導するプロンプトを使用
    private func generateRethoughtQuery(
        originalInstruction: String,
        failedAttempts: [SearchAttempt],
        conversation: [(role: String, content: String)],
        callModel: @escaping @Sendable ([(role: String, content: String)]) async -> String?
    ) async -> String {

        let failureLog = failedAttempts.map { attempt in
            "試行\(attempt.attemptNumber): クエリ=\(attempt.query.prefix(60)) → 失敗理由=\(attempt.failureReason ?? "不明")"
        }.joined(separator: "\n")

        let rethoughtPrompt = """
        ## 検索失敗の再計画 (ReAct Re-thought Phase)

        ユーザーの要求: \(originalInstruction.prefix(200))

        以下の検索が失敗しました:
        \(failureLog)

        あなたのタスク:
        1. なぜ失敗したか分析してください。
        2. 特定のURLや特定サイトに依存しない、一般的なキーワード検索クエリを1つ生成してください。
        3. 回答は検索クエリのみを1行で出力してください。

        ルール:
        - ❌ 禁止: 特定URL (nhk.or.jp/rss など) を推測して出力すること
        - ✅ 推奨: 「トランプ大統領 最新ニュース 2025」のような一般キーワード
        - クエリは日本語または英語で。URLは含めない。

        新しい検索クエリ (1行のみ):
        """

        var rethoughtConversation = conversation
        rethoughtConversation.append((role: "user", content: rethoughtPrompt))

        guard let response = await callModel(rethoughtConversation) else {
            // LLM が応答しない場合はシンプルなフォールバック
            return buildFallbackQuery(instruction: originalInstruction)
        }

        // 応答から1行目のクエリを抽出
        let extracted = response
            .components(separatedBy: "\n")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty && !$0.hasPrefix("#") && !$0.hasPrefix("-") }
            .first ?? buildFallbackQuery(instruction: originalInstruction)

        // URL が含まれている場合はフォールバック (URLを直叩きさせない)
        if extracted.contains("http://") || extracted.contains("https://") {
            return buildFallbackQuery(instruction: originalInstruction)
        }

        return extracted
    }

    /// LLM が応答しない場合のフォールバッククエリ生成
    private func buildFallbackQuery(instruction: String) -> String {
        // instructionから日本語キーワードを抽出して汎用クエリを組み立てる
        let words = instruction
            .components(separatedBy: .whitespacesAndNewlines)
            .filter { $0.count > 1 }
            .prefix(5)
            .joined(separator: " ")
        return words.isEmpty ? "最新ニュース 今日" : "\(words) 最新情報"
    }

    // MARK: - Exhaustion Report

    private func buildExhaustionReport(
        userInstruction: String,
        attempts: [SearchAttempt]
    ) -> String {
        let attemptSummary = attempts.enumerated().map { (i, a) in
            "  試行\(i + 1): 「\(a.query.prefix(50))」→ \(a.failureReason ?? "失敗")"
        }.joined(separator: "\n")

        return """
        🔍 **検索を \(attempts.count) 回試みましたが、情報を取得できませんでした。**

        **要求**: \(userInstruction.prefix(100))

        **試行履歴**:
        \(attemptSummary)

        **提案**:
        - MCP 検索ツール (Brave Search など) が接続されていることを確認してください。
        - より具体的なキーワードで再度質問してください。
        - ネットワーク接続を確認してください。
        """
    }

    // MARK: - Helpers

    private func isSearchTool(_ tool: AgentTool) -> Bool {
        switch tool {
        case .search, .searchMulti, .browse: return true
        default: return false
        }
    }

    private func extractQueryFromTool(_ tool: AgentTool) -> String {
        switch tool {
        case .search(let q):      return q
        case .searchMulti(let q): return q
        case .browse(let url):    return url
        default:                  return ""
        }
    }
}

// MARK: - ReActRetryContext
//
// AgentLoop が各 while ループイテレーションをまたいで
// リトライ状態を追跡するための値型コンテナ。

struct ReActRetryContext: Sendable {
    /// このターンで検索失敗からリトライが発動した回数
    var retriesThisTurn: Int = 0
    /// 最後に失敗したツール
    var lastFailedTool: AgentTool? = nil
    /// ReAct ループが生成した新しいツール結果
    /// (これを TOOL RESULTS に追記してモデルに渡す)
    var injectedResult: String? = nil

    var hasRetried: Bool { retriesThisTurn > 0 }
    var isExhausted: Bool { retriesThisTurn >= 3 }

    mutating func reset() {
        retriesThisTurn = 0
        lastFailedTool = nil
        injectedResult = nil
    }
}
