import Foundation

/// Vector recall over JGEN's own hidden states.
///
/// There is no second embedding model: `JGenBackend.encode` produces the
/// index, exactly as the IDE's `EternalMemoryStore` does. That has a real
/// consequence worth stating plainly — vectors written by one model are only
/// meaningful to a model sharing that hidden space. When the model is swapped
/// (the Qwen3.6 → Qwen3.8 experiment), `GapStore` carries over verbatim
/// because it is text, while this store must be re-embedded. `needsReembed`
/// reports that rather than silently returning nonsense neighbours.
///
/// Layout (both under the `--memory` directory):
///   `vectors.f16`  flat fp16, `dim` values per record, append-only
///   `vectors.jsonl` one JSON object per record, same order
public final class VectorMemory {

    public struct Record: Codable, Sendable {
        public var id: String
        public var text: String
        public var kind: String
        public var ts: Double
        public var accessCount: Int
        public var lastAccess: Double
        /// Which model produced the vector — the guard against cross-space recall.
        public var modelId: String
    }

    public struct Hit: Sendable {
        public let text: String
        public let kind: String
        public let score: Float
    }

    private let dim: Int
    private let modelId: String
    private let vectorsURL: URL
    private let indexURL: URL
    private var records: [Record] = []

    /// Half-life for the recency term, in days, before access-count widening.
    private static let gravityHalfLifeDays: Double = 30

    public init(directory: URL, dim: Int, modelId: String) throws {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        self.dim = dim
        self.modelId = modelId
        self.vectorsURL = directory.appendingPathComponent("vectors.f16")
        self.indexURL = directory.appendingPathComponent("vectors.jsonl")
        try loadIndex()
    }

    public var count: Int { records.count }

    /// True when the store holds vectors from a different model than the one
    /// now loaded. Those rows are excluded from recall — a cosine score across
    /// two unrelated hidden spaces is not a similarity, it is noise.
    public var needsReembed: Bool {
        records.contains { $0.modelId != modelId }
    }

    public var foreignRecordCount: Int {
        records.filter { $0.modelId != modelId }.count
    }

    // MARK: - Index

    private func loadIndex() throws {
        records = []
        guard let data = FileManager.default.contents(atPath: indexURL.path),
              let text = String(data: data, encoding: .utf8) else { return }
        let decoder = JSONDecoder()
        for line in text.split(separator: "\n") {
            guard let lineData = line.data(using: .utf8),
                  let record = try? decoder.decode(Record.self, from: lineData) else { continue }
            records.append(record)
        }
    }

    private func rewriteIndex() throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        var out = Data()
        for record in records {
            out.append(try encoder.encode(record))
            out.append(0x0A)
        }
        try out.write(to: indexURL, options: .atomic)
    }

    // MARK: - Write

    /// Stores one memory. `vector` is expected to come from
    /// `JGenBackend.encode` and is L2-normalised here so recall is a plain
    /// dot product.
    public func add(text: String, kind: String, vector: [Float]) throws {
        let normalised = Self.l2Normalised(Self.fit(vector, to: dim))
        let half = normalised.map { Float16($0) }

        let handle: FileHandle
        if FileManager.default.fileExists(atPath: vectorsURL.path) {
            handle = try FileHandle(forWritingTo: vectorsURL)
            try handle.seekToEnd()
        } else {
            FileManager.default.createFile(atPath: vectorsURL.path, contents: nil)
            handle = try FileHandle(forWritingTo: vectorsURL)
        }
        defer { try? handle.close() }
        try half.withUnsafeBufferPointer { buf in
            try handle.write(contentsOf: Data(buffer: buf))
        }

        let now = Date().timeIntervalSince1970
        records.append(Record(
            id: "v_" + UUID().uuidString.prefix(8).lowercased(),
            text: text, kind: kind, ts: now,
            accessCount: 0, lastAccess: now, modelId: modelId
        ))
        try rewriteIndex()
    }

    // MARK: - Read

    /// Cosine similarity re-ranked by a recency/frequency gravity term, so a
    /// memory that keeps proving useful stays reachable while a one-off from
    /// months ago fades without being deleted.
    public func search(vector: [Float], k: Int) throws -> [Hit] {
        guard !records.isEmpty, k > 0 else { return [] }
        guard let data = FileManager.default.contents(atPath: vectorsURL.path) else { return [] }

        let query = Self.l2Normalised(Self.fit(vector, to: dim))
        let stride = dim * MemoryLayout<Float16>.size
        let now = Date().timeIntervalSince1970

        var scored: [(index: Int, score: Float)] = []
        scored.reserveCapacity(records.count)

        for (i, record) in records.enumerated() {
            // Never score across hidden spaces (see `needsReembed`).
            guard record.modelId == modelId else { continue }
            let start = i * stride
            guard start + stride <= data.count else { break }

            var dot: Float = 0
            data.withUnsafeBytes { raw in
                let base = raw.baseAddress!.advanced(by: start)
                    .assumingMemoryBound(to: Float16.self)
                for j in 0..<dim {
                    dot += Float(base[j]) * query[j]
                }
            }

            let days = max(0, (now - record.lastAccess) / 86_400)
            let halfLife = Self.gravityHalfLifeDays * Double(1 + record.accessCount)
            let gravity = Float(pow(0.5, days / halfLife))
            scored.append((i, dot * (0.7 + 0.3 * gravity)))
        }

        scored.sort { $0.score > $1.score }
        let top = scored.prefix(k)

        // A recalled memory becomes slightly harder to forget.
        for entry in top {
            records[entry.index].accessCount += 1
            records[entry.index].lastAccess = now
        }
        if !top.isEmpty { try rewriteIndex() }

        return top.map { Hit(text: records[$0.index].text,
                             kind: records[$0.index].kind,
                             score: $0.score) }
    }

    /// Prompt block for the next turn. Empty when nothing is close enough to
    /// be worth the tokens.
    ///
    /// Each hit is truncated: recall must stay a fixed-size window into an
    /// unbounded store, otherwise remembering more would silently cost more
    /// per turn and the flat-cost property this runtime claims would not hold.
    public func recallBlock(
        vector: [Float], k: Int = 3, minScore: Float = 0.2, maxCharsPerHit: Int = 160
    ) throws -> String {
        let hits = try search(vector: vector, k: k).filter { $0.score >= minScore }
        guard !hits.isEmpty else { return "" }
        var lines = ["[RECALLED] from prior work on this mission"]
        for hit in hits {
            let text = hit.text.replacingOccurrences(of: "\n", with: " ")
            lines.append(String(format: "- (%@ %.2f) %@", hit.kind, hit.score,
                                String(text.prefix(maxCharsPerHit))))
        }
        return lines.joined(separator: "\n")
    }

    // MARK: - Helpers

    static func fit(_ vector: [Float], to dim: Int) -> [Float] {
        if vector.count == dim { return vector }
        if vector.count > dim { return Array(vector.prefix(dim)) }
        return vector + [Float](repeating: 0, count: dim - vector.count)
    }

    static func l2Normalised(_ vector: [Float]) -> [Float] {
        var sum: Float = 0
        for value in vector { sum += value * value }
        let norm = sum.squareRoot()
        guard norm > 1e-6 else { return vector }
        return vector.map { $0 / norm }
    }
}
