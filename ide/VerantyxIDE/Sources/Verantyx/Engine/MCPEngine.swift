import Foundation
import SwiftUI

/// Persistent storage location for the bundled `vera-memory` binary's
/// knowledge store -- mirrors `JGenPaths` (`JGenConverter.swift`)'s
/// Application Support pattern. The store (`vera_store.json`) is user/
/// session-accumulated data, not app code, so it lives outside both the
/// app bundle and any hardcoded dev-checkout path.
enum VeraMemoryPaths {
    static var appSupportDir: URL {
        let base = (try? FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true))
            ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support")
        return base.appendingPathComponent("Verantyx/vera-memory", isDirectory: true)
    }

    // ── Memory profiles ──────────────────────────────────────────────
    // One Mac can keep several independent memories ("default" plus named
    // stores under stores/<name>) and point BOTH the vera-memory MCP store
    // and the IDE's eternal-vector store at the active one. The active
    // name lives in UserDefaults so a fresh launch — and the exported MCP
    // config — follow the same choice.
    static let profileDefaultsKey = "vera_memory_profile"

    static var activeProfile: String {
        UserDefaults.standard.string(forKey: profileDefaultsKey) ?? "default"
    }

    static func profileDir(_ name: String) -> URL {
        name == "default"
            ? appSupportDir
            : appSupportDir.appendingPathComponent("stores/\(name)", isDirectory: true)
    }

    /// default + every named store on disk.
    static func listProfiles() -> [String] {
        var names = ["default"]
        let stores = appSupportDir.appendingPathComponent("stores")
        if let subs = try? FileManager.default.contentsOfDirectory(atPath: stores.path) {
            names += subs.filter { !$0.hasPrefix(".") }.sorted()
        }
        return names
    }

    /// Creates an empty named store. Returns the sanitized name, or nil if
    /// nothing valid remained after sanitizing.
    @discardableResult
    static func createProfile(_ rawName: String) -> String? {
        let name = String(rawName.lowercased().map { c -> Character in
            (c.isLetter || c.isNumber || c == "-" || c == "_") ? c : "-"
        }).trimmingCharacters(in: CharacterSet(charactersIn: "-_"))
        guard !name.isEmpty, name != "default" else { return nil }
        try? FileManager.default.createDirectory(
            at: profileDir(name), withIntermediateDirectories: true)
        return name
    }

    static var storeFile: URL {
        let dir = profileDir(activeProfile)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir.appendingPathComponent("vera_store.json")
    }

    /// Resolve the portable bundled `vera-memory` binary relative to the
    /// running `.app` — never a developer-machine checkout path. Prefers
    /// `Contents/MacOS/` (Release/DMG embed phase), then `Contents/Resources/`.
    static func resolveBundledBinary() -> URL? {
        let fm = FileManager.default
        var candidates: [URL] = []
        if let exeDir = Bundle.main.executableURL?.deletingLastPathComponent() {
            candidates.append(exeDir.appendingPathComponent("vera-memory"))
        }
        candidates.append(
            Bundle.main.bundleURL
                .appendingPathComponent("Contents")
                .appendingPathComponent("MacOS")
                .appendingPathComponent("vera-memory")
        )
        if let resources = Bundle.main.resourceURL {
            candidates.append(resources.appendingPathComponent("vera-memory"))
        }
        // De-dupe while preserving order.
        var seen = Set<String>()
        for url in candidates {
            let path = url.path
            guard seen.insert(path).inserted else { continue }
            if fm.isExecutableFile(atPath: path) { return url }
        }
        return nil
    }

    /// Stdio MCP launch command for the bundled binary + Application Support store.
    static func bundledMCPCommand(binary: URL) -> String {
        "\"\(binary.path)\" --store \"\(storeFile.path)\" mcp"
    }

    /// The `mcpServers` JSON snippet other IDEs paste to reach the SAME
    /// bundled binary and the SAME store this app uses. One shape covers
    /// Claude Code (`.mcp.json`), Claude Desktop
    /// (`claude_desktop_config.json`) and Cursor (`.cursor/mcp.json`).
    ///
    /// Exists because the IDE itself no longer needs Settings › MCP to
    /// reach Vera — Vera-a runs natively in-process — so the MCP surface's
    /// remaining job is exporting Vera's memory to OTHER tools.
    static func externalMCPConfigJSON() -> String? {
        guard let binary = resolveBundledBinary() else { return nil }
        // vera-jgen-memory is the memory ORGAN (eternal recall/remember
        // through the pinned small JGEN) served over HTTP by the running
        // IDE's JGenAgentServer — see its handleMCP. Port 8766 is the
        // server's preferred bind; it only moves if something else took it.
        return """
        {
          "mcpServers": {
            "vera-memory": {
              "command": "\(binary.path)",
              "args": ["--store", "\(storeFile.path)", "mcp"]
            },
            "vera-jgen-memory": {
              "type": "http",
              "url": "http://127.0.0.1:8766/mcp"
            }
          }
        }
        """
    }

    /// True when the helper is Hardened Runtime but lacks
    /// `disable-library-validation` — the pre-97e8fd230 DMG failure mode
    /// ("different Team IDs" loading PyInstaller's extracted Python.framework).
    static func missingLibraryValidationEntitlement(at binary: URL) -> Bool {
        guard isHardenedRuntime(at: binary) else { return false }
        let ents = codesignEntitlementsXML(at: binary) ?? ""
        return !ents.contains("disable-library-validation")
    }

    /// User-facing install guidance when an old notarized DMG is detected.
    static var outdatedHardenedRuntimeMessage: String {
        """
        Bundled vera-memory is notarized (Hardened Runtime) but missing com.apple.security.cs.disable-library-validation.
        That is the pre-fix DMG: PyInstaller dies with "mapping process and mapped file have different Team IDs".
        Replace /Applications/Verantyx.app with VerantyxIDE-0.0.0-dev-98+ (CI artifact VerantyxIDE-macOS-App from commit 97e8fd230 or later), reopen Verantyx, then reconnect vera-memory.
        Verify: codesign -d --entitlements :- /Applications/Verantyx.app/Contents/MacOS/vera-memory | grep disable-library-validation
        """
    }

    /// Rewrite Team-ID / library-validation launch failures into actionable text.
    static func annotateLaunchFailure(_ message: String) -> String {
        let markers = ["different Team IDs", "disable-library-validation", "Failed to load Python shared library"]
        guard markers.contains(where: { message.contains($0) }) else { return message }
        return message + "\n\n" + outdatedHardenedRuntimeMessage
    }

    private static func isHardenedRuntime(at binary: URL) -> Bool {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/codesign")
        p.arguments = ["-dv", "--verbose=2", binary.path]
        let err = Pipe()
        p.standardOutput = Pipe()
        p.standardError = err
        do { try p.run() } catch { return false }
        p.waitUntilExit()
        let text = String(data: err.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
        return text.contains("flags=0x10000(runtime)") || text.contains("(runtime)")
    }

    private static func codesignEntitlementsXML(at binary: URL) -> String? {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/codesign")
        p.arguments = ["-d", "--entitlements", ":-", binary.path]
        let out = Pipe()
        let err = Pipe()
        p.standardOutput = out
        p.standardError = err
        do { try p.run() } catch { return nil }
        p.waitUntilExit()
        let data = out.fileHandleForReading.readDataToEndOfFile()
        return String(data: data, encoding: .utf8)
    }
}

// MARK: - MCPEngine
//
// Model Context Protocol client for Verantyx IDE.
//
// Persistent stdio design (fixes Puppeteer / slow-npx):
//   Each enabled server owns ONE long-running Process, started lazily on first
//   use and reused forever. The browser stays open between calls. No cold-start.
//
// HTTP design:
//   Uses a dedicated URLSession with no timeout so long-running HTTP tool calls
//   (e.g. Playwright, Puppeteer-HTTP) never time out at the network layer.
//
// Kill Switch:
//   killActiveCall() → Task.cancel(). Works for both transports.
//   subprocess is terminated only when disconnect() / removeServer() is called.

// MARK: - Data models

struct MCPServerConfig: Codable, Identifiable, Equatable {
    var id: UUID
    var name: String
    var transport: Transport
    var command: String          // stdio: e.g. "npx -y @modelcontextprotocol/server-puppeteer"
    var url: String              // http:  e.g. "http://localhost:3000"
    var envVars: [String: String]
    var isEnabled: Bool
    var mode: ExecutionMode

    enum Transport: String, Codable, CaseIterable {
        case stdio = "stdio"
        case http  = "http"
    }

    enum ExecutionMode: String, Codable, CaseIterable {
        case ai    = "AI Priority"   // no auto-timeout — runs until done or user kills
        case human = "Human Mode"    // 60 s outer deadline
    }

    init(id: UUID = UUID(), name: String, transport: Transport = .stdio,
         command: String = "", url: String = "", envVars: [String: String] = [:],
         isEnabled: Bool = true, mode: ExecutionMode = .ai) {
        self.id = id; self.name = name; self.transport = transport
        self.command = command; self.url = url; self.envVars = envVars
        self.isEnabled = isEnabled; self.mode = mode
    }

    static let examples: [MCPServerConfig] = [
        MCPServerConfig(name: "Filesystem", transport: .stdio,
                        command: "npx -y @modelcontextprotocol/server-filesystem /",
                        mode: .ai),
        MCPServerConfig(name: "GitHub", transport: .stdio,
                        command: "npx -y @modelcontextprotocol/server-github",
                        envVars: ["GITHUB_PERSONAL_ACCESS_TOKEN": ""],
                        mode: .ai),
        MCPServerConfig(name: "Puppeteer", transport: .stdio,
                        command: "npx -y @modelcontextprotocol/server-puppeteer",
                        mode: .ai),
        MCPServerConfig(name: "Brave Search", transport: .stdio,
                        command: "npx -y @modelcontextprotocol/server-brave-search",
                        envVars: ["BRAVE_API_KEY": ""],
                        mode: .human),
        MCPServerConfig(name: "Local HTTP", transport: .http,
                        url: "http://localhost:3000",
                        mode: .human),
    ]
}

struct MCPTool: Identifiable, Codable {
    let id: UUID
    let name: String
    let description: String
    let inputSchema: [String: AnyCodable]
    let serverName: String

    init(name: String, description: String, inputSchema: [String: AnyCodable] = [:], serverName: String) {
        self.id = UUID(); self.name = name; self.description = description
        self.inputSchema = inputSchema; self.serverName = serverName
    }
}

struct AnyCodable: Codable {
    let value: Any
    init(_ value: Any) { self.value = value }
    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if let v = try? c.decode(Bool.self)               { value = v; return }
        if let v = try? c.decode(Int.self)                { value = v; return }
        if let v = try? c.decode(Double.self)             { value = v; return }
        if let v = try? c.decode(String.self)             { value = v; return }
        if let v = try? c.decode([String: AnyCodable].self) { value = v; return }
        if let v = try? c.decode([AnyCodable].self)       { value = v; return }
        value = NSNull()
    }
    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch value {
        case let v as Bool:               try c.encode(v)
        case let v as Int:                try c.encode(v)
        case let v as Double:             try c.encode(v)
        case let v as String:             try c.encode(v)
        case let v as [String: AnyCodable]: try c.encode(v)
        case let v as [AnyCodable]:       try c.encode(v)
        default:                          try c.encodeNil()
        }
    }
}

// MARK: - MCPCallRecord

struct MCPCallRecord: Identifiable {
    let id = UUID()
    let serverName: String
    let toolName: String
    let startTime: Date
    var status: Status
    var elapsedSeconds: Int { Int(Date().timeIntervalSince(startTime)) }
    var task: Task<String, Error>?

    enum Status { case running, completed, timedOut, cancelled, failed(String) }

    var statusLabel: String {
        switch status {
        case .running:        return "RUNNING  \(elapsedSeconds)s"
        case .completed:      return "DONE"
        case .timedOut:       return "TIMEOUT"
        case .cancelled:      return "KILLED"
        case .failed(let e):  return "ERR: \(e.prefix(240))"
        }
    }

    var statusColor: Color {
        switch status {
        case .running:   return Color(red: 0.9, green: 0.7, blue: 0.2)
        case .completed: return Color(red: 0.3, green: 0.9, blue: 0.5)
        case .timedOut:  return .orange
        case .cancelled: return .red
        case .failed:    return Color(red: 0.9, green: 0.4, blue: 0.4)
        }
    }
}

// MARK: - nonisolated helper (callable from any Task or actor)

/// Extracts text content from an MCP JSON-RPC response.
/// nonisolated free function so it compiles inside Task.detached / actor methods alike.
func mcpExtractText(from json: [String: Any]) -> String {
    if let result = json["result"] as? [String: Any] {
        if let content = result["content"] as? [[String: Any]] {
            let text = content.compactMap { block -> String? in
                guard block["type"] as? String == "text" else { return nil }
                return block["text"] as? String
            }.joined(separator: "\n")
            if !text.isEmpty { return text }
        }
        if let text = result["text"] as? String { return text }
    }
    if let err = json["error"] as? [String: Any] {
        return "[MCP Error] \(err["message"] as? String ?? "Unknown")"
    }
    return json.description
}

// MARK: - URLSession without timeout (shared across MCP HTTP calls)

private let mcpNoTimeoutSession: URLSession = {
    let cfg = URLSessionConfiguration.default
    cfg.timeoutIntervalForRequest  = .infinity
    cfg.timeoutIntervalForResource = .infinity
    return URLSession(configuration: cfg)
}()

// MARK: - StdioSession
//
// Persistent actor — owns one Process per MCP server.
// Serialises all tool calls via Swift's actor model (no mutex needed).

actor StdioSession {

    private let server: MCPServerConfig

    private var process: Process?
    private var stdinHandle: FileHandle?
    private var stdoutHandle: FileHandle?
    private var stderrHandle: FileHandle?
    private var nextId: Int = 10        // RPC IDs; 1-2 reserved for handshake
    private var isReady = false

    // Captures the subprocess's stderr so launch/write failures can surface a real
    // reason (e.g. a Python traceback) instead of just "Write failed after auto-restart".
    // Lock-backed so the FileHandle readabilityHandler can append synchronously —
    // an actor-hop `Task { await }` raced and left Team-ID dyld stderr empty.
    private let stderrCapture = StderrCapture()

    private func recentStderr() -> String? {
        stderrCapture.text()
    }

    /// Thread-safe stderr ring buffer for Process readabilityHandler.
    private final class StderrCapture: @unchecked Sendable {
        private let lock = NSLock()
        private var buffer = Data()
        private let limit = 16_384

        func clear() {
            lock.lock(); defer { lock.unlock() }
            buffer.removeAll(keepingCapacity: true)
        }

        func append(_ chunk: Data) {
            guard !chunk.isEmpty else { return }
            lock.lock(); defer { lock.unlock() }
            buffer.append(chunk)
            if buffer.count > limit {
                buffer.removeFirst(buffer.count - limit)
            }
        }

        func text() -> String? {
            lock.lock(); defer { lock.unlock() }
            guard !buffer.isEmpty else { return nil }
            let trimmed = (String(data: buffer, encoding: .utf8) ?? "")
                .trimmingCharacters(in: .whitespacesAndNewlines)
            return trimmed.isEmpty ? nil : trimmed
        }
    }

    // AsyncStream continuation — readabilityHandler pushes chunks here.
    // NOT weak (Continuation is a struct, not a class).
    private var continuation: AsyncStream<Data>.Continuation?

    init(server: MCPServerConfig) {
        self.server = server
    }

    // ── Public API ──────────────────────────────────────────────────────────

    /// 起動中の一本。**actor は await のたびに他の呼びが入れる** ので、
    /// これが無いと最初の二つの呼びがそれぞれサーバーを起こし、後から
    /// 起こした方が先の握手中のプロセスを殺します。殺された側は
    /// 「No initialize response」と報告する — サーバーは動いているのに。
    /// (2026-08-23 実測: 起動のたびにサーバー2本、3回中3回)
    private var starting: Task<Void, Error>?

    func ensureRunning() async throws {
        if isReady, let p = process, p.isRunning { return }
        if let inFlight = starting {
            try await inFlight.value
            return
        }
        let task = Task { try await self.startProcess() }
        starting = task
        defer { starting = nil }
        try await task.value
    }

    /// Send one JSON-RPC request and return the matching response.
    /// If the process has crashed it is restarted transparently (once).
    func callTool(method: String, params: [String: Any], deadline: Date) async throws -> [String: Any] {
        try await ensureRunning()

        let rpcId = nextId
        nextId += 1

        let req: [String: Any] = [
            "jsonrpc": "2.0", "id": rpcId,
            "method": method, "params": params
        ]

        if !safeWrite(req) {
            // Likely crashed — restart once and retry
            try await startProcess()
            guard safeWrite(req) else {
                let stderr = recentStderr().map { "\nstderr: \($0)" } ?? ""
                throw MCPError.processLaunchFailed(
                    VeraMemoryPaths.annotateLaunchFailure("Write failed after auto-restart\(stderr)"))
            }
        }

        return try await readResponse(rpcId: rpcId, deadline: deadline)
    }

    func terminate() {
        stdoutHandle?.readabilityHandler = nil
        stderrHandle?.readabilityHandler = nil
        stderrHandle = nil
        continuation?.finish()
        continuation = nil
        process?.terminate()
        process = nil
        isReady = false
    }

    // ── Private: process lifecycle ──────────────────────────────────────────

    private func startProcess() async throws {
        // Tear down stale state
        process?.terminate()
        process = nil
        stdinHandle = nil
        stdoutHandle = nil
        isReady = false
        continuation?.finish()
        continuation = nil
        stderrCapture.clear()

        _ = StdioSession.sigpipeInstalled

        let p = Process()
        let stdinPipe  = Pipe()
        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()

        p.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        p.arguments     = tokenise(server.command)

        // ENV 構築: プロセス ENV + PATH 拡張 + Keychain 解決済み API キー
        var env = ProcessInfo.processInfo.environment
        env["PATH"] = "/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin:" + (env["PATH"] ?? "")
        // Keychain から解決した値を注入（空の env vars を上書き）
        let resolvedEnv = MCPKeychainStore.resolvedEnv(for: server)
        resolvedEnv.forEach { env[$0.key] = $0.value }
        p.environment = env

        p.standardInput  = stdinPipe
        p.standardOutput = stdoutPipe
        p.standardError  = stderrPipe
        p.terminationHandler = { [weak self] _ in
            Task { await self?.handleTermination() }
        }

        do { try p.run() } catch {
            throw MCPError.processLaunchFailed(
                VeraMemoryPaths.annotateLaunchFailure(error.localizedDescription))
        }

        process      = p
        stdinHandle  = stdinPipe.fileHandleForWriting
        stdoutHandle = stdoutPipe.fileHandleForReading
        stderrHandle = stderrPipe.fileHandleForReading

        // Wire readabilityHandler → AsyncStream
        // Note: cont is a VALUE (struct) so we capture it directly, not with [weak].
        let (stream, cont) = AsyncStream<Data>.makeStream()
        self.continuation = cont

        stdoutPipe.fileHandleForReading.readabilityHandler = { [weak p] fh in
            let chunk = fh.availableData
            if chunk.isEmpty {
                // **空読みは EOF とは限らない。** 起動に10秒かかる凍結
                // バイナリ (PyInstaller onefile) では、書き手が生きたまま
                // 0 バイトで起きることがあります。それを EOF と読むと、
                // 実際には応答できるサーバーに対して
                // 「No initialize response」と誤報します
                // (2026-08-23 実測: プロセスは生きたまま画面だけ
                //  UNKNOWN_ENGINE_UNREACHABLE になった)。
                // 本当に終わったのかはプロセスに訊く。取りこぼしても
                // terminationHandler が finish するので止まりません。
                if p?.isRunning != true {
                    cont.finish()
                    fh.readabilityHandler = nil
                }
            } else {
                cont.yield(chunk)
            }
        }

        // Capture stderr synchronously (see StderrCapture) so Team-ID / dyld
        // failures are present when performHandshake throws.
        let stderrCapture = self.stderrCapture
        stderrPipe.fileHandleForReading.readabilityHandler = { fh in
            let chunk = fh.availableData
            guard !chunk.isEmpty else {
                fh.readabilityHandler = nil
                return
            }
            stderrCapture.append(chunk)
        }

        do {
            // 凍結バイナリ (81MB, PyInstaller onefile) の冷起動は実測
            // 10.3 秒。GUI から初回に起動すると Gatekeeper の検査が
            // 乗るので、20 秒では足りないことがあります。
            try await performHandshake(stream: stream, maxWait: 45.0)
        } catch let error as MCPError {
            // Give the readabilityHandler a beat to flush dying-process stderr.
            try? await Task.sleep(nanoseconds: 80_000_000)
            let stderr = recentStderr()
            if case .processLaunchFailed(let msg) = error {
                var combined = msg
                if let stderr, !msg.contains(stderr) {
                    combined = "\(msg)\nstderr: \(stderr)"
                }
                throw MCPError.processLaunchFailed(VeraMemoryPaths.annotateLaunchFailure(combined))
            } else if let stderr {
                throw MCPError.processLaunchFailed(
                    VeraMemoryPaths.annotateLaunchFailure(
                        "\(error.localizedDescription)\nstderr: \(stderr)"))
            }
            throw error
        }
        isReady = true
    }

    private func performHandshake(stream: AsyncStream<Data>, maxWait: Double) async throws {
        // Prefer a widely-supported version; servers may negotiate newer
        // (mcp Python SDK lists 2024-11-05 … 2025-11-25). We accept any
        // successful initialize result and then send notifications/initialized.
        let initReq: [String: Any] = [
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": [
                "protocolVersion": "2024-11-05",
                "capabilities":    ["tools": [:], "resources": [:]],
                "clientInfo":      ["name": "Verantyx", "version": "0.1"]
            ]
        ]
        guard safeWrite(initReq) else {
            let stderr = recentStderr().map { "\nstderr: \($0)" } ?? ""
            throw MCPError.processLaunchFailed(
                VeraMemoryPaths.annotateLaunchFailure("Process exited before initialize\(stderr)"))
        }

        var buf = Data()
        let started = Date()
        var initResponse: [String: Any]?

        // **黙ったサーバーで固まらないようにする。** 締切の判定を
        // チャンク到着の中に置いていたので、一度も喋らないサーバーでは
        // 判定自体が回らず、時間切れが報告されませんでした。
        let reader = Task { () -> [String: Any]? in
            for await chunk in stream {
                buf.append(chunk)
                let (lines, remainder) = splitLines(buf)
                buf = remainder
                for line in lines {
                    if let json = parseJSON(line),
                       let idValue = json["id"], "\(idValue)" == "1" {
                        return json
                    }
                }
                try Task.checkCancellation()
            }
            return nil
        }
        let timer = Task {
            try await Task.sleep(nanoseconds: UInt64(maxWait * 1_000_000_000))
            reader.cancel()
        }
        initResponse = try? await reader.value
        timer.cancel()

        if initResponse == nil, Date().timeIntervalSince(started) >= maxWait {
            let stderr = recentStderr().map { "\nstderr: \($0)" } ?? ""
            throw MCPError.processLaunchFailed(
                VeraMemoryPaths.annotateLaunchFailure(
                    "Initialize timed out (>\(Int(maxWait))s). "
                    + "Server may not be installed.\(stderr)"))
        }

        guard let initResponse else {
            // **なぜ来なかったのかを書く。** 「返事が無い」だけだと、
            // 落ちたのか・黙っているのか・こちらが降りたのかが区別
            // できず、直す先が決まりません。
            let stderr = recentStderr().map { "\nstderr: \($0)" } ?? ""
            let alive = (process?.isRunning ?? false)
            let secs = String(format: "%.1f",
                              Date().timeIntervalSince(started))
            throw MCPError.processLaunchFailed(
                VeraMemoryPaths.annotateLaunchFailure(
                    "No initialize response after \(secs)s "
                    + "(process \(alive ? "still running" : "exited"), "
                    + "read \(buf.count) unparsed bytes)\(stderr)"))
        }
        if let err = initResponse["error"] as? [String: Any] {
            let msg = (err["message"] as? String) ?? String(describing: err)
            throw MCPError.processLaunchFailed("Initialize rejected: \(msg)")
        }
        guard initResponse["result"] != nil else {
            throw MCPError.processLaunchFailed("Initialize response missing result")
        }

        let notif: [String: Any] = ["jsonrpc": "2.0", "method": "notifications/initialized"]
        safeWrite(notif)
    }

    // ── Private: response reading ───────────────────────────────────────────

    /// Drain the stream after each call by reassigning the readabilityHandler to a
    /// fresh AsyncStream so each callTool() gets its own isolated iterator.
    private func readResponse(rpcId: Int, deadline: Date) async throws -> [String: Any] {
        guard let fh = stdoutHandle else { throw MCPError.noResponse }

        // Create a fresh stream for this specific call's response
        let (stream, freshCont) = AsyncStream<Data>.makeStream()
        self.continuation = freshCont

        fh.readabilityHandler = { handle in
            let chunk = handle.availableData
            if chunk.isEmpty {
                freshCont.finish()
                handle.readabilityHandler = nil
            } else {
                freshCont.yield(chunk)
            }
        }

        var buf = Data()
        for await chunk in stream {
            buf.append(chunk)
            let (lines, remainder) = splitLines(buf)
            buf = remainder
            for line in lines {
                if let json = parseJSON(line),
                   let idValue = json["id"] {
                    // Compare both Int and String forms of the id
                    if "\(idValue)" == "\(rpcId)" {
                        return json
                    }
                }
            }
            if Date() > deadline { throw MCPError.timeout }
            try Task.checkCancellation()
        }

        throw MCPError.noResponse
    }

    // ── Private: termination handler ────────────────────────────────────────

    private func handleTermination() {
        isReady = false
        continuation?.finish()
        continuation = nil
        stdoutHandle?.readabilityHandler = nil
        stderrHandle?.readabilityHandler = nil
        stderrHandle = nil
    }

    // ── Private: helpers ────────────────────────────────────────────────────

    @discardableResult
    private func safeWrite(_ obj: [String: Any]) -> Bool {
        guard let p = process, p.isRunning, let fh = stdinHandle else { return false }
        guard let data = try? JSONSerialization.data(withJSONObject: obj),
              let line = String(data: data, encoding: .utf8),
              let bytes = (line + "\n").data(using: .utf8) else { return false }
        do {
            try fh.write(contentsOf: bytes)
            return true
        } catch { return false }
    }

    private func parseJSON(_ s: String) -> [String: Any]? {
        guard let d = s.data(using: .utf8) else { return nil }
        return try? JSONSerialization.jsonObject(with: d) as? [String: Any]
    }

    private func splitLines(_ data: Data) -> ([String], Data) {
        guard let str = String(data: data, encoding: .utf8) else { return ([], data) }
        var parts = str.components(separatedBy: "\n")
        let remainder = parts.removeLast()         // last element may be partial
        let complete = parts.filter { !$0.trimmingCharacters(in: .whitespaces).isEmpty }
        return (complete, remainder.data(using: .utf8) ?? Data())
    }

    private func tokenise(_ command: String) -> [String] {
        var tokens: [String] = []
        var current = ""
        var inQ: Character? = nil
        for ch in command {
            if let q = inQ {
                if ch == q { inQ = nil } else { current.append(ch) }
            } else if ch == "\"" || ch == "'" {
                inQ = ch
            } else if ch == " " {
                if !current.isEmpty { tokens.append(current); current = "" }
            } else {
                current.append(ch)
            }
        }
        if !current.isEmpty { tokens.append(current) }
        return tokens
    }

    private static let sigpipeInstalled: Bool = {
        signal(SIGPIPE, SIG_IGN)
        return true
    }()
}

// MARK: - MCPEngine

@MainActor
final class MCPEngine: ObservableObject {

    static let shared = MCPEngine()

    // MARK: - Published state

    @Published var servers: [MCPServerConfig] = [] {
        didSet { saveServers() }
    }
    @Published var connectedTools: [MCPTool] = []
    @Published var activeCall: MCPCallRecord?
    @Published var callHistory: [MCPCallRecord] = []
    @Published var connectionStatus: [UUID: ConnectionStatus] = [:]

    enum ConnectionStatus { case disconnected, connecting, connected, error(String) }

    @Published var currentExecutionMode: MCPServerConfig.ExecutionMode = .human

    // One persistent session per server UUID
    private var stdioSessions: [UUID: StdioSession] = [:]

    private static let storageKey = "mcp_servers_v1"

    func setMode(_ mode: MCPServerConfig.ExecutionMode) {
        currentExecutionMode = mode
    }

    init() { loadServers() }

    /// 起動時に、保存済みで有効なサーバーへ接続し直す。
    ///
    /// これが無かったため、`connectAll` はユーザーが MCP パネルを開いて
    /// ボタンを押したときにしか走らなかった。つまり毎回の起動で MCP ツールは
    /// ゼロ本から始まり、AgentLoop や CloudAPIClient が `connectedTools` を
    /// 読む時点では空だった — 設定済みのサーバーが、UI を訪れるまで存在しない
    /// のと同じ状態になる。
    ///
    /// 失敗しても投げない。到達不能なサーバーは `connectionStatus` に
    /// `.error` として残り、MCP パネルにそのまま表示される。起動を止めたり
    /// 黙って消したりするより、そこに理由が出ている方が直せる。
    func autoConnectOnLaunch() async {
        guard !hasAutoConnected else { return }
        hasAutoConnected = true
        await connectAll()
    }

    private var hasAutoConnected = false

    // MARK: - Server CRUD

    func addServer(_ config: MCPServerConfig) { servers.append(config) }

    func removeServer(id: UUID) {
        if let session = stdioSessions.removeValue(forKey: id) {
            Task { await session.terminate() }
        }
        // Remove tools before removing the server entry
        if let name = servers.first(where: { $0.id == id })?.name {
            connectedTools.removeAll { $0.serverName == name }
        }
        servers.removeAll { $0.id == id }
        connectionStatus.removeValue(forKey: id)
    }

    func updateServer(_ config: MCPServerConfig) {
        if let idx = servers.firstIndex(where: { $0.id == config.id }) {
            servers[idx] = config
        }
    }

    /// サーバーのプロセスを強制終了して再接続する（再起動ボタン）
    func restartServer(id: UUID) async {
        // 既存セッションをクリーンに終了
        if let session = stdioSessions.removeValue(forKey: id) {
            await session.terminate()
        }
        connectionStatus[id] = .disconnected
        // ツールリストをクリアして再取得
        if let server = servers.first(where: { $0.id == id }) {
            connectedTools.removeAll { $0.serverName == server.name }
            await connect(server: server)
        }
    }

    /// 全サーバーをリロード（新たに接続されたものを含めて再スキャン）
    func reloadAll() async {
        // 全セッション終了
        for (_, session) in stdioSessions {
            await session.terminate()
        }
        stdioSessions.removeAll()
        connectedTools.removeAll()
        connectionStatus.removeAll()
        await connectAll()
    }

    // MARK: - Connect / discover tools

    func connectAll() async {
        for server in servers where server.isEnabled {
            await connect(server: server)
        }
    }

    func connect(server: MCPServerConfig) async {
        guard server.isEnabled else {
            connectionStatus[server.id] = .disconnected
            return
        }
        // Fail fast with install guidance when an old notarized DMG is still installed.
        if server.name == "vera-memory",
           let binary = VeraMemoryPaths.resolveBundledBinary(),
           VeraMemoryPaths.missingLibraryValidationEntitlement(at: binary) {
            connectionStatus[server.id] = .error(VeraMemoryPaths.outdatedHardenedRuntimeMessage)
            return
        }
        connectionStatus[server.id] = .connecting
        do {
            let tools = try await discoverTools(server: server)
            connectedTools.removeAll { $0.serverName == server.name }
            connectedTools.append(contentsOf: tools)
            connectionStatus[server.id] = .connected
        } catch {
            connectionStatus[server.id] = .error(
                VeraMemoryPaths.annotateLaunchFailure(error.localizedDescription))
        }
    }

    func disconnect(serverId: UUID) {
        if let session = stdioSessions.removeValue(forKey: serverId) {
            Task { await session.terminate() }
        }
        if let server = servers.first(where: { $0.id == serverId }) {
            connectedTools.removeAll { $0.serverName == server.name }
        }
        connectionStatus[serverId] = .disconnected
    }

    // MARK: - Tool execution

    func callTool(serverName: String, toolName: String,
                  arguments: [String: Any],
                  mode: MCPServerConfig.ExecutionMode? = nil) async -> String {
        let resolvedMode = mode ?? currentExecutionMode
        guard let server = servers.first(where: { $0.name == serverName && $0.isEnabled }) else {
            return "[MCP] Server '\(serverName)' not found or disabled"
        }

        var record = MCPCallRecord(serverName: serverName, toolName: toolName,
                                   startTime: Date(), status: .running)
        activeCall = record

        NotificationCenter.default.post(
            name: .mcpToolCalled, object: nil,
            userInfo: ["server": serverName, "tool": toolName]
        )

        // Obtain (or create) the persistent session before entering the detached task
        let session: StdioSession? = server.transport == .stdio
            ? getOrCreateSession(for: server)
            : nil

        let execTask = Task<String, Error>.detached(priority: .userInitiated) {
            let deadline: Date = resolvedMode == .human
                ? Date().addingTimeInterval(60)
                : Date.distantFuture

            var finalArgs = arguments
            if serverName == "tool-search-oss" {
                let allTools = await MainActor.run {
                    self.connectedTools.filter { $0.serverName != "tool-search-oss" }
                }
                let toolsList = allTools.map { t -> [String: Any] in
                    var dict: [String: Any] = [
                        "name": "\(t.serverName).\(t.name)",
                        "description": t.description
                    ]
                    // inputSchema is [String: AnyCodable]. Convert to [String: Any] via JSONSerialization
                    if let data = try? JSONEncoder().encode(t.inputSchema),
                       let schema = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                        dict["inputSchema"] = schema
                    }
                    return dict
                }
                finalArgs["tools"] = toolsList
            }

            let params: [String: Any] = ["name": toolName, "arguments": finalArgs]

            switch server.transport {
            case .stdio:
                guard let s = session else {
                    throw MCPError.processLaunchFailed("No session")
                }
                let resp = try await s.callTool(
                    method: "tools/call", params: params, deadline: deadline)
                return mcpExtractText(from: resp)

            case .http:
                guard let url = URL(string: server.url + "/tools/call") else {
                    throw MCPError.invalidURL
                }
                var req = URLRequest(url: url)
                req.httpMethod = "POST"
                req.setValue("application/json", forHTTPHeaderField: "Content-Type")
                req.httpBody = try? JSONSerialization.data(withJSONObject: [
                    "jsonrpc": "2.0", "id": UUID().uuidString,
                    "method": "tools/call", "params": params
                ])
                // mcpNoTimeoutSession: no URLSession-level timeout.
                // Human-mode deadline is enforced by Task.cancel() below.
                let (data, _) = try await mcpNoTimeoutSession.data(for: req)
                let json = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
                return mcpExtractText(from: json)
            }
        }

        record.task = execTask

        // Human mode: fire a cancellation timer
        if resolvedMode == .human {
            Task {
                try? await Task.sleep(nanoseconds: 60_000_000_000)
                execTask.cancel()
            }
        }

        do {
            let result = try await execTask.value
            finishRecord(record, status: .completed)
            return result
        } catch is CancellationError {
            finishRecord(record, status: .cancelled)
            return "[MCP] Tool call cancelled"
        } catch MCPError.timeout {
            execTask.cancel()
            finishRecord(record, status: .timedOut)
            return "[MCP] Tool '\(toolName)' timed out"
        } catch {
            finishRecord(record, status: .failed(error.localizedDescription))
            return "[MCP] Error: \(error.localizedDescription)"
        }
    }

    /// Kill Switch — immediately cancels the in-flight tool call
    func killActiveCall() {
        activeCall?.task?.cancel()
        if var a = activeCall {
            a.status = .cancelled
            callHistory.insert(a, at: 0)
        }
        activeCall = nil
    }

    // MARK: - Private helpers

    private func getOrCreateSession(for server: MCPServerConfig) -> StdioSession {
        if let s = stdioSessions[server.id] { return s }
        let s = StdioSession(server: server)
        stdioSessions[server.id] = s
        return s
    }

    private func finishRecord(_ record: MCPCallRecord, status: MCPCallRecord.Status) {
        var r = record
        r.status = status
        callHistory.insert(r, at: 0)
        if callHistory.count > 100 { callHistory.removeLast(50) }
        activeCall = nil
    }

    private func discoverTools(server: MCPServerConfig) async throws -> [MCPTool] {
        switch server.transport {
        case .stdio:
            let session = getOrCreateSession(for: server)
            // 30 s for first cold-start (npx may need to download the package)
            let deadline = Date().addingTimeInterval(30)
            let resp = try await session.callTool(
                method: "tools/list", params: [:], deadline: deadline)
            return parseTools(from: resp, serverName: server.name)

        case .http:
            guard let url = URL(string: server.url + "/tools/list") else {
                throw MCPError.invalidURL
            }
            var req = URLRequest(url: url)
            req.httpMethod = "POST"
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = try? JSONSerialization.data(withJSONObject: [
                "jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": [:]
            ])
            req.timeoutInterval = 15
            let (data, _) = try await URLSession.shared.data(for: req)
            let json = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
            return parseTools(from: json, serverName: server.name)
        }
    }

    private func parseTools(from json: [String: Any], serverName: String) -> [MCPTool] {
        guard let result = json["result"] as? [String: Any],
              let toolsList = result["tools"] as? [[String: Any]] else { return [] }
        return toolsList.compactMap { t in
            guard let name = t["name"] as? String else { return nil }
            let desc = t["description"] as? String ?? ""
            return MCPTool(name: name, description: desc, serverName: serverName)
        }
    }

    // MARK: - Persistence

    private func saveServers() {
        if let data = try? JSONEncoder().encode(servers) {
            UserDefaults.standard.set(data, forKey: Self.storageKey)
        }
    }

    private func loadServers() {
        if let data = UserDefaults.standard.data(forKey: Self.storageKey),
           let decoded = try? JSONDecoder().decode([MCPServerConfig].self, from: data) {
            servers = decoded
        }

        // Optional external MCP servers (Cortex compiler / tool-search) used
        // to be auto-injected with hardcoded `/usr/local/bin/node` +
        // `/Users/.../verantyx-cli` paths. Those commands fail on every
        // launch (wrong node path, wrong checkout, missing `tsx` deps),
        // which painted Settings/MCP with permanent red "server error"
        // dots. Same migration pattern as vera-memory (46e5d89f3): only
        // register when the launch command is actually runnable; disable
        // stale saved entries instead of auto-connecting them.
        migrateOrInjectOptionalExternalServers()

        // ── Auto-inject / migrate vera-memory ──
        // Vera's deterministic, typed-verdict knowledge store (`ask` /
        // `remember` / `propose_ai_facts` / ...), run as its own MCP
        // server. CortexEngine queries it live in `buildMemoryPrompt`/
        // `extractAndStore` — see docs/MCP.md and Verantyx-Vera-alpha's
        // docs/DESIGN.md for what it actually is.
        //
        // Milestone H + portable DMG: always resolve relative to the
        // running app bundle (`Contents/MacOS/vera-memory`, then
        // Resources). Never hardcode developer checkout / python3.11 paths
        // for the default install — a fresh Mac with only the DMG must work.
        // If the configured path is dead, try alternate bundle-relative
        // locations and rewrite the saved config; disable with a clear
        // message only when nothing in the bundle is runnable.
        try? FileManager.default.createDirectory(at: VeraMemoryPaths.appSupportDir, withIntermediateDirectories: true)
        let bundledVeraMemory = VeraMemoryPaths.resolveBundledBinary()

        if let bundled = bundledVeraMemory {
            let command = VeraMemoryPaths.bundledMCPCommand(binary: bundled)
            if VeraMemoryPaths.missingLibraryValidationEntitlement(at: bundled) {
                // Keep the row so Settings shows why MCP is red; do not auto-connect.
                if let existingIndex = servers.firstIndex(where: { $0.name == "vera-memory" }) {
                    var row = servers[existingIndex]
                    row.command = command
                    row.isEnabled = true
                    servers[existingIndex] = row
                    connectionStatus[row.id] = .error(VeraMemoryPaths.outdatedHardenedRuntimeMessage)
                } else {
                    let config = MCPServerConfig(
                        name: "vera-memory",
                        transport: .stdio,
                        command: command,
                        mode: .ai
                    )
                    servers.append(config)
                    connectionStatus[config.id] = .error(VeraMemoryPaths.outdatedHardenedRuntimeMessage)
                }
            } else if let existingIndex = servers.firstIndex(where: { $0.name == "vera-memory" }) {
                let existing = servers[existingIndex]
                // Application Support store paths live under /Users/... — that is
                // expected. Only treat the *launch* side as stale (wrong binary /
                // python checkout / non-runnable command).
                let pointsAtBundled = existing.command.contains("\"\(bundled.path)\"")
                    || existing.command.hasPrefix("\"\(bundled.path)\"")
                let looksLikeDevCheckout = existing.command.contains("Verantyx-Vera-alpha")
                    || existing.command.contains("python3")
                    || existing.command.contains("-m verantyx")
                let needsRewrite = existing.command != command
                    || !existing.isEnabled
                    || !pointsAtBundled
                    || looksLikeDevCheckout
                    || !Self.commandLooksRunnable(existing.command)
                if needsRewrite {
                    var migrated = existing
                    migrated.command = command
                    migrated.isEnabled = true
                    servers[existingIndex] = migrated
                    Task { await self.connect(server: migrated) }
                }
            } else {
                let config = MCPServerConfig(
                    name: "vera-memory",
                    transport: .stdio,
                    command: command,
                    mode: .ai
                )
                servers.append(config)
                Task { await self.connect(server: config) }
            }
        } else if let existingIndex = servers.firstIndex(where: { $0.name == "vera-memory" }) {
            // Bundle missing the helper (dev build without embed phase).
            let existing = servers[existingIndex]
            if Self.commandLooksRunnable(existing.command),
               !existing.command.isEmpty {
                // The row points at a runnable engine the developer set up
                // (e.g. python -m verantyx.cli over an editable install).
                // Respect it: a working developer wiring beats a hard
                // error, and disabling it silently was exactly how every
                // Vera door in a Debug build died at once.
                if !existing.isEnabled {
                    var enabled = existing
                    enabled.isEnabled = true
                    servers[existingIndex] = enabled
                }
                Task { await self.connect(server: self.servers[existingIndex]) }
            } else {
                var disabled = existing
                if disabled.isEnabled {
                    disabled.isEnabled = false
                    servers[existingIndex] = disabled
                }
                connectionStatus[servers[existingIndex].id] = .error(
                    "vera-memory binary missing from Verantyx.app (expected Contents/MacOS/vera-memory). Reinstall from the DMG / rebuild with the embed phase."
                )
            }
        }

        saveServers()
    }

    /// Resolve optional Cortex / tool-search MCP launch commands, migrate
    /// stale UserDefaults entries off broken hardcoded paths, and only
    /// auto-connect when the command is actually runnable on this machine.
    private func migrateOrInjectOptionalExternalServers() {
        // ── verantyx-compiler ──
        if let command = Self.resolveVerantyxCompilerCommand() {
            if let idx = servers.firstIndex(where: { $0.name == "verantyx-compiler" }) {
                let existing = servers[idx]
                if existing.command != command || !existing.isEnabled {
                    var migrated = existing
                    migrated.command = command
                    migrated.isEnabled = true
                    servers[idx] = migrated
                    Task { await self.connect(server: migrated) }
                }
            } else {
                let config = MCPServerConfig(
                    name: "verantyx-compiler",
                    transport: .stdio,
                    command: command,
                    mode: .ai
                )
                servers.append(config)
                Task { await self.connect(server: config) }
            }
        } else if let idx = servers.firstIndex(where: { $0.name == "verantyx-compiler" }) {
            // Keep the row visible but stop auto-failing on every launch.
            if servers[idx].isEnabled {
                var disabled = servers[idx]
                disabled.isEnabled = false
                servers[idx] = disabled
            }
            connectionStatus[servers[idx].id] = .disconnected
        }

        // ── tool-search-oss ──
        // There is no bundled / reliably-present server entrypoint today
        // (old node `tools/src/server.ts` path is gone; python module is
        // not shipped). Never auto-inject. Disable any stale saved entry
        // that still points at the broken command so Connect-All / launch
        // does not surface a permanent error.
        if let idx = servers.firstIndex(where: { $0.name == "tool-search-oss" }) {
            let cmd = servers[idx].command
            let looksBroken = cmd.contains("/usr/local/bin/node")
                || cmd.contains("verantyx-cli/tools")
                || cmd.contains("tsx/esm")
                || cmd.contains("tool_search_oss.server")
            if looksBroken || !Self.commandLooksRunnable(cmd) {
                if servers[idx].isEnabled {
                    var disabled = servers[idx]
                    disabled.isEnabled = false
                    servers[idx] = disabled
                }
                connectionStatus[servers[idx].id] = .disconnected
            }
        }
    }

    /// Prefer Homebrew node; fall back to `/usr/local` then `PATH`.
    private static func resolveNodeBinary() -> String? {
        let candidates = [
            "/opt/homebrew/bin/node",
            "/usr/local/bin/node"
        ]
        let fm = FileManager.default
        if let hit = candidates.first(where: { fm.isExecutableFile(atPath: $0) }) {
            return hit
        }
        // Last resort: whatever `env` would find (Process prepends homebrew PATH).
        return "node"
    }

    /// Build a working `verantyx-compiler` stdio command, or nil if the
    /// Cortex checkout / `tsx` deps are not present on this machine.
    private static func resolveVerantyxCompilerCommand() -> String? {
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        let cortexRoots = [
            "\(home)/Projects/verantyx-cli/cortex",
            "\(home)/verantyx-cli/cortex",
            "/Users/motonishikoudai/Projects/verantyx-cli/cortex",
            "/Users/motonishikoudai/verantyx-cli/cortex"
        ]
        let fm = FileManager.default
        guard let cortex = cortexRoots.first(where: {
            fm.fileExists(atPath: $0 + "/src/mcp/server.ts")
                && fm.fileExists(atPath: $0 + "/node_modules/tsx")
        }) else { return nil }
        guard let node = resolveNodeBinary() else { return nil }
        // `package.json` scripts use `cd cortex && node --import tsx src/mcp/server.ts`
        return "sh -c \"cd \(cortex) && \(node) --import tsx src/mcp/server.ts\""
    }

    /// Cheap preflight: for `sh -c "cd DIR && …"` require DIR to exist;
    /// for quoted binary paths require the binary to exist.
    private static func commandLooksRunnable(_ command: String) -> Bool {
        let fm = FileManager.default
        if command.hasPrefix("\"") {
            let path = String(command.dropFirst().prefix { $0 != "\"" })
            return fm.isExecutableFile(atPath: path)
        }
        if let range = command.range(of: #"cd ([^ &\"]+)"#, options: .regularExpression) {
            let token = String(command[range]).replacingOccurrences(of: "cd ", with: "")
            return fm.fileExists(atPath: token)
        }
        return true
    }
}

// MARK: - Errors

enum MCPError: LocalizedError {
    case timeout
    case invalidURL
    case noResponse
    case decodingFailed
    case processLaunchFailed(String)

    var errorDescription: String? {
        switch self {
        case .timeout:                    return "MCP tool call timed out"
        case .invalidURL:                 return "Invalid MCP server URL"
        case .noResponse:                 return "No response from MCP server"
        case .decodingFailed:             return "Failed to decode MCP response"
        case .processLaunchFailed(let r): return "MCP process failed to launch: \(r)"
        }
    }
}

// MARK: - Notification

extension Notification.Name {
    static let mcpToolCalled = Notification.Name("mcpToolCalled")
}
