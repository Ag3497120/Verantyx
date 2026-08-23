import Foundation

// MARK: - BrowserBridgePool
//
// verantyx-browser の並列フェッチを可能にするプロセスプール。
//
// 設計:
//   ・N 個の独立した BrowserBridge インスタンス（= 独立プロセス）を管理
//   ・checkout() で空きプロセスを取得、withBridge { } 完了後に自動返却
//   ・全プロセスが使用中の場合は空きが出るまで待機（無限待機なし・タイムアウト付き）
//   ・IDE 起動時に warmUp() を呼んで全プロセスを事前起動 → 初回 fetch の遅延ゼロ化
//   ・個別プロセスのクラッシュは自動再起動で吸収

// MARK: - Pool configuration

private let kDefaultPoolSize = 3          // 並列ブラウザプロセス数（Pre-flight の 3クエリと一致）
private let kCheckoutTimeoutSec: Double = 25.0  // checkout タイムアウト
private let kMaxSlotRestarts = 3          // スロットごとの最大再起動回数（ゾンビ振れ止まり）

// MARK: - BrowserBridgePool

actor BrowserBridgePool {

    static let shared = BrowserBridgePool(size: kDefaultPoolSize)

    // ── プール内の各スロット ─────────────────────────────────────────────────
    private var slots: [PoolSlot]
    private var waiters: [CheckedContinuation<PoolSlot, Error>] = []

    init(size: Int) {
        self.slots = (0..<size).map { PoolSlot(id: $0) }
    }

    // MARK: - Warm-up

    /// IDE 起動直後に呼ぶ。全スロットのブラウザプロセスを事前起動する。
    /// バックグラウンドで並列起動するため呼び出し元はブロックしない。
    func warmUp() {
        Task.detached(priority: .utility) {
            // Kill any orphaned verantyx-browser processes from previous crashed sessions
            let killTask = Process()
            killTask.executableURL = URL(fileURLWithPath: "/usr/bin/killall")
            killTask.arguments = ["-9", "verantyx-browser"]
            try? killTask.run()
            killTask.waitUntilExit()

            await withTaskGroup(of: Void.self) { group in
                for slot in await self.slots {
                    group.addTask {
                        do {
                            try await slot.bridge.launch(visible: true)
                        } catch {
                            // ウォームアップ失敗は警告のみ（最初の fetch 時にリトライされる）
                            print("[BrowserPool] warmUp slot \(slot.id) failed: \(error.localizedDescription)")
                        }
                    }
                }
            }
        }
    }

    // MARK: - Fetch API（外部から使う主なインターface）

    /// URL を fetch して Markdown で返す。
    /// 空きスロットがなければ待機。タイムアウト時は .fetch フォールバック。
    func fetch(_ url: String, entropy: [[Double]]? = nil, keyboardEntropy: [Double]? = nil, target: [Double]? = nil) async throws -> String {
        let slot = try await checkout()
        defer { Task { await self.returnSlot(slot) } }
        return try await slot.bridge.fetch(url, entropy: entropy, keyboardEntropy: keyboardEntropy, target: target)
    }

    /// 検索エンジンでの人間らしいタイピングとナビゲーションをシミュレートする
    func interactiveSearch(query: String, searchURL: String, entropy: [[Double]]? = nil, keyboardEntropy: [Double]? = nil, target: [Double]? = nil) async throws -> String {
        let slot = try await checkout()
        defer { Task { await self.returnSlot(slot) } }
        
        // 1. トップページを開く
        _ = try await slot.bridge.fetch("https://html.duckduckgo.com/html/", entropy: nil, keyboardEntropy: nil, target: nil)
        
        // 2. 検索ボックスにフォーカス
        _ = try await slot.bridge.evalJS("document.getElementById('search_form_input_homepage').focus();")
        
        // 3. タイピングシミュレーション
        try await slot.bridge.typeText(query, keyboardEntropy: keyboardEntropy)
        
        // 入力が終わるまで待機
        let typingDuration = Double(query.count) * 0.15 + 0.5
        try await Task.sleep(nanoseconds: UInt64(typingDuration * 1_000_000_000))
        
        // 4. 検索結果ページへ遷移（Submitイベントの代わりに直接URL遷移してHITL_DONEを待つ）
        return try await slot.bridge.fetch(searchURL, entropy: entropy, keyboardEntropy: keyboardEntropy, target: target)
    }

    /// スロット数だけ並列 URL フェッチを実行して結果を返す。
    /// 3クエリを Pre-flight で同時実行する際に使う。
    func fetchAll(_ urls: [String]) async -> [Result<String, Error>] {
        return await withTaskGroup(of: (Int, Result<String, Error>).self) { group in
            for (i, url) in urls.enumerated() {
                group.addTask {
                    do {
                        let md = try await self.fetch(url)
                        return (i, .success(md))
                    } catch {
                        return (i, .failure(error))
                    }
                }
            }
            var results = [Result<String, Error>](repeating: .failure(BrowserError.timeout), count: urls.count)
            for await (i, result) in group {
                results[i] = result
            }
            return results
        }
    }

    // MARK: - Pool mechanics

    /// 空きスロットを借りる。全スロットが使用中なら空きが出るまで待機。
    private func checkout() async throws -> PoolSlot {
        // 空きスロットを探す
        if let idx = slots.firstIndex(where: { !$0.inUse }) {
            slots[idx].inUse = true
            return slots[idx]
        }
        // 空きなし → Continuation を登録して待機
        return try await withCheckedThrowingContinuation { cont in
            waiters.append(cont)
            // タイムアウト
            Task {
                try? await Task.sleep(nanoseconds: UInt64(kCheckoutTimeoutSec * 1_000_000_000))
                await self.expireWaiter(cont: cont)
            }
        }
    }

    /// スロットを返却。次の waiter がいれば即座に渡す。
    private func returnSlot(_ slot: PoolSlot) {
        if let waiterCont = waiters.first {
            waiters.removeFirst()
            // スロットを次の waiter に直接渡す（inUse フラグは維持）
            waiterCont.resume(returning: slot)
        } else {
            // 返却: inUse をリセット
            if let idx = slots.firstIndex(where: { $0.id == slot.id }) {
                slots[idx].inUse = false
            }
        }
    }

    /// タイムアウトした waiter を除去してエラーで resume
    private func expireWaiter(cont: CheckedContinuation<PoolSlot, Error>) {
        if let idx = waiters.firstIndex(where: { ObjectIdentifier($0 as AnyObject) == ObjectIdentifier(cont as AnyObject) }) {
            waiters.remove(at: idx)
            cont.resume(throwing: BrowserError.timeout)
        }
    }

    // MARK: - Health & Status

    /// 全スロットの生存確認。クラッシュしたプロセスを再起動する（上限付き）。
    func healthCheck() async {
        for slot in slots where !slot.inUse {
            let alive = await slot.bridge.ping()
            if !alive {
                guard slot.restartCount < kMaxSlotRestarts else {
                    if !slot.isDegraded {
                        slot.isDegraded = true
                        print("[BrowserPool] slot \(slot.id) degraded after \(kMaxSlotRestarts) restarts — no longer restarting")
                    }
                    continue
                }
                slot.restartCount += 1
                print("[BrowserPool] slot \(slot.id) dead (restart \(slot.restartCount)/\(kMaxSlotRestarts)) — restarting")
                Task.detached(priority: .utility) {
                    try? await slot.bridge.launch(visible: true)
                }
            } else {
                // 元気なら degraded フラグとカウンターをリセット
                slot.restartCount = 0
                slot.isDegraded   = false
            }
        }
    }

    /// プール全体を終了する（IDE 終了時）
    func shutdown() async {
        for slot in slots {
            await slot.bridge.quit()
        }
    }

    /// デバッグ用: 各スロットの状態をログ出力
    func statusSummary() -> String {
        let parts = slots.map { "[\($0.id):\($0.inUse ? "busy" : "idle")]" }
        return "BrowserPool(\(parts.joined(separator: " ")))"
    }
}

// MARK: - PoolSlot

/// プール内の1スロット = 1 verantyx-browser プロセス
class PoolSlot {
    let id:     Int
    let bridge: BrowserBridge
    var inUse:       Bool = false
    var restartCount: Int = 0       // クラッシュ後の再起動回数
    var isDegraded:  Bool = false   // 上限到達フラグ

    init(id: Int) {
        self.id     = id
        self.bridge = BrowserBridge()
    }
}
