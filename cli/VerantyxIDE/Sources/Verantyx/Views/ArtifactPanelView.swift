import SwiftUI
import WebKit

// MARK: - ArtifactPanelView
// Right-side Artifact Panel — Claude-style live preview of HTML/Mermaid/Markdown/SVG/Code.
// In AI Priority mode this replaces the SideBySideDiffView entirely.

struct ArtifactPanelView: View {
    @EnvironmentObject var app: AppState

    enum DisplayTab: String, CaseIterable {
        case preview = "Preview"
        case code    = "Code"
        case diff    = "Diff"
    }

    @State private var activeTab: DisplayTab = .preview
    @State private var copyState: Bool = false

    var body: some View {
        VStack(spacing: 0) {
            panelHeader

            Divider().opacity(0.3)

            switch activeTab {
            case .preview:
                artifactPreview
            case .code:
                codeView
            case .diff:
                // Hand off to the existing diff view — must pass EnvironmentObject
                SideBySideDiffView()
                    .environmentObject(app)
            }
        }
        .background(Color(red: 0.10, green: 0.10, blue: 0.13))
        .onChange(of: app.currentArtifact?.id) { _, _ in
            // Auto-switch tab when a new artifact arrives
            guard let art = app.currentArtifact else { return }
            withAnimation(.easeInOut(duration: 0.15)) {
                activeTab = art.type == .code ? .code : .preview
            }
        }
        // Bug-fix: watch Optional<FileDiff> directly rather than `pendingDiff != nil`.
        // The Bool expression evaluated outside the closure could read a stale value
        // when AI Priority mode clears pendingDiff synchronously.
        .onChange(of: app.pendingDiff) { _, newDiff in
            if newDiff != nil {
                withAnimation(.easeInOut(duration: 0.15)) { activeTab = .diff }
            }
        }
    }

    // MARK: - Header

    private var panelHeader: some View {
        HStack(spacing: 0) {
            if let art = app.currentArtifact {
                Image(systemName: art.type.icon)
                    .font(.system(size: 10))
                    .foregroundStyle(typeColor(art.type))
                    .padding(.trailing, 5)
                Text(art.title)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Color(red: 0.88, green: 0.88, blue: 0.94))
                    .lineLimit(1)
                Spacer(minLength: 8)
            } else {
                Image(systemName: "rectangle.on.rectangle")
                    .font(.system(size: 10))
                    .foregroundStyle(.secondary)
                Text("Artifact")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(.secondary)
                Spacer()
            }

            tabSwitcher

            Spacer(minLength: 8)

            if app.currentArtifact != nil {
                Button {
                    if let code = app.currentArtifact?.content {
                        NSPasteboard.general.clearContents()
                        NSPasteboard.general.setString(code, forType: .string)
                        withAnimation { copyState = true }
                        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
                            withAnimation { copyState = false }
                        }
                    }
                } label: {
                    Image(systemName: copyState ? "checkmark" : "doc.on.doc")
                        .font(.system(size: 10))
                        .foregroundStyle(copyState
                                         ? Color(red: 0.3, green: 0.9, blue: 0.5)
                                         : Color(red: 0.55, green: 0.55, blue: 0.65))
                }
                .contentShape(Rectangle())
                .buttonStyle(.plain)
                .padding(.trailing, 6)
            }

            historyMenu
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 7)
        .background(Color(red: 0.13, green: 0.13, blue: 0.17))
    }

    private var tabSwitcher: some View {
        HStack(spacing: 0) {
            ForEach(availableTabs, id: \.rawValue) { tab in
                Button {
                    withAnimation(.easeInOut(duration: 0.12)) { activeTab = tab }
                } label: {
                    HStack(spacing: 4) {
                        Text(tab.rawValue)
                            .font(.system(size: 11, weight: activeTab == tab ? .semibold : .regular))
                            .foregroundStyle(activeTab == tab ? .white : Color(red: 0.5, green: 0.5, blue: 0.62))
                        if tab == .diff, let diff = app.pendingDiff, diff.hasChanges {
                            ZStack {
                                Circle()
                                    .fill(Color(red: 1.0, green: 0.65, blue: 0.2))
                                    .frame(width: 6, height: 6)
                            }
                        }
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 5)
                    .background(activeTab == tab ? Color.white.opacity(0.08) : Color.clear)
                    .overlay(
                        Rectangle()
                            .fill(activeTab == tab ? tabAccent(tab) : Color.clear)
                            .frame(height: 1.5),
                        alignment: .bottom
                    )
                }
                .contentShape(Rectangle())
                .buttonStyle(.plain)
            }
        }
        .background(Color(red: 0.16, green: 0.16, blue: 0.20))
        .clipShape(RoundedRectangle(cornerRadius: 6))
    }

    private var availableTabs: [DisplayTab] {
        return [.preview, .code, .diff]
    }

    // MARK: - Preview (WKWebView)

    private var artifactPreview: some View {
        Group {
            if let art = app.currentArtifact {
                // .id(art.id) forces SwiftUI to RECREATE the view (and WebView) only
                // when the artifact identity changes — not on every AppState update.
                ArtifactWebView(artifact: art)
                    .id(art.id)
            } else {
                emptyState
            }
        }
    }

    // MARK: - Code view

    private var codeView: some View {
        Group {
            if let art = app.currentArtifact {
                ScrollView([.horizontal, .vertical]) {
                    Text(art.content)
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(Color(red: 0.82, green: 0.82, blue: 0.88))
                        .textSelection(.enabled)
                        .lineSpacing(2)
                        .padding(14)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .background(Color(red: 0.07, green: 0.07, blue: 0.10))
            } else {
                emptyState
            }
        }
    }

    // MARK: - Empty state

    private var emptyState: some View {
        VStack(spacing: 20) {
            Spacer()
            ZStack {
                Circle()
                    .fill(Color(red: 0.15, green: 0.20, blue: 0.30).opacity(0.6))
                    .frame(width: 80, height: 80)
                Image(systemName: "rectangle.on.rectangle.angled")
                    .font(.system(size: 32))
                    .foregroundStyle(Color(red: 0.35, green: 0.55, blue: 0.85).opacity(0.8))
            }
            VStack(spacing: 8) {
                Text("Artifact Preview")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(Color(red: 0.60, green: 0.65, blue: 0.80))
                Text(AppLanguage.shared.t("When AI generates code or UI,\nit will be automatically displayed here.", "AIがコードや画面を生成すると\nここに自動表示されます"))
                    .font(.system(size: 11))
                    .foregroundStyle(Color(red: 0.40, green: 0.40, blue: 0.55))
                    .multilineTextAlignment(.center)
                    .lineSpacing(3)
            }
            VStack(spacing: 8) {
                hintRow(icon: "chevron.left.forwardslash.chevron.right",
                        color: Color(red: 0.6, green: 0.4, blue: 1.0),
                        text: AppLanguage.shared.t("Code block (```swift ...) → Auto display", "コードブロック (```swift ...) → 自動表示"))
                hintRow(icon: "globe",
                        color: Color(red: 0.9, green: 0.5, blue: 0.2),
                        text: AppLanguage.shared.t("Generate HTML → Live preview", "HTMLを生成して → ライブプレビュー"))
                hintRow(icon: "arrow.triangle.branch",
                        color: Color(red: 0.3, green: 0.8, blue: 1.0),
                        text: AppLanguage.shared.t("Draw Mermaid diagram → Graph display", "Mermaid図を描いて → グラフ表示"))
                hintRow(icon: "arrow.left.arrow.right.square",
                        color: Color(red: 0.4, green: 0.85, blue: 0.5),
                        text: AppLanguage.shared.t("File changes → Show in Diff tab", "ファイル変更 → Diffタブに表示"))
            }
            .padding(.horizontal, 24)
            Spacer()
        }
        .frame(maxWidth: .infinity)
    }

    private func hintRow(icon: String, color: Color, text: String) -> some View {
        HStack(spacing: 10) {
            Image(systemName: icon)
                .font(.system(size: 11))
                .foregroundStyle(color)
                .frame(width: 20)
            Text(text)
                .font(.system(size: 11))
                .foregroundStyle(Color(red: 0.50, green: 0.52, blue: 0.65))
            Spacer()
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 7)
        .background(Color.white.opacity(0.03), in: RoundedRectangle(cornerRadius: 6))
    }

    // MARK: - History menu

    private var historyMenu: some View {
        Menu {
            ForEach(app.artifactHistory) { art in
                Button {
                    app.currentArtifact = art
                    activeTab = art.type.isWebRenderable ? .preview : .code
                } label: {
                    HStack {
                        Image(systemName: art.type.icon)
                        Text(art.title)
                        Spacer()
                        Text(art.createdAt, style: .relative)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            if app.artifactHistory.isEmpty {
                Text(AppLanguage.shared.t("No History", "履歴なし")).foregroundStyle(.secondary)
            }
        } label: {
            Image(systemName: "clock.arrow.circlepath")
                .font(.system(size: 10))
                .foregroundStyle(Color(red: 0.5, green: 0.5, blue: 0.62))
        }
        .menuStyle(.borderlessButton)
        .help(AppLanguage.shared.t("Artifact History", "Artifact履歴"))
    }

    // MARK: - Helpers

    private func typeColor(_ type: Artifact.ArtifactType) -> Color {
        switch type {
        case .html:     return Color(red: 0.90, green: 0.45, blue: 0.20)
        case .markdown: return Color(red: 0.55, green: 0.85, blue: 0.70)
        case .mermaid:  return Color(red: 0.45, green: 0.75, blue: 1.00)
        case .code:     return Color(red: 0.70, green: 0.55, blue: 1.00)
        case .svg:      return Color(red: 0.98, green: 0.70, blue: 0.30)
        case .browser:  return Color(red: 0.20, green: 0.80, blue: 0.90)
        }
    }

    private func tabAccent(_ tab: DisplayTab) -> Color {
        switch tab {
        case .preview: return Color(red: 0.3, green: 0.85, blue: 0.60)
        case .code:    return Color(red: 0.6, green: 0.50, blue: 0.95)
        case .diff:    return Color(red: 0.4, green: 0.70, blue: 1.00)
        }
    }
}

// MARK: - ArtifactWebView (WKWebView wrapper)
//
// KEY STABILITY FIX: Coordinator caches the last HTML content hash.
// updateNSView is called by SwiftUI on EVERY @Published AppState change
// (e.g., tokensPerSecond updates 10× per second during streaming).
// Without the hash guard, WKWebView.loadHTMLString() fires repeatedly,
// interrupting CDN script downloads mid-flight → blank preview.
// With the guard: loadHTMLString is only called when content actually changes.

struct ArtifactWebView: NSViewRepresentable {
    let artifact: Artifact

    // MARK: - Coordinator
    final class Coordinator {
        var lastContentHash: Int = 0
    }

    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.preferences.setValue(true, forKey: "allowFileAccessFromFileURLs")
        let wv = WKWebView(frame: .zero, configuration: config)
        wv.setValue(false, forKey: "drawsBackground")
        wv.layer?.backgroundColor = NSColor(red: 0.06, green: 0.06, blue: 0.08, alpha: 1).cgColor
        return wv
    }

    func updateNSView(_ wv: WKWebView, context: Context) {
        if artifact.type == .browser {
            let targetURL = artifact.content.trimmingCharacters(in: .whitespacesAndNewlines)
            if let url = URL(string: targetURL), wv.url?.absoluteString != targetURL {
                wv.load(URLRequest(url: url))
            }
            return
        }

        let html = buildHTML(for: artifact)
        let newHash = html.hashValue
        // Skip reload when content hasn't changed (prevents streaming-driven flicker)
        guard newHash != context.coordinator.lastContentHash else { return }
        context.coordinator.lastContentHash = newHash
        wv.loadHTMLString(html, baseURL: nil)
    }

    // MARK: - HTML construction (CDN-free for Markdown/Code/SVG)

    private func buildHTML(for art: Artifact) -> String {
        switch art.type {

        case .html:
            return """
            <!DOCTYPE html>
            <html>
            <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
              * { box-sizing: border-box; }
              body { margin: 0; padding: 12px; background: #0f0f12; color: #dde;
                     font-family: -apple-system, sans-serif; }
            </style>
            </head>
            <body>\(art.content)</body>
            </html>
            """

        case .markdown:
            // CDN-free: pure CSS + minimal Swift inline renderer (no marked.js)
            let rendered = renderMarkdownCSS(escapeHTML(art.content))
            return """
            <!DOCTYPE html>
            <html>
            <head>
            <meta charset="utf-8">
            <style>
              body { margin: 0; padding: 20px; background: #0f0f12; color: #d8d8e8;
                     font-family: -apple-system, sans-serif; line-height: 1.7;
                     font-size: 13px; max-width: 820px; }
              h1 { color: #b8c8f8; font-size: 1.6em; margin: 0.8em 0 0.4em;
                   border-bottom: 1px solid #2a2a3a; padding-bottom: 0.3em; }
              h2 { color: #a8b8e8; font-size: 1.3em; margin: 0.7em 0 0.3em; }
              h3 { color: #98a8d8; font-size: 1.1em; margin: 0.6em 0 0.3em; }
              pre, code { font-family: 'SF Mono','Menlo',monospace; background: #1a1a24; border-radius: 5px; }
              pre  { padding: 12px 14px; overflow-x: auto; margin: 10px 0; font-size: 11.5px; line-height: 1.5; }
              code { padding: 1px 5px; font-size: 0.9em; color: #d0a8ff; }
              pre code { padding: 0; background: none; color: #c8d4e8; }
              blockquote { border-left: 3px solid #334466; padding-left: 14px;
                           margin-left: 0; color: #7880a0; font-style: italic; }
              a { color: #6ab0f5; text-decoration: none; }
              a:hover { text-decoration: underline; }
              strong { color: #e8e8f8; } em { color: #c0c8e0; }
              ul, ol { padding-left: 22px; } li { margin: 3px 0; }
              hr { border: none; border-top: 1px solid #2a2a3a; margin: 16px 0; }
              table { border-collapse: collapse; width: 100%; margin: 10px 0; }
              th, td { border: 1px solid #2a2a3a; padding: 6px 10px; }
              th { background: #1a1a24; color: #a8b8e8; }
            </style>
            </head>
            <body>\(rendered)</body>
            </html>
            """

        case .mermaid:
            // Mermaid requires its own JS runtime — CDN kept, but hash guard above
            // ensures loadHTMLString is only called once per diagram, not per token.
            return """
            <!DOCTYPE html>
            <html>
            <head>
            <meta charset="utf-8">
            <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
            <style>
              body { margin: 0; padding: 20px; background: #0f0f12;
                     display: flex; justify-content: center; }
              .mermaid { background: #161620; border-radius: 8px; padding: 20px; }
              svg { max-width: 100%; }
            </style>
            </head>
            <body>
            <div class="mermaid">\(art.content)</div>
            <script>
              mermaid.initialize({ startOnLoad: true, theme: 'dark',
                themeVariables: { background: '#161620', primaryColor: '#2d4a8a',
                  lineColor: '#4a6090', textColor: '#c8d4f0' }
              });
            </script>
            </body>
            </html>
            """

        case .svg:
            return """
            <!DOCTYPE html>
            <html>
            <head><meta charset="utf-8">
            <style>
              body { margin: 0; padding: 20px; background: #0f0f12;
                     display: flex; justify-content: center; align-items: center; min-height: 100vh; }
              svg { max-width: 100%; max-height: 90vh; }
            </style>
            </head>
            <body>\(art.content)</body>
            </html>
            """

        case .code:
            // CDN-free: CSS-only token coloring (replaces highlight.js)
            let lang = art.title.lowercased()
            let highlighted = applyCodeHighlight(escapeHTML(art.content), lang: lang)
            return """
            <!DOCTYPE html>
            <html>
            <head>
            <meta charset="utf-8">
            <style>
              body { margin: 0; background: #0d0d10; }
              pre {
                margin: 0; padding: 20px;
                font-family: 'SF Mono','Menlo','Monaco',monospace;
                font-size: 12px; line-height: 1.6; color: #c8d4e8;
                white-space: pre; overflow-x: auto; background: #0d0d10;
              }
              .kw  { color: #c792ea; }
              .str { color: #c3e88d; }
              .cmt { color: #546e7a; font-style: italic; }
              .num { color: #f78c6c; }
              .ann { color: #ff9cac; }
            </style>
            </head>
            <body>
            <pre><code class="\(lang)">\(highlighted)</code></pre>
            </body>
            </html>
            """
            
        case .browser:
            return "" // handled in updateNSView
        }
    }

    // MARK: - Inline Markdown renderer (no JS, pure Swift + HTML)

    private func renderMarkdownCSS(_ escaped: String) -> String {
        let lines = escaped.components(separatedBy: "\n")
        var out: [String] = []
        var inCode = false
        var inList = false

        for line in lines {
            if line.hasPrefix("```") {
                if inCode {
                    if inList { out.append("</ul>"); inList = false }
                    out.append("</pre>"); inCode = false
                } else {
                    if inList { out.append("</ul>"); inList = false }
                    out.append("<pre><code>"); inCode = true
                }
                continue
            }
            if inCode { out.append(line); continue }

            if line.hasPrefix("### ") {
                if inList { out.append("</ul>"); inList = false }
                out.append("<h3>\(line.dropFirst(4))</h3>"); continue
            }
            if line.hasPrefix("## ") {
                if inList { out.append("</ul>"); inList = false }
                out.append("<h2>\(line.dropFirst(3))</h2>"); continue
            }
            if line.hasPrefix("# ") {
                if inList { out.append("</ul>"); inList = false }
                out.append("<h1>\(line.dropFirst(2))</h1>"); continue
            }
            if line.hasPrefix("&gt; ") {
                if inList { out.append("</ul>"); inList = false }
                out.append("<blockquote>\(line.dropFirst(5))</blockquote>"); continue
            }
            if line == "---" || line == "***" || line == "___" {
                out.append("<hr>"); continue
            }
            if line.hasPrefix("- ") || line.hasPrefix("* ") {
                if !inList { out.append("<ul>"); inList = true }
                out.append("<li>\(applyInline(String(line.dropFirst(2))))</li>"); continue
            }
            if inList && (line.isEmpty || (!line.hasPrefix("- ") && !line.hasPrefix("* "))) {
                out.append("</ul>"); inList = false
            }
            if line.isEmpty { out.append("<br>"); continue }
            out.append("<p>\(applyInline(line))</p>")
        }
        if inCode  { out.append("</pre>") }
        if inList  { out.append("</ul>") }
        return out.joined(separator: "\n")
    }

    private func applyInline(_ s: String) -> String {
        var r = s
        r = r.replacingOccurrences(of: "\\*\\*\\*(.+?)\\*\\*\\*",
            with: "<strong><em>$1</em></strong>", options: .regularExpression)
        r = r.replacingOccurrences(of: "\\*\\*(.+?)\\*\\*",
            with: "<strong>$1</strong>", options: .regularExpression)
        r = r.replacingOccurrences(of: "\\*(.+?)\\*",
            with: "<em>$1</em>", options: .regularExpression)
        r = r.replacingOccurrences(of: "`(.+?)`",
            with: "<code>$1</code>", options: .regularExpression)
        r = r.replacingOccurrences(of: "\\[(.+?)\\]\\((.+?)\\)",
            with: "<a href=\"$2\">$1</a>", options: .regularExpression)
        return r
    }

    // MARK: - CDN-free syntax highlighter (regex token classes)

    private func applyCodeHighlight(_ code: String, lang: String) -> String {
        var r = code

        let swiftKw = "\\b(import|class|struct|enum|func|var|let|if|else|guard|return|for|in|while|switch|case|default|break|continue|true|false|nil|self|super|init|deinit|override|final|public|private|internal|open|fileprivate|mutating|static|async|await|throws|try|catch|throw|some|any|protocol|extension|where|typealias|defer|inout)\\b"
        let rustKw  = "\\b(fn|let|mut|pub|use|mod|struct|enum|impl|trait|where|for|in|while|if|else|match|return|self|super|crate|move|ref|async|await|type|const|static|unsafe|dyn|loop|break|continue|true|false|Some|None|Ok|Err)\\b"
        let tsKw    = "\\b(const|let|var|function|class|interface|type|enum|import|export|from|return|if|else|for|while|switch|case|default|break|continue|async|await|new|this|super|extends|implements|public|private|protected|readonly|true|false|null|undefined|void|never)\\b"
        let pyKw    = "\\b(def|class|import|from|return|if|elif|else|for|while|with|as|in|not|and|or|is|lambda|yield|pass|break|continue|True|False|None|async|await|try|except|finally|raise)\\b"

        let kwPat: String
        switch lang {
        case "swift":                       kwPat = swiftKw
        case "rust", "rs":                  kwPat = rustKw
        case "typescript", "ts",
             "javascript", "js", "tsx":     kwPat = tsKw
        case "python", "py":                kwPat = pyKw
        default:                            kwPat = swiftKw
        }

        // Apply in order: comments → strings → keywords (avoids double-wrapping)
        r = r.replacingOccurrences(of: "(//[^\\n]*)",
            with: "<span class='cmt'>$1</span>", options: .regularExpression)
        r = r.replacingOccurrences(of: "(/\\*[\\s\\S]*?\\*/)",
            with: "<span class='cmt'>$1</span>", options: .regularExpression)
        if ["python","py","sh","bash","toml","yaml"].contains(lang) {
            r = r.replacingOccurrences(of: "(#[^\\n]*)",
                with: "<span class='cmt'>$1</span>", options: .regularExpression)
        }
        r = r.replacingOccurrences(of: "(\"[^\"\\n]*\")",
            with: "<span class='str'>$1</span>", options: .regularExpression)
        r = r.replacingOccurrences(of: "('[^'\\n]*')",
            with: "<span class='str'>$1</span>", options: .regularExpression)
        r = r.replacingOccurrences(of: "\\b([0-9]+(?:\\.[0-9]+)?)\\b",
            with: "<span class='num'>$1</span>", options: .regularExpression)
        r = r.replacingOccurrences(of: kwPat,
            with: "<span class='kw'>$1</span>", options: .regularExpression)
        r = r.replacingOccurrences(of: "(@[A-Za-z_][A-Za-z0-9_]*)",
            with: "<span class='ann'>$1</span>", options: .regularExpression)
        return r
    }

    private func escapeHTML(_ s: String) -> String {
        s.replacingOccurrences(of: "&", with: "&amp;")
         .replacingOccurrences(of: "<", with: "&lt;")
         .replacingOccurrences(of: ">", with: "&gt;")
    }
}
