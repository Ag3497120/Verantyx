import Foundation
import CryptoKit

// MARK: - RoutingSessionLogger
//
// Gatekeeper Mode のパイプライン全体を JCross 4層×4ゾーンで管理する
// 「唯一の真実ソース (Single Source of Truth)」。
//
// Claudeのコンテキストは信用しない。
// 送った順番・実/ダミーノードの区別・パッチ検証TODOは全てここに記録される。
//
// ゾーンライフサイクル:
//   front/ → セッション進行中 (draft → sending → awaiting_patch)
//   near/  → 完了済み直近 (applied → archived, 24h保持)
//   mid/   → プロジェクト統計 (ファイル単位の集計)
//   deep/  → 永続スキーマ・IDシャッフルマップ (外部送信禁止)

@MainActor
final class RoutingSessionLogger: ObservableObject {

    // MARK: - Types

    /// セッションの状態遷移
    enum SessionStatus: String, Codable {
        case draft           = "draft"
        case sending         = "sending"
        case awaitingPatch   = "awaiting_patch"
        case validating      = "validating"
        case applied         = "applied"
        case archived        = "archived"
        case failed          = "failed"
    }

    /// フラグメントの種別
    enum FragmentKind: String, Codable {
        case real  = "real"    // 実コードノード
        case dummy = "dummy"   // カモフラージュ用ダミー
    }

    /// カモフラージュドメイン
    enum CamouflageDomain: String, Codable, CaseIterable {
        case orbitalMechanics  = "orbital_mechanics"
        case signalProcessing  = "signal_processing"
        case fluidDynamics     = "fluid_dynamics"
        case computationalBio  = "computational_biology"
        case gamePhysics       = "game_physics"
        case none              = "none"

        /// ダミーノード生成に使うドメイン固有の定数・変数名プール
        var tokenPool: [String] {
            switch self {
            case .orbitalMechanics:
                return ["gravitationalConstant","orbitalPeriod","eccentricity",
                        "semiMajorAxis","keplerEquation","angularVelocity",
                        "perihelionDistance","apoapsis","trueAnomaly","meanMotion"]
            case .signalProcessing:
                return ["samplingFrequency","nyquistRate","filterCoefficient",
                        "fftBinSize","windowFunction","phaseShift",
                        "amplitudeSpectrum","convolutionKernel","signalToNoise","decimationFactor"]
            case .fluidDynamics:
                return ["reynoldsNumber","viscosityCoefficient","pressureGradient",
                        "vorticityTensor","bernoulliConstant","turbulenceIntensity",
                        "laminarFlowRate","naviersStokesCoeff","hydraulicDiameter","froudeNumber"]
            case .computationalBio:
                return ["sequenceAlignment","smithWatermanScore","nucleotideFrequency",
                        "aminoAcidMatrix","phylogeneticDistance","mutationRate",
                        "hiddenMarkovState","transcriptionFactor","codonTable","gapPenalty"]
            case .gamePhysics:
                return ["rigidBodyMoment","collisionImpulse","frictionCoefficient",
                        "restitutionFactor","broadPhaseAABB","constraintSolver",
                        "verletIntegration","separatingAxis","angularDamping","gravityVector"]
            case .none:
                return []
            }
        }
    }

    /// 送信フラグメントの記録
    struct FragmentRecord: Codable, Identifiable {
        let id: UUID
        let sequenceNumber: Int       // 送信順番 (1-indexed)
        let nodeID: String            // ローカルのノードID (N001等)
        let claudeAlias: String       // Claudeに送ったエイリアス (Z847等)
        let kind: FragmentKind
        let camouflageDomain: CamouflageDomain?  // kindが.dummyの場合のみ
        let role: String              // "func_entry", "helper_calc", "return_format" 等
        let sentAtEpoch: Double
    }

    /// ルーティングセッションの完全な状態
    struct RoutingSession: Codable, Identifiable {
        let id: UUID
        let sessionID: String         // SES_YYYYMMDD_NNN 形式
        let projectID: String
        let sourceRelativePath: String
        let schemaSessionID: String   // JCrossSchemaのsessionID
        var status: SessionStatus
        let createdAtEpoch: Double
        var updatedAtEpoch: Double

        // 断片化記録
        var fragmentOrder: [FragmentRecord]
        var realNodeCount: Int
        var dummyNodeCount: Int

        // カモフラージュ設定
        let camouflageDomain: CamouflageDomain
        var noiseRatio: Double {
            guard realNodeCount + dummyNodeCount > 0 else { return 0 }
            return Double(dummyNodeCount) / Double(realNodeCount + dummyNodeCount)
        }

        // トークン管理
        var claudeTokensSent: Int
        var claudeTokensReceived: Int
        var bonsaiBudgetUsed: Int
        var bonsaiBudgetCap: Int

        // TODOチェックリスト
        var todoReceivePatch: Bool
        var todoParsePatchFormat: Bool
        var todoFilterDummyPatches: Bool
        var todoValidateRealPatches: Bool
        var todoReverseTransform: Bool
        var todoApplyToSource: Bool
        var todoArchiveSession: Bool

        // パッチデータ
        var rawPatchReceived: String?
        var filteredPatchContent: String?

        /// 全TODOが完了しているか
        var isComplete: Bool {
            todoReceivePatch && todoParsePatchFormat && todoFilterDummyPatches &&
            todoValidateRealPatches && todoReverseTransform && todoApplyToSource && todoArchiveSession
        }

        /// 実ノードのエイリアスセット (パッチフィルタリングに使用)
        var realNodeAliases: Set<String> {
            Set(fragmentOrder.filter { $0.kind == .real }.map { $0.claudeAlias })
        }

        /// ダミーノードのエイリアスセット
        var dummyNodeAliases: Set<String> {
            Set(fragmentOrder.filter { $0.kind == .dummy }.map { $0.claudeAlias })
        }
    }

    // MARK: - Properties

    @Published var activeSessions: [RoutingSession] = []
    @Published var contextBudgetUsed: Int = 0

    static let bonsaiBudgetCap: Int = 32_000   // Bonsai-8B の実効コンテキスト上限

    private let vaultRootURL: URL
    private let frontDir: URL
    private let nearDir: URL
    private let midDir: URL
    private let deepDir: URL

    private var sessionCounter: Int = 0

    // MARK: - Init

    init(vaultRootURL: URL) {
        self.vaultRootURL = vaultRootURL
        self.frontDir = vaultRootURL.appendingPathComponent("routing/front")
        self.nearDir  = vaultRootURL.appendingPathComponent("routing/near")
        self.midDir   = vaultRootURL.appendingPathComponent("routing/mid")
        self.deepDir  = vaultRootURL.appendingPathComponent("routing/deep")

        Task { await self.setup() }
    }

    private func setup() async {
        let front = frontDir
        let near = nearDir
        let mid = midDir
        let deep = deepDir
        
        let loadedSessions = await Task.detached(priority: .utility) { () -> [RoutingSession] in
            let fm = FileManager.default
            for dir in [front, near, mid, deep] {
                try? fm.createDirectory(at: dir, withIntermediateDirectories: true)
            }
            guard let files = try? fm.contentsOfDirectory(at: front, includingPropertiesForKeys: nil) else { return [] }

            return files
                .filter { $0.pathExtension == "json" }
                .compactMap { try? JSONDecoder().decode(RoutingSession.self, from: Data(contentsOf: $0)) }
                .sorted { $0.createdAtEpoch < $1.createdAtEpoch }
        }.value

        self.activeSessions = loadedSessions
        self.sessionCounter = activeSessions.count
    }

    // MARK: - Session Creation

    /// 新しいルーティングセッションを作成して front/ に保存
    func createSession(
        projectID: String,
        sourceRelativePath: String,
        schemaSessionID: String,
        camouflageDomain: CamouflageDomain = .orbitalMechanics
    ) -> RoutingSession {
        sessionCounter += 1
        let dateStr = formatDateCompact(Date())
        let sessionID = "SES_\(dateStr)_\(String(format: "%03d", sessionCounter))"

        let session = RoutingSession(
            id: UUID(),
            sessionID: sessionID,
            projectID: projectID,
            sourceRelativePath: sourceRelativePath,
            schemaSessionID: schemaSessionID,
            status: .draft,
            createdAtEpoch: Date().timeIntervalSince1970,
            updatedAtEpoch: Date().timeIntervalSince1970,
            fragmentOrder: [],
            realNodeCount: 0,
            dummyNodeCount: 0,
            camouflageDomain: camouflageDomain,
            claudeTokensSent: 0,
            claudeTokensReceived: 0,
            bonsaiBudgetUsed: 0,
            bonsaiBudgetCap: Self.bonsaiBudgetCap,
            todoReceivePatch: false,
            todoParsePatchFormat: false,
            todoFilterDummyPatches: false,
            todoValidateRealPatches: false,
            todoReverseTransform: false,
            todoApplyToSource: false,
            todoArchiveSession: false
        )

        activeSessions.append(session)
        persistToFront(session)
        return session
    }

    // MARK: - Fragment Recording

    /// 実ノードを追加
    @discardableResult
    func addRealFragment(
        to sessionID: String,
        nodeID: String,
        claudeAlias: String,
        role: String = "unknown"
    ) -> FragmentRecord? {
        guard let idx = activeSessions.firstIndex(where: { $0.sessionID == sessionID }) else { return nil }

        var session = activeSessions[idx]
        let nextSeq = session.fragmentOrder.count + 1

        let fragment = FragmentRecord(
            id: UUID(),
            sequenceNumber: nextSeq,
            nodeID: nodeID,
            claudeAlias: claudeAlias,
            kind: .real,
            camouflageDomain: nil,
            role: role,
            sentAtEpoch: Date().timeIntervalSince1970
        )

        session.fragmentOrder.append(fragment)
        session.realNodeCount += 1
        session.updatedAtEpoch = Date().timeIntervalSince1970
        activeSessions[idx] = session
        persistToFront(session)
        return fragment
    }

    /// ダミーノードを追加
    @discardableResult
    func addDummyFragment(
        to sessionID: String,
        nodeID: String,
        claudeAlias: String,
        domain: CamouflageDomain
    ) -> FragmentRecord? {
        guard let idx = activeSessions.firstIndex(where: { $0.sessionID == sessionID }) else { return nil }

        var session = activeSessions[idx]
        let nextSeq = session.fragmentOrder.count + 1

        let fragment = FragmentRecord(
            id: UUID(),
            sequenceNumber: nextSeq,
            nodeID: nodeID,
            claudeAlias: claudeAlias,
            kind: .dummy,
            camouflageDomain: domain,
            role: "camouflage_decoy",
            sentAtEpoch: Date().timeIntervalSince1970
        )

        session.fragmentOrder.append(fragment)
        session.dummyNodeCount += 1
        session.updatedAtEpoch = Date().timeIntervalSince1970
        activeSessions[idx] = session
        persistToFront(session)
        return fragment
    }

    // MARK: - Status Transitions

    func transitionStatus(_ sessionID: String, to status: SessionStatus) {
        guard let idx = activeSessions.firstIndex(where: { $0.sessionID == sessionID }) else { return }
        activeSessions[idx].status = status
        activeSessions[idx].updatedAtEpoch = Date().timeIntervalSince1970
        persistToFront(activeSessions[idx])
    }

    func updateTokenCount(_ sessionID: String, sent: Int, received: Int) {
        guard let idx = activeSessions.firstIndex(where: { $0.sessionID == sessionID }) else { return }
        activeSessions[idx].claudeTokensSent = sent
        activeSessions[idx].claudeTokensReceived = received
        activeSessions[idx].updatedAtEpoch = Date().timeIntervalSince1970
        recalcBudget()
        persistToFront(activeSessions[idx])
    }

    func updateBonsaiBudget(_ sessionID: String, used: Int) {
        guard let idx = activeSessions.firstIndex(where: { $0.sessionID == sessionID }) else { return }
        activeSessions[idx].bonsaiBudgetUsed = used
        recalcBudget()
        persistToFront(activeSessions[idx])
    }

    // MARK: - TODO Management

    func completeTodo(_ sessionID: String, todo: TODOStep) {
        guard let idx = activeSessions.firstIndex(where: { $0.sessionID == sessionID }) else { return }
        var session = activeSessions[idx]

        switch todo {
        case .receivePatch:         session.todoReceivePatch = true
        case .parsePatchFormat:     session.todoParsePatchFormat = true
        case .filterDummyPatches:   session.todoFilterDummyPatches = true
        case .validateRealPatches:  session.todoValidateRealPatches = true
        case .reverseTransform:     session.todoReverseTransform = true
        case .applyToSource:        session.todoApplyToSource = true
        case .archiveSession:
            session.todoArchiveSession = true
            session.status = .applied
        }

        session.updatedAtEpoch = Date().timeIntervalSince1970
        activeSessions[idx] = session
        persistToFront(session)

        // 全TODO完了でnear/に移動
        if session.isComplete {
            archiveToNear(session)
        }
    }

    enum TODOStep: CaseIterable {
        case receivePatch
        case parsePatchFormat
        case filterDummyPatches
        case validateRealPatches
        case reverseTransform
        case applyToSource
        case archiveSession
    }

    func recordReceivedPatch(_ sessionID: String, raw: String) {
        guard let idx = activeSessions.firstIndex(where: { $0.sessionID == sessionID }) else { return }
        activeSessions[idx].rawPatchReceived = raw
        activeSessions[idx].updatedAtEpoch = Date().timeIntervalSince1970
        persistToFront(activeSessions[idx])
    }

    func recordFilteredPatch(_ sessionID: String, filtered: String) {
        guard let idx = activeSessions.firstIndex(where: { $0.sessionID == sessionID }) else { return }
        activeSessions[idx].filteredPatchContent = filtered
        activeSessions[idx].updatedAtEpoch = Date().timeIntervalSince1970
        persistToFront(activeSessions[idx])
    }

    // MARK: - Session Lookup

    func session(id: String) -> RoutingSession? {
        activeSessions.first { $0.sessionID == id }
    }

    func pendingSessions() -> [RoutingSession] {
        activeSessions.filter { $0.status == .awaitingPatch || $0.status == .validating }
    }

    func incompleteSessions() -> [RoutingSession] {
        activeSessions.filter { !$0.isComplete && $0.status != .archived }
    }

    // MARK: - Bonsai-8B Context Budget

    var remainingBonsaiBudget: Int {
        max(0, Self.bonsaiBudgetCap - contextBudgetUsed)
    }

    var isBudgetCritical: Bool {
        remainingBonsaiBudget < 4_000
    }

    private func recalcBudget() {
        // front/の全セッションのbonsaiBudgetUsed合計
        contextBudgetUsed = activeSessions
            .filter { $0.status != .archived }
            .reduce(0) { $0 + $1.bonsaiBudgetUsed }
    }

    // MARK: - Zone Archiving

    /// front/ → near/ へ移動
    private func archiveToNear(_ session: RoutingSession) {
        let fm = FileManager.default
        let frontURL = frontDir.appendingPathComponent("\(session.sessionID).json")
        let nearURL  = nearDir.appendingPathComponent("\(session.sessionID).json")

        // JCrossノードもnear/に移動
        let jcrossFront = frontDir.appendingPathComponent("\(session.sessionID).jcross")
        let jcrossNear  = nearDir.appendingPathComponent("\(session.sessionID).jcross")

        try? fm.moveItem(at: frontURL,  to: nearURL)
        try? fm.moveItem(at: jcrossFront, to: jcrossNear)

        activeSessions.removeAll { $0.sessionID == session.sessionID }

        // mid/ に統計を集計
        aggregateToMid(session)

        // 古いnear/ファイルを自動削除 (24h超)
        pruneNearZone()
    }

    /// mid/ にプロジェクト統計を追記
    private func aggregateToMid(_ session: RoutingSession) {
        let statsURL = midDir.appendingPathComponent("PROJECT_STATS.json")
        var stats: ProjectStats = (try? JSONDecoder().decode(
            ProjectStats.self,
            from: Data(contentsOf: statsURL)
        )) ?? ProjectStats()

        stats.totalSessions += 1
        stats.totalRealFragments += session.realNodeCount
        stats.totalDummyFragments += session.dummyNodeCount
        stats.totalClaudeTokens += session.claudeTokensSent + session.claudeTokensReceived
        stats.filesProcessed.insert(session.sourceRelativePath)
        stats.lastUpdated = Date().timeIntervalSince1970

        if let data = try? JSONEncoder().encode(stats) {
            try? data.write(to: statsURL)
        }
    }

    private struct ProjectStats: Codable {
        var totalSessions: Int = 0
        var totalRealFragments: Int = 0
        var totalDummyFragments: Int = 0
        var totalClaudeTokens: Int = 0
        var filesProcessed: Set<String> = []
        var lastUpdated: Double = 0
    }

    private func pruneNearZone() {
        let fm = FileManager.default
        let cutoff = Date().timeIntervalSince1970 - (24 * 3600) // 24h
        guard let files = try? fm.contentsOfDirectory(at: nearDir, includingPropertiesForKeys: nil) else { return }

        for file in files where file.pathExtension == "json" {
            let attrs = try? fm.attributesOfItem(atPath: file.path)
            if let created = (attrs?[.creationDate] as? Date)?.timeIntervalSince1970,
               created < cutoff {
                try? fm.removeItem(at: file)
                // 対応する.jcrossもdeep/に移動
                let jcrossNear = nearDir.appendingPathComponent(file.deletingPathExtension().lastPathComponent + ".jcross")
                let jcrossDeep = deepDir.appendingPathComponent(file.deletingPathExtension().lastPathComponent + ".jcross")
                try? fm.moveItem(at: jcrossNear, to: jcrossDeep)
            }
        }
    }

    // MARK: - JCross Node Generation (L1-L3)

    /// セッションをJCross L1-L3形式で保存
    func persistAsJCrossNode(_ session: RoutingSession) {
        let l1Tags = generateL1Tags(for: session)
        let l1Summary = generateL1Summary(for: session)
        let l2Content = generateL2Content(for: session)
        let l3Raw = generateL3Raw(for: session)

        let jcrossContent = """
        // ROUTING_SESSION_NODE
        // SessionID: \(session.sessionID)
        // Status: \(session.status.rawValue)
        // Generated: \(ISO8601DateFormatter().string(from: Date()))

        ─── L1 (高速タグ) ────────────────────────────────────────────
        \(l1Tags)
        \(l1Summary)

        ─── L2 (構造化TODO + 記録) ──────────────────────────────────
        \(l2Content)

        ─── L3 (生データ) ────────────────────────────────────────────
        \(l3Raw)
        """

        let url = frontDir.appendingPathComponent("\(session.sessionID).jcross")
        try? jcrossContent.data(using: .utf8)?.write(to: url)
    }

    // MARK: - L1 Generation

    private func generateL1Tags(for session: RoutingSession) -> String {
        var tags: [String] = []

        // ステータスタグ
        switch session.status {
        case .awaitingPatch: tags.append("[待:1.0]")
        case .validating:    tags.append("[検:1.0]")
        case .applied:       tags.append("[済:1.0]")
        case .failed:        tags.append("[失:1.0]")
        default:             tags.append("[進:1.0]")
        }

        tags.append("[散:0.9]")  // フラグメント化
        tags.append("[偽:0.9]")  // ノイズ注入

        // TODO残存数
        let remaining = pendingTODOCount(session)
        if remaining > 0 { tags.append("[TODO:\(remaining)]") }

        return tags.joined(separator: " ")
    }

    private func generateL1Summary(for session: RoutingSession) -> String {
        "\(session.sessionID): 実\(session.realNodeCount)ノード/ダミー\(session.dummyNodeCount)ノード送信。" +
        "\(session.camouflageDomain.rawValue)でカモフラージュ。" +
        "TODO残\(pendingTODOCount(session))件。"
    }

    private func pendingTODOCount(_ session: RoutingSession) -> Int {
        [session.todoReceivePatch, session.todoParsePatchFormat,
         session.todoFilterDummyPatches, session.todoValidateRealPatches,
         session.todoReverseTransform, session.todoApplyToSource,
         session.todoArchiveSession].filter { !$0 }.count
    }

    // MARK: - L2 Generation

    private func generateL2Content(for session: RoutingSession) -> String {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]

        let fragmentJSON = (try? encoder.encode(session.fragmentOrder))
            .flatMap { String(data: $0, encoding: .utf8) } ?? "[]"

        let todoStatus: (Bool) -> String = { $0 ? "done" : "pending" }

        return """
        OP.FACT("session_id",         "\(session.sessionID)")
        OP.FACT("project_id",         "\(session.projectID)")
        OP.FACT("source_file",        "\(session.sourceRelativePath)")
        OP.FACT("schema_session_id",  "\(session.schemaSessionID)")
        OP.STATE("status",            "\(session.status.rawValue)")
        OP.FACT("noise_domain",       "\(session.camouflageDomain.rawValue)")
        OP.FACT("noise_ratio",        "\(String(format: "%.2f", session.noiseRatio))")
        OP.FACT("claude_tokens_sent", \(session.claudeTokensSent))
        OP.STATE("claude_tokens_returned", \(session.claudeTokensReceived))
        OP.STATE("bonsai_budget_used", \(session.bonsaiBudgetUsed))
        OP.STATE("bonsai_budget_cap",  \(session.bonsaiBudgetCap))

        // 送信順番の完全記録 (唯一の正解)
        OP.ENTITY("fragment_order", \(fragmentJSON))

        // TODOチェックリスト
        OP.TODO("receive_patch",         "\(todoStatus(session.todoReceivePatch))")
        OP.TODO("parse_patch_format",    "\(todoStatus(session.todoParsePatchFormat))")
        OP.TODO("filter_dummy_patches",  "\(todoStatus(session.todoFilterDummyPatches))")
        OP.TODO("validate_real_patches", "\(todoStatus(session.todoValidateRealPatches))")
        OP.TODO("reverse_transform",     "\(todoStatus(session.todoReverseTransform))")
        OP.TODO("apply_to_source",       "\(todoStatus(session.todoApplyToSource))")
        OP.TODO("archive_session",       "\(todoStatus(session.todoArchiveSession))")
        """
    }

    // MARK: - L3 Generation

    private func generateL3Raw(for session: RoutingSession) -> String {
        var parts: [String] = []
        parts.append("<SESSION_METADATA>")
        parts.append("created_at: \(session.createdAtEpoch)")
        parts.append("updated_at: \(session.updatedAtEpoch)")
        parts.append("real_nodes: \(session.realNodeCount)")
        parts.append("dummy_nodes: \(session.dummyNodeCount)")
        parts.append("</SESSION_METADATA>")

        if let patch = session.rawPatchReceived {
            parts.append("<RECEIVED_PATCH_RAW>")
            parts.append(patch)
            parts.append("</RECEIVED_PATCH_RAW>")
        } else {
            parts.append("<RECEIVED_PATCH_RAW>")
            parts.append("(pending)")
            parts.append("</RECEIVED_PATCH_RAW>")
        }

        if let filtered = session.filteredPatchContent {
            parts.append("<FILTERED_PATCH>")
            parts.append(filtered)
            parts.append("</FILTERED_PATCH>")
        }

        return parts.joined(separator: "\n")
    }

    // MARK: - Persistence (JSON)

    private func persistToFront(_ session: RoutingSession) {
        let url = frontDir.appendingPathComponent("\(session.sessionID).json")
        if let data = try? JSONEncoder().encode(session) {
            try? data.write(to: url)
        }
        // JCrossノードも同時更新
        persistAsJCrossNode(session)
    }

    private func loadActiveSessions() {
        // Replaced by inline async loading in setup()
    }

    // MARK: - Utility

    private func formatDateCompact(_ date: Date) -> String {
        let fmt = DateFormatter()
        fmt.dateFormat = "yyyyMMdd"
        return fmt.string(from: date)
    }
}
