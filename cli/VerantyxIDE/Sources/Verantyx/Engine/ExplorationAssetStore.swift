import Foundation

// MARK: - ExplorationAssetStore
//
// Infinite exploration assets for JGEN Act — Voyager-style substrate reuse.
//
// Failures leave logs (eternal + JCross wisdom + vector-bus stamp).
// Success forges a compact SkillLibrary macro (`source: exploration-asset`)
// so the next similar goal gets `[PRIOR_ASSET]` guidance (“一発で行ける”).
//
// Deliberately NOT a parallel mega-system: persistence is SkillLibrary +
// EternalMemoryStore + SessionMemoryArchiver — same sinks AgentLoop / FORGE_SKILL use.

enum ExplorationAssetStore {

    static let sourceTag = "exploration-asset"
    static let forgedBy = "jgen-act-exploration"
    static let tagExploration = "exploration-asset"
    static let tagJgenAct = "jgen-act"

    // MARK: - Tool → macro payload line

    /// Bracket tag suitable for SkillNode.macro payload / PRIOR_ASSET steps.
    nonisolated static func toolTag(_ tool: AgentTool) -> String? {
        switch tool {
        case .openApp(let name):
            return "[OPEN_APP: \(name)]"
        case .desktopSnapshot:
            return "[DESKTOP_SNAPSHOT]"
        case .desktopAct(let action):
            return "[DESKTOP_ACT: \(action)]"
        case .axAct(let action):
            return "[AX_ACT: \(action)]"
        case .pastePayload:
            return "[PASTE_PAYLOAD]"
        case .waitUntilStable(let stable, let timeout):
            return "[WAIT_UNTIL_STABLE: \(stable) \(timeout)]"
        default:
            return nil
        }
    }

    // MARK: - Goal helpers

    nonisolated static func goalIsJapanese(_ goal: String) -> Bool {
        for s in goal.unicodeScalars {
            let v = s.value
            if (0x3040...0x30FF).contains(v) || (0x4E00...0x9FFF).contains(v) {
                return true
            }
        }
        return false
    }

    nonisolated static func goalFingerprint(_ goal: String) -> String {
        // Keep letters/digits and CJK so Japanese goals stay stable.
        let mapped = goal.lowercased().map { c -> Character in
            if c.isLetter || c.isNumber { return c }
            if let v = c.unicodeScalars.first?.value,
               (0x3040...0x30FF).contains(v) || (0x4E00...0x9FFF).contains(v) {
                return c
            }
            return "_"
        }
        let collapsed = String(mapped)
            .replacingOccurrences(of: "_+", with: "_", options: .regularExpression)
            .trimmingCharacters(in: CharacterSet(charactersIn: "_"))
        if collapsed.count < 2 {
            var hasher = Hasher()
            hasher.combine(goal)
            let hex = String(UInt64(bitPattern: Int64(hasher.finalize())), radix: 16)
            return String(hex.prefix(12))
        }
        return String(collapsed.prefix(48))
    }

    nonisolated static func skillName(for goal: String, appHint: String?) -> String {
        var parts = ["act"]
        if let app = appHint?.trimmingCharacters(in: .whitespacesAndNewlines), !app.isEmpty {
            parts.append(sanitize(app))
        }
        parts.append(goalFingerprint(goal))
        return String(parts.joined(separator: "_").prefix(56))
    }

    nonisolated private static func sanitize(_ s: String) -> String {
        let mapped = s.lowercased().map { c -> Character in
            (c.isLetter || c.isNumber) ? c : "_"
        }
        return String(String(mapped).prefix(24))
    }

    // MARK: - Failure log

    /// Structured exploration failure — persists so next runs can avoid the dead end.
    static func logFailure(
        goal: String,
        actionTried: String,
        result: String,
        turn: Int,
        sessionId: String?
    ) async {
        let fp = goalFingerprint(goal)
        let ts = ISO8601DateFormatter().string(from: Date())
        let resultClass = classifyResult(result)
        let clipped = String(result.prefix(280))
            .replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
        let line = """
        [探索資産/fail] fp=\(fp) turn=\(turn) action=\(actionTried) class=\(resultClass) at=\(ts)
        detail: \(clipped)
        """

        try? await EternalMemoryStore.shared.add(
            text: line,
            concepts: [tagExploration, tagJgenAct, "exploration-fail", resultClass]
        )

        let chunkId = "explore_fail_\(fp)_\(turn)_\(Int(Date().timeIntervalSince1970) % 100000)"
        SessionMemoryArchiver.shared.archiveWisdomChunk(
            chunkId: chunkId,
            taskTitle: "ExploreFail \(fp)",
            l1: "🗂 fail \(actionTried) → \(resultClass)",
            l2: "OP.FACT(\"explore_fp\", \"\(fp)\")\nOP.FACT(\"explore_action\", \"\(String(actionTried.prefix(80)))\")\nOP.FACT(\"explore_class\", \"\(resultClass)\")",
            l3: line
        )

        await JGenVectorBusMemory.stampObservation(
            label: "explore_fail",
            detail: line,
            sessionId: sessionId,
            stepIndex: turn,
            actionLabel: actionTried,
            changedRegion: nil,
            concepts: [tagExploration, "exploration-fail", tagJgenAct]
        )
    }

    nonisolated static func classifyResult(_ result: String) -> String {
        let u = result.uppercased()
        if u.contains("MISMATCH") { return "mismatch" }
        if u.contains("NO VISUAL CHANGE") { return "no_visual_change" }
        if u.contains("DESKTOP_BLOCKED") || u.contains("BLOCKED") { return "blocked" }
        if u.contains("ERROR") { return "error" }
        if u.contains("FAILED") { return "failed" }
        return "other"
    }

    nonisolated static func looksLikeFailure(_ observation: String) -> Bool {
        let u = observation.uppercased()
        return u.contains("MISMATCH")
            || u.contains("NO VISUAL CHANGE")
            || u.contains("DESKTOP_BLOCKED")
            || (u.contains("ERROR") && !u.contains("NO ERROR"))
            || u.contains("(BLOCKED")
            || u.contains("(REJECTED")
    }

    // MARK: - Forge on success

    /// Compact reusable asset from a successful Act DONE path.
    @discardableResult
    static func forgeOnSuccess(
        goal: String,
        appHint: String?,
        successfulTags: [String],
        notes: String
    ) async -> SkillNode? {
        let tags = successfulTags
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        // Need at least one act-ish step (open / sense / act). Snapshots alone are weak.
        let meaningful = tags.filter {
            $0.hasPrefix("[OPEN_APP:") || $0.hasPrefix("[AX_ACT:")
                || $0.hasPrefix("[DESKTOP_ACT:") || $0.hasPrefix("[PASTE_PAYLOAD")
        }
        guard !meaningful.isEmpty else { return nil }

        await SkillLibrary.shared.loadIndex()
        let name = skillName(for: goal, appHint: appHint)
        let desc = String(goal.prefix(120))
        var nodeTags = [tagExploration, tagJgenAct, "voyager"]
        if let app = appHint, !app.isEmpty {
            nodeTags.append(sanitize(app))
        }

        var node = SkillNode(
            name: name,
            description: desc.isEmpty ? "Act exploration path" : desc,
            version: 1,
            createdAt: Date(),
            updatedAt: Date(),
            tags: nodeTags,
            executionType: .macro,
            payload: Array(tags.prefix(16))
        )
        node.source = sourceTag
        node.forgedBy = forgedBy
        if !notes.isEmpty {
            node.kanjiTags = String(notes.prefix(80))
        }

        let saved = await SkillLibrary.shared.save(node)

        let stamp = """
        [探索資産/forge] name=\(saved.name) v\(saved.version) steps=\(saved.payload.count)
        goal: \(String(goal.prefix(160)))
        path: \(saved.payload.joined(separator: " → "))
        """
        try? await EternalMemoryStore.shared.add(
            text: stamp,
            concepts: [tagExploration, tagJgenAct, "exploration-forge"]
        )
        return saved
    }

    // MARK: - Recall

    /// Top similar exploration assets for this goal (SkillLibrary TF-IDF + source filter).
    static func recall(for goal: String, topK: Int = 2) async -> [SkillNode] {
        await SkillLibrary.shared.loadIndex()
        let hits = await SkillLibrary.shared.search(query: goal, topK: max(topK * 4, 8))
        let filtered = hits.filter { node in
            node.source == sourceTag
                || node.forgedBy == forgedBy
                || node.tags.contains(tagExploration)
                || node.name.hasPrefix("act_")
        }
        if !filtered.isEmpty {
            return Array(filtered.prefix(topK))
        }
        // Soft fallback: any skill whose payload looks like Act tools.
        let actish = hits.filter { node in
            node.payload.contains { line in
                line.contains("OPEN_APP") || line.contains("DESKTOP_") || line.contains("AX_ACT")
            }
        }
        return Array(actish.prefix(topK))
    }

    nonisolated static func formatPriorAsset(_ node: SkillNode) -> String {
        let steps = node.payload.prefix(12).joined(separator: "\n")
        return """
        [PRIOR_ASSET]
        name: \(node.name) v\(node.version)
        description: \(node.description)
        wins: \(node.successCount) fails: \(node.failCount)
        Prefer this learned path (adapt AX ids if UI shifted). On MISMATCH explore then success forges an update.
        steps:
        \(steps)
        [/PRIOR_ASSET]
        """
    }

    nonisolated static func hintFromPriorAsset(_ node: SkillNode?) -> String? {
        guard let node, let first = node.payload.first else { return nil }
        return "PRIOR_ASSET \(node.name): prefer \(first) then follow listed steps; do not invent coords."
    }
}

// MARK: - ExplorationNarrator
//
// Occasional 現状説明 + short 独り言 during long Act exploration.
// Same channel as `🛠 [L2 JGEN Act]…` (LoopEvent.systemLog).

struct ExplorationNarrator: Sendable {
    let japanese: Bool
    private var lastStatusTurn: Int = 0
    private var lastMutterTurn: Int = 0
    /// Status at most once per this many turns.
    private let statusEvery: Int = 2
    /// Mutter rarer than status.
    private let mutterEvery: Int = 3

    init(goal: String) {
        japanese = ExplorationAssetStore.goalIsJapanese(goal)
        lastStatusTurn = 0
        lastMutterTurn = 0
    }

    /// User-visible status line (現状説明). Nil when cadence says wait.
    mutating func statusIfDue(
        turn: Int,
        openAppSucceeded: Bool,
        appHint: String?,
        lastObservation: String?,
        force: Bool = false
    ) -> String? {
        let due = force || (turn - lastStatusTurn) >= statusEvery
        guard due, turn > 0 else { return nil }
        lastStatusTurn = turn

        let app = appHint ?? (japanese ? "アプリ" : "app")
        let obs = lastObservation ?? ""
        let u = obs.uppercased()

        let body: String
        if japanese {
            if !openAppSucceeded {
                body = "\(app) を開こうとしている"
            } else if u.contains("MISMATCH") || u.contains("NO VISUAL CHANGE") {
                body = "\(app) は開いた。さっきの操作は外れ — 別の手がかりを探す"
            } else if u.contains("OPEN") || u.contains("OPENED") {
                body = "\(app) は開いた。画面を読んで次の一手を探している"
            } else if u.contains("UI MAP") || u.contains("SNAPSHOT") || u.contains("SEMANTIC") {
                body = "画面マップを得た。目標に効く操作を選んでいる"
            } else if u.contains("PASTE") {
                body = "ペイロードを貼った。結果を確認している"
            } else {
                body = "探索中（ターン \(turn)）。失敗はログに残し、成功したら資産化する"
            }
            return "🗣 [現状] \(body)"
        } else {
            if !openAppSucceeded {
                body = "Trying to open \(app)"
            } else if u.contains("MISMATCH") || u.contains("NO VISUAL CHANGE") {
                body = "\(app) is open; last action missed — trying another cue"
            } else if u.contains("OPEN") || u.contains("OPENED") {
                body = "\(app) opened; sensing the screen for the next move"
            } else if u.contains("UI MAP") || u.contains("SNAPSHOT") || u.contains("SEMANTIC") {
                body = "Got a UI map; picking an action toward the goal"
            } else if u.contains("PASTE") {
                body = "Pasted payload; checking the result"
            } else {
                body = "Exploring (turn \(turn)). Failures log; success becomes a reusable asset"
            }
            return "🗣 [status] \(body)"
        }
    }

    /// Short self-talk (独り言). Rarer than status.
    mutating func mutterIfDue(
        turn: Int,
        hadMismatch: Bool,
        hadPriorAsset: Bool,
        force: Bool = false
    ) -> String? {
        let due = force || hadMismatch || (turn - lastMutterTurn) >= mutterEvery
        // Keep mutter rarer than status: require at least 2 turns since last mutter
        // unless it's a mismatch and we haven't muttered this turn window.
        guard due, turn > 0 else { return nil }
        if !force && !hadMismatch && (turn - lastMutterTurn) < mutterEvery {
            return nil
        }
        // Don't mutter on the exact same turn we just status'd unless mismatch.
        if turn == lastStatusTurn && !hadMismatch && !force {
            return nil
        }
        lastMutterTurn = turn

        if japanese {
            if hadPriorAsset && hadMismatch {
                return "💭 前はここに成功した…今は違うかも"
            }
            if hadMismatch {
                return "💭 ここじゃないな"
            }
            if hadPriorAsset {
                return "💭 覚えている道を辿ってみる"
            }
            let pool = ["💭 もう少し探してみるか", "💭 別の入り口があるはず", "💭 焦らず、観測を積む"]
            return pool[turn % pool.count]
        } else {
            if hadPriorAsset && hadMismatch {
                return "💭 Prior path worked before — UI may have shifted"
            }
            if hadMismatch {
                return "💭 Not this one"
            }
            if hadPriorAsset {
                return "💭 Following a remembered path"
            }
            let pool = ["💭 Keep sensing", "💭 Another angle…", "💭 Log the miss, try again"]
            return pool[turn % pool.count]
        }
    }

    mutating func forgeAnnounce(skillName: String) -> String {
        if japanese {
            return "🗂 [探索資産] 成功パスを記録: \(skillName) — 次回は一発を狙う"
        }
        return "🗂 [探索資産] forged success path: \(skillName) — next similar goal can one-shot"
    }

    mutating func recallAnnounce(skillName: String) -> String {
        if japanese {
            return "🗂 [探索資産] 類似成功を想起: \(skillName)"
        }
        return "🗂 [探索資産] recalled prior success: \(skillName)"
    }

    mutating func failAnnounce(action: String) -> String {
        let short = String(action.prefix(40))
        if japanese {
            return "🗂 [探索資産] 失敗を記録: \(short)"
        }
        return "🗂 [探索資産] logged failure: \(short)"
    }
}
