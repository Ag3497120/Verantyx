import Foundation
import SwiftUI

/// VerantyxExpertEngine
/// Specialized chat engine for guiding users through Verantyx IDE setup and CLI mappings.
/// Uses strict L1-L3 spatial memory injection to prevent hallucinations.
@MainActor
final class VerantyxExpertEngine: ObservableObject {
    public static let shared = VerantyxExpertEngine()
    
    @Published var messages: [ChatMessage] = []
    @Published var isGenerating = false
    
    // Condensed L1-L3 Memory Mapping for local LLMs
    private let systemContext = """
    # ROLE
    You are the Verantyx IDE Support Expert. Your job is to help the user configure Verantyx, understand Exo Distributed Clustering, and teach them CLI commands.
    
    # CRITICAL RULE
    Do NOT hallucinate commands. Only use the CLI commands from the exact mapping table below.
    
    # L1-L3 MAPPING: GUI to CLI Commands
    | Goal | GUI Action | CLI Command |
    |------|------------|-------------|
    | Turn on Exo Master | Settings > Model > Click [ Master ] | `verantyx ide config set exo.role master` |
    | Turn on Exo Worker | Settings > Model > Click [ Worker ] | `verantyx ide config set exo.role worker` |
    | Disable Exo | Settings > Model > Click [ Idle ] | `verantyx ide config set exo.enabled false` |
    | Setup Exo Wizard | Settings > Model > Setup | `verantyx ide setup exo` |
    | Change LLM to Ollama | Settings > Model > Local LLM | `verantyx ide config set llm.local ollama` |
    
    # SYSTEM ARCHITECTURE EXPLANATION
    - **Exo**: A distributed inference engine. It splits AI models across multiple Macs via Thunderbolt.
    - **Master (親機)**: The Mac running the Verantyx UI and orchestrating the request.
    - **Worker (子機)**: The Mac providing background compute power.
    - **Auto-Sync**: Verantyx uses Bonjour P2P to automatically set the other Mac to Worker if this Mac is set to Master.
    """
    
    private init() {
        messages.append(ChatMessage(role: .system, content: systemContext))
        messages.append(ChatMessage(role: .assistant, content: "Verantyxサポートボットです。CLIコマンドやExoの設定、分散推論の仕組みについて何でも聞いてください。"))
    }
    
    func sendQuery(_ query: String) async {
        messages.append(ChatMessage(role: .user, content: query))
        isGenerating = true
        
        do {
            let prompt = buildPrompt(from: messages)
            // Use local LLM directly through existing inference engine (e.g., Ollama or MLX)
            let responseText = try await generateFromLocalLLM(prompt)
            messages.append(ChatMessage(role: .assistant, content: responseText))
        } catch {
            messages.append(ChatMessage(role: .assistant, content: "エラーが発生しました: \(error.localizedDescription)"))
        }
        
        isGenerating = false
    }
    
    private func buildPrompt(from msgs: [ChatMessage]) -> String {
        // Simple chat formatting
        return msgs.map { "\($0.role == .user ? "User:" : "Assistant:") \($0.content)" }.joined(separator: "\n")
    }
    
    private func generateFromLocalLLM(_ prompt: String) async throws -> String {
        // Fallback or use OllamaClient depending on what is available
        // Simplified for this architecture wrapper.
        let fullPrompt = systemContext + "\n" + prompt
        let response = await OllamaClient.shared.generate(model: "gemma:27b", prompt: fullPrompt)
        return response ?? "エラー: 応答がありません"
    }
}
