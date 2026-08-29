import Foundation

#if !CHAT_MESSAGE_ATTACHMENT_PERSISTENCE_STANDALONE
import XCTest
@testable import Verantyx
#endif

private enum ChatMessageAttachmentPersistenceAudit {
    static func failures() -> [String] {
        let file = URL(fileURLWithPath: #filePath)
        let app = file.deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        let sources = app.appendingPathComponent("Sources/Verantyx")
        guard let state = read(sources.appendingPathComponent("AppState.swift")),
              let intake = read(sources.appendingPathComponent("Views/AtelierIntake.swift")),
              let manager = read(sources.appendingPathComponent("Engine/AttachmentManager.swift"))
        else { return ["ATTACHMENT_SOURCE_UNREADABLE"] }

        var failures: [String] = []
        require(state.contains("var attachments: [Attachment] = []") &&
                state.contains("decodeIfPresent([Attachment].self, forKey: .attachments) ?? []") &&
                state.contains("struct Attachment: Identifiable, Codable, Equatable"),
                "CHAT_HISTORY_IS_NOT_BACKWARD_COMPATIBLE_WITH_TYPED_ATTACHMENTS", &failures)
        require(state.contains("AtelierIntake.shared.composerSelectedClip") &&
                state.contains("attachments: messageAttachments") &&
                state.contains("AtelierIntake.shared.clearComposerSelection()") &&
                !state.contains("📎 [Garment image:"),
                "ATELIER_SEND_STILL_SERIALIZES_A_FILENAME_MARKER", &failures)
        require(intake.contains("composerAttachmentVisible") &&
                intake.contains("var composerSelectedClip: Clip?") &&
                intake.contains("composerAttachmentVisible = false") &&
                clearBody(intake).contains("composerAttachmentVisible = false") &&
                !clearBody(intake).contains("selectedClip = nil"),
                "COMPOSER_CLEAR_CAN_CANCEL_THE_ACTIVE_FACTORY_IMAGE", &failures)
        require(manager.contains("Verantyx/chat-attachments") &&
                manager.contains("cacheTranscriptImage") &&
                manager.contains("NSImage(contentsOf: source) != nil") &&
                manager.contains("ChatMessage.Attachment(kind: .image"),
                "SENT_IMAGE_HAS_NO_DURABLE_RENDERABLE_SNAPSHOT", &failures)
        return failures
    }

    private static func read(_ url: URL) -> String? {
        try? String(contentsOf: url, encoding: .utf8)
    }

    private static func clearBody(_ source: String) -> String {
        guard let start = source.range(of: "func clearComposerSelection()"),
              let end = source.range(of: "\n    }", range: start.upperBound..<source.endIndex)
        else { return "" }
        return String(source[start.lowerBound..<end.upperBound])
    }

    private static func require(_ condition: @autoclosure () -> Bool,
                                _ code: String, _ failures: inout [String]) {
        if !condition() { failures.append(code) }
    }
}

#if !CHAT_MESSAGE_ATTACHMENT_PERSISTENCE_STANDALONE
final class ChatMessageAttachmentPersistenceAuditTests: XCTestCase {
    func testTypedAttachmentSnapshotAndComposerFactorySeparation() {
        XCTAssertEqual(ChatMessageAttachmentPersistenceAudit.failures(), [])
    }
}
#else
@main
private enum ChatMessageAttachmentPersistenceAuditMain {
    static func main() {
        let failures = ChatMessageAttachmentPersistenceAudit.failures()
        if failures.isEmpty { print("PASS typed chat attachment persistence audit") }
        else { failures.forEach { print("FAIL \($0)") }; exit(1) }
    }
}
#endif
