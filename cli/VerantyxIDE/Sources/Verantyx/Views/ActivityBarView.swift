import SwiftUI

// MARK: - ActivityBarView
// Left icon strip (VS Code style)

struct ActivityBarView: View {
    @Binding var selectedSection: ActivitySection?
    @EnvironmentObject var app: AppState

    enum ActivitySection: String, CaseIterable {
        case explorer    = "folder"
        case search      = "magnifyingglass"
        case git         = "arrow.triangle.branch"
        case mcp         = "puzzlepiece.extension"
        case growth      = "leaf"  // Vera M/O growth + quarantine (web module)
        case vera        = "cube.transparent"  // Vera-a feature dock (記憶/成長/2台/3D…)
        case evolution   = "arrow.triangle.2.circlepath"  // IDE source patches / PR
        case extensions  = "puzzlepiece"
        case settings    = "gearshape"
    }

    var body: some View {
        VStack(spacing: 0) {
            // Top icons
            VStack(spacing: 2) {
                ForEach([ActivitySection.explorer, .git, .mcp, .growth, .vera, .evolution], id: \.self) { section in
                    activityButton(section)
                }
            }
            .padding(.top, 10)

            Spacer()

            // Bottom icons
            VStack(spacing: 2) {
                activityButton(.settings)

                // Avatar placeholder
                Circle()
                    .fill(Color(red: 0.3, green: 0.5, blue: 0.9))
                    .frame(width: 22, height: 22)
                    .overlay(Text("A").font(.system(size: 11, weight: .bold)).foregroundStyle(.white))
                    .padding(.top, 8)
            }
            .padding(.bottom, 10)
        }
        .frame(width: 48)
        .background(Color(red: 0.15, green: 0.15, blue: 0.18))
    }

    private func activityButton(_ section: ActivitySection) -> some View {
        Button {
            if selectedSection == section {
                selectedSection = nil
            } else {
                selectedSection = section
            }
        } label: {
            ZStack(alignment: .topTrailing) {
                Image(systemName: section.rawValue)
                    .font(.system(size: 18))
                    .foregroundStyle(selectedSection == section
                        ? Color.white
                        : Color(red: 0.55, green: 0.55, blue: 0.60))
                    .frame(width: 48, height: 44)
                    .background(
                        selectedSection == section
                            ? Color.white.opacity(0.08)
                            : Color.clear
                    )
                    .overlay(
                        Rectangle()
                            .fill(Color(red: 0.4, green: 0.7, blue: 1.0))
                            .frame(width: 2)
                            .frame(maxHeight: selectedSection == section ? 24 : 0),
                        alignment: .leading
                    )

                // MCP kill-switch badge — red dot when tool is running
                if section == .mcp, MCPEngine.shared.activeCall != nil {
                    Circle()
                        .fill(Color.red)
                        .frame(width: 8, height: 8)
                        .offset(x: -6, y: 6)
                }
                // Evolution badge — spinning when building
                if section == .evolution {
                    if case .building(_) = SelfEvolutionEngine.shared.buildState {
                        ProgressView()
                            .scaleEffect(0.35)
                            .frame(width: 8, height: 8)
                            .offset(x: -6, y: 6)
                    } else if !SelfEvolutionEngine.shared.pendingPatches.isEmpty {
                        Circle()
                            .fill(Color(red: 1.0, green: 0.65, blue: 0.2))
                            .frame(width: 8, height: 8)
                            .offset(x: -6, y: 6)
                    }
                }
            }
            .contentShape(Rectangle())
        }
        .contentShape(Rectangle())
        .buttonStyle(.plain)
        .help(helpLabel(section))
    }

    private func helpLabel(_ section: ActivitySection) -> String {
        switch section {
        case .mcp:       return app.t("MCP Servers", "MCP サーバー")
        case .explorer:  return app.t("Explorer", "エクスプローラー")
        case .search:    return app.t("Search", "検索")
        case .git:       return app.t("Source Control", "ソース管理")
        case .evolution: return app.t("IDE patches (build/PR)", "IDEパッチ（ビルド/PR）")
        case .growth:    return app.t("Vera growth (M/O + quarantine)", "Vera成長（M/O・検疫）")
        case .vera:      return app.t("Vera-a features (memory/3D/two-Mac…)", "Vera-a機能（記憶・3D・2台…）")
        case .extensions: return app.t("Extensions", "拡張機能")
        case .settings:  return app.t("Settings", "設定")
        }
    }
}


// MARK: - Multi-purpose left panel

/// The left column, no longer only a file tree. Three surfaces:
/// ファイル (the tree, when a workspace is open), メモ (a scratch pad that
/// persists), and AI (a surface the agent can write into via
/// `AppState.flexPanelText` — "define what this area shows" is now an
/// instruction the model can follow rather than a fixed layout decision).
struct MultiPurposePanel: View {
    @EnvironmentObject var app: AppState
    @AppStorage("flex_panel_tab") private var tab = "files"
    @AppStorage("flex_panel_note") private var note = ""

    var body: some View {
        VStack(spacing: 0) {
            // Fixed tabs plus every panel the AI has created and NAMED —
            // the agent decides what this column holds, not the layout.
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 4) {
                    ForEach([("files", app.t("Files", "ファイル")),
                             ("notes", app.t("Notes", "メモ"))], id: \.0) { key, label in
                        tabChip(label, key)
                    }
                    ForEach(app.aiPanels) { panel in
                        tabChip(panel.title, "ai:" + panel.id)
                    }
                }
                .padding(6)
            }
            .frame(height: 30)
            Divider().opacity(0.25)
            if tab.hasPrefix("ai:") {
                let pid = String(tab.dropFirst(3))
                ScrollView {
                    Text(app.aiPanels.first(where: { $0.id == pid })?.text ?? "")
                        .font(.system(size: 11))
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(8)
                }
            } else {
            switch tab {
            case "notes":
                TextEditor(text: $note)
                    .font(.system(size: 12, design: .monospaced))
                    .scrollContentBackground(.hidden)
                    .background(Color(red: 0.1, green: 0.1, blue: 0.13))
            case "ai":
                ScrollView {
                    VStack(alignment: .leading, spacing: 6) {
                        if !app.flexPanelTitle.isEmpty {
                            Text(app.flexPanelTitle)
                                .font(.system(size: 11, weight: .semibold))
                        }
                        Text(app.flexPanelText.isEmpty
                             ? app.t("The agent can write here (flex panel).",
                                     "エージェントがここに表示を書き込めます(フレックスパネル)。")
                             : app.flexPanelText)
                            .font(.system(size: 11))
                            .textSelection(.enabled)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(8)
                }
            default:
                FileTreeView()
            }
            }
        }
    }

    private func tabChip(_ label: String, _ key: String) -> some View {
        Button { tab = key } label: {
            Text(label)
                .font(.system(size: 10, weight: tab == key ? .bold : .regular))
                .foregroundStyle(tab == key ? Color.white : Color(red: 0.55, green: 0.55, blue: 0.65))
                .padding(.horizontal, 8).padding(.vertical, 3)
                .background(RoundedRectangle(cornerRadius: 4)
                    .fill(tab == key ? Color.white.opacity(0.1) : Color.clear))
        }
        .buttonStyle(.plain)
    }
}
