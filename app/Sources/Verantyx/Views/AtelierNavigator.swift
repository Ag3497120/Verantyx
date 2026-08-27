import Foundation

/// **Making `AtelierModel.step` settable from outside is most of the
/// work** — the owner's brief, verbatim, for UI B. AtelierView owns its
/// `AtelierModel` as a private `@StateObject`; nothing outside that
/// subtree may reach in and assign `m.step` directly (`AtelierContext`'s
/// own doc comment already turned down doing that for `projectName`, for
/// the same reason). This is the write side of the same shape of fix:
/// a tiny shared channel AtelierView opts into reading, not a second
/// copy of the model and not a loosened access level on the real one.
///
/// One request at a time, carrying a rising `token` so a request for the
/// SAME step twice in a row still fires `onChange` — SwiftUI only reacts
/// to a value that actually changes, and "go to Materials" twice in a
/// row (the person asks again after wandering off) must not be a no-op.
@MainActor
final class AtelierNavigator: ObservableObject {
    static let shared = AtelierNavigator()
    private init() {}

    struct Request: Equatable {
        let step: String
        let token: Int
    }

    @Published private(set) var request: Request?
    private var nextToken = 0

    /// Called only after a destination has already been resolved against
    /// the real engine or the step list — never with a guess. See
    /// `AtelierChatRouter`.
    func go(to step: String) {
        nextToken += 1
        request = Request(step: step, token: nextToken)
    }
}
