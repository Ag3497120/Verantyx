import Foundation
import SwiftUI

/// ExoEngine
/// Manages the local `exo` daemon process for distributed inference via Thunderbolt.
@MainActor
public final class ExoEngine: ObservableObject {
    public static let shared = ExoEngine()
    
    @Published public var isRunning: Bool = false
    @Published public var connectedPeers: Int = 0
    
    private var process: Process?
    private var stdoutPipe: Pipe?
    private var stderrPipe: Pipe?
    
    private init() {}
    
    /// Starts the Exo daemon.
    public func start() {
        guard !isRunning else { return }
        
        let tbIP = ThunderboltDetector.getThunderboltIP() ?? "0.0.0.0"
        let msg = tbIP != "0.0.0.0" 
            ? "Starting Exo node bound to Thunderbolt IP: \(tbIP)" 
            : "Starting Exo node bound to 0.0.0.0 (No Thunderbolt bridge detected)"
        
        AppState.shared?.addSystemMessage("🔗 [Exo Engine] \(msg)")
        
        // Command to run exo. We use `uv run exo` in the exo-test directory if it exists,
        // otherwise we fallback to global `exo` command.
        let process = Process()
        
        // Check for local repo installation
        let homeDir = FileManager.default.homeDirectoryForCurrentUser
        let localExoPath = homeDir.appendingPathComponent("verantyx-cli/exo-test/exo").path
        
        if FileManager.default.fileExists(atPath: localExoPath) {
            process.executableURL = URL(fileURLWithPath: "/bin/bash")
            process.arguments = ["-c", "cd \(localExoPath) && uv run exo --host \(tbIP)"]
        } else {
            // Global fallback
            process.executableURL = URL(fileURLWithPath: "/bin/bash")
            process.arguments = ["-c", "exo --host \(tbIP)"]
        }
        
        stdoutPipe = Pipe()
        stderrPipe = Pipe()
        process.standardOutput = stdoutPipe
        process.standardError = stderrPipe
        
        setupLogReaders()
        
        do {
            try process.run()
            self.process = process
            self.isRunning = true
            AppState.shared?.addSystemMessage("✅ [Exo Engine] Node is running.")
            
            // Set dynamic endpoint to 52415
            AppState.shared?.exoEndpoint = "http://\(tbIP == "0.0.0.0" ? "127.0.0.1" : tbIP):52415"
            
        } catch {
            AppState.shared?.addSystemMessage("❌ [Exo Engine] Failed to start: \(error.localizedDescription)")
            self.isRunning = false
        }
    }
    
    public func stop() {
        guard isRunning, let process = process else { return }
        process.terminate()
        self.process = nil
        self.isRunning = false
        AppState.shared?.addSystemMessage("🛑 [Exo Engine] Node stopped.")
    }
    
    private func setupLogReaders() {
        guard let stdoutPipe = stdoutPipe, let stderrPipe = stderrPipe else { return }
        
        stdoutPipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty, let str = String(data: data, encoding: .utf8) else { return }
            Task { @MainActor in
                self?.parseLog(str)
            }
        }
        
        stderrPipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty, let str = String(data: data, encoding: .utf8) else { return }
            Task { @MainActor in
                self?.parseLog(str)
            }
        }
    }
    
    private func parseLog(_ log: String) {
        // Here we parse exo's stdout to detect connected peers if needed.
        // E.g. "Discovered node" or "Connected to node"
        if log.contains("Discovered node") || log.contains("Connected to peer") {
            connectedPeers += 1
            AppState.shared?.addSystemMessage("🤝 [Exo Cluster] Connected to a Thunderbolt peer! (Total Peers: \(connectedPeers))")
        } else if log.contains("Lost connection") || log.contains("Disconnected") {
            connectedPeers = max(0, connectedPeers - 1)
        }
        
        // Push log to the central process log for monitoring without an external terminal
        AppState.shared?.logStore.entries.append(
            AppState.ProcessLogEntry(timestamp: Date(), text: log.trimmingCharacters(in: .whitespacesAndNewlines), kind: .system)
        )
    }
}
