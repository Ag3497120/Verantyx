import AppKit
import CoreImage

/// Pure Core Image pixel-diff helper -- localizes *where* two screenshots
/// differ, complementing `SafariVisionBridge.computeVisualSimilarity`
/// (which only answers *whether* they differ, as a single whole-frame
/// distance scalar). No ML model involved, sub-frame-time cost: this is
/// the "crop to what changed before running inference on it" primitive
/// for Milestone G's UI-testing vector trace.
enum VisualDiffRegion {
    private static let ciContext = CIContext(options: [.useSoftwareRenderer: false])

    /// Returns the bounding box (in pixel coordinates of `after`) of the
    /// region that changed between `before` and `after`, or `nil` if
    /// nothing changed beyond `threshold`. `threshold` is a 0-1 fraction
    /// of max per-channel difference (0.08 default -- tolerant of JPEG/
    /// resampling noise, sensitive to real UI changes).
    static func changedRegion(before: NSImage, after: NSImage, threshold: Float = 0.08) -> CGRect? {
        guard let ciBefore = ciImage(from: before), let ciAfter = ciImage(from: after) else { return nil }

        let extent = ciBefore.extent.intersection(ciAfter.extent)
        guard !extent.isEmpty else { return nil }

        guard let diffFilter = CIFilter(name: "CIDifferenceBlendMode") else { return nil }
        diffFilter.setValue(ciBefore.cropped(to: extent), forKey: kCIInputImageKey)
        diffFilter.setValue(ciAfter.cropped(to: extent), forKey: kCIInputBackgroundImageKey)
        guard let diff = diffFilter.outputImage else { return nil }

        // Threshold to a binary mask so faint compression/resampling noise
        // doesn't register as "changed".
        guard let thresholdFilter = CIFilter(name: "CIColorThreshold") else { return nil }
        thresholdFilter.setValue(diff, forKey: kCIInputImageKey)
        thresholdFilter.setValue(threshold, forKey: "inputThreshold")
        guard let mask = thresholdFilter.outputImage else { return nil }

        guard let cgMask = ciContext.createCGImage(mask, from: extent) else { return nil }
        return boundingBox(ofWhitePixelsIn: cgMask, extent: extent)
    }

    private static func ciImage(from image: NSImage) -> CIImage? {
        guard let tiff = image.tiffRepresentation, let bitmap = NSBitmapImageRep(data: tiff) else { return nil }
        return CIImage(bitmapImageRep: bitmap)
    }

    /// Scans the thresholded mask for the bounding box of "changed" (white)
    /// pixels. Downsamples to a coarse grid for speed -- a pixel-exact box
    /// isn't needed, just enough to crop a sensible region.
    private static func boundingBox(ofWhitePixelsIn cgImage: CGImage, extent: CGRect) -> CGRect? {
        let gridSize = 64
        let width = cgImage.width, height = cgImage.height
        guard width > 0, height > 0 else { return nil }

        let colorSpace = CGColorSpaceCreateDeviceGray()
        let bytesPerRow = gridSize
        var pixels = [UInt8](repeating: 0, count: gridSize * gridSize)
        guard let context = CGContext(
            data: &pixels, width: gridSize, height: gridSize, bitsPerComponent: 8,
            bytesPerRow: bytesPerRow, space: colorSpace, bitmapInfo: CGImageAlphaInfo.none.rawValue
        ) else { return nil }
        context.interpolationQuality = .low
        context.draw(cgImage, in: CGRect(x: 0, y: 0, width: gridSize, height: gridSize))

        var minX = gridSize, minY = gridSize, maxX = -1, maxY = -1
        for gy in 0..<gridSize {
            for gx in 0..<gridSize {
                if pixels[gy * gridSize + gx] > 32 {
                    minX = min(minX, gx); maxX = max(maxX, gx)
                    minY = min(minY, gy); maxY = max(maxY, gy)
                }
            }
        }
        guard maxX >= minX, maxY >= minY else { return nil }

        let scaleX = extent.width / CGFloat(gridSize)
        let scaleY = extent.height / CGFloat(gridSize)
        // Grid y=0 is the top of the rendered mask; CG image coordinate
        // space for CGContext drawing here is already top-down, matching
        // extent's origin at (0,0) top-left convention used by callers
        // (screenshot bitmaps), so no additional flip is needed.
        return CGRect(
            x: extent.origin.x + CGFloat(minX) * scaleX,
            y: extent.origin.y + CGFloat(minY) * scaleY,
            width: CGFloat(maxX - minX + 1) * scaleX,
            height: CGFloat(maxY - minY + 1) * scaleY
        )
    }
}
