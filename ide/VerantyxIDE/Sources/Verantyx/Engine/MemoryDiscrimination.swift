import Foundation

/// Does a memory delivered as a *vector* shift what the model expects next?
///
/// This replaces the scoring in `MemoryABHarness`, which asked a question the
/// mechanism cannot answer. Its probes require reproducing an invented string
/// exactly — "Kestrel-9", "8790", "tilde-vault" — and `VectorMemoryInjection`'s
/// own documentation says a stored vector is a PromptEOL summary, "a direction
/// in representation space, not a reconstruction", carrying nothing exact. The
/// vector arm was going to score zero regardless of model or strength, so the
/// comparison was decided before it ran. A bigger model does not fix that.
///
/// The second problem was resolution. A string-match verdict is a coarsening of
/// "did the argmax token change", and a measurement on this engine showed the
/// argmax is the last thing to move: blending a memory vector at a third of the
/// way up a 24-layer model shifts 45% of the distribution's mass at alpha 1.0
/// while the top token never changes once. A binary verdict would have called
/// every one of those runs inert. The signal was under the instrument.
///
/// So this measures a margin instead of a match:
///
///     Δ = log p(correct) − log p(distractor)
///
/// on a question whose sense the memory disambiguates. Δ is continuous, so a
/// real but modest steer is visible long before it changes any answer.
///
/// **The arms, and why each exists.**
///
///  - `none`        control. Without it, an arm scoring well is
///                  indistinguishable from a question that never needed memory.
///  - `text`        today's behaviour: the memory pasted into the prompt.
///  - `vector`      the memory blended into a mid-layer residual.
///  - `soft`        the memory prepended as a soft token. The second route,
///                  and the reason `jcross_engine_inject_multi_layer` had to
///                  start forwarding its `soft` argument: routing this arm
///                  through `encodeSoft` instead would have made the code path
///                  a difference between the routes being compared.
///  - `wrongVector` **the arm that decides whether any of this means anything.**
///                  An unrelated memory, injected identically. If Δ rises here
///                  too, the measurement is picking up a generic consequence of
///                  perturbing the residual, not recall. `vector` beating
///                  `none` proves nothing on its own; `vector` beating
///                  `wrongVector` is the claim worth making. This is the same
///                  role the alpha=0 control played when a stale KV cache made
///                  every run look like it was working.
///
/// Every arm goes through one function, `injectMultiLayer`, with everything but
/// the injection held fixed.
actor MemoryDiscrimination {

    static let shared = MemoryDiscrimination()
    private init() {}

    struct Probe {
        /// The fact that resolves the ambiguity.
        let memory: String
        /// An unrelated fact of similar length and shape, for `wrongVector`.
        /// Similar shape on purpose: a decoy that is obviously different in
        /// size or register would change the residual by a different amount and
        /// stop being a control for anything.
        let decoy: String
        /// Ends where the next token discriminates.
        let question: String
        /// The continuation the memory should favour.
        let correct: String
        /// The continuation it should favour less.
        let distractor: String
    }

    /// Ambiguous terms whose everyday sense competes with a project-specific
    /// one. A direction in representation space can plausibly carry "this is
    /// the software sense" — that is the kind of thing it is for. None of them
    /// asks for a rare literal string, which is the kind of thing it is not.
    static let defaultProbes: [Probe] = [
        Probe(memory: "In this codebase, 'bridge' means the Thunderbolt network link joining the two Macs.",
              decoy:  "In this codebase, 'harvest' means the nightly job that compacts old log files.",
              question: "Q: Is 'bridge' here about networking or about card games?\nA: It is about",
              correct: " networking", distractor: " card"),
        Probe(memory: "In this codebase, 'forge' means the tool that converts model weights into the JGEN format.",
              decoy:  "In this codebase, 'lantern' means the banner shown while a long task is running.",
              question: "Q: Is 'forge' here about software or about metalworking?\nA: It is about",
              correct: " software", distractor: " metal"),
        Probe(memory: "In this codebase, 'anchor' means an image pinned into the prompt every turn.",
              decoy:  "In this codebase, 'ledger' means the append-only record of approved facts.",
              question: "Q: Is 'anchor' here about images or about ships?\nA: It is about",
              correct: " images", distractor: " ships"),
        Probe(memory: "In this codebase, 'council' means a set of model roles that vote on an answer.",
              decoy:  "In this codebase, 'quarry' means the folder scanned for new source files.",
              question: "Q: Is 'council' here about models or about local government?\nA: It is about",
              correct: " models", distractor: " government"),
    ]

    enum Arm: String, CaseIterable, Codable {
        case none, text, vector, matched, soft, wrongVector, wrongMatched

        var label: String {
            switch self {
            case .none:         return "no memory (control)"
            case .text:         return "text in the prompt"
            case .vector:       return "blend, final-layer vector"
            case .matched:      return "blend, same-layer vector"
            case .soft:         return "soft prefix"
            case .wrongVector:  return "unrelated, final-layer (control)"
            case .wrongMatched: return "unrelated, same-layer (control)"
            }
        }
    }

    struct Measurement: Codable {
        var arm: String
        var probe: String
        /// log p(correct) − log p(distractor).
        var delta: Float
        var pCorrect: Float
        var pDistractor: Float
        /// How far this arm's whole distribution moved from the control's.
        /// Reported alongside Δ because an arm with L1 ≈ 0 did nothing at all,
        /// and a Δ that barely moved for that reason should not be read as
        /// "the memory did not help".
        var l1FromNone: Float
        /// Whether the candidates were visible in the top-K at all. A Δ built
        /// on two floored probabilities is not a measurement, and silently
        /// averaging it in is how a table of plausible numbers gets built out
        /// of nothing.
        var candidatesFound: Bool
    }

    struct Report: Codable {
        var model: String
        var layer: Int
        var alpha: Float
        var topK: Int
        var measurements: [Measurement]
        var lines: [String]
    }

    /// Floor for an unseen candidate. Chosen well below anything top-K would
    /// return so the flooring is visible as an outlier rather than blending in.
    private static let floorP: Float = 1e-9

    /// Sweeps strengths and depths within one load.
    ///
    /// Written this way because the model load dominates everything else: on
    /// the 0.8B it is minutes, and on the 9B this is meant for it is far worse.
    /// Running the process once per (alpha, layer) spent most of the wall clock
    /// re-reading weights that had not changed. The control arms are re-run per
    /// setting rather than hoisted, since a control shared across settings
    /// stops being a control for any of them.
    func sweep(
        probes: [Probe] = MemoryDiscrimination.defaultProbes,
        alphas: [Float],
        layers: [Int?],
        topK: Int = 4096
    ) async throws -> [Report] {
        var reports: [Report] = []
        for layer in layers {
            for alpha in alphas {
                reports.append(try await run(probes: probes, layer: layer,
                                             alpha: alpha, topK: topK))
            }
        }
        return reports
    }

    /// One line per setting, so a sweep reads as a curve instead of a stack of
    /// separate verdicts. `blend−wrong` is the column that matters: it is the
    /// only one that isolates content from the act of perturbing the residual.
    ///
    /// The `usable` column is not decoration. A first version of this table
    /// omitted it and printed rows reading `blend Δ −1.833` at high alpha,
    /// which looked like a large negative effect and was nothing of the kind:
    /// the injection had destroyed the distribution, both candidates had fallen
    /// out of the top-K, the mean over an empty set came back 0, and the column
    /// was showing `0 − controlΔ`. Rows with no usable probes are not
    /// measurements, and a table that cannot say so invites reading noise as
    /// signal — the same failure as the binary verdict this harness replaced,
    /// one level up.
    static func sweepTable(_ reports: [Report]) -> [String] {
        var lines = [String(format: "%-6@ %-6@ %9@ %9@ %11@ %10@ %9@ %8@",
                            "layer" as NSString, "alpha" as NSString,
                            "blend Δ" as NSString, "wrong Δ" as NSString,
                            "blend−wrong" as NSString, "blend L1" as NSString,
                            "soft Δ" as NSString, "usable" as NSString)]
        for r in reports {
            func usable(_ arm: Arm) -> [Measurement] {
                r.measurements.filter { $0.arm == arm.rawValue && $0.candidatesFound }
            }
            func meanDelta(_ arm: Arm) -> Float? {
                let m = usable(arm)
                return m.isEmpty ? nil : m.map(\.delta).reduce(0, +) / Float(m.count)
            }
            func meanL1(_ arm: Arm) -> Float {
                let m = r.measurements.filter { $0.arm == arm.rawValue }
                return m.isEmpty ? 0 : m.map(\.l1FromNone).reduce(0, +) / Float(m.count)
            }
            let total = r.measurements.filter { $0.arm == Arm.vector.rawValue }.count
            let nUsable = usable(.vector).count
            guard let none = meanDelta(.none), let blend = meanDelta(.vector),
                  let wrong = meanDelta(.wrongVector) else {
                lines.append(String(format: "%-6d %-6.2f %9@ %9@ %11@ %10.4f %9@ %4d/%d",
                                    r.layer, r.alpha, "—" as NSString, "—" as NSString,
                                    "not measured" as NSString, meanL1(.vector),
                                    "—" as NSString, nUsable, total))
                continue
            }
            let soft = meanDelta(.soft).map { $0 - none }
            lines.append(String(format: "%-6d %-6.2f %+9.3f %+9.3f %+11.3f %10.4f %+9.3f %4d/%d",
                                r.layer, r.alpha, blend - none, wrong - none,
                                blend - wrong, meanL1(.vector), soft ?? 0, nUsable, total))
        }
        return lines
    }

    /// The same table for the space-matched pair, kept separate because it is a
    /// different question with a different control.
    static func matchedTable(_ reports: [Report]) -> [String] {
        var lines = [String(format: "%-6@ %-6@ %11@ %11@ %13@ %10@ %8@",
                            "layer" as NSString, "alpha" as NSString,
                            "matched Δ" as NSString, "its decoy Δ" as NSString,
                            "matched−decoy" as NSString, "matched L1" as NSString,
                            "usable" as NSString)]
        for r in reports {
            func usable(_ arm: Arm) -> [Measurement] {
                r.measurements.filter { $0.arm == arm.rawValue && $0.candidatesFound }
            }
            func meanDelta(_ arm: Arm) -> Float? {
                let m = usable(arm)
                return m.isEmpty ? nil : m.map(\.delta).reduce(0, +) / Float(m.count)
            }
            func meanL1(_ arm: Arm) -> Float {
                let m = r.measurements.filter { $0.arm == arm.rawValue }
                return m.isEmpty ? 0 : m.map(\.l1FromNone).reduce(0, +) / Float(m.count)
            }
            let total = r.measurements.filter { $0.arm == Arm.matched.rawValue }.count
            let nUsable = usable(.matched).count
            guard let none = meanDelta(.none), let m = meanDelta(.matched),
                  let w = meanDelta(.wrongMatched) else {
                lines.append(String(format: "%-6d %-6.2f %11@ %11@ %13@ %10.4f %4d/%d",
                                    r.layer, r.alpha, "—" as NSString, "—" as NSString,
                                    "not measured" as NSString, meanL1(.matched), nUsable, total))
                continue
            }
            lines.append(String(format: "%-6d %-6.2f %+11.3f %+11.3f %+13.3f %10.4f %4d/%d",
                                r.layer, r.alpha, m - none, w - none, m - w,
                                meanL1(.matched), nUsable, total))
        }
        return lines
    }

    func run(
        probes: [Probe] = MemoryDiscrimination.defaultProbes,
        layer: Int? = nil,
        alpha: Float = 0.2,
        topK: Int = 4096
    ) async throws -> Report {
        let chat = JCrossChatManager.shared
        let model = await chat.loadedModelName ?? "(none)"
        let n = await chat.loadedLayerCount
        guard n > 0 else {
            throw NSError(domain: "MemoryDiscrimination", code: 1,
                          userInfo: [NSLocalizedDescriptionKey: "No JGEN model loaded."])
        }
        let injectLayer = layer ?? max(n / 3, 1)

        var measurements: [Measurement] = []
        var lines: [String] = []
        lines.append("model \(model): \(n) layers, injecting at \(injectLayer), alpha \(alpha), top-\(topK)")
        lines.append("")

        // Control before any arm: the same call twice must give the same
        // distribution. If the engine is not deterministic here, no difference
        // measured below can be attributed to an injection.
        if let first = probes.first {
            let q = try await chat.tokenize(first.question)
            let a = try await distribution(tokens: q, soft: [], injections: [], topK: topK)
            let b = try await distribution(tokens: q, soft: [], injections: [], topK: topK)
            let repeatability = Self.l1(a, b)
            lines.append(String(format: "determinism control: repeat of the same call differs by L1 %.6f%@",
                                repeatability,
                                repeatability == 0 ? " — OK" : " — NOT DETERMINISTIC, everything below is suspect"))
            lines.append("")
        }

        for probe in probes {
            let qTokens = try await chat.tokenize(probe.question)
            let correctTok = try await firstToken(of: probe.correct)
            let distractTok = try await firstToken(of: probe.distractor)

            // Two vectors per memory, from two different depths, because the
            // shipping code mixes them up. `encodeText` returns the state after
            // the *final* norm — the end of the stack — and `VectorMemory
            // Injection` blends it into a residual a third of the way up.
            // Those are not the same space. Norm matching rescales the
            // magnitude but says nothing about whether the direction means the
            // same thing at layer 8 as it does at layer 24, and there is no
            // reason it should. The `matched` arm takes the memory's residual
            // at the very layer it will be injected into, which is the version
            // of the idea that at least has a coherent space to live in.
            let memVec = try await chat.encodeText(probe.memory)
            let decoyVec = try await chat.encodeText(probe.decoy)
            let memAtLayer = try await chat.encodeTextAtLayer(probe.memory, layer: injectLayer)
            let decoyAtLayer = try await chat.encodeTextAtLayer(probe.decoy, layer: injectLayer)

            var noneDist: [JCrossChatManager.TopKText] = []

            for arm in Arm.allCases {
                var tokens = qTokens
                var soft: [[Float]] = []
                var injections: [(layer: Int, vector: [Float], alpha: Float)] = []

                switch arm {
                case .none:
                    break
                case .text:
                    tokens = try await chat.tokenize(probe.memory + "\n" + probe.question)
                case .vector:
                    injections = [(layer: injectLayer, vector: memVec, alpha: alpha)]
                case .matched:
                    injections = [(layer: injectLayer, vector: memAtLayer, alpha: alpha)]
                case .soft:
                    soft = [memVec]
                case .wrongVector:
                    injections = [(layer: injectLayer, vector: decoyVec, alpha: alpha)]
                case .wrongMatched:
                    injections = [(layer: injectLayer, vector: decoyAtLayer, alpha: alpha)]
                }

                let dist = try await distribution(tokens: tokens, soft: soft,
                                                  injections: injections, topK: topK)
                if arm == .none { noneDist = dist }

                let pc = Self.prob(dist, correctTok)
                let pd = Self.prob(dist, distractTok)
                let found = pc > 0 && pd > 0
                let delta = log(max(pc, Self.floorP)) - log(max(pd, Self.floorP))

                measurements.append(Measurement(
                    arm: arm.rawValue, probe: probe.question,
                    delta: delta, pCorrect: pc, pDistractor: pd,
                    l1FromNone: Self.l1(dist, noneDist),
                    candidatesFound: found))
            }
        }

        lines.append(contentsOf: Self.summarise(measurements: measurements, probes: probes))
        return Report(model: model, layer: injectLayer, alpha: alpha,
                      topK: topK, measurements: measurements, lines: lines)
    }

    /// One forward pass, one distribution. Observing `numLayers` returns the
    /// post-final-norm residual, which is what `lm_head` expects; observing a
    /// layer index would return an unnormalised state and give logits that mean
    /// nothing.
    private func distribution(
        tokens: [UInt32], soft: [[Float]],
        injections: [(layer: Int, vector: [Float], alpha: Float)],
        topK: Int
    ) async throws -> [JCrossChatManager.TopKText] {
        let chat = JCrossChatManager.shared
        let n = await chat.loadedLayerCount
        await chat.resetEngine()
        let hidden = try await chat.injectMultiLayerRaw(
            tokens: tokens, soft: soft, injections: injections, observeLayers: [n])
        guard let h = hidden[n] else {
            throw NSError(domain: "MemoryDiscrimination", code: 2,
                          userInfo: [NSLocalizedDescriptionKey: "No observation at the final norm."])
        }
        return try await chat.topKDistributionText(vector: h, k: topK)
    }

    private func firstToken(of text: String) async throws -> UInt32 {
        let ids = try await JCrossChatManager.shared.tokenize(text)
        guard let first = ids.first else {
            throw NSError(domain: "MemoryDiscrimination", code: 3,
                          userInfo: [NSLocalizedDescriptionKey: "Candidate '\(text)' tokenized to nothing."])
        }
        return first
    }

    private static func prob(_ d: [JCrossChatManager.TopKText], _ token: UInt32) -> Float {
        d.first { $0.tokenId == token }?.prob ?? 0
    }

    /// Half the summed absolute difference over the tokens either distribution
    /// ranked highly. Understates the true total variation, since only the
    /// top-K is visible — which is fine, because what it is asked is whether
    /// the number is zero.
    private static func l1(_ a: [JCrossChatManager.TopKText], _ b: [JCrossChatManager.TopKText]) -> Float {
        guard !b.isEmpty else { return 0 }
        var ma: [UInt32: Float] = [:]
        for e in a { ma[e.tokenId] = e.prob }
        var mb: [UInt32: Float] = [:]
        for e in b { mb[e.tokenId] = e.prob }
        var sum: Float = 0
        for (t, p) in ma { sum += abs(p - (mb[t] ?? 0)) }
        for (t, p) in mb where ma[t] == nil { sum += abs(p) }
        return sum / 2
    }

    private static func summarise(measurements: [Measurement], probes: [Probe]) -> [String] {
        var lines: [String] = []
        lines.append(String(format: "%-22@ %8@ %10@ %10@ %8@",
                            "arm" as NSString, "mean Δ" as NSString, "mean L1" as NSString,
                            "vs none" as NSString, "usable" as NSString))

        func mean(_ v: [Float]) -> Float { v.isEmpty ? 0 : v.reduce(0, +) / Float(v.count) }

        var byArm: [String: Float] = [:]
        for arm in Arm.allCases {
            let mine = measurements.filter { $0.arm == arm.rawValue }
            guard !mine.isEmpty else { continue }
            let usable = mine.filter(\.candidatesFound)
            // Only probes where both candidates were actually visible. A Δ
            // computed from two floors is an artefact of the floor, not of the
            // model, and averaging it in would manufacture a number.
            let d = mean(usable.map(\.delta))
            byArm[arm.rawValue] = d
            let base = byArm[Arm.none.rawValue] ?? 0
            lines.append(String(format: "%-22@ %8.3f %10.4f %+10.3f %5d/%d",
                                arm.label as NSString, d, mean(mine.map(\.l1FromNone)),
                                d - base, usable.count, mine.count))
        }

        lines.append("")
        let none = byArm[Arm.none.rawValue] ?? 0
        let vec = byArm[Arm.vector.rawValue] ?? 0
        let wrong = byArm[Arm.wrongVector.rawValue] ?? 0
        let matched = byArm[Arm.matched.rawValue] ?? 0
        let wrongMatched = byArm[Arm.wrongMatched.rawValue] ?? 0
        let soft = byArm[Arm.soft.rawValue] ?? 0
        let text = byArm[Arm.text.rawValue] ?? 0

        // Stated as conditions rather than read off the table by eye, and in
        // the order that can actually invalidate the result.
        if measurements.filter(\.candidatesFound).isEmpty {
            lines.append("INVALID: no probe had both candidates inside the top-K. "
                       + "Every Δ above came from the floor. Raise K or pick commoner candidates.")
            return lines
        }
        let vecMoved = mean(measurements.filter { $0.arm == Arm.vector.rawValue }.map(\.l1FromNone))
        if vecMoved == 0 {
            lines.append("INVALID: the vector arm's distribution is identical to the control's. "
                       + "The injection did nothing, so its Δ is the control's Δ by construction.")
            return lines
        }
        if vec - none <= 0 {
            lines.append(String(format: "Vector injection did NOT help: Δ moved %+.3f against the control.", vec - none))
        } else if vec - wrong <= 0 {
            lines.append(String(format:
                "INCONCLUSIVE: the vector arm beat the control by %+.3f, but an unrelated memory "
                + "beat it by %+.3f. Whatever moved Δ is not recall — it is what perturbing the "
                + "residual does regardless of content.", vec - none, wrong - none))
        } else {
            lines.append(String(format:
                "Vector injection helped: %+.3f against the control, and %+.3f against an "
                + "unrelated memory injected the same way.", vec - none, vec - wrong))
        }
        lines.append(String(format: "Routes: mid-layer blend %+.3f, soft prefix %+.3f (text, for scale, %+.3f).",
                            vec - none, soft - none, text - none))

        // Reported separately because it is a different claim: not "does
        // injection work" but "was the vector being injected from the wrong
        // place". Each version is judged against its own decoy, since the two
        // perturb the residual by different amounts and their controls are not
        // interchangeable.
        lines.append(String(format:
            "Space: final-layer vector %+.3f over its decoy, same-layer vector %+.3f over its decoy.",
            vec - wrong, matched - wrongMatched))
        if matched - wrongMatched > 0 && vec - wrong <= 0 {
            lines.append("  The same-layer vector separates from its decoy where the final-layer one "
                       + "does not. The vector was being taken from the end of the stack and blended "
                       + "into the middle, which are different spaces.")
        }
        return lines
    }
}
