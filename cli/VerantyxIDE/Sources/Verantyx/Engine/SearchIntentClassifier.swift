import Foundation

// MARK: - SearchIntent
//
// ユーザープロンプトから抽出された「検索意図」の構造体。
// SearchIntentClassifier が生成し、AgentLoop の事前フライト検索で利用される。
//
// 設計原則:
//   LLM呼び出し不要 — 正規表現とキーワードマッチングで高速分類 (<5ms)
//   複数クエリ生成 — 包括的な情報収集のため最大3クエリを生成
//   鮮度判定 — 「現在」「最新」などのキーワードで外部検索必要性を強化

struct SearchIntent {

    // MARK: - 意図タイプ

    enum IntentType {
        case githubProject(name: String)       // GitHub リポジトリ参照
        case websiteURL(url: String)           // 直接 URL 参照
        case weather(location: String)         // 天気情報
        case newsEvent(topic: String)          // ニュース・最新情報
        case documentation(tech: String)       // 公式ドキュメント参照
        case general(topic: String)            // 汎用外部情報
        case noSearch                          // 検索不要
    }

    let needsExternalSearch: Bool
    let queries: [String]                      // 最大3クエリ（優先度順）
    let intentType: IntentType
    let freshnessCritical: Bool                // 「現在・最新」系キーワードを検出

    // ─── 静的デフォルト ───────────────────────────────────────────────────

    static let noSearch = SearchIntent(
        needsExternalSearch: false,
        queries: [],
        intentType: .noSearch,
        freshnessCritical: false
    )

    // ─── UI 表示用ラベル ──────────────────────────────────────────────────

    var displayLabel: String {
        switch intentType {
        case .githubProject(let name): return "🔍 GitHub: \(name)"
        case .websiteURL(let url):     return "🌐 URL: \(url.prefix(50))"
        case .weather(let loc):        return "☀️ 天気: \(loc.prefix(30))"
        case .newsEvent(let topic):    return "📰 ニュース: \(topic.prefix(40))"
        case .documentation(let t):    return "📚 ドキュメント: \(t.prefix(40))"
        case .general(let t):          return "🌐 Web検索: \(t.prefix(40))"
        case .noSearch:                return ""
        }
    }

    // ─── JCross 漢字トポロジータグ ────────────────────────────────────────
    //
    // 意図タイプに応じて L1 漢字座標ベクトルを返す。
    // JCross ARC-SGI Gravity Z-Depth アルゴリズムで検索ノードを空間配置するために使用。
    //
    // 命名規則:
    //   最高重み 1.0 = 主概念（何について）
    //   0.9       = 行為・状態（何をする）
    //   0.8       = 文脈・属性（どういう文脈か）
    //   0.7       = 鮮度補正（freshnessCritical == true の場合に加算）

    var kanjiTopologyTags: String {
        let freshnessTag = freshnessCritical ? " [新:0.75] [時:0.7]" : ""
        switch intentType {
        case .githubProject:
            return "[技:1.0] [開:0.9] [版:0.85] [証:0.8] [存:0.75]\(freshnessTag)"
        case .websiteURL:
            return "[網:1.0] [参:0.9] [照:0.85] [証:0.8] [外:0.75]\(freshnessTag)"
        case .weather:
            // 天=天気, 気=気象, 地=地域, 時=時刻, 予=予報
            return "[天:1.0] [気:0.95] [地:0.85] [時:0.8] [予:0.75]"
        case .newsEvent:
            return "[報:1.0] [新:0.95] [時:0.85] [証:0.8] [変:0.7]\(freshnessTag)"
        case .documentation:
            return "[書:1.0] [式:0.9] [技:0.85] [証:0.8] [参:0.75]\(freshnessTag)"
        case .general:
            return "[検:1.0] [情:0.9] [証:0.85] [外:0.8] [新:0.75]\(freshnessTag)"
        case .noSearch:
            return ""
        }
    }
}

// MARK: - SearchIntentClassifier
//
// AgentLoop の事前フライトフェーズで呼び出される意図分類エンジン。
// ユーザー入力を解析して検索クエリのセットを生成する。
//
// 呼び出しタイミング:
//   AgentLoop.run() → while true の「前」に1回だけ実行
//   → 結果を system prompt に [PRE-FETCH RESULTS] として注入

actor SearchIntentClassifier {

    static let shared = SearchIntentClassifier()
    private init() {}

    // MARK: - 主エントリポイント

    func classify(userPrompt: String) -> SearchIntent {
        let prompt = userPrompt.trimmingCharacters(in: .whitespacesAndNewlines)
        let lower  = prompt.lowercased()

        // 優先度順に分類を試みる
        if let intent = classifyWeather(prompt: prompt, lower: lower)       { return intent } // 必ずnewsの前に
        if let intent = classifyGitHub(prompt: prompt, lower: lower)        { return intent }
        if let intent = classifyDirectURL(prompt: prompt, lower: lower)     { return intent }
        if let intent = classifyNews(prompt: prompt, lower: lower)          { return intent }
        if let intent = classifyDocumentation(prompt: prompt, lower: lower) { return intent }
        if hasFreshnessKeywords(lower) {
            let topic   = extractMainTopic(from: prompt)
            let queries = [topic, "\(topic) 最新情報", "\(topic) latest"].filter { !$0.isEmpty }
            return SearchIntent(
                needsExternalSearch: true,
                queries: Array(queries.prefix(3)),
                intentType: .general(topic: topic),
                freshnessCritical: true
            )
        }
        return .noSearch
    }

    // MARK: - 天気分類（newsEvent より先に評価する）

    private func classifyWeather(prompt: String, lower: String) -> SearchIntent? {
        let weatherKeywords = [
            "天気", "気温", "降水", "雨", "晴れ", "曇り", "雪", "台風", "気象",
            "weather", "forecast", "temperature", "rain", "sunny",
            "最高気温", "最低気温", "湿度", "風速", "予報",
        ]
        guard weatherKeywords.contains(where: { lower.contains($0) }) else { return nil }

        // 地名を抽出（市区町村・都道府県・国名）
        let location = extractWeatherLocation(from: prompt, lower: lower)
        let timeLabel = extractWeatherTimeLabel(from: lower) // "今日", "明日", "今週" 等

        // verantyx-browser で直接取得する天気サイト URL を生成
        let encoded   = location.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? location
        let tenki     = "https://tenki.jp/search/?keyword=\(encoded)"
        let yahoo     = "https://weather.yahoo.co.jp/weather/search/?p=\(encoded)"
        let ddgQuery  = "\(location) \(timeLabel)天気 予報"

        return SearchIntent(
            needsExternalSearch: true,
            queries: [tenki, yahoo, ddgQuery],
            intentType: .weather(location: "\(timeLabel)\(location)"),
            freshnessCritical: true
        )
    }

    private func extractWeatherLocation(from prompt: String, lower: String) -> String {
        // 都道府県・市区町村パターン
        let patterns = [
            #"([^\s　、。]+(?:都|道|府|県|市|区|町|村|島))"#,
            #"([a-zA-Z][a-zA-Z\s]{2,20})(?:\s+(?:city|prefecture|town))?"#,
        ]
        for pattern in patterns {
            if let re = try? NSRegularExpression(pattern: pattern),
               let m  = re.firstMatch(in: prompt, range: NSRange(prompt.startIndex..., in: prompt)),
               let r  = Range(m.range(at: 1), in: prompt) {
                let loc = String(prompt[r]).trimmingCharacters(in: .whitespacesAndNewlines)
                if !loc.isEmpty { return loc }
            }
        }
        // フォールバック: 天気系ワードを除いた主トピック
        return extractMainTopic(from: prompt)
    }

    private func extractWeatherTimeLabel(from lower: String) -> String {
        if lower.contains("今日") || lower.contains("today")   { return "今日の" }
        if lower.contains("明日") || lower.contains("tomorrow") { return "明日の" }
        if lower.contains("明後日")                              { return "明後日の" }
        if lower.contains("今週") || lower.contains("this week") { return "今週の" }
        if lower.contains("週間") || lower.contains("weekly")   { return "週間" }
        return ""
    }

    // MARK: - GitHub プロジェクト分類

    private func classifyGitHub(prompt: String, lower: String) -> SearchIntent? {
        // ① github.com/user/repo 形式の URL
        let urlPattern = #"github\.com/([a-zA-Z0-9_\-\.]+/[a-zA-Z0-9_\-\.]+)"#
        if let regex = try? NSRegularExpression(pattern: urlPattern, options: .caseInsensitive),
           let match = regex.firstMatch(in: prompt, range: NSRange(prompt.startIndex..., in: prompt)),
           let r = Range(match.range(at: 1), in: prompt) {
            let repoPath = String(prompt[r])
            let name     = repoPath.components(separatedBy: "/").last ?? repoPath
            return buildGitHubIntent(repoPath: repoPath, projectName: name)
        }

        // ② "〇〇 github" / "githubの〇〇" / "〇〇リポジトリ" パターン
        let ghKeywords = ["github", "ギットハブ", "リポジトリ", "repository", "repo"]
        guard ghKeywords.contains(where: { lower.contains($0) }) else { return nil }

        // プロジェクト名を抽出する正規表現パターン群（優先度順）
        let namePatterns = [
            #"「([^」]+)」[^\w]*(?:という|の)?(?:github|リポジトリ)"#,
            #""([^"]+)"[^\w]*(?:github|リポジトリ)"#,
            #"([a-zA-Z][a-zA-Z0-9_\-]{2,30})[^\w]*(?:という|の)?(?:github|githubプロジェクト|リポジトリ|repository|repo)"#,
            #"(?:github|リポジトリ)[^\w（(]*(?:の|プロジェクト|project)?[^\w（(「"]*([a-zA-Z][a-zA-Z0-9_\-]{2,30})"#,
            // 日本語名（カタカナ・ひらがな含む固有名詞）
            #"([ァ-ヶー一-龥a-zA-Z][ァ-ヶー一-龥a-zA-Z0-9_\-]{2,30})[^\w]*(?:という|の)?(?:github|リポジトリ)"#,
        ]
        for pattern in namePatterns {
            if let regex = try? NSRegularExpression(pattern: pattern, options: .caseInsensitive),
               let match = regex.firstMatch(in: prompt, range: NSRange(prompt.startIndex..., in: prompt)),
               match.numberOfRanges > 1,
               let r = Range(match.range(at: 1), in: prompt) {
                let name = String(prompt[r]).trimmingCharacters(in: .whitespacesAndNewlines)
                if !name.isEmpty && name.count > 1 {
                    return buildGitHubIntent(repoPath: nil, projectName: name)
                }
            }
        }

        // プロジェクト名が特定できなかった場合: 汎用 GitHub 検索
        let topic = extractMainTopic(from: prompt)
        return SearchIntent(
            needsExternalSearch: true,
            queries: ["site:github.com \(topic)", "github \(topic)"],
            intentType: .githubProject(name: topic),
            freshnessCritical: hasFreshnessKeywords(lower)
        )
    }

    private func buildGitHubIntent(repoPath: String?, projectName: String) -> SearchIntent {
        var queries: [String]
        if let path = repoPath {
            queries = [
                "site:github.com/\(path)",
                "github \(projectName) release notes OR changelog",
                "\(projectName) github project status commits",
            ]
        } else {
            queries = [
                "site:github.com \(projectName)",
                "github.com \(projectName) repository README",
                "\(projectName) github recent activity stars",
            ]
        }
        return SearchIntent(
            needsExternalSearch: true,
            queries: Array(queries.prefix(3)),
            intentType: .githubProject(name: projectName),
            freshnessCritical: true
        )
    }

    // MARK: - 直接 URL 参照

    private func classifyDirectURL(prompt: String, lower: String) -> SearchIntent? {
        let urlPattern = #"https?://[^\s\u3000-\u303F\uff00-\uffef]+"#
        guard let regex = try? NSRegularExpression(pattern: urlPattern),
              let match = regex.firstMatch(in: prompt, range: NSRange(prompt.startIndex..., in: prompt)),
              let r = Range(match.range, in: prompt) else { return nil }
        let url = String(prompt[r]).trimmingCharacters(in: CharacterSet(charactersIn: "。、．，）)」』"))
        return SearchIntent(
            needsExternalSearch: true,
            queries: [url],
            intentType: .websiteURL(url: url),
            freshnessCritical: hasFreshnessKeywords(lower)
        )
    }

    // MARK: - ニュース・最新情報（時刻分解エンジン搭載）

    // 「現在」「今日」「今週」などのキーワードを実時刻に変換してクエリを精密化する。
    // 例: "今日のイラン情勢" → topic="イラン情勢", date="2026年4月25日"
    //     → クエリ = ["イラン情勢 2026年4月25日", "イラン情勢 site:nhk.or.jp 2026", ...]

    private func classifyNews(prompt: String, lower: String) -> SearchIntent? {
        let newsKeywords = [
            // 日本語ニュース系
            "ニュース", "最新", "最近", "今日", "今週", "今月", "今年",
            "現在", "情勢", "状況", "速報", "記事",
            "発表", "リリース", "アップデート", "新機能", "障害",
            "戦争", "事件", "問題",
            // 英語
            "news", "latest", "recent", "today", "current",
            "announcement", "release", "update", "outage",
        ]
        guard newsKeywords.contains(where: { lower.contains($0) }) else { return nil }

        let topic = extractMainTopic(from: prompt)
        // topic が空の場合（「ニュースを教えて」のような汎用クエリ）も NHK RSS で対応
        let topicLabel = topic.isEmpty ? "最新ニュース" : topic

        // ── 時刻分解: 現在日時を取得してクエリに埋め込む ──────────────────────
        let temporalCtx = buildTemporalQueryContext(from: lower)

        // q1: NHK RSS URL（直接取得・JS不要・常に成功する最優先ソース）
        // q2: トピック+日付でDDG検索（ブラウザが動く場合の精密クエリ）
        // q3: 英語国際ニュース
        let nhkRssURL = "https://www3.nhk.or.jp/rss/news/cat0.xml"
        let q1 = nhkRssURL
        let q2 = "\(topicLabel) \(temporalCtx.dateLabel)"
        let q3 = "\(topicLabel) \(temporalCtx.yearLabel) \(temporalCtx.monthLabel) news"

        return SearchIntent(
            needsExternalSearch: true,
            queries: [q1, q2, q3],
            intentType: .newsEvent(topic: topicLabel),
            freshnessCritical: true
        )
    }

    // ── 時刻分解コンテキスト ──────────────────────────────────────────────────

    private struct TemporalContext {
        let dateLabel:  String   // "2026年4月25日" など
        let yearLabel:  String   // "2026"
        let monthLabel: String   // "4月"
    }

    /// プロンプト内の時制表現を現在日時で解決してクエリラベルを生成する。
    private func buildTemporalQueryContext(from lower: String) -> TemporalContext {
        let now = Date()
        let cal = Calendar.current
        let year  = cal.component(.year,  from: now)
        let month = cal.component(.month, from: now)
        let day   = cal.component(.day,   from: now)
        let week  = cal.component(.weekOfYear, from: now)

        let yearLabel  = "\(year)"
        let monthLabel = "\(month)月"

        // 「今日」→ YYYY年M月D日
        // 「今週」→ YYYY年第W週
        // 「今月」→ YYYY年M月
        // 「今年」「現在」→ YYYY年
        let dateLabel: String
        if lower.contains("今日") || lower.contains("today") || lower.contains("本日") {
            dateLabel = "\(year)年\(month)月\(day)日"
        } else if lower.contains("今週") || lower.contains("this week") {
            dateLabel = "\(year)年第\(week)週"
        } else if lower.contains("今月") || lower.contains("this month") {
            dateLabel = "\(year)年\(month)月"
        } else {
            dateLabel = "\(year)年"
        }

        return TemporalContext(dateLabel: dateLabel, yearLabel: yearLabel, monthLabel: monthLabel)
    }

    // MARK: - ドキュメント参照

    private func classifyDocumentation(prompt: String, lower: String) -> SearchIntent? {
        let docKeywords = [
            "ドキュメント", "documentation", "docs",
            "公式", "official", "仕様", "specification", "spec",
            "使い方", "how to", "usage", "チュートリアル", "tutorial",
            "api reference", "マニュアル", "manual",
        ]
        guard docKeywords.contains(where: { lower.contains($0) }) else { return nil }

        let topic = extractMainTopic(from: prompt)
        guard !topic.isEmpty else { return nil }

        return SearchIntent(
            needsExternalSearch: true,
            queries: [
                "\(topic) official documentation site:docs.",
                "\(topic) official docs OR README site:github.com",
            ],
            intentType: .documentation(tech: topic),
            freshnessCritical: false
        )
    }

    // MARK: - ヘルパー

    private func hasFreshnessKeywords(_ lower: String) -> Bool {
        let keywords = [
            "現在", "最新", "最近", "今", "今日", "今週", "今月",
            "current", "latest", "recent", "now", "today",
            "状況", "状態", "status", "どうなって",
        ]
        return keywords.contains(where: { lower.contains($0) })
    }

    /// ユーザープロンプトから主要トピックを抽出する。
    /// 日本語助詞・常用疑問フレーズを除去してコアキーワードを残す。
    private func extractMainTopic(from prompt: String) -> String {
        var s = prompt

        // 日本語助詞・質問フレーズの除去
        let stripPatterns = [
            #"(?:について|を|に|は|が|の|で|と|から|まで|より|へ)(?:教えて|調べて|聞かせて|説明して|知りたい|わかりますか|ありますか)?"#,
            #"(?:教えて|調べて|知りたい|見せて|ください|くれ|くれますか|くれないか)[。\.\!！]*$"#,
            #"(?:どんな|どのような|どういう|どれ)[もの]?"#,
            #"(?:現在|最新|最近)の"#,
            #"(?:について|に関して|に関する)"#,
        ]
        for pattern in stripPatterns {
            if let re = try? NSRegularExpression(pattern: pattern) {
                let range = NSRange(s.startIndex..., in: s)
                s = re.stringByReplacingMatches(in: s, range: range, withTemplate: " ")
            }
        }

        let words = s.components(separatedBy: CharacterSet.whitespacesAndNewlines.union(.init(charactersIn: "　、。，．")))
                     .map { $0.trimmingCharacters(in: .punctuationCharacters) }
                     .filter { $0.count > 1 }

        return words.prefix(6).joined(separator: " ").trimmingCharacters(in: .whitespaces)
    }
}
