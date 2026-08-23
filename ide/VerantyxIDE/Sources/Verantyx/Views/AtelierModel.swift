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
                        "Pattern", "Solid", "Tech Pack"]
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

    // -- 設計図。**作図であって生成ではない** --------------------------
    @Published var drawSVG = ""
    /// 画面に描くための図形。**SVG と同じ数字から作られている** —
    /// macOS の NSImage が SVG の viewBox を再現しないことがあるので、
    /// 表示は自前で描き、SVG は書き出しの原本として持つ。
    @Published var drawShapes: [DrawShape] = []
    @Published var drawCanvas = CGSize(width: 1, height: 1)
    /// 図に載る文字。**SVG と同じ配列から作る** — 別々に書くと、
    /// 書き出した図と画面の図が違うものになる。
    @Published var drawLabels: [DrawLabel] = []
    @Published var drawSkipped: [String] = []
    @Published var drawDefaulted: [String] = []
    @Published var drawUnit = "cm"

    // -- 立体・ゆとり・サイズ展開。**着せない。比べる。** --------------
    @Published var solidVertices: [[Double]] = []
    @Published var solidFaces: [[Int]] = []
    @Published var solidGroups: [SolidGroup] = []
    @Published var solidSkipped: [String] = []
    @Published var solidAssumedDepth: Double = 0
    @Published var solidAssumedWhy = ""
    @Published var solidDisclaimer = ""

    @Published var bodySize = "M"
    @Published var easeRows: [EaseRow] = []
    /// 基準体そのもの。**着用者ではない。** ゆとりは服 − これ。
    /// これを出さないと、何から引いた差なのかが画面に無い。
    @Published var bodyRef: [String: Double] = [:]
    @Published var bodyRefNote = ""
    @Published var easeNegative: [String] = []
    @Published var easeDisclaimer = ""
    @Published var gradeSizes: [String] = []
    @Published var gradeBase = "M"
    @Published var gradeTable: [String: [GradeRow]] = [:]

    /// 裁断前に潰すことの一覧。**UNKNOWN は失敗ではなく、次に探すもの。**
    @Published var worklist: [WorkItem] = []

    /// 設計値の派生元。値を変えた後も、どこから来たかが残る。
    @Published var designTrail: [String: [DesignStep]] = [:]

    /// このコマがどの素材のどこから来たか。
    @Published var clipOrigins: [String: String] = [:]

    /// 平らな布を落としてみた結果。**型紙の前に、生地だけを試す口。**
    /// 生地の物性がおかしければ、縫っても直らない。
    @Published var drapeFabric = ""
    @Published var drapeVerdict = ""
    @Published var drapeChecks: [SewCheck] = []
    @Published var drapeWhyNoShape = ""
    /// 置いた仮定。**辞書のまま持つ** — String(describing:) に通すと
    /// 日本語が \Uxxxx に化けて画面に出ます(2026-08-23 実測)。
    @Published var drapeAssumed: [String: String] = [:]
    @Published var drapeBusy = false

    // -- 生地の性質と重ね着。**割れを隠さない** ------------------------
    @Published var fabricRows: [FabricRow] = []
    @Published var fabricCounts: [String: Int] = [:]
    @Published var clothEstimate: ClothEstimate?
    @Published var layerResult: LayerFit?

    // -- 型紙。**足りない寸法を既定で埋めない** ------------------------
    @Published var patternVerdict = ""
    @Published var patternMissing: [String] = []
    @Published var patternHowToClose = ""
    @Published var patternPieces: [PatternPiece] = []
    @Published var patternChecks: [SeamCheck] = []
    @Published var patternTotalArea: Double = 0
    @Published var patternSleeveMissing: [String] = []
    @Published var patternFormulas: [(String, String)] = []
    @Published var patternSeamAllowance = ""
    @Published var patternNotPublished = ""

    // -- 縫って落とす。**この一着を落とす唯一の口** ---------------------
    @Published var sewVerdict = ""
    @Published var sewPoints: [[Double]] = []
    @Published var sewOwner: [String] = []
    @Published var sewShapes: [[[Double]]] = []
    /// メッシュの辺。点だけ描くと布に見えない。
    @Published var sewEdges: [[Int]] = []
    @Published var sewSeams: [SewSeam] = []
    @Published var sewChecks: [SewCheck] = []
    @Published var sewWhyNoShape = ""
    @Published var sewBusy = false
    @Published var sewFabric = ""

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

    struct DrawShape: Identifiable {
        let id = UUID()
        var part = ""
        var points: [CGPoint] = []
    }

    struct DrawLabel: Identifiable {
        let id = UUID()
        var x: CGFloat = 0
        var y: CGFloat = 0
        var text = ""
        var tone = "ink"          // ink / warn / quiet
    }

    struct SolidGroup { var part = ""; var firstFace = 0; var faces = 0 }

    struct WorkItem: Identifiable {
        let id = UUID()
        var part = ""; var aspect = ""; var state = ""
        var howToClose = ""
    }

    struct DesignStep: Identifiable {
        let id = UUID()
        var stage = ""; var value = ""; var source = ""; var note = ""
    }

    struct EaseRow: Identifiable {
        let id = UUID()
        var spot = ""; var state = ""
        var garment: Double?
        var body: Double = 0
        var ease: Double?
        var unit = "cm"
        var fromDerived = false
        var howToClose = ""
    }

    struct GradeRow: Identifiable {
        let id = UUID()
        var spot = ""; var name = ""; var state = ""
        var value: Double?
        var unit = "cm"; var from = ""
        var howToClose = ""
    }

    struct FabricRow: Identifiable {
        let id = UUID()
        var fabric = ""; var prop = ""; var state = ""
        var value = ""
        var sources: [String] = []
        var sides: [(value: String, sources: [String])] = []
        var howToClose = ""
    }

    struct ClothEstimate {
        var fabric = ""; var state = ""
        var areaM2: Double = 0
        var gsm: Double?
        var weightG: Double?
        var from = ""; var howToClose = ""; var disclaimer = ""
    }

    struct LayerFit {
        var verdict = ""
        var slack: Double?
        var fits = false
        var thicknessAdds: Double = 0
        var missing: [String] = []
        var howToClose = ""; var disclaimer = ""
        var layers: [(fabric: String, thickness: Double?, state: String)] = []
    }

    struct PatternPiece: Identifiable {
        let id = UUID()
        var name = ""
        var outline: [CGPoint] = []
        var areaCm2: Double = 0
    }

    struct SeamCheck: Identifiable {
        let id = UUID()
        var label = ""; var a = ""; var b = ""
        var lengthA: Double = 0
        var lengthB: Double = 0
        var difference: Double = 0
        var tolerance: Double = 0
        var sewable = false
        var why = ""
    }

    struct SewSeam: Identifiable {
        let id = UUID()
        var seam = ""; var state = ""; var stitches = 0
        var lengthA: Double?; var lengthB: Double?
    }

    struct SewCheck: Identifiable {
        let id = UUID()
        var name = ""; var verdict = ""
        var difference: Double?
        var tolerance: Double?
        var detail = ""
        /// 「同じ形が揺れた」のか「別の形に落ちた」のか。形の中の距離で
        /// 分かる — 座標の差だけでは区別が付かない。
        var sameShapeMoved: Bool?
        var shapeDifference: Double?
        /// どのピースがどれだけ動いたか。一枚だけなら、そこを疑える。
        var byPiece: [String: Double] = [:]
        /// 許容の出どころ。選んだ数字か、何かから出した数字か。
        var toleranceFrom = ""
    }

    struct CrossArm {
        var part = ""; var aspect = ""; var sources = 0
    }

    struct Evidence: Identifiable {
        let id = UUID()
        var at = ""; var part = ""; var aspect = ""
        var value = ""; var kind = ""; var source = ""
        var note = ""; var adoptedBy = ""
        /// **開くための情報。** 「見に行ける」と出しながら開けないのは、
        /// 確かめられると言って確かめさせないのと同じ。
        var refStatus = ""; var refPath = ""; var refMark = ""
        var refURL = ""
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
        // 台帳を読んだら、そのつど「次に潰すこと」も引く。画面側で
        // counts の変化を見張ると、読み込みのたびに呼びが二重になる。
        await loadWorklist()
        let tl = await call("garment_timeline")
        timeline = (tl["timeline"] as? [[String: Any]] ?? []).map { row in
            let r = row["ref"] as? [String: Any] ?? [:]
            return Evidence(
                at: row["at"] as? String ?? "",
                part: row["part"] as? String ?? "",
                aspect: row["aspect"] as? String ?? "",
                value: row["value"] as? String ?? "",
                kind: row["kind"] as? String ?? "",
                source: row["source"] as? String ?? "",
                note: row["note"] as? String ?? "",
                adoptedBy: row["adopted_by"] as? String ?? "",
                refStatus: r["status"] as? String ?? "",
                refPath: r["path"] as? String ?? "",
                refMark: r["mark"] as? String ?? "",
                refURL: r["url"] as? String ?? "")
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

    /// 設計図を作る。**モデルは呼ばない** — 台帳にある確定項目と
    /// 寸法だけを決定的に描く。
    func loadDrawing() async {
        let d = await call("garment_draw")
        drawSVG = d["svg"] as? String ?? ""
        drawShapes = (d["shapes"] as? [[String: Any]] ?? []).map { row in
            DrawShape(part: row["part"] as? String ?? "",
                      points: (row["points"] as? [[Double]] ?? [])
                        .map { CGPoint(x: $0.first ?? 0, y: $0.count > 1 ? $0[1] : 0) })
        }
        drawLabels = (d["labels"] as? [[String: Any]] ?? []).map {
            DrawLabel(x: ($0["x"] as? Double) ?? 0,
                      y: ($0["y"] as? Double) ?? 0,
                      text: $0["text"] as? String ?? "",
                      tone: $0["tone"] as? String ?? "ink")
        }
        if let c = d["canvas"] as? [String: Any] {
            drawCanvas = CGSize(width: (c["width"] as? Double) ?? 1,
                                height: (c["height"] as? Double) ?? 1)
        }
        drawSkipped = (d["skipped"] as? [[String: Any]] ?? [])
            .compactMap { $0["part"] as? String }
        drawDefaulted = d["defaulted"] as? [String] ?? []
        drawUnit = d["unit"] as? String ?? "cm"
    }

    func saveDrawing(to path: String) async -> String {
        let d = await call("garment_draw_save", ["path": path])
        return (d["verdict"] as? String) ?? "UNKNOWN_NO_ANSWER"
    }

    /// 立体を組む。**着装シミュレーションではない。**
    func loadSolid() async {
        let d = await call("garment_solid")
        solidVertices = d["vertices"] as? [[Double]] ?? []
        solidFaces = d["faces"] as? [[Int]] ?? []
        solidGroups = (d["groups"] as? [[String: Any]] ?? []).map {
            SolidGroup(part: $0["part"] as? String ?? "",
                       firstFace: $0["first_face"] as? Int ?? 0,
                       faces: $0["faces"] as? Int ?? 0)
        }
        solidSkipped = (d["skipped"] as? [[String: Any]] ?? [])
            .compactMap { $0["part"] as? String }
        let a = d["assumed"] as? [String: Any] ?? [:]
        solidAssumedDepth = (a["depth_ratio"] as? Double) ?? 0
        solidAssumedWhy = a["why"] as? String ?? ""
        solidDisclaimer = d["not_a_simulation"] as? String ?? ""
    }

    func saveSolid(to path: String) async -> String {
        let d = await call("garment_solid_save", ["path": path])
        return (d["verdict"] as? String) ?? "UNKNOWN_NO_ANSWER"
    }

    /// ゆとり。**引き算であって着装計算ではない。**
    /// 基準体を引く。**着用者ではないと画面にも書く。**
    func loadBodyRef() async {
        let d = await call("body_reference", ["size": bodySize])
        bodyRef = d["measurements"] as? [String: Double] ?? [:]
        bodyRefNote = d["note"] as? String ?? ""
    }

    /// 裁断前に潰すことの一覧。
    func loadWorklist() async {
        let d = await call("garment_worklist")
        worklist = (d["worklist"] as? [[String: Any]] ?? []).map {
            WorkItem(part: $0["part"] as? String ?? "",
                     aspect: $0["aspect"] as? String ?? "",
                     state: $0["state"] as? String ?? "",
                     howToClose: $0["how_to_close"] as? String ?? "")
        }
    }

    /// 一項目の派生元。開いたときだけ引く — 全部を先に引く必要はない。
    func loadDesignTrail(part: String, aspect: String) async {
        let key = "\(part)/\(aspect)"
        let d = await call("design_history",
                           ["part": part, "aspect": aspect])
        designTrail[key] = (d["history"] as? [[String: Any]] ?? []).map {
            DesignStep(stage: $0["stage"] as? String
                           ?? $0["state"] as? String ?? "",
                       value: String(describing: $0["value"] ?? ""),
                       source: $0["source"] as? String ?? "",
                       note: $0["note"] as? String ?? "")
        }
    }

    /// このコマの出どころ。**紐づいていなければ、そう言う。**
    func loadClipOrigin(_ clipPath: String) async {
        let d = await call("intake_origin", ["clip_path": clipPath])
        if let o = d["origin"] as? [String: Any] {
            let src = o["source"] as? String ?? ""
            let at = o["at"] as? String ?? o["time"] as? String ?? ""
            clipOrigins[clipPath] = at.isEmpty ? src : "\(src) \(at)"
        } else {
            clipOrigins[clipPath] = d["verdict"] as? String
                ?? "UNKNOWN_CLIP_NOT_REGISTERED"
        }
    }

    /// 平らな布を落とす。**型紙は要らない。生地だけを測る。**
    func drapeValidate(fabric: String, iterations: Int = 400) async {
        drapeBusy = true
        drapeFabric = fabric
        defer { drapeBusy = false }
        let d = await call("drape_validate",
                           ["fabric": fabric, "iterations": iterations])
        drapeVerdict = d["verdict"] as? String ?? ""
        drapeWhyNoShape = d["why_no_shape"] as? String ?? ""
        drapeAssumed = d["assumed"] as? [String: String] ?? [:]
        drapeChecks = (d["checks"] as? [String: [String: Any]] ?? [:])
            .sorted { $0.key < $1.key }.map { key, v in
                SewCheck(name: key,
                         verdict: v["verdict"] as? String ?? "",
                         difference: v["worst_difference"] as? Double
                             ?? v["worst_strain"] as? Double
                             ?? v["last"] as? Double,
                         tolerance: v["tolerance"] as? Double,
                         detail: {
                             if let last = v["last"] as? Double,
                                let first = v["first"] as? Double {
                                 return String(format: "%.2f → %.2f",
                                               first, last)
                             }
                             return ""
                         }())
            }
    }

    func loadEase() async {
        let d = await call("body_ease", ["size": bodySize])
        easeRows = (d["rows"] as? [[String: Any]] ?? []).map { r in
            EaseRow(spot: r["spot"] as? String ?? "",
                    state: r["state"] as? String ?? "",
                    garment: r["garment"] as? Double,
                    body: (r["body"] as? Double) ?? 0,
                    ease: r["ease"] as? Double,
                    unit: r["unit"] as? String ?? "cm",
                    fromDerived: (r["from_derived"] as? Bool) ?? false,
                    howToClose: r["how_to_close"] as? String ?? "")
        }
        easeNegative = d["negative"] as? [String] ?? []
        easeDisclaimer = d["not_a_fit_calculation"] as? String ?? ""
    }

    /// サイズ展開。**振り分けで出た寸法は実測ではない。**
    func loadGrade() async {
        let d = await call("body_grade", ["base_size": gradeBase])
        gradeSizes = d["sizes"] as? [String] ?? []
        var out: [String: [GradeRow]] = [:]
        for (size, rows) in (d["table"] as? [String: [[String: Any]]] ?? [:]) {
            out[size] = rows.map { r in
                GradeRow(spot: r["spot"] as? String ?? "",
                         name: r["name"] as? String ?? "",
                         state: r["state"] as? String ?? "",
                         value: r["value"] as? Double,
                         unit: r["unit"] as? String ?? "cm",
                         from: r["from"] as? String ?? "",
                         howToClose: r["how_to_close"] as? String ?? "")
            }
        }
        gradeTable = out
    }

    /// 生地台帳。**出典が食い違うものは片方を勝たせない。**
    func loadFabrics() async {
        let d = await call("fabric_report")
        fabricCounts = (d["counts"] as? [String: Int]) ?? [:]
        fabricRows = (d["rows"] as? [[String: Any]] ?? []).map { r in
            FabricRow(
                fabric: r["fabric"] as? String ?? "",
                prop: r["prop"] as? String ?? "",
                state: r["state"] as? String ?? "",
                value: r["value"] as? String ?? "",
                sources: r["sources"] as? [String] ?? [],
                sides: (r["sides"] as? [[String: Any]] ?? []).map {
                    (value: $0["value"] as? String ?? "",
                     sources: $0["sources"] as? [String] ?? [])
                },
                howToClose: r["how_to_close"] as? String ?? "")
        }
    }

    func addFabric(fabric: String, prop: String, value: String,
                   source: String) async -> String {
        let d = await call("fabric_record",
                           ["fabric": fabric, "prop": prop,
                            "value": value, "source": source])
        await loadFabrics()
        return (d["verdict"] as? String) ?? "UNKNOWN_NO_ANSWER"
    }

    /// 面積から重さを見積もる。**必要量ではなく下限の目安。**
    func loadClothEstimate(fabric: String) async {
        let d = await call("fabric_cloth_estimate", ["fabric": fabric])
        clothEstimate = ClothEstimate(
            fabric: d["fabric"] as? String ?? fabric,
            state: d["state"] as? String ?? "",
            areaM2: (d["surface_area_m2"] as? Double) ?? 0,
            gsm: d["gsm"] as? Double,
            weightG: d["weight_g"] as? Double,
            from: d["from"] as? String ?? "",
            howToClose: d["how_to_close"] as? String ?? "",
            disclaimer: d["not_a_yardage"] as? String ?? "")
    }

    /// 外が内の上に入るか。**引き算であって着装計算ではない。**
    func loadLayerFit(inner: Double, outer: Double,
                      fabrics: [String]) async {
        let d = await call("fabric_layer_fit",
                           ["inner_girth": inner, "outer_girth": outer,
                            "fabrics": fabrics.joined(separator: ",")])
        layerResult = LayerFit(
            verdict: d["verdict"] as? String ?? "",
            slack: d["slack_cm"] as? Double,
            fits: (d["fits"] as? Bool) ?? false,
            thicknessAdds: (d["thickness_adds_cm"] as? Double) ?? 0,
            missing: d["missing"] as? [String] ?? [],
            howToClose: d["how_to_close"] as? String ?? "",
            disclaimer: d["not_a_drape"] as? String ?? "",
            layers: (d["layers"] as? [[String: Any]] ?? []).map {
                (fabric: $0["fabric"] as? String ?? "",
                 thickness: $0["thickness"] as? Double,
                 state: $0["state"] as? String ?? "")
            })
    }

    /// 型紙を引く。**縫い合わせの差を必ず読む。**
    func loadPattern() async {
        let d = await call("pattern_draft")
        patternVerdict = d["verdict"] as? String ?? ""
        patternMissing = d["missing"] as? [String] ?? []
        patternHowToClose = d["how_to_close"] as? String ?? ""
        patternSleeveMissing = d["sleeve_missing"] as? [String] ?? []
        patternTotalArea = (d["total_area_cm2"] as? Double) ?? 0
        patternSeamAllowance = d["seam_allowance"] as? String ?? ""
        patternNotPublished = d["not_a_published_system"] as? String ?? ""
        patternFormulas = (d["formulas"] as? [String: String] ?? [:])
            .sorted { $0.key < $1.key }.map { ($0.key, $0.value) }
        patternPieces = (d["pieces"] as? [[String: Any]] ?? []).map { p in
            PatternPiece(
                name: p["name"] as? String ?? "",
                outline: (p["outline"] as? [[Double]] ?? []).map {
                    CGPoint(x: $0.first ?? 0, y: $0.count > 1 ? $0[1] : 0)
                },
                areaCm2: (p["area_cm2"] as? Double) ?? 0)
        }
        patternChecks = (d["seam_checks"] as? [[String: Any]] ?? []).map { c in
            SeamCheck(label: c["label"] as? String ?? "",
                      a: c["a"] as? String ?? "",
                      b: c["b"] as? String ?? "",
                      lengthA: (c["length_a"] as? Double) ?? 0,
                      lengthB: (c["length_b"] as? Double) ?? 0,
                      difference: (c["difference"] as? Double) ?? 0,
                      tolerance: (c["tolerance"] as? Double) ?? 0,
                      sewable: (c["sewable"] as? Bool) ?? false,
                      why: c["why"] as? String ?? "")
        }
    }

    func savePattern(to path: String) async -> String {
        let d = await call("pattern_save", ["path": path])
        return (d["verdict"] as? String) ?? "UNKNOWN_NO_ANSWER"
    }

    /// 型紙を縫って落とす。**検査に通ったときだけ形が返る。**
    func sewAndDrape(fabric: String, iterations: Int = 600) async {
        sewBusy = true
        sewFabric = fabric
        defer { sewBusy = false }
        let d = await call("sew_and_drape",
                           ["fabric": fabric, "iterations": iterations])
        sewVerdict = d["verdict"] as? String ?? ""
        sewPoints = d["points"] as? [[Double]] ?? []
        sewOwner = d["owner"] as? [String] ?? []
        sewShapes = d["shapes"] as? [[[Double]]] ?? []
        sewEdges = d["edges"] as? [[Int]] ?? []
        sewWhyNoShape = d["why_no_shape"] as? String ?? ""
        sewSeams = (d["seams"] as? [[String: Any]] ?? []).map {
            SewSeam(seam: $0["seam"] as? String ?? "",
                    state: $0["state"] as? String ?? "",
                    stitches: $0["stitches"] as? Int ?? 0,
                    lengthA: $0["length_a"] as? Double,
                    lengthB: $0["length_b"] as? Double)
        }
        sewChecks = (d["checks"] as? [String: [String: Any]] ?? [:])
            .sorted { $0.key < $1.key }.map { key, v in
                SewCheck(name: key,
                         verdict: v["verdict"] as? String ?? "",
                         difference: v["worst_difference"]
                             as? Double ?? v["last"] as? Double,
                         tolerance: v["tolerance"] as? Double,
                         detail: {
                             if let last = v["last"] as? Double,
                                let first = v["first"] as? Double {
                                 return String(format: "%.2f → %.2f cm",
                                               first, last)
                             }
                             return ""
                         }(),
                         sameShapeMoved: v["same_shape_moved"] as? Bool,
                         shapeDifference: v["shape_difference"] as? Double,
                         byPiece: v["by_piece"] as? [String: Double] ?? [:],
                         toleranceFrom: v["tolerance_from"] as? String ?? "")
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
                // 「同じ参照を N 回読んだ」を落とさない。落とすと、
                // 畳んだ行が最初から1回だけの観測に見える。
                let note = e["note"] as? String ?? ""
                out.rows.append(.init(
                    label: at.isEmpty ? "—" : at,
                    value: "\(e["part"] as? String ?? "") / "
                        + "\(e["aspect"] as? String ?? "") — "
                        + "\(e["value"] as? String ?? "")  "
                        + "\(e["source"] as? String ?? "")"
                        + (note.isEmpty ? "" : "  [\(note)]"),
                    state: ""))
            }
            return out
        }
        showTechPack = true
    }
}
