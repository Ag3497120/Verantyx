import XCTest
@testable import VeraCore

/// Regression tests for the completion gate.
///
/// Each rejection case here was observed in a real 0.5B run before it was
/// fixed. The gate is the only thing standing between "the agent kept working"
/// and "the agent declared victory on the strength of the prompt it was given",
/// so every hole that opens once gets a test.
final class HonestyGateTests: XCTestCase {

    private let goal = "Trace the cause of the CI packaging failure"

    func testRejectsMissingMarker() {
        XCTAssertFalse(LongHorizonRunner.looksComplete(
            "I will look at the build logs next.", goal: goal))
    }

    func testRejectsBareMarker() {
        XCTAssertFalse(LongHorizonRunner.looksComplete("DONE:", goal: goal))
        XCTAssertFalse(LongHorizonRunner.looksComplete("Done: ok", goal: goal))
    }

    /// Observed: the model echoed the system prompt's own instruction back.
    func testRejectsInstructionEcho() {
        XCTAssertFalse(LongHorizonRunner.looksComplete(
            "Done: 2/5. State one concrete next step, then a short result line.",
            goal: goal))
    }

    /// Observed after the model swap: the goal restated as its own outcome.
    func testRejectsGoalRestatedAsResult() {
        XCTAssertFalse(LongHorizonRunner.looksComplete(
            "DONE: Trace the cause of the CI packaging failure", goal: goal))
        XCTAssertFalse(LongHorizonRunner.looksComplete(
            "DONE: the CI packaging failure cause trace", goal: goal))
    }

    func testAcceptsSubstantiveResult() {
        XCTAssertTrue(LongHorizonRunner.looksComplete(
            "DONE: the packaging step calls hdiutil before the app bundle is signed, so codesign runs on a mounted image",
            goal: goal))
    }

    /// ChatML scaffolding a small model re-emits must not become stored
    /// "experience" that is recalled forever.
    func testCleanReplyStripsChatMLAndKeepsFirstLine() {
        let raw = "1/3. Check the signing step.<|im_end|>\n<|im_start|>done:<|im_end|>\n<|im_start|>1/3. Check"
        XCTAssertEqual(LongHorizonRunner.cleanReply(raw), "1/3. Check the signing step.")
    }
}

/// The gap store is what makes a resumed process a continuation rather than a
/// restart, so its identity and retention rules are pinned here.
final class GapStoreTests: XCTestCase {

    private func makeStore() throws -> (GapStore, URL) {
        let dir = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("gapstore-" + UUID().uuidString)
        return (try GapStore(directory: dir), dir)
    }

    func testSameScopeSubjectReturnsSameNode() throws {
        let (store, dir) = try makeStore()
        defer { try? FileManager.default.removeItem(at: dir) }

        let first = try store.open(gapType: "MISSION", subject: "audit repo", scope: "mission")
        let second = try store.open(gapType: "MISSION", subject: "audit repo", scope: "mission")
        XCTAssertEqual(first.gapId, second.gapId)
        XCTAssertEqual(store.nodes.count, 1)
    }

    func testResolvedNodesAreRetainedAndReturned() throws {
        let (store, dir) = try makeStore()
        defer { try? FileManager.default.removeItem(at: dir) }

        let gap = try store.open(gapType: "MISSION", subject: "audit repo", scope: "mission")
        try store.resolve(gap.gapId, note: "settled")
        // Re-opening the same ground must surface the settled node, not a new
        // one — that is how a later session knows not to redo the work.
        let again = try store.open(gapType: "MISSION", subject: "audit repo", scope: "mission")
        XCTAssertEqual(again.gapId, gap.gapId)
        XCTAssertEqual(again.status, .resolved)
        XCTAssertTrue(store.openGaps.isEmpty)
    }

    func testSurvivesReopeningTheDirectory() throws {
        let (store, dir) = try makeStore()
        defer { try? FileManager.default.removeItem(at: dir) }

        let gap = try store.open(gapType: "MISSION", subject: "audit repo", scope: "mission")
        try store.recordAttempt(gap.gapId, strategy: "grep the logs", failureType: "not_yet_complete")

        let reopened = try GapStore(directory: dir)
        let recovered = reopened.get(gap.gapId)
        XCTAssertEqual(recovered?.subject, "audit repo")
        XCTAssertEqual(recovered?.attemptedStrategies, ["grep the logs"])
    }

    /// Prompt cost must not grow with mission length: the store keeps every
    /// attempt, the prompt line shows a bounded window of them.
    func testBriefLineBoundsAttemptHistory() throws {
        let (store, dir) = try makeStore()
        defer { try? FileManager.default.removeItem(at: dir) }

        let gap = try store.open(gapType: "MISSION", subject: "audit repo", scope: "mission")
        for i in 1...20 {
            try store.recordAttempt(gap.gapId, strategy: "strategy number \(i)", failureType: nil)
        }
        let line = store.get(gap.gapId)!.briefLine()
        XCTAssertTrue(line.contains("strategy number 20"))
        XCTAssertFalse(line.contains("strategy number 1 "))
        XCTAssertTrue(line.contains("earlier"))
        XCTAssertEqual(store.get(gap.gapId)?.attemptedStrategies.count, 20)
    }
}
