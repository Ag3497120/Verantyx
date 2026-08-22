import Foundation
import CryptoKit
import SwiftUI

/// Live transfer state, observable by any screen on either machine.
///
/// Lives outside the `ModelTransfer` actor because a `@Published` property on
/// an actor is unreachable from SwiftUI (the earlier one sat here unread,
/// which is how "transfer" shipped as a stub without anyone noticing — no
/// screen could have shown it anyway).
@MainActor
final class TransferProgress: ObservableObject {
    static let shared = TransferProgress()

    enum Phase: String { case idle, fetching, verifying, done, failed }

    @Published private(set) var phase: Phase = .idle
    @Published private(set) var name = ""
    @Published private(set) var bytesDone: UInt64 = 0
    @Published private(set) var bytesTotal: UInt64 = 0
    @Published private(set) var error: String?

    var fraction: Double {
        bytesTotal > 0 ? Double(bytesDone) / Double(bytesTotal) : 0
    }

    /// One transfer at a time; two 16 GB pulls onto one disk is how a resumable
    /// transfer becomes two failed ones.
    func beginIfIdle(name: String) -> Bool {
        if phase == .fetching || phase == .verifying { return false }
        self.name = name; phase = .fetching
        bytesDone = 0; bytesTotal = 0; error = nil
        return true
    }

    func update(done: UInt64, total: UInt64) { bytesDone = done; bytesTotal = total }
    func verify() { phase = .verifying }
    func finish() { phase = .done }
    func fail(_ message: String) { phase = .failed; error = message }

    func snapshot() -> [String: Any] {
        ["ok": true, "phase": phase.rawValue, "name": name,
         "done": String(bytesDone), "total": String(bytesTotal),
         "error": error ?? ""]
    }
}

/// Copies a converted model from the master to the worker.
///
/// The receiver pulls. It knows its own free space, controls where bytes land,
/// and can resume — none of which the sender can do on its behalf.
///
/// Bytes do **not** go through `JGenAgentServer`. Its request reader accumulates
/// the whole body into a single in-memory `Data` with no cap, so a multi-GB POST
/// would exhaust memory on the receiving machine. The control plane negotiates;
/// a one-shot raw stream carries the payload.
///
/// Above `rsyncThresholdGB` this deliberately does not transfer at all. Over
/// Thunderbolt 57 GB is under a minute, but over Wi-Fi it is two to three hours
/// of in-app progress bar — and `rsync -avP --partial` over SSH saturates the
/// link, already resumes, and is less code than anything written here. The UI
/// hands over the command instead of pretending to do better.
actor ModelTransfer {

    static let shared = ModelTransfer()

    /// In-app transfer is offered below this; above it, the rsync command is.
    static let rsyncThresholdGB: Double = 20

    struct ManifestEntry: Codable, Equatable {
        /// Path relative to the model's own name, e.g. "" for the `.jgen`
        /// itself, "meta.json", "tokenizer/tokenizer.json".
        var relPath: String
        var size: UInt64
        var sha256: String
    }

    struct Manifest: Codable, Equatable {
        var name: String
        var files: [ManifestEntry]
        var totalBytes: UInt64
    }

    enum TransferError: LocalizedError {
        case notEnoughSpace(neededGB: Double, freeGB: Double)
        case ranOutOfSpace(neededGB: Double)
        case hashMismatch(String)
        case sourceMissing(String)
        case cancelled

        var errorDescription: String? {
            switch self {
            case .notEnoughSpace(let n, let f):
                return String(format: "Needs %.1f GB but only %.1f GB is free.", n, f)
            case .ranOutOfSpace(let n):
                return String(format: "Ran out of space — %.1f GB more is needed. "
                                    + "Free some space and press Resume; what has already "
                                    + "transferred is kept.", n)
            case .hashMismatch(let f):
                return "\(f) did not match after transfer. It will be re-fetched."
            case .sourceMissing(let f):
                return "The other Mac no longer has \(f)."
            case .cancelled:
                return "Transfer cancelled."
            }
        }
    }

    private init() {}

    // MARK: - Sender side

    /// Everything the receiver needs to reproduce this model, with a hash per
    /// file so a partial or corrupted arrival is caught rather than loaded.
    ///
    /// A model is four artifacts, not one: the weights, the sidecar, an optional
    /// `.aux`, and a tokenizer directory. Copying only the `.jgen` produces a
    /// file that fails at load with a missing-tokenizer error.
    static func buildManifest(for name: String) throws -> Manifest {
        let base = JGenPaths.convertedModelsDir.appendingPathComponent(name)
        let fm = FileManager.default
        guard fm.fileExists(atPath: base.path) else {
            throw TransferError.sourceMissing(name)
        }

        var files: [ManifestEntry] = []
        func add(_ url: URL, _ rel: String) throws {
            guard fm.fileExists(atPath: url.path) else { return }
            let size = (try fm.attributesOfItem(atPath: url.path)[.size] as? NSNumber)?.uint64Value ?? 0
            files.append(ManifestEntry(relPath: rel, size: size,
                                       sha256: try JGenIdentity.fullContentHash(of: url)))
        }

        try add(base, "")
        try add(URL(fileURLWithPath: base.path + ".meta.json"), "meta.json")
        try add(URL(fileURLWithPath: base.path + ".aux"), "aux")

        let tokDir = URL(fileURLWithPath: base.path + ".tokenizer")
        if let entries = try? fm.contentsOfDirectory(atPath: tokDir.path) {
            for f in entries.sorted() {
                try add(tokDir.appendingPathComponent(f), "tokenizer/\(f)")
            }
        }

        return Manifest(name: name, files: files,
                        totalBytes: files.reduce(0) { $0 + $1.size })
    }

    static func sourceURL(name: String, relPath: String) -> URL {
        let base = JGenPaths.convertedModelsDir.appendingPathComponent(name)
        switch relPath {
        case "":          return base
        case "meta.json": return URL(fileURLWithPath: base.path + ".meta.json")
        case "aux":       return URL(fileURLWithPath: base.path + ".aux")
        default:
            let leaf = relPath.replacingOccurrences(of: "tokenizer/", with: "")
            return URL(fileURLWithPath: base.path + ".tokenizer").appendingPathComponent(leaf)
        }
    }

    // MARK: - Receiver side

    static func stagingDir(for name: String) -> URL {
        // Inside the models directory so the move is a same-volume rename, but
        // hidden and — critically — not matching `*.jgen`, which is what
        // `refreshConvertedModelsList`'s sweep deletes.
        JGenPaths.convertedModelsDir
            .appendingPathComponent(".incoming", isDirectory: true)
            .appendingPathComponent(name, isDirectory: true)
    }

    /// Local name for a staged file. Never `*.jgen` while in flight.
    static func stagedURL(for name: String, relPath: String) -> URL {
        let dir = stagingDir(for: name)
        switch relPath {
        case "":          return dir.appendingPathComponent("model.jgen.part")
        case "meta.json": return dir.appendingPathComponent("meta.json")
        case "aux":       return dir.appendingPathComponent("aux")
        default:          return dir.appendingPathComponent(relPath)  // tokenizer/<leaf>
        }
    }

    /// Verifies every staged file, then publishes them in an order that cannot
    /// leave a deletable state visible.
    ///
    /// The order is load-bearing:
    ///   1. rewrite meta.json's tokenizer path to *this* machine's absolute path
    ///   2. tokenizer directory
    ///   3. .aux
    ///   4. meta.json      ← before the weights
    ///   5. .jgen          ← last, and atomically
    ///
    /// A `.meta.json` with no `.jgen` is harmless: the sweep only deletes `.jgen`
    /// files. Publishing the weights first would expose a `.jgen` with no sidecar
    /// to any inventory refresh, and it would be deleted. Step 1 exists because
    /// meta["tokenizer"] is an absolute path under the *sending* user's home —
    /// copying it verbatim gives a model that loads on neither machine.
    func publish(name: String, manifest: Manifest) async throws {
        let fm = FileManager.default
        let staging = Self.stagingDir(for: name)

        for entry in manifest.files {
            let staged = Self.stagedURL(for: name, relPath: entry.relPath)
            guard fm.fileExists(atPath: staged.path) else {
                throw TransferError.sourceMissing(entry.relPath.isEmpty ? name : entry.relPath)
            }
            let actual = try JGenIdentity.fullContentHash(of: staged)
            guard actual == entry.sha256 else {
                try? fm.removeItem(at: staged)
                throw TransferError.hashMismatch(entry.relPath.isEmpty ? name : entry.relPath)
            }
        }

        let base = JGenPaths.convertedModelsDir.appendingPathComponent(name)
        let finalMeta = URL(fileURLWithPath: base.path + ".meta.json")
        let finalTok  = URL(fileURLWithPath: base.path + ".tokenizer")
        let finalAux  = URL(fileURLWithPath: base.path + ".aux")

        // 1 — point the sidecar at this machine's tokenizer.
        let stagedMeta = Self.stagedURL(for: name, relPath: "meta.json")
        if fm.fileExists(atPath: stagedMeta.path),
           let d = try? Data(contentsOf: stagedMeta),
           var obj = (try? JSONSerialization.jsonObject(with: d)) as? [String: Any] {
            if let tok = obj["tokenizer"] as? String {
                let leaf = (tok as NSString).lastPathComponent
                obj["tokenizer"] = finalTok.appendingPathComponent(leaf).path
            }
            let out = try JSONSerialization.data(withJSONObject: obj, options: [.sortedKeys])
            try out.write(to: stagedMeta, options: .atomic)
        }

        // 2, 3
        let stagedTok = staging.appendingPathComponent("tokenizer", isDirectory: true)
        if fm.fileExists(atPath: stagedTok.path) {
            try? fm.removeItem(at: finalTok)
            try fm.moveItem(at: stagedTok, to: finalTok)
        }
        let stagedAux = Self.stagedURL(for: name, relPath: "aux")
        if fm.fileExists(atPath: stagedAux.path) {
            try? fm.removeItem(at: finalAux)
            try fm.moveItem(at: stagedAux, to: finalAux)
        }

        // 4 — sidecar before weights.
        if fm.fileExists(atPath: stagedMeta.path) {
            try? fm.removeItem(at: finalMeta)
            try fm.moveItem(at: stagedMeta, to: finalMeta)
        }

        // 5 — weights last; same volume, so this is an atomic rename.
        let stagedJgen = Self.stagedURL(for: name, relPath: "")
        try? fm.removeItem(at: base)
        try fm.moveItem(at: stagedJgen, to: base)

        try? fm.removeItem(at: staging)
        // Drop the stale identity cache: same path, different bytes.
        try? fm.removeItem(at: JGenIdentity.cacheURL(forModelAt: base))
    }

    /// Where to resume from: the size already on disk.
    static func resumeOffset(name: String, relPath: String) -> UInt64 {
        let url = stagedURL(for: name, relPath: relPath)
        guard let a = try? FileManager.default.attributesOfItem(atPath: url.path) else { return 0 }
        return (a[.size] as? NSNumber)?.uint64Value ?? 0
    }

    /// Checked before starting **and** every few GB during: a transfer long
    /// enough to matter is long enough for the disk to fill from elsewhere.
    static func checkSpace(needBytes: UInt64) throws {
        let need = Double(needBytes) / Double(1 << 30) * 1.05
        let free = PipeStore.freeDiskGB()
        guard free >= need else {
            throw TransferError.notEnoughSpace(neededGB: need, freeGB: free)
        }
    }

    static let spaceRecheckInterval: UInt64 = 5 * UInt64(1 << 30)

    // MARK: - The pull loop (receiver side)

    /// Fetches every file in the sender's manifest into staging, resumably,
    /// then verifies and publishes. Progress goes to `TransferProgress.shared`
    /// so both this machine's UI and the sender (via /pipe/model/pull_status)
    /// can watch the same numbers.
    func pull(name: String, host: String, port: UInt16) async {
        // Session id first: the sender's model routes are locked to the
        // pairing, and asking without it is a guaranteed 403.
        let sid = await MainActor.run { PipeStore.shared.snapshot().sessionId }
        func fail(_ msg: String) async {
            await MainActor.run { TransferProgress.shared.fail(msg) }
        }
        do {
            // 1. Manifest.
            guard let mURL = URL(string: "http://\(host):\(port)/pipe/model/manifest?sid=\(sid)&name="
                                 + (name.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? name))
            else { await fail("bad host"); return }
            let (mData, _) = try await URLSession.shared.data(from: mURL)
            guard let mJSON = try JSONSerialization.jsonObject(with: mData) as? [String: Any],
                  let mObj = mJSON["manifest"],
                  let manifest = try? JSONDecoder().decode(
                      Manifest.self, from: JSONSerialization.data(withJSONObject: mObj))
            else { await fail("the other Mac has no model named \(name)"); return }

            // 2. Space, counting what is already staged as done.
            let already = manifest.files.reduce(UInt64(0)) {
                $0 + min(Self.resumeOffset(name: name, relPath: $1.relPath), $1.size)
            }
            try Self.checkSpace(needBytes: manifest.totalBytes - already)
            try FileManager.default.createDirectory(at: Self.stagingDir(for: name),
                                                    withIntermediateDirectories: true)
            let tokDir = Self.stagingDir(for: name).appendingPathComponent("tokenizer")
            try? FileManager.default.createDirectory(at: tokDir, withIntermediateDirectories: true)

            var done = already
            await MainActor.run { TransferProgress.shared.update(done: done, total: manifest.totalBytes) }

            // 3. Files, largest last so the cheap ones cannot be stranded
            //    behind a 16 GB failure.
            var lastSpaceCheck = done
            for entry in manifest.files.sorted(by: { $0.size < $1.size }) {
                let staged = Self.stagedURL(for: name, relPath: entry.relPath)
                var offset = Self.resumeOffset(name: name, relPath: entry.relPath)
                if offset > entry.size {
                    // Staged file is LONGER than the source says — stale from a
                    // different version. Start that file over.
                    try? FileManager.default.removeItem(at: staged)
                    offset = 0
                }
                if offset == entry.size { continue }

                if !FileManager.default.fileExists(atPath: staged.path) {
                    FileManager.default.createFile(atPath: staged.path, contents: nil)
                }
                let fh = try FileHandle(forWritingTo: staged)
                defer { try? fh.close() }
                try fh.seekToEnd()

                let esc = { (s: String) in
                    s.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? s
                }
                guard let fURL = URL(string: "http://\(host):\(port)/pipe/model/file?sid=\(sid)&name=\(esc(name))&rel=\(esc(entry.relPath))&off=\(offset)")
                else { await fail("bad host"); return }
                var req = URLRequest(url: fURL)
                req.timeoutInterval = 3600
                let (bytes, resp) = try await URLSession.shared.bytes(for: req)
                guard (resp as? HTTPURLResponse)?.statusCode == 200 else {
                    await fail("the other Mac refused \(entry.relPath.isEmpty ? name : entry.relPath)")
                    return
                }

                // Buffer ~4 MB between writes: per-byte FileHandle writes are
                // three orders of magnitude too slow for a 16 GB stream.
                var buf = Data(capacity: 4 << 20)
                for try await b in bytes {
                    buf.append(b)
                    if buf.count >= 4 << 20 {
                        try fh.write(contentsOf: buf)
                        done += UInt64(buf.count)
                        buf.removeAll(keepingCapacity: true)
                        await MainActor.run {
                            TransferProgress.shared.update(done: done, total: manifest.totalBytes)
                        }
                        if done - lastSpaceCheck > Self.spaceRecheckInterval {
                            lastSpaceCheck = done
                            try Self.checkSpace(needBytes: manifest.totalBytes - done)
                        }
                    }
                }
                if !buf.isEmpty {
                    try fh.write(contentsOf: buf)
                    done += UInt64(buf.count)
                    await MainActor.run {
                        TransferProgress.shared.update(done: done, total: manifest.totalBytes)
                    }
                }
            }

            // 4. Verify + publish (hashes re-checked inside).
            await MainActor.run { TransferProgress.shared.verify() }
            try await publish(name: name, manifest: manifest)
            await MainActor.run { TransferProgress.shared.finish() }
            await MainActor.run { JGenConverter.shared.refreshConvertedModelsList() }
        } catch {
            await fail(error.localizedDescription)
        }
    }

    // MARK: - The large-model escape hatch

    /// Whether to hand over an rsync command instead of transferring in-app.
    static func shouldUseRsync(totalBytes: UInt64) -> Bool {
        Double(totalBytes) / Double(1 << 30) > rsyncThresholdGB
    }

    /// A copy-pasteable command. Quoted for the space in "Application Support",
    /// and `--partial` so an interrupted run resumes.
    static func rsyncCommand(name: String, user: String, host: String) -> String {
        let dir = JGenPaths.convertedModelsDir.path
            .replacingOccurrences(of: " ", with: "\\ ")
        return "rsync -avP --partial \\\n  \(dir)/\(name)* \\\n  \(user)@\(host):\(dir)/"
    }

    /// After an rsync, the sidecar still points at the *sender's* home directory.
    /// Detects and repairs that in place — one line of JSON, versus re-copying
    /// tens of gigabytes.
    @discardableResult
    static func repairTokenizerPath(name: String) -> Bool {
        let base = JGenPaths.convertedModelsDir.appendingPathComponent(name)
        let metaURL = URL(fileURLWithPath: base.path + ".meta.json")
        guard let d = try? Data(contentsOf: metaURL),
              var obj = (try? JSONSerialization.jsonObject(with: d)) as? [String: Any],
              let tok = obj["tokenizer"] as? String
        else { return false }
        if FileManager.default.fileExists(atPath: tok) { return false }   // already fine

        let leaf = (tok as NSString).lastPathComponent
        let fixed = URL(fileURLWithPath: base.path + ".tokenizer")
            .appendingPathComponent(leaf)
        guard FileManager.default.fileExists(atPath: fixed.path) else { return false }
        obj["tokenizer"] = fixed.path
        guard let out = try? JSONSerialization.data(withJSONObject: obj, options: [.sortedKeys]),
              (try? out.write(to: metaURL, options: .atomic)) != nil else { return false }
        return true
    }
}
