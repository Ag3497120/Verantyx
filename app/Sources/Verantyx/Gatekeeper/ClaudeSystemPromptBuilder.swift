import Foundation

// MARK: - ClaudeSystemPromptBuilder
//
// Claude (外部Worker) へのシステムプロンプトを生成する専用ビルダー。
//
// 設計目的:
//   - JCROSS_PATCH_BEGIN/END フォーマットを絶対に強制する
//   - Claudeがソースコードを推測できないよう、文脈を意図的に制限する
//   - フォーマット違反時の動作を定義する (→ Validatorが廃棄)
//   - 1セッション1タスクの原則を維持する

final class ClaudeSystemPromptBuilder {

    // MARK: - Format Spec Constants

    /// JCross Patch フォーマット仕様 (Version 1.2)
    static let formatVersion = "JCrossPatch/1.2"

    /// Patch ブロックの開始マーカー
    static let patchBegin = "--- JCROSS_PATCH_BEGIN ---"

    /// Patch ブロックの終了マーカー
    static let patchEnd   = "--- JCROSS_PATCH_END ---"

    // MARK: - Prompt Parts

    /// Worker AI の基本アイデンティティ定義
    static let coreIdentity = """
    You are a JCross Worker AI. Your role is EXCLUSIVELY to apply structured \
    code transformations to JCross IR fragments.

    CRITICAL CONSTRAINTS:
    - You ONLY see JCross IR fragments — never actual source code
    - All identifiers (aliases) are session-specific tokens with NO semantic meaning
    - You MUST NOT attempt to reconstruct the original program structure
    - You MUST NOT infer business logic from alias names or patterns
    - You MUST NOT use knowledge from previous sessions
    """

    /// フォーマット仕様ブロック (完全な例付き)
    static let formatSpecification = """
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    OUTPUT FORMAT SPECIFICATION — \(formatVersion)
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    ALL your output MUST be enclosed in patch blocks.
    Text outside patch blocks will be DISCARDED by the validator.

    BLOCK STRUCTURE:
    \(patchBegin)
    MODIFY_ALIAS <ALIAS_TOKEN>:
      // Optional: brief description of change (one line, max 80 chars)
      REPLACE_LINE: <exact line to replace>
      WITH_LINE:    <replacement line>
    \(patchEnd)

    SUPPORTED OPERATIONS:
    ┌─────────────────┬────────────────────────────────────────────┐
    │ REPLACE_LINE    │ Replace exact line content                 │
    │ WITH_LINE       │ New content for replaced line              │
    │ INSERT_AFTER:   │ Insert new line after specified line       │
    │ DELETE_LINE:    │ Remove specified line entirely             │
    └─────────────────┴────────────────────────────────────────────┘

    RULES:
    1. One MODIFY_ALIAS block per alias that requires changes
    2. Multiple operations per MODIFY_ALIAS block are allowed
    3. Alias tokens are CASE-SENSITIVE and must match EXACTLY
    4. Only modify aliases marked [TASK] in the fragment list
    5. Aliases marked [CONTEXT] are reference-only — DO NOT modify

    VALID EXAMPLE:
    \(patchBegin)
    MODIFY_ALIAS XK827:
      // Extract repeated computation into variable
      REPLACE_LINE: result = XK827 * XK827 + XK827 * CONST_A
      WITH_LINE:    xk827sq = XK827 * XK827\n      result = xk827sq + XK827 * CONST_A

    MODIFY_ALIAS MN043:
      // Simplify conditional guard
      REPLACE_LINE: if MN043 != nil && MN043 > 0 {
      WITH_LINE:    if let mn043 = MN043, mn043 > 0 {
    \(patchEnd)

    INVALID (will be rejected):
    ✗ Natural language explanations outside patch blocks
    ✗ ``` code blocks ``` instead of JCROSS_PATCH_BEGIN/END
    ✗ Modifying [CONTEXT] aliases
    ✗ Inventing new alias tokens not present in the input

    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    """

    /// フォーマット違反時の動作説明 (Claudeへの警告)
    static let formatEnforcement = """
    FORMAT ENFORCEMENT NOTICE:
    Your response will be parsed by an automated validator.
    - Output outside \(patchBegin) / \(patchEnd) blocks = silently discarded
    - Malformed MODIFY_ALIAS blocks = rejected with error code MALFORMED_PATCH
    - Modifications to [CONTEXT] aliases = rejected with error code DUMMY_PATCH
    - Unknown alias tokens = rejected with error code HALLUCINATED_ALIAS

    If you have NO changes to make, output exactly:
    \(patchBegin)
    // NO_CHANGES_REQUIRED
    \(patchEnd)
    """

    // MARK: - Main Builder

    /// 完全なシステムプロンプトを生成する
    ///
    /// - Parameters:
    ///   - plan: AdversarialNoiseEngine が生成したフラグメント計画
    ///   - userTask: 開発者の指示 (ソースコードや実ファイル名は含めないこと)
    ///   - sessionInfo: セッション識別情報 (先頭8文字のみ)
    /// - Returns: Claudeへのシステムプロンプト文字列
    func build(
        plan: AdversarialNoiseEngine.FragmentPlan,
        userTask: String,
        sessionInfo: String? = nil
    ) -> String {
        let sessionTag = sessionInfo.map { "Session-Tag: \($0.prefix(8))" } ?? ""
        let taskSection = buildTaskSection(userTask: userTask, plan: plan)
        let fragmentManifest = buildFragmentManifest(plan: plan)
        let constraints = buildSessionConstraints(plan: plan)

        return """
        \(Self.coreIdentity)

        \(Self.formatSpecification)

        \(Self.formatEnforcement)

        ━━━━ TASK DEFINITION ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        \(sessionTag)
        \(taskSection)
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        \(fragmentManifest)

        \(constraints)
        """
    }

    // MARK: - Task Section

    private func buildTaskSection(userTask: String, plan: AdversarialNoiseEngine.FragmentPlan) -> String {
        """
        TRANSFORMATION REQUEST:
        \(userTask)

        Scope: Apply this transformation ONLY to [TASK] aliases listed below.
        Budget: Minimize the number of line-level changes. Prefer surgical edits.
        """
    }

    // MARK: - Fragment Manifest

    private func buildFragmentManifest(plan: AdversarialNoiseEngine.FragmentPlan) -> String {
        let taskAliases = plan.fragments
            .filter { $0.kind == .real }
            .map { "  [TASK]    \($0.claudeAlias)  (role: \($0.role))" }
            .joined(separator: "\n")

        let contextAliases = plan.fragments
            .filter { $0.kind == .dummy }
            .map { "  [CONTEXT] \($0.claudeAlias)  ← DO NOT MODIFY" }
            .joined(separator: "\n")

        return """
        ━━━━ FRAGMENT MANIFEST ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        Total fragments in session: \(plan.fragments.count)
        Task aliases  : \(plan.totalRealCount)
        Context aliases: \(plan.totalDummyCount) (noise/reference only)

        \(taskAliases)
        \(contextAliases.isEmpty ? "" : "\n" + contextAliases)
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        """
    }

    // MARK: - Session Constraints

    private func buildSessionConstraints(plan: AdversarialNoiseEngine.FragmentPlan) -> String {
        """
        SESSION CONSTRAINTS:
        - Do NOT reference any alias outside this manifest
        - Do NOT assume ordering or hierarchy between fragments
        - Do NOT add new identifiers not present in input
        - This session processes \(plan.totalRealCount) task unit(s) only
        - Context budget: Keep total response under 2048 tokens
        """
    }

    // MARK: - Prompt Validation

    /// プロンプトが有効かチェック (テスト用)
    func validatePrompt(_ prompt: String) -> PromptValidationResult {
        var issues: [String] = []

        if !prompt.contains(Self.patchBegin) {
            issues.append("Missing JCROSS_PATCH_BEGIN marker definition")
        }
        if !prompt.contains(Self.patchEnd) {
            issues.append("Missing JCROSS_PATCH_END marker definition")
        }
        if !prompt.contains("MODIFY_ALIAS") {
            issues.append("Missing MODIFY_ALIAS format example")
        }
        if !prompt.contains("[TASK]") {
            issues.append("Missing fragment manifest")
        }
        if prompt.count < 500 {
            issues.append("Prompt too short — likely missing key sections")
        }

        return PromptValidationResult(
            isValid: issues.isEmpty,
            issues: issues,
            characterCount: prompt.count,
            estimatedTokens: prompt.count / 4
        )
    }

    struct PromptValidationResult {
        let isValid: Bool
        let issues: [String]
        let characterCount: Int
        let estimatedTokens: Int
    }
}

// MARK: - AdversarialNoiseEngine Extension

extension AdversarialNoiseEngine {
    /// ClaudeSystemPromptBuilder を使った強制フォーマットプロンプト生成
    func buildFinalizedClaudeSystemPrompt(
        plan: FragmentPlan,
        userTask: String,
        sessionID: String
    ) -> String {
        let builder = ClaudeSystemPromptBuilder()
        let prompt = builder.build(plan: plan, userTask: userTask, sessionInfo: sessionID)

        // バリデーション (開発時アサート)
        let validation = builder.validatePrompt(prompt)
        assert(validation.isValid, "System prompt validation failed: \(validation.issues)")

        return prompt
    }
}
