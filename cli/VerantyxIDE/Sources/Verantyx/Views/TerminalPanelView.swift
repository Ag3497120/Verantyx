import SwiftUI

// MARK: - TerminalPanelView
// Bottom panel showing AI-executed and manual command output.
// Approach B: shows Process stdout/stderr as plain text.

struct TerminalPanelView: View {
    @EnvironmentObject var app: AppState
    @ObservedObject var terminal: TerminalRunner
    @State private var input: String = ""
    @State private var isExpanded = true
    @FocusState private var inputFocused: Bool
    @State private var suggestedCmds: [(label: String, command: String)] = []

    var body: some View {
        VStack(spacing: 0) {
            // ── Header bar ──────────────────────────────────────────────────
            headerBar

            if isExpanded {
                Divider()
                // ── Output log ──────────────────────────────────────────────
                outputLog
                Divider()
                // ── Input bar ───────────────────────────────────────────────
                inputBar
            }
        }
        .frame(maxWidth: .infinity)
        .background(Color(red: 0.08, green: 0.08, blue: 0.10))
        .onChange(of: app.workspaceURL) { _, url in
            if let url = url {
                terminal.workingDirectory = url
                suggestedCmds = TerminalRunner.suggestedCommands(for: url)
            }
        }
        .onAppear {
            if let url = app.workspaceURL {
                terminal.workingDirectory = url
                suggestedCmds = TerminalRunner.suggestedCommands(for: url)
            }
        }
    }

    // MARK: - Header

    private var headerBar: some View {
        HStack(spacing: 8) {
            // Traffic lights style dots
            Circle().fill(Color(red: 0.2, green: 0.8, blue: 0.4)).frame(width: 8, height: 8)
            Text("Terminal")
                .font(.system(.caption, design: .monospaced))
                .fontWeight(.semibold)
                .foregroundStyle(Color(red: 0.6, green: 0.6, blue: 0.7))

            if terminal.isRunning {
                ProgressView().scaleEffect(0.5).frame(width: 12, height: 12)
                Text("running…")
                    .font(.system(.caption2, design: .monospaced))
                    .foregroundStyle(Color(red: 0.5, green: 0.9, blue: 0.5))
            }

            Spacer()

            // Working directory
            if let wd = terminal.workingDirectory {
                Text("~/" + wd.lastPathComponent)
                    .font(.system(.caption2, design: .monospaced))
                    .foregroundStyle(Color.secondary)
            }

            // Clear button
            Button {
                terminal.clear()
            } label: {
                Image(systemName: "trash")
                    .font(.caption2)
            }
            .contentShape(Rectangle())
            .buttonStyle(.plain)
            .foregroundStyle(Color.secondary)
            .help("Clear terminal")

            // Expand/collapse
            Button {
                withAnimation(.easeInOut(duration: 0.2)) { isExpanded.toggle() }
            } label: {
                Image(systemName: isExpanded ? "chevron.down" : "chevron.up")
                    .font(.caption2)
            }
            .contentShape(Rectangle())
            .buttonStyle(.plain)
            .foregroundStyle(Color.secondary)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(Color(red: 0.12, green: 0.12, blue: 0.15))
    }

    // MARK: - Output log

    private var outputLog: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 1) {
                    ForEach(terminal.history) { entry in
                        entryRow(entry)
                            .id(entry.id)
                    }
                    Color.clear.frame(height: 4).id("bottom")
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 4)
            }
            .onChange(of: terminal.history.count) { _, _ in
                proxy.scrollTo("bottom", anchor: .bottom)
            }
        }
        .frame(minHeight: 120, maxHeight: 200)
    }

    private func entryRow(_ entry: TerminalEntry) -> some View {
        HStack(alignment: .top, spacing: 0) {
            Text(entry.prefix)
                .font(.system(.caption, design: .monospaced))
                .foregroundStyle(entry.displayColor)
                .frame(width: entry.prefix == "  " ? 14 : CGFloat(entry.prefix.count) * 7, alignment: .leading)

            Text(entry.text)
                .font(.system(.caption, design: .monospaced))
                .foregroundStyle(entry.displayColor)
                .frame(maxWidth: .infinity, alignment: .leading)
                .textSelection(.enabled)
        }
    }

    // MARK: - Input bar

    private var inputBar: some View {
        VStack(spacing: 0) {
            // Quick command buttons (project-specific)
            if !suggestedCmds.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 6) {
                        ForEach(suggestedCmds, id: \.label) { cmd in
                            Button(cmd.label) {
                                Task { await terminal.run(cmd.command) }
                            }
                            .buttonStyle(TerminalButtonStyle())
                        }
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 5)
                }
                .background(Color(red: 0.10, green: 0.10, blue: 0.13))
            }

            // Manual input
            HStack(spacing: 6) {
                Text("$")
                    .font(.system(.callout, design: .monospaced))
                    .foregroundStyle(Color(red: 0.5, green: 0.9, blue: 0.5))

                TextField("", text: $input)
                    .font(.system(.callout, design: .monospaced))
                    .foregroundStyle(Color(red: 0.92, green: 0.92, blue: 0.92))
                    .textFieldStyle(.plain)
                    .focused($inputFocused)
                    .onSubmit {
                        let cmd = input.trimmingCharacters(in: .whitespaces)
                        guard !cmd.isEmpty else { return }
                        input = ""
                        Task { await terminal.run(cmd) }
                    }

                if terminal.isRunning {
                    ProgressView().controlSize(.small)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(Color(red: 0.10, green: 0.10, blue: 0.13))
        }
    }
}

// MARK: - Terminal button style

struct TerminalButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(.caption2, design: .monospaced))
            .foregroundStyle(Color(red: 0.7, green: 0.9, blue: 0.7))
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(
                RoundedRectangle(cornerRadius: 4)
                    .fill(Color(red: 0.15, green: 0.25, blue: 0.15))
                    .opacity(configuration.isPressed ? 0.6 : 1.0)
            )
    }
}
