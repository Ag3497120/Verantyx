import Foundation
import Security

// MARK: - MCPCatalog
//
// 既知 MCP サーバーの「マニフェスト」カタログ。
// Cursor が「魔法」と呼ばれる UX の正体：
//   - サーバー名 → 必要な環境変数キー一覧 (requiredEnv)
//   - IDE はカタログを照合し自動的に API キー入力フォームを表示
//   - 入力値は Keychain に保存し、プロセス起動時に ENV として注入

struct MCPCatalogEntry: Identifiable {
    let id: String                    // 一意キー (例: "brave-search")
    let displayName: String           // UI 表示名
    let defaultCommand: String        // 既定 stdio コマンド
    let requiredEnv: [MCPEnvSpec]     // 必須環境変数定義
    let optionalEnv: [MCPEnvSpec]     // 任意環境変数定義
    let homepage: String              // APIキー取得ページ URL
    let icon: String                  // SF Symbol
}

struct MCPEnvSpec {
    let key: String                   // 環境変数名 (例: "BRAVE_API_KEY")
    let hint: String                  // UI プレースホルダ (例: "BSAxxxx...")
    let helpURL: String               // キー発行ページ URL
    let isSecret: Bool                // true → SecureField でマスク表示
}

// MARK: - Known catalog (extend as needed)

enum MCPCatalog {
    static let all: [MCPCatalogEntry] = [
        MCPCatalogEntry(
            id: "brave-search",
            displayName: "Brave Search",
            defaultCommand: "npx -y @modelcontextprotocol/server-brave-search",
            requiredEnv: [
                MCPEnvSpec(
                    key: "BRAVE_API_KEY",
                    hint: "BSA…",
                    helpURL: "https://brave.com/search/api/",
                    isSecret: true
                )
            ],
            optionalEnv: [],
            homepage: "https://brave.com/search/api/",
            icon: "magnifyingglass"
        ),
        MCPCatalogEntry(
            id: "github",
            displayName: "GitHub",
            defaultCommand: "npx -y @modelcontextprotocol/server-github",
            requiredEnv: [
                MCPEnvSpec(
                    key: "GITHUB_PERSONAL_ACCESS_TOKEN",
                    hint: "ghp_…",
                    helpURL: "https://github.com/settings/tokens",
                    isSecret: true
                )
            ],
            optionalEnv: [],
            homepage: "https://github.com/settings/tokens",
            icon: "chevron.left.forwardslash.chevron.right"
        ),
        MCPCatalogEntry(
            id: "google-drive",
            displayName: "Google Drive",
            defaultCommand: "npx -y @modelcontextprotocol/server-gdrive",
            requiredEnv: [
                MCPEnvSpec(
                    key: "GDRIVE_CLIENT_ID",
                    hint: "xxx.apps.googleusercontent.com",
                    helpURL: "https://console.cloud.google.com/",
                    isSecret: false
                ),
                MCPEnvSpec(
                    key: "GDRIVE_CLIENT_SECRET",
                    hint: "GOCSPX-…",
                    helpURL: "https://console.cloud.google.com/",
                    isSecret: true
                )
            ],
            optionalEnv: [],
            homepage: "https://console.cloud.google.com/",
            icon: "folder.fill.badge.gearshape"
        ),
        MCPCatalogEntry(
            id: "slack",
            displayName: "Slack",
            defaultCommand: "npx -y @modelcontextprotocol/server-slack",
            requiredEnv: [
                MCPEnvSpec(
                    key: "SLACK_BOT_TOKEN",
                    hint: "xoxb-…",
                    helpURL: "https://api.slack.com/apps",
                    isSecret: true
                ),
                MCPEnvSpec(
                    key: "SLACK_TEAM_ID",
                    hint: "Txxxxxxxx",
                    helpURL: "https://api.slack.com/apps",
                    isSecret: false
                )
            ],
            optionalEnv: [],
            homepage: "https://api.slack.com/apps",
            icon: "message.badge"
        ),
        MCPCatalogEntry(
            id: "puppeteer",
            displayName: "Puppeteer",
            defaultCommand: "npx -y @modelcontextprotocol/server-puppeteer",
            requiredEnv: [],
            optionalEnv: [],
            homepage: "https://github.com/modelcontextprotocol/servers",
            icon: "globe"
        ),
        MCPCatalogEntry(
            id: "filesystem",
            displayName: "Filesystem",
            defaultCommand: "npx -y @modelcontextprotocol/server-filesystem /",
            requiredEnv: [],
            optionalEnv: [],
            homepage: "https://github.com/modelcontextprotocol/servers",
            icon: "folder"
        ),
    ]

    static func find(byName name: String) -> MCPCatalogEntry? {
        let lower = name.lowercased()
        return all.first {
            $0.id == lower
            || $0.displayName.lowercased() == lower
            || lower.contains($0.id)
        }
    }
}

// MARK: - MCPKeychainStore
//
// macOS Keychain を介した API キーの安全な保存・取得・削除。
// キーは平文で UserDefaults / ディスクに書かれない。

enum MCPKeychainStore {

    private static let service = "jp.openclaw.mcp"

    // MARK: Save (add or update)
    @discardableResult
    static func save(key: String, value: String) -> Bool {
        guard let data = value.data(using: .utf8) else { return false }
        let account = key

        // Try to update first
        let query: [CFString: Any] = [
            kSecClass:       kSecClassGenericPassword,
            kSecAttrService: service,
            kSecAttrAccount: account,
        ]
        let attributes: [CFString: Any] = [kSecValueData: data]
        let status = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)

        if status == errSecItemNotFound {
            // Insert new
            var addQuery = query
            addQuery[kSecValueData] = data
            return SecItemAdd(addQuery as CFDictionary, nil) == errSecSuccess
        }
        return status == errSecSuccess
    }

    // MARK: Load
    static func load(key: String) -> String? {
        let query: [CFString: Any] = [
            kSecClass:            kSecClassGenericPassword,
            kSecAttrService:      service,
            kSecAttrAccount:      key,
            kSecReturnData:       true,
            kSecMatchLimit:       kSecMatchLimitOne,
        ]
        var result: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        guard status == errSecSuccess,
              let data = result as? Data,
              let str  = String(data: data, encoding: .utf8)
        else { return nil }
        return str
    }

    // MARK: Delete
    @discardableResult
    static func delete(key: String) -> Bool {
        let query: [CFString: Any] = [
            kSecClass:       kSecClassGenericPassword,
            kSecAttrService: service,
            kSecAttrAccount: key,
        ]
        return SecItemDelete(query as CFDictionary) == errSecSuccess
    }

    // MARK: Batch load for a server (returns env dict with Keychain values injected)
    static func resolvedEnv(for config: MCPServerConfig) -> [String: String] {
        var env = config.envVars
        // For each env var that is empty in config, try Keychain
        for key in env.keys {
            if (env[key] ?? "").isEmpty, let kv = load(key: "\(config.id).\(key)") {
                env[key] = kv
            }
        }
        return env
    }
}
