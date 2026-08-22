import Foundation

/// Authoritative pairing state, deliberately **not** on the main actor.
///
/// This exists because of a failure found by actually running it: the first
/// version kept the state in a `@MainActor ObservableObject` and every
/// `/pipe/*` handler hopped to the main actor to read it. Launching the app
/// surfaced a Screen Recording permission dialog, `[NSAlert runModal]` parked
/// the main thread, and every request hung until it timed out — connection
/// accepted, zero bytes returned.
///
/// That is not a test artifact. A peer asking "are you there?" must not depend
/// on whether this Mac's user happens to have a modal open, otherwise a healthy
/// machine looks dead for as long as someone leaves a dialog on screen. The
/// control plane answers from a lock-protected store; `PipeSession` is a
/// main-actor *view* of it for SwiftUI, never the source of truth.
final class PipeStore: @unchecked Sendable {

    static let shared = PipeStore()

    enum Role: String, Codable { case idle, master, worker }
    enum SplitMode: String, Codable { case auto, manual }

    struct PeerInfo: Codable, Equatable, Sendable {
        var deviceId: String
        var deviceName: String
        var appVersion: String
        var engineBuild: String
        var protocolVersion: Int
        var ramGB: Int
        var freeDiskGB: Double
        var host: String
        var controlPort: UInt16
    }

    struct Snapshot: Sendable, Equatable {
        var role: Role
        var sessionId: String
        var peer: PeerInfo?
        var splitMode: SplitMode
        var splitK: Int
        var lastError: String?
        var isPaired: Bool { role != .idle && peer != nil }
    }

    enum PairOutcome: Sendable {
        case accepted(role: Role)
        case rejected(reason: String)
        /// Both sides claimed master; this Mac won and keeps the role.
        case tiebreakWon(reason: String)
    }

    private let lock = NSLock()
    private var role: Role = .idle
    private var sessionId = ""
    private var peer: PeerInfo?
    private var splitMode: SplitMode = .auto
    private var splitK = 0
    private var lastError: String?

    /// This Mac's own id, cached so reads never touch `AppState` (main actor).
    ///
    /// `VERANTYX_PIPE_DEVICE_ID` overrides it. That exists for one reason and it
    /// is worth keeping: two instances of this app on one Mac share a bundle id
    /// and therefore a UserDefaults domain, so they report the same id and refuse
    /// to pair with "That is this Mac." Two real Macs never collide. Without the
    /// override the entire pairing path — version gate, tiebreak, busy rejection,
    /// split propagation — could only be exercised with a second machine present.
    private var _localDeviceId: String = {
        if let override = ProcessInfo.processInfo.environment["VERANTYX_PIPE_DEVICE_ID"],
           !override.isEmpty {
            return override
        }
        if let id = UserDefaults.standard.string(forKey: "pipe_device_id") { return id }
        if let legacy = UserDefaults.standard.string(forKey: "exo_device_id") { return legacy }
        let fresh = UUID().uuidString
        UserDefaults.standard.set(fresh, forKey: "pipe_device_id")
        return fresh
    }()
    var localDeviceId: String { lock.withLock { _localDeviceId } }

    private init() {}

    // MARK: - Local node identity (no main actor)

    /// SHA-256 prefix of the bundled engine dylib, computed once and cached.
    ///
    /// This is the real compatibility guarantee between two Macs — the app
    /// version string is only what gets *shown* when it fails.
    private var _engineBuild: String?
    var engineBuild: String {
        lock.withLock {
            if let cached = _engineBuild { return cached }
            let candidates = [
                Bundle.main.privateFrameworksURL?.appendingPathComponent("libjcross_engine_glm.dylib"),
                Bundle.main.bundleURL.appendingPathComponent("Contents/Frameworks/libjcross_engine_glm.dylib"),
                Bundle.main.bundleURL.appendingPathComponent("Contents/MacOS/libjcross_engine_glm.dylib"),
            ].compactMap { $0 }
            var result = "unknown"
            for url in candidates where FileManager.default.fileExists(atPath: url.path) {
                if let hash = try? JGenIdentity.fullContentHash(of: url) {
                    result = String(hash.prefix(12))
                    break
                }
            }
            _engineBuild = result
            return result
        }
    }

    var appVersion: String {
        Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "0"
    }
    var deviceName: String { Host.current().localizedName ?? "Mac" }
    var ramGB: Int { Int((Double(ProcessInfo.processInfo.physicalMemory) / Double(1 << 30)).rounded()) }
    var protocolVersion: Int { 1 }

    func localVersion() -> VersionTriple {
        VersionTriple(protocolVersion: protocolVersion,
                      appVersion: appVersion,
                      engineBuild: engineBuild)
    }

    func snapshot() -> Snapshot {
        lock.withLock {
            Snapshot(role: role, sessionId: sessionId, peer: peer,
                     splitMode: splitMode, splitK: splitK, lastError: lastError)
        }
    }

    // MARK: - Tiebreak

    /// Which device id keeps Master when both claim it at once.
    ///
    /// Pure and total on purpose. The property that must hold is *agreement*:
    /// both machines evaluate this over the same two ids, so they always reach
    /// the same conclusion and there is never a moment with two masters or none.
    /// "Lower id wins" is arbitrary; deterministic and symmetric is not. A rule
    /// like "whoever asked first" would depend on message ordering — precisely
    /// what is unreliable when both ask simultaneously.
    static func tiebreakWinner(_ a: String, _ b: String) -> String {
        a == b ? a : (a < b ? a : b)
    }

    // MARK: - Version gate

    struct VersionTriple: Codable, Equatable, Sendable {
        var protocolVersion: Int
        var appVersion: String
        var engineBuild: String
    }

    /// `nil` when compatible, otherwise a sentence the user can act on.
    ///
    /// All three must match. The app version alone is not enough: the shipped
    /// build reports `0.0.0-dev-107`, and two locally built DMGs can both stamp
    /// `0.0.0-dev` while embedding different engines — and this design assumes
    /// both machines compute identical numbers bit for bit.
    func versionMismatchReason(_ remote: VersionTriple, local: VersionTriple) -> String? {
        if remote.protocolVersion != local.protocolVersion {
            return "Pairing protocol differs (\(remote.protocolVersion) vs \(local.protocolVersion)). "
                 + "Both Macs must run the same Verantyx build."
        }
        if remote.appVersion != local.appVersion {
            return "Cannot pair — this Mac runs \(local.appVersion), the other runs \(remote.appVersion). "
                 + "Both Macs must run the same Verantyx build."
        }
        if remote.engineBuild != local.engineBuild {
            return "Same version number, different engine builds "
                 + "(\(local.engineBuild) vs \(remote.engineBuild)) — one of these was built locally. "
                 + "Reinstall both from the same DMG."
        }
        return nil
    }

    // MARK: - Mutations

    func acceptPairing(from remote: PeerInfo, sessionId incoming: String,
                       local: VersionTriple) -> PairOutcome {
        if let reason = versionMismatchReason(
            VersionTriple(protocolVersion: remote.protocolVersion,
                          appVersion: remote.appVersion,
                          engineBuild: remote.engineBuild), local: local) {
            return .rejected(reason: reason)
        }
        return lock.withLock {
            if remote.deviceId == _localDeviceId {
                return .rejected(reason: "That is this Mac.")
            }
            // Already working with someone else — name them, so the third
            // machine's user knows where to look instead of seeing an opaque
            // refusal.
            if role != .idle, let current = peer, current.deviceId != remote.deviceId {
                return .rejected(reason: "\"\(current.deviceName)\" is already working with this Mac.")
            }
            if role == .master, !_localDeviceId.isEmpty,
               Self.tiebreakWinner(_localDeviceId, remote.deviceId) == _localDeviceId {
                return .tiebreakWon(reason:
                    "Both Macs asked to be Master — this Mac won the tiebreak and "
                    + "\"\(remote.deviceName)\" becomes the Worker.")
            }
            role = .worker
            peer = remote
            sessionId = incoming
            lastError = nil
            return .accepted(role: .worker)
        }
    }

    func becomeMaster(peer remote: PeerInfo, sessionId newId: String) {
        lock.withLock {
            role = .master; peer = remote; sessionId = newId; lastError = nil
        }
    }

    func unpair() {
        lock.withLock {
            role = .idle; peer = nil; sessionId = ""; splitK = 0; splitMode = .auto
        }
    }

    /// Master-side resolution. The worker never computes its own — a second
    /// writer is how two machines end up loading different layer ranges and
    /// producing confident nonsense.
    @discardableResult
    func setSplit(mode: SplitMode, k: Int) -> Bool {
        lock.withLock {
            guard role == .master else { return false }
            splitMode = mode; splitK = k
            return true
        }
    }

    /// Accepts a split pushed by the master.
    func applyRemoteState(mode: SplitMode, k: Int) {
        lock.withLock { splitMode = mode; splitK = k }
    }

    func fail(_ message: String) {
        lock.withLock { lastError = message }
    }

    // MARK: - Inventory (filesystem only, no main actor)

    struct ModelEntry: Codable, Equatable, Sendable {
        var name: String
        var sizeBytes: UInt64
        var structuralHash: String
        var metaHash: String
        var contentHash: String?
        var contentHashKind: String?
        var archSupported: Bool
    }

    /// Reads the converted-models directory directly rather than going through
    /// `JGenConverter` (which is main-actor bound, and whose refresh also runs a
    /// delete sweep this has no business triggering).
    ///
    /// Content hashes are reported only when already cached: computing one is a
    /// deliberate, visible step, never something a list request sets off.
    func localModels() -> [ModelEntry] {
        let dir = JGenPaths.convertedModelsDir
        guard let names = try? FileManager.default.contentsOfDirectory(atPath: dir.path) else { return [] }
        var out: [ModelEntry] = []
        for name in names.sorted() where name.hasSuffix(".jgen") {
            let url = dir.appendingPathComponent(name)
            // A .jgen with no sidecar is an incomplete conversion or an
            // in-flight transfer; either way it is not offerable.
            guard FileManager.default.fileExists(atPath: url.path + ".meta.json"),
                  let id = try? JGenIdentity.identity(forModelAt: url) else { continue }
            let cached = JGenIdentity.loadCache(forModelAt: url)
            out.append(ModelEntry(
                name: name,
                sizeBytes: id.fileSize,
                structuralHash: id.structuralHash,
                metaHash: id.metaHash,
                contentHash: cached?.contentHash,
                contentHashKind: cached?.contentHashKind?.rawValue,
                archSupported: Self.archSupported(metaAt: url.path + ".meta.json")
            ))
        }
        return out
    }

    /// Same rule as `JGenConverter.isArchSupported`, read straight from the
    /// sidecar so it needs no main-actor hop.
    private static func archSupported(metaAt path: String) -> Bool {
        guard let d = FileManager.default.contents(atPath: path),
              let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any] else { return false }
        if (j["parts"] as? String) == "lexicon" { return false }
        let arch = (j["arch"] as? String) ?? "standard"
        return ["standard", "moe_standard", "hybrid_ssm"].contains(arch)
    }

    static func freeDiskGB() -> Double {
        if let v = try? JGenPaths.convertedModelsDir.resourceValues(
            forKeys: [.volumeAvailableCapacityForImportantUsageKey]),
           let bytes = v.volumeAvailableCapacityForImportantUsage {
            return Double(bytes) / Double(1 << 30)
        }
        return 0
    }
}

private extension NSLock {
    func withLock<T>(_ body: () -> T) -> T {
        lock(); defer { unlock() }
        return body()
    }
}
