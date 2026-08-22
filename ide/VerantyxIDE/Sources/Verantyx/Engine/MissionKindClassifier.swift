import Foundation

// MARK: - MissionKindClassifier
//
// Thin deterministic SPEAK / ACT gate for Layer 2.
// Vera-a decides / remembers / gaps; 0.5B JGEN is a short-tag executor —
// do NOT ask the tiny model to invent mission kind from freeform prose.
//
// Priority when `executionUseJGEN`:
//   1. prior ExplorationAsset `mission_kind:*` tag (if recalled)
//   2. deterministic keywords / greetings / Q&A
//   3. JGEN classify as weak tie-break only when still undecided

enum MissionKind: String, Sendable, Codable {
    case act
    case speak
}

enum MissionKindSource: String, Sendable {
    case deterministic
    case priorAsset = "prior_asset"
    case jgen
}

enum MissionKindClassifier {

    struct Decision: Sendable {
        let kind: MissionKind
        let source: MissionKindSource
    }

    /// Tag written onto forged exploration skills for prior lookup.
    static let assetTagPrefix = "mission_kind:"
    static func assetTag(for kind: MissionKind) -> String { "\(assetTagPrefix)\(kind.rawValue)" }

    /// Short intent line for `[DIRECTIVE] goal_short` (≤ ~120 chars).
    static func goalShort(from text: String, maxChars: Int = 120) -> String {
        if let intent = PromptBudget.extractTaskIntentLine(from: text) {
            let clipped = String(intent.prefix(maxChars))
                .trimmingCharacters(in: .whitespacesAndNewlines)
            if !clipped.isEmpty { return clipped }
        }
        let seed = PromptBudget.searchSeed(from: text)
        if !seed.isEmpty {
            return String(seed.prefix(maxChars))
                .trimmingCharacters(in: .whitespacesAndNewlines)
        }
        let trimmed = PromptBudget.dedupeRepeatedParagraphs(text)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return String(trimmed.prefix(maxChars))
    }

    /// Resolve mission kind for L2 routing.
    /// - Parameter allowDesktop: when false, always SPEAK (template policy).
    static func resolve(
        question: String,
        handoff: CouncilOrchestrator.Handoff,
        allowDesktop: Bool,
        useJGenTieBreak: Bool
    ) async -> Decision {
        if !allowDesktop {
            return Decision(kind: .speak, source: .deterministic)
        }

        // Greetings are always SPEAK — never burn Act turns on 「こんにちは」.
        if JCrossChatManager.isSimpleGreeting(question) {
            return Decision(kind: .speak, source: .deterministic)
        }

        // Prefer a previously forged asset's stored kind when fingerprints match.
        if let prior = await ExplorationAssetStore.recallMissionKind(for: question) {
            return Decision(kind: prior, source: .priorAsset)
        }

        if let det = classifyDeterministic(question: question, handoff: handoff) {
            return Decision(kind: det, source: .deterministic)
        }

        // Weak JGEN tie-break only when deterministic is undecided.
        if useJGenTieBreak,
           let route = await JGenSpeakActRouter.classify(question: question, handoff: handoff) {
            return Decision(
                kind: route == .act ? .act : .speak,
                source: .jgen
            )
        }

        // Safe default: chat, don't click.
        return Decision(kind: .speak, source: .deterministic)
    }

    /// Pure keyword / structure classifier. `nil` = undecided (JGEN may tie-break).
    static func classifyDeterministic(
        question: String,
        handoff: CouncilOrchestrator.Handoff? = nil
    ) -> MissionKind? {
        if JCrossChatManager.isSimpleGreeting(question) {
            return .speak
        }

        let blob = PromptBudget.truncateForModel(
            {
                var parts = [question]
                if let handoff {
                    parts.append(handoff.asText)
                    parts.append(handoff.detail)
                    parts.append(handoff.nextAction)
                    parts.append(handoff.conclusion)
                }
                return parts.joined(separator: "\n")
            }(),
            maxChars: 2_000,
            headChars: 1_400,
            tailChars: 400
        )
        let lower = blob.lowercased()

        let actKeys = [
            // Imperative desktop verbs (JP)
            "開いて", "開け", "開く", "起動", "立ち上げ", "操作", "入力",
            "クリック", "送る", "送信", "選択", "タイプ", "貼付", "ペースト",
            "検索", "調べ", "かけて",  // operational; 「かけて」= act-ish when present
            // Arrows / procedure separators
            "→", "->", "⇒", "➜",
            // EN verbs
            "click", "type ", "paste", "open ", "launch ", "scroll", "search",
            // Apps / desktop surface
            "safari", "chrome", "firefox", "browser", "ブラウザ",
            "desktop", "アプリ", "snapshot", "ウィンドウ", "window",
            "open_app", "desktop_act", "desktop_snapshot", "ax_act",
            "deepl", "翻訳", "translate",
            // UI repro
            "バグ", "bug", "再現", "reproduce", "repro", "押せ",
        ]
        let hasAct = actKeys.contains { blob.contains($0) || lower.contains($0) }
            || PromptBudget.isProceduralMission(question)

        // Pure explain / Q&A without desktop intent → SPEAK.
        let speakKeys = [
            "天気", "weather", "気温", "temperature",
            "とは", "って何", "教えて", "意味", "why ", "what is", "what's",
            "説明して", "教えてください", "どう思う",
            "誰", "いつ", "どこ", "どうして",
        ]
        let hasSpeakAsk = speakKeys.contains { blob.contains($0) || lower.contains($0) }

        if hasAct { return .act }
        if hasSpeakAsk { return .speak }

        // Short social / explain-only without ops → SPEAK.
        let trimmed = question.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.count <= 40, !hasAct {
            let explainOnly = ["ありがとう", "thanks", "ok", "わかった", "了解"]
            if explainOnly.contains(where: { trimmed.lowercased().contains($0) }) {
                return .speak
            }
        }

        return nil
    }

    /// Log line: `🧭 [MissionKind] act|speak (deterministic|prior_asset|jgen)`.
    static func logLine(for decision: Decision) -> String {
        "🧭 [MissionKind] \(decision.kind.rawValue) (\(decision.source.rawValue))"
    }
}
