import Foundation

#if !REALISTIC_CANDIDATE_DRESS_FORM_STANDALONE
import XCTest
@testable import Verantyx
#endif

/// Source-level regression audit for the beginner candidate dress-form view.
///
/// The app test target is not available in every local build, so this audit is
/// also executable with `REALISTIC_CANDIDATE_DRESS_FORM_STANDALONE`.  It checks
/// the presentation contract without promoting a rendered proxy to physical or
/// measurement evidence.
private enum RealisticCandidateDressFormAudit {
    static func failures() -> [String] {
        let file = URL(fileURLWithPath: #filePath)
        let sourceURL = file.deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Sources/Verantyx/Views/AtelierChatPaneView.swift")
        guard let source = try? String(contentsOf: sourceURL, encoding: .utf8)
        else { return ["ATELIER_CHAT_PANE_UNREADABLE"] }
        var failures: [String] = []

        require(source.contains("struct DressFormFrame") &&
                source.contains("struct ProfileRing") &&
                source.contains("radialProfileGeometry") &&
                source.contains("limbSegment(name:"),
                "DRESS_FORM_IS_NOT_PROCEDURAL_PROFILE_GEOMETRY", &failures)
        for anatomicalPart in [
            "head", "neck", "torso", "left-upper-arm", "right-upper-arm",
            "left-forearm", "right-forearm", "left-thigh", "right-thigh",
            "left-calf", "right-calf", "left-hand", "right-hand",
            "left-foot", "right-foot",
        ] {
            require(source.contains("\"\(anatomicalPart)\""),
                    "MISSING_PROPORTIONED_PART_\(anatomicalPart)", &failures)
        }
        require(source.contains("FactoryGarmentLayerDescriptor.parse") &&
                source.contains("source_node_id") &&
                source.contains("piece_id") && source.contains("layer") &&
                source.contains("bindProposalIdentity") &&
                source.contains("PROPOSED_TYPED_PROXY"),
                "CANDIDATE_NODE_OR_LAYER_IDENTITY_WAS_FLATTENED", &failures)
        require(source.contains("garmentProxyNodes(for:") &&
                source.contains("garment-sleeve-upper") &&
                source.contains("garment-trouser-upper") &&
                source.contains("garment-flared-lower") &&
                source.contains("garment-cape-overlay") &&
                source.contains("garment-ruffle-surface"),
                "CANDIDATE_LAYERS_HAVE_NO_GENERIC_GARMENT_GEOMETRY", &failures)
        require(source.contains("let preservesSourceFront: Bool") &&
                source.contains("if !preservesSourceFront") &&
                source.contains("artifact.preservesSourceFront"),
                "GENERIC_PROXY_CAN_HIDE_IMAGE_SPECIFIC_FRONT", &failures)
        require(source.contains("sideDrapedPanelNode") &&
                source.contains("garment-side-specific-proposed-pleated-panel-left") &&
                source.contains("garment-side-specific-proposed-pleated-panel-right") &&
                source.contains("ownsOneSide && isSidePanel"),
                "SIDE_SPECIFIC_GORE_OR_OVERSKIRT_WAS_MIRRORED", &failures)
        require(source.contains("candidate-three-quarter-camera") &&
                source.contains("addStudioFloor") &&
                source.contains("castsShadow = true") &&
                source.contains("lightingModel = .physicallyBased"),
                "REALISTIC_STUDIO_PRESENTATION_MISSING", &failures)
        require(source.contains("robustProposalBounds") &&
                source.contains("let lower = 0.03") &&
                source.contains("let upper = 0.97") &&
                source.contains("frameCameraAndLights(scene: scene, frame: frame)") &&
                source.contains("frameHeight * 1.045"),
                "CAMERA_STILL_FRAMES_DISTANT_REPAIR_OUTLIERS", &failures)
        require(source.contains("UNKNOWN BACK / NOT A MEASURED WEARER") &&
                source.contains("no displayed fold is faithful physical drape") &&
                source.contains("PROPOSED_NOT_OBSERVED_FROM_FRONT") &&
                source.contains("UNKNOWN_NOT_MEASURED"),
                "PROPOSAL_TRUTH_BOUNDARY_MISSING", &failures)

        guard let sceneStart = source.range(of: "struct FactoryProposedDressedSceneView"),
              let patternStart = source.range(of: "struct FactoryFlatPatternPreview")
        else {
            failures.append("DRESS_FORM_SECTION_UNBOUNDED")
            return failures
        }
        let sceneSection = String(source[sceneStart.lowerBound..<patternStart.lowerBound])
        for forbidden in ["lastPathComponent", "imagePath", "emerald", "anime-garment",
                          "layered-separates"] {
            require(!sceneSection.contains(forbidden),
                    "IMAGE_NAME_SPECIFIC_3D_BRANCH_\(forbidden)", &failures)
        }
        return failures
    }

    private static func require(_ condition: @autoclosure () -> Bool,
                                _ code: String, _ failures: inout [String]) {
        if !condition() { failures.append(code) }
    }
}

#if !REALISTIC_CANDIDATE_DRESS_FORM_STANDALONE
final class RealisticCandidateDressFormAuditTests: XCTestCase {
    func testCandidatePreviewUsesProportionedTruthBoundedDressForm() {
        XCTAssertEqual(RealisticCandidateDressFormAudit.failures(), [])
    }
}
#else
@main
private enum RealisticCandidateDressFormAuditMain {
    static func main() {
        let failures = RealisticCandidateDressFormAudit.failures()
        if failures.isEmpty { print("PASS realistic candidate dress form audit") }
        else { failures.forEach { print("FAIL \($0)") }; exit(1) }
    }
}
#endif
