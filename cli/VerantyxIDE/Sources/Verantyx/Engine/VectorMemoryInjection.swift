import Foundation

/// Memory reaching the model as vectors rather than as prompt text.
///
/// Retrieval is unchanged and stays unchanged: `EternalMemoryStore` already
/// embeds through JGEN's own `encode` and ranks by cosine similarity. The only
/// thing that differs here is the last step — instead of pasting the recalled
/// *text* into the prompt, the recalled *vector* is blended into a mid-layer
/// residual.
///
/// What that trades, stated plainly because it is not a free win:
///
///  - **Gained**: the memory costs no prompt tokens. A 480-character recall
///    block is roughly 120 tokens of context; the same memory as a vector costs
///    none, because a mid-layer blend consumes no positions.
///  - **Lost**: the model no longer receives the memory's *words*. The stored
///    vector is a PromptEOL summary ("means in one word"), a direction in
///    representation space, not a reconstruction. Anything that has to be exact
///    — a date, a file name, a number — is not carried by it.
///
/// So this is not a lossless compression of text injection. It is a different,
/// lossier operation that happens to be much cheaper, and whether it is worth
/// it is an empirical question per use — which is what `MemoryABHarness`
/// exists to answer.
enum VectorMemoryInjection {

    enum Mode: String, CaseIterable, Codable {
        /// Current behaviour: recalled text prepended to the prompt.
        case text
        /// Recalled vectors blended into a mid-layer residual.
        case vector
        /// No memory at all.
        ///
        /// Not a user-facing setting — a control. Without it, `text` and
        /// `vector` both scoring well is indistinguishable from a question that
        /// never needed memory in the first place, and the whole comparison
        /// says nothing.
        case none

        var label: String {
            switch self {
            case .text:   return "text injection"
            case .vector: return "vector injection"
            case .none:   return "no memory (control)"
            }
        }
    }

    /// Where the blend lands and how hard.
    ///
    /// The defaults come from a measured sweep rather than taste: on
    /// qwen2.5-0.5b, alpha up to about 0.4 leaves generation coherent and 0.5
    /// upward degrades it, so 0.25 sits inside the band with room to spare.
    /// A third of the way up the stack is where `jgen_reflect` already operates
    /// usefully — early enough that later layers can act on the nudge, late
    /// enough that the representation is not still mostly lexical.
    struct Settings: Codable, Equatable {
        /// Measured, and deliberately inside the band rather than at its edge.
        ///
        /// Swept across three prompts at a third of the way up a 24-layer model,
        /// a single injection is coherent from 0.05 to 0.2 and degrades beyond.
        /// 0.15 sits inside that with margin; the per-hit similarity score
        /// scales it down further still.
        ///
        /// An earlier value of 0.2 came from a single-prompt sweep that read
        /// coherent to 0.3. Repeating it across three prompts moved the edge
        /// down — one prompt at one strength is one sample, and the band was
        /// narrower than a single sample suggested.
        var alpha: Float = 0.15
        /// `nil` = one third of the model's depth.
        var layer: Int? = nil
        /// One, because stacking was swept and came back **unresolved**.
        ///
        /// The sweep asked which quantity governs the limit: total alpha across
        /// injections (so the rule would be a budget, alpha = budget / count) or
        /// per-layer alpha (so stacking is free). The answer at this measurement
        /// scale is neither — the safe band did not vary monotonically with
        /// count, and at three injections there was no contiguous healthy band
        /// at all (0.05 failed while 0.1 passed).
        ///
        /// A first pass did produce a tidy-looking law, "budget 0.56 total", by
        /// comparing the spread of two noisy quantities and calling the less
        /// noisy one conserved. It was not a finding; two noisy numbers always
        /// have one smaller than the other.
        ///
        /// So this stays at one until the measurement can answer the question.
        /// The limiting factor is the health heuristic — sixteen greedy tokens
        /// either loop or do not, which is too blunt to resolve a band edge.
        var maxMemories: Int = 1
        /// Blend across every prompt position rather than only the last.
        ///
        /// Not a preference. Last-position-only is `execute_inject_at_layer`'s
        /// convention and was measured to be completely inert for generation —
        /// even at alpha 1.0 the output came back byte-identical. That
        /// convention was written for *observation*, where nudging one row
        /// enough to read it back is the whole requirement.
        var blendAllPositions: Bool = true
        var injectEachStep: Bool = false

        func resolvedLayer(numLayers: Int) -> Int {
            if let layer { return min(max(layer, 0), max(numLayers - 1, 0)) }
            return max(numLayers / 3, 1)
        }
    }

    /// Turns recalled memories into layer injections.
    ///
    /// Several memories go to *neighbouring* layers rather than all to one:
    /// stacking blends at a single layer compounds the mix ratio, and the sweep
    /// showed the residual stops tolerating that well above ~0.4 total. Spread
    /// out, each stays inside its own band.
    static func injections(
        for memories: [(text: String, score: Float)],
        settings: Settings,
        numLayers: Int,
        embed: (String) async throws -> [Float]
    ) async rethrows -> [(layer: Int, vector: [Float], alpha: Float)] {
        let base = settings.resolvedLayer(numLayers: numLayers)
        var out: [(layer: Int, vector: [Float], alpha: Float)] = []
        for (i, m) in memories.prefix(settings.maxMemories).enumerated() {
            out.append((
                layer: min(base + i, numLayers - 1),
                vector: try await embed(m.text),
                // Weaker for lower-ranked hits: a weak match nudging as hard as
                // a strong one is how retrieval noise becomes generation noise.
                alpha: settings.alpha * max(m.score, 0.2)))
        }
        return out
    }
}
