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
// ── Why the payload carries an input box ──────────────────────────────────
//
// The first cut treated any clipboard change as the user's message. That is
// wrong in a way that matters: copy a password, a URL, a block of code
// anywhere on the Mac while the relay is on, and it would have been typed
// straight into the agent. "The clipboard changed" is not "the user spoke".
//
// The fix is not to guess where a copy came from — that cannot be done
// reliably, and trying is the wrong question anyway. Instead, ship an input
// box as part of the payload and ask a question that CAN be answered exactly:
// did this text come out of a Verantyx input box, for this session, for the
// reply I am currently waiting on?
//
//   [VX:9f31a2c4#42]   session · expected input id
//
// A match is proof. Anything else is somebody else's clipboard, and is
// ignored without a trace.
//
// ── Why plain text only ───────────────────────────────────────────────────
//
// Copying from a web page carries several representations at once (HTML, RTF,
// attributed variants), and which one a target picks is what turns pasted text
// into garbage. Notes normalizes to real characters, which is exactly why it
// works as the middle step. This relay writes and reads `.string` only, so
// nothing downstream has a representation to choose wrongly.
@MainActor
final class ClipboardChatRelay: ObservableObject {

    static let shared = ClipboardChatRelay()

    // MARK: State

    enum Mode: String { case off, waitingForPaste, waitingForReply }

    @Published private(set) var mode: Mode = .off
    @Published private(set) var chunks: [String] = []
    @Published private(set) var cursor: Int = 0
    @Published private(set) var lastEvent: String = ""

    /// Identifies this relay session. Regenerated on every start so a stale
    /// input box left in Notes from a previous session cannot be re-sent.
    @Published private(set) var sessionId: String = ""

    /// The reply we are currently waiting for. Incremented after each accepted
    /// message, so copying the same box twice does not send it twice.
    @Published private(set) var expectedInputId: Int = 0

    /// Set when the pasteboard resolves lazy data immediately on copy rather
    /// than on paste. Handoff may pre-fetch to have the content ready on the
    /// other device, which would fire the provider with no user involved.
    @Published private(set) var eagerPasteboard = false

    var isRunning: Bool { mode != .off }
    var progressLabel: String {
        chunks.isEmpty ? "" : "\(min(cursor + 1, chunks.count))/\(chunks.count)"
    }

    /// Delivered to the chat as if typed.
    var onUserMessage: ((String) -> Void)?

    // MARK: Internals

    private var poll: Timer?
    private var lastChangeCount: Int = 0
    private var writtenAt: Date = .distantPast
    private let chunkLimit = 1600

    // MARK: - Lifecycle

    func start() {
        guard mode == .off else { return }
        sessionId = String(UUID().uuidString.replacingOccurrences(of: "-", with: "")
            .prefix(8)).lowercased()
        expectedInputId = 1
        lastChangeCount = NSPasteboard.general.changeCount
        mode = .waitingForReply
        // Put an empty input box out immediately, so the phone has something
        // to paste before the agent has said anything.
        writeInputOnly()
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
        sessionId = ""
        lastEvent = ""
    }

    // MARK: - Outbound

    func send(_ reply: String) {
        guard isRunning else { return }
        let body = reply.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !body.isEmpty else { writeInputOnly(); return }
        chunks = Self.split(body, limit: chunkLimit)
        cursor = 0
        writeCurrentChunk()
    }

    /// Manual advance, for when the paste signal cannot be trusted.
    func advance() {
        guard isRunning, cursor + 1 < chunks.count else { return }
        cursor += 1
        writeCurrentChunk()
    }

    /// Just the input box — used at session start and after a message is
    /// accepted, so there is always somewhere to type.
    private func writeInputOnly() {
        writePayload(VXInputTemplate.inputBox(session: sessionId, inputId: expectedInputId),
                     lazily: false)
        mode = .waitingForReply
        lastEvent = "入力欄をクリップボードへ — メモに貼って書いてください"
    }

    private func writeCurrentChunk() {
        guard cursor < chunks.count else { writeInputOnly(); return }

        let isLast = cursor == chunks.count - 1
        var payload = "〔Vera \(cursor + 1)/\(chunks.count)〕\n" + chunks[cursor]
        if isLast {
            // The input box rides on the final chunk only. Putting it on every
            // chunk would leave three boxes in the note after three pastes.
            payload += "\n\n" + VXInputTemplate.inputBox(session: sessionId,
                                                        inputId: expectedInputId)
        } else {
            payload += "\n\n… 続きがあります。もう一度貼り付けてください。"
        }

        writePayload(payload, lazily: !eagerPasteboard)
        writtenAt = Date()
        mode = isLast ? .waitingForReply : .waitingForPaste
        lastEvent = isLast
            ? "\(progressLabel)（最後）— 貼り付けて、入力欄に返信を書いてください"
            : "\(progressLabel) をクリップボードへ — メモに貼り付けてください"
    }

    private func writePayload(_ text: String, lazily: Bool) {
        let pb = NSPasteboard.general
        pb.clearContents()
        if lazily {
            let item = NSPasteboardItem()
            item.setDataProvider(LazyChunk(payload: text) { [weak self] in
                MainActor.assumeIsolated { self?.pasteObserved() }
            }, forTypes: [.string])
            pb.writeObjects([item])
        } else {
            pb.setString(text, forType: .string)
        }
        lastChangeCount = pb.changeCount
    }

    /// The pasteboard handed our data to someone. That is a paste.
    private func pasteObserved() {
        // Handoff pre-fetching would fire this moments after the copy with no
        // human in between. A near-instant read is the system staging content,
        // not a paste — and once seen, the signal is not trusted again.
        if Date().timeIntervalSince(writtenAt) < 1.5 {
            eagerPasteboard = true
            lastEvent = "貼り付け検知は使えません（システムが先読みしています）— 「次へ」で進めます"
            return
        }
        guard mode == .waitingForPaste else { return }

        // Do NOT write the next chunk from inside this callback. The paste
        // that triggered it is still in flight, and writing begins with
        // clearContents() — which pulls the pasteboard out from under the read
        // happening right now. Tested: doing it synchronously makes the user's
        // paste come back EMPTY for every chunk but the last. The delay also
        // covers readers that ask for several types for one paste.
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) { [weak self] in
            MainActor.assumeIsolated {
                guard let self, self.mode == .waitingForPaste else { return }
                if self.cursor + 1 < self.chunks.count {
                    self.cursor += 1
                    self.writeCurrentChunk()
                }
            }
        }
    }

    // MARK: - Inbound

    private func tick() {
        let pb = NSPasteboard.general
        guard pb.changeCount != lastChangeCount else { return }
        lastChangeCount = pb.changeCount

        guard let raw = pb.string(forType: .string) else { return }

        // The only thing that counts as the user speaking: text that came out
        // of THIS session's input box, for the reply we are waiting on.
        // Everything else — a copied password, a URL, our own chunk pasted
        // back — fails this and is ignored silently.
        guard let filled = VXInputTemplate.parse(raw,
                                                 session: sessionId,
                                                 inputId: expectedInputId)
        else { return }

        guard !filled.isEmpty else {
            lastEvent = "入力欄が空のままコピーされました — 本文を書いてからコピーしてください"
            return
        }

        expectedInputId += 1
        chunks = []
        cursor = 0
        mode = .waitingForReply
        lastEvent = "受信: \(String(filled.prefix(40)))…"
        onUserMessage?(filled)
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
            if candidate.count <= limit { current = candidate; continue }
            if !current.isEmpty { out.append(current); current = "" }

            if paragraph.count <= limit {
                current = paragraph
            } else {
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

// MARK: - The input box
//
// Deliberately visible, plain ASCII framing. An invisible marker (zero-width
// characters, private-use codepoints) is exactly what a normalizing editor
// strips — and normalization is the reason Notes is in this loop at all. A
// marker that survives being retyped by hand is worth more than a pretty one.
enum VXInputTemplate {

    static let rule = "━━━━━━━━━━━━━━━━"
    static let title = "VERANTYX INPUT"
    static let placeholder = "（ここに入力してコピーしてください）"

    static func tag(session: String, inputId: Int) -> String {
        "[VX:\(session)#\(inputId)]"
    }

    static func inputBox(session: String, inputId: Int) -> String {
        """
        \(rule)
        \(title)  \(tag(session: session, inputId: inputId))
        \(rule)

        \(placeholder)

        \(rule)
        """
    }

    /// Pull the typed text out of a copied input box.
    ///
    /// Returns nil when this is not our box — wrong session, wrong reply, or
    /// not one of our boxes at all. nil means "ignore this clipboard entirely",
    /// which is what keeps unrelated copying out of the conversation.
    nonisolated static func parse(_ raw: String, session: String, inputId: Int) -> String? {
        guard !session.isEmpty, raw.contains(tag(session: session, inputId: inputId))
        else { return nil }

        // Body is what sits between the last two rules. Taking the LAST pair
        // matters: the payload the user pasted has the reply above the box,
        // and the reply may itself contain rule-like characters.
        let parts = raw.components(separatedBy: rule)
        guard parts.count >= 2 else { return nil }

        let body = parts[parts.count - 2]
        var text = body.trimmingCharacters(in: .whitespacesAndNewlines)

        // The user typed around the placeholder instead of replacing it.
        text = text.replacingOccurrences(of: placeholder, with: "")
        // A line still carrying the tag means they typed above the box.
        text = text.components(separatedBy: "\n")
            .filter { !$0.contains("[VX:") && !$0.contains(title) }
            .joined(separator: "\n")

        return text.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

// MARK: - Lazy pasteboard item

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
