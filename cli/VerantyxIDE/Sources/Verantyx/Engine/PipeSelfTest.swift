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
        let k = Int(env["VERANTYX_PIPE_SELFTEST_K"] ?? "") ?? (n / 2)
        let maxTokens = Int(env["VERANTYX_PIPE_SELFTEST_TOKENS"] ?? "") ?? 12
        say("model \(model): \(n) layers, split \(k)/\(n - k), up to \(maxTokens) tokens")

        // Reference: the same prompt run whole, on this machine.
        let conversation = [(role: "user", content: env["VERANTYX_PIPE_SELFTEST_PROMPT"] ?? "Reply with exactly: PONG")]
        guard let prompt = try? await chat.promptTokens(conversation: conversation) else {
            say("FAIL: could not tokenize"); write(out); return
        }
        say("prompt: \(prompt.count) tokens")

        guard let reference = try? await chat.generateRaw(promptTokens: prompt, maxTokens: maxTokens) else {
            say("FAIL: reference generation threw"); write(out); return
        }
        say("reference (whole model): \(reference)")

        // Distributed: same prompt, same model, layers split across two processes.
        do {
            try await PipeChannel.shared.connect(host: host, port: port)
        } catch {
            say("FAIL: could not reach worker at \(host):\(port) — \(error)")
            write(out); return
        }

        do {
            let eos = await chat.eosTokenIds
            say("eos ids: \(eos.sorted())")
            let result = try await PipelineRunner.shared.generate(
                promptTokens: prompt, splitK: k, numLayers: n, maxTokens: maxTokens,
                eosTokens: eos)
            say("distributed:            \(result.tokens)")
            say(String(format: "%.2fs, stopped: %@", result.elapsed, result.stoppedBecause))

            // Compare over the shared prefix as well as exactly, because the
            // two paths can legitimately stop at different points: the engine's
            // own loop has stop rules (repeat guard, cycle detection) that the
            // distributed loop does not implement. A common prefix equal to the
            // full reference means the arithmetic agrees and only the stopping
            // differs; a short common prefix means a real divergence, and a
            // position bug in particular shows up as a clean split after a few
            // correct tokens.
            let common = zip(result.tokens, reference).prefix { $0 == $1 }.count
            if result.tokens == reference {
                say("PASS: distributed generation is token-identical to the whole model")
            } else if common == reference.count {
                say("PASS: all \(common) reference tokens match; "
                    + "distributed produced \(result.tokens.count) before stopping on \(result.stoppedBecause)")
            } else {
                say("FAIL: diverges at token \(common) of \(reference.count)")
            }
        } catch {
            say("FAIL: distributed generation threw — \(error.localizedDescription)")
        }
        write(out)
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
