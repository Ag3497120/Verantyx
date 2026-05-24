import Foundation
import SwiftUI
import Network

/// ExoClusterSync
/// Manages P2P role synchronization (Master/Worker) for Verantyx IDE instances
/// connected on the same local network / Thunderbolt bridge via Bonjour (NetService).
@MainActor
public final class ExoClusterSync: NSObject, ObservableObject, NetServiceDelegate, NetServiceBrowserDelegate {
    public static let shared = ExoClusterSync()
    
    private var netService: NetService?
    private var browser: NetServiceBrowser?
    private var discoveredServices: [NetService] = []
    
    private let serviceType = "_verantyx_exo._tcp."
    private let serviceDomain = "local."
    
    override private init() {
        super.init()
    }
    
    /// Starts advertising our current role and browsing for peers.
    public func start() {
        startAdvertising()
        startBrowsing()
    }
    
    public func stop() {
        netService?.stop()
        browser?.stop()
        netService = nil
        browser = nil
        discoveredServices.removeAll()
    }
    
    /// Updates the TXT record when our role changes.
    func updateRole(_ role: AppState.ExoRole) {
        guard let netService = netService else { return }
        let deviceId = AppState.shared?.exoDeviceId ?? UUID().uuidString
        let txtDict = ["deviceId": deviceId.data(using: .utf8)!, "role": role.rawValue.data(using: .utf8)!]
        let txtData = NetService.data(fromTXTRecord: txtDict)
        netService.setTXTRecord(txtData)
    }
    
    private func startAdvertising() {
        let port: Int32 = 52416 // Dummy port just for Bonjour advertising
        let deviceName = Host.current().localizedName ?? "VerantyxIDE"
        let serviceName = "VerantyxExo-\(UUID().uuidString.prefix(6))"
        
        netService = NetService(domain: serviceDomain, type: serviceType, name: serviceName, port: port)
        netService?.delegate = self
        
        // Initial TXT record
        updateRole(AppState.shared?.exoRole ?? .idle)
        
        netService?.publish()
    }
    
    private func startBrowsing() {
        browser = NetServiceBrowser()
        browser?.delegate = self
        browser?.searchForServices(ofType: serviceType, inDomain: serviceDomain)
    }
    
    // MARK: - NetServiceBrowserDelegate
    
    public func netServiceBrowser(_ browser: NetServiceBrowser, didFind service: NetService, moreComing: Bool) {
        // Resolve the service to read its TXT records
        service.delegate = self
        service.resolve(withTimeout: 5.0)
        discoveredServices.append(service)
    }
    
    public func netServiceBrowser(_ browser: NetServiceBrowser, didRemove service: NetService, moreComing: Bool) {
        discoveredServices.removeAll { $0 == service }
    }
    
    // MARK: - NetServiceDelegate
    
    public func netServiceDidResolveAddress(_ sender: NetService) {
        processTXTRecord(for: sender)
    }
    
    public func netService(_ sender: NetService, didUpdateTXTRecord data: Data) {
        processTXTRecord(for: sender)
    }
    
    private func processTXTRecord(for service: NetService) {
        guard let txtData = service.txtRecordData() else { return }
        let dict = NetService.dictionary(fromTXTRecord: txtData)
        
        guard let roleData = dict["role"], let deviceIdData = dict["deviceId"],
              let roleStr = String(data: roleData, encoding: .utf8),
              let peerDeviceId = String(data: deviceIdData, encoding: .utf8) else {
            return
        }
        
        let myDeviceId = AppState.shared?.exoDeviceId ?? ""
        if peerDeviceId == myDeviceId { return } // Ignore our own broadcast
        
        Task { @MainActor in
            let myRole = AppState.shared?.exoRole ?? .idle
            
            // Auto-Sync Logic: If a peer is Master and we are Idle, we automatically become Worker.
            if roleStr == AppState.ExoRole.master.rawValue && myRole == .idle {
                AppState.shared?.addSystemMessage("📡 [Cluster Sync] Detected Master node. Automatically switching to Worker mode.")
                AppState.shared?.exoRole = .worker
                AppState.shared?.exoEnabled = true
                ExoEngine.shared.start()
            }
        }
    }
}
