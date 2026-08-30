import SwiftUI
import UniformTypeIdentifiers

// MARK: - MainSplitView
// Verantyx IDE layout — switches between:
//   • Human Mode          → 4-pane IDE (Activity + File Tree + Chat + Diff/Terminal)
//   • AI Priority         → Full-screen 2-pane (Chat | Artifact) — AIModeLayoutView
//   • Human Priority Mode → VS Code-style (File Tree | Code Editor | AI Chat right)
//   • Gatekeeper Mode     → Human Priority layout + persistent green Gatekeeper border

struct MainSplitView: View {
    @EnvironmentObject var app: AppState
    @State private var showMCPQuick     = false

    /// True once any non-system message exists — locks the mode toggle
    private var chatStarted: Bool {
        app.messages.contains { $0.role != .system }
    }

    var body: some View {
        ZStack {
            Group {
                    // ── Enterprise Gatekeeper Mode Layout ─
                    // (The persistent green mode border is gone by request —
                    // the Gatekeeper chip in the chat bar already names the
                    // mode, and a painted frame around the whole window read
                    // as decoration, not information.)
                    HumanPriorityModeView()
                        .environmentObject(app)

                // ── MCP Quick Panel global overlay (⌘⇧M) ────────────────────────
                if showMCPQuick {
                    MCPQuickPanel(isPresented: $showMCPQuick)
                        .environmentObject(app)
                        .zIndex(99)
                        .transition(.scale(scale: 0.96).combined(with: .opacity))
                }
            }
            .animation(.easeInOut(duration: 0.25), value: app.operationMode)

            // The Settings and Extension Store overlays lived here. Both
            // were opened by `activitySection == .settings` and by nothing
            // else, and the rail that set it is gone — they had become
            // screens with no door. Settings itself is not lost: the live
            // one is HumanPriorityModeView's, raised by
            // `app.showSettingsRequested`, which is what every caller
            // already used. Atelier mode has its own settings screen the
            // same way, raised by `app.showAtelierSettingsRequested` and
            // presented alongside it — two independent overlays, not one
            // screen with a mode switch inside it.

            // ── VS Code Extension UI Overlay ──────────────────────────────
            ExtensionUIPanelView()
                .zIndex(105)
                
            // ── Floating Action Button (Expert Bot) ───────────────────────
            // The floating assistant is gone. In an app whose entire surface
            // is a conversation, a second place to ask questions is a strange
            // thing to keep — and it sat on top of the send control, which is
            // the one button that must never be covered. Guidance belongs in
            // the chat that is already there.
                .zIndex(200)
                
            // Removed Mode Selector Overlay
        }
        .toolbar { toolbarContent }
        // 自動接続は LLM を使うモードだけ(2026-08-19)。Vera 単体/ぼっとで
        // Ollama の接続警告が出るのは説明と矛盾する。
        // どちらも「下見」— 見つかれば拾い、居なければ黙る。Ollama は
        // 11 ある backend の 1 つなので、居ないことは異常ではない。
        // 人が明示的に繋ぎにいったときだけ結果を報せる(announce: true)。
        .onAppear { if app.usesLLMBackend { app.connectOllama(announce: false) } }
        .onChange(of: app.veraEngineMode) { _, _ in
            // モードを LLM 側へ戻したらそこで繋ぐ — 起動時に諦めたままに
            // しない。
            if app.usesLLMBackend { app.connectOllama(announce: false) }
        }
        // ── Human Mode: file write approval sheet ────────────────────────────
        .sheet(item: $app.pendingFileApproval) { req in
            FileApprovalView(req: req)
                .environmentObject(app)
        }
        // ── 4-layer architecture setup: review then approve ──────────────────
        .sheet(item: $app.pendingSetupProposal) { proposal in
            TemplateSetupApprovalSheet(proposal: proposal)
                .environmentObject(app)
        }
        // ── Vera-α layer: save-preview approval sheet ────────────────────────
        // Suppressed while the stereo-cross graph demo is active -- the
        // same request is shown as an inline card in AgentChatView instead
        // (see veraSaveInlineCard there), so it doesn't cover the graph.
        .sheet(item: Binding<VeraSaveApprovalRequest?>(
            get: { app.showStereoCrossGraph ? nil : app.pendingVeraSave },
            set: { app.pendingVeraSave = $0 }
        )) { req in
            VeraSaveApprovalView(req: req)
                .environmentObject(app)
        }
    } // end body


    // `humanModeLayout` lived here: the 4-pane IDE with the 48pt activity
    // rail. It had no call sites — this view has rendered
    // HumanPriorityModeView unconditionally for a long time — but it still
    // carried working routes into the docked MCP / Vera / growth panes, so
    // a stray notification could open a screen out of a layout nobody
    // mounts. Deleted rather than left as a trap.

    // MARK: - Human Mode: approval banner

    private func humanApprovalBanner(diff: FileDiff) -> some View {
        HStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(Theme.warn)
                .font(.system(size: 13))

            VStack(alignment: .leading, spacing: 2) {
                Text(app.t("Pending approval: ", "承認待ち: ") + diff.fileURL.lastPathComponent)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Color(red: 0.95, green: 0.88, blue: 0.60))
                Text(app.t("AI has proposed changes. Review in the Diff tab.", "AIが変更を提案しています。Diffタブで内容を確認してください。"))
                    .font(.system(size: 11))
                    .foregroundStyle(Theme.dim)
            }

            Spacer()

            // Quick Reject
            Button {
                app.pendingDiff = nil
                app.showDiff    = false
                app.addSystemMessage("↩️ " + app.t("Change rejected", "変更を却下しました"))
            } label: {
                Text(app.t("Reject", "却下"))
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Theme.bad)
                    .padding(.horizontal, 16).padding(.vertical, 5)
                    .background(Color(red: 0.35, green: 0.12, blue: 0.12).opacity(0.6),
                                in: RoundedRectangle(cornerRadius: 6))
                    .overlay(RoundedRectangle(cornerRadius: 6)
                        .stroke(Theme.bad.opacity(0.5), lineWidth: 1))
            }
            .contentShape(Rectangle())
            .buttonStyle(.plain)

            // Quick Approve
            Button {
                do {
                    try diff.modifiedContent.write(to: diff.fileURL, atomically: true, encoding: .utf8)
                    app.selectedFileContent = diff.modifiedContent
                    app.pendingDiff = nil
                    app.showDiff    = false
                    app.addSystemMessage("✅ " + app.t("Change approved & applied: ", "変更を承認・適用しました: ") + diff.fileURL.lastPathComponent)
                } catch {
                    app.addSystemMessage("❌ " + app.t("Write failed: ", "書き込み失敗: ") + error.localizedDescription)
                }
            } label: {
                Text(app.t("Approve", "承認"))
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Theme.ok)
                    .padding(.horizontal, 16).padding(.vertical, 5)
                    .background(Color(red: 0.12, green: 0.30, blue: 0.18).opacity(0.7),
                                in: RoundedRectangle(cornerRadius: 6))
                    .overlay(RoundedRectangle(cornerRadius: 6)
                        .stroke(Theme.ok.opacity(0.5), lineWidth: 1))
            }
            .contentShape(Rectangle())
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
        .background(Color(red: 0.16, green: 0.14, blue: 0.08))
        .overlay(Rectangle().fill(Theme.warn.opacity(0.3)).frame(height: 1),
                 alignment: .top)
        .transition(.move(edge: .bottom).combined(with: .opacity))
        .animation(.easeInOut(duration: 0.2), value: app.pendingDiff != nil)
    }

    // MARK: - Toolbar

    @ToolbarContentBuilder
    /// ウィンドウ上部の道具は置かない。
    ///
    /// 「フォルダーを開く」と「ターミナル切替」はここにあったが、服飾の
    /// 作業面には要らないものが常に見えている状態だった。どちらも他から
    /// 届く(ワークスペースは左のツリー、ターミナルは ⌘⇧L)ので、
    /// **窓の上を空けて作業面を広く取る**。
    private var toolbarContent: some ToolbarContent {
        ToolbarItem(placement: .navigation) { EmptyView() }
    }

    private var shortModelLabel: String {
        switch app.modelStatus {
        case .ollamaReady(let m):   return m.components(separatedBy: ":").first ?? m
        case .mlxReady(let m):      return "MLX:" + (m.components(separatedBy: "/").last ?? m)
        case .bitnetReady(let m):   return "⚡" + m.components(separatedBy: "-").prefix(3).joined(separator: "-")
        case .connecting:            return "connecting…"
        case .error:                 return "error"
        default:                     return "no model"
        }
    }
}

// MARK: - FileApprovalView
// A polished modal that shows what the AI wants to write.
// Suspends AgentLoop via CheckedContinuation until user decides.

struct FileApprovalView: View {
    @EnvironmentObject var app: AppState
    let req: FileApprovalRequest

    var body: some View {
        VStack(spacing: 0) {

            // ─ Header ───────────────────────────────────────────────────
            HStack(spacing: 12) {
                // Operation icon
                ZStack {
                    RoundedRectangle(cornerRadius: 8)
                        .fill(req.isNewFile
                              ? Theme.sel.opacity(0.18)
                              : Theme.warn.opacity(0.18))
                        .frame(width: 40, height: 40)
                    Image(systemName: req.isNewFile ? "doc.badge.plus" : "pencil.line")
                        .font(.system(size: 18))
                        .foregroundStyle(req.isNewFile
                                         ? Theme.sel
                                         : Theme.warn)
                }

                VStack(alignment: .leading, spacing: 3) {
                    Text(req.displayTitle)
                        .font(.system(size: 14, weight: .bold))
                        .foregroundStyle(Theme.fg)
                    Text(req.shortPath)
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(Theme.sel)
                        .lineLimit(1)
                }

                Spacer()

                // 小さいベッジ
                Text(req.isNewFile ? "NEW" : "EDIT")
                    .font(.system(size: 9, weight: .bold, design: .monospaced))
                    .foregroundStyle(req.isNewFile
                                     ? Theme.ok
                                     : Theme.warn)
                    .padding(.horizontal, 7).padding(.vertical, 3)
                    .background(
                        Capsule()
                            .fill(req.isNewFile
                                  ? Theme.ok.opacity(0.15)
                                  : Theme.warn.opacity(0.15))
                            .overlay(Capsule()
                                .stroke(req.isNewFile
                                        ? Theme.ok.opacity(0.4)
                                        : Theme.warn.opacity(0.4),
                                        lineWidth: 0.8))
                    )
            }
            .padding(.horizontal, 20)
            .padding(.top, 20)
            .padding(.bottom, 14)

            Divider().opacity(0.25)

            // ─ Content diff ──────────────────────────────────────────────
            ScrollView([.vertical, .horizontal]) {
                VStack(alignment: .leading, spacing: 0) {
                    if req.isNewFile {
                        // New file — show full content with green "+" markers
                        ForEach(Array(req.newContent.components(separatedBy: "\n").enumerated()), id: \.offset) { i, line in
                            approvalDiffLine("+", text: "  " + line,
                                            bg: Color(red: 0.1, green: 0.3, blue: 0.15).opacity(0.6),
                                            fg: Theme.ok)
                        }
                    } else {
                        // Existing file — minimal unified diff (context ±3 lines)
                        let diffLines = buildUnifiedDiff(original: req.originalContent,
                                                         modified: req.newContent)
                        ForEach(Array(diffLines.enumerated()), id: \.offset) { _, entry in
                            approvalDiffLine(entry.marker, text: entry.text,
                                            bg: entry.bg, fg: entry.fg)
                        }
                    }
                }
                .padding(.vertical, 8)
                .padding(.horizontal, 4)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .background(Theme.bg)
            .frame(maxHeight: .infinity)

            Divider().opacity(0.25)

            // ─ Action buttons ───────────────────────────────────────────
            HStack(spacing: 12) {
                Spacer()

                // Reject
                Button {
                    app.rejectFileWrite()
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: "xmark")
                            .font(.system(size: 11, weight: .semibold))
                        Text(app.t("Cancel", "キャンセル"))
                            .font(.system(size: 13, weight: .semibold))
                    }
                    .foregroundStyle(Theme.bad)
                    .padding(.horizontal, 20).padding(.vertical, 9)
                    .contentShape(Rectangle())
                    .background(Color(red: 0.32, green: 0.10, blue: 0.10).opacity(0.7),
                                in: RoundedRectangle(cornerRadius: 8))
                    .overlay(RoundedRectangle(cornerRadius: 8)
                        .stroke(Theme.bad.opacity(0.5), lineWidth: 1))
                }
                .contentShape(Rectangle())
                .buttonStyle(.plain)
                .keyboardShortcut(.escape)

                // Approve
                Button {
                    app.approveFileWrite()
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: "checkmark")
                            .font(.system(size: 11, weight: .semibold))
                        Text(app.t("Approve & Apply", "承認して適用"))
                            .font(.system(size: 13, weight: .semibold))
                    }
                    .foregroundStyle(Theme.ok)
                    .padding(.horizontal, 20).padding(.vertical, 9)
                    .contentShape(Rectangle())
                    .background(Color(red: 0.10, green: 0.28, blue: 0.15).opacity(0.8),
                                in: RoundedRectangle(cornerRadius: 8))
                    .overlay(RoundedRectangle(cornerRadius: 8)
                        .stroke(Theme.ok.opacity(0.5), lineWidth: 1))
                }
                .contentShape(Rectangle())
                .buttonStyle(.plain)
                .keyboardShortcut(.return, modifiers: .command)
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 14)
            .background(Theme.panel2)
        }
        .background(Theme.panel)
        .frame(minWidth: 640, idealWidth: 760, maxWidth: 960,
               minHeight: 420, idealHeight: 560, maxHeight: 720)
    }

    // MARK: - Diff line helper

    private struct DiffEntry {
        let marker: String
        let text: String
        let bg: Color
        let fg: Color
    }

    @ViewBuilder
    private func approvalDiffLine(_ marker: String, text: String, bg: Color, fg: Color) -> some View {
        HStack(spacing: 0) {
            Text(marker)
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(fg)
                .frame(width: 18, alignment: .center)
            Text(text)
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(marker == " " ? Theme.sel : fg)
                .lineLimit(1)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.vertical, 1)
        .background(bg)
    }

    /// Build a lightweight unified diff (context ±3 lines) without Foundation Diff.
    private func buildUnifiedDiff(original: String, modified: String) -> [DiffEntry] {
        let oLines = original.components(separatedBy: "\n")
        let mLines = modified.components(separatedBy: "\n")
        var entries: [DiffEntry] = []

        // 簡易LCS：行単位で差分を計算
        var oIdx = 0, mIdx = 0
        while oIdx < oLines.count || mIdx < mLines.count {
            let ol = oIdx < oLines.count ? oLines[oIdx] : nil
            let ml = mIdx < mLines.count ? mLines[mIdx] : nil

            if ol == ml {
                entries.append(DiffEntry(marker: " ", text: "  " + (ol ?? ""),
                                         bg: .clear, fg: .secondary))
                oIdx += 1; mIdx += 1
            } else {
                if let ol { // removed
                    entries.append(DiffEntry(marker: "-", text: "  " + ol,
                                             bg: Color(red: 0.35, green: 0.08, blue: 0.08).opacity(0.5),
                                             fg: Theme.bad))
                    oIdx += 1
                }
                if let ml { // added
                    entries.append(DiffEntry(marker: "+", text: "  " + ml,
                                             bg: Color(red: 0.08, green: 0.28, blue: 0.12).opacity(0.5),
                                             fg: Theme.ok))
                    mIdx += 1
                }
            }
        }
        return entries
    }
}
