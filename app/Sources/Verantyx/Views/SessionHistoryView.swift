import SwiftUI

// MARK: - SessionHistoryView
// Sidebar panel showing past chat sessions with JCross layer switcher.
// Appears as a sheet or as the "History" tab in AgentChatView.

struct SessionHistoryView: View {
    @EnvironmentObject var app: AppState
    @State private var editingId: UUID? = nil
    @State private var editTitle: String = ""
    @State private var confirmDeleteId: UUID? = nil
    @State private var showLayerPickerFor: UUID? = nil

    var body: some View {
        VStack(spacing: 0) {
            // ── Header ─────────────────────────────────────────────
            HStack {
                Image(systemName: "clock.arrow.circlepath")
                    .font(.system(size: 11))
                    .foregroundStyle(Theme.sel)
                Text(app.t("Session History", "セッション履歴"))
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Color(red: 0.85, green: 0.85, blue: 0.95))
                Spacer()
                // 新規作成の「＋」はここには置かない。左レールの PROJECTS
                // の「＋」に一本化した(2026-08-30) — 同じことをする入口が
                // 二つあり、片方はモーダルを挟み、片方は挟まないので、
                // 「新規チャットを押したら何が起きるか」が場所で変わって
                // いた。ここは**履歴を見る場所**に徹する。
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)

            Divider().opacity(0.3)

            // ── Session List ────────────────────────────────────────
            if app.sessions.sessions.isEmpty {
                emptyState
            } else {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 2) {
                        // Workspace sections, the way Claude's sidebar groups
                        // by project: the folder a conversation belonged to is
                        // usually how it is remembered.
                        ForEach(groupedSessions, id: \.key) { group in
                            Text(group.key)
                                .font(.system(size: 10, weight: .semibold))
                                .foregroundStyle(Theme.sel)
                                .padding(.horizontal, 12).padding(.top, 8)
                            ForEach(group.sessions) { session in
                                SessionRowView(
                                    session: session,
                                    isActive: session.id == app.sessions.activeSessionId,
                                    editingId: $editingId,
                                    editTitle: $editTitle,
                                    showLayerPickerFor: $showLayerPickerFor,
                                    confirmDeleteId: $confirmDeleteId
                                )
                                .environmentObject(app)
                            }
                        }
                    }
                    .padding(.vertical, 4)
                }
            }
        }
        .background(Theme.panel2)
        .confirmationDialog(
            app.t("Delete this session?", "セッションを削除しますか？"),
            isPresented: Binding(
                get: { confirmDeleteId != nil },
                set: { if !$0 { confirmDeleteId = nil } }
            ),
            titleVisibility: .visible
        ) {
            Button(app.t("Delete", "削除"), role: .destructive) {
                if let id = confirmDeleteId { app.sessions.delete(id) }
                confirmDeleteId = nil
            }
            Button(app.t("Cancel", "キャンセル"), role: .cancel) { confirmDeleteId = nil }
        }
    }

    private struct SessionGroup { let key: String; let sessions: [ChatSession] }

    /// Sessions bucketed by their workspace's folder name, most recent group
    /// first; sessions started without a workspace live under 一般/General.
    private var groupedSessions: [SessionGroup] {
        var order: [String] = []
        var buckets: [String: [ChatSession]] = [:]
        for sn in app.sessions.sessions {
            let key = sn.workspacePath.map { ($0 as NSString).lastPathComponent }
                ?? app.t("General", "一般")
            if buckets[key] == nil { order.append(key) }
            buckets[key, default: []].append(sn)
        }
        return order.map { SessionGroup(key: $0, sessions: buckets[$0] ?? []) }
    }

    private var emptyState: some View {
        VStack(spacing: 12) {
            Spacer()
            Image(systemName: "bubble.left.and.bubble.right")
                .font(.system(size: 32))
                .foregroundStyle(Color(red: 0.3, green: 0.3, blue: 0.4))
            Text(app.t("No sessions yet", "まだセッションがありません"))
                .font(.system(size: 12))
                .foregroundStyle(Theme.dim)
            Text(app.t("Sessions are saved automatically when you start a chat.",
                       "チャットを開始すると自動的に保存されます"))
                .font(.system(size: 11))
                .foregroundStyle(Color(red: 0.35, green: 0.35, blue: 0.45))
                .multilineTextAlignment(.center)
            Spacer()
        }
        .padding()
    }
}

// MARK: - Session Row

struct SessionRowView: View {
    let session: ChatSession
    let isActive: Bool
    @Binding var editingId: UUID?
    @Binding var editTitle: String
    @Binding var showLayerPickerFor: UUID?
    @Binding var confirmDeleteId: UUID?

    @EnvironmentObject var app: AppState

    private var isEditing: Bool { editingId == session.id }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                // Active indicator
                RoundedRectangle(cornerRadius: 2)
                    .fill(isActive
                          ? Theme.sel
                          : Color.clear)
                    .frame(width: 3)
                    .padding(.vertical, 4)

                VStack(alignment: .leading, spacing: 2) {
                    // Title (editable)
                    if isEditing {
                        TextField(app.t("Session name", "セッション名"), text: $editTitle)
                            .textFieldStyle(.plain)
                            .font(.system(size: 12, weight: .medium))
                            .foregroundStyle(Color.white)
                            .onSubmit {
                                app.sessions.rename(session.id, to: editTitle)
                                editingId = nil
                            }
                    } else {
                        // 名前は作った時点では空。まだ何も無いことを
                        // 「New Session」と嘘の名前で埋めない — 仮の名前
                        // だと分かる字で出し、服を送れば特徴が名前になる。
                        Text(session.title.isEmpty
                             ? app.t("Untitled chat", "名前のないチャット")
                             : session.title)
                            .font(.system(size: 12, weight: isActive ? .semibold : .regular))
                            .foregroundStyle(isActive
                                             ? Color.white
                                             : Color(red: 0.75, green: 0.75, blue: 0.85))
                            .lineLimit(1)
                    }

                    HStack(spacing: 6) {
                        // Date
                        Text(session.updatedAt, style: .relative)
                            .font(.system(size: 10))
                            .foregroundStyle(Theme.dim)

                        // Workspace
                        if let wp = session.workspacePath {
                            Text("·")
                                .foregroundStyle(Color(red: 0.4, green: 0.4, blue: 0.5))
                            Text(URL(fileURLWithPath: wp).lastPathComponent)
                                .font(.system(size: 10, design: .monospaced))
                                .foregroundStyle(Theme.ok)
                                .lineLimit(1)
                        }

                        // Memory nodes count
                        if !session.memoryNodeIds.isEmpty {
                            Text("·")
                                .foregroundStyle(Color(red: 0.4, green: 0.4, blue: 0.5))
                            Image(systemName: "brain")
                                .font(.system(size: 9))
                                .foregroundStyle(Theme.accent)
                            Text("\(session.memoryNodeIds.count)")
                                .font(.system(size: 10))
                                .foregroundStyle(Theme.accent)
                        }
                    }
                }

                Spacer()

                // Action buttons
                HStack(spacing: 4) {
                    // Layer badge
                    layerBadge

                    // Rename
                    Button {
                        editingId = session.id
                        editTitle = session.title
                    } label: {
                        Image(systemName: "pencil")
                            .font(.system(size: 10))
                    }
                    .contentShape(Rectangle())
                    .buttonStyle(.plain)
                    .foregroundStyle(Theme.dim)
                    .help(app.t("Rename", "名前を変更"))

                    // Delete
                    Button {
                        confirmDeleteId = session.id
                    } label: {
                        Image(systemName: "trash")
                            .font(.system(size: 10))
                    }
                    .contentShape(Rectangle())
                    .buttonStyle(.plain)
                    .foregroundStyle(Theme.bad)
                    .help(app.t("Delete", "削除"))
                }
                .opacity(isActive ? 1 : 0.5)
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 6)
            .background(
                RoundedRectangle(cornerRadius: 6)
                    .fill(isActive
                          ? Color.white.opacity(0.06)
                          : Color.clear)
            )
            .contentShape(Rectangle())
            .onTapGesture {
                guard !isEditing else { return }
                app.restoreSession(session.id)
            }

            // Layer picker (inline, shown on active row)
            if isActive && showLayerPickerFor == session.id {
                layerPicker
                    .padding(.horizontal, 8)
                    .padding(.bottom, 4)
            }
        }
        .padding(.horizontal, 4)
    }

    // MARK: - Layer Badge

    private var layerBadge: some View {
        Button {
            withAnimation(.easeInOut(duration: 0.15)) {
                showLayerPickerFor = showLayerPickerFor == session.id ? nil : session.id
            }
        } label: {
            Text(session.activeLayer.rawValue)
                .font(.system(size: 9, weight: .semibold, design: .monospaced))
                .foregroundStyle(layerColor(session.activeLayer))
                .padding(.horizontal, 5)
                .padding(.vertical, 2)
                .background(
                    RoundedRectangle(cornerRadius: 3)
                        .fill(layerColor(session.activeLayer).opacity(0.15))
                        .overlay(
                            RoundedRectangle(cornerRadius: 3)
                                .stroke(layerColor(session.activeLayer).opacity(0.4), lineWidth: 0.5)
                        )
                )
        }
        .contentShape(Rectangle())
        .buttonStyle(.plain)
        .help(app.t("Memory layer: \(session.activeLayer.description)",
                    "記憶レイヤー: \(session.activeLayer.description)"))
    }

    // MARK: - Inline Layer Picker

    private var layerPicker: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(app.t("Switch memory layer", "記憶レイヤーを切り替え"))
                .font(.system(size: 10))
                .foregroundStyle(Theme.dim)

            HStack(spacing: 6) {
                ForEach(JCrossLayer.allCases) { layer in
                    Button {
                        app.sessions.setLayer(layer, for: session.id)
                        // If this is the active session, re-inject memory
                        if session.id == app.sessions.activeSessionId {
                            Task {
                                let injection = await app.sessions.buildMemoryInjection(for: session.id)
                                if !injection.isEmpty {
                                    await MainActor.run {
                                        app.messages.removeAll { $0.role == .system && $0.content.contains("[JCROSS MEMORY") }
                                        app.messages.insert(ChatMessage(role: .system, content: injection), at: 0)
                                    }
                                }
                            }
                        }
                        withAnimation { showLayerPickerFor = nil }
                    } label: {
                        VStack(spacing: 2) {
                            Image(systemName: layer.icon)
                                .font(.system(size: 11))
                            Text(layer.rawValue)
                                .font(.system(size: 9, weight: .semibold))
                        }
                        .foregroundStyle(session.activeLayer == layer
                                         ? layerColor(layer)
                                         : Theme.dim)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 5)
                        .background(
                            RoundedRectangle(cornerRadius: 5)
                                .fill(session.activeLayer == layer
                                      ? layerColor(layer).opacity(0.12)
                                      : Color.white.opacity(0.04))
                        )
                    }
                    .contentShape(Rectangle())
                    .buttonStyle(.plain)
                    .help(layer.description)
                }
            }
        }
        .padding(8)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(Theme.panel2)
                .shadow(color: .black.opacity(0.4), radius: 6, y: 2)
        )
    }

    // 5 層を見分けるための固有色。l1_5 と vera がどちらも Theme.ok に
    // 潰れると凡例として区別できなくなるため、状態トークンには寄せず
    // レイヤーごとの固有色のまま残す。
    private func layerColor(_ layer: JCrossLayer) -> Color {
        switch layer {
        case .l1:   return Color(red: 0.9, green: 0.7, blue: 0.3)
        case .l1_5: return Color(red: 0.4, green: 0.8, blue: 0.5)
        case .l2:   return Color(red: 0.4, green: 0.7, blue: 1.0)
        case .l3:   return Color(red: 0.8, green: 0.5, blue: 1.0)
        case .vera: return Color(red: 0.3, green: 0.9, blue: 0.7)
        }
    }
}

// MARK: - Preview

#Preview {
    SessionHistoryView()
        .environmentObject(AppState())
        .frame(width: 260, height: 500)
}


// MARK: - New session sheet

/// Two decisions a new conversation actually has, asked up front:
/// where it lives (a workspace folder, or nowhere) and what it remembers
/// (continue the accumulated Vera-a memory, or start a fresh store).
/// Neither can be changed retroactively without confusion, which is why
/// this is a sheet and not two hidden defaults.
struct NewSessionSheet: View {
    @EnvironmentObject var app: AppState
    @Environment(\.dismiss) private var dismiss

    private enum Place: String, CaseIterable { case workspace, none }
    private enum Memory: String, CaseIterable { case carry, fresh }

    @State private var place: Place = .none
    @State private var memory: Memory = .carry

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(app.t("New session", "新しいセッション"))
                .font(.system(size: 14, weight: .semibold))

            VStack(alignment: .leading, spacing: 6) {
                Text(app.t("Where", "どこで"))
                    .font(.system(size: 10, weight: .semibold)).foregroundStyle(.secondary)
                Picker("", selection: $place) {
                    Text(app.t("No workspace — just chat", "何も開かずに始める")).tag(Place.none)
                    Text(app.t("Open a workspace folder…", "ワークスペースを開いてから")).tag(Place.workspace)
                }
                .pickerStyle(.radioGroup).labelsHidden()
            }

            VStack(alignment: .leading, spacing: 6) {
                Text(app.t("Vera memory", "Vera の記憶"))
                    .font(.system(size: 10, weight: .semibold)).foregroundStyle(.secondary)
                Picker("", selection: $memory) {
                    Text(app.t("Continue accumulated memory", "これまでの記憶を引き継ぐ")).tag(Memory.carry)
                    Text(app.t("Start a fresh memory store", "新規の記憶で最初から蓄積")).tag(Memory.fresh)
                }
                .pickerStyle(.radioGroup).labelsHidden()
                Text(app.t("Fresh stores are kept side by side — nothing is deleted.",
                           "新規にしても既存の記憶は消えません(並存します)。"))
                    .font(.system(size: 9)).foregroundStyle(.tertiary)
            }

            HStack {
                Spacer()
                Button(app.t("Cancel", "キャンセル")) { dismiss() }
                Button(app.t("Start", "開始")) { start() }
                    .buttonStyle(.borderedProminent)
            }
        }
        .padding(18)
        .frame(width: 340)
    }

    private func start() {
        if memory == .fresh {
            let df = DateFormatter(); df.dateFormat = "yyyyMMdd-HHmmss"
            app.veraMemoryTask = "vera-mem-" + df.string(from: Date())
        }
        if place == .workspace {
            let panel = NSOpenPanel()
            panel.canChooseDirectories = true
            panel.canChooseFiles = false
            panel.allowsMultipleSelection = false
            if panel.runModal() == .OK, let url = panel.url {
                app.workspaceURL = url
                app.terminal.workingDirectory = url
                UserDefaults.standard.set(url.path, forKey: "last_workspace_path")
                GatekeeperModeState.shared.configure(workspaceURL: url)
                app.refreshFiles()
            }
        }
        app.newChatSession()
        dismiss()
    }
}
