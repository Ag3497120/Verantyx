import Foundation
import SwiftUI

// MARK: - CIValidationEngine
//
// ローカル「仮想CI/CD」エンジン。
//
// AIがソースを書き換えた際、メインバイナリを直接上書きする前に:
//   1. feature ブランチで swift build / xcodebuild をテスト実行
//   2. コンパイルエラー → ErrorDigest を生成 → AIに自動送信
//   3. AIがエラーを読んでパッチを修正 → 再検証
//   4. 最大 MAX_RETRIES 回繰り返す
//   5. 全パスしたらメインビルドを許可
//
// このファイルは AIが改変しない「不死身コア」の一部。

@MainActor
final class CIValidationEngine: ObservableObject {

    static let shared = CIValidationEngine()

    let MAX_RETRIES = 3

    // MARK: - Published state

    @Published var currentPhase: Phase = .idle
    @Published var retryCount: Int = 0
    @Published var ciLog: String = ""
    @Published var lastErrors: [CompileError] = []
    @Published var isRunning: Bool = false

    enum Phase: Equatable {
        case idle
        case preparingBranch
        case compiling(attempt: Int)
        case fixingErrors(attempt: Int)
        case passed
        case failed(String)
    }

    // MARK: - Compile Error model

    struct CompileError: Identifiable {
        let id = UUID()
        let file: String
        let line: Int
        let column: Int
        let severity: String  // "error" | "warning"
        let message: String

        var displayString: String {
            "\(severity.uppercased()) \(file):\(line):\(column) — \(message)"
        }
    }

    // MARK: - Main entry point

    /// Run the validation loop. Returns true if compilation passed.
    /// `onAIRetry` is called with the error digest; caller should invoke the AI
    /// and return the new patches.
    func runValidationLoop(
        repoRoot: URL,
        scheme: String,
        patches: [SelfEvolutionEngine.FilePatch],
        onAIRetry: @escaping ([CompileError]) async -> [SelfEvolutionEngine.FilePatch]
    ) async -> Bool {

        isRunning = true
        retryCount = 0
        lastErrors = []
        currentPhase = .preparingBranch
        appendLog("🔬 仮想CI/CD 開始 (最大\(MAX_RETRIES)回)")
        appendLog("=" .repeated(50))

        // --- Step 1: Setup validation branch ---
        let valBranch = "ci-validate-\(Int(Date().timeIntervalSince1970))"
        appendLog("🌿 検証ブランチ作成: \(valBranch)")
        _ = await runGit(["stash"], in: repoRoot)
        _ = await runGit(["checkout", "-b", valBranch], in: repoRoot)

        var currentPatches = patches

        for attempt in 1...MAX_RETRIES {
            retryCount = attempt
            currentPhase = .compiling(attempt: attempt)
            appendLog("\n🔨 コンパイル試行 \(attempt)/\(MAX_RETRIES)…")

            // Apply patches
            for patch in currentPatches {
                let url = repoRoot.appendingPathComponent(patch.relativePath)
                try? patch.patchedContent.write(to: url, atomically: true, encoding: .utf8)
            }

            // --- Step 2: Compile ---
            let (success, errors) = await compile(in: repoRoot, scheme: scheme)
            lastErrors = errors

            if success {
                appendLog("✅ コンパイル成功! (\(attempt)回目)")
                currentPhase = .passed

                // Clean up: merge to feature branch, delete ci branch
                _ = await runGit(["add", "-A"], in: repoRoot)
                _ = await runGit(["commit", "-m", "ci: validated at attempt \(attempt)"], in: repoRoot)
                appendLog("🧹 CI ブランチをクリーンアップ")
                isRunning = false
                return true
            }

            appendLog("❌ エラー \(errors.count) 件:")
            for e in errors.prefix(10) { appendLog("  \(e.displayString)") }

            if attempt == MAX_RETRIES {
                appendLog("\n🚫 最大リトライ数に達しました。パッチは破棄されます。")
                // Rollback
                _ = await runGit(["checkout", "-"], in: repoRoot)
                _ = await runGit(["branch", "-D", valBranch], in: repoRoot)
                _ = await runGit(["stash", "pop"], in: repoRoot)
                currentPhase = .failed("最大 \(MAX_RETRIES) 回試行しましたがコンパイルエラーが残っています")
                isRunning = false
                return false
            }

            // --- Step 3: AI retry ---
            currentPhase = .fixingErrors(attempt: attempt)
            appendLog("\n🤖 AI にエラーを送信してパッチを修正させます (試行 \(attempt+1)/\(MAX_RETRIES))…")
            let newPatches = await onAIRetry(errors)
            currentPatches = newPatches
        }

        isRunning = false
        return false
    }

    // MARK: - swift build / xcodebuild compile check

    private func compile(in root: URL, scheme: String) async -> (Bool, [CompileError]) {

        // Prefer xcodebuild if xcodeproj exists, else swift build
        let fm = FileManager.default
        let contents = (try? fm.contentsOfDirectory(at: root, includingPropertiesForKeys: nil)) ?? []
        let hasXcodeproj = contents.contains { $0.pathExtension == "xcodeproj" }

        if hasXcodeproj {
            return await runXcodeBuildCheck(in: root, scheme: scheme)
        } else {
            return await runSwiftBuildCheck(in: root)
        }
    }

    private func runXcodeBuildCheck(in root: URL, scheme: String) async -> (Bool, [CompileError]) {
        let derivedData = NSTemporaryDirectory() + "verantyx_ci_\(Int(Date().timeIntervalSince1970))"
        let args = [
            "-scheme", scheme,
            "-configuration", "Debug",
            "-derivedDataPath", derivedData,
            "build",
            "CODE_SIGN_IDENTITY=",
            "CODE_SIGNING_REQUIRED=NO"
        ]

        let output = await runProcess("/usr/bin/xcodebuild", args: args, in: root)
        // Clean up derived data
        try? FileManager.default.removeItem(atPath: derivedData)

        let errors = parseXcodeBuildErrors(output)
        let success = output.contains("BUILD SUCCEEDED") && errors.filter { $0.severity == "error" }.isEmpty
        return (success, errors)
    }

    private func runSwiftBuildCheck(in root: URL) async -> (Bool, [CompileError]) {
        let output = await runProcess("swift", args: ["build"], in: root)
        let errors = parseSwiftBuildErrors(output)
        let success = !output.contains("error:") && !output.contains("build error")
        return (success, errors)
    }

    // MARK: - Error parsers

    /// Parse xcodebuild JSON-style or text error output.
    private func parseXcodeBuildErrors(_ output: String) -> [CompileError] {
        var errors: [CompileError] = []
        // Pattern: /path/to/File.swift:42:10: error: some message
        let pattern = #"([^:\n]+\.swift):(\d+):(\d+): (error|warning): (.+)"#
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return [] }
        let range = NSRange(output.startIndex..., in: output)
        let matches = regex.matches(in: output, range: range)
        for m in matches {
            guard let fileR = Range(m.range(at: 1), in: output),
                  let lineR = Range(m.range(at: 2), in: output),
                  let colR  = Range(m.range(at: 3), in: output),
                  let sevR  = Range(m.range(at: 4), in: output),
                  let msgR  = Range(m.range(at: 5), in: output)
            else { continue }
            let file = URL(fileURLWithPath: String(output[fileR])).lastPathComponent
            errors.append(CompileError(
                file: file,
                line: Int(output[lineR]) ?? 0,
                column: Int(output[colR]) ?? 0,
                severity: String(output[sevR]),
                message: String(output[msgR]).trimmingCharacters(in: .whitespaces)
            ))
        }
        return errors
    }

    private func parseSwiftBuildErrors(_ output: String) -> [CompileError] {
        // Reuse same pattern
        parseXcodeBuildErrors(output)
    }

    // MARK: - Error digest for AI

    /// Build a compact error summary to send to the AI for self-correction.
    func buildErrorDigest(errors: [CompileError], patches: [SelfEvolutionEngine.FilePatch]) -> String {
        let errorList = errors.prefix(20).map { "• \($0.displayString)" }.joined(separator: "\n")
        let fileList  = Set(errors.map { $0.file }).joined(separator: ", ")

        return AppLanguage.shared.t("""
        ## ⚠️ Compilation Errors Detected

        Errors occurred in the following files: \(fileList)

        Error list:
        \(errorList)

        Please fix the patches you generated.
        Output the fixed files using the same [PATCH_FILE: ...] format.
        Review each error and resolve all of them.
        """, """
        ## ⚠️ コンパイルエラーが検出されました

        以下のファイルでエラーが発生しています: \(fileList)

        エラー一覧:
        \(errorList)

        あなたが生成したパッチを修正してください。
        同じ [PATCH_FILE: ...] 形式で修正済みファイルを出力してください。
        エラーを一つずつ確認し、すべてのエラーを解消してください。
        """)
    }

    // MARK: - CI Status View (embeddable)

    var statusSummary: String {
        switch currentPhase {
        case .idle:                       return AppLanguage.shared.t("Idle", "待機中")
        case .preparingBranch:            return AppLanguage.shared.t("🌿 Preparing validation branch…", "🌿 検証ブランチ準備中…")
        case .compiling(let n):           return AppLanguage.shared.t("🔨 Compiling (Attempt \(n)/\(MAX_RETRIES))…", "🔨 コンパイル中 (試行 \(n)/\(MAX_RETRIES))…")
        case .fixingErrors(let n):        return AppLanguage.shared.t("🤖 AI fixing errors (Attempt \(n))…", "🤖 AI がエラーを修正中 (試行 \(n))…")
        case .passed:                     return AppLanguage.shared.t("✅ CI Passed — Main build permitted", "✅ CI 通過 — メインビルドを許可")
        case .failed(let msg):            return AppLanguage.shared.t("❌ CI Failed: \(msg)", "❌ CI 失敗: \(msg)")
        }
    }

    var phaseColor: Color {
        switch currentPhase {
        case .idle:             return .secondary
        case .preparingBranch:  return Color(red: 0.7, green: 0.65, blue: 0.95)
        case .compiling:        return Color(red: 0.4, green: 0.7, blue: 1.0)
        case .fixingErrors:     return Color(red: 1.0, green: 0.75, blue: 0.2)
        case .passed:           return Color(red: 0.3, green: 0.9, blue: 0.5)
        case .failed:           return .red
        }
    }

    // MARK: - Process runner

    @discardableResult
    func runProcess(_ executable: String, args: [String], in dir: URL) async -> String {
        await withCheckedContinuation { cont in
            DispatchQueue.global(qos: .userInitiated).async {
                let p = Process()
                let execURL: URL
                if executable.hasPrefix("/") {
                    execURL = URL(fileURLWithPath: executable)
                } else {
                    // Resolve via /usr/bin/env
                    p.executableURL = URL(fileURLWithPath: "/usr/bin/env")
                    p.arguments = [executable] + args
                    p.currentDirectoryURL = dir
                    var env = ProcessInfo.processInfo.environment
                    env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:" + (env["PATH"] ?? "")
                    p.environment = env
                    let pipe = Pipe()
                    p.standardOutput = pipe; p.standardError = pipe
                    try? p.run()
                    let out = String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
                    p.waitUntilExit()
                    cont.resume(returning: out)
                    return
                }
                p.executableURL = execURL
                p.arguments = args
                p.currentDirectoryURL = dir
                var env = ProcessInfo.processInfo.environment
                env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:" + (env["PATH"] ?? "")
                p.environment = env
                let pipe = Pipe()
                p.standardOutput = pipe; p.standardError = pipe
                try? p.run()
                let out = String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
                p.waitUntilExit()
                cont.resume(returning: out)
            }
        }
    }

    @discardableResult
    func runGit(_ args: [String], in directory: URL) async -> String {
        await runProcess("/usr/bin/git", args: args, in: directory)
    }

    private func appendLog(_ text: String) {
        ciLog += text + "\n"
    }
}

// MARK: - String helper

private extension String {
    func repeated(_ n: Int) -> String { String(repeating: self, count: n) }
}
