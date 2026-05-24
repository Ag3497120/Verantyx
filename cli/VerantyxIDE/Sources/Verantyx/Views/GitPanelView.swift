import SwiftUI

// MARK: - GitPanelView
// Source Control panel: unstaged/staged changes, commit UI, push/pull.
// Lives in the Activity Bar's "Version Control" section.

struct GitPanelView: View {
    @EnvironmentObject var app: AppState
    @StateObject private var git = GitEngine()

    @State private var commitMessage = ""
    @State private var isCommitting  = false
    @State private var isPushing     = false
    @State private var isPulling     = false
    @State private var showLog       = false
    @State private var errorBanner: String? = nil
    @State private var successBanner: String? = nil

    var body: some View {
        VStack(spacing: 0) {
            // ── Header ──────────────────────────────────────────────────
            gitHeader

            Divider().opacity(0.3)

            if git.isLoading && git.unstagedFiles.isEmpty && git.stagedFiles.isEmpty {
                VStack { Spacer(); ProgressView().scaleEffect(0.7); Spacer() }
                    .frame(maxWidth: .infinity)
            } else {
                ScrollView {
                    VStack(spacing: 0) {
                        // Error / success banners
                        if let err = errorBanner {
                            bannerView(err, isError: true)
                        }
                        if let ok = successBanner {
                            bannerView(ok, isError: false)
                        }

                        // ── Commit Box ──────────────────────────────────
                        commitBox

                        // ── Staged Changes ──────────────────────────────
                        if !git.stagedFiles.isEmpty {
                            fileSection(title: "STAGED CHANGES",
                                        color: Color(red: 0.3, green: 0.85, blue: 0.45),
                                        files: git.stagedFiles,
                                        isStaged: true)
                        }

                        // ── Unstaged Changes ────────────────────────────
                        if !git.unstagedFiles.isEmpty {
                            fileSection(title: "CHANGES",
                                        color: Color(red: 0.9, green: 0.65, blue: 0.3),
                                        files: git.unstagedFiles,
                                        isStaged: false)
                        }

                        // ── No Changes ──────────────────────────────────
                        if git.stagedFiles.isEmpty && git.unstagedFiles.isEmpty {
                            noChangesView
                        }

                        // ── Commit Log ──────────────────────────────────
                        if showLog { commitLogSection }
                    }
                    .padding(.vertical, 4)
                }
                .background(Color(red: 0.09, green: 0.09, blue: 0.12))
            }
        }
        .onAppear {
            if let root = app.workspaceURL { git.configure(root: root) }
        }
        .onChange(of: app.workspaceURL) { _, url in
            if let url { git.configure(root: url) }
        }
    }

    // MARK: - Header

    private var gitHeader: some View {
        HStack(spacing: 6) {
            Image(systemName: "arrow.triangle.branch")
                .font(.system(size: 10))
                .foregroundStyle(Color(red: 0.6, green: 0.8, blue: 0.4))

            Text(git.currentBranch.isEmpty ? "Git" : git.currentBranch)
                .font(.system(size: 10, weight: .semibold, design: .monospaced))
                .foregroundStyle(Color(red: 0.80, green: 0.80, blue: 0.92))
                .lineLimit(1)

            Spacer()

            // Pull
            toolButton(icon: "arrow.down.circle", tooltip: "Pull") {
                Task { await safePull() }
            }
            // Push
            toolButton(icon: "arrow.up.circle", tooltip: "Push") {
                Task { await safePush() }
            }
            // Refresh
            toolButton(icon: "arrow.clockwise", tooltip: "Refresh") {
                Task { await git.refresh() }
            }
            // Log toggle
            toolButton(icon: showLog ? "clock.fill" : "clock", tooltip: "Commit History") {
                withAnimation { showLog.toggle() }
            }
        }
        .padding(.horizontal, 10).padding(.vertical, 7)
        .background(Color(red: 0.10, green: 0.10, blue: 0.13))
    }

    // MARK: - Commit Box

    private var commitBox: some View {
        VStack(spacing: 6) {
            // Message editor
            ZStack(alignment: .topLeading) {
                if commitMessage.isEmpty {
                    Text(app.t("Message (⌘↩ to commit)", "メッセージ (⌘↩ でコミット)"))
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(Color(red: 0.4, green: 0.4, blue: 0.55))
                        .padding(.horizontal, 8)
                        .padding(.top, 7)
                }
                TextEditor(text: $commitMessage)
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(Color(red: 0.88, green: 0.88, blue: 0.95))
                    .scrollContentBackground(.hidden)
                    .background(Color.clear)
                    .frame(height: 70)
                    .padding(4)
            }
            .background(Color(red: 0.12, green: 0.12, blue: 0.17))
            .clipShape(RoundedRectangle(cornerRadius: 6))
            .overlay(RoundedRectangle(cornerRadius: 6)
                .stroke(Color(red: 0.25, green: 0.25, blue: 0.38).opacity(0.5), lineWidth: 1))

            // Commit button
            Button {
                Task { await safeCommit() }
            } label: {
                HStack(spacing: 6) {
                    if isCommitting {
                        ProgressView().scaleEffect(0.6).frame(width: 14, height: 14)
                    } else {
                        Image(systemName: "checkmark.circle.fill")
                            .font(.system(size: 12))
                    }
                    Text(git.stagedFiles.isEmpty ? "Commit All" : "Commit Staged")
                        .font(.system(size: 11, weight: .semibold))
                }
                .foregroundStyle(Color(red: 0.3, green: 0.85, blue: 0.45))
                .frame(maxWidth: .infinity)
                .padding(.vertical, 6)
                .background(
                    RoundedRectangle(cornerRadius: 6)
                        .fill(Color(red: 0.12, green: 0.28, blue: 0.18).opacity(0.8))
                        .overlay(RoundedRectangle(cornerRadius: 6)
                            .stroke(Color(red: 0.3, green: 0.85, blue: 0.45).opacity(0.35), lineWidth: 1))
                )
            }
            .contentShape(Rectangle())
            .buttonStyle(.plain)
            .disabled(isCommitting || commitMessage.trimmingCharacters(in: .whitespaces).isEmpty)
            .keyboardShortcut(.return, modifiers: .command)
        }
        .padding(10)
        .background(Color(red: 0.10, green: 0.10, blue: 0.14))
    }

    // MARK: - File Sections

    @ViewBuilder
    private func fileSection(title: String, color: Color, files: [GitEngine.FileStat], isStaged: Bool) -> some View {
        VStack(spacing: 0) {
            // Section header
            HStack(spacing: 6) {
                Text(title)
                    .font(.system(size: 9, weight: .bold, design: .monospaced))
                    .foregroundStyle(color)

                Text("\(files.count)")
                    .font(.system(size: 9, weight: .bold, design: .monospaced))
                    .foregroundStyle(color.opacity(0.7))

                Spacer()

                if !isStaged {
                    Button("Stage All") {
                        Task { try? await git.stageAll(); await git.refresh() }
                    }
                    .font(.system(size: 9)).foregroundStyle(color.opacity(0.8))
                    .contentShape(Rectangle())
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(Color(red: 0.11, green: 0.11, blue: 0.16))

            Divider().opacity(0.2)

            ForEach(files) { file in
                GitFileRow(file: file, isStaged: isStaged, git: git)
            }
        }
    }

    // MARK: - No Changes

    private var noChangesView: some View {
        VStack(spacing: 8) {
            Spacer(minLength: 20)
            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 28))
                .foregroundStyle(Color(red: 0.3, green: 0.75, blue: 0.4))
            Text("No changes")
                .font(.system(size: 11))
                .foregroundStyle(Color(red: 0.5, green: 0.5, blue: 0.65))
            Spacer(minLength: 10)
        }
        .frame(maxWidth: .infinity)
    }

    // MARK: - Commit Log

    private var commitLogSection: some View {
        VStack(spacing: 0) {
            HStack {
                Text("HISTORY")
                    .font(.system(size: 9, weight: .bold, design: .monospaced))
                    .foregroundStyle(Color(red: 0.55, green: 0.55, blue: 0.7))
                Spacer()
            }
            .padding(.horizontal, 10).padding(.vertical, 5)
            .background(Color(red: 0.11, green: 0.11, blue: 0.16))

            Divider().opacity(0.2)

            ForEach(git.commitLog) { commit in
                HStack(spacing: 8) {
                    Text(commit.shortHash)
                        .font(.system(size: 10, weight: .semibold, design: .monospaced))
                        .foregroundStyle(Color(red: 0.5, green: 0.7, blue: 1.0))
                        .frame(width: 52, alignment: .leading)

                    VStack(alignment: .leading, spacing: 2) {
                        Text(commit.message)
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(Color(red: 0.82, green: 0.82, blue: 0.92))
                            .lineLimit(1)
                        Text("\(commit.author) · \(commit.date)")
                            .font(.system(size: 9))
                            .foregroundStyle(Color(red: 0.45, green: 0.45, blue: 0.60))
                    }
                    Spacer()
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 5)
                .background(Color.clear)

                Divider().opacity(0.15)
            }
        }
    }

    // MARK: - Banners

    @ViewBuilder
    private func bannerView(_ message: String, isError: Bool) -> some View {
        HStack(spacing: 6) {
            Image(systemName: isError ? "xmark.circle.fill" : "checkmark.circle.fill")
                .font(.system(size: 11))
            Text(message)
                .font(.system(size: 10, design: .monospaced))
                .lineLimit(2)
            Spacer()
            Button { if isError { errorBanner = nil } else { successBanner = nil } } label: {
                Image(systemName: "xmark").font(.system(size: 9))
            }
            .contentShape(Rectangle())
            .buttonStyle(.plain)
        }
        .foregroundStyle(isError ? Color(red: 1.0, green: 0.4, blue: 0.4) : Color(red: 0.3, green: 0.9, blue: 0.5))
        .padding(.horizontal, 10).padding(.vertical, 6)
        .background(
            isError
            ? Color(red: 0.28, green: 0.10, blue: 0.10)
            : Color(red: 0.10, green: 0.24, blue: 0.15)
        )
    }

    // MARK: - Actions

    private func safeCommit() async {
        isCommitting = true
        errorBanner = nil
        do {
            if git.stagedFiles.isEmpty { try await git.stageAll() }
            let result = try await git.commit(message: commitMessage)
            successBanner = result.components(separatedBy: "\n").first ?? "Committed"
            commitMessage = ""
        } catch {
            errorBanner = error.localizedDescription
        }
        isCommitting = false
    }

    private func safePush() async {
        isPushing = true; errorBanner = nil
        do {
            let result = try await git.push()
            successBanner = "Pushed: " + (result.components(separatedBy: "\n").first ?? "")
        } catch { errorBanner = error.localizedDescription }
        isPushing = false
    }

    private func safePull() async {
        isPulling = true; errorBanner = nil
        do {
            let result = try await git.pull()
            successBanner = "Pulled: " + (result.components(separatedBy: "\n").first ?? "")
        } catch { errorBanner = error.localizedDescription }
        isPulling = false
    }

    // MARK: - Tool button

    @ViewBuilder
    private func toolButton(icon: String, tooltip: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: icon)
                .font(.system(size: 11))
                .foregroundStyle(Color(red: 0.55, green: 0.55, blue: 0.70))
        }
        .contentShape(Rectangle())
        .buttonStyle(.plain)
        .help(tooltip)
    }
}

// MARK: - GitFileRow

struct GitFileRow: View {
    let file: GitEngine.FileStat
    let isStaged: Bool
    @ObservedObject var git: GitEngine
    @EnvironmentObject var app: AppState
    @State private var isHovered = false

    var statusColor: Color {
        switch file.status {
        case .modified:  return Color(red: 0.9, green: 0.65, blue: 0.2)
        case .added:     return Color(red: 0.3, green: 0.85, blue: 0.45)
        case .deleted:   return Color(red: 0.9, green: 0.35, blue: 0.35)
        case .untracked: return Color(red: 0.55, green: 0.55, blue: 0.70)
        default:         return Color(red: 0.6, green: 0.6, blue: 0.75)
        }
    }

    var statusLetter: String {
        switch file.status {
        case .modified:  return "M"
        case .added:     return "A"
        case .deleted:   return "D"
        case .untracked: return "U"
        case .renamed:   return "R"
        default:         return "?"
        }
    }

    var body: some View {
        HStack(spacing: 6) {
            // Status badge
            Text(statusLetter)
                .font(.system(size: 9, weight: .bold, design: .monospaced))
                .foregroundStyle(statusColor)
                .frame(width: 12)

            // File name
            Text((file.path as NSString).lastPathComponent)
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(Color(red: 0.82, green: 0.82, blue: 0.92))
                .lineLimit(1)

            // Dir context
            let dir = (file.path as NSString).deletingLastPathComponent
            if !dir.isEmpty && dir != "." {
                Text(dir)
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(Color(red: 0.4, green: 0.4, blue: 0.55))
                    .lineLimit(1)
            }

            Spacer()

            // Stage / unstage button (appears on hover)
            if isHovered {
                Button {
                    Task {
                        guard let root = app.workspaceURL else { return }
                        let url = root.appendingPathComponent(file.path)
                        if isStaged {
                            try? await git.unstageFile(url)
                        } else {
                            try? await git.stageFile(url)
                        }
                        await git.refresh()
                    }
                } label: {
                    Image(systemName: isStaged ? "minus.circle" : "plus.circle")
                        .font(.system(size: 12))
                        .foregroundStyle(isStaged
                                         ? Color(red: 0.9, green: 0.4, blue: 0.4)
                                         : Color(red: 0.3, green: 0.85, blue: 0.45))
                }
                .contentShape(Rectangle())
                .buttonStyle(.plain)
                .transition(.opacity)
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 5)
        .background(isHovered ? Color(red: 0.15, green: 0.15, blue: 0.22).opacity(0.6) : Color.clear)
        .contentShape(Rectangle())
        .onHover { isHovered = $0 }
        .onTapGesture {
            guard let root = app.workspaceURL else { return }
            app.selectFile(root.appendingPathComponent(file.path))
        }
        .animation(.easeInOut(duration: 0.1), value: isHovered)
    }
}
