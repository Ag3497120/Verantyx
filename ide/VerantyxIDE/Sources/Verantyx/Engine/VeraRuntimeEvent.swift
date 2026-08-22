import Foundation

// MARK: - Shared runtime event schema (CLI + GUI)
//
// Dual-track posture (do not gut the IDE):
//   • CLI (`cli/verantyx-cli`, product `vera`) is the research / repro interface
//     and JSONL source of truth for missions.
//   • GUI (this app) stays fully intact — chat, mirror, Act, MCP, settings.
//   • TODO(gui): thin-visualize these events (replay JSONL / SSE). Do NOT
//     rebuild the GUI as a second inference brain.
//
// Canonical package types: `cli/verantyx-cli/Sources/VeraCore/VeraRuntimeEvent.swift`
// Keep field names / kinds in sync until the app target links VeraCore.

/// Event kinds aligned with the research CLI surface:
/// `MISSION / OBSERVATION / PROPOSED_ACTION / POLICY / RESULT` (+ gap, skill_recall).
enum VeraEventKind: String, Codable, Sendable, CaseIterable {
    case mission
    case observation
    case proposed_action
    case policy
    case result
    case gap
    case skill_recall
}

/// One structured runtime event. Encoded as a single JSONL line by `vera run --trace`.
struct VeraRuntimeEvent: Codable, Sendable, Equatable {
    var schemaVersion: Int
    var ts: String
    var kind: VeraEventKind
    var missionId: String
    var turn: Int?
    var summary: String
    var detail: [String: String]
    var tags: [String]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case ts
        case kind
        case missionId = "mission_id"
        case turn
        case summary
        case detail
        case tags
    }

    static let currentSchemaVersion = 1

    /// Optional `detail["mission_kind"]` = `act`|`speak` (IDE MissionKindClassifier).
    init(
        kind: VeraEventKind,
        missionId: String,
        summary: String,
        turn: Int? = nil,
        detail: [String: String] = [:],
        tags: [String] = [],
        ts: Date = Date(),
        schemaVersion: Int = VeraRuntimeEvent.currentSchemaVersion
    ) {
        self.schemaVersion = schemaVersion
        self.ts = ISO8601DateFormatter().string(from: ts)
        self.kind = kind
        self.missionId = missionId
        self.turn = turn
        self.summary = summary
        self.detail = detail
        self.tags = tags
    }

    /// Human-readable one-liner matching CLI stdout formatting.
    var cliLine: String {
        let kindLabel = kind.rawValue.uppercased().padding(toLength: 16, withPad: " ", startingAt: 0)
        var parts: [String] = [kindLabel, summary]
        if let turn {
            parts.insert("t=\(turn)", at: 1)
        }
        if !detail.isEmpty {
            let extras = detail
                .sorted { $0.key < $1.key }
                .prefix(6)
                .map { "\($0.key)=\($0.value)" }
                .joined(separator: " ")
            if !extras.isEmpty {
                parts.append(extras)
            }
        }
        return parts.joined(separator: "  ")
    }
}

/// Optional in-app sink. GUI may keep using `LoopEvent` / AppState today;
/// wire this later for unified traces without moving inference into the UI.
enum VeraEventBus {
    /// No-op default. CLI writes JSONL via `VeraEventSink` in VeraCore.
    /// TODO(gui): append to session trace / SSE when observation layer lands.
    static func emit(_ event: VeraRuntimeEvent) {
        #if DEBUG
        // Keep quiet in GUI by default — CLI is the research log surface.
        _ = event
        #endif
    }
}
