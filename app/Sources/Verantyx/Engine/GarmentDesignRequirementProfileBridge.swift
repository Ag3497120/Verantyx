import Foundation

/// Typed boundary between `GarmentCommandIR.Requirement` and the deterministic
/// `garment_design_requirement_profile` MCP tool.
///
/// The Python tool remains the canonical compiler. This bridge independently
/// derives the only geometry addresses that the supplied typed requirements
/// are allowed to affect, then compares the MCP response with that allow-list
/// before applying anything to a candidate. A size label is never expanded
/// here, and an unscoped ease value has no geometry address.
enum GarmentDesignRequirementProfileBridge {
    static let serverName = "vera-memory"
    static let toolName = "garment_design_requirement_profile"
    static let requestSchema = "garment.design-requirement-profile.request.v1"
    static let responseSchema = "garment.design-requirement-profile.v1"

    struct Failure: Error, Equatable, CustomStringConvertible {
        let code: String
        let detail: String

        var description: String { "\(code): \(detail)" }
    }

    struct PreparedRequest {
        let request: [String: Any]
        let jsonText: String
        let arguments: [String: Any]
        fileprivate let expectedOverrides: [String: [String: ExpectedOverride]]
        fileprivate let requiredReviewCodes: Set<String>
    }

    struct Override: Equatable {
        let valueCM: Double
        let state: String
        let authority: String
        let sourceRequirementTargets: [String]
        let notMeasuredFromImage: Bool
        let previewOnly: Bool

        fileprivate var provenanceDictionary: [String: Any] {
            [
                "value_cm": valueCM,
                "unit": "cm",
                "state": state,
                "authority": authority,
                "source_requirement_targets": sourceRequirementTargets,
                "not_measured_from_image": notMeasuredFromImage,
                "preview_only": previewOnly,
            ]
        }
    }

    struct ValidatedProfile {
        let verdict: String
        let profileDigest: String
        let requirements: [[String: Any]]
        let primitiveOverrides: [String: [String: Override]]
        let reviewItems: [[String: Any]]
        let raw: [String: Any]
    }

    struct AppliedCandidate {
        let candidate: [String: Any]
        let appliedFieldCount: Int
        let applicationReviewItems: [[String: Any]]
        let verdict: String
        let profile: ValidatedProfile
    }

    fileprivate struct ExpectedOverride: Equatable {
        let valueCM: Double
        let sourceTargets: Set<String>
    }

    private struct Dimension {
        let valueCM: Double
        let sourceTarget: String
    }

    private static let dimensionKinds: Set<GarmentCommandIR.Requirement.Kind> = [
        .bodyMeasurement, .garmentMeasurement, .ease, .length,
    ]

    private static let targetAliases: [String: [String]] = [
        "chest_bust": ["chest", "bust", "chest bust", "胸囲", "バスト"],
        "waist": ["waist", "waist circumference", "ウエスト", "胴囲"],
        "hip": ["hip", "hips", "hip circumference", "ヒップ", "腰回り"],
        "body_length": ["body length", "torso length", "背丈", "身頃丈"],
        "inseam": ["inseam", "inside leg", "股下"],
        "shoulder": ["shoulder", "shoulder width", "肩幅"],
        "sleeve_length": ["sleeve length", "sleeve", "袖丈"],
        "height": ["height", "stature", "身長"],
        "skirt_length": ["skirt length", "スカート丈"],
        "garment_length": ["garment length", "dress length", "coat length", "着丈"],
        "hem_circumference": ["hem circumference", "hem width", "裾周り", "裾幅"],
        "overlay_height": ["overlay height", "cape length", "オーバーレイ丈", "ケープ丈"],
    ]

    static func prepare(
        requirements: [GarmentCommandIR.Requirement]
    ) throws -> PreparedRequest {
        guard (1...24).contains(requirements.count) else {
            throw Failure(code: "UNKNOWN_TYPED_REQUIREMENTS_REQUIRED",
                          detail: "requirements must contain 1-24 rows")
        }

        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        let rowsData: Data
        do {
            rowsData = try encoder.encode(requirements)
        } catch {
            throw Failure(code: "UNKNOWN_REQUIREMENT_ENCODING",
                          detail: error.localizedDescription)
        }
        guard let rows = try JSONSerialization.jsonObject(with: rowsData)
                as? [[String: Any]] else {
            throw Failure(code: "UNKNOWN_REQUIREMENT_ENCODING",
                          detail: "encoded requirements are not an object array")
        }
        try validateInput(requirements)

        let request: [String: Any] = [
            "schema": requestSchema,
            "requirements": rows,
        ]
        guard JSONSerialization.isValidJSONObject(request) else {
            throw Failure(code: "UNKNOWN_REQUIREMENT_ENCODING",
                          detail: "request is not canonical JSON")
        }
        let data = try JSONSerialization.data(
            withJSONObject: request, options: [.sortedKeys, .withoutEscapingSlashes])
        guard let jsonText = String(data: data, encoding: .utf8) else {
            throw Failure(code: "UNKNOWN_REQUIREMENT_ENCODING",
                          detail: "request is not UTF-8")
        }
        let policy = try expectedPolicy(requirements)
        return PreparedRequest(
            request: request,
            jsonText: jsonText,
            arguments: ["json_text": jsonText],
            expectedOverrides: policy.overrides,
            requiredReviewCodes: policy.reviewCodes)
    }

    /// Production call convention used by the other Engine bridges. The
    /// controller can call this convenience or inject its existing ToolDoor
    /// and use `prepare` + `validate` directly.
    #if !GARMENT_DESIGN_REQUIREMENT_PROFILE_STANDALONE
    @MainActor
    static func call(
        requirements: [GarmentCommandIR.Requirement]
    ) async throws -> ValidatedProfile {
        let prepared = try prepare(requirements: requirements)
        let raw = await MCPEngine.shared.callTool(
            serverName: serverName,
            toolName: toolName,
            arguments: prepared.arguments)
        return try validate(rawText: raw, prepared: prepared)
    }
    #endif

    static func validate(
        rawText: String, prepared: PreparedRequest
    ) throws -> ValidatedProfile {
        guard let data = rawText.data(using: .utf8),
              let response = try? JSONSerialization.jsonObject(with: data)
                as? [String: Any] else {
            throw Failure(code: "UNKNOWN_REQUIREMENT_PROFILE_RESPONSE",
                          detail: "MCP response is not a JSON object")
        }
        return try validate(response: response, prepared: prepared)
    }

    static func validate(
        response: [String: Any], prepared: PreparedRequest
    ) throws -> ValidatedProfile {
        guard response["schema"] as? String == responseSchema else {
            throw Failure(code: "UNKNOWN_REQUIREMENT_PROFILE_SCHEMA",
                          detail: "unexpected response schema")
        }
        guard let verdict = response["verdict"] as? String,
              ["PROPOSED", "REVIEW"].contains(verdict),
              response["state"] as? String == "PREVIEW_PROFILE_READY" else {
            throw Failure(code: "UNKNOWN_REQUIREMENT_PROFILE_NOT_READY",
                          detail: "profile did not reach a proposal-only ready state")
        }
        guard response["preview_only"] as? Bool == true,
              response["manufacturing_ready"] as? Bool == false,
              response["manufacturing_certified"] as? Bool == false else {
            throw Failure(code: "UNKNOWN_REQUIREMENT_PROFILE_AUTHORITY",
                          detail: "profile crossed the preview/manufacturing boundary")
        }
        guard let claims = response["claims"] as? [String: Any],
              claims["front_image_measured"] as? Bool == false,
              claims["standard_size_expanded_without_chart"] as? Bool == false,
              claims["generic_ease_auto_distributed"] as? Bool == false,
              claims["user_dimension_treated_as_measured_fact"] as? Bool == false else {
            throw Failure(code: "UNKNOWN_REQUIREMENT_PROFILE_CLAIMS",
                          detail: "required non-measurement claims are absent")
        }

        let normalizedRequirements = response["requirements"] as? [[String: Any]] ?? []
        try validateNormalizedRequirements(
            normalizedRequirements, request: prepared.request)

        let reviewItems = response["review_items"] as? [[String: Any]] ?? []
        let reviewCodes = Set(reviewItems.compactMap { $0["code"] as? String })
        guard prepared.requiredReviewCodes.isSubset(of: reviewCodes) else {
            let missing = prepared.requiredReviewCodes.subtracting(reviewCodes).sorted()
            throw Failure(code: "UNKNOWN_REQUIREMENT_PROFILE_REVIEW_MISSING",
                          detail: missing.joined(separator: ","))
        }
        if !prepared.requiredReviewCodes.isEmpty && verdict != "REVIEW" {
            throw Failure(code: "UNKNOWN_REQUIREMENT_PROFILE_REVIEW_BYPASSED",
                          detail: "required review was labelled \(verdict)")
        }

        let supplied = response["primitive_overrides"] as? [String: Any] ?? [:]
        let suppliedAddresses = try overrideAddressSet(supplied)
        let expectedAddresses = Set(prepared.expectedOverrides.flatMap { primitive, fields in
            fields.keys.map { "\(primitive).\($0)" }
        })
        guard suppliedAddresses == expectedAddresses else {
            throw Failure(code: "UNKNOWN_PROFILE_OVERRIDE_SET_MISMATCH",
                          detail: "expected \(expectedAddresses.sorted()), got \(suppliedAddresses.sorted())")
        }

        var validated: [String: [String: Override]] = [:]
        for primitive in prepared.expectedOverrides.keys.sorted() {
            guard let rawFields = supplied[primitive] as? [String: Any] else {
                throw Failure(code: "UNKNOWN_PROFILE_OVERRIDE_SHAPE",
                              detail: "\(primitive) is not an object")
            }
            for field in prepared.expectedOverrides[primitive]!.keys.sorted() {
                guard let rawRecord = rawFields[field] as? [String: Any],
                      let expected = prepared.expectedOverrides[primitive]?[field] else {
                    throw Failure(code: "UNKNOWN_PROFILE_OVERRIDE_SHAPE",
                                  detail: "missing \(primitive).\(field)")
                }
                let record = try validatedOverride(
                    rawRecord, primitive: primitive, field: field)
                guard nearlyEqual(record.valueCM, expected.valueCM),
                      Set(record.sourceRequirementTargets) == expected.sourceTargets else {
                    throw Failure(code: "UNKNOWN_PROFILE_OVERRIDE_VALUE_MISMATCH",
                                  detail: "\(primitive).\(field) is not derivable from the typed request")
                }
                validated[primitive, default: [:]][field] = record
            }
        }

        guard let digest = response["profile_digest"] as? String,
              !digest.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw Failure(code: "UNKNOWN_REQUIREMENT_PROFILE_DIGEST",
                          detail: "profile digest is absent")
        }
        return ValidatedProfile(
            verdict: verdict,
            profileDigest: digest,
            requirements: normalizedRequirements,
            primitiveOverrides: validated,
            reviewItems: reviewItems,
            raw: response)
    }

    /// Applies a previously validated profile to both common candidate forms:
    /// `structure.nodes` and `parts`/`parts_ir.parts`. Every changed dimension
    /// receives a sibling provenance record; no value is marked OBSERVED.
    static func apply(
        _ profile: ValidatedProfile, to candidate: [String: Any]
    ) throws -> AppliedCandidate {
        var output = candidate
        var applied = 0
        var applicationReviews: [[String: Any]] = []

        var plans: [ApplicationPlan] = []

        if let structure = output["structure"] as? [String: Any],
           let nodes = structure["nodes"] as? [[String: Any]] {
            plans.append(applicationPlan(profile.primitiveOverrides, to: nodes,
                                         container: "structure.nodes"))
        }
        if let parts = output["parts"] as? [[String: Any]] {
            plans.append(applicationPlan(profile.primitiveOverrides, to: parts,
                                         container: "parts"))
        }
        if let partsIR = output["parts_ir"] as? [String: Any],
           let parts = partsIR["parts"] as? [[String: Any]] {
            plans.append(applicationPlan(profile.primitiveOverrides, to: parts,
                                         container: "parts_ir.parts"))
        }

        // A requirement is one atomic edit even when the candidate exposes
        // structure and flat-parts representations.  If any representation
        // cannot resolve its graph address, none of the representations may
        // receive a partial update for that requirement.
        let blockedGroups = plans.reduce(into: Set<RequirementGroup>()) {
            $0.formUnion($1.blockedGroups)
        }
        for plan in plans {
            let result = applying(plan, blockedGroups: blockedGroups)
            switch plan.container {
            case "structure.nodes":
                if var structure = output["structure"] as? [String: Any] {
                    structure["nodes"] = result.rows
                    output["structure"] = structure
                }
            case "parts":
                output["parts"] = result.rows
            case "parts_ir.parts":
                if var partsIR = output["parts_ir"] as? [String: Any] {
                    partsIR["parts"] = result.rows
                    output["parts_ir"] = partsIR
                }
            default:
                break
            }
            applied += result.count
            applicationReviews.append(contentsOf: plan.reviewItems)
        }

        let combinedReviews = profile.reviewItems + applicationReviews
        let appliedVerdict = applicationReviews.isEmpty ? profile.verdict : "REVIEW"

        output["design_requirement_profile"] = [
            "schema": responseSchema,
            "profile_digest": profile.profileDigest,
            "verdict": appliedVerdict,
            "state": "REQUESTED_PREVIEW_APPLIED",
            "requirements": profile.requirements,
            "review_items": combinedReviews,
            "authority": "USER_EXPLICIT_REQUEST_NOT_MEASUREMENT_CERTIFICATE",
            "not_measured_from_image": true,
            "preview_only": true,
            "manufacturing_ready": false,
            "manufacturing_certified": false,
        ]
        output["manufacturing_ready"] = false
        output["manufacturing_certified"] = false
        return AppliedCandidate(candidate: output, appliedFieldCount: applied,
                                applicationReviewItems: applicationReviews,
                                verdict: appliedVerdict,
                                profile: profile)
    }

    // MARK: - Input policy

    private static func validateInput(
        _ requirements: [GarmentCommandIR.Requirement]
    ) throws {
        for (index, item) in requirements.enumerated() {
            guard !item.target.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                throw Failure(code: "UNKNOWN_REQUIREMENT_TARGET",
                              detail: "requirements[\(index)] has no target")
            }
            if dimensionKinds.contains(item.kind) {
                guard let value = item.value, value.isFinite, value > 0,
                      item.unit != nil else {
                    throw Failure(code: "UNKNOWN_EXPLICIT_DIMENSION_REQUIRED",
                                  detail: "requirements[\(index)] needs a positive value and unit")
                }
            } else if item.value != nil {
                throw Failure(code: "UNKNOWN_NUMERIC_NON_DIMENSION_REQUIREMENT",
                              detail: "requirements[\(index)] uses a numeric non-dimension")
            }
            let hasText = !(item.text ?? "")
                .trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            if item.value == nil && !hasText {
                throw Failure(code: "UNKNOWN_REQUIREMENT_VALUE",
                              detail: "requirements[\(index)] has neither text nor value")
            }
        }
    }

    private static func expectedPolicy(
        _ requirements: [GarmentCommandIR.Requirement]
    ) throws -> (overrides: [String: [String: ExpectedOverride]],
                 reviewCodes: Set<String>) {
        var body: [String: Dimension] = [:]
        var ease: [String: Dimension] = [:]
        var direct: [(String, Dimension)] = []
        var reviewCodes: Set<String> = []

        for item in requirements {
            let canonical = canonicalTarget(item.target)
            switch item.kind {
            case .standardSize:
                reviewCodes.insert("UNKNOWN_STANDARD_SIZE_CHART_REQUIRED")
            case .bodyMeasurement:
                guard let canonical,
                      ["chest_bust", "waist", "hip", "body_length", "inseam",
                       "shoulder", "sleeve_length", "height"].contains(canonical),
                      let dimension = try dimension(item) else {
                    reviewCodes.insert("UNKNOWN_BODY_MEASUREMENT_TARGET")
                    continue
                }
                try putInput(&body, key: canonical, dimension: dimension)
            case .ease:
                guard let canonical,
                      ["chest_bust", "waist", "hip"].contains(canonical),
                      let dimension = try dimension(item) else {
                    reviewCodes.insert("UNKNOWN_EASE_TARGET_REQUIRED")
                    continue
                }
                try putInput(&ease, key: canonical, dimension: dimension)
            case .garmentMeasurement, .length:
                guard let canonical, let dimension = try dimension(item) else {
                    reviewCodes.insert("UNKNOWN_GARMENT_DIMENSION_TARGET")
                    continue
                }
                direct.append((canonical, dimension))
            default:
                break
            }
        }

        var result: [String: [String: ExpectedOverride]] = [:]
        func put(_ primitive: String, _ field: String,
                 _ value: Double, _ sources: Set<String>) throws {
            let next = ExpectedOverride(valueCM: value, sourceTargets: sources)
            if let old = result[primitive]?[field], old != next {
                throw Failure(code: "UNKNOWN_CONFLICTING_REQUIREMENT_DIMENSIONS",
                              detail: "\(primitive).\(field) has conflicting inputs")
            }
            result[primitive, default: [:]][field] = next
        }

        if let chest = body["chest_bust"] {
            let chestEase = ease["chest_bust"]
            var sources: Set<String> = [chest.sourceTarget]
            if let chestEase { sources.insert(chestEase.sourceTarget) }
            try put("BODY_SHELL", "circumference_cm",
                    chest.valueCM + (chestEase?.valueCM ?? 0),
                    sources)
        }
        if let length = body["body_length"] {
            try put("BODY_SHELL", "height_cm", length.valueCM, [length.sourceTarget])
        }
        if let length = body["sleeve_length"] {
            try put("SLEEVE", "length_cm", length.valueCM, [length.sourceTarget])
        }
        if let length = body["inseam"] {
            try put("TUBE", "length_cm", length.valueCM, [length.sourceTarget])
        }
        if let waist = body["waist"] {
            let waistEase = ease["waist"]
            let value = waist.valueCM + (waistEase?.valueCM ?? 0)
            var sources: Set<String> = [waist.sourceTarget]
            if let waistEase { sources.insert(waistEase.sourceTarget) }
            for (primitive, field) in [
                ("FLARE", "top_circumference_cm"),
                ("FRUSTUM", "top_circumference_cm"),
                ("BAND", "length_cm"),
            ] {
                try put(primitive, field, value, sources)
            }
        }

        let directMap: [String: [(String, String)]] = [
            "body_length": [("BODY_SHELL", "height_cm")],
            "sleeve_length": [("SLEEVE", "length_cm")],
            "inseam": [("TUBE", "length_cm")],
            "skirt_length": [("FLARE", "height_cm"), ("FRUSTUM", "height_cm")],
            "garment_length": [("BODY_SHELL", "height_cm")],
            "hem_circumference": [("FLARE", "bottom_circumference_cm"),
                                  ("FRUSTUM", "bottom_circumference_cm")],
            "overlay_height": [("OVERLAY", "height_cm")],
        ]
        for (target, value) in direct {
            guard let addresses = directMap[target] else {
                reviewCodes.insert("UNKNOWN_GARMENT_DIMENSION_TARGET")
                continue
            }
            for (primitive, field) in addresses {
                try put(primitive, field, value.valueCM, [value.sourceTarget])
            }
        }
        return (result, reviewCodes)
    }

    private static func putInput(
        _ values: inout [String: Dimension], key: String, dimension: Dimension
    ) throws {
        if let old = values[key],
           (!nearlyEqual(old.valueCM, dimension.valueCM)
            || old.sourceTarget != dimension.sourceTarget) {
            throw Failure(code: "UNKNOWN_CONFLICTING_REQUIREMENT_DIMENSIONS",
                          detail: "conflicting values for \(key)")
        }
        values[key] = dimension
    }

    private static func dimension(
        _ item: GarmentCommandIR.Requirement
    ) throws -> Dimension? {
        guard let value = item.value, let unit = item.unit else { return nil }
        let multiplier: Double
        switch unit {
        case .mm: multiplier = 0.1
        case .cm: multiplier = 1
        case .m: multiplier = 100
        }
        let valueCM = value * multiplier
        guard valueCM.isFinite, valueCM > 0 else {
            throw Failure(code: "UNKNOWN_EXPLICIT_DIMENSION_REQUIRED",
                          detail: "dimension must be positive and finite")
        }
        return Dimension(valueCM: valueCM, sourceTarget: item.target)
    }

    private static func canonicalTarget(_ raw: String) -> String? {
        let text = normalized(raw)
        var matches: [(Int, String)] = []
        for (canonical, aliases) in targetAliases {
            for alias in aliases {
                let candidate = normalized(alias)
                if candidate == text || text.contains(candidate) {
                    matches.append((candidate.count, canonical))
                }
            }
        }
        return matches.sorted {
            $0.0 == $1.0 ? $0.1 > $1.1 : $0.0 > $1.0
        }.first?.1
    }

    private static func normalized(_ raw: String) -> String {
        raw.lowercased()
            .replacingOccurrences(of: "_", with: " ")
            .replacingOccurrences(of: "-", with: " ")
            .replacingOccurrences(of: ":", with: " ")
            .replacingOccurrences(of: "/", with: " ")
            .split(whereSeparator: { $0.isWhitespace })
            .joined(separator: " ")
    }

    // MARK: - Response validation and application

    private static func overrideAddressSet(_ supplied: [String: Any]) throws -> Set<String> {
        var result: Set<String> = []
        for (primitive, rawFields) in supplied {
            guard let fields = rawFields as? [String: Any] else {
                throw Failure(code: "UNKNOWN_PROFILE_OVERRIDE_SHAPE",
                              detail: "\(primitive) is not an object")
            }
            for field in fields.keys { result.insert("\(primitive).\(field)") }
        }
        return result
    }

    private static func validateNormalizedRequirements(
        _ normalized: [[String: Any]], request: [String: Any]
    ) throws {
        guard let requested = request["requirements"] as? [[String: Any]],
              normalized.count == requested.count else {
            throw Failure(code: "UNKNOWN_PROFILE_REQUIREMENT_PROVENANCE_MISMATCH",
                          detail: "normalized requirement count changed")
        }
        for (index, pair) in zip(requested, normalized).enumerated() {
            let source = pair.0
            let result = pair.1
            guard source["kind"] as? String == result["kind"] as? String,
                  source["target"] as? String == result["target"] as? String,
                  result["state"] as? String == "REQUESTED" else {
                throw Failure(code: "UNKNOWN_PROFILE_REQUIREMENT_PROVENANCE_MISMATCH",
                              detail: "requirements[\(index)] identity changed")
            }
            if let value = number(source["value"]),
               let unit = source["unit"] as? String {
                let multiplier: Double
                switch unit {
                case "mm": multiplier = 0.1
                case "cm": multiplier = 1
                case "m": multiplier = 100
                default:
                    throw Failure(code: "UNKNOWN_PROFILE_REQUIREMENT_PROVENANCE_MISMATCH",
                                  detail: "requirements[\(index)] unit changed")
                }
                guard let normalizedValue = number(result["value_cm"]),
                      nearlyEqual(normalizedValue, value * multiplier) else {
                    throw Failure(code: "UNKNOWN_PROFILE_REQUIREMENT_PROVENANCE_MISMATCH",
                                  detail: "requirements[\(index)] value changed")
                }
            }
            if let text = source["text"] as? String,
               result["text"] as? String != text {
                throw Failure(code: "UNKNOWN_PROFILE_REQUIREMENT_PROVENANCE_MISMATCH",
                              detail: "requirements[\(index)] text changed")
            }
        }
    }

    private static func validatedOverride(
        _ raw: [String: Any], primitive: String, field: String
    ) throws -> Override {
        guard let value = number(raw["value_cm"]), value.isFinite, value > 0,
              raw["unit"] as? String == "cm",
              raw["state"] as? String == "REQUESTED",
              raw["authority"] as? String
                == "USER_EXPLICIT_REQUEST_NOT_MEASUREMENT_CERTIFICATE",
              raw["not_measured_from_image"] as? Bool == true,
              raw["preview_only"] as? Bool == true,
              let sources = raw["source_requirement_targets"] as? [String],
              !sources.isEmpty else {
            throw Failure(code: "UNKNOWN_PROFILE_OVERRIDE_AUTHORITY",
                          detail: "\(primitive).\(field) lacks REQUESTED provenance")
        }
        return Override(
            valueCM: value,
            state: "REQUESTED",
            authority: "USER_EXPLICIT_REQUEST_NOT_MEASUREMENT_CERTIFICATE",
            sourceRequirementTargets: sources.sorted(),
            notMeasuredFromImage: true,
            previewOnly: true)
    }

    private struct RequirementGroup: Hashable {
        let valueBits: UInt64
        let sourceTargets: String
    }

    private struct PlannedApplication {
        let rowIndex: Int
        let field: String
        let override: Override
        let group: RequirementGroup
    }

    private struct ApplicationPlan {
        let container: String
        let rows: [[String: Any]]
        let applications: [PlannedApplication]
        let blockedGroups: Set<RequirementGroup>
        let reviewItems: [[String: Any]]
    }

    /// Resolve every primitive override against the complete candidate graph
    /// before changing a row.  Primitive kind is only the first selector;
    /// garment_unit/layer/side/placement/shape/detail_role form the bounded
    /// node address.  A non-unique address blocks the whole numeric
    /// requirement group rather than broadcasting it to every same-kind node.
    private static func applicationPlan(
        _ overrides: [String: [String: Override]],
        to rows: [[String: Any]],
        container: String
    ) -> ApplicationPlan {
        var applications: [PlannedApplication] = []
        var blockedGroups: Set<RequirementGroup> = []
        var reviewItems: [[String: Any]] = []

        for primitive in overrides.keys.sorted() {
            guard let fields = overrides[primitive] else { continue }
            let primitiveRows = rows.indices.filter { index in
                guard let rawKind = rows[index]["kind"] as? String else {
                    return false
                }
                return primitiveKind(rawKind) == primitive
            }
            guard !primitiveRows.isEmpty else { continue }

            for field in fields.keys.sorted() {
                guard let override = fields[field] else { continue }
                let group = requirementGroup(override)
                var eligible = primitiveRows

                // BAND and TUBE share their primitive with unrelated garment
                // geometry.  Their semantic gate runs before graph-address
                // uniqueness, preserving the existing conservative policy.
                if primitive == "BAND" {
                    eligible = primitiveRows.filter { bandAddress(rows[$0]) == .waist }
                    for index in primitiveRows where bandAddress(rows[index]) == .ambiguous {
                        let nodeID = rowIdentifier(rows[index], fallback: "unknown-band")
                        reviewItems.append([
                            "code": "UNKNOWN_REQUIREMENT_BAND_NODE_ADDRESS",
                            "node_id": nodeID,
                            "container": container,
                            "why": "waist-derived BAND dimensions require explicit waist/belt/sash placement or detail_role",
                            "state": "REVIEW",
                        ])
                    }
                }
                if primitive == "TUBE" {
                    eligible = primitiveRows.filter { tubeAddress(rows[$0]) == .trouserLeg }
                    for index in primitiveRows where tubeAddress(rows[index]) == .ambiguous {
                        let nodeID = rowIdentifier(rows[index], fallback: "unknown-tube")
                        reviewItems.append([
                            "code": "UNKNOWN_REQUIREMENT_TUBE_NODE_ADDRESS",
                            "node_id": nodeID,
                            "container": container,
                            "why": "inseam-derived TUBE length requires explicit trouser/leg side, placement, shape or detail_role",
                            "state": "REVIEW",
                        ])
                    }
                }

                guard !eligible.isEmpty else { continue }
                let resolved = resolveCandidateGraphAddress(
                    eligible, rows: rows,
                    sourceTargets: override.sourceRequirementTargets)
                guard resolved.count == 1, let rowIndex = resolved.first else {
                    blockedGroups.insert(group)
                    reviewItems.append([
                        "code": "UNKNOWN_REQUIREMENT_CANDIDATE_GRAPH_ADDRESS_AMBIGUOUS",
                        "primitive": primitive,
                        "field": field,
                        "container": container,
                        "candidate_node_ids": eligible.map {
                            rowIdentifier(rows[$0], fallback: "row-\($0)")
                        }.sorted(),
                        "source_requirement_targets": override.sourceRequirementTargets,
                        "required_address_fields": [
                            "garment_unit", "layer", "side", "placement",
                            "shape", "detail_role",
                        ],
                        "why": "numeric requirement matches multiple distinct candidate nodes without a sufficient explicit graph address",
                        "state": "REVIEW",
                    ])
                    continue
                }
                applications.append(PlannedApplication(
                    rowIndex: rowIndex, field: field,
                    override: override, group: group))
            }
        }

        // Circumference edits can describe both sides of one seam (for
        // example a skirt top plus an attached waistband).  They are allowed
        // as a group only when every affected pair has an explicit graph edge.
        let grouped = Dictionary(grouping: applications, by: \.group)
        for (group, edits) in grouped where !blockedGroups.contains(group) {
            let seamEdits = edits.filter { isSeamCircumferenceField($0.field) }
            if seamEdits.count > 1 && !isExactJoinedGroup(seamEdits, rows: rows) {
                blockedGroups.insert(group)
                reviewItems.append([
                    "code": "UNKNOWN_REQUIREMENT_SEAM_ADDRESS_NOT_EXACT",
                    "container": container,
                    "candidate_node_ids": seamEdits.map {
                        rowIdentifier(rows[$0.rowIndex], fallback: "row-\($0.rowIndex)")
                    }.sorted(),
                    "source_requirement_targets": seamEdits.first?
                        .override.sourceRequirementTargets ?? [],
                    "why": "joined seam circumference requires an explicit attached_to edge; no side was changed",
                    "state": "REVIEW",
                ])
            }
        }

        return ApplicationPlan(container: container, rows: rows,
                               applications: applications,
                               blockedGroups: blockedGroups,
                               reviewItems: reviewItems)
    }

    private static func applying(
        _ plan: ApplicationPlan, blockedGroups: Set<RequirementGroup>
    ) -> (rows: [[String: Any]], count: Int) {
        var rows = plan.rows
        var count = 0
        for edit in plan.applications where !blockedGroups.contains(edit.group) {
            var row = rows[edit.rowIndex]
            var dimensions = row["dimensions"] as? [String: Any] ?? [:]
            var provenance = row["dimension_provenance"] as? [String: Any] ?? [:]
            dimensions[edit.field] = edit.override.valueCM
            provenance[edit.field] = edit.override.provenanceDictionary
            row["dimensions"] = dimensions
            row["dimension_provenance"] = provenance
            row["measurement_authority"] = "REQUESTED_NOT_MEASURED"
            rows[edit.rowIndex] = row
            count += 1
        }
        return (rows, count)
    }

    private static func requirementGroup(_ override: Override) -> RequirementGroup {
        RequirementGroup(
            valueBits: override.valueCM.bitPattern,
            sourceTargets: override.sourceRequirementTargets.sorted()
                .joined(separator: "\u{1f}"))
    }

    private static let graphAddressFields = [
        "garment_unit", "layer", "side", "placement", "shape", "detail_role",
    ]

    private static let graphAddressStopWords: Set<String> = [
        "body", "shell", "bodice", "sleeve", "skirt", "flare", "frustum",
        "overlay", "tube", "band", "garment", "dress", "coat", "trouser",
        "trousers", "pant", "pants", "length", "width", "height",
        "circumference", "measurement", "ease", "cm", "mm", "arm", "leg",
        "layer", "unit", "look", "身頃", "袖", "スカート", "服", "着丈",
        "袖丈", "丈", "幅", "周囲", "寸法", "ゆとり", "腕", "脚",
    ]

    private static func resolveCandidateGraphAddress(
        _ candidateIndexes: [Int], rows: [[String: Any]],
        sourceTargets: [String]
    ) -> [Int] {
        guard candidateIndexes.count > 1 else { return candidateIndexes }
        let source = normalized(sourceTargets.joined(separator: " "))
        let sourceTokens = Set(source.split(separator: " ").map(String.init))
        var resolved = candidateIndexes
        var usedExplicitHint = false

        for field in graphAddressFields {
            var matchedValues: Set<String> = []
            for index in candidateIndexes {
                for value in semanticValues(field, in: rows[index]) {
                    let normalizedValue = normalized(value)
                    guard !normalizedValue.isEmpty else { continue }
                    let tokens = normalizedValue.split(separator: " ").map(String.init)
                    let significant = tokens.filter {
                        $0.count > 1 && !graphAddressStopWords.contains($0)
                    }
                    let numericLayerMatch = field == "layer" &&
                        (source.contains("layer \(normalizedValue)") ||
                         sourceTokens.contains(normalizedValue))
                    if numericLayerMatch ||
                        (!significant.isEmpty && source.contains(normalizedValue)) ||
                        significant.contains(where: sourceTokens.contains) {
                        matchedValues.insert(normalizedValue)
                    }
                }
            }
            guard !matchedValues.isEmpty else { continue }
            usedExplicitHint = true
            resolved = resolved.filter { index in
                semanticValues(field, in: rows[index]).contains { value in
                    matchedValues.contains(normalized(value))
                }
            }
        }
        return usedExplicitHint ? resolved : candidateIndexes
    }

    private static func isSeamCircumferenceField(_ field: String) -> Bool {
        ["circumference_cm", "top_circumference_cm",
         "bottom_circumference_cm", "length_cm"].contains(field)
    }

    private static func isExactJoinedGroup(
        _ edits: [PlannedApplication], rows: [[String: Any]]
    ) -> Bool {
        let indexes = Set(edits.map(\.rowIndex))
        guard indexes.count > 1 else { return true }
        let ids = Dictionary(uniqueKeysWithValues: indexes.map { index in
            (index, rowIdentifier(rows[index], fallback: ""))
        })
        guard ids.values.allSatisfy({ !$0.isEmpty }) else { return false }

        func isJoined(_ lhs: Int, _ rhs: Int) -> Bool {
            let lhsReferences = Set(semanticValues("attached_to", in: rows[lhs]))
            let rhsReferences = Set(semanticValues("attached_to", in: rows[rhs]))
            return lhsReferences.contains(ids[rhs] ?? "") ||
                rhsReferences.contains(ids[lhs] ?? "")
        }

        // Every selected seam side must belong to one explicit connected
        // component. Merely giving each node some neighbour would still allow
        // two unrelated seams to be edited by one requirement.
        guard let first = indexes.first else { return false }
        var visited: Set<Int> = [first]
        var frontier = [first]
        while let current = frontier.popLast() {
            for peer in indexes where !visited.contains(peer) && isJoined(current, peer) {
                visited.insert(peer)
                frontier.append(peer)
            }
        }
        return visited == indexes
    }

    private static func rowIdentifier(
        _ row: [String: Any], fallback: String
    ) -> String {
        row["node_id"] as? String
            ?? row["part_id"] as? String
            ?? row["id"] as? String
            ?? fallback
    }

    private enum BandAddress {
        case waist
        case other
        case ambiguous
    }

    /// A primitive-level profile cannot distinguish a waist belt from a hem
    /// ruffle, cuff, neck ribbon or tie because all of them compile to BAND.
    /// Candidate metadata therefore supplies the final deterministic address.
    private static func bandAddress(_ row: [String: Any]) -> BandAddress {
        let placement = normalized(semanticText("placement", in: row))
        let detailRole = normalized(semanticText("detail_role", in: row))
        let shape = normalized(semanticText("shape", in: row))
        let address = [placement, detailRole, shape].filter { !$0.isEmpty }
            .joined(separator: " ")
        let waistTerms = ["waist", "belt", "sash", "ウエスト", "ベルト", "帯"]
        if waistTerms.contains(where: address.contains) { return .waist }

        let otherTerms = [
            "hem", "ruffle", "frill", "cuff", "wrist", "sleeve", "tie",
            "neck", "neckline", "collar", "裾", "フリル", "袖口", "袖",
            "手首", "タイ", "襟", "首",
        ]
        if otherTerms.contains(where: address.contains) { return .other }
        return .ambiguous
    }

    private enum TubeAddress {
        case trouserLeg
        case other
        case ambiguous
    }

    /// TUBE is shared by trouser legs and unrelated cylindrical geometry.
    /// Inseam may address only a node whose own semantics explicitly identify
    /// a leg; left/right alone is insufficient because sleeves also have sides.
    private static func tubeAddress(_ row: [String: Any]) -> TubeAddress {
        let fields = ["side", "detail_role", "shape", "placement"]
        let address = fields.map { semanticText($0, in: row) }
            .map(normalized)
            .filter { !$0.isEmpty }
            .joined(separator: " ")
        let legTerms = [
            "leg", "trouser", "trousers", "pant", "pants", "inseam",
            "legging", "lower limb", "ズボン", "パンツ", "股下", "脚",
        ]
        if legTerms.contains(where: address.contains) { return .trouserLeg }

        let otherTerms = [
            "skirt", "dress", "sleeve", "arm", "cuff", "neck", "collar",
            "boot", "shoe", "footwear", "hem", "スカート", "ドレス", "袖",
            "腕", "袖口", "襟", "首", "ブーツ", "靴", "裾",
        ]
        if otherTerms.contains(where: address.contains) { return .other }
        return .ambiguous
    }

    /// Parts IR stores semantics at row level, while a structure candidate
    /// stores the same proposal fields under `attributes`.  Both forms pass
    /// through this bridge; address guards must inspect the actual form used
    /// by the vision controller rather than treating every nested node as
    /// ambiguous.
    private static func semanticText(_ key: String, in row: [String: Any]) -> String {
        semanticValues(key, in: row).first ?? ""
    }

    private static func semanticValues(
        _ key: String, in row: [String: Any]
    ) -> [String] {
        func strings(_ raw: Any?) -> [String] {
            if let value = raw as? String,
               !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                return [value]
            }
            if let values = raw as? [String] {
                return values.filter {
                    !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                }
            }
            if key == "layer", let value = number(raw), value.isFinite {
                return [value.rounded() == value
                    ? String(Int(value)) : String(value)]
            }
            return []
        }
        let direct = strings(row[key])
        if !direct.isEmpty { return direct }
        let attributes = row["attributes"] as? [String: Any]
        return strings(attributes?[key])
    }

    private static func primitiveKind(_ raw: String) -> String {
        switch raw.uppercased() {
        case "BODICE": return "BODY_SHELL"
        case "SKIRT": return "FLARE"
        default: return raw.uppercased()
        }
    }

    private static func number(_ value: Any?) -> Double? {
        if let value = value as? Double { return value }
        if let value = value as? Int { return Double(value) }
        if let value = value as? NSNumber { return value.doubleValue }
        return nil
    }

    private static func nearlyEqual(_ lhs: Double, _ rhs: Double) -> Bool {
        abs(lhs - rhs) <= 1e-8 * max(1, abs(lhs), abs(rhs))
    }
}
