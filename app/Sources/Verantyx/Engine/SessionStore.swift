import Foundation
import SwiftUI

// MARK: - ChatSession
// A persisted chat session linking messages ↔ JCross memory nodes.

struct ChatSession: Identifiable, Codable {
    let id: UUID
    var title: String
    var createdAt: Date
    var updatedAt: Date
    var messages: [ChatMessage]
    var workspacePath: String?
    var memoryNodeIds: [String]    // filenames in JCross memory (e.g. "TURN_1234.jcross")
    var activeLayer: JCrossLayer

    /// この名前は**人か AI が意図して付けたもの**か。
    ///
    /// `autoTitle()` は最初のユーザー発言の先頭40字で名前を上書きする。
    /// それ自体は空の名前を埋めるのに要るが、**付け直した名前まで毎ターン
    /// 上書きしていた** — 名前を変えても次の発言で消えるので、名前を
    /// 付ける機能が事実上効かなかった。ここが立つと `autoTitle()` は
    /// 手を引く。
    ///
    /// `Optional` なのは既存のセッション JSON にこの鍵が無いため。
    /// 非 Optional にすると合成された `init(from:)` が `keyNotFound` を
    /// 投げ、**保存済みの会話が一つも読めなくなる**(既定値は復号に効かない)。
    var titleLocked: Bool?

    init(
        id: UUID = UUID(),
        title: String = "",
        messages: [ChatMessage] = [],
        workspacePath: String? = nil
    ) {
        self.id           = id
        self.title        = title
        self.createdAt    = Date()
        self.updatedAt    = Date()
        self.messages     = messages
        self.workspacePath = workspacePath
        self.memoryNodeIds = []
        self.activeLayer  = .l2
        self.titleLocked  = nil
    }

    // Auto-title from first user message
    mutating func autoTitle() {
        if titleLocked == true { return }
        if let first = messages.first(where: { $0.role == .user }) {
            let derived = String(first.content.prefix(40))
                        .trimmingCharacters(in: .whitespacesAndNewlines)
            // 画像だけを送ったターンは本文が空になる。空で上書きすると
            // 名無しに戻るので、**空は名前として採らない** — その場合は
            // 名前が空のまま残り、服の特徴から付ける経路に譲る。
            if !derived.isEmpty { title = derived }
        }
    }

    /// 意図して付けた名前。以後 `autoTitle()` は触らない。
    mutating func setIntentionalTitle(_ newTitle: String) {
        let t = newTitle.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !t.isEmpty else { return }
        title = String(t.prefix(60))
        titleLocked = true
    }
}

// MARK: - JCrossLayer

enum JCrossLayer: String, Codable, CaseIterable, Identifiable {
    case l1   = "L1"
    case l1_5 = "L1.5"
    case l2   = "L2"
    case l3   = "L3"
    // Vera-α: a session's memory backed by Vera's own deterministic,
    // typed-verdict store (over MCP, "vera-memory" server) instead of
    // .jcross node files. Same position as l1/l1.5/l2/l3 — one active
    // layer per session, mutually exclusive — routed at the call sites in
    // AgentLoop.run() via VeraMemoryBridge instead of
    // SessionMemoryArchiver. See docs comment on VeraMemoryBridge.swift.
    case vera = "Vera-α"

    var id: String { rawValue }

    var displayName: String { rawValue }

    var description: String {
        switch self {
        case .l1:   return "Kanji topology (ultrafast)"
        case .l1_5: return "Summary index (balanced)"
        case .l2:   return "Structured facts (accurate)"
        case .l3:   return "Verbatim text (max context)"
        case .vera: return "Vera deterministic store — auto-saves every turn, typed ANSWER/UNKNOWN verdicts"
        }
    }

    var icon: String {
        switch self {
        case .l1:   return "character.ja"
        case .l1_5: return "tablecells"
        case .l2:   return "list.bullet.rectangle"
        case .l3:   return "doc.text.fill"
        case .vera: return "checkmark.seal"
        }
    }

    // Maps to the layer argument in mcp_verantyx-compiler_read
    var mcpLayerArg: String {
        switch self {
        case .l1:   return "l1"
        case .l1_5: return "l2"   // L1.5 ≈ L2 summary in the MCP schema
        case .l2:   return "l2l3"
        case .l3:   return "l3"
        case .vera: return "vera"   // not read via this path — VeraMemoryBridge instead
        }
    }
}

// MARK: - SessionStore

@MainActor
final class SessionStore: ObservableObject {

    @Published var sessions: [ChatSession] = []
    @Published var activeSessionId: UUID? = nil

    /// ディスクからの復号が終わったか。**起動直後は `false`。**
    ///
    /// `init` の読み込みは `Task.detached` なので、起動直後に
    /// `activeSessionId` を同期で読むと「まだ nil」か「もう復元済み」かが
    /// 区別できない。会話の復元はこの旗が立ってから行う — 立つ前に
    /// 書き込むと、**読み込み前の空の本文で保存済みの会話を潰す。**
    @Published private(set) var didLoad: Bool = false

    var activeSession: ChatSession? {
        guard let id = activeSessionId else { return nil }
        return sessions.first(where: { $0.id == id })
    }

    // MARK: - Persistence

    private let storageDir: URL = {
        let dir = FileManager.default.urls(for: .applicationSupportDirectory,
                                            in: .userDomainMask)[0]
            .appendingPathComponent("Verantyx/sessions")
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }()

    init() {
        // ⚠️ loadAll() は起動時にディスクI/Oを実行するためメインスレッドをブロックする。
        // Task.detached でバックグラウンドに逃がし、完了後に MainActor へ反映する。
        // ⚠️ [weak self] を Task.detached で直接キャプチャすると ObservableObject の
        // 型チェッククラッシュ(SIGTERM)を誘発するため、値返しの Task.detached を使用する。
        let dir = storageDir
        Task { [weak self] in
            let decoded = await Task.detached(priority: .utility) { () -> [ChatSession] in
                guard let files = try? FileManager.default.contentsOfDirectory(
                    at: dir, includingPropertiesForKeys: [.creationDateKey]
                ) else { return [] }
                
                return files
                    .filter { $0.pathExtension == "json" }
                    .compactMap { url -> ChatSession? in
                        guard let data = try? Data(contentsOf: url) else { return nil }
                        return try? JSONDecoder().decode(ChatSession.self, from: data)
                    }
                    .sorted { $0.updatedAt > $1.updatedAt }
            }.value
            
            self?.sessions = decoded
            self?.activeSessionId = decoded.first?.id
            self?.didLoad = true
        }
    }

    // MARK: - CRUD

    func newSession(messages: [ChatMessage] = [], workspacePath: String? = nil) -> ChatSession {
        var session = ChatSession(messages: messages, workspacePath: workspacePath)
        if !messages.isEmpty { session.autoTitle() }
        sessions.insert(session, at: 0)
        activeSessionId = session.id
        save(session)
        return session
    }

    /// 届いた本文は、保存済みの会話の**続き**か、それとも別の会話か。
    ///
    /// 保存は追記ではなく `sessions[idx].messages = clean` の**丸ごと
    /// 置き換え**なので、活きている本文が別の会話だと、保存済みの会話が
    /// その場で消える。実際に起きていた道筋: 起動時に `activeSessionId`
    /// だけが最後の会話に向くが `messages` は空のまま → 最初の発言が
    /// その会話の続きとして採用され → 1発言だけの本文で JSON が上書き
    /// される。**同じ会話の続きなら最初の発言は同じもののはず**、を
    /// 判定に使う。
    private func continuesStored(_ stored: [ChatMessage],
                                 _ incoming: [ChatMessage]) -> Bool {
        guard let a = stored.first(where: { $0.role != .system }) else { return true }
        guard let b = incoming.first(where: { $0.role != .system }) else { return false }
        return a.id == b.id
    }

    private func cleaned(_ messages: [ChatMessage]) -> [ChatMessage] {
        // Strip any empty-content assistant bubbles that were created mid-stream
        // (e.g. the placeholder appended before the first token arrives).
        // These appear as blank bubbles when a session is restored.
        messages.filter { msg in
            !(msg.role == .assistant && msg.content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        }
    }

    func updateActiveSession(messages: [ChatMessage], workspacePath: String? = nil) {
        guard let id = activeSessionId,
              let idx = sessions.firstIndex(where: { $0.id == id }) else { return }
        let clean = cleaned(messages)
        // 空の本文で保存済みの会話を潰さない。書くものが無いだけで、
        // 消す理由にはならない。
        guard !clean.isEmpty else { return }
        if !continuesStored(sessions[idx].messages, clean) {
            // 別の会話。潰す代わりに、新しいセッションとして受け止める。
            _ = newSession(messages: clean, workspacePath: workspacePath)
            return
        }
        sessions[idx].messages     = clean
        sessions[idx].updatedAt    = Date()
        if let wp = workspacePath { sessions[idx].workspacePath = wp }
        sessions[idx].autoTitle()
        save(sessions[idx])
    }

    /// 終了時専用の同期セーブ。
    /// `save()` は毎 5 メッセージごとに `Task.detached { archiveProgressively() }` を起動するが、
    /// `applicationShouldTerminate` の同期コンテキストでこれを呼ぶとメインスレッドがブロックされる。
    /// このメソッドは JSON ディスク書き込みのみを行い、非同期タスクを一切起動しない。
    func saveForQuit(messages: [ChatMessage], workspacePath: String? = nil) {
        guard let id = activeSessionId,
              let idx = sessions.firstIndex(where: { $0.id == id }) else { return }
        let clean = cleaned(messages)
        // 終了時も同じ規律。**終了は上書きの理由にならない。**
        guard !clean.isEmpty else { return }
        guard continuesStored(sessions[idx].messages, clean) else {
            // 別の会話を抱えたまま終了した。終了経路で新しいセッションを
            // 起こすと保存順が乱れるので、ここは**書かない**方を選ぶ。
            // 保存済みの会話はそのまま残る。
            return
        }
        sessions[idx].messages  = clean
        sessions[idx].updatedAt = Date()
        if let wp = workspacePath { sessions[idx].workspacePath = wp }
        sessions[idx].autoTitle()
        // JSON のみ書き込む — archiveProgressively は起動しない
        guard let data = try? JSONEncoder().encode(sessions[idx]) else { return }
        try? data.write(to: sessionURL(sessions[idx].id))
    }

    func setLayer(_ layer: JCrossLayer, for sessionId: UUID) {
        guard let idx = sessions.firstIndex(where: { $0.id == sessionId }) else { return }
        sessions[idx].activeLayer = layer
        save(sessions[idx])
    }

    func linkMemoryNode(_ fileName: String, to sessionId: UUID) {
        guard let idx = sessions.firstIndex(where: { $0.id == sessionId }) else { return }
        if !sessions[idx].memoryNodeIds.contains(fileName) {
            sessions[idx].memoryNodeIds.append(fileName)
            save(sessions[idx])
        }
    }

    func rename(_ sessionId: UUID, to newTitle: String) {
        guard let idx = sessions.firstIndex(where: { $0.id == sessionId }) else { return }
        // 付け直した名前は以後 `autoTitle()` に消させない。
        sessions[idx].setIntentionalTitle(newTitle)
        save(sessions[idx])
    }

    /// 服の特徴から付いた名前(例:「緑色のスカート」)を採る。
    ///
    /// `rename` と分けてあるのは呼ぶ側の意図が違うから — こちらは人が
    /// まだ名前を付けていないときだけ効かせたい。**人が付けた名前を
    /// AI が塗り替えない。**
    func applyDerivedTitle(_ derived: String, to sessionId: UUID) {
        guard let idx = sessions.firstIndex(where: { $0.id == sessionId }) else { return }
        guard sessions[idx].titleLocked != true else { return }
        sessions[idx].setIntentionalTitle(derived)
        save(sessions[idx])
    }

    /// Delete a session. The **conversation messages** are removed, but the
    /// session's key facts are immortalized as a JCross node BEFORE deletion.
    func delete(_ sessionId: UUID) {
        // ── Step 1: Archive to JCross (永続化) ─────────────────────────
        if let session = sessions.first(where: { $0.id == sessionId }) {
            SessionMemoryArchiver.shared.archiveBeforeDelete(session: session)
        }

        // ── Step 2: Remove the session JSON (会話は消す) ────────────────
        sessions.removeAll { $0.id == sessionId }
        let url = sessionURL(sessionId)
        try? FileManager.default.removeItem(at: url)
        if activeSessionId == sessionId { activeSessionId = sessions.first?.id }
    }

    func selectSession(_ sessionId: UUID) {
        activeSessionId = sessionId
    }

    // MARK: - JCross Memory retrieval
    // Returns a context injection string built from the session's linked nodes
    // at the current active layer. This is called before inference to inject
    // session-specific long-term memory into the prompt.

    func buildMemoryInjection(for sessionId: UUID) async -> String {
        guard let session = sessions.first(where: { $0.id == sessionId }),
              !session.memoryNodeIds.isEmpty else { return "" }

        var parts: [String] = []
        let layer = session.activeLayer

        for fileName in session.memoryNodeIds.prefix(8) {
            if let content = await fetchJCrossNode(fileName: fileName, layer: layer) {
                parts.append(content)
            }
        }

        guard !parts.isEmpty else { return "" }

        return """

        [JCROSS MEMORY — Layer: \(layer.rawValue) — \(layer.description)]
        \(parts.joined(separator: "\n---\n"))
        [/JCROSS MEMORY]
        """
    }

    // Fetch a single JCross node via the MCP server file system
    // (reads from ~/.openclaw/memory/ where JCross nodes live)
    private func fetchJCrossNode(fileName: String, layer: JCrossLayer) async -> String? {
        let wsPath = await MainActor.run { AppState.shared?.cortexWorkspacePath ?? AppState.shared?.workspaceURL?.path }
        guard let basePath = wsPath else { return nil }
        
        let searchPaths: [String] = [
            basePath + "/.openclaw/memory/front/" + fileName,
            basePath + "/.openclaw/memory/near/" + fileName,
            basePath + "/.openclaw/memory/mid/" + fileName,
            basePath + "/.openclaw/memory/deep/" + fileName,
        ]

        for path in searchPaths {
            guard FileManager.default.fileExists(atPath: path),
                  let raw = try? String(contentsOfFile: path, encoding: .utf8)
            else { continue }

            return extractLayer(from: raw, layer: layer)
        }
        return nil
    }

    // Extract the requested layer from a .jcross file's raw content
    private func extractLayer(from raw: String, layer: JCrossLayer) -> String {
        switch layer {
        case .l1:
            // L1: first non-empty line (kanji tags / summary)
            return raw.components(separatedBy: "\n")
                .first(where: { !$0.trimmingCharacters(in: .whitespaces).isEmpty })
                ?? String(raw.prefix(100))

        case .l1_5:
            // L1.5: first 3 lines (index + brief summary)
            let lines = raw.components(separatedBy: "\n")
                .filter { !$0.trimmingCharacters(in: .whitespaces).isEmpty }
            return lines.prefix(3).joined(separator: "\n")

        case .l2:
            // L2: Extract OP.FACT / OP.ENTITY / OP.STATE lines
            let opLines = raw.components(separatedBy: "\n")
                .filter { $0.contains("OP.FACT") || $0.contains("OP.ENTITY") || $0.contains("OP.STATE") }
            return opLines.isEmpty
                ? String(raw.prefix(400))
                : opLines.joined(separator: "\n")

        case .l3:
            // L3: full raw text (capped at 2000 chars)
            return String(raw.prefix(2000))

        case .vera:
            // Vera sessions don't read .jcross node files at all (this
            // helper only runs when one was found on disk, which won't
            // happen for content Vera itself owns) — harmless fallback.
            return String(raw.prefix(200))
        }
    }

    // MARK: - Disk I/O

    private func sessionURL(_ id: UUID) -> URL {
        storageDir.appendingPathComponent("\(id.uuidString).json")
    }

    private func save(_ session: ChatSession) {
        guard let data = try? JSONEncoder().encode(session) else { return }
        try? data.write(to: sessionURL(session.id))

        // ── Progressive JCross archiving ──────────────────────────────
        // Every 10 messages, distill the session into a .jcross node.
        // The node is overwritten each time (fixed filename PROG_<id>.jcross),
        // so the count stays bounded regardless of session length.
        let userMessageCount = session.messages.filter { $0.role == .user }.count
        if userMessageCount > 0 && userMessageCount % 5 == 0 {
            Task.detached(priority: .background) {
                SessionMemoryArchiver.shared.archiveProgressively(session: session)
            }
        }
    }

    private func loadAll() {
        guard let files = try? FileManager.default.contentsOfDirectory(at: storageDir,
                                                       includingPropertiesForKeys: [.creationDateKey]) else { return }
        let decoded: [ChatSession] = files
            .filter { $0.pathExtension == "json" }
            .compactMap { url -> ChatSession? in
                guard let data = try? Data(contentsOf: url) else { return nil }
                return try? JSONDecoder().decode(ChatSession.self, from: data)
            }
            .sorted { $0.updatedAt > $1.updatedAt }

        sessions = decoded
        activeSessionId = sessions.first?.id
    }
}
