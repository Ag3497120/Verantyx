import Foundation
import Network

/// CortexHandshakeServer listens on 127.0.0.1:5420 for a POST /api/handshake Ping from the Verantyx-Cortex CLI.
/// This establishes the dynamic path connection (ping-based approach) enabling true frontend-backend separation.
@MainActor
final class CortexHandshakeServer: ObservableObject {
    static let shared = CortexHandshakeServer()
    
    private var listener: NWListener?
    private let port: NWEndpoint.Port = 5420
    
    private init() {}
    
    func start() {
        guard listener == nil else { return }
        do {
            let parameters = NWParameters.tcp
            listener = try NWListener(using: parameters, on: port)
            
            listener?.newConnectionHandler = { [weak self] connection in
                Task { @MainActor in
                    self?.handleConnection(connection)
                }
            }
            
            listener?.stateUpdateHandler = { state in
                switch state {
                case .ready:
                    print("🌐 CortexHandshakeServer listening on port 5420")
                case .failed(let error):
                    print("⚠️ CortexHandshakeServer failed: \(error)")
                default:
                    break
                }
            }
            
            listener?.start(queue: .global(qos: .userInitiated))
        } catch {
            print("⚠️ Failed to start CortexHandshakeServer: \(error)")
        }
    }
    
    private func handleConnection(_ connection: NWConnection) {
        connection.start(queue: .global(qos: .userInitiated))
        
        connection.receive(minimumIncompleteLength: 1, maximumLength: 65536) { [weak self] data, context, isComplete, error in
            guard let self = self, let data = data, !data.isEmpty else {
                connection.cancel()
                return
            }
            
            Task { @MainActor in
                if let requestString = String(data: data, encoding: .utf8) {
                    if requestString.hasPrefix("POST /api/handshake") {
                        self.parseHandshakePayload(requestString, connection: connection)
                    } else if requestString.hasPrefix("GET /health") {
                        self.sendHTTPResponse(to: connection, statusCode: 200, body: "{\"status\": \"ok\"}")
                    } else if requestString.hasPrefix("GET /skills/version") {
                        self.sendHTTPResponse(to: connection, statusCode: 200, body: "{\"version\": 1, \"count\": 0}")
                    } else {
                        // Unsupported method or route
                        self.sendHTTPResponse(to: connection, statusCode: 404, body: "Not Found")
                    }
                } else {
                    self.sendHTTPResponse(to: connection, statusCode: 400, body: "Bad Request")
                }
            }
        }
    }
    
    private func parseHandshakePayload(_ requestString: String, connection: NWConnection) {
        // Find JSON body after double newlines
        guard let bodyRange = requestString.range(of: "\r\n\r\n") ?? requestString.range(of: "\n\n") else {
            sendHTTPResponse(to: connection, statusCode: 400, body: "Bad Request")
            return
        }
        
        let bodyString = String(requestString[bodyRange.upperBound...])
        guard let bodyData = bodyString.data(using: .utf8) else {
            sendHTTPResponse(to: connection, statusCode: 400, body: "Bad Request")
            return
        }
        
        do {
            if let json = try JSONSerialization.jsonObject(with: bodyData, options: []) as? [String: Any] {
                let workspacePath = json["workspace_path"] as? String
                let skillsPath = json["skills_path"] as? String
                let swarmActive = json["swarm_active"] as? Bool ?? false
                
                Task { @MainActor in
                    if let ws = workspacePath {
                        AppState.shared?.cortexWorkspacePath = ws
                        UserDefaults.standard.set(ws, forKey: "cortex_workspace_path")
                    }
                    if let sp = skillsPath {
                        AppState.shared?.cortexSkillsPath = sp
                        UserDefaults.standard.set(sp, forKey: "cortex_skills_path")
                    }
                    AppState.shared?.cortexSwarmActive = swarmActive
                    AppState.shared?.isCortexConnected = true
                    
                    print("✅ Cortex Connected via Ping!")
                    print("Workspace: \(workspacePath ?? "nil")")
                    print("Skills: \(skillsPath ?? "nil")")
                    
                    // Respond to CLI
                    self.sendHTTPResponse(to: connection, statusCode: 200, body: "{\"status\": \"accepted\"}")
                }
            } else {
                sendHTTPResponse(to: connection, statusCode: 400, body: "Invalid JSON")
            }
        } catch {
            sendHTTPResponse(to: connection, statusCode: 400, body: "Parse Error")
        }
    }
    
    private func sendHTTPResponse(to connection: NWConnection, statusCode: Int, body: String) {
        let statusString = statusCode == 200 ? "200 OK" : "\(statusCode) Error"
        let response = """
        HTTP/1.1 \(statusString)\r
        Content-Type: application/json\r
        Content-Length: \(body.utf8.count)\r
        Connection: close\r
        \r
        \(body)
        """
        let data = response.data(using: .utf8)!
        connection.send(content: data, completion: .contentProcessed { _ in
            connection.cancel()
        })
    }
}
import Foundation
import Network

/// CortexWebSocketServer listens on 127.0.0.1:5421 for incoming WebSocket connections from the Cortex Swarm nodes.
/// It provides real-time status reporting and coordination for the distributed Verantyx system.
@MainActor
final class CortexWebSocketServer: ObservableObject {
    static let shared = CortexWebSocketServer()
    
    private var listener: NWListener?
    private let port: NWEndpoint.Port = 5421
    private var activeConnections: [NWConnection] = []
    
    @Published var swarmStatus: String = "Offline"
    
    private init() {}
    
    func start() {
        guard listener == nil else { return }
        do {
            let parameters = NWParameters.tcp
            let webSocketOptions = NWProtocolWebSocket.Options()
            webSocketOptions.autoReplyPing = true
            parameters.defaultProtocolStack.applicationProtocols.insert(webSocketOptions, at: 0)
            
            listener = try NWListener(using: parameters, on: port)
            
            listener?.newConnectionHandler = { [weak self] connection in
                Task { @MainActor in
                    self?.handleConnection(connection)
                }
            }
            
            listener?.stateUpdateHandler = { state in
                switch state {
                case .ready:
                    print("🌐 CortexWebSocketServer listening on port 5421")
                case .failed(let error):
                    print("⚠️ CortexWebSocketServer failed: \(error)")
                default:
                    break
                }
            }
            
            listener?.start(queue: .global(qos: .userInitiated))
        } catch {
            print("⚠️ Failed to start CortexWebSocketServer: \(error)")
        }
    }
    
    private func handleConnection(_ connection: NWConnection) {
        activeConnections.append(connection)
        
        connection.stateUpdateHandler = { [weak self] state in
            guard let self = self else { return }
            Task { @MainActor in
                switch state {
                case .ready:
                    print("✅ WebSocket Client Connected")
                    self.swarmStatus = "Online (\(self.activeConnections.count) nodes)"
                    self.receiveMessages(from: connection)
                case .failed(_), .cancelled:
                    print("❌ WebSocket Client Disconnected")
                    self.activeConnections.removeAll(where: { $0 === connection })
                    self.swarmStatus = self.activeConnections.isEmpty ? "Offline" : "Online (\(self.activeConnections.count) nodes)"
                default:
                    break
                }
            }
        }
        
        connection.start(queue: .global(qos: .userInitiated))
    }
    
    private func receiveMessages(from connection: NWConnection) {
        connection.receiveMessage { [weak self] content, context, isComplete, error in
            guard let self = self else { return }
            
            if let error = error {
                print("⚠️ WebSocket receive error: \(error)")
                return
            }
            
            if let content = content, let message = String(data: content, encoding: .utf8) {
                Task { @MainActor in
                    print("📩 Swarm Status Update: \(message)")
                    if let data = message.data(using: .utf8),
                       let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                        if let count = json["nodes"] as? Int {
                            AppState.shared?.swarmNodeCount = count
                        }
                        if let status = json["status"] as? String {
                            AppState.shared?.swarmStatusText = status
                        }
                    }
                    self.receiveMessages(from: connection)
                }
            } else {
                Task { @MainActor in
                    self.receiveMessages(from: connection)
                }
            }
        }
    }
    
    func broadcast(message: String) {
        guard let data = message.data(using: .utf8) else { return }
        let metadata = NWProtocolWebSocket.Metadata(opcode: .text)
        let context = NWConnection.ContentContext(identifier: "Broadcast", metadata: [metadata])
        
        for connection in activeConnections {
            connection.send(content: data, contentContext: context, isComplete: true, completion: .contentProcessed({ error in
                if let error = error {
                    print("⚠️ WebSocket send error: \(error)")
                }
            }))
        }
    }
}
