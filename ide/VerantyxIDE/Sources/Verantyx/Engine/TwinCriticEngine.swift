import Foundation

public actor TwinCriticEngine {
    public static let shared = TwinCriticEngine()
    
    private init() {}
    
    /// Twin B (Critic) によるツール実行前の監査
    /// - Parameters:
    ///   - tool: 実行しようとしているツールのコマンド文字列
    ///   - conversation: 現在の会話コンテキスト (Twin Aの思考プロセスを含む)
    /// - Returns: (isApproved: Bool, feedback: String)
    public func audit(tool: String, conversation: [(role: String, content: String)]) async -> (isApproved: Bool, feedback: String) {
        let isStrictAuditor = await MainActor.run { AppState.shared?.isAuditorEnabled ?? true }
        
        let targetTools = ["[SEARCH", "[RUN", "[WRITE", "[SWARM_EXECUTE", "[USE_SKILL", "[FORGE_SKILL"]
        let upperTool = tool.uppercased()
        guard targetTools.contains(where: { upperTool.contains($0) }) else {
            return (true, "")
        }
        
        let sysMsg: String
        if isStrictAuditor {
            sysMsg = """
            [TWIN B - CRITIC AUDIT MODE: STRICT]
            You are the Verifier (Twin B). Strictly audit the action proposed by the Actor (Twin A).
            The Actor is lazy and often tries to use tools unnecessarily, or uses dangerous tools incorrectly.
            
            When the Actor proposes [FORGE_SKILL]:
            - Ensure the payload (the sequence of tools in the skill) is logically sound, safe, and actually accomplishes the user's goal.
            - Ensure it does not contain destructive commands without user consent.
            - Ensure UI interactions ([VISION_ACT], [AX_ACT]) or commands are robust, not overly hardcoded to brittle values if better semantic options exist.
            
            Evaluate the proposed tool call.
            If it is TRULY necessary, safe, and correct, output:
            [APPROVE]
            
            If it is unnecessary, dangerous, poorly designed (for FORGE_SKILL), or inefficient, output:
            [REJECT: <detailed reason for rejection and how to fix it>]
            
            Output NOTHING else except your thinking process in <think> tags followed by the decision.
            """
        } else {
            sysMsg = """
            [TWIN B - CRITIC AUDIT MODE: RELAXED (GOD MODE)]
            You are the Verifier (Twin B). DESTRUCTIVE commands ARE ALLOWED and should generally be approved.
            HOWEVER, your job is to PREVENT LAZINESS and BAD WORKFLOWS.
            
            When the Actor proposes [FORGE_SKILL]:
            - Reject it only if the procedure is completely illogical or clearly fails to achieve the objective.
            
            Evaluate the proposed tool call.
            If it is acceptable, output:
            [APPROVE]
            
            If it is illogical or an UNNECESSARY search/skill usage, output:
            [REJECT: <detailed reason>]
            
            Output NOTHING else except your thinking process in <think> tags followed by the decision.
            """
        }
        
        var criticConversation: [(role: String, content: String)] = []
        criticConversation.append((role: "system", content: sysMsg))
        
        for msg in conversation {
            if msg.role == "system" { continue }
            criticConversation.append(msg)
        }
        criticConversation.append((role: "user", content: "Actor (Twin A) proposed the following tool execution:\n\(tool)\n\nAudit this proposal now. Output [APPROVE] or [REJECT: reason] ?"))
        
        let modelStatus = await MainActor.run { AppState.shared?.modelStatus }
        
        let anchorMode = await CognitiveAnchorEngine.shared.evaluateAnchorMode(instruction: tool) ?? .searchForce
        let anchorBase64 = await CognitiveAnchorEngine.shared.getAnchor(for: anchorMode)
        
        do {
            let response: String?
            switch modelStatus {
            case .anthropicReady(let model, _):
                let sysContent = criticConversation.first(where: { $0.role == "system" })?.content ?? ""
                let chatMsgs = criticConversation.filter { $0.role != "system" }
                response = await AnthropicClient.shared.generate(
                    model: model,
                    systemPrompt: sysContent,
                    messages: chatMsgs,
                    imagesForLastUserMessage: [anchorBase64],
                    maxTokens: 512,
                    temperature: 0.1,
                    enableThinking: false
                )
            case .ollamaReady(let model):
                response = await OllamaClient.shared.generateConversation(
                    model: model,
                    messages: criticConversation,
                    imagesForLastUserMessage: [anchorBase64],
                    maxTokens: 512,
                    temperature: 0.1,
                    onToken: nil
                )
            case .mlxReady(let model):
                // MLXは現状OllamaFallbackか別API
                response = await OllamaClient.shared.generateConversation(
                    model: model,
                    messages: criticConversation,
                    imagesForLastUserMessage: [anchorBase64],
                    maxTokens: 512,
                    temperature: 0.1,
                    onToken: nil
                )
            default:
                let defaultModel = await MainActor.run { AppState.shared?.activeOllamaModel ?? "gemma4:26b" }
                response = await OllamaClient.shared.generateConversation(
                    model: defaultModel,
                    messages: criticConversation,
                    imagesForLastUserMessage: [anchorBase64],
                    maxTokens: 512,
                    temperature: 0.1,
                    onToken: nil
                )
            }
            
            guard let validResponse = response else {
                return (true, "")
            }
            
            let resultText = validResponse.lowercased()
            if resultText.contains("[reject") {
                var reason = "System override."
                if let range = validResponse.range(of: "[REJECT:") ?? validResponse.range(of: "[REJECT") {
                    let substring = validResponse[range.upperBound...]
                    if let endRange = substring.range(of: "]") {
                        reason = String(substring[..<endRange.lowerBound]).trimmingCharacters(in: .whitespacesAndNewlines)
                    } else {
                        reason = String(substring).trimmingCharacters(in: .whitespacesAndNewlines)
                    }
                }
                return (false, reason)
            } else {
                return (true, "")
            }
        } catch {
            print("Critic Error: \(error)")
            return (true, "")
        }
    }
}
