import Foundation
import SwiftUI

/// The stereo cross as the routing state it actually is.
///
/// The design rule this exists to keep honest: a question does not go
/// straight into the transcript. It enters the cross, is routed, and the
/// answer leaves from there — and the picture of that must be driven by
/// the real call, never by a timer pretending. Every publish here comes
/// from `VeraMemoryBridge.callDoor`, the single road every Vera door
/// takes, so the light on screen and the work in the engine are the same
/// event. When nothing is being asked, the cross is still: motion is a
/// consequence of a call, and a cross that animates on its own would be
/// decoration claiming to be state.
///
/// Two crosses exist and are not mixed. The SIX ARMS are structure —
/// support/oppose, cause/effect, general/instance (the engine's
/// `arm_schema`), and a fact with no surface cue has no arm at all. The
/// PHASES below are process: which stage of the pipeline the current
/// call is in. This type carries the phase; the arms are lit only by
/// what an answer actually reports, never by guesswork.
@MainActor
final class VeraRouteState: ObservableObject {
    static let shared = VeraRouteState()

    /// Where a live call sits. `idle` is the resting state and the one
    /// the view must spend most of its life in.
    enum Phase: String {
        case idle
        case routing        // the call is out; the engine is deciding
        case answered       // a verdict came back with evidence
        case refused        // a typed refusal came back
        case saving         // a claim is travelling toward memory
        case recalling      // memory is being read back through the cross
    }

    /// Which door the live call went through — the reader can see that
    /// a diff and an ask are not the same journey.
    @Published private(set) var phase: Phase = .idle
    @Published private(set) var door: String = ""
    @Published private(set) var verdict: String = ""
    /// Agreement band, when the answer carried one (`grain n/m`).
    @Published private(set) var grainAgree: Int?
    @Published private(set) var grainOf: Int?
    @Published private(set) var witnesses: Int?
    /// Named sources behind the shown facets — the provenance the band
    /// prints. Empty is honest: not every verdict has one.
    @Published private(set) var origins: [String] = []
    /// Structural arms the answer actually touched. Never inferred.
    @Published private(set) var arms: Set<CrossArm> = []
    /// Rises once per completed call so a view can run one pulse and
    /// then go quiet, instead of animating continuously.
    @Published private(set) var pulse: Int = 0

    enum CrossArm: String, CaseIterable {
        case support, oppose, cause, effect, general, instance

        var label: String {
            switch self {
            case .support:  return "支持"
            case .oppose:   return "反論"
            case .cause:    return "原因"
            case .effect:   return "結果"
            case .general:  return "一般"
            case .instance: return "実例"
            }
        }
    }

    /// The last completed reading, kept after the motion stops. Still
    /// is the resting STATE, not a blank: a band that forgets what it
    /// just reported makes the reader re-ask to see provenance again.
    @Published private(set) var lastReading: String = ""

    private var settle: Task<Void, Never>?

    // MARK: - Publishes from the real call

    func began(door: String) {
        settle?.cancel()
        self.door = door
        phase = door.contains("summarize") || door.contains("remember")
            ? .saving
            : (door.contains("recall") ? .recalling : .routing)
        verdict = ""
        grainAgree = nil; grainOf = nil; witnesses = nil
        origins = []; arms = []
    }

    /// Read the door's own JSON. Nothing is invented: a field that is
    /// absent stays absent, and the view renders that absence.
    func finished(door: String, payload: [String: Any]?) {
        guard let obj = payload else {
            phase = .refused
            verdict = "UNKNOWN_CALL_FAILED"
            bump()
            return
        }
        let v = (obj["verdict"] as? String) ?? ""
        verdict = v
        phase = v.hasPrefix("UNKNOWN") || v.hasPrefix("ABSTAIN") ? .refused : .answered

        if let g = obj["grain"] as? [String: Any] {
            grainAgree = g["agree"] as? Int
            grainOf = g["of"] as? Int
        }
        if let w = obj["witnesses"] as? [String: Any] {
            witnesses = (w["agree"] as? Int) ?? (w["answered"] as? Int)
        }
        if let o = obj["facet_origin"] as? [String: Any] {
            var named = Set<String>()
            for value in o.values {
                for label in (value as? [String] ?? []) {
                    named.insert(label)
                }
            }
            origins = named.sorted().prefix(4).map { $0 }
        }
        arms = Self.armsTouched(obj)
        bump()
    }

    /// Arms are read from the answer, never guessed. A staged chain
    /// walked cause→effect; a diff that found shared ground touched
    /// general/instance; an observed negation lit oppose. An answer
    /// with no such evidence lights no arm, which is the engine's own
    /// "untagged is a first-class state" rule kept on screen.
    private static func armsTouched(_ obj: [String: Any]) -> Set<CrossArm> {
        var out: Set<CrossArm> = []
        if obj["stage_split"] != nil { out.insert(.cause); out.insert(.effect) }
        if let shared = obj["shared"] as? [[String: Any]], !shared.isEmpty {
            out.insert(.general)
        }
        if let a = obj["only_a"] as? [[String: Any]], !a.isEmpty {
            out.insert(.instance)
        }
        if let b = obj["only_b"] as? [[String: Any]], !b.isEmpty {
            out.insert(.instance)
        }
        let blob = (obj["text"] as? String) ?? ""
        if blob.contains("¬") { out.insert(.oppose) }
        if let units = obj["units"] as? [[String: Any]], !units.isEmpty {
            out.insert(.general)
        }
        if (obj["witnesses"] as? [String: Any]) != nil { out.insert(.support) }
        return out
    }

    /// A save that landed in memory: the claim travelled through the
    /// cross and stopped. Called by the save gate, not by the view.
    func stored() {
        phase = .saving
        bump()
    }

    private func bump() {
        pulse &+= 1
        lastReading = liveReading
        settle?.cancel()
        settle = Task { [weak self] in
            try? await Task.sleep(nanoseconds: 2_600_000_000)
            guard !Task.isCancelled else { return }
            await MainActor.run { self?.phase = .idle }
        }
    }

    /// The one-line reading a header can show without opening anything.
    var summary: String {
        if phase == .idle {
            return lastReading.isEmpty ? "静止" : lastReading
        }
        return liveReading
    }

    private var liveReading: String {
        switch phase {
        case .idle:      return lastReading
        case .routing:   return "ルーティング中 · \(door)"
        case .saving:    return "記憶へ"
        case .recalling: return "記憶を参照"
        case .answered:
            var parts = [verdict]
            if let a = grainAgree, let o = grainOf { parts.append("grain \(a)/\(o)") }
            if let w = witnesses { parts.append("witnesses \(w)") }
            return parts.joined(separator: " · ")
        case .refused:   return verdict
        }
    }
}
