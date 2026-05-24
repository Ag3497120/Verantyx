import Foundation
import AppKit

// MARK: - CognitiveAnchorEngine
//
// ユーザーへの迎合性（Sycophancy）を打破するため、LLM の Vision Encoder に
// 視覚的アンカー（動的生成画像や1x1ピクセル）を注入するエンジン。
//
// [Modality Hacking の効果]
// 1. Temporal Anchor (時間軸アンカー): 現在日時をデカデカと描画した画像を渡すことで、知識カットオフの自信をVeto(拒否)する。
// 2. Search Force: 「SEARCH REQUIRED」という警告画像を渡し、テキストより視覚情報を優先させてツール発火を強制する。

public enum CognitiveAnchorMode {
    case doubt       // 疑念モード（ユーザーの報告を盲信せず検証する。赤色の視覚アンカー）
    case logic       // 論理モード（ASTと純粋な事実だけを見る。青色の視覚アンカー）
    case searchForce // 検索強制モード（[SEARCH REQUIRED] の警告画像）
    case temporal    // 時間軸強制モード（現在の日時を描画し、未来知識の欠如を自覚させる）
    case memoryDeficit // メモリ欠損モード（L1-L3未ヒット時の自動補完強制）
    case swarmCommander // Swarm司令官モード（自己実行を禁止し、全てをSwarmに委譲させる）
}

public actor CognitiveAnchorEngine {
    public static let shared = CognitiveAnchorEngine()
    
    // Store the last screenshot taken by VISION tools
    public var lastVisionScreenshot: String? = nil
    
    public func setVisionScreenshot(_ base64: String) {
        lastVisionScreenshot = base64
    }
    
    public func consumeVisionScreenshot() -> String? {
        let screenshot = lastVisionScreenshot
        lastVisionScreenshot = nil
        return screenshot
    }
    
    private init() {}
    
    // MARK: - Base64 Image Constants
    
    // 1x1 Red PNG
    private let redPixelBase64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    
    // 1x1 Blue PNG
    private let bluePixelBase64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    
    // MARK: - Anchor Retrieval
    
    /// 指定された認知状態に対応する極小または動的生成のBase64画像文字列を返す
    public func getAnchor(for mode: CognitiveAnchorMode) -> String {
        switch mode {
        case .doubt:
            return renderDynamicAnchor(
                text: "DOUBT / VERIFY",
                backgroundColor: NSColor.red,
                textColor: NSColor.white,
                width: 128, height: 128
            ) ?? ""
        case .logic:
            return renderDynamicAnchor(
                text: "LOGIC ONLY",
                backgroundColor: NSColor.blue,
                textColor: NSColor.white,
                width: 128, height: 128
            ) ?? ""
        case .searchForce:
            return renderDynamicAnchor(
                text: "[ SEARCH REQUIRED ]\nKNOWLEDGE BOUNDARY DETECTED",
                backgroundColor: NSColor.systemYellow,
                textColor: NSColor.black
            ) ?? ""
        case .temporal:
            let formatter = DateFormatter()
            formatter.dateFormat = "yyyy-MM-dd HH:mm"
            let nowStr = formatter.string(from: Date())
            return renderDynamicAnchor(
                text: "CURRENT TIME:\n\(nowStr)\nKNOWLEDGE OUTDATED.\nYOU MUST USE WEB SEARCH.",
                backgroundColor: NSColor.black,
                textColor: NSColor.green
            ) ?? ""
        case .memoryDeficit:
            return renderDynamicAnchor(
                text: "[ MEMORY DEFICIT ]\nL1-L3 CACHE MISS.\nSEARCH REQUIRED TO AUTO-COMPLETE.",
                backgroundColor: NSColor.systemPurple,
                textColor: NSColor.white
            ) ?? ""
        case .swarmCommander:
            return renderDynamicAnchor(
                text: "🔥 ROUTER MODE ACTIVE 🔥\nEXECUTION FORBIDDEN.\nDELEGATE ALL TASKS TO SWARM.",
                backgroundColor: NSColor(red: 0.8, green: 0.0, blue: 0.0, alpha: 1.0),
                textColor: NSColor.white
            ) ?? ""
        }
    }
    
    /// 任意のテキストを含むカスタム視覚アンカーを生成する
    public func getCustomAnchor(title: String = "CRITICAL DIRECTIVE", text: String) -> String {
        return renderDynamicAnchor(
            text: "[\(title)]\n\n" + text,
            backgroundColor: NSColor(red: 0.8, green: 0.0, blue: 0.0, alpha: 1.0),
            textColor: NSColor.white
        ) ?? ""
    }
    
    /// 現在のプロンプトのコンテキスト（文字やツール利用状況）から、
    /// 注入すべき認知アンカーを判定する。
    public func evaluateAnchorMode(instruction: String, memorySection: String = "", isSwarmMode: Bool = false) -> CognitiveAnchorMode? {
        if isSwarmMode {
            return .swarmCommander
        }

        if memorySection.contains("DEFICIT DETECTED") {
            return .memoryDeficit
        }

        let lower = instruction.lowercased()
        
        // 1. 時間軸・最新情報への言及があればTemporal Anchor
        if lower.contains("最新") || lower.contains("latest") || lower.contains("今年") || lower.contains("現在") {
            return .temporal
        }
        
        // 2. バグ報告や「直して」などの文脈がある場合はDoubt（疑念）モードを適用
        if lower.contains("バグ") || lower.contains("bug") || lower.contains("error") || lower.contains("エラー") || lower.contains("直して") {
            return .doubt
        }
        
        // 3. それ以外のすべてのタスク（コーディング指示含む）では、
        // 実装前の事実確認とハルシネーション防止のために常にSearchForceモードを適用する。
        return .searchForce
    }
    
    // MARK: - Dynamic Image Generation
    
    /// 動的にテキストを描画した画像を生成し、PNG Base64 として返す
    private func renderDynamicAnchor(text: String, backgroundColor: NSColor, textColor: NSColor, width: CGFloat = 800, height: CGFloat? = nil) -> String? {
        // Set up attributes
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
        
        // Calculate needed height if not provided
        let textWidth = width - 80 // 40px padding on each side
        let boundingRect = attributedString.boundingRect(
            with: NSSize(width: textWidth, height: .greatestFiniteMagnitude),
            options: [.usesLineFragmentOrigin, .usesFontLeading]
        )
        
        let finalHeight = height ?? max(400, boundingRect.height + 80)
        let size = NSSize(width: width, height: finalHeight)
        let image = NSImage(size: size)
        
        image.lockFocus()
        
        // Background
        backgroundColor.setFill()
        let rect = NSRect(origin: .zero, size: size)
        rect.fill()
        
        // Noise effect
        for _ in 0..<100 {
            let path = NSBezierPath()
            path.move(to: NSPoint(x: CGFloat.random(in: 0...width), y: CGFloat.random(in: 0...finalHeight)))
            path.line(to: NSPoint(x: CGFloat.random(in: 0...width), y: CGFloat.random(in: 0...finalHeight)))
            NSColor(calibratedWhite: CGFloat.random(in: 0...1), alpha: 0.15).setStroke()
            path.stroke()
        }
        
        // Draw Text
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
        
        return pngData.base64EncodedString()
    }
}
