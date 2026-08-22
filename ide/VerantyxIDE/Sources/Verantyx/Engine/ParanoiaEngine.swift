import Foundation

// MARK: - ParanoiaEngine
//
// Privacy Shield の最強モード。
// 従来の正規表現マスキング（PrivacyProxy）+ Gemmaセマンティックスキャン（PrivacyGateway）に加えて、
// Rustの ronin-extract（tree-sitter AST）で精密なバイトオフセット置換を行う。
//
// パイプライン:
//   [1] ronin-extract (Rust) → シンボルリスト (バイトオフセット付き)
//   [2] Gemma 4 local        → 機密判定 (true/false)
//   [3] ronin-masker (Rust)  → 外科的置換 → (maskedCode, vault)
//   [4] CortexEngine         → vault を JCross に保存
//   [5] Claude API           → 匿名コードで推論
//   [6] CortexEngine         → vault 取り出し → アンマスク → Diff表示

// MARK: - Data Structures

struct ASTSymbol: Codable {
    let name: String
    let kind: String
    let byte_start: Int
    let byte_end: Int
    let line: Int
}

struct ParanoiaVault: Codable {
    /// alias → original  (e.g. "Alpha__1" → "VerantyxCoreAuth")
    let forward: [String: String]
    let aliasCount: Int
    let sessionId: String
    let fileName: String
    let createdAt: Date

    // Unmask a string using the stored vault
    func unmask(_ text: String) -> String {
        var result = text
        // Longest alias first to prevent partial match (Alpha__10 before Alpha__1)
        let sorted = forward.keys.sorted { $0.count > $1.count }
        for alias in sorted {
            guard let original = forward[alias] else { continue }
            result = result.replacingOccurrences(of: alias, with: original)
        }
        return result
    }
}

struct ParanoiaResult {
    let maskedCode: String
    let vault: ParanoiaVault
    let sensitiveCount: Int
    let totalSymbols: Int
}

// MARK: - ParanoiaEngine

@MainActor
final class ParanoiaEngine {

    static let shared = ParanoiaEngine()

    // Path to compiled Rust binaries (built by `cargo build --release`)
    private var binaryDir: URL {
        // Primary: alongside the .app in DerivedData
        if let resDir = Bundle.main.resourceURL {
            let candidate = resDir.appendingPathComponent("ronin-extract")
            if FileManager.default.fileExists(atPath: candidate.path) { return resDir }
        }
        let fallbackPath = AppState.shared?.cortexWorkspacePath ?? AppState.shared?.workspaceURL?.path
        let baseDir: URL
        if let fallback = fallbackPath {
            let wsUrl = URL(fileURLWithPath: fallback)
            baseDir = wsUrl.lastPathComponent == "VerantyxIDE" ? wsUrl.deletingLastPathComponent() : wsUrl
        } else {
            baseDir = URL(fileURLWithPath: "/tmp").appendingPathComponent("verantyx-cli")
        }
        return baseDir.appendingPathComponent("verantyx-browser/target/debug")
    }

    private var extractorBinary: URL { binaryDir.appendingPathComponent("ronin-extract") }
    private var maskerBinary:    URL { binaryDir.appendingPathComponent("ronin-masker") }

    // ─── Log state (observed by ParanoiaModeView) ─────────────────────────────

    @Published private(set) var logLines: [ParanoiaLogLine] = []
    @Published private(set) var isRunning: Bool = false

    // MARK: - Main Entry

    /// Full Paranoia Mode masking pipeline.
    /// Returns nil if critical failure (Rust binaries missing / parse error).
    func mask(
        source: String,
        language: String,              // file extension: "swift", "py", "rs"
        fileName: String,
        modelStatus: AppState.ModelStatus,
        cortex: CortexEngine
    ) async -> ParanoiaResult? {

        isRunning = true
        logLines.removeAll()
        defer { isRunning = false }

        let sessionId = UUID().uuidString.prefix(8).lowercased()

        addLog(.phase, "PARANOIA MODE — session \(sessionId)")
        addLog(.info,  "Target: \(fileName) (\(language))")

        // ── Phase 1: AST Symbol Extraction (Rust) ─────────────────────────────
        addLog(.phase, "PHASE 1 · AST symbol extraction via tree-sitter")
        guard FileManager.default.fileExists(atPath: extractorBinary.path) else {
            addLog(.error, "ronin-extract binary not found at \(extractorBinary.path)")
            addLog(.info,  "Run: cargo build -p ronin-repomap")
            return nil
        }

        guard let rawSymbols = await runExtractor(source: source, language: language) else {
            addLog(.error, "AST extraction failed")
            return nil
        }

        addLog(.success, "Extracted \(rawSymbols.count) symbols from AST")

        // ── Phase 2: Sensitivity Classification (Gemma 4 local) ───────────────
        addLog(.phase, "PHASE 2 · Gemma 4 local sensitivity classification")

        let flagged = await classifyWithGemma(
            symbols: rawSymbols,
            modelStatus: modelStatus
        )

        addLog(.success, "\(flagged.count) sensitive symbols flagged")
        for sym in flagged.prefix(10) {
            addLog(.masked, "🔴 \(sym.name) → alias pending")
        }
        if flagged.count > 10 {
            addLog(.info, "... and \(flagged.count - 10) more")
        }

        // Safe symbols
        let sensitiveNames = Set(flagged.map(\.name))
        let safeCount = rawSymbols.filter { !sensitiveNames.contains($0.name) }.count
        addLog(.safe, "🟢 \(safeCount) symbols classified safe — kept as-is")

        if flagged.isEmpty {
            addLog(.success, "No sensitive symbols detected — code transmitted as-is")
            isRunning = false
            return ParanoiaResult(
                maskedCode: source,
                vault: ParanoiaVault(
                    forward: [:], aliasCount: 0,
                    sessionId: String(sessionId),
                    fileName: fileName, createdAt: Date()
                ),
                sensitiveCount: 0,
                totalSymbols: rawSymbols.count
            )
        }

        // ── Phase 3: Surgical Masking (Rust) ──────────────────────────────────
        addLog(.phase, "PHASE 3 · Surgical byte-offset masking (Rust)")
        guard FileManager.default.fileExists(atPath: maskerBinary.path) else {
            addLog(.error, "ronin-masker binary not found")
            return nil
        }

        guard let maskerOutput = await runMasker(source: source, flagged: flagged) else {
            addLog(.error, "Masking engine failed")
            return nil
        }

        let vault = ParanoiaVault(
            forward: maskerOutput.vault,
            aliasCount: maskerOutput.aliasCount,
            sessionId: String(sessionId),
            fileName: fileName,
            createdAt: Date()
        )

        // Update log with assigned aliases
        for (alias, original) in vault.forward.sorted(by: { $0.value < $1.value }) {
            addLog(.masked, "🔴 \(original) → \(alias)")
        }

        // ── Phase 4: Store Vault in JCross ────────────────────────────────────
        addLog(.phase, "PHASE 4 · Storing translation vault in JCross")
        await storeVault(vault, cortex: cortex)
        addLog(.success, "Vault stored: vault_paranoia_\(sessionId)")

        addLog(.ready, "✅ READY — \(flagged.count) secrets masked · 0 transmitted to cloud")

        return ParanoiaResult(
            maskedCode: maskerOutput.masked,
            vault: vault,
            sensitiveCount: flagged.count,
            totalSymbols: rawSymbols.count
        )
    }

    /// Restore masked Claude response using a stored vault.
    func unmask(claudeResponse: String, sessionId: String, cortex: CortexEngine) async -> String {
        guard let vault = await recoverVault(sessionId: sessionId, cortex: cortex) else {
            return claudeResponse
        }
        let restored = vault.unmask(claudeResponse)
        addLog(.success, "Restored \(vault.aliasCount) aliases from vault_paranoia_\(sessionId)")
        return restored
    }

    // MARK: - Rust Process Bridge

    private struct ExtractorInput: Encodable {
        let source: String
        let language: String
    }

    private struct ExtractorOutput: Decodable {
        let symbols: [ASTSymbol]
        let error: String?
    }

    private func runExtractor(source: String, language: String) async -> [ASTSymbol]? {
        let input = ExtractorInput(source: source, language: language)
        guard let inputData = try? JSONEncoder().encode(input) else { return nil }

        return await Task.detached(priority: .userInitiated) { [extractorBinary] in
            let process = Process()
            process.executableURL = extractorBinary
            let stdin  = Pipe(); let stdout = Pipe()
            process.standardInput  = stdin
            process.standardOutput = stdout
            process.standardError  = FileHandle.nullDevice  // ⚠️ stderr は不要 — 未読パイプの deadlock 防止

            do { try process.run() } catch { return nil }
            stdin.fileHandleForWriting.write(inputData)
            stdin.fileHandleForWriting.closeFile()

            let outData = stdout.fileHandleForReading.readDataToEndOfFile()
            process.waitUntilExit()
            guard let output = try? JSONDecoder().decode(ExtractorOutput.self, from: outData) else {
                return nil
            }
            return output.symbols
        }.value
    }

    // MARK: - Gemma 4 Sensitivity Classification

    private func classifyWithGemma(
        symbols: [ASTSymbol],
        modelStatus: AppState.ModelStatus
    ) async -> [ASTSymbol] {

        // Deduplicate by name for the classification prompt
        var seen = Set<String>()
        let uniqueNames = symbols.compactMap { sym -> String? in
            guard !seen.contains(sym.name) else { return nil }
            seen.insert(sym.name)
            return sym.name
        }

        guard !uniqueNames.isEmpty else { return [] }

        let prompt = """
        You are a code security classifier for enterprise software.
        Given a list of symbol names from a codebase, identify which ones are
        PROPRIETARY or CONFIDENTIAL (company-specific logic, internal API names,
        auth-related names, algorithm names, domain-specific identifiers).

        Return a JSON object where each key is a symbol name and value is true
        (proprietary/sensitive) or false (generic/safe).

        Symbols to classify:
        \(uniqueNames.joined(separator: ", "))

        Respond ONLY with valid JSON. Example:
        {"VerantyxCoreAuth": true, "processPayment": true, "viewDidLoad": false, "index": false}
        """

        let classification: [String: Bool]

        switch modelStatus {
        case .ollamaReady(let model):
            if let response = await OllamaClient.shared.generate(
                model: model, prompt: prompt, maxTokens: 1024, temperature: 0.0
            ) {
                classification = parseClassificationJSON(response)
            } else {
                // Fallback: heuristic classification if Gemma is unavailable
                classification = heuristicClassify(uniqueNames)
            }
        default:
            classification = heuristicClassify(uniqueNames)
        }

        // Filter and return all symbol occurrences for flagged names
        let flaggedNames = Set(classification.filter { $0.value }.map(\.key))
        return symbols.filter { flaggedNames.contains($0.name) }
    }

    private func parseClassificationJSON(_ text: String) -> [String: Bool] {
        guard let start = text.firstIndex(of: "{"),
              let end   = text.lastIndex(of: "}") else { return [:] }
        let jsonStr = String(text[start...end])
        guard let data = jsonStr.data(using: .utf8),
              let dict = try? JSONDecoder().decode([String: Bool].self, from: data)
        else { return [:] }
        return dict
    }

    /// Heuristic fallback: flag names that look project-specific (PascalCase > 8 chars, or camelCase > 12 chars)
    private func heuristicClassify(_ names: [String]) -> [String: Bool] {
        var result = [String: Bool]()
        for name in names {
            let isPascalLong = name.first?.isUppercase == true && name.count > 8
            let isCamelLong  = name.first?.isLowercase == true && name.count > 12
            let hasInternalMarker = ["Auth", "Secret", "Key", "Token", "Internal", "Private",
                                      "Core", "Config", "Engine", "Gateway"].contains(where: name.contains)
            result[name] = isPascalLong || isCamelLong || hasInternalMarker
        }
        return result
    }

    // MARK: - ronin-masker Bridge

    private struct MaskerInput: Encodable {
        let source: String
        let flagged: [FlaggedSym]
        struct FlaggedSym: Encodable {
            let name: String
            let byte_start: Int
            let byte_end: Int
        }
    }

    private struct MaskerOutput: Decodable {
        let masked: String
        let vault: [String: String]   // alias → original
        let alias_count: Int
        let error: String?

        var aliasCount: Int { alias_count }
    }

    private func runMasker(source: String, flagged: [ASTSymbol]) async -> MaskerOutput? {
        let input = MaskerInput(
            source: source,
            flagged: flagged.map {
                MaskerInput.FlaggedSym(name: $0.name, byte_start: $0.byte_start, byte_end: $0.byte_end)
            }
        )
        guard let inputData = try? JSONEncoder().encode(input) else { return nil }

        return await Task.detached(priority: .userInitiated) { [maskerBinary] in
            let process = Process()
            process.executableURL = maskerBinary
            let stdin  = Pipe(); let stdout = Pipe()
            process.standardInput  = stdin
            process.standardOutput = stdout
            process.standardError  = FileHandle.nullDevice  // ⚠️ stderr は不要 — deadlock 防止

            do { try process.run() } catch { return nil }
            stdin.fileHandleForWriting.write(inputData)
            stdin.fileHandleForWriting.closeFile()

            let outData = stdout.fileHandleForReading.readDataToEndOfFile()
            process.waitUntilExit()
            return try? JSONDecoder().decode(MaskerOutput.self, from: outData)
        }.value
    }

    // MARK: - JCross Vault Storage

    private func storeVault(_ vault: ParanoiaVault, cortex: CortexEngine) async {
        guard let encoded = try? JSONEncoder().encode(vault),
              let str = String(data: encoded, encoding: .utf8) else { return }
        let key = "vault_paranoia_\(vault.sessionId)"
        await cortex.remember(key: key, value: str, importance: 1.0, zone: .front)
    }

    private func recoverVault(sessionId: String, cortex: CortexEngine) async -> ParanoiaVault? {
        let key = "vault_paranoia_\(sessionId)"
        let nodes = await cortex.recall(for: key, topK: 1)
        guard let raw = nodes.first?.value,
              let data = raw.data(using: .utf8),
              let vault = try? JSONDecoder().decode(ParanoiaVault.self, from: data)
        else { return nil }
        return vault
    }

    // MARK: - Logging

    enum LogKind { case phase, info, masked, safe, success, error, ready }

    struct ParanoiaLogLine: Identifiable {
        let id = UUID()
        let kind: LogKind
        let text: String
        let timestamp: Date = Date()
    }

    private func addLog(_ kind: LogKind, _ text: String) {
        logLines.append(ParanoiaLogLine(kind: kind, text: text))
    }
}
