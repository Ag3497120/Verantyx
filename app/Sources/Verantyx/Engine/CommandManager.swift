import Foundation

@MainActor
final class CommandManager: ObservableObject {
    static let shared = CommandManager()

    @Published var availableCommands: Set<String> = []

    private init() {
        // Assume AppState registers the built-in Swift commands here
    }

    func registerCommand(_ command: String) {
        availableCommands.insert(command)
    }

    func unregisterCommand(_ command: String) {
        availableCommands.remove(command)
    }

    func executeCommand(command: String, args: [Any] = []) async throws -> Any? {
        // If it's a known extension command, route it to Node.js
        if availableCommands.contains(command) {
            return try await ExtensionHostManager.shared.sendRequest(method: "commands.executeLocalCommand", params: [
                "command": command,
                "args": args
            ])
        }
        
        // Otherwise handle native IDE commands (e.g., workbench.action.files.save)
        // ...
        return nil
    }
}
