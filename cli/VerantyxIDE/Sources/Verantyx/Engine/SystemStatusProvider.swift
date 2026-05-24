import Foundation

// MARK: - SystemStatusProvider
//
// Verantyx の全バックグラウンドプロセスの状態を集約し、
// AI (Gemma / Ollama) の systemPrompt に自動注入するプロバイダー。
//
// 設計思想:
//   - UI バナー不要。AI がチャットで「今何が動いていますか？」と聞かれたら
//     自律的に正確な状態を答えられる。
//   - MCP ツールのような「状態照会インターフェース」を AI に提供する。
//   - `systemStatusBlock` を呼ぶだけで現在のスナップショットを取得できる。
//
// 注入タイミング:
//   sendMessage() → buildEffectiveSystemPrompt() で自動付加される。
//   何も動いていないとき (idle) はブロック自体を省略しプロンプトを汚さない。

@MainActor
final class SystemStatusProvider {

    static let shared = SystemStatusProvider()
    private init() {}

    // MARK: - 状態ブロック生成

    /// 現在アクティブなプロセスがあれば [SYSTEM STATUS] ブロックを返す。
    /// 全プロセスが idle なら nil を返す (systemPrompt を汚さない)。
    func systemStatusBlock() -> String? {
        var lines: [String] = []

        // ── L2.5 インデックス ──────────────────────────────────────────
        let l25 = L25IndexEngine.shared
        if l25.isIndexing {
            let modeLabel = l25.indexingMode == .incremental ? AppLanguage.shared.t("Incremental", "差分更新") : AppLanguage.shared.t("Full", "全体生成")
            let pct = Int(l25.indexingProgress * 100)
            let total = l25.projectMap?.fileCount ?? 0
            let done  = Int(l25.indexingProgress * Double(max(total, 1)))
            var line  = AppLanguage.shared.t("• L2.5 BitNet Indexing [\(modeLabel)] \(pct)% (\(done)/\(max(total,1)) files)", "• L2.5 BitNet インデックス実行中 [\(modeLabel)] \(pct)% (\(done)/\(max(total,1)) files)")
            if !l25.currentFile.isEmpty {
                line += AppLanguage.shared.t(" → Current: \(l25.currentFile)", " → 現在: \(l25.currentFile)")
            }
            lines.append(line)
        } else if let map = l25.projectMap {
            lines.append(AppLanguage.shared.t("• L2.5 Map: Ready (\(map.fileCount) files, Gen: \(map.generatedAt.formatted(.dateTime.month().day().hour().minute())))", "• L2.5 地図: 準備完了 (\(map.fileCount) files, 生成: \(map.generatedAt.formatted(.dateTime.month().day().hour().minute())))"))
        } else {
            lines.append(AppLanguage.shared.t("• L2.5 Map: Not generated (Needs BitNet setup)", "• L2.5 地図: 未生成 (BitNet セットアップが必要)"))
        }

        // ── BitNet Commander ループ ────────────────────────────────────
        let cmd = BitNetCommanderLoop.shared
        if cmd.isRunning {
            let phase = cmd.currentPhase
            let task  = cmd.currentTask.isEmpty ? AppLanguage.shared.t("(Task pending)", "(タスク未定)") : String(cmd.currentTask.prefix(60))
            lines.append(AppLanguage.shared.t("• BitNet Commander: Running — Phase: \(phase)", "• BitNet Commander: 実行中 — フェーズ: \(phase)"))
            lines.append(AppLanguage.shared.t("  Task: \(task)", "  タスク: \(task)"))
        }

        // ── Transpilation Pipeline ────────────────────────────────────
        let pipe = TranspilationPipeline.shared
        if pipe.isRunning {
            lines.append(AppLanguage.shared.t("• Transpilation Pipeline: Running — \(pipe.progressMessage)", "• 変換パイプライン: 実行中 — \(pipe.progressMessage)"))
        }

        // ── モデル状態 ────────────────────────────────────────────────
        if let appState = AppState.shared {
            switch appState.modelStatus {
            case .downloading(let p):
                lines.append(AppLanguage.shared.t("• Model: Downloading \(Int(p * 100))%", "• モデル: ダウンロード中 \(Int(p * 100))%"))
            case .connecting:
                lines.append(AppLanguage.shared.t("• Model: Connecting", "• モデル: 接続中"))
            case .mlxDownloading(let m):
                lines.append(AppLanguage.shared.t("• Model: MLX Downloading (\(m))", "• モデル: MLX ダウンロード中 (\(m))"))
            case .none, .ready, .ollamaReady, .mlxReady, .bitnetReady, .anthropicReady, .error:
                break  // 準備完了・エラーは通常状態として注入しない
            }
        }

        // idle なら注入しない
        guard !lines.isEmpty else { return nil }

        // L2.5 準備完了のみの場合は軽量メッセージだけ返す (頻繁に汚さない)
        let hasActiveProcess = l25.isIndexing || cmd.isRunning || pipe.isRunning
        if !hasActiveProcess && lines.count == 1 {
            // 準備完了のみ → 省略 (毎回送ると noisy になる)
            return nil
        }

        let body = lines.joined(separator: "\n")
        let instEN = "Please answer the user's question based on the above state information."
        let instJP = "上記の状態情報を踏まえてユーザーの質問に答えてください。\n        状態について質問されたら、この情報を基に正確に日本語で答えてください。"
        
        return """
        [SYSTEM STATUS — \(Date().formatted(.dateTime.hour().minute().second()))]
        \(body)
        [END STATUS]

        \(AppLanguage.shared.t(instEN, instJP))
        """
    }

    // MARK: - 完全なステータスレポート (ユーザーが明示的に聞いた場合)

    /// 「状態を教えて」「何が動いている？」系の質問に対するフル回答用。
    func fullStatusReport() -> String {
        let l25 = L25IndexEngine.shared
        let cmd = BitNetCommanderLoop.shared
        let pipe = TranspilationPipeline.shared

        var sections: [String] = []

        // L2.5
        if l25.isIndexing {
            let mode = l25.indexingMode == .incremental ? AppLanguage.shared.t("Incremental", "差分更新") : AppLanguage.shared.t("Full", "全体生成")
            let pct  = Int(l25.indexingProgress * 100)
            let curr = l25.currentFile.isEmpty ? "-" : l25.currentFile
            let total = l25.projectMap?.fileCount ?? 0
            
            sections.append(AppLanguage.shared.t("""
            🟡 L2.5 Indexing in progress
               Mode: \(mode)
               Progress: \(pct)%
               Current file: \(curr)
               Total files: \(total)
            """, """
            🟡 L2.5 インデックス実行中
               モード: \(mode)
               進捗: \(pct)%
               現在ファイル: \(curr)
               総ファイル数: \(total)
            """))
        } else if let map = l25.projectMap {
            let fc = map.fileCount
            let topo = map.globalTopology.prefix(80)
            let gen = map.generatedAt.formatted(.dateTime.year().month().day().hour().minute())
            let root = URL(fileURLWithPath: map.workspaceRoot).lastPathComponent
            
            sections.append(AppLanguage.shared.t("""
            ✅ L2.5 Map: Ready
               Files: \(fc)
               Global Topology: \(topo)
               Generated: \(gen)
               Workspace: \(root)
            """, """
            ✅ L2.5 地図: 準備完了
               ファイル数: \(fc)
               グローバルトポロジー: \(topo)
               最終生成: \(gen)
               ワークスペース: \(root)
            """))
        } else {
            sections.append(AppLanguage.shared.t("⚫ L2.5 Map: Not generated — Please run BitNet setup", "⚫ L2.5 地図: 未生成 — BitNet のセットアップを実行してください"))
        }

        // BitNet Commander
        if cmd.isRunning {
            let cp = cmd.currentPhase
            let ct = cmd.currentTask.prefix(100)
            sections.append(AppLanguage.shared.t("""
            🟡 BitNet Commander: Running
               Phase: \(cp)
               Task: \(ct)
            """, """
            🟡 BitNet Commander: 実行中
               フェーズ: \(cp)
               タスク: \(ct)
            """))
        } else {
            sections.append(AppLanguage.shared.t("⚫ BitNet Commander: Idle", "⚫ BitNet Commander: 待機中"))
        }

        // Pipeline
        if pipe.isRunning {
            sections.append(AppLanguage.shared.t("🟡 Transpilation Pipeline: \(pipe.progressMessage)", "🟡 変換パイプライン: \(pipe.progressMessage)"))
        } else {
            sections.append(AppLanguage.shared.t("⚫ Transpilation Pipeline: Idle", "⚫ 変換パイプライン: 待機中"))
        }

        return sections.joined(separator: "\n")
    }

    // MARK: - ステータス質問の検出

    /// ユーザーの入力が「状態確認」系の質問かどうかを判定する。
    static func isStatusQuery(_ text: String) -> Bool {
        let lower = text.lowercased()
        let keywords = [
            "何が動いて", "状態を教えて", "今何を", "プロセス",
            "インデックス", "進捗", "l2.5", "bitnet",
            "what's running", "status", "what is happening",
            "処理中", "実行中", "どのくらい"
        ]
        return keywords.contains { lower.contains($0) }
    }
}
