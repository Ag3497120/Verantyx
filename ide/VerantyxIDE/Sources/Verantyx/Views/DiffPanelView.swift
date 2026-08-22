import SwiftUI

// MARK: - DiffPanelView
// Right panel: shows file diff with added/removed lines, Apply/Skip buttons.

struct DiffPanelView: View {
    @EnvironmentObject var app: AppState

    var body: some View {
        if app.showDiff, let diff = app.pendingDiff {
            diffView(diff)
        } else {
            emptyState
        }
    }

    // MARK: - Empty state

    private var emptyState: some View {
        VStack(spacing: 16) {
            Spacer()
            Image(systemName: "arrow.left.arrow.right.square")
                .font(.system(size: 40))
                .foregroundStyle(.tertiary)
            Text("Diff will appear here")
                .font(.title3)
                .foregroundStyle(.secondary)
            Text("Select a file and ask the AI to make changes.\nThe diff will be shown here for review.")
                .font(.callout)
                .foregroundStyle(.tertiary)
                .multilineTextAlignment(.center)
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .navigationTitle("Diff")
    }

    // MARK: - Diff view

    private func diffView(_ diff: FileDiff) -> some View {
        VStack(spacing: 0) {
            // Header bar
            diffHeader(diff)
            Divider()

            // Diff content
            ScrollView {
                VStack(alignment: .leading, spacing: 2) {
                    ForEach(diff.hunks) { hunk in
                        hunkView(hunk)
                        Divider().padding(.vertical, 4)
                    }
                }
                .padding(12)
            }

            Divider()

            // Action buttons
            actionBar(diff)
        }
    }

    private func diffHeader(_ diff: FileDiff) -> some View {
        HStack(spacing: 12) {
            Image(systemName: "doc.text.magnifyingglass")
                .foregroundStyle(Color.accentColor)
            Text(diff.fileURL.lastPathComponent)
                .font(.headline)
                .fontWeight(.semibold)
            Spacer()
            // Stats
            Label("\(diff.addedCount)", systemImage: "plus")
                .foregroundStyle(.green)
                .font(.callout.monospacedDigit())
            Label("\(diff.removedCount)", systemImage: "minus")
                .foregroundStyle(.red)
                .font(.callout.monospacedDigit())
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(.bar)
        .navigationTitle("Diff")
    }

    private func hunkView(_ hunk: DiffHunk) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            ForEach(hunk.lines) { line in
                HStack(spacing: 0) {
                    // Gutter
                    Text(glyph(for: line.kind))
                        .font(.system(.caption, design: .monospaced))
                        .frame(width: 18)
                        .foregroundStyle(glyphColor(for: line.kind))
                        .padding(.leading, 4)

                    // Content
                    Text(line.text)
                        .font(.system(.caption, design: .monospaced))
                        .foregroundStyle(textColor(for: line.kind))
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.leading, 6)
                        .padding(.vertical, 1)
                }
                .background(background(for: line.kind))
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 6))
    }

    private func actionBar(_ diff: FileDiff) -> some View {
        HStack(spacing: 12) {
            // Skip
            Button {
                app.skipDiff()
            } label: {
                Label("Discard", systemImage: "xmark")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
            .controlSize(.large)
            .keyboardShortcut(.escape)

            // Apply
            Button {
                app.applyDiff()
            } label: {
                Label("Apply Changes", systemImage: "checkmark")
                    .frame(maxWidth: .infinity)
                    .fontWeight(.semibold)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .keyboardShortcut(.return, modifiers: .command)
        }
        .padding(16)
    }

    // MARK: - Helpers

    private func glyph(for kind: DiffLine.Kind) -> String {
        switch kind {
        case .added:   return "+"
        case .removed: return "−"
        case .context: return " "
        }
    }

    private func glyphColor(for kind: DiffLine.Kind) -> Color {
        switch kind {
        case .added:   return .green
        case .removed: return .red
        case .context: return .secondary
        }
    }

    private func textColor(for kind: DiffLine.Kind) -> Color {
        switch kind {
        case .added:   return Color(nsColor: .labelColor)
        case .removed: return Color(nsColor: .labelColor).opacity(0.7)
        case .context: return Color(nsColor: .secondaryLabelColor)
        }
    }

    private func background(for kind: DiffLine.Kind) -> Color {
        switch kind {
        case .added:   return Color.green.opacity(0.12)
        case .removed: return Color.red.opacity(0.12)
        case .context: return .clear
        }
    }
}
