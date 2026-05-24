import Foundation

// MARK: - GatekeeperMCPServer
//
// Gatekeeper Mode の MCP サーバー。
// 外部 API (Claude/GPT) がこのサーバーのツールを呼び出すことで
// ファイル情報を取得・書き込みを行う。
//
// 外部 API が直接触れるのは「このサーバー経由のJCross IR」のみ。
// 実ファイルシステムへの直接アクセスは一切不可。
//
// MCP Tool Definitions:
//   read_file(path)           → JCross IR テキスト
//   list_directory(path)      → 抽象化ファイルツリー
//   search_code(query)        → JCross IR 内の検索結果
//   write_diff(path, jcross)  → 逆変換して実ファイルへ書き込み
//   get_project_structure()   → プロジェクト全体の抽象化構造

@MainActor
final class GatekeeperMCPServer {

    static let shared = GatekeeperMCPServer()

    private let state  = GatekeeperModeState.shared
    private var vault: JCrossVault { state.vault }

    // MARK: - MCP Tool Schema (Claude に渡すツール定義)

    static let toolDefinitions: [[String: Any]] = [
        [
            "name": "gk_read_file",
            "description": """
            Read a file from the workspace. Returns JCross IR (obfuscated intermediate representation).
            All identifiers are replaced with node IDs. Secrets are fully redacted.
            You MUST use this tool to read any file — direct filesystem access is disabled.
            """,
            "input_schema": [
                "type": "object",
                "properties": [
                    "path": ["type": "string", "description": "Relative path from workspace root (e.g. 'src/AppState.swift')"]
                ],
                "required": ["path"]
            ]
        ],
        [
            "name": "gk_list_directory",
            "description": """
            List files and directories at the given path.
            Returns an abstracted view showing node counts and secret counts per file.
            Use "" or "." for workspace root.
            """,
            "input_schema": [
                "type": "object",
                "properties": [
                    "path": ["type": "string", "description": "Relative path to list (empty string for root)"]
                ],
                "required": ["path"]
            ]
        ],
        [
            "name": "gk_search_code",
            "description": """
            Search the codebase for a query string within JCross IR content.
            Returns matching lines with file paths and line numbers.
            Searches across all files in the JCross Vault.
            """,
            "input_schema": [
                "type": "object",
                "properties": [
                    "query": ["type": "string", "description": "Search term (searches JCross IR content)"]
                ],
                "required": ["query"]
            ]
        ],
        [
            "name": "gk_write_diff",
            "description": """
            Write modified JCross IR back to the workspace.
            The local LLM will reverse-transpile the JCross IR back to real source code.
            Provide the COMPLETE modified JCross content for the file.
            Preserve ALL node IDs (⟨...⟩ style) and secret tokens (「...」 style) exactly.
            """,
            "input_schema": [
                "type": "object",
                "properties": [
                    "path":    ["type": "string", "description": "Relative path of the file to modify"],
                    "content": ["type": "string", "description": "Complete modified JCross IR content"]
                ],
                "required": ["path", "content"]
            ]
        ],
        [
            "name": "gk_get_project_structure",
            "description": "Get an overview of the entire project structure with file counts and node statistics.",
            "input_schema": [
                "type": "object",
                "properties": [:],
                "required": []
            ]
        ]
    ]

    // MARK: - Tool Dispatch

    /// MCP ツール呼び出しを処理して結果を返す
    func dispatch(toolName: String, input: [String: Any]) async -> MCPToolResult {
        guard state.isEnabled else {
            return .error(AppLanguage.shared.t("Gatekeeper Mode is disabled. Please enable it from Settings.", "Gatekeeper Mode が無効です。Settings から有効化してください。"))
        }

        switch toolName {
        case "gk_read_file":
            return await toolReadFile(input: input)

        case "gk_list_directory":
            return await toolListDirectory(input: input)

        case "gk_search_code":
            return await toolSearchCode(input: input)

        case "gk_write_diff":
            return await toolWriteDiff(input: input)

        case "gk_get_project_structure":
            return await toolGetProjectStructure()

        default:
            return .error("Unknown Gatekeeper tool: \(toolName)")
        }
    }

    // MARK: - Tool: read_file

    private func toolReadFile(input: [String: Any]) async -> MCPToolResult {
        guard let path = input["path"] as? String else {
            return .error(AppLanguage.shared.t("path parameter is required", "path パラメータが必要です"))
        }

        guard let result = vault.read(relativePath: path) else {
            // Vault にない場合: まだ変換されていないか、対象外ファイル
            return .error("""
            ファイルが Vault に見つかりません: \(path)
            このファイルはまだ JCross 変換されていないか、変換対象外です。
            gk_list_directory で利用可能なファイルを確認してください。
            """)
        }

        // アクセスログ記録
        state.logAccess(
            tool: "read_file",
            path: path,
            nodesExposed: result.entry.nodeCount,
            secretsRedacted: result.entry.secretCount
        )

        let header = """
        // === Gatekeeper JCross IR ===
        // File: \(path)
        // Nodes: \(result.entry.nodeCount) | Secrets redacted: \(result.entry.secretCount)
        // Schema: \(result.entry.schemaSessionID.prefix(8))
        // Instructions: \(result.schema.schemaInstructions().components(separatedBy: "\n").prefix(5).joined(separator: "\n// "))
        // ================================
        
        """

        return .text(header + result.jcrossContent)
    }

    // MARK: - Tool: list_directory

    private func toolListDirectory(input: [String: Any]) async -> MCPToolResult {
        let path = (input["path"] as? String) ?? ""
        let items = vault.listDirectory(relativePath: path == "." ? "" : path)

        if items.isEmpty {
            return .text(AppLanguage.shared.t("(Empty directory or path not found: '\\(path)')", "(空のディレクトリ、またはパスが見つかりません: '\\(path)')"))
        }

        var lines = ["📁 \(path.isEmpty ? "<workspace root>" : path)", ""]
        for item in items {
            if item.isDirectory {
                lines.append("  📁 \(item.name)/")
            } else {
                let nodeInfo = item.nodeCount.map { " [\($0) nodes" } ?? ""
                let secretInfo = (item.secretCount ?? 0) > 0 ? ", \(item.secretCount!) secrets redacted]" : (item.nodeCount != nil ? "]" : "")
                lines.append("  📄 \(item.name)\(nodeInfo)\(secretInfo)")
            }
        }

        state.logAccess(tool: "list_directory", path: path, nodesExposed: 0, secretsRedacted: 0)
        return .text(lines.joined(separator: "\n"))
    }

    // MARK: - Tool: search_code

    private func toolSearchCode(input: [String: Any]) async -> MCPToolResult {
        guard let query = input["query"] as? String else {
            return .error(AppLanguage.shared.t("query parameter is required", "query パラメータが必要です"))
        }

        let results = vault.search(query: query)
        if results.isEmpty {
            return .text(AppLanguage.shared.t("No results found: '\\(query)'", "検索結果なし: '\\(query)'"))
        }

        var lines = ["🔍 검색: '\(query)' — \(results.count) ファイルでヒット", ""]
        for r in results {
            lines.append("📄 \(r.relativePath)")
            for match in r.matches {
                lines.append("   L\(match.lineNumber): \(match.line)")
            }
            lines.append("")
        }

        state.logAccess(tool: "search_code", path: query, nodesExposed: 0, secretsRedacted: 0)
        return .text(lines.joined(separator: "\n"))
    }

    // MARK: - Tool: write_diff

    private func toolWriteDiff(input: [String: Any]) async -> MCPToolResult {
        guard let path    = input["path"]    as? String,
              let content = input["content"] as? String
        else {
            return .error(AppLanguage.shared.t("path and content parameters are required", "path と content パラメータが必要です"))
        }

        let transpiler = PolymorphicJCrossTranspiler.shared
        do {
            let restored = try await vault.writeDiff(
                jcrossDiff: content,
                relativePath: path,
                transpiler: transpiler
            )

            state.logAccess(
                tool: "write_diff",
                path: path,
                nodesExposed: 0,
                secretsRedacted: 0
            )

            return .text("""
            ✅ ファイル書き込み完了: \(path)
            逆変換後の文字数: \(restored.count) chars
            
            Vault が差分更新されました。
            """)
        } catch {
            return .error(AppLanguage.shared.t("Write failed: \\(error.localizedDescription)", "書き込み失敗: \\(error.localizedDescription)"))
        }
    }

    // MARK: - Tool: get_project_structure

    private func toolGetProjectStructure() async -> MCPToolResult {
        let items = vault.listDirectory(relativePath: "")
        let status = vault.vaultStatus

        var totalNodes = 0
        var totalSecrets = 0
        var fileCount = 0

        for item in items where !item.isDirectory {
            totalNodes   += item.nodeCount ?? 0
            totalSecrets += item.secretCount ?? 0
            fileCount    += 1
        }

        let statusStr: String
        switch status {
        case .ready(let count, let date):
            statusStr = "✅ Ready — \(count) ファイル変換済み (最終更新: \(date.formatted()))"
        case .converting(let progress, let file):
            statusStr = "🔄 変換中 \(Int(progress * 100))% — \(file)"
        case .notInitialized:
            statusStr = "⚠️ 未初期化"
        case .error(let msg):
            statusStr = "❌ \(msg)"
        }

        state.logAccess(tool: "get_project_structure", path: "/", nodesExposed: 0, secretsRedacted: 0)

        return .text("""
        📊 プロジェクト概要 (JCross Vault)
        
        ステータス: \(statusStr)
        合計ノード数: \(totalNodes)
        削除済みシークレット: \(totalSecrets)
        
        利用可能なツール:
          gk_read_file(path)          — ファイル内容を JCross IR で取得
          gk_list_directory(path)     — ディレクトリ一覧
          gk_search_code(query)       — コード検索
          gk_write_diff(path,content) — 変更を逆変換して書き込み
        
        ⚠️ 注意: 実際のソースコードは見えません。
        JCross IR のノード ID (例: _JCROSS_核_1_) のみが公開されています。
        """)
    }
}

// MARK: - MCPToolResult

enum MCPToolResult {
    case text(String)
    case error(String)

    var content: String {
        switch self {
        case .text(let t):  return t
        case .error(let e): return "❌ Error: \(e)"
        }
    }

    var isError: Bool {
        if case .error = self { return true }
        return false
    }

    /// Claude API の tool_result フォーマットに変換
    func toClaudeToolResult(toolUseId: String) -> [String: Any] {
        [
            "type": "tool_result",
            "tool_use_id": toolUseId,
            "content": content,
            "is_error": isError
        ]
    }
}
