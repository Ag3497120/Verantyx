import Foundation
import Darwin

/// ThunderboltDetector
/// Automatically detects high-speed network interfaces (like Thunderbolt Bridge `bridge0` or Ethernet `enX`)
/// to ensure Exo clusters prioritize low-latency connections over Wi-Fi (`en0`).
public struct ThunderboltDetector {
    
    /// Returns the IPv4 address of the best available Thunderbolt/Wired interface.
    /// Returns nil if no suitable high-speed interface is found.
    public static func getThunderboltIP() -> String? {
        var bestIP: String? = nil
        var fallbackIP: String? = nil
        
        var ifaddr: UnsafeMutablePointer<ifaddrs>?
        guard getifaddrs(&ifaddr) == 0, let firstAddr = ifaddr else { return nil }
        defer { freeifaddrs(ifaddr) }
        
        var ptr: UnsafeMutablePointer<ifaddrs>? = firstAddr
        
        while let interface = ptr {
            let addrFamily = interface.pointee.ifa_addr.pointee.sa_family
            
            // Target IPv4 only (AF_INET)
            if addrFamily == UInt8(AF_INET) {
                let name = String(cString: interface.pointee.ifa_name)
                
                // Exclude loopback (lo0) and Wi-Fi (en0 is almost universally Wi-Fi on MacBooks)
                if name != "lo0" && name != "en0" {
                    
                    var hostname = [CChar](repeating: 0, count: Int(NI_MAXHOST))
                    let result = getnameinfo(interface.pointee.ifa_addr, 
                                             socklen_t(interface.pointee.ifa_addr.pointee.sa_len),
                                             &hostname, 
                                             socklen_t(hostname.count),
                                             nil, 
                                             socklen_t(0), 
                                             NI_NUMERICHOST)
                    
                    if result == 0 {
                        let ip = String(cString: hostname)
                        
                        // Thunderbolt Bridge is typically "bridge0" in macOS Network Settings.
                        if name == "bridge0" {
                            bestIP = ip
                        }
                        // Other wired connections (en1, en2, etc. from TB docks)
                        else if name.hasPrefix("en") {
                            if fallbackIP == nil {
                                fallbackIP = ip
                            }
                        }
                    }
                }
            }
            ptr = interface.pointee.ifa_next
        }
        
        return bestIP ?? fallbackIP
    }
}
