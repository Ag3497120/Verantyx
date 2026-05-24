import Foundation

// MARK: - L2.5 Source Map Engine
//
// L2.5 は「ソースコード構造の簡易漢字トポロジー地図」である。
//
// ⚠️ L2.5 は Gatekeeper の「フル漢字 JCross IR」ではない。
//    L1 と同じ簡易形式 (1行) で表現する。
//
// 5層記憶の役割:
//
//   L1     — 会話・意思決定の漢字タグ: [迅:1.0][令:0.9]
//   L1.5   — コード差分フィンガープリント
//   L2     — OP.FACT / OP.STATE 操作命令
//   L2.5   — ソースコード構造の簡易漢字トポロジー地図 ← (本ファイル)
//            形式: [漢:1.0][漢:0.9] ClassName FuncName... (1行・コンパクト)
//            ※ Gatekeeper JCross IR (多行・OP.FACT多数) とは別物
//            ※ 要約担当は BitNet。ルールベースはフォールバックのみ。
//   L3     — 生ソースコード原文
//
// Gemma/qwen は L2.5 地図のみ参照。生ファイルツリーは参照不可。
// BitNet Commander が地図を生成・管理・更新する。

// MARK: - L2.5 エントリ (1ファイル1レコード)

struct L25SourceMapEntry: Codable, Identifiable {
    let id: UUID
    /// 元ファイルの相対パス
    let relativePath: String
    /// 言語 (swift / rs / ts / py など)
    let language: String
    /// 漢字トポロジー要約 (例: "[迅並路] Commander: build_loop jcross_vault")
    let kanjiTopology: String
    /// 抽出したクラス・関数・構造体名 (最大10件)
    let structureTokens: [String]
    /// importしているモジュール
    let dependencies: [String]
    /// ファイルの行数
    let lineCount: Int
    /// 関数数（目安）
    let functionCount: Int
    /// 複雑度スコア (1-5)
    let complexityScore: Int
    /// memory_map形式の1行インデックス
    let indexLine: String
    /// 生成日時
    let generatedAt: Date

    init(
        id: UUID = UUID(),
        relativePath: String,
        language: String,
        kanjiTopology: String,
        structureTokens: [String],
        dependencies: [String],
        lineCount: Int,
        functionCount: Int,
        complexityScore: Int,
        generatedAt: Date = Date(),
        indexLine: String? = nil
    ) {
        self.id = id
        self.relativePath = relativePath
        self.language = language
        self.kanjiTopology = kanjiTopology
        self.structureTokens = structureTokens
        self.dependencies = dependencies
        self.lineCount = lineCount
        self.functionCount = functionCount
        self.complexityScore = complexityScore
        self.generatedAt = generatedAt

        if let idx = indexLine {
            self.indexLine = idx
        } else {
            // memory_map で表示される1行形式
            let tokens = structureTokens.prefix(3).joined(separator: "+")
            let shortPath = URL(fileURLWithPath: relativePath)
                .lastPathComponent
            self.indexLine = "\(kanjiTopology.prefix(20)) | \"\(shortPath): \(tokens)\" L\(lineCount)F\(functionCount)"
        }
    }
}

// MARK: - L2.5 プロジェクト全体地図

struct L25ProjectMap: Codable {
    var entries: [String: L25SourceMapEntry]
    let workspaceRoot: String
    var generatedAt: Date          // var: 差分更新時に書き換える
    var fileCount: Int { entries.count }
    var globalTopology: String     // var: 差分更新後に再合成する

    /// memory_map形式のコンパクト一覧 (LLMに渡す地図本文)
    func toMapString(maxFiles: Int = 50) -> String {
        let sorted = entries.values
            .sorted { $0.complexityScore > $1.complexityScore }
            .prefix(maxFiles)

        var lines = ["[L2.5 PROJECT MAP — \(fileCount) files — \(workspaceRoot)]", ""]
        for entry in sorted {
            lines.append("  \(entry.indexLine)")
        }
        lines.append("")
        lines.append("[Global Topology]: \(globalTopology)")
        return lines.joined(separator: "\n")
    }

    /// 特定ファイルのL2.5エントリを取得 (部分一致)
    func findEntry(matching name: String) -> L25SourceMapEntry? {
        let lower = name.lowercased()
        return entries.values.first {
            $0.relativePath.lowercased().contains(lower) ||
            URL(fileURLWithPath: $0.relativePath).lastPathComponent.lowercased().contains(lower)
        }
    }

    // MARK: - JCross Format Serialization
    
    func toJCrossString() -> String {
        var lines: [String] = []
        lines.append(";;; L2.5 PROJECT MAP")
        lines.append(";;; GENERATED_AT: \(generatedAt.timeIntervalSince1970)")
        lines.append(";;; WORKSPACE: \(workspaceRoot)")
        lines.append(";;; GLOBAL: \(globalTopology)")
        lines.append("")
        
        for (path, entry) in entries {
            lines.append("■ NODE L25 \(path)")
            lines.append("LANG: \(entry.language)")
            lines.append("KANJI: \(entry.kanjiTopology)")
            lines.append("TOKENS: \(entry.structureTokens.joined(separator: ","))")
            lines.append("DEPS: \(entry.dependencies.joined(separator: ","))")
            lines.append("METRICS: L\(entry.lineCount) F\(entry.functionCount) C\(entry.complexityScore)")
            lines.append("DATE: \(entry.generatedAt.timeIntervalSince1970)")
            lines.append("INDEX: \(entry.indexLine)")
            lines.append("")
        }
        return lines.joined(separator: "\n")
    }
    
    static func fromJCrossString(_ text: String) -> L25ProjectMap? {
        let lines = text.components(separatedBy: "\n")
        var entries: [String: L25SourceMapEntry] = [:]
        var workspaceRoot = ""
        var generatedAt = Date()
        var globalTopology = ""
        
        var currentPath = ""
        var currentEntry: [String: String] = [:]
        
        func finishEntry() {
            guard !currentPath.isEmpty else { return }
            let lang = currentEntry["LANG"] ?? "text"
            let kanji = currentEntry["KANJI"] ?? ""
            let tokens = (currentEntry["TOKENS"] ?? "").components(separatedBy: ",").filter { !$0.isEmpty }
            let deps = (currentEntry["DEPS"] ?? "").components(separatedBy: ",").filter { !$0.isEmpty }
            let index = currentEntry["INDEX"]
            let dateVal = Double(currentEntry["DATE"] ?? "") ?? Date().timeIntervalSince1970
            
            var l = 0, f = 0, c = 1
            if let metrics = currentEntry["METRICS"] {
                let parts = metrics.components(separatedBy: " ")
                for p in parts {
                    if p.hasPrefix("L") { l = Int(p.dropFirst()) ?? 0 }
                    if p.hasPrefix("F") { f = Int(p.dropFirst()) ?? 0 }
                    if p.hasPrefix("C") { c = Int(p.dropFirst()) ?? 1 }
                }
            }
            
            let entry = L25SourceMapEntry(
                relativePath: currentPath,
                language: lang,
                kanjiTopology: kanji,
                structureTokens: tokens,
                dependencies: deps,
                lineCount: l,
                functionCount: f,
                complexityScore: c,
                generatedAt: Date(timeIntervalSince1970: dateVal),
                indexLine: index
            )
            entries[currentPath] = entry
            currentPath = ""
            currentEntry = [:]
        }
        
        for line in lines {
            let t = line.trimmingCharacters(in: .whitespaces)
            if t.hasPrefix(";;; GENERATED_AT: ") {
                let ts = Double(t.dropFirst(18)) ?? 0
                generatedAt = Date(timeIntervalSince1970: ts)
            } else if t.hasPrefix(";;; WORKSPACE: ") {
                workspaceRoot = String(t.dropFirst(15))
            } else if t.hasPrefix(";;; GLOBAL: ") {
                globalTopology = String(t.dropFirst(12))
            } else if t.hasPrefix("■ NODE L25 ") {
                finishEntry()
                currentPath = String(t.dropFirst(11))
            } else if t.contains(": ") && !currentPath.isEmpty {
                let parts = t.components(separatedBy: ": ")
                if parts.count >= 2 {
                    let key = parts[0]
                    let val = parts.dropFirst().joined(separator: ": ")
                    currentEntry[key] = val
                }
            }
        }
        finishEntry()
        
        return L25ProjectMap(entries: entries, workspaceRoot: workspaceRoot, generatedAt: generatedAt, globalTopology: globalTopology)
    }
}

// MARK: - L2.5 Index Engine

/// BitNetを使ってソースコード全体をL1レベルの漢字トポロジーに分解し、
/// プロジェクト地図 (L2.5) を生成するエンジン。
///
/// - ワークスペースにフォルダが追加されると自動的に全ファイルをスキャンする
/// - 各ファイルをルールベース(CPU)で漢字トポロジーに変換する
/// - 結果を .openclaw/l25_map.json に永続保存する
/// - qwen等の大型LLMには地図のみを渡し、生ソースは渡さない
@MainActor
final class L25IndexEngine: ObservableObject {

    static let shared = L25IndexEngine()

    @Published var projectMap: L25ProjectMap?
    @Published var isIndexing = false
    @Published var indexingProgress: Double = 0
    @Published var currentFile: String = ""   // 現在変換中のファイル名
    @Published var log: [String] = []
    var bitnetMissingAction: (() -> Void)?
    private var hasWarnedBitNetMissing = false

    // MARK: - キャンセル制御
    /// インデックスタスクを保持。キャンセル時に cancel() を呼ぶ。
    private var indexingTask: Task<Void, Never>?
    /// 最後にインデックスしたワークスペースURL（再開UI用）
    @Published var lastWorkspaceURL: URL?
    /// ユーザーが明示的に停止したことを示すフラグ（UIの「停止済み」表示用）
    @Published var isStopped = false

    /// 中断されたマップが存在するか（= 「再開」ボタンの表示判定用）
    var hasPausedMap: Bool {
        guard let ws = lastWorkspaceURL, !isIndexing else { return false }
        return projectMap != nil || (try? mapFileURL(workspaceURL: ws).checkResourceIsReachable()) == true
    }

    private init() {}

    // MARK: - 公開API

    // インデックスモードをUIに公開
    enum IndexingMode: Equatable { case none, full, incremental }
    @Published var indexingMode: IndexingMode = .none

    /// 現在実行中の L2.5 変換をキャンセルする。
    /// Task.detached で動いているので cancel() が即座に届く。
    func cancelIndexing() {
        guard isIndexing else { return }
        indexingTask?.cancel()
        isStopped = true   // ← UIに停止済みを即座展洸
        addLog(AppLanguage.shared.t("⏹️ L2.5 conversion stopped (converted files are kept)", "⏹️ L2.5 変換を停止しました（変換済み分は保持されます）"))
    }

    /// 前回キャンセルした場所から再開する。
    func resumeIndexing() {
        guard let ws = lastWorkspaceURL, !isIndexing else { return }
        isStopped = false
        Task { await buildProjectMap(workspaceURL: ws) }
    }

    /// ワークスペース全体をスキャンしてL2.5地図を生成する。
    /// BitNetが使えない場合はルールベースで処理する (常にフォールバック)。
    /// 既存地図をディスクから読み込む (進捗表示なし・高速)。
    func loadMap(workspaceURL: URL) {
        // ✅ nonisolated ヘルパーでディスクI/Oを実行、完了後に MainActor で @Published を書き込む
        // Task.detached + [weak self] は @MainActor クラスでは SIGTERM の原因になる。
        let mapURL = mapFileURL(workspaceURL: workspaceURL)
        Task {
            guard let map = await Self.loadMapFromDisk(mapURL: mapURL) else { return }
            self.projectMap = map
            self.addLog(AppLanguage.shared.t("📂 Loaded L2.5 cache: \(map.fileCount) files", "📂 L2.5 キャッシュ読み込み: \(map.fileCount) ファイル"))
        }
    }

    /// 純粋なディスクI/Oのみ — nonisolated なのでバックグラウンドスレッドで安全に呼び出せる
    nonisolated private static func loadMapFromDisk(mapURL: URL) async -> L25ProjectMap? {
        await Task.detached(priority: .utility) {
            guard let text = try? String(contentsOf: mapURL, encoding: .utf8) else { return nil }
            return L25ProjectMap.fromJCrossString(text)
        }.value
    }


    /// LLMに渡すコンパクトな地図文字列を返す。
    func mapString(maxFiles: Int = 40) -> String {
        projectMap?.toMapString(maxFiles: maxFiles) ?? "(L2.5 地図未生成)"
    }

    func buildProjectMap(workspaceURL: URL) async {
        guard !isIndexing else { return }
        lastWorkspaceURL = workspaceURL
        isStopped = false   // 再開/開始時にリセット
        isIndexing = true
        indexingMode = .full
        indexingProgress = 0

        // ✅ Task.detached で MainActorを完全に切り離す。
        // これにより cancelIndexing() がメインスレッドから即座に呼び出せる。
        let task: Task<Void, Never> = Task.detached(priority: .utility) { [weak self] in
            await self?.runIndexingLoop(workspaceURL: workspaceURL)
        }
        indexingTask = task
        await task.value  // 完了 or キャンセルまで待機

        // キャンセルされた場合は isStopped はリセットしない（UIにそのまま表示）
        isIndexing = false
        indexingMode = .none
        currentFile = ""
        indexingTask = nil
    }

    /// 実際のインデックスループ。Task.detached から呼ばれるため nonisolated。
    /// @Published プロパティへの書き込みは全て MainActor.run 経由。
    nonisolated private func runIndexingLoop(workspaceURL: URL) async {
        await Task.yield()
        await Task.yield()

        await MainActor.run { self.addLog(AppLanguage.shared.t("🗺️ Started L2.5 map generation: \(workspaceURL.lastPathComponent)", "🗺️ L2.5 地図生成開始: \(workspaceURL.lastPathComponent)")) }

        let files = collectTargetFiles(workspaceURL: workspaceURL)
        await MainActor.run { self.addLog(AppLanguage.shared.t("📁 Target: \(files.count) files", "📁 対象: \(files.count) ファイル")) }

        // キャッシュが存在すれば読み込んで続きから（レジューム対策）
        let mapURL = await MainActor.run { self.mapFileURL(workspaceURL: workspaceURL) }
        if let map = await Self.loadMapFromDisk(mapURL: mapURL) {
            await MainActor.run {
                self.projectMap = map
                self.addLog(AppLanguage.shared.t("📂 Loaded L2.5 cache: \(map.fileCount) files", "📂 L2.5 キャッシュ読み込み: \(map.fileCount) ファイル"))
            }
        } else {
            await MainActor.run { self.projectMap = nil }
        }
        var entries: [String: L25SourceMapEntry] = await MainActor.run { self.projectMap?.entries ?? [:] }
        let total = max(files.count, 1)

        for (i, fileURL) in files.enumerated() {
            // ✅ Task.detached で動いているためこのチェックが即座に届く
            if Task.isCancelled {
                await MainActor.run {
                    self.addLog(AppLanguage.shared.t("⏹️ Cancelled: \(i)/\(total) files complete — saved intermediate", "⏹️ キャンセル: \(i)/\(total) ファイル完了 — 中間保存"))
                    self.currentFile = ""
                }
                let partialMap = L25ProjectMap(
                    entries: entries,
                    workspaceRoot: workspaceURL.path,
                    generatedAt: Date(),
                    globalTopology: synthesizeGlobalTopology(from: Array(entries.values))
                )
                await MainActor.run { self.projectMap = partialMap }
                saveMap(partialMap, workspaceURL: workspaceURL)
                return
            }

            await Task.yield()

            // ✅ Throttle MainActor UI updates to prevent UI freezing (beachball)
            if i % 10 == 0 || i == total - 1 {
                await MainActor.run {
                    self.indexingProgress = Double(i) / Double(total)
                    self.currentFile = fileURL.lastPathComponent
                }
            }
            let relativePath = String(fileURL.path.dropFirst(workspaceURL.path.count + 1))

            // 既にエントリがあり変更されていない場合はスキップ（レジューム機能）
            if let existing = entries[relativePath] {
                let attrs = try? FileManager.default.attributesOfItem(atPath: fileURL.path)
                let modDate = (attrs?[.modificationDate] as? Date) ?? .distantPast
                if modDate <= existing.generatedAt { continue }
            }

            guard let source = try? String(contentsOf: fileURL, encoding: .utf8) else { continue }

            let entry = await generateL25Entry(
                source: source,
                relativePath: relativePath,
                language: fileURL.pathExtension.lowercased()
            )
            if let entry {
                entries[relativePath] = entry
                if entries.count % 5 == 0 {
                    let tempMap = L25ProjectMap(
                        entries: entries,
                        workspaceRoot: workspaceURL.path,
                        generatedAt: Date(),
                        globalTopology: synthesizeGlobalTopology(from: Array(entries.values))
                    )
                    saveMap(tempMap, workspaceURL: workspaceURL)
                }
            }
        }

        let globalTopology = synthesizeGlobalTopology(from: Array(entries.values))
        let map = L25ProjectMap(
            entries: entries,
            workspaceRoot: workspaceURL.path,
            generatedAt: Date(),
            globalTopology: globalTopology
        )
        saveMap(map, workspaceURL: workspaceURL)
        await MainActor.run {
            self.projectMap = map
            self.indexingProgress = 1.0
            self.currentFile = ""
            self.addLog(AppLanguage.shared.t("✅ L2.5 map complete: \(entries.count) entries / Global: \(globalTopology)", "✅ L2.5 地図完成: \(entries.count) エントリ / Global: \(globalTopology)"))
        }
    }


    /// キャッシュ読み込み → 変更ファイルのみ差分再インデックスする。
    ///
    /// 動作:
    ///   1. ディスクのキャッシュを読み込む (高速)
    ///   2. 前回の `generatedAt` より新しいファイルを検出
    ///   3. 変更・新規ファイルのみ BitNet で再インデックス
    ///   4. 削除されたファイルをエントリから除去
    func loadAndIncrementalUpdate(workspaceURL: URL) async {
        let task: Task<Void, Never> = Task.detached(priority: .utility) { [weak self] in
            await self?.runLoadAndIncrementalUpdate(workspaceURL: workspaceURL)
        }
        indexingTask = task
        await task.value
        indexingTask = nil
    }

    nonisolated private func runLoadAndIncrementalUpdate(workspaceURL: URL) async {
        // ── Step 1: キャッシュロード ──────────────────────────────────
        let mapURL = await MainActor.run { self.mapFileURL(workspaceURL: workspaceURL) }
        let loadedMap = await Self.loadMapFromDisk(mapURL: mapURL)

        if let loadedMap = loadedMap {
            await MainActor.run {
                self.projectMap = loadedMap
                self.addLog(AppLanguage.shared.t("📂 Loaded L2.5 cache: \(loadedMap.fileCount) files", "📂 L2.5 キャッシュ読み込み: \(loadedMap.fileCount) ファイル"))
            }
        } else {
            await MainActor.run { self.projectMap = nil }
        }

        let isIdx = await MainActor.run { self.isIndexing }
        guard !isIdx else { return }

        // キャッシュなし → フルビルドにフォールスルー
        let currentMapOpt: L25ProjectMap? = await MainActor.run { self.projectMap }
        guard let currentMap = currentMapOpt else {
            await MainActor.run { self.addLog(AppLanguage.shared.t("🆕 No L2.5 cache → starting full generation", "🆕 L2.5 キャッシュなし → フル生成開始")) }
            await self.buildProjectMap(workspaceURL: workspaceURL)
            return
        }

        let lastGenerated = currentMap.generatedAt

        // ── Step 2: 変更・新規ファイルを検出 ─────────────────────────
        // ✅ static nonisolated ヘルパーに純粋I/O処理を委譲— self をキャプチャしない
        let changedFilesAndRemovedKeys = await Self.detectChangedFiles(
            allFiles: Self.collectFiles(workspaceURL: workspaceURL),
            currentMap: currentMap,
            lastGenerated: lastGenerated,
            workspaceURL: workspaceURL
        )
        let changedFiles = changedFilesAndRemovedKeys.0
        let removedKeys = changedFilesAndRemovedKeys.1

        // 削除されたファイルをエントリから除去
        await MainActor.run {
            for key in removedKeys { self.projectMap?.entries.removeValue(forKey: key) }
        }

        // 変更なし → 終了
        guard !changedFiles.isEmpty else {
            await MainActor.run {
                if !removedKeys.isEmpty {
                    self.projectMap?.generatedAt = Date()
                    if let pm = self.projectMap { self.saveMap(pm, workspaceURL: workspaceURL) }
                }
                if let pm = self.projectMap {
                    self.addLog(AppLanguage.shared.t("✅ L2.5 no changes (cache valid: \(pm.fileCount) files / generated: \(lastGenerated.formatted(.dateTime.hour().minute())))", "✅ L2.5 差分なし (キャッシュ有効: \(pm.fileCount) ファイル / 生成: \(lastGenerated.formatted(.dateTime.hour().minute())))"))
                }
            }
            return
        }

        // ── Step 3: 差分のみ再インデックス ───────────────────────────
        await MainActor.run {
            self.isIndexing = true
            self.indexingMode = .incremental
            self.addLog(AppLanguage.shared.t("🔄 L2.5 incremental update: \(changedFiles.count) files (last: \(lastGenerated.formatted(.dateTime.hour().minute())))", "🔄 L2.5 差分更新: \(changedFiles.count) ファイル (前回: \(lastGenerated.formatted(.dateTime.hour().minute())))"))
        }
        defer {
            Task { @MainActor in
                self.isIndexing = false
                self.indexingMode = .none
            }
        }

        // 既に Task.detached 内なので直接呼ぶ
        await self.runIncrementalUpdate(workspaceURL: workspaceURL, changedFiles: changedFiles)
    }

    nonisolated private func runIncrementalUpdate(workspaceURL: URL, changedFiles: [URL]) async {
        await Task.yield()
        await Task.yield()
        let total = max(changedFiles.count, 1)

        for (i, fileURL) in changedFiles.enumerated() {
            if Task.isCancelled { break }
            await Task.yield()

            // ✅ Throttle MainActor UI updates
            if i % 10 == 0 || i == total - 1 {
                await MainActor.run {
                    self.indexingProgress = Double(i) / Double(total)
                    self.currentFile = fileURL.lastPathComponent
                }
            }
            let relativePath = String(fileURL.path.dropFirst(workspaceURL.path.count + 1))
            guard let source = try? String(contentsOf: fileURL, encoding: .utf8) else { continue }

            let entry = await generateL25Entry(source: source, relativePath: relativePath, language: fileURL.pathExtension.lowercased())
            if let entry = entry {
                await MainActor.run {
                    self.projectMap?.entries[relativePath] = entry
                    // 5ファイルごとに中間保存して、強制終了に備える
                    if i % 5 == 0 {
                        self.projectMap?.generatedAt = Date()
                        if let map = self.projectMap {
                            self.saveMap(map, workspaceURL: workspaceURL)
                        }
                    }
                }
            }
        }

        await MainActor.run {
            self.currentFile = ""
            self.projectMap?.generatedAt = Date()
            if let entries = self.projectMap?.entries {
                self.projectMap?.globalTopology = self.synthesizeGlobalTopology(from: Array(entries.values))
            }
            if let map = self.projectMap {
                self.saveMap(map, workspaceURL: workspaceURL)
                self.indexingProgress = 1.0
                self.addLog(AppLanguage.shared.t("✅ L2.5 incremental update complete: \(map.fileCount) files (\(changedFiles.count) updated)", "✅ L2.5 差分更新完了: \(map.fileCount) ファイル (\(changedFiles.count) 件更新)"))
            }
        }
    }
    //
    // ⚠️ LLM推論（BitNet等）は遅延の最大の原因となるため廃止し、
    //    完全なルールベース（100%決定論的かつ高速）に移行しました。

    /// ルールベースで1ファイルを L2.5 エントリに変換する。
    nonisolated func generateL25Entry(
        source: String,
        relativePath: String,
        language: String
    ) async -> L25SourceMapEntry? {
        let kanjiTopology = generateKanjiRuleBased(
            source: source,
            language: language,
            relativePath: relativePath
        )

        // 構造トークン・依存・行数を軽量抽出 (BitNetのプロンプト補助用・非公開)
        let lines = source.components(separatedBy: "\n")
        let lineCount = lines.count
        var tokens: [String] = []
        var funcCount = 0
        var deps: [String] = []
        for line in lines {
            let t = line.trimmingCharacters(in: .whitespaces)
            if t.hasPrefix("import ") || t.hasPrefix("use ") {
                let dep = t.replacingOccurrences(of: "import ", with: "")
                              .replacingOccurrences(of: "use ", with: "")
                              .components(separatedBy: ";").first?
                              .components(separatedBy: "::").first ?? ""
                if !dep.isEmpty && dep.count < 30 { deps.append(dep) }
            }
            for kw in ["class ", "struct ", "enum ", "func ", "fn ", "impl ", "protocol ", "extension "] {
                if t.hasPrefix(kw) {
                    let name = t.dropFirst(kw.count)
                                .components(separatedBy: CharacterSet(charactersIn: " <:({")).first ?? ""
                    if !name.isEmpty && name.count <= 40 { tokens.append(String(name)) }
                    if kw == "func " || kw == "fn " { funcCount += 1 }
                }
            }
        }
        let complexity: Int
        switch lineCount {
        case 0..<50:   complexity = 1
        case 50..<200: complexity = 2
        case 200..<500: complexity = 3
        case 500..<1000: complexity = 4
        default:        complexity = 5
        }

        return L25SourceMapEntry(
            relativePath: relativePath,
            language: language,
            kanjiTopology: kanjiTopology,
            structureTokens: Array(tokens.prefix(10)),
            dependencies: Array(Set(deps).prefix(8)),
            lineCount: lineCount,
            functionCount: funcCount,
            complexityScore: complexity
        )
    }

    /// クラウドLLMやルールベースでのコード修正（パッチ）適用直後に呼び出し、
    /// 即座にL2.5地図を更新し、変更された意図やコンテキストをマップ上にマーキングする。
    func updateEntryInstantly(for fileURL: URL, workspaceURL: URL, patchContext: String = "") async {
        let relativePath = String(fileURL.path.dropFirst(workspaceURL.path.count + 1))
        guard let source = try? String(contentsOf: fileURL, encoding: .utf8) else { return }
        
        if let entry = await generateL25Entry(source: source, relativePath: relativePath, language: fileURL.pathExtension.lowercased()) {
            await MainActor.run {
                var modifiedEntry = entry
                if !patchContext.isEmpty {
                    // 地図のトポロジー表記に変更ログを追記
                    let newTopology = entry.kanjiTopology + " [📝修:\(patchContext.prefix(10))]"
                    let shortPath = fileURL.lastPathComponent
                    let tokens = entry.structureTokens.prefix(3).joined(separator: "+")
                    let newIndexLine = "\(newTopology.prefix(30)) | \"\(shortPath): \(tokens)\" L\(entry.lineCount)F\(entry.functionCount)"
                    
                    modifiedEntry = L25SourceMapEntry(
                        relativePath: entry.relativePath,
                        language: entry.language,
                        kanjiTopology: newTopology,
                        structureTokens: entry.structureTokens,
                        dependencies: entry.dependencies,
                        lineCount: entry.lineCount,
                        functionCount: entry.functionCount,
                        complexityScore: entry.complexityScore,
                        generatedAt: Date(),
                        indexLine: newIndexLine
                    )
                }
                
                self.projectMap?.entries[relativePath] = modifiedEntry
                self.projectMap?.generatedAt = Date()
                if let entries = self.projectMap?.entries {
                    self.projectMap?.globalTopology = self.synthesizeGlobalTopology(from: Array(entries.values))
                }
                if let map = self.projectMap {
                    self.saveMap(map, workspaceURL: workspaceURL)
                    self.addLog(AppLanguage.shared.t("✅ L2.5 instant update: \(relativePath) (\(patchContext))", "✅ L2.5 即時更新: \(relativePath) (\(patchContext))"))
                }
            }
        }
    }

    nonisolated private func generateKanjiRuleBased(
        source: String,
        language: String,
        relativePath: String
    ) -> String {
        var scores: [(String, Double)] = []
        let lower = source.lowercased()

        // 1. 拡張子/言語ベース
        switch language.lowercased() {
        case "swift":    scores.append(("[迅:1.0]", 1.0))
        case "rs", "rust": scores.append(("[錆:1.0]", 1.0))
        case "py", "python": scores.append(("[蛇:1.0]", 1.0))
        case "ts", "tsx", "typescript": scores.append(("[型:1.0]", 1.0))
        case "go":       scores.append(("[駆:1.0]", 1.0))
        default:         scores.append(("[碼:1.0]", 1.0))
        }

        // 2. アーキテクチャ/役割ベース
        let lowerPath = relativePath.lowercased()
        if lowerPath.contains("view") || lowerPath.contains("ui") || lower.contains("render") {
            scores.append(("[視:0.9]", 0.9))
        }
        if lowerPath.contains("engine") || lowerPath.contains("manager") || lowerPath.contains("controller") {
            scores.append(("[機:0.9]", 0.9))
        }
        if lowerPath.contains("model") || lowerPath.contains("store") || lowerPath.contains("vault") {
            scores.append(("[蔵:0.8]", 0.8))
        }

        // 3. コンテンツ（処理内容）ベース
        if lower.contains("async") || lower.contains("await") || lower.contains("actor") || lower.contains("thread") {
            scores.append(("[並:0.8]", 0.8))
        }
        if lower.contains("encrypt") || lower.contains("crypto") || lower.contains("aes") || lower.contains("hash") {
            scores.append(("[秘:0.9]", 0.9))
        }
        if lower.contains("network") || lower.contains("http") || lower.contains("urlsession") || lower.contains("fetch") {
            scores.append(("[網:0.8]", 0.8))
        }
        if lower.contains("test") || lower.contains("assert") || lower.contains("expect") {
            scores.append(("[験:0.8]", 0.8))
        }

        // 上位のタグを合成（最大4つ）
        let top = scores.sorted { $0.1 > $1.1 }.prefix(4).map { $0.0 }.joined()
        
        // 構造名も一部抽出して付与
        let tokenNames = relativePath.components(separatedBy: "/").last?.components(separatedBy: ".").first ?? ""
        return "\(top.isEmpty ? "[碼:1.0]" : top) \(tokenNames)"
    }

    // MARK: - グローバルトポロジー合成

    nonisolated private func synthesizeGlobalTopology(from entries: [L25SourceMapEntry]) -> String {
        // 全エントリの漢字タグを集計してプロジェクト全体の特性を表す
        var kanjiFreq: [String: Int] = [:]
        for entry in entries {
            let pattern = "\\[([^\\]:]+):[0-9.]+\\]"
            let regex = try? NSRegularExpression(pattern: pattern)
            let range = NSRange(entry.kanjiTopology.startIndex..., in: entry.kanjiTopology)
            let nsMatches = regex?.matches(in: entry.kanjiTopology, range: range) ?? []
            for m in nsMatches {
                if let r = Range(m.range(at: 1), in: entry.kanjiTopology) {
                    let k = String(entry.kanjiTopology[r])
                    kanjiFreq[k, default: 0] += 1
                }
            }
        }
        let top = kanjiFreq.sorted { $0.value > $1.value }.prefix(6)
        let tagStr = top.map { "[\($0.key):\($0.value)]" }.joined()
        let fileTypes = Dictionary(grouping: entries, by: \.language)
            .map { "\($0.key)×\($0.value.count)" }
            .joined(separator: " ")
        return "\(tagStr) [\(fileTypes)]"
    }

    // MARK: - ファイル収集

    nonisolated private func collectTargetFiles(workspaceURL: URL) -> [URL] {
        let targetExts: Set<String> = ["swift", "rs", "ts", "tsx", "py", "go", "kt", "java", "cpp", "c", "h"]
        let excludedPaths = [
            ".openclaw", ".git", "node_modules", ".build", "build", "DerivedData", "__pycache__",
            "target", "vendor", "dist", "out", "Pods", "env", ".env", "site-packages", "third_party"
        ]
        var result: [URL] = []

        guard let enumerator = FileManager.default.enumerator(
            at: workspaceURL,
            includingPropertiesForKeys: [.isDirectoryKey, .fileSizeKey],
            options: [.skipsHiddenFiles]
        ) else { return [] }

        for case let fileURL as URL in enumerator {
            let name = fileURL.lastPathComponent
            let values = try? fileURL.resourceValues(forKeys: [.isDirectoryKey, .fileSizeKey])
            if values?.isDirectory == true {
                if excludedPaths.contains(name) { enumerator.skipDescendants() }
                continue
            }
            let ext = fileURL.pathExtension.lowercased()
            guard targetExts.contains(ext) else { continue }
            let size = values?.fileSize ?? 0
            if size > 300_000 { continue }  // 300KB超はスキップ
            result.append(fileURL)
        }
        return result
    }

    // MARK: - 永続化

    nonisolated private func mapFileURL(workspaceURL: URL) -> URL {
        workspaceURL.appendingPathComponent(".openclaw/l25_map.jcross")
    }

    nonisolated private func saveMap(_ map: L25ProjectMap, workspaceURL: URL) {
        let url = mapFileURL(workspaceURL: workspaceURL)
        try? FileManager.default.createDirectory(
            at: url.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        let text = map.toJCrossString()
        try? text.write(to: url, atomically: true, encoding: .utf8)
    }

    private func addLog(_ msg: String) {
        log.append("[\(Date().formatted(.dateTime.hour().minute().second()))] \(msg)")
        if log.count > 200 { log.removeFirst(50) }
    }

    // MARK: - Static nonisolated helpers (self をキャプチャしない・Task.detached 不要)

    /// collectTargetFiles の static ラッパー。nonisolated でバックグラウンド安全。
    nonisolated static func collectFiles(workspaceURL: URL) -> [URL] {
        let targetExts: Set<String> = ["swift", "rs", "ts", "tsx", "py", "go", "kt", "java", "cpp", "c", "h"]
        let excludedPaths = [
            ".openclaw", ".git", "node_modules", ".build", "build", "DerivedData", "__pycache__",
            "target", "vendor", "dist", "out", "Pods", "env", ".env", "site-packages", "third_party"
        ]
        var result: [URL] = []
        guard let enumerator = FileManager.default.enumerator(
            at: workspaceURL,
            includingPropertiesForKeys: [.isDirectoryKey, .fileSizeKey],
            options: [.skipsHiddenFiles]
        ) else { return [] }
        for case let fileURL as URL in enumerator {
            let name = fileURL.lastPathComponent
            let values = try? fileURL.resourceValues(forKeys: [.isDirectoryKey, .fileSizeKey])
            if values?.isDirectory == true {
                if excludedPaths.contains(name) { enumerator.skipDescendants() }
                continue
            }
            let ext = fileURL.pathExtension.lowercased()
            guard targetExts.contains(ext) else { continue }
            if (values?.fileSize ?? 0) > 300_000 { continue }
            result.append(fileURL)
        }
        return result
    }

    /// 変更・削除ファイルを検出する純粋関数。self 不要。
    nonisolated static func detectChangedFiles(
        allFiles: [URL],
        currentMap: L25ProjectMap,
        lastGenerated: Date,
        workspaceURL: URL
    ) async -> ([URL], [String]) {
        var changed: [URL] = []
        for fileURL in allFiles {
            let attrs = try? FileManager.default.attributesOfItem(atPath: fileURL.path)
            let modDate = (attrs?[.modificationDate] as? Date) ?? .distantPast
            let relativePath = String(fileURL.path.dropFirst(workspaceURL.path.count + 1))
            if currentMap.entries[relativePath] == nil || modDate > lastGenerated {
                changed.append(fileURL)
            }
        }
        let allRelative = Set(allFiles.map { String($0.path.dropFirst(workspaceURL.path.count + 1)) })
        let removed = currentMap.entries.keys.filter { !allRelative.contains($0) }
        return (changed, removed)
    }
}

