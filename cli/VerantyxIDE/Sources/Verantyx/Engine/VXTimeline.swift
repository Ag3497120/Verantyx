import Foundation

// MARK: - VXTimeline
//
// Nano Cortex Protocol のタイムライン管理。
// コンセプト:「モデルは直近1タスクに集中する。記憶継続性はインフラが担う」
//
// 役割:
//   near/ に TURN_*.jcross として時系列を保存
//   直近 5 ターンを verbatim で保持（VX-Loop が注入）
//   50 ターン到達で 1 ノードに圧縮 → front/ に昇格
//   front/ が cap を超えると既存 GC が near → mid → deep へ押し出す
//
// ファイル命名規則:
//   near/TURN_{sessionId}_{turnNumber:04d}_{timestamp}.jcross
//   front/TLSUMMARY_{sessionId}_{generation}.jcross  ← 50ターン圧縮済みノード

final class VXTimeline {

    static let shared = VXTimeline()
    private init() {}

    // ── 設定 ───────────────────────────────────────────────────────────────
    static let verbatimWindow  = 5   // 直近 N ターンは verbatim 注入
    static let compressionAt   = 50  // このターン数で 1 ノードに圧縮

    // ── セッション別ターンカウンター（AgentLoop が複数回呼ばれても連番維持）──
    // ディスクスキャンなし: ファイル名にタイムスタンプが含まれるため一意性は保証済み
    // メインスレッドブロック防止のため同期ディスクI/Oを排除
    private var sessionTurnCounters: [String: Int] = [:]

    /// 次のターン番号を採番する（軽量・ノンブロッキング）
    /// ディスクスキャンを行わず、インメモリカウンターのみ使用する。
    /// ファイル名に {sessionId}_{turnNum}_{unixTimestamp} を含むため重複は発生しない。
    func nextTurnNumber(for sessionId: String) -> Int {
        // Swift の Dictionary アクセスはシングルスレッド前提（AgentLoop は async/await）
        // メインスレッドをブロックしないよう同期I/Oは行わない
        let next = (sessionTurnCounters[sessionId] ?? 0) + 1
        sessionTurnCounters[sessionId] = next
        return next
    }

    // ── ゾーンディレクトリ ─────────────────────────────────────────────────

    private func baseMemoryDir(workspaceRoot: URL?) -> URL {
        if let ws = workspaceRoot {
            return ws.appendingPathComponent(".openclaw/memory", isDirectory: true)
        }
        return URL(fileURLWithPath: "/tmp").appendingPathComponent(".openclaw/memory", isDirectory: true)
    }

    private func nearDir(workspaceRoot: URL?) -> URL {
        let dir = baseMemoryDir(workspaceRoot: workspaceRoot).appendingPathComponent("near", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    private func midDir(workspaceRoot: URL?) -> URL {
        let dir = baseMemoryDir(workspaceRoot: workspaceRoot).appendingPathComponent("mid", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    private func deepDir(workspaceRoot: URL?) -> URL {
        let dir = baseMemoryDir(workspaceRoot: workspaceRoot).appendingPathComponent("deep", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    private func frontDir(workspaceRoot: URL?) -> URL {
        let dir = baseMemoryDir(workspaceRoot: workspaceRoot).appendingPathComponent("front", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    // MARK: - ターンを記録

    /// 1 ターン（Q + A）を near/ に保存し、50ターン到達で圧縮する。
    /// - Parameters:
    ///   - sessionId: セッション識別子（8文字）
    ///   - turnNumber: このセッション内の通算ターン番号（1始まり）
    ///   - userInput: ユーザーの入力テキスト
    ///   - assistantOutput: モデルの応答テキスト
    ///   - searchResults: SearchGate が取得した記憶検索結果（あれば）
    @discardableResult
    func recordTurn(
        sessionId: String,
        turnNumber: Int,
        userInput: String,
        assistantOutput: String,
        searchResults: String = "",
        workspaceRoot: URL? = nil
    ) -> URL {
        let ts = Int(Date().timeIntervalSince1970)
        let fileName = "TURN_\(sessionId)_\(String(format: "%04d", turnNumber))_\(ts).jcross"
        let url = nearDir(workspaceRoot: workspaceRoot).appendingPathComponent(fileName)

        // ── L1: 1行サマリー ─────────────────────────────────────────────
        let userPreview = String(userInput.prefix(80)).replacingOccurrences(of: "\n", with: " ")
        let aPreview    = String(assistantOutput.prefix(80)).replacingOccurrences(of: "\n", with: " ")
        let l1 = "[Turn \(turnNumber)] U: \(userPreview) | A: \(aPreview)"

        // ── L2: OP.FACT ────────────────────────────────────────────────
        var l2Lines = [
            "OP.FACT(\"session_id\", \"\(sessionId)\")",
            "OP.FACT(\"turn_number\", \"\(turnNumber)\")",
            "OP.FACT(\"timestamp\", \"\(ts)\")",
            "OP.FACT(\"user_input\", \"\(String(userInput.prefix(200)).escaped)\")",
            "OP.FACT(\"assistant_output\", \"\(String(assistantOutput.prefix(200)).escaped)\")",
        ]
        if !searchResults.isEmpty {
            l2Lines.append("OP.FACT(\"search_injected\", \"\(String(searchResults.prefix(200)).escaped)\")")
        }
        // 使用履歴タグ（UsedAt: このターンがいつ・どの文脈で参照されたか）
        l2Lines.append("OP.STATE(\"used_at\", \"[]\")")  // SearchGate が更新する

        // ── L3: 逐語 ───────────────────────────────────────────────────
        let l3 = """
        User: \(userInput)

        Assistant: \(assistantOutput)
        \(searchResults.isEmpty ? "" : "\n--- Search Context ---\n\(searchResults)")
        """

        let content = buildJCross(
            prefix: "TURN",
            label: "Turn \(turnNumber) / \(sessionId)",
            l1: l1, l2: l2Lines.joined(separator: "\n"), l3: l3
        )

        try? content.write(to: url, atomically: true, encoding: .utf8)

        // 50 ターン到達チェック
        if turnNumber % Self.compressionAt == 0 {
            compressGeneration(sessionId: sessionId, upToTurn: turnNumber, workspaceRoot: workspaceRoot)
        }

        return url
    }

    // MARK: - 直近 N ターンを注入文字列として返す（system prompt 用）

    /// near/ から sessionId に属する最新 verbatimWindow ターンを取得し
    /// system prompt 注入用の文字列として返す。
    func buildTimelineInjection(sessionId: String, layer: JCrossLayer = .l2, workspaceRoot: URL? = nil) -> String {
        let turns = listTurns(sessionId: sessionId, topK: Self.verbatimWindow, workspaceRoot: workspaceRoot)
        guard !turns.isEmpty else { return "" }

        var parts: [String] = []
        for url in turns.reversed() {   // 古い順 → 新しい順で並べる
            guard let raw = try? String(contentsOf: url, encoding: .utf8) else { continue }
            let extracted: String
            switch layer {
            case .l1, .l1_5:
                extracted = extractSection(from: raw, tag: "L1_SUMMARY") ?? ""
            case .l2, .l3:
                // nano には L2、large には L3 を渡す
                let tag = (layer == .l3) ? "L3_VERBATIM" : "L2_FACTS"
                extracted = extractSection(from: raw, tag: tag) ?? ""
            }
            if !extracted.isEmpty {
                let name = url.deletingPathExtension().lastPathComponent
                parts.append("【\(name)】\n\(String(extracted.prefix(600)))")
            }
        }

        guard !parts.isEmpty else { return "" }

        return """

        [VX TIMELINE — 直近\(parts.count)ターン (session: \(sessionId))]
        \(parts.joined(separator: "\n---\n"))
        [/VX TIMELINE]
        """
    }

    // MARK: - 直近 N ターンを conversation 注入用文字列配列として返す

    /// AgentLoop の conversation 配列に直接挿入するための形式で返す。
    /// useL1Only=true (nano): L1_SUMMARY（短いファクト）で 2048 トークン制限を節約
    /// useL1Only=false (large): L3_VERBATIM（逐語）で詳細を保持
    func buildTimelineAsMessages(sessionId: String, topK: Int, useL1Only: Bool = false, workspaceRoot: URL? = nil) -> [String] {
        let turns = listTurns(sessionId: sessionId, topK: topK, workspaceRoot: workspaceRoot)
        guard !turns.isEmpty else { return [] }

        var lines: [String] = []
        for url in turns.reversed() {
            guard let raw = try? String(contentsOf: url, encoding: .utf8) else { continue }
            let extracted: String
            if useL1Only {
                if let l1 = extractSection(from: raw, tag: "L1_SUMMARY") {
                    extracted = l1.trimmingCharacters(in: .whitespacesAndNewlines)
                } else if let l3 = extractSection(from: raw, tag: "L3_VERBATIM") {
                    extracted = String(l3.prefix(200)).trimmingCharacters(in: .whitespacesAndNewlines)
                } else { continue }
            } else {
                guard let l3 = extractSection(from: raw, tag: "L3_VERBATIM") else { continue }
                extracted = String(l3.prefix(600)).trimmingCharacters(in: .whitespacesAndNewlines)
            }
            if !extracted.isEmpty { lines.append(extracted) }
        }
        return lines
    }

    // MARK: - 使用履歴タグ更新（SearchGate が呼ぶ）

    /// 指定ノードの OP.STATE("used_at") に新しい参照ログを追記する。
    /// - Parameters:
    ///   - fileURL: 更新対象の .jcross ファイル
    ///   - turnNumber: 参照したターン番号
    ///   - context: 参照された文脈（質問のキーワードなど）
    func appendUsedAt(fileURL: URL, turnNumber: Int, context: String) {
        guard var raw = try? String(contentsOf: fileURL, encoding: .utf8) else { return }
        let entry = "{turn:\(turnNumber),ctx:\"\(String(context.prefix(60)).escaped)\"}"
        // OP.STATE("used_at", "[...]") の中身を更新
        let pattern = #"OP\.STATE\("used_at",\s*"\[(.*?)\]"\)"#
        if let regex = try? NSRegularExpression(pattern: pattern, options: .dotMatchesLineSeparators),
           let match = regex.firstMatch(in: raw, range: NSRange(raw.startIndex..., in: raw)),
           let range = Range(match.range(at: 1), in: raw) {
            let existing = String(raw[range])
            let updated  = existing.isEmpty ? entry : "\(existing),\(entry)"
            raw = raw.replacingCharacters(
                in: Range(match.range, in: raw)!,
                with: "OP.STATE(\"used_at\", \"[\(updated)]\")"
            )
        }
        try? raw.write(to: fileURL, atomically: true, encoding: .utf8)
    }

    // MARK: - 50ターン圧縮 → front/ に昇格

    /// sessionId の最新 compressionAt ターン分を 1 ノードに圧縮して front/ に書き込む。
    private func compressGeneration(sessionId: String, upToTurn: Int, workspaceRoot: URL? = nil) {
        let generation = upToTurn / Self.compressionAt
        let turns = listTurns(sessionId: sessionId, topK: Self.compressionAt, workspaceRoot: workspaceRoot)
        guard !turns.isEmpty else { return }

        // L1 サマリー（先頭と末尾のターンから）
        let firstRaw = (try? String(contentsOf: turns.first!, encoding: .utf8)) ?? ""
        let lastRaw  = (try? String(contentsOf: turns.last!,  encoding: .utf8)) ?? ""
        let firstL1  = extractSection(from: firstRaw, tag: "L1_SUMMARY") ?? ""
        let lastL1   = extractSection(from: lastRaw,  tag: "L1_SUMMARY") ?? ""
        let l1 = "[Session \(sessionId) Gen.\(generation)] \(turns.count)ターン圧縮 | 最初: \(String(firstL1.prefix(60))) | 最後: \(String(lastL1.prefix(60)))"

        // L2 ファクト（各ターンの user_input を集約）
        var allFacts: [String] = [
            "OP.FACT(\"session_id\", \"\(sessionId)\")",
            "OP.FACT(\"generation\", \"\(generation)\")",
            "OP.FACT(\"compressed_turns\", \"\(turns.count)\")",
            "OP.FACT(\"turn_range\", \"\(upToTurn - turns.count + 1)-\(upToTurn)\")",
        ]
        for (i, url) in turns.prefix(5).enumerated() {
            guard let raw = try? String(contentsOf: url, encoding: .utf8) else { continue }
            if let l2 = extractSection(from: raw, tag: "L2_FACTS"),
               let userLine = l2.components(separatedBy: "\n")
                   .first(where: { $0.contains("\"user_input\"") }) {
                allFacts.append("OP.FACT(\"turn_\(i)_user\", \(userLine.components(separatedBy: ", ").last ?? ""))")
            }
        }
        // 圧縮世代タグ（GCの落下優先度に使用）
        allFacts.append("OP.FACT(\"compressed_at\", \"\(ISO8601DateFormatter().string(from: Date()))\")")
        allFacts.append("OP.STATE(\"node_type\", \"TIMELINE_SUMMARY\")")

        // L3 ダイジェスト（各ターンのL1を並べる）
        let l3 = turns.compactMap { url -> String? in
            guard let raw = try? String(contentsOf: url, encoding: .utf8) else { return nil }
            return extractSection(from: raw, tag: "L1_SUMMARY")
        }.joined(separator: "\n")

        // front/ に TLSUMMARY_*.jcross として書き込む
        let ts       = Int(Date().timeIntervalSince1970)
        let fileName = "TLSUMMARY_\(sessionId)_gen\(generation)_\(ts).jcross"
        let content  = buildJCross(
            prefix: "TLSUMMARY",
            label: "Timeline Summary Gen.\(generation) / \(sessionId)",
            l1: l1,
            l2: allFacts.joined(separator: "\n"),
            l3: l3
        )
        let destURL = frontDir(workspaceRoot: workspaceRoot).appendingPathComponent(fileName)
        try? content.write(to: destURL, atomically: true, encoding: .utf8)
    }

    // MARK: - ヘルパー

    /// near/ + mid/ + deep/ から sessionId に属する TURN_* ファイルを新しい順で topK 件返す
    /// GC により near/ から追い出されたターンも確実に取得する
    private func listTurns(sessionId: String, topK: Int, workspaceRoot: URL? = nil) -> [URL] {
        let fm = FileManager.default
        // 全ゾーンを検索（GCで追い出されたファイルも拾う）
        let searchDirs = [nearDir(workspaceRoot: workspaceRoot), midDir(workspaceRoot: workspaceRoot), deepDir(workspaceRoot: workspaceRoot)]
        var allFiles: [URL] = []
        for dir in searchDirs {
            let files = (try? fm.contentsOfDirectory(
                at: dir,
                includingPropertiesForKeys: nil
            )) ?? []
            let matched = files.filter {
                $0.pathExtension == "jcross"
                && $0.lastPathComponent.hasPrefix("TURN_\(sessionId)_")
                && !$0.lastPathComponent.hasPrefix("JCROSS_TOMB")
            }
            allFiles.append(contentsOf: matched)
        }
        // ターン番号で降順ソート（タイムスタンプより確実）
        return allFiles
            .sorted { a, b in
                // TURN_{sessionId}_{turnNum}_{ts}.jcross
                let partsA = a.deletingPathExtension().lastPathComponent.components(separatedBy: "_")
                let partsB = b.deletingPathExtension().lastPathComponent.components(separatedBy: "_")
                let numA = partsA.count >= 3 ? (Int(partsA[2]) ?? 0) : 0
                let numB = partsB.count >= 3 ? (Int(partsB[2]) ?? 0) : 0
                return numA > numB
            }
            .prefix(topK)
            .map { $0 }
    }

    private func buildJCross(prefix: String, label: String, l1: String, l2: String, l3: String) -> String {
        let ts = ISO8601DateFormatter().string(from: Date())
        return """
        ;;; JCross Memory Node — \(prefix)
        ;;; Session: \(label)
        ;;; Created: \(ts)
        ;;; Archived: \(ts)

        [L1_SUMMARY]
        \(l1)
        [/L1_SUMMARY]

        [L2_FACTS]
        \(l2)
        [/L2_FACTS]

        [L3_VERBATIM]
        \(l3)
        [/L3_VERBATIM]
        """
    }

    private func extractSection(from raw: String, tag: String) -> String? {
        let open  = "[\(tag)]"
        let close = "[/\(tag)]"
        guard let start = raw.range(of: open),
              let end   = raw.range(of: close),
              start.upperBound < end.lowerBound
        else { return nil }
        return String(raw[start.upperBound..<end.lowerBound])
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

// MARK: - String extension

private extension String {
    var escaped: String {
        replacingOccurrences(of: "\"", with: "'")
            .replacingOccurrences(of: "\n", with: "\\n")
    }
}
