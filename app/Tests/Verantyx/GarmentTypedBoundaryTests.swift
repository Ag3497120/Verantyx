import Foundation

#if !GARMENT_BOUNDARY_STANDALONE
import XCTest
@testable import Verantyx
#endif

/// Executable security/invariant audit for the beginner garment chat boundary.
///
/// The project currently has no XCTest native target, so the same checks can be
/// compiled with the three production sources using
/// `-D GARMENT_BOUNDARY_STANDALONE`. Once app/Tests is wired to a test bundle,
/// the XCTest wrapper below runs the identical checks.
@MainActor
private enum GarmentTypedBoundaryAudit {
    struct Report {
        var failures: [String] = []
        var knownGaps: [String] = []
    }

    static let expectedKnownGaps: Set<String> = []

    static func sourceAudit() -> Report {
        var report = Report()
        let testFile = URL(fileURLWithPath: #filePath)
        let appRoot = testFile.deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let engine = appRoot.appendingPathComponent("Sources/Verantyx/Engine")
        let routerURL = engine.appendingPathComponent("AtelierChatRouter.swift")
        let irURL = engine.appendingPathComponent("GarmentCommandIR.swift")
        let jobURL = engine.appendingPathComponent("GarmentGenerationJob.swift")
        let factoryURL = engine.appendingPathComponent("GarmentFactoryReactController.swift")
        let lmStudioURL = engine.appendingPathComponent("LMStudioClient.swift")

        guard let router = try? String(contentsOf: routerURL, encoding: .utf8),
              let ir = try? String(contentsOf: irURL, encoding: .utf8),
              let job = try? String(contentsOf: jobURL, encoding: .utf8),
              let factory = try? String(contentsOf: factoryURL, encoding: .utf8),
              let lmStudio = try? String(contentsOf: lmStudioURL, encoding: .utf8) else {
            report.failures.append("SOURCE_AUDIT_FILES_UNREADABLE")
            return report
        }

        // Strip line comments before looking for executable model clients. The
        // router's design comments intentionally contain the words LLM/model.
        let executableRouter = router.components(separatedBy: .newlines)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")
        for forbidden in ["GatekeeperLLM", "OllamaClient", "LMStudioClient",
                          "CloudAPIClient", "modelProposal"]
        where executableRouter.contains(forbidden) {
            report.failures.append("ROUTER_EXECUTABLE_MODEL_PATH_\(forbidden)")
        }

        require(router.contains("private static func execute("),
                "UNTYPED_EXECUTE_IS_EXTERNALLY_REACHABLE", into: &report)
        require(router.contains("GarmentCommandParser.parse("),
                "RESOLVE_DOES_NOT_PARSE_TYPED_COMMAND", into: &report)
        require(router.contains("AtelierGarmentRequestPlanner.plan(") &&
                router.contains("case .modelGenerated") &&
                router.contains("isExplicitHumanControl"),
                "BEGINNER_CHAT_IS_NOT_LLM_LED_WITH_TYPED_VERA_CONTROL", into: &report)
        require(!router.contains("let fallback = await resolve(text)") &&
                !router.contains("deterministicCommand"),
                "BEGINNER_CHAT_STILL_FALLS_BACK_TO_FIXED_GRAMMAR", into: &report)
        let completeConversation = sourceBlock(
            in: lmStudio, from: "func generateCompleteConversation(",
            to: "func generateConversation(")
        require(factory.contains("LMStudioClient.shared.generateCompleteConversation(") &&
                completeConversation.contains("\"stream\": false") &&
                completeConversation.contains("\"enable_thinking\": false") &&
                completeConversation.contains("/no_think") &&
                completeConversation.contains("\"reasoning_effort\": \"none\""),
                "ATELIER_MODEL_MOUTH_STILL_USES_REASONING_STREAM", into: &report)
        require(router.contains("callDoor(\"garment_workflow\""),
                "GARMENT_WORKFLOW_DOOR_MISSING", into: &report)
        require(router.contains("\"json_text\": json"),
                "WORKFLOW_DOOR_HAS_LOOSE_ARGUMENT_SHAPE", into: &report)
        require(!router.contains("callDoor(\"garment_command\""),
                "ROUTER_BYPASSES_INTEGRATED_WORKFLOW", into: &report)
        require(!router.contains("callDoor(\"garment_job\""),
                "ROUTER_BYPASSES_INTEGRATED_JOB", into: &report)
        require(router.contains("if command.requiresPreview"),
                "MUTATION_PREVIEW_GATE_MISSING", into: &report)
        require(router.contains("previewDigest: digest"),
                "APPROVAL_DIGEST_BINDING_MISSING", into: &report)
        require(ir.contains("let commit: Bool"),
                "IR_COMMIT_FIELD_MISSING", into: &report)
        require(ir.contains("commit: Bool = false"),
                "IR_MUTATION_DEFAULTS_TO_COMMIT", into: &report)
        require(ir.contains("static let schema = \"garment.command.v1\""),
                "IR_SCHEMA_NOT_CLOSED", into: &report)
        require(job.contains("UNKNOWN_STALE_PREVIEW_DIGEST"),
                "STALE_PREVIEW_REFUSAL_MISSING", into: &report)
        require(job.contains("UNKNOWN_INVALID_JOB_TRANSITION"),
                "LOCAL_TRANSITION_REFUSAL_MISSING", into: &report)
        require(job.contains("committedSnapshots.removeLast()"),
                "UNDO_IS_NOT_COMPENSATING_SNAPSHOT_RESTORE", into: &report)
        return report
    }

    private static func sourceBlock(
        in source: String, from startMarker: String, to endMarker: String
    ) -> String {
        guard let start = source.range(of: startMarker),
              let end = source.range(
                of: endMarker, range: start.upperBound..<source.endIndex)
        else { return "" }
        return String(source[start.lowerBound..<end.lowerBound])
    }

    static func runtimeAudit() -> Report {
        var report = Report()

        switch GarmentCommandParser.parse("30番から35番を広げて", jobID: "audit-job") {
        case .refused(let refusal):
            require(refusal.verdict == "UNKNOWN_EXPLICIT_UNIT_REQUIRED",
                    "UNITLESS_MUTATION_WRONG_REFUSAL", into: &report)
        default:
            report.failures.append("UNITLESS_MUTATION_WAS_NOT_REFUSED")
        }

        let mutation: GarmentCommandIR
        switch GarmentCommandParser.parse("35番から30番を3cm広げて", jobID: "audit-job") {
        case .command(let parsed):
            mutation = parsed
            require(parsed.schema == GarmentCommandIR.schema,
                    "PARSED_SCHEMA_CHANGED", into: &report)
            require(parsed.target?.first == 30 && parsed.target?.last == 35,
                    "PATTERN_SPAN_NOT_CANONICAL", into: &report)
            require(parsed.operation?.value == 3 && parsed.operation?.unit == .cm,
                    "TYPED_DIMENSION_LOST", into: &report)
            require(parsed.commit == false && parsed.requiresPreview,
                    "MUTATION_CAN_COMMIT_WITHOUT_PREVIEW", into: &report)
            require(parsed.provenance == .deterministicParse,
                    "PARSER_PROVENANCE_NOT_DETERMINISTIC", into: &report)
        default:
            report.failures.append("VALID_TYPED_MUTATION_DID_NOT_PARSE")
            return report
        }

        switch GarmentCommandParser.parse("approve", jobID: "audit-job") {
        case .refused(let refusal):
            require(refusal.verdict == "UNKNOWN_APPROVAL_DIGEST_REQUIRED",
                    "DIGESTLESS_APPROVAL_WRONG_REFUSAL", into: &report)
        default:
            report.failures.append("DIGESTLESS_APPROVAL_WAS_NOT_REFUSED")
        }

        for phrase in ["この画像を服にして", "この写真を衣装にして",
                       "添付画像の服を作って"] {
            switch GarmentCommandParser.parse(phrase, jobID: "audit-job") {
            case .command(let command):
                require(command.intent == .generateFromImage &&
                        command.target?.kind == "SELECTED_IMAGE",
                        "PHOTO_ALIAS_WRONG_COMMAND_\(phrase)", into: &report)
            default:
                report.failures.append("PHOTO_ALIAS_DID_NOT_PARSE_\(phrase)")
            }
        }

        let job = GarmentGenerationJob.shared
        require(job.activeSnapshot == .empty && job.pendingPreview == nil,
                "JOB_NOT_EMPTY_AT_AUDIT_START", into: &report)

        let jump = response(state: .complete, digest: "jump-evidence")
        switch job.stage(command: mutation, response: jump) {
        case .failure(let refusal):
            require(refusal.verdict == "UNKNOWN_INVALID_JOB_TRANSITION",
                    "INVALID_TRANSITION_WRONG_REFUSAL", into: &report)
        case .success:
            report.failures.append("LOCAL_RESPONSE_SKIPPED_STATE_MACHINE")
        }
        require(job.activeSnapshot == .empty,
                "REFUSED_TRANSITION_MUTATED_ACTIVE_STATE", into: &report)

        switch job.stage(command: mutation,
                         response: ["verdict": "ANSWER", "state": "IMAGE_RECEIVED"]) {
        case .failure(let refusal):
            require(refusal.verdict == "UNKNOWN_JOB_EVIDENCE_REQUIRED",
                    "EVIDENCELESS_TRANSITION_WRONG_REFUSAL", into: &report)
        case .success:
            report.failures.append("STATE_TRANSITION_WITHOUT_EVIDENCE_ACCEPTED")
        }

        let image = response(state: .imageReceived, digest: "image-evidence")
        let imagePreview: GarmentPreview
        switch job.stage(command: mutation, response: image) {
        case .success(let preview): imagePreview = preview
        case .failure(let refusal):
            report.failures.append("VALID_INITIAL_PREVIEW_REFUSED_\(refusal.verdict)")
            return report
        }
        require(job.activeSnapshot == .empty,
                "STAGING_MUTATED_ACTIVE_STATE", into: &report)

        switch job.approve(digest: "stale-000000000000") {
        case .failure(let refusal):
            require(refusal.verdict == "UNKNOWN_STALE_PREVIEW_DIGEST",
                    "STALE_APPROVAL_WRONG_REFUSAL", into: &report)
        case .success:
            report.failures.append("STALE_APPROVAL_COMMITTED")
        }
        require(job.activeSnapshot == .empty,
                "STALE_APPROVAL_MUTATED_ACTIVE_STATE", into: &report)

        switch job.approve(digest: imagePreview.digest) {
        case .success(let snapshot):
            require(snapshot.state == .imageReceived,
                    "APPROVAL_COMMITTED_WRONG_STATE", into: &report)
        case .failure(let refusal):
            report.failures.append("CURRENT_DIGEST_REFUSED_\(refusal.verdict)")
        }

        let regions = response(state: .regionsConfirmed, digest: "region-evidence")
        switch job.stage(command: mutation, response: regions) {
        case .success(let preview):
            if case .failure(let refusal) = job.approve(digest: preview.digest) {
                report.failures.append("SECOND_APPROVAL_REFUSED_\(refusal.verdict)")
            }
        case .failure(let refusal):
            report.failures.append("VALID_NEXT_TRANSITION_REFUSED_\(refusal.verdict)")
        }
        require(job.activeSnapshot.state == .regionsConfirmed && job.canUndo,
                "VALID_TRANSITION_DID_NOT_COMMIT", into: &report)

        switch job.undo() {
        case .success(let snapshot):
            require(snapshot.state == .imageReceived,
                    "UNDO_DID_NOT_RESTORE_PREVIOUS_SNAPSHOT", into: &report)
        case .failure(let refusal):
            report.failures.append("UNDO_REFUSED_\(refusal.verdict)")
        }
        require(job.pendingPreview == nil,
                "UNDO_LEFT_PENDING_PREVIEW", into: &report)

        // Remote previews pass the same state/evidence gate as local previews.
        let remote = remotePreview(
            jobID: job.jobID, before: .imageReceived, after: .complete,
            digest: String(repeating: "a", count: 64))
        if case .failure(let refusal) = job.stage(command: mutation, response: remote) {
            require(refusal.verdict == "UNKNOWN_INVALID_JOB_TRANSITION",
                    "REMOTE_PREVIEW_WRONG_TRANSITION_REFUSAL", into: &report)
        } else {
            report.failures.append("REMOTE_PREVIEW_SKIPPED_TRANSITION_GATE")
        }

        // Model-originated text can be a suggestion, never an engine fact.
        let modelAnswer = job.mirrorAnswer([
            "verdict": "ANSWER",
            "facts": ["model-originated unverified fact"],
            "provenance": "MODEL_PROPOSAL",
            "forbidden_claims": ["model-originated unverified fact"],
        ])
        require(modelAnswer.verdict == "PROPOSED" && modelAnswer.facts.isEmpty,
                "MODEL_PROPOSAL_WAS_EXPOSED_AS_FACT", into: &report)

        let knownGapSetIsExpected = Set(report.knownGaps) == expectedKnownGaps
        require(knownGapSetIsExpected,
                "KNOWN_GAP_SET_CHANGED", into: &report)
        return report
    }

    private static func response(state: GarmentGenerationJob.State,
                                 digest: String) -> [String: Any] {
        ["verdict": "ANSWER", "state": state.rawValue,
         "evidence_digest": digest,
         "artifact": ["digest": digest, "kind": "audit-fixture"]]
    }

    private static func remotePreview(jobID: String,
                                      before: GarmentGenerationJob.State,
                                      after: GarmentGenerationJob.State,
                                      digest: String) -> [String: Any] {
        [
            "verdict": "ANSWER",
            "job_id": jobID,
            "result": [
                "schema": GarmentPreview.schema,
                "preview_id": "audit-remote-preview",
                "digest": digest,
                "before": ["state": before.rawValue,
                           "artifacts": ["active": "before-evidence"],
                           "data": ["fixture": "before"]],
                "after": ["state": after.rawValue,
                          "artifacts": ["active": "after-evidence"],
                          "data": ["fixture": "after"]],
                "changed_addresses": ["/job/state"],
                "validation_results": ["ANSWER"],
            ],
        ]
    }

    private static func require(_ condition: @autoclosure () -> Bool,
                                _ failure: String, into report: inout Report) {
        if !condition() { report.failures.append(failure) }
    }
}

#if !GARMENT_BOUNDARY_STANDALONE
final class GarmentTypedBoundaryTests: XCTestCase {
    @MainActor
    func testRouterSourceHasNoExecutableLLMPathOrLooseGarmentDoor() {
        let report = GarmentTypedBoundaryAudit.sourceAudit()
        XCTAssertTrue(report.failures.isEmpty, report.failures.joined(separator: "\n"))
    }

    @MainActor
    func testTypedIRPreviewApprovalStateMachineAndDocumentedGaps() {
        let report = GarmentTypedBoundaryAudit.runtimeAudit()
        XCTAssertTrue(report.failures.isEmpty, report.failures.joined(separator: "\n"))
        XCTAssertEqual(Set(report.knownGaps), GarmentTypedBoundaryAudit.expectedKnownGaps)
    }
}
#else
@main
private struct GarmentTypedBoundaryStandaloneRunner {
    @MainActor
    static func main() {
        let source = GarmentTypedBoundaryAudit.sourceAudit()
        let runtime = GarmentTypedBoundaryAudit.runtimeAudit()
        let failures = source.failures + runtime.failures
        for gap in runtime.knownGaps.sorted() {
            print("KNOWN_GAP \(gap)")
        }
        if failures.isEmpty {
            print("PASS garment typed boundary invariants")
            exit(0)
        }
        for failure in failures { print("FAIL \(failure)") }
        exit(1)
    }
}
#endif
