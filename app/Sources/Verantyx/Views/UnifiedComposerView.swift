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

    private var runningGlowColor: Color { activity.state.color }
    private var runningGlowActive: Bool { activity.state.glows }

    var body: some View {
        composerBox
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
                composerTextField
                composerControls
            }
            .padding(.horizontal, 11).padding(.top, 8).padding(.bottom, 7)
        }
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
    /// 自動/手動 execution-mode stepper. Vera model mode used to hide this
    /// too — no LLM ever entered that turn — but that mode was removed
    /// 2026-08-26, so the only remaining reason to hide the bar is Atelier.
    private var modelSelectorBar: some View {
        HStack(spacing: 8) {
            if app.veraEngineMode != .atelier {
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
