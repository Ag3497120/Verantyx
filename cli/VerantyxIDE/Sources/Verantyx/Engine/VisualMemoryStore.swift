import Foundation
import CoreGraphics

/// A memory of *what UI screens looked like*, stored via the same
/// fp16-vector + JSONL-sidecar mechanism `EternalMemoryStore` uses for
/// text -- but embedded with Apple's on-device Vision framework
/// (`VisualFeaturePrintEmbedder`) instead of JGEN's `encodeText`. This is
/// how the IDE gets a pseudo-multimodal memory without JGEN itself ever
/// touching an image: JGEN only ever sees the recalled text description
/// (`recallBlock`), never the feature-print vector.
///
/// Deliberately NOT a generalization of `EternalMemoryStore` sharing
/// implementation: the two differ in `dim` (Vision's feature-print length,
/// not JGEN's hidden size), embedding source (Vision request, not a JGEN
/// forward pass), node schema (`changedRegion`/`nearbyElements` instead of
/// `concepts`), and write-gating (only on a real `VisualDiffRegion` hit,
/// since a Vision request is far more expensive than JGEN's cached-prompt
/// text embed). `UITestVectorTrace` made the same call for the same
/// reasons -- this follows that precedent rather than forcing a shared
/// base that would need a `Node` protocol/associated type for ~60 lines of
/// storage plumbing.
///
/// Deliberately does **not** persist raw screenshot pixels: only the
/// derived feature-print vector, a text label, a bounding box, and nearby
/// UI-element name strings ever reach disk. Matches the "vector-only, not
/// video" decision already made for `UITestVectorTrace`/`VisualDiffRegion`.
actor VisualMemoryStore {
    static let shared = VisualMemoryStore()

    /// Vision's `VNFeaturePrintObservation.elementCount` is not a documented
    /// constant, so this is a storage target, not an assumption -- any
    /// vector is padded/truncated to it by `fitVec`, same as
    /// `EternalMemoryStore.fitVec` already does for JGEN vectors.
    private static let dim = 2048
    private static let gravityHalfLifeDays: Double = 30.0

    private struct Node: Codable {
        let id: Int
        let ts: Double
        var label: String
        var changedRegion: [Double]?   // [x, y, width, height], same shape as UITestVectorTrace.Moment
        var nearbyElements: [String]   // e.g. "SettingsButton@(420,610)"
        var accessCount: Int
        var lastAccess: Double
    }

    private let directory: URL
    private var vectorsURL: URL { directory.appendingPathComponent("visual.vectors") }
    private var nodesURL: URL { directory.appendingPathComponent("visual.nodes.jsonl") }

    private var nodes: [Node] = []
    private var loaded = false

    private init() {
        let home = FileManager.default.homeDirectoryForCurrentUser
        // A separate subdirectory from EternalMemoryStore's own files:
        // mixing a different `dim` into the same flat vector file would
        // corrupt `loadVector`'s fixed-offset seek arithmetic.
        directory = home.appendingPathComponent(".verantyx_chrono_swift/visual", isDirectory: true)
    }

    private func ensureLoaded() throws {
        guard !loaded else { return }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        if let data = FileManager.default.contents(atPath: nodesURL.path),
           let text = String(data: data, encoding: .utf8) {
            nodes = text.split(separator: "\n").compactMap { line in
                guard let d = line.data(using: .utf8) else { return nil }
                return try? JSONDecoder().decode(Node.self, from: d)
            }
        }
        loaded = true
    }

    /// Node count for Growth Console / multimodal status (no vectors exposed).
    func nodeCount() async -> Int {
        (try? ensureLoaded()) != nil ? nodes.count : 0
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

    /// Embeds a screenshot and appends it as a new visual-memory node.
    /// `nearbyElements` should already be filtered to whatever's near
    /// `changedRegion` -- this store doesn't do that filtering itself, see
    /// `AgentLoop.swift`'s call site for how the list is built from
    /// `VeraMemoryBridge.listVerifiedUIElements`.
    func add(base64Image: String, label: String, changedRegion: CGRect?, nearbyElements: [String]) async throws {
        try ensureLoaded()
        guard let raw = VisualFeaturePrintEmbedder.embed(base64Image: base64Image) else {
            throw VisualMemoryError.embeddingFailed
        }
        let vec = Self.fitVec(Self.l2Normalize(raw))

        var fp16Bytes = Data(capacity: vec.count * 2)
        for f in vec {
            var half = Float16(f)
            withUnsafeBytes(of: &half) { fp16Bytes.append(contentsOf: $0) }
        }
        if let handle = FileHandle(forWritingAtPath: vectorsURL.path) {
            handle.seekToEndOfFile()
            handle.write(fp16Bytes)
            handle.closeFile()
        } else {
            FileManager.default.createFile(atPath: vectorsURL.path, contents: fp16Bytes)
        }

        let region = changedRegion.map { [Double($0.origin.x), Double($0.origin.y), Double($0.width), Double($0.height)] }
        let node = Node(
            id: nodes.count, ts: Date().timeIntervalSince1970, label: label,
            changedRegion: region, nearbyElements: nearbyElements,
            accessCount: 0, lastAccess: Date().timeIntervalSince1970
        )
        nodes.append(node)
        try appendNodeLine(node)
    }

    private func appendNodeLine(_ node: Node) throws {
        var data = try JSONEncoder().encode(node)
        data.append(contentsOf: "\n".utf8)
        if let handle = FileHandle(forWritingAtPath: nodesURL.path) {
            handle.seekToEndOfFile()
            handle.write(data)
            handle.closeFile()
        } else {
            FileManager.default.createFile(atPath: nodesURL.path, contents: data)
        }
    }

    private func rewriteIndex() throws {
        var out = Data()
        for node in nodes {
            var data = try JSONEncoder().encode(node)
            data.append(contentsOf: "\n".utf8)
            out.append(data)
        }
        try out.write(to: nodesURL, options: .atomic)
    }

    private func loadVector(at index: Int) -> [Float]? {
        guard let handle = FileHandle(forReadingAtPath: vectorsURL.path) else { return nil }
        defer { handle.closeFile() }
        let byteOffset = UInt64(index * Self.dim * 2)
        handle.seek(toFileOffset: byteOffset)
        guard let data = try? handle.read(upToCount: Self.dim * 2), data.count == Self.dim * 2 else { return nil }
        var out = [Float](repeating: 0, count: Self.dim)
        data.withUnsafeBytes { raw in
            let half = raw.bindMemory(to: Float16.self)
            for i in 0..<Self.dim { out[i] = Float(half[i]) }
        }
        return out
    }

    private func gravity(daysSinceAccess: Double, accessCount: Int) -> Double {
        let halfLife = Self.gravityHalfLifeDays * Double(1 + accessCount)
        guard halfLife > 0 else { return 1 }
        return pow(0.5, daysSinceAccess / halfLife)
    }

    /// Cosine similarity against every stored screen, re-ranked by the same
    /// recency/access-count gravity decay as `EternalMemoryStore.search`.
    /// The query is a screenshot, not text -- this is fundamentally
    /// screen-to-screen recall ("does *this* screen resemble one we've
    /// seen"), not text-to-screen; a Vision feature print cannot be
    /// produced from a word alone.
    func search(base64Image: String, k: Int) async throws -> [(node: NodeSummary, score: Float)] {
        try ensureLoaded()
        guard !nodes.isEmpty else { return [] }
        guard let raw = VisualFeaturePrintEmbedder.embed(base64Image: base64Image) else {
            throw VisualMemoryError.embeddingFailed
        }
        let qv = Self.fitVec(Self.l2Normalize(raw))

        var scored: [(index: Int, eff: Float, sim: Float)] = []
        let now = Date().timeIntervalSince1970
        for (i, node) in nodes.enumerated() {
            guard let vec = loadVector(at: i) else { continue }
            var dot: Float = 0
            for j in 0..<Self.dim { dot += vec[j] * qv[j] }
            let daysSince = max((now - node.lastAccess) / 86400.0, 0)
            let grav = Float(gravity(daysSinceAccess: daysSince, accessCount: node.accessCount))
            let eff = dot * (0.7 + 0.3 * grav)
            scored.append((i, eff, dot))
        }
        scored.sort { $0.eff > $1.eff }
        let top = Array(scored.prefix(k))

        for hit in top {
            nodes[hit.index].accessCount += 1
            nodes[hit.index].lastAccess = now
        }
        if !top.isEmpty { try rewriteIndex() }

        return top.map { hit in
            let n = nodes[hit.index]
            return (NodeSummary(label: n.label, changedRegion: n.changedRegion,
                                nearbyElements: n.nearbyElements, lastAccess: n.lastAccess),
                    hit.sim)
        }
    }

    struct NodeSummary {
        let label: String
        let changedRegion: [Double]?
        let nearbyElements: [String]
        let lastAccess: Double
    }

    /// Text-block recall, same shape as `EternalMemoryStore.recallBlock` --
    /// this is the ONLY thing that ever reaches a chat/council prompt.
    /// JGEN never sees the feature-print vector itself.
    func recallBlock(base64Image: String, k: Int = 3) async -> String {
        guard let hits = try? await search(base64Image: base64Image, k: k), !hits.isEmpty else { return "" }
        let now = Date().timeIntervalSince1970
        let lines = hits.map { hit -> String in
            let n = hit.node
            let agoSeconds = max(now - n.lastAccess, 0)
            let ago = Self.humanElapsed(agoSeconds)
            let regionDesc = n.changedRegion.map {
                "region (\(Int($0[0])),\(Int($0[1])) \(Int($0[2]))x\(Int($0[3])))"
            } ?? "unknown region"
            let nearby = n.nearbyElements.isEmpty ? "" : " near " + n.nearbyElements.joined(separator: ", ")
            return "  👁️ \(n.label) — \(regionDesc)\(nearby), seen \(ago) (score: \(String(format: "%.2f", hit.score)))"
        }.joined(separator: "\n")
        return "\n[VISUAL MEMORY — Vision feature-print recall]\n\(lines)\n[/VISUAL MEMORY]\n"
    }

    /// Recency-only text labels for the jgen-vector-bus path when there is
    /// no current screenshot to query Vision-space with. Labels only —
    /// never the feature-print vector.
    func recallRecentLabelsBlock(k: Int = 3) async -> String {
        guard (try? ensureLoaded()) != nil else { return "" }
        guard !nodes.isEmpty else { return "" }
        let now = Date().timeIntervalSince1970
        let recent = nodes.sorted { $0.lastAccess > $1.lastAccess }.prefix(k)
        let lines = recent.map { n -> String in
            let ago = Self.humanElapsed(max(now - n.lastAccess, 0))
            let nearby = n.nearbyElements.isEmpty ? "" : " near " + n.nearbyElements.prefix(4).joined(separator: ", ")
            return "  👁️ \(n.label)\(nearby), seen \(ago)"
        }.joined(separator: "\n")
        return "\n[VISUAL MEMORY — recent labels]\n\(lines)\n[/VISUAL MEMORY]\n"
    }

    private static func humanElapsed(_ seconds: Double) -> String {
        if seconds < 60 { return "just now" }
        if seconds < 3600 { return "\(Int(seconds / 60))m ago" }
        if seconds < 86400 { return "\(Int(seconds / 3600))h ago" }
        return "\(Int(seconds / 86400))d ago"
    }

    enum VisualMemoryError: Error, LocalizedError {
        case embeddingFailed
        var errorDescription: String? { "Vision feature-print extraction failed" }
    }
}
