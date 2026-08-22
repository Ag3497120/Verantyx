import SwiftUI
import Combine

// MARK: - GatekeeperDashboardViewModel

@MainActor
final class GatekeeperDashboardViewModel: ObservableObject {

    // MARK: - Published State

    @Published var pipelineState: PipelineState = .idle
    @Published var currentSessionID: String?
    @Published var totalFragmentsSent: Int = 0
    @Published var realFragmentCount: Int = 0
    @Published var dummyFragmentCount: Int = 0
    @Published var noiseRatio: Double = 0.0
    @Published var acceptedPatchCount: Int = 0
    @Published var dummyPatchBlocked: Int = 0
    @Published var hallucinatedPatchCount: Int = 0
    @Published var malformedPatchCount: Int = 0
    @Published var acceptanceRate: Double = 0.0
    @Published var currentDomain: String?
    @Published var securityInsights: [String] = []
    @Published var sessionHistory: [SessionHistoryEntry] = []

    // MARK: - Internals

    private var cancellables = Set<AnyCancellable>()
    private let logger: RoutingSessionLogger
    private let vaultRootURL: URL

    // MARK: - Init

    init() {
        let base = FileManager.default
            .urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        vaultRootURL = base.appendingPathComponent("Verantyx/jcross_vault")
        logger = RoutingSessionLogger(vaultRootURL: vaultRootURL)

        // Observe GatekeeperPipelineOrchestrator notifications
        NotificationCenter.default.publisher(for: .gatekeeperSessionDidUpdate)
            .receive(on: DispatchQueue.main)
            .sink { [weak self] note in
                guard let id = note.userInfo?["sessionID"] as? String else { return }
                Task { await self?.reload(sessionID: id) }
            }
            .store(in: &cancellables)

        NotificationCenter.default.publisher(for: .gatekeeperPipelineStateChanged)
            .receive(on: DispatchQueue.main)
            .sink { [weak self] note in
                if let raw = note.userInfo?["state"] as? String {
                    self?.pipelineState = PipelineState(rawValue: raw) ?? .idle
                }
            }
            .store(in: &cancellables)

        // Mirror logger.activeSessions changes
        logger.$activeSessions
            .receive(on: DispatchQueue.main)
            .sink { [weak self] _ in
                Task { await self?.loadCurrentSession() }
            }
            .store(in: &cancellables)
    }

    // MARK: - Public API

    func loadCurrentSession() async {
        if let last = logger.activeSessions.last {
            await reload(sessionID: last.sessionID)
        } else {
            // Try near/ zone for completed sessions
            await loadMostRecentCompletedSession()
        }
        await loadSessionHistory()
    }

    func refresh() async {
        if let id = currentSessionID {
            await reload(sessionID: id)
        } else {
            await loadCurrentSession()
        }
    }

    func requestAbort() {
        NotificationCenter.default.post(
            name: .gatekeeperAbortRequested,
            object: nil,
            userInfo: currentSessionID.map { ["sessionID": $0] }
        )
        pipelineState = .aborting
    }

    // MARK: - Private

    private func reload(sessionID: String) async {
        currentSessionID = sessionID

        // Look up in active sessions first, then near zone
        if let session = logger.session(id: sessionID) {
            applySession(session)
        } else if let session = loadSessionFromNear(sessionID: sessionID) {
            applySession(session)
        }
    }

    private func applySession(_ session: RoutingSessionLogger.RoutingSession) {
        realFragmentCount  = session.realNodeCount
        dummyFragmentCount = session.dummyNodeCount
        totalFragmentsSent = session.realNodeCount + session.dummyNodeCount
        noiseRatio         = session.noiseRatio
        currentDomain      = session.camouflageDomain == .none ? nil : session.camouflageDomain.rawValue

        // Derive patch metrics from fragment records
        // The validator stores results in GatekeeperPipelineOrchestrator side;
        // here we read them from the filteredPatchContent prefix tag if present.
        decodePatchMetrics(from: session)
        buildSecurityInsights(session: session)

        // Update pipeline state from session status
        pipelineState = PipelineState.fromSessionStatus(session.status)
    }

    /// Decode lightweight patch counters embedded by the orchestrator.
    /// Format: "METRICS:accepted=N,dummy=N,hallucinated=N,malformed=N\n..."
    private func decodePatchMetrics(from session: RoutingSessionLogger.RoutingSession) {
        guard let raw = session.filteredPatchContent,
              raw.hasPrefix("METRICS:") else {
            // Default from TODO state
            acceptedPatchCount     = session.todoApplyToSource ? 1 : 0
            dummyPatchBlocked      = 0
            hallucinatedPatchCount = 0
            malformedPatchCount    = 0
            recomputeAcceptance()
            return
        }
        let firstLine = raw.components(separatedBy: "\n").first ?? ""
        let kvPart    = firstLine.dropFirst("METRICS:".count)
        var kvMap: [String: Int] = [:]
        for part in kvPart.components(separatedBy: ",") {
            let kv = part.components(separatedBy: "=")
            if kv.count == 2, let v = Int(kv[1]) {
                kvMap[kv[0]] = v
            }
        }
        acceptedPatchCount     = kvMap["accepted"]    ?? 0
        dummyPatchBlocked      = kvMap["dummy"]       ?? 0
        hallucinatedPatchCount = kvMap["hallucinated"] ?? 0
        malformedPatchCount    = kvMap["malformed"]   ?? 0
        recomputeAcceptance()
    }

    private func recomputeAcceptance() {
        let total = acceptedPatchCount + dummyPatchBlocked + hallucinatedPatchCount + malformedPatchCount
        acceptanceRate = total > 0 ? Double(acceptedPatchCount) / Double(total) : 0.0
    }

    private func buildSecurityInsights(session: RoutingSessionLogger.RoutingSession) {
        var insights: [String] = []

        if session.noiseRatio > 0.5 {
            insights.append("高ノイズ比 (\(String(format: "%.0f%%", session.noiseRatio * 100))): 外部LLMによるドメイン推測を効果的に阻害しています。")
        }

        if session.camouflageDomain != .none {
            insights.append("カモフラージュドメイン「\(session.camouflageDomain.rawValue)」により、実際のビジネスロジックが隠蔽されています。")
        }

        if dummyPatchBlocked > 0 {
            insights.append("⚠ \(dummyPatchBlocked)件のダミーノードへのパッチを検出・廃棄しました（意味的リーク試行の可能性）。")
        }

        if hallucinatedPatchCount > 0 {
            insights.append("⚠ \(hallucinatedPatchCount)件のhallucinated aliasを検出しました。プロンプトの明確化を検討してください。")
        }

        if acceptedPatchCount > 0 && dummyPatchBlocked == 0 {
            insights.append("✓ セッション中にダミーへのパッチ試行はありませんでした。LLMへの情報遮断は良好です。")
        }

        let realAliases = session.realNodeAliases
        let uniqueCount = Set(realAliases).count
        if uniqueCount == realAliases.count && uniqueCount > 0 {
            insights.append("✓ IDシャッフルマップは一意性を保持しています（衝突なし）。")
        }

        if logger.isBudgetCritical {
            insights.append("⚠ Bonsai-8Bコンテキストバジェットが残り4,000トークン未満です。")
        }

        self.securityInsights = insights
    }

    // MARK: - Near Zone Loading

    private func loadSessionFromNear(sessionID: String) -> RoutingSessionLogger.RoutingSession? {
        let nearURL = vaultRootURL
            .appendingPathComponent("routing/near")
            .appendingPathComponent("\(sessionID).json")
        guard let data = try? Data(contentsOf: nearURL) else { return nil }
        return try? JSONDecoder().decode(RoutingSessionLogger.RoutingSession.self, from: data)
    }

    private func loadMostRecentCompletedSession() async {
        let nearDir = vaultRootURL.appendingPathComponent("routing/near")
        let session = await Task.detached(priority: .utility) { () -> RoutingSessionLogger.RoutingSession? in
            let fm = FileManager.default
            guard let files = try? fm.contentsOfDirectory(
                at: nearDir,
                includingPropertiesForKeys: [.creationDateKey],
                options: .skipsHiddenFiles
            ) else { return nil }

            let jsonFiles = files.filter { $0.pathExtension == "json" }
            let sorted = jsonFiles.compactMap { url -> (URL, Date)? in
                let attrs = try? fm.attributesOfItem(atPath: url.path)
                let date  = attrs?[.creationDate] as? Date ?? .distantPast
                return (url, date)
            }
            .sorted { $0.1 > $1.1 }

            guard let (latestURL, _) = sorted.first,
                  let data = try? Data(contentsOf: latestURL),
                  let session = try? JSONDecoder().decode(RoutingSessionLogger.RoutingSession.self, from: data)
            else { return nil }

            return session
        }.value

        guard let session = session else { return }
        applySession(session)
        currentSessionID = session.sessionID
    }

    private func loadSessionHistory() async {
        // Gather completed sessions from near/ zone
        let nearDir = vaultRootURL.appendingPathComponent("routing/near")
        
        let newHistory = await Task.detached(priority: .utility) { () -> [SessionHistoryEntry] in
            let fm = FileManager.default
            guard let files = try? fm.contentsOfDirectory(
                at: nearDir,
                includingPropertiesForKeys: [.creationDateKey],
                options: .skipsHiddenFiles
            ) else { return [] }

            let decoded = files
                .filter { $0.pathExtension == "json" }
                .compactMap { url -> RoutingSessionLogger.RoutingSession? in
                    guard let data = try? Data(contentsOf: url) else { return nil }
                    return try? JSONDecoder().decode(RoutingSessionLogger.RoutingSession.self, from: data)
                }
                .sorted { $0.updatedAtEpoch > $1.updatedAtEpoch }

            return decoded.prefix(10).map { s in
                return SessionHistoryEntry(
                    id: s.sessionID,
                    sourcePath: s.sourceRelativePath,
                    fragmentCount: s.realNodeCount + s.dummyNodeCount,
                    acceptanceRate: 1.0,  // accurate value comes from filteredPatchContent metrics
                    domain: s.camouflageDomain.rawValue,
                    completedAt: Date(timeIntervalSince1970: s.updatedAtEpoch),
                    wasSuccessful: s.status == .applied
                )
            }
        }.value
        
        self.sessionHistory = newHistory
    }

    // MARK: - Types

    enum PipelineState: String, CaseIterable {
        case idle        = "idle"
        case planning    = "planning"
        case fragmenting = "fragmenting"
        case sending     = "sending"
        case validating  = "validating"
        case applying    = "applying"
        case completed   = "completed"
        case aborting    = "aborting"
        case failed      = "failed"

        static func fromSessionStatus(_ s: RoutingSessionLogger.SessionStatus) -> PipelineState {
            switch s {
            case .draft:         return .planning
            case .sending:       return .sending
            case .awaitingPatch: return .sending
            case .validating:    return .validating
            case .applied:       return .completed
            case .archived:      return .completed
            case .failed:        return .failed
            }
        }

        var label: String {
            switch self {
            case .idle:        return "Idle — Waiting for pipeline task"
            case .planning:    return "Planning fragmentation strategy…"
            case .fragmenting: return "Fragmenting & injecting noise…"
            case .sending:     return "Sending to external LLM…"
            case .validating:  return "Validating patches (Bonsai-8B)…"
            case .applying:    return "Applying accepted patches…"
            case .completed:   return "Pipeline completed successfully"
            case .aborting:    return "Aborting pipeline…"
            case .failed:      return "Pipeline failed — check logs"
            }
        }

        var icon: String {
            switch self {
            case .idle:        return "pause.circle"
            case .planning:    return "lightbulb"
            case .fragmenting: return "scissors"
            case .sending:     return "paperplane"
            case .validating:  return "checkmark.shield"
            case .applying:    return "wrench.and.screwdriver"
            case .completed:   return "checkmark.circle.fill"
            case .aborting:    return "stop.fill"
            case .failed:      return "exclamationmark.octagon.fill"
            }
        }

        var color: Color {
            switch self {
            case .idle:        return .gray
            case .planning:    return .yellow
            case .fragmenting: return .orange
            case .sending:     return .cyan
            case .validating:  return .blue
            case .applying:    return .purple
            case .completed:   return .green
            case .aborting:    return .red
            case .failed:      return .red
            }
        }
    }

    struct SessionHistoryEntry: Identifiable {
        let id: String
        let sourcePath: String
        let fragmentCount: Int
        let acceptanceRate: Double
        let domain: String
        let completedAt: Date
        let wasSuccessful: Bool

        var relativeDate: String {
            let formatter = RelativeDateTimeFormatter()
            formatter.unitsStyle = .short
            return formatter.localizedString(for: completedAt, relativeTo: Date())
        }
    }
}

// MARK: - Notification Names

extension Notification.Name {
    static let gatekeeperSessionDidUpdate     = Notification.Name("verantyx.gatekeeper.sessionUpdate")
    static let gatekeeperPipelineStateChanged = Notification.Name("verantyx.gatekeeper.stateChange")
    static let gatekeeperAbortRequested       = Notification.Name("verantyx.gatekeeper.abortRequest")
}
