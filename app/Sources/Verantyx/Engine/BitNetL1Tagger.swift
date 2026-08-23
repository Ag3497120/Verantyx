import Foundation

// MARK: - BitNetL1Tagger
//
// BitNet b1.58 を使い、ソースコードから JCross v2.2 構造メタデータ (L1トポロジータグ) を抽出する。
//
// 設計原則（Test A 実験結果に基づく）:
//   - 適度な長さの英語指示文（~30トークン）が最も安定した出力を引き出す
//   - 出力フォーマットは JCross v2.2 の 6-Axis Opaque タグ群を要求する
//   - 失敗時はルールベースフォールバックで構造タグを割り当てる
//
// 出力例: "[CTRL_async:1.0][SEC_hash:0.9][TYPE_opaque:0.8]"
//
// ゲートキーパーモードでの役割:
//   source → BitNetL1Tagger → v2.2 tags (.l1tags)    ← このファイルが担う
//   source → JCrossIRGenerator → 6-Axis IR + Vault分離
//   V2.2 tags + JCross IR → Cloud LLM → JCross diff
//   JCross diff + schema → VaultPatcher → 実コード変更

final class BitNetL1Tagger: @unchecked Sendable {

    static let shared = BitNetL1Tagger()
    private let semaphore = DispatchSemaphore(value: 1)

    private init() {}

    // MARK: - Public API

    /// ソースコードから L1 構造トポロジータグ (v2.2) を生成する。
    /// - Parameters:
    ///   - code: ソースコード（先頭 200 行を使用）
    ///   - language: プログラミング言語名（ヒントとして使用）
    /// - Returns: "[CTRL_async:1.0][SEC_hash:0.9]" 形式の文字列
    func generateL1Tags(from code: String, language: String) async -> String {
        guard let config = BitNetConfig.load(), config.isValid else {
            // BitNet 未インストール → ルールベースフォールバック
            return ruleBasedTags(for: code, language: language)
        }

        // コンテキスト制限: 先頭 3000 文字（~750トークン）のみ
        let snippet = String(code.prefix(3000))

        // Test A スタイル: 適度な長さの英語指示 + 明確な出力形式の例示
        let prompt = """
        You are a JCross v2.2 structural analyzer. Read the following \(language) code and extract \
        3 to 5 Gatekeeper IR structural tags that best represent its core operations. \
        Format your answer EXACTLY as: [CTRL_loop:1.0][MEM_alloc:0.9][TYPE_opaque:0.8] \
        Valid prefixes: CTRL_, MEM_, TYPE_, SCOPE_, NET_, SEC_. \
        Use scores from 1.0 (most central) to 0.7 (supporting). \
        Output only the structural tags on one line, nothing else.

        Code:
        \(snippet)

        Tags:
        """

        do {
            let raw = try await runBitNet(config: config, prompt: prompt, maxTokens: 40)
            let parsed = parseL1Tags(from: raw)
            if parsed.isEmpty {
                return ruleBasedTags(for: code, language: language)
            }
            return parsed
        } catch {
            print("⚠️ BitNetL1Tagger: \(error.localizedDescription) — rule-base fallback")
            return ruleBasedTags(for: code, language: language)
        }
    }

    // MARK: - Subprocess

    private func runBitNet(config: BitNetConfig, prompt: String, maxTokens: Int) async throws -> String {
        return try await withCheckedThrowingContinuation { continuation in
            // ⚠️ semaphore.wait() を GCD スレッド上に移動。
            // continuation 内でセマフォを待つと Swift Concurrency の協調スレッドプールが
            // ブロックされ、システム全体がデッドロックする。
            DispatchQueue.global(qos: .userInitiated).async { [weak self] in
                guard let self else {
                    continuation.resume(throwing: L1TaggerError.timeout)
                    return
                }
                self.semaphore.wait()

                let process = Process()
                process.executableURL = URL(fileURLWithPath: config.binaryPath)
                process.arguments = [
                    "-m", config.modelPath,
                    "-p", prompt,
                    "-n", String(maxTokens),
                    "--temp", "0.05",
                    "-c", "2048",
                    "--threads", String(max(2, ProcessInfo.processInfo.processorCount / 2)),
                    "--no-perf",
                ]

                let stdoutPipe = Pipe()
                process.standardOutput = stdoutPipe
                process.standardError  = FileHandle.nullDevice  // ⚠️ stderr → nullDevice — terminationHandler 内の readDataToEndOfFile deadlock 防止

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
                    self.semaphore.signal()
                    if resumed.trySet() {
                        continuation.resume(throwing: L1TaggerError.timeout)
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
                    self?.semaphore.signal()

                    guard resumed.trySet() else { return }
                    if proc.terminationStatus == 0 || !output.isEmpty {
                        continuation.resume(returning: output)
                    } else {
                        continuation.resume(throwing: L1TaggerError.processError("exit code \(proc.terminationStatus)"))
                    }
                }

                do {
                    try process.run()
                } catch {
                    timeout.cancel()
                    self.semaphore.signal()
                    if resumed.trySet() {
                        continuation.resume(throwing: L1TaggerError.launchFailed(error))
                    }
                }
            }
        }
    }

    // MARK: - L1 Tag Parser

    /// モデルの出力から [TAG:score] パターンを抽出する。
    /// エコーされたプロンプト部分は無視し、タグ行のみを取り出す。
    private func parseL1Tags(from raw: String) -> String {
        // "Tags:" の後に来る行を探す（エコー対策）
        let lines = raw.components(separatedBy: "\n")
        for line in lines.reversed() {
            let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
            // [TAG_NAME:数値] パターンが含まれる行を探す
            if trimmed.contains("[") && trimmed.contains(":") && trimmed.contains("]") {
                // パターン検証: [XXX_YYY:Z.W] 形式
                let regex = try? NSRegularExpression(pattern: #"\\[[A-Za-z0-9_]+:\\d\\.\\d\\]"#)
                let range = NSRange(trimmed.startIndex..., in: trimmed)
                let matches = regex?.numberOfMatches(in: trimmed, range: range) ?? 0
                if matches > 0 {
                    return trimmed
                }
            }
        }
        return ""
    }

    // MARK: - Rule-based Fallback

    /// BitNet 未使用時のルールベースタグ生成。
    /// ファイル言語・キーワードの出現頻度から代表的な v2.2 タグを割り当てる。
    private func ruleBasedTags(for code: String, language: String) -> String {
        var scores: [(String, Double)] = []

        // 言語ベースタグ
        switch language.lowercased() {
        case "swift":    scores.append(("[TYPE_swift:1.0]", 1.0))
        case "rust":     scores.append(("[MEM_safe:1.0]", 1.0))
        case "python":   scores.append(("[TYPE_dynamic:1.0]", 1.0))
        case "typescript", "javascript":
                         scores.append(("[TYPE_opaque:1.0]", 1.0))
        case "go":       scores.append(("[CTRL_goroutine:1.0]", 1.0))
        default:         scores.append(("[TYPE_opaque:1.0]", 1.0))
        }

        // コンテンツベースタグ（キーワード検出）
        let lower = code.lowercased()
        if lower.contains("async") || lower.contains("await") || lower.contains("actor") {
            scores.append(("[CTRL_async:0.9]", 0.9))
        }
        if lower.contains("encrypt") || lower.contains("secret") || lower.contains("token") || lower.contains("key") {
            scores.append(("[SEC_hash:0.9]", 0.9))
        }
        if lower.contains("network") || lower.contains("http") || lower.contains("url") || lower.contains("socket") {
            scores.append(("[NET_ipc:0.8]", 0.8))
        }
        if lower.contains("database") || lower.contains("sql") || lower.contains("store") || lower.contains("cache") {
            scores.append(("[MEM_store:0.8]", 0.8))
        }
        if lower.contains("test") || lower.contains("spec") || lower.contains("assert") {
            scores.append(("[TEST_assert:0.8]", 0.8))
        }
        if lower.contains("view") || lower.contains("ui") || lower.contains("render") || lower.contains("layout") {
            scores.append(("[SCOPE_ui:0.7]", 0.7))
        }
        if lower.contains("parse") || lower.contains("decode") || lower.contains("encode") {
            scores.append(("[DATA_parse:0.7]", 0.7))
        }
        if lower.contains("error") || lower.contains("throw") || lower.contains("catch") {
            scores.append(("[CTRL_catch:0.7]", 0.7))
        }

        // 上位5つを返す
        let top = scores.prefix(5).map { $0.0 }.joined()
        return top.isEmpty ? "[码:1.0]" : top
    }

    // MARK: - Error

    enum L1TaggerError: Error, LocalizedError {
        case timeout
        case processError(String)
        case launchFailed(Error)

        var errorDescription: String? {
            switch self {
            case .timeout:             return "BitNet L1Tagger timed out (30s)"
            case .processError(let m): return "BitNet process error: \(m.prefix(200))"
            case .launchFailed(let e): return "BitNet launch failed: \(e.localizedDescription)"
            }
        }
    }
}

// MARK: - JCrossVault L1 Integration Extension

extension JCrossVault {
    /// ファイルの L1 タグを取得する（Vault から読み込み）。
    /// .l1tags ファイルが存在しない場合は nil を返す。
    func readL1Tags(relativePath: String) -> String? {
        guard let entry = vaultIndex?.entries[relativePath] else { return nil }
        let safeRelPath = relativePath.replacingOccurrences(of: "/", with: "∕")
        let l1URL = vaultRootURL.appendingPathComponent(safeRelPath + ".l1tags")
        return try? String(contentsOf: l1URL, encoding: .utf8)
    }
}
