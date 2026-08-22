import Foundation

// MARK: - JCrossIRParser
//
// 「生成と検証の分離」アーキテクチャの第一層。
//
// nano モデルが出力した JCross 思考 IR トークン列を構造化ノードに変換する。
// モデルの思考プロセス（CoT）を自然言語ではなく記号列として扱うことで
// Verantyx 側で決定論的な照合・修正が可能になる。
//
// 思考IR フォーマット（nanoPrompt で定義済み）:
//   [想:X]  → Thinking(topic: X)   — X について考えている
//   [確:X]  → Verify(claim: X)     — X を照合・確認する
//   [出:X]  → Output(answer: X)    — X を最終回答として出力する
//   [記:X]  → Recall(key: X)       — 記憶 X を参照する
//   [否:X]  → Negate(subject: X)   — X は存在しない / 該当なし
//
// Example:
//   モデル出力: "[想:食好]→[記:U食=ラーメン]→[出:ラーメン]"
//   パース結果: [.think("食好"), .recall("U食=ラーメン"), .output("ラーメン")]

// MARK: - IR ノード定義

enum IRNode: Equatable {
    case think(topic: String)       // [想:X]
    case verify(claim: String)      // [確:X]
    case output(answer: String)     // [出:X]
    case recall(key: String)        // [記:X]
    case negate(subject: String)    // [否:X]
    case unknown(raw: String)       // パース不能なトークン（無視）

    /// ノードの種別文字列（ログ用）
    var typeName: String {
        switch self {
        case .think:   return "想"
        case .verify:  return "確"
        case .output:  return "出"
        case .recall:  return "記"
        case .negate:  return "否"
        case .unknown: return "?"
        }
    }

    /// ノードが保持するペイロード文字列
    var payload: String {
        switch self {
        case .think(let t):   return t
        case .verify(let c):  return c
        case .output(let a):  return a
        case .recall(let k):  return k
        case .negate(let s):  return s
        case .unknown(let r): return r
        }
    }
}

// MARK: - パースエンジン

enum JCrossIRParser {

    // MARK: - メインパース

    /// モデル応答文字列から IR ノード列を抽出する。
    /// IR トークンが一つも見つからない場合は空配列（通常の自然言語応答）。
    static func parse(_ response: String) -> [IRNode] {
        // [漢字:ペイロード] 形式を正規表現で抽出
        // ペイロードは複数文字・記号を許容（=, →, ・等を含む）
        guard let regex = try? NSRegularExpression(
            pattern: #"\[([想確出記否]):(.*?)\]"#,
            options: []
        ) else { return [] }

        let nsStr = response as NSString
        let matches = regex.matches(
            in: response,
            options: [],
            range: NSRange(location: 0, length: nsStr.length)
        )

        return matches.compactMap { match in
            guard
                match.numberOfRanges == 3,
                let typeRange    = Range(match.range(at: 1), in: response),
                let payloadRange = Range(match.range(at: 2), in: response)
            else { return nil }

            let typeChar = String(response[typeRange]).trimmingCharacters(in: .whitespaces)
            let payload  = String(response[payloadRange]).trimmingCharacters(in: .whitespaces)

            return makeNode(type: typeChar, payload: payload)
        }
    }

    /// モデル応答が IR 形式を含むか判定（高速チェック）
    static func containsIR(_ response: String) -> Bool {
        response.contains("[想:") ||
        response.contains("[確:") ||
        response.contains("[出:") ||
        response.contains("[記:") ||
        response.contains("[否:")
    }

    // MARK: - 抽出ヘルパー

    /// 出力ノード ([出:X]) から最終回答を取得する。
    /// 複数ある場合は最後（最終決定）を返す。
    static func extractFinalOutput(from nodes: [IRNode]) -> String? {
        nodes.reversed().compactMap {
            if case .output(let ans) = $0 { return ans }
            return nil
        }.first
    }

    /// 検証要求ノード ([確:X]) を全て返す。
    static func extractVerifyClaims(from nodes: [IRNode]) -> [String] {
        nodes.compactMap {
            if case .verify(let claim) = $0 { return claim }
            return nil
        }
    }

    /// 記憶参照ノード ([記:X]) を全て返す。
    static func extractRecallKeys(from nodes: [IRNode]) -> [String] {
        nodes.compactMap {
            if case .recall(let key) = $0 { return key }
            return nil
        }
    }

    /// モデル出力から IR ブロックを除いた「ユーザー向けテキスト」を返す。
    /// IR ブロック自体はユーザーに見せない（ブラックボックス思考）。
    static func stripIR(from response: String) -> String {
        guard let regex = try? NSRegularExpression(
            pattern: #"\[([想確出記否]):.*?\](\s*→\s*)?"#,
            options: []
        ) else { return response }

        let stripped = regex.stringByReplacingMatches(
            in: response,
            options: [],
            range: NSRange(response.startIndex..., in: response),
            withTemplate: ""
        ).trimmingCharacters(in: .whitespacesAndNewlines)

        return stripped.isEmpty ? response : stripped
    }

    // MARK: - プライベート

    private static func makeNode(type: String, payload: String) -> IRNode {
        switch type {
        case "想": return .think(topic: payload)
        case "確": return .verify(claim: payload)
        case "出": return .output(answer: payload)
        case "記": return .recall(key: payload)
        case "否": return .negate(subject: payload)
        default:   return .unknown(raw: "[\(type):\(payload)]")
        }
    }
}

// MARK: - デバッグ表示

extension IRNode: CustomStringConvertible {
    var description: String { "[\(typeName):\(payload)]" }
}
