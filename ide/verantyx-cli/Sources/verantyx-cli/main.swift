import Foundation
import VeraCore

@main
struct VeraCLI {
    static func main() async {
        let args = Array(CommandLine.arguments.dropFirst())
        guard let command = args.first else {
            printUsage()
            exit(2)
        }

        switch command {
        case "run":
            // `--model` selects the real JGEN-backed long-horizon loop;
            // without it, `run` stays the model-free demo runner.
            let rest = Array(args.dropFirst())
            if rest.contains("--model") {
                exit(await runLongHorizon(rest, resume: false))
            }
            exit(await runMission(rest))
        case "demo":
            // Alias: reproducible first-publish demo
            exit(await runMission(["--demo"] + Array(args.dropFirst())))
        case "compat":
            exit(runCompat(Array(args.dropFirst())))
        case "resume":
            exit(await runLongHorizon(Array(args.dropFirst()), resume: true))
        case "reembed":
            exit(await runLongHorizon(Array(args.dropFirst()), resume: false, reembedOnly: true))
        case "schema":
            printSchema()
            exit(0)
        case "help", "-h", "--help":
            printUsage()
            exit(0)
        case "version", "--version":
            print("vera 0.1.0 (verantyx-cli) — dual-track with Verantyx IDE GUI")
            exit(0)
        default:
            fputs("unknown command: \(command)\n\n", stderr)
            printUsage()
            exit(2)
        }
    }

    static func printUsage() {
        let text = """
        vera — Verantyx research / repro CLI (GUI stays intact; CLI owns structured logs)

        Usage:
          vera compat --model M.jgen
          vera run    --model M.jgen --memory DIR --goal "…" [--trace T.jsonl] [--max-turns N] [--no-vector-memory]
          vera resume --model M.jgen --memory DIR [--trace T.jsonl] [--max-turns N]
          vera run --demo [--trace PATH] [--dry-run]      # model-free demo
          vera schema
          vera version

        Long-horizon runtime:
          Every turn is an independent forward pass — the KV cache is reset before
          each one and no conversation history is kept. Purpose and prior attempts
          live in DIR/gaps.json; recalled experience in DIR/vectors.*. `resume`
          therefore continues a mission in a fresh process from an empty model.

          The model forgets every turn. The agent does not.

        Model support:
          Runtime is model-agnostic. Published/validated target is Qwen3.6-27B
          (hybrid Gated DeltaNet), with Qwen3.8-27B as the planned swap test.
          `vera compat` reports which tier a given .jgen falls into.

        Examples:
          vera compat --model qwen3.6-27b.jgen
          vera run --model qwen3.6-27b.jgen --memory ./memory \\
                   --goal "Audit this repository for unresolved bugs" \\
                   --trace runs/qwen36.jsonl
          vera resume --model qwen3.6-27b.jgen --memory ./memory
          # A/B the memory itself:
          vera run … --no-vector-memory

        Event kinds (stdout + JSONL):
          MISSION / OBSERVATION / PROPOSED_ACTION / POLICY / RESULT / GAP / SKILL_RECALL

        Defaults:
          vector-only sense ON, PromptBudget-aligned caps (see POLICY events).

        Architecture:
          vera-core     — state, Gap, evidence, skills, safety (event surface)
          verantyx-cli  — this binary (formal research interface)
          verantyx-gui  — Verantyx IDE (observation / approval / demo UI; not gutted)

        TODO(gui): thin-visualize JSONL / SSE from this CLI — do not rebuild GUI as brain.
        """
        print(text)
    }

    /// `vera run --model … --memory …` and `vera resume --model … --memory …`.
    ///
    /// Separate from the demo runner: this one actually loads JGEN and drives
    /// the gap-backed loop, so it is the path any published claim rests on.
    static func runLongHorizon(_ args: [String], resume: Bool, reembedOnly: Bool = false) async -> Int32 {
        var modelPath: String?
        var memoryDir = "./memory"
        var goal: String?
        var tracePath: String?
        var maxTurns = 8
        var noVectorMemory = false
        var workspace = FileManager.default.currentDirectoryPath
        // Read-only unless the operator opts in: an unattended agent that can
        // write files and run shell commands is a different risk category.
        var policy: VeraCore.ToolPolicy = .readOnly
        var agentId: String?

        var i = 0
        while i < args.count {
            func value(_ flag: String) -> String? {
                i += 1
                guard i < args.count else {
                    fputs("\(flag) requires a value\n", stderr)
                    return nil
                }
                return args[i]
            }
            switch args[i] {
            case "--model":
                guard let v = value("--model") else { return 2 }
                modelPath = v
            case "--memory":
                guard let v = value("--memory") else { return 2 }
                memoryDir = v
            case "--goal":
                guard let v = value("--goal") else { return 2 }
                goal = v
            case "--trace":
                guard let v = value("--trace") else { return 2 }
                tracePath = v
            case "--max-turns":
                guard let v = value("--max-turns"), let n = Int(v) else { return 2 }
                maxTurns = n
            case "--no-vector-memory":
                noVectorMemory = true
            case "--workspace":
                guard let v = value("--workspace") else { return 2 }
                workspace = v
            case "--allow-write":
                policy = .allowWrite
            case "--allow-shell":
                policy = .allowShell
            case "--agent":
                guard let v = value("--agent") else { return 2 }
                agentId = v
            case "-h", "--help":
                print("""
                vera run    --model M.jgen --memory DIR --goal "…" [--trace T.jsonl] [--max-turns N] [--no-vector-memory]
                vera resume --model M.jgen --memory DIR [--trace T.jsonl] [--max-turns N]
                """)
                return 0
            default:
                fputs("unknown flag: \(args[i])\n", stderr)
                return 2
            }
            i += 1
        }

        guard let modelPath else {
            fputs("--model is required (use `vera run --demo` for the model-free demo)\n", stderr)
            return 2
        }
        if !resume, !reembedOnly, goal == nil {
            fputs("--goal is required for `vera run --model …`\n", stderr)
            return 2
        }

        // Refuse to start on a model the engine cannot load, rather than
        // failing deep inside the first forward pass.
        let compat = VeraCore.ModelCompat.inspect(modelPath: modelPath)
        guard compat.allBlockingChecksPassed else {
            fputs(compat.report() + "\n", stderr)
            fputs("\npreflight failed — not starting\n", stderr)
            return 1
        }

        let missionId = "m-" + String(UUID().uuidString.prefix(8)).lowercased()
        let traceURL = tracePath.map { URL(fileURLWithPath: $0, relativeTo: cwdURL()).standardizedFileURL }
        let memoryURL = URL(fileURLWithPath: memoryDir, relativeTo: cwdURL()).standardizedFileURL

        do {
            let sink = try VeraEventSink(missionId: missionId, traceURL: traceURL, writeStdout: true)
            defer { sink.close() }

            let runner = try await VeraCore.LongHorizonRunner(
                config: .init(
                    modelPath: modelPath,
                    memoryDirectory: memoryURL,
                    maxTurns: maxTurns,
                    useVectorMemory: !noVectorMemory,
                    workspace: URL(fileURLWithPath: workspace, relativeTo: cwdURL()).standardizedFileURL,
                    toolPolicy: policy,
                    agentId: agentId
                ),
                sink: sink
            )

            if reembedOnly {
                guard let result = try runner.reembedMemory() else {
                    fputs("vector memory is disabled — nothing to re-embed\n", stderr)
                    return 0
                }
                fputs("""
                re-embedded: \(result.migrated) migrated, \(result.kept) already in this space, \(result.failed) failed

                """, stderr)
                return result.failed == 0 ? 0 : 1
            }

            // A swap is detected, not assumed: run/resume migrate on sight so a
            // user who simply passes a new --model does not silently lose the
            // recall half of memory.
            try runner.reembedMemory()

            let outcome = resume
                ? try await runner.resume()
                : try await runner.run(goal: goal!)

            if let traceURL {
                fputs("trace written: \(traceURL.path)\n", stderr)
            }
            guard let outcome else { return 0 }
            fputs("""
            turns=\(outcome.turns) open_gaps=\(outcome.openGaps) resolved=\(outcome.resolvedGaps)
            prompt tokens/turn: \(outcome.promptTokensPerTurn.map(String.init).joined(separator: ", "))

            """, stderr)
            return 0
        } catch {
            fputs("vera \(resume ? "resume" : "run") failed: \(error)\n", stderr)
            return 1
        }
    }

    static func cwdURL() -> URL {
        URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
    }

    /// Step 0 of the release plan: report what a model *would* need, without
    /// loading it and without claiming it runs.
    static func runCompat(_ args: [String]) -> Int32 {
        var modelPath: String?
        var i = 0
        while i < args.count {
            switch args[i] {
            case "--model":
                i += 1
                guard i < args.count else {
                    fputs("--model requires a path\n", stderr)
                    return 2
                }
                modelPath = args[i]
            case "-h", "--help":
                print("vera compat --model PATH/TO/model.jgen")
                return 0
            default:
                // Allow a bare path: `vera compat model.jgen`
                if modelPath == nil, !args[i].hasPrefix("-") {
                    modelPath = args[i]
                } else {
                    fputs("unknown flag: \(args[i])\n", stderr)
                    return 2
                }
            }
            i += 1
        }

        guard let modelPath else {
            fputs("usage: vera compat --model PATH/TO/model.jgen\n", stderr)
            return 2
        }

        let report = VeraCore.ModelCompat.inspect(modelPath: modelPath)
        print(report.report())
        return report.allBlockingChecksPassed ? 0 : 1
    }

    static func printSchema() {
        print("""
        # VeraRuntimeEvent schema_version=1 (JSONL one object per line)
        # kinds: mission | observation | proposed_action | policy | result | gap | skill_recall
        {
          "schema_version": 1,
          "ts": "ISO8601",
          "kind": "mission",
          "mission_id": "…",
          "turn": 0,
          "summary": "…",
          "detail": { "key": "value" },
          "tags": ["demo"]
        }
        """)
    }

    static func runMission(_ args: [String]) async -> Int32 {
        var demo = false
        var dryRun = false
        var goal: String?
        var app = "Calculator"
        var tracePath: String?

        var i = 0
        while i < args.count {
            let a = args[i]
            switch a {
            case "--demo":
                demo = true
            case "--dry-run":
                dryRun = true
            case "--goal":
                i += 1
                guard i < args.count else {
                    fputs("--goal requires a value\n", stderr)
                    return 2
                }
                goal = args[i]
            case "--app":
                i += 1
                guard i < args.count else {
                    fputs("--app requires a value\n", stderr)
                    return 2
                }
                app = args[i]
            case "--trace":
                i += 1
                guard i < args.count else {
                    fputs("--trace requires a path\n", stderr)
                    return 2
                }
                tracePath = args[i]
            case "-h", "--help":
                printUsage()
                return 0
            default:
                fputs("unknown flag: \(a)\n", stderr)
                return 2
            }
            i += 1
        }

        if demo {
            goal = goal ?? DemoMissionRunner.calculatorDemo().goal
        }

        guard let goal, !goal.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            fputs("provide --demo or --goal \"…\"\n", stderr)
            return 2
        }

        let missionId = "m-" + String(UUID().uuidString.prefix(8)).lowercased()
        let traceURL: URL? = tracePath.map { path in
            let url = URL(fileURLWithPath: path)
            if url.path.hasPrefix("/") {
                return url
            }
            return URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
                .appendingPathComponent(path)
        }

        do {
            let sink = try VeraEventSink(missionId: missionId, traceURL: traceURL, writeStdout: true)
            defer { sink.close() }

            let runner = demo
                ? DemoMissionRunner.calculatorDemo(dryRun: dryRun)
                : DemoMissionRunner(goal: goal, appName: app, dryRun: dryRun, allowOpenApp: !dryRun)

            let code = await runner.run(sink: sink)
            if let traceURL {
                fputs("trace written: \(traceURL.path)\n", stderr)
            }
            return Int32(code)
        } catch {
            fputs("vera run failed: \(error)\n", stderr)
            return 1
        }
    }
}
