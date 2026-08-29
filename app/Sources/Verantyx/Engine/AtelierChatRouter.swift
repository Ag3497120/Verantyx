import Foundation

// MARK: - AtelierChatRouter
//
// UI B (「チャット画面プラス服飾ui」— owner's spec): the whole garment
// workbench stays on screen, and the chat pane beside it first compiles a
// closed garment command and otherwise decides where to look. Commands are
// previews only until the human approves their digest. No LLM participates.
//
// **The destination must come from something the engine can resolve, not
// from a model guessing** (owner's words, verbatim in the brief). Two
// resolution paths, both grounded:
//
//   1. A number span ("30番から35番", "30 to 35") is sent to the real
//      `pattern_span` MCP tool, the same door `AtelierModel` itself calls
//      for `pattern_where`/`pattern_numbers`. If it refuses (crosses
//      edges, unregistered number), that refusal is the answer; the
//      router does not fall back to guessing a step instead. This calls
//      MCPEngine directly rather than through an `AtelierModel` instance
//      — the chat pane in UI B sits OUTSIDE AtelierView's subtree and has
//      no reference to its private `@StateObject` model (see
//      `AtelierNavigator`'s doc comment), and the call needs nothing from
//      that instance beyond the door itself.
//   2. Anything else is checked against a fixed lexicon whose right-hand
//      side is always the literal name of a step in `AtelierModel.steps`
//      — the same array the step rail itself iterates. There is no way
//      to add a destination here that the rail cannot also reach by hand,
//      because the answer IS the rail's own list, not an invented one.
//
// Neither path calls a model. When neither matches, `resolve` returns
// `.none` and the caller must not move the view — a workbench that jumps
// somewhere arbitrary because a model felt like it is worse than one that
// stays put (owner's words).
@MainActor
enum AtelierChatRouter {

    /// Consume the UI operation identity. The image path remains the evidence
    /// identity, so a repeated selection clears stale analysis without adding
    /// another copy of the same source to the ledger.
    static func consumeSelectionRevision(_ revision: UInt64,
                                         imagePath: String) {
        GarmentFactoryReactController.shared.consumeImageSelection(
            revision: revision, imagePath: imagePath)
        GarmentGenerationJob.shared.consumeImageSelection(revision: revision)
    }

    struct Destination {
        let step: String
        let reasonEN: String
        let reasonJA: String
    }

    enum Resolution {
        /// Free model speech is visible but explicitly unverified. Any action
        /// result nested here came through the normal typed Vera boundary.
        indirect case modelGenerated(String, Resolution?)
        /// A real address was found; move to `Destination.step`.
        case moved(Destination)
        /// The engine was asked (a number span went to `pattern_span`)
        /// and it refused — a typed answer, not a guess, so it is shown
        /// as-is and the view does not move.
        case refused(String)
        /// A mutating command ran with commit=false and produced an immutable
        /// before/after preview. The workbench may move to its relevant step,
        /// but the active job has not changed.
        case preview(GarmentPreview, Destination?)
        /// A read-only command, approval, rejection, or undo completed.
        case answered(GarmentAnswerEnvelope, Destination?)
        /// The garment-factory ReAct foreman advanced to a deterministic
        /// pause/convergence point. The LLM text itself is never returned as
        /// this result; only the factory controller's typed report is shown.
        case factory(GarmentFactoryReactController.Report, Destination?)
        /// Nothing in the message named a place the engine or the step
        /// list can resolve. The view stays exactly where it is.
        case none
    }

    /// Right-hand side is always a member of `AtelierModel.steps` —
    /// `Self.validateLexicon()` below asserts that in DEBUG builds, so a
    /// typo here fails fast during development rather than silently
    /// routing nowhere in the field.
    private static let lexicon: [(words: [String], step: String)] = [
        (["生地", "素材", "布", "fabric", "material", "materials", "drape", "垂れ"],
         "Materials"),
        (["証拠", "根拠", "出典", "evidence", "witness"],
         "Evidence"),
        (["構造", "衿", "襟", "袖", "後ろ", "後身頃", "前身頃", "ポケット", "見返し",
          "collar", "sleeve", "pocket", "back panel", "structure"],
         "Structure"),
        (["由来", "権利", "オリジナル", "provenance", "rights", "origin"],
         "Provenance"),
        (["作り直", "変更案", "リデザイン", "re-design", "redesign"],
         "Re-design"),
        (["型紙", "裁断", "ノッチ", "縫い代", "パターン", "pattern", "notch",
          "seam allowance"],
         "Pattern"),
        (["立体", "ゆとり", "サイズ展開", "グレーディング", "ease", "grade",
          "solid", "mannequin", "マネキン"],
         "Solid"),
        (["仕様書", "テックパック", "tech pack", "techpack", "spec sheet"],
         "Tech Pack"),
        (["パーツ", "部位一覧", "garments", "parts list"],
         "Garments"),
        (["動画", "映像", "クリップ", "取り込み", "clip", "footage", "intake"],
         "Sources"),
    ]

    /// 「30番から35番」「30 to 35」「30-35」— 数字二つを繋ぐ語の**両側**
    /// に数字がある形だけを番号区間として読む。片方だけの数字("96cm"の
    /// ような実測値)を区間と誤読しないための境目。
    private static func numberSpan(in text: String) -> (Int, Int)? {
        let pattern = #"(\d+)\s*番?\s*(?:から|〜|~|-|–|to)\s*(\d+)\s*番?"#
        guard let re = try? NSRegularExpression(pattern: pattern) else { return nil }
        let ns = text as NSString
        guard let m = re.firstMatch(in: text, range: NSRange(location: 0, length: ns.length)),
              m.numberOfRanges == 3,
              let first = Int(ns.substring(with: m.range(at: 1))),
              let last = Int(ns.substring(with: m.range(at: 2)))
        else { return nil }
        return (first, last)
    }

    private static func stepNumber(_ step: String) -> Int {
        (AtelierModel.steps.firstIndex(of: step) ?? 0) + 1
    }

    /// Makes the doc comment on `lexicon` true: every right-hand side must
    /// name a real step. Called once from `resolve` under `#if DEBUG` —
    /// cheap (10 entries) and only runs in debug builds, so it costs
    /// nothing in release.
    private static func validateLexicon() {
        for (_, step) in lexicon {
            assert(AtelierModel.steps.contains(step),
                   "AtelierChatRouter.lexicon points at unknown step \"\(step)\"")
        }
    }

    /// Same door `AtelierModel`'s own private `call(_:_:)` uses — copied
    /// rather than shared because that one is `private` to the model and
    /// this router deliberately holds no reference to a model instance.
    private static func callDoor(_ tool: String, _ args: [String: Any]) async -> [String: Any] {
        let raw = await MCPEngine.shared.callTool(
            serverName: "vera-memory", toolName: tool, arguments: args)
        guard let d = raw.data(using: .utf8),
              let o = (try? JSONSerialization.jsonObject(with: d)) as? [String: Any]
        else { return ["verdict": "UNKNOWN_ENGINE_UNREACHABLE"] }
        return o
    }

    /// Garment command doors have one input shape only. Keeping every call in
    /// `json_text` prevents Swift-side convenience parameters from becoming a
    /// second, looser contract than docs/garment-generation-contract.md.
    private static func callJSONDoor(_ tool: String, json: String) async -> [String: Any] {
        await callDoor(tool, ["json_text": json])
    }

    private static func destination(for command: GarmentCommandIR) -> Destination? {
        guard let step = command.suggestedStep,
              AtelierModel.steps.contains(step) else { return nil }
        let n = stepNumber(step)
        let label = String(format: "→ %02d %@", n, step)
        return Destination(step: step, reasonEN: label, reasonJA: label)
    }

    private static func refusalText(_ refusal: GarmentCommandRefusal) -> String {
        [refusal.verdict, refusal.why, refusal.howToClose]
            .filter { !$0.isEmpty }.joined(separator: "\n")
    }

    private static func factoryRequest(_ command: GarmentCommandIR) -> String {
        var parts = [command.jsonString ?? command.intent.rawValue]
        if let requirements = GarmentGenerationJob.shared.approvedRequirementsContext() {
            parts.append("APPROVED_DESIGN_REQUIREMENTS=\(requirements)")
        }
        return parts.joined(separator: "\n")
    }

    // MARK: - RegionPicker -> visible-parts spatial bridge

    /// The image model names visible garment parts; it does not get to invent
    /// pixel coordinates.  This router-side bridge intersects those typed
    /// names with RegionPicker's bounded component geometry before the result
    /// enters the Vera factory.  Every binding remains a front-only PROPOSED
    /// hypothesis even when the source region was human-observed: the pixels
    /// can be OBSERVED while "this region is a cropped vest" is still model
    /// interpretation.
    private static let visionSpatialCandidateLimit = 1
    private static let visionSpatialPartLimit = 24
    private static let visionSpatialRegionLimit = 32
    private static let visionSpatialMinimumMatchScore = 0.18

    struct VisionSpatialBridgeOutput {
        let outline: [String: Any]
        let response: String
    }

    private struct VisionSpatialPreparedInput {
        let outline: [String: Any]
        let proposer: GarmentFactoryReactController.VisionProposer?
        let fashionRetrieval: [String: Any]
    }

    private struct VisionSpatialRect {
        let x: Double
        let y: Double
        let width: Double
        let height: Double

        var centerX: Double { x + width / 2 }
        var centerY: Double { y + height / 2 }
        var area: Double { max(0, width) * max(0, height) }

        func clipped() -> VisionSpatialRect {
            let x0 = min(1, max(0, x))
            let y0 = min(1, max(0, y))
            let x1 = min(1, max(x0, x + width))
            let y1 = min(1, max(y0, y + height))
            return .init(x: x0, y: y0, width: x1 - x0, height: y1 - y0)
        }
    }

    private struct VisionSpatialRegion {
        let id: String
        let rect: VisionSpatialRect
        let red: Double
        let green: Double
        let blue: Double
        let state: String
    }

    private struct VisionSpatialPart {
        let index: Int
        let id: String
        let kind: String
        let semanticRole: String
        let visibleColor: String
        let side: String
        let layer: Int
        let prior: VisionSpatialRect
        let zone: String
    }

    private struct VisionSpatialMatch {
        let partIndex: Int
        let regionIndex: Int
        let score: Double
    }

    @MainActor
    private final class VisionSpatialResponseReplay {
        private var first: String?

        init(_ first: String?) { self.first = first }

        func take() -> String? {
            defer { first = nil }
            return first
        }
    }

    /// Perform at most one up-front vision call.  The controller receives a
    /// replay closure, so that call is not duplicated; its own existing single
    /// repair attempt remains the only retry.  If the model or bridge cannot
    /// produce a valid compact object, the original response is replayed and
    /// the controller's typed parser fails closed as before.
    private static func prepareVisionSpatialInput(
        outline: [String: Any], imagePath: String, userRequest: String,
        pick: AtelierAnalyst.Pick
    ) async -> VisionSpatialPreparedInput {
        async let fashionRetrieval =
            GarmentFactoryReactController.shared.proposeInitialFashionSimilarity(
                imagePath: imagePath)
        guard let base = GarmentFactoryModelMouth.visionProposer(for: pick) else {
            return .init(
                outline: outline, proposer: nil,
                fashionRetrieval: await fashionRetrieval)
        }
        async let rawProposal = base(
            visionSpatialPrompt(userRequest: userRequest), imagePath)
        let raw = await rawProposal
        let bridged = raw.flatMap {
            bridgeVisionVisibleParts($0, outline: outline)
        }
        let replay = VisionSpatialResponseReplay(bridged?.response ?? raw)
        let enrichedOutline = bridged?.outline ?? outline
        let wrapped: GarmentFactoryReactController.VisionProposer = { prompt, path in
            if let cached = replay.take() { return cached }
            guard let repaired = await base(prompt, path) else { return nil }
            return bridgeVisionVisibleParts(repaired, outline: outline)?.response
                ?? repaired
        }
        return .init(
            outline: enrichedOutline, proposer: wrapped,
            fashionRetrieval: await fashionRetrieval)
    }

    private static func visionSpatialPrompt(userRequest: String) -> String {
        """
        Inspect only the visible FRONT garment pixels. Return JSON only:
        {"candidates":[{"candidate_id":"visible-front",
        "back_design":"PROPOSED; rear not visible",
        "assumptions":["rear, depth, material, dimensions and sewing are unknown"],
        "parts":[{"part_id":"stable-id","kind":"BODY_SHELL","layer":0,
        "semantic_role":"blouse, cropped vest, left trouser leg, right trouser leg, or overlay",
        "visible_color":"front pixel colour","placement":"visible front zone",
        "image_side":"left, center, right, or bilateral","garment_unit":"object-id",
        "attached_to":null,"visible_basis":"pixel-visible cue","dimensions":{}}]}]}
        Return exactly one candidate and no more than 24 visible garment parts.
        Keep a blouse and independently wearable vest as separate BODY_SHELL
        units; keep left and right trouser legs as separate TUBE parts; keep a
        sheer wrap or overskirt as a separate OVERLAY above those trousers.
        Include visible sleeves, collars, yokes, bands, openings, frills and
        ornaments. Exclude body, skin, hair, footwear, background and props.
        Do not output pixel coordinates: deterministic RegionPicker geometry
        will supply them. Do not infer rear construction, centimetres, material,
        sewing, strength, comfort, approval, observation or manufacturability.
        USER REQUEST: \(userRequest)
        """
    }

    /// Functional seam used by router tests.  The returned JSON is still a
    /// model proposal, but each visible part now carries a deterministic
    /// front-spatial record.  The same records are attached to the outline
    /// envelope consumed by the factory event, without changing any existing
    /// RegionPicker authority state.
    static func bridgeVisionVisibleParts(
        _ raw: String, outline: [String: Any]
    ) -> VisionSpatialBridgeOutput? {
        guard var object = firstJSONObject(in: raw),
              let candidates = object["candidates"] as? [[String: Any]],
              let sourceCandidate = candidates.prefix(visionSpatialCandidateLimit)
                .first(where: { ($0["parts"] as? [[String: Any]])?.isEmpty == false }),
              let sourceParts = sourceCandidate["parts"] as? [[String: Any]],
              !sourceParts.isEmpty else { return nil }

        let width = positiveDouble(outline["width_px"] ?? outline["width"]) ?? 1
        let height = positiveDouble(outline["height_px"] ?? outline["height"]) ?? 1
        let regions = spatialRegions(from: outline, width: width, height: height)
        let boundedParts = Array(sourceParts.prefix(visionSpatialPartLimit))
        let typedParts = boundedParts.enumerated().compactMap {
            spatialPart(from: $0.element, index: $0.offset)
        }
        guard !typedParts.isEmpty else { return nil }

        var matches: [VisionSpatialMatch] = []
        for part in typedParts {
            for (regionIndex, region) in regions.enumerated() {
                matches.append(.init(
                    partIndex: part.index, regionIndex: regionIndex,
                    score: spatialMatchScore(part: part, region: region)))
            }
        }
        matches.sort {
            if $0.score != $1.score { return $0.score > $1.score }
            if $0.partIndex != $1.partIndex { return $0.partIndex < $1.partIndex }
            return regions[$0.regionIndex].id < regions[$1.regionIndex].id
        }
        var assignedRegions = Set<Int>()
        var regionForPart: [Int: Int] = [:]
        for match in matches where match.score >= visionSpatialMinimumMatchScore {
            guard regionForPart[match.partIndex] == nil,
                  assignedRegions.insert(match.regionIndex).inserted else { continue }
            regionForPart[match.partIndex] = match.regionIndex
        }

        let typedByIndex = Dictionary(uniqueKeysWithValues: typedParts.map {
            ($0.index, $0)
        })
        var proposals: [[String: Any]] = []
        var outputParts: [[String: Any]] = []
        for (index, source) in boundedParts.enumerated() {
            var part = source
            guard let typed = typedByIndex[index] else {
                outputParts.append(part)
                continue
            }
            let regionIndex = regionForPart[index]
            let region = regionIndex.map { regions[$0] }
            let rect = (region?.rect ?? typed.prior).clipped()
            let score = regionIndex.map {
                spatialMatchScore(part: typed, region: regions[$0])
            }
            let sourceIDs = region.map { [$0.id] } ?? []
            let sourceStates = region.map { [$0.state] } ?? []
            let proposal: [String: Any] = [
                "schema": "garment.front-spatial-proposal.v1",
                "part_id": typed.id,
                "kind": typed.kind,
                "semantic_role": typed.semanticRole,
                "side": typed.side,
                "layer": typed.layer,
                "zone": typed.zone,
                "state": "PROPOSED",
                "authority": "PROPOSED",
                "front_only": true,
                "coordinate_frame": "IMAGE_TOP_LEFT",
                "rear_observed": false,
                "dimensions_inferred_from_pixels": false,
                "bbox_normalized": rectDictionary(rect),
                "bbox_px": pixelRectDictionary(rect, width: width, height: height),
                "source_region_ids": sourceIDs,
                "source_region_states": sourceStates,
                "deterministic_match_score": score ?? 0,
                "match_score_is_probability": false,
                "geometry_source": region == nil
                    ? "TYPED_FRONT_ZONE_PRIOR_NO_REGION_MATCH"
                    : "REGIONPICKER_COMPONENT_X_TYPED_FRONT_ZONE",
                "basis": region == nil
                    ? "typed visible-part role projected into a bounded front zone; no RegionPicker component passed the deterministic threshold"
                    : "RegionPicker geometry matched to a model-proposed visible role by bounded overlap, position and front-pixel colour rules",
                "unobserved": ["rear", "depth", "material", "dimensions", "sewing"],
            ]
            proposals.append(proposal)
            part["front_spatial_proposal"] = proposal
            if part["placement"] as? String == nil {
                part["placement"] = "front \(typed.zone)"
            }
            if part["side"] as? String == nil, typed.side != "center" {
                part["side"] = typed.side
            }
            let originalBasis = (part["visible_basis"] as? String)?
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            let regionBasis = sourceIDs.isEmpty
                ? "no RegionPicker component matched"
                : "RegionPicker \(sourceIDs.joined(separator: ","))"
            part["visible_basis"] = [originalBasis,
                "PROPOSED front spatial binding: \(regionBasis); semantic assignment and all hidden construction remain unobserved"]
                .filter { !$0.isEmpty }.joined(separator: " | ")
            outputParts.append(part)
        }

        guard !proposals.isEmpty else { return nil }
        var candidate = sourceCandidate
        candidate["parts"] = outputParts
        candidate["back_design"] = "PROPOSED; rear not visible in the source front image"
        candidate["rear_authority"] = "UNKNOWN_UNOBSERVED"
        candidate["rear_observed"] = false
        candidate["manufacturing_ready"] = false
        candidate["manufacturing_certified"] = false
        var assumptions = (candidate["assumptions"] as? [String] ?? [])
            .prefix(8).map { String($0.prefix(240)) }
        assumptions.append(
            "front spatial bindings are PROPOSED; rear, depth, material, dimensions and sewing remain unknown")
        if sourceParts.count > visionSpatialPartLimit {
            assumptions.append(
                "visible part proposal was bounded to \(visionSpatialPartLimit) entries before Vera validation")
        }
        candidate["assumptions"] = Array(Set(assumptions)).sorted()
        object["candidates"] = [candidate]
        object["router_spatial_bridge"] = [
            "schema": "garment.front-spatial-bridge.v1",
            "state": "PROPOSED",
            "front_only": true,
            "candidate_limit": visionSpatialCandidateLimit,
            "part_limit": visionSpatialPartLimit,
            "region_limit": visionSpatialRegionLimit,
            "rear_observed": false,
            "authority_rule": "RegionPicker geometry may retain OBSERVED; model-to-part semantic binding is always PROPOSED",
        ]

        var enrichedOutline = outline
        enrichedOutline["front_spatial_proposals"] = proposals
        enrichedOutline["front_spatial_bridge"] = object["router_spatial_bridge"]
        if var rows = outline["regions"] as? [[String: Any]] {
            for rowIndex in rows.indices {
                guard let regionID = rows[rowIndex]["region_id"] as? String else { continue }
                let partIDs = proposals.compactMap { proposal -> String? in
                    guard let ids = proposal["source_region_ids"] as? [String],
                          ids.contains(regionID) else { return nil }
                    return proposal["part_id"] as? String
                }.sorted()
                guard !partIDs.isEmpty else { continue }
                // Deliberately leave rows[rowIndex]["state"] untouched.
                rows[rowIndex]["proposed_part_ids"] = partIDs
                rows[rowIndex]["semantic_assignment_state"] = "PROPOSED"
                rows[rowIndex]["semantic_assignment_front_only"] = true
                rows[rowIndex]["rear_observed"] = false
            }
            enrichedOutline["regions"] = rows
        }
        guard JSONSerialization.isValidJSONObject(object),
              let data = try? JSONSerialization.data(
                withJSONObject: object, options: [.sortedKeys]),
              let response = String(data: data, encoding: .utf8) else { return nil }
        return .init(outline: enrichedOutline, response: response)
    }

    private static func spatialRegions(
        from outline: [String: Any], width: Double, height: Double
    ) -> [VisionSpatialRegion] {
        let rows = outline["regions"] as? [[String: Any]] ?? []
        let parsed = rows.compactMap { row -> VisionSpatialRegion? in
            guard let id = row["region_id"] as? String,
                  let box = row["bounding_box"] as? [String: Any],
                  let x = finiteDouble(box["x"]),
                  let y = finiteDouble(box["y"]),
                  let w = positiveDouble(box["width"]),
                  let h = positiveDouble(box["height"]) else { return nil }
            let rgba = row["average_rgba"] as? [String: Any] ?? [:]
            return .init(
                id: id,
                rect: .init(x: x / width, y: y / height,
                            width: w / width, height: h / height).clipped(),
                red: (finiteDouble(rgba["red"]) ?? 127.5) / 255,
                green: (finiteDouble(rgba["green"]) ?? 127.5) / 255,
                blue: (finiteDouble(rgba["blue"]) ?? 127.5) / 255,
                state: (row["state"] as? String)?.uppercased() == "OBSERVED"
                    ? "OBSERVED" : "PROPOSED")
        }.sorted {
            if $0.rect.area != $1.rect.area { return $0.rect.area > $1.rect.area }
            return $0.id < $1.id
        }
        return Array(parsed.prefix(visionSpatialRegionLimit))
    }

    private static func spatialPart(
        from row: [String: Any], index: Int
    ) -> VisionSpatialPart? {
        let allowed = Set([
            "BODY_SHELL", "TUBE", "FLARE", "FRUSTUM", "SLEEVE", "BAND",
            "OVERLAY", "COLLAR", "YOKE", "GORE", "GUSSET", "OPENING",
            "DRAPE_ANCHOR", "BOW", "RIBBON", "ROSETTE", "TIE", "FLAP",
            "RUFFLE", "FRILL",
        ])
        guard let rawKind = row["kind"] as? String else { return nil }
        let kind = rawKind.uppercased()
        guard allowed.contains(kind) else { return nil }
        let id = (row["part_id"] as? String)?.trimmingCharacters(
            in: .whitespacesAndNewlines)
        guard let id, !id.isEmpty, id.count <= 80 else { return nil }
        let role = ((row["semantic_role"] as? String)
            ?? (row["placement"] as? String) ?? kind.lowercased())
        let color = (row["visible_color"] as? String) ?? ""
        let text = [role, row["placement"] as? String,
                    row["detail_role"] as? String, kind]
            .compactMap { $0 }.joined(separator: " ").lowercased()
        let side = spatialSide(row: row, text: text)
        let layer = max(0, min((row["layer"] as? NSNumber)?.intValue ?? 0, 15))
        let prior = spatialPrior(kind: kind, text: text, side: side)
        return .init(index: index, id: id, kind: kind,
                     semanticRole: String(role.prefix(120)),
                     visibleColor: String(color.prefix(80)), side: side,
                     layer: layer, prior: prior.rect, zone: prior.zone)
    }

    private static func spatialSide(row: [String: Any], text: String) -> String {
        let raw = ((row["image_side"] as? String) ?? (row["side"] as? String) ?? "")
            .lowercased()
        if raw.contains("bilateral") || raw.contains("both") || text.contains("bilateral") {
            return "bilateral"
        }
        if raw.contains("left") || raw.contains("左") || text.contains(" left ")
            || text.hasPrefix("left ") || text.contains("左") { return "left" }
        if raw.contains("right") || raw.contains("右") || text.contains(" right ")
            || text.hasPrefix("right ") || text.contains("右") { return "right" }
        return "center"
    }

    private static func spatialPrior(
        kind: String, text: String, side: String
    ) -> (rect: VisionSpatialRect, zone: String) {
        func sided(_ left: VisionSpatialRect, _ right: VisionSpatialRect,
                   _ center: VisionSpatialRect) -> VisionSpatialRect {
            side == "left" ? left : (side == "right" ? right : center)
        }
        if kind == "COLLAR" || kind == "YOKE" || text.contains("neck")
            || text.contains("襟") || text.contains("衿") {
            return (.init(x: 0.30, y: 0.08, width: 0.40, height: 0.24), "upper-neck")
        }
        if kind == "SLEEVE" || text.contains("sleeve") || text.contains("袖") {
            return (sided(.init(x: 0.04, y: 0.18, width: 0.34, height: 0.52),
                          .init(x: 0.62, y: 0.18, width: 0.34, height: 0.52),
                          .init(x: 0.04, y: 0.18, width: 0.92, height: 0.52)),
                    "upper-limb")
        }
        let trouser = kind == "TUBE" || text.contains("trouser")
            || text.contains("pants") || text.contains("legging")
            || text.contains("ズボン") || text.contains("パンツ")
        if trouser {
            return (sided(.init(x: 0.20, y: 0.47, width: 0.31, height: 0.50),
                          .init(x: 0.49, y: 0.47, width: 0.31, height: 0.50),
                          .init(x: 0.20, y: 0.47, width: 0.60, height: 0.50)),
                    "lower-leg")
        }
        let lowerOverlay = kind == "FLARE" || kind == "FRUSTUM"
            || kind == "GORE" || text.contains("skirt")
            || text.contains("wrap") || text.contains("overskirt")
            || text.contains("スカート") || text.contains("ラップ")
        if lowerOverlay {
            return (sided(.init(x: 0.10, y: 0.40, width: 0.55, height: 0.56),
                          .init(x: 0.35, y: 0.40, width: 0.55, height: 0.56),
                          .init(x: 0.13, y: 0.40, width: 0.74, height: 0.56)),
                    "lower-overlay")
        }
        if kind == "BAND" || text.contains("belt") || text.contains("waist")
            || text.contains("ベルト") || text.contains("ウエスト") {
            return (.init(x: 0.18, y: 0.40, width: 0.64, height: 0.16), "waist-band")
        }
        if kind == "OVERLAY" {
            return (sided(.init(x: 0.08, y: 0.18, width: 0.56, height: 0.72),
                          .init(x: 0.36, y: 0.18, width: 0.56, height: 0.72),
                          .init(x: 0.14, y: 0.18, width: 0.72, height: 0.72)),
                    "front-overlay")
        }
        if text.contains("vest") || text.contains("ベスト") {
            return (.init(x: 0.24, y: 0.17, width: 0.52, height: 0.34), "upper-cropped-shell")
        }
        if kind == "BODY_SHELL" {
            return (.init(x: 0.20, y: 0.15, width: 0.60, height: 0.45), "upper-torso")
        }
        return (sided(.init(x: 0.12, y: 0.18, width: 0.42, height: 0.48),
                      .init(x: 0.46, y: 0.18, width: 0.42, height: 0.48),
                      .init(x: 0.24, y: 0.20, width: 0.52, height: 0.42)),
                "front-detail")
    }

    private static func spatialMatchScore(
        part: VisionSpatialPart, region: VisionSpatialRegion
    ) -> Double {
        let a = part.prior.clipped(), b = region.rect.clipped()
        let ix = max(0, min(a.x + a.width, b.x + b.width) - max(a.x, b.x))
        let iy = max(0, min(a.y + a.height, b.y + b.height) - max(a.y, b.y))
        let overlap = (ix * iy) / max(0.000_001, min(a.area, b.area))
        let distance = sqrt(pow(a.centerX - b.centerX, 2)
            + pow(a.centerY - b.centerY, 2))
        let position = max(0, 1 - distance / 0.85)
        let size = min(1, b.area / max(0.000_001, a.area))
        let color = colorMatchScore(part.visibleColor, region: region)
        return rounded(0.50 * overlap + 0.25 * position
            + 0.20 * color + 0.05 * size)
    }

    private static func colorMatchScore(
        _ raw: String, region: VisionSpatialRegion
    ) -> Double {
        let text = raw.lowercased()
        let named: [(words: [String], rgb: (Double, Double, Double))] = [
            (["white", "ivory", "cream", "白", "アイボリー"], (0.94, 0.92, 0.84)),
            (["navy", "dark blue", "濃紺", "紺"], (0.08, 0.12, 0.24)),
            (["red", "rust", "terracotta", "赤", "レンガ"], (0.63, 0.18, 0.12)),
            (["teal", "cyan", "turquoise", "青緑", "ターコイズ"], (0.05, 0.46, 0.50)),
            (["black", "黒"], (0.05, 0.05, 0.05)),
            (["grey", "gray", "グレー", "灰"], (0.50, 0.50, 0.50)),
            (["blue", "青"], (0.12, 0.30, 0.70)),
            (["green", "緑"], (0.15, 0.55, 0.25)),
            (["pink", "ピンク"], (0.90, 0.45, 0.60)),
            (["brown", "茶"], (0.40, 0.22, 0.12)),
        ]
        guard let target = named.first(where: { item in
            item.words.contains(where: text.contains)
        })?.rgb else { return 0.5 }
        let distance = sqrt(pow(target.0 - region.red, 2)
            + pow(target.1 - region.green, 2)
            + pow(target.2 - region.blue, 2)) / sqrt(3)
        return max(0, 1 - distance)
    }

    private static func rectDictionary(_ rect: VisionSpatialRect) -> [String: Double] {
        ["x": rounded(rect.x), "y": rounded(rect.y),
         "width": rounded(rect.width), "height": rounded(rect.height)]
    }

    private static func pixelRectDictionary(
        _ rect: VisionSpatialRect, width: Double, height: Double
    ) -> [String: Double] {
        ["x": rounded(rect.x * width), "y": rounded(rect.y * height),
         "width": rounded(rect.width * width),
         "height": rounded(rect.height * height)]
    }

    private static func rounded(_ value: Double) -> Double {
        (value * 1_000_000).rounded() / 1_000_000
    }

    private static func finiteDouble(_ value: Any?) -> Double? {
        guard let number = value as? NSNumber,
              CFGetTypeID(number) != CFBooleanGetTypeID(),
              number.doubleValue.isFinite else { return nil }
        return number.doubleValue
    }

    private static func positiveDouble(_ value: Any?) -> Double? {
        guard let value = finiteDouble(value), value > 0 else { return nil }
        return value
    }

    /// Extract the first balanced JSON object without accepting trailing model
    /// prose as part of the transport.  String escapes are honoured, and work
    /// is bounded by the response's existing byte count.
    private static func firstJSONObject(in raw: String) -> [String: Any]? {
        let bytes = Array(raw.utf8)
        for start in bytes.indices where bytes[start] == 0x7B {
            var depth = 0
            var inString = false
            var escaped = false
            for index in start..<bytes.count {
                let byte = bytes[index]
                if inString {
                    if escaped { escaped = false }
                    else if byte == 0x5C { escaped = true }
                    else if byte == 0x22 { inString = false }
                    continue
                }
                if byte == 0x22 { inString = true; continue }
                if byte == 0x7B { depth += 1 }
                if byte == 0x7D {
                    depth -= 1
                    if depth == 0 {
                        let data = Data(bytes[start...index])
                        if let object = try? JSONSerialization.jsonObject(with: data)
                            as? [String: Any] { return object }
                        break
                    }
                }
            }
        }
        return nil
    }

    private static func execute(_ parsed: GarmentCommandIR) async -> Resolution {
        var command = parsed
        var imageSelection: AtelierIntake.AnalysisSelection?
        var confirmedFactoryImage: (outline: [String: Any], path: String, evidenceState: String)?

        // Rear inspection is a continuation of the active audited image job,
        // not another image-generation request. Keep it queued across the
        // human visible-parts and cleanup gates, then render a PROPOSED rear
        // bound to the accepted front target.
        if command.intent == .inspect,
           command.target?.candidateKind?.uppercased() == "BACK",
           command.operation?.kind.uppercased() == "REQUEST_BACK_3D" {
            let proposer = GarmentFactoryModelMouth.proposer(
                for: AtelierAnalyst.shared.pick)
            let report = await GarmentFactoryReactController.shared
                .requestBack3DPreview(
                    userRequest: factoryRequest(command), proposer: proposer)
            return .factory(report, Destination(
                step: "Structure",
                reasonEN: "→ 05 Structure — proposed rear 3D",
                reasonJA: "→ 05 Structure — 未観測の背面3D候補"))
        }
        if command.intent == .generateFromImage {
            guard let selected = AtelierIntake.shared.analysisSelection else {
                return .refused("UNKNOWN_NO_SELECTED_IMAGE\n写真を追加して選択してから、もう一度実行してください")
            }
            imageSelection = selected
            command.target?.reference = selected.clip.path
        }

        guard var json = command.jsonString else {
            return .refused("UNKNOWN_COMMAND_ENCODING\n型付き命令をJSONへ変換できませんでした")
        }
        if command.intent == .generateFromImage {
            let intake = AtelierIntake.shared
            guard let selected = imageSelection,
                  intake.isCurrent(selected) else {
                return .refused("UNKNOWN_NO_SELECTED_IMAGE")
            }
            let outline: [String: Any]
            let evidenceState: String
            if intake.confirmedOutlineImagePath == selected.clip.path,
               intake.confirmedOutlineSelectionRevision == selected.revision,
               let confirmed = intake.confirmedClothingOutline {
                outline = confirmed
                evidenceState = "OBSERVED"
            } else {
                let proposed = await GarmentRegionPickerModel.automaticClothingProposal(
                    path: selected.clip.path)
                guard intake.isCurrent(selected) else {
                    return .refused("UNKNOWN_STALE_IMAGE_SELECTION\n画像が再選択されたため、古い服領域候補を破棄しました")
                }
                if let verdict = proposed["verdict"] as? String {
                    let close = proposed["how_to_close"] as? String ?? "服領域を確認してください"
                    return .refused("\(verdict)\n\(close)")
                }
                outline = proposed
                evidenceState = "PROPOSED"
            }
            guard let commandData = json.data(using: .utf8),
                  let commandObject = try? JSONSerialization.jsonObject(with: commandData),
                  JSONSerialization.isValidJSONObject(outline),
                  JSONSerialization.isValidJSONObject([
                    "command": commandObject,
                    "context": ["confirmed_outline": outline]
                  ]),
                  let envelopeData = try? JSONSerialization.data(withJSONObject: [
                    "command": commandObject,
                    "context": ["confirmed_outline": outline]
                  ], options: [.sortedKeys]),
                  let envelope = String(data: envelopeData, encoding: .utf8) else {
                return .refused("UNKNOWN_CONFIRMED_OUTLINE_ENCODING\n確定した服領域を型付き命令へ添付できませんでした")
            }
            json = envelope
            confirmedFactoryImage = (outline, selected.clip.path, evidenceState)

            // A fully automatic region is sufficient for an explicitly
            // labelled preview, not for the legacy workflow's
            // `confirmed_outline` manufacturing path.  Start the Vera factory
            // directly and let its geometric retries produce the 3D/flat
            // pattern cards without pretending an automatic probe was human
            // evidence.
            if evidenceState == "PROPOSED" {
                let proposer = GarmentFactoryModelMouth.proposer(
                    for: AtelierAnalyst.shared.pick)
                let spatialInput = await prepareVisionSpatialInput(
                    outline: outline, imagePath: selected.clip.path,
                    userRequest: factoryRequest(command),
                    pick: AtelierAnalyst.shared.pick)
                let report = await GarmentFactoryReactController.shared.beginConfirmedImage(
                    outline: spatialInput.outline, imagePath: selected.clip.path,
                    userRequest: factoryRequest(command),
                    designRequirements: command.operation?.requirements ?? [],
                    proposer: proposer, visionProposer: spatialInput.proposer,
                    initialFashionRetrieval: spatialInput.fashionRetrieval,
                    evidenceState: evidenceState)
                guard intake.isCurrent(selected) else {
                    consumeSelectionRevision(
                        intake.selectionRevision,
                        imagePath: intake.selectedClip?.path ?? "")
                    return .refused("UNKNOWN_STALE_IMAGE_SELECTION\n画像が再選択されたため、古い候補プレビューを破棄しました")
                }
                return .factory(report, Destination(
                    step: "Structure",
                    reasonEN: "Automatic proposed outline → geometry factory",
                    reasonJA: "自動の未確定輪郭 → 幾何縫製工場"))
            }
        }
        if command.intent == .runSimulation {
            switch GarmentGenerationJob.shared.simulationRequestJSON(command: command) {
            case .success(let simulationJSON):
                json = simulationJSON
            case .failure(let refusal):
                return .refused(refusalText(refusal))
            }
        }
        // One MCP integration door owns command routing and the persisted
        // preview/approval/Undo history. The Swift mirror only renders it.
        let response = await callDoor("garment_workflow", [
            "json_text": json,
            "approver": NSFullUserName().trimmingCharacters(in: .whitespacesAndNewlines)
        ])
        let verdict = response["verdict"] as? String ?? "UNKNOWN_ENGINE_RESPONSE"
        guard verdict == "ANSWER" else {
            let answer = GarmentGenerationJob.shared.mirrorAnswer(response)
            return .refused(answer.deterministicText)
        }

        // The existing garment_workflow remains authoritative for its own
        // preview/Undo path. In parallel, initialise the separate factory
        // state machine from the same human-confirmed clothing region. The
        // foreman will stop at retrieval rather than asking an LLM to invent
        // search hits.
        if let image = confirmedFactoryImage {
            let proposer = GarmentFactoryModelMouth.proposer(
                for: AtelierAnalyst.shared.pick)
            let spatialInput = await prepareVisionSpatialInput(
                outline: image.outline, imagePath: image.path,
                userRequest: factoryRequest(command),
                pick: AtelierAnalyst.shared.pick)
            _ = await GarmentFactoryReactController.shared.beginConfirmedImage(
                outline: spatialInput.outline, imagePath: image.path,
                userRequest: factoryRequest(command),
                designRequirements: command.operation?.requirements ?? [],
                proposer: proposer, visionProposer: spatialInput.proposer,
                initialFashionRetrieval: spatialInput.fashionRetrieval,
                evidenceState: image.evidenceState)
            if let selected = imageSelection,
               !AtelierIntake.shared.isCurrent(selected) {
                consumeSelectionRevision(
                    AtelierIntake.shared.selectionRevision,
                    imagePath: AtelierIntake.shared.selectedClip?.path ?? "")
                return .refused("UNKNOWN_STALE_IMAGE_SELECTION\n画像が再選択されたため、古い候補プレビューを破棄しました")
            }
        }

        switch command.intent {
        case .approve:
            guard let digest = command.operation?.previewDigest else {
                return .refused("UNKNOWN_APPROVAL_DIGEST_REQUIRED")
            }
            switch GarmentGenerationJob.shared.approve(digest: digest) {
            case .success:
                return .answered(GarmentGenerationJob.shared.mirrorAnswer(response),
                                 destination(for: command))
            case .failure(let refusal):
                return .refused(refusalText(refusal))
            }
        case .reject:
            guard let digest = command.operation?.previewDigest else {
                return .refused("UNKNOWN_REJECTION_DIGEST_REQUIRED")
            }
            switch GarmentGenerationJob.shared.reject(digest: digest) {
            case .success:
                return .answered(GarmentGenerationJob.shared.mirrorAnswer(response), nil)
            case .failure(let refusal):
                return .refused(refusalText(refusal))
            }
        case .undo:
            switch GarmentGenerationJob.shared.undo() {
            case .success:
                return .answered(GarmentGenerationJob.shared.mirrorAnswer(response), nil)
            case .failure(let refusal):
                return .refused(refusalText(refusal))
            }
        default:
            if command.requiresPreview {
                switch GarmentGenerationJob.shared.stage(command: command, response: response) {
                case .success(let preview):
                    return .preview(preview, destination(for: command))
                case .failure(let refusal):
                    return .refused(refusalText(refusal))
                }
            }
            return .answered(GarmentGenerationJob.shared.mirrorAnswer(response),
                             destination(for: command))
        }
    }

    static func approvePending(digest: String) async -> Resolution {
        let job = GarmentGenerationJob.shared
        return await execute(GarmentCommandParser.approval(
            previewDigest: digest, jobID: job.jobID))
    }

    static func approveFactoryCandidate(
        _ candidate: GarmentFactoryReactController.Candidate,
        material: Bool
    ) async -> Resolution {
        let by = NSFullUserName().trimmingCharacters(in: .whitespacesAndNewlines)
        let human = by.isEmpty ? "Local User" : by
        // Closed human-click vocabulary. The controller, not the model,
        // creates APPROVE_HYPOTHESIS / APPROVE_MATERIAL with this name and
        // the exact digest rendered in the candidate card.
        let typedEvent = material ? "APPROVE_MATERIAL" : "APPROVE_HYPOTHESIS"
        precondition(typedEvent == "APPROVE_MATERIAL" || typedEvent == "APPROVE_HYPOTHESIS")
        let proposer = GarmentFactoryModelMouth.proposer(
            for: AtelierAnalyst.shared.pick)
        let report: GarmentFactoryReactController.Report
        if material {
            report = await GarmentFactoryReactController.shared.approveMaterial(
                candidate, by: human, userRequest: "Human selected material candidate",
                proposer: proposer)
        } else {
            report = await GarmentFactoryReactController.shared.approveShape(
                candidate, by: human, userRequest: "Human selected structure candidate",
                proposer: proposer)
        }
        return .factory(report, nil)
    }

    static func rejectFactoryCandidate(
        _ candidate: GarmentFactoryReactController.Candidate
    ) async -> Resolution {
        let by = NSFullUserName().trimmingCharacters(in: .whitespacesAndNewlines)
        let human = by.isEmpty ? "Local User" : by
        let report = await GarmentFactoryReactController.shared.rejectShape(
            candidate, by: human,
            reason: "Named human rejected this digest from the beginner candidate comparison")
        return .factory(report, nil)
    }

    static func undoFactoryShapeDecision() async -> Resolution {
        let by = NSFullUserName().trimmingCharacters(in: .whitespacesAndNewlines)
        let human = by.isEmpty ? "Local User" : by
        let report = await GarmentFactoryReactController.shared.undoShapeDecision(by: human)
        return .factory(report, nil)
    }

    static func rejectPending(digest: String) async -> Resolution {
        let job = GarmentGenerationJob.shared
        return await execute(GarmentCommandParser.rejection(
            previewDigest: digest, jobID: job.jobID))
    }

    static func undoLast() async -> Resolution {
        let job = GarmentGenerationJob.shared
        let command = GarmentCommandIR(
            commandID: "undo-\(job.history.count)", intent: .undo,
            jobID: job.jobID, provenance: .humanInput)
        return await execute(command)
    }

    /// Beginner-chat entry point. The selected LLM owns ordinary conversation
    /// and may attach one typed action proposal. Vera owns validation and
    /// execution. Fixed natural-language grammar is intentionally not a
    /// fallback here; only explicit approval/rejection/Undo controls bypass
    /// the model because their authority must remain directly human-authored.
    static func resolveFlexible(_ message: String) async -> Resolution {
        let text = message.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return .none }
        if isExplicitHumanControl(text) {
            switch GarmentCommandParser.parse(
                text, jobID: GarmentGenerationJob.shared.jobID) {
            case .command(let command):
                return await execute(command)
            case .refused(let refusal):
                return .refused(refusalText(refusal))
            case .notACommand:
                return .refused("UNKNOWN_HUMAN_CONTROL\n承認操作を読み取れませんでした。")
            }
        }

        // The selected LLM remains free to interpret and answer the message.
        // When a current garment image exists, Vera simultaneously prepares a
        // proposal-only geometric preview so the beginner surface is not an
        // empty chat canvas during a long local-model turn.  This warm-up has
        // no command authority and is discarded by the normal revision gate.
        async let plannedTurn = AtelierGarmentRequestPlanner.plan(
            text, pick: AtelierAnalyst.shared.pick,
            jobID: GarmentGenerationJob.shared.jobID)
        async let previewWarmup: Void = warmProposedImagePreviewIfAvailable()
        let planned = await plannedTurn
        await previewWarmup
        switch planned {
        case .response(let speech, let proposedCommand):
            let action: Resolution?
            if let proposedCommand {
                action = await execute(proposedCommand)
            } else {
                action = nil
            }
            return .modelGenerated(speech, action)
        case .refused(let planningRefusal):
            return .refused(planningRefusal)
        }
    }

    private static func warmProposedImagePreviewIfAvailable() async {
        let intake = AtelierIntake.shared
        guard let selected = intake.analysisSelection else { return }
        let outline: [String: Any]
        if intake.confirmedOutlineImagePath == selected.clip.path,
           intake.confirmedOutlineSelectionRevision == selected.revision,
           let confirmed = intake.confirmedClothingOutline {
            outline = confirmed
        } else {
            let proposed = await GarmentRegionPickerModel.automaticClothingProposal(
                path: selected.clip.path)
            guard intake.isCurrent(selected), proposed["verdict"] == nil else { return }
            outline = proposed
        }
        guard intake.isCurrent(selected) else { return }
        await GarmentFactoryReactController.shared.prepareProposedImagePreview(
            outline: outline, imagePath: selected.clip.path)
        guard intake.isCurrent(selected) else {
            consumeSelectionRevision(
                intake.selectionRevision,
                imagePath: intake.selectedClip?.path ?? "")
            return
        }
    }

    private static func isExplicitHumanControl(_ raw: String) -> Bool {
        let text = raw.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if ["undo", "元に戻す", "取り消す"].contains(text) { return true }
        let pattern = #"^(?:承認|approve|却下|reject)\s+[0-9a-f]{12,64}$"#
        guard let expression = try? NSRegularExpression(pattern: pattern) else { return false }
        return expression.firstMatch(
            in: text, range: NSRange(text.startIndex..., in: text)) != nil
    }

    /// Text shown in the existing full-screen Chat transcript. It reports the
    /// typed result; it never turns a model explanation into a success claim.
    static func transcriptText(for resolution: Resolution) -> String {
        switch resolution {
        case .modelGenerated(let text, let action):
            var answer = "制作モデル生成（未検証）\n\(text)"
            if let action {
                answer += "\n\nVera検証・実行結果\n\(transcriptText(for: action))"
            } else {
                answer += "\n\nVera: 状態変更は提案・実行されていません。"
            }
            return answer
        case .moved(let destination):
            return AppLanguage.shared.isJapanese
                ? destination.reasonJA : destination.reasonEN
        case .refused(let text):
            return text
        case .preview(let preview, let destination):
            let changes = preview.changedAddresses.isEmpty
                ? "変更箇所は未報告"
                : preview.changedAddresses.joined(separator: ", ")
            let move = destination.map { "\n\($0.reasonJA)" } ?? ""
            return "PROPOSED — まだ適用していません\n"
                + "\(changes)\npreview digest: \(preview.digest)\(move)\n"
                + "プレビューを確認して承認または却下してください。"
        case .answered(let answer, let destination):
            let move = destination.map { "\n\($0.reasonJA)" } ?? ""
            return answer.deterministicText + move
        case .factory(let report, let destination):
            var lines = [report.verdict, report.message,
                         "phase=\(report.phase) / rounds=\(report.iterations) / model=\(report.modelCalls)"]
            if let artifact = GarmentFactoryReactController.shared.previewArtifact {
                lines.append("3D着装・型紙プレビュー: \(artifact.method) / attempt \(artifact.attempt)")
            }
            if let destination { lines.append(destination.reasonJA) }
            return lines.joined(separator: "\n")
        case .none:
            return "UNKNOWN_GARMENT_REQUEST\n服飾命令として解釈できなかったため、何も変更していません。"
        }
    }

    static func resolve(_ message: String) async -> Resolution {
        #if DEBUG
        validateLexicon()
        #endif
        let text = message.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return .none }

        // Typed garment commands take precedence over the legacy number-span
        // navigator. A plain "30 to 35" still falls through to pattern_span;
        // "30 to 35 by 3cm" becomes a preview and never commits directly.
        switch GarmentCommandParser.parse(
            text, jobID: GarmentGenerationJob.shared.jobID) {
        case .command(let command):
            return await execute(command)
        case .refused(let refusal):
            return .refused(refusalText(refusal))
        case .notACommand:
            break
        }

        let lower = text.lowercased()
        let factoryWords = ["縫製工場", "工場を続", "生成を続", "検証を続",
                            "factory loop", "continue factory", "react loop"]
        if factoryWords.contains(where: { lower.contains($0.lowercased()) }) {
            let proposer = GarmentFactoryModelMouth.proposer(
                for: AtelierAnalyst.shared.pick)
            let report = await GarmentFactoryReactController.shared.runUntilPause(
                userRequest: text, proposer: proposer)
            let destination: Destination?
            switch report.phase {
            case "RETRIEVAL_READY", "BACK_CANDIDATES_READY",
                 "STRUCTURE_CANDIDATES_READY", "STRUCTURE_APPROVED":
                destination = Destination(step: "Structure",
                    reasonEN: "→ 05 Structure — factory \(report.phase)",
                    reasonJA: "→ 05 Structure — 工場 \(report.phase)")
            case "PATTERN_READY", "PATTERN_REPAIRED":
                destination = Destination(step: "Pattern",
                    reasonEN: "→ 08 Pattern — factory \(report.phase)",
                    reasonJA: "→ 08 Pattern — 工場 \(report.phase)")
            case "MATERIAL_CANDIDATES_READY", "MATERIAL_APPROVED", "SIMULATION_READY":
                destination = Destination(step: "Materials",
                    reasonEN: "→ 03 Materials — factory \(report.phase)",
                    reasonJA: "→ 03 Materials — 工場 \(report.phase)")
            default:
                destination = nil
            }
            return .factory(report, destination)
        }

        if let (lo, hi) = numberSpan(in: text) {
            let d = await callDoor("pattern_span", ["first": lo, "last": hi])
            if (d["verdict"] as? String) == "ANSWER",
               let piece = d["piece"] as? String, let edge = d["edge"] as? String {
                let n = stepNumber("Pattern")
                let where_ = "\(piece)/\(edge)"
                return .moved(Destination(
                    step: "Pattern",
                    reasonEN: String(format: "→ %02d Pattern — %@", n, where_),
                    reasonJA: String(format: "→ %02d Pattern — %@", n, where_)))
            }
            // pattern_span itself answered — just not with a place
            // ("UNKNOWN_SPAN_CROSSES_EDGES" etc). That refusal is the
            // honest thing to show; inventing a step here would be
            // exactly the guess the owner's brief rules out.
            if let close = d["how_to_close"] as? String, !close.isEmpty {
                return .refused(close)
            }
            let verdict = (d["verdict"] as? String) ?? "UNKNOWN_ENGINE_UNREACHABLE"
            return .refused(verdict)
        }

        for (words, step) in lexicon where words.contains(where: { lower.contains($0.lowercased()) }) {
            let n = stepNumber(step)
            let label = String(format: "→ %02d %@", n, step)
            return .moved(Destination(step: step, reasonEN: label, reasonJA: label))
        }
        return .none
    }
}
