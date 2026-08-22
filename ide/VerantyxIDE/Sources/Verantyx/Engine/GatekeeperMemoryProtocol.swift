import Foundation

// MARK: - GatekeeperMemoryProtocol
//
// Gatekeeperパイプラインにおける L1〜L3 全層記憶プロトコル。
//
// 【設計背景】
// Gatekeeperパイプラインの各ステップはLLMに対してステートレスに呼び出される。
// 「何が変わったか」をステップ間で伝えるには通常のコンテキストウィンドウを使うが、
// これにはセマンティック漏洩のリスクがある。
//
// 解決策: L1〜L3をコンテキスト代替として使用する。
//
//   L1 (漢字トポロジー): 変換セッションのカテゴリ要約
//              例: [迅錆変:0.9] [型対:0.8] [進300/500:0.7]
//
//   L2 (mid-res操作): 確定した型マッピング・状態・エンティティ
//              例: OP.ENTITY("Codable", "serde::Serialize")
//                  OP.STATE("NetworkManager.swift", "converted")
//                  OP.FACT("session_id", "gk-20260503-abc123")
//
//   L3 (raw verbatim): 変換前後のコード/IRの完全テキスト
//              例: 変換前のIRスニペット、生成されたRustコード断片
//
// 【nanoモデル問題】
// nanoモデル（< 20B相当）はL1漢字トポロジーのみ解釈でき、
// L2のOP命令やL3のrawテキストを正確に処理できない。
// → Gatekeeperモード中は20B+モデル（gemma4:26b等）を強制使用。

// MARK: - Memory Layer Types

/// L1: 漢字トポロジータグ（超圧縮サマリー）
struct GKMemoryL1 {
    /// 変換種別タグ: [迅錆変] = Swift→Rust変換セッション
    let kanjiTags: String
    /// 進捗サマリー（1文）
    let summary: String

    var formatted: String {
        "L1: \(kanjiTags) — \(summary)"
    }
}

/// L2: Mid-resolution操作コマンド（型マッピング・状態・決定の記録）
struct GKMemoryL2 {
    var operations: [String]  // "OP.ENTITY(\"Codable\", \"serde::Serialize\")" 等

    mutating func addFact(_ key: String, _ value: String) {
        operations.append("OP.FACT(\"\(key)\", \"\(value)\")")
    }

    mutating func addEntity(_ from: String, _ to: String) {
        operations.append("OP.ENTITY(\"\(from)\", \"\(to)\")")
    }

    mutating func addState(_ key: String, _ state: String) {
        operations.append("OP.STATE(\"\(key)\", \"\(state)\")")
    }

    var formatted: String {
        "L2:\n" + operations.map { "  \($0)" }.joined(separator: "\n")
    }
}

/// L3: Raw verbatim（変換前後のコード/IRの完全テキスト）
struct GKMemoryL3 {
    let stepName: String
    let rawBefore: String   // 変換前のIR/コード（最大2000文字）
    let rawAfter: String    // 変換後のIR/コード（最大2000文字）
    let nodeIDMap: [String: String]  // IRノードID → 実名（Vault由来）

    var formatted: String {
        """
        L3 [\(stepName)]:
          BEFORE: \(rawBefore.prefix(500))...
          AFTER:  \(rawAfter.prefix(500))...
          NODES:  \(nodeIDMap.prefix(5).map { "\($0.key)→\($0.value)" }.joined(separator: ", "))
        """
    }
}

// MARK: - GKConversionSessionMemory

/// 1つの変換セッション全体の L1〜L3 記憶を管理する。
///
/// Gatekeeperパイプラインの各ステップが完了するたびに記録され、
/// 次ステップのプロンプトに注入される。
actor GKConversionSessionMemory {

    // MARK: - Session Identity
    let sessionID: String
    let startedAt: Date
    let userInstruction: String
    let sourceLang: String
    let targetLang: String

    // MARK: - Conversion Progress
    private(set) var totalFiles: Int = 1
    private(set) var convertedFiles: Int = 0

    // MARK: - Type Mapping Table (L2 の核心)
    // Swift型 → Rust型等の確定済みマッピング。
    // 一度決定したら全ファイルで一貫して使用する。
    private(set) var typeMapping: [String: String] = [
        // デフォルト Swift→Rust マッピング
        "String":         "String",
        "Int":            "i64",
        "Double":         "f64",
        "Float":          "f32",
        "Bool":           "bool",
        "Optional<T>":    "Option<T>",
        "Array<T>":       "[T]",
        "Dictionary<K,V>":"HashMap<K, V>",
        "Codable":        "serde::Serialize + serde::Deserialize",
        "Error":          "Box<dyn std::error::Error>",
        "UUID":           "uuid::Uuid",
        "Date":           "chrono::DateTime<chrono::Utc>",
        "Data":           "Vec<u8>",
        "URL":            "url::Url",
    ]

    // MARK: - Step Memory Layers
    private(set) var stepMemories: [GKStepMemory] = []

    // MARK: - File Conversion State (L2)
    private(set) var fileStates: [String: FileConversionState] = [:]

    enum FileConversionState: String {
        case pending    = "pending"
        case converting = "converting"
        case converted  = "converted"
        case failed     = "failed"
    }

    init(
        sessionID: String = "gk-\(Date().timeIntervalSince1970)",
        userInstruction: String,
        sourceLang: String,
        targetLang: String
    ) {
        self.sessionID = sessionID
        self.startedAt = Date()
        self.userInstruction = userInstruction
        self.sourceLang = sourceLang
        self.targetLang = targetLang
    }

    // MARK: - Record Step Memory

    func recordStep(
        step: GatekeeperPipelineStep,
        l1Tags: String,
        l1Summary: String,
        l2Operations: [String],
        l3Before: String,
        l3After: String,
        nodeIDMap: [String: String] = [:]
    ) {
        let memory = GKStepMemory(
            step: step,
            l1: GKMemoryL1(kanjiTags: l1Tags, summary: l1Summary),
            l2: GKMemoryL2(operations: l2Operations),
            l3: GKMemoryL3(
                stepName: step.rawValue,
                rawBefore: l3Before,
                rawAfter: l3After,
                nodeIDMap: nodeIDMap
            ),
            recordedAt: Date()
        )
        stepMemories.append(memory)
    }

    // MARK: - Type Mapping

    func registerTypeMapping(_ swiftType: String, _ targetType: String) {
        typeMapping[swiftType] = targetType
    }

    func resolveType(_ swiftType: String) -> String {
        typeMapping[swiftType] ?? "/* \(swiftType) */"
    }

    // MARK: - File State

    func markFile(_ path: String, state: FileConversionState) {
        fileStates[path] = state
    }

    func setTotalFiles(_ count: Int) {
        totalFiles = count
    }

    func incrementConverted() {
        convertedFiles += 1
    }

    // MARK: - Context Injection (L1〜L3 + 3Dグラフ → LLMプロンプト注入)

    /// v2.2+: L1〜L3 全層 + JCross3DGraph（L1.5/L2.5）をコンテキスト代替として注入。
    ///
    /// レイヤー構成:
    ///   L1    — 漢字タグ（超圧縮、nano可読）
    ///   L1.5  — 3Dグラフの1行スキャンインデックス（nano可読）
    ///   L2    — OP命令列（20B+向け）
    ///   L2.5  — 3Dグラフ座標ナビゲーションマップ（nanoがグラフ探索で状態追跡可能）
    ///   L3    — 直前3ステップのrawテキスト
    func buildContextInjection() -> String {
        var lines: [String] = []

        lines.append("// ═══════════════════════════════════════════════════════")
        lines.append("// GATEKEEPER MEMORY — JCross 立体十字構造 v1.0")
        lines.append("// Session: \(sessionID)  Progress: \(convertedFiles)/\(totalFiles)")
        lines.append("// ═══════════════════════════════════════════════════════")
        lines.append("")

        // ── L1: 漢字タグ（超圧縮）──────────────────────────────────────────
        let srcKanji = langToKanji(sourceLang)
        let dstKanji = langToKanji(targetLang)
        lines.append("// L1: [\(srcKanji)\(dstKanji)変:\(convertedFiles)/\(totalFiles)] \(userInstruction.prefix(50))")
        lines.append("")

        // ── L1.5: 3Dグラフ 1行スキャンインデックス ─────────────────────────
        // 注: 非同期呼び出しが必要なためここでは同期的に簡易版を生成
        let topKanji = [srcKanji, dstKanji, convertedFiles >= totalFiles ? "完" : "進"]
        lines.append("// L1.5: [\(topKanji.joined())] Z=\(stepMemories.count) — \(userInstruction.prefix(40))")
        lines.append("")

        // ── L2: OP命令（20B+向け 型マッピング）────────────────────────────
        lines.append("// L2 [型マッピング]:")
        for (swiftType, targetType) in typeMapping.sorted(by: { $0.key < $1.key }).prefix(12) {
            lines.append("//   OP.ENTITY(\"\(swiftType)\", \"\(targetType)\")")
        }
        lines.append("")

        // ── L2 [状態]: 変換済みファイル ──────────────────────────────────
        let convertedPaths = fileStates.filter { $0.value == .converted }.keys.sorted()
        if !convertedPaths.isEmpty {
            lines.append("// L2 [変換済み \(convertedPaths.count)件]:")
            for path in convertedPaths.suffix(5) {
                lines.append("//   OP.STATE(\"\(path)\", \"converted\")")
            }
            if convertedPaths.count > 5 { lines.append("//   ... +\(convertedPaths.count - 5) more") }
            lines.append("")
        }

        // ── L2.5: 3Dグラフ座標ナビゲーションマップ（nano向け）─────────────
        // nanoモデルは「隣接ノードを見る」操作のみで変換状態を追跡できる
        lines.append("// L2.5 [3D Nav Map — nano可読]:")
        lines.append("// FORMAT: [漢字:weight] @(x,y) z=T | →関係→隣接")
        let progressWeight = min(1.0, Double(convertedFiles) / Double(max(totalFiles, 1)))
        // KanjiPhaseSpace.xy() で KanjiXY 構造体を取得 (タプルを使わない)
        let srcXY = KanjiPhaseSpace.xy(for: srcKanji)
        let dstXY = KanjiPhaseSpace.xy(for: dstKanji)
        let srcCoordStr = srcXY.map { "(\(String(format: "%.0f", $0.x)),\(String(format: "%.0f", $0.y)))" } ?? "(0,0)"
        let dstCoordStr = dstXY.map { "(\(String(format: "%.0f", $0.x)),\(String(format: "%.0f", $0.y)))" } ?? "(1,0)"
        lines.append("//   [\(srcKanji):1.0] @\(srcCoordStr) z=\(stepMemories.count) | →変換→\(dstKanji)")
        lines.append("//   [\(dstKanji):1.0] @\(dstCoordStr) z=\(stepMemories.count) | ←変換←\(srcKanji)")
        lines.append("//   [\(convertedFiles >= totalFiles ? "完" : "進"):\(String(format: "%.2f", progressWeight))] @(5,\(convertedFiles >= totalFiles ? "2" : "4")) z=\(stepMemories.count) — \(convertedFiles)/\(totalFiles) files")
        lines.append("")

        // ── L3: 直前3ステップのrawテキスト ────────────────────────────────
        let recent = stepMemories.suffix(3)
        if !recent.isEmpty {
            lines.append("// L3 [直前ステップ]:")
            for mem in recent {
                lines.append("//   [\(mem.step.rawValue)] \(mem.l1.summary)")
                for op in mem.l2.operations.prefix(2) { lines.append("//     \(op)") }
                if !mem.l3.rawAfter.isEmpty {
                    let snip = mem.l3.rawAfter.prefix(150).replacingOccurrences(of: "\n", with: " ")
                    lines.append("//     → \(snip)...")
                }
            }
            lines.append("")
        }

        lines.append("// ═══════════════════════════════════════════════════════")
        return lines.joined(separator: "\n")
    }

    // MARK: - Helpers

    private func langToKanji(_ lang: String) -> String {
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
}

// MARK: - GKStepMemory (ステップ単体の記憶)

struct GKStepMemory {
    let step: GatekeeperPipelineStep
    let l1: GKMemoryL1
    let l2: GKMemoryL2
    let l3: GKMemoryL3
    let recordedAt: Date
}

// MARK: - GKModelGuard (nanoモデルガード)

/// Gatekeeperモードで使用するモデルが20B+であることを検証する。
///
/// 【理由】
/// nanoモデル（< 20B相当）は:
///   - L2のOP命令を正確に生成できない
///   - L3のrawテキストを正確に解釈できない
///   - GraphPatch JSONの構造的整合性を保てない
///   → Gatekeeperパイプラインが破綻する
///
/// Nanoモデルへのアプローチが確立されるまで、20B+を強制する。
enum GKModelGuard {

    /// 承認済み20B+モデルのパターン
    static let approvedPatterns: [String] = [
        "gemma4:26b", "gemma4:27b", "gemma3:27b",
        "llama3:70b", "llama3.1:70b", "llama3.3:70b",
        "qwen2.5:72b", "qwen2.5:32b",
        "claude-3", "claude-sonnet", "claude-opus",
        "gpt-4", "deepseek-r1",
        "gemini-2.0", "gemini-1.5-pro",
        "mistral-large", "mixtral-8x22b",
        "command-r-plus",
    ]

    /// 警告対象のnanoモデルパターン（Gatekeeperで使用禁止）
    static let nanoPatterns: [String] = [
        "gemma:2b", "gemma3:2b", "gemma3:4b",
        "phi3:mini", "phi3.5:mini",
        "qwen2.5:7b", "qwen2.5:3b",
        "llama3.2:1b", "llama3.2:3b",
        "smollm", "tinyllama",
        ":1b", ":2b", ":3b", ":4b",
    ]

    /// モデルがGatekeeperモードで使用可能かを検証する。
    /// 承認済みパターンに一致しない場合は `fallback` を返す。
    static func validate(
        model: String,
        provider: GatekeeperCloudProvider
    ) -> ValidationResult {
        let lower = model.lowercased()

        // nanoモデルチェック
        for nanoPattern in nanoPatterns {
            if lower.contains(nanoPattern.lowercased()) {
                return .rejected(
                    reason: "nanoモデル(\(model))はGatekeeperモードで使用できません。\n" +
                            "L2/L3記憶を正確に処理するには20B+モデルが必要です。",
                    fallback: provider.gatekeeperFallbackModel
                )
            }
        }

        // 承認済みパターンチェック
        for approved in approvedPatterns {
            if lower.contains(approved.lowercased()) {
                return .approved(model: model)
            }
        }

        // Anthropic/OpenRouter/DeepSeek はAPIプロバイダーなのでモデル名で判断が難しい
        // → Cloud APIプロバイダーは通常承認とする（クラウドモデルは基本的に大規模）
        if provider != .ollama {
            return .approved(model: model)
        }

        // Ollama でパターン不明な場合は警告付き承認
        return .warning(
            model: model,
            message: "モデル(\(model))のパラメータ数が確認できません。\n" +
                     "20B未満のモデルはGatekeeperパイプラインが不安定になる可能性があります。\n" +
                     "推奨: gemma4:26b / llama3:70b"
        )
    }

    enum ValidationResult {
        case approved(model: String)
        case warning(model: String, message: String)
        case rejected(reason: String, fallback: String)

        var effectiveModel: String {
            switch self {
            case .approved(let m):         return m
            case .warning(let m, _):       return m
            case .rejected(_, let fb):     return fb
            }
        }

        var isRejected: Bool {
            if case .rejected = self { return true }
            return false
        }

        var warningMessage: String? {
            switch self {
            case .warning(_, let msg): return msg
            case .rejected(let reason, _): return reason
            default: return nil
            }
        }
    }
}

// MARK: - GatekeeperCloudProvider fallback model

extension GatekeeperCloudProvider {
    /// Gatekeeperモードでのフォールバックモデル（20B+保証）
    var gatekeeperFallbackModel: String {
        switch self {
        case .ollama:     return "gemma4:26b"
        case .anthropic:  return "claude-sonnet-4-5"
        case .openRouter: return "anthropic/claude-3.5-sonnet"
        case .deepSeek:   return "deepseek-chat"
        }
    }
}

// MARK: - GKSessionStore (セッション永続化)

/// 変換セッションの記憶を UserDefaults に永続化する。
/// アプリ再起動後も変換を再開できる。
final class GKSessionStore {

    static let shared = GKSessionStore()
    private init() {}

    private let defaults = UserDefaults.standard
    private let key = "gatekeeper_session_store_v2"

    struct StoredSession: Codable {
        let sessionID: String
        let startedAt: Date
        let userInstruction: String
        let sourceLang: String
        let targetLang: String
        let convertedFiles: Int
        let totalFiles: Int
        let typeMapping: [String: String]
        let fileStates: [String: String]  // FileConversionState.rawValue
        let lastStepSummary: String
    }

    /// 現在のセッション状態を永続化する。
    func save(session: GKConversionSessionMemory) async {
        let typeMapping = await session.typeMapping
        let fileStates  = await session.fileStates.mapValues { $0.rawValue }
        let lastSummary = await session.stepMemories.last?.l1.summary ?? ""
        let converted   = await session.convertedFiles
        let total       = await session.totalFiles

        let stored = StoredSession(
            sessionID: await session.sessionID,
            startedAt: await session.startedAt,
            userInstruction: await session.userInstruction,
            sourceLang: await session.sourceLang,
            targetLang: await session.targetLang,
            convertedFiles: converted,
            totalFiles: total,
            typeMapping: typeMapping,
            fileStates: fileStates,
            lastStepSummary: lastSummary
        )

        if let data = try? JSONEncoder().encode(stored) {
            defaults.set(data, forKey: key)
        }
    }

    /// 最後に保存されたセッション状態を読み込む。
    func load() -> StoredSession? {
        guard let data = defaults.data(forKey: key),
              let session = try? JSONDecoder().decode(StoredSession.self, from: data)
        else { return nil }
        return session
    }

    /// セッションをリセット（変換完了後またはキャンセル後）。
    func reset() {
        defaults.removeObject(forKey: key)
    }

    /// 未完了セッションが存在するか確認する。
    var hasIncompleteSession: Bool {
        guard let session = load() else { return false }
        return session.convertedFiles < session.totalFiles
    }
}
