import Foundation

// MARK: - Identity Extractor
//
// 独立した OS Asset スキャン時に呼び出され、
// 「ユーザーのアイデンティティ、嗜好、現在のプロジェクト」などを抽出し、
// メインの CortexEngine (L1記憶) へ注入するためのプロファイラー。
// OSアセット自体は分離されるが、ここで抽出された「コンテキスト」のみが
// 通常会話へ安全に統合される。

@MainActor
final class IdentityExtractor {
    static let shared = IdentityExtractor()
    
    private init() {}
    
    /// OS領域をスキャンしてプロフィールを抽出し、CortexEngineに注入する
    nonisolated func extractAndInjectProfile() async {
        // 例: ~/Developer や ~/Documents の直下を浅く見て、プロジェクト名を取得
        let fileManager = FileManager.default
        let devURL = fileManager.homeDirectoryForCurrentUser.appendingPathComponent("Developer")
        let docsURL = fileManager.homeDirectoryForCurrentUser.appendingPathComponent("Documents")
        
        var recentProjects: [String] = []
        
        for url in [devURL, docsURL] {
            if let enumerator = fileManager.enumerator(
                at: url,
                includingPropertiesForKeys: [.isDirectoryKey, .contentModificationDateKey],
                options: [.skipsSubdirectoryDescendants, .skipsHiddenFiles]
            ) {
                // 更新日時が最近のフォルダをトッププロジェクトとみなす
                var candidates: [(String, Date)] = []
                for case let fileURL as URL in enumerator {
                    if let values = try? fileURL.resourceValues(forKeys: Set([.isDirectoryKey, .contentModificationDateKey])),
                       values.isDirectory == true,
                       let modDate = values.contentModificationDate {
                        candidates.append((fileURL.lastPathComponent, modDate))
                    }
                }
                let sorted = candidates.sorted { $0.1 > $1.1 }.prefix(3)
                recentProjects.append(contentsOf: sorted.map { $0.0 })
            }
        }
        
        let identitySummary = """
        [USER IDENTITY & CONTEXT]
        The user is likely a developer working on the following recent projects:
        \(recentProjects.joined(separator: ", "))
        This information is automatically extracted to personalize your responses.
        """
        
        // 抽出したアイデンティティをメインメモリ(CortexEngineなど)に注入する
        await MainActor.run {
            // CortexEngineのSystem Message等として登録
            // アプリ起動時やセッション生成時に読み込ませる仕組みがあればそこに追記
            UserDefaults.standard.set(identitySummary, forKey: "extracted_user_identity")
        }
    }
}
