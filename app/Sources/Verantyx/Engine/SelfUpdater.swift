import Foundation
import SwiftUI
import AppKit

@MainActor
class SelfUpdater: ObservableObject {
    static let shared = SelfUpdater()
    
    @Published var isChecking = false
    @Published var updateAvailable = false
    @Published var latestVersion = ""
    @Published var downloadProgress: Double = 0.0
    @Published var isDownloading = false
    @Published var errorMessage: String? = nil
    
    private let repoURL = "https://api.github.com/repos/Ag3497120/Verantyx/releases/latest"
    private var pkgDownloadURL: URL? = nil
    
    var currentVersion: String {
        Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "0.0.0"
    }
    
    func checkForUpdates(background: Bool = false) async {
        isChecking = true
        errorMessage = nil
        defer { isChecking = false }
        
        do {
            guard let url = URL(string: repoURL) else { return }
            let (data, _) = try await URLSession.shared.data(from: url)
            
            if let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
               let tagName = json["tag_name"] as? String,
               let assets = json["assets"] as? [[String: Any]] {
                
                let latest = tagName.replacingOccurrences(of: "v", with: "")
                self.latestVersion = latest
                
                // Compare versions
                if latest.compare(currentVersion, options: .numeric) != .orderedAscending {
                    self.updateAvailable = true
                    
                    // Find DMG asset
                    if let dmgAsset = assets.first(where: { ($0["name"] as? String ?? "").hasSuffix(".dmg") }),
                       let urlString = dmgAsset["browser_download_url"] as? String,
                       let downloadURL = URL(string: urlString) {
                        self.pkgDownloadURL = downloadURL
                    }
                } else {
                    self.updateAvailable = false
                }
            }
        } catch {
            if !background {
                self.errorMessage = "Failed to check for updates: \(error.localizedDescription)"
            }
        }
    }
    
    func downloadAndInstallUpdate() {
        guard let url = pkgDownloadURL else { return }
        isDownloading = true
        errorMessage = nil
        
        let destination = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("VerantyxUpdate_\(latestVersion).dmg")
        
        // Remove old file if exists
        try? FileManager.default.removeItem(at: destination)
        
        let task = URLSession.shared.downloadTask(with: url) { [weak self] localURL, response, error in
            if let error = error {
                Task { @MainActor in
                    self?.isDownloading = false
                    self?.errorMessage = "Download failed: \(error.localizedDescription)"
                }
                return
            }
            
            guard let localURL = localURL else {
                Task { @MainActor in self?.isDownloading = false }
                return
            }
            
            do {
                try FileManager.default.moveItem(at: localURL, to: destination)
                let script = """
                #!/bin/bash
                while kill -0 \(ProcessInfo.processInfo.processIdentifier) 2>/dev/null; do
                    sleep 0.5
                done
                MOUNT_INFO=$(hdiutil attach "\(destination.path)" -nobrowse)
                MOUNT_POINT=$(echo "$MOUNT_INFO" | grep "/Volumes/" | awk -F '\t' '{print $3}' | xargs)
                if [ -n "$MOUNT_POINT" ]; then
                    rm -rf /Applications/Verantyx.app
                    cp -R "$MOUNT_POINT/Verantyx.app" /Applications/
                    hdiutil detach "$MOUNT_POINT"
                    open /Applications/Verantyx.app
                fi
                """
                let scriptURL = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("verantyx_update.sh")
                try script.write(to: scriptURL, atomically: true, encoding: .utf8)
                try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: scriptURL.path)
                
                let process = Process()
                process.executableURL = URL(fileURLWithPath: "/bin/bash")
                process.arguments = ["-c", "nohup \(scriptURL.path) >/dev/null 2>&1 &"]
                try process.run()
                
                Task { @MainActor in
                    self?.isDownloading = false
                    // Terminate ourself to let the installer work
                    DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
                        NSApplication.shared.terminate(nil)
                    }
                }
            } catch {
                Task { @MainActor in
                    self?.isDownloading = false
                    self?.errorMessage = "Failed to prepare update: \(error.localizedDescription)"
                }
            }
        }
        
        // We can track progress if we use a delegate, but for simplicity we'll just show an indeterminate spinner
        task.resume()
    }
}
