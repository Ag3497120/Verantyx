import AppKit
import Foundation

#if !GARMENT_FRONT_IMAGE_CANDIDATE_PIPELINE_STANDALONE
import XCTest
@testable import Verantyx
#endif

/// Focused regression audit for the front-image candidate boundary.
///
/// The executable half calls the production vision parser. The source half
/// guards the preview authority boundary because the app test target is not
/// available in every local build. Compile this file with the production
/// controller and the standalone flag to run both halves from the terminal.
private enum GarmentFrontImageCandidatePipelineAudit {
    /// One front observation deliberately contains more semantic detail than
    /// the old body/front/back three-piece preview can represent.
    static let richFrontFixture = #"""
    {"candidates":[{
      "candidate_id":"rich-visible-front",
      "back_design":"rear is not visible in the source image",
      "assumptions":["all listed parts are visible-front proposals"],
      "parts":[
        {"part_id":"front-body","kind":"BODY_SHELL","layer":0,
         "placement":"front torso","garment_unit":"rich-look",
         "visible_basis":"fitted front torso boundary",
         "dimensions":{"height_cm":44,"circumference_cm":92}},
        {"part_id":"bilateral-sleeves","kind":"SLEEVE","layer":1,
         "placement":"both arms","garment_unit":"rich-look",
         "attached_to":"front-body","side":"bilateral","quantity":2,
         "visible_basis":"two visible sleeves with matching cuffs",
         "dimensions":{"length_cm":58,"upper_circumference_cm":34,
                       "cuff_circumference_cm":20}},
        {"part_id":"outer-layer","kind":"OVERLAY","layer":1,
         "placement":"front upper body","garment_unit":"rich-look",
         "attached_to":"front-body",
         "visible_basis":"separate visible outer layer",
         "dimensions":{"height_cm":36,"width_cm":48}},
        {"part_id":"asymmetric-layer","kind":"OVERLAY","layer":2,
         "placement":"left front","garment_unit":"rich-look",
         "attached_to":"outer-layer","side":"left",
         "detail_role":"asymmetric_front_layer",
         "visible_basis":"asymmetric pointed layer visible only on the left",
         "dimensions":{"height_cm":42,"width_cm":29}},
        {"part_id":"front-cutout","kind":"OPENING","layer":2,
         "placement":"center front cutout","garment_unit":"rich-look",
         "attached_to":"front-body","detail_role":"cutout",
         "visible_basis":"bounded front cutout is visibly open",
         "dimensions":{"length_cm":18}},
        {"part_id":"front-ribbon","kind":"RIBBON","layer":3,
         "placement":"right shoulder","garment_unit":"rich-look",
         "attached_to":"outer-layer",
         "visible_basis":"long visible shoulder ribbon",
         "dimensions":{"length_cm":46,"width_cm":4}},
        {"part_id":"front-bow","kind":"BOW","layer":3,
         "placement":"center chest","garment_unit":"rich-look",
         "attached_to":"front-body",
         "visible_basis":"two bow loops and center knot are visible",
         "dimensions":{"body_length_cm":24,"body_width_cm":8,
                       "knot_length_cm":6,"knot_width_cm":3}},
        {"part_id":"front-rosette","kind":"ROSETTE","layer":3,
         "placement":"left chest","garment_unit":"rich-look",
         "attached_to":"outer-layer",
         "visible_basis":"spiral rosette is visible on the left chest",
         "dimensions":{"strip_length_cm":72,"strip_width_cm":4,
                       "finished_inner_length_cm":18}},
        {"part_id":"front-tie","kind":"TIE","layer":3,
         "placement":"front neckline","garment_unit":"rich-look",
         "attached_to":"front-body",
         "visible_basis":"tapered tie hangs from the visible neckline",
         "dimensions":{"length_cm":35,"top_width_cm":7,"tip_width_cm":2}},
        {"part_id":"cuff-frill","kind":"FRILL","layer":3,
         "placement":"both cuffs","garment_unit":"rich-look",
         "attached_to":"bilateral-sleeves","quantity":2,
         "visible_basis":"repeated gathered frills surround both cuffs",
         "dimensions":{"length_cm":100,"width_cm":6}}
      ]
    }]}
    """#

    @MainActor
    static func expansionFailures() -> [String] {
        var failures: [String] = []
        func require(_ condition: @autoclosure () -> Bool, _ code: String) {
            if !condition() { failures.append(code) }
        }

        guard let parsed = GarmentFactoryReactController.parseVisionProposal(
                richFrontFixture),
              let alternatives = parsed["hypotheses"] as? [[String: Any]],
              alternatives.count == 3 else {
            return ["RICH_FRONT_CANDIDATE_DID_NOT_EXPAND_TO_THREE_REAR_ALTERNATIVES"]
        }

        let expectedVisibleIDs = Set([
            "front-body", "bilateral-sleeves", "outer-layer",
            "asymmetric-layer", "front-cutout", "front-ribbon",
            "front-bow", "front-rosette", "front-tie", "cuff-frill",
        ])
        let expectedModelKinds = Set(["RIBBON", "BOW", "ROSETTE", "TIE", "FRILL"])
        let expectedRearIDs = Set([
            "center-back-opening", "side-opening-closed-back",
            "closed-back-stretch",
        ])

        var visibleFingerprints: [Data] = []
        var rearContracts: Set<String> = []
        for alternative in alternatives {
            guard let structure = alternative["structure"] as? [String: Any],
                  let nodes = structure["nodes"] as? [[String: Any]] else {
                failures.append("EXPANDED_ALTERNATIVE_HAS_NO_STRUCTURE_NODES")
                continue
            }
            let nodeIDs = Set(nodes.compactMap { $0["node_id"] as? String })
            require(nodeIDs == expectedVisibleIDs,
                    "REAR_EXPANSION_REDUCED_OR_REPLACED_VISIBLE_SEMANTIC_NODES")
            require(nodes.count == expectedVisibleIDs.count,
                    "REAR_EXPANSION_CHANGED_VISIBLE_NODE_CARDINALITY")

            let modelKinds = Set(nodes.compactMap { node -> String? in
                let attributes = node["attributes"] as? [String: Any]
                return attributes?["model_kind"] as? String
            })
            require(expectedModelKinds.isSubset(of: modelKinds),
                    "RICH_VISIBLE_ORNAMENT_SEMANTICS_WERE_REDUCED")
            require(nodes.contains {
                $0["node_id"] as? String == "asymmetric-layer" &&
                (($0["attributes"] as? [String: Any])?["side"] as? String) == "left"
            }, "VISIBLE_ASYMMETRY_WAS_REDUCED")
            require(nodes.contains {
                $0["node_id"] as? String == "front-cutout" &&
                $0["kind"] as? String == "OPENING" &&
                (($0["attributes"] as? [String: Any])?["detail_role"] as? String)
                    == "cutout"
            }, "VISIBLE_CUTOUT_WAS_REDUCED")
            require(nodes.contains {
                $0["node_id"] as? String == "bilateral-sleeves" &&
                $0["kind"] as? String == "SLEEVE" &&
                (($0["attributes"] as? [String: Any])?["quantity"] as? Int) == 2
            }, "VISIBLE_SLEEVES_WERE_REDUCED")

            if let fingerprint = visibleSemanticFingerprint(nodes) {
                visibleFingerprints.append(fingerprint)
            } else {
                failures.append("VISIBLE_SEMANTIC_FINGERPRINT_ENCODING_FAILED")
            }

            guard let rearID = alternative["rear_alternative_id"] as? String,
                  let difference = alternative["rear_difference"] as? [String: Any],
                  let closure = difference["closure_detail"] as? [String: Any],
                  let opening = difference["opening_topology"] as? [String: Any]
            else {
                failures.append("REAR_OR_CLOSURE_DIFFERENCE_IS_NOT_TYPED")
                continue
            }
            rearContracts.insert(rearID)
            require(difference["state"] as? String == "PROPOSED" &&
                    difference["not_observed_from_front"] as? Bool == true &&
                    closure["state"] as? String == "PROPOSED" &&
                    closure["not_observed_from_front"] as? Bool == true &&
                    opening["state"] as? String == "PROPOSED",
                    "REAR_DIFFERENCE_ESCAPED_PROPOSED_AUTHORITY")

            // The production expansion copies rear data into node attributes.
            // After removing exactly those fields, every visible semantic node
            // must be byte-for-byte identical across all alternatives.
            for node in nodes {
                let attributes = node["attributes"] as? [String: Any] ?? [:]
                let rearKeys = Set(attributes.keys).intersection([
                    "back_design", "closure_detail", "opening_topology",
                ])
                require(rearKeys.contains("back_design"),
                        "REAR_VARIANT_IS_NOT_BOUND_TO_NODE_STRUCTURE")
                if node["node_id"] as? String == "front-body" {
                    require(rearKeys == Set([
                        "back_design", "closure_detail", "opening_topology",
                    ]), "ANCHOR_DIFFERS_OUTSIDE_REAR_AND_CLOSURE")
                } else {
                    require(rearKeys == Set(["back_design"]),
                            "VISIBLE_NODE_DIFFERS_OUTSIDE_REAR_AND_CLOSURE")
                }
            }
        }

        require(rearContracts == expectedRearIDs,
                "REAR_ALTERNATIVE_SET_IS_INCOMPLETE")
        require(visibleFingerprints.count == 3 &&
                Set(visibleFingerprints).count == 1,
                "REAR_ALTERNATIVES_DO_NOT_PRESERVE_IDENTICAL_VISIBLE_SEMANTICS")
        return failures
    }

    static func previewBoundaryFailures() -> [String] {
        let testFile = URL(fileURLWithPath: #filePath)
        let appRoot = testFile.deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        let controllerURL = appRoot.appendingPathComponent(
            "Sources/Verantyx/Engine/GarmentFactoryReactController.swift")
        guard let source = try? String(contentsOf: controllerURL, encoding: .utf8),
              let body = functionBody(in: source, named: "previewShape") else {
            return ["PREVIEW_SHAPE_SOURCE_UNREADABLE"]
        }

        var failures: [String] = []
        func require(_ condition: @autoclosure () -> Bool, _ code: String) {
            if !condition() { failures.append(code) }
        }
        require(body.contains("visionPipelineArtifacts[candidate.id]") &&
                body.contains("artifacts[\"preview\"]") &&
                body.contains("artifacts[\"flat_pattern\"]") &&
                body.contains("artifacts[\"manufacturing_preview\"]") &&
                body.contains("artifacts[\"sewing_plan\"]"),
                "SUCCESSFUL_PREVIEW_DOES_NOT_REQUIRE_CANDIDATE_SPECIFIC_ARTIFACTS")
        require(body.contains("same_structure_digest") &&
                body.contains("all_downstream_artifacts_bound") &&
                body.contains("structure_digest") &&
                body.contains("image parts IR → deterministic topology → bound 3D + flat pattern"),
                "SUCCESSFUL_PREVIEW_IS_NOT_BOUND_TO_CANDIDATE_STRUCTURE_AND_PATTERN")
        require(!body.contains("garment_structure_preview") &&
                !body.contains("garment_structure_pattern") &&
                !body.contains("selected structure graph → deterministic 3D mesh + flat pieces"),
                "GENERIC_THREE_PIECE_FALLBACK_STILL_ACCEPTED")
        return failures
    }

    @MainActor
    static func failures() -> [String] {
        expansionFailures() + previewBoundaryFailures()
    }

    private static func visibleSemanticFingerprint(_ nodes: [[String: Any]]) -> Data? {
        let visible = nodes.sorted {
            ($0["node_id"] as? String ?? "") < ($1["node_id"] as? String ?? "")
        }.map { node -> [String: Any] in
            var copy = node
            var attributes = copy["attributes"] as? [String: Any] ?? [:]
            attributes.removeValue(forKey: "back_design")
            attributes.removeValue(forKey: "closure_detail")
            attributes.removeValue(forKey: "opening_topology")
            copy["attributes"] = attributes
            return copy
        }
        guard JSONSerialization.isValidJSONObject(visible) else { return nil }
        return try? JSONSerialization.data(withJSONObject: visible,
                                            options: [.sortedKeys])
    }

    private static func functionBody(in source: String, named name: String) -> String? {
        guard let signature = source.range(of: "func \(name)("),
              let open = source[signature.upperBound...].firstIndex(of: "{") else {
            return nil
        }
        var depth = 0
        var cursor = open
        var quoted = false
        var escaped = false
        while cursor < source.endIndex {
            let character = source[cursor]
            if quoted {
                if escaped { escaped = false }
                else if character == "\\" { escaped = true }
                else if character == "\"" { quoted = false }
            } else if character == "\"" {
                quoted = true
            } else if character == "{" {
                depth += 1
            } else if character == "}" {
                depth -= 1
                if depth == 0 { return String(source[open...cursor]) }
            }
            cursor = source.index(after: cursor)
        }
        return nil
    }
}

#if !GARMENT_FRONT_IMAGE_CANDIDATE_PIPELINE_STANDALONE
final class GarmentFrontImageCandidatePipelineAuditTests: XCTestCase {
    @MainActor
    func testRichVisibleFrontSurvivesRearExpansion() {
        XCTAssertEqual(
            GarmentFrontImageCandidatePipelineAudit.expansionFailures(), [])
    }

    func testCandidatePreviewRejectsGenericThreePieceFallback() {
        XCTAssertEqual(
            GarmentFrontImageCandidatePipelineAudit.previewBoundaryFailures(), [])
    }
}
#else

// Minimal app-boundary stubs used only while compiling the production
// controller into this standalone audit executable.
@MainActor
final class MCPEngine {
    static let shared = MCPEngine()
    func callTool(serverName: String, toolName: String,
                  arguments: [String: Any]) async -> String { "{}" }
}

@MainActor
final class GarmentGenerationJob {
    static let shared = GarmentGenerationJob()
    let jobID = "standalone-front-image-candidate-audit"
}

enum AtelierAnalyst {
    enum Pick {
        case vera
        case ollama(String)
        case jgen(String)
        case lmStudio(String)
        case cloud(String, String)
    }
}

@MainActor
final class OllamaClient {
    static let shared = OllamaClient()
    func generate(model: String, prompt: String, maxTokens: Int,
                  temperature: Double) async -> String? { nil }
    func generateConversation(model: String, messages: [(String, String)],
                              imagesForLastUserMessage: [String],
                              allowImageFallback: Bool, maxTokens: Int,
                              temperature: Double) async -> String? { nil }
}

actor JCrossChatManager {
    static let shared = JCrossChatManager()
    var loadedModelName: String? { nil }
    func load(modelFileName: String) async throws {}
    func generate(conversation: [(String, String)], maxTokens: Int,
                  keepThinking: Bool) async throws -> String { "" }
}

@MainActor
final class LMStudioClient {
    static let shared = LMStudioClient()
    func generateCompleteConversation(
        model: String, messages: [(String, String)], maxTokens: Int,
        temperature: Double, responseFormat: [String: Any]? = nil
    ) async -> String? { nil }
    func generateWithImage(model: String, systemPrompt: String,
                           userText: String, imageBase64: String,
                           mimeType: String, temperature: Double,
                           maxTokens: Int) async -> String? { nil }
}

private enum StandaloneCloudError: Error { case unavailable }

@MainActor
final class CloudAPIClient {
    static let shared = CloudAPIClient()
    func send(systemPrompt: String, userMessage: String,
              imageBase64: String? = nil, provider: String,
              modelOverride: String) async -> Result<String, Error> {
        .failure(StandaloneCloudError.unavailable)
    }
}

@main
private enum GarmentFrontImageCandidatePipelineAuditMain {
    @MainActor
    static func main() {
        let expansionFailures =
            GarmentFrontImageCandidatePipelineAudit.expansionFailures()
        let previewFailures =
            GarmentFrontImageCandidatePipelineAudit.previewBoundaryFailures()
        if expansionFailures.isEmpty {
            print("PASS rich visible-front semantics survive all rear alternatives")
        } else {
            expansionFailures.forEach { print("FAIL \($0)") }
        }
        if previewFailures.isEmpty {
            print("PASS candidate preview requires bound 3D and flat pattern")
        } else {
            previewFailures.forEach { print("FAIL \($0)") }
        }
        let failures = expansionFailures + previewFailures
        if failures.isEmpty {
            print("PASS front-image candidate preservation and bound-preview audit")
            exit(0)
        }
        exit(1)
    }
}
#endif
