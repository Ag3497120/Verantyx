import Foundation

#if !INITIAL_HUMAN_REVIEW_GATE_STANDALONE
import XCTest
#endif

private enum InitialHumanReviewGateAudit {
    static func failures() -> [String] {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent()
        guard let controller = try? String(
                contentsOf: root.appendingPathComponent(
                    "Sources/Verantyx/Engine/GarmentFactoryReactController.swift"),
                encoding: .utf8),
              let view = try? String(
                contentsOf: root.appendingPathComponent(
                    "Sources/Verantyx/Views/AtelierChatPaneView.swift"),
                encoding: .utf8),
              let dynamicView = try? String(
                contentsOf: root.appendingPathComponent(
                    "Sources/Verantyx/Views/AtelierDynamicFlowView.swift"),
                encoding: .utf8) else {
            return ["INITIAL_HUMAN_REVIEW_SOURCE_UNREADABLE"]
        }
        var failures: [String] = []
        require(controller.contains(
                    "visibleFrontInventoryAuditRequired") &&
                controller.contains("HUMAN_GARMENT_AUDIT_REQUIRED") &&
                controller.contains("deferForHumanAudit") &&
                controller.contains("pendingHumanAuditedVisionRows"),
                "AUTOMATIC_VISION_CAN_BYPASS_VISIBLE_GARMENT_AUDIT",
                &failures)
        require(controller.contains(
                    "visibleFrontInventoryAuditConfirmed") &&
                controller.contains("targetCleanupConfirmed") &&
                controller.contains("RECORD_AI_VISIBLE_ANALYSIS") &&
                controller.contains("SUBMIT_HUMAN_VISIBLE_AUDIT") &&
                controller.contains("SUBMIT_FOREGROUND_CLEANUP") &&
                controller.contains("activeVisibleAnalysisDigest") &&
                controller.contains("resumeAfterInitialHumanReviewIfReady"),
                "PARTS_COMPILATION_IS_NOT_GATED_BY_AUDIT_AND_CLEANUP",
                &failures)
        require(controller.contains("FRONT_FACTS_RECORDED") &&
                controller.contains("rear_hidden_observed\": false") &&
                controller.contains("material_identity_observed\": false"),
                "FRONT_REVIEW_CAN_PROMOTE_REAR_OR_MATERIAL_TO_OBSERVED",
                &failures)
        require(view.contains(
                    "atelier.beginner.confirm-visible-front-inventory") &&
                view.contains("confirmVisibleFrontInventoryAudit") &&
                view.contains("GarmentRegionPickerView") &&
                view.contains("allowsAutomaticProposalConfirmation: false") &&
                view.contains("confirmedOutline: outline") &&
                view.contains("if !factory.visibleFrontInventory.isEmpty") &&
                view.contains("factoryVisibleFrontInventoryCard") &&
                dynamicView.contains(
                    "atelier.beginner.confirm-visible-front-inventory") &&
                dynamicView.contains("confirmVisibleFrontInventoryAudit") &&
                dynamicView.contains("GarmentRegionPickerView") &&
                dynamicView.contains(
                    "allowsAutomaticProposalConfirmation: false") &&
                dynamicView.contains("confirmedOutline: outline") &&
                dynamicView.contains("visibleFrontInventoryAuditCard"),
                "BEGINNER_UI_HAS_NO_VISIBLE_GARMENT_AUDIT_ACTION",
                &failures)
        require(controller.contains("humanConfirmedFrontEvidence") &&
                controller.contains("three_to_five_human_seeds") &&
                controller.contains("HUMAN_CONFIRMED_REGION_SELECTION") &&
                controller.contains("humanConfirmed: true"),
                "HUMAN_REGION_PICKER_DOES_NOT_OPEN_CONFIRMED_GEOMETRY_PATH",
                &failures)
        require(controller.contains("garment_target_sculpt_modifier") &&
                controller.contains("applyTargetSculptModifier") &&
                view.contains("case pull") &&
                view.contains("case stretch") &&
                view.contains("onModifierDrag") &&
                view.contains("polygonPoints") &&
                dynamicView.contains("輪郭点をドラッグ") &&
                dynamicView.contains("外側を一周クリック") &&
                dynamicView.contains("WIND_PREVIEW") &&
                dynamicView.contains("形状Undo"),
                "BEGINNER_CAD_HAS_NO_TYPED_PULL_STRETCH_WIND_PATH",
                &failures)
        return failures
    }

    static func behaviorFailures() -> [String] {
        let imagePath = "/tmp/photoloset-human-front.png"
        var failures: [String] = []

        func evaluate(_ outline: [String: Any], activePath: String? = nil)
            -> HumanConfirmedFrontEvidenceGate.Evidence? {
            HumanConfirmedFrontEvidenceGate.humanConfirmedFrontEvidence(
                outline,
                activeImagePath: activePath ?? imagePath,
                submittedImagePath: imagePath)
        }

        let valid = confirmedOutline(seedCount: 3)
        if let evidence = evaluate(valid) {
            require(evidence.regions.count == 1 && evidence.seeds.count == 3,
                    "VALID_HUMAN_CONFIRMED_FRONT_WAS_CHANGED",
                    &failures)
        } else {
            failures.append("VALID_HUMAN_CONFIRMED_FRONT_WAS_REFUSED")
        }

        require(evaluate(confirmedOutline(seedCount: 2)) == nil,
                "TWO_HUMAN_SEEDS_OPENED_THE_GATE", &failures)
        require(evaluate(confirmedOutline(seedCount: 6)) == nil,
                "SIX_HUMAN_SEEDS_OPENED_THE_GATE", &failures)

        var proposedProvenance = valid
        var provenance = proposedProvenance["provenance"] as! [String: Any]
        provenance["kind"] = "PROPOSED"
        proposedProvenance["provenance"] = provenance
        require(evaluate(proposedProvenance) == nil,
                "PROPOSED_PROVENANCE_OPENED_THE_GATE", &failures)

        var proposedSeed = valid
        provenance = proposedSeed["provenance"] as! [String: Any]
        var seeds = provenance["human_seeds"] as! [[String: Any]]
        seeds[0]["kind"] = "PROPOSED"
        provenance["human_seeds"] = seeds
        proposedSeed["provenance"] = provenance
        require(evaluate(proposedSeed) == nil,
                "PROPOSED_SEED_OPENED_THE_GATE", &failures)

        var noClothingLabel = valid
        provenance = noClothingLabel["provenance"] as! [String: Any]
        seeds = provenance["human_seeds"] as! [[String: Any]]
        for index in seeds.indices { seeds[index]["label"] = "skin" }
        provenance["human_seeds"] = seeds
        noClothingLabel["provenance"] = provenance
        require(evaluate(noClothingLabel) == nil,
                "NO_CLOTHING_LABEL_OPENED_THE_GATE", &failures)

        var proposedRegion = valid
        var regions = proposedRegion["regions"] as! [[String: Any]]
        regions[0]["state"] = "PROPOSED"
        proposedRegion["regions"] = regions
        require(evaluate(proposedRegion) == nil,
                "PROPOSED_REGION_OPENED_THE_GATE", &failures)

        require(evaluate(valid, activePath: "/tmp/a-different-image.png") == nil,
                "MISMATCHED_IMAGE_PATH_OPENED_THE_GATE", &failures)

        let multiple = confirmedMultiRegionOutline(includeRelation: true)
        if let evidence = evaluate(multiple) {
            require(evidence.regions.count == 2
                    && evidence.layerRelations.count == 1,
                    "VALID_HUMAN_MULTI_REGION_RELATION_WAS_CHANGED",
                    &failures)
            require(evidence.layerRelations.first?["source"] as? String
                    == "HUMAN_EXPLICIT_FRONT_ORDER",
                    "HUMAN_LAYER_RELATION_LOST_EXPLICIT_SOURCE",
                    &failures)
        } else {
            failures.append("VALID_HUMAN_MULTI_REGION_RELATION_WAS_REFUSED")
        }

        if let evidence = evaluate(
            confirmedMultiRegionOutline(includeRelation: false)) {
            require(evidence.regions.count == 2
                    && evidence.layerRelations.isEmpty,
                    "MULTI_REGION_WITHOUT_ORDER_INVENTED_A_RELATION",
                    &failures)
        } else {
            failures.append("MULTI_REGION_WITHOUT_ORDER_WAS_REFUSED")
        }

        var proposedRelation = multiple
        var relations = proposedRelation["human_layer_relations"]
            as! [[String: Any]]
        relations[0]["state"] = "PROPOSED"
        proposedRelation["human_layer_relations"] = relations
        require(evaluate(proposedRelation) == nil,
                "PROPOSED_LAYER_RELATION_OPENED_THE_GATE", &failures)

        var unknownEndpoint = multiple
        relations = unknownEndpoint["human_layer_relations"]
            as! [[String: Any]]
        relations[0]["front_region_id"] = "region-missing"
        unknownEndpoint["human_layer_relations"] = relations
        require(evaluate(unknownEndpoint) == nil,
                "UNKNOWN_LAYER_ENDPOINT_OPENED_THE_GATE", &failures)

        var cyclic = multiple
        relations = cyclic["human_layer_relations"] as! [[String: Any]]
        relations.append([
            "relation_id": "human-layer:region-front->region-behind",
            "kind": "LAYER",
            "behind_region_id": "region-front",
            "front_region_id": "region-behind",
            "state": "OBSERVED",
            "source": "HUMAN_EXPLICIT_FRONT_ORDER",
        ])
        cyclic["human_layer_relations"] = relations
        require(evaluate(cyclic) == nil,
                "CYCLIC_HUMAN_LAYER_RELATION_OPENED_THE_GATE", &failures)
        return failures
    }

    private static func confirmedOutline(seedCount: Int) -> [String: Any] {
        let seeds: [[String: Any]] = (0..<seedCount).map { index in
            [
                "id": "human-seed-\(index)",
                "kind": "OBSERVED",
                "label": index == 0 ? "clothing" : "skin",
                "point": [Double(index), Double(index)],
            ]
        }
        return [
            "outline": [[0.0, 0.0], [10.0, 0.0], [5.0, 12.0]],
            "regions": [[
                "region_id": "human-clothing-region",
                "state": "OBSERVED",
                "semantic_label": "clothing",
            ]],
            "provenance": [
                "kind": "OBSERVED",
                "human_seeds": seeds,
            ],
        ]
    }

    private static func confirmedMultiRegionOutline(
        includeRelation: Bool
    ) -> [String: Any] {
        var result = confirmedOutline(seedCount: 3)
        result["regions"] = [
            [
                "region_id": "region-behind",
                "part_id": "human-part:region-behind",
                "state": "OBSERVED",
                "semantic_label": "clothing",
                "outline": [[0.0, 0.0], [8.0, 0.0], [8.0, 8.0], [0.0, 8.0]],
                "layer": 0,
            ],
            [
                "region_id": "region-front",
                "part_id": "human-part:region-front",
                "state": "OBSERVED",
                "semantic_label": "clothing",
                "outline": [[2.0, 2.0], [7.0, 2.0], [7.0, 7.0], [2.0, 7.0]],
                "layer": 1,
            ],
        ]
        result["human_layer_relations"] = includeRelation ? [[
            "relation_id": "human-layer:region-behind->region-front",
            "kind": "LAYER",
            "behind_region_id": "region-behind",
            "front_region_id": "region-front",
            "state": "OBSERVED",
            "source": "HUMAN_EXPLICIT_FRONT_ORDER",
        ]] : []
        return result
    }

    private static func require(_ condition: @autoclosure () -> Bool,
                                _ code: String,
                                _ failures: inout [String]) {
        if !condition() { failures.append(code) }
    }
}

#if !INITIAL_HUMAN_REVIEW_GATE_STANDALONE
final class InitialHumanReviewGateAuditTests: XCTestCase {
    func testAutomaticImageAnalysisWaitsForHumanAuditAndCleanup() {
        XCTAssertEqual(InitialHumanReviewGateAudit.failures(), [])
    }

    func testOnlySameImageObservedThreeToFiveSeedEvidenceOpensGate() {
        XCTAssertEqual(InitialHumanReviewGateAudit.behaviorFailures(), [])
    }
}
#else
@main
private enum InitialHumanReviewGateAuditMain {
    static func main() {
        let failures = InitialHumanReviewGateAudit.failures()
            + InitialHumanReviewGateAudit.behaviorFailures()
        if failures.isEmpty { print("PASS initial human review gate audit") }
        else { failures.forEach { print("FAIL \($0)") }; exit(1) }
    }
}
#endif
