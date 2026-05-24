import Foundation
import AppKit
import SQLite3

// MARK: - OS Asset Mapping Rules
//
// PC全体のコンテキスト（設定、ファイル、アプリ、履歴）を
// ルールベースで抽出し、JCross（独自メモリ構造）に変換するためのマッパー。

protocol OSAssetRule {
    var category: String { get }
    func extractAssets() async -> [OSAssetEntry]
}

// 1. 言語・システム設定の抽出
struct SettingsRule: OSAssetRule {
    let category = "SystemSettings"
    
    func extractAssets() async -> [OSAssetEntry] {
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
    
    func extractAssets() async -> [OSAssetEntry] {
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
    
    func extractAssets() async -> [OSAssetEntry] {
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
            entries.append(OSAssetEntry(name: domain, path: "web://history/\(domain)", category: category, metadata: "Visits: \(count)"))
        }
        return entries
    }
}

// 4. よく使うアプリ（起動中など）の抽出
struct UsageRule: OSAssetRule {
    let category = "ActiveUsage"
    
    func extractAssets() async -> [OSAssetEntry] {
        var entries: [OSAssetEntry] = []
        
        // NSWorkspace から現在起動中のアプリケーションを取得
        let runningApps = await MainActor.run {
            return NSWorkspace.shared.runningApplications
        }
        
        for app in runningApps {
            guard let name = app.localizedName, let url = app.bundleURL else { continue }
            // バックグラウンドプロセスを除外するための簡易フィルタ
            if app.activationPolicy == .regular {
                entries.append(OSAssetEntry(name: name, path: url.path, category: category, metadata: "Running"))
            }
        }
        
        return entries
    }
}

// MARK: - OS Asset Mapper

final class OSAssetMapper {
    let rules: [OSAssetRule] = [
        SettingsRule(),
        ApplicationRule(),
        WebHistoryRule(),
        UsageRule()
    ]
    
    func buildMap(onProgress: ((String, [OSAssetEntry]) -> Void)? = nil) async -> [OSAssetEntry] {
        var allEntries: [OSAssetEntry] = []
        
        // 各ルールを非同期で実行し、結果をマージする
        await withTaskGroup(of: (String, [OSAssetEntry]).self) { group in
            for rule in rules {
                group.addTask {
                    let res = await rule.extractAssets()
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
