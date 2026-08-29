import Foundation

#if !GARMENT_AUTOMATIC_PROPOSAL_STANDALONE
import XCTest
#endif

#if GARMENT_AUTOMATIC_PROPOSAL_RUNTIME || !GARMENT_AUTOMATIC_PROPOSAL_STANDALONE
import AppKit
import SwiftUI
#endif

/// Guards the beginner image route against returning to five fixed clothing
/// seeds.  The source audit can run without an app test target; the runtime
/// audit below compiles the production RegionPicker and proposal code against
/// a deterministic synthetic image.
private enum GarmentAutomaticProposalSourceAudit {
    struct Report { var failures: [String] = [] }

    static func run() -> Report {
        var report = Report()
        let testFile = URL(fileURLWithPath: #filePath)
        let sourceURL = testFile.deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Sources/Verantyx/Views/GarmentRegionPickerView.swift")
        guard let raw = try? String(contentsOf: sourceURL, encoding: .utf8) else {
            report.failures.append("GARMENT_REGION_PICKER_SOURCE_UNREADABLE")
            return report
        }
        let source = executableSource(raw)
        guard let route = functionBody(in: source, named: "automaticClothingProposal"),
              let ranker = functionBody(in: source, named: "rankAutomaticClothingCandidates"),
              let assessment = functionBody(in: source, named: "automaticComponentAssessment"),
              let proposed = functionBody(in: source, named: "extractProposedClothing"),
              let confirmed = functionBody(in: source, named: "extractConfirmedClothing")
        else {
            report.failures.append("AUTOMATIC_COMPONENT_RANKING_FUNCTION_MISSING")
            return report
        }

        require(route.contains("analyze(image, seeds: [])") &&
                route.contains("rankAutomaticClothingCandidates(from: result)") &&
                route.contains("rankedCandidates: candidates"),
                "BEGINNER_ROUTE_DOES_NOT_USE_SEEDLESS_RANKED_COMPONENTS", into: &report)
        require(!route.contains("(0.50, 0.25)") && !route.contains("label: .clothing"),
                "BEGINNER_ROUTE_STILL_LABELS_FIXED_POINTS_AS_CLOTHING", into: &report)

        for feature in ["coverageFraction", "centralBandFraction", "verticalZoneCount",
                        "proximityScore", "symmetryScore", "pairedSymmetryScore",
                        "hairRisk", "accessoryRisk", "backgroundRisk"] {
            require(source.contains(feature), "MISSING_TYPED_RANK_FEATURE_\(feature)", into: &report)
        }
        require(ranker.contains("$0.status == .proposed") &&
                ranker.contains("primaryIDs") && ranker.contains("proposedSets") &&
                ranker.contains("candidates.prefix(3)"),
                "RANKER_DOES_NOT_BUILD_BOUNDED_MULTI_COMPONENT_PROPOSALS", into: &report)
        require(assessment.contains("isLikelyBackground") &&
                assessment.contains("BACKGROUND_EDGE_AREA_RISK") &&
                assessment.contains("OUTSIDE_BODY_CENTRAL_BAND"),
                "BACKGROUND_OR_OFF_BODY_REJECTION_IS_NOT_EXPLICIT", into: &report)

        require(proposed.contains("clothing_mask_candidates") &&
                proposed.contains("primary_clothing_mask_candidate_id") &&
                proposed.contains("state: \"PROPOSED\"") &&
                proposed.contains("regionEvidence($0, state: \"PROPOSED\""),
                "AUTOMATIC_CANDIDATES_ARE_NOT_EXPORTED_AS_PROPOSED", into: &report)
        require(!route.contains("OBSERVED") && !ranker.contains(".observed"),
                "AUTOMATIC_ROUTE_PROMOTES_A_COMPONENT_TO_OBSERVED", into: &report)

        // Human confirmation must keep its authority boundary and the two
        // previously connected internal-geometry routes.
        require(confirmed.contains("$0.status == .observed") &&
                confirmed.contains("$0.semanticLabel == .clothing") &&
                confirmed.contains("proposedInternalBoundaries(") &&
                confirmed.contains("proposedInternalLines("),
                "HUMAN_CONFIRMATION_OR_INTERNAL_GEOMETRY_ROUTE_CHANGED", into: &report)
        return report
    }

    private static func executableSource(_ source: String) -> String {
        source.components(separatedBy: .newlines).map { line in
            guard let range = line.range(of: "//") else { return line }
            return String(line[..<range.lowerBound])
        }.joined(separator: "\n")
    }

    private static func functionBody(in source: String, named name: String) -> String? {
        guard let signature = source.range(of: "func \(name)("),
              let open = source[signature.upperBound...].firstIndex(of: "{") else { return nil }
        var depth = 0
        var cursor = open
        while cursor < source.endIndex {
            if source[cursor] == "{" { depth += 1 }
            if source[cursor] == "}" {
                depth -= 1
                if depth == 0 { return String(source[open...cursor]) }
            }
            cursor = source.index(after: cursor)
        }
        return nil
    }

    private static func require(_ condition: @autoclosure () -> Bool,
                                _ failure: String,
                                into report: inout Report) {
        if !condition() { report.failures.append(failure) }
    }
}

#if GARMENT_AUTOMATIC_PROPOSAL_RUNTIME
// Minimal host declarations for compiling the production view/ranker as a
// standalone executable. The real app supplies these types in normal builds.
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
#endif

#if GARMENT_AUTOMATIC_PROPOSAL_RUNTIME || !GARMENT_AUTOMATIC_PROPOSAL_STANDALONE
private enum GarmentAutomaticProposalRuntimeAudit {
    struct Report { var failures: [String] = [] }

    static func run() -> Report {
        var report = Report()
        do {
            let fixture = try syntheticFixture()
            let first = GarmentOutline.rankAutomaticClothingCandidates(from: fixture.result)
            let second = GarmentOutline.rankAutomaticClothingCandidates(from: fixture.result)
            require(first == second,
                    "IDENTICAL_IMAGE_DID_NOT_RETURN_IDENTICAL_CANDIDATES", into: &report)
            require((2...3).contains(first.count),
                    "RANKER_DID_NOT_RETURN_TWO_TO_THREE_ALTERNATIVES", into: &report)
            guard let primary = first.first else {
                report.failures.append("NO_PRIMARY_CLOTHING_MASK_CANDIDATE")
                return report
            }
            require(primary.selectedRegionIDs.contains(fixture.topID) &&
                    primary.selectedRegionIDs.contains(fixture.bottomID),
                    "PRIMARY_MASK_DROPPED_SEPARATE_TOP_OR_BOTTOM", into: &report)
            require(!primary.selectedRegionIDs.contains(fixture.hairID),
                    "CENTRAL_HAIR_COMPONENT_WAS_SELECTED_AS_CLOTHING", into: &report)
            require(!primary.selectedRegionIDs.contains(fixture.backgroundID),
                    "BACKGROUND_COMPONENT_WAS_SELECTED_AS_CLOTHING", into: &report)
            require(!primary.selectedRegionIDs.contains(fixture.accessoryID),
                    "THIN_PERIPHERAL_PROP_WAS_SELECTED_AS_CLOTHING", into: &report)
            require(fixture.result.regions.allSatisfy { $0.status == .proposed },
                    "SEEDLESS_RUNTIME_FIXTURE_CREATED_OBSERVED_REGIONS", into: &report)

            let payload = GarmentOutline.extractProposedClothing(
                from: fixture.result, probes: [], imagePath: "fixture://automatic-ranking",
                rankedCandidates: first, sourceImage: nil)
            let candidates = payload["clothing_mask_candidates"] as? [[String: Any]] ?? []
            let regions = payload["regions"] as? [[String: Any]] ?? []
            require(candidates.count == first.count &&
                    candidates.allSatisfy { ($0["state"] as? String) == "PROPOSED" },
                    "PAYLOAD_DROPPED_OR_PROMOTED_MASK_CANDIDATES", into: &report)
            require(regions.allSatisfy { ($0["state"] as? String) == "PROPOSED" },
                    "SELECTED_AUTOMATIC_REGION_ESCAPED_PROPOSED", into: &report)
            require((payload["primary_clothing_mask_candidate_id"] as? String)
                    == primary.candidateID,
                    "BEGINNER_PAYLOAD_DID_NOT_USE_TOP_RANKED_CANDIDATE", into: &report)
        } catch {
            report.failures.append("SYNTHETIC_RUNTIME_FIXTURE_FAILED: \(error)")
        }
        return report
    }

    private struct Fixture {
        let result: RegionPicker.Result
        let backgroundID: Int
        let hairID: Int
        let topID: Int
        let bottomID: Int
        let accessoryID: Int
    }

    private static func syntheticFixture() throws -> Fixture {
        let width = 120, height = 160
        var rgba = [UInt8](repeating: 0, count: width * height * 4)
        fill(&rgba, width: width, x: 0...119, y: 0...159,
             color: (232, 232, 232, 255))                         // studio background
        fill(&rgba, width: width, x: 53...66, y: 5...42,
             color: (80, 42, 30, 255))                            // central hair-like strip
        fill(&rgba, width: width, x: 34...85, y: 47...86,
             color: (24, 62, 142, 255))                           // separate top
        fill(&rgba, width: width, x: 27...92, y: 89...146,
             color: (28, 116, 72, 255))                           // separate bottom
        fill(&rgba, width: width, x: 98...102, y: 55...105,
             color: (174, 112, 18, 255))                          // thin prop

        let result = try RegionPicker.pickRegions(
            rgba8: rgba, width: width, height: height,
            seeds: [], options: .photo)
        func id(_ x: Int, _ y: Int) throws -> Int {
            guard let region = result.region(containing: .init(x: x, y: y)) else {
                throw FixtureError.missingRegion(x: x, y: y)
            }
            return region.id
        }
        return try Fixture(result: result,
                           backgroundID: id(0, 0), hairID: id(58, 12),
                           topID: id(40, 60), bottomID: id(40, 110),
                           accessoryID: id(100, 70))
    }

    private static func fill(_ rgba: inout [UInt8], width: Int,
                             x: ClosedRange<Int>, y: ClosedRange<Int>,
                             color: (UInt8, UInt8, UInt8, UInt8)) {
        for row in y {
            for column in x {
                let offset = (row * width + column) * 4
                rgba[offset] = color.0
                rgba[offset + 1] = color.1
                rgba[offset + 2] = color.2
                rgba[offset + 3] = color.3
            }
        }
    }

    private enum FixtureError: Error { case missingRegion(x: Int, y: Int) }

    private static func require(_ condition: @autoclosure () -> Bool,
                                _ failure: String,
                                into report: inout Report) {
        if !condition() { report.failures.append(failure) }
    }
}
#endif

#if !GARMENT_AUTOMATIC_PROPOSAL_STANDALONE
final class GarmentAutomaticClothingProposalAuditTests: XCTestCase {
    func testBeginnerRouteUsesProposedComponentRanking() {
        XCTAssertEqual(GarmentAutomaticProposalSourceAudit.run().failures, [])
    }

    func testSyntheticHairBackgroundAndSeparatedGarments() {
        XCTAssertEqual(GarmentAutomaticProposalRuntimeAudit.run().failures, [])
    }
}
#else
@main
private enum GarmentAutomaticProposalAuditMain {
    static func main() {
        var failures = GarmentAutomaticProposalSourceAudit.run().failures
#if GARMENT_AUTOMATIC_PROPOSAL_RUNTIME
        failures += GarmentAutomaticProposalRuntimeAudit.run().failures
#endif
        if failures.isEmpty {
#if GARMENT_AUTOMATIC_PROPOSAL_RUNTIME
            print("PASS automatic clothing proposal source and runtime audit")
#else
            print("PASS automatic clothing proposal source audit")
#endif
        } else {
            failures.forEach { print("FAIL \($0)") }
            exit(1)
        }
    }
}
#endif
