import Foundation

#if !ATELIER_REAL_IMAGE_PIPELINE_STANDALONE
import XCTest
#endif

/// Standalone integration audit for the beginner image route.
///
/// Computer Use cannot reliably cross the native picker boundary, so this
/// harness injects an existing image path at the contract immediately below
/// `AtelierIntake.ingest(_:)`: the same intake MCP calls, source/clip ledger,
/// equal-path selection revision, and one-turn composer attachment state.  It
/// then executes the proposal-only MCP stages and checks that the app source
/// still connects those stages through the router, Vera factory, rear
/// continuation, CAD controls, and dynamic cards.  It adds no runtime door to
/// the application and never copies or modifies the source image.
private enum AtelierRealImagePipelineAudit {
    struct Report {
        var failures: [String] = []
        var trace: [[String: Any]] = []
        var imagePath = ""
    }

    private struct IntakeMirror {
        var selectedPath: String?
        var selectionRevision: UInt64 = 0
        var composerAttachmentVisible = false

        mutating func publish(_ path: String) {
            selectionRevision &+= 1
            selectedPath = path
            composerAttachmentVisible = true
        }

        mutating func clearComposerAttachment() {
            composerAttachmentVisible = false
        }
    }

    private enum AuditFailure: Error, CustomStringConvertible {
        case message(String)

        var description: String {
            switch self {
            case .message(let text): return text
            }
        }
    }

    private final class MCPClient {
        private let repositoryRoot: URL
        private let temporaryHome: URL

        init(repositoryRoot: URL, temporaryHome: URL) {
            self.repositoryRoot = repositoryRoot
            self.temporaryHome = temporaryHome
        }

        func call(_ tool: String, _ arguments: [String: Any] = [:]) throws
            -> [String: Any] {
            let request: [String: Any] = [
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": ["name": tool, "arguments": arguments],
            ]
            let input = try JSONSerialization.data(
                withJSONObject: request, options: [.sortedKeys])
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
            process.arguments = ["python3", "-m", "photoloset.mcp"]
            process.currentDirectoryURL = repositoryRoot
            var environment = ProcessInfo.processInfo.environment
            environment["PHOTOLOSET_HOME"] = temporaryHome.path
            let existingPythonPath = environment["PYTHONPATH"] ?? ""
            environment["PYTHONPATH"] = repositoryRoot.path
                + (existingPythonPath.isEmpty ? "" : ":\(existingPythonPath)")
            process.environment = environment

            let standardInput = Pipe()
            let standardOutput = Pipe()
            let standardError = Pipe()
            process.standardInput = standardInput
            process.standardOutput = standardOutput
            process.standardError = standardError
            try process.run()
            standardInput.fileHandleForWriting.write(input)
            standardInput.fileHandleForWriting.write(Data([0x0A]))
            try? standardInput.fileHandleForWriting.close()
            process.waitUntilExit()

            let output = standardOutput.fileHandleForReading.readDataToEndOfFile()
            let errors = standardError.fileHandleForReading.readDataToEndOfFile()
            guard process.terminationStatus == 0 else {
                throw AuditFailure.message(
                    "MCP_PROCESS_FAILED_\(tool):"
                    + String(data: errors, encoding: .utf8).orEmpty)
            }
            let lines = String(data: output, encoding: .utf8).orEmpty
                .split(whereSeparator: \Character.isNewline)
            guard let last = lines.last,
                  let outerData = String(last).data(using: .utf8),
                  let outer = try JSONSerialization.jsonObject(with: outerData)
                    as? [String: Any],
                  let rpcResult = outer["result"] as? [String: Any],
                  let content = rpcResult["content"] as? [[String: Any]],
                  let text = content.first?["text"] as? String,
                  let resultData = text.data(using: .utf8),
                  let result = try JSONSerialization.jsonObject(with: resultData)
                    as? [String: Any] else {
                throw AuditFailure.message("MCP_RESPONSE_UNREADABLE_\(tool)")
            }
            return result
        }
    }

    static func run(imagePath requestedPath: String? = nil) -> Report {
        var report = Report()
        let appRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let repositoryRoot = appRoot.deletingLastPathComponent()
        auditSwiftReachability(appRoot: appRoot, report: &report)

        guard let imageURL = resolveImage(requestedPath),
              FileManager.default.fileExists(atPath: imageURL.path),
              let imageData = try? Data(contentsOf: imageURL),
              !imageData.isEmpty else {
            report.failures.append("REAL_FASHION_CROP_IMAGE_UNAVAILABLE")
            return report
        }
        report.imagePath = imageURL.path
        report.trace.append(event(
            "REAL_FILE_PATH_INJECTED", actor: "ATELIER_INTAKE_STANDALONE",
            detail: ["path": imageURL.path, "bytes": imageData.count]))

        let temporaryHome = FileManager.default.temporaryDirectory
            .appendingPathComponent(
                "photoloset-atelier-real-image-audit-\(UUID().uuidString)",
                isDirectory: true)
        do {
            try FileManager.default.createDirectory(
                at: temporaryHome, withIntermediateDirectories: true)
        } catch {
            report.failures.append("AUDIT_TEMPORARY_HOME_UNAVAILABLE")
            return report
        }
        defer { try? FileManager.default.removeItem(at: temporaryHome) }

        let client = MCPClient(
            repositoryRoot: repositoryRoot, temporaryHome: temporaryHome)
        let imageDigest = "fnv1a64:" + fnv1a64(imageData)
        let source: [String: Any] = [
            "image_digest": imageDigest,
            "image_id": imageURL.lastPathComponent,
            "orientation": "UP",
        ]

        do {
            try auditIntake(
                client: client, imageURL: imageURL, report: &report)
            try auditProposalModes(
                client: client, source: source, report: &report)
            try auditCADModifiers(client: client, report: &report)
        } catch {
            report.failures.append(String(describing: error))
        }

        let requiredRuntimeStates: Set<String> = [
            "ATTACHMENT_VISIBLE",
            "ATTACHMENT_CLEARED_ACTIVE_IMAGE_RETAINED",
            "SAME_IMAGE_RESELECTED_REVISION_2",
            "HUMAN_SEPARATION_PROPOSED",
            "AUTO_SEPARATION_PROPOSED",
            "HUMAN_BODY_PROXY_PROPOSED",
            "AUTO_BODY_PROXY_PROPOSED",
            "CAD_PULL_REVISION_REACHED",
            "CAD_STRETCH_REVISION_REACHED",
            "CAD_WIND_PREVIEW_REVISION_REACHED",
        ]
        let reached = Set(report.trace.compactMap { $0["state"] as? String })
        let missing = requiredRuntimeStates.subtracting(reached).sorted()
        if !missing.isEmpty {
            report.failures.append(
                "RUNTIME_STATES_NOT_REACHED:" + missing.joined(separator: ","))
        }
        return report
    }

    private static func auditIntake(
        client: MCPClient, imageURL: URL, report: inout Report
    ) throws {
        var mirror = IntakeMirror()
        let arguments: [String: Any] = [
            "path": imageURL.path,
            "kind": "image",
            "at": "2026-08-29T00:00:00Z",
            "note": "standalone integration audit; source image is not copied",
        ]
        let firstRegister = try client.call("intake_register", arguments)
        try requireVerdict(firstRegister, "ANSWER", "INTAKE_FIRST_REGISTER")
        let clipArguments: [String: Any] = [
            "source_path": imageURL.path,
            "clip_path": imageURL.path,
            "mark": "still",
            "seconds": 0.0,
        ]
        try requireVerdict(
            try client.call("intake_add_clip", clipArguments),
            "ANSWER", "INTAKE_FIRST_CLIP")
        mirror.publish(imageURL.path)
        report.trace.append(event(
            "ATTACHMENT_VISIBLE", actor: "ATELIER_INTAKE_STANDALONE",
            detail: ["selection_revision": Int(mirror.selectionRevision)]))

        mirror.clearComposerAttachment()
        guard mirror.selectedPath == imageURL.path,
              mirror.composerAttachmentVisible == false else {
            throw AuditFailure.message("ATTACHMENT_CLEAR_LOST_ACTIVE_IMAGE")
        }
        report.trace.append(event(
            "ATTACHMENT_CLEARED_ACTIVE_IMAGE_RETAINED",
            actor: "ATELIER_INTAKE_STANDALONE"))

        try requireVerdict(
            try client.call("intake_register", arguments),
            "ANSWER", "INTAKE_RESELECT_REGISTER")
        try requireVerdict(
            try client.call("intake_add_clip", clipArguments),
            "ANSWER", "INTAKE_RESELECT_CLIP")
        mirror.publish(imageURL.path)
        guard mirror.selectionRevision == 2,
              mirror.composerAttachmentVisible,
              mirror.selectedPath == imageURL.path else {
            throw AuditFailure.message("SAME_IMAGE_RESELECT_STATE_INVALID")
        }
        report.trace.append(event(
            "SAME_IMAGE_RESELECTED_REVISION_2",
            actor: "ATELIER_INTAKE_STANDALONE"))

        let ledger = try client.call("intake_report")
        try requireVerdict(ledger, "ANSWER", "INTAKE_REPORT")
        let sources = ledger["sources"] as? [[String: Any]] ?? []
        let matching = sources.filter { ($0["path"] as? String) == imageURL.path }
        guard matching.count == 1,
              let clips = matching.first?["clips"] as? [[String: Any]],
              clips.filter({ ($0["path"] as? String) == imageURL.path }).count == 1
        else {
            throw AuditFailure.message("RESELECTION_DUPLICATED_EVIDENCE")
        }
    }

    private static func auditProposalModes(
        client: MCPClient, source: [String: Any], report: inout Report
    ) throws {
        for mode in ["HUMAN_APPROVAL", "AUTO_PROPOSED"] {
            let separationRequest: [String: Any] = [
                "schema": "garment.body-image-separation.request.v1",
                "source": source,
                "selection_mode": mode,
            ]
            let separation = try client.call(
                "garment_body_image_separation_propose",
                ["json_text": try jsonString(separationRequest)])
            try requireVerdict(
                separation,
                "PROPOSED_BODY_GARMENT_SEPARATION_CANDIDATES",
                "BODY_IMAGE_SEPARATION_\(mode)")
            guard separation["rear_state"] as? String == "UNKNOWN_UNOBSERVED",
                  separation["manufacturing_ready"] as? Bool == false,
                  separation["manufacturing_certified"] as? Bool == false,
                  isEmptyArray(separation["fact_promotions"]),
                  let candidates = separation["candidates"] as? [[String: Any]],
                  !candidates.isEmpty,
                  candidates.allSatisfy({ candidate in
                      candidate["state"] as? String
                        == "PROPOSED_BODY_GARMENT_SEPARATION"
                  }) else {
                throw AuditFailure.message(
                    "BODY_IMAGE_SEPARATION_AUTHORITY_ESCAPED_\(mode)")
            }
            let separationSelection = separation["selection"] as? [String: Any]
            if mode == "HUMAN_APPROVAL" {
                guard separationSelection?["status"] as? String
                        == "HUMAN_APPROVAL_REQUIRED",
                      separationSelection?["selected_candidate_id"] is NSNull
                        || separationSelection?["selected_candidate_id"] == nil
                else {
                    throw AuditFailure.message(
                        "HUMAN_SEPARATION_AUTO_SELECTED")
                }
            } else {
                guard separationSelection?["status"] as? String
                        == "AUTO_PROPOSED_SELECTED",
                      separationSelection?["selected_candidate_id"] as? String != nil
                else {
                    throw AuditFailure.message(
                        "AUTO_SEPARATION_DID_NOT_SELECT_PROPOSAL")
                }
            }
            report.trace.append(event(
                mode == "HUMAN_APPROVAL"
                    ? "HUMAN_SEPARATION_PROPOSED"
                    : "AUTO_SEPARATION_PROPOSED",
                actor: "VERA_BODY_IMAGE_SEPARATION_MCP",
                detail: ["mode": mode, "candidate_count": candidates.count]))

            let proxyRequest: [String: Any] = [
                "schema": "garment.body-proxy.request.v1",
                "source": source,
                "selection_mode": mode,
            ]
            let proxy = try client.call(
                "garment_body_proxy_propose",
                ["json_text": try jsonString(proxyRequest)])
            try requireVerdict(
                proxy, "PROPOSED_BODY_PROXY_CANDIDATES",
                "BODY_PROXY_\(mode)")
            guard proxy["manufacturing_ready"] as? Bool == false,
                  proxy["manufacturing_certified"] as? Bool == false,
                  isEmptyArray(proxy["fact_promotions"]),
                  let proxyCandidates = proxy["candidates"] as? [[String: Any]],
                  !proxyCandidates.isEmpty,
                  proxyCandidates.allSatisfy({ candidate in
                      guard candidate["state"] as? String == "PROPOSED_BODY_PROXY",
                            let rear = candidate["rear_generation_constraints"]
                                as? [String: Any]
                      else { return false }
                      return rear["rear_surface_observed"] as? Bool == false
                  }) else {
                throw AuditFailure.message("BODY_PROXY_AUTHORITY_ESCAPED_\(mode)")
            }
            report.trace.append(event(
                mode == "HUMAN_APPROVAL"
                    ? "HUMAN_BODY_PROXY_PROPOSED"
                    : "AUTO_BODY_PROXY_PROPOSED",
                actor: "VERA_BODY_PROXY_MCP",
                detail: ["mode": mode, "candidate_count": proxyCandidates.count]))
        }
    }

    private static func auditCADModifiers(
        client: MCPClient, report: inout Report
    ) throws {
        var surface: [String: Any] = [
            "schema": "garment.target-sculpt-surface.v1",
            "vertices_cm": [
                [0.0, 0.0, 0.0], [2.0, 0.0, 0.0],
                [2.0, 2.0, 0.0], [0.0, 2.0, 0.0],
            ],
            "faces": [[0, 1, 2], [0, 2, 3]],
            "revision": 0,
        ]
        let modifiers: [(String, [String: Any])] = [
            ("PULL", [
                "kind": "PULL", "face_indices": [0],
                "direction": "LOCAL_NORMAL", "distance_cm": 0.5,
            ]),
            ("STRETCH", [
                "kind": "STRETCH", "vertex_indices": [1, 2],
                "anchor_cm": [0.0, 0.0, 0.0],
                "axis_vector": [1.0, 0.0, 0.0], "scale_factor": 1.1,
            ]),
            ("WIND_PREVIEW", [
                "kind": "WIND_PREVIEW",
                "wind_vector_m_s": [2.0, 0.0, 0.0],
                "preview_gain_cm_per_m_s": 0.1,
                "anchor_vertex_indices": [0],
            ]),
        ]
        for (expectedRevision, entry) in modifiers.enumerated() {
            var request: [String: Any] = [
                "schema": "garment.target-sculpt-modifier.request.v1",
                "sculpt_surface": surface,
                "expected_revision": expectedRevision,
                "modifier": entry.1,
            ]
            if let digest = surface["digest"] as? String {
                request["expected_digest"] = digest
            }
            let response = try client.call(
                "garment_target_sculpt_modifier",
                ["json_text": try jsonString(request)])
            try requireVerdict(
                response, "PROPOSED_CAD_MODIFIER", "CAD_\(entry.0)")
            guard response["authority"] as? String == "PROPOSED_CAD_MODIFIER",
                  response["manufacturing_ready"] as? Bool == false,
                  response["manufacturing_certified"] as? Bool == false,
                  isEmptyArray(response["fact_promotions"]),
                  response["revision"] as? Int == expectedRevision + 1,
                  let child = response["sculpt_surface"] as? [String: Any],
                  child["revision"] as? Int == expectedRevision + 1,
                  child["digest"] as? String != nil else {
                throw AuditFailure.message("CAD_MODIFIER_BOUNDARY_INVALID_\(entry.0)")
            }
            surface = child
            report.trace.append(event(
                "CAD_\(entry.0)_REVISION_REACHED",
                actor: "VERA_CAD_MODIFIER_MCP",
                detail: ["revision": expectedRevision + 1]))
        }
    }

    private static func auditSwiftReachability(
        appRoot: URL, report: inout Report
    ) {
        let paths = [
            "intake": "Sources/Verantyx/Views/AtelierIntake.swift",
            "router": "Sources/Verantyx/Engine/AtelierChatRouter.swift",
            "controller": "Sources/Verantyx/Engine/GarmentFactoryReactController.swift",
            "cards": "Sources/Verantyx/Views/AtelierDynamicFlowView.swift",
            "state": "Sources/Verantyx/AppState.swift",
        ]
        var source: [String: String] = [:]
        for (key, path) in paths {
            guard let text = try? String(
                contentsOf: appRoot.appendingPathComponent(path), encoding: .utf8)
            else {
                report.failures.append("SWIFT_SOURCE_UNREADABLE_\(key.uppercased())")
                return
            }
            source[key] = text
        }
        func require(_ condition: @autoclosure () -> Bool, _ code: String) {
            if !condition() { report.failures.append(code) }
        }
        let intake = source["intake"].orEmpty
        let router = source["router"].orEmpty
        let controller = source["controller"].orEmpty
        let cards = source["cards"].orEmpty
        let state = source["state"].orEmpty

        let ingest = blockBody(in: intake, after: "func ingest(").orEmpty
        require(ordered([
            "intake_register", "intake_add_clip", "publishSelection(clips.first)",
        ], in: ingest), "ATELIER_INGEST_CONTRACT_ORDER_BROKEN")
        require(intake.contains("selectionRevision &+= 1")
                && intake.contains("composerAttachmentVisible = true")
                && intake.contains("func clearComposerSelection()")
                && state.contains("AtelierIntake.shared.clearComposerSelection()"),
                "ATTACHMENT_CLEAR_OR_RESELECT_ROUTE_BROKEN")

        let rear = router.range(of: "requestBack3DPreview(")?.lowerBound
        let image = router.range(
            of: "if command.intent == .generateFromImage")?.lowerBound
        require(rear != nil && image != nil && rear! < image!
                && router.contains("AtelierIntake.shared.analysisSelection")
                && router.contains("beginConfirmedImage("),
                "ROUTER_IMAGE_OR_REAR_CONTINUATION_UNREACHABLE")

        let proxy = blockBody(
            in: controller, after: "private func prepareBodyProxyCandidates(")
            .orEmpty
        let begin = blockBody(
            in: controller, after: "func beginConfirmedImage(").orEmpty
        require(ordered([
            "prepareBodyImageSeparation(",
            "garment_body_proxy_propose",
        ], in: proxy)
            && ordered([
                "prepareBodyProxyCandidates(",
                "prepareTargetReconstruction(",
                "door(\"start\"",
                "advance(event: event)",
            ], in: begin),
            "VERA_HARNESS_STAGE_ORDER_BROKEN")
        require(controller.contains("VERA_BODY_IMAGE_SEPARATION_MCP")
                && controller.contains("VERA_BODY_PROXY_MCP")
                && controller.contains("pendingBack3DRequest = true")
                && controller.contains("PROPOSED_TARGET_BOUND_REAR_PREVIEW")
                && controller.contains("VERA_CAD_MODIFIER_MCP"),
                "VERA_TYPED_TRACE_OR_REAR_STATE_UNREACHABLE")

        require(cards.contains("visibleFrontInventoryAuditCard")
                && cards.contains("targetReconstructionCard(target)")
                && cards.contains("pendingBack3DRequest")
                && cards.contains("applyTargetSculptModifier(\"PULL\")")
                && cards.contains("applyTargetSculptModifier(\"STRETCH\")")
                && cards.contains("applyTargetSculptModifier(\"WIND_PREVIEW\")")
                && cards.contains("targetSculptModifierStatus"),
                "DYNAMIC_CARD_STATE_IS_NOT_RENDERABLE")

        report.trace.append(event(
            "BACK_3D_REQUEST_CAN_QUEUE", actor: "SWIFT_SOURCE_REACHABILITY",
            detail: ["authority": "PROPOSED_REAR_ONLY"]))
        report.trace.append(event(
            "PROPOSED_TARGET_BOUND_REAR_PREVIEW_CAN_RENDER",
            actor: "SWIFT_SOURCE_REACHABILITY",
            detail: ["rear_observed": false]))
        report.trace.append(event(
            "DYNAMIC_ATELIER_CARDS_REACHABLE",
            actor: "SWIFT_SOURCE_REACHABILITY"))
    }

    private static func resolveImage(_ requestedPath: String?) -> URL? {
        let fileManager = FileManager.default
        let candidates = [
            requestedPath,
            ProcessInfo.processInfo.environment["PHOTOLOSET_ATELIER_AUDIT_IMAGE"],
            fileManager.homeDirectoryForCurrentUser
                .appendingPathComponent("Desktop/vera_fashion_crops_20/male_08.png")
                .path,
        ].compactMap { $0 }.map { URL(fileURLWithPath: $0) }
        if let direct = candidates.first(where: {
            fileManager.fileExists(atPath: $0.path)
        }) { return direct }

        let directory = fileManager.homeDirectoryForCurrentUser
            .appendingPathComponent("Desktop/vera_fashion_crops_20")
        let files = (try? fileManager.contentsOfDirectory(
            at: directory, includingPropertiesForKeys: [.isRegularFileKey],
            options: [.skipsHiddenFiles])) ?? []
        return files.filter {
            ["png", "jpg", "jpeg"].contains($0.pathExtension.lowercased())
        }.sorted { $0.lastPathComponent < $1.lastPathComponent }.dropFirst().first
    }

    private static func requireVerdict(
        _ result: [String: Any], _ expected: String, _ stage: String
    ) throws {
        guard result["verdict"] as? String == expected else {
            throw AuditFailure.message(
                "\(stage)_VERDICT_\(result["verdict"] as? String ?? "MISSING")")
        }
    }

    private static func jsonString(_ object: Any) throws -> String {
        let data = try JSONSerialization.data(
            withJSONObject: object, options: [.sortedKeys])
        guard let text = String(data: data, encoding: .utf8) else {
            throw AuditFailure.message("JSON_ENCODING_FAILED")
        }
        return text
    }

    private static func isEmptyArray(_ value: Any?) -> Bool {
        (value as? [Any])?.isEmpty == true
    }

    private static func fnv1a64(_ data: Data) -> String {
        var hash: UInt64 = 14_695_981_039_346_656_037
        for byte in data {
            hash ^= UInt64(byte)
            hash &*= 1_099_511_628_211
        }
        return String(format: "%016llx", hash)
    }

    private static func event(
        _ state: String, actor: String, detail: [String: Any] = [:]
    ) -> [String: Any] {
        var row = detail
        row["state"] = state
        row["actor"] = actor
        return row
    }

    private static func blockBody(in source: String, after marker: String)
        -> String? {
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
            guard let range = haystack.range(
                of: needle, range: cursor..<haystack.endIndex)
            else { return false }
            cursor = range.upperBound
        }
        return true
    }

    static func jsonReport(_ report: Report) -> String {
        let object: [String: Any] = [
            "verdict": report.failures.isEmpty ? "PASS" : "FAIL",
            "image_path": report.imagePath,
            "failures": report.failures,
            "trace": report.trace,
        ]
        guard let data = try? JSONSerialization.data(
                withJSONObject: object, options: [.prettyPrinted, .sortedKeys]),
              let text = String(data: data, encoding: .utf8)
        else { return "{\"verdict\":\"FAIL\",\"failures\":[\"REPORT_ENCODING\"]}" }
        return text
    }
}

private extension Optional where Wrapped == String {
    var orEmpty: String { self ?? "" }
}

#if !ATELIER_REAL_IMAGE_PIPELINE_STANDALONE
final class AtelierRealImagePipelineAuditTests: XCTestCase {
    func testRealImageIntakeRouterVeraCardsAndCADTrace() {
        let report = AtelierRealImagePipelineAudit.run()
        XCTAssertEqual(
            report.failures, [], AtelierRealImagePipelineAudit.jsonReport(report))
    }
}
#else
@main
private enum AtelierRealImagePipelineAuditMain {
    static func main() {
        let requestedPath = CommandLine.arguments.dropFirst().first
        let report = AtelierRealImagePipelineAudit.run(imagePath: requestedPath)
        print(AtelierRealImagePipelineAudit.jsonReport(report))
        exit(report.failures.isEmpty ? 0 : 1)
    }
}
#endif
