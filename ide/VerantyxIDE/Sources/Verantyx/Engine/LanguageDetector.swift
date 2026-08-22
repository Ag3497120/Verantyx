import Foundation

// MARK: - LanguageDetector
//
// チャット入力から「どの言語から・どの言語へ」変換するかを検出する。
// BitNet が使える場合は1.58bで分類。未インストール時はキーワードマッチ。

struct LangPair {
    let source: String       // 例: "swift"
    let target: String       // 例: "python"
    let sourceExt: String    // 例: ".swift"
    let targetExt: String    // 例: ".py"
    let targetDirHint: String // 例: "verantyx-python-target"
}

enum LanguageDetector {

    // MARK: - 言語→拡張子マップ

    static let extMap: [String: String] = [
        "swift": ".swift", "rust": ".rs", "rs": ".rs",
        "python": ".py", "py": ".py",
        "typescript": ".ts", "ts": ".ts",
        "javascript": ".js", "js": ".js",
        "kotlin": ".kt", "kt": ".kt",
        "go": ".go", "golang": ".go",
        "java": ".java",
        "cpp": ".cpp", "c++": ".cpp",
        "c": ".c",
        "csharp": ".cs", "c#": ".cs",
        "ruby": ".rb", "rb": ".rb",
    ]

    // MARK: - 指示文から LangPair を抽出

    /// 「SwiftをPythonに変換」「convert swift to go」などから LangPair を返す。
    static func detect(from instruction: String) -> LangPair? {
        let lower = instruction.lowercased()

        // ── パターンマッチ ──
        // "X to Y", "X→Y", "XからY", "X に変換", "convert X to Y"
        let patterns: [(String, String)] = [
            ("swift", "rust"), ("swift", "python"), ("swift", "typescript"),
            ("swift", "kotlin"), ("swift", "go"), ("swift", "java"),
            ("swift", "javascript"), ("swift", "csharp"),
            ("rust", "swift"), ("rust", "python"),
            ("typescript", "rust"), ("typescript", "python"),
            ("python", "rust"), ("python", "typescript"),
            ("kotlin", "swift"), ("java", "swift"),
        ]

        for (src, tgt) in patterns {
            if lower.contains(src) && lower.contains(tgt) {
                return makePair(source: src, target: tgt)
            }
        }

        // ワイルドカード検索: 「〜をXに変換」の X を取り出す
        // "to rust", "to python", "rust に", "pythonに"
        for (lang, ext) in extMap {
            guard lang.count > 1 else { continue }
            let toPatterns = ["to \(lang)", "\(lang)に変換", "\(lang)に", "→\(lang)", "to \(lang)"]
            for p in toPatterns {
                if lower.contains(p) {
                    // ソースを推定 (ワークスペースのL2.5地図から主要言語を取得)
                    let srcLang = guessSourceLanguage(from: lower, excluding: lang)
                    return makePair(source: srcLang, target: lang)
                }
            }
        }

        return nil
    }

    private static func guessSourceLanguage(from text: String, excluding: String) -> String {
        for lang in ["swift", "typescript", "python", "kotlin", "java", "rust"] {
            if lang != excluding && text.contains(lang) { return lang }
        }
        // L2.5地図参照はMainActorが必要なためここでは汎用フォールバック
        return "swift"
    }

    private static func makePair(source: String, target: String) -> LangPair {
        let srcExt = extMap[source] ?? ".\(source)"
        let tgtExt = extMap[target] ?? ".\(target)"
        return LangPair(
            source: source,
            target: target,
            sourceExt: srcExt,
            targetExt: tgtExt,
            targetDirHint: "verantyx-\(target)-target"
        )
    }

    // MARK: - パイプラインインテント判定 (言語非依存)

    /// 指示文がコード変換・生成タスクかどうかを判定する。
    /// 言語名は問わない。
    static func isPipelineIntent(_ text: String) -> Bool {
        let lower = text.lowercased()

        // 明示コマンド
        if lower.hasPrefix("/pipeline") || lower.hasPrefix("pipeline:") { return true }

        // 明示的に会話系を除外
        let chatPrefixes = ["what ", "why ", "how ", "explain", "show ", "describe", "tell me", "教えて", "なぜ", "どうして"]
        if chatPrefixes.contains(where: { lower.hasPrefix($0) }) { return false }

        // 変換キーワード (言語非依存)
        let conversionKeywords = [
            "convert", "transpile", "translate", "rewrite", "port to", "migrate",
            "変換", "書き換え", "移植", "トランスパイル", "ポート",
            "に変換", "に書き換え", "に移行", "一括変換", "全ファイル変換",
        ]
        if conversionKeywords.contains(where: { lower.contains($0) }) { return true }

        // 言語ペアが検出できる場合もパイプライン
        if detect(from: text) != nil { return true }

        return false
    }
}
