import Foundation
import AppKit

func renderDynamicAnchor(text: String, backgroundColor: NSColor, textColor: NSColor, width: CGFloat = 800, height: CGFloat? = nil) -> Data? {
    let paragraphStyle = NSMutableParagraphStyle()
    paragraphStyle.alignment = .left
    paragraphStyle.lineBreakMode = .byWordWrapping
    
    let font = NSFont.monospacedSystemFont(ofSize: 20, weight: .bold)
    let attributes: [NSAttributedString.Key: Any] = [
        .font: font,
        .foregroundColor: textColor,
        .paragraphStyle: paragraphStyle
    ]
    
    let attributedString = NSAttributedString(string: text, attributes: attributes)
    
    let textWidth = width - 80
    let boundingRect = attributedString.boundingRect(
        with: NSSize(width: textWidth, height: .greatestFiniteMagnitude),
        options: [.usesLineFragmentOrigin, .usesFontLeading]
    )
    
    let finalHeight = height ?? max(400, boundingRect.height + 80)
    let size = NSSize(width: width, height: finalHeight)
    let image = NSImage(size: size)
    
    image.lockFocus()
    
    backgroundColor.setFill()
    let rect = NSRect(origin: .zero, size: size)
    rect.fill()
    
    for _ in 0..<100 {
        let path = NSBezierPath()
        path.move(to: NSPoint(x: CGFloat.random(in: 0...width), y: CGFloat.random(in: 0...finalHeight)))
        path.line(to: NSPoint(x: CGFloat.random(in: 0...width), y: CGFloat.random(in: 0...finalHeight)))
        NSColor(calibratedWhite: CGFloat.random(in: 0...1), alpha: 0.15).setStroke()
        path.stroke()
    }
    
    let textRect = NSRect(
        x: 40,
        y: size.height - boundingRect.height - 40,
        width: textWidth,
        height: boundingRect.height
    )
    
    attributedString.draw(with: textRect, options: [.usesLineFragmentOrigin, .usesFontLeading])
    
    image.unlockFocus()
    
    guard let tiffData = image.tiffRepresentation,
          let bitmapImage = NSBitmapImageRep(data: tiffData),
          let pngData = bitmapImage.representation(using: .png, properties: [:]) else {
        return nil
    }
    
    return pngData
}

let mockSkillText = """
[ 🔧 SKILL SYSTEM ACTIVE ]

── §スキルライブラリ SKILL LIBRARY (技: 習得済みスキル) ──────────────────────
以下のスキルは過去の成功体験から自動生成されたカスタムツールです。
該当タスクでは必ず組み込みツールより先に呼び出してください。

呼び出し構文: [USE_SKILL: スキル名]
パラメータ付き: [USE_SKILL: スキル名|key=val|key=val]

  🔧 scaffold_react_app  v2 ✦蒸留
     └─ Creates a Vite+React+TypeScript app with Tailwind config.
        tags: react, vite, tailwind
        ✅ 15 wins | ❌ 1 fails

  🔧 deploy_staging  v5 ★共有
     └─ Builds the project and pushes to staging server via SSH.
        tags: deploy, staging, build
        ✅ 42 wins | ❌ 3 fails
"""

if let pngData = renderDynamicAnchor(text: mockSkillText, backgroundColor: NSColor.systemTeal, textColor: NSColor.black) {
    let url = URL(fileURLWithPath: "/Users/motonishikoudai/.gemini/antigravity/brain/34fda5b6-a8cb-44e7-a268-81365465c046/mock_skill_anchor.png")
    try! pngData.write(to: url)
    print("Saved to \\(url.path)")
} else {
    print("Failed")
}
