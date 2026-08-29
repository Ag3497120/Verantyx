import Foundation
import AppKit
import SwiftUI

/// Beginner-mode cards derived only from the current deterministic garment job.
///
/// This view deliberately has no general chat, progress dashboard, or guessed
/// next action. It renders only evidence-backed candidates for the effective
/// job stage, a pending preview's approval/rejection gate, and a compensating
/// Undo when the append-only job says one exists.
@MainActor
struct AtelierDynamicFlowView: View {
    @StateObject private var job = GarmentGenerationJob.shared
    @State private var actionInFlight: ActionKind?
    @State private var feedback: Feedback?

    private enum ActionKind: String {
        case approve
        case reject
        case undo
    }

    private struct Feedback: Equatable {
        let text: String
        let isRefusal: Bool
    }

    struct Candidate: Identifiable, Equatable {
        let id: String
        let title: String
        let detail: String?
        let status: String?
        let digest: String?
    }

    private struct CandidateSection: Equatable {
        let title: String
        let evidenceKeys: [String]
    }

    var body: some View {
        let candidates = currentCandidates

        Group {
            if candidates.isEmpty,
               job.pendingPreview == nil,
               !job.canUndo,
               feedback == nil {
                EmptyView()
            } else {
                VStack(alignment: .leading, spacing: 10) {
                    if !candidates.isEmpty {
                        candidateCard(candidates)
                    }
                    if let preview = job.pendingPreview {
                        decisionCard(preview)
                    }
                    if job.canUndo {
                        undoCard
                    }
                    if let feedback {
                        feedbackCard(feedback)
                    }
                }
                .padding(10)
                .background(Theme.panel)
                .accessibilityElement(children: .contain)
                .accessibilityLabel("服作りの現在の選択肢")
            }
        }
        .animation(.easeInOut(duration: 0.16), value: job.pendingPreview?.digest)
        .animation(.easeInOut(duration: 0.16), value: job.canUndo)
        .animation(.easeInOut(duration: 0.16), value: candidates)
    }

    // MARK: - Stage-filtered candidates

    private var effectiveState: GarmentGenerationJob.State? {
        job.pendingPreview?.after.state ?? job.activeSnapshot.state
    }

    private var candidateSection: CandidateSection? {
        switch effectiveState {
        case .imageReceived:
            return CandidateSection(
                title: "服として扱う範囲の候補",
                evidenceKeys: ["region_candidates", "proposed_regions", "regions"])
        case .regionsConfirmed, .geometryContested:
            return CandidateSection(
                title: "形状の候補",
                evidenceKeys: ["geometry_candidates", "silhouette_candidates", "shape_candidates", "candidates"])
        case .backCandidatesReady:
            return CandidateSection(
                title: "背面構造の候補",
                evidenceKeys: ["back_candidates", "back_structure_candidates", "rear_candidates", "candidates"])
        case .structureApproved, .materialContested:
            return CandidateSection(
                title: "素材の候補",
                evidenceKeys: ["material_candidates", "fabric_candidates", "drape_candidates", "candidates"])
        case .simulationReady:
            return CandidateSection(
                title: "着用形状の候補",
                evidenceKeys: ["simulation_candidates", "shape_candidates", "fit_candidates", "candidates"])
        case .shapeApproved, .patternValidated:
            return CandidateSection(
                title: "型紙構成の候補",
                evidenceKeys: ["pattern_candidates", "transform_candidates", "construction_candidates", "candidates"])
        case .sewingBlockedNoCorpus:
            return CandidateSection(
                title: "確認できる縫製候補",
                evidenceKeys: ["sewing_candidates", "construction_candidates"])
        case .complete, .none:
            return nil
        }
    }

    private var currentCandidates: [Candidate] {
        guard let section = candidateSection else { return [] }
        let sources = [job.pendingPreview?.after.resultJSON,
                       job.activeSnapshot.resultJSON].compactMap { $0 }
        for source in sources {
            guard let root = Self.dictionary(from: source),
                  let raw = Self.firstValue(for: section.evidenceKeys, in: root)
            else { continue }
            let candidates = Self.candidates(from: raw)
            if !candidates.isEmpty { return Array(candidates.prefix(8)) }
        }
        return []
    }

    private func candidateCard(_ candidates: [Candidate]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: "square.stack.3d.up")
                    .foregroundStyle(Theme.sel)
                Text(candidateSection?.title ?? "候補")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Theme.fg)
                Spacer()
                Text("\(candidates.count)件")
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(Theme.faint)
            }

            ForEach(candidates) { candidate in
                VStack(alignment: .leading, spacing: 4) {
                    HStack(alignment: .firstTextBaseline, spacing: 6) {
                        Text(candidate.title)
                            .font(.system(size: 11, weight: .medium))
                            .foregroundStyle(Theme.fg)
                            .fixedSize(horizontal: false, vertical: true)
                        Spacer(minLength: 6)
                        if let status = candidate.status {
                            Text(Self.displayStatus(status))
                                .font(.system(size: 8.5, weight: .semibold))
                                .foregroundStyle(status.uppercased() == "PROPOSED" ? Theme.warn : Theme.dim)
                        }
                    }
                    if let detail = candidate.detail {
                        Text(detail)
                            .font(.system(size: 9.5))
                            .foregroundStyle(Theme.dim)
                            .fixedSize(horizontal: false, vertical: true)
                            .lineLimit(4)
                    }
                    if let digest = candidate.digest {
                        Text("digest \(digest.prefix(16))")
                            .font(.system(size: 8, design: .monospaced))
                            .foregroundStyle(Theme.faint)
                            .textSelection(.enabled)
                    }
                }
                .padding(8)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Theme.panel2, in: RoundedRectangle(cornerRadius: 8))
                .accessibilityElement(children: .combine)
            }
        }
        .cardSurface()
    }

    // MARK: - Human decision gate

    private func decisionCard(_ preview: GarmentPreview) -> some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack(spacing: 6) {
                Image(systemName: "person.crop.circle.badge.questionmark")
                    .foregroundStyle(Theme.warn)
                Text("この変更を反映しますか？")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Theme.fg)
                Spacer()
                Text(String(preview.digest.prefix(12)))
                    .font(.system(size: 8, design: .monospaced))
                    .foregroundStyle(Theme.faint)
                    .textSelection(.enabled)
            }

            if preview.before.mesh != nil || preview.after.mesh != nil {
                GarmentSimulationPreview(before: preview.before.mesh,
                                         after: preview.after.mesh)
                    .frame(minHeight: 150, idealHeight: 210, maxHeight: 260)
            }

            if !preview.changedAddresses.isEmpty {
                VStack(alignment: .leading, spacing: 3) {
                    Text("変わる場所")
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundStyle(Theme.dim)
                    Text(preview.changedAddresses.joined(separator: " ・ "))
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(Theme.faint)
                        .lineLimit(4)
                }
            }

            HStack(spacing: 8) {
                Button {
                    perform(.approve, digest: preview.digest)
                } label: {
                    actionLabel("承認して反映", icon: "checkmark.circle.fill",
                                action: .approve)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .disabled(actionInFlight != nil)

                Button(role: .cancel) {
                    perform(.reject, digest: preview.digest)
                } label: {
                    actionLabel("却下", icon: "xmark.circle", action: .reject)
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .disabled(actionInFlight != nil)
            }
        }
        .cardSurface(border: Theme.warn.opacity(0.45))
    }

    private var undoCard: some View {
        HStack(alignment: .center, spacing: 10) {
            Image(systemName: "arrow.uturn.backward.circle")
                .font(.system(size: 18))
                .foregroundStyle(Theme.sel)
            VStack(alignment: .leading, spacing: 2) {
                Text("直前の承認を取り消せます")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(Theme.fg)
                Text("新しい変更を作らず、承認済み状態を一つ前へ戻します。")
                    .font(.system(size: 9.5))
                    .foregroundStyle(Theme.dim)
            }
            Spacer(minLength: 8)
            Button {
                perform(.undo, digest: nil)
            } label: {
                actionLabel("Undo", icon: "arrow.uturn.backward", action: .undo)
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            .disabled(actionInFlight != nil)
        }
        .cardSurface()
    }

    private func actionLabel(_ title: String, icon: String,
                             action: ActionKind) -> some View {
        HStack(spacing: 5) {
            if actionInFlight == action {
                ProgressView().controlSize(.small)
            } else {
                Image(systemName: icon)
            }
            Text(title)
        }
    }

    private func feedbackCard(_ feedback: Feedback) -> some View {
        HStack(alignment: .top, spacing: 7) {
            Image(systemName: feedback.isRefusal ? "exclamationmark.triangle" : "checkmark.circle")
            Text(feedback.text)
                .font(.system(size: 10))
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
            Button {
                self.feedback = nil
            } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 8, weight: .bold))
            }
            .buttonStyle(.plain)
            .accessibilityLabel("メッセージを閉じる")
        }
        .foregroundStyle(feedback.isRefusal ? Theme.warn : Theme.ok)
        .cardSurface(border: (feedback.isRefusal ? Theme.warn : Theme.ok).opacity(0.35))
    }

    private func perform(_ action: ActionKind, digest: String?) {
        guard actionInFlight == nil else { return }
        actionInFlight = action
        feedback = nil
        Task { @MainActor in
            let resolution: AtelierChatRouter.Resolution
            switch action {
            case .approve:
                guard let digest else {
                    actionInFlight = nil
                    feedback = Feedback(text: "承認対象のdigestがありません。", isRefusal: true)
                    return
                }
                resolution = await AtelierChatRouter.approvePending(digest: digest)
            case .reject:
                guard let digest else {
                    actionInFlight = nil
                    feedback = Feedback(text: "却下対象のdigestがありません。", isRefusal: true)
                    return
                }
                resolution = await AtelierChatRouter.rejectPending(digest: digest)
            case .undo:
                resolution = await AtelierChatRouter.undoLast()
            }
            actionInFlight = nil
            feedback = Self.feedback(for: resolution, action: action)
        }
    }

    private static func feedback(for resolution: AtelierChatRouter.Resolution,
                                 action: ActionKind) -> Feedback {
        switch resolution {
        case .modelGenerated:
            return Feedback(text: AtelierChatRouter.transcriptText(for: resolution),
                            isRefusal: false)
        case .answered(let answer, _):
            return Feedback(text: answer.deterministicText, isRefusal: answer.verdict != "ANSWER")
        case .refused(let reason):
            return Feedback(text: reason, isRefusal: true)
        case .preview:
            return Feedback(text: "新しいプレビューが作成されました。", isRefusal: false)
        case .moved:
            return Feedback(text: "表示工程を移動しました。", isRefusal: false)
        case .factory(let report, _):
            return Feedback(text: "\(report.verdict)\n\(report.message)",
                            isRefusal: report.verdict.hasPrefix("UNKNOWN_")
                                || report.verdict.hasPrefix("ESCALATE_"))
        case .none:
            let label: String
            switch action {
            case .approve: label = "承認"
            case .reject: label = "却下"
            case .undo: label = "Undo"
            }
            return Feedback(text: "\(label)の確定結果を取得できませんでした。", isRefusal: true)
        }
    }

    // MARK: - Deterministic candidate extraction

    private static func dictionary(from json: String) -> [String: Any]? {
        guard let data = json.data(using: .utf8),
              let object = try? JSONSerialization.jsonObject(with: data),
              let dictionary = object as? [String: Any]
        else { return nil }
        return dictionary
    }

    private static func firstValue(for keys: [String],
                                   in root: [String: Any]) -> Any? {
        let wanted = Set(keys)
        var queue: [[String: Any]] = [root]
        var cursor = 0
        while cursor < queue.count {
            let dictionary = queue[cursor]
            cursor += 1
            for key in keys where dictionary[key] != nil {
                return dictionary[key]
            }
            for key in dictionary.keys.sorted() {
                if wanted.contains(key) { continue }
                if let child = dictionary[key] as? [String: Any] {
                    queue.append(child)
                } else if let children = dictionary[key] as? [[String: Any]] {
                    queue.append(contentsOf: children)
                }
            }
        }
        return nil
    }

    private static func candidates(from raw: Any) -> [Candidate] {
        if let rows = raw as? [Any] {
            return rows.enumerated().compactMap { candidate(from: $0.element,
                                                             fallbackID: "candidate-\($0.offset)") }
        }
        if let dictionary = raw as? [String: Any] {
            if looksLikeCandidate(dictionary),
               let item = candidate(from: dictionary, fallbackID: "candidate-0") {
                return [item]
            }
            return dictionary.keys.sorted().enumerated().compactMap { offset, key in
                candidate(from: dictionary[key] as Any,
                          fallbackID: key.isEmpty ? "candidate-\(offset)" : key,
                          fallbackTitle: key)
            }
        }
        return candidate(from: raw, fallbackID: "candidate-0").map { [$0] } ?? []
    }

    private static func candidate(from raw: Any, fallbackID: String,
                                  fallbackTitle: String? = nil) -> Candidate? {
        if let text = raw as? String, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return Candidate(id: fallbackID, title: fallbackTitle ?? text,
                             detail: fallbackTitle == nil ? nil : text,
                             status: nil, digest: nil)
        }
        guard let dictionary = raw as? [String: Any] else { return nil }
        let title = string(in: dictionary,
                           keys: ["title", "label", "name", "candidate_id", "id"])
            ?? fallbackTitle ?? fallbackID
        let detail = string(in: dictionary,
                            keys: ["summary", "description", "rationale", "reason", "assumption"])
        let status = string(in: dictionary, keys: ["status", "verdict", "state"])
        let digest = string(in: dictionary,
                            keys: ["digest", "evidence_digest", "artifact_digest"])
        let explicitID = string(in: dictionary, keys: ["candidate_id", "id", "digest"])
        return Candidate(id: explicitID ?? fallbackID, title: title,
                         detail: detail, status: status, digest: digest)
    }

    private static func looksLikeCandidate(_ dictionary: [String: Any]) -> Bool {
        !Set(dictionary.keys).isDisjoint(with: [
            "title", "label", "name", "candidate_id", "summary", "description",
            "rationale", "status", "digest"
        ])
    }

    private static func string(in dictionary: [String: Any],
                               keys: [String]) -> String? {
        for key in keys {
            if let value = dictionary[key] as? String,
               !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                return value
            }
            if let value = dictionary[key] as? NSNumber {
                return value.stringValue
            }
        }
        return nil
    }

    private static func displayStatus(_ status: String) -> String {
        switch status.uppercased() {
        case "PROPOSED": return "候補"
        case "OBSERVED": return "確認済み"
        case "APPROVED": return "承認済み"
        default: return status
        }
    }
}

/// Chat-first projection of the one Atelier state. Progressive disclosure is
/// expressed as pages (3D, pattern, manufacturing, Advanced), not as a second
/// beginner/expert garment model. Every value is read from the same job,
/// factory controller and Atelier context.
@MainActor
struct AtelierBeginnerContextCardsView: View {
    @EnvironmentObject private var app: AppState
    @ObservedObject private var factory = GarmentFactoryReactController.shared
    @ObservedObject private var job = GarmentGenerationJob.shared
    @ObservedObject private var context = AtelierContext.shared
    @State private var selecting: String?
    @State private var undoingFactoryDecision = false
    @State private var previewingCandidate: String?
    @State private var feedback = ""
    @State private var page: Page = .progress
    // 会話に新しい作業が届いた時は、まず一行の選択カードとして見せる。
    // ユーザーが選んだ時だけ同じ場所で展開し、会話や入力欄を覆わない。
    @State private var collapsed = true
    @State private var dismissedRevision = ""
    @State private var expandedManufacturingCards: Set<String> = []
    @State private var expandedFailureDiagnostics: Set<String> = []
    @State private var initializedFailureDiagnostics: Set<String> = []
    @State private var directInspectorExpanded = false
    @State private var selectedExportArtifact: ExportArtifact?
    @State private var targetSculptTool: TargetSculptTool = .orbit
    @State private var targetSculptBrushRings = 2.0
    @FocusState private var candidateControlFocus: CandidateControlFocus?

    private enum CandidateControlAction: String, Hashable {
        case preview
        case adopt
        case reject
    }

    private struct CandidateControlFocus: Hashable {
        let domain: String
        let candidateID: String
        let action: CandidateControlAction
    }

    private enum Page: String, CaseIterable, Identifiable {
        case progress = "工程"
        case threeD = "3D"
        case pattern = "型紙"
        case manufacturing = "製造"
        case choices = "候補"
        case change = "変更"
        case advanced = "Advanced"
        var id: String { rawValue }
    }

    private struct ManufacturingPiece: Identifiable, Equatable {
        let id: String
        let cutCount: Int?
        let sewPointCount: Int?
        let cutPointCount: Int?
        let notchCount: Int
        let layer: Int?
        let role: String?
    }

    private struct GrainRecord: Identifiable, Equatable {
        let id: String
        let angle: String
        let state: String
        let orientation: String?
    }

    private struct SewingStep: Identifiable, Equatable {
        let id: String
        let number: Int?
        let action: String
        let pieces: [String]
        let dependencies: [String]
        let quantity: Int?
    }

    private struct ManufacturingDetails: Equatable {
        let digest: String
        let candidateState: String
        let previewReady: Bool
        let manufacturingReady: Bool
        let pieces: [ManufacturingPiece]
        let grains: [GrainRecord]
        let steps: [SewingStep]
        let gates: [String]
        let exports: [ExportArtifact]
        let exportVerified: Bool
        let exportVerificationScope: String
    }

    private struct ExportArtifact: Identifiable, Equatable {
        let id: String
        let representation: String
        let text: String?
        let base64: String?
        let byteCount: Int
    }

    private struct FailureDiagnosticField: Identifiable, Equatable {
        let id: String
        let label: String
        let value: String
    }

    private struct TypedFailureDiagnostic: Identifiable, Equatable {
        let id: String
        let code: String
        let state: String
        let authority: String?
        let fields: [FailureDiagnosticField]
    }

    private var hasFactoryContext: Bool {
        factory.lastReport != nil || factory.previewArtifact != nil
            || factory.targetReconstruction != nil
            || !factory.shapeCandidates.isEmpty
            || !factory.materialCandidates.isEmpty
            || !factory.rearWebReferences.isEmpty
            || !factory.sewingWebReferences.isEmpty
            || factory.canUndoShapeDecision
            || !factory.designRequirementReviewItems.isEmpty
            || !factory.visionPipelineReviewItems.isEmpty
            || manufacturingDetails != nil
    }

    private var revision: String {
        [factory.phase,
         factory.lastReport?.verdict ?? "",
         String(factory.previewAttempts),
         job.pendingPreview?.digest ?? "",
         String(factory.shapeCandidates.count),
         String(factory.materialCandidates.count),
         factory.rearReferenceSearchStatus,
         String(factory.rearWebReferences.count),
         factory.sewingReferenceSearchStatus,
         String(factory.sewingWebReferences.count),
         String(factory.canUndoShapeDecision),
         factory.targetReconstruction?.targetDigest ?? "",
         factory.selectedBaseAvatarID,
         String(factory.targetCleanupConfirmed),
         String(factory.designRequirementReviewItems.count),
         factory.visionPipelineReviewItems
            .compactMap { $0["code"] as? String }.joined(separator: ","),
         factory.candidateManufacturingPreview?["compact_digest"] as? String ?? "",
         manufacturingDetails?.digest ?? ""].joined(separator: "|")
    }

    private var pages: [Page] {
        var result: [Page] = []
        if factory.lastReport != nil { result.append(.progress) }
        if factory.previewArtifact != nil { result += [.threeD, .pattern] }
        if manufacturingDetails != nil { result.append(.manufacturing) }
        if factory.targetReconstruction != nil
            || !factory.designRequirementReviewItems.isEmpty
            || !factory.visionPipelineReviewItems.isEmpty
            || !factory.shapeCandidates.isEmpty
            || !factory.materialCandidates.isEmpty
            || factory.rearReferenceSearchStatus != "IDLE"
            || factory.sewingReferenceSearchStatus != "IDLE"
            || factory.canUndoShapeDecision {
            result.append(.choices)
        }
        if job.pendingPreview != nil || job.canUndo { result.append(.change) }
        if hasFactoryContext { result.append(.advanced) }
        return result
    }

    var body: some View {
        if (hasFactoryContext || job.pendingPreview != nil || job.canUndo)
            && dismissedRevision != revision {
            VStack(spacing: 0) {
                inlineCardHeader
                if !collapsed {
                    Divider().opacity(0.25)
                    pageBar
                    Divider().opacity(0.2)
                    windowContent
                        .frame(maxHeight: 440)
                        .transition(.opacity.combined(with: .move(edge: .top)))
                }
            }
            .frame(maxWidth: 880)
            .background(Theme.panel,
                        in: RoundedRectangle(cornerRadius: 13,
                                             style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 13)
                .stroke(Theme.sel.opacity(0.32), lineWidth: 1))
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("atelier.inline-context-card")
            .frame(maxWidth: .infinity)
            .padding(.horizontal, 18)
            .padding(.vertical, 8)
            .sheet(item: $selectedExportArtifact) { artifact in
                exportArtifactSheet(artifact)
            }
            .onAppear {
                selectMostRelevantPage()
            }
            .onChange(of: revision) { _, _ in
                dismissedRevision = ""
                collapsed = true
                candidateControlFocus = nil
                selectMostRelevantPage()
            }
            .onChange(of: collapsed) { _, isCollapsed in
                if isCollapsed {
                    candidateControlFocus = nil
                    return
                }
                // 候補操作は、ユーザーが会話内カードを選んで開いた後だけ
                // フォーカスする。通常の会話ターンでは入力欄を奪わない。
                Task { @MainActor in
                    await Task.yield()
                    focusFirstPendingCandidateIfNeeded()
                }
            }
        }
    }

    private var inlineCardHeader: some View {
        HStack(spacing: 8) {
            Button {
                withAnimation(.easeInOut(duration: 0.18)) {
                    collapsed.toggle()
                }
            } label: {
                HStack(spacing: 8) {
                    Image(systemName: "sparkles.rectangle.stack")
                        .foregroundStyle(Theme.sel)
                    VStack(alignment: .leading, spacing: 1) {
                        Text("Vera Atelier")
                            .font(.system(size: 11.5, weight: .semibold))
                            .foregroundStyle(Theme.fg)
                        Text(collapsed
                             ? "選択して候補・3D・型紙・監査内容を開く"
                             : "チャット内で \(page.rawValue) を表示中")
                            .font(.system(size: 8.5))
                            .foregroundStyle(Theme.faint)
                    }
                    Spacer(minLength: 12)
                    Text(collapsed ? "選択して開く" : "閉じる")
                        .font(.system(size: 8.5, weight: .semibold))
                        .foregroundStyle(Theme.sel)
                    Image(systemName: collapsed ? "chevron.up" : "chevron.down")
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundStyle(Theme.dim)
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityLabel(collapsed
                                ? "Vera Atelier の作業カードを開く"
                                : "Vera Atelier の作業カードを閉じる")
            .accessibilityIdentifier("atelier.inline-context-card.toggle")
            Menu {
                ForEach(GarmentFactoryReactController.InitialAuditMode.allCases) { mode in
                    Button {
                        factory.selectInitialAuditMode(mode)
                    } label: {
                        Label(mode.title,
                              systemImage: factory.selectedAuditMode == mode
                                ? "checkmark.circle.fill" : "circle")
                    }
                }
                Divider()
                Text(factory.selectedAuditMode.detail)
            } label: {
                Label(factory.selectedAuditMode.title,
                      systemImage: factory.selectedAuditMode == .humanAudit
                        ? "person.crop.circle.badge.checkmark"
                        : "wand.and.stars")
                    .font(.system(size: 8.5, weight: .semibold))
            }
            .menuStyle(.borderlessButton)
            .fixedSize()
            .help("画像取り込み時の監査方法。実行中のジョブは変更せず、次の画像から適用します。")
            .accessibilityIdentifier("atelier.initial-audit-mode")
            if factory.busy { ProgressView().controlSize(.mini) }
            Button { dismissedRevision = revision } label: {
                Image(systemName: "xmark")
            }
            .buttonStyle(.plain)
            .help("この作業カードを閉じる。状態が変わると再表示します。")
        }
        .padding(.horizontal, 12).padding(.vertical, 8)
    }

    private var pageBar: some View {
        HStack(spacing: 5) {
            ForEach(pages) { item in
                Button { page = item } label: {
                    Text(item.rawValue)
                        .font(.system(size: 9.5, weight: page == item ? .semibold : .regular))
                        .foregroundStyle(page == item ? Theme.fg : Theme.dim)
                        .padding(.horizontal, 9).padding(.vertical, 4)
                        .background(page == item ? Theme.sel.opacity(0.18) : .clear,
                                    in: Capsule())
                }
                .buttonStyle(.plain)
            }
            Spacer()
            Text(page == .advanced ? "直接検査" : "Chat-first")
                .font(.system(size: 8, weight: .semibold,
                              design: .monospaced))
                .foregroundStyle(page == .advanced ? Theme.warn : Theme.faint)
            Text(factory.activeAuditMode.rawValue)
                .font(.system(size: 7, weight: .semibold,
                              design: .monospaced))
                .foregroundStyle(factory.activeAuditMode == .humanAudit
                                 ? Theme.ok : Theme.warn)
        }
        .padding(.horizontal, 10).padding(.vertical, 6)
    }

    @ViewBuilder
    private var windowContent: some View {
        ScrollView(.vertical, showsIndicators: true) {
            VStack(alignment: .leading, spacing: 8) {
                switch page {
                case .progress:
                    if let report = factory.lastReport { reportCard(report) }
                case .threeD:
                    if let artifact = factory.previewArtifact {
                        FactoryProposedDressedSceneView(
                            points: artifact.points, edges: artifact.edges,
                            faces: artifact.faces,
                            manufacturingPreview:
                                factory.candidateManufacturingPreview,
                            fallbackPieces: artifact.pieces,
                            avatarProfile: factory.selectedBaseAvatar,
                            preservesSourceFront:
                                artifact.preservesSourceFront)
                            .frame(minHeight: 220, idealHeight: 300)
                        artifactCard(artifact)
                    }
                case .pattern:
                    if let artifact = factory.previewArtifact {
                        FactoryFlatPatternPreview(pieces: artifact.pieces)
                            .frame(minHeight: 220, idealHeight: 300)
                    }
                    if manufacturingDetails == nil {
                        Text("製造プレビューがまだ無いため、既存の平面型紙を表示しています。")
                            .font(.system(size: 9))
                            .foregroundStyle(Theme.faint)
                    }
                case .manufacturing:
                    if let details = manufacturingDetails {
                        manufacturingCards(details)
                    } else if let artifact = factory.previewArtifact {
                        FactoryFlatPatternPreview(pieces: artifact.pieces)
                            .frame(minHeight: 220, idealHeight: 300)
                    }
                case .choices:
                    if !factory.visibleFrontInventory.isEmpty {
                        visibleFrontInventoryAuditCard
                    }
                    if let target = factory.targetReconstruction {
                        targetReconstructionCard(target)
                    }
                    if !factory.visionPipelineReviewItems.isEmpty {
                        visionPipelineStatusCard
                    }
                    if !factory.designRequirementReviewItems.isEmpty {
                        requestedConditionsReviewCard
                    }
                    if factory.rearReferenceSearchStatus != "IDLE" {
                        autonomousReferencesCard(
                            title: "背面の類似資料（自律検索）",
                            status: factory.rearReferenceSearchStatus,
                            references: factory.rearWebReferences)
                    }
                    if factory.sewingReferenceSearchStatus != "IDLE" {
                        autonomousReferencesCard(
                            title: "縫い方の資料（自律検索）",
                            status: factory.sewingReferenceSearchStatus,
                            references: factory.sewingWebReferences)
                    }
                    if !factory.shapeCandidates.isEmpty {
                        candidateCard(title: "形・背面の候補",
                                      candidates: factory.shapeCandidates,
                                      material: false)
                    }
                    if !factory.materialCandidates.isEmpty {
                        candidateCard(title: "素材の候補",
                                      candidates: factory.materialCandidates,
                                      material: true)
                    }
                    if factory.canUndoShapeDecision {
                        factoryUndoCard
                    }
                case .change:
                    AtelierDynamicFlowView()
                case .advanced:
                    advancedInspectorCard
                }
                if !feedback.isEmpty {
                    Text(feedback)
                        .font(.system(size: 9.5))
                        .foregroundStyle(Theme.dim)
                        .textSelection(.enabled)
                }
            }
            .padding(10)
        }
    }

    /// The former separate expert surface, projected as folded inspection
    /// groups inside the same Chat-first card. Read-only summaries use the
    /// live typed factory state; the final direct-tools disclosure embeds the
    /// existing editor here instead of routing to another mode or window.
    private var advancedInspectorCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Label("Advanced Inspector", systemImage: "slider.horizontal.3")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(Theme.fg)
                Spacer()
                Text(GarmentFactoryReactController.harnessSchema)
                    .font(.system(size: 7.5, design: .monospaced))
                    .foregroundStyle(Theme.faint)
            }

            inspectorDisclosure("Structure / GarmentStructureGraph",
                                systemImage: "point.3.connected.trianglepath.dotted") {
                inspectorRow("phase", factory.phase)
                inspectorRow("visible front parts",
                             String(factory.visibleFrontInventory.count))
                inspectorRow("shape candidates",
                             String(factory.shapeCandidates.count))
                inspectorRow("current workbench step", context.step)
                ForEach(factory.visibleFrontInventory.prefix(12)) { item in
                    inspectorRow(item.id,
                                 "\(item.normalizedKind) · layer \(item.layer) · \(item.state)")
                }
            }

            inspectorDisclosure("Pattern / Seam topology",
                                systemImage: "scissors") {
                if let artifact = factory.previewArtifact {
                    inspectorRow("method", artifact.method)
                    inspectorRow("mesh",
                                 "\(artifact.points.count) vertices / \(artifact.faces.count) faces")
                    inspectorRow("pattern pieces", String(artifact.pieces.count))
                    inspectorRow("attempt", String(artifact.attempt))
                } else {
                    inspectorRow("state", "UNKNOWN_NO_PATTERN_PREVIEW")
                }
                if let details = manufacturingDetails {
                    inspectorRow("manufacturing pieces", String(details.pieces.count))
                    inspectorRow("sewing steps", String(details.steps.count))
                    inspectorRow("manufacturing ready",
                                 String(details.manufacturingReady))
                    ForEach(Array(details.gates.prefix(8)), id: \.self) { gate in
                        inspectorRow("gate", gate)
                    }
                }
            }

            inspectorDisclosure("Evidence / Proof Cross / Raw IR",
                                systemImage: "cross.case") {
                inspectorRow("target digest",
                             factory.targetSculptDigest ?? "UNKNOWN")
                inspectorRow("requested dimensions",
                             String(factory.designRequirementReviewItems.count))
                inspectorRow("typed review stops",
                             String(factory.visionPipelineReviewItems.count))
                ForEach(factory.trace.suffix(12)) { entry in
                    inspectorRow("r\(entry.round) · \(entry.actor)",
                                 "\(entry.action) → \(entry.verdict)")
                }
            }

            DisclosureGroup(isExpanded: $directInspectorExpanded) {
                AtelierView()
                    .environmentObject(app)
                    .frame(minHeight: 620, idealHeight: 700)
                    .padding(.top, 8)
            } label: {
                VStack(alignment: .leading, spacing: 2) {
                    Label("Direct editing / Pattern・Seam・Material・Graph",
                          systemImage: "ruler")
                        .font(.system(size: 9.5, weight: .semibold))
                        .foregroundStyle(Theme.dim)
                    Text("必要な時だけ、既存の直接編集機能をこのチャット内に展開します")
                        .font(.system(size: 8.25))
                        .foregroundStyle(Theme.faint)
                }
            }
            .padding(9)
            .background(Theme.panel.opacity(0.62),
                        in: RoundedRectangle(cornerRadius: 8))
            .accessibilityIdentifier("atelier.inline-advanced-direct-tools")

            Text("表示は同じ型付き状態の深掘りです。Inspectorを開いただけでは候補承認・事実昇格・型紙変更は行いません。")
                .font(.system(size: 8.25))
                .foregroundStyle(Theme.warn)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private func inspectorDisclosure<Content: View>(
        _ title: String, systemImage: String,
        @ViewBuilder content: @escaping () -> Content
    ) -> some View {
        DisclosureGroup {
            VStack(alignment: .leading, spacing: 4) { content() }
                .padding(.top, 6)
        } label: {
            Label(title, systemImage: systemImage)
                .font(.system(size: 9.5, weight: .semibold))
                .foregroundStyle(Theme.dim)
        }
        .padding(9)
        .background(Theme.panel.opacity(0.62),
                    in: RoundedRectangle(cornerRadius: 8))
    }

    private func inspectorRow(_ key: String, _ value: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text(key)
                .foregroundStyle(Theme.faint)
                .frame(width: 150, alignment: .leading)
            Text(value)
                .foregroundStyle(Theme.fg)
                .textSelection(.enabled)
            Spacer(minLength: 0)
        }
        .font(.system(size: 8, design: .monospaced))
    }

    private func selectMostRelevantPage() {
        if factory.targetReconstruction != nil
            || !factory.designRequirementReviewItems.isEmpty
            || !factory.visionPipelineReviewItems.isEmpty
            || !factory.shapeCandidates.isEmpty
            || !factory.materialCandidates.isEmpty
            || factory.canUndoShapeDecision {
            page = .choices
        } else if job.pendingPreview != nil || job.canUndo {
            page = .change
        } else if manufacturingDetails != nil {
            page = .manufacturing
        } else if factory.previewArtifact != nil {
            page = .threeD
        } else {
            page = .progress
        }
    }

    /// Interactive beginner projection of the same typed target state used by
    /// the expert workbench. Choosing a body or removing a region changes the
    /// target digest; it does not directly mutate a pattern or approve an AI
    /// completion.
    private func targetReconstructionCard(
        _ target: GarmentFactoryReactController.TargetReconstructionArtifact
    ) -> some View {
        let isFrontConformalFallback = target.sculptSurface?.surfaceMode
            == "FRONT_CONFORMAL_SHELL"
        return VStack(alignment: .leading, spacing: 9) {
            HStack(spacing: 6) {
                Image(systemName: "figure.stand.dress.line.vertical.figure")
                    .foregroundStyle(Theme.sel)
                VStack(alignment: .leading, spacing: 1) {
                    Text(isFrontConformalFallback
                         ? "AI生成の融合前景を削って仕上げる"
                         : "融合立体を直接仕上げる")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(Theme.fg)
                    Text(isFrontConformalFallback
                         ? "人物＋服の正面2.5Dです。不要な人体・髪・別衣服を削ります"
                         : "回して確認し、消しゴムのように面を削ります")
                        .font(.system(size: 8.5))
                        .foregroundStyle(Theme.faint)
                }
                Spacer()
                Text(target.sourceKind)
                    .font(.system(size: 7, design: .monospaced))
                    .foregroundStyle(Theme.warn)
            }
            if factory.targetCleanupAuthority != "UNSELECTED" {
                Label(factory.targetCleanupAuthority == "AUTO_ACCEPTED_FOR_PREVIEW"
                      ? "自動採用された比較目標です。AI提案のままで、観測・縫製可能性・製造承認へは昇格しません。"
                      : "人が正面比較目標として採用済み。背面・隠れ面・人体寸法は引き続き未観測です。",
                      systemImage: factory.targetCleanupAuthority
                        == "AUTO_ACCEPTED_FOR_PREVIEW"
                        ? "wand.and.stars" : "person.crop.circle.badge.checkmark")
                    .font(.system(size: 8, weight: .semibold))
                    .foregroundStyle(factory.targetCleanupAuthority
                        == "AUTO_ACCEPTED_FOR_PREVIEW" ? Theme.warn : Theme.ok)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let surface = target.sculptSurface {
                HStack(spacing: 5) {
                    Menu {
                        ForEach(factory.baseAvatarProfiles) { profile in
                            Button(profile.title) {
                                Task { @MainActor in
                                    await factory.selectBaseAvatar(profile.id)
                                }
                            }
                        }
                    } label: {
                        Label(factory.selectedBaseAvatar.title,
                              systemImage: "figure.stand")
                    }
                    .menuStyle(.borderlessButton)
                    .fixedSize()
                    Spacer()
                    ForEach(TargetSculptTool.allCases) { tool in
                        Button {
                            targetSculptTool = tool
                        } label: {
                            Label(tool.title, systemImage: tool.symbol)
                        }
                        .buttonStyle(.bordered)
                        .tint(targetSculptTool == tool ? Theme.sel : Theme.dim)
                        .controlSize(.small)
                    }
                }

                TargetSculptSceneRepresentable(
                    points: factory.targetSculptDisplayVertices,
                    faces: surface.faces,
                    faceRegionIDs: surface.faceRegionIDs,
                    textureCoordinates: surface.textureCoordinates,
                    removedFaces: factory.targetSculptRemovedFaces,
                    clearanceBands: Dictionary(uniqueKeysWithValues:
                        (factory.targetSculptClearancePreview?
                            .faceClearances ?? []).map {
                                ($0.faceIndex, $0.band)
                            }),
                    sourceImagePath: factory.targetSculptSourceImagePath,
                    avatarProfile: factory.selectedBaseAvatar,
                    tool: targetSculptTool,
                    brushRings: Int(targetSculptBrushRings.rounded()),
                    onStroke: { faces, removing in
                        factory.applyTargetSculptFaces(faces, removing: removing)
                    })
                    .frame(minHeight: 300, idealHeight: 380)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                    .overlay(alignment: .topLeading) {
                        Text(targetSculptTool == .orbit
                             ? "ドラッグ: 回転 · ⌥スクロール/ピンチ: 拡大 · スクロール: ページ"
                             : "ドラッグして\(targetSculptTool == .erase ? "削る" : "復元")")
                            .font(.system(size: 7.5, weight: .semibold,
                                          design: .monospaced))
                            .padding(6)
                            .foregroundStyle(Theme.fg)
                            .background(.black.opacity(0.34), in: Capsule())
                            .padding(7)
                    }
                    .accessibilityIdentifier("atelier.beginner.target.sculpt-canvas")

                HStack(spacing: 8) {
                    Text("ブラシ")
                    Slider(value: $targetSculptBrushRings, in: 1...8, step: 1)
                        .frame(maxWidth: 140)
                    Text("\(Int(targetSculptBrushRings))")
                        .font(.system(size: 8, design: .monospaced))
                    Divider().frame(height: 14)
                    Text("布厚")
                    Slider(value: Binding(
                        get: { factory.targetSculptThicknessMM },
                        set: { factory.setTargetSculptThickness($0) }
                    ), in: 0.1...6.0, step: 0.1)
                        .frame(maxWidth: 150)
                    Text(String(format: "%.1f mm", factory.targetSculptThicknessMM))
                        .font(.system(size: 8, design: .monospaced))
                }
                .font(.system(size: 8.5, weight: .medium))
                .foregroundStyle(Theme.dim)

                HStack(spacing: 6) {
                    Text("形状")
                        .font(.system(size: 8.5, weight: .semibold))
                        .foregroundStyle(Theme.dim)
                    Button("引っ張る") {
                        Task { await factory.applyTargetSculptModifier("PULL") }
                    }
                    Button("縦に伸ばす") {
                        Task { await factory.applyTargetSculptModifier("STRETCH") }
                    }
                    Button("風 2.5 m/s") {
                        Task { await factory.applyTargetSculptModifier("WIND_PREVIEW") }
                    }
                    Button("形状Undo") {
                        factory.undoTargetSculptModifier()
                    }
                    .disabled(!factory.canUndoTargetSculptModifier)
                    Spacer()
                    Text("全操作は未承認の比較候補")
                        .font(.system(size: 7.5, design: .monospaced))
                        .foregroundStyle(Theme.warn)
                }
                .buttonStyle(.bordered)
                .controlSize(.mini)

                if let modifier = factory.targetSculptModifierStatus {
                    HStack(spacing: 8) {
                        Label(modifier.kind,
                              systemImage: modifier.kind == "WIND_PREVIEW"
                                ? "wind" : "move.3d")
                        Text("移動頂点 \(modifier.movedVertexCount)")
                        Text("revision \(modifier.revision)")
                        Spacer()
                        Text(modifier.verdict)
                            .font(.system(size: 7, design: .monospaced))
                    }
                    .font(.system(size: 8.25, weight: .medium))
                    .foregroundStyle(Theme.warn)
                }

                if let clearance = factory.targetSculptClearancePreview {
                    VStack(alignment: .leading, spacing: 5) {
                        HStack(spacing: 9) {
                            Label("人体干渉 \(clearance.collisionFaceIndices.count) 面",
                                  systemImage: clearance.collisionFaceIndices.isEmpty
                                    ? "checkmark.shield" : "exclamationmark.triangle")
                            Text("補正頂点 \(clearance.movedVertexCount)")
                            Text(String(format: "補正後最小隙間 %.2f mm",
                                        clearance.minimumClearanceAfterMM))
                            Spacer()
                            Text(clearance.method)
                                .font(.system(size: 7, design: .monospaced))
                        }
                        geometricClearanceLegend
                    }
                    .font(.system(size: 8.25, weight: .medium))
                    .foregroundStyle(clearance.collisionFaceIndices.isEmpty
                                     ? Theme.ok : Theme.warn)
                } else {
                    HStack(spacing: 6) {
                        ProgressView().controlSize(.mini)
                        Text("人体貫通と布厚クリアランスを再計算中")
                    }
                    .font(.system(size: 8.25))
                    .foregroundStyle(Theme.faint)
                }

                HStack(spacing: 7) {
                    Text("\(surface.faces.count - factory.targetSculptRemovedFaces.count) / \(surface.faces.count) 面を保持")
                        .font(.system(size: 8, design: .monospaced))
                        .foregroundStyle(Theme.faint)
                    Spacer()
                    Button("Undo") { factory.undoTargetSculptStroke() }
                        .disabled(factory.targetSculptUndoStack.isEmpty)
                    Button("リセット") { factory.resetTargetSculpt() }
                        .disabled(factory.targetSculptRemovedFaces.isEmpty)
                }
                .buttonStyle(.bordered)
                .controlSize(.mini)

                Label(isFrontConformalFallback
                      ? "AI生成・未承認の正面追従シェルです。背面は生成していません。赤→青は人体＋布厚に対する幾何クリアランスで、圧力・温度・着心地の実測ではありません。"
                      : "人体は融合立体の内側に固定済み。赤→青は決定論的な幾何クリアランスです。素材ドレープ・圧力・温度・着心地の実測ではありません。",
                      systemImage: "square.3.layers.3d")
                    .font(.system(size: 8.25))
                    .foregroundStyle(Theme.warn)
                    .fixedSize(horizontal: false, vertical: true)

                HStack(spacing: 8) {
                    Button(factory.targetCleanupConfirmed
                           ? "この形状を採用済み"
                           : (factory.previewArtifact == nil
                              ? "この形状を採用"
                              : "この形状で型紙・3Dを再計算")) {
                        factory.confirmTargetSculpt()
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.small)
                    .disabled(factory.targetCleanupConfirmed)
                    Spacer()
                    Text(String((factory.targetSculptDigest
                                 ?? target.targetDigest).prefix(12)))
                        .font(.system(size: 7.5, design: .monospaced))
                        .foregroundStyle(Theme.faint)
                        .textSelection(.enabled)
                }
                if factory.targetCleanupConfirmed {
                    if let comparison = factory.targetSameCameraComparison {
                        HStack(spacing: 8) {
                            Label("同一カメラ: \(comparison.convergenceStatus)",
                                  systemImage: comparison.convergenceStatus == "CONVERGED"
                                    ? "checkmark.circle" : "arrow.triangle.2.circlepath")
                            if let iou = comparison.silhouetteIOU {
                                Text(String(format: "輪郭 IoU %.3f", iou))
                            }
                            Text("修正提案 \(comparison.proposalCount)")
                            Spacer()
                            Text(comparison.referenceAuthority)
                                .font(.system(size: 7, design: .monospaced))
                        }
                        .font(.system(size: 8.25, weight: .medium))
                        .foregroundStyle(comparison.convergenceStatus == "CONVERGED"
                                         ? Theme.ok : Theme.warn)
                    } else if factory.previewArtifact != nil {
                        HStack(spacing: 6) {
                            ProgressView().controlSize(.mini)
                            Text("採用した編集目標と候補3Dを同一カメラで比較中")
                        }
                        .font(.system(size: 8.25))
                        .foregroundStyle(Theme.faint)
                    } else {
                        Label("編集目標を採用済み。候補固有3Dができると同一カメラ反復を開始します。",
                              systemImage: "viewfinder")
                            .font(.system(size: 8.25))
                            .foregroundStyle(Theme.faint)
                    }
                }
            } else {
                Label("編集可能な融合3D面をまだ準備できません。外部3Dまたは輪郭ロフトが必要です。",
                      systemImage: "exclamationmark.triangle")
                    .font(.system(size: 9))
                    .foregroundStyle(Theme.warn)
            }
        }
        .padding(9)
        .background(Theme.sel.opacity(0.055),
                    in: RoundedRectangle(cornerRadius: 9))
        .overlay(RoundedRectangle(cornerRadius: 9)
            .stroke(Theme.sel.opacity(0.22), lineWidth: 1))
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("atelier.beginner.target-reconstruction")
    }

    private var geometricClearanceLegend: some View {
        HStack(spacing: 8) {
            clearanceLegendItem(.red, "貫通補正")
            clearanceLegendItem(.orange, "布厚不足")
            clearanceLegendItem(.yellow, "近い")
            clearanceLegendItem(.green, "中間")
            clearanceLegendItem(.blue, "離れる")
            Spacer(minLength: 4)
            Text("幾何のみ / 圧力ではない")
                .font(.system(size: 7, design: .monospaced))
                .foregroundStyle(Theme.faint)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(
            "Geometric clearance heat map from corrected penetration to high clearance; not pressure, temperature, fit, or comfort")
    }

    private func autonomousReferencesCard(
        title: String, status: String,
        references: [GarmentFactoryReactController.GarmentWebReference]
    ) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack(spacing: 6) {
                Label(title, systemImage: "network")
                    .font(.system(size: 10.5, weight: .semibold))
                    .foregroundStyle(Theme.sel)
                Spacer()
                Text(status)
                    .font(.system(size: 7, design: .monospaced))
                    .foregroundStyle(status == "PROPOSED_REFERENCES_READY"
                                     ? Theme.warn : Theme.faint)
            }
            if status == "SEARCHING" {
                HStack(spacing: 6) {
                    ProgressView().controlSize(.mini)
                    Text("FashionSigLIP/ローカル候補と並行して資料を探索中")
                }
                .font(.system(size: 8.5))
                .foregroundStyle(Theme.faint)
            }
            ForEach(references.prefix(5)) { reference in
                VStack(alignment: .leading, spacing: 3) {
                    if let destination = URL(string: reference.url) {
                        Link(destination: destination) {
                            Label(reference.title, systemImage: "arrow.up.right.square")
                                .font(.system(size: 9, weight: .medium))
                        }
                    } else {
                        Text(reference.title)
                            .font(.system(size: 9, weight: .medium))
                    }
                    if !reference.snippet.isEmpty {
                        Text(reference.snippet)
                            .font(.system(size: 8))
                            .foregroundStyle(Theme.dim)
                            .lineLimit(2)
                    }
                    Text("\(reference.authority) · \(reference.rightsState)")
                        .font(.system(size: 6.75, design: .monospaced))
                        .foregroundStyle(Theme.warn)
                }
                .padding(6)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.white.opacity(0.025),
                            in: RoundedRectangle(cornerRadius: 6))
            }
            Text("検索結果は背面・縫製の提案資料です。ページ本文と利用権を確認するまで、形状・型紙・縫製事実には使いません。検索が空でも複数の幾何/モデル候補で継続します。")
                .font(.system(size: 8))
                .foregroundStyle(Theme.warn)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(9)
        .background(Theme.sel.opacity(0.055),
                    in: RoundedRectangle(cornerRadius: 9))
        .overlay(RoundedRectangle(cornerRadius: 9)
            .stroke(Theme.sel.opacity(0.20), lineWidth: 1))
        .accessibilityElement(children: .contain)
        .accessibilityLabel(
            "Autonomous garment references, proposal only, source rights review required")
    }

    private func clearanceLegendItem(_ colour: Color, _ title: String) -> some View {
        HStack(spacing: 3) {
            Circle().fill(colour).frame(width: 6, height: 6)
            Text(title).font(.system(size: 7.25)).foregroundStyle(Theme.dim)
        }
    }

    /// Makes the distinction between a bound semantic candidate and the
    /// outline-only warm preview explicit. This is the exact failure that used
    /// to make a three-piece silhouette look like a completed garment.
    private var visibleFrontInventoryAuditCard: some View {
        VStack(alignment: .leading, spacing: 6) {
            Label("正面の可視部品台帳 · AI提案",
                  systemImage: "square.3.layers.3d")
                .font(.system(size: 10.5, weight: .semibold))
                .foregroundStyle(Theme.sel)
            Text("ここで確認するのは正面に見える衣服数・重なり・部品だけです。背面、素材、実寸、縫製方法は推測のままです。")
                .font(.system(size: 8.5))
                .foregroundStyle(Theme.dim)
                .fixedSize(horizontal: false, vertical: true)
            if factory.visibleFrontInventoryAuthority == "AUTO_ACCEPTED_FOR_PREVIEW" {
                Label("AUTO_ACCEPTED_FOR_PREVIEW — AI提案を比較用に自動採用。観測事実・型紙承認・製造承認ではありません。",
                      systemImage: "wand.and.stars")
                    .font(.system(size: 8, weight: .semibold))
                    .foregroundStyle(Theme.warn)
                    .fixedSize(horizontal: false, vertical: true)
            } else if factory.visibleFrontInventoryAuthority
                        == "HUMAN_REVIEWED_VISIBLE_SOURCE" {
                Label("HUMAN_REVIEWED_VISIBLE_SOURCE — 人が正面可視部品だけを確認済み",
                      systemImage: "person.crop.circle.badge.checkmark")
                    .font(.system(size: 8, weight: .semibold))
                    .foregroundStyle(Theme.ok)
            }
            ForEach(factory.visibleFrontInventory.prefix(24)) { item in
                HStack(alignment: .top, spacing: 6) {
                    Text("L\(item.layer)")
                        .font(.system(size: 7.5, design: .monospaced))
                        .foregroundStyle(Theme.faint)
                        .frame(width: 22, alignment: .leading)
                    VStack(alignment: .leading, spacing: 1) {
                        Text([item.visibleColor, item.label]
                            .compactMap { $0 }.joined(separator: " · "))
                            .font(.system(size: 8.5, weight: .medium))
                            .foregroundStyle(Theme.fg)
                        Text("\(item.sourceKind) → \(item.normalizedKind) · \(item.garmentUnit)")
                            .font(.system(size: 7.2, design: .monospaced))
                            .foregroundStyle(Theme.faint)
                        Text(item.visibleBasis)
                            .font(.system(size: 7.8))
                            .foregroundStyle(Theme.dim)
                            .lineLimit(2)
                    }
                }
            }
            if factory.visibleFrontInventoryAuditRequired {
                if factory.pendingBack3DRequest {
                    Label("背面3Dの要求を保持中 — この監査後も自動で継続します",
                          systemImage: "clock.arrow.circlepath")
                        .font(.system(size: 8.5, weight: .semibold))
                        .foregroundStyle(Theme.warn)
                }
                Button("正面の衣服数・重なり・部品を確認") {
                    Task { @MainActor in
                        _ = await factory.confirmVisibleFrontInventoryAudit()
                    }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .disabled(factory.busy)
                .accessibilityIdentifier(
                    "atelier.beginner.confirm-visible-front-inventory")
                .accessibilityHint(
                    "正面の可視内容だけを確認します。背面・素材・実寸・縫製は承認しません。")
            } else if factory.visibleFrontInventoryAuditConfirmed {
                Label("正面台帳を確認済み — 融合3Dの削除編集を採用してください",
                      systemImage: "checkmark.circle")
                    .font(.system(size: 8.5, weight: .semibold))
                    .foregroundStyle(Theme.ok)
            }
        }
        .padding(9)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.sel.opacity(0.07),
                    in: RoundedRectangle(cornerRadius: 9))
        .overlay(RoundedRectangle(cornerRadius: 9)
            .stroke(Theme.sel.opacity(0.20), lineWidth: 1))
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("atelier.beginner.visible-front-inventory")
    }

    /// Makes the distinction between a bound semantic candidate and the
    /// outline-only warm preview explicit. This is the exact failure that used
    /// to make a three-piece silhouette look like a completed garment.
    private var visionPipelineStatusCard: some View {
        let fallback = factory.visionPipelineReviewItems.contains {
            $0["fallback_used"] as? Bool == true
        }
        let refused = factory.visionPipelineReviewItems.contains { item in
            let code = Self.nonemptyString(item["code"])
                ?? Self.nonemptyString(item["verdict"])
                ?? ""
            let execution = Self.nonemptyString(item["execution_status"])
                ?? ""
            return code.hasPrefix("UNKNOWN_")
                || code.hasPrefix("ESCALATE_")
                || (!execution.isEmpty && execution != "SUCCEEDED")
        }
        let reviewRequired = fallback || refused
        let statusTitle: String
        if fallback {
            statusTitle = "画像構造 · REVIEW（輪郭プレビューのみ）"
        } else if refused {
            statusTitle = "画像構造 · REVIEW（候補生成を型付き拒否）"
        } else {
            statusTitle = "画像構造 · PROPOSED（候補固有3D・型紙に結合）"
        }
        return VStack(alignment: .leading, spacing: 6) {
            Label(statusTitle,
                  systemImage: reviewRequired
                    ? "exclamationmark.triangle" : "link.circle")
                .font(.system(size: 10.5, weight: .semibold))
                .foregroundStyle(reviewRequired ? Theme.warn : Theme.sel)
            ForEach(Array(factory.visionPipelineReviewItems.prefix(4).enumerated()),
                    id: \.offset) { index, item in
                Text(Self.nonemptyString(item["code"])
                     ?? "UNKNOWN_IMAGE_STRUCTURE_STATUS")
                    .font(.system(size: 8.5, weight: .semibold,
                                  design: .monospaced))
                    .foregroundStyle(Theme.fg)
                if let why = Self.nonemptyString(item["why"]) {
                    Text(why)
                        .font(.system(size: 8.5))
                        .foregroundStyle(Theme.dim)
                        .fixedSize(horizontal: false, vertical: true)
                }
                let diagnostics = Self.typedFailureDiagnostics(
                    from: item, reviewIndex: index)
                if !diagnostics.isEmpty {
                    typedFailureDisclosure(
                        diagnostics,
                        id: Self.failureDisclosureID(item, reviewIndex: index))
                }
            }
        }
        .padding(9)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background((reviewRequired ? Theme.warn : Theme.sel).opacity(0.07),
                    in: RoundedRectangle(cornerRadius: 9))
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("atelier.beginner.dynamic.vision-pipeline.status")
        .accessibilityLabel(reviewRequired
            ? "Image structure review: visible-parts pipeline has typed refusals or outline-only fallback; not manufacturing-ready"
            : "Image structure proposed: visible parts bound to candidate-specific 3D and flat pattern; hidden rear, depth, material, dimensions, and sewing remain unobserved")
        .accessibilityValue(factory.visionPipelineReviewItems.prefix(4).map { item in
            let code = Self.nonemptyString(item["code"])
                ?? Self.nonemptyString(item["verdict"])
                ?? "UNKNOWN_IMAGE_STRUCTURE_STATUS"
            let why = Self.nonemptyString(item["why"]) ?? ""
            return why.isEmpty ? code : "\(code): \(why)"
        }.joined(separator: "; "))
    }

    /// Shows only typed detail already returned by the deterministic engine.
    /// It does not infer a missing relation or promote a proposal/unknown into
    /// an observation merely because the diagnostic is visible to a beginner.
    private func typedFailureDisclosure(
        _ diagnostics: [TypedFailureDiagnostic], id: String
    ) -> some View {
        DisclosureGroup(isExpanded: Binding(
            get: { expandedFailureDiagnostics.contains(id) },
            set: { expanded in
                if expanded { expandedFailureDiagnostics.insert(id) }
                else { expandedFailureDiagnostics.remove(id) }
            }
        )) {
            VStack(alignment: .leading, spacing: 6) {
                Text("エンジンが返した型付き情報です。未観測値を確定しません。")
                    .font(.system(size: 8.5))
                    .foregroundStyle(Theme.warn)
                    .fixedSize(horizontal: false, vertical: true)
                ForEach(diagnostics) { diagnostic in
                    VStack(alignment: .leading, spacing: 3) {
                        HStack(alignment: .firstTextBaseline, spacing: 6) {
                            Text(diagnostic.code)
                                .font(.system(size: 8.25, weight: .semibold,
                                              design: .monospaced))
                                .foregroundStyle(Theme.fg)
                                .textSelection(.enabled)
                            Spacer(minLength: 4)
                            Text([diagnostic.state, diagnostic.authority]
                                .compactMap { $0 }.joined(separator: " · "))
                                .font(.system(size: 7.75, weight: .semibold,
                                              design: .monospaced))
                                .foregroundStyle(Theme.warn)
                        }
                        ForEach(diagnostic.fields) { field in
                            HStack(alignment: .firstTextBaseline, spacing: 6) {
                                Text(field.label)
                                    .font(.system(size: 8.25, weight: .medium))
                                    .foregroundStyle(Theme.dim)
                                    .frame(width: 88, alignment: .leading)
                                Text(field.value)
                                    .font(.system(size: 8.25, design: .monospaced))
                                    .foregroundStyle(Theme.faint)
                                    .textSelection(.enabled)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                    }
                    .padding(6)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.white.opacity(0.025),
                                in: RoundedRectangle(cornerRadius: 6))
                }
            }
            .padding(.top, 5)
        } label: {
            HStack(spacing: 6) {
                Image(systemName: "stethoscope")
                    .foregroundStyle(Theme.warn)
                Text("型付き診断を表示")
                    .font(.system(size: 8.75, weight: .semibold))
                    .foregroundStyle(Theme.fg)
                Spacer()
                Text("\(diagnostics.count)件 · REVIEW")
                    .font(.system(size: 7.75, design: .monospaced))
                    .foregroundStyle(Theme.warn)
            }
        }
        .padding(7)
        .background(Theme.warn.opacity(0.045),
                    in: RoundedRectangle(cornerRadius: 7))
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("atelier.beginner.dynamic.typed-failure-diagnostic")
        .accessibilityLabel("Typed engine failure diagnostic, REVIEW; proposal and unknown truth labels are preserved")
        .onAppear {
            // A beginner should see the exact typed stop reason without
            // discovering a hidden disclosure control.  Initialize each
            // diagnostic once so a deliberate manual collapse remains in
            // effect on subsequent view updates.
            if initializedFailureDiagnostics.insert(id).inserted {
                expandedFailureDiagnostics.insert(id)
            }
        }
    }

    private static func failureDisclosureID(
        _ review: [String: Any], reviewIndex: Int
    ) -> String {
        let candidate = nonemptyString(review["candidate_id"]) ?? "candidate"
        let code = nonemptyString(review["code"])
            ?? nonemptyString(review["verdict"]) ?? "failure"
        return "\(reviewIndex):\(candidate):\(code)"
    }

    /// Failure details are commonly nested under `failures[].engine_result`.
    /// Read that envelope recursively, but restrict the visible result to the
    /// small typed identity/topology/closure vocabulary used for remediation.
    private static func typedFailureDiagnostics(
        from review: [String: Any], reviewIndex: Int
    ) -> [TypedFailureDiagnostic] {
        let failures = dictionaries(review["failures"])
        let rows = failures.isEmpty ? [review] : failures
        let inheritedCandidate = nonemptyString(review["candidate_id"])
        let inheritedState = nonemptyString(review["state"]) ?? "REVIEW"
        let inheritedAuthority = nonemptyString(review["authority"])

        return rows.enumerated().compactMap { failureIndex, failure in
            let contexts = failureDiagnosticContexts(failure)
            let code = firstDiagnosticString(
                keys: ["code", "verdict"], contexts: contexts)
                ?? "UNKNOWN_ENGINE_FAILURE"
            let state = firstDiagnosticString(
                keys: ["state"], contexts: contexts) ?? inheritedState
            let authority = firstDiagnosticString(
                keys: ["authority"], contexts: contexts) ?? inheritedAuthority
            var fields: [FailureDiagnosticField] = []

            func append(_ key: String, label: String, fallback: Any? = nil) {
                let value = firstDiagnosticValue(key: key, contexts: contexts)
                    ?? fallback
                guard let text = diagnosticValueText(value) else { return }
                fields.append(.init(id: "\(key):\(fields.count)",
                                    label: label, value: text))
            }

            append("candidate_id", label: "候補", fallback: inheritedCandidate)
            append("garment_unit", label: "服ユニット")
            append("layer", label: "レイヤー")
            append("leg_node_ids", label: "脚ノード")
            append("gusset_node_ids", label: "マチノード")
            append("orphan_gusset_node_ids", label: "未接続マチ")

            let missingKeys = Set(contexts.flatMap { context in
                context.keys.filter { $0.hasPrefix("missing_") }
            }).sorted()
            for key in missingKeys {
                append(key, label: diagnosticLabel(for: key))
            }
            append("how_to_close", label: "解決に必要")

            guard !fields.isEmpty else { return nil }
            return TypedFailureDiagnostic(
                id: "\(reviewIndex):\(failureIndex):\(code)",
                code: code, state: state, authority: authority, fields: fields)
        }
    }

    nonisolated private static func failureDiagnosticContexts(
        _ root: [String: Any]
    ) -> [[String: Any]] {
        var result: [[String: Any]] = []
        var queue: [([String: Any], Int)] = [(root, 0)]
        var cursor = 0
        let nestedKeys = ["detail", "engine_result", "stage_result"]
        while cursor < queue.count {
            let (context, depth) = queue[cursor]
            cursor += 1
            result.append(context)
            guard depth < 3 else { continue }
            for key in nestedKeys {
                if let child = context[key] as? [String: Any] {
                    queue.append((child, depth + 1))
                }
            }
        }
        return result
    }

    nonisolated private static func firstDiagnosticString(
        keys: [String], contexts: [[String: Any]]
    ) -> String? {
        for context in contexts {
            for key in keys {
                if let value = nonemptyString(context[key]) { return value }
            }
        }
        return nil
    }

    nonisolated private static func firstDiagnosticValue(
        key: String, contexts: [[String: Any]]
    ) -> Any? {
        for context in contexts where context[key] != nil {
            return context[key]
        }
        return nil
    }

    nonisolated private static func diagnosticValueText(_ value: Any?) -> String? {
        guard let value else { return nil }
        if let text = nonemptyString(value) { return text }
        if let boolean = value as? Bool { return boolean ? "true" : "false" }
        if let number = value as? NSNumber { return number.stringValue }
        if let values = value as? [Any] {
            let rendered = values.prefix(8).compactMap(diagnosticValueText)
            guard !rendered.isEmpty else { return nil }
            return rendered.joined(separator: ", ")
                + (values.count > rendered.count ? " … +\(values.count - rendered.count)" : "")
        }
        if let dictionary = value as? [String: Any] {
            let rendered = dictionary.keys.sorted().prefix(6).compactMap { key in
                diagnosticValueText(dictionary[key]).map { "\(key)=\($0)" }
            }
            return rendered.isEmpty ? nil : rendered.joined(separator: "; ")
        }
        return nil
    }

    nonisolated private static func diagnosticLabel(for key: String) -> String {
        switch key {
        case "missing_relations", "missing_relation_keys": return "不足関係"
        case "missing_seams": return "不足縫い目"
        case "missing_measurements": return "不足寸法"
        case "missing_element_ids", "missing_elements": return "不足部品"
        default:
            return key.replacingOccurrences(of: "missing_", with: "不足 ")
                .replacingOccurrences(of: "_", with: " ")
        }
    }

    /// Projects the deterministic requirement bridge into beginner mode.
    /// These records are requests/review constraints, never measurements
    /// recovered from a front image. Missing values remain missing.
    private var requestedConditionsReviewCard: some View {
        VStack(alignment: .leading, spacing: 6) {
            Label("指定条件 · REQUESTED_NOT_MEASURED", systemImage: "ruler")
                .font(.system(size: 10.5, weight: .semibold))
                .foregroundStyle(Theme.warn)
            Text("ユーザー指定条件または要確認事項であり、画像から観測した実測値ではありません。AI推測の背面・奥行き・素材も未観測のままです。")
                .font(.system(size: 9))
                .foregroundStyle(Theme.dim)
                .fixedSize(horizontal: false, vertical: true)
            ForEach(Array(factory.designRequirementReviewItems.prefix(8).enumerated()),
                    id: \.offset) { _, item in
                Text(requestedConditionText(item))
                    .font(.system(size: 8.5, design: .monospaced))
                    .foregroundStyle(Theme.faint)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(9)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.warn.opacity(0.07),
                    in: RoundedRectangle(cornerRadius: 9))
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("atelier.beginner.dynamic.requested-conditions.review")
        .accessibilityLabel(requestedConditionsAccessibilityLabel)
    }

    private var requestedConditionsAccessibilityLabel: String {
        let values = factory.designRequirementReviewItems.prefix(8)
            .map(requestedConditionText)
            .joined(separator: "; ")
        let provenance = "Requested conditions, REQUESTED_NOT_MEASURED, not measurements observed from the image; AI-inferred back, depth, and material remain not observed"
        return values.isEmpty ? provenance : "\(provenance); \(values)"
    }

    private func requestedConditionText(_ item: [String: Any]) -> String {
        var parts: [String] = []
        for key in ["requested_text", "text", "label"] {
            if let value = Self.nonemptyString(item[key]) {
                parts.append(value)
                break
            }
        }
        if let target = Self.nonemptyString(item["target"]) {
            parts.append(target)
        } else if let targets = item["targets"] as? [String], !targets.isEmpty {
            parts.append(targets.joined(separator: ", "))
        }
        if let value = Self.numberText(item["value_cm"]) {
            parts.append("\(value) cm")
        } else if let value = Self.numberText(item["value"]) {
            let unit = Self.nonemptyString(item["unit"])
            parts.append(unit.map { "\(value) \($0)" } ?? value)
        }
        if let code = Self.nonemptyString(item["code"]) {
            parts.append(code)
        }
        if let why = Self.nonemptyString(item["why"]) {
            parts.append(why)
        }
        return parts.isEmpty ? "REVIEW · REQUESTED_NOT_MEASURED"
            : parts.joined(separator: " · ")
    }

    private func reportCard(
        _ report: GarmentFactoryReactController.Report
    ) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: factory.busy ? "arrow.triangle.2.circlepath" : "cross.case")
                .foregroundStyle(factory.busy ? Theme.sel : Theme.dim)
            VStack(alignment: .leading, spacing: 3) {
                Text("制作工程  \(report.phase)")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(Theme.fg)
                Text(report.message)
                    .font(.system(size: 9.5))
                    .foregroundStyle(Theme.dim)
                Text("round \(report.iterations) ・ model \(report.modelCalls) ・ expert: \(context.step)")
                    .font(.system(size: 8.5, design: .monospaced))
                    .foregroundStyle(Theme.faint)
            }
            Spacer()
            Text(report.verdict)
                .font(.system(size: 8.5, weight: .semibold, design: .monospaced))
                .foregroundStyle(report.verdict.hasPrefix("UNKNOWN_") ? Theme.warn : Theme.ok)
        }
        .padding(9)
        .background(Theme.panel2, in: RoundedRectangle(cornerRadius: 9))
    }

    private func artifactCard(
        _ artifact: GarmentFactoryReactController.PreviewArtifact
    ) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack {
                Label("3D着装・型紙プレビュー", systemImage: "cube.transparent")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(Theme.fg)
                Spacer()
                Text("PROPOSED")
                    .font(.system(size: 8.5, weight: .bold))
                    .foregroundStyle(Theme.warn)
            }
            Text("\(artifact.method) ・ attempt \(artifact.attempt)")
                .font(.system(size: 9, design: .monospaced))
                .foregroundStyle(Theme.dim)
            Text("vertices \(artifact.points.count) ・ faces \(artifact.faces.count) ・ pattern pieces \(artifact.pieces.count)")
                .font(.system(size: 9, design: .monospaced))
                .foregroundStyle(Theme.faint)
            if !artifact.repairSummary.isEmpty {
                Text(artifact.repairSummary)
                    .font(.system(size: 9))
                    .foregroundStyle(Theme.dim)
                    .lineLimit(3)
            }
        }
        .padding(9)
        .background(Theme.panel2, in: RoundedRectangle(cornerRadius: 9))
    }

    private func candidateCard(
        title: String,
        candidates: [GarmentFactoryReactController.Candidate],
        material: Bool
    ) -> some View {
        let domain = material ? "material" : "structure"
        return VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.system(size: 10.5, weight: .semibold))
                .foregroundStyle(Theme.fg)
            ForEach(candidates.prefix(4)) { candidate in
                let previewFocus = CandidateControlFocus(
                    domain: domain, candidateID: candidate.id, action: .preview)
                let adoptFocus = CandidateControlFocus(
                    domain: domain, candidateID: candidate.id, action: .adopt)
                let rejectFocus = CandidateControlFocus(
                    domain: domain, candidateID: candidate.id, action: .reject)
                VStack(alignment: .leading, spacing: 7) {
                    HStack(alignment: .top, spacing: 8) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(candidate.title)
                                .font(.system(size: 10, weight: .medium))
                                .foregroundStyle(Theme.fg)
                            Text(candidate.detail)
                                .font(.system(size: 8.5))
                                .foregroundStyle(Theme.dim)
                                .lineLimit(3)
                        }
                        Spacer()
                        Button(previewingCandidate == candidate.id ? "3D表示中" : "3Dで見る") {
                            preview(candidate)
                        }
                        .font(.system(size: 9, weight: .semibold))
                        .buttonStyle(.bordered)
                        .disabled(selecting != nil)
                        .focusable()
                        .focused($candidateControlFocus, equals: previewFocus)
                        .onKeyPress(.return) {
                            preview(candidate)
                            return .handled
                        }
                        .onKeyPress(.space) {
                            preview(candidate)
                            return .handled
                        }
                        .onKeyPress(phases: .down) { press in
                            moveCandidateFocus(
                                for: press, candidates: candidates,
                                material: material)
                        }
                        .accessibilityIdentifier(
                            candidateControlIdentifier(previewFocus))
                        .accessibilityLabel(
                            "\(candidate.title)の3D・型紙を確認、AI推測候補")
                        .accessibilityHint("この候補を承認せずに表示します。")
                    }
                    HStack(spacing: 7) {
                        Button(selecting == candidate.id ? "採用中…" : "この案を採用") {
                            choose(candidate, material: material)
                        }
                        .font(.system(size: 9, weight: .semibold))
                        .buttonStyle(.borderedProminent)
                        .disabled(selecting != nil)
                        .focusable()
                        .focused($candidateControlFocus, equals: adoptFocus)
                        .onKeyPress(.return) {
                            choose(candidate, material: material)
                            return .handled
                        }
                        .onKeyPress(.space) {
                            choose(candidate, material: material)
                            return .handled
                        }
                        .onKeyPress(phases: .down) { press in
                            moveCandidateFocus(
                                for: press, candidates: candidates,
                                material: material)
                        }
                        .accessibilityIdentifier(
                            candidateControlIdentifier(adoptFocus))
                        .accessibilityLabel(
                            "AI推測候補「\(candidate.title)」を採用")
                        .accessibilityHint("この提案を明示的に承認し、次の制作工程へ進めます。")

                        if !material {
                            Button(selecting == "reject:\(candidate.id)" ? "却下中…" : "却下") {
                                reject(candidate)
                            }
                            .font(.system(size: 9, weight: .semibold))
                            .buttonStyle(.bordered)
                            .disabled(selecting != nil)
                            .focusable()
                            .focused($candidateControlFocus, equals: rejectFocus)
                            .onKeyPress(.return) {
                                reject(candidate)
                                return .handled
                            }
                            .onKeyPress(.space) {
                                reject(candidate)
                                return .handled
                            }
                            .onKeyPress(phases: .down) { press in
                                moveCandidateFocus(
                                    for: press, candidates: candidates,
                                    material: material)
                            }
                            .accessibilityIdentifier(
                                candidateControlIdentifier(rejectFocus))
                            .accessibilityLabel(
                                "AI推測候補「\(candidate.title)」を却下")
                            .accessibilityHint("digestに結び付けて却下し、別候補を選べる状態を維持します。")
                        }
                    }
                }
                .padding(7)
                .background(Color.white.opacity(0.035),
                            in: RoundedRectangle(cornerRadius: 7))
                .overlay {
                    RoundedRectangle(cornerRadius: 7)
                        .stroke(candidateControlFocus?.candidateID == candidate.id
                                && candidateControlFocus?.domain == domain
                                ? Theme.sel.opacity(0.9) : .clear,
                                lineWidth: 1.5)
                }
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier(
                    "atelier.beginner.dynamic-candidate.\(domain).\(candidate.id).card")
            }
        }
        .padding(9)
        .background(Theme.panel2, in: RoundedRectangle(cornerRadius: 9))
        .focusSection()
    }

    private func candidateControlIdentifier(
        _ focus: CandidateControlFocus
    ) -> String {
        "atelier.beginner.dynamic-candidate.\(focus.domain).\(focus.candidateID).\(focus.action.rawValue)"
    }

    private func candidateFocusOrder(
        _ candidates: [GarmentFactoryReactController.Candidate], material: Bool
    ) -> [CandidateControlFocus] {
        let domain = material ? "material" : "structure"
        return candidates.flatMap { candidate in
            var order = [
                CandidateControlFocus(
                    domain: domain, candidateID: candidate.id, action: .preview),
                CandidateControlFocus(
                    domain: domain, candidateID: candidate.id, action: .adopt),
            ]
            if !material {
                order.append(CandidateControlFocus(
                    domain: domain, candidateID: candidate.id, action: .reject))
            }
            return order
        }
    }

    private func moveCandidateFocus(
        for press: KeyPress,
        candidates: [GarmentFactoryReactController.Candidate], material: Bool
    ) -> KeyPress.Result {
        guard press.key == .tab else { return .ignored }
        let order = candidateFocusOrder(candidates, material: material)
        guard !order.isEmpty else { return .ignored }
        let backwards = press.modifiers.contains(.shift)
        let currentIndex = candidateControlFocus.flatMap { order.firstIndex(of: $0) }
        let nextIndex: Int
        if let currentIndex {
            nextIndex = backwards ? currentIndex - 1 : currentIndex + 1
        } else {
            nextIndex = backwards ? order.count - 1 : 0
        }
        guard order.indices.contains(nextIndex) else {
            candidateControlFocus = nil
            return .ignored
        }
        candidateControlFocus = order[nextIndex]
        return .handled
    }

    private func focusFirstPendingCandidateIfNeeded() {
        guard !collapsed, page == .choices,
              candidateControlFocus == nil, selecting == nil else { return }
        let phase = factory.lastReport?.phase ?? factory.phase
        if ["BACK_CANDIDATES_READY", "STRUCTURE_CANDIDATES_READY"].contains(phase),
           let first = factory.shapeCandidates.first {
            candidateControlFocus = CandidateControlFocus(
                domain: "structure", candidateID: first.id, action: .preview)
        } else if phase == "MATERIAL_CANDIDATES_READY",
                  let first = factory.materialCandidates.first {
            candidateControlFocus = CandidateControlFocus(
                domain: "material", candidateID: first.id, action: .preview)
        }
    }

    private func preview(_ candidate: GarmentFactoryReactController.Candidate) {
        guard selecting == nil else { return }
        previewingCandidate = candidate.id
        Task { @MainActor in
            let shown = await factory.previewShape(candidate)
            feedback = shown
                ? "\(candidate.title) 固有の3D・型紙を表示しました。AI生成の未承認候補です。"
                : "\(candidate.title) の構造を3D・型紙へ変換できませんでした。"
            previewingCandidate = shown ? candidate.id : nil
            if shown { page = .threeD }
        }
    }

    private func choose(_ candidate: GarmentFactoryReactController.Candidate,
                        material: Bool) {
        selecting = candidate.id
        Task {
            let result = await AtelierChatRouter.approveFactoryCandidate(
                candidate, material: material)
            feedback = AtelierChatRouter.transcriptText(for: result)
            selecting = nil
        }
    }

    private func reject(_ candidate: GarmentFactoryReactController.Candidate) {
        selecting = "reject:\(candidate.id)"
        Task {
            let result = await AtelierChatRouter.rejectFactoryCandidate(candidate)
            feedback = AtelierChatRouter.transcriptText(for: result)
            selecting = nil
        }
    }

    private var factoryUndoCard: some View {
        HStack(spacing: 8) {
            Image(systemName: "arrow.uturn.backward.circle")
                .foregroundStyle(Theme.sel)
            VStack(alignment: .leading, spacing: 2) {
                Text("直前の候補判断を取り消す")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(Theme.fg)
                Text("承認に依存する3D・型紙・素材・シミュレーションは失効し、候補比較へ戻ります。")
                    .font(.system(size: 8.5))
                    .foregroundStyle(Theme.dim)
            }
            Spacer(minLength: 8)
            Button(undoingFactoryDecision ? "Undo中…" : "Undo") {
                undoFactoryDecision()
            }
            .font(.system(size: 9, weight: .semibold))
            .buttonStyle(.bordered)
            .disabled(undoingFactoryDecision || selecting != nil)
            .accessibilityIdentifier("atelier.beginner.factory-shape-decision.undo")
        }
        .padding(9)
        .background(Theme.panel2, in: RoundedRectangle(cornerRadius: 9))
    }

    private func undoFactoryDecision() {
        guard !undoingFactoryDecision else { return }
        undoingFactoryDecision = true
        Task {
            let result = await AtelierChatRouter.undoFactoryShapeDecision()
            feedback = AtelierChatRouter.transcriptText(for: result)
            undoingFactoryDecision = false
        }
    }

    // MARK: - Candidate-specific manufacturing projection

    /// Reads only persisted result JSON. Missing, malformed, or not-yet-wired
    /// manufacturing data never gets synthesized from the visual preview.
    private var manufacturingDetails: ManufacturingDetails? {
        if let preview = factory.candidateManufacturingPreview {
            return Self.makeManufacturingDetails(
                preview: preview, plan: factory.candidateSewingPlan,
                package: nil, verification: nil)
        }
        let sources = [job.pendingPreview?.after.resultJSON,
                       job.activeSnapshot.resultJSON].compactMap { $0 }
        for source in sources {
            guard let root = Self.dictionary(from: source),
                  let pattern = Self.findPatternPayload(in: root),
                  let preview = pattern["manufacturing_preview"] as? [String: Any]
            else { continue }
            let plan = pattern["topology_sewing_plan"] as? [String: Any]
            let package = pattern["export_package"] as? [String: Any]
            let verification = pattern["export_verification"] as? [String: Any]
            return Self.makeManufacturingDetails(
                preview: preview, plan: plan, package: package,
                verification: verification)
        }
        return nil
    }

    private func manufacturingCards(_ details: ManufacturingDetails) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline, spacing: 7) {
                Label("候補固有の製造成果物", systemImage: "scissors")
                    .font(.system(size: 11.5, weight: .semibold))
                    .foregroundStyle(Theme.fg)
                Spacer()
                Text(Self.displayManufacturingState(details.candidateState))
                    .font(.system(size: 8.5, weight: .bold))
                    .foregroundStyle(Theme.warn)
            }
            Text("各カードをクリックすると、Veraが保持している裁断・縫製候補の値を確認できます。")
                .font(.system(size: 9))
                .foregroundStyle(Theme.dim)

            manufacturingDisclosure(
                id: "boundaries", title: "裁ち線 / 縫い線",
                icon: "scribble.variable",
                summary: "\(details.pieces.count)裁片"
            ) {
                ForEach(details.pieces) { piece in
                    manufacturingRow(
                        piece.id,
                        value: "縫い線 \(Self.countText(piece.sewPointCount)) ・ 裁ち線 \(Self.countText(piece.cutPointCount))")
                }
            }

            manufacturingDisclosure(
                id: "cut-count", title: "裁断枚数 cut_count",
                icon: "square.on.square",
                summary: "合計 \(details.pieces.compactMap(\.cutCount).reduce(0, +))枚"
            ) {
                ForEach(details.pieces) { piece in
                    manufacturingRow(piece.id,
                                     value: piece.cutCount.map { "×\($0)" } ?? "未記録")
                }
            }

            manufacturingDisclosure(
                id: "notches", title: "合印",
                icon: "triangle",
                summary: "\(details.pieces.reduce(0) { $0 + $1.notchCount })個"
            ) {
                ForEach(details.pieces) { piece in
                    manufacturingRow(piece.id, value: "\(piece.notchCount)個")
                }
            }

            manufacturingDisclosure(
                id: "grain", title: "地の目",
                icon: "arrow.up.and.down",
                summary: "\(details.grains.count)裁片"
            ) {
                if details.grains.isEmpty {
                    manufacturingEmpty("地の目はまだ型付きで記録されていません。")
                } else {
                    ForEach(details.grains) { grain in
                        manufacturingRow(
                            grain.id,
                            value: "\(grain.angle) ・ \(Self.displayEvidenceState(grain.state))"
                                + (grain.orientation.map { " ・ \($0)" } ?? ""))
                    }
                }
            }

            manufacturingDisclosure(
                id: "sewing-order", title: "縫製順序",
                icon: "list.number",
                summary: details.steps.isEmpty ? "未生成" : "\(details.steps.count)工程"
            ) {
                if details.steps.isEmpty {
                    manufacturingEmpty("トポロジから導出した縫製順序はまだありません。")
                } else {
                    ForEach(details.steps) { step in
                        VStack(alignment: .leading, spacing: 2) {
                            Text("\(step.number.map(String.init) ?? "–"). \(Self.displaySewingAction(step.action))")
                                .font(.system(size: 9.5, weight: .medium))
                                .foregroundStyle(Theme.fg)
                            Text(Self.sewingStepDetail(step))
                                .font(.system(size: 8.5, design: .monospaced))
                                .foregroundStyle(Theme.faint)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        .padding(.vertical, 2)
                    }
                }
            }

            manufacturingDisclosure(
                id: "gates", title: "残っている確認",
                icon: "checklist.unchecked",
                summary: details.gates.isEmpty ? "0件" : "\(details.gates.count)件"
            ) {
                if details.gates.isEmpty {
                    manufacturingEmpty("この成果物に記録された残ゲートはありません。")
                } else {
                    ForEach(Array(details.gates.enumerated()), id: \.offset) { _, gate in
                        Label(gate, systemImage: "exclamationmark.circle")
                            .font(.system(size: 9))
                            .foregroundStyle(Theme.warn)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }

            manufacturingDisclosure(
                id: "exports", title: "提出用ファイル",
                icon: "shippingbox",
                summary: details.exports.isEmpty ? "未生成"
                    : (details.exportVerified ? "\(details.exports.count)件・整合確認済み" : "未検証")
            ) {
                if details.exports.isEmpty {
                    manufacturingEmpty("同一候補digestに拘束した提出物はまだ生成されていません。")
                } else {
                    Label(
                        details.exportVerified
                            ? "manifest・SVG・DXF・JSONのhashと候補系譜を再検証しました。"
                            : "提出物の整合検証に通っていないため保存できません。工程を再実行してください。",
                        systemImage: details.exportVerified
                            ? "checkmark.shield" : "exclamationmark.shield")
                        .font(.system(size: 8.5))
                        .foregroundStyle(details.exportVerified ? Theme.ok : Theme.warn)
                        .fixedSize(horizontal: false, vertical: true)
                    ForEach(details.exports) { artifact in
                        Button {
                            selectedExportArtifact = artifact
                        } label: {
                            HStack(spacing: 7) {
                                Image(systemName: artifact.representation == "base64"
                                      ? "doc.zipper" : "doc.text")
                                    .foregroundStyle(Theme.sel)
                                Text(artifact.id)
                                    .font(.system(size: 9.5, weight: .medium))
                                Spacer()
                                Text("\(artifact.byteCount) bytes")
                                    .font(.system(size: 8.5, design: .monospaced))
                                    .foregroundStyle(Theme.faint)
                                Image(systemName: "chevron.right")
                                    .font(.system(size: 8))
                                    .foregroundStyle(Theme.faint)
                            }
                        }
                        .buttonStyle(.plain)
                        .disabled(!details.exportVerified)
                    }
                    Text(details.exportVerificationScope)
                        .font(.system(size: 8, design: .monospaced))
                        .foregroundStyle(Theme.faint)
                }
            }

            Label(
                details.manufacturingReady
                    ? "内部の製造ゲート通過記録がありますが、工業認証・強度・安全性・適合性の保証ではありません。"
                    : "これは未確定を含む製造プレビューです。工業認証・強度・安全性・適合性の保証ではありません。",
                systemImage: details.previewReady ? "eye" : "exclamationmark.triangle")
                .font(.system(size: 8.5))
                .foregroundStyle(Theme.warn)
                .fixedSize(horizontal: false, vertical: true)

            Text("digest \(details.digest.prefix(16))")
                .font(.system(size: 8, design: .monospaced))
                .foregroundStyle(Theme.faint)
                .textSelection(.enabled)
        }
        .padding(9)
        .background(Theme.panel2, in: RoundedRectangle(cornerRadius: 9))
    }

    private func exportArtifactSheet(_ artifact: ExportArtifact) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Label(artifact.id, systemImage: "doc.badge.arrow.up")
                    .font(.system(size: 13, weight: .semibold))
                Spacer()
                Text("\(artifact.byteCount) bytes")
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(Theme.faint)
            }
            if let text = artifact.text {
                ScrollView([.horizontal, .vertical]) {
                    Text(text)
                        .font(.system(size: 9, design: .monospaced))
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .background(Theme.panel2)
            } else {
                Text("DXFの原バイト列です。画面表示用に変換せず、パッケージdigestが対象にした内容をそのまま保存します。")
                    .font(.system(size: 10))
                    .foregroundStyle(Theme.dim)
            }
            HStack {
                Text("候補・構造・型紙の系譜はmanifestに記録されています。")
                    .font(.system(size: 8.5))
                    .foregroundStyle(Theme.warn)
                Spacer()
                Button("保存…") { saveExportArtifact(artifact) }
                    .buttonStyle(.borderedProminent)
            }
        }
        .padding(14)
        .frame(minWidth: 620, minHeight: 420)
        .background(Theme.panel)
    }

    private func saveExportArtifact(_ artifact: ExportArtifact) {
        let data: Data?
        if let text = artifact.text {
            data = text.data(using: .utf8)
        } else if let base64 = artifact.base64 {
            data = Data(base64Encoded: base64)
        } else {
            data = nil
        }
        guard let data else {
            feedback = "提出物のバイト列を復元できませんでした。"
            return
        }
        let panel = NSSavePanel()
        panel.nameFieldStringValue = artifact.id
        panel.canCreateDirectories = true
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do {
            try data.write(to: url, options: .atomic)
            feedback = "\(artifact.id) を保存しました。"
        } catch {
            feedback = "保存できませんでした: \(error.localizedDescription)"
        }
    }

    private func manufacturingDisclosure<Content: View>(
        id: String, title: String, icon: String, summary: String,
        @ViewBuilder content: @escaping () -> Content
    ) -> some View {
        DisclosureGroup(isExpanded: Binding(
            get: { expandedManufacturingCards.contains(id) },
            set: { expanded in
                if expanded { expandedManufacturingCards.insert(id) }
                else { expandedManufacturingCards.remove(id) }
            }
        )) {
            VStack(alignment: .leading, spacing: 4) { content() }
                .padding(.top, 6)
        } label: {
            HStack(spacing: 7) {
                Image(systemName: icon)
                    .frame(width: 14)
                    .foregroundStyle(Theme.sel)
                Text(title)
                    .font(.system(size: 9.5, weight: .semibold))
                    .foregroundStyle(Theme.fg)
                Spacer()
                Text(summary)
                    .font(.system(size: 8.5, design: .monospaced))
                    .foregroundStyle(Theme.faint)
            }
        }
        .padding(8)
        .background(Color.white.opacity(0.035),
                    in: RoundedRectangle(cornerRadius: 7))
    }

    private func manufacturingRow(_ label: String, value: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 7) {
            Text(label)
                .font(.system(size: 9, weight: .medium))
                .foregroundStyle(Theme.dim)
                .lineLimit(2)
            Spacer(minLength: 5)
            Text(value)
                .font(.system(size: 8.5, design: .monospaced))
                .foregroundStyle(Theme.faint)
                .multilineTextAlignment(.trailing)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private func manufacturingEmpty(_ text: String) -> some View {
        Text(text)
            .font(.system(size: 8.5))
            .foregroundStyle(Theme.faint)
            .fixedSize(horizontal: false, vertical: true)
    }

    private static func findPatternPayload(in root: [String: Any]) -> [String: Any]? {
        var queue: [[String: Any]] = [root]
        var cursor = 0
        while cursor < queue.count {
            let dictionary = queue[cursor]
            cursor += 1
            if dictionary["manufacturing_preview"] is [String: Any] {
                return dictionary
            }
            if let pattern = dictionary["pattern"] as? [String: Any] {
                queue.insert(pattern, at: cursor)
            }
            for key in dictionary.keys.sorted() where key != "pattern" {
                if let child = dictionary[key] as? [String: Any] {
                    queue.append(child)
                } else if let children = dictionary[key] as? [[String: Any]] {
                    queue.append(contentsOf: children)
                }
            }
        }
        return nil
    }

    private static func makeManufacturingDetails(
        preview: [String: Any], plan: [String: Any]?,
        package: [String: Any]?, verification: [String: Any]?
    ) -> ManufacturingDetails {
        let notchTable = preview["notches"] as? [String: Any] ?? [:]
        let pieces = dictionaries(preview["pieces"]).enumerated().map { index, row in
            let id = nonemptyString(row["piece_id"])
                ?? nonemptyString(row["name"]) ?? "piece-\(index + 1)"
            return ManufacturingPiece(
                id: id,
                cutCount: positiveInteger(row["cut_count"]),
                sewPointCount: optionalArrayCount(row["sew_line"]),
                cutPointCount: optionalArrayCount(row["cut_line"]),
                notchCount: arrayCount(notchTable[id]),
                layer: nonnegativeInteger(row["layer"]),
                role: nonemptyString(row["role"]))
        }
        let grains = dictionaries(preview["grain"]).enumerated().map { index, row in
            let id = nonemptyString(row["piece"]) ?? "piece-\(index + 1)"
            let angle = numberText(row["angle_deg"]).map { "\($0)°" } ?? "角度未記録"
            return GrainRecord(id: id, angle: angle,
                               state: nonemptyString(row["state"]) ?? "UNKNOWN",
                               orientation: nonemptyString(row["orientation"]))
        }
        let steps = dictionaries(plan?["steps"]).enumerated().map { index, row in
            SewingStep(
                id: nonemptyString(row["step_id"]) ?? "step-\(index + 1)",
                number: positiveInteger(row["step"]),
                action: nonemptyString(row["action"]) ?? "未記録の工程",
                pieces: strings(row["pieces"]),
                dependencies: strings(row["depends_on"]),
                quantity: positiveInteger(row["quantity"]))
        }
        var gates = strings(preview["remaining_gates"])
        for review in dictionaries(plan?["reviews"]) {
            let code = nonemptyString(review["verdict"]) ?? "REVIEW_REQUIRED"
            let why = nonemptyString(review["why"])
            gates.append(why.map { "\(code): \($0)" } ?? code)
        }
        gates = Array(NSOrderedSet(array: gates)).compactMap { $0 as? String }
        let exportFiles = package?["files"] as? [String: Any] ?? [:]
        let exports = exportFiles.keys.sorted().compactMap { filename -> ExportArtifact? in
            guard let row = exportFiles[filename] as? [String: Any] else { return nil }
            let representation = nonemptyString(row["representation"]) ?? "unknown"
            return ExportArtifact(
                id: filename,
                representation: representation,
                text: row["text"] as? String,
                base64: row["data"] as? String,
                byteCount: nonnegativeInteger(row["bytes"]) ?? 0)
        }
        let exportVerified = verification?["verdict"] as? String == "ANSWER"
            && verification?["verified"] as? Bool == true
            && nonemptyString(verification?["package_digest"])
                == nonemptyString(package?["digest"])
        return ManufacturingDetails(
            digest: nonemptyString(preview["digest"])
                ?? nonemptyString(preview["source_digest"]) ?? "digest-not-recorded",
            candidateState: nonemptyString(preview["candidate_state"]) ?? "PROPOSED",
            previewReady: preview["manufacturing_preview_ready"] as? Bool ?? false,
            manufacturingReady: preview["manufacturing_ready"] as? Bool ?? false,
            pieces: pieces, grains: grains, steps: steps, gates: gates,
            exports: exports, exportVerified: exportVerified,
            exportVerificationScope: nonemptyString(
                verification?["verification_scope"])
                ?? "transport integrity has not been verified")
    }

    private static func dictionaries(_ value: Any?) -> [[String: Any]] {
        guard let rows = value as? [Any] else { return [] }
        return rows.compactMap { $0 as? [String: Any] }
    }

    private static func strings(_ value: Any?) -> [String] {
        guard let rows = value as? [Any] else { return [] }
        return rows.compactMap { nonemptyString($0) }
    }

    private static func arrayCount(_ value: Any?) -> Int {
        (value as? [Any])?.count ?? 0
    }

    private static func optionalArrayCount(_ value: Any?) -> Int? {
        guard let rows = value as? [Any], !rows.isEmpty else { return nil }
        return rows.count
    }

    private static func dictionary(from json: String) -> [String: Any]? {
        guard let data = json.data(using: .utf8),
              let object = try? JSONSerialization.jsonObject(with: data),
              let dictionary = object as? [String: Any]
        else { return nil }
        return dictionary
    }

    nonisolated private static func nonemptyString(_ value: Any?) -> String? {
        guard let text = value as? String,
              !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        else { return nil }
        return text
    }

    private static func positiveInteger(_ value: Any?) -> Int? {
        guard !(value is Bool), let number = value as? NSNumber,
              number.doubleValue.rounded() == number.doubleValue,
              number.intValue > 0 else { return nil }
        return number.intValue
    }

    private static func nonnegativeInteger(_ value: Any?) -> Int? {
        guard !(value is Bool), let number = value as? NSNumber,
              number.doubleValue.rounded() == number.doubleValue,
              number.intValue >= 0 else { return nil }
        return number.intValue
    }

    private static func numberText(_ value: Any?) -> String? {
        guard !(value is Bool), let number = value as? NSNumber else { return nil }
        return String(format: "%g", number.doubleValue)
    }

    private static func countText(_ value: Int?) -> String {
        value.map { "\($0)点" } ?? "未記録"
    }

    private static func displayEvidenceState(_ state: String) -> String {
        switch state.uppercased() {
        case "APPROVED", "EXPLICIT", "MEASURED": return "確認値"
        case "PROPOSED", "INFERRED": return "推測値"
        default: return "未確認"
        }
    }

    private static func displayManufacturingState(_ state: String) -> String {
        switch state.uppercased() {
        case "APPROVED": return "採用候補"
        case "OBSERVED": return "観測由来"
        default: return "PROPOSED"
        }
    }

    private static func displaySewingAction(_ action: String) -> String {
        [
            "close_intrinsic_wrap": "本体の閉じ縫い",
            "join_pieces": "裁片を接合",
            "attach_sleeve": "袖を取り付け",
            "attach_hood": "フードを取り付け",
            "attach_collar": "衿を取り付け",
            "attach_gathered_section": "ギャザー部を取り付け",
            "secure_overlap": "重なりを固定",
            "apply_outer_layer": "外側レイヤーを配置",
            "finish_opening": "開きを仕上げ",
            "mark_and_form_gathers": "ギャザーを印付け・成形",
            "sew_dart": "ダーツを縫う",
            "form_pleat": "プリーツを成形",
            "form_fold": "折りを成形",
        ][action] ?? action
    }

    private static func sewingStepDetail(_ step: SewingStep) -> String {
        var parts: [String] = []
        if !step.pieces.isEmpty { parts.append(step.pieces.joined(separator: ", ")) }
        if let quantity = step.quantity { parts.append("quantity \(quantity)") }
        if !step.dependencies.isEmpty {
            parts.append("after: \(step.dependencies.joined(separator: ", "))")
        }
        return parts.isEmpty ? "依存情報なし" : parts.joined(separator: " ・ ")
    }
}

private extension View {
    func cardSurface(border: Color = Theme.faint.opacity(0.24)) -> some View {
        padding(10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.panel2.opacity(0.72),
                        in: RoundedRectangle(cornerRadius: 10))
            .overlay {
                RoundedRectangle(cornerRadius: 10)
                    .stroke(border, lineWidth: 1)
            }
    }
}
