import Foundation

#if !ATELIER_DUAL_AUDIT_MODE_STANDALONE
import XCTest
#endif

private enum AtelierDualAuditModeBridgeAudit {
    static func failures() -> [String] {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent()
        let controllerURL = root.appendingPathComponent(
            "Sources/Verantyx/Engine/GarmentFactoryReactController.swift")
        let flowURL = root.appendingPathComponent(
            "Sources/Verantyx/Views/AtelierDynamicFlowView.swift")
        guard let controller = try? String(
                contentsOf: controllerURL, encoding: .utf8),
              let flow = try? String(contentsOf: flowURL, encoding: .utf8)
        else { return ["DUAL_AUDIT_MODE_SOURCE_UNREADABLE"] }
        var failures: [String] = []
        func require(_ value: @autoclosure () -> Bool, _ code: String) {
            if !value() { failures.append(code) }
        }

        require(controller.contains("enum InitialAuditMode") &&
                controller.contains("case humanAudit = \"HUMAN_AUDIT\"") &&
                controller.contains("case autoProposed = \"AUTO_PROPOSED\""),
                "APP_HAS_NO_TYPED_HUMAN_AND_AUTO_MODES")
        require(controller.contains("activeAuditMode = selectedAuditMode") &&
                controller.contains("\"audit_mode\": activeAuditMode.rawValue") &&
                controller.contains("activeAuditMode == .humanAudit"),
                "SELECTED_MODE_DOES_NOT_REACH_PERSISTED_HARNESS")
        require(controller.contains("AUTO_ACCEPTED_FOR_PREVIEW") &&
                controller.contains("\"foreground_cleanup\"") &&
                controller.contains("OPEN_RETRIEVAL_AFTER_FRONT_REVIEW") &&
                controller.contains("fact_promotions\": 0"),
                "AUTO_MODE_CANNOT_REACH_BOUND_PREVIEW_WITHOUT_FACT_PROMOTION")
        require(controller.contains("manufacturing_ready\": false") &&
                controller.contains("manufacturing_certified\": false") &&
                controller.contains("rear_hidden_observed\": false"),
                "AUTO_MODE_CAN_ESCAPE_PREVIEW_AUTHORITY_CEILING")
        require(controller.contains("targetCleanupAuthority") &&
                controller.contains("front_authority") &&
                controller.contains("HUMAN_APPROVED_FOR_FRONT_COMPARISON"),
                "FRONT_TARGET_AUTHORITY_IS_NOT_EXPLICIT")
        require(flow.contains("atelier.initial-audit-mode") &&
                flow.contains("selectedAuditMode.title") &&
                flow.contains("activeAuditMode.rawValue") &&
                flow.contains("次の画像から適用"),
                "CHAT_FIRST_UI_HAS_NO_AUDIT_MODE_CONTROL")
        return failures
    }
}

#if !ATELIER_DUAL_AUDIT_MODE_STANDALONE
final class AtelierDualAuditModeBridgeAuditTests: XCTestCase {
    func testHumanAndAutoProposedModesShareOneBoundedHarness() {
        XCTAssertEqual(AtelierDualAuditModeBridgeAudit.failures(), [])
    }
}
#else
@main
private enum AtelierDualAuditModeBridgeAuditMain {
    static func main() {
        let failures = AtelierDualAuditModeBridgeAudit.failures()
        if failures.isEmpty {
            print("PASS Atelier human/auto proposed audit mode bridge")
            exit(0)
        }
        failures.forEach { print("FAIL \($0)") }
        exit(1)
    }
}
#endif
