import Foundation

/// Runs one generation across two machines.
///
/// The master holds layers `[0, k)` and the embedding table; the worker holds
/// `[k, N)`, the final norm and `lm_head`. Per token the master turns one id
/// into a residual, ships it, and gets back the sampled token — four bytes.
///
/// The division of labour is not arbitrary. The worker samples because the
/// engine's sampling is pure greedy argmax (no temperature, no top-p, no RNG
/// anywhere in it), so there is no sampler state to keep in sync. The master
/// keeps the *stop policy* — EOS, repeat guard, max tokens, cancellation —
/// because it owns the tokenizer and the streaming callback, and because
/// deciding when to stop from a stream of bare ids is exactly what the worker
/// cannot do.
actor PipelineRunner {

    static let shared = PipelineRunner()

    private init() {}

    struct Result {
        var tokens: [UInt32]
        /// Wall-clock, for the connection screen's throughput line.
        var elapsed: TimeInterval
        var stoppedBecause: String
    }

    enum RunError: LocalizedError {
        case notPaired
        case noSplit
        case workerLost(String)
        case modelNotLoaded

        var errorDescription: String? {
            switch self {
            case .notPaired:       return "Not connected to another Mac."
            case .noSplit:         return "No layer split has been agreed yet."
            case .modelNotLoaded:  return "No model loaded on this Mac."
            case .workerLost(let m):
                return "\(m) This reply is incomplete."
            }
        }
    }

    /// Generates from pre-tokenized ids.
    ///
    /// `onToken` fires per accepted token so the UI streams exactly as it does
    /// for a local run.
    func generate(
        promptTokens: [UInt32],
        splitK k: Int,
        numLayers n: Int,
        maxTokens: Int,
        eosTokens: Set<UInt32> = [],
        onToken: (@Sendable (UInt32) -> Void)? = nil
    ) async throws -> Result {
        guard k >= 1, k < n else { throw RunError.noSplit }
        let started = Date()

        let chat = JCrossChatManager.shared
        await chat.beginPipelineTurn()
        defer { Task { await chat.endPipelineTurn() } }

        // Both caches must be empty and both sides must agree they are. Starting
        // a turn against a worker still holding the previous turn's positions
        // produces fluent, wrong text with no error — the most dangerous failure
        // in this design, so the ack is awaited rather than assumed.
        await chat.resetEngine()
        do {
            try await PipeChannel.shared.resetPeer()
        } catch {
            throw RunError.workerLost("The other Mac did not confirm it was ready.")
        }

        var generated: [UInt32] = []
        var pos = 0
        var stopped = "max tokens"

        // ── Prefill ────────────────────────────────────────────────────────
        // One shot rather than token-by-token. Mathematically identical for a
        // standard model (the chunked attention is causal and RoPE uses
        // start_pos + t) and literally identical for a hybrid, whose chunked
        // entry point loops per token internally anyway.
        let head = try await chat.runSegment(
            tokens: promptTokens, startLayer: 0, endLayer: k,
            startPos: 0, rawFlags: 0)
        guard case .hidden(let rows) = head else { throw RunError.modelNotLoaded }

        var next: UInt32
        do {
            next = try await PipeChannel.shared.sendSegmentForToken(
                hidden: rows, startLayer: k, endLayer: n, startPos: 0,
                flags: JCrossEngine.SegmentFlags.lmHeadArgmax.rawValue,
                timeout: PipeChannel.prefillTimeout)
        } catch {
            throw RunError.workerLost(error.localizedDescription)
        }
        pos = promptTokens.count
        generated.append(next)
        onToken?(next)

        // ── Decode ─────────────────────────────────────────────────────────
        while generated.count < maxTokens {
            if Task.isCancelled { stopped = "cancelled"; break }
            if eosTokens.contains(next) { stopped = "end of sequence"; break }

            let step = try await chat.runSegment(
                tokens: [next], startLayer: 0, endLayer: k,
                startPos: pos, rawFlags: 0)
            guard case .hidden(let h) = step else { break }

            do {
                next = try await PipeChannel.shared.sendSegmentForToken(
                    hidden: h, startLayer: k, endLayer: n, startPos: pos,
                    flags: JCrossEngine.SegmentFlags.lmHeadArgmax.rawValue,
                    timeout: PipeChannel.decodeTimeout)
            } catch {
                // Deliberately does not fall back to running locally: the
                // remaining layers are not resident here and on the machine this
                // exists for they cannot be. Better an honestly truncated reply
                // than one that swaps the Mac to a standstill.
                throw RunError.workerLost(error.localizedDescription)
            }
            pos += 1
            generated.append(next)
            onToken?(next)
        }

        return Result(tokens: generated,
                      elapsed: Date().timeIntervalSince(started),
                      stoppedBecause: stopped)
    }
}
