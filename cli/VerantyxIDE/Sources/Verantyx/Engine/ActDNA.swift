import Foundation

// MARK: - ActDNA（足場 DNA / Body scaffold invariants）
//
// 【最低限の手を壊すな / Do not break minimal limbs】
// このファイルは Act の**先天的不変条件**の単一ファサード。
// 実装の詳細は PromptBudget / MissionKindClassifier / HierarchicalExploreGate /
// ExplorationAssetStore / SensePixelPolicy / InstalledAppIndex に残し、
// 呼び出し側はここ経由で「何が許されるか」を読む。
//
// ━━━ Invariant checklist（未来のエージェントへ）━━━
// EN / JA — bolt site scripts here and you fight DNA:
//
// 1. Limbs (thin, fixed) — only OPEN_APP / SENSE(DESKTOP_SNAPSHOT) / ACT
//    (DESKTOP_ACT|AX_ACT) / PASTE_PAYLOAD / DONE.
//    肢は増やさない。Hierarchical choice は policy（一時停止）、新肢ではない。
//    Do NOT grow a verb catalog, Gemini/Teams/GitHub bootstraps, or per-app flows.
//
// 2. Honesty — never report success if the limb failed; phantom sessions forbidden.
//    OPEN_APP: installed resolve + process running, else MISMATCH.
//
// 3. Budget / body boundary — PromptBudget on all model/encode paths;
//    no mission prose into search bar; procedural → open+sense only.
//
// 4. Directive handoff — Act sees short [DIRECTIVE] + optional [VECTOR_STEER]
//    (cosine prior directives) + PRIOR_ASSET + OBSERVATIONS, not the full
//    essay every turn. The directive string is also stamped into JGEN eternal
//    space so future missions retrieve directive-shaped memories by cosine.
//
// 5. MissionKind — deterministic thin gate before 0.5B freeform;
//    prior asset label; JGEN classify = tie-break only.
//
// 6. Exploration assets — fail log / success forge / recall with mission_kind;
//    vector bus stamp.
//
// 7. Hierarchical explore — default ON; list → ask user → resume;
//    general heuristics only (no site-specific DOM).
//
// 8. Memory/GPU safety — JGenGPUSafety / quiet capture / purge on unload remain.
//
// 9. Structured events — VeraRuntimeEvent kinds stay shared CLI + future GUI language.
//
// 10. Gap-driven persistence — ActGapController is the loop contract:
//     openGap → while open: act → on mismatch/cycle update gap → on success resolve.
//     GAP observations are not terminal. Identical-limb cycles are honesty brakes
//     (force a different limb), not early surrender. Vera GapGraph MCP is best-effort;
//     the local mirror always drives the body when MCP is down.
//
// InstalledAppIndex = proprioception for OPEN_APP, not mission scripting.
// Defaults ON: vectorOnlySense, hierarchicalExplore; act turns configurable.

// MARK: - ActGapController (GapNode-shaped loop driver)

/// Local GapNode mirror that **drives** Act persistence.
/// Vera GapGraph (`bootstrap_unknown_task` / `record_ui_transition`) is best-effort
/// sync — never required for the loop to keep trying.
struct ActGapController: Sendable {
    enum Status: String, Sendable {
        case open = "DETECTED"
        case inProgress = "ACQUIRING"
        case resolved = "RESOLVED"
        case blocked = "BLOCKED"
    }

    var subject: String
    var status: Status
    var gapId: String?
    var failureType: String?
    var lastAction: String?
    var mismatchCount: Int
    var distinctStrategies: Set<String>
    var cycleHits: Int

    /// True while the mission gap is unresolved — forbids surrender DONE / early quit.
    var isOpen: Bool {
        status == .open || status == .inProgress
    }

    static func open(subject: String, gapId: String? = nil) -> ActGapController {
        ActGapController(
            subject: String(subject.prefix(120)),
            status: .open,
            gapId: gapId,
            failureType: nil,
            lastAction: nil,
            mismatchCount: 0,
            distinctStrategies: [],
            cycleHits: 0
        )
    }

    mutating func noteMismatch(action: String, failureType: String = "mismatch") {
        status = .inProgress
        lastAction = String(action.prefix(80))
        self.failureType = failureType
        mismatchCount += 1
        if !action.isEmpty { distinctStrategies.insert(action) }
    }

    mutating func noteCycle(cycleKey: String) {
        status = .inProgress
        lastAction = String(cycleKey.prefix(80))
        failureType = "cycle"
        cycleHits += 1
        distinctStrategies.insert("cycle:\(cycleKey)")
    }

    mutating func noteStrategy(_ key: String) {
        if !key.isEmpty { distinctStrategies.insert(key) }
        if status == .open { status = .inProgress }
    }

    mutating func resolve(via: String = "DONE") {
        status = .resolved
        lastAction = via
        failureType = nil
    }

    /// Only after distinct strategies are exhausted (caller decides threshold).
    mutating func markBlocked(reason: String) {
        status = .blocked
        failureType = reason
    }

    /// Observation line for the next ChatML turn (not a stop signal).
    func observationLine() -> String {
        let gid = gapId.map { " id=\($0)" } ?? ""
        let fail = failureType.map { " failure=\($0)" } ?? ""
        let last = lastAction.map { " last=\(String($0.prefix(40)))" } ?? ""
        return "GAP subject=\"\(subject)\" status=\(status.rawValue)\(gid)\(fail) streak=\(mismatchCount) strategies=\(distinctStrategies.count)\(last) — keep trying a DIFFERENT limb until RESOLVED or turn budget"
    }

    /// True when DONE text looks like premature surrender while gap still open.
    static func looksLikeSurrenderDONE(_ message: String) -> Bool {
        let t = message.lowercased()
        let keys = [
            "couldn't", "could not", "cannot", "can't", "unable", "failed", "give up",
            "できません", "できなかった", "失敗", "諦め", "無理", "わからない", "分からない",
            "開けません", "送れません", "clone", "クローン",
        ]
        return keys.contains { t.contains($0) }
    }
}

// MARK: - Action cycle detection (length 2–3)

enum ActCycleDetector {
    /// Detect ABAB… (len 2) or ABCABC… (len 3) in the recent action-key ring.
    /// Returns the repeating unit when a cycle of at least `minRepeats` full periods is present.
    nonisolated static func detectCycle(
        recentKeys: [String],
        period: Int? = nil,
        minRepeats: Int = 2
    ) -> [String]? {
        let keys = recentKeys.filter { !$0.isEmpty }
        guard keys.count >= 4 else { return nil }
        let periods: [Int]
        if let period { periods = [period] }
        else { periods = [2, 3] }
        for p in periods {
            let need = p * minRepeats
            guard keys.count >= need else { continue }
            let window = Array(keys.suffix(need))
            let unit = Array(window.prefix(p))
            guard Set(unit).count == p else { continue } // trivial AAAA is identical-streak, not ABAB
            var ok = true
            for i in 0..<need {
                if window[i] != unit[i % p] { ok = false; break }
            }
            if ok { return unit }
        }
        return nil
    }

    nonisolated static func cycleKey(_ unit: [String]) -> String {
        unit.joined(separator: "↔")
    }
}

/// Fixed Act limb set — the body's thin hands. Not a product catalog.
enum ActLimb: String, Sendable, CaseIterable {
    case openApp = "OPEN_APP"
    case sense = "SENSE"           // DESKTOP_SNAPSHOT / AX map → text/concepts → vectors
    case act = "ACT"               // DESKTOP_ACT / AX_ACT
    case pastePayload = "PASTE_PAYLOAD"
    case done = "DONE"
}

/// Central DNA façade for desktop Act invariants.
enum ActDNA {

    // MARK: - Directives (short handoff to the tiny executor)

    struct Directives: Sendable {
        let kind: MissionKind
        let goalShort: String
        let openHint: String?
        let priorAssets: [SkillNode]
        let priorAssetTags: String
        let priorAssetBlock: String?
        let hierarchicalPending: Bool
        let selected: String?
        let directiveBlock: String
        /// Short cosine neighbors of prior DIRECTIVE stamps (optional).
        let vectorSteerBlock: String?
        let missionPayload: String?
        let vectorOnlySense: Bool
        let hierarchicalExplore: Bool

        var priorAsset: SkillNode? { priorAssets.first }
    }

    /// Outcome of honesty check on a limb observation.
    enum LimbVerdict: Sendable, Equatable {
        case ok
        case mismatch(reason: String)

        var isOk: Bool {
            if case .ok = self { return true }
            return false
        }
    }

    // MARK: - Settings defaults (DNA ON)

    /// Vector-only sense default — no pixel inject to model.
    nonisolated static var isVectorOnlySense: Bool { CouncilSettingsStore.isVectorOnlySense }

    /// Hierarchical explore default ON.
    nonisolated static var isHierarchicalExplore: Bool {
        CouncilSettingsStore.isHierarchicalExplore || HierarchicalExploreGate.isEnabled
    }

    /// Effective Act turn budget (unlimited → practical cap).
    nonisolated static var resolvedActMaxTurns: Int { CouncilSettingsStore.resolvedActMaxTurns }

    // MARK: - prepareActContext

    /// Build the short directive handoff for an Act run.
    /// Recalls exploration assets; stamps directive into JGEN vector space;
    /// never embeds the full mission essay.
    static func prepareActContext(
        goal: String,
        selected: String? = nil,
        hierarchicalPending: Bool = false,
        missionPayload: String? = nil,
        kind: MissionKind = .act,
        openHintOverride: String? = nil,
        recallPriorAssets: Bool = true,
        sessionId: String? = nil
    ) async -> Directives {
        let bounded = PromptBudget.truncateForModel(goal)
        let goalShort = MissionKindClassifier.goalShort(from: bounded)
        let openHint = openHintOverride
            ?? JGenActAgent.extractOpenAppName(from: bounded)

        var priors: [SkillNode] = []
        var priorTags = ""
        var priorBlock: String? = nil
        if recallPriorAssets {
            priors = await ExplorationAssetStore.recall(for: bounded, topK: 2)
            priorTags = ExplorationAssetStore.directivePriorTags(priors)
            priorBlock = priors.first.map { ExplorationAssetStore.formatPriorAsset($0) }
        }

        let sel = selected?.trimmingCharacters(in: .whitespacesAndNewlines)
        let directiveBlock = ExplorationAssetStore.formatDirective(
            goalShort: goalShort,
            openHint: openHint,
            priorTags: priorTags,
            selected: (sel?.isEmpty == false) ? sel : nil
        )

        // Prior similar directives (VECTOR_STEER) before stamping this mission,
        // so cosine neighbors are earlier runs — not only the stamp we just wrote.
        let vectorSteer = await JGenVectorBusMemory.recallDirectiveSteer(
            for: goalShort, k: 2
        )
        await JGenVectorBusMemory.stampDirective(
            compactText: directiveBlock,
            goalShort: goalShort,
            kind: kind,
            openHint: openHint,
            sessionId: sessionId
        )
        EternalVeraBridge.shareToVera(
            "directive \(kind.rawValue): \(String(goalShort.prefix(100)))",
            kind: .directive
        )

        let payload: String?
        if let missionPayload, !missionPayload.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            payload = missionPayload
        } else {
            payload = PromptBudget.extractMissionPayload(from: goal)
        }

        return Directives(
            kind: kind,
            goalShort: goalShort,
            openHint: openHint,
            priorAssets: priors,
            priorAssetTags: priorTags,
            priorAssetBlock: priorBlock,
            hierarchicalPending: hierarchicalPending,
            selected: sel,
            directiveBlock: directiveBlock,
            vectorSteerBlock: vectorSteer.isEmpty ? nil : vectorSteer,
            missionPayload: payload,
            vectorOnlySense: isVectorOnlySense,
            hierarchicalExplore: isHierarchicalExplore
        )
    }

    // MARK: - validateLimbResult (honesty)

    /// Never report success if the limb failed. Phantom OPEN_APP sessions forbidden.
    nonisolated static func validateLimbResult(tool: AgentTool, result: String) -> LimbVerdict {
        let trimmed = result.trimmingCharacters(in: .whitespacesAndNewlines)
        let u = trimmed.uppercased()

        switch tool {
        case .openApp:
            if looksLikeOpenAppMismatch(trimmed) {
                return .mismatch(reason: "OPEN_APP MISMATCH — unresolved or not running")
            }
            if looksLikeOpenAppSuccess(trimmed) {
                return .ok
            }
            // Ambiguous / empty: treat as mismatch (honesty > optimism).
            return .mismatch(reason: "OPEN_APP did not confirm frontmost/opened")

        case .desktopSnapshot, .desktopAct, .axAct, .pastePayload, .waitUntilStable:
            if ExplorationAssetStore.looksLikeFailure(trimmed)
                || trimmed.hasPrefix("✗")
                || u.hasPrefix("✗") {
                return .mismatch(reason: shortFailReason(trimmed))
            }
            return .ok

        case .done:
            return .ok

        default:
            // Non-Act limbs (AgentLoop catalog) — still refuse ✗ / MISMATCH optimism.
            if trimmed.hasPrefix("✗") || u.contains("MISMATCH") {
                return .mismatch(reason: shortFailReason(trimmed))
            }
            return .ok
        }
    }

    /// Convenience: observation text after OPEN_APP (bootstrap or model).
    nonisolated static func openAppSucceeded(fromObservation obs: String?) -> Bool {
        guard let obs else { return false }
        return validateLimbResult(tool: .openApp(name: ""), result: obs).isOk
    }

    nonisolated static func looksLikeOpenAppMismatch(_ obs: String) -> Bool {
        let u = obs.uppercased()
        if u.contains("OPEN_APP MISMATCH") { return true }
        if u.contains("MISMATCH") && (u.contains("OPEN_APP") || u.contains("NOTHING WAS OPENED")) {
            return true
        }
        if obs.hasPrefix("✗") && (u.contains("OPEN") || u.contains("LAUNCH") || u.contains("RESOLVE")) {
            return true
        }
        return false
    }

    nonisolated static func looksLikeOpenAppSuccess(_ obs: String) -> Bool {
        if looksLikeOpenAppMismatch(obs) { return false }
        let u = obs.uppercased()
        if u.contains("MISMATCH") || u.contains("COULD NOT") { return false }
        if u.contains("ERROR") && !u.contains("NO ERROR") { return false }
        // Honest success stamps from AgentToolExecutor.openApp.
        return u.contains("OS APP OPENED")
            || u.contains("BROUGHT FRONTMOST")
            || (u.contains("FRONTMOST") && u.contains("OPENED"))
            || (obs.contains("✓") && u.contains("OPENED"))
    }

    nonisolated private static func shortFailReason(_ obs: String) -> String {
        let line = obs.split(whereSeparator: \.isNewline).first.map(String.init) ?? obs
        return String(line.prefix(120))
    }

    // MARK: - shouldTypeSearchBootstrap

    /// False for procedural / translate / unsafe tokens — host must not dump
    /// the mission into Smart Search. Translate uses named-URL navigate instead.
    nonisolated static func shouldTypeSearchBootstrap(
        goal: String,
        seed: String? = nil
    ) -> Bool {
        let querySource = {
            let s = seed?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            return s.isEmpty ? goal : s
        }()

        if PromptBudget.isProceduralMission(goal) || PromptBudget.isProceduralMission(querySource) {
            return false
        }
        if PromptBudget.isTranslateIntent(goal) || PromptBudget.isTranslateIntent(querySource) {
            return false
        }
        let token = PromptBudget.safeSearchQuery(from: querySource)
            ?? PromptBudget.safeSearchQuery(from: goal)
        guard let token, !token.isEmpty else { return false }
        // URL navigate is not "typing search" — callers handle separately.
        if looksLikeURL(token) { return false }
        return true
    }

    /// Procedural missions: OPEN_APP + SENSE only (no search-bar dump).
    nonisolated static func isProceduralOpenSenseOnly(goal: String, seed: String? = nil) -> Bool {
        let querySource = {
            let s = seed?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            return s.isEmpty ? goal : s
        }()
        return PromptBudget.isProceduralMission(goal)
            || PromptBudget.isProceduralMission(querySource)
    }

    nonisolated static func looksLikeURL(_ s: String) -> Bool {
        let t = s.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return t.hasPrefix("http://") || t.hasPrefix("https://") || t.hasPrefix("www.")
            || t.contains(".com/") || t.contains(".co.jp/")
    }

    // MARK: - shouldPauseForCandidates (hierarchical policy — not a limb)

    /// When hierarchical explore is ON and observation yields a destination list,
    /// return candidates to present to the user. `nil` = do not pause.
    /// `enabled` overrides settings (for tests / explicit call sites).
    nonisolated static func shouldPauseForCandidates(
        observation: String,
        enabled: Bool? = nil
    ) -> [HierarchicalExploreGate.Candidate]? {
        let on = enabled ?? isHierarchicalExplore
        guard on else { return nil }
        let candidates = HierarchicalExploreGate.extractCandidates(from: observation)
        // Do not re-read HierarchicalExploreGate.isEnabled — caller already gated.
        guard Self.destinationListWarrantsAsk(candidates) else { return nil }
        return candidates
    }

    /// Same thresholds as `HierarchicalExploreGate.shouldAskUser` without the settings gate.
    nonisolated static func destinationListWarrantsAsk(
        _ candidates: [HierarchicalExploreGate.Candidate]
    ) -> Bool {
        let links = candidates.filter {
            $0.role == "link" || $0.role == "result" || $0.axId?.hasPrefix("#link") == true
        }
        if links.count >= HierarchicalExploreGate.preferredCandidates { return true }
        if links.count >= HierarchicalExploreGate.minCandidates { return true }
        let dest = candidates.filter { HierarchicalExploreGate.isDestinationRole($0.role) }
        return dest.count >= HierarchicalExploreGate.preferredCandidates
    }

    // MARK: - Limb allow-list (filterAllowed)

    /// True when the tool is one of the thin Act limbs (plus WAIT_UNTIL_STABLE helper).
    nonisolated static func isAllowedActLimb(_ tool: AgentTool) -> Bool {
        switch tool {
        case .openApp, .desktopSnapshot, .desktopAct, .axAct, .pastePayload, .waitUntilStable, .done:
            return true
        default:
            return false
        }
    }

    // MARK: - Assert-style invariant checks (DEBUG / unit)

    /// Returns human-readable failures (empty = DNA helpers behave).
    /// Call from tests or DEBUG boot — does not mutate settings.
    nonisolated static func runInvariantChecks() -> [String] {
        var fails: [String] = []

        // ── Procedural detection / search bootstrap ──
        let proceduralGoal = "Safariを開いて検索欄に「テスト」を入力して送信する → 結果を確認"
        if !PromptBudget.isProceduralMission(proceduralGoal) {
            fails.append("procedural arrow mission not detected")
        }
        if shouldTypeSearchBootstrap(goal: proceduralGoal) {
            fails.append("shouldTypeSearchBootstrap must be false for procedural")
        }
        if !isProceduralOpenSenseOnly(goal: proceduralGoal) {
            fails.append("isProceduralOpenSenseOnly expected true")
        }

        let searchGoal = "Safariを開いて今日のニュースを検索して"
        if PromptBudget.isProceduralMission(searchGoal) {
            // May still be procedural due to 開いて+検索 — safeSearchQuery path.
            // Typing is OK only when a short safe token exists and not translate.
        }
        // Pure short search should allow typing when safe token exists.
        let pureSearch = "今日のニュースを検索"
        if PromptBudget.isProceduralMission(pureSearch) {
            fails.append("pure search misclassified as procedural")
        }
        if !shouldTypeSearchBootstrap(goal: pureSearch) {
            // safeSearchQuery may still return a token
            if PromptBudget.safeSearchQuery(from: pureSearch) != nil {
                fails.append("shouldTypeSearchBootstrap false despite safe token")
            }
        }

        // ── OPEN_APP honesty ──
        let mismatchObs = "✗ OPEN_APP MISMATCH: \"NotARealAppXYZ\" does not resolve — nothing was opened."
        if validateLimbResult(tool: .openApp(name: "x"), result: mismatchObs).isOk {
            fails.append("OPEN_APP MISMATCH must not validate as ok")
        }
        if openAppSucceeded(fromObservation: mismatchObs) {
            fails.append("openAppSucceeded must be false on MISMATCH")
        }
        let successObs = "✓ OS App opened and brought frontmost: Safari. Use [DESKTOP_ACT]/[DESKTOP_SNAPSHOT] to operate it."
        if !validateLimbResult(tool: .openApp(name: "Safari"), result: successObs).isOk {
            fails.append("OPEN_APP success stamp must validate as ok")
        }
        if !openAppSucceeded(fromObservation: successObs) {
            fails.append("openAppSucceeded must be true on frontmost success")
        }
        // Phantom: mention OPEN_APP without success markers
        let phantom = "I will use OPEN_APP next"
        if validateLimbResult(tool: .openApp(name: "Safari"), result: phantom).isOk {
            fails.append("phantom OPEN_APP prose must not validate as ok")
        }

        // ── Hierarchical pause trigger ──
        let listObs = """
        SEMANTIC UI MAP
        <link id="#link1" title="First Result Article"/>
        <link id="#link2" title="Second Result Article"/>
        <link id="#link3" title="Third Result Article"/>
        """
        if shouldPauseForCandidates(observation: listObs, enabled: true) == nil {
            fails.append("hierarchical pause should trigger on ≥2–3 link list")
        }
        if shouldPauseForCandidates(observation: listObs, enabled: false) != nil {
            fails.append("hierarchical pause must be nil when disabled")
        }
        let singleLink = "<link id=\"#link1\" title=\"Only One\"/>"
        if shouldPauseForCandidates(observation: singleLink, enabled: true) != nil {
            fails.append("single link should not force pause")
        }

        // ── Limb set size (do not thicken) ──
        if ActLimb.allCases.count != 5 {
            fails.append("ActLimb must stay at 5 primitives (got \(ActLimb.allCases.count))")
        }

        // ── Cycle detection (Safari↔SNAPSHOT) ──
        let abab = ["open_app:safari", "desktop_snapshot", "open_app:safari", "desktop_snapshot"]
        if ActCycleDetector.detectCycle(recentKeys: abab) == nil {
            fails.append("cycle detector must catch Safari↔SNAPSHOT ABAB")
        }
        let noCycle = ["open_app:safari", "desktop_snapshot", "ax_act:#btn1", "desktop_snapshot"]
        if ActCycleDetector.detectCycle(recentKeys: noCycle) != nil {
            fails.append("cycle detector must not false-positive distinct limbs")
        }

        // ── Gap controller: open ≠ surrender ──
        var gap = ActGapController.open(subject: "open Messages")
        if !gap.isOpen { fails.append("fresh gap must be open") }
        gap.noteMismatch(action: "open_app:JGEN", failureType: "mismatch")
        if ActGapController.looksLikeSurrenderDONE("couldn't open Messages") == false {
            fails.append("surrender DONE detector missed english give-up")
        }
        gap.resolve(via: "DONE")
        if gap.isOpen { fails.append("resolved gap must not stay open") }

        // ── Defaults documented ──
        // Missing UserDefaults key → ON (read helpers already default true).
        _ = isVectorOnlySense
        _ = isHierarchicalExplore

        return fails
    }

#if DEBUG
    /// Fatal in DEBUG if DNA helpers regress (optional call from boot).
    nonisolated static func assertInvariants() {
        let fails = runInvariantChecks()
        assert(fails.isEmpty, "ActDNA invariant checks failed:\n" + fails.joined(separator: "\n"))
    }
#endif
}
