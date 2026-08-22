import XCTest
@testable import VeraCore

/// The 0.5B model used for loop verification cannot reliably emit a tool tag,
/// so the tool path is pinned here directly rather than being left to whatever
/// a weak model happens to produce.
final class CLIToolParserTests: XCTestCase {

    func testParsesSimpleTags() {
        XCTAssertEqual(CLIToolParser.parseFirst("[READ_FILE: src/main.swift]"),
                       .readFile("src/main.swift"))
        XCTAssertEqual(CLIToolParser.parseFirst("[LIST_DIR: .]"), .listDir("."))
        XCTAssertEqual(CLIToolParser.parseFirst("[MAKE_DIR: build/out]"),
                       .makeDir("build/out"))
    }

    func testListDirDefaultsToWorkspaceRoot() {
        XCTAssertEqual(CLIToolParser.parseFirst("[LIST_DIR:]"), .listDir("."))
    }

    /// The IDE truncated commands at the first `]`; shell and file bodies
    /// contain brackets routinely, so matching must be balanced.
    func testBracketsInsidePayloadDoNotTruncate() {
        let tool = CLIToolParser.parseFirst("[RUN: grep -n 'arr[0]' src/main.swift]")
        XCTAssertEqual(tool, .runCommand("grep -n 'arr[0]' src/main.swift"))
    }

    func testWriteFileSplitsPathFromBody() {
        let tool = CLIToolParser.parseFirst("[WRITE_FILE: notes.md\nline one\nline two]")
        XCTAssertEqual(tool, .writeFile(path: "notes.md", content: "line one\nline two"))
    }

    func testIgnoresProseWithoutTags() {
        XCTAssertNil(CLIToolParser.parseFirst("I think we should look at the log file."))
    }
}

final class ToolExecutorTests: XCTestCase {

    private func makeWorkspace() -> URL {
        let dir = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("ws-" + UUID().uuidString)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    func testReadsFileInsideWorkspace() throws {
        let ws = makeWorkspace()
        defer { try? FileManager.default.removeItem(at: ws) }
        try "hdiutil attach failed".write(to: ws.appendingPathComponent("ci.log"),
                                          atomically: true, encoding: .utf8)

        let result = ToolExecutor(workspace: ws).execute(.readFile("ci.log"))
        XCTAssertTrue(result.ok)
        XCTAssertTrue(result.text.contains("hdiutil"))
    }

    /// Escapes must be caught after standardisation, not by looking for a
    /// leading "..".
    func testRefusesPathEscapingWorkspace() {
        let ws = makeWorkspace()
        defer { try? FileManager.default.removeItem(at: ws) }

        for path in ["../outside.txt", "a/../../etc/hosts", "/etc/hosts"] {
            let result = ToolExecutor(workspace: ws).execute(.readFile(path))
            XCTAssertFalse(result.ok, "should refuse \(path)")
            XCTAssertTrue(result.refused, "should refuse \(path)")
        }
    }

    func testReadOnlyPolicyRefusesMutationButSaysSo() {
        let ws = makeWorkspace()
        defer { try? FileManager.default.removeItem(at: ws) }

        let result = ToolExecutor(workspace: ws, policy: .readOnly)
            .execute(.writeFile(path: "x.txt", content: "hi"))
        XCTAssertFalse(result.ok)
        XCTAssertTrue(result.refused)
        // A refusal must be visible, never a silent no-op that reads as success.
        XCTAssertTrue(result.text.contains("refused"))
        XCTAssertFalse(FileManager.default.fileExists(atPath: ws.appendingPathComponent("x.txt").path))
    }

    func testAllowWriteStillRefusesShell() {
        let ws = makeWorkspace()
        defer { try? FileManager.default.removeItem(at: ws) }

        let executor = ToolExecutor(workspace: ws, policy: .allowWrite)
        XCTAssertTrue(executor.execute(.writeFile(path: "x.txt", content: "hi")).ok)
        let shell = executor.execute(.runCommand("echo hi"))
        XCTAssertFalse(shell.ok)
        XCTAssertTrue(shell.refused)
    }

    func testNonZeroExitIsReportedAsFailure() {
        let ws = makeWorkspace()
        defer { try? FileManager.default.removeItem(at: ws) }

        let result = ToolExecutor(workspace: ws, policy: .allowShell)
            .execute(.runCommand("echo out; exit 3"))
        XCTAssertFalse(result.ok, "a command that printed output but failed is still a failure")
        XCTAssertTrue(result.text.contains("exit 3"))
    }

    /// Vector memory removes the need to keep a conversation, but one oversized
    /// observation can still blow a single turn's prompt.
    func testLongObservationIsBounded() throws {
        let ws = makeWorkspace()
        defer { try? FileManager.default.removeItem(at: ws) }
        let big = String(repeating: "x", count: 50_000)
        try big.write(to: ws.appendingPathComponent("big.txt"), atomically: true, encoding: .utf8)

        let result = ToolExecutor(workspace: ws, maxObservationChars: 500).execute(.readFile("big.txt"))
        XCTAssertTrue(result.ok)
        XCTAssertLessThan(result.text.count, 1_000)
        XCTAssertTrue(result.text.contains("truncated"))
    }
}
