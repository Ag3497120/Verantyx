import Foundation

/// Tool execution for the CLI runtime.
///
/// The bracket grammar is deliberately the **same** one the IDE's
/// `AgentTool.swift` parses, so a model prompted for one surface behaves on
/// the other and traces stay comparable. What is *not* shared is the
/// implementation: the IDE's executor is 2700 lines bound to SwiftUI, AppKit
/// and `AppState.shared` (approval sheets, artifact panel, diff view), none of
/// which exist in a CLI process. Porting it verbatim was not possible; this is
/// the subset that Foundation can honestly carry, plus an approval seam the
/// CLI fills with a policy instead of a modal.
///
/// Desktop / vision tools (`DESKTOP_ACT`, `AX_ACT`, `VISION_*`) are absent on
/// purpose rather than stubbed: a tool that silently does nothing is worse
/// than one that reports it is unavailable, and the honesty rule this runtime
/// is built on says a limb that did not act must never look like one that did.
public enum CLITool: Sendable, Equatable {
    case readFile(String)
    case writeFile(path: String, content: String)
    case makeDir(String)
    case listDir(String)
    case runCommand(String)
    case done(message: String)

    /// Tag as it appears in model output — used for traces and attempt keys.
    public var label: String {
        switch self {
        case .readFile(let p): return "READ_FILE: \(p)"
        case .writeFile(let p, _): return "WRITE_FILE: \(p)"
        case .makeDir(let p): return "MAKE_DIR: \(p)"
        case .listDir(let p): return "LIST_DIR: \(p)"
        case .runCommand(let c): return "RUN: \(c.prefix(60))"
        case .done: return "DONE"
        }
    }

    /// True when the tool changes state outside the process.
    public var isMutating: Bool {
        switch self {
        case .readFile, .listDir, .done: return false
        case .writeFile, .makeDir, .runCommand: return true
        }
    }
}

// MARK: - Parsing

public enum CLIToolParser {

    /// Extracts the first tool tag in `text`.
    ///
    /// Content is read to the *matching* closing bracket rather than the first
    /// one, because file bodies and shell commands routinely contain `]` — the
    /// IDE hit exactly this bug and truncated commands mid-argument.
    public static func parseFirst(_ text: String) -> CLITool? {
        for (open, build) in grammar {
            guard let range = text.range(of: "[\(open)", options: .caseInsensitive) else { continue }
            guard let body = balancedBody(in: text, from: range.lowerBound) else { continue }
            let payload = body
                .dropFirst(open.count + 1)          // "[TAG"
                .drop(while: { $0 == ":" || $0 == " " })
            if let tool = build(String(payload)) { return tool }
        }
        return nil
    }

    /// Returns the substring from `[` to its matching `]`, tracking nesting.
    private static func balancedBody(in text: String, from start: String.Index) -> String? {
        var depth = 0
        var index = start
        while index < text.endIndex {
            let ch = text[index]
            if ch == "[" { depth += 1 }
            if ch == "]" {
                depth -= 1
                if depth == 0 {
                    return String(text[text.index(after: start)..<index])
                }
            }
            index = text.index(after: index)
        }
        return nil
    }

    private static let grammar: [(String, (String) -> CLITool?)] = [
        ("READ_FILE", { p in p.isEmpty ? nil : .readFile(p.trimmed) }),
        ("WRITE_FILE", { payload in
            // WRITE_FILE: path\ncontent…
            guard let newline = payload.firstIndex(of: "\n") else { return nil }
            let path = String(payload[..<newline]).trimmed
            let content = String(payload[payload.index(after: newline)...])
            return path.isEmpty ? nil : .writeFile(path: path, content: content)
        }),
        ("MAKE_DIR", { p in p.isEmpty ? nil : .makeDir(p.trimmed) }),
        ("LIST_DIR", { p in .listDir(p.trimmed.isEmpty ? "." : p.trimmed) }),
        ("RUN", { c in c.trimmed.isEmpty ? nil : .runCommand(c.trimmed) }),
        ("DONE", { m in .done(message: m.trimmed) }),
    ]
}

private extension String {
    var trimmed: String { trimmingCharacters(in: .whitespacesAndNewlines) }
}

// MARK: - Execution

/// What a CLI run is allowed to do without a human in the loop.
///
/// The IDE asks with a sheet; a non-interactive run has no one to ask, so the
/// decision has to be made up front and stated in the trace. Default is
/// read-only: an agent that can edit files and run shell commands unattended
/// is a different risk category, and opting into it should be deliberate.
public enum ToolPolicy: String, Sendable {
    /// Reads and listings only. Mutating tools are refused, not silently skipped.
    case readOnly
    /// Mutating tools allowed inside the workspace.
    case allowWrite
    /// Adds shell execution.
    case allowShell

    public func permits(_ tool: CLITool) -> Bool {
        switch tool {
        case .readFile, .listDir, .done: return true
        case .writeFile, .makeDir: return self != .readOnly
        case .runCommand: return self == .allowShell
        }
    }
}

public struct ToolResult: Sendable {
    public let ok: Bool
    public let text: String
    /// Set when the tool was refused rather than attempted.
    public let refused: Bool

    public init(ok: Bool, text: String, refused: Bool = false) {
        self.ok = ok
        self.text = text
        self.refused = refused
    }
}

public struct ToolExecutor: Sendable {

    public let workspace: URL
    public let policy: ToolPolicy
    /// Observations are bounded before they reach the model. Vector memory
    /// removes the need to keep a *conversation*, but a single 50 KB file read
    /// would still blow one turn's prompt on its own.
    public let maxObservationChars: Int

    public init(workspace: URL, policy: ToolPolicy = .readOnly, maxObservationChars: Int = 2_000) {
        self.workspace = workspace
        self.policy = policy
        self.maxObservationChars = maxObservationChars
    }

    public func execute(_ tool: CLITool) -> ToolResult {
        guard policy.permits(tool) else {
            return ToolResult(
                ok: false,
                text: "✗ refused by policy (\(policy.rawValue)): \(tool.label)",
                refused: true
            )
        }
        switch tool {
        case .readFile(let path):
            return readFile(path)
        case .listDir(let path):
            return listDir(path)
        case .makeDir(let path):
            return makeDir(path)
        case .writeFile(let path, let content):
            return writeFile(path, content)
        case .runCommand(let command):
            return runCommand(command)
        case .done(let message):
            return ToolResult(ok: true, text: message)
        }
    }

    // MARK: - Path safety

    /// Resolves inside the workspace, refusing escapes.
    ///
    /// `..` is checked after standardisation, so `a/../../etc/passwd` is caught
    /// rather than only literal leading `..`.
    private func resolve(_ path: String) -> URL? {
        let candidate = path.hasPrefix("/")
            ? URL(fileURLWithPath: path)
            : workspace.appendingPathComponent(path)
        let resolved = candidate.standardizedFileURL
        let root = workspace.standardizedFileURL
        guard resolved.path == root.path || resolved.path.hasPrefix(root.path + "/") else {
            return nil
        }
        return resolved
    }

    private func outsideWorkspace(_ path: String) -> ToolResult {
        ToolResult(ok: false, text: "✗ path is outside the workspace: \(path)", refused: true)
    }

    // MARK: - Tools

    private func readFile(_ path: String) -> ToolResult {
        guard let url = resolve(path) else { return outsideWorkspace(path) }
        guard let data = FileManager.default.contents(atPath: url.path),
              let text = String(data: data, encoding: .utf8) else {
            return ToolResult(ok: false, text: "✗ cannot read \(path)")
        }
        return ToolResult(ok: true, text: bound(text, note: "file"))
    }

    private func listDir(_ path: String) -> ToolResult {
        guard let url = resolve(path) else { return outsideWorkspace(path) }
        guard let entries = try? FileManager.default.contentsOfDirectory(atPath: url.path) else {
            return ToolResult(ok: false, text: "✗ cannot list \(path)")
        }
        let listing = entries.sorted().prefix(200).joined(separator: "\n")
        return ToolResult(ok: true, text: bound(listing, note: "listing"))
    }

    private func makeDir(_ path: String) -> ToolResult {
        guard let url = resolve(path) else { return outsideWorkspace(path) }
        do {
            try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
            return ToolResult(ok: true, text: "✓ created \(path)")
        } catch {
            return ToolResult(ok: false, text: "✗ mkdir failed: \(error.localizedDescription)")
        }
    }

    private func writeFile(_ path: String, _ content: String) -> ToolResult {
        guard let url = resolve(path) else { return outsideWorkspace(path) }
        do {
            try FileManager.default.createDirectory(
                at: url.deletingLastPathComponent(), withIntermediateDirectories: true
            )
            try content.write(to: url, atomically: true, encoding: .utf8)
            return ToolResult(ok: true, text: "✓ wrote \(content.count) chars to \(path)")
        } catch {
            return ToolResult(ok: false, text: "✗ write failed: \(error.localizedDescription)")
        }
    }

    private func runCommand(_ command: String) -> ToolResult {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/zsh")
        process.arguments = ["-lc", command]
        process.currentDirectoryURL = workspace
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = pipe
        do { try process.run() } catch {
            return ToolResult(ok: false, text: "✗ could not launch: \(error.localizedDescription)")
        }
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        let output = String(data: data, encoding: .utf8) ?? ""
        let status = process.terminationStatus
        // A non-zero exit is reported as a failure even when it printed output,
        // so a broken command cannot read as a successful step.
        return ToolResult(
            ok: status == 0,
            text: bound((status == 0 ? "" : "✗ exit \(status)\n") + output, note: "output")
        )
    }

    /// Keeps the head and tail of a long observation: the beginning usually
    /// carries the shape of the result and the end carries the error.
    private func bound(_ text: String, note: String) -> String {
        guard text.count > maxObservationChars else { return text }
        let half = maxObservationChars / 2
        let head = text.prefix(half)
        let tail = text.suffix(half)
        return "\(head)\n… [\(note) truncated, \(text.count) chars total] …\n\(tail)"
    }
}
