import Foundation

/// 検索クエリを「人間がやり直すように」書き直す。
///
/// 動機: 未公開・社内の固有名詞（このアプリ自身の "Verantyx" など）で検索
/// しても Web 上には情報が無いので0件になる。人間ならそこで諦めず、
/// 「MCP の設定方法なら Claude Desktop や Cursor の手順を読めばいい」と
/// **一般的でよく文書化された等価物**に置き換えて調べ直す。その段階的な
/// 後退（ラダー）を実装したもの。
///
/// 段階:
///   L0 … モデルが最初に書いたクエリ（ここでは扱わない）
///   L2 … 一般的な技術名 + 代表的な実装名
///   L3 … 公式仕様・ドキュメント
/// L1（固有名詞を消しただけ）は意図的に飛ばす。単独では SEO ノイズを拾い
/// やすく、ユーザーの求めているのは L2 だから。`ReActRetryEngine` の
/// `maxRetries = 3` は実質「書き直し2回」なので、2段で足りる。
enum QueryReformulator {

    /// このアプリ自身の名前。Web に情報が無いことが確実に分かっている固有
    /// 名詞なので、検出の起点として最も信頼できる。
    static let localBrandTerms = [
        "verantyx", "vera-α", "vera-alpha", "jgen", "jcross", "vxloop",
        "verantyx-cli", "jgen_forge", "vera-memory",
    ]

    /// 「この技術ならこれを読めばいい」の対応表。
    ///
    /// 正直に言えばこれは**表に載っている範囲でしか効かない**。一般解は LLM
    /// による書き直しで、この表はローカルモデルが使えないときに
    /// 「少なくとも害のないクエリ」へ落とすための保険。まずはこのアプリで
    /// 実際に出てくる語から始める。
    private static let conceptTable: [(key: String, general: String, exemplars: [String])] = [
        ("mcp",         "MCP サーバー 設定 mcpServers json",      ["Claude Desktop", "Cursor"]),
        ("tokenizer",   "HuggingFace tokenizer.json 形式",        ["transformers"]),
        ("トークナイザ",  "HuggingFace tokenizer.json 形式",        ["transformers"]),
        ("gguf",        "GGUF 変換 量子化",                        ["llama.cpp"]),
        ("ollama",      "Ollama Modelfile 設定",                   ["Ollama 公式"]),
        ("lsp",         "Language Server Protocol 設定",           ["VS Code"]),
        ("xcodebuild",  "xcodebuild コマンド 使い方",               ["Apple 公式"]),
        ("safetensors", "safetensors 形式 読み込み",                ["HuggingFace"]),
        ("swiftui",     "SwiftUI 実装例",                          ["Apple 公式"]),
    ]

    /// クエリの書き直しに使える一番安いローカルモデルを探す。
    ///
    /// 12語程度のクエリを作るのに、会話全体とアンカー画像を本命モデルへ
    /// 送るのは明らかに過剰。0件判定を入れて再検索の発火頻度が上がる分、
    /// ここを安くしておかないと体感が悪化する。
    ///
    /// (削除した `IgnoranceRouter.detectNanoModel` から救出したもの。
    ///  キーワード一覧は古かったので広げ、見つからない場合は最小サイズの
    ///  モデルへフォールバックする。)
    static func cheapLocalModel() async -> String? {
        let models = await OllamaClient.shared.listModels()
        guard !models.isEmpty else { return nil }

        let nanoKeywords = [
            "e2b", ":2b", "-2b", "0.5b", "1b", "1.5b", "3b",
            "nano", "mini", "small", "tiny", "gemma2b", "smollm", "qwen2.5:0.5b",
        ]
        for keyword in nanoKeywords {
            if let found = models.first(where: { $0.lowercased().contains(keyword) }) {
                return found
            }
        }

        // キーワードに当たらない場合は実サイズが最小のものを選ぶ
        let detailed = await OllamaClient.shared.listModelsDetailed()
        if let smallest = detailed.min(by: { $0.sizeBytes < $1.sizeBytes }) {
            return smallest.name
        }
        return models.first
    }

    /// 固有名詞らしきものを1つ返す。LLM を使わない。
    ///
    /// 優先順:
    ///   1. このアプリ自身の名前（確実に既知）
    ///   2. 一般語でない大文字始まりの ASCII 語
    ///   3. 3文字以上のカタカナ連続
    static func detectProperNoun(in query: String) -> String? {
        let lower = query.lowercased()
        if let brand = localBrandTerms.first(where: { lower.contains($0) }) {
            // 元の表記のまま返したいので、元文字列から切り出す
            if let r = lower.range(of: brand) {
                return String(query[r])
            }
            return brand
        }

        let tokens = query.components(separatedBy: CharacterSet.whitespacesAndNewlines.union(.punctuationCharacters))
            .filter { !$0.isEmpty }

        let commonCapitalized: Set<String> = [
            "I", "The", "A", "An", "How", "What", "Why", "When", "Where",
            "Mac", "MacOS", "Apple", "Google", "GitHub", "Python", "Swift",
        ]
        if let cap = tokens.first(where: { tok in
            guard let f = tok.first, f.isUppercase, f.isASCII, tok.count >= 3 else { return false }
            return !commonCapitalized.contains(tok)
        }) {
            return cap
        }

        // カタカナ連続（3文字以上）
        var run = ""
        var best = ""
        for ch in query {
            if let s = ch.unicodeScalars.first, (0x30A0...0x30FF).contains(s.value) {
                run.append(ch)
                if run.count > best.count { best = run }
            } else {
                run = ""
            }
        }
        return best.count >= 3 ? best : nil
    }

    /// LLM が使えないときの決定論的な書き直し。
    ///
    /// - Parameter rung: 2 = 一般名 + 代表実装名、3 = 公式ドキュメント
    ///
    /// 以前の実装は「先頭5語 + 最新情報」だったが、これは**固有名詞を残した
    /// まま**再検索するので、この場面ではむしろ有害だった（同じ0件を引く）。
    static func deterministic(query: String, rung: Int) -> String {
        let properNoun = detectProperNoun(in: query)
        var stripped = query
        if let pn = properNoun {
            stripped = stripped.replacingOccurrences(of: pn, with: " ", options: .caseInsensitive)
        }
        let lowerStripped = stripped.lowercased()

        if let hit = conceptTable.first(where: { lowerStripped.contains($0.key) }) {
            if rung >= 3 {
                return "\(hit.general) 公式ドキュメント"
            }
            let exemplar = hit.exemplars.first ?? ""
            return "\(exemplar) \(hit.general)".trimmingCharacters(in: .whitespaces)
        }

        // 表に無い場合: 固有名詞だけ落として、一般的な問いの形にする
        let terms = WebSearchResult.contentTerms(of: stripped).prefix(5).joined(separator: " ")
        if terms.isEmpty {
            return rung >= 3 ? "公式ドキュメント 設定方法" : "設定方法 例"
        }
        return rung >= 3 ? "\(terms) 公式ドキュメント" : "\(terms) 設定方法 例"
    }

    /// 書き直し結果が使い物になるか検査する。
    ///
    /// LLM は指示を無視して言い換えただけの文を返すことがある。それをその
    /// まま投げると同じ0件を引くだけなので、ここで弾いて決定論的経路へ回す。
    static func isAcceptable(rewritten: String,
                             properNoun: String?,
                             previousQueries: [String]) -> Bool {
        let q = rewritten.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !q.isEmpty else { return false }
        // URL を含むものは（既存方針どおり）拒否
        if q.contains("http://") || q.contains("https://") { return false }
        // 引用符が残ると完全一致検索になってしまう
        if q.contains("\"") { return false }
        // 語数が多すぎる = 文をそのまま返している
        if q.components(separatedBy: .whitespaces).filter({ !$0.isEmpty }).count > 12 { return false }
        // 固有名詞が残っている = 一般化できていない
        if let pn = properNoun, q.lowercased().contains(pn.lowercased()) { return false }
        // 過去の試行と実質同じ
        let norm = { (s: String) in
            s.lowercased().components(separatedBy: .whitespaces).filter { !$0.isEmpty }.joined(separator: " ")
        }
        if previousQueries.map(norm).contains(norm(q)) { return false }
        return true
    }

    /// LLM に渡す書き直し指示。ユーザー自身の例をそのまま入れてある —
    /// この few-shot が一番効く。
    static func rethoughtPrompt(userInstruction: String,
                                failedQuery: String,
                                missingTerm: String?,
                                rung: Int) -> String {
        let detected = missingTerm.map { "（システムが検出した候補: 「\($0)」）" } ?? ""
        let rungGoal = rung >= 3
            ? "3. 公式仕様・公式ドキュメントに当たるクエリにせよ。"
            : "3. その技術について**広く文書化されている代表的な実装名を1つ**クエリに含めよ。"

        return """
        検索が0件でした。人間がやり直すように、検索語を作り直してください。

        元の要求: \(userInstruction.prefix(160))
        失敗したクエリ: \(failedQuery)

        手順:
        1. 失敗クエリの中から「Web上に存在しない可能性が高い固有名詞」を1つ特定せよ。\(detected)
        2. その固有名詞を、それが属する**一般的な技術名・タスク名**に置き換えよ。
        \(rungGoal)

        例:
          失敗: 「Verantyx MCP 設定方法」
                → Verantyx は一般公開製品ではないため0件
          成功: 「Claude Desktop MCP サーバー 設定 mcpServers json 例」
          理由: MCP設定は実装非依存の共通仕様。よく文書化された Claude Desktop や
                Cursor の手順を読めば、同じ形式が Verantyx にも適用できる。

        制約:
        - 5〜8語の語の列。文にしない。
        - URLと引用符は含めない。
        - 特定した固有名詞は残さない。

        新しい検索クエリ（1行のみ、説明不要）:
        """
    }
}
