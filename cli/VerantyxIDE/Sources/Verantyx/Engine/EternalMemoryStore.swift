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
        // 'agent' by default; 'human' marks a demonstration the person
        // actually drove, which is the ground truth the motion model wants.
        exec("ALTER TABLE mouse_trace ADD COLUMN source TEXT NOT NULL DEFAULT 'agent'")
        // The join key. Without it a trajectory records how the pointer
        // moved and nothing about why.
        exec("ALTER TABLE mouse_trace ADD COLUMN episode_id TEXT")
        // 'browser' when the run actually drove a page, 'headless' when a
        // fetch answered it. Recorded so routing can be learned from what
        // WORKED rather than re-derived from a keyword list.
        exec("ALTER TABLE act_episode ADD COLUMN route TEXT NOT NULL DEFAULT ''")
        // Pixels paired with what Accessibility said was on them, at the same
        // instant. The supervision for the vision tower, produced free during
        // ordinary work and previously discarded.
        exec("""
        CREATE TABLE IF NOT EXISTS visual_ground (
          ts REAL NOT NULL,
          app TEXT NOT NULL DEFAULT '',
          signature TEXT NOT NULL,
          layout TEXT NOT NULL DEFAULT '',
          window_title TEXT NOT NULL DEFAULT '',
          labels TEXT NOT NULL DEFAULT ''
        )
        """)

        // ── One act, whole ────────────────────────────────────────────
        // Each of these already existed somewhere: the goal in ActDNA's
        // directive, the action in the tool call, the outcome in the
        // honesty verdict, the screens in frames that were captured and
        // then dropped. Separately they are logs. Joined by episode_id
        // they answer the question logs cannot: why was this action
        // chosen, against what screen, and what did it actually do.
        exec("""
        CREATE TABLE IF NOT EXISTS act_episode (
          episode_id TEXT PRIMARY KEY,
          ts REAL NOT NULL,
          session_id TEXT NOT NULL DEFAULT '',
          app TEXT NOT NULL DEFAULT '',
          goal TEXT NOT NULL DEFAULT '',
          rationale TEXT NOT NULL DEFAULT '',
          action TEXT NOT NULL DEFAULT '',
          target_label TEXT NOT NULL DEFAULT '',
          screen_before TEXT NOT NULL DEFAULT '',
          screen_after TEXT NOT NULL DEFAULT '',
          visual_distance REAL NOT NULL DEFAULT -1,
          changed INTEGER NOT NULL DEFAULT 0,
          ok INTEGER NOT NULL DEFAULT 0,
          note TEXT NOT NULL DEFAULT ''
        )
        """)
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
        // Mouse trajectories the Act limbs actually drove. Synthetic
        // cursor motion is the least reliable thing this app does — the
        // calibration probe can measure nothing and silently fall back to
        // a scale of 1.0, which puts the click somewhere else entirely.
        // A trajectory that verifiably REACHED its target is therefore
        // worth remembering: next time the probe fails, the remembered
        // calibration replaces the blind guess.
        exec("""
        CREATE TABLE IF NOT EXISTS mouse_trace (
          ts REAL NOT NULL,
          app TEXT NOT NULL,
          cell TEXT NOT NULL,
          screen_w REAL NOT NULL,
          screen_h REAL NOT NULL,
          req_x REAL NOT NULL, req_y REAL NOT NULL,
          reached_x REAL NOT NULL, reached_y REAL NOT NULL,
          calib_x REAL NOT NULL, calib_y REAL NOT NULL,
          path TEXT NOT NULL,
          ok INTEGER NOT NULL
        )
        """)
    }

    /// Opens the database without loading the node index or the vector
    /// cache — for callers that only touch a side table (query log, mouse
    /// traces) and must not pay a 600 MB cache load to write one row.
    private func ensureDB() throws {
        guard db == nil else { return }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try openDB()
    }

    // MARK: - Mouse traces (Act limb hints)

    /// A trajectory that worked, offered back as a starting point.
    struct MouseHint: Sendable {
        let reachedX: Double
        let reachedY: Double
        let calibX: Double
        let calibY: Double
        let ts: Double
    }

    func recordMouseTrace(app: String, cell: String,
                          screenW: Double, screenH: Double,
                          reqX: Double, reqY: Double,
                          reachedX: Double, reachedY: Double,
                          calibX: Double, calibY: Double,
                          path: String, ok: Bool,
                          source: String = "agent",
                          episodeId: String = "") {
        try? ensureDB()
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, """
            INSERT INTO mouse_trace
              (ts, app, cell, screen_w, screen_h, req_x, req_y,
               reached_x, reached_y, calib_x, calib_y, path, ok, source, episode_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, -1, &stmt, nil) == SQLITE_OK else { return }
        defer { sqlite3_finalize(stmt) }
        sqlite3_bind_double(stmt, 1, Date().timeIntervalSince1970)
        sqlite3_bind_text(stmt, 2, app, -1, Self.sqliteTransient)
        sqlite3_bind_text(stmt, 3, cell, -1, Self.sqliteTransient)
        sqlite3_bind_double(stmt, 4, screenW)
        sqlite3_bind_double(stmt, 5, screenH)
        sqlite3_bind_double(stmt, 6, reqX)
        sqlite3_bind_double(stmt, 7, reqY)
        sqlite3_bind_double(stmt, 8, reachedX)
        sqlite3_bind_double(stmt, 9, reachedY)
        sqlite3_bind_double(stmt, 10, calibX)
        sqlite3_bind_double(stmt, 11, calibY)
        sqlite3_bind_text(stmt, 12, String(path.prefix(2000)), -1, Self.sqliteTransient)
        sqlite3_bind_int64(stmt, 13, ok ? 1 : 0)
        sqlite3_bind_text(stmt, 14, source, -1, Self.sqliteTransient)
        sqlite3_bind_text(stmt, 15, episodeId, -1, Self.sqliteTransient)
        sqlite3_step(stmt)
    }

    // MARK: - Browser session (what is open right now)

    func saveBrowserSession(url: String, title: String, scrollNotches: Int,
                            candidates: [String], updatedAt: Double) {
        try? ensureDB()
        exec("CREATE TABLE IF NOT EXISTS browser_session (id INTEGER PRIMARY KEY CHECK (id = 1), url TEXT, title TEXT, scroll INTEGER, candidates TEXT, updated_at REAL)")
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, """
            INSERT OR REPLACE INTO browser_session (id, url, title, scroll, candidates, updated_at)
            VALUES (1,?,?,?,?,?)
            """, -1, &stmt, nil) == SQLITE_OK else { return }
        defer { sqlite3_finalize(stmt) }
        let joined = candidates.joined(separator: "\u{1}")
        sqlite3_bind_text(stmt, 1, url, -1, Self.sqliteTransient)
        sqlite3_bind_text(stmt, 2, title, -1, Self.sqliteTransient)
        sqlite3_bind_int64(stmt, 3, Int64(scrollNotches))
        sqlite3_bind_text(stmt, 4, joined, -1, Self.sqliteTransient)
        sqlite3_bind_double(stmt, 5, updatedAt)
        sqlite3_step(stmt)
    }

    func loadBrowserSession() -> (url: String, title: String, scrollNotches: Int,
                                  candidates: [String], updatedAt: Double)? {
        try? ensureDB()
        exec("CREATE TABLE IF NOT EXISTS browser_session (id INTEGER PRIMARY KEY CHECK (id = 1), url TEXT, title TEXT, scroll INTEGER, candidates TEXT, updated_at REAL)")
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db,
            "SELECT url, title, scroll, candidates, updated_at FROM browser_session WHERE id = 1",
            -1, &stmt, nil) == SQLITE_OK else { return nil }
        defer { sqlite3_finalize(stmt) }
        guard sqlite3_step(stmt) == SQLITE_ROW else { return nil }
        let url = sqlite3_column_text(stmt, 0).map { String(cString: $0) } ?? ""
        guard !url.isEmpty else { return nil }
        let raw = sqlite3_column_text(stmt, 3).map { String(cString: $0) } ?? ""
        return (url,
                sqlite3_column_text(stmt, 1).map { String(cString: $0) } ?? "",
                Int(sqlite3_column_int64(stmt, 2)),
                raw.isEmpty ? [] : raw.components(separatedBy: "\u{1}"),
                sqlite3_column_double(stmt, 4))
    }

    // MARK: - Act episodes (the join)

    /// One complete act: why it was chosen, what it did, what changed.
    func recordActEpisode(episodeId: String, sessionId: String, app: String,
                          goal: String, rationale: String, action: String,
                          targetLabel: String,
                          screenBefore: String, screenAfter: String,
                          visualDistance: Double, changed: Bool, ok: Bool,
                          note: String, route: String = "") {
        try? ensureDB()
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, """
            INSERT OR REPLACE INTO act_episode
              (episode_id, ts, session_id, app, goal, rationale, action,
               target_label, screen_before, screen_after, visual_distance,
               changed, ok, note, route)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, -1, &stmt, nil) == SQLITE_OK else { return }
        defer { sqlite3_finalize(stmt) }
        sqlite3_bind_text(stmt, 1, episodeId, -1, Self.sqliteTransient)
        sqlite3_bind_double(stmt, 2, Date().timeIntervalSince1970)
        sqlite3_bind_text(stmt, 3, sessionId, -1, Self.sqliteTransient)
        sqlite3_bind_text(stmt, 4, app, -1, Self.sqliteTransient)
        sqlite3_bind_text(stmt, 5, String(goal.prefix(300)), -1, Self.sqliteTransient)
        sqlite3_bind_text(stmt, 6, String(rationale.prefix(600)), -1, Self.sqliteTransient)
        sqlite3_bind_text(stmt, 7, String(action.prefix(200)), -1, Self.sqliteTransient)
        sqlite3_bind_text(stmt, 8, String(targetLabel.prefix(200)), -1, Self.sqliteTransient)
        sqlite3_bind_text(stmt, 9, screenBefore, -1, Self.sqliteTransient)
        sqlite3_bind_text(stmt, 10, screenAfter, -1, Self.sqliteTransient)
        sqlite3_bind_double(stmt, 11, visualDistance)
        sqlite3_bind_int64(stmt, 12, changed ? 1 : 0)
        sqlite3_bind_int64(stmt, 13, ok ? 1 : 0)
        sqlite3_bind_text(stmt, 14, String(note.prefix(300)), -1, Self.sqliteTransient)
        sqlite3_bind_text(stmt, 15, route, -1, Self.sqliteTransient)
        sqlite3_step(stmt)
    }

    /// A route that produced a real result, recorded without a full act
    /// episode — the search paths have a goal and an outcome but no
    /// screen or pointer to report.
    func recordRouteOutcome(goal: String, route: String, ok: Bool, note: String) {
        guard !goal.trimmingCharacters(in: .whitespaces).isEmpty else { return }
        recordActEpisode(episodeId: UUID().uuidString, sessionId: "", app: "",
                         goal: goal, rationale: "", action: "search",
                         targetLabel: "", screenBefore: "", screenAfter: "",
                         visualDistance: -1, changed: ok, ok: ok,
                         note: note, route: route)
    }

    /// Which route past goals LIKE this one actually needed.
    ///
    /// The structural half of routing: instead of asking a keyword list
    /// whether "githubのissueを見て" is browsing, ask what happened the
    /// last times a goal sharing its distinctive words was run. The label
    /// is the outcome — a run that really drove a page counts as browser
    /// — so a mis-route is not learned as truth just because it was
    /// chosen. Deliberately lexical rather than embedded: it needs no
    /// model loaded, survives a model swap, and can state its reason
    /// ("3 of 4 similar goals used the browser") in words.
    func routeEvidence(for goal: String, minOverlap: Int = 2)
            -> (browser: Int, headless: Int, example: String)? {
        try? ensureDB()
        let wanted = ClaimGrounding.anchorTokens(goal)
            .union(ClaimGrounding.lexicalTokens(goal))
        guard wanted.count >= minOverlap else { return nil }

        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, """
            SELECT goal, route FROM act_episode
            WHERE route <> '' AND ok = 1 AND goal <> ''
            ORDER BY ts DESC LIMIT 400
            """, -1, &stmt, nil) == SQLITE_OK else { return nil }
        defer { sqlite3_finalize(stmt) }

        var browser = 0, headless = 0, example = ""
        while sqlite3_step(stmt) == SQLITE_ROW {
            let pastGoal = sqlite3_column_text(stmt, 0).map { String(cString: $0) } ?? ""
            let route = sqlite3_column_text(stmt, 1).map { String(cString: $0) } ?? ""
            let past = ClaimGrounding.anchorTokens(pastGoal)
                .union(ClaimGrounding.lexicalTokens(pastGoal))
            guard wanted.intersection(past).count >= minOverlap else { continue }
            if route == "browser" {
                browser += 1
                if example.isEmpty { example = String(pastGoal.prefix(50)) }
            } else if route == "headless" {
                headless += 1
                if example.isEmpty { example = String(pastGoal.prefix(50)) }
            }
        }
        guard browser + headless > 0 else { return nil }
        return (browser, headless, example)
    }

    // MARK: - Closing the loop: how to drive a given app
    //
    // The methods were being written and never read. Writing alone is a log;
    // reading it back before choosing is what makes it memory. These three
    // steps are the loop:
    //
    //   record   → every menu/keys/click attempt, with its outcome
    //   read     → before choosing, ask what worked here before
    //   general  → when one app has enough history, turn the rows into a
    //              sentence and put it where recall can find it
    //
    // The third step is the one that turns experience into knowledge. Rows
    // only answer questions someone thought to ask; a consolidated fact in the
    // node index participates in ordinary similarity recall, so it surfaces
    // for a question nobody anticipated — including about an app it was never
    // written about, when that app is close enough in the same space.

    struct MethodTally {
        let method: String
        let attempts: Int
        let successes: Int
        var rate: Double { attempts == 0 ? 0 : Double(successes) / Double(attempts) }
        var display: String { "\(method) \(successes)/\(attempts)" }
    }

    /// What has actually worked for this app, newest 200 attempts.
    func methodEvidence(app: String) -> [MethodTally] {
        try? ensureDB()
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, """
            SELECT action, COUNT(*), SUM(ok) FROM (
              SELECT action, ok FROM act_episode
              WHERE app = ? AND route LIKE 'method:%'
              ORDER BY ts DESC LIMIT 200
            ) GROUP BY action
            """, -1, &stmt, nil) == SQLITE_OK else { return [] }
        defer { sqlite3_finalize(stmt) }
        sqlite3_bind_text(stmt, 1, app, -1, Self.sqliteTransient)

        var out: [MethodTally] = []
        while sqlite3_step(stmt) == SQLITE_ROW {
            let method = sqlite3_column_text(stmt, 0).map { String(cString: $0) } ?? ""
            let attempts = Int(sqlite3_column_int64(stmt, 1))
            let successes = Int(sqlite3_column_int64(stmt, 2))
            guard !method.isEmpty, attempts > 0 else { continue }
            out.append(MethodTally(method: method, attempts: attempts, successes: successes))
        }
        // Best first, and a method tried more often breaks a tie — one lucky
        // success should not outrank nine out of ten.
        return out.sorted {
            $0.rate == $1.rate ? $0.attempts > $1.attempts : $0.rate > $1.rate
        }
    }

    /// How many attempts exist for an app at all. Used to decide when there is
    /// enough history to be worth generalizing.
    func methodAttemptCount(app: String) -> Int {
        methodEvidence(app: app).reduce(0) { $0 + $1.attempts }
    }

    /// Turn the rows for one app into a durable, recallable sentence.
    ///
    /// Called after an attempt once there is enough history. Deliberately
    /// written as plain language rather than a structured blob: it goes into
    /// the same node index as everything else vera-a knows, so it has to be
    /// something recall can match a question against.
    func consolidateMethodKnowledge(app: String, minAttempts: Int = 6) async {
        let tallies = methodEvidence(app: app)
        let total = tallies.reduce(0) { $0 + $1.attempts }
        guard total >= minAttempts, let best = tallies.first else { return }

        // Nothing worth asserting when everything failed equally — a fact that
        // says "we know nothing" is worse than no fact.
        guard best.successes > 0 else { return }

        let worked = tallies.filter { $0.rate >= 0.6 && $0.successes > 0 }
        let failed = tallies.filter { $0.rate < 0.4 && $0.attempts >= 2 }

        var sentence = "\(app) を操作するには \(best.method) が有効"
            + "（\(best.successes)/\(best.attempts) 成功）。"
        if worked.count > 1 {
            sentence += " 他に使えた方法: "
                + worked.dropFirst().map(\.display).joined(separator: "、") + "。"
        }
        if !failed.isEmpty {
            sentence += " 失敗が多い方法: "
                + failed.map(\.display).joined(separator: "、") + "。"
        }

        try? await addFact(key: "method:\(app)", text: sentence,
                           concepts: [app, "操作方法", best.method, "app-control"])
    }

    // MARK: - What this workspace IS, not just where it is
    //
    // The system prompt states CURRENT WORKSPACE ROOT and nothing else. The
    // model knows the path and must rediscover everything behind it — the
    // layout, the build command, which directory the real source lives in —
    // by listing directories again, every session, forever. The knowledge is
    // produced every time and kept none of the times.
    //
    // vera-a already holds facts in a similarity space. A workspace is a
    // subject like any other, so what was learned about it is recalled the
    // same way, and the path is only the key that starts the lookup.

    /// A compact block about this workspace for the system prompt.
    /// Empty when nothing is known — silence beats a heading with no content.
    func workspaceContext(path: String, k: Int = 5) async -> String {
        let name = URL(fileURLWithPath: path).lastPathComponent
        // Query by name AND path: the name carries the meaning, the path
        // disambiguates two checkouts of the same project.
        guard let hits = try? await search(query: "\(name) \(path) プロジェクト 構成 ビルド", k: k),
              !hits.isEmpty else { return "" }

        // Only reasonably confident matches. A weak hit is a different project
        // that happens to share a word, and a wrong fact about the layout is
        // worse than no fact — it sends the agent to a path that is not there.
        let good = hits.filter { $0.score >= 0.35 }
        guard !good.isEmpty else { return "" }

        return """

        [THIS WORKSPACE — vera-a に蓄積された理解]
        \(good.map { "  • \($0.text)" }.joined(separator: "\n"))
        これらは過去のセッションで確かめた内容です。現状と矛盾する場合は実際のファイルを優先してください。
        [/THIS WORKSPACE]
        """
    }

    /// A command that actually worked here. Build and test invocations are the
    /// expensive things to rediscover: they are project-specific, long, and
    /// wrong in a dozen ways before they are right.
    func recordWorkspaceCommand(path: String, command: String, ok: Bool,
                                sessionId: String) {
        // Only commands worth remembering. `ls` and `pwd` are not knowledge.
        let c = command.lowercased()
        let interesting = ["build", "test", "run", "make", "xcodebuild", "swift",
                           "npm", "yarn", "pnpm", "cargo", "go ", "pytest",
                           "python", "gradle", "mvn", "docker"]
        guard interesting.contains(where: { c.contains($0) }) else { return }

        recordActEpisode(
            episodeId: UUID().uuidString, sessionId: sessionId, app: path,
            goal: "このワークスペースで有効なコマンド",
            rationale: "同じ発見を毎回やり直さないため",
            action: "shell", targetLabel: String(command.prefix(160)),
            screenBefore: "", screenAfter: "",
            visualDistance: 0, changed: ok, ok: ok,
            note: ok ? "成功" : "失敗", route: "workspace:cmd")
    }

    /// Turn repeated successes into a sentence recall can find.
    func consolidateWorkspaceKnowledge(path: String, minSuccesses: Int = 2) async {
        try? ensureDB()
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, """
            SELECT target_label, COUNT(*) FROM act_episode
            WHERE app = ? AND route = 'workspace:cmd' AND ok = 1
            GROUP BY target_label ORDER BY COUNT(*) DESC LIMIT 3
            """, -1, &stmt, nil) == SQLITE_OK else { return }
        defer { sqlite3_finalize(stmt) }
        sqlite3_bind_text(stmt, 1, path, -1, Self.sqliteTransient)

        var lines: [String] = []
        while sqlite3_step(stmt) == SQLITE_ROW {
            let cmd = sqlite3_column_text(stmt, 0).map { String(cString: $0) } ?? ""
            let n = Int(sqlite3_column_int64(stmt, 1))
            guard n >= minSuccesses, !cmd.isEmpty else { continue }
            lines.append("`\(cmd)`（\(n)回成功）")
        }
        guard !lines.isEmpty else { return }

        let name = URL(fileURLWithPath: path).lastPathComponent
        try? await addFact(
            key: "workspace:\(path)",
            text: "\(name)（\(path)）で通るコマンド: " + lines.joined(separator: "、"),
            concepts: [name, path, "プロジェクト", "ビルド", "コマンド"])
    }

    // MARK: - Do our corrections actually work?
    //
    // The parser tells the model what it did wrong and asks again. Whether
    // that message ever produces a different attempt was never measured, and
    // the cost of not measuring it was visible: an [MCP_CALL] missing its
    // closing tag was told "write it on its own line" — which it already was —
    // so the model rewrote the identical text and the turn repeated. A
    // correction that cannot be acted on does not fail quietly; it loops.
    //
    // A correction is a METHOD for a DEFECT, exactly as a dismissal is a
    // method for an overlay. Same table, same shape, same lesson: try what has
    // worked for this defect before, and stop reissuing what never has.

    /// Which correction has fixed this defect before, best first.
    /// Signature is "TOOL|defectKind".
    func correctionEvidence(signature: String) -> [MethodTally] {
        try? ensureDB()
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, """
            SELECT action, COUNT(*), SUM(ok) FROM (
              SELECT action, ok FROM act_episode
              WHERE target_label = ? AND route LIKE 'correction:%'
              ORDER BY ts DESC LIMIT 60
            ) GROUP BY action
            """, -1, &stmt, nil) == SQLITE_OK else { return [] }
        defer { sqlite3_finalize(stmt) }
        sqlite3_bind_text(stmt, 1, signature, -1, Self.sqliteTransient)

        var out: [MethodTally] = []
        while sqlite3_step(stmt) == SQLITE_ROW {
            let method = sqlite3_column_text(stmt, 0).map { String(cString: $0) } ?? ""
            let attempts = Int(sqlite3_column_int64(stmt, 1))
            let successes = Int(sqlite3_column_int64(stmt, 2))
            guard !method.isEmpty, attempts > 0 else { continue }
            out.append(MethodTally(method: method, attempts: attempts, successes: successes))
        }
        return out.sorted {
            $0.rate == $1.rate ? $0.attempts > $1.attempts : $0.rate > $1.rate
        }
    }

    /// Corrections that have never once worked for this defect. Not merely
    /// ranked last — reissuing them is the loop, so they are excluded.
    func uselessCorrections(signature: String, minAttempts: Int = 2) -> Set<String> {
        Set(correctionEvidence(signature: signature)
            .filter { $0.successes == 0 && $0.attempts >= minAttempts }
            .map(\.method))
    }

    func recordCorrection(signature: String, strategy: String, worked: Bool,
                          sessionId: String, note: String) async {
        recordActEpisode(
            episodeId: UUID().uuidString, sessionId: sessionId, app: "parser",
            goal: signature,
            rationale: "ツール指定の誤りを直させるため",
            action: strategy, targetLabel: signature,
            screenBefore: "", screenAfter: "",
            visualDistance: 0, changed: worked, ok: worked,
            note: note, route: "correction:\(strategy)")

        // Once a defect has a correction that reliably works, say so where
        // recall can find it — the next session should not rediscover it.
        let tallies = correctionEvidence(signature: signature)
        let total = tallies.reduce(0) { $0 + $1.attempts }
        if total >= 4, let best = tallies.first, best.successes > 0, best.rate >= 0.6 {
            try? await addFact(
                key: "correction:\(signature)",
                text: "\(signature) の誤りは「\(best.method)」で直る"
                    + "（\(best.successes)/\(best.attempts)）。",
                concepts: [signature, "ツール指定", "訂正"])
        }
    }

    /// Which dismissal has cleared THIS overlay before, best first.
    ///
    /// Keyed on the overlay's signature rather than the app, because one app
    /// has several overlays and they do not all close the same way — Safari's
    /// downloads popover and its permission sheet are different problems.
    func dismissEvidence(signature: String) -> [MethodTally] {
        try? ensureDB()
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, """
            SELECT action, COUNT(*), SUM(ok) FROM (
              SELECT action, ok FROM act_episode
              WHERE target_label = ? AND route LIKE 'dismiss:%'
              ORDER BY ts DESC LIMIT 60
            ) GROUP BY action
            """, -1, &stmt, nil) == SQLITE_OK else { return [] }
        defer { sqlite3_finalize(stmt) }
        sqlite3_bind_text(stmt, 1, signature, -1, Self.sqliteTransient)

        var out: [MethodTally] = []
        while sqlite3_step(stmt) == SQLITE_ROW {
            let method = sqlite3_column_text(stmt, 0).map { String(cString: $0) } ?? ""
            let attempts = Int(sqlite3_column_int64(stmt, 1))
            let successes = Int(sqlite3_column_int64(stmt, 2))
            guard !method.isEmpty, attempts > 0 else { continue }
            out.append(MethodTally(method: method, attempts: attempts, successes: successes))
        }
        return out.sorted {
            $0.rate == $1.rate ? $0.attempts > $1.attempts : $0.rate > $1.rate
        }
    }

    /// Turn repeated dismissals of one overlay into a recallable sentence, so
    /// it stops being a table lookup and becomes something the agent can be
    /// reminded of for an overlay it has never seen but which sits nearby in
    /// the same space.
    func consolidateDismissKnowledge(signature: String, appName: String,
                                     overlay: String, minAttempts: Int = 3) async {
        let tallies = dismissEvidence(signature: signature)
        let total = tallies.reduce(0) { $0 + $1.attempts }
        guard total >= minAttempts, let best = tallies.first, best.successes > 0 else { return }
        try? await addFact(
            key: "dismiss:\(signature)",
            text: "\(appName) の「\(overlay)」が邪魔なときは \(best.method) で閉じられる"
                + "（\(best.successes)/\(best.attempts)）。",
            concepts: [appName, overlay, "障害物", "閉じ方"])
    }

    /// What happened last time this app was in this screen state and an
    /// act like this was tried — the question a log cannot answer.
    /// Returns compact lines for injection, newest first.
    func actEpisodeRecall(app: String, screenBefore: String, limit: Int = 3) -> [String] {
        try? ensureDB()
        var stmt: OpaquePointer?
        // Was `screen_before = ?` against a SHA256. Two captures of the same
        // page differ by a caret blink, so the hashes differed completely and
        // this never once matched — the question it exists to answer was
        // unanswerable. Candidates are fetched and ranked by signature
        // distance instead, which is what "the same screen" actually means.
        guard sqlite3_prepare_v2(db, """
            SELECT action, target_label, changed, ok, rationale, screen_before
            FROM act_episode
            WHERE app = ? AND screen_before <> ''
            ORDER BY ts DESC LIMIT 200
            """, -1, &stmt, nil) == SQLITE_OK else { return [] }
        defer { sqlite3_finalize(stmt) }
        sqlite3_bind_text(stmt, 1, app, -1, Self.sqliteTransient)

        let wanted = ScreenSignature.decode(screenBefore)
        var scored: [(line: String, distance: Double)] = []
        while sqlite3_step(stmt) == SQLITE_ROW {
            let action = sqlite3_column_text(stmt, 0).map { String(cString: $0) } ?? ""
            let target = sqlite3_column_text(stmt, 1).map { String(cString: $0) } ?? ""
            let changed = sqlite3_column_int64(stmt, 2) != 0
            let ok = sqlite3_column_int64(stmt, 3) != 0
            let why = sqlite3_column_text(stmt, 4).map { String(cString: $0) } ?? ""
            let storedSig = sqlite3_column_text(stmt, 5).map { String(cString: $0) } ?? ""

            let distance: Double
            if let wanted, let past = ScreenSignature.decode(storedSig) {
                distance = wanted.distance(to: past)
                guard distance <= ScreenSignature.sameScreenThreshold else { continue }
            } else if wanted == nil && storedSig == screenBefore {
                distance = 0            // legacy digest rows still match exactly
            } else {
                continue
            }

            scored.append((
                "\(action)\(target.isEmpty ? "" : " → \(target)"): "
                    + (changed ? "screen changed" : "NO CHANGE")
                    + (ok ? "" : " (failed)")
                    + (why.isEmpty ? "" : " — chosen because: \(String(why.prefix(120)))"),
                distance))
        }
        // Closest screens first: the most similar past state is the most
        // relevant precedent.
        return scored.sorted { $0.distance < $1.distance }
            .prefix(limit).map(\.line)
    }

    // MARK: - The vision tower's memory
    //
    // Structure in, meaning accumulated. Nothing is learned by training: a
    // screen's appearance is paired with the OS's own description of it, and
    // enough agreeing pairs become a recognition.

    func recordVisualGround(_ obs: VisionTower.Observation) {
        // A screen with no labels teaches nothing — that is an unlabelled
        // sample, and storing it only dilutes later agreement counts.
        guard !obs.labels.isEmpty else { return }
        try? ensureDB()
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, """
            INSERT INTO visual_ground (ts, app, signature, layout, window_title, labels)
            VALUES (?, ?, ?, ?, ?, ?)
            """, -1, &stmt, nil) == SQLITE_OK else { return }
        defer { sqlite3_finalize(stmt) }
        sqlite3_bind_double(stmt, 1, Date().timeIntervalSince1970)
        sqlite3_bind_text(stmt, 2, obs.app, -1, Self.sqliteTransient)
        sqlite3_bind_text(stmt, 3, obs.signature.encoded, -1, Self.sqliteTransient)
        sqlite3_bind_text(stmt, 4, obs.layout.encoded, -1, Self.sqliteTransient)
        sqlite3_bind_text(stmt, 5, obs.windowTitle, -1, Self.sqliteTransient)
        sqlite3_bind_text(stmt, 6, obs.labels.joined(separator: "\u{1F}"), -1, Self.sqliteTransient)
        sqlite3_step(stmt)
    }

    /// What this screen probably carries, or a named reason for not saying.
    ///
    /// Used when Accessibility cannot see — Chrome refusing to publish, a
    /// canvas app, a remote desktop. The mapping was learned while AX could
    /// see, which is what makes an answer possible at all here.
    func visualVerdict(for sig: ScreenSignature, layout: VisionTower.Layout,
                       app: String) -> VisionTower.Verdict {
        try? ensureDB()
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, """
            SELECT signature, layout, labels FROM visual_ground
            WHERE app = ? ORDER BY ts DESC LIMIT 400
            """, -1, &stmt, nil) == SQLITE_OK else { return .unknownNoEvidence }
        defer { sqlite3_finalize(stmt) }
        sqlite3_bind_text(stmt, 1, app, -1, Self.sqliteTransient)

        var neighbours: [(distance: Double, labels: [String])] = []
        var nearest = Double.infinity
        while sqlite3_step(stmt) == SQLITE_ROW {
            let sigText = sqlite3_column_text(stmt, 0).map { String(cString: $0) } ?? ""
            let layText = sqlite3_column_text(stmt, 1).map { String(cString: $0) } ?? ""
            let labText = sqlite3_column_text(stmt, 2).map { String(cString: $0) } ?? ""
            guard let past = ScreenSignature.decode(sigText) else { continue }

            // Appearance and layout both count: two screens can share a
            // brightness profile and be laid out completely differently.
            var d = sig.distance(to: past)
            if let pastLayout = VisionTower.Layout.decode(layText) {
                d = d * 0.7 + layout.distance(to: pastLayout) * 0.3
            }
            nearest = min(nearest, d)
            guard d <= VisionTower.kindThreshold else { continue }
            neighbours.append((d, labText.components(separatedBy: "\u{1F}")))
        }

        guard !neighbours.isEmpty else { return .unknownNoEvidence }

        // Agreement, not proximity, is what licenses an assertion. A label
        // carried by one neighbour is that screen's detail; one carried by
        // most of them is what this KIND of screen has.
        var tally: [String: Int] = [:]
        for n in neighbours { for l in Set(n.labels) where !l.isEmpty { tally[l, default: 0] += 1 } }
        let quorum = max(2, neighbours.count / 2)
        let agreed = tally.filter { $0.value >= quorum }
            .sorted { $0.value > $1.value }
            .map(\.key)

        guard neighbours.count >= VisionTower.minSupport, !agreed.isEmpty else {
            return .unknownInsufficient(nearest: nearest, support: neighbours.count)
        }
        return .recognised(labels: agreed, support: neighbours.count,
                           distance: neighbours.map(\.distance).min() ?? nearest)
    }

    /// A trajectory the PERSON drove — the ground truth the agent's motion
    /// is supposed to resemble. Recorded whole, without a target or a
    /// calibration, because what matters is its shape.
    // MARK: - The demonstration set, as something the user manages
    //
    // The puzzle used to appear mid-run, as an overlay, because the agent had
    // hit something it needed a human trajectory for. That only works if the
    // IDE is on screen and the person is sitting in front of it — which is
    // exactly the assumption everything else this week removed. The agent now
    // takes the screen, the window is deliberately not kept in front, and the
    // conversation may be happening on a phone. An overlay nobody is looking
    // at is not a prompt; it is a stall.
    //
    // So collection moves to a place the user goes on purpose, with time set
    // aside for it. That makes the demonstrations a dataset rather than an
    // interruption — and a dataset is something you can see the size of, add
    // to deliberately, and remove bad samples from.

    struct DemonstrationStats: Sendable {
        let human: Int
        let agent: Int
        let screens: [String]

        /// The motion model prefers human paths but will fall back to the
        /// agent's own, and imitating itself only compounds its own error.
        /// Below this, the model is mostly the agent copying the agent.
        static let enoughHuman = 8
        var sufficient: Bool { human >= Self.enoughHuman }
    }

    func demonstrationStats() -> DemonstrationStats {
        try? ensureDB()
        var human = 0, agent = 0
        var screens: [String] = []

        var stmt: OpaquePointer?
        if sqlite3_prepare_v2(db, """
            SELECT source, COUNT(*) FROM mouse_trace GROUP BY source
            """, -1, &stmt, nil) == SQLITE_OK {
            while sqlite3_step(stmt) == SQLITE_ROW {
                let src = sqlite3_column_text(stmt, 0).map { String(cString: $0) } ?? ""
                let n = Int(sqlite3_column_int64(stmt, 1))
                if src == "human" { human += n } else { agent += n }
            }
        }
        sqlite3_finalize(stmt)

        // Trajectories are only comparable within one screen geometry, so the
        // count that matters is per resolution, not overall.
        var s2: OpaquePointer?
        if sqlite3_prepare_v2(db, """
            SELECT screen_w, screen_h, COUNT(*) FROM mouse_trace
            WHERE source = 'human' GROUP BY screen_w, screen_h
            """, -1, &s2, nil) == SQLITE_OK {
            while sqlite3_step(s2) == SQLITE_ROW {
                let w = Int(sqlite3_column_double(s2, 0))
                let h = Int(sqlite3_column_double(s2, 1))
                let n = Int(sqlite3_column_int64(s2, 2))
                screens.append("\(w)×\(h): \(n)件")
            }
        }
        sqlite3_finalize(s2)

        return DemonstrationStats(human: human, agent: agent, screens: screens)
    }

    /// Remove the most recent human demonstration — the one just recorded,
    /// when the user knows they moved badly. Undo is why recording is safe to
    /// do casually.
    func deleteLastDemonstration() {
        try? ensureDB()
        exec("""
            DELETE FROM mouse_trace WHERE rowid = (
              SELECT rowid FROM mouse_trace WHERE source = 'human'
              ORDER BY ts DESC LIMIT 1
            )
            """)
    }

    /// Clear the human demonstrations. The agent's own traces are left: they
    /// are the fallback, and deleting them would leave nothing at all.
    func deleteAllDemonstrations() {
        try? ensureDB()
        exec("DELETE FROM mouse_trace WHERE source = 'human'")
    }

    func recordHumanDemonstration(points: [(x: Double, y: Double)],
                                  screenW: Double, screenH: Double) {
        guard points.count >= 3, let first = points.first, let last = points.last else { return }
        let path = points.suffix(64).map { "\(Int($0.x)),\(Int($0.y))" }.joined(separator: ";")
        recordMouseTrace(app: "human-demo", cell: "demo",
                         screenW: screenW, screenH: screenH,
                         reqX: first.x, reqY: first.y,
                         reachedX: last.x, reachedY: last.y,
                         calibX: 1.0, calibY: 1.0,
                         path: path, ok: true, source: "human")
    }

    /// The most recent trajectory that reached its target for this app,
    /// screen and neighbourhood. Screen size is part of the key because a
    /// calibration measured on one display means nothing on another.
    func mouseHint(app: String, cell: String,
                   screenW: Double, screenH: Double) -> MouseHint? {
        try? ensureDB()
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, """
            SELECT reached_x, reached_y, calib_x, calib_y, ts FROM mouse_trace
            WHERE app = ? AND cell = ? AND screen_w = ? AND screen_h = ? AND ok = 1
            ORDER BY ts DESC LIMIT 1
            """, -1, &stmt, nil) == SQLITE_OK else { return nil }
        defer { sqlite3_finalize(stmt) }
        sqlite3_bind_text(stmt, 1, app, -1, Self.sqliteTransient)
        sqlite3_bind_text(stmt, 2, cell, -1, Self.sqliteTransient)
        sqlite3_bind_double(stmt, 3, screenW)
        sqlite3_bind_double(stmt, 4, screenH)
        guard sqlite3_step(stmt) == SQLITE_ROW else { return nil }
        return MouseHint(reachedX: sqlite3_column_double(stmt, 0),
                         reachedY: sqlite3_column_double(stmt, 1),
                         calibX: sqlite3_column_double(stmt, 2),
                         calibY: sqlite3_column_double(stmt, 3),
                         ts: sqlite3_column_double(stmt, 4))
    }

    /// How many times a click at this neighbourhood has verifiably landed.
    /// Past a threshold the caller may stop rehearsing the approach — the
    /// route is established, and the human-like animation costs a second
    /// of visible cursor motion on every single click.
    func mouseSuccessCount(app: String, cell: String,
                           screenW: Double, screenH: Double) -> Int {
        try? ensureDB()
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, """
            SELECT COUNT(*) FROM mouse_trace
            WHERE app = ? AND cell = ? AND screen_w = ? AND screen_h = ? AND ok = 1
            """, -1, &stmt, nil) == SQLITE_OK else { return 0 }
        defer { sqlite3_finalize(stmt) }
        sqlite3_bind_text(stmt, 1, app, -1, Self.sqliteTransient)
        sqlite3_bind_text(stmt, 2, cell, -1, Self.sqliteTransient)
        sqlite3_bind_double(stmt, 3, screenW)
        sqlite3_bind_double(stmt, 4, screenH)
        guard sqlite3_step(stmt) == SQLITE_ROW else { return 0 }
        return Int(sqlite3_column_int64(stmt, 0))
    }

    // MARK: - The uncertainty of a human hand, as data

    /// How much a real pointer wanders on its way somewhere, measured
    /// rather than invented.
    ///
    /// The path generator used `Double.random(in: -50...50)` for its
    /// control point — a guess about human motion baked in as a constant.
    /// Every trajectory this Mac has actually driven is stored, so the
    /// same quantity can be measured: how far, in proportion to the
    /// distance travelled, the pointer strayed from the straight line.
    struct MotionModel: Sendable {
        /// Peak perpendicular deviation ÷ straight-line distance.
        let jitterRatio: Double
        /// Where along the chord that peak falls (0…1). A hand does not
        /// bulge symmetrically; the curve leans toward where it started.
        let peakAt: Double
        /// How far past the target the pointer travelled before settling,
        /// as a fraction of the distance. 0 when the demonstrations did
        /// not overshoot.
        let overshoot: Double
        /// Travelled distance ÷ straight-line distance. Above 1 for any
        /// real hand.
        let lengthRatio: Double
        /// Normalized progress at equally spaced moments — the shape of
        /// slow-fast-slow. Sampled at 9 points including both ends, so
        /// index 4 is the halfway moment: a machine would read 0.5 there,
        /// a hand reads higher.
        let easing: [Double]
        /// Waypoints a real trajectory used, averaged.
        let steps: Int
        /// Trajectories the numbers came from — below a handful, treat
        /// the model as a hint rather than a measurement.
        let samples: Int
        /// True when human demonstrations, not the agent's own paths,
        /// dominated the sample.
        let fromHuman: Bool

        /// Progress at fraction `u` of the way through the movement.
        func progress(at u: Double) -> Double {
            guard easing.count >= 2 else { return u }
            let clamped = min(max(u, 0), 1)
            let scaled = clamped * Double(easing.count - 1)
            let i = min(Int(scaled), easing.count - 2)
            let frac = scaled - Double(i)
            return easing[i] + (easing[i + 1] - easing[i]) * frac
        }
    }

    /// Human demonstrations dominate the sample the moment any exist:
    /// an agent imitating its own synthetic motion would only compound
    /// whatever was already wrong with it. 'human' sorts before 'agent',
    /// so the ordering does that without a second query.
    func motionModel(screenW: Double, screenH: Double, limit: Int = 50) -> MotionModel? {
        try? ensureDB()
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, """
            SELECT path, source FROM mouse_trace
            WHERE screen_w = ? AND screen_h = ? AND ok = 1
            -- Human demonstrations FIRST. This was `ORDER BY source ASC`,
            -- and 'agent' sorts before 'human', so the limit was filled with
            -- the agent's own traces and the demonstrations were never read
            -- once a resolution had 50 agent clicks — which is one session.
            -- The comment above this query said human demos dominate; the
            -- query did the exact opposite, and the agent has been imitating
            -- itself, compounding its own error, the whole time.
            -- Written out rather than DESC so it does not depend on where
            -- a future source value lands in the alphabet.
            ORDER BY CASE source WHEN 'human' THEN 0 ELSE 1 END, ts DESC LIMIT ?
            """, -1, &stmt, nil) == SQLITE_OK else { return nil }
        defer { sqlite3_finalize(stmt) }
        sqlite3_bind_double(stmt, 1, screenW)
        sqlite3_bind_double(stmt, 2, screenH)
        sqlite3_bind_int64(stmt, 3, Int64(limit))

        let easingSamples = 9
        var ratios: [Double] = []
        var peaks: [Double] = []
        var overshoots: [Double] = []
        var lengths: [Double] = []
        var easingSum = [Double](repeating: 0, count: easingSamples)
        var stepCounts: [Int] = []
        var humanCount = 0

        while sqlite3_step(stmt) == SQLITE_ROW {
            guard let raw = sqlite3_column_text(stmt, 0).map({ String(cString: $0) }) else { continue }
            let source = sqlite3_column_text(stmt, 1).map { String(cString: $0) } ?? "agent"
            let pts: [(Double, Double)] = raw.split(separator: ";").compactMap {
                let xy = $0.split(separator: ",")
                guard xy.count == 2, let x = Double(xy[0]), let y = Double(xy[1]) else { return nil }
                return (x, y)
            }
            guard pts.count >= 3, let first = pts.first, let last = pts.last else { continue }
            let dx = last.0 - first.0, dy = last.1 - first.1
            let span = (dx * dx + dy * dy).squareRoot()
            guard span > 20 else { continue }   // a nudge has no shape to measure

            // Deviation from the chord: how big, and where along it.
            var peak = 0.0
            var peakAt = 0.5
            var maxProjection = 0.0
            for (i, p) in pts.enumerated() where i > 0 && i < pts.count - 1 {
                let perp = abs(dx * (p.1 - first.1) - dy * (p.0 - first.0)) / span
                if perp > peak {
                    peak = perp
                    // Projection onto the chord, as a fraction of it.
                    peakAt = ((p.0 - first.0) * dx + (p.1 - first.1) * dy) / (span * span)
                }
                let proj = ((p.0 - first.0) * dx + (p.1 - first.1) * dy) / (span * span)
                maxProjection = max(maxProjection, proj)
            }
            ratios.append(peak / span)
            peaks.append(min(max(peakAt, 0.05), 0.95))
            // Anything beyond the endpoint is overshoot the hand corrected.
            overshoots.append(max(0, maxProjection - 1.0))

            // Travelled distance, and the shape of progress over time. The
            // waypoints are sampled at a fixed interval, so their spacing
            // IS the speed: cumulative distance against index gives the
            // slow-fast-slow curve without needing timestamps.
            var cumulative: [Double] = [0]
            var travelled = 0.0
            for i in 1..<pts.count {
                travelled += ((pts[i].0 - pts[i-1].0) * (pts[i].0 - pts[i-1].0)
                            + (pts[i].1 - pts[i-1].1) * (pts[i].1 - pts[i-1].1)).squareRoot()
                cumulative.append(travelled)
            }
            guard travelled > 0 else { continue }
            lengths.append(travelled / span)
            for k in 0..<easingSamples {
                let u = Double(k) / Double(easingSamples - 1)
                let idx = u * Double(cumulative.count - 1)
                let lo = min(Int(idx), cumulative.count - 2)
                let f = idx - Double(lo)
                let value = cumulative[lo] + (cumulative[lo + 1] - cumulative[lo]) * f
                easingSum[k] += value / travelled
            }
            stepCounts.append(pts.count)
            if source == "human" { humanCount += 1 }
        }
        guard !ratios.isEmpty else { return nil }
        let n = Double(ratios.count)
        var easing = easingSum.map { $0 / n }
        easing[0] = 0
        easing[easingSamples - 1] = 1
        return MotionModel(
            jitterRatio: ratios.reduce(0, +) / n,
            peakAt: peaks.reduce(0, +) / n,
            overshoot: overshoots.reduce(0, +) / n,
            lengthRatio: lengths.isEmpty ? 1.0 : lengths.reduce(0, +) / Double(lengths.count),
            easing: easing,
            steps: max(8, stepCounts.reduce(0, +) / stepCounts.count),
            samples: ratios.count,
            fromHuman: humanCount * 2 >= ratios.count)
    }

    /// Any calibration that worked on this display recently, regardless of
    /// where on screen it was measured — the fallback when the probe fails
    /// somewhere this app has never clicked before.
    func lastGoodCalibration(screenW: Double, screenH: Double) -> (x: Double, y: Double)? {
        try? ensureDB()
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, """
            SELECT calib_x, calib_y FROM mouse_trace
            WHERE screen_w = ? AND screen_h = ? AND ok = 1
            ORDER BY ts DESC LIMIT 1
            """, -1, &stmt, nil) == SQLITE_OK else { return nil }
        defer { sqlite3_finalize(stmt) }
        sqlite3_bind_double(stmt, 1, screenW)
        sqlite3_bind_double(stmt, 2, screenH)
        guard sqlite3_step(stmt) == SQLITE_ROW else { return nil }
        return (sqlite3_column_double(stmt, 0), sqlite3_column_double(stmt, 1))
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
        try ensureDB()
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
    // MARK: - Facts that replace themselves
    //
    // The consolidators run on every attempt past their threshold, and `add`
    // appends unconditionally. So a fact that is re-derived writes a new,
    // near-identical node each time:
    //
    //   Safari を操作するには menu が有効（11/12 成功）。
    //   Safari を操作するには menu が有効（12/13 成功）。
    //   Safari を操作するには menu が有効（13/14 成功）。
    //
    // One per click, forever. Recall returns k results, so after a busy
    // session all k are the same sentence at different counts, and genuinely
    // different knowledge is crowded out of every answer. The store grows and
    // gets less useful — the opposite of accumulating.
    //
    // A consolidated fact is a CURRENT SUMMARY, not an event: there should be
    // exactly one live copy. Older versions are quarantined rather than
    // deleted, because the vector file is append-only and index-aligned with
    // the node rows — rewriting it to remove one entry would renumber
    // everything. `search` already skips quarantined nodes, so exclusion is
    // enough, and the superseded text stays on disk as history.

    private static let factKeyPrefix = "factkey:"

    /// Write a fact that replaces any previous version of itself.
    func addFact(key: String, text: String, concepts: [String]) async throws {
        supersedeFact(key: key)
        try await add(text: text, concepts: concepts + [Self.factKeyPrefix + key])
    }

    /// Retire earlier copies of one fact.
    private func supersedeFact(key: String) {
        try? ensureLoaded()
        let tag = Self.factKeyPrefix + key
        var retired: [Int] = []
        for i in nodes.indices where !nodes[i].quarantined && nodes[i].concepts.contains(tag) {
            nodes[i].quarantined = true
            retired.append(nodes[i].id)
        }
        guard !retired.isEmpty else { return }

        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, "UPDATE nodes SET quarantined = 1 WHERE id = ?",
                                 -1, &stmt, nil) == SQLITE_OK else { return }
        defer { sqlite3_finalize(stmt) }
        for id in retired {
            sqlite3_reset(stmt)
            sqlite3_bind_int64(stmt, 1, Int64(id))
            sqlite3_step(stmt)
        }
    }

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
