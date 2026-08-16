import SwiftUI

/// Bot mode as an operator's console — dense on purpose.
///
/// Every other surface in this app was stripped: the chrome went so that
/// a person would not have to learn a second vocabulary beside the one
/// they type. That was right for the modes where the work is a
/// conversation.
///
/// Bot mode is not one of those. It is the mode ABOUT the app, and the
/// person in it is configuring, registering and inspecting rather than
/// asking. For that work a clean screen is an obstacle: forty-nine
/// persisted settings exist and most have never had a control, so the
/// only way to see one has been to know its key. A console that shows
/// them all is not clutter here — it is the subject.
///
/// So the rule stays intact and its scope is named: chrome is absent from
/// the conversation surfaces, and present on the one surface whose
/// subject is the machine.
struct VeraOperatorConsole: View {
    @EnvironmentObject var app: AppState
    @StateObject private var model = OperatorConsoleModel()
    @State private var filter: String = ""
    @State private var section: Section = .domains

    enum Section: String, CaseIterable, Identifiable {
        case domains = "分野"
        case settings = "設定"
        case engine = "エンジン"
        var id: String { rawValue }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Divider().opacity(0.35)
            ScrollView {
                switch section {
                case .domains:  domainsBody
                case .settings: settingsBody
                case .engine:   engineBody
                }
            }
        }
        .task { await model.refresh() }
    }

    // MARK: - chrome

    private var header: some View {
        HStack(spacing: 10) {
            Text("OPERATOR")
                .font(.system(size: 11, weight: .semibold, design: .monospaced))
                .tracking(2.0)
                .foregroundStyle(.secondary)
            Picker("", selection: $section) {
                ForEach(Section.allCases) { Text($0.rawValue).tag($0) }
            }
            .pickerStyle(.segmented)
            .frame(width: 240)
            Spacer()
            // The settings button people asked for. It does not open a
            // second surface — it moves this one, because a console with a
            // modal on top of it is two places to look for one thing.
            Button {
                section = .settings
            } label: {
                Label("設定", systemImage: "slider.horizontal.3")
                    .font(.system(size: 11))
            }
            .buttonStyle(.bordered)
            .help("Vera の永続設定をすべて表示")
            TextField("絞り込み", text: $filter)
                .textFieldStyle(.roundedBorder)
                .frame(width: 180)
            Button {
                Task { await model.refresh() }
            } label: {
                Image(systemName: "arrow.clockwise").font(.system(size: 11))
            }
            .buttonStyle(.plain)
            .help("読み直す")
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 9)
    }

    // MARK: - 分野

    private var domainsBody: some View {
        VStack(alignment: .leading, spacing: 12) {
            // The switch an enterprise deployment actually sets. Layering
            // lets the shared vocabulary answer whenever a domain is
            // silent, which is right for reach and wrong the moment a
            // reader takes the sentence as the organisation's own.
            Toggle(isOn: $app.veraDomainOnly) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("この分野の外に出ない").font(.system(size: 12))
                    Text("共有語彙に落ちず UNKNOWN_NOT_IN_DOMAIN で断る。"
                         + "業務導入ではこちらが安全側")
                        .font(.system(size: 10)).foregroundStyle(.secondary)
                }
            }
            .toggleStyle(.switch)

            row("使用中の分野", app.veraDomain.isEmpty ? "（共有のみ）" : app.veraDomain)

            if model.domains.isEmpty {
                Text("登録された分野はありません。文書を添付し「分野」と答えると"
                     + "その語彙が登録されます（文法は共有のまま）。")
                    .font(.system(size: 11)).foregroundStyle(.secondary)
            } else {
                ForEach(model.domains, id: \.self) { d in
                    HStack {
                        Circle()
                            .fill(app.veraDomain == d ? VeraInk.verified : .clear)
                            .frame(width: 5, height: 5)
                        Text(d).font(.system(size: 12, design: .monospaced))
                        Spacer()
                        Button(app.veraDomain == d ? "解除" : "使う") {
                            app.veraDomain = (app.veraDomain == d) ? "" : d
                        }
                        .buttonStyle(.link).font(.system(size: 11))
                    }
                }
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: - 設定

    private var settingsBody: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("永続設定 \(shown.count) / \(model.settings.count) 件 — "
                 + "画面を持たないものも含めて全て")
                .font(.system(size: 10)).foregroundStyle(.secondary)
                .padding(.bottom, 8)
            ForEach(shown, id: \.key) { s in
                HStack(alignment: .top, spacing: 8) {
                    Text(s.key)
                        .font(.system(size: 11, design: .monospaced))
                        .frame(width: 230, alignment: .leading)
                        .textSelection(.enabled)
                    // A key holding a secret is shown as present, never as
                    // its value: this console is for operating the app, not
                    // for reading credentials off a shared screen.
                    Text(s.masked ? (s.value.isEmpty ? "—" : "●●●● (設定済み)")
                                  : (s.value.isEmpty ? "—" : s.value))
                        .font(.system(size: 11))
                        .foregroundStyle(s.value.isEmpty ? .tertiary : .primary)
                        .textSelection(.enabled)
                    Spacer()
                    Text(s.type)
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(.tertiary)
                }
                .padding(.vertical, 3)
                Divider().opacity(0.15)
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var shown: [OperatorConsoleModel.Setting] {
        let f = filter.trimmingCharacters(in: .whitespaces).lowercased()
        return f.isEmpty ? model.settings
            : model.settings.filter { $0.key.lowercased().contains(f) }
    }

    // MARK: - エンジン

    private var engineBody: some View {
        VStack(alignment: .leading, spacing: 8) {
            row("扉", model.doors.map { "\($0) 本" } ?? "—")
            row("核", model.cores.map(String.init) ?? "—")
            row("面", model.facets.map(String.init) ?? "—")
            row("モード", String(describing: app.veraEngineMode))
            Text(model.note).font(.system(size: 10))
                .foregroundStyle(.secondary).padding(.top, 6)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func row(_ k: String, _ v: String) -> some View {
        HStack {
            Text(k).font(.system(size: 11)).foregroundStyle(.secondary)
                .frame(width: 130, alignment: .leading)
            Text(v).font(.system(size: 12, design: .monospaced))
                .textSelection(.enabled)
            Spacer()
        }
    }
}

/// Reads what the console shows. Numbers come from the engine or from
/// UserDefaults; nothing here is invented, and a value the engine did not
/// return stays nil and renders as「—」rather than as a zero.
@MainActor
final class OperatorConsoleModel: ObservableObject {
    struct Setting: Hashable {
        let key: String
        let value: String
        let type: String
        let masked: Bool
    }

    @Published private(set) var domains: [String] = []
    @Published private(set) var settings: [Setting] = []
    @Published private(set) var doors: Int?
    @Published private(set) var cores: Int?
    @Published private(set) var facets: Int?
    @Published private(set) var note: String = ""

    /// Substrings that mark a value as a secret. Closed and matched on the
    /// KEY, because a value that looks harmless today may not tomorrow.
    private static let secret = ["api_key", "token", "secret", "password"]

    func refresh() async {
        settings = Self.readDefaults()
        if let obj = await VeraMemoryBridge.callDoor("vera_domains", [:]),
           let list = obj["domains"] as? [String] {
            domains = list
        }
        if let obj = await VeraMemoryBridge.callDoor("stats", [:]) {
            cores = obj["cores"] as? Int
            facets = obj["facets"] as? Int
            note = (obj["note"] as? String) ?? ""
        } else {
            note = "エンジンが応答しません。数値は表示しません（0とは書きません）。"
        }
    }

    private static func readDefaults() -> [Setting] {
        let d = UserDefaults.standard.dictionaryRepresentation()
        // Apple's own domains are in here too; the console is about this
        // app, so anything that is plainly system-owned is left out rather
        // than shown as if the operator could meaningfully change it.
        let skip = ["NS", "Apple", "com.apple", "AK", "WebKit", "PK"]
        return d.keys
            .filter { k in !skip.contains { k.hasPrefix($0) } }
            .sorted()
            .map { k in
                let v = d[k]
                return Setting(
                    key: k,
                    value: String(describing: v ?? "").prefix(120).description,
                    type: String(describing: type(of: v ?? "")),
                    masked: secret.contains { k.lowercased().contains($0) })
            }
    }
}
