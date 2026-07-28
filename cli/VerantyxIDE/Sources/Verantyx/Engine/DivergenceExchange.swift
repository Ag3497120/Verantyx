import Foundation

/// Swift port of `divergence_exchange.py`'s `exchange_packets()` -- scores
/// each role's `DivergencePacket` against every other role's, decides
/// whether the round's opinions can be merged as-is (`joined`), need one
/// reconciliation pass on the most-divergent roles (`reinfer`), or need to
/// escalate to a stronger backend (`escalate`), and produces the S_i
/// consensus weights `CouncilOrchestrator` blends opinions with. Constants
/// and formula are verbatim from the Python original.
enum DivergenceExchange {
    static let coeffConfidence: Float = 1.0   // A
    static let coeffEvidence: Float = 0.6     // B
    static let coeffRisk: Float = 0.8         // C
    static let coeffNovelty: Float = 0.4      // D
    static let divergenceHigh: Float = 0.42
    static let joinThresholdBase: Float = 0.35
    static let joinThresholdMax: Float = 0.62

    enum Action: String { case joined, reinfer, escalate }

    struct Result {
        let action: Action
        /// role -> normalized weight (raw = max(S,0.05), no softmax, no
        /// majority vote).
        let weights: [String: Float]
        /// roles whose own mean pairwise divergence is at or above the
        /// group mean -- the reconciliation/reinfer target set.
        let splitRoles: [String]
        let meanDivergence: Float
    }

    /// Ramps from `joinThresholdBase` to `joinThresholdMax` as mean
    /// divergence rises past `divergenceHigh` toward 1.0. Not itself part
    /// of the join/reinfer/escalate decision (that branches on
    /// `divergenceHigh` directly, per the Python original) -- kept for
    /// parity/diagnostics.
    static func joinThreshold(forDivergence meanDiv: Float) -> Float {
        guard meanDiv > divergenceHigh else { return joinThresholdBase }
        let t = min(max((meanDiv - divergenceHigh) / (1.0 - divergenceHigh), 0), 1)
        return joinThresholdBase + t * (joinThresholdMax - joinThresholdBase)
    }

    static func cosine(_ a: [Float], _ b: [Float]) -> Float {
        guard a.count == b.count, !a.isEmpty else { return 0 }
        var dot: Float = 0, na: Float = 0, nb: Float = 0
        for i in 0..<a.count { dot += a[i] * b[i]; na += a[i] * a[i]; nb += b[i] * b[i] }
        let denom = sqrt(na) * sqrt(nb)
        return denom > 0 ? dot / denom : 0
    }

    static func tokenMassOverlap(_ a: [String: Float], _ b: [String: Float]) -> Float {
        var overlap: Float = 0
        for (key, massA) in a {
            if let massB = b[key] { overlap += min(massA, massB) }
        }
        return overlap
    }

    static func jaccard(_ a: [String], _ b: [String]) -> Float {
        let sa = Set(a), sb = Set(b)
        guard !sa.isEmpty || !sb.isEmpty else { return 1 }
        let intersection = sa.intersection(sb).count
        let union = sa.union(sb).count
        return union > 0 ? Float(intersection) / Float(union) : 1
    }

    /// Port of `pairwise_divergence(a, b)`.
    static func pairwiseDivergence(_ a: DivergencePacket, _ b: DivergencePacket) -> Float {
        let keyDiff = 1.0 - jaccard(a.propositionKeys, b.propositionKeys)

        let sa = Set(a.dissentKeys), sb = Set(b.dissentKeys)
        var dissentClash: Float = 0
        let union = sa.union(sb).count
        if union > 0 {
            dissentClash = Float(sa.intersection(sb).count) / Float(union)
        }
        if keyDiff > 0.5 { dissentClash = 1 - dissentClash }

        let cos = cosine(a.vector, b.vector)
        let overlap = tokenMassOverlap(a.massByToken, b.massByToken)
        let hiddenDiv = 0.5 * (1 - cos) + 0.5 * (1 - overlap)

        return min(max(0.45 * hiddenDiv + 0.35 * keyDiff + 0.20 * dissentClash, 0), 1)
    }

    /// Port of `weighted_consensus_vector`: weighted sum of L2-normalized
    /// role vectors, renormalized to `baseNorm` (or the mean of the
    /// contributing norms if none given).
    static func weightedConsensusVector(vectors: [String: [Float]], weights: [String: Float], baseNorm: Float?) -> [Float]? {
        guard let dim = vectors.values.first?.count, dim > 0 else { return nil }
        var acc = [Float](repeating: 0, count: dim)
        var normSum: Float = 0
        var normCount = 0
        for (role, vec) in vectors {
            let n = sqrt(vec.reduce(Float(0)) { $0 + $1 * $1 })
            guard n > 0 else { continue }
            let w = weights[role] ?? 0
            for i in 0..<dim { acc[i] += w * (vec[i] / n) }
            normSum += n
            normCount += 1
        }
        let accNorm = sqrt(acc.reduce(Float(0)) { $0 + $1 * $1 })
        guard accNorm > 0 else { return nil }
        let target = baseNorm ?? (normCount > 0 ? normSum / Float(normCount) : 1)
        return acc.map { $0 / accNorm * target }
    }

    /// Port of `exchange_packets(packets, zs, dists, reinfer_done)`.
    static func exchange(packets: [DivergencePacket], reinferDone: Bool) -> Result {
        let n = packets.count
        guard n > 0 else {
            return Result(action: .escalate, weights: [:], splitRoles: [], meanDivergence: 1.0)
        }

        if n == 1 {
            // S = A_C*C + B_E*E (no R/N terms with nothing to compare
            // against) -- weight is trivially 1.0 either way, so the score
            // itself isn't needed downstream.
            return Result(action: .joined, weights: [packets[0].role: 1.0], splitRoles: [], meanDivergence: 0)
        }

        // Pairwise divergence matrix + per-role mean divergence.
        var pairDiv: [[Float]] = Array(repeating: Array(repeating: 0, count: n), count: n)
        var roleMeanDiv = [String: Float](minimumCapacity: n)
        var allDivs: [Float] = []
        for i in 0..<n {
            var sumI: Float = 0
            for j in 0..<n where i != j {
                let d = i < j ? pairwiseDivergence(packets[i], packets[j]) : pairDiv[j][i]
                pairDiv[i][j] = d
                sumI += d
                if i < j { allDivs.append(d) }
            }
            roleMeanDiv[packets[i].role] = sumI / Float(max(n - 1, 1))
        }
        let meanDiv = allDivs.isEmpty ? 0 : allDivs.reduce(0, +) / Float(allDivs.count)

        // Per-packet S = A*C + B*E - C*R + D*N.
        let allKeys = packets.map { Set($0.propositionKeys) }
        var scores: [String: Float] = [:]
        for (idx, p) in packets.enumerated() {
            let c = min(max(p.confidence, 0), 1)
            let e = p.evidenceMass
            let r = min(max(0.5 * meanDiv + 0.5 * (roleMeanDiv[p.role] ?? 0), 0), 1)
            let mine = allKeys[idx]
            var othersUnion = Set<String>()
            for (j, keys) in allKeys.enumerated() where j != idx { othersUnion.formUnion(keys) }
            let novel = mine.isEmpty ? 0 : Float(mine.subtracting(othersUnion).count) / Float(mine.count)
            let s = coeffConfidence * c + coeffEvidence * e - coeffRisk * r + coeffNovelty * novel
            scores[p.role] = s
        }
        let rawWeights = scores.mapValues { max($0, 0.05) }
        let totalWeight = max(rawWeights.values.reduce(0, +), 0.0001)
        let weights = rawWeights.mapValues { $0 / totalWeight }

        if meanDiv < divergenceHigh {
            return Result(action: .joined, weights: weights, splitRoles: [], meanDivergence: meanDiv)
        }

        var splitRoles = packets.filter { (roleMeanDiv[$0.role] ?? 0) >= meanDiv }.map(\.role)
        if splitRoles.isEmpty { splitRoles = packets.map(\.role) }

        return Result(action: reinferDone ? .escalate : .reinfer, weights: weights, splitRoles: splitRoles, meanDivergence: meanDiv)
    }
}
