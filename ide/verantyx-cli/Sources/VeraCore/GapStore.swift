import Foundation

/// Persistent record of what is *not yet settled*.
///
/// This is the component that makes long-horizon work possible without a
/// growing context window: the model is reset before every forward and keeps
/// nothing, while purpose, failed approaches and open questions live here on
/// disk. A resumed run reconstructs its intent from this store alone.
///
/// Mirrors the contract of Vera-alpha's `gap_graph.py` closely enough that the
/// two describe the same world:
///   - identity is `(scope, subject)`; creating a duplicate returns the
///     existing node instead of a second one
///   - RESOLVED nodes are **kept**, never deleted, so a later run recognises
///     "this was already settled" and does not redo it
///
/// It is deliberately a separate Swift implementation rather than an MCP call
/// into the Python store: the CLI must be able to run with nothing else
/// installed, and a research trace should not depend on a live subprocess.
public struct GapNode: Codable, Sendable, Equatable {

    public enum Status: String, Codable, Sendable {
        case detected = "DETECTED"
        case acquiring = "ACQUIRING"
        case evidenceCollected = "EVIDENCE_COLLECTED"
        case resolved = "RESOLVED"
        case blockedNoSource = "BLOCKED_NO_SOURCE"
        case blockedBudget = "BLOCKED_BUDGET"
        case stale = "STALE"

        /// Open means "still worth spending turns on".
        public var isOpen: Bool {
            switch self {
            case .detected, .acquiring, .evidenceCollected: return true
            case .resolved, .blockedNoSource, .blockedBudget, .stale: return false
            }
        }
    }

    public enum Severity: String, Codable, Sendable {
        case critical = "CRITICAL"
        case quality = "QUALITY"
        case optional = "OPTIONAL"
    }

    public var gapId: String
    public var gapType: String
    public var subject: String
    public var scope: String
    public var severity: Severity
    public var status: Status
    public var causedBy: [String]
    public var blocks: [String]
    /// Distinct approaches already tried. The point of recording these is to
    /// stop a resumed run from repeating a move that already failed.
    public var attemptedStrategies: [String]
    public var observedTransition: String?
    public var failureType: String?
    public var note: String?
    public var createdAt: Double
    public var updatedAt: Double

    public init(
        gapId: String, gapType: String, subject: String, scope: String,
        severity: Severity, status: Status = .detected,
        causedBy: [String] = [], blocks: [String] = [],
        attemptedStrategies: [String] = [],
        observedTransition: String? = nil, failureType: String? = nil,
        note: String? = nil,
        createdAt: Double = Date().timeIntervalSince1970,
        updatedAt: Double = Date().timeIntervalSince1970
    ) {
        self.gapId = gapId
        self.gapType = gapType
        self.subject = subject
        self.scope = scope
        self.severity = severity
        self.status = status
        self.causedBy = causedBy
        self.blocks = blocks
        self.attemptedStrategies = attemptedStrategies
        self.observedTransition = observedTransition
        self.failureType = failureType
        self.note = note
        self.createdAt = createdAt
        self.updatedAt = updatedAt
    }

    /// One-line form injected back into the next turn's prompt.
    ///
    /// Bounded on purpose. The store keeps every attempt, but the *prompt* only
    /// ever shows the most recent few: the whole point of this runtime is that
    /// per-turn cost does not grow with mission length, and replaying an
    /// unbounded attempt list would reintroduce exactly the growth that a
    /// conversation history causes.
    public func briefLine(maxStrategies: Int = 3, maxSubject: Int = 90) -> String {
        var parts = ["GAP \(status.rawValue) [\(severity.rawValue)] \(subject.prefix(maxSubject))"]
        if !attemptedStrategies.isEmpty {
            let recent = attemptedStrategies.suffix(maxStrategies)
            let elided = attemptedStrategies.count - recent.count
            var line = "already tried: " + recent.map { String($0.prefix(48)) }.joined(separator: " | ")
            if elided > 0 { line += " (+\(elided) earlier)" }
            parts.append(line)
        }
        if let failureType { parts.append("last failure: \(failureType)") }
        return parts.joined(separator: " — ")
    }
}

/// File-backed collection of `GapNode`s. Single-writer; the CLI runs one
/// mission per process.
public final class GapStore {

    private(set) public var nodes: [String: GapNode] = [:]
    private let url: URL

    /// - Parameter directory: the `--memory` directory shared with `VectorMemory`.
    public init(directory: URL) throws {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        self.url = directory.appendingPathComponent("gaps.json")
        try load()
    }

    public var path: String { url.path }

    // MARK: - Persistence

    private func load() throws {
        guard let data = FileManager.default.contents(atPath: url.path), !data.isEmpty else {
            nodes = [:]
            return
        }
        nodes = try JSONDecoder().decode([String: GapNode].self, from: data)
    }

    /// Written after every mutation: a run that is killed mid-mission must
    /// still leave a resumable store behind, so batching writes to the end
    /// would defeat the purpose.
    public func save() throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        try encoder.encode(nodes).write(to: url, options: .atomic)
    }

    // MARK: - Queries

    public func find(scope: String, subject: String) -> GapNode? {
        nodes.values.first { $0.scope == scope && $0.subject == subject }
    }

    public var openGaps: [GapNode] {
        nodes.values.filter { $0.status.isOpen }
            .sorted { $0.createdAt < $1.createdAt }
    }

    public var resolvedGaps: [GapNode] {
        nodes.values.filter { $0.status == .resolved }
            .sorted { $0.updatedAt < $1.updatedAt }
    }

    public func get(_ gapId: String) -> GapNode? { nodes[gapId] }

    // MARK: - Mutation

    /// Creates a gap, or returns the existing one for the same
    /// `(scope, subject)`. Returning the existing node — including a RESOLVED
    /// one — is what lets a later session recognise settled ground.
    @discardableResult
    public func open(
        gapType: String, subject: String, scope: String,
        severity: GapNode.Severity = .quality,
        note: String? = nil
    ) throws -> GapNode {
        if let existing = find(scope: scope, subject: subject) { return existing }
        let node = GapNode(
            gapId: "gap_" + UUID().uuidString.prefix(8).lowercased(),
            gapType: gapType, subject: subject, scope: scope,
            severity: severity, note: note
        )
        nodes[node.gapId] = node
        try save()
        return node
    }

    /// Records an attempt that did not settle the gap.
    @discardableResult
    public func recordAttempt(
        _ gapId: String, strategy: String, failureType: String?
    ) throws -> GapNode? {
        guard var node = nodes[gapId] else { return nil }
        let trimmed = strategy.trimmingCharacters(in: .whitespacesAndNewlines)
        if !trimmed.isEmpty, !node.attemptedStrategies.contains(trimmed) {
            node.attemptedStrategies.append(trimmed)
        }
        node.failureType = failureType
        node.status = .acquiring
        node.updatedAt = Date().timeIntervalSince1970
        nodes[gapId] = node
        try save()
        return node
    }

    @discardableResult
    public func resolve(_ gapId: String, note: String? = nil) throws -> GapNode? {
        guard var node = nodes[gapId] else { return nil }
        node.status = .resolved
        node.failureType = nil
        if let note { node.note = note }
        node.updatedAt = Date().timeIntervalSince1970
        nodes[gapId] = node
        try save()
        return node
    }

    @discardableResult
    public func block(_ gapId: String, status: GapNode.Status, reason: String) throws -> GapNode? {
        guard var node = nodes[gapId], !status.isOpen else { return nil }
        node.status = status
        node.failureType = reason
        node.updatedAt = Date().timeIntervalSince1970
        nodes[gapId] = node
        try save()
        return node
    }

    // MARK: - Prompt surface

    /// The block re-injected at the top of each turn. This is the entire
    /// mechanism by which a turn "remembers" what it is doing — there is no
    /// conversation history behind it.
    public func purposeBlock(limit: Int = 6) -> String {
        let open = openGaps.prefix(limit)
        guard !open.isEmpty else { return "" }
        var lines = ["[OPEN GAPS] keep working until these are RESOLVED"]
        for gap in open { lines.append("- " + gap.briefLine()) }
        let settled = resolvedGaps.suffix(3)
        if !settled.isEmpty {
            lines.append("[ALREADY SETTLED] do not redo")
            for gap in settled { lines.append("- \(gap.subject)") }
        }
        return lines.joined(separator: "\n")
    }
}
