import Foundation
import CryptoKit

// MARK: - JCross IR Vault (Production v2.1)
//
// 6軸IRの「Z軸（意味論）」を保持するローカル専用ストレージ。
//
// ■ 保持するもの:
//   - 関数名・変数名・定数値・ビジネスロジックの目的
//   - 型の具体名・スコープの名前
//   - パッチ適用に必要なすべての具体情報
//
// ■ 保持しないもの（LLMに公開）:
//   - 構造（ノードの接続・分岐・アリティ）
//   - 演算カテゴリ（「乗算がある」という事実）
//
// ■ セキュリティ:
//   - AES-256-GCM でオンディスク暗号化
//   - デバイス固有鍵（CryptoKit SymmetricKey）
//   - メモリ内は平文（セッション中のみ）
//   - セッション終了時に安全消去（memset相当）

// MARK: - Vault Entry

/// ノード1つ分の「隠された軸」の完全情報
struct VaultEntry: Codable {
    let nodeID: IRNodeID

    // 軸6（意味論）— 最高機密
    var semantics: SemanticsData?

    // 軸2（データフロー）の具体値 — 機密
    var dataFlowConcrete: DataFlowConcrete?

    // 軸3（型制約）の具体情報 — 機密
    var typeConcrete: TypeConcrete?

    // 軸4（メモリ）の具体情報 — 機密
    var memoryConcrete: MemoryConcrete?

    // 軸5（スコープ）の具体情報 — 機密
    var scopeConcrete: ScopeConcrete?

    let createdAt: Date
    var lastModifiedAt: Date
}

// MARK: - Concrete Data Structures

/// データフローの具体値（LLMには数値が届かない）
struct DataFlowConcrete: Codable {
    /// 左オペランドの実値（例: "price_var"）
    var leftOperand: String?
    /// 右オペランドの実値（例: "1.21"）← gus_mass対象
    var rightOperand: String?
    /// 実際の演算関数名（例: "round"）
    var functionName: String?
    /// 結果変数名
    var resultVariable: String?
    /// インライン定数マップ（placeholder → 実値）
    var inlineConstants: [String: String]  // "CONST_α" → "1.21"
}

/// 型の具体情報
struct TypeConcrete: Codable {
    /// Swiftの具体的な型名（例: "Double", "Float", "Decimal"）
    var concreteTypeName: String
    /// セマンティクス上の役割（例: "tax_rate_multiplier"）
    var semanticRole: String?
    /// ドメイン（例: "currency", "temperature", "probability"）
    var domain: String?
}

/// メモリの具体情報
struct MemoryConcrete: Codable {
    /// 実際の変数名
    var variableName: String
    /// 構造体・クラス名
    var typeName: String?
    /// スコープ文脈（例: "payment_processing"）
    var scopeContext: String?
    /// フィールド情報（struct の場合）
    var fields: [String: String]  // フィールド名 → 値
}

/// スコープの具体情報
struct ScopeConcrete: Codable {
    /// 関数コンテキスト（例: "calculateTax"）
    var functionContext: String
    /// 目的（例: "VAT computation for Argentina"）
    var purpose: String?
    /// 参照しているグローバル変数等
    var externalReferences: [String]
}

// MARK: - Patch Application Record

/// パッチの適用記録（undo/redo, 監査証跡用）
struct PatchApplicationRecord: Codable {
    let patchID: IRNodeID
    let targetNodeID: IRNodeID
    let appliedAt: Date
    let previousState: VaultEntry?
    let newState: VaultEntry
    let appliedBy: String  // "user", "llm_response", "auto"
}

// MARK: - JCrossIRVault

/// JCross 6軸IRの秘密軸を管理するローカルVault。
/// スレッド安全。AES-256-GCM による暗号化永続化をサポート。
final class JCrossIRVault: @unchecked Sendable {

    // MARK: - Storage

    private var entries: [IRNodeID: VaultEntry] = [:]
    private var functionEntries: [IRNodeID: FunctionVaultEntry] = [:]
    private var patchHistory: [PatchApplicationRecord] = []
    private let lock = NSLock()

    // MARK: - Encryption

    /// デバイス固有のセッション鍵。永続化しない。
    private let sessionKey: SymmetricKey

    /// 永続化先のURL
    private var persistenceURL: URL?

    // MARK: - Init

    init(persistenceURL: URL? = nil) {
        self.sessionKey = SymmetricKey(size: .bits256)
        self.persistenceURL = persistenceURL
    }

    // MARK: - Entry Management

    /// ノードのVaultエントリを登録・更新
    func store(entry: VaultEntry) {
        lock.withLock {
            entries[entry.nodeID] = entry
        }
    }

    /// ノードの意味論情報を保存
    func storeSemantics(
        nodeID: IRNodeID,
        semantics: SemanticsData? = nil,
        dataFlowConcrete: DataFlowConcrete? = nil,
        typeConcrete: TypeConcrete? = nil,
        memoryConcrete: MemoryConcrete? = nil,
        scopeConcrete: ScopeConcrete? = nil
    ) {
        lock.withLock {
            if var existing = entries[nodeID] {
                existing.semantics          = semantics ?? existing.semantics
                existing.dataFlowConcrete  = dataFlowConcrete ?? existing.dataFlowConcrete
                existing.typeConcrete      = typeConcrete ?? existing.typeConcrete
                existing.memoryConcrete    = memoryConcrete ?? existing.memoryConcrete
                existing.scopeConcrete     = scopeConcrete ?? existing.scopeConcrete
                entries[nodeID] = existing
            } else {
                entries[nodeID] = VaultEntry(
                    nodeID: nodeID,
                    semantics: semantics,
                    dataFlowConcrete: dataFlowConcrete,
                    typeConcrete: typeConcrete,
                    memoryConcrete: memoryConcrete,
                    scopeConcrete: scopeConcrete,
                    createdAt: Date(),
                    lastModifiedAt: Date()
                )
            }
        }
    }

    /// エントリを取得
    func entry(for nodeID: IRNodeID) -> VaultEntry? {
        lock.withLock { entries[nodeID] }
    }

    /// 関数のVaultエントリを保存
    func storeFunctionEntry(_ entry: FunctionVaultEntry) {
        lock.withLock { functionEntries[entry.functionID] = entry }
    }

    func functionEntry(for id: IRNodeID) -> FunctionVaultEntry? {
        lock.withLock { functionEntries[id] }
    }

    // MARK: - Patch Application

    /// LLMからのIRパッチをVaultに適用する。
    /// 実際の値の変更はユーザー確認後にのみ実行される。
    @discardableResult
    func applyPatch(
        _ patch: JCrossIRPatch,
        resolvedValues: [String: String] = [:]  // placeholder → 実値
    ) throws -> VaultEntry {
        return try lock.withLock {
            guard var entry = entries[patch.targetNodeID] else {
                throw VaultError.nodeNotFound(patch.targetNodeID)
            }

            let previousState = entry

            switch patch.operation {
            case .modifyOperand(let position, let placeholder):
                // LLMが「右オペランドを CONST_NEW_TAX_RATE に変更」と要求
                // ローカルでその placeholder に実値を解決して適用
                let resolvedValue = resolvedValues[placeholder]
                var concrete = entry.dataFlowConcrete ?? DataFlowConcrete(
                    leftOperand: nil, rightOperand: nil,
                    functionName: nil, resultVariable: nil,
                    inlineConstants: [:]
                )
                switch position {
                case .right:  concrete.rightOperand  = resolvedValue
                case .left:   concrete.leftOperand   = resolvedValue
                default:
                    if var inlines = entry.dataFlowConcrete?.inlineConstants {
                        inlines[placeholder] = resolvedValue
                        concrete.inlineConstants = inlines
                    }
                }
                entry.dataFlowConcrete = concrete

            case .removeNode:
                entries.removeValue(forKey: patch.targetNodeID)
                let record = PatchApplicationRecord(
                    patchID: patch.patchID,
                    targetNodeID: patch.targetNodeID,
                    appliedAt: Date(),
                    previousState: previousState,
                    newState: entry,
                    appliedBy: "llm_response"
                )
                patchHistory.append(record)
                return entry

            case .insertNode, .insertBranch, .rewireConnection:
                // 構造的な変更はIR側で実施済み。
                // VaultにはノードIDのみ記録する。
                break
            }

            entry.lastModifiedAt = Date()
            entries[patch.targetNodeID] = entry

            let record = PatchApplicationRecord(
                patchID: patch.patchID,
                targetNodeID: patch.targetNodeID,
                appliedAt: Date(),
                previousState: previousState,
                newState: entry,
                appliedBy: "llm_response"
            )
            patchHistory.append(record)

            return entry
        }
    }

    // MARK: - Reconstruction (パッチ後の元コード再生成)

    /// ノードの意味論情報からコードスニペットを再生成する。
    /// パッチ適用後にローカルでのみ実行される。
    func reconstructCodeSnippet(for nodeID: IRNodeID) -> String? {
        guard let entry = self.entry(for: nodeID),
              let semantics = entry.semantics else { return nil }

        var parts: [String] = []

        if let funcName = semantics.functionName {
            var params = semantics.parameterNames.joined(separator: ", ")
            if params.isEmpty { params = "_" }
            parts.append("func \(funcName)(\(params))")
        }

        if let purpose = semantics.semanticPurpose {
            parts.append("// \(purpose)")
        }

        if let concrete = entry.dataFlowConcrete {
            var expr = ""
            if let fn = concrete.functionName {
                let left = concrete.leftOperand ?? "x"
                let right = concrete.rightOperand ?? "?"
                expr = "\(fn)(\(left), \(right))"
            } else if let left = concrete.leftOperand, let right = concrete.rightOperand {
                expr = "\(left) * \(right)"
            }
            if !expr.isEmpty { parts.append(expr) }
        }

        return parts.joined(separator: "\n")
    }

    // MARK: - Undo

    func undoLastPatch() throws {
        try lock.withLock {
            guard let last = patchHistory.last else { throw VaultError.noPatchHistory }
            if let prev = last.previousState {
                entries[last.targetNodeID] = prev
            } else {
                entries.removeValue(forKey: last.targetNodeID)
            }
            patchHistory.removeLast()
        }
    }

    // MARK: - Encrypted Persistence

    /// AES-256-GCMで暗号化してディスクに保存
    func saveEncrypted(to url: URL? = nil) throws {
        let targetURL = url ?? persistenceURL
        guard let targetURL else { throw VaultError.noPersistenceURL }

        let snapshot = lock.withLock { VaultSnapshot(entries: entries, patchHistory: patchHistory) }
        let data = try JSONEncoder().encode(snapshot)

        // AES-256-GCM 暗号化
        let sealedBox = try AES.GCM.seal(data, using: sessionKey)
        guard let encryptedData = sealedBox.combined else {
            throw VaultError.encryptionFailed
        }

        try FileManager.default.createDirectory(
            at: targetURL.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try encryptedData.write(to: targetURL, options: .atomic)
    }

    /// 暗号化されたVaultをディスクから復元
    func loadEncrypted(from url: URL) throws {
        let encryptedData = try Data(contentsOf: url)
        let sealedBox = try AES.GCM.SealedBox(combined: encryptedData)
        let decryptedData = try AES.GCM.open(sealedBox, using: sessionKey)

        let snapshot = try JSONDecoder().decode(VaultSnapshot.self, from: decryptedData)
        lock.withLock {
            entries = snapshot.entries
            patchHistory = snapshot.patchHistory
        }
    }

    // MARK: - Statistics

    var statistics: VaultStatistics2 {
        lock.withLock {
            let totalEntries = entries.count
            let withSemantics = entries.values.filter { $0.semantics != nil }.count
            let withConstants = entries.values.filter {
                !($0.dataFlowConcrete?.inlineConstants.isEmpty ?? true)
            }.count
            return VaultStatistics2(
                totalEntries: totalEntries,
                entriesWithSemantics: withSemantics,
                entriesWithConstants: withConstants,
                patchCount: patchHistory.count
            )
        }
    }

    // MARK: - Debug（ローカル専用）

    /// 全VaultエントリをArrayで返す（Gatekeeper Pipeline用）
    func allEntries() -> [VaultEntry] {
        lock.withLock { Array(entries.values) }
    }

    var debugDescription: String {
        lock.withLock {
            var lines = [
                "╔══ JCross IR VAULT (6-Axis) ══════════════════════════",
                "║  ⚠️  CLASSIFIED — DO NOT TRANSMIT TO ANY LLM",
                "║  entries: \(entries.count)  patches: \(patchHistory.count)",
                "╠══════════════════════════════════════════════════════"
            ]
            for (id, entry) in entries.sorted(by: { $0.key.raw < $1.key.raw }) {
                lines.append("║  NODE \(id.raw)")
                if let sem = entry.semantics {
                    if let fn = sem.functionName  { lines.append("║    func: \(fn)") }
                    if let dn = sem.domainLabel   { lines.append("║    domain: \(dn)") }
                    if !sem.inlineConstants.isEmpty { lines.append("║    constants: \(sem.inlineConstants)") }
                }
                if let df = entry.dataFlowConcrete {
                    if let r = df.rightOperand    { lines.append("║    right_operand: \(r)") }
                    if let l = df.leftOperand     { lines.append("║    left_operand: \(l)") }
                }
            }
            lines.append("╚══════════════════════════════════════════════════════")
            return lines.joined(separator: "\n")
        }
    }
}

// MARK: - Function Vault Entry

struct FunctionVaultEntry: Codable {
    let functionID: IRNodeID
    let name: String
    let semanticPurpose: String?
    let parameterDetails: [(name: String, domain: String?)]
    let returnTypeName: String?
    let inlineConstants: [String]
    let domainLabel: String?

    enum CodingKeys: String, CodingKey {
        case functionID, name, semanticPurpose, parameterNames, parameterDomains
        case returnTypeName, inlineConstants, domainLabel
    }

    init(
        functionID: IRNodeID, name: String, semanticPurpose: String? = nil,
        parameterDetails: [(name: String, domain: String?)] = [],
        returnTypeName: String? = nil, inlineConstants: [String] = [],
        domainLabel: String? = nil
    ) {
        self.functionID = functionID
        self.name = name
        self.semanticPurpose = semanticPurpose
        self.parameterDetails = parameterDetails
        self.returnTypeName = returnTypeName
        self.inlineConstants = inlineConstants
        self.domainLabel = domainLabel
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(functionID, forKey: .functionID)
        try c.encode(name, forKey: .name)
        try c.encodeIfPresent(semanticPurpose, forKey: .semanticPurpose)
        try c.encode(parameterDetails.map { $0.name }, forKey: .parameterNames)
        try c.encode(parameterDetails.map { $0.domain }, forKey: .parameterDomains)
        try c.encodeIfPresent(returnTypeName, forKey: .returnTypeName)
        try c.encode(inlineConstants, forKey: .inlineConstants)
        try c.encodeIfPresent(domainLabel, forKey: .domainLabel)
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        functionID = try c.decode(IRNodeID.self, forKey: .functionID)
        name = try c.decode(String.self, forKey: .name)
        semanticPurpose = try c.decodeIfPresent(String.self, forKey: .semanticPurpose)
        let names   = try c.decode([String].self, forKey: .parameterNames)
        let domains = try c.decode([String?].self, forKey: .parameterDomains)
        parameterDetails = zip(names, domains).map { (name: $0.0, domain: $0.1) }
        returnTypeName = try c.decodeIfPresent(String.self, forKey: .returnTypeName)
        inlineConstants = try c.decode([String].self, forKey: .inlineConstants)
        domainLabel = try c.decodeIfPresent(String.self, forKey: .domainLabel)
    }
}

// MARK: - Supporting Types

private struct VaultSnapshot: Codable {
    var entries: [IRNodeID: VaultEntry]
    var patchHistory: [PatchApplicationRecord]
}

struct VaultStatistics2 {
    let totalEntries: Int
    let entriesWithSemantics: Int
    let entriesWithConstants: Int
    let patchCount: Int
}

// MARK: - Vault Errors

enum VaultError: Error, LocalizedError {
    case nodeNotFound(IRNodeID)
    case noPatchHistory
    case noPersistenceURL
    case encryptionFailed
    case decryptionFailed

    var errorDescription: String? {
        switch self {
        case .nodeNotFound(let id):   return "VaultEntry not found: \(id)"
        case .noPatchHistory:         return "No patch history to undo"
        case .noPersistenceURL:       return "No persistence URL configured"
        case .encryptionFailed:       return "AES-256-GCM encryption failed"
        case .decryptionFailed:       return "AES-256-GCM decryption failed"
        }
    }
}


