import SwiftUI

// MARK: - AtelierSettingsView
//
// 服飾モード専用の設定画面。LLM モードの SettingsView (2,400 行超) とは
// 別物 — 別の UserDefaults キーに置き(AppState.swift の
// atelierDefaultUnit / atelierOperatorName)、どちらのモードで変えても
// もう一方には出ない。言語だけは例外: app.appLanguage は両モードと
// チューザー画面が読む唯一の真実で、ここでもその同じ値を読み書きする
// (別のキーへフォークしない)。
//
// ここに置く二つは ../photoloset/ の実コードを読んで決めた。エンジンが
// 実際に使う値だけを置く — 使い道の無い設定は「押して何も起きない
// ボタン」と同じ欠陥だと AtelierView.swift 自身が書いている通り:
//
//   採寸の既定単位 (cm/mm/inch) — garment_measure.py の
//     Measures.measured() は単位の無い数字を UNKNOWN_NO_UNIT で断る。
//     UNITS は cm/mm/inch の三つ(cm/inch の二択ではない)。
//     AtelierView.MeasurePanel の単位ピッカーの初期値をここから読む。
//
//   台帳に残す名前 — garment.py の Ledger.adopt は空の名前を
//     UNKNOWN_NO_ADOPTER で断る。実測・再設計の「誰が」欄も同じ理由で
//     人の名前を要る。AtelierView の AdoptSheet / DesignPanel /
//     MeasurePanel、三箇所すべての既定値をここから読む。
//
// 見送ったもの、確認した上で:
//
//   既定の縫い代・生地幅 — marker.py と mcp.py の marker_lay /
//     bom_estimate は確かにこの二つを要求し、無いと
//     UNKNOWN_SEAM_ALLOWANCE_NOT_STATED / UNKNOWN_FABRIC_WIDTH_NOT_STATED
//     で断る。だが 2026-08-26 時点、この Swift アプリのどの画面も
//     Python 側の garment_app.py も、この二つの MCP ツールを一度も
//     呼んでいない — 呼び先の無い設定は値を持っても何も変えない。
//     マーカー/BOM 画面がこのアプリに付いた時に、ここへ足す場所。
//
//   体の採寸値 — マネキンが使う寸法は Measures/Ledger 側の実測データで、
//     服ごとに変わる記録であってアプリの「設定」ではない。ここに
//     複製すると、同じ値の出所が二つになる(採寸パネルとここ)。
struct AtelierSettingsView: View {
    @EnvironmentObject var app: AppState
    var onDismiss: (() -> Void)? = nil

    private let units = ["cm", "mm", "inch"]

    var body: some View {
        VStack(spacing: 0) {
            header
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    languageSection
                    unitSection
                    nameSection
                }
                .padding(16)
            }
            .frame(width: 460, height: 330)
            .background(Theme.panel2)
            footer
        }
        .frame(width: 460, height: 430)
        .background(Theme.panel)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    // MARK: - Header / footer (SettingsView と同じ枠組み)

    private var header: some View {
        HStack(spacing: 10) {
            Button {
                onDismiss?()
            } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(Theme.dim)
                    .frame(width: 22, height: 22)
                    .background(Color.white.opacity(0.07), in: Circle())
            }
            .contentShape(Rectangle())
            .buttonStyle(.plain)
            .keyboardShortcut(.escape, modifiers: [])
            .help(app.t("Close (Esc)", "閉じる (Esc)"))

            Spacer()
            Text(app.t("Atelier Settings", "服飾の設定"))
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(Color(red: 0.75, green: 0.75, blue: 0.88))
            Spacer()

            Image(systemName: "tshirt")
                .font(.system(size: 11))
                .foregroundStyle(.quaternary)
                .frame(width: 22)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(Theme.panel)
        .overlay(Rectangle().fill(Color.white.opacity(0.07)).frame(height: 0.5), alignment: .bottom)
    }

    private var footer: some View {
        HStack(spacing: 10) {
            Spacer()
            Button(app.t("Done", "完了")) { onDismiss?() }
                .keyboardShortcut(.return, modifiers: [.command])
                .buttonStyle(.borderedProminent)
                .controlSize(.regular)
                .tint(Theme.sel)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(Theme.panel)
        .overlay(Rectangle().fill(Color.white.opacity(0.07)).frame(height: 0.5), alignment: .top)
    }

    // MARK: - Sections

    private func sectionHeader(_ title: String, icon: String) -> some View {
        HStack(spacing: 7) {
            Image(systemName: icon).font(.system(size: 11)).foregroundStyle(Theme.sel)
            Text(title).font(.system(size: 13, weight: .bold)).foregroundStyle(.white)
        }
    }

    private func settingsCard<Content: View>(@ViewBuilder content: () -> Content) -> some View {
        content()
            .padding(14)
            .background(Color.white.opacity(0.04), in: RoundedRectangle(cornerRadius: 9))
            .overlay(RoundedRectangle(cornerRadius: 9).strokeBorder(Color.white.opacity(0.08), lineWidth: 0.5))
    }

    /// 言語 — 両モードとチューザー画面が同じ `app.appLanguage` を読み書き
    /// する、唯一のグローバル設定。LLM 側の SettingsView にも同じピッカー
    /// があるが、これは服を作る人が LLM モードへ切り替えずに直せるように
    /// 置いた同じコントロール(別のキーではない)。
    private var languageSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            sectionHeader(app.t("Language (shared)", "言語（共通）"), icon: "globe")
            settingsCard {
                HStack(spacing: 10) {
                    ForEach(AppState.UILanguage.allCases, id: \.self) { lang in
                        Button {
                            withAnimation(.easeInOut(duration: 0.15)) { app.appLanguage = lang }
                        } label: {
                            VStack(spacing: 6) {
                                Text(lang.flag).font(.system(size: 22))
                                Text(lang.rawValue)
                                    .font(.system(size: 10, weight: .semibold))
                                    .foregroundStyle(app.appLanguage == lang ? .white : Theme.sel)
                            }
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 10)
                            .background(
                                app.appLanguage == lang
                                    ? Color(red: 0.25, green: 0.35, blue: 0.60).opacity(0.7)
                                    : Color.white.opacity(0.04),
                                in: RoundedRectangle(cornerRadius: 8)
                            )
                            .overlay(
                                RoundedRectangle(cornerRadius: 8)
                                    .strokeBorder(app.appLanguage == lang
                                                  ? Theme.sel.opacity(0.6)
                                                  : Color.white.opacity(0.06), lineWidth: 1)
                            )
                        }
                        .contentShape(Rectangle())
                        .buttonStyle(.plain)
                    }
                }
            }
        }
    }

    private var unitSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            sectionHeader(app.t("Default measurement unit", "採寸の既定単位"), icon: "ruler")
            settingsCard {
                VStack(alignment: .leading, spacing: 8) {
                    Picker("", selection: $app.atelierDefaultUnit) {
                        ForEach(units, id: \.self) { u in Text(u).tag(u) }
                    }
                    .pickerStyle(.segmented)
                    .labelsHidden()
                    .frame(width: 220)

                    Text(app.t(
                        "New entries in the measure panel start with this unit. garment_measure refuses a number with no unit — cm, mm, or inch, nothing else.",
                        "採寸パネルで新しく入力するとき、この単位から始まります。garment_measure は単位の無い数字を断ります — cm・mm・inch の三つだけです。"))
                        .font(.system(size: 10.5)).foregroundStyle(.tertiary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }

    private var nameSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            sectionHeader(app.t("Name kept in the ledger", "台帳に残す名前"), icon: "signature")
            settingsCard {
                VStack(alignment: .leading, spacing: 8) {
                    TextField(app.t("your name", "あなたの名前"),
                              text: $app.atelierOperatorName)
                        .textFieldStyle(.roundedBorder)
                        .frame(width: 240)

                    Text(app.t(
                        "Adopting evidence needs a name — an empty one is refused. This pre-fills that field, and the \"who measured\" / \"who decides\" fields, so you don't retype it each time. Leave it blank to keep being asked.",
                        "証拠の採用には名前が要ります — 空では断られます。この値は「採用」欄と、「測った人」「決めた人」欄の初期値になり、毎回打ち直さずに済みます。空のままなら今まで通り毎回尋ねられます。"))
                        .font(.system(size: 10.5)).foregroundStyle(.tertiary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }
}
