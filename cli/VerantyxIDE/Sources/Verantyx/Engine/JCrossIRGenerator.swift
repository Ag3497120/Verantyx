import Foundation
import CryptoKit

// MARK: - JCross IR Generator v2.1
//
// ソースコードを 6軸IR + ローカルVault に変換するエンジン。
//
// 処理フロー:
//   Source Code
//       ↓ generateIR()
//   ┌── JCrossIRDocument ──┐    ←  LLMへ送信（意味論なし）
//   │  IRNode × N         │
//   │  DataFlow topology  │
//   │  Control structure  │
//   └──────────────────────┘
//       ↓ 同時に
//   ┌── JCrossIRVault ─────┐    ←  ローカルのみ保持
//   │  VaultEntry × N     │
//   │  function names     │
//   │  concrete values    │
//   │  1.21, "tax", etc.  │
//   └──────────────────────┘
//       ↓ patch適用後
//   Source Code (完全復元)      ←  ローカルで再生成

// MARK: - Generation Context

private struct GenerationContext {
    let language: JCrossCodeTranspiler.CodeLanguage
    let vault: JCrossIRVault
    var nodes: [IRNodeID: JCrossIRNode] = [:]
    var functions: [JCrossIRFunction] = []
    var nodeCounter: Int = 0

    mutating func nextNode(kind: JCrossIRNode.NodeKind) -> (IRNodeID, JCrossIRNode) {
        nodeCounter += 1
        let id = IRNodeID()
        let node = JCrossIRNode(
            id: id, nodeKind: kind,
            controlFlow: nil, dataFlow: nil, typeConstraints: nil,
            memoryLifecycle: nil, scope: nil
        )
        return (id, node)
    }
}

// MARK: - JCrossIRGenerator

/// ソースコード → 6軸IR の生成エンジン。
/// Vault への秘密軸の分離を同時に実行する。
final class JCrossIRGenerator {

    // MARK: - Configuration

    /// ノイズノードの注入率（0.0 = なし、1.0 = 100%密度）
    var noiseDensity: Double = 0.3

    /// 型情報の曖昧化レベル（0 = 具体型公開, 1 = カテゴリのみ）
    var typeObfuscationLevel: Int = 1

    // MARK: - Main API

    /// ソースコードを解析し、6軸IRドキュメントとVaultを生成する。
    ///
    /// - Parameters:
    ///   - source: 対象ソースコード
    ///   - language: 言語
    ///   - vault: 秘密軸の保存先Vault（外部から注入）
    /// - Returns: LLMに送信可能なIRドキュメント
    func generateIR(
        from source: String,
        language: JCrossCodeTranspiler.CodeLanguage,
        vault: JCrossIRVault
    ) -> JCrossIRDocument {
        var context = GenerationContext(language: language, vault: vault)

        // Phase 1: ソースを行単位で解析してIRに変換
        let lines = source.components(separatedBy: "\n")
        let irFunctions = extractFunctions(from: lines, context: &context)

        // Phase 2: ダミーノードを注入してパターン推論を妨げる
        let noisedNodes = injectNoiseNodes(into: context.nodes, density: noiseDensity)

        // Phase 3: IRドキュメントを構築
        return JCrossIRDocument(
            documentID: IRNodeID(),
            language: language.rawValue,
            protocolVersion: "2.1",
            generatedAt: Date(),
            functions: irFunctions,
            nodes: noisedNodes
        )
    }

    // MARK: - Function Extraction

    private func extractFunctions(
        from lines: [String],
        context: inout GenerationContext
    ) -> [JCrossIRFunction] {
        var functions: [JCrossIRFunction] = []
        var i = 0

        while i < lines.count {
            let line = lines[i].trimmingCharacters(in: .whitespaces)

            if let funcInfo = parseFunctionDeclaration(line, language: context.language) {
                let funcID = IRNodeID()
                var bodyNodeIDs: [IRNodeID] = []

                // 関数本体を解析（簡易実装：次の閉じ括弧まで）
                var depth = 1
                var j = i + 1
                while j < lines.count && depth > 0 {
                    let bodyLine = lines[j].trimmingCharacters(in: .whitespaces)
                    if bodyLine.contains("{") { depth += 1 }
                    if bodyLine.contains("}") { depth -= 1 }
                    if depth > 0 {
                        if let nodeID = processLine(bodyLine, funcID: funcID, context: &context) {
                            bodyNodeIDs.append(nodeID)
                        }
                    }
                    j += 1
                }

                // IRFunctionを構築
                let irFunc = JCrossIRFunction(
                    id: funcID,
                    paramCount: funcInfo.paramCount,
                    returnCount: funcInfo.hasReturn ? 1 : 0,
                    bodyNodeIDs: bodyNodeIDs,
                    isAsync: funcInfo.isAsync,
                    canThrow: funcInfo.canThrow
                )
                functions.append(irFunc)

                // Vaultに意味論情報を保存
                let funcVaultEntry = FunctionVaultEntry(
                    functionID: funcID,
                    name: funcInfo.name,
                    semanticPurpose: inferPurpose(from: funcInfo.name),
                    parameterDetails: funcInfo.paramNames.map { (name: $0, domain: inferDomain($0)) },
                    returnTypeName: funcInfo.returnType,
                    inlineConstants: [],
                    domainLabel: inferDomainLabel(from: funcInfo.name)
                )
                context.vault.storeFunctionEntry(funcVaultEntry)

                i = j
            } else {
                i += 1
            }
        }

        return functions
    }

    // MARK: - Line Processing

    /// 1行を解析し、対応するIRノードIDを返す
    private func processLine(
        _ line: String,
        funcID: IRNodeID,
        context: inout GenerationContext
    ) -> IRNodeID? {
        let trimmed = line.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty && !trimmed.hasPrefix("//") else { return nil }

        // 制御フロー検出
        if let cfProjection = parseControlFlow(trimmed) {
            let nodeID = IRNodeID()
            let node = JCrossIRNode(
                id: nodeID, nodeKind: .controlBlock,
                controlFlow: cfProjection,
                dataFlow: nil, typeConstraints: nil,
                memoryLifecycle: nil, scope: nil
            )
            context.nodes[nodeID] = node

            // Vaultに条件式の具体内容を保存
            context.vault.storeSemantics(
                nodeID: nodeID,
                semantics: SemanticsData(
                    functionName: nil,
                    variableName: nil,
                    semanticPurpose: "control_flow: \(trimmed)",
                    domainLabel: nil,
                    inlineConstants: [],
                    parameterNames: [],
                    returnTypeLabel: nil
                )
            )
            return nodeID
        }

        // 演算検出（乗算・関数呼び出し等）
        if let (dfProjection, concrete, literals) = parseDataFlow(trimmed, language: context.language) {
            let nodeID = IRNodeID()
            let node = JCrossIRNode(
                id: nodeID, nodeKind: .operation,
                controlFlow: nil,
                dataFlow: dfProjection,
                typeConstraints: nil, memoryLifecycle: nil, scope: nil
            )
            context.nodes[nodeID] = node

            // Vaultにオペランドの具体値を保存（1.21などはここで隔離）
            context.vault.storeSemantics(
                nodeID: nodeID,
                semantics: SemanticsData(
                    functionName: concrete.functionName,
                    variableName: concrete.resultVariable,
                    semanticPurpose: nil,
                    domainLabel: nil,
                    inlineConstants: literals,
                    parameterNames: [],
                    returnTypeLabel: nil
                ),
                dataFlowConcrete: concrete
            )
            return nodeID
        }

        // 変数宣言検出
        if let (typeProj, typeConcrete, varName) = parseVariableDeclaration(trimmed) {
            let nodeID = IRNodeID()
            let node = JCrossIRNode(
                id: nodeID, nodeKind: .variable,
                controlFlow: nil, dataFlow: nil,
                typeConstraints: typeProj,
                memoryLifecycle: MemoryLifecycleProjection(
                    ownershipPattern: .stackLocal,
                    sizeClass: .small,
                    relativeLifetimeOrder: []
                ),
                scope: nil
            )
            context.nodes[nodeID] = node

            // Vaultに変数名・具体型を保存
            context.vault.storeSemantics(
                nodeID: nodeID,
                typeConcrete: typeConcrete,
                memoryConcrete: MemoryConcrete(
                    variableName: varName,
                    typeName: typeConcrete.concreteTypeName,
                    scopeContext: nil,
                    fields: [:]
                )
            )
            return nodeID
        }

        return nil
    }

    // MARK: - Pattern Parsers

    private struct FunctionInfo {
        let name: String
        let paramCount: Int
        let paramNames: [String]
        let hasReturn: Bool
        let returnType: String?
        let isAsync: Bool
        let canThrow: Bool
    }

    /// Swift/Python/TypeScript の関数宣言を検出
    private func parseFunctionDeclaration(
        _ line: String,
        language: JCrossCodeTranspiler.CodeLanguage
    ) -> FunctionInfo? {
        // Swift: func name(param: Type) -> ReturnType {
        if language == .swift {
            let pattern = #"(?:public |private |internal |open )*func\s+(\w+)\s*\(([^)]*)\)\s*(?:->([^{]+))?\{?"#
            if let match = line.range(of: pattern, options: .regularExpression) {
                let matched = String(line[match])
                // 関数名を抽出
                if let nameRange = matched.range(of: #"func\s+(\w+)"#, options: .regularExpression) {
                    var funcName = String(matched[nameRange])
                    funcName = funcName.replacingOccurrences(of: "func ", with: "").trimmingCharacters(in: .whitespaces)

                    // パラメータ数を推定
                    let paramSection = matched.components(separatedBy: "(").dropFirst().first ?? ""
                    let paramNames = paramSection.components(separatedBy: ",")
                        .map { $0.trimmingCharacters(in: .whitespaces) }
                        .filter { !$0.isEmpty && !$0.hasPrefix(")") }
                        .map { $0.components(separatedBy: ":").first?.trimmingCharacters(in: .whitespaces) ?? "" }
                        .filter { !$0.isEmpty }

                    let hasReturn = matched.contains("->")
                    let returnType = hasReturn ? matched.components(separatedBy: "->").last?
                        .trimmingCharacters(in: .whitespacesAndNewlines)
                        .replacingOccurrences(of: "{", with: "")
                        .trimmingCharacters(in: .whitespaces) : nil

                    return FunctionInfo(
                        name: funcName,
                        paramCount: paramNames.count,
                        paramNames: paramNames,
                        hasReturn: hasReturn,
                        returnType: returnType,
                        isAsync: line.contains("async"),
                        canThrow: line.contains("throws")
                    )
                }
            }
        }

        // Python: def name(param, ...):
        if language == .python {
            let pattern = #"def\s+(\w+)\s*\(([^)]*)\)\s*(?:->([^:]+))?:"#
            if let _ = line.range(of: pattern, options: .regularExpression) {
                let parts = line.components(separatedBy: "def ").last ?? ""
                let name = parts.components(separatedBy: "(").first?.trimmingCharacters(in: .whitespaces) ?? ""
                let paramStr = parts.components(separatedBy: "(").dropFirst().first?.components(separatedBy: ")").first ?? ""
                let params = paramStr.components(separatedBy: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
                return FunctionInfo(
                    name: name,
                    paramCount: params.count,
                    paramNames: params,
                    hasReturn: line.contains("->"),
                    returnType: nil,
                    isAsync: line.contains("async"),
                    canThrow: false
                )
            }
        }

        return nil
    }

    /// 制御フローの検出
    private func parseControlFlow(_ line: String) -> ControlFlowProjection? {
        let conditionalKeywords = ["if ", "guard ", "switch "]
        let loopKeywords = ["for ", "while "]

        for kw in conditionalKeywords {
            if line.hasPrefix(kw) {
                // 条件式のハッシュを生成（内容は隠す）
                let condExpr = line.dropFirst(kw.count).components(separatedBy: "{").first ?? ""
                let hash = "0x" + SHA256.hash(data: Data(condExpr.utf8))
                    .map { String(format: "%02x", $0) }.joined().prefix(8)
                let arity = condExpr.components(separatedBy: "&&").count
                    + condExpr.components(separatedBy: "||").count - 1

                return ControlFlowProjection(
                    kind: .conditionalBranch,
                    branchCount: 2,
                    conditionHash: hash,
                    conditionArity: max(1, arity)
                )
            }
        }

        for kw in loopKeywords {
            if line.hasPrefix(kw) {
                return ControlFlowProjection(
                    kind: .loop,
                    branchCount: 1,
                    conditionHash: "0x" + String(abs(line.hashValue), radix: 16).prefix(8),
                    conditionArity: 1
                )
            }
        }

        return nil
    }

    /// データフローの検出（演算 + 関数呼び出し）
    private func parseDataFlow(
        _ line: String,
        language: JCrossCodeTranspiler.CodeLanguage
    ) -> (DataFlowProjection, DataFlowConcrete, [String])? {
        // 数値リテラルの検出
        let literalHint = LiteralLanguageHint.swift  // 簡易版
        let foundLiterals = LiteralExtractor.extractFromLine(line, lineNumber: 0, language: literalHint)
        let literalValues = foundLiterals.map { $0.cleanValue }

        // 乗算の検出: x * 1.21
        if line.contains("*"), !literalValues.isEmpty {
            let parts = line.components(separatedBy: "*")
            let leftStr = parts.first?.trimmingCharacters(in: .whitespaces)
                .components(separatedBy: "=").last?.trimmingCharacters(in: .whitespaces)
            let rightStr = literalValues.first

            let df = DataFlowProjection(
                inputArity: 2,
                outputArity: 1,
                operationCategory: .arithmetic,
                operationType: .multiply,
                inputNodeIDs: [IRNodeID(), IRNodeID()],  // 左右オペランドのノード
                outputNodeIDs: [IRNodeID()]
            )
            let concrete = DataFlowConcrete(
                leftOperand: leftStr,
                rightOperand: rightStr,          // ← 1.21 はVaultに隔離
                functionName: nil,
                resultVariable: extractResultVar(from: line),
                inlineConstants: Dictionary(uniqueKeysWithValues: literalValues.enumerated().map {
                    ("CONST_\($0.offset)", $0.element)
                })
            )
            return (df, concrete, literalValues)
        }

        // 関数呼び出しの検出: round(x, 2)
        if let fnCallPattern = line.range(of: #"(\w+)\s*\([^)]+\)"#, options: .regularExpression) {
            let fnCall = String(line[fnCallPattern])
            let fnName = fnCall.components(separatedBy: "(").first ?? ""

            let df = DataFlowProjection(
                inputArity: max(1, literalValues.count),
                outputArity: 1,
                operationCategory: .functional,
                operationType: .call,
                inputNodeIDs: (0..<max(1, literalValues.count)).map { _ in IRNodeID() },
                outputNodeIDs: [IRNodeID()]
            )
            let concrete = DataFlowConcrete(
                leftOperand: nil,
                rightOperand: nil,
                functionName: fnName,            // ← "round" はVaultに隔離
                resultVariable: extractResultVar(from: line),
                inlineConstants: Dictionary(uniqueKeysWithValues: literalValues.enumerated().map {
                    ("CONST_\($0.offset)", $0.element)
                })
            )
            return (df, concrete, literalValues)
        }

        return nil
    }

    /// 変数宣言の検出: let/var/const
    private func parseVariableDeclaration(
        _ line: String
    ) -> (TypeConstraintProjection, TypeConcrete, String)? {
        let keywords = ["let ", "var ", "const ", "val "]
        for kw in keywords {
            if line.hasPrefix(kw) {
                let rest = String(line.dropFirst(kw.count))
                let varName = rest.components(separatedBy: ":").first?
                    .components(separatedBy: "=").first?
                    .trimmingCharacters(in: .whitespaces) ?? "?"

                // 型の曖昧化
                let typeStr = rest.components(separatedBy: ":").dropFirst().first?
                    .components(separatedBy: "=").first?
                    .trimmingCharacters(in: .whitespaces) ?? ""

                let category: TypeConstraintProjection.TypeCategory
                let magnitude: TypeConstraintProjection.MagnitudeClass
                let concreteType: String

                if typeStr.contains("Double") || typeStr.contains("Float") || typeStr.contains("Decimal") {
                    category = .numeric; magnitude = .fractional; concreteType = typeStr
                } else if typeStr.contains("Int") {
                    category = .numeric; magnitude = .integral; concreteType = typeStr
                } else if typeStr.contains("String") {
                    category = .string; magnitude = .unknown; concreteType = typeStr
                } else if typeStr.contains("Bool") {
                    category = .boolean; magnitude = .unknown; concreteType = typeStr
                } else {
                    category = .opaque; magnitude = .unknown; concreteType = typeStr.isEmpty ? "?" : typeStr
                }

                let hashStr = "0x" + String(abs(concreteType.hashValue), radix: 16).prefix(8)
                let typeProj = TypeConstraintProjection(
                    category: category,
                    magnitudeClass: magnitude,
                    sealedHash: hashStr
                )
                let concrete = TypeConcrete(
                    concreteTypeName: concreteType,
                    semanticRole: inferSemanticRole(from: varName),
                    domain: inferDomain(varName)
                )
                return (typeProj, concrete, varName)
            }
        }
        return nil
    }

    // MARK: - Noise Injection

    private func injectNoiseNodes(
        into nodes: [IRNodeID: JCrossIRNode],
        density: Double
    ) -> [IRNodeID: JCrossIRNode] {
        var result = nodes
        let targetCount = Int(Double(nodes.count) * density)

        for _ in 0..<targetCount {
            let noiseID = IRNodeID()
            let noiseNode = JCrossIRNode(
                id: noiseID,
                nodeKind: .unknown,
                controlFlow: nil,
                dataFlow: DataFlowProjection(
                    inputArity: Int.random(in: 1...3),
                    outputArity: 1,
                    operationCategory: .unknown,
                    operationType: .unknown,
                    inputNodeIDs: [],
                    outputNodeIDs: []
                ),
                typeConstraints: nil,
                memoryLifecycle: nil,
                scope: nil
            )
            result[noiseID] = noiseNode
        }
        return result
    }

    // MARK: - Semantic Inference (Vault-side only)

    private func inferPurpose(from name: String) -> String? {
        let lower = name.lowercased()
        if lower.contains("tax")     { return "Tax computation" }
        if lower.contains("auth")    { return "Authentication" }
        if lower.contains("payment") { return "Payment processing" }
        if lower.contains("encrypt") { return "Encryption" }
        return nil
    }

    private func inferDomainLabel(from name: String) -> String? {
        let lower = name.lowercased()
        if lower.contains("tax") || lower.contains("vat") || lower.contains("price") { return "finance" }
        if lower.contains("auth") || lower.contains("token") { return "security" }
        if lower.contains("user") || lower.contains("account") { return "identity" }
        return nil
    }

    private func inferDomain(_ name: String) -> String? {
        let lower = name.lowercased()
        if lower.contains("rate") || lower.contains("price") || lower.contains("amount") { return "currency" }
        if lower.contains("temp") || lower.contains("celsius") { return "temperature" }
        if lower.contains("prob") || lower.contains("confidence") { return "probability" }
        return nil
    }

    private func inferSemanticRole(from name: String) -> String? {
        let lower = name.lowercased()
        if lower.contains("rate")   { return "rate_multiplier" }
        if lower.contains("total")  { return "aggregate_value" }
        if lower.contains("result") { return "computation_output" }
        return nil
    }

    private func extractResultVar(from line: String) -> String? {
        // "let result = ..." → "result"
        let pattern = #"(?:let|var|const|val)\s+(\w+)\s*="#
        if let m = line.range(of: pattern, options: .regularExpression) {
            let matched = String(line[m])
            return matched
                .replacingOccurrences(of: "let ", with: "")
                .replacingOccurrences(of: "var ", with: "")
                .replacingOccurrences(of: "const ", with: "")
                .components(separatedBy: "=").first?
                .trimmingCharacters(in: .whitespaces)
        }
        return nil
    }
}

