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
                        "Materials", "Provenance", "Re-design",
                        "Pattern", "Tech Pack"]
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

    // -- 由来。**「オリジナル」という状態は無い** ---------------------
    @Published var rights: [String: RightsState] = [:]     // "part/aspect"
    @Published var rightsCounts: [String: Int] = [:]
    @Published var rightsWorklist: [RightsState] = []
    @Published var intent = "personal"
    @Published var legalAnswer = ""

    // -- 寸法。**映像から採寸はできない** -----------------------------
    @Published var measureRows: [MeasureRow] = []
    @Published var measureCounts: [String: Int] = [:]

    // -- 立体十字への配置(像であって台帳ではない) ----------------------
    @Published var crossGeneric: [CrossArm] = []
    @Published var crossSpecific: [CrossArm] = []
    @Published var crossAgree: Bool?
    @Published var crossOriginSplit: [String] = []

    // -- 設計。観測とは別の台帳 ---------------------------------------
    @Published var designRows: [DesignRow] = []
    @Published var designCounts: [String: Int] = [:]

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
        /// 後からこの行を**見に行けるか**。参照が付いていなければ false。
        /// false は「見ていない」ではなく「開き直せない」。
        var verifiable = false
        var unverifiableReason = ""
        var refs: [Ref] = []
        var sides: [Side] = []
        var proposals: [Proposal] = []
        struct Ref {
            var status = ""   // VERIFIABLE / UNKNOWN_SOURCE_NOT_FOUND / …
            var path = ""; var mark = ""; var url = ""; var source = ""
        }
        struct Side { var value = ""; var sources: [String] = [] }
        struct Proposal { var value = ""; var source = ""; var note = "" }
    }

    struct RightsState {
        var part = ""; var aspect = ""
        var state = "UNKNOWN_RIGHTS_NOT_CHECKED"
        var howToClose = ""
        var why = ""
        var genericSources: [String] = []
        var specificSources: [String] = []
        var searchedScopes: [String] = []
        var declaredBy: [String] = []
    }

    struct DesignRow {
        var part = ""; var aspect = ""; var value = ""
        var kind = ""              // kept / changed / new
        var derivedFrom = ""
        var originalValue = ""
        var by = ""
    }

    struct MeasureRow {
        var spot = ""; var name = ""; var state = ""
        var value: Double?
        var unit = ""; var from = ""; var howToClose = ""; var source = ""
    }

    struct CrossArm {
        var part = ""; var aspect = ""; var sources = 0
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
                s.verifiable = row["verifiable"] as? Bool ?? false
                s.unverifiableReason =
                    row["unverifiable_reason"] as? String ?? ""
                s.refs = (row["refs"] as? [[String: Any]] ?? []).map {
                    .init(status: $0["status"] as? String ?? "",
                          path: $0["path"] as? String ?? "",
                          mark: $0["mark"] as? String ?? "",
                          url: $0["url"] as? String ?? "",
                          source: $0["source"] as? String ?? "")
                }
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
        await loadRights()
        await loadDesign()
        await loadMeasures()
        await loadCross()
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

    private func rightsRow(_ o: [String: Any]) -> RightsState {
        var r = RightsState()
        r.part = o["part"] as? String ?? ""
        r.aspect = o["aspect"] as? String ?? ""
        r.state = o["state"] as? String ?? "UNKNOWN_RIGHTS_NOT_CHECKED"
        r.howToClose = o["how_to_close"] as? String ?? ""
        r.why = o["why"] as? String ?? ""
        r.genericSources = o["generic_sources"] as? [String] ?? []
        r.specificSources = o["specific_sources"] as? [String] ?? []
        r.searchedScopes = o["searched_scopes"] as? [String] ?? []
        r.declaredBy = o["declared_by"] as? String != nil
            ? [o["declared_by"] as! String]
            : (o["declared_by"] as? [String] ?? [])
        return r
    }

    func loadRights() async {
        let d = await call("rights_report")
        if let i = d["intent"] as? String { intent = i }
        rightsCounts = (d["counts"] as? [String: Int]) ?? [:]
        var next: [String: RightsState] = [:]
        for o in (d["rows"] as? [[String: Any]] ?? []) {
            let r = rightsRow(o)
            next["\(r.part)/\(r.aspect)"] = r
        }
        rights = next
        rightsWorklist = (d["worklist"] as? [[String: Any]] ?? [])
            .map(rightsRow)
    }

    func rightsState(_ part: String, _ aspect: String) -> RightsState {
        rights["\(part)/\(aspect)"] ?? RightsState(part: part, aspect: aspect)
    }

    /// 由来の申し立てを置く。claim は generic / specific / no_match /
    /// declared。**出典や範囲や名前が無いものは扉が断る** — ここで
    /// 補わない。
    func addRights(part: String, aspect: String, claim: String,
                   text: String, note: String) async -> String {
        let tool = ["generic": "rights_generic", "specific": "rights_specific",
                    "no_match": "rights_no_match",
                    "declared": "rights_declare"][claim] ?? "rights_generic"
        var args: [String: Any] = ["part": part, "aspect": aspect,
                                   "note": note]
        switch claim {
        case "no_match": args["scope"] = text
        case "declared": args["by"] = text
        default: args["source"] = text
        }
        let d = await call(tool, args)
        await loadRights()
        return (d["verdict"] as? String) ?? "UNKNOWN_NO_ANSWER"
    }

    func setIntent(_ value: String) async {
        _ = await call("rights_intent", ["intent": value])
        await loadRights()
    }

    /// 「作ってよいか」を訊く口。**答えは常に断り**で、それが仕様。
    func askLegal() async {
        let d = await call("rights_may_i_make_this")
        let v = (d["verdict"] as? String) ?? ""
        let why = (d["why"] as? String) ?? ""
        let how = (d["how_to_close"] as? String) ?? ""
        legalAnswer = "\(v)\n\(why)\n→ \(how)"
    }

    /// 寸法表。実測 / 計算値 / 未取得を混ぜずに読む。
    func loadMeasures() async {
        let d = await call("measure_sheet")
        measureCounts = (d["counts"] as? [String: Int]) ?? [:]
        var rows: [MeasureRow] = []
        for key in ["measured", "derived", "open"] {
            for o in (d[key] as? [[String: Any]] ?? []) {
                var r = MeasureRow()
                r.spot = o["spot"] as? String ?? ""
                r.name = o["name"] as? String ?? ""
                r.state = o["state"] as? String ?? ""
                r.value = o["value"] as? Double
                r.unit = o["unit"] as? String ?? ""
                r.from = o["from"] as? String ?? ""
                r.howToClose = o["how_to_close"] as? String ?? ""
                r.source = o["source"] as? String ?? ""
                rows.append(r)
            }
        }
        measureRows = rows
    }

    func addMeasure(spot: String, value: Double, unit: String,
                    source: String, by: String) async -> String {
        let d = await call("measure_taken",
                           ["spot": spot, "value": value, "unit": unit,
                            "source": source, "by": by])
        await loadMeasures()
        return (d["verdict"] as? String) ?? "UNKNOWN_NO_ANSWER"
    }

    func addRatio(spot: String, value: Double, basis: String,
                  source: String) async -> String {
        let d = await call("measure_ratio",
                           ["spot": spot, "value": value, "basis": basis,
                            "source": source])
        await loadMeasures()
        return (d["verdict"] as? String) ?? "UNKNOWN_NO_ANSWER"
    }

    /// 立体十字への配置。**台帳の像であって台帳ではない。**
    /// ここから台帳が書き換わることはない。
    func loadCross() async {
        let d = await call("garment_cross")
        func arms(_ key: String) -> [CrossArm] {
            let a = d["arms"] as? [String: Any] ?? [:]
            return (a[key] as? [[String: Any]] ?? []).map {
                .init(part: $0["part"] as? String ?? "",
                      aspect: $0["aspect"] as? String ?? "",
                      sources: $0["sources"] as? Int ?? 0)
            }
        }
        crossGeneric = arms("kind+ (一般)")
        crossSpecific = arms("kind- (実例)")
        let agreement = d["contested_agreement"] as? [String: Any] ?? [:]
        crossAgree = agreement["agree"] as? Bool
        let split = d["origin_split_agreement"] as? [String: Any] ?? [:]
        crossOriginSplit = ((split["cross"] as? [[Any]]) ?? []).map {
            $0.map { "\($0)" }.joined(separator: "/")
        }
    }

    func loadDesign() async {
        let d = await call("design_sheet")
        designCounts = (d["counts"] as? [String: Int]) ?? [:]
        designRows = (d["rows"] as? [[String: Any]] ?? []).map { o in
            var r = DesignRow()
            r.part = o["part"] as? String ?? ""
            r.aspect = o["aspect"] as? String ?? ""
            r.value = o["value"] as? String ?? ""
            r.kind = o["kind"] as? String ?? ""
            r.derivedFrom = o["derived_from"] as? String ?? ""
            r.originalValue = o["original_value"] as? String ?? ""
            r.by = o["by"] as? String ?? ""
            return r
        }
    }

    func design(_ action: String, part: String, aspect: String,
                value: String, by: String, note: String) async -> String {
        let tool = ["keep": "design_keep", "change": "design_change",
                    "new": "design_create"][action] ?? "design_keep"
        var args: [String: Any] = ["part": part, "aspect": aspect, "by": by]
        if action != "keep" { args["value"] = value; args["note"] = note }
        let d = await call(tool, args)
        await loadDesign()
        return (d["verdict"] as? String) ?? "UNKNOWN_NO_ANSWER"
    }

    func add(part: String, aspect: String, kind: String, value: String,
             source: String, note: String,
             refPath: String = "", refMark: String = "",
             refURL: String = "") async {
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
        // 参照は観測にだけ意味がある。推論や提案に付けても、
        // 「その推論を見に行く」ことはできない。
        if tool == "garment_observe" {
            args["ref_path"] = refPath
            args["ref_mark"] = refMark
            args["ref_url"] = refURL
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
