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
        /// `--system-prompt` REPLACES the CLI's own prompt. `--append-system-prompt`
        /// only adds to it, which leaves the CLI's agent identity and its tool
        /// roster in force — see the note above `toolDenyList`.
        let supportsSystemPrompt: Bool
        let supportsToolDenial: Bool
        let supportsStrictMCP: Bool
        /// `--output-format json`, which is how a turn's real token split and
        /// cost are read back instead of estimated.
        let supportsJSONOutput: Bool
        let notes: [String]

        var usable: Bool { supportsPrint }

        /// Whether the CLI can be reduced to a plain model backend. Without
        /// this, the CLI runs its own agent loop with its own tools and
        /// Verantyx's OS layer is bypassed entirely.
        var canBeSilenced: Bool { supportsSystemPrompt && supportsToolDenial }

        var summary: String {
            var out = ["claude CLI: \(path)", "  バージョン: \(version)"]
            out.append("  -p / --print: \(supportsPrint ? "対応" : "非対応")")
            out.append("  --model: \(supportsModelFlag ? "対応（モデル切替可）" : "非対応（既定モデルのみ）")")
            out.append("  --output-format stream-json: \(supportsStreamJSON ? "対応" : "非対応")")
            out.append("  --system-prompt: \(supportsSystemPrompt ? "対応（Verantyx の規約で置換）" : "非対応（追記のみ）")")
            out.append("  --disallowedTools: \(supportsToolDenial ? "対応（CLI 側ツールを無効化）" : "非対応")")
            out.append("  --output-format json: \(supportsJSONOutput ? "対応（実測値を取得）" : "非対応（コストは推測のまま）")")
            out.append("  モデルバックエンド化: \(canBeSilenced ? "可能" : "不可 — CLI が自前のエージェントとして動作します")")
            for n in notes { out.append("  ⚠️ \(n)") }
            return out.joined(separator: "\n")
        }
    }

    // MARK: - Why every CLI-side tool is switched off
    //
    // The CLI is a complete agent, not a model endpoint. Left alone in print
    // mode it runs its own loop with its own tools, and the observed result was
    // exactly that: asked to open Teams and Safari it reached for `open`,
    // `screencapture`, `WebSearch` and `WebFetch` — none of which belong to
    // this app — then reported "This command requires approval" for all of
    // them and told the user to edit `.claude/settings.json`.
    //
    // Two separate faults produced that:
    //
    //   1. `--append-system-prompt` APPENDS. The CLI's own prompt, including
    //      its identity and tool roster, stayed in force and Verantyx's rules
    //      were bolted on the end. The rules did apply — the transcript shows
    //      ERROR STOP PROTOCOL firing — but the tools the model could actually
    //      call were the CLI's.
    //
    //   2. Print mode cannot show a permission prompt. Anything gated fails
    //      instantly and unrecoverably, so the run cannot even ask.
    //
    // The fix is not to grant those permissions. Handing the CLI's Bash a
    // blanket approval would put an unsupervised shell on the user's machine
    // AND still route the work around ForegroundAppOperator, OSControl,
    // ScreenChangeMonitor and VisionTower — the layers that make an action
    // checkable. It would trade the app's entire verification story for a
    // shortcut.
    //
    // So the CLI is reduced to what every other provider here already is: a
    // thing that returns text. Verantyx's own loop parses the tool tags out of
    // that text and executes them through AX, where the screen oracle can
    // contradict a false claim.
    // Every name here is verified against the installed CLI: an unrecognised
    // one makes it print "matches no known tool" to stderr, which this class
    // surfaces as a failure reason on a non-zero exit and would read as a real
    // error. ("SlashCommand" was in the first draft and is not a tool.)
    private static let toolDenyList = [
        "Bash", "BashOutput", "KillShell", "Edit", "Write", "NotebookEdit",
        "Read", "Glob", "Grep", "WebFetch", "WebSearch", "Task", "TodoWrite",
        "ExitPlanMode",
    ]

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
        // `--system-prompt` and `--append-system-prompt` share a prefix, so a
        // plain `contains` matches the append flag too and would report the
        // replace flag as present on a CLI that only has the append one.
        let hasSystemPrompt = help.contains("--system-prompt <")
            || help.contains("--system-prompt ")
            || help.range(of: #"--system-prompt\b(?!-)"#, options: .regularExpression) != nil
        let hasToolDenial = help.contains("--disallowedTools")
            || help.contains("--disallowed-tools")
        let hasStrictMCP = help.contains("--strict-mcp-config")
        let hasJSONOutput = help.contains("--output-format")

        if !hasPrint {
            notes.append("--print が見つかりません。この CLI ではプログラム実行ができない可能性があります。")
        }
        if !hasModel {
            notes.append("--model が見つかりません。モデルは CLI 側の既定に従います。")
        }
        // The loud one. Without both flags the CLI stays an agent in its own
        // right, and every OS action bypasses this app's verification layers.
        if !hasSystemPrompt || !hasToolDenial {
            notes.append("""
                この CLI をモデルバックエンドにできません\
                （\(hasSystemPrompt ? "" : "--system-prompt 無し ")\
                \(hasToolDenial ? "" : "--disallowedTools 無し")）。
                  CLI が自前のツール（Bash / WebSearch など）で動くため、Verantyx の
                  画面操作・画面変化検知・記憶の各層を経由しません。実行結果を検証できない\
                ので、この経路ではなく API キー経路の利用を推奨します。
                """)
        }

        let caps = Capabilities(path: path, version: version,
                                supportsPrint: hasPrint, supportsModelFlag: hasModel,
                                supportsStreamJSON: hasStream,
                                supportsSystemPrompt: hasSystemPrompt,
                                supportsToolDenial: hasToolDenial,
                                supportsStrictMCP: hasStrictMCP,
                                supportsJSONOutput: hasJSONOutput,
                                notes: notes)
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
        /// What the turn actually cost, straight from the CLI. Nil when the
        /// CLI could not report it.
        var usage: TurnUsage?
    }

    // MARK: - Measuring what a turn costs
    //
    // Everything said about this route's cost so far has been inference from
    // the shape of the calls: history is re-flattened every turn, nothing is
    // trimmed, `--resume` is a comment rather than code, so the prefix differs
    // each time and lands as cache CREATION rather than cache READ. That
    // reasoning is sound and still not a measurement.
    //
    // `--output-format json` ends the guessing: the CLI reports per-call token
    // counts split by cache behaviour, plus its own cost figure. The split is
    // the number that matters, because the gap between the two paths is not
    // 1.25× over uncached input — it is cache-write against cache-read, and
    // those differ by more than an order of magnitude. Whether this route is
    // actually paying that, and how much of the history it re-creates each
    // turn, stops being a matter of opinion the moment these fields are read.
    //
    // `session_id` is captured in the same parse because it is free here and
    // is exactly what `--resume` needs to make the prefix stable.
    struct TurnUsage: Equatable {
        let inputTokens: Int
        let cacheCreationTokens: Int
        let cacheReadTokens: Int
        let outputTokens: Int
        let costUSD: Double
        let turns: Int
        let sessionID: String?

        /// Tokens the model saw, however they were billed.
        var totalInput: Int { inputTokens + cacheCreationTokens + cacheReadTokens }

        /// Share of the prefix that had to be written rather than read. High
        /// here means the prompt is changing shape every turn — the signature
        /// of a flattened, untrimmed history.
        var cacheWriteShare: Double {
            let cached = cacheCreationTokens + cacheReadTokens
            return cached == 0 ? 0 : Double(cacheCreationTokens) / Double(cached)
        }

        var summary: String {
            let cost = String(format: "%.4f", costUSD)
            let share = Int((cacheWriteShare * 100).rounded())
            return "入力 \(totalInput) tok"
                + "（新規 \(inputTokens) / キャッシュ書込 \(cacheCreationTokens) / 読出 \(cacheReadTokens)）"
                + " ・ 出力 \(outputTokens) tok ・ $\(cost)"
                + " ・ 書込率 \(share)%"
        }
    }

    /// The most recent measured turn, for anything that wants to show it.
    private(set) var lastUsage: TurnUsage?

    // MARK: - Transient failure
    //
    // A 529 means the request never reached a model: nothing was computed,
    // nothing was charged, and the condition usually clears in seconds.
    // Surfacing it straight to the user turns a hiccup into a dead run someone
    // has to notice and restart by hand — the worst outcome for the unattended
    // operation this app is built around.

    nonisolated static let transientRetries = 3

    /// Widening gaps. An overloaded service is made worse by clients that
    /// retry immediately and in lockstep.
    nonisolated static let retryDelays: [Double] = [2, 6, 15]

    /// Whether a failure says "not right now" rather than "not like this".
    /// Quota exhaustion is deliberately excluded: it is a real limit, and
    /// retrying it three times only delays telling the user the truth.
    nonisolated static func isTransient(_ message: String) -> Bool {
        let m = message.lowercased()
        let permanent = ["usage limit", "quota", "credit balance", "insufficient",
                         "not logged in", "invalid api key", "authentication"]
        if permanent.contains(where: { m.contains($0) }) { return false }
        let transient = ["529", "overloaded", "503", "502", "504",
                         "429", "rate limit", "temporarily", "try again"]
        return transient.contains(where: { m.contains($0) })
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

        // Replace rather than append. Appending leaves the CLI's own prompt —
        // and with it the belief that it is a coding agent holding a shell —
        // ahead of Verantyx's rules, which is how a request to open Safari
        // turned into `open -a Safari` instead of [USE_APP].
        if let systemPrompt, !systemPrompt.isEmpty {
            args += [caps.supportsSystemPrompt ? "--system-prompt" : "--append-system-prompt",
                     systemPrompt]
        }

        // Ask for the measured numbers. Placed before the variadic deny list,
        // which swallows anything that follows it.
        if caps.supportsJSONOutput { args += ["--output-format", "json"] }

        // Do not inherit the user's MCP servers. They are a tool surface this
        // app did not offer, cannot document to the model, and cannot verify.
        if caps.supportsStrictMCP { args.append("--strict-mcp-config") }

        // Last, because the flag is variadic: anything placed after it risks
        // being read as another tool name.
        if caps.supportsToolDenial {
            args.append("--disallowedTools")
            args += Self.toolDenyList
        }

        var lastTransient = ""
        for attempt in 0...Self.transientRetries {
        if attempt > 0 {
            let wait = Self.retryDelays[min(attempt - 1, Self.retryDelays.count - 1)]
            try? await Task.sleep(nanoseconds: UInt64(wait * 1_000_000_000))
        }
        do {
            let result = try await run(path: caps.path, args: args, input: prompt)
            // With --output-format json the reply is a field inside an
            // envelope, not the whole of stdout. A parse failure falls back to
            // the raw text rather than showing the user a wall of JSON.
            let measured = caps.supportsJSONOutput ? Self.parseEnvelope(result.out) : nil
            if let usage = measured?.usage { lastUsage = usage }
            let text = (measured?.text ?? result.out)
                .trimmingCharacters(in: .whitespacesAndNewlines)
            if result.status != 0 {
                // The CLI's own message is more useful than anything this
                // layer could invent — not logged in, over quota, bad model.
                // "exit code 1" names nothing anyone can act on. The CLI
                // writes its reason to stderr; when it writes nothing, the
                // common causes are knowable and worth listing rather than
                // leaving the user to guess — with the exact command to run by
                // hand, which is the fastest way to see the real message.
                let err = result.err.trimmingCharacters(in: .whitespacesAndNewlines)
                let reason = err.isEmpty ? text : err
                if Self.isTransient(reason), attempt < Self.transientRetries {
                    lastTransient = reason
                    continue
                }
                let tries = attempt > 0 ? "（\(attempt + 1) 回試行）" : ""
                if !reason.isEmpty {
                    return Reply(text: "claude CLI: \(reason)\(tries)", isError: true)
                }
                let modelFlag = model.map { " --model \($0)" } ?? ""
                return Reply(text: """
                    claude CLI が終了コード \(result.status) を返しました（stderr は空でした）。
                    考えられる原因:
                      • Claude Code にログインしていない → ターミナルで `claude` を起動してログイン
                      • 指定したモデルが使えない → 今回の指定: \(model ?? "(既定)")
                      • 使用量の上限
                    同じ条件を手元で再現するには:
                      \(caps.path) -p "test"\(modelFlag)
                    """, isError: true)
            }
            // An un-silenceable CLI still answers, but what it did to produce
            // the answer happened outside this app. Say so on the turn rather
            // than only in a settings pane nobody is looking at.
            guard caps.canBeSilenced else {
                return Reply(text: """
                    ⚠️ この claude CLI はツールを無効化できないバージョンのため、CLI 自身の\
                    エージェントとして実行されました。以下の内容は Verantyx の画面操作・\
                    画面変化検知・記憶の各層を経由していないため、検証されていません。

                    """ + text, isError: false, usage: measured?.usage)
            }
            return Reply(text: text, isError: false, usage: measured?.usage)
        } catch {
            return Reply(text: "claude CLI を実行できません: \(error.localizedDescription)",
                         isError: true)
        }
        }
        // Every attempt hit the same "not right now". Say how many, so the
        // difference between a blip and an outage is visible.
        return Reply(text: """
            claude CLI: \(lastTransient)
            \(Self.transientRetries + 1) 回試行しましたが回復しませんでした。\
            サーバー側の一時的な過負荷です。時間をおいて再実行してください。
            状況: https://status.claude.com
            """, isError: true)
    }

    /// Pull the reply and the measured usage out of `--output-format json`.
    ///
    /// Deliberately tolerant: an envelope whose shape changes with a CLI
    /// version must not cost the user their answer. Anything unreadable
    /// returns nil and the caller falls back to raw stdout — losing the
    /// measurement, never the reply.
    nonisolated static func parseEnvelope(_ stdout: String) -> (text: String?, usage: TurnUsage?)? {
        guard let data = stdout.data(using: .utf8),
              let root = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
        else { return nil }

        let text = root["result"] as? String
        guard let u = root["usage"] as? [String: Any] else { return (text, nil) }
        func count(_ key: String) -> Int { (u[key] as? Int) ?? 0 }

        let usage = TurnUsage(
            inputTokens: count("input_tokens"),
            cacheCreationTokens: count("cache_creation_input_tokens"),
            cacheReadTokens: count("cache_read_input_tokens"),
            outputTokens: count("output_tokens"),
            costUSD: (root["total_cost_usd"] as? Double) ?? 0,
            turns: (root["num_turns"] as? Int) ?? 0,
            sessionID: root["session_id"] as? String)
        return (text, usage)
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
