import Foundation
import CoreGraphics

/// A time-indexed sequence of small JGEN vectors representing one UI-
/// testing/bug-repro session's steps ("vector video") -- deliberately
/// reuses `EternalMemoryStore`'s exact fp16-vector + JSONL-sidecar storage
/// pattern rather than introducing a new one, per the user's own framing
/// ("Veraのベクトル版のような形"): one file pair per session, tiny vectors,
/// no image/video data ever touches disk, so a long testing session stays
/// cheap regardless of how many steps it takes.
///
/// No natural-language narration happens here -- each "moment" embeds only
/// the already-cheap tool-call label (e.g. "click 412,600"), never an
/// LLM-generated description. That keeps the per-step cost to one JGEN
/// `encode()` call, not a vision-model round trip; the one-shot,
/// end-of-session natural-language summary (`AgentLoop.swift`'s `[DONE]`
/// handler, already wired) is still where narration belongs.
actor UITestVectorTrace {
    static let shared = UITestVectorTrace()

    private static let dim = 1024

    struct Moment: Codable {
        let id: Int
        let ts: Double
        let stepIndex: Int
        let actionLabel: String
        /// [x, y, width, height] of the region `VisualDiffRegion` detected
        /// as changed by this step, or nil if no region was computed/found.
        let changedRegion: [Double]?
    }

    private var sessionDirectory: URL {
        let home = FileManager.default.homeDirectoryForCurrentUser
        return home.appendingPathComponent(".verantyx_chrono_swift/ui_traces", isDirectory: true)
    }

    private func vectorsURL(for sessionId: String) -> URL {
        sessionDirectory.appendingPathComponent("\(sessionId).vectors")
    }

    private func nodesURL(for sessionId: String) -> URL {
        sessionDirectory.appendingPathComponent("\(sessionId).nodes.jsonl")
    }

    private init() {}

    private func ensureDirectory() throws {
        try FileManager.default.createDirectory(at: sessionDirectory, withIntermediateDirectories: true)
    }

    /// Embeds `actionLabel` (not a natural-language description -- see
    /// file doc comment) via `JCrossChatManager.encodeText` and appends it
    /// as the next step in `sessionId`'s vector sequence.
    func recordMoment(sessionId: String, stepIndex: Int, actionLabel: String, changedRegion: CGRect?) async throws {
        try ensureDirectory()

        let clipped = PromptBudget.truncateForEncode(actionLabel)
        let prompt = "This sentence: \"\(clipped)\" means in one word:\""
        let raw = try await JCrossChatManager.shared.encodeText(prompt)
        let vec = Self.fitVec(Self.l2Normalize(raw))

        var fp16Bytes = Data(capacity: vec.count * 2)
        for f in vec {
            var half = Float16(f)
            withUnsafeBytes(of: &half) { fp16Bytes.append(contentsOf: $0) }
        }
        let vURL = vectorsURL(for: sessionId)
        if let handle = FileHandle(forWritingAtPath: vURL.path) {
            handle.seekToEndOfFile()
            handle.write(fp16Bytes)
            handle.closeFile()
        } else {
            FileManager.default.createFile(atPath: vURL.path, contents: fp16Bytes)
        }

        let region = changedRegion.map { [Double($0.origin.x), Double($0.origin.y), Double($0.width), Double($0.height)] }
        let existingCount = (try? countExistingNodes(sessionId: sessionId)) ?? stepIndex
        let moment = Moment(id: existingCount, ts: Date().timeIntervalSince1970, stepIndex: stepIndex, actionLabel: actionLabel, changedRegion: region)

        var data = try JSONEncoder().encode(moment)
        data.append(contentsOf: "\n".utf8)
        let nURL = nodesURL(for: sessionId)
        if let handle = FileHandle(forWritingAtPath: nURL.path) {
            handle.seekToEndOfFile()
            handle.write(data)
            handle.closeFile()
        } else {
            FileManager.default.createFile(atPath: nURL.path, contents: data)
        }
    }

    private func countExistingNodes(sessionId: String) throws -> Int {
        guard let data = FileManager.default.contents(atPath: nodesURL(for: sessionId).path),
              let text = String(data: data, encoding: .utf8) else { return 0 }
        return text.split(separator: "\n").count
    }

    /// Reads a session's steps back in order -- used both for the
    /// end-of-session natural-language summary and for the "UI Test Trace"
    /// 3D visualization (z = `stepIndex`).
    func trace(sessionId: String) async -> [Moment] {
        guard let data = FileManager.default.contents(atPath: nodesURL(for: sessionId).path),
              let text = String(data: data, encoding: .utf8) else { return [] }
        let moments: [Moment] = text.split(separator: "\n").compactMap { line in
            guard let d = line.data(using: .utf8) else { return nil }
            return try? JSONDecoder().decode(Moment.self, from: d)
        }
        return moments.sorted { $0.stepIndex < $1.stepIndex }
    }

    /// Text labels of the latest UI steps for jgen-vector-bus recall
    /// (council / speak / act). Action labels only — no raw vectors.
    func recallRecentBlock(sessionId: String, k: Int = 8) async -> String {
        let moments = await trace(sessionId: sessionId)
        guard !moments.isEmpty else { return "" }
        let recent = moments.suffix(k)
        let lines = recent.map { m in
            "  🧭 step \(m.stepIndex): \(m.actionLabel)"
        }.joined(separator: "\n")
        return "\n[UI TEST TRACE — recent steps]\n\(lines)\n[/UI TEST TRACE]\n"
    }

    private static func l2Normalize(_ v: [Float]) -> [Float] {
        let norm = sqrt(v.reduce(Float(0)) { $0 + $1 * $1 })
        guard norm > 0 else { return v }
        return v.map { $0 / norm }
    }

    private static func fitVec(_ v: [Float]) -> [Float] {
        if v.count == dim { return v }
        if v.count > dim { return Array(v.prefix(dim)) }
        return v + [Float](repeating: 0, count: dim - v.count)
    }
}
