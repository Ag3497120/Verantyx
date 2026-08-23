import Foundation
import CoreGraphics

/// Vera-a-V isolated time-series ring for ~1fps keyframe observations.
/// Does **not** write GapGraph / vera-memory / EternalMemoryStore — those stay
/// on the existing event-driven UI step path (Milestone S / UI-trace).
actor VeraAVRing {
    static let shared = VeraAVRing()

    struct Observation: Codable, Sendable {
        let ts: TimeInterval
        let sessionId: String
        let appName: String
        let changed: Bool
        let region: [Double]?
        let axDeltaSummary: String
        let note: String
    }

    /// ~60s at 1Hz when every tick changes; unchanged ticks are not stored.
    private let capacity = 60
    private var nodes: [Observation] = []
    private(set) var lastChangeTs: TimeInterval = 0
    private(set) var ticksAttempted: Int = 0
    private(set) var ticksDroppedUnchanged: Int = 0
    private(set) var ticksCaptured: Int = 0

    private init() {}

    func clear() {
        nodes.removeAll()
        lastChangeTs = 0
    }

    func clearSession() {
        clear()
        ticksAttempted = 0
        ticksDroppedUnchanged = 0
        ticksCaptured = 0
    }

    func noteTickAttempted() {
        ticksAttempted += 1
    }

    func noteTickDroppedUnchanged() {
        ticksDroppedUnchanged += 1
    }

    func append(_ obs: Observation) {
        nodes.append(obs)
        if obs.changed { lastChangeTs = obs.ts }
        ticksCaptured += 1
        if nodes.count > capacity {
            nodes.removeFirst(nodes.count - capacity)
        }
    }

    func recent(limit: Int = 3) -> [Observation] {
        Array(nodes.suffix(limit))
    }

    func lastChange() -> Observation? {
        nodes.last(where: { $0.changed }) ?? nodes.last
    }

    /// Seconds since last recorded visual change. `nil` if none yet.
    func secondsSinceLastChange(now: TimeInterval = Date().timeIntervalSince1970) -> TimeInterval? {
        guard lastChangeTs > 0 else { return nil }
        return max(0, now - lastChangeTs)
    }

    func recallRecentBlock(limit: Int = 3) -> String {
        let hits = recent(limit: limit)
        guard !hits.isEmpty else { return "" }
        let now = Date().timeIntervalSince1970
        let lines = hits.map { o -> String in
            let ago = Int(max(0, now - o.ts))
            let regionDesc: String
            if let r = o.region, r.count >= 4 {
                regionDesc = String(format: "region (%.0f,%.0f %.0fx%.0f)", r[0], r[1], r[2], r[3])
            } else {
                regionDesc = "no-region"
            }
            let delta = o.axDeltaSummary.isEmpty ? "" : " ax:\(o.axDeltaSummary)"
            return "  ⏱️ \(ago)s ago — \(o.appName): \(o.note) [\(regionDesc)]\(delta)"
        }.joined(separator: "\n")
        return "\n[KEYFRAME EYE — Vera-a-V recent changes]\n\(lines)\n[/KEYFRAME EYE]\n"
    }

    func statusMap() -> [String: Any] {
        [
            "ring_count": nodes.count,
            "ticks_attempted": ticksAttempted,
            "ticks_dropped_unchanged": ticksDroppedUnchanged,
            "ticks_captured": ticksCaptured,
            "seconds_since_last_change": secondsSinceLastChange() as Any,
        ]
    }

    static func regionArray(_ r: CGRect?) -> [Double]? {
        guard let r else { return nil }
        return [Double(r.origin.x), Double(r.origin.y), Double(r.width), Double(r.height)]
    }
}
