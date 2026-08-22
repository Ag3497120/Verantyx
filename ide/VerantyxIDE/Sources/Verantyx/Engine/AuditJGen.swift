import Foundation

// jgen support for the audit screen — DRAFTS and MEMORY, never decisions.
//
// The engine that publishes is deterministic and human-approved; jgen is a
// language model, and a language model must not be the thing that decides
// what enters the corpus. So its two jobs here are strictly upstream of the
// approval gate:
//
//   * DRAFT — turn a raw fetched article into a clean, ingest-shaped set of
//     definition sentences, and turn a plain-language edit request into an
//     HTML patch the human then previews. The human still runs the same
//     offer -> preview -> approve, or reads the diff before publishing.
//   * MEMORY — hold the task's context forever, in a durable file, so the
//     audit session survives restarts and every resolved gap and applied
//     edit is remembered. Deterministic to reload: the memory is data, and
//     re-reading it yields the same state.
//
// Reasoning models (qwen3.x) emit a `thinking` field separately from
// `response`; both are captured, only `response` is used, because the
// thinking is the model's scratch and the response is its output — the same
// distinction the deterministic engine draws between a walk and a citation.

struct JGenReply {
    let response: String
    let thinking: String
}

enum AuditJGen {
    /// One non-streaming generation. `endpoint` is passed in from the
    /// MainActor caller — this type stays actor-agnostic so it can run off
    /// the main thread. Returns nil on any failure — a missing
    /// model means "no draft", which the caller shows as such, never as an
    /// empty approval.
    static func generate(endpoint: String, model: String, prompt: String,
                         numPredict: Int = 400) async -> JGenReply? {
        guard let url = URL(string: "\(endpoint)/api/generate") else { return nil }
        struct Req: Encodable {
            let model: String; let prompt: String; let stream: Bool
            let think: Bool
            let options: Opt
            struct Opt: Encodable { let temperature: Double; let num_predict: Int }
        }
        struct Res: Decodable { let response: String?; let thinking: String? }
        // think:false — reasoning models (qwen3.x) otherwise spend the whole
        // token budget in a `thinking` field and return an EMPTY response;
        // measured on qwen3.5:4b, 1,485 thinking chars and 0 response. The
        // draft is the output, not the scratch, so the scratch is switched
        // off — the same reason the deterministic engine ships the citation,
        // not the walk.
        let body = Req(model: model, prompt: prompt, stream: false, think: false,
                       options: .init(temperature: 0.15, num_predict: numPredict))
        guard let data = try? JSONEncoder().encode(body) else { return nil }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.httpBody = data
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.timeoutInterval = 240
        guard let (respData, _) = try? await URLSession.shared.data(for: req),
              let decoded = try? JSONDecoder().decode(Res.self, from: respData)
        else { return nil }
        return JGenReply(response: (decoded.response ?? "")
                            .trimmingCharacters(in: .whitespacesAndNewlines),
                         thinking: decoded.thinking ?? "")
    }

    /// Clean an article into ingest-shaped definition sentences. The output
    /// is what a human previews before approving — jgen shapes, the person
    /// decides.
    static func draftIngest(endpoint: String, subject: String,
                            article: String, model: String) async -> String? {
        let head = String(article.prefix(2400))
        let prompt = """
        あなたは知識ベースの前処理器です。以下の記事から、主題「\(subject)」に\
        ついての事実を、一文一事実の平易な定義文に書き直してください。推測や\
        評価を加えず、記事に書かれていることだけを、5〜10文で。箇条書き記号や\
        見出しは付けず、日本語の文だけを出力してください。

        記事:
        \(head)
        """
        return await generate(endpoint: endpoint, model: model, prompt: prompt, numPredict: 500)?.response
    }

    /// Turn a plain-language edit request into an HTML patch of the page.
    /// The human previews the result against the live origin before publish.
    static func draftEdit(endpoint: String, request: String,
                          currentHTML: String, model: String) async -> String? {
        let ctx = String(currentHTML.prefix(6000))
        let prompt = """
        You are editing a self-contained HTML page. Apply this request and \
        return ONLY the full modified HTML, no explanation, no code fences.

        Request: \(request)

        Current HTML (may be truncated; preserve everything you cannot see):
        \(ctx)
        """
        return await generate(endpoint: endpoint, model: model, prompt: prompt, numPredict: 4000)?.response
    }
}

// MARK: - Everlasting task memory

/// Durable, append-only memory of an audit task. One JSON file per task;
/// re-reading it reconstructs the whole context, so a session survives quits
/// and a decision made yesterday is present today. Deterministic: the memory
/// is data, and the same file yields the same state.
struct AuditMemory: Codable {
    struct Entry: Codable, Identifiable {
        var id = UUID()
        var at: Date = Date()
        var kind: String          // "gap_resolved" | "edit_applied" | "note"
        var subject: String
        var detail: String
    }

    var task: String
    var created: Date = Date()
    var entries: [Entry] = []

    static func path(task: String) -> URL {
        let dir = FileManager.default
            .homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/Verantyx/audit-memory",
                                    isDirectory: true)
        try? FileManager.default.createDirectory(at: dir,
                                                 withIntermediateDirectories: true)
        let safe = task.replacingOccurrences(of: "/", with: "_")
        return dir.appendingPathComponent("\(safe).json")
    }

    static func load(task: String) -> AuditMemory {
        let url = path(task: task)
        if let d = try? Data(contentsOf: url),
           let m = try? JSONDecoder().decode(AuditMemory.self, from: d) {
            return m
        }
        return AuditMemory(task: task)
    }

    mutating func remember(kind: String, subject: String, detail: String) {
        entries.append(Entry(kind: kind, subject: subject, detail: detail))
        save()
    }

    func save() {
        let url = AuditMemory.path(task: task)
        if let d = try? JSONEncoder().encode(self) {
            try? d.write(to: url, options: .atomic)
        }
    }
}
