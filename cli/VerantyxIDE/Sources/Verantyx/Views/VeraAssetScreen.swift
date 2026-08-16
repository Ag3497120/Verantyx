import SwiftUI

/// The apps on this machine, as tools Vera may use and surfaces it may
/// show you things on.
///
/// This is the mode the whole "アプリ喰らい" idea lands in: the IDE stays
/// deliberately plain because it does not need to compete with the apps
/// already installed — it needs to USE them. An editor is where a file
/// gets edited, Preview is where a PDF gets shown to a person, and the
/// point of knowing they exist is that Vera can reach for one instead of
/// growing a worse copy of it inside itself.
///
/// Two things this screen exists to keep straight.
///
/// **Presence is a fact; ability is a claim.** That
/// `/Applications/Visual Studio Code.app` exists is checkable by looking.
/// That it can edit code is true, obvious, and still not something the
/// store may hold until a run witnessed it here. So the columns are
/// separate and never summed: `present` from a survey, `witnessed` from a
/// run that happened, `chosen` from a run that closed a need.
///
/// **Why an app was opened changes what counts as success.** Opening a
/// PDF so Vera can read it and opening it so you can look at it end in
/// the same `handedOff`, but the first is a dead end and the second is
/// the entire deliverable. `DelegationPurpose` carries that distinction
/// and `unknown` is graded strictly, so leaving it unclassified is never
/// the cheap option.
///
/// The engine has answered these questions since 2026-08-15 and nothing
/// in the IDE has ever asked them. This screen asks.
struct VeraAssetScreen: View {
    @EnvironmentObject var app: AppState
    @StateObject private var model = AssetScreenModel()
    @State private var need: String = "確認"

    /// The needs `assets_for` maps. A closed table, shown as one: a text
    /// field here would invite a need the door refuses, and a refusal you
    /// could have prevented is worse than a control that cannot make it.
    private let needs = ["編集", "実行", "確認", "検索", "版管理",
                         "設計", "文書", "表計算", "ビルド"]

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Divider().opacity(0.35)
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    forNeed
                    Divider().opacity(0.2)
                    inventory
                }
                .padding(16)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .task { await model.load(need: need) }
    }

    private var header: some View {
        HStack(spacing: 10) {
            Text("ASSETS")
                .font(.system(size: 11, weight: .semibold, design: .monospaced))
                .tracking(2.0).foregroundStyle(.secondary)
            Picker("", selection: $need) {
                ForEach(needs, id: \.self) { Text($0).tag($0) }
            }
            .frame(width: 130)
            .onChange(of: need) { _, n in Task { await model.load(need: n) } }
            Spacer()
            Button {
                Task { await model.survey() }
            } label: {
                Label("調べ直す", systemImage: "magnifyingglass")
                    .font(.system(size: 11))
            }
            .buttonStyle(.bordered)
            .help("このマシンを走査して在るものを記録する。"
                  + "在ることだけを書き、できることは書かない")
        }
        .padding(.horizontal, 14).padding(.vertical, 9)
    }

    // MARK: - この需要に対して

    private var forNeed: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("「\(need)」に使えるもの")
                .font(.system(size: 12, weight: .medium))

            if model.verdict == "UNKNOWN_NEED_NOT_MAPPED" {
                Text("この需要は表にありません。表は閉じています —"
                     + "推測で当てると、テストを走らせるのに Blender を"
                     + "自信満々で薦めることになります。")
                    .font(.system(size: 11)).foregroundStyle(.secondary)
            }

            band("採用済み", model.chosen, VeraInk.verified,
                 "この需要を実際に閉じた")
            band("証人あり", model.witnessed, VeraInk.verified,
                 "この種の仕事で成功した記録がある。繰り返せる")
            band("在るだけ", model.present, VeraInk.quiet,
                 "存在する。それ以上は主張しない — 一度も試していない")
            band("失敗した", model.failed, VeraInk.contested,
                 "試して駄目だった。次の計画が踏み込まないための記録")
        }
    }

    @ViewBuilder
    private func band(_ title: String, _ items: [String],
                      _ tint: Color, _ why: String) -> some View {
        if !items.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Rectangle().fill(tint).frame(width: 2, height: 10)
                    Text(title)
                        .font(.system(size: 10, weight: .semibold,
                                      design: .monospaced))
                        .tracking(1.2).foregroundStyle(.secondary)
                    Text(why).font(.system(size: 9))
                        .foregroundStyle(.tertiary)
                }
                ForEach(items, id: \.self) { a in
                    HStack(spacing: 8) {
                        Text(a).font(.system(size: 12, design: .monospaced))
                        Spacer()
                        // Two buttons, because the purpose changes what
                        // success means — and the classification is
                        // recorded with the outcome rather than inferred
                        // from it afterwards.
                        Button("Veraが使う") { open(a, purpose: .forVera) }
                            .buttonStyle(.link).font(.system(size: 11))
                        Button("見せてもらう") { open(a, purpose: .forHuman) }
                            .buttonStyle(.link).font(.system(size: 11))
                    }
                    .padding(.leading, 8)
                }
            }
        }
    }

    // MARK: - 在庫

    private var inventory: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("在庫").font(.system(size: 12, weight: .medium))
                Spacer()
                Text(model.surveyed.map { "\($0) 件" } ?? "未走査")
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(.tertiary)
            }
            Text("在ることだけを記録します。何ができるかは、"
                 + "この機械で実際に走ったときに初めて別の面として付きます。")
                .font(.system(size: 10)).foregroundStyle(.secondary)
            if !model.lastOutcome.isEmpty {
                Text(model.lastOutcome)
                    .font(.system(size: 11))
                    .padding(10)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(.quaternary.opacity(0.25),
                                in: RoundedRectangle(cornerRadius: 5))
            }
        }
    }

    private func open(_ asset: String, purpose: DelegationPurpose) {
        Task { await model.open(asset, need: need, purpose: purpose) }
    }
}

@MainActor
final class AssetScreenModel: ObservableObject {
    @Published private(set) var chosen: [String] = []
    @Published private(set) var witnessed: [String] = []
    @Published private(set) var present: [String] = []
    @Published private(set) var failed: [String] = []
    @Published private(set) var verdict: String = ""
    @Published private(set) var surveyed: Int?
    @Published private(set) var lastOutcome: String = ""

    func load(need: String) async {
        guard let obj = await VeraMemoryBridge.callDoor(
            "assets_for", ["need": need]) else { return }
        verdict = (obj["verdict"] as? String) ?? ""
        chosen = obj["chosen"] as? [String] ?? []
        failed = obj["failed_before"] as? [String] ?? []
        witnessed = names(obj["witnessed"])
        present = names(obj["present_untried"])
    }

    func survey() async {
        guard let obj = await VeraMemoryBridge.callDoor(
            "survey_assets", [:]) else { return }
        surveyed = obj["recorded"] as? Int ?? obj["assets"] as? Int
        lastOutcome = "走査しました。" +
            ((obj["note"] as? String) ?? "在ることだけを記録しています。")
    }

    /// Opening records its purpose with its outcome. `handedOff` means the
    /// app accepted the request and nothing more is observable from here —
    /// which is the whole result when the person is the audience, and a
    /// dead end when Vera needed to read something.
    func open(_ asset: String, need: String,
              purpose: DelegationPurpose) async {
        // The real path: build a request, let the licence book authorise or
        // refuse it, and file the evidence. Nothing here opens anything
        // directly — a screen that bypassed `perform` would also bypass the
        // record that says afterwards what actually ran.
        guard let target = DelegatedApp.allCases.first(where: {
            $0.displayName.lowercased() == asset.lowercased()
                || $0.rawValue.lowercased() == asset.lowercased()
        }) else {
            lastOutcome = "\(asset) は免許帳の対象アプリではありません。"
                + "在ることと、指揮してよいことは別です。"
            return
        }
        var request = DelegationRequest(
            app: target, verb: .open, payload: "",
            goal: "「\(need)」のため",
            // The person pressed the button, so the origin is `user`.
            // `model` and `observedContent` are graded differently and
            // borrowing the lenient one here would misfile the evidence.
            origin: .user)
        request.purpose = purpose
        let evidence = await AppDelegation.shared.perform(request)
        let worked = !evidence.outcome.isRefusal
        _ = await VeraMemoryBridge.callDoor("record_asset_outcome", [
            "need": need, "asset": asset, "worked": worked,
            "command": "open:" + asset + " (" + purpose.rawValue + ")",
            "result": String(describing: evidence.outcome)])
        lastOutcome = worked
            ? "\(asset) に渡しました（\(purpose.displayName)）。"
              + (purpose.handOffIsTheResult
                 ? "見せることが成果なので、これで完了です。"
                 : "受け取ったことしか分かりません — Veraが読めたかは別の証人が要ります。")
            : "\(asset) は開けませんでした。記録しています。"
        await load(need: need)
    }

    private func names(_ raw: Any?) -> [String] {
        if let a = raw as? [String] { return a }
        if let a = raw as? [[String: Any]] {
            return a.compactMap { $0["asset"] as? String }
        }
        return []
    }
}
