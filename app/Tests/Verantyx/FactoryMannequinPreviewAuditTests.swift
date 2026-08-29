import Foundation

#if !FACTORY_MANNEQUIN_PREVIEW_STANDALONE
import XCTest
@testable import Verantyx
#endif

private enum FactoryMannequinPreviewAudit {
    static func failures() -> [String] {
        let file = URL(fileURLWithPath: #filePath)
        let views = file.deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Sources/Verantyx/Views")
        guard let source = try? String(contentsOf:
            views.appendingPathComponent("AtelierChatPaneView.swift"), encoding: .utf8)
        else { return ["FACTORY_PREVIEW_SOURCE_UNREADABLE"] }
        var failures: [String] = []
        require(source.contains("3D MANNEQUIN · PROPOSED") &&
                source.contains("mannequinNode(minimum:") &&
                source.contains("SCNCapsule") && source.contains("SCNSphere"),
                "PREVIEW_HAS_NO_ARTICULATED_DRESS_FORM", &failures)
        require(source.contains("faceComponents(validFaces)") &&
                source.contains("let palette: [NSColor]") &&
                source.contains("surface.lightingModel = .physicallyBased"),
                "GARMENT_LAYERS_ARE_NOT_VISUALLY_SEPARATED", &failures)
        require(source.contains("This is a visual proposal, never material identification") &&
                source.contains("wearer measurements") &&
                source.contains("not from this display proxy"),
                "DISPLAY_PROXY_LOST_ITS_TRUTH_BOUNDARY", &failures)
        return failures
    }

    private static func require(_ condition: @autoclosure () -> Bool,
                                _ code: String, _ failures: inout [String]) {
        if !condition() { failures.append(code) }
    }
}

#if !FACTORY_MANNEQUIN_PREVIEW_STANDALONE
final class FactoryMannequinPreviewAuditTests: XCTestCase {
    func testCandidateSurfaceIsShownOnNeutralMannequinWithoutPromotingFacts() {
        XCTAssertEqual(FactoryMannequinPreviewAudit.failures(), [])
    }
}
#else
@main
private enum FactoryMannequinPreviewAuditMain {
    static func main() {
        let failures = FactoryMannequinPreviewAudit.failures()
        if failures.isEmpty { print("PASS factory mannequin preview audit") }
        else { failures.forEach { print("FAIL \($0)") }; exit(1) }
    }
}
#endif
