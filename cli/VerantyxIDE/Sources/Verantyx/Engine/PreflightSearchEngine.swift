import Foundation

// MARK: - PreflightSearchEngine
//
// AgentLoop の事前フライトフェーズで SearchIntent に基づく複数クエリ検索を実行し、
// system prompt 注入用のグラウンディングブロックを生成するエンジン。
//
// 動作フロー（AgentLoop 内）:
//   1. SearchIntentClassifier → SearchIntent (queries[])
//   2. PreflightSearchEngine.fetch(intent) → PreflightResult
//   3. PreflightResult.systemBlock → system prompt に [PRE-FETCH RESULTS] として注入
//   4. モデルは注入された事実のみを使って回答（グラウンディング強制）
//
// 設計目標:
//   - ハルシネーション物理遮断: 検索結果にない情報は「情報なし」として明示
//   - フェイルセーフ: 全クエリ失敗時もグラウンディング指示を挿入
//   - 非ブロッキング: タイムアウト8秒、失敗は graceful degradation

// MARK: - PreflightResult

struct PreflightResult {
    let intent: SearchIntent
    let results: [(query: String, snippet: String, succeeded: Bool)]
    let executedAt: Date
    let tier: ModelTier   // ← tier-adaptive フォーマット生成のため保持

    // 成功した結果数
    var successCount: Int { results.filter(\.succeeded).count }

    // system prompt に挿入するグラウンディングブロック
    //
    // Nano/Small  → 平文箇条書き（JCross 記法はNanoが誤読するため使用しない）
    // Large/Giant → JCross トライレイヤー（L1/L2/L3 フル構造）
    //
    // グラウンディング指示は両フォーマットとも先頭の INSTRUCTION 行に明示。

    var systemBlock: String {
        let tsISO    = ISO8601DateFormatter().string(from: executedAt)
        let hasResults = results.contains(where: { $0.succeeded && !$0.snippet.isEmpty })
        let isNano   = (tier == .nano || tier == .small)

        if isNano {
            return nanoSystemBlock(tsISO: tsISO, hasResults: hasResults)
        } else {
            return jcrossSystemBlock(tsISO: tsISO, hasResults: hasResults)
        }
    }

    // ── Nano/Small: 平文箇条書きフォーマット ────────────────────────────────
    //
    // JCross の OP.FACT / [L1] タグなどはNanoが無視するため、
    // 直接読める平文で「今日のニュース:」「・項目」形式で提示する。
    // INSTRUCTION 行を最初に置くことで、モデルが最初に制約を読む。

    private func nanoSystemBlock(tsISO: String, hasResults: Bool) -> String {
        let topicLabel = String(describing: intent.intentType)
            .replacingOccurrences(of: "newsEvent(topic: ", with: "")
            .replacingOccurrences(of: ")", with: "")

        guard hasResults else {
            return """
            [PRE-FETCH RESULTS — 取得失敗]
            INSTRUCTION: 検索で情報を取得できませんでした。「最新情報を確認できませんでした」とユーザーに伝えてください。学習データから推測して補完することは禁止します。
            取得試行クエリ: \(intent.queries.prefix(2).joined(separator: " / "))
            取得時刻: \(tsISO)
            """
        }

        let bullets = results
            .filter { $0.succeeded && !$0.snippet.isEmpty }
            .enumerated()
            .map { i, r in
                let clean = r.snippet
                    .replacingOccurrences(of: #"<[^>]+>"#, with: " ", options: .regularExpression)
                    .replacingOccurrences(of: #"\s+"#,    with: " ", options: .regularExpression)
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                return "【情報\(i+1)】\(String(clean.prefix(1000)))"
            }
            .joined(separator: "\n\n")

        return """
        [PRE-FETCH RESULTS — \(topicLabel) / \(tsISO)]
        INSTRUCTION: 以下の情報のみを根拠として回答してください。この情報に含まれていない事実は「確認できませんでした」と答えてください。自分の学習データからの補完は禁止です。

        \(bullets)
        [/PRE-FETCH RESULTS]
        """
    }

    // ── Large/Giant: JCross トライレイヤーフォーマット ───────────────────────

    private func jcrossSystemBlock(tsISO: String, hasResults: Bool) -> String {
        let queryList = intent.queries.prefix(3).enumerated()
            .map { i, q in "OP.FACT(\"query_\(i+1)\", \"\(q.replacingOccurrences(of: "\"", with: "'"))\")" }
            .joined(separator: "\n")

        if hasResults {
            // ── L2: 各クエリの結果ファクト ──────────────────────────────────
            let resultFacts = results
                .filter { $0.succeeded && !$0.snippet.isEmpty }
                .enumerated()
                .map { i, r -> String in
                    let safe = r.snippet
                        .replacingOccurrences(of: "\"", with: "'")
                        .replacingOccurrences(of: "\n", with: " ")
                    let q    = r.query.replacingOccurrences(of: "\"", with: "'")
                    return """
                    OP.ENTITY("source_\(i+1)", "\(q)")
                    OP.FACT("result_\(i+1)", "\(String(safe.prefix(1200)))")
                    """
                }
                .joined(separator: "\n")

            // ── L3: 生スニペット ─────────────────────────────────────────────
            let verbatim = results
                .filter { $0.succeeded && !$0.snippet.isEmpty }
                .enumerated()
                .map { i, r in "### [\(i+1)] \(r.query)\n\(r.snippet)" }
                .joined(separator: "\n\n")

            return """
            ;;; JCross Pre-flight Grounding Node
            ;;; Fetched: \(tsISO)  Queries: \(results.count)  Succeeded: \(successCount)

            [L1 空間座相]
            \(intent.kanjiTopologyTags)
            [/L1]

            [L2 位相対応表]
            \(queryList)
            \(resultFacts)
            OP.FACT("fetch_timestamp", "\(tsISO)")
            OP.STATE("search_status", "SUCCESS:\(successCount)/\(results.count)")
            OP.STATE("grounding_rule", "このL3原文に存在しない事実は断言しないこと。情報が見つからない場合は「検索で確認できませんでした」と明示する。学習データからの推測による補完は禁止（ハルシネーション遮断）。")
            [/L2]

            [L3 原文]
            \(verbatim)
            [/L3]
            """
        } else {
            // ── 全クエリ失敗 → フェイルセーフ JCross ノード ──────────────────
            return """
            ;;; JCross Pre-flight Grounding Node — SEARCH FAILED
            ;;; Fetched: \(tsISO)

            [L1 空間座相]
            \(intent.kanjiTopologyTags)
            [/L1]

            [L2 位相対応表]
            \(queryList)
            OP.FACT("fetch_timestamp", "\(tsISO)")
            OP.STATE("search_status", "FAILED:0/\(results.count)")
            OP.STATE("grounding_rule", "検索エンジンから有効な情報を取得できなかった。回答する際は「私の知識カットオフ時点での情報です」と明記し、最新状況については断言しないこと。推測補完禁止。")
            [/L2]

            [L3 原文]
            （検索結果なし — クエリ: \(intent.queries.joined(separator: " / "))）
            [/L3]
            """
        }
    }

    // AgentLoop の onProgress 表示用ラベル
    var progressLabel: String {
        let queryList = intent.queries.prefix(2).map { "「\(String($0.prefix(35)))」" }.joined(separator: " + ")
        return "\(intent.displayLabel) → \(successCount)/\(results.count) クエリ成功: \(queryList)"
    }

}

// MARK: - PreflightSearchEngine

actor PreflightSearchEngine {

    static let shared = PreflightSearchEngine()
    private init() {}

    // MARK: - メインエントリポイント

    /// SearchIntent に従って最大 3 クエリを並列実行し、結果をマージして返す。
    func fetch(intent: SearchIntent, tier: ModelTier) async -> PreflightResult {
        guard intent.needsExternalSearch, !intent.queries.isEmpty else {
            return PreflightResult(intent: intent, results: [], executedAt: Date(), tier: tier)
        }

        // 並列でクエリを実行（Structured Concurrency）
        let queryResults = await withTaskGroup(of: (String, String, Bool).self) { group in
            for query in intent.queries.prefix(3) {
                group.addTask {
                    let snippet = await self.fetchSingleQuery(query: query, intent: intent, tier: tier)
                    return (query, snippet, !snippet.isEmpty)
                }
            }
            var collected: [(String, String, Bool)] = []
            for await r in group { collected.append(r) }
            return collected
        }

        // クエリの元の順序を保持して返す
        let ordered = intent.queries.prefix(3).compactMap { q in
            queryResults.first(where: { $0.0 == q })
        }.map { (query: $0.0, snippet: $0.1, succeeded: $0.2) }

        return PreflightResult(intent: intent, results: ordered, executedAt: Date(), tier: tier)
    }

    // MARK: - 単一クエリ実行
    //
    // ルーティング優先度:
    //   1. site:github.com/user/repo → https://github.com/user/repo に変換して
    //      verantyx-browser で直接取得（REST API をメタデータ補完として追加）
    //   2. https?:// URL → verantyx-browser で直接取得
    //      （github.com の場合は REST API メタデータも補完）
    //   3. 汎用テキストクエリ → verantyx-browser 経由 DDG 検索
    //   4. すべて失敗 → ""

    private func fetchSingleQuery(
        query: String,
        intent: SearchIntent,
        tier: ModelTier
    ) async -> String {
        let budget = snippetBudget(for: tier)

        // ── site:github.com/user/repo → verantyx-browser で直接取得 ───────
        // "site:github.com/MemPalace/mempalace" → "https://github.com/MemPalace/mempalace"
        if query.lowercased().hasPrefix("site:github.com") {
            let path = query
                .replacingOccurrences(of: "site:github.com", with: "", options: .caseInsensitive)
                .trimmingCharacters(in: .whitespaces)

            let githubURL = path.hasPrefix("http") ? path : "https://github.com/\(path)"
            let browserResult = await WebSearchEngine.shared.browse(
                url: githubURL, preferredSource: .safari
            )
            var text = String(browserResult.contextSnippet.prefix(budget))

            // REST API のスター数・言語等メタデータを補完
            if !path.isEmpty, let apiMeta = await fetchGitHubAPI(projectName: path, tier: tier) {
                text += "\n\n[GitHub API Meta]\n\(String(apiMeta.prefix(max(300, budget / 3))))"
            }
            return text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "" : text
        }

        // ── https?:// URL 直接参照 → verantyx-browser ─────────────────────
        if query.hasPrefix("http://") || query.hasPrefix("https://") {
            if query.lowercased().contains("github.com/") {
                let browserResult = await WebSearchEngine.shared.browse(
                    url: query, preferredSource: .safari
                )
                var text = String(browserResult.contextSnippet.prefix(budget))
                let path = query
                    .replacingOccurrences(of: "https://github.com/", with: "", options: .caseInsensitive)
                    .replacingOccurrences(of: "http://github.com/",  with: "", options: .caseInsensitive)
                if !path.isEmpty, let apiMeta = await fetchGitHubAPI(projectName: path, tier: tier) {
                    text += "\n\n[GitHub API Meta]\n\(String(apiMeta.prefix(300)))"
                }
                return text.isEmpty ? "" : text
            }
            let result = await WebSearchEngine.shared.browse(url: query, preferredSource: .safari)
            return String(result.contextSnippet.prefix(budget))
        }

        // ── 汎用テキストクエリ → verantyx-browser 経由 Google 検索 ────────────
        let result = await WebSearchEngine.shared.search(
            query: query,
            engine: .google,
            preferredSource: .safari
        )
        let text = String(result.contextSnippet.prefix(budget))
        return text.isEmpty || text.hasPrefix("❌") ? "" : text
    }

    // MARK: - GitHub REST API（主力ソース）

    /// GitHub Search API + Repositories API を使ってプロジェクト情報を取得する。
    /// 認証不要（unauthenticated: 10 req/min）。ボット検知なし。JSON 構造化データ。
    private func fetchGitHubAPI(projectName: String, tier: ModelTier) async -> String? {
        let budget = snippetBudget(for: tier)

        // ① "user/repo" 形式なら直接 /repos エンドポイント
        let parts = projectName.components(separatedBy: "/")
        if parts.count == 2 {
            let owner = parts[0], repo = parts[1]
            if let text = await fetchGitHubRepo(owner: owner, repo: repo, budget: budget) {
                return text
            }
        }

        // ② プロジェクト名で検索
        let encoded = projectName.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? projectName
        let searchURL = "https://api.github.com/search/repositories?q=\(encoded)&sort=stars&per_page=3"
        guard let url = URL(string: searchURL) else { return nil }

        var req = URLRequest(url: url, timeoutInterval: 10)
        req.setValue("application/vnd.github.v3+json", forHTTPHeaderField: "Accept")
        req.setValue("VerantyxIDE/1.0 (macOS)", forHTTPHeaderField: "User-Agent")

        guard let (data, resp) = try? await URLSession.shared.data(for: req),
              let http = resp as? HTTPURLResponse, http.statusCode == 200 else { return nil }

        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let items = json["items"] as? [[String: Any]],
              !items.isEmpty else { return nil }

        // 最上位マッチの詳細を取得
        var parts2: [String] = []
        for item in items.prefix(2) {
            let fullName    = item["full_name"]    as? String ?? ""
            let desc        = item["description"]  as? String ?? "（説明なし）"
            let stars       = item["stargazers_count"] as? Int ?? 0
            let forks       = item["forks_count"]  as? Int ?? 0
            let lang        = item["language"]     as? String ?? "不明"
            let pushed      = item["pushed_at"]    as? String ?? ""
            let openIssues  = item["open_issues_count"] as? Int ?? 0
            let archived    = item["archived"]     as? Bool ?? false
            let htmlURL     = item["html_url"]     as? String ?? ""
            let topics      = item["topics"]       as? [String] ?? []

            let archivedNote = archived ? "⚠️ アーカイブ済み" : "✅ アクティブ"
            let topicStr     = topics.isEmpty ? "" : "\nトピック: \(topics.prefix(5).joined(separator: ", "))"
            let pushedNote   = pushed.isEmpty ? "" : "\n最終プッシュ: \(pushed.prefix(10))"

            parts2.append("""
            ## \(fullName) (\(archivedNote))
            \(htmlURL)
            説明: \(desc)
            言語: \(lang) | ⭐ \(stars) | 🍴 \(forks) | 未解決Issue: \(openIssues)\(pushedNote)\(topicStr)
            """)
        }

        // 最上位リポジトリの詳細 README 取得を試みる（best-effort）
        if let firstItem = items.first,
           let fullName = firstItem["full_name"] as? String {
            let ownerRepo = fullName.components(separatedBy: "/")
            if ownerRepo.count == 2,
               let readme = await fetchGitHubReadme(owner: ownerRepo[0], repo: ownerRepo[1]) {
                parts2.append("### README（抜粋）\n\(String(readme.prefix(600)))")
            }
        }

        let result = parts2.joined(separator: "\n\n")
        return String(result.prefix(budget))
    }

    /// 特定リポジトリの詳細情報を取得する。
    private func fetchGitHubRepo(owner: String, repo: String, budget: Int) async -> String? {
        let urlStr = "https://api.github.com/repos/\(owner)/\(repo)"
        guard let url = URL(string: urlStr) else { return nil }

        var req = URLRequest(url: url, timeoutInterval: 10)
        req.setValue("application/vnd.github.v3+json", forHTTPHeaderField: "Accept")
        req.setValue("VerantyxIDE/1.0 (macOS)", forHTTPHeaderField: "User-Agent")

        guard let (data, resp) = try? await URLSession.shared.data(for: req),
              let http = resp as? HTTPURLResponse, http.statusCode == 200,
              let item = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return nil }

        let desc       = item["description"]       as? String ?? "（説明なし）"
        let stars      = item["stargazers_count"]  as? Int ?? 0
        let forks      = item["forks_count"]       as? Int ?? 0
        let lang       = item["language"]          as? String ?? "不明"
        let pushed     = item["pushed_at"]         as? String ?? ""
        let issues     = item["open_issues_count"] as? Int ?? 0
        let archived   = item["archived"]          as? Bool ?? false
        let htmlURL    = item["html_url"]          as? String ?? ""
        let license    = (item["license"] as? [String: Any])?["spdx_id"] as? String ?? "なし"
        let watchers   = item["watchers_count"]    as? Int ?? 0

        let archivedNote = archived ? "⚠️ アーカイブ済み" : "✅ アクティブ"
        let summary = """
        ## \(owner)/\(repo) (\(archivedNote))
        \(htmlURL)
        説明: \(desc)
        言語: \(lang) | ⭐ \(stars) | 🍴 \(forks) | 👁 \(watchers) | Issue: \(issues)
        ライセンス: \(license) | 最終プッシュ: \(pushed.prefix(10))
        """

        var parts = [summary]
        if let readme = await fetchGitHubReadme(owner: owner, repo: repo) {
            parts.append("### README（抜粋）\n\(String(readme.prefix(400)))")
        }
        return String(parts.joined(separator: "\n\n").prefix(budget))
    }

    /// GitHub README を取得してプレーンテキストに変換する。
    private func fetchGitHubReadme(owner: String, repo: String) async -> String? {
        let urlStr = "https://api.github.com/repos/\(owner)/\(repo)/readme"
        guard let url = URL(string: urlStr) else { return nil }

        var req = URLRequest(url: url, timeoutInterval: 8)
        req.setValue("application/vnd.github.raw+json", forHTTPHeaderField: "Accept")
        req.setValue("VerantyxIDE/1.0 (macOS)", forHTTPHeaderField: "User-Agent")

        guard let (data, resp) = try? await URLSession.shared.data(for: req),
              let http = resp as? HTTPURLResponse, http.statusCode == 200 else { return nil }

        // raw README (Markdown) → 先頭 600 文字だけ返す
        if let raw = String(data: data, encoding: .utf8), !raw.isEmpty {
            return raw
        }
        // fallback: base64 JSON レスポンス
        if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let b64  = json["content"] as? String,
           let decoded = Data(base64Encoded: b64.filter { !$0.isWhitespace }) {
            return String(data: decoded, encoding: .utf8)
        }
        return nil
    }

    // MARK: - Tier 別文字数上限

    private func snippetBudget(for tier: ModelTier) -> Int {
        switch tier {
        case .nano:          return 3000   // RSS/JSON はプレーンテキスト → 多く取れる
        case .small:         return 2000
        case .mid:           return 2400
        case .large, .giant: return 3600
        }
    }
}

// MARK: - HTML ストリップヘルパー (SearchGate.swift と共用定義を避けるため private extension で定義)

private extension String {
    var htmlStripped: String {
        let tagless = self.replacingOccurrences(of: #"<[^>]+>"#, with: " ", options: .regularExpression)
        return tagless
            .replacingOccurrences(of: "&amp;",  with: "&")
            .replacingOccurrences(of: "&lt;",   with: "<")
            .replacingOccurrences(of: "&gt;",   with: ">")
            .replacingOccurrences(of: "&quot;", with: "\"")
            .replacingOccurrences(of: "&#39;",  with: "'")
            .replacingOccurrences(of: "&nbsp;", with: " ")
            .replacingOccurrences(of: #"\s+"#,  with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

// MARK: - IgnoranceRouter
/// Nano Cortex Protocol - Ignorance Router
/// 2Bモデル（Nano）を「無知の検出器」として利用し、メインモデル（26B等）に渡す前の
/// 事前フライト検索用クエリを生成するルーティング層。
actor IgnoranceRouter {

    static let shared = IgnoranceRouter()
    private init() {}

    /// Ollama でロード可能な Nano モデル（2Bクラス）を探す
    private func detectNanoModel() async -> String? {
        let models = await OllamaClient.shared.listModels()
        // gemma4:e2b, gemma-2b などを優先
        let nanoKeywords = ["e2b", ":2b", "-2b", "nano", "mini", "gemma2b"]
        for keyword in nanoKeywords {
            if let found = models.first(where: { $0.lowercased().contains(keyword) }) {
                return found
            }
        }
        return nil
    }

    /// ユーザーの指示文に対し、Nano モデルが「自分の知識で回答可能か」を判断し、
    /// 知識がない場合は「検索の必要性を示す文章」をユーザーの質問文に付与して返す。
    /// 回答可能な場合は nil を返す（元の質問のまま）。
    func evaluate(instruction: String) async -> String? {
        guard let nanoModel = await detectNanoModel() else {
            return nil
        }

        let systemPrompt = """
        [核:無知検出] [職:Router] [標:JSON出力のみ] [禁:回答生成]
        あなたは知識の限界を判定するルーターです。
        ユーザーの質問に対して、あなたの貧弱な知識（2Bパラメータ相当）で自信を持って答えられない場合、
        または最新情報や特定の事実確認が必要な場合は、必ず検索クエリを生成してください。
        答えられる場合は needs_search を false にしてください。
        
        OUTPUT FORMAT (JSON ONLY):
        {
          "needs_search": true or false,
          "query": "search keywords"
        }
        """

        let prompt = "User Query: \(instruction)"

        print(AppLanguage.shared.t("🧠 [IgnoranceRouter] Requesting ignorance check from 2B model (\\(nanoModel))...", "🧠 [IgnoranceRouter] 2Bモデル (\\(nanoModel)) に無知判定を依頼中..."))
        let response = await OllamaClient.shared.generate(
            model: nanoModel,
            prompt: "\(systemPrompt)\n\n\(prompt)",
            maxTokens: 50,
            temperature: 0.1
        )

        guard let text = response else { return nil }

        // JSON部分を抽出
        guard let jsonStart = text.firstIndex(of: "{"),
              let jsonEnd = text.lastIndex(of: "}") else {
            return nil
        }
        
        let jsonStr = String(text[jsonStart...jsonEnd])
        guard let data = jsonStr.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return nil
        }

        let needsSearch = json["needs_search"] as? Bool ?? false
        if needsSearch, let query = json["query"] as? String, !query.isEmpty {
            print(AppLanguage.shared.t("🧠 [IgnoranceRouter] 2B model detected unknown concept. Instructing 26B to search.", "🧠 [IgnoranceRouter] 2Bモデルが未知の概念を検出。26Bに検索を指示します。"))
            // 26Bモデルに検索を強制する文章を付加する
            let mcpTools = await MainActor.run { MCPEngine.shared.connectedTools }
            var overrideText = """
            [ROUTER OVERRIDE]
            This query contains concepts or recent information that require external knowledge.
            You MUST use a Search tool using the query: "\(query)" before attempting to answer.
            Do NOT rely on your internal knowledge.
            """

            if !mcpTools.isEmpty {
                let serverNames = Array(Set(mcpTools.map { $0.serverName })).joined(separator: ", ")
                overrideText += "\nIMPORTANT: You have connected MCP tools (\(serverNames)). You MUST prioritize using [MCP_CALL] for search over the default [SEARCH] tool."
            }
            
            return """
            \(overrideText)
            
            USER QUERY:
            \(instruction)
            """
        } else {
            print(AppLanguage.shared.t("🧠 [IgnoranceRouter] 2B model: Search not required.", "🧠 [IgnoranceRouter] 2Bモデル: 検索不要と判定。"))
            return nil
        }
    }
}
