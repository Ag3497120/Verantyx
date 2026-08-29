import Foundation

#if !GARMENT_DESIGN_REQUIREMENT_PROFILE_STANDALONE
import XCTest
@testable import Verantyx
#endif

private enum GarmentDesignRequirementProfileBridgeAudit {
    static func failures() -> [String] {
        var failures = sourceFailures()
        failures.append(contentsOf: runtimeFailures())
        return failures
    }

    private static func sourceFailures() -> [String] {
        let file = URL(fileURLWithPath: #filePath)
        let appRoot = file.deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let bridgeURL = appRoot.appendingPathComponent(
            "Sources/Verantyx/Engine/GarmentDesignRequirementProfileBridge.swift")
        let controllerURL = appRoot.appendingPathComponent(
            "Sources/Verantyx/Engine/GarmentFactoryReactController.swift")
        let routerURL = appRoot.appendingPathComponent(
            "Sources/Verantyx/Engine/AtelierChatRouter.swift")
        guard let source = try? String(contentsOf: bridgeURL, encoding: .utf8),
              let controller = try? String(contentsOf: controllerURL, encoding: .utf8),
              let router = try? String(contentsOf: routerURL, encoding: .utf8) else {
            return ["REQUIREMENT_PROFILE_BRIDGE_SOURCE_UNREADABLE"]
        }
        var failures: [String] = []
        func require(_ condition: Bool, _ code: String) {
            if !condition { failures.append(code) }
        }
        require(source.contains("garment_design_requirement_profile") &&
                source.contains("MCPEngine.shared.callTool") &&
                source.contains("serverName: serverName") &&
                source.contains("arguments: prepared.arguments"),
                "MCP_ENGINE_CALL_CONVENTION_MISSING")
        require(source.contains("UNKNOWN_STANDARD_SIZE_CHART_REQUIRED") &&
                source.contains("UNKNOWN_EASE_TARGET_REQUIRED"),
                "SIZE_OR_GENERIC_EASE_REVIEW_GATE_MISSING")
        require(source.contains("expectedOverrides") &&
                source.contains("UNKNOWN_PROFILE_OVERRIDE_SET_MISMATCH") &&
                source.contains("UNKNOWN_PROFILE_OVERRIDE_VALUE_MISMATCH"),
                "MCP_OVERRIDE_ALLOW_LIST_VALIDATION_MISSING")
        require(source.contains("USER_EXPLICIT_REQUEST_NOT_MEASUREMENT_CERTIFICATE") &&
                source.contains("REQUESTED_NOT_MEASURED") &&
                source.contains("not_measured_from_image"),
                "REQUESTED_PROVENANCE_BOUNDARY_MISSING")
        require(source.contains("output[\"manufacturing_ready\"] = false") &&
                source.contains("output[\"manufacturing_certified\"] = false"),
                "APPLIED_CANDIDATE_CAN_CLAIM_MANUFACTURING_READINESS")
        require(source.contains("structure[\"nodes\"]") &&
                source.contains("partsIR[\"parts\"]") &&
                source.contains("output[\"parts\"]"),
                "CANDIDATE_STRUCTURE_AND_PARTS_APPLICATION_MISSING")
        require(source.contains("bandAddress") &&
                source.contains("UNKNOWN_REQUIREMENT_BAND_NODE_ADDRESS") &&
                source.contains("waist-derived BAND dimensions require explicit"),
                "PRIMITIVE_LEVEL_BAND_OVERRIDE_HAS_NO_NODE_ADDRESS_GATE")
        require(source.contains("tubeAddress") &&
                source.contains("UNKNOWN_REQUIREMENT_TUBE_NODE_ADDRESS") &&
                source.contains("inseam-derived TUBE length requires explicit"),
                "PRIMITIVE_LEVEL_TUBE_OVERRIDE_HAS_NO_NODE_ADDRESS_GATE")
        require(source.contains("graphAddressFields") &&
                source.contains("garment_unit") &&
                source.contains("layer") &&
                source.contains("UNKNOWN_REQUIREMENT_CANDIDATE_GRAPH_ADDRESS_AMBIGUOUS"),
                "LAYERED_CANDIDATE_GRAPH_ADDRESS_GATE_MISSING")
        require(source.contains("UNKNOWN_REQUIREMENT_SEAM_ADDRESS_NOT_EXACT") &&
                source.contains("blockedGroups") &&
                source.contains("attached_to"),
                "JOINED_SEAM_ATOMIC_ADDRESS_GATE_MISSING")
        require(controller.contains(
                    "designRequirements: [GarmentCommandIR.Requirement] = []") &&
                controller.contains("applyDesignRequirements(to: rows)") &&
                controller.contains("GarmentDesignRequirementProfileBridge.validate(") &&
                controller.contains("requested_dimension_fields_applied"),
                "FACTORY_DOES_NOT_APPLY_TYPED_REQUIREMENTS_BEFORE_PARTS_PIPELINE")
        require(router.components(separatedBy:
                    "designRequirements: command.operation?.requirements ?? []").count == 3,
                "BEGINNER_IMAGE_ROUTES_DROP_TYPED_REQUIREMENTS")
        require(controller.contains("USER_EXPLICIT_REQUEST_NOT_MEASUREMENT_CERTIFICATE") &&
                controller.contains("\"state\": \"PROPOSED\"") &&
                controller.contains("not_measured_from_image"),
                "REQUESTED_DIMENSION_PROVENANCE_IS_NOT_PRESERVED_TO_PARTS_IR")
        return failures
    }

    private static func runtimeFailures() -> [String] {
        var failures: [String] = []
        func require(_ condition: @autoclosure () -> Bool, _ code: String) {
            if !condition() { failures.append(code) }
        }

        let requirements: [GarmentCommandIR.Requirement] = [
            .init(kind: .standardSize, target: "wearer_size", text: "M",
                  value: nil, unit: nil, note: "user selected M"),
            .init(kind: .bodyMeasurement, target: "waist", text: nil,
                  value: 72, unit: .cm, note: "explicit user value"),
            .init(kind: .ease, target: "waist ease", text: nil,
                  value: 40, unit: .mm, note: "explicit user value"),
            .init(kind: .bodyMeasurement, target: "inseam", text: nil,
                  value: 78, unit: .cm, note: "explicit user value"),
        ]
        let prepared: GarmentDesignRequirementProfileBridge.PreparedRequest
        do {
            prepared = try GarmentDesignRequirementProfileBridge.prepare(
                requirements: requirements)
        } catch {
            return failures + ["VALID_REQUIREMENTS_PREPARATION_FAILED_\(error)"]
        }
        require(prepared.arguments.keys.sorted() == ["json_text"],
                "MCP_ARGUMENT_SHAPE_IS_NOT_JSON_TEXT_ONLY")
        if let data = prepared.jsonText.data(using: .utf8),
           let request = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            require(request["schema"] as? String
                    == GarmentDesignRequirementProfileBridge.requestSchema,
                    "REQUEST_SCHEMA_CHANGED")
            require((request["requirements"] as? [[String: Any]])?.count == 4,
                    "TYPED_REQUIREMENTS_DROPPED_DURING_ENCODING")
        } else {
            failures.append("PREPARED_JSON_IS_NOT_DECODABLE")
        }

        let response = profileResponse(
            overrides: waistOverrides(),
            reviewItems: [[
                "code": "UNKNOWN_STANDARD_SIZE_CHART_REQUIRED",
                "targets": ["wearer_size"],
                "why": "M is a label, not a measurement",
            ]],
            requirements: [
                ["kind": "STANDARD_SIZE", "target": "wearer_size",
                 "text": "M", "state": "REQUESTED"],
                ["kind": "BODY_MEASUREMENT", "target": "waist",
                 "value_cm": 72.0, "state": "REQUESTED"],
                ["kind": "EASE", "target": "waist ease",
                 "value_cm": 4.0, "state": "REQUESTED"],
                ["kind": "BODY_MEASUREMENT", "target": "inseam",
                 "value_cm": 78.0, "state": "REQUESTED"],
            ])
        let profile: GarmentDesignRequirementProfileBridge.ValidatedProfile
        do {
            profile = try GarmentDesignRequirementProfileBridge.validate(
                response: response, prepared: prepared)
        } catch {
            return failures + ["VALID_PROFILE_RESPONSE_REJECTED_\(error)"]
        }
        require(profile.verdict == "REVIEW",
                "M_WITHOUT_CHART_DID_NOT_REMAIN_REVIEW")
        require(profile.reviewItems.contains {
            $0["code"] as? String == "UNKNOWN_STANDARD_SIZE_CHART_REQUIRED"
        }, "SIZE_CHART_REVIEW_ITEM_WAS_LOST")

        let candidate: [String: Any] = [
            "candidate_id": "front-a",
            "manufacturing_ready": true,
            "structure": ["nodes": [
                ["node_id": "body", "kind": "BODY_SHELL",
                 "dimensions": ["circumference_cm": 92.0]],
                ["node_id": "skirt", "kind": "FLARE",
                 "attributes": ["attached_to": "body"],
                 "dimensions": ["top_circumference_cm": 70.0]],
                ["node_id": "belt", "kind": "BAND",
                 "attributes": ["placement": "waist", "detail_role": "belt",
                                "attached_to": "skirt"],
                 "dimensions": ["length_cm": 70.0]],
                ["node_id": "hem-ruffle", "kind": "BAND",
                 "attributes": ["placement": "skirt hem", "detail_role": "ruffle"],
                 "dimensions": ["length_cm": 144.0]],
                ["node_id": "ambiguous-band", "kind": "BAND",
                 "attributes": ["placement": "center front"],
                 "dimensions": ["length_cm": 51.0]],
                ["node_id": "trouser-left", "kind": "TUBE",
                 "attributes": ["side": "left leg", "detail_role": "trouser_leg",
                                "shape": "tapered trouser", "placement": "lower limb"],
                 "dimensions": ["length_cm": 74.0]],
                ["node_id": "straight-skirt-tube", "kind": "TUBE",
                 "attributes": ["shape": "straight skirt",
                                "placement": "skirt lower body"],
                 "dimensions": ["length_cm": 62.0]],
                ["node_id": "ambiguous-tube", "kind": "TUBE",
                 "attributes": ["side": "left", "placement": "lower"],
                 "dimensions": ["length_cm": 55.0]],
            ]],
            "parts": [
                ["part_id": "skirt-part", "kind": "SKIRT",
                 "dimensions": ["top_circumference_cm": 70.0]],
            ],
        ]
        do {
            let applied = try GarmentDesignRequirementProfileBridge.apply(
                profile, to: candidate)
            require(applied.appliedFieldCount == 4,
                    "EXPECTED_STRUCTURE_AND_PART_OVERRIDES_NOT_APPLIED")
            require(applied.candidate["manufacturing_ready"] as? Bool == false &&
                    applied.candidate["manufacturing_certified"] as? Bool == false,
                    "APPLIED_CANDIDATE_CLAIMS_MANUFACTURING_READINESS")
            if let structure = applied.candidate["structure"] as? [String: Any],
               let nodes = structure["nodes"] as? [[String: Any]],
               let skirt = nodes.first(where: { $0["node_id"] as? String == "skirt" }),
               let dimensions = skirt["dimensions"] as? [String: Any],
               let provenance = skirt["dimension_provenance"] as? [String: Any],
               let top = provenance["top_circumference_cm"] as? [String: Any] {
                require(number(dimensions["top_circumference_cm"]) == 76,
                        "WAIST_AND_EASE_WERE_NOT_COMBINED_TO_76CM")
                require(top["state"] as? String == "REQUESTED" &&
                        top["not_measured_from_image"] as? Bool == true &&
                        top["preview_only"] as? Bool == true,
                        "APPLIED_DIMENSION_LOST_REQUESTED_PROVENANCE")
                let body = nodes.first { $0["node_id"] as? String == "body" }
                let bodyDimensions = body?["dimensions"] as? [String: Any]
                require(number(bodyDimensions?["circumference_cm"]) == 92,
                        "WAIST_REQUIREMENT_WAS_SILENTLY_ASSIGNED_TO_BODY_CHEST")
                let belt = nodes.first { $0["node_id"] as? String == "belt" }
                let beltDimensions = belt?["dimensions"] as? [String: Any]
                require(number(beltDimensions?["length_cm"]) == 76,
                        "EXPLICIT_WAIST_BELT_WAS_NOT_UPDATED")
                let ruffle = nodes.first { $0["node_id"] as? String == "hem-ruffle" }
                let ruffleDimensions = ruffle?["dimensions"] as? [String: Any]
                require(number(ruffleDimensions?["length_cm"]) == 144,
                        "WAIST_LENGTH_WAS_APPLIED_TO_HEM_RUFFLE_BAND")
                let ambiguous = nodes.first {
                    $0["node_id"] as? String == "ambiguous-band"
                }
                let ambiguousDimensions = ambiguous?["dimensions"] as? [String: Any]
                require(number(ambiguousDimensions?["length_cm"]) == 51,
                        "WAIST_LENGTH_WAS_APPLIED_TO_AMBIGUOUS_BAND")
                require(applied.applicationReviewItems.contains {
                    $0["code"] as? String
                        == "UNKNOWN_REQUIREMENT_BAND_NODE_ADDRESS" &&
                    $0["node_id"] as? String == "ambiguous-band"
                }, "AMBIGUOUS_BAND_DID_NOT_PRESERVE_REVIEW")
                let trouser = nodes.first {
                    $0["node_id"] as? String == "trouser-left"
                }
                let trouserDimensions = trouser?["dimensions"] as? [String: Any]
                require(number(trouserDimensions?["length_cm"]) == 78,
                        "EXPLICIT_TROUSER_LEG_DID_NOT_RECEIVE_INSEAM")
                let straightSkirt = nodes.first {
                    $0["node_id"] as? String == "straight-skirt-tube"
                }
                let skirtTubeDimensions = straightSkirt?["dimensions"] as? [String: Any]
                require(number(skirtTubeDimensions?["length_cm"]) == 62,
                        "INSEAM_WAS_APPLIED_TO_STRAIGHT_SKIRT_TUBE")
                let ambiguousTube = nodes.first {
                    $0["node_id"] as? String == "ambiguous-tube"
                }
                let ambiguousTubeDimensions = ambiguousTube?["dimensions"]
                    as? [String: Any]
                require(number(ambiguousTubeDimensions?["length_cm"]) == 55,
                        "INSEAM_WAS_APPLIED_TO_AMBIGUOUS_TUBE")
                require(applied.applicationReviewItems.contains {
                    $0["code"] as? String
                        == "UNKNOWN_REQUIREMENT_TUBE_NODE_ADDRESS" &&
                    $0["node_id"] as? String == "ambiguous-tube"
                }, "AMBIGUOUS_TUBE_DID_NOT_PRESERVE_REVIEW")
                require(applied.verdict == "REVIEW",
                        "AMBIGUOUS_NODE_DID_NOT_PROMOTE_APPLIED_RESULT_TO_REVIEW")
            } else {
                failures.append("APPLIED_STRUCTURE_IS_NOT_READABLE")
            }
            if let metadata = applied.candidate["design_requirement_profile"]
                as? [String: Any],
               let reviews = metadata["review_items"] as? [[String: Any]] {
                require(reviews.contains {
                    $0["code"] as? String == "UNKNOWN_STANDARD_SIZE_CHART_REQUIRED"
                }, "APPLIED_CANDIDATE_LOST_REVIEW_ITEMS")
            } else {
                failures.append("APPLIED_PROFILE_METADATA_MISSING")
            }

            let reapplied = try GarmentDesignRequirementProfileBridge.apply(
                profile, to: candidate)
            require(canonicalJSON(applied.candidate) == canonicalJSON(reapplied.candidate),
                    "CANDIDATE_APPLICATION_IS_NOT_DETERMINISTIC")
        } catch {
            failures.append("VALID_PROFILE_APPLICATION_FAILED_\(error)")
        }

        failures.append(contentsOf: layeredAddressFailures())

        // A malicious or stale MCP response cannot turn M into dimensions.
        let sizeOnly: [GarmentCommandIR.Requirement] = [
            .init(kind: .standardSize, target: "wearer_size", text: "M",
                  value: nil, unit: nil, note: nil),
        ]
        do {
            let sizePrepared = try GarmentDesignRequirementProfileBridge.prepare(
                requirements: sizeOnly)
            let malicious = profileResponse(
                overrides: ["BODY_SHELL": ["circumference_cm": overrideRecord(
                    value: 92, sources: ["wearer_size"]) ]],
                reviewItems: [["code": "UNKNOWN_STANDARD_SIZE_CHART_REQUIRED"]],
                requirements: [["kind": "STANDARD_SIZE", "target": "wearer_size",
                                "text": "M", "state": "REQUESTED"]])
            do {
                _ = try GarmentDesignRequirementProfileBridge.validate(
                    response: malicious, prepared: sizePrepared)
                failures.append("STANDARD_SIZE_INVENTED_MEASUREMENT_WAS_ACCEPTED")
            } catch let error as GarmentDesignRequirementProfileBridge.Failure {
                require(error.code == "UNKNOWN_PROFILE_OVERRIDE_SET_MISMATCH",
                        "STANDARD_SIZE_MALICE_WRONG_REFUSAL")
            }
        } catch {
            failures.append("SIZE_ONLY_REQUEST_PREPARATION_FAILED_\(error)")
        }

        // Numeric but unscoped ease remains visible as REVIEW and has no
        // geometry address. It is never guessed to mean waist/chest/hip.
        let genericEase: [GarmentCommandIR.Requirement] = [
            .init(kind: .ease, target: "ease", text: nil,
                  value: 4, unit: .cm, note: nil),
        ]
        do {
            let easePrepared = try GarmentDesignRequirementProfileBridge.prepare(
                requirements: genericEase)
            let safe = profileResponse(
                overrides: [:],
                reviewItems: [["code": "UNKNOWN_EASE_TARGET_REQUIRED"]],
                requirements: [["kind": "EASE", "target": "ease",
                                "value_cm": 4.0, "state": "REQUESTED"]])
            _ = try GarmentDesignRequirementProfileBridge.validate(
                response: safe, prepared: easePrepared)
            let malicious = profileResponse(
                overrides: ["FLARE": ["top_circumference_cm": overrideRecord(
                    value: 76, sources: ["ease"]) ]],
                reviewItems: [["code": "UNKNOWN_EASE_TARGET_REQUIRED"]],
                requirements: [["kind": "EASE", "target": "ease",
                                "value_cm": 4.0, "state": "REQUESTED"]])
            do {
                _ = try GarmentDesignRequirementProfileBridge.validate(
                    response: malicious, prepared: easePrepared)
                failures.append("GENERIC_EASE_SILENT_ASSIGNMENT_WAS_ACCEPTED")
            } catch let error as GarmentDesignRequirementProfileBridge.Failure {
                require(error.code == "UNKNOWN_PROFILE_OVERRIDE_SET_MISMATCH",
                        "GENERIC_EASE_MALICE_WRONG_REFUSAL")
            }
        } catch {
            failures.append("GENERIC_EASE_REVIEW_FLOW_FAILED_\(error)")
        }

        var authorityViolation = response
        authorityViolation["manufacturing_ready"] = true
        do {
            _ = try GarmentDesignRequirementProfileBridge.validate(
                response: authorityViolation, prepared: prepared)
            failures.append("MANUFACTURING_READY_RESPONSE_WAS_ACCEPTED")
        } catch let error as GarmentDesignRequirementProfileBridge.Failure {
            require(error.code == "UNKNOWN_REQUIREMENT_PROFILE_AUTHORITY",
                    "MANUFACTURING_AUTHORITY_WRONG_REFUSAL")
        } catch {
            failures.append("MANUFACTURING_AUTHORITY_UNTYPED_REFUSAL")
        }
        return failures
    }

    private static func layeredAddressFailures() -> [String] {
        var failures: [String] = []
        func require(_ condition: @autoclosure () -> Bool, _ code: String) {
            if !condition() { failures.append(code) }
        }

        func sleeveProfile(
            target: String
        ) throws -> GarmentDesignRequirementProfileBridge.ValidatedProfile {
            let requirements: [GarmentCommandIR.Requirement] = [
                .init(kind: .bodyMeasurement, target: target, text: nil,
                      value: 61, unit: .cm, note: "explicit user value"),
            ]
            let prepared = try GarmentDesignRequirementProfileBridge.prepare(
                requirements: requirements)
            return try GarmentDesignRequirementProfileBridge.validate(
                response: profileResponse(
                    overrides: [
                        "SLEEVE": ["length_cm": overrideRecord(
                            value: 61, sources: [target])],
                    ],
                    reviewItems: [],
                    requirements: [[
                        "kind": "BODY_MEASUREMENT", "target": target,
                        "value_cm": 61.0, "state": "REQUESTED",
                    ]]),
                prepared: prepared)
        }

        let layeredSleeves: [[String: Any]] = [
            ["node_id": "outer-left-sleeve", "kind": "SLEEVE",
             "attributes": ["garment_unit": "look-alpha", "layer": "outer",
                            "side": "left", "placement": "left arm",
                            "shape": "bell sleeve", "detail_role": "outer sleeve"],
             "dimensions": ["length_cm": 48.0]],
            ["node_id": "inner-right-sleeve", "kind": "SLEEVE",
             "attributes": ["garment_unit": "look-alpha", "layer": "inner",
                            "side": "right", "placement": "right arm",
                            "shape": "fitted sleeve", "detail_role": "under sleeve"],
             "dimensions": ["length_cm": 52.0]],
        ]

        do {
            let generic = try sleeveProfile(target: "sleeve length")
            let candidate: [String: Any] = [
                "structure": ["nodes": layeredSleeves],
                "parts": [[
                    "part_id": "single-flat-sleeve", "kind": "SLEEVE",
                    "dimensions": ["length_cm": 49.0],
                ]],
            ]
            let applied = try GarmentDesignRequirementProfileBridge.apply(
                generic, to: candidate)
            require(applied.appliedFieldCount == 0,
                    "AMBIGUOUS_LAYERED_REQUIREMENT_PARTIALLY_MUTATED_CANDIDATE")
            require(applied.verdict == "REVIEW",
                    "AMBIGUOUS_LAYERED_REQUIREMENT_DID_NOT_RETAIN_REVIEW")
            require(applied.applicationReviewItems.contains {
                $0["code"] as? String
                    == "UNKNOWN_REQUIREMENT_CANDIDATE_GRAPH_ADDRESS_AMBIGUOUS" &&
                $0["primitive"] as? String == "SLEEVE" &&
                $0["field"] as? String == "length_cm"
            }, "AMBIGUOUS_LAYERED_REQUIREMENT_EXACT_REVIEW_CODE_MISSING")
            let structure = applied.candidate["structure"] as? [String: Any] ?? [:]
            let nodes = structure["nodes"] as? [[String: Any]] ?? []
            require(number((nodes.first {
                $0["node_id"] as? String == "outer-left-sleeve"
            }?["dimensions"] as? [String: Any])?["length_cm"]) == 48,
                    "AMBIGUOUS_LAYERED_REQUIREMENT_CHANGED_OUTER_SLEEVE")
            require(number((nodes.first {
                $0["node_id"] as? String == "inner-right-sleeve"
            }?["dimensions"] as? [String: Any])?["length_cm"]) == 52,
                    "AMBIGUOUS_LAYERED_REQUIREMENT_CHANGED_INNER_SLEEVE")
            let parts = applied.candidate["parts"] as? [[String: Any]] ?? []
            let partDimensions = parts.first?["dimensions"] as? [String: Any]
            require(number(partDimensions?["length_cm"]) == 49,
                    "AMBIGUOUS_STRUCTURE_REQUIREMENT_CHANGED_FLAT_PART_REPRESENTATION")
        } catch {
            failures.append("AMBIGUOUS_LAYERED_REQUIREMENT_AUDIT_FAILED_\(error)")
        }

        do {
            let addressed = try sleeveProfile(
                target: "look alpha outer left sleeve length")
            let applied = try GarmentDesignRequirementProfileBridge.apply(
                addressed, to: ["structure": ["nodes": layeredSleeves]])
            require(applied.appliedFieldCount == 1,
                    "EXPLICIT_LAYERED_GRAPH_ADDRESS_DID_NOT_SELECT_ONE_NODE")
            let structure = applied.candidate["structure"] as? [String: Any] ?? [:]
            let nodes = structure["nodes"] as? [[String: Any]] ?? []
            require(number((nodes.first {
                $0["node_id"] as? String == "outer-left-sleeve"
            }?["dimensions"] as? [String: Any])?["length_cm"]) == 61,
                    "EXPLICIT_OUTER_LEFT_SLEEVE_ADDRESS_NOT_APPLIED")
            require(number((nodes.first {
                $0["node_id"] as? String == "inner-right-sleeve"
            }?["dimensions"] as? [String: Any])?["length_cm"]) == 52,
                    "EXPLICIT_OUTER_LEFT_ADDRESS_LEAKED_TO_OTHER_LAYER")
        } catch {
            failures.append("EXPLICIT_LAYERED_REQUIREMENT_AUDIT_FAILED_\(error)")
        }

        do {
            let numericLayers: [[String: Any]] = [
                ["node_id": "left-layer-1", "kind": "SLEEVE", "layer": 1,
                 "attributes": ["garment_unit": "look-beta",
                                "side": "left", "placement": "left arm"],
                 "dimensions": ["length_cm": 45.0]],
                ["node_id": "left-layer-2", "kind": "SLEEVE", "layer": 2,
                 "attributes": ["garment_unit": "look-beta",
                                "side": "left", "placement": "left arm"],
                 "dimensions": ["length_cm": 55.0]],
            ]
            let addressed = try sleeveProfile(target: "layer 2 sleeve length")
            let applied = try GarmentDesignRequirementProfileBridge.apply(
                addressed, to: ["structure": ["nodes": numericLayers]])
            require(applied.appliedFieldCount == 1,
                    "NUMERIC_LAYER_GRAPH_ADDRESS_DID_NOT_SELECT_ONE_NODE")
            let structure = applied.candidate["structure"] as? [String: Any] ?? [:]
            let nodes = structure["nodes"] as? [[String: Any]] ?? []
            require(number((nodes.first {
                $0["node_id"] as? String == "left-layer-1"
            }?["dimensions"] as? [String: Any])?["length_cm"]) == 45,
                    "NUMERIC_LAYER_ADDRESS_CHANGED_LAYER_1")
            require(number((nodes.first {
                $0["node_id"] as? String == "left-layer-2"
            }?["dimensions"] as? [String: Any])?["length_cm"]) == 61,
                    "NUMERIC_LAYER_ADDRESS_DID_NOT_CHANGE_LAYER_2")
        } catch {
            failures.append("NUMERIC_LAYER_REQUIREMENT_AUDIT_FAILED_\(error)")
        }

        do {
            let target = "waist"
            let requirements: [GarmentCommandIR.Requirement] = [
                .init(kind: .bodyMeasurement, target: target, text: nil,
                      value: 72, unit: .cm, note: nil),
            ]
            let prepared = try GarmentDesignRequirementProfileBridge.prepare(
                requirements: requirements)
            let profile = try GarmentDesignRequirementProfileBridge.validate(
                response: profileResponse(
                    overrides: [
                        "FLARE": ["top_circumference_cm": overrideRecord(
                            value: 72, sources: [target])],
                        "FRUSTUM": ["top_circumference_cm": overrideRecord(
                            value: 72, sources: [target])],
                        "BAND": ["length_cm": overrideRecord(
                            value: 72, sources: [target])],
                    ],
                    reviewItems: [],
                    requirements: [[
                        "kind": "BODY_MEASUREMENT", "target": target,
                        "value_cm": 72.0, "state": "REQUESTED",
                    ]]),
                prepared: prepared)
            let candidate: [String: Any] = ["structure": ["nodes": [
                ["node_id": "unjoined-skirt", "kind": "FLARE",
                 "attributes": ["placement": "lower body", "layer": "outer"],
                 "dimensions": ["top_circumference_cm": 68.0]],
                ["node_id": "unjoined-belt", "kind": "BAND",
                 "attributes": ["placement": "waist", "detail_role": "belt"],
                 "dimensions": ["length_cm": 68.0]],
            ]]]
            let applied = try GarmentDesignRequirementProfileBridge.apply(
                profile, to: candidate)
            require(applied.appliedFieldCount == 0,
                    "UNJOINED_SEAM_CIRCUMFERENCE_WAS_PARTIALLY_APPLIED")
            require(applied.applicationReviewItems.contains {
                $0["code"] as? String == "UNKNOWN_REQUIREMENT_SEAM_ADDRESS_NOT_EXACT"
            }, "UNJOINED_SEAM_EXACT_REVIEW_CODE_MISSING")
            let structure = applied.candidate["structure"] as? [String: Any] ?? [:]
            let nodes = structure["nodes"] as? [[String: Any]] ?? []
            require(nodes.allSatisfy { row in
                let dimensions = row["dimensions"] as? [String: Any]
                return number(dimensions?[row["kind"] as? String == "BAND"
                    ? "length_cm" : "top_circumference_cm"]) == 68
            }, "UNJOINED_SEAM_FAIL_CLOSED_CHANGED_A_SIDE")
        } catch {
            failures.append("UNJOINED_SEAM_ATOMIC_AUDIT_FAILED_\(error)")
        }

        return failures
    }

    private static func waistOverrides() -> [String: Any] {
        let sources = ["waist", "waist ease"]
        return [
            "BAND": ["length_cm": overrideRecord(value: 76, sources: sources)],
            "FLARE": ["top_circumference_cm": overrideRecord(
                value: 76, sources: sources)],
            "FRUSTUM": ["top_circumference_cm": overrideRecord(
                value: 76, sources: sources)],
            "TUBE": ["length_cm": overrideRecord(
                value: 78, sources: ["inseam"])],
        ]
    }

    private static func overrideRecord(
        value: Double, sources: [String]
    ) -> [String: Any] {
        [
            "value_cm": value,
            "unit": "cm",
            "state": "REQUESTED",
            "authority": "USER_EXPLICIT_REQUEST_NOT_MEASUREMENT_CERTIFICATE",
            "source_requirement_targets": sources.sorted(),
            "not_measured_from_image": true,
            "preview_only": true,
        ]
    }

    private static func profileResponse(
        overrides: [String: Any], reviewItems: [[String: Any]],
        requirements: [[String: Any]]
    ) -> [String: Any] {
        [
            "schema": GarmentDesignRequirementProfileBridge.responseSchema,
            "verdict": reviewItems.isEmpty ? "PROPOSED" : "REVIEW",
            "state": "PREVIEW_PROFILE_READY",
            "requirements": requirements,
            "primitive_overrides": overrides,
            "review_items": reviewItems,
            "claims": [
                "natural_language_parsed_here": false,
                "front_image_measured": false,
                "standard_size_expanded_without_chart": false,
                "generic_ease_auto_distributed": false,
                "user_dimension_treated_as_measured_fact": false,
            ],
            "preview_only": true,
            "manufacturing_ready": false,
            "manufacturing_certified": false,
            "profile_digest": "audit-profile-digest",
        ]
    }

    private static func number(_ value: Any?) -> Double? {
        if let value = value as? Double { return value }
        if let value = value as? NSNumber { return value.doubleValue }
        return nil
    }

    private static func canonicalJSON(_ value: Any) -> String? {
        guard JSONSerialization.isValidJSONObject(value),
              let data = try? JSONSerialization.data(
                withJSONObject: value, options: [.sortedKeys, .withoutEscapingSlashes])
        else { return nil }
        return String(data: data, encoding: .utf8)
    }
}

#if !GARMENT_DESIGN_REQUIREMENT_PROFILE_STANDALONE
final class GarmentDesignRequirementProfileBridgeAuditTests: XCTestCase {
    func testTypedRequirementsMCPValidationAndCandidateApplication() {
        XCTAssertEqual(GarmentDesignRequirementProfileBridgeAudit.failures(), [])
    }
}
#else
@main
private struct GarmentDesignRequirementProfileBridgeAuditRunner {
    static func main() {
        let failures = GarmentDesignRequirementProfileBridgeAudit.failures()
        if failures.isEmpty {
            print("PASS garment design requirement profile Swift bridge invariants")
            exit(0)
        }
        failures.forEach { print("FAIL \($0)") }
        exit(1)
    }
}
#endif
