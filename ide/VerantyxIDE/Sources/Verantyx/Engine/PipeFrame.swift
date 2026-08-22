import Foundation

/// Wire format for the pipeline data plane.
///
/// Split out of `PipeChannel` so it can be compiled and exercised without a
/// socket, an actor, or a loaded model. This is the part where a mistake is
/// least visible — a wrong offset produces a residual that is merely *shifted*,
/// which still generates fluent text, just the wrong text — so it is the part
/// that most needs to be testable on its own.
///
/// All integers little-endian. Header is 20 bytes:
///
///     magic  u32   'VXPP'
///     ver    u16   protocol version, independent of the app version
///     type   u16   FrameType
///     seq    u64   request id, echoed in the reply
///     len    u32   payload length
enum PipeFrame {

    static let magic: UInt32 = 0x5850_5856
    static let headerSize = 20
    static let protocolVersion: UInt16 = 1

    enum FrameType: UInt16 {
        case hello = 1, helloAck = 2
        case segment = 3, token = 4
        case reset = 5, resetAck = 6
        case error = 7
        case ping = 8, pong = 9
    }

    struct Header: Equatable {
        var version: UInt16
        var type: FrameType
        var seq: UInt64
        var length: UInt32
    }

    struct Segment: Equatable {
        var startLayer: UInt32
        var endLayer: UInt32
        var startPos: UInt64
        var seqLen: UInt32
        var flags: UInt32
        /// `seqLen × hidden` f32, row-major.
        var hidden: [Float]
    }

    enum FrameError: Error, Equatable {
        case badMagic
        case unknownType(UInt16)
        case truncated
        case shape(String)
    }

    // MARK: - Header

    static func encode(type: FrameType, seq: UInt64, payload: Data) -> Data {
        var out = Data(capacity: headerSize + payload.count)
        out.append(le32(magic))
        out.append(le16(protocolVersion))
        out.append(le16(type.rawValue))
        out.append(le64(seq))
        out.append(le32(UInt32(payload.count)))
        out.append(payload)
        return out
    }

    static func decodeHeader(_ d: Data) throws -> Header {
        guard d.count >= headerSize else { throw FrameError.truncated }
        let b = [UInt8](d.prefix(headerSize))
        guard u32(b, 0) == magic else { throw FrameError.badMagic }
        let raw = u16(b, 6)
        guard let type = FrameType(rawValue: raw) else { throw FrameError.unknownType(raw) }
        return Header(version: u16(b, 4), type: type, seq: u64(b, 8), length: u32(b, 16))
    }

    // MARK: - Segment

    static func encodeSegment(_ s: Segment) -> Data {
        var out = Data(capacity: 24 + s.hidden.count * 4)
        out.append(le32(s.startLayer))
        out.append(le32(s.endLayer))
        out.append(le64(s.startPos))
        out.append(le32(s.seqLen))
        out.append(le32(s.flags))
        // Explicit per-value little-endian rather than a raw memory copy: a raw
        // copy is host-endian and would silently produce garbage the day this
        // talks to anything that is not another arm64 Mac.
        for f in s.hidden { out.append(le32(f.bitPattern)) }
        return out
    }

    static func decodeSegment(_ d: Data) throws -> Segment {
        guard d.count >= 24 else { throw FrameError.truncated }
        let b = [UInt8](d)
        let floatBytes = d.count - 24
        guard floatBytes % 4 == 0 else { throw FrameError.truncated }
        var hidden = [Float](repeating: 0, count: floatBytes / 4)
        for i in 0..<hidden.count {
            hidden[i] = Float(bitPattern: u32(b, 24 + i * 4))
        }
        return Segment(startLayer: u32(b, 0), endLayer: u32(b, 4), startPos: u64(b, 8),
                       seqLen: u32(b, 16), flags: u32(b, 20), hidden: hidden)
    }

    /// Splits a flat residual into rows, refusing rather than guessing when the
    /// count does not divide evenly — an uneven split is a protocol bug, and
    /// carrying on would feed the engine rows of the wrong width.
    static func rows(_ s: Segment) throws -> [[Float]] {
        let n = Int(s.seqLen)
        guard n > 0, s.hidden.count % n == 0 else {
            throw FrameError.shape("\(s.hidden.count) floats do not divide into \(n) rows")
        }
        let width = s.hidden.count / n
        return (0..<n).map { Array(s.hidden[($0 * width)..<(($0 + 1) * width)]) }
    }

    // MARK: - Token

    static func encodeToken(_ token: UInt32, topK: [(id: UInt32, logit: Float)] = []) -> Data {
        var out = Data()
        out.append(le32(token))
        out.append(le32(UInt32(topK.count)))
        for e in topK {
            out.append(le32(e.id))
            out.append(le32(e.logit.bitPattern))
        }
        return out
    }

    static func decodeToken(_ d: Data) throws -> UInt32 {
        guard d.count >= 4 else { throw FrameError.truncated }
        return u32([UInt8](d.prefix(4)), 0)
    }

    // MARK: - Byte helpers

    static func le16(_ v: UInt16) -> Data { Data([UInt8(v & 0xFF), UInt8(v >> 8)]) }
    static func le32(_ v: UInt32) -> Data { Data((0..<4).map { UInt8((v >> (8 * $0)) & 0xFF) }) }
    static func le64(_ v: UInt64) -> Data { Data((0..<8).map { UInt8((v >> (8 * UInt64($0))) & 0xFF) }) }

    static func u16(_ b: [UInt8], _ i: Int) -> UInt16 { UInt16(b[i]) | UInt16(b[i+1]) << 8 }
    static func u32(_ b: [UInt8], _ i: Int) -> UInt32 {
        UInt32(b[i]) | UInt32(b[i+1]) << 8 | UInt32(b[i+2]) << 16 | UInt32(b[i+3]) << 24
    }
    static func u64(_ b: [UInt8], _ i: Int) -> UInt64 {
        var v: UInt64 = 0
        for k in (0..<8).reversed() { v = (v << 8) | UInt64(b[i + k]) }
        return v
    }
}
