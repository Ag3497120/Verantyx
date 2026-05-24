import Foundation

// MARK: - SearchEngine
// Global project search using ripgrep (preferred) or git-grep (fallback).
// Streams results progressively via AsyncStream so the UI updates live.

final class ProjectSearchEngine: ObservableObject {

    // MARK: - Result model

    struct SearchResult: Identifiable, Equatable {
        let id: UUID
        let file: URL
        let lineNumber: Int
        let lineContent: String
        let matchRange: Range<String.Index>?

        var displayPath: String { file.lastPathComponent }
        var contextSnippet: String {
            let trimmed = lineContent.trimmingCharacters(in: .whitespaces)
            return trimmed.count > 120 ? String(trimmed.prefix(120)) + "…" : trimmed
        }
    }

    struct FileGroup: Identifiable {
        let id: URL
        var file: URL { id }
        var results: [SearchResult]
    }

    // MARK: - State

    @Published var query: String = ""
    @Published var groups: [FileGroup] = []
    @Published var totalMatches: Int = 0
    @Published var isSearching: Bool = false
    @Published var errorMessage: String? = nil

    private var accumulated: [URL: [SearchResult]] = [:]
    private var searchTask: Task<Void, Never>? = nil
    private static let rgPath: String = {
        // Common Homebrew paths
        for path in ["/opt/homebrew/bin/rg", "/usr/local/bin/rg", "/usr/bin/rg"] {
            if FileManager.default.fileExists(atPath: path) { return path }
        }
        return ""
    }()

    // MARK: - Public API

    /// Start a new search. Cancels any in-flight search first.
    func search(query: String, in root: URL,
                caseSensitive: Bool = false,
                regex: Bool = false,
                filePattern: String? = nil) {
        guard !query.trimmingCharacters(in: .whitespaces).isEmpty else {
            clear(); return
        }

        searchTask?.cancel()
        isSearching = true
        groups = []
        accumulated = [:]
        totalMatches = 0
        errorMessage = nil

        searchTask = Task(priority: .userInitiated) { [weak self] in
            guard let self else { return }

            let stream: AsyncStream<SearchResult>
            if !Self.rgPath.isEmpty {
                stream = self.ripgrepStream(query: query, root: root,
                                             caseSensitive: caseSensitive,
                                             regex: regex,
                                             filePattern: filePattern)
            } else {
                stream = self.gitGrepStream(query: query, root: root,
                                             caseSensitive: caseSensitive)
            }

            for await result in stream {
                guard !Task.isCancelled else { break }

                await MainActor.run {
                    self.accumulated[result.file, default: []].append(result)
                    self.totalMatches += 1

                    // Rebuild groups sorted by file path
                    self.groups = self.accumulated
                        .sorted { $0.key.path < $1.key.path }
                        .map { FileGroup(id: $0.key, results: $0.value) }
                }
            }

            await MainActor.run { self.isSearching = false }
        }
    }

    func cancel() {
        searchTask?.cancel()
        isSearching = false
    }

    func clear() {
        searchTask?.cancel()
        groups = []
        totalMatches = 0
        isSearching = false
        errorMessage = nil
    }

    // MARK: - ripgrep backend

    private func ripgrepStream(query: String, root: URL,
                                caseSensitive: Bool,
                                regex: Bool,
                                filePattern: String?) -> AsyncStream<SearchResult> {
        AsyncStream { continuation in
            let process = Process()
            let pipe = Pipe()

            process.executableURL = URL(fileURLWithPath: Self.rgPath)
            process.currentDirectoryURL = root

            var args = [
                "--line-number",
                "--no-heading",
                "--color", "never",
                "--max-count", "50",       // max 50 matches per file
                "--max-filesize", "2M",    // skip binary/huge files
            ]
            if !caseSensitive { args.append("--ignore-case") }
            if !regex { args.append("--fixed-strings") }
            if let pat = filePattern, !pat.isEmpty { args += ["--glob", pat] }
            args.append(query)
            args.append(".")

            process.arguments = args
            process.standardOutput = pipe
            process.standardError = Pipe() // discard stderr

            do {
                try process.run()
            } catch {
                continuation.finish()
                return
            }

            // Read output line by line
            let handle = pipe.fileHandleForReading
            var buffer = Data()

            handle.readabilityHandler = { fh in
                let chunk = fh.availableData
                if chunk.isEmpty {
                    // Parse remaining buffer
                    if !buffer.isEmpty, let line = String(data: buffer, encoding: .utf8) {
                        if let r = Self.parseRgLine(line, root: root) { continuation.yield(r) }
                    }
                    continuation.finish()
                    handle.readabilityHandler = nil
                    return
                }
                buffer.append(chunk)
                while let nl = buffer.firstIndex(of: UInt8(ascii: "\n")) {
                    let lineData = buffer[buffer.startIndex...nl]
                    buffer = buffer[buffer.index(after: nl)...]
                    if let line = String(data: lineData, encoding: .utf8) {
                        if let r = Self.parseRgLine(line.trimmingCharacters(in: .newlines), root: root) {
                            continuation.yield(r)
                        }
                    }
                }
            }

            process.terminationHandler = { _ in
                // handled by readabilityHandler empty-data signal
            }

            continuation.onTermination = { _ in
                if process.isRunning { process.terminate() }
            }
        }
    }

    // MARK: - git grep fallback

    private func gitGrepStream(query: String, root: URL,
                                caseSensitive: Bool) -> AsyncStream<SearchResult> {
        AsyncStream { continuation in
            let process = Process()
            let pipe = Pipe()
            process.executableURL = URL(fileURLWithPath: "/usr/bin/git")
            process.currentDirectoryURL = root
            var args = ["grep", "--line-number", "--color=never"]
            if !caseSensitive { args.append("-i") }
            args += ["-e", query]
            process.arguments = args
            process.standardOutput = pipe
            process.standardError = FileHandle.nullDevice  // ⚠️ stderr は不要 — 未読パイプの deadlock 防止

            guard (try? process.run()) != nil else { continuation.finish(); return }

            let output = pipe.fileHandleForReading.readDataToEndOfFile()
            process.waitUntilExit()

            if let text = String(data: output, encoding: .utf8) {
                for line in text.components(separatedBy: "\n") {
                    if let r = Self.parseGitGrepLine(line, root: root) {
                        continuation.yield(r)
                    }
                }
            }
            continuation.finish()
        }
    }

    // MARK: - Line parsers

    /// rg format: relative/path/to/file.swift:42:content of the line
    private static func parseRgLine(_ line: String, root: URL) -> SearchResult? {
        let parts = line.split(separator: ":", maxSplits: 2, omittingEmptySubsequences: false)
        guard parts.count >= 3,
              let lineNum = Int(parts[1]) else { return nil }
        let relativePath = String(parts[0])
        let content = String(parts[2])
        let fileURL = root.appendingPathComponent(relativePath)
        return SearchResult(id: UUID(), file: fileURL, lineNumber: lineNum,
                            lineContent: content, matchRange: nil)
    }

    /// git grep format: relative/path/to/file.swift:42:content
    private static func parseGitGrepLine(_ line: String, root: URL) -> SearchResult? {
        let parts = line.split(separator: ":", maxSplits: 2, omittingEmptySubsequences: false)
        guard parts.count >= 3, let lineNum = Int(parts[1]) else { return nil }
        let relativePath = String(parts[0])
        let content = String(parts[2])
        let fileURL = root.appendingPathComponent(relativePath)
        return SearchResult(id: UUID(), file: fileURL, lineNumber: lineNum,
                            lineContent: content, matchRange: nil)
    }
}
