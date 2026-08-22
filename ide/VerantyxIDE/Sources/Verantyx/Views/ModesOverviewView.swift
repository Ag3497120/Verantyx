import SwiftUI

/// Every mode family in the app, on one screen.
///
/// The IDE has six independent families — operation, inference route, MCP
/// execution, BitNet memory depth, cognition, Vera save approval — spread over
/// five settings screens. Met one at a time, each one looks like *the* mode
/// switch, and there is no way to tell from any single screen what a given
/// switch cannot affect. That is the actual reason configuring this app is
/// hard: not the number of options, but that they are never shown as a set.
///
/// The content is not written here. It is fetched from Vera's `list_modes`,
/// the same registry that answers the support bot and generates the settings
/// guide, so those three can never disagree about what a mode does. When a
/// Swift enum gains a case and the registry does not, Vera's own
/// `verify_against_source()` fails — the drift becomes a failing check rather
/// than a screen that quietly went stale.
struct ModesOverviewView: View {
    @EnvironmentObject var app: AppState

    @State private var families: [ModeFamilyDTO] = []
    @State private var loadState: LoadState = .loading

    enum LoadState: Equatable {
        case loading
        case ready
        /// Carries the reason. An empty list with no explanation is
        /// indistinguishable from "this app has no modes", which is worse
        /// than saying the registry could not be reached.
        case unavailable(String)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Divider().opacity(0.2)
            switch loadState {
            case .loading:
                loadingBody
            case .unavailable(let why):
                unavailableBody(why)
            case .ready:
                ScrollView {
                    VStack(alignment: .leading, spacing: 20) {
                        ForEach(families) { family in
                            familyCard(family)
                        }
                    }
                    .padding(16)
                }
            }
        }
        .task { await load() }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(app.t("Modes", "モード"))
                .font(.system(size: 15, weight: .bold))
            Text(app.t(
                "Six independent families. Each governs one thing only — "
                + "knowing which family a switch belongs to tells you what it "
                + "cannot change.",
                "独立した6つの群です。それぞれが担当するのは一つだけで、"
                + "どの群に属するかが分かると、その切り替えが「何を変えないか」も分かります。"))
                .font(.system(size: 11))
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
    }

    private var loadingBody: some View {
        HStack(spacing: 8) {
            ProgressView().scaleEffect(0.6)
            Text(app.t("Reading the settings registry…", "設定レジストリを読み込み中…"))
                .font(.system(size: 11)).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func unavailableBody(_ why: String) -> some View {
        VStack(spacing: 8) {
            Image(systemName: "exclamationmark.triangle")
                .font(.system(size: 22)).foregroundStyle(.orange)
            Text(app.t("The settings registry is not answering.",
                       "設定レジストリから応答がありません。"))
                .font(.system(size: 12, weight: .semibold))
            Text(why).font(.system(size: 11)).foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            Text(app.t("Check Settings › MCP — the `vera-memory` server "
                       + "provides this list.",
                       "設定 › MCP を確認してください。この一覧は `vera-memory` "
                       + "サーバーが提供しています。"))
                .font(.system(size: 11)).foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            Button(app.t("Retry", "再試行")) { Task { await load() } }
                .controlSize(.small)
        }
        .padding(24)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func familyCard(_ family: ModeFamilyDTO) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(app.t(family.titleEN, family.titleJA))
                    .font(.system(size: 13, weight: .bold))
                Spacer()
                Text("Settings › \(family.tab)")
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(.secondary)
            }
            Text(family.what)
                .font(.system(size: 11)).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            ForEach(family.options) { option in
                VStack(alignment: .leading, spacing: 3) {
                    Text(app.t(option.labelEN, option.labelJA))
                        .font(.system(size: 12, weight: .semibold))
                    Text(option.what)
                        .font(.system(size: 11))
                        .fixedSize(horizontal: false, vertical: true)
                    // The line that makes this a decision table rather than a
                    // glossary: a list of what each option does still leaves
                    // the reader guessing which one is theirs.
                    Text(app.t("Pick this when: ", "選ぶ場面: ") + option.when)
                        .font(.system(size: 10))
                        .foregroundStyle(Color.accentColor.opacity(0.9))
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(8)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.white.opacity(0.03))
                .clipShape(RoundedRectangle(cornerRadius: 6))
            }

            Text(family.source)
                .font(.system(size: 9, design: .monospaced))
                .foregroundStyle(.tertiary)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.white.opacity(0.05))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    private func load() async {
        loadState = .loading
        let raw = await MCPEngine.shared.callTool(
            serverName: "vera-memory", toolName: "list_modes", arguments: [:])
        guard let data = raw.data(using: .utf8),
              let parsed = try? JSONDecoder().decode([ModeFamilyDTO].self, from: data),
              !parsed.isEmpty else {
            loadState = .unavailable(String(raw.prefix(180)))
            return
        }
        families = parsed
        loadState = .ready
    }
}

// MARK: - Wire format
//
// Mirrors `all_modes()` in verantyx/settings_registry.py. Decoding rather than
// hand-parsing means a shape change fails here loudly instead of rendering a
// screen full of blanks.

struct ModeFamilyDTO: Decodable, Identifiable {
    let group: String
    let title: [String: String]
    let what: String
    let tab: String
    let source: String
    let options: [ModeOptionDTO]

    var id: String { group }
    var titleEN: String { title["en"] ?? group }
    var titleJA: String { title["ja"] ?? titleEN }
}

struct ModeOptionDTO: Decodable, Identifiable {
    let key: String
    let label: [String: String]
    let what: String
    let when: String

    var id: String { key }
    var labelEN: String { label["en"] ?? key }
    var labelJA: String { label["ja"] ?? labelEN }
}
