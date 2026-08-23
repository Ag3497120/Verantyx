import Foundation
import AppKit

// MARK: - WorkspaceManager
// NSOpenPanel-based file I/O. No sandbox — full filesystem access.

final class WorkspaceManager {

    // MARK: - Folder picker (NSOpenPanel)

    func pickFolder() -> URL? {
        let panel = NSOpenPanel()
        panel.title = "Open Workspace Folder"
        panel.message = "Select your project folder. Verantyx will have full read/write access."
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        panel.canCreateDirectories = false
        panel.prompt = "Open"

        guard panel.runModal() == .OK else { return nil }
        return panel.url
    }

    // MARK: - Directory scan (sync — legacy)

    func listFiles(in root: URL, extensions: [String]) -> [URL] {
        _scanDirectory(root: root, extensions: Set(extensions.map { $0.lowercased() }))
    }

    // MARK: - Directory scan (async — preferred)

    func listFilesAsync(in root: URL, extensions: [String]) async -> [URL] {
        _scanDirectory(root: root, extensions: Set(extensions.map { $0.lowercased() }))
    }

    // MARK: - Streaming scan (VS Code-style: progressive results)
    //
    // Returns an AsyncStream that yields sorted batches as files are found.
    // AppState can update workspaceFiles after each batch so the tree appears
    // within milliseconds even for large repositories.

    func scanStreaming(in root: URL, extensions: Set<String>) -> AsyncStream<[URL]> {
        AsyncStream { continuation in
            Task.detached(priority: .userInitiated) {
                var accumulated: [URL] = []
                accumulated.reserveCapacity(1_000)
                var batchBuffer: [URL] = []
                batchBuffer.reserveCapacity(200)

                let batchSize  = 150          // yield to UI every N new files found
                let maxFiles   = 5_000        // hard cap — stop after this many files
                let deadline   = Date().addingTimeInterval(8.0)  // 8 second timeout

                self._scanDirectory(
                    root: root,
                    extensions: extensions,
                    onFile: { url in
                        guard accumulated.count < maxFiles, Date() < deadline else { return }
                        accumulated.append(url)
                        batchBuffer.append(url)
                        if batchBuffer.count >= batchSize {
                            let snapshot = accumulated.sorted { $0.path < $1.path }
                            continuation.yield(snapshot)
                            batchBuffer.removeAll(keepingCapacity: true)
                        }
                    }
                )

                // Final sorted result
                let final = accumulated.sorted { $0.path < $1.path }
                continuation.yield(final)
                continuation.finish()
            }
        }
    }

    // MARK: - Core scanner

    /// Heavy directories that should NEVER be descended into.
    private static let skipDirNames: Set<String> = [
        // JavaScript / Node
        "node_modules", ".npm", ".yarn", ".pnpm",
        // Rust
        "target",
        // Swift Package Manager
        ".build",
        // Xcode
        "DerivedData", "xcuserdata",
        // Python
        "__pycache__", "venv", ".venv", "env", ".env",
        "eggs", ".eggs", ".mypy_cache", ".pytest_cache", ".tox",
        "site-packages", "dist-packages",
        // Java / Android / Gradle
        ".gradle", ".idea", "bin", "obj",
        // iOS/macOS
        "Pods", "Carthage",
        // Web bundlers
        "dist", ".next", ".nuxt", ".output", ".svelte-kit",
        // Generic build/coverage/cache
        "build", "coverage", ".cache", ".parcel-cache", ".turbo",
        // Git LFS object store (can be huge)
        "lfs",
        // Firebase / cloud
        ".firebase",
        // ML / datasets
        "__MACOSX", ".DS_Store",
    ]
    // Note: .skipsHiddenFiles already handles .git, .svn, .hg, etc.

    /// Scan `root` recursively, calling `onFile` for each matching file.
    /// Dispatches to `Task.detached` so it never touches the main thread.
    ///
    /// The key optimization is `enumerator.skipDescendants()` on ignored directories:
    /// it prevents the enumerator from ever entering that subtree, regardless of size.
    private func _scanDirectory(
        root: URL,
        extensions: Set<String>,
        onFile: ((URL) -> Void)? = nil
    ) -> [URL] {
        var results: [URL] = []
        let fm = FileManager.default

        guard let enumerator = fm.enumerator(
            at: root,
            // Pre-fetch isRegularFile + isDirectory so resourceValues() below is O(1) (cache hit)
            includingPropertiesForKeys: [.isRegularFileKey, .isDirectoryKey],
            options: [.skipsHiddenFiles, .skipsPackageDescendants]
        ) else { return [] }

        for case let url as URL in enumerator {
            let name = url.lastPathComponent

            // ── Skip heavy build/dependency directories ────────────────────────
            // This is the KEY fix: instead of visiting every file inside `target/`
            // (which can be 200k+ files), we skip the entire subtree instantly.
            if Self.skipDirNames.contains(name) {
                enumerator.skipDescendants()
                continue
            }

            // ── Directory / File Check ─────────────────────────────────────────
            // `try? url.resourceValues` can throw obscure errors on macOS 14+ (e.g. for symlinks or cloud files).
            // Fall back to a robust check if it fails.
            var isDir = false
            var isRegularFile = false

            if let vals = try? url.resourceValues(forKeys: [.isRegularFileKey, .isDirectoryKey]) {
                isDir = vals.isDirectory == true
                isRegularFile = vals.isRegularFile == true
            } else {
                var objcIsDir: ObjCBool = false
                if fm.fileExists(atPath: url.path, isDirectory: &objcIsDir) {
                    isDir = objcIsDir.boolValue
                    isRegularFile = !isDir
                }
            }

            if isDir { continue }   // skip dir entries, we already handled skipDescendants above
            guard isRegularFile else { continue }

            // ── Extension filter ───────────────────────────────────────────────
            let ext = url.pathExtension.lowercased()
            if extensions.contains(ext) || (ext.isEmpty && extensions.contains(name.lowercased())) {
                results.append(url)
                onFile?(url)
            }
        }

        return results
    }

    // MARK: - File I/O

    func read(_ url: URL) -> String? {
        try? String(contentsOf: url, encoding: .utf8)
    }

    func write(_ url: URL, content: String) throws {
        try content.write(to: url, atomically: true, encoding: .utf8)
    }

    // MARK: - Relative path helper

    func relativePath(of url: URL, from root: URL) -> String {
        let full = url.path
        let base = root.path
        if full.hasPrefix(base) {
            return String(full.dropFirst(base.count + 1))
        }
        return url.lastPathComponent
    }
}
