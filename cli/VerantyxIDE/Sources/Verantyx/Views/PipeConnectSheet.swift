import SwiftUI

/// Connecting two Macs, as one linear path.
///
/// The previous attempt at this feature was unusable — not because the concepts
/// were hard but because the UI offered every control at once and none of them
/// explained what would happen. This is deliberately the opposite shape: exactly
/// one screen at a time, exactly one primary action on each, and every failure
/// rendered in the *same slot* as one sentence plus one button, so a user who
/// hits a problem is never hunting for where the explanation went.
///
/// Two rules that keep it honest:
///
///  - Nothing offers a choice before the information needed to make it exists.
///    No role picker until both Macs are visible; no Transfer button until the
///    identity check has resolved (it has three states — Verify, Verifying,
///    then Ready-or-Transfer — because the content hash is computed lazily and
///    collapsing to two would either propose a needless multi-gigabyte copy or
///    claim "identical" on structural evidence alone).
///  - It says plainly that two Macs is not faster. Pipeline parallelism is two
///    stages at batch 1: exactly one machine computes at any instant. What it
///    buys is a model that does not fit on either Mac alone becoming runnable.
///    Someone expecting 2× would file this as broken.
struct PipeConnectSheet: View {

    @EnvironmentObject var app: AppState
    @ObservedObject private var discovery = PipeDiscovery.shared
    @ObservedObject private var session = PipeSession.shared
    @ObservedObject private var coordinator = PipeCoordinator.shared
    @Environment(\.dismiss) private var dismiss

    enum Step { case find, choose, model, ready }

    @State private var step: Step = .find
    @State private var manualHost = ""
    @State private var manualPort = "8766"
    @State private var candidate: PipeClient.Hello?
    @State private var candidateHost = ""
    @State private var candidatePort: UInt16 = 8766
    @State private var remoteModels: [PipeClient.RemoteModel] = []
    @State private var busy = false
    /// The single failure slot. One sentence; the retry button sits under it.
    @State private var problem: String?
    @State private var link: (rttMs: Double, mbPerSec: Double)?
    @State private var verifying: String?
    /// The receiving Mac's live numbers, mirrored here (name, done, total, phase).
    @State private var remoteTransfer: (name: String, done: UInt64, total: UInt64, phase: String)?

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Divider().opacity(0.2)
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    switch step {
                    case .find:   findStep
                    case .choose: chooseStep
                    case .model:  modelStep
                    case .ready:  readyStep
                    }
                    if let problem { problemSlot(problem) }
                }
                .padding(22)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            Divider().opacity(0.2)
            footer
        }
        .frame(width: 620, height: 560)
        .background(Color(red: 0.10, green: 0.10, blue: 0.13))
        .task { await enterFind() }
    }

    // MARK: - Chrome

    private var header: some View {
        HStack(spacing: 10) {
            Image(systemName: "rectangle.connected.to.line.below")
                .foregroundStyle(Color(red: 0.4, green: 0.8, blue: 0.85))
            VStack(alignment: .leading, spacing: 2) {
                Text(app.t("Use two Macs for one model", "2台のMacで1つのモデルを動かす"))
                    .font(.system(size: 14, weight: .semibold))
                Text(stepCaption)
                    .font(.system(size: 11)).foregroundStyle(.secondary)
            }
            Spacer()
            stepDots
        }
        .padding(.horizontal, 22).padding(.vertical, 14)
    }

    private var stepDots: some View {
        HStack(spacing: 5) {
            ForEach(0..<4, id: \.self) { i in
                Circle()
                    .fill(i <= stepIndex ? Color(red: 0.4, green: 0.8, blue: 0.85)
                                         : Color.white.opacity(0.15))
                    .frame(width: 6, height: 6)
            }
        }
    }

    private var stepIndex: Int {
        switch step { case .find: 0; case .choose: 1; case .model: 2; case .ready: 3 }
    }

    private var stepCaption: String {
        switch step {
        case .find:   app.t("Step 1 of 4 — find the other Mac", "手順 1/4 — もう一台を見つける")
        case .choose: app.t("Step 2 of 4 — choose which Mac runs the first half",
                            "手順 2/4 — どちらが前半を担当するか選ぶ")
        case .model:  app.t("Step 3 of 4 — check the model", "手順 3/4 — モデルを確認する")
        case .ready:  app.t("Step 4 of 4 — ready", "手順 4/4 — 準備完了")
        }
    }

    private var footer: some View {
        HStack {
            if session.isPaired {
                Button(app.t("Disconnect", "接続を解除")) {
                    Task { await disconnect() }
                }
                .buttonStyle(.bordered)
            }
            Spacer()
            Button(app.t("Close", "閉じる")) { dismiss() }
                .buttonStyle(.bordered)
        }
        .padding(.horizontal, 22).padding(.vertical, 12)
    }

    /// The one place any failure is ever shown.
    private func problemSlot(_ text: String) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 11))
                .foregroundStyle(Color(red: 0.95, green: 0.7, blue: 0.35))
            Text(text)
                .font(.system(size: 11))
                .fixedSize(horizontal: false, vertical: true)
            Spacer()
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 7).fill(Color.orange.opacity(0.08)))
    }

    // MARK: - Step 1: find

    private var findStep: some View {
        VStack(alignment: .leading, spacing: 14) {
            explainer(
                app.t("Both Macs need the same version of Verantyx, and both need this switch on.",
                      "両方のMacで同じバージョンのVerantyxが必要で、両方でこのスイッチを入れてください。"))

            Toggle(app.t("Allow this Mac to be found", "このMacを見つけられるようにする"),
                   isOn: Binding(get: { app.pipePairingEnabled },
                                 set: { app.pipePairingEnabled = $0 }))
                .toggleStyle(.switch)

            if coordinator.isEnabled {
                Text(app.t("This Mac is visible on port \(coordinator.controlPort).",
                           "このMacはポート \(coordinator.controlPort) で見えています。"))
                    .font(.system(size: 10)).foregroundStyle(.tertiary)
            }

            Divider().opacity(0.15)

            HStack(spacing: 6) {
                Text(app.t("Macs found", "見つかったMac"))
                    .font(.system(size: 12, weight: .medium))
                if discovery.isBrowsing { ProgressView().controlSize(.mini) }
            }

            if discovery.peers.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text(app.t("Nothing found yet.", "まだ見つかっていません。"))
                        .font(.system(size: 11)).foregroundStyle(.secondary)
                    if discovery.likelyBlockedByPrivacy {
                        // Denied Local Network permission looks exactly like an
                        // empty network from inside the app, so it has to be
                        // offered as a possibility rather than diagnosed.
                        problemSlot(app.t(
                            "macOS may be blocking local-network access. Open System Settings → Privacy & Security → Local Network and switch Verantyx on, then try again.",
                            "macOSがローカルネットワークへのアクセスを止めている可能性があります。システム設定 → プライバシーとセキュリティ → ローカルネットワーク でVerantyxをオンにしてから再度お試しください。"))
                    }
                }
            } else {
                ForEach(discovery.peers) { peer in
                    peerRow(peer)
                }
            }

            Divider().opacity(0.15)
            manualEntry
        }
    }

    private func peerRow(_ peer: PipeDiscovery.Peer) -> some View {
        let local = PipeStore.shared.localVersion()
        let mismatch = peer.incompatibilityReason(vs: PipeDiscovery.LocalIdentity(
            protocolVersion: local.protocolVersion, appVersion: local.appVersion,
            engineBuild: local.engineBuild, deviceId: "", deviceName: "", ramGB: 0))
        return HStack(spacing: 10) {
            Image(systemName: "desktopcomputer")
                .foregroundStyle(mismatch == nil ? Color.green : Color.orange)
            VStack(alignment: .leading, spacing: 2) {
                Text(peer.deviceName).font(.system(size: 12, weight: .medium))
                Text("\(peer.ramGB) GB · \(peer.interfaceKind.displayName)"
                     + (mismatch.map { " · \($0)" } ?? ""))
                    .font(.system(size: 10)).foregroundStyle(.secondary)
            }
            Spacer()
            if mismatch == nil {
                Button(app.t("Connect", "接続")) {
                    Task { await connectDiscovered(peer) }
                }
                .buttonStyle(.borderedProminent).controlSize(.small)
                .disabled(busy)
            } else {
                // Deliberately no override: this design assumes both engines
                // compute identical numbers bit for bit.
                Text(app.t("Not compatible", "非対応"))
                    .font(.system(size: 10)).foregroundStyle(.orange)
            }
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 7).fill(Color.white.opacity(0.04)))
    }

    private var manualEntry: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(app.t("Or type the other Mac's address",
                       "またはもう一台のアドレスを入力"))
                .font(.system(size: 11, weight: .medium))
            Text(app.t("Automatic discovery needs mDNS, which some networks block. This always works.",
                       "自動検出はmDNSを使うため、遮断しているネットワークがあります。こちらは常に使えます。"))
                .font(.system(size: 10)).foregroundStyle(.tertiary)
                .fixedSize(horizontal: false, vertical: true)
            HStack(spacing: 6) {
                TextField("10.0.0.1", text: $manualHost)
                    .textFieldStyle(.roundedBorder).frame(width: 160)
                TextField("8766", text: $manualPort)
                    .textFieldStyle(.roundedBorder).frame(width: 70)
                Button(app.t("Connect", "接続")) {
                    Task { await connect(host: manualHost.trimmingCharacters(in: .whitespaces),
                                         port: UInt16(manualPort) ?? 8766) }
                }
                .buttonStyle(.bordered).controlSize(.small)
                .disabled(busy || manualHost.trimmingCharacters(in: .whitespaces).isEmpty)
            }
            if !NetworkInterfaces.candidates().isEmpty {
                Text(app.t("This Mac's addresses: ", "このMacのアドレス: ")
                     + NetworkInterfaces.candidates().map { "\($0.ip) (\($0.kind.displayName))" }
                        .joined(separator: ", "))
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(.tertiary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    // MARK: - Step 2: choose master

    private var chooseStep: some View {
        VStack(alignment: .leading, spacing: 14) {
            if let c = candidate {
                explainer(app.t(
                    "Connected to \"\(c.deviceName)\" (\(c.ramGB) GB). The layers are cut where memory says, not down the middle — the smaller Mac gets fewer layers.",
                    "「\(c.deviceName)」(\(c.ramGB) GB) に接続しました。層は真ん中ではなくメモリに応じて切ります — メモリの少ない側の担当層が少なくなります。"))

                memoryLadder(peerRAM: Double(c.ramGB))

                notFasterNotice

                Text(app.t("Which Mac should run the first half?",
                           "どちらのMacが前半を担当しますか?"))
                    .font(.system(size: 12, weight: .medium))

                // Only one button: choosing "this Mac" is the act of becoming
                // Master, and the other side becomes Worker automatically. There
                // is no separate "make them master" — that is done from the
                // other machine, which is where its user is.
                //
                // The button carries the recommendation rather than sitting
                // beside it. The first half is not a symmetric job: its machine
                // also holds the embedding table, and in a tied-embedding model
                // (no `lm_head` tensor at all) the second half's fixed cost is
                // ZERO. Presenting this as a free choice let someone put the
                // whole fixed cost on the 24 GB Mac and lose layers that the
                // 64 GB Mac had room for.
                leadButton(recommended: thisMacShouldLead(peerRAM: Double(c.ramGB)))

                Text(thisMacShouldLead(peerRAM: Double(c.ramGB))
                     ? app.t("To let \"\(c.deviceName)\" take the first half instead, press this on that Mac.",
                             "「\(c.deviceName)」に前半を任せる場合は、そのMac側でこのボタンを押してください。")
                     : app.t("Recommended: press the same button on \"\(c.deviceName)\" — it has more memory, so it absorbs the embedding table and leaves this Mac's budget for layers.",
                             "推奨は「\(c.deviceName)」側で同じボタンを押すことです。メモリが多い側が埋め込み表を引き受け、このMacの予算を層に回せます。"))
                    .font(.system(size: 10))
                    .foregroundStyle(thisMacShouldLead(peerRAM: Double(c.ramGB))
                                     ? AnyShapeStyle(.tertiary)
                                     : AnyShapeStyle(Color(red: 0.95, green: 0.72, blue: 0.35)))
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    /// Whether THIS Mac is the right one to hold the first half.
    ///
    /// The first half is not the symmetric job the name suggests. Its machine
    /// also holds `embed_tokens`, and a tied-embedding model has no `lm_head`
    /// tensor at all — so the second half's fixed cost can be zero while the
    /// first half's never is. Giving the fixed cost to the machine with more
    /// memory is therefore never worse and is sometimes the difference between
    /// fitting and not. Equal memory (within 2 GB, so a 32 vs 32 pair with
    /// different reported totals does not flip) leaves it a real free choice,
    /// and this Mac is then a fine answer.
    private func thisMacShouldLead(peerRAM: Double) -> Bool {
        MachineProfile.current().totalRAMGB >= peerRAM - 2
    }

    @ViewBuilder
    private func leadButton(recommended: Bool) -> some View {
        let label = Label(
            app.t(recommended ? "This Mac runs the first half (recommended)"
                              : "This Mac runs the first half anyway",
                  recommended ? "このMacが前半を担当する(推奨)"
                              : "それでもこのMacが前半を担当する"),
            systemImage: "1.circle.fill")
        if recommended {
            Button { Task { await becomeMaster() } } label: { label }
                .buttonStyle(.borderedProminent)
                .disabled(busy)
        } else {
            Button { Task { await becomeMaster() } } label: { label }
                .buttonStyle(.bordered)
                .disabled(busy)
        }
    }

    /// Both machines' memory, side by side, with the larger one marked.
    ///
    /// Shown before the role choice because the choice is made on exactly this
    /// number and the user could not previously see both at once.
    private func memoryLadder(peerRAM: Double) -> some View {
        let mine = MachineProfile.current().totalRAMGB
        let peerName = candidate?.deviceName ?? app.t("the other Mac", "もう一方のMac")
        return VStack(alignment: .leading, spacing: 6) {
            memoryRow(name: app.t("This Mac", "このMac"), gb: mine,
                      larger: mine >= peerRAM)
            memoryRow(name: peerName, gb: peerRAM, larger: peerRAM > mine)
            Text(app.t(String(format: "Pipeline budget is %.0f%% of each total (%.1f GB + %.1f GB = %.1f GB usable).",
                              SplitPlanner.pipelineRAMFactor * 100,
                              mine * SplitPlanner.pipelineRAMFactor,
                              peerRAM * SplitPlanner.pipelineRAMFactor,
                              (mine + peerRAM) * SplitPlanner.pipelineRAMFactor),
                       String(format: "パイプライン時の予算は各機の%.0f%%(%.1f GB + %.1f GB = 使用可能 %.1f GB)。",
                              SplitPlanner.pipelineRAMFactor * 100,
                              mine * SplitPlanner.pipelineRAMFactor,
                              peerRAM * SplitPlanner.pipelineRAMFactor,
                              (mine + peerRAM) * SplitPlanner.pipelineRAMFactor)))
                .font(.system(size: 10)).foregroundStyle(.tertiary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 8).fill(Color.white.opacity(0.04)))
    }

    private func memoryRow(name: String, gb: Double, larger: Bool) -> some View {
        HStack(spacing: 8) {
            Image(systemName: larger ? "memorychip.fill" : "memorychip")
                .font(.system(size: 11))
                .foregroundStyle(larger ? Color(red: 0.45, green: 0.8, blue: 0.5)
                                        : Color.secondary)
            Text(name).font(.system(size: 11, weight: larger ? .semibold : .regular))
                .lineLimit(1).truncationMode(.middle)
            Spacer()
            Text(String(format: "%.0f GB", gb))
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(larger ? .primary : .secondary)
            if larger {
                Text(app.t("more memory", "メモリ多"))
                    .font(.system(size: 9))
                    .padding(.horizontal, 5).padding(.vertical, 1)
                    .background(Capsule().fill(Color(red: 0.45, green: 0.8, blue: 0.5).opacity(0.18)))
            }
        }
    }

    private var notFasterNotice: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "info.circle")
                .font(.system(size: 11))
                .foregroundStyle(Color(red: 0.5, green: 0.7, blue: 0.95))
            Text(app.t(
                "This does not make replies faster. Only one Mac computes at a time. What it does is let a model that fits on neither Mac alone actually run.",
                "これは返答が速くなる機能ではありません。計算するのは常に片方だけです。単体では入らないモデルが動くようになる、というものです。"))
                .font(.system(size: 11))
                .fixedSize(horizontal: false, vertical: true)
            Spacer()
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 7).fill(Color.blue.opacity(0.08)))
    }

    // MARK: - Step 3: model

    private var modelStep: some View {
        VStack(alignment: .leading, spacing: 12) {
            explainer(app.t(
                "Both Macs need the same model file. Pick one you have here; if the other Mac does not have it, you can send it.",
                "両方のMacに同じモデルファイルが必要です。こちらにあるものを選んでください。相手が持っていなければ送れます。"))

            let localModels = PipeStore.shared.localModels()
            if localModels.isEmpty {
                Text(app.t("No converted models on this Mac yet.",
                           "このMacにはまだ変換済みモデルがありません。"))
                    .font(.system(size: 11)).foregroundStyle(.secondary)
            }
            ForEach(localModels, id: \.name) { m in
                modelRow(local: m)
            }
        }
    }

    private func modelRow(local: PipeStore.ModelEntry) -> some View {
        let remote = remoteModels.first { $0.name == local.name }
        let localIdentity = JGenIdentity.Identity(
            fileSize: local.sizeBytes, structuralHash: local.structuralHash,
            contentHash: local.contentHash,
            contentHashKind: local.contentHashKind.flatMap {
                JGenIdentity.Identity.ContentHashKind(rawValue: $0) },
            metaHash: local.metaHash)
        let verdict = remote.map { JGenIdentity.compare(local: localIdentity, remote: $0.identity) }

        return HStack(spacing: 10) {
            VStack(alignment: .leading, spacing: 2) {
                Text(local.name)
                    .font(.system(size: 11, design: .monospaced))
                    .lineLimit(1).truncationMode(.middle)
                Text(String(format: "%.1f GB", Double(local.sizeBytes) / Double(1 << 30)))
                    .font(.system(size: 10)).foregroundStyle(.secondary)
            }
            Spacer()
            modelAction(name: local.name, sizeBytes: local.sizeBytes, verdict: verdict)
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 7).fill(Color.white.opacity(0.04)))
    }

    @ViewBuilder
    private func modelAction(name: String, sizeBytes: UInt64, verdict: JGenIdentity.Verdict?) -> some View {
        if verifying == name {
            HStack(spacing: 5) {
                ProgressView().controlSize(.mini)
                Text(app.t("Checking…", "確認中…")).font(.system(size: 10))
            }
        } else {
            switch verdict {
            case .none:
                Text(app.t("Not on the other Mac", "相手に無し"))
                    .font(.system(size: 10)).foregroundStyle(.secondary)
                transferButton(name: name, sizeBytes: sizeBytes)
            case .some(.identical):
                // The transfer affordance disappears entirely, as specified.
                Label(app.t("Both Macs have it", "両方にあります"), systemImage: "checkmark.seal.fill")
                    .font(.system(size: 10)).foregroundStyle(.green)
                Button(app.t("Use", "使う")) { Task { await useModel(name) } }
                    .buttonStyle(.borderedProminent).controlSize(.small)
            case .some(.needsContentHash):
                Button(app.t("Verify", "照合")) { Task { await verify(name) } }
                    .buttonStyle(.bordered).controlSize(.small)
            case .some(.sameWeightsDifferentMeta):
                // Re-copying gigabytes cannot fix a sidecar disagreement, so the
                // transfer button is deliberately absent here.
                Text(app.t("Same weights, different settings file",
                           "重みは同じ、設定ファイルが異なる"))
                    .font(.system(size: 10)).foregroundStyle(.orange)
            case .some(.differentWeights(let why)):
                Text(why).font(.system(size: 10)).foregroundStyle(.secondary)
                transferButton(name: name, sizeBytes: sizeBytes)
            }
        }
    }

    @ViewBuilder
    private func transferButton(name: String, sizeBytes: UInt64) -> some View {
        if let t = remoteTransfer, t.name == name, t.phase != "done", t.phase != "failed" {
            HStack(spacing: 6) {
                ProgressView(value: t.total > 0 ? Double(t.done) / Double(t.total) : 0)
                    .frame(width: 120)
                Text(t.phase == "verifying"
                     ? app.t("verifying…", "検証中…")
                     : String(format: "%.1f / %.1f GB",
                              Double(t.done) / Double(1 << 30),
                              Double(t.total) / Double(1 << 30)))
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(.secondary)
            }
        } else if ModelTransfer.shouldUseRsync(totalBytes: sizeBytes) {
            Button(app.t("How to send", "送る方法")) { showRsync(name: name) }
                .buttonStyle(.bordered).controlSize(.small)
        } else {
            Button(app.t("Send", "送る")) { Task { await startTransfer(name) } }
                .buttonStyle(.bordered).controlSize(.small)
        }
    }

    // MARK: - Step 4: ready

    private var readyStep: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 10) {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundStyle(.green)
                VStack(alignment: .leading, spacing: 2) {
                    Text(app.t("Connected", "接続済み")).font(.system(size: 13, weight: .semibold))
                    Text("\(session.role == .master ? app.t("This Mac runs the first half", "このMacが前半") : app.t("This Mac runs the second half", "このMacが後半")) ⇄ \(session.peer?.deviceName ?? "")")
                        .font(.system(size: 11)).foregroundStyle(.secondary)
                }
            }

            if let link {
                // The single most reassuring thing this screen can show: which
                // physical path the data is actually taking.
                Text(String(format: app.t("Link: %@ · %.1f ms round trip · %.0f MB/s",
                                          "リンク: %@ · 往復 %.1f ms · %.0f MB/s"),
                            discovery.peers.first?.interfaceKind.displayName ?? "Network",
                            link.rttMs, link.mbPerSec))
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(.tertiary)
            }

            if session.splitK > 0 {
                Text(app.t("Layers 0–\(session.splitK - 1) here, \(session.splitK) onward on the other Mac.",
                           "層 0〜\(session.splitK - 1) をこちらで、\(session.splitK) 以降を相手で。"))
                    .font(.system(size: 11))
            }

            notFasterNotice
        }
    }

    private func explainer(_ text: String) -> some View {
        Text(text)
            .font(.system(size: 11))
            .foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)
    }

    // MARK: - Actions

    private func enterFind() async {
        if app.pipePairingEnabled && !coordinator.isEnabled { await coordinator.enable() }
        if session.isPaired { step = .ready; await refreshLink() }
    }

    /// Resolve the Bonjour result to an address, then connect.
    ///
    /// The old call passed `peer.host ?? peer.deviceName`, and `peer.host`
    /// was never set — browse results carry names, not addresses. So every
    /// discovered connect handed a display name to `URL(string:)`, which
    /// returns nil for "本西航大のMacBook Pro", and the pairing failed as
    /// "Bad address". Resolving first is the fix; when resolution fails the
    /// message points at the manual field instead of retrying with a name
    /// that cannot work.
    private func connectDiscovered(_ peer: PipeDiscovery.Peer) async {
        if let host = peer.host, !host.isEmpty {
            await connect(host: host, port: peer.controlPort)
            return
        }
        busy = true
        problem = nil
        verifying = app.t("Resolving \(peer.deviceName)…",
                          "\(peer.deviceName) のアドレスを解決中…")
        let resolved = await PipeDiscovery.shared.resolve(peer)
        busy = false
        verifying = nil
        guard let r = resolved else {
            problem = app.t(
                "Could not resolve \(peer.deviceName) to an address. Enter "
                + "its Thunderbolt IP in the field below — discovery found "
                + "the Mac but not a route to it.",
                "\(peer.deviceName) のアドレスを解決できません。下の欄に"
                + "そのMacの Thunderbolt IP を入力してください — 発見は"
                + "できていますが経路が取れていません。")
            return
        }
        // The advertised control port is authoritative; the resolved port is
        // whatever the browser happened to connect to.
        await connect(host: r.host,
                      port: peer.controlPort != 0 ? peer.controlPort : r.port)
    }

    private func connect(host: String, port: UInt16) async {
        busy = true; problem = nil
        defer { busy = false }
        if NetworkInterfaces.isLocalAddress(host) && port == coordinator.controlPort {
            problem = app.t("That address is this Mac.", "そのアドレスはこのMac自身です。")
            return
        }
        do {
            let hello = try await PipeClient.shared.hello(host: host, port: port)
            if let reason = PipeStore.shared.versionMismatchReason(
                PipeStore.VersionTriple(protocolVersion: hello.protocolVersion,
                                        appVersion: hello.appVersion,
                                        engineBuild: hello.engineBuild),
                local: PipeStore.shared.localVersion()) {
                problem = reason
                return
            }
            if hello.paired && !hello.peerName.isEmpty {
                problem = app.t("\"\(hello.deviceName)\" is already working with \"\(hello.peerName)\".",
                                "「\(hello.deviceName)」は既に「\(hello.peerName)」と接続中です。")
                return
            }
            candidate = hello; candidateHost = host; candidatePort = port
            step = .choose
        } catch {
            problem = error.localizedDescription
        }
    }

    private func becomeMaster() async {
        busy = true; problem = nil
        defer { busy = false }
        let sessionId = UUID().uuidString
        do {
            switch try await PipeClient.shared.pairAsMaster(
                host: candidateHost, port: candidatePort,
                sessionId: sessionId, localControlPort: coordinator.controlPort) {
            case .became(_, let peer, let models):
                session.becomeMaster(peer: peer, sessionId: sessionId)
                coordinator.refreshAdvertisedRole()
                remoteModels = models
                step = .model
            case .lostTiebreak(let reason):
                // Not an error. The other Mac won; this one is the worker now.
                problem = reason
                step = .ready
                await refreshLink()
            case .refused(let reason):
                problem = reason
            }
        } catch {
            problem = error.localizedDescription
        }
    }

    private func verify(_ name: String) async {
        verifying = name
        defer { verifying = nil }
        let url = JGenPaths.convertedModelsDir.appendingPathComponent(name)
        guard let base = try? JGenIdentity.identity(forModelAt: url) else { return }
        _ = try? JGenIdentity.withContentHash(base, forModelAt: url, kind: .sampled)
        remoteModels = (try? await PipeClient.shared.models(
            host: candidateHost, port: candidatePort)) ?? remoteModels
    }

    private func useModel(_ name: String) async {
        app.loadJGenModel(name)
        await pushAutoSplit(for: name)
        step = .ready
        await refreshLink()
    }

    /// Resolves the split from both machines' real budgets and pushes it. The
    /// master is the only writer; the worker only ever displays what it is told.
    private func pushAutoSplit(for name: String) async {
        guard let peer = session.peer else { return }
        let url = JGenPaths.convertedModelsDir.appendingPathComponent(name)
        guard let layout = try? JGenIdentity.readLayout(at: url) else { return }
        let shape = SplitPlanner.ModelShape.from(layout)
        let mine = SplitPlanner.Budget(totalRAMGB: MachineProfile.current().totalRAMGB)
        let theirs = SplitPlanner.Budget(totalRAMGB: Double(peer.ramGB))
        switch SplitPlanner.auto(shape: shape, master: mine, worker: theirs) {
        case .fits(let plan):
            session.setSplit(mode: .auto, k: plan.k)
            await PipeClient.shared.pushState(host: peer.host, port: peer.controlPort,
                                              mode: "auto", k: plan.k)
        case .doesNotFit(let reason, _, _):
            // Before reporting a dead end, check the OTHER orientation. The
            // fixed costs are asymmetric (embedding table on the first half,
            // `lm_head` — possibly absent — on the second), so a pair that
            // does not fit this way around can fit the other way, and the
            // remedy is one button press on the other Mac. Saying only "it
            // does not fit" would send someone looking for a smaller model
            // when the model they have would run.
            if case .fits(let swapped) = SplitPlanner.auto(shape: shape,
                                                           master: theirs,
                                                           worker: mine) {
                problem = reason + "\n" + app.t(
                    "It DOES fit with the roles reversed (\(swapped.k)/\(shape.numLayers - swapped.k) layers). "
                    + "Press \"This Mac runs the first half\" on \"\(peer.deviceName)\" instead.",
                    "役割を入れ替えれば入ります(\(swapped.k)/\(shape.numLayers - swapped.k) 層)。"
                    + "「\(peer.deviceName)」側で「このMacが前半を担当する」を押してください。")
            } else {
                problem = reason
            }
        case .modelTooSmall(let reason):
            problem = reason
        }
    }

    /// "Send" is really "ask the other Mac to pull from me": the receiver
    /// knows its own free space and resume offsets, the sender does not. We
    /// then poll its /pipe/model/pull_status so the button that was pressed
    /// shows the same numbers the receiving Mac sees.
    private func startTransfer(_ name: String) async {
        guard let peer = session.peer else { return }
        problem = nil
        // The address the PEER should pull from: the interface we share with
        // it, best-first (Thunderbolt bridge when it is up).
        guard let myAddr = NetworkInterfaces.candidates().first?.ip else {
            problem = app.t("No network interface is up.", "有効なネットワークが見つかりません。")
            return
        }
        do {
            var req = URLRequest(url: URL(string: "http://\(peer.host):\(peer.controlPort)/pipe/model/pull")!)
            req.httpMethod = "POST"
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = try JSONSerialization.data(withJSONObject: [
                "name": name, "host": myAddr, "port": Int(coordinator.controlPort)])
            req.timeoutInterval = 10
            let (data, resp) = try await URLSession.shared.data(for: req)
            guard (resp as? HTTPURLResponse)?.statusCode == 200 else {
                let j = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
                let why = (j?["error"] as? String) ?? "HTTP \((resp as? HTTPURLResponse)?.statusCode ?? 0)"
                problem = why == "transfer_in_progress"
                    ? app.t("The other Mac is already receiving a model.", "相手のMacは別の転送を受信中です。")
                    : app.t("The other Mac refused (\(why)). Its app may be an older build — update it and retry.",
                            "相手が拒否しました (\(why))。相手のアプリが古い可能性があります。更新して再試行してください。")
                return
            }
            await pollPeerTransfer(name: name, peer: peer)
        } catch {
            problem = error.localizedDescription
        }
    }

    /// Mirrors the receiver's progress into this sheet's failure/progress slot.
    private func pollPeerTransfer(name: String, peer: PipeStore.PeerInfo) async {
        remoteTransfer = (name, 0, 0, "fetching")
        defer { if remoteTransfer?.phase != "done" && remoteTransfer?.phase != "failed" { remoteTransfer = nil } }
        while true {
            try? await Task.sleep(nanoseconds: 1_000_000_000)
            guard let url = URL(string: "http://\(peer.host):\(peer.controlPort)/pipe/model/pull_status"),
                  let (data, _) = try? await URLSession.shared.data(from: url),
                  let j = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
                  let phase = j["phase"] as? String
            else {
                problem = app.t("Lost contact with the other Mac mid-transfer. It resumes when you press Send again.",
                                "転送中に相手と切断しました。もう一度「送る」で続きから再開します。")
                return
            }
            let done = UInt64(j["done"] as? String ?? "0") ?? 0
            let total = UInt64(j["total"] as? String ?? "0") ?? 0
            remoteTransfer = (name, done, total, phase)
            switch phase {
            case "done":
                problem = nil
                await refreshRemoteModels()
                return
            case "failed":
                problem = app.t("Transfer failed on the other Mac: ", "相手側で転送失敗: ")
                    + ((j["error"] as? String) ?? "")
                return
            case "idle":
                // Receiver finished so fast we missed every non-idle poll, or
                // it never started. One more poll decides which.
                return
            default:
                continue
            }
        }
    }

    private func refreshRemoteModels() async {
        guard let peer = session.peer else { return }
        if let models = try? await PipeClient.shared.models(host: peer.host, port: peer.controlPort) {
            remoteModels = models
        }
    }

    private func showRsync(name: String) {
        guard let peer = session.peer else { return }
        let cmd = ModelTransfer.rsyncCommand(name: name, user: NSUserName(), host: peer.host)
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(cmd, forType: .string)
        problem = app.t(
            "Command copied. Run it in Terminal, then press Verify again.\n\n\(cmd)",
            "コマンドをコピーしました。ターミナルで実行してから、もう一度「照合」を押してください。\n\n\(cmd)")
    }

    private func refreshLink() async {
        guard let peer = session.peer else { return }
        link = await PipeClient.shared.measureLink(host: peer.host, port: peer.controlPort)
    }

    private func disconnect() async {
        if let peer = session.peer {
            await PipeClient.shared.unpair(host: peer.host, port: peer.controlPort)
        }
        session.unpair()
        coordinator.refreshAdvertisedRole()
        link = nil
        candidate = nil
        step = .find
    }
}
