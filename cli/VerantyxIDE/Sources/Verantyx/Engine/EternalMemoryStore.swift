import Foundation
import Accelerate
import SQLite3

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
/// ── Storage (mirrors vera-memory's own SQLite move) ──────────────────
/// Node metadata and the placement log live in `cortex.db` (SQLite):
/// an access bump is one row UPDATE inside a per-query transaction, so
/// the old whole-file JSONL rewrite — and the batching machinery that
/// existed only to soften it — is gone entirely. The vectors stay in the
/// flat fp16 file: a BLOB per row would trade the single mapped scan
/// for row-at-a-time reads, which is exactly the pattern the 3-year
/// budget ruled out. A legacy `cortex.nodes.jsonl` is imported once and
/// kept beside the DB as `cortex.nodes.jsonl.migrated`.
///
/// ── Scale (the 3-year budget) ────────────────────────────────────────
/// This store gains ~1 node per turn; three years of heavy use is
/// ~150k nodes. Per-query costs that grow with N are held flat:
///
///   1. the vectors file is loaded once into an fp32 cache and scanned
///      in place
///   2. dot products go through vDSP
///   3. access bumps are row UPDATEs, not index rewrites
///
/// On top sits the fluid placement layer (`hotOrder`): nodes are
/// scanned in gravity order, hottest first, and a query that finds a
/// confident hit inside the hot bucket skips the cold tail entirely.
/// Placement changes append to the `placement_log` table so any
/// before/after answer difference can be attributed to a specific,
/// replayable reorder — fluidity without unexplainable drift.
actor EternalMemoryStore {
    static let shared = EternalMemoryStore()

    private static let dim = 1024
    private static let gravityHalfLifeDays: Double = 30.0

    /// The hot bucket is this fraction of the store (min 256 nodes) —
    /// sized from the Zipf shape of long-lived personal stores, where a
    /// few percent of nodes serve the large majority of recalls.
    private static let hotFraction = 0.05

    /// A hot-bucket hit at or above this cosine ends the scan early.
    /// Below it, the cold tail is scanned too — correctness beats speed
    /// on unfamiliar queries.
    private static let hotConfidence: Float = 0.62

    /// Re-sort the scan order after this many access bumps.
    private static let reorderEvery = 128

    private struct Node: Codable {
        let id: Int
        let ts: Double
        var text: String
        var concepts: [String]
        var accessCount: Int
        var lastAccess: Double
        // ── vera-a governance (mechanism 2/4) ─────────────────────────
        // The typed verdict and core this node was judged into at save
        // time — the symbolic anchor that survives model swaps and seeds
        // clusters. `quarantined` nodes (vera-a reported a contradiction)
        // are excluded from scans until a human clears them.
        var veraVerdict: String? = nil
        var veraCore: String? = nil
        var quarantined: Bool = false
    }

    private var directory: URL
    private var vectorsURL: URL { directory.appendingPathComponent("cortex.vectors") }
    private var legacyNodesURL: URL { directory.appendingPathComponent("cortex.nodes.jsonl") }
    private var dbURL: URL { directory.appendingPathComponent("cortex.db") }

    private var nodes: [Node] = []
    private var loaded = false
    private var db: OpaquePointer?

    // ── Vector cache ─────────────────────────────────────────────────
    // fp32 mirror of the fp16 vectors file, converted once per launch
    // (and appended to on add). 150k nodes × 1024 dims × 4 B = ~600 MB
    // worst-case after three years; today's stores are a few MB. The
    // fp16 file stays the on-disk format — this cache is derived state.
    private var vecCache: [Float] = []
    private var vecCount = 0

    // ── Fluid placement ──────────────────────────────────────────────
    /// Node indices in scan order: hot bucket first (by gravity at last
    /// reorder), then the cold tail. Rebuilt lazily when enough access
    /// activity accumulates; every rebuild that moves anything is logged.
    private var hotOrder: [Int] = []
    private var hotCount = 0
    private var accessesSinceReorder = 0

    /// Root/profile layout mirrors VeraMemoryPaths: "default" is the
    /// legacy root directory (existing stores keep working untouched),
    /// named profiles live under stores/<name>.
    private static func directoryFor(profile: String) -> URL {
        let root = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".verantyx_chrono_swift", isDirectory: true)
        return profile == "default"
            ? root
            : root.appendingPathComponent("stores/\(profile)", isDirectory: true)
    }

    private init() {
        directory = Self.directoryFor(profile: VeraMemoryPaths.activeProfile)
    }

    /// Live-switches to the profile currently named in UserDefaults
    /// (VeraMemoryPaths.profileDefaultsKey): closes the DB, drops every
    /// cache, and lets the next access load the other store. The embed
    /// pin travels with the store — each profile can be owned by a
    /// different JGEN.
    func switchToActiveProfile() {
        let newDir = Self.directoryFor(profile: VeraMemoryPaths.activeProfile)
        guard newDir != directory || !loaded else {
            directory = newDir
            return
        }
        if db != nil { sqlite3_close(db); db = nil }
        directory = newDir
        nodes = []
        vecCache = []
        vecCount = 0
        hotOrder = []
        hotCount = 0
        accessesSinceReorder = 0
        warnedModelMismatch = false
        loaded = false
    }

    // MARK: - SQLite plumbing

    /// `sqlite3_bind_text`'s "copy the bytes" destructor constant, which
    /// the Swift importer cannot express directly.
    private static let sqliteTransient = unsafeBitCast(-1, to: sqlite3_destructor_type.self)

    private func exec(_ sql: String) {
        sqlite3_exec(db, sql, nil, nil, nil)
    }

    private func openDB() throws {
        guard db == nil else { return }
        guard sqlite3_open(dbURL.path, &db) == SQLITE_OK else {
            let msg = String(cString: sqlite3_errmsg(db))
            sqlite3_close(db); db = nil
            throw NSError(domain: "EternalMemoryStore", code: 1,
                          userInfo: [NSLocalizedDescriptionKey: "cannot open cortex.db: \(msg)"])
        }
        // WAL: a reader (scan) and a writer (access bump) do not block
        // each other, and a crash mid-transaction cannot corrupt the DB.
        exec("PRAGMA journal_mode=WAL")
        exec("""
        CREATE TABLE IF NOT EXISTS nodes (
          id INTEGER PRIMARY KEY,
          ts REAL NOT NULL,
          text TEXT NOT NULL,
          concepts TEXT NOT NULL DEFAULT '[]',
          access_count INTEGER NOT NULL DEFAULT 0,
          last_access REAL NOT NULL
        )
        """)
        exec("""
        CREATE TABLE IF NOT EXISTS placement_log (
          ts REAL NOT NULL,
          reason TEXT NOT NULL,
          total INTEGER NOT NULL,
          hot INTEGER NOT NULL,
          entered INTEGER NOT NULL,
          departed INTEGER NOT NULL
        )
        """)
        // Mechanism 1's ground truth: the pairs themselves are the asset
        // (the projector trained from them is derived state, re-trainable
        // after any model swap). Populated by save approvals/rejections.
        exec("""
        CREATE TABLE IF NOT EXISTS supervision_pairs (
          ts REAL NOT NULL,
          kind TEXT NOT NULL,       -- approved | rejected | superseded
          text_a TEXT NOT NULL,
          text_b TEXT NOT NULL,
          core TEXT
        )
        """)
        // Governance columns (mechanism 2/4) — added after the table first
        // shipped, so bring old DBs up to shape. SQLite has no IF NOT
        // EXISTS for columns; the failed ALTER on an up-to-date DB is the
        // no-op we want.
        exec("ALTER TABLE nodes ADD COLUMN vera_verdict TEXT")
        exec("ALTER TABLE nodes ADD COLUMN vera_core TEXT")
        exec("ALTER TABLE nodes ADD COLUMN quarantined INTEGER NOT NULL DEFAULT 0")
        // Store-level facts, e.g. which JGEN owns this vector space.
        exec("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        // Vera-planned web searches and what they fetched: the raw
        // material for query analysis. Reused directly (same question →
        // last successful query) and mirrored into supervision_pairs so
        // the question→query mapping is learnable later.
        exec("""
        CREATE TABLE IF NOT EXISTS query_log (
          ts REAL NOT NULL,
          question TEXT NOT NULL,
          query TEXT NOT NULL,
          url TEXT NOT NULL
        )
        """)
    }

    /// One planned search that produced substantive evidence.
    func recordQueryPlan(question: String, query: String, url: String) {
        try? ensureLoaded()
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db,
            "INSERT INTO query_log (ts, question, query, url) VALUES (?,?,?,?)",
            -1, &stmt, nil) == SQLITE_OK else { return }
        defer { sqlite3_finalize(stmt) }
        sqlite3_bind_double(stmt, 1, Date().timeIntervalSince1970)
        sqlite3_bind_text(stmt, 2, String(question.prefix(300)), -1, Self.sqliteTransient)
        sqlite3_bind_text(stmt, 3, String(query.prefix(120)), -1, Self.sqliteTransient)
        sqlite3_bind_text(stmt, 4, String(url.prefix(500)), -1, Self.sqliteTransient)
        sqlite3_step(stmt)
        recordSupervisionPair(kind: "search-plan", textA: question, textB: query, core: nil)
    }

    /// The most recent query that already worked for this exact question —
    /// query analysis in its simplest honest form: reuse before replanning.
    func reusableQuery(forQuestion question: String) -> String? {
        try? ensureLoaded()
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db,
            "SELECT query FROM query_log WHERE question = ? ORDER BY ts DESC LIMIT 1",
            -1, &stmt, nil) == SQLITE_OK else { return nil }
        defer { sqlite3_finalize(stmt) }
        sqlite3_bind_text(stmt, 1, String(question.prefix(300)), -1, Self.sqliteTransient)
        guard sqlite3_step(stmt) == SQLITE_ROW else { return nil }
        return sqlite3_column_text(stmt, 0).map { String(cString: $0) }
    }

    private func metaGet(_ key: String) -> String? {
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, "SELECT value FROM meta WHERE key = ?",
                                 -1, &stmt, nil) == SQLITE_OK else { return nil }
        defer { sqlite3_finalize(stmt) }
        sqlite3_bind_text(stmt, 1, key, -1, Self.sqliteTransient)
        guard sqlite3_step(stmt) == SQLITE_ROW else { return nil }
        return sqlite3_column_text(stmt, 0).map { String(cString: $0) }
    }

    private func metaSet(_ key: String, _ value: String) {
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, "INSERT OR REPLACE INTO meta (key, value) VALUES (?,?)",
                                 -1, &stmt, nil) == SQLITE_OK else { return }
        defer { sqlite3_finalize(stmt) }
        sqlite3_bind_text(stmt, 1, key, -1, Self.sqliteTransient)
        sqlite3_bind_text(stmt, 2, value, -1, Self.sqliteTransient)
        sqlite3_step(stmt)
    }

    /// The JGEN this store's vector space belongs to, if one has claimed
    /// it — read by the launch-time memory-organ autoloader.
    func pinnedEmbedModel() -> String? {
        try? ensureLoaded()
        return metaGet("embed_model")
    }

    // ── Memory-organ pinning ─────────────────────────────────────────
    // The embedding space belongs to whichever JGEN wrote the first
    // vector. Encoding with a DIFFERENT loaded JGEN would silently mix
    // spaces — cosines between them are noise — so reads and writes are
    // refused (with one chat notice per launch) until the pinned model is
    // loaded again or the store is re-embedded. The chat model is free:
    // this pin only concerns the memory organ.
    private var warnedModelMismatch = false

    private func embedModelAllowed() async -> Bool {
        guard let current = await JCrossChatManager.shared.loadedModelName else { return false }
        if let pinned = metaGet("embed_model") {
            if pinned == current { return true }
            if !warnedModelMismatch {
                warnedModelMismatch = true
                let msg = L(
                    "🧠 Eternal memory is pinned to '\(pinned)' but '\(current)' is loaded — memory reads/writes are paused so the vector space stays coherent. Load the pinned model, or re-embed the store to switch organs.",
                    "🧠 永遠記憶は『\(pinned)』の空間に固定されていますが、現在は『\(current)』がロード中です — 空間の混線を防ぐため記憶の読み書きを一時停止します。固定モデルをロードするか、ストアを再埋め込みしてください。")
                await MainActor.run { AppState.shared?.addSystemMessage(msg) }
            }
            return false
        }
        // First write claims the space.
        metaSet("embed_model", current)
        return true
    }

    /// One-time import of the pre-SQLite JSONL index. The file is kept
    /// beside the DB with a `.migrated` suffix rather than deleted — it is
    /// the only backup of node metadata that predates the DB.
    private func migrateLegacyJSONLIfNeeded() {
        var count: Int64 = 0
        var stmt: OpaquePointer?
        if sqlite3_prepare_v2(db, "SELECT COUNT(*) FROM nodes", -1, &stmt, nil) == SQLITE_OK,
           sqlite3_step(stmt) == SQLITE_ROW {
            count = sqlite3_column_int64(stmt, 0)
        }
        sqlite3_finalize(stmt)
        guard count == 0,
              let data = FileManager.default.contents(atPath: legacyNodesURL.path),
              let text = String(data: data, encoding: .utf8) else { return }

        let legacy: [Node] = text.split(separator: "\n").compactMap { line in
            guard let d = line.data(using: .utf8) else { return nil }
            return try? JSONDecoder().decode(Node.self, from: d)
        }
        guard !legacy.isEmpty else { return }
        exec("BEGIN")
        for n in legacy { insertNodeRow(n) }
        exec("COMMIT")
        try? FileManager.default.moveItem(
            at: legacyNodesURL,
            to: directory.appendingPathComponent("cortex.nodes.jsonl.migrated"))
        NSLog("[EternalMemory] migrated \(legacy.count) nodes from JSONL to cortex.db")
    }

    private func insertNodeRow(_ n: Node) {
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, """
            INSERT OR REPLACE INTO nodes
              (id, ts, text, concepts, access_count, last_access,
               vera_verdict, vera_core, quarantined)
            VALUES (?,?,?,?,?,?,?,?,?)
            """, -1, &stmt, nil) == SQLITE_OK else { return }
        defer { sqlite3_finalize(stmt) }
        let concepts = (try? JSONEncoder().encode(n.concepts))
            .flatMap { String(data: $0, encoding: .utf8) } ?? "[]"
        sqlite3_bind_int64(stmt, 1, Int64(n.id))
        sqlite3_bind_double(stmt, 2, n.ts)
        sqlite3_bind_text(stmt, 3, n.text, -1, Self.sqliteTransient)
        sqlite3_bind_text(stmt, 4, concepts, -1, Self.sqliteTransient)
        sqlite3_bind_int64(stmt, 5, Int64(n.accessCount))
        sqlite3_bind_double(stmt, 6, n.lastAccess)
        if let v = n.veraVerdict { sqlite3_bind_text(stmt, 7, v, -1, Self.sqliteTransient) }
        else { sqlite3_bind_null(stmt, 7) }
        if let c = n.veraCore { sqlite3_bind_text(stmt, 8, c, -1, Self.sqliteTransient) }
        else { sqlite3_bind_null(stmt, 8) }
        sqlite3_bind_int64(stmt, 9, n.quarantined ? 1 : 0)
        sqlite3_step(stmt)
    }

    private func loadNodesFromDB() {
        nodes = []
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, """
            SELECT id, ts, text, concepts, access_count, last_access,
                   vera_verdict, vera_core, quarantined
            FROM nodes ORDER BY id
            """, -1, &stmt, nil) == SQLITE_OK else { return }
        defer { sqlite3_finalize(stmt) }
        while sqlite3_step(stmt) == SQLITE_ROW {
            let conceptsJSON = sqlite3_column_text(stmt, 3).map { String(cString: $0) } ?? "[]"
            let concepts = (conceptsJSON.data(using: .utf8))
                .flatMap { try? JSONDecoder().decode([String].self, from: $0) } ?? []
            nodes.append(Node(
                id: Int(sqlite3_column_int64(stmt, 0)),
                ts: sqlite3_column_double(stmt, 1),
                text: sqlite3_column_text(stmt, 2).map { String(cString: $0) } ?? "",
                concepts: concepts,
                accessCount: Int(sqlite3_column_int64(stmt, 4)),
                lastAccess: sqlite3_column_double(stmt, 5),
                veraVerdict: sqlite3_column_text(stmt, 6).map { String(cString: $0) },
                veraCore: sqlite3_column_text(stmt, 7).map { String(cString: $0) },
                quarantined: sqlite3_column_int64(stmt, 8) != 0
            ))
        }
    }

    private func bumpAccess(ids: [Int], now: Double) {
        guard !ids.isEmpty else { return }
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db,
            "UPDATE nodes SET access_count = access_count + 1, last_access = ? WHERE id = ?",
            -1, &stmt, nil) == SQLITE_OK else { return }
        defer { sqlite3_finalize(stmt) }
        exec("BEGIN")
        for id in ids {
            sqlite3_reset(stmt)
            sqlite3_bind_double(stmt, 1, now)
            sqlite3_bind_int64(stmt, 2, Int64(id))
            sqlite3_step(stmt)
        }
        exec("COMMIT")
    }

    private func logPlacement(reason: String, total: Int, hot: Int,
                              entered: Int, departed: Int, now: Double) {
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, """
            INSERT INTO placement_log (ts, reason, total, hot, entered, departed)
            VALUES (?,?,?,?,?,?)
            """, -1, &stmt, nil) == SQLITE_OK else { return }
        defer { sqlite3_finalize(stmt) }
        sqlite3_bind_double(stmt, 1, now)
        sqlite3_bind_text(stmt, 2, reason, -1, Self.sqliteTransient)
        sqlite3_bind_int64(stmt, 3, Int64(total))
        sqlite3_bind_int64(stmt, 4, Int64(hot))
        sqlite3_bind_int64(stmt, 5, Int64(entered))
        sqlite3_bind_int64(stmt, 6, Int64(departed))
        sqlite3_step(stmt)
    }

    // MARK: - Load

    private func ensureLoaded() throws {
        guard !loaded else { return }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try openDB()
        migrateLegacyJSONLIfNeeded()
        loadNodesFromDB()
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

    // MARK: - Embedding

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

    // MARK: - Write

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
        guard await embedModelAllowed() else { return }
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
        insertNodeRow(node)
    }

    // MARK: - vera-a governance (mechanisms 1–4)

    /// Mechanism 2 + 4: after a save approval, vera-a's `ask` verdict for
    /// the saved prompt lands here. Recent nodes whose text contains the
    /// prompt (or vice versa) get the core/verdict tag; a reported
    /// contradiction quarantines them out of the scan until a human looks.
    func applyVeraJudgment(promptPrefix: String, core: String,
                           verdict: String, contradiction: Int) {
        try? ensureLoaded()
        let needle = String(promptPrefix.prefix(80))
        guard !needle.isEmpty else { return }
        let quarantine = contradiction > 0
        var touched: [Int] = []
        // Only the recent tail — the save being judged just happened.
        for i in nodes.indices.suffix(50)
        where nodes[i].text.contains(needle) || needle.contains(nodes[i].text.prefix(80)) {
            nodes[i].veraCore = core
            nodes[i].veraVerdict = verdict
            nodes[i].quarantined = quarantine
            touched.append(i)
        }
        guard !touched.isEmpty else { return }
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, """
            UPDATE nodes SET vera_verdict = ?, vera_core = ?, quarantined = ? WHERE id = ?
            """, -1, &stmt, nil) == SQLITE_OK else { return }
        defer { sqlite3_finalize(stmt) }
        exec("BEGIN")
        for i in touched {
            sqlite3_reset(stmt)
            sqlite3_bind_text(stmt, 1, verdict, -1, Self.sqliteTransient)
            sqlite3_bind_text(stmt, 2, core, -1, Self.sqliteTransient)
            sqlite3_bind_int64(stmt, 3, quarantine ? 1 : 0)
            sqlite3_bind_int64(stmt, 4, Int64(nodes[i].id))
            sqlite3_step(stmt)
        }
        exec("COMMIT")
        if quarantine {
            logPlacement(reason: "vera-quarantine", total: nodes.count, hot: hotCount,
                         entered: 0, departed: touched.count,
                         now: Date().timeIntervalSince1970)
        }
    }

    /// Mechanism 3 (supersession proxy): a new approved fact just landed in
    /// `core`, so older eternal nodes tagged with the same core cool — their
    /// gravity drops by ~4 half-lives so the fresh fact outranks them in
    /// placement and (later) injection, without deleting anything.
    func coolCore(_ core: String, before ts: Double) {
        try? ensureLoaded()
        let pushback = Self.gravityHalfLifeDays * 4 * 86_400
        var cooled: [Int] = []
        for i in nodes.indices
        where nodes[i].veraCore == core && nodes[i].ts < ts && !nodes[i].quarantined {
            nodes[i].lastAccess = min(nodes[i].lastAccess, ts - pushback)
            cooled.append(i)
        }
        guard !cooled.isEmpty else { return }
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db,
            "UPDATE nodes SET last_access = ? WHERE id = ?", -1, &stmt, nil) == SQLITE_OK else { return }
        defer { sqlite3_finalize(stmt) }
        exec("BEGIN")
        for i in cooled {
            sqlite3_reset(stmt)
            sqlite3_bind_double(stmt, 1, nodes[i].lastAccess)
            sqlite3_bind_int64(stmt, 2, Int64(nodes[i].id))
            sqlite3_step(stmt)
        }
        exec("COMMIT")
        rebuildHotOrder(reason: "vera-supersede")
    }

    /// Mechanism 1's collection side: the pair table IS the asset — the
    /// projector eventually trained from it is derived state, re-trainable
    /// after any model swap. `kind`: approved / rejected / superseded.
    func recordSupervisionPair(kind: String, textA: String, textB: String, core: String?) {
        try? ensureLoaded()
        let a = String(textA.prefix(500)), b = String(textB.prefix(500))
        guard !a.isEmpty, !b.isEmpty else { return }
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, """
            INSERT INTO supervision_pairs (ts, kind, text_a, text_b, core) VALUES (?,?,?,?,?)
            """, -1, &stmt, nil) == SQLITE_OK else { return }
        defer { sqlite3_finalize(stmt) }
        sqlite3_bind_double(stmt, 1, Date().timeIntervalSince1970)
        sqlite3_bind_text(stmt, 2, kind, -1, Self.sqliteTransient)
        sqlite3_bind_text(stmt, 3, a, -1, Self.sqliteTransient)
        sqlite3_bind_text(stmt, 4, b, -1, Self.sqliteTransient)
        if let core { sqlite3_bind_text(stmt, 5, core, -1, Self.sqliteTransient) }
        else { sqlite3_bind_null(stmt, 5) }
        sqlite3_step(stmt)
    }

    // MARK: - Fluid placement

    private func gravity(daysSinceAccess: Double, accessCount: Int) -> Double {
        let halfLife = Self.gravityHalfLifeDays * Double(1 + accessCount)
        guard halfLife > 0 else { return 1 }
        return pow(0.5, daysSinceAccess / halfLife)
    }

    /// Re-sorts the scan order by current gravity and records the move in
    /// the `placement_log` table: when, why, how many nodes entered/left
    /// the hot bucket. The structure moves, but every move is replayable.
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
        let departed = oldHot.subtracting(newHot).count
        guard entered > 0 || departed > 0 else { return }
        logPlacement(reason: reason, total: nodes.count, hot: newHotCount,
                     entered: entered, departed: departed, now: now)
    }

    // MARK: - Search

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
    /// bumps are row UPDATEs inside one transaction.
    func search(query: String, k: Int) async throws -> [(text: String, score: Float)] {
        try ensureLoaded()
        guard !nodes.isEmpty else { return [] }
        guard JGenGPUSafety.allowEternalEncode else {
            NSLog("[EternalMemory] skipped search encode under GPU/memory safety policy")
            return []
        }
        guard await embedModelAllowed() else { return [] }
        let qv = Self.fitVec(try await embed(query))
        let now = Date().timeIntervalSince1970

        var scored: [(index: Int, eff: Float, sim: Float)] = []
        scored.reserveCapacity(min(nodes.count, 4096))

        func scan(_ slice: ArraySlice<Int>) {
            // Quarantined nodes (vera-a reported a contradiction) stay out
            // of recall until a human clears them.
            for i in slice where i < vecCount && !nodes[i].quarantined {
                let sim = dot(qv, at: i)
                let daysSince = max((now - nodes[i].lastAccess) / 86400.0, 0)
                let grav = Float(gravity(daysSinceAccess: daysSince, accessCount: nodes[i].accessCount))
                scored.append((i, sim * (0.7 + 0.3 * grav), sim))
            }
        }

        scan(hotOrder.prefix(hotCount))
        let bestHot = scored.max(by: { $0.sim < $1.sim })?.sim ?? -1
        // Cold tail only when the hot bucket is not confident enough —
        // or when there is no meaningful hot bucket yet.
        if bestHot < Self.hotConfidence || hotCount == 0 || scored.count < k {
            scan(hotOrder.dropFirst(hotCount))
        }

        scored.sort { $0.eff > $1.eff }
        let top = Array(scored.prefix(k))

        if !top.isEmpty {
            for hit in top {
                nodes[hit.index].accessCount += 1
                nodes[hit.index].lastAccess = now
            }
            bumpAccess(ids: top.map { nodes[$0.index].id }, now: now)
            accessesSinceReorder += top.count
            // Let placement drift with real usage: reorder after enough
            // access activity, not per query.
            if accessesSinceReorder >= Self.reorderEvery {
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
