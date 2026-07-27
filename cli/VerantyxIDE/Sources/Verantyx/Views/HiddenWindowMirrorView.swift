import SwiftUI

/// Live view of whatever window HiddenWindowAutomation has parked
/// off-screen for autonomous operation. The real window never appears on
/// the user's actual display and never steals focus from Verantyx -- this
/// view is the only place its content is actually visible, refreshed on a
/// timer by re-capturing it via CGWindowListCreateImage (which works
/// regardless of on-screen position).
struct HiddenWindowMirrorView: View {
    @EnvironmentObject var app: AppState
    @ObservedObject private var automation = HiddenWindowAutomation.shared
    @State private var nsImage: NSImage?
    @State private var refreshTask: Task<Void, Never>?

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider().opacity(0.3)
            ZStack {
                Color.black
                if let nsImage {
                    Image(nsImage: nsImage)
                        .resizable()
                        .aspectRatio(contentMode: .fit)
                } else {
                    Text(app.t(
                        "No app is currently parked off-screen. Ask the agent to [OPEN_APP: ...] to start a hidden session.",
                        "現在オフスクリーンに退避中のアプリはありません。エージェントに[OPEN_APP: ...]を実行させるとここに表示されます。"
                    ))
                    .font(.system(size: 11))
                    .foregroundStyle(Color(red: 0.55, green: 0.55, blue: 0.6))
                    .multilineTextAlignment(.center)
                    .padding(24)
                }
            }
        }
        .background(Color(red: 0.04, green: 0.04, blue: 0.07))
        .task { startRefreshLoop() }
        .onDisappear { refreshTask?.cancel() }
    }

    private var header: some View {
        HStack(spacing: 10) {
            Image(systemName: "eye.trianglebadge.exclamationmark")
                .font(.system(size: 13))
                .foregroundStyle(Color(red: 1.0, green: 0.7, blue: 0.3))
            Text(app.t("Hidden Window Mirror", "非表示ウィンドウ ミラー"))
                .font(.system(size: 12, weight: .bold))
                .foregroundStyle(Color(red: 0.85, green: 0.9, blue: 1.0))
            if let name = automation.targetAppName {
                Text("· \(name)")
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(Color(red: 0.6, green: 0.6, blue: 0.7))
            }
            Spacer()
            if automation.targetAppName != nil {
                Button {
                    Task { await automation.endOffscreenSession() }
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "arrow.uturn.left")
                        Text(app.t("Restore window", "ウィンドウを復元"))
                    }
                    .font(.system(size: 10, weight: .semibold))
                }
                .buttonStyle(.plain)
                .foregroundStyle(Color(red: 1.0, green: 0.7, blue: 0.3))
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(Color.black.opacity(0.4))
    }

    private func startRefreshLoop() {
        refreshTask?.cancel()
        refreshTask = Task {
            while !Task.isCancelled {
                if automation.targetAppName != nil,
                   let base64 = await automation.captureWindowImage(),
                   let data = Data(base64Encoded: base64) {
                    nsImage = NSImage(data: data)
                }
                try? await Task.sleep(nanoseconds: 800_000_000)
            }
        }
    }
}
