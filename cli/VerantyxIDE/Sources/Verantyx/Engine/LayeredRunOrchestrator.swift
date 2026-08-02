import Foundation

/// Runs the user's 4-layer architecture end to end:
///
///   Layer 0  memory        — Vera facts / L1-L3 zone memory / eternal vectors
///   Layer 1  council core  — same-arch JGEN roles deliberating in vector space
///   Layer 2  execution     — jgen-native speak/act (preferred) or a tool-using agent
///   Layer 3  escalation    — a stronger model, only when explicitly enabled
///
/// Layer 0 needs no code here: `CouncilOrchestrator.deliberate` already
/// assembles the memory prefix from the same `Config` flags this passes in.
/// The point of this type is the L1 → L2 → L3 sequencing and the fallbacks,
/// so no single missing piece (no JGEN model, no execution model configured)
/// leaves the user with nothing.
@MainActor
enum LayeredRunOrchestrator {

    /// True when the layered path can actually run: it needs the JGEN engine
    /// loaded, because the council deliberates on hidden states.
    static var isAvailable: Bool {
        if case .jcrossReady = AppState.shared?.modelStatus { return true }
        return false
    }

    /// - Returns: true if the layered path ran. False means the caller should
    ///   fall back to its normal agent loop (e.g. no JGEN model loaded).
    @discardableResult
    static func run(
        question: String,
        app: AppState,
        onProgress: @escaping @Sendable (LoopEvent) async -> Void
    ) async -> Bool {

        guard isAvailable else {
            await onProgress(.systemLog(AppLanguage.shared.t(
                "⚠️ Council needs a JGEN model loaded — falling back to the normal agent.",
                "⚠️ 合議にはJGENモデルのロードが必要です — 通常のエージェントで実行します。")))
            return false
        }

        // Bound the paste *once* at entry. Council roles re-tokenize + encode
        // the user string every round; a 4k–10k essay multiplied across the
        // cast OOMs the device. Keep a head/tail window for intent; derive
        // desktop search from the original head before middle drop.
        let originalLength = question.count
        let modelQuestion = PromptBudget.truncateForModel(question)
        let actSearchSeed = PromptBudget.searchSeed(from: question)
        if PromptBudget.needsTruncate(question) {
            await onProgress(.systemLog(AppLanguage.shared.t(
                "✂️ [PromptBudget] user text \(originalLength)→\(modelQuestion.count) chars (head/tail windows; full paste not embedded in role prompts).",
                "✂️ [PromptBudget] ユーザー文 \(originalLength)→\(modelQuestion.count) 文字（先頭/末尾のみ。全文は役割プロンプトに埋め込みません）。")))
        }

        let store = CouncilSettingsStore.shared
        var config = store.config
        // This orchestrator owns Layers 2 and 3; tell the council not to do
        // its own one-shot execution call.
        config.executionMode = .external

        // ── Layer 1: council ──────────────────────────────────────────────
        await onProgress(.systemLog(AppLanguage.shared.t(
            "🧠 [L1 Council] deliberating (\(config.roleCount) roles, up to \(config.roundsCap) rounds)…",
            "🧠 [L1 合議] 審議中 (\(config.roleCount)役割・最大\(config.roundsCap)ラウンド)…")))

        let result: CouncilOrchestrator.Result
        do {
            result = try await CouncilOrchestrator.shared.deliberate(question: modelQuestion, config: config, onProgress: onProgress)
        } catch {
            await onProgress(.systemLog(AppLanguage.shared.t(
                "⚠️ [L1 Council] failed: \(error.localizedDescription) — falling back to the normal agent.",
                "⚠️ [L1 合議] 失敗: \(error.localizedDescription) — 通常のエージェントで実行します。")))
            return false
        }

        let handoff = result.handoff
        await onProgress(.aiMessage(AppLanguage.shared.t(
            "**[L1 合議 → 手渡し]**\n```\n\(handoff.asText)\n```",
            "**[L1 合議 → 手渡し]**\n```\n\(handoff.asText)\n```")))

        // ── Layer 2: execution ────────────────────────────────────────────
        let executionModel = store.executionModel.trimmingCharacters(in: .whitespaces)
        var outcome: ExecutionAgent.Outcome?
        var jgenSpoke = false

        let template = ArchitectureTemplate.builtins.first { $0.id == store.templateId }
        let policy = template?.executionToolPolicy
        let maxTurns = policy?.maxTurns ?? 8

        // Preferred path for the jgen-vector-bus architecture: same engine as
        // L1, soft/eternal memory conditioning, **no AgentLoop** (avoids
        // Nano `[MEM:check]` prompt collapse on 0.5B–2B JGENs).
        let wantJGenNative = store.executionUseJGEN
            || store.templateId == "jgen-vector-bus"
        // When JGEN-native is on but templateId is "custom" (hand-edited
        // settings), `policy` is nil and the old `?? false` forced Speak for
        // every turn — including "open Safari and search…". Default desktop
        // on for that native path; templates that disable it still win.
        let allowDesktop = policy?.allowDesktop ?? wantJGenNative
        if wantJGenNative, case .jcrossReady = app.modelStatus {
            let sessionId = app.vxChatSessionId
            let useAct: Bool
            if !allowDesktop {
                useAct = false
                await onProgress(.systemLog(AppLanguage.shared.t(
                    "🧭 [L2 Router] desktop disabled by template → SPEAK",
                    "🧭 [L2 ルーター] テンプレでデスクトップ無効 → SPEAK")))
            } else if JCrossChatManager.isSimpleGreeting(modelQuestion) {
                useAct = false
                await onProgress(.systemLog(AppLanguage.shared.t(
                    "🧭 [L2 Router] greeting → SPEAK",
                    "🧭 [L2 ルーター] 挨拶 → SPEAK")))
            } else {
                let keywordAct = looksLikeDesktopAct(question: modelQuestion, handoff: handoff)
                // Pure Q&A ("今日の天気を教えて") must not become random clicks
                // when the tiny classifier emits ACT without desktop intent.
                if looksLikeSpeakOnlyQA(modelQuestion), !keywordAct {
                    useAct = false
                    await onProgress(.systemLog(AppLanguage.shared.t(
                        "🧭 [L2 Router] informational Q&A → SPEAK",
                        "🧭 [L2 ルーター] 情報質問 → SPEAK")))
                } else if let route = await JGenSpeakActRouter.classify(question: modelQuestion, handoff: handoff) {
                    // Tiny models sometimes emit SPEAK while the user clearly
                    // asked to operate the desktop — override with keyword signal.
                    if route == .speak, keywordAct {
                        useAct = true
                        await onProgress(.systemLog(AppLanguage.shared.t(
                            "🧭 [L2 Router] JGEN→SPEAK but desktop intent in user text → ACT",
                            "🧭 [L2 ルーター] JGENはSPEAKだがユーザー文に操作意図 → ACT")))
                    } else if route == .act, !keywordAct, looksLikeSpeakOnlyQA(modelQuestion) {
                        useAct = false
                        await onProgress(.systemLog(AppLanguage.shared.t(
                            "🧭 [L2 Router] JGEN→ACT but informational Q&A → SPEAK",
                            "🧭 [L2 ルーター] JGENはACTだが情報質問 → SPEAK")))
                    } else {
                        useAct = (route == .act)
                        await onProgress(.systemLog(AppLanguage.shared.t(
                            "🧭 [L2 Router] JGEN classified → \(route.rawValue.uppercased())",
                            "🧭 [L2 ルーター] JGEN分類 → \(route.rawValue.uppercased())")))
                    }
                } else {
                    useAct = keywordAct
                    await onProgress(.systemLog(AppLanguage.shared.t(
                        "🧭 [L2 Router] JGEN classify failed — keyword fallback → \(useAct ? "ACT" : "SPEAK")",
                        "🧭 [L2 ルーター] JGEN分類失敗 — キーワード補助 → \(useAct ? "ACT" : "SPEAK")")))
                }
            }

            if useAct {
                await onProgress(.systemLog(AppLanguage.shared.t(
                    "🛠 [L2 Execution — JGEN Act] same model — desktop/AX via vector bus (no AgentLoop)…",
                    "🛠 [L2 実行 — JGEN操作] 同一モデル — ベクトルバス経由のデスクトップ/AX（AgentLoopなし）…")))
                let act = await JGenActAgent.shared.run(
                    handoff: handoff,
                    question: modelQuestion,
                    useEternalMemory: config.useEternalMemory,
                    maxTurns: maxTurns,
                    sessionId: sessionId,
                    workspaceURL: app.workspaceURL,
                    searchQuerySeed: actSearchSeed,
                    onProgress: onProgress
                )
                outcome = .completed(act.text)
            } else {
                await onProgress(.systemLog(AppLanguage.shared.t(
                    "🛠 [L2 Execution — JGEN native] same model as council — speak via vector bus (no AgentLoop)…",
                    "🛠 [L2 実行 — JGENネイティブ] 合議と同一モデル — ベクトルバス発話（AgentLoopなし）…")))
                let speak = await JGenSpeakAgent.shared.run(
                    handoff: handoff,
                    question: modelQuestion,
                    useEternalMemory: config.useEternalMemory,
                    sessionId: sessionId,
                    onProgress: onProgress
                )
                outcome = .completed(speak.text)
            }
            jgenSpoke = true
        } else if executionModel.isEmpty {
            await onProgress(.systemLog(AppLanguage.shared.t(
                "ℹ️ [L2] No execution model set — stopping at the council handoff. Set one in the JGEN options popover, or enable “JGEN for Layer 2”.",
                "ℹ️ [L2] 実行モデル未設定 — 合議の手渡しで停止します。JGENオプションで設定するか「L2もJGEN」を有効にしてください。")))
        } else {
            await onProgress(.systemLog(AppLanguage.shared.t(
                "🛠 [L2 Execution] \(executionModel) — acting on the handoff…",
                "🛠 [L2 実行] \(executionModel) — 手渡しに基づき実行中…")))

            let spec = ExecutionAgent.Spec(
                modelStatus: .ollamaReady(model: executionModel),
                activeModel: executionModel,
                workspaceURL: app.workspaceURL,
                operationMode: app.operationMode,
                chatSessionId: app.vxChatSessionId
            )
            outcome = await ExecutionAgent.shared.run(
                handoff: handoff,
                question: modelQuestion,
                spec: spec,
                cortex: app.cortex,
                onProgress: onProgress
            )
        }

        // ── Layer 3: escalation (only when explicitly enabled) ───────────
        // jgen-vector-bus / escalateOnLowConfidence=false never enters here.
        let lowConfidence = handoff.confidence < config.escalationConfidenceThreshold
        let executionFailed = outcome?.isFailure ?? false
        let escalationModel = config.escalationModel.trimmingCharacters(in: .whitespaces)
        let allowEscalate = config.escalateOnLowConfidence && !jgenSpoke

        if allowEscalate, lowConfidence || executionFailed, !escalationModel.isEmpty {
            let reason = executionFailed
                ? AppLanguage.shared.t("execution failed", "実行が失敗")
                : AppLanguage.shared.t("confidence \(String(format: "%.2f", handoff.confidence)) below threshold", "確信度 \(String(format: "%.2f", handoff.confidence)) が閾値未満")
            await onProgress(.systemLog(AppLanguage.shared.t(
                "⬆️ [L3 Escalation] \(escalationModel) — \(reason).",
                "⬆️ [L3 エスカレ] \(escalationModel) — \(reason)。")))

            let digest = outcome.map { "\n[EXECUTION RESULT] \($0.text.prefix(1500))" } ?? ""
            if let answer = await OllamaClient.shared.generateConversation(
                model: escalationModel,
                messages: [
                    ("system", "You are the escalation layer. A council deliberated and an execution agent attempted the work; both are summarized below. Give the final, direct answer."),
                    ("user", handoff.asText + digest + "\n\n[ORIGINAL QUESTION] \(modelQuestion)")
                ]
            ), !answer.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                await onProgress(.done(message: answer, workspace: app.workspaceURL))
                return true
            }
            await onProgress(.systemLog(AppLanguage.shared.t(
                "⚠️ [L3] Escalation produced no answer.", "⚠️ [L3] エスカレーションは回答を返しませんでした。")))
        }

        // Terminal message: JGenSpeakAgent / JGenActAgent / ExecutionAgent already emit .done
        // through onProgress when they run; only close the turn when L2 never ran.
        if outcome == nil {
            await onProgress(.done(
                message: handoff.detail.isEmpty ? handoff.asText : handoff.detail,
                workspace: app.workspaceURL))
        }
        return true
    }

    /// Keyword fallback when `JGenSpeakActRouter` cannot parse ACT/SPEAK.
    /// Prefer the JGEN classifier; do not grow this list as the primary router.
    private static func looksLikeDesktopAct(
        question: String,
        handoff: CouncilOrchestrator.Handoff
    ) -> Bool {
        // Bound before lowercasing — keyword scan must not allocate a
        // multi-megabyte string from a long paste + handoff.
        let blob = PromptBudget.truncateForModel(
            question + "\n" + handoff.asText + "\n" + handoff.detail
            + "\n" + handoff.nextAction + "\n" + handoff.conclusion,
            maxChars: 2_000,
            headChars: 1_400,
            tailChars: 400
        ).lowercased()
        let keys = [
            // UI bug / repro
            "バグ", "bug", "ボタン", "押せ", "押せない", "ui", "gui",
            "reproduce", "repro", "再現", "click", "クリック", "画面",
            "操作", "desktop", "アプリ", "snapshot", "開けない", "動かない",
            "disabled", "grayed", "greyed", "accessibility", "ax_",
            // Browser / search / open-app (the failure case: "Safariを開いて検索")
            "safari", "chrome", "firefox", "browser", "ブラウザ",
            "検索", "search", "ニュース", "news", "開いて", "開け", "起動",
            "open ", "open_", "browse", "ウェブ", "google", "url", "http",
            "デスクトップ", "ウィンドウ", "window", "入力して", "スクロール",
            "scroll", "open_app", "desktop_act", "desktop_snapshot",
            "deepl", "翻訳", "translate",
        ]
        return keys.contains { blob.contains($0) }
    }

    /// Informational Q&A that should SPEAK (not random desktop clicks).
    /// e.g. 「今日の天気を教えて」 without Safari/open/search intent.
    private static func looksLikeSpeakOnlyQA(_ question: String) -> Bool {
        let t = PromptBudget.truncateForModel(question, maxChars: 400, headChars: 300, tailChars: 80)
            .lowercased()
        let askHints = [
            "天気", "weather", "気温", "temperature",
            "とは", "って何", "教えて", "意味", "why ", "what is", "what's",
            "誰", "いつ", "どこ", "どうして",
        ]
        let desktopHints = [
            "safari", "chrome", "firefox", "ブラウザ", "開いて", "開け", "起動",
            "検索", "search", "クリック", "click", "desktop", "操作",
            "deepl", "翻訳", "translate", "snapshot", "画面",
        ]
        let asks = askHints.contains { t.contains($0) }
        let desktop = desktopHints.contains { t.contains($0) }
        return asks && !desktop
    }
}
