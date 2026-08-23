import Foundation
import Combine

/// JSON-RPC 2.0 Message Structures
struct RPCRequest: Codable {
    let jsonrpc: String
    let id: Int?
    let method: String
    let params: [String: AnyCodable]?
}

struct RPCResponse: Codable {
    let jsonrpc: String
    let id: Int
    let result: AnyCodable?
    let error: RPCError?
}

struct RPCError: Codable {
    let code: Int
    let message: String
}


/// Manages the Node.js VS Code Extension Host
@MainActor
final class ExtensionHostManager: ObservableObject {
    static let shared = ExtensionHostManager()

    private var process: Process?
    private var inputPipe: Pipe?
    private var outputPipe: Pipe?
    private var errorPipe: Pipe?
    
    private var requestIDCounter = 0
    private var pendingRequests: [Int: (Any?) -> Void] = [:]
    
    @Published var isRunning = false
    @Published var loadedExtensions: [String] = []

    private init() {}

    func start() {
        guard process == nil else { return }

        // Locate the Node.js Extension Host entry point
        // For development, we assume it's in Resources/ExtensionHost/dist/main.js
        let fm = FileManager.default
        let currentDir = URL(fileURLWithPath: fm.currentDirectoryPath)
        let hostPath = currentDir.appendingPathComponent("Resources/ExtensionHost/dist/main.js").path

        guard fm.fileExists(atPath: hostPath) else {
            AppState.shared?.logProcess(AppLanguage.shared.t("❌ Extension Host not found at \(hostPath)", "❌ Extension Host が \(hostPath) に見つかりません"), kind: .system)
            return
        }

        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/local/bin/node") // Assuming node is here or use env
        if !fm.fileExists(atPath: "/usr/local/bin/node") {
            process.executableURL = URL(fileURLWithPath: "/opt/homebrew/bin/node") // Apple Silicon fallback
        }
        process.arguments = [hostPath]

        let inputPipe = Pipe()
        let outputPipe = Pipe()
        let errorPipe = Pipe()

        process.standardInput = inputPipe
        process.standardOutput = outputPipe
        process.standardError = errorPipe

        self.process = process
        self.inputPipe = inputPipe
        self.outputPipe = outputPipe
        self.errorPipe = errorPipe

        outputPipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty else { return }
            Task { @MainActor in
                self?.handleIncomingData(data)
            }
        }

        errorPipe.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            guard !data.isEmpty, let errString = String(data: data, encoding: .utf8) else { return }
            Task { @MainActor in
                AppState.shared?.logProcess("ExtensionHost stderr: \(errString.trimmingCharacters(in: .whitespacesAndNewlines))", kind: .system)
            }
        }

        process.terminationHandler = { [weak self] _ in
            Task { @MainActor in
                self?.isRunning = false
                self?.process = nil
                AppState.shared?.logProcess(AppLanguage.shared.t("Extension Host terminated", "Extension Host が終了しました"), kind: .system)
            }
        }

        do {
            try process.run()
            isRunning = true
            AppState.shared?.logProcess(AppLanguage.shared.t("🚀 VS Code Extension Host started", "🚀 VS Code Extension Host が起動しました"), kind: .system)
        } catch {
            AppState.shared?.logProcess(AppLanguage.shared.t("❌ Failed to start Extension Host: \(error.localizedDescription)", "❌ Extension Host の起動に失敗: \(error.localizedDescription)"), kind: .system)
        }
    }

    func stop() {
        process?.terminate()
        process = nil
        isRunning = false
    }

    // MARK: - IPC Communication

    private var incomingBuffer = ""

    private func handleIncomingData(_ data: Data) {
        guard let string = String(data: data, encoding: .utf8) else { return }
        
        // JSON-RPC messages are often separated by newlines
        incomingBuffer += string
        let lines = incomingBuffer.components(separatedBy: "\n")
        
        guard lines.count > 1 else { return }
        
        for line in lines.dropLast() {
            if !line.isEmpty {
                parseRPCMessage(line)
            }
        }
        
        incomingBuffer = lines.last ?? ""
    }

    private func parseRPCMessage(_ jsonString: String) {
        guard let data = jsonString.data(using: .utf8) else { return }
        
        do {
            // It could be a Request (from host) or a Response (to our request)
            if let response = try? JSONDecoder().decode(RPCResponse.self, from: data) {
                Task { @MainActor in
                    if let callback = pendingRequests[response.id] {
                        callback(response.result?.value)
                        pendingRequests.removeValue(forKey: response.id)
                    }
                }
            } else if let request = try? JSONDecoder().decode(RPCRequest.self, from: data) {
                Task { @MainActor in
                    await handleRequestFromHost(request)
                }
            }
        }
    }

    private func handleRequestFromHost(_ request: RPCRequest) async {
        
        switch request.method {
        case "window.showInformationMessage":
            if let params = request.params, let msg = params["message"]?.value as? String {
                AppState.shared?.addSystemMessage(AppLanguage.shared.t("ℹ️ [Extension] \(msg)", "ℹ️ [拡張機能] \(msg)"))
                if let id = request.id { sendResponse(id: id, result: "OK") }
            }
        case "window.showErrorMessage":
            if let params = request.params, let msg = params["message"]?.value as? String {
                AppState.shared?.addSystemMessage(AppLanguage.shared.t("❌ [Extension Error] \(msg)", "❌ [拡張機能エラー] \(msg)"))
                if let id = request.id { sendResponse(id: id, result: "OK") }
            }
        case "commands.registerCommand":
            if let params = request.params, let cmd = params["command"]?.value as? String {
                CommandManager.shared.registerCommand(cmd)
                if let id = request.id { sendResponse(id: id, result: "OK") }
            }
        case "commands.unregisterCommand":
            if let params = request.params, let cmd = params["command"]?.value as? String {
                CommandManager.shared.unregisterCommand(cmd)
                if let id = request.id { sendResponse(id: id, result: "OK") }
            }
        case "languages.registerProvider":
            if let params = request.params, 
               let providerId = params["id"]?.value as? String,
               let type = params["type"]?.value as? String {
                LanguageManager.shared.registerProvider(id: providerId, type: type, selector: params["selector"])
                if let id = request.id { sendResponse(id: id, result: "OK") }
            }
        case "languages.unregisterProvider":
            if let params = request.params, let providerId = params["id"]?.value as? String {
                LanguageManager.shared.unregisterProvider(id: providerId)
                if let id = request.id { sendResponse(id: id, result: "OK") }
            }
        case "window.createWebviewPanel":
            // Usually this instructs UI to open the WKWebView.
            if let id = request.id { sendResponse(id: id, result: "OK") }
            
        case "window.showQuickPick":
            if let params = request.params, let id = request.id {
                let items = params["items"]?.value as? [String] ?? []
                let options = params["options"]?.value as? [String: Any]
                
                Task {
                    let result = await ExtensionUIManager.shared.showQuickPick(items: items, options: options)
                    sendResponse(id: id, result: result)
                }
            }

        case "window.showInputBox":
            if let params = request.params, let id = request.id {
                let options = params["options"]?.value as? [String: Any]
                
                Task {
                    let result = await ExtensionUIManager.shared.showInputBox(options: options)
                    sendResponse(id: id, result: result)
                }
            }
            
        // MARK: FileSystem Handlers
        case "workspace.fs.stat":
            if let params = request.params, let uri = params["uri"]?.value as? String, let id = request.id {
                do {
                    let result = try WorkspaceFileSystem.shared.stat(uri: uri)
                    sendResponse(id: id, result: result)
                } catch { sendResponse(id: id, result: nil) /* Send error in full RPC format if needed */ }
            }
        case "workspace.fs.readDirectory":
            if let params = request.params, let uri = params["uri"]?.value as? String, let id = request.id {
                do {
                    let result = try WorkspaceFileSystem.shared.readDirectory(uri: uri)
                    sendResponse(id: id, result: result)
                } catch { sendResponse(id: id, result: nil) }
            }
        case "workspace.fs.readFile":
            if let params = request.params, let uri = params["uri"]?.value as? String, let id = request.id {
                do {
                    let result = try WorkspaceFileSystem.shared.readFile(uri: uri)
                    sendResponse(id: id, result: result)
                } catch { sendResponse(id: id, result: nil) }
            }
        case "workspace.fs.writeFile":
            if let params = request.params, let uri = params["uri"]?.value as? String, let content = params["content"]?.value as? String, let id = request.id {
                do {
                    try WorkspaceFileSystem.shared.writeFile(uri: uri, contentBase64: content)
                    sendResponse(id: id, result: "OK")
                } catch { sendResponse(id: id, result: nil) }
            }
        case "workspace.fs.createDirectory":
            if let params = request.params, let uri = params["uri"]?.value as? String, let id = request.id {
                do {
                    try WorkspaceFileSystem.shared.createDirectory(uri: uri)
                    sendResponse(id: id, result: "OK")
                } catch { sendResponse(id: id, result: nil) }
            }
        case "workspace.fs.delete":
            if let params = request.params, let uri = params["uri"]?.value as? String, let id = request.id {
                do {
                    try WorkspaceFileSystem.shared.delete(uri: uri)
                    sendResponse(id: id, result: "OK")
                } catch { sendResponse(id: id, result: nil) }
            }
        case "workspace.fs.rename":
            if let params = request.params, let src = params["source"]?.value as? String, let tgt = params["target"]?.value as? String, let id = request.id {
                do {
                    try WorkspaceFileSystem.shared.rename(source: src, target: tgt)
                    sendResponse(id: id, result: "OK")
                } catch { sendResponse(id: id, result: nil) }
            }
            
        default:
            AppState.shared?.logProcess(AppLanguage.shared.t("⚠️ Unknown RPC method from host: \(request.method)", "⚠️ ホストからの不明なRPCメソッド: \(request.method)"), kind: .system)
            if let id = request.id { sendResponse(id: id, result: nil) }
        }
    }

    // MARK: - Sending Messages

    func sendNotification(method: String, params: [String: Any] = [:]) {
        let msg: [String: Any] = [
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        ]
        send(msg)
    }

    func sendRequest(method: String, params: [String: Any] = [:]) async throws -> Any? {
        return await withCheckedContinuation { continuation in
            let id = requestIDCounter
            requestIDCounter += 1
            
            pendingRequests[id] = { result in
                continuation.resume(returning: result)
            }
            
            let msg: [String: Any] = [
                "jsonrpc": "2.0",
                "id": id,
                "method": method,
                "params": params
            ]
            send(msg)
        }
    }

    private func sendResponse(id: Int, result: Any?) {
        var msg: [String: Any] = [
            "jsonrpc": "2.0",
            "id": id
        ]
        if let result = result {
            msg["result"] = result
        }
        send(msg)
    }

    private func send(_ dict: [String: Any]) {
        guard let data = try? JSONSerialization.data(withJSONObject: dict),
              let jsonString = String(data: data, encoding: .utf8),
              let pipe = inputPipe else { return }
        
        let payload = jsonString + "\n"
        if let payloadData = payload.data(using: .utf8) {
            pipe.fileHandleForWriting.write(payloadData)
        }
    }
}
