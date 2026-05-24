import Foundation
import os

// MARK: - GlobalTaskSupervisor
//
// 目的: どんな操作中でもデッドロックなしにシャットダウンできることを保証する。
//
// 設計原則:
//   1. 全ての長時間タスクはここに登録する
//   2. shutdown() は全タスクをキャンセルし、タイムアウト付きで待機する
//   3. MainActor を一切 await しない — shutdown は nonisolated で完結する
//   4. 各コンポーネントは isShuttingDown を確認して早期終了する

final class GlobalTaskSupervisor: @unchecked Sendable {

    static let shared = GlobalTaskSupervisor()
    private init() {}

    // ── State ────────────────────────────────────────────────────────────────

    private let _lock = NSLock()
    private var registeredTasks: [UUID: Task<Void, Never>] = [:]
    private var _isShuttingDown = false

    var isShuttingDown: Bool {
        _lock.lock(); defer { _lock.unlock() }
        return _isShuttingDown
    }

    // ── Inline lock helper (NSLock.withLock は他ファイルで定義済みの場合があるため private 実装) ──

    @inline(__always)
    @discardableResult
    private func locked<T>(_ body: () -> T) -> T {
        _lock.lock(); defer { _lock.unlock() }
        return body()
    }

    // ── Registration ─────────────────────────────────────────────────────────

    /// タスクを登録して管理下に置く。
    /// クロージャは Task.detached で起動するため MainActor をブロックしない。
    @discardableResult
    func register(priority: TaskPriority = .utility, _ body: @escaping @Sendable () async -> Void) -> Task<Void, Never> {
        let id = UUID()
        let task = Task.detached(priority: priority) { [weak self] in
            await body()
            self?.unregister(id: id)
        }
        locked { registeredTasks[id] = task }
        return task
    }

    private func unregister(id: UUID) {
        locked { registeredTasks.removeValue(forKey: id) }
    }

    // ── Shutdown ─────────────────────────────────────────────────────────────

    /// 全登録タスクをキャンセルし、最大 `timeout` 秒待つ。
    ///
    /// - Parameter timeout: 強制終了するまでの秒数 (デフォルト 2.0s)
    func shutdown(timeout: TimeInterval = 2.0) async {
        locked { _isShuttingDown = true }

        // 全タスクをキャンセル
        let tasks = locked { registeredTasks }
        for (_, task) in tasks { task.cancel() }

        // タイムアウト付きで完了を待機 (非同期 await)
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            let remaining = locked { registeredTasks.count }
            if remaining == 0 { break }
            try? await Task.sleep(nanoseconds: 50_000_000) // 50ms
        }

        let remaining = locked { registeredTasks.count }
        if remaining > 0 {
            print("[GlobalTaskSupervisor] ⚠️ \(remaining) tasks still pending after timeout — forcing exit")
        } else {
            print("[GlobalTaskSupervisor] ✅ All tasks cancelled cleanly")
        }
    }
}
