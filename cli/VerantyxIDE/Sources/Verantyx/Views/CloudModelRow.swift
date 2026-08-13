import SwiftUI

// MARK: - Model catalog
//
// Every provider's model list used to be four hardcoded `Text(...).tag(...)`
// lines, so the picker went stale the day a provider shipped anything new and
// only a source edit could fix it. This asks each provider what it serves,
// caches the answer on disk, and refreshes it in the background once a day.
//
// The cache is what makes it usable offline: the list shown at launch is the
// last one the provider gave, not an empty menu, and a failed refresh leaves
// it untouched rather than clearing it.
@MainActor
final class CloudModelCatalog: ObservableObject {

    static let shared = CloudModelCatalog()

    @Published private(set) var models: [CloudProvider: [String]] = [:]
    @Published private(set) var refreshing: Set<CloudProvider> = []
    @Published private(set) var lastError: [CloudProvider: String] = [:]

    private static let ttl: TimeInterval = 60 * 60 * 24

    private init() {
        for provider in CloudProvider.allCases {
            if let cached = UserDefaults.standard.stringArray(forKey: Self.cacheKey(provider)),
               !cached.isEmpty {
                models[provider] = cached
            }
        }
    }

    private static func cacheKey(_ p: CloudProvider) -> String { "model_catalog_\(p.modelDefaultsKey)" }
    private static func stampKey(_ p: CloudProvider) -> String { "model_catalog_at_\(p.modelDefaultsKey)" }

    /// Refresh only if the cache is missing or older than a day. Called on
    /// appear, so opening Settings is enough to keep the list current.
    func refreshIfStale(_ provider: CloudProvider) {
        let stamp = UserDefaults.standard.double(forKey: Self.stampKey(provider))
        let age = Date().timeIntervalSince1970 - stamp
        if models[provider]?.isEmpty == false && age < Self.ttl { return }
        refresh(provider)
    }

    /// Ask the provider now. An empty answer means the call failed or there is
    /// no key — keep whatever list we already had rather than blanking it.
    func refresh(_ provider: CloudProvider) {
        guard !refreshing.contains(provider) else { return }
        refreshing.insert(provider)
        lastError[provider] = nil

        Task {
            let fetched = await CloudAPIClient.shared.listModels(for: provider)
            await MainActor.run {
                refreshing.remove(provider)
                if fetched.isEmpty {
                    lastError[provider] = models[provider]?.isEmpty == false
                        ? "更新できませんでした（前回の一覧を表示中）"
                        : "APIキーを設定すると一覧を取得します"
                } else {
                    models[provider] = fetched
                    UserDefaults.standard.set(fetched, forKey: Self.cacheKey(provider))
                    UserDefaults.standard.set(Date().timeIntervalSince1970, forKey: Self.stampKey(provider))
                }
            }
        }
    }

    /// What the picker should offer: the live list, plus the saved selection if
    /// the provider no longer lists it — dropping it silently would move the
    /// user onto a different model without telling them.
    func options(for provider: CloudProvider, including selection: String) -> [String] {
        var list = models[provider] ?? []
        if !selection.isEmpty && !list.contains(selection) {
            list.insert(selection, at: 0)
        }
        if list.isEmpty { list = [provider.defaultModel] }
        return list
    }

    /// Whether a key is configured. The selector uses this to hide providers
    /// that would fail the moment they were chosen.
    func hasKey(_ provider: CloudProvider) -> Bool {
        let k = UserDefaults.standard.string(forKey: provider.spec.keyDefaults) ?? ""
        return !k.trimmingCharacters(in: .whitespaces).isEmpty
    }

    func lastRefreshed(_ provider: CloudProvider) -> Date? {
        let stamp = UserDefaults.standard.double(forKey: Self.stampKey(provider))
        return stamp > 0 ? Date(timeIntervalSince1970: stamp) : nil
    }
}

// MARK: - Row

/// The "Model" row for one provider: a picker fed by the live catalog, a
/// refresh button, and a line saying where the list came from.
struct CloudModelRow: View {

    let provider: CloudProvider
    @Binding var selection: String

    @ObservedObject private var catalog = CloudModelCatalog.shared

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack {
                Text("Model")
                    .font(.system(size: 12))
                    .foregroundStyle(Color(red: 0.75, green: 0.75, blue: 0.88))
                Spacer()

                Picker("", selection: $selection) {
                    ForEach(catalog.options(for: provider, including: selection), id: \.self) { id in
                        Text(id).tag(id)
                    }
                }
                .labelsHidden()
                .frame(width: 240)

                Button {
                    catalog.refresh(provider)
                } label: {
                    if catalog.refreshing.contains(provider) {
                        ProgressView().scaleEffect(0.5).frame(width: 14, height: 14)
                    } else {
                        Image(systemName: "arrow.clockwise").font(.system(size: 11))
                    }
                }
                .buttonStyle(.plain)
                .contentShape(Rectangle())
                .foregroundStyle(.secondary)
                .disabled(catalog.refreshing.contains(provider))
                .help("プロバイダーに現在のモデル一覧を問い合わせます")
            }

            HStack(spacing: 4) {
                Spacer()
                Text(statusLine)
                    .font(.system(size: 9))
                    .foregroundStyle(.tertiary)
            }
        }
        .onAppear { catalog.refreshIfStale(provider) }
    }

    private var statusLine: String {
        if let err = catalog.lastError[provider] { return err }
        let count = catalog.models[provider]?.count ?? 0
        guard count > 0, let at = catalog.lastRefreshed(provider) else {
            return "内蔵の既定値を表示中"
        }
        let fmt = DateFormatter()
        fmt.dateFormat = "M/d HH:mm"
        return "\(count) 件・\(fmt.string(from: at)) 取得"
    }
}
