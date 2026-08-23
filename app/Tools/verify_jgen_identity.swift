// Verifies JGenIdentity against the real .jgen files on this machine.
//
// JGenIdentity is self-contained (Foundation + CryptoKit only), so it compiles
// without the rest of the app. There is no XCTest target in this project, and
// adding one for this alone would be a bigger change than the check it runs — so
// this is a plain executable instead.
//
//   cd cli/VerantyxIDE
//   swiftc -O Sources/Verantyx/Engine/JGenIdentity.swift Tools/verify_jgen_identity.swift -o /tmp/idcheck
//   /tmp/idcheck
//
// Needs at least two converted models under
// ~/Library/Application Support/Verantyx/jgen/converted_models/.

import Foundation

@main
struct VerifyJGenIdentity {

    static var failures = 0

    static func check(_ ok: Bool, _ label: String) {
        print("\(ok ? "  ok  " : " FAIL ") \(label)")
        if !ok { failures += 1 }
    }

    static func main() throws {
        let modelsDir = URL(fileURLWithPath: NSHomeDirectory())
            .appendingPathComponent("Library/Application Support/Verantyx/jgen/converted_models")

        try checkCanonicalisation()
        try checkByteSensitivity(modelsDir: modelsDir)
        try checkVerdicts(modelsDir: modelsDir)
        try checkAccounting(modelsDir: modelsDir)

        print("\n=== \(failures == 0 ? "ALL OK" : "\(failures) FAILURES") ===")
        if failures != 0 { exit(1) }
    }

    // MARK: 1 — the sidecar can never match byte-for-byte across machines

    /// `meta["tokenizer"]` is an absolute path containing the converting user's
    /// account name. The two Macs this feature targets are `motonishikoudai` and
    /// `motonisihikoudai`, so a raw byte comparison of the sidecar would report
    /// "different model" on every single pairing. Canonicalisation is what makes
    /// the comparison mean anything — and it has to neutralise the machine-
    /// specific prefix *without* also erasing a genuinely different tokenizer.
    static func checkCanonicalisation() throws {
        let a: [String: Any] = [
            "arch": "hybrid_ssm", "num_layers": 24,
            "tokenizer": "/Users/motonishikoudai/Library/Application Support/Verantyx/jgen/converted_models/m.jgen.tokenizer/tokenizer.json",
        ]
        let b: [String: Any] = [   // same content, other user, keys in another order
            "num_layers": 24, "arch": "hybrid_ssm",
            "tokenizer": "/Users/motonisihikoudai/Library/Application Support/Verantyx/jgen/converted_models/m.jgen.tokenizer/tokenizer.json",
        ]
        check(JGenIdentity.canonicalJSON(a) == JGenIdentity.canonicalJSON(b),
              "same sidecar under two different usernames canonicalises identically")

        var c = a; c["num_layers"] = 48
        check(JGenIdentity.canonicalJSON(a) != JGenIdentity.canonicalJSON(c),
              "a real sidecar difference (num_layers 24 vs 48) still shows up")

        var d = a; d["tokenizer"] = "/Users/x/OTHER_DIR/other.jgen.tokenizer/tokenizer.json"
        check(JGenIdentity.canonicalJSON(a) != JGenIdentity.canonicalJSON(d),
              "a genuinely different tokenizer file is not normalised away")

        check(JGenIdentity.canonicalJSON(["k": true]) != JGenIdentity.canonicalJSON(["k": 1]),
              "true and 1 are distinguished")
    }

    // MARK: 2 — what each hash actually detects

    /// Measures the sampled hash's real sensitivity instead of assuming it.
    /// A single flipped bit is expected to slip past it (66 MB of 1.15 GB is
    /// read) and to be caught by the full hash. The slip-through is *reported*,
    /// not asserted, because it is probabilistic; what is asserted is that the
    /// full hash catches it and the structural hash does not pretend to.
    static func checkByteSensitivity(modelsDir: URL) throws {
        let src = modelsDir.appendingPathComponent("qwen_0.5b_full.jgen")
        guard FileManager.default.fileExists(atPath: src.path) else {
            print("  skip  byte-sensitivity (qwen_0.5b_full.jgen not present)")
            return
        }
        let tmp = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("jgen_flip_test.jgen")
        try? FileManager.default.removeItem(at: tmp)
        try FileManager.default.copyItem(at: src, to: tmp)
        defer { try? FileManager.default.removeItem(at: tmp) }

        let base = try JGenIdentity.readLayout(at: src)
        let baseStruct = JGenIdentity.structuralHash(of: base)
        let baseSampled = try JGenIdentity.sampledContentHash(
            of: src, structuralHash: baseStruct, fileSize: base.fileSize)
        let baseFull = try JGenIdentity.fullContentHash(of: src)

        let victim = base.entries[base.entries.count / 2]
        let flipAt = victim.dataOffset + victim.byteLength / 2
        let h = try FileHandle(forUpdating: tmp)
        try h.seek(toOffset: flipAt)
        var byte = try h.read(upToCount: 1)!.first!
        byte ^= 0x01
        try h.seek(toOffset: flipAt)
        try h.write(contentsOf: Data([byte]))
        try h.close()
        print("  ..    flipped 1 bit at \(flipAt) inside '\(victim.name)'")

        let flip = try JGenIdentity.readLayout(at: tmp)
        let flipStruct = JGenIdentity.structuralHash(of: flip)
        let flipSampled = try JGenIdentity.sampledContentHash(
            of: tmp, structuralHash: flipStruct, fileSize: flip.fileSize)
        let flipFull = try JGenIdentity.fullContentHash(of: tmp)

        check(baseStruct == flipStruct,
              "structural hash is unchanged by a weight edit (it describes layout)")
        check(baseFull != flipFull,
              "FULL content hash detects a single flipped bit")
        print("  ..    sampled hash \(baseSampled == flipSampled ? "did NOT notice" : "noticed") "
              + "the flip — expected to miss most single-bit edits")
    }

    // MARK: 3 — the verdict table drives what the UI offers

    static func checkVerdicts(modelsDir: URL) throws {
        let files = (try FileManager.default.contentsOfDirectory(atPath: modelsDir.path))
            .filter { $0.hasSuffix(".jgen") }.sorted()
        guard files.count >= 2 else {
            print("  skip  verdicts (need two models)")
            return
        }
        func id(_ n: String, meta: String = "M") throws -> JGenIdentity.Identity {
            let l = try JGenIdentity.readLayout(at: modelsDir.appendingPathComponent(n))
            return JGenIdentity.Identity(
                fileSize: l.fileSize, structuralHash: JGenIdentity.structuralHash(of: l),
                contentHash: nil, contentHashKind: nil, metaHash: meta)
        }
        let one = try id(files[0]), two = try id(files[1])

        if case .differentWeights = JGenIdentity.compare(local: one, remote: two) {
            check(true, "two different models -> differentWeights, no content hash read")
        } else {
            check(false, "two different models should compare as differentWeights")
        }

        check(JGenIdentity.compare(local: one, remote: one) == .needsContentHash,
              "structure matches but no content hash yet -> needsContentHash")

        var s1 = one; s1.contentHash = "abc"; s1.contentHashKind = .sampled
        var s2 = one; s2.contentHash = "abc"; s2.contentHashKind = .sampled
        check(JGenIdentity.compare(local: s1, remote: s2) == .identical,
              "same weights + same meta -> identical (transfer button disappears)")

        let s3 = JGenIdentity.Identity(
            fileSize: one.fileSize, structuralHash: one.structuralHash,
            contentHash: "abc", contentHashKind: .sampled, metaHash: "DIFFERENT")
        check(JGenIdentity.compare(local: s1, remote: s3) == .sameWeightsDifferentMeta,
              "same weights + different sidecar -> sameWeightsDifferentMeta, not a huge transfer")

        var mixed = s1; mixed.contentHashKind = .full
        check(JGenIdentity.compare(local: s1, remote: mixed) == .needsContentHash,
              "a sampled hash is never compared against a full one")
    }

    // MARK: 4 — byte accounting feeds the split planner

    /// Every tensor byte must land in exactly one bucket. The split planner sizes
    /// each machine from `perLayerBytes`, so an unattributed byte is a machine
    /// planned smaller than the weights it will actually fault in.
    static func checkAccounting(modelsDir: URL) throws {
        for m in (try FileManager.default.contentsOfDirectory(atPath: modelsDir.path))
            .filter({ $0.hasSuffix(".jgen") }).sorted() {
            let u = modelsDir.appendingPathComponent(m)
            let l = try JGenIdentity.readLayout(at: u)
            let sum = l.perLayerBytes.values.reduce(UInt64(0), +) + l.nonLayerBytes
            let ratio = Double(sum) / Double(l.fileSize)
            check(sum <= l.fileSize && ratio > 0.99,
                  "\(m): layers=\(l.layerCount) accounts for "
                  + "\(String(format: "%.2f", ratio * 100))% of the file")
        }
    }
}
