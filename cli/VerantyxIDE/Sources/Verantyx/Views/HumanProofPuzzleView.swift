import SwiftUI

struct HumanProofPuzzleView: View {
    @State private var position: CGPoint = CGPoint(x: 30, y: 30)
    @State private var targetPosition: CGPoint = CGPoint(x: 250, y: 100)
    @State private var isSolved: Bool = false
    @State private var mousePath: [CGPoint] = []
    @State private var startTime: Date? = nil
    @State private var solveDuration: TimeInterval = 0
    @State private var puzzleId = UUID()
    
    var onSolve: (_ entropy: [CGPoint], _ duration: TimeInterval, _ frames: [String]?) -> Void
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: "lock.shield")
                    .foregroundColor(.orange)
                Text("Human Verification Needed")
                    .font(.headline)
                    .foregroundColor(.primary)
            }
            
            Text("BotGuard detected. Please drag the node to the target to authorize autonomous background interaction.")
                .font(.subheadline)
                .foregroundColor(.secondary)
            
            GeometryReader { geo in
                ZStack(alignment: .topLeading) {
                    // Background
                    RoundedRectangle(cornerRadius: 8)
                        .fill(Color.gray.opacity(0.1))
                    
                    // Target area
                    Circle()
                        .fill(Color.green.opacity(0.3))
                        .frame(width: 44, height: 44)
                        .position(targetPosition)
                        .overlay(
                            Circle()
                                .stroke(Color.green.opacity(0.8), style: StrokeStyle(lineWidth: 2, dash: [4]))
                                .frame(width: 44, height: 44)
                                .position(targetPosition)
                        )
                    
                    // Connection line (optional, for visual feedback)
                    Path { path in
                        path.move(to: position)
                        path.addLine(to: targetPosition)
                    }
                    .stroke(Color.gray.opacity(0.2), style: StrokeStyle(lineWidth: 2, dash: [5]))
                    
                    // Draggable piece
                    Circle()
                        .fill(isSolved ? Color.green : Color.accentColor)
                        .frame(width: 36, height: 36)
                        .overlay(
                            Image(systemName: isSolved ? "checkmark" : "hand.draw.fill")
                                .foregroundColor(.white)
                                .font(.system(size: 14, weight: .bold))
                        )
                        .position(position)
                        .gesture(
                            DragGesture()
                                .onChanged { value in
                                    guard !isSolved else { return }
                                    if startTime == nil {
                                        startTime = Date()
                                        // Phase 2: Start lightweight video clipping
                                        Task { @MainActor in
                                            VideoClipManager.shared.startRecording()
                                        }
                                    }
                                    
                                    mousePath.append(value.location)
                                    
                                    // Limit dragging within bounds
                                    let newX = max(18, min(value.location.x, geo.size.width - 18))
                                    let newY = max(18, min(value.location.y, geo.size.height - 18))
                                    position = CGPoint(x: newX, y: newY)
                                }
                                .onEnded { value in
                                    guard !isSolved else { return }
                                    
                                    let dx = position.x - targetPosition.x
                                    let dy = position.y - targetPosition.y
                                    let distance = sqrt(dx*dx + dy*dy)
                                    
                                    if distance < 20 {
                                        withAnimation(.spring()) {
                                            position = targetPosition
                                            isSolved = true
                                        }
                                        solveDuration = Date().timeIntervalSince(startTime ?? Date())
                                        
                                        // Stop video clipping
                                        Task { @MainActor in
                                            let frames = VideoClipManager.shared.stopRecording()
                                            // Delay slighty so user sees the checkmark
                                            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                                                onSolve(mousePath, solveDuration, frames)
                                            }
                                        }
                                    } else {
                                        // Reset puzzle
                                        withAnimation(.spring()) {
                                            position = CGPoint(x: 30, y: 30)
                                            mousePath.removeAll()
                                            startTime = nil
                                            Task { @MainActor in
                                                _ = VideoClipManager.shared.stopRecording()
                                            }
                                        }
                                    }
                                }
                        )
                }
                .onAppear {
                    randomizePuzzle(in: geo.size)
                }
                .onChange(of: puzzleId) { _, _ in
                    randomizePuzzle(in: geo.size)
                }
            }
            .frame(height: 160) // Taller frame for 2D interaction
        }
        .padding()
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(12)
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .strokeBorder(Color.orange.opacity(0.5), lineWidth: 1)
        )
    }
    
    private func randomizePuzzle(in size: CGSize) {
        guard size.width > 100 && size.height > 100 else { return }
        // Ensure the target is sufficiently far away from the start (30, 30)
        let minDistance: CGFloat = 80
        var tx: CGFloat = 0
        var ty: CGFloat = 0
        var dist: CGFloat = 0
        
        while dist < minDistance {
            tx = CGFloat.random(in: 40...(size.width - 40))
            ty = CGFloat.random(in: 40...(size.height - 40))
            let dx = tx - 30
            let dy = ty - 30
            dist = sqrt(dx*dx + dy*dy)
        }
        
        targetPosition = CGPoint(x: tx, y: ty)
        position = CGPoint(x: 30, y: 30)
        isSolved = false
        mousePath.removeAll()
        startTime = nil
    }
}
