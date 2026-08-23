import Foundation
import CryptoKit

// MARK: - JCross Logic Decomposer (Verantyx-Logic Reinforced)
//
// 従来の Verantyx-Logic (Python) は自然言語の論理式（First-Order / Modal Logic）を
// 文字列ベースで分解していましたが、以下の「弱点（脆弱性）」がありました：
//
// 【特定された弱点】
// 1. 意味論の混入 (Semantic Leakage): "User = admin -> access" のようなドメイン固有の
//    名詞（User, admin 等）が論理演算子 (->, &) と同じレイヤーに平文で存在していた。
// 2. 空間軸の欠落: ControlFlow（論理構造）と Z-Axis（具体値）の分離がなかった。
//
// 【立体十字構造 (6-Axis) による補強】
// 本エンジンは、Verantyx-Logic のルールベース推論を 6-Axis IR に統合します。
// - 命題/原子 (Atoms) -> Z-Axis (Vault) へ暗号化して隔離
// - 論理演算子 (□, ◇, ->, &) -> X-Axis (Control Flow) へ純粋なトポロジーとして抽出
// - ドメイン推論 (Domain) -> メタデータ軸へ隔離

struct LogicSpec {
    let domain: String
    let assumptions: [String]
    let queryType: String
}

final class JCrossLogicDecomposer {
    
    private let vault: JCrossIRVault
    
    init(vault: JCrossIRVault) {
        self.vault = vault
    }
    
    /// 自然言語または論理式を 6軸 JCross IR に変換する（ルールベースの代替エンジン）
    func decompose(logicalText: String) -> (JCrossIRDocument, LogicSpec) {
        let domain = detectDomain(logicalText)
        let assumptions = detectAssumptions(logicalText)
        let queryType = inferQueryType(logicalText)
        
        let spec = LogicSpec(domain: domain, assumptions: assumptions, queryType: queryType)
        var nodes: [IRNodeID: JCrossIRNode] = [:]
        
        // 1. 命題（Atom）の抽出と Z-Axis Vault への隔離（弱点の補強）
        // 例: "A -> B" の A, B を抽出し、IRには抽象IDだけを残す
        let tokens = tokenizeFormula(logicalText)
        
        var currentControlFlowIDs: [IRNodeID] = []
        
        for token in tokens {
            let nodeID = IRNodeID()
            
            if isLogicalOperator(token) {
                // X-Axis (Control Flow): 論理演算子
                let cf = ControlFlowProjection(
                    kind: .conditionalBranch,
                    branchCount: getOperatorArity(token),
                    conditionHash: "0x" + SHA256.hash(data: Data(token.utf8)).map { String(format: "%02x", $0) }.joined().prefix(8),
                    conditionArity: 1
                )
                nodes[nodeID] = JCrossIRNode(id: nodeID, nodeKind: .controlBlock, controlFlow: cf, dataFlow: nil, typeConstraints: nil, memoryLifecycle: nil, scope: nil)
                currentControlFlowIDs.append(nodeID)
            } else {
                // Z-Axis (Semantics): 原子命題（Atom）は Vault に隔離
                nodes[nodeID] = JCrossIRNode(id: nodeID, nodeKind: .variable, controlFlow: nil, dataFlow: nil, typeConstraints: nil, memoryLifecycle: nil, scope: nil)
                
                // Vault への保存（意味論漏洩の防止）
                vault.storeSemantics(
                    nodeID: nodeID,
                    typeConcrete: TypeConcrete(concreteTypeName: "Atom", semanticRole: "LogicalProposition", domain: domain),
                    memoryConcrete: MemoryConcrete(variableName: token, typeName: "Atom", scopeContext: nil, fields: [:])
                )
            }
        }
        
        let document = JCrossIRDocument(
            documentID: IRNodeID(),
            language: "logic",
            protocolVersion: "3.0",
            generatedAt: Date(),
            functions: [],
            nodes: nodes
        )
        
        return (document, spec)
    }
    
    // MARK: - Rule-based Parsers (Ported from decomposer.py)
    
    private func detectDomain(_ text: String) -> String {
        let lower = text.lowercased()
        if lower.contains("∀") || lower.contains("∃") || lower.contains("forall") { return "first_order_logic" }
        if lower.contains("kripke") || lower.contains("□") || lower.contains("◇") || lower.contains("modal") { return "modal_logic" }
        if lower.contains("tautology") || lower.contains("恒真") { return "propositional_logic" }
        return "unknown"
    }
    
    private func detectAssumptions(_ text: String) -> [String] {
        var assumptions: [String] = []
        if text.lowercased().contains("assume") || text.contains("前提") {
            assumptions.append("explicit_assumption")
        }
        return assumptions
    }
    
    private func inferQueryType(_ text: String) -> String {
        let lower = text.lowercased()
        if lower.contains("同値") || lower.contains("equivalent") { return "EQUIVALENCE" }
        if lower.contains("すべて") || lower.contains("all") { return "SET_ALL" }
        if lower.contains("どれか") || lower.contains("any") { return "SET_ANY" }
        return "SINGLE"
    }
    
    private func tokenizeFormula(_ text: String) -> [String] {
        // 簡易トークナイザ: 演算子と変数を分離
        let cleanText = text.replacingOccurrences(of: "→", with: "->")
                           .replacingOccurrences(of: "∧", with: "&")
                           .replacingOccurrences(of: "∨", with: "|")
                           .replacingOccurrences(of: "¬", with: "~")
        
        let pattern = "->|<->|&|\\||~|□|◇|\\(|\\)|[A-Za-z_][A-Za-z0-9_]*"
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return [] }
        
        let nsString = cleanText as NSString
        let results = regex.matches(in: cleanText, range: NSRange(location: 0, length: nsString.length))
        
        return results.map { nsString.substring(with: $0.range) }
    }
    
    private func isLogicalOperator(_ token: String) -> Bool {
        let ops = ["->", "<->", "&", "|", "~", "□", "◇", "(", ")"]
        return ops.contains(token)
    }
    
    private func getOperatorArity(_ token: String) -> Int {
        if ["->", "<->", "&", "|"].contains(token) { return 2 }
        if ["~", "□", "◇"].contains(token) { return 1 }
        return 0
    }
}
