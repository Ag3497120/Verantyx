import Foundation
import AppKit
import SwiftUI

// MARK: - SafeModeGuard
//
// 「究極の命綱」— AIが絶対に改変できない起動ガード。
//
// 動作:
//   1. アプリ起動直後 (applicationWillFinishLaunching) に Shift キーの状態を検知
//   2. Shift が押されていた場合: SafeMode ウィンドウを表示
//   3. ユーザーが選択:
//        [ロールバック & 起動] → git reset --hard HEAD~1 → 通常起動
//        [そのまま起動]       → safe.app バックアップから起動
//        [最終コミットに戻す] → git reset --hard <last stable tag>
//        [終了]              → NSApp.terminate
//
// このファイル自体は Self-Evolution パッチ対象外（AIへの指示ルールで除外）。

@MainActor
final class SafeModeGuard: ObservableObject {

    static let shared = SafeModeGuard()

    @Published var isSafeModeActive: Bool = false
    @Published var safeModeLog: String = ""
    @Published var stableCommitList: [StableCommit] = []

    struct StableCommit: Identifiable {
        let id: UUID = UUID()
        let hash: String
        let message: String
        let date: String
    }

    // MARK: - Startup check (called from AppDelegate.applicationWillFinishLaunching)

    /// Check Shift key state at launch. Returns true if safe mode was triggered.
    func checkOnLaunch() -> Bool {
        // Read the physical Shift key state via CGEventSource (works before any window appears)
        let shiftHeld = CGEventSource.keyState(.combinedSessionState, key: CGKeyCode(56)) // left shift
                     || CGEventSource.keyState(.combinedSessionState, key: CGKeyCode(60)) // right shift

        if shiftHeld || ProcessInfo.processInfo.environment["VERANTYX_SAFE_MODE"] == "1" {
            isSafeModeActive = true
            appendLog(AppLanguage.shared.t("⚠️ SAFE MODE triggered", "⚠️ SAFE MODE 起動を検知"))
            appendLog(AppLanguage.shared.t("  Shift key was held during application launch", "  Shift キーが押された状態でアプリが起動されました"))
            appendLog(AppLanguage.shared.t("  Please select a recovery action", "  リカバリー操作を選択してください"))
            Task { await loadCommitHistory() }
            return true
        }
        return false
    }

    // MARK: - Recovery actions

    /// git reset --hard HEAD~1  (1コミット前に戻す)
    func rollbackOneCommit() async -> Bool {
        await performReset(to: "HEAD~1")
    }

    /// git reset --hard <hash>  (指定コミットに戻す)
    func rollbackTo(hash: String) async -> Bool {
        await performReset(to: hash)
    }

    /// git reset --hard <latest stable tag>
    func rollbackToLatestTag() async -> Bool {
        guard let root = SelfEvolutionEngine.shared.repoRoot else {
            appendLog(AppLanguage.shared.t("❌ Repository not found", "❌ リポジトリが見つかりません")); return false
        }
        let tag = await runGit(["describe", "--tags", "--abbrev=0"], in: root)
        if tag.isEmpty || tag.contains("fatal") {
            appendLog(AppLanguage.shared.t("⚠️ Tag not found. Rolling back to HEAD~1", "⚠️ タグが見つかりません。HEAD~1 にロールバックします"))
            return await rollbackOneCommit()
        }
        return await performReset(to: tag)
    }

    private func performReset(to ref: String) async -> Bool {
        guard let root = SelfEvolutionEngine.shared.repoRoot else {
            appendLog(AppLanguage.shared.t("❌ Repository not found", "❌ リポジトリが見つかりません")); return false
        }
        appendLog(AppLanguage.shared.t("🔄 Running git reset --hard \(ref)...", "🔄 git reset --hard \(ref) を実行中…"))

        // Safety: stash any untracked changes first so git reset can proceed
        _ = await runGit(["stash", "--include-untracked"], in: root)

        let result = await runGit(["reset", "--hard", ref], in: root)
        appendLog(result)

        if result.contains("HEAD is now at") || result.contains("Updating files") {
            appendLog(AppLanguage.shared.t("✅ Rollback complete: \(ref)", "✅ ロールバック完了: \(ref)"))
            return true
        } else {
            appendLog(AppLanguage.shared.t("❌ Rollback failed: \(result)", "❌ ロールバック失敗: \(result)"))
            return false
        }
    }

    // MARK: - Commit history

    func loadCommitHistory() async {
        guard let root = SelfEvolutionEngine.shared.repoRoot else { return }
        // Get last 20 commits with hash + subject + date
        let log = await runGit(
            ["log", "--oneline", "--format=%H|%s|%ar", "-n", "20"],
            in: root
        )
        let commits: [StableCommit] = log.components(separatedBy: "\n")
            .compactMap { line -> StableCommit? in
                let parts = line.components(separatedBy: "|")
                guard parts.count >= 3 else { return nil }
                return StableCommit(hash: String(parts[0].prefix(8)),
                                    message: parts[1], date: parts[2])
            }
        stableCommitList = commits
    }

    // MARK: - Git helper

    @discardableResult
    func runGit(_ args: [String], in directory: URL) async -> String {
        await withCheckedContinuation { cont in
            DispatchQueue.global(qos: .userInteractive).async {
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

    private func appendLog(_ text: String) {
        safeModeLog += text + "\n"
    }
}

// MARK: - SafeModeWindow
// 全画面を覆うリカバリー画面。通常UIより前面に表示。

struct SafeModeWindow: View {
    @ObservedObject private var guard_ = SafeModeGuard.shared
    @State private var isProcessing = false
    @State private var done = false
    @State private var selectedHash: String? = nil

    var body: some View {
        ZStack {
            // Dark pulsing background
            Color(red: 0.08, green: 0.04, blue: 0.04)
                .ignoresSafeArea()

            // Warning stripes (CSS-style)
            GeometryReader { geo in
                Canvas { ctx, size in
                    let stripe = 30.0
                    var x: Double = 0.0
                    while x < size.width + size.height {
                        let path = Path { p in
                            p.move(to: CGPoint(x: x, y: 0))
                            p.addLine(to: CGPoint(x: x + stripe, y: 0))
                            p.addLine(to: CGPoint(x: x + stripe - size.height, y: size.height))
                            p.addLine(to: CGPoint(x: x - size.height, y: size.height))
                        }
                        ctx.fill(path, with: .color(Color(red: 1.0, green: 0.5, blue: 0.0).opacity(0.04)))
                        x += stripe * 2
                    }
                }
            }
            .ignoresSafeArea()

            VStack(spacing: 0) {
                // ── Header ───────────────────────────────────────────────
                VStack(spacing: 10) {
                    HStack(spacing: 14) {
                        Image(systemName: "exclamationmark.shield.fill")
                            .font(.system(size: 42))
                            .foregroundStyle(Color(red: 1.0, green: 0.45, blue: 0.1))
                            .symbolEffect(.pulse)

                        VStack(alignment: .leading, spacing: 4) {
                            Text("VERANTYX SAFE MODE")
                                .font(.system(size: 22, weight: .black, design: .monospaced))
                                .foregroundStyle(Color(red: 1.0, green: 0.45, blue: 0.15))
                            Text(AppLanguage.shared.t("Shift key detected — please select a recovery action", "Shift キーが検知されました — リカバリー操作を選択してください"))
                                .font(.system(size: 12))
                                .foregroundStyle(Color(red: 0.80, green: 0.65, blue: 0.55))
                        }
                    }
                    .padding(.top, 40)

                    // Divider with animation
                    Rectangle()
                        .fill(
                            LinearGradient(
                                colors: [.clear, Color(red: 1.0, green: 0.4, blue: 0.1), .clear],
                                startPoint: .leading, endPoint: .trailing
                            )
                        )
                        .frame(height: 1)
                        .padding(.horizontal, 60)
                }

                // ── Recovery Options ──────────────────────────────────────
                HStack(alignment: .top, spacing: 20) {
                    // Left: Quick actions
                    VStack(spacing: 12) {
                        recoveryButton(
                            icon: "arrow.uturn.backward.circle.fill",
                            title: AppLanguage.shared.t("Rollback 1 commit", "1コミット前にロールバック"),
                            subtitle: "git reset --hard HEAD~1",
                            color: Color(red: 0.9, green: 0.35, blue: 0.15)
                        ) {
                            isProcessing = true
                            let ok = await guard_.rollbackOneCommit()
                            if ok { done = true } else { isProcessing = false }
                        }

                        recoveryButton(
                            icon: "tag.circle.fill",
                            title: AppLanguage.shared.t("Rollback to latest stable tag", "最新の安定タグに戻す"),
                            subtitle: "git reset --hard <latest-tag>",
                            color: Color(red: 0.55, green: 0.35, blue: 0.90)
                        ) {
                            isProcessing = true
                            let ok = await guard_.rollbackToLatestTag()
                            if ok { done = true } else { isProcessing = false }
                        }

                        recoveryButton(
                            icon: "arrow.right.circle.fill",
                            title: AppLanguage.shared.t("Continue booting", "このまま起動する"),
                            subtitle: AppLanguage.shared.t("May not be safe", "安全ではない可能性"),
                            color: Color(red: 0.35, green: 0.65, blue: 0.40)
                        ) {
                            done = true
                        }

                        recoveryButton(
                            icon: "xmark.circle.fill",
                            title: AppLanguage.shared.t("Exit", "終了する"),
                            subtitle: "NSApp.terminate",
                            color: Color(red: 0.55, green: 0.55, blue: 0.65)
                        ) {
                            NSApp.terminate(nil)
                        }
                    }
                    .frame(width: 320)

                    // Right: Commit history picker
                    VStack(alignment: .leading, spacing: 8) {
                        Text(AppLanguage.shared.t("Select from commit history", "コミット履歴から選択"))
                            .font(.system(size: 11, weight: .semibold, design: .monospaced))
                            .foregroundStyle(Color(red: 0.7, green: 0.65, blue: 0.6))

                        if guard_.stableCommitList.isEmpty {
                            ProgressView(AppLanguage.shared.t("Loading history...", "履歴を読み込み中…"))
                                .foregroundStyle(.secondary)
                                .frame(maxWidth: .infinity, alignment: .center)
                                .padding(.top, 20)
                        } else {
                            ScrollView {
                                LazyVStack(spacing: 1) {
                                    ForEach(guard_.stableCommitList) { commit in
                                        commitRow(commit)
                                    }
                                }
                            }
                            .frame(maxHeight: 220)
                            .background(Color.white.opacity(0.03), in: RoundedRectangle(cornerRadius: 8))

                            if let hash = selectedHash {
                                Button {
                                    isProcessing = true
                                    Task {
                                        let ok = await guard_.rollbackTo(hash: hash)
                                        if ok { done = true } else { isProcessing = false }
                                    }
                                } label: {
                                    Label(AppLanguage.shared.t("git reset --hard to this commit", "このコミットに git reset --hard"), systemImage: "arrow.uturn.backward")
                                        .font(.system(size: 11, weight: .bold))
                                        .foregroundStyle(.white)
                                        .frame(maxWidth: .infinity)
                                        .padding(.vertical, 8)
                                        .background(Color(red: 0.7, green: 0.25, blue: 0.1), in: RoundedRectangle(cornerRadius: 6))
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }
                    .frame(maxWidth: .infinity)
                }
                .padding(.horizontal, 60)
                .padding(.top, 24)

                // ── Log ───────────────────────────────────────────────────
                Spacer(minLength: 10)

                ScrollView {
                    Text(guard_.safeModeLog.isEmpty
                         ? AppLanguage.shared.t("git command logs will appear here...", "git コマンドのログがここに表示されます…")
                         : guard_.safeModeLog)
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(Color(red: 0.5, green: 0.85, blue: 0.5))
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(8)
                }
                .frame(height: 80)
                .background(Color(red: 0.04, green: 0.06, blue: 0.04))
                .padding(.horizontal, 60)
                .padding(.bottom, 20)

                // ── Done state ────────────────────────────────────────────
                if done {
                    Text(AppLanguage.shared.t("✅ Recovery complete — continuing normal boot", "✅ リカバリー完了 — 通常起動を続行します"))
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(Color(red: 0.4, green: 0.9, blue: 0.5))
                        .padding(.bottom, 16)
                }
            }

            // Processing overlay
            if isProcessing && !done {
                Color.black.opacity(0.6).ignoresSafeArea()
                VStack(spacing: 14) {
                    ProgressView().scaleEffect(1.2)
                    Text(AppLanguage.shared.t("Running git reset...", "git reset を実行中…"))
                        .font(.system(size: 13, design: .monospaced))
                        .foregroundStyle(.secondary)
                }
            }
        }
        .frame(minWidth: 700, minHeight: 520)
    }

    private func recoveryButton(
        icon: String, title: String, subtitle: String, color: Color,
        action: @escaping () async -> Void
    ) -> some View {
        Button {
            Task { await action() }
        } label: {
            HStack(spacing: 12) {
                Image(systemName: icon)
                    .font(.system(size: 22))
                    .foregroundStyle(color)
                    .frame(width: 32)
                VStack(alignment: .leading, spacing: 3) {
                    Text(title)
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(Color(red: 0.88, green: 0.88, blue: 0.92))
                    Text(subtitle)
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(Color(red: 0.50, green: 0.50, blue: 0.60))
                }
                Spacer()
                Image(systemName: "chevron.right")
                    .font(.system(size: 9))
                    .foregroundStyle(.tertiary)
            }
            .padding(.horizontal, 14).padding(.vertical, 11)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(Color.white.opacity(0.05))
                    .overlay(
                        RoundedRectangle(cornerRadius: 8)
                            .stroke(color.opacity(0.25), lineWidth: 0.8)
                    )
            )
        }
        .buttonStyle(.plain)
        .disabled(isProcessing)
    }

    private func commitRow(_ commit: SafeModeGuard.StableCommit) -> some View {
        Button {
            selectedHash = selectedHash == commit.hash ? nil : commit.hash
        } label: {
            HStack(spacing: 8) {
                Text(commit.hash)
                    .font(.system(size: 9, weight: .bold, design: .monospaced))
                    .foregroundStyle(Color(red: 0.5, green: 0.75, blue: 1.0))
                    .frame(width: 60, alignment: .leading)
                Text(commit.message)
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(Color(red: 0.72, green: 0.72, blue: 0.80))
                    .lineLimit(1)
                Spacer()
                Text(commit.date)
                    .font(.system(size: 8)).foregroundStyle(.tertiary)
            }
            .padding(.horizontal, 8).padding(.vertical, 4)
            .background(
                selectedHash == commit.hash
                    ? Color(red: 0.7, green: 0.25, blue: 0.1).opacity(0.25)
                    : Color.clear
            )
        }
        .buttonStyle(.plain)
    }
}
