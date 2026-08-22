import XCTest
@testable import VeraCore

/// Structure, not wording, decides whether past work is relevant — and it is
/// what keeps an old-but-matching memory reachable when time decay alone would
/// have buried it.
final class StructuralSignatureTests: XCTestCase {

    private func sig(
        type: String = "MISSION", role: String? = "mission",
        failure: String? = "tool_failed", transition: String? = "no_change",
        resolved: Bool = false
    ) -> StructuralSignature {
        StructuralSignature(nodeType: type, role: role, failureType: failure,
                            observedTransition: transition, resolved: resolved)
    }

    /// Unset fields must not read as "equal" — two blank signatures matching
    /// would make every memory relevant to every situation.
    func testUnsetFieldsAreNotComparable() {
        XCTAssertEqual(sig(role: nil).match(sig()), .notComparable)
        XCTAssertEqual(sig(failure: nil).match(sig()), .notComparable)
        XCTAssertEqual(sig().match(sig(role: nil)), .notComparable)
    }

    func testRoleOrFailureMismatchDisqualifies() {
        XCTAssertEqual(sig(role: "mission").match(sig(role: "subtask")), .notComparable)
        XCTAssertEqual(sig(failure: "tool_failed").match(sig(failure: "refused_by_policy")),
                       .notComparable)
    }

    /// Different wording, same shape — the case this exists for.
    func testSameShapeDifferentTopicStillMatches() {
        let saveBug = sig()
        let exportBug = sig()
        XCTAssertEqual(saveBug.match(exportBug), .highConfidence)
    }

    func testDifferingTransitionDropsToCandidate() {
        XCTAssertEqual(sig(transition: "no_change").match(sig(transition: "changed")),
                       .structuralCandidate)
    }

    /// A settled twin is the most valuable neighbour: it carries a strategy
    /// that already worked.
    func testResolvedTwinIsSkillReuseCandidate() {
        XCTAssertEqual(sig().match(sig(resolved: true)), .skillReuseCandidate)
    }

    func testBoostOrderingFollowsMatchStrength() {
        XCTAssertGreaterThan(StructuralSignature.MatchLevel.skillReuseCandidate.recallBoost,
                             StructuralSignature.MatchLevel.highConfidence.recallBoost)
        XCTAssertGreaterThan(StructuralSignature.MatchLevel.highConfidence.recallBoost,
                             StructuralSignature.MatchLevel.structuralCandidate.recallBoost)
        // Noise must contribute nothing, not a small nudge that accumulates.
        XCTAssertEqual(StructuralSignature.MatchLevel.notComparable.recallBoost, 0)
    }

    func testDerivedFromGapNodeCarriesShape() {
        var gap = GapNode(gapId: "g1", gapType: "MISSION", subject: "audit",
                          scope: "mission", severity: .quality)
        gap.failureType = "tool_failed"
        gap.observedTransition = "no_change"
        let signature = StructuralSignature(gap: gap)
        XCTAssertEqual(signature.role, "mission")
        XCTAssertEqual(signature.failureType, "tool_failed")
        XCTAssertFalse(signature.resolved)
    }
}

/// Records carry provenance and shape; the store itself stays shared so
/// subagents on one model can recall each other's work.
final class VectorMemoryStructuralTests: XCTestCase {

    private func makeMemory(dim: Int = 4, model: String = "m.jgen") throws -> (VectorMemory, URL) {
        let dir = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("vm-" + UUID().uuidString)
        return (try VectorMemory(directory: dir, dim: dim, modelId: model), dir)
    }

    /// The aging claim, stated as a test: an old memory of the right shape must
    /// survive the clock, while an equally-similar recent one of the wrong
    /// shape does not automatically win.
    func testStructuralMatchSlowsForgetting() throws {
        let (memory, dir) = try makeMemory()
        defer { try? FileManager.default.removeItem(at: dir) }

        let shape = StructuralSignature(nodeType: "MISSION", role: "mission",
                                        failureType: "tool_failed",
                                        observedTransition: "no_change", resolved: true)
        let other = StructuralSignature(nodeType: "MISSION", role: "mission",
                                        failureType: "refused_by_policy",
                                        observedTransition: "no_change")

        // Same content similarity; both aged well past the base half-life.
        try memory.add(text: "old, matching shape", kind: "step",
                       vector: [1, 0, 0, 0], signature: shape)
        try memory.add(text: "old, unrelated shape", kind: "step",
                       vector: [1, 0, 0, 0], signature: other)
        memory.debugSetAge(days: 180)

        let hits = try memory.search(vector: [1, 0, 0, 0], k: 2, against: shape)
        XCTAssertEqual(hits.first?.text, "old, matching shape",
                       "a matching shape must resist decay that buries the unrelated one")
        XCTAssertGreaterThan(hits[0].score, hits[1].score)
    }

    /// Structure ranks, it does not overrule content: a genuinely close memory
    /// still beats an unrelated one that merely shares a shape.
    func testStructureDoesNotOverrideContentSimilarity() throws {
        let (memory, dir) = try makeMemory()
        defer { try? FileManager.default.removeItem(at: dir) }

        let shape = StructuralSignature(nodeType: "MISSION", role: "mission",
                                        failureType: "tool_failed",
                                        observedTransition: "no_change", resolved: true)
        try memory.add(text: "orthogonal but same shape", kind: "step",
                       vector: [0, 1, 0, 0], signature: shape)
        try memory.add(text: "exact content match", kind: "step", vector: [1, 0, 0, 0])

        let hits = try memory.search(vector: [1, 0, 0, 0], k: 2, against: shape)
        XCTAssertEqual(hits.first?.text, "exact content match")
    }

    /// Two subagents, one model, one store: what one records the other recalls.
    func testSubagentsShareOneVectorSpace() throws {
        let (writer, dir) = try makeMemory()
        defer { try? FileManager.default.removeItem(at: dir) }
        try writer.add(text: "scout found the failing step", kind: "observation",
                       vector: [1, 0, 0, 0], agentId: "scout")

        // A different agent opening the same directory on the same model.
        let reader = try VectorMemory(directory: dir, dim: 4, modelId: "m.jgen")
        XCTAssertFalse(reader.needsReembed)
        let hits = try reader.search(vector: [1, 0, 0, 0], k: 1)
        XCTAssertEqual(hits.first?.text, "scout found the failing step")
    }

    /// Provenance is recorded but must not partition recall — partitioning
    /// would defeat the sharing the design is after.
    func testAgentIdDoesNotFilterRecall()
        throws {
        let (memory, dir) = try makeMemory()
        defer { try? FileManager.default.removeItem(at: dir) }
        try memory.add(text: "from worker", kind: "step", vector: [1, 0, 0, 0], agentId: "worker")

        let hits = try memory.search(vector: [1, 0, 0, 0], k: 1)
        XCTAssertEqual(hits.first?.text, "from worker")
    }
}
