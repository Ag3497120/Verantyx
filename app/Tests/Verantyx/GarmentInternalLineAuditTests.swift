import Foundation

#if !GARMENT_INTERNAL_LINE_STANDALONE
import XCTest
#endif

#if GARMENT_INTERNAL_LINE_RUNTIME || !GARMENT_INTERNAL_LINE_STANDALONE
import AppKit
import CoreGraphics
#endif

/// Source audit for the image -> outline `internal_lines` authority boundary.
/// The production implementation needs AppKit/CoreGraphics; this audit stays
/// Foundation-only so it can also run on CI without the Verantyx test host.
private enum GarmentInternalLineAudit {
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
              let detector = functionBody(in: source, named: "proposedInternalLines"),
              let evidence = functionBody(in: source, named: "internalLineEvidence")
        else {
            report.failures.append("INTERNAL_LINE_CONTRACT_FUNCTION_MISSING")
            return report
        }

        for (route, body) in [("AUTOMATIC", proposed), ("HUMAN", confirmed)] {
            require(body.contains("proposedInternalBoundaries("),
                    "\(route)_ROUTE_DROPPED_EXISTING_INTERNAL_BOUNDARIES", into: &report)
            require(body.contains("proposedInternalLines(") &&
                    body.contains("sourceImage"),
                    "\(route)_ROUTE_DOES_NOT_ANALYZE_SOURCE_IMAGE", into: &report)
            require(body.contains("\"internal_lines\"") &&
                    body.contains("\"internal_lines_state\": \"PROPOSED\"") &&
                    body.contains("\"internal_line_evidence\""),
                    "\(route)_ROUTE_DOES_NOT_TRANSPORT_PROPOSED_INTERNAL_LINES",
                    into: &report)
        }

        require(detector.contains("regions.flatMap(\\.scanlineRuns)") &&
                detector.contains("clothingMask") &&
                detector.contains("isInsideErodedClothing"),
                "DETECTOR_IS_NOT_SCOPED_TO_ERODED_CLOTHING_REGIONS", into: &report)
        require(detector.contains("let interiorMargin = 3") &&
                detector.contains("minimumContrast = 3.5") &&
                detector.contains("maximumContrast = 38.0"),
                "WEAK_CONTRAST_AND_INTERIOR_THRESHOLDS_ARE_NOT_EXPLICIT", into: &report)
        require(detector.contains("minimumLength = max(18.0") &&
                detector.contains("minimumSupportFraction = 0.38") &&
                detector.contains("maximumProjectedGap = 4.5"),
                "SHORT_OR_DISCONTINUOUS_NOISE_IS_NOT_REJECTED", into: &report)
        require(detector.contains("maximumTangentialGradientFraction = 0.42") &&
                detector.contains("directions.enumerated()") &&
                detector.contains("rhoBandWidth = 3.0"),
                "DETECTOR_LACKS_DIRECTIONAL_COHERENCE_FILTERING", into: &report)
        require(detector.contains("if accepted.count == 8") &&
                detector.contains("abs(existing.rhoPixels - candidate.rhoPixels) < 7"),
                "DUPLICATE_OR_UNBOUNDED_LINE_PROPOSALS_ARE_NOT_SUPPRESSED", into: &report)

        require(evidence.contains("\"state\": \"PROPOSED\"") &&
                evidence.contains("\"kind\": \"PROPOSED\"") &&
                evidence.contains("\"semantic\": \"UNKNOWN\"") &&
                evidence.contains("\"closed\": false"),
                "INTERNAL_LINE_AUTHORITY_IS_NOT_PROPOSED_AND_UNKNOWN", into: &report)
        require(!evidence.contains("\"state\": \"OBSERVED\"") &&
                !evidence.contains("\"kind\": \"OBSERVED\"") &&
                !evidence.contains("\"semantic\": \"seam\""),
                "INTERNAL_LINE_WAS_PROMOTED_TO_OBSERVED_SEAM", into: &report)
        require(evidence.contains("minimum_length_px") &&
                evidence.contains("support_fraction") &&
                evidence.contains("contrast_range") &&
                evidence.contains("interior_margin_px"),
                "INTERNAL_LINE_FILTER_THRESHOLDS_ARE_NOT_AUDITABLE", into: &report)

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

#if GARMENT_INTERNAL_LINE_RUNTIME || !GARMENT_INTERNAL_LINE_STANDALONE
/// Executes the production detector through the complete
/// `RegionPicker.Result -> extractProposedClothing -> payload` route.  The
/// image deliberately keeps the garment and switch line in one colour
/// component so this verifies the weak-line path rather than the existing
/// `internal_boundaries` path.
private enum GarmentInternalLineRuntimeAudit {
    struct Report { var failures: [String] = [] }

    static func run() -> Report {
        var report = Report()
        do {
            let weak = try payload(hasWeakHorizontalLine: true)
            let weakLines = weak["internal_lines"] as? [[[Double]]] ?? []
            require(!weakLines.isEmpty,
                    "WEAK_INTERNAL_HORIZONTAL_LINE_WAS_NOT_EXTRACTED", into: &report)
            require(weakLines.allSatisfy { line in
                line.count >= 2 && line.allSatisfy { point in point.count == 2 }
            }, "INTERNAL_LINE_PAYLOAD_IS_NOT_POLYLINE_XY", into: &report)

            let evidence = weak["internal_line_evidence"] as? [[String: Any]] ?? []
            require(evidence.count == weakLines.count,
                    "INTERNAL_LINE_EVIDENCE_COUNT_MISMATCH", into: &report)
            require((weak["internal_lines_state"] as? String) == "PROPOSED" &&
                    evidence.allSatisfy {
                        ($0["state"] as? String) == "PROPOSED"
                            && ($0["kind"] as? String) == "PROPOSED"
                            && ($0["semantic"] as? String) == "UNKNOWN"
                    }, "RUNTIME_LINE_EVIDENCE_ESCAPED_PROPOSED_UNKNOWN", into: &report)

            let uniform = try payload(hasWeakHorizontalLine: false)
            let uniformLines = uniform["internal_lines"] as? [[[Double]]] ?? []
            require(uniformLines.isEmpty,
                    "UNIFORM_GARMENT_OR_STRONG_OUTER_EDGE_CREATED_INTERNAL_LINE",
                    into: &report)
        } catch {
            report.failures.append("RUNTIME_FIXTURE_FAILED: \(error)")
        }
        return report
    }

    private static func payload(hasWeakHorizontalLine: Bool) throws -> [String: Any] {
        let width = 128, height = 96
        var rgba = [UInt8](repeating: 0, count: width * height * 4)
        // Transparent background gives RegionPicker an exact garment mask;
        // only the strong outer silhouette remains in the no-line fixture.
        for y in 12...83 {
            for x in 24...103 {
                let offset = (y * width + x) * 4
                let value: UInt8 = hasWeakHorizontalLine && y == 48 ? 112 : 120
                rgba[offset] = value
                rgba[offset + 1] = value
                rgba[offset + 2] = value
                rgba[offset + 3] = 255
            }
        }
        guard let image = cgImage(rgba: rgba, width: width, height: height) else {
            throw RuntimeError.imageCreationFailed
        }
        let probes = [
            RegionPicker.Seed(x: 40, y: 28, label: .clothing),
            RegionPicker.Seed(x: 64, y: 40, label: .clothing),
            RegionPicker.Seed(x: 80, y: 68, label: .clothing),
        ]
        let result = try RegionPicker.pickRegions(
            rgba8: rgba, width: width, height: height,
            seeds: probes, options: .photo)
        return GarmentOutline.extractProposedClothing(
            from: result, probes: probes, imagePath: "fixture://weak-line",
            sourceImage: image)
    }

    private static func cgImage(rgba: [UInt8], width: Int, height: Int) -> CGImage? {
        let data = Data(rgba) as CFData
        guard let provider = CGDataProvider(data: data),
              let colorSpace = CGColorSpace(name: CGColorSpace.sRGB) else { return nil }
        return CGImage(width: width, height: height,
                       bitsPerComponent: 8, bitsPerPixel: 32,
                       bytesPerRow: width * 4, space: colorSpace,
                       bitmapInfo: CGBitmapInfo(rawValue:
                        CGImageAlphaInfo.premultipliedLast.rawValue),
                       provider: provider, decode: nil,
                       shouldInterpolate: false, intent: .defaultIntent)
    }

    private enum RuntimeError: Error { case imageCreationFailed }

    private static func require(_ condition: @autoclosure () -> Bool,
                                _ failure: String,
                                into report: inout Report) {
        if !condition() { report.failures.append(failure) }
    }
}
#endif

#if !GARMENT_INTERNAL_LINE_STANDALONE
final class GarmentInternalLineAuditTests: XCTestCase {
    func testWeakInternalLinesRemainDeterministicProposals() {
        XCTAssertEqual(GarmentInternalLineAudit.run().failures, [])
    }

    func testSyntheticWeakLineRuntimeContract() {
        XCTAssertEqual(GarmentInternalLineRuntimeAudit.run().failures, [])
    }
}
#else
@main
private enum GarmentInternalLineAuditMain {
    static func main() {
        var failures = GarmentInternalLineAudit.run().failures
#if GARMENT_INTERNAL_LINE_RUNTIME
        failures += GarmentInternalLineRuntimeAudit.run().failures
#endif
        if failures.isEmpty {
#if GARMENT_INTERNAL_LINE_RUNTIME
            print("PASS proposed garment internal-line source and runtime contract")
#else
            print("PASS proposed garment internal-line source contract")
#endif
        } else {
            failures.forEach { print("FAIL \($0)") }
            exit(1)
        }
    }
}
#endif
