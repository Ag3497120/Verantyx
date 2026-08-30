import Foundation

#if !ATELIER_LLM_ENVELOPE_STANDALONE
import XCTest
#endif

private enum AtelierLLMEnvelopeAudit {
    static func failures() -> [String] {
        let file = URL(fileURLWithPath: #filePath)
        let appRoot = file.deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let plannerURL = appRoot.appendingPathComponent(
            "Sources/Verantyx/Engine/AtelierGarmentRequestPlanner.swift")
        let routerURL = appRoot.appendingPathComponent(
            "Sources/Verantyx/Engine/AtelierChatRouter.swift")
        guard let planner = try? String(contentsOf: plannerURL, encoding: .utf8),
              let router = try? String(contentsOf: routerURL, encoding: .utf8) else {
            return ["LLM_ENVELOPE_SOURCE_UNREADABLE"]
        }
        var failures: [String] = []
        func require(_ condition: Bool, _ code: String) {
            if !condition { failures.append(code) }
        }
        require(planner.contains("private struct ModelEnvelope") &&
                planner.contains("let speech: String") &&
                planner.contains("let command: Proposal?"),
                "FREE_SPEECH_AND_ACTION_ARE_NOT_SEPARATE")
        require(planner.contains("Return exactly one JSON") &&
                planner.contains("it MUST be GENERATE_FROM_IMAGE"),
                "IMAGE_REQUEST_CAN_SILENTLY_DROP_ACTION")
        require(planner.contains("case \"CONVERSATION\"") &&
                planner.contains("never use a null command") &&
                planner.contains("\"command\": command") &&
                planner.contains("\"CONVERSATION\", \"SET_REQUIREMENTS\""),
                "MODEL_HAS_NO_MANDATORY_SEMANTIC_ROUTE_DECISION")
        require(planner.contains("JSONDecoder().decode(") &&
                planner.contains("ModelEnvelope.self") &&
                planner.contains("displayText(envelope.speech)"),
                "ENVELOPE_IS_NOT_DECODED_INTO_FREE_SPEECH")
        require(planner.contains("<vera_command>") &&
                planner.contains("Compatibility with models"),
                "PREVIOUS_MODEL_PROTOCOL_HAS_NO_SAFE_COMPATIBILITY")
        require(router.contains("AtelierGarmentRequestPlanner.plan(") &&
                !router.contains("let fallback = await resolve(text)"),
                "BEGINNER_REQUEST_FELL_BACK_TO_FIXED_TEXT_GRAMMAR")
        require(router.contains("制作モデルの提案（AI生成・未検証）") &&
                router.contains("以下は作業計画であり、生成結果ではありません") &&
                router.contains("artifact_status=NOT_GENERATED_WAITING_FOR_HUMAN") &&
                router.contains("3D・型紙・縫製成果物はまだ生成されていません"),
                "UNGENERATED_FACTORY_WORK_CAN_BE_PRESENTED_AS_A_RESULT")
        require(planner.contains("a proposed plan, not a progress or success") &&
                planner.contains("no 3D, pattern, or sewing output"),
                "MODEL_PROMPT_CAN_PROMISE_UNGENERATED_ARTIFACTS")
        return failures
    }
}

#if !ATELIER_LLM_ENVELOPE_STANDALONE
final class AtelierLLMEnvelopeAuditTests: XCTestCase {
    func testLLMFreeSpeechAndTypedProposalBoundary() {
        XCTAssertEqual(AtelierLLMEnvelopeAudit.failures(), [])
    }
}
#else
@main
private struct AtelierLLMEnvelopeAuditRunner {
    static func main() {
        let failures = AtelierLLMEnvelopeAudit.failures()
        if failures.isEmpty {
            print("PASS Atelier LLM free-speech envelope invariants")
            exit(0)
        }
        failures.forEach { print("FAIL \($0)") }
        exit(1)
    }
}
#endif
