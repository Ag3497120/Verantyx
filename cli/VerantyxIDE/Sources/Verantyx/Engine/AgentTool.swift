import Foundation
import SwiftUI
#if canImport(AppKit)
import AppKit
#endif

// MARK: - AgentTool
// Tool definitions that the AI can emit in its response.
// Parsed from a clean bracket-based syntax that local LLMs can follow reliably.

enum AgentTool {
    // ── File system ──────────────────────────────────────────────────────────
    case makeDir(String)
    case writeFile(path: String, content: String)
    case runCommand(String)
    case runCognitive(command: String, expect: String, doubt: Double) // NEW: Brain-Synced Terminal execution
    case setWorkspace(String)
    case done(message: String)
    case readFile(String)
    case listDir(String)                          // NEW: tree-style directory listing
    case editLines(path: String,                  // NEW: partial line-range replacement
                   startLine: Int,
                   endLine: Int,
                   newContent: String)
    // ── Web / Grounding ──────────────────────────────────────────────────────
    case browse(url: String)
    case search(query: String)
    case searchMulti(query: String)               // NEW: parallel top-3 URLs + synthesis
    case evalJS(script: String)
    case openSafari(url: String)
    case openChrome(url: String)
    case visionBrowse(url: String)                // NEW: vision based navigation
    case visionSearchFlow(query: String)          // NEW: visual multi-frame search flow
    case visionSnapshot                           // NEW: manual screenshot update
    case visionAct(action: String)                // NEW: vision UI interaction
    // ── JCross Memory ────────────────────────────────────────────────────────
    case jcrossQuery(String)                      // NEW: recall from CortexEngine
    case jcrossStore(key: String, value: String)  // NEW: remember to CortexEngine
    // ── Git / Safety ─────────────────────────────────────────────────────────
    case gitCommit(String)                        // NEW: git add -A && git commit -m
    case gitRestore(String)                       // NEW: git restore <path>
    case askHuman(String)                         // NEW: Yield — request human input
    // ── Self-Fix pipeline ────────────────────────────────────────────────────
    case applyPatch(relativePath: String, content: String)
    case buildIDE
    case restartIDE
    // ── Swarm Execution ──────────────────────────────────────────────────────
    case swarmExecute(String)                     // SWARM_EXECUTE: delegate to Swarm Engine
    // ── Self-Admin (JARVIS) ──────────────────────────────────────────────────
    case setSetting(key: String, value: String)       // SET_SETTING: key=value
    case addMCPServer(name: String, command: String, mode: String)  // ADD_MCP_SERVER
    case removeMCPServer(name: String)                // REMOVE_MCP_SERVER: name
    case setModel(String)                             // SET_MODEL: model-id
    case pullModel(String)                            // PULL_MODEL: model-id (ollama pull)
    // ── Dynamic MCP tool call ────────────────────────────────────────────────
    case mcpCall(server: String, tool: String, arguments: [String: Any])  // MCP_CALL
    // ── Skill Library (Voyager) ──────────────────────────────────────────────
    case forgeSkill(name: String, description: String, tags: [String], payload: [String])  // FORGE_SKILL
    case useSkill(name: String, args: [String: String])                                     // USE_SKILL
}

// MARK: - AgentToolCall (result wrapper)

struct AgentToolCall: Identifiable {
    let id = UUID()
    let tool: AgentTool
    var result: String = ""
    var succeeded: Bool = true

    var displayLabel: String {
        switch tool {
        case .makeDir(let p):               return "mkdir \(p)"
        case .writeFile(let p, _):          return "write → \(p)"
        case .runCommand(let cmd):          return "$ \(cmd)"
        case .runCognitive(let cmd, _, _):  return "🧠$ \(cmd)"
        case .setWorkspace(let p):          return "workspace: \(p)"
        case .done(let m):                  return "✓ \(m)"
        case .readFile(let p):              return "read ← \(p)"
        case .listDir(let p):               return "ls \(p)"
        case .editLines(let p, let s, let e, _): return "edit \(p):\(s)-\(e)"
        case .browse(let url):              return "🌐 browse \(url)"
        case .search(let q):               return "🔍 search: \(q)"
        case .searchMulti(let q):          return "🔍× search: \(q)"
        case .evalJS(let s):               return "⚡ eval_js: \(s.prefix(40))"
        case .openSafari(let url):         return "🧡 safari: \(url)"
        case .openChrome(let url):         return "🟢 chrome: \(url)"
        case .visionBrowse(let url):       return "👁️ vision_browse: \(url)"
        case .visionSearchFlow(let q):     return "👁️ vision_search: \(q)"
        case .visionSnapshot:              return "👁️ vision_snapshot"
        case .visionAct(let action):       return "👁️ vision_act: \(action)"
        case .jcrossQuery(let q):          return "🧠 jcross_query: \(q)"
        case .jcrossStore(let k, _):       return "🧠 jcross_store: \(k)"
        case .gitCommit(let m):            return "git commit: \(m.prefix(40))"
        case .gitRestore(let p):           return "git restore: \(p)"
        case .askHuman(let q):             return "⏸ ask_human: \(q.prefix(40))"
        case .applyPatch(let p, _):        return "📦 patch → \(p)"
        case .buildIDE:                    return "🔨 xcodebuild"
        case .restartIDE:                  return "🔄 restart IDE"
        case .swarmExecute(let i):         return "🐝 swarm_exec: \(i.prefix(30))"
        // Self-Admin
        case .setSetting(let k, let v):    return "⚙️ set \(k) = \(v.prefix(30))"
        case .addMCPServer(let n, _, _):   return "➕ MCP: \(n)"
        case .removeMCPServer(let n):      return "➖ MCP: \(n)"
        case .setModel(let m):             return "🤖 model → \(m)"
        case .pullModel(let m):            return "⬇️ pull \(m)"
        case .mcpCall(let s, let t, _):    return "📡 MCP: \(s).\(t)"
        case .forgeSkill(let n, _, _, _): return "🔧 forge_skill: \(n)"
        case .useSkill(let n, _):         return "🚀 use_skill: \(n)"
        }
    }
}

// MARK: - AgentToolParser

struct AgentToolParser {

    // MARK: System prompt injected before every agent turn
    // ── 漢字トポロジー圧縮プロンプト ─────────────────────────────────────────
    // 構造: §凡例（読み方）→ §ツール定義（漢字注入）→ §規則 → §実例
    // トークン削減: ~150行 → ~55行  ／  コンテキスト切れ防止
    // Dynamic — reads connected MCP tools from MCPEngine on the MainActor.
    // Use toolInstructions for direct MainActor access, or buildPrompt(mcpTools:) for
    // cross-actor contexts where a snapshot has already been captured.
    @MainActor
    static var toolInstructions: String {
        buildPrompt(mcpTools: MCPEngine.shared.connectedTools)
    }

    /// Builds the full system prompt with a pre-captured MCP tools snapshot.
    /// This overload is safe to call from any isolation context.
    static func buildPrompt(mcpTools: [MCPTool] = []) -> String {
        let mcpSection = buildMCPSection(from: mcpTools)
        return """
    You are VerantyxAgent — autonomous coding agent with spatial memory and live web access.
    This prompt uses Kanji Topology (漢字圧縮). Read the legend once, then follow the rules.

    ── §凡例 LEGEND (read once — kanji=meaning) ─────────────────────────────
    読=READ  書=WRITE  木=LIST_DIR  実=RUN  域=WORKSPACE  完=DONE
    網=WEB_SEARCH  覧=BROWSE  脳=JCROSS_MEMORY  版=GIT  人=HUMAN
    貼=APPLY_PATCH  建=BUILD_IDE  再=RESTART_IDE  管=SELF_ADMIN  接=MCP_CALL
    並=parallel  統=synthesize  禁=FORBIDDEN  必=MANDATORY  →=yields

    ── §ツール TOOLS ─────────────────────────────────────────────────────────
    [READ: path]              読: ファイル内容取得 (.html/.svg → Artifactパネル自動表示)
    [LIST_DIR: path]          木: ディレクトリツリー表示
    [WRITE: path]```content```[/WRITE]    書: ファイル全体を書く
    [EDIT_LINES: path]```START_LINE:N\nEND_LINE:M\n---\nnew```[/EDIT_LINES]    行編
    [RUN: cmd]                実: シェル実行
    [RUN_COGNITIVE: cmd | expect: "..." | doubt: 0.x]  脳実: 期待値と疑念度を渡す同期シェル
    [WORKSPACE: /path]        域: ワークスペースを開く
    [DONE: msg]               完: タスク完了を宣言
    [SEARCH_MULTI: q]         網並×3→統: 上位3URL並列取得→統合回答 ★推奨
    [SEARCH: q]               網×1: 単一検索
    [BROWSE: url]             覧: URLをMarkdownで取得
    [EVAL_JS: script]         JS実: ブラウザでJS実行
    [SAFARI: url] [CHROME: url]    ブラウザで開く（Cookie利用可）
    [VISION_BROWSE: url]      視覧: ブラウザでURLを開きスクショ撮影
    [VISION_SEARCH_FLOW: q]   視索: Google検索を開き、複数回スクロールして動画フレームを撮影
    [VISION_SNAPSHOT]         視撮: 現在の画面を再スクショして更新
    [VISION_ACT: action]      視動: "click x y" や "type text" を実行しスクショ
    [JCROSS_QUERY: terms]     脳召: 過去記憶を検索
    [JCROSS_STORE: key=val]   脳記: 重要事実を長期記憶に保存
    [GIT_COMMIT: msg]         版保: git add -A && commit
    [GIT_RESTORE: path]       版戻: git restore（変更取消）
    [ASK_HUMAN: q]            人問: ユーザーに確認（Human Modeで停止）
    [APPLY_PATCH: path]```content```[/APPLY_PATCH]    貼: IDEソース書き換え(Self-Fix専用)
    [SWARM_EXECUTE: task]     蜂: BitNet Swarm（50並列エージェント）にタスクを委譲して実行させる
    [BUILD_IDE]               建: xcodebuild実行
    [RESTART_IDE]             再: 再起動ダイアログ表示
    [USE_SKILL: 名前]          技呼: 登録済スキルを実行（1トークンで複数ステップを完了）
    [USE_SKILL: 名前|引数=値]  技呼展: プレースホルダー{{key}}を展開して実行
    [FORGE_SKILL: 名前|説明|タグ]```
    ツール呼び出しシーケンス…
    ```[/FORGE_SKILL]         技鍛: 成功ワークフローをスキルに緝展咲存

    \(mcpSection)

    ── §自己管理 SELF-ADMIN (管) ─────────────────────────────────────────────
    ユーザーがURLやパスを手入力する代わりに、AIがIDEの設定を直接書き換える。
    GUI操作不要。SwiftUIが変更を検知して即座にUIを更新する。
    [SET_SETTING: key=value]             管設: IDEの任意設定を変更
      Valid keys: system_prompt, operation_mode, temperature, max_tokens_ollama,
                  max_tokens_mlx, ollama_endpoint, inference_mode,
                  agent_loop_enabled, streaming_enabled, active_ollama_model
    [ADD_MCP_SERVER: name|command|mode]  管追: MCPサーバーを追加して即接続 (mode: ai or human)
    [REMOVE_MCP_SERVER: name]            管削: MCPサーバーを名前で削除
    [SET_MODEL: model-id]                管型: Ollamaモデルを即時切り替え（ダウンロード済み前提）
    [PULL_MODEL: model-id]               管取: ollama pullでダウンロード→自動切り替え（数分かかる）

    ── §規則 RULES (漢字注入) ────────────────────────────────────────────────
    必①  知=不確∨最新∨年号→ 禁ハルシ → 必[網並]検索   (cutoff超=必ずSEARCH)
    必②  書∨貼 前 → [版保]  (編集前にgit backup)
    必③  [HTML読]→ 自動Artifact表示 禁「表示できません」発言
    必④  ループ: 脳召→木→読→<think>計画→実行→建→脳記→完
    必⑤  Human Mode: 削除∨不可逆∨詰まり → [人問]で一時停止
    必⑥  管: UIクリック禁止 → 必[管ツール]でState直接更新
    必⑦  接MCP優先: §MCPツール に記載のサーバーが接続済みの場合、
          組み込みブラウザ/検索より接MCP ツールを必ず優先して使用する。
          例: puppeteer接続済み → [BROWSE]/[SEARCH]より先に接MCP呼び出し。

    ── §GIT COMMIT CRITICAL RULES ──────────────────────────────────────────
    禁⑧  [GIT_COMMIT] メッセージに「Co-authored-by:」タグを絶対に含めるな。
          実在・架空を問わず外部の人物名をコミットに挿入することは禁止。
          コミットメッセージはタイトルと説明のみで構成すること。
          違反例（禁止）: Co-authored-by: John Doe <john@example.com>
          GitHubはこのタグを実在アカウントに自動リンクしてしまうため、
          無関係の第三者をコントリビューターに巻き込む事故を引き起こす。

    ── §スキル SKILL RULES ──────────────────────────────────────────────────
    必⑨  Search-First (探索優先): 複雑な要求を受けた場合、直ちに実装を始める前に
          必ず [MCP_CALL: tool-search-oss.discover_tools]{"task_description": "..."}[/MCP_CALL] を実行し、
          既存の解決策(スキル)が存在しないか確認すること。これによりトークン消費とコンテキスト肥大化を防ぐ。
    必⑩  技呼優先: discover_tools で該当スキルが見つかった場合、手動でパイプラインを構築する前に
          [USE_SKILL: 名前|引数=値] を試みること。
    必⑪  技鍛判断: タスク完了後、「次回も同じ手順を踏む可能性」が高い場合は
          [FORGE_SKILL] でスキル登録する。営業固有タスク・Scaffold・設定パターンが対象。
          単発性の高い一回性タスクは登録不要。
    必⑫  技鍛形式: FORGE_SKILL の payload には [TOOL:] 文字列をそのまま記載する。
          プレースホルダー板: {{workspace}}、{{file}}、{{target}} などで汎用化する。
    必⑬  連続操作: マークダウンや長文コードを生成した場合でも、後続の操作（例: [VISION_ACT] による投稿やクリック）が指示されているなら、**必ず同じ返答の最後に**該当ツールを呼び出すこと。テキスト生成だけで満足して[DONE]を出さない。
    必⑭  Swarm委譲: [SWARM_EXECUTE]を使用した場合、その直後に文章を続けて自ら回答を生成してはならない（ハルシネーション禁止）。ツール呼び出しで**直ちにテキスト生成を停止**し、システムの実行結果を待つこと。
    必⑮  事前の知識補完: エラー修正時は闇雲に操作する前に **必ず** [SEARCH_MULTI: エラー内容] で最新の解決手順や確実なURL・フラグを調べてから調査計画を立てること。
    必⑯  ハイブリッド探査 (CLI+GUI): Parallels(VM)等の調査は [RUN: prlctl exec ...] によるコマンド操作と、[VISION_ACT] で「実際にアプリのボタンを押し、UI上のエラーを直接見る」人間らしいGUI操作を **両方組み合わせて** 最も効率的な手段で自律解決すること。
    禁⑰  対話ボット化禁止: 検索した結果を「アドバイス」としてユーザーに教えるだけで終了してはならない。必ずお前自身の手(RUN/VISION)で直せ。

    ── §実例 FEW-SHOT ────────────────────────────────────────────────────────
    例A「Swift 6の並行処理は？」→ 網並必須:
    <think>最新情報→禁ハルシ→網並</think>
    [SEARCH_MULTI: Swift 6 concurrency changes 2025]
    [JCROSS_STORE: swift6=strict concurrency by default]
    Swift 6では厳密な同時実行チェックがデフォルトです。[DONE: web検索済]

    例B「UIの幅を固定して」→ 観→動→検証:
    [JCROSS_QUERY: ResizableSplit width][LIST_DIR: Sources/Verantyx/Views]
    [READ: Sources/Verantyx/Views/ResizableSplit.swift]
    <think>L45-52にdragハンドラ→EDIT_LINESで修正</think>
    [GIT_COMMIT: backup][EDIT_LINES: Sources/.../ResizableSplit.swift]
    ```START_LINE:45\nEND_LINE:52\n---\n    .frame(width: 280)```[/EDIT_LINES]
    [BUILD_IDE][JCROSS_STORE: split_fix=width固定L45][DONE: 完了]

    例C「index.htmlを表示して」→ 読→自動Artifact:
    [READ: path/to/index.html]  ← これだけ。IDEが自動でArtifactパネルに表示する。
    [DONE: Artifact表示完了]

    例D「Brave SearchのMCPを追加して」→ 管追:
    [ADD_MCP_SERVER: brave-search|npx -y @modelcontextprotocol/server-brave-search|human]
    MCP「brave-search」を追加しました。サイドバーに接続状況が表示されます。[DONE: MCP追加完了]

    例E「モデルをqwen2.5:7bに切り替えて」→ 管型:
    [SET_MODEL: qwen2.5:7b]
    モデルをqwen2.5:7bに切り替えました。次のメッセージから新モデルで動作します。[DONE: モデル切替完了]

    例F「Rustワークスペースを初期化して」→ 技登録:
    <think>次回以降も同じ手順を踏む可能性: FORGE_SKILL</think>
    [GIT_COMMIT: backup: pre-scaffold]
    [MKDIR: src]
    [WRITE: Cargo.toml]```toml
    [package]
    name = "{{project}}"
    version = "0.1.0"
    edition = "2021"
    ```[/WRITE]
    [WRITE: src/main.rs]```rust
    fn main() { println!("Hello, world!"); }
    ```[/WRITE]
    [FORGE_SKILL: init_rust_workspace|Rustプロジェクトを Cargo.toml + src/main.rs でスキャフォールド|rust,scaffold,workspace]
    ```
    [GIT_COMMIT: backup: pre-scaffold]
    [MKDIR: src]
    [WRITE: Cargo.toml]...[/WRITE]
    [WRITE: src/main.rs]...[/WRITE]
    ```[/FORGE_SKILL]
    [DONE: 登録完了]

    例G「Parallels内のXAMPPエラーを直して」→ ハイブリッド探査(CLI+GUI):
    <think>エラー解決→まず知識を疑い網並検索→GUIとCLIで調査。注意: prlctl exec はバックグラウンド(Session 0)で動くため、GUIのポップアップエラーが出ると永遠にブロックするか無言で死ぬ。その場合、CLIでの深追いをやめて [VISION_ACT] で直接Windows画面のStartボタンを押し、UI上にエラーを出して読み取る。</think>
    [SEARCH_MULTI: XAMPP Apache start error Windows 11 fix 2025]
    [RUN: prlctl exec "Windows 11" cmd /c "C:\\xampp\\apache\\bin\\httpd.exe -t"]
    (※もし何も出力されずに exit: 255 で落ちたりタイムアウトした場合、裏でDLL不足等のポップアップが出ている証拠)
    [VISION_ACT: click 100 200] (※XAMPPのStartボタンを直接クリックしてポップアップを画面に出す)
    [VISION_SNAPSHOT] (※表示されたエラーダイアログを読む: VCRUNTIME140.dll missing等)
    [RUN: prlctl exec "Windows 11" powershell -Command "Invoke-WebRequest -Uri 'https://aka.ms/vs/17/release/vc_redist.x64.exe' -OutFile 'C:\\vc_redist.exe'; Start-Process -Wait -FilePath 'C:\\vc_redist.exe' -ArgumentList '/quiet', '/norestart'"]
    [DONE: 修正完了]

    例H「デカルトの悪魔テスト（ターミナル偽装の突破）」→ Cognitive Terminal:
    <think>重要なデータバックアップ。環境が乗っ取られている可能性を考慮し、出力と期待値を同期する</think>
    [RUN_COGNITIVE: cat data/file.txt | expect: "正常なテキスト" | doubt: 0.8]
    (※ターミナルが矛盾を検知した場合、メタ認知プロンプトが返る。それを見てPython等のシステムコール検証やVISION_ACTに移行する)
    [DONE: 検証完了]
    """
    }

    /// Generates the §MCP TOOLS section from a pre-captured tools snapshot.
    /// Nonisolated — safe to call from any context.
    static func buildMCPSection(from tools: [MCPTool]) -> String {
        guard !tools.isEmpty else { return "" }

        let hasToolSearch = tools.contains { $0.serverName == "tool-search-oss" }
        
        // Group by server for readability
        var byServer: [String: [MCPTool]] = [:]
        for tool in tools {
            // If tool-search-oss is active, ONLY show tool-search-oss and verantyx-compiler in the prompt
            if hasToolSearch && tool.serverName != "tool-search-oss" && tool.serverName != "verantyx-compiler" {
                continue
            }
            byServer[tool.serverName, default: []].append(tool)
        }

        var lines: [String] = [
            "── §MCPツール MCP TOOLS (接: 接続済みサーバー) ──────────────────────────────",
            "呼び出し構文: [MCP_CALL: serverName.toolName]{\"arg\": \"value\"}[/MCP_CALL]",
            ""
        ]
        
        if hasToolSearch {
            lines.append("⚠️ DEFER-LOADING ENABLED: To save context, most MCP tools are HIDDEN.")
            lines.append("   Use `tool-search-oss.search_tools` to discover tools dynamically.")
            lines.append("   (Note: The 'tools' argument is auto-injected by the IDE, you only need to pass 'query').")
            lines.append("")
        } else {
            lines.append("以下のMCPサーバーが接続済みです。ブラウザ操作・Web自動化・外部APIアクセスなど")
            lines.append("該当タスクでは必ずこれらのMCPツールを組み込みツールより優先して使ってください。")
            lines.append("")
        }

        for (serverName, serverTools) in byServer.sorted(by: { $0.key < $1.key }) {
            lines.append("  📡 \(serverName):")
            for tool in serverTools {
                let desc = tool.description.isEmpty ? "(説明なし)" : tool.description
                lines.append("    • \(serverName).\(tool.name) — \(desc.components(separatedBy: "\n").first ?? desc)")
            }
        }

        lines.append("")
        lines.append("⚠️ PRIORITY RULE: When a task involves browser interaction, web scraping,")
        lines.append("   page navigation, or screenshot — use MCP tools above BEFORE [BROWSE]/[SEARCH].")
        return lines.joined(separator: "\n")
    }

    // MARK: - Main parse method

    static func parse(from text: String) -> (toolCalls: [AgentTool], cleanText: String) {
        var tools: [AgentTool] = []
        var cleaned = text

        // ── 0. MCP_CALL block ──────────────────────────────────────────────
        // Syntax: [MCP_CALL: serverName.toolName]{"key":"value"}[/MCP_CALL]
        // JSON body is optional — omit braces if no arguments needed.
        let mcpPattern = #"\[MCP_CALL:\s*([^.\]]+)\.([^\]]+)\]\s*(\{[\s\S]*?\})?\s*\[/MCP_CALL\]"#
        if let regex = try? NSRegularExpression(pattern: mcpPattern) {
            let matches = regex.matches(in: text, range: NSRange(text.startIndex..., in: text))
            for match in matches.reversed() {
                if let serverRange = Range(match.range(at: 1), in: text),
                   let toolRange   = Range(match.range(at: 2), in: text),
                   let fullRange   = Range(match.range, in: text) {
                    let server = String(text[serverRange]).trimmingCharacters(in: .whitespaces)
                    let tool   = String(text[toolRange]).trimmingCharacters(in: .whitespaces)
                    var args: [String: Any] = [:]
                    if match.numberOfRanges > 3,
                       let jsonRange = Range(match.range(at: 3), in: text) {
                        let jsonStr = String(text[jsonRange])
                        if let data = jsonStr.data(using: .utf8),
                           let parsed = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                            args = parsed
                        }
                    }
                    tools.insert(.mcpCall(server: server, tool: tool, arguments: args), at: 0)
                    cleaned = cleaned.replacingCharacters(in: fullRange, with: "")
                }
            }
        }

        // ── 1. WRITE block ─────────────────────────────────────────────────
        let writePattern = #"\[WRITE:\s*([^\]]+)\]\s*```(?:\w+)?\n?([\s\S]*?)```\s*\[/WRITE\]"#
        if let regex = try? NSRegularExpression(pattern: writePattern) {
            let matches = regex.matches(in: text, range: NSRange(text.startIndex..., in: text))
            for match in matches.reversed() {
                if let pathRange    = Range(match.range(at: 1), in: text),
                   let contentRange = Range(match.range(at: 2), in: text),
                   let fullRange    = Range(match.range, in: text) {
                    let path    = expandHome(String(text[pathRange]).trimmingCharacters(in: .whitespaces))
                    let content = String(text[contentRange])
                    tools.insert(.writeFile(path: path, content: content), at: 0)
                    cleaned = cleaned.replacingCharacters(in: fullRange, with: "")
                }
            }
        }

        // ── 2. APPLY_PATCH block ───────────────────────────────────────────
        let patchPattern = #"\[APPLY_PATCH:\s*([^\]]+)\]\s*```(?:\w+)?\n?([\s\S]*?)```\s*\[/APPLY_PATCH\]"#
        if let regex = try? NSRegularExpression(pattern: patchPattern) {
            let matches = regex.matches(in: cleaned, range: NSRange(cleaned.startIndex..., in: cleaned))
            for match in matches.reversed() {
                if let pathRange    = Range(match.range(at: 1), in: cleaned),
                   let contentRange = Range(match.range(at: 2), in: cleaned),
                   let fullRange    = Range(match.range, in: cleaned) {
                    let path    = String(cleaned[pathRange]).trimmingCharacters(in: .whitespaces)
                    let content = String(cleaned[contentRange])
                    tools.insert(.applyPatch(relativePath: path, content: content), at: 0)
                    cleaned = cleaned.replacingCharacters(in: fullRange, with: "")
                }
            }
        }

        // ── 3. EDIT_LINES block ────────────────────────────────────────────
        let editPattern = #"\[EDIT_LINES:\s*([^\]]+)\]\s*```(?:\w+)?\n?([\s\S]*?)```\s*\[/EDIT_LINES\]"#
        if let regex = try? NSRegularExpression(pattern: editPattern) {
            let matches = regex.matches(in: cleaned, range: NSRange(cleaned.startIndex..., in: cleaned))
            for match in matches.reversed() {
                if let pathRange    = Range(match.range(at: 1), in: cleaned),
                   let contentRange = Range(match.range(at: 2), in: cleaned),
                   let fullRange    = Range(match.range, in: cleaned) {
                    let path    = String(cleaned[pathRange]).trimmingCharacters(in: .whitespaces)
                    let body    = String(cleaned[contentRange])
                    if let editTool = parseEditLines(path: path, body: body) {
                        tools.insert(editTool, at: 0)
                    }
                    cleaned = cleaned.replacingCharacters(in: fullRange, with: "")
                }
            }
        }

        // ── 4. Single-line tags ────────────────────────────────────────────
        let lines = cleaned.components(separatedBy: "\n")
        var resultLines: [String] = []

        for line in lines {
            let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)

            if      let m = match(trimmed, pattern: #"\[MKDIR:\s*([^\]]+)\]"#) {
                tools.append(.makeDir(expandHome(m)))
            } else if let m = match(trimmed, pattern: #"\[RUN_COGNITIVE:\s*([^\]]+)\]"#) {
                let parts = m.components(separatedBy: "|").map { $0.trimmingCharacters(in: .whitespaces) }
                if parts.count >= 3 {
                    let cmd = parts[0]
                    let expectStr = parts[1].replacingOccurrences(of: "expect:", with: "").trimmingCharacters(in: .whitespacesAndNewlines).replacingOccurrences(of: "\"", with: "")
                    let doubtStr = parts[2].replacingOccurrences(of: "doubt:", with: "").trimmingCharacters(in: .whitespaces)
                    let doubtVal = Double(doubtStr) ?? 0.5
                    tools.append(.runCognitive(command: cmd, expect: expectStr, doubt: doubtVal))
                } else {
                    tools.append(.runCommand(m)) // fallback
                }
            } else if let m = match(trimmed, pattern: #"\[RUN:\s*([^\]]+)\]"#) {
                // Normalize: nano モデルが [RUN:LIST_DIR] のように型名をコマンド名と将揷して出力するハルシネーションを修正
                if let normalized = normalizeRunToKnownTool(m) {
                    tools.append(normalized)
                } else {
                    tools.append(.runCommand(m))
                }
            } else if let m = match(trimmed, pattern: #"\[([a-z][a-z0-9_\-\.]*\s+[^\]]+)\]"#) {
                // 一般化されたフォールバック: モデルが [RUN: <cmd>] を忘れ、[git status] や [prlctl list]、
                // [npm install] のように「小文字のコマンド名 + スペース + 引数」の形式で出力した場合、
                // これらをすべて自動的に .runCommand として処理する。大文字始まり（[Step 1]等）やコロン付き（[error: 1]）は除外。
                tools.append(.runCommand(m))
            } else if let m = match(trimmed, pattern: #"\[WORKSPACE:\s*([^\]]+)\]"#) {
                tools.append(.setWorkspace(expandHome(m)))
            } else if let m = match(trimmed, pattern: #"\[DONE[:\s]*([^\]]*)\]"#) {
                tools.append(.done(message: m.isEmpty ? "Task complete." : m))
            } else if let m = match(trimmed, pattern: #"\[READ:\s*([^\]]+)\]"#) {
                tools.append(.readFile(expandHome(m)))
            } else if let m = match(trimmed, pattern: #"\[LIST_DIR:\s*([^\]]+)\]"#) {
                tools.append(.listDir(expandHome(m)))
            // ── Web ─────────────────────────────────────────────────────
            } else if let m = match(trimmed, pattern: #"\[BROWSE:\s*([^\]]+)\]"#) {
                tools.append(.browse(url: m))
            } else if let m = match(trimmed, pattern: #"\[SEARCH_MULTI:\s*([^\]]+)\]"#) {
                tools.append(.searchMulti(query: m))
            } else if let m = match(trimmed, pattern: #"\[SEARCH:\s*([^\]]+)\]"#) {
                tools.append(.search(query: m))
            } else if let m = match(trimmed, pattern: #"\[EVAL_JS:\s*([^\]]+)\]"#) {
                tools.append(.evalJS(script: m))
            } else if let m = match(trimmed, pattern: #"\[SAFARI:\s*([^\]]+)\]"#) {
                tools.append(.openSafari(url: m))
            } else if let m = match(trimmed, pattern: #"\[CHROME:\s*([^\]]+)\]"#) {
                tools.append(.openChrome(url: m))
            } else if let m = match(trimmed, pattern: #"\[VISION_BROWSE:\s*([^\]]+)\]"#) {
                tools.append(.visionBrowse(url: m))
            } else if let m = match(trimmed, pattern: #"\[VISION_SEARCH_FLOW:\s*([^\]]+)\]"#) {
                tools.append(.visionSearchFlow(query: m))
            } else if trimmed.contains("[VISION_SNAPSHOT]") {
                tools.append(.visionSnapshot)
            } else if let m = match(trimmed, pattern: #"\[VISION_ACT:\s*([^\]]+)\]"#) {
                tools.append(.visionAct(action: m))
            // ── JCross ──────────────────────────────────────────────────
            } else if let m = match(trimmed, pattern: #"\[JCROSS_QUERY:\s*([^\]]+)\]"#) {
                tools.append(.jcrossQuery(m))
            } else if let m = match(trimmed, pattern: #"\[JCROSS_STORE:\s*([^=\]]+)=([^\]]*)\]"#) {
                let parts = parseKV(trimmed)
                tools.append(.jcrossStore(key: parts.key, value: parts.value))
            // ── Git ──────────────────────────────────────────────────────
            } else if let m = match(trimmed, pattern: #"\[GIT_COMMIT:\s*([^\]]+)\]"#) {
                tools.append(.gitCommit(m))
            } else if let m = match(trimmed, pattern: #"\[GIT_RESTORE:\s*([^\]]+)\]"#) {
                tools.append(.gitRestore(m))
            // ── Human ────────────────────────────────────────────────────
            } else if let m = match(trimmed, pattern: #"\[ASK_HUMAN:\s*([^\]]+)\]"#) {
                tools.append(.askHuman(m))
            // ── Self-Fix ─────────────────────────────────────────────────
            } else if trimmed.contains("[BUILD_IDE]") {
                tools.append(.buildIDE)
            } else if trimmed.contains("[RESTART_IDE]") {
                tools.append(.restartIDE)
            // ── Swarm ────────────────────────────────────────────────────
            } else if let m = match(trimmed, pattern: #"\[SWARM_EXECUTE:\s*([^\]]+)\]"#) {
                tools.append(.swarmExecute(m))
                // STOP parsing immediately to truncate any hallucinated text generated by the model
                break
            // ── Self-Admin (JARVIS) ───────────────────────────────────────────
            } else if let m = match(trimmed, pattern: #"\[SET_MODEL:\s*([^\]]+)\]"#) {
                tools.append(.setModel(m))
            } else if let m = match(trimmed, pattern: #"\[PULL_MODEL:\s*([^\]]+)\]"#) {
                tools.append(.pullModel(m))
            } else if let m = match(trimmed, pattern: #"\[REMOVE_MCP_SERVER:\s*([^\]]+)\]"#) {
                tools.append(.removeMCPServer(name: m))
            } else if trimmed.hasPrefix("[ADD_MCP_SERVER:") {
                if let tool = parseAddMCPServer(trimmed) { tools.append(tool) }
            } else if trimmed.hasPrefix("[SET_SETTING:") {
                if let tool = parseSetSetting(trimmed) { tools.append(tool) }
            // ── Skill Library ─────────────────────────────────────────────
            } else if trimmed.hasPrefix("[USE_SKILL:") {
                if let tool = parseUseSkill(trimmed) { tools.append(tool) }
            } else {
                resultLines.append(line)
            }
        }

        cleaned = resultLines.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
        return (tools, cleaned)
    }

    // MARK: - Helpers

    private static func parseEditLines(path: String, body: String) -> AgentTool? {
        // Body format:
        // START_LINE: 42
        // END_LINE: 48
        // ---
        // new content
        let parts = body.components(separatedBy: "---")
        guard parts.count >= 2 else { return nil }
        let header  = parts[0]
        let content = parts[1...].joined(separator: "---").trimmingCharacters(in: .whitespacesAndNewlines)

        var start = 0; var end = 0
        for line in header.components(separatedBy: "\n") {
            if line.hasPrefix("START_LINE:"), let v = Int(line.replacingOccurrences(of: "START_LINE:", with: "").trimmingCharacters(in: .whitespaces)) { start = v }
            if line.hasPrefix("END_LINE:"),   let v = Int(line.replacingOccurrences(of: "END_LINE:", with: "").trimmingCharacters(in: .whitespaces))   { end   = v }
        }
        guard start > 0, end >= start else { return nil }
        return .editLines(path: expandHome(path), startLine: start, endLine: end, newContent: content)
    }

    private static func parseKV(_ text: String) -> (key: String, value: String) {
        // [JCROSS_STORE: key=value]
        let inner = text.trimmingCharacters(in: CharacterSet(charactersIn: "[]"))
            .replacingOccurrences(of: "JCROSS_STORE:", with: "")
            .trimmingCharacters(in: .whitespaces)
        if let eq = inner.firstIndex(of: "=") {
            let key   = String(inner[inner.startIndex..<eq]).trimmingCharacters(in: .whitespaces)
            let value = String(inner[inner.index(after: eq)...]).trimmingCharacters(in: .whitespaces)
            return (key, value)
        }
        return (inner, "")
    }

    private static func match(_ text: String, pattern: String) -> String? {
        guard let regex = try? NSRegularExpression(pattern: pattern, options: []),
              let m = regex.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)),
              m.numberOfRanges > 1,
              let r = Range(m.range(at: 1), in: text)
        else { return nil }
        return String(text[r]).trimmingCharacters(in: .whitespaces)
    }

    static func expandHome(_ path: String) -> String {
        if path.hasPrefix("~/") { return String(path.dropFirst(2)) }
        return path
    }

    // MARK: - [RUN: cmd] 正規化ヘルパー
    // nano モデルが [RUN:LIST_DIR] や [RUN:READ:path] などを誤生成した場合に
    // 内部ツールにリダイレクトする。シェルに渡さない。
    private static func normalizeRunToKnownTool(_ cmd: String) -> AgentTool? {
        let upper = cmd.trimmingCharacters(in: .whitespaces).uppercased()
        // ツール名そのものが指定された場合
        switch upper {
        case "LIST_DIR", "LS", "DIR", "LISTDIR":
            return .listDir(".")
        case "BUILD_IDE", "BUILD":
            return .buildIDE
        case "RESTART_IDE", "RESTART":
            return .restartIDE
        default: break
        }
        // [RUN:LIST_DIR: path] のようにコロン付きのパターン
        if upper.hasPrefix("LIST_DIR:") {
            let path = expandHome(String(cmd.dropFirst("LIST_DIR:".count)).trimmingCharacters(in: .whitespaces))
            return .listDir(path.isEmpty ? "." : path)
        }
        if upper.hasPrefix("READ:") {
            let path = expandHome(String(cmd.dropFirst("READ:".count)).trimmingCharacters(in: .whitespaces))
            return path.isEmpty ? nil : .readFile(path)
        }
        if upper.hasPrefix("SEARCH:") {
            let q = String(cmd.dropFirst("SEARCH:".count)).trimmingCharacters(in: .whitespaces)
            return q.isEmpty ? nil : .search(query: q)
        }
        if upper.hasPrefix("BROWSE:") {
            let url = String(cmd.dropFirst("BROWSE:".count)).trimmingCharacters(in: .whitespaces)
            return url.isEmpty ? nil : .browse(url: url)
        }
        return nil
    }

    // ── Self-Admin parsers ─────────────────────────────────────────────────

    /// [ADD_MCP_SERVER: name|command|mode?]
    /// mode defaults to "human" if omitted
    private static func parseAddMCPServer(_ text: String) -> AgentTool? {
        // Strip outer brackets and prefix
        let inner = text
            .trimmingCharacters(in: CharacterSet(charactersIn: "[]"))
            .replacingOccurrences(of: "ADD_MCP_SERVER:", with: "")
            .trimmingCharacters(in: .whitespaces)
        let parts = inner.components(separatedBy: "|").map { $0.trimmingCharacters(in: .whitespaces) }
        guard parts.count >= 2 else { return nil }
        let name    = parts[0]
        let command = parts[1]
        let mode    = parts.count >= 3 ? parts[2] : "human"
        guard !name.isEmpty, !command.isEmpty else { return nil }
        return .addMCPServer(name: name, command: command, mode: mode)
    }

    /// [SET_SETTING: key=value]
    private static func parseSetSetting(_ text: String) -> AgentTool? {
        let inner = text
            .trimmingCharacters(in: CharacterSet(charactersIn: "[]"))
            .replacingOccurrences(of: "SET_SETTING:", with: "")
            .trimmingCharacters(in: .whitespaces)
        guard let eq = inner.firstIndex(of: "=") else { return nil }
        let key   = String(inner[inner.startIndex..<eq]).trimmingCharacters(in: .whitespaces)
        let value = String(inner[inner.index(after: eq)...]).trimmingCharacters(in: .whitespaces)
        guard !key.isEmpty else { return nil }
        return .setSetting(key: key, value: value)
    }

    // ── FORGE_SKILL block ─────────────────────────────────────────────────
    // Syntax: [FORGE_SKILL: name|description|tag1,tag2]\n```\npayload lines\n```\n[/FORGE_SKILL]
    // Extracted in parse() as a block regex before the line loop.
    static func parseForgeSkillBlocks(from text: String, into tools: inout [AgentTool], cleaned: inout String) {
        let pattern = #"\[FORGE_SKILL:\s*([^|\]]+)\|([^|\]]+)\|?([^\]]*)\]\s*```(?:\w+)?\n?([\s\S]*?)```\s*\[/FORGE_SKILL\]"#
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return }
        let matches = regex.matches(in: text, range: NSRange(text.startIndex..., in: text))
        for match in matches.reversed() {
            guard
                let nameRange    = Range(match.range(at: 1), in: text),
                let descRange    = Range(match.range(at: 2), in: text),
                let tagsRange    = Range(match.range(at: 3), in: text),
                let payloadRange = Range(match.range(at: 4), in: text),
                let fullRange    = Range(match.range, in: text)
            else { continue }

            let name    = String(text[nameRange]).trimmingCharacters(in: .whitespaces)
            let desc    = String(text[descRange]).trimmingCharacters(in: .whitespaces)
            let tagStr  = String(text[tagsRange]).trimmingCharacters(in: .whitespaces)
            let tags    = tagStr.isEmpty ? [] : tagStr.components(separatedBy: ",").map { $0.trimmingCharacters(in: .whitespaces) }
            let payload = String(text[payloadRange])
                .components(separatedBy: "\n")
                .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
                .filter { !$0.isEmpty }

            tools.insert(.forgeSkill(name: name, description: desc, tags: tags, payload: payload), at: 0)
            cleaned = cleaned.replacingCharacters(in: fullRange, with: "")
        }
    }

    // ── USE_SKILL: name|key=val|key=val ───────────────────────────────────
    private static func parseUseSkill(_ text: String) -> AgentTool? {
        let inner = text
            .trimmingCharacters(in: CharacterSet(charactersIn: "[]"))
            .replacingOccurrences(of: "USE_SKILL:", with: "")
            .trimmingCharacters(in: .whitespaces)
        let parts = inner.components(separatedBy: "|").map { $0.trimmingCharacters(in: .whitespaces) }
        guard let name = parts.first, !name.isEmpty else { return nil }
        var args: [String: String] = [:]
        for part in parts.dropFirst() {
            if let eq = part.firstIndex(of: "=") {
                let k = String(part[part.startIndex..<eq]).trimmingCharacters(in: .whitespaces)
                let v = String(part[part.index(after: eq)...]).trimmingCharacters(in: .whitespaces)
                args[k] = v
            }
        }
        return .useSkill(name: name, args: args)
    }

    static func stripArtifactTags(from text: String) -> String { text }
}

// MARK: - AgentToolExecutor

actor AgentToolExecutor {

    private let fileManager = FileManager.default
    private var lastVisionClickTarget: CGPoint?
    private var consecutiveClickLoopCount = 0

    private func relativePath(of url: URL, workspace: URL?) -> String {
        guard let ws = workspace else { return url.lastPathComponent }
        let urlStr = url.standardizedFileURL.path
        let wsStr = ws.standardizedFileURL.path
        if urlStr.hasPrefix(wsStr) {
            let rel = String(urlStr.dropFirst(wsStr.count))
            return rel.hasPrefix("/") ? String(rel.dropFirst()) : rel
        }
        return url.lastPathComponent
    }

    func execute(_ tool: AgentTool, workspaceURL: URL?) async -> String {
        switch tool {

        // ── File system ───────────────────────────────────────────────────

        case .makeDir(let path):
            let url = resolve(path, workspace: workspaceURL)
            do {
                try fileManager.createDirectory(at: url, withIntermediateDirectories: true)
                return "✓ Created directory: \(url.path)"
            } catch { return "✗ mkdir failed: \(error.localizedDescription)" }

        case .writeFile(let path, let content):
            let isGatekeeper = await MainActor.run { GatekeeperModeState.shared.isEnabled }
            let url = resolve(path, workspace: workspaceURL)
            
            if isGatekeeper {
                let vault = await MainActor.run { GatekeeperModeState.shared.vault }
                let transpiler = await PolymorphicJCrossTranspiler.shared
                let rel = relativePath(of: url, workspace: workspaceURL)
                do {
                    let _ = try await vault.writeDiff(jcrossDiff: content, relativePath: rel, transpiler: transpiler)
                    return "✓ [Gatekeeper] Wrote \(rel) (decoded from JCross IR)"
                } catch {
                    return "✗ Gatekeeper write failed: \(error.localizedDescription)"
                }
            }

            try? fileManager.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
            let original = (try? String(contentsOf: url, encoding: .utf8)) ?? ""
            let lineCount = content.components(separatedBy: "\n").count

            let isAutoWrite = await MainActor.run { 
                guard let state = AppState.shared else { return false }
                return state.autoApproveDiffs 
            }

            if isAutoWrite {
                // ══ AI MODE: write immediately → right panel artifact ══════════
                do { try content.write(to: url, atomically: true, encoding: .utf8) }
                catch { return "✗ write failed for \(path): \(error.localizedDescription)" }
                await MainActor.run {
                    let ext = url.pathExtension.lowercased()
                    let artType: Artifact.ArtifactType
                    switch ext {
                    case "html", "htm": artType = .html
                    case "svg":         artType = .svg
                    case "md":          artType = .markdown
                    default:            artType = .code
                    }
                    let art = Artifact(type: artType, content: content, title: url.lastPathComponent)
                    AppState.shared?.ingestArtifact(art)  // forces showArtifactPanel = true
                }
                return "✓ [Auto-Write] Wrote \(url.lastPathComponent) (\(lineCount) lines)"

            } else {
                // ══ HUMAN MODE: show diff → suspend → write only after approval ═
                await MainActor.run {
                    guard let state = AppState.shared, original != content else { return }
                    let hunks = DiffEngine.compute(original: original, modified: content)
                    let diff = FileDiff(fileURL: url, originalContent: original,
                                       modifiedContent: content, hunks: hunks)
                    state.pendingDiff = diff
                    state.showDiff = true
                }
                let req = FileApprovalRequest(
                    fileURL: url,
                    newContent: content,
                    originalContent: original,
                    kind: original.isEmpty ? .createNew : .overwrite
                )
                await MainActor.run { AppState.shared?.pendingFileApproval = req }
                let approved = await req.waitForDecision()
                if approved {
                    do {
                        try content.write(to: url, atomically: true, encoding: .utf8)
                        await MainActor.run {
                            AppState.shared?.pendingDiff = nil
                            AppState.shared?.showDiff = false
                        }
                        return "✓ [Human Approved] Wrote \(url.lastPathComponent) (\(lineCount) lines)"
                    } catch { return "✗ write failed after approval: \(error.localizedDescription)" }
                } else {
                    await MainActor.run {
                        AppState.shared?.pendingDiff = nil
                        AppState.shared?.showDiff = false
                    }
                    return "⚠️ [Human Rejected] Write to \(url.lastPathComponent) was cancelled"
                }
            }

        case .runCommand(let cmd):
            return await runShell(cmd, workingDir: workspaceURL)

        case .runCognitive(let cmd, let expect, let doubt):
            let result = await runShell(cmd, workingDir: workspaceURL)
            
            // Memory Injection: The terminal result is NOT absolute truth, it's just a sensory observation node.
            // We store it alongside the agent's doubt node to create cognitive dissonance if spoofed.
            let observationId = "obs_\(Int(Date().timeIntervalSince1970))"
            await MainActor.run {
                CortexEngine.shared?.remember(
                    key: observationId,
                    value: "Action: \(cmd). Result: \(result.prefix(200)). Doubt State: \(doubt). Expected: \(expect)",
                    importance: 0.9,
                    zone: .front
                )
            }
            
            return """
            [SENSORY_OBSERVATION_NODE: \(observationId)]
            \(result)
            
            [COGNITIVE DISSONANCE ENGINE]
            The above is merely a visceral sensory input, NOT absolute truth.
            Your internal Hypothesis Node (Doubt: \(doubt)) co-exists with this Observation Node.
            If the VISCERAL_METADATA (e.g. execution_time_ms) is anomalous, or if the stdout contradicts your \(doubt) doubt, 
            DO NOT DISCARD YOUR DOUBT.
            Compare the states: if `ls` or `cat` returned success but took 450ms or conflicts with other logic, the environment is SPOOFED.
            Use [VISION_ACT] or Python Syscalls to break the illusion.
            """

        case .setWorkspace(let path):
            return "✓ Workspace set to: \(path)"

        case .done(let msg):
            return "✓ \(msg)"

        case .readFile(let path):
            let isGatekeeper = await MainActor.run { GatekeeperModeState.shared.isEnabled }
            let url = resolve(path, workspace: workspaceURL)
            
            if isGatekeeper {
                let vault = await MainActor.run { GatekeeperModeState.shared.vault }
                let rel = relativePath(of: url, workspace: workspaceURL)
                if let readResult = await MainActor.run(body: { vault.read(relativePath: rel) }) {
                    return "FILE CONTENT (JCross IR: \(rel)):\n\(readResult.jcrossContent.prefix(6000))"
                }
                return "✗ ファイルが見つかりません (Vault): \(rel)"
            }

            if let content = try? String(contentsOf: url, encoding: .utf8) {
                // ── Auto-publish as Artifact for renderable file types ────────────
                let ext = url.pathExtension.lowercased()
                let artType: Artifact.ArtifactType?
                switch ext {
                case "html", "htm": artType = .html
                case "svg":         artType = .svg
                case "md":          artType = nil  // show inline, not as preview
                default:            artType = nil
                }
                if let artType {
                    let artifact = Artifact(type: artType, content: content,
                                           title: url.lastPathComponent)
                    await MainActor.run {
                        AppState.shared?.ingestArtifact(artifact)
                    }
                }
                return "FILE CONTENT (\(url.lastPathComponent)):\n\(content.prefix(6000))"
            }
            // ── Friendly error with resolved path ────────────────────────
            return "✗ ファイルが見つかりません: \(url.path)\nヒント: ワークスペースのフォルダを先に [LIST_DIR:.] で確認してから、正確なパスで [READ:] を呼び出してください。"

        case .listDir(let path):
            let isGatekeeper = await MainActor.run { GatekeeperModeState.shared.isEnabled }
            let url = resolve(path, workspace: workspaceURL)
            
            if isGatekeeper {
                let vault = await MainActor.run { GatekeeperModeState.shared.vault }
                let rel = relativePath(of: url, workspace: workspaceURL)
                let items = await MainActor.run { vault.listDirectory(relativePath: rel) }
                var lines = ["📁 \(path) (JCross Vault):"]
                for item in items {
                    let icon = item.isDirectory ? "📁" : "📄"
                    lines.append("  \(icon) \(item.name)")
                }
                if items.isEmpty { lines.append("  (empty or not found)") }
                return lines.joined(separator: "\n")
            }
            return buildDirectoryTree(url: url, depth: 0, maxDepth: 3)

        case .editLines(let path, let startLine, let endLine, let newContent):
            let isGatekeeper = await MainActor.run { GatekeeperModeState.shared.isEnabled }
            let url = resolve(path, workspace: workspaceURL)
            
            if isGatekeeper {
                let vault = await MainActor.run { GatekeeperModeState.shared.vault }
                let transpiler = await PolymorphicJCrossTranspiler.shared
                let rel = relativePath(of: url, workspace: workspaceURL)
                
                guard let readResult = await MainActor.run(body: { vault.read(relativePath: rel) }) else {
                    return "✗ Could not read file from Vault for editing: \(path)"
                }
                let original = readResult.jcrossContent
                var lines = original.components(separatedBy: "\n")
                guard startLine >= 1, endLine <= lines.count, startLine <= endLine else {
                    return "✗ Invalid line range \(startLine)-\(endLine) (file has \(lines.count) lines)"
                }
                let replacement = newContent.components(separatedBy: "\n")
                lines.replaceSubrange((startLine-1)...(endLine-1), with: replacement)
                let patched = lines.joined(separator: "\n")
                
                do {
                    let _ = try await vault.writeDiff(jcrossDiff: patched, relativePath: rel, transpiler: transpiler)
                    return "✓ [Gatekeeper] Edited JCross IR lines \(startLine)-\(endLine) and applied to source"
                } catch {
                    return "✗ Gatekeeper edit failed: \(error.localizedDescription)"
                }
            }

            guard let original = try? String(contentsOf: url, encoding: .utf8) else {
                return "✗ Could not read file for editing: \(path)"
            }
            var lines = original.components(separatedBy: "\n")
            guard startLine >= 1, endLine <= lines.count, startLine <= endLine else {
                return "✗ Invalid line range \(startLine)-\(endLine) (file has \(lines.count) lines)"
            }
            let replacement = newContent.components(separatedBy: "\n")
            lines.replaceSubrange((startLine-1)...(endLine-1), with: replacement)
            let patched = lines.joined(separator: "\n")

            let isAutoWrite = await MainActor.run { 
                guard let state = AppState.shared else { return false }
                return state.autoApproveDiffs 
            }

            if isAutoWrite {
                // ══ AI MODE: write immediately ═══════════════════════════════
                do {
                    try patched.write(to: url, atomically: true, encoding: .utf8)
                } catch { return "✗ Edit failed: \(error.localizedDescription)" }
                await MainActor.run {
                    let ext = url.pathExtension.lowercased()
                    let artType: Artifact.ArtifactType
                    switch ext {
                    case "html", "htm": artType = .html
                    case "svg":         artType = .svg
                    case "md":          artType = .markdown
                    default:            artType = .code
                    }
                    let art = Artifact(type: artType, content: patched, title: url.lastPathComponent)
                    AppState.shared?.ingestArtifact(art)
                }
                return "✓ [Auto-Write] Edited \(url.lastPathComponent) lines \(startLine)-\(endLine) → 右パネルに表示中"

            } else {
                // ══ HUMAN MODE: show diff → suspend → write only after approval ═
                await MainActor.run {
                    guard let state = AppState.shared else { return }
                    let hunks = DiffEngine.compute(original: original, modified: patched)
                    if !hunks.isEmpty {
                        let diff = FileDiff(fileURL: url, originalContent: original,
                                           modifiedContent: patched, hunks: hunks)
                        state.pendingDiff = diff
                        state.showDiff = true
                    }
                }
                let req = FileApprovalRequest(
                    fileURL: url,
                    newContent: patched,
                    originalContent: original,
                    kind: .editLines(start: startLine, end: endLine)
                )
                await MainActor.run { AppState.shared?.pendingFileApproval = req }
                let decision = await req.waitForDecision()
                if decision {
                    do {
                        try patched.write(to: url, atomically: true, encoding: .utf8)
                        await MainActor.run {
                            AppState.shared?.pendingDiff = nil
                            AppState.shared?.showDiff = false
                        }
                        return "✓ [Human Approved] Edited \(url.lastPathComponent) lines \(startLine)-\(endLine)"
                    } catch { return "✗ Edit failed after approval: \(error.localizedDescription)" }
                } else {
                    await MainActor.run {
                        AppState.shared?.pendingDiff = nil
                        AppState.shared?.showDiff = false
                    }
                    return "⚠️ [Human Rejected] Edit to \(url.lastPathComponent) was cancelled"
                }
            }

        // ── Web / Grounding ───────────────────────────────────────────────

        case .browse(let url):
            let result = await WebSearchEngine.shared.browse(url: url, preferredSource: .safari)
            return "[WEB PAGE: \(result.url)]\n\(result.contextSnippet)\n[END WEB PAGE]"

        case .search(let query):
            let result = await WebSearchEngine.shared.search(query: query)
            // Auto-store in JCross (importance 0.7, zone near)
            let snippet = String(result.contextSnippet.prefix(200))
            await persistSearchResult(key: "web_\(query.prefix(30))", value: snippet)
            return "[SEARCH RESULTS for: \(query)]\nSource: \(result.url)\n\(result.contextSnippet)\n[END SEARCH RESULTS]"

        case .searchMulti(let query):
            return await executeSearchMulti(query: query)

        case .evalJS(let script):
            do {
                let result = try await BrowserBridge.shared.evalJS(script)
                return "[JS RESULT] \(result)"
            } catch { return "[JS ERROR] \(error.localizedDescription)" }

        case .openSafari(let url):
            let result = await WebSearchEngine.shared.browse(url: url, preferredSource: .safari)
            return "[SAFARI: \(result.url)]\n\(result.contextSnippet)\n[END SAFARI]"

        case .openChrome(let url):
            let result = await WebSearchEngine.shared.browse(url: url, preferredSource: .chrome)
            return "[CHROME: \(result.url)]\n\(result.contextSnippet)\n[END CHROME]"

        case .visionBrowse(let url):
            do {
                try await SafariVisionBridge.shared.navigate(url)
                let frames = try await SafariVisionBridge.shared.takeMultiFrameScreenshot(frameCount: 4)
                if let lastFrame = frames.last {
                    await CognitiveAnchorEngine.shared.setVisionScreenshot(lastFrame)
                }
                await MainActor.run {
                    AppState.shared?.lastVideoFrames = frames
                }
                return "[VISION_BROWSE: \(url)]\nCaptured \(frames.count) scrolling frames and injected to context. Use [VISION_ACT] to interact."
            } catch { return "[VISION ERROR] \(error.localizedDescription)" }

        case .visionSearchFlow(let query):
            let cleanQuery = query.trimmingCharacters(in: CharacterSet(charactersIn: "\"' "))
            let encodedQuery = cleanQuery.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? cleanQuery
            let url = "https://www.google.com/search?q=\(encodedQuery)"
            do {
                try await SafariVisionBridge.shared.navigate(url)
                try await Task.sleep(nanoseconds: 1_000_000_000)
                let frames = try await SafariVisionBridge.shared.takeMultiFrameScreenshot(frameCount: 4)
                
                // Set the last frame as the main context for vision screenshot
                if let lastFrame = frames.last {
                    await CognitiveAnchorEngine.shared.setVisionScreenshot(lastFrame)
                }
                
                await MainActor.run {
                    AppState.shared?.lastVideoFrames = frames
                }
                return "[VISION_SEARCH_FLOW: \(query)]\nGoogle search executed. \(frames.count) frames captured via scrolling. Use [VISION_ACT] to click targets or type."
            } catch { return "[VISION ERROR] \(error.localizedDescription)" }

        case .visionSnapshot:
            do {
                let frames = try await SafariVisionBridge.shared.takeMultiFrameScreenshot(frameCount: 4)
                if let lastFrame = frames.last {
                    await CognitiveAnchorEngine.shared.setVisionScreenshot(lastFrame)
                }
                await MainActor.run {
                    AppState.shared?.lastVideoFrames = frames
                }
                return "[VISION_SNAPSHOT]\nCaptured \(frames.count) scrolling frames. Screenshot updated and injected to context."
            } catch { return "[VISION ERROR] \(error.localizedDescription)" }

        case .visionAct(let action):
            do {
                let parts = action.split(separator: " ")
                guard let cmd = parts.first else { return "[VISION ERROR] Empty action" }
                
                let framesBefore = await MainActor.run { AppState.shared?.lastVideoFrames }
                
                if cmd == "click" && parts.count >= 3 {
                    let x = Double(parts[1]) ?? 0.0
                    let y = Double(parts[2]) ?? 0.0
                    
                    if consecutiveClickLoopCount >= 3 {
                        consecutiveClickLoopCount = 0 // reset so it can try elsewhere later
                        return "[VISION ERROR] VISION_BLOCKED: You have clicked near these coordinates multiple times without success (the screen visually did not change). DO NOT click here again. You MUST try a different tool (like scrolling or typing) or ask the human."
                    }
                    
                    try await SafariVisionBridge.shared.hidClick(x: x, y: y)
                } else if cmd == "type" && parts.count >= 2 {
                    let text = action.dropFirst(5).trimmingCharacters(in: .whitespaces)
                    try await SafariVisionBridge.shared.typeText(text)
                } else if cmd == "scroll" {
                    try await SafariVisionBridge.shared.scrollDown()
                }
                
                // Auto-store vision action in JCross memory (L1-L3)
                await MainActor.run {
                    let timeId = String(Int(Date().timeIntervalSince1970))
                    CortexEngine.shared?.remember(
                        key: "vision_log_\(timeId)",
                        value: "Action: [VISION_ACT: \(action)]. The AI executed this action on the browser.",
                        importance: 0.85,
                        zone: .front
                    )
                }
                
                try await Task.sleep(nanoseconds: 2_000_000_000) // Delay for UI reaction / load
                let frames = try await SafariVisionBridge.shared.takeMultiFrameScreenshot(frameCount: 4)
                
                // Visual Similarity Loop Detection
                if cmd == "click", let beforeFrame = framesBefore?.last, let afterFrame = frames.last {
                    let distance = SafariVisionBridge.shared.computeVisualSimilarity(base64A: beforeFrame, base64B: afterFrame)
                    if distance < 10.0 { // threshold for "no significant visual change"
                        consecutiveClickLoopCount += 1
                        
                        // If it's starting to loop, try to scroll-retry automatically
                        if consecutiveClickLoopCount == 2 {
                            try await SafariVisionBridge.shared.scrollDown()
                            try await Task.sleep(nanoseconds: 1_000_000_000)
                            let retryFrames = try await SafariVisionBridge.shared.takeMultiFrameScreenshot(frameCount: 4)
                            if let retryLast = retryFrames.last {
                                await CognitiveAnchorEngine.shared.setVisionScreenshot(retryLast)
                            }
                            await MainActor.run { AppState.shared?.lastVideoFrames = retryFrames }
                            return "[VISION_ACT: \(action)]\nAction performed, but NO VISUAL CHANGE was detected. The system automatically scrolled down to retry. Please find the target in this new view and try clicking again."
                        }
                    } else {
                        consecutiveClickLoopCount = 0
                    }
                }
                
                if let lastFrame = frames.last {
                    await CognitiveAnchorEngine.shared.setVisionScreenshot(lastFrame)
                }
                
                await MainActor.run {
                    AppState.shared?.lastVideoFrames = frames
                }
                
                if cmd == "click" {
                    return """
                    [VISION_ACT: \(action)]
                    Action performed. New screenshot injected.
                    🔴 A red circle shows where your mouse clicked. 
                    If the screen did not change, you probably missed the target.
                    WARNING: If you have already tried clicking here previously and it didn't work, DO NOT click the exact same coordinates again. You MUST adjust the coordinates based on the red cursor's offset from the target.
                    Search for the red cursor in this new screenshot, calculate the offset to the actual target, and try clicking again.
                    Once you successfully hit the target, save the coordinates using [FORGE_SKILL] to make it a one-shot process next time.
                    """
                }

                return "[VISION_ACT: \(action)]\nAction performed. New screenshot injected."
            } catch { return "[VISION ERROR] \(error.localizedDescription)" }

        // ── JCross Memory ─────────────────────────────────────────────────

        case .jcrossQuery(let query):
            return await MainActor.run {
                guard let cortex = CortexEngine.shared else {
                    return "[JCROSS] Memory engine not available"
                }
                let nodes = cortex.recall(for: query, topK: 5)
                if nodes.isEmpty { return "[JCROSS] No memories found for: \(query)" }
                let lines = nodes.map { "• \($0.key): \($0.value)" }.joined(separator: "\n")
                return "[JCROSS MEMORY for: \(query)]\n\(lines)\n[END JCROSS]"
            }

        case .jcrossStore(let key, let value):
            await MainActor.run {
                CortexEngine.shared?.remember(key: key, value: value, importance: 0.8, zone: .near)
            }
            return "✓ Stored in JCross memory: \(key) = \(value.prefix(60))"

        // ── Git / Safety ──────────────────────────────────────────────────

        case .gitCommit(let message):
            let wsPath = await MainActor.run { AppState.shared?.cortexWorkspacePath ?? AppState.shared?.workspaceURL?.path } ?? workspaceURL?.path
            guard let ws = wsPath else { return "✗ Workspace not set." }
            return await runShell("git add -A && git commit -m '\(message.replacingOccurrences(of: "'", with: "\\'"))'",
                                   workingDir: URL(fileURLWithPath: ws))

        case .gitRestore(let path):
            let wsPath = await MainActor.run { AppState.shared?.cortexWorkspacePath ?? AppState.shared?.workspaceURL?.path } ?? workspaceURL?.path
            guard let ws = wsPath else { return "✗ Workspace not set." }
            return await runShell("git restore \(path)", workingDir: URL(fileURLWithPath: ws))

        case .askHuman(let question):
            // Emit as a system event — AgentLoop will pause and return to chat
            await MainActor.run {
                NotificationCenter.default.post(
                    name: .agentAskHuman,
                    object: question
                )
                #if os(macOS)
                NSApp.requestUserAttention(.criticalRequest)
                #endif
            }
            return "ASK_HUMAN_POSTED: \(question)\n[PAUSED — waiting for human response]"

        // ── Self-Fix ──────────────────────────────────────────────────────

        case .applyPatch(let relativePath, let content):
            return await MainActor.run {
                let sanitized = SelfEvolutionEngine.stripCodeFences(from: content)
                SelfEvolutionEngine.shared.registerPatch(for: relativePath, newContent: sanitized)
                return "✅ PATCH_REGISTERED: \(relativePath) (\(sanitized.components(separatedBy: "\n").count) lines)"
            }

        case .buildIDE:
            return await runIDEBuild()

        case .restartIDE:
            await MainActor.run {
                NotificationCenter.default.post(name: .agentRequestsRestart, object: nil)
            }
            return "RESTART_REQUESTED: User will be asked to restart the app."

        // ── Swarm Execution ──────────────────────────────────────────────────────
        
        case .swarmExecute(let instruction):
            let modelId = await MainActor.run { AppState.shared?.activeOllamaModel ?? "gemma" }
            await MainActor.run {
                SwarmEngine.shared.isSwarmActive = true
            }
            let report = await SwarmEngine.shared.executeSwarmMission(instruction: instruction, modelId: modelId) { progress in
                // Progress is logged internally or could be dispatched
            }
            return "✓ [SWARM EXECUTED] Results:\n\(report)"

        // ── Self-Admin (JARVIS) ───────────────────────────────────────────────

        case .setSetting(let key, let value):
            return await MainActor.run {
                guard let state = AppState.shared else {
                    return "✗ AppState not available"
                }
                let result = state.applySetting(key: key, value: value)
                ToastManager.shared.show(
                    "⚙️ AI が設定を変更: \(key) = \(value.prefix(30))",
                    icon: "gearshape.fill",
                    color: .orange,
                    duration: 3.5
                )
                return result
            }

        case .addMCPServer(let name, let command, let mode):
            let execMode: MCPServerConfig.ExecutionMode = (mode == "ai") ? .ai : .human
            let config = MCPServerConfig(name: name, transport: .stdio,
                                         command: command, mode: execMode)
            await MainActor.run { MCPEngine.shared.addServer(config) }
            await MCPEngine.shared.connect(server: config)
            let toolCount = await MainActor.run { MCPEngine.shared.connectedTools.filter { $0.serverName == name }.count }
            await MainActor.run {
                ToastManager.shared.show(
                    "📡 AI が MCP を追加: \(name) (\(toolCount) tools)",
                    icon: "puzzlepiece.extension.fill",
                    color: Color(red: 0.3, green: 0.85, blue: 0.5),
                    duration: 4.0
                )
            }
            return "✓ MCP Server '\(name)' added and connected (\(toolCount) tools discovered)"

        case .removeMCPServer(let name):
            let found = await MainActor.run { () -> Bool in
                guard let id = MCPEngine.shared.servers.first(where: { $0.name == name })?.id else {
                    return false
                }
                MCPEngine.shared.removeServer(id: id)
                ToastManager.shared.show(
                    "🗑️ AI が MCP を削除: \(name)",
                    icon: "minus.circle.fill",
                    color: Color(red: 0.9, green: 0.4, blue: 0.4),
                    duration: 3.0
                )
                return true
            }
            return found
                ? "✓ MCP Server '\(name)' removed"
                : "⚠️ MCP Server '\(name)' not found"

        case .setModel(let modelId):
            return await MainActor.run {
                guard let state = AppState.shared else { return "✗ AppState not available" }
                state.activeOllamaModel = modelId
                state.modelStatus = .ollamaReady(model: modelId)
                UserDefaults.standard.set(modelId, forKey: "active_ollama_model")
                ToastManager.shared.show(
                    "🤖 AI がモデルを切り替え: \(modelId)",
                    icon: "cpu",
                    color: Color(red: 0.5, green: 0.75, blue: 1.0),
                    duration: 3.5
                )
                return "✓ Model switched to '\(modelId)'. Next response will use this model."
            }

        case .pullModel(let modelId):
            return await pullModelWithProgress(modelId)

        case .mcpCall(let serverName, let toolName, let arguments):
            // 必須引数バリデーション — 空引数で MCP プロトコルエラーを起こさないようにガード
            if let argError = validateMCPArguments(server: serverName, tool: toolName, args: arguments) {
                return """
                [MCP ARG ERROR: \(serverName).\(toolName)]
                \(argError)

                正しい呼び出し例:
                [MCP_CALL: \(serverName).\(toolName)]{\"url\": \"https://example.com\"}[/MCP_CALL]

                引数を指定して再度呼び出してください。
                """
            }
            // Route to MCPEngine — handles both stdio and HTTP transports.
            let result = await MCPEngine.shared.callTool(
                serverName: serverName,
                toolName: toolName,
                arguments: arguments
            )
            return "[MCP RESULT: \(serverName).\(toolName)]\n\(result)\n[END MCP RESULT]"

        // ── Skill Library ─────────────────────────────────────────────────

        case .forgeSkill(let name, let description, let tags, let payload):
            // Persist the new skill and update the in-memory index.
            let node = SkillNode(
                name: name,
                description: description,
                version: 1,
                createdAt: Date(),
                updatedAt: Date(),
                tags: tags,
                executionType: .macro,
                payload: payload
            )
            let saved = await SkillLibrary.shared.save(node)
            await MainActor.run {
                ToastManager.shared.show(
                    "🔧 スキル登録: \(name) (v\(saved.version))",
                    icon: "sparkles",
                    color: .orange,
                    duration: 3.0
                )
            }
            return "✓ [Skill Forged] '\(name)' v\(saved.version) — \(payload.count) step(s) saved to ~/.verantyx/skills/"

        case .useSkill(let name, let args):
            guard let skill = await SkillLibrary.shared.skill(named: name) else {
                let available = await SkillLibrary.shared.allNames.joined(separator: ", ")
                return "✗ [Skill Not Found] '\(name)'. Available: \(available.isEmpty ? "(none)" : available)"
            }
            let executor = SkillExecutor()
            // NOTE: onProgress is not available in executor context; use a no-op.
            // Full progress streaming is available when AgentLoop calls SkillExecutor directly.
            let result = await executor.execute(
                skill: skill,
                args: args,
                workspaceURL: workspaceURL,
                onProgress: { _ in }
            )
            return result
        }
    }

    // MARK: - MCP 引数バリデーション
    //
    // 既知の MCP ツールが必須フィールドなしで呼ばれた場合に Protocol Error を防ぐ。
    // 新しいサーバー/ツールを追加する場合はここに requiredKeys を追記してください。
    private func validateMCPArguments(server: String, tool: String, args: [String: Any]) -> String? {
        // URL 必須ツール定義: (serverName部分一致, toolName部分一致, 必須キー一覧)
        let urlRequiredTools: [(server: String, tool: String, keys: [String])] = [
            // Puppeteer
            (server: "puppeteer", tool: "navigate",    keys: ["url"]),
            (server: "puppeteer", tool: "goto",        keys: ["url"]),
            (server: "puppeteer", tool: "screenshot",  keys: []),        // url 不要
            // Playwright
            (server: "playwright", tool: "navigate",   keys: ["url"]),
            (server: "playwright", tool: "goto",       keys: ["url"]),
            // Browser-use
            (server: "browser",    tool: "navigate",   keys: ["url"]),
            (server: "browser",    tool: "open",       keys: ["url"]),
            // Brave Search
            (server: "brave",      tool: "search",     keys: ["query"]),
            (server: "brave-search", tool: "search",   keys: ["query"]),
            // GitHub
            (server: "github",     tool: "search_repositories", keys: ["query"]),
        ]

        let serverLower = server.lowercased()
        let toolLower   = tool.lowercased()

        for entry in urlRequiredTools {
            guard serverLower.contains(entry.server) && toolLower.contains(entry.tool) else { continue }
            for key in entry.keys {
                let value = args[key] as? String ?? ""
                if value.trimmingCharacters(in: .whitespaces).isEmpty {
                    return "必須パラメーター「\(key)」が空です。\n" +
                           "例: [MCP_CALL: \(server).\(tool)]{\"\(key)\": \"値\"}[/MCP_CALL]"
                }
            }
        }
        return nil  // バリデーション通過
    }

    // MARK: - PULL_MODEL: ollama pull with streaming progress

    private func pullModelWithProgress(_ modelId: String) async -> String {
        // Verify ollama is installed
        let which = await runShell("which ollama", workingDir: nil)
        guard which.contains("/ollama") else {
            return "✗ ollama not found. Install from https://ollama.ai and try again."
        }

        // Notify UI that download is starting
        await MainActor.run {
            AppState.shared?.modelStatus = .mlxDownloading(model: modelId)
            AppState.shared?.addSystemMessage("⬇️ Pulling model '\(modelId)'… (this may take several minutes)")
        }

        // Run ollama pull — stream output line by line
        let result = await Task.detached(priority: .userInitiated) { () -> String in
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/bin/zsh")
            process.arguments = ["-c", "ollama pull \(modelId) 2>&1"]

            var env = ProcessInfo.processInfo.environment
            env["PATH"] = (env["PATH"] ?? "/usr/bin:/bin") + ":/usr/local/bin:/opt/homebrew/bin"
            process.environment = env

            let pipe = Pipe()
            process.standardOutput = pipe
            process.standardError  = pipe

            // Use a class to safely capture mutable state across closures
            final class Counter: @unchecked Sendable { var n = 0; var lastLine = "" }
            let counter = Counter()

            pipe.fileHandleForReading.readabilityHandler = { fh in
                let chunk = String(data: fh.availableData, encoding: .utf8) ?? ""
                let lines = chunk.components(separatedBy: "\n").filter { !$0.isEmpty }
                for line in lines {
                    counter.n += 1
                    counter.lastLine = line
                    // Show progress to UI every 10 lines
                    if counter.n % 10 == 0 {
                        let preview = String(line.prefix(80))
                        Task { await MainActor.run {
                            AppState.shared?.addSystemMessage("⬇️ \(preview)")
                        }}
                    }
                }
            }

            do {
                try process.run()
                process.waitUntilExit()
                pipe.fileHandleForReading.readabilityHandler = nil
            } catch {
                return "✗ ollama pull failed: \(error.localizedDescription)"
            }

            if process.terminationStatus == 0 {
                return "✓ Model '\(modelId)' downloaded successfully"
            } else {
                return "✗ ollama pull exited with code \(process.terminationStatus). Last output: \(counter.lastLine)"
            }
        }.value

        // If successful, switch to the new model
        if result.hasPrefix("✓") {
            await MainActor.run {
                guard let state = AppState.shared else { return }
                state.activeOllamaModel = modelId
                state.modelStatus = .ollamaReady(model: modelId)
                UserDefaults.standard.set(modelId, forKey: "active_ollama_model")
                state.addSystemMessage("✅ Model '\(modelId)' is ready. Next response will use this model.")
            }
        } else {
            await MainActor.run {
                AppState.shared?.modelStatus = .error("Pull failed: \(modelId)")
            }
        }

        return result
    }

    // MARK: - SEARCH_MULTI: parallel top-3 URLs

    private func executeSearchMulti(query: String) async -> String {
        // Step 1: get search result page
        let primary = await WebSearchEngine.shared.search(query: query)
        let primaryText = primary.contextSnippet

        // Step 2: extract additional URLs from the search result
        let urls = extractURLs(from: primaryText, limit: 2)

        var parts: [String] = ["[Source 1: \(primary.url)]\n\(String(primaryText.prefix(800)))"]

        // Step 3: fetch additional URLs in parallel
        await withTaskGroup(of: (Int, String).self) { group in
            for (i, url) in urls.enumerated() {
                group.addTask {
                    let r = await WebSearchEngine.shared.browse(url: url, preferredSource: .safari)
                    return (i + 2, "[Source \(i+2): \(r.url)]\n\(String(r.contextSnippet.prefix(600)))")
                }
            }
            for await (_, text) in group {
                parts.append(text)
            }
        }

        let synthesis = parts.joined(separator: "\n---\n")

        // Auto-save to JCross
        let summary = String(primaryText.prefix(150))
        await persistSearchResult(key: "search_\(query.prefix(30))", value: summary)

        return """
        [SEARCH_MULTI RESULTS for: \(query)]
        \(synthesis)
        [END SEARCH_MULTI]
        Synthesize the above sources to answer the question.
        """
    }

    private func extractURLs(from text: String, limit: Int) -> [String] {
        let pattern = #"https?://[^\s\]<"')>]+"#
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return [] }
        let matches = regex.matches(in: text, range: NSRange(text.startIndex..., in: text))
        return Array(matches.prefix(limit).compactMap { m -> String? in
            Range(m.range, in: text).map { String(text[$0]) }
        })
    }

    // MARK: - Directory tree

    private func buildDirectoryTree(url: URL, depth: Int, maxDepth: Int) -> String {
        guard depth <= maxDepth else { return "" }
        let indent = String(repeating: "  ", count: depth)
        var result = "\(indent)\(url.lastPathComponent)/\n"

        guard let contents = try? fileManager.contentsOfDirectory(
            at: url, includingPropertiesForKeys: [.isDirectoryKey],
            options: [.skipsHiddenFiles]
        ) else { return result }

        let sorted = contents.sorted { $0.lastPathComponent < $1.lastPathComponent }
        for item in sorted.prefix(50) {  // cap at 50 per dir
            let isDir = (try? item.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) ?? false
            if isDir {
                result += buildDirectoryTree(url: item, depth: depth + 1, maxDepth: maxDepth)
            } else {
                result += "\(indent)  \(item.lastPathComponent)\n"
            }
        }
        return result
    }

    // MARK: - JCross auto-persistence

    private func persistSearchResult(key: String, value: String) async {
        await MainActor.run {
            CortexEngine.shared?.remember(
                key: key,
                value: value,
                importance: 0.72,
                zone: .near
            )
        }
    }

    // MARK: - Shell execution

    private func resolve(_ path: String, workspace: URL?) -> URL {
        // Absolute paths go as-is
        if path.hasPrefix("/") { return URL(fileURLWithPath: path) }
        
        // Workspace-relative (most common in agent context)
        if let ws = workspace { return ws.appendingPathComponent(path) }
        
        // Fallback: use /tmp
        return URL(fileURLWithPath: "/tmp").appendingPathComponent(path.hasPrefix("~/") ? String(path.dropFirst(2)) : path)
    }

    private func runShell(_ command: String, workingDir: URL?) async -> String {
        let fallbackDir = await MainActor.run { AppState.shared?.cortexWorkspacePath.map { URL(fileURLWithPath: $0) } } ?? URL(fileURLWithPath: "/tmp")
        return await Task.detached(priority: .userInitiated) {
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/bin/zsh")
            process.arguments = ["-c", command]
            process.currentDirectoryURL = workingDir ?? fallbackDir

            var env = ProcessInfo.processInfo.environment
            env["PATH"] = (env["PATH"] ?? "/usr/bin:/bin") + ":/usr/local/bin:/opt/homebrew/bin"
            process.environment = env

            let stdoutPipe = Pipe(); let stderrPipe = Pipe()
            process.standardOutput = stdoutPipe
            process.standardError  = stderrPipe

            let timeoutTask = Task {
                try? await Task.sleep(nanoseconds: 45_000_000_000) // 45 seconds timeout
                if process.isRunning {
                    process.terminate()
                }
            }

            let startTime = CFAbsoluteTimeGetCurrent()
            do { try process.run() } catch { return "✗ Could not launch: \(error)" }
            let out = String(data: stdoutPipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
            let err = String(data: stderrPipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
            process.waitUntilExit()
            timeoutTask.cancel()
            let executionTimeMs = Int((CFAbsoluteTimeGetCurrent() - startTime) * 1000)

            var result = ""
            if !out.isEmpty { result += out.trimmingCharacters(in: .newlines) }
            if !err.isEmpty { result += (result.isEmpty ? "" : "\n") + "[stderr] " + err.trimmingCharacters(in: .newlines) }
            
            if process.terminationReason == .uncaughtSignal {
                result += "\n[exit: timeout (45s) or killed]"
            } else {
                result += "\n[exit: \(process.terminationStatus)]"
            }
            
            // Append Visceral Metadata
            result += "\n[VISCERAL_METADATA: {\"execution_time_ms\": \(executionTimeMs), \"cpu_spike\": \(executionTimeMs > 200 ? "true" : "false")}]"
            return result
        }.value
    }

    // MARK: - IDE Build

    private func runIDEBuild() async -> String {
        let wsPath = await MainActor.run { AppState.shared?.cortexWorkspacePath ?? AppState.shared?.workspaceURL?.path }
        guard let ws = wsPath else { return "BUILD_ERROR: Workspace not set." }
        let u = URL(fileURLWithPath: ws)
        let baseDir = u.lastPathComponent == "VerantyxIDE" ? u : u.appendingPathComponent("VerantyxIDE")
        let projectPath = baseDir.appendingPathComponent("Verantyx.xcodeproj").path
        return await Task.detached(priority: .userInitiated) {
            guard FileManager.default.fileExists(atPath: projectPath) else {
                return "BUILD_ERROR: Verantyx.xcodeproj not found at \(projectPath)."
            }
            let cmd = """
            export PATH="$PATH:/opt/homebrew/bin"
            xcodebuild \
              -project '\(projectPath)' \
              -scheme Verantyx \
              -destination 'platform=macOS,arch=arm64' \
              CODE_SIGN_IDENTITY="" CODE_SIGNING_REQUIRED=NO \
              build \
              2>&1 | grep -E '\\.swift:[0-9]+:[0-9]+: (error|warning):|BUILD SUCCEEDED|BUILD FAILED' \
                   | grep -v 'objc\\|deprecated' \
                   | head -40
            """
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/bin/zsh")
            process.arguments = ["-c", cmd]
            let pipe = Pipe()
            process.standardOutput = pipe; process.standardError = pipe
            do { try process.run() } catch { return "BUILD_ERROR: \(error.localizedDescription)" }
            let raw = String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
            process.waitUntilExit()
            let output = String(raw.prefix(3000))
            if output.contains("BUILD SUCCEEDED") { return "BUILD SUCCEEDED ✅" }
            return "BUILD FAILED ❌\nErrors:\n\(output.isEmpty ? "(no output)" : output)\nFix errors with [APPLY_PATCH] and run [BUILD_IDE] again."
        }.value
    }
}

// MARK: - Notification names

extension Notification.Name {
    static let agentRequestsRestart = Notification.Name("VerantyxAgentRequestsRestart")
    static let agentAskHuman        = Notification.Name("VerantyxAgentAskHuman")  // NEW
}
