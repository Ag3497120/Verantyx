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

        var annotatedSource: String? = nil
        var unobfuscatedIR: JCrossIRDocument? = nil

        if let content = contextFileContent, let name = contextFileName {
            let ext = URL(fileURLWithPath: name).pathExtension.lowercased()
            let language = JCrossCodeTranspiler.CodeLanguage.from(extension: ext)
            let vault = JCrossIRVault() // Temporary memory vault for analysis
            let irGen = JCrossIRGenerator()
            let genResult = irGen.generateIR(from: content, language: language, vault: vault)
            annotatedSource = genResult.annotatedSource
            unobfuscatedIR = genResult.ir
        }

        let prompt = buildPrompt(
            instruction: instruction,
            annotatedSource: annotatedSource,
            unobfuscatedIR: unobfuscatedIR,
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

        return parseOutput(output, originalContent: annotatedSource ?? contextFileContent)
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
            annotatedSource: contextFileContent // Fallback, would ideally use actual annotated source
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
        annotatedSource: String?,
        unobfuscatedIR: JCrossIRDocument?,
        hasTerminal: Bool = false
    ) -> String {
        let codeSection: String
        if let source = annotatedSource, !source.isEmpty {
            codeSection = """
            [CARBON PAPER SOURCE]
            This is the raw source code. It contains `// NODE[0x...]` annotations on structural lines.
            You MUST use these NODE IDs to target your modifications.
            ```
            \(source.prefix(12000))
            ```

            """
        } else {
            codeSection = ""
        }

        let irSection: String
        if let ir = unobfuscatedIR {
            irSection = """
            [UNOBFUSCATED 6-AXIS JCross IR]
            This is the deep structural dependency graph of the file, mapped to the NODE IDs.
            Use this to understand control flow, data flow, and variable types before making changes.
            Nodes count: \(ir.nodes.count)
            Functions count: \(ir.functions.count)

            """
        } else {
            irSection = ""
        }

        let terminalSection = hasTerminal ? """

        TOOL: You can execute shell commands by writing [RUN: command] anywhere in your response.
        """ : ""

        return """
        You are Verantyx, an expert AI coding assistant running locally on Apple Silicon.\(terminalSection)

        Your task:
        1. Read the user's instruction carefully.
        2. Analyze the [UNOBFUSCATED 6-AXIS JCross IR] to understand the architecture.
        3. Formulate a GraphPatch targeting specific NODE IDs in the [CARBON PAPER SOURCE].
        4. Output your patch as a JSON object inside a ````json block.
        5. DO NOT output the entire file.

        JSON FORMAT:
        ```json
        {
          "patches": [
            {
              "targetNodeID": "0x123abc...",
              "operation": "replaceNode", // or insertNode, wrapNode, removeNode
              "snippet": "let x = 1\\nlet y = 2" // The exact Swift code to inject, preserving indentation
            }
          ],
          "explanation": "Brief explanation of the changes"
        }
        ```

        \(irSection)\(codeSection)USER INSTRUCTION: \(instruction)

        YOUR RESPONSE:
        """
    }

    // MARK: - Error fix prompt

    private func buildErrorFixPrompt(
        original: String,
        errorOutput: String,
        annotatedSource: String?
    ) -> String {
        let fileSection = annotatedSource.map { "CURRENT CARBON PAPER:\n```\n\($0.prefix(6000))\n```\n" } ?? ""
        return """
        You previously attempted a GraphPatch code change, but the build/test failed.

        YOUR PREVIOUS RESPONSE:
        \(original.prefix(2000))

        BUILD/TEST ERROR:
        ```
        \(errorOutput.prefix(2000))
        ```

        \(fileSection)
        Please fix the error. Output the CORRECTED GraphPatch JSON.
        """
    }

    // MARK: - Output parser

    private func parseOutput(_ raw: String, originalContent: String?) -> AgentResult {
        // 1. Extract [RUN: cmd] tool calls
        let runPattern = #"\\[RUN:\\s*([^\\]]+)\\]"#
        var ranCommands: [String] = []
        if let regex = try? NSRegularExpression(pattern: runPattern) {
            let matches = regex.matches(in: raw, range: NSRange(raw.startIndex..., in: raw))
            ranCommands = matches.compactMap { m in
                Range(m.range(at: 1), in: raw).map { String(raw[$0]).trimmingCharacters(in: .whitespaces) }
            }
        }
        let cleanedRaw = raw.replacingOccurrences(of: runPattern, with: "", options: .regularExpression)

        // 2. Extract JSON GraphPatch block
        let pattern = #"```json\n([\s\S]*?)```"#
        if let regex = try? NSRegularExpression(pattern: pattern),
           let match = regex.firstMatch(in: cleanedRaw, range: NSRange(cleanedRaw.startIndex..., in: cleanedRaw)),
           let range = Range(match.range(at: 1), in: cleanedRaw) {
            
            let jsonString = String(cleanedRaw[range])
            
            struct AgentPatchResponse: Codable {
                struct AgentPatch: Codable {
                    let targetNodeID: String
                    let operation: String
                    let snippet: String
                }
                let patches: [AgentPatch]
                let explanation: String
            }
            
            if let data = jsonString.data(using: .utf8),
               let response = try? JSONDecoder().decode(AgentPatchResponse.self, from: data) {
                
                var patchedContent = originalContent ?? ""
                var diagnostics: [String] = []
                
                // Apply patches sequentially using VaultPatcher Carbon Paper logic
                for patch in response.patches {
                    guard let op = StructuralCommand.Operation(rawValue: patch.operation) else { continue }
                    patchedContent = VaultPatcher.shared.applyCarbonPaperPatch(
                        annotatedSource: patchedContent,
                        targetNodeID: patch.targetNodeID,
                        restoredSnippet: patch.snippet,
                        operation: op,
                        diagnostics: &diagnostics
                    )
                }
                
                return AgentResult(
                    explanation: response.explanation,
                    diff: patchedContent,
                    ranCommands: ranCommands
                )
            }
        }

        // No valid JSON block — conversational answer
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
