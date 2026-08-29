import Foundation

#if !GARMENT_INTERNAL_BOUNDARY_STANDALONE
import XCTest
#endif

/// Source-level audit for the RegionPicker -> GarmentOutline evidence seam.
///
/// This runs without AppKit so CI can guard the authority boundary even when
/// the full macOS test host is unavailable.  Runtime compilation is covered by
/// the Verantyx Debug build performed alongside this audit.
private enum GarmentInternalBoundaryAudit {
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

        guard let proposed = functionBody(in: source, named: "extractProposedClothing"),
              let confirmed = functionBody(in: source, named: "extractConfirmedClothing"),
              let extraction = functionBody(in: source, named: "proposedInternalBoundaries"),
              let evidence = functionBody(in: source, named: "internalBoundaryEvidence")
        else {
            report.failures.append("INTERNAL_BOUNDARY_CONTRACT_FUNCTION_MISSING")
            return report
        }

        for (route, body) in [("AUTOMATIC", proposed), ("HUMAN", confirmed)] {
            require(body.contains("proposedInternalBoundaries("),
                    "\(route)_ROUTE_DOES_NOT_EXTRACT_INTERNAL_LOOPS", into: &report)
            require(body.contains("\"internal_boundaries\"") &&
                    body.contains("\"internal_boundaries_state\": \"PROPOSED\"") &&
                    body.contains("\"internal_boundary_evidence\""),
                    "\(route)_ROUTE_DOES_NOT_TRANSPORT_PROPOSED_INTERNAL_BOUNDARIES",
                    into: &report)
        }

        require(extraction.contains("outerIndex = loops.indices.max") &&
                extraction.contains("index != outerIndex"),
                "MAXIMUM_OUTER_LOOP_IS_NOT_EXCLUDED_FROM_INTERNAL_BOUNDARIES",
                into: &report)
        require(extraction.contains("boundaryLoops(from: region.boundaryEdges)") &&
                extraction.contains("for region in regions.sorted"),
                "INTERNAL_LOOPS_ARE_NOT_SCOPED_TO_THE_SAME_REGION", into: &report)
        require(extraction.contains("loops[index].count >= 3") &&
                extraction.contains("area >= minimumArea") &&
                extraction.contains("area < outerArea") &&
                extraction.contains("max(16.0,") &&
                extraction.contains("max(frameArea * 0.0005, outerArea * 0.005)"),
                "OPEN_OR_NOISE_LOOPS_CAN_ENTER_INTERNAL_BOUNDARIES", into: &report)

        require(evidence.contains("\"state\": \"PROPOSED\"") &&
                evidence.contains("\"kind\": \"PROPOSED\"") &&
                evidence.contains("\"semantic\": \"UNKNOWN\"") &&
                evidence.contains("\"closed\": true"),
                "INTERNAL_BOUNDARY_AUTHORITY_IS_NOT_PROPOSED_AND_UNKNOWN",
                into: &report)
        for forbidden in ["\"state\": \"OBSERVED\"", "\"semantic\": \"seam\"",
                          "\"semantic\": \"frill\"", "\"semantic\": \"overlap\""] {
            require(!evidence.contains(forbidden),
                    "INTERNAL_BOUNDARY_WAS_PROMOTED_TO_OBSERVED_SEMANTICS_\(forbidden)",
                    into: &report)
        }
        require(confirmed.contains("\"kind\": \"OBSERVED\"") &&
                confirmed.contains("\"internal_boundaries_kind\": \"PROPOSED\""),
                "HUMAN_REGION_EVIDENCE_AND_INTERNAL_MEANING_ARE_NOT_SEPARATED",
                into: &report)

        return report
    }

    private static func executableSource(_ source: String) -> String {
        source.components(separatedBy: .newlines)
            .map { line -> String in
                guard let range = line.range(of: "//") else { return line }
                return String(line[..<range.lowerBound])
            }
            .joined(separator: "\n")
    }

    private static func functionBody(in source: String, named name: String) -> String? {
        guard let signature = source.range(of: "func \(name)("),
              let open = source[signature.upperBound...].firstIndex(of: "{")
        else { return nil }
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

#if !GARMENT_INTERNAL_BOUNDARY_STANDALONE
final class GarmentInternalBoundaryAuditTests: XCTestCase {
    func testRegionPickerTransportsOnlyProposedInternalBoundaries() {
        XCTAssertEqual(GarmentInternalBoundaryAudit.run().failures, [])
    }
}
#else
@main
private enum GarmentInternalBoundaryAuditMain {
    static func main() {
        let failures = GarmentInternalBoundaryAudit.run().failures
        if failures.isEmpty {
            print("PASS proposed garment internal-boundary contract")
        } else {
            failures.forEach { print("FAIL \($0)") }
            exit(1)
        }
    }
}
#endif
