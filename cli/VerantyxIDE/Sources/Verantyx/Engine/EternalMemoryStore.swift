import Foundation

/// Swift-owned port of `verantyx_mind.py`'s `CortexMemory` (Milestone C).
/// Both writing and reading eternal memory in the Python original use the
/// SAME `jcross_engine_encode` hidden state already wrapped by
/// `JCrossEngine.encode()`/`JCrossChatManager.encodeText()` -- there is no
/// separate embedding model, so this store just needs cosine search + a
/// gravity-decay re-ranking on top of vectors JCrossChatManager already
/// knows how to produce.
///
/// Deliberately a **separate storage pool** from the Python CLI's
/// `.verantyx_chrono/` (decided explicitly, not a placeholder) -- avoids
/// any risk of a format mismatch corrupting the Python tool's memory, at
/// the cost of the IDE and CLI not sharing recall.
///
/// Simplifications vs. `CortexMemory`: no legacy-v2 migration, no L1
/// axis-signature pre-filter (an optimization for very large stores, not
/// needed at this store's expected scale).
actor EternalMemoryStore {
    static let shared = EternalMemoryStore()

    private static let dim = 1024
    private static let gravityHalfLifeDays: Double = 30.0

    private struct Node: Codable {
        let id: Int
        let ts: Double
        var text: String
        var concepts: [String]
        var accessCount: Int
        var lastAccess: Double
    }

    private let directory: URL
    private var vectorsURL: URL { directory.appendingPathComponent("cortex.vectors") }
    private var nodesURL: URL { directory.appendingPathComponent("cortex.nodes.jsonl") }

    private var nodes: [Node] = []
    private var loaded = false

    private init() {
        let home = FileManager.default.homeDirectoryForCurrentUser
        directory = home.appendingPathComponent(".verantyx_chrono_swift", isDirectory: true)
    }

    private func ensureLoaded() throws {
        guard !loaded else { return }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        if let data = FileManager.default.contents(atPath: nodesURL.path),
           let text = String(data: data, encoding: .utf8) {
            nodes = text.split(separator: "\n").compactMap { line in
                guard let d = line.data(using: .utf8) else { return nil }
                return try? JSONDecoder().decode(Node.self, from: d)
            }
        }
        loaded = true
    }

    /// Builds the same PromptEOL wrapper prompt as `embed_text()`, then
    /// forwards it through the JGEN engine and L2-normalizes -- the same
    /// vector space used for both writes and reads.
    private func embed(_ text: String) async throws -> [Float] {
        // Cap before wrapping — encodeText also truncates, but the PromptEOL
        // wrapper would otherwise re-inflate a huge quote into the prompt.
        let clipped = PromptBudget.truncateForEncode(text)
        let prompt = "This sentence: \"\(clipped)\" means in one word:\""
        let raw = try await JCrossChatManager.shared.encodeText(prompt)
        return Self.l2Normalize(raw)
    }

    private static func l2Normalize(_ v: [Float]) -> [Float] {
        let norm = sqrt(v.reduce(Float(0)) { $0 + $1 * $1 })
        guard norm > 0 else { return v }
        return v.map { $0 / norm }
    }

    private static func fitVec(_ v: [Float]) -> [Float] {
        if v.count == dim { return v }
        if v.count > dim { return Array(v.prefix(dim)) }
        return v + [Float](repeating: 0, count: dim - v.count)
    }

    /// Embeds `text` and appends it as a new eternal-memory node. Call after
    /// a completed Council deliberation (consensus text) or, optionally, a
    /// plain JGEN chat turn.
    func add(text: String, concepts: [String]) async throws {
        try ensureLoaded()
        let vec = Self.fitVec(try await embed(text))

        var fp16Bytes = Data(capacity: vec.count * 2)
        for f in vec {
            var half = Float16(f)
            withUnsafeBytes(of: &half) { fp16Bytes.append(contentsOf: $0) }
        }
        if let handle = FileHandle(forWritingAtPath: vectorsURL.path) {
            handle.seekToEndOfFile()
            handle.write(fp16Bytes)
            handle.closeFile()
        } else {
            FileManager.default.createFile(atPath: vectorsURL.path, contents: fp16Bytes)
        }

        let node = Node(
            id: nodes.count, ts: Date().timeIntervalSince1970, text: text,
            concepts: concepts, accessCount: 0, lastAccess: Date().timeIntervalSince1970
        )
        nodes.append(node)
        try appendNodeLine(node)
    }

    private func appendNodeLine(_ node: Node) throws {
        var data = try JSONEncoder().encode(node)
        data.append(contentsOf: "\n".utf8)
        if let handle = FileHandle(forWritingAtPath: nodesURL.path) {
            handle.seekToEndOfFile()
            handle.write(data)
            handle.closeFile()
        } else {
            FileManager.default.createFile(atPath: nodesURL.path, contents: data)
        }
    }

    private func rewriteIndex() throws {
        var out = Data()
        for node in nodes {
            var data = try JSONEncoder().encode(node)
            data.append(contentsOf: "\n".utf8)
            out.append(data)
        }
        try out.write(to: nodesURL, options: .atomic)
    }

    private func loadVector(at index: Int) -> [Float]? {
        guard let handle = FileHandle(forReadingAtPath: vectorsURL.path) else { return nil }
        defer { handle.closeFile() }
        let byteOffset = UInt64(index * Self.dim * 2)
        handle.seek(toFileOffset: byteOffset)
        guard let data = try? handle.read(upToCount: Self.dim * 2), data.count == Self.dim * 2 else { return nil }
        var out = [Float](repeating: 0, count: Self.dim)
        data.withUnsafeBytes { raw in
            let half = raw.bindMemory(to: Float16.self)
            for i in 0..<Self.dim { out[i] = Float(half[i]) }
        }
        return out
    }

    private func gravity(daysSinceAccess: Double, accessCount: Int) -> Double {
        let halfLife = Self.gravityHalfLifeDays * Double(1 + accessCount)
        guard halfLife > 0 else { return 1 }
        return pow(0.5, daysSinceAccess / halfLife)
    }

    /// Port of `CortexMemory.search`: cosine similarity against all stored
    /// vectors, re-ranked by a recency/access-count gravity decay, top-K
    /// returned. Bumps `accessCount`/`lastAccess` on each hit (full JSONL
    /// rewrite, matching the Python original's `_rewrite_index`).
    func search(query: String, k: Int) async throws -> [(text: String, score: Float)] {
        try ensureLoaded()
        guard !nodes.isEmpty else { return [] }
        let qv = Self.fitVec(try await embed(query))

        var scored: [(index: Int, eff: Float, sim: Float)] = []
        let now = Date().timeIntervalSince1970
        for (i, node) in nodes.enumerated() {
            guard let vec = loadVector(at: i) else { continue }
            var dot: Float = 0
            for j in 0..<Self.dim { dot += vec[j] * qv[j] }
            let daysSince = max((now - node.lastAccess) / 86400.0, 0)
            let grav = Float(gravity(daysSinceAccess: daysSince, accessCount: node.accessCount))
            let eff = dot * (0.7 + 0.3 * grav)
            scored.append((i, eff, dot))
        }
        scored.sort { $0.eff > $1.eff }
        let top = Array(scored.prefix(k))

        for hit in top {
            nodes[hit.index].accessCount += 1
            nodes[hit.index].lastAccess = now
        }
        if !top.isEmpty { try rewriteIndex() }

        return top.map { (text: nodes[$0.index].text, score: $0.sim) }
    }

    /// Text-block recall matching `VeraMemoryBridge.recall`/
    /// `SessionMemoryArchiver.buildZonePriorityInjection`'s self-contained
    /// block shape, for prepending into role/chat prompts.
    func recallBlock(for query: String, k: Int = 3) async -> String {
        guard let hits = try? await search(query: query, k: k), !hits.isEmpty else { return "" }
        let lines = hits.map { "  🧠 \($0.text)  (score: \(String(format: "%.2f", $0.score)))" }.joined(separator: "\n")
        return "\n[ETERNAL MEMORY — JGEN hidden-state recall]\n\(lines)\n[/ETERNAL MEMORY]\n"
    }
}
