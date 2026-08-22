import Foundation

// MARK: - JCrossPatchValidator
//
// Claudeから返ってきたパッチを検証・フィルタリングするモジュール。
//
// 役割:
//   1. JCross Patch形式のパース
//   2. ダミーノードへのパッチを検出・廃棄
//   3. 実ノードへのパッチを構造的に検証
//   4. IDシャッフルの逆変換 (claudeAlias → nodeID)
//   5. 逆変換後のパッチをPolymorphicJCrossTranspilerに渡す準備
//
// セキュリティ:
//   - ダミーノードへのパッチは内容に関わらず全て破棄
//   - hallucinated nodeID（存在しないエイリアス）も破棄
//   - 構造変更の安全性をBonsai-8Bで事前検証

final class JCrossPatchValidator {

    // MARK: - Types

    /// パースされたパッチの単位
    struct ParsedPatch: Identifiable {
        let id: UUID
        let targetAlias: String          // Claudeが変更しようとしたalias
        let resolvedNodeID: String?      // 逆シャッフル後の実nodeID (nilならhallucinated)
        let modificationType: ModificationType
        let oldLine: String?
        let newLine: String?
        let description: String
        var validationResult: ValidationResult
    }

    enum ModificationType: String {
        case replaceLine   = "REPLACE_LINE"
        case insertAfter   = "INSERT_AFTER"
        case deleteLine    = "DELETE_LINE"
        case restructure   = "RESTRUCTURE"
        case unknown       = "UNKNOWN"
    }

    enum ValidationResult {
        case accepted        // 実ノードへの有効なパッチ
        case rejectedDummy   // ダミーノードへのパッチ (廃棄)
        case rejectedHallucinated  // 存在しないエイリアス (廃棄)
        case rejectedMalformed     // フォーマット不正 (廃棄)
        case rejectedDangerous     // 危険な操作 (廃棄)
        case pendingBonsaiReview   // Bonsai-8Bによるレビュー待ち
    }

    /// バリデーション結果のサマリー
    struct ValidationSummary {
        let totalPatches: Int
        let acceptedPatches: [ParsedPatch]
        let rejectedPatches: [ParsedPatch]
        let dummyPatchCount: Int
        let hallucinatedPatchCount: Int
        let acceptanceRate: Double

        var isValid: Bool { !acceptedPatches.isEmpty }
        var hasHallucinations: Bool { hallucinatedPatchCount > 0 }
    }

    // MARK: - Properties

    // 危険なコードパターン (JCross IRに現れてはいけないもの)
    private let dangerousPatterns: [String] = [
        "exec(", "eval(", "system(", "shell_exec",
        "__import__", "subprocess", "os.system",
        "ProcessInfo", "NSTask", "Process(",
        "FileManager.default.removeItem",
        "URLSession.shared.data", // IR内でのネットワーク呼び出し
    ]

    // MARK: - Parse

    /// Claude の出力からJCross Patchブロックを抽出・パース
    func parsePatches(
        from claudeOutput: String,
        session: RoutingSessionLogger.RoutingSession
    ) -> [ParsedPatch] {

        var patches: [ParsedPatch] = []

        // JCROSS_PATCH_BEGIN ... JCROSS_PATCH_END ブロックを抽出
        let pattern = #"---\s*JCROSS_PATCH_BEGIN\s*---([\s\S]*?)---\s*JCROSS_PATCH_END\s*---"#
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return [] }

        let range = NSRange(claudeOutput.startIndex..., in: claudeOutput)
        let matches = regex.matches(in: claudeOutput, range: range)

        for match in matches {
            guard let contentRange = Range(match.range(at: 1), in: claudeOutput) else { continue }
            let blockContent = String(claudeOutput[contentRange])

            // MODIFY_ALIAS ブロックを個別にパース
            let modifyPattern = #"MODIFY_ALIAS\s+(\S+):\s*\n([\s\S]*?)(?=MODIFY_ALIAS|\z)"#
            guard let modRegex = try? NSRegularExpression(pattern: modifyPattern) else { continue }

            let blockRange = NSRange(blockContent.startIndex..., in: blockContent)
            let modMatches = modRegex.matches(in: blockContent, range: blockRange)

            for mod in modMatches {
                guard let aliasRange = Range(mod.range(at: 1), in: blockContent),
                      let bodyRange  = Range(mod.range(at: 2), in: blockContent)
                else { continue }

                let alias = String(blockContent[aliasRange]).trimmingCharacters(in: .whitespaces)
                let body  = String(blockContent[bodyRange])

                let patch = parseSingleModification(
                    alias: alias,
                    body: body,
                    session: session
                )
                patches.append(patch)
            }
        }

        // フォールバック: 旧来のdiff形式も試行
        if patches.isEmpty {
            patches = parseLegacyDiffFormat(from: claudeOutput, session: session)
        }

        return patches
    }

    private func parseSingleModification(
        alias: String,
        body: String,
        session: RoutingSessionLogger.RoutingSession
    ) -> ParsedPatch {
        let lines = body.components(separatedBy: "\n")
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }

        var description = ""
        var oldLine: String?
        var newLine: String?
        var modType: ModificationType = .unknown

        for line in lines {
            if line.hasPrefix("REPLACE_LINE:") {
                modType = .replaceLine
                oldLine = String(line.dropFirst("REPLACE_LINE:".count)).trimmingCharacters(in: .whitespaces)
            } else if line.hasPrefix("WITH_LINE:") {
                newLine = String(line.dropFirst("WITH_LINE:".count)).trimmingCharacters(in: .whitespaces)
            } else if line.hasPrefix("INSERT_AFTER:") {
                modType = .insertAfter
                oldLine = String(line.dropFirst("INSERT_AFTER:".count)).trimmingCharacters(in: .whitespaces)
            } else if line.hasPrefix("DELETE_LINE:") {
                modType = .deleteLine
                oldLine = String(line.dropFirst("DELETE_LINE:".count)).trimmingCharacters(in: .whitespaces)
            } else if !line.hasPrefix("//") {
                description = line
            }
        }

        // 逆シャッフル: claudeAlias → nodeID
        let resolvedNodeID = session.fragmentOrder
            .first { $0.claudeAlias == alias }?
            .nodeID

        return ParsedPatch(
            id: UUID(),
            targetAlias: alias,
            resolvedNodeID: resolvedNodeID,
            modificationType: modType,
            oldLine: oldLine,
            newLine: newLine,
            description: description,
            validationResult: .pendingBonsaiReview
        )
    }

    /// レガシーなdiff形式のフォールバックパーサー
    private func parseLegacyDiffFormat(
        from output: String,
        session: RoutingSessionLogger.RoutingSession
    ) -> [ParsedPatch] {
        // `` ```jcross ... ``` `` 形式
        let pattern = #"```jcross path:([^\n]+)\n([\s\S]*?)```"#
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return [] }

        let range = NSRange(output.startIndex..., in: output)
        let matches = regex.matches(in: output, range: range)

        return matches.compactMap { match -> ParsedPatch? in
            guard let aliasRange   = Range(match.range(at: 1), in: output),
                  let contentRange = Range(match.range(at: 2), in: output)
            else { return nil }

            let alias   = String(output[aliasRange]).trimmingCharacters(in: .whitespaces)
            let content = String(output[contentRange])

            let resolvedNodeID = session.fragmentOrder
                .first { $0.claudeAlias == alias }?.nodeID

            return ParsedPatch(
                id: UUID(),
                targetAlias: alias,
                resolvedNodeID: resolvedNodeID,
                modificationType: .restructure,
                oldLine: nil,
                newLine: content,
                description: "Legacy diff format",
                validationResult: .pendingBonsaiReview
            )
        }
    }

    // MARK: - Validate

    /// パースされたパッチを検証し、ValidationSummaryを返す
    func validate(
        patches: [ParsedPatch],
        session: RoutingSessionLogger.RoutingSession
    ) -> ValidationSummary {
        let realAliases  = session.realNodeAliases
        let dummyAliases = session.dummyNodeAliases

        var validatedPatches: [ParsedPatch] = []
        var dummyCount = 0
        var hallucinatedCount = 0

        for var patch in patches {
            // 1. ダミーノードへのパッチを廃棄
            if dummyAliases.contains(patch.targetAlias) {
                patch.validationResult = .rejectedDummy
                dummyCount += 1
                validatedPatches.append(patch)
                continue
            }

            // 2. Hallucinated alias (存在しないエイリアス) を廃棄
            if !realAliases.contains(patch.targetAlias) && !dummyAliases.contains(patch.targetAlias) {
                patch.validationResult = .rejectedHallucinated
                hallucinatedCount += 1
                validatedPatches.append(patch)
                continue
            }

            // 3. フォーマット不正チェック
            if patch.modificationType == .unknown && patch.newLine == nil {
                patch.validationResult = .rejectedMalformed
                validatedPatches.append(patch)
                continue
            }

            // 4. 危険パターンチェック
            let contentToCheck = [patch.newLine, patch.oldLine, patch.description]
                .compactMap { $0 }.joined(separator: " ")
            if containsDangerousPattern(contentToCheck) {
                patch.validationResult = .rejectedDangerous
                validatedPatches.append(patch)
                continue
            }

            // 5. 実ノードへの有効なパッチ → 承認
            patch.validationResult = .accepted
            validatedPatches.append(patch)
        }

        let accepted = validatedPatches.filter { $0.validationResult == .accepted }
        let rejected = validatedPatches.filter { $0.validationResult != .accepted }
        let total = validatedPatches.count

        return ValidationSummary(
            totalPatches: total,
            acceptedPatches: accepted,
            rejectedPatches: rejected,
            dummyPatchCount: dummyCount,
            hallucinatedPatchCount: hallucinatedCount,
            acceptanceRate: total > 0 ? Double(accepted.count) / Double(total) : 0
        )
    }

    // MARK: - Apply Reverse Shuffle

    /// 承認済みパッチにIDシャッフル逆変換を適用
    /// claudeAlias → nodeID に変換されたパッチ内容を返す
    func applyReverseShuffleMap(
        to summary: ValidationSummary,
        reverseMap: [String: String]  // claudeAlias → originalNodeID
    ) -> [(nodeID: String, modification: String)] {

        return summary.acceptedPatches.compactMap { patch in
            guard let nodeID = patch.resolvedNodeID ?? reverseMap[patch.targetAlias] else { return nil }

            var modification = ""
            switch patch.modificationType {
            case .replaceLine:
                modification = """
                REPLACE:
                  OLD: \(patch.oldLine ?? "")
                  NEW: \(patch.newLine ?? "")
                """
            case .insertAfter:
                modification = """
                INSERT_AFTER: \(patch.oldLine ?? "")
                  CONTENT: \(patch.newLine ?? "")
                """
            case .deleteLine:
                modification = "DELETE: \(patch.oldLine ?? "")"
            case .restructure:
                modification = patch.newLine ?? ""
            case .unknown:
                modification = patch.description
            }

            return (nodeID: nodeID, modification: modification)
        }
    }

    // MARK: - Bonsai-8B Pre-Validation Report

    /// Bonsai-8Bに渡すバリデーションレポートを生成
    /// Bonsai-8Bはこれを読んでコンテキストバジェット内で安全性を確認する
    func buildBonsaiValidationPrompt(
        summary: ValidationSummary,
        session: RoutingSessionLogger.RoutingSession
    ) -> String {
        let acceptedList = summary.acceptedPatches.map { p in
            "  - alias:\(p.targetAlias) node:\(p.resolvedNodeID ?? "?") type:\(p.modificationType.rawValue)"
        }.joined(separator: "\n")

        let rejectedList = summary.rejectedPatches.map { p in
            "  - alias:\(p.targetAlias) reason:\(p.validationResult)"
        }.joined(separator: "\n")

        return """
        BONSAI VALIDATION REQUEST
        Session: \(session.sessionID)
        File: \(session.sourceRelativePath)
        Schema: \(session.schemaSessionID.prefix(8))

        ACCEPTED PATCHES (\(summary.acceptedPatches.count)):
        \(acceptedList.isEmpty ? "  (none)" : acceptedList)

        REJECTED PATCHES (\(summary.rejectedPatches.count)):
        \(rejectedList.isEmpty ? "  (none)" : rejectedList)

        STATS:
          Total: \(summary.totalPatches)
          Acceptance rate: \(String(format: "%.0f%%", summary.acceptanceRate * 100))
          Dummy patches filtered: \(summary.dummyPatchCount)
          Hallucinated aliases: \(summary.hallucinatedPatchCount)

        QUESTION: Are these accepted patches safe to apply to source? (YES/NO + reason)
        Consider: scope creep, unexpected side effects, logic changes outside requested scope.
        Budget: Keep response under 200 tokens.
        """
    }

    // MARK: - Danger Detection

    private func containsDangerousPattern(_ content: String) -> Bool {
        let lower = content.lowercased()
        return dangerousPatterns.contains { lower.contains($0.lowercased()) }
    }

    // MARK: - Audit Log

    func buildAuditEntry(summary: ValidationSummary, sessionID: String) -> String {
        """
        [PATCH_AUDIT] \(ISO8601DateFormatter().string(from: Date()))
        Session: \(sessionID)
        Total: \(summary.totalPatches) | Accepted: \(summary.acceptedPatches.count) | Rejected: \(summary.rejectedPatches.count)
        Dummies filtered: \(summary.dummyPatchCount) | Hallucinated: \(summary.hallucinatedPatchCount)
        Acceptance rate: \(String(format: "%.1f%%", summary.acceptanceRate * 100))
        """
    }
}
