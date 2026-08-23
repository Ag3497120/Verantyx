import Foundation
import SwiftUI
import Combine

// MARK: - SelfEvolutionEngine
//
// The engine that gives Verantyx IDE "self-consciousness":
//   1. Indexes its own source code into JCross memory nodes.
//   2. Applies AI-generated patches to files.
//   3. Rebuilds itself using xcodebuild.
//   4. Hot-swaps the new binary (restart into evolved self).
//   5. Maintains a stable backup for safe-mode recovery.
//
// Architecture:
//   SourceIndex   — per-file Swift code snapshot + summary
//   BuildRunner   — xcodebuild subprocess with live log streaming
//   SafeMode      — stable binary backup / restore

@MainActor
final class SelfEvolutionEngine: ObservableObject {

    static let shared = SelfEvolutionEngine()

    // MARK: - Published state

    @Published var sourceNodes: [SourceNode] = []
    @Published var isIndexing: Bool = false
    @Published var buildState: BuildState = .idle
    @Published var buildLog: String = ""
    @Published var pendingPatches: [FilePatch] = []
    @Published var customBranch: String = ""
    @Published var appliedFeatures: [AppliedFeature] = []

    // MARK: - Paths

    /// Root of the IDE source repo — detected lazily with workspace hint + UserDefaults fallback.
    private var _repoRoot: URL? = nil

    private var safeDir: URL {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Verantyx/safe", isDirectory: true)
    }

    // MARK: - Data models

    struct SourceNode: Identifiable {
        let id: UUID
        let relativePath: String   // e.g. "Sources/Verantyx/Views/AgentChatView.swift"
        let content: String
        let summary: String        // 1-line AI-generated summary (or heuristic)
        var jcrossFileName: String? // linked JCross node filename if saved
        var lastModified: Date
    }

    struct FilePatch: Identifiable {
        let id = UUID()
        let relativePath: String
        let originalContent: String
        let patchedContent:  String
        var status: PatchStatus = .pending

        enum PatchStatus { case pending, applied, failed(String) }

        var diff: String {
            // Compute a simple unified-diff for display
            let origLines = originalContent.components(separatedBy: "\n")
            let newLines  = patchedContent.components(separatedBy: "\n")
            var result = "--- \(relativePath)\n+++ \(relativePath)\n"
            // Ultra-simple: show changed lines only (full diff via DiffEngine in practice)
            let maxLen = max(origLines.count, newLines.count)
            for i in 0..<min(maxLen, 200) {
                let o = i < origLines.count ? origLines[i] : ""
                let n = i < newLines.count  ? newLines[i] : ""
                if o != n {
                    if !o.isEmpty { result += "-\(o)\n" }
                    if !n.isEmpty { result += "+\(n)\n" }
                }
            }
            return result
        }
    }

    struct AppliedFeature: Identifiable, Codable {
        let id: UUID
        var name: String
        var description: String
        var branchName: String
        var appliedAt: Date
        var prURL: String?
    }

    enum BuildState: Equatable {
        case idle
        case building(progress: Double)
        case succeeded(binaryURL: URL)
        case failed(log: String)
        case safeMode
    }

    // MARK: - Source Indexing

    /// Call to hint the engine with a known workspace URL (e.g. from open folder).
    /// This improves repoRoot detection when bundle path is in DerivedData.
    func setWorkspaceHint(_ url: URL) {
        // Walk up from workspace to find xcodeproj / Package.swift
        if let root = walkUpToRepoRoot(from: url) {
            _repoRoot = root
            UserDefaults.standard.set(root.path, forKey: "evo_last_repo_root")
        }
    }

    /// Index all Swift source files into in-memory SourceNodes.
    func indexSourceTree() async {
        // Ensure repoRoot is resolved (triggers detection + UserDefaults fallback)
        guard let root = repoRoot else {
            buildLog = "❌ リポジトリが見つかりません。ワークスペースフォルダを開いてください (Cmd+Shift+O)"
            return
        }

        isIndexing = true
        buildLog = "🔍 インデックス中: \(root.lastPathComponent)…"

        let fm = FileManager.default
        guard let enumerator = fm.enumerator(
            at: root,
            includingPropertiesForKeys: [.contentModificationDateKey],
            options: [.skipsHiddenFiles]
        ) else {
            isIndexing = false
            return
        }

        var nodes: [SourceNode] = []
        let swiftFiles = enumerator.compactMap { $0 as? URL }
            .filter {
                $0.pathExtension == "swift"
                && !$0.path.contains("/.build/")
                && !$0.path.contains("/DerivedData/")
                && !$0.path.contains("/ci-validate-")
            }

        for url in swiftFiles {
            guard let content = try? String(contentsOf: url, encoding: .utf8) else { continue }
            let rel = url.path.replacingOccurrences(of: root.path + "/", with: "")
            let modDate = (try? url.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? Date()
            let summary = heuristicSummary(of: content, filename: url.lastPathComponent)
            nodes.append(SourceNode(id: UUID(), relativePath: rel, content: content,
                                    summary: summary, jcrossFileName: nil, lastModified: modDate))
        }

        sourceNodes = nodes.sorted { $0.relativePath < $1.relativePath }
        isIndexing = false
        buildLog = "✅ インデックス完了: \(nodes.count) ファイル (\(root.lastPathComponent))"
    }

    /// Simple heuristic summary from Swift source (no AI needed for indexing).
    private func heuristicSummary(of content: String, filename: String) -> String {
        let lines = content.components(separatedBy: "\n")
        // Find the first meaningful comment or struct/class/enum declaration
        for line in lines.prefix(20) {
            let t = line.trimmingCharacters(in: .whitespaces)
            if t.hasPrefix("//") && t.count > 6 && !t.hasPrefix("//  Created") {
                return t.dropFirst(2).trimmingCharacters(in: .whitespaces)
            }
            if t.hasPrefix("struct ") || t.hasPrefix("class ") || t.hasPrefix("enum ") || t.hasPrefix("actor ") {
                return "\(filename): \(t.prefix(80))"
            }
        }
        return filename
    }

    // MARK: - Patch Application

    /// Register a set of patches (from AI diff generation).
    func registerPatch(for relativePath: String, newContent: String) {
        guard let node = sourceNodes.first(where: { $0.relativePath == relativePath }) else {
            return
        }
        // ── Sanitize: strip Markdown code fences AI sometimes adds by mistake ──
        // e.g. AI writes ```swift\n...\n``` but we need only the inner content
        let sanitized = Self.stripCodeFences(from: newContent)

        let patch = FilePatch(relativePath: relativePath,
                              originalContent: node.content,
                              patchedContent: sanitized)
        pendingPatches.removeAll { $0.relativePath == relativePath }
        pendingPatches.append(patch)
    }

    /// Strip leading/trailing Markdown code fences from AI-generated content.
    /// Handles: ```swift\n...\n```, ```\n...\n```, and lone ``` at line start.
    static func stripCodeFences(from content: String) -> String {
        var lines = content.components(separatedBy: "\n")

        // Remove leading fence line (```swift, ```Swift, ```, etc.)
        if let first = lines.first,
           first.trimmingCharacters(in: .whitespaces).hasPrefix("```") {
            lines.removeFirst()
        }

        // Remove trailing fence line (```)
        if let last = lines.last,
           last.trimmingCharacters(in: .whitespaces) == "```" {
            lines.removeLast()
        }

        return lines.joined(separator: "\n")
    }

    /// Write all pending patches to disk (in-place edit of source files).
    func applyAllPatches() throws {
        guard let root = repoRoot else { throw EvoError.noRepoRoot }
        for i in pendingPatches.indices {
            let patch = pendingPatches[i]
            let url = root.appendingPathComponent(patch.relativePath)
            do {
                try patch.patchedContent.write(to: url, atomically: true, encoding: .utf8)
                pendingPatches[i].status = .applied
                // Update in-memory node
                if let ni = sourceNodes.firstIndex(where: { $0.relativePath == patch.relativePath }) {
                    sourceNodes[ni] = SourceNode(
                        id: sourceNodes[ni].id,
                        relativePath: patch.relativePath,
                        content: patch.patchedContent,
                        summary: heuristicSummary(of: patch.patchedContent, filename: URL(fileURLWithPath: patch.relativePath).lastPathComponent),
                        jcrossFileName: sourceNodes[ni].jcrossFileName,
                        lastModified: Date()
                    )
                }
            } catch {
                pendingPatches[i].status = .failed(error.localizedDescription)
                throw error
            }
        }
    }

    // MARK: - Rebuild

    // CI mode: validated route (default). Set to false to bypass.
    var ciEnabled: Bool = true

    /// Apply patches → CI validation loop → commit → xcodebuild → hot-swap.
    func applyPatchesAndRebuild(featureName: String, gitCommitMessage: String) async {
        guard let root = repoRoot else {
            buildState = .failed(log: "❌ Repo root not found")
            return
        }

        buildState = .building(progress: 0.03)
        appendLog("⚡ 自己再構築を開始: \(featureName)")

        // 1. Back up stable binary FIRST (always, before any mutation)
        backupStableBinary()

        // ── Phase A: 仮想 CI/CD ────────────────────────────────────────
        if ciEnabled && !pendingPatches.isEmpty {
            appendLog("\n🔬 仮想CI/CD を起動 (最大 \(CIValidationEngine.shared.MAX_RETRIES) 回)…")
            buildState = .building(progress: 0.08)

            let scheme = detectXcodeScheme(in: root) ?? "Verantyx"
            let ci = CIValidationEngine.shared

            let ciPassed = await ci.runValidationLoop(
                repoRoot: root,
                scheme: scheme,
                patches: pendingPatches
            ) { [weak self] errors -> [FilePatch] in
                // AI auto-retry: send error digest back through AppState → AgentLoop
                guard let self else { return [] }
                let digest = ci.buildErrorDigest(errors: errors, patches: self.pendingPatches)
                appendLog("🤖 AI にエラーを送信:\n\(digest.prefix(400))")

                // Post error digest as a chat message → triggers next AI response
                await MainActor.run {
                    NotificationCenter.default.post(
                        name: .selfEvolutionCIError,
                        object: nil,
                        userInfo: ["digest": digest, "errors": errors]
                    )
                }

                // Wait up to 90s for AI to produce new patches
                var waited = 0
                let initialCount = self.pendingPatches.count
                while waited < 90 {
                    try? await Task.sleep(nanoseconds: 2_000_000_000) // 2s
                    waited += 2
                    if self.pendingPatches.count != initialCount { break }
                }
                return self.pendingPatches
            }

            // Relay CI log to our build log
            appendLog(ci.ciLog)

            if !ciPassed {
                buildState = .failed(log: buildLog + "\n❌ CI/CD 失敗 — パッチは破棄されました")
                appendLog("🛡 安定版バイナリを復元します")
                restoreStableBinary()
                return
            }

            appendLog("✅ CI/CD 通過 — メインビルドを開始します")
        }

        buildState = .building(progress: 0.20)

        // ── Phase B: Apply patches (CI already wrote them on its branch) ──
        do {
            try applyAllPatches()
            appendLog("✅ パッチ適用完了 (\(pendingPatches.count) ファイル)")
        } catch {
            buildState = .failed(log: buildLog + "\n❌ パッチ適用失敗: \(error)")
            return
        }

        buildState = .building(progress: 0.30)

        // ── Phase C: git commit on feature branch ─────────────────────
        let safeName = featureName.lowercased().replacingOccurrences(of: " ", with: "-").prefix(40)
        let branch = "custom-features/\(safeName)-\(Int(Date().timeIntervalSince1970))"
        customBranch = branch

        let gitBranch = await runGit(["checkout", "-b", branch], in: root)
        appendLog("🌿 ブランチ: \(branch)\n\(gitBranch)")
        let gitAdd = await runGit(["add", "-A"], in: root)
        appendLog("📂 git add: \(gitAdd)")
        let gitCommit = await runGit(
            ["commit", "-m", gitCommitMessage.isEmpty ? "feat: \(featureName)" : gitCommitMessage],
            in: root
        )
        appendLog("💾 git commit: \(gitCommit)")

        buildState = .building(progress: 0.40)

        // ── Phase D: Release build ─────────────────────────────────────
        let scheme = detectXcodeScheme(in: root) ?? "Verantyx"
        let derivedData = safeDir.path.appending("/DerivedData")
        appendLog("🔨 xcodebuild -scheme \(scheme) (Release)…")

        let buildSuccess = await runXcodeBuild(in: root, scheme: scheme, derivedDataPath: derivedData)

        if buildSuccess {
            buildState = .building(progress: 0.95)
            appendLog("✅ ビルド成功！")

            let newBinary = findBuiltApp(in: derivedData, scheme: scheme)
            if let bin = newBinary {
                buildState = .succeeded(binaryURL: bin)
                appendLog("🚀 新バイナリ: \(bin.lastPathComponent)")

                let feature = AppliedFeature(
                    id: UUID(), name: featureName, description: gitCommitMessage,
                    branchName: branch, appliedAt: Date(), prURL: nil
                )
                appliedFeatures.insert(feature, at: 0)
                saveAppliedFeatures()
                pendingPatches.removeAll()
            } else {
                buildState = .failed(log: buildLog + "\n⚠️ バイナリが見つかりませんでした")
            }
        } else {
            buildState = .failed(log: buildLog)
            appendLog("❌ Release ビルド失敗 — セーフモードへ")
            restoreStableBinary()
        }
    }

    /// Launch the newly built binary (user must approve this call).
    func launchNewBinary() {
        guard case .succeeded(let url) = buildState else { return }
        NSWorkspace.shared.open(url)
        // Save JCross state then exit current instance
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
            NSApp.terminate(nil)
        }
    }

    // MARK: - Safe Mode

    private func backupStableBinary() {
        guard let appURL = Bundle.main.executableURL?.deletingLastPathComponent()
                                .deletingLastPathComponent() // .app
        else { return }
        try? FileManager.default.createDirectory(at: safeDir, withIntermediateDirectories: true)
        let dest = safeDir.appendingPathComponent("stable.app")
        try? FileManager.default.removeItem(at: dest)
        try? FileManager.default.copyItem(at: appURL, to: dest)
        appendLog("🛡 安定版バックアップ完了")
    }

    func restoreStableBinary() {
        let stable = safeDir.appendingPathComponent("stable.app")
        guard FileManager.default.fileExists(atPath: stable.path) else {
            buildState = .safeMode
            return
        }
        NSWorkspace.shared.open(stable)
        buildState = .safeMode
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) { NSApp.terminate(nil) }
    }

    // MARK: - Git helpers

    @discardableResult
    func runGit(_ args: [String], in directory: URL) async -> String {
        await withCheckedContinuation { cont in
            DispatchQueue.global(qos: .userInitiated).async {
                let p = Process()
                p.executableURL = URL(fileURLWithPath: "/usr/bin/git")
                p.arguments = args
                p.currentDirectoryURL = directory
                let pipe = Pipe()
                p.standardOutput = pipe
                p.standardError  = pipe   // ⚠️ 同一パイプ — dual-pipe deadlock 防止
                try? p.run()
                let out = String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
                p.waitUntilExit()
                cont.resume(returning: out.trimmingCharacters(in: .whitespacesAndNewlines))
            }
        }
    }

    // MARK: - Xcodebuild

    private func runXcodeBuild(in root: URL, scheme: String, derivedDataPath: String) async -> Bool {
        // Find xcodeproj
        let projFiles = (try? FileManager.default.contentsOfDirectory(at: root, includingPropertiesForKeys: nil))
            ?? []
        let proj = projFiles.first(where: { $0.pathExtension == "xcodeproj" })
        let projFlag = proj.map { ["-project", $0.lastPathComponent] } ?? ["-scheme", scheme]

        var args = projFlag + [
            "-scheme", scheme,
            "-configuration", "Release",
            "-derivedDataPath", derivedDataPath,
            "build",
            "CODE_SIGN_IDENTITY=",
            "CODE_SIGNING_REQUIRED=NO",
            "CODE_SIGNING_ALLOWED=NO"
        ]

        return await withCheckedContinuation { cont in
            DispatchQueue.global(qos: .userInitiated).async { [weak self] in
                let p = Process()
                p.executableURL = URL(fileURLWithPath: "/usr/bin/xcodebuild")
                p.arguments = args
                p.currentDirectoryURL = root
                var env = ProcessInfo.processInfo.environment
                env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:" + (env["PATH"] ?? "")
                p.environment = env

                let pipe = Pipe()
                p.standardOutput = pipe
                p.standardError  = pipe

                pipe.fileHandleForReading.readabilityHandler = { fh in
                    let chunk = String(data: fh.availableData, encoding: .utf8) ?? ""
                    if chunk.isEmpty { return }
                    Task { @MainActor [weak self] in
                        self?.appendLog(chunk)
                        // Estimate progress from xcodebuild output
                        if chunk.contains("CompileSwift") || chunk.contains("Compile") {
                            if case .building(let p) = self?.buildState, p < 0.85 {
                                self?.buildState = .building(progress: p + 0.02)
                            }
                        }
                    }
                }

                try? p.run()
                p.waitUntilExit()
                pipe.fileHandleForReading.readabilityHandler = nil
                cont.resume(returning: p.terminationStatus == 0)
            }
        }
    }

    private func detectXcodeScheme(in root: URL) -> String? {
        let files = (try? FileManager.default.contentsOfDirectory(at: root, includingPropertiesForKeys: nil)) ?? []
        return files.first(where: { $0.pathExtension == "xcodeproj" })?
            .deletingPathExtension().lastPathComponent
    }

    private func findBuiltApp(in derivedData: String, scheme: String) -> URL? {
        let buildProducts = URL(fileURLWithPath: derivedData)
            .appendingPathComponent("Build/Products/Release")
        let app = buildProducts.appendingPathComponent("\(scheme).app")
        return FileManager.default.fileExists(atPath: app.path) ? app : nil
    }

    // MARK: - Repo detection

    var repoRoot: URL? {
        if let cached = _repoRoot { return cached }
        _repoRoot = detectRepoRoot()
        return _repoRoot
    }

    private func detectRepoRoot() -> URL? {
        // 1. Walk up from bundle (works when running from source)
        if let found = walkUpToRepoRoot(from: Bundle.main.bundleURL) { return found }

        // 2. Last known repo root (set by setWorkspaceHint or openWorkspace)
        if let saved = UserDefaults.standard.string(forKey: "evo_last_repo_root") {
            let url = URL(fileURLWithPath: saved)
            if FileManager.default.fileExists(atPath: url.path) { return url }
        }

        return nil
    }

    func walkUpToRepoRoot(from startURL: URL) -> URL? {
        var url = startURL
        let fm = FileManager.default
        for _ in 0..<12 {
            if fm.fileExists(atPath: url.appendingPathComponent("Package.swift").path) { return url }
            let contents = (try? fm.contentsOfDirectory(at: url, includingPropertiesForKeys: nil)) ?? []
            if contents.contains(where: { $0.pathExtension == "xcodeproj" }) { return url }
            let parent = url.deletingLastPathComponent()
            if parent == url { break }  // filesystem root
            url = parent
        }
        return nil
    }

    // MARK: - Persistence

    private let featuresKey = "self_evolution_features"

    private func saveAppliedFeatures() {
        if let data = try? JSONEncoder().encode(appliedFeatures) {
            UserDefaults.standard.set(data, forKey: featuresKey)
        }
    }

    func loadAppliedFeatures() {
        if let data = UserDefaults.standard.data(forKey: featuresKey),
           let feat = try? JSONDecoder().decode([AppliedFeature].self, from: data) {
            appliedFeatures = feat
        }
    }

    // MARK: - Log helper

    private func appendLog(_ text: String) {
        buildLog += text.hasSuffix("\n") ? text : text + "\n"
    }
}

// MARK: - Errors

enum EvoError: LocalizedError {
    case noRepoRoot
    var errorDescription: String? { "Could not find repository root" }
}
