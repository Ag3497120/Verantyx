import SwiftUI

// MARK: - AgentChatView
// Center panel: "Vibe Coding Workspace" + "Thinking Log" tabs
// Shows AntigravityAgent with <think> rendering in teal

struct AgentChatView: View {
    @EnvironmentObject var app: AppState
    @State private var showingHistory: Bool = false
    @State private var inputText: String = ""
    /// 0 = 「Vera に質問」, 1 = 「<verantyx> 〜 </verantyx> で投入」.
    @State private var placeholderPhase: Int = 0
    /// Laid-out height of the input's content, reported back from AppKit.
    @State private var composerContentHeight: CGFloat = 0
    @State private var showingModelPill = false

    /// Drives the composer glow. Eases out after the state settles.
    @State private var glowPulse: Bool = false

    /// The composer reads the same state machine as the window edge and the
    /// menu-bar icon. It used to read `isGenerating || isAgentControllingMouse`
    /// directly, which made three indicators that could disagree and gave
    /// planning, generating, exploring and operating one identical colour.
    @ObservedObject private var activity = AgentActivityCenter.shared

    private var runningGlowColor: Color { activity.state.color }
    private var runningGlowActive: Bool { activity.state.glows }
    @FocusState private var inputFocused: Bool
    
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
                // Every mode gets the same screen: memory and the free
                // window down the left, the cross as a watermark over
                // all of it, and the main area filled by whatever this
                // mode actually answers with — the transcript in every
                // mode except Bot. Vera runs under all three; only the
                // reply differs.
                VeraSovereignLayout {
                    if app.veraEngineMode == .atelier {
                        // 服飾の作業面。ここだけは会話が主役ではない —
                        // 見るのは服の状態で、Vera はその裏で台帳を持つ。
                        // 上のモデル選択は、のちに「どの AI に解析させるか」
                        // を選ぶ場所になる。
                        AtelierView().environmentObject(app)
                    } else if app.veraEngineMode == .veraBot {
                        // Bot's replies are screens, and an NSTextView
                        // cannot hold one. Same messages, rendered as
                        // views.
                        //
                        // The console sits above them because this is the
                        // one mode whose subject is the machine: naming a
                        // screen still summons it into the transcript, and
                        // the settings that never had a control are now
                        // simply visible. Chrome stays absent everywhere
                        // the work is a conversation; here the work is
                        // operating the thing.
                        VSplitView {
                            VeraOperatorConsole().environmentObject(app)
                                .frame(minHeight: 180, idealHeight: 300)
                            VeraBotTranscript().environmentObject(app)
                                .frame(minHeight: 160)
                        }
                    } else {
                        chatTranscriptArea
                    }
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
            inputBar
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
        .background(Color(red: 0.13, green: 0.13, blue: 0.16))
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
                        .foregroundStyle(Color(red: 0.4, green: 0.7, blue: 1.0))
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
        .background(Color(red: 0.15, green: 0.15, blue: 0.19))
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
                .foregroundStyle(Color(red: 0.45, green: 0.72, blue: 1.0))
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
            // 以前のモードは動くまま残す — 消すと、動いていたものを
            // 消したことになる。ただし常に見えている必要は無い。
            Picker("", selection: Binding(
                get: { app.veraEngineMode },
                set: { app.veraEngineMode = $0 })) {
                Text("Atelier").tag(AppState.VeraEngineMode.atelier)
                Divider()
                Text("Vera").tag(AppState.VeraEngineMode.veraModel)
                Text("Bot").tag(AppState.VeraEngineMode.veraBot)
                Text("LLM").tag(AppState.VeraEngineMode.localLLM)
            }
            .pickerStyle(.menu)
            .labelsHidden()
            .frame(width: 92)
            .controlSize(.small)
            .font(.system(size: 10))
            .help(app.t(
                "Atelier is the garment workbench. Vera answers from the store "
                + "alone — typed verdicts, no LLM in the turn. Bot answers about "
                + "the app itself. LLM is just a model, with nothing in front of it.",
                "Atelier は服飾の作業面。Vera は台帳だけで答える(型付き判定・"
                + "ターン内でLLMを呼ばない)。Bot はこのアプリについて答える。"
                + "LLM は素のモデル。"))

            // Which stamped Vera release answers — only when one does.
            if app.veraEngineMode == .veraModel {
                Picker("", selection: Binding(
                    get: { app.selectedVeraVersionId },
                    set: { id in Task { await app.selectVeraModelVersion(id) } })) {
                    Text(app.t("local build", "ローカル")).tag("local")
                    ForEach(app.veraModelVersions) { v in
                        Text(v.id).tag(v.id)
                    }
                }
                .pickerStyle(.menu)
                .frame(maxWidth: 170)
                .disabled(app.veraVersionBusy)
                .task { await app.refreshVeraModelVersions() }
                .help(app.t(
                    "Switching downloads the version and restarts the engine "
                    + "process — never a silent reload.",
                    "切替は版の取得とエンジンプロセスの再起動 — "
                    + "静かな差し替えはしません。"))
                if app.veraVersionBusy { ProgressView().controlSize(.small) }
            }

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
            // NSTextView ベースのトランスクリプト。
            // 単一テキストストレージのためメッセージをまたいでドラッグ選択・コピーができる。
            ChatTranscriptView(messages: visibleMessages, isGenerating: app.isGenerating)
                .frame(maxWidth: .infinity, maxHeight: .infinity)

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
                    .foregroundStyle(Color(red: 0.3, green: 0.9, blue: 0.7))
                Text(app.t("Save this turn to Vera?", "この内容を Vera に保存しますか？"))
                    .font(.system(size: 12, weight: .bold))
                    .foregroundStyle(Color(red: 0.9, green: 0.92, blue: 0.98))
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
                        .foregroundStyle(Color(red: 0.9, green: 0.4, blue: 0.4))
                        .padding(.horizontal, 12).padding(.vertical, 5)
                        .background(Capsule().fill(Color(red: 0.32, green: 0.1, blue: 0.1).opacity(0.7)))
                }
                .buttonStyle(.plain)

                Button {
                    app.approveVeraSave()
                } label: {
                    Text(app.t("Save", "保存")).font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(Color(red: 0.3, green: 0.92, blue: 0.5))
                        .padding(.horizontal, 12).padding(.vertical, 5)
                        .background(Capsule().fill(Color(red: 0.1, green: 0.28, blue: 0.15).opacity(0.8)))
                }
                .buttonStyle(.plain)
            }
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(Color(red: 0.13, green: 0.13, blue: 0.17))
                .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color(red: 0.3, green: 0.9, blue: 0.7).opacity(0.35), lineWidth: 1))
        )
        .shadow(color: .black.opacity(0.4), radius: 8, y: 2)
        .padding(.horizontal, 14)
        .padding(.bottom, 10)
    }


    // MARK: - Model selector bar

    /// ModelSelectorBarView is entirely about LLM backends: which one is
    /// loaded (Gatekeeper chip), the 監視(Auditor)/ERROR badge, the
    /// 自動/手動 execution-mode stepper. None of it means anything in Vera
    /// mode — no LLM ever enters that turn (see AppState.sendMessage's
    /// veraModel branch) — so showing it there was showing controls for a
    /// backend the mode never calls. Requested 2026-08-19. The engine-mode
    /// picker and, when Vera mode is active, the version picker ("ローカル"
    /// / a stamped release) already live in the top bar's veraModeControls
    /// — that is where Vera's own "which model answers" question is
    /// answered, so nothing is lost by hiding this bar here.
    ///
    /// The Atelier is hidden for the same reason, one step further along.
    /// It already has a model picker of its own — the ANALYSIS AI row in the
    /// left rail, which names the model and says what it is allowed to do
    /// ("writes proposals only") and opens the analyst sheet when tapped.
    /// Two selectors for one question is worse than either alone: the answer
    /// to "which AI is reading this garment" was in two places that could
    /// disagree, and neither said which one won. The composer itself stays —
    /// it is where re-design intent is typed ("もっと丸い襟に"), which is a
    /// different question from which backend answers it.
    private var modelSelectorBar: some View {
        HStack(spacing: 8) {
            if app.veraEngineMode != .veraModel && app.veraEngineMode != .atelier {
                ModelSelectorBarView()
            }

            Spacer()

            // ── Stop button (visible only while generating) ───────────
            if app.isGenerating {
                Button {
                    app.cancelGeneration()
                } label: {
                    HStack(spacing: 5) {
                        Image(systemName: "stop.fill").font(.system(size: 11))
                        Text(app.t("Stop", "停止")).font(.system(size: 11, weight: .semibold))
                    }
                    .foregroundStyle(.white)
                    .padding(.horizontal, 10).padding(.vertical, 5)
                    .background(
                        RoundedRectangle(cornerRadius: 6)
                            .fill(Color(red: 0.8, green: 0.2, blue: 0.2))
                    )
                    .contentShape(Rectangle())
                }
                .contentShape(Rectangle())
                .buttonStyle(.plain)
                .transition(.scale.combined(with: .opacity))
            }

            // ── Send button ───────────────────────────────────────────
            if !app.isGenerating {
            }
        }
        .padding(.horizontal, 10).padding(.vertical, 4)
        .background(Color(red: 0.15, green: 0.15, blue: 0.19))
        .animation(.easeInOut(duration: 0.15), value: app.isGenerating)
    }

    // MARK: - Input bar

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

    /// The three controls that belong beside what is being written, on their
    /// own line inside the box. Everything else moved behind the mark.
    private var composerControls: some View {
        HStack(spacing: 7) {
            JCrossMenu(items: [
                JCrossMenuItem(icon: "photo.badge.plus",
                               title: app.t("Add a photo", "写真を追加")) {
                    app.attachedImages.append(contentsOf: AttachmentManager.pickImages())
                },
                JCrossMenuItem(icon: "paperclip",
                               title: app.t("Add a file", "ファイルを追加")) {
                    app.attachedFiles.append(contentsOf: AttachmentManager.pickFiles())
                },
            ], japanese: AppLanguage.shared.isJapanese)
            // `modelSelectorBar`, not the bare `ModelSelectorBarView`:
            // the wrapper carries the STOP button, and its only call site
            // (`composerChrome`) had been unmounted — so a run in flight
            // could not be cancelled from the composer at all, and an
            // `isGenerating` that never cleared was both invisible and
            // unrecoverable. That is the shape of the dropped sends: the
            // guard at the top of `sendMessage` returns on `isGenerating`,
            // and with no Stop and no message there was nothing to see.
            modelSelectorBar
                .layoutPriority(1)
            JCrossSendButton(enabled: canSend) { sendMessage() }
        }
    }

    private var inputBar: some View {
        VStack(spacing: 7) {
            // The typing-time surface preview is gone. It popped a panel
            // above the composer as the word was still being typed, and
            // then pressing Return added the same panel to the log — two
            // different answers to one action, half a second apart.
            composerBox
        }
    }

    private var composerBox: some View {
        VStack(spacing: 0) {
            // ── Attachment preview strip ──────────────────────────────
            if !app.attachedImages.isEmpty || !app.attachedFiles.isEmpty {
                attachmentStrip
                Divider().opacity(0.3)
            }

            // ── IDE Fix mode banner / normal file badge ───────────────
            if app.selfFixMode {
                // Persistent IDE Fix banner — always visible while mode is active
                HStack(spacing: 8) {
                    Image(systemName: "lock.fill")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(Color(red: 1.0, green: 0.65, blue: 0.15))

                    Text("🔧 IDE Fix Mode")
                        .font(.system(size: 11, weight: .bold, design: .monospaced))
                        .foregroundStyle(Color(red: 1.0, green: 0.75, blue: 0.30))

                    if let file = app.selectedFile {
                        Text("▸ \(file.lastPathComponent)")
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(Color(red: 0.9, green: 0.6, blue: 0.2).opacity(0.8))
                            .lineLimit(1)
                            .truncationMode(.middle)
                    } else {
                        Text("▸ IDE Source Index")
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(Color(red: 0.9, green: 0.6, blue: 0.2).opacity(0.8))
                    }

                    Spacer()

                    // Exit button — explicitly exits IDE Fix mode
                    Button {
                        app.selfFixMode = false
                    } label: {
                        HStack(spacing: 4) {
                            Image(systemName: "xmark")
                                .font(.system(size: 9, weight: .bold))
                            Text(app.t("Exit Mode", "モード終了"))
                                .font(.system(size: 10, weight: .semibold))
                        }
                        .foregroundStyle(Color(red: 1.0, green: 0.65, blue: 0.15))
                        .padding(.horizontal, 8)
                        .padding(.vertical, 3)
                        .background(
                            RoundedRectangle(cornerRadius: 4)
                                .stroke(Color(red: 1.0, green: 0.65, blue: 0.15).opacity(0.5), lineWidth: 1)
                        )
                    }
                    .contentShape(Rectangle())
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(
                    LinearGradient(
                        colors: [
                            Color(red: 0.28, green: 0.18, blue: 0.04),
                            Color(red: 0.22, green: 0.14, blue: 0.02)
                        ],
                        startPoint: .leading, endPoint: .trailing
                    )
                )
                .overlay(
                    Rectangle()
                        .fill(Color(red: 1.0, green: 0.60, blue: 0.10).opacity(0.6))
                        .frame(height: 1),
                    alignment: .bottom
                )
            }

            // ── Text input + action buttons ───────────────────────────
            VStack(alignment: .leading, spacing: 6) {
                composerTextField
                composerControls
            }
            .padding(.horizontal, 11).padding(.top, 8).padding(.bottom, 7)
        }
        .background(
            app.selfFixMode
                ? Color(red: 0.22, green: 0.16, blue: 0.08)  // warm amber tint in self-fix mode
                : Color(red: 0.17, green: 0.17, blue: 0.21),
            in: RoundedRectangle(cornerRadius: 16, style: .continuous)
        )
        // While the agent is working the whole composer breathes. The small
        // activity icon stays where it was, but it loses to an overlapping
        // window — a glow the width of the input bar does not.
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(runningGlowActive
                        ? runningGlowColor.opacity(glowPulse ? 0.95 : 0.35)
                        : (app.selfFixMode
                           ? Color(red: 1.0, green: 0.60, blue: 0.10).opacity(0.8)
                           : Color.white.opacity(0.12)),
                        lineWidth: runningGlowActive ? 2 : 1)
        )
        .shadow(color: runningGlowActive
                ? runningGlowColor.opacity(glowPulse ? 0.55 : 0.12) : .clear,
                radius: runningGlowActive ? (glowPulse ? 16 : 4) : 0)
        .padding(.horizontal, 16)
        .padding(.bottom, 16)
        .padding(.top, 8)
        .animation(.easeInOut(duration: 0.2), value: app.selfFixMode)
        .onChange(of: runningGlowActive) { _, running in
            if running {
                withAnimation(.easeInOut(duration: 1.1).repeatForever(autoreverses: true)) {
                    glowPulse = true
                }
            } else {
                withAnimation(.easeOut(duration: 0.25)) { glowPulse = false }
            }
        }
        .onAppear {
            if runningGlowActive {
                withAnimation(.easeInOut(duration: 1.1).repeatForever(autoreverses: true)) {
                    glowPulse = true
                }
            }
        }
        // Drag-and-drop images onto the input bar
        .onDrop(of: [.image, .fileURL], isTargeted: nil) { providers in
            handleDrop(providers: providers)
            return true
        }
    }

    // MARK: - Attachment Strip

    private var attachmentStrip: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                // Image thumbnails
                ForEach(app.attachedImages) { img in
                    ZStack(alignment: .topTrailing) {
                        img.swiftUIImage
                            .resizable().scaledToFill()
                            .frame(width: 56, height: 56)
                            .clipShape(RoundedRectangle(cornerRadius: 6))
                            .overlay(
                                RoundedRectangle(cornerRadius: 6)
                                    .stroke(Color.white.opacity(0.15), lineWidth: 0.5)
                            )

                        Button {
                            app.attachedImages.removeAll { $0.id == img.id }
                        } label: {
                            Image(systemName: "xmark.circle.fill")
                                .font(.system(size: 13))
                                .foregroundStyle(.white)
                                .background(Circle().fill(Color.black.opacity(0.55)))
                        }
                        .contentShape(Rectangle())
                        .buttonStyle(.plain)
                        .offset(x: 4, y: -4)
                    }
                }

                // File chips
                ForEach(app.attachedFiles, id: \.absoluteString) { url in
                    HStack(spacing: 5) {
                        Image(systemName: FileIcons.icon(for: url))
                            .font(.system(size: 10))
                            .foregroundStyle(FileIcons.color(for: url))
                        Text(url.lastPathComponent)
                            .font(.system(size: 10, design: .monospaced))
                            .lineLimit(1)
                        Button {
                            app.attachedFiles.removeAll { $0 == url }
                        } label: {
                            Image(systemName: "xmark").font(.system(size: 8))
                        }
                        .contentShape(Rectangle())
                        .buttonStyle(.plain)
                    }
                    .foregroundStyle(Color(red: 0.75, green: 0.75, blue: 0.85))
                    .padding(.horizontal, 8).padding(.vertical, 4)
                    .background(
                        RoundedRectangle(cornerRadius: 5)
                            .fill(Color.white.opacity(0.07))
                    )
                }
            }
            .padding(.horizontal, 10).padding(.vertical, 6)
        }
    }

    // MARK: - Drag-and-drop handler

    private func handleDrop(providers: [NSItemProvider]) {
        for provider in providers {
            if provider.hasItemConformingToTypeIdentifier("public.image") {
                _ = provider.loadDataRepresentation(forTypeIdentifier: "public.image") { data, _ in
                    guard let data, let img = AttachmentManager.loadImage(from: data) else { return }
                    Task { @MainActor in
                        guard app.isMultimodalModel else { return }
                        app.attachedImages.append(img)
                    }
                }
            } else if provider.hasItemConformingToTypeIdentifier("public.file-url") {
                _ = provider.loadItem(forTypeIdentifier: "public.file-url") { item, _ in
                    guard let data = item as? Data,
                          let url = URL(dataRepresentation: data, relativeTo: nil) else { return }
                    Task { @MainActor in
                        // If it's an image and model supports multimodal, attach as image
                        let imgExts: Set<String> = ["png","jpg","jpeg","gif","webp","heic","tiff"]
                        if imgExts.contains(url.pathExtension.lowercased()), app.isMultimodalModel,
                           let img = AttachmentManager.loadImage(from: url) {
                            app.attachedImages.append(img)
                        } else {
                            app.attachedFiles.append(url)
                        }
                    }
                }
            }
        }
    }

    // MARK: - Helpers

    /// Extracted from the composer's body on purpose: inline, the surrounding
    /// expression grew past what the type checker will solve in reasonable
    /// time, and adding the growth modifiers tipped it over. Splitting is the
    /// fix SwiftUI actually wants here.
    /// Two things can be typed here and only one of them was ever named.
    /// The field alternates so the second is discoverable without a manual:
    /// a question goes to Vera, and a document wrapped in ⟨verantyx⟩ …
    /// ⟨/verantyx⟩ goes INTO it as that document's vocabulary.
    ///
    /// Five seconds because a hint that changes while you are reading it is
    /// worse than one that never changes. It stops the moment there is text,
    /// which is the existing behaviour and stays.
    private var placeholderRotation: String {
        // <verantyx>タグ投入は廃止(2026-08-19) — 投入は OPERATOR の
        // 文書/分野画面の共通フォームだけ。案内も消す。
        //
        // 服飾の面では用途が違う。**台帳に入れる観測はここからは
        // 入らない** — 入口は右の記録フォームだけ。ここは「もっと丸い
        // 襟にしたい」のような、まだ形になっていない要望を書く場所。
        app.veraEngineMode == .atelier
            ? app.t("Say what you want changed…",
                    "どうしたいかを書く（例: もっと丸い襟に）")
            : app.t("Ask Vera…", "Vera に質問")
    }

    @ViewBuilder
    private var composerTextField: some View {
        ZStack(alignment: .topLeading) {
            if inputText.isEmpty {
                Text(app.selfFixMode
                     ? app.t("Fix this IDE… (Self Fix Mode)", "このIDEを修正… (Self Fix モード)")
                     : (app.selectedFile == nil
                        ? placeholderRotation
                        : app.t("Describe the changes you want…", "Describe the changes you want…")))
                    .font(.system(size: 13))
                    .foregroundStyle(
                        app.selfFixMode
                            ? Color(red: 1.0, green: 0.65, blue: 0.15).opacity(0.55)
                            : Color(red: 0.38, green: 0.38, blue: 0.45)
                    )
                    // Matches NSTextView's default lineFragmentPadding (5) + inset (~6)
                    .padding(.leading, 5)
                    .task(id: placeholderPhase) {
                        try? await Task.sleep(nanoseconds: 5_000_000_000)
                        if !Task.isCancelled { placeholderPhase ^= 1 }
                    }
                    .padding(.top, 6)
                    // No pointer interaction so clicks pass through to TextEditor
                    .allowsHitTesting(false)
            }
            ChatInputTextView(
                text: $inputText,
                onSend: { sendMessage() },
                isFocused: $inputFocused,
                measuredHeight: $composerContentHeight
            )
            // One line to start, growing with the text, and past the
            // cap it stops growing and scrolls instead — the NSScrollView
            // underneath already has its scroller, it was simply never
            // reached because the frame never changed.
            .frame(maxWidth: .infinity,
                   minHeight: composerHeight, maxHeight: composerHeight)
            .animation(.spring(response: 0.24, dampingFraction: 0.9),
                       value: composerHeight)
        }
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
                        .foregroundStyle(app.persistentTaskAnchor.isEmpty ? Color(red: 0.9, green: 0.3, blue: 0.3) : Color.orange)
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
                        : Color(red: 0.5, green: 0.5, blue: 0.55)
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
                    .foregroundStyle(Color(red: 0.5, green: 0.9, blue: 0.6))
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
                            .foregroundStyle(Color(red: 0.5, green: 0.9, blue: 0.6))
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
                                     : Color(red: 0.55, green: 0.55, blue: 0.65))
                    .frame(width: 26, height: 26)
                    .background(
                        app.selfFixMode
                            ? Color(red: 1.0, green: 0.65, blue: 0.15)
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
                    .foregroundStyle(assetVault.isScanning ? Color.gray : Color(red: 0.35, green: 0.75, blue: 0.9))
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

    private var canSend: Bool {
        !inputText.trimmingCharacters(in: .whitespaces).isEmpty
            || !app.attachedImages.isEmpty || !app.attachedFiles.isEmpty
    }

    /// One line at rest, capped before it eats the transcript.
    ///
    /// The floor is a single line rather than the old 44pt minimum, so an empty
    /// composer is as small as it can honestly be. The ceiling is where growth
    /// stops and scrolling starts: past roughly eight lines a taller box stops
    /// helping and starts hiding the conversation it is about.
    private var composerHeight: CGFloat {
        // **服飾の面では入力欄を畳む。** 主役は服の状態で、会話ではない。
        // ただし消さない — 「もっと丸い襟にしたい」のような要望を書く
        // 場所は要る。書き始めれば伸びる。
        let cap: CGFloat = app.veraEngineMode == .atelier ? 76 : 200
        let floor: CGFloat = app.veraEngineMode == .atelier ? 20 : 24
        return min(max(composerContentHeight, floor), cap)
    }

    private func sendMessage() {
        let text = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !app.isGenerating else { return }

        // Typing here while the agent is out driving the screen is allowed,
        // but it is worth one sentence first: the run may not finish. This is
        // a warning, not a lock — the user decides.
        if needsScreenContentionWarning, !confirmScreenContention() { return }

        // Checked BEFORE clearing the box. AppState guards this too, but by
        // then the text is already gone — and a dropped send that also
        // eats what you typed is worse than one that merely says no.
        guard !app.isGenerating else {
            app.addSystemMessage("⏳ 生成中のため送信していません。停止してから送ってください。")
            return
        }
        inputText = ""          // ローカル state を即時クリア（@Published を触る前）
        app.sendMessage(with: text)
    }

    /// True when sending from the Mac would compete with what the agent is
    /// doing on screen, or with the phone relay's own input path.
    private var needsScreenContentionWarning: Bool {
        app.isAgentControllingMouse || ClipboardChatRelay.shared.isRunning
    }

    /// Returns true to go ahead. Named rather than inlined so the reason the
    /// dialog exists stays attached to the text it shows.
    private func confirmScreenContention() -> Bool {
        let relayOn = ClipboardChatRelay.shared.isRunning
        let alert = NSAlert()
        alert.alertStyle = .warning
        alert.messageText = AppLanguage.shared.t(
            "The agent may not finish what it is doing",
            "エージェントが探索を完遂できない可能性があります")

        var reasons: [String] = []
        if app.isAgentControllingMouse {
            reasons.append(AppLanguage.shared.t(
                "• The agent is driving the screen. Typing here brings this window forward, "
                + "and a click meant for the app it is operating can land on the wrong window — "
                + "the run may stop partway.",
                "• エージェントが画面を操作中です。ここへ入力するとこのウィンドウが前面に出るため、"
                + "操作対象のアプリに向けたクリックが別のウィンドウに当たり、途中で探索が止まることがあります。"))
        }
        if relayOn {
            reasons.append(AppLanguage.shared.t(
                "• The phone relay is running. Sending from both sides interleaves two "
                + "conversations into one thread.",
                "• iPhoneリレーが稼働中です。両方から送ると、ひとつの会話に二系統の入力が混ざります。"))
        }
        reasons.append(AppLanguage.shared.t(
            "You can send anyway.", "このまま送信することもできます。"))
        alert.informativeText = reasons.joined(separator: "\n\n")

        alert.addButton(withTitle: AppLanguage.shared.t("Send anyway", "このまま送信"))
        alert.addButton(withTitle: AppLanguage.shared.t("Cancel", "やめる"))
        if relayOn {
            alert.addButton(withTitle: AppLanguage.shared.t("Stop relay and send",
                                                            "リレーを止めて送信"))
        }

        switch alert.runModal() {
        case .alertFirstButtonReturn:
            return true
        case .alertThirdButtonReturn:
            ClipboardChatRelay.shared.stop()
            return true
        default:
            return false
        }
    }

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
    var isFocused: FocusState<Bool>.Binding
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
            parent.isFocused.wrappedValue = true
        }

        func textDidEndEditing(_ notification: Notification) {
            parent.isFocused.wrappedValue = false
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
