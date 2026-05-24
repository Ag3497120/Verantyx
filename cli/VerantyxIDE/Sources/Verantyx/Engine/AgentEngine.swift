import Foundation

// MARK: - AgentEngine
// Orchestrates: instruction + context → LLM inference → (explanation, modifiedCode)
// Approach B: AI can emit [RUN: command] in its response to execute shell commands.

struct AgentResult {
    var explanation: String
    var diff: String?              // full modified file content
    var ranCommands: [String] = [] // commands AI executed
    var commandOutputs: [String] = []
}

actor AgentEngine {

    // MARK: - Main entry point

    func process(
        instruction: String,
        contextFileContent: String?,
        contextFileName: String?,
        modelStatus: AppState.ModelStatus,
        activeOllamaModel: String,
        hasTerminal: Bool = false,
        workspaceURL: URL? = nil
    ) async -> AgentResult {

        let prompt = buildPrompt(
            instruction: instruction,
            fileContent: contextFileContent,
            fileName: contextFileName,
            hasTerminal: hasTerminal
        )

        let rawOutput: String?
        switch modelStatus {
        case .ollamaReady(let model):
            rawOutput = await OllamaClient.shared.generate(
                model: model,
                prompt: prompt,
                maxTokens: 2048,
                temperature: 0.1
            )
        case .mlxReady:
            // Direct in-process MLX inference (no HTTP server)
            rawOutput = try? await MLXRunner.shared.generate(
                prompt: prompt,
                maxTokens: 4096,
                temperature: 0.1
            )
        case .ready:
            rawOutput = await callMLX(prompt: prompt)
        default:
            return AgentResult(
                explanation: "⚠️ No model loaded. Use the model picker to connect Ollama, start MLX server, or download a model.",
                diff: nil
            )
        }

        guard let output = rawOutput, !output.isEmpty else {
            return AgentResult(explanation: "⚠️ Model returned empty response. Try again.", diff: nil)
        }

        return parseOutput(output, originalContent: contextFileContent)
    }

    /// Second pass: given terminal error output, attempt to produce a fix.
    func fixWithErrorOutput(
        originalAIResponse: String,
        errorOutput: String,
        contextFileContent: String?,
        contextFileName: String?,
        activeOllamaModel: String
    ) async -> AgentResult {
        let fixPrompt = buildErrorFixPrompt(
            original: originalAIResponse,
            errorOutput: errorOutput,
            fileContent: contextFileContent,
            fileName: contextFileName
        )
        let fixOutput = await OllamaClient.shared.generate(
            model: activeOllamaModel,
            prompt: fixPrompt,
            maxTokens: 2048,
            temperature: 0.1
        ) ?? ""
        return parseOutput(fixOutput, originalContent: contextFileContent)
    }

    // MARK: - Prompt builder

    private func buildPrompt(
        instruction: String,
        fileContent: String?,
        fileName: String?,
        hasTerminal: Bool = false
    ) -> String {
        let codeSection: String
        if let content = fileContent, !content.isEmpty, let name = fileName {
            codeSection = """
            FILE: \(name)
            ```
            \(content.prefix(8000))
            ```

            """
        } else {
            codeSection = ""
        }

        let terminalSection = hasTerminal ? """

        TOOL: You can execute shell commands by writing [RUN: command] anywhere in your response.
        Example: [RUN: cargo check] or [RUN: swift build] or [RUN: python -m pytest]
        Use this to verify your changes compile/pass tests. The output will be shown to the user.
        """ : ""

        return """
        You are Verantyx, an expert AI coding assistant running locally on Apple Silicon.\(terminalSection)

        Your task:
        1. Read the user's instruction carefully.
        2. If code changes are needed, output the COMPLETE modified file in a fenced code block.
        3. After the code block, write a brief explanation of what you changed and why.
        4. If no code changes are needed, just answer conversationally.
        5. If relevant, include [RUN: command] to verify your changes (e.g. [RUN: cargo check]).

        RULE: When outputting modified code, output the ENTIRE file — not just the changed lines.

        \(codeSection)USER INSTRUCTION: \(instruction)

        YOUR RESPONSE:
        """
    }

    // MARK: - Error fix prompt

    private func buildErrorFixPrompt(
        original: String,
        errorOutput: String,
        fileContent: String?,
        fileName: String?
    ) -> String {
        let fileSection = fileContent.map { "CURRENT FILE:\n```\n\($0.prefix(6000))\n```\n" } ?? ""
        return """
        You previously attempted a code change, but the build/test failed.

        YOUR PREVIOUS RESPONSE:
        \(original.prefix(2000))

        BUILD/TEST ERROR:
        ```
        \(errorOutput.prefix(2000))
        ```

        \(fileSection)
        Please fix the error. Output the COMPLETE corrected file in a fenced code block,
        then explain what went wrong and how you fixed it.

        CORRECTED RESPONSE:
        """
    }

    // MARK: - Output parser

    private func parseOutput(_ raw: String, originalContent: String?) -> AgentResult {
        // 1. Extract [RUN: cmd] tool calls
        let runPattern = #"\[RUN:\s*([^\]]+)\]"#
        var ranCommands: [String] = []
        if let regex = try? NSRegularExpression(pattern: runPattern) {
            let matches = regex.matches(in: raw, range: NSRange(raw.startIndex..., in: raw))
            ranCommands = matches.compactMap { m in
                Range(m.range(at: 1), in: raw).map { String(raw[$0]).trimmingCharacters(in: .whitespaces) }
            }
        }
        // Remove [RUN:...] tags from display text
        let cleanedRaw = raw.replacingOccurrences(of: runPattern, with: "", options: .regularExpression)

        // 2. Extract fenced code block
        let pattern = #"```(?:\w+)?\n([\s\S]*?)```"#
        if let regex = try? NSRegularExpression(pattern: pattern),
           let match = regex.firstMatch(in: cleanedRaw, range: NSRange(cleanedRaw.startIndex..., in: cleanedRaw)),
           let range = Range(match.range(at: 1), in: cleanedRaw) {

            let modifiedCode = String(cleanedRaw[range])
            let afterCode = cleanedRaw.components(separatedBy: "```").last ?? ""
            let explanation = afterCode.trimmingCharacters(in: .whitespacesAndNewlines)

            if let orig = originalContent,
               modifiedCode.trimmingCharacters(in: .whitespacesAndNewlines) != orig.trimmingCharacters(in: .whitespacesAndNewlines) {
                return AgentResult(
                    explanation: explanation.isEmpty ? "Changes applied." : explanation,
                    diff: modifiedCode,
                    ranCommands: ranCommands
                )
            }
        }

        // No code block — conversational answer
        return AgentResult(
            explanation: cleanedRaw.trimmingCharacters(in: .whitespacesAndNewlines),
            diff: nil,
            ranCommands: ranCommands
        )
    }

    // MARK: - MLX placeholder (Phase 2)

    private func callMLX(prompt: String) async -> String? {
        // TODO: wire MLXExecutor in Phase 2
        return "MLX inference not yet connected. Use Ollama for now."
    }
}
