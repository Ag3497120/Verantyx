import Foundation
import Combine

enum ExtensionUIPromptType {
    case quickPick(items: [String], options: [String: Any]?)
    case inputBox(options: [String: Any]?)
}

@MainActor
final class ExtensionUIManager: ObservableObject {
    static let shared = ExtensionUIManager()

    @Published var isPromptPresented: Bool = false
    @Published var currentPrompt: ExtensionUIPromptType? = nil
    
    // QuickPick State
    @Published var quickPickItems: [String] = []
    @Published var quickPickFilteredItems: [String] = []
    @Published var quickPickSearchText: String = ""
    
    // InputBox State
    @Published var inputBoxText: String = ""
    @Published var inputBoxPrompt: String = ""
    
    private var pendingPromptContinuation: CheckedContinuation<Any?, Never>?

    private init() {}

    func showQuickPick(items: [String], options: [String: Any]?) async -> String? {
        self.quickPickItems = items
        self.quickPickFilteredItems = items
        self.quickPickSearchText = ""
        self.currentPrompt = .quickPick(items: items, options: options)
        self.isPromptPresented = true
        
        let result = await withCheckedContinuation { continuation in
            self.pendingPromptContinuation = continuation
        }
        
        self.isPromptPresented = false
        self.currentPrompt = nil
        return result as? String
    }

    func showInputBox(options: [String: Any]?) async -> String? {
        self.inputBoxText = ""
        self.inputBoxPrompt = options?["prompt"] as? String ?? "Enter value"
        self.currentPrompt = .inputBox(options: options)
        self.isPromptPresented = true
        
        let result = await withCheckedContinuation { continuation in
            self.pendingPromptContinuation = continuation
        }
        
        self.isPromptPresented = false
        self.currentPrompt = nil
        return result as? String
    }

    func submitPrompt(value: Any?) {
        guard let continuation = pendingPromptContinuation else { return }
        self.pendingPromptContinuation = nil
        continuation.resume(returning: value)
    }

    func cancelPrompt() {
        guard let continuation = pendingPromptContinuation else { return }
        self.pendingPromptContinuation = nil
        continuation.resume(returning: nil)
    }
}
