import Foundation

func match(_ text: String, pattern: String) -> String? {
    guard let regex = try? NSRegularExpression(pattern: pattern, options: []),
          let m = regex.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)),
          m.numberOfRanges > 1,
          let r = Range(m.range(at: 1), in: text)
    else { return nil }
    return String(text[r]).trimmingCharacters(in: .whitespaces)
}

let text = """
[SEARCH: Zenn]
"""

let lines = text.components(separatedBy: "\n")
var tools = [String]()
for line in lines {
    let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
    if let m = match(trimmed, pattern: #"^\[SEARCH:\s*([^\]]+)\]$"#) {
        tools.append(m)
    }
}
print("Tools: \(tools)")
