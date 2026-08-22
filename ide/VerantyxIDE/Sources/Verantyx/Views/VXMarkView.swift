import SwiftUI

// MARK: - VXMarkView
// Verantyx logomark — the crystalline asterisk.
// 3 hexagonal bars crossing at 60° intervals, isometric cube-star form.
// Drawn via Canvas for pixel-perfect crispness at any size.

struct VXMarkView: View {
    var size: CGFloat = 14
    var color: Color = .white

    var body: some View {
        Canvas { ctx, sz in
            let cx = sz.width / 2
            let cy = sz.height / 2
            let r  = min(cx, cy) * 0.95   // arm reach from center
            let hw = r * 0.30              // half-width of each bar

            // 3 bars at 0°, 60°, 120° — union gives the crystalline star
            for i in 0..<3 {
                let angle = Double(i) * (Double.pi / 3.0)
                let path  = barPath(cx: cx, cy: cy, angle: angle,
                                    reach: r, halfWidth: hw)
                ctx.fill(path, with: .color(color))
            }

            // Inner bright hexagon at intersection (gives the "core glow" look)
            let hexR = hw * 0.72
            var hex  = Path()
            for j in 0..<6 {
                let a  = Double(j) * Double.pi / 3.0 - Double.pi / 6.0
                let pt = CGPoint(x: cx + hexR * cos(a),
                                 y: cy + hexR * sin(a))
                j == 0 ? hex.move(to: pt) : hex.addLine(to: pt)
            }
            hex.closeSubpath()
            ctx.fill(hex, with: .color(color.opacity(0.25)))
        }
        .frame(width: size, height: size)
    }

    // Rotated rectangle path for one bar
    private func barPath(cx: CGFloat, cy: CGFloat,
                         angle: Double, reach: CGFloat,
                         halfWidth hw: CGFloat) -> Path {
        let ca = cos(angle), sa = sin(angle)
        let cp = cos(angle + .pi / 2), sp = sin(angle + .pi / 2)

        let p0 = CGPoint(x: cx + reach * ca + hw * cp,
                         y: cy + reach * sa + hw * sp)
        let p1 = CGPoint(x: cx + reach * ca - hw * cp,
                         y: cy + reach * sa - hw * sp)
        let p2 = CGPoint(x: cx - reach * ca - hw * cp,
                         y: cy - reach * sa - hw * sp)
        let p3 = CGPoint(x: cx - reach * ca + hw * cp,
                         y: cy - reach * sa + hw * sp)

        var path = Path()
        path.move(to: p0)
        path.addLine(to: p1)
        path.addLine(to: p2)
        path.addLine(to: p3)
        path.closeSubpath()
        return path
    }
}

// MARK: - Previews

struct VXMarkView_Previews: PreviewProvider {
    static var previews: some View {
        HStack(spacing: 20) {
            // Toolbar size — white on dark
            VXMarkView(size: 14, color: .white)
                .padding(6)
                .background(Color(red: 0.1, green: 0.1, blue: 0.14))
                .cornerRadius(4)

            // Medium — white
            VXMarkView(size: 22, color: .white)
                .padding(6)
                .background(Color(red: 0.1, green: 0.1, blue: 0.14))
                .cornerRadius(4)

            // Large — gray tint
            VXMarkView(size: 40, color: Color(red: 0.85, green: 0.85, blue: 0.90))
                .padding(8)
                .background(Color(red: 0.08, green: 0.08, blue: 0.12))
                .cornerRadius(6)

            // White on white bg (inverted / light mode)
            VXMarkView(size: 22, color: .black)
                .padding(6)
                .background(Color.white)
                .cornerRadius(4)
        }
        .padding(20)
        .background(Color(red: 0.12, green: 0.12, blue: 0.16))
        .previewLayout(.sizeThatFits)
    }
}
