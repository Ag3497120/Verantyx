import Foundation

#if !IMAGE_RELATIVE_AVATAR_FIT_STANDALONE
import XCTest
@testable import Verantyx
#endif

private enum ImageRelativeAvatarPreviewFitAudit {
    static func failures() -> [String] {
        let file = URL(fileURLWithPath: #filePath)
        let sourceURL = file.deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Sources/Verantyx/Views/AtelierChatPaneView.swift")
        guard let source = try? String(contentsOf: sourceURL, encoding: .utf8)
        else { return ["IMAGE_RELATIVE_FIT_SOURCE_UNREADABLE"] }
        let engineURL = file.deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent(
                "Sources/Verantyx/Engine/GarmentFactoryReactController.swift")
        guard let engineSource = try? String(
                contentsOf: engineURL, encoding: .utf8) else {
            return ["BASE_AVATAR_PROFILE_SOURCE_UNREADABLE"]
        }
        var failures: [String] = []

        require(source.contains("proposedImageProportionFrame(") &&
                source.contains("FUSED_SUBJECT_OUTLINE_MESH_BOUNDS") &&
                source.contains("PROPOSED_IMAGE_PROPORTION_FIT"),
                "FUSED_TARGET_DOES_NOT_USE_TYPED_IMAGE_PROPORTION_FIT",
                &failures)
        require(source.contains("let floor = Float(minimum.y)") &&
                source.contains("let top = Float(maximum.y)") &&
                source.contains("height: height, width: bodyWidth"),
                "AVATAR_HEAD_TO_FOOT_DOES_NOT_FOLLOW_SUBJECT_MESH_BOUNDS",
                &failures)
        require(source.contains("func symmetricWidth(") &&
                source.contains("2 * min(left, right)") &&
                source.contains("let shoulderWidth = symmetricWidth") &&
                source.contains("let hipWidth = symmetricWidth"),
                "ASYMMETRIC_GARMENT_CAN_STILL_DEFINE_BODY_ENVELOPE",
                &failures)
        require(source.contains("chestDepthShape") &&
                source.contains("waistDepthShape") &&
                source.contains("hipDepthShape") &&
                source.contains("avatarProfile.chestCM / 92.0") &&
                source.contains("avatarProfile.waistCM / 76.0") &&
                source.contains("avatarProfile.hipCM / 98.0"),
                "SELECTED_DIMENSIONS_ARE_NOT_RETAINED_FOR_DEPTH",
                &failures)
        require(source.contains("selectedMeasurementAuthority") &&
                source.contains("REQUESTED_OR_SELECTED") &&
                source.contains("singleImageMeasurementsInferred = false") &&
                source.contains("metadata.single-image-measurements-inferred"),
                "SINGLE_IMAGE_VISUAL_FIT_CAN_BE_MISTAKEN_FOR_MEASUREMENT",
                &failures)
        require(!source.contains("node.userData") &&
                !source.contains("content.userData") &&
                source.contains("addTypedPreviewMetadata") &&
                source.contains("marker.categoryBitMask"),
                "PREVIEW_METADATA_USES_UNSUPPORTED_SCENEKIT_USER_DATA",
                &failures)
        require(source.contains("IMAGE_TOP_IS_TEXTURE_V_0") &&
                source.contains("CGPoint(x: CGFloat($0[0]), y: CGFloat($0[1]))"),
                "FIXED_UV_TOP_CONVENTION_WAS_NOT_PRESERVED", &failures)
        let expectedAvatarIDs = [
            "preview-straight-170", "preview-balanced-170",
            "preview-curved-165", "preview-petite-155",
            "preview-compact-160", "preview-straight-165",
            "preview-balanced-175", "preview-tall-180",
            "preview-broad-175", "preview-tall-185",
        ]
        require(expectedAvatarIDs.allSatisfy(engineSource.contains) &&
                engineSource.contains("authority: \"PROPOSED_PREVIEW\""),
                "TEN_PROPOSAL_ONLY_BASE_AVATARS_ARE_NOT_AVAILABLE",
                &failures)
        return failures
    }

    private static func require(_ condition: @autoclosure () -> Bool,
                                _ code: String, _ failures: inout [String]) {
        if !condition() { failures.append(code) }
    }
}

#if !IMAGE_RELATIVE_AVATAR_FIT_STANDALONE
final class ImageRelativeAvatarPreviewFitAuditTests: XCTestCase {
    func testFusedCleanupMannequinUsesProposalOnlyImageRelativeFit() {
        XCTAssertEqual(ImageRelativeAvatarPreviewFitAudit.failures(), [])
    }
}
#else
@main
private enum ImageRelativeAvatarPreviewFitAuditMain {
    static func main() {
        let failures = ImageRelativeAvatarPreviewFitAudit.failures()
        if failures.isEmpty { print("PASS image-relative avatar preview fit audit") }
        else { failures.forEach { print("FAIL \($0)") }; exit(1) }
    }
}
#endif
