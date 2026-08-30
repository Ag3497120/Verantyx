import SwiftUI

// MARK: - AgentChatView
// Center panel: "Vibe Coding Workspace" + "Thinking Log" tabs
// Shows AntigravityAgent with <think> rendering in teal

struct AgentChatView: View {
    @EnvironmentObject var app: AppState
    @ObservedObject private var garmentJob = GarmentGenerationJob.shared
    @ObservedObject private var garmentFactory = GarmentFactoryReactController.shared
    @State private var showingHistory: Bool = false
    @State private var showingModelPill = false

    /// The pinned composer that used to end this view's body is gone —
    /// moved to `UnifiedComposerView`, which IDEShellView now positions
    /// itself (below whatever tab is open, or alone in the empty state).
    /// The two remaining callers that still want a self-contained chat
    /// pane (SwarmMonitorView's side-by-side agents; the dormant
    /// AIModeLayoutView) pass `true` here so they keep a composer of
    /// their own — the SAME implementation, not a second one.
    var showsOwnComposer: Bool = true

    @State private var showVisualAnchorPrompt: Bool = false
    @State private var visualAnchorText: String = ""
    @State private var showSpotlightPrompt: Bool = false
    /// Milestone H: the lock-icon anchor popover used to be two separate
    /// buttons/popovers (lock = "Visual Anchor" / red "CRITICAL DIRECTIVE"
    /// framing, wand = "Agent Instruction" / gray "USER INSTRUCTION"
    /// framing) that both rendered text into a PNG via the same
    /// `CognitiveAnchorEngine` pipeline and attached it to
    /// `app.attachedImages` -- functionally identical except for framing.
    /// Consolidated into one popover with this style picker; both
    /// "Set Persistent" and "Inject Once" apply to whichever style is
    /// selected.
    private enum AnchorFramingStyle: String, CaseIterable, Identifiable {
        case criticalDirective, userInstruction
        var id: String { rawValue }
    }
    @State private var anchorFramingStyle: AnchorFramingStyle = .criticalDirective

    @State private var showVerifiedURLPrompt: Bool = false
    @State private var verifiedURLName: String = ""
    @State private var verifiedURLValue: String = ""
    @State private var verifiedURLStatus: String = ""

    var body: some View {
        VStack(spacing: 0) {
            // ── Tab bar ─────────────────────────────────────────────
            tabBar

            Divider().opacity(0.3)

            // ── Content ─────────────────────────────────────────────
            ZStack {
                // Vera mode used to replace the TRANSCRIPT with
                // VeraConsolePane's stacked ANSWER/GAP sections — no
                // turn-by-turn history, because that view reads
                // VeraRouteState directly and never looks at
                // app.messages. Turned out to read as "vera mode has no
                // history" (user report, 2026-08-19): the question WAS
                // being recorded (sendMessage appends role:.user for
                // every mode before branching), the console pane just
                // never showed it. Requested to look like Vera-a's
                // You/Verantyx history instead — chatTranscriptArea
                // already renders app.messages turn by turn and needs
                // no Vera-specific handling, since Vera's replies are
                // already plain ChatMessage(role:.assistant, content:)
                // like every other mode.
                // Every mode gets the same screen: the main area filled
                // by whatever this mode actually answers with. Only two
                // modes remain (2026-08-26 — Vera単体 and Veraぼっと were
                // removed, see AppState.VeraEngineMode), so this is now a
                // straight either/or rather than a three-way branch: the
                // garment workbench, or the ordinary transcript.
                // **服飾の作業面はここでは描かない。** かつてこの画面が唯一の
                // 面だった頃の名残で、atelier モードのとき AtelierView を出して
                // いた。いまはシェルの服飾タブが同じものを描くので、チャットの
                // タブを開いていると AtelierView が二つ生き、互いの領域に食い
                // 込んで画面が崩れた（レール連打で再現）。**同じ物を二箇所で
                // 描かない。** 会話の画面は会話だけを持つ。
                VeraSovereignLayout {
                    HStack(spacing: 0) {
                        chatTranscriptArea
                            .frame(minWidth: resolutionRequest == nil ? 560 : 620)
                            .layoutPriority(1)
                        if let request = resolutionRequest {
                            Divider().opacity(0.35)
                            GarmentResolutionSidebarView(request: request)
                                .environmentObject(app)
                                .frame(width: 336)
                                .transition(.move(edge: .trailing).combined(with: .opacity))
                        }
                    }
                    // The sidebar keeps a stable reading width. Below this
                    // minimum the app window stops shrinking instead of
                    // reflowing controls into an unusable stack.
                    .frame(minWidth: resolutionRequest == nil ? 560 : 956,
                           maxWidth: .infinity, maxHeight: .infinity)
                }
                .environmentObject(app)
                    .opacity(showingHistory ? 0 : 1)
                    .offset(x: showingHistory ? 20 : 0)
                
                if showingHistory {
                    SessionHistoryView()
                        .environmentObject(app)
                        .opacity(showingHistory ? 1 : 0)
                        .offset(x: showingHistory ? 0 : -20)
                        .transition(.move(edge: .leading).combined(with: .opacity))
                }
            }
            .animation(.spring(response: 0.4, dampingFraction: 0.8), value: showingHistory)

            Divider().opacity(0.3)

            // ── Puzzle Overlay ───────────────────────────────────────
            if app.requiresHumanPuzzle {
                HumanProofPuzzleView { entropy, duration, frames in
                    print("Puzzle solved in \(duration)s with \(entropy.count) entropy points.")
                    app.lastEntropy = entropy
                    app.lastVideoFrames = frames
                    app.lastEntropyTimestamp = Date()

                    // The person just drove a real trajectory. It used to be
                    // spent on one search and discarded; now it also lands in
                    // vera-a as a demonstration, and the motion model prefers
                    // demonstrations over the agent's own synthetic paths —
                    // imitating itself would only compound its own error.
                    let pts = entropy.map { (x: Double($0.x), y: Double($0.y)) }
                    let screen = NSScreen.main?.frame.size ?? .zero
                    Task {
                        await EternalMemoryStore.shared.recordHumanDemonstration(
                            points: pts,
                            screenW: Double(screen.width), screenH: Double(screen.height))
                    }
                    // Hide puzzle after solve
                    app.requiresHumanPuzzle = false
                    
                    // Proceed with background botguard bypass using this entropy
                    // ... (send entropy to backend via AppState logic if needed)
                }
                .padding()
            }
            
            // ── Input ────────────────────────────────────────────────
            // IDEShellView mounts UnifiedComposerView itself for the main
            // shell (below the active tab, or alone in the empty state) —
            // this only renders here for the two embeds that still want a
            // self-contained pane.
            if showsOwnComposer {
                inputBar
            }
        }
        .overlay(
            Group {
                if app.isAgentControllingMouse {
                    ZStack {
                        // Semi-transparent black background
                        Color.black.opacity(0.85)
                            .edgesIgnoringSafeArea(.all)
                        
                        VStack(spacing: 20) {
                            ProgressView()
                                .progressViewStyle(CircularProgressViewStyle(tint: Color(red: 0.0, green: 1.0, blue: 0.8)))
                                .scaleEffect(2.0)
                            
                            Text(AppLanguage.shared.t("🧩 Injecting biometric trajectory...", "🧩 生体データを注入中... (Injecting trajectory...)"))
                                .font(.system(size: 24, weight: .bold, design: .monospaced))
                                .foregroundColor(Color(red: 0.0, green: 1.0, blue: 0.8))
                                .shadow(color: Color(red: 0.0, green: 1.0, blue: 0.8).opacity(0.5), radius: 10, x: 0, y: 0)
                            
                            Text(AppLanguage.shared.t("Physical mouse input temporarily blocked", "物理的なマウス入力を一時的に遮断しています"))
                                .font(.system(size: 14, weight: .medium))
                                .foregroundColor(.gray)
                        }
                    }
                    .transition(.opacity)
                    .animation(.easeInOut(duration: 0.3), value: app.isAgentControllingMouse)
                }
            }
        )
        .background(Theme.panel2)
        // ─ Sync state with AppState (for session restore programmatic switch) ─
        .onChange(of: app.activeChatTab) { _, newVal in
            withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
                showingHistory = (newVal == 1)
            }
        }
        .onChange(of: showingHistory) { _, isHistory in
            let idx = isHistory ? 1 : 0
            if app.activeChatTab != idx { app.activeChatTab = idx }
        }
        .onChange(of: app.sessions.activeSessionId) { _, _ in
            // When a session is selected from history, automatically switch back to chat view
            if showingHistory {
                withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
                    showingHistory = false
                }
            }
        }
        .onChange(of: app.activeGarment) { _, name in
            // Every project change goes through the canonical activation
            // boundary. Normal picker changes have already activated the job;
            // this guard catches only restored/legacy direct assignments.
            if garmentJob.activeResolutionProject != name {
                app.activateGarmentProject(name)
            }
        }
        .onReceive(garmentFactory.$pendingResolutionRequest) { request in
            // This typed publisher is authoritative. Do not reconstruct its
            // missing fields, options, digest or terminal state from prose.
            garmentJob.ingestResolutionEnvelope(request.map {
                GarmentResolutionRequest(factoryRequest: $0)
            })
        }
        .onReceive(garmentFactory.$lastReport) { report in
            // Compatibility adapter for factory paths that have not yet
            // published GarmentResolutionRequest directly.
            guard garmentFactory.pendingResolutionRequest == nil,
                  let report else { return }
            garmentJob.registerResolution(
                code: report.verdict, stage: report.phase,
                explanation: report.message,
                provenanceDigest: nil,
                authority: "UNOBSERVED")
        }
        .onAppear {
            if garmentJob.activeResolutionProject != app.activeGarment {
                app.activateGarmentProject(app.activeGarment)
            }
            if let pending = garmentFactory.pendingResolutionRequest {
                garmentJob.ingestResolutionEnvelope(
                    GarmentResolutionRequest(factoryRequest: pending))
            } else if let report = garmentFactory.lastReport {
                garmentJob.registerResolution(
                    code: report.verdict, stage: report.phase,
                    explanation: report.message,
                    provenanceDigest: nil,
                    authority: "UNOBSERVED")
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: NSNotification.Name("ChatTranscriptClicked"))) { _ in
            // Only offer the Spotlight panel when a Control x3 conversation
            // actually exists in the background — a plain click (or a copy
            // press) in a normal chat used to raise this alert every time.
            if !SpotlightPanelManager.shared.isPresented,
               app.messages.contains(where: { $0.isSpotlight }) {
                showSpotlightPrompt = true
            }
        }
        .alert(app.t("Open Spotlight Agent?", "Spotlightエージェントを起動しますか？"), isPresented: $showSpotlightPrompt) {
            Button(app.t("Open (Control x3)", "起動する (Control x3)")) {
                SpotlightPanelManager.shared.show()
            }
            Button(app.t("Cancel", "キャンセル"), role: .cancel) {}
        } message: {
            Text(app.t(
                "The Control x3 agent is currently running in the background. Would you like to open the Spotlight panel to continue?",
                "現在、Control x3 のエージェントがバックグラウンドで待機しています。Spotlightエージェントを起動してチャットを継続しますか？"
            ))
        }
    }

    private var resolutionRequest: GarmentResolutionRequest? {
        guard app.veraEngineMode == .atelier else { return nil }
        return garmentJob.activeResolutionRequest
    }

    // MARK: - Top Chat Button

    private var tabBar: some View {
        HStack {
            Spacer()
            if app.veraEngineMode == .atelier {
                // **服飾の面では、中央は服を選ぶところ。**
                // 会話の履歴より、いま何を作っているかの方が上位。
                garmentPicker
            } else {
            Button {
                withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
                    showingHistory.toggle()
                }
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: "bubble.left.and.bubble.right.fill")
                        .font(.system(size: 11))
                        .foregroundStyle(Theme.sel)
                    Text(app.t("Chat", "チャット"))
                        .font(.system(size: 13, weight: .bold))
                        .foregroundStyle(Color.white)
                    Image(systemName: "chevron.down")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(Color.white.opacity(0.6))
                        .rotationEffect(.degrees(showingHistory ? 180 : 0))
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 8)
                .background(
                    Capsule()
                        .fill(Color(red: 0.2, green: 0.2, blue: 0.25))
                        .overlay(
                            Capsule().stroke(Color.white.opacity(0.1), lineWidth: 1)
                        )
                )
            }
            .buttonStyle(.plain)
            }
            Spacer()
        }
        .padding(.vertical, 5)
        .background(Theme.panel2)
        .overlay(alignment: .leading) {
            veraModeControls.padding(.leading, 12)
        }
        .overlay(alignment: .trailing) {
            overflowMenu.padding(.trailing, 12)
        }
    }

    // MARK: - どの服を見ているか

    /// 服の選択。**以前のチャット選択欄をここに転用した。**
    ///
    /// 会話の切替より、いま何を作っているかの方が、この道具では上位に
    /// あります。複数の服を持つときはここで替えます。
    private var garmentPicker: some View {
        HStack(spacing: 8) {
            Image(systemName: "square.on.square")
                .font(.system(size: 11))
                .foregroundStyle(Theme.sel)
            Menu {
                ForEach(app.garmentProjects, id: \.self) { name in
                    Button {
                        // Project selection is an engine operation, not just a
                        // label change.  Keep the Python ledger namespace and
                        // the visible project in lockstep whichever picker the
                        // user uses (sidebar or chat header).
                        app.activateGarmentProject(name)
                    } label: {
                        if name == app.activeGarment {
                            Label(name, systemImage: "checkmark")
                        } else {
                            Text(name)
                        }
                    }
                }
                Divider()
                Button(app.t("New garment…", "新しい服…")) {
                    app.newGarmentProject()
                }
                Button(app.t("Chat history", "会話の履歴")) {
                    withAnimation(.spring(response: 0.4,
                                          dampingFraction: 0.8)) {
                        showingHistory.toggle()
                    }
                }
            } label: {
                HStack(spacing: 6) {
                    Text(app.activeGarment)
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(.white)
                    Image(systemName: "chevron.down")
                        .font(.system(size: 9, weight: .bold))
                        .foregroundStyle(.white.opacity(0.55))
                }
            }
            .menuStyle(.borderlessButton)
            .fixedSize()
        }
        .padding(.horizontal, 12).padding(.vertical, 4)
        .background(
            Capsule().fill(Color(red: 0.2, green: 0.2, blue: 0.25))
                .overlay(Capsule().stroke(Color.white.opacity(0.1),
                                          lineWidth: 1)))
    }

    // MARK: - Which engine answers
    //
    // Moved here from the band above, which existed only to hold it. It
    // stays visible rather than becoming a summon, because the mode
    // decides what KIND of answer the next reply is — a typed verdict or
    // an LLM's prose — and that is not a setting, it is the label on what
    // you are reading.
    private var veraModeControls: some View {
        HStack(spacing: 6) {
            // **この道具は服飾のものなので、モード選択は小さく畳む。**
            // 4モードだったうちの Vera単体・Veraぼっと は 2026-08-26 に
            // 削除(owner指示 — 「モードは2つだけ」)。旧「版の切替」
            // ピッカー(veraModelVersions/selectVeraModelVersion)も
            // Vera単体でだけ出ていたので、モードと一緒に消えた。
            Picker("", selection: Binding(
                get: { app.veraEngineMode },
                set: { app.selectEngineMode($0) })) {
                Text("Atelier").tag(AppState.VeraEngineMode.atelier)
                Text("LLM").tag(AppState.VeraEngineMode.localLLM)
            }
            .pickerStyle(.menu)
            .labelsHidden()
            .frame(width: 92)
            .controlSize(.small)
            .font(.system(size: 10))
            .help(app.t(
                "Atelier is the garment workbench. LLM is just a model, "
                + "with nothing in front of it.",
                "Atelier は服飾の作業面。LLM は素のモデル。"))

            // Progress only: these two used to be buttons that started long
            // jobs. The words 「マップ」「パイプライン」 start them now; what
            // is left here is the part worth watching.
            IsolatedL25HeaderButton(progressOnly: true)
            IsolatedPipelineHeaderButton(showPipelineSheet: .constant(false),
                                         progressOnly: true)
        }
    }

    // MARK: - Overflow ("...") menu

    private var overflowMenu: some View {
        Menu {
            Button {
                copyAllConversation()
            } label: {
                Label(app.t("Copy all conversation", "会話履歴を全てコピー"),
                      systemImage: "doc.on.doc")
            }
        } label: {
            Image(systemName: "ellipsis.circle")
                .font(.system(size: 15))
                .foregroundStyle(Color.white.opacity(0.65))
                .frame(width: 24, height: 24)
        }
        .menuStyle(.borderlessButton)
        .fixedSize()
        .help(app.t("More options", "その他のオプション"))
    }

    private func copyAllConversation() {
        let text = app.messages
            .filter { !$0.isSpotlight }
            .map { msg -> String in
                let roleLabel: String
                switch msg.role {
                case .user:      roleLabel = "User"
                case .assistant: roleLabel = "VerantyxAgent"
                case .system:    roleLabel = "System"
                }
                return "[\(roleLabel)] \(msg.content)"
            }
            .joined(separator: "\n\n")
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
    }

    // MARK: - Workspace (main chat)

    /// The transcript with tool/system logs folded away when the user has
    /// collapsed them. Replies are never hidden — only the running commentary.
    private var visibleMessages: [ChatMessage] {
        app.messages.filter {
            !$0.isSpotlight && (app.showSystemLogs || $0.role != .system)
        }
    }

    private var hiddenLogCount: Int {
        app.showSystemLogs ? 0 : app.messages.filter { !$0.isSpotlight && $0.role == .system }.count
    }

    /// A disclosure arrow over the transcript: collapse the log chatter and
    /// read only the answers, or open it back up. Sits at the top-right so it
    /// never covers the newest message.
    private var logToggleChip: some View {
        VStack {
            HStack {
                // ── 立体十字ルーティング ─────────────────────────
                // The route the answer took, over the transcript it
                // arrived in. Still when nothing is asked; lit by the
                // real call when one is. It reports and never decides —
                // no gate reads this, exactly like the grain band.
                Spacer()
                Button {
                    withAnimation(.easeInOut(duration: 0.15)) {
                        app.showSystemLogs.toggle()
                    }
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: app.showSystemLogs ? "chevron.down" : "chevron.right")
                            .font(.system(size: 9, weight: .bold))
                        Text(app.showSystemLogs
                             ? AppLanguage.shared.t("logs", "ログ")
                             : AppLanguage.shared.t("logs (\(hiddenLogCount))", "ログ \(hiddenLogCount)件"))
                            .font(.system(size: 10, weight: .medium))
                    }
                    .foregroundStyle(app.showSystemLogs ? .secondary : .tertiary)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(Color.white.opacity(0.06), in: Capsule())
                    .overlay(Capsule().strokeBorder(Color.white.opacity(0.10), lineWidth: 0.5))
                }
                .buttonStyle(.plain)
                .contentShape(Capsule())
                .help(AppLanguage.shared.t("Show or hide tool and system logs",
                                           "ツール・システムログの表示を切り替え"))
                .padding(.trailing, 14)
                .padding(.top, 10)
            }
            Spacer()
        }
    }

    private var chatTranscriptArea: some View {
        ZStack(alignment: .bottom) {
            VStack(spacing: 0) {
                // NSTextView ベースのトランスクリプト。
                // 単一テキストストレージのためメッセージをまたいでドラッグ選択・コピーができる。
                ChatTranscriptView(messages: visibleMessages,
                                   isGenerating: app.isGenerating)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .layoutPriority(1)

                // 必要な候補・3D・型紙・監査内容は、会話を覆う別ウィンドウでは
                // なく、トランスクリプトの末尾に選択式カードとして差し込む。
                // 展開しても通常レイアウト内で高さを使うため、本文も入力欄も
                // 隠さない。同じ factory/job/context を使うので状態の複製もない。
                if app.veraEngineMode == .atelier {
                    AtelierBeginnerContextCardsView()
                        .environmentObject(app)
                }
            }

            logToggleChip

            // LiveTerminalView used to pop up here inline on every generating
            // turn. Removed -- actual command output already routes to
            // app.terminal (AppState's .toolCall/.toolResult handling),
            // which feeds the real TerminalPanelView/StatusBarView below
            // the file editor. No need to show it a second time in chat.

            // Vera-α save approval, shown here instead of a center-screen
            // sheet only while the stereo-cross graph demo is active (see
            // MainSplitView/VerantyxApp's suppressed .sheet(item:)) -- so
            // approving/discarding doesn't cover the 3D structure.
            if app.showStereoCrossGraph, let req = app.pendingVeraSave {
                veraSaveInlineCard(req)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                    .animation(.spring(response: 0.35, dampingFraction: 0.85), value: app.pendingVeraSave?.id)
            }
        }
    }

    @ViewBuilder
    private func veraSaveInlineCard(_ req: VeraSaveApprovalRequest) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Image(systemName: "checkmark.seal")
                    .font(.system(size: 12))
                    .foregroundStyle(Theme.ok)
                Text(app.t("Save this turn to Vera?", "この内容を Vera に保存しますか？"))
                    .font(.system(size: 12, weight: .bold))
                    .foregroundStyle(Theme.fg)
                Spacer()
            }

            if !req.userPrompt.isEmpty {
                Text(req.userPrompt)
                    .font(.system(size: 11))
                    .foregroundStyle(Color(red: 0.7, green: 0.8, blue: 1.0))
                    .lineLimit(2)
            }
            if !req.aiResponse.isEmpty {
                Text(req.aiResponse)
                    .font(.system(size: 11))
                    .foregroundStyle(Color(red: 0.75, green: 0.75, blue: 0.82))
                    .lineLimit(2)
            }

            HStack(spacing: 10) {
                Spacer()
                Button {
                    app.rejectVeraSave()
                } label: {
                    Text(app.t("Discard", "破棄")).font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(Theme.bad)
                        .padding(.horizontal, 12).padding(.vertical, 5)
                        .background(Capsule().fill(Color(red: 0.32, green: 0.1, blue: 0.1).opacity(0.7)))
                }
                .buttonStyle(.plain)

                Button {
                    app.approveVeraSave()
                } label: {
                    Text(app.t("Save", "保存")).font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(Theme.ok)
                        .padding(.horizontal, 12).padding(.vertical, 5)
                        .background(Capsule().fill(Color(red: 0.1, green: 0.28, blue: 0.15).opacity(0.8)))
                }
                .buttonStyle(.plain)
            }
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(Theme.panel2)
                .overlay(RoundedRectangle(cornerRadius: 10).stroke(Theme.ok.opacity(0.35), lineWidth: 1))
        )
        .shadow(color: .black.opacity(0.4), radius: 8, y: 2)
        .padding(.horizontal, 14)
        .padding(.bottom, 10)
    }


    // MARK: - Input bar
    //
    // `modelSelectorBar` moved to UnifiedComposerView.swift along with the
    // rest of the composer — see that file for the model-hidden-in-Vera/
    // Atelier-modes reasoning, which still applies unchanged.

    /// Box + chrome. The tools, the model and the send action sit BELOW the
    /// text box rather than inside it: inside, they competed with the text for
    /// the same row and won, and every one of them stole width the text needed.
    /// A compact model pill, not a bar.
    ///
    /// The bar it replaces carried a label, a picker, a layers button, an
    /// auditor toggle, an error badge and a mode stepper — six controls on a
    /// permanent row above the text. The picker is the only one someone reaches
    /// for while writing; the rest are settings, and settings are summoned now.
    private var modelPill: some View {
        // A Button with a popover rather than a Menu: Menu draws its own
        // indicator wherever its style decides, and on screen that landed to
        // the LEFT of the label — an arrow pointing away from the thing it
        // opens.
        Button { showingModelPill.toggle() } label: {
            HStack(spacing: 4) {
                Text(app.activeModelName ?? AppLanguage.shared.t("no model", "未読込"))
                    .font(.system(size: 11.5))
                    .lineLimit(1)
                Image(systemName: "chevron.down").font(.system(size: 8, weight: .semibold))
            }
            .foregroundStyle(.secondary)
            .padding(.horizontal, 9).padding(.vertical, 4)
            .background(Capsule().fill(Color.white.opacity(0.07)))
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .popover(isPresented: $showingModelPill, arrowEdge: .top) {
            VStack(alignment: .leading, spacing: 2) {
                if app.ollamaModels.isEmpty {
                    Text(AppLanguage.shared.t("No local model is reachable.",
                                              "到達できるローカルモデルがありません。"))
                        .font(.system(size: 11)).foregroundStyle(.secondary)
                        .padding(8)
                } else {
                    ForEach(app.ollamaModels, id: \.self) { name in
                        Button {
                            app.modelStatus = .ollamaReady(model: name)
                            showingModelPill = false
                        } label: {
                            Text(name).font(.system(size: 12, design: .monospaced))
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(.horizontal, 9).padding(.vertical, 5)
                                .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            .padding(5)
            .frame(minWidth: 190)
        }
    }

    /// The composer itself — text, attach, model, send — now lives in
    /// `UnifiedComposerView`, shared with IDEShellView so there is exactly
    /// one implementation instead of the pinned one this file used to carry
    /// plus the `composerTools` variant below that never had a call site.
    /// This wrapper is what keeps `showsOwnComposer` call sites working.
    private var inputBar: some View {
        UnifiedComposerView()
            .environmentObject(app)
    }

    /// The composer's tools, OUTSIDE the text box.
    ///
    /// They used to sit in the same row as the text, held to `width: 142` so a
    /// mode toggle could not shift the field sideways. The icons need about
    /// 190, so they always overflowed that clamp — invisibly, because the box
    /// was tall enough that they sat at the bottom while the placeholder sat at
    /// the top. The moment the composer collapsed to one line they landed on
    /// the same line and the placeholder ran underneath them.
    ///
    /// Below the box there is no clamp to overflow and nothing to collide with,
    /// and the text field gets the full width — which is what the box is for.
    @ViewBuilder
    private var composerTools: some View {
        // ── Fixed-width action button group ──────────────────────
        // IMPORTANT: fixed frame prevents Self Fix toggle from
        // shifting the TextEditor to the right
        HStack(spacing: 2) {
            // Attach image
            Button {
                let picked = AttachmentManager.pickImages()
                app.attachedImages.append(contentsOf: picked)
            } label: {
                Image(systemName: "photo.badge.plus")
                    .font(.system(size: 15))
                    .foregroundStyle(
                        app.isMultimodalModel
                        ? Color(red: 0.6, green: 0.8, blue: 1.0)
                        : Color(red: 0.35, green: 0.35, blue: 0.45)
                    )
                    .frame(width: 26, height: 26)
            }
            .contentShape(Rectangle())
            .buttonStyle(.plain)
            .disabled(!app.isMultimodalModel)
            .help(app.isMultimodalModel ? app.t("Attach image", "画像を添付") : app.t("Multimodal not supported by this model", "このモデルはマルチモーダル非対応です"))

            // Attach file
            Button {
                let picked = AttachmentManager.pickFiles()
                app.attachedFiles.append(contentsOf: picked)
            } label: {
                Image(systemName: "paperclip")
                    .font(.system(size: 15))
                    .foregroundStyle(Color(red: 0.6, green: 0.7, blue: 0.85))
                    .frame(width: 26, height: 26)
            }
            .contentShape(Rectangle())
            .buttonStyle(.plain)
            .help(app.t("Attach file", "ファイルを添付"))
            
            // ── Visual Anchor Insertion ──
            Button {
                showVisualAnchorPrompt = true
            } label: {
                ZStack(alignment: .topTrailing) {
                    Image(systemName: "exclamationmark.lock.fill")
                        .font(.system(size: 15))
                        .foregroundStyle(app.persistentTaskAnchor.isEmpty ? Theme.bad : Color.orange)
                        .frame(width: 26, height: 26)
                    
                    if !app.persistentTaskAnchor.isEmpty {
                        Circle().fill(Color.orange).frame(width: 6, height: 6).offset(x: -2, y: 2)
                    }
                }
            }
            .contentShape(Rectangle())
            .buttonStyle(.plain)
            .help(app.t(
                "Insert Anchor (Critical Directive or User Instruction framing)",
                "アンカーを注入(Critical DirectiveまたはUser Instruction枠)"
            ))
            .popover(isPresented: $showVisualAnchorPrompt) {
                VStack(alignment: .leading, spacing: 10) {
                    Text(app.t("Anchor Injection", "アンカー注入"))
                        .font(.headline)
                    Text(app.t(
                        "Inject once, or every turn automatically (Persistent Task). Set Persistent with an empty field to clear it.",
                        "1回のみ注入するか、毎ターン自動注入（Persistent Task）するか選択できます。\n空欄でSet Persistentを押すと解除されます。"
                    ))
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    Picker("", selection: $anchorFramingStyle) {
                        Text(app.t("Critical Directive", "Critical Directive")).tag(AnchorFramingStyle.criticalDirective)
                        Text(app.t("User Instruction", "User Instruction")).tag(AnchorFramingStyle.userInstruction)
                    }
                    .pickerStyle(.segmented)
                    .labelsHidden()

                    TextEditor(text: $visualAnchorText)
                        .frame(width: 300, height: 100)
                        .font(.system(size: 12, design: .monospaced))
                        .border(Color.gray.opacity(0.3))

                    HStack {
                        Spacer()
                        Button("Cancel") {
                            showVisualAnchorPrompt = false
                        }
                        Button(app.persistentTaskAnchor.isEmpty ? "Set Persistent" : "Clear Persistent") {
                            app.persistentTaskAnchor = visualAnchorText
                            showVisualAnchorPrompt = false
                            visualAnchorText = ""
                        }
                        .buttonStyle(.bordered)
                        .tint(app.persistentTaskAnchor.isEmpty ? .orange : .gray)

                        Button("Inject Once") {
                            guard !visualAnchorText.isEmpty else { return }
                            let anchorBase64 = anchorFramingStyle == .criticalDirective
                                ? CognitiveAnchorEngine.shared.getCustomAnchor(text: visualAnchorText)
                                : CognitiveAnchorEngine.shared.getUserPromptAnchor(text: visualAnchorText)
                            // Base64からローカルファイルに書き出して添付する
                            if let data = Data(base64Encoded: anchorBase64),
                               let img = NSImage(data: data) {
                                let tempUrl = FileManager.default.temporaryDirectory.appendingPathComponent("anchor_\(UUID().uuidString).png")
                                if let tiff = img.tiffRepresentation,
                                   let bitmap = NSBitmapImageRep(data: tiff),
                                   let png = bitmap.representation(using: .png, properties: [:]) {
                                    try? png.write(to: tempUrl)
                                    let attached = AttachedImage(name: "VisualAnchor.png", url: tempUrl, nsImage: img)
                                    app.attachedImages.append(attached)
                                }
                            }
                            showVisualAnchorPrompt = false
                            visualAnchorText = ""
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(anchorFramingStyle == .criticalDirective ? .red : .blue)
                    }
                }
                .padding()
            }

            // ── Auto Visual Anchor images on/off ──
            // Toggles whether the automatic per-turn Cognitive Anchor
            // images (searchForce/doubt/logic/etc, rendered every turn
            // for multimodal-classified models) are actually attached.
            // Kept as a runtime switch rather than removed outright, so
            // it can be flipped off for a quick A/B test (e.g. does a
            // model's output quality change without these images) and
            // back on again without a rebuild.
            Button {
                app.autoVisualAnchorImagesEnabled.toggle()
            } label: {
                Image(systemName: app.autoVisualAnchorImagesEnabled ? "eye.fill" : "eye.slash.fill")
                    .font(.system(size: 15))
                    .foregroundStyle(
                        app.autoVisualAnchorImagesEnabled
                        ? Color(red: 0.6, green: 0.8, blue: 1.0)
                        : Theme.dim
                    )
                    .frame(width: 26, height: 26)
            }
            .contentShape(Rectangle())
            .buttonStyle(.plain)
            .help(app.autoVisualAnchorImagesEnabled
                ? app.t("Auto Visual Anchor images: ON (click to disable)", "自動Visual Anchor画像: ON（クリックで無効化）")
                : app.t("Auto Visual Anchor images: OFF (click to enable)", "自動Visual Anchor画像: OFF（クリックで有効化）"))

            // ── Context usage indicator ──
            ContextUsageIndicator()

            // ── Verified URL registry ──
            // Lets the user directly pin a confirmed URL for a
            // named destination (e.g. "Gemini") into Vera, rather
            // than relying only on the organic save-approval flow
            // after a conversation. CRITICAL RULE 8 has the agent
            // check this via [VERIFIED_URL_LOOKUP: name] before
            // navigating to a named site, instead of guessing a
            // URL from its own (possibly stale) internal knowledge.
            Button {
                showVerifiedURLPrompt = true
            } label: {
                Image(systemName: "link.badge.plus")
                    .font(.system(size: 15))
                    .foregroundStyle(Theme.ok)
                    .frame(width: 26, height: 26)
            }
            .contentShape(Rectangle())
            .buttonStyle(.plain)
            .help(app.t("Register a verified URL", "検証済みURLを登録"))
            .popover(isPresented: $showVerifiedURLPrompt) {
                VStack(alignment: .leading, spacing: 10) {
                    Text(app.t("Register Verified URL", "検証済みURLの登録"))
                        .font(.headline)
                    Text(app.t(
                        "Pin a confirmed URL for a named site (e.g. \"Gemini\") into Vera, so the agent checks it instead of guessing.",
                        "「Gemini」のような名前付きサイトの確認済みURLをVeraに固定登録します。エージェントは推測する前にこれを確認します。"
                    ))
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    TextField(app.t("Name (e.g. Gemini)", "名前（例: Gemini）"), text: $verifiedURLName)
                        .textFieldStyle(.roundedBorder)
                        .frame(width: 280)
                    TextField(app.t("URL (e.g. https://gemini.google.com/)", "URL（例: https://gemini.google.com/）"), text: $verifiedURLValue)
                        .textFieldStyle(.roundedBorder)
                        .frame(width: 280)

                    if !verifiedURLStatus.isEmpty {
                        Text(verifiedURLStatus)
                            .font(.caption)
                            .foregroundStyle(Theme.ok)
                    }

                    HStack {
                        Spacer()
                        Button(app.t("Cancel", "キャンセル")) {
                            showVerifiedURLPrompt = false
                            verifiedURLStatus = ""
                        }
                        Button(app.t("Register", "登録")) {
                            let name = verifiedURLName
                            let url = verifiedURLValue
                            Task {
                                let ok = await VeraMemoryBridge.recordVerifiedURL(name: name, url: url)
                                await MainActor.run {
                                    verifiedURLStatus = ok
                                        ? app.t("✓ Registered", "✓ 登録しました")
                                        : app.t("✗ Failed — check vera-memory connection", "✗ 失敗 — vera-memory接続を確認してください")
                                    if ok {
                                        verifiedURLName = ""
                                        verifiedURLValue = ""
                                    }
                                }
                            }
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(.green)
                        .disabled(verifiedURLName.trimmingCharacters(in: .whitespaces).isEmpty
                            || verifiedURLValue.trimmingCharacters(in: .whitespaces).isEmpty)
                    }
                }
                .padding()
            }

            // ── Self Fix — icon-only, fixed frame ────────────────
            // Using just the icon + background color (no expanding text)
            // so width never changes and TextEditor stays in place.
            Button {
                app.selfFixMode.toggle()
            } label: {
                Image(systemName: app.selfFixMode
                      ? "wrench.and.screwdriver.fill"
                      : "wrench.and.screwdriver")
                    .font(.system(size: 13))
                    .foregroundStyle(app.selfFixMode
                                     ? Color.black
                                     : Theme.dim)
                    .frame(width: 26, height: 26)
                    .background(
                        app.selfFixMode
                            ? Theme.warn
                            : Color.white.opacity(0.06),
                        in: RoundedRectangle(cornerRadius: 5)
                    )
            }
            .contentShape(Rectangle())
            .buttonStyle(.plain)
            .help(app.selfFixMode
                  ? app.t("Self Fix Mode ON — tap to disable", "Self Fix モード ON — タップで解除")
                  : app.t("Self Fix: auto-fix IDE source", "Self Fix: IDEソースを自己修正"))
            // ── L3.5 OS Asset Build Button ──
            @ObservedObject var assetVault = OSAssetMemoryVault.shared
            
            Button {
                app.addSystemMessage(app.t("🔄 Starting L3.5 PC Asset Map generation...", "🔄 L3.5 PC資産マップの生成を開始します..."))
                assetVault.scanBackground()
            } label: {
                Image(systemName: "macwindow.badge.plus")
                    .font(.system(size: 13))
                    .foregroundStyle(assetVault.isScanning ? Color.gray : Theme.sel)
                    .frame(width: 26, height: 26)
            }
            .contentShape(Rectangle())
            .buttonStyle(.plain)
            .disabled(assetVault.isScanning)
            .help(app.t("Generate L3.5 PC Asset Map", "PC内資産マップ(L3.5)を生成する"))
            .onChange(of: assetVault.scanProgress) { newValue in
                if !newValue.isEmpty {
                    app.addSystemMessage(newValue)
                }
            }
        }
        // FIXED width — never changes regardless of selfFixMode
        .frame(width: 142, alignment: .leading)
    }

    // `canSend`/`composerHeight`/`sendMessage`/`needsScreenContentionWarning`/
    // `confirmScreenContention` moved to UnifiedComposerView.swift with the
    // rest of the composer.

    private var modelDisplayName: String {
        switch app.modelStatus {
        case .ollamaReady(let m):              return m
        case .mlxReady(let m):                 return m.components(separatedBy: "/").last ?? m
        case .anthropicReady(let m, _):        return m
        case .ready(let n):                    return n
        case .mlxDownloading(let m):           return "↓ \(m.components(separatedBy: "/").last ?? m)…"
        case .connecting:                      return "Connecting…"
        default:                               return "Select model ↓"
        }
    }

    private func extractThinking(from text: String) -> String {
        let pattern = #"<think>([\s\S]*?)</think>"#
        guard let regex = try? NSRegularExpression(pattern: pattern),
              let match = regex.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)),
              let range = Range(match.range(at: 1), in: text)
        else { return "" }
        return String(text[range]).trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

// MARK: - Progressive garment resolution sidebar

/// One Atelier surface, progressively disclosed. This is deliberately a
/// normal right-hand column rather than a sheet, popover or floating window,
/// so the transcript and the evidence that caused the request remain visible.
private struct GarmentResolutionSidebarView: View {
    @EnvironmentObject private var app: AppState
    @ObservedObject private var job = GarmentGenerationJob.shared

    let request: GarmentResolutionRequest

    @State private var showsEntry = false
    @State private var showsGeometryHelp = false
    @State private var showsConnectionHelp = false
    @State private var values: [String: String] = [:]
    @State private var geometryValues: [String: String] = [:]
    @State private var measured = false
    @State private var isResolving = false
    @State private var resolutionFeedback: String?
    @State private var resolutionFailed = false

    private var consent: GarmentLLMResolutionConsent? {
        guard job.activeLLMResolutionConsent?.requestID == request.id else { return nil }
        return job.activeLLMResolutionConsent
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                header
                explanation
                requirementSummary
                missingFields
                authorityBoundary
                actions
                if let resolutionFeedback {
                    Text(resolutionFeedback)
                        .font(.system(size: 10, weight: .medium))
                        .foregroundStyle(resolutionFailed ? Theme.bad : Theme.ok)
                        .fixedSize(horizontal: false, vertical: true)
                }
                provenance
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .topLeading)
        }
        .frame(width: 336)
        .frame(maxHeight: .infinity)
        .background(Theme.panel)
        .id(request.id)
        .onChange(of: request.id) { _, _ in
            showsEntry = false
            showsGeometryHelp = false
            showsConnectionHelp = false
            values = [:]
            geometryValues = [:]
            measured = false
            isResolving = false
            resolutionFeedback = nil
            resolutionFailed = false
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack(spacing: 8) {
                Image(systemName: request.terminal
                      ? "stop.circle.fill" : "person.crop.circle.badge.questionmark")
                    .foregroundStyle(request.terminal ? Theme.bad : Theme.warn)
                Text(request.terminal
                     ? app.t("Typed stop", "型付き停止")
                     : app.t("Input needed", "入力が必要です"))
                    .font(.system(size: 13, weight: .bold))
                    .foregroundStyle(Theme.fg)
                Spacer(minLength: 0)
            }
            Text(request.title)
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(Theme.fg)
                .fixedSize(horizontal: false, vertical: true)
            HStack(spacing: 6) {
                badge(request.stage, color: Theme.sel)
                badge(request.authority, color: request.authority == "PROPOSED"
                      ? Theme.warn : Theme.faint)
            }
        }
    }

    private var explanation: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(app.t("Why this is needed", "なぜ必要か"))
                .font(.system(size: 10, weight: .bold))
                .foregroundStyle(Theme.dim)
            Text(request.explanation)
                .font(.system(size: 12))
                .foregroundStyle(Theme.fg)
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
            Text(request.code)
                .font(.system(size: 10, design: .monospaced))
                .foregroundStyle(request.terminal ? Theme.bad : Theme.warn)
                .textSelection(.enabled)
        }
        .padding(10)
        .background(Theme.panel2, in: RoundedRectangle(cornerRadius: 8))
    }

    private var missingFields: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(app.t("Unobserved fields", "未観測の項目"))
                .font(.system(size: 11, weight: .bold))
                .foregroundStyle(Theme.fg)
            if request.missingFields.isEmpty {
                Text(app.t("No field can close this stop.", "この停止を閉じられる入力項目はありません。"))
                    .font(.system(size: 11))
                    .foregroundStyle(Theme.bad)
            } else {
                ForEach(request.missingFields, id: \.self) { field in
                    VStack(alignment: .leading, spacing: 3) {
                        HStack(spacing: 6) {
                            Text(fieldTitle(field))
                                .font(.system(size: 11, weight: .semibold))
                                .foregroundStyle(Theme.fg)
                            Spacer(minLength: 0)
                            Text("UNOBSERVED")
                                .font(.system(size: 8, weight: .bold, design: .monospaced))
                                .foregroundStyle(Theme.warn)
                        }
                        Text(field)
                            .font(.system(size: 9, design: .monospaced))
                            .foregroundStyle(Theme.dim)
                            .textSelection(.enabled)
                        Text(fieldReason(field))
                            .font(.system(size: 10))
                            .foregroundStyle(Theme.dim)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .padding(8)
                    .background(Color.white.opacity(0.025),
                                in: RoundedRectangle(cornerRadius: 6))
                    .overlay(RoundedRectangle(cornerRadius: 6)
                        .strokeBorder(Theme.line, lineWidth: 0.7))
                }
            }
        }
    }

    private var requirementSummary: some View {
        VStack(alignment: .leading, spacing: 7) {
            Text(app.t("Resolution scope", "不足の種類"))
                .font(.system(size: 11, weight: .bold))
                .foregroundStyle(Theme.fg)
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 122), spacing: 5)],
                      alignment: .leading, spacing: 5) {
                ForEach(requirementCategories, id: \.id) { category in
                    Label(app.t(category.english, category.japanese),
                          systemImage: category.icon)
                        .font(.system(size: 9.5, weight: .semibold))
                        .foregroundStyle(category.color)
                        .padding(.horizontal, 7)
                        .padding(.vertical, 4)
                        .background(category.color.opacity(0.10), in: Capsule())
                }
            }
        }
    }

    private var authorityBoundary: some View {
        VStack(alignment: .leading, spacing: 5) {
            Label(app.t("LLM authority boundary", "LLMの権限境界"),
                  systemImage: "lock.shield")
                .font(.system(size: 11, weight: .bold))
                .foregroundStyle(Theme.warn)
            Text(app.t(
                "An LLM may only create PROPOSED alternatives for the exact fields above. It cannot turn a proposal into an observation, measurement or approval.",
                "LLMが作れるのは上記項目に限定したPROPOSED候補だけです。提案を観測・実測・承認済みへ昇格させることはできません。"))
                .font(.system(size: 10.5))
                .foregroundStyle(Theme.dim)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(10)
        .background(Theme.warn.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8)
            .strokeBorder(Theme.warn.opacity(0.35), lineWidth: 0.8))
    }

    private var actions: some View {
        VStack(alignment: .leading, spacing: 8) {
            resolutionButton(
                app.t("Enter or measure", "入力・実測する"),
                systemImage: "ruler",
                option: GarmentResolutionRequest.enterOrMeasure,
                color: Theme.sel) {
                    guard app.beginGarmentHumanInput(request) else { return }
                    withAnimation(.easeInOut(duration: 0.18)) { showsEntry.toggle() }
                }
            if showsEntry { entryEditor.transition(.opacity) }

            resolutionButton(
                app.t("Edit geometry", "形状を編集する"),
                systemImage: "point.3.connected.trianglepath.dotted",
                option: GarmentResolutionRequest.editGeometry,
                color: Theme.sel) {
                    guard app.beginGarmentGeometryEdit(request) else { return }
                    withAnimation(.easeInOut(duration: 0.18)) {
                        showsGeometryHelp.toggle()
                    }
                }
            if showsGeometryHelp { geometryHelp.transition(.opacity) }

            resolutionButton(
                app.t("Connect provider", "検索・プロバイダーを接続"),
                systemImage: "network.badge.shield.half.filled",
                option: GarmentResolutionRequest.connectProvider,
                color: Theme.sel) {
                    guard app.beginGarmentProviderConnection(request) else { return }
                    withAnimation(.easeInOut(duration: 0.18)) {
                        showsConnectionHelp.toggle()
                    }
                }
            if showsConnectionHelp { connectionHelp.transition(.opacity) }

            resolutionButton(
                app.t("Allow one-time LLM proposal", "LLMの一回限りの提案を許可"),
                systemImage: "sparkles.rectangle.stack",
                option: GarmentResolutionRequest.allowOneTimeLLMProposal,
                color: Theme.warn) {
                    performResolution(
                        success: app.t(
                            "One PROPOSED-only grant was persisted.",
                            "PROPOSED限定の許可を永続化しました。")) {
                        await app.grantOneTimeGarmentLLMProposal(request)
                    }
                }
            if let consent { consentCard(consent) }

            resolutionButton(
                app.t("Keep unknown / use bounded alternatives",
                      "UNKNOWNを保持して限定候補を使う"),
                systemImage: "arrow.triangle.branch",
                option: GarmentResolutionRequest.keepUnknownUseBoundedAlternatives,
                color: Theme.ok) {
                    performResolution(
                        success: app.t(
                            "Bounded alternatives were persisted; fields remain unobserved.",
                            "限定候補を永続化しました。項目は未観測のままです。")) {
                        await app.continueGarmentWithBoundedAlternatives(request)
                    }
                }

            resolutionButton(
                app.t("Stop with reason (\(request.code))",
                      "理由付きで停止（\(request.code)）"),
                systemImage: "stop.fill",
                option: GarmentResolutionRequest.stop,
                color: Theme.bad) {
                    performResolution(
                        success: app.t(
                            "The typed stop was persisted.",
                            "理由付き停止を永続化しました。")) {
                        await app.stopGarmentResolution(request)
                    }
                }
            if isResolving {
                HStack(spacing: 8) {
                    ProgressView().controlSize(.small)
                    Text(app.t(
                        "Verifying the persisted factory event…",
                        "工場イベントの永続化を検証中…"))
                        .font(.system(size: 10))
                        .foregroundStyle(Theme.dim)
                }
            }
        }
    }

    private var entryEditor: some View {
        VStack(alignment: .leading, spacing: 8) {
            Picker("", selection: $measured) {
                Text(app.t("Entered", "入力値")).tag(false)
                Text(app.t("Measured", "実測値")).tag(true)
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            ForEach(request.missingFields, id: \.self) { field in
                TextField(fieldTitle(field), text: Binding(
                    get: { values[field, default: ""] },
                    set: { values[field] = $0 }))
                    .textFieldStyle(.roundedBorder)
                    .font(.system(size: 11))
            }
            Text(app.t(
                "Include units. Entered values remain HUMAN_ENTERED; choose Measured only for values you actually measured.",
                "単位も入力してください。通常入力はHUMAN_ENTEREDのままです。実際に測った値だけ「実測値」を選んでください。"))
                .font(.system(size: 9.5))
                .foregroundStyle(Theme.dim)
                .fixedSize(horizontal: false, vertical: true)
            Button {
                performResolution(
                    success: app.t(
                        "The scoped human values were accepted by the factory.",
                        "指定範囲の人間入力を工場が受理しました。")) {
                    await app.submitGarmentResolution(
                        request, values: values, measured: measured)
                }
            } label: {
                Label(app.t("Submit scoped values", "この項目だけ送信"),
                      systemImage: "arrow.up.circle.fill")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .disabled(isResolving || Set(values.keys.filter {
                !values[$0, default: ""]
                    .trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            }) != Set(request.missingFields))
        }
        .padding(9)
        .background(Theme.panel2, in: RoundedRectangle(cornerRadius: 8))
    }

    private var geometryHelp: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(app.t("Geometry remains a human edit", "形状は人が編集します"))
                .font(.system(size: 10.5, weight: .bold))
                .foregroundStyle(Theme.fg)
            Text(app.t(
                "Use the inline Atelier geometry card in the transcript. Its result returns through the same typed request; opening this guide does not approve or alter geometry.",
                "会話内のAtelier形状カードを操作してください。編集結果は同じ型付き要求へ戻ります。このガイドを開くだけでは形状の変更・承認は行いません。"))
                .font(.system(size: 10))
                .foregroundStyle(Theme.dim)
                .fixedSize(horizontal: false, vertical: true)
            ForEach(request.missingFields, id: \.self) { field in
                TextField(
                    app.t("Edit artifact for \(fieldTitle(field))",
                          "\(fieldTitle(field))の編集結果/digest"),
                    text: Binding(
                        get: { geometryValues[field, default: ""] },
                        set: { geometryValues[field] = $0 }))
                    .textFieldStyle(.roundedBorder)
                    .font(.system(size: 11))
            }
            Button {
                performResolution(
                    success: app.t(
                        "The human geometry edit was persisted.",
                        "人による形状編集を永続化しました。")) {
                    await app.submitGarmentGeometryResolution(
                        request, editArtifacts: geometryValues)
                }
            } label: {
                Label(app.t("Submit geometry edit", "形状編集を確定"),
                      systemImage: "point.3.filled.connected.trianglepath.dotted")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .disabled(isResolving || Set(geometryValues.keys.filter {
                !geometryValues[$0, default: ""]
                    .trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            }) != Set(request.missingFields))
        }
        .padding(9)
        .background(Theme.panel2, in: RoundedRectangle(cornerRadius: 8))
    }

    private var connectionHelp: some View {
        VStack(alignment: .leading, spacing: 7) {
            Text(app.t("Connection remains explicit", "接続は明示的に行います"))
                .font(.system(size: 10.5, weight: .bold))
                .foregroundStyle(Theme.fg)
            Text(app.t(
                "Connect only the provider required by this request. Search results remain cited proposals and do not become image observations.",
                "この要求に必要なプロバイダーだけを接続してください。検索結果は出典付きPROPOSEDのままで、画像の観測事実にはなりません。"))
                .font(.system(size: 10))
                .foregroundStyle(Theme.dim)
                .fixedSize(horizontal: false, vertical: true)
            Button {
                performResolution(
                    success: app.t(
                        "The connection request was persisted; the missing evidence remains OPEN.",
                        "接続要求を永続化しました。不足資料はOPENのままです。")) {
                    await app.connectGarmentProvider(request)
                }
            } label: {
                Label(app.t("Record request and open settings",
                            "接続要求を記録して設定を開く"),
                      systemImage: "gearshape")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
            .disabled(isResolving)
        }
        .padding(9)
        .background(Theme.panel2, in: RoundedRectangle(cornerRadius: 8))
    }

    private func consentCard(_ consent: GarmentLLMResolutionConsent) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            Label(app.t("One proposal turn granted", "提案1回分を許可済み"),
                  systemImage: "checkmark.shield")
                .font(.system(size: 10.5, weight: .bold))
                .foregroundStyle(Theme.warn)
            Text(consent.fieldKeys.joined(separator: ", "))
                .font(.system(size: 9, design: .monospaced))
                .foregroundStyle(Theme.dim)
                .textSelection(.enabled)
            Text("authority ≤ \(consent.authorityCeiling)")
                .font(.system(size: 9, weight: .bold, design: .monospaced))
                .foregroundStyle(Theme.warn)
            Text("consent \(consent.engineConsentDigest.prefix(16))")
                .font(.system(size: 8.5, design: .monospaced))
                .foregroundStyle(Theme.faint)
                .textSelection(.enabled)
            Text("workflow \(consent.boundWorkflowDigest.prefix(16))")
                .font(.system(size: 8.5, design: .monospaced))
                .foregroundStyle(Theme.faint)
                .textSelection(.enabled)
            Text(app.t(
                "Permission alone does not resolve this request. A provider must return every scoped field through CONSENTED_LLM_PROPOSAL; all output remains PROPOSED.",
                "許可だけでは要求は解決しません。プロバイダーがCONSENTED_LLM_PROPOSALとして対象項目を返す必要があり、出力はすべてPROPOSEDのままです。"))
                .font(.system(size: 9.5))
                .foregroundStyle(Theme.dim)
                .fixedSize(horizontal: false, vertical: true)
            HStack {
                Button(app.t("Revoke", "取り消す"), role: .destructive) {
                    app.revokeGarmentLLMProposalConsent()
                }
                .buttonStyle(.bordered)
                .disabled(isResolving)
            }
        }
        .padding(9)
        .background(Theme.warn.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
    }

    private var provenance: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text("request \(request.id.prefix(12))")
            Text("provenance \(request.provenanceDigest.prefix(12))")
            Text("project \(job.activeResolutionProject)")
        }
        .font(.system(size: 8.5, design: .monospaced))
        .foregroundStyle(Theme.faint)
        .textSelection(.enabled)
    }

    private func performResolution(
        success: String,
        operation: @escaping @MainActor () async -> Bool
    ) {
        guard !isResolving else { return }
        isResolving = true
        resolutionFeedback = nil
        resolutionFailed = false
        Task { @MainActor in
            let accepted = await operation()
            resolutionFailed = !accepted
            resolutionFeedback = accepted
                ? success
                : app.t(
                    "The factory rejected this action. The request remains open; see the transcript for its typed reason.",
                    "工場が操作を拒否しました。要求はOPENのままです。型付き理由は会話欄を確認してください。")
            isResolving = false
        }
    }

    private func resolutionButton(_ title: String,
                                  systemImage: String,
                                  option: String,
                                  color: Color,
                                  action: @escaping () -> Void) -> some View {
        let enabled = request.allows(option)
        return Button(action: action) {
            HStack(spacing: 8) {
                Image(systemName: systemImage).frame(width: 16)
                Text(title)
                    .font(.system(size: 11, weight: .semibold))
                    .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 0)
                if !enabled { Image(systemName: "nosign") }
            }
            .foregroundStyle(enabled ? color : Theme.faint)
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(color.opacity(enabled ? 0.09 : 0.025),
                        in: RoundedRectangle(cornerRadius: 7))
            .overlay(RoundedRectangle(cornerRadius: 7)
                .strokeBorder(color.opacity(enabled ? 0.35 : 0.10), lineWidth: 0.7))
        }
        .buttonStyle(.plain)
        .disabled(!enabled || isResolving)
    }

    private func badge(_ text: String, color: Color) -> some View {
        Text(text)
            .font(.system(size: 8.5, weight: .bold, design: .monospaced))
            .lineLimit(1)
            .padding(.horizontal, 6).padding(.vertical, 3)
            .foregroundStyle(color)
            .background(color.opacity(0.10), in: Capsule())
    }

    private func fieldTitle(_ key: String) -> String {
        let labels: [String: (String, String)] = [
            "visible_garment_parts": ("Visible garment parts", "正面の服飾部品"),
            "layer_order": ("Layer order", "重なり順"),
            "foreground_boundary": ("Foreground boundary", "前景の境界"),
            "body_hair_background_exclusions": ("Body / hair / background exclusions", "人体・髪・背景の除外"),
            "provider_connection": ("Provider connection", "プロバイダー接続"),
            "search_provider_connection": ("Search connection", "検索接続"),
            "height_cm": ("Height", "身長"),
            "chest_cm": ("Chest", "胸囲"),
            "waist_cm": ("Waist", "胴囲"),
            "hip_cm": ("Hip", "腰囲"),
            "body_length_cm": ("Body length", "背丈"),
            "rear_structure": ("Rear structure", "背面構造"),
            "rear_closure": ("Rear closure", "背面の開閉"),
            "rear_seams": ("Rear seams", "背面の縫い目"),
            "material_composition": ("Material composition", "素材組成"),
            "thickness_mm": ("Thickness", "厚み"),
            "warp_stretch": ("Warp stretch", "経方向の伸縮"),
            "weft_stretch": ("Weft stretch", "緯方向の伸縮"),
            "friction": ("Friction", "摩擦"),
            "bending_stiffness": ("Bending stiffness", "曲げ剛性"),
            "garment_surface_geometry": ("Garment surface", "服の表面形状"),
            "arbitrary_3d_target": ("Arbitrary 3D target", "任意3D目標"),
            "approved_target_geometry": ("Approved target geometry", "承認対象3D"),
            "completed_pattern": ("Completed pattern", "完成型紙"),
            "pattern_geometry": ("Pattern geometry", "型紙形状"),
            "pattern_validation": ("Pattern validation", "型紙検証"),
            "sewing_reference_provider": ("Sewing reference", "縫製資料"),
            "seam_finish": ("Seam finish", "縫製始末"),
            "lining": ("Lining", "裏地"),
            "interfacing": ("Interfacing", "芯地"),
            "physics_calibration": ("Physics calibration", "物理校正"),
            "material_calibration": ("Material calibration", "素材校正"),
            "wind_calibration": ("Wind calibration", "風校正"),
            "required_input": ("Required input", "必要な入力"),
        ]
        guard let label = labels[key] else { return key.replacingOccurrences(of: "_", with: " ") }
        return app.t(label.0, label.1)
    }

    private func fieldReason(_ key: String) -> String {
        if key.contains("rear") {
            return app.t("The rear is not visible in a front image and must remain a candidate.",
                         "正面画像では背面を観測できないため、候補として扱う必要があります。")
        }
        if key.contains("material") || key.contains("stretch")
            || key == "friction" || key.contains("stiffness") || key.contains("thickness") {
            return app.t("Required to bound drape and pattern calculations; pixels do not measure it.",
                         "ドレープと型紙計算の範囲を定める値です。画像画素からは実測できません。")
        }
        if key.contains("cm") {
            return app.t("Required to size the selected wearer; it is not measured from the photo.",
                         "着用者寸法へ合わせるため必要です。写真からの実測値ではありません。")
        }
        if key.contains("provider") {
            return app.t("The requested evidence or reconstruction route has no connected provider.",
                         "必要な資料・再構成経路のプロバイダーが接続されていません。")
        }
        if key.contains("pattern") {
            return app.t("A cuttable, validated pattern must be derived from approved geometry.",
                         "承認済み形状から、裁断可能で検証済みの型紙へ落とす必要があります。")
        }
        if key.contains("calibration") {
            return app.t("A preview can use bounded assumptions; a physical claim needs measured calibration.",
                         "プレビューは限定仮定で可能ですが、物理的主張には実測校正が必要です。")
        }
        if key.contains("finish") || key == "lining" || key == "interfacing" {
            return app.t("Construction order alone does not determine the real seam finish or support layers.",
                         "縫製順だけでは、実際の縫製始末・裏地・芯地は確定できません。")
        }
        return app.t("The deterministic loop needs this value before the next bounded transition.",
                     "決定論的ループが次の限定遷移へ進むために必要です。")
    }

    private struct RequirementCategory: Identifiable {
        let id: String
        let english: String
        let japanese: String
        let icon: String
        let color: Color
        let markers: [String]
    }

    private var requirementCategories: [RequirementCategory] {
        let categories: [RequirementCategory] = [
            .init(id: "rear", english: "Rear", japanese: "背面",
                  icon: "person.crop.rectangle.stack", color: Theme.warn,
                  markers: ["rear", "back_"]),
            .init(id: "material", english: "Material", japanese: "素材",
                  icon: "swatchpalette", color: Theme.warn,
                  markers: ["material", "thickness", "stretch", "friction", "stiffness"]),
            .init(id: "dimensions", english: "Dimensions", japanese: "寸法",
                  icon: "ruler", color: Theme.sel,
                  markers: ["_cm", "measurement", "dimension", "body_size"]),
            .init(id: "3d", english: "Arbitrary 3D", japanese: "任意3D",
                  icon: "cube.transparent", color: Theme.sel,
                  markers: ["3d", "geometry", "surface"]),
            .init(id: "pattern", english: "Completed pattern", japanese: "完成型紙",
                  icon: "scissors", color: Theme.ok,
                  markers: ["pattern", "dxf"]),
            .init(id: "finish", english: "Sewing finish", japanese: "縫製始末",
                  icon: "point.topleft.down.to.point.bottomright.curvepath", color: Theme.ok,
                  markers: ["seam_finish", "lining", "interfacing", "sewing_reference"]),
            .init(id: "calibration", english: "Physics calibration", japanese: "物理校正",
                  icon: "waveform.path.ecg", color: Theme.warn,
                  markers: ["calibration", "wind_tunnel", "physical_test"]),
            .init(id: "search", english: "Search connection", japanese: "検索接続",
                  icon: "network", color: Theme.sel,
                  markers: ["provider", "search", "retrieval", "corpus", "fashionsiglip"]),
        ]
        let signal = ([request.code, request.stage] + request.missingFields)
            .joined(separator: " ").lowercased()
        let matches = categories.filter { category in
            category.markers.contains { signal.contains($0) }
        }
        return matches.isEmpty
            ? [.init(id: "required", english: "Required input", japanese: "必要な入力",
                     icon: "questionmark.diamond", color: Theme.warn,
                     markers: [])]
            : matches
    }
}

// MARK: - ChatInputTextView (IME-aware Enter-to-send)
// NSViewRepresentable wrapping NSTextView for reliable Japanese IME handling.
//
// Behavior:
//   • Enter (no modifier):
//       - If IME has markedText (未確定文字) → confirms composition (default NSTextView behavior)
//       - If no markedText → sends the message
//   • Shift+Enter: inserts newline (multi-line input)
//   • ⌘+Enter: also sends the message (legacy shortcut)

struct ChatInputTextView: NSViewRepresentable {
    @Binding var text: String
    var onSend: () -> Void
    @Binding var isFocused: Bool
    /// How tall the text actually is once laid out.
    ///
    /// The composer was not fixed by choice — the frame already said
    /// `minHeight: 44, maxHeight: 110`. It never moved because an
    /// NSViewRepresentable has no intrinsic size to give SwiftUI, so the layout
    /// resolved to the minimum and stayed there no matter how much was typed.
    /// The height has to be measured on the AppKit side and handed back.
    @Binding var measuredHeight: CGFloat

    /// The laid-out height of the content, insets included.
    static func contentHeight(of textView: NSTextView) -> CGFloat {
        guard let manager = textView.layoutManager,
              let container = textView.textContainer else { return 0 }
        // usedRect is only meaningful after layout has actually been done, and
        // typing invalidates it — asking without ensuring returns the height
        // from before the keystroke.
        manager.ensureLayout(for: container)
        return manager.usedRect(for: container).height
            + textView.textContainerInset.height * 2
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(parent: self)
    }

    func makeNSView(context: Context) -> NSScrollView {
        let scrollView = NSScrollView()
        scrollView.hasVerticalScroller = true
        scrollView.hasHorizontalScroller = false
        scrollView.autohidesScrollers = true
        scrollView.borderType = .noBorder
        scrollView.drawsBackground = false

        let textView = IMEAwareTextView()
        textView.delegate = context.coordinator
        textView.onSend = onSend
        textView.isRichText = false
        textView.allowsUndo = true
        textView.font = NSFont.systemFont(ofSize: 13)
        textView.textColor = NSColor(red: 0.88, green: 0.88, blue: 0.92, alpha: 1.0)
        textView.backgroundColor = .clear
        textView.drawsBackground = false
        textView.minSize = NSSize(width: 0, height: 0)
        textView.maxSize = NSSize(width: CGFloat.greatestFiniteMagnitude, height: CGFloat.greatestFiniteMagnitude)
        textView.isVerticallyResizable = true
        textView.isHorizontallyResizable = false
        textView.autoresizingMask = [.width]
        textView.textContainerInset = NSSize(width: 0, height: 5)
        textView.textContainer?.lineFragmentPadding = 5
        textView.textContainer?.widthTracksTextView = true

        // Caret color
        textView.insertionPointColor = NSColor(red: 0.4, green: 0.7, blue: 1.0, alpha: 1.0)

        scrollView.documentView = textView
        context.coordinator.textView = textView

        return scrollView
    }

    func updateNSView(_ scrollView: NSScrollView, context: Context) {
        guard let textView = scrollView.documentView as? IMEAwareTextView else { return }

        // SwiftUI's FocusState does not automatically cross an
        // NSViewRepresentable boundary.  The unified Atelier composer sets
        // this binding after an image is ingested so the user can continue
        // typing immediately; without explicitly making the NSTextView the
        // first responder the binding changed but keyboard focus stayed on
        // the file picker (and assistive keyboard operation could not enter
        // the prompt at all).
        if isFocused,
           textView.window?.firstResponder !== textView {
            DispatchQueue.main.async { [weak textView] in
                guard let textView,
                      textView.window?.firstResponder !== textView else { return }
                textView.window?.makeFirstResponder(textView)
            }
        }

        // ── GUARD 1: Never interrupt active IME composition ──────────
        // Setting textView.string during composition destroys the markedText.
        if textView.hasMarkedText() {
            textView.onSend = onSend
            return
        }

        // ── GUARD 2: Prevent feedback loop ──────────────────────────
        // textDidChange sets parent.text → triggers updateNSView → must not set string again
        let coordinator = context.coordinator
        guard !coordinator.isSyncingToBinding else {
            textView.onSend = onSend
            return
        }

        // ── Only apply external changes (e.g., clearing after send) ─
        if textView.string != text {
            coordinator.isSyncingFromBinding = true
            textView.string = text
            coordinator.reportHeight(textView)
            textView.setSelectedRange(NSRange(location: textView.string.count, length: 0))
            coordinator.isSyncingFromBinding = false
        }

        textView.onSend = onSend
    }

    // MARK: - Coordinator

    class Coordinator: NSObject, NSTextViewDelegate {
        var parent: ChatInputTextView
        weak var textView: IMEAwareTextView?

        /// True while textDidChange is propagating to the binding.
        /// Prevents updateNSView from re-entering.
        var isSyncingToBinding = false

        /// True while updateNSView is writing to textView.string.
        /// Prevents textDidChange from re-entering.
        var isSyncingFromBinding = false

        init(parent: ChatInputTextView) {
            self.parent = parent
        }

        func textDidChange(_ notification: Notification) {
            guard let textView = notification.object as? NSTextView else { return }
            // Don't propagate if WE set the string programmatically
            guard !isSyncingFromBinding else { return }

            isSyncingToBinding = true
            parent.text = textView.string
            isSyncingToBinding = false
            reportHeight(textView)
        }

        /// Publishing height during a view update is what SwiftUI warns about,
        /// so it lands on the next runloop pass. Unchanged values are dropped
        /// to avoid a redraw on every keystroke that stays on one line.
        func reportHeight(_ textView: NSTextView) {
            let height = ChatInputTextView.contentHeight(of: textView)
            guard abs(height - parent.measuredHeight) > 0.5 else { return }
            DispatchQueue.main.async { [weak self] in
                self?.parent.measuredHeight = height
            }
        }

        func textDidBeginEditing(_ notification: Notification) {
            parent.isFocused = true
        }

        func textDidEndEditing(_ notification: Notification) {
            parent.isFocused = false
        }
    }
}

// MARK: - IMEAwareTextView
// Custom NSTextView subclass that intercepts Enter key events
// and checks IME composition state before deciding to send.

final class IMEAwareTextView: NSTextView {
    var onSend: (() -> Void)?

    override func insertNewline(_ sender: Any?) {
        // ── IME composition active → let default behavior confirm it ──
        if hasMarkedText() {
            super.insertNewline(sender)
            return
        }

        // ── Shift+Enter → insert actual newline (multi-line input) ──
        if NSEvent.modifierFlags.contains(.shift) {
            super.insertNewline(sender)
            return
        }

        // ── Plain Enter (no IME, no Shift) → send message ──
        onSend?()
    }

    // Also support ⌘+Enter as a legacy send shortcut
    override func keyDown(with event: NSEvent) {
        let now = Date()
        Task { @MainActor in
            if let app = AppState.shared {
                if let last = app.lastKeystrokeTime {
                    let interval = now.timeIntervalSince(last)
                    if interval < 2.0 { // only capture continuous typing
                        var current = app.lastKeyboardEntropy ?? []
                        current.append(interval)
                        if current.count > 100 { current.removeFirst(current.count - 100) }
                        app.lastKeyboardEntropy = current
                    }
                }
                app.lastKeystrokeTime = now
            }
        }

        if event.keyCode == 36,  // Return key
           event.modifierFlags.contains(.command) {
            onSend?()
            return
        }
        super.keyDown(with: event)
    }
}

// MARK: - RateLimitStatusView

struct RateLimitStatusView: View {
    @EnvironmentObject var app: AppState
    
    var body: some View {
        TimelineView(.periodic(from: .now, by: 1.0)) { timeline in
            HStack(spacing: 6) {
                // Rate Limit Cooldown
                if let cooldown = app.searchCooldownUntil {
                    let remaining = cooldown.timeIntervalSince(timeline.date)
                    if remaining > 0 {
                        HStack(spacing: 4) {
                            Image(systemName: "timer")
                            Text("Cooldown: \(Int(remaining))s")
                        }
                        .font(.system(size: 10, weight: .bold, design: .monospaced))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 6).padding(.vertical, 2)
                        .background(Color.red.opacity(0.8), in: RoundedRectangle(cornerRadius: 3))
                    }
                }
                
                // Entropy Freshness
                if let ts = app.lastEntropyTimestamp {
                    let elapsed = timeline.date.timeIntervalSince(ts)
                    let remaining = 300 - elapsed
                    if remaining > 0 {
                        HStack(spacing: 4) {
                            Image(systemName: "shield.fill")
                            Text("Fresh: \(Int(remaining))s")
                        }
                        .font(.system(size: 10, weight: .bold, design: .monospaced))
                        .foregroundStyle(.black)
                        .padding(.horizontal, 6).padding(.vertical, 2)
                        .background(Color.green.opacity(0.8), in: RoundedRectangle(cornerRadius: 3))
                    }
                }
            }
        }
    }
}
