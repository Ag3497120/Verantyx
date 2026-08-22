import Foundation

// MARK: - Shared runtime event schema (CLI + future GUI)
//
// Dual-track posture:
//   • CLI (`vera run`) is the research / repro interface and JSONL source of truth.
//   • GUI (Verantyx IDE) stays fully intact — chat, mirror, Act, MCP, settings.
//   • Later: GUI thin-visualizes these events; do NOT rebuild GUI as a second brain.
//
// Keep this schema minimal and text-small-model friendly (flat string fields).
// IDE mirror: `cli/VerantyxIDE/Sources/Verantyx/Engine/VeraRuntimeEvent.swift`
// (same shapes — keep in sync until VeraCore is linked into the app target).

/// Event kinds visible on the research CLI:
/// `MISSION / OBSERVATION / PROPOSED_ACTION / POLICY / RESULT` (+ gap, skill_recall).
public enum VeraEventKind: String, Codable, Sendable, CaseIterable {
    case mission
    case observation
    case proposed_action
    case policy
    case result
    case gap
    case skill_recall
}

/// One structured runtime event. Encoded as a single JSONL line.
public struct VeraRuntimeEvent: Codable, Sendable, Equatable {
    public var schemaVersion: Int
    public var ts: String
    public var kind: VeraEventKind
    public var missionId: String
    public var turn: Int?
    public var summary: String
    /// Flat bag for small models / log grepping. Prefer short strings.
    /// Optional keys include `mission_kind` (`act`|`speak`) on `.mission` events.
    public var detail: [String: String]
    public var tags: [String]

    public enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case ts
        case kind
        case missionId = "mission_id"
        case turn
        case summary
        case detail
        case tags
    }

    public static let currentSchemaVersion = 1

    public init(
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
}

extension VeraRuntimeEvent {
    /// Human-readable one-liner for structured stdout (research interface).
    public var cliLine: String {
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
