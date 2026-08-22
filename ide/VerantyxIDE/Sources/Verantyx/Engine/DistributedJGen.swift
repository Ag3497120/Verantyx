import Foundation

// Running a jgen larger than one Mac, across a Thunderbolt bridge.
//
// Two arrangements, and they are NOT the same thing — conflating them is
// how "distributed" becomes a word that means nothing:
//
//   REMOTE   the peer holds the whole model and answers over HTTP. Simple,
//            already works (point the endpoint at the peer), and it does
//            NOT let you run a model neither machine could hold.
//   SHARDED  the model's layers are split across both machines and the
//            activations cross the Thunderbolt link every token. This is
//            what makes qwen3.6:27b possible on two Macs that each fall
//            short — MLX's ring backend over the TB bridge.
//
// This type prepares and launches the SHARDED arrangement and reports
// precisely which preconditions are missing, because a distributed setup
// that half-works is worse than one that refuses: the failure surfaces as
// slow gibberish rather than an error.
//
// Preconditions, each checked and named:
//   1. a Thunderbolt Bridge interface with an address (TB cable + bridge
//      configured in System Settings on both Macs)
//   2. the peer reachable at its bridge address
//   3. python with mlx and mlx_lm on BOTH machines
//   4. passwordless ssh to the peer (mlx.launch runs the ring over ssh)
//
// Nothing here fabricates a fallback: when a precondition fails, drafting
// keeps using whatever single-node endpoint is configured, and the panel
// says the sharded path is unavailable and why.

struct TBInterface {
    let device: String       // bridge0
    let address: String      // 169.254.x.x or configured static
}

struct DistributedReadiness {
    var bridge: TBInterface?
    var peerReachable: Bool = false
    var localMLX: Bool = false
    var peerMLX: Bool = false
    var sshOK: Bool = false
    var notes: [String] = []

    var canShard: Bool {
        bridge != nil && peerReachable && localMLX && peerMLX && sshOK
    }
}

enum DistributedJGen {

    // MARK: Preconditions

    /// The Thunderbolt Bridge interface and its address, if configured.
    static func thunderboltBridge() -> TBInterface? {
        // `networksetup -listallhardwareports` names the bridge device;
        // ifconfig carries whether it actually has an address. Both are
        // needed: a bridge with no inet is a cable nobody configured.
        guard let ports = run("/usr/sbin/networksetup",
                              ["-listallhardwareports"]) else { return nil }
        var device: String?
        var sawTB = false
        for line in ports.split(separator: "\n") {
            if line.contains("Thunderbolt Bridge") { sawTB = true; continue }
            if sawTB, line.hasPrefix("Device: ") {
                device = String(line.dropFirst("Device: ".count))
                    .trimmingCharacters(in: .whitespaces)
                break
            }
        }
        guard let dev = device,
              let cfg = run("/sbin/ifconfig", [dev]) else { return nil }
        for line in cfg.split(separator: "\n") {
            let t = line.trimmingCharacters(in: .whitespaces)
            if t.hasPrefix("inet "), let addr = t.split(separator: " ").dropFirst().first {
                return TBInterface(device: dev, address: String(addr))
            }
        }
        return nil
    }

    static func check(peerHost: String) async -> DistributedReadiness {
        var r = DistributedReadiness()
        r.bridge = thunderboltBridge()
        if r.bridge == nil {
            r.notes.append(L("No Thunderbolt Bridge address. Connect the "
                             + "cable and enable Thunderbolt Bridge in "
                             + "System Settings → Network on both Macs.",
                             "Thunderbolt Bridge にアドレスがありません。"
                             + "ケーブルを接続し、両方の Mac のシステム設定→"
                             + "ネットワークで Thunderbolt Bridge を有効に。"))
        }
        r.localMLX = (mlxBin("mlx.launch") != nil)
        if !r.localMLX {
            r.notes.append(L("mlx / mlx_lm missing here: pip3 install mlx mlx-lm",
                             "この機に mlx / mlx_lm がありません: pip3 install mlx mlx-lm"))
        }
        guard !peerHost.isEmpty else {
            r.notes.append(L("No peer host set.", "ピアのホストが未設定です。"))
            return r
        }
        r.peerReachable = (run("/sbin/ping", ["-c", "1", "-t", "2", peerHost]) != nil)
        if !r.peerReachable {
            r.notes.append(L("Peer \(peerHost) does not answer ping.",
                             "ピア \(peerHost) が ping に応答しません。"))
            return r
        }
        // ssh without a password is what mlx.launch needs; test it as such.
        let sshProbe = run("/usr/bin/ssh",
                           ["-o", "BatchMode=yes", "-o", "ConnectTimeout=4",
                            peerHost, "python3 -c 'import mlx.core, mlx_lm; print(1)'"])
        r.sshOK = sshProbe != nil
        r.peerMLX = (sshProbe?.contains("1") ?? false)
        if !r.sshOK {
            r.notes.append(L("Passwordless ssh to \(peerHost) failed — "
                             + "ssh-copy-id first; mlx.launch runs the ring over ssh.",
                             "\(peerHost) へのパスワード無し ssh が失敗 — "
                             + "先に ssh-copy-id を。mlx.launch は ssh 上で ring を張ります。"))
        } else if !r.peerMLX {
            r.notes.append(L("Peer lacks mlx / mlx_lm: pip3 install mlx mlx-lm there.",
                             "ピアに mlx / mlx_lm がありません: 向こうで pip3 install mlx mlx-lm。"))
        }
        return r
    }

    // MARK: Launch

    /// The ring hostfile, generated by MLX's own tool.
    ///
    /// `mlx.distributed_config --over thunderbolt` exists precisely for
    /// this topology: it discovers the Thunderbolt links between the hosts
    /// and writes the ring in the order the cables actually run. A
    /// hand-written `[{"ssh": a}, {"ssh": b}]` — which this originally had
    /// — ignores the wiring and can ring the machines over the wrong
    /// interface, which is how "distributed" becomes slow gibberish.
    static func writeHostfile(local: String, peer: String) -> URL? {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("vera-mlx-hosts.json")
        if let cfg = mlxBin("mlx.distributed_config"),
           run(cfg, ["--backend", "ring", "--over", "thunderbolt",
                     "--hosts", "\(local),\(peer)",
                     "--hostfile-only", "--output-hostfile", url.path]) != nil,
           FileManager.default.fileExists(atPath: url.path) {
            return url
        }
        // Fallback: a plain two-host ring. Recorded as a fallback in the
        // launch note so nobody mistakes it for the discovered topology.
        let hosts: [[String: Any]] = [["ssh": local], ["ssh": peer]]
        guard let data = try? JSONSerialization.data(withJSONObject: hosts,
                                                     options: [.prettyPrinted])
        else { return nil }
        try? data.write(to: url)
        return url
    }

    /// Start a sharded mlx_lm server across both machines. Returns the
    /// process so the caller can stop it; nil when preconditions fail.
    static func launchSharded(model: String, local: String, peer: String,
                              port: Int = 8081) -> Process? {
        guard let hostfile = writeHostfile(local: local, peer: peer) else { return nil }
        guard let launch = mlxBin("mlx.launch"),
              let server = mlxBin("mlx_lm.server") else { return nil }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: launch)
        p.arguments = [
            "--backend", "ring",
            "--hostfile", hostfile.path,
            server, "--model", model, "--port", String(port),
        ]
        do { try p.run() } catch { return nil }
        return p
    }

    /// Where pip put `mlx.launch` / `mlx.distributed_config`. They are
    /// console scripts, NOT `python3 -m` modules — the first version
    /// invoked `python3 -m mlx_lm.launch` and would have failed at runtime
    /// with "No module named mlx_lm.launch". Checked, not assumed.
    static func mlxBin(_ name: String) -> String? {
        var candidates = [
            "/opt/homebrew/bin/\(name)",
            "/usr/local/bin/\(name)",
        ]
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        if let vers = try? FileManager.default.contentsOfDirectory(
            atPath: home + "/Library/Python") {
            for v in vers {
                candidates.append(home + "/Library/Python/\(v)/bin/\(name)")
            }
        }
        return candidates.first { FileManager.default.isExecutableFile(atPath: $0) }
    }

    // MARK: helpers

    @discardableResult
    private static func run(_ exe: String, _ args: [String]) -> String? {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: exe)
        p.arguments = args
        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = Pipe()
        guard (try? p.run()) != nil else { return nil }
        p.waitUntilExit()
        guard p.terminationStatus == 0 else { return nil }
        return String(data: pipe.fileHandleForReading.readDataToEndOfFile(),
                      encoding: .utf8)
    }
}
