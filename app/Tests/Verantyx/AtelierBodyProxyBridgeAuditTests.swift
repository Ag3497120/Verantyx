import Foundation

#if !ATELIER_BODY_PROXY_BRIDGE_STANDALONE
import XCTest
#endif

/// Source-level guard for the image -> proposed body proxy -> target 3D bridge.
/// It prevents a clothing silhouette from silently becoming a wearer
/// measurement and keeps automatic selection below manufacturing authority.
private enum AtelierBodyProxyBridgeAudit {
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
        else { return ["BODY_PROXY_BRIDGE_SOURCE_UNREADABLE"] }
        var failures: [String] = []
        func require(_ condition: @autoclosure () -> Bool, _ code: String) {
            if !condition() { failures.append(code) }
        }

        require(controller.contains("prepareBodyProxyCandidates(") &&
                controller.contains("garment.body-proxy.request.v1") &&
                controller.contains("garment_body_proxy_propose"),
                "SWIFT_DOES_NOT_CALL_TYPED_BODY_PROXY_MCP")
        require(controller.contains("prepareBodyImageSeparation(") &&
                controller.contains("garment.body-image-separation.request.v1") &&
                controller.contains("garment_body_image_separation_propose") &&
                controller.contains("VERA_BODY_IMAGE_SEPARATION_MCP") &&
                controller.contains("UNKNOWN_UNOBSERVED"),
                "SWIFT_DOES_NOT_CALL_BOUNDED_BODY_IMAGE_SEPARATION_MCP")
        require(controller.contains("GarmentOutline.bodyImageSeparationProvider(") &&
                controller.contains("APPLE_VISION_LOCAL_PROVIDER") &&
                controller.contains("request[\"provider_outputs\"] = [provider]") &&
                controller.contains("REVIEW_CLOTHED_SUBJECT_PROXY_NOT_BODY_MEASUREMENT"),
                "LOCAL_VISION_PROVIDER_DOES_NOT_REACH_TYPED_SEPARATION")
        let separationCall = controller.range(
            of: "let separation = await prepareBodyImageSeparation(")?.lowerBound
        let bodyProxyRequest = controller.range(
            of: "\"schema\": \"garment.body-proxy.request.v1\"",
            options: [], range: separationCall.map { $0..<controller.endIndex })?
            .lowerBound
        require(separationCall != nil && bodyProxyRequest != nil &&
                separationCall! < bodyProxyRequest!,
                "BODY_PROXY_IS_NOT_CONDITIONED_BY_TYPED_SEPARATION")
        let proxyCall = controller.range(
            of: "await prepareBodyProxyCandidates(")?.lowerBound
        let targetCall = controller.range(
            of: "await prepareTargetReconstruction(outline: outline, imagePath: imagePath)",
            options: [], range: proxyCall.map { $0..<controller.endIndex })?.lowerBound
        require(proxyCall != nil && targetCall != nil && proxyCall! < targetCall!,
                "TARGET_3D_IS_BUILT_BEFORE_BODY_PROXY_SELECTION")
        require(controller.contains("for item in requirements where item.kind == .bodyMeasurement") &&
                controller.contains("\"authority\": \"REQUESTED\"") &&
                controller.contains("\"kind\": \"GARMENT\"") &&
                controller.contains("[\"BODY\", \"GARMENT\"].contains(kind.uppercased())") &&
                !controller.contains("\"scale_cm_per_px\":") &&
                !controller.contains("\"body_dimension_ranges_cm\":") &&
                !controller.contains("\"kind\": \"BODY\",\n                \"mask_digest\": outlineDigest"),
                "CLOTHING_PIXELS_CAN_BE_PROMOTED_TO_BODY_MEASUREMENTS")
        require(controller.contains("PROPOSED_BODY_PROXY") &&
                controller.contains("avatar:body-proxy:") &&
                controller.contains("AUTO_PROPOSED") &&
                controller.contains("selected_candidate_id"),
                "BODY_PROXY_ALTERNATIVES_DO_NOT_REACH_AVATAR_SELECTION")
        require(flow.contains("AUTO_ACCEPTED_FOR_PREVIEW — AI提案を比較用に自動採用") &&
                flow.contains("観測・縫製可能性・製造承認へは昇格しません"),
                "BEGINNER_UI_HIDES_BODY_TARGET_AUTHORITY_CEILING")
        return failures
    }
}

#if !ATELIER_BODY_PROXY_BRIDGE_STANDALONE
final class AtelierBodyProxyBridgeAuditTests: XCTestCase {
    func testImageBoundBodyProxyRemainsProposalOnly() {
        XCTAssertEqual(AtelierBodyProxyBridgeAudit.failures(), [])
    }
}
#else
@main
private enum AtelierBodyProxyBridgeAuditMain {
    static func main() {
        let failures = AtelierBodyProxyBridgeAudit.failures()
        if failures.isEmpty {
            print("PASS Atelier image-bound body proxy bridge")
            exit(0)
        }
        failures.forEach { print("FAIL \($0)") }
        exit(1)
    }
}
#endif
