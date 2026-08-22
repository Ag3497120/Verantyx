import SwiftUI
import WebKit

/// Resolves `Vendor/modules/<id>/index.html` from the app bundle (DMG path)
/// or a sibling Vendor folder during development.
enum WebModulePaths {
    static func indexHTML(moduleId: String) -> URL? {
        let file = "index.html"
        if let bundled = Bundle.main.resourceURL?
            .appendingPathComponent("modules", isDirectory: true)
            .appendingPathComponent(moduleId, isDirectory: true)
            .appendingPathComponent(file),
           FileManager.default.fileExists(atPath: bundled.path) {
            return bundled
        }
        // Dev fallback: Sources aren't copied; Vendor/ next to the project.
        if let exe = Bundle.main.executableURL {
            let candidates = [
                exe.deletingLastPathComponent() // MacOS
                    .deletingLastPathComponent() // Contents
                    .appendingPathComponent("Resources/modules/\(moduleId)/\(file)"),
            ]
            for c in candidates where FileManager.default.fileExists(atPath: c.path) {
                return c
            }
        }
        // Checkout Vendor (developer machine)
        let home = FileManager.default.homeDirectoryForCurrentUser
        let vendor = home
            .appendingPathComponent("Verantyx/cli/VerantyxIDE/Vendor/modules/\(moduleId)/\(file)")
        if FileManager.default.fileExists(atPath: vendor.path) { return vendor }
        return nil
    }
}

/// Thin WKWebView shell: loads a web module and routes `verantyx.invoke`
/// to CapabilityRegistry. Feature UI grows by adding modules, not Swift views.
struct WebModuleHost: NSViewRepresentable {
    let moduleId: String

    func makeCoordinator() -> Coordinator { Coordinator(moduleId: moduleId) }

    func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.userContentController.add(context.coordinator, name: "verantyx")
        let bridgeJS = """
        window.verantyx = {
          invoke: function(name, args) {
            return new Promise(function(resolve, reject) {
              var id = 'c' + Date.now() + '_' + Math.random().toString(36).slice(2);
              window.__vxPending = window.__vxPending || {};
              window.__vxPending[id] = { resolve: resolve, reject: reject };
              window.webkit.messageHandlers.verantyx.postMessage({
                id: id, name: name, args: args || {}
              });
            });
          },
          _settle: function(id, ok, payload) {
            var p = (window.__vxPending || {})[id];
            if (!p) return;
            delete window.__vxPending[id];
            if (ok) p.resolve(payload); else p.reject(payload);
          }
        };
        """
        let script = WKUserScript(source: bridgeJS, injectionTime: .atDocumentStart, forMainFrameOnly: true)
        config.userContentController.addUserScript(script)

        let webView = WKWebView(frame: .zero, configuration: config)
        webView.setValue(false, forKey: "drawsBackground")
        context.coordinator.webView = webView
        context.coordinator.load()
        return webView
    }

    func updateNSView(_ nsView: WKWebView, context: Context) {}

    final class Coordinator: NSObject, WKScriptMessageHandler {
        let moduleId: String
        weak var webView: WKWebView?

        init(moduleId: String) { self.moduleId = moduleId }

        func load() {
            guard let webView else { return }
            if let url = WebModulePaths.indexHTML(moduleId: moduleId) {
                let dir = url.deletingLastPathComponent()
                webView.loadFileURL(url, allowingReadAccessTo: dir)
            } else {
                let html = """
                <html><body style="font:13px -apple-system;background:#1a1a1f;color:#ccc;padding:16px">
                <p>Module “\(moduleId)” not found.</p>
                <p>Expected Vendor/modules/\(moduleId)/index.html (embedded as Resources/modules).</p>
                </body></html>
                """
                webView.loadHTMLString(html, baseURL: nil)
            }
        }

        func userContentController(_ userContentController: WKUserContentController,
                                   didReceive message: WKScriptMessage) {
            guard let body = message.body as? [String: Any],
                  let id = body["id"] as? String,
                  let name = body["name"] as? String else { return }
            let args = body["args"] as? [String: Any] ?? [:]
            Task { @MainActor in
                do {
                    let result = try await CapabilityRegistry.invoke(name, args: args)
                    settle(id: id, ok: true, payload: result)
                } catch {
                    settle(id: id, ok: false, payload: ["error": error.localizedDescription])
                }
            }
        }

        private func settle(id: String, ok: Bool, payload: [String: Any]) {
            guard let data = try? JSONSerialization.data(withJSONObject: payload) else { return }
            let b64 = data.base64EncodedString()
            let js = """
            (function(){
              try {
                var bin = atob('\(b64)');
                var bytes = new Uint8Array(bin.length);
                for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
                var json = new TextDecoder('utf-8').decode(bytes);
                window.verantyx._settle('\(id)', \(ok ? "true" : "false"), JSON.parse(json));
              } catch (e) {
                window.verantyx._settle('\(id)', false, {error: String(e)});
              }
            })();
            """
            webView?.evaluateJavaScript(js, completionHandler: nil)
        }
    }
}

/// Activity-panel wrapper for the Growth Console web module.
struct GrowthConsolePanel: View {
    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                Image(systemName: "leaf.fill")
                    .font(.system(size: 11))
                    .foregroundStyle(Color(red: 0.45, green: 0.85, blue: 0.55))
                Text("Vera Growth")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Color(red: 0.85, green: 0.85, blue: 0.92))
                Text("M/O · quarantine · JGEN actuator")
                    .font(.system(size: 9))
                    .foregroundStyle(.tertiary)
                Spacer()
            }
            .padding(.horizontal, 10).padding(.vertical, 8)
            .background(Color(red: 0.13, green: 0.13, blue: 0.17))
            Divider().opacity(0.3)
            WebModuleHost(moduleId: "growth-console")
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .background(Color(red: 0.10, green: 0.10, blue: 0.13))
    }
}
