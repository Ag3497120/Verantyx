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

    /// Copy a sent image into the transcript cache so the message keeps a
    /// renderable thumbnail after the composer clears or a temporary drag/drop
    /// file disappears.  This is presentation history, not Vera evidence.
    static func transcriptAttachment(for image: AttachedImage) -> ChatMessage.Attachment? {
        if let url = image.url,
           let copied = cacheTranscriptImage(source: url, preferredName: image.name) {
            return copied
        }
        guard let tiff = image.nsImage.tiffRepresentation,
              let bitmap = NSBitmapImageRep(data: tiff),
              let png = bitmap.representation(using: .png, properties: [:])
        else { return nil }
        let name = image.name.isEmpty ? "image.png" : image.name
        let destination = transcriptCacheDirectory
            .appendingPathComponent("\(UUID().uuidString)-\(safeFilename(name, fallbackExtension: "png"))")
        do {
            try png.write(to: destination, options: .atomic)
            return ChatMessage.Attachment(kind: .image, name: name,
                                          path: destination.path)
        } catch {
            return nil
        }
    }

    static func transcriptAttachment(forImagePath path: String) -> ChatMessage.Attachment? {
        let source = URL(fileURLWithPath: path)
        return cacheTranscriptImage(source: source,
                                    preferredName: source.lastPathComponent)
    }

    private static var transcriptCacheDirectory: URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory,
                                            in: .userDomainMask)[0]
            .appendingPathComponent("Verantyx/chat-attachments", isDirectory: true)
        try? FileManager.default.createDirectory(at: base,
                                                 withIntermediateDirectories: true)
        return base
    }

    private static func cacheTranscriptImage(source: URL,
                                             preferredName: String) -> ChatMessage.Attachment? {
        guard FileManager.default.fileExists(atPath: source.path),
              NSImage(contentsOf: source) != nil else { return nil }
        let safe = safeFilename(preferredName,
                                fallbackExtension: source.pathExtension.isEmpty
                                    ? "png" : source.pathExtension)
        let destination = transcriptCacheDirectory
            .appendingPathComponent("\(UUID().uuidString)-\(safe)")
        do {
            try FileManager.default.copyItem(at: source, to: destination)
            return ChatMessage.Attachment(kind: .image,
                                          name: preferredName,
                                          path: destination.path)
        } catch {
            return nil
        }
    }

    private static func safeFilename(_ raw: String,
                                     fallbackExtension: String) -> String {
        let cleaned = raw.map { character -> Character in
            character.isLetter || character.isNumber || ".-_".contains(character)
                ? character : "_"
        }
        var name = String(cleaned).trimmingCharacters(in: CharacterSet(charactersIn: "."))
        if name.isEmpty { name = "image.\(fallbackExtension)" }
        if URL(fileURLWithPath: name).pathExtension.isEmpty {
            name += ".\(fallbackExtension)"
        }
        return name
    }

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
