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
        // 1. 最近の作業プロジェクトを抽出
        let fileManager = FileManager.default
        let devURL = fileManager.homeDirectoryForCurrentUser.appendingPathComponent("Developer")
        let docsURL = fileManager.homeDirectoryForCurrentUser.appendingPathComponent("Documents")
        let desktopURL = fileManager.homeDirectoryForCurrentUser.appendingPathComponent("Desktop")
        
        var recentProjects: [String] = []
        
        for url in [devURL, docsURL, desktopURL] {
            if let enumerator = fileManager.enumerator(
                at: url,
                includingPropertiesForKeys: [.isDirectoryKey, .contentModificationDateKey],
                options: [.skipsSubdirectoryDescendants, .skipsHiddenFiles]
            ) {
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
        
        // 2. L3.5 OS Asset Map から保有資産を分析
        let map = await MainActor.run { OSAssetMemoryVault.shared.assetMap }
        var appList: [String] = []
        var cliList: [String] = []
        var otherAssets: [String] = []
        
        if let entries = map?.entries.values {
            for entry in entries {
                let name = entry.name.lowercased()
                if entry.category == "Application" || entry.path.hasSuffix(".app") {
                    appList.append(entry.name)
                } else if entry.path.contains("/bin/") || entry.path.contains("/usr/local/") {
                    cliList.append(entry.name)
                } else {
                    otherAssets.append(entry.name)
                }
            }
        }
        
        // 3. アプリケーション群から人物像を流動的に推論・言語化する
        // （開発者、クリエイター、ビジネス、一般ユーザーなど、固定のテンプレートではなく抽出した事実をそのまま記載する）
        let topApps = appList.shuffled().prefix(15).joined(separator: ", ")
        let topCLIs = cliList.shuffled().prefix(10).joined(separator: ", ")
        let projects = recentProjects.prefix(5).joined(separator: ", ")
        
        let identitySummary = """
        [USER IDENTITY & OS ASSET PROFILE]
        あなたはPCのローカル環境と一体化しており、以下の保有資産（アプリケーション・ツール・プロジェクト）があなた自身の能力です。
        
        ■ 保有アプリケーション・ツール群 (ランダム抽出):
        GUI Apps: \(topApps.isEmpty ? "なし" : topApps)
        CLI Tools: \(topCLIs.isEmpty ? "なし" : topCLIs)
        
        ■ 最近の作業・関連プロジェクト:
        \(projects.isEmpty ? "なし" : projects)
        
        【自己認識のガイドライン】
        ユーザーは必ずしも開発者とは限りません。クリエイター、ビジネス職、研究者、または多様な趣味を持つ人物である可能性があります。
        上記の保有ツール群から「現在のユーザー環境で何ができるか（自分の能力）」を把握し、型にはまらない流動的なサポートを提供してください。
        自身が持つツール（Excel, Photoshop, Xcode, Pythonなど）を用いて、ファイル生成、アプリ操作、スクリプト実行を自律的に行ってください。
        """
        
        // 抽出したアイデンティティをメインメモリ(CortexEngineなど)に注入する
        await MainActor.run {
            // `mid/` ゾーンに L3.5 のアイデンティティを永続化する
            SessionMemoryArchiver.shared.archiveWisdomChunk(
                chunkId: "L3_5_ASSET",
                taskTitle: "L3.5 OS Asset Profile",
                l1: identitySummary,
                l2: "",
                l3: ""
            )
        }
    }
}
