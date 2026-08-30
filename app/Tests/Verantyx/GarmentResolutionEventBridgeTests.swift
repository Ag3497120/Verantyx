import Foundation

#if GARMENT_RESOLUTION_EVENT_BRIDGE_RUNTIME || !GARMENT_RESOLUTION_EVENT_BRIDGE_STANDALONE
@testable import Verantyx
#endif

#if !GARMENT_RESOLUTION_EVENT_BRIDGE_RUNTIME && !GARMENT_RESOLUTION_EVENT_BRIDGE_STANDALONE
import XCTest
#endif

/// Focused acceptance test for the progressive-resolution boundary.
///
/// The runtime fixture is deliberately a persisted factory, not a chat mock:
/// controller calls reach its `advance` door, mutate `cross_workflow`, and
/// return the same consent/resolution ledgers that the Python schema returns.
/// A controller result is accepted only if those persisted rows can be read
/// back. The source audit remains independently runnable on repositories where
/// `app/Tests` has not yet been attached to an Xcode test target.
private enum GarmentResolutionEventBridgeSourceAudit {
    struct Report { var failures: [String] = [] }

    static func run() -> Report {
        var report = Report()
        let testFile = URL(fileURLWithPath: #filePath)
        let appRoot = testFile.deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        let sourceRoot = appRoot.appendingPathComponent("Sources/Verantyx")
        let files = [
            sourceRoot.appendingPathComponent(
                "Engine/GarmentFactoryReactController.swift"),
            sourceRoot.appendingPathComponent("AppState.swift"),
            sourceRoot.appendingPathComponent("Views/AgentChatView.swift"),
        ]
        let sources = files.map { try? String(contentsOf: $0, encoding: .utf8) }
        guard sources.allSatisfy({ $0 != nil }) else {
            report.failures.append("RESOLUTION_BRIDGE_SOURCE_UNREADABLE")
            return report
        }
        let controller = executableSource(sources[0]!)
        let appState = executableSource(sources[1]!)
        let view = executableSource(sources[2]!)

        require(controller.contains("public func grantOneTimeLLMProposalConsent(") &&
                controller.contains("public func resolveCrossObligation("),
                "PUBLIC_ASYNC_CONTROLLER_BOUNDARY_MISSING", into: &report)
        for event in ["GRANT_LLM_PROPOSAL_CONSENT", "RESOLVE_CROSS_OBLIGATION"] {
            require(controller.contains("\"type\": \"\(event)\"") &&
                    controller.contains("let response = await advance(event: event)"),
                    "\(event)_DOES_NOT_REACH_FACTORY_ADVANCE", into: &report)
        }
        for persistedField in ["cross_workflow", "consents", "resolutions",
                               "resolution_digest", "request_provenance_digest",
                               "project_name"] {
            require(controller.contains("\"\(persistedField)\""),
                    "PERSISTED_\(persistedField.uppercased())_NOT_VERIFIED",
                    into: &report)
        }
        require(controller.contains("UNKNOWN_STALE_RESOLUTION_REQUEST") &&
                controller.contains("projectName == activeResolutionProject") &&
                controller.contains("request.provenanceDigest == provenanceDigest"),
                "REQUEST_DIGEST_PROJECT_STALENESS_GATE_MISSING", into: &report)
        require(appState.contains("await factory.grantOneTimeLLMProposalConsent(") &&
                appState.contains(".resolveCrossObligation(") &&
                !appState.contains("GRANT_LLM_PROPOSAL_CONSENT]") &&
                !appState.contains("RESOLVE_CROSS_OBLIGATION]"),
                "APPSTATE_RESOLUTION_STILL_USES_CHAT_MARKERS", into: &report)
        require(view.contains("garmentFactory.$pendingResolutionRequest") &&
                view.contains("performResolution") && view.contains("await operation()"),
                "SIDEBAR_DOES_NOT_AWAIT_TYPED_FACTORY_RESULT", into: &report)
        return report
    }

    private static func executableSource(_ source: String) -> String {
        source.replacingOccurrences(
            of: #"(?s)/\*.*?\*/|//[^\n]*"#, with: "",
            options: .regularExpression)
    }

    private static func require(
        _ condition: @autoclosure () -> Bool, _ failure: String,
        into report: inout Report
    ) {
        if !condition() { report.failures.append(failure) }
    }
}

#if GARMENT_RESOLUTION_EVENT_BRIDGE_RUNTIME || !GARMENT_RESOLUTION_EVENT_BRIDGE_STANDALONE
@MainActor
private final class PersistedResolutionFactoryFixture {
    let requestID = "resolution-fixture-1"
    let provenanceDigest = "sha256:fixture-request-v1"
    let projectName = "Fixture Garment"
    let missingFields = ["waist_cm", "rear_construction"]

    private(set) var state: [String: Any]
    private(set) var advanceEvents: [[String: Any]] = []

    init() {
        state = [
            "schema": GarmentFactoryReactController.harnessSchema,
            "phase": "HUMAN_GARMENT_AUDIT_REQUIRED",
            "cross_workflow": [
                "revision": 7,
                "obligations": [[
                    "request_id": requestID,
                    "code": "UNKNOWN_MEASUREMENTS_AND_REAR",
                    "stage": "BODY_AND_REAR",
                    "title": "寸法と背面構造が必要です",
                    "explanation": "正面画像では人体寸法と背面を観測できません。",
                    "missing_fields": missingFields,
                    "resolution_paths": [
                        ["path": "MEASURED_INPUT"],
                        ["path": "HUMAN_EDIT"],
                        ["path": "CONSENTED_LLM_PROPOSAL"],
                        ["path": "BOUNDED_ALTERNATIVES"],
                        ["path": "TYPED_STOP"],
                    ],
                    "provenance_digest": provenanceDigest,
                    "authority": "UNRESOLVED_WITH_TYPED_CONTINUATIONS",
                    "status": "OPEN",
                ]],
                "consents": [],
                "resolutions": [],
            ],
        ]
    }

    lazy var door: GarmentFactoryReactController.Door = { [weak self] action, payload in
        guard let self else { return ["verdict": "UNKNOWN_FIXTURE_RELEASED"] }
        switch action {
        case "inspect":
            return ["verdict": "REVIEW", "state": self.state]
        case "advance":
            guard let event = payload["event"] as? [String: Any] else {
                return ["verdict": "UNKNOWN_EVENT_REQUIRED", "state": self.state]
            }
            self.advanceEvents.append(event)
            switch event["type"] as? String {
            case "GRANT_LLM_PROPOSAL_CONSENT":
                return self.persistConsent(event)
            case "RESOLVE_CROSS_OBLIGATION":
                return self.persistResolution(event)
            default:
                return ["verdict": "UNKNOWN_FIXTURE_EVENT", "state": self.state]
            }
        default:
            return ["verdict": "UNKNOWN_FIXTURE_ACTION", "state": self.state]
        }
    }

    var persistedConsentCount: Int {
        workflow["consents"] as? [[String: Any]] != nil
            ? (workflow["consents"] as? [[String: Any]])!.count : 0
    }

    var persistedResolutionCount: Int {
        workflow["resolutions"] as? [[String: Any]] != nil
            ? (workflow["resolutions"] as? [[String: Any]])!.count : 0
    }

    private var workflow: [String: Any] {
        get { state["cross_workflow"] as? [String: Any] ?? [:] }
        set { state["cross_workflow"] = newValue }
    }

    private func persistConsent(_ event: [String: Any]) -> [String: Any] {
        var next = workflow
        let consentDigest = "sha256:consent-\(advanceEvents.count)"
        let boundDigest = "sha256:workflow-\(advanceEvents.count)"
        let artifact: [String: Any] = [
            "schema": "cross.workflow.consent.v1",
            "consent_digest": consentDigest,
            "bound_workflow_digest": boundDigest,
            "request_id": event["request_id"] as? String ?? "",
            "scope": event["scope"] as? String ?? "",
            "fields": event["fields"] as? [String] ?? [],
            "granted_by": event["granted_by"] as? String ?? "",
            "authority_ceiling": "PROPOSED",
            "may_promote_to_observed": false,
        ]
        var consents = next["consents"] as? [[String: Any]] ?? []
        consents.append(artifact)
        next["consents"] = consents
        next["revision"] = (next["revision"] as? Int ?? 0) + 1
        workflow = next
        return [
            "verdict": "CONSENT_RECORDED", "state": state,
            "consent_artifact": artifact,
        ]
    }

    private func persistResolution(_ event: [String: Any]) -> [String: Any] {
        var next = workflow
        let path = event["choice"] as? String ?? ""
        let values = event["values"] as? [String: Any] ?? [:]
        let status = path == "CONNECT_PROVIDER"
            ? "PARTIALLY_RESOLVED" : (path == "TYPED_STOP" ? "STOPPED" : "RESOLVED")
        var row: [String: Any] = [
            "request_id": event["request_id"] as? String ?? "",
            "choice": path,
            "resolution_path": path,
            "actor": event["actor"] as? String ?? "",
            "fields": Array(values.keys).sorted(),
            "remaining_fields": [],
            "status": status,
            "provenance": event["provenance"] as? [String: Any] ?? [:],
            "resolution_digest": "sha256:resolution-\(advanceEvents.count)",
        ]
        if let digest = event["consent_digest"] as? String {
            row["consent_digest"] = digest
        }
        var rows = next["resolutions"] as? [[String: Any]] ?? []
        rows.append(row)
        next["resolutions"] = rows
        if path != "CONNECT_PROVIDER" {
            var obligations = next["obligations"] as? [[String: Any]] ?? []
            if let index = obligations.firstIndex(where: {
                $0["request_id"] as? String == requestID
            }) {
                obligations[index]["status"] = status
            }
            next["obligations"] = obligations
            state["phase"] = path == "TYPED_STOP"
                ? "STOPPED" : "CONVERGED_REVIEW"
        }
        next["revision"] = (next["revision"] as? Int ?? 0) + 1
        workflow = next
        let verdict = path == "TYPED_STOP"
            ? "TYPED_STOP" : (path == "CONNECT_PROVIDER"
                ? "UNKNOWN_PARTIAL_RESOLUTION" : "ANSWER")
        return ["verdict": verdict, "state": state]
    }
}

@MainActor
private enum GarmentResolutionEventBridgeRuntimeAudit {
    static func run() async -> [String] {
        var failures: [String] = []
        await auditPersistedHumanResolution(into: &failures)
        await auditPersistedLLMConsentAndProposal(into: &failures)
        await auditStaleAndRevokedBoundaries(into: &failures)
        return failures
    }

    private static func preparedController(
        fixture: PersistedResolutionFactoryFixture,
        failures: inout [String]
    ) async -> GarmentFactoryReactController {
        let controller = GarmentFactoryReactController(
            hardRoundLimit: 2, door: fixture.door,
            toolDoor: { _, _ in ["verdict": "UNKNOWN_TOOL_NOT_EXPECTED"] })
        controller.activateResolutionProject(fixture.projectName)
        _ = await controller.runUntilPause(userRequest: "fixture")
        if controller.pendingResolutionRequest?.id != fixture.requestID {
            failures.append("FIXTURE_REQUEST_NOT_PUBLISHED")
        }
        return controller
    }

    private static func auditPersistedHumanResolution(
        into failures: inout [String]
    ) async {
        let fixture = PersistedResolutionFactoryFixture()
        let controller = await preparedController(fixture: fixture, failures: &failures)
        guard let published = controller.pendingResolutionRequest else {
            failures.append("UI_RESOLUTION_REQUEST_NOT_PUBLISHED")
            return
        }
        let request = GarmentResolutionRequest(factoryRequest: published)
        let app = AppState(garmentResolutionFactory: controller)
        let originalActiveGarment = app.activeGarment
        defer { app.activeGarment = originalActiveGarment }
        app.activeGarment = fixture.projectName
        let accepted = await app.submitGarmentResolution(
            request,
            values: ["waist_cm": "72",
                     "rear_construction": "human-edited"],
            measured: true)
        require(accepted, "PERSISTED_HUMAN_RESOLUTION_REJECTED", into: &failures)
        require(fixture.persistedResolutionCount == 1,
                "UI_ACTION_DID_NOT_CHANGE_PERSISTED_FACTORY_STATE", into: &failures)
        require(fixture.advanceEvents.last?["type"] as? String
                    == "RESOLVE_CROSS_OBLIGATION",
                "HUMAN_RESOLUTION_DID_NOT_CALL_ADVANCE", into: &failures)
        require(controller.pendingResolutionRequest == nil,
                "REQUEST_CLEARED_BEFORE_OR_NOT_AFTER_PERSISTENCE", into: &failures)
    }

    private static func auditPersistedLLMConsentAndProposal(
        into failures: inout [String]
    ) async {
        let fixture = PersistedResolutionFactoryFixture()
        let controller = await preparedController(fixture: fixture, failures: &failures)
        let grant = await controller.grantOneTimeLLMProposalConsent(
            requestID: fixture.requestID,
            provenanceDigest: fixture.provenanceDigest,
            projectName: fixture.projectName, by: "HUMAN:fixture")
        require(grant.accepted && fixture.persistedConsentCount == 1,
                "CONSENT_WAS_NOT_PERSISTED", into: &failures)
        require(fixture.advanceEvents.first?["type"] as? String
                    == "GRANT_LLM_PROPOSAL_CONSENT",
                "CONSENT_DID_NOT_CALL_ADVANCE", into: &failures)
        require(controller.pendingResolutionRequest != nil,
                "CONSENT_CLICK_SILENTLY_CLEARED_REQUEST", into: &failures)

        guard let consentDigest = grant.consentDigest else {
            failures.append("PERSISTED_CONSENT_DIGEST_MISSING")
            return
        }
        let proposal = await controller.resolveCrossObligation(
            requestID: fixture.requestID,
            provenanceDigest: fixture.provenanceDigest,
            projectName: fixture.projectName,
            path: .consentedLLMProposal,
            values: ["waist_cm": "PROPOSED:72",
                     "rear_construction": "PROPOSED:center-back"],
            actor: "LLM:fixture", consentDigest: consentDigest,
            resumeAfterAcceptance: false)
        require(proposal.accepted && fixture.persistedResolutionCount == 1,
                "CONSENTED_LLM_PROPOSAL_NOT_PERSISTED", into: &failures)
        let provenance = fixture.advanceEvents.last?["provenance"] as? [String: Any]
        require(provenance?["authority_ceiling"] as? String == "PROPOSED" &&
                provenance?["may_promote_model_output_to_observed"] as? Bool == false,
                "LLM_PROPOSAL_AUTHORITY_WAS_PROMOTED", into: &failures)
    }

    private static func auditStaleAndRevokedBoundaries(
        into failures: inout [String]
    ) async {
        let fixture = PersistedResolutionFactoryFixture()
        let controller = await preparedController(fixture: fixture, failures: &failures)
        let values: [String: Any] = [
            "waist_cm": "72", "rear_construction": "human-edited",
        ]
        let staleInputs = [
            ("stale-request", fixture.provenanceDigest, fixture.projectName),
            (fixture.requestID, "sha256:stale", fixture.projectName),
            (fixture.requestID, fixture.provenanceDigest, "Other Garment"),
        ]
        for (requestID, digest, project) in staleInputs {
            let before = fixture.advanceEvents.count
            let outcome = await controller.resolveCrossObligation(
                requestID: requestID, provenanceDigest: digest,
                projectName: project, path: .measuredInput,
                values: values, actor: "HUMAN:fixture",
                resumeAfterAcceptance: false)
            require(!outcome.accepted && fixture.advanceEvents.count == before,
                    "STALE_REQUEST_DIGEST_OR_PROJECT_REACHED_ADVANCE",
                    into: &failures)
        }

        let staleConsentBefore = fixture.advanceEvents.count
        let staleConsent = await controller.grantOneTimeLLMProposalConsent(
            requestID: fixture.requestID,
            provenanceDigest: "sha256:stale",
            projectName: fixture.projectName, by: "HUMAN:fixture")
        require(!staleConsent.accepted &&
                fixture.advanceEvents.count == staleConsentBefore,
                "STALE_CONSENT_REACHED_ADVANCE", into: &failures)

        let grant = await controller.grantOneTimeLLMProposalConsent(
            requestID: fixture.requestID,
            provenanceDigest: fixture.provenanceDigest,
            projectName: fixture.projectName, by: "HUMAN:fixture")
        require(grant.accepted, "REVOCATION_FIXTURE_GRANT_FAILED", into: &failures)
        controller.revokeLLMProposalConsent()
        let beforeRevokedUse = fixture.advanceEvents.count
        let revoked = await controller.resolveCrossObligation(
            requestID: fixture.requestID,
            provenanceDigest: fixture.provenanceDigest,
            projectName: fixture.projectName,
            path: .consentedLLMProposal,
            values: values, actor: "LLM:fixture",
            consentDigest: grant.consentDigest, resumeAfterAcceptance: false)
        require(!revoked.accepted && fixture.advanceEvents.count == beforeRevokedUse,
                "REVOKED_CONSENT_REACHED_ADVANCE", into: &failures)
    }

    private static func require(
        _ condition: @autoclosure () -> Bool, _ failure: String,
        into failures: inout [String]
    ) {
        if !condition() { failures.append(failure) }
    }
}
#endif

#if GARMENT_RESOLUTION_EVENT_BRIDGE_RUNTIME
@main
private struct GarmentResolutionEventBridgeRuntimeMain {
    @MainActor
    static func main() async {
        let failures = await GarmentResolutionEventBridgeRuntimeAudit.run()
        if failures.isEmpty {
            print("PASS persisted garment resolution event bridge")
            return
        }
        failures.forEach { print("FAIL \($0)") }
        exit(1)
    }
}
#elseif !GARMENT_RESOLUTION_EVENT_BRIDGE_STANDALONE
final class GarmentResolutionEventBridgeTests: XCTestCase {
    func testSourceBoundary() {
        XCTAssertEqual(GarmentResolutionEventBridgeSourceAudit.run().failures, [])
    }

    @MainActor
    func testPersistedEventsAndStaleRejection() async {
        XCTAssertEqual(await GarmentResolutionEventBridgeRuntimeAudit.run(), [])
    }
}
#else
@main
private struct GarmentResolutionEventBridgeSourceMain {
    static func main() {
        let failures = GarmentResolutionEventBridgeSourceAudit.run().failures
        if failures.isEmpty {
            print("PASS garment resolution source boundary")
            return
        }
        failures.forEach { print("FAIL \($0)") }
        exit(1)
    }
}
#endif
