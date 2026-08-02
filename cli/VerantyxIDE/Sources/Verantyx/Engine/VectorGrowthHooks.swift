import Foundation

/// Status + future hook points for using JGEN as the growth **actuator**
/// (hidden-state inject / vector bus). Accepting quarantine items does not
/// auto-write the bus today — only records a note for a later slice.
@MainActor
final class VectorGrowthHooks: ObservableObject {
    static let shared = VectorGrowthHooks()

    enum QuarantineKind: String {
        case domainModule
        case aiFact
    }

    struct AcceptNote: Identifiable {
        let id = UUID()
        let kind: QuarantineKind
        let index: Int
        let at: Date
    }

    @Published private(set) var recentAccepts: [AcceptNote] = []

    /// Reserved: after accept, a future slice may encode a trace onto the
    /// JGEN vector bus. Must never auto-promote Vera store entries.
    private(set) var busWriteEnabled = false

    private init() {}

    func noteQuarantineAccepted(kind: QuarantineKind, index: Int) {
        recentAccepts.insert(AcceptNote(kind: kind, index: index, at: Date()), at: 0)
        if recentAccepts.count > 40 {
            recentAccepts = Array(recentAccepts.prefix(40))
        }
        // Hook point only — no bus write while busWriteEnabled is false.
        if busWriteEnabled {
            // Future: JCrossChatManager / JGenVectorBusMemory append.
        }
    }

    func statusMap() async -> [String: Any] {
        let loaded = await JCrossChatManager.shared.loadedModelName
        let agentRunning = await JGenAgentServer.shared.isRunning
        let agentPort = await JGenAgentServer.shared.port
        let harness = CouncilSettingsStore.shared.useVeraHarnessForChat
        let mode = CouncilSettingsStore.shared.cognitionMode.rawValue
        return [
            "ok": true,
            "jgen_loaded": loaded != nil,
            "jgen_model": loaded ?? "",
            "jgen_agent_server_running": agentRunning,
            "jgen_agent_server_port": Int(agentPort),
            "vera_harness": harness,
            "cognition_mode": mode,
            "actuator": "jgen_inject_multi_layer_and_vector_bus",
            "bus_write_on_accept": busWriteEnabled,
            "recent_accepts": recentAccepts.prefix(10).map { n -> [String: Any] in
                [
                    "kind": n.kind.rawValue,
                    "index": n.index,
                    "at": ISO8601DateFormatter().string(from: n.at),
                ]
            },
        ]
    }
}
