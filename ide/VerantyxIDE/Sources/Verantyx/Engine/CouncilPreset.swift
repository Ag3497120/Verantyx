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

    /// Derived from `ArchitectureTemplate.builtins` so there is one list of
    /// templates, not two that can drift. `VectorLabView` consumes this
    /// unchanged; the richer per-layer/model/hardware fields live on
    /// `ArchitectureTemplate` and are what the setup planner reasons about.
    static var builtins: [CouncilPreset] {
        ArchitectureTemplate.builtins.map(\.asCouncilPreset)
    }
}
