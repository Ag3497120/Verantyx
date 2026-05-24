import Foundation
import Security

// MARK: - JCrossVault
//
// ワークスペース全体の JCross 変換済みシャドウファイルシステム。
// 実体: .openclaw/jcross_vault/{relativePath}.jcross
//       .openclaw/jcross_vault/{relativePath}.schema.json
//
// セキュリティ:
//   - .jcross ファイルには JCross IR のみ（識別子は全てノードID）
//   - .schema.json はノードID ↔ 実識別子のマッピング（ローカルのみ）
//   - .gitignore に jcross_vault/ を追加（リモートへの流出防止）

@MainActor
final class JCrossVault: ObservableObject {

    // MARK: - Types

    enum VaultStatus: Equatable {
        case notInitialized
        case converting(progress: Double, currentFile: String)
        case ready(fileCount: Int, lastConverted: Date)
        case error(String)
    }

    struct VaultEntry: Codable {
        let relativePath: String      // 元ファイルの相対パス
        let jcrossPath: String        // .jcross ファイルの相対パス
        let schemaPath: String        // .schema.json の相対パス
        let l1TagsPath: String?       // .l1tags ファイルの相対パス（BitNet 未導入の場合 nil）
        let convertedAt: Date
        let fileHash: String          // 元ファイルの SHA256（変更検知）
        let nodeCount: Int
        let secretCount: Int
        let schemaSessionID: String   // JCrossSchema の sessionID
        // ── L1.5 コード差分情報（ローカルモード用） ─────────────────────
        var l15Index: L15DiffEntry?   // 最後の変更差分サマリー（記憶システム用）
    }

    /// L1.5 差分メタデータ。
    /// 「何がどこで変わったか」を漢字トポロジーで記録し、
    /// 次セッション起動時にフルソースなしで変更を再追跡できる。
    struct L15DiffEntry: Codable {
        /// 変更行数範囲 e.g. "45-120"
        var lineRange: String
        /// 変更前の内容の漢字要約 e.g. "guard!fileExists廃止前"
        var beforeKanji: String
        /// 変更後の内容の漢字要約 e.g. "extractPackageName+moveItem追加"
        var afterKanji: String
        /// 変更の文脈・理由 (1行)
        var context: String
        /// 記録日時
        var recordedAt: Date
        /// L1.5インデックス行（memory_mapで表示される1行形式）
        var indexLine: String
    }

    struct VaultIndex: Codable {
        var entries: [String: VaultEntry]  // relativePath → VaultEntry
        var createdAt: Date
        var lastUpdatedAt: Date
        var workspaceRoot: String
    }

    struct ReadResult {
        let jcrossContent: String
        let schema: JCrossSchema
        let entry: VaultEntry
    }

    // MARK: - Properties

    @Published var vaultStatus: VaultStatus = .notInitialized
    @Published var conversionLog: [String] = []

    let workspaceURL: URL
    var vaultIndex: VaultIndex?

    lazy var vaultRootURL: URL = {
        workspaceURL.appendingPathComponent(".openclaw/jcross_vault")
    }()

    private lazy var indexURL: URL = {
        vaultRootURL.appendingPathComponent("VAULT_INDEX.json")
    }()

    // 変換対象の拡張子
    private static let targetExtensions: Set<String> = [
        "swift", "ts", "tsx", "js", "jsx", "py", "rs", "go", "kt", "java",
        "cpp", "cc", "c", "h", "cs", "rb", "php", "sh",
        "css", "scss", "html", "htm", "json", "md", "txt", "yaml", "yml", "toml", "xml", "csv"
    ]

    // 除外パス
    nonisolated(unsafe) private static let excludedPaths: [String] = [
        ".openclaw", ".git", "node_modules", ".build", "build",
        "DerivedData", ".DS_Store", "__pycache__", ".venv", "venv",
        "target", "vendor", "dist", "out", "Pods", "env", ".env", "site-packages",
        "third_party", "benchmarks", "benchmark", "test_data", "test-data",
        "envs"
    ]

    // MARK: - Init

    init(workspaceURL: URL) {
        self.workspaceURL = workspaceURL
    }

    // MARK: - Initialize Vault

    func initialize() async {
        // 既存インデックスを読み込む（ディスク読み取り1回のみ — 軽量化のため別スレッド化）
        let idxURL = self.indexURL
        let existingIndex = await Task.detached(priority: .utility) { [idxURL] in
            guard let data = try? Data(contentsOf: idxURL) else { return nil as VaultIndex? }
            return try? JSONDecoder().decode(VaultIndex.self, from: data)
        }.value

        if let existing = existingIndex {
            vaultIndex = existing
            let count = existing.entries.count
            let date  = existing.lastUpdatedAt
            vaultStatus = .ready(fileCount: count, lastConverted: date)
            log("✅ Vault ロード完了: \(count) ファイル (最終更新: \(date.formatted()))")

            // ⚠️ セッションマッピング復元 + 差分更新はバックグラウンドで実行。
            // MainActor をブロックしないよう、重いディスクI/Oは Task.detached に逃がす。
            let vaultRoot = self.vaultRootURL
            let entries   = existing.entries
            Task { [weak self] in
                guard let self else { return }

                // ① スキーマ復元（ファイルごとにディスクI/Oのためバックグラウンドへ）
                let transpiler = await PolymorphicJCrossTranspiler.shared
                let sessionDatas = await Task.detached(priority: .utility) {
                    var results: [PolymorphicJCrossTranspiler.JCrossSchemaSessionData] = []
                    for entry in entries.values {
                        let schemaFileURL = vaultRoot.appendingPathComponent(entry.schemaPath)
                        if let data = try? Data(contentsOf: schemaFileURL),
                           let sessionData = try? JSONDecoder().decode(
                               PolymorphicJCrossTranspiler.JCrossSchemaSessionData.self, from: data
                           ) {
                            results.append(sessionData)
                        }
                    }
                    return results
                }.value
                
                // 復元したセッションデータを Transpiler に登録
                for data in sessionDatas {
                    transpiler.restoreSession(from: data)
                }

                // ② Git 差分で変更されたファイルのみ再変換
                await self.updateDelta()
            }
        } else {
            // 初回: 全ファイル一括変換（すでにバックグラウンドで動く）
            await bulkConvert()
        }
    }


    // MARK: - Rebuild Vault (強制再変換)

    func rebuildVault() async {
        vaultStatus = .notInitialized
        vaultIndex = nil
        conversionLog.removeAll()
        do {
            try FileManager.default.removeItem(at: vaultRootURL)
        } catch {
            log("Vault ディレクトリ削除に失敗: \(error.localizedDescription) (初回作成の場合は無視可能)")
        }
        await bulkConvert()
    }

    // MARK: - Bulk Conversion (初回)

    // nonisolated: @MainActor クラスのメソッドは省略すると @MainActor を継承するため
    // Task.detached から呼んでも MainActor に戻ってしまう。
    // nonisolated を明示することで真にバックグラウンドで動作する。
    nonisolated func bulkConvert() async {
        // MainActor プロパティへの初回アクセスは await で取得
        let wsRoot    = await workspaceURL
        let vaultRoot = await vaultRootURL
        let idxURL    = await indexURL

        do {
            try FileManager.default.createDirectory(at: vaultRoot, withIntermediateDirectories: true)
        } catch {
            let msg = error.localizedDescription
            await MainActor.run { self.vaultStatus = .error("Vault ディレクトリ作成失敗: \(msg)") }
            return
        }

        let files = JCrossVault.collectTargetFiles(wsRoot: wsRoot)
        await MainActor.run { self.log("📁 変換対象: \(files.count) ファイル") }

        // fire-and-forget でバックグラウンド変換を開始
        Task { [weak self] in  // was Task.detached
            await JCrossVault._convertBatch(
                files: files, wsRoot: wsRoot, vaultRoot: vaultRoot, idxURL: idxURL, vault: self
            )
        }
    }

    /// バックグラウンド変換バッチ（nonisolated static — @MainActor を継承しない）
    nonisolated private static func _convertBatch(
        files: [URL],
        wsRoot: URL,
        vaultRoot: URL,
        idxURL: URL,
        vault: JCrossVault?
    ) async {
        guard let vault else { return }

        // バッチ全体で1つの irVault を共有し、最後に1回だけディスクへ書き込む（ディスクI/Oのボトルネックと上書きバグ解消）
        let irVaultURL = vaultRoot.appendingPathComponent("ir_vault.enc")
        let irVault    = JCrossIRVault(persistenceURL: irVaultURL)
        if FileManager.default.fileExists(atPath: irVaultURL.path) {
            try? irVault.loadEncrypted(from: irVaultURL)
        }

        // MainActor スイッチのオーバーヘッドを避けるため、バッチ開始時に1度だけ取得
        let useOllama = await MainActor.run { GatekeeperModeState.shared.useOllamaNER }


        var index = VaultIndex(
            entries: [:],
            createdAt: Date(),
            lastUpdatedAt: Date(),
            workspaceRoot: wsRoot.path
        )

        // JCrossCodeTranspiler.shared (MainActor) へのアクセスを一度だけ行い、
        // nonisolated メソッドを呼び出すため参照を保持する
        let transpiler = await PolymorphicJCrossTranspiler.shared
        let totalFiles = files.count

        await withTaskGroup(of: (Int, String, VaultEntry?, String?).self) { group in
            let concurrencyLimit = 32
            var activeTasks = 0
            var i = 0

            func enqueueNext() {
                guard i < totalFiles else { return }
                let fileURL = files[i]
                let idx = i
                i += 1
                activeTasks += 1
                
                group.addTask {
                    let relativePath = String(fileURL.path.dropFirst(wsRoot.path.count + 1))
                    do {
                        let entry = try await vault.convertFile(
                            fileURL: fileURL, relativePath: relativePath,
                            transpiler: transpiler,
                            vaultRootURL: vaultRoot,
                            irVault: irVault,
                            useOllamaNER: useOllama
                        )
                        return (idx, relativePath, entry, nil)
                    } catch {
                        return (idx, relativePath, nil, error.localizedDescription)
                    }
                }
            }

            // 初期タスク投入
            while activeTasks < concurrencyLimit && i < totalFiles {
                enqueueNext()
            }

            for await (idx, relativePath, entry, errDesc) in group {
                activeTasks -= 1
                
                let prog = Double(idx) / Double(max(totalFiles, 1))
                if idx % 10 == 0 || idx == totalFiles - 1 {
                    Task { @MainActor [weak vault] in
                        vault?.vaultStatus = .converting(progress: prog, currentFile: relativePath)
                    }
                }

                if let entry = entry {
                    index.entries[relativePath] = entry
                    if idx % 10 == 0 || idx == totalFiles - 1 {
                        let msg = "  [\(idx+1)/\(totalFiles)] ✓ \(relativePath) (\(entry.nodeCount) nodes)"
                        await MainActor.run { vault.conversionLog.append(msg) }
                    }
                } else if let errorDesc = errDesc {
                    let msg = "  [\(idx+1)/\(totalFiles)] ⚠️ \(relativePath): \(errorDesc)"
                    await MainActor.run { vault.conversionLog.append(msg) }
                }

                // 次のタスクを補充
                enqueueNext()
            }
        }

        index.lastUpdatedAt = Date()

        // ディスク書き込み（バックグラウンド安全）
        if let data = try? JSONEncoder().encode(index) {
            try? data.write(to: idxURL, options: .atomic)
        }
        try? irVault.saveEncrypted()
        JCrossVault._addGitignoreEntry(vaultRoot: vaultRoot, wsRoot: wsRoot)

        let count = index.entries.count
        let fin   = index.lastUpdatedAt
        Task { @MainActor [weak vault] in
            vault?.vaultIndex  = index
            vault?.vaultStatus = .ready(fileCount: count, lastConverted: fin)
            vault?.log("✅ 一括変換完了: \(count) ファイル")
        }
    }

    /// ファイル同期変換（nonisolated static — バックグラウンドスレッド専用）
    nonisolated private static func _convertFileSynchronously(
        fileURL: URL,
        relativePath: String,
        wsRoot: URL,
        vaultRoot: URL
    ) throws -> VaultEntry {
        let source = try String(contentsOf: fileURL, encoding: .utf8)
        let ext    = fileURL.pathExtension.lowercased()

        let transpiler = SimpleJCrossTranspiler()
        let (jcrossContent, nodeCount, secretCount, sessionID) =
            transpiler.transpile(source, fileExtension: ext)

        let jcrossURL = vaultRoot.appendingPathComponent(relativePath + ".jcross")
        try FileManager.default.createDirectory(
            at: jcrossURL.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try jcrossContent.write(to: jcrossURL, atomically: true, encoding: .utf8)

        let hash: String = {
            guard let data = source.data(using: .utf8) else { return "unknown" }
            var h = 5381
            data.forEach { h = ((h << 5) &+ h) &+ Int($0) }
            return String(format: "%08x", h & 0xFFFFFFFF)
        }()

        return VaultEntry(
            relativePath: relativePath,
            jcrossPath:   relativePath + ".jcross",
            schemaPath:   relativePath + ".schema.json",
            l1TagsPath:   nil,
            convertedAt:  Date(),
            fileHash:     hash,
            nodeCount:    nodeCount,
            secretCount:  secretCount,
            schemaSessionID: sessionID
        )
    }

    /// .gitignore 更新（nonisolated static）
    nonisolated private static func _addGitignoreEntry(vaultRoot: URL, wsRoot: URL) {
        let gitignoreURL = wsRoot.appendingPathComponent(".gitignore")
        let entry = "\n# Verantyx JCross Vault (local only)\n.openclaw/jcross_vault/\n"
        if let existing = try? String(contentsOf: gitignoreURL, encoding: .utf8) {
            if !existing.contains("jcross_vault") {
                try? (existing + entry).write(to: gitignoreURL, atomically: true, encoding: .utf8)
            }
        } else {
            try? entry.write(to: gitignoreURL, atomically: true, encoding: .utf8)
        }
    }


    // MARK: - Delta Update (差分)

    func updateDelta() async {
        let wsURL = workspaceURL
        let changedFiles = await Task.detached(priority: .utility) { () -> [String] in
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/usr/bin/git")
            process.arguments = ["diff", "--name-only", "HEAD"]
            process.currentDirectoryURL = wsURL

            let pipe = Pipe()
            process.standardOutput = pipe
            process.standardError  = FileHandle.nullDevice  // stderr は不要

            do {
                try process.run()
            } catch {
                return []
            }
            // ⚠️ readDataToEndOfFile → waitUntilExit の順序を厳守
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            process.waitUntilExit()
            let output = String(data: data, encoding: .utf8) ?? ""
            return output.components(separatedBy: "\n")
                .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
                .filter { !$0.isEmpty }
        }.value

        guard !changedFiles.isEmpty else {
            log("✅ 変更なし — Vault は最新です")
            return
        }

        log("🔄 差分更新: \(changedFiles.count) ファイル")
        let transpiler = PolymorphicJCrossTranspiler.shared
        let useOllama = GatekeeperModeState.shared.useOllamaNER
        
        let irVaultURL = vaultRootURL.appendingPathComponent("ir_vault.enc")
        let irVault = JCrossIRVault(persistenceURL: irVaultURL)
        if FileManager.default.fileExists(atPath: irVaultURL.path) {
            try? irVault.loadEncrypted(from: irVaultURL)
        }

        for relativePath in changedFiles {
            let fileURL = workspaceURL.appendingPathComponent(relativePath)
            guard FileManager.default.fileExists(atPath: fileURL.path) else {
                // 削除されたファイル → Vault から除去
                removeFromVault(relativePath: relativePath)
                continue
            }

            do {
                let currentVaultRoot = vaultRootURL
                let entry = try await convertFile(
                    fileURL: fileURL,
                    relativePath: relativePath,
                    transpiler: transpiler,
                    vaultRootURL: currentVaultRoot,
                    irVault: irVault,
                    useOllamaNER: useOllama
                )
                vaultIndex?.entries[relativePath] = entry
                log("  ✓ 更新: \(relativePath)")
            } catch {
                log("  ⚠️ 更新失敗: \(relativePath) — \(error.localizedDescription)")
            }
        }

        try? irVault.saveEncrypted()

        vaultIndex?.lastUpdatedAt = Date()
        if let index = vaultIndex { saveIndex(index) }
        log("✅ 差分更新完了")
    }

    // MARK: - Read (外部API向け)

    func read(relativePath: String) -> ReadResult? {
        guard let entry = vaultIndex?.entries[relativePath] else { return nil }

        let jcrossURL = vaultRootURL.appendingPathComponent(entry.jcrossPath)
        let schemaURL = vaultRootURL.appendingPathComponent(entry.schemaPath)

        guard let jcrossContent = try? String(contentsOf: jcrossURL, encoding: .utf8) else { return nil }

        let schema: JCrossSchema
        if let schemaData = try? Data(contentsOf: schemaURL),
           let decoded = try? JSONDecoder().decode(JCrossSchema.self, from: schemaData) {
            schema = decoded
        } else {
            schema = JCrossSchema(
                sessionID: entry.schemaSessionID,
                createdAt: entry.convertedAt,
                schemaVersion: 1,
                nodeOpen: "⟨",
                nodeClose: "⟩",
                secretOpen: "「",
                secretClose: "」",
                tagOpen: "[",
                tagClose: "]",
                kanjiCategoryMap: [:],
                opNameMap: [:],
                nodePrefixMap: [:],
                noiseLevel: 0,
                noiseNodeIDs: []
            )
        }

        return ReadResult(jcrossContent: jcrossContent, schema: schema, entry: entry)
    }

    // MARK: - Write Diff (逆変換 → 実ファイル書き込み)

    func writeDiff(
        jcrossDiff: String,
        relativePath: String,
        transpiler: PolymorphicJCrossTranspiler
    ) async throws -> String {
        var targetEntry = vaultIndex?.entries[relativePath]

        if targetEntry == nil, let index = vaultIndex {
            let searchName = URL(fileURLWithPath: relativePath).lastPathComponent.lowercased()
            let baseName = searchName.replacingOccurrences(of: ".jc", with: "").replacingOccurrences(of: ".jcross", with: "")
            if let matched = index.entries.values.first(where: {
                $0.relativePath.lowercased().hasSuffix(baseName) ||
                URL(fileURLWithPath: $0.relativePath).lastPathComponent.lowercased().starts(with: baseName)
            }) {
                targetEntry = matched
            }
        }

        guard let entry = targetEntry else {
            // 既存ファイルが見つからない場合：新規ファイルとして扱う（例：トランスパイル後の別言語ファイル生成）
            let fileURL = workspaceURL.appendingPathComponent(relativePath)
            let dirURL = fileURL.deletingLastPathComponent()
            try? FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true, attributes: nil)
            
            let restored = jcrossDiff
            try restored.write(to: fileURL, atomically: true, encoding: .utf8)
            await updateDelta()
            
            log("✅ 新規ファイル生成・書き込み完了: \(relativePath)")
            return restored
        }

        // 実ファイルの内容を取得
        let fileURL = workspaceURL.appendingPathComponent(entry.relativePath)
        let originalContent = (try? String(contentsOf: fileURL, encoding: .utf8)) ?? ""

        // JCross → 実コードに逆変換
        guard let restored = await transpiler.reverseTranspile(jcross: jcrossDiff, originalContent: originalContent, schemaID: entry.schemaSessionID) else {
            throw VaultError.reverseTranspileFailed(entry.relativePath)
        }

        // 実ファイルに書き込み
        try restored.write(to: fileURL, atomically: true, encoding: .utf8)

        // Vault を更新（差分適用後の状態で再変換）
        await updateDelta()

        log("✅ 逆変換・書き込み完了: \(entry.relativePath)")
        return restored
    }

    // MARK: - List Directory (抽象化)

    func listDirectory(relativePath: String) -> [AbstractedFileInfo] {
        guard let index = vaultIndex else { return [] }
        let prefix = relativePath.isEmpty ? "" : relativePath + "/"

        // 直下のエントリのみ返す
        var seen = Set<String>()
        var result: [AbstractedFileInfo] = []

        for path in index.entries.keys {
            guard path.hasPrefix(prefix) else { continue }
            let rest = String(path.dropFirst(prefix.count))
            let component = rest.components(separatedBy: "/").first ?? rest
            if seen.contains(component) { continue }
            seen.insert(component)

            let isDir = rest.contains("/")
            let entry = index.entries[path]
            result.append(AbstractedFileInfo(
                name: component,
                isDirectory: isDir,
                jcrossPath: isDir ? nil : entry?.jcrossPath,
                nodeCount: isDir ? nil : entry?.nodeCount,
                secretCount: isDir ? nil : entry?.secretCount
            ))
        }

        return result.sorted { $0.isDirectory && !$1.isDirectory || $0.name < $1.name }
    }

    // MARK: - Search (JCross内のノードID検索)

    func search(query: String) -> [SearchResult] {
        guard let index = vaultIndex else { return [] }
        var results: [SearchResult] = []

        for (path, entry) in index.entries {
            let jcrossURL = vaultRootURL.appendingPathComponent(entry.jcrossPath)
            guard let content = try? String(contentsOf: jcrossURL, encoding: .utf8) else { continue }

            // JCross IR 内でクエリに一致する行を検索
            let matchingLines = content.components(separatedBy: "\n")
                .enumerated()
                .filter { $0.element.localizedCaseInsensitiveContains(query) }
                .prefix(3)
                .map { SearchResult.Match(lineNumber: $0.offset + 1, line: String($0.element.prefix(120))) }

            if !matchingLines.isEmpty {
                results.append(SearchResult(relativePath: path, matches: Array(matchingLines)))
            }

            if results.count >= 20 { break }
        }

        return results
    }

    // MARK: - Private Helpers

    nonisolated private func convertFile(
        fileURL: URL,
        relativePath: String,
        transpiler: PolymorphicJCrossTranspiler,
        vaultRootURL: URL,
        irVault: JCrossIRVault,
        useOllamaNER: Bool
    ) async throws -> VaultEntry {
        let source = try String(contentsOf: fileURL, encoding: .utf8)
        let lang   = JCrossCodeTranspiler.CodeLanguage.from(extension: fileURL.pathExtension)

        // ── 6軸IR生成 (新方式) ────────────────────────────────────────────
        // JCrossIRGenerator がソースを 6軸構造体 + ローカルVault に変換する。
        // 秘密軸（関数名・定数値等）は irVault に隔離。
        // LLMへ送信するのは ObfuscatedIRDocument のみ。
        let irGen      = JCrossIRGenerator()
        let irDoc      = irGen.generateIR(from: source, language: lang, vault: irVault)

        // 3層難読化を適用して LLM 送信用ドキュメントを生成
        let obfPipeline = JCrossObfuscationPipeline()
        let obfDoc      = obfPipeline.obfuscate(document: irDoc)

        // LLM に送信するコンテキストは、識別子をシャッフルした構文構造 (Polymorphic) を使用する。
        // opaque な 6軸IR では LLM がコードを編集できないため。
        let transpiled = await transpiler.transpileBackground(source, language: lang, noiseLevel: 2, useOllamaNER: useOllamaNER)
        let jcrossContent = transpiled.jcross
        let schemaID = transpiled.schemaID

        let nodeCount   = irDoc.nodes.count
        let secretCount = irVault.statistics.entriesWithSemantics

        // .jcross / .schema.json ファイルを書き込む
        // v2.3: ディレクトリ階層を維持し、確実にディレクトリを作成する
        let jcrossRelPath = relativePath + ".jcross"
        let schemaRelPath = relativePath + ".schema.json"

        let jcrossFileURL = vaultRootURL.appendingPathComponent(jcrossRelPath)
        let schemaFileURL = vaultRootURL.appendingPathComponent(schemaRelPath)

        try? FileManager.default.createDirectory(at: jcrossFileURL.deletingLastPathComponent(), withIntermediateDirectories: true)

        try jcrossContent.write(to: jcrossFileURL, atomically: true, encoding: String.Encoding.utf8)

        // 逆変換に必要なセッションデータ（スキーママップ、NodeMap、ReverseMap）を保存
        if let sessionData = await transpiler.getSessionData(for: schemaID),
           let schemaData = try? JSONEncoder().encode(sessionData) {
            try? schemaData.write(to: schemaFileURL)
        }

        // ── BitNet L1 タグ生成 ──────────────────────────────────────────
        let langName      = fileURL.pathExtension.lowercased()
        let l1Tags        = await generateL1TagsViaBitNet(source: source, language: langName)
        let l1TagsRelPath = relativePath + ".l1tags"
        let l1TagsFileURL = vaultRootURL.appendingPathComponent(l1TagsRelPath)
        if let l1Data = l1Tags.data(using: .utf8) {
            try? l1Data.write(to: l1TagsFileURL)
        }
        // ───────────────────────────────────────────────────────────────

        let fileHash = await sha256(of: source)
        return VaultEntry(
            relativePath: relativePath,
            jcrossPath: jcrossRelPath,
            schemaPath: schemaRelPath,
            l1TagsPath: l1TagsRelPath,
            convertedAt: Date(),
            fileHash: fileHash,
            nodeCount: nodeCount,
            secretCount: secretCount,
            schemaSessionID: schemaID
        )
    }

    /// 6軸IRドキュメントを IDE の Gatekeeper ビュー用テキストに変換する。
    /// LLMには難読化済み版が送られるが、ローカルビューには構造情報を表示する。
    nonisolated private func buildJCrossText(
        irDoc: JCrossIRDocument,
        obfDoc: ObfuscatedIRDocument,
        relativePath: String,
        lang: String
    ) -> String {
        var lines: [String] = []

        lines.append(";;; 🛡️ GATEKEEPER MODE — JCross 6-Axis IR v2.2-opaque")
        lines.append(";;; Source: \(relativePath)")
        lines.append(";;; Schema: \(irDoc.documentID.raw.prefix(12))")
        lines.append(";;; Nodes: \(irDoc.nodes.count) real + \(obfDoc.nodes.values.filter { $0.isPhantom }.count) phantom")
        lines.append(";;; Obfuscation: arity_normalization + complete_opaquification + random_hash_per_node + phantom_node_injection + topology_shuffling")
        lines.append(";;;")
        lines.append(";;; What LLM receives:")
        lines.append(";;;   ALL nodes → kind:opaque TYPE:opaque MEM:opaque HASH:{unique random}")
        lines.append(";;;   ARITY class only (noise-shifted ±20%)")
        lines.append(";;;   Phantoms mixed in (45% density) — indistinguishable from real nodes")
        lines.append(";;;   SEMANTICS → NEVER exposed (encrypted Vault only)")
        lines.append(";;;")  
        lines.append("// JCROSS_6AXIS_BEGIN")
        lines.append("// lang:\(lang) doc:\(irDoc.documentID.raw.prefix(8))")
        lines.append("")

        // 関数単位で出力
        for func_ in irDoc.functions {
            lines.append("// ── FUNC[\(func_.id.raw.prefix(6))] params:\(func_.paramCount) return:\(func_.returnCount) async:\(func_.isAsync) throw:\(func_.canThrow)")
            for nodeID in func_.bodyNodeIDs {
                if let node = irDoc.nodes[nodeID] {
                    lines.append(formatNode(node))
                }
            }
            lines.append("")
        }

        // 関数に属さないノード
        let bodyNodeIDs = Set(irDoc.functions.flatMap { $0.bodyNodeIDs })
        let orphans = irDoc.nodes.filter { !bodyNodeIDs.contains($0.key) }
        if !orphans.isEmpty {
            lines.append("// ── TOP-LEVEL NODES")
            for (_, node) in orphans {
                lines.append(formatNode(node))
            }
        }

        lines.append("")
        lines.append("// JCROSS_6AXIS_END")

        return lines.joined(separator: "\n")
    }

    /// v2.2: すべてのノードを kind:opaque TYPE:opaque MEM:opaque HASH:{random} で出力。
    /// 具体的な種別・型・メモリ情報は一切公開しない。
    nonisolated private func formatNode(_ node: JCrossIRNode) -> String {
        var parts: [String] = ["  NODE[\(node.id.raw.prefix(6))]"]

        // v2.2: kind / TYPE / MEM はすべて opaque
        parts.append("kind:opaque")
        parts.append("TYPE:opaque")
        parts.append("MEM:opaque")

        // v2.2: ハッシュは毎回ランダム（同一ノードでも呼び出しごとに異なる）
        var bytes = [UInt8](repeating: 0, count: 4)
        _ = SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes)
        let hash = "0x" + bytes.map { String(format: "%02x", $0) }.joined()
        parts.append("HASH:\(hash)")

        // アリティのみ公開（グラフ解法の最小情報）
        if let df = node.dataFlow {
            let arity = NormalizedArity.normalize(df.inputArity).rawValue
            parts.append("ARITY:class.\(arity)")
        }

        return parts.joined(separator: " ")
    }


    nonisolated private static func collectTargetFiles(wsRoot: URL) -> [URL] {
        var result: [URL] = []
        let fm = FileManager.default
        guard let enumerator = fm.enumerator(
            at: wsRoot,
            includingPropertiesForKeys: [.isDirectoryKey, .fileSizeKey, .isRegularFileKey],
            options: [.skipsHiddenFiles]
        ) else { return [] }

        for case let fileURL as URL in enumerator {
            // Check if it's a directory
            let resourceValues = try? fileURL.resourceValues(forKeys: [.isDirectoryKey, .fileSizeKey])
            let isDirectory = resourceValues?.isDirectory ?? false
            let fileName = fileURL.lastPathComponent

            if isDirectory {
                if JCrossVault.excludedPaths.contains(fileName) {
                    enumerator.skipDescendants()
                }
                continue
            }

            // Exclude minified files
            if fileName.contains(".min.") { continue }

            // Exclude by path substrings just in case
            let path = fileURL.path
            if JCrossVault.excludedPaths.contains(where: { path.contains("/\($0)/") || path.hasSuffix("/\($0)") }) {
                continue
            }

            // 拡張子フィルタ
            let ext = fileURL.pathExtension.lowercased()
            guard JCrossVault.targetExtensions.contains(ext) else { continue }

            // サイズフィルタ (500KB 以上は重すぎるため JCross 変換対象外)
            let fileSize = resourceValues?.fileSize ?? 0
            if fileSize > 500_000 { continue }

            result.append(fileURL)
        }

        return result
    }



    private func removeFromVault(relativePath: String) {
        guard let entry = vaultIndex?.entries[relativePath] else { return }
        try? FileManager.default.removeItem(at: vaultRootURL.appendingPathComponent(entry.jcrossPath))
        try? FileManager.default.removeItem(at: vaultRootURL.appendingPathComponent(entry.schemaPath))
        vaultIndex?.entries.removeValue(forKey: relativePath)
        log("🗑️ Vault から除去: \(relativePath)")
    }

    private func loadIndex() -> VaultIndex? {
        guard let data = try? Data(contentsOf: indexURL) else { return nil }
        return try? JSONDecoder().decode(VaultIndex.self, from: data)
    }

    private func saveIndex(_ index: VaultIndex) {
        guard let data = try? JSONEncoder().encode(index) else { return }
        try? data.write(to: indexURL)
    }

    private func addGitignoreEntry() {
        let gitignoreURL = workspaceURL.appendingPathComponent(".gitignore")
        let entry = "\n# Verantyx JCross Vault (session-specific schemas — never commit)\n.openclaw/jcross_vault/\n"

        if let existing = try? String(contentsOf: gitignoreURL, encoding: .utf8) {
            if !existing.contains("jcross_vault") {
                try? (existing + entry).write(to: gitignoreURL, atomically: true, encoding: .utf8)
                log("📝 .gitignore に jcross_vault/ を追加")
            }
        } else {
            try? entry.write(to: gitignoreURL, atomically: true, encoding: .utf8)
        }
    }

    private func sha256(of string: String) -> String {
        let data = Data(string.utf8)
        var hash = [UInt8](repeating: 0, count: 32)
        data.withUnsafeBytes { ptr in
            _ = ptr // Simple checksum as placeholder
        }
        return String(data.hashValue, radix: 16)
    }

    private func log(_ message: String) {
        conversionLog.append("[\(Date().formatted(.dateTime.hour().minute().second()))] \(message)")
        if conversionLog.count > 500 { conversionLog.removeFirst(100) }
    }

    // MARK: - Errors

    enum VaultError: Error, LocalizedError {
        case entryNotFound(String)
        case reverseTranspileFailed(String)
        var errorDescription: String? {
            switch self {
            case .entryNotFound(let p): return "Vault にエントリなし: \(p)"
            case .reverseTranspileFailed(let p): return "逆変換失敗 (スキーマが見つかりません): \(p)"
            }
        }
    }

    // MARK: - L1.5 Index (コード差分記憶)

    /// ファイルの変更前後を比較し、L1.5インデックス（差分漢字サマリー）を生成して
    /// VaultEntryに保存する。ローカルモードで `remember()` を呼ぶ際に自動的に
    /// `codeDiff` フィールドを補完するために使用する。
    ///
    /// - Parameters:
    ///   - relativePath: 対象ファイルの相対パス
    ///   - oldSource: 変更前のソースコード
    ///   - newSource: 変更後のソースコード
    ///   - context: 変更の理由・文脈（1行）
    @discardableResult
    func recordL15Diff(
        relativePath: String,
        oldSource: String,
        newSource: String,
        context: String
    ) -> L15DiffEntry? {
        guard vaultIndex?.entries[relativePath] != nil else { return nil }

        let diff = computeL15Diff(old: oldSource, new: newSource)
        guard let diff else { return nil }

        let l1Tags = generateL1TagsFromSource(newSource, language: URL(fileURLWithPath: relativePath).pathExtension)
        let kanjiStr = l1Tags.prefix(3)
        let indexLine = "[\(kanjiStr)] | \"\(diff.beforeKanji.prefix(12))→\(diff.afterKanji.prefix(12))\" ▶ \(relativePath.split(separator:"/").suffix(2).joined(separator:"/")):L\(diff.lineRange)"

        let entry = L15DiffEntry(
            lineRange: diff.lineRange,
            beforeKanji: diff.beforeKanji,
            afterKanji: diff.afterKanji,
            context: context,
            recordedAt: Date(),
            indexLine: indexLine
        )

        vaultIndex?.entries[relativePath]?.l15Index = entry
        if let idx = vaultIndex { saveIndex(idx) }
        log("📐 L1.5記録: \(relativePath) L\(diff.lineRange) [\(diff.beforeKanji)→\(diff.afterKanji)]")
        return entry
    }

    /// 変更前後のソースを行単位で比較し、変更範囲と漢字要約を生成する。
    /// 純粋CPU処理（LLM不使用）。
    private func computeL15Diff(
        old: String,
        new: String
    ) -> (lineRange: String, beforeKanji: String, afterKanji: String)? {
        let oldLines = old.components(separatedBy: "\n")
        let newLines = new.components(separatedBy: "\n")
        guard oldLines != newLines else { return nil }

        // 変更範囲を検出（最初と最後の差異行）
        var firstDiff = 0
        var lastDiffOld = oldLines.count - 1
        var lastDiffNew = newLines.count - 1

        while firstDiff < min(oldLines.count, newLines.count),
              oldLines[firstDiff] == newLines[firstDiff] {
            firstDiff += 1
        }
        while lastDiffOld > firstDiff, lastDiffNew > firstDiff,
              oldLines[lastDiffOld] == newLines[lastDiffNew] {
            lastDiffOld -= 1
            lastDiffNew -= 1
        }
        let lineRange = "\(firstDiff + 1)-\(lastDiffNew + 1)"

        // 変更前後の漢字要約（変更行から主要キーワードを抽出）
        let oldSlice = oldLines[firstDiff...min(lastDiffOld, oldLines.count - 1)]
        let newSlice = newLines[firstDiff...min(lastDiffNew, newLines.count - 1)]

        let beforeKanji = extractChangeKanji(from: Array(oldSlice), label: "before")
        let afterKanji  = extractChangeKanji(from: Array(newSlice), label: "after")

        return (lineRange, beforeKanji, afterKanji)
    }

    /// コードスニペットから変更の漢字トポロジー要約を生成する（ルールベース）。
    private func extractChangeKanji(from lines: [String], label: String) -> String {
        let joined = lines.joined(separator: " ").lowercased()
        var tokens: [String] = []

        // 構造変化のシグナル
        if joined.contains("guard")        { tokens.append("守") }
        if joined.contains("func ")        { tokens.append("義") }
        if joined.contains("struct ") || joined.contains("class ") { tokens.append("型") }
        if joined.contains("async") || joined.contains("await")    { tokens.append("並") }
        if joined.contains("throw") || joined.contains("catch")    { tokens.append("捕") }
        if joined.contains("return")       { tokens.append("返") }
        if joined.contains("for ") || joined.contains("while ")    { tokens.append("廻") }
        if joined.contains("if ")          { tokens.append("条") }
        if joined.contains("filemanager") || joined.contains("url") { tokens.append("路") }
        if joined.contains("write") || joined.contains("read")     { tokens.append("読") }
        if joined.contains("remove") || joined.contains("delete")  { tokens.append("廃") }
        if joined.contains("rename") || joined.contains("move")    { tokens.append("移") }
        if joined.contains("import")       { tokens.append("導") }
        if joined.contains("publish") || joined.contains("@published") { tokens.append("発") }

        // 関数名・型名を抽出（最大2語）
        let identifiers = joined
            .components(separatedBy: .whitespaces)
            .filter { $0.count >= 4 && $0.count <= 20 && $0.first?.isLetter == true }
            .prefix(2)
            .map { String($0.prefix(10)) }

        let kanjiPart = tokens.prefix(4).joined()
        let idPart = identifiers.joined(separator:"+")
        let summary = kanjiPart.isEmpty ? idPart : (idPart.isEmpty ? kanjiPart : "\(kanjiPart)(\(idPart))")
        return summary.prefix(20).description
    }

    /// ソースから言語タグを取得する補助（generateL1TagsViaBitNetのpure版）。
    private func generateL1TagsFromSource(_ source: String, language ext: String) -> String {
        switch ext.lowercased() {
        case "swift": return "迅並路"
        case "rs":    return "錆並廃"
        case "ts", "tsx": return "型並発"
        case "py":    return "蛇並路"
        default:      return "码路"
        }
    }

    // MARK: - L1 Tag Bridge

    /// BitNet L1 タグ生成への橋渡し。
    private func generateL1TagsViaBitNet(source: String, language: String) async -> String {
        let lower = source.lowercased()
        var tags: [String] = []
        switch language {
        case "swift":       tags.append("[迅:1.0]")
        case "rs":          tags.append("[錆:1.0]")
        case "py":          tags.append("[蛇:1.0]")
        case "ts", "tsx":   tags.append("[型:1.0]")
        default:            tags.append("[码:1.0]")
        }
        if lower.contains("async") || lower.contains("await") { tags.append("[並:0.9]") }
        if lower.contains("secret") || lower.contains("token") { tags.append("[秘:0.9]") }
        if lower.contains("network") || lower.contains("http")  { tags.append("[網:0.8]") }
        if lower.contains("database") || lower.contains("sql")  { tags.append("[蔵:0.8]") }
        return tags.prefix(5).joined()
    }
}

// MARK: - Supporting Types

struct AbstractedFileInfo: Identifiable {
    let id = UUID()
    let name: String
    let isDirectory: Bool
    let jcrossPath: String?
    let nodeCount: Int?
    let secretCount: Int?

    var icon: String { isDirectory ? "folder.fill" : "doc.text" }
}

struct SearchResult: Identifiable {
    let id = UUID()
    let relativePath: String
    let matches: [Match]

    struct Match: Identifiable {
        let id = UUID()
        let lineNumber: Int
        let line: String
    }
}

// MARK: - JCrossCodeTranspiler Language Extension

extension JCrossCodeTranspiler.CodeLanguage {
    static func from(extension ext: String) -> JCrossCodeTranspiler.CodeLanguage {
        switch ext.lowercased() {
        case "swift": return .swift
        case "py":    return .python
        case "ts", "tsx": return .typescript
        case "js", "jsx": return .javascript
        case "rs":    return .rust
        case "go":    return .go
        case "kt":    return .kotlin
        case "java":  return .java
        default:      return .plain
        }
    }
}

// MARK: - PolymorphicJCrossTranspiler Session Extensions

extension PolymorphicJCrossTranspiler {
    func sessionNodeCount(for schemaID: String) async -> Int {
        // schemaSessions は private なので currentSchema から取得
        return 0  // TODO: expose session stats
    }
    func sessionSecretCount(for schemaID: String) async -> Int {
        return 0  // TODO: expose session stats
    }
}
