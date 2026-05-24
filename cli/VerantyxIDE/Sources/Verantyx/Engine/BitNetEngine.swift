import Foundation
import SwiftUI

// MARK: - BitNetEngine
//
// Microsoft BitNet b1.58 をサブプロセスとして起動し、
// JCross トランスパイルの NER（固有表現抽出）タスクを実行する。
//
// アーキテクチャ:
//   IDE (Swift / Main Process)
//        ↕ stdin / stdout pipe (JSON-line protocol)
//   BitNet subprocess (llama-cli / bitnet.cpp バイナリ)
//        ↕ mmap (ゼロコピー重み読み込み)
//   BitNet b1.58-2B-4T model weights (.gguf)
//
// セキュリティ:
//   - BitNet プロセスはネットワーク接続を行わない
//   - 入出力はローカルパイプのみ
//   - モデルは ~/Library/Application Support/VerantyxIDE/ に保管

// MARK: - BitNetConfig

struct BitNetConfig: Codable {
    let binaryPath: String
    let modelPath: String
    let maxTokens: Int
    let temperature: Double
    let installedAt: String
    let modelName: String
    let nerPromptTemplate: String

    var isValid: Bool {
        FileManager.default.fileExists(atPath: binaryPath) &&
        FileManager.default.fileExists(atPath: modelPath)
    }

    static let configPath: String = {
        let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        return support.appendingPathComponent("VerantyxIDE/bitnet_config.json").path
    }()

    static func load() -> BitNetConfig? {
        guard let data = try? Data(contentsOf: URL(fileURLWithPath: configPath)),
              let config = try? JSONDecoder().decode(BitNetConfig.self, from: data)
        else { return nil }
        return config
    }

    enum CodingKeys: String, CodingKey {
        case binaryPath = "binary_path"
        case modelPath = "model_path"
        case maxTokens = "max_tokens"
        case temperature
        case installedAt = "installed_at"
        case modelName = "model_name"
        case nerPromptTemplate = "ner_prompt_template"
    }
}

// MARK: - BitNetNEREngine

/// BitNetTranspilerInterface の本実装。
/// bitnet.cpp の llama-cli バイナリを通じて 1-bit LLM を実行する。
final class BitNetNEREngine: BitNetTranspilerInterface, @unchecked Sendable {

    private let config: BitNetConfig
    private let processSemaphore = DispatchSemaphore(value: 1)  // 同時実行1件のみ

    init(config: BitNetConfig) {
        self.config = config
    }

    // MARK: - BitNetTranspilerInterface

    func extractSensitiveIdentifiers(from code: String) async -> [String] {
        // BitNet が利用可能か確認
        guard config.isValid else {
            // フォールバック: ルールベース NER
            return await RuleBaseNEREngine().extractSensitiveIdentifiers(from: code)
        }

        // コードが大きすぎる場合は先頭 4000 文字のみを使用
        let snippet = String(code.prefix(4000))

        let prompt = config.nerPromptTemplate
            .replacingOccurrences(of: "{CODE}", with: snippet)

        do {
            let response = try await runBitNet(prompt: prompt)
            let parsed = parseJSON(from: response)

            if parsed.isEmpty {
                // 結果が空の場合はルールベースで補完
                let ruleBase = await RuleBaseNEREngine().extractSensitiveIdentifiers(from: code)
                return ruleBase
            }

            return parsed
        } catch {
            // BitNet 実行失敗 → ルールベースへフォールバック
            print("⚠️ BitNet NER failed: \(error.localizedDescription) — falling back to rule-base")
            return await RuleBaseNEREngine().extractSensitiveIdentifiers(from: code)
        }
    }

    // MARK: - Run BitNet Subprocess

    private func runBitNet(prompt: String) async throws -> String {
        return try await withCheckedThrowingContinuation { continuation in
            // ⚠️ semaphore.wait() を GCD スレッド上に移動。
            // continuation 内でセマフォを待つと Swift Concurrency の協調スレッドプールが
            // ブロックされ、システム全体がデッドロックする。
            DispatchQueue.global(qos: .userInitiated).async { [weak self] in
                guard let self else {
                    continuation.resume(throwing: BitNetError.timeout)
                    return
                }
                self.processSemaphore.wait()

                let process = Process()
                process.executableURL = URL(fileURLWithPath: self.config.binaryPath)
                process.arguments = [
                    "-m", self.config.modelPath,
                    "-p", prompt,
                    "-n", String(self.config.maxTokens),
                    "--temp", String(self.config.temperature),
                    "-c", "2048",
                    "--threads", String(max(1, ProcessInfo.processInfo.processorCount / 2)),
                    "--no-perf",
                ]

                let stdoutPipe = Pipe()
                process.standardOutput = stdoutPipe
                process.standardError  = FileHandle.nullDevice  // ⚠️ stderr → nullDevice — terminationHandler 内の readToEnd deadlock 防止

                // readabilityHandler でストリーム読み取り（terminationHandler 内の readDataToEndOfFile デッドロック防止）
                let outputBox = _StringBox()
                stdoutPipe.fileHandleForReading.readabilityHandler = { handle in
                    let chunk = handle.availableData
                    guard !chunk.isEmpty, let text = String(data: chunk, encoding: .utf8) else { return }
                    outputBox.append(text)
                }

                let resumed = _AtomicFlag()

                let timeout = DispatchWorkItem {
                    if process.isRunning { process.terminate() }
                    stdoutPipe.fileHandleForReading.readabilityHandler = nil
                    self.processSemaphore.signal()
                    if resumed.trySet() {
                        continuation.resume(throwing: BitNetError.timeout)
                    }
                }
                DispatchQueue.global().asyncAfter(deadline: .now() + 30, execute: timeout)

                process.terminationHandler = { [weak self] proc in
                    timeout.cancel()
                    stdoutPipe.fileHandleForReading.readabilityHandler = nil
                    if let remainder = try? stdoutPipe.fileHandleForReading.readToEnd(),
                       let text = String(data: remainder, encoding: .utf8) {
                        outputBox.append(text)
                    }

                    let output = outputBox.value.trimmingCharacters(in: .whitespacesAndNewlines)
                    self?.processSemaphore.signal()

                    guard resumed.trySet() else { return }
                    if proc.terminationStatus == 0 || !output.isEmpty {
                        continuation.resume(returning: output)
                    } else {
                        continuation.resume(throwing: BitNetError.processError("exit code \(proc.terminationStatus)"))
                    }
                }

                do {
                    try process.run()
                } catch {
                    timeout.cancel()
                    stdoutPipe.fileHandleForReading.readabilityHandler = nil
                    self.processSemaphore.signal()
                    if resumed.trySet() {
                        continuation.resume(throwing: BitNetError.launchFailed(error))
                    }
                }
            }
        }
    }

    // MARK: - JSON Parser

    private func parseJSON(from response: String) -> [String] {
        // レスポンスから JSON 配列を抽出
        guard let start = response.firstIndex(of: "["),
              let end   = response.lastIndex(of: "]"),
              start <= end
        else { return [] }

        let jsonStr = String(response[start...end])
        guard let data = jsonStr.data(using: .utf8),
              let array = try? JSONDecoder().decode([String].self, from: data)
        else { return [] }

        // フィルタリング: 3文字以上、英数字のみ
        return array.filter { $0.count >= 3 && $0.allSatisfy { $0.isLetter || $0.isNumber || $0 == "_" } }
    }

    // MARK: - Error

    enum BitNetError: Error, LocalizedError {
        case timeout
        case processError(String)
        case launchFailed(Error)
        case modelNotFound

        var errorDescription: String? {
            switch self {
            case .timeout:           return "BitNet NER timed out (30s)"
            case .processError(let m): return "BitNet process error: \(m.prefix(200))"
            case .launchFailed(let e): return "BitNet launch failed: \(e.localizedDescription)"
            case .modelNotFound:     return "BitNet model not found"
            }
        }
    }
}

// MARK: - BitNetEngineManager (ObservableObject)

@MainActor
final class BitNetEngineManager: ObservableObject {

    static let shared = BitNetEngineManager()

    // MARK: - State

    enum Status: Equatable {
        case notInstalled        // セットアップ未実施
        case checking            // 確認中
        case ready(modelName: String, sizeMB: Int)  // 使用可能
        case error(String)       // エラー
        case installing          // インストール中
    }

    @Published var status: Status = .checking
    @Published var nerEngine: (any BitNetTranspilerInterface)?
    @Published var setupProgress: String = ""
    @Published var setupLog: [String] = []
    /// 0.0–1.0 ダウンロード進捗（推定）。スクリプトログから更新。
    @Published var downloadProgress: Double = 0.0

    private var setupProcess: Process?

    private init() {
        Task { await checkInstallation() }
    }

    // MARK: - Installation Check

    func checkInstallation() async {
        // インストール中はステータスを上書きしない（ダウンロードUIが閉じるのを防ぐ）
        if case .installing = status { return }
        status = .checking
        guard let config = BitNetConfig.load(), config.isValid else {
            status = .notInstalled
            return
        }

        // モデルサイズ取得
        let attrs  = try? FileManager.default.attributesOfItem(atPath: config.modelPath)
        let bytes  = (attrs?[.size] as? Int) ?? 0
        let sizeMB = bytes / 1_048_576

        nerEngine = BitNetNEREngine(config: config)
        status    = .ready(modelName: config.modelName, sizeMB: sizeMB)
    }

    // MARK: - Install / Setup

    func runSetup() async {
        status = .installing
        setupLog = []
        downloadProgress = 0.0
        setupProgress = "セットアップスクリプトを起動中..."

        let scriptPath = self.setupScriptPath()

        // スクリプトが存在するか確認
        guard FileManager.default.fileExists(atPath: scriptPath) else {
            status = .error("setup_bitnet.sh が見つかりません: \(scriptPath)")
            return
        }

        do {
            try await runShellScript(scriptPath)
            // インストール完了後のみ checkInstallation を呼ぶ
            // （ここに来た時点で status は .installing のまま → 安全に上書き可能）
            status = .checking  // 一時的に .checking へ（UI上は確認中スピナー）
            await checkInstallation()
            if case .ready = status {
                addLog(AppLanguage.shared.t("✅ BitNet b1.58 setup complete!", "✅ BitNet b1.58 セットアップ完了!"))
                downloadProgress = 1.0
            } else {
                status = .error("インストール後の確認に失敗しました。再試行してください。")
            }
        } catch {
            status = .error("セットアップ失敗: \(error.localizedDescription)")
            addLog("❌ \(error.localizedDescription)")
        }
    }

    private func runShellScript(_ path: String) async throws {
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/bin/bash")
            process.arguments = [path]

            let pipe = Pipe()
            process.standardOutput = pipe
            process.standardError  = pipe

            // リアルタイムログ読み取り
            pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
                let data = handle.availableData
                guard !data.isEmpty,
                      let line = String(data: data, encoding: .utf8)?
                          .trimmingCharacters(in: .whitespacesAndNewlines),
                      !line.isEmpty
                else { return }
                DispatchQueue.main.async {
                    self?.addLog(line)
                    self?.setupProgress = line
                    // ダウンロード進捗を推定（"Downloading" or "xx%" を検出）
                    if let pct = line.range(of: #"(\d+)%"#, options: .regularExpression)
                           .map({ String(line[$0]) })
                           .flatMap({ Int($0.dropLast()) }) {
                        self?.downloadProgress = Double(pct) / 100.0
                    } else if line.lowercased().contains("download") {
                        self?.downloadProgress = min((self?.downloadProgress ?? 0) + 0.02, 0.95)
                    } else if line.lowercased().contains("build") || line.lowercased().contains("cmake") {
                        // ビルドフェーズ: 進捗バーを 0.5 以上に固定
                        if (self?.downloadProgress ?? 0) < 0.5 {
                            self?.downloadProgress = 0.5
                        }
                    }
                }
            }

            process.terminationHandler = { proc in
                pipe.fileHandleForReading.readabilityHandler = nil
                if proc.terminationStatus == 0 {
                    continuation.resume()
                } else {
                    continuation.resume(throwing: SetupError.failed(proc.terminationStatus))
                }
            }

            do {
                try process.run()
                setupProcess = process
            } catch {
                continuation.resume(throwing: error)
            }
        }
    }

    private func addLog(_ line: String) {
        setupLog.append(line)
        if setupLog.count > 500 { setupLog.removeFirst(100) }  // ログが膨らみすぎないよう管理
    }

    private func setupScriptPath() -> String {
        // アプリバンドル内のスクリプトを優先、なければプロジェクトディレクトリ
        if let bundlePath = Bundle.main.path(forResource: "setup_bitnet", ofType: "sh") {
            return bundlePath
        }
        return "/Users/motonishikoudai/verantyx-cli/VerantyxIDE/setup_bitnet.sh"
    }

    enum SetupError: Error, LocalizedError {
        case failed(Int32)
        var errorDescription: String? { "セットアップスクリプトが終了コード \(self) で失敗しました" }
    }

    // MARK: - Quick NER Test

    func testNER(code: String = #"let stripeKey = "sk_live_XYZ123"; let email = "admin@company.com""#) async -> [String] {
        guard let engine = nerEngine else { return [] }
        return await engine.extractSensitiveIdentifiers(from: code)
    }
}

// MARK: - BitNetSetupView

struct BitNetSetupView: View {
    @ObservedObject private var manager = BitNetEngineManager.shared
    @State private var testResult: [String] = []
    @State private var isTesting = false


    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Header
            HStack {
                Image(systemName: "cpu.fill")
                    .foregroundStyle(.purple)
                    .font(.title2)
                Text(AppLanguage.shared.t("BitNet b1.58 — Local 1-bit LLM", "BitNet b1.58 — ローカル 1-bit LLM"))
                    .font(.headline)
                Spacer()
                statusBadge
            }
            .padding()
            .background(.ultraThinMaterial)

            Divider()

            ScrollView {
                VStack(alignment: .leading, spacing: 16) {

                    // Architecture Diagram
                    architectureCard

                    // Status / Action
                    switch manager.status {
                    case .notInstalled:
                        notInstalledCard

                    case .checking:
                        loadingCard

                    case .ready(let name, let size):
                        readyCard(model: name, size: size)

                    case .installing:
                        installingCard

                    case .error(let msg):
                        errorCard(msg)
                    }

                    // NER Test
                    if case .ready = manager.status {
                        nerTestCard
                    }
                }
                .padding()
            }
        }
        // NOTE: minWidth/minHeight を外す → SettingsView の固定コンテナと競合しない
        .frame(maxWidth: .infinity)
    }

    // MARK: - Sub-views

    @ViewBuilder
    private var statusBadge: some View {
        switch manager.status {
        case .ready:
            Label(AppLanguage.shared.t("Running", "稼働中"), systemImage: "circle.fill")
                .foregroundStyle(.green)
                .font(.caption)
        case .installing:
            Label(AppLanguage.shared.t("Installing", "インストール中"), systemImage: "arrow.down.circle.fill")
                .foregroundStyle(.orange)
                .font(.caption)
        case .notInstalled:
            Label(AppLanguage.shared.t("Not Installed", "未インストール"), systemImage: "circle")
                .foregroundStyle(.secondary)
                .font(.caption)
        default:
            Label(AppLanguage.shared.t("Checking", "確認中"), systemImage: "ellipsis.circle.fill")
                .foregroundStyle(.blue)
                .font(.caption)
        }
    }

    private var architectureCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(AppLanguage.shared.t("Architecture", "アーキテクチャ"), systemImage: "square.3.layers.3d")
                .font(.subheadline.bold())
                .foregroundStyle(.purple)

            Text("""
            IDE ──→ [BitNetEngine] ──→ llama-cli subprocess
                         │                      │
                    stdin/stdout pipe      BitNet b1.58 weights (.gguf)
                         │                 (weights are 1.58-bit = ultra light)
                    [NER JSON Output]            │
                         │                 Uses CPU idle threads only
                    [JCross Transpiler]    No GPU/NPU required
            """)
            .font(.system(.caption, design: .monospaced))
            .padding(10)
            .background(Color.purple.opacity(0.08))
            .clipShape(RoundedRectangle(cornerRadius: 8))
        }
        .padding()
        .background(.thinMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private var notInstalledCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label(AppLanguage.shared.t("BitNet b1.58 is not installed", "BitNet b1.58 が未インストールです"), systemImage: "exclamationmark.triangle")
                .foregroundStyle(.orange)
                .font(.subheadline.bold())

            Text(AppLanguage.shared.t("Setup script will auto-install Homebrew, cmake, bitnet.cpp, and download 2B model (~800MB).", "セットアップスクリプトが Homebrew・cmake・bitnet.cpp を自動インストールし、2B モデル (~800MB) をダウンロードします。"))
                .font(.caption)
                .foregroundStyle(.secondary)

            Text(AppLanguage.shared.t("Estimated time: 10-30 min for the first time (build & download)", "所要時間: 初回約 10〜30分（ビルドとダウンロード）"))
                .font(.caption2)
                .foregroundStyle(.secondary)

            Button {
                Task { await manager.runSetup() }
            } label: {
                Label(AppLanguage.shared.t("Setup BitNet b1.58", "BitNet b1.58 をセットアップ"), systemImage: "arrow.down.circle.fill")
                    .frame(maxWidth: .infinity)
            }
            .controlSize(.large)
            .buttonStyle(.borderedProminent)
            .tint(.purple)
        }
        .padding()
        .background(.thinMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private var loadingCard: some View {
        HStack {
            ProgressView().scaleEffect(0.8)
            Text(AppLanguage.shared.t("Checking installation status...", "インストール状態を確認中..."))
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding()
    }

    private func readyCard(model: String, size: Int) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(AppLanguage.shared.t("BitNet b1.58 — Ready", "BitNet b1.58 — 使用可能"), systemImage: "checkmark.circle.fill")
                .foregroundStyle(.green)
                .font(.subheadline.bold())

            Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 4) {
                GridRow {
                    Text(AppLanguage.shared.t("Model", "モデル")).font(.caption).foregroundStyle(.secondary)
                    Text(model).font(.caption.monospaced())
                }
                GridRow {
                    Text(AppLanguage.shared.t("Size", "サイズ")).font(.caption).foregroundStyle(.secondary)
                    Text("\(size) MB").font(.caption.monospaced())
                }
                GridRow {
                    Text(AppLanguage.shared.t("Precision", "精度")).font(.caption).foregroundStyle(.secondary)
                    Text(AppLanguage.shared.t("1.58-bit (Ternary -1/0/+1)", "1.58-bit (三値 -1/0/+1)")).font(.caption.monospaced())
                }
                GridRow {
                    Text(AppLanguage.shared.t("Task", "タスク")).font(.caption).foregroundStyle(.secondary)
                    Text(AppLanguage.shared.t("NER → JCross Transpile", "NER → JCross トランスパイル")).font(.caption.monospaced())
                }
            }
        }
        .padding()
        .background(Color.green.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private var installingCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            // ── ヘッダー ────────────────────────────────────────────────────
            HStack(spacing: 8) {
                ProgressView()
                    .scaleEffect(0.75)
                    .frame(width: 14, height: 14)
                Text(manager.setupProgress.isEmpty
                        ? AppLanguage.shared.t("Setting up...", "セットアップ中...")
                        : String(manager.setupProgress.prefix(80)))
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
                Spacer()
                // 進捗パーセンテージ
                if manager.downloadProgress > 0 {
                    Text("\(Int(manager.downloadProgress * 100))%")
                        .font(.system(size: 11, weight: .semibold, design: .monospaced))
                        .foregroundStyle(Color(red: 0.7, green: 0.4, blue: 1.0))
                }
            }

            // ── プログレスバー ──────────────────────────────────────────────
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 3)
                        .fill(Color.white.opacity(0.08))
                        .frame(height: 6)
                    RoundedRectangle(cornerRadius: 3)
                        .fill(
                            LinearGradient(
                                colors: [Color(red: 0.5, green: 0.2, blue: 0.9),
                                         Color(red: 0.7, green: 0.4, blue: 1.0)],
                                startPoint: .leading,
                                endPoint: .trailing
                            )
                        )
                        .frame(width: max(6, geo.size.width * manager.downloadProgress), height: 6)
                        .animation(.easeInOut(duration: 0.3), value: manager.downloadProgress)
                }
            }
            .frame(height: 6)

            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading) {
                        ForEach(Array(manager.setupLog.enumerated()), id: \.offset) { i, line in
                            Text(line)
                                .font(.system(.caption2, design: .monospaced))
                                .foregroundStyle(line.hasPrefix("✓") ? .green :
                                                 line.hasPrefix("❌") ? .red : .primary)
                                .id(i)
                        }
                    }
                    .padding(8)
                }
                .frame(height: 200)
                .background(Color.black.opacity(0.6))
                .clipShape(RoundedRectangle(cornerRadius: 8))
                .onChange(of: manager.setupLog.count) { _, _ in
                    proxy.scrollTo(manager.setupLog.count - 1, anchor: .bottom)
                }
            }
        }
        .padding()
        .background(.thinMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private func errorCard(_ msg: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(AppLanguage.shared.t("Error", "エラー"), systemImage: "xmark.circle.fill")
                .foregroundStyle(.red)
                .font(.subheadline.bold())
            Text(msg)
                .font(.caption.monospaced())
                .foregroundStyle(.secondary)
            Button(AppLanguage.shared.t("Retry", "再試行")) {
                Task { await manager.runSetup() }
            }
            .buttonStyle(.borderedProminent)
            .tint(.red)
        }
        .padding()
        .background(Color.red.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private var nerTestCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(AppLanguage.shared.t("NER Test", "NER テスト"), systemImage: "magnifyingglass")
                .font(.subheadline.bold())
                .foregroundStyle(.purple)

            Text(AppLanguage.shared.t("Test input: let stripeKey = \"sk_live_ABC123\"; let serverIP = \"192.168.1.45\"", "テスト入力: let stripeKey = \"sk_live_ABC123\"; let serverIP = \"192.168.1.45\""))
                .font(.caption.monospaced())
                .foregroundStyle(.secondary)

            Button {
                isTesting = true
                Task {
                    testResult = await manager.testNER()
                    isTesting = false
                }
            } label: {
                if isTesting {
                    ProgressView().scaleEffect(0.7)
                } else {
                    Label(AppLanguage.shared.t("Run BitNet NER", "BitNet NER を実行"), systemImage: "play.fill")
                }
            }
            .buttonStyle(.bordered)
            .disabled(isTesting)

            if !testResult.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text(AppLanguage.shared.t("Detection result:", "検出結果:")).font(.caption.bold())
                    ForEach(testResult, id: \.self) { token in
                        Label(token, systemImage: "lock.fill")
                            .font(.caption.monospaced())
                            .foregroundStyle(.orange)
                    }
                }
                .padding(8)
                .background(Color.orange.opacity(0.08))
                .clipShape(RoundedRectangle(cornerRadius: 8))
            }
        }
        .padding()
        .background(.thinMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }
}

// MARK: - BitNetCommanderEngine
//
// GatekeeperMode の Commander 専用 BitNet ラッパー。
// BitNetNEREngine (NER タスク専用) とは別のセマフォで動作し、
// 汎用テキスト生成（計画・要約・最終回答）を担う。
//
// 優先順位:
//   1. BitNetConfig が有効 → BitNet サブプロセスで生成
//   2. BitNet 未インストール / タイムアウト → nil を返す → Ollama フォールバック

final class BitNetCommanderEngine: @unchecked Sendable {

    static let shared = BitNetCommanderEngine()

    private let semaphore = DispatchSemaphore(value: 1)  // Commander は同時1件

    private init() {}

    // MARK: - Availability Check

    /// BitNet \u304c\u30a4\u30f3\u30b9\u30c8\u30fc\u30eb\u6e08\u307f\u304b\u3069\u3046\u304b\u3092\u8fd4\u3059\u3002
    /// AppState.sendMessage \u304c BitNetCommanderLoop \u306b\u30eb\u30fc\u30c6\u30a3\u30f3\u30b0\u3059\u308b\u524d\u306b\u547c\u3073\u51fa\u3059\u3002
    func isAvailable() async -> Bool {
        BitNetConfig.load()?.isValid == true
    }

    // MARK: - Generate

    /// BitNet を使って Commander 用の自由形式テキストを生成する。
    /// BitNet が未インストールの場合は nil を返す（Ollama フォールバック用）。
    func generate(prompt: String, systemPrompt: String) async -> String? {
        guard let config = BitNetConfig.load(), config.isValid else {
            return nil  // 未インストール → Ollama フォールバック
        }

        // system prompt を先頭に結合（単一プロンプトとして渡す）
        let fullPrompt: String
        if systemPrompt.isEmpty {
            fullPrompt = prompt
        } else {
            fullPrompt = "### Instruction:\n\(systemPrompt)\n\n\(prompt)\n\n### Response:\n"
        }

        do {
            let response = try await runBitNetGenerate(config: config, prompt: fullPrompt)
            return response
        } catch {
            print("⚠️ BitNetCommanderEngine: \(error.localizedDescription) — falling back to Ollama")
            return nil
        }
    }

    // MARK: - Subprocess

    /// プロンプトをファイルに書き出して -f フラグで渡す。
    /// 理由:
    ///   1. -p 引数は ARG_MAX (~1MB) 制限があり長いプロンプトで失敗する
    ///   2. --no-display-prompt はこのバイナリでは生成テキストごと消えてしまう
    ///   3. readabilityHandler でストリーム読み取りして terminationHandler の
    ///      readDataToEndOfFile デッドロックを回避する
    private func runBitNetGenerate(config: BitNetConfig, prompt: String) async throws -> String {
        // プロンプトを一時ファイルへ書き込む
        let tmpDir  = FileManager.default.temporaryDirectory
        let tmpFile = tmpDir.appendingPathComponent("vx_bitnet_\(Int(Date().timeIntervalSince1970)).txt")
        try prompt.write(to: tmpFile, atomically: true, encoding: .utf8)
        defer { try? FileManager.default.removeItem(at: tmpFile) }

        // ⚠️ semaphore.wait() を continuation の外（GCDスレッド上）に移動。
        // withCheckedThrowingContinuation 内でセマフォを待つと Swift Concurrency の
        // 協調スレッドプールがブロックされ、システム全体がデッドロックする。
        return try await withCheckedThrowingContinuation { continuation in
            DispatchQueue.global(qos: .userInitiated).async { [weak self] in
                guard let self else {
                    continuation.resume(throwing: BitNetCommanderError.timeout)
                    return
                }
                self.semaphore.wait()

                let process = Process()
                process.executableURL = URL(fileURLWithPath: config.binaryPath)
                process.arguments = [
                    "-m", config.modelPath,
                    "-p", prompt,
                    "-n", "512",
                    "--temp", String(config.temperature),
                    "-c", "2048",
                    "--threads", String(max(2, ProcessInfo.processInfo.processorCount / 2)),
                    "--repeat-penalty", "1.15",
                    "--no-perf",
                    "-r", "###",
                    "-r", "### Instruction:",
                    "-r", "User:"
                ]

                let stdinPipe = Pipe()
                let stdoutPipe = Pipe()
                process.standardInput = stdinPipe
                process.standardOutput = stdoutPipe
                process.standardError  = FileHandle.nullDevice  // ⚠️ stderr → nullDevice — terminationHandler 内の readToEnd deadlock 防止

                try? stdinPipe.fileHandleForWriting.close()

                let outputBox = _StringBox()
                stdoutPipe.fileHandleForReading.readabilityHandler = { handle in
                    let chunk = handle.availableData
                    guard !chunk.isEmpty,
                          let text = String(data: chunk, encoding: .utf8)
                    else { return }
                    outputBox.append(text)
                }

                let resumed = _AtomicFlag()

                let timeout = DispatchWorkItem {
                    if process.isRunning { process.terminate() }
                    stdoutPipe.fileHandleForReading.readabilityHandler = nil
                    self.semaphore.signal()
                    if resumed.trySet() {
                        continuation.resume(throwing: BitNetCommanderError.timeout)
                    }
                }
                DispatchQueue.global().asyncAfter(deadline: .now() + 90, execute: timeout)

                process.terminationHandler = { [weak self] proc in
                    timeout.cancel()
                    stdoutPipe.fileHandleForReading.readabilityHandler = nil
                    if let remainder = try? stdoutPipe.fileHandleForReading.readToEnd(),
                       let text = String(data: remainder, encoding: .utf8) {
                        outputBox.append(text)
                    }

                    let output = outputBox.value.trimmingCharacters(in: .whitespacesAndNewlines)
                    self?.semaphore.signal()

                    guard resumed.trySet() else { return }
                    if proc.terminationStatus == 0 || !output.isEmpty {
                        let cleaned = Self.stripEchoedPrompt(output: output, prompt: prompt)
                        continuation.resume(returning: cleaned)
                    } else {
                        continuation.resume(throwing: BitNetCommanderError.processError("exit code \(proc.terminationStatus)"))
                    }
                }

                do {
                    try process.run()
                } catch {
                    timeout.cancel()
                    stdoutPipe.fileHandleForReading.readabilityHandler = nil
                    self.semaphore.signal()
                    if resumed.trySet() {
                        continuation.resume(throwing: BitNetCommanderError.launchFailed(error))
                    }
                }
            }
        }
    }

    /// llama-cli がプロンプト自体を stdout に echo するので除去する。
    /// また ANSI エスケープシーケンスや BOM も除去してクリーンなテキストを返す。
    private static func stripEchoedPrompt(output: String, prompt: String) -> String {
        // ── Step 1: ANSI エスケープシーケンスを除去 ──────────────────────
        // llama-cli は --no-color フラグなしだと \e[...m などを stdout に出す
        var cleaned = output
        if cleaned.contains("\u{1B}[") {
            // 正規表現: ESC [ ... m  (SGR シーケンス)
            if let regex = try? NSRegularExpression(pattern: "\\x1B\\[[0-9;]*[mGKHF]") {
                let range = NSRange(cleaned.startIndex..., in: cleaned)
                cleaned = regex.stringByReplacingMatches(in: cleaned, range: range, withTemplate: "")
            }
        }
        // BOM と NULL バイトを除去
        cleaned = cleaned
            .replacingOccurrences(of: "\u{FEFF}", with: "")
            .replacingOccurrences(of: "\u{0000}", with: "")

        // ── Step 2: マーカーで分割（Commander モードのプロンプト形式）──
        // 形式: ### Instruction:\n...\n\n### Response:\n<生成部分>
        let assistantMarker = "### Response:"
        if let range = cleaned.range(of: assistantMarker) {
            var result = String(cleaned[range.upperBound...]).trimmingCharacters(in: .whitespacesAndNewlines)
            while result.hasSuffix("#") { result.removeLast() }
            return result.trimmingCharacters(in: .whitespacesAndNewlines)
        }
        // 別形式: ### Assistant や <|assistant|> も試みる
        for marker in ["### Assistant:", "### Response:", "<|assistant|>", "[/INST]"] {
            if let range = cleaned.range(of: marker) {
                var result = String(cleaned[range.upperBound...]).trimmingCharacters(in: .whitespacesAndNewlines)
                while result.hasSuffix("#") { result.removeLast() }
                return result.trimmingCharacters(in: .whitespacesAndNewlines)
            }
        }

        // ── Step 3: プロンプト先頭一致フォールバック ──────────────────────
        // prompt の先頭 120 文字が output 先頭と一致する場合はまるごと除去
        let checkLen = min(prompt.count, 120)
        if checkLen > 10 {
            let promptHead = String(prompt.prefix(checkLen))
            if cleaned.hasPrefix(promptHead) {
                let afterPrompt = String(cleaned.dropFirst(prompt.count))
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                if !afterPrompt.isEmpty { return afterPrompt }
            }
        }

        return cleaned.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    // MARK: - Error

    enum BitNetCommanderError: Error, LocalizedError {
        case timeout
        case processError(String)
        case launchFailed(Error)

        var errorDescription: String? {
            switch self {
            case .timeout:             return "BitNet Commander timed out (90s)"
            case .processError(let m): return "BitNet Commander process error: \(m.prefix(200))"
            case .launchFailed(let e): return "BitNet Commander launch failed: \(e.localizedDescription)"
            }
        }
    }
}

// MARK: - _StringBox (internal helper)
// readabilityHandler のチャンクを蓄積するスレッドセーフボックス。
// DispatchQueue によりデータ競合を防ぐ。

final class _StringBox: @unchecked Sendable {
    private var _value: String = ""
    private let queue = DispatchQueue(label: "vx.stringbox", qos: .utility)

    var value: String { queue.sync { _value } }

    func append(_ text: String) {
        queue.sync { self._value += text }
    }
}
