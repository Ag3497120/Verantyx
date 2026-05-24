import Foundation

// MARK: - JCross IR Patcher v2.1
//
// LLMからのIRパッチをローカルVaultと組み合わせて
// 元のソースコードへの変更として適用するエンジン。
//
// 「データは残らないが修正はできる」という理想の実装。
//
// フロー:
//   1. ユーザー:「乗数を0.15に変えたい」
//   2. IRPatcher: LLMへ「Node 0x8A1B3C5D の右オペランドを変更」と送信
//      ※ 0.15という値は送信しない（ユーザーの意図だけを構造として表現）
//   3. LLMが返す:
//      IRPatch { targetNode: "0x8A1B3C5D", operation: modifyOperand(right, "CONST_NEW") }
//   4. IRPatcher: Vault から 0x8A1B3C5D の context を取得
//   5. IRPatcher: vault entry の right_operand を 0.15 に更新
//   6. IRPatcher: 更新されたVaultからソースコードを再生成
//      → result = round(price * 0.15, 2)  ← 完全復元

// MARK: - Patch Request (ユーザー → IRPatcher)

/// ユーザーが意図する変更。意味論的な指示。
struct UserPatchIntent {
    enum Intent {
        /// 定数値を変更したい
        case changeConstant(nodeID: IRNodeID, newValue: String)
        /// 関数呼び出しを追加したい
        case addFunctionCall(afterNodeID: IRNodeID, functionName: String)
        /// 制御フローを追加したい（ログ出力、バリデーション等）
        case addControlCheck(afterNodeID: IRNodeID, checkType: CheckType)
        /// ノードを削除したい
        case removeNode(nodeID: IRNodeID)
        /// データフローのオペランドを変更したい
        case rewireDataFlow(nodeID: IRNodeID, position: JCrossIRPatch.PatchOperation.OperandPosition, newValue: String)
    }

    enum CheckType: String {
        case nullCheck, rangeCheck, typeCheck, loggingCall
    }

    let intent: Intent
    let requestedBy: String  // "user", "automated_test"
}

// MARK: - Patch Result

struct IRPatchResult {
    let patch: JCrossIRPatch
    let updatedVaultEntry: VaultEntry?
    let generatedSourceDiff: String?
    let success: Bool
    let errorMessage: String?
}

// MARK: - IRPatcher

/// LLMからのIRパッチとローカルVaultを統合して
/// ソースコードへの変更を完全に復元するエンジン。
@MainActor
final class JCrossIRPatcher: ObservableObject {

    @Published var isPatching = false
    @Published var patchHistory: [IRPatchResult] = []

    private let vault: JCrossIRVault
    private let generator: JCrossIRGenerator

    init(vault: JCrossIRVault) {
        self.vault = vault
        self.generator = JCrossIRGenerator()
    }

    // MARK: - Main API

    /// ユーザーの意図をIRパッチに変換してLLMに送信し、
    /// 返ってきたパッチをVaultに適用する。
    ///
    /// この関数はLLM通信をシミュレートする（実際のLLM呼び出しはワーカー経由）。
    func applyUserIntent(
        _ intent: UserPatchIntent,
        irDocument: JCrossIRDocument
    ) async -> IRPatchResult {
        isPatching = true
        defer { isPatching = false }

        // Step 1: ユーザー意図をIRパッチに変換
        let irPatch = translateIntentToIRPatch(intent, document: irDocument)

        // Step 2: IRパッチをVaultに適用（実値解決を含む）
        let resolvedValues = resolveValues(for: irPatch, intent: intent)

        do {
            let updatedEntry = try vault.applyPatch(irPatch, resolvedValues: resolvedValues)

            // Step 3: 更新されたVaultからdiffを生成
            let diff = generateSourceDiff(for: updatedEntry, patch: irPatch)

            let result = IRPatchResult(
                patch: irPatch,
                updatedVaultEntry: updatedEntry,
                generatedSourceDiff: diff,
                success: true,
                errorMessage: nil
            )
            patchHistory.append(result)
            return result

        } catch {
            let result = IRPatchResult(
                patch: irPatch,
                updatedVaultEntry: nil,
                generatedSourceDiff: nil,
                success: false,
                errorMessage: error.localizedDescription
            )
            patchHistory.append(result)
            return result
        }
    }

    /// LLMからのIRパッチを直接適用する（LLMレスポンスを受け取った場合）
    func applyLLMPatch(
        _ patch: JCrossIRPatch,
        userProvidedValues: [String: String] = [:]  // ユーザーが確認した実値
    ) async -> IRPatchResult {
        isPatching = true
        defer { isPatching = false }

        do {
            let entry = try vault.applyPatch(patch, resolvedValues: userProvidedValues)
            let diff = generateSourceDiff(for: entry, patch: patch)

            return IRPatchResult(
                patch: patch,
                updatedVaultEntry: entry,
                generatedSourceDiff: diff,
                success: true,
                errorMessage: nil
            )
        } catch {
            return IRPatchResult(
                patch: patch,
                updatedVaultEntry: nil,
                generatedSourceDiff: nil,
                success: false,
                errorMessage: error.localizedDescription
            )
        }
    }

    /// 直前のパッチを取り消す
    func undo() async throws {
        try vault.undoLastPatch()
        patchHistory.removeLast()
    }

    // MARK: - LLM Instruction Generation

    /// IRDocumentとユーザーの意図から、LLMへの指示文を生成する。
    /// この指示文には具体的な値（0.15等）を含まない。
    func generateLLMInstruction(for intent: UserPatchIntent, document: JCrossIRDocument) -> String {
        switch intent.intent {
        case .changeConstant(let nodeID, _):
            return """
            Modify IRNode \(nodeID.raw):
            - Locate the node in the provided IR document
            - The right operand of this node needs to be replaced
            - Return an IRPatch with:
              - targetNodeID: "\(nodeID.raw)"
              - operation: modifyOperand(position: right, newConstantPlaceholder: "CONST_UPDATED")
            Do NOT infer or suggest what the new value should be.
            The actual value will be applied locally.
            """

        case .addFunctionCall(let afterID, _):
            return """
            Insert a new function call node after \(afterID.raw):
            - Add a new IRNode of kind: functionCall
            - Connect its input to the output of node \(afterID.raw)
            - Return an IRPatch with:
              - operation: insertNode(kind: functionCall, afterNodeID: "\(afterID.raw)")
            Do NOT include function name or parameters in the patch.
            """

        case .addControlCheck(let afterID, let checkType):
            return """
            Insert a \(checkType.rawValue) node after \(afterID.raw):
            - Add a conditional branch node (kind: controlBlock)
            - Connect to node \(afterID.raw)
            - Return an IRPatch with:
              - operation: insertBranch(afterNodeID: "\(afterID.raw)", branchCount: 2)
            """

        case .removeNode(let nodeID):
            return """
            Remove IRNode \(nodeID.raw):
            - Return: IRPatch { targetNodeID: "\(nodeID.raw)", operation: removeNode }
            """

        case .rewireDataFlow(let nodeID, let position, _):
            return """
            Modify the \(position.rawValue) operand of node \(nodeID.raw).
            Return: IRPatch { targetNodeID: "\(nodeID.raw)", operation: modifyOperand(\(position.rawValue), "CONST_REWIRED") }
            """
        }
    }

    // MARK: - Source Diff Generation

    /// Vault状態の変化からソースコードの差分を生成する
    func generateSourceDiff(for entry: VaultEntry, patch: JCrossIRPatch) -> String {
        var diff = "// === PATCH APPLIED: \(patch.patchID.raw) ===\n"

        if let concrete = entry.dataFlowConcrete {
            if let newRight = concrete.rightOperand {
                diff += "// right_operand changed to: \(newRight)\n"
            }
            if let fn = concrete.functionName {
                diff += "// function: \(fn)\n"
            }
        }

        if let sem = entry.semantics {
            if let varName = sem.variableName {
                diff += "// variable: \(varName)\n"
            }
        }

        // 完全なコードスニペットを再生成
        if let reconstructed = vault.reconstructCodeSnippet(for: entry.nodeID) {
            diff += "// Reconstructed:\n\(reconstructed)\n"
        }

        return diff
    }

    // MARK: - Private Helpers

    private func translateIntentToIRPatch(
        _ intent: UserPatchIntent,
        document: JCrossIRDocument
    ) -> JCrossIRPatch {
        switch intent.intent {
        case .changeConstant(let nodeID, _):
            return JCrossIRPatch(
                patchID: IRNodeID(),
                targetNodeID: nodeID,
                operation: .modifyOperand(position: .right, newConstantPlaceholder: "CONST_UPDATED")
            )
        case .rewireDataFlow(let nodeID, let position, _):
            return JCrossIRPatch(
                patchID: IRNodeID(),
                targetNodeID: nodeID,
                operation: .modifyOperand(position: position, newConstantPlaceholder: "CONST_REWIRED")
            )
        case .removeNode(let nodeID):
            return JCrossIRPatch(
                patchID: IRNodeID(),
                targetNodeID: nodeID,
                operation: .removeNode
            )
        case .addFunctionCall(let afterID, _):
            return JCrossIRPatch(
                patchID: IRNodeID(),
                targetNodeID: afterID,
                operation: .insertNode(kind: .functionCall, afterNodeID: afterID)
            )
        case .addControlCheck(let afterID, _):
            return JCrossIRPatch(
                patchID: IRNodeID(),
                targetNodeID: afterID,
                operation: .insertBranch(afterNodeID: afterID, branchCount: 2)
            )
        }
    }

    /// ユーザー意図から実値を解決する（LLMには渡さない）
    private func resolveValues(
        for patch: JCrossIRPatch,
        intent: UserPatchIntent
    ) -> [String: String] {
        switch intent.intent {
        case .changeConstant(_, let newValue):
            return ["CONST_UPDATED": newValue]
        case .rewireDataFlow(_, _, let newValue):
            return ["CONST_REWIRED": newValue]
        default:
            return [:]
        }
    }
}

// MARK: - Patch Validation

extension JCrossIRPatcher {

    /// IRパッチがVaultと整合性があるか検証する
    func validatePatch(_ patch: JCrossIRPatch, document: JCrossIRDocument) -> ValidationResult {
        // ノードがIRドキュメントに存在するか確認
        guard document.nodes[patch.targetNodeID] != nil else {
            return ValidationResult(
                isValid: false,
                warnings: ["Target node \(patch.targetNodeID.raw) not found in IR document"]
            )
        }

        // Vaultにエントリが存在するか確認
        let vaultEntry = vault.entry(for: patch.targetNodeID)
        var warnings: [String] = []

        if vaultEntry == nil {
            warnings.append("No vault entry for node \(patch.targetNodeID.raw). Patch will create new entry.")
        }

        // 操作の整合性チェック
        switch patch.operation {
        case .modifyOperand:
            if let entry = vaultEntry, entry.dataFlowConcrete == nil {
                warnings.append("Node has no dataflow concrete. This may be a structural-only node.")
            }
        default:
            break
        }

        return ValidationResult(isValid: true, warnings: warnings)
    }

    struct ValidationResult {
        let isValid: Bool
        let warnings: [String]
    }
}
import Foundation

/// JCross Graph Patch Engine
/// Safely merges AST-verified patches from the NPU Gatekeeper into the actual JCross Vault / File System.
@MainActor
public final class JCrossGraphPatchEngine {
    public static let shared = JCrossGraphPatchEngine()
    
    private init() {}
    
    /// Commits an approved patch to the physical file system and requests a JCross Topology re-index.
    public func commit(patch: String, targetFile: String, workspaceURL: URL?) throws {
        guard let workspace = workspaceURL else {
            throw NSError(domain: "JCrossGraphPatchEngine", code: 1, userInfo: [NSLocalizedDescriptionKey: "No active workspace. Cannot commit patch."])
        }
        
        let fileURL = workspace.appendingPathComponent(targetFile)
        
        // 1. Extract raw code from LLM Markdown output
        let cleanCode = extractCode(from: patch)
        
        if cleanCode.isEmpty {
            throw NSError(domain: "JCrossGraphPatchEngine", code: 2, userInfo: [NSLocalizedDescriptionKey: "Extracted code is empty. Aborting commit."])
        }
        
        // 2. Diff Application vs Full Overwrite
        // If the LLM returned a unified diff (--- a/ +++ b/), we would apply it.
        // For E-Cores generating the full file or pure code block, we overwrite safely.
        // In a true 100% production system, we'd use SwiftSyntax to merge the AST node directly.
        // Here we simulate the final file write.
        
        let fileManager = FileManager.default
        if !fileManager.fileExists(atPath: fileURL.path) {
            // Create directory if it doesn't exist
            let dirURL = fileURL.deletingLastPathComponent()
            try fileManager.createDirectory(at: dirURL, withIntermediateDirectories: true, attributes: nil)
        }
        
        // Safety check: Don't overwrite if it looks like a fragmented snippet and the file is large,
        // unless it's a unified diff. We assume the E-core outputted the full file for now based on prompt.
        try cleanCode.write(to: fileURL, atomically: true, encoding: .utf8)
        
        print("✅ [JCross Graph Patch Engine] Successfully committed changes to \(targetFile).")
        
        // 3. Trigger JCross L1-L3 Re-indexing and instant L2.5 update
        Task {
            await L25IndexEngine.shared.updateEntryInstantly(
                for: fileURL,
                workspaceURL: workspace,
                patchContext: "LLM_PATCH"
            )
        }
        // JCrossIRVault.shared.reindex(file: fileURL)
    }
    
    private func extractCode(from raw: String) -> String {
        // Strip out markdown ```swift ... ```
        let pattern = #"```(?:swift)?\n([\s\S]*?)```"#
        if let regex = try? NSRegularExpression(pattern: pattern),
           let match = regex.firstMatch(in: raw, range: NSRange(raw.startIndex..., in: raw)),
           let range = Range(match.range(at: 1), in: raw) {
            return String(raw[range]).trimmingCharacters(in: .whitespacesAndNewlines)
        }
        // Fallback: If no markdown block is present, return the raw text
        return raw.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
