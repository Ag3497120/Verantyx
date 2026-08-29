import Foundation

#if !GARMENT_AUTOMATIC_CANDIDATE_SELECTION_STANDALONE
import XCTest
#endif

#if GARMENT_AUTOMATIC_CANDIDATE_SELECTION_RUNTIME || !GARMENT_AUTOMATIC_CANDIDATE_SELECTION_STANDALONE
import AppKit
import SwiftUI
#endif

private enum GarmentAutomaticCandidateSelectionSourceAudit {
    struct Report { var failures: [String] = [] }

    static func run() -> Report {
        var report = Report()
        let sourceURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Sources/Verantyx/Views/GarmentRegionPickerView.swift")
        guard let source = try? String(contentsOf: sourceURL, encoding: .utf8) else {
            report.failures.append("GARMENT_REGION_PICKER_SOURCE_UNREADABLE")
            return report
        }

        require(source.contains("automaticCandidatePicker") &&
                source.contains("selectAutomaticCandidate(candidate.candidateID)") &&
                source.contains("Use selected proposal & run"),
                "AUTOMATIC_CANDIDATE_SELECTION_UI_MISSING", into: &report)
        require(source.contains("selectedAutomaticCandidateID") &&
                source.contains("automaticSelectionWasUserInitiated") &&
                source.contains("selectedAutomaticGeometry"),
                "AUTOMATIC_SELECTION_STATE_IS_NOT_EXPLICIT", into: &report)
        require(source.contains("drawAutomaticGeometry") &&
                source.contains("geometry.internalBoundaries") &&
                source.contains("geometry.internalLines"),
                "SELECTED_GEOMETRY_IS_NOT_DRAWN_AS_ONE_UNIT", into: &report)
        require(source.contains("selectedCandidateID: selectedAutomaticCandidateID") &&
                source.contains("selectedByUser: true") &&
                source.contains("USER_SELECTED_PROPOSAL"),
                "USER_SELECTION_IS_NOT_TRANSPORTED_TO_PAYLOAD", into: &report)
        require(source.contains("automaticCandidateGeometry") &&
                source.contains("selectedGeometry?.outline") &&
                source.contains("selectedGeometry?.internalBoundaries") &&
                source.contains("selectedGeometry?.internalLines"),
                "DRAW_AND_PAYLOAD_GEOMETRY_ROUTES_CAN_DIVERGE", into: &report)
        require(source.contains("RegionPicker.PixelPoint(x: $0.maxX, y: y)") &&
                !source.contains("RegionPicker.PixelPoint(x: $0.maxX, y: y + 1)"),
                "AUTOMATIC_ENVELOPE_RIGHT_CHAIN_IS_NOT_Y_MONOTONE", into: &report)
        require(source.contains("candidate_id") && source.contains("score") &&
                source.contains("reasons") && source.contains("geometry_digest") &&
                source.contains("FNV-1a-64"),
                "DETERMINISTIC_CANDIDATE_EVIDENCE_INCOMPLETE", into: &report)
        require(source.contains("\"state\": \"PROPOSED\"") &&
                source.contains("does_not_observe") &&
                source.contains("garment_structure") && source.contains("back") &&
                source.contains("seams") && source.contains("layers") &&
                source.contains("material"),
                "AUTOMATIC_SELECTION_AUTHORITY_BOUNDARY_MISSING", into: &report)
        require(source.contains("automaticCandidates = []") &&
                source.contains("selectedAutomaticCandidateID = nil") &&
                source.contains("automaticSelectionWasUserInitiated = false"),
                "REATTACH_DOES_NOT_RESET_CANDIDATE_SELECTION", into: &report)
        require(!source.contains("candidateID == \"dress") &&
                !source.contains("candidateID == \"shirt") &&
                !source.contains("candidateID == \"anime"),
                "GARMENT_NAME_HARDCODE_FOUND_IN_SELECTION", into: &report)
        return report
    }

    private static func require(_ condition: @autoclosure () -> Bool,
                                _ failure: String,
                                into report: inout Report) {
        if !condition() { report.failures.append(failure) }
    }
}

#if GARMENT_AUTOMATIC_CANDIDATE_SELECTION_RUNTIME
@MainActor
final class AppState: ObservableObject {
    func t(_ english: String, _ japanese: String) -> String { english }
}

enum Theme {
    static let fg = Color.white
    static let dim = Color.gray
    static let faint = Color.gray.opacity(0.8)
    static let bad = Color.red
    static let panel = Color.black
    static let sel = Color.blue
}

enum GarmentOutline {
    static let outlineDegenerate = "UNKNOWN_OUTLINE_DEGENERATE"
}

private enum GarmentAutomaticCandidateSelectionRuntimeAudit {
    struct Report { var failures: [String] = [] }

    static func run() -> Report {
        var report = Report()
        do {
            let fixture = try syntheticFixture()
            let firstRanking = GarmentOutline.rankAutomaticClothingCandidates(from: fixture)
            let repeatedRanking = GarmentOutline.rankAutomaticClothingCandidates(from: fixture)
            require(firstRanking == repeatedRanking,
                    "SAME_IMAGE_CHANGED_CANDIDATE_ORDER", into: &report)
            guard firstRanking.count >= 2 else {
                report.failures.append("FIXTURE_DID_NOT_PRODUCE_COMPARABLE_CANDIDATES")
                return report
            }

            let first = firstRanking[0]
            let second = firstRanking[1]
            guard let firstGeometry = GarmentOutline.automaticCandidateGeometry(
                        first, in: fixture, sourceImage: nil),
                  let secondGeometry = GarmentOutline.automaticCandidateGeometry(
                        second, in: fixture, sourceImage: nil) else {
                report.failures.append("CANDIDATE_GEOMETRY_MISSING")
                return report
            }
            require(firstGeometry.geometryDigest != secondGeometry.geometryDigest,
                    "ALTERNATIVE_CANDIDATES_SHARE_GEOMETRY_DIGEST", into: &report)
            require(isSimpleYMonotoneEnvelope(firstGeometry.outline) &&
                    isSimpleYMonotoneEnvelope(secondGeometry.outline),
                    "AUTOMATIC_MULTI_COMPONENT_OUTLINE_SELF_INTERSECTS", into: &report)

            let defaultPayload = GarmentOutline.extractProposedClothing(
                from: fixture, probes: [], imagePath: "fixture://candidate-selection",
                rankedCandidates: firstRanking, sourceImage: nil)
            require(selectionState(defaultPayload) == "PROPOSED_DEFAULT",
                    "DEFAULT_PREVIEW_WAS_RECORDED_AS_USER_SELECTION", into: &report)

            let secondPayload = GarmentOutline.extractProposedClothing(
                from: fixture, probes: [], imagePath: "fixture://candidate-selection",
                rankedCandidates: firstRanking,
                selectedCandidateID: second.candidateID,
                selectedByUser: true, sourceImage: nil)
            require((secondPayload["selected_clothing_mask_candidate_id"] as? String)
                    == second.candidateID,
                    "SELECTED_CANDIDATE_ID_NOT_SWITCHED", into: &report)
            require(selectionState(secondPayload) == "USER_SELECTED_PROPOSAL",
                    "USER_SELECTION_FACT_NOT_RECORDED", into: &report)
            require((secondPayload["selected_clothing_mask_geometry_digest"] as? String)
                    == secondGeometry.geometryDigest,
                    "SELECTED_PAYLOAD_DIGEST_DOES_NOT_MATCH_DRAW_GEOMETRY", into: &report)
            require(payloadPoints(secondPayload, key: "outline") == secondGeometry.outline,
                    "SELECTED_OUTLINE_DID_NOT_SWITCH", into: &report)
            require(payloadNestedPointCount(secondPayload, key: "internal_boundaries")
                    == secondGeometry.internalBoundaries.reduce(0) { $0 + $1.count },
                    "SELECTED_INTERNAL_BOUNDARIES_DID_NOT_SWITCH", into: &report)
            require(payloadNestedPointCount(secondPayload, key: "internal_lines")
                    == secondGeometry.internalLines.reduce(0) { $0 + $1.count },
                    "SELECTED_INTERNAL_LINES_DID_NOT_SWITCH", into: &report)

            let evidence = secondPayload["clothing_mask_candidates"] as? [[String: Any]] ?? []
            require(evidence.count == firstRanking.count && evidence.allSatisfy {
                ($0["state"] as? String) == "PROPOSED" &&
                $0["candidate_id"] is String && $0["score"] is Double &&
                $0["reasons"] is [String] && $0["geometry_digest"] is String
            }, "CANDIDATE_EVIDENCE_MISSING_OR_PROMOTED", into: &report)
            let regions = secondPayload["regions"] as? [[String: Any]] ?? []
            require(!regions.isEmpty && regions.allSatisfy { ($0["state"] as? String) == "PROPOSED" },
                    "SELECTED_MASK_REGION_BECAME_OBSERVED", into: &report)

            let reselectedPayload = GarmentOutline.extractProposedClothing(
                from: fixture, probes: [], imagePath: "fixture://candidate-selection",
                rankedCandidates: repeatedRanking,
                selectedCandidateID: first.candidateID,
                selectedByUser: true, sourceImage: nil)
            require((reselectedPayload["selected_clothing_mask_geometry_digest"] as? String)
                    == firstGeometry.geometryDigest,
                    "RESELECTION_DID_NOT_RESTORE_FIRST_GEOMETRY", into: &report)
        } catch {
            report.failures.append("RUNTIME_FIXTURE_FAILED: \(error)")
        }
        return report
    }

    private static func selectionState(_ payload: [String: Any]) -> String? {
        (payload["automatic_candidate_selection"] as? [String: Any])?["state"] as? String
    }

    private static func payloadPoints(
        _ payload: [String: Any], key: String
    ) -> [RegionPicker.PixelPoint] {
        (payload[key] as? [[Double]] ?? []).compactMap {
            guard $0.count == 2 else { return nil }
            return RegionPicker.PixelPoint(x: Int($0[0]), y: Int($0[1]))
        }
    }

    private static func payloadNestedPointCount(_ payload: [String: Any], key: String) -> Int {
        (payload[key] as? [[[Double]]] ?? []).reduce(0) { $0 + $1.count }
    }

    /// `horizontalEnvelope` is formed by one ascending left chain followed by
    /// one descending right chain.  Equal row sets and a strictly positive
    /// span are the invariant which prevents the automatic multi-component
    /// outline from reaching Python as a bow-tie polygon.
    private static func isSimpleYMonotoneEnvelope(
        _ points: [RegionPicker.PixelPoint]
    ) -> Bool {
        guard points.count >= 6, points.count.isMultiple(of: 2) else { return false }
        let half = points.count / 2
        let left = Array(points[..<half])
        let right = Array(points[half...].reversed())
        guard left.count == right.count else { return false }
        for index in left.indices {
            if index > 0 && left[index - 1].y >= left[index].y { return false }
            if left[index].y != right[index].y || left[index].x >= right[index].x {
                return false
            }
        }
        return true
    }

    private static func syntheticFixture() throws -> RegionPicker.Result {
        let width = 120, height = 160
        var rgba = [UInt8](repeating: 0, count: width * height * 4)
        fill(&rgba, width: width, x: 0...119, y: 0...159, color: (232, 232, 232, 255))
        fill(&rgba, width: width, x: 53...66, y: 5...42, color: (80, 42, 30, 255))
        fill(&rgba, width: width, x: 34...85, y: 47...86, color: (24, 62, 142, 255))
        fill(&rgba, width: width, x: 27...92, y: 89...146, color: (28, 116, 72, 255))
        fill(&rgba, width: width, x: 98...102, y: 55...105, color: (174, 112, 18, 255))
        return try RegionPicker.pickRegions(
            rgba8: rgba, width: width, height: height, seeds: [], options: .photo)
    }

    private static func fill(_ rgba: inout [UInt8], width: Int,
                             x: ClosedRange<Int>, y: ClosedRange<Int>,
                             color: (UInt8, UInt8, UInt8, UInt8)) {
        for row in y { for column in x {
            let offset = (row * width + column) * 4
            rgba[offset] = color.0; rgba[offset + 1] = color.1
            rgba[offset + 2] = color.2; rgba[offset + 3] = color.3
        }}
    }

    private static func require(_ condition: @autoclosure () -> Bool,
                                _ failure: String,
                                into report: inout Report) {
        if !condition() { report.failures.append(failure) }
    }
}
#endif

#if !GARMENT_AUTOMATIC_CANDIDATE_SELECTION_STANDALONE
final class GarmentAutomaticCandidateSelectionAuditTests: XCTestCase {
    func testCandidateSelectionSourceContract() {
        XCTAssertEqual(GarmentAutomaticCandidateSelectionSourceAudit.run().failures, [])
    }
}
#else
@main
private enum GarmentAutomaticCandidateSelectionAuditMain {
    static func main() {
        var failures = GarmentAutomaticCandidateSelectionSourceAudit.run().failures
#if GARMENT_AUTOMATIC_CANDIDATE_SELECTION_RUNTIME
        failures += GarmentAutomaticCandidateSelectionRuntimeAudit.run().failures
#endif
        if failures.isEmpty {
            print("PASS automatic clothing candidate selection source/runtime audit")
        } else {
            failures.forEach { print("FAIL \($0)") }
            exit(1)
        }
    }
}
#endif
