import Foundation

/// Emits structured events to stdout and optionally a JSONL trace file.
///
/// TODO(gui): Verantyx IDE should eventually subscribe to the same sink
/// (or replay JSONL) for thin visualization — without owning inference state.
public final class VeraEventSink: @unchecked Sendable {
    public let missionId: String
    public private(set) var events: [VeraRuntimeEvent] = []

    private let jsonEncoder: JSONEncoder
    private let fileHandle: FileHandle?
    private let writeStdout: Bool
    private let lock = NSLock()

    public init(missionId: String, traceURL: URL? = nil, writeStdout: Bool = true) throws {
        self.missionId = missionId
        self.writeStdout = writeStdout
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        self.jsonEncoder = encoder

        if let traceURL {
            let dir = traceURL.deletingLastPathComponent()
            try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            if !FileManager.default.fileExists(atPath: traceURL.path) {
                FileManager.default.createFile(atPath: traceURL.path, contents: nil)
            }
            self.fileHandle = try FileHandle(forWritingTo: traceURL)
            try self.fileHandle?.seekToEnd()
        } else {
            self.fileHandle = nil
        }
    }

    deinit {
        try? fileHandle?.close()
    }

    @discardableResult
    public func emit(
        _ kind: VeraEventKind,
        summary: String,
        turn: Int? = nil,
        detail: [String: String] = [:],
        tags: [String] = []
    ) -> VeraRuntimeEvent {
        let event = VeraRuntimeEvent(
            kind: kind,
            missionId: missionId,
            summary: summary,
            turn: turn,
            detail: detail,
            tags: tags
        )
        lock.lock()
        events.append(event)
        lock.unlock()

        if writeStdout {
            FileHandle.standardOutput.write(Data((event.cliLine + "\n").utf8))
        }
        if let fileHandle, let data = try? jsonEncoder.encode(event) {
            fileHandle.write(data)
            fileHandle.write(Data("\n".utf8))
        }
        return event
    }

    public func close() {
        try? fileHandle?.synchronize()
        try? fileHandle?.close()
    }
}
