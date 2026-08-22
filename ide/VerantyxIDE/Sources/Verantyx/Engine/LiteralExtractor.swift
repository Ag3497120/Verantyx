import Foundation

// MARK: - JCross Literal Extractor  (Production v2)
//
// ソースコードからリテラル値を「意味を理解して」抽出するモジュール。
//
// 設計原則:
//   1. コンテキスト認識 — 文字列リテラルの"内側"にある数値は検出しない
//   2. 言語対応 — Swift / Python / TypeScript / Rust / Go に対応
//   3. エッジケース完全対応:
//      - 負数 (-1.21)
//      - 科学的記数法 (1.21e-5, 3.14E+10)
//      - 16進数 (0xFF, 0xDEADBEEF)
//      - 8進数 (0o777)
//      - 2進数 (0b1010_1111)
//      - 数値区切り (1_000_000 → Swift/Rust)
//      - 複数行文字列 (""" ... """ → Swift, ''' ... ''' → Python)
//   4. 除外ルール — ループカウンタ相当 (0, 1, -1) はデフォルト除外
//   5. パフォーマンス — O(N) スキャン、バックトラックなし

// MARK: - Found Literal

struct FoundLiteral {
    let value: String           // 生の値 (引用符・負号を含む)
    let cleanValue: String      // 正規化された値 (Vaultに保存する値)
    let range: Range<String.Index>
    let category: LiteralCategory
    let lineNumber: Int
}

// MARK: - Language Hint

enum LiteralLanguageHint {
    case swift
    case python
    case typescript
    case javascript
    case rust
    case go
    case kotlin
    case java
    case generic

    var supportsTripleQuote: Bool {
        switch self { case .swift, .python, .kotlin: return true; default: return false }
    }
    var usesHashComment: Bool {
        switch self { case .python: return true; default: return false }
    }
}

// MARK: - Scanner State

private enum ScanState {
    case normal
    case lineComment
    case blockComment
    case stringSingle         // '...'
    case stringDouble         // "..."
    case stringTripleDouble   // """..."""
    case stringTripleSingle   // '''...'''
    case stringRaw            // Swift #"..."# or Rust r"..."
}

// MARK: - LiteralExtractor

enum LiteralExtractor {

    // MARK: - Public API

    /// ソースコード全体からリテラルを抽出する（コンテキスト認識スキャン）。
    ///
    /// - Parameters:
    ///   - source: 対象ソースコード全文
    ///   - language: 言語ヒント（文字列リテラル方式の判定に使用）
    ///   - excludeZeroOne: true の場合、0/1/-1 を除外（デフォルト true）
    ///   - minSensitivity: この感度以上のみ返す（デフォルト 1）
    /// - Returns: 検出されたリテラルのリスト（位置順）
    static func extract(
        from source: String,
        language: LiteralLanguageHint = .generic,
        excludeZeroOne: Bool = true,
        minSensitivity: Int = 1
    ) -> [FoundLiteral] {
        var results: [FoundLiteral] = []

        // Phase 1: コンテキスト認識スキャンで「安全な範囲」を特定
        let safeRanges = identifySafeRanges(in: source, language: language)

        // Phase 2: 安全な範囲内でのみリテラルを検出
        for safeRange in safeRanges {
            let substring = String(source[safeRange.range])
            let lineBase = safeRange.startLine

            let found = extractLiterals(
                from: substring,
                baseRange: safeRange.range,
                baseLineNumber: lineBase,
                language: language,
                excludeZeroOne: excludeZeroOne,
                source: source
            )
            results.append(contentsOf: found)
        }

        // Phase 3: 感度フィルタリング
        return results
            .filter { $0.category.sensitivityScore >= minSensitivity }
            .sorted { $0.range.lowerBound < $1.range.lowerBound }
    }

    /// 単一行からリテラルを抽出する（後方互換 API）。
    static func extractFromLine(
        _ line: String,
        lineNumber: Int = 0,
        language: LiteralLanguageHint = .generic,
        excludeZeroOne: Bool = true
    ) -> [FoundLiteral] {
        extract(from: line, language: language, excludeZeroOne: excludeZeroOne)
            .map { lit in
                FoundLiteral(
                    value: lit.value,
                    cleanValue: lit.cleanValue,
                    range: lit.range,
                    category: lit.category,
                    lineNumber: lineNumber
                )
            }
    }

    // MARK: - Phase 1: Safe Range Identification
    // コンテキストスキャンで「コード（非コメント・非文字列）」の範囲を列挙する

    private struct SafeRange {
        let range: Range<String.Index>
        let startLine: Int
    }

    private static func identifySafeRanges(
        in source: String,
        language: LiteralLanguageHint
    ) -> [SafeRange] {
        var ranges: [SafeRange] = []
        var state: ScanState = .normal
        var i = source.startIndex
        var segmentStart = i
        var lineNumber = 0
        var segmentStartLine = 0

        func commitSegment(end: String.Index) {
            if segmentStart < end {
                ranges.append(SafeRange(range: segmentStart..<end, startLine: segmentStartLine))
            }
        }

        while i < source.endIndex {
            let ch = source[i]
            let next = source.index(after: i)
            let peek: Character? = next < source.endIndex ? source[next] : nil

            switch state {
            case .normal:
                if ch == "\n" { lineNumber += 1 }

                // ブロックコメント開始 /* (C系)
                if ch == "/" && peek == "*" {
                    commitSegment(end: i)
                    state = .blockComment
                    i = source.index(i, offsetBy: 2, limitedBy: source.endIndex) ?? source.endIndex
                    continue

                // 行コメント開始 // (C系)
                } else if ch == "/" && peek == "/" {
                    commitSegment(end: i)
                    state = .lineComment
                    i = source.index(i, offsetBy: 2, limitedBy: source.endIndex) ?? source.endIndex
                    continue

                // 行コメント開始 # (Python)
                } else if ch == "#" && language.usesHashComment {
                    commitSegment(end: i)
                    state = .lineComment
                    i = next
                    continue

                // トリプルクォート文字列 """  (Swift, Python, Kotlin)
                } else if ch == "\"" && peek == "\"",
                          language.supportsTripleQuote,
                          next < source.endIndex {
                    let next2 = source.index(after: next)
                    if next2 < source.endIndex && source[next2] == "\"" {
                        commitSegment(end: i)
                        state = .stringTripleDouble
                        i = source.index(i, offsetBy: 3, limitedBy: source.endIndex) ?? source.endIndex
                        continue
                    }
                }

                // トリプルシングルクォート ''' (Python)
                if ch == "'" && peek == "'",
                   language == .python {
                    let next2Idx = source.index(after: next)
                    if next2Idx < source.endIndex && source[next2Idx] == "'" {
                        commitSegment(end: i)
                        state = .stringTripleSingle
                        i = source.index(i, offsetBy: 3, limitedBy: source.endIndex) ?? source.endIndex
                        continue
                    }
                }

                // 通常ダブルクォート文字列
                if ch == "\"" {
                    commitSegment(end: i)
                    state = .stringDouble
                    i = next
                    continue
                }

                // 通常シングルクォート文字列 (Python, JS/TS)
                if ch == "'" && (language == .python || language == .typescript || language == .javascript) {
                    commitSegment(end: i)
                    state = .stringSingle
                    i = next
                    continue
                }

                segmentStartLine = lineNumber

            case .lineComment:
                if ch == "\n" {
                    lineNumber += 1
                    state = .normal
                    segmentStart = next
                    segmentStartLine = lineNumber
                }

            case .blockComment:
                if ch == "\n" { lineNumber += 1 }
                if ch == "*" && peek == "/" {
                    state = .normal
                    let afterClose = source.index(i, offsetBy: 2, limitedBy: source.endIndex) ?? source.endIndex
                    segmentStart = afterClose
                    segmentStartLine = lineNumber
                    i = afterClose
                    continue
                }

            case .stringDouble:
                if ch == "\\" { // エスケープ → 次の文字スキップ
                    if next < source.endIndex { i = source.index(after: next) }
                    continue
                }
                if ch == "\n" { lineNumber += 1 }
                if ch == "\"" {
                    state = .normal
                    segmentStart = next
                    segmentStartLine = lineNumber
                }

            case .stringSingle:
                if ch == "\\" {
                    if next < source.endIndex { i = source.index(after: next) }
                    continue
                }
                if ch == "\n" { lineNumber += 1 }
                if ch == "'" {
                    state = .normal
                    segmentStart = next
                    segmentStartLine = lineNumber
                }

            case .stringTripleDouble:
                if ch == "\n" { lineNumber += 1 }
                if ch == "\"" && peek == "\"" {
                    let next2Idx = source.index(after: next)
                    if next2Idx < source.endIndex && source[next2Idx] == "\"" {
                        state = .normal
                        let afterClose = source.index(i, offsetBy: 3, limitedBy: source.endIndex) ?? source.endIndex
                        segmentStart = afterClose
                        segmentStartLine = lineNumber
                        i = afterClose
                        continue
                    }
                }

            case .stringTripleSingle:
                if ch == "\n" { lineNumber += 1 }
                if ch == "'" && peek == "'" {
                    let next2Idx = source.index(after: next)
                    if next2Idx < source.endIndex && source[next2Idx] == "'" {
                        state = .normal
                        let afterClose = source.index(i, offsetBy: 3, limitedBy: source.endIndex) ?? source.endIndex
                        segmentStart = afterClose
                        segmentStartLine = lineNumber
                        i = afterClose
                        continue
                    }
                }

            case .stringRaw:
                break
            }

            i = next
        }

        // 最後のセグメントをコミット
        if state == .normal { commitSegment(end: source.endIndex) }

        return ranges
    }

    // MARK: - Phase 2: Literal Detection within Safe Range

    private static func extractLiterals(
        from substring: String,
        baseRange: Range<String.Index>,
        baseLineNumber: Int,
        language: LiteralLanguageHint,
        excludeZeroOne: Bool,
        source: String
    ) -> [FoundLiteral] {
        var results: [FoundLiteral] = []

        // ── 数値リテラル ────────────────────────────────────────────────
        // 優先順位: 科学的記数法 > 16進 > 2進 > 8進 > 小数 > 負の整数 > 整数
        let numericPatterns: [(pattern: String, priority: Int)] = [
            // 科学的記数法: 1.21e-5, 3.14E+10
            (#"(?<![.\w])-?\d+\.?\d*[eE][+-]?\d+"#, 6),
            // 16進数: 0xFF, 0xDEAD_BEEF
            (#"\b0[xX][0-9A-Fa-f][0-9A-Fa-f_]*\b"#, 5),
            // 2進数: 0b1010_1111
            (#"\b0[bB][01][01_]*\b"#, 4),
            // 8進数: 0o777
            (#"\b0[oO][0-7][0-7_]*\b"#, 3),
            // 小数点付き浮動小数点 (負数含む): -1.21, 0.05, 1_234.56
            (#"(?<![.\w])-?(?:0|[1-9][0-9_]*)\.[0-9][0-9_]*\b"#, 2),
            // 負の整数: -42, -1000
            (#"(?<![.\w])-[1-9][0-9_]*\b"#, 1),
            // 正の整数 (0, 1 は後で除外): \b[0-9][0-9_]*\b
            (#"\b[0-9][0-9_]*\b"#, 0),
        ]

        var coveredRanges: [Range<String.Index>] = []

        for (pattern, _) in numericPatterns {
            guard let regex = try? NSRegularExpression(pattern: pattern) else { continue }
            let ns = substring as NSString
            let matches = regex.matches(in: substring, range: NSRange(location: 0, length: ns.length))

            for match in matches {
                guard let matchRange = Range(match.range, in: substring) else { continue }

                // 既に別パターンで捕捉済みの範囲とオーバーラップしているか確認
                let alreadyCovered = coveredRanges.contains { covered in
                    matchRange.overlaps(covered)
                }
                if alreadyCovered { continue }

                let rawValue = String(substring[matchRange])
                let cleanValue = rawValue.replacingOccurrences(of: "_", with: "") // 区切り文字を除去
                let category = categorizeNumeric(cleanValue)

                // 除外判定: 0, 1, -1
                if excludeZeroOne {
                    let d = Double(cleanValue)
                    if d == 0 || d == 1 || d == -1 { continue }
                }

                // 元のソース文字列における絶対位置を計算
                let absoluteRange = offsetRange(matchRange, in: substring, base: baseRange, source: source)

                coveredRanges.append(matchRange)
                results.append(FoundLiteral(
                    value: rawValue,
                    cleanValue: cleanValue,
                    range: absoluteRange,
                    category: category,
                    lineNumber: baseLineNumber + countNewlines(before: matchRange.lowerBound, in: substring)
                ))
            }
        }

        return results
    }

    // MARK: - Category Classification

    private static func categorizeNumeric(_ cleanValue: String) -> LiteralCategory {
        if cleanValue.hasPrefix("0x") || cleanValue.hasPrefix("0X") { return .numericHex }
        if cleanValue.hasPrefix("0b") || cleanValue.hasPrefix("0B") { return .numericBinary }
        if cleanValue.hasPrefix("0o") || cleanValue.hasPrefix("0O") { return .numericOctal }
        if cleanValue.lowercased().contains("e") { return .numericScientific }
        if cleanValue.hasPrefix("-") {
            if cleanValue.contains(".") { return .numericDecimal }
            return .numericNegative
        }
        if cleanValue.contains(".") { return .numericDecimal }
        let d = Double(cleanValue) ?? 0
        if d == 0 || d == 1 { return .numericZeroOne }
        if d < 100 { return .numericSmall }
        return .numericLarge
    }

    // MARK: - Helpers

    /// substring内のoffsetを元のソース文字列のインデックスに変換
    private static func offsetRange(
        _ range: Range<String.Index>,
        in substring: String,
        base: Range<String.Index>,
        source: String
    ) -> Range<String.Index> {
        // substring は source の base.lowerBound から始まるスライスではなく独立コピーなので
        // UTF-16オフセットで計算する
        let startOffset = substring.utf16.distance(from: substring.startIndex, to: range.lowerBound)
        let endOffset   = substring.utf16.distance(from: substring.startIndex, to: range.upperBound)

        // base.lowerBound を起点としたオフセット
        let sourceStart = base.lowerBound
        guard let absStart = source.utf16.index(sourceStart, offsetBy: startOffset, limitedBy: source.utf16.endIndex),
              let absEnd   = source.utf16.index(sourceStart, offsetBy: endOffset,   limitedBy: source.utf16.endIndex)
        else { return base.lowerBound..<base.lowerBound }

        // UTF-16インデックスをString.Indexに変換 (Swift 5ではIndexは共通)
        let si = absStart
        let ei = absEnd
        return si..<ei
    }

    private static func countNewlines(before index: String.Index, in str: String) -> Int {
        str[str.startIndex..<index].filter { $0 == "\n" }.count
    }
}

// MARK: - LiteralCategory ← sensitivityScore は JCrossZAxisVault.swift で定義済み
// (同一モジュールで共有するため再宣言なし)
