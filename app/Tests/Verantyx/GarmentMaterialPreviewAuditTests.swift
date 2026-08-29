import Foundation

#if !GARMENT_MATERIAL_PREVIEW_STANDALONE
import XCTest
@testable import Verantyx
#endif

/// Narrow source-boundary audit for material preview and bounded ITERATE
/// continuation. The app test target is not enabled in every local build, so
/// the same checks remain executable with swiftc in CI or from the terminal.
private enum GarmentMaterialPreviewAudit {
    static func failures() -> [String] {
        let file = URL(fileURLWithPath: #filePath)
        let appRoot = file.deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let controllerURL = appRoot.appendingPathComponent(
            "Sources/Verantyx/Engine/GarmentFactoryReactController.swift")
        guard let source = try? String(contentsOf: controllerURL, encoding: .utf8)
        else { return ["MATERIAL_PREVIEW_CONTROLLER_UNREADABLE"] }

        var failures: [String] = []
        func require(_ condition: @autoclosure () -> Bool, _ code: String) {
            if !condition() { failures.append(code) }
        }

        require(source.contains("materialCandidatePayloads") &&
                source.contains("payload[\"digest\"] as? String == candidate.digest"),
                "MATERIAL_PREVIEW_IS_NOT_BOUND_TO_CURRENT_CANDIDATE_DIGEST")
        require(source.contains("return await previewMaterial(candidate)"),
                "LEGACY_PREVIEW_ENTRY_DOES_NOT_DISPATCH_MATERIAL_DOMAIN")

        if let body = functionBody(in: source, named: "previewMaterial") {
            require(body.contains("industrial_cloth_simulate"),
                    "MATERIAL_PREVIEW_HAS_NO_TYPED_SIMULATION")
            require(body.contains("materialPreviewBasePattern") &&
                    body.contains("materialPreviewBaseArtifact") &&
                    body.contains("\"structure_fixed\": true") &&
                    body.contains("\"flat_pattern_fixed\": true") &&
                    body.contains("\"rest_mesh_fixed\": true"),
                    "MATERIAL_PREVIEW_DOES_NOT_FREEZE_APPROVED_ARTIFACTS")
            require(body.contains("\"authority\": \"PROPOSED\"") &&
                    body.contains("\"observed\": false") &&
                    body.contains("\"manufacturing_ready\": false") &&
                    body.contains("\"manufacturing_certified\": false"),
                    "MATERIAL_PREVIEW_CROSSES_AUTHORITY_BOUNDARY")
            require(body.contains("PROPOSED_NOT_MEASURED") &&
                    body.contains("candidate_payload_digest") &&
                    body.contains("range_resolution"),
                    "MATERIAL_PREVIEW_DROPS_PARAMETER_PROVENANCE")
            require(body.contains("REVIEW_MATERIAL_SIMULATION_COMPARISON_UNAVAILABLE") &&
                    body.contains("REVIEW_MATERIAL_PARAMETERS_OR_FIXED_MESH_REQUIRED"),
                    "MATERIAL_PREVIEW_FAILURE_IS_NOT_TYPED_REVIEW")
            require(!body.contains("garment_structure_preview") &&
                    !body.contains("garment_structure_pattern"),
                    "MATERIAL_PREVIEW_STILL_CALLS_STRUCTURE_COMPILER")
        } else {
            failures.append("MATERIAL_PREVIEW_FUNCTION_MISSING")
        }

        require(source.contains("basePattern: materialPreviewBasePattern ?? rawPreviewPattern") &&
                source.contains("baseArtifact: materialPreviewBaseArtifact ?? previewArtifact"),
                "ADOPTED_MATERIAL_CANNOT_REUSE_APPROVED_SIMULATION_BASE")
        require(source.contains("if eventType == \"ITERATE\", verdict == \"CONTINUE\"") &&
                source.contains("phase == \"ITERATING\", nextPhase == phase") &&
                source.contains("guard nextPhase != phase else"),
                "BOUNDED_ITERATE_CONTINUE_EXCEPTION_MISSING")
        require(ordered([
            "if eventType == \"ITERATE\", verdict == \"CONTINUE\"",
            "guard nextPhase != phase else",
        ], in: source), "GENERIC_NO_PROGRESS_GATE_PRECEDES_ITERATE_EXCEPTION")

        require(source.contains("requestedNotMeasuredItems(from: profile.requirements)") &&
                source.contains("row[\"state\"] = \"REQUESTED_NOT_MEASURED\"") &&
                source.contains("row[\"authority\"] = \"REQUESTED_NOT_MEASURED\"") &&
                source.contains("row[\"not_measured_from_image\"] = true") &&
                source.contains("uniqueRequirementItems"),
                "SUCCESSFUL_REQUEST_VALUES_ARE_NOT_EXPOSED_AS_REQUESTED_NOT_MEASURED")
        return failures
    }

    private static func functionBody(in source: String, named name: String) -> String? {
        guard let signature = source.range(of: "func \(name)("),
              let open = source[signature.upperBound...].firstIndex(of: "{") else {
            return nil
        }
        var depth = 0
        var cursor = open
        var quoted = false
        var escaped = false
        while cursor < source.endIndex {
            let character = source[cursor]
            if quoted {
                if escaped { escaped = false }
                else if character == "\\" { escaped = true }
                else if character == "\"" { quoted = false }
            } else if character == "\"" {
                quoted = true
            } else if character == "{" {
                depth += 1
            } else if character == "}" {
                depth -= 1
                if depth == 0 { return String(source[open...cursor]) }
            }
            cursor = source.index(after: cursor)
        }
        return nil
    }

    private static func ordered(_ needles: [String], in haystack: String) -> Bool {
        var cursor = haystack.startIndex
        for needle in needles {
            guard let range = haystack.range(
                of: needle, range: cursor..<haystack.endIndex) else { return false }
            cursor = range.upperBound
        }
        return true
    }
}

#if !GARMENT_MATERIAL_PREVIEW_STANDALONE
final class GarmentMaterialPreviewAuditTests: XCTestCase {
    func testMaterialPreviewAndBoundedIterationContract() {
        XCTAssertEqual(GarmentMaterialPreviewAudit.failures(), [])
    }
}
#else
@main
private enum GarmentMaterialPreviewAuditMain {
    static func main() {
        let failures = GarmentMaterialPreviewAudit.failures()
        if failures.isEmpty {
            print("PASS material preview, requested values, and bounded ITERATE continuation")
        } else {
            failures.forEach { print("FAIL \($0)") }
            exit(1)
        }
    }
}
#endif
