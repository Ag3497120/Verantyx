import Foundation
let fileManager = FileManager.default
let home = fileManager.homeDirectoryForCurrentUser
print("home: \(home.path)")
if let contents = try? fileManager.contentsOfDirectory(at: home, includingPropertiesForKeys: [.isDirectoryKey], options: [.skipsHiddenFiles]) {
    for url in contents {
        print(" - \(url.lastPathComponent)")
    }
} else {
    print("Failed to read contents")
}
