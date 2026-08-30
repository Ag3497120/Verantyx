import Foundation

#if !BACK_3D_CONTINUATION_CAD_STANDALONE
import XCTest
#endif

/// Source-level regression for the beginner route which previously restarted
/// image intake when the user asked for the hidden rear, and for the CAD view
/// which previously trapped ordinary page scrolling behind a body proxy.
private enum Back3DContinuationAndCADInteractionAudit {
    static func failures() -> [String] {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let files = [
            "planner": "Sources/Verantyx/Engine/AtelierGarmentRequestPlanner.swift",
            "router": "Sources/Verantyx/Engine/AtelierChatRouter.swift",
            "controller": "Sources/Verantyx/Engine/GarmentFactoryReactController.swift",
            "scene": "Sources/Verantyx/Views/AtelierChatPaneView.swift",
            "flow": "Sources/Verantyx/Views/AtelierDynamicFlowView.swift",
        ]
        var source: [String: String] = [:]
        for (key, path) in files {
            guard let text = try? String(
                contentsOf: root.appendingPathComponent(path), encoding: .utf8)
            else { return ["BACK_3D_CAD_SOURCE_UNREADABLE_\(key.uppercased())"] }
            source[key] = text
        }
        let planner = source["planner"] ?? ""
        let router = source["router"] ?? ""
        let controller = source["controller"] ?? ""
        let scene = source["scene"] ?? ""
        let flow = source["flow"] ?? ""
        var failures: [String] = []
        func require(_ condition: @autoclosure () -> Bool, _ code: String) {
            if !condition() { failures.append(code) }
        }

        require(planner.contains("case \"INSPECT_BACK_3D\"") &&
                planner.contains("REQUEST_BACK_3D") &&
                planner.contains("must not restart image intake"),
                "MODEL_HAS_NO_TYPED_REAR_CONTINUATION_ACTION")
        let rearRoute = router.range(of: "requestBack3DPreview(")?.lowerBound
        let imageRoute = router.range(of: "if command.intent == .generateFromImage")?.lowerBound
        require(rearRoute != nil && imageRoute != nil && rearRoute! < imageRoute!,
                "REAR_REQUEST_CAN_RESTART_IMAGE_INTAKE")

        require(controller.contains("@Published private(set) var pendingBack3DRequest") &&
                controller.contains("fulfillPendingBack3DRequestIfPossible") &&
                controller.contains("HUMAN_GARMENT_AUDIT_REQUIRED") &&
                controller.contains("FOREGROUND_CLEANUP_REQUIRED"),
                "REAR_REQUEST_IS_NOT_DURABLE_ACROSS_HUMAN_GATES")
        let boundPreview = controller.range(
            of: "publishTargetBoundBackPreview(candidate: candidate")?.lowerBound
        let genericPreview = controller.range(
            of: "toolDoor(\"garment_structure_preview\"")?.lowerBound
        require(boundPreview != nil && genericPreview != nil &&
                boundPreview! < genericPreview!,
                "GENERIC_CAPE_PREVIEW_PRECEDES_ADOPTED_FRONT")
        require(controller.contains("PROPOSED_TARGET_BOUND_REAR_PREVIEW") &&
                controller.contains("\"front_fixed\": true") &&
                controller.contains("\"rear_observed\": false") &&
                controller.contains("manufacturing_certified\": false"),
                "INFERRED_REAR_CAN_ESCAPE_PROPOSED_AUTHORITY")
        require(controller.contains("garment_target_bound_candidate_preview") &&
                controller.contains("\"candidate_preview\": structurePreview") &&
                controller.contains("garmentComponentSurface") &&
                controller.contains("face_component_ids"),
                "ADOPTED_FRONT_IS_NOT_BOUND_TO_TYPED_CANDIDATE_GEOMETRY")
        require(!controller.contains("depthVariant = 0.92") &&
                !controller.contains("widthVariant = 0.985"),
                "CANDIDATE_ID_HASH_STILL_CONTROLS_REAR_GEOMETRY")

        require(scene.contains("SCNHitTestSearchMode.all") &&
                scene.contains("material.writesToDepthBuffer = false") &&
                scene.contains("renderingOrder = -20"),
                "BODY_PROXY_CAN_BLOCK_OR_HIDE_GARMENT_EDITING")
        require(scene.contains("override func scrollWheel") &&
                scene.contains("modifierFlags.contains(.option)") &&
                scene.contains("nextResponder.scrollWheel") &&
                scene.contains("override func magnify"),
                "CAD_CANVAS_CAN_TRAP_ORDINARY_PAGE_SCROLL")
        require(scene.contains("addPolygonPoint") &&
                scene.contains("commitPolygon") &&
                scene.contains("visibleEditableFace") &&
                !scene.contains("brushRings") &&
                flow.contains("外側を一周クリック"),
                "CAD_ERASER_IS_NOT_EXPLICIT_CLOSED_POLYGON")
        require(scene.contains("refreshBoundaryAnchors") &&
                scene.contains("faceComponentIDs") &&
                scene.contains("localDragVectorCM") &&
                flow.contains("onModifierDrag") &&
                controller.contains("vertexIndices requestedVertexIndices"),
                "CAD_PULL_STRETCH_IS_NOT_COMPONENT_POINT_DRIVEN")
        require(flow.contains("ViewThatFits(in: .horizontal)") &&
                flow.contains("Color.clear") &&
                flow.contains(".aspectRatio(16.0 / 9.0") &&
                flow.contains(".frame(maxWidth: .infinity, maxHeight: .infinity)") &&
                scene.contains("private var polygonAnchors: [SCNVector3]") &&
                scene.contains("refreshPolygonOverlay()") &&
                !flow.contains("targetSculptBrushRings") &&
                !flow.contains("maxHeight: 520") &&
                !flow.contains(".frame(maxWidth: 880)"),
                "INLINE_CAD_DOES_NOT_REFLOW_WITH_WINDOW")

        let auditCard = flow.range(of: "visibleFrontInventoryAuditCard")?.lowerBound
        let targetCard = flow.range(of: "targetReconstructionCard(target)")?.lowerBound
        require(auditCard != nil && targetCard != nil && auditCard! < targetCard!,
                "LARGE_CAD_CARD_PRECEDES_VISIBLE_PARTS_AUDIT")
        require(flow.contains("pendingBack3DRequest"),
                "BEGINNER_UI_HIDES_QUEUED_REAR_REQUEST")
        return failures
    }
}

#if !BACK_3D_CONTINUATION_CAD_STANDALONE
final class Back3DContinuationAndCADInteractionAuditTests: XCTestCase {
    func testRearContinuationAndCADInteractionContracts() {
        XCTAssertEqual(Back3DContinuationAndCADInteractionAudit.failures(), [])
    }
}
#else
@main
private enum Back3DContinuationAndCADInteractionAuditMain {
    static func main() {
        let failures = Back3DContinuationAndCADInteractionAudit.failures()
        if failures.isEmpty {
            print("PASS rear-3D continuation and CAD interaction invariants")
            exit(0)
        }
        failures.forEach { print("FAIL \($0)") }
        exit(1)
    }
}
#endif
