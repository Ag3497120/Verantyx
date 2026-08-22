import Foundation

/// Does vector-injected memory actually work, and is it worth what it costs?
///
/// The design of this is a direct response to being wrong twice today. Both
/// times the mechanism *looked* like it was working: once because a stale KV
/// cache made every run differ from the baseline, once because a test asserted
/// something that was never true. In both cases the thing that caught it was a
/// control, not inspection.
///
/// So the controls come first:
///
///  - **`.none` is mandatory.** If text and vector both answer correctly, that
///    is only meaningful if answering *without* memory fails. A question the
///    model can answer from its weights measures nothing about memory. Any
///    question where `.none` succeeds is discarded from the score, not counted
///    as a win for both.
///  - **The engine is reset before every single run.** `execute_generation_loop`
///    does not clear the KV cache — the caller's job — and forgetting it is
///    exactly how the earlier run produced convincing nonsense.
///  - **Cost is recorded alongside correctness.** Vector injection that answers
///    as well as text while costing no prompt tokens is the win; answering
///    slightly worse for a large saving is a real trade-off; answering worse
///    for no saving is a straightforward loss. One number cannot express that.
///
/// The facts are seeded here rather than assumed present, so the store's prior
/// contents cannot make a question answerable by accident.
actor MemoryABHarness {

    static let shared = MemoryABHarness()
    private init() {}

    struct Probe {
        /// Seeded into memory before the run.
        let fact: String
        /// Asked afterwards. Must be unanswerable without the fact.
        let question: String
        /// Case-insensitive substring that marks a correct answer.
        let expect: String
    }

    /// Deliberately invented, specific, and unguessable: a model that answers
    /// these without the memory is not recalling, and a probe whose answer is
    /// derivable from the question is not testing recall.
    static let defaultProbes: [Probe] = [
        Probe(fact: "The Verantyx build codename for the 2026-08 release is Kestrel-9.",
              question: "What is the Verantyx build codename for the 2026-08 release?",
              expect: "kestrel"),
        Probe(fact: "The pipeline control port used between the two Macs is 8790.",
              question: "Which port do the two Macs use for the pipeline channel?",
              expect: "8790"),
        Probe(fact: "The tokenizer for ornith-1.0-9b was recovered from the folder named tilde-vault.",
              question: "Which folder was the ornith-1.0-9b tokenizer recovered from?",
              expect: "tilde-vault"),
    ]

    struct Outcome: Codable {
        var mode: String
        var question: String
        var answer: String
        var correct: Bool
        var promptChars: Int
        var generatedTokens: Int
        var seconds: Double
    }

    struct Report: Codable {
        var model: String
        var settings: VectorMemoryInjection.Settings
        var outcomes: [Outcome]
        /// Probes where the control also succeeded, and which therefore say
        /// nothing about memory.
        var discardedProbes: [String]
        var summary: String
    }

    func run(
        probes: [Probe] = MemoryABHarness.defaultProbes,
        settings: VectorMemoryInjection.Settings = .init(),
        maxTokens: Int = 48
    ) async throws -> Report {
        let chat = JCrossChatManager.shared
        let modelName = await chat.loadedModelName ?? "(none)"
        let numLayers = await chat.loadedLayerCount
        guard numLayers > 0 else {
            throw NSError(domain: "MemoryAB", code: 1,
                          userInfo: [NSLocalizedDescriptionKey: "No JGEN model loaded."])
        }

        for p in probes {
            try? await EternalMemoryStore.shared.add(text: p.fact, concepts: [])
        }

        var outcomes: [Outcome] = []
        var discarded: [String] = []

        for probe in probes {
            var perMode: [VectorMemoryInjection.Mode: Outcome] = [:]
            for mode in VectorMemoryInjection.Mode.allCases {
                let o = try await ask(probe: probe, mode: mode,
                                      settings: settings, numLayers: numLayers,
                                      maxTokens: maxTokens)
                perMode[mode] = o
                outcomes.append(o)
            }
            // A probe the control answers is not a memory probe.
            if perMode[VectorMemoryInjection.Mode.none]?.correct == true {
                discarded.append(probe.question)
            }
        }

        return Report(model: modelName, settings: settings, outcomes: outcomes,
                      discardedProbes: discarded,
                      summary: Self.summarise(outcomes: outcomes, discarded: discarded))
    }

    private func ask(
        probe: Probe, mode: VectorMemoryInjection.Mode,
        settings: VectorMemoryInjection.Settings, numLayers: Int, maxTokens: Int
    ) async throws -> Outcome {
        let chat = JCrossChatManager.shared
        let started = Date()

        var promptText = probe.question
        var injections: [(layer: Int, vector: [Float], alpha: Float)] = []

        switch mode {
        case .text:
            let block = await EternalMemoryStore.shared.recallBlock(for: probe.question, k: settings.maxMemories)
            promptText = block + "\n" + probe.question
        case .vector:
            let hits = (try? await EternalMemoryStore.shared.search(
                query: probe.question, k: settings.maxMemories)) ?? []
            injections = try await VectorMemoryInjection.injections(
                for: hits, settings: settings, numLayers: numLayers,
                embed: { try await chat.encodeText($0) })
        case .none:
            break
        }

        let tokens = try await chat.promptTokens(conversation: [(role: "user", content: promptText)])
        // Reset before every run. Not defensive — omitting this is precisely
        // what produced a convincing but meaningless result earlier today.
        await chat.resetEngine()
        let out = try await chat.generateInjectedRaw(
            promptTokens: tokens, layerInjections: injections,
            injectEachStep: settings.injectEachStep,
            blendAllPositions: settings.blendAllPositions, maxTokens: maxTokens)
        let answer = (try? await chat.decode(tokens: out)) ?? ""

        return Outcome(
            mode: mode.rawValue,
            question: probe.question,
            answer: answer.trimmingCharacters(in: .whitespacesAndNewlines),
            correct: answer.lowercased().contains(probe.expect.lowercased()),
            promptChars: promptText.count,
            generatedTokens: out.count,
            seconds: Date().timeIntervalSince(started))
    }

    private static func summarise(outcomes: [Outcome], discarded: [String]) -> String {
        var lines: [String] = []
        for mode in VectorMemoryInjection.Mode.allCases {
            let mine = outcomes.filter { $0.mode == mode.rawValue && !discarded.contains($0.question) }
            guard !mine.isEmpty else { continue }
            let right = mine.filter(\.correct).count
            let avgChars = mine.map(\.promptChars).reduce(0, +) / mine.count
            lines.append(String(
                format: "%-22@ %d/%d correct · avg prompt %d chars",
                mode.label as NSString, right, mine.count, avgChars))
        }
        if !discarded.isEmpty {
            lines.append("discarded \(discarded.count) probe(s): the control answered them, "
                       + "so they never required memory")
        }
        if outcomes.filter({ $0.mode == VectorMemoryInjection.Mode.none.rawValue && !$0.correct }).isEmpty {
            lines.append("WARNING: the control answered everything — this run measures nothing "
                       + "about memory. Write harder probes.")
        }
        return lines.joined(separator: "\n")
    }
}
