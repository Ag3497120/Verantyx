import SwiftUI

// MARK: - ChatPanelView
// Center panel: conversation history + input box.

struct ChatPanelView: View {
    @EnvironmentObject var app: AppState
    @FocusState private var isFocused: Bool

    var body: some View {
        VStack(spacing: 0) {
            // Context file badge
            if let file = app.selectedFile {
                contextBadge(file)
            }

            Divider()

            // Messages
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: 12) {
                        ForEach(app.messages) { msg in
                            MessageBubble(message: msg)
                                .id(msg.id)
                        }
                        if app.isGenerating {
                            LiveThinkingBubble(logStore: app.logStore)
                                .id("generating")
                        }
                    }
                    .padding(16)
                }
                // アニメーションなしでスクロール: テキスト震えを防ぐ
                .onChange(of: app.messages.count) { _, _ in
                    if app.isGenerating {
                        proxy.scrollTo("generating", anchor: .bottom)
                    } else if let lastId = app.messages.last?.id {
                        proxy.scrollTo(lastId, anchor: .bottom)
                    }
                }
                .onChange(of: app.isGenerating) { _, generating in
                    if generating {
                        proxy.scrollTo("generating", anchor: .bottom)
                    }
                }
            }

            Divider()

            // Input bar
            inputBar
        }
        .navigationTitle("Chat")
    }

    private func contextBadge(_ file: URL) -> some View {
        HStack(spacing: 6) {
            Image(systemName: "doc.text")
                .font(.caption2)
            Text(file.lastPathComponent)
                .font(.caption)
                .fontWeight(.medium)
            Spacer()
            Button {
                app.selectedFile = nil
                app.selectedFileContent = ""
            } label: {
                Image(systemName: "xmark.circle.fill")
                    .font(.caption)
            }
            .contentShape(Rectangle())
            .buttonStyle(.plain)
            .foregroundStyle(.secondary)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(Color.accentColor.opacity(0.1))
        .foregroundStyle(.secondary)
    }

    private var inputBar: some View {
        HStack(alignment: .bottom, spacing: 8) {
            ZStack(alignment: .leading) {
                if app.inputText.isEmpty {
                    Text(app.selectedFile == nil
                         ? "Ask anything, or select a file to edit…"
                         : "Describe the changes you want…")
                        .foregroundStyle(.tertiary)
                        .padding(.leading, 4)
                        .padding(.top, 1)
                }
                TextEditor(text: $app.inputText)
                    .font(.system(.body))
                    .frame(minHeight: 36, maxHeight: 120)
                    .scrollContentBackground(.hidden)
                    .focused($isFocused)
                    .onSubmit { sendIfPossible() }
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 6)
            .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 10))
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .strokeBorder(
                        isFocused ? Color.accentColor.opacity(0.6) : Color(nsColor: .separatorColor),
                        lineWidth: isFocused ? 1.5 : 0.5
                    )
            )

            Button {
                sendIfPossible()
            } label: {
                Image(systemName: app.isGenerating ? "stop.circle.fill" : "arrow.up.circle.fill")
                    .font(.title2)
                    .foregroundStyle(canSend ? Color.accentColor : Color.secondary)
            }
            .contentShape(Rectangle())
            .buttonStyle(.plain)
            .disabled(!canSend)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
    }

    private var canSend: Bool {
        !app.inputText.trimmingCharacters(in: .whitespaces).isEmpty && !app.isGenerating
    }

    private func sendIfPossible() {
        guard canSend else { return }
        app.sendMessage()
    }
}

// MARK: - MessageBubble

struct MessageBubble: View {
    let message: ChatMessage

    var body: some View {
        switch message.role {
        case .user:
            HStack {
                Spacer(minLength: 60)
                Text(message.content)
                    .font(.body)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                    .background(Color.accentColor)
                    .foregroundStyle(.white)
                    .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
            }

        case .assistant:
            VStack(alignment: .leading, spacing: 6) {
                // Thinking ブロック（ログがある場合のみ表示）
                if !message.thinkingLog.isEmpty {
                    CompletedThinkingBlock(log: message.thinkingLog)
                }

                HStack(alignment: .top, spacing: 10) {
                    Image(systemName: "brain.head.profile")
                        .font(.title3)
                        .foregroundStyle(Color.accentColor)
                        .frame(width: 28, height: 28)
                        .background(Color.accentColor.opacity(0.12), in: Circle())

                    AssistantText(content: message.content)
                        .frame(maxWidth: .infinity, alignment: .leading)

                    Spacer(minLength: 40)
                }
            }

        case .system:
            HStack {
                Image(systemName: "info.circle")
                    .font(.caption)
                Text(message.content)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .center)
        }
    }
}

// MARK: - LiveThinkingBubble
// Claudeスタイル：推論中にリアルタイムでログをインライン表示 + 折りたたみ可能

struct LiveThinkingBubble: View {
    @EnvironmentObject var app: AppState
    @ObservedObject var logStore: AppState.ProcessLogStore
    @State private var isExpanded = true

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            // ── AI アイコン ────────────────────────────────────────────
            ZStack {
                Circle()
                    .fill(Color.accentColor.opacity(0.12))
                    .frame(width: 28, height: 28)
                Image(systemName: "brain.head.profile")
                    .font(.title3)
                    .foregroundStyle(Color.accentColor)
            }

            VStack(alignment: .leading, spacing: 6) {
                // ── ヘッダー（クリックで折りたたみ） ──────────────────
                Button {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        isExpanded.toggle()
                    }
                } label: {
                    HStack(spacing: 8) {
                        // 新しい動画スピナー（2.7倍速でピンポンループ再生・青い部分を丸く切り出し）
                        if let url = URL(string: "file:///Users/motonishikoudai/verantyx-cli/VerantyxIDE/Sources/Verantyx/Views/mp_.mp4") {
                            VideoSpinnerView(videoURL: url, speed: 2.7)
                                .frame(width: 20, height: 20)
                        }

                        Text("Thinking…")
                            .font(.caption)
                            .fontWeight(.semibold)
                            .foregroundStyle(Color.accentColor)

                        if !logStore.entries.isEmpty {
                            Text("(\(logStore.entries.count) steps)")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }

                        Spacer()

                        Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
                .contentShape(Rectangle())
                .buttonStyle(.plain)

                // ── ログ本体（折りたたみ可能） ─────────────────────────
                if isExpanded {
                    VStack(alignment: .leading, spacing: 3) {
                        ForEach(logStore.entries.suffix(50)) { entry in
                            LogEntryRow(entry: entry)
                        }
                    }
                    .padding(10)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(
                        RoundedRectangle(cornerRadius: 10)
                            .fill(Color(nsColor: .controlBackgroundColor).opacity(0.7))
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 10)
                            .strokeBorder(Color(nsColor: .separatorColor).opacity(0.4), lineWidth: 0.5)
                    )
                    .transition(.opacity.combined(with: .move(edge: .top)))
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(
                RoundedRectangle(cornerRadius: 14)
                    .fill(Color.accentColor.opacity(0.04))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 14)
                    .strokeBorder(Color.accentColor.opacity(0.2), lineWidth: 1)
            )

            Spacer(minLength: 40)
        }
    }
}

// MARK: - LogEntryRow
// ProcessLog の1行を表示するビュー（ライブ用 / 保存済み用 両対応）

struct LogEntryRow: View {
    let entry: AppState.ProcessLogEntry

    var body: some View {
        ThinkingLogRow(
            timestamp: entry.timestamp,
            text:      entry.text,
            kindStr:   entry.kind.rawValue,
            color:     entry.color
        )
    }
}

// MARK: - ThinkingLogRow（汎用ログ行 — ライブ / 完了後 両対応）

private struct ThinkingLogRow: View {
    let timestamp: Date
    let text:      String
    let kindStr:   String
    let color:     Color

    private var icon: String {
        switch kindStr {
        case "memory":   return "memorychip"
        case "tool":     return "wrench.and.screwdriver"
        case "browser":  return "globe"
        case "thinking": return "bubble.left.and.text.bubble.right"
        case "perf":     return "bolt.fill"
        default:         return "gear"
        }
    }

    private var timeStr: String {
        let f = DateFormatter()
        f.dateFormat = "HH:mm:ss"
        return f.string(from: timestamp)
    }

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            Text(timeStr)
                .font(.system(.caption2, design: .monospaced))
                .foregroundStyle(Color(nsColor: .tertiaryLabelColor))
                .frame(width: 60, alignment: .leading)
            Image(systemName: icon)
                .font(.system(size: 9))
                .foregroundStyle(color)
                .frame(width: 12)
            Text(text)
                .font(.system(.caption, design: .monospaced))
                .foregroundStyle(color)
                .textSelection(.enabled)
                .lineLimit(3)
                .truncationMode(.tail)
        }
    }
}

// MARK: - CompletedThinkingBlock
// 推論完了後のメッセージに添付する折りたたみ可能な Thinking ブロック

struct CompletedThinkingBlock: View {
    let log: [ChatMessage.ThinkingLogEntry]
    @State private var isExpanded = false

    private func color(for kind: String) -> Color {
        switch kind {
        case "memory":   return Color(red: 0.4, green: 0.9, blue: 0.6)
        case "tool":     return Color(red: 0.4, green: 0.8, blue: 1.0)
        case "browser":  return Color(red: 0.9, green: 0.7, blue: 0.3)
        case "thinking": return Color(red: 0.8, green: 0.8, blue: 1.0)
        case "perf":     return Color(red: 0.3, green: 1.0, blue: 0.5)
        default:         return Color(red: 0.6, green: 0.6, blue: 0.6)
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            // ── ヘッダー（クリックで展開・折りたたみ） ─────────────────
            Button {
                withAnimation(.easeInOut(duration: 0.2)) { isExpanded.toggle() }
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: "brain")
                        .font(.system(size: 10))
                        .foregroundStyle(.secondary)
                    Text("Thinking")
                        .font(.caption)
                        .fontWeight(.medium)
                        .foregroundStyle(.secondary)
                    Text("· \(log.count) steps")
                        .font(.caption2)
                        .foregroundStyle(Color(nsColor: .tertiaryLabelColor))
                    Spacer()
                    Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                        .font(.system(size: 9))
                        .foregroundStyle(Color(nsColor: .tertiaryLabelColor))
                }
            }
            .contentShape(Rectangle())
            .buttonStyle(.plain)

            // ── ログ本体 ────────────────────────────────────────────────
            if isExpanded {
                VStack(alignment: .leading, spacing: 3) {
                    ForEach(log) { entry in
                        ThinkingLogRow(
                            timestamp: entry.timestamp,
                            text:      entry.text,
                            kindStr:   entry.kind,
                            color:     color(for: entry.kind)
                        )
                    }
                }
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(
                    RoundedRectangle(cornerRadius: 8)
                        .fill(Color(nsColor: .controlBackgroundColor).opacity(0.6))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .strokeBorder(Color(nsColor: .separatorColor).opacity(0.3), lineWidth: 0.5)
                )
                .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
        .padding(.leading, 38)  // アシスタントアイコン分のインデント
    }
}


// MARK: - ThinkingBubble (後方互換 — 未使用だが残す)
struct ThinkingBubble: View {
    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: "brain.head.profile")
                .font(.title3)
                .foregroundStyle(Color.accentColor)
                .frame(width: 28, height: 28)
                .background(Color.accentColor.opacity(0.12), in: Circle())
            if let url = URL(string: "file:///Users/motonishikoudai/verantyx-cli/VerantyxIDE/Sources/Verantyx/Views/mp_.mp4") {
                VideoSpinnerView(videoURL: url, speed: 2.7)
                    .frame(width: 24, height: 24)
                    .padding(.horizontal, 14).padding(.vertical, 12)
                    .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 16))
            }
        }
    }
}
