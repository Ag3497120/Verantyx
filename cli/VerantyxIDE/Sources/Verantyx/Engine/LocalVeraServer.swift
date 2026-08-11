import Foundation

// The engine, started natively, because the IDE is native.
//
// The web build boots CPython in the tab and downloads ~46MB to do it —
// necessary on verantyx.ai, where there is no process to talk to. Inside
// this app that is all wasted: a Mac that can run Xcode can run
// `python3 -m verantyx.serve_view3d`, and doing so is strictly better in
// four ways the browser path cannot match:
//
//   * no download, no boot button — the page opens already answering
//   * the FULL artifact (144MB vera.db, every facet) instead of the
//     24-facet browser cut, so Yes/No stops falling back to NOT_ATTESTED
//   * SSE: the staircase's rungs, the answering core's real cross, and
//     new nodes stream as they happen — the browser build has no such
//     channel because there is no server to open it
//   * ~30ms answers against seconds
//
// So the audit screen starts this on appear and points the WKWebView at
// it. The button the web page needs is exactly the thing a native host
// should not have.

@MainActor
final class LocalVeraServer: ObservableObject {
    static let shared = LocalVeraServer()

    enum State: Equatable {
        case idle
        case starting
        case ready(port: Int)
        case failed(String)
    }

    @Published private(set) var state: State = .idle
    @Published private(set) var log: String = ""

    private var proc: Process?
    private let port = 8794

    var url: URL? {
        if case .ready(let p) = state {
            return URL(string: "http://127.0.0.1:\(p)/vera3d.html")
        }
        return nil
    }

    /// Where the engine and its viewer live. Both are needed: the module
    /// is the engine, `--page` is the directory holding vera3d.html and
    /// view3d.json. Checked rather than assumed — a missing checkout is
    /// reported as such instead of a server that starts and 404s.
    static func repoPath() -> String {
        let saved = UserDefaults.standard.string(forKey: "vera.repoPath")
        if let saved, FileManager.default.fileExists(
            atPath: saved + "/verantyx/serve_view3d.py") { return saved }
        let guess = NSString(string: "~/Projects/Verantyx-Vera-alpha")
            .expandingTildeInPath
        return guess
    }

    static func corpusPath() -> String {
        let saved = UserDefaults.standard.string(forKey: "vera.corpusPath")
        if let saved, !saved.isEmpty { return saved }
        return NSString(string: "~/Projects/vera-corpus").expandingTildeInPath
    }

    func start() {
        guard case .idle = state else { return }
        let repo = Self.repoPath()
        let corpus = Self.corpusPath()
        guard FileManager.default.fileExists(
                atPath: repo + "/verantyx/serve_view3d.py") else {
            state = .failed(L("Engine checkout not found at \(repo)",
                              "エンジンのチェックアウトが \(repo) にありません"))
            return
        }
        guard FileManager.default.fileExists(
                atPath: corpus + "/build/vera.db") else {
            state = .failed(L("No built artifact at \(corpus)/build/vera.db",
                              "\(corpus)/build/vera.db がありません"))
            return
        }
        state = .starting
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        p.arguments = ["python3", "-m", "verantyx.serve_view3d",
                       "--root", corpus, "--page", repo + "/viewer",
                       "--port", String(port)]
        p.currentDirectoryURL = URL(fileURLWithPath: repo)
        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = pipe
        pipe.fileHandleForReading.readabilityHandler = { [weak self] h in
            let d = h.availableData
            guard !d.isEmpty, let s = String(data: d, encoding: .utf8) else { return }
            Task { @MainActor in
                self?.log = String((self?.log ?? "" + s).suffix(4000)) + s
            }
        }
        do { try p.run() } catch {
            state = .failed(error.localizedDescription)
            return
        }
        proc = p
        // The federation takes a few seconds to load; poll rather than
        // guess, so the page is pointed at a server that answers.
        Task { await waitReady() }
    }

    private func waitReady() async {
        let probe = URL(string: "http://127.0.0.1:\(port)/vera3d.html")!
        for _ in 0..<40 {
            if let (_, resp) = try? await URLSession.shared.data(from: probe),
               (resp as? HTTPURLResponse)?.statusCode == 200 {
                state = .ready(port: port)
                return
            }
            try? await Task.sleep(nanoseconds: 500_000_000)
        }
        state = .failed(L("Engine did not answer in 20s — see the log.",
                          "20秒待っても応答しません — ログを確認してください。"))
    }

    func stop() {
        proc?.terminate()
        proc = nil
        state = .idle
    }
}
