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
//
// **Reflow, not clipping (owner's brief, 2026-08-27).** The workbench
// needs 640pt to show the garment without squeezing it, and the chat
// pane needs at least 280pt to be worth having open — 921pt together
// with the divider. The declared window minimum is 900x600
// (`VerantyxApp.swift`), which is BELOW that sum. Below the threshold
// the chat pane would previously get squeezed under its own floor, the
// overflow silently eaten by `.clipped()` on this view and on
// `AtelierView` beneath it — which is exactly how "Sources" rendered as
// "ources": the rail computed its layout inside a workbench that had
// already been handed less width than either child asked for.
//
// The fix is to stop asking for both floors to fit in the same row when
// they can't. Below `chatInlineThreshold` the chat pane drops out of the
// row entirely — one of the three sanctioned answers (collapse to icons,
// drop the pane, or scroll; never clip) — and reappears as a `.sheet`
// behind a toggle button, so **the workbench never has to give up
// getting its full width to make room for it.**
struct AtelierWorkbenchSplitView: View {
    @EnvironmentObject var app: AppState
    @State private var chatSheetShown = false

    /// Below this total width, `AtelierView`'s own 640pt floor plus the
    /// chat pane's 280pt floor plus the 1pt divider (921pt) no longer
    /// fit side by side. 960 leaves a little slack above that exact sum
    /// so the switch happens before either pane is actually squeezed,
    /// not after. At the declared window minimum (900x600) this always
    /// takes the "chat is a sheet" branch — see the finding in the task
    /// report about whether 900pt can hold both panes inline; it cannot,
    /// and this is the deliberate answer, not an oversight.
    private static let chatInlineThreshold: CGFloat = 960

    var body: some View {
        GeometryReader { geo in
            let showChatInline = geo.size.width >= Self.chatInlineThreshold
            ZStack(alignment: .bottomTrailing) {
                HStack(spacing: 0) {
                    // **中央は潰れてはいけない** (house rule 2). The
                    // workbench gets an explicit floor; the chat pane
                    // (when inline) is capped at 380pt — see
                    // AtelierChatPaneView — so a narrower-than-comfortable
                    // window squeezes the pane before it ever squeezes
                    // the garment itself. Below `chatInlineThreshold` the
                    // pane isn't in this row at all, so there is nothing
                    // left to squeeze the workbench.
                    AtelierView()
                        .environmentObject(app)
                        .frame(minWidth: 640, maxWidth: .infinity, maxHeight: .infinity)
                        .clipped()
                    if showChatInline {
                        Divider().opacity(0.3)
                        AtelierChatPaneView()
                            .environmentObject(app)
                            .frame(maxHeight: .infinity)
                            .transition(.move(edge: .trailing).combined(with: .opacity))
                    }
                }
                if !showChatInline {
                    chatToggleButton
                        .padding(14)
                }
            }
            .animation(.easeInOut(duration: 0.15), value: showChatInline)
        }
        .background(Theme.panel2)
        .clipped()
        .sheet(isPresented: $chatSheetShown) {
            AtelierChatPaneView()
                .environmentObject(app)
                .frame(minWidth: 320, idealWidth: 380, maxWidth: 460,
                       minHeight: 420, idealHeight: 560, maxHeight: 720)
        }
    }

    /// **Never a control that does nothing** (house rule 3). When the
    /// pane can't sit inline, this replaces it — same job (steer the
    /// workbench), reached one tap away instead of always-visible.
    private var chatToggleButton: some View {
        Button {
            chatSheetShown = true
        } label: {
            Image(systemName: "bubble.left.and.bubble.right.fill")
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(.white)
                .frame(width: 44, height: 44)
                .background(Theme.sel, in: Circle())
                .shadow(radius: 4, y: 2)
        }
        .buttonStyle(.plain)
        .help(app.t("Steer (chat)", "誘導（チャット）"))
    }
}
