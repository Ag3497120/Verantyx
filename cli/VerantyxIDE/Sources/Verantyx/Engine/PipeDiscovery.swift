import Foundation
import Network

/// Finds the other Mac, and lets it find this one.
///
/// Why the previous attempt never worked, in order of how much it mattered:
///
///  1. **`ExoClusterSync.shared.start()` had no call site.** Bonjour was never
///     switched on at all, and the settings card that would have switched it on
///     was never rendered in any tab. That is the whole explanation; the rest is
///     hygiene.
///  2. On macOS 15+, any local-network access requires
///     `NSLocalNetworkUsageDescription` and `NSBonjourServices` in Info.plist.
///     Without them there is no error and no prompt; discovery just never
///     returns anything. Both keys are now present — if either is removed, this
///     file stops working with no diagnostic.
///
/// The service type was also renamed from `_verantyx_exo._tcp` to
/// `_verantyx-pipe._tcp` because RFC 6763 §7 permits only letters, digits and
/// hyphens in a service name. To be accurate about this: the old name was
/// *checked* and macOS's mDNSResponder registers it happily, so it was **not** a
/// cause of the old failure — the rename is conformance, not a fix.
///
/// `NWBrowser`/`NWListener` are used rather than the older
/// `NetService`/`NetServiceBrowser` the exo code used, because they report which
/// interface a result arrived on — which is what lets the UI say "found over
/// Thunderbolt" instead of just "found".
///
/// Discovery is a convenience, never a requirement: `manualPeer(host:port:)`
/// reaches a peer by address alone. Every environment where mDNS is filtered —
/// and there are many — still works through that path.
@MainActor
final class PipeDiscovery: ObservableObject {

    static let shared = PipeDiscovery()

    /// RFC 6763-valid: letters, digits, hyphens only, 15 characters or fewer.
    /// `verantyx-pipe` is 13.
    static let serviceType = "_verantyx-pipe._tcp"
    static let serviceDomain = "local."

    struct Peer: Identifiable, Equatable {
        let endpointName: String        // Bonjour instance name
        var deviceName: String          // human-readable, from TXT `nm`
        var deviceId: String            // stable UUID, from TXT `id`
        var appVersion: String          // CFBundleShortVersionString, TXT `av`
        var engineBuild: String         // dylib hash prefix, TXT `eb`
        var protocolVersion: Int        // TXT `v`
        var ramGB: Int                  // TXT `ram`
        var role: String                // TXT `role`
        var controlPort: UInt16         // TXT `cp`
        var host: String?               // resolved address, when known
        var interfaceKind: NetworkInterfaces.LinkKind

        var id: String { deviceId.isEmpty ? endpointName : deviceId }

        /// Pairing requires all three to match. `appVersion` alone is not
        /// enough: the shipped build currently reports `0.0.0-dev-107`, and two
        /// locally built DMGs can both stamp `0.0.0-dev` while embedding
        /// different engines — and this whole feature assumes both sides compute
        /// identical numbers bit for bit.
        func isCompatible(with local: LocalIdentity) -> Bool {
            protocolVersion == local.protocolVersion
                && appVersion == local.appVersion
                && engineBuild == local.engineBuild
        }

        /// Which of the three differs, for a message the user can act on.
        func incompatibilityReason(vs local: LocalIdentity) -> String? {
            if protocolVersion != local.protocolVersion {
                return "protocol \(protocolVersion) vs \(local.protocolVersion)"
            }
            if appVersion != local.appVersion {
                return "app version \(appVersion) vs \(local.appVersion)"
            }
            if engineBuild != local.engineBuild {
                return "same version number, different engine build "
                     + "(\(engineBuild) vs \(local.engineBuild))"
            }
            return nil
        }
    }

    /// What this Mac advertises about itself.
    struct LocalIdentity {
        var protocolVersion: Int = 1
        var appVersion: String
        var engineBuild: String
        var deviceId: String
        var deviceName: String
        var ramGB: Int
        var role: String = "idle"
        var controlPort: UInt16 = 0
    }

    // MARK: - Published state

    @Published private(set) var peers: [Peer] = []
    @Published private(set) var isBrowsing = false
    @Published private(set) var isAdvertising = false
    /// Set when a browse produces nothing and the browser never reached `.ready`
    /// — the observable signature of a denied Local Network permission, which
    /// otherwise looks identical to "no peers on this network".
    @Published private(set) var likelyBlockedByPrivacy = false

    private var browser: NWBrowser?
    private var listener: NWListener?
    private var browseStartedAt: Date?

    // MARK: - Local identity

    /// SHA-256 prefix of the bundled engine dylib, computed once per launch.
    ///
    /// This is the real compatibility guarantee — `CFBundleShortVersionString` is
    /// what gets *shown* when it fails, but it is the engine bytes that have to
    /// agree.
    private(set) lazy var engineBuildHash: String = {
        let candidates = [
            Bundle.main.privateFrameworksURL?.appendingPathComponent("libjcross_engine_glm.dylib"),
            Bundle.main.bundleURL.appendingPathComponent("Contents/Frameworks/libjcross_engine_glm.dylib"),
            Bundle.main.bundleURL.appendingPathComponent("Contents/MacOS/libjcross_engine_glm.dylib"),
        ].compactMap { $0 }
        for url in candidates where FileManager.default.fileExists(atPath: url.path) {
            if let hash = try? JGenIdentity.fullContentHash(of: url) {
                return String(hash.prefix(12))
            }
        }
        return "unknown"
    }()

    func localIdentity(role: String = "idle", controlPort: UInt16 = 0) -> LocalIdentity {
        LocalIdentity(
            protocolVersion: 1,
            appVersion: Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "0",
            engineBuild: engineBuildHash,
            deviceId: AppState.shared?.pipeDeviceId ?? "",
            deviceName: Host.current().localizedName ?? "Mac",
            ramGB: Int((Double(ProcessInfo.processInfo.physicalMemory) / Double(1 << 30)).rounded()),
            role: role,
            controlPort: controlPort
        )
    }

    // MARK: - Advertising

    /// Publishes this Mac so the peer can find it. `controlPort` must be the
    /// port `JGenAgentServer` actually bound, not the one it preferred.
    func startAdvertising(role: String, controlPort: UInt16) {
        stopAdvertising()
        let identity = localIdentity(role: role, controlPort: controlPort)

        let params = NWParameters.tcp
        params.includePeerToPeer = true
        guard let listener = try? NWListener(using: params) else { return }
        listener.service = NWListener.Service(
            name: identity.deviceName,
            type: Self.serviceType,
            domain: Self.serviceDomain,
            txtRecord: txtRecord(for: identity).data
        )
        // Discovery-only listener: connections for real work arrive on
        // JGenAgentServer (control) and PipeChannel (data), so anything that
        // lands here is cancelled rather than left dangling.
        listener.newConnectionHandler = { $0.cancel() }
        listener.stateUpdateHandler = { [weak self] state in
            Task { @MainActor in
                switch state {
                case .ready:  self?.isAdvertising = true
                case .failed, .cancelled: self?.isAdvertising = false
                default: break
                }
            }
        }
        listener.start(queue: .global(qos: .utility))
        self.listener = listener
    }

    func stopAdvertising() {
        listener?.cancel()
        listener = nil
        isAdvertising = false
    }

    /// Kept under the 255-byte TXT limit by construction: eight short keys and
    /// a device name clipped to 40 characters.
    private func txtRecord(for i: LocalIdentity) -> NWTXTRecord {
        var txt = NWTXTRecord()
        txt["v"]  = String(i.protocolVersion)
        txt["av"] = i.appVersion
        txt["eb"] = i.engineBuild
        txt["id"] = i.deviceId
        txt["nm"] = String(i.deviceName.prefix(40))
        txt["ram"] = String(i.ramGB)
        txt["role"] = i.role
        txt["cp"] = String(i.controlPort)
        return txt
    }

    // MARK: - Browsing

    func startBrowsing() {
        stopBrowsing()
        likelyBlockedByPrivacy = false
        browseStartedAt = Date()

        let params = NWParameters()
        params.includePeerToPeer = true
        let browser = NWBrowser(
            for: .bonjourWithTXTRecord(type: Self.serviceType, domain: Self.serviceDomain),
            using: params
        )

        browser.stateUpdateHandler = { [weak self] state in
            Task { @MainActor in
                guard let self else { return }
                switch state {
                case .ready:
                    self.isBrowsing = true
                case .failed, .cancelled:
                    self.isBrowsing = false
                    // Never reaching .ready is what a denied Local Network
                    // permission looks like from here — there is no distinct
                    // error for it, so the UI has to infer and offer the
                    // System Settings path.
                    self.likelyBlockedByPrivacy = self.peers.isEmpty
                default:
                    break
                }
            }
        }

        browser.browseResultsChangedHandler = { [weak self] results, _ in
            Task { @MainActor in
                self?.apply(results: results)
            }
        }

        browser.start(queue: .global(qos: .utility))
        self.browser = browser
    }

    func stopBrowsing() {
        browser?.cancel()
        browser = nil
        isBrowsing = false
    }

    /// True when a browse has been running long enough that "nothing found" is
    /// meaningful rather than merely early — the point at which the UI should
    /// start suggesting the manual-IP path.
    var browseHasHadTimeToFind: Bool {
        guard let started = browseStartedAt else { return false }
        return Date().timeIntervalSince(started) > 3
    }

    private func apply(results: Set<NWBrowser.Result>) {
        let localId = AppState.shared?.pipeDeviceId ?? ""
        var found: [Peer] = []

        for r in results {
            guard case let .bonjour(txt) = r.metadata else { continue }
            guard case let .service(name, _, _, _) = r.endpoint else { continue }

            let deviceId = txt["id"] ?? ""
            // This Mac advertises too; without this it pairs with itself.
            if !deviceId.isEmpty && deviceId == localId { continue }

            found.append(Peer(
                endpointName: name,
                deviceName: txt["nm"] ?? name,
                deviceId: deviceId,
                appVersion: txt["av"] ?? "?",
                engineBuild: txt["eb"] ?? "?",
                protocolVersion: Int(txt["v"] ?? "") ?? 0,
                ramGB: Int(txt["ram"] ?? "") ?? 0,
                role: txt["role"] ?? "idle",
                controlPort: UInt16(txt["cp"] ?? "") ?? 0,
                host: nil,
                interfaceKind: kind(of: r.interfaces)
            ))
        }

        peers = found.sorted { $0.deviceName < $1.deviceName }
        if !peers.isEmpty { likelyBlockedByPrivacy = false }
    }

    /// Which physical link a result arrived over, so the UI can say so.
    private func kind(of interfaces: [NWInterface]) -> NetworkInterfaces.LinkKind {
        let wifiName = NetworkInterfaces.candidates().first(where: { $0.kind == .wifi })?.name
        let kinds = interfaces.map { NetworkInterfaces.classify(name: $0.name, wifiName: wifiName) }
        return kinds.min(by: { $0.rank < $1.rank }) ?? .other
    }
}
