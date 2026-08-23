import Foundation
import SwiftUI

// MARK: - GatekeeperModeState
//
// Gatekeeper Mode の中枢状態管理。
//
// ロール定義:
//   Commander (Local LLM) — Ollama  ← ファイルシステムへの完全アクセス権
//   Worker   (External API) — Claude/GPT ← JCross IR しか見えない
//
// 動作フロー:
//   User → Commander → JCrossVault.read() → Worker
//   Worker → JCross diff → Commander → ReverseTranspile → 実ファイル書き込み

@MainActor
final class GatekeeperModeState: ObservableObject {

    static let shared = GatekeeperModeState()

    // MARK: - Published State

    @Published var isEnabled: Bool = false {
        didSet {
            UserDefaults.standard.set(isEnabled, forKey: "gatekeeperModeEnabled")
            // ⚠️ ここでは自動変換しない。
            // 変換は「一括変換を開始」ボタン押下時のみ実行する。
            // 起動直後や大規模ワークスペースで自動実行するとメインスレッドが詰まる。
        }
    }

    @Published var commanderModel: String = "qwen2.5:1.5b" {
        didSet { UserDefaults.standard.set(commanderModel, forKey: "gatekeeperCommanderModel") }
    }

    @Published var workerProvider: CloudProvider = .claude {
        didSet { userDefaults.set(workerProvider.rawValue, forKey: "gatekeeperWorkerProvider") }
    }

    @Published var maxWorkerRetries: Int = 1 {
        didSet { userDefaults.set(maxWorkerRetries, forKey: "gatekeeperMaxWorkerRetries") }
    }

    enum MemoryLayerMode: String, CaseIterable, Equatable {
        case l1Only = "L1 Only"
        case l1ToL3 = "L1-L3 Full"
    }

    @Published var allowExternalLLMForCommander: Bool = true {
        didSet { userDefaults.set(allowExternalLLMForCommander, forKey: "gkAllowExternalLLM") }
    }

    @Published var bitnetMemoryLayerMode: MemoryLayerMode = .l1ToL3 {
        didSet { userDefaults.set(bitnetMemoryLayerMode.rawValue, forKey: "gkBitnetMemoryMode") }
    }

    @Published var useOllamaNER: Bool = true {
        didSet { userDefaults.set(useOllamaNER, forKey: "gkUseOllamaNER") }
    }

    @Published var vault: JCrossVault
    @Published var accessLog: [GatekeeperAccessLogEntry] = []
    @Published var phase: GatekeeperPhase = .idle
    @Published var currentProjectID: String = "default"

    // MARK: - Models

    enum GatekeeperPhase: Equatable {
        case idle
        case commanderPlanning(step: String)
        case fetchingVault(file: String)
        case workerCalling
        case workerThinking
        case reverseTranspiling
        case writingToDisk(file: String)
        case done
        case error(String)
    }

    private let userDefaults = UserDefaults.standard

    // MARK: - Init

    private init() {
        // currentDirectoryPath はサンドボックスでは読み取り専用バンドルを指すため使わない。
        // Application Support 内の専用ディレクトリを書き込み可能なデフォルトとして使用する。
        // ワークスペースが開かれると configure(workspaceURL:) で上書きされる。
        let workspaceURL = GatekeeperModeState.defaultVaultBaseURL()
        self.vault = JCrossVault(workspaceURL: workspaceURL)
        self.isEnabled = userDefaults.bool(forKey: "gatekeeperModeEnabled")
        
        if let savedModel = userDefaults.string(forKey: "gatekeeperCommanderModel") {
            self.commanderModel = savedModel
        }
        
        if let savedProviderStr = userDefaults.string(forKey: "gatekeeperWorkerProvider"),
           let savedProvider = CloudProvider(rawValue: savedProviderStr) {
            self.workerProvider = savedProvider
        }
        
        let savedRetries = userDefaults.integer(forKey: "gatekeeperMaxWorkerRetries")
        if savedRetries > 0 {
            self.maxWorkerRetries = savedRetries
        }

        if userDefaults.object(forKey: "gkAllowExternalLLM") != nil {
            self.allowExternalLLMForCommander = userDefaults.bool(forKey: "gkAllowExternalLLM")
        }

        if let savedModeStr = userDefaults.string(forKey: "gkBitnetMemoryMode"),
           let savedMode = MemoryLayerMode(rawValue: savedModeStr) {
            self.bitnetMemoryLayerMode = savedMode
        }

        if userDefaults.object(forKey: "gkUseOllamaNER") != nil {
            self.useOllamaNER = userDefaults.bool(forKey: "gkUseOllamaNER")
        }
    }

    /// 書き込み可能なデフォルト Vault ベースディレクトリ。
    /// ワークスペース未設定時の一時領域として ~/Library/Application Support/VerantyxIDE/jcross_vault/ を使う。
    static func defaultVaultBaseURL() -> URL {
        let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        let dir = support.appendingPathComponent("VerantyxIDE/DefaultVault", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    // MARK: - Configure for Workspace

    func configure(workspaceURL: URL) {
        vault = JCrossVault(workspaceURL: workspaceURL)
        // ✅ Task { } は @MainActor を継承するが、vault.initialize() は async なので
        // ディスクI/O中はサスペンドしてメインスレッドをブロックしない。
        // Task.detached + MainActor.run { self } は @MainActor クラスでは SIGTERM の原因。
        let v = vault
        Task {
            await v.initialize()
            self.phase = .idle
        }
    }


    // MARK: - Vault Initialization

    func initializeVault() async {
        phase = .fetchingVault(file: "ワークスペース全体")
        await vault.initialize()
        phase = .idle
    }

    // MARK: - Access Log

    func logAccess(
        tool: String,
        path: String,
        nodesExposed: Int,
        secretsRedacted: Int
    ) {
        let entry = GatekeeperAccessLogEntry(
            timestamp: Date(),
            tool: tool,
            path: path,
            nodesExposed: nodesExposed,
            secretsRedacted: secretsRedacted
        )
        accessLog.insert(entry, at: 0)
        if accessLog.count > 200 { accessLog.removeLast(50) }
    }

    // MARK: - Available Commander Models

    var availableCommanderModels: [String] {
        get async {
            struct Resp: Decodable { struct M: Decodable { let name: String }; let models: [M] }
            guard let url = URL(string: "http://localhost:11434/api/tags"),
                  let (data, _) = try? await URLSession.shared.data(from: url),
                  let json = try? JSONDecoder().decode(Resp.self, from: data)
            else { return [] }
            return json.models.map { $0.name }
        }
    }
}

// MARK: - GatekeeperAccessLogEntry

struct GatekeeperAccessLogEntry: Identifiable {
    let id = UUID()
    let timestamp: Date
    let tool: String
    let path: String
    let nodesExposed: Int
    let secretsRedacted: Int

    var isHighRisk: Bool { secretsRedacted > 0 }
}
