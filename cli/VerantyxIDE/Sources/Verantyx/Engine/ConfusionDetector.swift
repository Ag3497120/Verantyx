import Foundation

// MARK: - ConfusionDetector
//
// Nano Cortex Protocol の「混乱検知レイヤー」。
//
// 設計思想:
//   モデルに特殊トークンを出力させるのではなく、
//   スクリプト側が応答パターンから「混乱」を検知し自動で記憶を注入する。
//   ユーザーには「モデルが詰まった」という状況は一切見えない（ブラックボックス）。
//
// 動作フロー:
//   1. モデルが応答を生成
//   2. ConfusionDetector.isConfused(response) → true なら
//   3. 記憶検索 → context注入 → 同一ターンで再生成
//   4. ユーザーには最終応答のみ表示
//
// 対象:
//   nano / small ティア (≤7B) で自動有効化。
//   large/giant は不要（それらは自己修正能力があるため）。

struct ConfusionSignal {
    let pattern: String
    let weight: Double  // 重みが高いほど確実な混乱シグナル
}

enum ConfusionDetector {

    // MARK: - 混乱パターンリスト

    /// 重み付き混乱シグナルパターン（日英）
    ///
    /// 設計方針:
    ///   - weight=1.0: 単独でも確実に「知らない」を意味するフレーズ
    ///   - weight=0.5: 補助シグナル（単独では誤発火、複数で判定）
    ///   - isConfused threshold = 1.0 → weight=1.0が1つ OR weight=0.5が2つ以上で発火
    ///
    ///   NG パターン:「教えてください」「提供してください」は
    ///   AIが情報を求める際の通常フレーズなので除外。
    static let signals: [ConfusionSignal] = [
        // ── 高確度シグナル (weight=1.0) ─────────────────────────────────
        // 明確に「情報がない」「知らない」を示すフレーズのみ
        .init(pattern: "わかりません",              weight: 1.0),
        .init(pattern: "分かりません",              weight: 1.0),
        .init(pattern: "知りません",                weight: 1.0),
        .init(pattern: "存じません",                weight: 1.0),
        .init(pattern: "情報がありません",           weight: 1.0),
        .init(pattern: "記憶がありません",           weight: 1.0),
        .init(pattern: "覚えていません",             weight: 1.0),
        .init(pattern: "記憶にございません",         weight: 1.0),
        .init(pattern: "確認できません",             weight: 1.0),
        .init(pattern: "詳細はわかりません",         weight: 1.0),
        .init(pattern: "コンテキストには含まれていません", weight: 1.0),
        .init(pattern: "現在のコンテキストには",     weight: 1.0),  // 「現在のコンテキストには含まれていません」を確実に捕捉
        .init(pattern: "i don't know",               weight: 1.0),
        .init(pattern: "i do not know",              weight: 1.0),
        .init(pattern: "i have no information",      weight: 1.0),
        .init(pattern: "i do not have information",  weight: 1.0),
        .init(pattern: "i don't have information",   weight: 1.0),
        .init(pattern: "i have no memory",           weight: 1.0),
        .init(pattern: "i don't recall",             weight: 1.0),
        .init(pattern: "i do not recall",            weight: 1.0),
        .init(pattern: "i'm not aware",              weight: 1.0),
        .init(pattern: "i am not aware",             weight: 1.0),
        .init(pattern: "i wasn't provided",          weight: 1.0),
        .init(pattern: "no information available",   weight: 1.0),
        .init(pattern: "no memory of",               weight: 1.0),
        .init(pattern: "beyond my knowledge",        weight: 1.0),
        .init(pattern: "not in my knowledge",        weight: 1.0),

        // ── 補助シグナル (weight=0.5) ─────────────────────────────────
        // 単独では誤発火になりうる。weight=1.0 と組み合わせた場合のみ意味を持つ。
        // 「教えてください」「提供してください」は通常の質問返しフレーズなので除外済み。
        .init(pattern: "i don't have access",        weight: 0.5),
        .init(pattern: "i cannot find",              weight: 0.5),
        .init(pattern: "i can't find",               weight: 0.5),
        .init(pattern: "not found in my",            weight: 0.5),
        .init(pattern: "情報がない",                weight: 0.5),
        .init(pattern: "i don't have",               weight: 0.5),
        .init(pattern: "i do not have",              weight: 0.5),
        .init(pattern: "i'm unable to",              weight: 0.5),
        .init(pattern: "i am unable to",             weight: 0.5),
    ]

    // MARK: - 混乱スコア計算

    /// 混乱スコアを返す（0.0 = 混乱なし、1.0以上 = 混乱あり）
    /// 複数パターンにヒットするほどスコアが上がる。
    static func confusionScore(for response: String) -> Double {
        let lower = response.lowercased()
        return signals.reduce(0.0) { acc, signal in
            lower.contains(signal.pattern.lowercased()) ? acc + signal.weight : acc
        }
    }

    /// 混乱しているか判定（スコア ≥ threshold）
    /// - Parameter threshold: デフォルト 1.0（weight=1.0 のシグナルが1件以上必要）
    ///   これにより「教えてください」等の通常フレーズでは発火しない。
    static func isConfused(_ response: String, threshold: Double = 1.0) -> Bool {
        confusionScore(for: response) >= threshold
    }

    /// ヒットしたパターンのリストを返す（デバッグ用）
    static func matchedPatterns(in response: String) -> [String] {
        let lower = response.lowercased()
        return signals.compactMap { lower.contains($0.pattern.lowercased()) ? $0.pattern : nil }
    }

    // MARK: - 検索クエリ生成

    /// ユーザー入力と混乱した応答から、記憶検索クエリを生成する。
    /// 単純に userInput を返すが、必要なら NER 抽出を後で追加できる。
    static func buildSearchQuery(userInput: String, confusedResponse: String) -> String {
        // ── シンプル戦略: ユーザーの元の質問をそのまま使う ──
        // 理由: 混乱の原因は「ユーザーが参照した過去の文脈」であるため
        //       ユーザー入力 → 記憶検索が最も直接的
        let trimmed = userInput.trimmingCharacters(in: .whitespacesAndNewlines)
        // 長すぎる場合は先頭150文字に絞る
        return trimmed.count > 150 ? String(trimmed.prefix(150)) : trimmed
    }
}
