import Foundation

// MARK: - Claude through the Agent SDK, not through raw HTTP
//
// Anthropic restricted subscription credentials to its own clients, then
// reopened third-party use through one specific door: applications built on
// the Claude Agent SDK. Posting to api.anthropic.com with a token lifted out
// of a Claude Code session is the door that stayed shut, and building on it
// would be building on something that has changed three times this year.
//
// Verantyx is a Swift app and there is no Swift SDK, so the SDK is reached the
// way any non-JS/Python program reaches it: the `claude` binary in print mode,
// which is the same entry point `claude -p` and the GitHub Action use. The
// user's existing Claude Code login supplies the credentials — this process
// never sees, stores, or transmits them.
//
// ── What this does NOT do ─────────────────────────────────────────────────
//
// It does not extract, read, or copy any credential. It runs an installed
// binary and reads its stdout. If the user is not logged into Claude Code,
// the binary says so and that message is passed through unchanged.
//
// ── Flags ─────────────────────────────────────────────────────────────────
//
// The CLI's flags are its own and change with its versions, so nothing here
// assumes them. `probe()` asks the installed binary what it supports and the
// request is built from the answer. A flag that turns out not to exist is
// reported rather than silently dropped — the same rule the tool specs follow,
// for the same reason.
actor ClaudeAgentSDKClient {

    static let shared = ClaudeAgentSDKClient()

    struct Capabilities {
        let path: String
        let version: String
        let supportsPrint: Bool
        let supportsModelFlag: Bool
        let supportsStreamJSON: Bool
        let notes: [String]

        var usable: Bool { supportsPrint }

        var summary: String {
            var out = ["claude CLI: \(path)", "  バージョン: \(version)"]
            out.append("  -p / --print: \(supportsPrint ? "対応" : "非対応")")
            out.append("  --model: \(supportsModelFlag ? "対応（モデル切替可）" : "非対応（既定モデルのみ）")")
            out.append("  --output-format stream-json: \(supportsStreamJSON ? "対応" : "非対応")")
            for n in notes { out.append("  ⚠️ \(n)") }
            return out.joined(separator: "\n")
        }
    }

    private var cached: Capabilities?

    // MARK: - Finding the binary

    /// Where the CLI usually is, plus whatever the user has configured. PATH
    /// is not enough on its own: a GUI app launched from Finder does not
    /// inherit the shell's PATH, which is why a binary the user can run in
    /// Terminal is routinely invisible to the app.
    private static var candidatePaths: [String] {
        var paths: [String] = []
        if let custom = UserDefaults.standard.string(forKey: "claude_cli_path"),
           !custom.isEmpty { paths.append(custom) }
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        paths += [
            "/usr/local/bin/claude",
            "/opt/homebrew/bin/claude",
            "\(home)/.claude/local/claude",
            "\(home)/.local/bin/claude",
            "\(home)/.bun/bin/claude",
            "\(home)/.npm-global/bin/claude",
        ]
        return paths
    }

    static func locate() -> String? {
        let fm = FileManager.default
        for p in candidatePaths where fm.isExecutableFile(atPath: p) { return p }
        // Last resort: ask a login shell, which does have the user's PATH.
        let which = Process()
        which.executableURL = URL(fileURLWithPath: "/bin/zsh")
        which.arguments = ["-lc", "command -v claude"]
        let pipe = Pipe()
        which.standardOutput = pipe
        which.standardError = Pipe()
        guard (try? which.run()) != nil else { return nil }
        which.waitUntilExit()
        let out = String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8)?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return out.isEmpty ? nil : out
    }

    // MARK: - Asking the binary what it can do

    /// Never assume a flag. The CLI is versioned independently of this app, so
    /// what it accepts is a fact to be read, not a constant to be compiled in.
    func probe(force: Bool = false) async -> Capabilities? {
        if !force, let cached { return cached }
        guard let path = Self.locate() else { return nil }

        let version = (try? await run(path: path, args: ["--version"], input: nil).out)?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? "unknown"
        let help = (try? await run(path: path, args: ["--help"], input: nil).out) ?? ""

        var notes: [String] = []
        let hasPrint = help.contains("--print") || help.contains("-p,")
        let hasModel = help.contains("--model")
        let hasStream = help.contains("stream-json")
        if !hasPrint {
            notes.append("--print が見つかりません。この CLI ではプログラム実行ができない可能性があります。")
        }
        if !hasModel {
            notes.append("--model が見つかりません。モデルは CLI 側の既定に従います。")
        }

        let caps = Capabilities(path: path, version: version,
                                supportsPrint: hasPrint, supportsModelFlag: hasModel,
                                supportsStreamJSON: hasStream, notes: notes)
        cached = caps
        return caps
    }

    // MARK: - Models
    //
    // The Agent SDK serves Anthropic models only. That is the honest limit of
    // this route: it is a way to reach Claude on a subscription, not a way to
    // reach Grok or Qwen. Those stay on the API-key path, which is why this is
    // an additional backend rather than a replacement for it.

    nonisolated static let models: [String] = [
        "claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5",
        "opus", "sonnet", "haiku"     // the CLI's own aliases
    ]

    // MARK: - Asking it something

    struct Reply {
        let text: String
        let isError: Bool
    }

    /// One turn. Conversation history is flattened into the prompt because
    /// print mode takes a prompt, not a message array; `--resume` exists for
    /// real session continuity and is a later step.
    func send(prompt: String, systemPrompt: String?, model: String?) async -> Reply {
        guard let caps = await probe() else {
            return Reply(text: """
                claude CLI が見つかりません。
                Agent SDK 経由で使うには Claude Code をインストールしてください:
                  npm i -g @anthropic-ai/claude-code
                インストール済みなら、設定でパスを指定できます（claude_cli_path）。
                """, isError: true)
        }
        guard caps.usable else {
            return Reply(text: "この claude CLI は print モードに対応していません。\n\(caps.summary)",
                         isError: true)
        }

        var args = ["-p"]
        if let model, caps.supportsModelFlag { args += ["--model", model] }
        if let systemPrompt, !systemPrompt.isEmpty {
            args += ["--append-system-prompt", systemPrompt]
        }

        do {
            let result = try await run(path: caps.path, args: args, input: prompt)
            let text = result.out.trimmingCharacters(in: .whitespacesAndNewlines)
            if result.status != 0 {
                // The CLI's own message is more useful than anything this
                // layer could invent — not logged in, over quota, bad model.
                let err = result.err.trimmingCharacters(in: .whitespacesAndNewlines)
                return Reply(text: err.isEmpty ? "claude CLI が終了コード \(result.status) を返しました" : err,
                             isError: true)
            }
            return Reply(text: text, isError: false)
        } catch {
            return Reply(text: "claude CLI を実行できません: \(error.localizedDescription)",
                         isError: true)
        }
    }

    // MARK: - Process plumbing

    private struct RunResult { let out: String; let err: String; let status: Int32 }

    private func run(path: String, args: [String], input: String?) async throws -> RunResult {
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: path)
        proc.arguments = args

        let outPipe = Pipe(), errPipe = Pipe(), inPipe = Pipe()
        proc.standardOutput = outPipe
        proc.standardError = errPipe
        proc.standardInput = inPipe

        try proc.run()

        if let input {
            inPipe.fileHandleForWriting.write(Data(input.utf8))
        }
        try? inPipe.fileHandleForWriting.close()

        let outData = outPipe.fileHandleForReading.readDataToEndOfFile()
        let errData = errPipe.fileHandleForReading.readDataToEndOfFile()
        proc.waitUntilExit()

        return RunResult(out: String(data: outData, encoding: .utf8) ?? "",
                         err: String(data: errData, encoding: .utf8) ?? "",
                         status: proc.terminationStatus)
    }
}
