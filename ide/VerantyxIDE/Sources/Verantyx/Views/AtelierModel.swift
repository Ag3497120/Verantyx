import SwiftUI

/// Atelier の状態。**画面は状態を持たない** — 持っているのは Vera の台帳で、
/// ここはその読み出しと書き込みの口です。
///
/// 書き込み口は MCP の扉しかありません。`garment_observe`(見えた)、
/// `garment_infer`(推した)、`garment_propose`(外から来た)、
/// `garment_adopt`(人が採用した)。**モデルが「事実」を直接書ける道は
/// ありません** — クラウドの AI もローカルの LLM も、置けるのは提案まで。
@MainActor
final class AtelierModel: ObservableObject {
    static let steps = ["Sources", "Garments", "Evidence", "Structure",
                        "Materials", "Pattern", "Tech Pack"]
    /// 図に描ける部位。ここに無い部位は場所を持たないので、図ではなく
    /// チップで出す。**表に出ない部位を作らない**ための境目で、
    /// engine が部位を増やしても自動でチップ側に回る。
    static let spatial: Set<String> = ["collar", "sleeve", "body",
                                       "back", "pocket"]

    @Published var step = "Structure"
    @Published var view = "Front"
    @Published var tab = "Film"
    @Published var selected = "collar"
    @Published var anime = false
    @Published var loading = false
    @Published var projectName = "Black Coat"

    @Published var parts: [String: [String]] = [:]
    @Published var states: [String: AspectState] = [:]     // "part/aspect"
    @Published var counts: [String: Int] = [:]
    @Published var timeline: [Evidence] = []

    /// **エンジンが答えなかった**という事実。これを nil のままにして
    /// 空の台帳を描くと、「まだ観測していない」と「engine に届かなかった」が
    /// 同じ 0 に見える。不在と故障は違うものなので、別に持つ。
    @Published var engineError: String?

    @Published var showTechPack = false
    @Published var techPack: [TechSection] = []
    @Published var techPackNote = ""
    @Published var pendingAdopt: AdoptRequest?

    struct AspectState {
        var state = "UNKNOWN_NOT_OBSERVED"
        var value = ""
        var sources: [String] = []
        var basis: [String] = []
        var agreed = 0
        var adoptedBy = ""
        var howToClose = ""
        var sides: [Side] = []
        var proposals: [Proposal] = []
        struct Side { var value = ""; var sources: [String] = [] }
        struct Proposal { var value = ""; var source = ""; var note = "" }
    }

    struct Evidence {
        var at = ""; var part = ""; var aspect = ""
        var value = ""; var kind = ""; var source = ""
    }

    struct TechSection {
        var no = ""; var name = ""; var rows: [Row] = []
        struct Row { var label = ""; var value = ""; var state = "" }
    }

    struct AdoptRequest: Identifiable {
        var id: String { "\(part)/\(aspect)/\(value)" }
        let part: String
        let aspect: String
        let value: String
    }

    // MARK: - 扉

    private func call(_ tool: String,
                      _ args: [String: Any] = [:]) async -> [String: Any] {
        let raw = await MCPEngine.shared.callTool(
            serverName: "vera-memory", toolName: tool, arguments: args)
        guard let d = raw.data(using: .utf8),
              let o = (try? JSONSerialization.jsonObject(with: d))
                as? [String: Any] else {
            // 扉が開かなかった。ここで黙って [:] を返すと画面は 0 を描く。
            engineError = raw.isEmpty ? "engine から応答がありません" : raw
            return [:]
        }
        return o
    }

    func aspects(of part: String) -> [String] { parts[part] ?? [] }

    /// 場所を持たない部位。fabric/lining だけを決め打ちしていたとき、
    /// detail が画面のどこからも開けなくなっていた(実地で踏んだ)。
    var nonSpatial: [String] {
        parts.keys.filter { !Self.spatial.contains($0) }.sorted()
    }

    func state(_ part: String, _ aspect: String) -> AspectState {
        states["\(part)/\(aspect)"] ?? AspectState()
    }

    /// 部位の状態は**最も弱い側面に合わせる**。強い方に丸めると、
    /// 一つでも未観測が残っているのに緑に見えてしまう。
    func partState(_ part: String) -> String {
        let all = aspects(of: part).map { state(part, $0).state }
        if all.contains("CONTESTED") { return "CONTESTED" }
        if !all.isEmpty && all.allSatisfy({ $0 == "OBSERVED" }) {
            return "OBSERVED"
        }
        if all.contains("OBSERVED") || all.contains("INFERRED") {
            return "INFERRED"
        }
        return "UNKNOWN_NOT_OBSERVED"
    }

    /// 繋ぎ直して読み直す。ビルドで実体が入れ替わった瞬間の失敗は
    /// 残り続けるので、画面から一手で解けるようにしておく。
    func reconnect() async {
        let engine = MCPEngine.shared
        if let server = engine.servers.first(where: { $0.name == "vera-memory" }) {
            engine.disconnect(serverId: server.id)
            await engine.connect(server: server)
        }
        await load()
    }

    /// 台帳を読む前に、engine が**繋がるのを待つ**。
    ///
    /// 実地で踏んだ: アプリ起動と同時にこの画面が出ると、まだ接続が
    /// 済んでいない一瞬に読みに行って失敗し、その失敗が残り続ける。
    /// 動いているエンジンを前にして「届かない」と出るのは嘘なので、
    /// 繋がるまで待つ。待っても繋がらなければ、そのときは本当に
    /// 届いていないので、そう出す。
    private func waitForEngine(seconds: Double = 25) async {
        let engine = MCPEngine.shared
        let deadline = Date().addingTimeInterval(seconds)
        while Date() < deadline {
            guard let server = engine.servers.first(where: {
                $0.name == "vera-memory" && $0.isEnabled
            }) else {
                // サーバー定義そのものがまだ読み込まれていない
                try? await Task.sleep(nanoseconds: 400_000_000)
                continue
            }
            switch engine.connectionStatus[server.id] {
            case .connected: return
            case .connecting, .none:
                try? await Task.sleep(nanoseconds: 400_000_000)
            case .disconnected, .error:
                await engine.connect(server: server)
                if case .connected = engine.connectionStatus[server.id] {
                    return
                }
                try? await Task.sleep(nanoseconds: 600_000_000)
            }
        }
    }

    func load() async {
        loading = true
        engineError = nil
        defer { loading = false }
        await waitForEngine()
        let p = await call("garment_parts")
        if let table = p["parts"] as? [String: [String]] { parts = table }
        let spec = await call("garment_spec")
        if let t = spec["title"] as? String, !t.isEmpty { projectName = t }
        counts = (spec["counts"] as? [String: Int]) ?? [:]
        var next: [String: AspectState] = [:]
        for key in ["confirmed", "contested", "inferred", "open"] {
            for row in (spec[key] as? [[String: Any]] ?? []) {
                let part = row["part"] as? String ?? ""
                let aspect = row["aspect"] as? String ?? ""
                var s = AspectState()
                s.state = row["state"] as? String ?? "UNKNOWN_NOT_OBSERVED"
                s.value = row["value"] as? String ?? ""
                s.sources = row["sources"] as? [String] ?? []
                s.basis = row["basis"] as? [String] ?? []
                s.agreed = row["agreed"] as? Int ?? 0
                s.adoptedBy = row["adopted_by"] as? String ?? ""
                s.howToClose = row["how_to_close"] as? String ?? ""
                s.sides = (row["sides"] as? [[String: Any]] ?? []).map {
                    .init(value: $0["value"] as? String ?? "",
                          sources: $0["sources"] as? [String] ?? [])
                }
                s.proposals = (row["proposals"] as? [[String: Any]] ?? []).map {
                    .init(value: $0["value"] as? String ?? "",
                          source: $0["source"] as? String ?? "",
                          note: $0["note"] as? String ?? "")
                }
                next["\(part)/\(aspect)"] = s
            }
        }
        states = next
        let tl = await call("garment_timeline")
        timeline = (tl["timeline"] as? [[String: Any]] ?? []).map {
            .init(at: $0["at"] as? String ?? "",
                  part: $0["part"] as? String ?? "",
                  aspect: $0["aspect"] as? String ?? "",
                  value: $0["value"] as? String ?? "",
                  kind: $0["kind"] as? String ?? "",
                  source: $0["source"] as? String ?? "")
        }
    }

    func add(part: String, aspect: String, kind: String, value: String,
             source: String, note: String) async {
        let tool = ["observation": "garment_observe",
                    "inference": "garment_infer",
                    "proposal": "garment_propose"][kind] ?? "garment_propose"
        var args: [String: Any] = ["part": part, "aspect": aspect,
                                   "value": value, "note": note]
        // 推論の出所は「根拠」。名前が違うのは、観測の出典と混ぜないため。
        if tool == "garment_infer" {
            args["basis"] = source.isEmpty ? "(根拠未記入)" : source
            args.removeValue(forKey: "note")
        } else {
            args["source"] = source.isEmpty ? "(出典なし)" : source
        }
        _ = await call(tool, args)
        await load()
    }

    func adopt(_ req: AdoptRequest, by: String) async {
        _ = await call("garment_adopt", ["part": req.part,
                                         "aspect": req.aspect,
                                         "value": req.value, "by": by])
        pendingAdopt = nil
        await load()
    }

    func loadTechPack() async {
        let d = await call("garment_techpack")
        techPackNote = (d["note"] as? String) ?? ""
        techPack = (d["sections"] as? [[String: Any]] ?? []).map { sec in
            var out = TechSection(no: sec["no"] as? String ?? "",
                                  name: sec["name"] as? String ?? "")
            for r in (sec["rows"] as? [[String: Any]] ?? []) {
                out.rows.append(.init(label: r["label"] as? String ?? "",
                                      value: r["value"] as? String ?? "",
                                      state: r["state"] as? String ?? ""))
            }
            for (part, list) in (sec["parts"] as? [String: [[String: Any]]]
                                 ?? [:]).sorted(by: { $0.key < $1.key }) {
                for s in list {
                    let sides = (s["sides"] as? [[String: Any]] ?? [])
                        .compactMap { $0["value"] as? String }
                        .joined(separator: " / ")
                    out.rows.append(.init(
                        label: "\(part) / \(s["aspect"] as? String ?? "")",
                        value: (s["value"] as? String ?? "").isEmpty
                            ? sides : (s["value"] as? String ?? ""),
                        state: s["state"] as? String ?? ""))
                }
            }
            for e in (sec["timeline"] as? [[String: Any]] ?? []) {
                let at = e["at"] as? String ?? ""
                out.rows.append(.init(
                    label: at.isEmpty ? "—" : at,
                    value: "\(e["part"] as? String ?? "") / "
                        + "\(e["aspect"] as? String ?? "") — "
                        + "\(e["value"] as? String ?? "")  "
                        + "\(e["source"] as? String ?? "")",
                    state: ""))
            }
            return out
        }
        showTechPack = true
    }
}
