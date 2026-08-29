import Foundation
import CoreGraphics

/// Deterministic, model-free color-region extraction for photographs and
/// line art. Coordinates use the source image's pixel grid with the origin at
/// the top-left and positive y pointing down.
enum RegionPicker {

    enum SemanticLabel: String, Codable, CaseIterable, Sendable {
        case hair
        case clothing
        case skin
    }

    enum LabelStatus: String, Codable, Sendable {
        /// At least one caller-supplied seed confirms this region.
        case observed = "OBSERVED"
        /// The region was found automatically and has no confirming seed.
        case proposed = "PROPOSED"
    }

    enum Connectivity: Int, Codable, Sendable {
        case four = 4
        case eight = 8
    }

    struct PixelPoint: Codable, Hashable, Sendable {
        let x: Int
        let y: Int

        init(x: Int, y: Int) {
            self.x = x
            self.y = y
        }

        var cgPoint: CGPoint { CGPoint(x: x, y: y) }
    }

    struct PixelRect: Codable, Hashable, Sendable {
        let x: Int
        let y: Int
        let width: Int
        let height: Int

        var cgRect: CGRect { CGRect(x: x, y: y, width: width, height: height) }
    }

    struct RGBA: Codable, Hashable, Sendable {
        let red: UInt8
        let green: UInt8
        let blue: UInt8
        let alpha: UInt8
    }

    struct Seed: Codable, Hashable, Sendable {
        let point: PixelPoint
        let label: SemanticLabel

        init(x: Int, y: Int, label: SemanticLabel) {
            self.point = PixelPoint(x: x, y: y)
            self.label = label
        }

        init(point: PixelPoint, label: SemanticLabel) {
            self.point = point
            self.label = label
        }
    }

    /// One exact horizontal run of member pixels, inclusive at both ends.
    /// Runs are sorted by y and then x and can reconstruct a region mask
    /// without retaining the source image.
    struct ScanlineRun: Codable, Hashable, Sendable {
        let y: Int
        let xStart: Int
        let xEnd: Int
    }

    /// A unit-length edge on the pixel-corner grid. Edges are emitted in
    /// row-major pixel order and top/right/bottom/left side order. Their
    /// direction keeps the region interior consistently on one side, making
    /// them suitable for later loop stitching or direct overlay rendering.
    struct BoundaryEdge: Codable, Hashable, Sendable {
        let start: PixelPoint
        let end: PixelPoint
    }

    /// Evidence tying a caller's seed to the deterministic region it hit.
    struct SeedObservation: Codable, Hashable, Sendable {
        let inputIndex: Int
        let point: PixelPoint
        let label: SemanticLabel
        let sampledColor: RGBA
    }

    struct LabelConflict: Codable, Hashable, Sendable {
        let regionID: Int
        let labels: [SemanticLabel]
        let seedInputIndices: [Int]
    }

    enum RejectedSeedReason: String, Codable, Sendable {
        case outsideImage
        case excludedByAlphaThreshold
    }

    struct RejectedSeed: Codable, Hashable, Sendable {
        let inputIndex: Int
        let seed: Seed
        let reason: RejectedSeedReason
    }

    struct Region: Codable, Hashable, Sendable {
        /// Stable for identical pixels and options: components are numbered by
        /// the row-major position of their first pixel.
        let id: Int
        let status: LabelStatus
        /// Non-nil only when all confirming seeds agree on one label.
        let semanticLabel: SemanticLabel?
        /// All distinct human-confirmed labels touching this component.
        let confirmedLabels: [SemanticLabel]
        let seedObservations: [SeedObservation]
        /// Row-major first pixel used as the flood-fill color anchor.
        let anchorPoint: PixelPoint
        let anchorColor: RGBA
        let pixelCount: Int
        let boundingBox: PixelRect
        let averageColor: RGBA
        let scanlineRuns: [ScanlineRun]
        let boundaryEdges: [BoundaryEdge]
    }

    struct Provenance: Codable, Hashable, Sendable {
        let algorithm: String
        let source: String
        let width: Int
        let height: Int
        let connectivity: Connectivity
        let neighborColorTolerance: UInt8
        let anchorColorTolerance: UInt8
        let alphaThreshold: UInt8
        let includesTransparentPixels: Bool
    }

    struct Result: Codable, Hashable, Sendable {
        let regions: [Region]
        let conflicts: [LabelConflict]
        let rejectedSeeds: [RejectedSeed]
        let provenance: Provenance

        func region(containing point: PixelPoint) -> Region? {
            guard point.x >= 0, point.y >= 0,
                  point.x < provenance.width, point.y < provenance.height else {
                return nil
            }
            return regions.first { region in
                region.scanlineRuns.contains {
                    $0.y == point.y && $0.xStart <= point.x && point.x <= $0.xEnd
                }
            }
        }
    }

    struct Options: Codable, Hashable, Sendable {
        var connectivity: Connectivity
        /// Maximum RGB Euclidean distance between adjacent pixels.
        var neighborColorTolerance: UInt8
        /// Maximum RGB Euclidean distance from a component's first pixel.
        /// This prevents a long smooth gradient from leaking across a photo.
        var anchorColorTolerance: UInt8
        /// Pixels at or below this alpha are background unless
        /// `includeTransparentPixels` is true.
        var alphaThreshold: UInt8
        var includeTransparentPixels: Bool

        init(connectivity: Connectivity = .eight,
             neighborColorTolerance: UInt8 = 30,
             anchorColorTolerance: UInt8 = 64,
             alphaThreshold: UInt8 = 8,
             includeTransparentPixels: Bool = false) {
            self.connectivity = connectivity
            self.neighborColorTolerance = neighborColorTolerance
            self.anchorColorTolerance = anchorColorTolerance
            self.alphaThreshold = alphaThreshold
            self.includeTransparentPixels = includeTransparentPixels
        }

        /// Conservative preset that avoids crossing antialiased ink edges.
        static let lineArt = Options(connectivity: .four,
                                     neighborColorTolerance: 18,
                                     anchorColorTolerance: 36,
                                     alphaThreshold: 1)

        /// More tolerant preset for lighting and texture variation in photos.
        static let photo = Options()
    }

    enum PickerError: Error, Equatable, LocalizedError {
        case invalidDimensions(width: Int, height: Int)
        case invalidRGBAByteCount(expected: Int, actual: Int)
        case imageRenderingFailed

        var errorDescription: String? {
            switch self {
            case .invalidDimensions(let width, let height):
                return "RegionPicker requires positive, non-overflowing dimensions; got \(width)x\(height)."
            case .invalidRGBAByteCount(let expected, let actual):
                return "RegionPicker expected \(expected) RGBA bytes but received \(actual)."
            case .imageRenderingFailed:
                return "RegionPicker could not render the CGImage into an RGBA8 pixel buffer."
            }
        }
    }

    // MARK: - Entry points

    /// Normalizes `image` into an sRGB, premultiplied RGBA8 buffer before
    /// extraction. The returned provenance records that normalization.
    static func pickRegions(in image: CGImage,
                            seeds: [Seed] = [],
                            options: Options = .photo) throws -> Result {
        let width = image.width
        let height = image.height
        let byteCount = try checkedByteCount(width: width, height: height)
        var bytes = [UInt8](repeating: 0, count: byteCount)
        let rendered = bytes.withUnsafeMutableBytes { rawBuffer -> Bool in
            guard let baseAddress = rawBuffer.baseAddress,
                  let colorSpace = CGColorSpace(name: CGColorSpace.sRGB),
                  let context = CGContext(data: baseAddress,
                                          width: width,
                                          height: height,
                                          bitsPerComponent: 8,
                                          bytesPerRow: width * 4,
                                          space: colorSpace,
                                          bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else {
                return false
            }
            context.interpolationQuality = .none
            // A bitmap CGContext's default coordinate system is y-up. Flip
            // it so byte row zero, raw-buffer row zero, and the public pixel
            // coordinate system all consistently mean the image's top row.
            context.translateBy(x: 0, y: CGFloat(height))
            context.scaleBy(x: 1, y: -1)
            context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
            return true
        }
        guard rendered else { throw PickerError.imageRenderingFailed }
        return try pickRegions(rgba8: bytes, width: width, height: height,
                               seeds: seeds, options: options,
                               source: "CGImage rendered to sRGB premultiplied RGBA8")
    }

    /// Extracts from tightly packed, row-major RGBA8 bytes. Supplying this
    /// form is useful for callers that already own decoded pixels and for
    /// deterministic fixture validation without AppKit or Vision.
    static func pickRegions(rgba8: [UInt8],
                            width: Int,
                            height: Int,
                            seeds: [Seed] = [],
                            options: Options = .photo) throws -> Result {
        try pickRegions(rgba8: rgba8, width: width, height: height,
                        seeds: seeds, options: options,
                        source: "caller-supplied tightly packed RGBA8")
    }

    // MARK: - Deterministic flood fill

    private struct Component {
        let pixels: [Int]
        let firstPixelIndex: Int
    }

    private static func pickRegions(rgba8: [UInt8],
                                    width: Int,
                                    height: Int,
                                    seeds: [Seed],
                                    options: Options,
                                    source: String) throws -> Result {
        let expectedBytes = try checkedByteCount(width: width, height: height)
        guard rgba8.count == expectedBytes else {
            throw PickerError.invalidRGBAByteCount(expected: expectedBytes, actual: rgba8.count)
        }

        let pixelCount = width * height
        var componentForPixel = [Int](repeating: -1, count: pixelCount)
        var components: [Component] = []
        let offsets = options.connectivity == .four
            ? [(0, -1), (-1, 0), (1, 0), (0, 1)]
            : [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]

        for startIndex in 0..<pixelCount {
            if componentForPixel[startIndex] >= 0 ||
                isExcluded(index: startIndex, rgba8: rgba8, options: options) {
                continue
            }

            let componentID = components.count
            let anchor = color(at: startIndex, rgba8: rgba8)
            var queue = [startIndex]
            var cursor = 0
            var members: [Int] = []
            componentForPixel[startIndex] = componentID

            while cursor < queue.count {
                let current = queue[cursor]
                cursor += 1
                members.append(current)
                let currentColor = color(at: current, rgba8: rgba8)
                let x = current % width
                let y = current / width

                for (dx, dy) in offsets {
                    let nx = x + dx
                    let ny = y + dy
                    guard nx >= 0, nx < width, ny >= 0, ny < height else { continue }
                    let neighbor = ny * width + nx
                    guard componentForPixel[neighbor] < 0,
                          !isExcluded(index: neighbor, rgba8: rgba8, options: options) else {
                        continue
                    }
                    let neighborColor = color(at: neighbor, rgba8: rgba8)
                    guard isWithinTolerance(currentColor, neighborColor,
                                            tolerance: options.neighborColorTolerance),
                          isWithinTolerance(anchor, neighborColor,
                                            tolerance: options.anchorColorTolerance) else {
                        continue
                    }
                    componentForPixel[neighbor] = componentID
                    queue.append(neighbor)
                }
            }
            components.append(Component(pixels: members.sorted(), firstPixelIndex: startIndex))
        }

        var observations = [[SeedObservation]](repeating: [], count: components.count)
        var rejected: [RejectedSeed] = []
        for (inputIndex, seed) in seeds.enumerated() {
            let x = seed.point.x
            let y = seed.point.y
            guard x >= 0, x < width, y >= 0, y < height else {
                rejected.append(RejectedSeed(inputIndex: inputIndex, seed: seed, reason: .outsideImage))
                continue
            }
            let pixelIndex = y * width + x
            let componentID = componentForPixel[pixelIndex]
            guard componentID >= 0 else {
                rejected.append(RejectedSeed(inputIndex: inputIndex, seed: seed,
                                             reason: .excludedByAlphaThreshold))
                continue
            }
            observations[componentID].append(SeedObservation(inputIndex: inputIndex,
                                                              point: seed.point,
                                                              label: seed.label,
                                                              sampledColor: color(at: pixelIndex, rgba8: rgba8)))
        }

        var conflicts: [LabelConflict] = []
        var regions: [Region] = []
        regions.reserveCapacity(components.count)
        for (componentID, component) in components.enumerated() {
            let evidence = observations[componentID].sorted { $0.inputIndex < $1.inputIndex }
            let labels = SemanticLabel.allCases.filter { label in evidence.contains { $0.label == label } }
            let semanticLabel = labels.count == 1 ? labels[0] : nil
            if labels.count > 1 {
                conflicts.append(LabelConflict(regionID: componentID,
                                               labels: labels,
                                               seedInputIndices: evidence.map(\.inputIndex)))
            }
            regions.append(buildRegion(id: componentID,
                                       component: component,
                                       semanticLabel: semanticLabel,
                                       labels: labels,
                                       evidence: evidence,
                                       rgba8: rgba8,
                                       width: width,
                                       height: height,
                                       componentForPixel: componentForPixel))
        }

        return Result(regions: regions,
                      conflicts: conflicts,
                      rejectedSeeds: rejected,
                      provenance: Provenance(
                        algorithm: "deterministic anchored RGB flood fill v1",
                        source: source,
                        width: width,
                        height: height,
                        connectivity: options.connectivity,
                        neighborColorTolerance: options.neighborColorTolerance,
                        anchorColorTolerance: options.anchorColorTolerance,
                        alphaThreshold: options.alphaThreshold,
                        includesTransparentPixels: options.includeTransparentPixels))
    }

    private static func buildRegion(id: Int,
                                    component: Component,
                                    semanticLabel: SemanticLabel?,
                                    labels: [SemanticLabel],
                                    evidence: [SeedObservation],
                                    rgba8: [UInt8],
                                    width: Int,
                                    height: Int,
                                    componentForPixel: [Int]) -> Region {
        var minX = width
        var minY = height
        var maxX = 0
        var maxY = 0
        var redTotal: UInt64 = 0
        var greenTotal: UInt64 = 0
        var blueTotal: UInt64 = 0
        var alphaTotal: UInt64 = 0
        var runs: [ScanlineRun] = []
        var edges: [BoundaryEdge] = []
        var runY = -1
        var runStart = -1
        var previousX = -2

        func isMember(_ x: Int, _ y: Int) -> Bool {
            x >= 0 && x < width && y >= 0 && y < height && componentForPixel[y * width + x] == id
        }

        for pixelIndex in component.pixels {
            let x = pixelIndex % width
            let y = pixelIndex / width
            minX = min(minX, x)
            minY = min(minY, y)
            maxX = max(maxX, x)
            maxY = max(maxY, y)
            let value = color(at: pixelIndex, rgba8: rgba8)
            redTotal += UInt64(value.red)
            greenTotal += UInt64(value.green)
            blueTotal += UInt64(value.blue)
            alphaTotal += UInt64(value.alpha)

            if y != runY || x != previousX + 1 {
                if runY >= 0 {
                    runs.append(ScanlineRun(y: runY, xStart: runStart, xEnd: previousX))
                }
                runY = y
                runStart = x
            }
            previousX = x

            if !isMember(x, y - 1) {
                edges.append(BoundaryEdge(start: PixelPoint(x: x, y: y),
                                          end: PixelPoint(x: x + 1, y: y)))
            }
            if !isMember(x + 1, y) {
                edges.append(BoundaryEdge(start: PixelPoint(x: x + 1, y: y),
                                          end: PixelPoint(x: x + 1, y: y + 1)))
            }
            if !isMember(x, y + 1) {
                edges.append(BoundaryEdge(start: PixelPoint(x: x + 1, y: y + 1),
                                          end: PixelPoint(x: x, y: y + 1)))
            }
            if !isMember(x - 1, y) {
                edges.append(BoundaryEdge(start: PixelPoint(x: x, y: y + 1),
                                          end: PixelPoint(x: x, y: y)))
            }
        }
        if runY >= 0 {
            runs.append(ScanlineRun(y: runY, xStart: runStart, xEnd: previousX))
        }

        let count = UInt64(component.pixels.count)
        let average = RGBA(red: UInt8(redTotal / count),
                           green: UInt8(greenTotal / count),
                           blue: UInt8(blueTotal / count),
                           alpha: UInt8(alphaTotal / count))
        return Region(id: id,
                      status: evidence.isEmpty ? .proposed : .observed,
                      semanticLabel: semanticLabel,
                      confirmedLabels: labels,
                      seedObservations: evidence,
                      anchorPoint: PixelPoint(x: component.firstPixelIndex % width,
                                              y: component.firstPixelIndex / width),
                      anchorColor: color(at: component.firstPixelIndex, rgba8: rgba8),
                      pixelCount: component.pixels.count,
                      boundingBox: PixelRect(x: minX, y: minY,
                                             width: maxX - minX + 1,
                                             height: maxY - minY + 1),
                      averageColor: average,
                      scanlineRuns: runs,
                      boundaryEdges: edges)
    }

    private static func checkedByteCount(width: Int, height: Int) throws -> Int {
        guard width > 0, height > 0,
              width <= Int.max / height,
              width * height <= Int.max / 4 else {
            throw PickerError.invalidDimensions(width: width, height: height)
        }
        return width * height * 4
    }

    private static func color(at pixelIndex: Int, rgba8: [UInt8]) -> RGBA {
        let offset = pixelIndex * 4
        return RGBA(red: rgba8[offset], green: rgba8[offset + 1],
                    blue: rgba8[offset + 2], alpha: rgba8[offset + 3])
    }

    private static func isExcluded(index: Int, rgba8: [UInt8], options: Options) -> Bool {
        !options.includeTransparentPixels && rgba8[index * 4 + 3] <= options.alphaThreshold
    }

    private static func isWithinTolerance(_ lhs: RGBA, _ rhs: RGBA, tolerance: UInt8) -> Bool {
        let red = Int(lhs.red) - Int(rhs.red)
        let green = Int(lhs.green) - Int(rhs.green)
        let blue = Int(lhs.blue) - Int(rhs.blue)
        let squaredDistance = red * red + green * green + blue * blue
        let limit = Int(tolerance) * Int(tolerance)
        return squaredDistance <= limit
    }
}
