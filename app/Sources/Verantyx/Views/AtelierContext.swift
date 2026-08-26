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
}
