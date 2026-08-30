import AppKit
import SceneKit
import SwiftUI
import simd

// MARK: - AtelierConversationContext
//
// ChatGPT-style working memory for Atelier: one text transcript for the
// lifetime of this app process, with old turns folded into an in-transcript
// summary when the selected model's context budget is approached.  It never
// calls SessionStore, CortexEngine, EternalMemoryStore, VeraMemoryBridge, or
// SessionMemoryArchiver; closing the app discards it.  The stereo-cross keeps
// garment state/evidence deterministic, while this store remembers only what
// the user and the UI said during the current session.
@MainActor
final class AtelierConversationContext: ObservableObject {
    static let shared = AtelierConversationContext()

    enum Role { case user, navigation, assistant, refusal, system }

    struct Entry: Identifiable {
        let id = UUID()
        let role: Role
        let text: String
    }

    @Published private(set) var entries: [Entry] = []
    @Published private(set) var compressedTurnCount = 0

    private init() {}

    func append(_ role: Role, _ text: String, characterBudget: Int) {
        entries.append(Entry(role: role, text: text))
        compactIfNeeded(characterBudget: characterBudget)
    }

    func clear() {
        entries.removeAll()
        compressedTurnCount = 0
    }

    /// A plain role/text history suitable for a future Atelier LLM mouth.
    /// The deterministic router remains the only component allowed to act.
    var contextMessages: [ChatMessage] {
        entries.map { entry in
            let role: ChatMessage.Role
            switch entry.role {
            case .user: role = .user
            case .navigation, .assistant, .refusal: role = .assistant
            case .system: role = .system
            }
            return ChatMessage(role: role, content: entry.text)
        }
    }

    private func compactIfNeeded(characterBudget: Int) {
        guard characterBudget < Int.max / 8 else { return }
        let safeBudget = max(characterBudget, 4_000)
        guard entries.reduce(0, { $0 + $1.text.count }) > safeBudget else { return }

        let keepCount = 12
        guard entries.count > keepCount + 2 else { return }
        let old = Array(entries.dropLast(keepCount))
        let recent = Array(entries.suffix(keepCount))
        let priorSummary = old.first.flatMap { $0.role == .system ? $0.text : nil }
        let raw = old.dropFirst(priorSummary == nil ? 0 : 1)

        var lines: [String] = []
        if let priorSummary {
            lines.append(String(priorSummary.prefix(safeBudget / 5)))
        }
        for entry in raw {
            let label: String
            switch entry.role {
            case .user: label = "User"
            case .navigation: label = "Navigation"
            case .assistant: label = "Atelier"
            case .refusal: label = "Refusal"
            case .system: label = "Context"
            }
            lines.append("\(label): \(String(entry.text.prefix(240)))")
        }
        let cap = max(1_000, safeBudget / 3)
        let summary = String(("[ATELIER SESSION SUMMARY — text only, not persisted]\n" +
                              lines.joined(separator: "\n")).prefix(cap))
        compressedTurnCount += raw.count
        entries = [Entry(role: .system, text: summary)] + recent
    }
}

// MARK: - AtelierChatPaneView
//
// UI B (owner's spec, verbatim): 「チャット画面プラス服飾uiというのは全体を
// 表示しながら現在いるuiをチャットが自動で切り替えてくれるというもの…
// こっちは全体を表示していてそこを開くというもの。」The whole garment
// workbench stays on screen (`AtelierView`, untouched, still the ONE place
// that view is drawn — see AtelierView.swift's own house-rule comment);
// this pane sits BESIDE it and asks `AtelierChatRouter` where a typed line
// resolves. Recognised garment mutations compile to typed IR and show an
// immutable preview here; navigation remains the legacy fallback. It never
// calls a model to decide facts or to invent a destination.
//
// The transcript is a process-local text conversation. It deliberately does
// not reuse `app.messages`, because that path persists sessions and can write
// Cortex/Vera/JCross memories. One pane, one job: remember this Atelier
// session, resolve a typed line, move or answer, and forget it on app exit.
struct AtelierChatPaneView: View {
    @EnvironmentObject var app: AppState
    /// The mirror, not the model — this pane lives outside AtelierView's
    /// subtree. See `AtelierContext.step` and `AtelierNavigator`.
    @ObservedObject private var ctx = AtelierContext.shared
    @ObservedObject private var nav = AtelierNavigator.shared
    @StateObject private var job = GarmentGenerationJob.shared
    @StateObject private var factory = GarmentFactoryReactController.shared
    @StateObject private var intake = AtelierIntake.shared
    @ObservedObject private var conversation = AtelierConversationContext.shared
    @State private var input: String = ""
    @State private var resolving = false
    @FocusState private var focused: Bool
    @FocusState private var candidateControlFocus: CandidateControlFocus?

    private enum CandidateControlAction: String, Hashable {
        case preview
        case adopt
    }

    /// A candidate id alone is not unique across the structure and material
    /// lists.  Keeping the domain and action in the focus identity makes Tab
    /// order stable even when the cards are rebuilt after a factory update.
    private struct CandidateControlFocus: Hashable {
        let domain: String
        let candidateID: String
        let action: CandidateControlAction
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider().opacity(0.25)
            if let report = factory.lastReport {
                factoryProgressCard(report)
                Divider().opacity(0.25)
            }
            transcript
            Divider().opacity(0.25)
            if let preview = job.pendingPreview {
                pendingPreviewCard(preview)
                Divider().opacity(0.25)
            }
            if intake.selectedClip != nil {
                selectedPhotoStrip
            }
            inputRow
        }
        .background(Theme.panel)
        // The same chat surface is used inline and beside the workbench.
        // Keep a readable floor, but never hard-clip it at an arbitrary
        // maximum width: the surrounding split or chat canvas owns width.
        .frame(minWidth: 320, idealWidth: 380, maxWidth: .infinity)
        .layoutPriority(1)
    }

    // MARK: - Header

    private var header: some View {
        HStack(spacing: 6) {
            Image(systemName: "bubble.left.and.bubble.right")
                .font(.system(size: 10))
                .foregroundStyle(Theme.sel)
            Text(app.t("Steer", "誘導")).font(.system(size: 11, weight: .semibold))
                .foregroundStyle(Theme.fg)
            Spacer()
            Text(app.t("now: \(ctx.step)", "現在地: \(ctx.step)"))
                .font(.system(size: 10, design: .monospaced))
                .foregroundStyle(Theme.dim)
                .lineLimit(1)
            if let state = job.activeSnapshot.state {
                Text(state.rawValue)
                    .font(.system(size: 8.5, design: .monospaced))
                    .foregroundStyle(Theme.faint)
                    .lineLimit(1)
            }
            if conversation.compressedTurnCount > 0 {
                Text(app.t("compressed \(conversation.compressedTurnCount)",
                           "圧縮 \(conversation.compressedTurnCount)"))
                    .font(.system(size: 8.5, design: .monospaced))
                    .foregroundStyle(Theme.faint)
            }
            Button {
                conversation.clear()
            } label: {
                Image(systemName: "trash")
                    .font(.system(size: 9))
            }
            .buttonStyle(.plain)
            .foregroundStyle(Theme.faint)
            .help(app.t("Clear this Atelier session", "このAtelierセッションを消去"))
        }
        .padding(.horizontal, 12).padding(.vertical, 8)
    }

    // MARK: - Transcript

    private func factoryProgressCard(
        _ report: GarmentFactoryReactController.Report
    ) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                factoryProgressHeader(report)
                factoryStageRail(report)
                factoryInferenceNotice(report)

                if let target = factory.targetReconstruction {
                    factoryTargetReconstructionCard(target)
                }

                // This audit deliberately precedes rear/structure candidate
                // generation. Keeping it inside `factoryCandidateCard` made
                // the required action disappear during
                // HUMAN_GARMENT_AUDIT_REQUIRED, when no candidate card exists.
                if !factory.visibleFrontInventory.isEmpty {
                    factoryVisibleFrontInventoryCard
                }

                if !factory.visionPatternOperations.isEmpty {
                    factoryVisionPatternOperationCard(factory.visionPatternOperations)
                }

                if let artifact = factory.previewArtifact {
                    factoryArtifactPreview(artifact)
                }

                if report.phase == "BACK_CANDIDATES_READY"
                    || report.phase == "STRUCTURE_CANDIDATES_READY" {
                    factoryCandidateCard(factory.shapeCandidates, material: false)
                }
                if report.phase == "MATERIAL_CANDIDATES_READY" {
                    factoryCandidateCard(factory.materialCandidates, material: true)
                }
                if !factory.trace.isEmpty {
                    factoryTraceCard
                }
                artifactRouteCard
            }
            .padding(10)
        }
        .frame(maxHeight: 420)
        .background(Theme.panel2)
        .accessibilityElement(children: .contain)
        .accessibilityLabel(app.t("Garment production progress",
                                  "服の制作進捗"))
    }

    private func factoryProgressHeader(
        _ report: GarmentFactoryReactController.Report
    ) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack(spacing: 7) {
                Image(systemName: report.verdict == "CONVERGED"
                      ? "checkmark.seal.fill" : "gearshape.2.fill")
                    .foregroundStyle(report.verdict == "CONVERGED" ? Theme.ok : Theme.sel)
                Text(app.t("Making this garment", "この服を制作中"))
                    .font(.system(size: 11.5, weight: .semibold))
                    .foregroundStyle(Theme.fg)
                if factory.busy {
                    ProgressView().controlSize(.small)
                }
                Spacer()
                Text("\(report.iterations)/8")
                    .font(.system(size: 8.5, design: .monospaced))
                    .foregroundStyle(Theme.faint)
            }
            Text(factoryStageTitle(report.phase))
                .font(.system(size: 10.5, weight: .medium))
                .foregroundStyle(Theme.fg)
            Text(report.message)
                .font(.system(size: 9.5))
                .foregroundStyle(Theme.dim)
                .fixedSize(horizontal: false, vertical: true)
            HStack(spacing: 5) {
                evidenceBadge(report.verdict.hasPrefix("UNKNOWN_")
                              ? app.t("waiting", "確認待ち")
                              : report.verdict,
                              color: report.verdict.hasPrefix("UNKNOWN_")
                              ? Theme.warn : Theme.sel)
                evidenceBadge(app.t("Vera controls", "Vera制御"), color: Theme.ok)
                if report.modelCalls > 0 {
                    evidenceBadge(app.t("AI proposals \(report.modelCalls)",
                                        "AI提案 \(report.modelCalls)"),
                                  color: Theme.warn)
                }
            }
        }
    }

    private func factoryStageRail(
        _ report: GarmentFactoryReactController.Report
    ) -> some View {
        let current = factoryStageIndex(report.phase)
        let labels = zip(
            ["Photo", "Search", "Shape", "Pattern", "Fabric", "Review"],
            ["写真", "検索", "構造", "型紙", "素材", "検証"]
        ).map { app.t($0.0, $0.1) }
        return VStack(alignment: .leading, spacing: 5) {
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule().fill(Theme.faint.opacity(0.28)).frame(height: 3)
                    Capsule().fill(Theme.sel).frame(
                        width: geo.size.width * CGFloat(max(0, current)) /
                            CGFloat(max(1, labels.count - 1)), height: 3)
                }
            }
            .frame(height: 3)
            HStack(spacing: 0) {
                ForEach(Array(labels.enumerated()), id: \.offset) { index, label in
                    Text(label)
                        .font(.system(size: 7.5, weight: index <= current ? .semibold : .regular))
                        .foregroundStyle(index <= current ? Theme.sel : Theme.faint)
                        .frame(maxWidth: .infinity)
                }
            }
        }
        .accessibilityLabel(app.t("Production stage \(current + 1) of \(labels.count)",
                                  "制作工程 \(current + 1) / \(labels.count)"))
    }

    @ViewBuilder
    private func factoryInferenceNotice(
        _ report: GarmentFactoryReactController.Report
    ) -> some View {
        if isInferencePhase(report.phase) || report.modelCalls > 0 {
            VStack(alignment: .leading, spacing: 4) {
                Label(app.t("AI inference — not observed",
                            "AI推測 — 観測事実ではありません"),
                      systemImage: "sparkles")
                    .font(.system(size: 9.5, weight: .semibold))
                    .foregroundStyle(Theme.warn)
                Text(app.t(
                    "A front photo cannot confirm the back, internal construction, or material. Alternatives remain PROPOSED until you choose one; Vera does not let the model approve itself.",
                    "正面写真だけでは背面・内部構造・素材を確定できません。候補は選択されるまでPROPOSEDのままで、VeraはAI自身による承認を許可しません。"))
                    .font(.system(size: 9))
                    .foregroundStyle(Theme.dim)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(8)
            .background(Theme.warn.opacity(0.08), in: RoundedRectangle(cornerRadius: 7))
        }
    }

    private func factoryCandidateCard(
        _ candidates: [GarmentFactoryReactController.Candidate],
        material: Bool
    ) -> some View {
        let domain = material ? "material" : "structure"
        return VStack(alignment: .leading, spacing: 5) {
            HStack(spacing: 6) {
                Text(material
                     ? app.t("Material hypotheses", "素材の推測候補")
                     : app.t("Back / structure hypotheses", "背面・構造の推測候補"))
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(Theme.fg)
                Spacer()
                Text(app.t("Tab: candidate controls", "Tab: 候補を操作"))
                    .font(.system(size: 7.5, design: .monospaced))
                    .foregroundStyle(Theme.faint)
            }
            if !factory.designRequirementReviewItems.isEmpty {
                factoryDesignRequirementReviewCard
            }
            ForEach(candidates) { candidate in
                let previewFocus = CandidateControlFocus(
                    domain: domain, candidateID: candidate.id, action: .preview)
                let adoptFocus = CandidateControlFocus(
                    domain: domain, candidateID: candidate.id, action: .adopt)
                VStack(alignment: .leading, spacing: 6) {
                    HStack(alignment: .top, spacing: 6) {
                        Image(systemName: "person.crop.circle.badge.checkmark")
                        VStack(alignment: .leading, spacing: 2) {
                            HStack(spacing: 5) {
                                Text(candidate.title)
                                    .font(.system(size: 9.5, weight: .semibold))
                                Text("PROPOSED")
                                    .font(.system(size: 7, weight: .bold, design: .monospaced))
                                    .foregroundStyle(Theme.warn)
                            }
                            Text(candidate.detail)
                                .font(.system(size: 8.5))
                                .foregroundStyle(Theme.faint)
                                .lineLimit(4)
                            Text(app.t("proposal digest ", "提案digest ") +
                                 String(candidate.digest.prefix(12)))
                                .font(.system(size: 7.5, design: .monospaced))
                                .foregroundStyle(Theme.faint)
                            Text(app.t("Choose this hypothesis",
                                       "この推測を人が採用する"))
                                .font(.system(size: 8.5, weight: .semibold))
                                .foregroundStyle(Theme.sel)
                        }
                        Spacer()
                    }
                    HStack(spacing: 7) {
                        if !material {
                            Button(app.t("Preview 3D / pattern", "3D・型紙を確認")) {
                                Task { @MainActor in
                                    _ = await factory.previewShape(candidate)
                                }
                            }
                            .buttonStyle(.bordered)
                            .controlSize(.small)
                            .focusable()
                            .focused($candidateControlFocus, equals: previewFocus)
                            .onKeyPress(.return) {
                                Task { @MainActor in
                                    _ = await factory.previewShape(candidate)
                                }
                                return .handled
                            }
                            .onKeyPress(.space) {
                                Task { @MainActor in
                                    _ = await factory.previewShape(candidate)
                                }
                                return .handled
                            }
                            .onKeyPress(phases: .down) { press in
                                moveCandidateFocus(
                                    for: press, candidates: candidates,
                                    material: material)
                            }
                            .accessibilityIdentifier(
                                candidateControlIdentifier(previewFocus))
                            .accessibilityLabel(app.t(
                                "Preview 3D and pattern for \(candidate.title), AI-proposed candidate",
                                "\(candidate.title)の3D・型紙を確認、AI推測候補"))
                            .accessibilityHint(app.t(
                                "Shows this candidate without approving it.",
                                "この候補を承認せずに表示します。"))
                        }
                        Button(app.t("Adopt", "この案を採用")) {
                            approveFactoryCandidate(candidate, material: material)
                        }
                        .buttonStyle(.borderedProminent)
                        .controlSize(.small)
                        .focusable()
                        .focused($candidateControlFocus, equals: adoptFocus)
                        .onKeyPress(.return) {
                            approveFactoryCandidate(candidate, material: material)
                            return .handled
                        }
                        .onKeyPress(.space) {
                            approveFactoryCandidate(candidate, material: material)
                            return .handled
                        }
                        .onKeyPress(phases: .down) { press in
                            moveCandidateFocus(
                                for: press, candidates: candidates,
                                material: material)
                        }
                        .accessibilityIdentifier(
                            candidateControlIdentifier(adoptFocus))
                        .accessibilityLabel(app.t(
                            "Adopt \(candidate.title), AI-proposed candidate",
                            "AI推測候補「\(candidate.title)」を採用"))
                        .accessibilityHint(app.t(
                            "Explicitly approves this proposal for the next factory step.",
                            "この提案を明示的に承認し、次の制作工程へ進めます。"))
                    }
                }
                .foregroundStyle(Theme.sel)
                .disabled(resolving)
                .padding(7)
                .background(Theme.panel, in: RoundedRectangle(cornerRadius: 7))
                .overlay {
                    RoundedRectangle(cornerRadius: 7)
                        .stroke(candidateControlFocus?.candidateID == candidate.id
                                && candidateControlFocus?.domain == domain
                                ? Theme.sel.opacity(0.9) : .clear,
                                lineWidth: 1.5)
                }
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier(
                    "atelier.beginner.candidate.\(domain).\(candidate.id).card")
                .accessibilityLabel(app.t(
                    "\(candidate.title), AI-proposed \(domain) candidate",
                    "\(candidate.title)、AI推測の\(material ? "素材" : "背面・構造")候補"))
            }
        }
        .focusSection()
    }

    /// Renders only records already published by the deterministic design-
    /// requirement bridge.  Values absent from those records stay absent: a
    /// front image is never promoted to a body measurement by this view.
    private var factoryDesignRequirementReviewCard: some View {
        VStack(alignment: .leading, spacing: 4) {
            Label(app.t("Requested conditions · REQUESTED_NOT_MEASURED",
                        "指定条件 · REQUESTED_NOT_MEASURED"),
                  systemImage: "ruler")
                .font(.system(size: 8.5, weight: .semibold))
                .foregroundStyle(Theme.warn)
            Text(app.t(
                "These are user-requested conditions or review items, not measurements observed from the image. AI-inferred back, depth, and material remain not observed.",
                "ユーザー指定条件または要確認事項であり、画像から観測した実測値ではありません。AI推測の背面・奥行き・素材も未観測のままです。"))
                .font(.system(size: 8))
                .foregroundStyle(Theme.dim)
                .fixedSize(horizontal: false, vertical: true)
            ForEach(Array(factory.designRequirementReviewItems.prefix(4).enumerated()),
                    id: \.offset) { _, item in
                Text(designRequirementReviewText(item))
                    .font(.system(size: 7.5, design: .monospaced))
                    .foregroundStyle(Theme.faint)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(7)
        .background(Theme.warn.opacity(0.07),
                    in: RoundedRectangle(cornerRadius: 6))
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("atelier.beginner.requested-conditions.review")
    }

    private func factoryTargetReconstructionCard(
        _ target: GarmentFactoryReactController.TargetReconstructionArtifact
    ) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack(spacing: 6) {
                Label(app.t("Choose the body, then clean the fused target",
                            "体型を選び、融合目標を手で整える"),
                      systemImage: "figure.stand")
                    .font(.system(size: 9.5, weight: .semibold))
                    .foregroundStyle(Theme.fg)
                Spacer()
                evidenceBadge(target.sourceKind, color: Theme.warn)
            }
            Text(app.t(
                "Vera keeps this body fixed while it dresses patterns and compares them with the photo. These are chosen preview dimensions, not measurements inferred from the image.",
                "この人体を型紙着装と写真比較の間ずっと固定します。表示寸法は選択した設計値で、画像から測った人体寸法ではありません。"))
                .font(.system(size: 8))
                .foregroundStyle(Theme.dim)
                .fixedSize(horizontal: false, vertical: true)

            VStack(alignment: .leading, spacing: 4) {
                Text(app.t("1 · Base body", "1 · 着せる人体"))
                    .font(.system(size: 8.5, weight: .semibold))
                    .foregroundStyle(Theme.sel)
                ForEach(factory.baseAvatarProfiles) { profile in
                    Button {
                        Task { @MainActor in
                            await factory.selectBaseAvatar(profile.id)
                        }
                    } label: {
                        HStack(spacing: 6) {
                            Image(systemName: factory.selectedBaseAvatarID == profile.id
                                  ? "checkmark.circle.fill" : "circle")
                            Text(profile.title)
                                .font(.system(size: 8.5, design: .monospaced))
                            Spacer()
                            Text(profile.authority)
                                .font(.system(size: 6.5, design: .monospaced))
                                .foregroundStyle(Theme.faint)
                        }
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(factory.selectedBaseAvatarID == profile.id
                                     ? Theme.sel : Theme.dim)
                    .accessibilityIdentifier("atelier.target.avatar.\(profile.id)")
                }
            }

            VStack(alignment: .leading, spacing: 4) {
                Text(app.t("2 · Keep or remove source regions",
                           "2 · 元画像の領域を残す／消す"))
                    .font(.system(size: 8.5, weight: .semibold))
                    .foregroundStyle(Theme.sel)
                ForEach(target.regions) { region in
                    HStack(spacing: 6) {
                        Image(systemName: region.removed ? "eye.slash" : "eye")
                            .foregroundStyle(region.removed ? Theme.warn : Theme.ok)
                        VStack(alignment: .leading, spacing: 1) {
                            Text(region.label)
                                .font(.system(size: 8.5, weight: .medium))
                                .foregroundStyle(Theme.fg)
                            Text("\(region.regionClass) · \(region.state)" +
                                 (region.occludesGarment
                                  ? " · " + app.t("covers garment", "服を覆う") : ""))
                                .font(.system(size: 6.8, design: .monospaced))
                                .foregroundStyle(Theme.faint)
                        }
                        Spacer()
                        if region.removable {
                            Button(region.removed
                                   ? app.t("Restore", "戻す")
                                   : app.t("Remove", "消す")) {
                                Task { @MainActor in
                                    await factory.toggleTargetCleanupRegion(region.id)
                                }
                            }
                            .buttonStyle(.bordered)
                            .controlSize(.mini)
                            .accessibilityIdentifier(
                                "atelier.target.region.\(region.id).toggle")
                        } else {
                            Text(app.t("target", "目標"))
                                .font(.system(size: 7, weight: .semibold))
                                .foregroundStyle(Theme.sel)
                        }
                    }
                }
            }

            if target.occlusionHoleCount > 0 {
                Label(app.t(
                    "Removed occluders opened \(target.occlusionHoleCount) unknown surface(s); \(target.proposedCompletionCount) AI completion(s) remain PROPOSED.",
                    "遮蔽物の除去で未知面が\(target.occlusionHoleCount)件開き、AI補完\(target.proposedCompletionCount)件はPROPOSEDのままです。"),
                      systemImage: "wand.and.stars")
                    .font(.system(size: 8))
                    .foregroundStyle(Theme.warn)
            }
            ForEach(target.reviewCodes, id: \.self) { code in
                Text(code)
                    .font(.system(size: 7, design: .monospaced))
                    .foregroundStyle(Theme.warn)
            }
            HStack(spacing: 6) {
                Button(factory.targetCleanupConfirmed
                       ? app.t("Target selected", "この目標を選択済み")
                       : app.t("Use this as the comparison target",
                               "この状態を比較目標にする")) {
                    factory.confirmTargetCleanup()
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .disabled(factory.targetCleanupConfirmed)
                Text(String(target.targetDigest.prefix(10)))
                    .font(.system(size: 6.8, design: .monospaced))
                    .foregroundStyle(Theme.faint)
            }
        }
        .padding(8)
        .background(Theme.sel.opacity(0.055),
                    in: RoundedRectangle(cornerRadius: 7))
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("atelier.beginner.target-reconstruction")
    }

    private var factoryVisibleFrontInventoryCard: some View {
        VStack(alignment: .leading, spacing: 5) {
            Label(app.t("Visible-front target inventory · AI proposal",
                        "正面の可視部品台帳 · AI提案"),
                  systemImage: "square.3.layers.3d")
                .font(.system(size: 8.5, weight: .semibold))
                .foregroundStyle(Theme.sel)
            Text(app.t(
                "Fixed before 3D generation and used as the same-camera reprojection target. It does not assert the back, material identity, or sewing method.",
                "3D生成前に保持し、同一カメラ再投影の目標にします。背面・素材の正体・縫い方を事実とはしません。"))
                .font(.system(size: 8))
                .foregroundStyle(Theme.dim)
                .fixedSize(horizontal: false, vertical: true)
            ForEach(factory.visibleFrontInventory) { item in
                HStack(alignment: .top, spacing: 5) {
                    Text("L\(item.layer)")
                        .font(.system(size: 7, design: .monospaced))
                        .foregroundStyle(Theme.faint)
                    VStack(alignment: .leading, spacing: 1) {
                        Text([item.visibleColor, item.label]
                            .compactMap { $0 }.joined(separator: " · "))
                            .font(.system(size: 8.5, weight: .medium))
                            .foregroundStyle(Theme.fg)
                        Text("\(item.sourceKind) → \(item.normalizedKind) · \(item.garmentUnit)" +
                             (item.side.map { " · \($0)" } ?? ""))
                            .font(.system(size: 7.2, design: .monospaced))
                            .foregroundStyle(Theme.faint)
                        Text(item.visibleBasis)
                            .font(.system(size: 7.5))
                            .foregroundStyle(Theme.dim)
                            .lineLimit(2)
                    }
                }
            }
            if factory.visibleFrontInventoryAuditRequired {
                Button(app.t(
                    "Confirm visible garments and layers",
                    "正面の衣服数・重なり・部品を確認")) {
                    Task { @MainActor in
                        _ = await factory.confirmVisibleFrontInventoryAudit()
                    }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .disabled(factory.busy)
                .accessibilityIdentifier(
                    "atelier.beginner.confirm-visible-front-inventory")
                .accessibilityHint(app.t(
                    "Confirms only what is visible from the front. The rear, material identity, measurements, and sewing remain proposed.",
                    "正面で見える内容だけを確認します。背面・素材の正体・寸法・縫製は推測のままです。"))
            } else if factory.visibleFrontInventoryAuditConfirmed &&
                        !factory.targetCleanupConfirmed {
                Label(app.t(
                    "Visible inventory confirmed — finish the 3D cleanup target",
                    "可視部品を確認済み — 融合3Dの削除編集を採用してください"),
                      systemImage: "checkmark.circle")
                    .font(.system(size: 8, weight: .semibold))
                    .foregroundStyle(Theme.ok)
            }
        }
        .padding(7)
        .background(Theme.sel.opacity(0.07),
                    in: RoundedRectangle(cornerRadius: 6))
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("atelier.beginner.visible-front-inventory")
        .accessibilityLabel(app.t(
            "AI-proposed visible-front target inventory",
            "AI提案の正面可視部品台帳"))
    }

    private func designRequirementReviewText(_ item: [String: Any]) -> String {
        var parts: [String] = []
        if let text = firstString(item, keys: ["requested_text", "text", "label"]) {
            parts.append(text)
        }
        if let target = firstString(item, keys: ["target"]) {
            parts.append(target)
        } else if let targets = item["targets"] as? [String], !targets.isEmpty {
            parts.append(targets.joined(separator: ", "))
        }
        if let value = numberString(item["value_cm"]) {
            parts.append("\(value) cm")
        } else if let value = numberString(item["value"]) {
            let unit = firstString(item, keys: ["unit"]) ?? ""
            parts.append(unit.isEmpty ? value : "\(value) \(unit)")
        }
        if let code = firstString(item, keys: ["code"]) {
            parts.append(code)
        }
        if let why = firstString(item, keys: ["why"]) {
            parts.append(why)
        }
        return parts.isEmpty ? "REVIEW · REQUESTED_NOT_MEASURED"
            : parts.joined(separator: " · ")
    }

    private func firstString(_ item: [String: Any], keys: [String]) -> String? {
        for key in keys {
            if let value = item[key] as? String,
               !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                return value
            }
        }
        return nil
    }

    private func numberString(_ value: Any?) -> String? {
        guard let number = value as? NSNumber else { return nil }
        let double = number.doubleValue
        return double.rounded() == double
            ? String(Int(double)) : String(format: "%.2f", double)
    }

    private func candidateControlIdentifier(
        _ focus: CandidateControlFocus
    ) -> String {
        "atelier.beginner.candidate.\(focus.domain).\(focus.candidateID).\(focus.action.rawValue)"
    }

    private func candidateFocusOrder(
        _ candidates: [GarmentFactoryReactController.Candidate],
        material: Bool
    ) -> [CandidateControlFocus] {
        let domain = material ? "material" : "structure"
        return candidates.flatMap { candidate in
            let adopt = CandidateControlFocus(
                domain: domain, candidateID: candidate.id, action: .adopt)
            guard !material else { return [adopt] }
            return [CandidateControlFocus(
                domain: domain, candidateID: candidate.id, action: .preview),
                    adopt]
        }
    }

    private func moveCandidateFocus(
        for press: KeyPress,
        candidates: [GarmentFactoryReactController.Candidate],
        material: Bool
    ) -> KeyPress.Result {
        guard press.key == .tab else { return .ignored }
        let order = candidateFocusOrder(candidates, material: material)
        guard !order.isEmpty else { return .ignored }
        let backwards = press.modifiers.contains(.shift)
        if let current = candidateControlFocus,
           let index = order.firstIndex(of: current) {
            let next = backwards ? index - 1 : index + 1
            if order.indices.contains(next) {
                candidateControlFocus = order[next]
            } else {
                candidateControlFocus = nil
                focused = true
            }
        } else {
            focused = false
            candidateControlFocus = backwards ? order.last : order.first
        }
        return .handled
    }

    private func moveFromComposerToCandidate(for press: KeyPress) -> KeyPress.Result {
        guard press.key == .tab else { return .ignored }
        let phase = factory.lastReport?.phase ?? factory.phase
        if ["BACK_CANDIDATES_READY", "STRUCTURE_CANDIDATES_READY"].contains(phase),
           !factory.shapeCandidates.isEmpty {
            return moveCandidateFocus(
                for: press, candidates: factory.shapeCandidates, material: false)
        }
        if phase == "MATERIAL_CANDIDATES_READY",
           !factory.materialCandidates.isEmpty {
            return moveCandidateFocus(
                for: press, candidates: factory.materialCandidates, material: true)
        }
        return .ignored
    }

    private func factoryVisionPatternOperationCard(
        _ operations: [GarmentFactoryReactController.VisionPatternOperationStatus]
    ) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Label(app.t("AI-proposed pattern construction",
                        "AIが提案した型紙構成"),
                  systemImage: "square.and.pencil")
                .font(.system(size: 10, weight: .semibold))
                .foregroundStyle(Theme.fg)
            Text(app.t(
                "These are image-model proposals. MCP geometry validation does not make them observed or approved.",
                "画像モデル由来の提案です。MCPの幾何検証を通っても、観測事実や承認済みにはなりません。"))
                .font(.system(size: 8.5))
                .foregroundStyle(Theme.dim)
                .fixedSize(horizontal: false, vertical: true)
            ForEach(operations) { operation in
                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 5) {
                        Text(operation.kind)
                            .font(.system(size: 8.5, weight: .bold, design: .monospaced))
                        Text(operation.disposition)
                            .font(.system(size: 7, weight: .bold, design: .monospaced))
                            .foregroundStyle(operation.disposition == "REVIEW"
                                             ? Theme.warn : Theme.sel)
                        Text("· \(operation.authority)")
                            .font(.system(size: 7, design: .monospaced))
                            .foregroundStyle(Theme.faint)
                    }
                    Text("\(operation.candidateID) · \(operation.target)")
                        .font(.system(size: 8, design: .monospaced))
                        .foregroundStyle(Theme.faint)
                    Text(operation.detail)
                        .font(.system(size: 8.5))
                        .foregroundStyle(Theme.dim)
                        .lineLimit(3)
                    Text(operation.executionStatus == "NOT_EXECUTED_REVIEW"
                         ? app.t("Not executed — resolve the piece/edge in expert review.",
                                 "未実行 — 熟練者画面で裁片・辺を確定してください。")
                         : operation.executionStatus)
                        .font(.system(size: 7.5, weight: .medium, design: .monospaced))
                        .foregroundStyle(operation.executionStatus == "NOT_EXECUTED_REVIEW"
                                         ? Theme.warn : Theme.ok)
                }
                .padding(7)
                .background(Theme.panel, in: RoundedRectangle(cornerRadius: 7))
            }
        }
        .padding(8)
        .background(Theme.panel2, in: RoundedRectangle(cornerRadius: 8))
        .accessibilityElement(children: .contain)
        .accessibilityLabel(app.t("AI pattern operation proposals",
                                  "AI型紙操作の提案"))
    }

    private var factoryTraceCard: some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack {
                Label(app.t("Factory attempts", "制作ログとリトライ"),
                      systemImage: "list.bullet.rectangle")
                    .font(.system(size: 9.5, weight: .semibold))
                    .foregroundStyle(Theme.fg)
                Spacer()
                Text(app.t("latest \(min(factory.trace.count, 10))",
                           "最新 \(min(factory.trace.count, 10)) 件"))
                    .font(.system(size: 7.5, design: .monospaced))
                    .foregroundStyle(Theme.faint)
            }
            ForEach(Array(factory.trace.suffix(10))) { entry in
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text(String(format: "%02d", entry.round))
                        .font(.system(size: 7.5, design: .monospaced))
                        .foregroundStyle(Theme.faint)
                    Text(traceActor(entry.actor))
                        .font(.system(size: 7.5, weight: .semibold))
                        .foregroundStyle(entry.actor.contains("LLM") ? Theme.warn : Theme.ok)
                        .frame(width: 54, alignment: .leading)
                    Text(entry.action)
                        .font(.system(size: 8, design: .monospaced))
                        .foregroundStyle(Theme.dim)
                        .lineLimit(1)
                    Spacer(minLength: 4)
                    Text(entry.verdict)
                        .font(.system(size: 7.5, design: .monospaced))
                        .foregroundStyle(entry.verdict.hasPrefix("UNKNOWN_")
                                         ? Theme.warn : Theme.faint)
                        .lineLimit(1)
                }
            }
            Text(app.t(
                "Each retry is selected by Vera's closed transition table. The LLM may propose, but cannot choose tools, approve, or declare completion.",
                "各リトライはVeraの閉じた遷移表が選択します。LLMは提案できますが、ツール選択・承認・完成宣言はできません。"))
                .font(.system(size: 8.5))
                .foregroundStyle(Theme.faint)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(8)
        .background(Theme.panel, in: RoundedRectangle(cornerRadius: 7))
    }

    private var artifactRouteCard: some View {
        let threeDReady = canOpenThreeD
        let patternReady = canOpenPattern
        return VStack(alignment: .leading, spacing: 6) {
            Text(app.t("Outputs", "生成物を確認"))
                .font(.system(size: 9.5, weight: .semibold))
                .foregroundStyle(Theme.fg)
            HStack(spacing: 7) {
                Button {
                    openArtifact(step: "Solid", labelEN: "Open 3D dressed form",
                                 labelJA: "3Dの着装形状を開きました")
                } label: {
                    Label(app.t("3D form", "3D着装"), systemImage: "cube.transparent")
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .disabled(!threeDReady)

                Button {
                    openArtifact(step: "Pattern", labelEN: "Open flat pattern",
                                 labelJA: "平面型紙を開きました")
                } label: {
                    Label(app.t("Pattern", "型紙"), systemImage: "scissors")
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .disabled(!patternReady)
            }
            if !threeDReady || !patternReady {
                Text(app.t(
                    "These links become available only after the corresponding artifact exists.",
                    "対応する生成物ができた段階で導線が有効になります。"))
                    .font(.system(size: 8.5))
                    .foregroundStyle(Theme.faint)
            }
        }
    }

    private func factoryArtifactPreview(
        _ artifact: GarmentFactoryReactController.PreviewArtifact
    ) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack {
                Label(app.t("Automatic proposed preview", "自動生成した未確定プレビュー"),
                      systemImage: "cube.transparent")
                    .font(.system(size: 9.5, weight: .semibold))
                Spacer()
                Text("PROPOSED · retry \(artifact.attempt)/\(factory.previewAttempts)")
                    .font(.system(size: 7.5, design: .monospaced))
                    .foregroundStyle(Theme.warn)
            }
            HStack(alignment: .top, spacing: 7) {
                VStack(alignment: .leading, spacing: 4) {
                    Label(app.t("3D form", "3D着装"),
                          systemImage: "cube.transparent")
                        .font(.system(size: 8.5, weight: .semibold))
                    if artifact.points.contains(where: { $0.count >= 3 }) {
                        FactoryProposedDressedSceneView(points: artifact.points,
                                                        edges: artifact.edges,
                                                        faces: artifact.faces,
                                                        manufacturingPreview:
                                                            factory.candidateManufacturingPreview,
                                                        fallbackPieces: artifact.pieces,
                                                        avatarProfile:
                                                            factory.selectedBaseAvatar,
                                                        preservesSourceFront:
                                                            artifact.preservesSourceFront)
                            .frame(height: 220)
                            .clipShape(RoundedRectangle(cornerRadius: 7))
                    } else {
                        factoryArtifactPlaceholder("UNKNOWN_NO_PREVIEW_POINTS",
                                                   icon: "cube.transparent")
                    }
                }
                .frame(maxWidth: .infinity)

                VStack(alignment: .leading, spacing: 4) {
                    Label(app.t("Flat pattern", "平面型紙"),
                          systemImage: "scissors")
                        .font(.system(size: 8.5, weight: .semibold))
                    if artifact.pieces.contains(where: { $0.outline.count >= 3 }) {
                        FactoryFlatPatternPreview(pieces: artifact.pieces)
                            .frame(height: 138)
                    } else {
                        factoryArtifactPlaceholder("UNKNOWN_NO_PREVIEW_PIECES",
                                                   icon: "scissors")
                    }
                }
                .frame(maxWidth: .infinity)
            }
            Text(artifact.repairSummary)
                .font(.system(size: 8.5, weight: .semibold))
                .foregroundStyle(Theme.ok)
            Text(artifact.method)
                .font(.system(size: 7.5, design: .monospaced))
                .foregroundStyle(Theme.faint)
            ForEach(Array(artifact.assumptions.prefix(3)), id: \.self) { assumption in
                Label(assumption, systemImage: "exclamationmark.triangle")
                    .font(.system(size: 8.5))
                    .foregroundStyle(Theme.warn)
            }
            Text(app.t(
                "Viewing this PROPOSED artifact does not approve its back, material, pattern, or repair.",
                "このPROPOSED生成物を表示しても、背面・素材・型紙・修復結果は承認されません。"))
                .font(.system(size: 8))
                .foregroundStyle(Theme.faint)
        }
        .padding(8)
        .background(Theme.panel, in: RoundedRectangle(cornerRadius: 7))
    }

    private func factoryArtifactPlaceholder(_ text: String,
                                            icon: String) -> some View {
        VStack(spacing: 5) {
            Image(systemName: icon).foregroundStyle(Theme.faint)
            Text(text)
                .font(.system(size: 7, design: .monospaced))
                .foregroundStyle(Theme.faint)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, minHeight: 220)
        .background(Theme.panel2, in: RoundedRectangle(cornerRadius: 7))
    }

    private func evidenceBadge(_ text: String, color: Color) -> some View {
        Text(text)
            .font(.system(size: 7.5, weight: .semibold, design: .monospaced))
            .foregroundStyle(color)
            .padding(.horizontal, 5).padding(.vertical, 3)
            .background(color.opacity(0.10), in: Capsule())
    }

    private func factoryStageTitle(_ phase: String) -> String {
        switch phase {
        case "EMPTY":
            return app.t("Waiting for a confirmed photo", "服領域を確認した写真を待っています")
        case "REGIONS_CONFIRMED":
            return app.t("Finding similar parts and construction", "類似部位と構造を検索しています")
        case "RETRIEVAL_READY":
            return app.t("Composing structural hypotheses", "検索結果から構造候補を組み立てています")
        case "BACK_CANDIDATES_READY", "STRUCTURE_CANDIDATES_READY":
            return app.t("Waiting for your structure choice", "背面・構造候補の選択を待っています")
        case "STRUCTURE_APPROVED":
            return app.t("Generating the base pattern", "基礎型紙を生成しています")
        case "PATTERN_READY":
            return app.t("Checking and repairing sewability", "縫製可能性を検査・修復しています")
        case "PATTERN_REPAIRED":
            return app.t("Comparing material behaviour", "素材の挙動候補を比較しています")
        case "MATERIAL_CANDIDATES_READY":
            return app.t("Waiting for your material choice", "素材候補の選択を待っています")
        case "MATERIAL_APPROVED":
            return app.t("Preparing physical simulation", "物理シミュレーションを準備しています")
        case "SIMULATION_READY", "SEWING_CANDIDATES_READY", "ITERATING":
            return app.t("Testing fit, strength, comfort, and construction",
                         "着心地・強度・快適性・縫製を反復検証しています")
        case "CONVERGED_REVIEW":
            return app.t("Ready for engineering review", "工学レビューの準備ができました")
        default:
            return phase
        }
    }

    private func factoryStageIndex(_ phase: String) -> Int {
        switch phase {
        case "EMPTY": return 0
        case "REGIONS_CONFIRMED": return 1
        case "RETRIEVAL_READY", "BACK_CANDIDATES_READY",
             "STRUCTURE_CANDIDATES_READY", "STRUCTURE_APPROVED": return 2
        case "PATTERN_READY", "PATTERN_REPAIRED": return 3
        case "MATERIAL_CANDIDATES_READY", "MATERIAL_APPROVED": return 4
        case "SIMULATION_READY", "SEWING_CANDIDATES_READY", "ITERATING",
             "CONVERGED_REVIEW": return 5
        default: return 0
        }
    }

    private func isInferencePhase(_ phase: String) -> Bool {
        ["RETRIEVAL_READY", "BACK_CANDIDATES_READY",
         "STRUCTURE_CANDIDATES_READY", "PATTERN_REPAIRED",
         "MATERIAL_CANDIDATES_READY"].contains(phase)
    }

    private func traceActor(_ actor: String) -> String {
        if actor.contains("LLM") { return "AI提案" }
        if actor.contains("ENGINE") { return "Engine" }
        return "Vera"
    }

    private var canOpenThreeD: Bool {
        if let artifact = factory.previewArtifact,
           artifact.points.contains(where: { $0.count >= 3 }) { return true }
        if job.pendingPreview?.after.mesh?.isRenderable == true
            || job.activeSnapshot.mesh?.isRenderable == true { return true }
        return false
    }

    private var canOpenPattern: Bool {
        if factory.previewArtifact?.pieces.contains(where: {
            $0.outline.count >= 3
        }) == true { return true }
        if let state = job.pendingPreview?.after.state ?? job.activeSnapshot.state {
            switch state {
            case .shapeApproved, .patternValidated, .sewingBlockedNoCorpus, .complete:
                return true
            default:
                break
            }
        }
        return false
    }

    private func openArtifact(step: String, labelEN: String, labelJA: String) {
        AtelierNavigator.shared.go(to: step)
        append(.navigation, app.t(labelEN, labelJA))
    }

    private func approveFactoryCandidate(
        _ candidate: GarmentFactoryReactController.Candidate,
        material: Bool
    ) {
        resolving = true
        Task {
            let resolution = await AtelierChatRouter.approveFactoryCandidate(
                candidate, material: material)
            resolving = false
            handle(resolution)
        }
    }

    // MARK: - Transcript

    private var transcript: some View {
        ScrollViewReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    if conversation.entries.isEmpty {
                        Text(app.t(
                            "Attach a garment photo, then say “make this garment”. The production cards show what Vera is doing, every retry, and which parts are AI hypotheses. Nothing is approved until you choose it.",
                            "服の写真を添付して「この服を作って」と送ってください。制作カードにはVeraの工程、各リトライ、AI推測の範囲が表示されます。あなたが選ぶまで候補は承認されません。"))
                            .font(.system(size: 11))
                            .foregroundStyle(Theme.faint)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    ForEach(conversation.entries) { line in
                        lineView(line).id(line.id)
                    }
                    if resolving {
                        HStack(spacing: 5) {
                            ProgressView().controlSize(.small)
                            Text(app.t("resolving…", "解決中…"))
                                .font(.system(size: 10)).foregroundStyle(Theme.faint)
                        }
                    }
                }
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .onChange(of: conversation.entries.count) { _, _ in
                guard let last = conversation.entries.last?.id else { return }
                withAnimation(.easeOut(duration: 0.15)) {
                    proxy.scrollTo(last, anchor: .bottom)
                }
            }
        }
    }

    @ViewBuilder
    private func lineView(_ line: AtelierConversationContext.Entry) -> some View {
        switch line.role {
        case .user:
            Text(line.text)
                .font(.system(size: 11))
                .foregroundStyle(Theme.fg)
                .padding(.horizontal, 9).padding(.vertical, 6)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Theme.panel2, in: RoundedRectangle(cornerRadius: 7))
        case .navigation:
            // **見出しではなく答え。** 動いた理由を一行で言う — 説明なく
            // 変わる画面はバグに見える、という owner の言葉のとおり。
            HStack(alignment: .top, spacing: 5) {
                Image(systemName: "arrow.turn.down.right")
                    .font(.system(size: 9, weight: .bold))
                Text(line.text).font(.system(size: 11, weight: .semibold))
            }
            .foregroundStyle(Theme.sel)
        case .assistant:
            Text(line.text)
                .font(.system(size: 10.5))
                .foregroundStyle(Theme.ok)
                .fixedSize(horizontal: false, vertical: true)
        case .refusal:
            Text(line.text)
                .font(.system(size: 10.5))
                .foregroundStyle(Theme.warn)
        case .system:
            Text(line.text)
                .font(.system(size: 10.5))
                .foregroundStyle(Theme.faint)
        }
    }

    // MARK: - Pending deterministic preview

    private func pendingPreviewCard(_ preview: GarmentPreview) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Label(app.t("Preview — not committed", "プレビュー — 未反映"),
                          systemImage: "eye")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(Theme.warn)
                    Spacer()
                    Text(String(preview.digest.prefix(12)))
                        .font(.system(size: 8.5, design: .monospaced))
                        .foregroundStyle(Theme.faint)
                        .textSelection(.enabled)
                }

                GarmentSimulationPreview(before: preview.before.mesh,
                                         after: preview.after.mesh)

                if !preview.changedAddresses.isEmpty {
                    Text(preview.changedAddresses.joined(separator: " · "))
                        .font(.system(size: 8.5, design: .monospaced))
                        .foregroundStyle(Theme.faint)
                        .lineLimit(3)
                }
                HStack(spacing: 8) {
                    Button(app.t("Approve", "承認")) { approve(preview.digest) }
                        .buttonStyle(.borderedProminent)
                        .controlSize(.small)
                        .disabled(resolving)
                    Button(app.t("Reject", "却下")) { reject(preview.digest) }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                        .disabled(resolving)
                    Spacer()
                }
            }
            .padding(10)
        }
        .frame(maxHeight: 300)
        .background(Theme.panel)
    }

    // MARK: - Input

    @ViewBuilder
    private var selectedPhotoStrip: some View {
        if let clip = intake.selectedClip {
            HStack(spacing: 8) {
                if let image = NSImage(contentsOfFile: clip.path) {
                    Image(nsImage: image)
                        .resizable()
                        .scaledToFill()
                        .frame(width: 38, height: 38)
                        .clipShape(RoundedRectangle(cornerRadius: 6))
                } else {
                    Image(systemName: "photo")
                        .frame(width: 38, height: 38)
                        .background(Theme.panel2, in: RoundedRectangle(cornerRadius: 6))
                }
                VStack(alignment: .leading, spacing: 2) {
                    Text(URL(fileURLWithPath: clip.path).lastPathComponent)
                        .font(.system(size: 9.5, weight: .semibold))
                        .foregroundStyle(Theme.fg)
                        .lineLimit(1)
                    Text(intake.confirmedOutlineImagePath == clip.path
                         && intake.confirmedOutlineSelectionRevision
                            == intake.selectionRevision
                         ? app.t("Clothing region confirmed", "服領域を確認済み")
                         : app.t("Clothing region still needs confirmation",
                                 "服領域の確認が必要です"))
                        .font(.system(size: 8.5))
                        .foregroundStyle(intake.confirmedOutlineImagePath == clip.path
                                         && intake.confirmedOutlineSelectionRevision
                                            == intake.selectionRevision
                                         ? Theme.ok : Theme.warn)
                }
                Spacer(minLength: 4)
                Button(app.t("Change", "変更"), action: attachPhoto)
                    .buttonStyle(.plain)
                    .font(.system(size: 9))
                    .foregroundStyle(Theme.sel)
                    .disabled(resolving || intake.busy)
            }
            .padding(.horizontal, 10).padding(.top, 8)
            .frame(maxWidth: 320)
            .frame(maxWidth: .infinity)
        }
    }

    private var inputRow: some View {
        VStack(spacing: 7) {
            HStack(spacing: 8) {
                Button(action: attachPhoto) {
                    Image(systemName: "photo.badge.plus")
                        .font(.system(size: 15))
                }
                .buttonStyle(.plain)
                .foregroundStyle(Theme.sel)
                .disabled(resolving || intake.busy)
                .help(app.t("Attach a garment photo", "服の写真を追加"))

                TextField(app.t("Attach a photo and say “make this garment”…",
                                "写真を添付して「この服を作って」…"),
                          text: $input)
                    .textFieldStyle(.plain)
                    .font(.system(size: 12))
                    .padding(.horizontal, 9).padding(.vertical, 6)
                    .background(Theme.panel2, in: RoundedRectangle(cornerRadius: 7))
                    .focused($focused)
                    .onKeyPress(phases: .down) { press in
                        moveFromComposerToCandidate(for: press)
                    }
                    .onSubmit(send)
                Button(action: send) {
                    Image(systemName: "arrow.up.circle.fill").font(.system(size: 20))
                }
                .buttonStyle(.plain)
                .foregroundStyle(canSend ? Theme.sel : Theme.faint)
                .disabled(!canSend)
            }
            .frame(maxWidth: 320)
            if job.canUndo {
                HStack {
                    Button(action: undo) {
                        Label(app.t("Undo approved change", "承認済み変更を戻す"),
                              systemImage: "arrow.uturn.backward")
                    }
                    .buttonStyle(.plain)
                    .font(.system(size: 9.5))
                    .foregroundStyle(Theme.dim)
                    .disabled(resolving)
                    Spacer()
                }
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity)
    }

    private var canSend: Bool {
        !input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !resolving
    }

    private var contextCharacterBudget: Int {
        let configured = app.contextWindowOverride
        if configured >= 999_999 { return Int.max / 4 }
        if configured > 0 { return configured * 4 }
        return ModelProfileDetector.detect(modelId: app.effectiveModelName)
            .tier.compressThreshold
    }

    private func append(_ role: AtelierConversationContext.Role, _ text: String) {
        conversation.append(role, text, characterBudget: contextCharacterBudget)
    }

    private func attachPhoto() {
        resolving = true
        Task {
            await intake.pickAndIngest()
            if intake.selectedClip != nil,
               input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                input = app.t("Make this garment", "この服を作って")
            }
            resolving = false
            focused = true
        }
    }

    private func send() {
        let text = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        input = ""
        append(.user, text)
        resolving = true
        Task {
            let resolution = await AtelierChatRouter.resolveFlexible(text)
            resolving = false
            handle(resolution)
        }
    }

    private func approve(_ digest: String) {
        resolving = true
        Task {
            let resolution = await AtelierChatRouter.approvePending(digest: digest)
            resolving = false
            handle(resolution)
        }
    }

    private func reject(_ digest: String) {
        resolving = true
        Task {
            let resolution = await AtelierChatRouter.rejectPending(digest: digest)
            resolving = false
            handle(resolution)
        }
    }

    private func undo() {
        resolving = true
        Task {
            let resolution = await AtelierChatRouter.undoLast()
            resolving = false
            handle(resolution)
        }
    }

    private func handle(_ resolution: AtelierChatRouter.Resolution) {
        switch resolution {
        case .modelGenerated(let text, let action):
            append(.assistant,
                   "制作モデルの提案（AI生成・未検証）\n"
                   + "以下は作業計画であり、生成結果ではありません。\n\(text)")
            if let action { handle(action) }
        case .moved(let destination):
            move(destination)
        case .preview(let preview, let destination):
            if let destination { move(destination) }
            append(.assistant, app.t(
                "Preview ready; active garment unchanged. digest \(preview.digest.prefix(12))",
                "プレビューを作成しました。現在の服は未変更です。digest \(preview.digest.prefix(12))"))
        case .answered(let answer, let destination):
            if let destination { move(destination) }
            append(.assistant, answer.deterministicText)
        case .factory(let report, let destination):
            if let destination { move(destination) }
            append(report.verdict.hasPrefix("UNKNOWN_") ? .refusal : .assistant,
                   AtelierChatRouter.transcriptText(
                    for: .factory(report, nil)))
        case .refused(let why):
            append(.refusal, why)
        case .none:
            append(.system, app.t(
                "No matching place or typed command — staying on \(ctx.step).",
                "対応する場所または型付き命令が見つからず、\(ctx.step) のままです。"))
        }
    }

    private func move(_ destination: AtelierChatRouter.Destination) {
        // Destination is already resolved against an engine address or the
        // literal step list. Never assign the mirror `ctx.step` directly.
        AtelierNavigator.shared.go(to: destination.step)
        append(.navigation, app.t(destination.reasonEN, destination.reasonJA))
    }
}

/// Typed presentation metadata copied from the candidate manufacturing sheet.
/// It is never reconstructed from an image name.  Scene nodes retain these
/// values so separately proposed layers do not collapse into an anonymous mesh.
struct FactoryGarmentLayerDescriptor: Identifiable {
    let id: String
    let pieceID: String
    let sourceNodeID: String
    let role: String
    let primitiveKind: String
    let side: String
    let layer: Int
    let proposedColor: String?

    static func parse(
        manufacturingPreview: [String: Any]?,
        fallbackPieces: [GarmentFactoryReactController.PreviewPiece]
    ) -> [FactoryGarmentLayerDescriptor] {
        let rows = manufacturingPreview?["pieces"] as? [[String: Any]] ?? []
        if rows.isEmpty {
            return fallbackPieces.enumerated().map { index, piece in
                FactoryGarmentLayerDescriptor(
                    id: "fallback:\(piece.id)", pieceID: piece.id,
                    sourceNodeID: piece.id, role: piece.name,
                    primitiveKind: "UNKNOWN", side: "unknown", layer: index,
                    proposedColor: nil)
            }
        }
        return rows.enumerated().map { index, row in
            let attributes = row["attributes"] as? [String: Any] ?? [:]
            let pieceID = text(row["piece_id"]) ?? "piece-\(index)"
            let sourceNode = text(row["source_node_id"])
                ?? text(attributes["source_node_id"]) ?? pieceID
            return FactoryGarmentLayerDescriptor(
                id: "\(sourceNode):\(pieceID):\(index)", pieceID: pieceID,
                sourceNodeID: sourceNode,
                role: text(row["role"]) ?? text(attributes["role"])
                    ?? text(row["name"]) ?? "unknown role",
                primitiveKind: text(row["primitive_kind"])
                    ?? text(attributes["primitive_kind"]) ?? "UNKNOWN",
                side: text(row["side"]) ?? text(attributes["derived_side"])
                    ?? text(attributes["side"]) ?? "bilateral",
                layer: integer(row["layer"]) ?? integer(attributes["layer"]) ?? 0,
                proposedColor: text(row["color"]) ?? text(attributes["color"])
                    ?? text(attributes["hex_color"]))
        }
    }

    private static func text(_ value: Any?) -> String? {
        guard let value = value as? String,
              !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        else { return nil }
        return value
    }

    private static func integer(_ value: Any?) -> Int? {
        if let value = value as? Int { return value }
        if let value = value as? NSNumber { return value.intValue }
        if let value = value as? String { return Int(value) }
        return nil
    }
}

/// Read-only rendering of proposal-only candidate geometry on a neutral,
/// proportioned procedural dress form.  It is a construction preview, not a
/// single-view photogrammetry claim: back geometry remains PROPOSED, the body
/// is not a measured wearer, and no displayed fold is faithful physical drape.
struct FactoryProposedDressedSceneView: View {
    let points: [[Double]]
    let edges: [[Int]]
    let faces: [[Int]]
    let garmentLayers: [FactoryGarmentLayerDescriptor]
    let avatarProfile: GarmentFactoryReactController.BaseAvatarProfile
    let preservesSourceFront: Bool

    private static let defaultAvatar =
        GarmentFactoryReactController.BaseAvatarProfile(
            id: "preview-balanced-170", title: "170 · 92 / 76 / 98 cm",
            heightCM: 170, chestCM: 92, waistCM: 76, hipCM: 98,
            geometryDigest: "parametric-avatar-balanced-v1",
            authority: "PROPOSED_PREVIEW")

    init(points: [[Double]], edges: [[Int]], faces: [[Int]]) {
        self.points = points
        self.edges = edges
        self.faces = faces
        self.garmentLayers = []
        self.avatarProfile = Self.defaultAvatar
        self.preservesSourceFront = false
    }

    init(points: [[Double]], edges: [[Int]], faces: [[Int]],
         manufacturingPreview: [String: Any]?,
         fallbackPieces: [GarmentFactoryReactController.PreviewPiece],
         avatarProfile: GarmentFactoryReactController.BaseAvatarProfile,
         preservesSourceFront: Bool = false) {
        self.points = points
        self.edges = edges
        self.faces = faces
        self.garmentLayers = FactoryGarmentLayerDescriptor.parse(
            manufacturingPreview: manufacturingPreview,
            fallbackPieces: fallbackPieces)
        self.avatarProfile = avatarProfile
        self.preservesSourceFront = preservesSourceFront
    }

    var body: some View {
        SceneView(scene: Self.makeScene(points: points, edges: edges,
                                        faces: faces, layers: garmentLayers,
                                        avatarProfile: avatarProfile,
                                        preservesSourceFront:
                                            preservesSourceFront),
                  pointOfView: nil,
                  options: [.allowsCameraControl])
            .background(Color.black.opacity(0.18))
            .overlay(alignment: .topLeading) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("3D MANNEQUIN · PROPOSED")
                    Text("candidate mesh + procedural dress form")
                        .foregroundStyle(Theme.faint)
                }
                .font(.system(size: 7, weight: .semibold, design: .monospaced))
                .foregroundStyle(Theme.warn)
                .padding(6)
            }
            .overlay(alignment: .bottomLeading) {
                Text("UNKNOWN BACK / NOT A MEASURED WEARER / NO PHYSICAL DRAPE CLAIM")
                    .font(.system(size: 6.5, weight: .semibold,
                                  design: .monospaced))
                    .foregroundStyle(Theme.faint)
                    .padding(6)
            }
            .overlay(RoundedRectangle(cornerRadius: 7)
                .stroke(Theme.warn.opacity(0.25), lineWidth: 1))
    }

    private struct DressFormFrame {
        let centerX: Float
        let centerZ: Float
        let top: Float
        let height: Float
        let width: Float
        let chestShape: Float
        let waistShape: Float
        let hipShape: Float
        let chestDepthShape: Float
        let waistDepthShape: Float
        let hipDepthShape: Float
        let fitAuthority: String
        let fitBasis: String

        var head: Float { top - height * 0.075 }
        var neck: Float { top - height * 0.165 }
        var shoulder: Float { top - height * 0.225 }
        var chest: Float { top - height * 0.315 }
        var waist: Float { top - height * 0.435 }
        var hip: Float { top - height * 0.535 }
        var crotch: Float { top - height * 0.585 }
        var elbow: Float { top - height * 0.445 }
        var wrist: Float { top - height * 0.615 }
        var knee: Float { top - height * 0.775 }
        var ankle: Float { top - height * 0.965 }
        var floor: Float { top - height }
    }

    private struct ProfileRing {
        let y: Float
        let radiusX: Float
        let radiusZ: Float
    }

    private static func makeScene(points: [[Double]], edges: [[Int]],
                                  faces: [[Int]],
                                  layers: [FactoryGarmentLayerDescriptor],
                                  avatarProfile: GarmentFactoryReactController.BaseAvatarProfile,
                                  preservesSourceFront: Bool
    ) -> SCNScene {
        let scene = SCNScene()
        scene.background.contents = NSColor(calibratedWhite: 0.045, alpha: 1)
        let valid = Set(points.indices.filter { points[$0].count >= 3 })
        guard !valid.isEmpty else { return scene }

        let vertices = points.map { point -> SCNVector3 in
            guard point.count >= 3 else { return SCNVector3Zero }
            return SCNVector3(Float(point[0]), Float(point[1]), Float(point[2]))
        }
        let validVertices = valid.sorted().map { vertices[$0] }
        let validFaces = faces.filter {
            $0.count >= 3 && $0.allSatisfy(valid.contains)
        }
        let lineIndices: [Int32] = edges.flatMap { edge -> [Int32] in
            guard edge.count >= 2, valid.contains(edge[0]), valid.contains(edge[1])
            else { return [] }
            return [Int32(edge[0]), Int32(edge[1])]
        }
        // A failed/partial structure solve may retain a handful of distant
        // repair vertices. Framing the camera from raw extrema made the actual
        // mannequin occupy only a few pixels. Use robust proposal bounds for
        // presentation while retaining every source vertex in the scene.
        let (garmentMinimum, garmentMaximum) = robustProposalBounds(
            validVertices)
        let frame = dressFormFrame(minimum: garmentMinimum, maximum: garmentMaximum,
                                   avatarProfile: avatarProfile)
        let root = SCNNode()
        root.name = "proposal-dressed-form-root"
        root.addChildNode(mannequinNode(minimum: garmentMinimum,
                                       maximum: garmentMaximum,
                                       avatarProfile: avatarProfile))

        // Disconnected surfaces remain the strongest geometry-grounded signal
        // available for candidate layers. This is a visual proposal, never material identification.
        // A front image does not establish that any proposed back face was observed.
        let palette: [NSColor] = fashionPalette
        let components = faceComponents(validFaces)
        let source = SCNGeometrySource(vertices: vertices)
        for (componentIndex, component) in components.enumerated() {
            let indices: [Int32] = component.flatMap { face in
                (1..<(face.count - 1)).flatMap { index in
                    [Int32(face[0]), Int32(face[index]), Int32(face[index + 1])]
                }
            }
            guard !indices.isEmpty else { continue }
            let descriptor = layers.indices.contains(componentIndex)
                ? layers[componentIndex] : nil
            let element = SCNGeometryElement(indices: indices,
                                             primitiveType: .triangles)
            let geometry = SCNGeometry(sources: [source], elements: [element])
            let color = proposedColor(for: descriptor,
                                      fallbackIndex: componentIndex,
                                      palette: palette)
            let surface = garmentMaterial(color: color, layer: descriptor?.layer ?? 0,
                                          opacity: 0.92)
            surface.lightingModel = .physicallyBased
            geometry.materials = [surface]
            let surfaceNode = SCNNode(geometry: geometry)
            bindProposalIdentity(surfaceNode, descriptor: descriptor,
                                 componentIndex: componentIndex,
                                 allLayers: layers,
                                 binding: descriptor == nil
                                    ? "PROPOSED_COMPONENT_GROUP"
                                    : "PROPOSED_COMPONENT_ORDER")
            root.addChildNode(surfaceNode)
        }

        // Candidate pattern metadata can contain more semantic layers than a
        // connected simulation surface.  Add a conservative, generic proxy
        // for every typed source node so ownership and layer ordering remain
        // inspectable instead of being flattened into one anonymous shell.
        if !preservesSourceFront {
            for (index, descriptor) in layers.enumerated() {
                let color = proposedColor(for: descriptor, fallbackIndex: index,
                                          palette: palette)
                for proxy in garmentProxyNodes(for: descriptor, frame: frame,
                                               color: color) {
                    bindProposalIdentity(proxy, descriptor: descriptor,
                                         componentIndex: index, allLayers: layers,
                                         binding: "PROPOSED_TYPED_PROXY")
                    root.addChildNode(proxy)
                }
            }
        }

        if !lineIndices.isEmpty {
            let element = SCNGeometryElement(indices: lineIndices,
                                             primitiveType: .line)
            let geometry = SCNGeometry(sources: [source], elements: [element])
            let wire = SCNMaterial()
            wire.diffuse.contents = NSColor.white.withAlphaComponent(
                validFaces.isEmpty ? 0.66 : 0.16)
            wire.emission.contents = NSColor.systemTeal.withAlphaComponent(0.10)
            wire.lightingModel = .constant
            wire.isDoubleSided = true
            geometry.materials = [wire]
            let node = SCNNode(geometry: geometry)
            node.name = "proposal-source-seam-lines"
            root.addChildNode(node)
        }
        if validFaces.isEmpty && lineIndices.isEmpty {
            let element = SCNGeometryElement(
                indices: valid.sorted().map(Int32.init), primitiveType: .point)
            element.pointSize = 3
            element.minimumPointScreenSpaceRadius = 1
            element.maximumPointScreenSpaceRadius = 5
            let geometry = SCNGeometry(sources: [source], elements: [element])
            let pointMaterial = SCNMaterial()
            pointMaterial.diffuse.contents = NSColor.systemTeal
            pointMaterial.lightingModel = .constant
            geometry.materials = [pointMaterial]
            root.addChildNode(SCNNode(geometry: geometry))
        }

        scene.rootNode.addChildNode(root)
        addStudioFloor(to: scene, frame: frame)
        frameCameraAndLights(scene: scene, frame: frame)
        return scene
    }

    private static func robustProposalBounds(
        _ vertices: [SCNVector3]
    ) -> (SCNVector3, SCNVector3) {
        func quantile(_ values: [CGFloat], _ fraction: Double) -> CGFloat {
            let sorted = values.sorted()
            guard !sorted.isEmpty else { return 0 }
            let raw = Double(sorted.count - 1) * fraction
            return sorted[max(0, min(sorted.count - 1, Int(raw.rounded())))]
        }
        guard vertices.count >= 20 else {
            return (
                SCNVector3(vertices.map(\.x).min() ?? 0,
                           vertices.map(\.y).min() ?? 0,
                           vertices.map(\.z).min() ?? 0),
                SCNVector3(vertices.map(\.x).max() ?? 1,
                           vertices.map(\.y).max() ?? 1,
                           vertices.map(\.z).max() ?? 1))
        }
        let lower = 0.03
        let upper = 0.97
        var minimum = SCNVector3(
            quantile(vertices.map(\.x), lower),
            quantile(vertices.map(\.y), lower),
            quantile(vertices.map(\.z), lower))
        var maximum = SCNVector3(
            quantile(vertices.map(\.x), upper),
            quantile(vertices.map(\.y), upper),
            quantile(vertices.map(\.z), upper))
        if maximum.x - minimum.x < 0.1 {
            minimum.x -= 0.05; maximum.x += 0.05
        }
        if maximum.y - minimum.y < 0.1 {
            minimum.y -= 0.05; maximum.y += 0.05
        }
        if maximum.z - minimum.z < 0.1 {
            minimum.z -= 0.05; maximum.z += 0.05
        }
        return (minimum, maximum)
    }

    private static func dressFormFrame(minimum: SCNVector3,
                                       maximum: SCNVector3,
                                       avatarProfile:
                                           GarmentFactoryReactController.BaseAvatarProfile
    ) -> DressFormFrame {
        let minX = Float(minimum.x), maxX = Float(maximum.x)
        let minY = Float(minimum.y), maxY = Float(maximum.y)
        let minZ = Float(minimum.z), maxZ = Float(maximum.z)
        let garmentHeight: Float = max(maxY - minY, 0.1)
        let garmentWidth: Float = max(maxX - minX, garmentHeight * 0.2)
        let heightScale = Float(avatarProfile.heightCM / 170.0)
        let circumferenceScale = Float(max(
            avatarProfile.chestCM / 92.0, avatarProfile.hipCM / 98.0))
        let bodyHeight = max(garmentHeight * 1.20 * heightScale,
                             garmentWidth * 2.55)
        let bodyWidth = min(max(garmentWidth * 0.67 * circumferenceScale,
                                bodyHeight * 0.19),
                            bodyHeight * 0.30)
        let centerX: Float = (minX + maxX) * 0.5
        let centerZ: Float = (minZ + maxZ) * 0.5 - bodyHeight * 0.018
        let top: Float = maxY + bodyHeight * 0.125
        return DressFormFrame(
            centerX: centerX, centerZ: centerZ, top: top,
            height: bodyHeight, width: bodyWidth,
            chestShape: Float(avatarProfile.chestCM / 92.0) / circumferenceScale,
            waistShape: Float(avatarProfile.waistCM / 76.0) / circumferenceScale,
            hipShape: Float(avatarProfile.hipCM / 98.0) / circumferenceScale,
            chestDepthShape: Float(avatarProfile.chestCM / 92.0)
                / circumferenceScale,
            waistDepthShape: Float(avatarProfile.waistCM / 76.0)
                / circumferenceScale,
            hipDepthShape: Float(avatarProfile.hipCM / 98.0)
                / circumferenceScale,
            fitAuthority: "PROPOSED_GEOMETRY_BOUNDS_FIT",
            fitBasis: "CANDIDATE_GEOMETRY_BOUNDS")
    }

    /// Fit only the cleanup mannequin's *display proportions* to the complete
    /// fused subject. The selected centimetre values remain requested/selected
    /// design inputs: the photograph supplies no metric scale. Front widths
    /// use a symmetric envelope around the subject axis so a one-sided train,
    /// wrap or overskirt cannot widen the procedural body on its own.
    private static func proposedImageProportionFrame(
        vertices: [SCNVector3],
        avatarProfile: GarmentFactoryReactController.BaseAvatarProfile
    ) -> DressFormFrame {
        let (minimum, maximum) = robustProposalBounds(vertices)
        let floor = Float(minimum.y)
        let top = Float(maximum.y)
        let height = max(top - floor, 0.1)

        struct Envelope {
            let lower: Float
            let upper: Float
            var center: Float { (lower + upper) * 0.5 }
            var width: Float { max(upper - lower, 0.001) }
        }
        func quantile(_ values: [Float], _ fraction: Float) -> Float {
            let sorted = values.sorted()
            guard !sorted.isEmpty else { return 0 }
            let raw = Float(sorted.count - 1) * fraction
            return sorted[max(0, min(sorted.count - 1,
                                     Int(raw.rounded())))]
        }
        func envelope(_ range: ClosedRange<Float>) -> Envelope? {
            let xs = vertices.compactMap { vertex -> Float? in
                let down = (top - Float(vertex.y)) / height
                return range.contains(down) ? Float(vertex.x) : nil
            }
            guard xs.count >= 4 else { return nil }
            let lower = quantile(xs, 0.04)
            let upper = quantile(xs, 0.96)
            return upper > lower ? Envelope(lower: lower, upper: upper) : nil
        }
        func median(_ values: [Float]) -> Float {
            quantile(values, 0.5)
        }
        func clamp(_ value: Float, _ lower: Float, _ upper: Float) -> Float {
            min(max(value, lower), upper)
        }

        let head = envelope(0.025...0.145)
        let shoulder = envelope(0.17...0.27)
        let chest = envelope(0.27...0.38)
        let waist = envelope(0.40...0.50)
        let hip = envelope(0.50...0.61)
        let centerCandidates = [head, shoulder, chest, waist]
            .compactMap { $0?.center }
        let fallbackCenter = (Float(minimum.x) + Float(maximum.x)) * 0.5
        let centerX = centerCandidates.isEmpty
            ? fallbackCenter : median(centerCandidates)

        func symmetricWidth(_ proposal: Envelope?, fallback: Float,
                            plausible: ClosedRange<Float>) -> Float {
            guard let proposal else {
                return clamp(fallback, plausible.lowerBound,
                             plausible.upperBound)
            }
            let left = max(centerX - proposal.lower, 0)
            let right = max(proposal.upper - centerX, 0)
            let symmetric = 2 * min(left, right)
            let usable = symmetric > height * 0.06 ? symmetric : proposal.width
            return clamp(usable, plausible.lowerBound, plausible.upperBound)
        }

        let fullWidth = max(Float(maximum.x) - Float(minimum.x), height * 0.2)
        let shoulderWidth = symmetricWidth(
            shoulder, fallback: fullWidth * 0.68,
            plausible: (height * 0.18)...(height * 0.36))
        let chestWidth = symmetricWidth(
            chest, fallback: shoulderWidth * 0.88,
            plausible: (height * 0.15)...(height * 0.34))
        let waistWidth = symmetricWidth(
            waist, fallback: chestWidth * 0.78,
            plausible: (height * 0.12)...(height * 0.29))
        let hipWidth = symmetricWidth(
            hip, fallback: chestWidth * 1.02,
            plausible: (height * 0.16)...(height * 0.36))
        let bodyWidth = max(shoulderWidth / 1.04, height * 0.17)
        let circumferenceScale = Float(max(
            avatarProfile.chestCM / 92.0, avatarProfile.hipCM / 98.0))
        let centerZ = (Float(minimum.z) + Float(maximum.z)) * 0.5
            - height * 0.018

        return DressFormFrame(
            centerX: centerX, centerZ: centerZ, top: top,
            height: height, width: bodyWidth,
            chestShape: clamp(chestWidth / (bodyWidth * 0.90), 0.72, 1.35),
            waistShape: clamp(waistWidth / (bodyWidth * 0.67), 0.68, 1.40),
            hipShape: clamp(hipWidth / (bodyWidth * 0.91), 0.72, 1.38),
            chestDepthShape: Float(avatarProfile.chestCM / 92.0)
                / circumferenceScale,
            waistDepthShape: Float(avatarProfile.waistCM / 76.0)
                / circumferenceScale,
            hipDepthShape: Float(avatarProfile.hipCM / 98.0)
                / circumferenceScale,
            fitAuthority: "PROPOSED_IMAGE_PROPORTION_FIT",
            fitBasis: "FUSED_SUBJECT_OUTLINE_MESH_BOUNDS")
    }

    private static func faceComponents(_ faces: [[Int]]) -> [[[Int]]] {
        guard !faces.isEmpty else { return [] }
        var byVertex: [Int: [Int]] = [:]
        for (faceIndex, face) in faces.enumerated() {
            for vertex in face { byVertex[vertex, default: []].append(faceIndex) }
        }
        var unseen = Set(faces.indices)
        var result: [[[Int]]] = []
        while let seed = unseen.first {
            var stack = [seed]
            unseen.remove(seed)
            var component: [[Int]] = []
            while let current = stack.popLast() {
                component.append(faces[current])
                for vertex in faces[current] {
                    for neighbor in byVertex[vertex] ?? [] where unseen.contains(neighbor) {
                        unseen.remove(neighbor)
                        stack.append(neighbor)
                    }
                }
            }
            result.append(component)
        }
        return result
    }

    /// Neutral articulated dress form inferred only from preview bounds.  The
    /// torso, pelvis and limbs are smooth profile meshes rather than one circle
    /// or cylinder per body part; wearer measurements still come from approved
    /// requirements, not from this display proxy.
    private static func mannequinNode(minimum: SCNVector3,
                                      maximum: SCNVector3,
                                      avatarProfile:
                                          GarmentFactoryReactController.BaseAvatarProfile
    ) -> SCNNode {
        let frame = dressFormFrame(minimum: minimum, maximum: maximum,
                                   avatarProfile: avatarProfile)
        return mannequinNode(frame: frame, avatarProfile: avatarProfile)
    }

    private static func mannequinNode(
        frame: DressFormFrame,
        avatarProfile: GarmentFactoryReactController.BaseAvatarProfile
    ) -> SCNNode {
        let node = SCNNode()
        node.name = frame.fitAuthority == "PROPOSED_IMAGE_PROPORTION_FIT"
            ? "procedural-human-proposed-image-proportion-fit"
            : "procedural-human-dress-form-not-measured"
        addTypedPreviewMetadata(to: node, fitAuthority: frame.fitAuthority,
                                fitBasis: frame.fitBasis)
        let material = dressFormMaterial()
        let w = frame.width

        addProfile(to: node, name: "head", centerX: frame.centerX,
                   centerZ: frame.centerZ, material: material, rings: [
            .init(y: frame.top - frame.height * 0.012, radiusX: w * 0.030,
                  radiusZ: w * 0.035),
            .init(y: frame.top - frame.height * 0.032, radiusX: w * 0.145,
                  radiusZ: w * 0.145),
            .init(y: frame.head, radiusX: w * 0.205, radiusZ: w * 0.185),
            .init(y: frame.top - frame.height * 0.120, radiusX: w * 0.175,
                  radiusZ: w * 0.170),
            .init(y: frame.top - frame.height * 0.145, radiusX: w * 0.075,
                  radiusZ: w * 0.090),
        ])
        addProfile(to: node, name: "neck", centerX: frame.centerX,
                   centerZ: frame.centerZ, material: material, rings: [
            .init(y: frame.top - frame.height * 0.150, radiusX: w * 0.105,
                  radiusZ: w * 0.100),
            .init(y: frame.neck, radiusX: w * 0.125, radiusZ: w * 0.115),
            .init(y: frame.top - frame.height * 0.195, radiusX: w * 0.155,
                  radiusZ: w * 0.130),
        ])
        addProfile(to: node, name: "torso", centerX: frame.centerX,
                   centerZ: frame.centerZ, material: material, rings: [
            .init(y: frame.top - frame.height * 0.195, radiusX: w * 0.22,
                  radiusZ: w * 0.17),
            .init(y: frame.shoulder, radiusX: w * 0.52, radiusZ: w * 0.22),
            .init(y: frame.chest, radiusX: w * 0.45 * frame.chestShape,
                  radiusZ: w * 0.265 * frame.chestDepthShape),
            .init(y: frame.top - frame.height * 0.375, radiusX: w * 0.38,
                  radiusZ: w * 0.235),
            .init(y: frame.waist, radiusX: w * 0.335 * frame.waistShape,
                  radiusZ: w * 0.205 * frame.waistDepthShape),
            .init(y: frame.top - frame.height * 0.485, radiusX: w * 0.40,
                  radiusZ: w * 0.235),
            .init(y: frame.hip, radiusX: w * 0.455 * frame.hipShape,
                  radiusZ: w * 0.255 * frame.hipDepthShape),
            .init(y: frame.crotch, radiusX: w * 0.31, radiusZ: w * 0.205),
        ])

        for side: Float in [-1, 1] {
            let shoulder = SIMD3<Float>(frame.centerX + side * w * 0.48,
                                        frame.shoulder - frame.height * 0.005,
                                        frame.centerZ)
            let elbow = SIMD3<Float>(frame.centerX + side * w * 0.57,
                                     frame.elbow, frame.centerZ + w * 0.008)
            let wrist = SIMD3<Float>(frame.centerX + side * w * 0.55,
                                     frame.wrist, frame.centerZ + w * 0.025)
            node.addChildNode(limbSegment(name: side < 0 ? "left-upper-arm" : "right-upper-arm",
                                          from: shoulder, to: elbow,
                                          startRadius: w * 0.105,
                                          endRadius: w * 0.078,
                                          depthScale: 0.88, material: material))
            node.addChildNode(limbSegment(name: side < 0 ? "left-forearm" : "right-forearm",
                                          from: elbow, to: wrist,
                                          startRadius: w * 0.082,
                                          endRadius: w * 0.055,
                                          depthScale: 0.86, material: material))
            addEllipsoid(to: node, name: side < 0 ? "left-hand" : "right-hand",
                         center: SIMD3<Float>(wrist.x, wrist.y - frame.height * 0.035,
                                              wrist.z + w * 0.012),
                         radii: SIMD3<Float>(w * 0.064, frame.height * 0.044,
                                             w * 0.040), material: material)

            let hip = SIMD3<Float>(frame.centerX + side * w * 0.19,
                                   frame.top - frame.height * 0.565, frame.centerZ)
            let knee = SIMD3<Float>(frame.centerX + side * w * 0.18,
                                    frame.knee, frame.centerZ + w * 0.006)
            let ankle = SIMD3<Float>(frame.centerX + side * w * 0.17,
                                     frame.ankle, frame.centerZ)
            node.addChildNode(limbSegment(name: side < 0 ? "left-thigh" : "right-thigh",
                                          from: hip, to: knee,
                                          startRadius: w * 0.17,
                                          endRadius: w * 0.11,
                                          depthScale: 0.88, material: material))
            node.addChildNode(limbSegment(name: side < 0 ? "left-calf" : "right-calf",
                                          from: knee, to: ankle,
                                          startRadius: w * 0.115,
                                          endRadius: w * 0.070,
                                          depthScale: 0.86, material: material))
            addEllipsoid(to: node, name: side < 0 ? "left-foot" : "right-foot",
                         center: SIMD3<Float>(ankle.x, frame.floor + frame.height * 0.018,
                                              frame.centerZ + w * 0.10),
                         radii: SIMD3<Float>(w * 0.105, frame.height * 0.025,
                                             w * 0.19), material: material)
        }

        // Small shoulder joint caps keep the profile continuous under sleeveless
        // candidates. They are not the old primitive torso construction.
        for side: Float in [-1, 1] {
            let cap = SCNCapsule(capRadius: CGFloat(w * 0.075),
                                 height: CGFloat(w * 0.16))
            cap.materials = [material]
            let shoulder = SCNNode(geometry: cap)
            shoulder.name = side < 0 ? "left-shoulder-joint" : "right-shoulder-joint"
            shoulder.position = SCNVector3(frame.centerX + side * w * 0.47,
                                           frame.shoulder, frame.centerZ)
            shoulder.eulerAngles.z = CGFloat(side * 0.18)
            node.addChildNode(shoulder)
        }
        // A tiny inner head core preserves SceneKit's smooth sphere normal path
        // without returning to the previous sphere-as-body display.
        let headCore = SCNSphere(radius: CGFloat(w * 0.01))
        headCore.materials = [material]
        let headCoreNode = SCNNode(geometry: headCore)
        headCoreNode.name = "head-normal-core"
        headCoreNode.position = SCNVector3(frame.centerX, frame.head, frame.centerZ)
        node.addChildNode(headCoreNode)
        return node
    }

    /// SceneKit on the submission deployment target has no `SCNNode.userData`.
    /// Keep the truth boundary as inert, name-addressable child nodes instead
    /// of KVC. They have no geometry, do not render or participate in picking,
    /// and can be inspected without promoting the visual fit to measurement.
    private static func addTypedPreviewMetadata(
        to parent: SCNNode, fitAuthority: String, fitBasis: String
    ) {
        let selectedMeasurementAuthority = "REQUESTED_OR_SELECTED"
        let singleImageMeasurementsInferred = false
        let rows = [
            "metadata.visual-fit-authority.\(fitAuthority)",
            "metadata.visual-fit-basis.\(fitBasis)",
            "metadata.selected-measurement-authority.\(selectedMeasurementAuthority)",
            "metadata.single-image-measurements-inferred.\(singleImageMeasurementsInferred)",
            "metadata.texture-convention.IMAGE_TOP_IS_TEXTURE_V_0",
        ]
        for name in rows {
            let marker = SCNNode()
            marker.name = name
            marker.categoryBitMask = 1 << 20
            parent.addChildNode(marker)
        }
    }

    private static func addProfile(to parent: SCNNode, name: String,
                                   centerX: Float, centerZ: Float,
                                   material: SCNMaterial,
                                   rings: [ProfileRing]) {
        let geometry = radialProfileGeometry(rings: rings.map {
            ProfileRing(y: $0.y, radiusX: $0.radiusX, radiusZ: $0.radiusZ)
        })
        geometry.materials = [material]
        let node = SCNNode(geometry: geometry)
        node.name = name
        node.position = SCNVector3(centerX, 0, centerZ)
        parent.addChildNode(node)
    }

    private static func addEllipsoid(to parent: SCNNode, name: String,
                                     center: SIMD3<Float>, radii: SIMD3<Float>,
                                     material: SCNMaterial) {
        let samples: [Float] = [-1, -0.82, -0.45, 0, 0.45, 0.82, 1]
        let rings = samples.map { value -> ProfileRing in
            let radial = sqrt(max(0, 1 - value * value))
            return ProfileRing(y: value * radii.y,
                               radiusX: max(radii.x * radial, radii.x * 0.025),
                               radiusZ: max(radii.z * radial, radii.z * 0.025))
        }
        let geometry = radialProfileGeometry(rings: rings)
        geometry.materials = [material]
        let node = SCNNode(geometry: geometry)
        node.name = name
        node.simdPosition = center
        parent.addChildNode(node)
    }

    private static func limbSegment(name: String, from: SIMD3<Float>,
                                    to: SIMD3<Float>, startRadius: Float,
                                    endRadius: Float, depthScale: Float,
                                    material: SCNMaterial) -> SCNNode {
        let vector = to - from
        let length = max(simd_length(vector), 0.001)
        let geometry = radialProfileGeometry(rings: [
            .init(y: -length * 0.5, radiusX: startRadius * 0.88,
                  radiusZ: startRadius * depthScale),
            .init(y: -length * 0.36, radiusX: startRadius,
                  radiusZ: startRadius * depthScale),
            .init(y: length * 0.36, radiusX: endRadius,
                  radiusZ: endRadius * depthScale),
            .init(y: length * 0.5, radiusX: endRadius * 0.88,
                  radiusZ: endRadius * depthScale),
        ], radialSegments: 22)
        geometry.materials = [material]
        let node = SCNNode(geometry: geometry)
        node.name = name
        node.simdPosition = (from + to) * 0.5
        node.simdOrientation = simd_quatf(from: SIMD3<Float>(0, 1, 0),
                                          to: simd_normalize(vector))
        return node
    }

    private static func radialProfileGeometry(rings: [ProfileRing],
                                              radialSegments: Int = 32) -> SCNGeometry {
        guard rings.count >= 2 else { return SCNGeometry() }
        var vertices: [SCNVector3] = []
        var normals: [SCNVector3] = []
        var indices: [Int32] = []
        for ring in rings {
            for segment in 0..<radialSegments {
                let angle = Float(segment) / Float(radialSegments) * Float.pi * 2
                let x = cos(angle), z = sin(angle)
                vertices.append(SCNVector3(x * ring.radiusX, ring.y,
                                           z * ring.radiusZ))
                let normal = simd_normalize(SIMD3<Float>(
                    x / max(ring.radiusX, 0.0001), 0,
                    z / max(ring.radiusZ, 0.0001)))
                normals.append(SCNVector3(normal))
            }
        }
        for ring in 0..<(rings.count - 1) {
            for segment in 0..<radialSegments {
                let next = (segment + 1) % radialSegments
                let a = Int32(ring * radialSegments + segment)
                let b = Int32(ring * radialSegments + next)
                let c = Int32((ring + 1) * radialSegments + next)
                let d = Int32((ring + 1) * radialSegments + segment)
                indices.append(contentsOf: [a, b, c, a, c, d])
            }
        }
        let sources = [SCNGeometrySource(vertices: vertices),
                       SCNGeometrySource(normals: normals)]
        let element = SCNGeometryElement(indices: indices,
                                         primitiveType: .triangles)
        return SCNGeometry(sources: sources, elements: [element])
    }

    private static func garmentProxyNodes(
        for descriptor: FactoryGarmentLayerDescriptor,
        frame: DressFormFrame, color: NSColor
    ) -> [SCNNode] {
        let semantic = [descriptor.primitiveKind, descriptor.role,
                        descriptor.pieceID].joined(separator: " ").lowercased()
        let material = garmentMaterial(color: color, layer: descriptor.layer,
                                       opacity: 0.40)
        let allowance = frame.width * (0.035 + Float(max(0, descriptor.layer)) * 0.012)
        let sideValues: [Float]
        if descriptor.side.lowercased().contains("left") { sideValues = [-1] }
        else if descriptor.side.lowercased().contains("right") { sideValues = [1] }
        else { sideValues = [-1, 1] }

        if semantic.contains("sleeve") || semantic.contains("arm") {
            return sideValues.flatMap { side -> [SCNNode] in
                let shoulder = SIMD3<Float>(frame.centerX + side * frame.width * 0.48,
                                            frame.shoulder, frame.centerZ)
                let elbow = SIMD3<Float>(frame.centerX + side * frame.width * 0.57,
                                         frame.elbow, frame.centerZ)
                let wrist = SIMD3<Float>(frame.centerX + side * frame.width * 0.55,
                                         frame.wrist, frame.centerZ)
                return [limbSegment(name: "garment-sleeve-upper", from: shoulder,
                                    to: elbow, startRadius: frame.width * 0.125 + allowance,
                                    endRadius: frame.width * 0.10 + allowance,
                                    depthScale: 0.95, material: material),
                        limbSegment(name: "garment-sleeve-lower", from: elbow,
                                    to: wrist, startRadius: frame.width * 0.105 + allowance,
                                    endRadius: frame.width * 0.075 + allowance,
                                    depthScale: 0.95, material: material)]
            }
        }
        if semantic.contains("trouser") || semantic.contains("pant")
            || semantic.contains("legging") {
            return sideValues.flatMap { side -> [SCNNode] in
                let hip = SIMD3<Float>(frame.centerX + side * frame.width * 0.19,
                                       frame.top - frame.height * 0.565, frame.centerZ)
                let knee = SIMD3<Float>(frame.centerX + side * frame.width * 0.18,
                                        frame.knee, frame.centerZ)
                let ankle = SIMD3<Float>(frame.centerX + side * frame.width * 0.17,
                                         frame.ankle, frame.centerZ)
                return [limbSegment(name: "garment-trouser-upper", from: hip, to: knee,
                                    startRadius: frame.width * 0.19 + allowance,
                                    endRadius: frame.width * 0.13 + allowance,
                                    depthScale: 1.0, material: material),
                        limbSegment(name: "garment-trouser-lower", from: knee, to: ankle,
                                    startRadius: frame.width * 0.14 + allowance,
                                    endRadius: frame.width * 0.095 + allowance,
                                    depthScale: 1.0, material: material)]
            }
        }
        let ownsOneSide = descriptor.side.lowercased().contains("left")
            || descriptor.side.lowercased().contains("right")
        let isSidePanel = semantic.contains("gore")
            || semantic.contains("overskirt") || semantic.contains("panel")
        if ownsOneSide && isSidePanel {
            let side: Float = descriptor.side.lowercased().contains("left") ? -1 : 1
            return [sideDrapedPanelNode(frame: frame, material: material,
                                        side: side, layerOffset: allowance)]
        }
        if semantic.contains("skirt") || semantic.contains("dress")
            || semantic.contains("gore") || semantic.contains("flare") {
            let bodice = semantic.contains("dress")
                ? torsoGarmentNode(frame: frame, material: material,
                                   allowance: allowance, lowerY: frame.waist)
                : nil
            let skirt = profileGarmentNode(name: "garment-flared-lower", frame: frame,
                                           material: material, rings: [
                .init(y: frame.waist, radiusX: frame.width * 0.37 + allowance,
                      radiusZ: frame.width * 0.23 + allowance),
                .init(y: frame.hip, radiusX: frame.width * 0.48 + allowance,
                      radiusZ: frame.width * 0.27 + allowance),
                .init(y: frame.knee, radiusX: frame.width * 0.59 + allowance,
                      radiusZ: frame.width * 0.36 + allowance),
                .init(y: frame.ankle, radiusX: frame.width * 0.72 + allowance,
                      radiusZ: frame.width * 0.44 + allowance),
            ])
            return [bodice, skirt].compactMap { $0 }
        }
        if semantic.contains("cape") || semantic.contains("cloak")
            || semantic.contains("mantle") || semantic.contains("overlay") {
            return [capePanelNode(frame: frame, material: material,
                                  layerOffset: allowance)]
        }
        if semantic.contains("ruffle") || semantic.contains("frill")
            || semantic.contains("flounce") || semantic.contains("gather") {
            return [ruffleNode(frame: frame, material: material,
                               layerOffset: allowance)]
        }
        if semantic.contains("belt") || semantic.contains("waistband")
            || semantic.contains("yoke") || semantic.contains("band") {
            return [profileGarmentNode(name: "garment-band", frame: frame,
                                       material: material, rings: [
                .init(y: frame.waist + frame.height * 0.018,
                      radiusX: frame.width * 0.37 + allowance,
                      radiusZ: frame.width * 0.23 + allowance),
                .init(y: frame.waist - frame.height * 0.018,
                      radiusX: frame.width * 0.37 + allowance,
                      radiusZ: frame.width * 0.23 + allowance),
            ])]
        }
        return [torsoGarmentNode(frame: frame, material: material,
                                allowance: allowance,
                                lowerY: semantic.contains("coat")
                                    ? frame.top - frame.height * 0.66 : frame.hip)]
    }

    private static func torsoGarmentNode(frame: DressFormFrame,
                                         material: SCNMaterial,
                                         allowance: Float,
                                         lowerY: Float) -> SCNNode {
        profileGarmentNode(name: "garment-torso-shell", frame: frame,
                           material: material, rings: [
            .init(y: frame.shoulder, radiusX: frame.width * 0.51 + allowance,
                  radiusZ: frame.width * 0.24 + allowance),
            .init(y: frame.chest, radiusX: frame.width * 0.47 + allowance,
                  radiusZ: frame.width * 0.285 + allowance),
            .init(y: frame.waist, radiusX: frame.width * 0.36 + allowance,
                  radiusZ: frame.width * 0.225 + allowance),
            .init(y: lowerY, radiusX: frame.width * 0.47 + allowance,
                  radiusZ: frame.width * 0.27 + allowance),
        ])
    }

    private static func profileGarmentNode(name: String, frame: DressFormFrame,
                                           material: SCNMaterial,
                                           rings: [ProfileRing]) -> SCNNode {
        let geometry = radialProfileGeometry(rings: rings)
        geometry.materials = [material]
        let node = SCNNode(geometry: geometry)
        node.name = name
        node.position = SCNVector3(frame.centerX, 0, frame.centerZ)
        return node
    }

    private static func capePanelNode(frame: DressFormFrame, material: SCNMaterial,
                                      layerOffset: Float) -> SCNNode {
        let rows = 9, columns = 17
        var vertices: [SCNVector3] = []
        var indices: [Int32] = []
        for row in 0..<rows {
            let v = Float(row) / Float(rows - 1)
            let y = frame.shoulder - v * frame.height * 0.56
            let halfWidth = frame.width * (0.50 + v * 0.38) + layerOffset
            for column in 0..<columns {
                let u = Float(column) / Float(columns - 1) * 2 - 1
                let z = frame.centerZ - frame.width * (0.25 + 0.09 * (1 - u * u))
                let fold = sin(Float(column) * Float.pi * 0.72) * frame.width * 0.025
                vertices.append(SCNVector3(frame.centerX + u * halfWidth,
                                           y + fold * v, z - abs(fold)))
            }
        }
        for row in 0..<(rows - 1) {
            for column in 0..<(columns - 1) {
                let a = Int32(row * columns + column)
                let b = a + 1, d = Int32((row + 1) * columns + column), c = d + 1
                indices.append(contentsOf: [a, b, c, a, c, d])
            }
        }
        let geometry = SCNGeometry(
            sources: [SCNGeometrySource(vertices: vertices)],
            elements: [SCNGeometryElement(indices: indices,
                                           primitiveType: .triangles)])
        geometry.materials = [material]
        let node = SCNNode(geometry: geometry)
        node.name = "garment-cape-overlay"
        return node
    }

    /// One-sided PROPOSED drape for typed left/right GORE, overskirt or panel
    /// ownership. It deliberately does not mirror itself; structural bilateral
    /// SKIRT/FLARE nodes continue through the full profile branch above.
    private static func sideDrapedPanelNode(
        frame: DressFormFrame, material: SCNMaterial,
        side: Float, layerOffset: Float
    ) -> SCNNode {
        let rows = 10, columns = 11
        var vertices: [SCNVector3] = []
        var indices: [Int32] = []
        for row in 0..<rows {
            let v = Float(row) / Float(rows - 1)
            let y = frame.waist - v * frame.height * 0.51
            let width = frame.width * (0.26 + v * 0.40) + layerOffset
            for column in 0..<columns {
                let u = Float(column) / Float(columns - 1)
                let pleat = sin(Float(column) * Float.pi) * frame.width * 0.035
                let innerX = frame.centerX + side * frame.width * 0.04
                let x = innerX + side * u * width
                let frontDepth = frame.centerZ + frame.width * 0.27
                    + pleat * (0.45 + v * 0.55)
                let asymmetricDrop = abs(u - 0.65) * frame.height * 0.035 * v
                vertices.append(SCNVector3(x, y - asymmetricDrop, frontDepth))
            }
        }
        for row in 0..<(rows - 1) {
            for column in 0..<(columns - 1) {
                let a = Int32(row * columns + column), b = a + 1
                let d = Int32((row + 1) * columns + column), c = d + 1
                indices.append(contentsOf: [a, b, c, a, c, d])
            }
        }
        let geometry = SCNGeometry(
            sources: [SCNGeometrySource(vertices: vertices)],
            elements: [SCNGeometryElement(indices: indices,
                                           primitiveType: .triangles)])
        geometry.materials = [material]
        let node = SCNNode(geometry: geometry)
        node.name = side < 0
            ? "garment-side-specific-proposed-pleated-panel-left"
            : "garment-side-specific-proposed-pleated-panel-right"
        return node
    }

    private static func ruffleNode(frame: DressFormFrame, material: SCNMaterial,
                                   layerOffset: Float) -> SCNNode {
        let segments = 64
        var vertices: [SCNVector3] = []
        var indices: [Int32] = []
        for row in 0...1 {
            for segment in 0..<segments {
                let angle = Float(segment) / Float(segments) * Float.pi * 2
                let wave = sin(angle * 12) * frame.width * 0.035
                let radiusX = frame.width * 0.48 + layerOffset + wave
                let radiusZ = frame.width * 0.28 + layerOffset * 0.6 + wave * 0.5
                vertices.append(SCNVector3(frame.centerX + cos(angle) * radiusX,
                                           frame.hip - Float(row) * frame.height * 0.045
                                                + cos(angle * 12) * frame.height * 0.008,
                                           frame.centerZ + sin(angle) * radiusZ))
            }
        }
        for segment in 0..<segments {
            let next = (segment + 1) % segments
            let a = Int32(segment), b = Int32(next)
            let c = Int32(segments + next), d = Int32(segments + segment)
            indices.append(contentsOf: [a, b, c, a, c, d])
        }
        let geometry = SCNGeometry(
            sources: [SCNGeometrySource(vertices: vertices)],
            elements: [SCNGeometryElement(indices: indices,
                                           primitiveType: .triangles)])
        geometry.materials = [material]
        let node = SCNNode(geometry: geometry)
        node.name = "garment-ruffle-surface"
        return node
    }

    private static func bindProposalIdentity(
        _ node: SCNNode, descriptor: FactoryGarmentLayerDescriptor?,
        componentIndex: Int, allLayers: [FactoryGarmentLayerDescriptor],
        binding: String
    ) {
        let source = descriptor?.sourceNodeID ?? "unresolved-component-\(componentIndex)"
        let piece = descriptor?.pieceID ?? "unresolved-component-\(componentIndex)"
        let layer = descriptor?.layer ?? -1
        let identity = "proposal/source=\(source)/piece=\(piece)/layer=\(layer)"
        node.name = "\(identity)/\(node.name ?? "surface")"
        node.geometry?.name = identity
        let metadata = SCNNode()
        metadata.name = [
            "metadata", "authority=PROPOSED",
            "rear_authority=PROPOSED_NOT_OBSERVED_FROM_FRONT",
            "material_authority=UNKNOWN_NOT_MEASURED",
            "source_node_id=\(source)", "piece_id=\(piece)", "layer=\(layer)",
            "side=\(descriptor?.side ?? "unknown")",
            "role=\(descriptor?.role ?? "unknown")",
            "primitive_kind=\(descriptor?.primitiveKind ?? "UNKNOWN")",
            "identity_binding=\(binding)",
            "available_source_node_ids=\(allLayers.map(\.sourceNodeID).joined(separator: ","))",
        ].joined(separator: "/")
        node.addChildNode(metadata)
    }

    private static let fashionPalette: [NSColor] = [
        NSColor(calibratedRed: 0.10, green: 0.20, blue: 0.38, alpha: 1),
        NSColor(calibratedRed: 0.50, green: 0.12, blue: 0.16, alpha: 1),
        NSColor(calibratedRed: 0.05, green: 0.40, blue: 0.36, alpha: 1),
        NSColor(calibratedRed: 0.33, green: 0.18, blue: 0.46, alpha: 1),
        NSColor(calibratedRed: 0.65, green: 0.30, blue: 0.12, alpha: 1),
        NSColor(calibratedRed: 0.18, green: 0.38, blue: 0.62, alpha: 1),
        NSColor(calibratedRed: 0.62, green: 0.27, blue: 0.42, alpha: 1),
        NSColor(calibratedRed: 0.27, green: 0.45, blue: 0.23, alpha: 1),
    ]

    private static func proposedColor(for descriptor: FactoryGarmentLayerDescriptor?,
                                      fallbackIndex: Int,
                                      palette: [NSColor] = fashionPalette) -> NSColor {
        if let token = descriptor?.proposedColor,
           let color = color(from: token) { return color }
        let identity = descriptor.map {
            "\($0.sourceNodeID)|\($0.pieceID)|\($0.layer)"
        } ?? "component|\(fallbackIndex)"
        let stable = identity.utf8.reduce(UInt64(1469598103934665603)) {
            ($0 ^ UInt64($1)) &* 1099511628211
        }
        return palette[Int(stable % UInt64(palette.count))]
    }

    private static func color(from token: String) -> NSColor? {
        let trimmed = token.trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: "#", with: "")
        guard trimmed.count == 6, let value = UInt64(trimmed, radix: 16) else { return nil }
        return NSColor(calibratedRed: CGFloat((value >> 16) & 0xff) / 255,
                       green: CGFloat((value >> 8) & 0xff) / 255,
                       blue: CGFloat(value & 0xff) / 255, alpha: 1)
    }

    private static func garmentMaterial(color: NSColor, layer: Int,
                                        opacity: CGFloat) -> SCNMaterial {
        let material = SCNMaterial()
        material.name = "PROPOSED garment layer \(layer)"
        material.diffuse.contents = color.withAlphaComponent(opacity)
        material.emission.contents = color.withAlphaComponent(0.025)
        material.roughness.contents = max(0.42, 0.72 - CGFloat(layer) * 0.025)
        material.metalness.contents = 0.015
        material.transparency = opacity
        material.lightingModel = .physicallyBased
        material.isDoubleSided = true
        return material
    }

    private static func dressFormMaterial() -> SCNMaterial {
        let material = SCNMaterial()
        material.name = "neutral procedural dress form — not measured"
        material.diffuse.contents = NSColor(calibratedRed: 0.69, green: 0.61,
                                             blue: 0.54, alpha: 1)
        material.roughness.contents = 0.82
        material.metalness.contents = 0.0
        material.lightingModel = .physicallyBased
        return material
    }

    private static func addStudioFloor(to scene: SCNScene, frame: DressFormFrame) {
        let floor = SCNFloor()
        floor.reflectivity = 0.06
        floor.reflectionFalloffEnd = CGFloat(frame.height * 0.4)
        let material = SCNMaterial()
        material.diffuse.contents = NSColor(calibratedWhite: 0.09, alpha: 1)
        material.roughness.contents = 0.92
        floor.materials = [material]
        let node = SCNNode(geometry: floor)
        node.name = "studio-floor"
        node.position = SCNVector3(0, frame.floor - frame.height * 0.008, 0)
        scene.rootNode.addChildNode(node)
    }

    private static func frameCameraAndLights(scene: SCNScene,
                                             frame: DressFormFrame) {
        let frameCenterX = CGFloat(frame.centerX)
        let frameCenterY = CGFloat((frame.top + frame.floor) * 0.5)
        let frameCenterZ = CGFloat(frame.centerZ)
        let frameHeight = CGFloat(frame.height)
        let frameWidth = CGFloat(frame.width)
        let center = SCNVector3(frame.centerX,
                                (frame.top + frame.floor) * 0.5,
                                frame.centerZ)
        let extent = max(frameHeight, frameWidth * 2.2)
        let camera = SCNNode()
        camera.name = "candidate-three-quarter-camera"
        camera.camera = SCNCamera()
        camera.camera?.zNear = 0.001
        camera.camera?.zFar = Double(max(extent * 60, 1_000))
        camera.camera?.usesOrthographicProjection = true
        camera.camera?.orthographicScale = Double(max(frameHeight * 1.045, 1))
        let cameraX = frameCenterX + frameWidth * 0.42
        let cameraY = frameCenterY + frameHeight * 0.018
        let cameraZ = frameCenterZ + max(frameHeight * 2.6, 1)
        camera.position = SCNVector3(cameraX, cameraY, cameraZ)
        camera.look(at: center)
        scene.rootNode.addChildNode(camera)

        let key = SCNNode()
        key.light = SCNLight()
        key.light?.type = .area
        key.light?.intensity = 920
        key.light?.castsShadow = true
        key.light?.shadowRadius = 8
        key.light?.color = NSColor(calibratedWhite: 0.98, alpha: 1)
        let keyX = frameCenterX - extent
        let keyY = frameCenterY + extent * 0.75
        let keyZ = frameCenterZ + extent * 1.8
        key.position = SCNVector3(keyX, keyY, keyZ)
        scene.rootNode.addChildNode(key)
        let rim = SCNNode()
        rim.light = SCNLight()
        rim.light?.type = .omni
        rim.light?.intensity = 420
        rim.light?.color = NSColor(calibratedRed: 0.42, green: 0.55,
                                   blue: 0.82, alpha: 1)
        let rimX = frameCenterX + extent
        let rimY = frameCenterY + extent * 0.25
        let rimZ = frameCenterZ - extent
        rim.position = SCNVector3(rimX, rimY, rimZ)
        scene.rootNode.addChildNode(rim)
        let fill = SCNNode()
        fill.light = SCNLight()
        fill.light?.type = .ambient
        fill.light?.intensity = 280
        fill.light?.color = NSColor(calibratedRed: 0.60, green: 0.63,
                                    blue: 0.72, alpha: 1)
        scene.rootNode.addChildNode(fill)
    }

    /// Build the interactive cleanup scene from the fused visual target. The
    /// returned face mapping lets a brush hit update the original stable face
    /// ids even after erased triangles are removed from the displayed mesh.
    static func makeTargetSculptScene(
        points: [[Double]], faces: [[Int]], faceRegionIDs: [String],
        textureCoordinates: [[Double]],
        removedFaces: Set<Int>, sourceImagePath: String?,
        clearanceBands: [Int: String],
        avatarProfile: GarmentFactoryReactController.BaseAvatarProfile
    ) -> (scene: SCNScene, faceMappings: [String: [Int]]) {
        let scene = SCNScene()
        scene.background.contents = NSColor(calibratedWhite: 0.035, alpha: 1)
        let content = SCNNode()
        content.name = "target-sculpt-content"
        scene.rootNode.addChildNode(content)
        let vertices = points.map { point -> SCNVector3 in
            guard point.count >= 3 else { return SCNVector3Zero }
            return SCNVector3(Float(point[0]), Float(point[1]), Float(point[2]))
        }
        let valid = Set(points.indices.filter { points[$0].count >= 3 })
        guard !valid.isEmpty else { return (scene, [:]) }
        let validVertices = valid.sorted().map { vertices[$0] }
        let frame = proposedImageProportionFrame(
            vertices: validVertices, avatarProfile: avatarProfile)
        let bodyProxy = mannequinNode(frame: frame, avatarProfile: avatarProfile)
        bodyProxy.name = "target-sculpt-body-proxy"
        bodyProxy.renderingOrder = -20
        bodyProxy.enumerateChildNodes { node, _ in
            node.renderingOrder = -20
            node.geometry?.materials.forEach { material in
                material.name = "PROPOSED body proxy — not measured"
                material.diffuse.contents = NSColor(
                    calibratedWhite: 0.48, alpha: 0.15)
                material.emission.contents = NSColor(
                    calibratedWhite: 0.20, alpha: 0.03)
                material.transparency = 0.15
                material.writesToDepthBuffer = false
                material.readsFromDepthBuffer = true
                material.isDoubleSided = true
            }
        }
        content.addChildNode(bodyProxy)

        var frontIndices: [Int32] = []
        var frontFaceIDs: [Int] = []
        var rearIndices: [Int32] = []
        var rearFaceIDs: [Int] = []
        var edgeIndices: [Int32] = []
        var edgeFaceIDs: [Int] = []
        var removedIndices: [Int32] = []
        var removedFaceIDs: [Int] = []
        var clearanceIndices: [String: [Int32]] = [:]
        for (faceID, face) in faces.enumerated()
        where face.count >= 3 && face.allSatisfy(valid.contains) {
            for index in 1..<(face.count - 1) {
                if removedFaces.contains(faceID) {
                    removedIndices.append(contentsOf: [
                        Int32(face[0]), Int32(face[index]), Int32(face[index + 1]),
                    ])
                    removedFaceIDs.append(faceID)
                } else {
                    let triangle = [
                        Int32(face[0]), Int32(face[index]), Int32(face[index + 1]),
                    ]
                    let region = faceRegionIDs.indices.contains(faceID)
                        ? faceRegionIDs[faceID] : "front-visible-surface"
                    switch region {
                    case "rear-proposed-surface":
                        rearIndices.append(contentsOf: triangle)
                        rearFaceIDs.append(faceID)
                    case "edge-proposed-surface":
                        edgeIndices.append(contentsOf: triangle)
                        edgeFaceIDs.append(faceID)
                    default:
                        frontIndices.append(contentsOf: triangle)
                        frontFaceIDs.append(faceID)
                    }
                    if let band = clearanceBands[faceID] {
                        clearanceIndices[band, default: []]
                            .append(contentsOf: triangle)
                    }
                }
            }
        }
        let source = SCNGeometrySource(vertices: vertices)
        let minX = vertices.map(\.x).min() ?? 0
        let maxX = vertices.map(\.x).max() ?? 1
        let minY = vertices.map(\.y).min() ?? 0
        let maxY = vertices.map(\.y).max() ?? 1
        let spanX = max(maxX - minX, 0.0001)
        let spanY = max(maxY - minY, 0.0001)
        let mappedTextureCoordinates: [CGPoint]
        if textureCoordinates.count == vertices.count,
           textureCoordinates.allSatisfy({ $0.count >= 2 }) {
            mappedTextureCoordinates = textureCoordinates.map {
                CGPoint(x: CGFloat($0[0]), y: CGFloat($0[1]))
            }
        } else {
            mappedTextureCoordinates = vertices.map {
                CGPoint(x: CGFloat(($0.x - minX) / spanX),
                        y: CGFloat(($0.y - minY) / spanY))
            }
        }
        let textureSource = SCNGeometrySource(
            textureCoordinates: mappedTextureCoordinates)

        func addEditableSurface(name: String, indices: [Int32], faceIDs: [Int],
                                material: SCNMaterial) {
            guard !indices.isEmpty else { return }
            let element = SCNGeometryElement(indices: indices,
                                             primitiveType: .triangles)
            let geometry = SCNGeometry(sources: [source, textureSource],
                                       elements: [element])
            geometry.materials = [material]
            let target = SCNNode(geometry: geometry)
            target.name = name
            target.renderingOrder = name.hasSuffix("front") ? 30 : 20
            content.addChildNode(target)
        }

        if !frontIndices.isEmpty {
            let material = SCNMaterial()
            material.name = "source-projected editable fused target"
            if let path = sourceImagePath,
               let image = NSImage(contentsOfFile: path) {
                material.diffuse.contents = image
            } else {
                material.diffuse.contents = NSColor(
                    calibratedRed: 0.16, green: 0.63, blue: 0.78, alpha: 0.92)
            }
            material.metalness.contents = 0.02
            material.roughness.contents = 0.62
            material.transparency = 0.96
            material.isDoubleSided = true
            material.lightingModel = .physicallyBased
            addEditableSurface(name: "editable-fused-target-front",
                               indices: frontIndices, faceIDs: frontFaceIDs,
                               material: material)
        }
        if !rearIndices.isEmpty {
            let material = SCNMaterial()
            material.name = "unobserved rear proposal"
            material.diffuse.contents = NSColor(
                calibratedRed: 0.12, green: 0.44, blue: 0.56, alpha: 0.72)
            material.emission.contents = NSColor.systemTeal.withAlphaComponent(0.035)
            material.roughness.contents = 0.78
            material.transparency = 0.76
            material.isDoubleSided = true
            material.lightingModel = .physicallyBased
            addEditableSurface(name: "editable-fused-target-rear",
                               indices: rearIndices, faceIDs: rearFaceIDs,
                               material: material)
        }
        if !edgeIndices.isEmpty {
            let material = SCNMaterial()
            material.name = "proposed target thickness wall"
            material.diffuse.contents = NSColor.systemTeal.withAlphaComponent(0.64)
            material.roughness.contents = 0.74
            material.transparency = 0.70
            material.isDoubleSided = true
            material.lightingModel = .physicallyBased
            addEditableSurface(name: "editable-fused-target-edge",
                               indices: edgeIndices, faceIDs: edgeFaceIDs,
                               material: material)
        }

        let allVisibleIndices = frontIndices + rearIndices + edgeIndices
        if !allVisibleIndices.isEmpty {
            let wireElement = SCNGeometryElement(indices: allVisibleIndices,
                                                 primitiveType: .triangles)
            let wireGeometry = SCNGeometry(sources: [source], elements: [wireElement])
            let wire = SCNMaterial()
            wire.diffuse.contents = NSColor.white.withAlphaComponent(0.20)
            wire.emission.contents = NSColor.systemTeal.withAlphaComponent(0.08)
            wire.fillMode = .lines
            wire.lightingModel = .constant
            wire.isDoubleSided = true
            wireGeometry.materials = [wire]
            let wireNode = SCNNode(geometry: wireGeometry)
            wireNode.name = "editable-fused-target-wire"
            wireNode.renderingOrder = 45
            wireNode.isHidden = true
            content.addChildNode(wireNode)
        }
        for band in clearanceIndices.keys.sorted() {
            guard let indices = clearanceIndices[band], !indices.isEmpty else {
                continue
            }
            let colour: NSColor
            let opacity: CGFloat
            switch band {
            case "PENETRATION_CORRECTED":
                colour = .systemRed; opacity = 0.48
            case "THICKNESS_CLEARANCE_CORRECTED":
                colour = .systemOrange; opacity = 0.40
            case "LOW_CLEARANCE":
                colour = .systemYellow; opacity = 0.28
            case "MODERATE_CLEARANCE":
                colour = .systemGreen; opacity = 0.20
            default:
                colour = .systemBlue; opacity = 0.14
            }
            let element = SCNGeometryElement(indices: indices,
                                             primitiveType: .triangles)
            let geometry = SCNGeometry(sources: [source], elements: [element])
            let material = SCNMaterial()
            material.name = "geometric clearance \(band) — not pressure"
            material.diffuse.contents = colour.withAlphaComponent(opacity)
            material.emission.contents = colour.withAlphaComponent(opacity * 0.55)
            material.transparency = opacity
            material.isDoubleSided = true
            material.lightingModel = .constant
            geometry.materials = [material]
            let node = SCNNode(geometry: geometry)
            node.name = "target-clearance-\(band.lowercased())"
            node.renderingOrder = 50
            content.addChildNode(node)
        }
        if !removedIndices.isEmpty {
            let element = SCNGeometryElement(indices: removedIndices,
                                             primitiveType: .triangles)
            let geometry = SCNGeometry(sources: [source], elements: [element])
            let ghost = SCNMaterial()
            ghost.diffuse.contents = NSColor.systemOrange.withAlphaComponent(0.10)
            ghost.emission.contents = NSColor.systemOrange.withAlphaComponent(0.04)
            ghost.transparency = 0.18
            ghost.isDoubleSided = true
            ghost.lightingModel = .constant
            geometry.materials = [ghost]
            let node = SCNNode(geometry: geometry)
            node.name = "editable-fused-target-removed"
            node.renderingOrder = 40
            content.addChildNode(node)
        }
        addStudioFloor(to: scene, frame: frame)
        frameCameraAndLights(scene: scene, frame: frame)
        scene.rootNode.childNode(
            withName: "candidate-three-quarter-camera", recursively: true)?
            .removeFromParentNode()
        let camera = SCNNode()
        camera.name = "target-sculpt-camera"
        camera.camera = SCNCamera()
        camera.camera?.zNear = 0.001
        camera.camera?.zFar = Double(max(CGFloat(frame.height) * 60, 1_000))
        camera.camera?.usesOrthographicProjection = true
        camera.camera?.orthographicScale = Double(
            max(CGFloat(frame.height) * 0.92, 1))
        camera.position = SCNVector3(
            CGFloat(frame.centerX),
            CGFloat((frame.top + frame.floor) * 0.5),
            CGFloat(frame.centerZ + max(frame.height * 3.0, 1)))
        // A fresh camera prevents the candidate preview's inherited
        // three-quarter orbit from turning a front target into a side sliver.
        camera.eulerAngles = SCNVector3Zero
        scene.rootNode.addChildNode(camera)
        return (scene, [
            "editable-fused-target-front": frontFaceIDs,
            "editable-fused-target-rear": rearFaceIDs,
            "editable-fused-target-edge": edgeFaceIDs,
            "editable-fused-target-removed": removedFaceIDs,
        ])
    }
}

enum TargetSculptTool: String, CaseIterable, Identifiable {
    case orbit
    case erase
    case restore
    case pull
    case stretch

    var id: String { rawValue }
    var title: String {
        switch self {
        case .orbit: return "回転"
        case .erase: return "削る"
        case .restore: return "戻す"
        case .pull: return "引っ張る"
        case .stretch: return "伸縮"
        }
    }
    var symbol: String {
        switch self {
        case .orbit: return "rotate.3d"
        case .erase: return "eraser.fill"
        case .restore: return "paintbrush.pointed.fill"
        case .pull: return "arrow.up.and.down.and.arrow.left.and.right"
        case .stretch: return "arrow.left.and.right.circle"
        }
    }

    var usesPolygon: Bool { self == .erase || self == .restore }
    var usesBoundaryDrag: Bool { self == .pull || self == .stretch }
}

private struct TargetSculptBoundaryAnchor {
    let point: CGPoint
    let depth: CGFloat
    let vertexIndex: Int
    let componentID: String
    let colourIndex: Int
}

/// A non-intercepting AppKit overlay keeps lasso vertices and component
/// handles visible while SceneKit continues to receive mouse events.  It is
/// deliberately local UI state: no mesh changes until a polygon closes or a
/// boundary drag ends.
private final class TargetSculptSelectionOverlayView: NSView {
    var tool: TargetSculptTool = .orbit { didSet { needsDisplay = true } }
    var polygonPoints: [CGPoint] = [] { didSet { needsDisplay = true } }
    var boundaryAnchors: [TargetSculptBoundaryAnchor] = [] {
        didSet { needsDisplay = true }
    }
    var activeAnchor: TargetSculptBoundaryAnchor? {
        didSet { needsDisplay = true }
    }
    var dragPoint: CGPoint? { didSet { needsDisplay = true } }

    override func hitTest(_ point: NSPoint) -> NSView? { nil }

    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        if tool.usesPolygon { drawPolygon() }
        if tool.usesBoundaryDrag { drawBoundaryHandles() }
    }

    private func drawPolygon() {
        guard !polygonPoints.isEmpty else { return }
        let colour: NSColor = tool == .erase ? .systemRed : .systemGreen
        let path = NSBezierPath()
        path.lineWidth = 2
        path.lineJoinStyle = .round
        path.move(to: polygonPoints[0])
        for point in polygonPoints.dropFirst() { path.line(to: point) }
        colour.setStroke()
        path.stroke()

        if polygonPoints.count >= 3 {
            let fill = path.copy() as! NSBezierPath
            fill.close()
            colour.withAlphaComponent(0.10).setFill()
            fill.fill()
        }
        for (index, point) in polygonPoints.enumerated() {
            let radius: CGFloat = index == 0 ? 5.5 : 4.0
            let dot = NSBezierPath(ovalIn: NSRect(
                x: point.x - radius, y: point.y - radius,
                width: radius * 2, height: radius * 2))
            (index == 0 ? NSColor.white : colour).setFill()
            dot.fill()
            colour.setStroke()
            dot.lineWidth = 1.5
            dot.stroke()
        }
    }

    private func drawBoundaryHandles() {
        let palette: [NSColor] = [
            .systemCyan, .systemOrange, .systemPink, .systemGreen,
            .systemPurple, .systemYellow, .systemBlue,
        ]
        for anchor in boundaryAnchors {
            let selected = activeAnchor?.componentID == anchor.componentID
            let colour = palette[anchor.colourIndex % palette.count]
            let radius: CGFloat = selected ? 4.5 : 3.2
            let dot = NSBezierPath(ovalIn: NSRect(
                x: anchor.point.x - radius, y: anchor.point.y - radius,
                width: radius * 2, height: radius * 2))
            (selected ? NSColor.white : colour).setFill()
            dot.fill()
            colour.setStroke()
            dot.lineWidth = selected ? 2 : 1
            dot.stroke()
        }
        guard let anchor = activeAnchor, let dragPoint else { return }
        let colour = palette[anchor.colourIndex % palette.count]
        let arrow = NSBezierPath()
        arrow.lineWidth = 2.5
        arrow.move(to: anchor.point)
        arrow.line(to: dragPoint)
        colour.setStroke()
        arrow.stroke()
        let angle = atan2(dragPoint.y - anchor.point.y,
                          dragPoint.x - anchor.point.x)
        let headLength: CGFloat = 11
        for offset: CGFloat in [-0.55, 0.55] {
            let tip = CGPoint(
                x: dragPoint.x - cos(angle + offset) * headLength,
                y: dragPoint.y - sin(angle + offset) * headLength)
            let head = NSBezierPath()
            head.lineWidth = 2.5
            head.move(to: dragPoint)
            head.line(to: tip)
            head.stroke()
        }
    }
}

final class TargetSculptSCNView: SCNView {
    var sculptTool: TargetSculptTool = .orbit
    var faceMappings: [String: [Int]] = [:]
    var onStroke: ((Set<Int>, Bool) -> Void)?
    var onModifierDrag: ((String, [Int], Int, [Double]) -> Void)?

    private let selectionOverlay = TargetSculptSelectionOverlayView(frame: .zero)
    private var sourcePoints: [SCNVector3] = []
    private var faces: [[Int]] = []
    private var faceComponentIDs: [String] = []
    private var removedFaces = Set<Int>()
    private var vertexAdjacency: [Int: Set<Int>] = [:]
    private var componentVertices: [String: Set<Int>] = [:]
    private var boundaryAnchors: [TargetSculptBoundaryAnchor] = []
    // Lasso vertices live in the target content's local 3D plane, not in
    // window pixels. Reprojection keeps them attached to the same garment
    // locations across resize, camera zoom, and orbit.
    private var polygonAnchors: [SCNVector3] = []
    private var activeAnchor: TargetSculptBoundaryAnchor?
    private var dragStart: CGPoint?
    private var previousOrbitPoint: NSPoint?
    private var representedSceneRevision: UInt64?
    private var representedGeometryRevision: UInt64?

    func installSelectionOverlay() {
        guard selectionOverlay.superview == nil else { return }
        selectionOverlay.autoresizingMask = [.width, .height]
        selectionOverlay.frame = bounds
        addSubview(selectionOverlay)
    }

    func requiresSceneUpdate(_ revision: UInt64) -> Bool {
        representedSceneRevision != revision
    }

    func installScene(
        _ nextScene: SCNScene,
        camera nextCamera: SCNNode?,
        faceMappings nextMappings: [String: [Int]],
        sceneRevision: UInt64,
        geometryRevision: UInt64,
        points: [[Double]], faces: [[Int]],
        faceComponentIDs: [String], removedFaces: Set<Int>
    ) {
        let priorContentTransform = scene?.rootNode.childNode(
            withName: "target-sculpt-content", recursively: true)?.simdTransform
        let priorCameraScale = pointOfView?.camera?.orthographicScale
        let preservesPolygon = representedGeometryRevision == geometryRevision

        scene = nextScene
        pointOfView = nextCamera
        faceMappings = nextMappings
        if let priorContentTransform,
           let content = nextScene.rootNode.childNode(
                withName: "target-sculpt-content", recursively: true) {
            content.simdTransform = priorContentTransform
        }
        if let priorCameraScale, let camera = nextCamera?.camera {
            camera.orthographicScale = priorCameraScale
        }

        sourcePoints = points.map { point in
            guard point.count >= 3 else { return SCNVector3Zero }
            return SCNVector3(point[0], point[1], point[2])
        }
        self.faces = faces
        self.faceComponentIDs = faceComponentIDs
        self.removedFaces = removedFaces
        vertexAdjacency = Self.makeVertexAdjacency(faces)
        let retainedPolygon = preservesPolygon ? polygonAnchors : []
        clearTransientSelection()
        polygonAnchors = retainedPolygon
        representedSceneRevision = sceneRevision
        representedGeometryRevision = geometryRevision
        refreshPolygonOverlay()
        refreshBoundaryAnchors()
        needsDisplay = true
        DispatchQueue.main.async { [weak self] in
            guard let self else { return }
            self.refreshPolygonOverlay()
            self.refreshBoundaryAnchors()
        }
    }

    func setSculptTool(_ tool: TargetSculptTool) {
        guard sculptTool != tool else {
            selectionOverlay.tool = tool
            refreshBoundaryAnchors()
            return
        }
        sculptTool = tool
        selectionOverlay.tool = tool
        clearTransientSelection()
        refreshBoundaryAnchors()
    }

    override func layout() {
        super.layout()
        selectionOverlay.frame = bounds
        refreshPolygonOverlay()
        refreshBoundaryAnchors()
    }

    override var acceptsFirstResponder: Bool { true }

    override func mouseDown(with event: NSEvent) {
        window?.makeFirstResponder(self)
        if sculptTool == .orbit {
            previousOrbitPoint = convert(event.locationInWindow, from: nil)
            return
        }
        let point = convert(event.locationInWindow, from: nil)
        if sculptTool.usesPolygon {
            addPolygonPoint(point, clickCount: event.clickCount)
        } else if sculptTool.usesBoundaryDrag {
            beginBoundaryDrag(at: point)
        }
    }

    override func mouseDragged(with event: NSEvent) {
        if sculptTool == .orbit {
            let point = convert(event.locationInWindow, from: nil)
            if let previous = previousOrbitPoint,
               let content = scene?.rootNode.childNode(
                    withName: "target-sculpt-content", recursively: true) {
                let dx = Float(point.x - previous.x)
                let dy = Float(point.y - previous.y)
                content.eulerAngles.y += CGFloat(dx * 0.008)
                content.eulerAngles.x = min(
                    CGFloat.pi * 0.42,
                    max(-CGFloat.pi * 0.42,
                        content.eulerAngles.x + CGFloat(dy * 0.005)))
                needsDisplay = true
            }
            previousOrbitPoint = point
            refreshPolygonOverlay()
            refreshBoundaryAnchors()
            return
        }
        guard sculptTool.usesBoundaryDrag, activeAnchor != nil else { return }
        selectionOverlay.dragPoint = convert(event.locationInWindow, from: nil)
    }

    override func mouseUp(with event: NSEvent) {
        if sculptTool == .orbit {
            previousOrbitPoint = nil
            return
        }
        guard sculptTool.usesBoundaryDrag,
              let anchor = activeAnchor,
              let start = dragStart else { return }
        let end = convert(event.locationInWindow, from: nil)
        let distance = hypot(end.x - start.x, end.y - start.y)
        defer {
            activeAnchor = nil
            dragStart = nil
            selectionOverlay.activeAnchor = nil
            selectionOverlay.dragPoint = nil
        }
        guard distance >= 3,
              let vectorCM = localDragVectorCM(
                from: start, to: end, depth: anchor.depth) else { return }
        let component = componentVertices[anchor.componentID]
            ?? Set([anchor.vertexIndex])
        let selected: Set<Int>
        if sculptTool == .stretch {
            selected = component
        } else {
            selected = localPatch(from: anchor.vertexIndex, within: component,
                                  rings: 3)
        }
        onModifierDrag?(
            sculptTool == .stretch ? "STRETCH" : "PULL",
            selected.sorted(), anchor.vertexIndex, vectorCM)
    }

    override func rightMouseDown(with event: NSEvent) {
        guard sculptTool.usesPolygon, !polygonAnchors.isEmpty else {
            super.rightMouseDown(with: event)
            return
        }
        polygonAnchors.removeLast()
        refreshPolygonOverlay()
    }

    override func keyDown(with event: NSEvent) {
        if event.keyCode == 53 { // Escape
            clearTransientSelection()
            return
        }
        if (event.keyCode == 51 || event.keyCode == 117),
           sculptTool.usesPolygon, !polygonAnchors.isEmpty {
            polygonAnchors.removeLast()
            refreshPolygonOverlay()
            return
        }
        super.keyDown(with: event)
    }

    override func scrollWheel(with event: NSEvent) {
        // Ordinary scrolling belongs to the surrounding chat/page. Zoom is an
        // explicit CAD gesture so a large canvas cannot trap the whole page.
        guard event.modifierFlags.contains(.option) else {
            if let scrollView = enclosingScrollView {
                scrollView.scrollWheel(with: event)
            } else if let nextResponder {
                nextResponder.scrollWheel(with: event)
            } else {
                super.scrollWheel(with: event)
            }
            return
        }
        zoom(by: Double(event.scrollingDeltaY) * 0.018)
    }

    override func magnify(with event: NSEvent) {
        zoom(by: -Double(event.magnification) * 1.8)
    }

    private func zoom(by logarithmicDelta: Double) {
        guard let camera = pointOfView?.camera else { return }
        camera.orthographicScale = min(
            1_000, max(4, camera.orthographicScale * exp(logarithmicDelta)))
        needsDisplay = true
        refreshPolygonOverlay()
        refreshBoundaryAnchors()
    }

    private func addPolygonPoint(_ point: CGPoint, clickCount: Int) {
        let projected = projectedPolygonPoints()
        if polygonAnchors.count >= 3,
           (clickCount >= 2 || projected.first.map {
               Self.distance(point, $0) <= 14
           } == true) {
            commitPolygon()
            return
        }
        guard let anchor = polygonLocalAnchor(at: point) else { return }
        polygonAnchors.append(anchor)
        refreshPolygonOverlay()
    }

    private func commitPolygon() {
        let selectionPolygon = projectedPolygonPoints()
        guard selectionPolygon.count >= 3 else { return }
        let removing = sculptTool == .erase
        var selected = Set<Int>()
        for faceIndex in faces.indices {
            guard removedFaces.contains(faceIndex) != removing,
                  let centroid = projectedFaceCentroid(faceIndex),
                  Self.contains(centroid, polygon: selectionPolygon),
                  visibleEditableFace(at: centroid, removing: removing)
                    == faceIndex else { continue }
            selected.insert(faceIndex)
        }
        polygonAnchors = []
        selectionOverlay.polygonPoints = []
        if !selected.isEmpty { onStroke?(selected, removing) }
    }

    private func visibleEditableFace(at point: CGPoint,
                                     removing: Bool) -> Int? {
        let hits = hitTest(point, options: [
            .searchMode: SCNHitTestSearchMode.all.rawValue,
            .ignoreHiddenNodes: true,
            .backFaceCulling: false,
        ])
        guard let hit = hits.first(where: { hit in
            guard let name = hit.node.name else { return false }
            if removing {
                return name.hasPrefix("editable-fused-target-")
                    && name != "editable-fused-target-wire"
                    && name != "editable-fused-target-removed"
            }
            return name == "editable-fused-target-removed"
        }), let name = hit.node.name,
              let mapping = faceMappings[name],
              mapping.indices.contains(hit.faceIndex) else { return nil }
        return mapping[hit.faceIndex]
    }

    private func beginBoundaryDrag(at point: CGPoint) {
        refreshBoundaryAnchors()
        guard let nearest = boundaryAnchors.min(by: {
            Self.distance($0.point, point) < Self.distance($1.point, point)
        }), Self.distance(nearest.point, point) <= 20 else { return }
        activeAnchor = nearest
        dragStart = nearest.point
        selectionOverlay.activeAnchor = nearest
        selectionOverlay.dragPoint = nearest.point
    }

    private func refreshBoundaryAnchors() {
        guard sculptTool.usesBoundaryDrag, bounds.width > 1, bounds.height > 1,
              pointOfView != nil else {
            boundaryAnchors = []
            componentVertices = [:]
            selectionOverlay.boundaryAnchors = []
            return
        }
        var grouped = [String: Set<Int>]()
        var visibleGrouped = [String: Set<Int>]()
        for faceIndex in faces.indices where !removedFaces.contains(faceIndex) {
            let component = faceComponentIDs.indices.contains(faceIndex)
                && !faceComponentIDs[faceIndex].isEmpty
                ? faceComponentIDs[faceIndex] : "garment"
            let vertices = faces[faceIndex].filter(sourcePoints.indices.contains)
            grouped[component, default: []].formUnion(vertices)
            if let centroid = projectedFaceCentroid(faceIndex),
               visibleEditableFace(at: centroid, removing: false) == faceIndex {
                visibleGrouped[component, default: []].formUnion(vertices)
            }
        }
        componentVertices = grouped
        var next: [TargetSculptBoundaryAnchor] = []
        for (colourIndex, component) in grouped.keys.sorted().enumerated() {
            let handleVertices = visibleGrouped[component]?.isEmpty == false
                ? visibleGrouped[component, default: []]
                : grouped[component, default: []]
            let projected = handleVertices.compactMap {
                projectedVertex($0).map { (point: $0.point, depth: $0.depth,
                                           vertexIndex: $0.vertexIndex) }
            }
            let hull = Self.convexHull(projected)
            let stride = max(1, Int(ceil(Double(hull.count) / 48.0)))
            for (index, item) in hull.enumerated() where index % stride == 0 {
                next.append(TargetSculptBoundaryAnchor(
                    point: item.point, depth: item.depth,
                    vertexIndex: item.vertexIndex,
                    componentID: component, colourIndex: colourIndex))
            }
        }
        boundaryAnchors = next
        selectionOverlay.boundaryAnchors = next
    }

    private func projectedVertex(_ index: Int)
        -> (point: CGPoint, depth: CGFloat, vertexIndex: Int)? {
        guard sourcePoints.indices.contains(index),
              let content = scene?.rootNode.childNode(
                withName: "target-sculpt-content", recursively: true) else {
            return nil
        }
        let world = content.convertPosition(sourcePoints[index], to: nil)
        let projected = projectPoint(world)
        guard projected.z >= 0, projected.z <= 1 else { return nil }
        return (CGPoint(x: projected.x, y: projected.y), projected.z, index)
    }

    private func projectedFaceCentroid(_ faceIndex: Int) -> CGPoint? {
        guard faces.indices.contains(faceIndex) else { return nil }
        let projected = faces[faceIndex].compactMap { projectedVertex($0)?.point }
        guard !projected.isEmpty else { return nil }
        let count = CGFloat(projected.count)
        return CGPoint(x: projected.reduce(0) { $0 + $1.x } / count,
                       y: projected.reduce(0) { $0 + $1.y } / count)
    }

    private func localDragVectorCM(from start: CGPoint, to end: CGPoint,
                                   depth: CGFloat) -> [Double]? {
        guard let content = scene?.rootNode.childNode(
            withName: "target-sculpt-content", recursively: true) else {
            return nil
        }
        let worldStart = unprojectPoint(SCNVector3(start.x, start.y, depth))
        let worldEnd = unprojectPoint(SCNVector3(end.x, end.y, depth))
        let localStart = content.convertPosition(worldStart, from: nil)
        let localEnd = content.convertPosition(worldEnd, from: nil)
        return [Double(localEnd.x - localStart.x),
                Double(localEnd.y - localStart.y),
                Double(localEnd.z - localStart.z)]
    }

    private func polygonLocalAnchor(at point: CGPoint) -> SCNVector3? {
        guard let content = scene?.rootNode.childNode(
            withName: "target-sculpt-content", recursively: true) else {
            return nil
        }
        // Use the target surface's median screen depth so a point may be
        // placed just outside its silhouette without accidentally attaching
        // to the mannequin or the studio floor.
        let depths = sourcePoints.indices.compactMap {
            projectedVertex($0)?.depth
        }.sorted()
        guard !depths.isEmpty else { return nil }
        let depth = depths[depths.count / 2]
        let world = unprojectPoint(SCNVector3(point.x, point.y, depth))
        return content.convertPosition(world, from: nil)
    }

    private func projectedPolygonPoints() -> [CGPoint] {
        guard let content = scene?.rootNode.childNode(
            withName: "target-sculpt-content", recursively: true) else {
            return []
        }
        return polygonAnchors.map { anchor in
            let world = content.convertPosition(anchor, to: nil)
            let projected = projectPoint(world)
            return CGPoint(x: projected.x, y: projected.y)
        }
    }

    private func refreshPolygonOverlay() {
        selectionOverlay.polygonPoints = projectedPolygonPoints()
    }

    private func localPatch(from seed: Int, within allowed: Set<Int>,
                            rings: Int) -> Set<Int> {
        var selected: Set<Int> = [seed]
        var frontier: Set<Int> = [seed]
        for _ in 0..<max(0, rings) {
            let next = Set(frontier.flatMap { vertexAdjacency[$0] ?? [] })
                .intersection(allowed).subtracting(selected)
            selected.formUnion(next)
            frontier = next
            if frontier.isEmpty { break }
        }
        return selected
    }

    private func clearTransientSelection() {
        polygonAnchors = []
        activeAnchor = nil
        dragStart = nil
        selectionOverlay.polygonPoints = []
        selectionOverlay.activeAnchor = nil
        selectionOverlay.dragPoint = nil
    }

    private static func makeVertexAdjacency(_ faces: [[Int]])
        -> [Int: Set<Int>] {
        var result = [Int: Set<Int>]()
        for face in faces where face.count >= 2 {
            for index in face.indices {
                let vertex = face[index]
                let previous = face[(index - 1 + face.count) % face.count]
                let next = face[(index + 1) % face.count]
                result[vertex, default: []].formUnion([previous, next])
            }
        }
        return result
    }

    private static func convexHull(
        _ points: [(point: CGPoint, depth: CGFloat, vertexIndex: Int)]
    ) -> [(point: CGPoint, depth: CGFloat, vertexIndex: Int)] {
        let sorted = points.sorted {
            $0.point.x == $1.point.x
                ? $0.point.y < $1.point.y : $0.point.x < $1.point.x
        }
        guard sorted.count > 2 else { return sorted }
        func cross(_ a: CGPoint, _ b: CGPoint, _ c: CGPoint) -> CGFloat {
            (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x)
        }
        var lower: [(point: CGPoint, depth: CGFloat, vertexIndex: Int)] = []
        for point in sorted {
            while lower.count >= 2,
                  cross(lower[lower.count - 2].point,
                        lower[lower.count - 1].point, point.point) <= 0 {
                lower.removeLast()
            }
            lower.append(point)
        }
        var upper: [(point: CGPoint, depth: CGFloat, vertexIndex: Int)] = []
        for point in sorted.reversed() {
            while upper.count >= 2,
                  cross(upper[upper.count - 2].point,
                        upper[upper.count - 1].point, point.point) <= 0 {
                upper.removeLast()
            }
            upper.append(point)
        }
        lower.removeLast()
        upper.removeLast()
        return lower + upper
    }

    private static func contains(_ point: CGPoint,
                                 polygon: [CGPoint]) -> Bool {
        guard polygon.count >= 3 else { return false }
        var inside = false
        var j = polygon.count - 1
        for i in polygon.indices {
            let a = polygon[i], b = polygon[j]
            let crosses = (a.y > point.y) != (b.y > point.y)
                && point.x < (b.x - a.x) * (point.y - a.y)
                    / (b.y - a.y) + a.x
            if crosses { inside.toggle() }
            j = i
        }
        return inside
    }

    private static func distance(_ lhs: CGPoint, _ rhs: CGPoint) -> CGFloat {
        hypot(lhs.x - rhs.x, lhs.y - rhs.y)
    }
}

struct TargetSculptSceneRepresentable: NSViewRepresentable {
    let points: [[Double]]
    let faces: [[Int]]
    let faceRegionIDs: [String]
    let faceComponentIDs: [String]
    let textureCoordinates: [[Double]]
    let removedFaces: Set<Int>
    let clearanceBands: [Int: String]
    let sourceImagePath: String?
    let avatarProfile: GarmentFactoryReactController.BaseAvatarProfile
    let tool: TargetSculptTool
    let onStroke: (Set<Int>, Bool) -> Void
    let onModifierDrag: (String, [Int], Int, [Double]) -> Void

    func makeNSView(context: Context) -> TargetSculptSCNView {
        let view = TargetSculptSCNView(frame: .zero)
        view.antialiasingMode = .multisampling4X
        view.preferredFramesPerSecond = 60
        view.rendersContinuously = false
        view.autoenablesDefaultLighting = false
        view.backgroundColor = NSColor(calibratedWhite: 0.035, alpha: 1)
        view.installSelectionOverlay()
        update(view)
        return view
    }

    func updateNSView(_ view: TargetSculptSCNView, context: Context) {
        update(view)
    }

    private func update(_ view: TargetSculptSCNView) {
        let geometryRevision = stableGeometryRevision
        let sceneRevision = stableSceneRevision(geometryRevision: geometryRevision)
        if view.requiresSceneUpdate(sceneRevision) {
            let built = FactoryProposedDressedSceneView.makeTargetSculptScene(
                points: points, faces: faces, faceRegionIDs: faceRegionIDs,
                textureCoordinates: textureCoordinates,
                removedFaces: removedFaces, sourceImagePath: sourceImagePath,
                clearanceBands: clearanceBands,
                avatarProfile: avatarProfile)
            view.installScene(
                built.scene,
                camera: built.scene.rootNode.childNode(
                    withName: "target-sculpt-camera", recursively: true),
                faceMappings: built.faceMappings,
                sceneRevision: sceneRevision,
                geometryRevision: geometryRevision,
                points: points, faces: faces,
                faceComponentIDs: faceComponentIDs,
                removedFaces: removedFaces)
        }
        view.setSculptTool(tool)
        view.scene?.rootNode.childNode(
            withName: "editable-fused-target-wire", recursively: true)?
            .isHidden = tool == .orbit
        view.onStroke = onStroke
        view.onModifierDrag = onModifierDrag
        view.allowsCameraControl = false
    }

    /// Stable FNV-1a revisions keep SwiftUI refreshes from rebuilding the
    /// SceneKit graph. Geometry and appearance are separate so a clearance
    /// recolour can preserve an unfinished polygon in garment-local space.
    private var stableGeometryRevision: UInt64 {
        var hash = Self.fnvOffset
        for point in points {
            for value in point { Self.mix(value.bitPattern, into: &hash) }
            Self.mix(0xFF, into: &hash)
        }
        for face in faces {
            for value in face { Self.mix(UInt64(bitPattern: Int64(value)), into: &hash) }
            Self.mix(0xFE, into: &hash)
        }
        for component in faceComponentIDs {
            Self.mix(component, into: &hash)
        }
        return hash
    }

    private func stableSceneRevision(geometryRevision: UInt64) -> UInt64 {
        var hash = geometryRevision
        for region in faceRegionIDs { Self.mix(region, into: &hash) }
        for coordinate in textureCoordinates {
            for value in coordinate { Self.mix(value.bitPattern, into: &hash) }
        }
        for face in removedFaces.sorted() {
            Self.mix(UInt64(bitPattern: Int64(face)), into: &hash)
        }
        for (face, band) in clearanceBands.sorted(by: { $0.key < $1.key }) {
            Self.mix(UInt64(bitPattern: Int64(face)), into: &hash)
            Self.mix(band, into: &hash)
        }
        Self.mix(sourceImagePath ?? "", into: &hash)
        Self.mix(avatarProfile.id, into: &hash)
        Self.mix(avatarProfile.geometryDigest, into: &hash)
        return hash
    }

    private static let fnvOffset: UInt64 = 14_695_981_039_346_656_037
    private static let fnvPrime: UInt64 = 1_099_511_628_211

    private static func mix(_ value: UInt64, into hash: inout UInt64) {
        var value = value
        for _ in 0..<8 {
            hash ^= value & 0xFF
            hash &*= fnvPrime
            value >>= 8
        }
    }

    private static func mix(_ value: String, into hash: inout UInt64) {
        for byte in value.utf8 {
            hash ^= UInt64(byte)
            hash &*= fnvPrime
        }
        hash ^= 0xFF
        hash &*= fnvPrime
    }
}

/// Compact, read-only pattern sheet for beginner chat.  It normalizes every
/// piece into one common canvas but never changes panel coordinates.
struct FactoryFlatPatternPreview: View {
    let pieces: [GarmentFactoryReactController.PreviewPiece]

    var body: some View {
        Canvas { context, size in
            let points = pieces.flatMap(\.outline).filter { $0.count >= 2 }
            guard let minX = points.map({ $0[0] }).min(),
                  let maxX = points.map({ $0[0] }).max(),
                  let minY = points.map({ $0[1] }).min(),
                  let maxY = points.map({ $0[1] }).max() else { return }
            let width = max(maxX - minX, 1), height = max(maxY - minY, 1)
            let scale = min((size.width - 18) / width, (size.height - 24) / height)
            for (index, piece) in pieces.enumerated() where piece.outline.count >= 3 {
                var path = Path()
                for (pointIndex, point) in piece.outline.enumerated() where point.count >= 2 {
                    let p = CGPoint(x: 9 + (point[0] - minX) * scale,
                                    y: 9 + (point[1] - minY) * scale)
                    if pointIndex == 0 { path.move(to: p) } else { path.addLine(to: p) }
                }
                path.closeSubpath()
                let hue = Double(index % 7) / 7.0
                context.fill(path, with: .color(Color(hue: hue, saturation: 0.35,
                                                      brightness: 0.72).opacity(0.20)))
                context.stroke(path, with: .color(Theme.sel.opacity(0.86)), lineWidth: 1.2)
                if let anchor = piece.outline.first, anchor.count >= 2 {
                    let labelPoint = CGPoint(x: 11 + (anchor[0] - minX) * scale,
                                             y: 12 + (anchor[1] - minY) * scale)
                    context.draw(Text(piece.name)
                        .font(.system(size: 6.5, weight: .medium))
                        .foregroundColor(Theme.dim), at: labelPoint, anchor: .topLeading)
                }
            }
            context.draw(Text("FLAT PATTERN · PROPOSED")
                .font(.system(size: 8, weight: .semibold, design: .monospaced))
                .foregroundColor(Theme.faint), at: CGPoint(x: 88, y: size.height - 7))
        }
        .background(Color.black.opacity(0.12), in: RoundedRectangle(cornerRadius: 7))
        .overlay(RoundedRectangle(cornerRadius: 7).stroke(Theme.faint.opacity(0.24)))
    }
}
