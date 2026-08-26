import SwiftUI

// MARK: - UI the conversation summons, instead of UI that is always there
//
// The usual answer to "let the user change the model" is a control that lives
// on screen forever, and the usual answer to "let the user see memory" is a
// settings window with a tab for it. Do that a dozen times and the product is
// mostly chrome with a chat squeezed between it.
//
// The other answer: keep the window empty and let what the user says decide
// what appears. Typing 設定 raises a settings surface. Typing モデル raises the
// models. Typing 記憶 raises what the library actually holds. Nothing is
// permanent, so nothing has to earn permanent space.
//
// Two rules keep it honest.
//
// Recognition is deterministic — plain matching over the typed text, no model
// call. A panel that appears after a round trip is a panel that appears late,
// and one that appears because a model guessed is one that appears wrongly.
//
// Every number on these surfaces is counted, never estimated. This is the last
// place in the product where a plausible figure would be acceptable: a memory
// panel reporting a made-up count is the architecture contradicting itself in
// its own window.

enum VeraSurface: Equatable, Identifiable {
    case settings
    case models
    case memory

    var id: String {
        switch self {
        case .settings: return "settings"
        case .models:   return "models"
        case .memory:   return "memory"
        }
    }

    func title(japanese: Bool) -> String {
        switch self {
        case .settings: return japanese ? "設定" : "SETTINGS"
        case .models:   return japanese ? "モデル" : "MODELS"
        case .memory:   return japanese ? "記憶" : "MEMORY"
        }
    }

    /// Matched against what is being typed, as it is typed.
    ///
    /// Whole-word-ish and short on purpose: a surface that springs up in the
    /// middle of an ordinary sentence is worse than no surface at all, so the
    /// triggers are the words someone types when they mean only that word.
    static func recognise(_ raw: String) -> VeraSurface? {
        let text = raw.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !text.isEmpty, text.count <= 12 else { return nil }
        let table: [(VeraSurface, [String])] = [
            (.settings, ["設定", "せってい", "settings", "setting"]),
            (.models,   ["モデル", "もでる", "model", "models", "jgen"]),
            (.memory,   ["記憶", "きおく", "メモリ", "memory", "vera"]),
        ]
        for (surface, keys) in table where keys.contains(where: { text == $0 }) {
            return surface
        }
        return nil
    }
}

struct VeraSurfaceView: View {

    let surface: VeraSurface
    var japanese: Bool = true
    let onDismiss: () -> Void

    @EnvironmentObject var app: AppState
    @State private var stats: EternalMemoryStore.LibraryStats?
    @State private var appeared = false

    private func t(_ en: String, _ ja: String) -> String { japanese ? ja : en }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Divider().overlay(Color.white.opacity(0.07))
            content
                .padding(.horizontal, 14)
                .padding(.vertical, 11)
        }
        .frame(maxWidth: 360, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 13, style: .continuous)
                .fill(Theme.panel2)
                .shadow(color: .black.opacity(0.4), radius: 18, y: 8)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 13, style: .continuous)
                .strokeBorder(Color.white.opacity(0.09), lineWidth: 1)
        )
        // Summoned, not opened: it rises into the conversation rather than
        // sliding in from an edge, because it belongs to what was just typed.
        .scaleEffect(appeared ? 1 : 0.965, anchor: .bottom)
        .opacity(appeared ? 1 : 0)
        .offset(y: appeared ? 0 : 10)
        .onAppear {
            withAnimation(.spring(response: 0.4, dampingFraction: 0.82)) { appeared = true }
            if surface == .memory {
                Task {
                    let s = await EternalMemoryStore.shared.libraryStats()
                    await MainActor.run { stats = s }
                }
            }
        }
    }

    private var header: some View {
        HStack(spacing: 8) {
            // The mark appears where Vera's own machinery is on screen — not
            // as decoration on every surface in the app.
            JCrossGlyph(tint: Theme.sel, thickness: 1.6)
                .frame(width: 13, height: 13)
            Text(surface.title(japanese: japanese))
                .font(.system(size: 11, weight: .semibold, design: .monospaced))
                .foregroundStyle(.primary.opacity(0.85))
                .tracking(0.6)
            Spacer()
            Button { onDismiss() } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundStyle(.tertiary)
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 9)
    }

    @ViewBuilder
    private var content: some View {
        switch surface {
        case .models:   models
        case .memory:   memory
        case .settings: settings
        }
    }

    // MARK: Models — the list is real, and choosing one switches it

    private var models: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(t("Now", "現在"))
                .font(.system(size: 10)).foregroundStyle(.tertiary)
            Text(app.activeModelName ?? t("none", "未読込"))
                .font(.system(size: 12, design: .monospaced))
                .foregroundStyle(Theme.sel)

            if app.ollamaModels.isEmpty {
                Text(t("No local model is reachable.", "到達できるローカルモデルがありません。"))
                    .font(.system(size: 11)).foregroundStyle(.secondary)
            } else {
                Text(t("Available", "利用可能"))
                    .font(.system(size: 10)).foregroundStyle(.tertiary).padding(.top, 2)
                ForEach(app.ollamaModels, id: \.self) { name in
                    Button {
                        app.modelStatus = .ollamaReady(model: name)
                        onDismiss()
                    } label: {
                        HStack(spacing: 7) {
                            Circle()
                                .strokeBorder(Color.secondary.opacity(0.5), lineWidth: 1)
                                .background(Circle().fill(
                                    app.activeModelName == name
                                        ? Theme.sel
                                        : .clear))
                                .frame(width: 9, height: 9)
                            Text(name).font(.system(size: 12, design: .monospaced))
                                .foregroundStyle(.primary.opacity(0.9))
                            Spacer(minLength: 0)
                        }
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }

    // MARK: Memory — counted, never estimated

    private var memory: some View {
        VStack(alignment: .leading, spacing: 7) {
            if let stats {
                row(t("records", "レコード"), stats.nodes)
                row(t("act episodes", "操作エピソード"), stats.actEpisodes)
                row(t("human demonstrations", "人間の実演"), stats.humanDemonstrations)
                row(t("visual grounds", "視覚の接地"), stats.visualGrounds)
            } else {
                Text(t("Counting…", "集計中…"))
                    .font(.system(size: 11)).foregroundStyle(.secondary)
            }
            Text(t("Counted from the store, not estimated.",
                   "ストアからの実数です（推定ではありません）。"))
                .font(.system(size: 10)).foregroundStyle(.tertiary).padding(.top, 3)
        }
    }

    private func row(_ label: String, _ value: Int) -> some View {
        HStack {
            Text(label).font(.system(size: 12)).foregroundStyle(.secondary)
            Spacer(minLength: 12)
            Text("\(value)")
                .font(.system(size: 12, weight: .semibold, design: .monospaced))
                .foregroundStyle(.primary.opacity(0.9))
        }
    }

    // MARK: Settings — a map, not a second settings app

    private var settings: some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach([
                (t("Models", "モデル"), t("type モデル", "「モデル」と入力")),
                (t("Memory", "記憶"), t("type 記憶", "「記憶」と入力")),
            ], id: \.0) { name, hint in
                HStack {
                    Text(name).font(.system(size: 12)).foregroundStyle(.primary.opacity(0.9))
                    Spacer(minLength: 12)
                    Text(hint).font(.system(size: 10)).foregroundStyle(.tertiary)
                }
            }
            Text(t("Say what you want to change. Surfaces are summoned, not stored.",
                   "変えたいものを言ってください。画面は呼び出されるもので、置いてあるものではありません。"))
                .font(.system(size: 10)).foregroundStyle(.tertiary).padding(.top, 4)
        }
    }
}
