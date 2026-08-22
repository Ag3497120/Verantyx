import Foundation

/// SwiftUI's view of pairing state.
///
/// Deliberately not the source of truth — `PipeStore` is. This object only
/// republishes the store's snapshot so views can observe it. The split exists
/// because the control plane has to keep answering peers while the main thread
/// is busy (a modal dialog is enough to stall it), and a `@Published` property
/// cannot be read off the main actor.
///
/// Nothing here decides anything: no version gate, no tiebreak, no role
/// assignment. Those all live in `PipeStore` so that exactly one implementation
/// exists and the network path and the UI path cannot drift apart.
@MainActor
final class PipeSession: ObservableObject {

    static let shared = PipeSession()

    typealias Role = PipeStore.Role
    typealias SplitMode = PipeStore.SplitMode
    typealias PeerInfo = PipeStore.PeerInfo
    typealias ModelEntry = PipeStore.ModelEntry

    @Published private(set) var role: Role = .idle
    @Published private(set) var sessionId: String = ""
    @Published private(set) var peer: PeerInfo?
    @Published private(set) var splitMode: SplitMode = .auto
    @Published private(set) var splitK: Int = 0
    @Published private(set) var lastError: String?

    var isPaired: Bool { role != .idle && peer != nil }

    private var timer: Timer?

    private init() {
        refresh()
        // Polled rather than pushed: the store is written from network threads,
        // and a callback into the main actor from there would reintroduce the
        // coupling this split exists to remove. One second is imperceptible for
        // state that only changes on an explicit user action.
        timer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.refresh() }
        }
    }

    func refresh() {
        let s = PipeStore.shared.snapshot()
        if role != s.role { role = s.role }
        if sessionId != s.sessionId { sessionId = s.sessionId }
        if peer != s.peer { peer = s.peer }
        if splitMode != s.splitMode { splitMode = s.splitMode }
        if splitK != s.splitK { splitK = s.splitK }
        if lastError != s.lastError { lastError = s.lastError }
    }

    // MARK: - Actions (all delegate to the store, then refresh immediately)

    func becomeMaster(peer remote: PeerInfo, sessionId newId: String) {
        PipeStore.shared.becomeMaster(peer: remote, sessionId: newId)
        refresh()
    }

    func unpair() {
        PipeStore.shared.unpair()
        refresh()
    }

    func setSplit(mode: SplitMode, k: Int) {
        PipeStore.shared.setSplit(mode: mode, k: k)
        refresh()
    }

    func localModels() -> [ModelEntry] { PipeStore.shared.localModels() }

    static func freeDiskGB() -> Double { PipeStore.freeDiskGB() }

    /// This Mac's descriptor for an outgoing pair request.
    func localPeerInfo(host: String, controlPort: UInt16) -> PeerInfo {
        let id = PipeDiscovery.shared.localIdentity()
        return PeerInfo(
            deviceId: PipeStore.shared.localDeviceId,
            deviceName: id.deviceName,
            appVersion: id.appVersion,
            engineBuild: id.engineBuild,
            protocolVersion: id.protocolVersion,
            ramGB: id.ramGB,
            freeDiskGB: PipeStore.freeDiskGB(),
            host: host,
            controlPort: controlPort
        )
    }
}
