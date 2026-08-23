import Foundation
import AppKit

// MARK: - WHY Hook Installer
//
// アプリバンドル内の Resources/AgentPayload/ から
// .agents/hooks/ + git hooks をワークスペースに展開する。
//
// DMG に同梱されているため、ユーザーは何もダウンロードしない。
// onAppear で installIfNeeded() を一度だけ呼び出す。
//
// Phase 1 安定化: @MainActor を外し Task.detached から直接呼び出せるようにする。
// FileSystem I/O のみのため MainActor の依存は不要。

final class WHYHookInstaller {

    static let shared = WHYHookInstaller()
    private init() {}

    // UserDefaults キー：インストール済みバンドルバージョンを記録
    private let installedVersionKey = "verantyx.whyhook.installedVersion"

    // バンドル内リソースルート
    private var bundleAgentPayload: URL? {
        Bundle.main.url(forResource: "AgentPayload", withExtension: nil)
    }

    // ── インストール判定 ─────────────────────────────────────────────────────

    @MainActor
    func installIfNeeded(workspaceURL: URL?) {
        let currentVersion = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "0"
        let installedVersion = UserDefaults.standard.string(forKey: installedVersionKey) ?? ""

        guard installedVersion != currentVersion else { return }

        let payload = self.bundleAgentPayload
        Task.detached(priority: .utility) {
            await self.performInstall(
                workspaceURL: workspaceURL,
                version: currentVersion,
                payload: payload
            )
        }
    }

    // ── コアインストール処理 ─────────────────────────────────────────────────

    private func performInstall(workspaceURL: URL?, version: String, payload: URL?) async {
        guard let payload else {
            print("[WHYHookInstaller] AgentPayload not found in bundle")
            return
        }

        let fm = FileManager.default

        // 1. ホームディレクトリに ~/.openclaw/agents/ を展開
        let homeAgentsDir: URL
        if let customPath = UserDefaults.standard.string(forKey: "cortex_skills_path") {
            let baseAgents = URL(fileURLWithPath: customPath).deletingLastPathComponent()
            homeAgentsDir = baseAgents.appendingPathComponent("hooks", isDirectory: true)
        } else {
            homeAgentsDir = FileManager.default.homeDirectoryForCurrentUser
                .appendingPathComponent(".openclaw/agents", isDirectory: true)
        }
        do {
            try fm.createDirectory(at: homeAgentsDir, withIntermediateDirectories: true)
            try copyPayload(payload, to: homeAgentsDir, fm: fm)
            print("[WHYHookInstaller] ~/.openclaw/agents/ populated from bundle")
        } catch {
            print("[WHYHookInstaller] Home install error: \(error)")
        }

        // 2. ワークスペースに .agents/ を展開（ワークスペースが開かれている場合）
        if let ws = workspaceURL {
            let wsAgentsDir = ws.appendingPathComponent(".agents", isDirectory: true)
            do {
                try fm.createDirectory(at: wsAgentsDir, withIntermediateDirectories: true)
                try copyPayload(payload, to: wsAgentsDir, fm: fm)
                print("[WHYHookInstaller] \(ws.path)/.agents/ populated")
                // git hooks をインストール
                installGitHooks(workspaceURL: ws, agentsDir: wsAgentsDir)
            } catch {
                print("[WHYHookInstaller] Workspace install error: \(error)")
            }
        }

        // 3. MCP server.ts をバックグラウンドで起動（Node.js がある場合）
        startMCPServerIfAvailable()

        // 4. 完了記録
        await MainActor.run {
            UserDefaults.standard.set(version, forKey: installedVersionKey)
            NotificationCenter.default.post(
                name: .verantyxAgentPayloadInstalled,
                object: version
            )
        }

        print("[WHYHookInstaller] ✅ Agent payload v\(version) installed")
    }

    // ── git hooks インストール ────────────────────────────────────────────────

    private func installGitHooks(workspaceURL: URL, agentsDir: URL) {
        let gitDir = workspaceURL.appendingPathComponent(".git", isDirectory: true)
        guard FileManager.default.fileExists(atPath: gitDir.path) else { return }

        let hooksDir = gitDir.appendingPathComponent("hooks", isDirectory: true)
        let sourceHooksDir = agentsDir.appendingPathComponent("hooks", isDirectory: true)

        // post-commit: symlink
        let postCommitSrc = sourceHooksDir.appendingPathComponent("post-commit")
        let postCommitDst = hooksDir.appendingPathComponent("post-commit")
        installHook(src: postCommitSrc, dst: postCommitDst)

        // prepare-commit-msg: inline script（symlink だと git が拒否することがある）
        let prepareCommitDst = hooksDir.appendingPathComponent("prepare-commit-msg")
        let prepareSrc = sourceHooksDir.appendingPathComponent("prepare-commit-msg")
        installHook(src: prepareSrc, dst: prepareCommitDst)

        print("[WHYHookInstaller] git hooks installed in \(hooksDir.path)")
    }

    private func installHook(src: URL, dst: URL) {
        let fm = FileManager.default
        guard fm.fileExists(atPath: src.path) else { return }
        do {
            if fm.fileExists(atPath: dst.path) {
                try fm.removeItem(at: dst)
            }
            // symlink で管理（アップデート時に自動追従）
            try fm.createSymbolicLink(at: dst, withDestinationURL: src)
            // chmod +x
            try fm.setAttributes([.posixPermissions: 0o755], ofItemAtPath: src.path)
        } catch {
            // fallback: コピー
            try? fm.copyItem(at: src, to: dst)
            try? fm.setAttributes([.posixPermissions: 0o755], ofItemAtPath: dst.path)
        }
    }

    // ── ペイロードコピー（上書き対応） ───────────────────────────────────────

    private func copyPayload(_ src: URL, to dst: URL, fm: FileManager) throws {
        guard let items = try? fm.contentsOfDirectory(
            at: src,
            includingPropertiesForKeys: nil,
            options: .skipsHiddenFiles
        ) else { return }

        for item in items {
            let target = dst.appendingPathComponent(item.lastPathComponent)
            if fm.fileExists(atPath: target.path) {
                // 既存ファイルを新バージョンで上書き
                try fm.removeItem(at: target)
            }
            if (try? item.resourceValues(forKeys: [.isDirectoryKey]))?.isDirectory == true {
                try fm.createDirectory(at: target, withIntermediateDirectories: true)
                try copyPayload(item, to: target, fm: fm)
            } else {
                try fm.copyItem(at: item, to: target)
            }
        }
    }

    // ── MCP サーバー起動 ─────────────────────────────────────────────────────

    private func startMCPServerIfAvailable() {
        // Node.js が利用可能か確認
        let nodePath = findNodePath()
        guard let node = nodePath else {
            print("[WHYHookInstaller] Node.js not found — MCP server will not start")
            return
        }

        let serverScript = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".openclaw/agents/mcp-server/server.js")

        guard FileManager.default.fileExists(atPath: serverScript.path) else { return }

        let process = Process()
        process.executableURL = URL(fileURLWithPath: node)
        process.arguments = [serverScript.path]
        process.environment = ProcessInfo.processInfo.environment

        do {
            try process.run()
            print("[WHYHookInstaller] MCP server started (PID \(process.processIdentifier))")
        } catch {
            print("[WHYHookInstaller] MCP server start failed: \(error)")
        }
    }

    private func findNodePath() -> String? {
        let candidates = [
            "/usr/local/bin/node",
            "/opt/homebrew/bin/node",
            "/usr/bin/node",
            "/opt/local/bin/node",
        ]
        return candidates.first { FileManager.default.fileExists(atPath: $0) }
    }

    // ── ワークスペース変更時の再インストール ─────────────────────────────────

    @MainActor
    func reinstallHooksForWorkspace(_ workspaceURL: URL) {
        let payload = bundleAgentPayload
        Task.detached(priority: .utility) {
            guard let payload else { return }
            let wsAgentsDir = workspaceURL.appendingPathComponent(".agents", isDirectory: true)
            try? FileManager.default.createDirectory(at: wsAgentsDir, withIntermediateDirectories: true)
            try? self.copyPayload(payload, to: wsAgentsDir, fm: FileManager.default)
            self.installGitHooks(workspaceURL: workspaceURL, agentsDir: wsAgentsDir)
            print("[WHYHookInstaller] Hooks re-installed for new workspace: \(workspaceURL.path)")
        }
    }
}

// MARK: - Notification
extension Notification.Name {
    static let verantyxAgentPayloadInstalled = Notification.Name("verantyxAgentPayloadInstalled")
}
