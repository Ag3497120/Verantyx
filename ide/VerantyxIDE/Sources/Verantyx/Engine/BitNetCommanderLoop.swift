import Foundation
import SwiftUI

// MARK: - BitNetCommanderLoop
//
// BitNet が担う Commander の全責務を実装する。
//
// 責務:
//   1. ワークスペース検知 → 全ファイルをL1漢字トポロジーに変換 → L2.5索引地図を作成
//   2. L2.5地図+索引 → Gemmaに渡してTODOを待機
//   3. TODOを受け取り順番通りに実行:
//      a. Gemmaがrequestしたファイルを渡す
//      b. Gemmaからmodifiedファイルを受け取り → ビルド検証 → L2.5更新
//      c. エラーがあればGemmaに送信
//   4. 常に5層記憶から「今一番必要な記憶」を選んでGemmaに注入
//   5. Gemmaから "Summary:" を受信したらユーザーに表示してループ終了

@MainActor
final class BitNetCommanderLoop: ObservableObject {

    static let shared = BitNetCommanderLoop()

    // ── 状態 ──────────────────────────────────────────────────────

    @Published var isRunning = false
    @Published var phase: Phase = .idle
    @Published var todos: [AgentTodoItem] = []
    @Published var log: [String] = []
    @Published var currentFile: String = ""
    @Published var currentTask: String = ""   // SystemStatusProvider 向け

    /// SystemStatusProvider が参照するフェーズ名
    var currentPhase: String { phase.description }

    enum Phase {
        case idle
        case indexing
        case buildingMap
        case waitingTodo
        case executing
        case buildVerify
        case complete
        case error
        
        var description: String {
            switch self {
            case .idle: return AppLanguage.shared.t("Idle", "待機中")
            case .indexing: return AppLanguage.shared.t("Converting L1 Kanji", "L1漢字変換中")
            case .buildingMap: return AppLanguage.shared.t("Building L2.5 Map", "L2.5地図構築中")
            case .waitingTodo: return AppLanguage.shared.t("Waiting for TODOs", "TODO待機中 (Gemma計画中)")
            case .executing: return AppLanguage.shared.t("Executing", "実行中")
            case .buildVerify: return AppLanguage.shared.t("Verifying Build", "ビルド検証中")
            case .complete: return AppLanguage.shared.t("Complete", "完了")
            case .error: return AppLanguage.shared.t("Error", "エラー")
            }
        }
    }

    // ── 依存 ──────────────────────────────────────────────────────

    private let mailbox = AgentMailbox()
    private let l25Engine = L25IndexEngine.shared
    private let orchestrator = CommanderOrchestrator.shared
    private var vault: JCrossVault { GatekeeperModeState.shared.vault }

    private var workerTask: Task<Void, Never>?
    private var commanderTask: Task<Void, Never>?

    private init() {}

    // MARK: - エントリポイント

    func start(userTask: String, workspaceURL: URL) async {
        guard !isRunning else { return }
        isRunning = true
        log.removeAll()
        todos.removeAll()
        phase = .indexing
        await mailbox.clearAll()

        addLog(AppLanguage.shared.t("🚀 BitNet Commander started", "🚀 BitNet Commander 起動"))
        addLog(AppLanguage.shared.t("📋 Task: \(userTask.prefix(80))", "📋 タスク: \(userTask.prefix(80))"))

        // ── Phase 1: L1 Kanji 変換 → L2.5 地図構築 ──────────────────
        addLog(AppLanguage.shared.t("🔤 Phase 1: Converting all source files to L1 Kanji topology...", "🔤 Phase 1: 全ソースファイルを L1 漢字トポロジーに変換中..."))
        await buildL1KanjiIndex(workspaceURL: workspaceURL)
        phase = .buildingMap
        addLog(AppLanguage.shared.t("🗺️ Phase 2: Building L2.5 index map...", "🗺️ Phase 2: L2.5 索引地図を構築中..."))
        await l25Engine.loadAndIncrementalUpdate(workspaceURL: workspaceURL)

        let l25Map = l25Engine.mapString(maxFiles: 50)
        let index  = buildIndexString()
        addLog(AppLanguage.shared.t("✅ L2.5 map complete: \(l25Engine.projectMap?.fileCount ?? 0) files", "✅ L2.5 地図完成: \(l25Engine.projectMap?.fileCount ?? 0) ファイル"))

        // ── Phase 2: Gemma へ地図+索引を渡してTODOを待機 ─────────────
        phase = .waitingTodo
        await mailbox.sendToGemma(.workspaceReady(l25Map: l25Map, index: index, userTask: userTask))
        addLog(AppLanguage.shared.t("📤 Sending task and map to Gemma. Waiting for TODOs...", "📤 Gemma にタスクと地図を送信。TODO 待機中..."))

        // ── Gemma Worker を並列起動 ───────────────────────────────────
        let workerAgent = GemmaWorkerAgent.shared
        workerTask = Task {
            await workerAgent.run(mailbox: mailbox, workspaceURL: workspaceURL)
        }

        // ── Commander メインループ ────────────────────────────────────
        commanderTask = Task {
            await self.commanderLoop(workspaceURL: workspaceURL, userTask: userTask)
        }

        await commanderTask?.value
        workerTask?.cancel()
        isRunning = false
        addLog(AppLanguage.shared.t("🏁 Commander loop finished", "🏁 Commander ループ終了"))
    }

    // MARK: - Commander メインループ

    private func commanderLoop(workspaceURL: URL, userTask: String) async {
        while !Task.isCancelled {
            try? await Task.sleep(nanoseconds: 200_000_000) // 200ms ポーリング

            guard let msg = await mailbox.receiveForBitNet() else { continue }

            switch msg {

            // ── GemmaからTODOリストを受信 ──────────────────────────
            case .todoListReady(let items):
                todos = items
                phase = .executing
                addLog(AppLanguage.shared.t("📋 Received TODOs: \(items.count)", "📋 TODO受信: \(items.count)件"))
                for (i, item) in items.enumerated() {
                    addLog("  [\(i+1)] \(item.action.rawValue): \(item.targetPath)")
                }

            // ── Gemmaがファイルを要求 ──────────────────────────────
            case .requestFile(let path, let reason):
                currentFile = path
                addLog(AppLanguage.shared.t("📁 File requested: \(path) (\(reason.prefix(40)))", "📁 ファイル要求: \(path) (\(reason.prefix(40)))"))
                await deliverFile(path: path, workspaceURL: workspaceURL)

            // ── Gemmaがファイルを修正/新規作成 ────────────────────
            case .fileModified(let path, let content, let l25Summary, let isBuildRequired):
                addLog(AppLanguage.shared.t("📝 File received: \(path)", "📝 ファイル受信: \(path)"))
                // ファイルを書き込む
                let fileURL = workspaceURL.appendingPathComponent(path)
                try? FileManager.default.createDirectory(
                    at: fileURL.deletingLastPathComponent(), withIntermediateDirectories: true
                )
                try? content.write(to: fileURL, atomically: true, encoding: .utf8)

                // L2.5 要約を更新
                updateL25Summary(path: path, summary: l25Summary)
                addLog(AppLanguage.shared.t("  🗺️ L2.5 updated: \(path)", "  🗺️ L2.5 更新: \(path)"))

                // ビルド検証 (必要な場合)
                if isBuildRequired {
                    phase = .buildVerify
                    addLog(AppLanguage.shared.t("  🔨 Verifying build: \(path)", "  🔨 ビルド検証中: \(path)"))
                    let targetRoot = workspaceURL.appendingPathComponent(
                        path.components(separatedBy: "/").first ?? "."
                    )
                    let (success, errors) = await orchestrator.runBuildCheckPublic(
                        workspaceURL: targetRoot, fileURL: fileURL
                    )
                    let errList = success ? [] : errors.components(separatedBy: "\n").filter { !$0.isEmpty }
                    await mailbox.sendToGemma(.buildResult(path: path, success: success, errors: errList))
                    addLog(AppLanguage.shared.t("  \(success ? "✅" : "❌") Build result: \(success ? "Success" : "\(errList.count) errors")", "  \(success ? "✅" : "❌") ビルド結果: \(success ? "成功" : "\(errList.count)エラー")"))
                    phase = .executing

                    // L1.5 差分記録
                    if success {
                        vault.recordL15Diff(relativePath: path, oldSource: "", newSource: content,
                                            context: "commander: \(userTask.prefix(50))")
                    }
                }

                // 最も必要な記憶を注入
                let memory = selectBestMemory(for: path)
                if !memory.content.isEmpty {
                    await mailbox.sendToGemma(.memoryInjection(layer: memory.layer, content: memory.content))
                }

            // ── GemmaがTODOを更新 ─────────────────────────────────
            case .todoUpdate(let updated):
                todos = updated
                addLog(AppLanguage.shared.t("🔄 TODOs updated: \(updated.count) (Build error fixes, etc.)", "🔄 TODO更新: \(updated.count)件 (ビルドエラー対応等)"))

            // ── Gemmaからエラー報告 ────────────────────────────────
            case .errorReport(let path, let error, _):
                addLog(AppLanguage.shared.t("⚠️ Gemma error reported: \(path): \(error.prefix(60))", "⚠️ Gemmaエラー報告: \(path): \(error.prefix(60))"))
                await saveErrorToMemory(path: path, error: error, workspaceURL: workspaceURL)

            // ── タスク完了 (Gemmaからサマリー) ──────────────────────
            case .summary(let text):
                phase = .complete
                addLog(AppLanguage.shared.t("🎉 Task completed!", "🎉 タスク完了!"))
                addLog("─────────────────────────────")
                addLog(text)
                addLog("─────────────────────────────")

                // サマリーをL2記憶に保存
                await saveSummaryToMemory(text: text, workspaceURL: workspaceURL)

                // AppState のチャットにサマリーを表示
                if let appState = AppState.shared {
                    appState.messages.append(ChatMessage(role: .assistant, content: "✅ **タスク完了**\n\n\(text)"))
                    appState.isGenerating = false
                }
                return  // ループ終了

            default:
                break
            }
        }
    }

    // MARK: - Phase 1: L1 漢字トポロジー変換

    private func buildL1KanjiIndex(workspaceURL: URL) async {
        // L25IndexEngine がファイルスキャン+L1要約を行う
        // (既存実装を活用。L1要約はindexLine = 漢字タグ行)
        await l25Engine.loadAndIncrementalUpdate(workspaceURL: workspaceURL)
        let count = l25Engine.projectMap?.fileCount ?? 0
        addLog(AppLanguage.shared.t("  🔤 L1 conversion complete: \(count) files", "  🔤 L1 変換完了: \(count) ファイル"))
    }

    // MARK: - L2.5 索引文字列を生成

    private func buildIndexString() -> String {
        guard let map = l25Engine.projectMap else { return "(empty)" }
        let lines = map.entries.values
            .sorted { $0.complexityScore < $1.complexityScore }
            .prefix(100)
            .map { "[\($0.language)] \($0.relativePath): \($0.indexLine)" }
        return lines.joined(separator: "\n")
    }

    // MARK: - ファイルをGemmaに渡す

    private func deliverFile(path: String, workspaceURL: URL) async {
        let fileURL = workspaceURL.appendingPathComponent(path)
        let content = (try? String(contentsOf: fileURL, encoding: .utf8)) ?? ""
        let l25Summary = l25Engine.projectMap?.entries[path]?.indexLine ?? path

        // コンテキスト予算を適用
        let budget = ContextBudgetManager.budget(for: GatekeeperModeState.shared.commanderModel)
        let trimmedContent = String(content.prefix(budget.sourceBudgetChars))

        // 最適な記憶層を選択してまとめて送信
        let memory = selectBestMemory(for: path)

        await mailbox.sendToGemma(.fileDelivery(
            path: path,
            content: trimmedContent,
            l25Summary: l25Summary,
            memoryContext: memory.content
        ))
        addLog(AppLanguage.shared.t("  📤 File delivered: \(path) (\(trimmedContent.count)ch)", "  📤 ファイル配信: \(path) (\(trimmedContent.count)ch)"))
    }

    // MARK: - 5層記憶から「今最も必要な記憶」を選択 (BitNet Commander の核心)

    private struct MemorySelection { let layer: String; let content: String }

    private func selectBestMemory(for path: String) -> MemorySelection {
        let fileExt = URL(fileURLWithPath: path).pathExtension

        // L1.5: 最近の差分 (同一ファイルや同一言語の変更履歴)
        if let index = vault.vaultIndex {
            let related = index.entries.values
                .filter { $0.l15Index != nil && $0.relativePath.hasSuffix(fileExt) }
                .compactMap { $0.l15Index?.indexLine }
                .prefix(5)
                .joined(separator: "\n")
            if !related.isEmpty {
                return MemorySelection(layer: "L1.5", content: "[Recent Diffs - \(fileExt)]\n\(related)")
            }
        }

        // L2: 既知エラーパターン
        let errDir = vault.workspaceURL.appendingPathComponent(".openclaw/local_build_errors")
        if let files = try? FileManager.default.contentsOfDirectory(at: errDir, includingPropertiesForKeys: nil),
           !files.isEmpty {
            let errs = files.sorted { $0.lastPathComponent > $1.lastPathComponent }
                .prefix(3)
                .compactMap { try? String(contentsOf: $0, encoding: .utf8) }
                .map { String($0.prefix(200)) }
                .joined(separator: "\n---\n")
            return MemorySelection(layer: "L2", content: "[Known Build Errors]\n\(errs)")
        }

        // L1: 漢字タグのみ (軽量)
        if let map = l25Engine.projectMap,
           let entry = map.entries[path] {
            return MemorySelection(layer: "L1", content: "[L1 Topology]\n\(entry.indexLine)")
        }

        return MemorySelection(layer: "none", content: "")
    }

    // MARK: - L2.5 更新

    private func updateL25Summary(path: String, summary: String) {
        guard let map = l25Engine.projectMap else { return }
        let lang = URL(fileURLWithPath: path).pathExtension.lowercased()
        if let existing = map.entries[path] {
            let updated = L25SourceMapEntry(
                relativePath: existing.relativePath,
                language: existing.language,
                kanjiTopology: summary,
                structureTokens: existing.structureTokens,
                dependencies: existing.dependencies,
                lineCount: existing.lineCount,
                functionCount: existing.functionCount,
                complexityScore: existing.complexityScore
            )
            l25Engine.projectMap?.entries[path] = updated
        } else {
            let entry = L25SourceMapEntry(
                relativePath: path,
                language: lang,
                kanjiTopology: summary,
                structureTokens: [],
                dependencies: [],
                lineCount: 0,
                functionCount: 0,
                complexityScore: 1
            )
            l25Engine.projectMap?.entries[path] = entry
        }
    }

    // MARK: - 記憶保存

    private func saveErrorToMemory(path: String, error: String, workspaceURL: URL) async {
        let node = """
        ■ COMMANDER_ERROR_\(Int(Date().timeIntervalSince1970))
        【空間座相】[誤:1.0][変:0.9][捕:0.8]
        【操作対応表】
        OP.FACT("path", "\(path)")
        OP.FACT("error", "\(error.prefix(200).replacingOccurrences(of: "\"", with: "'"))")
        【原文】\(error.prefix(500))
        """
        let dir = workspaceURL.appendingPathComponent(".openclaw/local_build_errors")
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        try? node.write(to: dir.appendingPathComponent("err_\(Int(Date().timeIntervalSince1970)).jcross"),
                        atomically: true, encoding: .utf8)
    }

    private func saveSummaryToMemory(text: String, workspaceURL: URL) async {
        let node = """
        ■ TASK_SUMMARY_\(Int(Date().timeIntervalSince1970))
        【空間座相】[成:1.0][令:0.9][変:0.8]
        【操作対応表】
        OP.STATE("task_status", "COMPLETED")
        OP.FACT("summary_preview", "\(text.prefix(100))")
        【原文】\(text)
        """
        let dir = workspaceURL.appendingPathComponent(".openclaw/summaries")
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        try? node.write(to: dir.appendingPathComponent("summary_\(Int(Date().timeIntervalSince1970)).jcross"),
                        atomically: true, encoding: .utf8)
    }

    private func addLog(_ msg: String) {
        log.append("[\(Date().formatted(.dateTime.hour().minute().second()))] \(msg)")
        if log.count > 500 { log.removeFirst(50) }
    }
}
