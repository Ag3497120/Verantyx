import Foundation

/// Turns distributed-inference pairing on and off as one unit.
///
/// Three pieces have to move together and it is easy to get a half-enabled
/// state that looks broken for the wrong reason:
///
///  - the control-plane server must be *bound* before advertising, because the
///    TXT record has to carry the port it actually got. `JGenAgentServer` scans
///    8766–8773, so the preferred port is a request, not a fact — advertising a
///    guessed port is a peer that appears in the list and then refuses to talk.
///  - advertising and browsing are both needed: whoever presses "connect" first
///    has to see the other, and neither Mac knows in advance which that will be.
///  - nothing may listen when pairing is off. This opens a port to the local
///    network, so it is strictly opt-in and reversible.
///
/// Kept separate from the UI so the same enable path serves the settings toggle,
/// app launch (when the user left it on), and tests.
@MainActor
final class PipeCoordinator: ObservableObject {

    static let shared = PipeCoordinator()

    @Published private(set) var isEnabled = false
    @Published private(set) var controlPort: UInt16 = 0
    @Published private(set) var lastError: String?

    private init() {}

    /// Starts the control server, then advertises the port it really bound, then
    /// browses for the peer. Safe to call repeatedly.
    func enable() async {
        guard !isEnabled else { return }
        lastError = nil
        do {
            try await JGenAgentServer.shared.start()
            let bound = await JGenAgentServer.shared.port
            controlPort = bound
            PipeDiscovery.shared.startAdvertising(
                role: PipeSession.shared.role.rawValue, controlPort: bound)
            PipeDiscovery.shared.startBrowsing()
            isEnabled = true
        } catch {
            lastError = "Could not open a port for pairing: \(error.localizedDescription)"
            isEnabled = false
        }
    }

    func disable() {
        PipeDiscovery.shared.stopBrowsing()
        PipeDiscovery.shared.stopAdvertising()
        PipeSession.shared.unpair()
        Task { await JGenAgentServer.shared.stop() }
        controlPort = 0
        isEnabled = false
    }

    /// Re-publishes the TXT record after a role change, so the peer's list stops
    /// showing a stale "idle" next to a Mac that is already a worker.
    func refreshAdvertisedRole() {
        guard isEnabled, controlPort != 0 else { return }
        PipeDiscovery.shared.startAdvertising(
            role: PipeSession.shared.role.rawValue, controlPort: controlPort)
    }

    /// Called at launch. Does nothing unless the user left pairing on.
    ///
    /// Reads UserDefaults directly rather than `AppState.shared`: this runs from
    /// `applicationDidFinishLaunching`, and `AppState.shared` is not assigned
    /// until the main window's `onAppear` — so going through it made this a
    /// silent no-op. The default is the source of truth anyway; AppState's
    /// property is a view of it.
    func restoreIfEnabled() {
        guard UserDefaults.standard.bool(forKey: "pipe_pairing_enabled") else { return }
        Task { await enable() }
    }
}
