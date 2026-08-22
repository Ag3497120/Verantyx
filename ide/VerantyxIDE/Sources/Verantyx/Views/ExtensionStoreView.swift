import SwiftUI

struct ExtensionStoreView: View {
    @EnvironmentObject var app: AppState
    @State private var query: String = "python"
    @State private var results: [OpenVSXExtension] = []
    @State private var isSearching = false
    @State private var installingID: String? = nil
    
    var onDismiss: () -> Void
    
    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Image(systemName: "shippingbox.fill")
                    .font(.title2)
                    .foregroundStyle(Color.blue)
                Text("Extension Store")
                    .font(.headline)
                Spacer()
                Button {
                    onDismiss()
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundStyle(.secondary)
                        .font(.title2)
                }
                .buttonStyle(PlainButtonStyle())
            }
            .padding()
            .background(Color(NSColor.controlBackgroundColor))
            
            Divider()
            
            // Search Bar
            HStack {
                TextField("Search extensions in Open VSX...", text: $query)
                    .textFieldStyle(RoundedBorderTextFieldStyle())
                    .onSubmit {
                        performSearch()
                    }
                
                Button("Search") {
                    performSearch()
                }
                .disabled(isSearching)
            }
            .padding()
            
            Divider()
            
            // Results List
            if isSearching {
                Spacer()
                ProgressView("Searching...")
                Spacer()
            } else if results.isEmpty {
                Spacer()
                Text("No extensions found.")
                    .foregroundColor(.secondary)
                Spacer()
            } else {
                List(results) { ext in
                    HStack(alignment: .top) {
                        // Icon placeholder (could use AsyncImage if URL is reliable)
                        if let icon = ext.files.icon, let url = URL(string: icon) {
                            AsyncImage(url: url) { image in
                                image.resizable()
                                     .aspectRatio(contentMode: .fit)
                            } placeholder: {
                                RoundedRectangle(cornerRadius: 8)
                                    .fill(Color.gray.opacity(0.3))
                            }
                            .frame(width: 48, height: 48)
                            .cornerRadius(8)
                        } else {
                            RoundedRectangle(cornerRadius: 8)
                                .fill(Color.gray.opacity(0.3))
                                .frame(width: 48, height: 48)
                        }
                        
                        VStack(alignment: .leading, spacing: 4) {
                            HStack {
                                Text(ext.displayName ?? ext.name)
                                    .font(.headline)
                                Text("v\(ext.version)")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            Text(ext.namespace)
                                .font(.caption)
                                .foregroundStyle(.blue)
                            
                            if let desc = ext.description {
                                Text(desc)
                                    .font(.callout)
                                    .foregroundStyle(.secondary)
                                    .lineLimit(2)
                            }
                        }
                        
                        Spacer()
                        
                        let isInstalled = VSIXPackageManager.shared.installedExtensions.contains(where: { $0.publisher == ext.namespace && $0.name == ext.name })
                        
                        if isInstalled {
                            Text("Installed")
                                .font(.caption)
                                .bold()
                                .padding(.horizontal, 10)
                                .padding(.vertical, 4)
                                .background(Color.green.opacity(0.2))
                                .foregroundColor(.green)
                                .cornerRadius(8)
                        } else if installingID == ext.id {
                            ProgressView()
                                .controlSize(.small)
                                .padding(.horizontal, 10)
                        } else {
                            Button("Install") {
                                install(ext: ext)
                            }
                        }
                    }
                    .padding(.vertical, 8)
                }
            }
        }
        .frame(width: 600, height: 500)
        .onAppear {
            performSearch()
        }
    }
    
    private func performSearch() {
        guard !query.isEmpty else { return }
        isSearching = true
        Task {
            do {
                let items = try await VSIXPackageManager.shared.searchOpenVSX(query: query)
                await MainActor.run {
                    self.results = items
                    self.isSearching = false
                }
            } catch {
                await MainActor.run {
                    self.isSearching = false
                    app.addSystemMessage("❌ Search failed: \(error.localizedDescription)")
                }
            }
        }
    }
    
    private func install(ext: OpenVSXExtension) {
        installingID = ext.id
        Task {
            do {
                try await VSIXPackageManager.shared.downloadAndInstall(extension: ext)
                app.addSystemMessage("✅ Installed VS Code Extension: \(ext.displayName ?? ext.name)")
            } catch {
                app.addSystemMessage("❌ Failed to install extension: \(error.localizedDescription)")
            }
            await MainActor.run {
                installingID = nil
            }
        }
    }
}
