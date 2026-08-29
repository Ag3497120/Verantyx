import Foundation

#if !BEGINNER_CHAT_LAYOUT_AUDIT_STANDALONE
import XCTest
@testable import Verantyx
#endif

/// Source-level boundary audit for the beginner chat layout.
///
/// The fixed measure spans SwiftUI and AppKit, so this audit checks the
/// coupling explicitly: one shared geometry contract, a fixed transcript /
/// composer canvas, equal flexible gutters, a real NSWindow content floor,
/// and one main background token. It also guards the existing attachment,
/// selection, spinner and composer implementations from being replaced by a
/// second chat surface as part of a layout-only edit.
private enum BeginnerChatLayoutAudit {
    static func failures() -> [String] {
        let testFile = URL(fileURLWithPath: #filePath)
        let appRoot = testFile.deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let sourceRoot = appRoot.appendingPathComponent("Sources/Verantyx")

        guard let shell = read("Views/IDEShellView.swift", from: sourceRoot),
              let transcript = read("Views/ChatTranscriptView.swift", from: sourceRoot),
              let composer = read("Views/UnifiedComposerView.swift", from: sourceRoot),
              let human = read("Views/HumanPriorityModeView.swift", from: sourceRoot),
              let app = read("VerantyxApp.swift", from: sourceRoot) else {
            return ["BEGINNER_CHAT_LAYOUT_SOURCE_UNREADABLE"]
        }

        var failures: [String] = []
        require(shell.contains("enum BeginnerChatLayout") &&
                shell.contains("static let canvasWidth: CGFloat = 920") &&
                shell.contains("static let outerGutter: CGFloat = 24") &&
                shell.contains("static let primarySidebarWidth: CGFloat = 210") &&
                shell.contains("static let minimumWindowContentWidth = primarySidebarWidth"),
                "SHARED_FIXED_CHAT_GEOMETRY_MISSING", into: &failures)

        let canvas = section(in: shell,
                             from: "private var beginnerChatCanvas",
                             to: "// MARK: - Left rail")
        require(shell.contains("if shell.activeTab?.kind == .chat") &&
                shell.contains("beginnerChatCanvas") &&
                canvas.contains("AgentChatView(showsOwnComposer: false)") &&
                canvas.contains("UnifiedComposerView()") &&
                canvas.contains(".frame(width: BeginnerChatLayout.canvasWidth"),
                "TRANSCRIPT_AND_COMPOSER_NOT_IN_ONE_FIXED_CANVAS", into: &failures)
        require(occurrences(of: "Spacer(minLength: BeginnerChatLayout.outerGutter)",
                            in: canvas) == 2,
                "SYMMETRIC_FLEXIBLE_GUTTERS_MISSING", into: &failures)
        require(shell.contains(".frame(minWidth: BeginnerChatLayout.minimumMainColumnWidth") &&
                shell.contains(".background(Theme.panel2)") &&
                shell.contains(".frame(width: 210)") &&
                shell.contains(".background(Theme.panel)"),
                "MAIN_SURFACE_OR_DISTINCT_SIDEBAR_CONTRACT_BROKEN", into: &failures)

        require(app.contains(".frame(minWidth: BeginnerChatLayout.minimumWindowContentWidth") &&
                app.contains("Self.enforceMainWindowMinimumContentSize()") &&
                app.contains("win.contentMinSize = NSSize(") &&
                app.contains("width: BeginnerChatLayout.minimumWindowContentWidth"),
                "MACOS_WINDOW_CONTENT_FLOOR_MISSING", into: &failures)
        require(human.contains("main surface. IDEShellView paints the left rail") &&
                human.contains(".background(Theme.panel2)"),
                "ROOT_MAIN_BACKGROUND_NOT_UNIFIED", into: &failures)
        require(transcript.contains("tv.backgroundColor      = Theme.nsPanel2") &&
                transcript.contains("sv.backgroundColor     = Theme.nsPanel2"),
                "APPKIT_TRANSCRIPT_BACKGROUND_NOT_UNIFIED", into: &failures)

        // Layout edits must keep the one established interactive transcript
        // and composer instead of introducing simplified replacements.
        require(transcript.contains("verantyx-image://") &&
                transcript.contains("ImagePreviewPanelController") &&
                transcript.contains("tv.isSelectable         = true") &&
                transcript.contains("verantyx-copy://"),
                "ATTACHMENT_PREVIEW_SELECTION_OR_COPY_REGRESSED", into: &failures)
        require(composer.contains("ComposerInferenceSpinner(phase: inferenceSpinnerPhase)") &&
                composer.contains("intake.composerSelectedClip") &&
                composer.contains("private var composerSendButton"),
                "SPINNER_ATTACHMENT_OR_COMPOSER_BEHAVIOR_REPLACED", into: &failures)

        return failures
    }

    private static func read(_ relativePath: String, from root: URL) -> String? {
        try? String(contentsOf: root.appendingPathComponent(relativePath),
                    encoding: .utf8)
    }

    private static func section(in source: String, from start: String,
                                to end: String) -> String {
        guard let lower = source.range(of: start),
              let upper = source.range(of: end,
                                       range: lower.upperBound..<source.endIndex) else {
            return ""
        }
        return String(source[lower.lowerBound..<upper.lowerBound])
    }

    private static func occurrences(of needle: String, in haystack: String) -> Int {
        haystack.components(separatedBy: needle).count - 1
    }

    private static func require(_ condition: @autoclosure () -> Bool,
                                _ failure: String,
                                into failures: inout [String]) {
        if !condition() { failures.append(failure) }
    }
}

#if !BEGINNER_CHAT_LAYOUT_AUDIT_STANDALONE
final class BeginnerChatLayoutAuditTests: XCTestCase {
    func testFixedMeasureGuttersMinimumWindowAndUnifiedBackground() {
        XCTAssertEqual(BeginnerChatLayoutAudit.failures(), [])
    }
}
#else
@main
private enum BeginnerChatLayoutAuditMain {
    static func main() {
        let failures = BeginnerChatLayoutAudit.failures()
        if failures.isEmpty {
            print("PASS beginner chat layout audit")
        } else {
            failures.forEach { print("FAIL \($0)") }
            exit(1)
        }
    }
}
#endif
