import Foundation

/// Shape of a situation, independent of its wording.
///
/// Swift-side counterpart of Vera-a's `structural_similarity.py`. The idea it
/// carries over: two problems can look nothing alike as text ("profile save
/// doesn't work" / "3D export doesn't work") while sharing the same underlying
/// shape — same role, same failure mode, same expected-vs-observed transition.
/// Comparing that shape lets a strategy learned on one transfer to the other
/// without pretending they are the same topic.
///
/// Kept lexicographic like the Python original rather than collapsed into one
/// weighted number: a role mismatch disqualifies no matter how well everything
/// else lines up, and "same failure shape, different evidence" stays visibly
/// distinct from "same failure shape, same evidence".
public struct StructuralSignature: Codable, Sendable, Equatable {
    public var nodeType: String
    public var role: String?
    public var failureType: String?
    public var observedTransition: String?
    public var resolved: Bool

    public init(
        nodeType: String, role: String? = nil, failureType: String? = nil,
        observedTransition: String? = nil, resolved: Bool = false
    ) {
        self.nodeType = nodeType
        self.role = role
        self.failureType = failureType
        self.observedTransition = observedTransition
        self.resolved = resolved
    }

    public init(gap: GapNode) {
        self.init(
            nodeType: gap.gapType,
            role: gap.scope,
            failureType: gap.failureType,
            observedTransition: gap.observedTransition,
            resolved: gap.status == .resolved
        )
    }

    public enum MatchLevel: String, Sendable, Comparable {
        case notComparable = "NOT_COMPARABLE"
        case structuralCandidate = "STRUCTURAL_CANDIDATE"
        case highConfidence = "HIGH_CONFIDENCE"
        /// Same shape *and* the other one was settled — the case worth reusing.
        case skillReuseCandidate = "SKILL_REUSE_CANDIDATE"

        private var rank: Int {
            switch self {
            case .notComparable: return 0
            case .structuralCandidate: return 1
            case .highConfidence: return 2
            case .skillReuseCandidate: return 3
            }
        }

        public static func < (a: MatchLevel, b: MatchLevel) -> Bool { a.rank < b.rank }

        /// Multiplier on a memory's decay half-life.
        ///
        /// This is where structure answers the aging question. Pure time decay
        /// says a six-month-old note is stale; but if its *shape* is the shape
        /// of the problem in front of you now, it is the most useful thing in
        /// the store, and letting the clock bury it is the wrong behaviour. A
        /// structural match therefore slows forgetting rather than adding a
        /// flat bonus — nothing is deleted either way, it stays reachable.
        ///
        /// Incomparable records get 1.0: noise must not gain longevity.
        public var ageResistance: Double {
            switch self {
            case .notComparable: return 1
            case .structuralCandidate: return 2
            case .highConfidence: return 4
            case .skillReuseCandidate: return 8
            }
        }

        /// Small additive nudge used to break ties between records of
        /// comparable similarity. Deliberately too small to let an unrelated
        /// memory outrank a genuinely close one — structure ranks, it does not
        /// overrule content.
        public var recallBoost: Float {
            switch self {
            case .notComparable: return 0
            case .structuralCandidate: return 0.02
            case .highConfidence: return 0.05
            case .skillReuseCandidate: return 0.08
            }
        }
    }

    /// Ordered rules, mirroring `classify_match`.
    public func match(_ other: StructuralSignature) -> MatchLevel {
        // Unset fields are not "equal" — fail closed rather than let two blank
        // signatures look like a perfect match.
        guard let role, let failureType,
              let otherRole = other.role, let otherFailure = other.failureType else {
            return .notComparable
        }
        guard role == otherRole else { return .notComparable }
        guard failureType == otherFailure else { return .notComparable }
        guard nodeType == other.nodeType else { return .structuralCandidate }
        guard observedTransition == other.observedTransition else { return .structuralCandidate }
        return other.resolved ? .skillReuseCandidate : .highConfidence
    }
}
