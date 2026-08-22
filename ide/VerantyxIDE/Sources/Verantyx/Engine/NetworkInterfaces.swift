import Foundation
import Darwin
import CoreWLAN

/// Enumerates this Mac's usable IPv4 interfaces, classified by link type.
///
/// Replaces `ThunderboltDetector.getThunderboltIP()`, which returned a single
/// `String?` and got two things wrong that matter once a real connection depends
/// on it:
///
///  1. **It never checked whether the interface was up.** A `bridge0` that is
///     configured but has no cable still appears in `getifaddrs` with an address,
///     so it won the preference and produced a dead IP — with no way for the
///     caller to notice or fall back, because only one string came back.
///  2. **It assumed `en0` is Wi-Fi and excluded it.** True on a MacBook, false on
///     a Mac Studio or Mini where `en0` is the built-in Ethernet — i.e. exactly
///     the fastest link available, silently discarded. The Wi-Fi interface name
///     is now asked for rather than guessed.
///
/// Returning the full list (rather than one winner) is also what a
/// "make the connection obvious" UI needs: it can name the link actually in use
/// instead of leaving the user to wonder which path the data took.
enum NetworkInterfaces {

    enum LinkKind: String, Codable {
        /// macOS Thunderbolt Bridge. Fastest local path by a wide margin.
        case thunderboltBridge
        case wired
        case wifi
        case other

        /// Preference order for automatic selection.
        var rank: Int {
            switch self {
            case .thunderboltBridge: return 0
            case .wired:             return 1
            case .wifi:              return 2
            case .other:             return 3
            }
        }

        var displayName: String {
            switch self {
            case .thunderboltBridge: return "Thunderbolt"
            case .wired:             return "Ethernet"
            case .wifi:              return "Wi-Fi"
            case .other:             return "Network"
            }
        }
    }

    struct NetInterface: Identifiable, Equatable {
        let name: String        // bsd name, e.g. "bridge0", "en0"
        let ip: String
        let kind: LinkKind
        var id: String { "\(name)|\(ip)" }

        var label: String { "\(kind.displayName) (\(name)) \(ip)" }
    }

    /// The BSD name of the Wi-Fi interface, asked of CoreWLAN rather than assumed.
    /// `nil` when this Mac has no Wi-Fi hardware, in which case nothing is
    /// classified as `.wifi`.
    private static var wifiInterfaceName: String? {
        CWWiFiClient.shared().interface()?.interfaceName
    }

    /// Every up-and-running IPv4 interface that could carry a peer connection.
    ///
    /// Sorted best-first, so `candidates().first` is the automatic choice while
    /// the rest stay available for display or manual override.
    static func candidates() -> [NetInterface] {
        var out: [NetInterface] = []
        let wifiName = wifiInterfaceName

        var head: UnsafeMutablePointer<ifaddrs>?
        guard getifaddrs(&head) == 0, let first = head else { return [] }
        defer { freeifaddrs(head) }

        var ptr: UnsafeMutablePointer<ifaddrs>? = first
        while let iface = ptr {
            defer { ptr = iface.pointee.ifa_next }

            guard let addr = iface.pointee.ifa_addr,
                  addr.pointee.sa_family == UInt8(AF_INET) else { continue }

            let name = String(cString: iface.pointee.ifa_name)
            if name == "lo0" { continue }

            // The check the old detector was missing. IFF_RUNNING is the one that
            // distinguishes "configured" from "actually carrying traffic".
            let flags = Int32(iface.pointee.ifa_flags)
            guard flags & IFF_UP == IFF_UP, flags & IFF_RUNNING == IFF_RUNNING else { continue }
            if flags & IFF_LOOPBACK == IFF_LOOPBACK { continue }

            var host = [CChar](repeating: 0, count: Int(NI_MAXHOST))
            guard getnameinfo(addr, socklen_t(addr.pointee.sa_len),
                              &host, socklen_t(host.count),
                              nil, 0, NI_NUMERICHOST) == 0 else { continue }
            let ip = String(cString: host)
            // link-local autoconfiguration: no peer is reachable this way.
            if ip.hasPrefix("169.254.") { continue }

            out.append(NetInterface(name: name, ip: ip, kind: classify(name: name, wifiName: wifiName)))
        }

        return out.sorted {
            $0.kind.rank != $1.kind.rank ? $0.kind.rank < $1.kind.rank : $0.name < $1.name
        }
    }

    static func classify(name: String, wifiName: String?) -> LinkKind {
        if name.hasPrefix("bridge") { return .thunderboltBridge }
        if let wifiName, name == wifiName { return .wifi }
        if name.hasPrefix("en") { return .wired }
        return .other
    }

    /// Best interface for reaching a peer, or `nil` when nothing is up.
    static func preferred() -> NetInterface? { candidates().first }

    /// Whether an address belongs to one of this Mac's own interfaces — used to
    /// stop a manually typed IP from pairing the app with itself.
    static func isLocalAddress(_ ip: String) -> Bool {
        candidates().contains { $0.ip == ip } || ip == "127.0.0.1" || ip == "localhost"
    }
}
