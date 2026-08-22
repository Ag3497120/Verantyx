import Foundation
import CoreGraphics

// MARK: - A vision tower that is trained by use, not by pretraining
//
// The conventional tower is a CNN or ViT aligned to a text space by
// contrastive training on captioned images. That cannot be built here, and
// bolting on a pretrained one would put the understanding back inside a model
// — the thing this architecture exists to avoid. A VLM's grasp of a screen
// dies with the VLM; the point of vera-a is knowledge that outlives the model.
//
// So invert it. The tower does not produce meaning. It produces STRUCTURE,
// deterministically and cheaply, and meaning is accumulated onto that
// structure from a source of ground truth this machine already has.
//
//   pixels ──▶ structural descriptor        (no training, no model)
//                     ▲
//                     │ paired, for free, at the same instant
//                     ▼
//              Accessibility tree           (exact labels, roles, title)
//                     │
//                     ▼
//              vera-a similarity space      (accumulate, consolidate)
//                     │
//                     ▼
//              typed verdict on a new screen
//
// The unusual asset here is the middle row. Most vision systems have no
// labels for the frames they see; this one has a precise, structured caption
// for every screen the agent looks at, produced by the OS, at zero cost,
// during ordinary work. DESKTOP_SNAPSHOT already captures both at the same
// moment in the same function — the pairs were being thrown away.
//
// What that buys: when AX is later unavailable — Chrome refusing to publish,
// a canvas app, a game, a remote desktop, a screenshot of a screenshot — the
// structure can still be recognised, because the mapping was learned while AX
// *was* available. That is the case a pretrained VLM is usually reached for,
// and this reaches it without one.
//
// What it cannot do: recognise a screen it has never seen anything like. It
// says so rather than guessing, which is the same discipline vera-a applies
// to text — an UNKNOWN with a reason beats a confident wrong answer.
enum VisionTower {

    // MARK: - The descriptor
    //
    // ScreenSignature carries luminance and local contrast. Layout adds the
    // part that identifies a KIND of screen rather than one instance: where
    // the dense regions sit relative to each other. A login form and an
    // article differ in layout long before they differ in any pixel you could
    // name.

    struct Layout: Equatable {
        /// Fraction of cells that are text-dense (high local contrast).
        let density: Double
        /// Vertical centre of mass of the dense cells, 0 (top) … 1 (bottom).
        let verticalBias: Double
        /// Horizontal centre of mass, 0 (left) … 1 (right).
        let horizontalBias: Double
        /// How spread out the dense cells are. A form is concentrated; an
        /// article is even; a dashboard is patchy.
        let dispersion: Double

        var encoded: String {
            String(format: "L%.2f,%.2f,%.2f,%.2f",
                   density, verticalBias, horizontalBias, dispersion)
        }

        static func decode(_ s: String) -> Layout? {
            guard s.hasPrefix("L") else { return nil }
            let p = s.dropFirst().split(separator: ",").compactMap { Double($0) }
            guard p.count == 4 else { return nil }
            return Layout(density: p[0], verticalBias: p[1],
                          horizontalBias: p[2], dispersion: p[3])
        }

        func distance(to o: Layout) -> Double {
            (abs(density - o.density) + abs(verticalBias - o.verticalBias)
             + abs(horizontalBias - o.horizontalBias) + abs(dispersion - o.dispersion)) / 4
        }

        static func from(_ sig: ScreenSignature) -> Layout {
            let side = ScreenSignature.side
            // Local contrast is the proxy for "there is text or an edge here".
            let dense = sig.contrast.enumerated().filter { $0.element > 0.18 }
            guard !dense.isEmpty else {
                return Layout(density: 0, verticalBias: 0.5,
                              horizontalBias: 0.5, dispersion: 0)
            }
            let n = Double(dense.count)
            let ys = dense.map { Double($0.offset / side) / Double(side - 1) }
            let xs = dense.map { Double($0.offset % side) / Double(side - 1) }
            let my = ys.reduce(0, +) / n
            let mx = xs.reduce(0, +) / n
            let spread = zip(ys, xs)
                .map { abs($0 - my) + abs($1 - mx) }
                .reduce(0, +) / n
            return Layout(density: n / Double(side * side),
                          verticalBias: my, horizontalBias: mx, dispersion: spread)
        }
    }

    /// One look at a screen: what it looked like, and — when Accessibility
    /// could see it — what was actually on it.
    struct Observation {
        let signature: ScreenSignature
        let layout: Layout
        let app: String
        let windowTitle: String
        /// Control labels from the AX tree. The free caption.
        let labels: [String]
    }

    // MARK: - Encoding

    static func encode(image: CGImage, app: String, axMap: String) -> Observation? {
        guard let sig = ScreenSignature.from(image) else { return nil }
        return Observation(
            signature: sig,
            layout: Layout.from(sig),
            app: app,
            windowTitle: ForegroundAppOperator.windowTitle(from: axMap),
            labels: Array(labels(from: axMap).prefix(24)))
    }

    /// The caption, taken from the AX tree. Titles and values only — roles
    /// alone ("button", "link") describe every screen equally and identify
    /// none of them.
    static func labels(from axMap: String) -> [String] {
        // `title` and `value` were the only names read, from a snapshot that
        // only ever emitted those two. The tree now also carries `label`
        // (AXDescription — where aria-label lands), `placeholder` and `help`,
        // which on web and Electron controls are frequently the ONLY name a
        // control has. Leaving them out would caption exactly the screens this
        // tower exists for — the ones with no titles — as if they were blank.
        guard let re = try? NSRegularExpression(
            pattern: #"(?:title|label|placeholder|help|value)="([^"]{2,40})""#,
            options: [.caseInsensitive])
        else { return [] }
        let ns = axMap as NSString
        var seen = Set<String>()
        var out: [String] = []
        for m in re.matches(in: axMap, range: NSRange(location: 0, length: ns.length)) {
            let t = ns.substring(with: m.range(at: 1))
                .trimmingCharacters(in: .whitespacesAndNewlines)
            guard t.count >= 2, !t.hasPrefix("http"), seen.insert(t.lowercased()).inserted
            else { continue }
            out.append(t)
        }
        return out
    }

    // MARK: - The verdict
    //
    // Same three-way shape vera-a uses for text, for the same reason: the two
    // kinds of not-knowing need different responses. Never having seen a
    // screen like this means look at it properly; having seen similar ones
    // that disagree means the structure is ambiguous and something else must
    // decide.

    enum Verdict {
        /// Enough neighbours agree on what this screen carries.
        case recognised(labels: [String], support: Int, distance: Double)
        /// Nothing structurally similar has ever been recorded.
        case unknownNoEvidence
        /// Similar screens exist but do not agree enough to assert anything.
        case unknownInsufficient(nearest: Double, support: Int)

        var text: String {
            switch self {
            case .recognised(let labels, let support, let distance):
                return "[VISION] 見覚えのある画面です"
                    + "（距離 \(String(format: "%.3f", distance))・一致 \(support)件）\n"
                    + "以前この構造で見えていたもの: " + labels.prefix(10).joined(separator: " / ")
            case .unknownNoEvidence:
                return "[VISION] UNKNOWN_NO_EVIDENCE — この構造の画面は記録にありません。"
                    + "推測せず [DESKTOP_SNAPSHOT] で実際に読んでください。"
            case .unknownInsufficient(let nearest, let support):
                return "[VISION] UNKNOWN_INSUFFICIENT_EVIDENCE — 似た画面は"
                    + "\(support)件ありますが（最近傍 \(String(format: "%.3f", nearest))）、"
                    + "内容が一致しません。構造だけでは判断できないので実際に読んでください。"
            }
        }
    }

    /// How close two observations must be to count as the same kind of screen.
    /// Looser than ScreenSignature.sameScreenThreshold, which asks "is this
    /// the same instance"; this asks "is this the same kind".
    static let kindThreshold = 0.14

    /// Layout must agree before appearance is consulted at all. A gate, not a
    /// weight — see the stacking note in `visualVerdict`.
    static let layoutGate = 0.18

    /// At least this many agreeing neighbours before asserting anything. Two
    /// is a coincidence; the cost of a wrong assertion here is the agent
    /// acting on a screen it has misidentified.
    static let minSupport = 3
}
