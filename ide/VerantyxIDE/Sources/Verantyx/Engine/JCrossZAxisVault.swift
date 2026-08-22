import Foundation

// MARK: - JCross Z-Axis Evidence Vault  (Production v2)
//
// 6軸立体十字構造の「Z軸（深度）」レイヤー。
//
// 設計原則:
//   1. ゼロ信頼 — リテラル値は絶対にこのVault外に出ない
//   2. 決定論的ID — 同一リテラルは常に同一IDにマップ (再現性)
//   3. スレッド安全 — NSLock による完全な排他制御
//   4. オーバーフロー耐性 — Base-62 エンコードで事実上無制限
//   5. 直列化可能 — セッションを Vault ごと保存・復元できる
//
// LLMが受け取るもの (X/Y平面のみ):
//   ⟨V1⟩ = ⟨F1⟩(⟨V2⟩ * ⟪CONST:a8f2⟫, ⟪CONST:b3c1⟫)
//
// ローカルVaultだけが知るもの (Z軸 Evidence):
//   CONST:a8f2 = 1.21   (taxRate: numericDecimal)
//   CONST:b3c1 = 2      (precision: numericSmall)
//
// ノイズ注入:
//   ⟪NOISE:x7k9⟫ を混入させることで、演算パターンからの
//   統計的リバースエンジニアリングを阻止する。
//   NOISEはVaultに値を持たないため、LLMが推論しても意味がない。

// MARK: - Literal Category

enum LiteralCategory: String, Codable, CaseIterable {
    case numericZeroOne       // 0 or 1 (loop counter — low sensitivity)
    case numericSmall         // 2–99 integer
    case numericDecimal       // float with decimal point (tax rates, ratios)
    case numericLarge         // ≥1000 integer (port numbers, timeouts)
    case numericHex           // 0x... hexadecimal
    case numericBinary        // 0b... binary
    case numericOctal         // 0o... octal
    case numericScientific    // 1.21e5 scientific notation
    case numericNegative      // negative numbers
    case stringShort          // string literal < 30 chars
    case stringLong           // string literal ≥ 30 chars
    case booleanLiteral       // true / false
    case unknown

    /// 感度スコア: 高いほどマスキングが重要
    var sensitivityScore: Int {
        switch self {
        case .numericDecimal:    return 10  // 税率・利率 → 最高優先
        case .numericLarge:      return 8   // ポート番号・タイムアウト
        case .numericHex:        return 8   // バイナリ定数・フラグ
        case .numericScientific: return 7
        case .numericNegative:   return 6
        case .stringShort:       return 6
        case .stringLong:        return 5
        case .numericSmall:      return 4
        case .numericBinary:     return 3
        case .numericOctal:      return 3
        case .booleanLiteral:    return 1
        case .numericZeroOne:    return 0   // マスク不要
        case .unknown:           return 2
        }
    }
}

// MARK: - Evidence Node

struct ZAxisEvidenceNode: Codable {
    /// JCross上の匿名ID  例: "CONST:a8f2"
    let constID: String
    /// 実際のリテラル値 (ローカル専用)
    let rawValue: String
    /// セマンティクスカテゴリ
    let category: LiteralCategory
    /// 出現回数 (同一値の頻度分析用)
    var occurrenceCount: Int
    /// 生成日時
    let createdAt: Date

    /// このノードをLLMに渡してよいか (false = 絶対に送信しない)
    var isSendable: Bool { false }
}

// MARK: - Vault Statistics

struct VaultStatistics {
    let totalNodes: Int
    let noiseNodeCount: Int
    let sensitiveNodeCount: Int
    let categoryBreakdown: [LiteralCategory: Int]
    let averageSensitivity: Double
}

// MARK: - JCross Z-Axis Vault  (Production)

/// Z軸リテラル隔離ボルト。
/// スレッド安全 (NSLock)。セッション単位でインスタンス化する。
final class JCrossZAxisVault: @unchecked Sendable {

    // MARK: - Storage

    private var evidences:    [String: ZAxisEvidenceNode] = [:]  // constID → node
    private var valueIndex:   [String: String]            = [:]  // rawValue → constID (重複防止)
    private var noiseIDs:     Set<String>                 = []
    private let lock = NSLock()

    // 採番カウンター
    private var evidenceCounter: Int = 0
    private var noiseCounter:    Int = 0

    // セッション固有のプレフィックス (同一値でも異なるセッションでは別ID)
    private let sessionPrefix: String

    // MARK: - Configuration

    /// 最小感度スコア: これ未満の値はマスクしない (0=すべてマスク)
    var minimumSensitivityThreshold: Int = 1

    /// ノイズ密度: 1行あたりの最大ノイズノード数
    var noiseDensity: Int = 2

    // MARK: - Init

    init(sessionPrefix: String = String(UUID().uuidString.prefix(4).lowercased())) {
        self.sessionPrefix = sessionPrefix
    }

    // MARK: - Public API

    /// リテラル値をVaultに格納し、匿名ID (⟪CONST:xxxx⟫ の中の "CONST:xxxx") を返す。
    /// 同一セッション内で同じ生値は必ず同じIDにマップされる。
    /// 感度スコアが閾値未満の場合は nil を返す (マスク不要と判断)。
    func store(rawValue: String, category: LiteralCategory) -> String? {
        guard category.sensitivityScore >= minimumSensitivityThreshold else { return nil }

        return lock.withLock {
            // 既存エントリがあれば再利用 (同一値 → 同一ID)
            if let existing = valueIndex[rawValue] {
                evidences[existing]?.occurrenceCount += 1
                return existing
            }

            // 新規登録
            evidenceCounter += 1
            let shortHash = compactID(evidenceCounter)
            let constID = "CONST:\(sessionPrefix)\(shortHash)"

            let node = ZAxisEvidenceNode(
                constID: constID,
                rawValue: rawValue,
                category: category,
                occurrenceCount: 1,
                createdAt: Date()
            )
            evidences[constID] = node
            valueIndex[rawValue] = constID
            return constID
        }
    }

    /// ノイズIDを生成する。
    /// ノイズはVaultに値を持たない — LLMが推論しても何も得られない。
    func generateNoiseID() -> String {
        return lock.withLock {
            noiseCounter += 1
            let noiseID = "NOISE:\(sessionPrefix)\(compactID(noiseCounter + 10000))"
            noiseIDs.insert(noiseID)
            return noiseID
        }
    }

    /// IDがノイズかどうか判定する。
    func isNoise(_ id: String) -> Bool {
        id.hasPrefix("NOISE:")
    }

    /// IDがリテラル定数かどうか判定する。
    func isConstant(_ id: String) -> Bool {
        id.hasPrefix("CONST:")
    }

    /// 登録済みの生値を返す (アンマスク用)。
    func rawValue(for constID: String) -> String? {
        lock.withLock { evidences[constID]?.rawValue }
    }

    /// アンマスク用の逆引きマップ (constID → rawValue)。
    var restoreMap: [String: String] {
        lock.withLock {
            evidences.compactMapValues { $0.rawValue }
        }
    }

    /// ノイズIDの全セット。
    var allNoiseIDs: Set<String> {
        lock.withLock { noiseIDs }
    }

    // MARK: - Statistics

    var statistics: VaultStatistics {
        lock.withLock {
            var breakdown: [LiteralCategory: Int] = [:]
            var totalSensitivity = 0
            let sensitive = evidences.values.filter { $0.category.sensitivityScore >= 6 }.count

            for node in evidences.values {
                breakdown[node.category, default: 0] += 1
                totalSensitivity += node.category.sensitivityScore
            }
            let avg = evidences.isEmpty ? 0.0 : Double(totalSensitivity) / Double(evidences.count)

            return VaultStatistics(
                totalNodes: evidences.count,
                noiseNodeCount: noiseIDs.count,
                sensitiveNodeCount: sensitive,
                categoryBreakdown: breakdown,
                averageSensitivity: avg
            )
        }
    }

    // MARK: - Serialization (セッション永続化)

    struct SerializedVault: Codable {
        let sessionPrefix: String
        let evidences: [String: ZAxisEvidenceNode]
        let valueIndex: [String: String]
        let noiseIDs: [String]
        let evidenceCounter: Int
        let noiseCounter: Int
    }

    func serialize() -> Data? {
        lock.withLock {
            let sv = SerializedVault(
                sessionPrefix: sessionPrefix,
                evidences: evidences,
                valueIndex: valueIndex,
                noiseIDs: Array(noiseIDs),
                evidenceCounter: evidenceCounter,
                noiseCounter: noiseCounter
            )
            return try? JSONEncoder().encode(sv)
        }
    }

    static func deserialize(from data: Data) -> JCrossZAxisVault? {
        guard let sv = try? JSONDecoder().decode(SerializedVault.self, from: data) else { return nil }
        let vault = JCrossZAxisVault(sessionPrefix: sv.sessionPrefix)
        vault.evidences = sv.evidences
        vault.valueIndex = sv.valueIndex
        vault.noiseIDs = Set(sv.noiseIDs)
        vault.evidenceCounter = sv.evidenceCounter
        vault.noiseCounter = sv.noiseCounter
        return vault
    }

    // MARK: - Debug (ローカル専用・LLMに渡してはならない)

    var debugDescription: String {
        lock.withLock {
            var lines = [
                "╔══ Z-AXIS EVIDENCE VAULT ══════════════════════════════",
                "║  SESSION: \(sessionPrefix)  NODES: \(evidences.count)  NOISE: \(noiseIDs.count)",
                "║  ⚠️  LOCAL ONLY — DO NOT SEND TO ANY LLM OR EXTERNAL SERVICE",
                "╠══════════════════════════════════════════════════════"
            ]
            for node in evidences.values.sorted(by: { $0.constID < $1.constID }) {
                let sensitivity = node.category.sensitivityScore
                let stars = String(repeating: "★", count: min(sensitivity, 5))
                lines.append("║  \(node.constID)  =  \"\(node.rawValue)\"")
                lines.append("║     [\(node.category.rawValue)]  sensitivity:\(sensitivity)\(stars)  ×\(node.occurrenceCount)")
            }
            lines.append("╚══════════════════════════════════════════════════════")
            return lines.joined(separator: "\n")
        }
    }

    // MARK: - ID Generation (Base-62, overflow-safe)
    // 0-9, a-z, A-Z の62文字。カウンター無制限。

    private static let base62chars = Array("0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")

    private func compactID(_ n: Int) -> String {
        guard n > 0 else { return "0" }
        var result = ""
        var value = n
        let base = Self.base62chars.count
        while value > 0 {
            result = String(Self.base62chars[value % base]) + result
            value /= base
        }
        // 最低4文字にパディング
        while result.count < 4 { result = "0" + result }
        return result
    }
}


