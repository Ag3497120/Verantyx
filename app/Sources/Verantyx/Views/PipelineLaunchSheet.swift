import SwiftUI

// MARK: - PipelineLaunchSheet
//
// 「▶ Run Pipeline」ボタンを押したときに表示されるシート。
// タスクを入力して「Start」を押すと TranspilationPipeline.run() が起動し、
// BitNet が L2.5 地図生成 → TODO 作成 → モデルが1ファイルずつ処理 →
// 対応言語ならビルド検証(swift/rust/typescript) → 自動修正ループ が
// 完全自律で動作する。元々はSwift→Rust変換専用に作られたが、L1-L3の
// 階層メモリでモデルにワークスペース全体を渡さず1ファイルずつ処理させる
// 仕組み自体は言語・タスクに依存しないため、変換タスクに限らず
// 汎用的な長時間タスク(テスト追加・リファクタ等)にも使える。

struct PipelineLaunchSheet: View {
    @Binding var isPresented: Bool
    @Binding var taskText: String
    @EnvironmentObject var app: AppState
    @ObservedObject private var pipeline = TranspilationPipeline.shared
    @ObservedObject private var l25Engine = L25IndexEngine.shared
    @State private var maxRetries = 3

    private let presets: [(String, String)] = [
        ("Swift→Rust 完全変換",
         "Convert the entire VerantyxIDE Swift codebase to Rust + Tauri 2 for Windows. Output into verantyx-windows-target/. Use tokio, serde, anyhow, tauri@2 ONLY. One file per step."),
        ("CortexEngine のみ",
         "Convert ONLY Sources/Verantyx/Engine/CortexEngine.swift to verantyx-windows-target/src/memory.rs using Rust with tokio and serde."),
        ("記憶システム3ファイル",
         "Convert CortexEngine.swift, JCrossVault.swift, and BitNetEngine.swift to Rust. Output to verantyx-windows-target/src/. Use Arc<RwLock<T>> for state management."),
        // Non-conversion examples (Milestone I: generalized beyond
        // Swift→Rust) -- targetPath stays equal to relativePath for these,
        // i.e. in-place edits, not a new output tree.
        ("テスト追加(例)",
         "Add unit tests for every file in Sources/Verantyx/Engine/ that doesn't already have one. One file per step."),
        ("リファクタ(例)",
         "Refactor every file under Sources/Verantyx/Views/ to extract repeated view-building code into private helper functions, in place."),
    ]

    var body: some View {
        VStack(spacing: 0) {
            // ヘッダー
            HStack {
                Image(systemName: "play.rectangle.fill")
                    .foregroundStyle(Color(red: 0.55, green: 1.0, blue: 0.65))
                    .font(.title3)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Pipeline")
                        .font(.headline)
                    Text(AppLanguage.shared.t(
                        "BitNet → L2.5 Map → TODO → per-file apply → build-verify where supported → Auto-fix",
                        "BitNet → L2.5地図 → TODO → ファイル単位で適用 → 対応言語ならビルド検証 → 自動修正"
                    ))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button { isPresented = false } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundStyle(.secondary)
                        .font(.title3)
                }
                .buttonStyle(.plain)
            }
            .padding()
            .background(Theme.panel2)

            Divider()

            ScrollView {
                VStack(alignment: .leading, spacing: 16) {

                    // L2.5 地図ステータス
                    l25StatusCard

                    // プリセット選択
                    VStack(alignment: .leading, spacing: 8) {
                        Label("Presets", systemImage: "list.bullet")
                            .font(.subheadline.bold())
                        ForEach(presets, id: \.0) { preset in
                            Button {
                                taskText = preset.1
                            } label: {
                                HStack {
                                    Image(systemName: "bolt.fill")
                                        .font(.caption)
                                        .foregroundStyle(Color(red: 0.55, green: 1.0, blue: 0.65))
                                    Text(preset.0)
                                        .font(.caption)
                                        .foregroundStyle(Color(red: 0.80, green: 0.90, blue: 1.0))
                                    Spacer()
                                }
                                .padding(.horizontal, 10)
                                .padding(.vertical, 6)
                                .background(
                                    RoundedRectangle(cornerRadius: 6)
                                        .fill(Color.white.opacity(0.05))
                                        .overlay(
                                            RoundedRectangle(cornerRadius: 6)
                                                .stroke(Color.white.opacity(0.08), lineWidth: 1)
                                        )
                                )
                            }
                            .buttonStyle(.plain)
                        }
                    }

                    // タスク入力
                    VStack(alignment: .leading, spacing: 6) {
                        Label(L("Task (BitNet turns this into TODOs)", "Task (BitNetがTODO化します)"), systemImage: "text.cursor")
                            .font(.subheadline.bold())
                        TextEditor(text: $taskText)
                            .font(.system(size: 12, design: .monospaced))
                            .frame(minHeight: 100, maxHeight: 160)
                            .padding(8)
                            .background(Theme.panel)
                            .clipShape(RoundedRectangle(cornerRadius: 8))
                            .overlay(
                                RoundedRectangle(cornerRadius: 8)
                                    .stroke(Color.white.opacity(0.12), lineWidth: 1)
                            )
                    }

                    // 設定
                    HStack {
                        Text("Max Retries per File:")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Stepper("\(maxRetries)", value: $maxRetries, in: 1...10)
                            .font(.caption)
                    }

                    // 5層メモリ説明
                    memoryLayerInfo

                    // パイプライン進捗（実行中のみ表示）
                    if pipeline.isRunning || !pipeline.todos.isEmpty {
                        pipelineProgressView
                    }
                }
                .padding()
            }

            Divider()

            // 実行ボタン
            HStack(spacing: 12) {
                Button("Cancel") { isPresented = false }
                    .buttonStyle(.bordered)

                Spacer()

                if pipeline.isRunning {
                    HStack(spacing: 8) {
                        ProgressView().scaleEffect(0.8)
                        Text(AppLanguage.shared.t("Pipeline running... \(pipeline.todos.filter{$0.status == .succeeded}.count)/\(pipeline.todos.count)", "Pipeline実行中... \(pipeline.todos.filter{$0.status == .succeeded}.count)/\(pipeline.todos.count)"))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Button(AppLanguage.shared.t("Stop", "停止")) {
                            // TranspilationPipeline.run()'s per-file loop
                            // checks `isRunning` between files -- this lets
                            // the current file finish, then stops before
                            // starting the next one, rather than an abrupt
                            // mid-file cancel.
                            pipeline.isRunning = false
                        }
                        .buttonStyle(.bordered)
                        .tint(.red)
                    }
                } else {
                    Button {
                        guard let ws = app.workspaceURL, !taskText.isEmpty else { return }
                        let task = taskText
                        let retries = maxRetries
                        Task {
                            await TranspilationPipeline.shared.run(
                                task: task,
                                workspaceURL: ws,
                                maxRetries: retries
                            )
                        }
                        isPresented = false
                    } label: {
                        HStack(spacing: 6) {
                            Image(systemName: "play.fill")
                            Text("Start Pipeline")
                                .fontWeight(.semibold)
                        }
                        .padding(.horizontal, 20)
                        .padding(.vertical, 8)
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(Theme.ok)
                    .disabled(taskText.isEmpty || app.workspaceURL == nil)
                }
            }
            .padding()
            .background(Theme.panel2)
        }
        .frame(width: 560, height: 680)
        .background(Theme.panel2)
    }

    // MARK: - L2.5 地図カード

    private var l25StatusCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(L("L2.5 Project Map (BitNet-generated)", "L2.5 Project Map (BitNet生成)"), systemImage: "map.fill")
                .font(.subheadline.bold())
                .foregroundStyle(Color(red: 0.4, green: 0.85, blue: 1.0))

            if l25Engine.isIndexing {
                HStack {
                    ProgressView(value: l25Engine.indexingProgress)
                        .progressViewStyle(.linear)
                    Text("\(Int(l25Engine.indexingProgress * 100))%")
                        .font(.caption.monospaced())
                }
            } else if let map = l25Engine.projectMap {
                Text("✅ \(map.fileCount) files indexed — \(map.globalTopology.prefix(60))")
                    .font(.caption.monospaced())
                    .foregroundStyle(Theme.ok)
            } else {
                HStack {
                    Text(AppLanguage.shared.t("⚠️ Map not generated. Press Start to auto-generate.", "⚠️ 地図未生成。Startボタンを押すと自動生成します。"))
                        .font(.caption)
                        .foregroundStyle(.orange)
                    Spacer()
                    Button(L("Generate now", "今すぐ生成")) {
                        if let ws = app.workspaceURL {
                            Task { await L25IndexEngine.shared.loadAndIncrementalUpdate(workspaceURL: ws) }
                        }
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.mini)
                }
            }
        }
        .padding(10)
        .background(Color(red: 0.4, green: 0.85, blue: 1.0).opacity(0.06))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    // MARK: - 5層メモリ説明

    private var memoryLayerInfo: some View {
        VStack(alignment: .leading, spacing: 4) {
            Label(L("What each of the five memory layers does", "5層記憶システムの役割"), systemImage: "cpu")
                .font(.caption.bold())
                .foregroundStyle(.secondary)
            ForEach([
                ("L1",   "漢字タグ — ファイル種別・ドメイン高速検索"),
                ("L1.5", "差分フィンガープリント — 変更追跡"),
                ("L2",   "OP.FACT — TODO進捗・エラーパターン"),
                ("L2.5", "ソースコード地図 — qwenが見る唯一の全体像"),
                ("L3",   "生ソース — 処理中のファイル1件のみ"),
            ], id: \.0) { layer, desc in
                HStack(alignment: .top, spacing: 6) {
                    Text(layer)
                        .font(.system(size: 9, weight: .bold, design: .monospaced))
                        .foregroundStyle(Color(red: 0.55, green: 1.0, blue: 0.65))
                        .frame(width: 28, alignment: .leading)
                    Text(desc)
                        .font(.system(size: 9))
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(10)
        .background(Color.white.opacity(0.03))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    // MARK: - パイプライン進捗

    private var pipelineProgressView: some View {
        VStack(alignment: .leading, spacing: 6) {
            Label("Pipeline Progress", systemImage: "list.number")
                .font(.caption.bold())

            ForEach(pipeline.todos.prefix(8)) { todo in
                HStack(spacing: 6) {
                    statusIcon(todo.status)
                    Text(URL(fileURLWithPath: todo.relativePath).lastPathComponent)
                        .font(.system(size: 10, design: .monospaced))
                        .lineLimit(1)
                    Spacer()
                    if todo.retryCount > 0 {
                        Text("retry:\(todo.retryCount)")
                            .font(.system(size: 9))
                            .foregroundStyle(.orange)
                    }
                }
            }
            if pipeline.todos.count > 8 {
                Text("... and \(pipeline.todos.count - 8) more")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(10)
        .background(Color.white.opacity(0.03))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    @ViewBuilder
    private func statusIcon(_ status: TranspilationTodo.Status) -> some View {
        switch status {
        case .pending:    Image(systemName: "circle").foregroundStyle(.secondary).font(.caption2)
        case .inProgress: ProgressView().scaleEffect(0.5).frame(width: 12, height: 12)
        case .succeeded:  Image(systemName: "checkmark.circle.fill").foregroundStyle(.green).font(.caption2)
        case .failed:     Image(systemName: "xmark.circle.fill").foregroundStyle(.red).font(.caption2)
        case .skipped:    Image(systemName: "minus.circle").foregroundStyle(.secondary).font(.caption2)
        }
    }
}
