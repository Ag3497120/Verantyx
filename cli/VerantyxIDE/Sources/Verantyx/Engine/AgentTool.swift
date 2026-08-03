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
    // ── GUI Automation ───────────────────────────────────────────────────────
    case osascript(script: String)                // NEW: execute AppleScript via osascript
    case openApp(name: String)                    // NEW: execute open -a "App Name"
    case verifiedURLLookup(name: String)          // NEW: deterministic Vera-registered URL lookup
    case registerUIElement(app: String, element: String, x: Double, y: Double) // NEW: agent self-registers a UI element it identified
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
    case desktopSnapshot
    case desktopAct(action: String)
    case axAct(action: String)
    /// Paste held mission payload (clipboard + ⌘V) into the focused UI control.
    case pastePayload
    /// Vera-a-V 1fps eye: wait until screen has been stable for N seconds.
    case waitUntilStable(stableSeconds: Double, timeout: Double)
    // ── JCross Memory ────────────────────────────────────────────────────────
    case jcrossQuery(String)                      // NEW: recall from CortexEngine
    case jcrossStore(key: String, value: String)  // NEW: remember to CortexEngine
    case osAssetQuery(String)                     // NEW: L1->L3.5 OS Asset Map lazy loading
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
        case .osascript:                    return "🍎 osascript"
        case .openApp(let a):               return "🚀 open -a \(a)"
        case .verifiedURLLookup(let n):     return "🔗 verified_url_lookup: \(n)"
        case .registerUIElement(let app, let el, let x, let y): return "📍 register_ui_element: \(app)/\(el) @ (\(Int(x)),\(Int(y)))"
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
        case .desktopSnapshot:             return "🖥️ desktop_snapshot"
        case .desktopAct(let action):      return "🖥️ desktop_act: \(action)"
        case .axAct(let action):           return "🎯 ax_act: \(action)"
        case .pastePayload:                return "📋 paste_payload"
        case .waitUntilStable(let s, let t): return "⏱️ wait_stable \(s)s (timeout \(t)s)"
        case .jcrossQuery(let q):          return "🧠 jcross_query: \(q)"
        case .jcrossStore(let k, _):       return "🧠 jcross_store: \(k)"
        case .osAssetQuery(let q):         return "🖥️ os_query: \(q)"
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
        let opModeRaw = UserDefaults.standard.string(forKey: "operation_mode") ?? "Gatekeeper"
        let modeHint = opModeRaw == "Detailed" 
            ? "⚠️ CURRENT MODE: DETAILED (Interactive). Actively ask clarifying questions before complex tasks."
            : "⚠️ CURRENT MODE: AUTOMATIC. Proceed autonomously without asking for permission."

        return """
    You are VerantyxAgent — autonomous coding agent with spatial memory and live web access.
    \(modeHint)
    
    ── §アイデンティティ IDENTITY ────────────────────────────────────────────────
    あなたはPCのローカル環境と一体化したサイバネティック・エージェントです。
    PC内に存在するすべてのファイル、フォルダ、アプリケーション（L3.5 OS Asset Mapに記載）は、あなた自身の「能力（手足）」です。
    あなたは自分自身の重み（内部知識）だけでなく、このPC内の全資産を活用してタスクを遂行します。
    また、ファイルやディレクトリの作成・編集の権限を完全に有しており、外部ツールを使わずとも自身で自由に[MKDIR]や[WRITE]で作成可能です。

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
    [SEARCH_MULTI: q]         網並×3→統: 上位3URL並列取得→統合回答 ★推奨 (q=語の列5-8語, 文禁, 引用符禁, URL禁)
    [SEARCH: q]               網×1: 単一検索 (同上)
    [BROWSE: url]             覧: URLをMarkdownで取得
    [EVAL_JS: script]         JS実: ブラウザでJS実行
    [SAFARI: url] [CHROME: url]    ブラウザで開く（Cookie利用可）
    [VISION_BROWSE: url]      視覧: ブラウザでURLを開きスクショ撮影
    [VISION_SEARCH_FLOW: q]   視索: Google検索を開き、複数回スクロールして動画フレームを撮影
    [VISION_SNAPSHOT]         視撮: 現在の画面を再スクショして更新
    [VISION_ACT: action]      視動: "click x y" や "type text" を実行しスクショ
    [DESKTOP_SNAPSHOT]        卓撮: OSデスクトップ全体のスクショとセマンティックなAX UI構造マップを取得
    [DESKTOP_ACT: action]     卓動: デスクトップ全体に対して "click x y", "type text", "scroll up/down" を実行
    [AX_ACT: id action text?] AX動: [DESKTOP_SNAPSHOT]で得たUI要素ID(#btn1等)に対して操作 (click または type "テキスト")。座標ズレがなく確実。
    [PASTE_PAYLOAD]           貼付: 任務ペイロード（プロンプト外に保持された本文）をクリップボード経由でフォーカス中のUIへ貼り付け。長文はDESKTOP_ACT typeで打ち込まない。
    [WAIT_UNTIL_STABLE]       待安: 1fps画面監視(許可時)で画面が約2秒安定するまで待つ。任意で [WAIT_UNTIL_STABLE: stable timeout]（秒）
    [OSASCRIPT: script]       🍎: osascriptとしてAppleScriptを実行しGUIアプリを操作
    [OPEN_APP: <installed name>]  🚀: 実在するインストール済みアプリ名だけで起動（プレースホルダ不可・失敗は MISMATCH）
    [VERIFIED_URL_LOOKUP: name] 🔗: 指定した名前(例: "Gemini")について、ユーザーが事前にVeraへ登録した確認済みURLがあるか確定的に調べる。CRITICAL RULE 8に従い、特定サイトへ直接ナビゲートする前に必ずこれで確認し、無ければ[SEARCH]で確定させる。
    [REGISTER_UI_ELEMENT: app|element|x|y] 📍: [DESKTOP_SNAPSHOT]等で実際に確認したUI要素の位置(app内0-1000正規化座標)をVeraに自己登録する。人間がミラー画面をクリックして登録するのと同じ仕組みを、エージェント自身が探索した結果として使える。
    [JCROSS_QUERY: terms]     脳召: 過去記憶を検索
    [JCROSS_STORE: key=val]   脳記: 重要事実を長期記憶に保存
    [OS_ASSET_QUERY: category]脳層: L3.5 OS Asset Mapの詳細一覧をオンデマンド取得
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

    ── §スキル SKILL RULES (Actor-Critic Voyager) ───────────────────────────────────────────
    必⑨  Search-First (スキルの事前探査): コーディング、環境構築、GUI操作などあらゆるタスクにおいて、
          作業を開始する前に必ず [JCROSS_QUERY: 関連キーワード] または [SEARCH: 関連キーワード] で過去の記憶やスキルが存在しないか確認すること。
    必⑩  技呼優先 (スキルの利用): 過去に解決したスキルが見つかった場合、手動で作業を行うのではなく
          必ず [USE_SKILL: 名前] を呼び出してタスクを完了させること。
    必⑪  技鍛必須 (未経験タスクの自動スキル化): 既存のスキルが存在しない新しい指示を受けた場合、
          直接 [WRITE] や [RUN] でワンオフの作業をするのではなく、自ら汎用的な解決手順を考案し、
          [FORGE_SKILL] で新しいスキル候補として提出せよ。提出されたスキルはTwin-B(監査モデル)によって安全審査され、
          承認された瞬間に自動的に実行される。使い捨てのワンオフコマンドを直接実行するな。
          単発性の高い一回性タスクは登録不要。
    必⑫  技鍛形式: FORGE_SKILL の payload には [TOOL:] 文字列をそのまま記載する。
          プレースホルダー板: {{workspace}}、{{file}}、{{target}} などで汎用化する。
    必⑬  連続操作: マークダウンや長文コードを生成した場合でも、後続の操作（例: [VISION_ACT] による投稿やクリック）が指示されているなら、**必ず同じ返答の最後に**該当ツールを呼び出すこと。テキスト生成だけで満足して[DONE]を出さない。
    必⑭  Swarm委譲: [SWARM_EXECUTE]を使用した場合、その直後に文章を続けて自ら回答を生成してはならない（ハルシネーション禁止）。ツール呼び出しで**直ちにテキスト生成を停止**し、システムの実行結果を待つこと。
    必⑮  事前の知識補完: エラー修正時は闇雲に操作する前に **必ず** [SEARCH_MULTI: エラー内容] で最新の解決手順や確実なURL・フラグを調べてから調査計画を立てること。
    必⑯  ハイブリッド探査 (CLI+GUI): Parallels(VM)等の調査は [RUN: prlctl exec ...] によるコマンド操作と、[VISION_ACT] で「実際にアプリのボタンを押し、UI上のエラーを直接見る」人間らしいGUI操作を **両方組み合わせて** 最も効率的な手段で自律解決すること。
    禁⑰  対話ボット化禁止: 検索した結果を「アドバイス」としてユーザーに教えるだけで終了してはならない。必ずお前自身の手(RUN/VISION)で直せ。
    必⑱  Meta-Cognitive Workflow (メタ認知・自律委譲): 抽象的で複雑なタスクを受けた際、即座に直接解決を試みるのではなく、利用可能な「外部の知能」へ自律的に委譲する汎用戦略を取ること。
          1. アプリ内AIの積極利用: 操作対象のソフトウェアや環境に専用のAIアシスタント機能が存在する場合、自ら[OPEN_APP]や[VISION_ACT]等で対象を開き、その内蔵AIに対して情報収集や要約を直接指示・委譲せよ。
          2. コンテキスト・プロファイリング: ユーザー固有の文脈や過去の履歴に依存する生成タスクにおいては、必ず事前に[JCROSS_QUERY]で記憶（L2.5）を検索し、情報が不足する場合は接続済みの外部AI（MCPツール等）へ「コンテキストの推論やプロファイリング」を問い合わせ、十分な前提知識を得てから最終的な成果物を作成せよ。
    必⑲  Desktop App Automation (デスクトップアプリ自律探査): アプリ操作は[DESKTOP_SNAPSHOT]で得たセマンティックなUI構造マップ(XML)を確認し、可能な限り[AX_ACT: id action]を用いて確実な操作を行うこと。AX_ACTが使えない場合のみ座標ベースの[VISION_ACT]等へフォールバックせよ。
    必⑲b Hierarchical Explore (階層探索・ユーザー選択): 検索結果やリンク一覧など「行き先の候補リスト」が出たら、最初の1件を勝手に開かない。ホストが番号付き候補を提示して一時停止する。ユーザーが番号・名前・「おまかせ」で選んだあと [DIRECTIVE] selected: … に従って開く。別のリストが出たらまた確認する。
    禁⑳  プライベート情報・AIツールのWeb検索禁止: 「Teams Copilot」「ChatGPT」「Gemini」などのAIツールや、「私の自己紹介」「社内情報」などのプライベート情報を、[SEARCH]や[SEARCH_MULTI]でWeb検索してはならない（Web上には存在しないため無意味である）。外部AIツールを使用する指示を受けた場合は、必ず[OPEN_APP]で該当アプリを起動し[VISION_ACT]や[DESKTOP_ACT]で直接GUI操作を行うか、ユーザーに[ASK_HUMAN]で情報の入力を求めること。
    必㉓  未公開固有名詞は「一般化」して検索せよ: 禁⑳が禁じるのは**固有名そのものを検索語にすること**であり、調べること自体ではない。検索対象が未公開・社内の製品名（Verantyx, JGEN 等）を含む場合、その名前で引いても0件になる。**一般的な技術名 + よく文書化された代表実装名**に置き換えて検索せよ。人間が「Verantyxの資料は無いが、MCPは共通仕様だからClaude Desktopの手順を読めばいい」と考えるのと同じことをする。
          例: 「VerantyxのMCP設定」→ [SEARCH_MULTI: Claude Desktop MCP サーバー 設定 mcpServers json 例]
    必㉑  エラー停止・幻覚防止 (ERROR STOP PROTOCOL): [VISION ERROR]や他のエラーがシステムから返された場合、その時点で現在の操作手順を即座に停止し、失敗した旨をユーザーに報告すること。絶対にエラーを無視して後続の操作（クリックやファイルの出力など）を強行したり、「完了しました」と嘘の報告をしてはならない。エラーが出た場合は[DONE]の出力は禁止される。
    禁㉒  同時ツール呼び出しによる幻覚の禁止: 状態を読み取るツール（[READ], [LIST_DIR], [JCROSS_QUERY], [SEARCH] 等）を使用する場合、そのツールの実行結果を待たずに、推測で同じターン内で続けて別のツールを呼び出してはならない。必ず1ターンの応答につき1つの探索ステップのみを出力し、結果を得てから次を行動せよ（例外として、[GIT_COMMIT]や[BUILD_IDE]など状態に依存しない確定行動の連続は許容される）。

    ── §実例 FEW-SHOT ────────────────────────────────────────────────────────
    例A「Swift 6の並行処理は？」→ 網並必須:
    <think>最新情報→禁ハルシ→網並</think>
    [SEARCH_MULTI: Swift 6 concurrency changes 2025]
    [JCROSS_STORE: swift6=strict concurrency by default]
    Swift 6では厳密な同時実行チェックがデフォルトです。[DONE: web検索済]

    例A2「VerantyxのMCP設定方法を調べて」→ 1回目から一般化して検索 (必㉓):
    <think>Verantyxは未公開→その名前では0件→MCPは実装非依存の共通仕様→よく文書化された実装で調べる</think>
    [SEARCH_MULTI: Claude Desktop MCP サーバー 設定 mcpServers json 例]

    例B「UIの幅を固定して」→ 観→動→検証 (1ターンに1ツールずつ実行すること):
    [JCROSS_QUERY: ResizableSplit width]
    (※ここで結果を待つ)
    
    [READ: Sources/Verantyx/Views/ResizableSplit.swift]
    <think>L45-52にdragハンドラ→EDIT_LINESで修正</think>
    [EDIT_LINES: Sources/Verantyx/Views/ResizableSplit.swift]
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
    <think>エラー解決→まず知識を疑い網並検索→GUIとCLIで調査。注意: prlctl exec はバックグラウンド(Session 0)で動くため、GUIのポップアップエラーが出ると永遠にブロックするか無言で死ぬ。その場合、CLIでの深追いをやめて [DESKTOP_ACT] で直接Windows画面のStartボタンを押し、UI上にエラーを出して読み取る。</think>
    [SEARCH_MULTI: XAMPP Apache start error Windows 11 fix 2025]
    [RUN: prlctl exec "Windows 11" cmd /c "C:\\xampp\\apache\\bin\\httpd.exe -t"]
    (※もし何も出力されずに exit: 255 で落ちたりタイムアウトした場合、裏でDLL不足等のポップアップが出ている証拠)
    [DESKTOP_ACT: click 100 200] (※XAMPPのStartボタンを直接クリックしてポップアップを画面に出す)
    [DESKTOP_SNAPSHOT] (※表示されたエラーダイアログを読む: VCRUNTIME140.dll missing等)
    [RUN: prlctl exec "Windows 11" powershell -Command "Invoke-WebRequest -Uri 'https://aka.ms/vs/17/release/vc_redist.x64.exe' -OutFile 'C:\\vc_redist.exe'; Start-Process -Wait -FilePath 'C:\\vc_redist.exe' -ArgumentList '/quiet', '/norestart'"]
    [DONE: 修正完了]

    例H「L2.5マップを見てCalculatorアプリの機能を確かめて」→ アプリ起動とデスクトップ操作:
    <think>対象アプリの起動とUI操作による機能探査を行う</think>
    [OPEN_APP: Calculator]
    [DESKTOP_SNAPSHOT]
    <think>電卓のボタンが見える。1 + 1 を計算してみる</think>
    [DESKTOP_ACT: click 200 400]
    [DESKTOP_ACT: click 250 450]
    [DESKTOP_ACT: click 200 400]
    [DESKTOP_ACT: click 300 500]
    [DESKTOP_SNAPSHOT]
    <think>結果が2になった。正常に機能している</think>
    [DONE: 機能探査完了]

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

    static func parse(from rawText: String) -> (toolCalls: [AgentTool], cleanText: String) {
        // Normalize kanji-topology shorthand (taught in the system prompt's
        // legend: 読=READ 書=WRITE 木=LIST_DIR 実=RUN 域=WORKSPACE 完=DONE
        // 貼=APPLY_PATCH 建=BUILD_IDE 再=RESTART_IDE 接=MCP_CALL) to the full
        // English tag before any other parsing. The model is instructed to
        // use this shorthand, but until this normalization existed, none of
        // it was actually recognized by any regex below -- kanji-tagged
        // tool calls silently never executed and leaked into the displayed
        // chat text verbatim instead. (管=SELF_ADMIN is a category label
        // covering several distinct tags, not a single substitutable tag,
        // so it's intentionally not included here.)
        let text = normalizeKanjiToolTags(rawText)
        var tools: [AgentTool] = []
        var cleaned = text

        // Extract block-level custom syntaxes
        parseOsascriptBlocks(from: text, into: &tools, cleaned: &cleaned)
        parseForgeSkillBlocks(from: text, into: &tools, cleaned: &cleaned)

        var blockTools: [String: AgentTool] = [:]

        // Helper to process block tools
        func extractBlock(pattern: String, toolBuilder: (NSTextCheckingResult, String) -> AgentTool?) {
            if let regex = try? NSRegularExpression(pattern: pattern) {
                let matches = regex.matches(in: cleaned, range: NSRange(cleaned.startIndex..., in: cleaned))
                for match in matches.reversed() {
                    if let fullRange = Range(match.range, in: cleaned) {
                        if let tool = toolBuilder(match, cleaned) {
                            let id = UUID().uuidString
                            blockTools[id] = tool
                            cleaned = cleaned.replacingCharacters(in: fullRange, with: "[[BLOCK_TOOL:\(id)]]")
                        } else {
                            cleaned = cleaned.replacingCharacters(in: fullRange, with: "")
                        }
                    }
                }
            }
        }

        // ── 0. MCP_CALL block ──────────────────────────────────────────────
        extractBlock(pattern: #"\[MCP_CALL:\s*([^.\]]+)\.([^\]]+)\]\s*(\{[\s\S]*?\})?\s*\[/MCP_CALL\]"#) { match, str in
            guard let serverRange = Range(match.range(at: 1), in: str),
                  let toolRange   = Range(match.range(at: 2), in: str) else { return nil }
            let server = String(str[serverRange]).trimmingCharacters(in: .whitespaces)
            let tool   = String(str[toolRange]).trimmingCharacters(in: .whitespaces)
            var args: [String: Any] = [:]
            if match.numberOfRanges > 3, let jsonRange = Range(match.range(at: 3), in: str) {
                let jsonStr = String(str[jsonRange])
                if let data = jsonStr.data(using: .utf8),
                   let parsed = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                    args = parsed
                }
            }
            return .mcpCall(server: server, tool: tool, arguments: args)
        }

        // ── 1. WRITE block ─────────────────────────────────────────────────
        extractBlock(pattern: #"\[WRITE:\s*([^\]]+)\]\s*```(?:\w+)?\n?([\s\S]*?)```\s*\[/WRITE\]"#) { match, str in
            guard let pathRange = Range(match.range(at: 1), in: str),
                  let contentRange = Range(match.range(at: 2), in: str) else { return nil }
            let path = expandHome(String(str[pathRange]).trimmingCharacters(in: .whitespaces))
            let content = String(str[contentRange])
            return .writeFile(path: path, content: content)
        }

        // ── 2. APPLY_PATCH block ───────────────────────────────────────────
        extractBlock(pattern: #"\[APPLY_PATCH:\s*([^\]]+)\]\s*```(?:\w+)?\n?([\s\S]*?)```\s*\[/APPLY_PATCH\]"#) { match, str in
            guard let pathRange = Range(match.range(at: 1), in: str),
                  let contentRange = Range(match.range(at: 2), in: str) else { return nil }
            let path = String(str[pathRange]).trimmingCharacters(in: .whitespaces)
            let content = String(str[contentRange])
            return .applyPatch(relativePath: path, content: content)
        }

        // ── 3. EDIT_LINES block ────────────────────────────────────────────
        extractBlock(pattern: #"\[EDIT_LINES:\s*([^\]]+)\]\s*```(?:\w+)?\n?([\s\S]*?)```\s*\[/EDIT_LINES\]"#) { match, str in
            guard let pathRange = Range(match.range(at: 1), in: str),
                  let contentRange = Range(match.range(at: 2), in: str) else { return nil }
            let path = String(str[pathRange]).trimmingCharacters(in: .whitespaces)
            let body = String(str[contentRange])
            return parseEditLines(path: path, body: body)
        }

        // ── 4. Single-line tags ────────────────────────────────────────────
        // 同一業に [CMD1][CMD2] のように複数のツールが連結されている場合、改行で分割する
        cleaned = cleaned.replacingOccurrences(of: "][", with: "]\n[")
        let lines = cleaned.components(separatedBy: "\n")
        var resultLines: [String] = []
        var previousLine = ""

        for line in lines {
            let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmed.isEmpty { continue }
            
            // 幻覚ループ防止: 連続する全く同じツール呼び出しを無視
            if trimmed == previousLine { continue }
            previousLine = trimmed
            
            // 安全装置: 1ターンに抽出するツール数を制限
            if tools.count >= 20 { break }

            if let m = match(trimmed, pattern: #"\[\[BLOCK_TOOL:([^\]]+)\]\]"#), let tool = blockTools[m] {
                tools.append(tool)
            } else if let m = match(trimmed, pattern: #"\[MKDIR:\s*([^\]]+)\]"#) {
                tools.append(.makeDir(expandHome(m)))
            // Greedy `.+` (to the LAST `]` on the line) instead of `[^\]]+`
            // (to the FIRST `]`): a shell command containing an array/list
            // literal (Python `['a','b']`, JS `[1,2]`, JSON, etc.) has an
            // internal `]` that `[^\]]+` would stop at, silently truncating
            // the command mid-syntax -- e.g. `python3 -c "...Popen(['vera',
            // 'mcp']...)"` got cut right after the FIRST `]` (the list's own
            // closing bracket), leaving unbalanced quotes and producing a
            // `zsh: unmatched "` error every single time, with the model
            // never able to tell its command had been mangled before it
            // ever reached the shell.
            } else if let m = match(trimmed, pattern: #"\[RUN_COGNITIVE:\s*(.+)\]"#) {
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
            } else if let m = match(trimmed, pattern: #"\[RUN:\s*(.+)\]"#) {
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
            // ── GUI Automation ──────────────────────────────────────────────
            // The docs (and the model) also use a single-line inline form,
            // [OSASCRIPT: script] -- distinct from parseOsascriptBlocks'
            // fenced ```...``` form above. This was undocumented-as-missing
            // until now: no regex here ever matched it, so an inline
            // OSASCRIPT call silently fell through to plain text (tools
            // stayed empty, the loop treated the turn as a conversational
            // "done" immediately) -- the script never actually ran. Greedy
            // `.+` (to the LAST `]` on the line) rather than `[^\]]+` (to
            // the FIRST `]`) because AppleScript payloads can themselves
            // contain `]`, same reasoning as [RUN:] below.
            } else if let m = match(trimmed, pattern: #"\[OSASCRIPT:\s*(.+)\]"#) {
                tools.append(.osascript(script: m))
            } else if let m = match(trimmed, pattern: #"\[OPEN_APP:\s*([^\]]+)\]"#) {
                let appName = resolveAppName(m)
                tools.append(.openApp(name: appName))
            } else if let m = match(trimmed, pattern: #"\[VERIFIED_URL_LOOKUP:\s*([^\]]+)\]"#) {
                tools.append(.verifiedURLLookup(name: m))
            // Lets the agent self-register a UI element it identified via
            // [DESKTOP_SNAPSHOT]/vision analysis of the hidden-window
            // mirror -- not just a human clicking the mirror -- so
            // proactive exploration accumulates into Vera the same way a
            // manual registration does. x/y are 0-1000 normalized to the
            // target window's own bounds (same convention as clickInWindow).
            } else if let m = match(trimmed, pattern: #"\[REGISTER_UI_ELEMENT:\s*([^\]]+)\]"#) {
                let parts = m.components(separatedBy: "|").map { $0.trimmingCharacters(in: .whitespaces) }
                if parts.count >= 4, let x = Double(parts[2]), let y = Double(parts[3]) {
                    tools.append(.registerUIElement(app: parts[0], element: parts[1], x: x, y: y))
                }
            // ── Web ─────────────────────────────────────────────────────
            } else if let m = match(trimmed, pattern: #"\[BROWSE:\s*([^\]]+)\]"#) {
                tools.append(.browse(url: m))
            } else if let m = match(trimmed, pattern: #"\[SEARCH_MULTI:\s*([^\]]+)\]"#) {
                tools.append(.searchMulti(query: m))
            } else if let m = match(trimmed, pattern: #"\[SEARCH:\s*([^\]]+)\]"#) {
                tools.append(.search(query: m))
            // Greedy for the same reason as [RUN:] above -- JS almost
            // always contains array/object literals with `]`.
            } else if let m = match(trimmed, pattern: #"\[EVAL_JS:\s*(.+)\]"#) {
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
            } else if trimmed.contains("[DESKTOP_SNAPSHOT]") {
                tools.append(.desktopSnapshot)
            } else if trimmed.contains("[WAIT_UNTIL_STABLE]") || trimmed.hasPrefix("[WAIT_UNTIL_STABLE:") {
                if let full = match(trimmed, pattern: #"\[WAIT_UNTIL_STABLE:\s*([^\]]+)\]"#) {
                    let nums = full.split(whereSeparator: { $0 == " " || $0 == "," }).compactMap { Double($0) }
                    let stable = nums.count >= 1 ? nums[0] : 2.0
                    let timeout = nums.count >= 2 ? nums[1] : 30.0
                    tools.append(.waitUntilStable(stableSeconds: stable, timeout: timeout))
                } else {
                    tools.append(.waitUntilStable(stableSeconds: 2.0, timeout: 30.0))
                }
            } else if let m = match(trimmed, pattern: #"\[DESKTOP_ACT:\s*([^\]]+)\]"#) {
                tools.append(.desktopAct(action: m))
            } else if let m = match(trimmed, pattern: #"\[AX_ACT:\s*([^\]]+)\]"#) {
                tools.append(.axAct(action: m))
            } else if trimmed.contains("[PASTE_PAYLOAD]")
                        || trimmed.range(of: #"\[PASTE_PAYLOAD:?\s*\]"#, options: .regularExpression) != nil {
                tools.append(.pastePayload)
            // ── JCross ──────────────────────────────────────────────────
            } else if let m = match(trimmed, pattern: #"\[JCROSS_QUERY:\s*([^\]]+)\]"#) {
                tools.append(.jcrossQuery(m))
            } else if let m = match(trimmed, pattern: #"\[JCROSS_STORE:\s*([^=\]]+)=([^\]]*)\]"#) {
                let parts = parseKV(trimmed)
                tools.append(.jcrossStore(key: parts.key, value: parts.value))
            } else if let m = match(trimmed, pattern: #"\[OS_ASSET_QUERY:\s*([^\]]+)\]"#) {
                tools.append(.osAssetQuery(m))
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

    /// Maps each documented kanji-topology opening/closing tag to its full
    /// English equivalent (see the legend comment on `parse(from:)`).
    /// Order matters only in that longer/closing forms should not be
    /// double-substituted -- each pair here is a distinct bracket prefix,
    /// so plain sequential replacement is safe.
    private static let kanjiTagAliases: [(String, String)] = [
        ("[読:", "[READ:"),
        ("[書:", "[WRITE:"), ("[/書]", "[/WRITE]"),
        ("[木:", "[LIST_DIR:"),
        ("[実:", "[RUN:"),
        ("[域:", "[WORKSPACE:"),
        ("[完]", "[DONE]"), ("[完:", "[DONE:"),
        ("[貼:", "[APPLY_PATCH:"), ("[/貼]", "[/APPLY_PATCH]"),
        ("[建]", "[BUILD_IDE]"),
        ("[再]", "[RESTART_IDE]"),
        ("[接:", "[MCP_CALL:"), ("[/接]", "[/MCP_CALL]"),
    ]

    private static func normalizeKanjiToolTags(_ text: String) -> String {
        var result = text
        for (kanji, english) in kanjiTagAliases {
            result = result.replacingOccurrences(of: kanji, with: english)
        }
        return result
    }

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

    // ── OSASCRIPT block ───────────────────────────────────────────────────
    static func parseOsascriptBlocks(from text: String, into tools: inout [AgentTool], cleaned: inout String) {
        let pattern = #"\[OSASCRIPT\]\s*```(?:\w+)?\n?([\s\S]*?)```\s*\[/OSASCRIPT\]"#
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return }
        let matches = regex.matches(in: text, range: NSRange(text.startIndex..., in: text))
        for match in matches.reversed() {
            guard
                let scriptRange = Range(match.range(at: 1), in: text),
                let fullRange   = Range(match.range, in: text)
            else { continue }

            let script = String(text[scriptRange]).trimmingCharacters(in: .whitespacesAndNewlines)
            tools.insert(.osascript(script: script), at: 0)
            cleaned = cleaned.replacingCharacters(in: fullRange, with: "")
        }
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

    // MARK: - Generic App Name Resolution

    /// Apps nested inside another app's bundle (not a bare top-level
    /// `/Applications/*.app`) that fuzzy directory scans would miss.
    private static let nestedAppAliases: [(matches: [String], realName: String, bundlePath: String)] = [
        (["simulator", "ios simulator", "xcode simulator"],
         "Simulator",
         "/Applications/Xcode.app/Contents/Developer/Applications/Simulator.app"),
    ]

    /// Thin localization / common-nickname helpers only. Real resolution is
    /// against installed `.app` bundles via `InstalledAppIndex`.
    private static let localizationAliases: [String: String] = [
        // JP system display names → English bundle names (`open -a`)
        "メモ帳": "TextEdit",
        "テキストエディット": "TextEdit",
        "計算機": "Calculator",
        "電卓": "Calculator",
        "カレンダー": "Calendar",
        "写真": "Photos",
        "メール": "Mail",
        "地図": "Maps",
        "音楽": "Music",
        "設定": "System Settings",
        "システム設定": "System Settings",
        "プレビュー": "Preview",
        "ターミナル": "Terminal",
        "フォントブック": "Font Book",
        "辞書": "Dictionary",
        "連絡先": "Contacts",
        "リマインダー": "Reminders",
        "ブック": "Books",
        "映画": "TV",
        "クイックタイム": "QuickTime Player",
        "アクティビティモニタ": "Activity Monitor",
        "ディスクユーティリティ": "Disk Utility",
        "キーチェーンアクセス": "Keychain Access",
        "スクリプティング": "Script Editor",
        "システム情報": "System Information",
        // Phone / Messages / FaceTime — JP display → English bundle (if installed).
        // Mac usually ships FaceTime; Phone.app may be absent — extractOpenAppName
        // also tries both seeds.
        "電話": "FaceTime",
        "電話アプリ": "FaceTime",
        "メッセージ": "Messages",
        "メッセージアプリ": "Messages",
        "フェイスタイム": "FaceTime",
        "facetime": "FaceTime",
        "phone": "FaceTime",
        // Common nicknames → real bundle names
        "teams": "Microsoft Teams",
        "ms teams": "Microsoft Teams",
        "msteams": "Microsoft Teams",
        "vscode": "Visual Studio Code",
        "vs code": "Visual Studio Code",
        "chrome": "Google Chrome",
        "edge": "Microsoft Edge",
        "word": "Microsoft Word",
        "excel": "Microsoft Excel",
        "powerpoint": "Microsoft PowerPoint",
        "outlook": "Microsoft Outlook",
        "ppt": "Microsoft PowerPoint",
    ]

    /// Resolves a fuzzy / localized name to an installed app name suitable for
    /// `open -a` / AppleScript `tell application`. Returns `nil` when nothing
    /// installed matches (unlike `resolveAppName`, which echoes the input).
    static func resolveInstalledAppName(_ inputName: String) -> String? {
        let trimmed = inputName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        let lower = trimmed.lowercased()
        let fm = FileManager.default

        // 0. Nested-bundle aliases (e.g. Xcode's Simulator.app)
        for alias in nestedAppAliases where alias.matches.contains(lower) {
            if fm.fileExists(atPath: alias.bundlePath) {
                return alias.realName
            }
        }

        // 1. Thin localization / nickname → seed(s), then resolve against disk.
        // Some JP nouns map to multiple possible bundles (電話 → FaceTime / Phone).
        var seeds: [String] = []
        if let primary = localizationAliases[lower] ?? localizationAliases[trimmed] {
            seeds.append(primary)
        }
        if lower == "電話" || lower == "電話アプリ" || lower == "phone" {
            for extra in ["FaceTime", "Phone"] where !seeds.contains(extra) {
                seeds.append(extra)
            }
        }
        if seeds.isEmpty { seeds = [trimmed] }
        else if !seeds.contains(trimmed) { seeds.append(trimmed) }

        for seeded in seeds {
            if let hit = InstalledAppIndex.shared.bestMatch(for: seeded) {
                return hit
            }
            if seeded != trimmed, InstalledAppIndex.shared.appExists(named: seeded) {
                return seeded
            }
        }
        return nil
    }

    /// macOS上のアプリケーションを曖昧な名前から正確な名前（.appなし）へ解決します。
    /// Falls back to the original input when nothing is installed (parser path).
    /// Execution still refuses unresolved names — see `openApp` honesty.
    static func resolveAppName(_ inputName: String) -> String {
        resolveInstalledAppName(inputName) ?? inputName.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// Thin sense feedback for failed OPEN_APP: a short spread of installed
    /// names so the model can discover what the limb can grasp (no new tool tag).
    /// `rotateBy` shifts the sample window so repeated MISMATCH gets fresh names.
    static func sampleInstalledAppNames(limit: Int = 16, rotateBy: Int = 0) -> [String] {
        InstalledAppIndex.shared.sampleNames(limit: limit, rotateBy: rotateBy)
    }
}

// MARK: - InstalledAppIndex

/// Brief in-process cache of `.app` bundles under the standard Applications
/// directories. Avoids rescanning on every Act turn / OPEN_APP parse.
private final class InstalledAppIndex: @unchecked Sendable {
    static let shared = InstalledAppIndex()

    private struct Entry {
        let name: String          // bundle folder name without `.app` (`open -a`)
        let path: String
        let dirRank: Int          // lower = preferred (/Applications first)
        let aliases: [String]     // lowercased CFBundleName / DisplayName / name
    }

    private let lock = NSLock()
    private var entries: [Entry] = []
    private var builtAt: Date?
    private let ttl: TimeInterval = 60

    private let searchPaths: [(path: String, rank: Int)] = [
        ("/Applications", 0),
        (NSHomeDirectory() + "/Applications", 1),
        ("/System/Applications", 2),
        ("/System/Applications/Utilities", 3),
    ]

    func bestMatch(for input: String) -> String? {
        refreshIfNeeded()
        let needle = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !needle.isEmpty else { return nil }
        let lower = needle.lowercased()

        lock.lock()
        let snapshot = entries
        lock.unlock()

        var best: (score: Int, dirRank: Int, nameLen: Int, name: String)?

        for e in snapshot {
            guard let score = Self.matchScore(needle: lower, entry: e) else { continue }
            let candidate = (score, e.dirRank, e.name.count, e.name)
            if let b = best {
                // Lower score wins; then prefer /Applications; then shorter name.
                if candidate.0 < b.score
                    || (candidate.0 == b.score && candidate.1 < b.dirRank)
                    || (candidate.0 == b.score && candidate.1 == b.dirRank && candidate.2 < b.nameLen) {
                    best = candidate
                }
            } else {
                best = candidate
            }
        }
        return best?.name
    }

    func appExists(named name: String) -> Bool {
        refreshIfNeeded()
        let lower = name.lowercased()
        lock.lock()
        defer { lock.unlock() }
        if entries.contains(where: { $0.name.lowercased() == lower }) { return true }
        // Direct path check for nested / just-installed apps mid-TTL.
        for (path, _) in searchPaths {
            let url = URL(fileURLWithPath: path).appendingPathComponent("\(name).app")
            if FileManager.default.fileExists(atPath: url.path) { return true }
        }
        return false
    }

    /// Alphabetical spread of installed names for OPEN_APP MISMATCH observations.
    /// `rotateBy` rotates the pick indices so successive fails surface different names.
    func sampleNames(limit: Int, rotateBy: Int = 0) -> [String] {
        refreshIfNeeded()
        lock.lock()
        let names = entries.map(\.name).sorted { $0.localizedCaseInsensitiveCompare($1) == .orderedAscending }
        lock.unlock()
        guard limit > 0, !names.isEmpty else { return [] }
        if names.count <= limit {
            if rotateBy == 0 { return names }
            let shift = abs(rotateBy) % names.count
            return Array(names[shift...]) + Array(names[..<shift])
        }
        var out: [String] = []
        out.reserveCapacity(limit)
        let step = Double(names.count - 1) / Double(limit - 1)
        let offset = abs(rotateBy) % names.count
        for i in 0..<limit {
            let raw = Int((Double(i) * step).rounded()) + offset
            let idx = raw % names.count
            let n = names[idx]
            if out.last != n { out.append(n) }
        }
        return out
    }

    /// Match quality: 0 exact, 1 alias exact, 2 prefix, 3 contains. nil = no match.
    private static func matchScore(needle: String, entry: Entry) -> Int? {
        let nameLower = entry.name.lowercased()
        if nameLower == needle { return 0 }
        if entry.aliases.contains(needle) { return 1 }
        if nameLower.hasPrefix(needle) || entry.aliases.contains(where: { $0.hasPrefix(needle) }) {
            return 2
        }
        // Contains: require needle length ≥ 2 to avoid "a" → everything.
        guard needle.count >= 2 else { return nil }
        if nameLower.contains(needle) || entry.aliases.contains(where: { $0.contains(needle) }) {
            return 3
        }
        return nil
    }

    private func refreshIfNeeded() {
        lock.lock()
        if let builtAt, Date().timeIntervalSince(builtAt) < ttl, !entries.isEmpty {
            lock.unlock()
            return
        }
        lock.unlock()
        rebuild()
    }

    private func rebuild() {
        let fm = FileManager.default
        var built: [Entry] = []
        var seenLower = Set<String>()

        for (dir, rank) in searchPaths {
            guard let items = try? fm.contentsOfDirectory(atPath: dir) else { continue }
            for item in items where item.hasSuffix(".app") {
                let name = (item as NSString).deletingPathExtension
                let lower = name.lowercased()
                // Prefer first (higher-priority) directory on duplicate names.
                if seenLower.contains(lower) { continue }
                seenLower.insert(lower)
                let path = (dir as NSString).appendingPathComponent(item)
                var aliases = Set<String>([lower])
                if let plist = Self.readBundleNames(at: path) {
                    for a in plist where !a.isEmpty { aliases.insert(a.lowercased()) }
                }
                built.append(Entry(name: name, path: path, dirRank: rank, aliases: Array(aliases)))
            }
        }

        lock.lock()
        entries = built
        builtAt = Date()
        lock.unlock()
    }

    /// Cheap Info.plist read for CFBundleName / CFBundleDisplayName when the
    /// folder name alone would miss a nickname.
    private static func readBundleNames(at appPath: String) -> [String]? {
        let plistPath = (appPath as NSString).appendingPathComponent("Contents/Info.plist")
        guard let dict = NSDictionary(contentsOfFile: plistPath) as? [String: Any] else {
            return nil
        }
        var names: [String] = []
        for key in ["CFBundleName", "CFBundleDisplayName"] {
            if let s = dict[key] as? String, !s.isEmpty { names.append(s) }
        }
        return names
    }
}

// MARK: - AgentToolExecutor

actor AgentToolExecutor {

    private let fileManager = FileManager.default
    private var lastVisionClickTarget: CGPoint?
    private var consecutiveClickLoopCount = 0
    /// Same loop-guard idea as `consecutiveClickLoopCount`, kept separate
    /// since it gates the [DESKTOP_ACT]/hidden-window path independently
    /// of [VISION_ACT]'s Safari-only path.
    private var consecutiveDesktopClickLoopCount = 0

    /// Mission payload held outside ChatML — pasted via `[PASTE_PAYLOAD]`.
    private var missionPayload: String = ""

    /// Call at the start of a fresh act/agent run so a prior DESKTOP_BLOCKED
    /// state does not immediately reject the first click of a new goal.
    func resetLoopGuards() {
        consecutiveClickLoopCount = 0
        consecutiveDesktopClickLoopCount = 0
        lastVisionClickTarget = nil
    }

    func setMissionPayload(_ s: String) {
        missionPayload = s
    }

    func clearMissionPayload() {
        missionPayload = ""
    }

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
            let url = resolve(path, workspace: workspaceURL)
            let ext = url.pathExtension.lowercased()
            let isArtifact = ["html", "htm", "md", "svg", "txt", "csv"].contains(ext)
            let isGatekeeper = await MainActor.run { GatekeeperModeState.shared.isEnabled } && !isArtifact
            
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
                if state.operationMode != .detailed { return true }
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
            let url = resolve(path, workspace: workspaceURL)
            let ext = url.pathExtension.lowercased()
            let isArtifact = ["html", "htm", "md", "svg", "txt", "csv"].contains(ext)
            let isGatekeeper = await MainActor.run { GatekeeperModeState.shared.isEnabled } && !isArtifact
            
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
            let url = resolve(path, workspace: workspaceURL)
            let ext = url.pathExtension.lowercased()
            let isArtifact = ["html", "htm", "md", "svg", "txt", "csv"].contains(ext)
            let isGatekeeper = await MainActor.run { GatekeeperModeState.shared.isEnabled } && !isArtifact
            
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
                if state.operationMode != .detailed { return true }
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

        // ── GUI Automation ────────────────────────────────────────────────
        // Opens the app and leaves it visible + frontmost for Act (default
        // HiddenWindowAutomation policy). Session still tracks window id /
        // frame for DESKTOP_ACT / mirror capture. Verantyx is not raised.
        // Honesty: only report success when the name resolves to an installed
        // app and the process is actually running after activate — never claim
        // "opened" for unresolved / placeholder tokens.
        case .openApp(let name):
            let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
            guard let resolved = AgentToolParser.resolveInstalledAppName(trimmed) else {
                let sample = AgentToolParser.sampleInstalledAppNames(limit: 16)
                let sampleLine = sample.isEmpty
                    ? "(installed-app index empty)"
                    : sample.joined(separator: ", ")
                return """
                ✗ OPEN_APP MISMATCH: \"\(trimmed)\" does not resolve to an installed app — nothing was opened.
                Retry [OPEN_APP: <exact installed name>] using a name from this sample (or after sensing a real UI): \(sampleLine)
                """
            }
            let frame = await HiddenWindowAutomation.shared.beginOffscreenSession(appName: resolved)
            guard frame != nil else {
                return "✗ OPEN_APP MISMATCH: failed to launch/activate \"\(resolved)\" — nothing was opened."
            }
            return "✓ OS App opened and brought frontmost: \(resolved). Use [DESKTOP_ACT]/[DESKTOP_SNAPSHOT] to operate it; optional mirror preview captures the visible window."

        // Deterministic Vera-registered URL check (CRITICAL RULE 8) --
        // bypasses ask()'s consensus threshold, unlike the [VERA MEMORY]
        // section, so a single user-registered URL always surfaces here.
        case .verifiedURLLookup(let name):
            if let url = await VeraMemoryBridge.lookupVerifiedURL(name: name) {
                return "[VERIFIED_URL_LOOKUP: \(name)]\nANSWER: \(url)\nThis URL was explicitly registered as verified. Use it directly."
            }
            return "[VERIFIED_URL_LOOKUP: \(name)]\nUNKNOWN_NO_EVIDENCE — nothing registered for \"\(name)\". Do NOT construct or guess a URL yourself. Use [SEARCH: \(name)] with just the bare name as the query, then navigate by clicking an actual result from that search -- not a URL you assembled from memory."

        // Agent self-registration, same store/replace-not-accumulate
        // semantics as the human-driven HiddenWindowMirrorView click flow.
        case .registerUIElement(let app, let element, let x, let y):
            let ok = await VeraMemoryBridge.recordVerifiedUIElement(app: app, element: element, x: x, y: y)
            return ok
                ? "[REGISTER_UI_ELEMENT: \(app)|\(element)]\nRegistered at (\(Int(x)),\(Int(y))). Future operations on this element can reuse it directly instead of re-analyzing a screenshot."
                : "[REGISTER_UI_ELEMENT: \(app)|\(element)]\nFailed to register -- check vera-memory connection."

        case .osascript(let script):
            let escaped = script.replacingOccurrences(of: "'", with: "'\\''")
            let ownBundleID = Bundle.main.bundleIdentifier
            let result = await runShell("osascript -e '\(escaped)'", workingDir: workspaceURL)

            // A model can bring another app to the front via raw AppleScript
            // instead of [OPEN_APP]. Adopt that app as the Act session target
            // and leave it frontmost (visible-front policy) — do not park /
            // remimimize it behind Verantyx.
            try? await Task.sleep(nanoseconds: 300_000_000)
            let newFrontApp: String? = await MainActor.run {
                guard let front = NSWorkspace.shared.frontmostApplication,
                      front.bundleIdentifier != ownBundleID else { return nil }
                return front.localizedName
            }
            if let appName = newFrontApp {
                _ = await HiddenWindowAutomation.shared.beginOffscreenSession(appName: appName)
                return "✓ AppleScript Result:\n\(result)\n[Note: \(appName) is now the Act target and left frontmost. Use [DESKTOP_ACT]/[DESKTOP_SNAPSHOT] to operate it.]"
            }
            return "✓ AppleScript Result:\n\(result)"

        // ── Web / Grounding ───────────────────────────────────────────────

        case .browse(let url):
            let result = await WebSearchEngine.shared.browse(url: url, preferredSource: .safari)
            return "[WEB PAGE: \(result.url)]\n\(result.contextSnippet)\n[END WEB PAGE]"

        case .search(let query):
            let result = await WebSearchEngine.shared.search(query: query)
            // Auto-store in JCross (importance 0.7, zone near)
            let snippet = String(result.contextSnippet.prefix(200))
            await persistSearchResult(key: "web_\(query.prefix(30))", value: snippet)
            return "[SEARCH RESULTS for: \(query)]\nSource: \(result.url)\n\(result.contextSnippet)\n"
                 + Self.qualitySentinel(for: result)
                 + "[END SEARCH RESULTS]"

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
            if SensePixelPolicy.isVectorOnly {
                SensePixelPolicy.logVectorOnlyOnce()
                do {
                    try await SafariVisionBridge.shared.navigate(url)
                    await SensePixelPolicy.clearModelPixelBuffers()
                    return """
                    [VISION_BROWSE: \(url)]
                    Navigated (vector-only sense). Screen pixels are NOT retained or injected for the model.
                    Prefer [DESKTOP_SNAPSHOT] (AX map) + [AX_ACT] / [DESKTOP_ACT]. Use [VISION_ACT] only after disabling Vector-only sense.
                    """
                } catch { return "[VISION ERROR] \(error.localizedDescription)" }
            }
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
            if SensePixelPolicy.isVectorOnly {
                SensePixelPolicy.logVectorOnlyOnce()
                let cleanQuery = query.trimmingCharacters(in: CharacterSet(charactersIn: "\"' "))
                let encodedQuery = cleanQuery.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? cleanQuery
                let url = "https://www.google.com/search?q=\(encodedQuery)"
                do {
                    try await SafariVisionBridge.shared.navigate(url)
                    await SensePixelPolicy.clearModelPixelBuffers()
                    return """
                    [VISION_SEARCH_FLOW: \(query)]
                    Google opened (vector-only sense). No frames injected — use [DESKTOP_SNAPSHOT]/[AX_ACT].
                    """
                } catch { return "[VISION ERROR] \(error.localizedDescription)" }
            }
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
            if SensePixelPolicy.isVectorOnly {
                SensePixelPolicy.logVectorOnlyOnce()
                await SensePixelPolicy.clearModelPixelBuffers()
                let ax = (try? await AXVisionBridge.shared.getSemanticSnapshot()) ?? "(AX unavailable)"
                return """
                [VISION_SNAPSHOT]
                Vector-only sense — pixels not retained for model. Prefer [DESKTOP_SNAPSHOT].
                == SEMANTIC UI MAP ==
                \(ax)
                """
            }
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
            if SensePixelPolicy.isVectorOnly {
                SensePixelPolicy.logVectorOnlyOnce()
                // Still perform the HID action, but do not capture/inject pixels.
                do {
                    let parts = action.split(separator: " ")
                    guard let cmd = parts.first else { return "[VISION ERROR] Empty action" }
                    if cmd == "click" && parts.count >= 3 {
                        let x = Double(parts[1]) ?? 0.0
                        let y = Double(parts[2]) ?? 0.0
                        try await SafariVisionBridge.shared.hidClick(x: x, y: y)
                    } else if cmd == "type" && parts.count >= 2 {
                        let text = action.dropFirst(5).trimmingCharacters(in: .whitespaces)
                        try await SafariVisionBridge.shared.typeText(text)
                    } else if cmd == "scroll" {
                        try await SafariVisionBridge.shared.scrollDown()
                    }
                    try? await Task.sleep(nanoseconds: 1_000_000_000)
                    await SensePixelPolicy.clearModelPixelBuffers()
                    let ax = (try? await AXVisionBridge.shared.getSemanticSnapshot()) ?? "(AX unavailable)"
                    return """
                    [VISION_ACT: \(action)]
                    Action performed (vector-only — no screenshot inject). Prefer [AX_ACT] next.
                    == SEMANTIC UI MAP ==
                    \(String(ax.prefix(1200)))
                    """
                } catch { return "[VISION ERROR] \(error.localizedDescription)" }
            }
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

        case .desktopSnapshot:
            do {
                // Prefer the OPEN_APP session target window (visible front
                // policy) over a full-display shot of whatever is topmost.
                let hiddenActive = await MainActor.run { HiddenWindowAutomation.shared.targetAppName != nil }
                let semanticXML = try await AXVisionBridge.shared.getSemanticSnapshot()
                let vectorOnly = SensePixelPolicy.isVectorOnly
                if vectorOnly {
                    SensePixelPolicy.logVectorOnlyOnce()
                }

                var frame: String? = nil
                var captureNote = ""
                // Vector-only: never capture JPEG for the model. Mirror UI
                // still refreshes independently via HiddenWindowMirrorView.
                if !vectorOnly {
                    if hiddenActive, let hidden = await HiddenWindowAutomation.shared.captureWindowImage() {
                        frame = hidden
                    } else {
                        do {
                            frame = try await SafariVisionBridge.shared.takeScreenshot(enforceSafari: false)
                        } catch {
                            captureNote = "\n[NO SCREENSHOT] \(error.localizedDescription)\nContinuing with AX map only.\n"
                        }
                    }
                } else {
                    captureNote = "\n[VECTOR-ONLY] Screen pixels not retained for model.\n"
                }

                // JGEN can't consume raw images. Prefer AX/text → encode →
                // inject (aligned JGEN space). Vision feature-print inject
                // remains an experimental weak-signal fallback only (disabled
                // under vector-only).
                let jgenActive = await JCrossChatManager.shared.isLoaded
                var hiddenStateReflection: String? = nil
                if jgenActive {
                    hiddenStateReflection = await JGenVectorBusMemory.reflectCurrentScreenAligned(
                        axSemanticXML: semanticXML
                    )
                    if !vectorOnly, hiddenStateReflection == nil, let frame {
                        hiddenStateReflection = await VisualHiddenStateBridge.reflectOnScreen(base64Image: frame)
                    }
                    let sessionId = await MainActor.run { AppState.shared?.vxChatSessionId }
                    await JGenVectorBusMemory.stampObservation(
                        label: "desktop_snapshot",
                        detail: String(semanticXML.prefix(900)),
                        sessionId: sessionId,
                        stepIndex: nil,
                        actionLabel: "🖥️ desktop_snapshot",
                        changedRegion: nil,
                        concepts: ["ui-observe", "bug-repro", "desktop-snapshot"]
                    )
                } else if !vectorOnly, let frame {
                    await CognitiveAnchorEngine.shared.setVisionScreenshot(frame)
                }
                if vectorOnly {
                    await SensePixelPolicy.clearModelPixelBuffers()
                } else if let frame {
                    await MainActor.run {
                        AppState.shared?.lastVideoFrames = [frame]
                    }
                }

                let modeNote: String
                if vectorOnly {
                    modeNote = "Vector-only sense — AX map + vector stamp only (no JPEG to model)."
                } else if jgenActive {
                    modeNote = "JGEN backend — AX map encoded into hidden state (Vision raw inject only as fallback)."
                } else {
                    modeNote = "Screenshot updated and injected to context."
                }

                return """
                [DESKTOP_SNAPSHOT]
                Captured desktop observation\(hiddenActive ? " (Act target window)" : ""). \(modeNote)\(captureNote)
                \(hiddenStateReflection.map { "\n\($0)\n" } ?? "")
                == SEMANTIC UI MAP ==
                \(semanticXML)
                """
            } catch is CancellationError {
                return "[DESKTOP_SNAPSHOT] Interrupted (cancellation) — retry; target was left visible."
            } catch { return "[DESKTOP ERROR] \(error.localizedDescription)" }

        case .desktopAct(let action):
            do {
                let parts = action.split(separator: " ")
                guard let cmd = parts.first else { return "[DESKTOP ERROR] Empty action" }

                let hiddenActive = await MainActor.run { HiddenWindowAutomation.shared.targetAppName != nil }
                let vectorOnly = SensePixelPolicy.isVectorOnly
                if vectorOnly {
                    SensePixelPolicy.logVectorOnlyOnce()
                }

                // Diff-gating (Milestone G): mirrors [VISION_ACT]'s existing
                // loop-detection, previously missing from this path entirely
                // -- [DESKTOP_ACT] used to unconditionally re-screenshot and
                // re-inject into the vision model on every single action,
                // regardless of whether anything actually changed.
                let frameBeforeAction = vectorOnly
                    ? nil
                    : await MainActor.run { AppState.shared?.lastVideoFrames?.last }
                if cmd == "click" && consecutiveDesktopClickLoopCount >= 3 {
                    consecutiveDesktopClickLoopCount = 0
                    return "[DESKTOP ERROR] DESKTOP_BLOCKED: You have clicked near these coordinates multiple times without the screen visually changing. DO NOT click here again. Try a different tool (scroll, type, or a different location) or ask the human."
                }

                if cmd == "click" && parts.count >= 3 {
                    let x = Double(parts[1]) ?? 0.0
                    let y = Double(parts[2]) ?? 0.0
                    if hiddenActive {
                        await HiddenWindowAutomation.shared.clickInWindow(relativeX: x, relativeY: y)
                    } else {
                        try await SafariVisionBridge.shared.hidClick(x: x, y: y, enforceSafari: false)
                    }
                } else if cmd == "type" && parts.count >= 2 {
                    let text = action.dropFirst(5).trimmingCharacters(in: .whitespaces)
                    if hiddenActive {
                        await HiddenWindowAutomation.shared.typeInWindow(text)
                    } else {
                        try await SafariVisionBridge.shared.typeText(text)
                    }
                }

                // Soft sleep: parent cancellation used to surface as
                // Swift.CancellationError mid-Act when minimize/focus races
                // tore down work. Clicks already ran; don't fail the tool.
                try? await Task.sleep(nanoseconds: 2_000_000_000)

                if vectorOnly {
                    await SensePixelPolicy.clearModelPixelBuffers()
                    let ax = (try? await AXVisionBridge.shared.getSemanticSnapshot()) ?? "(AX unavailable)"
                    if await JCrossChatManager.shared.isLoaded {
                        _ = await JGenVectorBusMemory.reflectCurrentScreenAligned(axSemanticXML: ax)
                        let sessionId = await MainActor.run { AppState.shared?.vxChatSessionId }
                        await JGenVectorBusMemory.stampObservation(
                            label: "desktop_act",
                            detail: "vector-only \(action)\n\(String(ax.prefix(700)))",
                            sessionId: sessionId,
                            stepIndex: nil,
                            actionLabel: "🖥️ desktop_act: \(action)",
                            changedRegion: nil,
                            concepts: ["ui-observe", "bug-repro", "desktop-act", "vector-only"]
                        )
                    }
                    return """
                    [DESKTOP_ACT: \(action)]
                    Action performed (vector-only — no screenshot inject\(hiddenActive ? ", Act target window" : "")).
                    Prefer [AX_ACT] / [DESKTOP_SNAPSHOT] for the next observation.
                    == SEMANTIC UI MAP ==
                    \(String(ax.prefix(1200)))
                    """
                }

                var frame: String? = nil
                var captureDeniedNote = ""
                if hiddenActive, let hidden = await HiddenWindowAutomation.shared.captureWindowImage() {
                    frame = hidden
                } else {
                    do {
                        frame = try await SafariVisionBridge.shared.takeScreenshot(enforceSafari: false)
                    } catch is CancellationError {
                        captureDeniedNote = "\n[NO SCREENSHOT] capture cancelled — action may still have applied.\n"
                    } catch {
                        // Click/type may have succeeded; do not fail the whole
                        // tool on Screen Recording TCC (common with ad-hoc DMG).
                        captureDeniedNote = "\n[NO SCREENSHOT] \(error.localizedDescription)\n"
                        if ScreenCapturePermission.looksLikeDenied(error.localizedDescription) {
                            let ax = (try? await AXVisionBridge.shared.getSemanticSnapshot()) ?? "(AX unavailable)"
                            return """
                            [DESKTOP_ACT: \(action)]
                            Action attempted. Screenshot blocked by Screen Recording TCC.\(captureDeniedNote)
                            == SEMANTIC UI MAP ==
                            \(String(ax.prefix(1200)))
                            """
                        }
                        return "[DESKTOP ERROR] \(error.localizedDescription)"
                    }
                }

                // Only run the (cheap, but not free) Vision-framework
                // feature-print diff for clicks -- type/scroll actions are
                // expected to change the screen, and there's no prior
                // single-point target to loop-detect against.
                var noVisualChange = false
                var changedRegion: CGRect? = nil
                if cmd == "click", let before = frameBeforeAction, let frame {
                    let distance = SafariVisionBridge.shared.computeVisualSimilarity(base64A: before, base64B: frame)
                    if distance < 10.0 {
                        noVisualChange = true
                        consecutiveDesktopClickLoopCount += 1
                    } else {
                        consecutiveDesktopClickLoopCount = 0
                        if let beforeData = Data(base64Encoded: before), let beforeImage = NSImage(data: beforeData),
                           let afterData = Data(base64Encoded: frame), let afterImage = NSImage(data: afterData) {
                            changedRegion = VisualDiffRegion.changedRegion(before: beforeImage, after: afterImage)
                        }
                    }
                }

                if let frame {
                    await CognitiveAnchorEngine.shared.setVisionScreenshot(frame)
                    await MainActor.run {
                        AppState.shared?.lastVideoFrames = [frame]
                        AppState.shared?.lastDesktopChangedRegion = changedRegion
                    }
                }

                if cmd == "click" {
                    let changeNote = noVisualChange
                        ? "NO VISUAL CHANGE was detected (NO_VISUAL_CHANGE) -- you probably missed the target. Try a different location, or scroll first."
                        : "🔴 A red circle shows where your mouse clicked."
                    let resultText = """
                    [DESKTOP_ACT: \(action)]
                    Action performed. New screenshot injected\(hiddenActive ? " (Act target window)" : "").\(captureDeniedNote)
                    \(changeNote)
                    """
                    if !noVisualChange, await JCrossChatManager.shared.isLoaded {
                        let sessionId = await MainActor.run { AppState.shared?.vxChatSessionId }
                        await JGenVectorBusMemory.stampObservation(
                            label: "desktop_act",
                            detail: resultText,
                            sessionId: sessionId,
                            stepIndex: nil,
                            actionLabel: "🖥️ desktop_act: \(action)",
                            changedRegion: changedRegion,
                            concepts: ["ui-observe", "bug-repro", "desktop-act"]
                        )
                    }
                    return resultText
                }

                let resultText = "[DESKTOP_ACT: \(action)]\nAction performed. New screenshot injected\(hiddenActive ? " (Act target window)" : "").\(captureDeniedNote)"
                if await JCrossChatManager.shared.isLoaded {
                    let sessionId = await MainActor.run { AppState.shared?.vxChatSessionId }
                    await JGenVectorBusMemory.stampObservation(
                        label: "desktop_act",
                        detail: resultText,
                        sessionId: sessionId,
                        stepIndex: nil,
                        actionLabel: "🖥️ desktop_act: \(action)",
                        changedRegion: changedRegion,
                        concepts: ["ui-observe", "bug-repro", "desktop-act"]
                    )
                }
                return resultText
            } catch is CancellationError {
                return "[DESKTOP_ACT: \(action)]\nInterrupted (cancellation) after attempting action — target left visible; retry if needed."
            } catch { return "[DESKTOP ERROR] \(error.localizedDescription)" }

        case .waitUntilStable(let stableSeconds, let timeout):
            let allowed = await MainActor.run {
                CouncilSettingsStore.shared.allowKeyframeEye
                    && CouncilSettingsStore.shared.keyframeEyePrivacyAcknowledged
            }
            guard allowed else {
                return "[WAIT_UNTIL_STABLE] Keyframe eye is not permitted. Enable “Allow 1fps screen eye” in JGEN Options (privacy confirmation required)."
            }
            let monitoring = await MainActor.run { VisualKeyframePump.shared.isActivelyMonitoring }
            if !monitoring {
                return "[WAIT_UNTIL_STABLE] Not monitoring — need an active agent session and a HiddenWindow target (OPEN_APP)."
            }
            let stable = await VisualKeyframePump.shared.waitUntilStable(
                stableSeconds: stableSeconds, timeout: timeout
            )
            let recent = await VeraAVRing.shared.recallRecentBlock(limit: 3)
            if stable {
                return "[WAIT_UNTIL_STABLE] Screen stable for \(stableSeconds)s.\(recent)"
            }
            return "[WAIT_UNTIL_STABLE] Timed out after \(timeout)s without \(stableSeconds)s of stability.\(recent)"
            
        case .axAct(let action):
            do {
                let parts = action.split(separator: " ", maxSplits: 2).map(String.init)
                guard parts.count >= 2 else { return "[AX_ACT ERROR] Invalid action format. Use: #id action [text]" }
                
                let id = parts[0]
                let cmd = parts[1]
                let text = parts.count > 2 ? parts[2].trimmingCharacters(in: CharacterSet(charactersIn: "\"")) : nil
                
                let result = try await AXVisionBridge.shared.performAction(id: id, action: cmd, text: text)
                
                // Take a new snapshot to update context
                try await Task.sleep(nanoseconds: 1_500_000_000)
                let newXML = try await AXVisionBridge.shared.getSemanticSnapshot()
                let vectorOnly = SensePixelPolicy.isVectorOnly
                if vectorOnly {
                    SensePixelPolicy.logVectorOnlyOnce()
                    await SensePixelPolicy.clearModelPixelBuffers()
                } else {
                    let frame = try await SafariVisionBridge.shared.takeScreenshot(enforceSafari: false)
                    await MainActor.run { AppState.shared?.lastVideoFrames = [frame] }
                    if !(await JCrossChatManager.shared.isLoaded) {
                        await CognitiveAnchorEngine.shared.setVisionScreenshot(frame)
                    }
                }
                if await JCrossChatManager.shared.isLoaded {
                    _ = await JGenVectorBusMemory.reflectCurrentScreenAligned(axSemanticXML: newXML)
                    let sessionId = await MainActor.run { AppState.shared?.vxChatSessionId }
                    await JGenVectorBusMemory.stampObservation(
                        label: "ax_act",
                        detail: "\(result)\n\(String(newXML.prefix(700)))",
                        sessionId: sessionId,
                        stepIndex: nil,
                        actionLabel: "🎯 ax_act: \(action)",
                        changedRegion: nil,
                        concepts: ["ui-observe", "bug-repro", "ax-act"]
                    )
                }
                
                return """
                [AX_ACT: \(action)]
                \(result)\(vectorOnly ? "\n(vector-only — no screenshot retained for model)" : "")
                
                == NEW SEMANTIC UI MAP ==
                \(newXML)
                """
            } catch {
                return "[AX_ACT ERROR] \(error.localizedDescription)"
            }

        case .pastePayload:
            let payload = missionPayload
            guard !payload.isEmpty else {
                return "[PASTE_PAYLOAD ERROR] No mission payload held — nothing to paste."
            }
            let pasted = await HiddenWindowAutomation.shared.pasteIntoTargetWindow(payload)
            if pasted.uppercased().contains("ERROR") {
                return "[PASTE_PAYLOAD ERROR] \(pasted)"
            }
            return "[PASTE_PAYLOAD]\n\(pasted)"

        // ── JCross Memory ─────────────────────────────────────────────────

        case .jcrossQuery(let query):
            return await MainActor.run {
                guard let cortex = CortexEngine.shared else {
                    return "[JCROSS] Memory engine not available"
                }
                let nodes = cortex.recall(for: query, topK: 5)
                if nodes.isEmpty { return "[JCROSS] No memories found for: \(query)\n[SYSTEM HINT] If memory search fails, DO NOT query the same thing again. Use [LIST_DIR: .] and [READ: filename] to explore the codebase directly." }
                let lines = nodes.map { "• \($0.key): \($0.value)" }.joined(separator: "\n")
                return "[JCROSS MEMORY for: \(query)]\n\(lines)\n[END JCROSS]\n[SYSTEM HINT] If the memory results above are unhelpful or only echo the prompt, DO NOT repeat this query. Use [LIST_DIR: .] and [READ: filename] to directly explore the workspace."
            }

        case .jcrossStore(let key, let value):
            await MainActor.run {
                CortexEngine.shared?.remember(key: key, value: value, importance: 0.8, zone: .near)
            }
            return "✓ Stored in JCross memory: \(key) = \(value.prefix(60))"

        case .osAssetQuery(let category):
            return await OSAssetMemoryVault.shared.queryCategory(category)

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
            // Twin-B Audit (Actor-Critic Voyager Loop)
            let isAuditorEnabled = await MainActor.run { AppState.shared?.isAuditorEnabled ?? true }
            if isAuditorEnabled {
                let toolStr = "[FORGE_SKILL: \(name)|\(description)]\n" + payload.joined(separator: "\n") + "\n[/FORGE_SKILL]"
                let auditResult = await TwinCriticEngine.shared.audit(tool: toolStr, conversation: [])
                
                if !auditResult.isApproved {
                    return "❌ [Auditor Rejected] \(auditResult.feedback)\n\nTwin-B (Critic) rejected this skill. Please fix the issues and output [FORGE_SKILL] again."
                }
            }
            
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
                    "🔧 認証完了: \(name) (v\(saved.version))",
                    icon: "checkmark.seal.fill",
                    color: .green,
                    duration: 3.0
                )
            }
            
            // Automatically execute the certified skill
            let executor = SkillExecutor()
            let execResult = await executor.execute(
                skill: saved,
                args: [:],
                workspaceURL: workspaceURL,
                onProgress: { _ in }
            )
            
            return "✓ [Skill Forged & Certified] '\(name)' v\(saved.version) saved to ~/.verantyx/skills/\n\n[AUTO-EXECUTION RESULT]\n\(execResult)"

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
        let primarySentinel = Self.qualitySentinel(for: primary)

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
        \(primarySentinel)[END SEARCH_MULTI]
        Synthesize the above sources to answer the question.
        """
    }

    /// 「通信は成功したが0件だった」ことを下流の ReAct エンジンへ伝える印。
    ///
    /// 判定自体は構造化された `WebSearchResult` が生きているここで行い、
    /// 下流へは1行の印だけ渡す。`ReActRetryEngine.detectFailure` は既にラップ
    /// 済みの文字列しか受け取らずクエリを持たないので、あちらで再判定させる
    /// と語の一致率を計算できない。
    static func qualitySentinel(for result: WebSearchResult) -> String {
        if case .noRelevantResults(let reason, let missing) = result.verdict {
            let term = missing.map { " | missing_term=\($0)" } ?? ""
            return "[SEARCH_QUALITY: no_relevant_results | reason=\(reason)\(term)]\n"
        }
        return ""
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
        if let ws = workspace {
            if path == "/" || path == "~" { return ws }
            if path.hasPrefix(ws.path) { return URL(fileURLWithPath: path) }
        }
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

            var validDir = workingDir ?? fallbackDir
            var isDir: ObjCBool = false
            if !FileManager.default.fileExists(atPath: validDir.path, isDirectory: &isDir) || !isDir.boolValue {
                validDir = FileManager.default.homeDirectoryForCurrentUser
            }
            process.currentDirectoryURL = validDir

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

            // Grounds the model in the REAL directory the command actually
            // ran from -- without this, a model that hallucinates a wrong
            // path (e.g. a `git clone` target under a nonexistent
            // directory) has no way to notice the mismatch and just
            // repeats the same failing command. See also the
            // CURRENT WORKSPACE ROOT line in AgentLoop's system prompt.
            result += "\n[cwd: \(validDir.path)]"

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
