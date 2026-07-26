import Foundation
import AppKit

public class JCrossSwarmRunner {
    public static let shared = JCrossSwarmRunner()
    
    private var activeProcess: Process?
    private var stdinPipe: Pipe?
    
    private init() {}
    
    public func runSwarm(prompt: String, nodes: Int = 10) async {
        guard activeProcess == nil else {
            await MainActor.run {
                AppState.shared?.addSystemMessage("Swarm Pipeline is already running.")
            }
            return
        }
        
        await MainActor.run {
            AppState.shared?.isGenerating = true
        }
        
        let process = Process()
        let outPipe = Pipe()
        let errPipe = Pipe()
        let inPipe = Pipe()
        
        self.stdinPipe = inPipe
        self.activeProcess = process
        
        // 開発環境や実行環境のパスを想定
        let basePath = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
        
        process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        process.arguments = ["python3", "cli/scripts/start_swarm_pipeline_socket.py", "--nodes", "\(nodes)", "--prompt", prompt]
        process.currentDirectoryURL = basePath
        
        process.standardOutput = outPipe
        process.standardError = errPipe
        process.standardInput = inPipe
        
        outPipe.fileHandleForReading.readabilityHandler = { [weak self] fh in
            let data = fh.availableData
            guard !data.isEmpty else { return }
            guard let str = String(data: data, encoding: .utf8) else { return }
            
            let lines = str.components(separatedBy: .newlines).filter { !$0.isEmpty }
            for line in lines {
                self?.handleRPCPayload(line)
            }
        }
        
        errPipe.fileHandleForReading.readabilityHandler = { fh in
            let data = fh.availableData
            guard !data.isEmpty else { return }
            if let str = String(data: data, encoding: .utf8) {
                Task {
                    await MainActor.run {
                        // バックグラウンドの処理状況をログ表示
                        AppState.shared?.logStore.entries.append(.init(timestamp: Date(), text: str.trimmingCharacters(in: .newlines), kind: .system))
                    }
                }
            }
        }
        
        process.terminationHandler = { [weak self] _ in
            outPipe.fileHandleForReading.readabilityHandler = nil
            errPipe.fileHandleForReading.readabilityHandler = nil
            Task {
                await MainActor.run {
                    AppState.shared?.isGenerating = false
                    self?.activeProcess = nil
                    self?.stdinPipe = nil
                    AppState.shared?.addSystemMessage("Swarm Pipeline finished.")
                }
            }
        }
        
        do {
            try process.run()
        } catch {
            await MainActor.run {
                AppState.shared?.addSystemMessage("Failed to start Swarm Pipeline: \(error)")
                AppState.shared?.isGenerating = false
            }
            activeProcess = nil
        }
    }
    
    private func handleRPCPayload(_ payload: String) {
        guard let data = payload.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return
        }
        
        // Check if it's a final result
        if let status = json["status"] as? String, status == "success", let result = json["result"] as? String {
            Task {
                await MainActor.run {
                    AppState.shared?.messages.append(ChatMessage(role: .assistant, content: result))
                }
            }
            return
        }
        
        // JSON-RPC format check
        guard let rpcVersion = json["jsonrpc"] as? String, rpcVersion == "2.0",
              let method = json["method"] as? String,
              let params = json["params"] as? [String: Any],
              let id = json["id"] as? Int else {
            return
        }
        
        // 既存のGatekeeperやファイルシステムを呼び出す (今回は直接ファイル処理で模倣)
        Task {
            var toolResult = ""
            
            if method == "read_file", let path = params["path"] as? String {
                let url = URL(fileURLWithPath: path)
                if let content = try? String(contentsOf: url, encoding: .utf8) {
                    toolResult = content
                } else {
                    toolResult = "Error: File not found or unreadable."
                }
            } else if method == "write_file", let path = params["path"] as? String, let content = params["content"] as? String {
                let url = URL(fileURLWithPath: path)
                do {
                    try content.write(to: url, atomically: true, encoding: .utf8)
                    toolResult = "Success: Wrote to \(path)"
                } catch {
                    toolResult = "Error: Failed to write to \(path). \(error)"
                }
            } else {
                toolResult = "Error: Unknown action \(method)"
            }
            
            // Swift側でのツール実行ログ
            await MainActor.run {
                AppState.shared?.logStore.entries.append(.init(timestamp: Date(), text: "[Gatekeeper] Executed \(method) for Swarm node \(id)", kind: .tool))
            }
            
            // 結果をパイプ経由でPython側に打ち返す
            let response: [String: Any] = [
                "jsonrpc": "2.0",
                "id": id,
                "result": toolResult
            ]
            
            if let respData = try? JSONSerialization.data(withJSONObject: response),
               var respString = String(data: respData, encoding: .utf8) {
                respString += "\n"
                if let inData = respString.data(using: .utf8) {
                    self.stdinPipe?.fileHandleForWriting.write(inData)
                }
            }
        }
    }
}
