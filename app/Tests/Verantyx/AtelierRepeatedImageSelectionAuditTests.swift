import Foundation

#if !ATELIER_REPEATED_IMAGE_SELECTION_STANDALONE
import Combine
import XCTest
@testable import Verantyx
#endif

/// Source-level boundary audit for the macOS beginner garment attachment.
///
/// The audit intentionally covers both sides of the seam: `AtelierIntake`
/// must republish an equal path as a new UI operation, and the beginner
/// buttons must all enter through its one native picker instead of reviving
/// the legacy generic-chat attachment manager.
private enum AtelierRepeatedImageSelectionAudit {
    struct Report { var failures: [String] = [] }

    static func run() -> Report {
        var report = Report()
        let testFile = URL(fileURLWithPath: #filePath)
        let appRoot = testFile.deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let viewsRoot = appRoot.appendingPathComponent("Sources/Verantyx/Views")
        let engineRoot = appRoot.appendingPathComponent("Sources/Verantyx/Engine")
        let repoRoot = appRoot.deletingLastPathComponent()

        guard let intakeRaw = read("AtelierIntake.swift", from: viewsRoot),
              let composerRaw = read("UnifiedComposerView.swift", from: viewsRoot),
              let beginnerRaw = read("AtelierChatPaneView.swift", from: viewsRoot),
              let routerRaw = read("AtelierChatRouter.swift", from: engineRoot),
              let factoryRaw = read("GarmentFactoryReactController.swift", from: engineRoot),
              let jobRaw = read("GarmentGenerationJob.swift", from: engineRoot),
              let ledgerRaw = read(
                "garment.py", from: repoRoot.appendingPathComponent("photoloset"))
        else {
            report.failures.append("ATELIER_ATTACHMENT_SOURCE_UNREADABLE")
            return report
        }

        let intake = executableSource(intakeRaw)
        let composer = executableSource(composerRaw)
        let beginner = executableSource(beginnerRaw)
        let router = executableSource(routerRaw)
        let factory = executableSource(factoryRaw)
        let job = executableSource(jobRaw)

        require(intake.contains("@Published private(set) var selectionRevision"),
                "SELECTION_REVISION_IS_NOT_READ_ONLY_TO_CALLERS", into: &report)
        require(intake.contains("var id: String { path }"),
                "RESELECT_FABRICATES_DUPLICATE_EVIDENCE", into: &report)

        guard let publish = functionBody(in: intake, named: "publishSelection") else {
            report.failures.append("SELECTION_PUBLISHER_MISSING")
            return report
        }
        require(ordered([
            "selectionRevision &+= 1",
            "confirmedClothingOutline = nil",
            "confirmedOutlineImagePath = nil",
            "confirmedOutlineSelectionRevision = nil",
            "selectionInvalidator(selectionRevision, clip.path)",
            "selectedClip = clip",
        ], in: publish) && !publish.contains("Task.yield"),
        "SELECTION_PUBLICATION_IS_NOT_SYNCHRONOUS_REVISION_INVALIDATION_THEN_CLIP",
        into: &report)
        require(publish.contains("guard let clip else") &&
                occurrences(of: "selectionRevision &+= 1", in: intake) == 1,
                "EMPTY_OR_MULTIPLE_SELECTIONS_ADVANCE_THE_REVISION", into: &report)
        require(publish.contains("confirmedClothingOutline = nil") &&
                publish.contains("confirmedOutlineImagePath = nil") &&
                publish.contains("confirmedOutlineSelectionRevision = nil"),
                "RESELECT_REUSES_A_PREVIOUS_IMAGE_OUTLINE", into: &report)
        require(intake.contains("typealias SelectionInvalidator") &&
                intake.contains("AtelierChatRouter.consumeSelectionRevision(") &&
                publish.contains("selectionInvalidator(selectionRevision, clip.path)"),
                "SELECTION_REVISION_IS_NOT_CONSUMED_AS_ANALYSIS_OPERATION",
                into: &report)
        require(publish.contains("matches = []"),
                "RESELECT_REUSES_STALE_SIMILARITY_CANDIDATES", into: &report)

        guard let remember = functionBody(in: intake, named: "rememberConfirmedOutline"),
              let routeRevision = functionBody(
                in: router, named: "consumeSelectionRevision"),
              let execute = functionBody(in: router, named: "execute"),
              let factoryRevision = functionBody(
                in: factory, named: "consumeImageSelection"),
              let jobRevision = functionBody(
                in: job, named: "consumeImageSelection")
        else {
            report.failures.append("SELECTION_ANALYSIS_INVALIDATOR_MISSING")
            return report
        }
        require(intake.contains("struct AnalysisSelection") &&
                intake.contains("var analysisSelection: AnalysisSelection?") &&
                intake.contains("func isCurrent(_ selection: AnalysisSelection)"),
                "ANALYSIS_SELECTION_DOES_NOT_BIND_PATH_AND_REVISION", into: &report)
        require(remember.contains("selectedClip?.path == imagePath") &&
                remember.contains("confirmedOutlineSelectionRevision = selectionRevision"),
                "CONFIRMED_REGION_IS_ONLY_BOUND_TO_PATH", into: &report)
        require(routeRevision.contains("GarmentFactoryReactController.shared.consumeImageSelection") &&
                routeRevision.contains("GarmentGenerationJob.shared.consumeImageSelection"),
                "REVISION_DOES_NOT_INVALIDATE_BOTH_PREVIEW_STORES", into: &report)
        require(execute.contains("AtelierIntake.shared.analysisSelection") &&
                execute.contains("confirmedOutlineSelectionRevision == selected.revision") &&
                occurrences(of: "isCurrent(selected)", in: execute) >= 3 &&
                execute.contains("UNKNOWN_STALE_IMAGE_SELECTION"),
                "ROUTER_CAN_REUSE_STALE_REGION_OR_FACTORY_RESULT", into: &report)
        require(factoryRevision.contains("shapeCandidates.removeAll()") &&
                factoryRevision.contains("materialCandidates.removeAll()") &&
                factoryRevision.contains("previewArtifact = nil") &&
                factoryRevision.contains("candidateManufacturingPreview = nil") &&
                factoryRevision.contains("visionPatternOperations.removeAll()") &&
                factoryRevision.contains("visionPipelineArtifacts = [:]") &&
                !factoryRevision.contains("intake_register"),
                "FACTORY_CANDIDATE_CACHE_SURVIVES_RESELECTION", into: &report)
        require(jobRevision.contains("activeSnapshot = .empty") &&
                jobRevision.contains("pendingPreview = nil") &&
                jobRevision.contains("committedSnapshots = [.empty]") &&
                !jobRevision.contains("intake_register"),
                "LEGACY_JOB_PREVIEW_SURVIVES_RESELECTION", into: &report)
        require(ledgerRaw.contains(
                    "existing = next((s for s in self.sources if s.path == str(p)), None)") &&
                ledgerRaw.contains("if existing:") &&
                ledgerRaw.contains("return existing") &&
                ledgerRaw.contains("if c.mark == mark:") &&
                ledgerRaw.contains("return c"),
                "SAME_SOURCE_OR_CLIP_CAN_BE_DUPLICATED_AS_EVIDENCE", into: &report)

        guard let picker = functionBody(in: intake, named: "pickAndIngest"),
              let ingest = functionBody(in: intake, named: "ingest")
        else {
            report.failures.append("INTAKE_PICKER_OR_INGEST_MISSING")
            return report
        }
        require(occurrences(of: "NSOpenPanel()", in: intake) == 1 &&
                occurrences(of: "NSOpenPanel()", in: picker) == 1,
                "ATELIER_INTAKE_HAS_MULTIPLE_NATIVE_PICKERS", into: &report)
        require(picker.contains("panel.canChooseDirectories = false") &&
                picker.contains("panel.allowedContentTypes = [.movie, .image]") &&
                picker.contains("withCheckedContinuation") &&
                picker.contains("panel.begin") &&
                !picker.contains("runModal") &&
                picker.contains("await ingest(url)") &&
                !picker.contains("AttachmentManager") &&
                !picker.contains("intake_register") &&
                !picker.contains("selectedClip ="),
                "PICKER_BYPASSES_THE_SHARED_INGEST_PATH", into: &report)
        require(occurrences(of: "publishSelection(clips.first)", in: ingest) == 1 &&
                !ingest.contains("await publishSelection") &&
                !ingest.contains("selectedClip = clips.first"),
                "INGEST_BYPASSES_EQUAL_PATH_REPUBLICATION", into: &report)

        guard let attachmentControl = propertyBody(
            in: composer, named: "attachmentControl"),
              let attachMedia = functionBody(in: composer, named: "attachMedia"),
              let attachPhoto = functionBody(in: beginner, named: "attachPhoto")
        else {
            report.failures.append("BEGINNER_ATTACHMENT_ENTRY_MISSING")
            return report
        }
        let atelierControl = attachmentControl.components(separatedBy: "} else {").first ?? ""
        require(atelierControl.contains("if app.veraEngineMode == .atelier") &&
                atelierControl.contains("Button(action: attachMedia)") &&
                atelierControl.contains(".focusable()") &&
                atelierControl.contains(".keyboardShortcut(\"i\", modifiers: [.command, .shift])") &&
                !atelierControl.contains("JCrossMenu") &&
                !atelierControl.contains("Add a file"),
                "ATELIER_COMPOSER_ATTACHMENT_IS_NOT_ONE_FOCUSABLE_SHORTCUT_PATH",
                into: &report)
        require(attachMedia.contains("await intake.pickAndIngest()") &&
                occurrences(of: "await intake.pickAndIngest()", in: attachMedia) == 1,
                "COMPOSER_PHOTO_BUTTON_DOES_NOT_USE_THE_SINGLE_PICKER",
                into: &report)
        require(attachPhoto.contains("await intake.pickAndIngest()") &&
                !attachPhoto.contains("NSOpenPanel") &&
                !attachPhoto.contains("AttachmentManager"),
                "BEGINNER_PHOTO_BUTTON_HAS_A_SECOND_ATTACHMENT_PATH",
                into: &report)
        require(composer.contains("AtelierIntake.shared") &&
                beginner.contains("AtelierIntake.shared"),
                "BEGINNER_SURFACES_DO_NOT_SHARE_THE_SAME_INTAKE",
                into: &report)
        require(composer.contains(".id(intake.selectionRevision)") &&
                beginner.contains("confirmedOutlineSelectionRevision") &&
                beginner.contains("== intake.selectionRevision"),
                "BEGINNER_UI_DOES_NOT_RENDER_THE_CURRENT_SELECTION_OPERATION",
                into: &report)

        return report
    }

    private static func read(_ name: String, from root: URL) -> String? {
        try? String(contentsOf: root.appendingPathComponent(name), encoding: .utf8)
    }

    private static func executableSource(_ source: String) -> String {
        source.components(separatedBy: .newlines)
            .map { line -> String in
                guard let range = line.range(of: "//") else { return line }
                return String(line[..<range.lowerBound])
            }
            .joined(separator: "\n")
    }

    private static func functionBody(in source: String, named name: String) -> String? {
        blockBody(in: source, after: "func \(name)(")
    }

    private static func propertyBody(in source: String, named name: String) -> String? {
        blockBody(in: source, after: "var \(name):")
    }

    private static func blockBody(in source: String, after marker: String) -> String? {
        guard let signature = source.range(of: marker),
              let open = source[signature.upperBound...].firstIndex(of: "{")
        else { return nil }
        var depth = 0
        var cursor = open
        while cursor < source.endIndex {
            if source[cursor] == "{" { depth += 1 }
            if source[cursor] == "}" {
                depth -= 1
                if depth == 0 { return String(source[open...cursor]) }
            }
            cursor = source.index(after: cursor)
        }
        return nil
    }

    private static func ordered(_ needles: [String], in haystack: String) -> Bool {
        var cursor = haystack.startIndex
        for needle in needles {
            guard let range = haystack.range(of: needle, range: cursor..<haystack.endIndex)
            else { return false }
            cursor = range.upperBound
        }
        return true
    }

    private static func occurrences(of needle: String, in haystack: String) -> Int {
        guard !needle.isEmpty else { return 0 }
        var count = 0
        var cursor = haystack.startIndex
        while let range = haystack.range(of: needle, range: cursor..<haystack.endIndex) {
            count += 1
            cursor = range.upperBound
        }
        return count
    }

    private static func require(_ condition: @autoclosure () -> Bool,
                                _ failure: String,
                                into report: inout Report) {
        if !condition() { report.failures.append(failure) }
    }
}

#if !ATELIER_REPEATED_IMAGE_SELECTION_STANDALONE
final class AtelierRepeatedImageSelectionAuditTests: XCTestCase {
    func testRepeatedSelectionAndSingleAttachmentPath() {
        XCTAssertEqual(AtelierRepeatedImageSelectionAudit.run().failures, [])
    }

    @MainActor
    func testEqualPathSelectionPublishesOncePerRevisionWithoutYieldGap() {
        var sequence: [String] = []
        var invalidations: [(UInt64, String)] = []
        let intake = AtelierIntake(selectionInvalidator: { revision, path in
            invalidations.append((revision, path))
            sequence.append("invalidate:\(revision)")
        })
        let path = "/tmp/same-garment.png"
        let clip = AtelierIntake.Clip(path: path, mark: "still", seconds: 0,
                                      sourcePath: path)
        var publications: [String?] = []
        let cancellable = intake.$selectedClip.dropFirst().sink { selected in
            publications.append(selected?.path)
            sequence.append("publish:\(selected?.path ?? "nil")")
        }

        intake.confirmedClothingOutline = ["points": [[0, 0], [1, 0], [1, 1]]]
        intake.confirmedOutlineImagePath = path
        intake.publishSelection(clip)
        intake.confirmedClothingOutline = ["points": [[0, 0], [2, 0], [2, 2]]]
        intake.confirmedOutlineImagePath = path
        intake.publishSelection(clip)

        XCTAssertEqual(intake.selectionRevision, 2)
        XCTAssertEqual(invalidations.map(\.0), [1, 2])
        XCTAssertEqual(invalidations.map(\.1), [path, path])
        XCTAssertEqual(publications, [path, path],
                       "@Published must emit the equal Clip assignment twice")
        XCTAssertEqual(sequence, [
            "invalidate:1", "publish:\(path)",
            "invalidate:2", "publish:\(path)",
        ])
        XCTAssertNil(intake.confirmedClothingOutline)
        XCTAssertNil(intake.confirmedOutlineImagePath)
        XCTAssertNil(intake.confirmedOutlineSelectionRevision)
        withExtendedLifetime(cancellable) {}
    }
}
#else
@main
private enum AtelierRepeatedImageSelectionAuditMain {
    static func main() {
        let failures = AtelierRepeatedImageSelectionAudit.run().failures
        if failures.isEmpty {
            print("PASS repeated garment image selection and single attachment path")
        } else {
            failures.forEach { print("FAIL \($0)") }
            exit(1)
        }
    }
}
#endif
