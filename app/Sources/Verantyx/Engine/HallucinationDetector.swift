import Foundation

// MARK: - HallucinationDetector
//
// SLM がループ・同一エラー繰り返し・コードブロック未出力などの
// ハレーション状態を検知し、プロンプト戦略を自動切り替えする。
//
// BitNet Commander の下位モジュールとして動作する。

enum PromptStrategy {
    case standard       // 通常
    case compressed     // プロンプトを短縮 (地図省略)
    case exampleForced  // 出力例を強制追加
    case englishOnly    // 英語のみ (日本語混入対策)
    case minimalTask    // 最小タスク化 (1関数ずつ)
    case abort          // リカバリー不能 → スキップ
}

struct HallucinationPattern {
    let errorFingerprint: String    // エラーの正規化ハッシュ
    var occurrenceCount: Int
    var lastSeen: Date
}

@MainActor
final class HallucinationDetector {

    static let shared = HallucinationDetector()

    // 現在のパイプラインセッション中のエラーパターン記録
    private var patterns: [String: HallucinationPattern] = [:]

    // 同一エラーの最大許容回数
    private let maxSameError = 3
    // ノーコードブロック連続の最大許容回数
    private var noCodeBlockStreak: Int = 0
    private let maxNoCodeBlock = 2

    private init() {}

    // MARK: - セッションリセット (新しいファイル処理開始時)

    func resetForNewFile() {
        noCodeBlockStreak = 0
        // ファイルをまたいだエラーパターンは保持する (学習を継続)
    }

    // MARK: - エラー分析

    struct AnalysisResult {
        let strategy: PromptStrategy
        let reason: String
        let injectedHint: String   // プロンプトに追加するヒント
    }

    /// エラーを受け取り、次のプロンプト戦略を決定する。
    func analyze(
        error: String,
        response: String,
        retryCount: Int,
        todo: TranspilationTodo
    ) -> AnalysisResult {

        // ── コードブロック未出力の検知 ──────────────────────────────
        let hasCodeBlock = response.contains("```")
        if !hasCodeBlock {
            noCodeBlockStreak += 1
            if noCodeBlockStreak >= maxNoCodeBlock {
                return AnalysisResult(
                    strategy: .exampleForced,
                    reason: "コードブロック未出力が\(noCodeBlockStreak)回連続",
                    injectedHint: """
                    IMPORTANT: You MUST output a fenced code block. Example:
                    ```rust
                    // FILE: \(todo.targetPath)
                    fn main() { /* your code here */ }
                    ```
                    Do NOT explain. Output ONLY the code block.
                    """
                )
            }
        } else {
            noCodeBlockStreak = 0
        }

        // ── 同一エラーの繰り返し検知 ────────────────────────────────
        let fingerprint = normalizeError(error)
        if !fingerprint.isEmpty {
            var pattern = patterns[fingerprint] ?? HallucinationPattern(
                errorFingerprint: fingerprint, occurrenceCount: 0, lastSeen: Date()
            )
            pattern.occurrenceCount += 1
            pattern.lastSeen = Date()
            patterns[fingerprint] = pattern

            if pattern.occurrenceCount >= maxSameError {
                return decideRecoveryStrategy(
                    fingerprint: fingerprint,
                    count: pattern.occurrenceCount,
                    error: error,
                    todo: todo
                )
            }
        }

        // ── 日本語・説明文混入の検知 ────────────────────────────────
        if containsExcessiveNonCode(response) {
            return AnalysisResult(
                strategy: .englishOnly,
                reason: "非コードテキストが過多 (説明文・日本語混入)",
                injectedHint: "RESPOND IN CODE ONLY. No explanations. No Japanese. Output the code block immediately."
            )
        }

        // ── リトライ上限近傍での圧縮戦略 ────────────────────────────
        if retryCount >= 2 {
            return AnalysisResult(
                strategy: .compressed,
                reason: "リトライ\(retryCount)回目 → プロンプト短縮",
                injectedHint: "Keep it minimal. Convert only the core logic. Skip comments."
            )
        }

        return AnalysisResult(strategy: .standard, reason: "標準リトライ", injectedHint: "")
    }

    // MARK: - エラーパターン→回復戦略

    private func decideRecoveryStrategy(
        fingerprint: String, count: Int, error: String, todo: TranspilationTodo
    ) -> AnalysisResult {
        // 依存関係エラー (型が見つからない系)
        if fingerprint.contains("cannot find type") ||
           fingerprint.contains("unresolved import") ||
           fingerprint.contains("undefined reference") {
            return AnalysisResult(
                strategy: .minimalTask,
                reason: "依存型エラー \(count)回 → スタブで代替",
                injectedHint: """
                The dependent types are not yet converted. Use stub types:
                Replace any unknown type with a placeholder (e.g., `String`, `Vec<u8>`, `serde_json::Value`).
                Do NOT import modules that don't exist yet. Use TODO comments instead.
                """
            )
        }

        // クレート/パッケージ幻覚
        if fingerprint.contains("no such crate") ||
           fingerprint.contains("package not found") ||
           fingerprint.contains("cannot find module") {
            return AnalysisResult(
                strategy: .compressed,
                reason: "クレート幻覚 \(count)回 → 標準ライブラリのみ指示",
                injectedHint: """
                USE ONLY standard library. Forbidden: chrono, uuid, llama_cpp, bitnet, ort.
                For time: use std::time::SystemTime.
                For IDs: use String (UUID format manually).
                No external crates at all.
                """
            )
        }

        // 構文エラー繰り返し
        if fingerprint.contains("syntax error") || fingerprint.contains("expected") {
            return AnalysisResult(
                strategy: .minimalTask,
                reason: "構文エラー \(count)回 → 最小タスク化",
                injectedHint: """
                Convert ONLY the first function/method in the file. Output nothing else.
                Keep it as simple as possible. No generics, no lifetimes, use String everywhere.
                """
            )
        }

        // 回復不能
        if count >= maxSameError * 2 {
            return AnalysisResult(strategy: .abort, reason: "回復不能エラー \(count)回", injectedHint: "")
        }

        return AnalysisResult(
            strategy: .exampleForced,
            reason: "不明エラー \(count)回",
            injectedHint: "Previous attempt failed: \(error.prefix(100)). Fix this specific issue."
        )
    }

    // MARK: - エラー正規化 (ファイルパス・行番号を除去してパターン化)

    private func normalizeError(_ error: String) -> String {
        var normalized = error.lowercased()
        // ファイルパスを除去
        normalized = normalized.replacingOccurrences(of: #"[\w/\-\.]+\.(?:rs|swift|py|ts|go):\d+"#,
                                                     with: "<file>", options: .regularExpression)
        // 数値を除去
        normalized = normalized.replacingOccurrences(of: #"\d+"#, with: "N", options: .regularExpression)
        // 識別子名を汎化 (大文字で始まる単語はIDとみなす)
        normalized = normalized.replacingOccurrences(of: #"\b[A-Z][a-zA-Z]+\b"#,
                                                     with: "<ID>", options: .regularExpression)
        return String(normalized.prefix(80))
    }

    private func containsExcessiveNonCode(_ response: String) -> Bool {
        guard !response.isEmpty else { return false }
        // コードブロックを除いたテキスト量
        let withoutCode = response.replacingOccurrences(
            of: #"```[\s\S]*?```"#, with: "", options: .regularExpression
        )
        // 非コード割合が70%超 → 過多と判定
        let ratio = Double(withoutCode.count) / Double(response.count)
        return ratio > 0.70 && withoutCode.count > 200
    }

    // MARK: - セッション全体のエラーパターンサマリー (L2記憶注入用)

    func buildErrorPatternSummary() -> String {
        guard !patterns.isEmpty else { return "" }
        let sorted = patterns.values.sorted { $0.occurrenceCount > $1.occurrenceCount }
        let lines = sorted.prefix(5).map {
            "- \($0.errorFingerprint) (x\($0.occurrenceCount))"
        }
        return "[Known Error Patterns]\n" + lines.joined(separator: "\n")
    }
}
