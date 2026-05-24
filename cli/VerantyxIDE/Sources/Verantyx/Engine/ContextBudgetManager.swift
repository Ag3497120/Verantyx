import Foundation

// MARK: - ContextBudgetManager
//
// モデルのコンテキスト上限を動的に取得し、
// L2.5地図・記憶・ソースファイルへのトークン予算を自動配分する。
//
// 役割: 全モデル・全ファイルサイズで安定した変換を実現する。
// 1000ファイル規模でも地図が溢れず、大ファイルもチャンクで確実に変換できる。

struct ContextBudget {
    let modelId: String
    let maxTokens: Int
    let mapBudgetChars: Int      // L2.5地図に使える文字数
    let memoryBudgetChars: Int   // L1.5/L2記憶に使える文字数
    let sourceBudgetChars: Int   // L3ソース1ファイルに使える文字数
    let chunkRequired: Bool      // ソースがチャンク分割必要か
    let chunkSizeChars: Int      // チャンクサイズ
}

struct ContextBudgetManager {

    // MARK: - トークン上限テーブル (モデル名パターンマッチ)
    // 実際のトークン数の90%を安全上限とする

    private static let knownLimits: [(pattern: String, tokens: Int)] = [
        ("gemma4:26b", 32768),
        ("gemma4", 32768),
        ("gemma3:27b", 32768),
        ("qwen2.5:72b", 131072),
        ("qwen2.5:32b", 32768),
        ("qwen2.5:14b", 16384),
        ("qwen2.5:7b", 8192),
        ("qwen", 8192),          // qwen 系のフォールバック
        ("llama3.3:70b", 131072),
        ("llama3.1:70b", 131072),
        ("llama3", 8192),
        ("mistral:7b", 8192),
        ("mistral", 8192),
        ("codestral", 32768),
        ("deepseek-coder", 16384),
        ("phi4", 16384),
        ("phi3", 8192),
        ("smollm", 4096),
    ]

    static func budget(for modelId: String) -> ContextBudget {
        let lower = modelId.lowercased()
        let maxTokens = knownLimits.first { lower.contains($0.pattern) }?.tokens ?? 8192
        let safeTokens = Int(Double(maxTokens) * 0.85)

        // 文字数へ変換 (日本語混在を考慮: 1トークン ≈ 2.5文字)
        let safeChars = safeTokens * 2
        // システムプロンプト・タスク・フォーマット指示用に固定費を引く
        let overhead = 800
        let budget = safeChars - overhead

        // 配分:
        //   地図:   30% (Kanji topology は圧縮済みなので少なくてOK)
        //   記憶:   10% (L1.5差分・L2エラー)
        //   ソース: 60% (変換対象ファイル)
        let mapBudget    = Int(Double(budget) * 0.30)
        let memBudget    = Int(Double(budget) * 0.10)
        let srcBudget    = Int(Double(budget) * 0.60)

        // チャンク分割の判断 (ソース予算 < 2000文字なら小型モデル → チャンク必須)
        let chunkRequired = srcBudget < 2000
        let chunkSize = chunkRequired ? max(srcBudget, 800) : srcBudget

        return ContextBudget(
            modelId: modelId,
            maxTokens: maxTokens,
            mapBudgetChars: mapBudget,
            memoryBudgetChars: memBudget,
            sourceBudgetChars: srcBudget,
            chunkRequired: chunkRequired,
            chunkSizeChars: chunkSize
        )
    }

    // MARK: - ソースをチャンクに分割

    /// 大ファイルを論理的な区切り (クラス境界・関数境界) でチャンク分割する。
    /// 境界が見つからない場合は行単位で分割。
    static func splitIntoChunks(source: String, chunkSizeChars: Int) -> [(index: Int, total: Int, content: String)] {
        guard source.count > chunkSizeChars else {
            return [(0, 1, source)]
        }

        // クラス/関数の境界でチャンクを切る
        let splitMarkers = [
            "\nclass ", "\nstruct ", "\nextension ", "\nfunc ",  // Swift
            "\npub fn ", "\nfn ", "\nimpl ", "\nmod ",           // Rust
            "\ndef ", "\nclass ", "\nasync def ",                // Python
            "\nfunction ", "\nexport function ", "\nconst ",     // JS/TS
        ]

        var chunks: [String] = []
        var current = ""
        let lines = source.components(separatedBy: "\n")

        for line in lines {
            let wouldExceed = (current.count + line.count + 1) > chunkSizeChars
            let isMarker = splitMarkers.contains { line.hasPrefix($0) }

            if wouldExceed && isMarker && !current.isEmpty {
                chunks.append(current)
                current = line + "\n"
            } else {
                current += line + "\n"
                if current.count > chunkSizeChars * 2 {
                    // 強制分割 (マーカーなし)
                    chunks.append(current)
                    current = ""
                }
            }
        }
        if !current.isEmpty { chunks.append(current) }

        return chunks.enumerated().map { (i, content) in (i, chunks.count, content) }
    }

    // MARK: - 予算サマリー (ログ用)

    static func describe(_ budget: ContextBudget) -> String {
        "[\(budget.modelId)] maxTok:\(budget.maxTokens) " +
        "map:\(budget.mapBudgetChars)ch mem:\(budget.memoryBudgetChars)ch " +
        "src:\(budget.sourceBudgetChars)ch chunk:\(budget.chunkRequired)"
    }
}
