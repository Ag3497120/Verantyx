import SwiftUI
import AppKit

// MARK: - FileTreeView
// Left panel: file hierarchy + selected file content preview.
//
// Performance architecture:
//   • nodeMap + rootItems — rebuilt ONLY when workspaceFiles changes (background Task)
//   • visibleNodes        — rebuilt ONLY when expandedFolders changes (cheap DFS, main thread)
//   • TreeRowView         — Equatable + EquatableView: rows that didn't change skip body
//   • previewLineCount    — cached in @State, updated via onChange

struct FileTreeView: View {
    @EnvironmentObject var app: AppState
    @ObservedObject private var gatekeeper = GatekeeperModeState.shared
    @State private var expandedFolders: Set<String> = []
    @State private var isScanning = false

    // ── Cached tree data ──────────────────────────────────────────────
    /// Full node map — rebuilt only when workspaceFiles changes. Expensive, done off-main.
    @State private var nodeMap: [String: TreeNode] = [:]
    /// Root-level paths (paths with no "/" in them), sorted.
    @State private var rootItems: [String] = []
    /// The flat list of visible rows derived from nodeMap + expandedFolders. Cheap to rebuild.
    @State private var visibleNodes: [TreeNode] = []
    /// Cached line count for the preview header — avoids splitting on every render.
    @State private var previewLineCount: Int = 0

    @State private var convertedFiles: Set<String> = []

    var body: some View {
        VStack(spacing: 0) {
            // ── Top: File hierarchy ───────────────────────────────────
            VStack(spacing: 0) {
                treeHeader
                Divider().opacity(0.3)

                if isScanning {
                    scanningIndicator
                } else if app.workspaceURL == nil {
                    emptyState
                } else if app.workspaceFiles.isEmpty {
                    VStack {
                        Spacer()
                        Text(AppLanguage.shared.t("No supported files found", "サポートされているファイルが見つかりません"))
                            .font(.system(size: 11, design: .monospaced))
                            .foregroundStyle(.tertiary)
                        Spacer()
                    }
                    .frame(maxWidth: .infinity)
                } else {
                    treeList
                }
            }
            .frame(maxHeight: .infinity)

            Rectangle().fill(Color.white.opacity(0.08)).frame(height: 1)

            // ── Bottom: File content preview ──────────────────────────
            filePreviewPanel.frame(maxHeight: .infinity)
        }
        // Workspace root changed → wipe everything
        .onChange(of: app.workspaceURL) { _, _ in
            isScanning = true
            expandedFolders.removeAll()
            nodeMap = [:]
            rootItems = []
            visibleNodes = []
        }
        .onChange(of: app.workspaceFiles) { _, files in
            isScanning = false
            rebuildNodeMap(files: files, root: app.workspaceURL)
        }
        .onChange(of: expandedFolders) { _, _ in
            visibleNodes = buildVisibleNodes()
        }
        .onChange(of: app.selectedFileContent) { _, content in
            previewLineCount = content.isEmpty ? 0 : content.components(separatedBy: "\n").count
        }
        .onReceive(gatekeeper.vault.$vaultStatus) { status in
            if case .ready = status {
                if let index = gatekeeper.vault.vaultIndex {
                    self.convertedFiles = Set(index.entries.keys)
                }
            }
        }
        .onAppear {
            if let index = gatekeeper.vault.vaultIndex {
                self.convertedFiles = Set(index.entries.keys)
            }
        }
    }

    // MARK: - Tree Header

    private var treeHeader: some View {
        HStack(spacing: 6) {
            Image(systemName: "folder.fill")
                .font(.system(size: 10))
                .foregroundStyle(Color(red: 0.5, green: 0.75, blue: 1.0))

            Text(app.workspaceURL?.lastPathComponent.uppercased() ?? "NO WORKSPACE")
                .font(.system(size: 10, weight: .semibold, design: .monospaced))
                .foregroundStyle(.secondary)
                .lineLimit(1)

            Spacer()

            if isScanning {
                ProgressView().scaleEffect(0.5).frame(width: 14, height: 14)
            } else {
                Button {
                    isScanning = true
                    app.refreshFiles()
                } label: {
                    Image(systemName: "arrow.clockwise").font(.system(size: 10))
                }
                .contentShape(Rectangle())
                .buttonStyle(.plain).foregroundStyle(.secondary)
            }

            Button { app.openWorkspace() } label: {
                Image(systemName: "folder.badge.plus").font(.system(size: 10))
            }
            .contentShape(Rectangle())
            .buttonStyle(.plain).foregroundStyle(.secondary)
        }
        .padding(.horizontal, 10).padding(.vertical, 7)
        .background(Color(red: 0.1, green: 0.1, blue: 0.13))
    }

    // MARK: - Tree List

    private var treeList: some View {
        TreeListView(
            visibleNodes: visibleNodes,
            expandedFolders: expandedFolders,
            selectedFile: app.selectedFile,
            convertedFiles: convertedFiles,
            onTap: handleTap
        )
    }

    private func handleTap(_ node: TreeNode) {
        if node.isDir {
            // Toggle expand — triggers onChange(of: expandedFolders) → fast rebuild
            if expandedFolders.contains(node.id) {
                expandedFolders.remove(node.id)
            } else {
                expandedFolders.insert(node.id)
            }
        } else if let url = node.url {
            app.selectFile(url)
        }
    }

    private var scanningIndicator: some View {
        VStack(spacing: 10) {
            Spacer()
            ProgressView().scaleEffect(0.8)
            Text(AppLanguage.shared.t("Scanning…", "スキャン中…"))
                .font(.system(size: 10, design: .monospaced)).foregroundStyle(.secondary)

            // Cancel button — forces scanning to stop
            Button("Cancel") {
                isScanning = false
            }
            .font(.system(size: 10))
            .foregroundStyle(Color(red: 0.9, green: 0.4, blue: 0.4))
            .contentShape(Rectangle())
            .buttonStyle(.plain)
            .padding(.top, 4)

            Spacer()
        }
        .frame(maxWidth: .infinity)
        // Auto-cancel after 10 seconds if still scanning
        .onAppear {
            DispatchQueue.main.asyncAfter(deadline: .now() + 10) {
                if isScanning { isScanning = false }
            }
        }
    }

    private var emptyState: some View {
        VStack(spacing: 10) {
            Spacer()
            Image(systemName: "folder.badge.questionmark").font(.title2).foregroundStyle(.tertiary)
            Text(AppLanguage.shared.t("No workspace", "ワークスペースなし")).font(.system(size: 11)).foregroundStyle(.secondary)
            Button(AppLanguage.shared.t("Open Folder…", "フォルダーを開く…")) { app.openWorkspace() }
                .buttonStyle(.borderedProminent).controlSize(.small)
            Spacer()
        }
        .frame(maxWidth: .infinity)
    }

    // MARK: - Bottom file preview

    private var filePreviewPanel: some View {
        VStack(spacing: 0) {
            HStack(spacing: 5) {
                if let file = app.selectedFile {
                    Image(systemName: FileIcons.icon(for: file))
                        .font(.system(size: 9))
                        .foregroundStyle(FileIcons.color(for: file))
                    Text(file.lastPathComponent)
                        .font(.system(size: 10, weight: .medium, design: .monospaced))
                        .foregroundStyle(.primary).lineLimit(1)
                    Spacer()
                    if previewLineCount > 0 {
                        // previewLineCount is cached via onChange — no string split here
                        Text("\(previewLineCount)L")
                            .font(.system(size: 9, design: .monospaced)).foregroundStyle(.tertiary)
                    }
                } else {
                    Image(systemName: "doc.text").font(.system(size: 9)).foregroundStyle(.tertiary)
                    Text(AppLanguage.shared.t("no file selected", "ファイルが選択されていません"))
                        .font(.system(size: 10, design: .monospaced)).foregroundStyle(.tertiary)
                    Spacer()
                }
            }
            .padding(.horizontal, 10).padding(.vertical, 6)
            .background(Color(red: 0.10, green: 0.10, blue: 0.14))

            Divider().opacity(0.3)

            if app.selectedFile != nil && app.selectedFileContent.isEmpty {
                VStack { Spacer(); ProgressView().scaleEffect(0.6); Spacer() }
                    .frame(maxWidth: .infinity)
            } else if app.selectedFileContent.isEmpty {
                VStack {
                    Spacer()
                    Text(AppLanguage.shared.t("Select a file to preview", "ファイルを選択してプレビュー"))
                        .font(.system(size: 10, design: .monospaced)).foregroundStyle(.tertiary)
                    Spacer()
                }
                .frame(maxWidth: .infinity)
            } else {
                // RawTextView: AppKit NSScrollView ベース — fixedSize なし
                // SwiftUI Text + fixedSize は大ファイルで swift_retain SIGTRAP を起こす
                RawTextView(content: app.selectedFileContent)
                    .transaction { t in t.animation = nil }
            }
        }
    }

    // MARK: - Tree Building

    /// Expensive: parse all workspace files into nodeMap.
    /// Runs off the main thread; posts result back via MainActor.
    private func rebuildNodeMap(files: [URL], root: URL?) {
        guard let root else { return }
        Task.detached(priority: .userInitiated) {
            var map: [String: TreeNode] = [:]
            map.reserveCapacity(files.count)

            for url in files {
                let rel = Self.relativePath(url, from: root)
                let parts = rel.split(separator: "/", omittingEmptySubsequences: true).map(String.init)
                var currentPath = ""
                for (i, part) in parts.enumerated() {
                    let parentPath = currentPath
                    currentPath = currentPath.isEmpty ? part : "\(currentPath)/\(part)"
                    if map[currentPath] == nil {
                        if i == parts.count - 1 {
                            map[currentPath] = TreeNode(id: currentPath, name: part,
                                                        depth: i, isDir: false, url: url, children: [])
                        } else {
                            map[currentPath] = TreeNode(id: currentPath, name: part,
                                                        depth: i, isDir: true, url: nil, children: [])
                        }
                        if !parentPath.isEmpty { map[parentPath]?.children.append(currentPath) }
                    }
                }
            }

            let roots = map.keys.filter { !$0.contains("/") }.sorted()

            await MainActor.run { [roots] in
                self.nodeMap   = map
                self.rootItems = roots
                // Auto-expand single root directory
                if roots.count == 1 { self.expandedFolders.insert(roots[0]) }
                self.visibleNodes = self.buildVisibleNodes()
            }
        }
    }

    /// Cheap: DFS over pre-built nodeMap respecting expandedFolders.
    /// O(visible nodes) — no file I/O, no allocations except result array.
    private func buildVisibleNodes() -> [TreeNode] {
        var result: [TreeNode] = []
        result.reserveCapacity(min(nodeMap.count, 512))

        func visit(_ id: String) {
            guard let node = nodeMap[id] else { return }
            result.append(node)
            if node.isDir && expandedFolders.contains(id) {
                for childId in node.children.sorted() { visit(childId) }
            }
        }
        for id in rootItems { visit(id) }
        return result
    }

    private static func relativePath(_ url: URL, from root: URL) -> String {
        let full = url.path, base = root.path
        if full.hasPrefix(base) { return String(full.dropFirst(base.count + 1)) }
        return url.lastPathComponent
    }
}

// MARK: - FileIcons
// Centralised icon + colour lookup for all file types.

enum FileIcons {

    static func icon(for url: URL) -> String { icon(ext: url.pathExtension) }
    static func icon(for name: String) -> String { icon(ext: (name as NSString).pathExtension) }

    static func icon(ext raw: String) -> String {
        switch raw.lowercased() {
        case "swift":              return "swift"
        case "xcodeproj","xcworkspace": return "hammer.fill"
        case "storyboard","xib":   return "rectangle.3.group"
        case "plist":              return "list.bullet.rectangle"
        case "py","pyw","pyi":     return "chevron.left.forwardslash.chevron.right"
        case "ipynb":              return "brain.head.profile"
        case "ts","tsx":           return "t.square.fill"
        case "js","jsx","mjs":     return "j.square"
        case "vue":                return "v.square.fill"
        case "html","htm":         return "globe"
        case "css","scss","sass","less": return "paintbrush.pointed"
        case "svg":                return "squareshape.controlhandles.on.squareshape.controlhandles"
        case "rs":                 return "r.square"
        case "go":                 return "g.square"
        case "kt","kts":           return "k.square"
        case "java":               return "j.circle.fill"
        case "scala":              return "s.square"
        case "c":                  return "c.square"
        case "cpp","cc","cxx":     return "c.square.fill"
        case "h","hpp":            return "h.square"
        case "rb","rake","gemspec": return "diamond.fill"
        case "php":                return "p.square"
        case "sh","bash","zsh","fish","ps1": return "terminal.fill"
        case "makefile","mk":      return "wrench.adjustable"
        case "json","jsonc":       return "curlybraces"
        case "yaml","yml":         return "list.dash"
        case "toml":               return "gearshape"
        case "ini","cfg","conf":   return "slider.horizontal.3"
        case "env":                return "lock.shield"
        case "dockerfile":         return "shippingbox"
        case "gitignore","gitattributes": return "arrow.triangle.branch"
        case "md","mdx","markdown": return "doc.richtext"
        case "txt":                return "doc.text"
        case "pdf":                return "doc.fill"
        case "docx","doc":         return "doc.richtext.fill"
        case "csv","tsv":          return "tablecells"
        case "xml":                return "angle.left.slash.angle.right"
        case "sql":                return "cylinder.split.1x2"
        case "png","jpg","jpeg","gif","webp","heic","tiff","bmp","ico":
                                   return "photo"
        case "mp3","m4a","wav","aiff","flac": return "music.note"
        case "mp4","mov","avi","mkv":          return "video"
        case "zip","tar","gz","bz2","xz","rar","7z": return "archivebox"
        case "lock":               return "lock.fill"
        case "package":            return "shippingbox.fill"
        default:                   return "doc"
        }
    }

    static func color(for url: URL) -> Color { color(ext: url.pathExtension) }
    static func color(for name: String) -> Color { color(ext: (name as NSString).pathExtension) }

    static func color(ext raw: String) -> Color {
        switch raw.lowercased() {
        case "swift":              return Color(red: 0.98, green: 0.49, blue: 0.18)
        case "py","pyw","pyi","ipynb": return Color(red: 0.97, green: 0.77, blue: 0.25)
        case "ts","tsx":           return Color(red: 0.27, green: 0.56, blue: 0.93)
        case "js","jsx","mjs":     return Color(red: 0.93, green: 0.80, blue: 0.18)
        case "vue":                return Color(red: 0.25, green: 0.75, blue: 0.56)
        case "html","htm":         return Color(red: 0.90, green: 0.40, blue: 0.20)
        case "css","scss","sass","less": return Color(red: 0.40, green: 0.65, blue: 0.95)
        case "svg":                return Color(red: 0.95, green: 0.58, blue: 0.18)
        case "rs":                 return Color(red: 0.86, green: 0.37, blue: 0.20)
        case "go":                 return Color(red: 0.37, green: 0.75, blue: 0.85)
        case "kt","kts":           return Color(red: 0.62, green: 0.45, blue: 0.95)
        case "java":               return Color(red: 0.90, green: 0.31, blue: 0.27)
        case "scala":              return Color(red: 0.82, green: 0.19, blue: 0.19)
        case "c":                  return Color(red: 0.56, green: 0.73, blue: 0.90)
        case "cpp","cc","cxx":     return Color(red: 0.35, green: 0.55, blue: 0.87)
        case "h","hpp":            return Color(red: 0.60, green: 0.80, blue: 0.96)
        case "rb","rake","gemspec": return Color(red: 0.90, green: 0.20, blue: 0.28)
        case "php":                return Color(red: 0.48, green: 0.52, blue: 0.80)
        case "sh","bash","zsh","fish","ps1": return Color(red: 0.45, green: 0.90, blue: 0.58)
        case "json","jsonc":       return Color(red: 0.95, green: 0.75, blue: 0.35)
        case "yaml","yml","toml":  return Color(red: 0.70, green: 0.65, blue: 0.95)
        case "md","mdx","markdown": return Color(red: 0.60, green: 0.85, blue: 0.75)
        case "dockerfile":         return Color(red: 0.25, green: 0.65, blue: 0.96)
        case "gitignore","gitattributes": return Color(red: 0.95, green: 0.45, blue: 0.32)
        case "pdf":                return Color(red: 0.90, green: 0.25, blue: 0.25)
        case "csv","tsv","sql":    return Color(red: 0.42, green: 0.78, blue: 0.56)
        case "png","jpg","jpeg","gif","webp","heic","tiff","bmp","ico":
                                   return Color(red: 0.88, green: 0.55, blue: 0.90)
        case "mp3","m4a","wav","aiff","flac": return Color(red: 0.95, green: 0.65, blue: 0.35)
        case "mp4","mov","avi","mkv": return Color(red: 0.58, green: 0.38, blue: 0.92)
        case "zip","tar","gz","bz2","xz","rar","7z": return Color(red: 0.75, green: 0.55, blue: 0.32)
        case "lock":               return Color(red: 0.55, green: 0.55, blue: 0.65)
        case "plist","xcodeproj","xcworkspace": return Color(red: 0.98, green: 0.49, blue: 0.18)
        default:                   return Color(red: 0.55, green: 0.55, blue: 0.65)
        }
    }
}

// MARK: - TreeNode

struct TreeNode: Identifiable {
    let id: String
    let name: String
    let depth: Int
    let isDir: Bool
    let url: URL?
    var children: [String]
}

// MARK: - TreeRowView
// Equatable: SwiftUI will skip body when node/isExpanded/isSelected haven't changed.
// The `onTap` closure is excluded from equality comparison intentionally — it's
// always the same logic (set by FileTreeView) and closures can't be compared.

struct TreeRowView: View, Equatable {
    let node: TreeNode
    let isExpanded: Bool
    let isSelected: Bool
    let isConverted: Bool
    let onTap: () -> Void

    static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.node.id         == rhs.node.id &&
        lhs.node.name       == rhs.node.name &&
        lhs.isExpanded      == rhs.isExpanded &&
        lhs.isSelected      == rhs.isSelected &&
        lhs.isConverted     == rhs.isConverted
    }

    var body: some View {
        Button(action: onTap) {
            HStack(spacing: 4) {
                Spacer().frame(width: CGFloat(node.depth) * 12 + 4)

                if node.isDir {
                    Image(systemName: isExpanded ? "chevron.down" : "chevron.right")
                        .font(.system(size: 8, weight: .semibold))
                        .foregroundStyle(.secondary).frame(width: 10)
                    Image(systemName: isExpanded ? "folder.open" : "folder")
                        .font(.system(size: 10))
                        .foregroundStyle(Color(red: 0.5, green: 0.75, blue: 1.0))
                } else {
                    Spacer().frame(width: 10)
                    Image(systemName: FileIcons.icon(for: node.name))
                        .font(.system(size: 9))
                        .foregroundStyle(FileIcons.color(for: node.name))
                }

                Text(node.name)
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(
                        isSelected ? .white :
                        isConverted ? .orange :
                        Color(red: 0.80, green: 0.80, blue: 0.86)
                    )
                    .lineLimit(1)

                Spacer()
            }
            .padding(.vertical, 3).padding(.horizontal, 4)
            .contentShape(Rectangle())
            .background(
                isSelected
                    ? Color(red: 0.2, green: 0.4, blue: 0.8).opacity(0.4)
                    : Color.clear,
                in: RoundedRectangle(cornerRadius: 3)
            )
        }
        .contentShape(Rectangle())
        .buttonStyle(.plain)
        .padding(.horizontal, 4)
    }
}

// MARK: - TreeListView
// Extracted to observe vault changes securely.

struct TreeListView: View {
    let visibleNodes: [TreeNode]
    let expandedFolders: Set<String>
    let selectedFile: URL?
    let convertedFiles: Set<String>
    let onTap: (TreeNode) -> Void
    
    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 0) {
                ForEach(visibleNodes) { node in
                    let isConverted = !node.isDir && convertedFiles.contains(node.id)
                    // EquatableView: row body is skipped when node/isExpanded/isSelected/isConverted unchanged
                    EquatableView(content: TreeRowView(
                        node: node,
                        isExpanded: expandedFolders.contains(node.id),
                        isSelected: node.url != nil && node.url == selectedFile,
                        isConverted: isConverted,
                        onTap: { onTap(node) }
                    ))
                }
            }
            .padding(.vertical, 4)
        }
    }
}
