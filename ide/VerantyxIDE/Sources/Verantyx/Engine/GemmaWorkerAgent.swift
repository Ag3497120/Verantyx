import Foundation

// MARK: - GemmaWorkerAgent
//
// Gemma (27b等) が担う Worker の全責務を実装する。
//
// 責務:
//   1. BitNetから地図+索引+タスクを受け取りTODOを作成 → BitNetに送信
//   2. BitNetにファイルを要求 → 受け取る
//   3. ファイルを変換/編集 → BitNetに送信
//   4. ビルド結果を受け取り → L2.5を参照してシミュレーション → TODOを更新
//   5. 全TODO完了したら "Summary: ..." を作成 → BitNetに送信してループ終了
//
// 重要な制約:
//   - Gemmaが参照できるのは「L2.5地図(Kanji topology)」と「現在のファイル(L3)」のみ
//   - 全フォルダを参照することはできない
//   - BitNetが選んだ記憶層のみ追加参照可能

@MainActor
final class GemmaWorkerAgent {

    static let shared = GemmaWorkerAgent()

    private let orchestrator = CommanderOrchestrator.shared
    private let l25Engine = L25IndexEngine.shared
    private var currentL25Map = ""
    private var currentIndex = ""
    private var currentTask = ""
    private var todos: [AgentTodoItem] = []
    private var completedPaths: Set<String> = []

    // 追加記憶 (BitNetが注入)
    private var injectedMemory = ""

    private init() {}

    // MARK: - メインループ

    func run(mailbox: AgentMailbox, workspaceURL: URL) async {
        while !Task.isCancelled {
            try? await Task.sleep(nanoseconds: 300_000_000) // 300ms ポーリング

            guard let msg = await mailbox.receiveForGemma() else { continue }

            switch msg {

            // ── 準備完了。地図+索引+タスクを受信 → TODO作成 ──────────
            case .workspaceReady(let map, let index, let task):
                currentL25Map = map
                currentIndex = index
                currentTask = task
                completedPaths.removeAll()
                todos.removeAll()

                let items = await createTodoList(map: map, index: index, task: task)
                todos = items
                await mailbox.sendToBitNet(.todoListReady(items))

                // 最初のファイルを要求
                if let first = nextPendingTodo() {
                    await mailbox.sendToBitNet(.requestFile(
                        path: first.sourcePath ?? first.targetPath,
                        reason: first.description
                    ))
                    markInProgress(id: first.id)
                }

            // ── ファイルを受信 → 変換/編集 → 送信 ─────────────────────
            case .fileDelivery(let path, let content, let l25Summary, let memCtx):
                injectedMemory = memCtx
                guard let todo = currentTodo(for: path) else { continue }

                let (modifiedContent, newSummary) = await processFile(
                    todo: todo, source: content, l25Summary: l25Summary, memCtx: memCtx
                )

                let needsBuild = isBuildableTarget(path: todo.targetPath)
                await mailbox.sendToBitNet(.fileModified(
                    path: todo.targetPath,
                    content: modifiedContent,
                    l25Summary: newSummary,
                    isBuildRequired: needsBuild
                ))

            // ── ビルド結果受信 → シミュレーション → TODO更新 ──────────
            case .buildResult(let path, let success, let errors):
                if success {
                    markSucceeded(targetPath: path)
                    completedPaths.insert(path)
                } else {
                    // ビルドエラーをTODOに追加
                    let fixTodo = AgentTodoItem(
                        id: "fix_\(Int(Date().timeIntervalSince1970))",
                        action: .modifyFile,
                        targetPath: path,
                        sourcePath: nil,
                        description: "Fix build errors: \(errors.prefix(3).joined(separator: "; "))",
                        dependsOn: [],
                        status: .pending
                    )
                    todos.append(fixTodo)
                    await mailbox.sendToBitNet(.todoUpdate(todos))
                }

                // 次のファイルを要求、またはサマリー送信
                if let next = nextPendingTodo() {
                    await mailbox.sendToBitNet(.requestFile(
                        path: next.sourcePath ?? next.targetPath,
                        reason: next.description
                    ))
                    markInProgress(id: next.id)
                } else {
                    // 全TODO完了 → サマリー作成
                    let summary = await createSummary()
                    await mailbox.sendToBitNet(.summary(text: summary))
                    return
                }

            // ── BitNetが記憶を注入 ────────────────────────────────────
            case .memoryInjection(let layer, let content):
                injectedMemory = "[\(layer)] \(content)"

            default:
                break
            }
        }
    }

    // MARK: - TODOリスト作成 (Gemmaが計画)

    private func createTodoList(map: String, index: String, task: String) async -> [AgentTodoItem] {
        let budget = ContextBudgetManager.budget(for: GatekeeperModeState.shared.commanderModel)
        let langPair = LanguageDetector.detect(from: task)

        let prompt = """
        ## Your Role
        You are a task planner. Create a TODO list to complete the given task.
        You can ONLY see the L2.5 map and index below. You cannot browse files directly.

        ## Task
        \(task.prefix(300))

        ## L2.5 Project Map (Kanji topology — your ONLY view of the project)
        \(map.prefix(budget.mapBudgetChars))

        ## File Index
        \(index.prefix(500))

        ## Instructions
        - List files in dependency order (dependencies first)
        - For each file: specify action (createFile/modifyFile), source path, target path
        - Keep descriptions concise

        Output ONLY valid JSON:
        [{"id":"1","action":"createFile","targetPath":"out/main.\(langPair?.targetExt.dropFirst() ?? "rs")","sourcePath":"src/main.swift","description":"Convert main entry point","dependsOn":[],"status":"pending"}]
        """

        let response = await orchestrator.callLocalModel(
            prompt: prompt,
            systemPrompt: "You are a code task planner. Output only JSON."
        )
        let resp = response ?? ""
        if !resp.isEmpty, let parsed = parseTodoJSON(resp), !parsed.isEmpty {
            return parsed
        }
        return buildRuleBasedTodos(langPair: langPair)
    }

    // MARK: - ファイル変換/編集

    private func processFile(
        todo: AgentTodoItem, source: String, l25Summary: String, memCtx: String
    ) async -> (String, String) {
        let langPair = LanguageDetector.detect(from: currentTask)
        let srcLang = langPair?.source ?? URL(fileURLWithPath: todo.sourcePath ?? "").pathExtension
        let tgtLang = langPair?.target ?? URL(fileURLWithPath: todo.targetPath).pathExtension
        let budget = ContextBudgetManager.budget(for: GatekeeperModeState.shared.commanderModel)

        // チャンク分割が必要な場合
        if budget.chunkRequired && source.count > budget.sourceBudgetChars {
            return await processFileInChunks(
                todo: todo, source: source, srcLang: srcLang, tgtLang: tgtLang,
                l25Summary: l25Summary, memCtx: memCtx, budget: budget
            )
        }

        let prompt = buildConvertPrompt(
            todo: todo, source: source, srcLang: srcLang, tgtLang: tgtLang,
            l25Summary: l25Summary, memCtx: memCtx, budget: budget
        )

        let response = await orchestrator.callLocalModel(
            prompt: prompt,
            systemPrompt: "You are a \(srcLang)-to-\(tgtLang) code converter. Output only a fenced code block."
        ) ?? ""

        let code = extractCodeBlock(from: response) ?? response
        let newSummary = await generateL25Summary(path: todo.targetPath, content: code)
        return (code, newSummary)
    }

    private func processFileInChunks(
        todo: AgentTodoItem, source: String, srcLang: String, tgtLang: String,
        l25Summary: String, memCtx: String, budget: ContextBudget
    ) async -> (String, String) {
        let chunks = ContextBudgetManager.splitIntoChunks(source: source, chunkSizeChars: budget.chunkSizeChars)
        var combined = "// FILE: \(todo.targetPath)\n"

        for chunk in chunks {
            let chunkPrompt = """
            \(buildConvertPrompt(todo: todo, source: chunk.content, srcLang: srcLang, tgtLang: tgtLang,
                                 l25Summary: l25Summary, memCtx: memCtx, budget: budget))
            Note: This is chunk \(chunk.index + 1)/\(chunk.total). Continue the conversion from where the previous chunk ended.
            """
            let response = await orchestrator.callLocalModel(
                prompt: chunkPrompt,
                systemPrompt: "Output only code. No fences needed for intermediate chunks."
            ) ?? ""
            let code = extractCodeBlock(from: response) ?? response
            combined += code + "\n"
        }

        let newSummary = await generateL25Summary(path: todo.targetPath, content: combined)
        return (combined, newSummary)
    }

    // MARK: - プロンプト構築

    private func buildConvertPrompt(
        todo: AgentTodoItem, source: String, srcLang: String, tgtLang: String,
        l25Summary: String, memCtx: String, budget: ContextBudget
    ) -> String {
        """
        Task: \(currentTask.prefix(200))

        ## CONSTRAINT: You can ONLY see:
        1. The L2.5 Kanji topology map (project overview)
        2. This ONE file
        3. Memory context provided by BitNet Commander

        ## L2.5 Map
        \(currentL25Map.prefix(budget.mapBudgetChars))

        ## Memory Context (from BitNet)
        \(memCtx.prefix(budget.memoryBudgetChars))
        \(injectedMemory.prefix(200))

        ## File to Convert
        \(srcLang) → \(tgtLang)
        Source: \(todo.sourcePath ?? "new") → Target: \(todo.targetPath)
        Summary: \(l25Summary)

        ```\(srcLang)
        \(source.prefix(budget.sourceBudgetChars))
        ```

        After converting, also output a ONE-LINE L2.5 summary in this format:
        // L2.5: [漢字tag1:0.9][漢字tag2:0.8] description in 10 words max

        Output format:
        ```\(tgtLang)
        // FILE: \(todo.targetPath)
        // L2.5: <your summary here>
        <converted code>
        ```
        """
    }

    // MARK: - L2.5 要約を生成 (変換後にGemma自身が要約)

    private func generateL25Summary(path: String, content: String) async -> String {
        // コードのL2.5要約をL1漢字で生成
        let lang = URL(fileURLWithPath: path).pathExtension

        // コードブロックからL2.5コメントを抽出 (// L2.5: ...)
        let lines = content.components(separatedBy: "\n")
        if let l25Line = lines.first(where: { $0.contains("L2.5:") }) {
            let summary = l25Line.replacingOccurrences(of: "//", with: "").trimmingCharacters(in: .whitespaces)
            return summary
        }

        // フォールバック: ルールベース要約
        let topLines = lines.prefix(5).joined(separator: " ")
        return "[\(lang):0.9] \(topLines.prefix(60))"
    }

    // MARK: - サマリー作成 (タスク完了時)

    private func createSummary() async -> String {
        let succeeded = todos.filter { $0.status == .succeeded }.count
        let failed    = todos.filter { $0.status == .failed }.count

        let prompt = """
        Task completed. Create a brief summary.
        Task: \(currentTask.prefix(200))
        Files processed: \(todos.count) | Succeeded: \(succeeded) | Failed: \(failed)
        Completed files: \(Array(completedPaths.prefix(10)).joined(separator: ", "))

        Write a 3-5 sentence summary starting with "Summary:".
        """

        let response = await orchestrator.callLocalModel(
            prompt: prompt, systemPrompt: "You are a task summarizer."
        ) ?? "Summary: Task completed. \(succeeded)/\(todos.count) files processed."

        // "Summary:" で始まることを保証
        if response.lowercased().hasPrefix("summary") { return response }
        return "Summary: \(response)"
    }

    // MARK: - TODO ヘルパー

    private func nextPendingTodo() -> AgentTodoItem? {
        todos.first { todo in
            guard todo.status == .pending else { return false }
            return todo.dependsOn.allSatisfy { depId in
                let dep = todos.first { $0.id == depId }
                if let dep { return dep.status == .succeeded }
                return true  // 依存がなければOK
            }
        }
    }

    private func currentTodo(for sourcePath: String) -> AgentTodoItem? {
        todos.first { $0.sourcePath == sourcePath || $0.targetPath == sourcePath }
    }

    private func markInProgress(id: String) {
        if let i = todos.firstIndex(where: { $0.id == id }) {
            todos[i].status = .inProgress
        }
    }

    private func markSucceeded(targetPath: String) {
        if let i = todos.firstIndex(where: { $0.targetPath == targetPath }) {
            todos[i].status = .succeeded
        }
    }

    private func isBuildableTarget(path: String) -> Bool {
        let ext = URL(fileURLWithPath: path).pathExtension
        return ["rs", "toml"].contains(ext)  // Rust のみビルド検証。他は書き込みで完了。
    }

    // MARK: - JSON パース

    private func parseTodoJSON(_ json: String) -> [AgentTodoItem]? {
        guard let start = json.firstIndex(of: "["), let end = json.lastIndex(of: "]") else { return nil }
        let jsonStr = String(json[start...end])
        guard let data = jsonStr.data(using: .utf8) else { return nil }
        return try? JSONDecoder().decode([AgentTodoItem].self, from: data)
    }

    private func buildRuleBasedTodos(langPair: LangPair?) -> [AgentTodoItem] {
        guard let map = l25Engine.projectMap else { return [] }
        let srcLang = langPair?.source ?? "swift"
        let srcExt  = langPair?.sourceExt ?? ".swift"
        let tgtExt  = langPair?.targetExt ?? ".rs"
        let tgtDir  = langPair?.targetDirHint ?? "verantyx-target"

        return map.entries.values
            .filter { $0.language == srcLang || $0.relativePath.hasSuffix(srcExt) }
            .sorted { $0.complexityScore < $1.complexityScore }
            .enumerated().map { (i, entry) in
                let name = URL(fileURLWithPath: entry.relativePath).deletingPathExtension().lastPathComponent
                return AgentTodoItem(
                    id: "\(i)", action: .createFile,
                    targetPath: "\(tgtDir)/src/\(name)\(tgtExt)",
                    sourcePath: entry.relativePath,
                    description: entry.indexLine,
                    dependsOn: [],
                    status: .pending
                )
            }
    }

    // MARK: - コードブロック抽出

    private func extractCodeBlock(from text: String) -> String? {
        let pattern = #"```[a-zA-Z]*\n([\s\S]*?)```"#
        guard let regex = try? NSRegularExpression(pattern: pattern),
              let match = regex.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)),
              let range = Range(match.range(at: 1), in: text) else { return nil }
        return String(text[range]).trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
