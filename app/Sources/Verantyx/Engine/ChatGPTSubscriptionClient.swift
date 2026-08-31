import Foundation

/// ChatGPT subscription access through the locally installed Codex CLI.
///
/// This is deliberately separate from `CloudAPIClient`'s OpenAI API route:
/// ChatGPT subscriptions and API billing are separate products. Verantyx
/// never reads or stores the user's OpenAI credential; the Codex CLI owns the
/// existing ChatGPT login and returns only the final text response.
actor ChatGPTSubscriptionClient {
    static let shared = ChatGPTSubscriptionClient()

    struct Capabilities: Equatable, Sendable {
        let path: String
        let version: String
        let loggedInWithChatGPT: Bool
        let statusText: String

        var usable: Bool { loggedInWithChatGPT }
    }

    struct Reply: Sendable {
        let text: String
        let isError: Bool
    }

    /// `default` intentionally omits `--model`, allowing the user's Codex
    /// configuration and subscription entitlement to choose the model.
    nonisolated static let models = ["default"]

    private var cached: Capabilities?

    private static var candidatePaths: [String] {
        var paths: [String] = []
        if let custom = UserDefaults.standard.string(forKey: "chatgpt_codex_cli_path"),
           !custom.isEmpty { paths.append(custom) }
        if let custom = ProcessInfo.processInfo.environment["CODEX_CLI_PATH"],
           !custom.isEmpty { paths.append(custom) }
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        paths += [
            "/Applications/ChatGPT.app/Contents/Resources/codex",
            "/usr/local/bin/codex",
            "/opt/homebrew/bin/codex",
            "\(home)/.local/bin/codex",
        ]
        return paths
    }

    nonisolated static func locate() -> String? {
        let fm = FileManager.default
        for path in candidatePaths where fm.isExecutableFile(atPath: path) { return path }

        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/zsh")
        process.arguments = ["-lc", "command -v codex"]
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = Pipe()
        guard (try? process.run()) != nil else { return nil }
        process.waitUntilExit()
        let output = String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8)?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return output.isEmpty ? nil : output
    }

    func probe(force: Bool = false) async -> Capabilities? {
        if !force, let cached { return cached }
        guard let path = Self.locate() else { return nil }

        let versionResult = try? await run(path: path, args: ["--version"], input: nil)
        let loginResult = try? await run(path: path, args: ["login", "status"], input: nil)
        let version = versionResult?.out.trimmingCharacters(in: .whitespacesAndNewlines) ?? "unknown"
        let status = [loginResult?.out, loginResult?.err]
            .compactMap { $0 }
            .joined(separator: "\n")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let loggedIn = loginResult?.status == 0
            && status.localizedCaseInsensitiveContains("ChatGPT")

        let capabilities = Capabilities(path: path, version: version,
                                        loggedInWithChatGPT: loggedIn,
                                        statusText: status)
        cached = capabilities
        return capabilities
    }

    /// Pure argument construction is kept testable. A subscription turn is
    /// ephemeral, runs in an empty directory, and has read-only filesystem
    /// access. No model flag is passed for `default`.
    nonisolated static func arguments(model: String?, workingDirectory: String,
                                      outputPath: String) -> [String] {
        var args = [
            "exec", "--ephemeral",
            "--sandbox", "read-only",
            "--skip-git-repo-check",
            "-C", workingDirectory,
            "-o", outputPath,
        ]
        if let model, !model.isEmpty, model != "default" {
            args += ["--model", model]
        }
        args.append("-")
        return args
    }

    func send(prompt: String, systemPrompt: String?, model: String?) async -> Reply {
        guard let capabilities = await probe() else {
            return Reply(text: "Codex CLI が見つかりません。ChatGPT デスクトップまたは Codex CLI をインストールしてください。",
                         isError: true)
        }
        guard capabilities.usable else {
            let detail = capabilities.statusText.isEmpty
                ? "ターミナルで `codex login` を実行してください。"
                : capabilities.statusText
            return Reply(text: "ChatGPT で Codex にログインしていません。\n\(detail)", isError: true)
        }

        let fm = FileManager.default
        let directory = fm.temporaryDirectory
            .appendingPathComponent("verantyx-chatgpt-\(UUID().uuidString)", isDirectory: true)
        let output = directory.appendingPathComponent("reply.txt")
        defer { try? fm.removeItem(at: directory) }

        do {
            try fm.createDirectory(at: directory, withIntermediateDirectories: true)
            let system = systemPrompt?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            let request = """
                You are the text model inside Verantyx. Return only the assistant response.
                Do not inspect files, run commands, browse, or perform an independent agent loop.
                Verantyx will parse and execute any application actions through its own verified loop.

                SYSTEM INSTRUCTIONS:
                \(system)

                CONVERSATION:
                \(prompt)
                """
            let args = Self.arguments(model: model,
                                      workingDirectory: directory.path,
                                      outputPath: output.path)
            let result = try await run(path: capabilities.path, args: args, input: request)
            let finalText = (try? String(contentsOf: output, encoding: .utf8))?
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            if result.status != 0 {
                let reason = result.err.trimmingCharacters(in: .whitespacesAndNewlines)
                return Reply(text: reason.isEmpty
                             ? "Codex CLI が終了コード \(result.status) を返しました。"
                             : reason,
                             isError: true)
            }
            guard !finalText.isEmpty else {
                return Reply(text: "Codex CLI は応答を返しませんでした。", isError: true)
            }
            return Reply(text: finalText, isError: false)
        } catch {
            return Reply(text: "Codex CLI を実行できません: \(error.localizedDescription)", isError: true)
        }
    }

    private struct RunResult: Sendable { let out: String; let err: String; let status: Int32 }

    private func run(path: String, args: [String], input: String?) async throws -> RunResult {
        try await Task.detached(priority: .userInitiated) {
            let process = Process()
            process.executableURL = URL(fileURLWithPath: path)
            process.arguments = args
            let outPipe = Pipe(), errPipe = Pipe(), inPipe = Pipe()
            process.standardOutput = outPipe
            process.standardError = errPipe
            process.standardInput = inPipe
            try process.run()
            if let input { inPipe.fileHandleForWriting.write(Data(input.utf8)) }
            try? inPipe.fileHandleForWriting.close()
            let out = outPipe.fileHandleForReading.readDataToEndOfFile()
            let err = errPipe.fileHandleForReading.readDataToEndOfFile()
            process.waitUntilExit()
            return RunResult(out: String(data: out, encoding: .utf8) ?? "",
                             err: String(data: err, encoding: .utf8) ?? "",
                             status: process.terminationStatus)
        }.value
    }
}
