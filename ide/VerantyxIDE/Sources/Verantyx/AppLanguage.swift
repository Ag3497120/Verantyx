import Foundation

// MARK: - AppLanguage
// Global singleton that mirrors AppState.appLanguage for use in non-EnvironmentObject contexts
// (e.g. NSTextView subclasses, NSMenuItem factories, pure structs).
// AppState updates this on every language change so it is always in sync.

final class AppLanguage {
    static let shared = AppLanguage()
    private init() {}

    /// Current language — updated by AppState whenever appLanguage changes.
    ///
    /// Seeded from the same UserDefaults key AppState reads, because
    /// AppState's `didSet` does not fire for the stored initial value: with
    /// only `= false` here, every L()-routed string rendered in English at
    /// launch regardless of the saved choice, until the user touched the
    /// language picker once.
    var isJapanese: Bool = {
        switch UserDefaults.standard.string(forKey: "app_language") {
        case "日本語":  return true
        case "English": return false
        default:        return Locale.current.language.languageCode?.identifier == "ja"
        }
    }()

    /// Translate: returns `en` when English is active, `ja` otherwise.
    func t(_ en: String, _ ja: String) -> String {
        isJapanese ? ja : en
    }
}

/// Convenience free function matching AppState.t() signature for use outside SwiftUI views.
func L(_ en: String, _ ja: String) -> String {
    AppLanguage.shared.t(en, ja)
}
