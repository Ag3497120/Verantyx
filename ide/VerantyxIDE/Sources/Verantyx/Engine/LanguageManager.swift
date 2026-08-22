import Foundation

struct LanguageProviderInfo {
    let id: String
    let type: String
    let selector: AnyCodable?
}

struct Position {
    let line: Int
    let character: Int
}

@MainActor
final class LanguageManager: ObservableObject {
    static let shared = LanguageManager()

    @Published var providers: [String: LanguageProviderInfo] = [:]

    private init() {}

    func registerProvider(id: String, type: String, selector: AnyCodable?) {
        providers[id] = LanguageProviderInfo(id: id, type: type, selector: selector)
    }

    func unregisterProvider(id: String) {
        providers.removeValue(forKey: id)
    }

    // Call this from the Swift IDE editor when the user triggers autocomplete
    func provideCompletionItems(for uri: URL, at position: Position) async throws -> Any? {
        // Find providers that match this language
        let matchingProviders = providers.values.filter { $0.type == "CompletionItemProvider" }
        
        // For demonstration, we just query the first one
        guard let provider = matchingProviders.first else { return nil }
        
        return try await ExtensionHostManager.shared.sendRequest(method: "languages.invokeProvider", params: [
            "providerId": provider.id,
            "method": "provideCompletionItems",
            "args": [
                "uri": uri.path,
                "position": [
                    "line": position.line,
                    "character": position.character
                ]
            ]
        ])
    }
    
    // Call this when hovering
    func provideHover(for uri: URL, at position: Position) async throws -> Any? {
        let matchingProviders = providers.values.filter { $0.type == "HoverProvider" }
        guard let provider = matchingProviders.first else { return nil }
        
        return try await ExtensionHostManager.shared.sendRequest(method: "languages.invokeProvider", params: [
            "providerId": provider.id,
            "method": "provideHover",
            "args": [
                "uri": uri.path,
                "position": [
                    "line": position.line,
                    "character": position.character
                ]
            ]
        ])
    }
}
