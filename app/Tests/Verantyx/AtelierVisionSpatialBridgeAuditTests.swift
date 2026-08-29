import Foundation

#if !ATELIER_VISION_SPATIAL_BRIDGE_STANDALONE
import XCTest
@testable import Verantyx
#endif

/// Router-boundary regression for:
/// RegionPicker geometry + model-proposed visible semantics -> front spatial
/// proposals.  The executable standalone half audits the wiring even on local
/// checkouts without an app test target; the XCTest half exercises the actual
/// production bridge when the Verantyx module test target is available.
private enum AtelierVisionSpatialBridgeAudit {
    static let layeredFixture = #"""
    model preface
    {"candidates":[{"candidate_id":"layered-visible-front",
      "back_design":"OBSERVED center-back zipper",
      "rear_observed":true,"manufacturing_ready":true,
      "assumptions":["model claimed a hidden rear"],"parts":[
       {"part_id":"ivory-blouse","kind":"BODY_SHELL","layer":0,
        "semantic_role":"ivory blouse","visible_color":"ivory",
        "placement":"front upper torso","garment_unit":"blouse",
        "visible_basis":"ivory torso and sleeves are visible","dimensions":{}},
       {"part_id":"navy-vest","kind":"BODY_SHELL","layer":1,
        "semantic_role":"cropped navy vest","visible_color":"navy",
        "placement":"front upper torso","garment_unit":"vest",
        "visible_basis":"dark cropped lapel shell is visible","dimensions":{}},
       {"part_id":"red-trouser-left","kind":"TUBE","layer":0,
        "semantic_role":"left trouser leg","visible_color":"red",
        "placement":"left lower body","side":"left",
        "garment_unit":"trousers","visible_basis":"left red leg","dimensions":{}},
       {"part_id":"red-trouser-right","kind":"TUBE","layer":0,
        "semantic_role":"right trouser leg","visible_color":"red",
        "placement":"right lower body","side":"right",
        "garment_unit":"trousers","visible_basis":"right red leg","dimensions":{}},
       {"part_id":"teal-overlay","kind":"OVERLAY","layer":2,
        "semantic_role":"right translucent overskirt overlay",
        "visible_color":"translucent teal","placement":"right waist to hem",
        "side":"right","garment_unit":"overlay-wrap",
        "visible_basis":"teal layer leaves red trousers visible","dimensions":{}}
      ]}]}
    trailing prose
    """#

    static let outline: [String: Any] = [
        "width_px": 100, "height_px": 200,
        "regions": [
            region("region-white", state: "OBSERVED", x: 25, y: 25,
                   width: 50, height: 70, rgb: (242, 238, 220)),
            region("region-navy", x: 28, y: 35,
                   width: 44, height: 35, rgb: (20, 29, 55)),
            region("region-red-left", x: 24, y: 94,
                   width: 25, height: 100, rgb: (163, 48, 35)),
            region("region-red-right", x: 51, y: 94,
                   width: 25, height: 100, rgb: (161, 45, 33)),
            region("region-teal", x: 51, y: 84,
                   width: 39, height: 96, rgb: (18, 118, 126)),
        ],
    ]

    private static func region(
        _ id: String, state: String = "PROPOSED", x: Int, y: Int,
        width: Int, height: Int, rgb: (Int, Int, Int)
    ) -> [String: Any] {
        [
            "region_id": id, "state": state,
            "bounding_box": ["x": x, "y": y, "width": width, "height": height],
            "average_rgba": ["red": rgb.0, "green": rgb.1,
                             "blue": rgb.2, "alpha": 255],
        ]
    }

    static func sourceFailures() -> [String] {
        let file = URL(fileURLWithPath: #filePath)
        let appRoot = file.deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        let routerURL = appRoot.appendingPathComponent(
            "Sources/Verantyx/Engine/AtelierChatRouter.swift")
        guard let source = try? String(contentsOf: routerURL, encoding: .utf8) else {
            return ["VISION_SPATIAL_ROUTER_SOURCE_UNREADABLE"]
        }
        var failures: [String] = []
        func require(_ condition: Bool, _ code: String) {
            if !condition { failures.append(code) }
        }
        require(source.contains("bridgeVisionVisibleParts") &&
                source.contains("prepareVisionSpatialInput"),
                "REGIONPICKER_TO_VISION_SPATIAL_BRIDGE_NOT_WIRED")
        require(source.contains("visionSpatialCandidateLimit = 1") &&
                source.contains("visionSpatialPartLimit = 24") &&
                source.contains("visionSpatialRegionLimit = 32") &&
                source.contains("visionSpatialMinimumMatchScore"),
                "VISION_SPATIAL_BRIDGE_IS_UNBOUNDED")
        require(source.contains("garment.front-spatial-proposal.v1") &&
                source.contains("REGIONPICKER_COMPONENT_X_TYPED_FRONT_ZONE") &&
                source.contains("TYPED_FRONT_ZONE_PRIOR_NO_REGION_MATCH"),
                "SPATIAL_PROPOSAL_HAS_NO_TYPED_DETERMINISTIC_PROVENANCE")
        require(source.contains("semantic_assignment_state\"] = \"PROPOSED\"") &&
                source.contains("Deliberately leave rows[rowIndex][\"state\"] untouched"),
                "REGION_AUTHORITY_CAN_BE_OVERWRITTEN_BY_MODEL_SEMANTICS")
        require(source.contains("rear_authority\"] = \"UNKNOWN_UNOBSERVED\"") &&
                source.contains("candidate[\"rear_observed\"] = false") &&
                source.contains("dimensions_inferred_from_pixels\": false"),
                "HIDDEN_REAR_OR_PIXEL_MEASUREMENT_CAN_ESCAPE_THE_BRIDGE")
        require(source.contains("left trouser leg") &&
                source.contains("right trouser leg") &&
                source.contains("separate OVERLAY"),
                "LAYERED_SEPARATES_PROMPT_CONTRACT_IS_MISSING")
        let calls = source.components(separatedBy: "prepareVisionSpatialInput(").count - 1
        require(calls >= 3,
                "AUTOMATIC_AND_CONFIRMED_FACTORY_ROUTES_DO_NOT_SHARE_THE_BRIDGE")
        return failures
    }

#if !ATELIER_VISION_SPATIAL_BRIDGE_STANDALONE
    @MainActor
    static func runtimeFailures() -> [String] {
        guard let output = AtelierChatRouter.bridgeVisionVisibleParts(
                layeredFixture, outline: outline),
              let data = output.response.data(using: .utf8),
              let object = try? JSONSerialization.jsonObject(with: data)
                as? [String: Any],
              let candidate = (object["candidates"] as? [[String: Any]])?.first,
              let parts = candidate["parts"] as? [[String: Any]],
              let proposals = output.outline["front_spatial_proposals"]
                as? [[String: Any]] else {
            return ["LAYERED_FIXTURE_DID_NOT_BRIDGE"]
        }
        var failures: [String] = []
        func require(_ condition: @autoclosure () -> Bool, _ code: String) {
            if !condition() { failures.append(code) }
        }
        require(parts.count == 5 && proposals.count == 5,
                "VISIBLE_PART_CARDINALITY_CHANGED")
        require(candidate["rear_observed"] as? Bool == false &&
                candidate["rear_authority"] as? String == "UNKNOWN_UNOBSERVED" &&
                (candidate["back_design"] as? String)?.contains("rear not visible") == true,
                "MODEL_REAR_CLAIM_WAS_NOT_DOWNGRADED")
        let byID = Dictionary(uniqueKeysWithValues: proposals.compactMap { row in
            guard let id = row["part_id"] as? String else { return nil }
            return (id, row)
        })
        let left = byID["red-trouser-left"]?["source_region_ids"] as? [String]
        let right = byID["red-trouser-right"]?["source_region_ids"] as? [String]
        let overlay = byID["teal-overlay"]?["source_region_ids"] as? [String]
        require(left == ["region-red-left"] && right == ["region-red-right"] &&
                left != right, "TROUSER_LEGS_DID_NOT_BIND_TO_DISTINCT_REGIONS")
        require(overlay == ["region-teal"],
                "ASYMMETRIC_OVERLAY_DID_NOT_BIND_TO_TEAL_REGION")
        require(proposals.allSatisfy {
            $0["state"] as? String == "PROPOSED" &&
            $0["front_only"] as? Bool == true &&
            $0["rear_observed"] as? Bool == false &&
            $0["dimensions_inferred_from_pixels"] as? Bool == false
        }, "SPATIAL_PROPOSAL_AUTHORITY_ESCAPED")
        let enrichedRows = output.outline["regions"] as? [[String: Any]] ?? []
        let observed = enrichedRows.first { $0["region_id"] as? String == "region-white" }
        require(observed?["state"] as? String == "OBSERVED" &&
                observed?["semantic_assignment_state"] as? String == "PROPOSED",
                "OBSERVED_PIXEL_AUTHORITY_WAS_CONFUSED_WITH_PROPOSED_SEMANTICS")
        return failures
    }
#endif
}

#if !ATELIER_VISION_SPATIAL_BRIDGE_STANDALONE
final class AtelierVisionSpatialBridgeAuditTests: XCTestCase {
    func testRouterSourceKeepsBridgeBoundedAndFrontOnly() {
        XCTAssertEqual(AtelierVisionSpatialBridgeAudit.sourceFailures(), [])
    }

    @MainActor
    func testLayeredSeparatesBindToDistinctFrontRegions() {
        XCTAssertEqual(AtelierVisionSpatialBridgeAudit.runtimeFailures(), [])
    }
}
#else
@main
private struct AtelierVisionSpatialBridgeAuditRunner {
    static func main() {
        let failures = AtelierVisionSpatialBridgeAudit.sourceFailures()
        if failures.isEmpty {
            print("PASS Atelier RegionPicker -> Vision visible-parts spatial bridge invariants")
            exit(0)
        }
        failures.forEach { print("FAIL \($0)") }
        exit(1)
    }
}
#endif
