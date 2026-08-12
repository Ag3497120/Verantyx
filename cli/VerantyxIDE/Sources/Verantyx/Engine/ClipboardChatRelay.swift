import Foundation
import Cocoa

// MARK: - Chatting from the phone, over the clipboard
//
// While the agent drives the Mac it needs the screen, and the IDE window ends
// up buried under whatever it is operating. The chat becomes unreachable
// exactly when you most want to watch it.
//
// So move the conversation to the phone without moving the text off the
// devices. Universal Clipboard already carries the clipboard between a Mac and
// an iPhone on the same Apple ID — end-to-end encrypted, over Apple's own
// Continuity channel. Nothing here contacts a server: the relay writes to the
// local pasteboard and reads from the local pasteboard, and Continuity does
// the rest. Apple Notes (or any editor on the phone) is the window.
//
// The protocol is one bit: did the user paste?
//
//   Mac writes chunk 1  →  you paste it in Notes  →  Mac writes chunk 2  →  …
//   …  you type a reply and copy it  →  Mac picks it up as your message.
//
// Detecting a paste is the whole trick. macOS has no "someone pasted"
// notification, but a pasteboard item can be written *lazily*: the data is not
// produced until a reader asks for it, and asking is what pasting does. That
// callback is the paste signal. Verified: it does not fire on write, fires on
// the first read, and does not fire again afterwards — one paste, one advance.
@MainActor
final class ClipboardChatRelay: ObservableObject {

    static let shared = ClipboardChatRelay()

    // MARK: State

    enum Mode: String { case off, waitingForPaste, waitingForReply }

    @Published private(set) var mode: Mode = .off
    @Published private(set) var chunks: [String] = []
    @Published private(set) var cursor: Int = 0
    @Published private(set) var lastEvent: String = ""

    /// Set when the pasteboard resolves lazy data immediately on copy rather
    /// than on paste. Handoff may pre-fetch to have the content ready on the
    /// other device, which would fire the provider with no user involved. When
    /// that is observed once, the paste signal is not trustworthy on this Mac
    /// and the relay falls back to advancing on the reply instead.
    @Published private(set) var eagerPasteboard = false

    var isRunning: Bool { mode != .off }
    var progressLabel: String {
        chunks.isEmpty ? "" : "\(min(cursor + 1, chunks.count))/\(chunks.count)"
    }

    /// Delivered to the chat as if typed. Set by whoever starts the relay.
    var onUserMessage: ((String) -> Void)?

    // MARK: Internals

    /// Marks our own chunks so a chunk copied back is never mistaken for the
    /// user's reply — on the phone, "select all, copy" is one slip away.
    private static let marker = "〔Vera"

    private var poll: Timer?
    private var lastChangeCount: Int = 0
    private var writtenAt: Date = .distantPast

    /// Chunk size. Small enough that a paste into Notes stays readable, large
    /// enough that an ordinary reply is one or two pastes.
    private let chunkLimit = 1600

    // MARK: - Lifecycle

    func start() {
        guard mode == .off else { return }
        lastChangeCount = NSPasteboard.general.changeCount
        mode = .waitingForReply
        lastEvent = "待機中 — iPhone のメモから送ってください"
        poll = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated { self?.tick() }
        }
    }

    func stop() {
        poll?.invalidate()
        poll = nil
        mode = .off
        chunks = []
        cursor = 0
        lastEvent = ""
    }

    // MARK: - Outbound: the agent's reply becomes pasteable chunks

    func send(_ reply: String) {
        guard isRunning else { return }
        let body = reply.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !body.isEmpty else { return }
        chunks = Self.split(body, limit: chunkLimit)
        cursor = 0
        writeCurrentChunk()
    }

    /// Manual advance, for when the paste signal cannot be trusted (see
    /// `eagerPasteboard`) or a paste did not land.
    func advance() {
        guard isRunning, cursor + 1 < chunks.count else { return }
        cursor += 1
        writeCurrentChunk()
    }

    private func writeCurrentChunk() {
        guard cursor < chunks.count else {
            mode = .waitingForReply
            lastEvent = "全て送信しました — 返信をコピーしてください"
            return
        }

        let header = "\(Self.marker) \(cursor + 1)/\(chunks.count)〕"
        let payload = header + "\n" + chunks[cursor]

        let pb = NSPasteboard.general
        pb.clearContents()

        if eagerPasteboard {
            // The lazy path is useless here; write plainly and let the reply
            // (or the Next button) drive the advance.
            pb.setString(payload, forType: .string)
        } else {
            let item = NSPasteboardItem()
            item.setDataProvider(LazyChunk(payload: payload) { [weak self] in
                MainActor.assumeIsolated { self?.pasteObserved() }
            }, forTypes: [.string])
            pb.writeObjects([item])
        }

        writtenAt = Date()
        lastChangeCount = pb.changeCount
        mode = .waitingForPaste
        lastEvent = "\(progressLabel) をクリップボードへ — メモに貼り付けてください"
    }

    /// The pasteboard handed our data to someone. That is a paste.
    private func pasteObserved() {
        // Handoff pre-fetching would fire this within a moment of the copy,
        // with no human in between. Treat a near-instant read as the system
        // staging the content, not as the user pasting, and stop trusting the
        // signal on this machine.
        if Date().timeIntervalSince(writtenAt) < 1.5 {
            eagerPasteboard = true
            lastEvent = "貼り付け検知は使えません（システムが先読みしています）— 「次へ」で進めます"
            return
        }
        guard mode == .waitingForPaste else { return }

        // Do NOT write the next chunk from inside this callback. The paste
        // that triggered it is still in flight, and `writeCurrentChunk` starts
        // with `clearContents()` — which pulls the pasteboard out from under
        // the read that is happening right now. Tested: doing it synchronously
        // makes the user's paste come back EMPTY, every time, for every chunk
        // but the last. Let the current read finish, then advance.
        //
        // The delay also covers readers that ask for several types in a row
        // (a rich-text target requests RTF, then plain) — all of those belong
        // to the one paste.
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) { [weak self] in
            MainActor.assumeIsolated {
                guard let self, self.mode == .waitingForPaste else { return }
                if self.cursor + 1 < self.chunks.count {
                    self.cursor += 1
                    self.writeCurrentChunk()
                } else {
                    self.mode = .waitingForReply
                    self.lastEvent = "全て送信しました — 返信をコピーしてください"
                }
            }
        }
    }

    // MARK: - Inbound: something the user copied

    private func tick() {
        let pb = NSPasteboard.general
        guard pb.changeCount != lastChangeCount else { return }
        lastChangeCount = pb.changeCount

        guard let text = pb.string(forType: .string)?
            .trimmingCharacters(in: .whitespacesAndNewlines), !text.isEmpty
        else { return }

        // Our own chunk coming back is not a message.
        guard !text.hasPrefix(Self.marker) else { return }

        // A copy from the user means they are done reading whatever was there.
        mode = .waitingForReply
        chunks = []
        cursor = 0
        lastEvent = "受信: \(String(text.prefix(40)))…"
        onUserMessage?(text)
    }

    // MARK: - Splitting

    /// Break at paragraph, then line, then hard length — a chunk that ends
    /// mid-sentence is hard to read on a phone.
    nonisolated static func split(_ text: String, limit: Int) -> [String] {
        guard text.count > limit else { return [text] }
        var out: [String] = []
        var current = ""

        for paragraph in text.components(separatedBy: "\n") {
            let candidate = current.isEmpty ? paragraph : current + "\n" + paragraph
            if candidate.count <= limit {
                current = candidate
                continue
            }
            if !current.isEmpty { out.append(current); current = "" }

            if paragraph.count <= limit {
                current = paragraph
            } else {
                // A single paragraph longer than the limit: cut it at the
                // limit, since there is no better boundary inside it.
                var rest = Substring(paragraph)
                while rest.count > limit {
                    out.append(String(rest.prefix(limit)))
                    rest = rest.dropFirst(limit)
                }
                current = String(rest)
            }
        }
        if !current.isEmpty { out.append(current) }
        return out
    }
}

// MARK: - Lazy pasteboard item
//
// Kept as its own object because NSPasteboard holds the provider weakly-ish
// and calls it from AppKit; the closure is the only thing the relay needs back.
private final class LazyChunk: NSObject, NSPasteboardItemDataProvider {
    private let payload: String
    private let onRead: () -> Void
    private var alreadyRead = false

    init(payload: String, onRead: @escaping () -> Void) {
        self.payload = payload
        self.onRead = onRead
    }

    func pasteboard(_ pasteboard: NSPasteboard?,
                    item: NSPasteboardItem,
                    provideDataForType type: NSPasteboard.PasteboardType) {
        item.setString(payload, forType: .string)
        guard !alreadyRead else { return }
        alreadyRead = true
        onRead()
    }
}
