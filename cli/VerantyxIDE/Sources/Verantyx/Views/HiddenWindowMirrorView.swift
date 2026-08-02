import SwiftUI

/// Live preview of the Act target window tracked by HiddenWindowAutomation.
/// Under the default visible-front policy the real window stays on-screen
/// and frontmost during Act; this view re-captures it via
/// CGWindowListCreateImage for in-IDE monitoring / UI-element registration.
///
/// Also doubles as the manual "v1" UI element registry pass: clicking the
/// mirror while "Register elements" is on captures the click's position
/// relative to the window's own bounds (0-1000, matching
/// HiddenWindowAutomation.clickInWindow's convention) and saves it to Vera
/// under a name, so a repeat operation can click it directly next time
/// without a fresh screenshot + vision pass.
struct HiddenWindowMirrorView: View {
    @EnvironmentObject var app: AppState
    @ObservedObject private var automation = HiddenWindowAutomation.shared
    @State private var nsImage: NSImage?
    @State private var refreshTask: Task<Void, Never>?

    @State private var registerMode = false
    @State private var pendingPoint: (x: Double, y: Double)?
    @State private var pendingName = ""
    @State private var registeredElements: [VeraMemoryBridge.RegisteredUIElement] = []
    @State private var currentAppVersion: String?
    @State private var statusText = ""

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider().opacity(0.3)
            HStack(spacing: 0) {
                mirrorPane
                if registerMode {
                    Divider().opacity(0.3)
                    elementListPane
                        .frame(width: 220)
                }
            }
        }
        .background(Color(red: 0.04, green: 0.04, blue: 0.07))
        .task {
            await automation.beginMirrorWatch()
            startRefreshLoop()
        }
        .onDisappear {
            refreshTask?.cancel()
            Task { await automation.endMirrorWatch() }
        }
        .onChange(of: automation.targetAppName) { _, newName in
            Task {
                if newName != nil {
                    await automation.ensureMirrorTargetRestored()
                } else {
                    nsImage = nil
                }
                await refreshElementList()
            }
        }
    }

    private var mirrorPane: some View {
        GeometryReader { geo in
            ZStack {
                Color.black
                if let nsImage {
                    let fittedRect = Self.aspectFitRect(imageSize: nsImage.size, in: geo.size)
                    Image(nsImage: nsImage)
                        .resizable()
                        .aspectRatio(contentMode: .fit)
                        .overlay(
                            registerMarkers(fittedRect: fittedRect)
                        )
                        .contentShape(Rectangle())
                        .onTapGesture { location in
                            guard registerMode else { return }
                            guard fittedRect.contains(location) else { return }
                            let relX = Double((location.x - fittedRect.minX) / fittedRect.width) * 1000
                            let relY = Double((location.y - fittedRect.minY) / fittedRect.height) * 1000
                            pendingPoint = (relX, relY)
                            pendingName = ""
                        }
                } else {
                    mirrorPlaceholder
                }

                if let pendingPoint {
                    VStack(spacing: 8) {
                        Text(app.t("Name this element", "この要素の名前"))
                            .font(.caption).foregroundStyle(.secondary)
                        TextField(app.t("e.g. ComposeBox", "例: ComposeBox"), text: $pendingName)
                            .textFieldStyle(.roundedBorder)
                            .frame(width: 200)
                        HStack {
                            Button(app.t("Cancel", "キャンセル")) { self.pendingPoint = nil }
                            Button(app.t("Save", "保存")) {
                                guard let appName = automation.targetAppName, !pendingName.isEmpty else { return }
                                Task {
                                    _ = await VeraMemoryBridge.recordVerifiedUIElement(
                                        app: appName, element: pendingName,
                                        x: pendingPoint.x, y: pendingPoint.y
                                    )
                                    await MainActor.run {
                                        statusText = app.t("✓ Registered \"\(pendingName)\"", "✓「\(pendingName)」を登録しました")
                                        self.pendingPoint = nil
                                    }
                                    await refreshElementList()
                                }
                            }
                            .buttonStyle(.borderedProminent)
                            .disabled(pendingName.trimmingCharacters(in: .whitespaces).isEmpty)
                        }
                    }
                    .padding(12)
                    .background(Color.black.opacity(0.85))
                    .cornerRadius(8)
                }
            }
        }
    }

    @ViewBuilder
    private var mirrorPlaceholder: some View {
        VStack(spacing: 12) {
            Image(systemName: placeholderSymbol)
                .font(.system(size: 28))
                .foregroundStyle(Color(red: 0.7, green: 0.7, blue: 0.78))
            Text(placeholderTitle)
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(Color(red: 0.85, green: 0.9, blue: 1.0))
                .multilineTextAlignment(.center)
            Text(placeholderDetail)
                .font(.system(size: 11))
                .foregroundStyle(Color(red: 0.55, green: 0.55, blue: 0.6))
                .multilineTextAlignment(.center)
            if showsPermissionActions {
                Button {
                    ScreenCapturePermission.request()
                    ScreenCapturePermission.openSystemSettings()
                } label: {
                    Text(app.t("Open Screen Recording Settings", "画面収録の設定を開く"))
                        .font(.system(size: 11, weight: .semibold))
                }
                .buttonStyle(.borderedProminent)
            }
        }
        .padding(24)
    }

    private var placeholderSymbol: String {
        switch automation.lastCaptureStatus {
        case .permissionDenied, .blank:
            return "eye.slash"
        case .noWindow, .failed:
            return "exclamationmark.triangle"
        case .noTarget, .idle, .ok:
            return "rectangle.dashed"
        }
    }

    private var placeholderTitle: String {
        if automation.targetAppName == nil {
            return app.t("No Act target session", "操作対象セッションなし")
        }
        switch automation.lastCaptureStatus {
        case .permissionDenied:
            return app.t("Screen Recording required", "画面収録の許可が必要です")
        case .blank:
            return app.t("Capture came back blank", "キャプチャが空白です")
        case .noWindow:
            return app.t("Target window not found", "対象ウィンドウが見つかりません")
        case .failed:
            return app.t("Capture failed", "キャプチャに失敗しました")
        case .ok, .idle, .noTarget:
            return app.t("Waiting for first frame…", "最初のフレームを待機中…")
        }
    }

    private var placeholderDetail: String {
        if automation.targetAppName == nil {
            return app.t(
                "Ask the agent to [OPEN_APP: ...] to start an Act session. The target stays frontmost; this mirror previews it.",
                "エージェントに[OPEN_APP: ...]を実行させると対象が前面に出ます。このミラーでプレビューできます。"
            )
        }
        switch automation.lastCaptureStatus {
        case .permissionDenied:
            return ScreenCapturePermission.recoveryMessage
        case .blank:
            return app.t(
                "The window was found but pixels were empty. Grant Screen Recording for this Verantyx process, then re-open the mirror.",
                "ウィンドウは見つかりましたが画素が空でした。この Verantyx に画面収録を許可してからミラーを開き直してください。"
            )
        case .noWindow:
            return app.t(
                "The target app has no capturable window yet. Wait for it to finish loading.",
                "対象アプリにキャプチャ可能なウィンドウがありません。読み込み完了を待ってください。"
            )
        case .failed:
            return app.t(
                "CGWindowListCreateImage returned nothing. Check Screen Recording TCC / codesign identity.",
                "CGWindowListCreateImage が空を返しました。画面収録の TCC / 署名を確認してください。"
            )
        case .ok, .idle, .noTarget:
            return app.t(
                "Session is active — refreshing the live mirror…",
                "セッション稼働中 — ライブミラーを更新しています…"
            )
        }
    }

    private var showsPermissionActions: Bool {
        automation.targetAppName != nil
            && (automation.lastCaptureStatus == .permissionDenied
                || automation.lastCaptureStatus == .blank
                || !ScreenCapturePermission.isGranted)
    }

    @ViewBuilder
    private func registerMarkers(fittedRect: CGRect) -> some View {
        ForEach(registeredElements) { el in
            let px = fittedRect.minX + (el.x / 1000) * fittedRect.width
            let py = fittedRect.minY + (el.y / 1000) * fittedRect.height
            Circle()
                .stroke(isStale(el) ? Color(red: 1.0, green: 0.7, blue: 0.3) : Color(red: 0.4, green: 0.9, blue: 0.5), lineWidth: 2)
                .frame(width: 14, height: 14)
                .position(x: px, y: py)
        }
    }

    private var elementListPane: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(app.t("Registered elements", "登録済み要素"))
                .font(.system(size: 11, weight: .bold))
                .foregroundStyle(Color(red: 0.85, green: 0.9, blue: 1.0))
                .padding(10)
            Divider().opacity(0.2)
            if registeredElements.isEmpty {
                Text(app.t("None yet — click the mirror to register one.", "まだありません — ミラーをクリックして登録してください。"))
                    .font(.system(size: 10))
                    .foregroundStyle(Color(red: 0.55, green: 0.55, blue: 0.6))
                    .padding(10)
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: 6) {
                        ForEach(registeredElements) { el in
                            HStack(spacing: 5) {
                                Circle()
                                    .fill(isStale(el) ? Color(red: 1.0, green: 0.7, blue: 0.3) : Color(red: 0.4, green: 0.9, blue: 0.5))
                                    .frame(width: 6, height: 6)
                                Text(el.element)
                                    .font(.system(size: 11, design: .monospaced))
                                    .foregroundStyle(Color(red: 0.85, green: 0.85, blue: 0.9))
                                    .lineLimit(1)
                                if isStale(el) {
                                    Image(systemName: "exclamationmark.triangle.fill")
                                        .font(.system(size: 9))
                                        .foregroundStyle(Color(red: 1.0, green: 0.7, blue: 0.3))
                                        .help(app.t(
                                            "App updated since registration (\(el.version) → \(currentAppVersion ?? "?")) — may need re-check",
                                            "登録時からアプリが更新されています（\(el.version) → \(currentAppVersion ?? "?")）— 再確認が必要かもしれません"
                                        ))
                                }
                            }
                        }
                    }
                    .padding(.horizontal, 10)
                }
            }
            if !statusText.isEmpty {
                Divider().opacity(0.2)
                Text(statusText)
                    .font(.system(size: 10))
                    .foregroundStyle(Color(red: 0.4, green: 0.9, blue: 0.5))
                    .padding(8)
            }
        }
        .background(Color.black.opacity(0.3))
    }

    private var header: some View {
        HStack(spacing: 10) {
            Image(systemName: "eye.trianglebadge.exclamationmark")
                .font(.system(size: 13))
                .foregroundStyle(Color(red: 1.0, green: 0.7, blue: 0.3))
            Text(app.t("Act Target Mirror", "操作対象ミラー"))
                .font(.system(size: 12, weight: .bold))
                .foregroundStyle(Color(red: 0.85, green: 0.9, blue: 1.0))
            if let name = automation.targetAppName {
                Text("· \(name)")
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(Color(red: 0.6, green: 0.6, blue: 0.7))
            }
            if automation.targetAppName != nil {
                Text(headerStatusLabel)
                    .font(.system(size: 10))
                    .foregroundStyle(headerStatusColor)
            }
            Spacer()

            Button {
                registerMode.toggle()
                pendingPoint = nil
            } label: {
                HStack(spacing: 4) {
                    Image(systemName: "mappin.and.ellipse")
                    Text(app.t("Register elements", "要素を登録"))
                }
                .font(.system(size: 10, weight: .semibold))
            }
            .buttonStyle(.plain)
            .foregroundStyle(registerMode
                ? Color(red: 0.4, green: 0.9, blue: 0.5)
                : Color(red: 0.6, green: 0.6, blue: 0.7))

            if automation.targetAppName != nil {
                Button {
                    Task { await automation.endOffscreenSession() }
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "xmark.circle")
                        Text(app.t("End session", "セッション終了"))
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
                if automation.targetAppName != nil {
                    if let base64 = await automation.captureWindowImage(),
                       let data = Data(base64Encoded: base64),
                       let image = NSImage(data: data) {
                        nsImage = image
                    } else if automation.lastCaptureStatus != .ok {
                        // Drop a stale frame when capture is denied/blank so
                        // the status placeholder is visible instead of a
                        // silent black rectangle.
                        nsImage = nil
                    }
                } else {
                    nsImage = nil
                }
                try? await Task.sleep(nanoseconds: 800_000_000)
            }
        }
        Task { await refreshElementList() }
    }

    private var headerStatusLabel: String {
        switch automation.lastCaptureStatus {
        case .ok:
            return app.t("live", "ライブ")
        case .permissionDenied:
            return app.t("needs Screen Recording", "画面収録が必要")
        case .blank:
            return app.t("blank frame", "空白フレーム")
        case .noWindow:
            return app.t("no window", "ウィンドウなし")
        case .failed:
            return app.t("capture failed", "失敗")
        case .idle, .noTarget:
            return app.t("waiting", "待機")
        }
    }

    private var headerStatusColor: Color {
        switch automation.lastCaptureStatus {
        case .ok:
            return Color(red: 0.4, green: 0.9, blue: 0.5)
        case .permissionDenied, .blank, .failed, .noWindow:
            return Color(red: 1.0, green: 0.7, blue: 0.3)
        case .idle, .noTarget:
            return Color(red: 0.6, green: 0.6, blue: 0.7)
        }
    }

    private func refreshElementList() async {
        guard let appName = automation.targetAppName else {
            await MainActor.run { registeredElements = []; currentAppVersion = nil }
            return
        }
        async let elements = VeraMemoryBridge.listVerifiedUIElements(app: appName)
        async let version = automation.currentAppVersion(appName: appName)
        let (fetchedElements, fetchedVersion) = await (elements, version)
        await MainActor.run {
            registeredElements = fetchedElements
            currentAppVersion = fetchedVersion
        }
    }

    /// Whether `el`'s recorded version differs from the app's current one
    /// -- a cheap, fully-local proxy for "the UI may have changed since
    /// this was registered," since no external feed publishes that.
    private func isStale(_ el: VeraMemoryBridge.RegisteredUIElement) -> Bool {
        guard !el.version.isEmpty, let currentAppVersion else { return false }
        return el.version != currentAppVersion
    }

    /// The actual displayed rect of an aspect-fit image within its
    /// container, needed to translate a tap location into a 0-1000
    /// coordinate relative to the real (off-screen) window bounds.
    private static func aspectFitRect(imageSize: NSSize, in containerSize: CGSize) -> CGRect {
        guard imageSize.width > 0, imageSize.height > 0 else {
            return CGRect(origin: .zero, size: containerSize)
        }
        let imageAspect = imageSize.width / imageSize.height
        let containerAspect = containerSize.width / containerSize.height
        if imageAspect > containerAspect {
            let height = containerSize.width / imageAspect
            let y = (containerSize.height - height) / 2
            return CGRect(x: 0, y: y, width: containerSize.width, height: height)
        } else {
            let width = containerSize.height * imageAspect
            let x = (containerSize.width - width) / 2
            return CGRect(x: x, y: 0, width: width, height: containerSize.height)
        }
    }
}
