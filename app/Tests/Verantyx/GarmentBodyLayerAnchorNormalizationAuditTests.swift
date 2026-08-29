import Foundation
import XCTest
@testable import Verantyx

final class GarmentBodyLayerAnchorNormalizationAuditTests: XCTestCase {
    @MainActor
    func testSameUnitLayeredBodyIsReaddressedOnlyToUniqueLowerBody() throws {
        let raw = #"""
        {"candidates":[{"candidate_id":"layered-body",
          "back_design":"rear not visible","parts":[
            {"part_id":"inner-body","kind":"BODY_SHELL","layer":0,
             "garment_unit":"look","dimensions":{"height_cm":42,"circumference_cm":92}},
            {"part_id":"inner-sleeve","kind":"SLEEVE","layer":1,
             "garment_unit":"look","attached_to":"inner-body",
             "dimensions":{"length_cm":58,"upper_circumference_cm":34,"cuff_circumference_cm":20}},
            {"part_id":"outer-body","kind":"BODY_SHELL","layer":2,
             "garment_unit":"look","attached_to":"inner-sleeve",
             "dimensions":{"height_cm":38,"circumference_cm":98}}
          ]}]}
        """#
        let nodes = try XCTUnwrap(structureNodes(raw))
        let outer = try XCTUnwrap(nodes.first {
            $0["node_id"] as? String == "outer-body"
        })
        let attributes = try XCTUnwrap(outer["attributes"] as? [String: Any])
        XCTAssertEqual(attributes["attached_to"] as? String, "inner-body")
        XCTAssertEqual(attributes["model_attached_to"] as? String, "inner-sleeve")
        let normalization = try XCTUnwrap(
            attributes["body_layer_anchor_normalization"] as? [String: Any])
        XCTAssertEqual(normalization["state"] as? String,
                       "PROPOSED_NORMALIZATION")
        XCTAssertEqual(normalization["sewn_join_observed"] as? Bool, false)
    }

    @MainActor
    func testCrossUnitOuterBodyBecomesIndependentProposedRoot() throws {
        let raw = #"""
        {"candidates":[{"candidate_id":"separate-vest",
          "back_design":"rear not visible","parts":[
            {"part_id":"blouse-body","kind":"BODY_SHELL","layer":0,
             "garment_unit":"blouse","dimensions":{"height_cm":45,"circumference_cm":92}},
            {"part_id":"blouse-sleeve","kind":"SLEEVE","layer":1,
             "garment_unit":"blouse","attached_to":"blouse-body",
             "dimensions":{"length_cm":58,"upper_circumference_cm":34,"cuff_circumference_cm":20}},
            {"part_id":"vest-body","kind":"BODY_SHELL","layer":2,
             "garment_unit":"vest","attached_to":"blouse-sleeve",
             "dimensions":{"height_cm":34,"circumference_cm":98}}
          ]}]}
        """#
        let nodes = try XCTUnwrap(structureNodes(raw))
        let vest = try XCTUnwrap(nodes.first {
            $0["node_id"] as? String == "vest-body"
        })
        let attributes = try XCTUnwrap(vest["attributes"] as? [String: Any])
        XCTAssertNil(attributes["attached_to"])
        XCTAssertEqual(attributes["model_attached_to"] as? String,
                       "blouse-sleeve")
        XCTAssertEqual(attributes["attachment_state"] as? String,
                       "PROPOSED_SEPARATE_BODY_SHELL_ROOT")
        let normalization = try XCTUnwrap(
            attributes["body_layer_anchor_normalization"] as? [String: Any])
        XCTAssertEqual(normalization["sewn_join_created"] as? Bool, false)
    }

    @MainActor
    private func structureNodes(_ raw: String) -> [[String: Any]]? {
        guard let parsed = GarmentFactoryReactController.parseVisionProposal(raw),
              let hypotheses = parsed["hypotheses"] as? [[String: Any]],
              let structure = hypotheses.first?["structure"] as? [String: Any]
        else { return nil }
        return structure["nodes"] as? [[String: Any]]
    }
}
