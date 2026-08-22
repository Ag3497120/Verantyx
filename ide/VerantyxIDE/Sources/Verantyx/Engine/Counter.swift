import Foundation

// Sendable reference-type counter for capturing mutable state in @Sendable closures.
// Used in MLX inference to track token count across concurrent tasks.
final class Counter: @unchecked Sendable {
    private var _value: Int = 0
    private let lock = NSLock()

    var value: Int {
        lock.withLock { _value }
    }

    func increment() {
        lock.withLock { _value += 1 }
    }
}
