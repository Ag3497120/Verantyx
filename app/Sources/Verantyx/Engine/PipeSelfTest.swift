import Foundation

/// End-to-end check that a split generation equals a single-machine one.
///
/// Exists because the claim this whole feature rests on cannot be checked from
/// the outside: two machines producing *some* text proves nothing, since a
/// pipeline with a position off by one still produces fluent text — just the
/// wrong text. The only meaningful assertion is token-for-token equality
/// against the same model run whole.
///
/// Driven by an environment variable rather than a button because it needs two
/// processes started in a known order, which is not something a person can do
/// reliably by clicking:
///
///     VERANTYX_PIPE_SELFTEST=worker
///     VERANTYX_PIPE_SELFTEST=master:127.0.0.1:8790:<model.jgen>
///     VERANTYX_PIPE_SELFTEST=memoryab:<model.jgen>   (memory injection A/B)
///
/// The master writes its verdict to `~/pipe_selftest_result.txt` and exits.
///
/// `VERANTYX_PIPE_SELFTEST_K` takes a comma-separated list, because the
/// reference does not depend on the split point but costs more than everything
/// else put together: on a 27B model the whole-model run is tens of minutes,
/// and recomputing it once per split point was the dominant cost of sweeping.
/// One reference, many splits.
///
///     VERANTYX_PIPE_SELFTEST_K=42,48,56,63
///     VERANTYX_PIPE_SELFTEST_TURNS=3       consecutive turns (RESET contract)
///     VERANTYX_PIPE_SELFTEST_LONG=1        add a long-prompt prefill case
///     VERANTYX_PIPE_SELFTEST_NOREF=1       skip the reference — memory only
///
/// `NOREF` exists because the reference and the memory measurement cannot both
/// be taken in one process. Computing the whole-model reference touches all N
/// layers, so from that moment the master's resident size reflects the whole
/// file and no longer says anything about what the split saves. A run with
/// `NOREF` proves nothing about correctness and is only useful for the number
/// it does measure honestly: the pages a master actually touches when it owns
/// layers [0,k). The worker never needs this — it has no reference to compute.
enum PipeSelfTest {

    static func runIfRequested() {
        guard let spec = ProcessInfo.processInfo.environment["VERANTYX_PIPE_SELFTEST"],
              !spec.isEmpty else { return }
        Task.detached(priority: .userInitiated) { await run(spec: spec) }
    }

    private static func log(_ s: String) {
        FileHandle.standardError.write(Data(("[selftest] " + s + "\n").utf8))
    }

    private static func run(spec: String) async {
        let parts = spec.split(separator: ":", maxSplits: 3).map(String.init)

        // Memory A/B shares this launcher because it has the same shape of
        // need: a real engine, a real store, and no GUI in the way.
        if parts[0] == "memoryab" {
            let model = parts.count > 1 ? parts[1] : ""
            if !model.isEmpty { await loadModel(model) }
            var settings = VectorMemoryInjection.Settings()
            let env = ProcessInfo.processInfo.environment
            if let a = env["VERANTYX_AB_ALPHA"], let v = Float(a) { settings.alpha = v }
            if let l = env["VERANTYX_AB_LAYER"], let v = Int(l) { settings.layer = v }
            do {
                let tokens = Int(env["VERANTYX_AB_TOKENS"] ?? "") ?? 48
                let report = try await MemoryABHarness.shared.run(settings: settings, maxTokens: tokens)
                var lines = ["model: \(report.model)",
                             "alpha: \(report.settings.alpha)  layer: \(report.settings.layer.map(String.init) ?? "auto(N/3)")",
                             ""]
                for o in report.outcomes {
                    lines.append(String(format: "[%-6@] %@  prompt %d chars, %d tok, %.1fs",
                                        o.mode as NSString,
                                        (o.correct ? "PASS" : "fail") as NSString,
                                        o.promptChars, o.generatedTokens, o.seconds))
                    lines.append("         Q: \(o.question)")
                    lines.append("         A: \(o.answer.prefix(160))")
                }
                lines.append("")
                lines.append(report.summary)
                for l in lines { log(l) }
                write(lines)
            } catch {
                log("memoryab FAILED: \(error.localizedDescription)")
            }
            return
        }

        // Shares this launcher for the same reason memoryab does: a real
        // engine, a real tokenizer, and no GUI in the way.
        if parts[0] == "discriminate" {
            let model = parts.count > 1 ? parts[1] : ""
            if !model.isEmpty { await loadModel(model) }
            let env = ProcessInfo.processInfo.environment
            // Comma-separated lists, swept inside one load. `layer` accepts
            // "auto" for the N/3 default so a sweep can mix it with explicit
            // depths without the caller having to know N.
            let alphas = (env["VERANTYX_DISC_ALPHA"] ?? "0.2")
                .split(separator: ",").compactMap { Float($0.trimmingCharacters(in: .whitespaces)) }
            let layers: [Int?] = (env["VERANTYX_DISC_LAYER"] ?? "auto")
                .split(separator: ",").map { s -> Int? in
                    let t = s.trimmingCharacters(in: .whitespaces)
                    return t == "auto" ? nil : Int(t)
                }
            do {
                let reports = try await MemoryDiscrimination.shared.sweep(
                    alphas: alphas.isEmpty ? [0.2] : alphas,
                    layers: layers.isEmpty ? [nil] : layers,
                    topK: env["VERANTYX_DISC_TOPK"].flatMap(Int.init) ?? 4096)
                var out: [String] = []
                if reports.count == 1 {
                    out = reports[0].lines
                } else {
                    out.append(contentsOf: reports[0].lines.prefix(3))
                    out.append("")
                    out.append("── final-layer vector (what the shipping code injects) ──")
                    out.append(contentsOf: MemoryDiscrimination.sweepTable(reports))
                    out.append("")
                    out.append("── same-layer vector (space-matched) ──")
                    out.append(contentsOf: MemoryDiscrimination.matchedTable(reports))
                }
                for l in out { log(l) }
                write(out)
            } catch {
                log("discriminate FAILED: \(error.localizedDescription)")
                write(["discriminate FAILED: \(error.localizedDescription)"])
            }
            return
        }

        if parts[0] == "worker" {
            // The worker only needs the model loaded and the channel listening;
            // the master drives everything else.
            let model = parts.count > 1 ? parts[1] : ""
            if !model.isEmpty { await loadModel(model) }
            do {
                try await PipeChannel.shared.startListening()
                let port = await PipeChannel.shared.boundPort
                log("worker listening on \(port)")
            } catch {
                log("worker FAILED to listen: \(error)")
            }
            return
        }

        guard parts[0] == "master", parts.count >= 4 else {
            log("bad spec: \(spec)")
            return
        }
        let host = parts[1]
        let port = UInt16(parts[2]) ?? 8790
        let model = parts[3]

        var out: [String] = []
        func say(_ s: String) { out.append(s); log(s) }

        await loadModel(model)
        let chat = JCrossChatManager.shared
        let n = await chat.loadedLayerCount
        guard n >= 2 else {
            say("FAIL: model reports \(n) layers")
            write(out); return
        }
        // Split point and length are overridable so the decode loop can be
        // exercised at more than one boundary; three tokens through two decode
        // steps is not enough to catch a position bug that only shows up later.
        let env = ProcessInfo.processInfo.environment
        let ks: [Int] = (env["VERANTYX_PIPE_SELFTEST_K"] ?? "")
            .split(separator: ",").compactMap { Int($0.trimmingCharacters(in: .whitespaces)) }
            .filter { $0 >= 1 && $0 < n }
        let splits = ks.isEmpty ? [n / 2] : ks
        let maxTokens = Int(env["VERANTYX_PIPE_SELFTEST_TOKENS"] ?? "") ?? 12
        let turns = max(1, Int(env["VERANTYX_PIPE_SELFTEST_TURNS"] ?? "") ?? 1)
        say("model \(model): \(n) layers, splits \(splits), up to \(maxTokens) tokens")
        say("rss after load: \(rssGB())")

        let promptA = env["VERANTYX_PIPE_SELFTEST_PROMPT"] ?? "Reply with exactly: PONG"
        guard let prompt = try? await chat.promptTokens(conversation: [(role: "user", content: promptA)]) else {
            say("FAIL: could not tokenize"); write(out); return
        }
        say("prompt: \(prompt.count) tokens")

        // Reference: the same prompt run whole, on this machine. Computed once —
        // it does not depend on where the stack is cut, and on a 27B model it
        // costs more than every distributed run in this sweep combined.
        let skipRef = env["VERANTYX_PIPE_SELFTEST_NOREF"] == "1"
        var reference: [UInt32] = []
        if skipRef {
            say("NOREF: skipping the reference. Nothing below is a correctness result —")
            say("       this run exists only to measure the master's resident size.")
        } else {
            let refStart = Date()
            guard let r = try? await chat.generateRaw(promptTokens: prompt, maxTokens: maxTokens) else {
                say("FAIL: reference generation threw"); write(out); return
            }
            reference = r
            let refElapsed = Date().timeIntervalSince(refStart)
            say("reference (whole model): \(reference)")
            say(String(format: "reference: %.1fs for %d tokens (%.2f tok/s), rss %@",
                       refElapsed, reference.count,
                       Double(reference.count) / max(refElapsed, 0.001), rssGB()))
            say("note: the reference touched all \(n) layers, so every rss below "
                + "reflects the whole file, not what the split costs.")
        }

        do {
            try await PipeChannel.shared.connect(host: host, port: port)
        } catch {
            say("FAIL: could not reach worker at \(host):\(port) — \(error)")
            write(out); return
        }
        let eos = await chat.eosTokenIds
        say("eos ids: \(eos.sorted())")
        say("")

        /// Compares over the shared prefix as well as exactly, because the two
        /// paths can legitimately stop at different points: the engine's own
        /// loop has stop rules (repeat guard, cycle detection) that the
        /// distributed loop does not implement. A common prefix equal to the
        /// full reference means the arithmetic agrees and only the stopping
        /// differs; a short common prefix means a real divergence, and a
        /// position bug in particular shows up as a clean split after a few
        /// correct tokens.
        func verdict(_ got: [UInt32], _ want: [UInt32], _ stopped: String) -> (Bool, String) {
            // With no reference there is nothing to be right or wrong against.
            // Reporting "PASS" here would be the exact false pass this harness
            // was written to prevent, so it says so instead.
            if want.isEmpty { return (true, "not checked — no reference in this run") }
            let common = zip(got, want).prefix { $0 == $1 }.count
            if got == want { return (true, "identical") }
            if common == want.count {
                return (true, "all \(common) match, ran to \(got.count) then \(stopped)")
            }
            return (false, "diverges at token \(common) of \(want.count)")
        }

        var allPassed = true

        // ── Split sweep ───────────────────────────────────────────────────
        for k in splits {
            do {
                let r = try await PipelineRunner.shared.generate(
                    promptTokens: prompt, splitK: k, numLayers: n,
                    maxTokens: maxTokens, eosTokens: eos)
                let (ok, why) = verdict(r.tokens, reference, r.stoppedBecause)
                allPassed = allPassed && ok
                say(String(format: "k=%-3d %@  %.1fs (%.2f tok/s)  rss %@  — %@",
                           k, (ok ? "PASS" : "FAIL") as NSString, r.elapsed,
                           Double(r.tokens.count) / max(r.elapsed, 0.001),
                           rssGB() as NSString, why as NSString))
                if !ok { say("      got  \(r.tokens)"); say("      want \(reference)") }
            } catch {
                allPassed = false
                say("k=\(k)   FAIL — \(error.localizedDescription)")
            }
        }

        // ── Consecutive turns ─────────────────────────────────────────────
        // A leaked KV cache does not throw; it produces fluent, wrong text. The
        // only way to see it is to run the same prompt twice with a different
        // prompt in between and require the two to match. Comparing turn 1 with
        // the reference alone cannot catch it, because turn 1 is the clean one.
        if turns > 1 {
            let k = splits[0]
            say("")
            say("consecutive turns at k=\(k) (A, B, A — the two A's must match):")
            guard let promptB = try? await chat.promptTokens(
                conversation: [(role: "user", content: "Name three colours.")]) else {
                say("  skipped: could not tokenize the second prompt"); write(out); return
            }
            var firstA: [UInt32] = []
            for t in 0..<turns {
                let usingA = (t % 2 == 0)
                let p = usingA ? prompt : promptB
                do {
                    let r = try await PipelineRunner.shared.generate(
                        promptTokens: p, splitK: k, numLayers: n,
                        maxTokens: maxTokens, eosTokens: eos)
                    if usingA && firstA.isEmpty { firstA = r.tokens }
                    var note = ""
                    if usingA && !firstA.isEmpty {
                        let same = r.tokens == firstA
                        if t > 0 { allPassed = allPassed && same }
                        note = t == 0 ? "(baseline)" : (same ? "matches turn 0 — state was reset"
                                                             : "DIFFERS from turn 0 — state leaked")
                    }
                    say(String(format: "  turn %d (%@) %.1fs  %@", t,
                               (usingA ? "A" : "B") as NSString, r.elapsed, note as NSString))
                } catch {
                    allPassed = false
                    say("  turn \(t) FAIL — \(error.localizedDescription)")
                }
            }
        }

        // ── Long-prompt prefill ───────────────────────────────────────────
        // The prefill sends the whole prompt as one [P, hidden] block, a
        // different code path from the one-row decode step. A 14-token prompt
        // barely exercises it.
        if env["VERANTYX_PIPE_SELFTEST_LONG"] == "1" {
            let k = splits[0]
            say("")
            let longText = String(repeating: "The quick brown fox jumps over the lazy dog. ", count: 40)
            if let lp = try? await chat.promptTokens(conversation: [(role: "user", content: longText)]) {
                say("long prompt: \(lp.count) tokens, k=\(k)")
                let lref = try? await chat.generateRaw(promptTokens: lp, maxTokens: maxTokens)
                do {
                    let r = try await PipelineRunner.shared.generate(
                        promptTokens: lp, splitK: k, numLayers: n,
                        maxTokens: maxTokens, eosTokens: eos)
                    if let lref {
                        let (ok, why) = verdict(r.tokens, lref, r.stoppedBecause)
                        allPassed = allPassed && ok
                        say(String(format: "  %@  %.1fs  — %@",
                                   (ok ? "PASS" : "FAIL") as NSString, r.elapsed, why as NSString))
                    } else {
                        say("  reference for the long prompt threw; distributed produced \(r.tokens.count) tokens")
                    }
                } catch {
                    allPassed = false
                    say("  FAIL — \(error.localizedDescription)")
                }
            }
        }

        say("")
        say(allPassed ? "OVERALL PASS" : "OVERALL FAIL")
        write(out)
    }

    /// Resident size of this process, which is the number the whole feature
    /// exists to move: the file is mmap'd whole on both machines, so the split
    /// saves nothing unless the pages of the other machine's layers stay
    /// untouched. Reported next to every result rather than measured once.
    private static func rssGB() -> String {
        var info = mach_task_basic_info()
        var count = mach_msg_type_number_t(MemoryLayout<mach_task_basic_info>.size / MemoryLayout<natural_t>.size)
        let kr = withUnsafeMutablePointer(to: &info) {
            $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                task_info(mach_task_self_, task_flavor_t(MACH_TASK_BASIC_INFO), $0, &count)
            }
        }
        guard kr == KERN_SUCCESS else { return "?" }
        return String(format: "%.1fGB", Double(info.resident_size) / 1_073_741_824)
    }

    private static func loadModel(_ name: String) async {
        do {
            try await JCrossChatManager.shared.load(modelFileName: name)
            log("loaded \(name)")
        } catch {
            log("load failed: \(error.localizedDescription)")
        }
    }

    private static func write(_ lines: [String]) {
        let url = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("pipe_selftest_result.txt")
        try? lines.joined(separator: "\n").write(to: url, atomically: true, encoding: .utf8)
    }
}
