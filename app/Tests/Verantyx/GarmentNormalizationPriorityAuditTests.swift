import Foundation

#if !GARMENT_NORMALIZATION_PRIORITY_STANDALONE
import XCTest
#endif

/// Source-level regression contract for boundaries that are intentionally
/// private or implemented by the bundled Python compiler.
///
/// The audit is standalone so it can run without changing the application
/// target or exposing production helpers merely for tests.
private enum GarmentNormalizationPriorityAudit {
    private static var repositoryRoot: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent() // Verantyx
            .deletingLastPathComponent() // Tests
            .deletingLastPathComponent() // app
            .deletingLastPathComponent() // repository
    }

    private static func read(_ relativePath: String) -> String? {
        try? String(
            contentsOf: repositoryRoot.appendingPathComponent(relativePath),
            encoding: .utf8)
    }

    private static func section(
        _ source: String, from startMarker: String, until endMarker: String
    ) -> String? {
        guard let start = source.range(of: startMarker),
              let end = source.range(
                of: endMarker, range: start.upperBound..<source.endIndex)
        else { return nil }
        return String(source[start.lowerBound..<end.lowerBound])
    }

    private static func compactWhitespace(_ source: String) -> String {
        source.split(whereSeparator: { $0.isWhitespace })
            .joined(separator: " ")
    }

    static func failures() -> [String] {
        var failures: [String] = []
        failures.append(contentsOf: trouserPairFailures())
        failures.append(contentsOf: modelCapabilityFailures())
        failures.append(contentsOf: layeredBodySleeveFailures())
        return failures
    }

    private static func trouserPairFailures() -> [String] {
        guard let source = read(
            "app/Sources/Verantyx/Engine/GarmentFactoryReactController.swift")
        else { return ["TROUSER_CONTROLLER_SOURCE_UNREADABLE"] }
        guard let function = section(
            source,
            from: "private static func normalizeMergedVisionTrouserPairs(",
            until: "private static func expandSingleVisibleVisionCandidate(")
        else { return ["MERGED_TROUSER_PAIR_NORMALIZER_MISSING"] }

        var failures: [String] = []
        func require(_ condition: Bool, _ code: String) {
            if !condition { failures.append(code) }
        }
        let compact = compactWhitespace(function)
        require(compact.contains(
            #"guard node["kind"] as? String == "TUBE", explicitVisionSide(node) == nil,"#),
            "EXPLICIT_SIDE_TUBE_CAN_ENTER_PAIR_EXPANSION")

        guard let markerStart = function.range(of: "let explicitPairMarker"),
              let markerEnd = function.range(
                of: "guard explicitPairMarker else",
                range: markerStart.upperBound..<function.endIndex)
        else {
            failures.append("EXPLICIT_PAIR_MARKER_GATE_MISSING")
            return failures
        }
        let markerClause = String(
            function[markerStart.lowerBound..<markerEnd.lowerBound])
        let compactMarker = compactWhitespace(markerClause)
        require(compactMarker.contains("let explicitPairMarker = quantity == 2"),
                "QUANTITY_TWO_NO_LONGER_EXPLICITLY_GATES_PAIR_EXPANSION")
        require(compactMarker.contains(
            #"["bilateral", "both", "pair", "paired"].contains(rawSide ?? "")"#),
            "EXPLICIT_PAIR_SIDE_VOCABULARY_DRIFTED")
        require(compactMarker.contains(
            #"["trousers", "pants", "leggings", "leg pair", "both legs", "two legs"].contains(where: semanticText.contains)"#),
            "EXPLICIT_PLURAL_TROUSER_VOCABULARY_DRIFTED")
        require(!compactMarker.contains(#""trouser_leg""#)
                    && !compactMarker.contains(#""trouser leg""#)
                    && !compactMarker.contains(#""leg""#),
                "SINGULAR_SIDELESS_LEG_CAN_TRIGGER_PAIR_EXPANSION")
        require(compact.contains(
            "guard explicitPairMarker else { output.append(node) continue }"),
            "SIDELESS_SINGULAR_TUBE_IS_NOT_PRESERVED_UNEXPANDED")
        require(compact.contains(
            #"expandedAttributes["pair_expansion_state"] = "PROPOSED_NORMALIZATION""#)
                    && compact.contains(
                        #""state": "PROPOSED_NORMALIZATION""#)
                    && compact.contains(
                        #""not_observed_as_separate_sides": true"#),
                "TROUSER_PAIR_EXPANSION_LOST_PROPOSED_NORMALIZATION_PROVENANCE")
        require(compact.contains("var expanded = node")
                    && !compact.contains(#"expanded["dimensions"]"#)
                    && compact.contains(#""dimensions_changed": false"#),
                "TROUSER_PAIR_EXPANSION_CAN_INVENT_OR_MUTATE_DIMENSIONS")
        return failures
    }

    private static func modelCapabilityFailures() -> [String] {
        guard let source = read(
            "app/Sources/Verantyx/Engine/GarmentModelCompatibility.swift")
        else { return ["MODEL_COMPATIBILITY_SOURCE_UNREADABLE"] }
        var failures: [String] = []
        func require(_ condition: Bool, _ code: String) {
            if !condition { failures.append(code) }
        }
        guard let allowList = section(
            source, from: "private static let qualifiedSignatures",
            until: "static func profile(sourceName raw: String)")
        else { return ["EXACT_MODEL_ALLOW_LIST_MISSING"] }
        let qualifiedLMStudioEntries = allowList.components(
            separatedBy: "lmstudio:").count - 1
        require(allowList.contains("lmstudio:qwen/qwen3.6-35b-a3b")
                    && qualifiedLMStudioEntries == 1,
                "MODEL_FAMILY_OR_UNTESTED_SIBLING_BECAME_QUALIFIED")
        require(source.contains("if qualifiedSignatures.contains(normalized)")
                    && source.contains("qualification: .qualified")
                    && source.contains("qualification: .probation")
                    && source.contains("boundedRepairAttempts: 1"),
                "EXTERNAL_MODEL_CAPABILITY_GATE_OR_BOUNDED_REPAIR_MISSING")
        require(source.contains(
            "minimum_gate=typed_schema+closed_vocabulary+provenance+deterministic_validation")
                    && source.contains("authority=PROPOSED_ONLY")
                    && source.contains("NORMALIZATION_RETRY 1/1"),
                "VERA_EXTERNAL_MODEL_HARNESS_AUTHORITY_BOUNDARY_MISSING")
        return failures
    }

    private static func layeredBodySleeveFailures() -> [String] {
        guard let source = read("photoloset/structure_to_pattern.py")
        else { return ["STRUCTURE_TO_PATTERN_SOURCE_UNREADABLE"] }
        guard let selector = section(
            source, from: "def _select_bodice_for_sleeves(",
            until: "def _sleeve_port(")
        else { return ["LAYERED_BODY_SLEEVE_SELECTOR_MISSING"] }
        var failures: [String] = []
        func require(_ condition: Bool, _ code: String) {
            if !condition { failures.append(code) }
        }
        let compact = compactWhitespace(selector)
        require(compact.contains("body_by_id =")
                    && compact.contains("body_parents =")
                    && compact.contains("if len(explicit_body_ids) == 1:"),
                "EXPLICIT_BODY_SLEEVE_PARENT_SELECTION_MISSING")
        require(selector.contains(
            "UNKNOWN_BODICE_SLEEVE_BODY_PARENT_AMBIGUOUS")
                    && selector.contains(
                        "UNKNOWN_BODICE_SLEEVE_BODY_PARENT_UNKNOWN"),
                "LAYERED_BODY_SLEEVE_PARENT_FAILURES_NO_LONGER_FAIL_CLOSED")
        require(selector.contains(
            "UNKNOWN_BODICE_SLEEVE_GARMENT_UNIT_MISMATCH")
                    && selector.contains(
                        "UNKNOWN_BODICE_SLEEVE_BODY_LAYER_MISMATCH"),
                "EXPLICIT_BODY_SLEEVE_UNIT_OR_LAYER_GATE_MISSING")
        require(compact.contains(
            "if int(body.get(\"layer\", 0)) == layer")
                    && compact.contains("eligible &= matches")
                    && compact.contains("if len(eligible) == 1:"),
                "IMPLICIT_LAYERED_BODY_SELECTION_IS_NOT_EXACT_UNIT_LAYER_INTERSECTION")
        require(selector.contains(
            #"required_address_fields=["attached_to", "garment_unit", "layer"]"#),
                "AMBIGUOUS_LAYERED_BODY_SLEEVE_ADDRESS_REQUIREMENTS_MISSING")
        return failures
    }
}

#if !GARMENT_NORMALIZATION_PRIORITY_STANDALONE
final class GarmentNormalizationPriorityAuditTests: XCTestCase {
    func testTrouserPairModelGateAndLayeredBodySleeveContracts() {
        XCTAssertEqual(GarmentNormalizationPriorityAudit.failures(), [])
    }
}
#else
@main
private struct GarmentNormalizationPriorityStandaloneMain {
    static func main() {
        let failures = GarmentNormalizationPriorityAudit.failures()
        if failures.isEmpty {
            print("PASS garment normalization priority source audit")
            exit(0)
        }
        failures.forEach { print("FAIL \($0)") }
        exit(1)
    }
}
#endif
