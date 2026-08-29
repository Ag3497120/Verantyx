import Foundation

#if !CHAT_TRANSCRIPT_ATTACHMENT_AUDIT_STANDALONE
import XCTest
@testable import Verantyx
#endif

/// Deterministic source audit for the AppKit transcript contract.  The view
/// intentionally remains one NSTextView so selection may span messages; this
/// audit prevents a future visual rewrite from quietly regressing that
/// behavior or replacing real sent images with filename-only markers.
private enum ChatTranscriptAttachmentAudit {
    static func failures() -> [String] {
        let testFile = URL(fileURLWithPath: #filePath)
        let sourceURL = testFile.deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Sources/Verantyx/Views/ChatTranscriptView.swift")
        guard let source = try? String(contentsOf: sourceURL, encoding: .utf8) else {
            return ["CHAT_TRANSCRIPT_SOURCE_UNREADABLE"]
        }

        var failures: [String] = []
        require(source.contains("struct ChatTranscriptView: NSViewRepresentable") &&
                source.contains("let tv = SelectableTextView()") &&
                source.contains("tv.isSelectable         = true"),
                "TRANSCRIPT_NO_LONGER_SINGLE_SELECTABLE_TEXT_VIEW", into: &failures)
        require(source.contains("NSTextTableBlock(") &&
                source.contains("paragraph.textBlocks = [block]") &&
                source.contains("for: .maximumWidth") &&
                source.contains("for: .margin, edge: .minX"),
                "USER_BUBBLE_IS_NOT_A_CONTROLLED_TEXT_BLOCK", into: &failures)
        require(!userFunction(in: source).contains(".backgroundColor: Palette.userBubbleBg"),
                "USER_BUBBLE_REGRESSED_TO_GLYPH_RUN_BACKGROUNDS", into: &failures)
        require(source.contains("message.attachments.enumerated()") &&
                source.contains("NSImage(contentsOfFile: item.path)") &&
                source.contains("verantyx-image://") &&
                source.contains("ImagePreviewPanelController") &&
                source.contains("let panel = NSPanel("),
                "REAL_IMAGE_THUMBNAIL_OR_IN_APP_PREVIEW_MISSING", into: &failures)
        require(source.contains("isReadableFile(atPath:") &&
                source.contains("continue\n            }"),
                "UNREADABLE_IMAGE_FAIL_CLOSED_PATH_MISSING", into: &failures)
        require(source.contains("systemSymbolName: \"doc.on.doc\"") &&
                source.contains("verantyx-copy://") &&
                source.contains("case .user:      appendUser") &&
                source.contains("case .assistant: appendAssistant"),
                "MESSAGE_COPY_ICON_PATH_MISSING", into: &failures)
        require(source.contains("Do not consume mouseDown") &&
                source.contains("hypot(pt.x - downPoint.x") &&
                source.contains("super.mouseDown(with: event)"),
                "ACTION_ICON_BLOCKS_TRANSCRIPT_DRAG_SELECTION", into: &failures)
        require(source.contains("lastAttachmentSignature") &&
                source.contains("!attachmentsChanged, newCount == co.lastCount"),
                "ATTACHMENTS_BYPASS_STREAMING_INVALIDATION", into: &failures)
        return failures
    }

    private static func userFunction(in source: String) -> String {
        guard let start = source.range(of: "private static func appendUser("),
              let end = source.range(of: "private static func appendAssistant(",
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

#if !CHAT_TRANSCRIPT_ATTACHMENT_AUDIT_STANDALONE
final class ChatTranscriptAttachmentAuditTests: XCTestCase {
    func testTranscriptPreservesSelectionBubbleImagesAndActions() {
        XCTAssertEqual(ChatTranscriptAttachmentAudit.failures(), [])
    }
}
#else
@main
private enum ChatTranscriptAttachmentAuditMain {
    static func main() {
        let failures = ChatTranscriptAttachmentAudit.failures()
        if failures.isEmpty {
            print("PASS chat transcript attachment audit")
        } else {
            failures.forEach { print("FAIL \($0)") }
            exit(1)
        }
    }
}
#endif
