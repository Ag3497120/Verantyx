import SwiftUI

// MARK: - UnifiedComposerView
//
// The pinned bottom bar is gone. This is the one composer for the whole
// app — extracted out of AgentChatView, where it used to live as a
// `VStack` row bolted to the bottom of whatever pane AgentChatView
// happened to be filling. Because that pane was, in most layouts, the
// entire window, the composer read as pinned to the window frame even
// though the code never said "window": nothing else could ever be small
// enough to reveal that it was actually the LAST row of one particular
// view.
//
// IDEShellView owns where this renders now: below the active tab's
// content when something is open, and as the entire centre when nothing
// is — "in the minimal view, this composer IS the app" (owner's words).
// AgentChatView keeps a thin call-through (`showsOwnComposer`) so the two
// older embeds that still expect a self-contained chat pane (SwarmMonitorView's
// side-by-side agents, the dormant AIModeLayoutView) do not lose their input
// — but there is exactly one implementation, here.
//
// Text box + attach live inside ONE bordered container, not two side-by-side
// controls — that part of the ask is real. What this does NOT do is put the
// attach/model/send row INSIDE the text line itself: `modelSelectorBar`'s own
// comment records that being tried once already and losing — the controls
// competed with the text for the same row and won, stealing width the typed
// text needed. So the merge here is "one box, one border, one identity, text
// on top / tools below" rather than "icons inside the caret line". Changing
// that shape again would be re-running an experiment this codebase already
// has the scar tissue for.
//
// Capped at `composerMaxWidth`, centred — not full-pane. A line of typed
// text a window's whole width wide is unreadable no matter what is in it.
//
// In Atelier mode this is a GARMENT composer, not a general chat box, and
// says so before anyone types: `atelierScopeBlock` names the open garment
// and offers example instructions that map 1:1 onto real MCP tools
// (`photoloset/mcp.py`), and `analystChip` replaces the LLM-backend picker
// with the SAME "which model proposes" control AtelierView's rail already
// has (`AtelierAnalyst.shared`) — one decision, shown in two places, never
// two competing ones.
struct UnifiedComposerView: View {
    @EnvironmentObject var app: AppState

    @State private var inputText: String = ""
    /// 0 = 「Vera に質問」, 1 = 「もっと丸い襟に」 style rotating hint.
    @State private var placeholderPhase: Int = 0
    /// Laid-out height of the input's content, reported back from AppKit.
    @State private var composerContentHeight: CGFloat = 0
    @State private var glowPulse: Bool = false
    @FocusState private var inputFocused: Bool

    /// The composer reads the same state machine as the window edge and the
    /// menu-bar icon, so all three agree by construction.
    @ObservedObject private var activity = AgentActivityCenter.shared
    /// The garment ledger's own intake path — reused here rather than a
    /// second "attach a clip" implementation. `AtelierIntake.shared` is the
    /// same instance AtelierView reads its clip list from, so a photo or
    /// clip attached from the composer shows up there immediately.
    @ObservedObject private var intake = AtelierIntake.shared
    /// Which model reads the garment and proposes — the SAME object
    /// AtelierView's rail ("ANALYSIS AI") reads, so this chip and that
    /// picker can never disagree. See `AtelierAnalyst.shared`.
    @ObservedObject private var an = AtelierAnalyst.shared
    /// The garment's name, for the scope chip. See `AtelierContext`.
    @ObservedObject private var atelierCtx = AtelierContext.shared
    @State private var showAnalyst = false

    private var runningGlowColor: Color { activity.state.color }
    private var runningGlowActive: Bool { activity.state.glows }

    /// Half of "spans the entire pane", roughly, and centred rather than
    /// pinned — a CAP, not a fixed size, so a narrow window still just
    /// gets whatever width it has. 820 keeps a line of typed text at a
    /// readable measure the way the reference app (Claude desktop) does.
    private let composerMaxWidth: CGFloat = 820

    var body: some View {
        composerBox
            .sheet(isPresented: $showAnalyst) {
                // `m: nil` — the composer has no ledger to run "ask about
                // open aspects" against, only a model to pick. See the
                // doc comment on `AnalystSheet.m`.
                AnalystSheet(an: an, m: nil).environmentObject(app)
            }
    }

    // MARK: - Placeholder

    private var placeholderRotation: String {
        app.veraEngineMode == .atelier
            ? app.t("Say what you want changed…",
                    "どうしたいかを書く（例: もっと丸い襟に）")
            : app.t("Ask Vera…", "Vera に質問")
    }

    // MARK: - Box

    private var composerBox: some View {
        VStack(spacing: 0) {
            // ── Attachment preview strip ──────────────────────────────
            if !app.attachedImages.isEmpty || !app.attachedFiles.isEmpty {
                attachmentStrip
                Divider().opacity(0.3)
            }

            // ── IDE Fix mode banner / normal file badge ───────────────
            if app.selfFixMode {
                HStack(spacing: 8) {
                    Image(systemName: "lock.fill")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(Theme.warn)

                    Text("🔧 IDE Fix Mode")
                        .font(.system(size: 11, weight: .bold, design: .monospaced))
                        .foregroundStyle(Theme.warn)

                    if let file = app.selectedFile {
                        Text("▸ \(file.lastPathComponent)")
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(Theme.warn.opacity(0.8))
                            .lineLimit(1)
                            .truncationMode(.middle)
                    } else {
                        Text("▸ IDE Source Index")
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(Theme.warn.opacity(0.8))
                    }

                    Spacer()

                    Button {
                        app.selfFixMode = false
                    } label: {
                        HStack(spacing: 4) {
                            Image(systemName: "xmark")
                                .font(.system(size: 9, weight: .bold))
                            Text(app.t("Exit Mode", "モード終了"))
                                .font(.system(size: 10, weight: .semibold))
                        }
                        .foregroundStyle(Theme.warn)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 3)
                        .background(
                            RoundedRectangle(cornerRadius: 4)
                                .stroke(Theme.warn.opacity(0.5), lineWidth: 1)
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
                        .fill(Theme.warn.opacity(0.6))
                        .frame(height: 1),
                    alignment: .bottom
                )
            }

            // ── Text input + action buttons ───────────────────────────
            VStack(alignment: .leading, spacing: 6) {
                // Scope, shown BEFORE the caret has anywhere to type —
                // see the file's own header note on why a plain text box
                // here reads as a general assistant it is not.
                if app.veraEngineMode == .atelier { atelierScopeBlock }
                composerTextField
                composerControls
            }
            .padding(.horizontal, 11).padding(.top, 8).padding(.bottom, 7)
        }
        .frame(maxWidth: composerMaxWidth)
        .background(
            app.selfFixMode
                ? Color(red: 0.22, green: 0.16, blue: 0.08)
                : Color(red: 0.17, green: 0.17, blue: 0.21),
            in: RoundedRectangle(cornerRadius: 16, style: .continuous)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(runningGlowActive
                        ? runningGlowColor.opacity(glowPulse ? 0.95 : 0.35)
                        : (app.selfFixMode
                           ? Theme.warn.opacity(0.8)
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
        .onDrop(of: [.image, .fileURL], isTargeted: nil) { providers in
            handleDrop(providers: providers)
            return true
        }
    }

    // MARK: - Text field

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
                            ? Theme.warn.opacity(0.55)
                            : Theme.faint
                    )
                    .padding(.leading, 5)
                    .task(id: placeholderPhase) {
                        try? await Task.sleep(nanoseconds: 5_000_000_000)
                        if !Task.isCancelled { placeholderPhase ^= 1 }
                    }
                    .padding(.top, 6)
                    .allowsHitTesting(false)
            }
            ChatInputTextView(
                text: $inputText,
                onSend: { sendMessage() },
                isFocused: $inputFocused,
                measuredHeight: $composerContentHeight
            )
            .frame(maxWidth: .infinity,
                   minHeight: composerHeight, maxHeight: composerHeight)
            .animation(.spring(response: 0.24, dampingFraction: 0.9),
                       value: composerHeight)
        }
    }

    /// Attach + model + send — one row, BELOW the text (see the file
    /// header comment for why not inline).
    private var composerControls: some View {
        HStack(spacing: 7) {
            JCrossMenu(items: [
                JCrossMenuItem(icon: "photo.badge.plus",
                               title: app.t("Add a photo or clip", "写真・動画を追加")) {
                    attachMedia()
                },
                JCrossMenuItem(icon: "paperclip",
                               title: app.t("Add a file", "ファイルを追加")) {
                    app.attachedFiles.append(contentsOf: AttachmentManager.pickFiles())
                },
            ], japanese: AppLanguage.shared.isJapanese)

            modelSelectorBar
                .layoutPriority(1)

            JCrossSendButton(enabled: canSend) { sendMessage() }
        }
    }

    /// In Atelier mode a "photo/clip" attach means intake into the garment
    /// ledger (split into frames, offered to a vision model) — the SAME
    /// path AtelierView's own intake button drives, via the shared
    /// `AtelierIntake` instance, not a copy of its NSOpenPanel + register
    /// + split sequence. Everywhere else it is the ordinary chat attachment.
    private func attachMedia() {
        if app.veraEngineMode == .atelier {
            Task {
                await intake.pickAndIngest()
                // 送っていないのに服の面が開くのは早すぎる —
                // 取り込みが終わってから開く。
                await MainActor.run { app.shell.openTab(.garment) }
            }
        } else {
            app.attachedImages.append(contentsOf: AttachmentManager.pickImages())
        }
    }

    /// ModelSelectorBarView is entirely about LLM backends: which one is
    /// loaded (Gatekeeper chip), the 監視(Auditor)/ERROR badge, the
    /// 自動/手動 execution-mode stepper. None of that is a question Atelier
    /// mode asks — Atelier does not hide this row, it REPLACES it with
    /// `analystChip`, a control over a different, garment-specific
    /// question: which model reads the garment and proposes. The two
    /// never show at once, so they never compete over the row's width the
    /// way the file header's comment warns about for inline placement.
    private var modelSelectorBar: some View {
        HStack(spacing: 8) {
            if app.veraEngineMode == .atelier {
                analystChip
            } else {
                ModelSelectorBarView()
            }

            Spacer()

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
                            .fill(Theme.bad)
                    )
                    .contentShape(Rectangle())
                }
                .contentShape(Rectangle())
                .buttonStyle(.plain)
                .transition(.scale.combined(with: .opacity))
            }
        }
        .padding(.horizontal, 10).padding(.vertical, 4)
        .background(Theme.panel2)
        .animation(.easeInOut(duration: 0.15), value: app.isGenerating)
    }

    /// Opens the SAME `AnalystSheet` AtelierView's rail opens, bound to the
    /// SAME `AtelierAnalyst.shared` — "agree with it rather than compete",
    /// in the owner's words. Nothing here decides which model reads the
    /// garment a second time; it only shows and re-opens the one decision
    /// that already exists.
    private var analystChip: some View {
        Button { showAnalyst = true } label: {
            HStack(spacing: 5) {
                Image(systemName: "sparkles").font(.system(size: 9))
                Text(app.t("Analysis AI:", "解析AI:"))
                    .font(.system(size: 10))
                    .foregroundStyle(Theme.faint)
                Text(an.pick.label)
                    .font(.system(size: 10, weight: .semibold))
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
            .foregroundStyle(Theme.dim)
        }
        .buttonStyle(.plain)
        .help(app.t("Whatever it says only reaches a PROPOSAL — a person "
                    + "still has to adopt it under their name.",
                    "何を言っても届くのは提案の欄だけです。事実になるのは"
                    + "人が名前を書いて採用したときだけです。"))
    }

    // MARK: - Atelier scope block
    //
    // 服飾用のチャット入力欄は特に別のことを聞くことにならないように —
    // プレーンな文字入力欄は一般アシスタントに見え、範囲を知らないまま
    // 打たれる。範囲を**打つ前に**見せる: どの服の話か(スコープの chip)、
    // この欄が実際に運べる指示の**形**(実在する道具に対応する例文)、
    // そして番号で場所を指せること自体が、これを普通のチャットと分けて
    // いるという点。例文はどちらも photoloset/mcp.py の実在するツール
    // (garment_adjust による番号区間の調整、garment_worklist の未確認
    // 一覧)に対応していて、この engine が出来ないことは書いていない。

    @ViewBuilder
    private var atelierScopeBlock: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                Image(systemName: "tshirt").font(.system(size: 9))
                Text(app.t("This is about:", "この欄が指すのは:"))
                    .font(.system(size: 10))
                Text(atelierCtx.projectName.isEmpty
                     ? app.t("the open garment", "開いている服")
                     : atelierCtx.projectName)
                    .font(.system(size: 10, weight: .semibold))
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
            .foregroundStyle(Theme.sel)
            .padding(.horizontal, 8).padding(.vertical, 3)
            .background(Capsule().fill(Theme.sel.opacity(0.16)))

            // Real instructions this composer can carry — each one names
            // a shape an actual MCP tool answers, not a capability made
            // up for the demo. Tapping fills the box; it does not send,
            // because a control that fires a real turn on a single tap
            // is a worse surprise than a blank text field.
            HStack(spacing: 6) {
                exampleChip(app.t("Loosen 30 to 35 a little",
                                  "30番から35番をもう少しゆとりに"))
                exampleChip(app.t("What haven't we confirmed yet?",
                                  "まだ確認できていないのは？"))
            }
        }
        .padding(.bottom, 2)
    }

    private func exampleChip(_ text: String) -> some View {
        Button {
            inputText = text
            inputFocused = true
        } label: {
            Text(text)
                .font(.system(size: 10))
                .lineLimit(1)
                .foregroundStyle(Theme.dim)
                .padding(.horizontal, 8).padding(.vertical, 4)
                .background(Capsule().fill(Color.white.opacity(0.06)))
                .overlay(Capsule().stroke(Color.white.opacity(0.10), lineWidth: 0.5))
        }
        .buttonStyle(.plain)
    }

    // MARK: - Attachment strip

    private var attachmentStrip: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
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

    // MARK: - Sending

    private var canSend: Bool {
        !inputText.trimmingCharacters(in: .whitespaces).isEmpty
            || !app.attachedImages.isEmpty || !app.attachedFiles.isEmpty
    }

    /// One line at rest, capped before it eats whatever is above it.
    private var composerHeight: CGFloat {
        let cap: CGFloat = app.veraEngineMode == .atelier ? 76 : 200
        let floor: CGFloat = app.veraEngineMode == .atelier ? 20 : 24
        return min(max(composerContentHeight, floor), cap)
    }

    private func sendMessage() {
        let text = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !app.isGenerating else { return }

        if needsScreenContentionWarning, !confirmScreenContention() { return }

        guard !app.isGenerating else {
            app.addSystemMessage("⏳ 生成中のため送信していません。停止してから送ってください。")
            return
        }
        inputText = ""
        app.sendMessage(with: text)

        // 「送って、返ってきたものはタブで開く」 — 何が返るかはモードで
        // 決まる: 服飾なら服の状態、それ以外は会話。
        app.shell.openTab(app.veraEngineMode == .atelier ? .garment : .chat)
    }

    private var needsScreenContentionWarning: Bool {
        app.isAgentControllingMouse || ClipboardChatRelay.shared.isRunning
    }

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
}
