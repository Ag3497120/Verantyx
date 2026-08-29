import Foundation
import AppKit
import CoreGraphics
import CoreVideo
import ImageIO
import Vision

/// Lifts one subject out of a photo and hands back its silhouette as a
/// closed 2-D polygon, in exactly the shape `photoloset/silhouette.py`'s
/// module docstring names as the boundary it refuses to cross:
///
///     {"outline": [[x, y], ...],   # one closed loop, image pixel coords,
///                                  # y DOWN, first point != last point
///      "width_px": Int, "height_px": Int,
///      "source": "<how it was produced>",
///      "fixture": false}
///
/// silhouette.py says the boundary out loud: 「このモジュールに画像は
/// 入ってこない。入力は輪郭」— that module never decodes a pixel, on
/// purpose, because `photoloset` (the Python package) imports nothing
/// outside the standard library and a JPEG/PNG decoder cannot live there.
/// `GarmentOutline` is the other half of that sentence: this is where the
/// image *stops*. Everything upstream of `extract` is pixels; everything
/// downstream of its return value is points. No function in this type
/// hands a `CGImage`, `NSImage`, or `CVPixelBuffer` back to a caller.
///
/// WHAT THE MASK ACTUALLY IS -- read this before trusting the outline.
/// Neither Vision request below segments a *garment*. `VNGenerateForeground
/// InstanceMaskRequest` segments "the most salient separable thing in the
/// frame" (a person, a mannequin, a folded sweater -- whatever Vision
/// judges to be the subject); `VNGeneratePersonSegmentationRequest`
/// segments a *person*, full stop. A photo of someone in a T-shirt and
/// shorts produces a mask that includes their head, their hands, and their
/// bare legs -- there is no Vision request that means "just the fabric".
/// The default output says this in its own `source` string every time
/// (`"subject mask covers head/hands/bare legs when visible, not
/// garment-only"`), not just in this comment, because a caller reading the
/// JSON and not the Swift source deserves the same warning.
///
/// The one crop this type is willing to apply on top -- cutting off the
/// top `headCropFraction` of the subject's own bounding box, a blunt
/// stand-in for "remove the head" -- is off by default (`Options()` does
/// nothing extra) and, when a caller turns it on, the exact fraction rides
/// along in `source` rather than disappearing into the returned points.
/// That mirrors `mannequin.align()` on the Python side: it also moves
/// points by a rule it chose (shoulder-to-collar anchoring, a rigid
/// translation) and puts `dy`/`dx`/`dz` in its own return value instead of
/// moving geometry and saying nothing about it.
///
/// PIPELINE. `VNImageRequestHandler` -> a binary mask (`CVPixelBuffer`,
/// `kCVPixelFormatType_OneComponent8`) -> largest 8-connected component
/// (guards against Vision handing back flecks of noise alongside the real
/// subject) -> Moore-neighbor boundary trace (a pixel-level walk around
/// the component's edge, clockwise, stopping when it returns to its own
/// start pixel) -> Douglas-Peucker simplification (closed-polygon variant:
/// split at the two farthest-apart traced points, simplify each arc
/// against its own chord, splice back together) -> scale from mask-pixel
/// space to the photo's own upright pixel space. Every stage that can
/// legitimately find nothing returns a typed `UNKNOWN_<REASON>` refusal
/// dict (`verdict` + `how_to_close`, the same two keys every other refusal
/// in this repository carries) instead of a plausible-looking empty
/// outline or a frame rectangle standing in for "I don't know".
///
/// HONESTY, not accuracy, is what this type promises. It does not promise
/// the traced polygon is a good garment pattern input -- silhouette.py
/// already states its own single-view limits for that job. It promises
/// only that `"fixture": false` never appears next to an outline nothing
/// real produced, and that every refusal names what was actually tried.
enum GarmentOutline {

    // MARK: - Verdicts

    /// The file/NSImage/CGImage never became decodable pixels at all --
    /// this is a step *before* Vision runs, so no Vision request name
    /// belongs in `how_to_close` for this one.
    static let imageUnreadable = "UNKNOWN_IMAGE_UNREADABLE"
    /// Every Vision request that was tried either raised or came back
    /// with zero foreground pixels above threshold. Distinct from
    /// `imageUnreadable`: the pixels decoded fine, Vision just did not
    /// find a subject in them.
    static let noSubjectFound = "UNKNOWN_NO_SUBJECT_FOUND"
    /// Reused verbatim from `photoloset/silhouette.py` (`BAD_OUTLINE`):
    /// the same verdict name for the same failure -- a polygon that
    /// collapsed to fewer than 3 points -- whether it happened on the
    /// Python side reading an outline or here, producing one. A caller
    /// checking for this string does not need a second name for the same
    /// problem depending on which side of the boundary it showed up on.
    static let outlineDegenerate = "UNKNOWN_OUTLINE_DEGENERATE"

    // MARK: - Options

    /// What a caller can ask this type to do beyond "trace the mask
    /// Vision handed back". Every field defaults to doing nothing --
    /// `Options()` alone changes no geometry and adds no crop.
    struct Options {
        /// See the type doc comment. `nil` (the default) applies no head
        /// crop: the returned outline is the full subject mask, head,
        /// hands, and bare legs included, exactly as traced. A value in
        /// `(0, 1)` removes the top fraction of the subject's own
        /// bounding-box height *before* tracing, and the fraction is
        /// echoed into `source` on success.
        var headCropFraction: Double? = nil

        /// Douglas-Peucker tolerance, in mask pixels. `nil` derives one
        /// from the mask's own size (0.15% of the shorter side, floored
        /// at 1.5px) so a 4000px photo and a 400px thumbnail both end up
        /// with a comparably simplified polygon instead of the small one
        /// going through nearly untouched.
        var simplifyEpsilonPx: Double? = nil

        /// Below this many pixels in the largest connected foreground
        /// component, treat it as noise rather than a subject. This
        /// mainly guards `VNGeneratePersonSegmentationRequest`, which
        /// always returns *some* confidence mask and never says "nobody
        /// is in this frame" on its own -- the emptiness has to be
        /// measured, not read off a flag.
        var minSubjectPixels: Int = 64

        init() {}
    }

    // MARK: - Public entry points

    /// Reads an image straight off disk (via `CGImageSource`, so EXIF
    /// orientation is read and honored -- `width_px`/`height_px` and every
    /// point in `outline` are in the photo's *upright*, as-displayed pixel
    /// grid, not however the sensor happened to store rows).
    static func extract(fileURL: URL, options: Options = Options()) -> [String: Any] {
        guard let source = CGImageSourceCreateWithURL(fileURL as CFURL, nil) else {
            return refusal(imageUnreadable,
                            howToClose: "could not open this path as an image source: \(fileURL.path)",
                            extra: ["path": fileURL.path])
        }
        guard let cgImage = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
            return refusal(imageUnreadable,
                            howToClose: "opened the file but could not decode a bitmap from it: \(fileURL.path)",
                            extra: ["path": fileURL.path])
        }
        let orientation = readOrientation(source)
        let (displayWidth, displayHeight) = displayDimensions(cgImage: cgImage, orientation: orientation)
        return run(cgImage: cgImage, orientation: orientation,
                    displayWidth: displayWidth, displayHeight: displayHeight, options: options)
    }

    /// Takes an already-decoded `NSImage` (e.g. one already held by the
    /// app's own view layer). `NSImage` does not carry EXIF orientation
    /// the way a fresh `CGImageSource` read does -- a bitmap that already
    /// made it into an `NSImage` is assumed upright. Prefer
    /// `extract(fileURL:)` when a file path is available.
    static func extract(image: NSImage, options: Options = Options()) -> [String: Any] {
        guard let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
            return refusal(imageUnreadable,
                            howToClose: "this NSImage had no CGImage representation to hand to Vision",
                            extra: [:])
        }
        return run(cgImage: cgImage, orientation: .up,
                    displayWidth: cgImage.width, displayHeight: cgImage.height, options: options)
    }

    /// Produces a local, precomputed provider payload for
    /// `garment_body_image_separation_propose` from capabilities already
    /// shipped with macOS and Verantyx:
    ///
    /// - Vision person segmentation supplies a *clothed subject envelope*;
    /// - Vision body pose supplies proposed 2-D joints;
    /// - RegionPicker evidence supplies one GARMENT mask per retained region.
    ///
    /// The BODY-class envelope is deliberately PROPOSED with low confidence.
    /// It includes clothes and hair and therefore is neither naked anatomy nor
    /// a body measurement.  No rear, centimetre, fit, material, or
    /// manufacturing claim is emitted here.  Keeping this provider-shaped
    /// boundary in one place prevents callers from independently promoting a
    /// person silhouette to an observed body.
    static func bodyImageSeparationProvider(
        fileURL: URL, garmentEvidence: [String: Any], evidenceState: String
    ) -> [String: Any] {
        guard let imageSource = CGImageSourceCreateWithURL(fileURL as CFURL, nil),
              let cgImage = CGImageSourceCreateImageAtIndex(imageSource, 0, nil) else {
            return refusal(
                imageUnreadable,
                howToClose: "could not decode the image for local body/garment separation",
                extra: ["path": fileURL.path])
        }
        let orientation = readOrientation(imageSource)
        let (displayWidth, displayHeight) = displayDimensions(
            cgImage: cgImage, orientation: orientation)
        // Vision does not need the source's full print resolution to find a
        // person or 2-D joints.  Use an upright, cached analysis thumbnail so
        // a 4K/8K fashion photo does not freeze the chat UI for tens of
        // seconds.  Normalized pose and mask coordinates are scaled back to
        // the original upright display grid below.
        let thumbnailOptions: [CFString: Any] = [
            kCGImageSourceCreateThumbnailFromImageAlways: true,
            kCGImageSourceCreateThumbnailWithTransform: true,
            kCGImageSourceThumbnailMaxPixelSize: 640,
            kCGImageSourceShouldCacheImmediately: true,
        ]
        let thumbnail = CGImageSourceCreateThumbnailAtIndex(
            imageSource, 0, thumbnailOptions as CFDictionary)
        let visionImage = thumbnail ?? cgImage
        let visionOrientation: CGImagePropertyOrientation = thumbnail == nil
            ? orientation : .up

        let observedGarment = evidenceState.uppercased() == "OBSERVED"
        let evidenceWidth = numericInt(garmentEvidence["width_px"])
            ?? numericInt(garmentEvidence["fused_target_width_px"])
            ?? displayWidth
        let evidenceHeight = numericInt(garmentEvidence["height_px"])
            ?? numericInt(garmentEvidence["fused_target_height_px"])
            ?? displayHeight
        let regionScaleX = evidenceWidth > 0
            ? Double(displayWidth) / Double(evidenceWidth) : 1.0
        let regionScaleY = evidenceHeight > 0
            ? Double(displayHeight) / Double(evidenceHeight) : 1.0

        var masks: [[String: Any]] = []
        let regions = garmentEvidence["regions"] as? [[String: Any]] ?? []
        for (index, region) in regions.enumerated() {
            let points = pointArray(region["outline"])
            guard points.count >= 3 else { continue }
            let regionObserved = observedGarment
                && (region["state"] as? String)?.uppercased() == "OBSERVED"
            let regionID = region["region_id"] as? String ?? "region-\(index + 1)"
            masks.append([
                "mask_id": "vision-garment-\(regionID)",
                "class": "GARMENT",
                "garment_unit_id": regionID,
                "outline": points.map { [$0[0] * regionScaleX, $0[1] * regionScaleY] },
                "confidence": regionObserved ? 1.0 : 0.58,
                "authority": regionObserved ? "OBSERVED" : "PROPOSED",
            ])
        }

        if masks.isEmpty {
            let usesFusedTarget = pointArray(
                garmentEvidence["fused_target_outline"]).count >= 3
            let points = usesFusedTarget
                ? pointArray(garmentEvidence["fused_target_outline"])
                : pointArray(garmentEvidence["outline"] ?? garmentEvidence["points"])
            if points.count >= 3 {
                let sourceWidth = usesFusedTarget
                    ? (numericInt(garmentEvidence["fused_target_width_px"])
                       ?? displayWidth)
                    : evidenceWidth
                let sourceHeight = usesFusedTarget
                    ? (numericInt(garmentEvidence["fused_target_height_px"])
                       ?? displayHeight)
                    : evidenceHeight
                let sx = sourceWidth > 0
                    ? Double(displayWidth) / Double(sourceWidth) : 1.0
                let sy = sourceHeight > 0
                    ? Double(displayHeight) / Double(sourceHeight) : 1.0
                // A fused target intentionally includes the person. It is
                // useful for reversible cleanup, but never observed garment.
                let authority = observedGarment && !usesFusedTarget
                    ? "OBSERVED" : "PROPOSED"
                masks.append([
                    "mask_id": usesFusedTarget
                        ? "vision-fused-person-garment-target"
                        : "vision-front-garment-outline",
                    "class": "GARMENT",
                    "garment_unit_id": usesFusedTarget
                        ? "FUSED_CLEANUP_TARGET" : "FRONT_GARMENT",
                    "outline": points.map { [$0[0] * sx, $0[1] * sy] },
                    "confidence": authority == "OBSERVED" ? 1.0 : 0.42,
                    "authority": authority,
                ])
            }
        }

        var personMaskID: String? = nil
        let personAttempt = runPersonSegmentation(
            cgImage: visionImage, orientation: visionOrientation,
            qualityLevel: .balanced)
        if case .success(let maskResult) = personAttempt,
           let component = largestComponent(
                grid: maskResult.grid, width: maskResult.width,
                height: maskResult.height) {
            let result = buildOutlineResult(
                componentGrid: component.grid,
                maskWidth: maskResult.width, maskHeight: maskResult.height,
                bbox: component.bbox, pixelCount: component.pixelCount,
                displayWidth: displayWidth, displayHeight: displayHeight,
                options: Options(), fixture: false,
                baseSource: maskResult.sourceDescription)
            if let outline = result["outline"] as? [[Double]],
               outline.count >= 3 {
                let maskID = "vision-clothed-subject-envelope"
                personMaskID = maskID
                masks.append([
                    "mask_id": maskID,
                    "class": "BODY",
                    "outline": outline,
                    "confidence": 0.24,
                    "authority": "PROPOSED",
                ])
            }
        }

        let pose = proposedBodyPose(
            cgImage: visionImage, orientation: visionOrientation,
            displayWidth: displayWidth, displayHeight: displayHeight)
        guard !masks.isEmpty || !pose.isEmpty else {
            return refusal(
                noSubjectFound,
                howToClose: "Apple Vision found neither a person/pose nor usable RegionPicker garment geometry",
                extra: ["path": fileURL.path])
        }

        let garmentMaskIDs = masks.compactMap { mask -> String? in
            guard (mask["class"] as? String) == "GARMENT" else { return nil }
            return mask["mask_id"] as? String
        }
        var occlusions: [[String: Any]] = []
        if let personMaskID {
            for garmentID in garmentMaskIDs {
                occlusions.append([
                    "occlusion_id": "front-\(garmentID)-over-subject",
                    "occluder_mask_id": garmentID,
                    "occluded_mask_id": personMaskID,
                    "relation": "OCCLUDES",
                    "authority": "PROPOSED",
                ])
            }
        }

        return [
            "provider_id": "apple-vision-local-v1",
            "provider_kind": "APPLE_VISION_POSE_AND_CLOTHED_SUBJECT_PROXY",
            "authority": "PROPOSED",
            "pose_keypoints": pose,
            "masks": masks,
            "occlusions": occlusions,
            "camera": [
                "orientation": "UP",
                "view": "UNKNOWN",
                "state": "OBSERVED",
                "authority": "OBSERVED",
                "width_px": displayWidth,
                "height_px": displayHeight,
            ],
            "rear_state": "UNKNOWN_UNOBSERVED",
            "manufacturing_ready": false,
            "fact_promotions": [],
            "warnings": [
                "BODY mask is a clothed-subject envelope and includes garment/hair pixels",
                "pose keypoints are Apple Vision proposals, not anatomical measurements",
                "HAIR and BACKGROUND remain UNKNOWN unless another provider or a person supplies them",
                "rear geometry, body dimensions, fit and manufacturing remain unobserved",
            ],
        ]
    }

    private static func proposedBodyPose(
        cgImage: CGImage, orientation: CGImagePropertyOrientation,
        displayWidth: Int, displayHeight: Int
    ) -> [[String: Any]] {
        let request = VNDetectHumanBodyPoseRequest()
        let handler = VNImageRequestHandler(
            cgImage: cgImage, orientation: orientation, options: [:])
        guard (try? handler.perform([request])) != nil,
              let observation = request.results?.max(by: {
                  $0.confidence < $1.confidence
              }) else { return [] }
        let joints: [(String, VNHumanBodyPoseObservation.JointName)] = [
            ("nose", .nose), ("neck", .neck), ("root", .root),
            ("left_shoulder", .leftShoulder),
            ("right_shoulder", .rightShoulder),
            ("left_elbow", .leftElbow), ("right_elbow", .rightElbow),
            ("left_wrist", .leftWrist), ("right_wrist", .rightWrist),
            ("left_hip", .leftHip), ("right_hip", .rightHip),
            ("left_knee", .leftKnee), ("right_knee", .rightKnee),
            ("left_ankle", .leftAnkle), ("right_ankle", .rightAnkle),
        ]
        return joints.compactMap { name, joint -> [String: Any]? in
            guard let point = try? observation.recognizedPoint(joint),
                  point.confidence >= 0.10 else { return nil }
            return [
                "name": name,
                "point": [
                    Double(point.location.x) * Double(displayWidth),
                    (1.0 - Double(point.location.y)) * Double(displayHeight),
                ],
                "confidence": Double(point.confidence),
                "authority": "PROPOSED",
            ]
        }
    }

    private static func numericInt(_ value: Any?) -> Int? {
        if let value = value as? Int { return value }
        if let value = value as? NSNumber { return value.intValue }
        if let value = value as? Double { return Int(value.rounded()) }
        return nil
    }

    private static func pointArray(_ value: Any?) -> [[Double]] {
        if let points = value as? [[Double]] { return points }
        guard let rows = value as? [[Any]] else { return [] }
        return rows.compactMap { row in
            guard row.count >= 2,
                  let x = (row[0] as? NSNumber)?.doubleValue,
                  let y = (row[1] as? NSNumber)?.doubleValue else { return nil }
            return [x, y]
        }
    }

    // MARK: - Fixture entry point (testing only)

    /// Runs the trace/simplify half of the pipeline on a mask a caller
    /// supplies directly, with **no Vision request and no pixel ever
    /// read**. This exists so the geometry (connected components, the
    /// boundary walk, Douglas-Peucker) can be exercised against a known
    /// shape without a camera, a photo, or a model in the loop.
    ///
    /// `fixture: true` is set unconditionally and `source` always starts
    /// with the literal prefix `"fixture:"` -- the same marker
    /// `photoloset/resemble.py` stamps on `install_fixture`'s output, for
    /// the same reason stated there: a fixture that could pass for a real
    /// backend is how a demo becomes a claim. This function cannot be
    /// reached from `extract(fileURL:)` or `extract(image:)`; nothing
    /// routes real photos through it.
    static func extractFromFixtureMask(_ mask: [[Bool]], widthPx: Int, heightPx: Int,
                                        options: Options = Options()) -> [String: Any] {
        guard widthPx > 0, heightPx > 0, mask.count == heightPx, mask.allSatisfy({ $0.count == widthPx }) else {
            return refusal(imageUnreadable,
                            howToClose: "fixture mask must be exactly heightPx rows of widthPx booleans; got \(mask.count) rows for heightPx=\(heightPx), widthPx=\(widthPx)",
                            extra: [:])
        }
        var flat = [Bool](repeating: false, count: widthPx * heightPx)
        for y in 0..<heightPx {
            for x in 0..<widthPx {
                flat[y * widthPx + x] = mask[y][x]
            }
        }
        guard let component = largestComponent(grid: flat, width: widthPx, height: heightPx) else {
            return refusal(noSubjectFound, howToClose: "the fixture mask has no true pixel at all", extra: [:])
        }
        return buildOutlineResult(
            componentGrid: component.grid, maskWidth: widthPx, maskHeight: heightPx,
            bbox: component.bbox, pixelCount: component.pixelCount,
            displayWidth: widthPx, displayHeight: heightPx,
            options: options, fixture: true,
            baseSource: "boundary-trace-only (mask supplied directly by the caller; no Vision request ran, no pixel was read)")
    }

    // MARK: - Core pipeline

    private static func run(cgImage: CGImage, orientation: CGImagePropertyOrientation,
                             displayWidth: Int, displayHeight: Int, options: Options) -> [String: Any] {
        let (attempt, attemptLog) = obtainMask(cgImage: cgImage, orientation: orientation)
        guard case .success(let maskResult) = attempt else {
            return refusal(noSubjectFound,
                            howToClose: "no Vision request found a subject in this frame; use a photo with one clear subject set off from its background",
                            extra: ["attempts": attemptLog])
        }
        guard let component = largestComponent(grid: maskResult.grid, width: maskResult.width, height: maskResult.height) else {
            return refusal(noSubjectFound,
                            howToClose: "\(maskResult.sourceDescription) ran but every mask pixel was below threshold",
                            extra: ["attempts": attemptLog])
        }
        return buildOutlineResult(
            componentGrid: component.grid, maskWidth: maskResult.width, maskHeight: maskResult.height,
            bbox: component.bbox, pixelCount: component.pixelCount,
            displayWidth: displayWidth, displayHeight: displayHeight,
            options: options, fixture: false, baseSource: maskResult.sourceDescription)
    }

    /// Shared tail of the pipeline: everything from "we have one connected
    /// foreground component" through emitting either the outline contract
    /// or a typed refusal. Both `run` (real Vision) and
    /// `extractFromFixtureMask` (no Vision at all) end here, so the two
    /// paths cannot silently diverge on how a small or degenerate mask
    /// gets reported.
    private static func buildOutlineResult(
        componentGrid: [Bool], maskWidth: Int, maskHeight: Int,
        bbox: (minX: Int, minY: Int, maxX: Int, maxY: Int), pixelCount: Int,
        displayWidth: Int, displayHeight: Int,
        options: Options, fixture: Bool, baseSource: String
    ) -> [String: Any] {
        guard pixelCount >= options.minSubjectPixels else {
            return refusal(noSubjectFound,
                            howToClose: "the largest connected subject region was only \(pixelCount)px, below the \(options.minSubjectPixels)px floor; use a larger or clearer subject, or lower Options.minSubjectPixels",
                            extra: ["pixel_count": pixelCount])
        }

        var workingGrid = componentGrid
        var headCropDescription = "no head crop applied (full subject mask kept: head/hands/legs included)"
        if let fraction = options.headCropFraction, fraction > 0, fraction < 1 {
            workingGrid = applyHeadCrop(grid: workingGrid, width: maskWidth, height: maskHeight,
                                         bbox: bbox, fraction: fraction)
            let bboxHeight = bbox.maxY - bbox.minY + 1
            headCropDescription = "head crop applied: top \(String(format: "%.3f", fraction)) of subject bbox height (\(bboxHeight)px) removed before tracing"
        }

        guard let rawBoundary = traceBoundary(grid: workingGrid, width: maskWidth, height: maskHeight),
              rawBoundary.count >= 3 else {
            return refusal(outlineDegenerate,
                            howToClose: "the subject mask traced to fewer than 3 boundary points (a head crop that removes the whole mask can cause this); lower headCropFraction or use a larger subject",
                            extra: ["pixel_count": pixelCount])
        }

        let epsilon = options.simplifyEpsilonPx ?? max(1.5, Double(min(maskWidth, maskHeight)) * 0.0015)
        let simplified = simplifyClosedPolygon(rawBoundary, epsilon: epsilon)
        guard simplified.count >= 3 else {
            return refusal(outlineDegenerate,
                            howToClose: "Douglas-Peucker simplification (epsilon=\(epsilon)px) collapsed the traced boundary below 3 points; this is this pipeline's bug, not a caller error -- lower simplifyEpsilonPx as a workaround and report it",
                            extra: ["raw_point_count": rawBoundary.count, "epsilon_px": epsilon])
        }

        let scaleX = Double(displayWidth) / Double(maskWidth)
        let scaleY = Double(displayHeight) / Double(maskHeight)
        let outlinePoints: [[Double]] = simplified.map { [Double($0.0) * scaleX, Double($0.1) * scaleY] }

        let fullSource = "\(baseSource); subject mask covers head/hands/bare legs when visible, not garment-only; \(headCropDescription)"
        return [
            "outline": outlinePoints,
            "width_px": displayWidth,
            "height_px": displayHeight,
            "source": fixture ? "fixture:\(fullSource)" : fullSource,
            "fixture": fixture,
        ]
    }

    // MARK: - Vision requests

    private struct MaskResult {
        let grid: [Bool]
        let width: Int
        let height: Int
        let sourceDescription: String
    }

    private enum MaskAttempt {
        case success(MaskResult)
        case threw(requestName: String, message: String)
        case empty(requestName: String)
    }

    /// Primary detector: a general "salient separable foreground thing"
    /// segmenter, not specific to people, which is exactly why it is tried
    /// first for a garment photo that may show a mannequin or a folded
    /// item rather than a person. macOS 14+ only.
    private static func runForegroundInstanceMask(cgImage: CGImage, orientation: CGImagePropertyOrientation) -> MaskAttempt {
        guard #available(macOS 14.0, *) else {
            return .empty(requestName: "VNGenerateForegroundInstanceMaskRequest (unavailable: this host is older than macOS 14)")
        }
        let handler = VNImageRequestHandler(cgImage: cgImage, orientation: orientation, options: [:])
        let request = VNGenerateForegroundInstanceMaskRequest()
        do {
            try handler.perform([request])
        } catch {
            return .threw(requestName: "VNGenerateForegroundInstanceMaskRequest", message: error.localizedDescription)
        }
        guard let observation = request.results?.first else {
            return .empty(requestName: "VNGenerateForegroundInstanceMaskRequest")
        }
        let instances = observation.allInstances
        guard !instances.isEmpty else {
            return .empty(requestName: "VNGenerateForegroundInstanceMaskRequest")
        }
        // Pick the single largest instance by pixel area rather than
        // merging every instance Vision found -- a photo with the garment
        // and, say, a hanger both read as separable "instances" should not
        // trace their union as one silhouette.
        var winner: (index: Int, grid: [Bool], width: Int, height: Int, count: Int)? = nil
        for index in instances {
            guard let buffer = try? observation.generateScaledMaskForImage(forInstances: IndexSet(integer: index), from: handler),
                  let (grid, width, height) = booleanGrid(from: buffer, threshold: 0.5) else { continue }
            let count = grid.reduce(0) { $0 + ($1 ? 1 : 0) }
            if winner == nil || count > winner!.count {
                winner = (index, grid, width, height, count)
            }
        }
        guard let best = winner else {
            return .empty(requestName: "VNGenerateForegroundInstanceMaskRequest (all \(instances.count) instance mask(s) failed to render)")
        }
        let description = "VNGenerateForegroundInstanceMaskRequest (instance \(best.index) of \(instances.count) by index, largest by pixel area: \(best.count)px)"
        return .success(MaskResult(grid: best.grid, width: best.width, height: best.height, sourceDescription: description))
    }

    /// Fallback: a person-only segmenter, tried when the instance-mask
    /// request is unavailable on this OS, raises, or comes back with zero
    /// instances -- a second real attempt at finding a subject, not merely
    /// an availability shim, and `source` says which of the two actually
    /// produced the mask.
    private static func runPersonSegmentation(
        cgImage: CGImage, orientation: CGImagePropertyOrientation,
        qualityLevel: VNGeneratePersonSegmentationRequest.QualityLevel = .accurate
    ) -> MaskAttempt {
        let handler = VNImageRequestHandler(cgImage: cgImage, orientation: orientation, options: [:])
        let request = VNGeneratePersonSegmentationRequest()
        request.qualityLevel = qualityLevel
        do {
            try handler.perform([request])
        } catch {
            return .threw(requestName: "VNGeneratePersonSegmentationRequest", message: error.localizedDescription)
        }
        guard let observation = request.results?.first,
              let (grid, width, height) = booleanGrid(from: observation.pixelBuffer, threshold: 0.5) else {
            return .empty(requestName: "VNGeneratePersonSegmentationRequest")
        }
        return .success(MaskResult(grid: grid, width: width, height: height,
                                    sourceDescription: "VNGeneratePersonSegmentationRequest(qualityLevel=\(qualityLevel.rawValue))"))
    }

    private static func obtainMask(cgImage: CGImage, orientation: CGImagePropertyOrientation) -> (MaskAttempt, [String]) {
        var log: [String] = []
        let first = runForegroundInstanceMask(cgImage: cgImage, orientation: orientation)
        switch first {
        case .success:
            return (first, log)
        case .threw(let name, let message):
            log.append("\(name) raised: \(message)")
        case .empty(let name):
            log.append("\(name) found no subject")
        }
        let second = runPersonSegmentation(cgImage: cgImage, orientation: orientation)
        switch second {
        case .success(let mask):
            let combined = MaskResult(grid: mask.grid, width: mask.width, height: mask.height,
                                       sourceDescription: (log + [mask.sourceDescription]).joined(separator: "; then "))
            return (.success(combined), log)
        case .threw(let name, let message):
            log.append("\(name) raised: \(message)")
        case .empty(let name):
            log.append("\(name) found no subject")
        }
        return (second, log)
    }

    // MARK: - CVPixelBuffer -> boolean grid

    /// `threshold` is normalized to `0...1` because the two Vision requests
    /// this type calls do not agree on pixel format for their masks:
    /// `VNGeneratePersonSegmentationRequest.pixelBuffer` is
    /// `kCVPixelFormatType_OneComponent8` (a byte per pixel), but
    /// `VNInstanceMaskObservation.generateScaledMaskForImage` is
    /// `kCVPixelFormatType_OneComponent32Float` (a 0.0-1.0 confidence per
    /// pixel) -- confirmed by running both against a real image and
    /// printing `CVPixelBufferGetPixelFormatType`, not assumed from
    /// documentation. An earlier version of this function only accepted
    /// `OneComponent8` and silently returned `nil` for every instance
    /// mask Vision ever produced, which made
    /// `VNGenerateForegroundInstanceMaskRequest` -- the primary detector,
    /// picked specifically because it can find a mannequin or a folded
    /// garment that no person is standing in -- a permanent no-op that
    /// fell through to the person-only fallback on every single call
    /// without ever saying so.
    private static func booleanGrid(from pixelBuffer: CVPixelBuffer, threshold: Double) -> (grid: [Bool], width: Int, height: Int)? {
        CVPixelBufferLockBaseAddress(pixelBuffer, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(pixelBuffer, .readOnly) }
        let width = CVPixelBufferGetWidth(pixelBuffer)
        let height = CVPixelBufferGetHeight(pixelBuffer)
        let bytesPerRow = CVPixelBufferGetBytesPerRow(pixelBuffer)
        guard width > 0, height > 0, let base = CVPixelBufferGetBaseAddress(pixelBuffer) else {
            return nil
        }
        var grid = [Bool](repeating: false, count: width * height)
        switch CVPixelBufferGetPixelFormatType(pixelBuffer) {
        case kCVPixelFormatType_OneComponent8:
            let ptr = base.assumingMemoryBound(to: UInt8.self)
            let byteThreshold = UInt8(max(0.0, min(255.0, threshold * 255.0)))
            for y in 0..<height {
                let rowBase = y * bytesPerRow
                for x in 0..<width {
                    grid[y * width + x] = ptr[rowBase + x] > byteThreshold
                }
            }
        case kCVPixelFormatType_OneComponent32Float:
            let ptr = base.assumingMemoryBound(to: Float32.self)
            let floatsPerRow = bytesPerRow / MemoryLayout<Float32>.stride
            let floatThreshold = Float32(threshold)
            for y in 0..<height {
                let rowBase = y * floatsPerRow
                for x in 0..<width {
                    grid[y * width + x] = ptr[rowBase + x] > floatThreshold
                }
            }
        default:
            // A pixel format neither Vision request is documented (or has
            // been observed) to produce. Refuse rather than reinterpret
            // unknown bytes as either scale.
            return nil
        }
        return (grid, width, height)
    }

    // MARK: - Connected components

    /// Largest 8-connected true region in `grid`, as its own boolean grid
    /// (same dimensions, everything outside the winning component cleared)
    /// plus its bounding box and pixel count. `nil` only when `grid` has
    /// no true pixel anywhere.
    private static func largestComponent(grid: [Bool], width: Int, height: Int)
        -> (grid: [Bool], bbox: (minX: Int, minY: Int, maxX: Int, maxY: Int), pixelCount: Int)? {
        var labels = [Int](repeating: 0, count: width * height)
        var sizes: [Int] = [0]
        var currentLabel = 0
        var stack: [Int] = []
        let offsets: [(Int, Int)] = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]

        for y in 0..<height {
            for x in 0..<width {
                let idx = y * width + x
                guard grid[idx], labels[idx] == 0 else { continue }
                currentLabel += 1
                sizes.append(0)
                labels[idx] = currentLabel
                stack.append(idx)
                while let top = stack.popLast() {
                    sizes[currentLabel] += 1
                    let ty = top / width
                    let tx = top % width
                    for (dx, dy) in offsets {
                        let nx = tx + dx, ny = ty + dy
                        guard nx >= 0, nx < width, ny >= 0, ny < height else { continue }
                        let nIdx = ny * width + nx
                        if grid[nIdx] && labels[nIdx] == 0 {
                            labels[nIdx] = currentLabel
                            stack.append(nIdx)
                        }
                    }
                }
            }
        }
        guard currentLabel > 0 else { return nil }

        var winner = 1
        if currentLabel >= 2 {
            for label in 2...currentLabel where sizes[label] > sizes[winner] {
                winner = label
            }
        }

        var outGrid = [Bool](repeating: false, count: width * height)
        var minX = width, minY = height, maxX = -1, maxY = -1
        for idx in 0..<(width * height) where labels[idx] == winner {
            outGrid[idx] = true
            let y = idx / width, x = idx % width
            if x < minX { minX = x }
            if x > maxX { maxX = x }
            if y < minY { minY = y }
            if y > maxY { maxY = y }
        }
        return (outGrid, (minX, minY, maxX, maxY), sizes[winner])
    }

    // MARK: - Head crop

    /// Clears the top `fraction` of the component's own bounding-box
    /// height, in place within the mask grid, before tracing. A blunt
    /// heuristic, not a head *detector* -- it does not look at the pixels
    /// it removes, only their row position within the bbox. Off by
    /// default; see `Options.headCropFraction`.
    private static func applyHeadCrop(grid: [Bool], width: Int, height: Int,
                                       bbox: (minX: Int, minY: Int, maxX: Int, maxY: Int),
                                       fraction: Double) -> [Bool] {
        let bboxHeight = bbox.maxY - bbox.minY + 1
        let cutRows = Int((Double(bboxHeight) * fraction).rounded())
        guard cutRows > 0 else { return grid }
        var out = grid
        let cutBelowY = min(bbox.minY + cutRows, height)
        for y in bbox.minY..<cutBelowY {
            for x in 0..<width {
                out[y * width + x] = false
            }
        }
        return out
    }

    // MARK: - Boundary trace (Moore-neighbor tracing, clockwise)

    /// Walks the outer edge of the single connected foreground region in
    /// `grid`, returning it as a closed loop of pixel coordinates (first
    /// point never repeated at the end -- matches the outline contract).
    /// `nil` only when `grid` has no true pixel; a single isolated pixel
    /// returns a 1-point "boundary" that the caller's `count >= 3` check
    /// then correctly refuses as degenerate.
    ///
    /// Verified against known shapes before this ever touched a real mask
    /// (see the task report / commit message for the numbers): a filled
    /// rectangle traces to its exact four corners after simplification,
    /// a filled circle traces to a closed loop whose shoelace area lands
    /// within ~1% of the source pixel count, and every consecutive pair
    /// of traced points is an 8-connected step (no jumps, no
    /// self-crossing shortcuts).
    private static func traceBoundary(grid: [Bool], width: Int, height: Int) -> [(Int, Int)]? {
        func isForeground(_ x: Int, _ y: Int) -> Bool {
            guard x >= 0, x < width, y >= 0, y < height else { return false }
            return grid[y * width + x]
        }
        // Clockwise neighbor offsets starting at West. West is picked as
        // index 0 because the start pixel (below) is found by a row-major
        // scan, which guarantees the pixel immediately West of it is
        // background -- that gives the walk a safe, always-correct initial
        // backtrack direction with no separate first-step special case.
        let directions: [(Int, Int)] = [(-1, 0), (-1, -1), (0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1)]

        var start: (Int, Int)? = nil
        outer: for y in 0..<height {
            for x in 0..<width where isForeground(x, y) {
                start = (x, y)
                break outer
            }
        }
        guard let startPixel = start else { return nil }

        var boundary: [(Int, Int)] = [startPixel]
        var current = startPixel
        var backtrackDir = 0 // West
        let maxSteps = width * height * 8 + 8
        var steps = 0

        while steps < maxSteps {
            steps += 1
            var found: (Int, Int)? = nil
            var foundDir = 0
            for step in 1...8 {
                let dir = (backtrackDir + step) % 8
                let (dx, dy) = directions[dir]
                let nx = current.0 + dx, ny = current.1 + dy
                if isForeground(nx, ny) {
                    found = (nx, ny)
                    foundDir = dir
                    break
                }
            }
            guard let next = found else {
                // Current pixel has no foreground neighbor at all: an
                // isolated single-pixel component. Nothing left to walk.
                return boundary
            }
            // The direction we arrived from, as seen from the pixel we
            // just moved to, is the opposite of the direction we moved in.
            backtrackDir = (foundDir + 4) % 8
            current = next
            if current == startPixel {
                break
            }
            boundary.append(current)
        }
        return boundary
    }

    // MARK: - Douglas-Peucker simplification (closed polygon)

    private static func perpendicularDistance(_ point: (x: Double, y: Double),
                                                _ a: (x: Double, y: Double),
                                                _ b: (x: Double, y: Double)) -> Double {
        let dx = b.x - a.x, dy = b.y - a.y
        if dx == 0 && dy == 0 {
            let ex = point.x - a.x, ey = point.y - a.y
            return (ex * ex + ey * ey).squareRoot()
        }
        let t = ((point.x - a.x) * dx + (point.y - a.y) * dy) / (dx * dx + dy * dy)
        let projX = a.x + t * dx, projY = a.y + t * dy
        let ex = point.x - projX, ey = point.y - projY
        return (ex * ex + ey * ey).squareRoot()
    }

    private static func rdp(_ points: [(x: Double, y: Double)], epsilon: Double) -> [(x: Double, y: Double)] {
        guard points.count >= 3 else { return points }
        let a = points[0], b = points[points.count - 1]
        var maxDist = -1.0
        var maxIndex = -1
        for i in 1..<(points.count - 1) {
            let d = perpendicularDistance(points[i], a, b)
            if d > maxDist {
                maxDist = d
                maxIndex = i
            }
        }
        if maxDist > epsilon, maxIndex > 0 {
            let left = rdp(Array(points[0...maxIndex]), epsilon: epsilon)
            let right = rdp(Array(points[maxIndex...]), epsilon: epsilon)
            return left.dropLast() + right
        }
        return [a, b]
    }

    /// Douglas-Peucker on a *closed* loop needs an anchor pair, or the
    /// single seam between the list's first and last point never gets
    /// simplified. The anchor here is the two traced points farthest apart
    /// from each other (sampled, not exhaustively -- exhaustive is O(n^2)
    /// and this only needs a good split, not the provably best one): the
    /// loop is cut into two open arcs at that pair, each arc is simplified
    /// against its own chord independently, and the two results are
    /// spliced back into one closed polygon.
    private static func simplifyClosedPolygon(_ points: [(Int, Int)], epsilon: Double) -> [(Int, Int)] {
        guard points.count >= 4 else { return points }
        let doublePoints = points.map { (x: Double($0.0), y: Double($0.1)) }
        let n = doublePoints.count
        let step = max(1, n / 200)

        var bestSquaredDist = -1.0
        var bestI = 0, bestJ = 1
        var i = 0
        while i < n {
            var j = 0
            while j < n {
                if i != j {
                    let dx = doublePoints[i].x - doublePoints[j].x
                    let dy = doublePoints[i].y - doublePoints[j].y
                    let d = dx * dx + dy * dy
                    if d > bestSquaredDist {
                        bestSquaredDist = d
                        bestI = i
                        bestJ = j
                    }
                }
                j += step
            }
            i += step
        }
        let lo = min(bestI, bestJ), hi = max(bestI, bestJ)
        let arc1 = Array(doublePoints[lo...hi])
        let arc2 = Array(doublePoints[hi...]) + Array(doublePoints[0...lo])

        let simplified1 = rdp(arc1, epsilon: epsilon)
        let simplified2 = rdp(arc2, epsilon: epsilon)
        let combined = simplified1.dropLast() + simplified2.dropLast()
        // Every retained point is one of the original traced points --
        // Douglas-Peucker only selects a subset, it never interpolates --
        // so rounding back to Int here is exact, not lossy.
        return combined.map { (Int($0.x.rounded()), Int($0.y.rounded())) }
    }

    // MARK: - EXIF orientation

    private static func readOrientation(_ source: CGImageSource) -> CGImagePropertyOrientation {
        guard let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
              let raw = properties[kCGImagePropertyOrientation] as? UInt32,
              let orientation = CGImagePropertyOrientation(rawValue: raw) else {
            return .up
        }
        return orientation
    }

    /// Vision's mask/pixel-buffer outputs are delivered in the *upright*
    /// orientation the `orientation` parameter tells the request handler
    /// to interpret the image as -- so the width/height this type reports
    /// (and every outline point's scale) has to be the upright dimensions
    /// too, not `cgImage.width`/`.height`, which are the raw storage
    /// dimensions and swap relative to upright whenever `orientation`
    /// is a 90-or-270-degree rotation.
    ///
    /// Exercised in testing only for `.up` (a synthetic PNG with no EXIF
    /// rotation, and NSImage inputs, which always report `.up`); the
    /// swapped-dimension branch below is implemented against Apple's
    /// documented contract but has not itself been run against a rotated
    /// real photo in this task.
    private static func displayDimensions(cgImage: CGImage, orientation: CGImagePropertyOrientation) -> (Int, Int) {
        switch orientation {
        case .left, .leftMirrored, .right, .rightMirrored:
            return (cgImage.height, cgImage.width)
        default:
            return (cgImage.width, cgImage.height)
        }
    }

    // MARK: - Refusals

    private static func refusal(_ verdict: String, howToClose: String, extra: [String: Any]) -> [String: Any] {
        var out: [String: Any] = ["verdict": verdict, "how_to_close": howToClose]
        for (key, value) in extra { out[key] = value }
        return out
    }
}
