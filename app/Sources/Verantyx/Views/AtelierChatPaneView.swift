import SwiftUI

// MARK: - AtelierChatPaneView
//
// UI B (owner's spec, verbatim): 「チャット画面プラス服飾uiというのは全体を
// 表示しながら現在いるuiをチャットが自動で切り替えてくれるというもの…
// こっちは全体を表示していてそこを開くというもの。」The whole garment
// workbench stays on screen (`AtelierView`, untouched, still the ONE place
// that view is drawn — see AtelierView.swift's own house-rule comment);
// this pane sits BESIDE it and asks `AtelierChatRouter` where a typed line
// resolves. It never renders the workbench itself, never becomes a second
// composer for general conversation, and never calls a model to decide
// where to go — see the router's own doc comment for why.
//
// Deliberately its own small transcript + text field, not a reuse of
// `UnifiedComposerView` — that composer's job is the general
// attach/model-pick/send pipeline into `app.messages`; wiring THIS pane's
// deterministic navigation through that pipeline would either fight it or
// quietly grow this into a second general chat implementation. One pane,
// one job: read a line, resolve a place, move there or say why not.
struct AtelierChatPaneView: View {
    @EnvironmentObject var app: AppState
    /// The mirror, not the model — this pane lives outside AtelierView's
    /// subtree. See `AtelierContext.step` and `AtelierNavigator`.
    @ObservedObject private var ctx = AtelierContext.shared
    @ObservedObject private var nav = AtelierNavigator.shared

    private enum Role { case user, nav, refused, empty }
    private struct Line: Identifiable {
        let id = UUID()
        let role: Role
        let text: String
    }

    @State private var lines: [Line] = []
    @State private var input: String = ""
    @State private var resolving = false
    @FocusState private var focused: Bool

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider().opacity(0.25)
            transcript
            Divider().opacity(0.25)
            inputRow
        }
        .background(Theme.panel)
        // 中央の workbench を潰さない側の相方として、この帯自体は伸び縮み
        // しない — HouseRule 2 (clip and constrain) の裏側。
        .frame(minWidth: 280, idealWidth: 320, maxWidth: 380)
        .clipped()
    }

    // MARK: - Header

    private var header: some View {
        HStack(spacing: 6) {
            Image(systemName: "bubble.left.and.bubble.right")
                .font(.system(size: 10))
                .foregroundStyle(Theme.sel)
            Text(app.t("Steer", "誘導")).font(.system(size: 11, weight: .semibold))
                .foregroundStyle(Theme.fg)
            Spacer()
            Text(app.t("now: \(ctx.step)", "現在地: \(ctx.step)"))
                .font(.system(size: 10, design: .monospaced))
                .foregroundStyle(Theme.dim)
                .lineLimit(1)
        }
        .padding(.horizontal, 12).padding(.vertical, 8)
    }

    // MARK: - Transcript

    private var transcript: some View {
        ScrollViewReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    if lines.isEmpty {
                        Text(app.t(
                            "Ask about the fabric, or name a number span (\"loosen 30 to 35\") — this pane moves the workbench wherever the engine resolves it. Nothing typed here writes to the ledger.",
                            "生地について聞く、または番号区間を書く(「30番から35番をゆとりに」)— engine が解決できた場所へこの欄が工程を動かします。ここに書いても台帳は書き換わりません。"))
                            .font(.system(size: 11))
                            .foregroundStyle(Theme.faint)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    ForEach(lines) { line in
                        lineView(line).id(line.id)
                    }
                    if resolving {
                        HStack(spacing: 5) {
                            ProgressView().controlSize(.small)
                            Text(app.t("resolving…", "解決中…"))
                                .font(.system(size: 10)).foregroundStyle(Theme.faint)
                        }
                    }
                }
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .onChange(of: lines.count) { _, _ in
                guard let last = lines.last?.id else { return }
                withAnimation(.easeOut(duration: 0.15)) {
                    proxy.scrollTo(last, anchor: .bottom)
                }
            }
        }
    }

    @ViewBuilder
    private func lineView(_ line: Line) -> some View {
        switch line.role {
        case .user:
            Text(line.text)
                .font(.system(size: 11))
                .foregroundStyle(Theme.fg)
                .padding(.horizontal, 9).padding(.vertical, 6)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Theme.panel2, in: RoundedRectangle(cornerRadius: 7))
        case .nav:
            // **見出しではなく答え。** 動いた理由を一行で言う — 説明なく
            // 変わる画面はバグに見える、という owner の言葉のとおり。
            HStack(alignment: .top, spacing: 5) {
                Image(systemName: "arrow.turn.down.right")
                    .font(.system(size: 9, weight: .bold))
                Text(line.text).font(.system(size: 11, weight: .semibold))
            }
            .foregroundStyle(Theme.sel)
        case .refused:
            Text(line.text)
                .font(.system(size: 10.5))
                .foregroundStyle(Theme.warn)
        case .empty:
            Text(line.text)
                .font(.system(size: 10.5))
                .foregroundStyle(Theme.faint)
        }
    }

    // MARK: - Input

    private var inputRow: some View {
        HStack(spacing: 8) {
            TextField(app.t("Say what to look at…", "何を見るか書く…"), text: $input)
                .textFieldStyle(.plain)
                .font(.system(size: 12))
                .padding(.horizontal, 9).padding(.vertical, 6)
                .background(Theme.panel2, in: RoundedRectangle(cornerRadius: 7))
                .focused($focused)
                .onSubmit(send)
            Button(action: send) {
                Image(systemName: "arrow.up.circle.fill").font(.system(size: 20))
            }
            .buttonStyle(.plain)
            .foregroundStyle(canSend ? Theme.sel : Theme.faint)
            .disabled(!canSend)
        }
        .padding(10)
    }

    private var canSend: Bool {
        !input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !resolving
    }

    private func send() {
        let text = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        input = ""
        lines.append(Line(role: .user, text: text))
        resolving = true
        Task {
            let resolution = await AtelierChatRouter.resolve(text)
            resolving = false
            switch resolution {
            case .moved(let d):
                // The one write this pane ever makes: a resolved
                // destination, offered through AtelierNavigator — never
                // `ctx.step` directly (see that property's own comment).
                AtelierNavigator.shared.go(to: d.step)
                lines.append(Line(role: .nav, text: app.t(d.reasonEN, d.reasonJA)))
            case .refused(let why):
                lines.append(Line(role: .refused, text: why))
            case .none:
                lines.append(Line(role: .empty, text: app.t(
                    "No matching place — staying on \(ctx.step).",
                    "対応する場所が見つからず、\(ctx.step) のままです。")))
            }
        }
    }
}
