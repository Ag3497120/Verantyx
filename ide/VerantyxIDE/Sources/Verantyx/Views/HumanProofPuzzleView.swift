import SwiftUI

// MARK: - One drag, captured as data
//
// Two things used this view and they want opposite behaviour. Mid-run it was a
// gate: solve once, the run continues. In settings it is a capture tool, and
// there the useful session is many drags in a row — closing and reopening a
// sheet between each one costs more clicks than the drag itself and makes a
// dataset of eight feel like a chore.
//
// `continuous` is that difference. When set, a solve re-arms immediately with
// fresh geometry instead of ending, and the count is reported so the user can
// watch the dataset fill.
//
// ── Why the geometry is re-randomised, not just the target ────────────────
//
// The first version always started the node at (30, 30). Every sample was
// therefore a path from the same corner, and a dataset of those teaches the
// motion model exactly one gesture: leave the top-left, arrive somewhere. The
// agent needs to move between arbitrary pairs of points, so the samples have
// to span arbitrary pairs. Start and target are both placed at random now,
// with a minimum separation so a sample is never a twitch.
struct HumanProofPuzzleView: View {

    /// Re-arm after each solve instead of finishing. Settings capture uses
    /// this; the mid-run gate does not.
    var continuous: Bool = false

    var onSolve: (_ entropy: [CGPoint], _ duration: TimeInterval, _ frames: [String]?) -> Void

    @State private var position: CGPoint = CGPoint(x: 30, y: 30)
    @State private var targetPosition: CGPoint = CGPoint(x: 250, y: 100)
    @State private var isSolved: Bool = false
    @State private var mousePath: [CGPoint] = []
    @State private var startTime: Date? = nil
    @State private var solveDuration: TimeInterval = 0
    @State private var puzzleId = UUID()
    @State private var solvedThisSession = 0
    @State private var lastPointCount = 0

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: continuous ? "hand.draw" : "lock.shield")
                    .foregroundColor(.orange)
                Text(continuous ? "人間の操作データを記録中" : "Human Verification Needed")
                    .font(.headline)
                    .foregroundColor(.primary)
                Spacer()
                if continuous && solvedThisSession > 0 {
                    Text("\(solvedThisSession) 件")
                        .font(.system(size: 12, weight: .bold, design: .monospaced))
                        .foregroundColor(.green)
                }
            }

            Text(continuous
                 ? "ノードを的まで運ぶと1件記録され、すぐ次が出ます。いつも通りの速さで、まっすぐでも回り込んでも構いません。"
                 : "BotGuard detected. Please drag the node to the target to authorize autonomous background interaction.")
                .font(.subheadline)
                .foregroundColor(.secondary)

            GeometryReader { geo in
                ZStack(alignment: .topLeading) {
                    RoundedRectangle(cornerRadius: 8)
                        .fill(Color.gray.opacity(0.1))

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

                    Path { path in
                        path.move(to: position)
                        path.addLine(to: targetPosition)
                    }
                    .stroke(Color.gray.opacity(0.2), style: StrokeStyle(lineWidth: 2, dash: [5]))

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
                                        // Frame capture is for the mid-run gate. A
                                        // long capture session does not need — and
                                        // should not silently accumulate — video.
                                        if !continuous {
                                            Task { @MainActor in
                                                VideoClipManager.shared.startRecording()
                                            }
                                        }
                                    }

                                    mousePath.append(value.location)

                                    let newX = max(18, min(value.location.x, geo.size.width - 18))
                                    let newY = max(18, min(value.location.y, geo.size.height - 18))
                                    position = CGPoint(x: newX, y: newY)
                                }
                                .onEnded { _ in
                                    guard !isSolved else { return }

                                    let dx = position.x - targetPosition.x
                                    let dy = position.y - targetPosition.y
                                    let distance = sqrt(dx*dx + dy*dy)

                                    guard distance < 22 else {
                                        // Missed. Re-arm the same puzzle rather
                                        // than recording a path that never
                                        // arrived — a sample that missed teaches
                                        // the model to miss.
                                        withAnimation(.spring()) {
                                            mousePath.removeAll()
                                            startTime = nil
                                        }
                                        if !continuous {
                                            Task { @MainActor in
                                                _ = VideoClipManager.shared.stopRecording()
                                            }
                                        }
                                        return
                                    }

                                    withAnimation(.spring()) {
                                        position = targetPosition
                                        isSolved = true
                                    }
                                    solveDuration = Date().timeIntervalSince(startTime ?? Date())
                                    lastPointCount = mousePath.count
                                    let captured = mousePath

                                    if continuous {
                                        solvedThisSession += 1
                                        onSolve(captured, solveDuration, nil)
                                        // Long enough to register as done, short
                                        // enough not to break the rhythm.
                                        DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) {
                                            puzzleId = UUID()
                                        }
                                    } else {
                                        Task { @MainActor in
                                            let frames = VideoClipManager.shared.stopRecording()
                                            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                                                onSolve(captured, solveDuration, frames)
                                            }
                                        }
                                    }
                                }
                        )
                }
                .onAppear { randomizePuzzle(in: geo.size) }
                .onChange(of: puzzleId) { _, _ in randomizePuzzle(in: geo.size) }
            }
            .frame(height: 160)

            if continuous && lastPointCount > 0 {
                Text("直前の記録: \(lastPointCount) 点")
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(.tertiary)
            }
        }
        .padding()
        .background(Color(NSColor.controlBackgroundColor))
        .cornerRadius(12)
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .strokeBorder(Color.orange.opacity(0.5), lineWidth: 1)
        )
    }

    /// Both endpoints move. See the note at the top of the file: a dataset
    /// that always starts in one corner only describes that corner.
    private func randomizePuzzle(in size: CGSize) {
        guard size.width > 100 && size.height > 100 else { return }
        // Far enough apart that the drag has shape to it. Scaled to the box so
        // it stays sensible if the sheet is resized.
        let minDistance = max(80, min(size.width, size.height) * 0.55)

        var start = CGPoint(x: 30, y: 30)
        var target = CGPoint(x: size.width - 40, y: size.height - 40)
        for _ in 0..<40 {
            let s = CGPoint(x: .random(in: 26...(size.width - 26)),
                            y: .random(in: 26...(size.height - 26)))
            let t = CGPoint(x: .random(in: 40...(size.width - 40)),
                            y: .random(in: 40...(size.height - 40)))
            if hypot(t.x - s.x, t.y - s.y) >= minDistance { start = s; target = t; break }
        }

        targetPosition = target
        position = start
        isSolved = false
        mousePath.removeAll()
        startTime = nil
    }
}
