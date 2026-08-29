import Foundation

#if !ATELIER_IMAGE_REQUIREMENT_ENVELOPE_STANDALONE
import XCTest
#endif

private enum AtelierImageRequirementEnvelopeAudit {
    static func failures() -> [String] {
        let file = URL(fileURLWithPath: #filePath)
        let appRoot = file.deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let plannerURL = appRoot.appendingPathComponent(
            "Sources/Verantyx/Engine/AtelierGarmentRequestPlanner.swift")
        guard let planner = try? String(contentsOf: plannerURL, encoding: .utf8) else {
            return ["IMAGE_REQUIREMENT_ENVELOPE_SOURCE_UNREADABLE"]
        }

        var failures: [String] = []
        func require(_ condition: Bool, _ code: String) {
            if !condition { failures.append(code) }
        }

        let generateBlock = sourceBlock(
            in: planner, from: "case \"GENERATE_FROM_IMAGE\":",
            to: "case \"PROPOSE_STRUCTURE\":")
        let setBlock = sourceBlock(
            in: planner, from: "case \"SET_REQUIREMENTS\":",
            to: "default:")
        let validatorBlock = sourceBlock(
            in: planner, from: "private static func validatedRequirements(",
            to: "private static func stableID(")

        require(generateBlock.contains(
            "proposal.requirements, required: false,") &&
                generateBlock.contains("explicitUserRequest: request"),
            "IMAGE_GENERATION_BYPASSES_SHARED_REQUIREMENT_VALIDATOR")
        require(generateBlock.contains("requirements: requirements"),
            "IMAGE_REQUIREMENTS_ARE_DROPPED_FROM_COMMAND_IR")
        require(setBlock.contains(
            "proposal.requirements, required: true,") &&
                setBlock.contains("explicitUserRequest: request"),
            "SET_REQUIREMENTS_DOES_NOT_USE_SHARED_VALIDATOR")

        require(validatorBlock.contains("!proposed.isEmpty") &&
                validatorBlock.contains("proposed.count <= 24"),
            "REQUIREMENT_COUNT_BOUNDARY_IS_MISSING")
        require(validatorBlock.contains("Requirement.Kind(") &&
                validatorBlock.contains("UNKNOWN_REQUIREMENT_KIND"),
            "REQUIREMENT_KIND_IS_NOT_CLOSED")
        require(validatorBlock.contains("value.isFinite, unit != nil") &&
                validatorBlock.contains("UNKNOWN_DIMENSION_UNIT_REQUIRED"),
            "UNITLESS_NUMERIC_REQUIREMENT_IS_NOT_REJECTED")
        require(validatorBlock.contains("containsExplicitDimension(") &&
                validatorBlock.contains("explicitUserRequest") &&
                validatorBlock.contains("UNKNOWN_MEASUREMENT_NOT_EXPLICIT"),
            "MODEL_CAN_INVENT_MEASUREMENTS_NOT_PRESENT_IN_USER_TEXT")
        require(validatorBlock.contains("precomposedStringWithCompatibilityMapping") &&
                validatorBlock.contains("let proposedMetres = metres") &&
                validatorBlock.contains("let explicitMetres = metres"),
            "EXPLICIT_DIMENSION_PROVENANCE_HAS_NO_UNIT_NORMALIZATION")
        require(validatorBlock.contains("item.unit != nil") &&
                validatorBlock.contains("UNKNOWN_DIMENSION_VALUE_REQUIRED"),
            "VALUELESS_UNIT_IS_NOT_REJECTED")
        require(validatorBlock.contains("valueOrText(value:") &&
                validatorBlock.contains("UNKNOWN_REQUIREMENT_VALUE"),
            "EMPTY_REQUIREMENT_IS_NOT_REJECTED")

        require(planner.contains(
            "\"kind\":\"STANDARD_SIZE\",\"target\":\"wearer_size\"") &&
                planner.contains("\"text\":\"M\",\"value\":null"),
            "STANDARD_SIZE_TEXT_EXAMPLE_IS_MISSING")
        require(planner.contains("only when the user explicitly supplied them") &&
                planner.contains("never infer measurements") &&
                planner.contains("do not flatten them into `reason`"),
            "MODEL_MAY_INVENT_OR_FLATTEN_IMAGE_REQUIREMENTS")
        require(planner.contains("waist 72 cm is BODY_MEASUREMENT") &&
                planner.contains("ease 4 cm is EASE"),
            "MULTIPLE_IMAGE_REQUIREMENT_PROMPT_IS_MISSING")
        require(planner.contains("responseFormat: plannerResponseFormat") &&
                planner.contains("\"type\": \"json_schema\"") &&
                planner.contains("\"name\": \"atelier_garment_turn\"") &&
                planner.contains("\"additionalProperties\": false") &&
                planner.contains("\"required\": [\"speech\", \"command\"]"),
            "LM_STUDIO_PLANNER_HAS_NO_TYPED_OUTPUT_SCHEMA")
        return failures
    }

    private static func sourceBlock(
        in source: String, from startMarker: String, to endMarker: String
    ) -> String {
        guard let start = source.range(of: startMarker),
              let end = source.range(of: endMarker, range: start.upperBound..<source.endIndex)
        else { return "" }
        return String(source[start.lowerBound..<end.lowerBound])
    }
}

#if !ATELIER_IMAGE_REQUIREMENT_ENVELOPE_STANDALONE
final class AtelierImageRequirementEnvelopeAuditTests: XCTestCase {
    func testImageGenerationPreservesStrictTypedRequirements() {
        XCTAssertEqual(AtelierImageRequirementEnvelopeAudit.failures(), [])
    }
}
#else
@main
private struct AtelierImageRequirementEnvelopeAuditRunner {
    static func main() {
        let failures = AtelierImageRequirementEnvelopeAudit.failures()
        if failures.isEmpty {
            print("PASS Atelier image + typed requirement envelope invariants")
            exit(0)
        }
        failures.forEach { print("FAIL \($0)") }
        exit(1)
    }
}
#endif
