import AppKit

class LineNumberRulerView: NSRulerView {
    
    var font: NSFont = .monospacedSystemFont(ofSize: 11, weight: .regular)
    var textColor: NSColor = NSColor(white: 0.5, alpha: 1.0)
    var backgroundColor: NSColor = NSColor(red: 0.09, green: 0.09, blue: 0.12, alpha: 1.0)
    
    init(textView: NSTextView) {
        super.init(scrollView: textView.enclosingScrollView!, orientation: .verticalRuler)
        self.clientView = textView
        self.ruleThickness = 40
    }
    
    required init(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
    
    override func drawHashMarksAndLabels(in rect: NSRect) {
        guard let textView = self.clientView as? NSTextView,
              let layoutManager = textView.layoutManager,
              let textContainer = textView.textContainer else { return }
        
        backgroundColor.setFill()
        rect.fill()
        
        let content = textView.string
        let nsString = content as NSString
        let textLength = nsString.length
        
        let visibleRect = self.scrollView!.documentVisibleRect
        let glyphRange = layoutManager.glyphRange(forBoundingRect: visibleRect, in: textContainer)
        let characterRange = layoutManager.characterRange(forGlyphRange: glyphRange, actualGlyphRange: nil)
        
        var lineNumber = 1
        // naive line counting for lines before the visible range
        if characterRange.location > 0 {
            let prefix = nsString.substring(to: characterRange.location)
            lineNumber = prefix.components(separatedBy: .newlines).count
            if prefix.hasSuffix("\n") {
                lineNumber -= 1
            }
        }
        
        var glyphIndexForStringLine = glyphRange.location
        while glyphIndexForStringLine < NSMaxRange(glyphRange) {
            let characterIndex = layoutManager.characterIndexForGlyph(at: glyphIndexForStringLine)
            let lineRange = nsString.lineRange(for: NSRange(location: characterIndex, length: 0))
            
            let lineGlyphRange = layoutManager.glyphRange(forCharacterRange: lineRange, actualCharacterRange: nil)
            
            var lineRect = layoutManager.lineFragmentRect(forGlyphAt: glyphIndexForStringLine, effectiveRange: nil)
            
            let textString = "\(lineNumber)"
            let attrs: [NSAttributedString.Key: Any] = [
                .font: font,
                .foregroundColor: textColor
            ]
            let attrString = NSAttributedString(string: textString, attributes: attrs)
            let size = attrString.size()
            
            let yPos = lineRect.origin.y + textView.textContainerInset.height - visibleRect.origin.y + (lineRect.height - size.height) / 2.0
            let point = NSPoint(x: self.ruleThickness - size.width - 8, y: yPos)
            
            attrString.draw(at: point)
            
            lineNumber += 1
            glyphIndexForStringLine = NSMaxRange(lineGlyphRange)
        }
        
        // Handle empty last line
        if textLength == 0 || nsString.character(at: textLength - 1) == 10 { // \n
            let textString = "\(lineNumber)"
            let attrs: [NSAttributedString.Key: Any] = [
                .font: font,
                .foregroundColor: textColor
            ]
            let attrString = NSAttributedString(string: textString, attributes: attrs)
            let size = attrString.size()
            
            var yPos: CGFloat = 0
            if textLength > 0 {
                let lastGlyph = layoutManager.glyphRange(forCharacterRange: NSRange(location: textLength - 1, length: 1), actualCharacterRange: nil)
                let lineRect = layoutManager.lineFragmentRect(forGlyphAt: lastGlyph.location, effectiveRange: nil)
                yPos = lineRect.origin.y + lineRect.height + textView.textContainerInset.height - visibleRect.origin.y
            } else {
                yPos = textView.textContainerInset.height - visibleRect.origin.y
            }
            
            let point = NSPoint(x: self.ruleThickness - size.width - 8, y: yPos)
            attrString.draw(at: point)
        }
    }
}
