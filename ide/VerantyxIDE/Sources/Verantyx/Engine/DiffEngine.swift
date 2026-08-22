import Foundation

// MARK: - DiffEngine
// Computes line-level diff between two strings using longest common subsequence.
// Pure Swift, zero dependencies.

enum DiffEngine {

    // MARK: - Public API

    static func compute(original: String, modified: String) -> [DiffHunk] {
        let origLines = original.components(separatedBy: "\n")
        let modLines  = modified.components(separatedBy: "\n")

        let editScript = lcs(origLines, modLines)
        return groupIntoHunks(editScript, contextLines: 3)
    }

    // MARK: - LCS-based edit script

    private enum Edit {
        case keep(String)
        case insert(String)
        case delete(String)
    }

    private static func lcs(_ a: [String], _ b: [String]) -> [Edit] {
        let m = a.count, n = b.count
        // dp[i][j] = LCS length of a[0..<i] and b[0..<j]
        var dp = Array(repeating: Array(repeating: 0, count: n + 1), count: m + 1)
        for i in 1...m {
            for j in 1...n {
                if a[i-1] == b[j-1] {
                    dp[i][j] = dp[i-1][j-1] + 1
                } else {
                    dp[i][j] = max(dp[i-1][j], dp[i][j-1])
                }
            }
        }

        // Backtrack
        var edits: [Edit] = []
        var i = m, j = n
        while i > 0 || j > 0 {
            if i > 0 && j > 0 && a[i-1] == b[j-1] {
                edits.append(.keep(a[i-1]))
                i -= 1; j -= 1
            } else if j > 0 && (i == 0 || dp[i][j-1] >= dp[i-1][j]) {
                edits.append(.insert(b[j-1]))
                j -= 1
            } else {
                edits.append(.delete(a[i-1]))
                i -= 1
            }
        }
        return edits.reversed()
    }

    // MARK: - Group into hunks with context

    private static func groupIntoHunks(_ edits: [Edit], contextLines: Int) -> [DiffHunk] {
        // Convert edits to DiffLines
        let lines: [DiffLine] = edits.map { edit in
            switch edit {
            case .keep(let t):   return DiffLine(kind: .context, text: t)
            case .insert(let t): return DiffLine(kind: .added,   text: t)
            case .delete(let t): return DiffLine(kind: .removed,  text: t)
            }
        }

        // Find changed line indices
        let changedIndices = lines.indices.filter { lines[$0].kind != .context }
        guard !changedIndices.isEmpty else { return [] }

        // Build hunk ranges
        var hunks: [DiffHunk] = []
        var ranges: [ClosedRange<Int>] = []

        for idx in changedIndices {
            let lo = max(0, idx - contextLines)
            let hi = min(lines.count - 1, idx + contextLines)
            if let last = ranges.last, lo <= last.upperBound + 1 {
                ranges[ranges.count - 1] = last.lowerBound...hi
            } else {
                ranges.append(lo...hi)
            }
        }

        for range in ranges {
            let hunkLines = Array(lines[range])
            hunks.append(DiffHunk(lines: hunkLines))
        }
        return hunks
    }
}

// MARK: - Stats helper

extension FileDiff {
    var addedCount:   Int { hunks.flatMap(\.lines).filter { $0.kind == .added   }.count }
    var removedCount: Int { hunks.flatMap(\.lines).filter { $0.kind == .removed }.count }
}
