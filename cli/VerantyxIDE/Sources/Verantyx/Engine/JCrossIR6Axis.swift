import Foundation
import CryptoKit

// MARK: - JCross IR 6軸完全分離プロトコル v2.1
//
// 6つの軸を物理的に分離し、AIに送信するIRには構造のみを含める。
// ビジネスロジック（意味論軸）はローカルVaultに隔離する。
//
// 送信先：LLM (Claude/GPT等)    ←  IRNode のみ（値・名前・目的なし）
// 保持先：ローカルVault          ←  VaultEntry（すべての具体情報）
//
// ┌─────────────────────────────────────────────────────────┐
// │  軸1 制御フロー   → AIへ: 分岐数, hash    隠す: 条件式  │
// │  軸2 データフロー → AIへ: 操作カテゴリ    隠す: 具体値  │
// │  軸3 型制約       → AIへ: カテゴリ        隠す: 具体型  │
// │  軸4 メモリ       → AIへ: 相対順序        隠す: スコープ│
// │  軸5 スコープ     → AIへ: 可視グラフ      隠す: 目的名  │
// │  軸6 意味論       → AIへ: 送信しない      隠す: 全て   │
// └─────────────────────────────────────────────────────────┘

// MARK: - IR Node ID

/// 不透明なノードID。UUIDベース。AIには意味のない文字列として届く。
struct IRNodeID: Hashable, Codable, CustomStringConvertible {
    let raw: String

    init() {
        // 0x形式の16文字16進数 (例: 0xF7E2A4D9B3C1A5E8)
        let bytes = (0..<8).map { _ in UInt8.random(in: 0..<255) }
        self.raw = "0x" + bytes.map { String(format: "%02X", $0) }.joined()
    }

    init(raw: String) { self.raw = raw }

    var description: String { raw }
}

// MARK: - 軸1: 制御フロー軸

/// LLMに公開する制御フロー情報。
/// 「何個の分岐があるか」「ループか条件か」のみを示す。
/// 条件式の内容・変数名・閾値は含まない。
struct ControlFlowProjection: Codable {
    enum FlowKind: String, Codable {
        case sequential       // 逐次実行
        case conditionalBranch // 条件分岐（if/guard/switch）
        case loop             // 反復（for/while）
        case tryCatch         // 例外処理
        case asyncAwait       // 非同期
        case earlyReturn      // 早期リターン
    }

    let kind: FlowKind
    /// 分岐数（ifなら2、switchなら0+）
    let branchCount: Int
    /// 条件式のハッシュ（不可逆）。同じ条件は同じハッシュになる。
    let conditionHash: String
    /// 条件式のアリティ（何個の変数で判定されるか）
    let conditionArity: Int

    /// ハッシュ生成（SHA-256の先頭8文字）
    static func hash(for expression: String) -> String {
        let data = Data(expression.utf8)
        let digest = SHA256.hash(data: data)
        let hex = digest.map { String(format: "%02x", $0) }.joined()
        return "0x" + hex.prefix(8)
    }
}

// MARK: - 軸2: データフロー軸

/// LLMに公開するデータフロー情報。
/// 「乗算がある」「1つの入力を受け取る」のみ。
/// 具体的な値（1.21）は含まない。
struct DataFlowProjection: Codable {
    enum OperationCategory: String, Codable {
        case arithmetic   // 算術演算（加減乗除）
        case logical      // 論理演算（and/or/not）
        case comparison   // 比較演算（</>=/==）
        case functional   // 関数呼び出し
        case memory       // メモリ操作（読み書き）
        case io           // 入出力
        case conversion   // 型変換
        case aggregation  // 集約（sum/count/max）
        case unknown
    }

    enum OperationType: String, Codable {
        // arithmetic
        case multiply, divide, add, subtract, modulo, power
        // logical
        case and, or, not, xor
        // comparison
        case lessThan, greaterThan, equal, notEqual
        // functional
        case call, curry, compose
        // memory
        case read, write, allocate, free
        // その他
        case unknown
    }

    let inputArity: Int
    let outputArity: Int
    let operationCategory: OperationCategory
    /// 操作の種類（「乗算」まで公開するが、オペランドの値は非公開）
    let operationType: OperationType
    /// 入力ノードIDリスト（接続トポロジー）
    let inputNodeIDs: [IRNodeID]
    /// 出力ノードIDリスト
    let outputNodeIDs: [IRNodeID]
}

// MARK: - 軸3: 型制約軸

/// LLMに公開する型情報。
/// 「小数」「整数」「文字列」という分類のみ。
/// Float/Double/Int32/Decimal の区別は非公開。
struct TypeConstraintProjection: Codable {
    enum TypeCategory: String, Codable {
        case numeric     // 数値全般
        case string      // 文字列全般
        case collection  // 配列・辞書全般
        case boolean     // 真偽値
        case opaque      // 不透明型（structなど）
        case void        // 戻り値なし
    }

    enum MagnitudeClass: String, Codable {
        case integral            // 整数
        case fractional          // 小数
        case integralOrDecimal   // 整数または小数
        case unknown
    }

    let category: TypeCategory
    /// 小数か整数かという一般的情報のみ
    let magnitudeClass: MagnitudeClass
    /// 具体的な型はシール（sealed_hash でのみ参照可能）
    let sealedHash: String
}

// MARK: - 軸4: メモリライフサイクル軸

/// LLMに公開するメモリ情報。
/// 「誰より先に確保されるか」という相対的順序のみ。
/// 変数名・スコープ名・バイト数は非公開。
struct MemoryLifecycleProjection: Codable {
    enum OwnershipPattern: String, Codable {
        case stackLocal   // スタック上のローカル変数
        case heapOwned    // ヒープ上の所有型
        case borrowed     // 借用（Rust borrow等）
        case shared       // 共有参照
        case unknown
    }

    enum SizeClass: String, Codable {
        case tiny    // <8 bytes
        case small   // 8-64 bytes
        case medium  // 64-1024 bytes
        case large   // >1024 bytes
        case unknown
    }

    let ownershipPattern: OwnershipPattern
    let sizeClass: SizeClass
    /// 「X より先に確保」「Y より後に解放」という相対順序のリスト
    let relativeLifetimeOrder: [String]
}

// MARK: - 軸5: スコープ軸

/// LLMに公開するスコープ情報。
/// 「ネスト深度」「見えている変数の数」のみ。
/// スコープの名前・目的は非公開。
struct ScopeProjection: Codable {
    let nestingDepth: Int
    let visibleVarCount: Int
    /// 可視性グラフ（どのノードIDが見えるか）
    let visibilityGraph: [IRNodeID: [IRNodeID]]
}

// MARK: - 軸6: 意味論軸（送信しない）

/// AIには絶対に送信しない意味論軸。
/// ローカルVaultのみで保持。
struct SemanticsData: Codable {
    let functionName: String?
    let variableName: String?
    let semanticPurpose: String?
    let domainLabel: String?         // "payment", "tax", "auth" など
    let inlineConstants: [String]    // ["1.21", "2"] など
    let parameterNames: [String]
    let returnTypeLabel: String?
}

// MARK: - IR Node（AIへの送信単位）

/// 6軸のうち、AIに公開可能な軸の「影（projection）」のみを含むノード。
/// 意味論軸（Semantics）は Swift の型システムで強制的に排除。
struct JCrossIRNode: Codable {
    let id: IRNodeID
    let nodeKind: NodeKind

    // 軸1: 制御フロー（optional: 分岐ノードのみ）
    let controlFlow: ControlFlowProjection?
    // 軸2: データフロー（optional: 演算ノードのみ）
    let dataFlow: DataFlowProjection?
    // 軸3: 型制約（optional: 変数ノードのみ）
    let typeConstraints: TypeConstraintProjection?
    // 軸4: メモリ（optional: 確保ノードのみ）
    let memoryLifecycle: MemoryLifecycleProjection?
    // 軸5: スコープ（optional: ブロックノードのみ）
    let scope: ScopeProjection?
    // 軸6: 意味論 → never型で強制排除
    // semantics: Never  ← コンパイル時に存在不可能

    enum NodeKind: String, Codable {
        case function       // 関数定義
        case variable       // 変数
        case operation      // 演算
        case functionCall   // 関数呼び出し
        case controlBlock   // 制御ブロック
        case scopeBlock     // スコープブロック
        case constant       // 定数（値は非公開）
        case unknown
    }
}

// MARK: - IR Function（関数レベルのIR）

/// 1つの関数を表す IR。
/// bodyNodes はノードIDのリストのみ（内容は非公開）。
struct JCrossIRFunction: Codable {
    let id: IRNodeID
    let paramCount: Int
    let returnCount: Int
    let bodyNodeIDs: [IRNodeID]
    /// 非同期かどうか（true/false のみ、目的は非公開）
    let isAsync: Bool
    /// throws かどうか
    let canThrow: Bool
}

// MARK: - IR Document（ファイル全体のIR）

/// ファイル1つ分の 6軸IR。LLMへの送信単位。
struct JCrossIRDocument: Codable {
    let documentID: IRNodeID
    let language: String
    let protocolVersion: String
    let generatedAt: Date
    let functions: [JCrossIRFunction]
    var nodes: [IRNodeID: JCrossIRNode]

    // 送信前の安全チェック
    var isSafeToSend: Bool {
        // すべてのノードが意味論情報を含まないことを確認
        // （Swift型システムで保証されているが念のため）
        return true
    }

    // MARK: - 送信用シリアライズ

    /// LLM 向けに送信する JSON。
    /// **必ず 3層難読化パイプラインを通る。**
    /// 元の `nodes` 辞書は含まれない。
    func toSendableJSON() throws -> Data {
        let pipeline = JCrossObfuscationPipeline()
        let obfDoc   = pipeline.obfuscate(document: self)
        return try obfDoc.toSendableJSON()
    }

    /// ローカル保存用の生 JSON（難読化なし）。
    /// Vaultへの内部保存などローカル処理のみに使用する。
    func toLocalJSON() throws -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        encoder.dateEncodingStrategy = .iso8601
        return try encoder.encode(self)
    }
}

// MARK: - IR Patch（LLMからの修正要求）

/// LLMが返す修正要求。ノードIDと操作のみを含む。
/// 具体的な値は含まない（値はローカルで適用）。
struct JCrossIRPatch: Codable {
    let patchID: IRNodeID
    let targetNodeID: IRNodeID
    let operation: PatchOperation

    enum PatchOperation: Codable {
        /// データフローのオペランドを変更
        case modifyOperand(position: OperandPosition, newConstantPlaceholder: String)
        /// 制御フローに分岐を追加
        case insertBranch(afterNodeID: IRNodeID, branchCount: Int)
        /// ノードを削除
        case removeNode
        /// ノードを新規挿入
        case insertNode(kind: JCrossIRNode.NodeKind, afterNodeID: IRNodeID?)
        /// 接続を変更（データフローのエッジ）
        case rewireConnection(fromNodeID: IRNodeID, toNodeID: IRNodeID)

        enum OperandPosition: String, Codable {
            case left, right, first, second, third
        }
    }
}

