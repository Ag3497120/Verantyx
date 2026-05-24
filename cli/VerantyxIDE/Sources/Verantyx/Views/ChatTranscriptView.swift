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
        return sv
    }

    func updateNSView(_ sv: NSScrollView, context: Context) {
        let co = context.coordinator
        guard let tv = sv.documentView as? NSTextView else { return }

        // メッセージが変化していなければスキップ
        let newCount   = messages.count
        let newTail    = messages.last?.content
        let newGen     = isGenerating
        guard co.lastCount != newCount || co.lastTail != newTail || co.lastGen != newGen
        else { return }
        co.lastCount = newCount
        co.lastTail  = newTail
        co.lastGen   = newGen

        // 更新前にスクロール位置とテキスト選択を保存
        let wasAtBottom   = co.isAtBottom(sv)
        let savedSel      = tv.selectedRange()

        // 全文再構築（NSAttributedString の組み立ては SwiftUI layout より高速）
        let attrStr = Transcript.build(messages: messages, isGenerating: isGenerating)
        tv.textStorage?.beginEditing()
        tv.textStorage?.setAttributedString(attrStr)
        tv.textStorage?.endEditing()
        
        // Force immediate layout and display to prevent text from disappearing until scroll/hover
        tv.needsLayout = true
        tv.needsDisplay = true
        if let layoutManager = tv.layoutManager, let textContainer = tv.textContainer {
            layoutManager.ensureLayout(for: textContainer)
        }

        // 選択範囲を復元（末尾が伸びても start 位置は有効なことが多い）
        if savedSel.location != NSNotFound {
            let len      = tv.textStorage?.length ?? 0
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
    final class Coordinator {
        weak var textView:   NSTextView?
        weak var scrollView: NSScrollView?
        var lastCount: Int    = -1
        var lastTail:  String? = nil
        var lastGen:   Bool    = false

        /// スクロールが末尾から 60pt 以内なら "末尾にいる" と判定
        func isAtBottom(_ sv: NSScrollView) -> Bool {
            guard let clip = sv.contentView as? NSClipView,
                  let doc  = sv.documentView else { return true }
            return doc.frame.maxY - clip.bounds.maxY < 60
        }
    }
}

// MARK: - SelectableTextView (NSTextView subclass)
private final class SelectableTextView: NSTextView {
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
}

// MARK: - Palette (アプリのダークテーマに合わせた色定数)
private enum Palette {
    static let bg       = NSColor(calibratedRed: 0.13, green: 0.13, blue: 0.16, alpha: 1)
    static let userText = NSColor(calibratedRed: 0.88, green: 0.88, blue: 0.92, alpha: 1)
    static let assiText = NSColor(calibratedRed: 0.85, green: 0.85, blue: 0.90, alpha: 1)
    static let sysText  = NSColor(calibratedRed: 0.45, green: 0.45, blue: 0.60, alpha: 1)
    static let thinkText = NSColor(calibratedRed: 0.35, green: 0.85, blue: 0.80, alpha: 1)
    static let userLabel = NSColor(calibratedRed: 0.55, green: 0.55, blue: 0.70, alpha: 1)
    static let assiLabel = NSColor(calibratedRed: 0.50, green: 0.70, blue: 1.00, alpha: 1)
    static let genText   = NSColor(calibratedRed: 0.50, green: 0.70, blue: 1.00, alpha: 0.65)
}

// MARK: - Transcript (NSAttributedString ビルダー)
private enum Transcript {

    // 静的 Regex（1 回だけコンパイル）
    private static let thinkRegex = try? NSRegularExpression(pattern: #"<think>([\s\S]*?)</think>"#)
    private static let boldRegex  = try? NSRegularExpression(pattern: #"\*\*(.+?)\*\*"#)

    // ─────────────────────────────────────────────────────────────
    static func build(messages: [ChatMessage], isGenerating: Bool) -> NSAttributedString {
        let result = NSMutableAttributedString()
        for (i, msg) in messages.enumerated() {
            if i > 0 { result.append(str("\n\n")) }
            switch msg.role {
            case .user:      appendUser(result, msg.content)
            case .assistant: appendAssistant(result, msg.content)
            case .system:    appendSystem(result, msg.content)
            }
        }
        // 生成中のUIはSwiftUI側でフローティング表示するため、ここでのテキスト追加は行わない
        return result
    }

    // ─────────────────────────────────────────────────────────────
    // ユーザーメッセージ
    private static func appendUser(_ r: NSMutableAttributedString, _ content: String) {
        let lp = para(spacing: 3)
        r.append(NSAttributedString(string: "You",
            attributes: [.font: NSFont.systemFont(ofSize: 10, weight: .semibold),
                         .foregroundColor: Palette.userLabel,
                         .paragraphStyle: lp]))
        r.append(str("\n"))

        let cp = para(lineSpacing: 2)
        r.append(NSAttributedString(string: content,
            attributes: [.font: NSFont.systemFont(ofSize: 13),
                         .foregroundColor: Palette.userText,
                         .paragraphStyle: cp]))
    }

    // ─────────────────────────────────────────────────────────────
    // アシスタントメッセージ（<think> タグ対応 + **bold** マークダウン）
    private static func appendAssistant(_ r: NSMutableAttributedString, _ content: String) {
        let lp = para(spacing: 3)
        r.append(NSAttributedString(string: "Verantyx",
            attributes: [.font: NSFont.systemFont(ofSize: 10, weight: .semibold),
                         .foregroundColor: Palette.assiLabel,
                         .paragraphStyle: lp]))
        r.append(str("\n"))

        let cp = para(lineSpacing: 2)

        for part in parseThink(content) {
            if part.isThink {
                let tp = para(lineSpacing: 3)
                r.append(NSAttributedString(string: part.text,
                    attributes: [.font: NSFont.monospacedSystemFont(ofSize: 11, weight: .regular),
                                 .foregroundColor: Palette.thinkText,
                                 .paragraphStyle: tp]))
            } else if !part.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                appendBold(r, text: part.text,
                           font: NSFont.systemFont(ofSize: 13),
                           color: Palette.assiText, para: cp)
            }
        }
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
                    bd[.font] = NSFontManager.shared.convert(font, toHaveTrait: .boldFontMask)
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
        guard let url = URL(string: "file:///Users/motonishikoudai/verantyx-cli/VerantyxIDE/Sources/Verantyx/Views/mp_.mp4") else { return nil }
        let spinner = VideoSpinnerView(videoURL: url, speed: 2.7)
            .frame(width: 16, height: 16)
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
