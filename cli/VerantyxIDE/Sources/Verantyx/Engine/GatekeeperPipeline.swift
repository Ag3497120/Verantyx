import Foundation

// MARK: - GatekeeperPipelineEvent

enum GatekeeperPipelineEvent: Sendable {
    case started
    case step(GatekeeperPipelineStep, String)
    case promptReady(String)
    case llmResponse(String)
    case patchApplied(PatchResult)
    case completed(String)
    case failed(String)
    case modelWarning(String)          // v2.2: nanoモデル警告
    case memoryRecorded(String)        // v2.2: L1-L3記憶保存通知
}

enum GatekeeperPipelineStep: String, Sendable {
    case modelValidation = "⓪ モデル検証"   // v2.2 追加
    case irGeneration    = "① IR 生成"
    case vaultSeparation = "② Vault 分離"
    case intentTranslate = "③ 意図翻訳"
    case promptBuild     = "④ プロンプト生成"
    case llmCall         = "⑤ Cloud LLM 呼び出し"
    case patchParse      = "⑥ パッチ解析"
    case vaultRehydrate  = "⑦ Vault 注入・復元"
}

// MARK: - GatekeeperPipeline（メインオーケストレーター v2.2）
//
// v2.2 変更点:
//   - ⓪ モデル検証ステップを追加（nanoモデルをブロック、20B+を強制）
//   - 各ステップ完了後に L1〜L3 全層記憶を GKConversionSessionMemory に保存
//   - ④ プロンプト生成時に L1〜L3 記憶をコンテキスト代替として注入
//   - セッション記憶を GKSessionStore で永続化（再起動後も継続可能）
//
// 処理フロー v2.2:
//   ⓪ モデル検証 (20B+強制)
//       ↓ [L1-L3 記録: セッション開始]
//   ① JCrossIRGenerator  Source → 6軸IR + Vault分離
//       ↓ [L1-L3 記録: IRノード数・Vault分離数]
//   ② BitNetIntentTranslator  指示 → StructuralCommand
//       ↓ [L1-L3 記録: 翻訳されたコマンド]
//   ③ GatekeeperPromptBuilder + L1〜L3注入  → Cloud LLMプロンプト
//       ↓
//   ④ GatekeeperUniversalLLMClient  Cloud LLM呼び出し
//       ↓ [L1-L3 記録: LLM応答要約]
//   ⑤ GraphPatch JSONパース
//       ↓ [L1-L3 記録: パッチ内容]
//   ⑥ VaultPatcher  パッチ + Vault実値 → コード復元
//       ↓ [L1-L3 記録: 復元結果 + 型マッピング確定]

final class GatekeeperPipeline: Sendable {

    static let shared = GatekeeperPipeline()
    private init() {}

    // MARK: - Main Entry Point

    func run(
        userInstruction: String,
        sourceCode: String,
        language: JCrossCodeTranspiler.CodeLanguage = .swift,
        config: GatekeeperConfig,
        sessionMemory: GKConversionSessionMemory? = nil,   // v2.2: セッション記憶
        onEvent: @Sendable @escaping (GatekeeperPipelineEvent) async -> Void
    ) async {
        await onEvent(.started)

        // ── ⓪ モデル検証（20B+強制） ───────────────────────────────────────
        await onEvent(.step(.modelValidation, "Gatekeeperモード: モデル検証中…"))

        let modelValidation = GKModelGuard.validate(
            model: config.cloudModel,
            provider: config.cloudProvider
        )

        let effectiveConfig: GatekeeperConfig
        switch modelValidation {
        case .rejected(let reason, let fallback):
            await onEvent(.modelWarning("⚠️ \(reason)\n→ フォールバック: \(fallback) で実行します"))
            // フォールバックモデルで継続
            var fallbackConfig = config
            fallbackConfig.cloudModel = fallback
            effectiveConfig = fallbackConfig
        case .warning(_, let msg):
            await onEvent(.modelWarning("⚠️ \(msg)"))
            effectiveConfig = config
        case .approved:
            effectiveConfig = config
        }

        await onEvent(.step(.modelValidation,
            "✅ モデル: \(effectiveConfig.cloudModel) (\(effectiveConfig.cloudProvider.rawValue)) — L2/L3記憶対応"))

        // セッション記憶を初期化（既存セッションがあれば再利用）
        let memory: GKConversionSessionMemory = sessionMemory ?? GKConversionSessionMemory(
            userInstruction: userInstruction,
            sourceLang: language.rawValue,
            targetLang: extractTargetLang(from: userInstruction)
        )

        // ── ① IR生成 + Vault分離 ──────────────────────────────────────────
        await onEvent(.step(.irGeneration, "ソースコードを6軸IRに変換 + 具体値をVaultへ分離中…"))

        let vault = JCrossIRVault()
        let irGenerator = JCrossIRGenerator()
        let ir = irGenerator.generateIR(from: sourceCode, language: language, vault: vault)

        let nodeCount  = ir.nodes.count
        let vaultCount = vault.allEntries().count

        // L1-L3 記録: ① IR生成
        await memory.recordStep(
            step: .irGeneration,
            l1Tags: "[迅IR生:0.9] [ノード\(nodeCount):0.8]",
            l1Summary: "\(language.rawValue)ソースを\(nodeCount)ノードのIRに変換、\(vaultCount)エントリをVaultに分離",
            l2Operations: [
                "OP.FACT(\"node_count\", \"\(nodeCount)\")",
                "OP.FACT(\"vault_entries\", \"\(vaultCount)\")",
                "OP.FACT(\"source_lang\", \"\(language.rawValue)\")",
                "OP.STATE(\"ir_generation\", \"completed\")",
            ],
            l3Before: sourceCode.prefix(1000).description,
            l3After: "IR: \(nodeCount) nodes generated (opaque v2.2)"
        )
        await onEvent(.memoryRecorded("L1-L3 記録: IR生成完了"))
        await onEvent(.step(.vaultSeparation,
            "IR生成完了: \(nodeCount)ノード / Vault: \(vaultCount)エントリ（意味軸を分離）"))

        // ── ② 意図翻訳 ────────────────────────────────────────────────────
        await onEvent(.step(.intentTranslate, "意図翻訳中: 「\(userInstruction.prefix(40))…」"))

        let command = await GatekeeperIntentClient.shared.translate(
            userInstruction: userInstruction,
            vault: vault,
            ir: ir,
            config: effectiveConfig
        )

        // L1-L3 記録: ② 意図翻訳
        await memory.recordStep(
            step: .intentTranslate,
            l1Tags: "[意翻:\(command.operation.rawValue):0.9]",
            l1Summary: "意図翻訳: \(command.operation.rawValue) → NODE[\(command.targetNodeID.prefix(8))]",
            l2Operations: [
                "OP.FACT(\"intent_operation\", \"\(command.operation.rawValue)\")",
                "OP.FACT(\"target_node\", \"\(command.targetNodeID.prefix(8))\")",
                "OP.FACT(\"domain_category\", \"\(command.domainCategory.rawValue)\")",
                "OP.STATE(\"intent_translation\", \"completed\")",
            ],
            l3Before: userInstruction,
            l3After: "StructuralCommand: \(command.operation.rawValue) on \(command.targetNodeID.prefix(8))"
        )
        await onEvent(.memoryRecorded("L1-L3 記録: 意図翻訳完了"))
        await onEvent(.step(.intentTranslate,
            "翻訳完了: \(command.operation.rawValue) → NODE[\(command.targetNodeID.prefix(8))](\(command.domainCategory.rawValue.uppercased()))"))

        // ── ③ プロンプト生成（L1〜L3 コンテキスト注入） ────────────────────
        await onEvent(.step(.promptBuild, "Gatekeeperプロンプトを構築中（L1〜L3記憶を注入）…"))

        // L1〜L3 記憶をコンテキスト代替として注入
        let memoryContext = await memory.buildContextInjection()

        let basePrompt = GatekeeperPromptBuilder.shared.buildPrompt(
            ir: ir, command: command, vault: vault
        )

        // L1〜L3 記憶ブロックをプロンプトの先頭に注入
        let fullPrompt = """
        \(memoryContext)

        // ─── 以下: 現在のステップのタスク ───────────────────────────────

        \(basePrompt)
        """

        await onEvent(.promptReady(fullPrompt))
        await onEvent(.step(.promptBuild,
            "プロンプト準備完了: \(fullPrompt.count)文字（L1〜L3記憶注入済み・意味ゼロ・構造フル）"))

        // ── ④ Cloud LLM 呼び出し ──────────────────────────────────────────
        let providerLabel = effectiveConfig.cloudProvider.rawValue
        let modelLabel    = effectiveConfig.cloudModel
        await onEvent(.step(.llmCall, "\(providerLabel) / \(modelLabel) に構造パズルを送信中…"))

        guard let rawResponse = await GatekeeperUniversalLLMClient.shared.complete(
            prompt: fullPrompt, config: effectiveConfig
        ) else {
            await onEvent(.failed("Cloud LLM からの応答が取得できませんでした。APIキーと設定を確認してください。"))
            return
        }

        // L1-L3 記録: ④ LLM応答
        await memory.recordStep(
            step: .llmCall,
            l1Tags: "[LLM応:\(modelLabel.prefix(10)):0.8]",
            l1Summary: "Cloud LLM応答受信: \(rawResponse.count)文字",
            l2Operations: [
                "OP.FACT(\"llm_model\", \"\(modelLabel)\")",
                "OP.FACT(\"response_chars\", \"\(rawResponse.count)\")",
                "OP.STATE(\"llm_call\", \"completed\")",
            ],
            l3Before: "Prompt: \(fullPrompt.prefix(300))...",
            l3After: rawResponse.prefix(500).description
        )
        await onEvent(.memoryRecorded("L1-L3 記録: LLM応答"))
        await onEvent(.llmResponse(rawResponse))
        await onEvent(.step(.llmCall, "Cloud LLM 応答受信: \(rawResponse.count)文字"))

        // ── ⑤ GraphPatch JSON解析 ──────────────────────────────────────────
        await onEvent(.step(.patchParse, "Cloud LLMの応答からGraphPatch JSONを抽出中…"))

        guard let patch = parseGraphPatch(from: rawResponse) else {
            await onEvent(.step(.patchParse, "⚠️ GraphPatch JSONではなくテキスト応答を検出。Vault注入を試みます。"))
            let rehydrated = rehydrateTextResponse(rawResponse, vault: vault, memory: memory)
            // L1-L3 記録: テキスト応答パス
            await memory.recordStep(
                step: .patchParse,
                l1Tags: "[テキスト応:0.7]",
                l1Summary: "GraphPatch JSONなし → テキスト応答をVault注入で補完",
                l2Operations: ["OP.STATE(\"patch_parse\", \"text_fallback\")"],
                l3Before: rawResponse.prefix(300).description,
                l3After: rehydrated.prefix(300).description
            )
            await onEvent(.memoryRecorded("L1-L3 記録: テキスト応答パス"))
            await onEvent(.completed(rehydrated))
            await GKSessionStore.shared.save(session: memory)
            return
        }

        // L1-L3 記録: ⑤ パッチ解析成功
        await memory.recordStep(
            step: .patchParse,
            l1Tags: "[グラフ解析:0.9]",
            l1Summary: "GraphPatch解析成功: \(patch.newControlFlow)",
            l2Operations: [
                "OP.FACT(\"patch_control_flow\", \"\(patch.newControlFlow)\")",
                "OP.FACT(\"patch_target\", \"\(patch.wrapNodeID ?? patch.afterNodeID ?? "unknown")\")",
                "OP.STATE(\"patch_parse\", \"success\")",
            ],
            l3Before: rawResponse.prefix(300).description,
            l3After: "GraphPatch: \(patch.newControlFlow)"
        )
        await onEvent(.memoryRecorded("L1-L3 記録: パッチ解析"))
        await onEvent(.step(.patchParse, "GraphPatch解析成功: \(patch.newControlFlow)"))

        // ── ⑥ Vault注入・コード復元 ──────────────────────────────────────
        await onEvent(.step(.vaultRehydrate, "Vaultから実値を注入してコードを復元中…"))

        let patchResult = VaultPatcher.shared.applyPatch(
            patch: patch,
            command: command,
            ir: ir,
            vault: vault,
            language: language
        )

        await onEvent(.patchApplied(patchResult))

        if patchResult.success, let code = patchResult.restoredSwiftCode {
            let diagnosticsSummary = patchResult.diagnostics.joined(separator: "\n")

            // 型マッピングをセッション記憶に登録（次ファイルで一貫使用）
            await registerTypeMappingsFromCode(code, into: memory)

            // L1-L3 記録: ⑦ 復元完了
            await memory.recordStep(
                step: .vaultRehydrate,
                l1Tags: "[復元完:0.9] [コード\(code.count)字:0.8]",
                l1Summary: "Vault注入・コード復元完了: \(code.count)文字",
                l2Operations: [
                    "OP.FACT(\"output_chars\", \"\(code.count)\")",
                    "OP.STATE(\"vault_rehydrate\", \"success\")",
                    "OP.FACT(\"diagnostics\", \"\(patchResult.diagnostics.count)件\")",
                ],
                l3Before: "Patch: \(patch.newControlFlow)",
                l3After: code.prefix(500).description
            )
            await onEvent(.memoryRecorded("L1-L3 記録: コード復元完了"))
            await onEvent(.step(.vaultRehydrate, "復元完了:\n\(diagnosticsSummary)"))
            await onEvent(.completed(code))

            // セッションを永続化（次回再起動で継続可能）
            await memory.incrementConverted()
            await GKSessionStore.shared.save(session: memory)

        } else {
            await onEvent(.failed("Vault注入に失敗しました: \(patchResult.diagnostics.joined(separator: ", "))"))
        }
    }

    // MARK: - Target Language Detection

    private func extractTargetLang(from instruction: String) -> String {
        let lower = instruction.lowercased()
        if lower.contains("rust") || lower.contains("錆")         { return "rust" }
        if lower.contains("python") || lower.contains("蛇")       { return "python" }
        if lower.contains("typescript") || lower.contains("型")   { return "typescript" }
        if lower.contains("kotlin") || lower.contains("晶")       { return "kotlin" }
        if lower.contains("go") || lower.contains("golang")       { return "go" }
        return "unknown"
    }

    // MARK: - Type Mapping Registration

    /// 生成されたコードから型マッピングを自動検出してセッション記憶に登録する。
    private func registerTypeMappingsFromCode(
        _ code: String, into memory: GKConversionSessionMemory
    ) async {
        // 簡易パターンマッチング（例: "// Swift: Codable → serde::Serialize"）
        let lines = code.components(separatedBy: "\n")
        for line in lines {
            if line.contains("→") && line.contains("//") {
                let parts = line.components(separatedBy: "→")
                if parts.count == 2 {
                    let from = parts[0].trimmingCharacters(in: .whitespaces)
                        .replacingOccurrences(of: "//", with: "")
                        .trimmingCharacters(in: .whitespaces)
                    let to = parts[1].trimmingCharacters(in: .whitespaces)
                    if !from.isEmpty && !to.isEmpty && from.count < 50 && to.count < 50 {
                        await memory.registerTypeMapping(from, to)
                    }
                }
            }
        }
    }

    // MARK: - GraphPatch JSON Parser

    private func parseGraphPatch(from response: String) -> GraphPatch? {
        let cleaned = extractJSON(from: response)
        guard let data = cleaned.data(using: .utf8) else { return nil }

        if let patch = try? JSONDecoder().decode(GraphPatch.self, from: data) {
            return patch
        }

        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return nil
        }

        return GraphPatch(
            afterNodeID:    json["afterNodeID"]    as? String,
            wrapNodeID:     json["wrapNodeID"]     as? String,
            newControlFlow: json["newControlFlow"] as? String ?? "CTRL:unknown",
            parameters:     json["parameters"]     as? [String: String] ?? [:],
            irSnippet:      json["irSnippet"]      as? String ?? ""
        )
    }

    private func extractJSON(from text: String) -> String {
        var t = text
        if let start = t.range(of: "```json"),
           let end = t.range(of: "```", range: start.upperBound..<t.endIndex) {
            t = String(t[start.upperBound..<end.lowerBound])
        } else if let start = t.range(of: "```"),
                  let end = t.range(of: "```", range: start.upperBound..<t.endIndex) {
            t = String(t[start.upperBound..<end.lowerBound])
        }
        if let start = t.firstIndex(of: "{"), let end = t.lastIndex(of: "}") {
            return String(t[start...end])
        }
        return t.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    // MARK: - Text Response Rehydration

    private func rehydrateTextResponse(
        _ response: String,
        vault: JCrossIRVault,
        memory: GKConversionSessionMemory
    ) -> String {
        var result = response

        // NODE[0xXXXX] パターンをVaultから実名に解決
        let entries = vault.allEntries()
        for entry in entries {
            let shortID = String(entry.nodeID.raw.dropFirst(2).prefix(8)).uppercased()
            let longID  = entry.nodeID.raw.uppercased()
            if let name = entry.memoryConcrete?.variableName {
                result = result.replacingOccurrences(of: "NODE[\(shortID)]", with: name)
                result = result.replacingOccurrences(of: "FUNC[\(shortID)]", with: name)
                result = result.replacingOccurrences(of: "NODE[\(longID)]",  with: name)
                result = result.replacingOccurrences(of: "FUNC[\(longID)]",  with: name)
            }
            if let name = entry.memoryConcrete?.variableName {
                result = result.replacingOccurrences(of: "VAULT:\(entry.nodeID.raw)", with: name)
            }
        }
        return result
    }
}

// MARK: - GatekeeperPipelineState（SwiftUI バインディング v2.2）

@MainActor
final class GatekeeperPipelineState: ObservableObject {

    static let shared = GatekeeperPipelineState()
    private init() {}

    @Published var isRunning: Bool = false
    @Published var currentStep: GatekeeperPipelineStep? = nil
    @Published var stepLog: [(step: String, detail: String, timestamp: Date)] = []
    @Published var lastPrompt: String = ""
    @Published var lastLLMResponse: String = ""
    @Published var lastResult: String = ""
    @Published var lastError: String? = nil
    @Published var modelWarning: String? = nil          // v2.2: nanoモデル警告
    @Published var memoryLog: [String] = []             // v2.2: L1-L3記憶ログ
    @Published var config: GatekeeperConfig = GatekeeperConfig.load()

    // v2.2: 変換セッション記憶（ファイル間で共有）
    private var sessionMemory: GKConversionSessionMemory? = nil

    func saveConfig() {
        config.save()
    }

    /// 新しい変換セッションを開始する。
    /// 未完了セッションがあれば再開を提案する。
    func startNewSession(instruction: String, sourceLang: String, targetLang: String) {
        sessionMemory = GKConversionSessionMemory(
            userInstruction: instruction,
            sourceLang: sourceLang,
            targetLang: targetLang
        )
        memoryLog.removeAll()
    }

    func execute(
        userInstruction: String,
        sourceCode: String,
        language: JCrossCodeTranspiler.CodeLanguage = .swift
    ) async {
        isRunning = true
        stepLog.removeAll()
        lastError = nil
        lastResult = ""
        lastPrompt = ""
        lastLLMResponse = ""
        modelWarning = nil

        let capturedConfig  = config
        let capturedSession = sessionMemory

        await GatekeeperPipeline.shared.run(
            userInstruction: userInstruction,
            sourceCode: sourceCode,
            language: language,
            config: capturedConfig,
            sessionMemory: capturedSession
        ) { [weak self] event in
            guard let self else { return }
            await MainActor.run {
                switch event {
                case .started:
                    self.stepLog.append((step: "開始", detail: "Gatekeeperパイプライン v2.2 起動", timestamp: Date()))

                case .step(let step, let detail):
                    self.currentStep = step
                    self.stepLog.append((step: step.rawValue, detail: detail, timestamp: Date()))

                case .promptReady(let prompt):
                    self.lastPrompt = prompt

                case .llmResponse(let resp):
                    self.lastLLMResponse = resp

                case .patchApplied(let result):
                    self.stepLog.append((
                        step: "パッチ適用",
                        detail: result.diagnostics.joined(separator: "\n"),
                        timestamp: Date()
                    ))

                case .completed(let code):
                    self.lastResult = code
                    self.isRunning = false
                    self.currentStep = nil
                    self.stepLog.append((step: "✅ 完了", detail: "\(code.count)文字のコードを生成", timestamp: Date()))

                case .failed(let error):
                    self.lastError = error
                    self.isRunning = false
                    self.currentStep = nil
                    self.stepLog.append((step: "❌ エラー", detail: error, timestamp: Date()))

                case .modelWarning(let warning):
                    self.modelWarning = warning
                    self.stepLog.append((step: "⚠️ モデル警告", detail: warning, timestamp: Date()))

                case .memoryRecorded(let summary):
                    self.memoryLog.append("[\(Date().formatted(.dateTime.hour().minute().second()))] \(summary)")
                    if self.memoryLog.count > 100 { self.memoryLog.removeFirst(20) }
                }
            }
        }
    }
}
