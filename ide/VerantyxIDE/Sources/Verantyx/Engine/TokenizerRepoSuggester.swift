import Foundation

/// GGUF からトークナイザを合成できなかったモデルについて、`--tokenizer` に
/// 指定すべき HuggingFace リポジトリを提案する。
///
/// 形式の判定（BPE / Unigram / byte-level か metaspace か）は **これとは無関係**
/// で、GGUF に入っている実データから決定論的に決めている（`jgen_forge.py` の
/// `_synthesize_hf_tokenizer`）。正解がファイルに書いてある問題を推測で解く
/// 意味は無いので、そちらに LLM は使わない。
///
/// ここが扱うのは「このモデルの正規のトークナイザはどこで公開されているか」
/// という**知識の問題**で、これはローカルモデルと検索が本当に役に立つ領域。
///
/// ただし推測したリポジトリ名をそのまま出すのは危険なので、**実在確認を必須**
/// にしてある。確認に通らなければ何も提案しない。
actor TokenizerRepoSuggester {

    static let shared = TokenizerRepoSuggester()
    private init() {}

    /// `org/repo` の形をしているか。自由文から拾った文字列をそのまま信用しない。
    private static let repoPattern = try? NSRegularExpression(
        pattern: #"\b([A-Za-z0-9][A-Za-z0-9._-]{0,60}/[A-Za-z0-9][A-Za-z0-9._-]{0,60})\b"#
    )

    /// モデル名から候補リポジトリを1つ返す。**実在が確認できたものだけ**返す。
    /// 見つからなければ nil（何も提案しない方が、嘘を提案するより良い）。
    func suggest(forModelName modelName: String) async -> String? {
        var candidates: [String] = []

        // 1) ローカルの小型モデルに聞く（安い・オフラインでも動く）
        if let cheap = await QueryReformulator.cheapLocalModel() {
            let prompt = """
            次のローカルLLMモデルの、公式のHuggingFaceリポジトリIDを答えてください。

            モデル名: \(modelName)

            ルール:
            - 「org/repo」の形式のみを1行で出力する
            - 説明・前置き・引用符は書かない
            - 分からなければ unknown とだけ書く

            リポジトリID:
            """
            if let out = await OllamaClient.shared.generate(
                model: cheap, prompt: prompt, maxTokens: 40, temperature: 0.1
            ) {
                candidates += Self.extractRepoIDs(from: out)
            }
        }

        // 2) 検索で補う。自由文なので、あくまで候補の供給源としてだけ使う。
        let result = await WebSearchEngine.shared.search(
            query: "\(modelName) huggingface tokenizer.json"
        )
        if case .ok = result.verdict {
            candidates += Self.extractRepoIDs(from: result.contextSnippet)
        }

        // 3) 実在確認。ここを通らないものは絶対に出さない。
        for repo in Self.dedupePreservingOrder(candidates).prefix(6) {
            if await Self.tokenizerExists(repo: repo) { return repo }
        }
        return nil
    }

    /// `https://huggingface.co/<repo>/resolve/main/tokenizer.json` が 200 を返すか。
    ///
    /// これが無いと、モデルや検索結果が作り出した実在しないリポジトリ名を
    /// そのままユーザーへ渡してしまう。最悪でも「何も出ない」で終わらせる。
    static func tokenizerExists(repo: String) async -> Bool {
        guard let url = URL(string: "https://huggingface.co/\(repo)/resolve/main/tokenizer.json") else {
            return false
        }
        var req = URLRequest(url: url)
        req.httpMethod = "HEAD"
        req.timeoutInterval = 8
        guard let (_, response) = try? await URLSession.shared.data(for: req),
              let http = response as? HTTPURLResponse else { return false }
        return http.statusCode == 200
    }

    /// 文字列から `org/repo` らしき断片を拾う。URLの一部や明らかに違うものは弾く。
    static func extractRepoIDs(from text: String) -> [String] {
        guard let regex = repoPattern else { return [] }
        let ns = NSRange(text.startIndex..., in: text)
        let noise: Set<String> = [
            "huggingface.co", "github.com", "resolve/main", "blob/main", "tree/main",
        ]
        return regex.matches(in: text, range: ns).compactMap { m -> String? in
            guard let r = Range(m.range(at: 1), in: text) else { return nil }
            let s = String(text[r])
            let lower = s.lowercased()
            if noise.contains(lower) { return nil }
            if lower.hasPrefix("http") || lower.contains(".co/") { return nil }
            // 拡張子付き（パスの一部）は除外
            if lower.hasSuffix(".json") || lower.hasSuffix(".md") || lower.hasSuffix(".py") { return nil }
            if s.lowercased() == "unknown" { return nil }
            return s
        }
    }

    static func dedupePreservingOrder(_ items: [String]) -> [String] {
        var seen = Set<String>()
        return items.filter { seen.insert($0.lowercased()).inserted }
    }
}
