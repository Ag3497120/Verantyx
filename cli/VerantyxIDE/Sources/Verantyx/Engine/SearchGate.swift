import Foundation

// MARK: - SearchGate
//
// Nano Cortex Protocol の「検索判定ゲート」。
//
// 設計思想:
//   モデルは応答の最後に SearchGate トークンを出力する。
//   スクリプト（SearchGate）がそれを解析し、必要なら検索を実行する。
//   モデル自身は検索結果を受け取らない（このターンは終了）。
//   次ターンのモデルが検索結果を near/ から自動注入で受け取る。
//
// SearchGate トークン形式（モデルが応答末尾に出力）:
//   [SEARCH_GATE: {"needs": true, "type": "memory", "query": "記憶検索ワード"}]
//   [SEARCH_GATE: {"needs": true, "type": "web",    "query": "web検索ワード"}]
//   [SEARCH_GATE: {"needs": false}]
//
// type 省略時のデフォルト: "memory"
// type="web": verantyx-browser (BrowserBridgePool) 経由で DuckDuckGo 検索し結果を注入

struct SearchGateDecision {
    let needsSearch: Bool
    let query: String
    let searchType: SearchType

    enum SearchType: String {
        case memory = "memory"
        case web    = "web"
    }
}

actor SearchGate {

    static let shared = SearchGate()
    private init() {}

    // MARK: - system prompt 追記用テキスト

    static func buildSearchGatePrompt(tier: ModelTier) -> String {
        switch tier {
        case .nano, .small:
            return """

            ## SEARCH GATE (必須)
            回答の最後の行に必ず以下のいずれかを出力してください:
            [SEARCH_GATE: {"needs": true, "type": "memory", "query": "記憶検索ワード"}]
            [SEARCH_GATE: {"needs": true, "type": "web",    "query": "web検索ワード"}]
            [SEARCH_GATE: {"needs": false}]

            使い分け:
            - type="memory": 過去の会話・個人情報が必要なとき
            - type="web":    GitHub・最新情報・外部データが必要なとき（GitHubリポジトリの状況、最新ニュース、公式ドキュメント等）
            - needs=false: 今の質問だけで十分なとき
            - query: 10語以内
            """
        case .mid, .large, .giant:
            return """

            ## SEARCH GATE
            応答の最後の行に必ず出力してください（UIには表示されません）:
            [SEARCH_GATE: {"needs": true, "type": "memory"|"web", "query": "キーワード"}]
            または [SEARCH_GATE: {"needs": false}]
            type="web" は GitHub/最新情報/外部URLが必要なとき。
            【重要】あなたの知識カットオフ（2024〜2025年）以降の話題については、推測で回答せず必ず type="web" で検索を実行してください。
            """
        }
    }

    // MARK: - 応答から SearchGate トークンをパース

    /// rawResponse から SearchGate 決定を抽出する。
    /// トークンが見つからない場合は needs=false を返す（安全デフォルト）。
    func parse(from rawResponse: String) -> SearchGateDecision {
        let pattern = #"\[SEARCH_GATE:\s*\{([^}]+)\}\]"#
        guard let regex = try? NSRegularExpression(pattern: pattern),
              let match = regex.firstMatch(
                in: rawResponse,
                range: NSRange(rawResponse.startIndex..., in: rawResponse)
              ),
              let range = Range(match.range(at: 1), in: rawResponse)
        else {
            return SearchGateDecision(needsSearch: false, query: "", searchType: .memory)
        }

        let json = "{\(rawResponse[range])}"
        guard let data = json.data(using: .utf8),
              let dict = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else {
            return SearchGateDecision(needsSearch: false, query: "", searchType: .memory)
        }

        let needs      = dict["needs"]  as? Bool   ?? false
        let query      = dict["query"]  as? String ?? ""
        let typeRaw    = dict["type"]   as? String ?? "memory"
        let searchType = SearchGateDecision.SearchType(rawValue: typeRaw) ?? .memory
        return SearchGateDecision(needsSearch: needs, query: query, searchType: searchType)
    }

    /// rawResponse から SearchGate トークンを除いたクリーンテキストを返す。
    func stripGateToken(from rawResponse: String) -> String {
        let pattern = #"\n?\[SEARCH_GATE:\s*\{[^}]+\}\]"#
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return rawResponse }
        let range = NSRange(rawResponse.startIndex..., in: rawResponse)
        return regex.stringByReplacingMatches(in: rawResponse, range: range, withTemplate: "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    // MARK: - 検索実行（memory / web 振り分け）

    @discardableResult
    func executeSearch(
        decision: SearchGateDecision,
        sessionId: String,
        turnNumber: Int,
        tier: ModelTier,
        preferredSource: BrowseSource = .safari,
        entropy: [[Double]]? = nil
    ) async -> String {
        guard decision.needsSearch, !decision.query.isEmpty else { return "" }

        switch decision.searchType {
        case .memory:
            return await executeMemorySearch(
                decision: decision, sessionId: sessionId,
                turnNumber: turnNumber, tier: tier
            )
        case .web:
            return await executeWebSearch(
                decision: decision, sessionId: sessionId,
                turnNumber: turnNumber, tier: tier,
                preferredSource: preferredSource,
                entropy: entropy
            )
        }
    }

    // MARK: - Memory Search（JCross セマンティック検索）

    private func executeMemorySearch(
        decision: SearchGateDecision,
        sessionId: String,
        turnNumber: Int,
        tier: ModelTier
    ) async -> String {
        let budget: Int
        let topK: Int
        switch tier {
        case .nano:          budget = 300;  topK = 2
        case .small:         budget = 500;  topK = 3
        case .mid:           budget = 700;  topK = 4
        case .large, .giant: budget = 1000; topK = 5
        }
        let layer: JCrossLayer = tier == .nano ? .l1 : .l2

        let searchResult = SessionMemoryArchiver.shared.semanticSearch(
            query: decision.query, topK: topK, layer: layer, budget: budget
        )
        guard !searchResult.isEmpty else { return "" }

        await updateUsedAtTags(
            searchResult: searchResult, turnNumber: turnNumber, context: decision.query
        )
        await saveSearchResult(
            sessionId: sessionId, turnNumber: turnNumber,
            query: decision.query, result: searchResult, type: "memory"
        )
        return searchResult
    }

    // MARK: - Web Search（verantyx-browser 経由）

    /// verantyx-browser (BrowserBridgePool) で DuckDuckGo 検索を実行する。
    /// WebSearchEngine.shared.search() を経由することで全ウェブ検索が
    /// verantyx-browser プール → URLSession フォールバック の共通パスを通る。
    private func executeWebSearch(
        decision: SearchGateDecision,
        sessionId: String,
        turnNumber: Int,
        tier: ModelTier,
        preferredSource: BrowseSource,
        entropy: [[Double]]? = nil
    ) async -> String {
        let query = decision.query

        let budget: Int
        switch tier {
        case .nano:          budget = 2000
        case .small:         budget = 2500
        case .mid:           budget = 3000
        case .large, .giant: budget = 4000
        }

        let result = await WebSearchEngine.shared.search(
            query: query,
            engine: .duckduckgoHTML,
            preferredSource: preferredSource,
            entropy: entropy
        )

        let bodyText = String(result.contextSnippet.prefix(budget))
        guard !bodyText.isEmpty else { return "" }

        let resultBlock = "[WEB SEARCH: \"\(String(query.prefix(60)))\"\n\(bodyText)\n[/WEB SEARCH]"

        await saveSearchResult(
            sessionId: sessionId, turnNumber: turnNumber,
            query: query, result: resultBlock, type: "web"
        )
        return resultBlock
    }

    // MARK: - 保存・タグ更新

    private func updateUsedAtTags(searchResult: String, turnNumber: Int, context: String) async {
        let wsPath = await MainActor.run { AppState.shared?.cortexWorkspacePath ?? AppState.shared?.workspaceURL?.path }
        guard let ws = wsPath else { return }
        let baseDir = URL(fileURLWithPath: ws)
        
        let zones: [URL] = [
            baseDir.appendingPathComponent(".openclaw/memory/near"),
            baseDir.appendingPathComponent(".openclaw/memory/front"),
            baseDir.appendingPathComponent(".openclaw/memory/mid"),
        ]

        let namePattern = #"TURN_[A-Za-z0-9_]+|TLSUMMARY_[A-Za-z0-9_]+|CONV_[A-Za-z0-9_]+"#
        guard let regex = try? NSRegularExpression(pattern: namePattern) else { return }
        let matches = regex.matches(
            in: searchResult, range: NSRange(searchResult.startIndex..., in: searchResult)
        )
        let names = Set(matches.compactMap {
            Range($0.range, in: searchResult).map { String(searchResult[$0]) }
        })
        guard !names.isEmpty else { return }

        for zone in zones {
            let files = (try? FileManager.default.contentsOfDirectory(
                at: zone, includingPropertiesForKeys: nil
            )) ?? []
            for file in files where file.pathExtension == "jcross" {
                let base = file.deletingPathExtension().lastPathComponent
                if names.contains(where: { base.hasPrefix($0) || $0.hasPrefix(base.prefix(20)) }) {
                    VXTimeline.shared.appendUsedAt(
                        fileURL: file, turnNumber: turnNumber, context: context
                    )
                }
            }
        }
    }

    private func saveSearchResult(
        sessionId: String, turnNumber: Int,
        query: String, result: String, type: String
    ) async {
        let wsPath = await MainActor.run { AppState.shared?.cortexWorkspacePath ?? AppState.shared?.workspaceURL?.path }
        guard let ws = wsPath else { return }
        let baseDir = URL(fileURLWithPath: ws)
        let nearDir = baseDir.appendingPathComponent(".openclaw/memory/near", isDirectory: true)
        try? FileManager.default.createDirectory(at: nearDir, withIntermediateDirectories: true)

        let ts       = Int(Date().timeIntervalSince1970)
        let prefix   = type == "web" ? "SGWEB" : "SGRESULT"
        let fileName = "\(prefix)_\(sessionId)_\(String(format: "%04d", turnNumber))_\(ts).jcross"
        let url      = nearDir.appendingPathComponent(fileName)
        let tsISO    = ISO8601DateFormatter().string(from: Date())

        let content = """
        ;;; JCross Memory Node — \(prefix)
        ;;; Session: SearchGate \(type) Result turn \(turnNumber) / \(sessionId)
        ;;; Created: \(tsISO)
        ;;; Archived: \(tsISO)

        [L1_SUMMARY]
        [SG-\(type.uppercased()) Turn \(turnNumber)] query="\(String(query.prefix(80)))"
        [/L1_SUMMARY]

        [L2_FACTS]
        OP.FACT("session_id", "\(sessionId)")
        OP.FACT("turn_number", "\(turnNumber)")
        OP.FACT("search_type", "\(type)")
        OP.FACT("search_query", "\(query.replacingOccurrences(of: "\"", with: "'"))")
        OP.STATE("node_type", "SEARCH_RESULT")
        OP.STATE("used_at", "[]")
        [/L2_FACTS]

        [L3_VERBATIM]
        Query: \(query)
        Type: \(type)

        Results:
        \(result)
        [/L3_VERBATIM]
        """

        try? content.write(to: url, atomically: true, encoding: .utf8)
    }
}

// MARK: - HTML ストリップヘルパー

private extension String {
    /// HTML タグを除去してプレーンテキストに変換する
    var htmlStripped: String {
        let tagless = self.replacingOccurrences(
            of: #"<[^>]+>"#, with: " ", options: .regularExpression
        )
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
