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
    
    // Condensed L1-L3 Memory Mapping for local LLMs.
    //
    // The rows here are a contract: the bot is told not to invent commands, so
    // every row must correspond to something that actually exists in the build.
    // The previous version described an "Exo Distributed Clustering" feature
    // (Master/Worker roles, a setup wizard, Bonjour auto-sync) that had already
    // become unreachable in the UI — the bot was confidently explaining a
    // feature the user could not find. Distributed inference is being rebuilt
    // from scratch (Milestone U); rows for it get added back when the new
    // connection UI actually ships, not before.
    private let systemContext = """
    # ROLE
    You are the Verantyx IDE Support Expert. Your job is to help the user configure Verantyx and teach them CLI commands.

    # CRITICAL RULE
    Do NOT hallucinate commands. Only use the CLI commands from the exact mapping table below.
    If the user asks about something not in the table, say plainly that you do not
    have a verified command for it rather than guessing one.

    # L1-L3 MAPPING: GUI to CLI Commands
    | Goal | GUI Action | CLI Command |
    |------|------------|-------------|
    | Change LLM to Ollama | Settings > Model > Local LLM | `verantyx ide config set llm.local ollama` |
    """

    private init() {
        messages.append(ChatMessage(role: .system, content: systemContext))
        messages.append(ChatMessage(role: .assistant, content: "Verantyxサポートボットです。CLIコマンドや設定について聞いてください。"))
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
        let response = await OllamaClient.shared.generate(model: "verantyx-gemma:latest", prompt: fullPrompt)
        return response ?? "エラー: 応答がありません"
    }
}
