import Foundation
import SwiftUI

// MARK: - TranspilationPipeline
//
// TODOファースト・5層記憶統合パイプライン（言語非依存）
//
// 対応変換例:
//   Swift → Rust/Python/TypeScript/Go/Kotlin/…
//   TypeScript → Python/Rust/…
//   など、LanguageDetector が LangPair を検出できれば全て対応
//
// フロー:
//   1. L2.5地図をBitNetが生成 (ワークスペース自動スキャン)
//   2. BitNetがTODOリストを生成し L2 記憶に保存
//   3. 各TODOを1件ずつ:
//      a. BitNetがメモリルーティング決定 (L1/L1.5/L2/L2.5)
//      b. モデルに「L2.5地図(Kanji topology) + 1ファイルのみ」を渡す
//         → 全フォルダは参照不可。常にBitNet地図のみが全体像
//      c. ビルド検証 → エラーはL2+L3に保存 → リトライ
//      d. 成功したらL1.5差分を記録

// MARK: - TranspilationTodo

struct TranspilationTodo: Codable, Identifiable {
    let id: UUID
    let relativePath: String
    let targetPath: String
    let l25Summary: String
    let priority: Int
    var status: Status
    var retryCount: Int
    var lastError: String?
    var completedAt: Date?

    enum Status: String, Codable {
        case pending, inProgress, succeeded, failed, skipped
    }

    init(relativePath: String, targetPath: String, l25Summary: String, priority: Int) {
        self.id = UUID()
        self.relativePath = relativePath
        self.targetPath = targetPath
        self.l25Summary = l25Summary
        self.priority = priority
        self.status = .pending
        self.retryCount = 0
    }
}

// MARK: - MemoryLayerRoute (BitNet が決定)

enum MemoryLayerRoute {
    case l1Only      // 2B以下: Kanji タグのみ
    case l1AndL2     // 7-8B: タグ + OP.FACT
    case l15AndL25   // デフォルト: 差分 + 構造地図
    case fullStack   // 27B+: L1〜L3 全層
}

// MARK: - TranspilationPipeline

@MainActor
final class TranspilationPipeline: ObservableObject {

    static let shared = TranspilationPipeline()

    @Published var todos: [TranspilationTodo] = []
    @Published var isRunning = false
    @Published var currentTodoIndex: Int = 0
    @Published var log: [String] = []

    /// SystemStatusProvider が参照する進捗テキスト
    var progressMessage: String {
        guard !todos.isEmpty else { return AppLanguage.shared.t("Idle", "待機中") }
        let done = todos.filter { $0.status == .succeeded }.count
        let current = todos.indices.contains(currentTodoIndex)
            ? URL(fileURLWithPath: todos[currentTodoIndex].relativePath).lastPathComponent
            : ""
        return AppLanguage.shared.t("\(done)/\(todos.count) Complete", "\(done)/\(todos.count) 完了") + (current.isEmpty ? "" : " → \(String(current.prefix(40)))")
    }

    private let l25Engine = L25IndexEngine.shared
    private var vault: JCrossVault { GatekeeperModeState.shared.vault }
    private let orchestrator = CommanderOrchestrator.shared
    private let hallucinationDetector = HallucinationDetector.shared
    // アクティブモデルのコンテキスト予算 (run() 開始時に確定)
    private var contextBudget: ContextBudget = ContextBudgetManager.budget(for: "qwen2.5:14b")

    private init() {}

    // MARK: - エントリポイント

    func run(task: String, workspaceURL: URL, maxRetries: Int = 3) async {
        guard !isRunning else { return }
        isRunning = true
        defer { isRunning = false }

        // アクティブモデルのコンテキスト予算を確定
        let modelId = GatekeeperModeState.shared.commanderModel
        contextBudget = ContextBudgetManager.budget(for: modelId)
        addLog("📐 Context Budget: \(ContextBudgetManager.describe(contextBudget))")

        // 言語ペアを自動検出 (Swift→Python, TS→Rust など何でも対応)
        let langPair = LanguageDetector.detect(from: task)
        let targetDir = langPair?.targetDirHint ?? "verantyx-target"

        addLog(AppLanguage.shared.t("🚀 Pipeline started: \(task.prefix(60))", "🚀 Pipeline 開始: \(task.prefix(60))"))
        if let lp = langPair {
            addLog(AppLanguage.shared.t("🔍 Language: \(lp.source) → \(lp.target) | Output: \(targetDir)/", "🔍 言語: \(lp.source) → \(lp.target) | 出力: \(targetDir)/"))
        } else {
            addLog(AppLanguage.shared.t("⚠️ Language pair not detected — Inferring from workspace primary language", "⚠️ 言語ペア未検出 — ワークスペースの主要言語から推定します"))
        }

        // Step 1: L2.5 地図 (既に生成済みなら再利用)
        if l25Engine.projectMap == nil {
            addLog(AppLanguage.shared.t("🗺️ Step 1: BitNet generating L2.5 source code map...", "🗺️ Step 1: L2.5 ソースコード地図を BitNet が生成中..."))
            await l25Engine.loadAndIncrementalUpdate(workspaceURL: workspaceURL)
        } else {
            addLog(AppLanguage.shared.t("🗺️ Step 1: Reusing L2.5 map (\(l25Engine.projectMap?.fileCount ?? 0) files)", "🗺️ Step 1: L2.5 地図を再利用 (\(l25Engine.projectMap?.fileCount ?? 0) ファイル)"))
        }
        let mapString = l25Engine.mapString(maxFiles: 40)

        // Step 2: BitNet が TODO リストを生成
        addLog(AppLanguage.shared.t("📋 Step 2: BitNet generating TODO list...", "📋 Step 2: BitNet が TODO リストを生成中..."))
        let generatedTodos = await generateTodoList(task: task, mapString: mapString, langPair: langPair)
        todos = generatedTodos

        // TODO を L2 記憶に保存
        await saveTodosToMemory(todos: generatedTodos, task: task, workspaceURL: workspaceURL)
        addLog(AppLanguage.shared.t("💾 Saved \(generatedTodos.count) TODOs to L2 memory", "💾 TODO \(generatedTodos.count) 件を L2 記憶に保存"))

        guard !generatedTodos.isEmpty else {
            addLog(AppLanguage.shared.t("⚠️ No TODOs generated. Please review your instructions.", "⚠️ TODO が生成されませんでした。指示を見直してください。"))
            return
        }

        // ユーザー要望により、裏側での順次処理を止め、生成したTODOをチャット欄に注入して処理を委譲する
        let lines = generatedTodos.enumerated()
            .map { "[\($0.0+1)] \($0.1.relativePath) → \($0.1.targetPath)" }
            .joined(separator: "\n")
            
        let promptToInject = """
        [システム: パイプラインがL2.5 TODOリストを生成しました。以下に従って順次作業してください]
        
        \(lines)
        
        対象タスク: \(task)
        """
        
        await MainActor.run {
            AppState.shared?.inputText = promptToInject
            AppState.shared?.sendMessage()
        }
        
        addLog(AppLanguage.shared.t("✅ TODOリストをチャット欄に注入しました。以後の作業はチャットで引き継がれます。", "✅ TODO list injected into chat. Work will continue there."))
        return
    }

    // MARK: - Step 2: TODO リスト生成 (BitNet Commander)

    private func generateTodoList(task: String, mapString: String, langPair: LangPair?) async -> [TranspilationTodo] {
        let srcExt  = langPair?.sourceExt  ?? ""
        let tgtExt  = langPair?.targetExt  ?? ""
        let tgtDir  = langPair?.targetDirHint ?? "verantyx-target"
        let srcLang = langPair?.source ?? "source"
        let tgtLang = langPair?.target ?? "target"

        // BitNet に渡すプロンプト
        // 重要: モデルはL2.5地図(Kanji topology)のみ参照。生ファイルは渡さない。
        let prompt = """
        ### Instruction:
        You are a task decomposer. Output a JSON array of files to convert.
        Task: \(task.prefix(200))
        Source language: \(srcLang) | Target language: \(tgtLang)

        L2.5 Project Map (Kanji topology — this is ALL you see, no raw source):
        \(mapString.prefix(1500))

        Output ONLY valid JSON:
        [{"relativePath":"src/file\(srcExt)","targetPath":"\(tgtDir)/src/file\(tgtExt)","priority":1,"reason":"why"}]
        ### Response:
        """

        if let resp = await BitNetCommanderEngine.shared.generate(prompt: prompt, systemPrompt: "") {
            let parsed = parseTodoJSON(resp, langPair: langPair)
            if !parsed.isEmpty { return parsed }
        }
        return buildRuleBasedTodos(langPair: langPair)
    }

    private func parseTodoJSON(_ json: String, langPair: LangPair?) -> [TranspilationTodo] {
        guard let s = json.firstIndex(of: "["), let e = json.lastIndex(of: "]") else {
            return buildRuleBasedTodos(langPair: langPair)
        }
        guard let data = String(json[s...e]).data(using: .utf8),
              let arr = try? JSONDecoder().decode([[String: String]].self, from: data) else {
            return buildRuleBasedTodos(langPair: langPair)
        }
        return arr.enumerated().compactMap { (i, dict) in
            guard let rel = dict["relativePath"], let tgt = dict["targetPath"] else { return nil }
            let summary = l25Engine.projectMap?.entries[rel]?.indexLine ?? rel
            return TranspilationTodo(relativePath: rel, targetPath: tgt, l25Summary: summary, priority: i)
        }
    }

    /// BitNet 未応答時のルールベースフォールバック (言語非依存)
    private func buildRuleBasedTodos(langPair: LangPair?) -> [TranspilationTodo] {
        guard let map = l25Engine.projectMap else { return [] }
        let srcLang = langPair?.source ?? guessMainLanguage(map: map)
        let srcExt  = langPair?.sourceExt ?? LanguageDetector.extMap[srcLang] ?? ".\(srcLang)"
        let tgtExt  = langPair?.targetExt ?? ".txt"
        let tgtDir  = langPair?.targetDirHint ?? "verantyx-target"

        return map.entries.values
            .filter { $0.language == srcLang || $0.relativePath.hasSuffix(srcExt) }
            .sorted { $0.complexityScore < $1.complexityScore }
            .enumerated().map { (i, entry) in
                let name = URL(fileURLWithPath: entry.relativePath).deletingPathExtension().lastPathComponent
                return TranspilationTodo(
                    relativePath: entry.relativePath,
                    targetPath: "\(tgtDir)/src/\(name)\(tgtExt)",
                    l25Summary: entry.indexLine,
                    priority: i
                )
            }
    }

    /// ワークスペースで最も多い言語を返す
    private func guessMainLanguage(map: L25ProjectMap) -> String {
        let freq = Dictionary(grouping: map.entries.values, by: \.language).mapValues { $0.count }
        return freq.max(by: { $0.value < $1.value })?.key ?? "swift"
    }

    // MARK: - Step 3: 1 ファイル処理

    private func processSingleTodo(
        index: Int, task: String, mapString: String,
        maxRetries: Int, workspaceURL: URL, langPair: LangPair?
    ) async {
        todos[index].status = .inProgress
        let todo = todos[index]

        let route = decideMemoryRoute()
        let memCtx = buildMemoryContext(route: route, query: todo.relativePath)

        // L3: 生ソース (このファイルのみ。他ファイルは見えない)
        let sourceURL = workspaceURL.appendingPathComponent(todo.relativePath)
        guard let source = try? String(contentsOf: sourceURL, encoding: .utf8) else {
            todos[index].status = .skipped
            addLog(AppLanguage.shared.t("⚠️ Source read failed: \(todo.relativePath)", "⚠️ ソース読み込み失敗: \(todo.relativePath)"))
            return
        }

        var retriesLeft = maxRetries
        while retriesLeft >= 0 {
            let prompt = buildTranspilationPrompt(
                task: task, todo: todo, source: source,
                mapString: mapString, memoryContext: memCtx, langPair: langPair,
                strategy: .standard, strategyHint: ""
            )
            addLog(AppLanguage.shared.t("  🤖 Sending to model (\(retriesLeft) retries left)...", "  🤖 モデルに送信中 (残り\(retriesLeft)回)..."))

            let response = await orchestrator.callLocalModel(
                prompt: prompt,
                systemPrompt: buildSystemPrompt(route: route, langPair: langPair)
            )

            let (success, errorMsg) = await writeAndVerify(
                response: response, todo: todo, workspaceURL: workspaceURL
            )

            if success {
                todos[index].status = .succeeded
                todos[index].completedAt = Date()
                if let newSrc = try? String(contentsOf: workspaceURL.appendingPathComponent(todo.targetPath), encoding: .utf8) {
                    vault.recordL15Diff(relativePath: todo.targetPath, oldSource: "", newSource: newSrc,
                                        context: "pipeline: \(task.prefix(50))")
                }
                
                // 即時に L2.5 を更新して次のプロンプトに反映させる
                await L25IndexEngine.shared.updateEntryInstantly(
                    for: workspaceURL.appendingPathComponent(todo.targetPath),
                    workspaceURL: workspaceURL,
                    patchContext: "Task: \(task.prefix(15))"
                )
                
                addLog(AppLanguage.shared.t("  ✅ Success: \(todo.targetPath)", "  ✅ 成功: \(todo.targetPath)"))
                return
            } else {
                // HallucinationDetector でエラー分析
                let analysis = await hallucinationDetector.analyze(
                    error: errorMsg, response: response,
                    retryCount: todos[index].retryCount, todo: todo
                )
                addLog("  🔍 Hallucination: \(analysis.reason) → \(analysis.strategy)")

                if analysis.strategy == .abort {
                    todos[index].status = .failed
                    addLog(AppLanguage.shared.t("  🛑 Abort: \(todo.relativePath) — Unrecoverable", "  🛑 Abort: \(todo.relativePath) — 回復不能"))
                    return
                }

                retriesLeft -= 1
                todos[index].retryCount += 1
                todos[index].lastError = errorMsg
                await saveErrorToMemory(todo: todo, error: errorMsg, workspaceURL: workspaceURL)

                // 次のリトライで戦略を反映させるためプロンプトを再構築
                let nextPrompt = buildTranspilationPrompt(
                    task: task, todo: todo, source: source,
                    mapString: mapString, memoryContext: memCtx, langPair: langPair,
                    strategy: analysis.strategy, strategyHint: analysis.injectedHint
                )
                // プロンプトを差し替えて再ループ (retriesLeft を消費済み)
                let retryResponse = await orchestrator.callLocalModel(
                    prompt: nextPrompt,
                    systemPrompt: buildSystemPrompt(route: route, langPair: langPair)
                )
                let (retrySuccess, retryErr) = await writeAndVerify(
                    response: retryResponse, todo: todo, workspaceURL: workspaceURL
                )
                if retrySuccess {
                    todos[index].status = .succeeded
                    todos[index].completedAt = Date()
                    addLog(AppLanguage.shared.t("  ✅ Success after strategy change: \(todo.targetPath)", "  ✅ 戦略変更後に成功: \(todo.targetPath)"))
                    return
                } else {
                    todos[index].lastError = retryErr
                    addLog(AppLanguage.shared.t("  ❌ Error persists after strategy change (\(retriesLeft) retries left)", "  ❌ 戦略変更後もエラー (残り\(retriesLeft)回)"))
                }
            }
        }
        todos[index].status = .failed
        addLog(AppLanguage.shared.t("  💀 Max retries reached: \(todo.relativePath)", "  💀 最大リトライ到達: \(todo.relativePath)"))
    }

    // MARK: - プロンプト構築 (言語非依存)

    private func buildTranspilationPrompt(
        task: String, todo: TranspilationTodo, source: String,
        mapString: String, memoryContext: String, langPair: LangPair?,
        strategy: PromptStrategy = .standard, strategyHint: String = ""
    ) -> String {
        let srcLang = langPair?.source ?? "source"
        let tgtLang = langPair?.target ?? "target"

        // コンテキスト予算に従って各セクションをトリム
        let trimmedMap = String(mapString.prefix(contextBudget.mapBudgetChars))
        let trimmedMem = String(memoryContext.prefix(contextBudget.memoryBudgetChars))
        // エラーパターンサマリーをメモリコンテキストに追加
        let errorPatterns = hallucinationDetector.buildErrorPatternSummary()

        // 戦略別にソース量・指示を調整
        let (trimmedSrc, taskNote): (String, String) = {
            switch strategy {
            case .minimalTask:
                // 最初の関数/クラスのみ
                let mini = source.components(separatedBy: "\n")
                    .prefix(50).joined(separator: "\n")
                return (mini, "Convert ONLY this partial code. Output a minimal stub if types are unknown.")
            case .compressed:
                let half = Int(Double(contextBudget.sourceBudgetChars) * 0.5)
                return (String(source.prefix(half)), "Keep output minimal. Core logic only.")
            default:
                return (String(source.prefix(contextBudget.sourceBudgetChars)), "")
            }
        }()

        let langNote: String = {
            if !strategyHint.isEmpty { return strategyHint }
            switch tgtLang {
            case "rust":
                return "Use tauri@2, tokio@1, serde@1 ONLY. No chrono, no uuid. Arc<RwLock<T>> for state."
            case "python":
                return "Python 3.11+. Dataclasses. Type hints. asyncio."
            case "typescript":
                return "TypeScript 5+. Strict mode. No any."
            case "go":
                return "Go 1.21+. Standard library only."
            case "kotlin":
                return "Kotlin 1.9+. Coroutines. Data classes."
            default:
                return "Follow idiomatic \(tgtLang) conventions."
            }
        }()

        return """
        Task: \(task.prefix(200))

        ## RULES
        - You see ONLY the L2.5 map and ONE file. No workspace browsing.
        - \(langNote)
        \(taskNote.isEmpty ? "" : "- " + taskNote)

        ## L2.5 Project Map (\(trimmedMap.count) chars)
        \(trimmedMap)

        ## Memory Context
        \(trimmedMem)
        \(errorPatterns.isEmpty ? "" : errorPatterns)

        ## File: \(srcLang) → \(tgtLang)
        Source: \(todo.relativePath) | Target: \(todo.targetPath)
        \(todo.l25Summary)

        ```\(srcLang)
        \(trimmedSrc)
        ```

        ## Output (ONLY a fenced code block)
        ```\(tgtLang)
        // FILE: \(todo.targetPath)
        <converted code>
        ```
        """
    }

    private func buildSystemPrompt(route: MemoryLayerRoute, langPair: LangPair?) -> String {
        let src = langPair?.source ?? "source"
        let tgt = langPair?.target ?? "target"
        switch route {
        case .l1Only:   return "You are a \(tgt) code generator. Output only code."
        case .l1AndL2, .l15AndL25:
            return "You are a \(src)-to-\(tgt) transpiler. Follow the file format exactly."
        case .fullStack:
            return "You are a Verantyx Cross-Language Transpiler. \(src)→\(tgt). Preserve all logic. Output only code."
        }
    }

    // MARK: - BitNet メモリルーティング

    private func decideMemoryRoute() -> MemoryLayerRoute {
        guard BitNetConfig.load()?.isValid == true else { return .l15AndL25 }
        let model = GatekeeperModeState.shared.commanderModel.lowercased()
        if model.contains("2b") || model.contains("1b") { return .l1Only }
        if model.contains("7b") || model.contains("8b") { return .l1AndL2 }
        if model.contains("27b") || model.contains("32b") { return .fullStack }
        return .l15AndL25
    }

    private func buildMemoryContext(route: MemoryLayerRoute, query: String) -> String {
        var ctx = ""
        if route != .l1Only, let index = vault.vaultIndex {
            let l15 = index.entries.values
                .compactMap { $0.l15Index?.indexLine }
                .prefix(8).joined(separator: "\n")
            if !l15.isEmpty { ctx += "[L1.5 Recent Diffs]\n\(l15)\n\n" }
        }
        if route == .l15AndL25 || route == .fullStack {
            let errDir = vault.workspaceURL.appendingPathComponent(".openclaw/local_build_errors")
            if let files = try? FileManager.default.contentsOfDirectory(at: errDir, includingPropertiesForKeys: nil) {
                let errs = files.sorted { $0.lastPathComponent > $1.lastPathComponent }
                    .prefix(2)
                    .compactMap { try? String(contentsOf: $0, encoding: .utf8) }
                    .map { String($0.prefix(150)) }
                    .joined(separator: "\n---\n")
                if !errs.isEmpty { ctx += "[L2 Known Errors]\n\(errs)\n" }
            }
        }
        return ctx.isEmpty ? "(no prior context)" : ctx
    }

    // MARK: - 書き込み・ビルド検証

    private func writeAndVerify(
        response: String, todo: TranspilationTodo, workspaceURL: URL
    ) async -> (Bool, String) {
        let targetRoot = workspaceURL.appendingPathComponent(
            URL(fileURLWithPath: todo.targetPath).pathComponents.first ?? "verantyx-target"
        )
        let fileURL = workspaceURL.appendingPathComponent(todo.targetPath)

        guard let code = extractFirstCodeBlock(from: response) else {
            return (false, "No code block found in response")
        }
        try? FileManager.default.createDirectory(
            at: fileURL.deletingLastPathComponent(), withIntermediateDirectories: true
        )
        if fileURL.lastPathComponent == "Cargo.toml" {
            try? code.write(to: fileURL, atomically: true, encoding: .utf8)
            orchestrator.sanitizeCargoToml(tomlURL: fileURL)
        } else {
            try? code.write(to: fileURL, atomically: true, encoding: .utf8)
        }

        // Rust のみ cargo check。他言語は書き込み成功で OK。
        let ext = fileURL.pathExtension
        if ext == "rs" || fileURL.lastPathComponent == "Cargo.toml" {
            return await orchestrator.runBuildCheckPublic(workspaceURL: targetRoot, fileURL: fileURL)
        }
        return (true, "")
    }

    private func extractFirstCodeBlock(from response: String) -> String? {
        let pattern = #"```[a-zA-Z]*\n([\s\S]*?)```"#
        guard let regex = try? NSRegularExpression(pattern: pattern),
              let match = regex.firstMatch(in: response, range: NSRange(response.startIndex..., in: response)),
              let range = Range(match.range(at: 1), in: response) else { return nil }
        return String(response[range]).trimmingCharacters(in: .whitespacesAndNewlines)
    }

    // MARK: - 記憶保存

    private func saveTodosToMemory(todos: [TranspilationTodo], task: String, workspaceURL: URL) async {
        let lines = todos.enumerated()
            .map { "[\($0.0+1)] \($0.1.relativePath) → \($0.1.targetPath)" }
            .joined(separator: "\n")
        let node = """
        ■ PIPELINE_TODO_\(Int(Date().timeIntervalSince1970))
        【空間座相】[令:1.0][変:0.9][廻:0.8]
        【L1.5索引】[令変廻] | "todo_list: \(todos.count)files"
        【操作対応表】
        OP.FACT("task", "\(task.prefix(100))")
        OP.FACT("todo_count", "\(todos.count)")
        OP.STATE("pipeline_status", "STARTED")
        【原文】Task: \(task)\nTODOs:\n\(lines)
        """
        let dir = workspaceURL.appendingPathComponent(".openclaw/pipeline_todos")
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        try? node.write(to: dir.appendingPathComponent("todo_\(Int(Date().timeIntervalSince1970)).jcross"),
                        atomically: true, encoding: .utf8)
    }

    private func saveErrorToMemory(todo: TranspilationTodo, error: String, workspaceURL: URL) async {
        let node = """
        ■ PIPELINE_ERROR_\(Int(Date().timeIntervalSince1970))
        【空間座相】[誤:1.0][変:0.9][捕:0.8]
        【L1.5索引】[誤変捕] | "\(todo.relativePath.prefix(30)): \(error.prefix(30))"
        【操作対応表】
        OP.FACT("failed_file", "\(todo.relativePath)")
        OP.FACT("error", "\(error.prefix(200).replacingOccurrences(of: "\"", with: "'"))")
        OP.FACT("retry_count", "\(todo.retryCount)")
        【原文】File: \(todo.relativePath)\nError: \(error.prefix(500))
        """
        let dir = workspaceURL.appendingPathComponent(".openclaw/local_build_errors")
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        try? node.write(to: dir.appendingPathComponent("err_\(Int(Date().timeIntervalSince1970)).jcross"),
                        atomically: true, encoding: .utf8)
    }

    private func savePipelineResultToMemory(task: String, succeeded: Int, failed: Int, workspaceURL: URL) async {
        let node = """
        ■ PIPELINE_RESULT_\(Int(Date().timeIntervalSince1970))
        【空間座相】[成:1.0][令:0.9][変:0.8]
        【L1.5索引】[成令変] | "succeeded:\(succeeded) failed:\(failed)"
        【操作対応表】
        OP.FACT("task", "\(task.prefix(100))")
        OP.FACT("succeeded", "\(succeeded)")
        OP.FACT("failed", "\(failed)")
        OP.STATE("pipeline_status", "COMPLETED")
        【原文】Task: \(task)\nResult: \(succeeded) succeeded, \(failed) failed
        """
        let dir = workspaceURL.appendingPathComponent(".openclaw/local_build_success")
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        try? node.write(to: dir.appendingPathComponent("result_\(Int(Date().timeIntervalSince1970)).jcross"),
                        atomically: true, encoding: .utf8)
    }

    private func addLog(_ msg: String) {
        log.append("[\(Date().formatted(.dateTime.hour().minute().second()))] \(msg)")
        if log.count > 300 { log.removeFirst(50) }
    }
}
