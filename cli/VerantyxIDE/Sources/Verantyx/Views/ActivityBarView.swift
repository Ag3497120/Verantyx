import SwiftUI

// MARK: - ActivityBarView
// Left icon strip (VS Code style)

struct ActivityBarView: View {
    @Binding var selectedSection: ActivitySection
    @EnvironmentObject var app: AppState

    enum ActivitySection: String, CaseIterable {
        case explorer    = "folder"
        case search      = "magnifyingglass"
        case git         = "arrow.triangle.branch"
        case mcp         = "puzzlepiece.extension"
        case evolution   = "arrow.triangle.2.circlepath"  // Self-Evolution
        case extensions  = "puzzlepiece"
        case settings    = "gearshape"
    }

    var body: some View {
        VStack(spacing: 0) {
            // Top icons
            VStack(spacing: 2) {
                // Logo
                Image(systemName: "atom")
                    .font(.system(size: 18, weight: .light))
                    .foregroundStyle(Color(red: 0.4, green: 0.7, blue: 1.0))
                    .padding(.bottom, 12)

                ForEach([ActivitySection.explorer, .search, .git, .mcp, .evolution], id: \.self) { section in
                    activityButton(section)
                }
            }
            .padding(.top, 10)

            Spacer()

            // Bottom icons
            VStack(spacing: 2) {
                activityButton(.extensions)
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
            selectedSection = section
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
        case .evolution: return app.t("Self-Evolution", "自己進化")
        case .extensions: return app.t("Extensions", "拡張機能")
        case .settings:  return app.t("Settings", "設定")
        }
    }
}
