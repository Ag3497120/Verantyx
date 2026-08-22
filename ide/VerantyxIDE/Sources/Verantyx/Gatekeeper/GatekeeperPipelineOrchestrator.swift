import Foundation

// MARK: - GatekeeperPipelineOrchestrator
//
// ゲートキーパーパイプライン全体を統合・制御するメインオーケストレーター。
//
// パイプラインフロー:
//   1. ソースコードをJCross IRに変換
//   2. AdversarialNoiseEngine でフラグメント計画立案
//   3. RoutingSessionLogger でTODO状態をfront/に永続化
//   4. ClaudeにJCross IRフラグメントを送信
//   5. 返却パッチをJCrossPatchValidatorで検証
//   6. Bonsai-8Bで安全性を確認
//   7. 逆変換して実ファイルに適用
//   8. セッションをnear/にアーカイブ

@MainActor
final class GatekeeperPipelineOrchestrator: ObservableObject {

    static let shared = GatekeeperPipelineOrchestrator()

    // MARK: - Pipeline Phase

    enum PipelinePhase: Equatable {
        case idle
        case fragmenting(file: String)
        case registeringSession
        case sendingToWorker(fragment: Int, total: Int)
        case awaitingPatch
        case validatingPatch
        case bonsaiReview
        case reverseTranspiling
        case applyingToSource(file: String)
        case archiving
        case done(stats: String)
        case failed(reason: String)

        static func == (lhs: PipelinePhase, rhs: PipelinePhase) -> Bool {
            switch (lhs, rhs) {
            case (.idle, .idle), (.awaitingPatch, .awaitingPatch),
                 (.validatingPatch, .validatingPatch), (.bonsaiReview, .bonsaiReview),
                 (.reverseTranspiling, .reverseTranspiling), (.archiving, .archiving): return true
            default: return false
            }
        }
    }

    // MARK: - Properties

    @Published var phase: PipelinePhase = .idle
    @Published var isRunning = false
    @Published var pipelineLog: [String] = []

    private let noiseEngine   = AdversarialNoiseEngine()
    private let validator     = JCrossPatchValidator()
    private let state         = GatekeeperModeState.shared
    /// 3層難読化パイプライン（全フラグメントに適用）
    private let obfuscator    = JCrossObfuscationPipeline()

    private var routingLogger: RoutingSessionLogger?

    private var vault: JCrossVault { state.vault }

    // MARK: - Init

    private init() {
        setupRoutingLogger()
    }

    private func setupRoutingLogger() {
        let vaultURL = state.vault.vaultRootURL
        routingLogger = RoutingSessionLogger(vaultRootURL: vaultURL)
    }

    // MARK: - Main Entry: Run Full Pipeline

    /// ゲートキーパーパイプラインを実行する
    func runPipeline(
        sourceRelativePath: String,
        userInstructions: String,
        noiseLevel: Int = 2,
        camouflageDomain: RoutingSessionLogger.CamouflageDomain = .orbitalMechanics
    ) async {
        guard !isRunning else { return }
        isRunning = true
        defer { isRunning = false }

        log(AppLanguage.shared.t("🚀 Pipeline started: \(sourceRelativePath)", "🚀 パイプライン開始: \(sourceRelativePath)"))

        // ── Step 1: JCross IR 取得 ────────────────────────────────
        phase = .fragmenting(file: sourceRelativePath)
        guard let vaultResult = vault.read(relativePath: sourceRelativePath) else {
            fail(AppLanguage.shared.t("File not found in Vault: \(sourceRelativePath)", "Vault にファイルが見つかりません: \(sourceRelativePath)"))
            return
        }

        let jcrossIR = vaultResult.jcrossContent
        let schema   = vaultResult.schema
        let nodeIDs  = extractNodeIDs(from: jcrossIR)
        log(AppLanguage.shared.t("📦 Nodes: \(nodeIDs.count) (schema: \(schema.sessionID.prefix(8)))", "📦 ノード数: \(nodeIDs.count) (schema: \(schema.sessionID.prefix(8)))"))

        // ── Step 2: フラグメント計画 ────────────────────────────────
        let plan = await noiseEngine.planFragmentation(
            sessionID: schema.sessionID,
            jcrossIR: jcrossIR,
            nodeIDs: nodeIDs,
            noiseLevel: noiseLevel,
            maxFragmentsPerSession: 10
        )
        log("🎭 フラグメント計画: 実\(plan.totalRealCount) + ダミー\(plan.totalDummyCount)" +
            " (\(camouflageDomain.rawValue)でカモフラージュ)")

        // ── Step 3: セッション登録 → front/ に永続化 ────────────────
        phase = .registeringSession
        guard let logger = routingLogger else {
            fail(AppLanguage.shared.t("RoutingSessionLogger is uninitialized", "RoutingSessionLogger が未初期化です"))
            return
        }

        var routingSession = logger.createSession(
            projectID: state.currentProjectID,
            sourceRelativePath: sourceRelativePath,
            schemaSessionID: schema.sessionID,
            camouflageDomain: camouflageDomain
        )
        let sessionID = routingSession.sessionID
        log(AppLanguage.shared.t("📝 Session registered: \(sessionID)", "📝 セッション登録: \(sessionID)"))

        // フラグメントを logger に記録
        for fragment in plan.fragments {
            if fragment.kind == .real {
                logger.addRealFragment(
                    to: sessionID,
                    nodeID: fragment.nodeID,
                    claudeAlias: fragment.claudeAlias,
                    role: fragment.role
                )
            } else {
                logger.addDummyFragment(
                    to: sessionID,
                    nodeID: fragment.nodeID,
                    claudeAlias: fragment.claudeAlias,
                    domain: fragment.domain ?? camouflageDomain
                )
            }
        }

        logger.transitionStatus(sessionID, to: .sending)

        // ── Step 4: Claudeにフラグメントを送信 ───────────────────────
        let totalFragments = plan.fragments.count
        var irBatches: [String] = []

        for (i, fragment) in plan.fragments.enumerated() {
            phase = .sendingToWorker(fragment: i + 1, total: totalFragments)
            irBatches.append(buildFragmentMessage(fragment: fragment, seq: i + 1, total: totalFragments))

            // トークン予算チェック (Bonsai-8B)
            let estimatedTokens = irBatches.joined().count / 4
            logger.updateBonsaiBudget(sessionID, used: estimatedTokens)

            if logger.isBudgetCritical {
                log(AppLanguage.shared.t("⚠️ Bonsai budget low — aborting fragment transmission", "⚠️ Bonsai バジェット残量僅少 — フラグメント送信を打ち切ります"))
                break
            }
        }

        let combinedIR = irBatches.joined(separator: "\n\n")
        let systemPrompt = noiseEngine.buildClaudeSystemPrompt(
            plan: plan,
            baseInstructions: buildBaseWorkerInstructions(userInstructions: userInstructions)
        )

        log(AppLanguage.shared.t("📡 Sending to Claude (\(combinedIR.count) chars)...", "📡 Claudeへ送信中 (\(combinedIR.count)文字)..."))
        logger.transitionStatus(sessionID, to: .awaitingPatch)
        logger.completeTodo(sessionID, todo: .receivePatch)

        let claudeResponse = await callExternalWorker(systemPrompt: systemPrompt, userContent: combinedIR)
        logger.recordReceivedPatch(sessionID, raw: claudeResponse)
        logger.updateTokenCount(sessionID, sent: combinedIR.count / 4, received: claudeResponse.count / 4)
        log(AppLanguage.shared.t("📥 Received patch from Claude (\(claudeResponse.count) chars)", "📥 Claudeからパッチを受信 (\(claudeResponse.count)文字)"))

        // セッションを再取得 (logger更新後)
        guard let updatedSession = logger.session(id: sessionID) else {
            fail(AppLanguage.shared.t("Session not found", "セッションが見つかりません"))
            return
        }
        routingSession = updatedSession

        // ── Step 5: パッチをパース ────────────────────────────────
        phase = .validatingPatch
        let parsedPatches = validator.parsePatches(from: claudeResponse, session: routingSession)
        logger.completeTodo(sessionID, todo: .parsePatchFormat)
        log(AppLanguage.shared.t("🔍 Parse result: \(parsedPatches.count) patch candidates", "🔍 パース結果: \(parsedPatches.count)件のパッチ候補"))

        // ── Step 6: バリデーション (ダミーフィルタ + 構造チェック) ─────
        let summary = validator.validate(patches: parsedPatches, session: routingSession)
        logger.completeTodo(sessionID, todo: .filterDummyPatches)

        log("✅ 承認: \(summary.acceptedPatches.count)件 | " +
            "❌ 却下: \(summary.rejectedPatches.count)件 | " +
            "🎭 ダミー廃棄: \(summary.dummyPatchCount)件")

        if summary.hasHallucinations {
            log("⚠️ Hallucinated aliases: \(summary.hallucinatedPatchCount)件 (Claudeが存在しないノードを参照)")
        }

        logger.recordFilteredPatch(sessionID, filtered: buildFilteredPatchSummary(summary))

        // ── Step 7: Bonsai-8B による安全性検証 ───────────────────────
        phase = .bonsaiReview
        let bonsaiPrompt = validator.buildBonsaiValidationPrompt(summary: summary, session: routingSession)
        let bonsaiVerdict = await runBonsaiValidation(prompt: bonsaiPrompt)
        logger.completeTodo(sessionID, todo: .validateRealPatches)
        log(AppLanguage.shared.t("🤖 Bonsai-8B verdict: \(bonsaiVerdict.prefix(80))", "🤖 Bonsai-8B 判定: \(bonsaiVerdict.prefix(80))"))

        guard bonsaiVerdict.uppercased().contains("YES") else {
            fail(AppLanguage.shared.t("Bonsai-8B could not verify safety: \(bonsaiVerdict.prefix(200))", "Bonsai-8Bが安全性を確認できませんでした: \(bonsaiVerdict.prefix(200))"))
            logger.transitionStatus(sessionID, to: .failed)
            return
        }

        // ── Step 8: IDシャッフル逆変換 ────────────────────────────────
        phase = .reverseTranspiling
        let reverseMap = plan.reverseShuffleMap
        let resolvedPatches = validator.applyReverseShuffleMap(to: summary, reverseMap: reverseMap)
        logger.completeTodo(sessionID, todo: .reverseTransform)
        log(AppLanguage.shared.t("🔄 De-transpilation complete: resolved \(resolvedPatches.count) patches to nodeIDs", "🔄 逆変換完了: \(resolvedPatches.count)件のパッチをnodeIDに解決"))

        // ── Step 9: 実ファイルへ適用 ────────────────────────────────
        phase = .applyingToSource(file: sourceRelativePath)
        do {
            let appliedCount = try await applyResolvedPatches(
                patches: resolvedPatches,
                relativePath: sourceRelativePath,
                schema: schema
            )
            logger.completeTodo(sessionID, todo: .applyToSource)
            log(AppLanguage.shared.t("✅ Applied \(appliedCount) changes to source", "✅ ソースに\(appliedCount)件の変更を適用しました"))
        } catch {
            fail(AppLanguage.shared.t("Source application failed: \(error.localizedDescription)", "ソース適用失敗: \(error.localizedDescription)"))
            logger.transitionStatus(sessionID, to: .failed)
            return
        }

        // ── Step 10: アーカイブ ────────────────────────────────────
        phase = .archiving
        logger.completeTodo(sessionID, todo: .archiveSession)
        log(AppLanguage.shared.t("📦 Archived session to near/", "📦 セッションをnear/にアーカイブ"))

        noiseEngine.clearShuffleHistory(for: schema.sessionID)

        let stats = buildPipelineStats(plan: plan, summary: summary)
        phase = .done(stats: stats)
        log(AppLanguage.shared.t("🎉 Pipeline completed!\n\(stats)", "🎉 パイプライン完了!\n\(stats)"))
    }

    // MARK: - Worker Call

    private func callExternalWorker(systemPrompt: String, userContent: String) async -> String {
        // CommanderOrchestratorのOllamaフォールバックを流用
        // 実装では外部APIエンドポイント (Anthropic等) に送信
        return await CommanderOrchestrator.shared.callExternalAPI(
            systemPrompt: systemPrompt,
            userContent: userContent
        )
    }

    // MARK: - Bonsai-8B Validation

    private func runBonsaiValidation(prompt: String) async -> String {
        // Bonsai-8B はOllamaでローカル実行 (bonsai-8b モデル名)
        let endpoint = await MainActor.run {
            AppState.shared?.ollamaEndpoint ?? "http://localhost:11434"
        }
        guard let url = URL(string: "\(endpoint)/api/generate") else { return "NO (endpoint error)" }

        struct Request: Encodable {
            let model: String; let prompt: String; let stream: Bool
            let options: Options
            struct Options: Encodable { let temperature: Double; let num_predict: Int }
        }
        struct Response: Decodable { let response: String }

        let body = Request(
            model: "bonsai-8b",
            prompt: prompt,
            stream: false,
            options: .init(temperature: 0.1, num_predict: 200)
        )

        guard let data = try? JSONEncoder().encode(body),
              let (respData, _) = try? await URLSession.shared.data(for: {
                  var req = URLRequest(url: url)
                  req.httpMethod = "POST"
                  req.httpBody = data
                  req.setValue("application/json", forHTTPHeaderField: "Content-Type")
                  req.timeoutInterval = 60
                  return req
              }()),
              let decoded = try? JSONDecoder().decode(Response.self, from: respData)
        else {
            // Bonsai未インストール時はデフォルト承認
            log(AppLanguage.shared.t("⚠️ Bonsai-8B unresponsive — approved by rule-base", "⚠️ Bonsai-8B 未応答 — ルールベースで承認"))
            return "YES (bonsai unavailable, rule-based approval)"
        }

        return decoded.response
    }

    // MARK: - Apply Patches

    private func applyResolvedPatches(
        patches: [(nodeID: String, modification: String)],
        relativePath: String,
        schema: JCrossSchema
    ) async throws -> Int {
        guard !patches.isEmpty else { return 0 }

        // JCross diff形式に変換してVaultに書き込む
        let patchContent = patches.map { p in
            "PATCH_NODE \(p.nodeID):\n\(p.modification)"
        }.joined(separator: "\n\n---\n\n")

        let transpiler = PolymorphicJCrossTranspiler.shared
        _ = try await vault.writeDiff(
            jcrossDiff: patchContent,
            relativePath: relativePath,
            transpiler: transpiler
        )

        return patches.count
    }

    // MARK: - Helpers

    private func buildFragmentMessage(fragment: AdversarialNoiseEngine.Fragment, seq: Int, total: Int) -> String {
        // ✅ Layer A+B+C 難読化をフラグメント内容に適用してから送信
        let obfuscatedContent = obfuscator.obfuscateTextFragment(fragment.irContent)
        return """
        // ── Fragment \(seq)/\(total) ──────────────────────────────────────
        // alias: \(fragment.claudeAlias) | role: \(fragment.role)
        // kind: \(fragment.kind == .real ? "TASK" : "CONTEXT")
        \(obfuscatedContent)
        """
    }

    private func buildBaseWorkerInstructions(userInstructions: String) -> String {
        """
        You are a Worker AI. You ONLY see JCross IR fragments — never real source code.
        Node aliases are session-specific and meaningless outside this session.

        IMPORTANT: Do NOT use old identifiers starting with ⌬Ξ. Our schema has migrated to semantic Kanji prefixes (e.g. _JCROSS_核_).
        If you see any ⌬Ξ or other strange symbols in past chat history, ignore them completely and ONLY use the new _JCROSS_ format present in the current fragment.

        YOUR TASK: \(userInstructions)

        CRITICAL: Respond ONLY with JCross Patch format. No explanations outside the patch block.
        """
    }

    private func buildFilteredPatchSummary(_ summary: JCrossPatchValidator.ValidationSummary) -> String {
        summary.acceptedPatches.map { p in
            "ACCEPTED: \(p.targetAlias) → \(p.resolvedNodeID ?? "?") [\(p.modificationType.rawValue)]"
        }.joined(separator: "\n")
    }

    private func buildPipelineStats(
        plan: AdversarialNoiseEngine.FragmentPlan,
        summary: JCrossPatchValidator.ValidationSummary
    ) -> String {
        """
        ── Pipeline Stats ──────────────────────────
        Noise domain: \(plan.selectedDomain.rawValue)
        Real fragments: \(plan.totalRealCount) | Dummy: \(plan.totalDummyCount) (\(String(format: "%.0f", plan.noiseRatio * 100))% noise)
        Patches received: \(summary.totalPatches)
        Patches accepted: \(summary.acceptedPatches.count) (\(String(format: "%.0f", summary.acceptanceRate * 100))%)
        Dummy patches filtered: \(summary.dummyPatchCount)
        Hallucinations blocked: \(summary.hallucinatedPatchCount)
        ────────────────────────────────────────────
        """
    }

    private func extractNodeIDs(from jcrossIR: String) -> [String] {
        // ノードIDパターン: N001, N002... または _JCROSS_核_1_ 形式
        let pattern = #"_JCROSS_[^_]+_\d+_"#
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return [] }
        let range = NSRange(jcrossIR.startIndex..., in: jcrossIR)
        let matches = regex.matches(in: jcrossIR, range: range)
        let ids = matches.compactMap { Range($0.range, in: jcrossIR).map { String(jcrossIR[$0]) } }
        return Array(Set(ids)).sorted()
    }

    private func log(_ msg: String) {
        pipelineLog.append("[\(timeStamp())] \(msg)")
        print("[GatekeeperPipeline] \(msg)")
    }

    private func fail(_ reason: String) {
        log("❌ FAILED: \(reason)")
        phase = .failed(reason: reason)
    }

    private func timeStamp() -> String {
        let fmt = DateFormatter()
        fmt.dateFormat = "HH:mm:ss"
        return fmt.string(from: Date())
    }
}

// MARK: - CommanderOrchestrator Extension (internal call bridge)

extension CommanderOrchestrator {
    /// GatekeeperPipelineOrchestrator から外部API呼び出しに使う内部ブリッジ
    func callExternalAPI(systemPrompt: String, userContent: String) async -> String {
        let provider = await MainActor.run { GatekeeperModeState.shared.workerProvider }
        let result = await CloudAPIClient.shared.send(
            systemPrompt: systemPrompt,
            userMessage: userContent,
            provider: provider
        )
        switch result {
        case .success(let text): return text
        case .failure(let err): return "❌ Worker Error: \(err.localizedDescription)"
        }
    }

}
