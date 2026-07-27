import SwiftUI

/// Bottom-panel view showing exactly what each memory layer (L1, L1.5, L2,
/// L3, Vera-α) would inject into the prompt right now, for the current
/// session. Lets the user switch layers and see the raw injected text —
/// answers "map をオンにするとこの変換されたものが注入されたりするのですか"
/// concretely instead of by explanation.
struct MemoryLayerInspectorView: View {
    @EnvironmentObject var app: AppState

    @State private var selectedLayer: JCrossLayer = .l2
    @State private var previewText: String = ""
    @State private var isLoading: Bool = false

    private let previewableLayers: [JCrossLayer] = [.l1, .l1_5, .l2, .l3, .vera]

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 8) {
                Text(app.t("Layer:", "レイヤー:"))
                    .font(.system(size: 10))
                    .foregroundStyle(.secondary)

                Picker("", selection: $selectedLayer) {
                    ForEach(previewableLayers) { layer in
                        Text(layer.rawValue).tag(layer)
                    }
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .frame(width: 300)
                .onChange(of: selectedLayer) { _ in refresh() }

                Spacer()

                if isLoading {
                    ProgressView().controlSize(.mini)
                }
                Button {
                    refresh()
                } label: {
                    Image(systemName: "arrow.clockwise")
                        .font(.system(size: 10))
                }
                .buttonStyle(.plain)
                .help(app.t("Recompute this layer's injection now", "このレイヤーの注入内容を再計算"))
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)

            Divider().opacity(0.2)

            ScrollView {
                Text(previewText.isEmpty
                     ? app.t("(this layer would inject nothing right now)",
                             "（現時点でこのレイヤーから注入される内容はありません）")
                     : previewText)
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(previewText.isEmpty
                        ? Color(red: 0.5, green: 0.5, blue: 0.55)
                        : Color(red: 0.82, green: 0.82, blue: 0.9))
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(10)
            }
        }
        .background(Color(red: 0.08, green: 0.08, blue: 0.11))
        .onAppear { refresh() }
    }

    private func refresh() {
        let layer = selectedLayer
        if layer == .vera {
            isLoading = true
            let query = app.messages.last(where: { $0.role == .user })?.content ?? ""
            Task {
                let result = await VeraMemoryBridge.recall(for: query)
                await MainActor.run {
                    guard selectedLayer == .vera else { return }
                    previewText = result
                    isLoading = false
                }
            }
        } else {
            isLoading = false
            let useNanoStore = app.isNanoSmallModelActive
            previewText = SessionMemoryArchiver.shared.buildZonePriorityInjection(
                layer: layer,
                useNanoStore: useNanoStore
            )
        }
    }
}
