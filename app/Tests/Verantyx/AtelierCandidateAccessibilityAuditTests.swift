import Foundation

#if !ATELIER_CANDIDATE_ACCESSIBILITY_STANDALONE
import XCTest
@testable import Verantyx
#endif

/// Source-level regression audit for the two beginner candidate-card surfaces.
/// It intentionally does not instantiate the factory or mutate engine state.
private enum AtelierCandidateAccessibilityAudit {
    static func failures() -> [String] {
        let testFile = URL(fileURLWithPath: #filePath)
        let views = testFile.deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Sources/Verantyx/Views")
        guard let live = read("AtelierChatPaneView.swift", from: views),
              let dynamic = read("AtelierDynamicFlowView.swift", from: views) else {
            return ["CANDIDATE_UI_SOURCE_UNREADABLE"]
        }

        var failures: [String] = []
        require(live.contains("@FocusState private var candidateControlFocus") &&
                live.contains("moveFromComposerToCandidate(for: press)") &&
                live.contains("press.key == .tab") &&
                live.contains("press.modifiers.contains(.shift)"),
                "LIVE_COMPOSER_HAS_NO_TAB_HANDOFF", into: &failures)
        require(live.contains(".focusable()") &&
                live.contains(".focused($candidateControlFocus, equals: previewFocus)") &&
                live.contains(".focused($candidateControlFocus, equals: adoptFocus)") &&
                live.contains(".focusSection()"),
                "LIVE_CANDIDATE_CONTROLS_NOT_FOCUSABLE", into: &failures)
        require(live.contains("atelier.beginner.candidate.\\(focus.domain).\\(focus.candidateID).\\(focus.action.rawValue)") &&
                live.contains("Preview 3D and pattern for \\(candidate.title), AI-proposed candidate") &&
                live.contains("Adopt \\(candidate.title), AI-proposed candidate") &&
                live.contains(".accessibilityElement(children: .contain)"),
                "LIVE_CANDIDATE_ACCESSIBILITY_IDENTITY_MISSING", into: &failures)
        require(live.contains("factory.designRequirementReviewItems") &&
                live.contains("REQUESTED_NOT_MEASURED") &&
                live.contains("not measurements observed from the image") &&
                live.contains("AI-inferred back, depth, and material remain not observed"),
                "LIVE_REQUESTED_CONDITIONS_PROVENANCE_MISSING", into: &failures)

        require(dynamic.contains("@FocusState private var candidateControlFocus") &&
                dynamic.contains(".focused($candidateControlFocus, equals: previewFocus)") &&
                dynamic.contains(".focused($candidateControlFocus, equals: adoptFocus)") &&
                dynamic.contains(".onKeyPress(.return)") &&
                dynamic.contains(".onKeyPress(.space)") &&
                dynamic.contains(".onKeyPress(phases: .down)") &&
                dynamic.contains("moveCandidateFocus(") &&
                dynamic.contains("focusFirstPendingCandidateIfNeeded()") &&
                dynamic.contains("BACK_CANDIDATES_READY") &&
                dynamic.contains("atelier.beginner.dynamic-candidate.\\(focus.domain).\\(focus.candidateID).\\(focus.action.rawValue)") &&
                dynamic.contains(".accessibilityElement(children: .contain)"),
                "DYNAMIC_CANDIDATE_ACCESSIBILITY_PATH_MISSING", into: &failures)
        require(dynamic.contains("factory.designRequirementReviewItems") &&
                dynamic.contains("指定条件 · REQUESTED_NOT_MEASURED") &&
                dynamic.contains("atelier.beginner.dynamic.requested-conditions.review") &&
                dynamic.contains("requestedConditionsAccessibilityLabel") &&
                dynamic.contains("not measurements observed from the image") &&
                dynamic.contains("AI-inferred back, depth, and material remain not observed"),
                "DYNAMIC_REQUESTED_CONDITIONS_PROVENANCE_MISSING", into: &failures)

        for forbidden in ["MCPEngine.shared", "garment_factory", "SUBMIT_HYPOTHESES"] {
            require(!candidateFunction(in: live).contains(forbidden),
                    "LIVE_CARD_BYPASSES_CONTROLLER_\(forbidden)", into: &failures)
        }
        return failures
    }

    private static func read(_ name: String, from root: URL) -> String? {
        try? String(contentsOf: root.appendingPathComponent(name), encoding: .utf8)
    }

    private static func candidateFunction(in source: String) -> String {
        guard let start = source.range(of: "private func factoryCandidateCard("),
              let end = source.range(of: "private func factoryVisionPatternOperationCard(",
                                     range: start.upperBound..<source.endIndex) else {
            return ""
        }
        return String(source[start.lowerBound..<end.lowerBound])
    }

    private static func require(_ condition: @autoclosure () -> Bool,
                                _ failure: String,
                                into failures: inout [String]) {
        if !condition() { failures.append(failure) }
    }
}

#if !ATELIER_CANDIDATE_ACCESSIBILITY_STANDALONE
final class AtelierCandidateAccessibilityAuditTests: XCTestCase {
    func testBeginnerCandidateKeyboardAndAccessibilityPath() {
        XCTAssertEqual(AtelierCandidateAccessibilityAudit.failures(), [])
    }
}
#else
@main
private enum AtelierCandidateAccessibilityAuditMain {
    static func main() {
        let failures = AtelierCandidateAccessibilityAudit.failures()
        if failures.isEmpty {
            print("PASS beginner candidate keyboard/accessibility audit")
        } else {
            failures.forEach { print("FAIL \($0)") }
            exit(1)
        }
    }
}
#endif
