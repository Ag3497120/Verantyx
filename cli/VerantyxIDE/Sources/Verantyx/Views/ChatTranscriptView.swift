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
        tv.backgroundColor      = Palette.bg
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
        sv.backgroundColor     = Palette.bg

        context.coordinator.textView   = tv
        context.coordinator.scrollView = sv
        tv.onCopyIndex = { [weak co = context.coordinator] idx in
            guard let co, idx >= 0, idx < co.currentMessages.count else { return }
            NSPasteboard.general.clearContents()
            NSPasteboard.general.setString(co.currentMessages[idx].content, forType: .string)
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
        guard co.lastCount != newCount || co.lastTail != newTail || co.lastGen != newGen
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
        if newCount == co.lastCount, newCount > 0 {
            // Same message count -- only the tail message's content
            // changed (the streaming case). Replace just that range.
            let tailAttr = Transcript.buildSingle(message: messages[newCount - 1], index: newCount - 1)
            let range = NSRange(location: co.lastMessageStartOffset, length: storage.length - co.lastMessageStartOffset)
            storage.beginEditing()
            storage.replaceCharacters(in: range, with: tailAttr)
            storage.endEditing()
            changedRange = NSRange(location: co.lastMessageStartOffset, length: tailAttr.length)
        } else if newCount == co.lastCount + 1, co.lastCount >= 0 {
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

        /// スクロールが末尾から 60pt 以内なら "末尾にいる" と判定
        func isAtBottom(_ sv: NSScrollView) -> Bool {
            guard let clip = sv.contentView as? NSClipView,
                  let doc  = sv.documentView else { return true }
            return doc.frame.maxY - clip.bounds.maxY < 60
        }

        /// Per-message "コピー" link click handler (see Transcript.build's
        /// appended copy links). Custom "verantyx-copy://<index>" scheme,
        /// never a real URL that should be opened.
        func textView(_ textView: NSTextView, clickedOnLink link: Any, at charIndex: Int) -> Bool {
            let indexString: String?
            if let url = link as? URL, url.scheme == "verantyx-copy" {
                indexString = url.host
            } else if let s = link as? String, s.hasPrefix("verantyx-copy://") {
                indexString = String(s.dropFirst("verantyx-copy://".count))
            } else {
                indexString = nil
            }
            guard let idxStr = indexString, let idx = Int(idxStr),
                  idx >= 0, idx < currentMessages.count else { return false }
            NSPasteboard.general.clearContents()
            NSPasteboard.general.setString(currentMessages[idx].content, forType: .string)
            return true
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

    /// Set when mouseDown consumed the click as a copy-button press, so the
    /// paired mouseUp doesn't also announce a "transcript clicked" event —
    /// that notification opened the Spotlight prompt on every copy.
    private var consumedAsCopyPress = false

    override func mouseDown(with event: NSEvent) {
        let pt = convert(event.locationInWindow, from: nil)
        if let lm = layoutManager, let tc = textContainer {
            let adjusted = NSPoint(x: pt.x - textContainerInset.width,
                                   y: pt.y - textContainerInset.height)
            let idx = lm.characterIndex(for: adjusted, in: tc,
                                        fractionOfDistanceBetweenInsertionPoints: nil)
            if idx < (textStorage?.length ?? 0),
               let link = textStorage?.attribute(.link, at: idx, effectiveRange: nil),
               let url = link as? URL, url.scheme == "verantyx-copy",
               let n = url.host.flatMap(Int.init) {
                onCopyIndex?(n)
                consumedAsCopyPress = true
                // Brief visual receipt: flash the link run.
                NSSound(named: "Tink")?.play()
                return   // consume; no selection change for a button press
            }
        }
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
        if consumedAsCopyPress {
            consumedAsCopyPress = false
            return   // copy-button press: copy already happened, nothing else
        }
        super.mouseUp(with: event)
        // If it's a simple click (no text selection)
        if self.selectedRange().length == 0 {
            NotificationCenter.default.post(name: NSNotification.Name("ChatTranscriptClicked"), object: nil)
        }
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
    /// User-message "bubble" — NSAttributedString's .backgroundColor draws
    /// a filled rect behind each line's glyphs. Not a rounded SwiftUI
    /// bubble (this is plain-text NSTextView rendering, not SwiftUI), but
    /// a real, visible fill distinguishing user from assistant text,
    /// which is what was actually missing (see the file header comment
    /// on why this view exists instead of SwiftUI per-message views).
    static let userBubbleBg = NSColor(calibratedRed: 0.2, green: 0.35, blue: 0.7, alpha: 1)
    static let copyLinkColor = NSColor(calibratedRed: 0.5, green: 0.55, blue: 0.68, alpha: 0.8)
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
            case .user:      appendUser(result, msg.content, index: i)
            case .assistant: appendAssistant(result, msg.content, index: i)
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
        case .user:      appendUser(result, message.content, index: index)
        case .assistant: appendAssistant(result, message.content, index: index)
        case .system:    appendSystem(result, message.content)
        }
        return result
    }

    // ─────────────────────────────────────────────────────────────
    // 各メッセージ末尾のクリック可能な「コピー」リンク。
    // "verantyx-copy://<index>" は本物のURLではなく、
    // ChatTranscriptView.Coordinator.textView(_:clickedOnLink:at:) が
    // 拾って該当メッセージの内容をクリップボードにコピーするだけの合図。
    private static func appendCopyLink(_ r: NSMutableAttributedString, index: Int,
                                       rightAligned: Bool = false) {
        guard let url = URL(string: "verantyx-copy://\(index)") else { return }
        let cp = mutablePara(); cp.paragraphSpacing = 2
        if rightAligned { cp.alignment = .right }
        r.append(NSAttributedString(string: "\n", attributes: [.paragraphStyle: cp]))
        r.append(NSAttributedString(
            string: AppLanguage.shared.t("copy", "コピー"),
            attributes: [.font: NSFont.systemFont(ofSize: 10),
                         .foregroundColor: Palette.copyLinkColor,
                         .link: url,
                         .cursor: NSCursor.pointingHand,
                         .paragraphStyle: cp]))
    }

    // ─────────────────────────────────────────────────────────────
    // ユーザーメッセージ — 右揃えの「囲い」。Claude/ChatGPT の作法:
    // 人間の発言は右に寄った塗り付きの塊、AI の答えは中央のカラム。
    // NSTextView では alignment .right + 左側の大きな headIndent が
    // その形になる(塗りは従来どおり .backgroundColor が行の字形の
    // 背後に矩形を描く)。
    private static func appendUser(_ r: NSMutableAttributedString, _ content: String, index: Int) {
        let lp = mutablePara(); lp.alignment = .right; lp.paragraphSpacing = 3
        r.append(NSAttributedString(string: "You",
            attributes: [.font: NSFont.systemFont(ofSize: 10, weight: .semibold),
                         .foregroundColor: Palette.userLabel,
                         .paragraphStyle: lp]))
        r.append(NSAttributedString(string: "\n", attributes: [.paragraphStyle: lp]))

        let cp = mutablePara()
        cp.alignment = .right
        cp.lineSpacing = 2
        // The indent is what keeps a long user message from becoming a
        // full-width right-aligned wall: it can only occupy the right
        // two-thirds, like a bubble.
        cp.headIndent = 90
        cp.firstLineHeadIndent = 90
        r.append(NSAttributedString(string: " \(content) ",
            attributes: [.font: NSFont.systemFont(ofSize: 13),
                         .foregroundColor: Palette.userText,
                         .backgroundColor: Palette.userBubbleBg,
                         .paragraphStyle: cp]))
        appendCopyLink(r, index: index, rightAligned: true)
    }

    // ─────────────────────────────────────────────────────────────
    // アシスタントメッセージ（<think> タグ対応 + **bold** マークダウン）
    private static func appendAssistant(_ r: NSMutableAttributedString, _ content: String, index: Int) {
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

        for part in parseThink(content) {
            if part.isThink {
                // HIDE think blocks in the IDE view per user request
                continue
            } else if !part.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                appendBold(r, text: part.text,
                           font: NSFont.systemFont(ofSize: 13),
                           color: Palette.assiText, para: cp)
            }
        }
        appendCopyLink(r, index: index)
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
        if cursor < text.endIndex { parts.append(Part(text: String(text[cursor...]), isThink: false)) }
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
