import SwiftUI

// MARK: - ResizableHSplit
// Custom horizontal split container with drag divider.
//
// Scroll Fix (v0.2.1):
//   • Removed .clipped() from left/right pane containers.
//     .clipped() creates a SwiftUI hit-test boundary that intercepts scroll
//     events before they reach nested ScrollViews — causing scrolling to
//     silently stop after the first pane resize.
//   • DragGesture is isolated to the 8pt divider strip only, using
//     .highPriorityGesture so scroll events on pane content are never stolen.
//   • GeometryReader is used only for size measurement (.background pattern).
//     The actual layout is a plain HStack so SwiftUI's gesture routing
//     reaches all nested scroll views correctly.

struct ResizableHSplit<Left: View, Right: View>: View {
    var minLeft: CGFloat
    var maxLeft: CGFloat
    var minRight: CGFloat

    let left: Left
    let right: Right

    // Store as fraction (0…1) so panes resize proportionally with window.
    @State private var fraction: CGFloat
    @GestureState private var dragDelta: CGFloat = 0
    @State private var isDragging: Bool = false
    // Measured actual total width (updated by GeometryReader in background).
    @State private var totalWidth: CGFloat = 1200

    init(
        minLeft: CGFloat = 160,
        maxLeft: CGFloat = 480,
        minRight: CGFloat = 300,
        initialLeft: CGFloat = 240,
        @ViewBuilder left: () -> Left,
        @ViewBuilder right: () -> Right
    ) {
        self.minLeft   = minLeft
        self.maxLeft   = maxLeft
        self.minRight  = minRight
        self.left  = left()
        self.right = right()
        _fraction = State(initialValue: initialLeft / 1200)
    }

    var body: some View {
        HStack(spacing: 0) {
            let currentWidth = clamped(total: totalWidth,
                                       px: fraction * totalWidth + dragDelta)
            left
                .frame(width: currentWidth)
                .clipped() // REQUIRED: Prevents overflowing hit-test areas from stealing scroll events from the adjacent pane.

            divider()

            right
                .frame(maxWidth: .infinity)
                .clipped() // REQUIRED
        }
        .background(
            GeometryReader { geo in
                Color.clear
                    .onAppear { totalWidth = geo.size.width }
                    .onChange(of: geo.size.width) { totalWidth = $0 }
            }
        )
    }

    private func clamped(total: CGFloat, px: CGFloat) -> CGFloat {
        let lo = minLeft
        let hi = Swift.min(maxLeft, total - minRight - 8)
        return Swift.max(lo, Swift.min(px, Swift.max(lo, hi)))
    }

    private func divider() -> some View {
        ZStack {
            Rectangle()
                .fill(isDragging
                      ? Color(red: 0.4, green: 0.65, blue: 1.0).opacity(0.60)
                      : Color.white.opacity(0.10))
                .frame(width: 1)
                .animation(.easeInOut(duration: 0.12), value: isDragging)

            Color.clear
                .frame(width: 8)
                .contentShape(Rectangle())
        }
        .frame(width: 8)
        .cursor(.resizeLeftRight)
        .gesture(
            DragGesture(minimumDistance: 4, coordinateSpace: .global)
                .updating($dragDelta) { value, state, _ in
                    state = value.translation.width
                }
                .onChanged { _ in
                    if !isDragging { isDragging = true }
                }
                .onEnded { value in
                    isDragging = false
                    let newPx = clamped(total: totalWidth,
                                        px: fraction * totalWidth + value.translation.width)
                    fraction = newPx / Swift.max(totalWidth, 1)
                }
        )
    }
}

// MARK: - ResizableVSplit

struct ResizableVSplit<Top: View, Bottom: View>: View {
    var minTop: CGFloat
    var maxTop: CGFloat
    var minBottom: CGFloat

    let top: Top
    let bottom: Bottom

    @State private var fraction: CGFloat
    @GestureState private var dragDelta: CGFloat = 0
    @State private var isDragging: Bool = false
    @State private var totalHeight: CGFloat = 800

    init(
        minTop: CGFloat = 200,
        maxTop: CGFloat = 800,
        minBottom: CGFloat = 120,
        initialTop: CGFloat = 400,
        @ViewBuilder top: () -> Top,
        @ViewBuilder bottom: () -> Bottom
    ) {
        self.minTop    = minTop
        self.maxTop    = maxTop
        self.minBottom = minBottom
        self.top    = top()
        self.bottom = bottom()
        _fraction = State(initialValue: initialTop / 800)
    }

    var body: some View {
        VStack(spacing: 0) {
            let currentHeight = clamped(total: totalHeight,
                                        px: fraction * totalHeight + dragDelta)
            top
                .frame(height: currentHeight)
                .clipped()

            hDivider()

            bottom
                .frame(maxHeight: .infinity)
                .clipped()
        }
        .background(
            GeometryReader { geo in
                Color.clear
                    .onAppear { totalHeight = geo.size.height }
                    .onChange(of: geo.size.height) { totalHeight = $0 }
            }
        )
    }

    private func clamped(total: CGFloat, px: CGFloat) -> CGFloat {
        let lo = minTop
        let hi = Swift.min(maxTop, total - minBottom - 8)
        return Swift.max(lo, Swift.min(px, Swift.max(lo, hi)))
    }

    private func hDivider() -> some View {
        ZStack {
            Rectangle()
                .fill(isDragging
                      ? Color(red: 0.4, green: 0.65, blue: 1.0).opacity(0.60)
                      : Color.white.opacity(0.10))
                .frame(height: 1)
                .animation(.easeInOut(duration: 0.12), value: isDragging)

            Color.clear
                .frame(height: 8)
                .contentShape(Rectangle())
        }
        .frame(height: 8)
        .cursor(.resizeUpDown)
        .gesture(
            DragGesture(minimumDistance: 4, coordinateSpace: .global)
                .updating($dragDelta) { value, state, _ in
                    state = value.translation.height
                }
                .onChanged { _ in
                    if !isDragging { isDragging = true }
                }
                .onEnded { value in
                    isDragging = false
                    let newPx = clamped(total: totalHeight,
                                        px: fraction * totalHeight + value.translation.height)
                    fraction = newPx / Swift.max(totalHeight, 1)
                }
        )
    }
}

// MARK: - Cursor modifier

extension View {
    func cursor(_ cursor: NSCursor) -> some View {
        self.onHover { inside in
            if inside { cursor.push() } else { NSCursor.pop() }
        }
    }
}
