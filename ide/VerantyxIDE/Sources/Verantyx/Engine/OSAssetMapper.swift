import Foundation
import AppKit
import SQLite3

// MARK: - OS Asset Mapping Rules
//
// PC全体のコンテキスト（設定、ファイル、アプリ、履歴）を
// ルールベースで抽出し、JCross（独自メモリ構造）に変換するためのマッパー。

protocol OSAssetRule {
    var category: String { get }
    func extractAssets(
        onFile: ((String) -> Void)?,
        onIncrementalSave: ((OSAssetEntry) -> Void)?
    ) async -> [OSAssetEntry]
}

// 1. 言語・システム設定の抽出
struct SettingsRule: OSAssetRule {
    let category = "SystemSettings"
    
    func extractAssets(onFile: ((String) -> Void)? = nil, onIncrementalSave: ((OSAssetEntry) -> Void)? = nil) async -> [OSAssetEntry] {
        var entries: [OSAssetEntry] = []
        
        let language = Locale.current.language.languageCode?.identifier ?? "Unknown"
        let timeZone = TimeZone.current.identifier
        
        entries.append(OSAssetEntry(name: "Language", path: "system://locale/language", category: category, metadata: language))
        entries.append(OSAssetEntry(name: "TimeZone", path: "system://locale/timezone", category: category, metadata: timeZone))
        
        return entries
    }
}

// 2. アプリケーションの抽出
struct ApplicationRule: OSAssetRule {
    let category = "Application"
    
    func extractAssets(onFile: ((String) -> Void)? = nil, onIncrementalSave: ((OSAssetEntry) -> Void)? = nil) async -> [OSAssetEntry] {
        let fileManager = FileManager.default
        var entries: [OSAssetEntry] = []
        
        let searchPaths = [
            "/Applications",
            "/System/Applications",
            "/System/Applications/Utilities",
            fileManager.homeDirectoryForCurrentUser.appendingPathComponent("Applications").path
        ]
        
        for basePath in searchPaths {
            guard let enumerator = fileManager.enumerator(
                at: URL(fileURLWithPath: basePath),
                includingPropertiesForKeys: [.isDirectoryKey],
                options: [.skipsSubdirectoryDescendants, .skipsHiddenFiles]
            ) else { continue }
            
            for case let fileURL as URL in enumerator {
                if fileURL.pathExtension == "app" {
                    let name = fileURL.deletingPathExtension().lastPathComponent
                    onFile?(fileURL.path)
                    entries.append(OSAssetEntry(name: name, path: fileURL.path, category: category, metadata: ""))
                }
            }
        }
        
        return entries
    }
}

// 3. Web閲覧履歴の抽出
struct WebHistoryRule: OSAssetRule {
    let category = "WebFootprint"
    
    func extractAssets(onFile: ((String) -> Void)? = nil, onIncrementalSave: ((OSAssetEntry) -> Void)? = nil) async -> [OSAssetEntry] {
        let fileManager = FileManager.default
        let historyURL = fileManager.homeDirectoryForCurrentUser.appendingPathComponent("Library/Safari/History.db")
        
        guard fileManager.fileExists(atPath: historyURL.path) else { return [] }
        
        var db: OpaquePointer?
        var domainCounts: [String: Int] = [:]
        
        // 読み取り専用で開く
        if sqlite3_open_v2(historyURL.path, &db, SQLITE_OPEN_READONLY, nil) == SQLITE_OK {
            // 直近のアクセス上位ドメインを取得する単純なクエリ
            let query = """
            SELECT url FROM history_items 
            ORDER BY visit_count DESC LIMIT 200;
            """
            var statement: OpaquePointer?
            if sqlite3_prepare_v2(db, query, -1, &statement, nil) == SQLITE_OK {
                while sqlite3_step(statement) == SQLITE_ROW {
                    if let cString = sqlite3_column_text(statement, 0) {
                        let urlString = String(cString: cString)
                        if let url = URL(string: urlString), let host = url.host {
                            let cleanHost = host.replacingOccurrences(of: "www.", with: "")
                            domainCounts[cleanHost, default: 0] += 1
                        }
                    }
                }
            }
            sqlite3_finalize(statement)
        }
        sqlite3_close(db)
        
        let topDomains = domainCounts.sorted { $0.value > $1.value }.prefix(10)
        var entries: [OSAssetEntry] = []
        for (domain, count) in topDomains {
            onFile?("web://history/\(domain)")
            entries.append(OSAssetEntry(name: domain, path: "web://history/\(domain)", category: category, metadata: "Visits: \(count)"))
        }
        return entries
    }
}

// 4. よく使うアプリ（起動中など）の抽出
struct UsageRule: OSAssetRule {
    let category = "ActiveUsage"
    
    func extractAssets(onFile: ((String) -> Void)? = nil, onIncrementalSave: ((OSAssetEntry) -> Void)? = nil) async -> [OSAssetEntry] {
        var entries: [OSAssetEntry] = []
        
        // NSWorkspace から現在起動中のアプリケーションを取得
        let runningApps = await MainActor.run {
            return NSWorkspace.shared.runningApplications
        }
        
        for app in runningApps {
            guard let name = app.localizedName, let url = app.bundleURL else { continue }
            // バックグラウンドプロセスを除外するための簡易フィルタ
            if app.activationPolicy == .regular {
                onFile?(url.path)
                entries.append(OSAssetEntry(name: name, path: url.path, category: category, metadata: "Running"))
            }
        }
        
        return entries
    }
}

// 5. ユーザーディレクトリの抽出
struct UserDirectoryRule: OSAssetRule {
    let category = "UserStorage"
    let targets: [ScanTarget]
    let isBitNetModeEnabled: Bool
    let existingMap: OSAssetMap?
    
    func extractAssets(onFile: ((String) -> Void)? = nil, onIncrementalSave: ((OSAssetEntry) -> Void)? = nil) async -> [OSAssetEntry] {
        var entries: [OSAssetEntry] = []
        let fileManager = FileManager.default
        let supportedExtensions = ["swift", "ts", "tsx", "md", "js", "json", "py"]
        
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
                if fileManager.fileExists(atPath: fileURL.path, isDirectory: &isDir), isDir.boolValue {
                    continue
                }
                
                var metadata = "Source: \(target.name)"
                
                if let existing = existingMap?.entries[fileURL.path], existing.metadata.contains("BitNetSummary:") {
                    // 変換済みの場合はスキップ
                    onFile?("[変換済み] \(fileURL.path)")
                    entries.append(existing)
                    continue
                }
                
                onFile?(fileURL.path)
                
                if isBitNetModeEnabled, supportedExtensions.contains(fileURL.pathExtension.lowercased()) {
                    if let content = try? String(contentsOf: fileURL, encoding: .utf8) {
                        let snippet = String(content.prefix(1500))
                        let prompt = "Please summarize the purpose and implementation details of this file in 1-2 sentences.\n\nCode:\n\(snippet)"
                        let sysPrompt = "You are an expert AI code analyzer. Output only the short summary."
                        if let summary = await BitNetCommanderEngine.shared.generate(prompt: prompt, systemPrompt: sysPrompt) {
                            metadata += " | BitNetSummary: \(summary.trimmingCharacters(in: .whitespacesAndNewlines))"
                        }
                    }
                }
                
                let entry = OSAssetEntry(name: fileURL.lastPathComponent, path: fileURL.path, category: category, metadata: metadata)
                entries.append(entry)
                onIncrementalSave?(entry)
            }
        }
        
        return entries
    }
}

// MARK: - OS Asset Mapper

final class OSAssetMapper {
    let rules: [OSAssetRule]
    
    init(scanTargets: [ScanTarget] = [], isBitNetModeEnabled: Bool = false, existingMap: OSAssetMap? = nil) {
        var defaultRules: [OSAssetRule] = [
            SettingsRule(),
            ApplicationRule(),
            WebHistoryRule(),
            UsageRule()
        ]
        if !scanTargets.isEmpty {
            defaultRules.append(UserDirectoryRule(targets: scanTargets, isBitNetModeEnabled: isBitNetModeEnabled, existingMap: existingMap))
        }
        self.rules = defaultRules
    }
    
    func buildMap(
        onProgress: ((String, [OSAssetEntry]) -> Void)? = nil,
        onFile: ((String) -> Void)? = nil,
        onIncrementalSave: ((OSAssetEntry) -> Void)? = nil
    ) async -> [OSAssetEntry] {
        var allEntries: [OSAssetEntry] = []
        
        // 各ルールを非同期で実行し、結果をマージする
        await withTaskGroup(of: (String, [OSAssetEntry]).self) { group in
            for rule in rules {
                group.addTask {
                    let res = await rule.extractAssets(onFile: onFile, onIncrementalSave: onIncrementalSave)
                    return (rule.category, res)
                }
            }
            
            for await (category, entries) in group {
                allEntries.append(contentsOf: entries)
                onProgress?(category, allEntries)
            }
        }
        
        return allEntries
    }
}
