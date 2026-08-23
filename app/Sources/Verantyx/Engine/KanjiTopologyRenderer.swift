import Foundation
import SwiftUI
import CoreGraphics
import AppKit

// MARK: - KanjiTopologyRenderer
// Renders the L3.5 OS Asset Map as a Kanji Topology image to avoid LLM context overload.

@MainActor
final class KanjiTopologyRenderer {
    
    static func renderToPNG(map: OSAssetMap) -> Data? {
        let width: CGFloat = 1024
        let height: CGFloat = 1024
        
        let view = KanjiTopologyView(map: map)
            .frame(width: width, height: height)
        
        let renderer = ImageRenderer(content: view)
        renderer.scale = 2.0 // High resolution
        
        guard let nsImage = renderer.nsImage,
              let tiffData = nsImage.tiffRepresentation,
              let bitmapImage = NSBitmapImageRep(data: tiffData),
              let pngData = bitmapImage.representation(using: .png, properties: [:]) else {
            return nil
        }
        
        return pngData
    }
}

struct KanjiTopologyView: View {
    let map: OSAssetMap
    
    var body: some View {
        ZStack {
            Color(red: 0.1, green: 0.1, blue: 0.12).ignoresSafeArea() // Dark background
            
            // Draw grid
            Path { path in
                for i in 0...10 {
                    let x = CGFloat(i) * 100
                    path.move(to: CGPoint(x: x, y: 0))
                    path.addLine(to: CGPoint(x: x, y: 1024))
                    path.move(to: CGPoint(x: 0, y: x))
                    path.addLine(to: CGPoint(x: 1024, y: x))
                }
            }
            .stroke(Color.white.opacity(0.05), lineWidth: 1)
            
            // Cluster by category
            let clusters = Dictionary(grouping: map.entries.values, by: { $0.category })
            let sortedCategories = clusters.keys.sorted()
            
            ForEach(Array(sortedCategories.enumerated()), id: \.element) { index, category in
                let angle = (Double(index) / Double(max(1, sortedCategories.count))) * 2 * .pi
                let radius: Double = 350.0
                let cx = 512.0 + cos(angle) * radius
                let cy = 512.0 + sin(angle) * radius
                
                let kanji = categoryToKanji(category)
                let entries = clusters[category] ?? []
                let count = entries.count
                
                // Draw line to center
                Path { path in
                    path.move(to: CGPoint(x: 512, y: 512))
                    path.addLine(to: CGPoint(x: cx, y: cy))
                }
                .stroke(Color.blue.opacity(0.3), lineWidth: 2)
                
                // Draw node
                Circle()
                    .fill(Color.black)
                    .frame(width: 80, height: 80)
                    .overlay(Circle().stroke(Color.blue.opacity(0.8), lineWidth: 2))
                    .position(x: cx, y: cy)
                
                Text(kanji)
                    .font(.system(size: 40, weight: .bold))
                    .foregroundStyle(.white)
                    .position(x: cx, y: cy - 10)
                
                Text("\(count) items")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(Color(red: 0.6, green: 0.8, blue: 1.0))
                    .position(x: cx, y: cy + 25)
                
                Text(category)
                    .font(.system(size: 12))
                    .foregroundStyle(.gray)
                    .position(x: cx, y: cy + 45)
                    
                // Optional: show some top items from this category as text
                let topItems = Array(entries.prefix(5))
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(topItems, id: \.id) { item in
                        Text(item.name)
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(Color.white.opacity(0.7))
                            .lineLimit(1)
                            .truncationMode(.tail)
                            .frame(width: 200, alignment: .leading)
                    }
                }
                .position(x: cx + (cos(angle) * 150), y: cy + (sin(angle) * 80))
            }
            
            // Center Core
            Circle()
                .fill(Color(red: 0.15, green: 0.2, blue: 0.3))
                .frame(width: 120, height: 120)
                .overlay(Circle().stroke(Color.cyan, lineWidth: 3))
                .position(x: 512, y: 512)
            
            Text(L("Core", "核"))
                .font(.system(size: 50, weight: .black))
                .foregroundStyle(Color.cyan)
                .position(x: 512, y: 500)
            Text("OS ASSET")
                .font(.system(size: 14, weight: .bold))
                .foregroundStyle(.white)
                .position(x: 512, y: 540)
            
            // Top Title
            VStack(alignment: .leading) {
                Text("L3.5 OS Asset Kanji Topology")
                    .font(.system(size: 28, weight: .bold, design: .monospaced))
                    .foregroundStyle(.white)
                Text("Total Managed Assets: \(map.entries.count) entries")
                    .font(.system(size: 18, design: .monospaced))
                    .foregroundStyle(.cyan)
                Text("Generated: \(map.generatedAt)")
                    .font(.system(size: 14, design: .monospaced))
                    .foregroundStyle(.gray)
            }
            .position(x: 300, y: 100)
        }
    }
    
    private func categoryToKanji(_ category: String) -> String {
        switch category.lowercased() {
        case _ where category.contains("user"): return "人"
        case _ where category.contains("system"): return "基"
        case _ where category.contains("library"): return "庫"
        case _ where category.contains("app"): return "応"
        case _ where category.contains("util"): return "具"
        default: return "他"
        }
    }
}
