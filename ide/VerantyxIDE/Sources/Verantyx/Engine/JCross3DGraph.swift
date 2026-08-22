import Foundation

// MARK: - JCross 3D Graph Engine  v1.1 (deadlock-free)
//
// ⚠️ 設計上の注意:
//   - defaultCoords はタプル型 (x:, y:) を使わない → Swift runtime conformance deadlock の原因
//   - GKConversionGraph.shared は nonisolated(unsafe) static var で遅延生成
//   - actor ネスト型に Codable を付けない (conformance chain が起動時デッドロックを引き起こす)

// MARK: - KanjiXY (タプルの代替 — conformance safe)
// (x: Double, y: Double) タプルを辞書の値型に使うと
// Swift ランタイムが起動時に conformance チェックでスタックし UI が固まる。
// 単純な struct で代替する。

struct KanjiXY {
    let x: Double
    let y: Double
}

// MARK: - Coordinate

struct KanjiCoord: Hashable, Sendable {
    let x: Double
    let y: Double
    let z: Int

    func distance(to other: KanjiCoord) -> Double {
        let dx = x - other.x
        let dy = y - other.y
        return (dx * dx + dy * dy).squareRoot()
    }
}

// MARK: - Edge

enum KanjiEdgeType: String, CaseIterable, Sendable {
    case convertsTo  = "→変換→"
    case dependsOn   = "→依存→"
    case extends     = "→拡張→"
    case calls       = "→呼出→"
    case contains    = "→包含→"
    case succeeds    = "→継承→"
    case contradicts = "→矛盾→"
    case temporal    = "→時系列→"
}

struct KanjiEdge: Sendable {
    let id: String
    let fromNodeID: String
    let toNodeID: String
    let type: KanjiEdgeType
    var weight: Double
    let createdAtZ: Int
    let label: String
}

// MARK: - KanjiNode

struct KanjiNode: Sendable {
    let id: String
    let kanji: String
    var coord: KanjiCoord
    var weight: Double
    var label: String
    var edgeIDs: [String]
    var zHistory: [ZSnapshot]

    var nanoReadable: String {
        "[\(kanji):\(String(format: "%.1f", weight))] @(\(String(format: "%.1f", coord.x)),\(String(format: "%.1f", coord.y))) z=\(coord.z) — \(label.prefix(40))"
    }

    struct ZSnapshot: Sendable {
        let z: Int
        let weight: Double
        let label: String
    }

    mutating func updateZ(_ z: Int, weight: Double, label: String) {
        zHistory.append(ZSnapshot(z: z, weight: weight, label: label))
        self.weight = weight
        self.label  = label
        self.coord  = KanjiCoord(x: coord.x, y: coord.y, z: z)
    }
}

// MARK: - KanjiPhaseSpace
// ⚠️ static let で [String: タプル] を使うと起動時 conformance deadlock が発生する。
//    KanjiXY 構造体を使い、かつ static func で遅延アクセスする。

enum KanjiPhaseSpace {

    // nonisolated(unsafe): 読み取り専用定数なので safe
    nonisolated(unsafe) private static let _coords: [String: KanjiXY] = {
        var d = [String: KanjiXY]()
        // 言語 (Y=0)
        d["迅"] = KanjiXY(x: 0, y: 0)   // Swift
        d["錆"] = KanjiXY(x: 1, y: 0)   // Rust
        d["蛇"] = KanjiXY(x: 2, y: 0)   // Python
        d["型"] = KanjiXY(x: 3, y: 0)   // TypeScript
        d["晶"] = KanjiXY(x: 4, y: 0)   // Kotlin
        d["碁"] = KanjiXY(x: 5, y: 0)   // Go
        d["码"] = KanjiXY(x: 6, y: 0)   // 汎用
        // コード構造 (X=0, Y=1-5)
        d["廻"] = KanjiXY(x: 0, y: 1)   // Loop
        d["条"] = KanjiXY(x: 0, y: 2)   // Branch
        d["並"] = KanjiXY(x: 0, y: 3)   // Async
        d["捕"] = KanjiXY(x: 0, y: 4)   // Error
        d["義"] = KanjiXY(x: 0, y: 5)   // Function
        d["構"] = KanjiXY(x: 1, y: 5)   // Struct
        d["契"] = KanjiXY(x: 2, y: 5)   // Protocol
        // アクション (X=5)
        d["変"] = KanjiXY(x: 5, y: 1)
        d["完"] = KanjiXY(x: 5, y: 2)
        d["失"] = KanjiXY(x: 5, y: 3)
        d["進"] = KanjiXY(x: 5, y: 4)
        d["記"] = KanjiXY(x: 5, y: 5)
        // 状態 (X=3)
        d["始"] = KanjiXY(x: 3, y: 1)
        d["済"] = KanjiXY(x: 3, y: 2)
        d["待"] = KanjiXY(x: 3, y: 3)
        d["中"] = KanjiXY(x: 3, y: 4)
        // セキュリティ (X=7)
        d["秘"] = KanjiXY(x: 7, y: 0)
        d["匿"] = KanjiXY(x: 7, y: 1)
        d["守"] = KanjiXY(x: 7, y: 2)
        d["鍵"] = KanjiXY(x: 7, y: 3)
        d["壁"] = KanjiXY(x: 7, y: 4)
        // メモリ (X=8)
        d["憶"] = KanjiXY(x: 8, y: 0)
        d["核"] = KanjiXY(x: 8, y: 1)
        d["標"] = KanjiXY(x: 8, y: 2)
        d["索"] = KanjiXY(x: 8, y: 3)
        d["脈"] = KanjiXY(x: 8, y: 4)
        return d
    }()

    static func xy(for kanji: String) -> KanjiXY? {
        _coords[kanji]
    }

    static func coord(for kanji: String, z: Int = 0) -> KanjiCoord {
        if let d = _coords[kanji] {
            return KanjiCoord(x: d.x, y: d.y, z: z)
        }
        let hash = abs(kanji.unicodeScalars.reduce(0) { $0 &+ Int($1.value) })
        return KanjiCoord(x: Double(hash % 10), y: Double((hash / 10) % 10), z: z)
    }
}

// MARK: - JCross3DDocument

actor JCross3DDocument {

    private(set) var nodes: [String: KanjiNode] = [:]
    private(set) var edges: [String: KanjiEdge] = [:]
    private(set) var currentZ: Int = 0
    let documentID: String

    init(documentID: String = UUID().uuidString) {
        self.documentID = documentID
    }

    @discardableResult
    func upsertNode(kanji: String, weight: Double = 1.0, label: String = "") -> KanjiNode {
        let nodeID = "N_\(kanji)"
        if var existing = nodes[nodeID] {
            existing.updateZ(currentZ, weight: weight, label: label.isEmpty ? existing.label : label)
            nodes[nodeID] = existing
            return existing
        }
        let coord = KanjiPhaseSpace.coord(for: kanji, z: currentZ)
        let node = KanjiNode(
            id: nodeID, kanji: kanji, coord: coord,
            weight: weight, label: label, edgeIDs: [],
            zHistory: [KanjiNode.ZSnapshot(z: currentZ, weight: weight, label: label)]
        )
        nodes[nodeID] = node
        return node
    }

    @discardableResult
    func addEdge(from: String, to: String, type edgeType: KanjiEdgeType,
                 weight: Double = 1.0, label: String = "") -> KanjiEdge {
        let edgeID = "E_\(from)_\(edgeType.rawValue)_\(to)_Z\(currentZ)"
        let edge = KanjiEdge(
            id: edgeID, fromNodeID: "N_\(from)", toNodeID: "N_\(to)",
            type: edgeType, weight: weight, createdAtZ: currentZ,
            label: label.isEmpty ? "\(from)\(edgeType.rawValue)\(to)" : label
        )
        edges[edgeID] = edge
        if var fromNode = nodes["N_\(from)"] {
            fromNode.edgeIDs.append(edgeID)
            nodes["N_\(from)"] = fromNode
        }
        return edge
    }

    func advanceZ() { currentZ += 1 }

    func toL1String(topK: Int = 5) -> String {
        nodes.values.sorted { $0.weight > $1.weight }
            .prefix(topK)
            .map { "[\($0.kanji):\(String(format: "%.1f", $0.weight))]" }
            .joined(separator: " ")
    }

    func toL15String() -> String {
        let top = nodes.values.sorted { $0.weight > $1.weight }.prefix(3)
        let kanjiPart = top.map { $0.kanji }.joined()
        let label = top.compactMap { $0.label.isEmpty ? nil : $0.label }.first ?? ""
        return "[\(kanjiPart)] Z=\(currentZ) — \(label.prefix(60))"
    }

    func toL25NanoMap() -> String {
        var lines = ["// JCROSS_3D_NAV Z=\(currentZ)",
                     "// FORMAT: [漢字:weight] @(x,y) | →type→隣接"]
        for node in nodes.values.sorted(by: { $0.weight > $1.weight }).prefix(10) {
            var line = node.nanoReadable
            let outEdges = node.edgeIDs.compactMap { edges[$0] }
                .filter { $0.fromNodeID == node.id }
                .prefix(3)
                .map { e -> String in
                    let toKanji = nodes[e.toNodeID]?.kanji ?? e.toNodeID
                    return "\(e.type.rawValue)\(toKanji)"
                }
            if !outEdges.isEmpty { line += " | " + outEdges.joined(separator: " ") }
            lines.append(line)
        }
        return lines.joined(separator: "\n")
    }
}

// MARK: - GKConversionGraph
// ⚠️ static let shared は actor の場合、起動時にメインスレッドで初期化され
//    Codable/Sendable conformance チェックがデッドロックを引き起こす。
//    nonisolated(unsafe) static var + 遅延生成で回避する。

actor GKConversionGraph {

    // nonisolated(unsafe): シングルトンは起動後に一度だけ書き込まれる (safe)
    nonisolated(unsafe) static var shared = GKConversionGraph()
    private init() {}

    private var graphs: [String: JCross3DDocument] = [:]

    func graph(for sessionID: String) -> JCross3DDocument {
        if let g = graphs[sessionID] { return g }
        let g = JCross3DDocument(documentID: sessionID)
        graphs[sessionID] = g
        return g
    }

    func recordPipelineStep(
        sessionID: String,
        step: GatekeeperPipelineStep,
        sourceLang: String,
        targetLang: String,
        convertedCount: Int,
        totalCount: Int,
        typeMappings: [String: String],
        summary: String
    ) async {
        let g = graph(for: sessionID)
        await g.advanceZ()

        let srcKanji = langKanji(sourceLang)
        let dstKanji = langKanji(targetLang)
        await g.upsertNode(kanji: srcKanji, weight: 1.0, label: sourceLang)
        await g.upsertNode(kanji: dstKanji, weight: 1.0, label: targetLang)
        await g.addEdge(from: srcKanji, to: dstKanji, type: .convertsTo, weight: 1.0,
                        label: "\(sourceLang) → \(targetLang)")

        let progress  = Double(convertedCount) / Double(max(totalCount, 1))
        let progKanji = progress >= 1.0 ? "完" : "進"
        await g.upsertNode(kanji: progKanji, weight: progress,
                           label: "\(convertedCount)/\(totalCount) \(summary.prefix(40))")

        let stepKanji = stepToKanji(step)
        await g.upsertNode(kanji: stepKanji, weight: 0.9, label: step.rawValue)
        await g.addEdge(from: srcKanji, to: stepKanji, type: .temporal, weight: 0.8)

        for (from, to) in typeMappings.prefix(5) {
            let fK = String(from.prefix(2))
            let tK = String(to.prefix(2))
            await g.upsertNode(kanji: fK, weight: 0.7, label: from)
            await g.upsertNode(kanji: tK, weight: 0.7, label: to)
            await g.addEdge(from: fK, to: tK, type: .convertsTo, weight: 0.9,
                            label: "\(from) → \(to)")
        }
    }

    func fullContextForLLM(sessionID: String) async -> String {
        let g  = graph(for: sessionID)
        let l1 = await g.toL1String()
        let l15 = await g.toL15String()
        let l25 = await g.toL25NanoMap()
        return """
        // 3D GRAPH MEMORY — JCross 立体十字構造 v1.1
        // L1:   \(l1)
        // L1.5: \(l15)
        // L2.5:
        \(l25.components(separatedBy: "\n").map { "//   \($0)" }.joined(separator: "\n"))
        """
    }

    // MARK: - Helpers

    private func langKanji(_ lang: String) -> String {
        switch lang.lowercased() {
        case "swift":      return "迅"
        case "rust":       return "錆"
        case "python":     return "蛇"
        case "typescript": return "型"
        case "kotlin":     return "晶"
        case "go":         return "碁"
        default:           return "码"
        }
    }

    private func stepToKanji(_ step: GatekeeperPipelineStep) -> String {
        switch step {
        case .modelValidation: return "守"
        case .irGeneration:    return "構"
        case .vaultSeparation: return "鍵"
        case .intentTranslate: return "義"
        case .promptBuild:     return "標"
        case .llmCall:         return "網"
        case .patchParse:      return "索"
        case .vaultRehydrate:  return "完"
        }
    }
}
