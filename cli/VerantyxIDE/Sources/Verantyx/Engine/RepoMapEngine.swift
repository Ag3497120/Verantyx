import Foundation

// MARK: - RepoMapEngine
//
// Generates a compact "mini RepoMap" of the current workspace that is:
//   1. Injected into the system prompt (hardcoded at top, always visible — not lost-in-middle)
//   2. Also indexed as JCross L1 nodes in CortexEngine (semantic kanji topology)
//
// This solves The Attention Wall (壁1) by:
//   - Eliminating the need for the agent to waste a turn calling [LIST_DIR]
//   - Providing symbol-level awareness without raw Ctags dumps
//   - Using JCross L1 for cross-session structural memory
//
// Strategy:
//   - Scan workspace for source files (.swift, .ts, .py, .js, .go, .rs, .kt, …)
//   - Extract top-level symbols (class, struct, func, def, fn, interface) via regex
//   - Build a compact tree: "  dir/File.swift: MyClass, myFunc, otherFunc"
//   - Store as JCross L1 (kanji topology) nodes in CortexEngine
//   - Return a short prompt-injectable string (target: < 500 tokens)

actor RepoMapEngine {

    static let shared = RepoMapEngine()

    // File types to scan and their language identifier
    private let sourceExtensions: [String: String] = [
        "swift": "Swift", "ts": "TypeScript", "tsx": "TSX",
        "js": "JavaScript", "jsx": "JSX", "py": "Python",
        "go": "Go", "rs": "Rust", "kt": "Kotlin",
        "java": "Java", "cpp": "C++", "c": "C",
        "rb": "Ruby", "cs": "C#", "html": "HTML", "css": "CSS", "json": "JSON"
    ]

    // Folders to skip unconditionally
    private let skipFolders: Set<String> = [
        ".git", "node_modules", ".build", "DerivedData", ".swp",
        "__pycache__", "dist", "build", "vendor", ".next", "Pods"
    ]

    // Max files to scan (防衛: too-large repos still produce a quick map)
    private let maxFiles = 120
    // Max symbols per file to show in the map
    private let maxSymbolsPerFile = 6

    // ── Cache: avoid re-scanning if workspace hasn't changed ──────────────
    private var cachedWorkspaceURL: URL?
    private var cachedMapString: String = ""
    private var cachedBuildTime: Date = .distantPast
    private let cacheTTL: TimeInterval = 30   // seconds

    // MARK: - Public API

    /// Build (or return cached) mini RepoMap for injection into system prompt.
    /// Also indexes all files as JCross L1 nodes in CortexEngine.
    @discardableResult
    func buildRepoMap(
        workspace: URL,
        cortex: CortexEngine?
    ) async -> String {
        // Cache hit
        if cachedWorkspaceURL == workspace,
           Date().timeIntervalSince(cachedBuildTime) < cacheTTL,
           !cachedMapString.isEmpty {
            return cachedMapString
        }

        let files = scanWorkspace(at: workspace)
        guard !files.isEmpty else {
            return ""
        }

        var lines: [String] = []
        var jcrossNodes: [(path: String, symbols: [String], lang: String)] = []

        let workspacePath = workspace.path

        for file in files.prefix(maxFiles) {
            let ext  = file.pathExtension.lowercased()
            let lang = sourceExtensions[ext] ?? ext.uppercased()
            let rel  = relativePath(of: file, from: workspace)

            let symbols = extractSymbols(from: file, language: lang)
            let symStr  = symbols.prefix(maxSymbolsPerFile).joined(separator: ", ")
            let lineStr = symStr.isEmpty ? "  \(rel)" : "  \(rel): \(symStr)"
            lines.append(lineStr)

            jcrossNodes.append((path: rel, symbols: symbols, lang: lang))
        }

        // ── Inject into JCross L1 (kanji topology) ──────────────────────
        if let cortex = cortex {
            await index(files: jcrossNodes, workspace: workspacePath, cortex: cortex)
        }

        let fileCount = min(files.count, maxFiles)
        let truncNote = files.count > maxFiles ? " (showing \(maxFiles) of \(files.count))" : ""
        let header    = "[REPO MAP — workspace: \(workspace.lastPathComponent), \(fileCount) files\(truncNote)]"
        let footer    = "[/REPO MAP]"
        let mapString = ([header] + lines + [footer]).joined(separator: "\n")

        cachedWorkspaceURL = workspace
        cachedMapString    = mapString
        cachedBuildTime    = Date()
        return mapString
    }

    /// Build only the compact L1 summary string (no disk scan) from existing cortex nodes.
    /// Used when workspace hasn't changed but we want the L1 kanji index for recall.
    func buildRepoMapFromL1(cortex: CortexEngine, query: String) async -> String {
        let nodes = await cortex.recall(for: "repomap \(query)", topK: 8)
        guard !nodes.isEmpty else { return "" }
        let facts = nodes.map { "  [\($0.kanjiTags.joined())] \($0.key): \($0.value)" }
            .joined(separator: "\n")
        return "[REPO MAP — JCross L1]\n\(facts)\n[/REPO MAP]"
    }

    // MARK: - File system scan

    private func scanWorkspace(at root: URL) -> [URL] {
        var results: [URL] = []
        let fm = FileManager.default
        let supportedExts = Set(sourceExtensions.keys)

        guard let enumerator = fm.enumerator(
            at: root,
            includingPropertiesForKeys: [.isRegularFileKey, .fileSizeKey],
            options: [.skipsHiddenFiles, .skipsPackageDescendants]
        ) else { return [] }

        for case let file as URL in enumerator {
            let components = file.pathComponents
            if components.contains(where: { skipFolders.contains($0) }) { continue }

            guard let vals = try? file.resourceValues(forKeys: [.isRegularFileKey, .fileSizeKey]),
                  vals.isRegularFile == true,
                  let size = vals.fileSize, size < 500_000  // skip huge generated files
            else { continue }

            guard supportedExts.contains(file.pathExtension.lowercased()) else { continue }
            results.append(file)

            if results.count >= maxFiles { break }
        }
        return results.sorted { $0.path < $1.path }
    }

    // MARK: - Symbol extraction (lightweight regex — no AST)

    private func extractSymbols(from url: URL, language: String) -> [String] {
        guard let content = try? String(contentsOf: url, encoding: .utf8) else { return [] }
        // Only scan first 8 KB for speed
        let preview = String(content.prefix(8192))
        return symbolPatterns(for: language)
            .flatMap { regex -> [String] in
                guard let r = try? NSRegularExpression(pattern: regex) else { return [] }
                let ms = r.matches(in: preview, range: NSRange(preview.startIndex..., in: preview))
                return ms.compactMap { m -> String? in
                    guard m.numberOfRanges > 1,
                          let r1 = Range(m.range(at: 1), in: preview)
                    else { return nil }
                    return String(preview[r1])
                }
            }
    }

    private func symbolPatterns(for language: String) -> [String] {
        switch language {
        case "Swift":
            return [
                #"(?:class|struct|enum|protocol|actor)\s+(\w+)"#,
                #"(?:func)\s+(\w+)\s*[\(<]"#
            ]
        case "TypeScript", "TSX", "JavaScript", "JSX":
            return [
                #"(?:class|interface)\s+(\w+)"#,
                #"(?:function|const|let|var)\s+(\w+)\s*(?:=\s*(?:async\s*)?\(?|[(<])"#,
                #"export\s+(?:default\s+)?(?:function|class)\s+(\w+)"#
            ]
        case "Python":
            return [
                #"(?:class|def)\s+(\w+)"#
            ]
        case "Go":
            return [
                #"(?:func|type)\s+(\w+)"#
            ]
        case "Rust":
            return [
                #"(?:pub\s+)?(?:fn|struct|enum|trait|impl)\s+(\w+)"#
            ]
        case "Kotlin":
            return [
                #"(?:class|fun|object|interface)\s+(\w+)"#
            ]
        case "Java", "C#":
            return [
                #"(?:class|interface|enum)\s+(\w+)"#,
                #"(?:public|private|protected)?\s+\w+\s+(\w+)\s*\("#
            ]
        default:
            return []
        }
    }

    // MARK: - JCross L1 indexing

    /// Store each source file as a JCross front-zone memory node
    /// with kanji topology derived from the file's language and symbols.
    private func index(
        files: [(path: String, symbols: [String], lang: String)],
        workspace: String,
        cortex: CortexEngine
    ) async {
        for item in files {
            let key   = "repomap:\(item.path)"
            let value = item.symbols.isEmpty
                ? "[\(item.lang)] (no top-level symbols)"
                : "[\(item.lang)] \(item.symbols.prefix(6).joined(separator: ", "))"

            // Importance: higher for files with more symbols (likely core files)
            let importance: Float = item.symbols.count > 4 ? 0.85 : 0.7

            // Build kanji tags from language + symbols count
            let kanjiTags = inferL1KanjiTags(lang: item.lang, symbols: item.symbols)

            await cortex.remember(
                key: key,
                value: value,
                importance: importance,
                zone: .front,
                kanjiTags: kanjiTags
            )
        }
    }

    /// Kanji tag derivation for L1 topology.
    /// Maps language + code patterns to semantic kanji vectors.
    private func inferL1KanjiTags(lang: String, symbols: [String]) -> [String] {
        var tags: [String] = []

        // Language → primary kanji
        switch lang {
        case "Swift":          tags.append("技")  // 技術 (technology)
        case "Python":         tags.append("算")  // 計算 (computation)
        case "TypeScript", "JavaScript", "TSX", "JSX":
                               tags.append("網")  // ネット (web/network)
        case "Go":             tags.append("速")  // 速度 (speed)
        case "Rust":           tags.append("堅")  // 堅牢 (robustness)
        case "Kotlin", "Java": tags.append("台")  // プラットフォーム (platform)
        case "HTML", "CSS":    tags.append("画")  // 画面 (screen/UI)
        case "JSON":           tags.append("標")  // 標準 (standard)
        default:               tags.append("技")
        }

        // Symbol pattern → secondary kanji
        let allSymbols = symbols.map { $0.lowercased() }.joined(separator: " ")
        if allSymbols.contains("view") || allSymbols.contains("ui")
            || allSymbols.contains("screen") || allSymbols.contains("widget") {
            tags.append("画")   // UI
        }
        if allSymbols.contains("model") || allSymbols.contains("state")
            || allSymbols.contains("store") || allSymbols.contains("data") {
            tags.append("模")   // 模型 (model/data)
        }
        if allSymbols.contains("engine") || allSymbols.contains("runner")
            || allSymbols.contains("service") || allSymbols.contains("manager") {
            tags.append("核")   // 核心 (core)
        }
        if allSymbols.contains("test") || allSymbols.contains("spec")
            || allSymbols.contains("bench") {
            tags.append("験")   // 実験 (experiment/test)
        }
        if allSymbols.contains("agent") || allSymbols.contains("loop")
            || allSymbols.contains("worker") {
            tags.append("律")   // 自律 (autonomy)
        }

        return Array(Set(tags)).prefix(4).sorted()   // dedupe + cap at 4
    }

    // MARK: - Relative path helper

    private func relativePath(of url: URL, from root: URL) -> String {
        let full = url.path
        let base = root.path
        if full.hasPrefix(base) {
            return String(full.dropFirst(base.count + 1))
        }
        return url.lastPathComponent
    }
}

// MARK: - CortexEngine extension (kanjiTags override in remember)

extension CortexEngine {
    /// remember() overload that accepts explicit kanjiTags for L1 control.
    func remember(
        key: String,
        value: String,
        importance: Float = 0.5,
        zone: MemoryNode.Zone? = nil,
        kanjiTags: [String]
    ) {
        guard isEnabled else { return }
        let resolvedZone = zone ?? classifyNode(importance: importance)

        if let idx = nodes.firstIndex(where: { $0.key == key }) {
            nodes[idx].value       = value
            nodes[idx].importance  = max(nodes[idx].importance, importance)
            nodes[idx].accessCount += 1
            nodes[idx].kanjiTags   = kanjiTags
            if resolvedZone == .front && nodes[idx].zone != .front {
                migrateNode(&nodes[idx], to: .front)
            }
            writeNode(nodes[idx])
        } else {
            let node = MemoryNode(
                key: key, value: value,
                importance: importance,
                zone: resolvedZone,
                kanjiTags: kanjiTags
            )
            nodes.append(node)
            writeNode(node)
        }
        runLRUGC()
    }
}
