import Foundation

// MARK: - VaultPatcher
//
// 【役割】Cloud LLMが返してきた「意味なしグラフパッチ」に、
//         ローカルVaultから具体的な変数名・数値を注入し、
//         実際のSwiftコードに復元する。
//
// 処理フロー:
//   Cloud LLM Response (structural patch)
//       ↓ applyPatch()
//   VaultLookup (VAULT:key → actual value)
//       ↓
//   IRDocument (patched)
//       ↓ JCrossCodeTranspiler へ
//   Swift Source Code（完全復元）

// MARK: - Patch Response（Cloud LLMが返すグラフパッチの型）

/// Cloud LLMが返す「意味なし・構造あり」のグラフパッチ。
/// 具体値はすべて VAULT:key 形式のプレースホルダーになっている。
struct GraphPatch: Codable {
    /// どのノードの後に挿入するか
    let afterNodeID: String?
    /// どのノードをラップするか
    let wrapNodeID: String?
    /// 新しい制御フローノードの種類
    let newControlFlow: String        // "CTRL:loop", "CTRL:timeout_wrapper" etc.
    /// パラメータ（VAULT:key形式のプレースホルダー）
    let parameters: [String: String]
    /// 生成されたIRスニペット（Cloud LLMが組んだグラフ断片）
    let irSnippet: String
}

// MARK: - Patch Result

struct PatchResult {
    let success: Bool
    let patchedIR: JCrossIRDocument
    let restoredSwiftCode: String?
    let diagnostics: [String]
}

// MARK: - VaultPatcher（メインAPI）

/// Cloud LLMのグラフパッチにVaultから実値を注入し、Swiftコードに復元する。
final class VaultPatcher {

    static let shared = VaultPatcher()
    private init() {}

    // MARK: - Main API

    /// グラフパッチを受け取り、Vaultから実値を注入してSwiftコードを復元する。
    ///
    /// - Parameters:
    ///   - patch: Cloud LLMが返したグラフパッチ
    ///   - command: 元のStructuralCommand（操作の意図）
    ///   - ir: 元のIRドキュメント
    ///   - vault: ローカルVault（VAULT:key → 実値マッピング）
    ///   - language: ターゲット言語
    /// - Returns: パッチ適用結果（Swiftコード含む）
    func applyPatch(
        patch: GraphPatch,
        command: StructuralCommand,
        ir: JCrossIRDocument,
        vault: JCrossIRVault,
        language: JCrossCodeTranspiler.CodeLanguage = .swift
    ) -> PatchResult {
        var diagnostics: [String] = []
        var patchedIR = ir

        // Step 1: IRにパッチを適用
        let patchedNodes = applyGraphPatch(patch: patch, to: &patchedIR, command: command, diagnostics: &diagnostics)

        if !patchedNodes {
            return PatchResult(
                success: false,
                patchedIR: ir,
                restoredSwiftCode: nil,
                diagnostics: diagnostics + ["[VaultPatcher] IRへのパッチ適用失敗"]
            )
        }

        // Step 2: VAULT:key プレースホルダーを実値に解決
        let resolvedSnippet = resolveVaultPlaceholders(
            irSnippet: patch.irSnippet,
            parameters: patch.parameters,
            vault: vault,
            command: command,
            diagnostics: &diagnostics
        )

        // Step 3: パッチ済みIRをSwiftコードに逆変換
        // （JCrossCodeTranspiler 経由でソースを復元）
        let restoredCode = transpileToSwift(
            patchedIR: patchedIR,
            resolvedSnippet: resolvedSnippet,
            command: command,
            vault: vault
        )

        diagnostics.append("[VaultPatcher] ✅ パッチ適用成功: \(patch.newControlFlow) → \(command.targetNodeID)")

        return PatchResult(
            success: true,
            patchedIR: patchedIR,
            restoredSwiftCode: restoredCode,
            diagnostics: diagnostics
        )
    }

    // MARK: - Step 1: IR へのグラフパッチ適用

    private func applyGraphPatch(
        patch: GraphPatch,
        to ir: inout JCrossIRDocument,
        command: StructuralCommand,
        diagnostics: inout [String]
    ) -> Bool {
        let cfKind = command.controlFlowKind

        switch command.operation {
        case .wrapNode:
            guard let wrapID = patch.wrapNodeID,
                  let existing = ir.nodes.first(where: { $0.key.raw == wrapID })?.value else {
                diagnostics.append("[VaultPatcher] wrapNode: ターゲットノード \(patch.wrapNodeID ?? "nil") が見つかりません")
                return false
            }

            // 新しいラッパーノードを生成
            let wrapperID = IRNodeID()
            let cf = ControlFlowProjection(
                kind: cfKindToIR(cfKind),
                branchCount: cfKind == .loop ? 1 : 2,
                conditionHash: "PATCHED_\(wrapID.prefix(8))",
                conditionArity: 1
            )
            let wrapperNode = JCrossIRNode(
                id: wrapperID,
                nodeKind: .controlBlock,
                controlFlow: cf,
                dataFlow: existing.dataFlow,
                typeConstraints: existing.typeConstraints,
                memoryLifecycle: existing.memoryLifecycle,
                scope: existing.scope
            )
            ir.nodes[wrapperID] = wrapperNode
            diagnostics.append("[VaultPatcher] wrapNode: CTRL:\(cfKind?.rawValue ?? "?") を \(wrapID.prefix(8))... に挿入")
            return true

        case .insertNode:
            let newID = IRNodeID()
            let cf = ControlFlowProjection(
                kind: cfKindToIR(cfKind),
                branchCount: 2,
                conditionHash: "INSERTED_\(newID.raw.suffix(8))",
                conditionArity: 1
            )
            let newNode = JCrossIRNode(
                id: newID,
                nodeKind: .controlBlock,
                controlFlow: cf,
                dataFlow: nil,
                typeConstraints: nil,
                memoryLifecycle: nil,
                scope: nil
            )
            ir.nodes[newID] = newNode
            diagnostics.append("[VaultPatcher] insertNode: CTRL:\(cfKind?.rawValue ?? "?") を新規挿入")
            return true

        case .removeNode:
            if let idStr = patch.afterNodeID {
                if let key = ir.nodes.keys.first(where: { $0.raw == idStr }) {
                    ir.nodes.removeValue(forKey: key)
                    diagnostics.append("[VaultPatcher] removeNode: \(idStr.prefix(8))... を削除")
                    return true
                }
            }
            return false

        default:
            diagnostics.append("[VaultPatcher] 未対応の操作: \(command.operation)")
            return false
        }
    }

    // MARK: - Step 2: VAULT:key プレースホルダーを実値に解決

    private func resolveVaultPlaceholders(
        irSnippet: String,
        parameters: [String: String],
        vault: JCrossIRVault,
        command: StructuralCommand,
        diagnostics: inout [String]
    ) -> String {
        var resolved = irSnippet

        for (paramKey, vaultKey) in parameters {
            let actualValue = resolveVaultKey(vaultKey, vault: vault, command: command)
            resolved = resolved.replacingOccurrences(of: "VAULT:\(paramKey)", with: actualValue)
            resolved = resolved.replacingOccurrences(of: vaultKey, with: actualValue)
            diagnostics.append("[VaultPatcher] \(paramKey): \(vaultKey) → \"\(actualValue)\"")
        }

        // OpaqueParameter の解決
        for (key, opaque) in command.parameters {
            let actual = resolveVaultKey(opaque.placeholder, vault: vault, command: command)
            resolved = resolved.replacingOccurrences(of: opaque.placeholder, with: actual)
            diagnostics.append("[VaultPatcher] opaque[\(key)]: \(opaque.placeholder) → \"\(actual)\"")
        }

        return resolved
    }

    /// VAULT:key を実値に解決する。
    /// Vault内を検索し、なければデフォルト値を返す。
    private func resolveVaultKey(_ key: String, vault: JCrossIRVault, command: StructuralCommand) -> String {
        // デフォルト値マップ（Vaultになければここから）
        let defaults: [String: String] = [
            "VAULT:retry_count_default": "3",
            "VAULT:timeout_default_seconds": "30.0",
            "VAULT:max_retry_delay": "2.0",
        ]

        if let def = defaults[key] { return def }

        // Vaultエントリの具体名を検索
        let entries = vault.allEntries()
        for entry in entries {
            if let mem = entry.memoryConcrete {
                if key.lowercased().contains(mem.variableName.lowercased()) {
                    return mem.variableName
                }
            }
        }
        return key // 解決できなければキーをそのまま返す
    }

    // MARK: - Step 3: Swift コードへの逆変換

    private func transpileToSwift(
        patchedIR: JCrossIRDocument,
        resolvedSnippet: String,
        command: StructuralCommand,
        vault: JCrossIRVault
    ) -> String {
        // 制御フロー種別ごとにSwiftコードテンプレートを生成
        switch command.controlFlowKind {
        case .loop:
            let retryCount = command.parameters["retry_count"]
                .flatMap { resolveVaultKey($0.placeholder, vault: vault, command: command) } ?? "3"
            return """
            var _retryCount = 0
            let _maxRetries = \(retryCount)
            repeat {
                do {
                    \(resolvedSnippet.isEmpty ? "// [PATCHED: 元の処理]" : resolvedSnippet)
                    break
                } catch {
                    _retryCount += 1
                    if _retryCount >= _maxRetries { throw error }
                }
            } while _retryCount < _maxRetries
            """

        case .timeout_wrapper:
            let timeout = command.parameters["timeout_duration"]
                .flatMap { resolveVaultKey($0.placeholder, vault: vault, command: command) } ?? "30.0"
            return """
            try await withThrowingTaskGroup(of: Void.self) { group in
                group.addTask {
                    \(resolvedSnippet.isEmpty ? "// [PATCHED: 元の処理]" : resolvedSnippet)
                }
                group.addTask {
                    try await Task.sleep(nanoseconds: UInt64(\(timeout) * 1_000_000_000))
                    throw CancellationError()
                }
                try await group.next()
                group.cancelAll()
            }
            """

        case .error_boundary:
            return """
            do {
                \(resolvedSnippet.isEmpty ? "// [PATCHED: 元の処理]" : resolvedSnippet)
            } catch {
                // [PATCHED: エラーハンドリング]
                throw error
            }
            """

        default:
            return resolvedSnippet.isEmpty
                ? "// [PATCHED: \(command.controlFlowKind?.rawValue ?? "unknown")]"
                : resolvedSnippet
        }
    }

    // MARK: - Helpers

    private func cfKindToIR(_ kind: StructuralCommand.ControlFlowKind?) -> ControlFlowProjection.FlowKind {
        switch kind {
        case .loop:             return .loop
        case .timeout_wrapper:  return .conditionalBranch
        case .error_boundary:   return .conditionalBranch
        case .condition:        return .conditionalBranch
        case .async_await:      return .asyncAwait
        default:                return .conditionalBranch
        }
    }
}
