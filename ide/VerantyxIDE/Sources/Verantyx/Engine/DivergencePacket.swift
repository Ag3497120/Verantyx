import Foundation

/// Swift port of `divergence_packet.py`'s `Proposition`/`DivergencePacket`
/// dataclasses and `packet_from_hidden_dist()`, for Milestone E's faithful
/// Council port. A packet is one role's structured "opinion" for a given
/// round -- a handful of grain-clipped claims plus scalar signals
/// (confidence, dissent keys, hidden-vector norm) that `DivergenceExchange`
/// scores against every other role's packet.
struct Proposition: Codable {
    static let minChars = 12
    static let maxChars = 240

    var text: String
    var confidence: Float
    /// claim | doubt | constraint | evidence
    var polarity: String

    init(text: String, confidence: Float = 0.5, polarity: String = "claim") {
        var t = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if t.count > Self.maxChars {
            t = String(t.prefix(Self.maxChars))
        }
        self.text = t
        self.confidence = min(max(confidence, 0), 1)
        self.polarity = polarity
    }

    var isValidGrain: Bool { text.count >= Self.minChars && text.count <= Self.maxChars }
}

struct DivergencePacket: Codable, Identifiable {
    static let maxPropositions = 4

    var id: String = String(UUID().uuidString.prefix(10)).lowercased()
    var role: String
    var axis: String?
    var propositions: [Proposition]
    /// Lowercased top-token strings -- candidate conflict keys used by
    /// `DivergenceExchange`'s dissent-clash term.
    var dissentKeys: [String]
    var confidence: Float
    var createdAt: Date = Date()

    // meta (flattened, matching divergence_packet.py's `meta` dict fields
    // actually consumed downstream)
    var zNorm: Float
    var distTop1: String
    var distEntropy: Float
    /// Caller-supplied evidence/factual-mass signal (defaults to 0 -- no
    /// separate fact-checking pipeline exists on the Swift side yet; the
    /// `E` term in `S = A·C+B·E−C·R+D·N` is a no-op until one is wired in).
    var evidenceMass: Float = 0.0

    /// The role's own hidden vector at packet-build time -- kept alongside
    /// the packet (unlike the Python original, which strips `intent_vec`
    /// before serialization) since `DivergenceExchange` needs it for
    /// cosine-divergence scoring and this struct is never persisted here.
    var vector: [Float]
    /// Top-3 candidate token strings (lowercased) the claims were built
    /// from -- Python's "proposition keys" for the Jaccard key-diff term.
    var propositionKeys: [String]
    /// token -> probability mass from the top-K distribution the packet
    /// was built from, for the token-mass-overlap term.
    var massByToken: [String: Float]

    /// Port of `normalize_grain`: drop propositions outside the valid
    /// char-length band, cap at `maxPropositions`, and blend the packet's
    /// own confidence 50/50 with the mean of its surviving propositions'.
    mutating func normalizeGrain() {
        propositions = Array(propositions.filter(\.isValidGrain).prefix(Self.maxPropositions))
        guard !propositions.isEmpty else { return }
        let meanConf = propositions.map(\.confidence).reduce(0, +) / Float(propositions.count)
        confidence = min(max(0.5 * confidence + 0.5 * meanConf, 0), 1)
    }
}

enum DivergencePacketBuilder {
    /// Port of `_confidence_from_dist`: Shannon entropy over the top-32
    /// (already-normalized) distribution weights, mapped to a 0.05-0.99
    /// confidence band -- low entropy (sharp distribution) => high
    /// confidence.
    static func confidence(fromEntropy entropy: Float) -> Float {
        min(max(1.0 / (1.0 + entropy / 3.0), 0.05), 0.99)
    }

    static func shannonEntropy(_ probs: [Float]) -> Float {
        let top = Array(probs.prefix(32))
        let sum = top.reduce(0, +)
        guard sum > 0 else { return 0 }
        var entropy: Float = 0
        for p in top {
            let w = p / sum
            if w > 0 { entropy -= w * log2(w) }
        }
        return entropy
    }

    /// Port of `packet_from_hidden_dist(role, z, dist, dictionary, tok)`:
    /// top-3 candidates become claim propositions, confidence derives from
    /// distribution entropy, and the top-6 candidates become dissent keys.
    /// `distribution` should be `JCrossChatManager.topKDistributionText`'s
    /// output, sorted by probability descending (as the FFI guarantees).
    static func packet(role: String, vector: [Float], distribution: [JCrossChatManager.TopKText]) -> DivergencePacket {
        let top3 = Array(distribution.prefix(3))
        var propositions: [Proposition] = []
        var propositionKeys: [String] = []
        if top3.isEmpty {
            propositions.append(Proposition(text: "No strong lexical candidate; keep the question open.", confidence: 0.3))
        } else {
            for entry in top3 {
                let token = entry.text.trimmingCharacters(in: .whitespacesAndNewlines)
                guard !token.isEmpty else { continue }
                let claim = "Candidate answer emphasizes '\(token)' (p=\(String(format: "%.2f", entry.prob)))."
                propositions.append(Proposition(text: claim, confidence: entry.prob))
                propositionKeys.append(token.lowercased())
            }
        }

        let entropy = shannonEntropy(distribution.map(\.prob))
        let conf = confidence(fromEntropy: entropy)
        let dissentKeys = Array(distribution.prefix(6))
            .map { $0.text.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() }
            .filter { !$0.isEmpty }
        let zNorm = sqrt(vector.reduce(Float(0)) { $0 + $1 * $1 })
        let top1 = distribution.first?.text.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() ?? ""
        var massByToken: [String: Float] = [:]
        for entry in distribution {
            let key = entry.text.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            guard !key.isEmpty else { continue }
            massByToken[key, default: 0] += entry.prob
        }

        var packet = DivergencePacket(
            role: role,
            axis: nil,
            propositions: propositions,
            dissentKeys: dissentKeys,
            confidence: conf,
            zNorm: zNorm,
            distTop1: top1,
            distEntropy: entropy,
            vector: vector,
            propositionKeys: propositionKeys,
            massByToken: massByToken
        )
        packet.normalizeGrain()
        return packet
    }
}
