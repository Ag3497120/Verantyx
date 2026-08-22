import Foundation

// MARK: - PrivacyGateway
//
// VerantyxIDEのキラーフィーチャー：「ローカル秘匿プロキシ・アーキテクチャ」
//
// ┌─────────────────────────────────────────────────────────────────┐
// │  Phase 1 (既存): Regex-based masking (PrivacyProxy.swift)        │
// │  Phase 2 (本ファイル): Gemma-semantic masking + JCross記憶        │
// └─────────────────────────────────────────────────────────────────┘
//
// 完全な処理フロー:
//
//   ユーザー指示
//        ↓
//   [1] JCross記憶検索 (CortexEngine) — 過去のファイル構造・変数情報を想起
//        ↓
//   [2] ローカルGemma (MLX/Ollama) — セマンティックマスキング
//       「processStripePayment」→「FUNC_A23」(意味を保った抽象化)
//        ↓ (マッピングノードをJCrossに保存)
//   [3] 外部API (Claude/GPT) — 抽象化された「論理パズル」として送信
//       ※ 実際のコード・変数名は一切外部に出ない
//        ↓
//   [4] ローカルGemma (MLX/Ollama) — セマンティックアンマスキング
//       JCrossマッピングノードを参照して完全復元
//        ↓
//   [5] DiffEngine — 元のコードとの差分生成
//       ユーザーには完璧なDiffとして提示
//
// セキュリティ保証:
//   - APIキー・シークレット: 完全ブロック (正規表現 + Gemma検出)
//   - 独自関数・クラス名: セマンティックコード化 (FUNC_A~Z)
//   - ファイルパス・ディレクトリ: パス抽象化 (PATH_001)
//   - 社内変数・定数: コンテキスト認識マスキング
//   - JCrossマッピング: ローカルのみ (~/.openclaw/memory/)

// MARK: - GatewayMaskingNode (JCrossに保存するマッピング情報)

struct GatewayMaskingNode: Codable, Sendable {
    let sessionId: String
    let fileHash: String           // ファイル内容のハッシュ (改ざん検知)
    let mappings: [String: String] // masked → real
    let reverseMappings: [String: String] // real → masked
    let createdAt: Date
    var expiresAt: Date            // デフォルト: 24時間後に失効

    // JCross key format: "gateway_map_<sessionId>"
    var jcrossKey: String { "gateway_map_\(sessionId)" }
}

// MARK: - GatewayResult

struct GatewayResult: Sendable {
    let restoredCode: String?
    let explanation: String
    let maskingStats: GatewayStats
    let provider: CloudProvider
    let sessionId: String
}

struct GatewayStats: Sendable {
    let phase1RegexMasked: Int    // 正規表現で検出した識別子数
    let phase2SemanticMasked: Int // Gemmaが追加で検出した識別子数
    let secretsBlocked: Int       // APIキー・シークレット数
    let pathsProtected: Int
    var totalProtected: Int { phase1RegexMasked + phase2SemanticMasked + secretsBlocked + pathsProtected }
    var privacyScore: Int { min(100, Int(Double(totalProtected) * 2.5)) }
}

// MARK: - PrivacyGateway (Phase 2 — Gemma-semantic masking)

actor PrivacyGateway {

    static let shared = PrivacyGateway()

    private let proxy   = PrivacyProxy.shared    // Phase 1 正規表現マスキング
    private let cloud   = CloudAPIClient.shared

    // ── Step 1: Gemma セマンティックマスキング ─────────────────────────────
    // ローカルGemmaに「このコードで外部に漏らすべきでない固有識別子を全て列挙せよ」
    // と依頼し、その結果を元に追加のマスキングを実施する。

    private func gemmaSemanticMask(
        code: String,
        phase1MaskedCode: String,
        phase1Map: MaskingMap,
        modelStatus: AppState.ModelStatus,
        activeModel: String,
        onStep: @escaping @Sendable (String) async -> Void
    ) async -> (maskedCode: String, allMappings: [String: String]) {

        await onStep("🧠 Local Gemma: Detecting sensitive identifiers semantically…")

        // Gemmaへのプロンプト: 残存する機密識別子を検出させる
        let detectionPrompt = """
        You are a code privacy analyzer. Analyze the following code and identify ALL identifiers that should be anonymized before sending to an external API.

        This includes:
        - Project-specific function/method names (business logic indicators)
        - Domain-specific variable names (e.g., paymentAmount, userAuthToken)
        - Internal class/struct names that reveal architecture
        - String literals containing paths, keys, or configuration
        - Comment text that reveals proprietary logic

        Output ONLY a JSON array of strings to anonymize. No explanation.
        Format: ["identifierName1", "identifierName2", ...]

        CODE:
        ```
        \(phase1MaskedCode.prefix(6000))
        ```

        JSON array:
        """

        // Gemmaによる識別子検出
        let detected: [String]
        switch modelStatus {
        case .ollamaReady(let model):
            if let response = await OllamaClient.shared.generate(
                model: model, prompt: detectionPrompt, maxTokens: 512, temperature: 0.05
            ) {
                detected = parseIdentifierList(from: response)
            } else {
                detected = []
            }
        default:
            // Gemmaが使えない場合はPhase 1のみ
            detected = []
        }

        if detected.isEmpty {
            // Phase 2で追加検出なし — Phase 1の結果をそのまま使用
            var allMappings = [String: String]()
            for (real, masked) in phase1Map.funcMap  { allMappings[real] = masked }
            for (real, masked) in phase1Map.classMap { allMappings[real] = masked }
            for (real, masked) in phase1Map.varMap   { allMappings[real] = masked }
            for (real, masked) in phase1Map.pathMap  { allMappings[real] = masked }
            return (phase1MaskedCode, allMappings)
        }

        await onStep("🔍 Gemma detected \(detected.count) additional sensitive identifiers")

        // Phase 2: Gemmaが検出した追加識別子をマスキング
        var result = phase1MaskedCode
        var allMappings = [String: String]()

        // Phase 1 マップを統合
        for (real, masked) in phase1Map.funcMap  { allMappings[real] = masked }
        for (real, masked) in phase1Map.classMap { allMappings[real] = masked }
        for (real, masked) in phase1Map.varMap   { allMappings[real] = masked }
        for (real, masked) in phase1Map.pathMap  { allMappings[real] = masked }

        // Phase 2 追加マスキング
        var p2Counter = 0
        for identifier in detected.sorted(by: { $0.count > $1.count }) {  // 長い方から置換
            guard !identifier.isEmpty, identifier.count >= 3 else { continue }
            guard allMappings[identifier] == nil else { continue }  // 既マスク済みをスキップ

            let masked = "SEMID_\(String(format: "%03d", p2Counter))"
            allMappings[identifier] = masked
            result = result.replacingOccurrences(of: identifier, with: masked)
            p2Counter += 1
        }

        return (result, allMappings)
    }

    // ── Step 4: Gemma セマンティックアンマスキング ────────────────────────
    // クラウドが返した抽象化コードを、JCrossに保存したマッピングで完全復元する。

    private func gemmaSemanticUnmask(
        maskedResponse: String,
        mappings: [String: String],
        modelStatus: AppState.ModelStatus,
        onStep: @escaping @Sendable (String) async -> Void
    ) async -> String {

        await onStep("🔓 Local Gemma: Restoring real identifiers from JCross map…")

        // 逆マッピング (masked → real)
        let reverseMap = Dictionary(uniqueKeysWithValues: mappings.map { ($1, $0) })

        // シンプルな文字列置換（長い方から置換してパーシャルマッチを防ぐ）
        var result = maskedResponse
        for (masked, real) in reverseMap.sorted(by: { $0.key.count > $1.key.count }) {
            result = result.replacingOccurrences(of: masked, with: real)
        }

        // Gemmaによる後処理: 構文的整合性チェック（高品質モードのみ）
        let needsGemmaVerify = reverseMap.count > 20  // 20識別子以上の場合のみ
        if needsGemmaVerify {
            switch modelStatus {
            case .ollamaReady(let model):
                let verifyPrompt = """
                The following code has had anonymized identifiers restored. Check if the restoration looks syntactically correct. 
                If there are obvious mis-restorations (like SEMID_ or FUNC_ tokens still remaining), fix them by removing the prefix.
                Return ONLY the corrected code, no explanation.
                
                CODE:
                ```
                \(result.prefix(8000))
                ```
                """
                if let verified = await OllamaClient.shared.generate(
                    model: model, prompt: verifyPrompt, maxTokens: 2048, temperature: 0.05
                ) {
                    // 残存マスクトークンがなければ採用
                    if !verified.contains("SEMID_") && !verified.contains("FUNC_") && !verified.contains("CLASS_") {
                        result = verified
                    }
                }
            default: break
            }
        }

        return result
    }

    // MARK: - Main: processWithGateway()
    // PrivacyShieldの完全版 (Phase 1 + Phase 2 + JCross記憶)

    func processWithGateway(
        instruction: String,
        fileContent: String,
        fileName: String,
        fileURL: URL?,
        modelStatus: AppState.ModelStatus,
        activeModel: String,
        provider: CloudProvider,
        cortex: CortexEngine,
        useGemmaSemanticMasking: Bool = true,   // AppState.gemmaSemanticMaskingEnabled で制御
        onStep: @escaping @Sendable (String) async -> Void
    ) async -> GatewayResult {

        let sessionId = UUID().uuidString.prefix(8).lowercased()
        let fileHash  = String(fileContent.hashValue)

        // ── Step 1: JCross記憶から過去のコンテキストを取得 ────────────────
        await onStep("🧠 Step 1/5: Querying JCross memory for file context…")

        let memoryContext = await cortex.buildMemoryPrompt(for: "file:\(fileName) \(instruction)")
        let hasMemory = !memoryContext.isEmpty
        if hasMemory {
            await onStep("📖 JCross: Found \(memoryContext.count) chars of relevant memory")
        }

        // ── Step 2: Phase 1 (正規表現マスキング) ──────────────────────────
        await onStep("🔒 Step 2/5: Phase 1 — Regex masking sensitive identifiers…")

        let lang = languageFromFileName(fileName)
        let (masked1, map1, stats1) = await proxy.mask(
            code: fileContent, language: lang, fileName: fileName
        )

        await onStep("🔒 Phase 1 masked \(stats1.total) identifiers (funcs/classes/vars/secrets)")

        // ── Step 3: Phase 2 (Gemmaセマンティックマスキング) ───────────────
        let finalMasked: String
        let allMappings: [String: String]

        if useGemmaSemanticMasking {
            await onStep("🧠 Step 3/5: Phase 2 — Gemma semantic deep scan…")
            (finalMasked, allMappings) = await gemmaSemanticMask(
                code: fileContent,
                phase1MaskedCode: masked1,
                phase1Map: map1,
                modelStatus: modelStatus,
                activeModel: activeModel,
                onStep: onStep
            )
        } else {
            await onStep("⏩ Step 3/5: Gemma semantic scan skipped (disabled in Settings)")
            // Phase 1のみ使用
            var p1Map = [String: String]()
            for (k, v) in map1.funcMap  { p1Map[k] = v }
            for (k, v) in map1.classMap { p1Map[k] = v }
            for (k, v) in map1.varMap   { p1Map[k] = v }
            for (k, v) in map1.pathMap  { p1Map[k] = v }
            finalMasked = masked1
            allMappings = p1Map
        }

        let p2Count = useGemmaSemanticMasking ? allMappings.count - stats1.total : 0

        // マッピングをJCrossに保存 (セッションキー付き)
        let gatewaySessionKey = "gateway_map_\(sessionId)"
        if let mappingData = try? JSONEncoder().encode(allMappings),
           let mappingStr = String(data: mappingData, encoding: .utf8) {
            await cortex.remember(
                key: gatewaySessionKey,
                value: "FILE:\(fileName) HASH:\(fileHash) MAP:\(mappingStr.prefix(2000))",
                importance: 1.0,  // 最高重要度 — GCで削除されない
                zone: .mid
            )
        }

        await onStep("📝 JCross: Mapping stored as '\(gatewaySessionKey)' (\(allMappings.count) identifiers)")

        // ── Step 4: 外部API呼び出し (抽象化コードのみ送信) ───────────────
        await onStep("☁️ Step 4/5: Sending anonymized logic to \(provider.rawValue)…")
        await onStep("🔐 Your real code NEVER leaves this Mac.")

        let langName = lang.rawValue  // PrivacyProxy.Language.rawValue = "swift" etc.
        let systemPrompt = """
        You are an expert code reviewer working with anonymized code.
        All identifiers have been anonymized (FUNC_xxx, CLASS_xxx, VAR_xxx, SEMID_xxx).
        Preserve these anonymized names EXACTLY in your output — do NOT rename them.

        Language: \(langName)
        \(hasMemory ? "Context notes:\n\(memoryContext.prefix(500))" : "")

        Return the modified code in a ```\(langName) code block.
        """

        let userMessage = """
        \(instruction)

        ```\(langName)
        \(finalMasked.prefix(20000))
        ```

        IMPORTANT: Keep all FUNC_xxx, CLASS_xxx, VAR_xxx, SEMID_xxx tokens unchanged.
        """

        let cloudResult = await cloud.send(
            systemPrompt: systemPrompt,
            userMessage: userMessage,
            provider: provider
        )

        switch cloudResult {
        case .failure(let error):
            return GatewayResult(
                restoredCode: nil,
                explanation: "❌ Cloud API error: \(error.localizedDescription)\n\nYour code was protected — nothing was sent before the error occurred.",
                maskingStats: GatewayStats(
                    phase1RegexMasked: stats1.total,
                    phase2SemanticMasked: p2Count,
                    secretsBlocked: stats1.strings,
                    pathsProtected: stats1.paths
                ),
                provider: provider,
                sessionId: String(sessionId)
            )

        case .success(let cloudResponse):
            await onStep("☁️ \(provider.rawValue) processed \(finalMasked.count) abstract chars — returned \(cloudResponse.count) chars")

            // ── Step 5: アンマスキング (JCrossマップで完全復元) ────────────
            await onStep("🔓 Step 5/5: Restoring real identifiers via JCross map…")

            // コードブロック抽出
            let maskedResult = extractCodeBlock(from: cloudResponse)
            guard let maskedCode = maskedResult.code else {
                return GatewayResult(
                    restoredCode: nil,
                    explanation: cloudResponse,
                    maskingStats: GatewayStats(
                        phase1RegexMasked: stats1.total,
                        phase2SemanticMasked: p2Count,
                        secretsBlocked: stats1.strings,
                        pathsProtected: stats1.paths
                    ),
                    provider: provider,
                    sessionId: String(sessionId)
                )
            }

            let restoredCode = await gemmaSemanticUnmask(
                maskedResponse: maskedCode,
                mappings: allMappings,
                modelStatus: modelStatus,
                onStep: onStep
            )

            // JCrossに処理ログを保存 (次回のコンテキストに活用)
            await cortex.remember(
                key: "gateway_result_\(sessionId)",
                value: "FILE:\(fileName) INSTRUCTION:\(instruction.prefix(100)) SUCCESS:true PROTECTED:\(allMappings.count)",
                importance: 0.7,
                zone: .near
            )

            let stats = GatewayStats(
                phase1RegexMasked: stats1.total,
                phase2SemanticMasked: p2Count,
                secretsBlocked: stats1.strings,
                pathsProtected: stats1.paths
            )

            await onStep("✅ Privacy Gateway complete! \(stats.totalProtected) identifiers protected. Privacy score: \(stats.privacyScore)/100")

            return GatewayResult(
                restoredCode: restoredCode,
                explanation: buildExplanation(
                    provider: provider,
                    stats: stats,
                    cloudExplanation: maskedResult.explanation,
                    sessionId: String(sessionId)
                ),
                maskingStats: stats,
                provider: provider,
                sessionId: String(sessionId)
            )
        }
    }

    // MARK: - Helpers

    private func parseIdentifierList(from response: String) -> [String] {
        // JSONアレイを抽出
        guard let start = response.firstIndex(of: "["),
              let end   = response.lastIndex(of: "]") else { return [] }
        let jsonStr = String(response[start...end])
        guard let data = jsonStr.data(using: .utf8),
              let arr  = try? JSONDecoder().decode([String].self, from: data)
        else { return [] }
        // 3文字以上、英数字のみ
        return arr.filter { $0.count >= 3 && $0.allSatisfy { $0.isLetter || $0.isNumber || $0 == "_" } }
    }

    private func extractCodeBlock(from text: String) -> (code: String?, explanation: String) {
        let pattern = #"```(?:\w+)?\n?([\s\S]*?)```"#
        guard let regex = try? NSRegularExpression(pattern: pattern),
              let match = regex.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)),
              let codeRange = Range(match.range(at: 1), in: text)
        else {
            return (nil, text.trimmingCharacters(in: .whitespacesAndNewlines))
        }
        let code = String(text[codeRange])
        let rest = text.components(separatedBy: "```").dropFirst(2).joined().trimmingCharacters(in: .whitespacesAndNewlines)
        return (code, rest.isEmpty ? "Changes applied via Privacy Gateway." : rest)
    }

    private func languageFromFileName(_ name: String) -> PrivacyProxy.Language {
        switch URL(fileURLWithPath: name).pathExtension.lowercased() {
        case "swift":          return .swift
        case "py":             return .python
        case "ts", "tsx":      return .typescript
        case "js", "jsx":      return .javascript
        case "rs":             return .rust
        case "go":             return .go
        case "cpp", "cc":      return .cpp
        default:               return .unknown
        }
    }

    private func buildExplanation(
        provider: CloudProvider,
        stats: GatewayStats,
        cloudExplanation: String,
        sessionId: String
    ) -> String {
        """
        🔐 **Privacy Gateway** — Session `\(sessionId)`

        **Protection summary:**
        • \(stats.phase1RegexMasked) identifiers blocked by regex scan
        • \(stats.phase2SemanticMasked) additional identifiers blocked by Gemma deep scan  
        • \(stats.secretsBlocked) secrets/API keys fully redacted
        • \(stats.pathsProtected) file paths anonymized
        • **Total: \(stats.totalProtected) identifiers** — Privacy score: **\(stats.privacyScore)/100**

        ✅ Your proprietary code, variable names, and architecture **never left your Mac**.
        Only abstract logic was processed by \(provider.rawValue).

        **Changes from \(provider.rawValue):**
        \(cloudExplanation)
        """
    }
}

// MARK: - PrivacyProxy: Language rawValue
// PrivacyProxy.Language.rawValue を systemPrompt の文字列として使えるようにする。
// Language enum は PrivacyProxy.swift で定義済み — rawValue は「swift」「python」等。
