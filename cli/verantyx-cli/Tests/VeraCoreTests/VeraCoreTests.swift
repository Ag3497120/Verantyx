import XCTest
@testable import VeraCore

final class VeraCoreTests: XCTestCase {
    func testEventJSONLRoundTrip() throws {
        let event = VeraRuntimeEvent(
            kind: .proposed_action,
            missionId: "m-test",
            summary: "[OPEN_APP: Calculator]",
            turn: 1,
            detail: ["tool": "OPEN_APP"],
            tags: ["act"]
        )
        let data = try JSONEncoder().encode(event)
        let decoded = try JSONDecoder().decode(VeraRuntimeEvent.self, from: data)
        XCTAssertEqual(decoded.kind, .proposed_action)
        XCTAssertEqual(decoded.missionId, "m-test")
        XCTAssertEqual(decoded.detail["tool"], "OPEN_APP")
        XCTAssertTrue(decoded.cliLine.contains("PROPOSED_ACTION"))
    }

    func testDryRunDemoEmitsRequiredKinds() async throws {
        let dir = FileManager.default.temporaryDirectory
        let url = dir.appendingPathComponent("vera-demo-\(UUID().uuidString).jsonl")
        defer { try? FileManager.default.removeItem(at: url) }

        let sink = try VeraEventSink(missionId: "m-dry", traceURL: url, writeStdout: false)
        let code = await DemoMissionRunner.calculatorDemo(dryRun: true).run(sink: sink)
        sink.close()
        XCTAssertEqual(code, 0)

        let kinds = Set(sink.events.map(\.kind))
        for need in [
            VeraEventKind.mission,
            .policy,
            .observation,
            .proposed_action,
            .result,
            .gap,
            .skill_recall,
        ] {
            XCTAssertTrue(kinds.contains(need), "missing \(need)")
        }

        let text = try String(contentsOf: url, encoding: .utf8)
        XCTAssertTrue(text.contains("\"kind\":\"mission\"") || text.contains("\"kind\" : \"mission\"") || text.contains("mission"))
    }
}
