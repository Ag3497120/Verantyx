import SwiftUI

/// Renders `ReasoningTimelineStore`'s events as a vertical mm:ss timeline —
/// the point being that a 10+ minute Council run should read as "generating
/// and verifying multiple hypotheses, recording failures along the way",
/// not as an opaque wait with the GPU spinning.
struct ReasoningTimelineView: View {
    @ObservedObject private var store = ReasoningTimelineStore.shared

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Image(systemName: "timeline.selection")
                Text(AppLanguage.shared.t("Reasoning Timeline", "推論タイムライン"))
                    .font(.headline)
                Spacer()
                if store.isActive {
                    ProgressView().controlSize(.small)
                    Text(AppLanguage.shared.t("Running…", "実行中…"))
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            .padding()

            Divider()

            if store.events.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "timeline.selection")
                        .font(.largeTitle)
                        .foregroundStyle(.tertiary)
                    Text(AppLanguage.shared.t(
                        "No run yet. This fills in while an agent turn (especially Council) is working.",
                        "まだ実行がありません。エージェントのターン(特に合議)が動いている間にここが埋まっていきます。"))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .padding()
            } else {
                ScrollViewReader { proxy in
                    ScrollView {
                        VStack(alignment: .leading, spacing: 0) {
                            ForEach(store.events) { event in
                                row(for: event)
                                    .id(event.id)
                            }
                        }
                        .padding(.vertical, 8)
                    }
                    .onChange(of: store.events.count) { _, _ in
                        if let last = store.events.last {
                            withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
                        }
                    }
                }
            }
        }
        .frame(minWidth: 420, minHeight: 360)
    }

    private func row(for event: TimelineEvent) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Text(event.elapsedLabel)
                .font(.system(.caption, design: .monospaced))
                .foregroundStyle(.secondary)
                .frame(width: 44, alignment: .trailing)

            VStack(spacing: 0) {
                Image(systemName: event.category.icon)
                    .foregroundStyle(event.category.color)
                    .frame(width: 16)
                Rectangle()
                    .fill(Color.secondary.opacity(0.2))
                    .frame(width: 1)
                    .frame(maxHeight: .infinity)
            }

            Text(event.label)
                .font(.callout)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.bottom, 12)

            Spacer(minLength: 0)
        }
        .padding(.horizontal)
    }
}
