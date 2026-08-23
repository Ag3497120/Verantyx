import Foundation

/// Defines a parsed extension from a package.json
struct ExtensionManifest: Codable {
    let name: String
    let displayName: String?
    let version: String
    let publisher: String
    let main: String?
    let engines: [String: String]?
    // Other fields like activationEvents, contributes, etc.
}

@MainActor
final class VSIXPackageManager: ObservableObject {
    static let shared = VSIXPackageManager()
    
    @Published var installedExtensions: [ExtensionManifest] = []
    
    private let fileManager = FileManager.default
    private var extensionsDirectory: URL
    
    private init() {
        // e.g. ~/Library/Application Support/VerantyxIDE/Extensions
        let appSupport = fileManager.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        extensionsDirectory = appSupport.appendingPathComponent("VerantyxIDE/Extensions", isDirectory: true)
        
        do {
            try fileManager.createDirectory(at: extensionsDirectory, withIntermediateDirectories: true)
        } catch {
            print("Failed to create extensions directory: \(error)")
        }
        
        loadInstalledExtensions()
    }
    
    /// Scans the extensions directory for package.json files and loads them into memory
    func loadInstalledExtensions() {
        var manifests: [ExtensionManifest] = []
        
        guard let dirs = try? fileManager.contentsOfDirectory(at: extensionsDirectory, includingPropertiesForKeys: [.isDirectoryKey]) else { return }
        
        for dir in dirs {
            var isDir: ObjCBool = false
            guard fileManager.fileExists(atPath: dir.path, isDirectory: &isDir), isDir.boolValue else { continue }
            
            let packageJsonURL = dir.appendingPathComponent("package.json")
            if let data = try? Data(contentsOf: packageJsonURL),
               let manifest = try? JSONDecoder().decode(ExtensionManifest.self, from: data) {
                manifests.append(manifest)
            }
        }
        
        self.installedExtensions = manifests
    }
    
    /// Unzips a .vsix file into the extensions directory (Note: Requires a ZIP unarchiver library like ZIPFoundation in a real app)
    func installExtension(from vsixURL: URL) async throws {
        // A VSIX is just a ZIP file.
        // Process:
        // 1. Unzip the vsix to a temporary folder
        // 2. Locate the "extension" folder inside
        // 3. Read package.json to get publisher and name
        // 4. Move "extension" folder to extensionsDirectory/publisher.name-version
        // 5. loadInstalledExtensions()
        // 6. Notify ExtensionHostManager to load the extension
        
        // This is a placeholder for the actual extraction logic, which would require Process() with `unzip`
        // or a Swift ZIP library.
        
        // ⚠️ @MainActor 上で waitUntilExit() を呼ぶとメインスレッドがブロックされるため
        //    バックグラウンドスレッドで実行する
        let tempDir = fileManager.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try fileManager.createDirectory(at: tempDir, withIntermediateDirectories: true)
        let vsixPath = vsixURL.path
        let tempPath = tempDir.path
        let exitCode = await Task.detached(priority: .userInitiated) { () -> Int32 in
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/usr/bin/unzip")
            process.arguments = ["-q", vsixPath, "-d", tempPath]
            do {
                try process.run()
                process.waitUntilExit()
                return process.terminationStatus
            } catch {
                return -1
            }
        }.value

        guard exitCode == 0 else {
            throw NSError(domain: "VSIXPackageManager", code: Int(exitCode), userInfo: [NSLocalizedDescriptionKey: "Failed to unzip VSIX"])
        }
        
        let extensionContentDir = tempDir.appendingPathComponent("extension")
        let packageJsonURL = extensionContentDir.appendingPathComponent("package.json")
        
        let data = try Data(contentsOf: packageJsonURL)
        let manifest = try JSONDecoder().decode(ExtensionManifest.self, from: data)
        
        let targetDirName = "\(manifest.publisher).\(manifest.name)-\(manifest.version)"
        let targetURL = extensionsDirectory.appendingPathComponent(targetDirName)
        
        if fileManager.fileExists(atPath: targetURL.path) {
            try fileManager.removeItem(at: targetURL)
        }
        
        try fileManager.moveItem(at: extensionContentDir, to: targetURL)
        
        // Clean up
        try fileManager.removeItem(at: tempDir)
        
        loadInstalledExtensions()
        
        // Activate it on the host!
        let mainScript = targetURL.appendingPathComponent(manifest.main ?? "extension.js").path
        ExtensionHostManager.shared.sendNotification(method: "extension.load", params: [
            "main": mainScript,
            "id": "\(manifest.publisher).\(manifest.name)"
        ])
    }
    
    // MARK: - Open VSX Store Integration
    
    func searchOpenVSX(query: String) async throws -> [OpenVSXExtension] {
        let encodedQuery = query.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? ""
        guard let url = URL(string: "https://open-vsx.org/api/-/search?query=\(encodedQuery)") else {
            return []
        }
        let (data, _) = try await URLSession.shared.data(from: url)
        let result = try JSONDecoder().decode(OpenVSXSearchResult.self, from: data)
        return result.extensions
    }
    
    func downloadAndInstall(extension ext: OpenVSXExtension) async throws {
        guard let downloadURL = URL(string: ext.files.download) else {
            throw URLError(.badURL)
        }
        
        let (tempURL, _) = try await URLSession.shared.download(from: downloadURL)
        
        let vsixURL = fileManager.temporaryDirectory.appendingPathComponent("\(ext.id)-\(ext.version).vsix")
        if fileManager.fileExists(atPath: vsixURL.path) {
            try fileManager.removeItem(at: vsixURL)
        }
        try fileManager.moveItem(at: tempURL, to: vsixURL)
        
        try await installExtension(from: vsixURL)
    }
}

// MARK: - Open VSX Models

struct OpenVSXSearchResult: Codable {
    let extensions: [OpenVSXExtension]
}

struct OpenVSXExtension: Codable, Identifiable {
    var id: String { "\(namespace).\(name)" }
    let name: String
    let namespace: String
    let displayName: String?
    let description: String?
    let version: String
    let files: OpenVSXFiles
}

struct OpenVSXFiles: Codable {
    let download: String
    let icon: String?
}
