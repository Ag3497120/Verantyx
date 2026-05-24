import Foundation

// MARK: - AppLanguage
// Global singleton that mirrors AppState.appLanguage for use in non-EnvironmentObject contexts
// (e.g. NSTextView subclasses, NSMenuItem factories, pure structs).
// AppState updates this on every language change so it is always in sync.

final class AppLanguage {
    static let shared = AppLanguage()
    private init() {}

    /// Current language — updated by AppState whenever appLanguage changes.
    var isJapanese: Bool = false

    /// Translate: returns `en` when English is active, `ja` otherwise.
    func t(_ en: String, _ ja: String) -> String {
        isJapanese ? ja : en
    }
}

/// Convenience free function matching AppState.t() signature for use outside SwiftUI views.
func L(_ en: String, _ ja: String) -> String {
    AppLanguage.shared.t(en, ja)
}
