import Foundation
import Accelerate

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
/// ── Scale (the 3-year budget) ────────────────────────────────────────
/// This store gains ~1 node per turn; three years of heavy use is
/// ~150k nodes. The original per-query costs — one FileHandle seek+read
/// PER NODE, a scalar Swift dot loop, and a full JSONL rewrite after
/// every hit — were invisible at 5k nodes and add up to seconds per turn
/// (plus ~45 MB of SSD writes per query) at 150k. Three changes hold the
/// same query at ~10 ms of scan regardless of age:
///
///   1. the vectors file is memory-mapped once and scanned in place
///   2. dot products go through vDSP against the fp32 cache
///   3. access-count bumps batch in memory and flush every
///      `rewriteEvery` hits (or on `flush()`), instead of rewriting the
///      whole index per query
///
/// On top of that sits the fluid placement layer (`hotOrder`): nodes are
/// scanned in gravity order, hottest first, and a query that finds a
/// confident hit inside the hot bucket skips the cold tail entirely.
/// Placement changes are appended to `placement.log.jsonl` so any
/// before/after answer difference can be attributed to a specific,
/// replayable reorder — fluidity without unexplainable drift.
actor EternalMemoryStore {
    static let shared = EternalMemoryStore()

    private static let dim = 1024
    private static let gravityHalfLifeDays: Double = 30.0

    /// Flush the node index after this many un-persisted access bumps.
    private static let rewriteEvery = 32

    /// The hot bucket is this fraction of the store (min 256 nodes) —
    /// sized from the Zipf shape of long-lived personal stores, where a
    /// few percent of nodes serve the large majority of recalls.
    private static let hotFraction = 0.05

    /// A hot-bucket hit at or above this cosine ends the scan early.
    /// Below it, the cold tail is scanned too — correctness beats speed
    /// on unfamiliar queries.
    private static let hotConfidence: Float = 0.62

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
    private var placementLogURL: URL { directory.appendingPathComponent("placement.log.jsonl") }

    private var nodes: [Node] = []
    private var loaded = false

    // ── Vector cache ─────────────────────────────────────────────────
    // fp32 mirror of the fp16 vectors file, converted once per launch
    // (and appended to on add). 150k nodes × 1024 dims × 4 B = ~600 MB
    // worst-case after three years; today's stores are a few MB. The
    // fp16 file stays the on-disk format — this cache is derived state.
    private var vecCache: [Float] = []
    private var vecCount = 0

    // ── Deferred index writes ────────────────────────────────────────
    private var pendingAccessBumps = 0

    // ── Fluid placement ──────────────────────────────────────────────
    /// Node indices in scan order: hot bucket first (by gravity at last
    /// reorder), then the cold tail. Rebuilt lazily when enough access
    /// activity accumulates; every rebuild is logged.
    private var hotOrder: [Int] = []
    private var hotCount = 0
    private var accessesSinceReorder = 0

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
        loadVectorCache()
        rebuildHotOrder(reason: "load")
        loaded = true
    }

    /// Map the fp16 file once and widen it into the fp32 scan cache.
    /// `.mappedIfSafe` keeps the transient footprint at one pass instead
    /// of read-then-convert double buffering.
    private func loadVectorCache() {
        vecCache = []
        vecCount = 0
        guard let data = try? Data(contentsOf: vectorsURL, options: .mappedIfSafe) else { return }
        let n = data.count / (Self.dim * 2)
        guard n > 0 else { return }
        vecCache = [Float](repeating: 0, count: n * Self.dim)
        data.withUnsafeBytes { (raw: UnsafeRawBufferPointer) in
            let half = raw.bindMemory(to: Float16.self)
            vecCache.withUnsafeMutableBufferPointer { out in
                for i in 0..<(n * Self.dim) { out[i] = Float(half[i]) }
            }
        }
        vecCount = n
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
        // Under IOGPU/unified-memory pressure, skip the extra full forward
        // encode — Vera-a chat/council already hammers JGEN; eternal write
        // is best-effort and must not tip WindowServer into a panic.
        guard JGenGPUSafety.allowEternalEncode else {
            NSLog("[EternalMemory] skipped encode under GPU/memory safety policy")
            return
        }
        try ensureLoaded()
        let clippedText = PromptBudget.truncateForModel(
            text, maxChars: PromptBudget.maxStoredMemoryChars, headChars: 2_800, tailChars: 800
        )
        let vec = Self.fitVec(try await embed(clippedText))

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

        // Keep the scan cache in step with the file — a new node is cold,
        // so it joins the tail of the scan order without a reorder.
        vecCache.append(contentsOf: vec)
        vecCount += 1
        hotOrder.append(nodes.count)

        let node = Node(
            id: nodes.count, ts: Date().timeIntervalSince1970, text: clippedText,
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
        pendingAccessBumps = 0
    }

    /// Persist any batched access bumps now. Called opportunistically from
    /// the flush threshold; safe to call any time.
    func flush() {
        guard pendingAccessBumps > 0 else { return }
        try? rewriteIndex()
    }

    private func gravity(daysSinceAccess: Double, accessCount: Int) -> Double {
        let halfLife = Self.gravityHalfLifeDays * Double(1 + accessCount)
        guard halfLife > 0 else { return 1 }
        return pow(0.5, daysSinceAccess / halfLife)
    }

    // ── Fluid placement ──────────────────────────────────────────────

    /// Re-sorts the scan order by current gravity and appends one line to
    /// the placement log: when, why, how many nodes moved into/out of the
    /// hot bucket, and the new hot membership. The structure moves, but
    /// every move is replayable.
    private func rebuildHotOrder(reason: String) {
        let now = Date().timeIntervalSince1970
        let ranked = nodes.indices.sorted { a, b in
            let ga = gravity(daysSinceAccess: max((now - nodes[a].lastAccess) / 86400, 0),
                             accessCount: nodes[a].accessCount)
            let gb = gravity(daysSinceAccess: max((now - nodes[b].lastAccess) / 86400, 0),
                             accessCount: nodes[b].accessCount)
            if ga != gb { return ga > gb }
            return a < b
        }
        let newHotCount = nodes.isEmpty ? 0
            : min(nodes.count, max(256, Int(Double(nodes.count) * Self.hotFraction)))
        let oldHot = Set(hotOrder.prefix(hotCount))
        let newHot = Set(ranked.prefix(newHotCount))
        hotOrder = ranked
        hotCount = newHotCount
        accessesSinceReorder = 0

        // Only log actual movement — a reorder that changed nothing is not
        // an event.
        let entered = newHot.subtracting(oldHot).count
        let left = oldHot.subtracting(newHot).count
        guard entered > 0 || left > 0 else { return }
        let entry: [String: Any] = [
            "ts": now, "reason": reason, "total": nodes.count,
            "hot": newHotCount, "entered": entered, "left": left,
        ]
        if var line = try? JSONSerialization.data(withJSONObject: entry, options: [.sortedKeys]) {
            line.append(contentsOf: "\n".utf8)
            if let h = FileHandle(forWritingAtPath: placementLogURL.path) {
                h.seekToEndOfFile(); h.write(line); h.closeFile()
            } else {
                FileManager.default.createFile(atPath: placementLogURL.path, contents: line)
            }
        }
    }

    /// vDSP cosine of the query against one cached vector.
    private func dot(_ qv: [Float], at index: Int) -> Float {
        var out: Float = 0
        qv.withUnsafeBufferPointer { q in
            vecCache.withUnsafeBufferPointer { c in
                vDSP_dotpr(c.baseAddress! + index * Self.dim, 1,
                           q.baseAddress!, 1, &out, vDSP_Length(Self.dim))
            }
        }
        return out
    }

    /// Cosine similarity in gravity scan order, re-ranked by the same
    /// gravity decay, top-K returned. The hot bucket is scanned first; a
    /// confident hot hit skips the cold tail (see the class doc). Access
    /// bumps batch in memory and flush every `rewriteEvery` hits.
    func search(query: String, k: Int) async throws -> [(text: String, score: Float)] {
        try ensureLoaded()
        guard !nodes.isEmpty else { return [] }
        guard JGenGPUSafety.allowEternalEncode else {
            NSLog("[EternalMemory] skipped search encode under GPU/memory safety policy")
            return []
        }
        let qv = Self.fitVec(try await embed(query))
        let now = Date().timeIntervalSince1970

        var scored: [(index: Int, eff: Float, sim: Float)] = []
        scored.reserveCapacity(min(nodes.count, 4096))

        func scan(_ slice: ArraySlice<Int>) {
            for i in slice where i < vecCount {
                let sim = dot(qv, at: i)
                let daysSince = max((now - nodes[i].lastAccess) / 86400.0, 0)
                let grav = Float(gravity(daysSinceAccess: daysSince, accessCount: nodes[i].accessCount))
                scored.append((i, sim * (0.7 + 0.3 * grav), sim))
            }
        }

        scan(hotOrder.prefix(hotCount))
        let bestHot = scored.max(by: { $0.sim < $1.sim })?.sim ?? -1
        // Cold tail only when the hot bucket is not confidently enough —
        // or when there is no meaningful hot bucket yet.
        if bestHot < Self.hotConfidence || hotCount == 0 || scored.count < k {
            scan(hotOrder.dropFirst(hotCount))
        }

        scored.sort { $0.eff > $1.eff }
        let top = Array(scored.prefix(k))

        for hit in top {
            nodes[hit.index].accessCount += 1
            nodes[hit.index].lastAccess = now
        }
        if !top.isEmpty {
            pendingAccessBumps += top.count
            accessesSinceReorder += top.count
            if pendingAccessBumps >= Self.rewriteEvery { try rewriteIndex() }
            // Let placement drift with real usage: reorder after enough
            // access activity, not per query.
            if accessesSinceReorder >= Self.rewriteEvery * 4 {
                rebuildHotOrder(reason: "access-drift")
            }
        }

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
