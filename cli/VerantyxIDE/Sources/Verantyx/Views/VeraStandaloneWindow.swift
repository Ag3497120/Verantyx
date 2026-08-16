import SwiftUI

/// Vera's own windows, branched from the menu bar.
///
/// Why a second window rather than another pane
/// --------------------------------------------
/// The IDE is 262 files and 107,199 lines, and its view layer and its
/// agent layer grew on the same tree. Adding a Vera surface inside
/// `MainSplitView` would inherit that tree: today alone `SettingsView`
/// reached 123 KB and sat near the type-check timeout that already broke
/// CI once from `StereoCrossView`, and every new file has to be written
/// into `project.pbxproj` by hand because xcodegen would destroy it.
///
/// A separate `Window` scene inherits none of it. Everything below talks
/// to `VeraMemoryBridge` — the doors — and to nothing else. No
/// `AgentChatView`, no `MainSplitView`, no `SettingsView`. So the engine
/// is not migrated, no transport is added, and the tangle is simply not
/// entered.
///
/// Four MODES — ask it, put documents in it, configure it, look at its
/// shape — switched from one control at the top, which is the gesture the
/// app already uses on its other surfaces. One window rather than four
/// because these are four things to BE in, not four things to have open.
struct VeraStandaloneWindow: View {
    @EnvironmentObject var app: AppState
    @State private var mode: Mode = .ask

    enum Mode: String, CaseIterable, Identifiable {
        case ask = "対話", load = "投入", assets = "連携", settings = "設定", shape = "構造"
        var id: String { rawValue }
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 10) {
                Picker("", selection: $mode) {
                    ForEach(Mode.allCases) { Text($0.rawValue).tag($0) }
                }
                .pickerStyle(.segmented)
                .frame(width: 400)
                Spacer()
                if !app.veraDomain.isEmpty {
                    Text(app.veraDomain)
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(.secondary)
                    if app.veraDomainOnly {
                        Text("この分野のみ")
                            .font(.system(size: 9))
                            .padding(.horizontal, 5).padding(.vertical, 2)
                            .background(.quaternary, in: Capsule())
                    }
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 9)
            Divider().opacity(0.35)

            switch mode {
            case .ask:      VeraDialogueScreen().environmentObject(app)
            case .load:     VeraLoadScreen().environmentObject(app)
            case .settings: VeraOperatorConsole().environmentObject(app)
            case .assets:   VeraAssetScreen().environmentObject(app)
            case .shape:    VeraShapeScreen()
            }
        }
        .navigationTitle("Vera")
    }
}

/// One menu entry. `openWindow` is the environment action, not
/// a selector — a private selector that silently does nothing is exactly
/// the kind of dead wiring this project keeps finding a day later.
struct VeraWindowCommands: Commands {
    @Environment(\.openWindow) private var openWindow

    var body: some Commands {
        CommandGroup(after: .newItem) {
            Divider()
            Button("Vera を開く") { openWindow(id: "vera") }
                .keyboardShortcut("v", modifiers: [.command, .shift])
        }
    }
}

/// Putting documents in — the one screen that changes what Vera holds.
///
/// Both routes are on screen at once with their consequences beside them,
/// because the difference is not obvious from the outside and it is the
/// whole decision: one adds facts that vote, the other adds words that
/// only speak.
struct VeraLoadScreen: View {
    @EnvironmentObject var app: AppState
    @State private var name: String = ""
    @State private var body_: String = ""
    @State private var result: String = ""
    @State private var working = false

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("投入").font(.system(size: 13, weight: .semibold))

            Text("語彙として入れると、この文書の言葉でVeraが話せるようになります。"
                 + "文法は共有のままで、票は持ちません。")
                .font(.system(size: 11)).foregroundStyle(.secondary)

            TextField("分野名（英数字と _ のみ）", text: $name)
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 320)

            TextEditor(text: $body_)
                .font(.system(size: 12, design: .monospaced))
                .frame(minHeight: 200)
                .overlay(RoundedRectangle(cornerRadius: 4)
                    .strokeBorder(Color.primary.opacity(0.12)))

            HStack(spacing: 10) {
                Button(working ? "登録中…" : "語彙として登録") { load() }
                    .disabled(working || name.isEmpty || body_.count < 40)
                Text("40字以上・動詞5本以上で登録できます")
                    .font(.system(size: 10)).foregroundStyle(.tertiary)
            }

            if !result.isEmpty {
                Text(result).font(.system(size: 11))
                    .textSelection(.enabled)
                    .padding(10)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(.quaternary.opacity(0.25),
                                in: RoundedRectangle(cornerRadius: 5))
            }
            Spacer()
        }
        .padding(18)
    }

    private func load() {
        working = true
        let n = name, b = body_
        Task {
            let r = await VeraMemoryBridge.registerDomainText(n, text: b)
            await MainActor.run { result = r; working = false }
        }
    }
}

/// The shape of what Vera holds.
///
/// Currently the isometric cross — six arms (support/oppose,
/// cause/effect, general/instance) drawn on a flat canvas. It is NOT yet
/// three-dimensional, and saying so here is cheaper than letting a
/// reader assume the picture carries depth it does not have. The measured
/// structure a real 3D view must honour is on record: six arms, four
/// faces each, capacity 24 — which saturates exactly — and an untagged
/// facet, which belongs to no arm and must be drawn as attached to
/// nothing rather than quietly parked on one.
struct VeraShapeScreen: View {
    var body: some View {
        VStack(spacing: 12) {
            StereoCrossView(span: 420, showsLabels: true)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            Text("等角投影の平面図です。立体表示は未実装 — "
                 + "6腕×4面・容量24・untagged はどの腕にも属さない、"
                 + "という測定済みの構造に忠実に作る必要があります。")
                .font(.system(size: 10))
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.bottom, 14)
                .padding(.horizontal, 24)
        }
    }
}
