import XCTest
@testable import VeraCore

/// Regression tests for reasoning-model output.
///
/// Every case here is drawn from a real qwen3-4b run whose "reply" was the
/// literal `<think>` tag, or a mid-thought fragment shown as a final answer.
final class ThinkingFilterTests: XCTestCase {

    func testClosedBlockYieldsTextAfterIt() {
        let raw = "<think>The log is at build.log, I should read it.</think>[READ_FILE: build.log]"
        let r = ThinkingFilter.split(raw)
        XCTAssertEqual(r.answer, "[READ_FILE: build.log]")
        XCTAssertTrue(r.thinking.contains("build.log"))
        XCTAssertFalse(r.truncatedThinking)
    }

    /// The observed failure: the budget ran out inside the block, so there is
    /// no answer — and the thinking must not be promoted into one.
    func testUnclosedBlockHasNoAnswer() {
        let r = ThinkingFilter.split("<think>Let me consider the options. First I")
        XCTAssertEqual(r.answer, "")
        XCTAssertTrue(r.truncatedThinking)
        XCTAssertTrue(r.thinking.hasPrefix("Let me consider"))
    }

    /// A block that closes with nothing after it is also unfinished: the model
    /// stopped at the boundary without saying anything.
    func testClosedBlockWithNoAnswerCountsAsTruncated() {
        let r = ThinkingFilter.split("<think>thought</think>   \n ")
        XCTAssertEqual(r.answer, "")
        XCTAssertTrue(r.truncatedThinking)
    }

    func testPlainReplyIsUntouched() {
        let r = ThinkingFilter.split("[LIST_DIR: .]")
        XCTAssertEqual(r.answer, "[LIST_DIR: .]")
        XCTAssertEqual(r.thinking, "")
        XCTAssertFalse(r.truncatedThinking)
    }

    /// Only the final segment is addressed to the user when a model reopens
    /// thinking part-way through.
    func testReopenedThinkingUsesTheLastBlock() {
        let raw = "<think>a</think>draft<think>b</think>DONE: the real answer"
        XCTAssertEqual(ThinkingFilter.split(raw).answer, "DONE: the real answer")
    }

    func testDetectsThinkingRegardlessOfClosure() {
        XCTAssertTrue(ThinkingFilter.containsThinking("<think>x"))
        XCTAssertTrue(ThinkingFilter.containsThinking("<THINK>x</THINK>y"))
        XCTAssertFalse(ThinkingFilter.containsThinking("no tags here"))
    }

    /// Ornith-1.0-9B reasons inside `<analysis>`, not `<think>`. With only the
    /// Qwen-style tag known, its reply came back as the literal `<analysis>` —
    /// the same defect as `<think>`, under a name the filter did not know.
    /// Every tag in the list was added after a real model emitted it.
    func testRecognisesNonQwenReasoningTags() {
        for tag in ["analysis", "scratchpad", "reasoning"] {
            XCTAssertTrue(ThinkingFilter.containsThinking("<\(tag)>considering"),
                          "<\(tag)> should count as thinking")
            let open = ThinkingFilter.split("<\(tag)>considering the log")
            XCTAssertEqual(open.answer, "", "<\(tag)> left open must yield no answer")
            XCTAssertTrue(open.truncatedThinking)

            let closed = ThinkingFilter.split("<\(tag)>reasoned</\(tag)>[READ_FILE: ci.log]")
            XCTAssertEqual(closed.answer, "[READ_FILE: ci.log]")
            XCTAssertFalse(closed.truncatedThinking)
        }
    }

    func testExpandedBudgetIsBigEnoughToReachAnAnswer() {
        // 96 was the budget that produced "<think>" and nothing else.
        XCTAssertGreaterThanOrEqual(ThinkingFilter.expandedBudget(96), 512)
        XCTAssertGreaterThan(ThinkingFilter.expandedBudget(96), 96)
    }

    // MARK: - Interaction with line selection

    /// `firstLine` on raw reasoning output returns the opening tag — which is
    /// precisely how the reply came to be reported as "<think>". Order matters,
    /// so it is pinned.
    func testFirstLineAloneWouldReturnTheOpeningTag() {
        let raw = "<think>\nthinking here\nmore"
        XCTAssertEqual(LongHorizonRunner.firstLine(raw), "<think>")
        XCTAssertEqual(LongHorizonRunner.cleanReply(raw), "",
                       "going through ThinkingFilter first must yield no answer, not the tag")
    }

    func testCleanReplyStillHandlesNonReasoningChatMLLeakage() {
        let raw = "1/3. Check the signing step.<|im_end|>\n<|im_start|>done:"
        XCTAssertEqual(LongHorizonRunner.cleanReply(raw), "1/3. Check the signing step.")
    }

    func testCleanReplyExtractsAnswerAfterThinking() {
        let raw = "<think>reason</think>\n[READ_FILE: ci.log]\ntrailing noise"
        XCTAssertEqual(LongHorizonRunner.cleanReply(raw), "[READ_FILE: ci.log]")
    }
}
