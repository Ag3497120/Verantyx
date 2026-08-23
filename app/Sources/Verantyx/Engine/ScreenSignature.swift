import Foundation
import CoreGraphics

// MARK: - A screen as a point in a space, not as an identity
//
// Act episodes store `screen_before` as a SHA256 of the JPEG and match it with
// `=`. Two captures of the SAME page differ by a caret blink or a clock digit,
// so the hashes differ completely and the lookup never fires. The question the
// whole episode system was built to answer — "what happened last time this app
// was in this state?" — has never once been answerable.
//
// A digest can only say "identical". What is needed is "how alike", which is
// the same move vera-a makes everywhere else: put the thing in a space and
// measure distance, so a screen resembling one seen before is recognised even
// though no two captures are ever byte-identical.
//
// ── On JGEN and multimodality ─────────────────────────────────────────────
//
// This deliberately does NOT go through JGEN. JGEN encodes text; its hidden
// states have no notion of an image, and feeding it a base64 blob would
// produce a vector describing the *characters of the encoding*, not the
// picture. Making JGEN see needs a vision tower emitting vectors into a
// compatible space — real work, and separate.
//
// What is available now, and is what "structural understanding of the screen"
// actually requires, is a structural descriptor with a metric: coarse spatial
// luminance plus local contrast. It cannot tell you the page is Reddit. It can
// tell you this screen is the one you were on two steps ago, which is the
// question the recall needs answered — and, unlike a model's opinion, it is a
// measurement.
struct ScreenSignature: Equatable {

    /// 12×12 = 144 cells. Coarse enough that text reflow and a moving cursor
    /// do not register, fine enough that a dialog opening in one corner does.
    static let side = 12

    /// Mean luminance per cell, 0…1.
    let luma: [Double]
    /// Local contrast per cell — the part that survives a theme change and
    /// distinguishes "dense text here" from "flat background here".
    let contrast: [Double]

    // MARK: Building

    static func from(_ image: CGImage) -> ScreenSignature? {
        // Sample at 2× the grid so each cell has real variance to measure.
        let n = side * 2
        var px = [UInt8](repeating: 0, count: n * n)
        guard let ctx = CGContext(data: &px, width: n, height: n,
                                  bitsPerComponent: 8, bytesPerRow: n,
                                  space: CGColorSpaceCreateDeviceGray(),
                                  bitmapInfo: CGImageAlphaInfo.none.rawValue)
        else { return nil }
        ctx.interpolationQuality = .medium
        ctx.draw(image, in: CGRect(x: 0, y: 0, width: n, height: n))

        var luma = [Double](repeating: 0, count: side * side)
        var contrast = [Double](repeating: 0, count: side * side)

        for gy in 0..<side {
            for gx in 0..<side {
                var vals: [Double] = []
                for dy in 0..<2 {
                    for dx in 0..<2 {
                        let x = gx * 2 + dx, y = gy * 2 + dy
                        vals.append(Double(px[y * n + x]) / 255.0)
                    }
                }
                let mean = vals.reduce(0, +) / Double(vals.count)
                let spread = (vals.max() ?? 0) - (vals.min() ?? 0)
                luma[gy * side + gx] = mean
                contrast[gy * side + gx] = spread
            }
        }
        return ScreenSignature(luma: luma, contrast: contrast)
    }

    // MARK: Storage
    //
    // A compact printable form, because this goes in the same TEXT column the
    // digest used and must survive a round trip through SQLite unchanged.
    // 4 bits per value: at this grid size the extra precision buys nothing and
    // costs twice the bytes in every episode row.

    var encoded: String {
        func hex(_ v: [Double]) -> String {
            v.map { String(format: "%x", Int(max(0, min(15, ($0 * 15).rounded())))) }.joined()
        }
        return "sig1:" + hex(luma) + ":" + hex(contrast)
    }

    static func decode(_ s: String) -> ScreenSignature? {
        let parts = s.split(separator: ":")
        guard parts.count == 3, parts[0] == "sig1" else { return nil }
        func vals(_ t: Substring) -> [Double]? {
            let out = t.compactMap { Int(String($0), radix: 16).map { Double($0) / 15.0 } }
            return out.count == side * side ? out : nil
        }
        guard let l = vals(parts[1]), let c = vals(parts[2]) else { return nil }
        return ScreenSignature(luma: l, contrast: c)
    }

    // MARK: Comparing

    /// 0 = identical, 1 = maximally different. Contrast is weighted lower:
    /// it moves more with rendering differences, and the layout carried by
    /// luminance is the more stable identity of a screen.
    func distance(to other: ScreenSignature) -> Double {
        guard luma.count == other.luma.count else { return 1 }
        var dl = 0.0, dc = 0.0
        for i in 0..<luma.count {
            dl += abs(luma[i] - other.luma[i])
            dc += abs(contrast[i] - other.contrast[i])
        }
        let n = Double(luma.count)
        return (dl / n) * 0.75 + (dc / n) * 0.25
    }

    /// Close enough to call the same screen.
    ///
    /// Set from what the two error cases cost. Too tight and recall never
    /// fires, which is the state this replaces. Too loose and the agent is
    /// told what it did on a different page, which is worse than silence
    /// because it reads as evidence.
    static let sameScreenThreshold = 0.06

    func isSameScreen(as other: ScreenSignature) -> Bool {
        distance(to: other) <= Self.sameScreenThreshold
    }

    /// Which cells changed, as a coarse region description. The grid is
    /// spatial, so "what moved" comes free once "how much" is measured.
    func changedRegion(vs other: ScreenSignature) -> String? {
        guard luma.count == other.luma.count else { return nil }
        var cells: [(x: Int, y: Int)] = []
        for i in 0..<luma.count where abs(luma[i] - other.luma[i]) > 0.12 {
            cells.append((i % Self.side, i / Self.side))
        }
        guard !cells.isEmpty else { return nil }
        let xs = cells.map(\.x), ys = cells.map(\.y)
        let third = Self.side / 3
        func band(_ v: Int) -> String { v < third ? "上" : (v < third * 2 ? "中" : "下") }
        func col(_ v: Int) -> String { v < third ? "左" : (v < third * 2 ? "中" : "右") }
        return "\(band(ys.reduce(0,+) / ys.count))\(col(xs.reduce(0,+) / xs.count))"
            + "（\(cells.count)/\(luma.count) セル）"
    }
}
