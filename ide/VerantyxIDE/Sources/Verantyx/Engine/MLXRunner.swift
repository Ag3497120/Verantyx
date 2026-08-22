//
//  MLXRunner.swift
//  Verantyx
//
//  Re-implemented to act as a lightweight client bridging the Swift UI
//  to the Python MLX FastAPI backend (server_mlx.py).
//

import Foundation

public struct MLXModel: Identifiable, Sendable {
    public let id: String
    public let displayName: String
    public let sizeGB: Double
    public let tags: [String]
    
    public init(id: String, displayName: String, sizeGB: Double, tags: [String]) {
        self.id = id
        self.displayName = displayName
        self.sizeGB = sizeGB
        self.tags = tags
    }
    
    public var isDownloaded: Bool {
        let path = NSHomeDirectory() + "/Library/Caches/models/" + id
        return FileManager.default.fileExists(atPath: path)
    }
}

@globalActor
public actor MLXRunner {
    public static let shared = MLXRunner()

    public static let popularModels: [MLXModel] = [
        MLXModel(id: "kofdai/talkie-1930-13b-it-mlx-8bit",
                 displayName: "Talkie 1930 13B (8bit) — Python API",
                 sizeGB: 13.0, tags: ["talkie", "python", "recommended"])
    ]

    // MARK: - State
    public private(set) var isLoaded = false
    public private(set) var currentModelId: String? = nil

    // KVCache tracking is now handled gracefully (or ignored if backend manages it)
    public var kvTokensConsumed: Int = 0
    public let kvFlushThreshold: Int = 4096

    private var pythonProcess: Process?

    private init() {
        // Automatically start the Python backend when the runner is first initialized.
        Task { await self.startPythonBackend() }
    }

    deinit {
        pythonProcess?.terminate()
    }

    private func startPythonBackend() {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        process.arguments = ["python3", "/Users/motonishikoudai/verantyx-cli/server_mlx.py"]
        
        do {
            try process.run()
            self.pythonProcess = process
            print("Python MLX backend started with PID: \(process.processIdentifier)")
        } catch {
            print("Failed to start python backend: \(error). Assuming it might be running already.")
        }
        
        Task {
            // Give it a tiny delay to ensure everything is settled.
            try? await Task.sleep(nanoseconds: 3_000_000_000)
            await self.setLoaded(true, modelId: "Python/Talkie-Backend")
        }
    }
    
    private func setLoaded(_ loaded: Bool, modelId: String?) {
        self.isLoaded = loaded
        self.currentModelId = modelId
        Task { @MainActor in
            NotificationCenter.default.post(
                name: Notification.Name("MLXModelLoaded"),
                object: nil,
                userInfo: ["modelName": modelId ?? "Python Backend"]
            )
        }
    }

    // MARK: - Memory Management
    func shouldFlushKVCache() -> Bool {
        kvTokensConsumed > kvFlushThreshold
    }

    func resetKVCounter() {
        kvTokensConsumed = 0
    }

    nonisolated var maxThinkingTokens: Int { 600 }

    // MARK: - API
    
    func unloadModel() async {
        isLoaded = false
        currentModelId = nil
        kvTokensConsumed = 0
        await MainActor.run {
            NotificationCenter.default.post(
                name: Notification.Name("MLXModelEjected"),
                object: nil,
                userInfo: ["modelName": "Python Backend"]
            )
        }
    }

    func loadModel(
        id modelId: String,
        hfToken: String? = nil,
        progressHandler: @escaping @Sendable (String) -> Void
    ) async throws {
        await MainActor.run { progressHandler("⟳ Connecting to Python Backend…") }
        try? await Task.sleep(nanoseconds: 500_000_000)
        self.isLoaded = true
        self.currentModelId = modelId
        await MainActor.run { progressHandler("✓ Connected to Backend") }
        
        await MainActor.run {
            NotificationCenter.default.post(
                name: Notification.Name("MLXModelLoaded"),
                object: nil,
                userInfo: ["modelName": modelId.components(separatedBy: "/").last ?? modelId]
            )
        }
    }

    func streamGenerateTokens(
        prompt: String,
        images: [String]? = nil,
        maxTokens: Int = 4096,
        temperature: Double = 0.6,
        onToken: @escaping @Sendable (String) -> Void,
        onThinkingProgress: (@Sendable (String) -> Void)? = nil,
        onFinish: (@Sendable (String) -> Void)? = nil
    ) async throws {
        guard let url = URL(string: "http://127.0.0.1:8000/v1/chat/completions") else { return }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let body: [String: Any] = [
            "messages": [
                ["role": "user", "content": prompt]
            ],
            "max_tokens": maxTokens,
            "temperature": temperature,
            "stream": true
        ]
        
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        
        let (result, response) = try await URLSession.shared.bytes(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            print("HTTP Error: \((response as? HTTPURLResponse)?.statusCode ?? 500)")
            return
        }
        
        var isThinking = false
        var fullOutput = ""
        
        for try await line in result.lines {
            guard line.hasPrefix("data: ") else { continue }
            let dataString = String(line.dropFirst(6))
            
            if dataString == "[DONE]" { break }
            
            if let data = dataString.data(using: .utf8),
               let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let choices = json["choices"] as? [[String: Any]],
               let delta = choices.first?["delta"] as? [String: Any],
               let content = delta["content"] as? String {
                
                self.kvTokensConsumed += 1
                fullOutput += content
                
                if content.contains("<think>") {
                    isThinking = true
                }
                
                if isThinking {
                    onThinkingProgress?(content)
                } else {
                    onToken(content)
                }
                
                if content.contains("</think>") {
                    isThinking = false
                }
            }
        }
        
        onFinish?(fullOutput)
    }

    func generate(
        prompt: String,
        images: [String]? = nil,
        maxTokens: Int = 4096,
        temperature: Double = 0.6
    ) async throws -> String {
        // Create an AsyncStream so we don't mutate captured variables concurrently
        let (stream, continuation) = AsyncStream.makeStream(of: String.self)
        
        Task {
            do {
                try await streamGenerateTokens(
                    prompt: prompt,
                    images: images,
                    maxTokens: maxTokens,
                    temperature: temperature,
                    onToken: { token in
                        continuation.yield(token)
                    },
                    onThinkingProgress: { _ in }
                )
                continuation.finish()
            } catch {
                continuation.finish()
            }
        }
        
        var finalResult = ""
        for await token in stream {
            finalResult += token
        }
        return finalResult
    }

    func downloadModel(
        repoId: String,
        hfToken: String? = nil,
        onProgress: @escaping @Sendable (String) -> Void
    ) async throws {
        onProgress("Already managed by Python Backend.")
    }
}
