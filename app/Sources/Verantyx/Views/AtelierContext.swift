import Foundation

/// **What garment is open right now**, readable from outside AtelierView's
/// own subtree.
///
/// `AtelierModel` already tracks this (`projectName`, read from
/// `garment_spec`'s "title"), but it is a per-screen `@StateObject`, not a
/// singleton — nothing else is meant to reach into it. The shell's composer
/// (`UnifiedComposerView`) still needs the name, for the scope chip that
/// says which garment a typed instruction would apply to: showing that
/// BEFORE typing is the whole point of the redesign (服飾用のチャット入力欄が
/// 何を指すか、打つ前にわかるように). Rather than give the composer a second
/// ledger reader, `AtelierModel.load()` publishes the title here once, and
/// this is the only thing that writes it.
///
/// Empty means "not loaded yet", not "this garment has no name" — callers
/// should show a neutral placeholder for empty, not a blank chip.
@MainActor
final class AtelierContext: ObservableObject {
    static let shared = AtelierContext()
    private init() {}

    @Published var projectName: String = ""

    /// **Which step the workbench is showing right now** — mirrored from
    /// `AtelierModel.step` on every change (see that property's own
    /// comment). Added for UI B (「チャット画面プラス服飾ui」): the chat
    /// pane beside the workbench needs to say "where am I" without a
    /// reference to AtelierView's private model. Read-only by convention
    /// — the one writer is `AtelierModel.step`'s `didSet`. To ask the
    /// workbench to MOVE, use `AtelierNavigator.shared.go(to:)` instead
    /// of setting this directly; setting it here would only relabel the
    /// mirror, not the model it mirrors.
    @Published var step: String = "Structure"
}
