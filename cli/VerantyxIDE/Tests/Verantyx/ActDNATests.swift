import Foundation
@testable import Verantyx

// MARK: - ActDNA invariant checks
//
// Assert-style unit checks for the DNA façade (procedural detection,
// OPEN_APP honesty, hierarchical pause). Runnable without a separate
// XCTest target via `ActDNA.runInvariantChecks()`; also exposed as
// XCTestCase when the Tests folder is wired into a test bundle.

#if canImport(XCTest)
import XCTest

final class ActDNATests: XCTestCase {

    func testDNAInvariantBundle() {
        let fails = ActDNA.runInvariantChecks()
        XCTAssertTrue(
            fails.isEmpty,
            "ActDNA invariants failed:\n" + fails.joined(separator: "\n")
        )
    }

    func testProceduralBlocksSearchBootstrap() {
        let goal = "メモ帳を開いて→テキストを入力して→保存する"
        XCTAssertTrue(PromptBudget.isProceduralMission(goal))
        XCTAssertFalse(ActDNA.shouldTypeSearchBootstrap(goal: goal))
        XCTAssertTrue(ActDNA.isProceduralOpenSenseOnly(goal: goal))
    }

    func testOpenAppHonesty() {
        let bad = "✗ OPEN_APP MISMATCH: \"FakeApp\" does not resolve to an installed app — nothing was opened."
        XCTAssertFalse(ActDNA.openAppSucceeded(fromObservation: bad))
        XCTAssertEqual(
            ActDNA.validateLimbResult(tool: .openApp(name: "FakeApp"), result: bad).isOk,
            false
        )

        let good = "✓ OS App opened and brought frontmost: Calculator. Use [DESKTOP_ACT]."
        XCTAssertTrue(ActDNA.openAppSucceeded(fromObservation: good))
        XCTAssertTrue(ActDNA.validateLimbResult(tool: .openApp(name: "Calculator"), result: good).isOk)
    }

    func testHierarchicalPauseTrigger() {
        let obs = """
        <link id="#link1" title="Alpha Destination"/>
        <link id="#link2" title="Beta Destination"/>
        <link id="#link3" title="Gamma Destination"/>
        """
        let cands = ActDNA.shouldPauseForCandidates(observation: obs, enabled: true)
        XCTAssertNotNil(cands)
        XCTAssertGreaterThanOrEqual(cands?.count ?? 0, 2)

        XCTAssertNil(ActDNA.shouldPauseForCandidates(observation: obs, enabled: false))
    }

    func testLimbSetIsThin() {
        XCTAssertEqual(ActLimb.allCases.count, 5)
        XCTAssertTrue(ActDNA.isAllowedActLimb(.openApp(name: "Safari")))
        XCTAssertTrue(ActDNA.isAllowedActLimb(.desktopSnapshot))
        XCTAssertTrue(ActDNA.isAllowedActLimb(.pastePayload))
        XCTAssertTrue(ActDNA.isAllowedActLimb(.done(message: "ok")))
        XCTAssertFalse(ActDNA.isAllowedActLimb(.search(query: "x")))
    }

    func testCycleDetectorCatchesSafariSnapshot() {
        let keys = ["open_app:safari", "desktop_snapshot", "open_app:safari", "desktop_snapshot"]
        let unit = ActCycleDetector.detectCycle(recentKeys: keys)
        XCTAssertEqual(unit, ["open_app:safari", "desktop_snapshot"])
    }

    func testPhoneGoalRejectsSafariBootstrap() {
        XCTAssertTrue(JGenActAgent.goalRejectsBrowserBootstrap("電話アプリを開いて本西朋子に電話して"))
        XCTAssertTrue(JGenActAgent.goalRejectsBrowserBootstrap("メッセージを開いてらにメッセージを送って"))
        XCTAssertFalse(JGenActAgent.goalNeedsBrowser("電話アプリを開いて本西朋子に電話して"))
        XCTAssertFalse(JGenActAgent.goalRejectsBrowserBootstrap("Safariでニュースを検索して"))
        XCTAssertTrue(JGenActAgent.goalNeedsBrowser("Safariでニュースを検索して"))
    }

    func testGapControllerBlocksSurrender() {
        var gap = ActGapController.open(subject: "open Messages")
        XCTAssertTrue(gap.isOpen)
        gap.noteMismatch(action: "open_app:JGEN", failureType: "mismatch")
        XCTAssertTrue(ActGapController.looksLikeSurrenderDONE("couldn't open the app"))
        gap.resolve()
        XCTAssertFalse(gap.isOpen)
    }
}
#endif
