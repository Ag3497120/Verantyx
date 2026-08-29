import SwiftUI

// MARK: - AgentChatView
// Center panel: "Vibe Coding Workspace" + "Thinking Log" tabs
// Shows AntigravityAgent with <think> rendering in teal

struct AgentChatView: View {
    @EnvironmentObject var app: AppState
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
                    chatTranscriptArea
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
                        app.activeGarment = name
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
