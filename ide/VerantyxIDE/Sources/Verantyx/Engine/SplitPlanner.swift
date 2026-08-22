import Foundation

/// Decides where to cut a model's layers between two Macs.
///
/// Works from the real tensor table (`JGenIdentity.Layout.perLayerBytes`), not
/// from a parameter-count estimate. Layers are not uniform — attention and MLP
/// widths differ, hybrids interleave two layer types with very different sizes —
/// and a machine planned smaller than the weights it will actually fault in is
/// a machine that swaps.
enum SplitPlanner {

    /// Memory factor for pipeline mode, deliberately separate from
    /// `MachineProfile.usableModelRAMGB` (0.6).
    ///
    /// The arithmetic that forces this: the motivating model, qwen3.6-27b, needs
    /// about 57.6 GB. At 0.6 the pair here gives 24×0.6 + 64×0.6 = **52.8 GB**,
    /// and the model does not fit at any split point. At 0.75 it is 18 + 48 =
    /// 66 GB, which fits with roughly 8 GB of slack.
    ///
    /// Pipeline mode exists precisely because the model does not fit under the
    /// conservative factor, so applying that same factor would make the feature
    /// unable to do the one thing it is for. The trade is real and the UI says
    /// so: both Macs run near the edge and macOS may compress or swap.
    static let pipelineRAMFactor: Double = 0.75

    struct Budget: Equatable {
        var totalRAMGB: Double
        var usableGB: Double { totalRAMGB * pipelineRAMFactor }
    }

    struct Plan: Equatable {
        /// Master runs `[0, k)`, worker runs `[k, N)`.
        var k: Int
        var masterNeedGB: Double
        var workerNeedGB: Double
        var masterHeadroomGB: Double
        var workerHeadroomGB: Double
    }

    enum Outcome: Equatable {
        case fits(Plan)
        /// No `k` in `1..<N` satisfies both machines.
        ///
        /// Reported with numbers rather than falling back to a "best effort"
        /// split: a plan that swaps looks like the feature working until the
        /// machine becomes unusable, which is worse than being told it does not
        /// fit.
        case doesNotFit(reason: String, bestK: Int, bestOverflowGB: Double)
        case modelTooSmall(reason: String)
    }

    /// Model shape derived from the tensor table.
    struct ModelShape: Equatable {
        var numLayers: Int
        /// Bytes per layer index.
        var perLayerBytes: [Int: UInt64]
        /// `embed_tokens` — paid by whoever turns tokens into vectors: the master.
        var embedBytes: UInt64
        /// `lm_head` + final norm — paid by whoever produces logits: the worker.
        var lmHeadBytes: UInt64
        /// Everything else (norms, biases); small, and split proportionally.
        var otherNonLayerBytes: UInt64

        static func from(_ layout: JGenIdentity.Layout) -> ModelShape {
            let other = layout.nonLayerBytes >= (layout.embedBytes + layout.lmHeadBytes)
                ? layout.nonLayerBytes - layout.embedBytes - layout.lmHeadBytes
                : 0
            return ModelShape(numLayers: layout.layerCount,
                              perLayerBytes: layout.perLayerBytes,
                              embedBytes: layout.embedBytes,
                              lmHeadBytes: layout.lmHeadBytes,
                              otherNonLayerBytes: other)
        }

        var totalGB: Double {
            let sum = perLayerBytes.values.reduce(UInt64(0), +)
                + embedBytes + lmHeadBytes + otherNonLayerBytes
            return Double(sum) / Double(1 << 30)
        }

        func layersGB(_ range: Range<Int>) -> Double {
            Double(range.reduce(UInt64(0)) { $0 + (perLayerBytes[$1] ?? 0) }) / Double(1 << 30)
        }
        var embedGB: Double { Double(embedBytes) / Double(1 << 30) }
        var lmHeadGB: Double { Double(lmHeadBytes) / Double(1 << 30) }
        /// Half the leftovers each; too small to be worth modelling precisely.
        var sharedGB: Double { Double(otherNonLayerBytes) / Double(1 << 30) / 2 }
    }

    // MARK: - Auto

    /// Picks `k` to equalise how much headroom each machine has left, then
    /// verifies both actually fit.
    ///
    /// Equalising *headroom fraction* rather than layer count is what makes an
    /// asymmetric pair (24 GB + 64 GB here) work: an even layer split would put
    /// the same load on both and overflow the smaller one long before the larger
    /// one was near capacity.
    static func auto(shape: ModelShape, master: Budget, worker: Budget) -> Outcome {
        let n = shape.numLayers
        guard n >= 2 else {
            return .modelTooSmall(reason: "A \(n)-layer model cannot be split across two machines.")
        }

        let masterRoom = master.usableGB - shape.embedGB - shape.sharedGB
        let workerRoom = worker.usableGB - shape.lmHeadGB - shape.sharedGB
        guard masterRoom > 0, workerRoom > 0 else {
            return .doesNotFit(
                reason: "One machine cannot even hold the embedding table or the output head.",
                bestK: n / 2, bestOverflowGB: 0)
        }

        let ideal = masterRoom / (masterRoom + workerRoom) * Double(n)
        let seed = min(max(Int(ideal.rounded()), 1), n - 1)

        // Search outward from the seed so the returned plan is the fitting one
        // nearest the balanced point, not merely the first that fits.
        var bestK = seed
        var bestOverflow = Double.greatestFiniteMagnitude
        for delta in 0..<n {
            for k in [seed - delta, seed + delta] where k >= 1 && k < n {
                let plan = evaluate(shape: shape, k: k, master: master, worker: worker)
                let overflow = max(0, -plan.masterHeadroomGB) + max(0, -plan.workerHeadroomGB)
                if overflow == 0 { return .fits(plan) }
                if overflow < bestOverflow { bestOverflow = overflow; bestK = k }
            }
        }

        let best = evaluate(shape: shape, k: bestK, master: master, worker: worker)
        return .doesNotFit(
            reason: String(
                format: "This model needs %.1f GB. The best split (%d/%d layers) still asks "
                      + "%.1f GB of a %.1f GB budget on one Mac and %.1f GB of %.1f GB on the other — "
                      + "%.1f GB short overall.",
                shape.totalGB, bestK, shape.numLayers - bestK,
                best.masterNeedGB, master.usableGB,
                best.workerNeedGB, worker.usableGB, bestOverflow),
            bestK: bestK, bestOverflowGB: bestOverflow)
    }

    /// Validates a user-chosen `k`, so a manual override cannot quietly create a
    /// plan that swaps.
    static func manual(shape: ModelShape, k: Int, master: Budget, worker: Budget) -> Outcome {
        guard shape.numLayers >= 2 else {
            return .modelTooSmall(reason: "A \(shape.numLayers)-layer model cannot be split.")
        }
        guard k >= 1, k < shape.numLayers else {
            return .doesNotFit(
                reason: "Split point must be between 1 and \(shape.numLayers - 1).",
                bestK: min(max(k, 1), shape.numLayers - 1), bestOverflowGB: 0)
        }
        let plan = evaluate(shape: shape, k: k, master: master, worker: worker)
        let overflow = max(0, -plan.masterHeadroomGB) + max(0, -plan.workerHeadroomGB)
        if overflow == 0 { return .fits(plan) }
        return .doesNotFit(
            reason: String(format: "A %d/%d split needs %.1f GB on the Master (budget %.1f GB) "
                                 + "and %.1f GB on the Worker (budget %.1f GB).",
                           k, shape.numLayers - k, plan.masterNeedGB, master.usableGB,
                           plan.workerNeedGB, worker.usableGB),
            bestK: k, bestOverflowGB: overflow)
    }

    static func evaluate(shape: ModelShape, k: Int, master: Budget, worker: Budget) -> Plan {
        let masterNeed = shape.embedGB + shape.sharedGB + shape.layersGB(0..<k)
        let workerNeed = shape.lmHeadGB + shape.sharedGB + shape.layersGB(k..<shape.numLayers)
        return Plan(k: k,
                    masterNeedGB: masterNeed,
                    workerNeedGB: workerNeed,
                    masterHeadroomGB: master.usableGB - masterNeed,
                    workerHeadroomGB: worker.usableGB - workerNeed)
    }

    // MARK: - Gate

    /// Whether splitting this model is worth doing at all.
    ///
    /// A model that fits on one machine must **not** be split: pipeline mode is
    /// CPU-only (the GPU segment path is not built, and `gpu_enabled()` refuses
    /// hybrids anyway), so splitting a model that would otherwise run on Metal
    /// trades a large speedup for a network hop. Someone who did that would see
    /// a 10× slowdown and reasonably conclude distributed mode is broken.
    static func shouldOfferSplit(modelGB: Double, localBudget: Budget) -> Bool {
        modelGB > localBudget.usableGB
    }
}
