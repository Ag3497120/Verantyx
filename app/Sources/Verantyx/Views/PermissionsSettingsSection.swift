import SwiftUI
import ApplicationServices

// MARK: - PermissionsSettingsSection
//
// Accessibility と Screen Recording は、Atelier (服飾モード) のどの操作
// にも要らない — マネキン・採寸・台帳はどれも Vera の台帳を通るアプリ内
// データで、画面を見たりクリックを送ったりしない。要るのは LLM モード側
// のエージェント操作 (OSControl / ForegroundAppOperator / AXVisionBridge /
// ScreenChangeMonitor) だけ。
//
// 以前は起動 1 秒後に無条件でこの二つを要求し、2.5 秒後にはアラートまで
// 出していた (VerantyxApp.applicationDidFinishLaunching) — Atelier しか
// 使わない人にも、まだ一度もエージェントを動かしていない人にも、毎回
// ポップアップが出ていた。ここに移した理由は「使うときに、使う人にだけ」
// — 実際に権限を要求する側 (上記 4 ファイル) の `AXIsProcessTrusted()` /
// `ScreenCapturePermission.isGranted` ガードは変えていない。それらは今も
// 「使った瞬間に足りないと分かる」唯一の場所のまま。ここは「今どうなって
// いるか」を見て、能動的に直しに行くための画面 — 起動時に押し付ける画面
// ではない。
//
// 色だけに頼らない: 8% の男性は赤緑を見分けにくい
// (AttentionOverviewView.Kind.label / JGenVeraSettingsPanelView の
// 「許可済み」と同じ理由・同じ言葉)。だからここでも許可状態は必ず
// 単語でも書く — 「許可済み」/「未許可」。チェックマークやアイコンの色
// だけでは判定不能な人がいる、という前提。
struct PermissionsSettingsSection: View {
    @EnvironmentObject var app: AppState

    @State private var axGranted = AXIsProcessTrusted()
    @State private var screenGranted = ScreenCapturePermission.isGranted
    @State private var showScreenRecovery = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            permissionRow(
                icon: "hand.tap.fill",
                title: app.t("Accessibility", "アクセシビリティ"),
                granted: axGranted,
                usage: app.t(
                    "Lets an agent click, type, and read elements in other apps on your behalf. Only used when an agent action needs it — not for using Atelier.",
                    "エージェントが他のアプリをクリック・入力し、画面の要素を読み取れるようにします。エージェントの操作が実際に必要とした時だけ使われます — 服飾(Atelier)の利用には不要です。"),
                permit: requestAccessibility,
                openSettings: openAccessibilitySettings
            )

            Divider().opacity(0.15).padding(.vertical, 12)

            permissionRow(
                icon: "record.circle",
                title: app.t("Screen Recording", "画面収録"),
                granted: screenGranted,
                usage: app.t(
                    "Lets an agent capture the screen it is automating, so it can see what it just did. Only used when an agent action needs it — not for using Atelier.",
                    "エージェントが自分の操作結果を確認できるよう、自動操作中の画面を撮影できるようにします。エージェントの操作が実際に必要とした時だけ使われます — 服飾(Atelier)の利用には不要です。"),
                permit: requestScreenRecording,
                openSettings: ScreenCapturePermission.openSystemSettings,
                recoveryDetail: ScreenCapturePermission.recoveryMessage
            )
        }
        .onAppear { refresh() }
        // System Settings で許可を切り替えて Verantyx に戻ってきた瞬間を
        // 捉える唯一の合図。これが無いと「許可した直後もチェックマークは
        // 古いまま」になる — タスクが名指しで禁じた「嘘のチェックマーク」
        // そのもの。
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
            refresh()
        }
    }

    private func refresh() {
        axGranted = AXIsProcessTrusted()
        screenGranted = ScreenCapturePermission.isGranted
    }

    // MARK: - Permit actions
    //
    // これはユーザーが押した明示的なボタンからのみ呼ばれる — 起動時の
    // 無条件リクエストとは違う。AXIsProcessTrustedWithOptions は既存の
    // AXVisionBridge.checkAndRequestPermissions() と同じ呼び方 (prompt: true)。

    private func requestAccessibility() {
        let options = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary
        _ = AXIsProcessTrustedWithOptions(options)
    }

    private func openAccessibilitySettings() {
        let urls = [
            "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
            "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_Accessibility",
        ]
        for s in urls {
            if let u = URL(string: s), NSWorkspace.shared.open(u) { return }
        }
    }

    private func requestScreenRecording() {
        ScreenCapturePermission.request()
    }

    // MARK: - Row

    @ViewBuilder
    private func permissionRow(
        icon: String,
        title: String,
        granted: Bool,
        usage: String,
        permit: @escaping () -> Void,
        openSettings: @escaping () -> Void,
        recoveryDetail: String? = nil
    ) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 12) {
                ZStack {
                    Circle()
                        .fill(granted ? Theme.ok.opacity(0.15) : Color.white.opacity(0.05))
                        .frame(width: 32, height: 32)
                    Image(systemName: icon)
                        .font(.system(size: 13))
                        .foregroundStyle(granted ? Theme.ok : .secondary)
                }

                VStack(alignment: .leading, spacing: 2) {
                    Text(title)
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(.white)
                    // 単語で状態を書く行 — 色/アイコンだけに頼らない。
                    Text(granted ? app.t("Granted", "許可済み") : app.t("Not granted", "未許可"))
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(granted ? Theme.ok : Theme.warn)
                }

                Spacer()

                if granted {
                    HStack(spacing: 4) {
                        Image(systemName: "checkmark.circle.fill")
                            .font(.system(size: 14))
                            .foregroundStyle(Theme.ok)
                    }
                } else {
                    Button(app.t("Permit…", "許可する…")) { permit() }
                        .buttonStyle(.borderedProminent)
                        .controlSize(.small)
                }
            }

            Text(usage)
                .font(.system(size: 10))
                .foregroundStyle(.tertiary)
                .fixedSize(horizontal: false, vertical: true)

            HStack(spacing: 12) {
                Button(app.t("Open System Settings", "システム設定を開く")) { openSettings() }
                    .buttonStyle(.bordered)
                    .controlSize(.small)

                if recoveryDetail != nil {
                    Button {
                        withAnimation(.easeInOut(duration: 0.15)) { showScreenRecovery.toggle() }
                    } label: {
                        Text(showScreenRecovery
                             ? app.t("Hide recovery steps", "復旧手順を隠す")
                             : app.t("Still not working? Show recovery steps",
                                     "直らない場合は復旧手順を表示"))
                            .font(.system(size: 10))
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(Theme.sel)
                }
            }

            // ScreenCapturePermission.recoveryMessage の全文 (tccutil の
            // 手順、ad-hoc 署名の注記を含む) — 削除せずここに移しただけ。
            // 既定では畳んであり、必要な人だけが開く。
            if let recoveryDetail, showScreenRecovery {
                Text(recoveryDetail)
                    .font(.system(size: 9.5, design: .monospaced))
                    .foregroundStyle(.secondary)
                    .padding(10)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.white.opacity(0.03), in: RoundedRectangle(cornerRadius: 6))
                    .textSelection(.enabled)
            }
        }
    }
}
