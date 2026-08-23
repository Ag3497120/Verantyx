import Foundation
import Combine

// MARK: - ProcessMonitor
//
// macOS の ps コマンドを定期的にポーリングし、
// CPU を消費しているプロセスをリアルタイムで把握する。
//
// Verantyx IDE に関連するプロセス (ollama, mlx_lm, bitnet, swift など) を
// 優先的にハイライトし、AI とユーザーに状態を提供する。

@MainActor
final class ProcessMonitor: ObservableObject {

    static let shared = ProcessMonitor()

    // MARK: - 公開プロパティ

    @Published var topProcesses: [ProcessInfo] = []
    @Published var totalCPU: Double = 0           // 全プロセス合計 CPU%
    @Published var verantyxCPU: Double = 0        // Verantyx 関連プロセスの CPU%
    @Published var isHighLoad: Bool = false        // CPU > 60% なら true

    struct ProcessInfo: Identifiable {
        let id = UUID()
        let pid: Int
        let name: String
        let cpuPercent: Double
        let memMB: Double
        let isVerantyxRelated: Bool   // Ollama/mlx/bitnet/swift/cargo 等
        let label: String             // 表示用ラベル (絵文字付き)
    }

    // Verantyx エコシステムに関連するプロセス名パターン
    private let verantyxPatterns = [
        "ollama", "mlx_lm", "mlx-lm", "bitnet", "swift",
        "cargo", "rustc", "python", "python3", "Verantyx",
        "xcodebuild", "lldb", "lldb-rpc-server"
    ]

    private var timer: Timer?
    private let pollInterval: TimeInterval = 2.0

    private init() {}

    // MARK: - 公開API

    func start() {
        guard timer == nil else { return }
        Task { await self.poll() }  // 即時実行
        timer = Timer.scheduledTimer(withTimeInterval: pollInterval, repeats: true) { [weak self] _ in
            Task { @MainActor in await self?.poll() }
        }
    }

    func stop() {
        timer?.invalidate()
        timer = nil
    }

    // MARK: - ポーリング

    private func poll() async {
        let result = await runPS()
        let parsed = parsePS(result)

        // CPU 合計
        let total = parsed.reduce(0.0) { $0 + $1.cpuPercent }
        let vCPU  = parsed.filter { $0.isVerantyxRelated }.reduce(0.0) { $0 + $1.cpuPercent }

        topProcesses = Array(parsed.prefix(8))
        totalCPU = total
        verantyxCPU = vCPU
        isHighLoad = total > 60.0
    }

    // MARK: - ps コマンド実行

    private func runPS() async -> String {
        await withCheckedContinuation { continuation in
            DispatchQueue.global(qos: .utility).async {
                let proc = Process()
                proc.executableURL = URL(fileURLWithPath: "/bin/ps")
                // CPU 降順で上位20プロセスを取得
                proc.arguments = ["-Ao", "pid,pcpu,pmem,comm", "-r"]
                let pipe = Pipe()
                proc.standardOutput = pipe
                proc.standardError = FileHandle.nullDevice  // ⚠️ stderr は不要 — 未読パイプの deadlock 防止
                do {
                    try proc.run()
                    // ⚠️ 必ず waitUntilExit の前にデータを読み切る。
                    // 逆にすると出力がパイプバッファ(64KB)を超えた時にプロセスがwriteブロックし、
                    // Swift側はwaitUntilExitで永久ブロックするデッドロックが起きる。
                    let data = pipe.fileHandleForReading.readDataToEndOfFile()
                    proc.waitUntilExit()
                    continuation.resume(returning: String(data: data, encoding: .utf8) ?? "")
                } catch {
                    continuation.resume(returning: "")
                }
            }
        }
    }

    // MARK: - パース

    private func parsePS(_ output: String) -> [ProcessInfo] {
        var results: [ProcessInfo] = []
        let lines = output.components(separatedBy: "\n").dropFirst()  // ヘッダー行を除く

        for line in lines.prefix(20) {
            let parts = line.trimmingCharacters(in: .whitespaces)
                            .components(separatedBy: .whitespaces)
                            .filter { !$0.isEmpty }
            guard parts.count >= 4,
                  let pid = Int(parts[0]),
                  let cpu = Double(parts[1]),
                  let mem = Double(parts[2]) else { continue }

            let fullPath = parts[3...].joined(separator: " ")
            let name = URL(fileURLWithPath: fullPath).lastPathComponent

            // 0.1% 未満はスキップ
            guard cpu >= 0.1 else { continue }

            let isRelated = verantyxPatterns.contains { name.lowercased().contains($0) }
            let label = makeLabel(name: name, cpu: cpu)

            results.append(ProcessInfo(
                pid: pid,
                name: name,
                cpuPercent: cpu,
                memMB: mem,
                isVerantyxRelated: isRelated,
                label: label
            ))
        }

        return results.sorted { $0.cpuPercent > $1.cpuPercent }
    }

    private func makeLabel(name: String, cpu: Double) -> String {
        let lower = name.lowercased()
        if lower.contains("ollama")    { return "🤖 Ollama (\(String(format: "%.1f", cpu))%)" }
        if lower.contains("mlx")       { return "⚡ MLX (\(String(format: "%.1f", cpu))%)" }
        if lower.contains("bitnet")    { return "⬡ BitNet (\(String(format: "%.1f", cpu))%)" }
        if lower.contains("swift")     { return "🦅 Swift (\(String(format: "%.1f", cpu))%)" }
        if lower.contains("cargo") || lower.contains("rustc") { return "🦀 Rust (\(String(format: "%.1f", cpu))%)" }
        if lower.contains("python")    { return "🐍 Python (\(String(format: "%.1f", cpu))%)" }
        if lower.contains("xcodebuild") { return "🔨 Xcode (\(String(format: "%.1f", cpu))%)" }
        if lower.contains("verantyx")  { return "⟐ Verantyx (\(String(format: "%.1f", cpu))%)" }
        return "\(name) (\(String(format: "%.1f", cpu))%)"
    }
}
