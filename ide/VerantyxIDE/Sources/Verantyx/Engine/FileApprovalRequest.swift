import Foundation

// MARK: - FileApprovalRequest
// Human Mode gate — suspends AgentLoop via CheckedContinuation until the user
// taps "承認" or "拒否" in the approval sheet.
//
// Usage (AgentLoop):
//   let req = FileApprovalRequest(fileURL: url, newContent: content, ...)
//   await onProgress(.fileApprovalRequest(req))   // UI receives and shows sheet
//   let approved = await req.waitForDecision()     // suspends here
//   if approved { /* write */ } else { /* skip */ }

final class FileApprovalRequest: Identifiable, @unchecked Sendable {

    // MARK: - Operation kind

    enum WriteKind {
        case createNew                          // file doesn't exist yet
        case overwrite                          // full file overwrite
        case editLines(start: Int, end: Int)    // partial line range replacement
        case makeDirectory                      // mkdir
        case applyPatch                         // APPLY_PATCH (full rewrite)
    }

    // MARK: - Properties

    let id = UUID()
    let fileURL: URL
    let newContent: String
    let originalContent: String   // "" for new files / directories
    let kind: WriteKind

    private var continuation: CheckedContinuation<Bool, Never>?

    // MARK: - Init

    init(fileURL: URL, newContent: String, originalContent: String, kind: WriteKind) {
        self.fileURL = fileURL
        self.newContent = newContent
        self.originalContent = originalContent
        self.kind = kind
    }

    // MARK: - Derived display info

    var isNewFile: Bool {
        switch kind {
        case .createNew, .makeDirectory: return true
        case .applyPatch: return originalContent.isEmpty
        default: return false
        }
    }

    var displayTitle: String {
        switch kind {
        case .createNew:                 return "新しいファイルを作成"
        case .overwrite:                 return "ファイルを上書き保存"
        case .editLines(let s, let e):   return "行 \(s)〜\(e) を編集"
        case .makeDirectory:             return "ディレクトリを作成"
        case .applyPatch:                return "パッチを適用"
        }
    }

    var displayFileName: String { fileURL.lastPathComponent }

    /// Relative path starting at the last 3 path components for readable display.
    var shortPath: String {
        let comps = fileURL.pathComponents
        let take = min(3, comps.count)
        return comps.suffix(take).joined(separator: "/")
    }

    // MARK: - Suspension / resumption

    /// Called by AppState when user taps "承認".
    func approve() {
        continuation?.resume(returning: true)
        continuation = nil
    }

    /// Called by AppState when user taps "拒否".
    func reject() {
        continuation?.resume(returning: false)
        continuation = nil
    }

    /// Suspends AgentLoop until the user makes a decision.
    func waitForDecision() async -> Bool {
        await withCheckedContinuation { cont in
            self.continuation = cont
        }
    }
}
