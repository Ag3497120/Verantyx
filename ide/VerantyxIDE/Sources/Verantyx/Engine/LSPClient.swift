import Foundation

// MARK: - LSPClient
// JSON-RPC 2.0 over stdio — talks to any Language Server Protocol server.
// Supports: sourcekit-lsp (Swift), pyright (Python), typescript-language-server (TS/JS)
//
// Implemented requests:
//   initialize / initialized
//   textDocument/didOpen, didChange, didClose
//   textDocument/completion
//   textDocument/hover
//   textDocument/definition
//   textDocument/publishDiagnostics (notification → callback)

@MainActor
final class LSPClient: ObservableObject {

    // MARK: - Published state

    @Published var isConnected: Bool = false
    @Published var diagnostics: [String: [LSPDiagnostic]] = [:]  // uri → diagnostics
    @Published var completionItems: [LSPCompletionItem] = []
    @Published var hoverContent: String? = nil

    // MARK: - Config

    enum Language: String, CaseIterable {
        case swift      = "swift"
        case python     = "python"
        case typescript = "typescript"
        case javascript = "javascript"

        var serverArgs: [String] {
            switch self {
            case .swift:
                return ["/usr/bin/xcrun", "sourcekit-lsp"]
            case .python:
                return ["/usr/bin/env", "pylsp"]
            case .typescript, .javascript:
                return ["/usr/bin/env", "typescript-language-server", "--stdio"]
            }
        }
    }

    // MARK: - Private

    private var process: Process?
    private var inputPipe  = Pipe()
    private var outputPipe = Pipe()
    private var readBuffer = Data()
    private var requestID  = 0
    private var pending: [Int: CheckedContinuation<LSPResponse, Error>] = [:]
    private var nextID: Int { requestID += 1; return requestID }
    private var workspaceURI: String = ""
    private var language: Language = .swift

    // MARK: - Lifecycle

    func start(language: Language, workspaceURL: URL) async {
        self.language = language
        self.workspaceURI = workspaceURL.absoluteString

        let args = language.serverArgs
        guard !args.isEmpty else { return }

        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: args[0])
        proc.arguments = Array(args.dropFirst())
        proc.standardInput  = inputPipe
        proc.standardOutput = outputPipe
        proc.standardError  = Pipe()  // discard

        do {
            try proc.run()
        } catch {
            print("LSP: failed to start \(language.rawValue): \(error)")
            return
        }

        self.process = proc
        startReading()

        // initialize handshake
        let initResult = try? await sendRequest(method: "initialize", params: initializeParams(workspaceURL))
        _ = initResult
        sendNotification(method: "initialized", params: [:] as [String: String])
        isConnected = true
    }

    func stop() {
        process?.terminate()
        process = nil
        isConnected = false
        diagnostics = [:]
    }

    // MARK: - textDocument lifecycle

    func didOpen(url: URL, content: String) {
        let uri = url.absoluteString
        let lang = languageID(for: url)
        sendNotification(method: "textDocument/didOpen", params: [
            "textDocument": [
                "uri": uri,
                "languageId": lang,
                "version": 1,
                "text": content
            ]
        ] as [String: Any])
    }

    func didChange(url: URL, content: String, version: Int) {
        sendNotification(method: "textDocument/didChange", params: [
            "textDocument": ["uri": url.absoluteString, "version": version],
            "contentChanges": [["text": content]]
        ] as [String: Any])
    }

    func didClose(url: URL) {
        sendNotification(method: "textDocument/didClose", params: [
            "textDocument": ["uri": url.absoluteString]
        ])
    }

    // MARK: - Completion

    func requestCompletion(url: URL, line: Int, character: Int) async -> [LSPCompletionItem] {
        guard isConnected else { return [] }
        guard let response = try? await sendRequest(
            method: "textDocument/completion",
            params: [
                "textDocument": ["uri": url.absoluteString],
                "position": ["line": line, "character": character]
            ] as [String: Any]
        ) else { return [] }

        return parseCompletionItems(from: response.result)
    }

    // MARK: - Hover

    func requestHover(url: URL, line: Int, character: Int) async -> String? {
        guard isConnected else { return nil }
        guard let response = try? await sendRequest(
            method: "textDocument/hover",
            params: [
                "textDocument": ["uri": url.absoluteString],
                "position": ["line": line, "character": character]
            ] as [String: Any]
        ) else { return nil }

        if let result = response.result as? [String: Any],
           let contents = result["contents"] as? [String: Any],
           let value = contents["value"] as? String {
            return value
        }
        return nil
    }

    // MARK: - Go to Definition

    func requestDefinition(url: URL, line: Int, character: Int) async -> URL? {
        guard isConnected else { return nil }
        guard let response = try? await sendRequest(
            method: "textDocument/definition",
            params: [
                "textDocument": ["uri": url.absoluteString],
                "position": ["line": line, "character": character]
            ] as [String: Any]
        ) else { return nil }

        if let result = response.result as? [[String: Any]],
           let first = result.first,
           let uriStr = first["uri"] as? String {
            return URL(string: uriStr)
        }
        return nil
    }

    // MARK: - JSON-RPC I/O

    private func sendRequest(method: String, params: Any) async throws -> LSPResponse {
        let id = nextID
        let message = jsonRPC(id: id, method: method, params: params)
        return try await withCheckedThrowingContinuation { (cont: CheckedContinuation<LSPResponse, Error>) in
            pending[id] = cont
            send(message)
        }
    }

    private func sendNotification(method: String, params: Any) {
        let message = jsonRPC(id: nil, method: method, params: params)
        send(message)
    }

    private func send(_ payload: Data) {
        let header = "Content-Length: \(payload.count)\r\n\r\n"
        let headerData = header.data(using: .utf8)!
        let combined = headerData + payload
        (process?.standardInput as? Pipe)?.fileHandleForWriting.write(combined)
    }

    private func startReading() {
        outputPipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            guard let self else { return }
            let data = handle.availableData
            guard !data.isEmpty else { return }
            Task { @MainActor in
                self.readBuffer.append(data)
                self.processBuffer()
            }
        }
    }

    private func processBuffer() {
        while true {
            guard let headerEnd = readBuffer.range(of: Data("\r\n\r\n".utf8)) else { break }
            let headerData = readBuffer[readBuffer.startIndex..<headerEnd.lowerBound]
            guard let headerStr = String(data: headerData, encoding: .utf8),
                  let lengthStr = headerStr.components(separatedBy: "\r\n")
                    .first(where: { $0.hasPrefix("Content-Length:") })?
                    .components(separatedBy: ":").last?.trimmingCharacters(in: .whitespaces),
                  let length = Int(lengthStr) else { break }

            let bodyStart = headerEnd.upperBound
            let bodyEnd = readBuffer.index(bodyStart, offsetBy: length, limitedBy: readBuffer.endIndex) ?? readBuffer.endIndex
            guard readBuffer.distance(from: bodyStart, to: readBuffer.endIndex) >= length else { break }

            let body = readBuffer[bodyStart..<bodyEnd]
            readBuffer = readBuffer[bodyEnd...]

            if let json = try? JSONSerialization.jsonObject(with: body) as? [String: Any] {
                handleMessage(json)
            }
        }
    }

    private func handleMessage(_ json: [String: Any]) {
        // Response to a request
        if let rawID = json["id"] {
            let id = (rawID as? Int) ?? Int((rawID as? String) ?? "") ?? -1
            let response = LSPResponse(id: id, result: json["result"], error: json["error"])
            if let cont = pending.removeValue(forKey: id) {
                if json["error"] != nil {
                    cont.resume(throwing: LSPError.serverError(json["error"].debugDescription))
                } else {
                    cont.resume(returning: response)
                }
            }
            return
        }

        // Notification (no id)
        if let method = json["method"] as? String {
            handleNotification(method: method, params: json["params"])
        }
    }

    private func handleNotification(method: String, params: Any?) {
        switch method {
        case "textDocument/publishDiagnostics":
            if let p = params as? [String: Any],
               let uri = p["uri"] as? String,
               let rawDiags = p["diagnostics"] as? [[String: Any]] {
                let diags = rawDiags.compactMap(LSPDiagnostic.init)
                DispatchQueue.main.async { self.diagnostics[uri] = diags }
            }
        default:
            break
        }
    }

    // MARK: - Helpers

    private func jsonRPC(id: Int?, method: String, params: Any) -> Data {
        var msg: [String: Any] = [
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        ]
        if let id { msg["id"] = id }
        return (try? JSONSerialization.data(withJSONObject: msg)) ?? Data()
    }

    private func initializeParams(_ root: URL) -> [String: Any] {
        [
            "processId": ProcessInfo.processInfo.processIdentifier,
            "rootUri": root.absoluteString,
            "capabilities": [
                "textDocument": [
                    "completion": ["completionItem": ["snippetSupport": false]],
                    "hover": ["contentFormat": ["plaintext"]],
                    "publishDiagnostics": ["relatedInformation": true]
                ]
            ],
            "initializationOptions": [:]
        ] as [String: Any]
    }

    private func languageID(for url: URL) -> String {
        switch url.pathExtension.lowercased() {
        case "swift":        return "swift"
        case "py":           return "python"
        case "ts", "tsx":    return "typescript"
        case "js", "jsx":    return "javascript"
        case "rs":           return "rust"
        case "go":           return "go"
        case "kt":           return "kotlin"
        case "java":         return "java"
        case "c", "h":       return "c"
        case "cpp", "hpp":   return "cpp"
        default:             return "plaintext"
        }
    }

    private func parseCompletionItems(from result: Any?) -> [LSPCompletionItem] {
        var rawItems: [[String: Any]] = []
        if let arr = result as? [[String: Any]] {
            rawItems = arr
        } else if let obj = result as? [String: Any],
                  let items = obj["items"] as? [[String: Any]] {
            rawItems = items
        }
        return rawItems.compactMap(LSPCompletionItem.init)
    }

    enum LSPError: Error {
        case serverError(String)
        case notConnected
    }
}

// MARK: - LSP Data Models

struct LSPResponse {
    let id: Int
    let result: Any?
    let error: Any?
}

struct LSPDiagnostic: Identifiable {
    let id: UUID
    let message: String
    let severity: Severity
    let startLine: Int
    let startCharacter: Int
    let endLine: Int
    let endCharacter: Int

    enum Severity: Int {
        case error   = 1
        case warning = 2
        case info    = 3
        case hint    = 4
    }

    init?(_ json: [String: Any]) {
        guard let msg = json["message"] as? String,
              let range = json["range"] as? [String: Any],
              let start = range["start"] as? [String: Any],
              let end   = range["end"]   as? [String: Any]
        else { return nil }

        self.id             = UUID()
        self.message        = msg
        self.severity       = Severity(rawValue: json["severity"] as? Int ?? 1) ?? .error
        self.startLine      = start["line"]      as? Int ?? 0
        self.startCharacter = start["character"] as? Int ?? 0
        self.endLine        = end["line"]        as? Int ?? 0
        self.endCharacter   = end["character"]   as? Int ?? 0
    }
}

struct LSPCompletionItem: Identifiable {
    let id: UUID
    let label: String
    let kind: Int
    let detail: String?
    let documentation: String?
    let insertText: String?

    var kindIcon: String {
        switch kind {
        case 2:  return "function"     // Method
        case 3:  return "function"     // Function
        case 4:  return "constructor"  // Constructor
        case 5:  return "field"        // Field
        case 6:  return "variable"     // Variable
        case 7:  return "class"        // Class
        case 8:  return "interface"    // Interface
        case 9:  return "module"       // Module
        case 10: return "property"     // Property
        case 14: return "keyword"      // Keyword
        default: return "text"
        }
    }

    init?(_ json: [String: Any]) {
        guard let label = json["label"] as? String else { return nil }
        self.id            = UUID()
        self.label         = label
        self.kind          = json["kind"] as? Int ?? 1
        self.detail        = json["detail"] as? String
        self.documentation = (json["documentation"] as? [String: Any])?["value"] as? String
                          ?? json["documentation"] as? String
        self.insertText    = json["insertText"] as? String ?? label
    }
}
