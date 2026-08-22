import Foundation
import SQLite3

// MARK: - User Profiler (Meta-Cognition Data Source)
//
// ユーザーのローカル環境（例：Safariの履歴）を軽量にスキャンし、
// Gemini, ChatGPT などの強力なクラウドAIリソースをユーザーが持っているか（頻繁にアクセスしているか）を判定する。
// この情報は、OSエージェントがタスクを自身で処理するか、ブラウザを操作してクラウドAIに委譲するかを
// 自律的に決定するための「メタ認知アンカー」のコンテキストとして利用される。

@MainActor
final class UserProfiler {
    static let shared = UserProfiler()
    
    @Published var availableCloudAssets: [String] = []
    
    private init() {}
    
    /// バックグラウンドでSafariの履歴データベースにアクセスし、利用頻度の高いAIサービスを抽出する
    func extractCloudAssets() {
        Task.detached(priority: .background) { [weak self] in
            let assets = self?.scanSafariHistory() ?? []
            await MainActor.run {
                self?.availableCloudAssets = assets
            }
        }
    }
    
    nonisolated private func scanSafariHistory() -> [String] {
        let fileManager = FileManager.default
        let historyURL = fileManager.homeDirectoryForCurrentUser.appendingPathComponent("Library/Safari/History.db")
        
        // SQLite データベースの読み取り権限がない場合はスキップするか、デフォルトアセットを返す
        guard fileManager.fileExists(atPath: historyURL.path) else { return [] }
        
        var db: OpaquePointer?
        var assets = Set<String>()
        
        // 読み取り専用で開く
        if sqlite3_open_v2(historyURL.path, &db, SQLITE_OPEN_READONLY, nil) == SQLITE_OK {
            // 最近のアクセス履歴から特定のドメインをカウント
            let query = """
            SELECT url FROM history_items 
            WHERE url LIKE '%gemini.google.com%' OR url LIKE '%chatgpt.com%' OR url LIKE '%claude.ai%'
            LIMIT 500;
            """
            var statement: OpaquePointer?
            if sqlite3_prepare_v2(db, query, -1, &statement, nil) == SQLITE_OK {
                while sqlite3_step(statement) == SQLITE_ROW {
                    if let cString = sqlite3_column_text(statement, 0) {
                        let url = String(cString: cString)
                        if url.contains("gemini.google.com") { assets.insert("Gemini (Google)") }
                        if url.contains("chatgpt.com") { assets.insert("ChatGPT (OpenAI)") }
                        if url.contains("claude.ai") { assets.insert("Claude (Anthropic)") }
                    }
                }
            }
            sqlite3_finalize(statement)
        }
        sqlite3_close(db)
        
        // 万が一SQLiteのアクセス権がなくても、システムとして一般的に使えるアセットは含める
        var finalAssets = Array(assets)
        if finalAssets.isEmpty {
            finalAssets.append("Safari Browser")
        }
        return finalAssets
    }
}
