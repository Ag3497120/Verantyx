import Foundation
import SwiftUI

/// ExoSetupWizard
/// Scans the system for `uv` and `exo` installations and automates setup via Terminal.app.
@MainActor
public final class ExoSetupWizard: ObservableObject {
    public static let shared = ExoSetupWizard()
    
    public enum SetupState {
        case idle
        case scanning
        case needsLLM
        case needsUV
        case needsExo
        case ready
    }
    
    @Published public var state: SetupState = .idle
    @Published public var uvPath: String?
    @Published public var exoPath: String?
    
    private init() {}
    
    /// Scans the system paths to detect existing installations.
    public func scan() {
        state = .scanning
        
        let fm = FileManager.default
        let home = fm.homeDirectoryForCurrentUser.path
        
        // Scan for UV
        let uvPossiblePaths = [
            "\(home)/.cargo/bin/uv",
            "/opt/homebrew/bin/uv",
            "/usr/local/bin/uv"
        ]
        
        uvPath = uvPossiblePaths.first(where: { fm.fileExists(atPath: $0) })
        
        // Scan for Exo
        let exoPossiblePaths = [
            "\(home)/.local/bin/exo",
            "\(home)/verantyx-cli/exo-test/exo"
        ]
        
        exoPath = exoPossiblePaths.first(where: { fm.fileExists(atPath: $0) })
        
        // Check local LLM
        let hasOllama = AppState.shared?.ollamaEndpoint.isEmpty == false
        let hasMLX = AppState.shared?.activeMlxModel.isEmpty == false
        
        if !hasOllama && !hasMLX {
            state = .needsLLM
        } else if uvPath == nil {
            state = .needsUV
        } else if exoPath == nil {
            state = .needsExo
        } else {
            state = .ready
        }
    }
    
    /// Opens the macOS Terminal to install UV.
    public func installUV() {
        let script = """
        tell application "Terminal"
            do script "echo '\\033[1;36m[Verantyx Setup] Installing uv...\\033[0m'; curl -LsSf https://astral.sh/uv/install.sh | sh; echo '\\033[1;32mInstallation complete! You can close this window and return to Verantyx IDE.\\033[0m'"
            activate
        end tell
        """
        runAppleScript(script)
    }
    
    /// Opens the macOS Terminal to install Exo via uv tool.
    public func installExoGlobal() {
        let script = """
        tell application "Terminal"
            do script "echo '\\033[1;36m[Verantyx Setup] Installing exo via uv tool...\\033[0m'; ~/.cargo/bin/uv tool install exo-explore; echo '\\033[1;32mInstallation complete! You can close this window and return to Verantyx IDE.\\033[0m'"
            activate
        end tell
        """
        runAppleScript(script)
    }
    
    private func runAppleScript(_ source: String) {
        var error: NSDictionary?
        if let appleScript = NSAppleScript(source: source) {
            appleScript.executeAndReturnError(&error)
            if let err = error {
                print("AppleScript Error: \(err)")
                AppState.shared?.addSystemMessage("❌ [Setup Wizard] AppleScript failed to run terminal command.")
            }
        }
    }
}
