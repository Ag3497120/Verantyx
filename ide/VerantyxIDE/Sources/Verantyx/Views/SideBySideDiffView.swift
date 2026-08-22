import SwiftUI

// MARK: - SideBySideDiffView
// Right panel: hunk-based side-by-side diff using DiffEngine's LCS output.
// Each hunk shows only the changed region ±3 context lines per side.

struct SideBySideDiffView: View {
    @EnvironmentObject var app: AppState

    var body: some View {
        VStack(spacing: 0) {
            panelHeader

            Divider().opacity(0.3)

            if let diff = app.pendingDiff {
                if diff.hasChanges {
                    diffBody(diff)
                } else {
                    noChangesState(diff)
                }
            } else {
                emptyState
            }
        }
        .background(Color(red: 0.10, green: 0.10, blue: 0.13))
    }

    // MARK: - Header

    private var panelHeader: some View {
        HStack(spacing: 8) {
            Image(systemName: "arrow.left.arrow.right.square")
                .font(.system(size: 11))
                .foregroundStyle(Color(red: 0.4, green: 0.65, blue: 1.0))

            if let diff = app.pendingDiff {
                Text(diff.fileURL.lastPathComponent)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Color(red: 0.85, green: 0.85, blue: 0.95))
                    .lineLimit(1)

                Spacer(minLength: 6)

                // Stats badges
                statBadge("+\(diff.addedCount)", color: Color(red: 0.3, green: 0.9, blue: 0.45))
                statBadge("-\(diff.removedCount)", color: Color(red: 0.9, green: 0.35, blue: 0.35))
            } else {
                Text("Diff")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Color(red: 0.55, green: 0.55, blue: 0.7))
                Spacer()
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 7)
        .background(Color(red: 0.13, green: 0.13, blue: 0.17))
    }

    private func statBadge(_ label: String, color: Color) -> some View {
        Text(label)
            .font(.system(size: 10, weight: .bold, design: .monospaced))
            .foregroundStyle(color)
            .padding(.horizontal, 7)
            .padding(.vertical, 2)
            .background(color.opacity(0.12), in: RoundedRectangle(cornerRadius: 4))
    }

    // MARK: - Main diff body

    private func diffBody(_ diff: FileDiff) -> some View {
        VStack(spacing: 0) {
            // Column headers
            HStack(spacing: 0) {
                columnHeader("before", color: Color(red: 0.9, green: 0.35, blue: 0.35))
                Divider().frame(width: 1).opacity(0.4)
                columnHeader("after", color: Color(red: 0.35, green: 0.9, blue: 0.5))
            }

            Divider().opacity(0.3)

            ScrollView([.vertical, .horizontal]) {
                HStack(alignment: .top, spacing: 0) {
                    // ── LEFT: before ──────────────────────────────────────
                    leftColumn(diff)
                        .frame(maxWidth: .infinity, alignment: .leading)

                    Rectangle()
                        .fill(Color.white.opacity(0.06))
                        .frame(width: 1)

                    // ── RIGHT: after ──────────────────────────────────────
                    rightColumn(diff)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .frame(maxWidth: .infinity)
            }

            Divider().opacity(0.3)

            actionBar(diff)
        }
    }

    // MARK: - Column headers

    private func columnHeader(_ title: String, color: Color) -> some View {
        HStack(spacing: 5) {
            Image(systemName: title == "before" ? "minus.circle.fill" : "plus.circle.fill")
                .foregroundStyle(color)
                .font(.system(size: 10))
            Text(title)
                .font(.system(size: 11, weight: .semibold, design: .monospaced))
                .foregroundStyle(color)
            Spacer()
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 5)
        .background(color.opacity(0.07))
        .frame(maxWidth: .infinity)
    }

    // MARK: - Left column (original)

    private func leftColumn(_ diff: FileDiff) -> some View {
        // Rebuild unified line sequence from hunks for the "before" side
        VStack(spacing: 0) {
            let entries = buildLeftSideLines(diff)
            ForEach(Array(entries.enumerated()), id: \.offset) { _, entry in
                lineRow(lineNum: entry.lineNum, text: entry.text, kind: entry.kind, side: .left)
            }
        }
    }

    // MARK: - Right column (modified)

    private func rightColumn(_ diff: FileDiff) -> some View {
        VStack(spacing: 0) {
            let entries = buildRightSideLines(diff)
            ForEach(Array(entries.enumerated()), id: \.offset) { _, entry in
                lineRow(lineNum: entry.lineNum, text: entry.text, kind: entry.kind, side: .right)
            }
        }
    }

    // MARK: - Row renderer

    enum Side { case left, right }

    private func lineRow(lineNum: Int?, text: String, kind: DiffLine.Kind, side: Side) -> some View {
        HStack(spacing: 0) {
            // Line number gutter
            Group {
                if let n = lineNum {
                    Text("\(n)")
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(Color(red: 0.35, green: 0.35, blue: 0.48))
                } else {
                    Text("·")
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(Color(red: 0.22, green: 0.22, blue: 0.32))
                }
            }
            .frame(width: 32, alignment: .trailing)
            .padding(.trailing, 6)

            // Change glyph
            Text(glyph(kind: kind, side: side))
                .font(.system(size: 10, design: .monospaced))
                .foregroundStyle(glyphColor(kind: kind))
                .frame(width: 12)

            // Code text
            Text(text)
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(textColor(kind: kind))
                .frame(maxWidth: .infinity, alignment: .leading)
                .lineLimit(1)
                .padding(.leading, 4)
        }
        .padding(.vertical, 1.5)
        .background(rowBackground(kind: kind, side: side))
    }

    // MARK: - Hunk separator (shown between hunks)

    private func hunkSeparator(_ label: String) -> some View {
        HStack {
            Text(label)
                .font(.system(size: 9, weight: .semibold, design: .monospaced))
                .foregroundStyle(Color(red: 0.4, green: 0.55, blue: 0.85))
            Spacer()
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 3)
        .background(Color(red: 0.12, green: 0.18, blue: 0.30).opacity(0.5))
    }

    // MARK: - Line data builders

    struct LineEntry {
        let lineNum: Int?
        let text: String
        let kind: DiffLine.Kind
    }

    /// Build left-side (before) line list from hunks.
    /// Removed lines appear; added lines show as empty placeholder.
    private func buildLeftSideLines(_ diff: FileDiff) -> [LineEntry] {
        var result: [LineEntry] = []
        let origLines = diff.originalContent.components(separatedBy: "\n")

        // Re-derive "before" lines from hunks
        for hunk in diff.hunks {
            for line in hunk.lines {
                switch line.kind {
                case .context:
                    // Context lines: find line number in original
                    let num = lineNumberInOriginal(text: line.text, lines: origLines)
                    result.append(LineEntry(lineNum: num, text: line.text, kind: .context))
                case .removed:
                    let num = lineNumberInOriginal(text: line.text, lines: origLines)
                    result.append(LineEntry(lineNum: num, text: line.text, kind: .removed))
                case .added:
                    // This line doesn't exist on left side — show empty placeholder row
                    result.append(LineEntry(lineNum: nil, text: "", kind: .added))
                }
            }
        }
        return result
    }

    /// Build right-side (after) line list from hunks.
    private func buildRightSideLines(_ diff: FileDiff) -> [LineEntry] {
        var result: [LineEntry] = []
        let modLines = diff.modifiedContent.components(separatedBy: "\n")

        for hunk in diff.hunks {
            for line in hunk.lines {
                switch line.kind {
                case .context:
                    let num = lineNumberInModified(text: line.text, lines: modLines)
                    result.append(LineEntry(lineNum: num, text: line.text, kind: .context))
                case .added:
                    let num = lineNumberInModified(text: line.text, lines: modLines)
                    result.append(LineEntry(lineNum: num, text: line.text, kind: .added))
                case .removed:
                    // This line doesn't exist on right side — show empty placeholder
                    result.append(LineEntry(lineNum: nil, text: "", kind: .removed))
                }
            }
        }
        return result
    }

    /// Simple first-occurrence line number lookup (1-indexed)
    private func lineNumberInOriginal(text: String, lines: [String]) -> Int? {
        if let idx = lines.firstIndex(of: text) { return idx + 1 }
        return nil
    }

    private func lineNumberInModified(text: String, lines: [String]) -> Int? {
        if let idx = lines.firstIndex(of: text) { return idx + 1 }
        return nil
    }

    // MARK: - Style helpers

    private func glyph(kind: DiffLine.Kind, side: Side) -> String {
        switch kind {
        case .removed: return side == .left  ? "−" : " "
        case .added:   return side == .right ? "+" : " "
        case .context: return " "
        }
    }

    private func glyphColor(kind: DiffLine.Kind) -> Color {
        switch kind {
        case .added:   return Color(red: 0.35, green: 0.90, blue: 0.50)
        case .removed: return Color(red: 0.90, green: 0.35, blue: 0.35)
        case .context: return Color.clear
        }
    }

    private func textColor(kind: DiffLine.Kind) -> Color {
        switch kind {
        case .added:   return Color(red: 0.85, green: 0.98, blue: 0.88)
        case .removed: return Color(red: 0.98, green: 0.80, blue: 0.78)
        case .context: return Color(red: 0.62, green: 0.62, blue: 0.75)
        }
    }

    private func rowBackground(kind: DiffLine.Kind, side: Side) -> Color {
        switch kind {
        case .added:
            return side == .right
                ? Color(red: 0.10, green: 0.30, blue: 0.15).opacity(0.6)
                : Color(red: 0.10, green: 0.22, blue: 0.14).opacity(0.25)
        case .removed:
            return side == .left
                ? Color(red: 0.30, green: 0.10, blue: 0.10).opacity(0.6)
                : Color(red: 0.22, green: 0.10, blue: 0.10).opacity(0.25)
        case .context:
            return Color.clear
        }
    }

    // MARK: - Action bar

    private func actionBar(_ diff: FileDiff) -> some View {
        HStack(spacing: 12) {
            // File path
            let wsPath = app.cortexWorkspacePath ?? app.workspaceURL?.path ?? ""
            Text(wsPath.isEmpty ? diff.fileURL.path : diff.fileURL.path.replacingOccurrences(of: wsPath, with: "~"))
                .font(.system(size: 10, design: .monospaced))
                .foregroundStyle(Color(red: 0.42, green: 0.42, blue: 0.58))
                .lineLimit(1)
                .truncationMode(.middle)

            Spacer()

            // Reject
            Button {
                withAnimation(.easeInOut(duration: 0.15)) {
                    app.pendingDiff = nil
                    app.showDiff = false
                }
                app.addSystemMessage("↩️ Changes rejected.")
            } label: {
                Text(app.t("Reject", "拒否"))
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Color(red: 0.9, green: 0.38, blue: 0.38))
                    .padding(.horizontal, 18)
                    .padding(.vertical, 6)
                    .background(Color(red: 0.32, green: 0.10, blue: 0.10).opacity(0.6),
                                in: RoundedRectangle(cornerRadius: 6))
                    .overlay(RoundedRectangle(cornerRadius: 6)
                        .strokeBorder(Color(red: 0.9, green: 0.38, blue: 0.38).opacity(0.4),
                                      lineWidth: 1))
            }
            .contentShape(Rectangle())
            .buttonStyle(.plain)
            .keyboardShortcut(.escape)

            // Approve All
            Button {
                app.autoApproveDiffs = true
                applyDiff(diff)
                app.addSystemMessage(app.t("🚀 Auto-Approve enabled. Swarm will no longer pause for diffs.", "🚀 自動承認が有効になりました。Swarmは今後Diffで停止しません。"))
            } label: {
                Text(app.t("Approve All", "ずっと承認"))
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Color(red: 0.9, green: 0.8, blue: 0.2))
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .background(Color(red: 0.3, green: 0.25, blue: 0.05).opacity(0.75),
                                in: RoundedRectangle(cornerRadius: 6))
                    .overlay(RoundedRectangle(cornerRadius: 6)
                        .strokeBorder(Color(red: 0.9, green: 0.8, blue: 0.2).opacity(0.4),
                                      lineWidth: 1))
            }
            .contentShape(Rectangle())
            .buttonStyle(.plain)
            .help(app.t("Approve this diff and automatically approve all future diffs in this session", "このDiffを承認し、今後このセッション中のすべてのDiffを自動承認します"))

            // Approve
            Button {
                applyDiff(diff)
            } label: {
                Text(app.t("Approve", "承認"))
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Color(red: 0.3, green: 0.92, blue: 0.48))
                    .padding(.horizontal, 18)
                    .padding(.vertical, 6)
                    .background(Color(red: 0.10, green: 0.28, blue: 0.16).opacity(0.75),
                                in: RoundedRectangle(cornerRadius: 6))
                    .overlay(RoundedRectangle(cornerRadius: 6)
                        .strokeBorder(Color(red: 0.3, green: 0.92, blue: 0.48).opacity(0.4),
                                      lineWidth: 1))
            }
            .contentShape(Rectangle())
            .buttonStyle(.plain)
            .keyboardShortcut(.return, modifiers: .command)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 9)
        .background(Color(red: 0.12, green: 0.12, blue: 0.16))
    }

    private func applyDiff(_ diff: FileDiff) {
        do {
            try diff.modifiedContent.write(to: diff.fileURL, atomically: true, encoding: .utf8)
            app.selectedFileContent = diff.modifiedContent
            app.pendingDiff = nil
            app.showDiff = false
            app.addSystemMessage("✅ Applied to \(diff.fileURL.lastPathComponent)")

            // If the written file is renderable, auto-register as Artifact
            let ext = diff.fileURL.pathExtension.lowercased()
            if ["html", "htm", "svg", "md"].contains(ext) {
                let artType: Artifact.ArtifactType =
                    ext == "svg" ? .svg :
                    (ext == "md" ? .markdown : .html)
                let art = Artifact(type: artType,
                                   content: diff.modifiedContent,
                                   title: diff.fileURL.lastPathComponent)
                app.ingestArtifact(art)
            }
        } catch {
            app.addSystemMessage("❌ Write failed: \(error.localizedDescription)")
        }
    }

    // MARK: - Empty / no-changes states

    private var emptyState: some View {
        VStack(spacing: 14) {
            Spacer()
            Image(systemName: "arrow.left.arrow.right.square")
                .font(.system(size: 34))
                .foregroundStyle(Color(red: 0.28, green: 0.32, blue: 0.45))
            Text("Diff will appear here")
                .font(.headline)
                .foregroundStyle(Color(red: 0.40, green: 0.42, blue: 0.58))
            Text(AppLanguage.shared.t("Diffs will appear here\\nwhen AI makes changes", "AIがファイルを変更すると\\nここにDiffが表示されます"))
                .font(.callout)
                .foregroundStyle(Color(red: 0.32, green: 0.32, blue: 0.46))
                .multilineTextAlignment(.center)
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func noChangesState(_ diff: FileDiff) -> some View {
        VStack(spacing: 14) {
            Spacer()
            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 34))
                .foregroundStyle(Color(red: 0.32, green: 0.88, blue: 0.52))
            Text("No changes detected")
                .font(.headline)
                .foregroundStyle(Color(red: 0.60, green: 0.88, blue: 0.68))
            Text(diff.fileURL.lastPathComponent)
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(Color(red: 0.50, green: 0.52, blue: 0.65))
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
