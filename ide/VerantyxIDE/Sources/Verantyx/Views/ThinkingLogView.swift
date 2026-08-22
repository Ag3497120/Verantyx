import SwiftUI
import AppKit

// MARK: - ThinkingLogView
// Raw process log — shows exactly what the AI is doing right now.
// This is the "brain exposure" panel. Hacker aesthetic: terminal-style, no decoration.
// Inspired by htop / gdb output. Every line tells a story.

struct ThinkingLogView: View {
    @EnvironmentObject var app: AppState
    @State private var autoScroll = true

    var body: some View {
        VStack(spacing: 0) {
            // ── Header ─────────────────────────────────────────────
            HStack(spacing: 8) {
                // Pulsing dot when active
                if app.isGenerating {
                    Circle()
                        .fill(Color(red: 0.3, green: 1.0, blue: 0.5))
                        .frame(width: 6, height: 6)
                        .opacity(0.9)
                }

                Text("PROCESS LOG")
                    .font(.system(size: 10, weight: .semibold, design: .monospaced))
                    .foregroundStyle(Color(red: 0.5, green: 0.9, blue: 0.6))

                if app.isGenerating {
                    Text("● LIVE")
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(Color(red: 0.3, green: 1.0, blue: 0.5))
                }

                Spacer()

                // tok/s inline
                if app.tokensPerSecond > 0 {
                    Text(String(format: "%.1f tok/s", app.tokensPerSecond))
                        .font(.system(size: 10, weight: .bold, design: .monospaced))
                        .foregroundStyle(tpsColor)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 1)
                        .background(tpsColor.opacity(0.12), in: RoundedRectangle(cornerRadius: 3))
                }

                Button {
                    autoScroll.toggle()
                } label: {
                    Image(systemName: autoScroll ? "arrow.down.to.line" : "arrow.down.to.line.compact")
                        .font(.system(size: 10))
                        .foregroundStyle(autoScroll ? .green : .secondary)
                }
                .contentShape(Rectangle())
                .buttonStyle(.plain)

                Button {
                    app.clearProcessLog()
                } label: {
                    Image(systemName: "trash")
                        .font(.system(size: 10))
                        .foregroundStyle(.secondary)
                }
                .contentShape(Rectangle())
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 5)
            .background(Color(red: 0.08, green: 0.10, blue: 0.12))

            Divider().opacity(0.3)

            // ── Log body (NSTextView — 行をまたいだドラッグ選択が可能) ──
            ProcessLogTranscriptView(entries: app.logStore.entries, autoScroll: autoScroll)
        }
        .background(Color(red: 0.06, green: 0.08, blue: 0.10))
    }

    private var tpsColor: Color {
        app.tokensPerSecond > 20
            ? Color(red: 0.3, green: 1.0, blue: 0.4)
            : app.tokensPerSecond > 5
                ? Color(red: 1.0, green: 0.8, blue: 0.2)
                : Color(red: 0.6, green: 0.6, blue: 0.6)
    }
}

// MARK: - ProcessLogTranscriptView
// NSTextView ベースの統合ログビュー。
// LazyVStack+ForEach だと各行が独立して行をまたぐドラッグ選択不可だったため置き換え。

private struct ProcessLogTranscriptView: NSViewRepresentable {
    let entries: [AppState.ProcessLogEntry]
    let autoScroll: Bool

    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeNSView(context: Context) -> NSScrollView {
        let tv = LogTextView()
        tv.isEditable           = false
        tv.isSelectable         = true
        tv.isRichText           = true
        tv.drawsBackground      = true
        tv.backgroundColor      = NSColor(calibratedRed: 0.06, green: 0.08, blue: 0.10, alpha: 1)
        tv.textContainerInset   = NSSize(width: 6, height: 4)
        tv.textContainer?.lineFragmentPadding   = 0
        tv.textContainer?.widthTracksTextView   = true
        tv.isVerticallyResizable                = true
        tv.isHorizontallyResizable              = false
        tv.autoresizingMask                     = [.width]

        let sv = NSScrollView()
        sv.documentView        = tv
        sv.hasVerticalScroller  = true
        sv.autohidesScrollers   = true
        sv.scrollerStyle        = .overlay
        sv.backgroundColor      = NSColor(calibratedRed: 0.06, green: 0.08, blue: 0.10, alpha: 1)

        context.coordinator.textView   = tv
        context.coordinator.scrollView = sv
        return sv
    }

    func updateNSView(_ sv: NSScrollView, context: Context) {
        let co = context.coordinator
        guard let tv = sv.documentView as? NSTextView else { return }

        // エントリ数が変わっていなければスキップ
        guard co.lastCount != entries.count else { return }
        co.lastCount = entries.count

        let wasAtBottom = co.isAtBottom(sv)
        let savedSel    = tv.selectedRange()

        let attrStr = LogBuilder.build(entries: entries)
        tv.textStorage?.beginEditing()
        tv.textStorage?.setAttributedString(attrStr)
        tv.textStorage?.endEditing()

        // 選択範囲を復元
        if savedSel.location != NSNotFound {
            let len      = tv.textStorage?.length ?? 0
            let clampLoc = min(savedSel.location, len)
            let clampLen = min(savedSel.length, len - clampLoc)
            tv.setSelectedRange(NSRange(location: clampLoc, length: clampLen))
        }

        // autoScroll が ON かつ末尾にいた場合のみスクロール
        if autoScroll && wasAtBottom {
            DispatchQueue.main.async { tv.scrollToEndOfDocument(nil) }
        }
    }

    // MARK: Coordinator
    final class Coordinator {
        weak var textView:   NSTextView?
        weak var scrollView: NSScrollView?
        var lastCount: Int = -1

        func isAtBottom(_ sv: NSScrollView) -> Bool {
            guard let clip = sv.contentView as? NSClipView,
                  let doc  = sv.documentView else { return true }
            return doc.frame.maxY - clip.bounds.maxY < 40
        }
    }
}

// MARK: - LogTextView (コンテキストメニュー限定)
private final class LogTextView: NSTextView {
    override func menu(for event: NSEvent) -> NSMenu? {
        let m = NSMenu()
        m.addItem(NSMenuItem(title: "コピー",       action: #selector(copy(_:)),      keyEquivalent: "c"))
        m.addItem(NSMenuItem(title: "すべて選択",   action: #selector(selectAll(_:)), keyEquivalent: "a"))
        m.items.forEach { $0.keyEquivalentModifierMask = .command }
        return m
    }
}

// MARK: - LogBuilder (NSAttributedString ビルダー)
private enum LogBuilder {
    private static let timeFmt: DateFormatter = {
        let f = DateFormatter(); f.dateFormat = "HH:mm:ss.SSS"; return f
    }()

    // フォント
    private static let monoFont    = NSFont.monospacedSystemFont(ofSize: 9, weight: .regular)
    private static let monoSemi    = NSFont.monospacedSystemFont(ofSize: 9, weight: .semibold)

    // 色
    private static let tsColor     = NSColor(calibratedRed: 0.40, green: 0.40, blue: 0.50, alpha: 1)
    private static let bodyColor   = NSColor(calibratedRed: 0.85, green: 0.85, blue: 0.90, alpha: 1)
    private static let perfColor   = NSColor(calibratedRed: 0.30, green: 1.00, blue: 0.50, alpha: 1)

    // kind → NSColor マップ
    private static func kindColor(_ kind: AppState.ProcessLogEntry.Kind) -> NSColor {
        switch kind {
        case .memory:   return NSColor(calibratedRed: 0.40, green: 0.90, blue: 0.60, alpha: 1)
        case .tool:     return NSColor(calibratedRed: 0.40, green: 0.80, blue: 1.00, alpha: 1)
        case .browser:  return NSColor(calibratedRed: 0.90, green: 0.70, blue: 0.30, alpha: 1)
        case .thinking: return NSColor(calibratedRed: 0.80, green: 0.80, blue: 1.00, alpha: 1)
        case .system:   return NSColor(calibratedRed: 0.60, green: 0.60, blue: 0.60, alpha: 1)
        case .perf:     return NSColor(calibratedRed: 0.30, green: 1.00, blue: 0.50, alpha: 1)
        }
    }

    static func build(entries: [AppState.ProcessLogEntry]) -> NSAttributedString {
        let result = NSMutableAttributedString()
        let linePara = NSMutableParagraphStyle()
        linePara.lineSpacing = 1

        for (i, e) in entries.enumerated() {
            if i > 0 { result.append(NSAttributedString(string: "\n")) }

            // Timestamp
            result.append(NSAttributedString(
                string: timeFmt.string(from: e.timestamp) + "  ",
                attributes: [.font: monoFont, .foregroundColor: tsColor, .paragraphStyle: linePara]
            ))

            // Prefix (kind badge)
            result.append(NSAttributedString(
                string: e.prefix + "  ",
                attributes: [.font: monoSemi, .foregroundColor: kindColor(e.kind), .paragraphStyle: linePara]
            ))

            // Content
            let textColor: NSColor = e.kind == .perf ? perfColor : bodyColor
            result.append(NSAttributedString(
                string: e.text,
                attributes: [.font: monoFont, .foregroundColor: textColor, .paragraphStyle: linePara]
            ))
        }
        return result
    }
}

// MARK: - ThinkingLogView extension helpers

extension AppState {
    /// Emit a log entry from browser operations, JCross hits, etc.
    func logMemoryHit(_ nodeId: String, summary: String) {
        logProcess("\(nodeId)  \(summary)", kind: .memory)
    }

    func logBrowser(_ action: String, url: String) {
        logProcess("\(action)  \(url)", kind: .browser)
    }

    func logThinking(_ excerpt: String) {
        // Only show first 120 chars of thinking to avoid log spam
        logProcess(String(excerpt.prefix(120)), kind: .thinking)
    }
}
