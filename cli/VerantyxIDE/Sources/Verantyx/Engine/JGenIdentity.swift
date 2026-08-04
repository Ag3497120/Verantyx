import Foundation
import CryptoKit

/// Model identity for distributed inference: "do these two Macs hold the same
/// model?"
///
/// The engine has no notion of this at all — the JGEN header is magic + version
/// + tensor count, the sidecar carries architecture fields only, and there is no
/// hashing crate in the Rust crate. So it is built here rather than over FFI,
/// which is also the only place it *can* live: the receiving machine may not have
/// the file yet, and `jcross_engine_create` would have to succeed (mmap, the
/// `embed_tokens` requirement, the load-time geometry check) before it could hash
/// anything.
///
/// Three hashes, because "identical" means different things for the three
/// artifacts a model is made of:
///
///  - `structuralHash` — the tensor table. Milliseconds even on a 57 GB file,
///    and it already separates ~every real case ("the worker has nothing",
///    "the worker has a different quantisation").
///  - `contentHash` — the weight bytes. Sampled by default; full on request.
///  - `metaHash` — the sidecar, **canonicalised**. It can never match byte-for-byte
///    across machines: `meta["tokenizer"]` is an absolute path containing the
///    user's account name, and the two Macs here are `motonishikoudai` and
///    `motonisihikoudai`. Comparing raw sidecar bytes would report "different
///    model" on every single pairing.
enum JGenIdentity {

    // MARK: - Types

    struct TensorEntry {
        let name: String
        let type: UInt8          // 1 SVDLossless, 2 Dense2D, 3 Dense1D
        let dims: [UInt32]
        let dataOffset: UInt64
        let byteLength: UInt64
    }

    /// Parsed tensor table plus the byte accounting the split planner needs.
    struct Layout {
        let version: UInt32
        let fileSize: UInt64
        let entries: [TensorEntry]

        /// Bytes belonging to `…layers.<i>.…`, keyed by layer index.
        let perLayerBytes: [Int: UInt64]
        /// Everything not attributable to a numbered layer.
        let nonLayerBytes: UInt64
        /// `embed_tokens` — paid by whichever machine turns tokens into vectors.
        let embedBytes: UInt64
        /// `lm_head` — paid by whichever machine produces logits.
        let lmHeadBytes: UInt64

        var layerCount: Int { (perLayerBytes.keys.max().map { $0 + 1 }) ?? 0 }

        func bytes(inLayers range: Range<Int>) -> UInt64 {
            range.reduce(UInt64(0)) { $0 + (perLayerBytes[$1] ?? 0) }
        }
    }

    struct Identity: Codable, Equatable {
        enum ContentHashKind: String, Codable { case sampled, full }

        let fileSize: UInt64
        let structuralHash: String
        var contentHash: String?
        var contentHashKind: ContentHashKind?
        let metaHash: String

        /// True when both sides have a content hash computed the same way.
        func contentComparable(with other: Identity) -> Bool {
            contentHash != nil && other.contentHash != nil
                && contentHashKind == other.contentHashKind
        }
    }

    /// What the UI should offer, given a local and a remote identity.
    enum Verdict: Equatable {
        /// Same weights, same effective sidecar. Hide the transfer affordance.
        case identical
        /// Structure or size differs — a real transfer is needed.
        case differentWeights(reason: String)
        /// Weights match but the sidecar disagrees. Re-copying gigabytes will not
        /// fix a `num_layers` mismatch, so this is deliberately not a transfer.
        case sameWeightsDifferentMeta
        /// Structure matches; content hashes not both available yet.
        case needsContentHash
    }

    enum IdentityError: LocalizedError {
        case notJGEN(String)
        case unsupportedVersion(UInt32)
        case truncated(String)
        case unknownTensorType(UInt8, String)

        var errorDescription: String? {
            switch self {
            case .notJGEN(let p):            return "Not a JGEN file: \(p)"
            case .unsupportedVersion(let v): return "Unsupported JGEN version: \(v)"
            case .truncated(let p):          return "JGEN file ends mid-table: \(p)"
            case .unknownTensorType(let t, let n):
                return "Unknown JGEN tensor type \(t) at '\(n)'"
            }
        }
    }

    // MARK: - Table walk

    /// Parses the JGEN v3 tensor table.
    ///
    /// Mirrors `load_jgen` in `jcross_engine_glm/src/lib.rs` exactly, including
    /// the SVDLossless byte length — that one is **not** `rows*rank + rank*cols`;
    /// the record covers six sub-tensors (U, S, V, mod_x, mod_y, c_valve) and
    /// getting it wrong desynchronises the walk from the first SVD tensor onward.
    ///
    /// The table is interleaved with the data, so this seeks rather than reads:
    /// one small header read plus one skip per tensor, ~40 bytes touched each.
    /// On a 57 GB file with ~1000 tensors that is a few milliseconds.
    static func readLayout(at url: URL) throws -> Layout {
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }

        let fileSize = (try FileManager.default.attributesOfItem(atPath: url.path)[.size] as? NSNumber)?
            .uint64Value ?? 0

        func read(_ n: Int, at off: UInt64) throws -> Data {
            try handle.seek(toOffset: off)
            guard let d = try handle.read(upToCount: n), d.count == n else {
                throw IdentityError.truncated(url.lastPathComponent)
            }
            return d
        }
        func u16(_ d: Data, _ i: Int) -> UInt16 {
            UInt16(d[d.startIndex + i]) | (UInt16(d[d.startIndex + i + 1]) << 8)
        }
        func u32(_ d: Data, _ i: Int) -> UInt32 {
            var v: UInt32 = 0
            for k in (0..<4).reversed() { v = (v << 8) | UInt32(d[d.startIndex + i + k]) }
            return v
        }

        let head = try read(12, at: 0)
        guard head.prefix(4).elementsEqual("JGEN".utf8) else {
            throw IdentityError.notJGEN(url.lastPathComponent)
        }
        let version = u32(head, 4)
        guard version == 3 else { throw IdentityError.unsupportedVersion(version) }
        let tensorCount = Int(u32(head, 8))

        var entries: [TensorEntry] = []
        entries.reserveCapacity(tensorCount)
        var offset: UInt64 = 12

        // Generous enough for the longest tensor name plus type and dims; the
        // walk reads one of these per tensor instead of five tiny reads.
        let headerWindow = 512

        for _ in 0..<tensorCount {
            guard offset < fileSize else { throw IdentityError.truncated(url.lastPathComponent) }
            let want = min(headerWindow, Int(fileSize - offset))
            let win = try read(want, at: offset)

            let nameLen = Int(u16(win, 0))
            guard 2 + nameLen + 1 <= win.count else {
                throw IdentityError.truncated(url.lastPathComponent)
            }
            let nameBytes = win.subdata(in: (win.startIndex + 2)..<(win.startIndex + 2 + nameLen))
            let name = String(decoding: nameBytes, as: UTF8.self)
            var p = 2 + nameLen
            let type = win[win.startIndex + p]
            p += 1

            let dims: [UInt32]
            let byteLength: UInt64
            switch type {
            case 1: // SVDLossless
                let r = UInt64(u32(win, p)), c = UInt64(u32(win, p + 4)), k = UInt64(u32(win, p + 8))
                dims = [UInt32(r), UInt32(c), UInt32(k)]
                // U + S + V + mod_x + mod_y + c_valve, all f16.
                byteLength = (r * k + k + c * k + c + r + k * k) * 2
                p += 12
            case 2: // Dense2D
                let r = UInt64(u32(win, p)), c = UInt64(u32(win, p + 4))
                dims = [UInt32(r), UInt32(c)]
                byteLength = r * c * 2
                p += 8
            case 3: // Dense1D
                let n = UInt64(u32(win, p))
                dims = [UInt32(n)]
                byteLength = n * 2
                p += 4
            default:
                throw IdentityError.unknownTensorType(type, name)
            }

            let dataOffset = offset + UInt64(p)
            entries.append(TensorEntry(name: name, type: type, dims: dims,
                                       dataOffset: dataOffset, byteLength: byteLength))
            offset = dataOffset + byteLength
        }

        // Byte accounting. `.layers.<i>.` is the same convention the engine uses
        // to infer num_layers, so a layer's real cost comes from the file rather
        // than from a parameter-count estimate.
        var perLayer: [Int: UInt64] = [:]
        var nonLayer: UInt64 = 0
        var embed: UInt64 = 0
        var lmHead: UInt64 = 0
        for e in entries {
            if let idx = layerIndex(of: e.name) {
                perLayer[idx, default: 0] += e.byteLength
            } else {
                nonLayer += e.byteLength
                if e.name.contains("embed_tokens") { embed += e.byteLength }
                if e.name.hasPrefix("lm_head") || e.name.contains(".lm_head") {
                    lmHead += e.byteLength
                }
            }
        }

        return Layout(version: version, fileSize: fileSize, entries: entries,
                      perLayerBytes: perLayer, nonLayerBytes: nonLayer,
                      embedBytes: embed, lmHeadBytes: lmHead)
    }

    private static func layerIndex(of name: String) -> Int? {
        guard let r = name.range(of: ".layers.") else { return nil }
        let rest = name[r.upperBound...]
        guard let dot = rest.firstIndex(of: ".") else { return nil }
        return Int(rest[rest.startIndex..<dot])
    }

    // MARK: - Structural hash

    /// SHA-256 over the header and the full tensor table, in file order.
    ///
    /// Deliberately includes each tensor's offset and byte length, not just its
    /// name and dims: two files can agree on every tensor's shape and still be
    /// laid out differently, and the sampled content hash below picks its windows
    /// from this digest — so both machines must agree on layout before those
    /// windows mean anything.
    static func structuralHash(of layout: Layout) -> String {
        var h = SHA256()
        h.update(data: Data("JGEN".utf8))
        h.update(data: le32(layout.version))
        h.update(data: le32(UInt32(layout.entries.count)))
        h.update(data: le64(layout.fileSize))
        for e in layout.entries {
            h.update(data: le16(UInt16(e.name.utf8.count)))
            h.update(data: Data(e.name.utf8))
            h.update(data: Data([e.type]))
            for d in e.dims { h.update(data: le32(d)) }
            h.update(data: le64(e.dataOffset))
            h.update(data: le64(e.byteLength))
        }
        return hex(h.finalize())
    }

    // MARK: - Content hash

    private static let sampleWindow = 1 << 20   // 1 MB
    private static let sampleCount = 64

    /// SHA-256 over 64 deterministically chosen 1 MB windows plus the first and
    /// last megabyte. ~64 MB read, well under a second.
    ///
    /// The window offsets are derived from `structuralHash`, so two machines that
    /// agree structurally sample the *same* bytes — without that the comparison
    /// would be meaningless. Machines that disagree structurally never reach this
    /// step, so the circularity is harmless.
    ///
    /// What this does and does not catch, measured rather than assumed: flipping
    /// a single bit inside `model.layers.19.self_attn.v_proj.weight` of a 1.15 GB
    /// model went **undetected** here (66 MB of 1.15 GB is read) while
    /// `fullContentHash` caught it. That is the intended trade, because the
    /// realistic alternatives at pairing time — the peer has nothing, a different
    /// quantisation, a different conversion run — all differ in size or tensor
    /// layout and are already resolved before this runs. Silent bit rot is not,
    /// so anything that must be bit-exact (a completed transfer) should verify
    /// against a full hash, not this one.
    static func sampledContentHash(of url: URL, structuralHash: String, fileSize: UInt64) throws -> String {
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }

        var offsets: [UInt64] = [0]
        if fileSize > UInt64(sampleWindow) {
            offsets.append(fileSize - UInt64(sampleWindow))
        }
        // SplitMix64 seeded from the structural digest: deterministic, identical
        // on both machines, and not sensitive to Swift's hashing seed.
        var state = seed64(from: structuralHash)
        let span = fileSize > UInt64(sampleWindow) ? fileSize - UInt64(sampleWindow) : 1
        for _ in 0..<sampleCount {
            state = state &+ 0x9E37_79B9_7F4A_7C15
            var z = state
            z = (z ^ (z >> 30)) &* 0xBF58_476D_1CE4_E5B9
            z = (z ^ (z >> 27)) &* 0x94D0_49BB_1331_11EB
            z = z ^ (z >> 31)
            offsets.append(z % span)
        }
        offsets.sort()

        var h = SHA256()
        h.update(data: le64(fileSize))
        for off in offsets {
            try handle.seek(toOffset: off)
            let want = Int(min(UInt64(sampleWindow), fileSize - off))
            guard let d = try handle.read(upToCount: want) else { continue }
            h.update(data: le64(off))
            h.update(data: d)
        }
        return hex(h.finalize())
    }

    /// Streaming SHA-256 over the whole file. Disk-bound: roughly 30 s for 57 GB
    /// on an M1, and it evicts the page cache — offer it, do not do it by default.
    static func fullContentHash(of url: URL, progress: ((Double) -> Void)? = nil) throws -> String {
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        let fileSize = (try FileManager.default.attributesOfItem(atPath: url.path)[.size] as? NSNumber)?
            .uint64Value ?? 0
        var h = SHA256()
        var done: UInt64 = 0
        let chunk = 8 << 20
        while let d = try handle.read(upToCount: chunk), !d.isEmpty {
            h.update(data: d)
            done += UInt64(d.count)
            if fileSize > 0 { progress?(Double(done) / Double(fileSize)) }
        }
        return hex(h.finalize())
    }

    // MARK: - Meta hash

    /// SHA-256 over the canonicalised sidecar, the tokenizer directory, and the
    /// optional `.aux`.
    ///
    /// Canonicalisation is what makes this comparable at all across machines:
    /// keys sorted, and any absolute path rewritten to its last two components.
    /// `meta["tokenizer"]` is written as a full path under the converting user's
    /// home directory, so the raw bytes differ between two Macs holding byte-
    /// identical weights.
    static func metaHash(forModelAt modelURL: URL) throws -> String {
        var h = SHA256()

        let metaURL = URL(fileURLWithPath: modelURL.path + ".meta.json")
        if let data = try? Data(contentsOf: metaURL),
           let obj = try? JSONSerialization.jsonObject(with: data) {
            h.update(data: Data(canonicalJSON(obj).utf8))
        }

        let tokDir = URL(fileURLWithPath: modelURL.path + ".tokenizer")
        if let files = try? FileManager.default.contentsOfDirectory(atPath: tokDir.path) {
            for f in files.sorted() {
                guard let d = try? Data(contentsOf: tokDir.appendingPathComponent(f)) else { continue }
                h.update(data: Data(f.utf8))
                h.update(data: Data(SHA256.hash(data: d)))
            }
        }

        let auxURL = URL(fileURLWithPath: modelURL.path + ".aux")
        if let d = try? Data(contentsOf: auxURL) {
            h.update(data: Data("aux".utf8))
            h.update(data: Data(SHA256.hash(data: d)))
        }

        return hex(h.finalize())
    }

    /// Stable textual form of a JSON value: keys sorted, absolute paths reduced
    /// to their last two components so a machine-specific prefix cannot leak in.
    static func canonicalJSON(_ value: Any) -> String {
        switch value {
        case let dict as [String: Any]:
            let body = dict.keys.sorted().map { k in
                "\(quoted(k)):\(canonicalJSON(dict[k]!))"
            }.joined(separator: ",")
            return "{\(body)}"
        case let arr as [Any]:
            return "[\(arr.map(canonicalJSON).joined(separator: ","))]"
        case let s as String:
            return quoted(normalisePath(s))
        case let n as NSNumber:
            // Bools arrive as NSNumber; distinguish them so `true` and `1` differ.
            if CFGetTypeID(n) == CFBooleanGetTypeID() { return n.boolValue ? "true" : "false" }
            return n.stringValue
        case is NSNull:
            return "null"
        default:
            return quoted(String(describing: value))
        }
    }

    /// `/Users/<someone>/…/x.jgen.tokenizer/tokenizer.json` → `x.jgen.tokenizer/tokenizer.json`.
    /// Anything that is not an absolute path is returned untouched.
    static func normalisePath(_ s: String) -> String {
        guard s.hasPrefix("/") else { return s }
        let parts = s.split(separator: "/")
        guard parts.count >= 2 else { return s }
        return parts.suffix(2).joined(separator: "/")
    }

    // MARK: - Assembly and caching

    /// Cache sits next to the model as `<name>.jgen.identity.json`.
    ///
    /// The suffix matters: `JGenConverter.refreshConvertedModelsList` deletes any
    /// file ending in `.jgen` that has no `.meta.json` sidecar, and it runs on
    /// every inventory refresh. `.identity.json` is invisible to that sweep.
    static func cacheURL(forModelAt modelURL: URL) -> URL {
        URL(fileURLWithPath: modelURL.path + ".identity.json")
    }

    private struct CacheEnvelope: Codable {
        let fileSize: UInt64
        let modifiedAt: Double
        let inode: UInt64
        let identity: Identity
    }

    private static func stat(_ url: URL) -> (size: UInt64, mtime: Double, inode: UInt64)? {
        guard let a = try? FileManager.default.attributesOfItem(atPath: url.path) else { return nil }
        let size = (a[.size] as? NSNumber)?.uint64Value ?? 0
        let mtime = (a[.modificationDate] as? Date)?.timeIntervalSince1970 ?? 0
        let inode = (a[.systemFileNumber] as? NSNumber)?.uint64Value ?? 0
        return (size, mtime, inode)
    }

    /// Structural + meta hash, from cache when the file has not changed.
    /// `contentHash` is left `nil` unless a cached one is still valid — computing
    /// it is a separate, explicitly-requested step.
    static func identity(forModelAt modelURL: URL) throws -> Identity {
        if let cached = loadCache(forModelAt: modelURL) { return cached }
        let layout = try readLayout(at: modelURL)
        let identity = Identity(
            fileSize: layout.fileSize,
            structuralHash: structuralHash(of: layout),
            contentHash: nil,
            contentHashKind: nil,
            metaHash: try metaHash(forModelAt: modelURL)
        )
        saveCache(identity, forModelAt: modelURL)
        return identity
    }

    /// Adds (or upgrades) the content hash and re-caches.
    static func withContentHash(
        _ identity: Identity,
        forModelAt modelURL: URL,
        kind: Identity.ContentHashKind,
        progress: ((Double) -> Void)? = nil
    ) throws -> Identity {
        var out = identity
        switch kind {
        case .sampled:
            out.contentHash = try sampledContentHash(
                of: modelURL, structuralHash: identity.structuralHash, fileSize: identity.fileSize
            )
        case .full:
            out.contentHash = try fullContentHash(of: modelURL, progress: progress)
        }
        out.contentHashKind = kind
        saveCache(out, forModelAt: modelURL)
        return out
    }

    static func loadCache(forModelAt modelURL: URL) -> Identity? {
        guard let s = stat(modelURL),
              let data = try? Data(contentsOf: cacheURL(forModelAt: modelURL)),
              let env = try? JSONDecoder().decode(CacheEnvelope.self, from: data),
              env.fileSize == s.size, env.inode == s.inode,
              abs(env.modifiedAt - s.mtime) < 0.001
        else { return nil }
        return env.identity
    }

    static func saveCache(_ identity: Identity, forModelAt modelURL: URL) {
        guard let s = stat(modelURL) else { return }
        let env = CacheEnvelope(fileSize: s.size, modifiedAt: s.mtime, inode: s.inode,
                                identity: identity)
        if let data = try? JSONEncoder().encode(env) {
            try? data.write(to: cacheURL(forModelAt: modelURL), options: .atomic)
        }
    }

    // MARK: - Comparison

    /// Cheap checks first: size and structure separate essentially every real
    /// case without reading a single weight byte.
    static func compare(local: Identity, remote: Identity) -> Verdict {
        if local.fileSize != remote.fileSize {
            return .differentWeights(reason: "file size differs")
        }
        if local.structuralHash != remote.structuralHash {
            return .differentWeights(reason: "tensor layout differs")
        }
        guard local.contentComparable(with: remote) else { return .needsContentHash }
        if local.contentHash != remote.contentHash {
            return .differentWeights(reason: "weight bytes differ")
        }
        return local.metaHash == remote.metaHash ? .identical : .sameWeightsDifferentMeta
    }

    // MARK: - Little-endian helpers

    private static func le16(_ v: UInt16) -> Data { Data([UInt8(v & 0xFF), UInt8(v >> 8)]) }
    private static func le32(_ v: UInt32) -> Data {
        Data((0..<4).map { UInt8((v >> (8 * $0)) & 0xFF) })
    }
    private static func le64(_ v: UInt64) -> Data {
        Data((0..<8).map { UInt8((v >> (8 * UInt64($0))) & 0xFF) })
    }
    private static func hex<D: Sequence>(_ d: D) -> String where D.Element == UInt8 {
        d.map { String(format: "%02x", $0) }.joined()
    }
    private static func seed64(from hexString: String) -> UInt64 {
        var v: UInt64 = 0
        for c in hexString.prefix(16) {
            v = (v << 4) | UInt64(c.hexDigitValue ?? 0)
        }
        return v
    }
    private static func quoted(_ s: String) -> String {
        var out = "\""
        for ch in s.unicodeScalars {
            switch ch {
            case "\"": out += "\\\""
            case "\\": out += "\\\\"
            case "\n": out += "\\n"
            case "\r": out += "\\r"
            case "\t": out += "\\t"
            default:
                if ch.value < 0x20 { out += String(format: "\\u%04x", ch.value) }
                else { out.unicodeScalars.append(ch) }
            }
        }
        return out + "\""
    }
}
