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
        /// Width of this record's vector. Models differ (896 / 1024 / 2048 /
        /// 2560 across the converted set), so the file is heterogeneous and a
        /// single global stride would read into a neighbouring record.
        public var dim: Int
        /// Byte offset into `vectors.f16`. Stored rather than derived for the
        /// same reason.
        public var offset: Int
        /// Shape of the situation this was recorded under. Lets recall be
        /// driven by structure rather than clock time alone.
        public var signature: StructuralSignature?
        /// Which agent wrote it. Subagents sharing one model share one vector
        /// space by construction — this records provenance, it does not
        /// partition the store.
        public var agentId: String?
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
    public func add(
        text: String, kind: String, vector: [Float],
        signature: StructuralSignature? = nil, agentId: String? = nil
    ) throws {
        let normalised = Self.l2Normalised(Self.fit(vector, to: dim))
        let now = Date().timeIntervalSince1970
        let offset = try appendVector(normalised)
        records.append(Record(
            id: "v_" + UUID().uuidString.prefix(8).lowercased(),
            text: text, kind: kind, ts: now,
            accessCount: 0, lastAccess: now, modelId: modelId,
            dim: dim, offset: offset,
            signature: signature, agentId: agentId
        ))
        try rewriteIndex()
    }

    /// Appends fp16 values and returns the byte offset they were written at.
    private func appendVector(_ values: [Float]) throws -> Int {
        let half = values.map { Float16($0) }
        let handle: FileHandle
        var offset = 0
        if FileManager.default.fileExists(atPath: vectorsURL.path) {
            handle = try FileHandle(forWritingTo: vectorsURL)
            offset = Int(try handle.seekToEnd())
        } else {
            FileManager.default.createFile(atPath: vectorsURL.path, contents: nil)
            handle = try FileHandle(forWritingTo: vectorsURL)
        }
        defer { try? handle.close() }
        try half.withUnsafeBufferPointer { buf in
            try handle.write(contentsOf: Data(buffer: buf))
        }
        return offset
    }

    // MARK: - Read

    /// Cosine similarity re-ranked by a recency/frequency gravity term, so a
    /// memory that keeps proving useful stays reachable while a one-off from
    /// months ago fades without being deleted.
    ///
    /// When `against` is supplied, a memory recorded under a structurally
    /// matching situation is lifted. This is the answer to "how should memory
    /// age": not purely by the clock. A six-month-old record of the same
    /// failure shape you are stuck on now is more use than yesterday's
    /// unrelated note, and time decay alone would have it the other way round.
    /// Time still participates — it just stops being the only judge.
    public func search(
        vector: [Float], k: Int, against signature: StructuralSignature? = nil
    ) throws -> [Hit] {
        guard !records.isEmpty, k > 0 else { return [] }
        guard let data = FileManager.default.contents(atPath: vectorsURL.path) else { return [] }

        let query = Self.l2Normalised(Self.fit(vector, to: dim))
        let now = Date().timeIntervalSince1970

        var scored: [(index: Int, score: Float)] = []
        scored.reserveCapacity(records.count)

        for (i, record) in records.enumerated() {
            // Never score across hidden spaces (see `needsReembed`). This also
            // guarantees `record.dim == dim` below, since one model has one
            // hidden size.
            guard record.modelId == modelId else { continue }
            let start = record.offset
            let byteCount = record.dim * MemoryLayout<Float16>.size
            guard start >= 0, start + byteCount <= data.count else { continue }

            var dot: Float = 0
            data.withUnsafeBytes { raw in
                let base = raw.baseAddress!.advanced(by: start)
                    .assumingMemoryBound(to: Float16.self)
                for j in 0..<min(record.dim, query.count) {
                    dot += Float(base[j]) * query[j]
                }
            }

            let level: StructuralSignature.MatchLevel = {
                guard let signature, let recorded = record.signature else { return .notComparable }
                return signature.match(recorded)
            }()

            let days = max(0, (now - record.lastAccess) / 86_400)
            // Three things resist forgetting: being recent, having proved
            // useful before, and matching the shape of the current problem.
            // The third is what stops the clock alone deciding relevance.
            let halfLife = Self.gravityHalfLifeDays
                * Double(1 + record.accessCount)
                * level.ageResistance
            let gravity = Float(pow(0.5, days / halfLife))
            scored.append((i, dot * (0.7 + 0.3 * gravity) + level.recallBoost))
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
        vector: [Float], k: Int = 3, minScore: Float = 0.2, maxCharsPerHit: Int = 160,
        against signature: StructuralSignature? = nil
    ) throws -> String {
        let hits = try search(vector: vector, k: k, against: signature)
            .filter { $0.score >= minScore }
        guard !hits.isEmpty else { return "" }
        var lines = ["[RECALLED] from prior work on this mission"]
        for hit in hits {
            let text = hit.text.replacingOccurrences(of: "\n", with: " ")
            lines.append(String(format: "- (%@ %.2f) %@", hit.kind, hit.score,
                                String(text.prefix(maxCharsPerHit))))
        }
        return lines.joined(separator: "\n")
    }

    // MARK: - Model swap

    public struct ReembedResult: Sendable {
        public let migrated: Int
        public let kept: Int
        public let failed: Int
    }

    /// Re-encodes every foreign record's **text** with the currently loaded
    /// model, so accumulated experience survives a model swap.
    ///
    /// This is the piece that makes "the model forgets, the agent does not"
    /// true of the vector half of memory as well. `GapStore` carries over for
    /// free because it is text; vectors cannot, because a hidden state is only
    /// meaningful inside the space that produced it. Storing the source text
    /// next to each vector is what makes re-embedding possible at all —
    /// without it a swap would silently discard everything learned.
    ///
    /// Preserved across the migration: `ts`, `accessCount`, `lastAccess`. How
    /// old a memory is and how often it proved useful are properties of the
    /// experience, not of the model that encoded it.
    ///
    /// The store is rewritten in place via a temporary file, so an interrupted
    /// migration leaves the original intact rather than half-converted.
    @discardableResult
    public func reembed(using encode: (String) throws -> [Float]) throws -> ReembedResult {
        guard needsReembed else { return ReembedResult(migrated: 0, kept: records.count, failed: 0) }

        let tempURL = vectorsURL.appendingPathExtension("migrating")
        FileManager.default.createFile(atPath: tempURL.path, contents: nil)
        let handle = try FileHandle(forWritingTo: tempURL)

        var rebuilt: [Record] = []
        rebuilt.reserveCapacity(records.count)
        var migrated = 0, kept = 0, failed = 0
        let existing = FileManager.default.contents(atPath: vectorsURL.path) ?? Data()

        for record in records {
            var updated = record
            var values: [Float]

            if record.modelId == modelId {
                // Already in this space — copy the bytes across unchanged.
                let byteCount = record.dim * MemoryLayout<Float16>.size
                guard record.offset + byteCount <= existing.count else { failed += 1; continue }
                let slice = existing[record.offset ..< record.offset + byteCount]
                var half = [Float16](repeating: 0, count: record.dim)
                _ = half.withUnsafeMutableBytes { slice.copyBytes(to: $0) }
                values = half.map { Float($0) }
                kept += 1
            } else {
                guard let fresh = try? encode(record.text) else { failed += 1; continue }
                values = Self.l2Normalised(Self.fit(fresh, to: dim))
                updated.modelId = modelId
                updated.dim = dim
                migrated += 1
            }

            updated.offset = Int(try handle.seekToEnd())
            let half = values.map { Float16($0) }
            try half.withUnsafeBufferPointer { try handle.write(contentsOf: Data(buffer: $0)) }
            rebuilt.append(updated)
        }

        try handle.close()
        _ = try FileManager.default.replaceItemAt(vectorsURL, withItemAt: tempURL)
        records = rebuilt
        try rewriteIndex()
        return ReembedResult(migrated: migrated, kept: kept, failed: failed)
    }

    /// Distinct models that have written into this store.
    public var modelIds: [String] {
        Array(Set(records.map(\.modelId))).sorted()
    }

    #if DEBUG
    /// Backdates every record so decay behaviour can be tested without waiting
    /// months. Test-only; not part of the public contract.
    func debugSetAge(days: Double) {
        let then = Date().timeIntervalSince1970 - days * 86_400
        for i in records.indices {
            records[i].ts = then
            records[i].lastAccess = then
        }
    }
    #endif

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
