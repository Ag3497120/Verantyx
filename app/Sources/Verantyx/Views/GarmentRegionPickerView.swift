import AppKit
import ImageIO
import SwiftUI

/// Human-in-the-loop bridge between the existing Atelier image intake and
/// `GarmentOutline`. RegionPicker may propose components without evidence;
/// only a component touched by a human seed becomes OBSERVED.
struct GarmentRegionPickerView: View {
    @EnvironmentObject private var app: AppState
    @StateObject private var model = GarmentRegionPickerModel()

    let imagePath: String?
    let onConfirm: ([String: Any]) -> Void

    var body: some View {
        Group {
            if let image = model.image {
                VStack(alignment: .leading, spacing: 9) {
                    HStack(spacing: 8) {
                        Text(app.t("Confirm garment regions", "服の領域を確認"))
                            .font(.system(size: 12.5, weight: .bold))
                            .foregroundStyle(Theme.fg)
                        Spacer()
                        statusLegend
                    }

                    Text(app.t(
                        "Choose a label, then place 3–5 points on the photo. Automatic regions remain PROPOSED; a point makes only the region it touches OBSERVED.",
                        "ラベルを選び、写真に3〜5点置いてください。自動領域は未決のまま、点が触れた領域だけが観測済みになります。"))
                        .font(.system(size: 10.5))
                        .foregroundStyle(Theme.dim)

                    labelPicker
                    automaticCandidatePicker
                    imageCanvas(image)
                        .frame(minHeight: 260, idealHeight: 360, maxHeight: 440)

                    keyboardSeedControls
                    controls
                    if let message = model.message, !message.isEmpty {
                        Text(message)
                            .font(.system(size: 10.5))
                            .foregroundStyle(model.hasBlockingIssue ? Theme.bad : Theme.faint)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                .padding(10)
                .background(Theme.panel.opacity(0.65), in: RoundedRectangle(cornerRadius: 9))
            } else if model.busy {
                HStack(spacing: 8) {
                    ProgressView().controlSize(.small)
                    Text(app.t("Finding candidate regions…", "候補領域を探しています…"))
                        .font(.system(size: 11.5)).foregroundStyle(Theme.dim)
                }
            } else if let message = model.message {
                Text(message)
                    .font(.system(size: 11.5))
                    .foregroundStyle(Theme.bad)
            } else if imagePath != nil {
                // Keep a concrete view mounted while a restored selection is
                // handed to `.task(id:)`. An entirely empty Group has no
                // lifecycle, so its task may never start when the path changes
                // from nil during AtelierIntake.restore().
                HStack(spacing: 8) {
                    ProgressView().controlSize(.small)
                    Text(app.t("Preparing photo…", "写真を準備しています…"))
                        .font(.system(size: 11.5)).foregroundStyle(Theme.dim)
                }
            }
        }
        .task(id: imagePath) {
            await model.load(path: imagePath)
        }
    }

    private var statusLegend: some View {
        HStack(spacing: 8) {
            legend(color: Theme.sel, text: "PROPOSED \(model.proposedCount)", dashed: true)
            legend(color: Color.green, text: "OBSERVED \(model.observedCount)", dashed: false)
        }
    }

    private func legend(color: Color, text: String, dashed: Bool) -> some View {
        HStack(spacing: 4) {
            Capsule()
                .stroke(color, style: StrokeStyle(lineWidth: 1.5, dash: dashed ? [3, 2] : []))
                .frame(width: 17, height: 7)
            Text(text).font(.system(size: 8.5, design: .monospaced)).foregroundStyle(Theme.faint)
        }
    }

    private var labelPicker: some View {
        Picker(app.t("Seed label", "点のラベル"), selection: $model.activeLabel) {
            ForEach(RegionPicker.SemanticLabel.allCases, id: \.self) { label in
                Text(labelName(label)).tag(label)
            }
        }
        .pickerStyle(.segmented)
        .labelsHidden()
        .disabled(model.busy || model.seeds.count >= 5)
    }

    @ViewBuilder
    private var automaticCandidatePicker: some View {
        if !model.automaticCandidates.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Text(app.t("Automatic clothing-mask proposals", "自動衣服マスク候補"))
                        .font(.system(size: 10.5, weight: .semibold))
                        .foregroundStyle(Theme.fg)
                    Spacer()
                    Text(app.t("Selection confirms the proposal choice, not garment semantics.",
                               "選択で確定するのは候補だけで、服の構造ではありません。"))
                        .font(.system(size: 9))
                        .foregroundStyle(Theme.faint)
                }
                HStack(spacing: 7) {
                    ForEach(Array(model.automaticCandidates.enumerated()), id: \.element.candidateID) { index, candidate in
                        let selected = model.selectedAutomaticCandidateID == candidate.candidateID
                        Button {
                            model.selectAutomaticCandidate(candidate.candidateID)
                        } label: {
                            VStack(alignment: .leading, spacing: 3) {
                                HStack(spacing: 5) {
                                    Text(app.t("Candidate \(index + 1)", "候補 \(index + 1)"))
                                        .font(.system(size: 10, weight: .bold))
                                    Text(String(format: "%.2f", candidate.score))
                                        .font(.system(size: 9, design: .monospaced))
                                        .foregroundStyle(Theme.faint)
                                }
                                Text(model.automaticCandidateSummary(candidate))
                                    .font(.system(size: 8.5))
                                    .foregroundStyle(Theme.dim)
                                    .lineLimit(2)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 6)
                            .background(selected ? Theme.sel.opacity(0.18) : Theme.panel.opacity(0.55))
                            .overlay(
                                RoundedRectangle(cornerRadius: 6)
                                    .stroke(selected ? Theme.sel : Theme.faint.opacity(0.35),
                                            lineWidth: selected ? 1.5 : 1)
                            )
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel(app.t("Select automatic clothing candidate \(index + 1)",
                                                  "自動衣服候補 \(index + 1) を選択"))
                    }
                }
            }
        }
    }

    private func imageCanvas(_ image: NSImage) -> some View {
        GeometryReader { geometry in
            let fitted = Self.aspectFitRect(imageSize: image.size, in: geometry.size)
            ZStack(alignment: .topLeading) {
                Color.black.opacity(0.16)
                Image(nsImage: image)
                    .resizable()
                    .aspectRatio(contentMode: .fit)
                    .frame(width: fitted.width, height: fitted.height)
                    .position(x: fitted.midX, y: fitted.midY)

                Canvas { context, _ in
                    drawRegions(context: &context, fitted: fitted)
                    drawSeeds(context: &context, fitted: fitted)
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: 7))
            .contentShape(Rectangle())
            .gesture(
                SpatialTapGesture().onEnded { value in
                    guard fitted.contains(value.location) else { return }
                    Task { await model.addSeed(at: value.location, fittedRect: fitted) }
                }
            )
        }
    }

    private func drawRegions(context: inout GraphicsContext, fitted: CGRect) {
        guard let result = model.result else { return }
        let width = CGFloat(result.provenance.width)
        let height = CGFloat(result.provenance.height)
        guard width > 0, height > 0 else { return }
        let scaleX = fitted.width / width
        let scaleY = fitted.height / height

        if let geometry = model.selectedAutomaticGeometry {
            drawAutomaticGeometry(geometry, context: &context, fitted: fitted,
                                  scaleX: scaleX, scaleY: scaleY)
        }

        // Unselected PROPOSED components remain hidden. Drawing every colour
        // component outlines the studio background and resembles an inverted
        // mask. The selected candidate alone is previewed above; observed
        // human-seeded regions are then drawn on top.
        let observed = result.regions.filter {
            $0.status == .observed && !Self.isLikelyBackground($0, in: result)
        }
        for region in observed {
            var path = Path()
            for edge in region.boundaryEdges {
                path.move(to: CGPoint(x: fitted.minX + CGFloat(edge.start.x) * scaleX,
                                      y: fitted.minY + CGFloat(edge.start.y) * scaleY))
                path.addLine(to: CGPoint(x: fitted.minX + CGFloat(edge.end.x) * scaleX,
                                         y: fitted.minY + CGFloat(edge.end.y) * scaleY))
            }
            let observedRegion = region.status == .observed
            context.stroke(path,
                           with: .color(observedRegion ? color(for: region.semanticLabel) : Theme.sel.opacity(0.7)),
                           style: StrokeStyle(lineWidth: observedRegion ? 2.2 : 1,
                                              dash: observedRegion ? [] : [4, 3]))
        }
    }

    private func drawAutomaticGeometry(
        _ geometry: GarmentOutline.AutomaticClothingCandidateGeometry,
        context: inout GraphicsContext,
        fitted: CGRect,
        scaleX: CGFloat,
        scaleY: CGFloat
    ) {
        func path(_ points: [RegionPicker.PixelPoint], closed: Bool) -> Path {
            var output = Path()
            guard let first = points.first else { return output }
            output.move(to: CGPoint(x: fitted.minX + CGFloat(first.x) * scaleX,
                                    y: fitted.minY + CGFloat(first.y) * scaleY))
            for point in points.dropFirst() {
                output.addLine(to: CGPoint(x: fitted.minX + CGFloat(point.x) * scaleX,
                                           y: fitted.minY + CGFloat(point.y) * scaleY))
            }
            if closed { output.closeSubpath() }
            return output
        }

        context.stroke(path(geometry.outline, closed: true),
                       with: .color(Theme.sel),
                       style: StrokeStyle(lineWidth: 2.0, dash: [5, 3]))
        for boundary in geometry.internalBoundaries {
            context.stroke(path(boundary, closed: true),
                           with: .color(.orange.opacity(0.9)),
                           style: StrokeStyle(lineWidth: 1.4, dash: [3, 2]))
        }
        for line in geometry.internalLines {
            context.stroke(path(line, closed: false),
                           with: .color(.cyan.opacity(0.9)),
                           style: StrokeStyle(lineWidth: 1.3, dash: [2, 2]))
        }
    }

    private func drawSeeds(context: inout GraphicsContext, fitted: CGRect) {
        guard let result = model.result else { return }
        let scaleX = fitted.width / CGFloat(result.provenance.width)
        let scaleY = fitted.height / CGFloat(result.provenance.height)
        for (index, seed) in model.seeds.enumerated() {
            let center = CGPoint(x: fitted.minX + (CGFloat(seed.point.x) + 0.5) * scaleX,
                                 y: fitted.minY + (CGFloat(seed.point.y) + 0.5) * scaleY)
            let marker = CGRect(x: center.x - 7, y: center.y - 7, width: 14, height: 14)
            context.fill(Path(ellipseIn: marker), with: .color(color(for: seed.label)))
            context.stroke(Path(ellipseIn: marker), with: .color(.white), lineWidth: 1.5)
            context.draw(Text("\(index + 1)").font(.system(size: 8, weight: .bold)).foregroundColor(.white),
                         at: center)
        }
    }

    private var controls: some View {
        HStack(spacing: 8) {
            Text(app.t("Seeds: \(model.seeds.count)/5", "点: \(model.seeds.count)/5"))
                .font(.system(size: 10.5, design: .monospaced))
                .foregroundStyle(model.seeds.count >= 3 ? Theme.fg : Theme.faint)
            Spacer()
            if !model.automaticCandidates.isEmpty {
                Button(app.t("Use selected proposal & run", "選択した候補で実行")) {
                    if let outline = model.selectedAutomaticOutline() { onConfirm(outline) }
                }
                .buttonStyle(.borderedProminent)
                .disabled(!model.canConfirmAutomatic || model.busy)
            }
            Button(app.t("Undo", "1点戻す")) {
                Task { await model.undoSeed() }
            }
            .disabled(model.seeds.isEmpty || model.busy)
            Button(app.t("Clear", "消去")) {
                Task { await model.clearSeeds() }
            }
            .disabled(model.seeds.isEmpty || model.busy)
            Button(app.t("Confirm clothing & run", "服の輪郭を確認して実行")) {
                if let outline = model.confirmedOutline() { onConfirm(outline) }
            }
            .buttonStyle(.borderedProminent)
            .disabled(!model.canConfirm || model.busy)
        }
        .font(.system(size: 10.5, weight: .semibold))
    }

    /// Coordinate clicks are not available to every assistive input method.
    /// These four representative positions keep the same explicit human
    /// label-and-place workflow reachable from Full Keyboard Access.
    private var keyboardSeedControls: some View {
        HStack(spacing: 6) {
            Text(app.t("Keyboard point:", "キーボード点:"))
                .font(.system(size: 10.5))
                .foregroundStyle(Theme.faint)
            Button(app.t("Upper left", "左上")) {
                Task { await model.addSeed(normalizedX: 0.42, normalizedY: 0.27) }
            }
            Button(app.t("Upper center", "上中央")) {
                Task { await model.addSeed(normalizedX: 0.50, normalizedY: 0.19) }
            }
            Button(app.t("Center", "中央")) {
                Task { await model.addSeed(normalizedX: 0.50, normalizedY: 0.53) }
            }
            Button(app.t("Lower center", "下中央")) {
                Task { await model.addSeed(normalizedX: 0.50, normalizedY: 0.72) }
            }
        }
        .buttonStyle(.bordered)
        .controlSize(.small)
        .disabled(model.busy || model.seeds.count >= 5)
    }

    private func labelName(_ label: RegionPicker.SemanticLabel) -> String {
        switch label {
        case .hair: return app.t("Hair", "髪")
        case .clothing: return app.t("Clothing", "服")
        case .skin: return app.t("Skin", "肌")
        }
    }

    private func color(for label: RegionPicker.SemanticLabel?) -> Color {
        switch label {
        case .hair: return .purple
        case .clothing: return .green
        case .skin: return .orange
        case nil: return Theme.bad
        }
    }

    /// A studio/background component normally reaches every image edge. It
    /// can contain holes around the subject, which made its boundary look
    /// exactly like an inverted person mask when a clothing seed hit it.
    fileprivate static func isLikelyBackground(_ region: RegionPicker.Region,
                                               in result: RegionPicker.Result) -> Bool {
        let box = region.boundingBox
        let width = result.provenance.width
        let height = result.provenance.height
        let edgesTouched = (box.x <= 0 ? 1 : 0)
            + (box.y <= 0 ? 1 : 0)
            + (box.x + box.width >= width ? 1 : 0)
            + (box.y + box.height >= height ? 1 : 0)
        let imagePixels = max(1, width * height)
        return edgesTouched >= 3 && region.pixelCount * 20 >= imagePixels
    }

    private static func aspectFitRect(imageSize: NSSize, in container: CGSize) -> CGRect {
        guard imageSize.width > 0, imageSize.height > 0,
              container.width > 0, container.height > 0 else { return .zero }
        let scale = min(container.width / imageSize.width, container.height / imageSize.height)
        let size = CGSize(width: imageSize.width * scale, height: imageSize.height * scale)
        return CGRect(x: (container.width - size.width) / 2,
                      y: (container.height - size.height) / 2,
                      width: size.width, height: size.height)
    }
}

@MainActor
final class GarmentRegionPickerModel: ObservableObject {
    @Published private(set) var image: NSImage?
    @Published private(set) var result: RegionPicker.Result?
    @Published private(set) var seeds: [RegionPicker.Seed] = []
    @Published var activeLabel: RegionPicker.SemanticLabel = .clothing
    @Published private(set) var busy = false
    @Published private(set) var message: String?
    @Published private(set) var automaticCandidates: [GarmentOutline.AutomaticClothingMaskCandidate] = []
    @Published private(set) var selectedAutomaticCandidateID: String?
    @Published private(set) var automaticSelectionWasUserInitiated = false

    private var cgImage: CGImage?
    private var loadedPath: String?
    private var automaticGeometryByCandidateID: [String: GarmentOutline.AutomaticClothingCandidateGeometry] = [:]

    var observedCount: Int { result?.regions.filter { $0.status == .observed }.count ?? 0 }
    var proposedCount: Int { result?.regions.filter { $0.status == .proposed }.count ?? 0 }
    var hasBlockingIssue: Bool {
        guard let result else { return message != nil }
        return !result.conflicts.isEmpty || !result.rejectedSeeds.isEmpty
    }
    var canConfirm: Bool {
        guard seeds.count >= 3, seeds.count <= 5, !hasBlockingIssue, let result else { return false }
        let clothing = result.regions.filter {
            $0.status == .observed && $0.semanticLabel == .clothing
        }
        return !clothing.isEmpty && !clothing.contains {
            GarmentRegionPickerView.isLikelyBackground($0, in: result)
        }
    }
    var canConfirmAutomatic: Bool {
        automaticSelectionWasUserInitiated && selectedAutomaticGeometry != nil && !hasBlockingIssue
    }
    var selectedAutomaticGeometry: GarmentOutline.AutomaticClothingCandidateGeometry? {
        guard let selectedAutomaticCandidateID else { return nil }
        return automaticGeometryByCandidateID[selectedAutomaticCandidateID]
    }

    func load(path: String?) async {
        loadedPath = path
        image = nil
        result = nil
        seeds = []
        cgImage = nil
        message = nil
        automaticCandidates = []
        selectedAutomaticCandidateID = nil
        automaticSelectionWasUserInitiated = false
        automaticGeometryByCandidateID = [:]
        guard let path else { return }
        busy = true
        defer { busy = false }
        do {
            let decoded = try Self.decodeThumbnail(path: path)
            guard loadedPath == path else { return }
            cgImage = decoded
            image = NSImage(cgImage: decoded,
                            size: NSSize(width: decoded.width, height: decoded.height))
            let analyzed = try await Self.analyze(decoded, seeds: [])
            guard loadedPath == path else { return }
            result = analyzed
            automaticCandidates = GarmentOutline.rankAutomaticClothingCandidates(from: analyzed)
            automaticGeometryByCandidateID = Dictionary(uniqueKeysWithValues:
                automaticCandidates.compactMap { candidate in
                    GarmentOutline.automaticCandidateGeometry(
                        candidate, in: analyzed, sourceImage: decoded).map {
                            (candidate.candidateID, $0)
                        }
                })
            selectedAutomaticCandidateID = automaticCandidates.first?.candidateID
            message = automaticCandidates.isEmpty
                ? "Place 3–5 labeled points. At least one must be clothing."
                : "Compare the proposed masks and select one, or confirm the clothing with 3–5 labeled points."
        } catch {
            message = error.localizedDescription
        }
    }

    func selectAutomaticCandidate(_ candidateID: String) {
        guard automaticCandidates.contains(where: { $0.candidateID == candidateID }) else { return }
        selectedAutomaticCandidateID = candidateID
        automaticSelectionWasUserInitiated = true
        message = "Selected a proposed mask. Its geometry changed; garment semantics remain unobserved."
    }

    func automaticCandidateSummary(_ candidate: GarmentOutline.AutomaticClothingMaskCandidate) -> String {
        let reasons = GarmentOutline.automaticCandidateReasons(candidate)
        return reasons.prefix(2).joined(separator: " · ")
    }

    func selectedAutomaticOutline() -> [String: Any]? {
        guard automaticSelectionWasUserInitiated,
              let selectedAutomaticCandidateID,
              let result,
              let loadedPath else {
            message = "Select an automatic clothing-mask proposal first."
            return nil
        }
        let exported = GarmentOutline.extractProposedClothing(
            from: result, probes: [], imagePath: loadedPath,
            rankedCandidates: automaticCandidates,
            selectedCandidateID: selectedAutomaticCandidateID,
            selectedByUser: true,
            sourceImage: cgImage)
        if let verdict = exported["verdict"] as? String {
            message = "\(verdict): \(exported["how_to_close"] as? String ?? "")"
            return nil
        }
        message = "User-selected proposed clothing mask exported; structure remains unobserved."
        return exported
    }

    func addSeed(at location: CGPoint, fittedRect: CGRect) async {
        guard !busy, seeds.count < 5, let result, fittedRect.width > 0, fittedRect.height > 0 else { return }
        let x = Int(((location.x - fittedRect.minX) / fittedRect.width * CGFloat(result.provenance.width)).rounded(.down))
        let y = Int(((location.y - fittedRect.minY) / fittedRect.height * CGFloat(result.provenance.height)).rounded(.down))
        let seed = RegionPicker.Seed(x: min(max(0, x), result.provenance.width - 1),
                                     y: min(max(0, y), result.provenance.height - 1),
                                     label: activeLabel)
        await replaceSeeds(seeds + [seed])
    }

    func addSeed(normalizedX: Double, normalizedY: Double) async {
        guard !busy, seeds.count < 5, let result else { return }
        let x = min(max(0, Int((normalizedX * Double(result.provenance.width)).rounded(.down))),
                    result.provenance.width - 1)
        let y = min(max(0, Int((normalizedY * Double(result.provenance.height)).rounded(.down))),
                    result.provenance.height - 1)
        await replaceSeeds(seeds + [RegionPicker.Seed(x: x, y: y, label: activeLabel)])
    }

    func undoSeed() async {
        guard !seeds.isEmpty else { return }
        await replaceSeeds(Array(seeds.dropLast()))
    }

    func clearSeeds() async {
        await replaceSeeds([])
    }

    func confirmedOutline() -> [String: Any]? {
        guard let result else { return nil }
        let exported = GarmentOutline.extractConfirmedClothing(
            from: result, seeds: seeds, sourceImage: cgImage)
        if let verdict = exported["verdict"] as? String {
            message = "\(verdict): \(exported["how_to_close"] as? String ?? "")"
            return nil
        }
        message = "Confirmed clothing boundary exported with RegionPicker provenance."
        return exported
    }

    private func replaceSeeds(_ replacement: [RegionPicker.Seed]) async {
        guard !busy, let cgImage else { return }
        busy = true
        defer { busy = false }
        do {
            let newResult = try await Self.analyze(cgImage, seeds: replacement)
            seeds = replacement
            result = newResult
            if !newResult.conflicts.isEmpty {
                message = "Two labels touch the same region. Undo and place the conflicting point elsewhere."
            } else if !newResult.rejectedSeeds.isEmpty {
                message = "A point landed outside usable image pixels. Undo and place it on the visible subject."
            } else if newResult.regions.contains(where: {
                $0.status == .observed && $0.semanticLabel == .clothing
                    && GarmentRegionPickerView.isLikelyBackground($0, in: newResult)
            }) {
                message = "A clothing point selected the image background. Undo it and place the point inside an opaque garment panel."
            } else if replacement.count < 3 {
                message = "Place \(3 - replacement.count) more point(s); include at least one clothing point."
            } else if !newResult.regions.contains(where: { $0.status == .observed && $0.semanticLabel == .clothing }) {
                message = "Label at least one point as clothing before confirming."
            } else {
                message = "Ready to confirm. Only seeded regions will be exported as evidence."
            }
        } catch {
            message = error.localizedDescription
        }
    }

    private nonisolated static func analyze(_ image: CGImage, seeds: [RegionPicker.Seed]) async throws -> RegionPicker.Result {
        // Do not use Task.detached here. Verantyx can have a long-running
        // cooperative-executor job during startup (for example schema
        // transpilation); on a constrained executor that starves this image
        // task and leaves the picker spinning although the UI is responsive.
        // A dedicated GCD work item makes the human-triggered analysis start
        // independently of those Swift concurrency jobs.
        return try await withCheckedThrowingContinuation { continuation in
            DispatchQueue.global(qos: .userInitiated).async {
                do {
                    continuation.resume(returning:
                        try RegionPicker.pickRegions(in: image, seeds: seeds,
                                                     options: .photo))
                } catch {
                    continuation.resume(throwing: error)
                }
            }
        }
    }

    /// Beginner-mode proposal.  Analyse every component without assigning a
    /// semantic seed, then let the deterministic garment-candidate ranker
    /// choose a *set* of plausible components.  This avoids turning hair,
    /// skin or a prop into clothing merely because one of five fixed points
    /// happened to land on it.  No automatic component becomes OBSERVED.
    nonisolated static func automaticClothingProposal(path: String) async -> [String: Any] {
        do {
            let image = try decodeThumbnail(path: path)
            let result = try await analyze(image, seeds: [])
            let candidates = GarmentOutline.rankAutomaticClothingCandidates(from: result)
            var proposal = GarmentOutline.extractProposedClothing(
                from: result, probes: [], imagePath: path,
                rankedCandidates: candidates,
                sourceImage: image)

            // The colour-component ranker above is useful evidence for later
            // garment decomposition, but it is the wrong authority for the
            // first CAD target.  A white blouse, navy vest, red trousers and
            // a translucent overlay can legitimately be four disconnected
            // components; selecting only the top-ranked colour made the
            // editable target collapse to the narrow slab seen in the app.
            //
            // The cleanup stage intentionally starts from the *whole salient
            // foreground* (person/mannequin + clothing).  A person then erases
            // hair/body/background and adopts what remains.  Keep this mask in
            // a separate typed field so it can never be mistaken for a
            // garment-only observation or pattern input.
            let fused = GarmentOutline.extract(
                fileURL: URL(fileURLWithPath: path))
            if fused["verdict"] == nil,
               let fusedOutline = fused["outline"] as? [[Double]],
               fusedOutline.count >= 3 {
                proposal["fused_target_outline"] = fusedOutline
                proposal["fused_target_width_px"] = fused["width_px"] ?? image.width
                proposal["fused_target_height_px"] = fused["height_px"] ?? image.height
                proposal["fused_target_state"] = "PROPOSED"
                proposal["fused_target_role"] = "FUSED_PERSON_AND_GARMENT_CAD_TARGET"
                proposal["fused_target_source"] = fused["source"]
                    ?? "salient foreground subject mask"
                proposal["fused_target_warning"] = [
                    "not garment-only: head, hair, skin and body may be included",
                    "for reversible CAD cleanup and same-camera comparison only",
                    "does not observe rear geometry, seams, material or pattern pieces",
                ]
            } else if let verdict = fused["verdict"] as? String {
                proposal["fused_target_verdict"] = verdict
                proposal["fused_target_how_to_close"] = fused["how_to_close"]
                    ?? "use a photo with one clear foreground subject"
            }
            return proposal
        } catch {
            return ["verdict": "UNKNOWN_AUTOMATIC_CLOTHING_REGION",
                    "why": error.localizedDescription,
                    "how_to_close": "服領域を3〜5点で確認してください"]
        }
    }

    private nonisolated static func decodeThumbnail(path: String) throws -> CGImage {
        let url = URL(fileURLWithPath: path) as CFURL
        guard let source = CGImageSourceCreateWithURL(url, nil) else {
            throw CocoaError(.fileReadCorruptFile)
        }
        let options: [CFString: Any] = [
            kCGImageSourceCreateThumbnailFromImageAlways: true,
            kCGImageSourceCreateThumbnailWithTransform: true,
            // RegionPicker materializes scanlines and boundary edges for
            // every color component. 900px photographs can create hundreds
            // of thousands of tiny texture components and keep one CPU core
            // busy for minutes before the human can place a seed. The picker
            // is an interaction mask, not the final pattern resolution; the
            // confirmed boundary is scaled through width_px/height_px.
            kCGImageSourceThumbnailMaxPixelSize: 360,
            kCGImageSourceShouldCacheImmediately: true,
        ]
        guard let image = CGImageSourceCreateThumbnailAtIndex(source, 0, options as CFDictionary) else {
            throw CocoaError(.fileReadCorruptFile)
        }
        return image
    }
}

// MARK: - RegionPicker → GarmentOutline contract

extension GarmentOutline {
    /// Deterministic evidence used to rank one RegionPicker component.  These
    /// are geometric/image-mask heuristics, never garment observations.
    struct AutomaticClothingComponentAssessment: Equatable {
        let regionID: Int
        let score: Double
        let coverageFraction: Double
        let centralBandFraction: Double
        let verticalZoneCount: Int
        let proximityScore: Double
        let symmetryScore: Double
        let pairedSymmetryScore: Double
        let hairRisk: Double
        let accessoryRisk: Double
        let headZoneRisk: Double
        let backgroundRisk: Double
        let eligible: Bool
        let rejectionReasons: [String]
    }

    struct AutomaticClothingMaskCandidate: Equatable {
        let candidateID: String
        let selectedRegionIDs: [Int]
        let score: Double
        let verticalZoneCount: Int
        let bodySpanFraction: Double
        let assessments: [AutomaticClothingComponentAssessment]
    }

    struct AutomaticClothingCandidateGeometry: Equatable {
        let candidateID: String
        let selectedRegionIDs: [Int]
        let outline: [RegionPicker.PixelPoint]
        let internalBoundaries: [[RegionPicker.PixelPoint]]
        let internalLines: [[RegionPicker.PixelPoint]]
        let geometryDigest: String
    }

    static func automaticCandidateReasons(
        _ candidate: AutomaticClothingMaskCandidate
    ) -> [String] {
        var reasons: [String] = []
        if candidate.selectedRegionIDs.count > 1 { reasons.append("MULTI_COMPONENT_COVERAGE") }
        if candidate.verticalZoneCount >= 2 { reasons.append("MULTI_ZONE_BODY_COVERAGE") }
        if candidate.bodySpanFraction >= 0.42 { reasons.append("LONG_BODY_SPAN") }
        if candidate.assessments.contains(where: { $0.symmetryScore >= 0.60 }) {
            reasons.append("SELF_SYMMETRY_SUPPORT")
        }
        if candidate.assessments.contains(where: { $0.pairedSymmetryScore >= 0.58 }) {
            reasons.append("PAIRED_COMPONENT_SUPPORT")
        }
        if reasons.isEmpty { reasons.append("CENTRAL_GARMENT_GEOMETRY_SCORE") }
        return reasons
    }

    static func automaticCandidateGeometry(
        _ candidate: AutomaticClothingMaskCandidate,
        in result: RegionPicker.Result,
        sourceImage: CGImage?
    ) -> AutomaticClothingCandidateGeometry? {
        let selected = Set(candidate.selectedRegionIDs)
        let clothing = result.regions.filter { selected.contains($0.id) }
            .sorted { $0.id < $1.id }
        guard !clothing.isEmpty else { return nil }
        let loops = clothing.flatMap { boundaryLoops(from: $0.boundaryEdges) }
        let outline: [RegionPicker.PixelPoint]
        if clothing.count == 1 {
            outline = loops.max(by: { abs(polygonArea($0)) < abs(polygonArea($1)) }) ?? []
        } else {
            outline = horizontalEnvelope(of: clothing)
        }
        guard outline.count >= 3, abs(polygonArea(outline)) > 0 else { return nil }
        let boundaries = proposedInternalBoundaries(in: clothing, frame: result.provenance)
        let lines = proposedInternalLines(
            in: sourceImage, regions: clothing, frame: result.provenance)
        let boundaryPoints = boundaries.map(\.points)
        let linePoints = lines.map(\.points)
        let digest = automaticGeometryDigest(
            candidateID: candidate.candidateID,
            regionIDs: candidate.selectedRegionIDs,
            frame: result.provenance,
            outline: outline,
            internalBoundaries: boundaryPoints,
            internalLines: linePoints)
        return AutomaticClothingCandidateGeometry(
            candidateID: candidate.candidateID,
            selectedRegionIDs: candidate.selectedRegionIDs,
            outline: outline,
            internalBoundaries: boundaryPoints,
            internalLines: linePoints,
            geometryDigest: digest)
    }

    private static func automaticGeometryDigest(
        candidateID: String,
        regionIDs: [Int],
        frame: RegionPicker.Provenance,
        outline: [RegionPicker.PixelPoint],
        internalBoundaries: [[RegionPicker.PixelPoint]],
        internalLines: [[RegionPicker.PixelPoint]]
    ) -> String {
        func encoded(_ points: [RegionPicker.PixelPoint]) -> String {
            points.map { "\($0.x),\($0.y)" }.joined(separator: ";")
        }
        let canonical = [
            "candidate=\(candidateID)",
            "regions=\(regionIDs.sorted().map(String.init).joined(separator: ","))",
            "frame=\(frame.width)x\(frame.height)",
            "outline=\(encoded(outline))",
            "boundaries=\(internalBoundaries.map(encoded).joined(separator: "|"))",
            "lines=\(internalLines.map(encoded).joined(separator: "|"))",
        ].joined(separator: "\n")
        var hash: UInt64 = 14_695_981_039_346_656_037
        for byte in canonical.utf8 {
            hash ^= UInt64(byte)
            hash &*= 1_099_511_628_211
        }
        return String(format: "fnv1a64:%016llx", hash)
    }

    /// Rank every sufficiently large PROPOSED component, then assemble up to
    /// three alternative masks.  The first candidate is the highest-scoring
    /// component *set*, so separate tops/bottoms and paired sleeves survive.
    /// Stable region IDs and explicit tie breaks make identical pixels return
    /// byte-for-byte identical candidate ordering.
    static func rankAutomaticClothingCandidates(
        from result: RegionPicker.Result
    ) -> [AutomaticClothingMaskCandidate] {
        let frame = result.provenance
        let frameArea = max(1, frame.width * frame.height)
        let minimumPixels = max(16, frameArea / 2_500)
        let proposed = result.regions
            .filter { $0.status == .proposed && $0.pixelCount >= minimumPixels }
            .sorted {
                $0.pixelCount == $1.pixelCount ? $0.id < $1.id : $0.pixelCount > $1.pixelCount
            }
        // Bound pair-comparison work on textured photos while retaining the
        // largest 256 deterministic components. Tiny omitted fragments remain
        // unobserved and can still be added through the human confirmation UI.
        let considered = Array(proposed.prefix(256))
        guard !considered.isEmpty else { return [] }

        let assessments = considered.map { region in
            automaticComponentAssessment(region, peers: considered, result: result)
        }.sorted {
            if $0.score != $1.score { return $0.score > $1.score }
            return $0.regionID < $1.regionID
        }
        let byID = Dictionary(uniqueKeysWithValues: assessments.map { ($0.regionID, $0) })
        let regionByID = Dictionary(uniqueKeysWithValues: considered.map { ($0.id, $0) })
        guard let best = assessments.first(where: { $0.eligible }) else { return [] }

        let scoreFloor = max(22.0, best.score - 24.0)
        let credible = assessments.filter {
            $0.eligible && $0.score >= scoreFloor
                && $0.hairRisk < 0.78 && $0.accessoryRisk < 0.82
                && $0.headZoneRisk < 0.72
        }

        var primaryIDs: [Int] = [best.regionID]
        for assessment in credible where assessment.regionID != best.regionID {
            guard let region = regionByID[assessment.regionID] else { continue }
            let related = primaryIDs.compactMap { regionByID[$0] }.contains {
                automaticRegionsAreRelated(region, $0, frame: frame)
            }
            let expandsZones = automaticVerticalZones(for: region, frame: frame)
                .subtracting(primaryIDs.compactMap { regionByID[$0] }
                    .reduce(into: Set<Int>()) { $0.formUnion(automaticVerticalZones(for: $1, frame: frame)) })
                .isEmpty == false
            if related || (assessment.centralBandFraction >= 0.35 && expandsZones) {
                primaryIDs.append(assessment.regionID)
            }
            if primaryIDs.count == 8 { break }
        }

        var proposedSets: [[Int]] = [primaryIDs]
        if primaryIDs.count > 1 {
            proposedSets.append(Array(primaryIDs.dropLast()))
        } else if credible.count > 1 {
            proposedSets.append([best.regionID, credible[1].regionID])
        }
        let expanded = assessments.filter {
            $0.eligible && $0.score >= max(16.0, best.score - 34.0)
                && $0.backgroundRisk < 0.75 && $0.headZoneRisk < 0.90
                && ($0.centralBandFraction >= 0.18 || $0.pairedSymmetryScore >= 0.58)
        }.prefix(8).map(\.regionID)
        if !expanded.isEmpty { proposedSets.append(expanded) }

        var seen = Set<String>()
        let candidates = proposedSets.compactMap { ids -> AutomaticClothingMaskCandidate? in
            let stableIDs = Array(Set(ids)).sorted()
            let key = stableIDs.map(String.init).joined(separator: ",")
            guard !stableIDs.isEmpty, seen.insert(key).inserted else { return nil }
            let selectedAssessments = stableIDs.compactMap { byID[$0] }
            let regions = stableIDs.compactMap { regionByID[$0] }
            guard !regions.isEmpty else { return nil }
            let zones = regions.reduce(into: Set<Int>()) {
                $0.formUnion(automaticVerticalZones(for: $1, frame: frame))
            }
            let minY = regions.map { $0.boundingBox.y }.min() ?? 0
            let maxY = regions.map { $0.boundingBox.y + $0.boundingBox.height }.max() ?? minY
            let span = clamped(Double(maxY - minY) / Double(max(1, frame.height)))
            let average = selectedAssessments.map(\.score).reduce(0, +)
                / Double(max(1, selectedAssessments.count))
            let risk = selectedAssessments.map {
                max($0.hairRisk, max($0.accessoryRisk, $0.headZoneRisk))
            }.reduce(0, +) / Double(max(1, selectedAssessments.count))
            let setScore = roundedScore(average + 18.0 * Double(zones.count) / 3.0
                + 15.0 * span - 4.0 * Double(max(0, stableIDs.count - 1))
                - 10.0 * risk)
            return AutomaticClothingMaskCandidate(
                candidateID: "mask-regions-" + stableIDs.map(String.init).joined(separator: "-"),
                selectedRegionIDs: stableIDs, score: setScore,
                verticalZoneCount: zones.count, bodySpanFraction: roundedScore(span),
                assessments: selectedAssessments)
        }.sorted {
            if $0.score != $1.score { return $0.score > $1.score }
            if $0.selectedRegionIDs.count != $1.selectedRegionIDs.count {
                return $0.selectedRegionIDs.count > $1.selectedRegionIDs.count
            }
            return $0.candidateID < $1.candidateID
        }
        return Array(candidates.prefix(3))
    }

    private static func automaticComponentAssessment(
        _ region: RegionPicker.Region,
        peers: [RegionPicker.Region],
        result: RegionPicker.Result
    ) -> AutomaticClothingComponentAssessment {
        let frame = result.provenance
        let box = region.boundingBox
        let frameArea = Double(max(1, frame.width * frame.height))
        let coverage = Double(region.pixelCount) / frameArea
        let widthFraction = Double(box.width) / Double(max(1, frame.width))
        let centerX = (Double(box.x) + Double(box.width) / 2.0) / Double(max(1, frame.width))
        let centerY = (Double(box.y) + Double(box.height) / 2.0) / Double(max(1, frame.height))
        let aspect = Double(box.height) / Double(max(1, box.width))
        let centralPixels = region.scanlineRuns.reduce(0) { partial, run in
            let lo = max(run.xStart, Int(Double(frame.width) * 0.20))
            let hi = min(run.xEnd, Int(Double(frame.width) * 0.80))
            return partial + max(0, hi - lo + 1)
        }
        let central = Double(centralPixels) / Double(max(1, region.pixelCount))
        let zones = automaticVerticalZones(for: region, frame: frame)
        let proximity = clamped(1.0 - sqrt(
            pow((centerX - 0.5) / 0.48, 2) + pow((centerY - 0.55) / 0.62, 2)))
        let symmetry = automaticSelfSymmetry(region, frame: frame)
        let pairedSymmetry = peers.filter { $0.id != region.id }.map {
            automaticPairSymmetry(region, $0, frame: frame)
        }.max() ?? 0

        let narrowness = clamped((0.20 - widthFraction) / 0.15)
        let tallness = clamped((aspect - 1.65) / 2.5)
        let startsHigh = clamped((0.42 - Double(box.y) / Double(max(1, frame.height))) / 0.36)
        let hairRisk = clamped(narrowness * (0.55 * tallness + 0.45 * startsHigh))
        let peripheral = clamped((abs(centerX - 0.5) - 0.14) / 0.34)
        let smallness = clamped((0.035 - coverage) / 0.032)
        let accessoryRisk = clamped(0.50 * peripheral + 0.30 * smallness + 0.20 * narrowness)
        let bottomY = Double(box.y + box.height) / Double(max(1, frame.height))
        let headZoneRisk = clamped((0.38 - bottomY) / 0.18) * clamped(central * 1.2)

        let edgeCount = automaticEdgeTouchCount(box, frame: frame)
        var backgroundRisk = 0.0
        if GarmentRegionPickerView.isLikelyBackground(region, in: result) { backgroundRisk = 1.0 }
        backgroundRisk = max(backgroundRisk,
            clamped(Double(edgeCount) / 3.0) * clamped((coverage - 0.04) / 0.28))
        if coverage > 0.60 { backgroundRisk = 1.0 }

        var reasons: [String] = []
        if backgroundRisk >= 0.75 { reasons.append("BACKGROUND_EDGE_AREA_RISK") }
        if coverage < 0.0006 { reasons.append("AREA_TOO_SMALL") }
        if central < 0.08 && pairedSymmetry < 0.45 { reasons.append("OUTSIDE_BODY_CENTRAL_BAND") }
        let eligible = reasons.isEmpty
        let score = roundedScore(
            28.0 * min(1.0, coverage / 0.12)
                + 22.0 * central
                + 18.0 * Double(zones.count) / 3.0
                + 12.0 * proximity
                + 8.0 * symmetry
                + 8.0 * pairedSymmetry
                - 34.0 * hairRisk
                - 24.0 * accessoryRisk
                - 38.0 * headZoneRisk
                - 60.0 * backgroundRisk)
        return AutomaticClothingComponentAssessment(
            regionID: region.id, score: score,
            coverageFraction: roundedScore(coverage),
            centralBandFraction: roundedScore(central), verticalZoneCount: zones.count,
            proximityScore: roundedScore(proximity), symmetryScore: roundedScore(symmetry),
            pairedSymmetryScore: roundedScore(pairedSymmetry),
            hairRisk: roundedScore(hairRisk), accessoryRisk: roundedScore(accessoryRisk),
            headZoneRisk: roundedScore(headZoneRisk), backgroundRisk: roundedScore(backgroundRisk),
            eligible: eligible, rejectionReasons: reasons)
    }

    private static func automaticVerticalZones(
        for region: RegionPicker.Region,
        frame: RegionPicker.Provenance
    ) -> Set<Int> {
        let ranges = [(0.18, 0.42), (0.38, 0.66), (0.62, 0.92)]
        var zones = Set<Int>()
        for (index, range) in ranges.enumerated() {
            let low = Int(Double(frame.height) * range.0)
            let high = Int(Double(frame.height) * range.1)
            let pixels = region.scanlineRuns.filter { $0.y >= low && $0.y < high }
                .reduce(0) { $0 + $1.xEnd - $1.xStart + 1 }
            if pixels >= max(4, region.pixelCount / 80) { zones.insert(index) }
        }
        return zones
    }

    private static func automaticRegionsAreRelated(
        _ lhs: RegionPicker.Region,
        _ rhs: RegionPicker.Region,
        frame: RegionPicker.Provenance
    ) -> Bool {
        let a = lhs.boundingBox, b = rhs.boundingBox
        let horizontalGap = max(0, max(a.x, b.x) - min(a.x + a.width, b.x + b.width))
        let verticalGap = max(0, max(a.y, b.y) - min(a.y + a.height, b.y + b.height))
        let xOverlap = max(0, min(a.x + a.width, b.x + b.width) - max(a.x, b.x))
        return (verticalGap <= max(4, Int(Double(frame.height) * 0.10))
                && (xOverlap > 0 || horizontalGap <= Int(Double(frame.width) * 0.12)))
            || automaticPairSymmetry(lhs, rhs, frame: frame) >= 0.62
    }

    private static func automaticSelfSymmetry(
        _ region: RegionPicker.Region,
        frame: RegionPicker.Provenance
    ) -> Double {
        let center = Double(frame.width) / 2.0
        var weighted = 0.0, total = 0.0
        for run in region.scanlineRuns {
            let length = Double(run.xEnd - run.xStart + 1)
            let runCenter = (Double(run.xStart + run.xEnd) + 1.0) / 2.0
            weighted += length * clamped(1.0 - abs(runCenter - center) / max(1.0, center * 0.75))
            total += length
        }
        return total > 0 ? clamped(weighted / total) : 0
    }

    private static func automaticPairSymmetry(
        _ lhs: RegionPicker.Region,
        _ rhs: RegionPicker.Region,
        frame: RegionPicker.Provenance
    ) -> Double {
        let a = lhs.boundingBox, b = rhs.boundingBox
        let acx = Double(a.x) + Double(a.width) / 2.0
        let bcx = Double(b.x) + Double(b.width) / 2.0
        let mirrorError = abs((acx + bcx) - Double(frame.width)) / Double(max(1, frame.width))
        let verticalError = abs((Double(a.y) + Double(a.height) / 2.0)
            - (Double(b.y) + Double(b.height) / 2.0)) / Double(max(1, frame.height))
        let widthError = abs(Double(a.width - b.width)) / Double(max(1, max(a.width, b.width)))
        let heightError = abs(Double(a.height - b.height)) / Double(max(1, max(a.height, b.height)))
        return clamped(1.0 - (2.8 * mirrorError + 1.8 * verticalError
            + 0.6 * widthError + 0.6 * heightError))
    }

    private static func automaticEdgeTouchCount(
        _ box: RegionPicker.PixelRect,
        frame: RegionPicker.Provenance
    ) -> Int {
        (box.x <= 0 ? 1 : 0) + (box.y <= 0 ? 1 : 0)
            + (box.x + box.width >= frame.width ? 1 : 0)
            + (box.y + box.height >= frame.height ? 1 : 0)
    }

    private static func clamped(_ value: Double) -> Double {
        min(1.0, max(0.0, value))
    }

    private static func roundedScore(_ value: Double) -> Double {
        (value * 1_000_000.0).rounded() / 1_000_000.0
    }

    static func extractProposedClothing(from result: RegionPicker.Result,
                                        probes: [RegionPicker.Seed],
                                        imagePath: String,
                                        rankedCandidates: [AutomaticClothingMaskCandidate]? = nil,
                                        selectedCandidateID: String? = nil,
                                        selectedByUser: Bool = false,
                                        sourceImage: CGImage? = nil) -> [String: Any] {
        guard result.conflicts.isEmpty, result.rejectedSeeds.isEmpty else {
            return ["verdict": "UNKNOWN_AUTOMATIC_REGION_CONFLICT",
                    "how_to_close": "服領域を人が確認してください"]
        }
        let candidateSets = rankedCandidates ?? []
        let selectedCandidate: AutomaticClothingMaskCandidate?
        if let selectedCandidateID {
            selectedCandidate = candidateSets.first { $0.candidateID == selectedCandidateID }
            guard selectedCandidate != nil else {
                return ["verdict": "UNKNOWN_AUTOMATIC_CANDIDATE_ID",
                        "how_to_close": "select one of the current deterministic mask candidates"]
            }
        } else {
            selectedCandidate = candidateSets.first
        }
        let selectedIDs = selectedCandidate.map { Set($0.selectedRegionIDs) }
        let clothing = result.regions.filter { region in
            if let selectedIDs { return selectedIDs.contains(region.id) }
            // Compatibility for explicit test/harness probes. The actual
            // beginner route passes seedless PROPOSED candidates above.
            return region.status == .observed && region.semanticLabel == .clothing
                && !GarmentRegionPickerView.isLikelyBackground(region, in: result)
        }.sorted { $0.id < $1.id }
        guard !clothing.isEmpty else {
            return ["verdict": "UNKNOWN_NO_PROPOSED_CLOTHING_REGION",
                    "how_to_close": "服領域を人が確認してください"]
        }
        let selectedGeometry = selectedCandidate.flatMap {
            automaticCandidateGeometry($0, in: result, sourceImage: sourceImage)
        }
        let loops = clothing.flatMap { boundaryLoops(from: $0.boundaryEdges) }
        let outline = selectedGeometry?.outline ?? (clothing.count == 1
            ? (loops.max(by: { abs(polygonArea($0)) < abs(polygonArea($1)) }) ?? [])
            : horizontalEnvelope(of: clothing))
        guard outline.count >= 3, abs(polygonArea(outline)) > 0 else {
            return ["verdict": outlineDegenerate,
                    "how_to_close": "服領域を人が確認してください"]
        }
        let internalBoundaryEvidenceRecords = proposedInternalBoundaries(
            in: clothing, frame: result.provenance)
        let internalLineEvidenceRecords = proposedInternalLines(
            in: sourceImage, regions: clothing, frame: result.provenance)
        let internalBoundaries = selectedGeometry?.internalBoundaries
            ?? internalBoundaryEvidenceRecords.map(\.points)
        let internalLines = selectedGeometry?.internalLines
            ?? internalLineEvidenceRecords.map(\.points)
        let geometryDigest = selectedGeometry?.geometryDigest
            ?? automaticGeometryDigest(candidateID: "legacy-probe-mask",
                regionIDs: clothing.map(\.id), frame: result.provenance,
                outline: outline, internalBoundaries: internalBoundaries,
                internalLines: internalLines)
        let selectionEvidence: [String: Any] = [
            "state": selectedByUser ? "USER_SELECTED_PROPOSAL" : "PROPOSED_DEFAULT",
            "candidate_id": selectedCandidate?.candidateID ?? "legacy-probe-mask",
            "score": selectedCandidate?.score ?? 0.0,
            "reasons": selectedCandidate.map(automaticCandidateReasons)
                ?? ["LEGACY_EXPLICIT_PROBE_COMPATIBILITY"],
            "geometry_digest": geometryDigest,
            "authority_scope": selectedByUser
                ? "the user selected which proposed image mask to continue with"
                : "the deterministic ranker supplied the preview default",
            "does_not_observe": ["garment_structure", "back", "seams", "layers", "material"],
        ]
        return [
            "outline": outline.map { [Double($0.x), Double($0.y)] },
            "internal_boundaries": internalBoundaries.map { boundary in
                boundary.map { [Double($0.x), Double($0.y)] }
            },
            "internal_boundaries_state": "PROPOSED",
            "internal_boundary_evidence": internalBoundaryEvidenceRecords.enumerated().map {
                internalBoundaryEvidence($0.element, index: $0.offset)
            },
            "internal_lines": internalLines.map { line in
                line.map { [Double($0.x), Double($0.y)] }
            },
            "internal_lines_state": "PROPOSED",
            "internal_line_evidence": internalLineEvidenceRecords.enumerated().map {
                internalLineEvidence($0.element, index: $0.offset)
            },
            "regions": clothing.map {
                regionEvidence($0, state: "PROPOSED", frame: result.provenance)
            },
            "primary_clothing_mask_candidate_id": candidateSets.first?.candidateID ?? "legacy-probe-mask",
            "selected_clothing_mask_candidate_id": selectedCandidate?.candidateID ?? "legacy-probe-mask",
            "selected_clothing_mask_geometry_digest": geometryDigest,
            "automatic_candidate_selection": selectionEvidence,
            "clothing_mask_candidates": candidateSets.enumerated().map { index, candidate in
                automaticCandidateEvidence(candidate, rank: index + 1,
                    result: result, sourceImage: sourceImage)
            },
            "width_px": result.provenance.width,
            "height_px": result.provenance.height,
            "source": "deterministic multi-component clothing ranking; preview proposal only",
            "fixture": false,
            "provenance": [
                "kind": "PROPOSED",
                "algorithm": result.provenance.algorithm,
                "source_image": imagePath,
                "automatic_probes": probes.map {
                    ["x": $0.point.x, "y": $0.point.y,
                     "label": $0.label.rawValue, "kind": "PROPOSED"]
                },
                "selection_strategy": candidateSets.isEmpty
                    ? "legacy explicit probe compatibility"
                    : "seedless deterministic component-set ranking",
                "selected_region_ids": clothing.map(\.id),
                "automatic_candidate_selection_state": selectedByUser
                    ? "USER_SELECTED_PROPOSAL" : "PROPOSED_DEFAULT",
                "automatic_candidate_geometry_digest": geometryDigest,
                "internal_boundaries_kind": "PROPOSED",
                "internal_boundaries_warning": "closed inner loops are geometry-only proposals; their meaning, depth order, and construction are unobserved",
                "internal_lines_kind": "PROPOSED",
                "internal_lines_warning": "weak image transitions are deterministic geometry candidates only; they are not observed seams or construction instructions",
                "warning": "automatic masks remain hypotheses; hair, skin, props, occlusion, and same-colour merged regions can still require human correction",
            ],
        ]
    }

    private static func automaticCandidateEvidence(
        _ candidate: AutomaticClothingMaskCandidate,
        rank: Int,
        result: RegionPicker.Result,
        sourceImage: CGImage?
    ) -> [String: Any] {
        let geometry = automaticCandidateGeometry(
            candidate, in: result, sourceImage: sourceImage)
        return [
            "candidate_id": candidate.candidateID,
            "rank": rank,
            "state": "PROPOSED",
            "semantic": "clothing_mask_candidate",
            "score": candidate.score,
            "reasons": automaticCandidateReasons(candidate),
            "geometry_digest": geometry?.geometryDigest ?? "UNKNOWN_GEOMETRY_DIGEST",
            "geometry_digest_algorithm": "FNV-1a-64 over canonical integer geometry",
            "selected_region_ids": candidate.selectedRegionIDs,
            "vertical_zone_count": candidate.verticalZoneCount,
            "body_span_fraction": candidate.bodySpanFraction,
            "component_assessments": candidate.assessments.map { assessment in
                [
                    "region_id": assessment.regionID,
                    "score": assessment.score,
                    "coverage_fraction": assessment.coverageFraction,
                    "central_band_fraction": assessment.centralBandFraction,
                    "vertical_zone_count": assessment.verticalZoneCount,
                    "proximity_score": assessment.proximityScore,
                    "symmetry_score": assessment.symmetryScore,
                    "paired_symmetry_score": assessment.pairedSymmetryScore,
                    "hair_risk": assessment.hairRisk,
                    "accessory_risk": assessment.accessoryRisk,
                    "head_zone_risk": assessment.headZoneRisk,
                    "background_risk": assessment.backgroundRisk,
                    "eligible": assessment.eligible,
                    "rejection_reasons": assessment.rejectionReasons,
                    "state": "PROPOSED",
                ] as [String: Any]
            },
            "warning": "ranked from deterministic geometry only; not a semantic observation or approval",
        ]
    }

    static func extractConfirmedClothing(from result: RegionPicker.Result,
                                         seeds: [RegionPicker.Seed],
                                         sourceImage: CGImage? = nil) -> [String: Any] {
        guard (3...5).contains(seeds.count) else {
            return ["verdict": "UNKNOWN_REGION_SEEDS_INCOMPLETE",
                    "how_to_close": "place 3 to 5 human-labeled seeds before exporting a clothing boundary"]
        }
        guard result.conflicts.isEmpty, result.rejectedSeeds.isEmpty else {
            return ["verdict": "UNKNOWN_REGION_SEED_CONFLICT",
                    "how_to_close": "remove rejected seeds and ensure no region is assigned more than one human label"]
        }
        let clothing = result.regions
            .filter {
                $0.status == .observed && $0.semanticLabel == .clothing
                    && !GarmentRegionPickerView.isLikelyBackground($0, in: result)
            }
            .sorted { lhs, rhs in
                lhs.pixelCount == rhs.pixelCount ? lhs.id < rhs.id : lhs.pixelCount > rhs.pixelCount
            }
        guard !clothing.isEmpty else {
            return ["verdict": "UNKNOWN_NO_CONFIRMED_CLOTHING_REGION",
                    "how_to_close": "place at least one seed labeled clothing on the garment"]
        }
        let outline: [RegionPicker.PixelPoint]
        if clothing.count == 1 {
            let loops = boundaryLoops(from: clothing[0].boundaryEdges)
            outline = loops.max(by: { abs(polygonArea($0)) < abs(polygonArea($1)) }) ?? []
        } else {
            outline = horizontalEnvelope(of: clothing)
        }
        guard outline.count >= 3, abs(polygonArea(outline)) > 0 else {
            return ["verdict": outlineDegenerate,
                    "how_to_close": "the confirmed clothing region did not form a closed boundary; place a clothing seed on a larger continuous area"]
        }
        let internalBoundaries = proposedInternalBoundaries(
            in: clothing, frame: result.provenance)
        let internalLines = proposedInternalLines(
            in: sourceImage, regions: clothing, frame: result.provenance)

        let seedEvidence: [[String: Any]] = seeds.enumerated().map { index, seed in
            ["input_index": index, "x": seed.point.x, "y": seed.point.y,
             "label": seed.label.rawValue, "kind": "OBSERVED"]
        }
        let provenance: [String: Any] = [
            "kind": "OBSERVED",
            "algorithm": result.provenance.algorithm,
            "source": result.provenance.source,
            "connectivity": result.provenance.connectivity.rawValue,
            "neighbor_color_tolerance": result.provenance.neighborColorTolerance,
            "anchor_color_tolerance": result.provenance.anchorColorTolerance,
            "alpha_threshold": result.provenance.alphaThreshold,
            "human_seeds": seedEvidence,
            "confirmed_clothing_region_ids": clothing.map(\.id),
            "exported_region_ids": clothing.map(\.id),
            "export_rule": "all OBSERVED clothing regions combined as a horizontal outer envelope; no PROPOSED region merged",
            "internal_boundaries_kind": "PROPOSED",
            "internal_boundaries_warning": "human seeds confirm the clothing region only; closed inner loops do not establish seam, overlap, frill, opening, or construction semantics",
            "internal_lines_kind": "PROPOSED",
            "internal_lines_warning": "human seeds confirm the clothing region only; weak image transitions remain unobserved geometry candidates and never establish a seam",
        ]
        return [
            "outline": outline.map { [Double($0.x), Double($0.y)] },
            "internal_boundaries": internalBoundaries.map { boundary in
                boundary.points.map { [Double($0.x), Double($0.y)] }
            },
            "internal_boundaries_state": "PROPOSED",
            "internal_boundary_evidence": internalBoundaries.enumerated().map {
                internalBoundaryEvidence($0.element, index: $0.offset)
            },
            "internal_lines": internalLines.map { line in
                line.points.map { [Double($0.x), Double($0.y)] }
            },
            "internal_lines_state": "PROPOSED",
            "internal_line_evidence": internalLines.enumerated().map {
                internalLineEvidence($0.element, index: $0.offset)
            },
            "regions": clothing.map {
                regionEvidence($0, state: "OBSERVED", frame: result.provenance)
            },
            "width_px": result.provenance.width,
            "height_px": result.provenance.height,
            "source": "RegionPicker clothing boundary confirmed by \(seeds.count) human-labeled seeds; automatic regions remained PROPOSED unless seeded",
            "fixture": false,
            "provenance": provenance,
        ]
    }

    /// A connected RegionPicker component has one maximum-area outer loop;
    /// any other closed loops are holes inside that same component.  Preserve
    /// only holes large enough to survive thumbnail noise.  Their geometry is
    /// useful to later front-structure hypotheses, but neither an automatic
    /// probe nor a human seed observes what a hole means.
    private struct ProposedInternalBoundary {
        let points: [RegionPicker.PixelPoint]
        let regionID: Int
        let areaPixels: Double
        let outerAreaPixels: Double
        let minimumAreaPixels: Double
    }

    private static func proposedInternalBoundaries(
        in regions: [RegionPicker.Region],
        frame: RegionPicker.Provenance
    ) -> [ProposedInternalBoundary] {
        let frameArea = Double(max(1, frame.width * frame.height))
        var boundaries: [ProposedInternalBoundary] = []

        for region in regions.sorted(by: { $0.id < $1.id }) {
            let loops = boundaryLoops(from: region.boundaryEdges)
            guard let outerIndex = loops.indices.max(by: {
                abs(polygonArea(loops[$0])) < abs(polygonArea(loops[$1]))
            }) else { continue }
            let outerArea = abs(polygonArea(loops[outerIndex]))
            guard outerArea > 0 else { continue }

            // Reject antialiasing pinholes deterministically at every image
            // size: at least 16 pixels, 0.05% of the frame, and 0.5% of the
            // containing component's maximum outer loop.
            let minimumArea = max(16.0,
                                  max(frameArea * 0.0005, outerArea * 0.005))
            for index in loops.indices where index != outerIndex {
                let area = abs(polygonArea(loops[index]))
                guard loops[index].count >= 3,
                      area >= minimumArea,
                      area < outerArea else { continue }
                boundaries.append(ProposedInternalBoundary(
                    points: loops[index], regionID: region.id,
                    areaPixels: area, outerAreaPixels: outerArea,
                    minimumAreaPixels: minimumArea))
            }
        }

        return boundaries.sorted {
            if $0.regionID != $1.regionID { return $0.regionID < $1.regionID }
            if $0.areaPixels != $1.areaPixels { return $0.areaPixels > $1.areaPixels }
            let left = $0.points.first ?? RegionPicker.PixelPoint(x: 0, y: 0)
            let right = $1.points.first ?? RegionPicker.PixelPoint(x: 0, y: 0)
            return left.y == right.y ? left.x < right.x : left.y < right.y
        }
    }

    private static func internalBoundaryEvidence(
        _ boundary: ProposedInternalBoundary,
        index: Int
    ) -> [String: Any] {
        [
            "boundary_id": "internal-region-\(boundary.regionID)-\(index)",
            "source_region_id": "region-\(boundary.regionID)",
            "state": "PROPOSED",
            "kind": "PROPOSED",
            "semantic": "UNKNOWN",
            "closed": true,
            "area_px2": boundary.areaPixels,
            "outer_area_px2": boundary.outerAreaPixels,
            "minimum_area_px2": boundary.minimumAreaPixels,
            "basis": "closed inner boundary loop inside one selected clothing region",
            "warning": "may be a switch line, overlap hem, frill boundary, opening, print boundary, or segmentation artifact; no construction meaning was observed",
        ]
    }

    // MARK: - Low-contrast internal switch-line proposals

    /// A weak image transition can be evidence for a waist switch, yoke,
    /// opening, overlap, fold, print boundary, or shadow.  It is deliberately
    /// represented as a two-point geometric proposal; no pixel operation can
    /// promote it to an observed seam or construction instruction.
    private struct ProposedInternalLine {
        let points: [RegionPicker.PixelPoint]
        let directionName: String
        let directionIndex: Int
        let rhoPixels: Double
        let projectedStart: Double
        let projectedEnd: Double
        let lengthPixels: Double
        let supportFraction: Double
        let meanContrast: Double
        let score: Double
        let minimumLengthPixels: Double
    }

    private struct InternalLineSample {
        let point: RegionPicker.PixelPoint
        let projection: Double
        let contrast: Double
        let coherence: Double
    }

    /// Find long, coherent weak gradients strictly inside the union of the
    /// selected clothing regions.  Eight integer directions make this a
    /// deterministic bounded Hough-like search without Vision/ML.  Strong
    /// colour boundaries are intentionally excluded: RegionPicker already
    /// transports those as component geometry, while this path exists for
    /// same-colour and low-contrast construction cues.
    private static func proposedInternalLines(
        in sourceImage: CGImage?,
        regions: [RegionPicker.Region],
        frame: RegionPicker.Provenance
    ) -> [ProposedInternalLine] {
        guard let sourceImage,
              sourceImage.width == frame.width,
              sourceImage.height == frame.height,
              let rgba = rgba8Pixels(from: sourceImage),
              !regions.isEmpty else { return [] }

        let width = frame.width
        let height = frame.height
        let pixelCount = width * height
        var clothingMask = [Bool](repeating: false, count: pixelCount)
        var minX = width, minY = height, maxX = -1, maxY = -1
        for run in regions.flatMap(\.scanlineRuns) {
            guard run.y >= 0, run.y < height else { continue }
            let start = max(0, run.xStart)
            let end = min(width - 1, run.xEnd)
            guard start <= end else { continue }
            minX = min(minX, start); maxX = max(maxX, end)
            minY = min(minY, run.y); maxY = max(maxY, run.y)
            for x in start...end { clothingMask[run.y * width + x] = true }
        }
        guard minX <= maxX, minY <= maxY else { return [] }

        // The 3 px mask erosion removes silhouette edges and region holes.
        // A weak edge must then persist for at least 18 px and a
        // frame/garment-relative distance before it can be exported.
        let interiorMargin = 3
        let minimumContrast = 3.5
        let maximumContrast = 38.0
        let maximumTangentialGradientFraction = 0.42
        let rhoBandWidth = 3.0
        let maximumProjectedGap = 4.5
        let minimumSupportFraction = 0.38
        let garmentSpan = Double(max(1, min(maxX - minX + 1, maxY - minY + 1)))
        let frameDiagonal = hypot(Double(width), Double(height))
        let minimumLength = max(18.0, max(garmentSpan * 0.12, frameDiagonal * 0.04))

        func maskContains(_ x: Int, _ y: Int) -> Bool {
            x >= 0 && y >= 0 && x < width && y < height
                && clothingMask[y * width + x]
        }
        func isInsideErodedClothing(_ x: Int, _ y: Int) -> Bool {
            guard x >= interiorMargin, y >= interiorMargin,
                  x + interiorMargin < width,
                  y + interiorMargin < height else { return false }
            // Cardinal and diagonal probes reject both the exterior outline
            // and narrow antialiasing/texture fragments without an expensive
            // full distance transform.
            for dy in [-interiorMargin, 0, interiorMargin] {
                for dx in [-interiorMargin, 0, interiorMargin]
                    where !maskContains(x + dx, y + dy) { return false }
            }
            return true
        }
        func luminance(_ x: Int, _ y: Int) -> Double {
            let offset = (y * width + x) * 4
            return (54.0 * Double(rgba[offset])
                    + 183.0 * Double(rgba[offset + 1])
                    + 19.0 * Double(rgba[offset + 2])) / 256.0
        }

        let directions: [(dx: Int, dy: Int, name: String)] = [
            (1, 0, "horizontal"), (2, 1, "shallow-down"),
            (1, 1, "diagonal-down"), (1, 2, "steep-down"),
            (0, 1, "vertical"), (1, -2, "steep-up"),
            (1, -1, "diagonal-up"), (2, -1, "shallow-up"),
        ]
        var candidates: [ProposedInternalLine] = []

        for (directionIndex, direction) in directions.enumerated() {
            let norm = hypot(Double(direction.dx), Double(direction.dy))
            let tangentX = Double(direction.dx) / norm
            let tangentY = Double(direction.dy) / norm
            var groups: [Int: [InternalLineSample]] = [:]

            if minX + interiorMargin <= maxX - interiorMargin,
               minY + interiorMargin <= maxY - interiorMargin {
                for y in (minY + interiorMargin)...(maxY - interiorMargin) {
                    for x in (minX + interiorMargin)...(maxX - interiorMargin) {
                        guard isInsideErodedClothing(x, y) else { continue }
                        let gradientX = (
                            luminance(x + 1, y - 1) + 2 * luminance(x + 1, y)
                            + luminance(x + 1, y + 1)
                            - luminance(x - 1, y - 1) - 2 * luminance(x - 1, y)
                            - luminance(x - 1, y + 1)) / 4
                        let gradientY = (
                            luminance(x - 1, y + 1) + 2 * luminance(x, y + 1)
                            + luminance(x + 1, y + 1)
                            - luminance(x - 1, y - 1) - 2 * luminance(x, y - 1)
                            - luminance(x + 1, y - 1)) / 4
                        let contrast = hypot(gradientX, gradientY)
                        guard contrast >= minimumContrast,
                              contrast <= maximumContrast else { continue }
                        let tangential = abs(gradientX * tangentX + gradientY * tangentY)
                            / contrast
                        guard tangential <= maximumTangentialGradientFraction else { continue }
                        let coherence = 1 - tangential
                        let rho = (-tangentY * Double(x) + tangentX * Double(y))
                        let rhoBand = Int((rho / rhoBandWidth).rounded())
                        let projection = tangentX * Double(x) + tangentY * Double(y)
                        groups[rhoBand, default: []].append(InternalLineSample(
                            point: .init(x: x, y: y), projection: projection,
                            contrast: contrast, coherence: coherence))
                    }
                }
            }

            for rhoBand in groups.keys.sorted() {
                let samples = groups[rhoBand]!.sorted {
                    if $0.projection != $1.projection {
                        return $0.projection < $1.projection
                    }
                    if $0.point.y != $1.point.y { return $0.point.y < $1.point.y }
                    return $0.point.x < $1.point.x
                }
                var clusters: [[InternalLineSample]] = []
                var cluster: [InternalLineSample] = []
                var previousProjection: Double?
                for sample in samples {
                    if let previousProjection,
                       sample.projection - previousProjection > maximumProjectedGap {
                        if !cluster.isEmpty { clusters.append(cluster) }
                        cluster = []
                    }
                    cluster.append(sample)
                    previousProjection = sample.projection
                }
                if !cluster.isEmpty { clusters.append(cluster) }

                for cluster in clusters {
                    guard let first = cluster.first, let last = cluster.last else { continue }
                    let length = last.projection - first.projection
                    guard length >= minimumLength else { continue }
                    let occupiedBins = Set(cluster.map { Int($0.projection.rounded()) }).count
                    let support = Double(occupiedBins) / max(1, length + 1)
                    guard support >= minimumSupportFraction else { continue }
                    let meanContrast = cluster.reduce(0) { $0 + $1.contrast }
                        / Double(cluster.count)
                    let meanCoherence = cluster.reduce(0) { $0 + $1.coherence }
                        / Double(cluster.count)
                    let score = length * support * meanCoherence
                    candidates.append(ProposedInternalLine(
                        points: [first.point, last.point],
                        directionName: direction.name,
                        directionIndex: directionIndex,
                        rhoPixels: Double(rhoBand) * rhoBandWidth,
                        projectedStart: first.projection,
                        projectedEnd: last.projection,
                        lengthPixels: length,
                        supportFraction: support,
                        meanContrast: meanContrast,
                        score: score,
                        minimumLengthPixels: minimumLength))
                }
            }
        }

        // Suppress parallel detections produced by the two sides of one thin
        // stitch/fold line.  The stable tie-breakers make identical pixels
        // produce byte-for-byte identical payload order.
        candidates.sort {
            if $0.score != $1.score { return $0.score > $1.score }
            if $0.directionIndex != $1.directionIndex {
                return $0.directionIndex < $1.directionIndex
            }
            if $0.rhoPixels != $1.rhoPixels { return $0.rhoPixels < $1.rhoPixels }
            let left = $0.points[0], right = $1.points[0]
            return left.y == right.y ? left.x < right.x : left.y < right.y
        }
        var accepted: [ProposedInternalLine] = []
        for candidate in candidates {
            let duplicate = accepted.contains { existing in
                guard existing.directionIndex == candidate.directionIndex,
                      abs(existing.rhoPixels - candidate.rhoPixels) < 7 else { return false }
                let overlap = max(0, min(existing.projectedEnd, candidate.projectedEnd)
                                  - max(existing.projectedStart, candidate.projectedStart))
                return overlap >= 0.55 * min(existing.lengthPixels, candidate.lengthPixels)
            }
            if !duplicate { accepted.append(candidate) }
            if accepted.count == 8 { break }
        }
        return accepted
    }

    private static func rgba8Pixels(from image: CGImage) -> [UInt8]? {
        let width = image.width, height = image.height
        guard width > 0, height > 0,
              width <= Int.max / 4,
              height <= Int.max / (width * 4) else { return nil }
        var bytes = [UInt8](repeating: 0, count: width * height * 4)
        let rendered = bytes.withUnsafeMutableBytes { rawBuffer -> Bool in
            guard let base = rawBuffer.baseAddress,
                  let colorSpace = CGColorSpace(name: CGColorSpace.sRGB),
                  let context = CGContext(data: base, width: width, height: height,
                                          bitsPerComponent: 8, bytesPerRow: width * 4,
                                          space: colorSpace,
                                          bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)
            else { return false }
            context.interpolationQuality = .none
            context.translateBy(x: 0, y: CGFloat(height))
            context.scaleBy(x: 1, y: -1)
            context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
            return true
        }
        return rendered ? bytes : nil
    }

    private static func internalLineEvidence(
        _ line: ProposedInternalLine,
        index: Int
    ) -> [String: Any] {
        [
            "line_id": "weak-internal-line-\(index)",
            "state": "PROPOSED",
            "kind": "PROPOSED",
            "semantic": "UNKNOWN",
            "closed": false,
            "direction": line.directionName,
            "length_px": line.lengthPixels,
            "minimum_length_px": line.minimumLengthPixels,
            "support_fraction": line.supportFraction,
            "mean_sobel_contrast": line.meanContrast,
            "contrast_range": ["minimum": 3.5, "maximum": 38.0],
            "interior_margin_px": 3,
            "basis": "long coherent weak gradient inside an eroded selected-clothing mask",
            "warning": "may be a seam, switch line, yoke, overlap, fold, print edge, lighting edge, or texture; construction meaning was not observed",
        ]
    }

    /// Preserve the geometry of separately confirmed components.  The old
    /// outer envelope is still exported for silhouette fitting, but collapsing
    /// every component into that one polygon erased the only local evidence
    /// available for overlays, separate tops/bottoms and disconnected frills.
    private static func regionEvidence(_ region: RegionPicker.Region,
                                       state: String,
                                       frame: RegionPicker.Provenance) -> [String: Any] {
        let loops = boundaryLoops(from: region.boundaryEdges)
        let loop = loops.max(by: {
            abs(polygonArea($0)) < abs(polygonArea($1))
        }) ?? []
        let box = region.boundingBox
        let frameArea = max(1, frame.width * frame.height)
        return [
            "region_id": "region-\(region.id)",
            "semantic_label": region.semanticLabel?.rawValue ?? "unknown",
            "state": state,
            "pixel_count": region.pixelCount,
            "coverage_fraction": Double(region.pixelCount) / Double(frameArea),
            "bounding_box": ["x": box.x, "y": box.y,
                             "width": box.width, "height": box.height],
            "outline": loop.map { [Double($0.x), Double($0.y)] },
            "average_rgba": ["red": Int(region.averageColor.red),
                             "green": Int(region.averageColor.green),
                             "blue": Int(region.averageColor.blue),
                             "alpha": Int(region.averageColor.alpha)],
            "provenance": [
                "algorithm": frame.algorithm,
                "region_id": region.id,
                "human_confirmed": state == "OBSERVED",
            ],
        ]
    }

    /// Combine separately coloured/connected garment parts without pulling
    /// in any unseeded background component. The downstream photo pipeline
    /// measures the left/right extent at each y, so exporting that exact
    /// horizontal envelope preserves all information it can consume.
    private static func horizontalEnvelope(of regions: [RegionPicker.Region])
        -> [RegionPicker.PixelPoint] {
        var spans: [Int: (minX: Int, maxX: Int)] = [:]
        for run in regions.flatMap(\.scanlineRuns) {
            if let span = spans[run.y] {
                spans[run.y] = (min(span.minX, run.xStart),
                                max(span.maxX, run.xEnd + 1))
            } else {
                spans[run.y] = (run.xStart, run.xEnd + 1)
            }
        }
        let rows = spans.keys.sorted()
        let left: [RegionPicker.PixelPoint] = rows.compactMap { y in
            spans[y].map { RegionPicker.PixelPoint(x: $0.minX, y: y) }
        }
        // Keep both chains on the same ordered scan-line ordinates.  Offsetting
        // only the right chain by one pixel made the closing edges cross when
        // a multi-component garment had gaps or rapidly changing widths.  The
        // photo-pattern bridge requires a simple polygon; a pair of y-monotone
        // chains with minX < maxX on every row provides that boundary without
        // inventing connectivity between the individual source components.
        let right: [RegionPicker.PixelPoint] = rows.reversed().compactMap { y in
            spans[y].map { RegionPicker.PixelPoint(x: $0.maxX, y: y) }
        }
        return left + right
    }

    private static func boundaryLoops(from edges: [RegionPicker.BoundaryEdge]) -> [[RegionPicker.PixelPoint]] {
        struct DirectedEdge: Hashable {
            let start: RegionPicker.PixelPoint
            let end: RegionPicker.PixelPoint
        }
        let allEdges = edges.map { DirectedEdge(start: $0.start, end: $0.end) }
        var remaining = Set(allEdges)
        let outgoing = Dictionary(grouping: allEdges, by: \.start)
        var loops: [[RegionPicker.PixelPoint]] = []

        func comesBefore(_ lhs: DirectedEdge, _ rhs: DirectedEdge) -> Bool {
            if lhs.start.y != rhs.start.y { return lhs.start.y < rhs.start.y }
            if lhs.start.x != rhs.start.x { return lhs.start.x < rhs.start.x }
            if lhs.end.y != rhs.end.y { return lhs.end.y < rhs.end.y }
            return lhs.end.x < rhs.end.x
        }

        while let first = remaining.min(by: comesBefore) {
            remaining.remove(first)
            var loop = [first.start, first.end]
            var cursor = first.end
            while cursor != first.start {
                guard let next = outgoing[cursor]?
                    .filter({ remaining.contains($0) })
                    .min(by: comesBefore) else {
                    loop.removeAll()
                    break
                }
                remaining.remove(next)
                cursor = next.end
                loop.append(cursor)
            }
            if loop.count >= 4, loop.last == loop.first {
                loop.removeLast()
                loops.append(loop)
            }
        }
        return loops
    }

    private static func polygonArea(_ points: [RegionPicker.PixelPoint]) -> Double {
        guard points.count >= 3 else { return 0 }
        var sum = 0.0
        for index in points.indices {
            let next = points[(index + 1) % points.count]
            sum += Double(points[index].x * next.y - next.x * points[index].y)
        }
        return sum / 2
    }
}
