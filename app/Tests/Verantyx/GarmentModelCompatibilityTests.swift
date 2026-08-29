import Foundation

#if !GARMENT_MODEL_COMPATIBILITY_STANDALONE
import XCTest
@testable import Verantyx
#endif

private enum GarmentModelCompatibilityAudit {
    static func failures() -> [String] {
        var failures: [String] = []
        func require(_ condition: Bool, _ code: String) {
            if !condition { failures.append(code) }
        }

        let qualified = GarmentModelCompatibility.profile(
            sourceName: "lmstudio:qwen/qwen3.6-35b-a3b")
        require(qualified.qualification == .qualified,
                "EXERCISED_PROVIDER_MODEL_PAIR_NOT_QUALIFIED")
        require(qualified.languageEnvelope && qualified.visionInput
                    && qualified.strictSchemaTransport,
                "QUALIFIED_PAIR_MISSING_REQUIRED_CAPABILITY")

        let unknownSibling = GarmentModelCompatibility.profile(
            sourceName: "lmstudio:qwen/qwen3.6-27b")
        require(unknownSibling.qualification == .probation,
                "MODEL_FAMILY_NAME_IMPROPERLY_GRANTS_QUALIFICATION")
        require(unknownSibling.boundedRepairAttempts == 1,
                "PROBATION_REPAIR_IS_NOT_BOUNDED_TO_ONE")

        let jgen = GarmentModelCompatibility.profile(
            sourceName: "jgen:any-future-model.jgen")
        require(jgen.qualification == .probation && !jgen.visionInput,
                "TEXT_ONLY_TRANSPORT_IMPROPERLY_CLAIMS_PIXEL_INPUT")

        let unsupported = GarmentModelCompatibility.profile(
            sourceName: "future-provider:any-model")
        require(unsupported.qualification == .unsupported
                    && !unsupported.languageEnvelope
                    && !unsupported.visionInput,
                "UNREGISTERED_TRANSPORT_DID_NOT_FAIL_CLOSED")

        let harness = GarmentModelCompatibility.harnessPrefix(
            sourceName: qualified.sourceName, operation: .visionStructure)
        for token in ["typed_schema", "closed_vocabulary", "PROPOSED_ONLY",
                      "OBSERVED", "manufacturing readiness"] {
            require(harness.contains(token),
                    "HARNESS_MINIMUM_GATE_MISSING_\(token)")
        }
        let repair = GarmentModelCompatibility.plannerRepairPrompt(
            sourceName: unknownSibling.sourceName,
            userRequest: "この画像から服を作って",
            rawResponse: "plain prose")
        require(repair.contains("NORMALIZATION_RETRY 1/1")
                    && repair.contains("Do not add measurements")
                    && repair.contains("CONVERSATION"),
                "NORMALIZATION_RETRY_CAN_CHANGE_INTENT_OR_REPEAT_UNBOUNDED")
        return failures
    }
}

#if !GARMENT_MODEL_COMPATIBILITY_STANDALONE
final class GarmentModelCompatibilityTests: XCTestCase {
    func testExternalModelHarnessProfilesAndBounds() {
        XCTAssertEqual(GarmentModelCompatibilityAudit.failures(), [])
    }
}
#else
@main
private struct GarmentModelCompatibilityMain {
    static func main() {
        let failures = GarmentModelCompatibilityAudit.failures()
        if failures.isEmpty {
            print("PASS garment external-model compatibility gate")
            exit(0)
        }
        failures.forEach { print("FAIL \($0)") }
        exit(1)
    }
}
#endif
