import Foundation

/// Tracks what actually goes into each turn's context, broken down by
/// source, so the memory-injection features built this session (L2 zone
/// memory, Vera, skills, eternal/vector memory) become *visible* doing
/// their job -- and, just as usefully, visible when they're NOT
/// contributing anything, as a dev diagnostic.
///
/// Everything here that isn't a real API-reported token count is a plain
/// character count -- matching what `AgentLoop.swift`'s own budget/
/// compression logic (`compressThreshold`) actually measures against
/// today. No new estimation logic is introduced; this just surfaces
/// numbers that already exist at the point each injection string gets
/// built, rather than computing anything new.
@MainActor
final class ContextUsageTracker: ObservableObject {
    static let shared = ContextUsageTracker()

    struct InjectionUsage {
        var systemPromptChars = 0
        var conversationHistoryChars = 0
        /// `SessionMemoryArchiver.buildZonePriorityInjection` (L1-L3).
        var l2ZoneChars = 0
        /// `VeraMemoryBridge.recall`.
        var veraChars = 0
        /// Skill text from `SkillLibrary` search results.
        var skillChars = 0
        /// `EternalMemoryStore.recallBlock` / `CouncilOrchestrator` handoff text.
        var eternalMemoryChars = 0

        /// Real token counts from the API's own `usage` field, when the
        /// active backend reports one (Anthropic always does; Ollama does
        /// on its final NDJSON chunk). `nil` means no real count arrived
        /// this turn -- the UI falls back to a `/4` char-based estimate,
        /// clearly labeled as an estimate rather than silently passed off
        /// as exact.
        var realInputTokens: Int?
        var realOutputTokens: Int?

        var totalInjectionChars: Int {
            systemPromptChars + conversationHistoryChars + l2ZoneChars + veraChars + skillChars + eternalMemoryChars
        }

        /// Same `/4` estimate `AgentLoop.swift`'s own debug logging already
        /// uses (`tier.compressThreshold / 4`) -- kept consistent rather
        /// than inventing a second estimate constant.
        var estimatedTotalTokens: Int { totalInjectionChars / 4 }
    }

    @Published private(set) var current = InjectionUsage()
    /// Mirrors `AgentLoop.swift`'s `compressThreshold` for the active model
    /// tier -- a character budget, not a token budget (see
    /// `SettingsView.swift`'s "Context window" picker, relabeled alongside
    /// this to stop implying it's token-accurate).
    @Published private(set) var contextWindowCharBudget: Int = 0
    @Published private(set) var compressionEventsThisSession = 0
    @Published private(set) var charsSavedByCompressionThisSession = 0

    private init() {}

    /// Call at the start of each turn, before the injection-building call
    /// sites run -- clears the per-turn breakdown so stale numbers from a
    /// previous turn don't linger in the popover.
    func beginTurn() {
        current = InjectionUsage()
    }

    func setSystemPromptChars(_ count: Int) { current.systemPromptChars = count }
    func setConversationHistoryChars(_ count: Int) { current.conversationHistoryChars = count }
    /// `+=` (not `=`) since some turns build more than one L2/Vera/skill/
    /// eternal-memory block (e.g. Council's per-role memory prefix).
    func addL2ZoneChars(_ count: Int) { current.l2ZoneChars += count }
    func addVeraChars(_ count: Int) { current.veraChars += count }
    func addSkillChars(_ count: Int) { current.skillChars += count }
    func addEternalMemoryChars(_ count: Int) { current.eternalMemoryChars += count }

    func recordRealUsage(inputTokens: Int?, outputTokens: Int?) {
        if let inputTokens { current.realInputTokens = inputTokens }
        if let outputTokens { current.realOutputTokens = outputTokens }
    }

    func setContextWindowCharBudget(_ budget: Int) {
        contextWindowCharBudget = budget
    }

    func recordCompression(charsBefore: Int, charsAfter: Int) {
        compressionEventsThisSession += 1
        charsSavedByCompressionThisSession += max(0, charsBefore - charsAfter)
    }
}
