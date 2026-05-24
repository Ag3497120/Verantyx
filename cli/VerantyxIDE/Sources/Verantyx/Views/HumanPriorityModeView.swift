import SwiftUI
import AppKit

// MARK: - HumanPriorityModeView
// VS Code / Antigravity style layout:
//   [Activity Bar 48pt] | [File Tree 240pt] | [Code Editor flex] | [AI Chat 340pt]
//
// The human writes code directly in the editor.
// The AI chat panel sits on the right as a co-pilot assistant.

struct HumanPriorityModeView: View {
    @EnvironmentObject var app: AppState
    @State private var activitySection: ActivityBarView.ActivitySection = .explorer
    @State private var showSettings     = false
    @State private var showMCPQuick     = false
    @State private var showL25ConversionAlert = false
    @State private var targetWorkspaceForL25: URL? = nil

    // Editor state
    @State private var editorContent: String = ""
    @State private var editorLanguage: String = "swift"
    @State private var hasUnsavedChanges = false
    @State private var saveStatus: SaveStatus = .saved
    @State private var showPipelineSheet = false
    @State private var pipelineTask: String = ""

    enum SaveStatus { case saved, unsaved, saving }
    enum CenterDisplayTab: String, CaseIterable {
        case diff = "Diff"
        case code = "Code"
        case artifact = "Artifact"
    }
    @State private var activeCenterTab: CenterDisplayTab = .code

    var body: some View {
        ZStack {
            VStack(spacing: 0) {
                HStack(spacing: 0) {

                    // ① Activity bar (fixed 48pt)
                    ActivityBarView(selectedSection: $activitySection)
                        .frame(width: 48)

                    // ② Outer split: [Left panel] | [Center + Right]
                    ResizableHSplit(
                        minLeft: 160, maxLeft: 400, minRight: 700, initialLeft: 220
                    ) {
                        // ── Left: File Tree / MCP / Evolution ─────────────────
                        Group {
                            switch activitySection {
                            case .mcp:       MCPView()
                            case .evolution: SelfEvolutionView().environmentObject(app)
                            case .search:    GlobalSearchView().environmentObject(app)
                            case .git:       GitPanelView().environmentObject(app)
                            default:         FileTreeView()
                            }
                        }
                        .frame(maxHeight: .infinity)

                    } right: {
                        // ③ Inner split: [Code Editor] | [AI Chat]
                        ResizableHSplit(
                            minLeft: 400, maxLeft: 99999, minRight: 280, initialLeft: 600
                        ) {
                            // ── Center: Code Editor ────────────────────────────
                            codeEditorPanel

                        } right: {
                            // ── Right: AI Chat ─────────────────────────────────
                            aiChatPanel
                        }
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)

                // ── Loaded Model Panel — shows when model is active ───────
                Group {
                    switch app.modelStatus {
                    case .mlxReady, .ollamaReady:
                        LoadedModelPanel()
                            .environmentObject(app)
                    default:
                        EmptyView()
                    }
                }
                .animation(.spring(response: 0.32, dampingFraction: 0.78), value: app.modelStatus)

                // ── Status bar ────────────────────────────────────────────────
                Divider().opacity(0.4)
                humanPriorityStatusBar
            }
            .background(Color(red: 0.10, green: 0.10, blue: 0.13))

            // ── Settings overlay (same pattern as MainSplitView) ─────────────
            if showSettings {
                Color.black.opacity(0.55)
                    .ignoresSafeArea()
                    .onTapGesture {
                        withAnimation(.easeOut(duration: 0.18)) { showSettings = false }
                    }
                    .transition(.opacity)

                SettingsView(onDismiss: {
                    withAnimation(.easeOut(duration: 0.18)) { showSettings = false }
                })
                .environmentObject(app)
                .transition(.scale(scale: 0.96).combined(with: .opacity))
                .zIndex(10)
            }
        }
        .animation(.easeOut(duration: 0.18), value: showSettings)
        .toastOverlay()
        .onReceive(NotificationCenter.default.publisher(for: Notification.Name("OpenMCPPanel"))) { _ in
            activitySection = .mcp
        }
        // ── Settings を開く ──────────────────────────────────────────────────
        .onChange(of: activitySection) { _, section in
            if section == .settings {
                withAnimation(.easeOut(duration: 0.18)) { showSettings = true }
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) {
                    activitySection = .explorer
                }
            }
        }
        .onChange(of: app.selectedFile) { _, url in
            loadFileIntoEditor(url: url)
        }
        .onChange(of: app.showGatekeeperRawCode) { _, _ in
            loadFileIntoEditor(url: app.selectedFile)
        }
        .onAppear {
            loadFileIntoEditor(url: app.selectedFile)
            // ProcessMonitor 起動 (CPU 監視開始)
            ProcessMonitor.shared.start()
        }
        // ── ワークスペースが変わったら L2.5 変換の確認ダイアログを出す ──────────────────────
        .onChange(of: app.workspaceURL) { _, newWS in
            guard let ws = newWS else { return }
            targetWorkspaceForL25 = ws
            showL25ConversionAlert = true
        }
        .alert(app.t("L2.5 Semantic Conversion", "L2.5 セマンティック変換"), isPresented: $showL25ConversionAlert) {
            Button(app.t("Cancel", "キャンセル"), role: .cancel) { }
            Button(app.t("Start Conversion", "変換を開始する")) {
                if let ws = targetWorkspaceForL25 {
                    Task { @MainActor in
                        await L25IndexEngine.shared.loadAndIncrementalUpdate(workspaceURL: ws)
                    }
                }
            }
        } message: {
            Text(app.t("Do you want to start BitNet L2.5 conversion for this workspace? This may take some time.", "このワークスペースの BitNet による L2.5 変換を開始しますか？（規模により時間がかかります）"))
        }
        .onChange(of: app.pendingDiff) { _, newDiff in
            if newDiff != nil {
                withAnimation { activeCenterTab = .diff }
            }
        }
        .onChange(of: app.currentArtifact?.id) { _, newId in
            if newId != nil {
                withAnimation { activeCenterTab = .artifact }
            }
        }
    }

    // MARK: - Code Editor Panel

    private var codeEditorPanel: some View {
        VStack(spacing: 0) {
            // Tab bar
            editorTabBar

            // L2.5 / BitNet ステータスバー (ゲートキーパーバーと同スタイル)
            L25StatusBar()
                .environmentObject(app)

            Divider().opacity(0.3)

            // Editor body & Terminal
            if app.showProcessLog {
                ResizableVSplit(
                    minTop: 200, maxTop: 99999, minBottom: 80, initialTop: 600
                ) {
                    editorBody
                } bottom: {
                    VStack(spacing: 0) {
                        Divider().opacity(0.3)
                        TerminalPanelView(terminal: app.terminal)
                            .environmentObject(app)
                    }
                }
            } else {
                editorBody
            }
        }
        .background(Color(red: 0.10, green: 0.10, blue: 0.13))
    }

    @ViewBuilder
    private var editorBody: some View {
        switch activeCenterTab {
        case .code:
            if let url = app.selectedFile {
                let isJCrossMode = GatekeeperModeState.shared.isEnabled && !app.showGatekeeperRawCode
                CodeEditorView(
                    content: $editorContent,
                    language: editorLanguage,
                    isEditable: !isJCrossMode,
                    onEdit: {
                        if !isJCrossMode {
                            hasUnsavedChanges = true
                            saveStatus = .unsaved
                        }
                    }
                )
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                emptyEditorState
            }
        case .diff:
            SideBySideDiffView()
                .environmentObject(app)
        case .artifact:
            if let art = app.currentArtifact {
                ArtifactWebView(artifact: art)
                    .id(art.id)
            } else {
                emptyEditorState
            }
        }
    }

    // MARK: - Editor Tab Bar

    private var editorTabBar: some View {
        HStack(spacing: 0) {
            // Tab switcher
            HStack(spacing: 0) {
                ForEach(CenterDisplayTab.allCases, id: \.rawValue) { tab in
                    Button {
                        withAnimation(.easeInOut(duration: 0.12)) { activeCenterTab = tab }
                    } label: {
                        HStack(spacing: 4) {
                            Text(tab.rawValue)
                                .font(.system(size: 11, weight: activeCenterTab == tab ? .semibold : .regular))
                                .foregroundStyle(activeCenterTab == tab ? .white : Color(red: 0.5, green: 0.5, blue: 0.62))
                            if tab == .diff, let diff = app.pendingDiff, diff.hasChanges {
                                Circle().fill(Color(red: 1.0, green: 0.65, blue: 0.2)).frame(width: 6, height: 6)
                            }
                        }
                        .padding(.horizontal, 10)
                        .padding(.vertical, 5)
                        .background(activeCenterTab == tab ? Color.white.opacity(0.08) : Color.clear)
                        .overlay(
                            Rectangle()
                                .fill(activeCenterTab == tab ? Color(red: 0.4, green: 0.75, blue: 1.0) : Color.clear)
                                .frame(height: 1.5),
                            alignment: .bottom
                        )
                    }
                    .contentShape(Rectangle())
                    .buttonStyle(.plain)
                }
            }
            .background(Color(red: 0.16, green: 0.16, blue: 0.20))
            .clipShape(RoundedRectangle(cornerRadius: 6))
            .padding(.leading, 10)

            if let url = app.selectedFile, activeCenterTab == .code {
                HStack(spacing: 6) {
                    // File icon
                    Image(systemName: fileIcon(for: url))
                        .font(.system(size: 11))
                        .foregroundStyle(fileIconColor(for: url))

                    Text(url.lastPathComponent)
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(Color(red: 0.88, green: 0.88, blue: 0.95))

                    // Unsaved dot
                    if hasUnsavedChanges {
                        Circle()
                            .fill(Color(red: 0.9, green: 0.7, blue: 0.3))
                            .frame(width: 6, height: 6)
                    }
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 7)
                .background(Color(red: 0.13, green: 0.13, blue: 0.17))
                .overlay(
                    Rectangle()
                        .fill(Color(red: 0.4, green: 0.75, blue: 1.0).opacity(0.6))
                        .frame(height: 1),
                    alignment: .top
                )
            }

            Spacer()

            // Save button / status
            HStack(spacing: 8) {
                if GatekeeperModeState.shared.isEnabled {
                    Picker("Gatekeeper View", selection: $app.showGatekeeperRawCode) {
                        Text("JCross IR").tag(false)
                        Text("Source File").tag(true)
                    }
                    .pickerStyle(.segmented)
                    .labelsHidden()
                    .frame(width: 150)
                    
                    Divider().frame(height: 16).opacity(0.4)
                }

                if hasUnsavedChanges {
                    Button(action: saveCurrentFile) {
                        HStack(spacing: 4) {
                            Image(systemName: "square.and.arrow.down")
                                .font(.system(size: 11))
                            Text("Save")
                                .font(.system(size: 11, weight: .medium))
                        }
                        .foregroundStyle(Color(red: 0.4, green: 0.85, blue: 0.55))
                        .padding(.horizontal, 10)
                        .padding(.vertical, 4)
                        .contentShape(Rectangle())
                        .background(
                            RoundedRectangle(cornerRadius: 5)
                                .fill(Color(red: 0.15, green: 0.32, blue: 0.20).opacity(0.8))
                        )
                    }
                    .contentShape(Rectangle())
                    .buttonStyle(.plain)
                    .keyboardShortcut("s", modifiers: .command)
                    .transition(.scale.combined(with: .opacity))
                }
            }
            .padding(.horizontal, 10)
            .animation(.easeInOut(duration: 0.15), value: hasUnsavedChanges)
        }
        .frame(height: 34)
        .background(Color(red: 0.11, green: 0.11, blue: 0.15))
    }

    // MARK: - Empty Editor State

    private var emptyEditorState: some View {
        VStack(spacing: 20) {
            Image(systemName: "cursorarrow.rays")
                .font(.system(size: 48))
                .foregroundStyle(Color(red: 0.35, green: 0.35, blue: 0.45))

            VStack(spacing: 6) {
                Text("No file selected")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundStyle(Color(red: 0.55, green: 0.55, blue: 0.68))

                Text("Select a file from the explorer to start editing")
                    .font(.system(size: 12))
                    .foregroundStyle(Color(red: 0.38, green: 0.38, blue: 0.50))
            }


        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(red: 0.09, green: 0.09, blue: 0.12))
    }

    // MARK: - AI Chat Panel (right side)

    private var aiChatPanel: some View {
        VStack(spacing: 0) {
            // Chat header
            HStack(spacing: 8) {
                Image(systemName: "sparkles")
                    .font(.system(size: 12))
                    .foregroundStyle(Color(red: 0.55, green: 1.0, blue: 0.65))

                Text("AI Assistant")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Color(red: 0.80, green: 0.80, blue: 0.92))

                Spacer()

                // ── L2.5 地図生成ボタン ────────────────────────
                IsolatedL25HeaderButton()

                Divider().frame(height: 14).opacity(0.3)

                // ── ▶ Run Pipeline ボタン ───────────────────────────
                IsolatedPipelineHeaderButton(showPipelineSheet: $showPipelineSheet)

                Divider().frame(height: 14).opacity(0.3)

                // Mode badge
                Text("Human Priority")
                    .font(.system(size: 9, weight: .bold, design: .monospaced))
                    .foregroundStyle(Color(red: 0.55, green: 1.0, blue: 0.65))
                    .padding(.horizontal, 6).padding(.vertical, 2)
                    .background(
                        Capsule()
                            .fill(Color(red: 0.55, green: 1.0, blue: 0.65).opacity(0.12))
                            .overlay(
                                Capsule()
                                    .stroke(Color(red: 0.55, green: 1.0, blue: 0.65).opacity(0.35), lineWidth: 0.8)
                            )
                    )
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 9)
            .background(Color(red: 0.11, green: 0.11, blue: 0.15))
            .overlay(
                Rectangle()
                    .fill(Color(red: 0.55, green: 1.0, blue: 0.65).opacity(0.25))
                    .frame(height: 1),
                alignment: .top
            )

            Divider().opacity(0.25)

            // Chat view
            AgentChatView()
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .background(Color(red: 0.10, green: 0.10, blue: 0.14))
        .sheet(isPresented: $showPipelineSheet) {
            PipelineLaunchSheet(isPresented: $showPipelineSheet, taskText: $pipelineTask)
                .environmentObject(app)
        }
    }

    // MARK: - Status Bar

    private var humanPriorityStatusBar: some View {
        HStack(spacing: 12) {
            // Mode indicator
            HStack(spacing: 5) {
                Image(systemName: "keyboard")
                    .font(.system(size: 10))
                    .foregroundStyle(Color(red: 0.55, green: 1.0, blue: 0.65))
                Text("Human Priority")
                    .font(.system(size: 10, weight: .medium))
                    .foregroundStyle(Color(red: 0.55, green: 1.0, blue: 0.65))
            }

            Divider().frame(height: 12).opacity(0.4)

            // File info
            if let url = app.selectedFile {
                Text(url.lastPathComponent)
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(Color(red: 0.55, green: 0.55, blue: 0.70))

                Text("•")
                    .foregroundStyle(Color(red: 0.35, green: 0.35, blue: 0.48))

                Text(editorLanguage.uppercased())
                    .font(.system(size: 10, weight: .medium, design: .monospaced))
                    .foregroundStyle(Color(red: 0.55, green: 0.55, blue: 0.70))

                if hasUnsavedChanges {
                    Text("•")
                        .foregroundStyle(Color(red: 0.35, green: 0.35, blue: 0.48))
                    Text("●")
                        .font(.system(size: 8))
                        .foregroundStyle(Color(red: 0.9, green: 0.7, blue: 0.3))
                }
            }

            Spacer()

            // CPU インジケーター (負荷が高いとき赤で点滅)
            IsolatedCPUPill()

            // Model status (reuse from StatusBarView)
            StatusBarView(terminal: app.terminal)
                .frame(maxHeight: .infinity)
        }
        .padding(.horizontal, 12)
        .frame(height: 24)
        .background(Color(red: 0.09, green: 0.09, blue: 0.12))
    }



    // MARK: - Actions

    private func loadFileIntoEditor(url: URL?) {
        guard let url = url else { return }
        let gatekeeper = GatekeeperModeState.shared
        if gatekeeper.isEnabled && !app.showGatekeeperRawCode {
            let relativePath: String
            if let wsPath = app.workspaceURL?.path,
               url.path.hasPrefix(wsPath + "/") {
                relativePath = String(url.path.dropFirst(wsPath.count + 1))
            } else {
                relativePath = url.lastPathComponent
            }
            Task {
                let vault = gatekeeper.vault
                let result = vault.read(relativePath: relativePath)
                if let vaultResult = result {
                    let banner = """
                    ;;; 🛡️ GATEKEEPER MODE — JCross IR View
                    ;;; Real identifiers have been replaced with node IDs.
                    ;;; Schema: \(vaultResult.entry.schemaSessionID.prefix(12))
                    ;;; Nodes: \(vaultResult.entry.nodeCount) | Secrets redacted: \(vaultResult.entry.secretCount)
                    ;;; Source: \(relativePath)
                    ;;; 
                    ;;; (To view raw code, toggle "Source File" above)
                    ;;;
                    """
                    let irContent = banner + "\n" + vaultResult.jcrossContent
                    await MainActor.run {
                        editorContent = irContent
                        editorLanguage = "jcross"
                        hasUnsavedChanges = false
                        saveStatus = .saved
                    }
                } else {
                    let raw = (try? String(contentsOf: url, encoding: .utf8)) ?? ""
                    let warning = app.t("""
                    ;;; ⚠️ GATEKEEPER MODE — This file is not yet converted to JCross
                    ;;; Please update the Vault via [Gatekeeper Settings] -> [Start Batch Conversion]
                    ;;; * The following is the raw source code. This view is temporary.
                    ;;;
                    
                    """, """
                    ;;; ⚠️ GATEKEEPER MODE — このファイルはまだ JCross 変換されていません
                    ;;; [Gatekeeper 設定] → [一括変換を開始] でVaultを更新してください
                    ;;; ※ 以下は実コードです。このビューは一時的なものです
                    ;;;
                    
                    """)
                    await MainActor.run {
                        editorContent = warning + raw
                        editorLanguage = "jcross"
                        hasUnsavedChanges = false
                        saveStatus = .saved
                    }
                }
            }
        } else {
            do {
                let content = try String(contentsOf: url, encoding: .utf8)
                editorContent = content
                editorLanguage = languageForExtension(url.pathExtension)
                hasUnsavedChanges = false
                saveStatus = .saved
            } catch {
                editorContent = ""
            }
        }
    }

    private func saveCurrentFile() {
        guard let url = app.selectedFile, hasUnsavedChanges else { return }
        saveStatus = .saving
        do {
            try editorContent.write(to: url, atomically: true, encoding: .utf8)
            hasUnsavedChanges = false
            saveStatus = .saved
            app.selectedFileContent = editorContent
            ToastManager.shared.show(
                "Saved \(url.lastPathComponent)",
                icon: "checkmark.circle.fill",
                color: Color(red: 0.3, green: 0.9, blue: 0.5)
            )
        } catch {
            saveStatus = .unsaved
            ToastManager.shared.show("Save failed: \(error.localizedDescription)", icon: "xmark.circle.fill", color: .red)
        }
    }

    // MARK: - Helpers

    private func fileIcon(for url: URL) -> String {
        switch url.pathExtension.lowercased() {
        case "swift":  return "swift"
        case "ts","js","tsx","jsx": return "doc.text"
        case "py":     return "doc.text"
        case "json":   return "curlybraces"
        case "md":     return "doc.richtext"
        case "html","htm": return "globe"
        case "css":    return "paintbrush"
        default:       return "doc.text"
        }
    }

    private func fileIconColor(for url: URL) -> Color {
        switch url.pathExtension.lowercased() {
        case "swift":  return Color(red: 1.0, green: 0.55, blue: 0.25)
        case "ts","tsx": return Color(red: 0.3, green: 0.6, blue: 1.0)
        case "js","jsx": return Color(red: 1.0, green: 0.85, blue: 0.2)
        case "py":     return Color(red: 0.4, green: 0.8, blue: 0.4)
        case "json":   return Color(red: 1.0, green: 0.75, blue: 0.3)
        case "md":     return Color(red: 0.7, green: 0.7, blue: 0.85)
        case "html","htm": return Color(red: 1.0, green: 0.5, blue: 0.3)
        default:       return Color(red: 0.6, green: 0.6, blue: 0.75)
        }
    }

    private func languageForExtension(_ ext: String) -> String {
        switch ext.lowercased() {
        case "swift":        return "swift"
        case "ts", "tsx":    return "typescript"
        case "js", "jsx":    return "javascript"
        case "py":           return "python"
        case "json":         return "json"
        case "md":           return "markdown"
        case "html", "htm":  return "html"
        case "css":          return "css"
        case "sh":           return "bash"
        case "yml", "yaml":  return "yaml"
        case "rs":           return "rust"
        case "go":           return "go"
        case "kt":           return "kotlin"
        default:             return ext.isEmpty ? "text" : ext
        }
    }

}

// MARK: - L25StatusBar
// タブバー直下に常時表示される L2.5 / BitNet ステータスバー。
// ゲートキーパーバーと同スタイル。状態に応じて色・内容が変化する。
//
//  ⚫ 未生成   → グレー  「⬡ L2.5 — 未初期化」
//  🟡 全体変換 → オレンジ「⬡ BitNet 変換中 ██░░░ 45%」(アニメーション)
//  🔵 差分更新 → シアン  「⬡ 差分更新中 ██░░░ 3/8 files」
//  🟢 準備完了 → 緑      「⬡ L2.5 準備完了 · 124 files · 3分前」

struct L25StatusBar: View {
    @EnvironmentObject var app: AppState
    @ObservedObject private var engine = L25IndexEngine.shared
    @State private var animPhase: CGFloat = 0
    @State private var showCancelConfirm = false

    private var barColor: Color {
        if engine.isStopped {
            return Color(red: 0.90, green: 0.22, blue: 0.22)  // 赤 (停止済み)
        }
        switch engine.indexingMode {
        case .full:        return Color(red: 1.0, green: 0.65, blue: 0.15)
        case .incremental: return Color(red: 0.25, green: 0.85, blue: 1.0)
        case .none:
            if engine.projectMap != nil { return Color(red: 0.25, green: 0.80, blue: 0.45) }
            return Color(red: 0.40, green: 0.40, blue: 0.52)
        }
    }

    private var bgColor: Color { barColor.opacity(0.10) }

    private var statusText: String {
        // 停止済み: 最優先で表示
        if engine.isStopped {
            let pct  = Int(engine.indexingProgress * 100)
            let done = engine.projectMap?.fileCount ?? 0
            return "⏹ 変換停止済み — \(pct)% / \(done) files 保存済・再開可能"
        }
        switch engine.indexingMode {
        case .full:
            let pct = Int(engine.indexingProgress * 100)
            let file = engine.currentFile.isEmpty ? "" : " · \(engine.currentFile)"
            return "⬡ BitNet L2.5 変換中 \(pct)%\(file)"
        case .incremental:
            let total = engine.projectMap?.fileCount ?? 0
            let done  = Int(engine.indexingProgress * Double(max(total, 1)))
            let file  = engine.currentFile.isEmpty ? "" : " · \(engine.currentFile)"
            return "⬡ 差分更新中 \(done)/\(total) files\(file)"
        case .none:
            if let map = engine.projectMap {
                let mins = Int(-map.generatedAt.timeIntervalSinceNow / 60)
                let timeStr = mins < 1 ? "たった今" : "\(mins)分前"
                return "⬡ L2.5 準備完了 · \(map.fileCount) files · \(timeStr)"
            }
            return "⬡ L2.5 — 未初期化 (ワークスペースを開いてください)"
        }
    }

    private var isIndexing: Bool { engine.indexingMode != .none }

    var body: some View {
        ZStack(alignment: .leading) {
            // ── 背景 ──────────────────────────────────────────────────
            barColor.opacity(0.06)

            // ── 進捗フィル ────────────────────────────────────────────
            if isIndexing {
                GeometryReader { geo in
                    barColor.opacity(0.18)
                        .frame(width: geo.size.width * engine.indexingProgress)
                        .animation(.linear(duration: 0.3), value: engine.indexingProgress)
                }
            }

            // ── コンテンツ ────────────────────────────────────────────
            HStack(spacing: 8) {
                // アイコン (インデックス中はパルス)
                ZStack {
                    Circle()
                        .fill(barColor)
                        .frame(width: 6, height: 6)
                    if isIndexing {
                        Circle()
                            .stroke(barColor.opacity(0.4), lineWidth: 1)
                            .frame(width: 6 + animPhase * 6, height: 6 + animPhase * 6)
                            .opacity(1 - animPhase)
                    }
                }

                // ステータステキスト
                Text(statusText)
                    .font(.system(size: 11, weight: .medium, design: .monospaced))
                    .foregroundStyle(barColor)
                    .lineLimit(1)
                    .truncationMode(.middle)

                Spacer()

                // 変換中: 進捗バー + 停止ボタン
                if isIndexing {
                    ProgressView(value: engine.indexingProgress)
                        .progressViewStyle(.linear)
                        .frame(width: 80)
                        .tint(barColor)
                        .scaleEffect(x: 1, y: 0.5)

                    // ── 停止ボタン ───────────────────────────────────────
                    Button {
                        showCancelConfirm = true
                    } label: {
                        HStack(spacing: 3) {
                            Image(systemName: "stop.fill")
                                .font(.system(size: 8, weight: .bold))
                            Text(AppLanguage.shared.t("Stop", "停止"))
                                .font(.system(size: 10, weight: .bold))
                        }
                        .foregroundStyle(.white)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 3)
                        .background(
                            Capsule()
                                .fill(Color(red: 0.80, green: 0.18, blue: 0.18))
                                .shadow(color: Color.red.opacity(0.5), radius: 4)
                        )
                    }
                    .buttonStyle(.plain)
                    .transition(.scale.combined(with: .opacity))
                    .confirmationDialog(
                        "L2.5 変換を停止しますか？",
                        isPresented: $showCancelConfirm,
                        titleVisibility: .visible
                    ) {
                        Button("停止する", role: .destructive) {
                            L25IndexEngine.shared.cancelIndexing()
                        }
                        Button("続ける", role: .cancel) { }
                    } message: {
                        Text(AppLanguage.shared.t("Converted files will be kept.\nYou can resume from where you left off.", "変換済みのファイルは保持されます。\n再開ボタンで続きから再開できます。"))
                    }

                // 停止済みバナー + 再開ボタン
                } else if engine.isStopped {
                    HStack(spacing: 4) {
                        Image(systemName: "exclamationmark.octagon.fill")
                            .font(.system(size: 9, weight: .bold))
                            .foregroundStyle(.white)
                        Text(AppLanguage.shared.t("Stopped", "停止済み"))
                            .font(.system(size: 9, weight: .heavy))
                            .foregroundStyle(.white)
                    }
                    .padding(.horizontal, 6)
                    .padding(.vertical, 3)
                    .background(Capsule().fill(Color(red: 0.85, green: 0.15, blue: 0.15)))
                    .transition(.scale.combined(with: .opacity))

                    Button { engine.resumeIndexing() } label: {
                        HStack(spacing: 3) {
                            Image(systemName: "play.fill")
                                .font(.system(size: 8, weight: .bold))
                            Text(AppLanguage.shared.t("Resume", "再開"))
                                .font(.system(size: 10, weight: .bold))
                        }
                        .foregroundStyle(.white)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 3)
                        .background(
                            Capsule()
                                .fill(Color(red: 0.20, green: 0.55, blue: 0.90))
                                .shadow(color: Color.blue.opacity(0.4), radius: 4)
                        )
                    }
                    .buttonStyle(.plain)
                    .transition(.scale.combined(with: .opacity))

                // 完了後の再インデックスボタン
                } else if engine.hasPausedMap {
                    Button { engine.resumeIndexing() } label: {
                        HStack(spacing: 3) {
                            Image(systemName: "play.fill")
                                .font(.system(size: 8, weight: .bold))
                            Text(AppLanguage.shared.t("Resume", "再開"))
                                .font(.system(size: 10, weight: .bold))
                        }
                        .foregroundStyle(.white)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 3)
                        .background(
                            Capsule()
                                .fill(Color(red: 0.20, green: 0.55, blue: 0.90))
                                .shadow(color: Color.blue.opacity(0.4), radius: 4)
                        )
                    }
                    .buttonStyle(.plain)
                    .transition(.scale.combined(with: .opacity))
                }

            }
            .padding(.horizontal, 12)
            .padding(.vertical, 5)
        }
        .frame(height: 26)
        .overlay(
            Rectangle()
                .fill(barColor.opacity(0.35))
                .frame(height: 1),
            alignment: .bottom
        )
        .onAppear {
            withAnimation(.easeInOut(duration: 1.2).repeatForever(autoreverses: false)) {
                animPhase = 1
            }
        }
        .animation(.easeInOut(duration: 0.3), value: engine.indexingMode)
    }
}

// MARK: - CPUActivityPanel
// PROCESS LOG の上部に常時表示されるリアルタイム CPU 監視パネル。
// 何のプロセスが CPU を消費しているかを即座に把握できる。

struct CPUActivityPanel: View {
    @ObservedObject var monitor: ProcessMonitor

    var body: some View {
        VStack(spacing: 0) {
            // ── ヘッダー ──────────────────────────────────────────────
            HStack(spacing: 6) {
                // CPU 合計ゲージ
                let totalCPU = monitor.totalCPU
                let gaugeColor: Color = totalCPU > 80 ? Color(red: 1.0, green: 0.3, blue: 0.3)
                                      : totalCPU > 40 ? Color(red: 1.0, green: 0.75, blue: 0.2)
                                      :                  Color(red: 0.4, green: 0.85, blue: 0.55)

                Image(systemName: "cpu")
                    .font(.system(size: 9))
                    .foregroundStyle(gaugeColor)

                Text("CPU ACTIVITY")
                    .font(.system(size: 9, weight: .bold, design: .monospaced))
                    .foregroundStyle(Color(red: 0.5, green: 0.5, blue: 0.65))

                Text("·")
                    .foregroundStyle(Color(red: 0.3, green: 0.3, blue: 0.42))

                Text("TOP \(String(format: "%.0f", totalCPU))%")
                    .font(.system(size: 9, weight: .semibold, design: .monospaced))
                    .foregroundStyle(gaugeColor)

                // 高負荷警告
                if totalCPU > 80 {
                    Text("⚡ HIGH LOAD")
                        .font(.system(size: 8, weight: .bold, design: .monospaced))
                        .foregroundStyle(Color(red: 1.0, green: 0.3, blue: 0.3))
                }

                Spacer()
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(Color(red: 0.09, green: 0.09, blue: 0.13))

            // ── プロセスリスト ─────────────────────────────────────────
            VStack(spacing: 2) {
                ForEach(monitor.topProcesses.prefix(6)) { proc in
                    CPUProcessRow(info: proc, maxCPU: monitor.topProcesses.first?.cpuPercent ?? 1)
                }
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 5)
            .background(Color(red: 0.08, green: 0.08, blue: 0.11))
        }
    }
}

struct CPUProcessRow: View {
    let info: ProcessMonitor.ProcessInfo
    let maxCPU: Double

    private var barColor: Color {
        if info.isVerantyxRelated {
            return info.cpuPercent > 80
                ? Color(red: 1.0, green: 0.3, blue: 0.3)
                : Color(red: 0.3, green: 0.85, blue: 1.0)  // Verantyx 関連 = シアン
        }
        return info.cpuPercent > 50
            ? Color(red: 0.9, green: 0.5, blue: 0.2)
            : Color(red: 0.4, green: 0.4, blue: 0.55)
    }

    var body: some View {
        HStack(spacing: 6) {
            // プロセス名
            Text(info.label)
                .font(.system(size: 9, weight: info.isVerantyxRelated ? .semibold : .regular, design: .monospaced))
                .foregroundStyle(info.isVerantyxRelated
                    ? Color(red: 0.85, green: 0.92, blue: 1.0)
                    : Color(red: 0.55, green: 0.55, blue: 0.68))
                .frame(width: 180, alignment: .leading)
                .lineLimit(1)

            // CPU バー
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 2)
                        .fill(Color(red: 0.15, green: 0.15, blue: 0.20))
                    RoundedRectangle(cornerRadius: 2)
                        .fill(barColor.opacity(0.85))
                        .frame(width: max(2, geo.size.width * CGFloat(info.cpuPercent / max(maxCPU, 1))))
                        .animation(.linear(duration: 0.4), value: info.cpuPercent)
                }
            }
            .frame(height: 5)

            // メモリ
            Text("\(String(format: "%.0f", info.memMB))%")
                .font(.system(size: 8, design: .monospaced))
                .foregroundStyle(Color(red: 0.35, green: 0.35, blue: 0.48))
                .frame(width: 28, alignment: .trailing)
        }
    }
}

// MARK: - CodeEditorView
// Native NSTextView-based code editor with line numbers and monospaced font.
// Supports direct editing and calls onEdit callback on each change.

struct CodeEditorView: NSViewRepresentable {
    @Binding var content: String
    let language: String
    var isEditable: Bool = true
    let onEdit: () -> Void

    func makeNSView(context: Context) -> NSScrollView {
        let scrollView = NSTextView.scrollableTextView()
        guard let textView = scrollView.documentView as? NSTextView else { return scrollView }

        textView.delegate = context.coordinator
        
        textView.isHorizontallyResizable = true
        textView.isVerticallyResizable   = true
        textView.autoresizingMask        = [.width]
        textView.textContainer?.widthTracksTextView = false
        textView.textContainer?.containerSize = CGSize(
            width: CGFloat.greatestFiniteMagnitude,
            height: CGFloat.greatestFiniteMagnitude
        )
        
        textView.layoutManager?.allowsNonContiguousLayout = true
        textView.layoutManager?.backgroundLayoutEnabled   = true
        
        textView.isEditable   = isEditable
        textView.isSelectable = true
        textView.usesFontPanel = false
        textView.usesFindPanel = false
        textView.allowsUndo   = true
        
        textView.font         = NSFont.monospacedSystemFont(ofSize: 13, weight: .regular)
        textView.textColor    = NSColor(red: 0.88, green: 0.88, blue: 0.95, alpha: 1.0)
        textView.backgroundColor = NSColor(red: 0.09, green: 0.09, blue: 0.12, alpha: 1.0)
        textView.textContainerInset = NSSize(width: 8, height: 8)
        
        scrollView.hasVerticalScroller = true
        scrollView.hasHorizontalScroller = true
        scrollView.autohidesScrollers = true
        scrollView.backgroundColor = NSColor(red: 0.09, green: 0.09, blue: 0.12, alpha: 1.0)
        
        // Temporarily disable the ruler to isolate layout bugs
        // let rulerView = LineNumberRulerView(textView: textView)
        // scrollView.verticalRulerView = rulerView
        // scrollView.hasVerticalRuler = true
        // scrollView.rulersVisible = true

        return scrollView
    }

    func updateNSView(_ scrollView: NSScrollView, context: Context) {
        context.coordinator.parent = self
        
        guard let textView = scrollView.documentView as? NSTextView else { return }
        if textView.isEditable != isEditable {
            textView.isEditable = isEditable
        }
        if textView.string != content {
            let selectedRange = textView.selectedRange()
            
            // Just set string directly
            textView.string = content
            
            if let storage = textView.textStorage {
                storage.beginEditing()
                let fullRange = NSRange(location: 0, length: storage.length)
                storage.addAttributes([
                    .font: NSFont.monospacedSystemFont(ofSize: 13, weight: .regular),
                    .foregroundColor: NSColor(red: 0.88, green: 0.88, blue: 0.95, alpha: 1.0)
                ], range: fullRange)
                storage.endEditing()
            }
            
            // Critical for editable text views
            textView.didChangeText()
            
            // Restore selection if possible
            let safeLen = min(selectedRange.location + selectedRange.length, textView.string.count)
            if safeLen <= textView.string.count {
                textView.setSelectedRange(NSRange(location: min(selectedRange.location, textView.string.count), length: 0))
            }
        }
    }

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    class Coordinator: NSObject, NSTextViewDelegate {
        var parent: CodeEditorView
        init(_ parent: CodeEditorView) { self.parent = parent }

        func textDidChange(_ notification: Notification) {
            guard let textView = notification.object as? NSTextView else { return }
            if parent.content != textView.string {
                parent.content = textView.string
                parent.onEdit()
            }
            // applyHighlighting(to: textView)
            
            // Redraw line numbers
            if let scrollView = textView.enclosingScrollView,
               let ruler = scrollView.verticalRulerView {
                ruler.needsDisplay = true
            }
        }

        func applyHighlighting(to textView: NSTextView) {
            guard let textStorage = textView.textStorage else { return }
            let string = textStorage.string
            let langEnum = SyntaxHighlighter.language(for: URL(fileURLWithPath: "dummy.\(parent.language)"))
            let tokens = SyntaxHighlighter.tokenize(string, language: langEnum)
            
            // Only update layout attributes to avoid interfering with cursor and undo state
            textStorage.beginEditing()
            let fullRange = NSRange(location: 0, length: textStorage.length)
            
            // Apply default style safely to reset
            let defaultColor = NSColor(red: 0.88, green: 0.88, blue: 0.95, alpha: 1.0)
            let defaultFont = NSFont.monospacedSystemFont(ofSize: 13, weight: .regular)
            textStorage.addAttribute(.foregroundColor, value: defaultColor, range: fullRange)
            textStorage.addAttribute(.font, value: defaultFont, range: fullRange)
            
            var currentIndex = 0
            for token in tokens {
                let tokenLength = token.text.utf16.count
                if currentIndex + tokenLength <= fullRange.length {
                    let range = NSRange(location: currentIndex, length: tokenLength)
                    
                    let nsColor: NSColor
                    switch token.kind {
                    case .keyword:    nsColor = NSColor(red: 0.42, green: 0.62, blue: 0.99, alpha: 1.0)
                    case .keyword2:   nsColor = NSColor(red: 0.73, green: 0.52, blue: 0.99, alpha: 1.0)
                    case .string:     nsColor = NSColor(red: 0.99, green: 0.50, blue: 0.40, alpha: 1.0)
                    case .comment:    nsColor = NSColor(red: 0.44, green: 0.68, blue: 0.44, alpha: 1.0)
                    case .number:     nsColor = NSColor(red: 0.34, green: 0.90, blue: 0.80, alpha: 1.0)
                    case .type:       nsColor = NSColor(red: 0.99, green: 0.85, blue: 0.42, alpha: 1.0)
                    case .function_:  nsColor = NSColor(red: 0.40, green: 0.85, blue: 0.80, alpha: 1.0)
                    case .attribute:  nsColor = NSColor(red: 0.75, green: 0.75, blue: 0.90, alpha: 1.0)
                    case .operator_:  nsColor = NSColor(red: 0.95, green: 0.95, blue: 0.95, alpha: 1.0)
                    case .punctuation:nsColor = NSColor(red: 0.70, green: 0.70, blue: 0.70, alpha: 1.0)
                    case .plain:      nsColor = NSColor(red: 0.92, green: 0.92, blue: 0.92, alpha: 1.0)
                    }
                    
                    textStorage.addAttribute(.foregroundColor, value: nsColor, range: range)
                    
                    if token.kind == .keyword || token.kind == .keyword2 {
                        textStorage.addAttribute(.font, value: NSFont.monospacedSystemFont(ofSize: 13, weight: .semibold), range: range)
                    } else {
                        textStorage.addAttribute(.font, value: NSFont.monospacedSystemFont(ofSize: 13, weight: .regular), range: range)
                    }
                }
                currentIndex += tokenLength
            }
            textStorage.endEditing()
        }
    }
}

// MARK: - Isolated Components

struct IsolatedCPUActivityPanel: View {
    @ObservedObject private var processMonitor = ProcessMonitor.shared
    var body: some View {
        if processMonitor.isHighLoad || !processMonitor.topProcesses.isEmpty {
            Divider().opacity(0.2)
            CPUActivityPanel(monitor: processMonitor)
        }
    }
}

struct IsolatedCPUPill: View {
    @ObservedObject private var processMonitor = ProcessMonitor.shared
    var body: some View {
        if !processMonitor.topProcesses.isEmpty {
            let topProc = processMonitor.topProcesses.first
            let cpu = topProc?.cpuPercent ?? 0
            let color: Color = cpu > 80 ? Color(red: 1.0, green: 0.35, blue: 0.35)
                             : cpu > 40 ? Color(red: 1.0, green: 0.75, blue: 0.2)
                             :             Color(red: 0.4, green: 0.9, blue: 0.55)
            HStack(spacing: 4) {
                Circle().fill(color).frame(width: 5, height: 5)
                Text(topProc?.label ?? "CPU \(Int(cpu))%")
                    .font(.system(size: 9, weight: .medium, design: .monospaced))
                    .foregroundStyle(color)
            }
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(color.opacity(0.1), in: RoundedRectangle(cornerRadius: 4))
        }
    }
}

struct IsolatedL25HeaderButton: View {
    @EnvironmentObject var app: AppState
    @ObservedObject private var l25Engine = L25IndexEngine.shared
    
    var body: some View {
        if l25Engine.isIndexing {
            HStack(spacing: 4) {
                ProgressView().scaleEffect(0.6)
                Text("L2.5 \(Int(l25Engine.indexingProgress * 100))%")
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(Color(red: 0.6, green: 0.85, blue: 1.0))
            }
        } else if l25Engine.projectMap != nil {
            Label("\(l25Engine.projectMap?.fileCount ?? 0) files mapped", systemImage: "map.fill")
                .font(.system(size: 9, weight: .medium))
                .foregroundStyle(Color(red: 0.4, green: 0.85, blue: 0.6))
        } else {
            Button {
                if let ws = app.workspaceURL {
                    Task { await L25IndexEngine.shared.loadAndIncrementalUpdate(workspaceURL: ws) }
                }
            } label: {
                Label("Map", systemImage: "map")
                    .font(.system(size: 9, weight: .medium))
                    .foregroundStyle(Color(red: 0.6, green: 0.85, blue: 1.0))
            }
            .buttonStyle(.plain)
        }
    }
}

struct IsolatedPipelineHeaderButton: View {
    @ObservedObject private var pipeline = TranspilationPipeline.shared
    @Binding var showPipelineSheet: Bool
    
    var body: some View {
        if pipeline.isRunning {
            HStack(spacing: 4) {
                ProgressView().scaleEffect(0.6)
                Text("Pipeline \(pipeline.todos.filter{$0.status == .succeeded}.count)/\(pipeline.todos.count)")
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(Color(red: 1.0, green: 0.75, blue: 0.3))
            }
        } else {
            Button {
                showPipelineSheet = true
            } label: {
                HStack(spacing: 3) {
                    Image(systemName: "play.fill")
                        .font(.system(size: 8))
                    Text("Pipeline")
                        .font(.system(size: 9, weight: .bold))
                }
                .foregroundStyle(.black)
                .padding(.horizontal, 7).padding(.vertical, 3)
                .background(
                    Capsule().fill(Color(red: 0.55, green: 1.0, blue: 0.65))
                )
            }
            .buttonStyle(.plain)
        }
    }
}
