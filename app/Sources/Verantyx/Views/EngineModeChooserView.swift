import SwiftUI
import AppKit

// MARK: - EngineModeChooserView
//
// 何も開いていない起動時、いちばん最初に出る画面。**トグルではなく画面。**
// 服飾か LLM か、両方の下に何が変わるかを一言添えて、大きく二枚出す。
//
// 一度選べば `AppState.selectEngineMode` が覚え、次回はここを通らず
// 前回いた場所に着地する — `hasChosenEngineMode` がその記憶そのもの。
// 選び直したい人のための「戻る道」はここではなく左レール側
// (`app.showModeChooser = true`)に置いてある。ここは選ぶだけの画面で、
// 選んだ後に自分で消える。
struct EngineModeChooserView: View {
    @EnvironmentObject var app: AppState

    var body: some View {
        let greetingIndex = Greetings.indexForToday()

        ZStack {
            Theme.bg.ignoresSafeArea()

            DriftingPatternBackground()
                .ignoresSafeArea()
                .allowsHitTesting(false)

            VStack(spacing: 28) {
                Spacer()

                VStack(spacing: 8) {
                    Text(app.t("Verantyx", "Verantyx"))
                        .font(.system(size: 15, weight: .bold, design: .rounded))
                        .foregroundStyle(Theme.dim)
                    Text(app.t(Greetings.en[greetingIndex], Greetings.ja[greetingIndex]))
                        .font(.system(size: 22, weight: .bold))
                        .foregroundStyle(Theme.fg)
                }

                HStack(spacing: 18) {
                    modeCard(
                        icon: "tshirt",
                        titleEN: "Atelier", titleJA: "Atelier（服飾）",
                        bodyEN: "A garment workbench. What you see is the state of the piece — evidence, structure, measurements — not a conversation.",
                        bodyJA: "服飾の作業面。画面に出るのは会話ではなく、服そのものの状態 — 証拠・構造・寸法です。",
                        mode: .atelier)

                    modeCard(
                        icon: "bubble.left.and.bubble.right",
                        titleEN: "LLM", titleJA: "LLM",
                        bodyEN: "A plain conversation with a model — code, files, a terminal alongside it. Nothing routed through the garment ledger.",
                        bodyJA: "モデルとの素の会話。コード・ファイル・ターミナルが並びます。服飾の台帳は通りません。",
                        mode: .localLLM)
                }
                .frame(maxWidth: 640)

                Spacer()
                Spacer()
            }
            .padding(40)
        }
    }

    private func modeCard(icon: String, titleEN: String, titleJA: String,
                          bodyEN: String, bodyJA: String,
                          mode: AppState.VeraEngineMode) -> some View {
        Button {
            app.selectEngineMode(mode)
        } label: {
            VStack(alignment: .leading, spacing: 14) {
                Image(systemName: icon)
                    .font(.system(size: 26, weight: .medium))
                    .foregroundStyle(Theme.sel)
                    .frame(width: 44, height: 44)
                    .background(Theme.sel.opacity(0.12), in: RoundedRectangle(cornerRadius: 10))

                Text(app.t(titleEN, titleJA))
                    .font(.system(size: 16, weight: .bold))
                    .foregroundStyle(Theme.fg)

                Text(app.t(bodyEN, bodyJA))
                    .font(.system(size: 12))
                    .foregroundStyle(Theme.dim)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)

                Spacer(minLength: 0)

                HStack(spacing: 5) {
                    Text(app.t("Start", "はじめる"))
                        .font(.system(size: 12, weight: .semibold))
                    Image(systemName: "arrow.right")
                        .font(.system(size: 10, weight: .semibold))
                }
                .foregroundStyle(Theme.sel)
            }
            .padding(20)
            .frame(width: 290, height: 210, alignment: .topLeading)
            .background(Theme.panel, in: RoundedRectangle(cornerRadius: 14))
            .overlay(RoundedRectangle(cornerRadius: 14).stroke(Theme.line, lineWidth: 1))
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Greetings
//
// リファレンスは Claude デスクトップアプリ — 挨拶が日によって変わる。
// ここも同じで、**日付から決まる** (レンダーごとに乱数を引かない — 引くと
// 再描画のたびにチラつく)。同じ日なら同じ文、次の日には別の文になる。
//
// 声域は既存コピーのまま: 淡々と、直接的に、はしゃがない。この画面は
// 最初の一文で「これはできません」も言うアプリなので、挨拶が浮いた
// トーンだと最初の一文と喧嘩する。
enum Greetings {
    static let en: [String] = [
        "What are you here to do?",
        "Where do you want to start?",
        "What's the piece today?",
        "What are we working on?",
        "What needs doing?",
        "What are you building?",
        "Where should we begin?",
        "What's on the table?",
    ]

    static let ja: [String] = [
        "何をしに来ましたか",
        "どこから始めますか",
        "今日は何をつくりますか",
        "何に取りかかりますか",
        "何が要りますか",
        "何を作っていますか",
        "どこから始めましょうか",
        "今日は何を扱いますか",
    ]

    /// 日付だけから決まる添字。時刻には依存しない — 同じ日のうちは
    /// 開き直しても同じ文のまま、日付が変われば次の文になる。
    /// `en.count == ja.count` を前提にしている(対で書くこと)。
    static func indexForToday(_ date: Date = Date(),
                               calendar: Calendar = .current) -> Int {
        let day = calendar.ordinality(of: .day, in: .era, for: date) ?? 0
        return day % en.count
    }
}

// MARK: - GarmentSnapshot
//
// 背景に敷く輪郭線は、この道具が実際に描くもの。AtelierView.swift の
// `GarmentFigure`(private struct、そちらの default/前面ケース)にある
// 座標をそのまま複製した — 300x320 の設計空間、後身頃/前身頃の襟・身頃・
// 袖・ポケット。ここは chooser 画面(プロジェクトを開く前、つまり実機の
// engine データがまだ無い場面)なので、ライブの構造を引く代わりに
// 「スナップショット」として固定値を持つ。GarmentFigure 側の形が変わって
// も、ここは自動追従しない — 架空の柄を「パターンです」と偽るよりは、
// 古くなり得る実物の複製を選んだ。
private enum GarmentSnapshot {
    static let bodyShell: [CGPoint] = [
        .init(x: 104, y: 74), .init(x: 92, y: 262), .init(x: 208, y: 262), .init(x: 196, y: 74),
    ]
    static let leftLapel: [CGPoint] = [
        .init(x: 126, y: 52), .init(x: 150, y: 86), .init(x: 118, y: 110), .init(x: 106, y: 74),
    ]
    static let rightLapel: [CGPoint] = [
        .init(x: 174, y: 52), .init(x: 150, y: 86), .init(x: 182, y: 110), .init(x: 194, y: 74),
    ]
    static let leftSleeve: [CGPoint] = [
        .init(x: 104, y: 74), .init(x: 78, y: 84), .init(x: 60, y: 224),
        .init(x: 94, y: 236), .init(x: 100, y: 150),
    ]
    static let rightSleeve: [CGPoint] = [
        .init(x: 196, y: 74), .init(x: 222, y: 84), .init(x: 240, y: 224),
        .init(x: 206, y: 236), .init(x: 200, y: 150),
    ]
    static let pockets: [CGPoint] = [
        .init(x: 110, y: 196), .init(x: 144, y: 196), .init(x: 144, y: 222), .init(x: 110, y: 222),
    ]

    /// 前面ビュー一式。設計空間は 300x320(GarmentFigure と同じ)。
    static let pieces: [[CGPoint]] = [bodyShell, leftLapel, rightLapel, leftSleeve, rightSleeve, pockets]
    static let designSize = CGSize(width: 300, height: 320)
}

// MARK: - DriftingPatternBackground
//
// 実物の輪郭線をタイル状に敷き、斜めに一定速度で流す。カードの後ろで
// 目立ってはいけないので、単色・低不透明度・線のみ(塗りなし)。負荷対策の
// 経緯は直後の `DriftLayerView` のコメントを参照。
private struct DriftingPatternBackground: NSViewRepresentable {
    func makeNSView(context: Context) -> DriftLayerView { DriftLayerView() }
    func updateNSView(_ nsView: DriftLayerView, context: Context) { nsView.rebuildIfNeeded() }
}

/// **なぜ SwiftUI の `Canvas` + `.offset` アニメーションではないか**、実測して
/// 捨てた。最初の実装は `@State` の phase を `withAnimation` で動かす版
/// だった — offset だけが変わるつもりでも、SwiftUI は毎フレーム `Canvas`
/// の描画クロージャを呼び直す。中は約700本の線分ストロークで、常駐画面で
/// 1コアが張り付いた(`top -pid <PID>` で 90〜110% を継続して観測)。
///
/// ここでは輪郭を**一度だけ** CGImage に焼き、その画像を貼った CALayer に
/// `CABasicAnimation` で position を animate させる。Core Animation の
/// アニメーションはコンポジタ(レンダーサーバ)側で回るので、SwiftUI の
/// body も CoreGraphics の再ストロークも一切呼ばれない — 焼き直した後は
/// アイドル時の追加 CPU がほぼ0%まで落ちた(同じ計測手順で確認済み)。
final class DriftLayerView: NSView {
    private let tileScale: CGFloat = 0.34
    private var tileSize: CGSize {
        CGSize(width: GarmentSnapshot.designSize.width * tileScale + 46,
               height: GarmentSnapshot.designSize.height * tileScale + 46)
    }
    private var lastBuiltSize: CGSize = .zero
    private var lastBuiltDark: Bool?
    private var tileLayer: CALayer?

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true
        layer?.masksToBounds = true
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) not used") }

    override func layout() {
        super.layout()
        rebuildIfNeeded()
    }

    override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()
        lastBuiltSize = .zero // 新しいウィンドウの backingScaleFactor で焼き直す
        rebuildIfNeeded()
    }

    override func viewDidChangeEffectiveAppearance() {
        super.viewDidChangeEffectiveAppearance()
        lastBuiltDark = nil // ライト/ダーク切り替えで再焼成
        rebuildIfNeeded()
    }

    func rebuildIfNeeded() {
        guard bounds.width > 4, bounds.height > 4 else { return }
        let isDark = effectiveAppearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
        guard bounds.size != lastBuiltSize || isDark != lastBuiltDark else { return }
        lastBuiltSize = bounds.size
        lastBuiltDark = isDark
        build(isDark: isDark)
    }

    private func build(isDark: Bool) {
        tileLayer?.removeFromSuperlayer()
        let ts = tileSize
        let cols = max(1, Int(ceil(bounds.width / ts.width)) + 3)
        let rows = max(1, Int(ceil(bounds.height / ts.height)) + 3)
        let logicalSize = CGSize(width: CGFloat(cols) * ts.width, height: CGFloat(rows) * ts.height)
        let scale = window?.backingScaleFactor ?? NSScreen.main?.backingScaleFactor ?? 2
        guard let image = Self.renderTileGrid(cols: cols, rows: rows, tileSize: ts,
                                               tileScale: tileScale, logicalSize: logicalSize,
                                               pixelScale: scale, isDark: isDark) else { return }

        let sub = CALayer()
        sub.contents = image
        sub.contentsScale = scale
        sub.anchorPoint = .zero
        sub.frame = CGRect(x: -ts.width, y: -ts.height, width: logicalSize.width, height: logicalSize.height)
        layer?.addSublayer(sub)
        tileLayer = sub

        guard !NSWorkspace.shared.accessibilityDisplayShouldReduceMotion else { return }

        let drift = CABasicAnimation(keyPath: "position")
        drift.fromValue = NSValue(point: sub.position)
        drift.toValue = NSValue(point: CGPoint(x: sub.position.x - ts.width, y: sub.position.y - ts.height))
        drift.duration = 150
        drift.repeatCount = .infinity
        drift.timingFunction = CAMediaTimingFunction(name: .linear)
        drift.isRemovedOnCompletion = false
        sub.add(drift, forKey: "drift")
    }

    /// 一度だけ焼く CoreGraphics ビットマップ。以降はこの画像を Core
    /// Animation が動かすだけで、Swift 側の再描画は起きない。
    private static func renderTileGrid(cols: Int, rows: Int, tileSize: CGSize, tileScale: CGFloat,
                                        logicalSize: CGSize, pixelScale: CGFloat, isDark: Bool) -> CGImage? {
        let pixelW = Int(logicalSize.width * pixelScale)
        let pixelH = Int(logicalSize.height * pixelScale)
        guard pixelW > 0, pixelH > 0,
              let ctx = CGContext(data: nil, width: pixelW, height: pixelH, bitsPerComponent: 8, bytesPerRow: 0,
                                   space: CGColorSpaceCreateDeviceRGB(),
                                   bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)
        else { return nil }
        ctx.scaleBy(x: pixelScale, y: pixelScale)

        // Theme.dim と同じ2値(Theme.swift を書き換えず、ここで複製している)。
        let c = isDark ? (0.541, 0.541, 0.616) : (0.360, 0.360, 0.400)
        ctx.setStrokeColor(red: c.0, green: c.1, blue: c.2, alpha: 0.09)
        ctx.setLineWidth(1)

        for r in 0..<rows {
            for c in 0..<cols {
                let origin = CGPoint(x: CGFloat(c) * tileSize.width, y: CGFloat(r) * tileSize.height)
                for piece in GarmentSnapshot.pieces {
                    guard let first = piece.first else { continue }
                    ctx.beginPath()
                    ctx.move(to: CGPoint(x: origin.x + first.x * tileScale, y: origin.y + first.y * tileScale))
                    for pt in piece.dropFirst() {
                        ctx.addLine(to: CGPoint(x: origin.x + pt.x * tileScale, y: origin.y + pt.y * tileScale))
                    }
                    ctx.closePath()
                    ctx.strokePath()
                }
            }
        }
        return ctx.makeImage()
    }
}
