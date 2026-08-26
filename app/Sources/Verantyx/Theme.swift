import SwiftUI
import AppKit

// MARK: - Theme
//
// 元は AtelierView.swift の `enum AT` — 服飾台帳のためだけに書かれた配色で、
// 他の 87 画面からは一切参照されていなかった (実測 0 件)。その結果、同じ
// 「ok/green」のつもりの色が 1,090 箇所の Color(red:green:blue:) の中に
// 472 通りの微妙な変種として散らばっていた。ここでは同じ 12 トークンを
// アプリ全体の唯一の色源にする。
//
// **なぜ NSColor(name:) の動的プロバイダなのか**、SwiftUI の
// `.preferredColorScheme` や `@Environment(\.colorScheme)` を各 88 画面に
// 配線するのではなく: NSColor は自分で実効 appearance を解決できる。
// `Theme.ok` は呼び出し側が colorScheme を知らなくても、ウィンドウの実効
// appearance (システム設定 or NSApp.appearance で強制した値) を見て自動的に
// dark/light を切り替える。配線し忘れる画面が原理的に存在しない。
//
// 検証済み: /private/tmp/.../scratchpad/dynamic_color_test.swift で
// NSAppearance(.darkAqua)/.aqua を `performAsCurrentDrawingAppearance` 越しに
// 強制し、同じ NSColor が異なる RGB を返すことを実測した
// (dark: 0.35/0.75/0.54, light: 0.11/0.45/0.28 — 狙った値と一致)。
enum Theme {

    // MARK: - 動的トークンの作り方
    //
    // ダークの値をそのまま反転してライトにしない。ここが「言うは易く」の
    // 部分 — ok/warn/bad はほぼ黒地の上で映えるよう調整済みの明るい彩度で、
    // 白地に置くと WCAG コントラスト比が軒並み 3:1 を割る (実測、後述)。
    // ライト側は別に採寸して、両方に対して比を測っている。
    private static func dynamicNSColor(
        dark: (Double, Double, Double),
        light: (Double, Double, Double)
    ) -> NSColor {
        NSColor(name: nil) { appearance in
            let isDark = appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
            let c = isDark ? dark : light
            return NSColor(srgbRed: c.0, green: c.1, blue: c.2, alpha: 1.0)
        }
    }

    private static func dynamic(
        dark: (Double, Double, Double),
        light: (Double, Double, Double)
    ) -> Color {
        Color(nsColor: dynamicNSColor(dark: dark, light: light))
    }

    // MARK: - AppKit (NSTextView/NSScrollView/WKWebView) 用の生 NSColor
    //
    // Color(nsColor:) の SwiftUI 側トークンは NSTextView.backgroundColor や
    // WKWebView.layer.backgroundColor には代入できない (前者は NSColor、
    // 後者は CGColor) — AppKit のブリッジ層 (CodeView.swift の NSViewRepresentable、
    // LineNumberRulerView.swift、ArtifactPanelView.swift の WKWebView) がライト
    // モードでも固定ダークのまま浮いていた原因のひとつがこれ。同じ動的解決を
    // NSColor のまま公開する。
    static let nsBg     = dynamicNSColor(dark: (0.063, 0.063, 0.086), light: (0.980, 0.980, 0.985))
    static let nsPanel2 = dynamicNSColor(dark: (0.106, 0.106, 0.149), light: (0.900, 0.900, 0.915))
    static let nsFg     = dynamicNSColor(dark: (0.914, 0.914, 0.949), light: (0.090, 0.090, 0.110))
    static let nsFaint  = dynamicNSColor(dark: (0.403, 0.403, 0.403), light: (0.517, 0.517, 0.517))

    // MARK: - 背景と罫線
    static let bg     = dynamic(dark: (0.063, 0.063, 0.086), light: (0.980, 0.980, 0.985))
    static let panel  = dynamic(dark: (0.086, 0.086, 0.122), light: (0.945, 0.945, 0.955))
    static let panel2 = dynamic(dark: (0.106, 0.106, 0.149), light: (0.900, 0.900, 0.915))
    /// 装飾的な罫線。WCAG 1.4.11 の非テキストコントラストは「境界を識別する
    /// 上で必要な」UI 部品にのみ適用され、単なる仕切り線は対象外
    /// (同注記の decorative exemption)。実測 dark 1.18〜1.31:1 /
    /// light 1.35〜1.61:1 — 意図的に沈めている値で、テキストではない。
    static let line   = dynamic(dark: (0.157, 0.157, 0.212), light: (0.780, 0.780, 0.800))

    // MARK: - 文字
    static let fg     = dynamic(dark: (0.914, 0.914, 0.949), light: (0.090, 0.090, 0.110))
    static let dim    = dynamic(dark: (0.541, 0.541, 0.616), light: (0.360, 0.360, 0.400))
    /// 三段目の最も控えめな文字。dim よりさらに沈めつつ、地色に対して
    /// 4.5:1 (通常サイズの本文基準) を要求すると dim と区別がつかない
    /// 灰色に収束してしまう (実測: dark は 0.51 階調必要、dim=0.541 と衝突)。
    /// そのため WCAG の「大きな文字/非テキスト要素」枠である 3:1 を最低線に
    /// 採寸した — railHead のようなトラッキング済みラベルや区切り記号での
    /// 使用を前提にした選択で、本文サイズの必須情報には使わないこと。
    static let faint  = dynamic(dark: (0.403, 0.403, 0.403), light: (0.517, 0.517, 0.517))

    // MARK: - 状態色 (台帳の五状態と共有)
    static let ok     = dynamic(dark: (0.349, 0.753, 0.541), light: (0.110, 0.450, 0.280))
    static let warn   = dynamic(dark: (0.851, 0.635, 0.290), light: (0.560, 0.360, 0.020))
    static let bad    = dynamic(dark: (0.878, 0.392, 0.373), light: (0.720, 0.120, 0.120))
    static let sel    = dynamic(dark: (0.357, 0.561, 0.839), light: (0.100, 0.350, 0.750))

    /// 移行で見つかった追加トークン。SettingsView のトグル行アイコンなど
    /// 10 箇所以上で紫 (0.7, 0.4, 1.0) が ok/warn/bad/sel のどれとも違う
    /// 「特別な機能」の意味で使われていた — 最も近いトークンに押し込めると
    /// 意味が壊れるので、既存 12 色に無い意味として素直にトークンを足した。
    static let accent = dynamic(dark: (0.700, 0.400, 1.000), light: (0.420, 0.200, 0.650))

    // MARK: - 台帳の状態 → 色・記号
    //
    // OBSERVED/CONTESTED/INFERRED/PROPOSED/UNKNOWN_NOT_OBSERVED は
    // このアプリで色の意味が全画面共通であるべき唯一の語彙。以前は
    // AtelierView.swift だけがこの対応表を持っていて(呼べる場所も
    // AtelierView.swift の中だけ)、他の画面が同じ状態を描くときに
    // 独自の色判定を書く余地があった。ここに一本化する。
    static func color(_ state: String) -> Color {
        switch state {
        case "OBSERVED", "MEASURED", "GENERIC_CONSTRUCTION": return ok
        case "CONTESTED", "CONTESTED_ORIGIN", "SPECIFIC_TO_SOURCE": return bad
        // 計算値は確定と同じ色にしない。裁つ前に実測で確かめるもの。
        case "INFERRED", "DERIVED": return warn
        default: return dim
        }
    }

    static func fill(_ state: String) -> Color {
        color(state).opacity(state == "UNKNOWN_NOT_OBSERVED" ? 0.06 : 0.18)
    }

    /// 状態の印。**寸法と由来の語彙も知っている必要がある。**
    ///
    /// 実測した 96.0cm が「?」で出ていた(実地で踏んだ)。この表を
    /// 観測の語彙だけで書くと、他の台帳から来た行が全部「不明」に
    /// 落ちる — 指示書としては嘘になる。
    static func symbol(_ state: String) -> String {
        switch state {
        case "OBSERVED", "MEASURED": return "✓"
        case "CONTESTED", "CONTESTED_ORIGIN": return "×"
        case "INFERRED": return "△"
        case "DERIVED": return "≈"
        case "PROPOSED": return "·"
        case "GENERIC_CONSTRUCTION": return "一般"
        case "SPECIFIC_TO_SOURCE": return "実例"
        default: return "?"
        }
    }

    static func short(_ state: String) -> String {
        state.replacingOccurrences(of: "_NOT_OBSERVED", with: "")
    }

    static func kindColor(_ kind: String) -> Color {
        switch kind {
        case "observation": return ok
        case "inference": return warn
        default: return dim
        }
    }
}

// MARK: - AppAppearanceMode
//
// System/Light/Dark の三択。トークン自体は appearance を自分で解決できる
// ので配線は要らないが、「アプリを常にダークで使いたい」という指定は
// システム設定ではなく NSApp.appearance に効かせる必要がある — SwiftUI の
// `.preferredColorScheme` はウィンドウ単位で、メニューバー拡張や独立ウィンドウ
// (ScreenEdgeGlowController 等) まで揃って切り替わらないため、アプリ全体の
// 実効 appearance を変える NSApp.appearance の方を使う。
enum AppAppearanceMode: String, CaseIterable, Identifiable {
    case system
    case light
    case dark

    var id: String { rawValue }

    static let storageKey = "verantyx_appearance_mode"

    var label: (String, String) {
        switch self {
        case .system: return ("System", "システム")
        case .light:  return ("Light", "ライト")
        case .dark:   return ("Dark", "ダーク")
        }
    }

    var icon: String {
        switch self {
        case .system: return "circle.lefthalf.filled"
        case .light:  return "sun.max.fill"
        case .dark:   return "moon.fill"
        }
    }

    /// NSApp.appearance に反映する。`.system` は nil を渡すことで
    /// 「OS の設定に従う」という NSApplication のデフォルト挙動に戻す —
    /// 固定した appearance を明示的に解除する必要があり、他の値を
    /// 適当に選んでもシステム追従には戻らない。
    func apply() {
        switch self {
        case .system: NSApp.appearance = nil
        case .light:  NSApp.appearance = NSAppearance(named: .aqua)
        case .dark:   NSApp.appearance = NSAppearance(named: .darkAqua)
        }
    }

    /// 起動時の復元用。SwiftUI の View が生きる前 (VerantyxApp の
    /// onAppear) から呼べるよう、@AppStorage ではなく UserDefaults を
    /// 直接読む。
    static func loadPersisted() -> AppAppearanceMode {
        let raw = UserDefaults.standard.string(forKey: storageKey) ?? AppAppearanceMode.system.rawValue
        return AppAppearanceMode(rawValue: raw) ?? .system
    }
}
