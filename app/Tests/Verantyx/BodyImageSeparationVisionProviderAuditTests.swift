import Foundation

#if !BODY_IMAGE_SEPARATION_VISION_PROVIDER_STANDALONE
import XCTest
#endif

private enum BodyImageSeparationVisionProviderAudit {
    static func failures(imagePaths: [String]) -> [String] {
        var failures: [String] = []
        var totalPosePoints = 0
        for path in imagePaths {
            let evidence: [String: Any] = [
                "outline": [[20.0, 30.0], [180.0, 30.0],
                            [190.0, 290.0], [10.0, 290.0]],
                "width_px": 200,
                "height_px": 320,
                "regions": [[
                    "region_id": "audit-garment",
                    "state": "PROPOSED",
                    "outline": [[20.0, 30.0], [180.0, 30.0],
                                [190.0, 290.0], [10.0, 290.0]],
                ]],
            ]
            let provider = GarmentOutline.bodyImageSeparationProvider(
                fileURL: URL(fileURLWithPath: path),
                garmentEvidence: evidence, evidenceState: "PROPOSED")
            let label = URL(fileURLWithPath: path).lastPathComponent
            if provider["provider_kind"] as? String
                != "APPLE_VISION_POSE_AND_CLOTHED_SUBJECT_PROXY" {
                failures.append("\(label):PROVIDER_KIND")
                continue
            }
            if provider["rear_state"] as? String != "UNKNOWN_UNOBSERVED" {
                failures.append("\(label):REAR_AUTHORITY")
            }
            if provider["manufacturing_ready"] as? Bool != false {
                failures.append("\(label):MANUFACTURING_AUTHORITY")
            }
            if provider["body_dimension_ranges_cm"] != nil
                || provider["dimensions"] != nil {
                failures.append("\(label):IMAGE_PROMOTED_TO_DIMENSIONS")
            }
            let masks = provider["masks"] as? [[String: Any]] ?? []
            if !masks.contains(where: {
                ($0["class"] as? String) == "GARMENT"
                    && ($0["authority"] as? String) == "PROPOSED"
            }) {
                failures.append("\(label):GARMENT_MASK")
            }
            if !masks.contains(where: {
                ($0["class"] as? String) == "BODY"
                    && ($0["authority"] as? String) == "PROPOSED"
            }) {
                failures.append("\(label):CLOTHED_SUBJECT_PROXY")
            }
            let camera = provider["camera"] as? [String: Any] ?? [:]
            let width = (camera["width_px"] as? NSNumber)?.doubleValue ?? 0
            let height = (camera["height_px"] as? NSNumber)?.doubleValue ?? 0
            let pose = provider["pose_keypoints"] as? [[String: Any]] ?? []
            totalPosePoints += pose.count
            for row in pose {
                guard let point = row["point"] as? [Double], point.count >= 2,
                      point[0] >= 0, point[0] <= width,
                      point[1] >= 0, point[1] <= height,
                      row["authority"] as? String == "PROPOSED" else {
                    failures.append("\(label):POSE_COORDINATE_OR_AUTHORITY")
                    break
                }
            }
        }
        // Pose can legitimately be unavailable for a cropped or heavily
        // occluded subject; across a mixed real-image sample the provider
        // should nevertheless prove that the Vision pose path is live.
        if totalPosePoints < 8 {
            failures.append("REAL_SAMPLE:POSE_PROVIDER_INACTIVE")
        }
        return failures
    }
}

#if !BODY_IMAGE_SEPARATION_VISION_PROVIDER_STANDALONE
final class BodyImageSeparationVisionProviderAuditTests: XCTestCase {
    func testProviderNeverPromotesClothedImageToMeasuredBody() throws {
        throw XCTSkip("Standalone audit receives real-image fixture paths")
    }
}
#else
@main
private enum BodyImageSeparationVisionProviderAuditMain {
    static func main() {
        let paths = Array(CommandLine.arguments.dropFirst())
        guard !paths.isEmpty else {
            print("FAIL REAL_IMAGE_PATHS_REQUIRED")
            exit(2)
        }
        let failures = BodyImageSeparationVisionProviderAudit.failures(
            imagePaths: paths)
        if failures.isEmpty {
            print("PASS Apple Vision body/garment provider on \(paths.count) real images")
            exit(0)
        }
        failures.forEach { print("FAIL \($0)") }
        exit(1)
    }
}
#endif
