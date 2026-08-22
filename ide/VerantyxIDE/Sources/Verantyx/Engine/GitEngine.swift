import Foundation

// MARK: - GitEngine
// Lightweight Git integration:
//   • getDiff()     — unstaged line-level diff (for gutter annotations)
//   • getStatus()   — file-level status (M/A/D/?)
//   • commit()      — stage all + commit with message
//   • push()        — git push origin HEAD
//   • log()         — recent commits
//   • branches()    — all local branches

final class GitEngine: ObservableObject {

    // MARK: - Models

    struct FileStat: Identifiable, Equatable {
        let id: String  // relative path
        let path: String
        let status: FileStatus

        enum FileStatus: String {
            case modified  = "M"
            case added     = "A"
            case deleted   = "D"
            case untracked = "?"
            case renamed   = "R"
            case copied    = "C"
            case unknown   = " "

            var color: String {
                switch self {
                case .modified:  return "orange"
                case .added:     return "green"
                case .deleted:   return "red"
                case .untracked: return "gray"
                default:         return "blue"
                }
            }

            var icon: String {
                switch self {
                case .modified:  return "pencil.circle"
                case .added:     return "plus.circle"
                case .deleted:   return "minus.circle"
                case .untracked: return "questionmark.circle"
                default:         return "circle"
                }
            }
        }
    }

    struct GutterMark: Identifiable, Equatable {
        let id: Int   // line number (1-based)
        let lineNumber: Int
        let kind: GutterKind

        enum GutterKind { case added, modified, deleted }
    }

    struct CommitLog: Identifiable {
        let id: String  // hash
        let hash: String
        let shortHash: String
        let message: String
        let author: String
        let date: String
    }

    // MARK: - Published state

    @Published var stagedFiles: [FileStat] = []
    @Published var unstagedFiles: [FileStat] = []
    @Published var currentBranch: String = ""
    @Published var commitLog: [CommitLog] = []
    @Published var isLoading: Bool = false
    @Published var lastError: String? = nil

    private var root: URL?

    // MARK: - Setup

    func configure(root: URL) {
        self.root = root
        Task { await refresh() }
    }

    @MainActor
    func refresh() async {
        guard let root else { return }
        isLoading = true
        defer { isLoading = false }

        currentBranch = (try? await run(["rev-parse", "--abbrev-ref", "HEAD"], in: root))
            .flatMap { $0.trimmingCharacters(in: .whitespacesAndNewlines) } ?? "unknown"

        let statusOutput = (try? await run(["status", "--porcelain", "-u"], in: root)) ?? ""
        parseStatus(statusOutput ?? "", root: root)

        let logOutput = (try? await run([
            "log", "--oneline", "--pretty=format:%H|%h|%s|%an|%ar", "-n", "20"
        ], in: root)) ?? ""
        parseLog(logOutput ?? "")
    }

    // MARK: - Gutter diff for a specific file

    func gutterMarks(for url: URL) async -> [GutterMark] {
        guard let root else { return [] }
        guard let diffOutput = try? await run(
            ["diff", "--unified=0", url.path], in: root
        ) else { return [] }
        return parseGutterMarks(from: diffOutput ?? "")
    }

    // MARK: - Staging & Commit

    @discardableResult
    func stageAll() async throws -> String {
        guard let root else { throw GitError.noRoot }
        return try await run(["add", "-A"], in: root) ?? ""
    }

    @discardableResult
    func stageFile(_ url: URL) async throws -> String {
        guard let root else { throw GitError.noRoot }
        return try await run(["add", url.path], in: root) ?? ""
    }

    @discardableResult
    func unstageFile(_ url: URL) async throws -> String {
        guard let root else { throw GitError.noRoot }
        return try await run(["reset", "HEAD", url.path], in: root) ?? ""
    }

    func commit(message: String) async throws -> String {
        guard let root else { throw GitError.noRoot }
        guard !message.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw GitError.emptyMessage
        }
        let result = try await run(["commit", "-m", message], in: root)
        await refresh()
        return result ?? ""
    }

    func push() async throws -> String {
        guard let root else { throw GitError.noRoot }
        return try await run(["push", "origin", "HEAD"], in: root) ?? ""
    }

    func pull() async throws -> String {
        guard let root else { throw GitError.noRoot }
        let result = try await run(["pull", "--rebase"], in: root)
        await refresh()
        return result ?? ""
    }

    func createBranch(_ name: String) async throws -> String {
        guard let root else { throw GitError.noRoot }
        return try await run(["checkout", "-b", name], in: root) ?? ""
    }

    func switchBranch(_ name: String) async throws -> String {
        guard let root else { throw GitError.noRoot }
        let result = try await run(["checkout", name], in: root)
        await refresh()
        return result ?? ""
    }

    func branches() async -> [String] {
        guard let root else { return [] }
        let output = (try? await run(["branch", "--format=%(refname:short)"], in: root)) ?? ""
        return (output ?? "").components(separatedBy: "\n").filter { !$0.isEmpty }
    }

    // MARK: - Private parsers

    private func parseStatus(_ output: String, root: URL) {
        var staged: [FileStat] = []
        var unstaged: [FileStat] = []

        for line in output.components(separatedBy: "\n") where line.count >= 3 {
            let xy = Array(line.prefix(2))
            let rawPath = String(line.dropFirst(3))
            let path = rawPath.trimmingCharacters(in: .whitespaces)

            let indexStatus = FileStat.FileStatus(rawValue: String(xy[0])) ?? .unknown
            let workStatus  = FileStat.FileStatus(rawValue: String(xy[1])) ?? .unknown

            if indexStatus != .unknown && indexStatus.rawValue != " " {
                staged.append(FileStat(id: "s-\(path)", path: path, status: indexStatus))
            }
            if workStatus != .unknown && workStatus.rawValue != " " && workStatus.rawValue != "?" {
                unstaged.append(FileStat(id: "u-\(path)", path: path, status: workStatus))
            } else if xy[0] == "?" && xy[1] == "?" {
                unstaged.append(FileStat(id: "u-\(path)", path: path, status: .untracked))
            }
        }

        DispatchQueue.main.async {
            self.stagedFiles   = staged
            self.unstagedFiles = unstaged
        }
    }

    private func parseLog(_ output: String) {
        let entries = output.components(separatedBy: "\n").compactMap { line -> CommitLog? in
            let parts = line.split(separator: "|", maxSplits: 4, omittingEmptySubsequences: false)
            guard parts.count == 5 else { return nil }
            return CommitLog(
                id: String(parts[0]),
                hash: String(parts[0]),
                shortHash: String(parts[1]),
                message: String(parts[2]),
                author: String(parts[3]),
                date: String(parts[4])
            )
        }
        DispatchQueue.main.async { self.commitLog = entries }
    }

    private func parseGutterMarks(from diff: String) -> [GutterMark] {
        // Parse unified diff hunk headers: @@ -a,b +c,d @@
        var marks: [GutterMark] = []
        let hunkPattern = try? NSRegularExpression(pattern: #"@@\s+-\d+(?:,\d+)?\s+\+(\d+)(?:,(\d+))?\s+@@"#)
        var currentNewLine = 0

        for line in diff.components(separatedBy: "\n") {
            if line.hasPrefix("@@") {
                if let match = hunkPattern?.firstMatch(in: line, range: NSRange(line.startIndex..., in: line)),
                   let r1 = Range(match.range(at: 1), in: line) {
                    currentNewLine = Int(line[r1]) ?? 0
                }
            } else if line.hasPrefix("+") {
                marks.append(GutterMark(id: currentNewLine, lineNumber: currentNewLine, kind: .added))
                currentNewLine += 1
            } else if line.hasPrefix("-") {
                marks.append(GutterMark(id: -currentNewLine, lineNumber: currentNewLine, kind: .deleted))
                // deleted lines don't advance new-file line count
            } else if !line.hasPrefix("\\") {
                currentNewLine += 1
            }
        }
        return marks
    }

    // MARK: - Process runner

    @discardableResult
    private func run(_ args: [String], in directory: URL) async throws -> String? {
        try await withCheckedThrowingContinuation { cont in
            DispatchQueue.global(qos: .userInitiated).async {
                do {
                    let proc = Process()
                    let pipe = Pipe()
                    proc.executableURL = URL(fileURLWithPath: "/usr/bin/git")
                    proc.arguments = args
                    proc.currentDirectoryURL = directory
                    proc.standardOutput = pipe
                    proc.standardError = pipe
                    try proc.run()
                    // ⚠️ readDataToEndOfFile → waitUntilExit の順序厳守。
                    // terminationHandler 内で読むと race condition が起きる。
                    let data = pipe.fileHandleForReading.readDataToEndOfFile()
                    proc.waitUntilExit()
                    let output = String(data: data, encoding: .utf8) ?? ""
                    if proc.terminationStatus == 0 {
                        cont.resume(returning: output)
                    } else {
                        cont.resume(throwing: GitError.processError(output))
                    }
                } catch {
                    cont.resume(throwing: error)
                }
            }
        }
    }

    // MARK: - Errors

    enum GitError: LocalizedError {
        case noRoot
        case emptyMessage
        case processError(String)

        var errorDescription: String? {
            switch self {
            case .noRoot:          return "No workspace root"
            case .emptyMessage:    return "Commit message cannot be empty"
            case .processError(let s): return s.isEmpty ? "Git command failed" : s
            }
        }
    }
}
