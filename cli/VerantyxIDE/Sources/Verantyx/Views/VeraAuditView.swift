import SwiftUI
import WebKit

// Vera-a audit screen — the mode's whole new body (Milestone U).
//
// The previous Vera-a layout was a chat about the engine; this is the
// ENGINE ITSELF, twice over: the exact page published at
// https://verantyx.ai/vera3d/ running live in a WKWebView (run side), and
// the same page's source checked out from verantyx-v6, editable and
// publishable by git push (edit side). One screen, both directions —
// an audit surface in the literal sense: what the world sees, and the
// lever that changes it, with nothing in between.
//
// Gap resolution rides the page's own governed flow: the demand list
// (refused subjects, ranked by how many people asked) loads each subject
// into the page, whose offer → preview → approve pipeline does the actual
// ingestion. The IDE adds no second ingestion path — a second path is how
// two readers of one corpus begin to disagree.
//
// Contributor permission is GitHub permission: publish is `git push` to
// verantyx-v6, so whoever the owner adds as a collaborator can publish,
// and nobody else can. No parallel auth system to get wrong.

// MARK: - Web view wrapper

/// What the 3D is currently saying. The right-hand panels read this and
/// nothing else, so the picture and the panels cannot disagree — they are
/// the same signal rendered twice, once as geometry and once as text.
@MainActor
final class VeraSignals: ObservableObject {
    @Published var verdict: String = ""
    @Published var core: String = ""
    @Published var path: String = ""
    @Published var tier: String = ""
    @Published var grain: String = ""
    @Published var witnesses: String = ""
    @Published var order: String = ""
    @Published var faces: Int = 0
    @Published var edges: Int = 0
    @Published var rungs: [(String, String)] = []
    @Published var grownCount: Int = 0
    @Published var lastGrown: String = ""
    @Published var selectedGap: String = ""
    @Published var editClickStamp: Int = 0
    @Published var trace: [String] = []

    func apply(_ m: [String: Any]) {
        let type = m["type"] as? String ?? ""
        switch type {
        case "ask":
            rungs = []; faces = 0; edges = 0
            note(AppLanguage.shared.t("ask ", "問 ") + (m["query"] as? String ?? ""))
        case "reading":
            let name = m["setting"] as? String ?? ""
            let v = m["verdict"] as? String ?? ""
            let item = m["item"] as? String ?? "—"
            rungs.append((name, v.hasPrefix("ANSWER") ? item : "—"))
        case "cross":
            faces = (m["faces"] as? [String])?.count ?? 0
            edges = (m["edges"] as? [Any])?.count ?? 0
            order = m["order"] as? String ?? ""
        case "verdict":
            verdict = m["verdict"] as? String ?? ""
            core = m["item"] as? String ?? ""
            path = m["path"] as? String ?? ""
            if let t = m["tier"] as? [String: Any] {
                tier = (t["label"] as? String ?? "")
                    + " (" + ((t["why"] as? [String])?.joined(separator: ", ") ?? "") + ")"
            } else { tier = "" }
            if let g = m["grain"] as? [String: Any],
               let a = g["agree"], let o = g["of"] {
                grain = "\(a)/\(o)"
            } else { grain = "" }
            if let w = m["witness"] as? [String: Any],
               let a = w["agree"], let n = w["answered"] {
                witnesses = "\(a)/\(n)"
            } else { witnesses = "" }
            note(verdict + " " + core)
        case "grown":
            grownCount += (m["count"] as? Int ?? 0)
            lastGrown = m["subject"] as? String ?? ""
            note(AppLanguage.shared.t("grown ", "成長 ") + lastGrown + " +" + String(m["count"] as? Int ?? 0))
        case "gap_click":
            selectedGap = m["subject"] as? String ?? ""
            note(AppLanguage.shared.t("gap selected ", "欠落を選択 ") + selectedGap)
        case "edit_click":
            editClickStamp += 1
            note(AppLanguage.shared.t("edit & publish opened", "編集と公開を確認"))
        case "grow_offer":
            note(AppLanguage.shared.t("offer ", "提案 ") + (m["subject"] as? String ?? ""))
        default:
            break
        }
    }

    private func note(_ s: String) {
        trace.insert(s, at: 0)
        if trace.count > 40 { trace.removeLast() }
    }
}

private struct AuditWebView: NSViewRepresentable {
    @Binding var request: AuditWebRequest
    /// JS evaluated into the page whenever the stamp moves — how the host
    /// paints the gap/edit overlay onto a viewer it does not control.
    @Binding var overlay: OverlayRequest
    var signals: VeraSignals

    func makeNSView(context: Context) -> WKWebView {
        let cfg = WKWebViewConfiguration()
        // The page posts every SSE event here; without the handler the
        // page's `toHost` is a no-op and it runs standalone, which is what
        // verantyx.ai does.
        cfg.userContentController.add(context.coordinator, name: "veraSignal")
        let v = WKWebView(frame: .zero, configuration: cfg)
        v.navigationDelegate = context.coordinator
        v.load(URLRequest(url: request.url))
        context.coordinator.lastStamp = request.stamp
        return v
    }

    func updateNSView(_ v: WKWebView, context: Context) {
        if context.coordinator.lastOverlayStamp != overlay.stamp {
            context.coordinator.lastOverlayStamp = overlay.stamp
            context.coordinator.pendingJS = overlay.js
            v.evaluateJavaScript(overlay.js, completionHandler: nil)
        }
        guard context.coordinator.lastStamp != request.stamp else { return }
        context.coordinator.lastStamp = request.stamp
        if let html = request.html {
            v.loadHTMLString(html, baseURL: request.url)
        } else {
            v.load(URLRequest(url: request.url))
        }
    }

    func makeCoordinator() -> Coord { Coord(signals: signals) }

    final class Coord: NSObject, WKScriptMessageHandler, WKNavigationDelegate {
        var lastStamp = 0
        var lastOverlayStamp = 0
        /// Last overlay JS, re-run on every page load — the prod-site
        /// fallback never fires the engine-ready hook, which is why the
        /// page stayed Japanese while the app was English.
        var pendingJS = ""

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            if !pendingJS.isEmpty { webView.evaluateJavaScript(pendingJS, completionHandler: nil) }
        }
        let signals: VeraSignals
        init(signals: VeraSignals) { self.signals = signals }

        func userContentController(_ c: WKUserContentController,
                                   didReceive message: WKScriptMessage) {
            guard let body = message.body as? [String: Any] else { return }
            Task { @MainActor in self.signals.apply(body) }
        }
    }
}

private struct AuditWebRequest {
    var url: URL
    var html: String? = nil
    var stamp: Int = 0
}

private struct OverlayRequest {
    var js: String = ""
    var stamp: Int = 0
}

// MARK: - Demand row

private struct DemandRow: Identifiable, Decodable {
    var id: String { subject }
    let subject: String
    let count: Int
}

private struct DemandReply: Decodable {
    let ok: Bool
    let demand: [DemandRow]?
}

// MARK: - The audit screen

struct VeraAuditView: View {
    @EnvironmentObject var app: AppState

    @StateObject private var engine = LocalVeraServer.shared
    @StateObject private var sig = VeraSignals()
    @State private var showSettings = false
    @ObservedObject private var pipeCoordinator = PipeCoordinator.shared
    @StateObject private var agent = VeraAAgent()
    @State private var chatInput = ""
    @State private var overlay = OverlayRequest()
    @State private var loadedJGen: String?
    @State private var web = AuditWebRequest(
        url: URL(string: "https://verantyx.ai/vera3d/")!)
    @State private var demand: [DemandRow] = []
    @State private var repoPath =
        NSString(string: "~/Projects/verantyx-v6").expandingTildeInPath
    @State private var memory = AuditMemory.load(task: AppState.shared?.veraMemoryTask ?? "verantyx-ai-vera3d")

    /// The audit screen's right panel is the one home for Vera-adjacent
    /// surfaces: the agent chat, growth, and MCP moved here from the
    /// activity bar / feature dock (which used to duplicate them).
    private enum RightTab: String, CaseIterable, Identifiable {
        case chat, growth, mcp
        var id: String { rawValue }
        @MainActor func title(_ app: AppState) -> String {
            switch self {
            case .chat:   return app.t("Chat", "チャット")
            case .growth: return app.t("Growth", "成長")
            case .mcp:    return "MCP"
            }
        }
    }
    @State private var rightTab: RightTab = .chat

    var body: some View {
        HStack(spacing: 0) {
            // Run side — the published page, live. The 3D is the agent's
            // shared blackboard: gap clicks and signals land in the chat.
            VStack(spacing: 0) {
                HStack(spacing: 8) {
                    Circle()
                        .fill(engineColor).frame(width: 7, height: 7)
                    Text(engineLabel).font(.system(size: 11, weight: .semibold))
                    Spacer()
                    // Settings is the only header control left. 2台/ローカル
                    // moved into the chat panel's toggle (configured in
                    // Settings, only switched here), and Exit went away —
                    // leaving the mode uses the same Vera-a/Gatekeeper chip
                    // that entered it, so there is exactly one way through
                    // the door in both directions.
                    if case .failed = engine.state {
                        // The failure names a path; Settings → Vera engine
                        // paths is where to answer it, and this retries with
                        // whatever was just saved.
                        Button(app.t("Retry engine", "エンジン再試行")) { engine.restart() }
                            .font(.system(size: 10))
                    }
                    Button { showSettings = true } label: {
                        Image(systemName: "gearshape")
                    }
                    .font(.system(size: 10))
                }
                .padding(.horizontal, 10).padding(.vertical, 6)
                Divider().opacity(0.3)
                AuditWebView(request: $web, overlay: $overlay, signals: sig)
            }
            .frame(minWidth: 480, maxWidth: .infinity)

            Divider().opacity(0.3)

            VStack(spacing: 0) {
                HStack(spacing: 4) {
                    ForEach(RightTab.allCases) { tab in
                        Button { rightTab = tab } label: {
                            Text(tab.title(app))
                                .font(.system(size: 10, weight: rightTab == tab ? .bold : .regular))
                                .foregroundStyle(rightTab == tab ? Color.white
                                                 : Color(red: 0.55, green: 0.55, blue: 0.65))
                                .padding(.horizontal, 8).padding(.vertical, 3)
                                .background(RoundedRectangle(cornerRadius: 4)
                                    .fill(rightTab == tab ? Color.white.opacity(0.08) : .clear))
                        }
                        .buttonStyle(.plain)
                    }
                    Spacer()
                }
                .padding(.horizontal, 8).padding(.vertical, 4)
                Divider().opacity(0.25)
                switch rightTab {
                case .chat:   chatPanel
                case .growth: GrowthDashboardView()
                case .mcp:    MCPView().environmentObject(app)
                }
            }
            .frame(width: 400)
            .background(Color(red: 0.11, green: 0.11, blue: 0.14))
        }
        .task {
            await refreshDemand()
            refreshOverlay()   // language + boot-button sync, even on prod fallback
            engine.start()
            await agent.refreshIssues()
        }
        .onChange(of: engine.state) { st in
            if case .ready = st, let u = engine.url {
                web = AuditWebRequest(url: u, stamp: web.stamp + 1)
                // The overlay is injected DOM, so a page (re)load wipes it.
                // Repaint once the fresh document has had time to exist.
                Task {
                    try? await Task.sleep(nanoseconds: 2_500_000_000)
                    refreshOverlay()
                }
            }
            // The live-site fallback path never repainted: the .task ran
            // refreshOverlay before the page existed, and no later state
            // change retriggered it — so the page kept its own language
            // and its own boot button, looking like "the sync is broken".
            // Repaint on failure too, twice (load timing varies).
            if case .failed = st {
                Task {
                    try? await Task.sleep(nanoseconds: 1_500_000_000)
                    refreshOverlay()
                    try? await Task.sleep(nanoseconds: 4_000_000_000)
                    refreshOverlay()
                }
            }
        }
        .onChange(of: demand.map(\.subject)) { _ in refreshOverlay() }
        .onChange(of: sig.editClickStamp) { _ in
            chatInput = app.t("What is unpublished or dirty in the vera3d page repo, and what should ship?",
                              "vera3dリポジトリの未公開・未コミットは何で、何を公開すべき?")
        }
        .onChange(of: sig.selectedGap) { gap in
            // A click in the 3D lands in the input, ready to be edited or
            // sent — the picture proposes, the human phrases.
            guard !gap.isEmpty else { return }
            chatInput = app.t("Gap: \(gap) — what would resolving it take?",
                              "欠落「\(gap)」— 解消するには何が必要?")
        }
        .sheet(isPresented: $showSettings) {
            // SettingsView closes through `onDismiss`, not through
            // @Environment(\.dismiss) — a sheet whose buttons are wired to
            // an optional callback is trapped when the callback is nil.
            SettingsView(onDismiss: { showSettings = false })
                .environmentObject(app)
                .frame(minWidth: 720, minHeight: 520)
        }
    }

    /// Paints the audit items INTO the 3D page: top gaps and the
    /// edit/publish door, as clickable rows in a corner overlay. The viewer
    /// ships unmodified — this is host-injected DOM, and clicks come back
    /// through the same veraSignal bridge the page already uses.
    private func refreshOverlay() {
        // The page follows the IDE, not its own chips: same language switch
        // as every other surface, and no browser boot button — the engine
        // is native here, there is nothing to download.
        let wantEn = !AppLanguage.shared.isJapanese
        let localReady: Bool = { if case .ready = engine.state { return true }; return false }()
        let syncJS = """
        (function(){
          try {
            if (typeof LANGUI !== 'undefined' && LANGUI !== '\(wantEn ? "en" : "ja")') {
              var b = document.getElementById('b-lang'); if (b) b.click();
            }
            if (b = document.getElementById('b-lang')) b.style.display = 'none';
            \(localReady ? """
            // Local engine answers — the page's own browser-engine boot is
            // dead weight, hide it.
            ['b-boot'].forEach(function(id){
              var el = document.getElementById(id); if (el) el.style.display='none';
            });
            document.querySelectorAll('button').forEach(function(el){
              if (/起動\\s*\\(~?45MB\\)|Boot\\s*\\(~?45MB\\)/.test(el.textContent)) el.style.display='none';
            });
            """ : """
            // No local engine on this Mac (no dev checkout — the released
            // IDE cannot assume one). Boot the page's own in-browser engine
            // automatically so the screen still fully starts; the flag keeps
            // repeated repaints from clicking it again.
            if (!window.__vxAutoBooted) {
              var bb = document.getElementById('b-boot');
              if (!bb) {
                document.querySelectorAll('button').forEach(function(el){
                  if (/起動\\s*\\(~?45MB\\)|Boot\\s*\\(~?45MB\\)/.test(el.textContent)) bb = el;
                });
              }
              if (bb) { window.__vxAutoBooted = true; bb.click(); bb.style.display='none'; }
            }
            """)
          } catch (e) {}
        })();
        """
        paintAuditOverlay(prefix: syncJS)
    }

    private func paintAuditOverlay(prefix: String = "") {
        let gapRows = demand.prefix(3).map { d in
            "{t:'gap',s:'\(Self.jsEscape(d.subject))',l:'\(Self.jsEscape(app.t("gap", "欠落"))) \(Self.jsEscape(d.subject)) ×\(d.count)'}"
        }.joined(separator: ",")
        let js = """
        (function(){
          var host = document.getElementById('vx-audit-overlay');
          if (!host) {
            host = document.createElement('div');
            host.id = 'vx-audit-overlay';
            host.style.cssText = 'position:fixed;left:10px;bottom:10px;z-index:9999;font:10px -apple-system;display:flex;flex-direction:column;gap:4px;max-width:240px';
            document.body.appendChild(host);
          }
          var items = [\(gapRows)\(gapRows.isEmpty ? "" : ",")
                       {t:'edit',s:'',l:'\(Self.jsEscape(app.t("edit & publish", "編集と公開を確認")))'}];
          host.innerHTML = '';
          items.forEach(function(it){
            var b = document.createElement('div');
            b.textContent = it.l;
            b.style.cssText = 'background:rgba(20,20,28,.85);color:'+(it.t==='gap'?'#f0a050':'#50c878')+';padding:4px 8px;border-radius:6px;cursor:pointer;border:1px solid rgba(255,255,255,.12)';
            b.onclick = function(){
              window.webkit && window.webkit.messageHandlers.veraSignal.postMessage(
                it.t==='gap' ? {type:'gap_click', subject: it.s} : {type:'edit_click'});
            };
            host.appendChild(b);
          });
        })();
        """
        overlay = OverlayRequest(js: prefix + "\n" + js, stamp: overlay.stamp + 1)
    }

    private static func jsEscape(_ s: String) -> String {
        s.replacingOccurrences(of: "\\", with: "\\\\")
         .replacingOccurrences(of: "'", with: "\\'")
         .replacingOccurrences(of: "\n", with: " ")
    }

    // MARK: - The chat panel (the whole right side)

    @ViewBuilder
    private var chatPanel: some View {
        VStack(spacing: 0) {
            chatToolbar
            Divider().opacity(0.2)
            signalStrip
            Divider().opacity(0.2)
            contextChips
            Divider().opacity(0.2)

            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 10) {
                        if agent.messages.isEmpty {
                            Text(app.t(
                                "This agent answers every message through the lens of what Vera is missing: gaps to resolve, edits to publish, memory worth keeping. Even a plain hello comes back as \"here is what needs fixing\".",
                                "このエージェントは全ての発言を「Veraに何が足りないか」の観点で返します。欠落の解消・編集と公開・残すべき記憶。ただの挨拶にも「今必要な直しはこれ」と返ります。"))
                                .font(.system(size: 11)).foregroundStyle(.tertiary)
                                .padding(10)
                        }
                        ForEach(agent.messages) { m in
                            chatBubble(m)
                                .id(m.id)
                        }
                        if agent.busy {
                            HStack(spacing: 6) {
                                ProgressView().controlSize(.small)
                                Text(agent.phase).font(.system(size: 10)).foregroundStyle(.tertiary)
                            }
                            .padding(.horizontal, 10)
                        }
                    }
                    .padding(.vertical, 8)
                }
                .onChange(of: agent.messages.count) { _ in
                    if let last = agent.messages.last {
                        withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
                    }
                }
            }

            Divider().opacity(0.2)
            chatInputBar
        }
    }

    /// Mode chip + model picker + the 2-Mac toggle. The same shape as the
    /// Gatekeeper bar, with less in it.
    private var chatToolbar: some View {
        HStack(spacing: 8) {
            // The same chip that entered this mode leaves it — identical
            // gesture to the Gatekeeper/Vera-a chip in the model bar.
            Button {
                app.isVeraAMode.toggle()
            } label: {
                Text("Vera-a")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(Color.purple)
                    .padding(.horizontal, 6).padding(.vertical, 4)
                    .background(Color.purple.opacity(0.1))
                    .cornerRadius(4)
            }
            .buttonStyle(.plain)
            .help(app.t("Back to Gatekeeper mode", "ゲートキーパーモードへ戻る"))

            // JGEN only, by design: the agent's memory injection rides the
            // hidden-state engine, and an Ollama model would silently get a
            // memoryless variant of the same conversation.
            Menu {
                ForEach(jgenModels, id: \.self) { name in
                    Button {
                        loadJGen(name)
                    } label: {
                        if loadedJGen == name { Label(name, systemImage: "checkmark") }
                        else { Text(name) }
                    }
                }
                if jgenModels.isEmpty {
                    Text(app.t("No converted JGEN models — Settings → JGEN",
                               "変換済みJGENなし — 設定 → JGEN"))
                }
            } label: {
                HStack(spacing: 4) {
                    Circle().fill(loadedJGen == nil ? Color.gray : Color.green)
                        .frame(width: 5, height: 5)
                    Text(loadedJGen ?? app.t("Choose model", "モデル選択"))
                        .font(.system(size: 10, design: .monospaced))
                        .lineLimit(1).truncationMode(.middle)
                }
            }
            .menuStyle(.borderlessButton)
            .frame(maxWidth: 150)

            Spacer()

            // ON/OFF only. The pairing, the roles and the split all live in
            // Settings; a toggle that could half-reconfigure a two-machine
            // topology from a chat toolbar is how machines end up swapping.
            Toggle(isOn: Binding(
                get: { pipeCoordinator.isEnabled },
                set: { on in
                    Task { if on { await pipeCoordinator.enable() } else { pipeCoordinator.disable() } }
                }
            )) {
                Text(app.t("2-Mac", "2台"))
                    .font(.system(size: 10))
            }
            .toggleStyle(.switch)
            .controlSize(.mini)
            .help(app.t("Runs with the pairing configured in Settings. Configure there; only switch here.",
                        "設定で構成済みのペアリングで動きます。構成は設定でのみ、ここではON/OFFだけ。"))
        }
        .padding(.horizontal, 10).padding(.vertical, 6)
    }

    /// One line of what the 3D is saying right now.
    private var signalStrip: some View {
        HStack(spacing: 10) {
            if !sig.verdict.isEmpty {
                Text(sig.verdict).font(.system(size: 9, weight: .semibold, design: .monospaced))
                    .foregroundStyle(sig.verdict.hasPrefix("ANSWER") ? Color.green : Color.orange)
                Text(sig.core).font(.system(size: 9, design: .monospaced))
            } else {
                Text(app.t("3D signals appear here", "3Dの信号がここに出ます"))
                    .font(.system(size: 9)).foregroundStyle(.quaternary)
            }
            Spacer()
            if sig.faces > 0 { Text(app.t("faces \(sig.faces) edges \(sig.edges)", "面\(sig.faces) 辺\(sig.edges)")).font(.system(size: 9, design: .monospaced)).foregroundStyle(.tertiary) }
            if !sig.grain.isEmpty { Text(app.t("grain \(sig.grain)", "粒\(sig.grain)")).font(.system(size: 9, design: .monospaced)).foregroundStyle(.tertiary) }
        }
        .padding(.horizontal, 10).padding(.vertical, 4)
    }

    /// What the agent currently knows about — each chip is clickable and
    /// drops a ready-to-edit question into the input.
    private var contextChips: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                ForEach(demand.prefix(4)) { d in
                    chip(app.t("gap \(d.subject) ×\(d.count)", "欠落 \(d.subject) ×\(d.count)"), color: .orange) {
                        chatInput = app.t("Gap: \(d.subject) (asked \(d.count)×) — plan the fix.",
                                          "欠落「\(d.subject)」(要望\(d.count)件) — 解消の段取りを。")
                    }
                }
                chip("issues \(agent.issues.count)", color: .blue) {
                    chatInput = app.t("Summarize the open vera-suggest issues and what each needs.",
                                      "openのvera-suggest issueを要約し、それぞれ何が必要か。")
                }
                chip(app.t("memory \(memory.entries.count)", "記憶 \(memory.entries.count)"), color: .purple) {
                    chatInput = app.t("What has this task remembered, and what is missing from memory?",
                                      "このタスクの記憶には何があり、何が欠けている?")
                }
                chip(app.t("edit/publish", "編集と公開"), color: .green) {
                    chatInput = app.t("What is unpublished or dirty in the vera3d page repo right now?",
                                      "vera3dページのリポジトリで未公開・未コミットのものは?")
                }
            }
            .padding(.horizontal, 10).padding(.vertical, 5)
        }
    }

    private func chip(_ label: String, color: Color, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(label)
                .font(.system(size: 9))
                .padding(.horizontal, 7).padding(.vertical, 3)
                .background(Capsule().fill(color.opacity(0.15)))
                .foregroundStyle(color)
                .lineLimit(1)
        }
        .buttonStyle(.plain)
    }

    /// Same conventions as the main transcript: the human's words sit in a
    /// right-aligned enclosure, the agent's answer occupies the column, and
    /// every message is selectable and has a working copy control.
    @ViewBuilder
    private func chatBubble(_ m: VeraAAgent.Message) -> some View {
        if m.role == .user {
            HStack(alignment: .bottom, spacing: 4) {
                Spacer(minLength: 50)
                copyButton(m.text)
                VStack(alignment: .trailing, spacing: 3) {
                    Text(app.t("You", "あなた"))
                        .font(.system(size: 8, weight: .bold)).foregroundStyle(Color.blue)
                    Text(m.text)
                        .font(.system(size: 11.5))
                        .textSelection(.enabled)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(8)
                .background(RoundedRectangle(cornerRadius: 10).fill(Color.blue.opacity(0.14)))
            }
            .padding(.horizontal, 8)
        } else {
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 6) {
                    Text("Vera-a")
                        .font(.system(size: 8, weight: .bold)).foregroundStyle(Color.purple)
                    copyButton(m.text)
                }
                Text(m.text)
                    .font(.system(size: 11.5))
                    .textSelection(.enabled)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(8)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 8)
        }
    }

    private func copyButton(_ text: String) -> some View {
        Button {
            NSPasteboard.general.clearContents()
            NSPasteboard.general.setString(text, forType: .string)
        } label: {
            Image(systemName: "doc.on.doc")
                .font(.system(size: 9))
                .foregroundStyle(Color.gray.opacity(0.7))
        }
        .buttonStyle(.plain)
        .help(app.t("Copy", "コピー"))
    }

    private var chatInputBar: some View {
        HStack(alignment: .bottom, spacing: 6) {
            TextField(app.t("Ask, or click a gap in the 3D…", "質問するか、3Dの欠落をクリック…"),
                      text: $chatInput, axis: .vertical)
                .textFieldStyle(.plain)
                .font(.system(size: 12))
                .lineLimit(1...5)
                .padding(8)
                .background(RoundedRectangle(cornerRadius: 8).fill(Color.white.opacity(0.05)))
                .onSubmit { sendChat() }
            Button {
                sendChat()
            } label: {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.system(size: 22))
                    .foregroundStyle(canSend ? Color.purple : Color.gray.opacity(0.5))
            }
            .buttonStyle(.plain)
            .disabled(!canSend)
        }
        .padding(8)
    }

    private var canSend: Bool {
        !chatInput.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !agent.busy && loadedJGen != nil
    }

    private var jgenModels: [String] {
        JGenConverter.shared.convertedModels.filter { JGenConverter.shared.isArchSupported($0) }
    }

    private func loadJGen(_ name: String) {
        Task {
            do {
                try await JCrossChatManager.shared.load(modelFileName: name)
                loadedJGen = name
                app.modelStatus = .jcrossReady(model: name)
            } catch {
                agent.append(.assistant, app.t("Could not load \(name): ", "\(name) を読み込めません: ")
                             + error.localizedDescription)
            }
        }
    }

    private func sendChat() {
        let text = chatInput.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !agent.busy else { return }
        chatInput = ""
        Task {
            await agent.send(text,
                             memory: memory,
                             demand: demand.map { ($0.subject, $0.count) },
                             selectedGap: sig.selectedGap,
                             signal: sig.verdict.isEmpty ? nil : "\(sig.verdict) \(sig.core)",
                             repoPath: repoPath)
            memory = AuditMemory.load(task: AppState.shared?.veraMemoryTask ?? "verantyx-ai-vera3d")
        }
    }

    /// What the picture is currently saying, above every tab — because the
    /// decision each tab asks for (approve this fetch? publish this edit?
    /// trust this answer?) is a decision about THIS, and reading it off the
    /// 3D by eye is not reading it.
    private var signalHeader: some View {
        VStack(alignment: .leading, spacing: 3) {
            if sig.verdict.isEmpty {
                Text(app.t("Ask something — the panels follow the 3D.",
                           "何か訊いてください — パネルは3Dに従います。"))
                    .font(.system(size: 10)).foregroundStyle(.secondary)
            } else {
                HStack(spacing: 6) {
                    Text(sig.verdict)
                        .font(.system(size: 10.5, weight: .semibold))
                        .foregroundStyle(sig.verdict.hasPrefix("UNKNOWN")
                                         ? Color.orange : Color.green)
                    if !sig.core.isEmpty {
                        Text(sig.core).font(.system(size: 11))
                    }
                    Spacer()
                    if sig.faces > 0 {
                        Text("面\(sig.faces)/辺\(sig.edges)")
                            .font(.system(size: 9.5, design: .monospaced))
                            .foregroundStyle(.secondary)
                    }
                }
                if !sig.path.isEmpty {
                    Text(sig.path).font(.system(size: 10))
                        .foregroundStyle(.secondary).lineLimit(2)
                }
                HStack(spacing: 8) {
                    if !sig.tier.isEmpty {
                        Text(app.t("confidence ", "確からしさ ") + sig.tier)
                            .foregroundStyle(sig.tier.hasPrefix("strong")
                                             ? Color.green
                                             : sig.tier.hasPrefix("weak")
                                               ? Color.secondary : Color.orange)
                    }
                    if !sig.grain.isEmpty { Text(app.t("grain ", "粒度 ") + sig.grain) }
                    if !sig.witnesses.isEmpty { Text(app.t("wit ", "合議 ") + sig.witnesses) }
                    if sig.order == "arbitrary" {
                        Text(app.t("unordered", "順不同")).foregroundStyle(.orange)
                    }
                }
                .font(.system(size: 9.5)).foregroundStyle(.secondary)
                if !sig.rungs.isEmpty {
                    // The staircase, rung by rung — the abstainers are the
                    // reason a 2/6 is not a failure, and seeing them is the
                    // only way that reads as evidence rather than as noise.
                    HStack(spacing: 4) {
                        ForEach(Array(sig.rungs.enumerated()), id: \.offset) { _, r in
                            Text(r.1 == "—" ? "·" : "●")
                                .foregroundStyle(r.1 == "—" ? Color.secondary
                                                            : Color.green)
                                .help("\(r.0): \(r.1)")
                        }
                        Text(app.t("rungs", "段")).foregroundStyle(.secondary)
                    }
                    .font(.system(size: 9))
                }
            }
        }
        .padding(.horizontal, 10).padding(.bottom, 6)
    }

    private var engineLabel: String {
        switch engine.state {
        case .idle:      return app.t("engine idle", "エンジン停止中")
        case .starting:  return app.t("engine starting…", "エンジン起動中…")
        case .ready:     return app.t("local engine — full artifact, live trace",
                                      "ローカルエンジン — 完全版・推論を実況")
        // A dev-checkout path in the header reads as a broken product.
        // The page auto-boots its in-browser engine in this state (see
        // refreshOverlay), so say what the reader actually has.
        case .failed: return app.t("live site — in-browser engine",
                                   "本番表示 — ブラウザ内エンジン")
        }
    }
    private var engineColor: Color {
        switch engine.state {
        case .ready: return .green
        case .starting: return .orange
        case .failed: return .secondary
        case .idle: return .secondary
        }
    }
    /// Whichever surface is currently live — so a "Resolve" click drives
    /// the page the reader is actually looking at, not a second one.
    private func webBase() -> String {
        if case .ready(let p) = engine.state {
            return "http://127.0.0.1:\(p)/vera3d.html"
        }
        return "https://verantyx.ai/vera3d/"
    }

    private func useLocal() {
        if let u = engine.url {
            web = AuditWebRequest(url: u, stamp: web.stamp + 1)
        } else {
            engine.start()
        }
    }

    private func refreshDemand() async {
        do {
            let (data, _) = try await URLSession.shared.data(
                from: URL(string: "https://verantyx.ai/api/vera/demand")!)
            let d = try JSONDecoder().decode(DemandReply.self, from: data)
            demand = d.demand ?? []
        } catch {
            // Unreachable inlet: the chips simply show nothing — the agent
            // says so in conversation when asked.
        }
    }
}

// MARK: - The Vera-a agent

/// The dedicated agent behind the Vera-a chat.
///
/// Its defining property is that it has no neutral gear: every reply —
/// including one to "こんにちは" — is framed as "here is what Vera currently
/// needs" (gaps to resolve, edits to publish, memory to keep). That framing
/// is enforced by the system prompt, and the material it reasons over is
/// assembled fresh for every call:
///
///   - eternal memory (AuditMemory) + the running conversation
///   - vector recall over indexed subjects (AuditVectorIndex)
///   - the live demand ranking and whatever gap is selected in the 3D
///   - the vera3d repo's unpublished state (git, read-only)
///   - open vera-suggest issues from GitHub (read; updating an issue is a
///     human act in this governance model, so the agent drafts, never posts)
///
/// The injection happens ONLY here — the same JGEN loaded in Gatekeeper mode
/// sees none of this. That is the point of it being a mode.
@MainActor
final class VeraAAgent: ObservableObject {

    /// The instance the normal chat's 単体 Vera-a segment uses, so both
    /// surfaces share issue caches and phrasing — one agent, two doors.
    static let engineShared = VeraAAgent()

    struct Message: Identifiable {
        enum Role { case user, assistant }
        let id = UUID()
        let role: Role
        let text: String
    }

    struct Issue: Identifiable {
        let id: Int
        let title: String
        let by: String
    }

    @Published private(set) var messages: [Message] = []
    @Published private(set) var busy = false
    @Published private(set) var phase = ""
    @Published private(set) var issues: [Issue] = []
    private var issuesFetchedAt: Date?

    func append(_ role: Message.Role, _ text: String) {
        messages.append(Message(role: role, text: text))
    }

    // MARK: Issues (read-only inlet, cached 5 minutes)

    func refreshIssues(force: Bool = false) async {
        if !force, let t = issuesFetchedAt, Date().timeIntervalSince(t) < 300 { return }
        guard let url = URL(string:
            "https://api.github.com/repos/Ag3497120/Verantyx-Vera-alpha/issues?state=open&labels=vera-suggest")
        else { return }
        var req = URLRequest(url: url)
        req.setValue("application/vnd.github+json", forHTTPHeaderField: "Accept")
        req.setValue("verantyx-ide vera-a", forHTTPHeaderField: "User-Agent")
        req.timeoutInterval = 15
        guard let (data, _) = try? await URLSession.shared.data(for: req),
              let arr = (try? JSONSerialization.jsonObject(with: data)) as? [[String: Any]]
        else { return }
        issues = arr.compactMap { it in
            guard let n = it["number"] as? Int else { return nil }
            return Issue(id: n,
                         title: (it["title"] as? String ?? "").replacingOccurrences(of: "[提案]", with: "").trimmingCharacters(in: .whitespaces),
                         by: (it["user"] as? [String: Any])?["login"] as? String ?? "")
        }
        issuesFetchedAt = Date()
    }

    // MARK: One turn

    func send(_ text: String,
              memory: AuditMemory,
              demand: [(String, Int)],
              selectedGap: String,
              signal: String?,
              repoPath: String) async {
        append(.user, text)
        busy = true
        defer { busy = false; phase = "" }
        let history = messages.suffix(12).map {
            (($0.role == .user ? "user" : "assistant"), $0.text)
        }
        let reply = await composeReply(text,
                                       veraVerdict: nil,
                                       memory: memory,
                                       demand: demand,
                                       selectedGap: selectedGap,
                                       signal: signal,
                                       repoPath: repoPath,
                                       history: history)
        append(.assistant, reply)
    }

    /// One engine turn under the audit framing, usable from anywhere.
    ///
    /// This is THE definition of what "Vera-a" answers like — the audit
    /// screen's send() and the normal chat's 単体 Vera-a segment both call
    /// it, so the two can no longer drift apart (they had: the segment was
    /// still a bare verdict-reader while the mode had grown memory, demand,
    /// issues and repo context).
    func composeReply(_ text: String,
                      veraVerdict: String?,
                      memory: AuditMemory? = nil,
                      demand demandIn: [(String, Int)]? = nil,
                      selectedGap: String = "",
                      signal: String? = nil,
                      repoPath: String = NSString(string: "~/Projects/verantyx-v6").expandingTildeInPath,
                      history: [(String, String)] = []) async -> String {
        phase = AppLanguage.shared.t("gathering context…", "文脈を集めています…")
        // Asked about memory → SHOW the memory, not just words about it.
        if text.contains("記憶") || text.lowercased().contains("memory") {
            AppState.shared?.aiShowMemory()
        }
        await refreshIssues()

        let mem = memory ?? AuditMemory.load(
            task: AppState.shared?.veraMemoryTask ?? "verantyx-ai-vera3d")
        var demand = demandIn ?? []
        if demandIn == nil {
            // Callers outside the audit screen have no demand list — fetch a
            // fresh one so the segment sees the same world the screen does.
            if let url = URL(string: "https://verantyx.ai/api/vera/demand"),
               let (data, _) = try? await URLSession.shared.data(from: url),
               let j = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let rows = j["demand"] as? [[String: Any]] {
                demand = rows.compactMap { r in
                    guard let s0 = r["subject"] as? String, let c = r["count"] as? Int
                    else { return nil }
                    return (s0, c)
                }
            }
        }

        let subjects = mem.entries.map(\.subject)
            + demand.map(\.0)
            + issues.map(\.title)
        _ = await AuditVectorIndex.shared.index(subjects: Array(Set(subjects)), preferJGen: false)
        let recall = await AuditVectorIndex.shared.nearest(to: text, limit: 6, preferJGen: false)
            .hits.map { String(format: "%@ (%.2f)", $0.subject, $0.score) }

        let gitState = Self.gitOneliner(repoPath: repoPath)

        var context: [String] = []
        let L = AppLanguage.shared
        if let veraVerdict {
            context.append(L.t("Vera's deterministic verdict for this question: ",
                               "この質問へのVera決定論判定: ") + veraVerdict)
        }
        if !demand.isEmpty {
            context.append(L.t("Unresolved gaps (by demand): ", "未解消の欠落(要望順): ")
                + demand.prefix(8).map { "\($0.0)×\($0.1)" }.joined(separator: ", "))
        }
        if !selectedGap.isEmpty { context.append(L.t("Gap selected in the 3D: ", "3Dで選択中の欠落: ") + selectedGap) }
        if let signal { context.append(L.t("Latest 3D verdict: ", "3Dの直近の判定: ") + signal) }
        if !issues.isEmpty {
            context.append("open issues (vera-suggest): "
                + issues.prefix(6).map { "#\($0.id) \($0.title) (@\($0.by))" }.joined(separator: " / "))
        }
        if !gitState.isEmpty { context.append(L.t("vera3d repo: ", "vera3dリポジトリ: ") + gitState) }
        if !mem.entries.isEmpty {
            let recent = mem.entries.suffix(5)
                .map { "[\($0.kind)] \($0.subject): \($0.detail)" }.joined(separator: "\n")
            context.append(L.t("Eternal memory (recent):\n", "永遠の記憶(直近):\n") + recent)
        }
        if !recall.isEmpty { context.append(L.t("Vector recall: ", "ベクトル想起: ") + recall.joined(separator: ", ")) }

        let ja = AppLanguage.shared.isJapanese
        let system = ja ? """
        あなたは Vera-a 監査エージェント。Vera(立体十字構造の知識エンジン)の欠落の解消・編集と公開・記憶の管理だけを目的とする。
        規則:
        1. どんな入力にも、現在の文脈(欠落・issue・未公開の編集・記憶)に結びつけて答える。挨拶や雑談にも「今必要な直し」を返す。
        2. 提案はするが実行はしない。取り込み・公開は人間が承認する。
        3. 知らないことは知らないと言う。文脈に無い事実を作らない。決定論判定があるときはそれを言い換えず先に活かす。
        4. 簡潔に。箇条書きを好む。必ず日本語で答える。

        現在の文脈:
        \(context.isEmpty ? "(文脈なし — まず欠落一覧の取得やモデルのロードを提案せよ)" : context.joined(separator: "\n"))
        """ : """
        You are the Vera-a audit agent. Your sole purpose is managing Vera (the stereo-cross knowledge engine): resolving gaps, editing & publishing, and keeping memory.
        Rules:
        1. Tie every reply to the current context (gaps, issues, unpublished edits, memory). Even a greeting gets "here is what needs fixing now".
        2. Propose, never execute. Ingestion and publishing are approved by a human.
        3. Say so when you do not know. Never invent facts absent from the context; when a deterministic verdict is present, honor it verbatim first.
        4. Be concise; prefer bullet points. Always answer in English.

        Current context:
        \(context.isEmpty ? "(no context — suggest fetching the gap list or loading a model first)" : context.joined(separator: "\n"))
        """

        var convo: [(role: String, content: String)] = [("system", system)]
        for (r, t) in history { convo.append((r, t)) }
        if history.last?.1 != text { convo.append(("user", text)) }

        phase = AppLanguage.shared.t("thinking (JGEN)…", "JGENで推論中…")
        do {
            let reply = try await JCrossChatManager.shared.generate(
                conversation: convo, maxTokens: 700)
            // A mid-thought turn now returns the reasoning itself (styled as
            // <think>), so empty means the model genuinely produced nothing.
            let final = reply.isEmpty
                ? AppLanguage.shared.t("(The model produced no output.)",
                                       "（モデルは何も出力しませんでした）")
                : reply
            var m2 = AuditMemory.load(task: AppState.shared?.veraMemoryTask ?? "verantyx-ai-vera3d")
            m2.remember(kind: "note", subject: String(text.prefix(40)),
                        detail: String(final.prefix(200)))
            m2.save()
            return final
        } catch {
            return AppLanguage.shared.t(
                "JGEN cannot answer: \(error.localizedDescription)\nLoad a JGEN model from the toolbar.",
                "JGENが応答できません: \(error.localizedDescription)\nモデルバーからJGENモデルをロードしてください。")
        }
    }

    /// "3 commits ahead, 2 files dirty" — enough for the agent to reason
    /// about publish state without shelling git per sentence.
    nonisolated private static func gitOneliner(repoPath: String) -> String {
        func git(_ args: [String]) -> String {
            let p = Process()
            p.executableURL = URL(fileURLWithPath: "/usr/bin/git")
            p.arguments = ["-C", repoPath] + args
            let pipe = Pipe(); p.standardOutput = pipe; p.standardError = Pipe()
            guard (try? p.run()) != nil else { return "" }
            p.waitUntilExit()
            return String(data: pipe.fileHandleForReading.readDataToEndOfFile(),
                          encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        }
        guard FileManager.default.fileExists(atPath: repoPath) else { return "" }
        let dirty = git(["status", "--porcelain"]).split(separator: "\n").count
        let ahead = git(["rev-list", "--count", "@{upstream}..HEAD"])
        var bits: [String] = []
        let L = AppLanguage.shared
        if dirty > 0 { bits.append(L.t("\(dirty) uncommitted", "未コミット\(dirty)件")) }
        if let n = Int(ahead), n > 0 { bits.append(L.t("\(n) unpushed commits", "未push \(n)コミット")) }
        return bits.isEmpty ? L.t("clean (matches published)", "クリーン(公開済みと一致)")
                            : bits.joined(separator: L.t(", ", "・"))
    }
}
