import SwiftUI

/// Distributed inference, as a working panel rather than a setup wizard.
///
/// `PipeConnectSheet` is for *getting* connected — linear, one step at a time,
/// written for someone who has never done it. This is for afterwards: status,
/// the split, and the peer's models, all visible at once because by this point
/// the user knows what the words mean.
///
/// The split slider is the one control that needs care. Only the Master resolves
/// a split; a Worker's change is a *request*, and the value shown stays whatever
/// the Master last confirmed. A second writer is how two machines end up loading
/// different layer ranges and producing confident nonsense, so the UI makes the
/// asymmetry visible instead of hiding it behind an identical-looking control.
struct PipeControlPanelView: View {

    @EnvironmentObject var app: AppState
    @ObservedObject private var session = PipeSession.shared
    @ObservedObject private var transfer = TransferProgress.shared
    @ObservedObject private var coordinator = PipeCoordinator.shared
    @ObservedObject private var discovery = PipeDiscovery.shared

    @Binding var showConnectSheet: Bool

    @State private var manualK: Double = 0
    @State private var plan: SplitPlanner.Plan?
    @State private var planProblem: String?
    @State private var remoteModels: [PipeClient.RemoteModel] = []
    @State private var pushing = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                statusSection
                if session.isPaired {
                    Divider().opacity(0.2)
                    splitSection
                    Divider().opacity(0.2)
                    peerModelsSection
                }
                Divider().opacity(0.2)
                notFasterNote
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .background(Theme.panel2)
        .task { await refresh() }
    }

    // MARK: - Status

    private var statusSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            header(app.t("Two-Mac model", "2台構成"), icon: "rectangle.connected.to.line.below")

            HStack(spacing: 7) {
                Circle()
                    .fill(session.isPaired ? Color.green
                          : (coordinator.isEnabled ? Color.orange : Color.gray))
                    .frame(width: 6, height: 6)
                Text(statusLine).font(.system(size: 11))
                Spacer()
                Button(session.isPaired ? app.t("Manage", "管理") : app.t("Set up…", "設定…")) {
                    showConnectSheet = true
                }
                .buttonStyle(.bordered).controlSize(.small)
            }

            Toggle(app.t("Allow this Mac to be found", "このMacを見つけられるようにする"),
                   isOn: Binding(get: { app.pipePairingEnabled },
                                 set: { app.pipePairingEnabled = $0 }))
                .toggleStyle(.checkbox).font(.system(size: 11))

            if coordinator.isEnabled && !session.isPaired {
                Text(discovery.peers.isEmpty
                     ? app.t("No other Mac found yet.", "他のMacはまだ見つかっていません。")
                     : app.t("\(discovery.peers.count) Mac(s) visible.",
                             "\(discovery.peers.count) 台が見えています。"))
                    .font(.system(size: 9)).foregroundStyle(.tertiary)
            }
            if let e = coordinator.lastError {
                Text(e).font(.system(size: 9)).foregroundStyle(.orange)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private var statusLine: String {
        guard session.isPaired, let peer = session.peer else {
            return coordinator.isEnabled
                ? app.t("Visible, not connected", "検出可能・未接続")
                : app.t("Off", "オフ")
        }
        let role = session.role == .master
            ? app.t("first half here", "前半はこちら")
            : app.t("second half here", "後半はこちら")
        return "\(peer.deviceName) · \(role)"
    }

    // MARK: - Split

    private var splitSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            header(app.t("Layer split", "層の分割"), icon: "square.split.2x1")

            if session.role == .worker {
                // Stated rather than implied by a disabled control: a greyed-out
                // slider says "not now", this says "not here".
                Text(app.t(
                    "The Master decides the split. This Mac shows what it was told; changing it from here sends a request.",
                    "分割を決めるのはマスターです。このMacは伝えられた値を表示します。ここから変えると要求として送られます。"))
                    .font(.system(size: 9)).foregroundStyle(.tertiary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            HStack {
                Text(app.t("Mode", "モード")).font(.system(size: 10)).foregroundStyle(.secondary)
                Spacer()
                Text(session.splitMode == .auto ? app.t("Automatic", "自動") : app.t("Manual", "手動"))
                    .font(.system(size: 10, design: .monospaced))
            }

            if session.splitK > 0, let layers = loadedLayerCount {
                Text(layerRangeText(splitK: session.splitK, layers: layers))
                    .font(.system(size: 10)).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            if let layers = loadedLayerCount, layers >= 2 {
                HStack(spacing: 6) {
                    Slider(value: $manualK, in: 1...Double(layers - 1), step: 1)
                    Text("\(Int(manualK))")
                        .font(.system(size: 10, design: .monospaced))
                        .frame(width: 24, alignment: .trailing)
                }
                if let plan {
                    // Real numbers from the real tensor table, not an estimate.
                    Text(String(format: app.t("This Mac %.1f GB / %.1f GB · other Mac %.1f GB / %.1f GB",
                                              "このMac %.1f GB / %.1f GB · 相手 %.1f GB / %.1f GB"),
                                thisMacRunsFirstHalf ? plan.masterNeedGB : plan.workerNeedGB,
                                budgets.map { thisMacRunsFirstHalf ? $0.master.usableGB : $0.worker.usableGB } ?? 0,
                                thisMacRunsFirstHalf ? plan.workerNeedGB : plan.masterNeedGB,
                                budgets.map { thisMacRunsFirstHalf ? $0.worker.usableGB : $0.master.usableGB } ?? 0))
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(plan.masterHeadroomGB < 0 || plan.workerHeadroomGB < 0
                                         ? Color.orange
                                         : Theme.dim)
                }
                if let planProblem {
                    Text(planProblem).font(.system(size: 9)).foregroundStyle(.orange)
                        .fixedSize(horizontal: false, vertical: true)
                }
                HStack(spacing: 6) {
                    Button(app.t("Apply", "適用")) { Task { await applySplit(Int(manualK)) } }
                        .buttonStyle(.bordered).controlSize(.small).disabled(pushing)
                    Button(app.t("Back to automatic", "自動に戻す")) { Task { await applyAuto() } }
                        .buttonStyle(.bordered).controlSize(.small).disabled(pushing)
                    if pushing { ProgressView().controlSize(.mini) }
                }
            } else {
                Text(app.t("Load a JGEN model to choose a split.",
                           "分割を選ぶにはJGENモデルをロードしてください。"))
                    .font(.system(size: 9)).foregroundStyle(.tertiary)
            }
        }
        .onChange(of: manualK) { _, k in recompute(k: Int(k)) }
    }

    // MARK: - Peer models

    private var peerModelsSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            header(app.t("Models on the other Mac", "相手のモデル"), icon: "externaldrive")
            if remoteModels.isEmpty {
                Text(app.t("None reported.", "報告なし。"))
                    .font(.system(size: 9)).foregroundStyle(.tertiary)
            }
            ForEach(remoteModels) { m in
                HStack(spacing: 8) {
                    Circle()
                        .fill(m.archSupported ? Color.green : Color.orange)
                        .frame(width: 5, height: 5)
                    Text(m.name)
                        .font(.system(size: 10, design: .monospaced))
                        .lineLimit(1).truncationMode(.middle)
                    Spacer()
                    Text(String(format: "%.1f GB", m.sizeGB))
                        .font(.system(size: 9, design: .monospaced)).foregroundStyle(.tertiary)
                    // The other direction of the transfer feature: this Mac
                    // pulls. Same loop the peer runs when its user presses
                    // Send — the receiver always pulls, whichever button
                    // started it.
                    if transfer.phase == .fetching || transfer.phase == .verifying {
                        if transfer.name == m.name {
                            ProgressView(value: transfer.fraction).frame(width: 70)
                        }
                    } else if !localModelNames.contains(m.name) {
                        Button(app.t("Fetch", "取り寄せ")) {
                            guard let peer = session.peer else { return }
                            guard TransferProgress.shared.beginIfIdle(name: m.name) else { return }
                            let host = peer.host, port = peer.controlPort
                            Task.detached(priority: .utility) {
                                await ModelTransfer.shared.pull(name: m.name, host: host, port: port)
                            }
                        }
                        .buttonStyle(.plain).font(.system(size: 9))
                        .foregroundStyle(Theme.sel)
                    }
                }
            }
            if transfer.phase == .failed, let e = transfer.error {
                Text(e).font(.system(size: 9)).foregroundStyle(.orange)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Button(app.t("Refresh", "更新")) { Task { await refresh() } }
                .buttonStyle(.plain).font(.system(size: 9))
                .foregroundStyle(Theme.sel)
        }
    }

    private var notFasterNote: some View {
        Text(app.t(
            "Splitting does not make replies faster — only one Mac computes at a time. It makes a model that fits on neither Mac alone runnable.",
            "分割しても返答は速くなりません。計算するのは常に片方だけです。単体では入らないモデルが動くようになる機能です。"))
            .font(.system(size: 9)).foregroundStyle(.tertiary)
            .fixedSize(horizontal: false, vertical: true)
    }

    // MARK: - Bits

    private func header(_ t: String, icon: String) -> some View {
        HStack(spacing: 5) {
            Image(systemName: icon).font(.system(size: 10))
                .foregroundStyle(Theme.sel)
            Text(t).font(.system(size: 12, weight: .semibold))
        }
    }

    private func layerRangeText(splitK: Int, layers: Int) -> String {
        let other = session.peer?.deviceName ?? app.t("the other Mac", "相手")
        let first = "0–\(splitK - 1)", second = "\(splitK)–\(layers - 1)"
        return thisMacRunsFirstHalf
            ? app.t("Layers \(first) here · \(second) on \(other)",
                    "層 \(first) はこちら · \(second) は \(other)")
            : app.t("Layers \(first) on \(other) · \(second) here",
                    "層 \(first) は \(other) · \(second) はこちら")
    }

    private var localModelNames: Set<String> {
        Set(JGenConverter.shared.convertedModels)
    }

    private var loadedLayerCount: Int? {
        guard case .jcrossReady(let name) = app.modelStatus else { return nil }
        let url = JGenPaths.convertedModelsDir.appendingPathComponent(name)
        return (try? JGenIdentity.readLayout(at: url))?.layerCount
    }

    private var shape: SplitPlanner.ModelShape? {
        guard case .jcrossReady(let name) = app.modelStatus else { return nil }
        let url = JGenPaths.convertedModelsDir.appendingPathComponent(name)
        guard let layout = try? JGenIdentity.readLayout(at: url) else { return nil }
        return SplitPlanner.ModelShape.from(layout)
    }

    /// Which machine's memory is the Master's budget, and which the Worker's.
    ///
    /// This panel is shown on BOTH Macs, and every calculation in it used to
    /// pass `master: mine, worker: theirs` unconditionally. On the worker that
    /// is exactly backwards: with a 24 GB worker and a 64 GB master, the fit
    /// check validated the first half against 24 GB and the second against
    /// 64 GB — approving splits that overflow the small Mac and rejecting ones
    /// that fit. The layer ranges and the two GB readouts were inverted with
    /// it, so the screen agreed with itself while being wrong.
    private var budgets: (master: SplitPlanner.Budget, worker: SplitPlanner.Budget)? {
        guard let peer = session.peer else { return nil }
        let mine = SplitPlanner.Budget(totalRAMGB: MachineProfile.current().totalRAMGB)
        let theirs = SplitPlanner.Budget(totalRAMGB: Double(peer.ramGB))
        return session.role == .master ? (mine, theirs) : (theirs, mine)
    }

    /// True when this Mac runs layers `[0, k)`.
    private var thisMacRunsFirstHalf: Bool { session.role == .master }

    private func recompute(k: Int) {
        guard let shape, let b = budgets else { plan = nil; return }
        let (mine, theirs) = (b.master, b.worker)
        switch SplitPlanner.manual(shape: shape, k: k, master: mine, worker: theirs) {
        case .fits(let p):            plan = p; planProblem = nil
        case .doesNotFit(let r, _, _): plan = SplitPlanner.evaluate(shape: shape, k: k, master: mine, worker: theirs); planProblem = r
        case .modelTooSmall(let r):    plan = nil; planProblem = r
        }
    }

    private func applySplit(_ k: Int) async {
        pushing = true; defer { pushing = false }
        guard let peer = session.peer else { return }
        if session.role == .master {
            session.setSplit(mode: .manual, k: k)
            await PipeClient.shared.pushState(host: peer.host, port: peer.controlPort,
                                              mode: "manual", k: k)
        } else {
            planProblem = await PipeClient.shared.requestSplit(
                host: peer.host, port: peer.controlPort, mode: "manual", k: k)
        }
    }

    private func applyAuto() async {
        pushing = true; defer { pushing = false }
        guard let shape, let peer = session.peer, let b = budgets else { return }
        // Same orientation as `recompute`: the worker asking for an automatic
        // split must compute it with the MASTER's budget as the master's, or
        // it requests a k that the other Mac cannot hold.
        switch SplitPlanner.auto(shape: shape, master: b.master, worker: b.worker) {
        case .fits(let p):
            planProblem = nil
            manualK = Double(p.k)
            if session.role == .master {
                session.setSplit(mode: .auto, k: p.k)
                await PipeClient.shared.pushState(host: peer.host, port: peer.controlPort,
                                                  mode: "auto", k: p.k)
            } else {
                planProblem = await PipeClient.shared.requestSplit(
                    host: peer.host, port: peer.controlPort, mode: "auto", k: p.k)
            }
        case .doesNotFit(let r, _, _): planProblem = r
        case .modelTooSmall(let r):    planProblem = r
        }
    }

    private func refresh() async {
        if session.splitK > 0 { manualK = Double(session.splitK) }
        else if let n = loadedLayerCount { manualK = Double(n / 2) }
        recompute(k: Int(manualK))
        guard let peer = session.peer else { return }
        remoteModels = (try? await PipeClient.shared.models(
            host: peer.host, port: peer.controlPort)) ?? []
    }
}
