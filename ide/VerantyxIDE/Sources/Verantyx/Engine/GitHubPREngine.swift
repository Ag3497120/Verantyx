import Foundation

// MARK: - GitHubPREngine
// GitHub API client for:
//   • Forking upstream repo
//   • Pushing custom branch
//   • Creating Pull Requests
//   • Listing user's PRs
//
// Authentication: GITHUB_TOKEN in environment or stored in Keychain.

@MainActor
final class GitHubPREngine: ObservableObject {

    static let shared = GitHubPREngine()

    // MARK: - Config

    struct Config: Codable {
        var githubToken: String     = ""
        var upstreamOwner: String   = ""   // e.g. "motonishikoudai"
        var upstreamRepo:  String   = ""   // e.g. "verantyx-ide"
        var yourForkOwner: String   = ""   // your GitHub username
    }

    @Published var config: Config = Config()
    @Published var submittedPRs: [PRRecord] = []
    @Published var isSubmitting: Bool = false
    @Published var lastError: String? = nil

    // MARK: - Data models

    struct PRDraft {
        var title: String
        var body: String
        var headBranch: String   // your fork's branch
        var baseBranch: String = "main"
    }

    struct PRRecord: Identifiable, Codable {
        let id: UUID
        let title: String
        let url: String
        let branch: String
        let createdAt: Date
        var state: String   // "open" / "merged" / "closed"
    }

    // MARK: - Keychain helpers (simple UserDefaults for MVP)

    private let configKey = "github_pr_config"

    func loadConfig() {
        if let data = UserDefaults.standard.data(forKey: configKey),
           let c = try? JSONDecoder().decode(Config.self, from: data) {
            config = c
        }
        // Override from environment variable if present
        if let token = ProcessInfo.processInfo.environment["GITHUB_TOKEN"], !token.isEmpty {
            config.githubToken = token
        }
        loadPRs()
    }

    func saveConfig() {
        if let data = try? JSONEncoder().encode(config) {
            UserDefaults.standard.set(data, forKey: configKey)
        }
    }

    private let prsKey = "github_submitted_prs"

    func loadPRs() {
        if let data = UserDefaults.standard.data(forKey: prsKey),
           let prs = try? JSONDecoder().decode([PRRecord].self, from: data) {
            submittedPRs = prs
        }
    }

    private func savePRs() {
        if let data = try? JSONEncoder().encode(submittedPRs) {
            UserDefaults.standard.set(data, forKey: prsKey)
        }
    }

    // MARK: - Push branch to remote fork

    /// Push the feature branch to the user's GitHub fork via git subprocess.
    func pushBranch(_ branch: String, in repoRoot: URL) async -> Bool {
        let evo = SelfEvolutionEngine.shared
        // Ensure remote 'fork' exists
        let remoteCheck = await evo.runGit(["remote", "get-url", "fork"], in: repoRoot)
        if remoteCheck.contains("fatal") || remoteCheck.isEmpty {
            // Add fork remote
            let forkURL = "https://github.com/\(config.yourForkOwner)/\(config.upstreamRepo).git"
            _ = await evo.runGit(["remote", "add", "fork", forkURL], in: repoRoot)
        }

        // Set token in URL for push auth
        let tokenURL = "https://\(config.githubToken)@github.com/\(config.yourForkOwner)/\(config.upstreamRepo).git"
        _ = await evo.runGit(["remote", "set-url", "fork", tokenURL], in: repoRoot)

        let push = await evo.runGit(["push", "--force", "fork", "\(branch):\(branch)"], in: repoRoot)
        return !push.contains("error") && !push.contains("fatal")
    }

    // MARK: - Create Pull Request via GitHub REST API

    func submitPR(draft: PRDraft, in repoRoot: URL) async -> PRRecord? {
        isSubmitting = true
        lastError = nil
        defer { isSubmitting = false }

        // Push branch first
        let pushed = await pushBranch(draft.headBranch, in: repoRoot)
        if !pushed {
            lastError = "⚠️ ブランチのプッシュに失敗しました。トークンとフォーク設定を確認してください。"
            return nil
        }

        // GitHub API: POST /repos/{owner}/{repo}/pulls
        let apiURL = URL(string: "https://api.github.com/repos/\(config.upstreamOwner)/\(config.upstreamRepo)/pulls")!
        var req = URLRequest(url: apiURL)
        req.httpMethod = "POST"
        req.setValue("token \(config.githubToken)", forHTTPHeaderField: "Authorization")
        req.setValue("application/vnd.github+json", forHTTPHeaderField: "Accept")
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let head = "\(config.yourForkOwner):\(draft.headBranch)"
        let body: [String: Any] = [
            "title": draft.title,
            "body":  draft.body,
            "head":  head,
            "base":  draft.baseBranch,
            "draft": false
        ]
        req.httpBody = try? JSONSerialization.data(withJSONObject: body)

        do {
            let (data, resp) = try await URLSession.shared.data(for: req)
            guard let http = resp as? HTTPURLResponse, (200...201).contains(http.statusCode) else {
                let errStr = String(data: data, encoding: .utf8) ?? "Unknown"
                lastError = "GitHub API エラー: \(errStr.prefix(200))"
                return nil
            }
            let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] ?? [:]
            let prURL = json["html_url"] as? String ?? ""
            let record = PRRecord(
                id: UUID(), title: draft.title, url: prURL,
                branch: draft.headBranch, createdAt: Date(), state: "open"
            )
            submittedPRs.insert(record, at: 0)
            savePRs()
            return record
        } catch {
            lastError = error.localizedDescription
            return nil
        }
    }

    // MARK: - AI-generated PR body

    func generatePRBody(featureName: String, patches: [SelfEvolutionEngine.FilePatch]) -> PRDraft {
        let fileList = patches.map { "- `\($0.relativePath)`" }.joined(separator: "\n")
        let body = """
        ## 概要 / Summary

        このPRは Verantyx IDE の **\(featureName)** 機能を追加します。

        AI Priority モードにより、VerantyxAgent がソースコードを自動生成・修正しました。

        ## 変更ファイル / Changed Files

        \(fileList)

        ## テスト方法 / How to Test

        1. このブランチをチェックアウト → `git checkout \(SelfEvolutionEngine.shared.customBranch)`
        2. `xcodebuild` でビルド
        3. アプリを起動して機能を確認

        ## 生成日時 / Generated At
        \(Date().formatted(date: .long, time: .standard))

        ---
        *このPRは Verantyx IDE の Self-Evolution 機能によって自動生成されました。*
        """

        return PRDraft(
            title: "feat: \(featureName) — VerantyxAgent自動生成",
            body: body,
            headBranch: SelfEvolutionEngine.shared.customBranch
        )
    }
}
