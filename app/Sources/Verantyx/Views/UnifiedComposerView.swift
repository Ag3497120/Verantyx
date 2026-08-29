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
    // AppKit owns the actual first responder. This must be ordinary state so
    // changing it reliably drives ChatInputTextView.updateNSView; FocusState
    // only propagates through SwiftUI's `.focused` modifier chain.
    @State private var inputFocused = false

    /// The composer reads the same state machine as the window edge and the
    /// menu-bar icon, so all three agree by construction.
    @ObservedObject private var activity = AgentActivityCenter.shared
    /// Read-only factory progress used to vary the inference animation.  The
    /// composer never advances this state machine itself.
    @ObservedObject private var factory = GarmentFactoryReactController.shared
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

    /// A closed, deterministic projection of observable engine state. There
    /// is no timer-driven state guessing and no model-authored UI label.
    private var inferenceSpinnerPhase: ComposerInferencePhase {
        if factory.busy {
            let signal = [
                factory.phase,
                factory.lastReport?.verdict ?? "",
                factory.trace.last?.action ?? "",
                factory.trace.last?.verdict ?? "",
            ].joined(separator: " ").uppercased()

            if ["REPAIR", "RETRY", "DIAGNOSE", "MAKE_SEWABLE"].contains(where: { signal.contains($0) }) {
                return .repair
            }
            if ["VALIDAT", "REVIEW", "CANDIDATE", "APPROV", "SIMULATION",
                "PATTERN", "SEWING", "STRENGTH", "COMFORT"].contains(where: { signal.contains($0) }) {
                return .validation
            }
        }

        switch activity.state {
        case .error:
            return .repair
        case .exploring, .operatingApp, .waitingUser:
            return .validation
        default:
            return .analysis
        }
    }

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
            if hasComposerAttachments {
                attachmentStrip
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
                // Keep one composer surface. Self Fix remains legible through
                // its warning icon/text and the outer warning stroke.
                .background(Color.clear)
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
        .overlay(alignment: .topLeading) {
            if app.isGenerating {
                ComposerInferenceSpinner(phase: inferenceSpinnerPhase)
                    .offset(x: 13, y: -27)
                    .transition(.scale(scale: 0.72, anchor: .bottomLeading)
                        .combined(with: .opacity))
            }
        }
        .padding(.horizontal, 16)
        .padding(.bottom, 16)
        // The spinner sits in its own status lane above the text surface and
        // therefore cannot be mistaken for the send control.
        .padding(.top, app.isGenerating ? 34 : 8)
        .animation(.easeInOut(duration: 0.2), value: app.selfFixMode)
        .animation(.easeInOut(duration: 0.18), value: app.isGenerating)
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
        .onReceive(NotificationCenter.default.publisher(
            for: Notification.Name("VerantyxFocusUnifiedComposer")
        )) { _ in
            focusComposerInput()
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
            attachmentControl

            modelSelectorBar
                .layoutPriority(1)

            composerSendButton
        }
    }

    /// Sending is intentionally conventional. The six-arm mark now has one
    /// unambiguous job—showing inference above the composer—while this button
    /// uses the familiar upward arrow and remains separate from stop/cancel.
    private var composerSendButton: some View {
        let enabled = canSend && !app.isGenerating
        return Button {
            guard enabled else { return }
            sendMessage()
        } label: {
            Image(systemName: "arrow.up")
                .font(.system(size: 13, weight: .bold))
                .foregroundStyle(enabled ? Color.white : Theme.faint)
                .frame(width: 30, height: 30)
                .background(
                    Circle().fill(enabled ? Theme.sel : Color.white.opacity(0.07))
                )
                .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .disabled(!enabled)
        .help(app.t("Send", "送信"))
        .accessibilityLabel(app.t("Send message", "メッセージを送信"))
        .accessibilityHint(app.t(
            "Sends the current text and attachments",
            "入力中の文章と添付を送信します"))
    }

    /// Atelier has one attachment concept: the image/video source in the
    /// garment intake ledger.  Showing the generic chat file menu beside it
    /// created two visually identical doors backed by different state; a file
    /// chip could appear while the composer selection remained nil. Other
    /// modes keep the ordinary image/file menu.
    @ViewBuilder
    private var attachmentControl: some View {
        if app.veraEngineMode == .atelier {
            Button(action: attachMedia) {
                Image(systemName: intake.hasComposerAttachment
                      ? "photo.fill" : "photo.badge.plus")
                    .font(.system(size: 15))
                    .foregroundStyle(Theme.sel)
                    .frame(width: 28, height: 28)
            }
            .buttonStyle(.plain)
            // The icon-only SwiftUI button was exposed to Accessibility but
            // macOS skipped it in the keyboard focus chain.  Keep a direct,
            // deterministic route for assistive operation and UI regression
            // tests; the action still enters the one shared intake picker.
            .focusable()
            .keyboardShortcut("i", modifiers: [.command, .shift])
            .disabled(intake.busy)
            .help(app.t("Attach or replace the garment image",
                        "服の画像・動画を添付／変更"))
            .accessibilityLabel(app.t("Attach garment image",
                                      "服の画像を添付"))
        } else {
            JCrossMenu(items: [
                JCrossMenuItem(icon: "photo.badge.plus",
                               title: app.t("Add a photo", "画像を追加")) {
                    attachMedia()
                },
                JCrossMenuItem(icon: "paperclip",
                               title: app.t("Add a file", "ファイルを追加")) {
                    app.attachedFiles.append(contentsOf: AttachmentManager.pickFiles())
                },
            ], japanese: AppLanguage.shared.isJapanese)
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
                if intake.hasComposerAttachment {
                    // Remove stale generic-chat attachments left by the old
                    // two-door UI. The garment ledger is the sole source now.
                    app.attachedImages.removeAll()
                    app.attachedFiles.removeAll()
                    focusComposerInput()
                }
            }
        } else {
            app.attachedImages.append(contentsOf: AttachmentManager.pickImages())
        }
    }

    private func focusComposerInput() {
        // Re-asserting `true` is not an observable FocusState transition when
        // the open panel restored focus elsewhere.  Toggle first, then let the
        // AppKit bridge make the NSTextView first responder on the next pass.
        inputFocused = false
        DispatchQueue.main.async { inputFocused = true }
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
        // No nested toolbar slab: text, attachment, model and send controls
        // all live on the composer's single rounded surface.
        .background(Color.clear)
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
                Text(app.t("Creation model:", "制作モデル:"))
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

    private var hasComposerAttachments: Bool {
        if app.veraEngineMode == .atelier { return intake.hasComposerAttachment }
        return !app.attachedImages.isEmpty || !app.attachedFiles.isEmpty
    }

    private var attachmentStrip: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                if app.veraEngineMode == .atelier,
                   let clip = intake.composerSelectedClip,
                   let image = NSImage(contentsOfFile: clip.path) {
                    ZStack(alignment: .topTrailing) {
                        Image(nsImage: image)
                            .resizable().scaledToFill()
                            .id(intake.selectionRevision)
                            .frame(width: 56, height: 56)
                            .clipShape(RoundedRectangle(cornerRadius: 6))
                            .overlay(RoundedRectangle(cornerRadius: 6)
                                .stroke(Theme.sel.opacity(0.5), lineWidth: 1))
                        Button { intake.clearComposerSelection() } label: {
                            Image(systemName: "xmark.circle.fill")
                                .font(.system(size: 13))
                                .foregroundStyle(.white)
                                .background(Circle().fill(Color.black.opacity(0.55)))
                        }
                        .buttonStyle(.plain)
                        .offset(x: 4, y: -4)
                    }
                }
                if app.veraEngineMode != .atelier {
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
                        if app.veraEngineMode == .atelier {
                            let root = FileManager.default.temporaryDirectory
                                .appendingPathComponent("VerantyxAtelierDrops", isDirectory: true)
                            try? FileManager.default.createDirectory(
                                at: root, withIntermediateDirectories: true)
                            let url = root.appendingPathComponent("\(UUID().uuidString).png")
                            guard (try? data.write(to: url, options: .atomic)) != nil else { return }
                            await intake.ingest(url)
                            app.attachedImages.removeAll()
                            app.attachedFiles.removeAll()
                        } else {
                            guard app.isMultimodalModel else { return }
                            app.attachedImages.append(img)
                        }
                    }
                }
            } else if provider.hasItemConformingToTypeIdentifier("public.file-url") {
                _ = provider.loadItem(forTypeIdentifier: "public.file-url") { item, _ in
                    let url: URL?
                    if let value = item as? URL {
                        url = value
                    } else if let value = item as? NSURL {
                        url = value as URL
                    } else if let data = item as? Data {
                        url = URL(dataRepresentation: data, relativeTo: nil)
                    } else {
                        url = nil
                    }
                    guard let url else { return }
                    Task { @MainActor in
                        let imgExts: Set<String> = ["png","jpg","jpeg","gif","webp","heic","tiff"]
                        let movieExts: Set<String> = ["mp4","mov","m4v","avi","mkv"]
                        if app.veraEngineMode == .atelier,
                           imgExts.union(movieExts).contains(url.pathExtension.lowercased()) {
                            await intake.ingest(url)
                            app.attachedImages.removeAll()
                            app.attachedFiles.removeAll()
                        } else if imgExts.contains(url.pathExtension.lowercased()), app.isMultimodalModel,
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
            || (app.veraEngineMode == .atelier && intake.hasComposerAttachment)
            || (app.veraEngineMode != .atelier
                && (!app.attachedImages.isEmpty || !app.attachedFiles.isEmpty))
    }

    /// One line at rest, capped before it eats whatever is above it.
    private var composerHeight: CGFloat {
        let cap: CGFloat = app.veraEngineMode == .atelier ? 76 : 200
        let floor: CGFloat = app.veraEngineMode == .atelier ? 20 : 24
        return min(max(composerContentHeight, floor), cap)
    }

    private func sendMessage() {
        let typed = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        let text = typed.isEmpty && app.veraEngineMode == .atelier
            && intake.hasComposerAttachment
            ? app.t("Make a garment from this image", "この画像から服を作って")
            : typed
        guard !text.isEmpty, !app.isGenerating else { return }

        if needsScreenContentionWarning, !confirmScreenContention() { return }

        guard !app.isGenerating else {
            app.addSystemMessage("⏳ 生成中のため送信していません。停止してから送ってください。")
            return
        }
        inputText = ""
        app.sendMessage(with: text)

        // Beginner Atelier stays in the existing full-screen Chat tab so the
        // user can watch proposals, retries and typed stops. The Garment tab
        // remains available for the full workbench; sending does not force it.
        app.shell.openTab(.chat)
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

// MARK: - Inference spinner

/// Visual modes are intentionally few and typed. They are a view of the
/// existing ReAct/activity states, not a second workflow state machine.
private enum ComposerInferencePhase: String, Equatable {
    case analysis
    case validation
    case repair

    var tint: Color {
        switch self {
        case .analysis:   return Theme.sel
        case .validation: return Color(red: 0.35, green: 0.85, blue: 1.00)
        case .repair:     return Theme.warn
        }
    }

    var accessibleName: String {
        switch self {
        case .analysis:
            return AppLanguage.shared.t("Analyzing", "分析中")
        case .validation:
            return AppLanguage.shared.t("Validating", "検証中")
        case .repair:
            return AppLanguage.shared.t("Repairing", "修復中")
        }
    }

    /// Same elapsed time and same phase always produce the same pose. This is
    /// deliberately mathematical rather than random so phase changes remain
    /// visually testable and reproducible.
    func pose(at elapsed: TimeInterval) -> (turn: Double, scale: CGFloat, tilt: Double) {
        switch self {
        case .analysis:
            return (0.035 + elapsed / 3.2, 1.0, 0.52)
        case .validation:
            let breath = 1.0 + 0.055 * sin(elapsed * 2.0 * .pi / 1.35)
            return (0.035 + elapsed / 5.0, CGFloat(breath), 0.42)
        case .repair:
            let pulse = 0.94 + 0.10 * abs(sin(elapsed * 2.0 * .pi / 0.72))
            return (0.035 - elapsed / 1.8, CGFloat(pulse), 0.68)
        }
    }
}

/// A six-arm, projected 3D cross. It is only rendered by the composer while
/// `AppState.isGenerating` is true; it has no button action and cannot send.
private struct ComposerInferenceSpinner: View {
    let phase: ComposerInferencePhase

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var phaseStartedAt = Date()

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 30.0, paused: reduceMotion)) { timeline in
            let elapsed = reduceMotion
                ? 0
                : max(0, timeline.date.timeIntervalSince(phaseStartedAt))
            let pose = phase.pose(at: elapsed)

            JCrossGlyph(
                phase: pose.turn,
                tint: phase.tint,
                tilt: pose.tilt,
                thickness: 1.8
            )
            .frame(width: 18, height: 18)
            .scaleEffect(pose.scale)
            .padding(4)
            .background(Circle().fill(Color.black.opacity(0.22)))
            .overlay(Circle().stroke(phase.tint.opacity(0.38), lineWidth: 0.6))
        }
        .frame(width: 26, height: 26)
        .onChange(of: phase) { _, _ in phaseStartedAt = Date() }
        .help(phase.accessibleName)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(AppLanguage.shared.t("Vera inference", "Vera 推論"))
        .accessibilityValue(phase.accessibleName)
    }
}
