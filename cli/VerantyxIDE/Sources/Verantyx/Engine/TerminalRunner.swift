import Foundation
import SwiftUI

// MARK: - TerminalEntry

struct TerminalEntry: Identifiable {
    let id = UUID()
    let timestamp: Date
    var kind: Kind
    var text: String

    enum Kind {
        case command         // $ cargo check
        case stdout          // green
        case stderr          // red/orange
        case info            // gray
        case aiAction        // AI-initiated command (purple)
        case exitCode(Int32) // ✓ 0 / ✗ 1
    }

    var displayColor: Color {
        switch kind {
        case .command:       return Color(red: 0.5, green: 0.9, blue: 0.5) // bright green
        case .stdout:        return Color(red: 0.88, green: 0.88, blue: 0.88)
        case .stderr:        return Color(red: 1.0, green: 0.4, blue: 0.3)
        case .info:          return Color(red: 0.6, green: 0.6, blue: 0.8)
        case .aiAction:      return Color(red: 0.8, green: 0.6, blue: 1.0) // purple
        case .exitCode(let c): return c == 0 ? .green : .red
        }
    }

    var prefix: String {
        switch kind {
        case .command:       return "$ "
        case .aiAction:      return "🤖 "
        case .info:          return "  "
        case .stdout:        return "  "
        case .stderr:        return "  "
        case .exitCode(let c): return c == 0 ? "✓ " : "✗ "
        }
    }
}

// MARK: - TerminalRunner (Approach B)
// Foundation.Process-based async command executor.
// Designed for AI-autonomous command execution:
//   AI emits [RUN: cargo check] → TerminalRunner executes → stdout/stderr returned to AI

@MainActor
final class TerminalRunner: ObservableObject {

    @Published var history: [TerminalEntry] = []
    @Published var isRunning = false
    @Published var workingDirectory: URL?

    // MARK: - Public API

    /// Run a shell command. Returns (stdout, stderr, exitCode).
    /// The output is also appended to `history` for UI display.
    @discardableResult
    func run(
        _ command: String,
        in directory: URL? = nil,
        initiatedByAI: Bool = false
    ) async -> TerminalResult {
        let fallbackPath = AppState.shared?.cortexWorkspacePath ?? AppState.shared?.workspaceURL?.path
        let dir = directory ?? workingDirectory ?? (fallbackPath != nil ? URL(fileURLWithPath: fallbackPath!) : URL(fileURLWithPath: "/tmp"))

        // Log the command
        let cmdString = "[\(dir.lastPathComponent)] \(command)"
        append(text: cmdString, kind: initiatedByAI ? .aiAction : .command)

        isRunning = true
        let result = await executeProcess(command: command, workingDir: dir)
        isRunning = false

        // Log output
        if !result.stdout.isEmpty {
            // Split long stdout into lines to keep UI responsive
            for line in result.stdout.components(separatedBy: "\n").prefix(200) {
                append(text: line, kind: .stdout)
            }
            if result.stdout.components(separatedBy: "\n").count > 200 {
                append(text: "… (\(result.stdout.components(separatedBy: "\n").count) lines)", kind: .info)
            }
        }
        if !result.stderr.isEmpty {
            for line in result.stderr.components(separatedBy: "\n").prefix(100) {
                append(text: line, kind: .stderr)
            }
        }

        append(text: "exit \(result.exitCode)", kind: .exitCode(result.exitCode))
        return result
    }

    /// Clear terminal history.
    func clear() { history = [] }

    // MARK: - Process execution (runs off main actor)

    private func executeProcess(command: String, workingDir: URL) async -> TerminalResult {
        await Task.detached(priority: .userInitiated) {
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/bin/zsh")
            process.arguments = ["-c", command]
            process.currentDirectoryURL = workingDir

            // Inherit parent environment (PATH, etc.) + add common paths
            var env = ProcessInfo.processInfo.environment
            env["PATH"] = (env["PATH"] ?? "/usr/bin:/bin") +
                ":/usr/local/bin:/opt/homebrew/bin:/opt/homebrew/sbin"
            env["TERM"] = "xterm-256color"
            process.environment = env

            let stdoutPipe = Pipe()
            let stderrPipe = Pipe()
            process.standardOutput = stdoutPipe
            process.standardError  = stderrPipe

            do {
                try process.run()
            } catch {
                return TerminalResult(
                    command: command,
                    stdout: "",
                    stderr: "Failed to launch process: \(error.localizedDescription)",
                    exitCode: -1
                )
            }

            // ⚠️ 両パイプを並行ドレインして dual-pipe deadlock を防止。
            // 逐次読み取り (readDataToEndOfFile を stdout → stderr の順に呼ぶ) だと、
            // stderr バッファ (64KB) が満杯になるとプロセスが stderr write でブロック →
            // stdout EOF が来ない → readDataToEndOfFile(stdout) が永久にブロック → デッドロック。
            let stdoutBox = _StringBox()
            let stderrBox = _StringBox()
            let group = DispatchGroup()

            group.enter()
            DispatchQueue.global(qos: .userInitiated).async {
                let data = stdoutPipe.fileHandleForReading.readDataToEndOfFile()
                if let text = String(data: data, encoding: .utf8) {
                    stdoutBox.append(text)
                }
                group.leave()
            }

            group.enter()
            DispatchQueue.global(qos: .userInitiated).async {
                let data = stderrPipe.fileHandleForReading.readDataToEndOfFile()
                if let text = String(data: data, encoding: .utf8) {
                    stderrBox.append(text)
                }
                group.leave()
            }

            group.wait()
            process.waitUntilExit()

            return TerminalResult(
                command: command,
                stdout: stdoutBox.value.trimmingCharacters(in: .whitespacesAndNewlines),
                stderr: stderrBox.value.trimmingCharacters(in: .whitespacesAndNewlines),
                exitCode: process.terminationStatus
            )
        }.value
    }

    // MARK: - Helpers

    private func append(text: String, kind: TerminalEntry.Kind) {
        guard !text.isEmpty else { return }
        history.append(TerminalEntry(timestamp: Date(), kind: kind, text: text))
        // Keep last 2000 entries
        if history.count > 2000 { history.removeFirst(history.count - 2000) }
    }
}

// MARK: - TerminalResult

struct TerminalResult {
    let command: String
    let stdout:  String
    let stderr:  String
    let exitCode: Int32

    var succeeded: Bool { exitCode == 0 }

    /// Combined output suitable for feeding back to AI as context.
    var combinedForAI: String {
        var parts: [String] = ["$ \(command)"]
        if !stdout.isEmpty { parts.append(stdout) }
        if !stderr.isEmpty { parts.append("[stderr]\n\(stderr)") }
        parts.append("[exit: \(exitCode)]")
        return parts.joined(separator: "\n")
    }
}

// MARK: - Quick-run commands

extension TerminalRunner {

    /// Detect project type and return suggested commands
    static func suggestedCommands(for directory: URL) -> [(label: String, command: String)] {
        let fm = FileManager.default
        func has(_ name: String) -> Bool {
            fm.fileExists(atPath: directory.appendingPathComponent(name).path)
        }

        if has("Package.swift")       { return swiftCommands }
        if has("Cargo.toml")          { return rustCommands }
        if has("package.json")        { return nodeCommands }
        if has("go.mod")              { return goCommands }
        if has("requirements.txt") || has("pyproject.toml") { return pythonCommands }
        if has("Makefile")            { return [("make", "make"), ("make clean", "make clean")] }
        return genericCommands
    }

    private static let swiftCommands: [(String, String)] = [
        ("swift build", "swift build"), ("swift test", "swift test"),
        ("swift run", "swift run"), ("swift package clean", "swift package clean")
    ]
    private static let rustCommands: [(String, String)] = [
        ("cargo check", "cargo check"), ("cargo build", "cargo build"),
        ("cargo test", "cargo test"), ("cargo clippy", "cargo clippy"),
        ("cargo fmt", "cargo fmt"), ("cargo run", "cargo run")
    ]
    private static let nodeCommands: [(String, String)] = [
        ("npm install", "npm install"), ("npm run dev", "npm run dev"),
        ("npm run build", "npm run build"), ("npm test", "npm test"),
        ("npm run lint", "npm run lint")
    ]
    private static let goCommands: [(String, String)] = [
        ("go build ./...", "go build ./..."), ("go test ./...", "go test ./..."),
        ("go vet ./...", "go vet ./..."), ("go fmt ./...", "go fmt ./...")
    ]
    private static let pythonCommands: [(String, String)] = [
        ("python -m pytest", "python -m pytest"), ("python -m mypy .", "python -m mypy ."),
        ("pip install -r requirements.txt", "pip install -r requirements.txt")
    ]
    private static let genericCommands: [(String, String)] = [
        ("ls -la", "ls -la"), ("git status", "git status"),
        ("git log --oneline -10", "git log --oneline -10")
    ]
}
