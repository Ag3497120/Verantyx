import Foundation

#if !ATELIER_BEGINNER_UI_STANDALONE
import XCTest
@testable import Verantyx
#endif

/// Static boundary audit for the beginner garment chat surface.
///
/// The view may render public factory/job/intake state and request explicit
/// user actions. It must not call MCP directly, synthesize factory events, or
/// turn attaching/sending a photo into an implicit candidate approval.
private enum AtelierBeginnerFactoryUIAudit {
    struct Report { var failures: [String] = [] }

    static func run() -> Report {
        var report = Report()
        let testFile = URL(fileURLWithPath: #filePath)
        let appRoot = testFile.deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let viewsRoot = appRoot.appendingPathComponent("Sources/Verantyx/Views")
        let engineRoot = appRoot.appendingPathComponent("Sources/Verantyx/Engine")
        guard let chatPaneRaw = read("AtelierChatPaneView.swift", from: viewsRoot),
              let dynamicRaw = read("AtelierDynamicFlowView.swift", from: viewsRoot),
              let agentChatRaw = read("AgentChatView.swift", from: viewsRoot),
              let shellRaw = read("IDEShellView.swift", from: viewsRoot),
              let shellLayoutRaw = read("ShellLayoutState.swift", from: engineRoot)
        else {
            report.failures.append("BEGINNER_OR_EXPERT_UI_SOURCE_UNREADABLE")
            return report
        }
        let source = executableSource(chatPaneRaw)
        let dynamic = executableSource(dynamicRaw)
        let agentChat = executableSource(agentChatRaw)
        let shell = executableSource(shellRaw)
        let shellLayout = executableSource(shellLayoutRaw)

        require(agentChat.contains("VStack(spacing: 0)") &&
                agentChat.contains("ChatTranscriptView(messages: visibleMessages") &&
                agentChat.contains("AtelierBeginnerContextCardsView()") &&
                agentChat.contains(".layoutPriority(1)") &&
                agentChat.contains("if app.veraEngineMode == .atelier") &&
                !agentChat.contains(".padding(.bottom, 18)"),
                "DYNAMIC_CARD_NOT_EMBEDDED_IN_BEGINNER_CHAT", into: &report)
        if let transcript = agentChat.range(
                of: "ChatTranscriptView(messages: visibleMessages"),
           let card = agentChat.range(of: "AtelierBeginnerContextCardsView()") {
            require(transcript.lowerBound < card.lowerBound,
                    "DYNAMIC_CARD_IS_NOT_AFTER_CHAT_TRANSCRIPT", into: &report)
        } else {
            report.failures.append("DYNAMIC_CARD_ORDER_UNAUDITABLE")
        }
        require(dynamic.contains("struct AtelierBeginnerContextCardsView") &&
                dynamic.contains("generationWaitingCard") &&
                dynamic.contains("AtelierInlineGenerationField") &&
                dynamic.contains("atelier.inline-generation-waiting") &&
                dynamic.contains("inlineArtifactResults") &&
                dynamic.contains("atelier.inline-generated-artifacts") &&
                dynamic.contains("inlineHumanActionCard") &&
                dynamic.contains("3D・型紙・縫製成果物はまだ完成していません") &&
                dynamic.contains("detailsDisclosure") &&
                dynamic.contains("atelier.inline-progressive-details") &&
                dynamic.contains("onChange(of: revision)") &&
                !dynamic.contains("@State private var collapsed") &&
                !dynamic.contains("inlineCardHeader") &&
                !dynamic.contains("atelier.inline-context-card") &&
                !dynamic.contains(".background(.ultraThinMaterial") &&
                !dynamic.contains(".shadow(color: .black.opacity(0.42)"),
                "BEGINNER_RESULTS_ARE_NOT_INLINE_PROGRESSIVE_OR_CONTEXTUAL", into: &report)
        for page in ["case progress", "case threeD", "case pattern",
                     "case manufacturing", "case choices", "case change"] {
            require(dynamic.contains(page),
                    "BEGINNER_DYNAMIC_PAGE_MISSING_\(page)", into: &report)
        }
        require(dynamic.contains("FactoryProposedDressedSceneView") &&
                dynamic.contains("FactoryFlatPatternPreview") &&
                dynamic.contains("AtelierDynamicFlowView()"),
                "BEGINNER_WINDOW_DOES_NOT_RENDER_REAL_EXPERT_ARTIFACTS", into: &report)
        require(dynamic.contains("GarmentFactoryReactController.shared") &&
                dynamic.contains("GarmentGenerationJob.shared") &&
                dynamic.contains("AtelierContext.shared"),
                "BEGINNER_AND_EXPERT_STATE_ARE_NOT_SHARED", into: &report)
        require(dynamic.contains("3Dで見る") &&
                dynamic.contains("factory.previewShape(candidate)") &&
                dynamic.contains("この案を採用") &&
                dynamic.contains("page = .threeD") &&
                dynamic.contains("approveFactoryCandidate"),
                "CANDIDATE_PREVIEW_AND_HUMAN_APPROVAL_ARE_NOT_SEPARATE",
                into: &report)
        require(dynamic.contains("manufacturing_preview") &&
                dynamic.contains("topology_sewing_plan") &&
                dynamic.contains("findPatternPayload") &&
                dynamic.contains("job.activeSnapshot.resultJSON"),
                "MANUFACTURING_RESULT_IS_NOT_READ_SAFELY_FROM_PATTERN",
                into: &report)
        for label in ["裁ち線 / 縫い線", "裁断枚数 cut_count", "合印",
                      "地の目", "縫製順序", "残っている確認", "提出用ファイル"] {
            require(dynamic.contains(label),
                    "MANUFACTURING_CARD_MISSING_\(label)", into: &report)
        }
        require(dynamic.contains("DisclosureGroup(isExpanded:") &&
                dynamic.contains("expandedManufacturingCards"),
                "MANUFACTURING_CARDS_ARE_NOT_CLICKABLE", into: &report)
        require(dynamic.contains("expandedFailureDiagnostics") &&
                dynamic.contains("initializedFailureDiagnostics") &&
                dynamic.contains("typedFailureDisclosure") &&
                dynamic.contains("typedFailureDiagnostics") &&
                dynamic.contains("failureDiagnosticContexts") &&
                dynamic.contains("DisclosureGroup(isExpanded: Binding(") &&
                dynamic.contains("initializedFailureDiagnostics.insert(id).inserted") &&
                dynamic.contains("expandedFailureDiagnostics.insert(id)"),
                "TYPED_FAILURE_DETAILS_ARE_NOT_EXPANDABLE", into: &report)
        for detailKey in ["candidate_id", "garment_unit", "layer",
                          "leg_node_ids", "gusset_node_ids",
                          "orphan_gusset_node_ids", "missing_",
                          "how_to_close", "engine_result"] {
            require(dynamic.contains("\"\(detailKey)\""),
                    "TYPED_FAILURE_DETAIL_MISSING_\(detailKey)", into: &report)
        }
        require(dynamic.contains("未観測値を確定しません") &&
                dynamic.contains("REVIEW") &&
                dynamic.contains("PROPOSED") &&
                dynamic.contains("UNKNOWN_ENGINE_FAILURE"),
                "TYPED_FAILURE_TRUTH_LABELS_ARE_NOT_PRESERVED", into: &report)
        require(dynamic.contains(
                    "atelier.beginner.dynamic.typed-failure-diagnostic"),
                "TYPED_FAILURE_DIAGNOSTIC_IS_NOT_ACCESSIBLE", into: &report)
        require(dynamic.contains("export_package") &&
                dynamic.contains("export_verification") &&
                dynamic.contains("checkmark.shield") &&
                dynamic.contains(".disabled(!details.exportVerified)") &&
                dynamic.contains("selectedExportArtifact") &&
                dynamic.contains("exportArtifactSheet") &&
                dynamic.contains("NSSavePanel") &&
                dynamic.contains("Data(base64Encoded:"),
                "EXPORT_PACKAGE_IS_NOT_CLICKABLE_OR_BYTE_PRESERVING",
                into: &report)
        require(dynamic.contains("製造プレビューがまだ無いため、既存の平面型紙を表示しています") &&
                dynamic.contains("FactoryFlatPatternPreview"),
                "MISSING_MANUFACTURING_PREVIEW_HAS_NO_PATTERN_FALLBACK",
                into: &report)
        require(dynamic.contains("工業認証・強度・安全性・適合性の保証ではありません") &&
                !dynamic.contains("工業認証済み"),
                "MANUFACTURING_PREVIEW_MISREPRESENTS_CERTIFICATION",
                into: &report)
        require(shell.contains("activeTabUsesChatFirstCanvas") &&
                shell.contains("app.veraEngineMode == .atelier && kind == .garment") &&
                shell.contains("case .garment:") &&
                shell.contains("beginnerChatCanvas") &&
                !shell.contains("AtelierWorkbenchSplitView()") &&
                !shell.contains("atelierModePicker") &&
                !shell.contains("atelierShowOverview"),
                "ATELIER_STILL_HAS_SEPARATE_BEGINNER_EXPERT_SURFACES", into: &report)
        require(agentChat.contains("AtelierBeginnerContextCardsView()") &&
                dynamic.contains("Advanced Inspector") &&
                dynamic.contains("AtelierView()") &&
                dynamic.contains("atelier.inline-advanced-direct-tools"),
                "CHAT_FIRST_ATELIER_LOST_PROGRESSIVE_ADVANCED_TOOLS", into: &report)
        require(shellLayout.contains("case .agentActivity: return false") &&
                shellLayout.contains("guard case .panel(let kind) = tab.kind") &&
                shellLayout.contains("return kind.surfaced") &&
                !shell.contains("requestMount(.agentActivity"),
                "AGENT_ACTIVITY_IS_STILL_A_VISIBLE_OR_RESTORABLE_PANE", into: &report)

        guard let composerRaw = read("UnifiedComposerView.swift", from: viewsRoot)
        else {
            report.failures.append("UNIFIED_COMPOSER_SOURCE_UNREADABLE")
            return report
        }
        let composer = executableSource(composerRaw)
        require(composer.contains("private var attachmentControl") &&
                composer.contains("Attach garment image") &&
                composer.contains("if app.veraEngineMode == .atelier"),
                "ATELIER_ATTACHMENT_IS_NOT_A_SINGLE_DIRECT_DOOR", into: &report)
        require(composer.contains("await intake.ingest(url)") &&
                composer.contains("intake.hasComposerAttachment") &&
                composer.contains("hasComposerAttachments"),
                "ATELIER_DROP_OR_SEND_DOES_NOT_SHARE_INTAKE_STATE", into: &report)
        require(composer.contains("if app.veraEngineMode == .atelier") &&
                composer.contains("app.shell.openTab(.garment)"),
                "ATELIER_SEND_LEAVES_THE_UNIFIED_PROJECT_SURFACE", into: &report)

        require(source.contains("AtelierIntake.shared") &&
                source.contains("pickAndIngest()") &&
                source.contains("selectedClip"),
                "PHOTO_ATTACHMENT_PATH_MISSING", into: &report)
        require(source.contains("この服を作って") &&
                source.contains("写真を添付"),
                "BEGINNER_PHOTO_PROMPT_MISSING", into: &report)

        require(source.contains("factory.trace") &&
                source.contains("制作ログとリトライ"),
                "REACT_TRACE_CARD_MISSING", into: &report)
        require(source.contains("AI推測") &&
                source.contains("PROPOSED") &&
                source.contains("観測事実ではありません"),
                "INFERENCE_PROVENANCE_NOT_VISIBLE", into: &report)
        require(source.contains("candidate.digest") &&
                source.contains("この推測を人が採用する"),
                "EXPLICIT_DIGEST_APPROVAL_CARD_MISSING", into: &report)

        require(source.contains("openArtifact(step: \"Solid\"") &&
                source.contains("openArtifact(step: \"Pattern\"") &&
                source.contains("AtelierNavigator.shared.go(to: step)"),
                "THREE_D_PATTERN_ROUTES_MISSING", into: &report)
        require(source.contains("GarmentSimulationPreview("),
                "THREE_D_PREVIEW_WAS_REMOVED", into: &report)
        require(source.contains("factory.previewArtifact") &&
                source.contains("factory.previewAttempts") &&
                source.contains("factoryArtifactPreview(artifact)"),
                "PROPOSED_PREVIEW_ARTIFACT_NOT_RENDERED", into: &report)
        require(source.contains("FactoryProposedDressedSceneView") &&
                source.contains("artifact.edges") &&
                source.contains("FactoryFlatPatternPreview") &&
                source.contains("artifact.pieces"),
                "PROPOSED_THREE_D_OR_PATTERN_VIEW_MISSING", into: &report)
        require(source.contains("if factory.previewArtifact != nil { return true }") ||
                source.contains("if let artifact = factory.previewArtifact"),
                "PREVIEW_ARTIFACT_DOES_NOT_ENABLE_OUTPUT", into: &report)
        if let preview = source.range(of: "factoryArtifactPreview(artifact)"),
           let candidates = source.range(of: "factoryCandidateCard(factory.shapeCandidates") {
            require(preview.lowerBound < candidates.lowerBound,
                    "PROPOSED_PREVIEW_IS_HIDDEN_BEHIND_APPROVAL", into: &report)
        } else {
            report.failures.append("PREVIEW_CANDIDATE_ORDER_UNAUDITABLE")
        }
        require(source.contains(".frame(maxWidth: 320)"),
                "COMPOSER_WIDTH_NOT_BOUNDED", into: &report)

        for forbidden in ["MCPEngine.shared", "toolName: \"garment_factory\"",
                          "SUBMIT_HYPOTHESES", "APPROVE_HYPOTHESIS",
                          "APPROVE_MATERIAL"] {
            require(!source.contains(forbidden),
                    "VIEW_BYPASSES_CONTROLLER_\(forbidden)", into: &report)
            require(!dynamic.contains(forbidden),
                    "DYNAMIC_WINDOW_BYPASSES_CONTROLLER_\(forbidden)", into: &report)
        }
        for name in ["send", "attachPhoto"] {
            guard let body = functionBody(in: source, named: name) else {
                report.failures.append("FUNCTION_\(name.uppercased())_MISSING")
                continue
            }
            require(!body.contains("approveFactoryCandidate"),
                    "\(name.uppercased())_AUTO_APPROVES_CANDIDATE", into: &report)
        }
        require(source.contains("Button(app.t(\"Adopt\", \"この案を採用\"))") &&
                source.contains("approveFactoryCandidate(candidate, material: material)"),
                "CANDIDATE_APPROVAL_NOT_BOUND_TO_EXPLICIT_BUTTON", into: &report)
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
        guard let signature = source.range(of: "func \(name)("),
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

    private static func require(_ condition: @autoclosure () -> Bool,
                                _ failure: String,
                                into report: inout Report) {
        if !condition() { report.failures.append(failure) }
    }
}

#if !ATELIER_BEGINNER_UI_STANDALONE
final class AtelierBeginnerFactoryUIAuditTests: XCTestCase {
    func testBeginnerFactoryUIBoundaries() {
        XCTAssertEqual(AtelierBeginnerFactoryUIAudit.run().failures, [])
    }
}
#else
@main
private enum AtelierBeginnerFactoryUIAuditMain {
    static func main() {
        let failures = AtelierBeginnerFactoryUIAudit.run().failures
        if failures.isEmpty {
            print("PASS beginner garment chat UI invariants")
        } else {
            failures.forEach { print("FAIL \($0)") }
            exit(1)
        }
    }
}
#endif
