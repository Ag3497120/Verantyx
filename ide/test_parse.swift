import Foundation

func match(_ text: String, pattern: String) -> String? {
    guard let regex = try? NSRegularExpression(pattern: pattern, options: []),
          let m = regex.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)),
          m.numberOfRanges > 1,
          let r = Range(m.range(at: 1), in: text)
    else { return nil }
    return String(text[r]).trimmingCharacters(in: .whitespaces)
}

let m = match("[SEARCH: Zenn]", pattern: "^(?:\\[SEARCH:\\[)?\\[SEARCH:\\s*([^\\]]+)\\]$")
print("Result: \(String(describing: m))")

let m2 = match("[SEARCH: Zenn]", pattern: "^\\[SEARCH:\\s*([^\\]]+)\\]$")
print("Result2: \(String(describing: m2))")
