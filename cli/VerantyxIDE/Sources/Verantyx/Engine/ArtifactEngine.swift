import Foundation
import SwiftUI

// MARK: - OperationMode
// Controls the overall agent behavior:
//   .aiPriority    — no confirmations, no MCP timeouts, full-screen Gemini-style UI
//   .human         — standard confirmations, 60s MCP timeout, 4-pane IDE layout
//   .humanPriority — VS Code-style: FileTree | CodeEditor | AI chat (right)
//   .gatekeeper    — Local LLM as Commander; external API sees JCross IR only

enum OperationMode: String, CaseIterable, Codable, Identifiable {
    case gatekeeper    = "Gatekeeper"

    var id: String { rawValue }

    var icon: String {
        switch self {
        case .gatekeeper:    return "shield.lefthalf.filled"
        }
    }

    var accentColor: Color {
        switch self {
        case .gatekeeper:    return Color(red: 0.2,  green: 0.9,  blue: 0.5)
        }
    }

    var description: String {
        switch self {
        case .gatekeeper:
            return L("Enterprise Gatekeeper IDE", "エンタープライズ向け Gatekeeper IDE")
        }
    }
    
    var displayName: String {
        switch self {
        case .gatekeeper:    return L("Gatekeeper", "ゲートキーパー")
        }
    }

    /// Short 2-letter badge displayed in the toolbar chip
    var badge: String {
        switch self {
        case .gatekeeper:    return "GK"
        }
    }

    /// Next mode in the cycle
    var next: OperationMode {
        return .gatekeeper
    }
}

// MARK: - Artifact
// A self-contained renderable output block extracted from AI response.

struct Artifact: Identifiable {
    let id: UUID
    let type: ArtifactType
    var content: String
    var title: String
    var createdAt: Date

    init(id: UUID = UUID(), type: ArtifactType, content: String, title: String = "") {
        self.id        = id
        self.type      = type
        self.content   = content
        self.title     = title.isEmpty ? type.defaultTitle : title
        self.createdAt = Date()
    }

    enum ArtifactType: String {
        case html     = "html"
        case markdown = "markdown"
        case mermaid  = "mermaid"
        case code     = "code"
        case svg      = "svg"
        case browser  = "browser"

        var defaultTitle: String {
            switch self {
            case .html:     return "HTML Preview"
            case .markdown: return "Markdown"
            case .mermaid:  return "Diagram"
            case .code:     return "Code"
            case .svg:      return "SVG"
            case .browser:  return "Live Browser"
            }
        }

        var icon: String {
            switch self {
            case .html:     return "globe"
            case .markdown: return "doc.richtext"
            case .mermaid:  return "arrow.triangle.branch"
            case .code:     return "chevron.left.forwardslash.chevron.right"
            case .svg:      return "squareshape.controlhandles.on.squareshape.controlhandles"
            case .browser:  return "safari"
            }
        }

        // Whether this type can be live-rendered in WKWebView
        var isWebRenderable: Bool {
            return true  // ALL types are rendered via WKWebView (code uses highlight.js)
        }

        static func detect(from tag: String) -> ArtifactType {
            let t = tag.lowercased()
            if t.contains("html")                        { return .html }
            if t.contains("mermaid")                     { return .mermaid }
            if t.contains("markdown") || t.contains("md") { return .markdown }
            if t.contains("svg")                         { return .svg }
            return .code
        }
    }
}

// MARK: - ArtifactParser
// Detects <artifact> ... </artifact> blocks in streamed AI output.
// Supports both complete and incremental (streaming) parsing.

enum ArtifactParser {

    // Extract the last (or only) artifact from a complete AI response string.
    // Priority: <artifact> tag > ``` code block > markdown detection
    static func extract(from text: String) -> Artifact? {
        // 1. Try <artifact> tag first (explicit)
        if let art = extractFromTag(text) { return art }

        // 2. Fallback: fenced code block (```lang ... ```)
        if let art = extractFromCodeBlock(text) { return art }

        return nil
    }

    // MARK: - <artifact> tag parser (original)
    static func extractFromTag(_ text: String) -> Artifact? {
        // Pattern: <artifact type="html" title="My Page"> ... </artifact>
        let pattern = #"<artifact(?:\s+type=\"([^\"]*?)\")?(?:\s+title=\"([^\"]*?)\")?\s*>([\s\S]*?)</artifact>"#
        guard let regex = try? NSRegularExpression(pattern: pattern, options: .dotMatchesLineSeparators),
              let match = regex.firstMatch(in: text, range: NSRange(text.startIndex..., in: text))
        else { return nil }

        let typeName  = match.group(1, in: text) ?? "html"
        let title     = match.group(2, in: text) ?? ""
        let content   = (match.group(3, in: text) ?? "").trimmingCharacters(in: .whitespacesAndNewlines)

        let artType = Artifact.ArtifactType.detect(from: typeName)
        return Artifact(type: artType, content: content, title: title)
    }

    // MARK: - Fenced code block fallback (``` lang ... ```)
    // Picks the LARGEST code block in the response (most likely the main output)
    static func extractFromCodeBlock(_ text: String) -> Artifact? {
        // Match fenced code blocks: ```lang\ncode\n```
        let pattern = #"```(\w*)\n([\s\S]*?)```"#
        guard let regex = try? NSRegularExpression(pattern: pattern, options: .dotMatchesLineSeparators)
        else { return nil }

        let matches = regex.matches(in: text, range: NSRange(text.startIndex..., in: text))
        guard !matches.isEmpty else { return nil }

        // Pick the largest block (most content)
        let best = matches.max { a, b in
            let aLen = Range(a.range(at: 2), in: text).map { text[$0].count } ?? 0
            let bLen = Range(b.range(at: 2), in: text).map { text[$0].count } ?? 0
            return aLen < bLen
        }

        guard let match = best,
              let langRange    = Range(match.range(at: 1), in: text),
              let contentRange = Range(match.range(at: 2), in: text)
        else { return nil }

        let lang    = String(text[langRange]).lowercased()
        let content = String(text[contentRange])
            .trimmingCharacters(in: .whitespacesAndNewlines)

        // Too short to bother showing
        guard content.count > 20 else { return nil }

        // Map language string → ArtifactType
        let artType: Artifact.ArtifactType
        switch lang {
        case "html", "htm":              artType = .html
        case "mermaid":                  artType = .mermaid
        case "svg":                      artType = .svg
        case "md", "markdown":           artType = .markdown
        default:                         artType = .code
        }

        let title = lang.isEmpty ? "Code" : lang.capitalized
        return Artifact(type: artType, content: content, title: title)
    }

    // Strip <artifact> tags from the display-facing text (so chat doesn't show raw tags)
    static func stripArtifactTags(from text: String) -> String {
        let pattern = #"<artifact[^>]*>[\s\S]*?</artifact>"#
        guard let regex = try? NSRegularExpression(pattern: pattern, options: .dotMatchesLineSeparators)
        else { return text }
        return regex.stringByReplacingMatches(
            in: text, range: NSRange(text.startIndex..., in: text), withTemplate: ""
        ).trimmingCharacters(in: .whitespacesAndNewlines)
    }

    // Check if a streaming buffer has a complete artifact block
    static func hasCompleteArtifact(in buffer: String) -> Bool {
        buffer.contains("<artifact") && buffer.contains("</artifact>")
    }

    // Check if streaming has started an artifact (but not closed it yet)
    static func isStreamingArtifact(in buffer: String) -> Bool {
        buffer.contains("<artifact") && !buffer.contains("</artifact>")
    }
}

private extension NSTextCheckingResult {
    func group(_ index: Int, in text: String) -> String? {
        guard index < numberOfRanges,
              let r = Range(range(at: index), in: text),
              !r.isEmpty else { return nil }
        return String(text[r])
    }
}

// MARK: - PatchFileParser
// Detects [PATCH_FILE: relative/path.swift] ... ``` blocks produced by
// the Self-Evolution system prompt and registers them as FilePatch objects.

enum PatchFileParser {

    /// Extract all (relativePath, content) pairs from an AI response.
    /// Expected format:
    ///   [PATCH_FILE: Sources/Verantyx/Views/SomeView.swift]
    ///   ```swift
    ///   // ... content ...
    ///   ```
    static func extract(from text: String) -> [(relativePath: String, content: String)] {
        let pattern = #"\[PATCH_FILE:\s*([^\]]+)\]\s*```(?:swift|)?\n([\s\S]*?)```"#
        guard let regex = try? NSRegularExpression(pattern: pattern, options: .dotMatchesLineSeparators)
        else { return [] }

        let range = NSRange(text.startIndex..., in: text)
        let matches = regex.matches(in: text, range: range)

        return matches.compactMap { m -> (String, String)? in
            guard let pathRange    = Range(m.range(at: 1), in: text),
                  let contentRange = Range(m.range(at: 2), in: text)
            else { return nil }
            let path    = String(text[pathRange]).trimmingCharacters(in: .whitespaces)
            let content = String(text[contentRange])
            return (path, content)
        }
    }

    /// Strip [PATCH_FILE:...] blocks from chat display text.
    static func strip(from text: String) -> String {
        let pattern = #"\[PATCH_FILE:[^\]]+\]\s*```(?:swift|)?[\s\S]*?```"#
        guard let regex = try? NSRegularExpression(pattern: pattern, options: .dotMatchesLineSeparators)
        else { return text }
        return regex.stringByReplacingMatches(
            in: text, range: NSRange(text.startIndex..., in: text), withTemplate: ""
        ).trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
