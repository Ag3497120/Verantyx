import Foundation
import Network

/// Per-token transport for a split model: one persistent TCP connection carrying
/// binary frames.
///
/// Deliberately not the HTTP control plane. `JGenAgentServer` sends
/// `Connection: close` and cancels after every response, so a decode step would
/// cost a TCP handshake — about 9 ms per token over Wi-Fi, purely wasted — and
/// JSON-encoding 5120 floats produces roughly 120 KB of text per frame against
/// 20 KB of actual data.
///
/// What crosses the wire, and why it is small:
///
///   uplink   (master → worker)  one residual: seq_len × hidden × 4 bytes
///   downlink (worker → master)  the sampled token id: 4 bytes
///
/// The worker returns a *token*, not logits and not a hidden state. Logits would
/// be 496 KB at vocab 248320 and the master has no use for them; returning a
/// hidden state would force the master to hold `lm_head` (2.5 GB), which defeats
/// the entire point of splitting. The engine samples by pure greedy argmax —
/// there is no temperature, top-p or RNG anywhere in it — so the worker can pick
/// the token with no coordination at all. Stop policy (EOS, repeat guard, cycle
/// detection, max tokens, cancel) stays on the master, which owns the tokenizer
/// and the streaming callback.
///
/// Wire precision is **f32, not f16**. f16 would save 10 KB per token on a link
/// that moves 10 KB in about 10 µs, in exchange for a 65504 ceiling on a
/// residual stream that grows with depth. If this ever needs to shrink, bf16 is
/// the answer — same exponent range as f32, so no overflow class of bug.
actor PipeChannel {

    static let shared = PipeChannel()

    // MARK: - Wire format
    //
    // Lives in `PipeFrame` so it can be exercised without a socket or a model.
    // Aliased here so call sites read naturally.

    typealias Header = PipeFrame.Header
    typealias FrameType = PipeFrame.FrameType
    typealias SegmentFrame = PipeFrame.Segment

    enum ChannelError: Error, LocalizedError {
        case notConnected
        case truncated
        case remote(String)
        case timeout

        var errorDescription: String? {
            switch self {
            case .notConnected: return "Not connected to the worker."
            case .truncated:    return "The worker closed the connection mid-frame."
            case .remote(let m): return m
            case .timeout:      return "The worker did not answer in time."
            }
        }
    }

    // MARK: - Timeouts
    //
    // Generous on purpose: a 27B CPU decode step legitimately takes seconds, and
    // prefill of a long prompt takes far longer. A 5 s timeout would fire
    // constantly on exactly the model this feature exists for.
    static let prefillTimeout: TimeInterval = 120
    static let decodeTimeout: TimeInterval = 60

    // MARK: - State

    private var listener: NWListener?
    private var connection: NWConnection?
    private(set) var boundPort: UInt16 = 0
    private var nextSeq: UInt64 = 1

    /// Worker side: the last request answered, replayed verbatim if the same
    /// `seq` arrives again. This is what makes a timeout retry safe rather than
    /// state-corrupting — without it, a retried SEGMENT would append to the KV
    /// cache twice and every later token would be computed against a cache one
    /// position too long.
    private var lastHandledSeq: UInt64 = 0
    private var lastReply: Data?

    /// Worker side: absolute position this side expects next, so a dropped or
    /// duplicated frame is caught instead of silently producing wrong text.
    private var expectedPos: UInt64 = 0

    private init() {}

    // MARK: - Worker side (listen)

    func startListening(preferredPort: UInt16 = 8790) throws {
        stopListening()
        var bound: NWListener?
        for candidate in preferredPort..<(preferredPort + 8) {
            guard let p = NWEndpoint.Port(rawValue: candidate) else { continue }
            if let l = try? NWListener(using: .tcp, on: p) {
                bound = l
                boundPort = candidate
                break
            }
        }
        guard let listener = bound else { throw ChannelError.notConnected }
        listener.newConnectionHandler = { [weak self] conn in
            Task { await self?.accept(conn) }
        }
        listener.start(queue: .global(qos: .userInitiated))
        self.listener = listener
    }

    func stopListening() {
        listener?.cancel(); listener = nil
        connection?.cancel(); connection = nil
        boundPort = 0
        lastHandledSeq = 0; lastReply = nil; expectedPos = 0
    }

    private func accept(_ conn: NWConnection) {
        // One master at a time: a second connection replaces the first rather
        // than racing it over the same KV cache.
        connection?.cancel()
        connection = conn
        conn.start(queue: .global(qos: .userInitiated))
        Task { await serveLoop(conn) }
    }

    /// Worker request loop. Runs until the connection drops.
    private func serveLoop(_ conn: NWConnection) async {
        while true {
            guard let (header, payload) = try? await Self.readFrame(conn) else { return }

            // Duplicate request: replay the stored answer without re-applying it.
            if header.seq != 0, header.seq == lastHandledSeq, let cached = lastReply {
                await Self.send(conn, cached)
                continue
            }

            let reply: Data
            switch header.type {
            case .ping:
                reply = PipeFrame.encode(type: .pong, seq: header.seq, payload: Data())
            case .hello:
                reply = PipeFrame.encode(type: .helloAck, seq: header.seq, payload: Data())
            case .reset:
                // Must complete before the master starts a turn. Beginning a
                // generation against a cache still holding the previous turn's
                // positions produces plausible, wrong text with no error at all —
                // the most dangerous failure in this design.
                await JCrossChatManager.shared.resetEngine()
                expectedPos = 0
                reply = PipeFrame.encode(type: .resetAck, seq: header.seq, payload: Data())
            case .segment:
                reply = await handleSegment(header: header, payload: payload)
            default:
                reply = PipeFrame.encode(type: .error, seq: header.seq,
                                    payload: Data("unexpected frame".utf8))
            }

            lastHandledSeq = header.seq
            lastReply = reply
            await Self.send(conn, reply)
        }
    }

    private func handleSegment(header: Header, payload: Data) async -> Data {
        guard let frame = try? PipeFrame.decodeSegment(payload) else {
            return PipeFrame.encode(type: .error, seq: header.seq,
                               payload: Data("malformed segment".utf8))
        }
        // Position is master-owned and never derived here; this only checks that
        // what arrived is what was expected, so a dropped or duplicated frame is
        // reported instead of quietly corrupting the output.
        if frame.startPos != expectedPos {
            return PipeFrame.encode(type: .error, seq: header.seq, payload: Data(
                "position_desync expected=\(expectedPos) got=\(frame.startPos)".utf8))
        }
        guard let hidden = try? PipeFrame.rows(frame) else {
            return PipeFrame.encode(type: .error, seq: header.seq, payload: Data(
                "segment shape: \(frame.hidden.count) floats do not divide into \(frame.seqLen) rows".utf8))
        }

        do {
            let result = try await JCrossChatManager.shared.runSegment(
                hidden: hidden,
                startLayer: Int(frame.startLayer),
                endLayer: Int(frame.endLayer),
                startPos: Int(frame.startPos),
                rawFlags: frame.flags)
            expectedPos += UInt64(frame.seqLen)
            switch result {
            case .token(let t):
                return PipeFrame.encode(type: .token, seq: header.seq, payload: PipeFrame.encodeToken(t))
            case .hidden(let rows):
                let flat = rows.flatMap { $0 }
                return PipeFrame.encode(type: .segment, seq: header.seq,
                                   payload: PipeFrame.encodeSegment(SegmentFrame(
                                    startLayer: frame.startLayer, endLayer: frame.endLayer,
                                    startPos: frame.startPos, seqLen: UInt32(rows.count),
                                    flags: 0, hidden: flat)))
            }
        } catch {
            return PipeFrame.encode(type: .error, seq: header.seq,
                               payload: Data(error.localizedDescription.utf8))
        }
    }

    // MARK: - Master side (connect)

    func connect(host: String, port: UInt16) async throws {
        connection?.cancel()
        guard let nwPort = NWEndpoint.Port(rawValue: port) else { throw ChannelError.notConnected }
        let conn = NWConnection(host: NWEndpoint.Host(host), port: nwPort, using: .tcp)
        conn.start(queue: .global(qos: .userInitiated))
        connection = conn
        nextSeq = 1
        _ = try await request(type: .hello, payload: Data(), timeout: 10)
    }

    func disconnect() {
        connection?.cancel(); connection = nil
    }

    /// Clears both sides' caches. Blocks on the ack: starting a turn without one
    /// is the silent-corruption case described above.
    func resetPeer() async throws {
        let (h, _) = try await request(type: .reset, payload: Data(), timeout: 30)
        guard h.type == .resetAck else { throw ChannelError.remote("worker did not acknowledge reset") }
    }

    /// Sends a residual and gets back the sampled token.
    func sendSegmentForToken(
        hidden: [[Float]], startLayer: Int, endLayer: Int, startPos: Int, flags: UInt32,
        timeout: TimeInterval
    ) async throws -> UInt32 {
        let frame = SegmentFrame(
            startLayer: UInt32(startLayer), endLayer: UInt32(endLayer),
            startPos: UInt64(startPos), seqLen: UInt32(hidden.count),
            flags: flags, hidden: hidden.flatMap { $0 })
        let (h, payload) = try await request(type: .segment,
                                             payload: PipeFrame.encodeSegment(frame),
                                             timeout: timeout)
        switch h.type {
        case .token: return try PipeFrame.decodeToken(payload)
        case .error:
            let msg = String(decoding: payload, as: UTF8.self)
            if msg.hasPrefix("position_desync") {
                throw ChannelError.remote(msg)
            }
            throw ChannelError.remote(msg)
        default: throw ChannelError.remote("unexpected reply \(h.type)")
        }
    }

    /// One outstanding request at a time, matched by `seq`.
    private func request(type: FrameType, payload: Data, timeout: TimeInterval) async throws -> (Header, Data) {
        guard let conn = connection else { throw ChannelError.notConnected }
        let seq = nextSeq
        nextSeq += 1
        await Self.send(conn, PipeFrame.encode(type: type, seq: seq, payload: payload))

        return try await withThrowingTaskGroup(of: (Header, Data).self) { group in
            group.addTask { try await Self.readFrame(conn) }
            group.addTask {
                try await Task.sleep(nanoseconds: UInt64(timeout * 1_000_000_000))
                throw ChannelError.timeout
            }
            let result = try await group.next()!
            group.cancelAll()
            return result
        }
    }

    // MARK: - Socket I/O

    private static func send(_ conn: NWConnection, _ data: Data) async {
        await withCheckedContinuation { (c: CheckedContinuation<Void, Never>) in
            conn.send(content: data, completion: .contentProcessed { _ in c.resume() })
        }
    }

    /// Reads exactly one frame. `NWConnection.receive(exactly:)` is used for both
    /// header and body so a large residual split across TCP segments reassembles
    /// correctly — the HTTP parser's "read until \r\n\r\n" approach cannot work
    /// for binary payloads that may contain any byte sequence.
    private static func readFrame(_ conn: NWConnection) async throws -> (Header, Data) {
        let headerData = try await receiveExactly(conn, PipeFrame.headerSize)
        let header = try PipeFrame.decodeHeader(headerData)
        let payload = header.length > 0
            ? try await receiveExactly(conn, Int(header.length))
            : Data()
        return (header, payload)
    }

    private static func receiveExactly(_ conn: NWConnection, _ count: Int) async throws -> Data {
        try await withCheckedThrowingContinuation { cont in
            conn.receive(minimumIncompleteLength: count, maximumLength: count) { data, _, isComplete, error in
                if let error { cont.resume(throwing: error); return }
                guard let data, data.count == count else {
                    cont.resume(throwing: isComplete ? ChannelError.truncated : ChannelError.truncated)
                    return
                }
                cont.resume(returning: data)
            }
        }
    }
}
