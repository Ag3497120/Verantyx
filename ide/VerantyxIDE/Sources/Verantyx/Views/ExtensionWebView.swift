import SwiftUI
import WebKit

@MainActor
final class ExtensionWebViewCoordinator: NSObject, WKNavigationDelegate, WKScriptMessageHandler {
    var panelId: String

    init(panelId: String) {
        self.panelId = panelId
        super.init()
    }

    // Handle messages sent from the Webview (JavaScript) to the Extension (Node.js)
    // Extensions typically call vscode.postMessage(data)
    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard message.name == "vscode", let body = message.body as? [String: Any] else { return }
        
        // Forward the message to the ExtensionHost
        ExtensionHostManager.shared.sendNotification(
            method: "webview.onDidReceiveMessage.\(panelId)",
            params: body
        )
    }
}

struct ExtensionWebView: NSViewRepresentable {
    let panelId: String
    @Binding var htmlContent: String

    func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        
        // Inject the acquireVsCodeApi() shim so that the JS in the webview can post messages back
        let scriptSource = """
        window.acquireVsCodeApi = function() {
            return {
                postMessage: function(message) {
                    window.webkit.messageHandlers.vscode.postMessage(message);
                }
            };
        };
        """
        let userScript = WKUserScript(source: scriptSource, injectionTime: .atDocumentStart, forMainFrameOnly: true)
        config.userContentController.addUserScript(userScript)
        config.userContentController.add(context.coordinator, name: "vscode")
        
        let webView = WKWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = context.coordinator
        
        // Initial HTML load
        webView.loadHTMLString(htmlContent, baseURL: nil)
        
        // Save reference if we need to call postMessage into the webview from Swift
        // For simplicity, we manage this globally or via AppState in a real app
        AppState.shared?.activeWebViews[panelId] = webView
        
        return webView
    }

    func updateNSView(_ nsView: WKWebView, context: Context) {
        // If the HTML content updates completely (e.g. extension overwrote html property)
        // In reality, we might want to diff or handle it more gracefully, but for now:
        if nsView.url == nil || nsView.title?.isEmpty == true {
            nsView.loadHTMLString(htmlContent, baseURL: nil)
        }
    }

    func makeCoordinator() -> ExtensionWebViewCoordinator {
        ExtensionWebViewCoordinator(panelId: panelId)
    }
}

// Ensure AppState has activeWebViews
extension AppState {
    // Dictionary to hold active webviews by panelId to route postMessage to them
    // This is a quick hack for the example, in reality we'd structure it better.
    // var activeWebViews: [String: WKWebView] = [:]
}
