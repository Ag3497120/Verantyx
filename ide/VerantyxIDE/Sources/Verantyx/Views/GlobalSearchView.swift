import SwiftUI

// MARK: - GlobalSearchView
// ⌘⇧F — project-wide search panel with live streaming results.
// Uses SearchEngine (ripgrep → git grep fallback).

struct GlobalSearchView: View {
    @EnvironmentObject var app: AppState
    @StateObject private var engine = ProjectSearchEngine()

    @State private var query: String = ""
    @State private var caseSensitive = false
    @State private var useRegex = false
    @State private var fileFilter = ""
    @FocusState private var queryFocused: Bool

    var body: some View {
        VStack(spacing: 0) {
            // ── Header ──────────────────────────────────────────────────
            VStack(spacing: 6) {
                HStack(spacing: 8) {
                    // Search input
                    HStack(spacing: 6) {
                        Image(systemName: "magnifyingglass")
                            .font(.system(size: 11))
                            .foregroundStyle(Color(red: 0.55, green: 0.55, blue: 0.7))

                        TextField("Search…", text: $query)
                            .font(.system(size: 12, design: .monospaced))
                            .textFieldStyle(.plain)
                            .foregroundStyle(Color(red: 0.90, green: 0.90, blue: 0.96))
                            .focused($queryFocused)
                            .onSubmit { triggerSearch() }
                            .onChange(of: query) { _, _ in
                                // Debounce: search 400ms after last keystroke
                                debounceSearch()
                            }

                        if engine.isSearching {
                            ProgressView().scaleEffect(0.5).frame(width: 14, height: 14)
                        } else if !query.isEmpty {
                            Button { query = ""; engine.clear() } label: {
                                Image(systemName: "xmark.circle.fill")
                                    .font(.system(size: 12))
                                    .foregroundStyle(Color(red: 0.5, green: 0.5, blue: 0.65))
                            }
                            .contentShape(Rectangle())
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.horizontal, 8).padding(.vertical, 5)
                    .background(Color(red: 0.12, green: 0.12, blue: 0.16))
                    .clipShape(RoundedRectangle(cornerRadius: 6))
                    .overlay(RoundedRectangle(cornerRadius: 6)
                        .stroke(queryFocused
                                ? Color(red: 0.4, green: 0.6, blue: 1.0).opacity(0.6)
                                : Color(red: 0.25, green: 0.25, blue: 0.35).opacity(0.5),
                                lineWidth: 1))
                }

                // ── Options row ──────────────────────────────────────────
                HStack(spacing: 4) {
                    // Case sensitive
                    toggleChip("Aa", active: caseSensitive) { caseSensitive.toggle(); triggerSearch() }
                    // Regex
                    toggleChip(".*", active: useRegex) { useRegex.toggle(); triggerSearch() }

                    Spacer()

                    // Results count
                    if !engine.groups.isEmpty {
                        Text("\(engine.totalMatches) result\(engine.totalMatches == 1 ? "" : "s")")
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(Color(red: 0.5, green: 0.5, blue: 0.65))
                    }
                }

                // ── File filter ──────────────────────────────────────────
                HStack(spacing: 6) {
                    Image(systemName: "doc.text")
                        .font(.system(size: 10))
                        .foregroundStyle(Color(red: 0.45, green: 0.45, blue: 0.6))
                    TextField("files to include (e.g. *.swift)", text: $fileFilter)
                        .font(.system(size: 11, design: .monospaced))
                        .textFieldStyle(.plain)
                        .foregroundStyle(Color(red: 0.75, green: 0.75, blue: 0.88))
                        .onSubmit { triggerSearch() }
                }
                .padding(.horizontal, 8).padding(.vertical, 4)
                .background(Color(red: 0.11, green: 0.11, blue: 0.15))
                .clipShape(RoundedRectangle(cornerRadius: 5))
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .background(Color(red: 0.10, green: 0.10, blue: 0.13))

            Divider().opacity(0.3)

            // ── Results list ─────────────────────────────────────────────
            if engine.groups.isEmpty && !engine.isSearching && !query.isEmpty {
                noResultsView
            } else {
                resultsList
            }
        }
        .onAppear { queryFocused = true }
    }

    // MARK: - Results List

    private var resultsList: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 0) {
                ForEach(engine.groups) { group in
                    SearchFileSection(
                        group: group,
                        highlight: query,
                        onSelect: { result in
                            app.selectFile(result.file)
                            // TODO: scroll to line result.lineNumber
                        }
                    )
                }
            }
            .padding(.vertical, 4)
        }
        .background(Color(red: 0.09, green: 0.09, blue: 0.12))
    }

    private var noResultsView: some View {
        VStack(spacing: 8) {
            Spacer()
            Image(systemName: "magnifyingglass")
                .font(.system(size: 28))
                .foregroundStyle(Color(red: 0.3, green: 0.3, blue: 0.4))
            Text("No results for \"\(query)\"")
                .font(.system(size: 12))
                .foregroundStyle(Color(red: 0.45, green: 0.45, blue: 0.60))
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: - Helpers

    @State private var debounceWorkItem: DispatchWorkItem? = nil

    private func debounceSearch() {
        debounceWorkItem?.cancel()
        let work = DispatchWorkItem { triggerSearch() }
        // Note: @State mutation from a non-mutating func — use DispatchQueue trick
        DispatchQueue.main.async {
            self.debounceWorkItem?.cancel()
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) {
            triggerSearch()
        }
    }

    private func triggerSearch() {
        guard let root = app.workspaceURL, !query.trimmingCharacters(in: .whitespaces).isEmpty else {
            engine.clear(); return
        }
        engine.search(
            query: query,
            in: root,
            caseSensitive: caseSensitive,
            regex: useRegex,
            filePattern: fileFilter.isEmpty ? nil : fileFilter
        )
    }

    @ViewBuilder
    private func toggleChip(_ label: String, active: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(label)
                .font(.system(size: 10, weight: .semibold, design: .monospaced))
                .foregroundStyle(active ? Color(red: 0.35, green: 0.75, blue: 1.0) : Color(red: 0.5, green: 0.5, blue: 0.65))
                .padding(.horizontal, 7).padding(.vertical, 3)
                .background(
                    RoundedRectangle(cornerRadius: 4)
                        .fill(active
                              ? Color(red: 0.15, green: 0.30, blue: 0.50).opacity(0.6)
                              : Color(red: 0.15, green: 0.15, blue: 0.20))
                        .overlay(RoundedRectangle(cornerRadius: 4)
                            .stroke(active
                                    ? Color(red: 0.35, green: 0.75, blue: 1.0).opacity(0.4)
                                    : Color(red: 0.25, green: 0.25, blue: 0.35).opacity(0.3),
                                    lineWidth: 0.8))
                )
        }
        .contentShape(Rectangle())
        .buttonStyle(.plain)
    }
}

// MARK: - SearchFileSection

struct SearchFileSection: View {
    let group: ProjectSearchEngine.FileGroup
    let highlight: String
    let onSelect: (ProjectSearchEngine.SearchResult) -> Void

    @State private var isExpanded = true

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // File header
            Button {
                withAnimation(.easeInOut(duration: 0.15)) { isExpanded.toggle() }
            } label: {
                HStack(spacing: 5) {
                    Image(systemName: isExpanded ? "chevron.down" : "chevron.right")
                        .font(.system(size: 8, weight: .semibold))
                        .foregroundStyle(.secondary)

                    Image(systemName: FileIcons.icon(for: group.file))
                        .font(.system(size: 10))
                        .foregroundStyle(FileIcons.color(for: group.file))

                    Text(group.file.lastPathComponent)
                        .font(.system(size: 11, weight: .semibold, design: .monospaced))
                        .foregroundStyle(Color(red: 0.88, green: 0.88, blue: 0.95))

                    Text(group.file.deletingLastPathComponent().lastPathComponent)
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(Color(red: 0.45, green: 0.45, blue: 0.60))

                    Spacer()

                    Text("\(group.results.count)")
                        .font(.system(size: 9, weight: .bold, design: .monospaced))
                        .foregroundStyle(Color(red: 0.4, green: 0.7, blue: 1.0))
                        .padding(.horizontal, 5).padding(.vertical, 2)
                        .background(Capsule().fill(Color(red: 0.15, green: 0.25, blue: 0.45).opacity(0.6)))
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 5)
                .contentShape(Rectangle())
                .background(Color(red: 0.11, green: 0.11, blue: 0.16))
            }
            .contentShape(Rectangle())
            .buttonStyle(.plain)

            // Result rows
            if isExpanded {
                ForEach(group.results) { result in
                    SearchResultRow(result: result, highlight: highlight)
                        .onTapGesture { onSelect(result) }
                }
            }
        }
    }
}

// MARK: - SearchResultRow

struct SearchResultRow: View {
    let result: ProjectSearchEngine.SearchResult
    let highlight: String
    @State private var isHovered = false

    var body: some View {
        HStack(spacing: 0) {
            // Line number gutter
            Text("\(result.lineNumber)")
                .font(.system(size: 10, design: .monospaced))
                .foregroundStyle(Color(red: 0.4, green: 0.4, blue: 0.55))
                .frame(width: 40, alignment: .trailing)
                .padding(.trailing, 8)

            // Content with highlight
            highlightedText(result.lineContent.trimmingCharacters(in: .whitespaces),
                            highlight: highlight)
                .font(.system(size: 11, design: .monospaced))
                .lineLimit(1)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 3)
        .background(isHovered
                    ? Color(red: 0.18, green: 0.22, blue: 0.32).opacity(0.6)
                    : Color.clear)
        .contentShape(Rectangle())
        .onHover { isHovered = $0 }
    }

    @ViewBuilder
    private func highlightedText(_ text: String, highlight: String) -> some View {
        if highlight.isEmpty {
            Text(text).foregroundStyle(Color(red: 0.72, green: 0.72, blue: 0.82))
        } else {
            // Simple highlight: find first occurrence
            let lower = text.lowercased()
            let hlLower = highlight.lowercased()
            if let range = lower.range(of: hlLower) {
                let before = String(text[text.startIndex..<range.lowerBound])
                let match  = String(text[range])
                let after  = String(text[range.upperBound...])
                Text(before)
                    .foregroundStyle(Color(red: 0.65, green: 0.65, blue: 0.78))
                + Text(match)
                    .foregroundStyle(Color(red: 1.0, green: 0.85, blue: 0.3))
                    .fontWeight(.semibold)
                + Text(after)
                    .foregroundStyle(Color(red: 0.65, green: 0.65, blue: 0.78))
            } else {
                Text(text).foregroundStyle(Color(red: 0.65, green: 0.65, blue: 0.78))
            }
        }
    }
}
