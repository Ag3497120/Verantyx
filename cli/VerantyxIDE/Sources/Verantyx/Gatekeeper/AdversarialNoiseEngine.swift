import Foundation

// MARK: - AdversarialNoiseEngine
//
// コンテキスト断片化（Context Fragmentation）と
// 意図的ノイズ注入（Adversarial Noise Injection）を担当するエンジン。
//
// 役割:
//   1. ASTベースのフラグメント計画を立案
//   2. カモフラージュドメインを選択し、ダミー構造を生成
//   3. 実ノード/ダミーノードのIDシャッフルマップを生成
//   4. Claudeへの送信IRを構築
//
// セキュリティ原則:
//   - ダミーノードは「構造的に同型 (Structural Isomorph)」なドメインから生成
//   - 実ノードとダミーノードはランダム順序で混合
//   - セッションごとに異なるIDシャッフルマップを使用

@MainActor
final class AdversarialNoiseEngine {

    // MARK: - Fragment Plan

    struct FragmentPlan {
        let sessionID: String
        let fragments: [Fragment]
        let totalRealCount: Int
        let totalDummyCount: Int
        let selectedDomain: RoutingSessionLogger.CamouflageDomain
        let idShuffleMap: [String: String]     // nodeID → claudeAlias
        let reverseShuffleMap: [String: String] // claudeAlias → nodeID

        var noiseRatio: Double {
            guard totalRealCount + totalDummyCount > 0 else { return 0 }
            return Double(totalDummyCount) / Double(totalRealCount + totalDummyCount)
        }
    }

    struct Fragment {
        let sequenceNumber: Int
        let nodeID: String
        let claudeAlias: String
        let kind: RoutingSessionLogger.FragmentKind
        let domain: RoutingSessionLogger.CamouflageDomain?
        let irContent: String   // このフラグメントのJCross IR内容
        let role: String
    }

    // MARK: - Properties

    private let schemaGenerator: JCrossSchemaGenerator
    private var rng = SystemRandomNumberGenerator()

    // セッション → シャッフルマップ (deep/に永続化)
    private var shuffleHistory: [String: [String: String]] = [:]

    // MARK: - Init

    init() {
        self.schemaGenerator = JCrossSchemaGenerator()
    }

    // MARK: - Main: Plan Fragmentation

    /// ソースコードのJCross IRを受け取り、フラグメント計画を立案する
    /// - Parameters:
    ///   - jcrossIR: PolymorphicJCrossTranspilerが生成したJCross IR
    ///   - nodeMap: nodeID → claudeAlias の元のマッピング
    ///   - noiseLevel: 0=なし, 1=軽微(20%), 2=中程度(40%), 3=強(60%)
    ///   - maxFragmentsPerSession: 1セッションで送る最大フラグメント数
    func planFragmentation(
        sessionID: String,
        jcrossIR: String,
        nodeIDs: [String],
        noiseLevel: Int = 2,
        maxFragmentsPerSession: Int = 8
    ) async -> FragmentPlan {

        // 1. カモフラージュドメインをドメイン推測に基づき選択
        let domain = selectCamouflageDomain(for: jcrossIR)

        // 2. 実ノードを機能ロールに分類
        let roleMap = classifyNodeRoles(jcrossIR: jcrossIR, nodeIDs: nodeIDs)

        // 3. Dynamic ID Shuffle — 実ノードに新しいエイリアスを割り当て
        let (idShuffleMap, reverseShuffleMap) = generateIDShuffleMap(
            nodeIDs: nodeIDs,
            sessionID: sessionID
        )

        // 4. ダミーノードを生成
        let dummyCount = calculateDummyCount(realCount: nodeIDs.count, noiseLevel: noiseLevel)
        let dummyFragments = generateDummyFragments(
            count: dummyCount,
            domain: domain,
            startSeq: nodeIDs.count + 1
        )

        // 5. 実フラグメントを構築
        var realFragments: [Fragment] = nodeIDs.enumerated().map { (i, nodeID) in
            let alias = idShuffleMap[nodeID] ?? nodeID
            let role = roleMap[nodeID] ?? "unknown"
            let ir = extractIRFragment(jcrossIR: jcrossIR, nodeID: nodeID, alias: alias)
            return Fragment(
                sequenceNumber: i + 1,
                nodeID: nodeID,
                claudeAlias: alias,
                kind: .real,
                domain: nil,
                irContent: ir,
                role: role
            )
        }

        // 6. 実フラグメントをランダムにシャッフル (送信順を予測不能に)
        realFragments.shuffle(using: &rng)

        // 7. ダミーをランダム位置に挿入
        let allFragments = interleaveWithDummies(real: realFragments, dummies: dummyFragments)

        // IDシャッフルマップを永続化
        shuffleHistory[sessionID] = idShuffleMap

        return FragmentPlan(
            sessionID: sessionID,
            fragments: allFragments,
            totalRealCount: realFragments.count,
            totalDummyCount: dummyFragments.count,
            selectedDomain: domain,
            idShuffleMap: idShuffleMap,
            reverseShuffleMap: reverseShuffleMap
        )
    }

    // MARK: - Domain Selection (ドメイン推測に基づくカモフラージュ選択)

    private func selectCamouflageDomain(for jcrossIR: String) -> RoutingSessionLogger.CamouflageDomain {
        let lower = jcrossIR.lowercased()

        // ドメイン推測スコア
        var scores: [RoutingSessionLogger.CamouflageDomain: Int] = [:]

        // 金融・税務パターンを検出 → 軌道力学でカモフラージュ
        let financeKeywords = ["tax", "salary", "payment", "invoice", "price", "rate", "amount", "fee", "account", "budget"]
        if financeKeywords.contains(where: { lower.contains($0) }) {
            scores[.orbitalMechanics, default: 0] += 3
        }

        // 認証・セキュリティパターン → 信号処理でカモフラージュ
        let authKeywords = ["auth", "token", "password", "session", "login", "permission", "role", "access"]
        if authKeywords.contains(where: { lower.contains($0) }) {
            scores[.signalProcessing, default: 0] += 3
        }

        // データ処理・時系列 → 計算流体力学でカモフラージュ
        let dataKeywords = ["fetch", "load", "parse", "transform", "filter", "aggregate", "map", "reduce"]
        if dataKeywords.contains(where: { lower.contains($0) }) {
            scores[.fluidDynamics, default: 0] += 3
        }

        // 配列・コレクション操作 → 計算生物学でカモフラージュ
        let arrayKeywords = ["array", "list", "sequence", "iterate", "sort", "search", "index", "match"]
        if arrayKeywords.contains(where: { lower.contains($0) }) {
            scores[.computationalBio, default: 0] += 3
        }

        // デフォルト: 軌道力学 (最も汎用的)
        let best = scores.max(by: { $0.value < $1.value })?.key ?? .orbitalMechanics
        return best
    }

    // MARK: - Node Role Classification

    private func classifyNodeRoles(jcrossIR: String, nodeIDs: [String]) -> [String: String] {
        var roles: [String: String] = [:]
        let lines = jcrossIR.components(separatedBy: "\n")

        for nodeID in nodeIDs {
            let matchingLines = lines.filter { $0.contains(nodeID) }
            let combined = matchingLines.joined(separator: " ").lowercased()

            if combined.contains("func") || combined.contains("def") || combined.contains("fn ") {
                roles[nodeID] = "func_definition"
            } else if combined.contains("return") {
                roles[nodeID] = "return_value"
            } else if combined.contains("param") || combined.contains("arg") {
                roles[nodeID] = "parameter"
            } else if combined.contains("init") || combined.contains("constructor") {
                roles[nodeID] = "initializer"
            } else {
                roles[nodeID] = "variable_or_property"
            }
        }

        return roles
    }

    // MARK: - Dynamic ID Shuffling

    private func generateIDShuffleMap(
        nodeIDs: [String],
        sessionID: String
    ) -> (shuffle: [String: String], reverse: [String: String]) {
        // セッションIDからシードを生成
        let seed = sessionID.utf8.reduce(0) { $0 &+ UInt64($1) }
        var seededRng = SeededRNG(seed: seed &+ UInt64(Date().timeIntervalSince1970))

        let aliasPool = generateAliasPool(count: nodeIDs.count * 3, rng: &seededRng)
        var usedAliases: Set<String> = []
        var shuffle: [String: String] = [:]
        var reverse: [String: String] = [:]

        for nodeID in nodeIDs {
            var alias = aliasPool.randomElement(using: &seededRng) ?? nodeID
            while usedAliases.contains(alias) {
                alias = aliasPool.randomElement(using: &seededRng) ?? nodeID
            }
            usedAliases.insert(alias)
            shuffle[nodeID] = alias
            reverse[alias] = nodeID
        }

        return (shuffle, reverse)
    }

    private func generateAliasPool(count: Int, rng: inout SeededRNG) -> [String] {
        let chars1 = Array("ABCDEFGHJKLMNPQRSTUVWXYZ")
        let chars2 = Array("ABCDEFGHJKLMNPQRSTUVWXYZ")
        let digits = Array("0123456789")

        return (0..<count).map { _ in
            let c1 = chars1.randomElement(using: &rng)!
            let c2 = chars2.randomElement(using: &rng)!
            let n1 = digits.randomElement(using: &rng)!
            let n2 = digits.randomElement(using: &rng)!
            let n3 = digits.randomElement(using: &rng)!
            return "\(c1)\(c2)\(n1)\(n2)\(n3)"
        }
    }

    // MARK: - Dummy Fragment Generation

    private func generateDummyFragments(
        count: Int,
        domain: RoutingSessionLogger.CamouflageDomain,
        startSeq: Int
    ) -> [Fragment] {
        let pool = domain.tokenPool
        guard !pool.isEmpty else { return [] }

        return (0..<count).map { i in
            let token1 = pool.randomElement() ?? "vectorField"
            let token2 = pool.randomElement() ?? "scalarValue"
            let dummyID = "DUMMY_\(domain.rawValue.prefix(3).uppercased())_\(String(format: "%03d", i + 1))"
            let dummyAlias = generateDummyAlias(index: i)

            // カモフラージュ域の構造的に同型なIRを生成
            let irContent = generateDomainSpecificIR(
                domain: domain,
                token1: token1,
                token2: token2,
                alias: dummyAlias
            )

            return Fragment(
                sequenceNumber: startSeq + i,
                nodeID: dummyID,
                claudeAlias: dummyAlias,
                kind: .dummy,
                domain: domain,
                irContent: irContent,
                role: "camouflage_decoy"
            )
        }
    }

    private func generateDummyAlias(index: Int) -> String {
        let prefixes = ["PHY", "SIG", "FLD", "BIO", "GAM"]
        let prefix = prefixes[index % prefixes.count]
        return "\(prefix)_\(String(format: "%04X", Int.random(in: 0...65535)))"
    }

    /// ドメイン固有の構造的同型IRを生成
    private func generateDomainSpecificIR(
        domain: RoutingSessionLogger.CamouflageDomain,
        token1: String,
        token2: String,
        alias: String
    ) -> String {
        switch domain {
        case .orbitalMechanics:
            return """
            // [decoy-orbital]
            \(alias) = COMPUTE(\(token1) * \(token2) / CONST_G)
            if \(alias) > PERIHELION_THRESHOLD { ADJUST(\(alias)) }
            """
        case .signalProcessing:
            return """
            // [decoy-signal]
            \(alias) = FFT_APPLY(\(token1), windowSize: \(token2))
            NORMALIZE(\(alias), scale: NYQUIST_RATE)
            """
        case .fluidDynamics:
            return """
            // [decoy-fluid]
            \(alias) = REYNOLDS(\(token1)) * \(token2)
            PRESSURE_GRADIENT += \(alias) * VISCOSITY_COEFF
            """
        case .computationalBio:
            return """
            // [decoy-bio]
            \(alias) = ALIGN(\(token1), against: \(token2), gap: GAP_PENALTY)
            SCORE += SMITH_WATERMAN(\(alias))
            """
        case .gamePhysics:
            return """
            // [decoy-physics]
            \(alias) = IMPULSE(\(token1), mass: \(token2))
            VERLET_INTEGRATE(\(alias), dt: PHYSICS_TIMESTEP)
            """
        case .none:
            return "// [no-decoy]"
        }
    }

    // MARK: - Fragment IR Extraction

    private func extractIRFragment(jcrossIR: String, nodeID: String, alias: String) -> String {
        // nodeIDを含む行とその前後3行を抽出
        let lines = jcrossIR.components(separatedBy: "\n")
        var result: [String] = []

        for (i, line) in lines.enumerated() {
            if line.contains(nodeID) {
                let start = max(0, i - 2)
                let end = min(lines.count - 1, i + 3)
                result.append(contentsOf: lines[start...end])
                result.append("---")
            }
        }

        // nodeIDをclaudeAliasに置換 (これがClaudeに見えるもの)
        let fragmentContent = result.joined(separator: "\n")
        return fragmentContent.replacingOccurrences(of: nodeID, with: alias)
    }

    // MARK: - Interleaving

    private func interleaveWithDummies(real: [Fragment], dummies: [Fragment]) -> [Fragment] {
        guard !dummies.isEmpty else { return real.enumerated().map { (i, f) in
            Fragment(sequenceNumber: i + 1, nodeID: f.nodeID, claudeAlias: f.claudeAlias,
                     kind: f.kind, domain: f.domain, irContent: f.irContent, role: f.role)
        }}

        var combined = real + dummies
        combined.shuffle(using: &rng)

        // シーケンス番号を再割り当て
        return combined.enumerated().map { (i, f) in
            Fragment(sequenceNumber: i + 1, nodeID: f.nodeID, claudeAlias: f.claudeAlias,
                     kind: f.kind, domain: f.domain, irContent: f.irContent, role: f.role)
        }
    }

    // MARK: - Noise Level Calculation

    private func calculateDummyCount(realCount: Int, noiseLevel: Int) -> Int {
        switch noiseLevel {
        case 0: return 0
        case 1: return max(1, realCount / 4)   // ~20%
        case 2: return max(2, realCount / 2)   // ~40%
        case 3: return max(3, realCount)       // ~50%
        default: return max(2, realCount / 2)
        }
    }

    // MARK: - Shuffle Map Retrieval (for ReverseTranspiler)

    func reverseShuffleMap(for sessionID: String) -> [String: String] {
        guard let forward = shuffleHistory[sessionID] else { return [:] }
        // reverse: alias → nodeID
        return Dictionary(uniqueKeysWithValues: forward.map { ($0.value, $0.key) })
    }

    func clearShuffleHistory(for sessionID: String) {
        shuffleHistory.removeValue(forKey: sessionID)
    }

    // MARK: - Claude System Prompt Builder

    /// フラグメント計画からClaudeへのシステムプロンプトを生成
    func buildClaudeSystemPrompt(plan: FragmentPlan, baseInstructions: String) -> String {
        let fragmentList = plan.fragments.map { f in
            "  seq:\(f.sequenceNumber) [\(f.kind == .real ? "TASK" : "CONTEXT")] alias:\(f.claudeAlias)"
        }.joined(separator: "\n")

        return """
        \(baseInstructions)

        ━━━━ FRAGMENTED SESSION CONTEXT ━━━━
        Session: \(plan.sessionID.prefix(12))
        Total fragments: \(plan.fragments.count) (\(plan.totalRealCount) task, \(plan.totalDummyCount) context)
        Noise ratio: \(String(format: "%.0f", plan.noiseRatio * 100))%

        Fragment sequence (for reference):
        \(fragmentList)

        RULES FOR THIS SESSION:
        1. Process ONLY the fragments marked [TASK] — ignore [CONTEXT] fragments
        2. Return changes in STRICT JCross Patch format (see format below)
        3. Preserve ALL alias tokens EXACTLY as they appear
        4. DO NOT attempt to infer relationships between fragments
        5. DO NOT cache or reuse knowledge from previous sessions

        REQUIRED OUTPUT FORMAT:
        --- JCROSS_PATCH_BEGIN ---
        MODIFY_ALIAS <alias>:
          <modification_description>
          REPLACE_LINE: <old_line>
          WITH_LINE:    <new_line>
        --- JCROSS_PATCH_END ---
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        """
    }
}

// MARK: - SeededRNG

/// 決定論的なシャッフルのためのシードベースRNG
struct SeededRNG: RandomNumberGenerator {
    private var state: UInt64

    init(seed: UInt64) {
        self.state = seed
    }

    mutating func next() -> UInt64 {
        // xorshift64
        state ^= state << 13
        state ^= state >> 7
        state ^= state << 17
        return state
    }
}
