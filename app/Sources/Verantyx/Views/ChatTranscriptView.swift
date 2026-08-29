import SwiftUI
import AppKit

// MARK: - ChatTranscriptView
//
// NSTextView ベースのチャットレンダラー。
// SwiftUI の LazyVStack+ForEach では各バブルが独立した Text なので
// バブルをまたぐドラッグ選択ができない。
// NSTextView は単一テキストストレージのため、ユーザー/アシスタント/システム
// メッセージを越えてマウスドラッグで連続選択・コピーができる。

struct ChatTranscriptView: NSViewRepresentable {
    let messages: [ChatMessage]
    let isGenerating: Bool

    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeNSView(context: Context) -> NSScrollView {
        let tv = SelectableTextView()
        tv.isEditable           = false
        tv.isSelectable         = true
        tv.isRichText           = true
        tv.drawsBackground      = true
        // Match the SwiftUI shell exactly. A private transcript gray made
        // the chat read as a slab inside another panel and exposed the fixed
        // canvas boundary when the window grew.
        tv.backgroundColor      = Theme.nsPanel2
        tv.textContainerInset   = NSSize(width: 14, height: 14)
        tv.textContainer?.lineFragmentPadding   = 0
        tv.textContainer?.widthTracksTextView   = true
        tv.minSize                              = NSSize(width: 0, height: 0)
        tv.maxSize                              = NSSize(width: CGFloat.greatestFiniteMagnitude, height: CGFloat.greatestFiniteMagnitude)
        tv.isVerticallyResizable                = true
        tv.isHorizontallyResizable              = false
        tv.autoresizingMask                     = [.width]
        tv.delegate = context.coordinator
        // Override NSTextView's default link styling (blue + underline)
        // for the per-message copy links -- otherwise .foregroundColor on
        // those runs gets ignored in favor of the system link color.
        tv.linkTextAttributes = [
            .foregroundColor: Palette.copyLinkColor,
            .underlineStyle: 0,
        ]
        // macOS: cmd+a/cmd+c のデフォルト動作はそのまま使える

        // 添付ビュープロバイダの登録 (動画スピナー用)
        NSTextAttachment.registerViewProviderClass(SpinnerAttachmentViewProvider.self, forFileType: "public.data")

        let sv = NSScrollView()
        sv.documentView        = tv
        sv.hasVerticalScroller = true
        sv.autohidesScrollers  = true
        sv.scrollerStyle       = .overlay
        sv.backgroundColor     = Theme.nsPanel2

        context.coordinator.textView   = tv
        context.coordinator.scrollView = sv
        tv.onCopyIndex = { [weak co = context.coordinator] idx in
            guard let co, idx >= 0, idx < co.currentMessages.count else { return }
            NSPasteboard.general.clearContents()
            NSPasteboard.general.setString(co.currentMessages[idx].content, forType: .string)
        }
        tv.onImageIndex = { [weak co = context.coordinator] messageIndex, attachmentIndex in
            guard let co,
                  messageIndex >= 0, messageIndex < co.currentMessages.count,
                  attachmentIndex >= 0,
                  attachmentIndex < co.currentMessages[messageIndex].attachments.count else { return }
            let attachment = co.currentMessages[messageIndex].attachments[attachmentIndex]
            co.imagePreview.showImage(atPath: attachment.path, title: attachment.name)
        }
        return sv
    }

    func updateNSView(_ sv: NSScrollView, context: Context) {
        let co = context.coordinator
        guard let tv = sv.documentView as? NSTextView, let storage = tv.textStorage else { return }

        // メッセージが変化していなければスキップ
        let newCount   = messages.count
        let newTail    = messages.last?.content
        let newGen     = isGenerating
        let newAttachmentSignature = messages.map { message in
            message.attachments.map {
                "\($0.id.uuidString)|\(String(describing: $0.kind))|\($0.name)|\($0.path)"
            }.joined(separator: "\u{1f}")
        }.joined(separator: "\u{1e}")
        let attachmentsChanged = co.lastAttachmentSignature != newAttachmentSignature
        guard co.lastCount != newCount || co.lastTail != newTail || co.lastGen != newGen || attachmentsChanged
        else { return }

        // 更新前にスクロール位置とテキスト選択を保存
        let wasAtBottom  = co.isAtBottom(sv)
        let savedSel     = tv.selectedRange()
        let hadSelection = savedSel.length > 0

        // ── Incremental update ──────────────────────────────────────────
        // Streaming fires this once per ~40ms-batched token flush
        // (AppState.flushStreamTokenBuffer). Rebuilding the ENTIRE
        // transcript's NSAttributedString + relaying out the whole
        // document on every flush was the actual freeze/lag source, not
        // just an inefficiency -- it's O(transcript length) work
        // competing with scrolling on the main thread, repeated at ~25Hz.
        // Two cheap paths cover the common cases; anything else (message
        // deleted, history compressed, session switch, first render)
        // falls back to the original full rebuild, which stays correct.
        var changedRange: NSRange
        if !attachmentsChanged, newCount == co.lastCount, newCount > 0 {
            // Same message count -- only the tail message's content
            // changed (the streaming case). Replace just that range.
            let tailAttr = Transcript.buildSingle(message: messages[newCount - 1], index: newCount - 1)
            let range = NSRange(location: co.lastMessageStartOffset, length: storage.length - co.lastMessageStartOffset)
            storage.beginEditing()
            storage.replaceCharacters(in: range, with: tailAttr)
            storage.endEditing()
            changedRange = NSRange(location: co.lastMessageStartOffset, length: tailAttr.length)
        } else if !attachmentsChanged, newCount == co.lastCount + 1, co.lastCount >= 0 {
            // Exactly one new message appended -- append, don't rebuild.
            let sep = NSAttributedString(string: "\n\n")
            let newMsgAttr = Transcript.buildSingle(message: messages[newCount - 1], index: newCount - 1)
            let appended = NSMutableAttributedString(attributedString: sep)
            appended.append(newMsgAttr)
            let insertLoc = storage.length
            storage.beginEditing()
            storage.append(appended)
            storage.endEditing()
            co.lastMessageStartOffset = insertLoc + sep.length
            changedRange = NSRange(location: insertLoc, length: appended.length)
        } else {
            // Fallback: full rebuild.
            let (attrStr, lastOffset) = Transcript.build(messages: messages, isGenerating: isGenerating)
            storage.beginEditing()
            storage.setAttributedString(attrStr)
            storage.endEditing()
            co.lastMessageStartOffset = lastOffset
            changedRange = NSRange(location: 0, length: storage.length)
        }

        co.lastCount = newCount
        co.lastTail  = newTail
        co.lastGen   = newGen
        co.lastAttachmentSignature = newAttachmentSignature
        co.currentMessages = messages

        tv.needsLayout  = true
        tv.needsDisplay = true
        // Force-layout only the range that actually changed (fixes "text
        // doesn't appear until scroll/hover" without re-typesetting the
        // whole historical transcript on every flush).
        tv.layoutManager?.ensureLayout(forCharacterRange: changedRange)

        // 選択範囲を復元 — 実際に選択(ドラッグ)していた場合のみ。カーソル位置
        // (length == 0) まで毎回復元すると、ストリーミング中の選択操作を
        // 潰してしまう。
        if hadSelection, savedSel.location != NSNotFound {
            let len      = storage.length
            let clampLoc = min(savedSel.location, len)
            let clampLen = min(savedSel.length, len - clampLoc)
            tv.setSelectedRange(NSRange(location: clampLoc, length: clampLen))
        }

        // 末尾にいた場合のみ自動スクロール
        if wasAtBottom {
            DispatchQueue.main.async {
                tv.scrollToEndOfDocument(nil)
                sv.reflectScrolledClipView(sv.contentView)
            }
        }
    }

    // MARK: - Coordinator
    final class Coordinator: NSObject, NSTextViewDelegate {
        weak var textView:   NSTextView?
        weak var scrollView: NSScrollView?
        var lastCount: Int    = -1
        var lastTail:  String? = nil
        var lastGen:   Bool    = false
        var lastAttachmentSignature = ""
        /// Snapshot of the messages currently rendered, indexed the same
        /// way as the "verantyx-copy://<index>" links Transcript.build()
        /// embeds -- lets the per-message copy link know what to copy
        /// without re-deriving it from the NSAttributedString.
        var currentMessages: [ChatMessage] = []
        /// Character offset where the last rendered message's content
        /// begins in the text storage (right after its "\n\n" separator).
        /// Lets updateNSView replace/append just that message instead of
        /// rebuilding the whole document on every streaming flush.
        var lastMessageStartOffset: Int = 0
        fileprivate let imagePreview = ImagePreviewPanelController()

        /// スクロールが末尾から 60pt 以内なら "末尾にいる" と判定
        func isAtBottom(_ sv: NSScrollView) -> Bool {
            let clip = sv.contentView
            guard let doc = sv.documentView else { return true }
            return doc.frame.maxY - clip.bounds.maxY < 60
        }

        /// Per-message "コピー" link click handler (see Transcript.build's
        /// appended copy links). Custom "verantyx-copy://<index>" scheme,
        /// never a real URL that should be opened.
        func textView(_ textView: NSTextView, clickedOnLink link: Any, at charIndex: Int) -> Bool {
            guard let url = (link as? URL) ?? (link as? String).flatMap(URL.init(string:)) else {
                return false
            }
            switch url.scheme {
            case "verantyx-copy":
                guard let idx = url.host.flatMap(Int.init),
                      idx >= 0, idx < currentMessages.count else { return false }
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(currentMessages[idx].content, forType: .string)
                return true
            case "verantyx-image":
                guard let messageIndex = url.host.flatMap(Int.init),
                      let attachmentIndex = url.pathComponents.last.flatMap(Int.init),
                      messageIndex >= 0, messageIndex < currentMessages.count,
                      attachmentIndex >= 0,
                      attachmentIndex < currentMessages[messageIndex].attachments.count else { return false }
                let attachment = currentMessages[messageIndex].attachments[attachmentIndex]
                imagePreview.showImage(atPath: attachment.path, title: attachment.name)
                return true
            default:
                return false
            }
        }
    }
}

// MARK: - SelectableTextView (NSTextView subclass)
private final class SelectableTextView: NSTextView {
    /// Called with a message index when the per-message copy link is
    /// clicked. Handled HERE via a mouseDown hit-test rather than through
    /// `textView(_:clickedOnLink:at:)` — the delegate route silently never
    /// fired for the custom scheme (which is why the button "existed but
    /// did nothing"), and a hit-test cannot be opted out of by AppKit.
    var onCopyIndex: ((Int) -> Void)?
    var onImageIndex: ((Int, Int) -> Void)?

    private enum PendingAction: Equatable {
        case copy(Int)
        case image(message: Int, attachment: Int)
    }
    private var pendingAction: PendingAction?
    private var pendingActionPoint: NSPoint?

    override func mouseDown(with event: NSEvent) {
        let pt = convert(event.locationInWindow, from: nil)
        pendingAction = action(at: pt)
        pendingActionPoint = pendingAction == nil ? nil : pt
        // Do not consume mouseDown. NSTextView must receive the ordinary
        // event stream so a drag that begins on/near an icon can still grow
        // into a selection spanning multiple messages.
        super.mouseDown(with: event)
    }

    // コンテキストメニューから "Copy" だけに絞る (オプション)
    override func menu(for event: NSEvent) -> NSMenu? {
        let m = NSMenu()
        let copy = NSMenuItem(title: "コピー", action: #selector(copy(_:)), keyEquivalent: "c")
        copy.keyEquivalentModifierMask = .command
        m.addItem(copy)
        let all = NSMenuItem(title: "すべて選択", action: #selector(selectAll(_:)), keyEquivalent: "a")
        all.keyEquivalentModifierMask = .command
        m.addItem(all)
        return m
    }
    
    override func mouseUp(with event: NSEvent) {
        let pt = convert(event.locationInWindow, from: nil)
        let downAction = pendingAction
        let downPoint = pendingActionPoint
        pendingAction = nil
        pendingActionPoint = nil

        if let downAction,
           downAction == action(at: pt),
           let downPoint,
           hypot(pt.x - downPoint.x, pt.y - downPoint.y) < 4 {
            switch downAction {
            case .copy(let index):
                onCopyIndex?(index)
                NSSound(named: "Tink")?.play()
            case .image(let message, let attachment):
                onImageIndex?(message, attachment)
            }
            return
        }
        super.mouseUp(with: event)
        // If it's a simple click (no text selection)
        if self.selectedRange().length == 0 {
            NotificationCenter.default.post(name: NSNotification.Name("ChatTranscriptClicked"), object: nil)
        }
    }

    private func action(at point: NSPoint) -> PendingAction? {
        guard let lm = layoutManager, let tc = textContainer else { return nil }
        let adjusted = NSPoint(x: point.x - textContainerInset.width,
                               y: point.y - textContainerInset.height)
        let idx = lm.characterIndex(for: adjusted, in: tc,
                                    fractionOfDistanceBetweenInsertionPoints: nil)
        guard idx < (textStorage?.length ?? 0),
              let raw = textStorage?.attribute(.link, at: idx, effectiveRange: nil),
              let url = (raw as? URL) ?? (raw as? String).flatMap(URL.init(string:)) else {
            return nil
        }
        switch url.scheme {
        case "verantyx-copy":
            return url.host.flatMap(Int.init).map(PendingAction.copy)
        case "verantyx-image":
            guard let message = url.host.flatMap(Int.init),
                  let attachment = url.pathComponents.last.flatMap(Int.init) else { return nil }
            return .image(message: message, attachment: attachment)
        default:
            return nil
        }
    }
}

// MARK: - In-app image enlargement
/// Owns a reusable, app-local preview panel.  Thumbnails never launch Finder,
/// Preview, or a browser; clicking one keeps the user inside the Atelier flow.
/// An unreadable path is deliberately ignored rather than replaced by a fake
/// placeholder that could be mistaken for the image that was sent.
private final class ImagePreviewPanelController: NSObject {
    private var panel: NSPanel?
    private var imageView: NSImageView?

    func showImage(atPath path: String, title: String) {
        guard FileManager.default.isReadableFile(atPath: path),
              let image = NSImage(contentsOfFile: path) else { return }

        let panel = panel ?? makePanel()
        panel.title = title.isEmpty ? AppLanguage.shared.t("Image", "画像") : title
        imageView?.image = image
        imageView?.setAccessibilityLabel(panel.title)

        let visible = panel.screen?.visibleFrame ?? NSScreen.main?.visibleFrame
        let maxSize = NSSize(width: min(920, (visible?.width ?? 1100) * 0.82),
                             height: min(820, (visible?.height ?? 900) * 0.82))
        let fitted = aspectFit(image.size, inside: maxSize)
        panel.setContentSize(NSSize(width: max(420, fitted.width),
                                    height: max(320, fitted.height)))
        panel.center()
        panel.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    private func makePanel() -> NSPanel {
        let panel = NSPanel(
            contentRect: NSRect(x: 0, y: 0, width: 760, height: 620),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        panel.isReleasedWhenClosed = false
        panel.isFloatingPanel = true
        panel.collectionBehavior = [.fullScreenAuxiliary]
        panel.minSize = NSSize(width: 360, height: 260)
        panel.backgroundColor = Palette.bg

        let imageView = NSImageView()
        imageView.autoresizingMask = [.width, .height]
        imageView.imageScaling = .scaleProportionallyUpOrDown
        imageView.imageAlignment = .alignCenter
        imageView.wantsLayer = true
        imageView.layer?.backgroundColor = Palette.imagePreviewBg.cgColor
        panel.contentView = imageView

        self.imageView = imageView
        self.panel = panel
        return panel
    }

    private func aspectFit(_ size: NSSize, inside bounds: NSSize) -> NSSize {
        guard size.width > 0, size.height > 0 else { return bounds }
        let scale = min(bounds.width / size.width, bounds.height / size.height, 1.0)
        return NSSize(width: size.width * scale, height: size.height * scale)
    }
}

// MARK: - Palette (アプリのダークテーマに合わせた色定数)
private enum Palette {
    static let bg       = NSColor(calibratedRed: 0.13, green: 0.13, blue: 0.16, alpha: 1)
    static let userText = NSColor(calibratedRed: 0.92, green: 0.94, blue: 1.00, alpha: 1)
    static let assiText = NSColor(calibratedRed: 0.85, green: 0.85, blue: 0.90, alpha: 1)
    static let sysText  = NSColor(calibratedRed: 0.45, green: 0.45, blue: 0.60, alpha: 1)
    static let thinkText = NSColor(calibratedRed: 0.35, green: 0.85, blue: 0.80, alpha: 1)
    static let userLabel = NSColor(calibratedRed: 0.55, green: 0.55, blue: 0.70, alpha: 1)
    static let assiLabel = NSColor(calibratedRed: 0.50, green: 0.70, blue: 1.00, alpha: 1)
    static let genText   = NSColor(calibratedRed: 0.50, green: 0.70, blue: 1.00, alpha: 0.65)
    static let userBubbleBg = NSColor(calibratedRed: 0.20, green: 0.21, blue: 0.25, alpha: 1)
    static let copyLinkColor = NSColor(calibratedRed: 0.5, green: 0.55, blue: 0.68, alpha: 0.8)
    static let imagePreviewBg = NSColor(calibratedRed: 0.075, green: 0.078, blue: 0.095, alpha: 1)
}

// MARK: - Transcript (NSAttributedString ビルダー)
private enum Transcript {

    // 静的 Regex（1 回だけコンパイル）
    private static let thinkRegex = try? NSRegularExpression(pattern: #"<think>([\s\S]*?)</think>"#)
    private static let boldRegex  = try? NSRegularExpression(pattern: #"\*\*(.+?)\*\*"#)

    // NSFontManager.shared.convert(_:toHaveTrait:) was being called once
    // per **bold** span on EVERY rebuild (i.e. every streaming flush) --
    // font-descriptor trait matching inside a ~25Hz loop. Memoized since
    // the same handful of (font) inputs recur constantly.
    private static var boldFontCache: [NSFont: NSFont] = [:]
    private static func boldVariant(of font: NSFont) -> NSFont {
        if let cached = boldFontCache[font] { return cached }
        let bold = NSFontManager.shared.convert(font, toHaveTrait: .boldFontMask)
        boldFontCache[font] = bold
        return bold
    }

    // ─────────────────────────────────────────────────────────────
    /// Builds the full transcript. Also returns the character offset
    /// where the LAST message begins, so callers can do incremental
    /// replace/append on subsequent updates instead of rebuilding
    /// everything again (see ChatTranscriptView.updateNSView).
    static func build(messages: [ChatMessage], isGenerating: Bool) -> (attributed: NSAttributedString, lastMessageOffset: Int) {
        let result = NSMutableAttributedString()
        var lastOffset = 0
        for (i, msg) in messages.enumerated() {
            if i > 0 { result.append(str("\n\n")) }
            if i == messages.count - 1 { lastOffset = result.length }
            switch msg.role {
            case .user:      appendUser(result, msg, index: i)
            case .assistant: appendAssistant(result, msg, index: i)
            case .system:    appendSystem(result, msg.content)
            }
        }
        // 生成中のUIはSwiftUI側でフローティング表示するため、ここでのテキスト追加は行わない
        return (result, lastOffset)
    }

    /// Builds just ONE message's attributed content (no leading "\n\n"
    /// separator -- the caller inserts that itself when appending, or
    /// omits it when replacing an existing tail message in place).
    static func buildSingle(message: ChatMessage, index: Int) -> NSAttributedString {
        let result = NSMutableAttributedString()
        switch message.role {
        case .user:      appendUser(result, message, index: index)
        case .assistant: appendAssistant(result, message, index: index)
        case .system:    appendSystem(result, message.content)
        }
        return result
    }

    // ─────────────────────────────────────────────────────────────
    // 各メッセージ末尾のクリック可能なコピーアイコン。
    // "verantyx-copy://<index>" は本物のURLではなく、
    // ChatTranscriptView.Coordinator.textView(_:clickedOnLink:at:) が
    // 拾って該当メッセージの内容をクリップボードにコピーするだけの合図。
    private static func appendCopyIcon(_ r: NSMutableAttributedString, index: Int,
                                       rightAligned: Bool = false) {
        guard let url = URL(string: "verantyx-copy://\(index)") else { return }
        let cp = mutablePara(); cp.paragraphSpacing = 2; cp.lineSpacing = 1
        if rightAligned { cp.alignment = .right }
        r.append(NSAttributedString(string: "\n", attributes: [.paragraphStyle: cp]))
        let iconRun = NSMutableAttributedString()
        if let icon = NSImage(systemSymbolName: "doc.on.doc", accessibilityDescription: AppLanguage.shared.t("Copy", "コピー")) {
            let configured = icon.withSymbolConfiguration(.init(pointSize: 11, weight: .regular)) ?? icon
            let attachment = NSTextAttachment()
            attachment.attachmentCell = NSTextAttachmentCell(imageCell: configured)
            attachment.bounds = NSRect(x: 0, y: -2, width: 13, height: 13)
            iconRun.append(NSAttributedString(attachment: attachment))
        } else {
            iconRun.append(NSAttributedString(string: "⧉", attributes: [.font: NSFont.systemFont(ofSize: 12)]))
        }
        iconRun.addAttributes([
            .foregroundColor: Palette.copyLinkColor,
            .link: url,
            .cursor: NSCursor.pointingHand,
            .paragraphStyle: cp,
            .toolTip: AppLanguage.shared.t("Copy message", "メッセージをコピー"),
        ], range: NSRange(location: 0, length: iconRun.length))
        r.append(iconRun)
    }

    // ─────────────────────────────────────────────────────────────
    // ユーザーメッセージ — NSTextBlock で一つの面として描く。
    // glyph-run の背景色と違い、複数行でも段落ごとのギザギザな矩形に
    // ならず、左マージン 34% / 最大幅 66% の同じブロックを共有する。
    private static func appendUser(_ r: NSMutableAttributedString, _ message: ChatMessage, index: Int) {
        let cp = userBubbleParagraph()
        let content = message.content.trimmingCharacters(in: .whitespacesAndNewlines)
        if !content.isEmpty {
            r.append(NSAttributedString(string: content,
                attributes: [.font: NSFont.systemFont(ofSize: 13),
                             .foregroundColor: Palette.userText,
                             .paragraphStyle: cp]))
        }
        appendImageAttachments(r, message: message, messageIndex: index,
                               paragraph: cp, maxSize: NSSize(width: 280, height: 190))
        // A terminating newline carrying the SAME block closes one coherent
        // bubble before the action row starts.
        r.append(NSAttributedString(string: "\n", attributes: [.paragraphStyle: cp]))
        appendCopyIcon(r, index: index, rightAligned: true)
    }

    // ─────────────────────────────────────────────────────────────
    // アシスタントメッセージ（<think> タグ対応 + **bold** マークダウン）
    private static func appendAssistant(_ r: NSMutableAttributedString, _ message: ChatMessage, index: Int) {
        let lp = para(spacing: 3)
        // The reply reads as a centre column, not a left-hugging block:
        // small symmetric margins, text itself stays natural-aligned —
        // centring the GLYPHS would make prose unreadable.
        r.append(NSAttributedString(string: "Verantyx",
            attributes: [.font: NSFont.systemFont(ofSize: 10, weight: .semibold),
                         .foregroundColor: Palette.assiLabel,
                         .paragraphStyle: lp]))
        r.append(str("\n"))

        let cp = mutablePara()
        cp.lineSpacing = 2
        cp.headIndent = 12
        cp.firstLineHeadIndent = 12
        cp.tailIndent = -12

        for part in parseThink(message.content) {
            let trimmed = part.text.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmed.isEmpty else { continue }
            if part.isThink {
                // Thinking is SHOWN (smaller, teal) — hiding it made a
                // reasoning-only turn look like an empty reply with a save
                // popup on top, which read as "the answer was eaten".
                r.append(NSAttributedString(string: trimmed + "\n",
                    attributes: [.font: NSFont.systemFont(ofSize: 11),
                                 .foregroundColor: Palette.thinkText,
                                 .paragraphStyle: cp]))
            } else {
                appendBold(r, text: part.text,
                           font: NSFont.systemFont(ofSize: 13),
                           color: Palette.assiText, para: cp)
            }
        }
        appendImageAttachments(r, message: message, messageIndex: index,
                               paragraph: cp, maxSize: NSSize(width: 340, height: 220))
        appendCopyIcon(r, index: index)
    }

    // ─────────────────────────────────────────────────────────────
    // Real attachment thumbnails. Missing/unreadable files intentionally
    // produce no thumbnail: presenting a generic stand-in here would make
    // it look as if the application had retained image evidence that it no
    // longer has.
    private static func appendImageAttachments(
        _ r: NSMutableAttributedString,
        message: ChatMessage,
        messageIndex: Int,
        paragraph: NSParagraphStyle,
        maxSize: NSSize
    ) {
        for (attachmentIndex, item) in message.attachments.enumerated() {
            switch item.kind {
            case .file:
                continue
            case .image:
                break
            }
            guard FileManager.default.isReadableFile(atPath: item.path),
                  let source = NSImage(contentsOfFile: item.path),
                  let thumbnail = thumbnail(source, fitting: maxSize),
                  let link = URL(string: "verantyx-image://\(messageIndex)/\(attachmentIndex)") else {
                continue
            }
            if r.length > 0 { r.append(NSAttributedString(string: "\n", attributes: [.paragraphStyle: paragraph])) }
            let attachment = NSTextAttachment()
            attachment.attachmentCell = NSTextAttachmentCell(imageCell: thumbnail)
            attachment.bounds = NSRect(x: 0, y: -3,
                                       width: thumbnail.size.width,
                                       height: thumbnail.size.height)
            let run = NSMutableAttributedString(attachment: attachment)
            run.addAttributes([
                .link: link,
                .cursor: NSCursor.pointingHand,
                .paragraphStyle: paragraph,
                .toolTip: AppLanguage.shared.t("Click to enlarge", "クリックして拡大"),
            ], range: NSRange(location: 0, length: run.length))
            r.append(run)
        }
    }

    private static func thumbnail(_ source: NSImage, fitting bounds: NSSize) -> NSImage? {
        guard source.size.width > 0, source.size.height > 0 else { return nil }
        let scale = min(bounds.width / source.size.width, bounds.height / source.size.height, 1)
        let size = NSSize(width: max(1, source.size.width * scale),
                          height: max(1, source.size.height * scale))
        let image = NSImage(size: size)
        image.lockFocus()
        NSGraphicsContext.current?.imageInterpolation = .high
        source.draw(in: NSRect(origin: .zero, size: size),
                    from: NSRect(origin: .zero, size: source.size),
                    operation: .copy,
                    fraction: 1)
        image.unlockFocus()
        return image
    }

    private static func userBubbleParagraph() -> NSMutableParagraphStyle {
        let table = NSTextTable()
        table.collapsesBorders = true
        let block = NSTextTableBlock(table: table, startingRow: 0, rowSpan: 1,
                                     startingColumn: 0, columnSpan: 1)
        block.backgroundColor = Palette.userBubbleBg
        block.setValue(66, type: .percentageValueType, for: .maximumWidth)
        block.setWidth(34, type: .percentageValueType, for: .margin, edge: .minX)
        block.setWidth(10, type: .absoluteValueType, for: .padding, edge: .minX)
        block.setWidth(10, type: .absoluteValueType, for: .padding, edge: .maxX)
        block.setWidth(8, type: .absoluteValueType, for: .padding, edge: .minY)
        block.setWidth(8, type: .absoluteValueType, for: .padding, edge: .maxY)

        let paragraph = mutablePara()
        paragraph.textBlocks = [block]
        paragraph.alignment = .left
        paragraph.lineSpacing = 2
        paragraph.paragraphSpacing = 0
        return paragraph
    }

    // ─────────────────────────────────────────────────────────────
    // システムメッセージ（長すぎるものは折りたたむ）
    private static func appendSystem(_ r: NSMutableAttributedString, _ content: String) {
        // JCross 記憶注入など極端に長いシステムメッセージは省略
        let display = content.count > 300 ? String(content.prefix(120)) + "…" : content
        let cp = mutablePara(); cp.alignment = .center
        r.append(NSAttributedString(string: display,
            attributes: [.font: NSFont.systemFont(ofSize: 11),
                         .foregroundColor: Palette.sysText,
                         .paragraphStyle: cp]))
    }

    // ─────────────────────────────────────────────────────────────
    // **bold** マークダウン展開
    private static func appendBold(
        _ r: NSMutableAttributedString,
        text: String,
        font: NSFont,
        color: NSColor,
        para: NSParagraphStyle
    ) {
        let base: [NSAttributedString.Key: Any] = [
            .font: font, .foregroundColor: color, .paragraphStyle: para
        ]
        guard let re = boldRegex else { r.append(NSAttributedString(string: text, attributes: base)); return }
        var cursor = text.startIndex
        for m in re.matches(in: text, range: NSRange(text.startIndex..., in: text)) {
            if let fr = Range(m.range, in: text) {
                if fr.lowerBound > cursor {
                    r.append(NSAttributedString(string: String(text[cursor..<fr.lowerBound]), attributes: base))
                }
                if let ir = Range(m.range(at: 1), in: text) {
                    var bd = base
                    bd[.font] = boldVariant(of: font)
                    r.append(NSAttributedString(string: String(text[ir]), attributes: bd))
                }
                cursor = fr.upperBound
            }
        }
        if cursor < text.endIndex {
            r.append(NSAttributedString(string: String(text[cursor...]), attributes: base))
        }
    }

    // ─────────────────────────────────────────────────────────────
    // <think>...</think> パース
    private struct Part { let text: String; let isThink: Bool }
    private static func parseThink(_ text: String) -> [Part] {
        var parts: [Part] = []
        guard let re = thinkRegex else { return [Part(text: text, isThink: false)] }
        var cursor = text.startIndex
        for m in re.matches(in: text, range: NSRange(text.startIndex..., in: text)) {
            if let fr = Range(m.range, in: text) {
                if fr.lowerBound > cursor {
                    parts.append(Part(text: String(text[cursor..<fr.lowerBound]), isThink: false))
                }
                if let ir = Range(m.range(at: 1), in: text) {
                    parts.append(Part(text: String(text[ir]), isThink: true))
                }
                cursor = fr.upperBound
            }
        }
        if cursor < text.endIndex {
            // A still-open <think> (mid-stream) renders as thinking too —
            // otherwise live reasoning shows as raw tagged text until the
            // close tag arrives.
            let tail = String(text[cursor...])
            if let open = tail.range(of: "<think>") {
                let before = String(tail[tail.startIndex..<open.lowerBound])
                if !before.isEmpty { parts.append(Part(text: before, isThink: false)) }
                parts.append(Part(text: String(tail[open.upperBound...]), isThink: true))
            } else {
                parts.append(Part(text: tail, isThink: false))
            }
        }
        return parts.isEmpty ? [Part(text: text, isThink: false)] : parts
    }

    // ─────────────────────────────────────────────────────────────
    // ヘルパー
    private static func str(_ s: String) -> NSAttributedString { NSAttributedString(string: s) }

    private static func mutablePara() -> NSMutableParagraphStyle { NSMutableParagraphStyle() }

    private static func para(spacing: CGFloat = 0, lineSpacing: CGFloat = 0) -> NSParagraphStyle {
        let p = NSMutableParagraphStyle()
        p.paragraphSpacing = spacing
        p.lineSpacing      = lineSpacing
        return p
    }
}

// MARK: - Video Spinner Text Attachment (macOS 12+)
final class SpinnerAttachment: NSTextAttachment {
    override init(data contentData: Data?, ofType uti: String?) {
        super.init(data: contentData, ofType: uti)
    }
    
    required init?(coder: NSCoder) {
        super.init(coder: coder)
    }
}

@available(macOS 12.0, *)
final class SpinnerAttachmentViewProvider: NSTextAttachmentViewProvider {
    // Shared view to ensure continuous playback across NSAttributedString rebuilds
    static let sharedSpinnerView: NSHostingView<AnyView>? = {
        let spinner = ProgressView().controlSize(.small)
        let hostingView = NSHostingView(rootView: AnyView(spinner))
        hostingView.frame = NSRect(x: 0, y: 0, width: 16, height: 16)
        return hostingView
    }()

    override func loadView() {
        if let shared = Self.sharedSpinnerView {
            self.view = shared
        } else {
            self.view = NSView(frame: NSRect(x: 0, y: 0, width: 16, height: 16))
        }
    }
}
