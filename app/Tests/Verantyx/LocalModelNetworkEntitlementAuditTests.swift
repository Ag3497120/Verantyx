import Foundation
import XCTest

final class LocalModelNetworkEntitlementAuditTests: XCTestCase {
    private var projectRoot: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
    }

    func testSignedAppAllowsOutboundLocalModelConnections() throws {
        let url = projectRoot
            .appendingPathComponent("Sources/Verantyx/Verantyx.entitlements")
        let data = try Data(contentsOf: url)
        let plist = try XCTUnwrap(
            PropertyListSerialization.propertyList(from: data, format: nil)
                as? [String: Any]
        )

        XCTAssertEqual(plist["com.apple.security.network.client"] as? Bool, true)
    }

    func testLocalNetworkPromptNamesCreationModelServers() throws {
        let url = projectRoot.appendingPathComponent("Sources/Verantyx/Info.plist")
        let data = try Data(contentsOf: url)
        let plist = try XCTUnwrap(
            PropertyListSerialization.propertyList(from: data, format: nil)
                as? [String: Any]
        )
        let description = try XCTUnwrap(plist["NSLocalNetworkUsageDescription"] as? String)

        XCTAssertTrue(description.localizedCaseInsensitiveContains("LM Studio"))
        XCTAssertTrue(description.localizedCaseInsensitiveContains("Ollama"))
    }
}
