import Foundation

#if !UNIFIED_COMPOSER_VISUAL_AUDIT_STANDALONE
import XCTest
@testable import Verantyx
#endif

/// Source-level guard for the unified composer contract. This deliberately
/// avoids constructing AppState or mutating the shared garment intake.
private enum UnifiedComposerVisualAudit {
    static func failures() -> [String] {
        let testFile = URL(fileURLWithPath: #filePath)
        let sourceURL = testFile.deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Sources/Verantyx/Views/UnifiedComposerView.swift")
        guard let source = try? String(contentsOf: sourceURL, encoding: .utf8) else {
            return ["UNIFIED_COMPOSER_SOURCE_UNREADABLE"]
        }

        var failures: [String] = []
        require(source.contains("private let composerMaxWidth: CGFloat = 820") &&
                source.contains("composerContentHeight") &&
                source.contains("private var composerHeight: CGFloat"),
                "COMPOSER_WIDTH_OR_DYNAMIC_HEIGHT_MISSING", into: &failures)
        require(!source.contains("JCrossSendButton(enabled:") &&
                source.contains("private var composerSendButton") &&
                source.contains("Image(systemName: \"arrow.up\")") &&
                source.contains("Circle().fill(enabled ? Theme.sel"),
                "CONVENTIONAL_SEND_BUTTON_MISSING", into: &failures)
        require(!source.contains(".background(Theme.panel2)") &&
                !source.contains("LinearGradient(") &&
                source.contains("all live on the composer's single rounded surface"),
                "NESTED_TWO_TONE_SURFACE_REINTRODUCED", into: &failures)
        require(source.contains("if app.isGenerating") &&
                source.contains("ComposerInferenceSpinner(phase: inferenceSpinnerPhase)") &&
                source.contains("@ObservedObject private var factory") &&
                source.contains("factory.busy") &&
                source.contains("case analysis") &&
                source.contains("case validation") &&
                source.contains("case repair"),
                "PHASE_AWARE_INFERENCE_SPINNER_MISSING", into: &failures)
        require(source.contains("TimelineView(.animation") &&
                source.contains("accessibilityReduceMotion") &&
                source.contains(".accessibilityValue(phase.accessibleName)"),
                "SPINNER_MOTION_ACCESSIBILITY_MISSING", into: &failures)
        require(spinnerSection(in: source).contains("JCrossGlyph(") &&
                !spinnerSection(in: source).contains("Button"),
                "INFERENCE_CROSS_IS_NOT_A_PASSIVE_SIX_ARM_SPINNER", into: &failures)
        require(source.contains("intake.composerSelectedClip") &&
                source.contains("intake.hasComposerAttachment") &&
                !source.contains("intake.selectedClip") &&
                source.contains(".keyboardShortcut(\"i\", modifiers: [.command, .shift])"),
                "ATELIER_COMPOSER_ATTACHMENT_CONTRACT_BROKEN", into: &failures)
        return failures
    }

    private static func spinnerSection(in source: String) -> String {
        guard let start = source.range(of: "private struct ComposerInferenceSpinner"),
              let end = source.range(of: "\n}", options: .backwards),
              end.lowerBound >= start.lowerBound else { return "" }
        return String(source[start.lowerBound...end.upperBound])
    }

    private static func require(_ condition: @autoclosure () -> Bool,
                                _ failure: String,
                                into failures: inout [String]) {
        if !condition() { failures.append(failure) }
    }
}

#if !UNIFIED_COMPOSER_VISUAL_AUDIT_STANDALONE
final class UnifiedComposerVisualAuditTests: XCTestCase {
    func testUnifiedComposerVisualContract() {
        XCTAssertEqual(UnifiedComposerVisualAudit.failures(), [])
    }
}
#else
@main
private enum UnifiedComposerVisualAuditMain {
    static func main() {
        let failures = UnifiedComposerVisualAudit.failures()
        if failures.isEmpty {
            print("PASS unified composer visual audit")
        } else {
            failures.forEach { print("FAIL \($0)") }
            exit(1)
        }
    }
}
#endif
