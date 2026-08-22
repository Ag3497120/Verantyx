import Foundation

// MARK: - BrowserSession
//
// Where the browsing actually IS, between turns.
//
// A real run searched for Zenn, opened it, and then — asked to log in on
// "the page currently open" — searched again from nothing, constructed
// `https://z/dev/` out of thin air, and walked into Safari's script block
// four times. The agent had no idea a page was already open, because
// nothing outlived the turn that opened it.
//
// This is that missing state: the page in front of the user, how it was
// reached, and what the last list of candidates was. It lives in vera-a's
// store (cortex.db) rather than in memory alone, so it survives a restart
// the way the rest of the memory does — and so "continue from where we
// are" is answerable by a query rather than by a guess.
//
// Deliberately small. It is not a history (act_episode already records
// what was done and why); it is the answer to one question: what is open
// right now?
@MainActor
final class BrowserSession: ObservableObject {
    static let shared = BrowserSession()

    struct State: Equatable {
        var url: String = ""
        var title: String = ""
        /// How far down the page the agent has scrolled, in wheel notches
        /// — enough to say "we are partway down", not a pixel offset.
        var scrollNotches: Int = 0
        /// The list the user was last asked to choose from, kept so a
        /// follow-up ("the second one") still has something to refer to.
        var candidates: [String] = []
        var updatedAt: Date = .distantPast

        var isOpen: Bool { !url.isEmpty }
    }

    @Published private(set) var state = State()

    private init() {
        Task { await restore() }
    }

    // MARK: - Mutation

    func opened(url: String, title: String) {
        state.url = url
        state.title = title
        state.scrollNotches = 0
        state.updatedAt = Date()
        persist()
    }

    func scrolled(by notches: Int) {
        guard state.isOpen else { return }
        state.scrollNotches += notches
        state.updatedAt = Date()
        persist()
    }

    func offered(candidates: [String]) {
        state.candidates = Array(candidates.prefix(12))
        state.updatedAt = Date()
        persist()
    }

    // ── URLs this session actually saw ───────────────────────────────
    // The difference between a destination that exists and one the model
    // assembled from a site name. `https://zenn.dev/login` looked
    // perfectly reasonable and was a 404; the agent had never seen it
    // anywhere, it just built it. Anything that arrived from a search
    // result, a verified-URL lookup, or a page the browser actually
    // reached is known; nothing else is.
    private var knownURLs = Set<String>()

    func register(urls: [String]) {
        for u in urls { knownURLs.insert(Self.key(u)) }
    }

    func isKnown(_ url: String) -> Bool {
        let k = Self.key(url)
        if knownURLs.contains(k) { return true }
        // The site you are already on is known by definition, including
        // its root — going "back to the top" is not an invention.
        guard state.isOpen, let host = URL(string: url)?.host,
              let openHost = URL(string: state.url)?.host else { return false }
        return host == openHost && (URL(string: url)?.path ?? "/") == "/"
    }

    private static func key(_ url: String) -> String {
        var u = url.lowercased()
        for p in ["https://", "http://"] where u.hasPrefix(p) { u = String(u.dropFirst(p.count)) }
        if u.hasPrefix("www.") { u = String(u.dropFirst(4)) }
        while u.hasSuffix("/") { u.removeLast() }
        return u
    }

    func closed() {
        state = State()
        persist()
    }

    // MARK: - Injection

    /// One block for the agent's context. Absent when nothing is open, so
    /// a fresh task is not told about a page that has nothing to do with
    /// it; stale sessions expire rather than misleading a later run.
    func contextBlock(maxAge: TimeInterval = 30 * 60) -> String {
        guard state.isOpen, Date().timeIntervalSince(state.updatedAt) < maxAge else { return "" }
        var lines = ["[BROWSER — already open, do NOT search or construct a URL to get here]",
                     "url: \(state.url)"]
        if !state.title.isEmpty { lines.append("title: \(state.title)") }
        if state.scrollNotches != 0 { lines.append("scrolled: \(state.scrollNotches) notches from the top") }
        if !state.candidates.isEmpty {
            lines.append("last offered: " + state.candidates.prefix(6).joined(separator: " / "))
        }
        lines.append("To act on this page use [CLICK_LINK: visible text] or [DESKTOP_ACT: scroll …]; "
                     + "[BROWSE] is for going somewhere new.")
        return lines.joined(separator: "\n")
    }

    // MARK: - Persistence

    private func persist() {
        let s = state
        Task {
            await EternalMemoryStore.shared.saveBrowserSession(
                url: s.url, title: s.title, scrollNotches: s.scrollNotches,
                candidates: s.candidates, updatedAt: s.updatedAt.timeIntervalSince1970)
        }
    }

    private func restore() async {
        guard let saved = await EternalMemoryStore.shared.loadBrowserSession() else { return }
        state = State(url: saved.url, title: saved.title,
                      scrollNotches: saved.scrollNotches, candidates: saved.candidates,
                      updatedAt: Date(timeIntervalSince1970: saved.updatedAt))
    }
}

// MARK: - URLPreflight
//
// Auto mode opens things without asking, so it has to look first.
//
// The check is a plain URLSession fetch — no browser, no JavaScript, no
// cookies, nothing the page can run — and it answers three questions the
// caller cannot answer from the URL text alone: does it resolve, does it
// end up on the host it claimed, and is it a page at all. That is a
// preflight, not a security guarantee: it cannot judge whether the
// content is trustworthy, and it says so rather than implying safety.
enum URLPreflight {

    enum Verdict: Equatable {
        case ok(finalURL: String)
        /// Refused before any fetch: not a web URL at all.
        case malformed(String)
        /// Landed somewhere other than where it said it was going.
        case redirectedOffHost(from: String, to: String)
        case notReachable(String)
        case notAPage(String)

        var allowsOpen: Bool { if case .ok = self { return true }; return false }

        var describedJP: String {
            switch self {
            case .ok(let u):                       return "事前検証OK: \(u)"
            case .malformed(let why):              return "URLとして不正: \(why)"
            case .redirectedOffHost(let f, let t): return "別ホストへ転送されました: \(f) → \(t)"
            case .notReachable(let why):           return "到達できません: \(why)"
            case .notAPage(let what):              return "ページではありません: \(what)"
            }
        }
        var describedEN: String {
            switch self {
            case .ok(let u):                       return "preflight ok: \(u)"
            case .malformed(let why):              return "not a usable URL: \(why)"
            case .redirectedOffHost(let f, let t): return "redirects off-host: \(f) → \(t)"
            case .notReachable(let why):           return "unreachable: \(why)"
            case .notAPage(let what):              return "not a page: \(what)"
            }
        }
    }

    static func check(_ urlString: String, timeout: TimeInterval = 8) async -> Verdict {
        guard let url = URL(string: urlString),
              let scheme = url.scheme?.lowercased(), scheme == "http" || scheme == "https",
              let host = url.host, host.contains("."), !host.hasSuffix(".")
        else {
            // This is the rule that would have stopped `https://z/dev/`
            // before Safari was ever asked to open it.
            return .malformed(urlString)
        }

        var request = URLRequest(url: url)
        request.timeoutInterval = timeout
        request.setValue("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Version/17.0 Safari/605.1.15",
                         forHTTPHeaderField: "User-Agent")
        guard let (data, response) = try? await URLSession.shared.data(for: request),
              let http = response as? HTTPURLResponse
        else { return .notReachable(urlString) }

        guard (200..<400).contains(http.statusCode) else {
            return .notReachable("HTTP \(http.statusCode)")
        }
        let finalHost = http.url?.host ?? host
        if !sameSite(host, finalHost) {
            return .redirectedOffHost(from: host, to: finalHost)
        }
        let type = (http.value(forHTTPHeaderField: "Content-Type") ?? "").lowercased()
        if !type.isEmpty, !type.contains("text/html"), !type.contains("text/plain"),
           !type.contains("application/xhtml") {
            return .notAPage(type)
        }
        if data.isEmpty { return .notAPage("empty response") }
        return .ok(finalURL: http.url?.absoluteString ?? urlString)
    }

    /// news.example.com and example.com are the same site; example.com and
    /// example-login.com are not, however similar they look.
    private static func sameSite(_ a: String, _ b: String) -> Bool {
        if a == b { return true }
        func registrable(_ host: String) -> String {
            let parts = host.lowercased().split(separator: ".")
            guard parts.count >= 2 else { return host.lowercased() }
            return parts.suffix(2).joined(separator: ".")
        }
        return registrable(a) == registrable(b)
    }
}
