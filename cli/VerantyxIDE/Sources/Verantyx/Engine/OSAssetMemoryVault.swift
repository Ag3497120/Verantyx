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

@MainActor
final class OSAssetMemoryVault: ObservableObject {
    static let shared = OSAssetMemoryVault()
    
    @Published var assetMap: OSAssetMap?
    @Published var isScanning = false
    @Published var scanProgress: String = ""
    
    private init() {}
    
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
    
    nonisolated private func runScan() async {
        let mapper = OSAssetMapper()
        
        await MainActor.run {
            self.scanProgress = "L3.5: Scanning started..."
        }
        
        let assetArray = await mapper.buildMap { category, currentList in
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
        }
        
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
            self.isScanning = false
        }
    }
    
    nonisolated private func saveMap(_ map: OSAssetMap) {
        let url = vaultURL()
        try? FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        let text = map.toJCrossString()
        try? text.write(to: url, atomically: true, encoding: .utf8)
    }
    
    /// OSエージェントが使用するためのサマリーを返す（通信経路に<PRIVATE_OS_MEM>タグを付与しファイアウォールでブロック可能にする）
    func getProtectedAssetSummary() -> String {
        guard let map = assetMap else { return "[OS ASSET MAP: Not initialized]" }
        let summary = map.toMapString()
        return "\n<PRIVATE_OS_MEM>\n\(summary)\n</PRIVATE_OS_MEM>\n"
    }
}
