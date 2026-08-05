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
        /// Measured, not chosen by feel. Sweeping a real encode vector at a
        /// third of the way up a 24-layer model: coherent to alpha 0.3, thinning
        /// at 0.4, one repeated token by 1.0. Identical band on CPU and GPU.
        /// 0.2 sits inside it with room, since the per-hit score scales it down
        /// further anyway.
        var alpha: Float = 0.2
        /// `nil` = one third of the model's depth.
        var layer: Int? = nil
        /// One by default because one is what was measured.
        ///
        /// Stacking blends is not a smaller version of the same thing — an
        /// earlier build applied the same alpha nine times without meaning to,
        /// and its apparent "usable band" was an artefact of that. Until
        /// stacking is swept the same way, more than one memory is an untested
        /// region, not a bigger dose.
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
