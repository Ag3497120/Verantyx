import Foundation

// MARK: - NSLock Extension (Shared Utility)
//
// JCrossCodeTranspiler, JCrossZAxisVault, JCrossIRVault で共通使用。
// このファイルでのみ定義する。他のファイルの private extension は削除済み。

extension NSLock {
    /// throwing クロージャをロック保護して実行する。
    @discardableResult
    func withLock<T>(_ body: () throws -> T) rethrows -> T {
        lock()
        defer { unlock() }
        return try body()
    }
}
