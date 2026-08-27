import SwiftUI

// MARK: - AtelierWorkbenchSplitView
//
// UI B, laid out. The owner's spec is explicit that the chat is a PANE
// beside the workbench, not a bar pinned under it — the pinned composer
// was deliberately removed elsewhere in this codebase and must not come
// back in that shape. So: two panes, one HStack, a Divider between them.
// `AtelierView` renders exactly as it always has (still the one place
// that view is drawn — see its own house-rule comment); the chat pane is
// new and additive.
struct AtelierWorkbenchSplitView: View {
    @EnvironmentObject var app: AppState

    var body: some View {
        HStack(spacing: 0) {
            // **中央は潰れてはいけない** (house rule 2). The chat pane is
            // capped at 380pt (see AtelierChatPaneView); the workbench
            // gets an explicit floor so a narrow window squeezes the pane
            // before it ever squeezes the garment itself.
            AtelierView()
                .environmentObject(app)
                .frame(minWidth: 640, maxWidth: .infinity, maxHeight: .infinity)
                .clipped()
            Divider().opacity(0.3)
            AtelierChatPaneView()
                .environmentObject(app)
                .frame(maxHeight: .infinity)
        }
        .background(Theme.panel2)
        .clipped()
    }
}
