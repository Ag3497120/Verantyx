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
            exit(await runMission(Array(args.dropFirst())))
        case "demo":
            // Alias: reproducible first-publish demo
            exit(await runMission(["--demo"] + Array(args.dropFirst())))
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
          vera run --demo [--trace PATH] [--dry-run]
          vera run --goal "…" [--app Calculator] [--trace PATH] [--dry-run]
          vera demo [--trace PATH] [--dry-run]
          vera schema
          vera version

        Examples:
          swift run vera run --demo --trace traces/demo.jsonl
          vera run --demo --dry-run --trace traces/demo.jsonl

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
