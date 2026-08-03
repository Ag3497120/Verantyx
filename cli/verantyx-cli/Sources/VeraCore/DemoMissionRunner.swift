import Foundation
import AppKit

/// Thin mission runtime for research / repro.
///
/// Wires a **scripted** Act/sense path (OPEN_APP → DESKTOP_SNAPSHOT → DONE)
/// without inventing a second brain. Full JGEN Act (`JGenActAgent`) remains
/// in the IDE; this runner shares the same tool-tag vocabulary and event schema
/// so traces are comparable.
public struct DemoMissionRunner: Sendable {
    public var goal: String
    public var appName: String
    public var dryRun: Bool
    public var allowOpenApp: Bool

    public init(
        goal: String,
        appName: String = "Calculator",
        dryRun: Bool = false,
        allowOpenApp: Bool = true
    ) {
        self.goal = goal
        self.appName = appName
        self.dryRun = dryRun
        self.allowOpenApp = allowOpenApp
    }

    /// Reproducible first-publish demo: open Calculator, AX snapshot, DONE.
    public static func calculatorDemo(dryRun: Bool = false) -> DemoMissionRunner {
        DemoMissionRunner(
            goal: "Open Calculator, take a vector-only AX snapshot, then DONE.",
            appName: "Calculator",
            dryRun: dryRun,
            allowOpenApp: !dryRun
        )
    }

    @discardableResult
    public func run(sink: VeraEventSink) async -> Int {
        let mid = sink.missionId
        sink.emit(
            .mission,
            summary: goal,
            turn: 0,
            detail: [
                "app": appName,
                "mode": dryRun ? "dry_run" : "live",
                "runtime": "verantyx-cli",
                "substrate": "act_sense_tags",
                "mission_kind": "act",
            ],
            tags: ["demo", "cli", "mission_kind:act"]
        )

        sink.emit(
            .policy,
            summary: "vector-only sense + PromptBudget-aligned caps (CLI default)",
            turn: 0,
            detail: VeraSafetyDefaults.policyDetail,
            tags: ["safety", "prompt_budget", "vector_only"]
        )

        // Skill / gap modules are swappable surfaces — stub but visible in logs.
        sink.emit(
            .skill_recall,
            summary: "no prior exploration asset for this demo goal",
            turn: 0,
            detail: [
                "store": "ExplorationAssetStore",
                "status": "stub_empty",
                "hint": "IDE JGenActAgent forges assets on successful DONE",
            ],
            tags: ["skills"]
        )

        sink.emit(
            .gap,
            summary: "no open GapNode for demo mission (normal cognition mode)",
            turn: 0,
            detail: [
                "module": "vera-a/gap",
                "status": "stub_none",
                "cognition_mode": "normal",
            ],
            tags: ["gap", "evidence"]
        )

        // ── Turn 1: OPEN_APP ──────────────────────────────────────────────
        let openTag = "[OPEN_APP: \(appName)]"
        sink.emit(
            .proposed_action,
            summary: openTag,
            turn: 1,
            detail: ["tool": "OPEN_APP", "app": appName],
            tags: ["act"]
        )

        let openResult: String
        if dryRun || !allowOpenApp {
            openResult = "dry-run: skipped live OPEN_APP for \(appName)"
        } else {
            openResult = await openApplication(named: appName)
        }
        sink.emit(
            .result,
            summary: openResult,
            turn: 1,
            detail: ["tool": "OPEN_APP", "ok": openResult.hasPrefix("✓") || openResult.contains("dry-run") ? "true" : "false"],
            tags: ["act"]
        )

        // ── Turn 2: DESKTOP_SNAPSHOT (vector-only / AX) ───────────────────
        sink.emit(
            .proposed_action,
            summary: "[DESKTOP_SNAPSHOT]",
            turn: 2,
            detail: [
                "tool": "DESKTOP_SNAPSHOT",
                "vector_only_sense": "true",
                "pixels": "not_retained_for_model",
            ],
            tags: ["sense"]
        )

        let snap = await axSnapshotSummary(appName: appName, dryRun: dryRun)
        sink.emit(
            .observation,
            summary: String(snap.prefix(240)),
            turn: 2,
            detail: [
                "tool": "DESKTOP_SNAPSHOT",
                "sense": "ax_map",
                "chars": "\(snap.count)",
            ],
            tags: ["sense", "observation"]
        )
        sink.emit(
            .result,
            summary: snap.hasPrefix("✗") ? snap : "✓ AX snapshot captured (\(snap.count) chars)",
            turn: 2,
            detail: ["tool": "DESKTOP_SNAPSHOT"],
            tags: ["sense"]
        )

        // ── Turn 3: DONE ─────────────────────────────────────────────────
        let doneTag = "[DONE: demo mission complete — \(appName) sensed]"
        sink.emit(
            .proposed_action,
            summary: doneTag,
            turn: 3,
            detail: ["tool": "DONE"],
            tags: ["act"]
        )
        sink.emit(
            .result,
            summary: "mission finished",
            turn: 3,
            detail: [
                "tool": "DONE",
                "mission_id": mid,
                "events": "\(sink.events.count)",
            ],
            tags: ["done"]
        )

        let failed = sink.events.contains {
            $0.kind == .result && ($0.detail["ok"] == "false")
        }
        return failed ? 1 : 0
    }

    // MARK: - Act/sense limbs (thin; same tags as AgentTool)

    private func openApplication(named name: String) async -> String {
        await withCheckedContinuation { cont in
            DispatchQueue.main.async {
                let workspace = NSWorkspace.shared
                let url = workspace.urlForApplication(withBundleIdentifier: self.bundleIdHint(for: name))
                    ?? workspace.urlForApplication(toOpen: URL(fileURLWithPath: "/System/Applications/\(name).app"))
                    ?? URL(fileURLWithPath: "/System/Applications/\(name).app")

                let config = NSWorkspace.OpenConfiguration()
                config.activates = true
                workspace.openApplication(at: url, configuration: config) { app, error in
                    if let error {
                        // Fallback: `open -a`
                        let proc = Process()
                        proc.executableURL = URL(fileURLWithPath: "/usr/bin/open")
                        proc.arguments = ["-a", name]
                        do {
                            try proc.run()
                            proc.waitUntilExit()
                            if proc.terminationStatus == 0 {
                                cont.resume(returning: "✓ OS App opened via open -a: \(name)")
                            } else {
                                cont.resume(returning: "✗ Could not open \(name): \(error.localizedDescription)")
                            }
                        } catch {
                            cont.resume(returning: "✗ Could not open \(name): \(error.localizedDescription)")
                        }
                        return
                    }
                    let label = app?.localizedName ?? name
                    cont.resume(returning: "✓ OS App opened and brought frontmost: \(label)")
                }
            }
        }
    }

    private func bundleIdHint(for name: String) -> String {
        switch name.lowercased() {
        case "calculator", "calc": return "com.apple.calculator"
        case "safari": return "com.apple.Safari"
        case "textedit": return "com.apple.TextEdit"
        default: return "com.apple.\(name.lowercased())"
        }
    }

    private func axSnapshotSummary(appName: String, dryRun: Bool) async -> String {
        if dryRun {
            return "[AX MAP dry-run] app=\(appName) vector_only=true (no live Accessibility query)"
        }
        // Minimal AX via AppleScript — same sense idea as DESKTOP_SNAPSHOT without
        // pulling HiddenWindowAutomation / JPEG paths (vector-only default).
        let script = """
        tell application "System Events"
          if not (exists process "\(appName)") then return "NO_PROCESS"
          tell process "\(appName)"
            set winCount to count of windows
            if winCount is 0 then return "WINDOWS=0"
            set w to window 1
            set winName to name of w
            set btnCount to 0
            try
              set btnCount to count of buttons of w
            end try
            return "APP=\(appName)|WINDOW=" & winName & "|BUTTONS=" & btnCount & "|VECTOR_ONLY=1"
          end tell
        end tell
        """
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
        proc.arguments = ["-e", script]
        let out = Pipe()
        let err = Pipe()
        proc.standardOutput = out
        proc.standardError = err
        do {
            try proc.run()
            proc.waitUntilExit()
            let data = out.fileHandleForReading.readDataToEndOfFile()
            let text = String(data: data, encoding: .utf8)?
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            if proc.terminationStatus != 0 || text.isEmpty || text == "NO_PROCESS" {
                let errText = String(data: err.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
                return "[AX MAP] app=\(appName) limited=\(text.isEmpty ? "unavailable" : text) err=\(errText.prefix(120)) — grant Accessibility if needed; vector-only sense still recorded"
            }
            return "[AX MAP] \(text)"
        } catch {
            return "✗ AX snapshot failed: \(error.localizedDescription)"
        }
    }
}
