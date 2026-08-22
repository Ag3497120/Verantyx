import Foundation
import os

// MARK: - MCPBridgeLauncher
//
// Automatically starts the Verantyx MCP Bridge (Node.js, port 5420) at IDE launch.
// The bridge exposes /skills/version and /health used by MCPSkillSync.
//
// Strategy:
//   1. Locate `node` binary via PATH resolution.
//   2. Find the server entry point: `<project>/src/verantyx/mcp/server.ts`
//   3. Launch using `node --import tsx <server.ts>` from the project root.
//   4. Monitor the process — restart on crash with exponential backoff (3s → 6s → 12s → cap 60s).
//   5. Verify the bridge is healthy via GET /health before reporting `isRunning = true`.
//   6. On app quit, terminate the child process.
//
// Usage (VerantyxApp.swift):
//   MCPBridgeLauncher.shared.start()          // call in .onAppear
//   MCPBridgeLauncher.shared.stop()           // call in applicationShouldTerminate

@MainActor
final class MCPBridgeLauncher: ObservableObject {

    static let shared = MCPBridgeLauncher()

    // ── Published state ────────────────────────────────────────────────────────
    @Published private(set) var isRunning: Bool = false
    @Published private(set) var launchError: String? = nil

    // ── Constants ─────────────────────────────────────────────────────────────
    private let bridgePort     = 5420
    private let maxBackoff:  TimeInterval = 60
    private let maxCrashes   = 5    // ← これを超えたら再起動を停止（ゾンビ蓄積防止）
    private let healthURL      = URL(string: "http://127.0.0.1:5420/health")!
    private let healthTimeout:TimeInterval = 3.0

    // ── Internal state ────────────────────────────────────────────────────────
    private var process: Process?
    private var monitorTask: Task<Void, Never>?
    private var consecutiveCrashes = 0
    private var didStop = false

    /// EADDRINUSE 対策: 起動前に port 5420 を保持しているプロセスを kill する。
    /// ⚠️ nonisolated: waitUntilExit() + Thread.sleep() を含むため
    ///    必ずバックグラウンドスレッド（Task.detached）から呼ぶこと。
    nonisolated private func killZombieOnPort() {
        let lsof = Process()
        lsof.executableURL = URL(fileURLWithPath: "/usr/sbin/lsof")
        lsof.arguments = ["-ti", "tcp:\(bridgePort)"]
        let pipe = Pipe()
        lsof.standardOutput = pipe
        lsof.standardError  = FileHandle.nullDevice
        try? lsof.run()
        let out = String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
        lsof.waitUntilExit()
        for pidStr in out.components(separatedBy: .newlines) {
            let trimmed = pidStr.trimmingCharacters(in: .whitespaces)
            guard let pid = Int32(trimmed), pid > 0 else { continue }
            // EADDRINUSE対策: 自分自身をキルしないようにする
            if pid == ProcessInfo.processInfo.processIdentifier { continue }
            kill(pid, SIGTERM)
            print("[MCPBridgeLauncher] 🔪 Killed zombie PID \(pid) holding port \(bridgePort)")
        }
        Thread.sleep(forTimeInterval: 0.3)  // ← バックグラウンドのため安全
    }

    private init() {}

    // MARK: - Public API

    func start(onPortCleared: @MainActor @Sendable @escaping () -> Void = {}) {
        guard monitorTask == nil else {
            print("[MCPBridgeLauncher] ⚠️ Already running — ignoring duplicate start()")
            return
        }
        didStop = false
        consecutiveCrashes = 0
        launchError = nil
        // アプリ起動時に残留ゾンビを一括削除（Xcodeデバッグ再起動対策）
        Task.detached(priority: .utility) { [weak self] in
            self?.killZombieOnPort()
            await onPortCleared()
        }
        // ⚠️ nonisolated Task: runLoop は MainActor を専有しない
        monitorTask = Task.detached(priority: .utility) { [weak self] in
            await self?.runLoop()
        }
    }

    func stop() {
        didStop = true
        monitorTask?.cancel()
        monitorTask = nil
    }

    // MARK: - Run Loop
    // ⚠️ nonisolated: MainActor を専有しない。Task.detached で起動すること。

    nonisolated private func runLoop() async {
        while !Task.isCancelled {
            let shouldStop = await MainActor.run { self.didStop }
            if shouldStop { return }

            // クラッシュ上限: maxCrashes を超えたら諦める（ゾンビ防止）
            let crashes = await MainActor.run { self.consecutiveCrashes }
            if crashes >= maxCrashes {
                let msg = "MCP Bridge failed \(maxCrashes) times. Giving up to prevent zombie accumulation."
                print("[MCPBridgeLauncher] ❌ \(msg)")
                await MainActor.run { self.launchError = msg }
                return
            }

            // Backoff before respawn (skip on first launch)
            if crashes > 0 {
                let backoff = min(3.0 * pow(2.0, Double(crashes - 1)), maxBackoff)
                print("[MCPBridgeLauncher] Crash #\(crashes)/\(maxCrashes) — respawning in \(Int(backoff))s")
                // キャンセル可能スリープ
                try? await Task.sleep(nanoseconds: UInt64(backoff * 1_000_000_000))
                if Task.isCancelled { return }
            }

            await launch()
        }
    }

    // MARK: - Launch

    /// ⚠️ nonisolated: killZombieOnPort()/findNode() などブロッキング呼び出しを含むため
    ///    runLoop() から Task.detached 経由で呼ばれ、MainActor をブロックしない。
    nonisolated private func launch() async {
        guard let (nodeBin, serverScript, projectRoot) = await resolvePaths() else {
            await MainActor.run {
                launchError = "Cannot locate node binary or MCP server script."
            }
            print("[MCPBridgeLauncher] ❌ Cannot locate node binary or MCP server script.")
            await MainActor.run { didStop = true }
            return
        }

        // ─── 既存ゾンビを kill してから起動する ─────────────────────────────
        killZombieOnPort()

        let proc = Process()
        proc.executableURL = nodeBin

        // tsx をローカルの node_modules から使う
        let tsxBin = projectRoot
            .appendingPathComponent("node_modules/.bin/tsx")
        let usesTsx = FileManager.default.fileExists(atPath: tsxBin.path)

        if usesTsx {
            proc.arguments = ["--import", "tsx", serverScript.path]
        } else {
            proc.arguments = [serverScript.path]
        }

        proc.currentDirectoryURL = projectRoot
        // buildEnv はピュア計算なので nonisolated コピーで処理
        let nodeDir = nodeBin.deletingLastPathComponent().path
        var env = ProcessInfo.processInfo.environment
        env["PATH"] = "\(nodeDir):\(env["PATH"] ?? "/usr/local/bin:/usr/bin:/bin")"
        env["NODE_NO_WARNINGS"] = "1"
        proc.environment = env

        // Pipe stderr so we can log it; stdout goes to /dev/null (stdio MCP path)
        let errPipe = Pipe()
        proc.standardError  = errPipe
        proc.standardOutput = FileHandle.nullDevice

        do {
            try proc.run()
        } catch {
            let msg = "Failed to launch MCP bridge: \(error.localizedDescription)"
            await MainActor.run {
                launchError = msg
                consecutiveCrashes += 1
            }
            print("[MCPBridgeLauncher] ❌ \(msg)")
            return
        }


        await MainActor.run { process = proc }
        print("[MCPBridgeLauncher] ✅ Launched PID \(proc.processIdentifier) (tsx=\(usesTsx))")

        // Pipe stderr → Console asynchronously
        Task.detached(priority: .utility) {
            let handle = errPipe.fileHandleForReading
            while true {
                let data = handle.availableData
                if data.isEmpty { break }
                if let line = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .newlines),
                   !line.isEmpty {
                    print("[MCPBridge] \(line)")
                }
            }
        }

        // Wait for /health to come up (up to 10s)
        let healthy = await waitForHealth()
        if healthy {
            await MainActor.run {
                isRunning     = true
                launchError   = nil
                consecutiveCrashes = 0
            }
            print("[MCPBridgeLauncher] 🌐 Bridge healthy on port \(bridgePort)")
        } else {
            print("[MCPBridgeLauncher] ⚠️ Bridge did not become healthy within 10s")
        }

        // ─── Block until process exits ─────────────────────────────────────────
        let pid = proc.processIdentifier
        // withTaskCancellationHandler: stop() でタスクがキャンセルされたら即座に resume。
        // 絶対に resume() が呼ばれないままブロックしない = "停止デッドロック" 根絶。
        await withTaskCancellationHandler(
            operation: {
                await withCheckedContinuation { (cont: CheckedContinuation<Void, Never>) in
                    let resumed = _AtomicFlag()
                    proc.terminationHandler = { _ in
                        if resumed.trySet() { cont.resume() }
                    }
                    // プロセスが handler 登録前に終了していたケース
                    if !proc.isRunning {
                        if resumed.trySet() { cont.resume() }
                    }
                }
            },
            onCancel: {
                // タスクキャンセル時: libc kill でプロセスを強制終了 (Process.terminateはスレッドセーフではないため使用禁止)
                if pid > 0 {
                    kill(pid, SIGTERM)
                }
            }
        )

        await MainActor.run {
            isRunning = false
            process   = nil
            consecutiveCrashes += 1
        }
        print("[MCPBridgeLauncher] ⚠️ Bridge exited (code \(proc.terminationStatus))")
    }

    // MARK: - Health check

    private func waitForHealth() async -> Bool {
        let deadline = Date().addingTimeInterval(10)
        let session  = URLSession(configuration: {
            let c = URLSessionConfiguration.ephemeral
            c.timeoutIntervalForRequest  = healthTimeout
            c.timeoutIntervalForResource = healthTimeout
            c.waitsForConnectivity       = false
            return c
        }())

        while Date() < deadline {
            try? await Task.sleep(nanoseconds: 500_000_000) // 0.5s
            if Task.isCancelled { return false }
            if let (_, resp) = try? await session.data(from: healthURL),
               (resp as? HTTPURLResponse)?.statusCode == 200 {
                return true
            }
        }
        return false
    }

    // MARK: - Path resolution

    /// Returns (nodeBinary, serverScript, projectRoot) or nil if not found.
    nonisolated private func resolvePaths() async -> (URL, URL, URL)? {
        // 1. node binary
        guard let nodeBin = await findNode() else { return nil }

        let wsPath = await MainActor.run { AppState.shared?.cortexWorkspacePath ?? AppState.shared?.workspaceURL?.path }
        let verantyxCLI: URL
        if let ws = wsPath {
            let u = URL(fileURLWithPath: ws)
            verantyxCLI = u.lastPathComponent == "VerantyxIDE" ? u.deletingLastPathComponent() : u
        } else {
            verantyxCLI = URL(fileURLWithPath: "/tmp/verantyx-cli")
        }

        // 2. server.ts 候補 (実際に存在するパス順)
        let scriptCandidates: [(script: String, root: URL)] = [
            // .openclaw-release
            (".openclaw-release/src/verantyx/mcp/server.ts", verantyxCLI),
            // cortex
            ("cortex/src/verantyx/mcp/server.ts", verantyxCLI),
            ("cortex/src/mcp/server.ts",          verantyxCLI),
            // src 直下
            ("src/verantyx/mcp/server.ts",                  verantyxCLI),
        ]

        for (rel, root) in scriptCandidates {
            let scriptURL = root.appendingPathComponent(rel)
            if FileManager.default.fileExists(atPath: scriptURL.path) {
                // projectRoot は server.ts が属するパッケージのルート
                let pkgRoot = scriptURL
                    .deletingLastPathComponent()   // mcp/
                    .deletingLastPathComponent()   // verantyx/ or src/
                    .deletingLastPathComponent()   // src/
                // node_modules を持つディレクトリを探す
                let rootWithModules = [pkgRoot, root].first {
                    FileManager.default.fileExists(atPath: $0.appendingPathComponent("node_modules").path)
                } ?? root
                print("[MCPBridgeLauncher] ✅ Found server.ts at \(scriptURL.path)")
                return (nodeBin, scriptURL, rootWithModules)
            }
        }
        print("[MCPBridgeLauncher] ❌ server.ts not found in any candidate path")
        return nil
    }

    /// ⚠️ nonisolated: proc.waitUntilExit() を含むため
    /// ⚠️ nonisolated: proc.waitUntilExit() を含むため
    ///    必ずバックグラウンドスレッド（Task.detached）から呼ぶこと。
    nonisolated private func findNode() async -> URL? {
        let home = NSHomeDirectory()
        // Fast path: known Homebrew / nvm / system locations
        let knownPaths = [
            "/opt/homebrew/bin/node",
            "/usr/local/bin/node",
            "/usr/bin/node",
            "\(home)/.nvm/versions/node/default/bin/node",
        ]
        for p in knownPaths {
            if FileManager.default.fileExists(atPath: p) {
                return URL(fileURLWithPath: p)
            }
        }
        // nvm: スキャンして最新バージョンを使う
        let nvmVersionsDir = URL(fileURLWithPath: "\(home)/.nvm/versions/node")
        if let versions = try? FileManager.default.contentsOfDirectory(
            at: nvmVersionsDir, includingPropertiesForKeys: nil
        ).sorted(by: { $0.lastPathComponent > $1.lastPathComponent }) {
            for version in versions {
                let nodeBin = version.appendingPathComponent("bin/node")
                if FileManager.default.fileExists(atPath: nodeBin.path) {
                    print("[MCPBridgeLauncher] 🔍 Found node via nvm: \(nodeBin.path)")
                    return nodeBin
                }
            }
        }
        // Fallback: ask `which node`
        let proc  = Process()
        let pipe  = Pipe()
        proc.executableURL    = URL(fileURLWithPath: "/usr/bin/env")
        proc.arguments        = ["bash", "-lc", "which node"]
        proc.standardOutput   = pipe
        proc.standardError    = FileHandle.nullDevice
        try? proc.run()
        let output = String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8)?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        proc.waitUntilExit()
        if !output.isEmpty {
            print("[MCPBridgeLauncher] 🔍 Found node via env: \(output)")
            return URL(fileURLWithPath: output)
        }
        return nil
    }

    private func buildEnv(nodeBin: URL) -> [String: String] {
        var env = ProcessInfo.processInfo.environment
        // Ensure PATH includes the directory containing node
        let nodeDir = nodeBin.deletingLastPathComponent().path
        let existingPath = env["PATH"] ?? "/usr/local/bin:/usr/bin:/bin"
        env["PATH"] = "\(nodeDir):\(existingPath)"
        // tsx needs this to resolve TypeScript at runtime
        env["NODE_NO_WARNINGS"] = "1"
        return env
    }

}

// MARK: - _AtomicFlag (internal helper)
//
// withCheckedContinuation で resume() が2回呼ばれることを防ぐための
// スレッドセーフな one-shot フラグ。
// - terminationHandler と「既に終了済み」ガードが両方発火するレースを防ぐ。

final class _AtomicFlag: @unchecked Sendable {
    private var _lock = os_unfair_lock()
    private var _set  = false

    /// 初回呼び出しのみ true を返す。以降は false。
    func trySet() -> Bool {
        os_unfair_lock_lock(&_lock)
        defer { os_unfair_lock_unlock(&_lock) }
        guard !_set else { return false }
        _set = true
        return true
    }
}
