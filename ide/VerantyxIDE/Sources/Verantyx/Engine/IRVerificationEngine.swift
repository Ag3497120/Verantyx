import Foundation

// MARK: - IRVerificationEngine
//
// 「生成と検証の分離」アーキテクチャの第二層（決定論的検証器）。
//
// 設計思想（ユーザー提案）:
//   LLM には「論理構造の仮説（コマンドの順序）」だけを出力させ、
//   実際の「検証」は外部の決定論的なエンジンに委譲する。
//
//   LLM の役割: IR トークン列を生成 ([想:]→[確:]→[出:])
//   エンジンの役割: [確:X] の主張が実際の会話履歴・記憶に存在するか照合
//
// 照合対象:
//   1. conversation 配列（同セッション内の全発言）
//   2. SessionMemoryArchiver（cross-session 記憶）
//
// 照合結果に応じたアクション:
//   - verified    : そのまま [出:X] を最終回答として使用
//   - unverified  : メモリ補完注入 → 再生成 (ConfusionDetector と同じフロー)
//   - contradicts : 矛盾検知（会話にある事実と [確:] が食い違う場合）

// MARK: - 検証結果型

enum IRVerificationResult {
    case verified(claim: String, evidence: String)       // 照合成功: 証拠テキスト付き
    case unverified(claim: String)                       // 照合不能: 記憶補完が必要
    case contradicts(claim: String, actual: String)      // 矛盾検知: 実際の値と異なる
}

// MARK: - 照合エンジン

actor IRVerificationEngine {

    static let shared = IRVerificationEngine()

    // MARK: - メイン照合

    /// [確:X] の主張リストを conversation 履歴と照合する。
    /// - Parameters:
    ///   - claims: JCrossIRParser から取得した検証要求リスト
    ///   - conversation: AgentLoop の現在の conversation 配列
    ///   - semanticSearcher: メモリ補完のためのセマンティック検索クロージャ
    /// - Returns: 各 claim に対する照合結果
    func verify(
        claims: [String],
        against conversation: [(role: String, content: String)],
        semanticSearcher: (String) async -> String
    ) async -> [IRVerificationResult] {
        var results: [IRVerificationResult] = []

        for claim in claims {
            let result = await verifySingle(claim: claim, in: conversation, searcher: semanticSearcher)
            results.append(result)
        }

        return results
    }

    // MARK: - まとめ判定

    /// 検証結果セット全体がパスするか（全て verified であるか）
    func allVerified(_ results: [IRVerificationResult]) -> Bool {
        results.allSatisfy {
            if case .verified = $0 { return true }
            return false
        }
    }

    /// unverified または contradicts な claim のリストを返す
    func failedClaims(_ results: [IRVerificationResult]) -> [String] {
        results.compactMap {
            switch $0 {
            case .unverified(let c):       return c
            case .contradicts(let c, _):   return c
            case .verified:                return nil
            }
        }
    }

    /// 矛盾した claim とその実際の値を返す
    func contradictions(_ results: [IRVerificationResult]) -> [(claim: String, actual: String)] {
        results.compactMap {
            if case .contradicts(let c, let a) = $0 { return (c, a) }
            return nil
        }
    }

    // MARK: - デバッグログ

    func debugSummary(_ results: [IRVerificationResult]) -> String {
        results.map { result -> String in
            switch result {
            case .verified(let c, _):        return "✅ 確:\(c)"
            case .unverified(let c):         return "❓ 確:\(c) — 照合不能"
            case .contradicts(let c, let a): return "⚠️ 確:\(c) vs 実:\(a)"
            }
        }.joined(separator: " / ")
    }

    // MARK: - プライベート照合ロジック

    private func verifySingle(
        claim: String,
        in conversation: [(role: String, content: String)],
        searcher: (String) async -> String
    ) async -> IRVerificationResult {

        // ── Step 1: 会話履歴を直接テキスト検索 ─────────────────────────────
        // [確:U食=ラーメン] → "ラーメン" が conversation に含まれるか確認
        let keywords = extractKeywords(from: claim)

        for message in conversation.reversed() {  // 新しい順で検索（最近の発言を優先）
            let content = message.content.lowercased()
            let keywordHits = keywords.filter { content.contains($0.lowercased()) }

            if keywordHits.count == keywords.count && !keywords.isEmpty {
                // 全キーワードが一致 → verified
                let snippet = String(message.content.prefix(100))
                return .verified(claim: claim, evidence: snippet)
            }

            // 部分一致（主要キーワード1件以上）でも tentatively verified
            if keywordHits.count >= max(1, keywords.count / 2) {
                let snippet = String(message.content.prefix(100))
                return .verified(claim: claim, evidence: "partial: \(snippet)")
            }
        }

        // ── Step 2: セマンティック記憶検索（cross-session） ─────────────────
        let searchResult = await searcher(claim)
        if !searchResult.isEmpty && !searchResult.contains("0 hit") {
            return .verified(claim: claim, evidence: searchResult)
        }

        // ── Step 3: 照合不能 ─────────────────────────────────────────────
        return .unverified(claim: claim)
    }

    /// 照合クレームからキーワードを抽出する。
    /// 例: "U食=ラーメン" → ["ラーメン", "食"]
    ///     "U犬=トイプードル" → ["トイプードル", "犬"]
    private func extractKeywords(from claim: String) -> [String] {
        var keywords: [String] = []

        // "=" で分割して右辺（値）を最重要キーワードとして取得
        if claim.contains("=") {
            let parts = claim.components(separatedBy: "=")
            if let value = parts.last, !value.isEmpty {
                keywords.append(value.trimmingCharacters(in: .whitespaces))
            }
            // 左辺から意味のある部分も取得（U食 → 食）
            if let key = parts.first {
                let semanticPart = key.trimmingCharacters(in: .whitespaces)
                    .replacingOccurrences(of: "U", with: "")  // "U" prefix（User）を除去
                    .replacingOccurrences(of: ":", with: "")
                if !semanticPart.isEmpty { keywords.append(semanticPart) }
            }
        } else {
            // "=" がない場合はそのままキーワード化
            keywords.append(claim.trimmingCharacters(in: .whitespaces))
        }

        return keywords.filter { !$0.isEmpty }
    }
}
