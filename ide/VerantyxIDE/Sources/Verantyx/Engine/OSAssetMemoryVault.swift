import Foundation
import Combine

// MARK: - OS Asset Memory Vault (L2.5 for System)
//
// 既存の L25IndexEngine (ソースコード地図) とは完全に独立したシステム。
// Mac内のアプリケーションや主要なユーザー環境を非同期にスキャンし、
// .openclaw/memory/os_assets.jcross に隔離・保存する。
//
// ⚠️ この記憶は通常のコンテキストには結合されず、
// エージェントが「システム資産を利用する」判断をした場合のみクエリ可能となる。
// （クラウドへの誤送信を防ぐHard Firewallによって保護される）

struct OSAssetEntry: Codable, Identifiable {
    let id: UUID
    let name: String
    let path: String
    let category: String // "Application", "Utility", "SystemSettings", "WebFootprint", etc.
    let metadata: String
    let indexLine: String
    
    init(id: UUID = UUID(), name: String, path: String, category: String, metadata: String) {
        self.id = id
        self.name = name
        self.path = path
        self.category = category
        self.metadata = metadata
        self.indexLine = "[\(category)] \(name) -> \(path) (\(metadata))"
    }
}

struct OSAssetMap: Codable {
    var entries: [String: OSAssetEntry]
    var generatedAt: Date
    
    func toJCrossString() -> String {
        var lines = [
            ";;; OS ASSET MAP (Isolated)",
            ";;; GENERATED_AT: \(generatedAt.timeIntervalSince1970)",
            ""
        ]
        
        for (path, entry) in entries {
            lines.append("■ NODE OS_ASSET \(path)")
            lines.append("NAME: \(entry.name)")
            lines.append("CATEGORY: \(entry.category)")
            if !entry.metadata.isEmpty {
                lines.append("METADATA: \(entry.metadata)")
            }
            lines.append("INDEX: \(entry.indexLine)")
            lines.append("")
        }
        return lines.joined(separator: "\n")
    }
    
    func toMapString(maxEntries: Int = 100) -> String {
        let sorted = entries.values.sorted { $0.category > $1.category }.prefix(maxEntries)
        var lines = ["[OS ASSET MAP — \(entries.count) items]", ""]
        for entry in sorted {
            lines.append("  \(entry.indexLine)")
        }
        return lines.joined(separator: "\n")
    }
}

struct ScanTarget: Identifiable, Codable, Equatable {
    var id = UUID()
    var url: URL
    var name: String
    var isEnabled: Bool
    var scanDepth: Int
}

@MainActor
final class OSAssetMemoryVault: ObservableObject {
    static let shared = OSAssetMemoryVault()
    
    @Published var assetMap: OSAssetMap?
    @Published var isScanning = false
    @Published var scanProgress: String = ""
    @Published var scanProgressValue: Double = 0.0
    @Published var conversionLog: [String] = []
    @Published var estimatedTimeRemaining: String = ""
    @Published var currentProcessingFile: String = ""
    
    @Published var totalFilesToScan: Int = 0
    @Published var processedFilesCount: Int = 0
    
    @Published var scanTargets: [ScanTarget] = []
    @Published var isBitNetModeEnabled = false
    
    private init() {
        setupDefaultScanTargets()
        loadMapFromDisk()
    }
    
    private func setupDefaultScanTargets() {
        let fileManager = FileManager.default
        let home = fileManager.homeDirectoryForCurrentUser
        
        var targets: [ScanTarget] = []
        if let contents = try? fileManager.contentsOfDirectory(at: home, includingPropertiesForKeys: [.isDirectoryKey], options: [.skipsHiddenFiles]) {
            let sortedContents = contents.sorted { $0.lastPathComponent < $1.lastPathComponent }
            for url in sortedContents {
                var isDir: ObjCBool = false
                if fileManager.fileExists(atPath: url.path, isDirectory: &isDir), isDir.boolValue {
                    targets.append(ScanTarget(
                        url: url,
                        name: url.lastPathComponent,
                        isEnabled: false,
                        scanDepth: 3
                    ))
                }
            }
        }
        self.scanTargets = targets
    }
    
    /// 独立した保存先パス
    nonisolated private func vaultURL() -> URL {
        let home = FileManager.default.homeDirectoryForCurrentUser
        return home.appendingPathComponent(".openclaw/memory/os_assets.jcross")
    }
    
    /// バックグラウンドでアプリケーションフォルダ等をスキャンする
    func scanBackground() {
        guard !isScanning else { return }
        isScanning = true
        
        Task.detached(priority: .background) { [weak self] in
            guard let self else { return }
            await self.runScan()
        }
    }
    
    func deleteMap() {
        let url = vaultURL()
        let jsonURL = url.deletingPathExtension().appendingPathExtension("json")
        try? FileManager.default.removeItem(at: url)
        try? FileManager.default.removeItem(at: jsonURL)
        Task { @MainActor in
            self.assetMap = nil
            self.scanProgress = "L3.5: Map deleted."
        }
    }
    
    private func loadMapFromDisk() {
        let jsonURL = vaultURL().deletingPathExtension().appendingPathExtension("json")
        guard let data = try? Data(contentsOf: jsonURL),
              let map = try? JSONDecoder().decode(OSAssetMap.self, from: data) else {
            return
        }
        self.assetMap = map
        self.scanProgress = "L3.5: Loaded existing map (\(map.entries.count) items)"
        self.scanProgressValue = 1.0
    }
    
    func diffUpdateMap() {
        // Differential update stub: scans and overwrites/updates differences.
        scanBackground()
    }
    
    nonisolated private func countExpectedFiles(for targets: [ScanTarget]) -> Int {
        var count = 0
        let fileManager = FileManager.default
        for target in targets where target.isEnabled {
            guard let enumerator = fileManager.enumerator(
                at: target.url,
                includingPropertiesForKeys: [.isDirectoryKey],
                options: [.skipsHiddenFiles, .skipsPackageDescendants]
            ) else { continue }
            
            for case let fileURL as URL in enumerator {
                let depth = fileURL.pathComponents.count - target.url.pathComponents.count
                if depth > target.scanDepth {
                    enumerator.skipDescendants()
                    continue
                }
                var isDir: ObjCBool = false
                if fileManager.fileExists(atPath: fileURL.path, isDirectory: &isDir), !isDir.boolValue {
                    count += 1
                }
            }
        }
        return count
    }
    
    nonisolated private func runScan() async {
        let targets = await MainActor.run { self.scanTargets }
        let isBitNetEnabled = await MainActor.run { self.isBitNetModeEnabled }
        let existingMap = await MainActor.run { self.assetMap }
        let mapper = OSAssetMapper(scanTargets: targets, isBitNetModeEnabled: isBitNetEnabled, existingMap: existingMap)
        
        await MainActor.run {
            self.scanProgress = "L3.5: Calculating total files..."
            self.scanProgressValue = 0.0
            self.conversionLog = []
            self.estimatedTimeRemaining = "Calculating..."
            self.currentProcessingFile = ""
            self.totalFilesToScan = 0
            self.processedFilesCount = 0
        }
        
        let fileCount = countExpectedFiles(for: targets)
        let estimatedTotal = Double(fileCount > 0 ? fileCount + 50 : 250) // +50 for other rules
        let startTime = Date()
        var processedCount = 0
        
        await MainActor.run {
            self.totalFilesToScan = Int(estimatedTotal)
            self.scanProgress = "L3.5: Scanning started..."
        }
        
        let assetArray = await mapper.buildMap(
            onProgress: { category, currentList in
                Task {
                    var newEntries: [String: OSAssetEntry] = [:]
                    for entry in currentList {
                        newEntries[entry.path] = entry
                    }
                    let map = OSAssetMap(entries: newEntries, generatedAt: Date())
                    self.saveMap(map)
                    
                    await MainActor.run {
                        self.assetMap = map
                        self.scanProgress = "L3.5: \(category) Indexed (\(currentList.count) items)"
                    }
                }
            },
            onFile: { file in
                Task { @MainActor in
                    self.currentProcessingFile = file
                    processedCount += 1
                    self.processedFilesCount = processedCount
                    self.scanProgressValue = min(Double(processedCount) / estimatedTotal, 0.99)
                    
                    let elapsed = Date().timeIntervalSince(startTime)
                    if processedCount > 10 {
                        let speed = Double(processedCount) / elapsed
                        let remain = max((estimatedTotal - Double(processedCount)) / speed, 0)
                        self.estimatedTimeRemaining = String(format: "%.0fs", remain)
                    }
                    
                    self.conversionLog.append("✓ JCross: \(file)")
                    if self.conversionLog.count > 100 {
                        self.conversionLog.removeFirst(50)
                    }
                }
            },
            onIncrementalSave: { newEntry in
                Task {
                    let currentMap = await MainActor.run { self.assetMap }
                    var currentEntries = currentMap?.entries ?? [:]
                    currentEntries[newEntry.path] = newEntry
                    let map = OSAssetMap(entries: currentEntries, generatedAt: Date())
                    self.saveMap(map)
                    await MainActor.run {
                        self.assetMap = map
                    }
                }
            }
        )
        
        var finalEntries: [String: OSAssetEntry] = [:]
        for entry in assetArray {
            finalEntries[entry.path] = entry
        }
        
        // 2. IdentityExtractor (プロジェクト構造の軽量スキャンなど) は別途呼び出す
        await IdentityExtractor.shared.extractAndInjectProfile()
        
        let map = OSAssetMap(entries: finalEntries, generatedAt: Date())
        self.saveMap(map)
        
        await MainActor.run {
            self.assetMap = map
            self.scanProgress = ""
            self.scanProgressValue = 1.0
            self.currentProcessingFile = "Completed"
            self.estimatedTimeRemaining = "0s"
            self.isScanning = false
        }
    }
    
    nonisolated private func saveMap(_ map: OSAssetMap) {
        let url = vaultURL()
        try? FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        let text = map.toJCrossString()
        try? text.write(to: url, atomically: true, encoding: .utf8)
        
        let jsonURL = url.deletingPathExtension().appendingPathExtension("json")
        if let jsonData = try? JSONEncoder().encode(map) {
            try? jsonData.write(to: jsonURL, options: .atomic)
        }
    }
    
    /// OSエージェントが使用するためのサマリーを返す（通信経路に<PRIVATE_OS_MEM>タグを付与しファイアウォールでブロック可能にする）
    func getProtectedAssetSummary() -> String {
        guard let map = assetMap else { return "[OS ASSET MAP: Not initialized]" }
        let summary = map.toMapString()
        return "\n<PRIVATE_OS_MEM>\n\(summary)\n</PRIVATE_OS_MEM>\n"
    }

    /// OSエージェントが使用するための画像ベースのサマリーを返す（Attention Scatterを防ぐ）
    @MainActor
    func getProtectedAssetSummaryImage() -> (textAnchor: String, imageData: Data?) {
        guard let map = assetMap else { 
            return ("[OS ASSET MAP: Not initialized]", nil) 
        }
        
        let pngData = KanjiTopologyRenderer.renderToPNG(map: map)
        let anchor = "\n<PRIVATE_OS_MEM_IMAGE>\n[L3.5 OS Asset Map Kanji Topology Image Attached]\n</PRIVATE_OS_MEM_IMAGE>\n"
        
        return (anchor, pngData)
    }

    /// Self-initializes the map on first use instead of requiring a human
    /// to have already clicked "scan" in Settings first. Before this,
    /// `osAssetQuery` on a fresh install always returned
    /// "[OS ASSET MAP: Not initialized]" no matter what was asked, since
    /// nothing ever triggered a scan automatically.
    private func ensureScanned() async {
        if assetMap != nil { return }
        if !isScanning {
            isScanning = true
            await runScan()
        } else {
            while isScanning {
                try? await Task.sleep(nanoseconds: 200_000_000)
            }
        }
    }

    /// 特定のカテゴリ（またはキーワード）に合致するOS Assetの詳細一覧（L3.5）を返す
    func queryCategory(_ query: String) async -> String {
        await ensureScanned()
        guard let map = assetMap else {
            return "[OS ASSET MAP: scan attempted but produced no data]"
        }
        let lowerQuery = query.lowercased()
        let matched = map.entries.values.filter { 
            $0.category.lowercased().contains(lowerQuery) || 
            $0.name.lowercased().contains(lowerQuery) 
        }
        
        if matched.isEmpty {
            return "[OS ASSET DETAILS: No matches found for '\(query)']"
        }
        
        var lines = ["[OS ASSET DETAILS FOR '\(query)' — \(matched.count) items]"]
        for entry in matched.sorted(by: { $0.category < $1.category }) {
            lines.append("  \(entry.indexLine)")
        }
        return lines.joined(separator: "\n")
    }
}
