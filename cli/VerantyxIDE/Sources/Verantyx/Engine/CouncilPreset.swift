import Foundation

/// Selectable configuration templates for `CouncilOrchestrator.Config`,
/// including the user's described "strongest" architecture --
/// **同型JGEN合議核 + 永遠の記憶 + 短いテキスト手渡し + 実行専用エージェント**
/// (identical-weights JGEN council core + eternal memory + a short
/// structured text handoff + a separate execution agent) -- plus a few
/// alternatives for different tradeoffs. Picking a preset just seeds
/// `VectorLabView`'s `@State` config vars; any field can still be
/// hand-edited afterward (see `markCustom()`/`applyPreset()`).
struct CouncilPreset: Identifiable {
    let id: String
    let name: String
    let nameJA: String
    let description: String
    let descriptionJA: String
    let config: CouncilOrchestrator.Config

    static let builtins: [CouncilPreset] = [
        CouncilPreset(
            id: "strongest",
            name: "Strongest (4-layer)",
            nameJA: "最強構成(4層)",
            description: "Full 5-role cast, all memory sources, deep rounds + perturb-test, escalates a short structured handoff to a separate execution model. Set the escalation model before running.",
            descriptionJA: "5役割フルキャスト、全記憶ソース、深いラウンド+摂動テスト、短い構造化ハンドオフを別の実行用モデルへエスカレーション。実行前にエスカレーション先モデルを設定してください。",
            config: CouncilOrchestrator.Config(
                roleCount: 5,
                roundsCap: 5,
                injectionPolicy: .deepRounds,
                useVeraMemory: true,
                zoneLayers: [.l1, .l1_5, .l2, .l3],
                useEternalMemory: true,
                escalateOnLowConfidence: true,
                escalationConfidenceThreshold: 0.6,
                escalationModel: ""
            )
        ),
        CouncilPreset(
            id: "fast",
            name: "Fast (single-pass)",
            nameJA: "高速(単一パス)",
            description: "2 roles, no injection, 1 round, no escalation -- a quick sanity check with minimal deliberation overhead.",
            descriptionJA: "2役割、注入なし、1ラウンド、エスカレーションなし — 最小限の合議コストでの簡易チェック。",
            config: CouncilOrchestrator.Config(
                roleCount: 2,
                roundsCap: 1,
                injectionPolicy: .none,
                useVeraMemory: true,
                zoneLayers: [],
                useEternalMemory: false,
                escalateOnLowConfidence: false,
                escalationConfidenceThreshold: 0.6,
                escalationModel: ""
            )
        ),
        CouncilPreset(
            id: "memoryHeavy",
            name: "Memory-heavy",
            nameJA: "記憶重視",
            description: "3 roles, all memory sources on, early-steal injection -- biases toward recalling stored context over independent reasoning.",
            descriptionJA: "3役割、全記憶ソースON、early-steal注入 — 独立した推論より蓄積された文脈の想起を優先。",
            config: CouncilOrchestrator.Config(
                roleCount: 3,
                roundsCap: 4,
                injectionPolicy: .earlySteal,
                useVeraMemory: true,
                zoneLayers: [.l1, .l1_5, .l2, .l3],
                useEternalMemory: true,
                escalateOnLowConfidence: true,
                escalationConfidenceThreshold: 0.6,
                escalationModel: ""
            )
        ),
        CouncilPreset(
            id: "skeptical",
            name: "Skeptical (perturb-focused)",
            nameJA: "懐疑的(摂動テスト重視)",
            description: "5 roles, deep rounds (always perturb-tests), a higher confidence bar before accepting an answer -- for questions where a wrong confident answer is costly.",
            descriptionJA: "5役割、深いラウンド(常に摂動テスト)、回答を受け入れる確信度の基準を引き上げ — 誤った自信過剰な回答のコストが高い質問向け。",
            config: CouncilOrchestrator.Config(
                roleCount: 5,
                roundsCap: 6,
                injectionPolicy: .deepRounds,
                useVeraMemory: true,
                zoneLayers: [.l2],
                useEternalMemory: true,
                escalateOnLowConfidence: true,
                escalationConfidenceThreshold: 0.75,
                escalationModel: ""
            )
        ),
    ]
}
