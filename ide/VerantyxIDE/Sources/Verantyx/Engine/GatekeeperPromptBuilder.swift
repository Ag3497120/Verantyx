import Foundation

// MARK: - GatekeeperPromptBuilder
//
// 【役割】6軸JCross IR + StructuralCommand → Cloud LLM への「意味なしプロンプト」を生成する。
//
// Verantyx-Logic の ReasoningCross（立体十字構造）を Swift に移植し、
// JCross 6軸 (X:制御フロー, Y:データフロー, Z:型制約, W:メモリ, V:スコープ, U:意味)
// のうち「U:意味」のみを Vault に隔離し、残り5軸のトポロジーだけを Cloud LLM に渡す。
//
// Verantyx-Logic からの移植要素:
//   - ReasoningCross  → JCrossGraphContext（グラフ状態の保持）
//   - SolverRouter    → PromptStrategy（どの軸構造をどの順で渡すかの戦略）
//   - ProofSketch     → PatchRequirement（Cloud LLMへの構造的要求仕様）
//   - InputPipeline   → IRDecomposer（IRを各軸に分解）

// MARK: - JCross 6軸ノードアノテーション

/// Verantyx-Logic の ReasoningCross に対応。
/// 6軸のうち意味軸(U)は除外し、残り5軸のトポロジーを保持する。
struct JCrossGraphContext {
    // X軸: 制御フロー（ループ、分岐、例外）
    var controlFlowNodes: [ControlFlowAxisNode]
    // Y軸: データフロー（変数の流れ・入出力）
    var dataFlowEdges: [DataFlowAxisEdge]
    // Z軸: 型制約（TYPE:opaque / TYPE:int 等、具体型はVaultへ）
    var typeConstraints: [TypeAxisConstraint]
    // W軸: メモリライフサイクル（確保/解放/参照カウント）
    var memoryEvents: [MemoryAxisEvent]
    // V軸: スコープ境界（関数境界、クロージャ境界）
    var scopeBoundaries: [ScopeAxisBoundary]
    // U軸: 意味（← ローカルVaultのみ保持。このContextには含まない）
}

struct ControlFlowAxisNode {
    let nodeID: String
    let kind: String          // "CTRL:loop", "CTRL:if", "CTRL:await", "CTRL:return"
    let branchCount: Int
    let domainCategory: String // "ASYNC_IO", "IPC", "COMPUTE" etc.（意味ゼロの抽象カテゴリ）
}

struct DataFlowAxisEdge {
    let fromNodeID: String
    let toNodeID: String
    let typeCategory: String  // "TYPE:opaque", "TYPE:int", "TYPE:bool"
}

struct TypeAxisConstraint {
    let nodeID: String
    let category: String      // "opaque", "int", "float", "string", "duration"
    // 具体的な型名（"URLSession", "String"等）はVaultに隔離
}

struct MemoryAxisEvent {
    let nodeID: String
    let event: String         // "alloc", "release", "retain", "borrow"
}

struct ScopeAxisBoundary {
    let kind: String          // "FUNC", "CLOSURE", "ASYNC_CONTEXT"
    let nodeID: String
    let childNodeIDs: [String]
}

// MARK: - PatchRequirement（ProofSketch に対応）

/// Verantyx-Logic の ProofSketch に対応。
/// Cloud LLM への「何をどう変えてほしいか」の構造的仕様書。
struct PatchRequirement {
    let operation: StructuralCommand.Operation
    let targetNodeID: String
    let domainCategory: String
    let requiredControlFlow: String?    // "CTRL:loop", "CTRL:timeout_wrapper" etc.
    let constraints: [String]           // "TYPE:opaque を使え", "副作用のある軸に触れるな" etc.
    let outputFormat: OutputFormat

    enum OutputFormat: String {
        case graphPatchJSON  // GraphPatch JSON を返す
        case irSnippet       // IRスニペット文字列を返す
    }
}

// MARK: - PromptStrategy（SolverRouter に対応）

/// Verantyx-Logic の SolverRouter に対応。
/// StructuralCommand の内容から最適なプロンプト戦略を選択する。
private struct GKPromptStrategy {

    static func selectAxesToExpose(
        for command: StructuralCommand,
        context: JCrossGraphContext
    ) -> [String] {
        // どの軸を Cloud LLM に見せるか（U軸は常に除外）
        var axes: [String] = ["X:ControlFlow"]  // 常に必要

        switch command.domainCategory {
        case .async_io, .ipc:
            axes += ["W:MemoryLifecycle", "V:ScopeAsync"]  // 非同期文脈では W/V 軸も必要
        case .compute:
            axes += ["Y:DataFlow", "Z:TypeConstraints"]    // 純粋計算では Y/Z 軸を重視
        case .ui_render:
            axes += ["V:ScopeBoundary"]                    // UIスコープの境界情報
        default:
            axes += ["Y:DataFlow"]
        }
        return axes
    }

    static func buildConstraints(for command: StructuralCommand) -> [String] {
        var constraints = [
            "U軸（意味軸）には一切触れるな。すべての変数名は TYPE:opaque として扱え。",
            "新たなノードの意味を推測しようとするな。純粋なグラフ構造パッチのみを返せ。",
            "返答は GraphPatch JSON 形式のみ。自然言語の説明は不要。",
        ]
        if command.domainCategory == .async_io || command.domainCategory == .ipc {
            constraints.append("CTRL:async_await の境界を破るな。スコープ境界を維持せよ。")
        }
        if command.controlFlowKind == .loop {
            constraints.append("ループ条件に具体的な数値を書くな。VAULT:placeholder 形式を使え。")
        }
        return constraints
    }
}

// MARK: - IRDecomposer（InputPipeline に対応）

/// Verantyx-Logic の InputPipeline に対応。
/// JCrossIRDocument を6軸に分解して JCrossGraphContext を構築する。
private struct IRDecomposer {

    static func decompose(ir: JCrossIRDocument) -> JCrossGraphContext {
        var cfNodes: [ControlFlowAxisNode] = []
        var dfEdges: [DataFlowAxisEdge] = []
        var typeConstraints: [TypeAxisConstraint] = []
        var memEvents: [MemoryAxisEvent] = []
        var scopeBounds: [ScopeAxisBoundary] = []

        for (nodeID, node) in ir.nodes {
            let idStr = nodeID.raw

            // X軸: 制御フロー
            if let cf = node.controlFlow {
                let kind: String
                switch cf.kind {
                case .loop:              kind = "CTRL:loop"
                case .conditionalBranch: kind = "CTRL:if"
                case .asyncAwait:        kind = "CTRL:await"
                case .tryCatch:          kind = "CTRL:catch"
                case .earlyReturn:       kind = "CTRL:return"
                case .sequential:        kind = "CTRL:seq"
                }
                let domainCat = inferDomainCategory(node: node)
                cfNodes.append(ControlFlowAxisNode(
                    nodeID: idStr,
                    kind: kind,
                    branchCount: cf.branchCount,
                    domainCategory: domainCat
                ))
            }

            // Y軸: データフロー（inputNodeIDs を使用）
            if let df = node.dataFlow {
                for dep in df.inputNodeIDs {
                    dfEdges.append(DataFlowAxisEdge(
                        fromNodeID: dep.raw,
                        toNodeID: idStr,
                        typeCategory: "TYPE:opaque"  // 具体型はVaultへ
                    ))
                }
            }

            // Z軸: 型制約（TypeConstraintProjection.category を使用）
            if let tc = node.typeConstraints {
                let cat: String
                switch tc.category {
                case .numeric:     cat = "float"
                case .string:      cat = "string"
                case .collection:  cat = "collection"
                case .boolean:     cat = "bool"
                case .opaque:      cat = "opaque"
                case .void:        cat = "void"
                }
                typeConstraints.append(TypeAxisConstraint(nodeID: idStr, category: cat))
            }

            // W軸: メモリライフサイクル（ownershipPattern を使用）
            if let ml = node.memoryLifecycle {
                let event: String
                switch ml.ownershipPattern {
                case .heapOwned:  event = "alloc"
                case .borrowed:   event = "borrow"
                case .shared:     event = "retain"
                case .stackLocal: event = "stack"
                case .unknown:    event = "unknown"
                }
                memEvents.append(.init(nodeID: idStr, event: event))
            }

            // V軸: スコープ境界（visibilityGraph から参照ノードIDを列挙）
            if let scope = node.scope {
                let childIDs = scope.visibilityGraph[nodeID]?.map { $0.raw } ?? []
                let kind = scope.nestingDepth > 0 ? "NESTED_SCOPE" : "ROOT_SCOPE"
                scopeBounds.append(ScopeAxisBoundary(
                    kind: kind,
                    nodeID: idStr,
                    childNodeIDs: childIDs
                ))
            }
        }

        return JCrossGraphContext(
            controlFlowNodes: cfNodes,
            dataFlowEdges: dfEdges,
            typeConstraints: typeConstraints,
            memoryEvents: memEvents,
            scopeBoundaries: scopeBounds
        )
    }

    private static func inferDomainCategory(node: JCrossIRNode) -> String {
        // W軸のメモリパターンでheuristic分類（スコープ非公開）
        if let ml = node.memoryLifecycle, ml.ownershipPattern == .shared { return "ASYNC_IO" }
        return "COMPUTE"
    }
}

// MARK: - GatekeeperPromptBuilder（メインAPI）

/// Verantyx-Logic の ReportBuilder に相当。
/// JCross 6軸 IR と StructuralCommand から Cloud LLM への「意味なし構造プロンプト」を生成する。
final class GatekeeperPromptBuilder {

    static let shared = GatekeeperPromptBuilder()
    private init() {}

    // MARK: - Main API

    /// プロンプトを生成して返す。
    ///
    /// - Parameters:
    ///   - ir: JCross IRドキュメント（6軸構造）
    ///   - command: BitNetIntentTranslatorが生成したStructuralCommand
    ///   - vault: ローカルVault（Opaqueパラメータのキー確認に使用、値は送らない）
    /// - Returns: Cloud LLMに送るプロンプト文字列（意味ゼロ・構造フル）
    func buildPrompt(
        ir: JCrossIRDocument,
        command: StructuralCommand,
        vault: JCrossIRVault
    ) -> String {

        // Step 1: IRを6軸に分解（IRDecomposer = InputPipeline相当）
        let context = IRDecomposer.decompose(ir: ir)

        // Step 2: 公開する軸を決定（PromptStrategy = SolverRouter相当）
        let exposedAxes = GKPromptStrategy.selectAxesToExpose(for: command, context: context)
        let constraints = GKPromptStrategy.buildConstraints(for: command)

        // Step 3: PatchRequirement を構築（ProofSketch相当）
        let requirement = PatchRequirement(
            operation: command.operation,
            targetNodeID: command.targetNodeID,
            domainCategory: command.domainCategory.rawValue.uppercased(),
            requiredControlFlow: command.controlFlowKind.map { "CTRL:\($0.rawValue)" },
            constraints: constraints,
            outputFormat: .graphPatchJSON
        )

        // Step 4: プロンプト文字列を合成
        return renderPrompt(
            context: context,
            requirement: requirement,
            exposedAxes: exposedAxes,
            command: command
        )
    }

    // MARK: - Prompt Rendering

    private func renderPrompt(
        context: JCrossGraphContext,
        requirement: PatchRequirement,
        exposedAxes: [String],
        command: StructuralCommand
    ) -> String {

        var sections: [String] = []

        // ── システム定義 ──────────────────────────────────────
        sections.append("""
        [GATEKEEPER SYSTEM PROMPT]
        You are a structural graph transformation engine.
        You CANNOT see variable names, function names, or concrete values — they are ALL hidden.
        You reason ONLY on graph topology: node IDs, control flow kinds, and structural relationships.
        """)

        // ── 公開する軸の構造データ ────────────────────────────
        sections.append("[EXPOSED AXES: \(exposedAxes.joined(separator: ", "))]")

        // X軸: 制御フロー（最重要軸）
        if !context.controlFlowNodes.isEmpty {
            var xLines = ["[X-AXIS: Control Flow]"]
            for cf in context.controlFlowNodes {
                xLines.append("  NODE[\(cf.nodeID.prefix(8))](\(cf.domainCategory)) = \(cf.kind) {branches:\(cf.branchCount)}")
            }
            sections.append(xLines.joined(separator: "\n"))
        }

        // Y軸: データフロー
        if exposedAxes.contains("Y:DataFlow"), !context.dataFlowEdges.isEmpty {
            var yLines = ["[Y-AXIS: Data Flow]"]
            for edge in context.dataFlowEdges.prefix(20) { // 上限20エッジ
                yLines.append("  NODE[\(edge.fromNodeID.prefix(8))] → NODE[\(edge.toNodeID.prefix(8))] : \(edge.typeCategory)")
            }
            sections.append(yLines.joined(separator: "\n"))
        }

        // Z軸: 型制約
        if exposedAxes.contains("Z:TypeConstraints"), !context.typeConstraints.isEmpty {
            var zLines = ["[Z-AXIS: Type Constraints]"]
            for tc in context.typeConstraints.prefix(10) {
                zLines.append("  NODE[\(tc.nodeID.prefix(8))]: TYPE:\(tc.category)")
            }
            sections.append(zLines.joined(separator: "\n"))
        }

        // W軸: メモリ
        if exposedAxes.contains("W:MemoryLifecycle"), !context.memoryEvents.isEmpty {
            var wLines = ["[W-AXIS: Memory Lifecycle]"]
            for ev in context.memoryEvents.prefix(10) {
                wLines.append("  NODE[\(ev.nodeID.prefix(8))]: MEM:\(ev.event)")
            }
            sections.append(wLines.joined(separator: "\n"))
        }

        // V軸: スコープ
        if exposedAxes.contains("V:ScopeAsync") || exposedAxes.contains("V:ScopeBoundary") {
            var vLines = ["[V-AXIS: Scope Boundaries]"]
            for scope in context.scopeBoundaries.prefix(5) {
                let childStr = scope.childNodeIDs.prefix(3).map { "NODE[\($0.prefix(8))]" }.joined(separator: ", ")
                vLines.append("  [\(scope.kind)] NODE[\(scope.nodeID.prefix(8))] → {\(childStr)}")
            }
            sections.append(vLines.joined(separator: "\n"))
        }

        // ── パッチ要求仕様（PatchRequirement）────────────────
        var reqLines = ["[PATCH REQUIREMENT]"]
        reqLines.append("  TARGET: NODE[\(requirement.targetNodeID.prefix(8))](\(requirement.domainCategory))")
        reqLines.append("  OPERATION: \(requirement.operation.rawValue.uppercased())")
        if let cf = requirement.requiredControlFlow {
            reqLines.append("  INSERT: \(cf)")
        }

        // OpaqueパラメータのVaultキーのみ（値は含めない）
        if !command.parameters.isEmpty {
            for (key, opaque) in command.parameters {
                reqLines.append("  PARAM[\(key)]: TYPE:\(opaque.typeCategory), REF:\(opaque.placeholder)")
            }
        }
        sections.append(reqLines.joined(separator: "\n"))

        // ── 制約リスト ────────────────────────────────────────
        var constraintLines = ["[CONSTRAINTS — YOU MUST FOLLOW ALL]"]
        for (i, c) in requirement.constraints.enumerated() {
            constraintLines.append("  \(i + 1). \(c)")
        }
        sections.append(constraintLines.joined(separator: "\n"))

        // ── 出力フォーマット指定 ──────────────────────────────
        sections.append("""
        [REQUIRED OUTPUT FORMAT]
        Return ONLY valid JSON in the following structure:
        {
          "afterNodeID": "NODE_ID or null",
          "wrapNodeID": "NODE_ID or null",
          "newControlFlow": "CTRL:xxx",
          "parameters": {
            "key": "VAULT:placeholder_key"
          },
          "irSnippet": "... structural IR snippet ..."
        }
        DO NOT include any natural language explanation.
        DO NOT include any actual variable names, function names, or numeric values.
        USE VAULT:key format for all concrete parameters.
        """)

        return sections.joined(separator: "\n\n")
    }
}
