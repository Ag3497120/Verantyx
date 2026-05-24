import Foundation

// MARK: - Notification Names
// Centralized notification names used across the self-evolution system.

extension Notification.Name {

    /// Posted by SelfEvolutionEngine when CI/CD detects compile errors.
    /// userInfo keys:
    ///   "digest" — String: human-readable error summary
    ///   "errors" — [CIValidationEngine.CompileError]
    static let selfEvolutionCIError = Notification.Name("SelfEvolutionCIError")

    /// Posted after a successful CI build + binary swap.
    static let selfEvolutionRebuildSucceeded = Notification.Name("SelfEvolutionRebuildSucceeded")

    /// Posted when Safe Mode was triggered on launch.
    static let safeModeActivated = Notification.Name("SafeModeActivated")
}
