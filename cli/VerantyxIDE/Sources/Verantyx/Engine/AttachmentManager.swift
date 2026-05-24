import Foundation
import AppKit
import SwiftUI

// MARK: - AttachedImage
// Represents an image attached to a chat message for multimodal inference.

struct AttachedImage: Identifiable {
    let id = UUID()
    let name: String
    let url: URL?        // source URL if from disk
    let nsImage: NSImage // rendered preview

    // Base64-encoded JPEG for inclusion in Ollama/MLX vision API payloads
    var base64JPEG: String? {
        let img = nsImage
        guard let tiff = img.tiffRepresentation,
              let bitmap = NSBitmapImageRep(data: tiff),
              let jpeg = bitmap.representation(using: .jpeg, properties: [.compressionFactor: 0.85])
        else { return nil }
        return jpeg.base64EncodedString()
    }

    // SwiftUI Image
    var swiftUIImage: Image { Image(nsImage: nsImage) }
}

// MARK: - AttachmentManager
// Handles picking / dropping images and files.

@MainActor
final class AttachmentManager {

    static func pickImages() -> [AttachedImage] {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = true
        panel.canChooseDirectories    = false
        panel.allowedContentTypes     = [.jpeg, .png, .gif, .webP, .heic, .tiff, .bmp]
        panel.message = "Select images to attach"
        guard panel.runModal() == .OK else { return [] }
        return panel.urls.compactMap { loadImage(from: $0) }
    }

    static func pickFiles() -> [URL] {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = true
        panel.canChooseDirectories    = false
        panel.message = "Select files to attach"
        guard panel.runModal() == .OK else { return [] }
        return panel.urls
    }

    static func loadImage(from url: URL) -> AttachedImage? {
        guard let img = NSImage(contentsOf: url) else { return nil }
        return AttachedImage(name: url.lastPathComponent, url: url, nsImage: img)
    }

    static func loadImage(from data: Data, name: String = "paste") -> AttachedImage? {
        guard let img = NSImage(data: data) else { return nil }
        return AttachedImage(name: name, url: nil, nsImage: img)
    }
}
