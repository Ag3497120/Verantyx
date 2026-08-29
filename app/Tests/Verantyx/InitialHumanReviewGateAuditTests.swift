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
                view.contains("if !factory.visibleFrontInventory.isEmpty") &&
                view.contains("factoryVisibleFrontInventoryCard") &&
                dynamicView.contains(
                    "atelier.beginner.confirm-visible-front-inventory") &&
                dynamicView.contains("confirmVisibleFrontInventoryAudit") &&
                dynamicView.contains("visibleFrontInventoryAuditCard"),
                "BEGINNER_UI_HAS_NO_VISIBLE_GARMENT_AUDIT_ACTION",
                &failures)
        require(controller.contains("garment_target_sculpt_modifier") &&
                controller.contains("applyTargetSculptModifier") &&
                dynamicView.contains("引っ張る") &&
                dynamicView.contains("縦に伸ばす") &&
                dynamicView.contains("WIND_PREVIEW") &&
                dynamicView.contains("形状Undo"),
                "BEGINNER_CAD_HAS_NO_TYPED_PULL_STRETCH_WIND_PATH",
                &failures)
        return failures
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
}
#else
@main
private enum InitialHumanReviewGateAuditMain {
    static func main() {
        let failures = InitialHumanReviewGateAudit.failures()
        if failures.isEmpty { print("PASS initial human review gate audit") }
        else { failures.forEach { print("FAIL \($0)") }; exit(1) }
    }
}
#endif
