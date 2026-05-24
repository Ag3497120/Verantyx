import Foundation
import SwiftUI

// MARK: - CommanderOrchestrator
//
// GatekeeperMode の会話フロー全体を制御する。
//
// フロー:
//   User message
//       ↓
//   [Commander: Local LLM (Ollama)]
//       • ユーザー意図を理解
//       • 必要なファイルを特定 (Vault経由)
//       • Worker (外部API) への問い合わせを組み立て
//       ↓ MCP tool calls (JCross IRのみ)
//   [Worker: Claude/GPT]
//       • JCross IR だけを見てコード変更を実施
//       • gk_write_diff で変更を提出
//       ↓
//   [Commander]
//       • JCross diff を逆変換
//       • 実ファイルへ書き込み
//       • ユーザーへ結果を報告

@MainActor
final class CommanderOrchestrator: ObservableObject {

    static let shared = CommanderOrchestrator()

    // MARK: - State

    @Published var messages: [OrchestratorMessage] = []
    @Published var phase: ConversationPhase = .idle
    @Published var isProcessing = false

    enum ConversationPhase: Equatable {
        case idle
        case commanderPlanning(step: String)
        case fetchingVault(file: String)
        case workerCalling
        case workerThinking
        case reverseTranspiling
        case writingToDisk(file: String)
        case done
        case error(String)
    }

    internal let state  = GatekeeperModeState.shared
    private let mcpServer = GatekeeperMCPServer.shared
    private var vault: JCrossVault { state.vault }
    private let memoryArchiver = SessionMemoryArchiver.shared

    private init() {
        // 起動時に .agents/skills/ をスキャンして mid/SKILL_*.jcross に登録。
        // これにより Commander がスキルを注入された状態でユーザーに応答できる。
        Task.detached(priority: .background) {
            let workspaceURL = await GatekeeperModeState.shared.vault.workspaceURL
            await SessionMemoryArchiver.shared.indexSkills(workspaceRoot: workspaceURL)
        }
    }

    // MARK: - Entry Point

    /// ユーザーメッセージを受け取り、全フローを実行する
    func handleUserMessage(_ message: String, images: [String] = []) async {
        guard !isProcessing else { return }
        isProcessing = true
        defer {
            isProcessing = false
            Task { @MainActor [weak self] in self?.flushRemainingMessages() }
        }

        // Vault が最新のファイルを把握できるよう、実行前に必ず差分を更新する
        await vault.updateDelta()

        appendMessage(.user(message))
        let isJp = AppLanguage.shared.isJapanese

        var currentUserMessage = message

        if !images.isEmpty {
            appendMessage(.system(isJp ? "👁️ 添付画像を Local Vision Model (\(state.commanderModel)) で解析中..." : "👁️ Analyzing attached images via Local Vision Model (\(state.commanderModel))..."))
            let visionPrompt = isJp ? "この画像の内容を詳細に説明してください。特にUI要素、コードスニペット、エラー画面、アーキテクチャ図に焦点を当ててください。" : "Describe the contents of this image in detail, particularly focusing on UI elements, code snippets, errors, or any architectural diagrams."
            let ollamaModel = state.commanderModel
            if let description = await OllamaClient.shared.generateConversation(
                model: ollamaModel,
                messages: [(role: "user", content: visionPrompt)],
                imagesForLastUserMessage: images,
                maxTokens: 1024,
                temperature: 0.2
            ) {
                currentUserMessage += "\n\n[Local Vision Analysis of Attached Image]\n" + description
                appendMessage(.system(isJp ? "✅ 画像解析完了。" : "✅ Image analysis complete."))
            } else {
                appendMessage(.system(isJp ? "⚠️ 画像解析に失敗しました。画像の内容は無視されます。" : "⚠️ Failed to analyze image. Image content will be ignored."))
            }
        }

        // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        // 外側ループ: Commander 自律制御ループ
        // Commander が continueLoop=true を返す間、ユーザー入力なしで
        // 次のバッチを自動処理する。安全キャップ: maxOuterIterations。
        // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        // ── AMSCP (Adaptive-Mesh Sequential Convex Programming) 軌道制御変数 ──
        var trustRegionSize = 5       // トラスト領域：1バッチあたりの最大処理ファイル数
        var systemCovariance = 0.0    // システムの不確実性（ビルドエラー等による軌道逸脱率）
        let keepOutZones = ["Auth", "Security", "Config", "Settings", ".env"] // 障害物（確率的制約）
        // ──────────────────────────────────────────────────────────────────

        var outerIteration = 0
        let maxOuterIterations = 500
        var shouldContinue = true
        var totalFilesApplied = 0
        var lastWorkerSummary = ""

        outerLoop: while shouldContinue && outerIteration < maxOuterIterations && !Task.isCancelled {
            outerIteration += 1
            let batchLabel = outerIteration > 1
                ? (isJp ? " (バッチ \(outerIteration))" : " (Batch \(outerIteration))")
                : ""

            // Step 1: Commander
            phase = .commanderPlanning(step: (isJp ? "Commander: 意図解析中" : "Commander: Analyzing") + batchLabel + "...")
            if outerIteration == 1 {
                appendMessage(.system(isJp
                    ? "🧠 Commander が意図を解析し、関連ファイルを特定します..."
                    : "🧠 Commander analyzing intent and selecting relevant files..."))
            } else {
                appendMessage(.system(isJp
                    ? "🔁 バッチ \(outerIteration): 次のファイルを選択中... (残り約 \(countRemainingSourceFiles()) ファイル)"
                    : "🔁 Batch \(outerIteration): Selecting next files... (~\(countRemainingSourceFiles()) remaining)"))
            }

            let commanderPlan = await runCommander(
                userMessage: currentUserMessage, 
                iteration: outerIteration,
                trustRegionSize: trustRegionSize,
                systemCovariance: systemCovariance,
                keepOutZones: keepOutZones
            )
            appendMessage(.commander(commanderPlan.explanation))

            if commanderPlan.relevantFiles.isEmpty && !commanderPlan.continueLoop {
                if outerIteration == 1 {
                    appendMessage(.system(isJp ? "⚠️ 処理対象ファイルが見つかりません。" : "⚠️ No files to process."))
                }
                break outerLoop
            }

            // Step 2: Worker ループ（ビルドエラーリトライ込み）
            var workerResult: WorkerResult!
            var hasBuildError = false
            var buildErrorMessage = ""
            var diffsToApply: [(String, String, JCrossVault.VaultEntry?, URL)] = []
            var maxRetries = 3
            var fallbackCount = 0
            var currentInstruction = commanderPlan.workerInstructions.isEmpty
                ? currentUserMessage : commanderPlan.workerInstructions

            innerLoop: while maxRetries >= 0 {
                guard !Task.isCancelled else { break outerLoop }
                phase = .workerCalling

                let relatedFiles = commanderPlan.relevantFiles.isEmpty
                    ? inferRelevantFiles(from: currentInstruction)
                    : commanderPlan.relevantFiles

                // ── Obstacle Avoidance (Keep-Out Zones) ──
                var safeFiles: [String] = []
                for file in relatedFiles {
                    let isObstacle = keepOutZones.contains { file.localizedCaseInsensitiveContains($0) }
                    if isObstacle {
                        appendMessage(.system(isJp ? "🛡️ 障害物回避: \(file) は Keep-Out Zone のため除外されました" : "🛡️ Obstacle Avoidance: \(file) excluded (Keep-Out Zone)"))
                    } else {
                        safeFiles.append(file)
                    }
                }
                // Trust Region でバッチサイズを制限
                let filesToProcess = Array(safeFiles.prefix(trustRegionSize))
                if filesToProcess.count < safeFiles.count {
                    appendMessage(.system(isJp ? "📉 トラスト領域制限: \(safeFiles.count)ファイル中 \(trustRegionSize)ファイルのみ処理" : "📉 Trust Region Limit: processing \(trustRegionSize) out of \(safeFiles.count) files"))
                }

                let vaultContext = await buildVaultContext(from: filesToProcess)

                workerResult = await runWorker(
                    userMessage: currentInstruction,
                    commanderPlan: commanderPlan,
                    vaultContext: vaultContext,
                    trustRegionSize: trustRegionSize,
                    systemCovariance: systemCovariance
                )
                lastWorkerSummary = workerResult.summary
                phase = .workerThinking
                for toolCall in workerResult.toolCalls {
                    _ = await mcpServer.dispatch(toolName: toolCall.name, input: toolCall.input)
                }
                appendMessage(.system("📥 Worker:\n\(workerResult.summary)"))

                if workerResult.diffs.isEmpty { diffsToApply.removeAll(); break innerLoop }

                phase = .commanderPlanning(step: isJp ? "JCross IR を解読中..." : "Decoding JCross IR...")
                hasBuildError = false
                diffsToApply.removeAll()
                let transpiler = PolymorphicJCrossTranspiler.shared
                var allErrors = ""

                let validDiffs = workerResult.diffs.filter { !$0.content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
                var processedDiffs = 0

                for diff in validDiffs {
                    guard !Task.isCancelled else { break outerLoop }
                    processedDiffs += 1
                    let pct = Int((Double(processedDiffs) / Double(max(1, validDiffs.count))) * 100.0)
                    await MainActor.run { self.phase = .commanderPlanning(step: "🔄 [\(pct)%] \(diff.path)") }

                    var targetEntry = vault.vaultIndex?.entries[diff.path]
                    if targetEntry == nil, let index = vault.vaultIndex {
                        let norm = diff.path.trimmingCharacters(in: .init(charactersIn: "/"))
                        targetEntry = index.entries.values.first {
                            let ep = $0.relativePath.lowercased()
                            return ep.hasSuffix(norm.lowercased()) || norm.lowercased().hasSuffix(ep)
                        }
                    }

                    let originalContent: String
                    let schemaID: String
                    let targetFileURL: URL
                    let isActuallyNew: Bool

                    if let entry = targetEntry {
                        let srcURL = vault.workspaceURL.appendingPathComponent(entry.relativePath)
                        originalContent = await Task.detached(priority: .userInitiated) {
                            (try? String(contentsOf: srcURL, encoding: .utf8)) ?? ""
                        }.value
                        schemaID = entry.schemaSessionID
                        targetFileURL = vault.workspaceURL.appendingPathComponent(entry.relativePath)
                        isActuallyNew = false
                    } else {
                        originalContent = ""; schemaID = ""
                        targetFileURL = vault.workspaceURL.appendingPathComponent(diff.path)
                        isActuallyNew = true
                    }

                    let restored: String
                    if isActuallyNew {
                        let isJCross = diff.content.contains("_JCROSS_") || diff.content.contains("__node_") || diff.content.contains("_AST_") || diff.content.contains("// POLYMORPHIC_JCROSS") || diff.content.contains("JCROSS_") || diff.content.contains("NODE[")
                        if isJCross {
                            restored = PolymorphicJCrossTranspiler.ruleBasedFallbackWithoutSchema(diff.content)
                        } else {
                            restored = sanitizeNewFileContent(diff.content, fileExtension: targetFileURL.pathExtension)
                        }
                    } else {
                        guard let r = await transpiler.reverseTranspile(jcross: diff.content, originalContent: originalContent, schemaID: schemaID) else {
                            hasBuildError = true
                            allErrors += "Reverse transpile failed: \(diff.path)\n"
                            continue
                        }
                        restored = r
                    }

                    let cu = targetFileURL; let cr = restored
                    await Task.detached(priority: .userInitiated) {
                        try? FileManager.default.createDirectory(at: cu.deletingLastPathComponent(), withIntermediateDirectories: true)
                        try? cr.write(to: cu, atomically: true, encoding: .utf8)
                    }.value

                    if cu.pathExtension.lowercased() == "toml", cu.lastPathComponent == "Cargo.toml" {
                        let wsURL = vault.workspaceURL
                        await Task.detached(priority: .utility) { [weak self] in
                            guard let self = self else { return }
                            self.sanitizeCargoToml(tomlURL: cu)
                            self.ensureWorkspaceCargoToml(targetRoot: wsURL, manifestURL: cu)
                            self.injectCargoTargetIfNeeded(tomlURL: cu)
                        }.value
                    }
                    diffsToApply.append((restored, originalContent, targetEntry, targetFileURL))
                }

                // ビルド検証（クロスプラットフォームはスキップ）
                if !hasBuildError {
                    let troot = diffsToApply.first?.3.deletingLastPathComponent() ?? vault.workspaceURL
                    if !isCrossCompilationTarget(url: troot) {
                        for (_, _, entry, furl) in diffsToApply {
                            let ext = furl.pathExtension.lowercased()
                            guard ["swift","rs","ts","tsx"].contains(ext) else { continue }
                            let (ok, err) = await runBuildCheck(workspaceURL: troot, fileURL: furl)
                            if !ok {
                                hasBuildError = true
                                allErrors += "File: \(entry?.relativePath ?? furl.lastPathComponent)\n\(err)\n"
                            }
                        }
                    }
                }

                if hasBuildError {
                    buildErrorMessage = allErrors
                    
                    // ── Covariance Steering & Adaptive Mesh (SCP) ──
                    systemCovariance = min(1.0, systemCovariance + 0.5) // 軌道の不確実性が上昇
                    trustRegionSize = max(1, trustRegionSize / 2) // トラスト領域の縮小（安全側へフォールバック）
                    appendMessage(.system(isJp ? "⚠️ エラー検知：状態共分散上昇 (Covariance: \(systemCovariance))。トラスト領域を \(trustRegionSize) に縮小" : "⚠️ Error detected: Covariance \(systemCovariance). Shrinking Trust Region to \(trustRegionSize)"))
                    // ───────────────────────────────────────────────
                    
                    appendMessage(.system("❌ Build error. Retrying... (\(maxRetries) left)"))
                    currentInstruction = "Fix build errors:\n```\n\(buildErrorMessage)\n```\nProvide CORRECTED diffs."
                    maxRetries -= 1
                    if maxRetries < 0 {
                        if fallbackCount == 0 {
                            appendMessage(.system(isJp ? "⚠️ リトライ上限到達。根本的バグの可能性があるためクラウドLLMへ差し戻し..." : "⚠️ Retry limit reached. Escalating fundamental fix to Cloud LLM..."))
                            currentInstruction = "CRITICAL: You failed 3 times. Your generated JCross IR still fails to compile.\nErrors:\n\(allErrors)\nDO NOT USE YOUR PREVIOUS LOGIC. Re-think your entire approach from scratch and provide a completely new valid solution."
                            fallbackCount += 1
                            maxRetries = 1 // 最後の泣きの1回（フルリセット）
                            systemCovariance = 1.0
                            trustRegionSize = 1
                            diffsToApply.removeAll()
                            continue
                        } else {
                            appendMessage(.system(isJp ? "🚨 差し戻しも失敗しました。安全のためバッチ停止。" : "🚨 Escalation failed. Halting batch."))
                            diffsToApply.removeAll() // 🚨 CRITICAL FIX: Do not apply broken files
                            shouldContinue = false   // 🚨 CRITICAL FIX: Stop the entire Commander loop if a batch fails completely
                            break innerLoop
                        }
                    }
                } else {
                    // ── Covariance Steering & Adaptive Mesh (SCP) ──
                    systemCovariance = max(0.0, systemCovariance - 0.2) // 軌道安定により不確実性が減少
                    trustRegionSize = min(20, trustRegionSize + 2) // トラスト領域の拡大（メッシュを荒くして計算効率化）
                    if !diffsToApply.isEmpty {
                        appendMessage(.system(isJp ? "✅ バッチ成功：軌道安定。トラスト領域を \(trustRegionSize) に拡大" : "✅ Batch success: Orbit stable. Expanding Trust Region to \(trustRegionSize)"))
                    }
                    // ───────────────────────────────────────────────
                    break innerLoop
                }
            } // end innerLoop

            // Step 3: ユーザー承認
            var batchApplied = 0
            for (restored, originalContent, entry, fileURL) in diffsToApply {
                guard !Task.isCancelled else { break }
                let req = FileApprovalRequest(fileURL: fileURL, newContent: restored, originalContent: originalContent, kind: .overwrite)
                await MainActor.run { AppState.shared?.pendingFileApproval = req }
                let approved = await req.waitForDecision()
                let dp = entry?.relativePath ?? fileURL.lastPathComponent
                if approved {
                    phase = .writingToDisk(file: dp)
                    try? restored.write(to: fileURL, atomically: true, encoding: .utf8)
                    await vault.updateDelta()
                    appendMessage(.system(isJp ? "✅ 承認: \(dp)" : "✅ Approved: \(dp)"))
                    batchApplied += 1; totalFilesApplied += 1
                } else {
                    appendMessage(.system(isJp ? "⏸ 拒否: \(dp)" : "⏸ Rejected: \(dp)"))
                }
            }

            // Step 4: バッチ完了後の自動記憶保存 → 次回セッションで boot() から再参照可能
            if batchApplied > 0 {
                let batchFiles = diffsToApply.map { $0.3.lastPathComponent }.joined(separator: ", ")
                let bL1 = "バッチ\(outerIteration)完了: \(batchApplied)ファイル変換 (累計\(totalFilesApplied))"
                let bL2 = """
                OP.FACT("batch_number", "\(outerIteration)")
                OP.FACT("batch_files", "\(batchFiles)")
                OP.STATE("total_converted", "\(totalFilesApplied)")
                OP.STATE("continue_loop", "\(commanderPlan.continueLoop)")
                OP.FACT("loop_reason", "\(commanderPlan.loopReason)")
                """
                let bL3 = "Batch \(outerIteration): \(batchFiles)"
                let cBL1 = bL1; let cBL2 = bL2; let cBL3 = bL3; let cIter = outerIteration
                Task.detached(priority: .background) {
                    SessionMemoryArchiver.shared.archiveSkillNode(
                        title: "GK_BATCH_\(cIter)", l1: cBL1, l2: cBL2, l3: cBL3
                    )
                }
            }

            // Step 5: Commander の自律ループ判断
            if commanderPlan.continueLoop && batchApplied > 0 && !Task.isCancelled {
                shouldContinue = true
                currentUserMessage = "Continue conversion batch \(outerIteration + 1). \(commanderPlan.loopReason). Already converted \(totalFilesApplied) files."
                appendMessage(.system(isJp
                    ? "🔁 Commander: 次のバッチへ... (\(commanderPlan.loopReason))"
                    : "🔁 Commander: Advancing to next batch... (\(commanderPlan.loopReason))"))
            } else {
                shouldContinue = false
            }
        } // end outerLoop

        // Step 6: タスク完了 & 最終記憶保存
        if totalFilesApplied == 0 {
            appendMessage(.system(isJp ? "⚠️ 変更が適用されませんでした。" : "⚠️ No modifications applied."))
        } else {
            appendMessage(.system(isJp
                ? "🎉 完了: \(totalFilesApplied) ファイルを変換しました (\(outerIteration) バッチ)"
                : "🎉 Done: Converted \(totalFilesApplied) files (\(outerIteration) batches)"))
                
            // ── Auto-Launch Web App Preview ──
            let packageJsonURL = vault.workspaceURL.appendingPathComponent("frontend/package.json")
            if FileManager.default.fileExists(atPath: packageJsonURL.path) {
                appendMessage(.system(isJp ? "🌐 Webサーバーを起動し、プレビューを表示します..." : "🌐 Starting development server..."))
                let process = Process()
                process.executableURL = URL(fileURLWithPath: "/bin/bash")
                process.arguments = ["-c", "cd '\(vault.workspaceURL.appendingPathComponent("frontend").path)' && npm run dev"]
                try? process.run()
                
                Task { @MainActor in
                    let artifact = Artifact(type: .browser, content: "http://localhost:5173", title: "Live Preview")
                    AppState.shared?.ingestArtifact(artifact)
                }
            }
            // ────────────────────────────────

            // タスク完了ログを near/ に保存 → 次回セッション boot() で「前回の続き」として参照
            let tL1 = "タスク完了: \(totalFilesApplied)ファイル変換 (\(outerIteration)バッチ)"
            let tL2 = """
            OP.FACT("total_files_converted", "\(totalFilesApplied)")
            OP.FACT("total_batches", "\(outerIteration)")
            OP.FACT("original_request", "\(message.prefix(200))")
            OP.STATE("task_status", "completed")
            """
            let cTL1 = tL1; let cTL2 = tL2; let cMsg = message
            Task.detached(priority: .background) {
                SessionMemoryArchiver.shared.archiveSkillNode(
                    title: "GK_TASK_COMPLETE", l1: cTL1, l2: cTL2, l3: "Request: \(cMsg)"
                )
            }
            
            // Auto-Distillation: Evaluate if the completed task should be a reusable skill
            let taskSummary = lastWorkerSummary
            Task.detached(priority: .background) { [weak self] in
                await self?.autoDistillSkillIfNeeded(userMessage: cMsg, workerSummary: taskSummary)
            }
        }

        phase = .commanderPlanning(step: isJp ? "最終回答を生成中..." : "Generating final response...")
        let finalSummaryText = "Applied changes to \(totalFilesApplied) files successfully."
        let finalResponse = await generateFinalResponse(userMessage: message, workerSummary: finalSummaryText, success: totalFilesApplied > 0)
        appendMessage(.assistant(finalResponse))
        appendMessage(.system(isJp ? "🧠 remember() 実行完了。" : "🧠 remember() executed."))

        phase = .done
        try? await Task.sleep(nanoseconds: 500_000_000)
        phase = .idle
    }

    // MARK: - Commander (BitNet → MLX → Ollama 3段フォールバック)
    //
    // 優先順位:
    //   1. BitNet  — 超軽量ローカル (未インストール時はスキップ)
    //   2. MLX     — Apple Silicon ネイティブ in-process 推論 (モデルロード済み時)
    //   3. Ollama  — HTTP ローカルサーバー (最終フォールバック)

    private struct CommanderPlan {
        let explanation: String
        let relevantFiles: [String]
        let workerInstructions: String
        /// Commander がこのタスクはまだ継続が必要と判断した場合 true。
        /// モデルが自律的にループを制御する。
        let continueLoop: Bool
        /// ループを続ける理由 (ログ・ユーザー向け表示に使用)
        let loopReason: String
    }

    // MARK: - Commander Plan Generation
    //
    // Commander が受け取る情報:
    // 1. プロジェクト構造（全 JCross パス）
    // 2. 既に変換済みのターゲットファイル（続き指示への対応）
    // 3. ユーザーの要求
    //
    // Commander は relevantFiles として次に変換すべきソースファイルを返す。
    // この値が buildVaultContext に渡され、Worker への JCross コンテキストになる。
    private func runCommander(
        userMessage: String, 
        iteration: Int = 1,
        trustRegionSize: Int = 5,
        systemCovariance: Double = 0.0,
        keepOutZones: [String] = []
    ) async -> CommanderPlan {
        let projectStructure = buildProjectSummary()
        let alreadyConvertedSummary = buildAlreadyConvertedSummary()
        let remainingCount = countRemainingSourceFiles()
        let isJp = AppLanguage.shared.isJapanese

        let prompt = """
        You are the Commander of the Verantyx Cognitive System. Batch \(iteration).
        Your role: select the next SOURCE files to process, AND decide if more batches are needed.


        PROJECT STRUCTURE (source files):
        \(projectStructure)

        ALREADY CONVERTED:
        \(alreadyConvertedSummary.isEmpty ? "(none yet)" : alreadyConvertedSummary)

        ESTIMATED REMAINING SOURCE FILES: \(remainingCount)

        [AMSCP CONTROL PARAMETERS]
        TRUST REGION (MAX BATCH SIZE): \(trustRegionSize)
        SYSTEM COVARIANCE (ERROR RATE): \(systemCovariance)
        OBSTACLES (KEEP-OUT ZONES): \(keepOutZones.joined(separator: ", "))

        USER REQUEST: \(userMessage)

        Respond ONLY in JSON:
        {
          "explanation": "Brief plan for this batch",
          "relevant_files": ["path/to/source1", "path/to/source2"],
          "worker_instructions": "Instructions for Worker including target output directory",
          "continue_loop": true,
          "loop_reason": "X files remain unconverted"
        }

        RULES:
        - Select up to \(trustRegionSize) SOURCE files per batch (not already-converted target files).
        - DO NOT select any files matching the OBSTACLES (Keep-Out Zones).
        - If SYSTEM COVARIANCE > 0.0, it means the previous batch had build errors. Output strictly safer, more constrained worker instructions.
        - Set continue_loop=true if REMAINING > 0 after this batch.
        - Set continue_loop=false when all source files have been converted.
        - For non-bulk tasks (Q&A, single file edits), set continue_loop=false.
        """

        // 1. claw-code ハイジャック済みプロンプト (base)
        let clawBasePrompt = await loadSkillPrompt(skillId: "claw_commander_hijacked") ?? ""
        // 2. 255スキルからメッセージに最適なJCross操作をマッチング
        let skillHint = await matchSkillForMessage(userMessage)
        let systemPrompt = """
        You are a Commander LLM. Respond ONLY in valid JSON. No markdown, no extra text.
        \(clawBasePrompt.isEmpty ? "" : "\n[CLAW-CODE FLOW BASE]\n" + String(clawBasePrompt.prefix(600)))
        \(skillHint.isEmpty ? "" : "\n[SKILL ENGINE — best match from 255 claw-code skills]\n" + skillHint)
        """

        let response = await callCommander(prompt: prompt, systemPrompt: systemPrompt)

        if let data = response.data(using: .utf8),
           let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            return CommanderPlan(
                explanation: json["explanation"] as? String ?? (isJp ? "ファイルを分析中..." : "Analyzing files..."),
                relevantFiles: json["relevant_files"] as? [String] ?? [],
                workerInstructions: json["worker_instructions"] as? String ?? userMessage,
                continueLoop: json["continue_loop"] as? Bool ?? false,
                loopReason: json["loop_reason"] as? String ?? ""
            )
        }

        return CommanderPlan(
            explanation: isJp ? "要求を処理します" : "Processing request",
            relevantFiles: Array(inferRelevantFiles(from: userMessage).prefix(5)),
            workerInstructions: userMessage,
            continueLoop: false,
            loopReason: ""
        )
    }

    /// まだ変換されていないソースファイルの推定数
    private func countRemainingSourceFiles() -> Int {
        if let map = L25IndexEngine.shared.projectMap {
            let targetPatterns = ["-clone", "-target", "-windows", "-linux", "-android", "-rust"]
            let total = map.entries.count
            let converted = map.entries.keys.filter { path in
                targetPatterns.contains(where: { path.lowercased().contains($0) })
            }.count
            return max(0, total - converted)
        }
        guard let index = vault.vaultIndex else { return 0 }
        let targetPatterns = ["-clone", "-target", "-windows", "-linux", "-android", "-rust"]
        let total = index.entries.keys.filter {
            !$0.contains(".build/") && !$0.contains(".git/") && !$0.hasPrefix(".")
        }.count
        let converted = index.entries.keys.filter { path in
            targetPatterns.contains(where: { path.lowercased().contains($0) })
        }.count
        return max(0, total - converted)
    }

    /// ターゲットディレクトリ（変換先）に既に存在するファイルをサマリー化。
    /// Commander に渡すことで「何がまだ変換されていないか」を判断させる。
    private func buildAlreadyConvertedSummary() -> String {
        let targetPatterns = ["-clone", "-target", "-windows", "-linux", "-android", "-rust"]
        
        if let map = L25IndexEngine.shared.projectMap {
            return map.entries.keys
                .filter { path in targetPatterns.contains(where: { path.lowercased().contains($0) }) }
                .sorted()
                .prefix(50)
                .map { "  ✅ \($0)" }
                .joined(separator: "\n")
        }
        
        guard let index = vault.vaultIndex else { return "" }
        let converted = index.entries.keys
            .filter { path in targetPatterns.contains(where: { path.lowercased().contains($0) }) }
            .sorted()
            .prefix(50)
            .map { "  ✅ \($0)" }
            .joined(separator: "\n")
        return converted
    }

    // MARK: - Worker (External API)

    private struct WorkerResult {
        let summary: String
        let toolCalls: [MCPToolCall]
        let diffs: [FileDiff]
    }

    private struct MCPToolCall {
        let name: String
        let input: [String: Any]
    }

    private struct FileDiff {
        let path: String
        let content: String
    }

    private func runWorker(
        userMessage: String,
        commanderPlan: CommanderPlan,
        vaultContext: String,
        trustRegionSize: Int,
        systemCovariance: Double
    ) async -> WorkerResult {
        let systemPrompt = await buildWorkerSystemPrompt()

        let projectSummary = buildProjectSummary()
        
        let userContent = """
        \(commanderPlan.workerInstructions)

        AVAILABLE PROJECT STRUCTURE (L2.5):
        \(projectSummary)

        \(vaultContext.isEmpty ? "" : "TARGET FILES (JCross IR):\n" + vaultContext)
        """

        // ── Visual Anchor ──
        let reasoningText = commanderPlan.workerInstructions.trimmingCharacters(in: .whitespacesAndNewlines)
        let anchorText = """
        DO NOT HALLUCINATE. FOLLOW STRICT JCROSS SYNTAX.
        Trust Region: \(trustRegionSize) | Covariance: \(systemCovariance)
        
        <THINKING_SCAFFOLD>
        \(reasoningText)
        </THINKING_SCAFFOLD>
        """
        let anchorImgBase64 = await CognitiveAnchorEngine.shared.getCustomAnchor(title: "COGNITIVE REASONING SCAFFOLD", text: anchorText)
        // ───────────────────

        let response = await callExternalAPIWithTools(
            systemPrompt: systemPrompt,
            userMessage: userContent,
            imageBase64: anchorImgBase64
        )

        return response
    }

    private func callExternalAPIWithTools(
        systemPrompt: String,
        userMessage: String,
        imageBase64: String? = nil
    ) async -> WorkerResult {
        let provider = state.workerProvider
        let isJp = AppLanguage.shared.isJapanese
        
        let responseResult = await CloudAPIClient.shared.send(
            systemPrompt: systemPrompt,
            userMessage: userMessage,
            imageBase64: imageBase64,
            provider: provider
        )
        
        let responseString: String
        switch responseResult {
        case .success(let text):
            responseString = text
        case .failure(let error):
            responseString = isJp
                ? "❌ External API Error: \(error.localizedDescription)\nAPIキーが設定されていないか、ネットワークエラーです。"
                : "❌ External API Error: \(error.localizedDescription)\nAPI key is not configured or network error occurred."
        }

        return WorkerResult(
            summary: responseString,
            toolCalls: [],  // TODO: Claude API の tool_use パース
            diffs: extractDiffs(from: responseString)
        )
    }

    private func generateFinalResponse(userMessage: String, workerSummary: String, success: Bool) async -> String {
        let prompt = """
        User request: \(userMessage)
        Worker result: \(workerSummary.prefix(500))
        """

        let sysPrompt = success ? """
            You are the Commander AI. 
            The Worker has just returned JCross IR modifications for the user's request.
            You have already decoded the modifications, verified them locally (simulated build inside Verantyx-IDE), and applied them successfully.
            
            YOUR TASK:
            Write a final response to the user in Japanese summarizing what was done.
            - Explicitly state that you verified the changes locally before applying them.
            - DO NOT repeat the prompt.
            - DO NOT output "### Assistant".
            - ONLY output the final Japanese response.
            """ : """
            You are the Commander AI. 
            The Worker attempted to fulfill the user's request, but the generated modifications FAILED local build verification or were rejected.
            NO changes were applied to the user's files.
            
            YOUR TASK:
            Write an apologetic final response to the user in Japanese explaining that the operation failed safety checks.
            - Explicitly state that NO files were modified to protect the system.
            - DO NOT repeat the prompt.
            - DO NOT output "### Assistant".
            - ONLY output the final Japanese response.
            """

        return await callCommander(
            prompt: prompt,
            systemPrompt: sysPrompt
        )
    }

    // MARK: - Auto-Distillation (Self-Learning)

    private func autoDistillSkillIfNeeded(userMessage: String, workerSummary: String) async {
        let isJp = AppLanguage.shared.isJapanese
        let prompt = """
        Analyze the following task completion summary.
        User Request: \(userMessage)
        Worker Action: \(workerSummary.prefix(1500))

        Determine if this task represents a highly reusable programming skill, architectural pattern, or a complex bug fix that should be memorized as a generic 'Skill'.
        If YES, generate a YAML file content for this skill. It must contain 'name', 'description', 'goal', 'inputs', and 'use_when' fields, followed by a detailed 'steps' or 'payload' array.
        If NO, output exactly 'NO_SKILL_NEEDED'.
        
        Output ONLY 'NO_SKILL_NEEDED' or the raw YAML content. Do NOT wrap in ```yaml.
        """

        let systemPrompt = """
        You are the Verantyx Auto-Distillation Engine.
        Your job is to identify generic, reusable skills from completed tasks.
        Rules for YAML format:
        name: snake_case_name
        description: Brief description
        goal: What this skill achieves
        inputs: Required inputs
        use_when: When to trigger this skill
        payload:
          - Step 1
          - Step 2
        """

        let response = await callCommander(prompt: prompt, systemPrompt: systemPrompt)
        let trimmed = response.trimmingCharacters(in: .whitespacesAndNewlines)

        if trimmed == "NO_SKILL_NEEDED" || trimmed.isEmpty || trimmed.contains("NO_SKILL_NEEDED") {
            return
        }

        // Clean up markdown code blocks if the model ignored the instructions
        var yamlContent = trimmed
        if yamlContent.hasPrefix("```yaml") {
            yamlContent = yamlContent.replacingOccurrences(of: "```yaml\n", with: "")
        }
        if yamlContent.hasPrefix("```") {
            yamlContent = yamlContent.replacingOccurrences(of: "```\n", with: "")
        }
        if yamlContent.hasSuffix("```") {
            yamlContent = String(yamlContent.dropLast(3))
        }

        // Extract a name to save the file
        let lines = yamlContent.components(separatedBy: .newlines)
        var skillName = "auto_skill_\(Int(Date().timeIntervalSince1970))"
        for line in lines {
            if line.hasPrefix("name:") {
                let extracted = line.dropFirst(5).trimmingCharacters(in: .whitespaces)
                    .trimmingCharacters(in: .init(charactersIn: "\"'"))
                if !extracted.isEmpty {
                    skillName = extracted
                }
                break
            }
        }

        // Save to .agents/skills/
        let workspaceURL = await MainActor.run { vault.workspaceURL }
        let skillsDir = workspaceURL.appendingPathComponent(".agents/skills")
        try? FileManager.default.createDirectory(at: skillsDir, withIntermediateDirectories: true)
        
        let fileURL = skillsDir.appendingPathComponent("\(skillName).yaml")
        try? yamlContent.write(to: fileURL, atomically: true, encoding: .utf8)
        
        // Notify IDE
        await MainActor.run {
            self.appendMessage(.system(isJp 
                ? "🧠 [Self-Distillation] 再利用可能なパターンを検出しました。スキル '\(skillName).yaml' として自動保存しました。" 
                : "🧠 [Self-Distillation] Reusable pattern detected. Auto-saved as skill '\(skillName).yaml'."))
        }
    }

    // MARK: - callCommander: BitNet → MLX → Ollama 3段フォールバック

    /// GatekeeperMode の LocalLLM 呼び出し口。
    /// 1. BitNetEngineManager が .ready → BitNetCommanderEngine
    /// 2. AppState.modelStatus が .mlxReady → MLXRunner (in-process, ゼロ HTTP)
    /// 3. それ以外 → Ollama HTTP API
    private func callCommander(prompt: String, systemPrompt: String) async -> String {
        let isMlxSelected = state.commanderModel.contains("mlx-community/") || state.commanderModel.lowercased().contains("mlx")
        let allowExternal = await MainActor.run { state.allowExternalLLMForCommander }
        
        // ── Tier 1: BitNet ───────────────────────────────────────
        if !allowExternal || !isMlxSelected {
            if case .ready = await MainActor.run(body: { BitNetEngineManager.shared.status }) {
                let result = await BitNetCommanderEngine.shared.generate(
                    prompt: prompt,
                    systemPrompt: systemPrompt
                )
                if let result, !result.isEmpty {
                    return result
                }
            } else if !allowExternal {
                // If BitNet is forced but not ready, try to fall back or return an error
                appendMessage(.system("⚠️ BitNet is forced but not ready. Attempting to start daemon..."))
                await BitNetEngineManager.shared.checkInstallation()
                try? await Task.sleep(nanoseconds: 2_000_000_000)
                let result = await BitNetCommanderEngine.shared.generate(prompt: prompt, systemPrompt: systemPrompt)
                if let result, !result.isEmpty { return result }
                return "❌ Error: BitNet Commander forced but failed to initialize."
            }
        }

        // ── Tier 2: MLX (Apple Silicon ネイティブ in-process) ────
        if isMlxSelected {
            let currentMLX = await MLXRunner.shared.currentModelId
            if currentMLX != state.commanderModel {
                do {
                    appendMessage(.system("📦 Loading MLX Commander: \(state.commanderModel)"))
                    try await MLXRunner.shared.loadModel(id: state.commanderModel) { progress in
                        // Optional: Could append progress to UI if needed
                    }
                } catch {
                    return "❌ MLX Load Error: \(error.localizedDescription)"
                }
            }
            if let result = await callMLX(prompt: prompt, systemPrompt: systemPrompt), !result.isEmpty {
                return result
            }
        }

        // ── Tier 3: Ollama ────────────────────────

        return await self.callOllama(
            model: self.state.commanderModel,
            prompt: prompt,
            systemPrompt: systemPrompt
        )
    }

    // MARK: - MLX In-Process Call (Tier 2)

    /// MLXRunner.shared.generate() を直接呼び出す。
    /// HTTP なし / ポート競合なし / Apple Unified Memory 直接使用。
    /// システムプロンプトはプロンプト先頭に埋め込む (ChatML 形式)。
    private func callMLX(prompt: String, systemPrompt: String) async -> String? {
        // ChatML テンプレートで system + user を結合
        let fullPrompt = """
        <start_of_turn>system
        \(systemPrompt)<end_of_turn>
        <start_of_turn>user
        \(prompt)<end_of_turn>
        <start_of_turn>model
        """
        let maxTokens = await MainActor.run { AppState.shared?.maxTokensMLX ?? 2048 }
        let temp      = await MainActor.run { AppState.shared?.temperature   ?? 0.3 }

        do {
            let start  = Date()
            let result = try await MLXRunner.shared.generate(
                prompt:      fullPrompt,
                maxTokens:   maxTokens,
                temperature: temp
            )
            let elapsed = Date().timeIntervalSince(start)
            // tok/s 概算をプロセスログへ送信（4文字≈1トークン）
            let tps = Double(result.count / 4) / max(elapsed, 0.001)
            await MainActor.run {
                AppState.shared?.tokensPerSecond = tps
                AppState.shared?.logProcess(
                    "⚡ MLX Commander: \(String(format: "%.1f", tps)) tok/s",
                    kind: .perf
                )
            }
            return result
        } catch {
            await MainActor.run {
                AppState.shared?.logProcess(
                    "⚠️ MLX fallback failed: \(error.localizedDescription)",
                    kind: .system
                )
            }
            return nil
        }
    }

    // MARK: - Public Bridges (TranspilationPipeline から呼び出す)

    /// TranspilationPipeline 用: ローカルモデルを呼び出す公開ラッパー。
    func callLocalModel(prompt: String, systemPrompt: String) async -> String {
        let model = await MainActor.run { state.commanderModel }
        return await callOllama(model: model, prompt: prompt, systemPrompt: systemPrompt)
    }

    /// TranspilationPipeline 用: ビルド検証の公開ラッパー。
    func runBuildCheckPublic(workspaceURL: URL, fileURL: URL) async -> (Bool, String) {
        return await runBuildCheck(workspaceURL: workspaceURL, fileURL: fileURL)
    }

    // MARK: - Ollama API Call (Tier 3 フォールバック)

    private func callOllama(model: String, prompt: String, systemPrompt: String) async -> String {
        var endpoint = await MainActor.run {
            AppState.shared?.ollamaEndpoint ?? "http://127.0.0.1:11434"
        }
        endpoint = endpoint.replacingOccurrences(of: "localhost", with: "127.0.0.1")
        guard let url = URL(string: "\(endpoint)/api/chat") else { return "" }

        struct Msg: Encodable { let role: String; let content: String }
        struct Request: Encodable {
            let model: String; let messages: [Msg]
            let stream: Bool; let options: Options
            struct Options: Encodable { let temperature: Double; let num_predict: Int }
        }
        struct Response: Decodable {
            struct MsgD: Decodable { let role: String; let content: String }
            let message: MsgD
        }

        let temp      = await MainActor.run { AppState.shared?.temperature    ?? 0.3 }
        let maxTokens = await MainActor.run { AppState.shared?.maxTokensOllama ?? 1024 }

        let body = Request(
            model: model,
            messages: [
                Msg(role: "system", content: systemPrompt),
                Msg(role: "user", content: prompt)
            ],
            stream: false,
            options: .init(temperature: temp, num_predict: maxTokens)
        )

        guard let data = try? JSONEncoder().encode(body) else { return "❌ Commander Encode Error" }

        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.httpBody = data
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.timeoutInterval = 120

        do {
            let (respData, _) = try await URLSession.shared.data(for: req)
            let decoded = try JSONDecoder().decode(Response.self, from: respData)
            return decoded.message.content
        } catch {
            return "❌ Commander HTTP/Decode Error: \(error.localizedDescription)"
        }
    }

    // MARK: - Helpers

    private func buildProjectSummary() -> String {
        if let map = L25IndexEngine.shared.projectMap {
            let paths = map.entries.keys.sorted()
            return paths.prefix(300).map { path in
                let summary = map.entries[path]?.indexLine ?? ""
                return "📄 \(path) (\(summary))"
            }.joined(separator: "\n")
        } else if let index = vault.vaultIndex {
            let paths = index.entries.keys.sorted()
            let filteredPaths = paths.filter { path in
                !path.contains(".build/") && !path.contains(".git/") && !path.contains("node_modules/") && !path.hasPrefix(".")
            }
            // 階層が深すぎても全てのソースファイルが見えるようにする
            return filteredPaths.prefix(300).map { "📄 \($0)" }.joined(separator: "\n")
        } else {
            let items = vault.listDirectory(relativePath: "")
            return items.prefix(50).map { item in
                item.isDirectory ? "📁 \(item.name)/" : "📄 \(item.name)"
            }.joined(separator: "\n")
        }
    }

    private func buildWorkerSystemPrompt() async -> String {
        // 1. Optional Override based on generic skill prompt
        let skillOverride = await loadSkillPrompt(skillId: "verantyx_worker_system")
        if let override = skillOverride, !override.isEmpty {
            return override
        }
        // フォールバック: 強化版組み込みプロンプト
        return """
        You are a Worker AI operating ENTIRELY inside the JCross IR semantic space.
        You ONLY see JCross IR (obfuscated code). You do NOT have access to raw files.

        ## Output Format
        You MUST output JCross diffs using EXACTLY this format:

        ```jcross path:target/path/file.rs
        // Complete modified JCross IR content
        ```

        ## Critical Rules
        1. All identifiers (e.g. _JCROSS_核_1_) are node IDs — preserve them EXACTLY.
        2. 🚨 NO OMISSION PROTOCOL: You MUST output the ENTIRE file content. Do NOT omit any lines or use `// ...`. Verantyx overwrites the file entirely with your output, so omitted lines are permanently deleted!
        3. DO NOT use XML action tags (<ReadFile>, <function_result>, etc.).
        4. Secrets (∮...∲ style) are permanently redacted — leave exactly as-is.
        5. NEVER attempt to decode or reverse-engineer node IDs.
        6. FOLDER CLONING: Output converted code to the target clone folder ONLY.
           Example: verantyx-windows-target/src/path/file.rs
           NEVER overwrite original source files.
        7. 🚨 ANTI-HALLUCINATION PROTOCOL: DO NOT invent new `NODE[0xHEX]` or `HASH:0xHEX` structures.
           Verantyx strictly validates all hashes against local AST state. If you make up a fake hash, the build will fatally crash.
           To insert brand new logic, write the RAW UNCOMMENTED code directly (e.g. `pub struct Message { ... }`). Do NOT wrap it in fake JCross nodes, and do NOT comment out the new code.

        ## AI-to-AI Collaboration Protocol
        You are a sub-agent under Commander control.
        - Commander provides JCross IR context + instructions
        - You return JCross IR diffs for the specified files
        - Commander decodes, builds locally, and verifies before committing
        - If you cannot complete a task, output: ```jcross path:ERROR
        // REASON: <explanation>```

        ## Task Decomposition (when task is large)
        For bulk operations (>5 files), process files in the order provided.
        Output one ```jcross path:...``` block per file.
        """
    }

    private func getSkillsRoot() async -> URL? {
        return await MainActor.run {
            if let sp = AppState.shared?.cortexSkillsPath, !sp.isEmpty {
                return URL(fileURLWithPath: sp)
            }
            if let ws = AppState.shared?.workspaceURL {
                return ws.appendingPathComponent(".agents/skills")
            }
            return nil
        }
    }

    /// スキルDB (.agents/skills/) から指定 skillId のプロンプトテンプレートを読み込む
    private func loadSkillPrompt(skillId: String) async -> String? {
        guard let skillsRoot = await getSkillsRoot() else { return nil }
        let fm = FileManager.default
        guard let enumerator = fm.enumerator(at: skillsRoot, includingPropertiesForKeys: nil,
                                              options: [.skipsHiddenFiles]) else { return nil }
        for case let file as URL in enumerator {
            let ext = file.pathExtension.lowercased()
            guard ext == "yaml" || ext == "md" else { continue }
            guard let raw = try? String(contentsOf: file, encoding: .utf8) else { continue }
            guard raw.contains("name: \(skillId)") else { continue }
            if let start = raw.range(of: "## Prompt Template\n```\n"),
               let end = raw.range(of: "\n```", range: start.upperBound..<raw.endIndex) {
                return String(raw[start.upperBound..<end.lowerBound])
            }
            if let opLine = raw.split(separator: "\n").first(where: { $0.hasPrefix("jcross_op:") }) {
                return String(opLine.dropFirst("jcross_op: ".count))
                    .trimmingCharacters(in: .init(charactersIn: "\""))
            }
        }
        return nil
    }

    /// メッセージキーワードで全255スキルをスコアリングし最適JCross操作を返す
    func matchSkillForMessage(_ message: String) async -> String {
        guard let skillsRoot = await getSkillsRoot() else { return "" }
        let fm = FileManager.default
        guard let enumerator = fm.enumerator(at: skillsRoot, includingPropertiesForKeys: nil,
                                              options: [.skipsHiddenFiles]) else { return "" }
        let msgLower = message.lowercased()
        var bestScore = 0
        var bestName = ""; var bestOp = ""; var bestCat = ""

        for case let file as URL in enumerator {
            guard file.pathExtension.lowercased() == "yaml" else { continue }
            guard let raw = try? String(contentsOf: file, encoding: .utf8) else { continue }
            var name = ""; var cat = ""; var op = ""
            for line in raw.split(separator: "\n").prefix(10) {
                let l = String(line)
                if l.hasPrefix("name: ")      { name = String(l.dropFirst(6)).trimmingCharacters(in: .whitespaces) }
                if l.hasPrefix("category: ")  { cat  = String(l.dropFirst(10)).trimmingCharacters(in: .whitespaces) }
                if l.hasPrefix("jcross_op: ") { op   = String(l.dropFirst(11)).trimmingCharacters(in: .init(charactersIn: "\"")) }
            }
            guard !name.isEmpty, !op.isEmpty else { continue }
            let tokens = name
                .replacingOccurrences(of: "claw_cmd_", with: "")
                .replacingOccurrences(of: "claw_skill_", with: "")
                .replacingOccurrences(of: "claw_", with: "")
                .lowercased().split(separator: "_").map(String.init)
            var score = tokens.filter { $0.count > 2 && msgLower.contains($0) }.count
            if !cat.isEmpty && msgLower.contains(cat) { score += 2 }
            if score > bestScore { bestScore = score; bestName = name; bestOp = op; bestCat = cat }
        }
        guard bestScore > 0 else { return "" }
        return """

[SKILL MATCH] \(bestName) (category: \(bestCat), score: \(bestScore))
Recommended JCross op: \(bestOp)
Rule: think semantically in <thought>, output JCROSS_* in <action><payload>.
"""
    }


    private func inferRelevantFiles(from message: String) -> [String] {
        if let map = L25IndexEngine.shared.projectMap {
            let matches = map.entries.keys.filter { path in
                let filename = URL(fileURLWithPath: path).lastPathComponent.lowercased()
                let baseName = filename.components(separatedBy: ".").first ?? filename
                let summary = map.entries[path]?.indexLine.lowercased() ?? ""
                let lowerMsg = message.lowercased()
                return lowerMsg.contains(baseName) || (!summary.isEmpty && lowerMsg.contains(summary))
            }
            return Array(matches.prefix(5))
        }
        guard let index = vault.vaultIndex else { return [] }
        let matches = index.entries.keys.filter { path in
            let filename = URL(fileURLWithPath: path).lastPathComponent.lowercased()
            let baseName = filename.components(separatedBy: ".").first ?? filename
            return message.lowercased().contains(baseName)
        }
        return Array(matches.prefix(5))
    }

    // MARK: - Vault Context Builder (async)
    //
    // ① パス解決は MainActor 上でインメモリ辞書を参照（高速）
    // ② ファイル読み込みは Task.detached でバックグラウンドスレッドに逃がす
    //    → MainActor をブロックせず UI が応答し続ける
    private func buildVaultContext(from paths: [String]) async -> String {
        // ① MainActor 上でパスと対応する jcross ファイル URL を解決（辞書参照のみ・高速）
        var fileMap: [(path: String, url: URL)] = []
        let vaultRoot = vault.vaultRootURL

        if let index = vault.vaultIndex {
            var resolvedPaths: Set<String> = []
            for path in paths {
                if index.entries.keys.contains(path) {
                    resolvedPaths.insert(path)
                } else {
                    let prefix = path.hasSuffix("/") ? path : path + "/"
                    for key in index.entries.keys where key.hasPrefix(prefix) || key.contains(path) {
                        resolvedPaths.insert(key)
                        if resolvedPaths.count >= 10 { break }
                    }
                }
                if resolvedPaths.count >= 10 { break }
            }
            for path in resolvedPaths {
                if let entry = index.entries[path] {
                    fileMap.append((path: path, url: vaultRoot.appendingPathComponent(entry.jcrossPath)))
                }
            }
        } else {
            for path in paths {
                fileMap.append((path: path, url: vaultRoot.appendingPathComponent(path + ".jcross")))
            }
        }

        guard !fileMap.isEmpty else { return "" }

        // ② バックグラウンドスレッドでファイルを読む（MainActor を解放）
        let sortedMap = fileMap.sorted { $0.path < $1.path }
        return await Task.detached(priority: .userInitiated) {
            var context = ""
            for item in sortedMap {
                if let content = try? String(contentsOf: item.url, encoding: .utf8), !content.isEmpty {
                    context += "```jcross path:\(item.path)\n\(content)\n```\n\n"
                }
            }
            return context
        }.value
    }

    private func extractDiffs(from response: String) -> [FileDiff] {
        // JCross diff ブロックを抽出。
        // Workerは ```jcross path:... だけでなく ```rust path:... や ```toml path:... 形式でも出力することがある。
        // 全ての言語フェンス（```<lang> path:<path>）に対応する。
        var diffs: [FileDiff] = []
        // Matches: ```<lang> path:<filepath>\n<content>``` (lang is optional)
        let pattern = "```(?:[a-zA-Z0-9_+-]*)[ \t]+path:([^\\n`]+)\\n([\\s\\S]*?)```"
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return [] }

        let range   = NSRange(response.startIndex..., in: response)
        let matches = regex.matches(in: response, range: range)

        for match in matches {
            guard let pathRange    = Range(match.range(at: 1), in: response),
                  let contentRange = Range(match.range(at: 2), in: response)
            else { continue }

            let path    = String(response[pathRange]).trimmingCharacters(in: .whitespaces)
            let content = String(response[contentRange])
            // Skip empty paths or paths that look like they're code examples, not file paths
            guard !path.isEmpty, !path.contains("\n"), path.contains(".") || path.contains("/") else { continue }
            diffs.append(FileDiff(path: path, content: content))
        }

        return diffs
    }

    // MARK: - New File Content Sanitizer

    /// Strips Worker's explanatory comment lines from new files.
    /// TOML uses `#` for comments, not `//`.
    /// JSON doesn't allow comments at all.
    /// This prevents cargo / serde from rejecting syntactically invalid files.
    private func sanitizeNewFileContent(_ content: String, fileExtension: String) -> String {
        let ext = fileExtension.lowercased()
        guard ext == "toml" || ext == "json" || ext == "yaml" || ext == "yml" else {
            // For .rs, .ts, etc. — C-style comments are valid, keep as-is
            return content
        }

        var lines = content.components(separatedBy: "\n")

        // Remove leading lines that are Worker explanations (// …)
        while let first = lines.first,
              first.trimmingCharacters(in: .whitespaces).hasPrefix("//") {
            lines.removeFirst()
        }

        // For TOML: convert any remaining `//` comment lines to `#` comments
        if ext == "toml" {
            lines = lines.map { line in
                let trimmed = line.trimmingCharacters(in: .whitespaces)
                if trimmed.hasPrefix("//") {
                    return line.replacingOccurrences(of: "//", with: "#", range: line.range(of: "//"))
                }
                return line
            }
        }

        return lines.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
    }

    // MARK: - Workspace Cargo.toml Auto-Generation (Always-Regenerate + Validated + Deduplicated)

    /// Generates a valid `[workspace]` Cargo.toml at `targetRoot` on **every call**.
    ///
    /// ## Why Always-Regenerate?
    /// Previous sessions leave stale members under targetRoot. These may have valid source
    /// files but duplicate package names, causing `cargo` to fail with
    /// "two packages named X in this workspace".
    ///
    /// ## Member Deduplication (NEW)
    /// If a discovered Cargo.toml has the same `name =` value as the primary manifest,
    /// it is a ghost from a previous session. It is:
    ///   1. Excluded from the workspace member list.
    ///   2. **Renamed** to `_stale_Cargo.toml` so future sessions cannot re-discover it.
    ///
    /// ## Validation Pipeline (per discovered Cargo.toml)
    ///   sanitize → inject → hasSrcMain/hasSrcLib check → name-dedup check → include
    nonisolated private func ensureWorkspaceCargoToml(targetRoot: URL, manifestURL: URL) {
        let workspaceToml = targetRoot.appendingPathComponent("Cargo.toml")

        // Helper: compute relative path of the *package directory* from targetRoot
        func relPath(_ url: URL) -> String {
            var rel = url.deletingLastPathComponent().path
            if rel.hasPrefix(targetRoot.path) {
                rel = String(rel.dropFirst(targetRoot.path.count))
                    .trimmingCharacters(in: CharacterSet(charactersIn: "/"))
            }
            return rel.isEmpty ? "src-tauri" : rel
        }

        // Helper: extract `name = "..."` from TOML content
        func extractPackageName(from content: String) -> String? {
            // Scan only the [package] section
            guard let pkgRange = content.range(of: "[package]") else { return nil }
            let afterPkg = String(content[pkgRange.upperBound...])
            let nextSection = afterPkg.range(of: "\n[")?.lowerBound ?? afterPkg.endIndex
            let pkgBlock = String(afterPkg[..<nextSection])
            guard let nameRange = pkgBlock.range(
                of: #"name\s*=\s*"([^"]+)""#, options: .regularExpression) else { return nil }
            let match = String(pkgBlock[nameRange])
            return match.components(separatedBy: "\"").dropFirst().first.map { String($0) }
        }

        // ── Primary member ─────────────────────────────────────────────────────
        let primaryContent = (try? String(contentsOf: manifestURL, encoding: .utf8)) ?? ""
        let primaryName = extractPackageName(from: primaryContent) ?? ""
        var validMembers: [String] = [relPath(manifestURL)]

        // ── Discover additional Cargo.toml files under targetRoot ──────────────
        if let enumerator = FileManager.default.enumerator(
            at: targetRoot,
            includingPropertiesForKeys: nil,
            options: [.skipsHiddenFiles]
        ) {
            for case let fileURL as URL in enumerator {
                guard fileURL.lastPathComponent == "Cargo.toml",
                      fileURL.path != workspaceToml.path,
                      fileURL.path != manifestURL.path else { continue }

                // ── Step 1: Repair ──────────────────────────────────────────
                sanitizeCargoToml(tomlURL: fileURL)
                injectCargoTargetIfNeeded(tomlURL: fileURL)

                guard let content = try? String(contentsOf: fileURL, encoding: .utf8) else { continue }

                // ── Step 2: Source-file check (ghost package guard) ─────────
                let packageDir = fileURL.deletingLastPathComponent()
                let hasSrcMain = FileManager.default.fileExists(
                    atPath: packageDir.appendingPathComponent("src/main.rs").path)
                let hasSrcLib  = FileManager.default.fileExists(
                    atPath: packageDir.appendingPathComponent("src/lib.rs").path)
                guard hasSrcMain || hasSrcLib else { continue }

                // ── Step 3: [lib] sanity after repair ───────────────────────
                if content.contains("[lib]") {
                    let hasExplicitPath = content.range(
                        of: #"path\s*="#, options: .regularExpression) != nil
                    guard hasSrcLib || hasExplicitPath else { continue }
                }

                // ── Step 4: Package-name deduplication ──────────────────────
                // If this discovered package has the same name as the primary,
                // it is a stale ghost from a previous session.
                // PERMANENTLY INVALIDATE IT by renaming its Cargo.toml.
                if !primaryName.isEmpty,
                   let discoveredName = extractPackageName(from: content),
                   discoveredName == primaryName {
                    let staleURL = fileURL.deletingLastPathComponent()
                        .appendingPathComponent("_stale_Cargo.toml")
                    try? FileManager.default.moveItem(at: fileURL, to: staleURL)
                    continue // Excluded from workspace
                }

                let rel = relPath(fileURL)
                if !validMembers.contains(rel) {
                    validMembers.append(rel)
                }
            }
        }

        let membersList = validMembers.map { "    \"\($0)\"" }.joined(separator: ",\n")
        var finalContent = """
        # Auto-generated Cargo workspace — Verantyx Windows Target
        # Regenerated unconditionally each session. Do not hand-edit the workspace section.
        [workspace]
        members = [
        \(membersList)
        ]
        resolver = "2"
        """

        if primaryContent.contains("[package]") || primaryContent.contains("[dependencies]") {
            // Remove old [workspace] block from primaryContent if it exists
            var cleanedContent = primaryContent
            if let wsRange = cleanedContent.range(of: "[workspace]") {
                let afterWs = String(cleanedContent[wsRange.upperBound...])
                if let nextSection = afterWs.range(of: "\n[") {
                    let toRemove = cleanedContent[wsRange.lowerBound..<nextSection.lowerBound]
                    cleanedContent.removeSubrange(wsRange.lowerBound..<nextSection.lowerBound)
                } else {
                    cleanedContent.removeSubrange(wsRange.lowerBound..<cleanedContent.endIndex)
                }
            }
            finalContent += "\n\n" + cleanedContent.trimmingCharacters(in: .whitespacesAndNewlines)
        }

        try? finalContent.write(to: workspaceToml, atomically: true, encoding: .utf8)
    }

    // MARK: - Cargo.toml Target Injection & Validation

    /// Validates and repairs Cargo.toml target declarations.
    ///
    /// **Case A — Dangling `[lib]`**: `[lib]` present but the referenced file doesn't exist
    ///   and no explicit `path =` given. Cargo fails: "can't find library ... specify lib.path".
    ///   Fix: strip the entire `[lib]` section.
    ///
    /// **Case B — No targets**: neither `[[bin]]` nor `[lib]` but `src/main.rs` exists.
    ///   Fix: inject `[[bin]]` pointing to src/main.rs.
    nonisolated private func injectCargoTargetIfNeeded(tomlURL: URL) {
        guard var content = try? String(contentsOf: tomlURL, encoding: .utf8) else { return }
        let tomlDir = tomlURL.deletingLastPathComponent()

        // ── Case A: Dangling [lib] ──────────────────────────────────────────────
        if content.contains("[lib]") {
            let libRsURL = tomlDir.appendingPathComponent("src/lib.rs")
            let hasLibRs = FileManager.default.fileExists(atPath: libRsURL.path)

            // Check whether [lib] already has an explicit path = so cargo can resolve it
            let hasExplicitLibPath: Bool = {
                guard let libRange = content.range(of: "[lib]") else { return false }
                let afterLib = String(content[libRange.upperBound...])
                let nextSection = afterLib.range(of: "\n[")?.lowerBound ?? afterLib.endIndex
                let libBlock = String(afterLib[..<nextSection])
                return libBlock.contains("path =") || libBlock.contains("path=")
            }()

            if !hasLibRs && !hasExplicitLibPath {
                // Remove the [lib] block (name, crate-type lines)
                var lines = content.components(separatedBy: "\n")
                var inLibSection = false
                lines = lines.filter { line in
                    let trimmed = line.trimmingCharacters(in: .whitespaces)
                    if trimmed == "[lib]" { inLibSection = true; return false }
                    if inLibSection {
                        if trimmed.hasPrefix("[") && trimmed != "[lib]" {
                            inLibSection = false
                            return true
                        }
                        return false
                    }
                    return true
                }
                content = lines.joined(separator: "\n")
                try? content.write(to: tomlURL, atomically: true, encoding: .utf8)
            }
        }

        // Re-read after possible edits above
        guard let updated = try? String(contentsOf: tomlURL, encoding: .utf8) else { return }
        content = updated

        // ── Case B: No targets at all ───────────────────────────────────────────
        // Virtual manifests (workspace only, no package) cannot have targets.
        guard content.contains("[package]") else { return }
        
        let hasTarget = content.contains("[[bin]]") ||
                        content.contains("[lib]") ||
                        content.contains("src/lib.rs") ||
                        content.contains("src/main.rs")
        guard !hasTarget else { return }

        let mainRsURL = tomlDir.appendingPathComponent("src/main.rs")
        guard FileManager.default.fileExists(atPath: mainRsURL.path) else { return }

        var binName = "app"
        if let nameRange = content.range(of: #"name\s*=\s*"([^"]+)""#, options: .regularExpression),
           let quotedName = content[nameRange].split(separator: "\"").dropFirst().first {
            binName = String(quotedName)
        }

        let injection = """

        [[bin]]
        name = "\(binName)"
        path = "src/main.rs"
        """
        try? (content + injection).write(to: tomlURL, atomically: true, encoding: .utf8)
    }

    // MARK: - Cargo.toml Hallucination Sanitizer

    /// Removes known-hallucinated or version-incompatible crate entries from Cargo.toml.
    /// LLMs consistently hallucinate crate names that don't exist on crates.io.
    /// Add entries to `hallucinatedCrates` whenever a new pattern causes a build failure.
    nonisolated func sanitizeCargoToml(tomlURL: URL) {
        guard var content = try? String(contentsOf: tomlURL, encoding: .utf8) else { return }

        // 許可リスト外のクレートを自動除去。モデルが幻覚しても安全。
        // chrono は std::time::SystemTime で代替可能なため除外。
        let hallucinatedCrates: [String] = [
            "bitnet",           // 存在しない
            "bitnet-rs",        // 存在しない
            "bitnet-core",      // 存在しない
            "ronin-core",       // 内部クレート
            "ronin-sandbox",    // 内部クレート
            "ronin-telemetry",  // 内部クレート
            "llama_cpp",        // 不安定・バージョン未固定
            "llama-cpp",        // 不安定
            "ort",              // onnxruntime バインディング (バージョン不安定)
            "chrono",           // 許可リスト外。std::time::SystemTime を使うこと
            "time",             // 許可リスト外。std::time を使うこと
            "uuid",             // 許可リスト外。String id を使うこと
        ]

        var lines = content.components(separatedBy: "\n")
        var modified = false

        lines = lines.map { line in
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            guard !trimmed.hasPrefix("#") else { return line }
            for crate in hallucinatedCrates {
                if trimmed.hasPrefix(crate + " ") || trimmed.hasPrefix(crate + "=") ||
                   trimmed.hasPrefix("\"" + crate + "\"") {
                    modified = true
                    return "# [SANITIZED - hallucinated crate '\(crate)'] " + line
                }
            }
            return line
        }

        if modified {
            content = lines.joined(separator: "\n")
            try? content.write(to: tomlURL, atomically: true, encoding: .utf8)
        }
    }

    // MARK: - Message Batching
    // appendMessage を直接 @Published に書かず、バッファに貯めてバッチフラッシュする。
    // これにより SwiftUI の再描画が1メッセージごとに発火せず、スクロール固まりを防ぐ。
    private var messageBatch: [ChatMessage] = []
    private var batchFlushTask: Task<Void, Never>? = nil

    private func appendMessage(_ message: OrchestratorMessage) {
        let chatMessage: ChatMessage
        switch message {
        case .user:
            // AppState.sendMessage がすでにユーザーメッセージを追加済み
            return
        case .commander(let text):
            chatMessage = ChatMessage(role: .assistant, content: "🛡️ Commander:\n" + text)
        case .system(let text):
            chatMessage = ChatMessage(role: .assistant, content: text)
        case .mcpToolCall(let tool, let result):
            chatMessage = ChatMessage(role: .assistant, content: "🔧 [\(tool)] → \(result.prefix(200))")
        case .assistant(let text):
            chatMessage = ChatMessage(role: .assistant, content: text)
        }

        messageBatch.append(chatMessage)

        // 既存フラッシュタスクがなければ 80ms 後にバッチフラッシュをスケジュール
        if batchFlushTask == nil {
            batchFlushTask = Task { @MainActor [weak self] in
                try? await Task.sleep(nanoseconds: 80_000_000) // 80ms
                self?.flushMessageBatch()
                self?.batchFlushTask = nil
            }
        }
    }

    /// バッファに貯まったメッセージを一括で AppState に追加する。
    /// 1回の @Published 更新にまとめることで SwiftUI の差分計算コストを最小化。
    @MainActor
    private func flushMessageBatch() {
        guard let appState = AppState.shared, !messageBatch.isEmpty else {
            messageBatch.removeAll()
            return
        }
        appState.messages.append(contentsOf: messageBatch)
        messageBatch.removeAll()
    }

    /// 処理完了時に残ったバッファを即時フラッシュする。
    @MainActor
    func flushRemainingMessages() {
        batchFlushTask?.cancel()
        batchFlushTask = nil
        flushMessageBatch()
    }

    // MARK: - Cross-Platform Detection

    /// ターゲットディレクトリがクロスプラットフォームビルド向けかを判定する。
    /// windows-target / linux-target / android-target 等はホスト環境でビルド不可なためスキップ。
    /// 特定のプロジェクト名ではなくパターンで判定するため、任意のクエリに対応できる。
    private func isCrossCompilationTarget(url: URL) -> Bool {
        let pathLower = url.path.lowercased()
        let crossPatterns = ["-windows", "-linux", "-android", "-wasm", "-arm", "-aarch", "windows-target", "linux-target"]
        // ホスト OS を確認
        #if os(macOS)
        if crossPatterns.contains(where: { pathLower.contains($0) }) { return true }
        #elseif os(Linux)
        if pathLower.contains("-windows") || pathLower.contains("-macos") || pathLower.contains("-darwin") { return true }
        #endif
        return false
    }

    private func runBuildCheck(workspaceURL: URL, fileURL: URL) async -> (Bool, String) {
        // スコープガード: workspaceURL 配下のファイルのみ
        guard fileURL.path.hasPrefix(workspaceURL.path) else {
            return (true, "")
        }
        guard let terminal = await MainActor.run(body: { AppState.shared?.terminal }) else {
            return (false, "Terminal unavailable")
        }

        let ext = fileURL.pathExtension.lowercased()
        let command: String
        var executionDir = workspaceURL

        switch ext {
        case "swift":
            if FileManager.default.fileExists(atPath: workspaceURL.appendingPathComponent("Package.swift").path) {
                command = "swift build"
            } else {
                command = "xcodebuild build -quiet"
            }
        case "rs":
            command = "cargo check"
            var current = fileURL.deletingLastPathComponent()
            while current.path != "/" && current.path.hasPrefix(workspaceURL.path) {
                if FileManager.default.fileExists(atPath: current.appendingPathComponent("Cargo.toml").path) {
                    executionDir = current
                    break
                }
                current = current.deletingLastPathComponent()
            }
        case "ts", "tsx":
            // Use npx tsc so it works even without a global tsc install.
            // If package.json not found within workspaceURL, skip gracefully.
            var foundPackageJson = false
            var current = fileURL.deletingLastPathComponent()
            while current.path != "/" && current.path.hasPrefix(workspaceURL.path) {
                if FileManager.default.fileExists(atPath: current.appendingPathComponent("package.json").path) {
                    executionDir = current
                    foundPackageJson = true
                    break
                }
                current = current.deletingLastPathComponent()
            }
            guard foundPackageJson else { return (true, "") }
            // Also require tsconfig.json; without it, tsc prints help text and exits 1
            let hasTsConfig = FileManager.default.fileExists(
                atPath: executionDir.appendingPathComponent("tsconfig.json").path)
            guard hasTsConfig else { return (true, "") }
            command = "npx --no-install tsc --noEmit 2>/dev/null || npx tsc --noEmit"
        default:
            return (true, "")
        }

        // Show terminal automatically
        await MainActor.run {
            AppState.shared?.showProcessLog = true
        }

        let result = await terminal.run(command, in: executionDir, initiatedByAI: true)
        
        if result.succeeded {
            return (true, result.stdout)
        } else {
            let errorMsg = result.stderr.isEmpty ? result.stdout : result.stderr
            return (false, errorMsg)
        }
    }

    // MARK: - Local Build Loop (人間モード専用・L1-L3記憶統合)
    //
    // ゲートキーパーモードの Worker ビルドループに相当する機能を
    // ローカル Ollama モデル（qwen3:27b 等）で実現する。
    //
    // ループフロー:
    //   1. モデルがコードを生成（ファイル書き込み指示を含む）
    //   2. 書き込み前に oldSource を保存 → 書き込み後に recordL15Diff (L1.5)
    //   3. cargo check / swift build / tsc を実行
    //   4. ❌ エラーが出たら:
    //      a. L2 OP.FACT としてエラーパターンをメモリに保存
    //      b. L3 生テキストとしてエラーログをメモリに保存
    //      c. エラー内容をプロンプトに注入してモデルに再生成を要求
    //      d. maxRetries 回まで繰り返す
    //   5. ✅ 成功したら L1.5 差分を確定保存してループ終了

    /// ローカルモードのビルド検証ループエントリーポイント。
    /// `handleLocalModeMessage()` から呼び出す。
    func runLocalBuildLoop(
        userMessage: String,
        workspaceURL: URL,
        maxRetries: Int = 5
    ) async {
        guard !isProcessing else { return }
        isProcessing = true
        defer { isProcessing = false }

        let isJp = AppLanguage.shared.isJapanese
        appendMessage(.user(userMessage))

        // ── Step 0: L1-L3 記憶からコンテキストを取得 ──────────────────────
        phase = .commanderPlanning(step: isJp ? "L1-L3 メモリ検索中..." : "Searching L1-L3 memory...")
        let memoryContext = buildMemoryContextForLocalMode(query: userMessage)
        appendMessage(.system(isJp
            ? "🧠 記憶システム: \(memoryContext.nodeCount) ノードを注入"
            : "🧠 Memory: injecting \(memoryContext.nodeCount) nodes"))

        // ── Step 1: 初回コード生成 ─────────────────────────────────────────
        let systemPrompt = buildLocalModeSystemPrompt(memoryContext: memoryContext)
        var currentInstruction = userMessage
        var retriesLeft = maxRetries
        var lastGeneratedCode = ""
        var succeededFiles: [(fileURL: URL, oldSource: String, newSource: String, relativePath: String)] = []

        while retriesLeft >= 0 {
            phase = .commanderPlanning(step: isJp
                ? "🤖 ローカルモデルで生成中 (残り\(retriesLeft)回)..."
                : "🤖 Generating with local model (\(retriesLeft) retries left)...")

            let rawResponse = await callOllama(
                model: state.commanderModel,
                prompt: currentInstruction,
                systemPrompt: systemPrompt
            )
            lastGeneratedCode = rawResponse
            appendMessage(.assistant(rawResponse))

            // ── Step 2: コードブロックを抽出してファイルに書き込む ──────────
            let filesToWrite = extractCodeBlocks(from: rawResponse, workspaceURL: workspaceURL)
            if filesToWrite.isEmpty {
                // コードブロックなし → 会話のみで終了
                appendMessage(.system(isJp ? "ℹ️ コード変更なし。ビルド検証をスキップ。" : "ℹ️ No code changes detected. Skipping build verification."))
                phase = .done
                try? await Task.sleep(nanoseconds: 500_000_000)
                phase = .idle
                return
            }

            succeededFiles.removeAll()
            var allErrors = ""
            var hasBuildError = false

            for (fileURL, newSource, relativePath) in filesToWrite {
                // oldSource を保存（L1.5用）
                let oldSource = (try? String(contentsOf: fileURL, encoding: .utf8)) ?? ""

                // Cargo.toml の場合は Gatekeeper と同じ sanitize/inject を適用
                let finalSource: String
                if fileURL.lastPathComponent == "Cargo.toml" {
                    let tempURL = fileURL
                    try? FileManager.default.createDirectory(at: tempURL.deletingLastPathComponent(), withIntermediateDirectories: true)
                    try? newSource.write(to: tempURL, atomically: true, encoding: .utf8)
                    sanitizeCargoToml(tomlURL: tempURL)
                    injectCargoTargetIfNeeded(tomlURL: tempURL)
                    let targetRoot = tempURL.deletingLastPathComponent()
                    ensureWorkspaceCargoToml(targetRoot: targetRoot, manifestURL: tempURL)
                    finalSource = (try? String(contentsOf: tempURL, encoding: .utf8)) ?? newSource
                } else {
                    try? FileManager.default.createDirectory(at: fileURL.deletingLastPathComponent(), withIntermediateDirectories: true)
                    try? newSource.write(to: fileURL, atomically: true, encoding: .utf8)
                    finalSource = newSource
                }

                // ── L1.5: 差分を記録 ────────────────────────────────────────
                vault.recordL15Diff(
                    relativePath: relativePath,
                    oldSource: oldSource,
                    newSource: finalSource,
                    context: "local-mode: \(userMessage.prefix(60))"
                )

                phase = .writingToDisk(file: relativePath)
                appendMessage(.system(isJp ? "💾 書き込み: \(relativePath)" : "💾 Written: \(relativePath)"))

                // ── Step 3: ビルド検証 ───────────────────────────────────────
                let (success, errorMsg) = await runBuildCheck(workspaceURL: workspaceURL, fileURL: fileURL)
                if success {
                    succeededFiles.append((fileURL, oldSource, finalSource, relativePath))
                } else {
                    hasBuildError = true
                    allErrors += "File: \(relativePath)\nError:\n\(errorMsg.prefix(800))\n\n"
                    appendMessage(.system(isJp
                        ? "❌ ビルドエラー: \(relativePath)\n\(errorMsg.prefix(300))"
                        : "❌ Build error: \(relativePath)\n\(errorMsg.prefix(300))"))
                }
            }

            if hasBuildError {
                // ── Step 4a: L2 OP.FACT にエラーパターンを保存 ────────────
                let errorSummary = allErrors.prefix(400)
                let memKey = "build_error_\(Int(Date().timeIntervalSince1970))"
                // L2 としてエラークラスを保存（非同期のため detach）
                let errForMemory = String(errorSummary)
                // NOTE: Task.detached を @MainActor クラスで使わない（[__NSDictionaryM objectForKey:] SIGTERM 回避）
                let fileCtx = allErrors.components(separatedBy: "\n").first ?? ""
                Task {
                    await self.saveLocalBuildErrorToMemory(
                        errorText: errForMemory,
                        fileContext: fileCtx,
                        key: memKey
                    )
                }

                // ── Step 4b: エラーを注入してリトライ ─────────────────────
                retriesLeft -= 1
                if retriesLeft < 0 {
                    appendMessage(.system(isJp
                        ? "⚠️ 自動修正の試行上限(\(maxRetries)回)に達しました。"
                        : "⚠️ Auto-fix retry limit (\(maxRetries)) reached."))
                    break
                }

                appendMessage(.system(isJp
                    ? "🔄 エラーを記憶に保存し、修正を要求します (残り\(retriesLeft)回)..."
                    : "🔄 Saved error to memory. Requesting fix (\(retriesLeft) retries left)..."))

                currentInstruction = """
                The code you just generated caused build errors. Fix them.

                Build errors:
                ```
                \(allErrors.prefix(1200))
                ```

                Rules:
                - Output ONLY the corrected code blocks in the same format as before.
                - Do NOT explain; just output corrected code.
                - CRITICAL: Do not use crates that don't exist on crates.io.
                Original request: \(userMessage)
                """
            } else {
                // ── Step 5: 成功 ─────────────────────────────────────────────
                appendMessage(.system(isJp
                    ? "✅ ビルド検証成功。L1.5差分を確定保存しました。"
                    : "✅ Build verification passed. L1.5 diff recorded."))

                // L3: 成功した変更のサマリーをメモリに保存
                // NOTE: Task.detached を @MainActor クラスで使わない（SIGTERM 回避）
                let filesSnap = succeededFiles.map { $0.relativePath }
                Task {
                    await self.saveLocalBuildSuccessToMemory(
                        files: filesSnap,
                        userMessage: userMessage
                    )
                }
                break
            }
        }

        phase = .done
        try? await Task.sleep(nanoseconds: 500_000_000)
        phase = .idle
    }

    // MARK: - Local Mode Helpers

    /// L1-L3 記憶からローカルモード用コンテキストを構築する。
    /// front/ の最新ノードの L1.5 インデックス行を注入する。
    private struct LocalMemoryContext {
        let nodeCount: Int
        let l15Lines: [String]    // L1.5 インデックス行（変更追跡）
        let recentFacts: [String] // L2 OP.FACT（エラーパターン等）
    }

    private func buildMemoryContextForLocalMode(query: String) -> LocalMemoryContext {
        // JCrossVault の VaultIndex から L1.5 エントリを収集
        guard let index = vault.vaultIndex else {
            return LocalMemoryContext(nodeCount: 0, l15Lines: [], recentFacts: [])
        }

        let l15Lines = index.entries.values
            .compactMap { $0.l15Index?.indexLine }
            .sorted()
            .prefix(15)
            .map { String($0) }

        return LocalMemoryContext(
            nodeCount: l15Lines.count,
            l15Lines: l15Lines,
            recentFacts: []
        )
    }

    /// ローカルモード用システムプロンプトを構築。L1.5 差分履歴を注入する。
    private func buildLocalModeSystemPrompt(memoryContext: LocalMemoryContext) -> String {
        let l15Section = memoryContext.l15Lines.isEmpty
            ? "(no previous code changes recorded)"
            : memoryContext.l15Lines.joined(separator: "\n")

        return """
        You are a local AI assistant running as part of the Verantyx IDE (Human Mode).
        You have access to the L1-L3 JCross memory system.

        ## L1.5 Code Change History (recent diffs from this workspace)
        \(l15Section)

        ## Rules
        - When generating code, output each file as a fenced code block with the file path as header comment.
        - Format: ```rust\\n// FILE: path/to/file.rs\\n<code>\\n```
        - Do NOT use non-existent crates (bitnet, ronin-*, ort@^2.0, etc.)
        - Use only stable crates: tauri@2, tokio, serde, candle-core, etc.
        - After writing code, expect build verification. If errors are fed back, fix them immediately.
        """
    }

    /// モデルの出力からコードブロックを抽出してファイルパスを解決する。
    private func extractCodeBlocks(
        from response: String,
        workspaceURL: URL
    ) -> [(fileURL: URL, source: String, relativePath: String)] {
        var results: [(URL, String, String)] = []

        // ```lang\n// FILE: path\ncode\n``` パターンを抽出
        let pattern = #"```[a-zA-Z]*\n(?://\s*FILE:\s*([^\n]+)\n)?([\s\S]*?)```"#
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return [] }

        let nsStr = response as NSString
        let matches = regex.matches(in: response, range: NSRange(location: 0, length: nsStr.length))

        for match in matches {
            let codeRange = match.range(at: 2)
            guard codeRange.location != NSNotFound else { continue }
            let code = nsStr.substring(with: codeRange).trimmingCharacters(in: .whitespacesAndNewlines)
            guard !code.isEmpty else { continue }

            // FILE: パスを取得（なければ先頭コメントから推測）
            var relativePath: String
            if match.range(at: 1).location != NSNotFound {
                relativePath = nsStr.substring(with: match.range(at: 1)).trimmingCharacters(in: .whitespaces)
            } else {
                // コード内の // FILE: 行を探す
                let firstLine = code.components(separatedBy: "\n").first ?? ""
                if firstLine.hasPrefix("// FILE:") || firstLine.hasPrefix("# FILE:") {
                    relativePath = firstLine
                        .replacingOccurrences(of: "// FILE:", with: "")
                        .replacingOccurrences(of: "# FILE:", with: "")
                        .trimmingCharacters(in: .whitespaces)
                } else {
                    continue // パス不明なブロックはスキップ
                }
            }

            let fileURL = workspaceURL.appendingPathComponent(relativePath)
            results.append((fileURL, code, relativePath))
        }

        return results
    }

    /// ローカルビルドエラーを L2+L3 記憶として MCP 経由で保存する。
    private func saveLocalBuildErrorToMemory(errorText: String, fileContext: String, key: String) async {
        // MCP の compile_trilayer_memory を直接呼ぶのではなく、
        // MCPサーバーが再起動後も読めるように JCrossVault の near/ に書き込む
        let errorNode = """
        ■ LOCAL_BUILD_ERROR_\(key)
        【空間座相】
        [誤:1.0][錆:0.9][捕:0.8]

        【L1.5索引】
        [誤錆捕] | "\(errorText.prefix(40))"

        【操作対応表】
        OP.FACT("build_error", "\(errorText.prefix(200).replacingOccurrences(of: "\"", with: "'"))")
        OP.FACT("file_context", "\(fileContext.prefix(100).replacingOccurrences(of: "\"", with: "'"))")
        OP.STATE("error_class", "local_mode_build_failure")

        【原文】
        \(errorText)
        """

        let errorDir = vault.workspaceURL.appendingPathComponent(".openclaw/local_build_errors")
        try? FileManager.default.createDirectory(at: errorDir, withIntermediateDirectories: true)
        let nodeURL = errorDir.appendingPathComponent("\(key).jcross")
        try? errorNode.write(to: nodeURL, atomically: true, encoding: .utf8)
    }

    /// ローカルビルド成功を L2+L3 記憶として保存する。
    private func saveLocalBuildSuccessToMemory(files: [String], userMessage: String) async {
        let successNode = """
        ■ LOCAL_BUILD_SUCCESS_\(Int(Date().timeIntervalSince1970))
        【空間座相】
        [成:1.0][恒:0.9][迅:0.8]

        【L1.5索引】
        [成恒迅] | "\(files.joined(separator: ", ").prefix(50))"

        【操作対応表】
        OP.FACT("succeeded_files", "\(files.joined(separator: ", ").prefix(200))")
        OP.FACT("task", "\(userMessage.prefix(100).replacingOccurrences(of: "\"", with: "'"))")
        OP.STATE("build_status", "LOCAL_MODE_SUCCEEDED")

        【原文】
        Task: \(userMessage)
        Files written and verified: \(files.joined(separator: "\n"))
        """

        let successDir = vault.workspaceURL.appendingPathComponent(".openclaw/local_build_success")
        try? FileManager.default.createDirectory(at: successDir, withIntermediateDirectories: true)
        let nodeURL = successDir.appendingPathComponent("success_\(Int(Date().timeIntervalSince1970)).jcross")
        try? successNode.write(to: nodeURL, atomically: true, encoding: .utf8)
    }
}

// MARK: - OrchestratorMessage

enum OrchestratorMessage: Identifiable {
    case user(String)
    case commander(String)
    case assistant(String)
    case system(String)
    case mcpToolCall(tool: String, result: String)
    var id: UUID { UUID() }
}
