import SwiftUI
import AppKit

// MARK: - CodeView
// Scrollable code viewer with line numbers.
//
// ⚠️ 設計上の制約 (フリーズ回避のため厳守):
//
//   [禁止1] fixedSize(horizontal: true) — 全行一括レイアウト → swift_retain SIGTRAP
//   [禁止2] NSTextView + per-line AttributedString build — NSCoreTypesetter が
//            全行のラインメトリクスをメインスレッドで同期計算 → SIGTERM デッドロック
//   [禁止3] setAttributedString() に巨大な NSMutableAttributedString を渡す
//
//   [採用] NSTextView に plain string を直接設定 + 全体にまとめて属性付与
//          これにより Typesetter は1回のパスで済み、同期ブロックが発生しない。
//   [採用] allowsNonContiguousLayout = true で表示可能部分だけを先にレイアウト
//   [採用] コンテンツは 80,000 文字でキャップ（約 2,000〜3,000 行相当）

struct CodeView: View {
    let content: String
    let language: SyntaxHighlighter.Language
    var showLineNumbers: Bool = true
    var highlightLines: Set<Int> = []

    var body: some View {
        SafeCodeTextView(content: content, showLineNumbers: showLineNumbers)
            .transaction { t in t.animation = nil }
    }
}

// MARK: - SafeCodeTextView
// NSViewRepresentable — plain text + global attributes only (no per-line NSAttributedString)

struct SafeCodeTextView: NSViewRepresentable {
    let content: String
    var showLineNumbers: Bool

    // コンテンツ上限: 80,000文字を超えると NSTypesetter が同期で全行計算してフリーズする
    private static let maxChars = 80_000

    func makeNSView(context: Context) -> NSScrollView {
        let scrollView = NSTextView.scrollableTextView()
        guard let tv = scrollView.documentView as? NSTextView else { return scrollView }

        // ── 横スクロール有効化 ─────────────────────────────────────────
        tv.isHorizontallyResizable = true
        tv.isVerticallyResizable   = true
        tv.autoresizingMask        = [.width]
        tv.textContainer?.widthTracksTextView = false
        tv.textContainer?.containerSize = CGSize(
            width:  CGFloat.greatestFiniteMagnitude,
            height: CGFloat.greatestFiniteMagnitude
        )

        // ── 非連続レイアウト: 表示領域だけを優先レイアウト ─────────────
        // これがないと setString() 後に全行をメインスレッドで同期レイアウトしてフリーズ
        tv.layoutManager?.allowsNonContiguousLayout = true
        tv.layoutManager?.backgroundLayoutEnabled   = true

        // ── 基本設定 ────────────────────────────────────────────────
        tv.isEditable   = false
        tv.isSelectable = true
        tv.usesFontPanel = false
        tv.usesFindPanel = false
        tv.backgroundColor = NSColor(red: 0.08, green: 0.08, blue: 0.11, alpha: 1)
        tv.textContainerInset = NSSize(width: 8, height: 8)

        context.coordinator.textView = tv
        Self.applyContent(to: tv, content: content, showLineNumbers: showLineNumbers)
        return scrollView
    }

    func updateNSView(_ scrollView: NSScrollView, context: Context) {
        guard let tv = context.coordinator.textView else { return }
        // 内容が同じなら何もしない（震え防止）
        let preview = String(content.prefix(100))
        guard context.coordinator.lastPreview != preview else { return }
        context.coordinator.lastPreview = preview
        Self.applyContent(to: tv, content: content, showLineNumbers: showLineNumbers)
    }

    func makeCoordinator() -> Coordinator { Coordinator() }

    // MARK: - Content Application (メインスレッド安全)

    private static func applyContent(to tv: NSTextView, content: String, showLineNumbers: Bool) {
        let monoFont = NSFont.monospacedSystemFont(ofSize: 11, weight: .regular)
        let textColor = NSColor(red: 0.82, green: 0.82, blue: 0.88, alpha: 1)
        let lineNumColor = NSColor(red: 0.38, green: 0.38, blue: 0.48, alpha: 1)

        // ── コンテンツをキャップ ──────────────────────────────────────
        let capped: String
        if content.count > maxChars {
            capped = String(content.prefix(maxChars)) +
                     "\n\n... (先頭 \(maxChars/1000)K文字を表示。残りは省略されています)"
        } else {
            capped = content
        }

        // インデント（タブ）を空白に変換して、行番号追加時にレイアウトが崩れないようにする
        let safeCapped = capped.replacingOccurrences(of: "\t", with: "    ")

        // ── 行番号付きプレーンテキスト構築 ────────────────────────────
        let plainText: String
        if showLineNumbers {
            let rawLines = safeCapped.components(separatedBy: "\n")
            let width = max(2, String(rawLines.count).count)
            plainText = rawLines.enumerated()
                .map { (i, line) in String(format: "%\(width)d  ", i + 1) + line }
                .joined(separator: "\n")
        } else {
            plainText = safeCapped
        }

        // ── テキスト設定 ────────────────────────────────
        // NSTextViewの string プロパティを使って安全に設定する
        tv.string = plainText
        guard let storage = tv.textStorage else { return }

        // 属性をバッチで適用
        storage.beginEditing()
        let fullRange = NSRange(location: 0, length: storage.length)

        // 全体属性（フォントとコードの文字色）
        storage.addAttributes([
            .font: monoFont,
            .foregroundColor: textColor
        ], range: fullRange)

        // 行番号部分のみ薄い色を適用
        if showLineNumbers {
            let rawLines = plainText.components(separatedBy: "\n")
            let numWidth = max(2, String(rawLines.count).count) + 2  // +2 for "  " separator
            var pos = 0
            for line in rawLines {
                let numLen = min(numWidth, line.count)
                if numLen > 0 {
                    storage.addAttribute(.foregroundColor, value: lineNumColor,
                                        range: NSRange(location: pos, length: numLen))
                }
                pos += line.count + 1  // +1 for \n
            }
        }

        storage.endEditing()
    }

    // MARK: - Coordinator
    final class Coordinator {
        var textView: NSTextView? // strong — weak causes swift_unknownObjectWeakCopyInit spin
        var lastPreview: String = ""
    }
}

// MARK: - RawTextView
// Plain text scrollable view — used for FileTreeView preview and FilePaneView Raw mode.

struct RawTextView: NSViewRepresentable {
    let content: String

    private static let maxChars = 80_000

    func makeNSView(context: Context) -> NSScrollView {
        let scrollView = NSTextView.scrollableTextView()
        guard let tv = scrollView.documentView as? NSTextView else { return scrollView }

        tv.isHorizontallyResizable = true
        tv.isVerticallyResizable   = true
        tv.textContainer?.widthTracksTextView = false
        tv.textContainer?.containerSize = CGSize(
            width: CGFloat.greatestFiniteMagnitude,
            height: CGFloat.greatestFiniteMagnitude
        )
        tv.layoutManager?.allowsNonContiguousLayout = true
        tv.layoutManager?.backgroundLayoutEnabled   = true
        tv.isEditable   = false
        tv.isSelectable = true
        tv.usesFontPanel = false
        tv.font         = NSFont.monospacedSystemFont(ofSize: 11, weight: .regular)
        tv.textColor    = NSColor(red: 0.82, green: 0.82, blue: 0.88, alpha: 1)
        tv.backgroundColor = NSColor(red: 0.07, green: 0.07, blue: 0.10, alpha: 1)
        tv.textContainerInset = NSSize(width: 8, height: 8)

        context.coordinator.textView = tv
        Self.setText(tv, content: content)
        return scrollView
    }

    func updateNSView(_ scrollView: NSScrollView, context: Context) {
        guard let tv = context.coordinator.textView else { return }
        let preview = String(content.prefix(100))
        guard context.coordinator.lastPreview != preview else { return }
        context.coordinator.lastPreview = preview
        Self.setText(tv, content: content)
    }

    func makeCoordinator() -> Coordinator { Coordinator() }

    private static func setText(_ tv: NSTextView, content: String) {
        let text = content.count > maxChars
            ? String(content.prefix(maxChars)) + "\n\n... (先頭 \(maxChars/1000)K文字を表示)"
            : content
        // tv.string = は内部で setAttributedString を呼ばず直接バッファに書き込む
        // Typesetter は allowsNonContiguousLayout のおかげで表示領域だけ計算する
        tv.string = text
    }

    final class Coordinator {
        var textView: NSTextView? // strong — weak causes swift_unknownObjectWeakCopyInit spin
        var lastPreview: String = ""
    }
}

// MARK: - FilePaneView

struct FilePaneView: View {
    @EnvironmentObject var app: AppState
    @ObservedObject var gatekeeper = GatekeeperModeState.shared
    @State private var viewMode: ViewMode = .code

    enum ViewMode: String, CaseIterable {
        case code = "Code"
        case raw  = "Raw"
    }

    var body: some View {
        if let file = app.selectedFile, !app.selectedFileContent.isEmpty {
            VStack(spacing: 0) {
                HStack {
                    Image(systemName: "doc.text.fill")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text(file.lastPathComponent)
                        .font(.system(.caption, design: .monospaced))
                        .fontWeight(.medium)
                    Spacer()

                    if gatekeeper.isEnabled {
                        Picker("Gatekeeper View", selection: $app.showGatekeeperRawCode) {
                            Text("JCross IR").tag(false)
                            Text("Source File").tag(true)
                        }
                        .pickerStyle(.segmented)
                        .labelsHidden()
                        .frame(width: 150)

                        Divider().frame(height: 16).padding(.horizontal, 4)
                    }

                    Picker("", selection: $viewMode) {
                        ForEach(ViewMode.allCases, id: \.self) { m in
                            Text(m.rawValue).tag(m)
                        }
                    }
                    .pickerStyle(.segmented)
                    .frame(width: 120)

                    Button {
                        app.selectedFile = nil
                        app.selectedFileContent = ""
                    } label: {
                        Image(systemName: "xmark").font(.caption2)
                    }
                    .contentShape(Rectangle())
                    .buttonStyle(.plain)
                    .foregroundStyle(.secondary)
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(Color(nsColor: .controlBackgroundColor))

                Divider()

                switch viewMode {
                case .code:
                    let lang: SyntaxHighlighter.Language = (gatekeeper.isEnabled && !app.showGatekeeperRawCode)
                        ? .jcross
                        : SyntaxHighlighter.language(for: file)
                    CodeView(content: app.selectedFileContent, language: lang)
                case .raw:
                    RawTextView(content: app.selectedFileContent)
                        .transaction { t in t.animation = nil }
                }
            }
        }
    }
}
