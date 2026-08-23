import Foundation

/// The outgoing half of the control plane: calls the peer's `/pipe/*`.
///
/// Every method reports a *reason* on failure rather than a bare error, because
/// the connection UI shows exactly one sentence and one button per failure, and
/// "something went wrong" is not actionable. The peer already phrases version
/// and busy rejections for a human; those strings are passed through verbatim
/// rather than re-worded here, so the two machines never describe the same
/// refusal differently.
actor PipeClient {

    static let shared = PipeClient()

    private init() {}

    struct Hello: Sendable, Equatable {
        var protocolVersion: Int
        var appVersion: String
        var engineBuild: String
        var deviceId: String
        var deviceName: String
        var ramGB: Int
        var freeDiskGB: Double
        var role: String
        var paired: Bool
        var peerName: String
    }

    struct RemoteModel: Sendable, Equatable, Identifiable {
        var name: String
        var sizeBytes: UInt64
        var structuralHash: String
        var metaHash: String
        var contentHash: String?
        var contentHashKind: String?
        var archSupported: Bool
        var id: String { name }

        var sizeGB: Double { Double(sizeBytes) / Double(1 << 30) }

        var identity: JGenIdentity.Identity {
            JGenIdentity.Identity(
                fileSize: sizeBytes,
                structuralHash: structuralHash,
                contentHash: contentHash,
                contentHashKind: contentHashKind.flatMap { JGenIdentity.Identity.ContentHashKind(rawValue: $0) },
                metaHash: metaHash)
        }
    }

    enum PairResult: Sendable {
        case became(role: String, peer: PipeStore.PeerInfo, models: [RemoteModel])
        /// The peer kept Master; this Mac must take Worker.
        case lostTiebreak(reason: String)
        case refused(reason: String)
    }

    enum ClientError: LocalizedError {
        case unreachable(String)
        case badResponse(String)

        var errorDescription: String? {
            switch self {
            case .unreachable(let h):
                return "No answer from \(h). Check that the other Mac is awake, on the same "
                     + "network, and has pairing switched on."
            case .badResponse(let m):
                return m
            }
        }
    }

    /// Short: this gates UI, so it must fail fast when nothing is there.
    private func session(timeout: TimeInterval) -> (URLSession, TimeInterval) {
        (URLSession.shared, timeout)
    }

    private func get(_ host: String, _ port: UInt16, _ path: String,
                     timeout: TimeInterval = 5) async throws -> [String: Any] {
        guard let url = URL(string: "http://\(host):\(port)\(path)") else {
            throw ClientError.badResponse("Bad address: \(host):\(port)")
        }
        var req = URLRequest(url: url)
        req.timeoutInterval = timeout
        do {
            let (data, _) = try await URLSession.shared.data(for: req)
            guard let j = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                throw ClientError.badResponse("Unreadable reply from \(host).")
            }
            return j
        } catch let e as ClientError {
            throw e
        } catch {
            throw ClientError.unreachable("\(host):\(port)")
        }
    }

    private func post(_ host: String, _ port: UInt16, _ path: String, body: [String: Any],
                      timeout: TimeInterval = 30) async throws -> (Int, [String: Any]) {
        guard let url = URL(string: "http://\(host):\(port)\(path)") else {
            throw ClientError.badResponse("Bad address: \(host):\(port)")
        }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.timeoutInterval = timeout
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONSerialization.data(withJSONObject: body)
        do {
            let (data, resp) = try await URLSession.shared.data(for: req)
            let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
            let j = (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
            return (code, j)
        } catch {
            throw ClientError.unreachable("\(host):\(port)")
        }
    }

    // MARK: - Calls

    func hello(host: String, port: UInt16) async throws -> Hello {
        let j = try await get(host, port, "/pipe/hello")
        return Hello(
            protocolVersion: j["protocol_version"] as? Int ?? 0,
            appVersion: j["app_version"] as? String ?? "?",
            engineBuild: j["engine_build"] as? String ?? "?",
            deviceId: j["device_id"] as? String ?? "",
            deviceName: j["device_name"] as? String ?? host,
            ramGB: j["ram_gb"] as? Int ?? 0,
            freeDiskGB: j["free_disk_gb"] as? Double ?? 0,
            role: j["role"] as? String ?? "idle",
            paired: j["paired"] as? Bool ?? false,
            peerName: j["peer_name"] as? String ?? "")
    }

    /// Declares this Mac as Master to the peer.
    ///
    /// The version triple travels in the request so the *peer* decides
    /// compatibility and phrases the refusal — one implementation of that rule,
    /// on the side that is about to give up control of its own engine.
    func pairAsMaster(host: String, port: UInt16, sessionId: String,
                      localControlPort: UInt16) async throws -> PairResult {
        let store = PipeStore.shared
        let v = store.localVersion()
        let body: [String: Any] = [
            "session_id": sessionId,
            "device_id": store.localDeviceId,
            "device_name": store.deviceName,
            "app_version": v.appVersion,
            "engine_build": v.engineBuild,
            "protocol_version": v.protocolVersion,
            "ram_gb": store.ramGB,
            "free_disk_gb": PipeStore.freeDiskGB(),
            "control_port": Int(localControlPort),
        ]
        let (code, j) = try await post(host, port, "/pipe/pair", body: body)
        switch code {
        case 200:
            let peer = PipeStore.PeerInfo(
                deviceId: j["device_id"] as? String ?? "",
                deviceName: j["device_name"] as? String ?? host,
                appVersion: v.appVersion,          // matched, or we would not be here
                engineBuild: v.engineBuild,
                protocolVersion: v.protocolVersion,
                ramGB: j["ram_gb"] as? Int ?? 0,
                freeDiskGB: j["free_disk_gb"] as? Double ?? 0,
                host: host,
                controlPort: port)
            return .became(role: j["role"] as? String ?? "worker",
                           peer: peer,
                           models: Self.decodeModels(j["models"]))
        case 409:
            return .lostTiebreak(reason: j["reason"] as? String
                                 ?? "The other Mac won the Master tiebreak.")
        default:
            return .refused(reason: j["reason"] as? String
                            ?? "The other Mac refused the connection.")
        }
    }

    func unpair(host: String, port: UInt16) async {
        _ = try? await post(host, port, "/pipe/unpair", body: [:], timeout: 5)
    }

    func models(host: String, port: UInt16) async throws -> [RemoteModel] {
        Self.decodeModels(try await get(host, port, "/pipe/models", timeout: 30)["models"])
    }

    /// Pushes a resolved split to the worker. Master-only by construction.
    func pushState(host: String, port: UInt16, mode: String, k: Int) async {
        _ = try? await post(host, port, "/pipe/state", body: ["mode": mode, "k": k], timeout: 10)
    }

    /// Worker asking the master to change the split.
    func requestSplit(host: String, port: UInt16, mode: String, k: Int) async -> String? {
        guard let (code, j) = try? await post(host, port, "/pipe/split",
                                              body: ["mode": mode, "k": k], timeout: 10)
        else { return "Could not reach the Master." }
        return code == 200 ? nil : (j["reason"] as? String ?? "The Master refused the change.")
    }

    /// Round-trip time and throughput on the link actually in use, so the paired
    /// screen can name it instead of leaving the user to guess which path the
    /// data took.
    func measureLink(host: String, port: UInt16) async -> (rttMs: Double, mbPerSec: Double)? {
        let start = Date()
        guard (try? await get(host, port, "/pipe/hello", timeout: 5)) != nil else { return nil }
        let rtt = Date().timeIntervalSince(start)

        // The models listing is the largest cheap payload available; good enough
        // to distinguish Thunderbolt from Wi-Fi, which is all the UI claims.
        let t0 = Date()
        guard let j = try? await get(host, port, "/pipe/models", timeout: 30),
              let data = try? JSONSerialization.data(withJSONObject: j) else {
            return (rtt * 1000, 0)
        }
        let elapsed = max(Date().timeIntervalSince(t0), 0.001)
        return (rtt * 1000, Double(data.count) / elapsed / 1_000_000)
    }

    private static func decodeModels(_ raw: Any?) -> [RemoteModel] {
        guard let arr = raw as? [[String: Any]] else { return [] }
        return arr.map { m in
            RemoteModel(
                name: m["name"] as? String ?? "?",
                // Sent as a string; see the encoder. Falls back to a number so
                // a peer on an older protocol still parses.
                sizeBytes: UInt64(m["size_bytes"] as? String ?? "")
                    ?? UInt64((m["size_bytes"] as? NSNumber)?.uint64Value ?? 0),
                structuralHash: m["structural_hash"] as? String ?? "",
                metaHash: m["meta_hash"] as? String ?? "",
                contentHash: m["content_hash"] as? String,
                contentHashKind: m["content_hash_kind"] as? String,
                archSupported: m["arch_supported"] as? Bool ?? false)
        }
    }
}
