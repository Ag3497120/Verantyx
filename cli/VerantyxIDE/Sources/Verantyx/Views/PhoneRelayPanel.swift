import SwiftUI

/// Controls the clipboard chat relay: chat from an iPhone while the agent has
/// the Mac's screen. Lives in Settings because it is a session mode, not a
/// per-message action.
struct PhoneRelayPanel: View {

    @EnvironmentObject var app: AppState
    @ObservedObject private var relay = ClipboardChatRelay.shared

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {

            HStack(spacing: 10) {
                Image(systemName: "iphone.gen3.radiowaves.left.and.right")
                    .font(.system(size: 15))
                    .foregroundStyle(relay.isRunning
                                     ? Color(red: 0.35, green: 0.85, blue: 1.0) : .secondary)
                VStack(alignment: .leading, spacing: 2) {
                    Text("iPhone リレー（クリップボード経由）")
                        .font(.system(size: 12, weight: .semibold)).foregroundStyle(.white)
                    Text("エージェントが画面を使っている間、iPhone のメモでチャットします。")
                        .font(.system(size: 10)).foregroundStyle(.secondary)
                }
                Spacer()
                Button(relay.isRunning ? "停止" : "開始") {
                    if relay.isRunning {
                        relay.stop()
                    } else {
                        relay.onUserMessage = { text in
                            AppState.shared?.sendMessage(with: text)
                        }
                        relay.start()
                    }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
            }

            if relay.isRunning {
                Divider().opacity(0.2)

                HStack(spacing: 8) {
                    Circle()
                        .fill(relay.mode == .waitingForPaste
                              ? Color(red: 1.0, green: 0.75, blue: 0.2)
                              : Color(red: 0.3, green: 0.9, blue: 0.5))
                        .frame(width: 7, height: 7)
                    Text(relay.lastEvent)
                        .font(.system(size: 11)).foregroundStyle(.secondary)
                    Spacer()
                    if relay.chunks.count > 1 {
                        Text(relay.progressLabel)
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(.tertiary)
                        Button("次へ") { relay.advance() }
                            .buttonStyle(.bordered)
                            .controlSize(.small)
                            .disabled(relay.cursor + 1 >= relay.chunks.count)
                    }
                }

                if relay.eagerPasteboard {
                    Text("このMacでは貼り付けの検知ができません（システムが内容を先読みするため）。"
                         + "長い返信は「次へ」で送ってください。")
                        .font(.system(size: 10))
                        .foregroundStyle(Color(red: 1.0, green: 0.75, blue: 0.2))
                }

                Text("""
                使い方: ① 開始 → ② iPhone の「メモ」を開く → ③ 貼り付けると返答が読めます \
                （長い場合は続けて貼り付け）→ ④ 返信を書いてコピーすると、Mac 側が受け取ります。
                """)
                    .font(.system(size: 10)).foregroundStyle(.tertiary).lineSpacing(2)

                Text("""
                前提: 同じ Apple ID・Handoff/Bluetooth/Wi-Fi が有効（ユニバーサルクリップボード）。\
                本文は Apple の経路のみを通り、外部サーバーには一切送信されません。\
                ただしクリップボードは両端末のどのアプリからも読めるため、機密の会話には使わないでください。
                """)
                    .font(.system(size: 10)).foregroundStyle(.tertiary).lineSpacing(2)
            }
        }
    }
}
