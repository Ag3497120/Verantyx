import Foundation
import Combine
import SwiftUI
import AppKit
import WebKit

// MARK: - Core data models

/// Tabs for the bottom slot of the editor's ResizableVSplit.
enum BottomPanelTab: String, CaseIterable, Identifiable {
    case terminal
    case memoryLayers

    var id: String { rawValue }

    @MainActor
    func displayName(_ app: AppState) -> String {
        switch self {
        case .terminal:     return app.t("Terminal", "ターミナル")
        case .memoryLayers: return app.t("Memory Layers", "記憶レイヤー")
        }
    }
}

struct ChatMessage: Identifiable, Equatable, Codable {
    var id: UUID
    var role: Role
    var content: String
    var timestamp = Date()
    var isSpotlight: Bool = false
    /// Immutable attachment snapshot for this turn.  Composer state is
    /// transient; without this field a sent image degraded into a filename
    /// marker and could not be previewed, enlarged, or restored with history.
    var attachments: [Attachment] = []
    /// 推論中のプロセスログのスナップショット（折りたたみ可能な Thinking ブロックに表示）
    var thinkingLog: [ThinkingLogEntry] = []

    init(id: UUID = UUID(), role: Role, content: String,
         isSpotlight: Bool = false,
         attachments: [Attachment] = [],
         thinkingLog: [ThinkingLogEntry] = []) {
        self.id = id
        self.role = role
        self.content = content
        self.isSpotlight = isSpotlight
        self.attachments = attachments
        self.thinkingLog = thinkingLog
    }

    enum Role: String, Codable { case user, assistant, system }

    struct Attachment: Identifiable, Codable, Equatable {
        enum Kind: String, Codable { case image, file }
        var id: UUID = UUID()
        var kind: Kind
        var name: String
        /// Absolute local source or transcript-cache path.  Rendering is
        /// fail-closed when it no longer exists; no placeholder is presented
        /// as if it were the uploaded image.
        var path: String
    }

    private enum CodingKeys: String, CodingKey {
        case id, role, content, timestamp, isSpotlight, attachments, thinkingLog
    }

    init(from decoder: Decoder) throws {
        let box = try decoder.container(keyedBy: CodingKeys.self)
        id = try box.decodeIfPresent(UUID.self, forKey: .id) ?? UUID()
        role = try box.decode(Role.self, forKey: .role)
        content = try box.decodeIfPresent(String.self, forKey: .content) ?? ""
        timestamp = try box.decodeIfPresent(Date.self, forKey: .timestamp) ?? Date()
        isSpotlight = try box.decodeIfPresent(Bool.self, forKey: .isSpotlight) ?? false
        attachments = try box.decodeIfPresent([Attachment].self, forKey: .attachments) ?? []
        thinkingLog = try box.decodeIfPresent([ThinkingLogEntry].self, forKey: .thinkingLog) ?? []
    }

    func encode(to encoder: Encoder) throws {
        var box = encoder.container(keyedBy: CodingKeys.self)
        try box.encode(id, forKey: .id)
        try box.encode(role, forKey: .role)
        try box.encode(content, forKey: .content)
        try box.encode(timestamp, forKey: .timestamp)
        try box.encode(isSpotlight, forKey: .isSpotlight)
        try box.encode(attachments, forKey: .attachments)
        try box.encode(thinkingLog, forKey: .thinkingLog)
    }

    // ProcessLogEntry の Codable スナップショット（Color は保存しないためシンプル化）
    struct ThinkingLogEntry: Identifiable, Codable, Equatable {
        var id = UUID()
        var timestamp: Date
        var text: String
        var kind: String    // "memory" | "tool" | "browser" | "thinking" | "system" | "perf"
    }
}


struct FileDiff: Identifiable, Equatable {
    let id = UUID()
    let fileURL: URL
    let originalContent: String
    let modifiedContent: String
    var hunks: [DiffHunk]

    var hasChanges: Bool { originalContent != modifiedContent }

    // Equatable: same identity ↔ same diff (new FileDiff always has new UUID)
    static func == (lhs: FileDiff, rhs: FileDiff) -> Bool { lhs.id == rhs.id }
}

struct DiffHunk: Identifiable {
    let id = UUID()
    var lines: [DiffLine]
}

struct DiffLine: Identifiable {
    let id = UUID()
    var kind: Kind
    var text: String

    enum Kind { case context, added, removed }
}

// MARK: - AppState

@MainActor
final class AppState: ObservableObject {

    /// Resolution actions are routed through this controller so focused tests
    /// can exercise the same AppState methods used by the sidebar against an
    /// injected persisted-factory door. Production keeps the canonical shared
    /// controller and therefore preserves existing project switching.
    private let garmentResolutionFactory: GarmentFactoryReactController

    init() {
        garmentResolutionFactory = .shared
    }

    init(garmentResolutionFactory: GarmentFactoryReactController) {
        self.garmentResolutionFactory = garmentResolutionFactory
    }

    // ── Global weak reference — set at launch so AgentToolExecutor can call
    // ingestArtifact() from actor context without importing the full SwiftUI stack.
    @MainActor static weak var shared: AppState?

    // ── IDE shell layout — tabs, left/right mounts, garment expand. One
    // model, persisted, read by IDEShellView and written to by anything
    // that opens a tab (file/folder pickers, aiShow*, panel-mount offers).
    // See ShellLayoutState.swift for why this replaced the old
    // `stageMode`/`aiPanels`/`activitySection` patchwork.
    let shell = ShellLayoutState()

    // Workspace
    @Published var activeWebViews: [String: WKWebView] = [:]
    @Published var workspaceURL: URL?
    @Published var workspaceFiles: [URL] = []


    // ── Act episode context ─────────────────────────────────────────────
    // The three things an action record needs that the action itself does
    // not carry: what the run is for, why the model picked this step, and
    // which episode the pointer trajectory belongs to. Set by AgentLoop
    // before tools run and read where the act is executed — see
    // EternalMemoryStore.recordActEpisode for why they are stored joined
    // rather than in three separate logs.
    @Published var currentActGoal: String = ""
    @Published var currentActRationale: String = ""
    @Published var currentEpisodeId: String = ""

    /// A non-chat surface shown FULL-WINDOW, the same way Vera-a mode
    /// takes over the layout — picked from the Gatekeeper chip's menu.
    /// nil = normal layout. See HumanPriorityModeView.fullSurfaceLayout.
    enum FullSurface: String, Identifiable {
        case mcp, veraSettings, growth, evolution
        var id: String { rawValue }
    }
    @Published var fullSurface: FullSurface? = nil
    
    // ── Distributed Cortex Connectivity (Handshake) ──
    @Published var cortexWorkspacePath: String? = nil
    @Published var cortexSkillsPath: String? = nil
    @Published var cortexSwarmActive: Bool = false
    @Published var swarmNodeCount: Int = 0
    @Published var swarmStatusText: String = "Offline"
    @Published var isCortexConnected: Bool = false
    @Published var selectedFile: URL? {
        didSet {
            // Notify Extension Host that a new document was opened
            if let file = selectedFile {
                ExtensionHostManager.shared.sendNotification(method: "workspace.didOpenTextDocument", params: [
                    "uri": file.path,
                    "languageId": file.pathExtension,
                    "version": 1,
                    "text": selectedFileContent
                ])
            }
        }
    }
    @Published var selectedFileContent: String = "" {
        didSet {
            // Notify Extension Host that the document content changed
            if let file = selectedFile {
                ExtensionHostManager.shared.sendNotification(method: "workspace.didChangeTextDocument", params: [
                    "uri": file.path,
                    "text": selectedFileContent,
                    "range": [
                        "startLine": 0,
                        "endLine": max(0, oldValue.filter { $0 == "\n" }.count)
                    ]
                ])
            }
        }
    }

    // Model
    @Published var modelStatus: ModelStatus = .none
    /// Name of the `.jgen` model currently being loaded (nil = idle), and the
    /// last load failure. Shared by the model-selector bar and the JGEN
    /// settings section so both show the same spinner/error.
    @Published var jgenLoadingModel: String?
    @Published var jgenLoadError: String?
    // ── いま作っている服 ────────────────────────────────────────
    //
    // 以前は「チャットの選択」だった場所を、服の選択に転用した。この
    // 道具では、会話の切替より **いま何を作っているか** の方が上位に
    // ある。台帳は服ごとに別なので、切替は台帳の切替でもある。
    @Published var garmentProjects: [String] = {
        UserDefaults.standard.stringArray(forKey: "garment_projects")
            ?? ["Black Coat"]
    }() {
        didSet { UserDefaults.standard.set(garmentProjects,
                                           forKey: "garment_projects") }
    }
    @Published var activeGarment: String = {
        UserDefaults.standard.string(forKey: "active_garment") ?? "Black Coat"
    }() {
        didSet { UserDefaults.standard.set(activeGarment,
                                           forKey: "active_garment") }
    }

    /// 名前だけの一覧に日付を添える。**台帳自体の作成日ではない** —
    /// 服の台帳は Vera 側の共有ストアで、この画面はいつ名前を登録したかしか
    /// 知らない。左レールが「プロジェクト」を服と会話で同じ形式(名前・種類・
    /// 作成日)で並べる以上、服の側だけ日付を持たないのは片手落ちになる。
    @Published var garmentProjectCreatedAt: [String: Date] = {
        guard let data = UserDefaults.standard.data(forKey: "garment_project_created_at"),
              let decoded = try? JSONDecoder().decode([String: Date].self, from: data)
        else { return [:] }
        return decoded
    }() {
        didSet {
            guard let data = try? JSONEncoder().encode(garmentProjectCreatedAt) else { return }
            UserDefaults.standard.set(data, forKey: "garment_project_created_at")
        }
    }

    /// 記録が無ければ「今」を返す純粋な読み出し ── 書き込みは
    /// `loadPersistedSettings()` が起動時に一度だけ済ませる
    /// (`backfillGarmentProjectDates`)。View の body から呼ばれる値なので、
    /// ここで @Published を書くと描画中に状態を変えることになり、
    /// SwiftUI の警告/再入の種になる。
    func createdDate(forGarment name: String) -> Date {
        garmentProjectCreatedAt[name] ?? Date()
    }

    /// 日付の無い名前(この機能より前からある "Black Coat" 等)に、
    /// 一度だけ「今」を振る。起動時に一回だけ呼ぶための関数 ── 呼ぶたびに
    /// 実行すると意味がない(初回で全部埋まる)ので副作用は起動経路からのみ。
    private func backfillGarmentProjectDates() {
        for name in garmentProjects where garmentProjectCreatedAt[name] == nil {
            garmentProjectCreatedAt[name] = Date()
        }
    }

    /// 服を増やす。**既存の台帳は触らない** — 増やすだけ。
    func newGarmentProject() {
        var n = 2
        var name = t("Garment \(n)", "服 \(n)")
        while garmentProjects.contains(name) {
            n += 1
            name = t("Garment \(n)", "服 \(n)")
        }
        garmentProjects.append(name)
        garmentProjectCreatedAt[name] = Date()
        // New and existing selections share one activation path. This keeps
        // the visible project, Python ledger and project-scoped resolution
        // consent in lockstep.
        activateGarmentProject(name)
    }

    /// UIの選択色だけでなく、Python側の台帳名前空間も同時に切り替える。
    /// 古いUI名だけが残っていて実体が無い場合は、その名前の空プロジェクトを
    /// 一度だけ作る。任意のコードフォルダは開かない。
    func activateGarmentProject(_ name: String) {
        guard garmentProjects.contains(name) else { return }
        activeGarment = name
        GarmentGenerationJob.shared.activateProject(name)
        garmentResolutionFactory.activateResolutionProject(name)
        Task { @MainActor in
            let raw = await MCPEngine.shared.callTool(
                serverName: "vera-memory", toolName: "project_open",
                arguments: ["name": name])
            guard let data = raw.data(using: .utf8),
                  let result = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  result["verdict"] as? String == "UNKNOWN_NO_SUCH_PROJECT" else { return }
            _ = await MCPEngine.shared.callTool(
                serverName: "vera-memory", toolName: "project_new",
                arguments: ["name": name])
        }
    }

    /// Select only the presentation route. The obligation remains OPEN until
    /// `resolveCrossObligation` verifies the matching persisted Python event.
    /// There is intentionally no compatibility success path when the factory
    /// did not publish the exact request/digest/project tuple.
    private func selectFactoryResolutionAction(
        _ kind: GarmentFactoryReactController.ResolutionActionKind,
        for request: GarmentResolutionRequest
    ) -> Bool {
        let factory = garmentResolutionFactory
        guard factory.activeResolutionProject == activeGarment,
              let pending = factory.pendingResolutionRequest else {
            addSystemMessage("永続工場に対応するOPEN解決要求がないため、操作を実行しませんでした。")
            return false
        }
        guard pending.id == request.id,
              pending.provenanceDigest == request.provenanceDigest else {
            addSystemMessage("解決要求が更新されたため、古い操作は実行しませんでした。")
            return false
        }
        return factory.selectResolutionAction(kind, requestID: request.id, by: "HUMAN")
    }

    @discardableResult
    func beginGarmentHumanInput(_ request: GarmentResolutionRequest) -> Bool {
        guard request.allows(GarmentResolutionRequest.enterOrMeasure) else { return false }
        return selectFactoryResolutionAction(.humanInput, for: request)
    }

    @discardableResult
    func beginGarmentGeometryEdit(_ request: GarmentResolutionRequest) -> Bool {
        guard request.allows(GarmentResolutionRequest.editGeometry) else { return false }
        return selectFactoryResolutionAction(.humanGeometryEdit, for: request)
    }

    @discardableResult
    func beginGarmentProviderConnection(_ request: GarmentResolutionRequest) -> Bool {
        guard request.allows(GarmentResolutionRequest.connectProvider) else { return false }
        return selectFactoryResolutionAction(.connectProvider, for: request)
    }

    func openGarmentProviderSettings() {
        openSettings(tab: "mcp")
    }

    private var garmentResolutionHumanActor: String {
        let fullName = NSFullUserName()
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return fullName.isEmpty ? "HUMAN_USER" : "HUMAN:\(fullName)"
    }

    private func reportGarmentResolutionFailure(
        _ outcome: GarmentFactoryReactController.ResolutionEventOutcome
    ) {
        addSystemMessage("\(outcome.verdict): \(outcome.message)")
    }

    @discardableResult
    func grantOneTimeGarmentLLMProposal(
        _ request: GarmentResolutionRequest
    ) async -> Bool {
        let factory = garmentResolutionFactory
        let project = activeGarment
        let outcome = await factory.grantOneTimeLLMProposalConsent(
            requestID: request.id,
            provenanceDigest: request.provenanceDigest,
            projectName: project,
            by: garmentResolutionHumanActor)
        guard outcome.accepted,
              let consentDigest = outcome.consentDigest,
              let boundWorkflowDigest = outcome.boundWorkflowDigest,
              GarmentGenerationJob.shared.recordOneTimeLLMProposalConsent(
                requestID: request.id,
                engineConsentDigest: consentDigest,
                boundWorkflowDigest: boundWorkflowDigest) else {
            factory.revokeLLMProposalConsent()
            GarmentGenerationJob.shared.revokeLLMProposalConsent()
            reportGarmentResolutionFailure(outcome)
            return false
        }
        addSystemMessage(outcome.message)
        return true
    }

    func revokeGarmentLLMProposalConsent() {
        GarmentGenerationJob.shared.revokeLLMProposalConsent()
        garmentResolutionFactory.revokeLLMProposalConsent()
    }

    func submitGarmentResolution(
        _ request: GarmentResolutionRequest,
        values: [String: String], measured: Bool
    ) async -> Bool {
        let scoped = values.mapValues {
            $0.trimmingCharacters(in: .whitespacesAndNewlines)
        }.filter { !$0.value.isEmpty }
        guard Set(scoped.keys) == Set(request.missingFields) else {
            addSystemMessage("型付き解決要求に列挙された全項目を入力してください。")
            return false
        }
        let project = activeGarment
        let path: GarmentFactoryReactController.CrossResolutionPath = measured
            ? .measuredInput : .humanInput
        let outcome = await garmentResolutionFactory
            .resolveCrossObligation(
                requestID: request.id,
                provenanceDigest: request.provenanceDigest,
                projectName: project,
                path: path,
                values: scoped,
                actor: garmentResolutionHumanActor)
        guard outcome.accepted else {
            reportGarmentResolutionFailure(outcome)
            return false
        }
        _ = GarmentGenerationJob.shared.recordAcceptedHumanResolution(
            request, projectName: project, values: scoped,
            measured: measured)
        addSystemMessage(outcome.message)
        return true
    }

    /// Called by the proposal provider after it has produced values under an
    /// already persisted one-shot grant. The proposal cannot resolve through
    /// a chat marker and remains capped at PROPOSED in both ledgers.
    func submitOneTimeGarmentLLMProposal(
        _ request: GarmentResolutionRequest,
        values: [String: String], modelID: String
    ) async -> Bool {
        let job = GarmentGenerationJob.shared
        guard let consent = job.activeLLMResolutionConsent,
              consent.requestID == request.id,
              consent.projectName == activeGarment,
              consent.provenanceDigest == request.provenanceDigest else {
            addSystemMessage("このrequest/digest/projectに限定したLLM提案許可がありません。")
            return false
        }
        let scoped = values.mapValues {
            $0.trimmingCharacters(in: .whitespacesAndNewlines)
        }.filter { !$0.value.isEmpty }
        guard Set(scoped.keys) == Set(request.missingFields) else {
            addSystemMessage("LLM提案は許可された全項目だけを返す必要があります。")
            return false
        }
        let project = activeGarment
        let outcome = await garmentResolutionFactory
            .resolveCrossObligation(
                requestID: request.id,
                provenanceDigest: request.provenanceDigest,
                projectName: project,
                path: .consentedLLMProposal,
                values: scoped,
                actor: "LLM:\(modelID)",
                consentDigest: consent.engineConsentDigest)
        guard outcome.accepted else {
            reportGarmentResolutionFailure(outcome)
            return false
        }
        _ = job.recordAcceptedLLMProposalResolution(
            request, projectName: project, values: scoped)
        addSystemMessage(outcome.message)
        return true
    }

    func submitGarmentGeometryResolution(
        _ request: GarmentResolutionRequest,
        editArtifacts: [String: String]
    ) async -> Bool {
        let scoped = editArtifacts.mapValues {
            $0.trimmingCharacters(in: .whitespacesAndNewlines)
        }.filter { !$0.value.isEmpty }
        guard Set(scoped.keys) == Set(request.missingFields) else {
            addSystemMessage("編集結果は要求された全形状項目へ紐付けてください。")
            return false
        }
        let project = activeGarment
        let outcome = await garmentResolutionFactory
            .resolveCrossObligation(
                requestID: request.id,
                provenanceDigest: request.provenanceDigest,
                projectName: project,
                path: .humanEdit,
                values: scoped,
                actor: garmentResolutionHumanActor)
        guard outcome.accepted else {
            reportGarmentResolutionFailure(outcome)
            return false
        }
        _ = GarmentGenerationJob.shared.recordAcceptedGeometryResolution(
            request, projectName: project, values: scoped)
        addSystemMessage(outcome.message)
        return true
    }

    func connectGarmentProvider(
        _ request: GarmentResolutionRequest
    ) async -> Bool {
        let outcome = await garmentResolutionFactory
            .resolveCrossObligation(
                requestID: request.id,
                provenanceDigest: request.provenanceDigest,
                projectName: activeGarment,
                path: .connectProvider,
                actor: garmentResolutionHumanActor,
                resumeAfterAcceptance: false)
        guard outcome.accepted else {
            reportGarmentResolutionFailure(outcome)
            return false
        }
        addSystemMessage(outcome.message)
        openGarmentProviderSettings()
        return true
    }

    func continueGarmentWithBoundedAlternatives(
        _ request: GarmentResolutionRequest
    ) async -> Bool {
        let bounded: [String: Any] = Dictionary(uniqueKeysWithValues:
            request.missingFields.map {
                ($0, ["UNKNOWN", "LOW_BOUND", "HIGH_BOUND"])
            })
        let project = activeGarment
        let outcome = await garmentResolutionFactory
            .resolveCrossObligation(
                requestID: request.id,
                provenanceDigest: request.provenanceDigest,
                projectName: project,
                path: .boundedAlternatives,
                values: bounded,
                actor: garmentResolutionHumanActor)
        guard outcome.accepted else {
            reportGarmentResolutionFailure(outcome)
            return false
        }
        _ = GarmentGenerationJob.shared.recordAcceptedBoundedAlternative(
            request, projectName: project)
        addSystemMessage(outcome.message)
        return true
    }

    func stopGarmentResolution(
        _ request: GarmentResolutionRequest
    ) async -> Bool {
        let project = activeGarment
        let outcome = await garmentResolutionFactory
            .resolveCrossObligation(
                requestID: request.id,
                provenanceDigest: request.provenanceDigest,
                projectName: project,
                path: .typedStop,
                actor: garmentResolutionHumanActor,
                resumeAfterAcceptance: false)
        guard outcome.accepted else {
            reportGarmentResolutionFailure(outcome)
            return false
        }
        GarmentGenerationJob.shared.recordAcceptedStop(
            request, projectName: project)
        if isGenerating { cancelGeneration() }
        addSystemMessage(outcome.message)
        return true
    }

    @Published var ollamaModels: [String] = []
    // activeOllamaModel は下記(L412付近)でdidSetつきで宣言済み
    @Published var anthropicApiKey: String = "" {
        didSet {
            // Anthropic API キーを AnthropicClient に反映
            Task { await AnthropicClient.shared.configure(apiKey: anthropicApiKey) }
            UserDefaults.standard.set(anthropicApiKey, forKey: "anthropic_api_key")
        }
    }
    @Published var activeAnthropicModel: String = {
        UserDefaults.standard.string(forKey: "anthropic_model") ?? "claude-sonnet-4-5"
    }() {
        didSet { UserDefaults.standard.set(activeAnthropicModel, forKey: "anthropic_model") }
    }
    @Published var activeOpenAIModel: String = {
        UserDefaults.standard.string(forKey: "openai_model") ?? "gpt-4o"
    }() {
        didSet { UserDefaults.standard.set(activeOpenAIModel, forKey: "openai_model") }
    }
    @Published var activeGeminiModel: String = {
        UserDefaults.standard.string(forKey: "gemini_model") ?? "gemini-3.1-pro"
    }() {
        didSet { UserDefaults.standard.set(activeGeminiModel, forKey: "gemini_model") }
    }
    @Published var activeDeepSeekModel: String = {
        UserDefaults.standard.string(forKey: "deepseek_model") ?? "deepseek-coder"
    }() {
        didSet { UserDefaults.standard.set(activeDeepSeekModel, forKey: "deepseek_model") }
    }
    @Published var customHFRepoId: String = "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit"
    @Published var downloadProgress: Double = 0

    // Chat
    @Published var messages: [ChatMessage] = []
    @Published var inputText: String = ""
    @Published var isGenerating = false {
        didSet {
            guard oldValue != isGenerating else { return }
            // Holding another app in front is only defensible while we are
            // actually driving it. The run ends in a dozen different places
            // (done, error, cancel, fallback), so release here rather than
            // trusting every one of them to remember.
            if oldValue && !isGenerating {
                ForegroundAppOperator.shared.stopHoldingFocus()
            }
            // The menu-bar icon is the run indicator you can still see when
            // the window is buried, so it has to hear about this.
            NotificationCenter.default.post(name: .veraRunStateChanged, object: nil)
        }
    }

    /// Whether tool/system log lines are shown in the transcript. Answers are
    /// always shown; this only folds away the running commentary, which on a
    /// long agent run buries the reply it was working towards.
    @Published var showSystemLogs: Bool = UserDefaults.standard.object(forKey: "show_system_logs") as? Bool ?? true {
        didSet { UserDefaults.standard.set(showSystemLogs, forKey: "show_system_logs") }
    }

    // Self-Fix mode — when true, next message(s) target IDE self-modification
    // Must be explicitly toggled by user pressing the "Self Fix" button.
    @Published var selfFixMode: Bool = false
    @Published var persistentTaskAnchor: String = "" // 毎ターン自動注入されるタスクの画像アンカー
    /// Set to true when the AI calls [RESTART_IDE] — triggers a restart alert in the UI.
    @Published var showRestartAlert: Bool = false
    @Published var requiresHumanPuzzle: Bool = false {
        didSet {
            guard oldValue != requiresHumanPuzzle else { return }
            if requiresHumanPuzzle { AgentActivityCenter.shared.set(.waitingUser) }
        }
    }
    @Published var isAgentControllingMouse: Bool = false {
        didSet {
            guard oldValue != isAgentControllingMouse else { return }
            NotificationCenter.default.post(name: .veraRunStateChanged, object: nil)
        }
    }
    @Published var isSwarmMode: Bool = false // 🐝 Swarm Pipeline Mode
    @Published var lastEntropy: [CGPoint]? = nil
    @Published var lastVideoFrames: [String]? = nil
    /// Set by `[DESKTOP_ACT]` click handling (`AgentTool.swift`) whenever
    /// `VisualDiffRegion` finds a changed region for the most recent click
    /// -- read (and cleared) by `AgentLoop.swift` right after the tool call
    /// so `UITestVectorTrace.recordMoment` can size/place the step's node.
    @Published var lastDesktopChangedRegion: CGRect? = nil
    @Published var lastKeyboardEntropy: [Double]? = nil
    @Published var lastEntropyTimestamp: Date? = nil
    @Published var searchCooldownUntil: Date? = nil
    var lastKeystrokeTime: Date? = nil

    // Attachments (images + files for multimodal inference)
    @Published var attachedImages: [AttachedImage] = []
    @Published var attachedFiles: [URL] = []

    /// Files attached in a turn that has been OFFERED to the store and
    /// not yet answered. Ingest is never automatic: an attachment is a
    /// file the person wanted the conversation to see, which is not the
    /// same as a document they want the store to hold forever, and
    /// deciding that for them is exactly the invisible ingest this
    /// engine refuses everywhere else.
    /// Which registered document vocabulary speaks. Empty = the shared
    /// map only. Persisted because an operator sets it once for a
    /// deployment, not once per launch.
    @Published var veraDomain: String = UserDefaults.standard
        .string(forKey: "vera_domain") ?? "" {
        didSet { UserDefaults.standard.set(veraDomain, forKey: "vera_domain") }
    }
    /// Refuse rather than fall through to the shared vocabulary. The safe
    /// side for a deployment: 「知らない」 beats an encyclopedia's sense of
    /// a term of art, and nothing on screen would have shown the swap.
    @Published var veraDomainOnly: Bool = UserDefaults.standard
        .bool(forKey: "vera_domain_only") {
        didSet { UserDefaults.standard.set(veraDomainOnly,
                                           forKey: "vera_domain_only") }
    }
    /// 取り込んだ文書だけを引く面に切り替える。
    ///
    /// 品質の改善ではなく契約の宣言である。実測 2026-08-18、核2,779の店で
    /// 7問を両面に当てたところ、文書に載っている4問は返答が完全に一致し、
    /// 分かれたのは2問だけ — 「正当防衛とは」は文書面が拒否して chat が
    /// SEEDED の空虚な節を3つ返し(文書面が優る)、「3たす4は」は chat が
    /// 正しく 7 を返して文書面が拒否した(文書面が劣る)。だから既定は off。
    /// 「社内文書に書いてあることしか答えない」が要件である配備でだけ、
    /// 算術も一般知識も落ちることを承知の上で入れる。
    @Published var veraDocumentsOnly: Bool = UserDefaults.standard
        .bool(forKey: "vera_documents_only") {
        didSet { UserDefaults.standard.set(veraDocumentsOnly,
                                           forKey: "vera_documents_only") }
    }
    @Published var pendingIngest: [URL] = []

    // Inference task handle (for cancellation)
    private var inferenceTask: Task<Void, Never>? = nil

    // UUID of the assistant message bubble currently receiving streaming tokens.
    // Elevated to instance-level so restoreSession() can nil it on session switch,
    // preventing stale UUIDs from corrupting a newly-loaded session's first stream.
    var streamingMsgId: UUID? = nil

    // Agent-loop .streamToken buffering — the Ollama/MLX direct paths
    // already batch UI updates to ~25fps (40ms); the agent-loop path
    // (LoopEvent.streamToken, handled below) had no such throttle, so
    // `messages[idx].content += token` fired (and re-rendered the whole
    // ChatTranscriptView) once per token. Buffered the same way here.
    private var streamTokenBuffer: String = ""
    private var lastStreamFlush: Date = .distantPast

    private func flushStreamTokenBuffer() {
        guard !streamTokenBuffer.isEmpty else { return }
        if let sid = streamingMsgId, let idx = messages.firstIndex(where: { $0.id == sid }) {
            messages[idx].content += streamTokenBuffer
        } else {
            let msg = ChatMessage(role: .assistant, content: streamTokenBuffer)
            streamingMsgId = msg.id
            messages.append(msg)
        }
        streamTokenBuffer = ""
        lastStreamFlush = Date()
    }

    // ── Performance metrics (the "Apple Silicon violence" numbers) ──
    @Published var tokensPerSecond: Double = 0       // live tok/s display
    @Published var totalTokensGenerated: Int = 0     // session total
    @Published var streamingText: String = ""        // current token buffer for live render
    @Published var inferenceMs: Int = 0              // last response latency ms

    // ── Zero-Translation Steering Signal ──
    // Publisher that emits commands (like "^C", "cd src/auth") entered in the LiveTerminalView.
    // The AgentLoop will subscribe to this and interrupt its current task immediately.
    let steeringSubject = PassthroughSubject<String, Never>()
    
    func sendSteeringCommand(_ cmd: String) {
        logProcess("❯ \(cmd)", kind: .system)
        steeringSubject.send(cmd)
    }

    // ── Process log ("what is the AI thinking right now") ──
    @MainActor
    final class ProcessLogStore: ObservableObject {
        @Published var entries: [ProcessLogEntry] = []
    }
    let logStore = ProcessLogStore()
    
    @Published var showProcessLog: Bool = true

    struct ProcessLogEntry: Identifiable {
        let id = UUID()
        let timestamp: Date
        var text: String
        var kind: Kind

        enum Kind: String { case memory, tool, browser, thinking, system, perf }

        var prefix: String {
            switch kind {
            case .memory:   return "→ MEM  "
            case .tool:     return "→ TOOL "
            case .browser:  return "→ DOM  "
            case .thinking: return "▶ THINK"
            case .system:   return "⋯ SYS  "
            case .perf:     return "⚡ PERF "
            }
        }

        var color: Color {
            switch kind {
            case .memory:   return Theme.ok
            case .tool:     return Color(red: 0.4, green: 0.8, blue: 1.0)
            case .browser:  return Theme.warn
            case .thinking: return Color(red: 0.8, green: 0.8, blue: 1.0)
            case .system:   return Theme.dim
            // memory と同じ Theme.ok に丸めると2行が同色になり見分けがつかない
            // (元は 0.4/0.9/0.6 と 0.3/1.0/0.5 の近似だが別の緑だった) ため
            // perf だけは accent で視覚的に分離する。
            case .perf:     return Theme.accent
            }
        }
    }

    // Diff
    @Published var pendingDiff: FileDiff?
    @Published var showDiff = false
    @Published var autoApproveDiffs: Bool = false

    // Human Mode: file write / create / edit approval
    @Published var pendingFileApproval: FileApprovalRequest? = nil

    // Vera-α layer: preview-before-save approval (see VeraMemoryBridge.swift)
    /// A 4-layer setup awaiting the user's approval. Presented as a sheet;
    /// nothing is applied until they press Apply.
    @Published var pendingSetupProposal: SetupProposal? = nil
    @Published var pendingVeraSave: VeraSaveApprovalRequest? = nil
    @Published var pendingVeraSaveQueue: [VeraSaveApprovalRequest] = []

    /// .perTurn (default): the agent loop blocks each turn until the
    /// human approves/rejects that turn's save -- what shipped originally.
    /// .batched: the agent keeps working uninterrupted; save requests
    /// queue up in pendingVeraSaveQueue for the human to review in bulk
    /// whenever they check back. See VeraMemoryBridge.requestSaveApproval.
    @Published var veraSaveApprovalMode: VeraSaveApprovalMode = .perTurn {
        didSet { UserDefaults.standard.set(veraSaveApprovalMode.rawValue, forKey: "vera_save_approval_mode") }
    }

    /// jgen × vera-a: after an APPROVED save, Vera proposes a skill from
    /// the memory and applies it where the JGEN harness recalls from
    /// (SkillLibrary for the Act limbs, eternal memory for Speak). See
    /// VeraJGenSkillProposer. Default ON; the applied skill only wraps a
    /// vera-memory lookup of the memory the human just approved.
    @Published var veraProposeSkillsToJGen: Bool =
        UserDefaults.standard.object(forKey: "vera_propose_skills_jgen") as? Bool ?? true {
        didSet { UserDefaults.standard.set(veraProposeSkillsToJGen, forKey: "vera_propose_skills_jgen") }
    }

    /// Stereo-cross 3D graph demo mode: replaces the code editor pane with
    /// a live SceneKit visualization of Vera's CrossStore (StereoCrossGraphView).
    /// While active, the Vera-α save-approval UI moves from a center-screen
    /// sheet into the chat transcript itself (see AgentChatView), and an
    /// approved save triggers a "connection" animation in the graph.
    @Published var showStereoCrossGraph: Bool = false
    /// Set by VeraMemoryBridge right after a save is approved while this
    /// mode is active; StereoCrossGraphView observes this to animate the
    /// new fact "connecting" into the structure, then clears it back to nil.
    @Published var pendingGraphConnection: String? = nil
    /// Real core key(s) VeraMemoryBridge.performSave actually saved under
    /// (from `remember`/`record_code_change`'s response), set alongside
    /// `pendingGraphConnection`. StereoCrossGraphView passes these as
    /// `focus_cores` when refreshing so a brand-new, low-pour-count fact is
    /// guaranteed to appear as a node instead of being crowded out by the
    /// top-ranked existing cores.
    @Published var pendingGraphFocusCores: [String] = []

    /// Shows the live mirror of whatever window HiddenWindowAutomation has
    /// parked off-screen, so the user can watch autonomous OS-agent
    /// operation without it visually stealing focus or covering the IDE.

    /// Shows the JGEN Vector Lab: text-in/text-out exploration of
    /// JCrossEngine's raw hidden-state operations (encode, resynthesize,
    /// puzzle_inference's confidence/entropy, optimize_thought_in_place's
    /// latent gradient descent) -- independent of the normal chat path.
    @Published var showVectorLab: Bool = false

    /// Which view occupies the bottom slot of the editor's ResizableVSplit:
    /// the real terminal, or the L1-L3 memory-injection preview.
    @Published var bottomPanelTab: BottomPanelTab = .terminal

    // Active tab in the center chat panel — driven by AppState so
    // SessionHistoryView can programmatically switch to .workspace
    // after restoring a session (the tab @State lives in AgentChatView).
    @Published var activeChatTab: Int = 0   // 0=workspace, 1=history, 2=thinking

    // Operation Mode (AI Priority vs Human)
    // Gatekeeper is no longer the default operating mode: its premise was
    // that source code must never reach a cloud LLM, but enterprise
    // contracts now routinely forbid training on submitted code, so the
    // obfuscation round-trip costs accuracy for a risk that is handled
    // contractually. The mode still exists (opt-in) — see OperationMode.
    @Published var operationMode: OperationMode = .automatic {
        didSet {
            UserDefaults.standard.set(operationMode.rawValue, forKey: "operation_mode")
            // Sync MCPEngine execution mode.
            //
            // **遅延初期化されるシングルトンに、初期化中に走る監視から
            // 触らない。** この didSet は AppState が保存済みのモードを
            // 読み込む時点で走る。そこで `MCPEngine.shared` に触ると、
            // その `once` が進行中の場合に同じ once を待って再入し、
            // `_dispatch_once_wait` で落ちる(2026-08-22、起動時
            // EXC_BREAKPOINT のクラッシュログで確認)。
            //
            // 1ティック譲ってから触る。譲った先では init は必ず
            // 終わっているので、待ちも再入も起きない。
            Task { @MainActor in
                await Task.yield()
                MCPEngine.shared.setMode(.ai)
            }
            
            // Auto-toggle JCross view and Gatekeeper State
            if operationMode == .gatekeeper {
                GatekeeperModeState.shared.isEnabled = true
                showGatekeeperRawCode = false
            } else {
                GatekeeperModeState.shared.isEnabled = false
                showGatekeeperRawCode = true
            }
            

            // L2.5 変換の制御 (自動実行は削除し、UI側の明示的なアクションまたは確認ダイアログに委ねる)
        }
    }

    // ── Non-Coding Task Routing ──
    enum NonCodingTaskEngine: String, CaseIterable, Codable {
        case localAgent = "Local Agent (Safe)"
        case cloudDirect = "Cloud Direct (MCP Tools)"
    }
    
    @Published var nonCodingTaskEngine: NonCodingTaskEngine = {
        let raw = UserDefaults.standard.string(forKey: "non_coding_engine") ?? NonCodingTaskEngine.localAgent.rawValue
        return NonCodingTaskEngine(rawValue: raw) ?? .localAgent
    }() {
        didSet { UserDefaults.standard.set(nonCodingTaskEngine.rawValue, forKey: "non_coding_engine") }
    }

    // ── Swarm Strategy ──
    enum SwarmStrategy: String, CaseIterable, Codable, Identifiable {
        case auto      = "Auto"
        case ultrawork = "Ultrawork"
        case ralph     = "Ralph"
        var id: String { rawValue }

        var displayName: String {
            switch self {
            case .auto:      return "Auto"
            case .ultrawork: return "Ultrawork"
            case .ralph:     return "Ralph"
            }
        }
    }

    @Published var activeSwarmStrategy: SwarmStrategy = {
        let raw = UserDefaults.standard.string(forKey: "active_swarm_strategy") ?? SwarmStrategy.auto.rawValue
        return SwarmStrategy(rawValue: raw) ?? .auto
    }() {
        didSet { UserDefaults.standard.set(activeSwarmStrategy.rawValue, forKey: "active_swarm_strategy") }
    }

    // ── Auditor (監視役) ──
    @Published var activeAuditorModel: String = {
        UserDefaults.standard.string(forKey: "active_auditor_model") ?? "llama3.1:8b"
    }() {
        didSet { UserDefaults.standard.set(activeAuditorModel, forKey: "active_auditor_model") }
    }
    @Published var isAuditorEnabled: Bool = {
        UserDefaults.standard.bool(forKey: "is_auditor_enabled")
    }() {
        didSet { UserDefaults.standard.set(isAuditorEnabled, forKey: "is_auditor_enabled") }
    }

    // ── Fine-Tuning ──
    @Published var fineTuningBaseModel: String = {
        UserDefaults.standard.string(forKey: "fine_tuning_base_model") ?? "llama3.1:8b"
    }() {
        didSet { UserDefaults.standard.set(fineTuningBaseModel, forKey: "fine_tuning_base_model") }
    }

    func clearFineTuningData() {
        let cortexWs = UserDefaults.standard.string(forKey: "cortex_workspace_path") ?? UserDefaults.standard.string(forKey: "last_workspace_path") ?? "/tmp"
        let baseDir = URL(fileURLWithPath: cortexWs).appendingPathComponent(".openclaw/memory/training_data")
        let datasetURL = baseDir.appendingPathComponent("verantyx_dataset.jsonl")
        
        if FileManager.default.fileExists(atPath: datasetURL.path) {
            let timestamp = Int(Date().timeIntervalSince1970)
            let archiveURL = baseDir.appendingPathComponent("verantyx_dataset_archive_\(timestamp).jsonl")
            try? FileManager.default.moveItem(at: datasetURL, to: archiveURL)
            self.addSystemMessage("🧹 The fine-tuning data has been archived to prevent duplicate training.")
        }
    }

    // Artifacts (Claude-style live preview)
    @Published var currentArtifact: Artifact? = nil
    @Published var artifactHistory: [Artifact] = []
    @Published var showArtifactPanel: Bool = false

    // Privacy Shield / Hybrid mode
    @Published var inferenceMode: InferenceMode = .localOnly {
        didSet { UserDefaults.standard.set(inferenceMode.rawValue, forKey: "inference_mode") }
    }
    /// Stable identity for this Mac, used by the distributed-inference pairing
    /// handshake (Milestone U) to name a peer and to break a both-claim-master
    /// tie deterministically.
    ///
    /// Migrated from the removed Exo integration's `exo_device_id` so existing
    /// installs keep the identity they already advertised, rather than looking
    /// like a brand-new machine after an update.
    @Published var pipeDeviceId: String = {
        if let id = UserDefaults.standard.string(forKey: "pipe_device_id") { return id }
        if let legacy = UserDefaults.standard.string(forKey: "exo_device_id") {
            UserDefaults.standard.set(legacy, forKey: "pipe_device_id")
            return legacy
        }
        let newId = UUID().uuidString
        UserDefaults.standard.set(newId, forKey: "pipe_device_id")
        return newId
    }()
    @Published var cloudProvider: CloudProvider = .claude {
        didSet { UserDefaults.standard.set(cloudProvider.rawValue, forKey: "cloud_provider") }
    }
    @Published var lastMaskingStats: MaskingStats?
    @Published var privacySteps: [String] = []
    @Published var paranoiaLogLines: [ParanoiaEngine.ParanoiaLogLine] = []  // Paranoia Mode live log

    // ── Model configuration (all persisted via UserDefaults) ──
    @Published var temperature: Double = 0.1 {
        didSet { UserDefaults.standard.set(temperature, forKey: "model_temperature") }
    }
    @Published var maxTokensOllama: Int = 2048 {
        didSet { UserDefaults.standard.set(maxTokensOllama, forKey: "max_tokens_ollama") }
    }
    @Published var maxTokensMLX: Int = 4096 {
        didSet { UserDefaults.standard.set(maxTokensMLX, forKey: "max_tokens_mlx") }
    }
    /// 0 = auto (use ModelTier.compressThreshold based on detected model
    /// size); any positive value overrides how much conversation history
    /// (chars) stays uncompressed before CortexEngine.compressIfNeeded
    /// kicks in. See AgentLoop.swift's `compressThreshold` computation.
    @Published var contextWindowOverride: Int = 0 {
        didSet { UserDefaults.standard.set(contextWindowOverride, forKey: "context_window_override") }
    }

    /// 0 = auto (tier table). Any positive value overrides the per-turn
    /// generation budget EVERYWHERE — the tier table stops being a ceiling
    /// the moment the user sets this, including the JGen safety clamp.
    @Published var maxTokensOverride: Int =
        UserDefaults.standard.integer(forKey: "max_tokens_override") {
        didSet { UserDefaults.standard.set(maxTokensOverride, forKey: "max_tokens_override") }
    }

    /// The model-name string used for tier/budget lookups (e.g.
    /// `ContextBudgetManager.budget(for:)`), extracted from whichever
    /// `ModelStatus` case is currently active. `nil` when no model is loaded.
    var activeModelName: String? {
        switch modelStatus {
        case .ready(let name): return name
        case .ollamaReady(let model): return model
        case .anthropicReady(let model, _): return model
        case .claudeAgentReady(let model): return model
        case .mlxReady(let model): return model
        case .mlxDownloading(let model): return model
        case .bitnetReady(let model): return model
        case .jcrossReady(let model): return model
        case .lmStudioReady(let model): return model
        case .none, .connecting, .downloading, .error: return nil
        }
    }
    @Published var ollamaEndpoint: String = "http://localhost:11434" {
        didSet { UserDefaults.standard.set(ollamaEndpoint, forKey: "ollama_endpoint") }
    }
    /// LM Studio's OpenAI-compatible server. Unlike Ollama it is not started
    /// automatically, so an unreachable endpoint here is the normal state until
    /// the user turns the Local Server on.
    /// Distributed inference pairing. Strictly opt-in: enabling it opens a port
    /// to the local network, so it must never default on.
    @Published var pipePairingEnabled: Bool = UserDefaults.standard.bool(forKey: "pipe_pairing_enabled") {
        didSet {
            UserDefaults.standard.set(pipePairingEnabled, forKey: "pipe_pairing_enabled")
            Task { @MainActor in
                if pipePairingEnabled { await PipeCoordinator.shared.enable() }
                else { PipeCoordinator.shared.disable() }
            }
        }
    }
    @Published var lmStudioEndpoint: String = {
        UserDefaults.standard.string(forKey: "lmstudio_endpoint") ?? LMStudioClient.defaultEndpoint
    }() {
        didSet { UserDefaults.standard.set(lmStudioEndpoint, forKey: "lmstudio_endpoint") }
    }
    @Published var activeLMStudioModel: String = {
        UserDefaults.standard.string(forKey: "active_lmstudio_model") ?? ""
    }() {
        didSet { UserDefaults.standard.set(activeLMStudioModel, forKey: "active_lmstudio_model") }
    }
    @Published var systemPrompt: String = "You are Verantyx, an expert AI coding assistant running on Apple Silicon. Be concise and precise. Prefer code over prose." {
        didSet { UserDefaults.standard.set(systemPrompt, forKey: "system_prompt") }
    }
    @Published var streamingEnabled: Bool = true {
        didSet { UserDefaults.standard.set(streamingEnabled, forKey: "streaming_enabled") }
    }

    // ── Tool toggles ──
    @Published var toolBrowserEnabled: Bool = true {
        didSet { UserDefaults.standard.set(toolBrowserEnabled, forKey: "tool_browser") }
    }
    @Published var toolWebSearchEnabled: Bool = true {
        didSet { UserDefaults.standard.set(toolWebSearchEnabled, forKey: "tool_web_search") }
    }
    // ── 不足知識時ウェブ検索の細粒度制御(2026-08-19) ──────────────────
    // 発火条件は一つに固定: Veraモードで型付き拒否(UNKNOWN*)が出たとき
    // だけ。答えが立った質問で外に出ることは構造上ない。以下はその上の
    // ダイヤル。
    /// 実行前に確認する — ONなら拒否時に案内だけ出し、「検索して」で実行。
    @Published var veraWebAskFirst: Bool = UserDefaults.standard
        .object(forKey: "vera_web_ask_first") as? Bool ?? true {
        didSet { UserDefaults.standard.set(veraWebAskFirst, forKey: "vera_web_ask_first") }
    }
    /// 開くページ数の上限(1〜4)。
    @Published var veraWebMaxPages: Int = {
        let v = UserDefaults.standard.integer(forKey: "vera_web_max_pages")
        return v == 0 ? 2 : min(max(v, 1), 4)
    }() {
        didSet { UserDefaults.standard.set(veraWebMaxPages, forKey: "vera_web_max_pages") }
    }
    /// 取得した抜粋を承認キュー(propose_web_evidence)へ提案する。
    /// 提案されても人が accept するまで ask() からは見えない。
    @Published var veraWebPropose: Bool = UserDefaults.standard
        .bool(forKey: "vera_web_propose") {
        didSet { UserDefaults.standard.set(veraWebPropose, forKey: "vera_web_propose") }
    }
    /// 「検索して」の対象 — 直近で拒否された質問(非永続)。
    var veraLastRefusedQuery: String?
    @Published var toolTerminalEnabled: Bool = true {
        didSet { UserDefaults.standard.set(toolTerminalEnabled, forKey: "tool_terminal") }
    }
    @Published var toolDiffEnabled: Bool = true {
        didSet { UserDefaults.standard.set(toolDiffEnabled, forKey: "tool_diff") }
    }
    @Published var toolJCrossEnabled: Bool = true {
        didSet { UserDefaults.standard.set(toolJCrossEnabled, forKey: "tool_jcross") }
    }

    // ── Privacy Gateway: Gemma semantic masking ──
    /// Gemmaによるセマンティックマスキング (Phase 2) の有効/無効
    /// OFF時は Phase 1 正規表現マスキングのみ使用（高速、Gemma不要）
    @Published var gemmaSemanticMaskingEnabled: Bool = true {
        didSet { UserDefaults.standard.set(gemmaSemanticMaskingEnabled, forKey: "gemma_semantic_masking") }
    }

    // ── UI Language ──
    enum UILanguage: String, CaseIterable, Codable {
        case system  = "System"
        case english = "English"
        case japanese = "日本語"

        var localeIdentifier: String {
            switch self {
            case .system:   return Locale.current.identifier
            case .english:  return "en"
            case .japanese: return "ja"
            }
        }

        var flag: String {
            switch self {
            case .system:   return "🌐"
            case .english:  return "🇺🇸"
            case .japanese: return "🇯🇵"
            }
        }
    }

    @Published var appLanguage: UILanguage = {
        let raw = UserDefaults.standard.string(forKey: "app_language") ?? UILanguage.system.rawValue
        return UILanguage(rawValue: raw) ?? .system
    }() {
        didSet {
            UserDefaults.standard.set(appLanguage.rawValue, forKey: "app_language")
            // Keep global AppLanguage singleton in sync for NSTextView/NSMenuItem code
            let isJA: Bool
            switch appLanguage {
            case .japanese: isJA = true
            case .english:  isJA = false
            case .system:   isJA = Locale.current.language.languageCode?.identifier == "ja"
            }
            AppLanguage.shared.isJapanese = isJA
        }
    }

    // MARK: - Localized string helper
    func t(_ en: String, _ ja: String) -> String {
        switch appLanguage {
        case .japanese: return ja
        case .english:  return en
        case .system:
            return Locale.current.language.languageCode?.identifier == "ja" ? ja : en
        }
    }

    // MARK: - UI Preferences

    @Published var codeFontSize: Int = {
        let v = UserDefaults.standard.integer(forKey: "code_font_size")
        return v > 0 ? v : 12
    }() {
        didSet { UserDefaults.standard.set(codeFontSize, forKey: "code_font_size") }
    }

    @Published var notifyOnDiffApply: Bool = UserDefaults.standard.bool(forKey: "notify_diff_apply") {
        didSet { UserDefaults.standard.set(notifyOnDiffApply, forKey: "notify_diff_apply") }
    }

    @Published var notifyOnError: Bool = {
        let v = UserDefaults.standard.object(forKey: "notify_error") as? Bool
        return v ?? true
    }() {
        didSet { UserDefaults.standard.set(notifyOnError, forKey: "notify_error") }
    }

    // Manual override for the automatic per-turn Visual/Cognitive Anchor
    // images (searchForce/doubt/logic/etc, rendered by CognitiveAnchorEngine
    // and attached every turn to multimodal-classified models). Kept
    // separate from `isMultimodalModel` so turning this off doesn't change
    // multimodal *detection* -- it only stops those anchor images from being
    // attached, e.g. to A/B-test whether they're responsible for a given
    // model's degraded/garbled output without touching image attachments
    // (photo.badge.plus) or the model classification itself.
    @Published var autoVisualAnchorImagesEnabled: Bool = {
        let v = UserDefaults.standard.object(forKey: "auto_visual_anchor_images_enabled") as? Bool
        return v ?? true
    }() {
        didSet { UserDefaults.standard.set(autoVisualAnchorImagesEnabled, forKey: "auto_visual_anchor_images_enabled") }
    }

    // ── Multimodal capability detection ──
    var isMultimodalModel: Bool {
        switch modelStatus {
        case .ollamaReady(let m):
            let mm = m.lowercased()
            return mm.contains("llava") || mm.contains("vision")
                || (mm.contains("qwen") && mm.contains("vl"))
                || mm.contains("qwen3") || mm.contains("qwen-vl")
                || mm.contains("minicpm") || mm.contains("moondream")
                || mm.contains("bakllava") || mm.contains("cogvlm")
                || mm.contains("ornith")
                || (mm.contains("gemma") && !mm.contains("gemma2") && !mm.contains("gemma-2"))
        case .mlxReady(let m):
            let mm = m.lowercased()
            return mm.contains("vision") || mm.contains("gemma-4")
                || mm.contains("qwen-vl") || mm.contains("llava") || mm.contains("llm3.2")
                || mm.contains("ornith")

        // Cloud models were never considered here at all, so every one of them
        // fell to `default: false` and was declared text-only — Claude, GPT-4o,
        // Gemini included. A run on a cloud model printed 「テキスト専用モデル」
        // on every turn and threw the screenshot away before sending, which
        // means the vision path was off precisely when it was most capable.
        case .anthropicReady(let m, _):
            return Self.cloudModelSeesImages(m)
        case .claudeAgentReady(let m):
            return Self.cloudModelSeesImages(m)

        default: return false
        }
    }

    /// Whether a cloud model accepts images. Stated per family rather than
    /// assumed true: DeepSeek's chat models are text-only, and sending an
    /// image to one is an HTTP 400, which surfaces as a nil response — the
    /// same silent failure this guard exists to prevent.
    static func cloudModelSeesImages(_ model: String) -> Bool {
        let m = model.lowercased()
        // Text-only, stated first because some share a prefix with vision ones.
        if m.contains("deepseek-chat") || m.contains("deepseek-reasoner")
            || m.contains("deepseek-v3") || m.contains("deepseek-v4") { return false }
        if m.contains("o1-mini") || m.contains("text-") { return false }

        return m.contains("claude")     // every current Claude accepts images
            || m.contains("gpt-4o") || m.contains("gpt-4.1") || m.contains("gpt-5")
            || m.contains("o3") || m.contains("o4")
            || m.contains("gemini")
            || m.contains("grok")       // grok-2-vision and later
            || m.contains("-vl") || m.contains("vision")
            || m.contains("pixtral") || m.contains("llama-4")
    }

    enum ModelStatus: Equatable {
        case none
        case connecting
        case downloading(progress: Double)
        case ready(name: String)
        case ollamaReady(model: String)
        case anthropicReady(model: String, maskedKey: String)  // Anthropic API
        /// Claude reached through the Agent SDK (the `claude` CLI), on the
        /// user's own Claude Code login. Distinct from `.anthropicReady`
        /// because no API key is involved and none is held here.
        case claudeAgentReady(model: String)
        case mlxReady(model: String)          // MLX server running at localhost:8080
        case mlxDownloading(model: String)    // mlx_lm download in progress
        case bitnetReady(model: String)       // BitNet local subprocess
        case jcrossReady(model: String)       // JGEN/RustBrain in-process engine (JCrossEngine)
        case lmStudioReady(model: String)     // LM Studio's OpenAI-compatible local server
        case error(String)
    }

    // Workspace manager (lazy)
    private let workspace = WorkspaceManager()
    let agent = AgentEngine()
    let terminal = TerminalRunner()
    let cortex = CortexEngine()
    let sessions = SessionStore()

    // MARK: - Dirty state (close/quit guard)

    /// True when there is active work that should be saved before quitting.
    var isDirty: Bool {
        (workspaceURL != nil && (pendingDiff != nil || messages.count > 2))
        || isGenerating
    }

    // MARK: - Self-Admin API
    // AI agent calls this to modify IDE settings directly from chat instructions.
    // AllowList design: only known keys are accepted; unknown keys warn but don't crash.
    @discardableResult
    func applySetting(key: String, value: String) -> String {
        switch key {
        case "system_prompt":
            systemPrompt = value
        case "operation_mode":
            // Previously this ignored `value` and always forced .gatekeeper,
            // so the setting was unsettable. Honor the requested mode and
            // report invalid input instead of silently picking one.
            guard let mode = OperationMode(rawValue: value) else {
                let valid = OperationMode.allCases.map(\.rawValue).joined(separator: ", ")
                return "⚠️ Invalid operation_mode: '\(value)' (expected: \(valid))"
            }
            operationMode = mode
        case "temperature":
            if let d = Double(value) { temperature = max(0.0, min(2.0, d)) }
            else { return "⚠️ Invalid temperature: \(value) (expected 0.0–2.0)" }
        case "max_tokens_ollama":
            if let i = Int(value) { maxTokensOllama = max(64, min(32768, i)) }
            else { return "⚠️ Invalid max_tokens_ollama: \(value)" }
        case "max_tokens_mlx":
            if let i = Int(value) { maxTokensMLX = max(64, min(32768, i)) }
            else { return "⚠️ Invalid max_tokens_mlx: \(value)" }
        case "ollama_endpoint":
            ollamaEndpoint = value
        case "inference_mode":
            if let m = InferenceMode(rawValue: value) { inferenceMode = m }
            else { return "⚠️ Unknown inference_mode: \(value). Valid: localOnly, cloudDirect, privacyShield, paranoiaMode" }
        case "agent_loop_enabled":
            agentLoopEnabled = (value == "true" || value == "1" || value == "yes")
        case "streaming_enabled":
            streamingEnabled = (value == "true" || value == "1" || value == "yes")
        case "anthropic_api_key":
            anthropicApiKey = value
        case "active_ollama_model":
            activeOllamaModel = value
            modelStatus = .ollamaReady(model: value)
        case "active_auditor_model":
            activeAuditorModel = value
        case "is_auditor_enabled":
            isAuditorEnabled = (value == "true" || value == "1" || value == "yes")
        case "context_window_override":
            guard let n = Int(value) else { return "⚠️ context_window_override expects an integer (0 = auto)" }
            contextWindowOverride = n
        case "active_mlx_model":
            activeMlxModel = value
        case "council_execution_model":
            CouncilSettingsStore.shared.executionModel = value
        case "council_escalation_model":
            CouncilSettingsStore.shared.config.escalationModel = value
        case "council_use_for_chat":
            CouncilSettingsStore.shared.useCouncilForChat = (value == "true" || value == "1" || value == "yes")
        case "vector_only_sense", "council_vector_only_sense":
            CouncilSettingsStore.shared.vectorOnlySense = (value == "true" || value == "1" || value == "yes")
        default:
            return "⚠️ Unknown setting key: '\(key)'. Valid keys: system_prompt, operation_mode, temperature, max_tokens_ollama, max_tokens_mlx, ollama_endpoint, inference_mode, agent_loop_enabled, streaming_enabled, anthropic_api_key, active_ollama_model, active_auditor_model, is_auditor_enabled, context_window_override, active_mlx_model, council_execution_model, council_escalation_model, council_use_for_chat, vector_only_sense"
        }
        return "✓ \(key) = \(value.prefix(80))"
    }

    // MLX state
    @Published var activeMlxModel: String = {
        UserDefaults.standard.string(forKey: "active_mlx_model")
            ?? "mlx-community/gemma-4-26b-a4b-it-4bit"
    }() {
        didSet { UserDefaults.standard.set(activeMlxModel, forKey: "active_mlx_model") }
    }
    @Published var mlxServerLogs: [String] = []

    // Agent loop
    @Published var agentLoopEnabled: Bool = true {
        didSet { UserDefaults.standard.set(agentLoopEnabled, forKey: "agent_loop_enabled") }
    }

    // ── Navigation requested from outside the settings screens ───────────
    //
    // The support bot answers with "Settings › Model › Ollama model", which
    // is only useful to someone who can already find it. Setting this opens
    // Settings on that tab, so an answer can end at the screen rather than at
    // a description of where the screen is.
    //
    // Deliberately a String rather than SettingsTab: the value comes from
    // Vera's registry over MCP, and matching it to the enum is the settings
    // screen's job. A tab name that no longer exists then falls back to the
    // default tab instead of failing to compile against a moving enum.
    @Published var requestedSettingsTab: String? = nil

    /// Ask the UI to open Settings at `tab` (a SettingsTab raw value).
    func openSettings(tab: String) {
        requestedSettingsTab = tab
        showSettingsRequested = true
    }

    /// Raised by `openSettings`; the mode layouts observe it and present the
    /// settings sheet. Cleared by the layout once it has acted.
    @Published var showSettingsRequested: Bool = false
    /// Which tab of the Vera dock a summon named, when it named one.
    @Published var requestedDockTab: String? = nil

    // ── Atelier's own settings ────────────────────────────────────────────
    //
    // 服飾モード専用。LLM モードの `showSettingsRequested` / SettingsView
    // とは別物 — 服飾の設定を変えても LLM 側には出ず、その逆も無い。
    // 言語 (`appLanguage`, 上) だけは例外で、両モードとチューザー画面が
    // 同じ値を読む。

    /// Raised by the rail's settings button in Atelier mode; observed by
    /// the same layout that observes `showSettingsRequested`, presenting
    /// `AtelierSettingsView` instead of `SettingsView`.
    @Published var showAtelierSettingsRequested: Bool = false

    /// 採寸の既定単位。garment_measure.Measures.measured() は単位の無い
    /// 数字を UNKNOWN_NO_UNIT で断る (単位は cm/mm/inch の三つだけ) —
    /// ここは MeasurePanel の単位ピッカーの初期値に使う。都度選び直せる
    /// ことに変わりは無く、ここは「次にどれで始まるか」だけを決める。
    @Published var atelierDefaultUnit: String = {
        let v = UserDefaults.standard.string(forKey: "atelier_default_unit") ?? "cm"
        return ["cm", "mm", "inch"].contains(v) ? v : "cm"
    }() {
        didSet { UserDefaults.standard.set(atelierDefaultUnit, forKey: "atelier_default_unit") }
    }

    /// 台帳に残る名前の既定値。Ledger.adopt は空の名前を UNKNOWN_NO_ADOPTER
    /// で断り、実測・再設計の「誰が」欄も同じ理由で人の名前を要る —
    /// 一人で使っていても採用のたびに打ち直す手間を、ここで一度に減らす。
    /// 空のままでも良い: その場合は各画面が今まで通り毎回尋ねる。
    @Published var atelierOperatorName: String =
        UserDefaults.standard.string(forKey: "atelier_operator_name") ?? "" {
        didSet { UserDefaults.standard.set(atelierOperatorName, forKey: "atelier_operator_name") }
    }

    // ── Vera engine mode ─────────────────────────────────────────────────
    //
    // Atelier is the mode this app is for; LLM is the plain conversation
    // it kept from the general-purpose IDE it grew out of. That is the
    // whole set now.
    //
    // jgen 合議 (`council`), 単体 Vera-a (`standalone`), Vera単体
    // (`vera_model`) and Veraぼっと (`vera_bot`) were all removed outright
    // rather than hidden — the last two on 2026-08-26. veraModel answered
    // with typed verdicts and no LLM in the turn; veraBot answered
    // questions about the app itself from the settings registry, and was
    // also the only mode `VeraSummon.resolve` fired in, so summoning a
    // panel by typing its name (記憶, 十字, 設定…) left with it — see
    // VeraSummon.swift and VeraSummonedPanel.swift for what that leaves
    // orphaned. A mode that is unreachable from the menu but still
    // constructible from a persisted string is not removed, it is just
    // harder to find — and it would keep its branches alive in the turn
    // handler where nobody exercises them. `loadPersistedSettings` maps
    // any of the four stored values onto `.atelier` so an existing
    // install comes back somewhere real instead of failing to decode.
    enum VeraEngineMode: String, CaseIterable {
        // 服飾のワークベンチ。作業面がチャットではなく「服の状態」になる。
        // 背景のパイプ(モデル登録・ローカルLLM・MCP)はそのまま使い、
        // 情報整理だけが必ず Vera の台帳を通る。
        case atelier = "atelier"        // Vera Atelier (服飾)
        // Named `localLLM` for its stored value only — the mode is "just an
        // LLM", and since cloud providers became selectable in the model menu
        // that LLM can equally be Claude or Grok. The raw value stays as it is
        // because it is persisted.
        case localLLM = "local_llm"     // 通常のLLM (合議もVeraも通さない)
    }

    // ── Vera model versions: the same menu the 3D page's toggle reads ──
    // (versions/index.json on the ask-vera Space). "local" is the build
    // beside the engine checkout; a stamped id downloads its db/edges/
    // writer into Application Support and pins the MCP process to it via
    // VERA_PUBLISHED_DB, then restarts the session — switching models is
    // switching which stamped release answers, never a silent reload.
    struct VeraModelVersion: Identifiable, Codable, Equatable {
        var id: String
        var db: String
        var edges: String?
        var writer: String?
        var notes: String?
        var cores: Int?
    }
    @Published var veraModelVersions: [VeraModelVersion] = []
    @Published var selectedVeraVersionId: String = "local"
    @Published var veraVersionBusy: Bool = false
    /// The last ANSWERED core in Vera model mode — the visible,
    /// deterministic conversation context. Cleared with the chat.
    var veraTrailCore: String? = nil

    static let veraSpaceAssets = "https://kofdai-ask-vera.static.hf.space"

    func refreshVeraModelVersions() async {
        guard let url = URL(string: Self.veraSpaceAssets + "/versions/index.json"),
              let (data, _) = try? await URLSession.shared.data(from: url),
              let list = try? JSONDecoder().decode([VeraModelVersion].self, from: data)
        else { return }
        await MainActor.run { self.veraModelVersions = list.reversed() }
    }

    func selectVeraModelVersion(_ id: String) async {
        await MainActor.run { self.veraVersionBusy = true }
        defer { Task { @MainActor in self.veraVersionBusy = false } }
        var envDB = ""
        if id != "local",
           let v = veraModelVersions.first(where: { $0.id == id }) {
            let fm = FileManager.default
            let dir = fm.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
                .appendingPathComponent("Verantyx/vera-models/\(id)", isDirectory: true)
            try? fm.createDirectory(at: dir, withIntermediateDirectories: true)
            let files: [(String?, String)] = [
                (v.db, "vera.db"), (v.edges, "vera_edges.db"),
                (v.writer, "writer.json")]
            for (remote, name) in files {
                guard let remote, !remote.isEmpty else { continue }
                let dst = dir.appendingPathComponent(name)
                if fm.fileExists(atPath: dst.path) { continue }
                guard let u = URL(string: Self.veraSpaceAssets + "/" + remote),
                      let (tmp, _) = try? await URLSession.shared.download(from: u)
                else { continue }
                // The Space stores gzip; expand with the system tool so a
                // partial download never silently becomes a store.
                let gz = dir.appendingPathComponent(name + ".gz")
                try? fm.removeItem(at: gz)
                try? fm.moveItem(at: tmp, to: gz)
                let p = Process()
                p.executableURL = URL(fileURLWithPath: "/usr/bin/gunzip")
                p.arguments = ["-f", gz.path]
                try? p.run(); p.waitUntilExit()
            }
            let db = dir.appendingPathComponent("vera.db")
            guard fm.fileExists(atPath: db.path) else { return }
            envDB = db.path
        }
        await MainActor.run { self.selectedVeraVersionId = id }
        // Pin the NATIVE engine and restart it — the model switch IS the
        // process restart, so no call can answer from a mixed build.
        await VeraModelProcess.shared.switchModel(
            dbPath: envDB.isEmpty ? nil : envDB)
        await MainActor.run { self.veraTrailCore = nil }
    }
    /// Which AuditMemory store Vera-a reads and writes. "Fresh memory" at
    /// session start swaps this to a dated task name; old stores stay on
    /// disk untouched, so switching back is choosing the old name again.
    // ── The stage: one surface, many faces ──────────────────────────────
    //
    // Editor, terminal, diff, artifact and memory used to be separate panes
    // and splits; they are now ONE area whose content the agent (or the
    // user) switches. The chat is the other pane — two screens total.
    enum StageMode: Equatable {
        case editor, terminal, diff, artifact, memory, files
        case aiPanel(String)   // id of an agent-defined panel
    }
    @Published var stageMode: StageMode = .editor
    @Published var stageDiff: String = ""
    @Published var stageArtifactTitle: String = ""
    @Published var stageArtifactText: String = ""

    /// Panels the AI names and fills itself — both the left column and the
    /// stage can show them. "The agent defines what this space is" is an
    /// API, not a fixed layout decision.
    struct AIPanel: Identifiable, Equatable {
        let id: String
        var title: String
        var text: String
    }
    @Published var aiPanels: [AIPanel] = []

    /// Agent API: create or update a named panel (and optionally front it).
    func aiShowPanel(title: String, text: String, front: Bool = true) {
        if let i = aiPanels.firstIndex(where: { $0.title == title }) {
            aiPanels[i].text = text
        } else {
            aiPanels.append(AIPanel(id: UUID().uuidString, title: title, text: text))
        }
        if front, let panel = aiPanels.first(where: { $0.title == title }) {
            stageMode = .aiPanel(panel.id)
            shell.openTab(.aiPanel(id: panel.id))
        }
    }
    func aiShowDiff(_ diff: String) {
        stageDiff = diff; stageMode = .diff
        shell.openTab(.diff)
    }
    func aiShowArtifact(title: String, text: String) {
        stageArtifactTitle = title; stageArtifactText = text; stageMode = .artifact
        shell.openTab(.artifact)
    }
    func aiShowTerminal() {
        stageMode = .terminal
        shell.openTab(.terminal)
    }
    func aiShowMemory() {
        stageMode = .memory
        shell.openTab(.memory)
    }

    /// AI-writable surface in the left multi-purpose panel.
    @Published var flexPanelTitle: String = ""
    @Published var flexPanelText: String = ""

    @Published var veraMemoryTask: String =
        UserDefaults.standard.string(forKey: "vera_memory_task") ?? "verantyx-ai-vera3d" {
        didSet { UserDefaults.standard.set(veraMemoryTask, forKey: "vera_memory_task") }
    }

    // ── Model roles ─────────────────────────────────────────────────────
    // The dual setup, made explicit: three separately chosen models.
    //   会話用  — modelStatus (the existing model menu)
    //   記憶用  — which JGEN the memory organ loads (engine only; never
    //             touches modelStatus). Autoload prefers this over the pin.
    //   Vera-a用 — who composes under the verdict in Vera-a mode:
    //             "auto" follows the chat model; "lmstudio:<id>" /
    //             "ollama:<id>" override it.
    @Published var memoryOrganModel: String =
        UserDefaults.standard.string(forKey: "memory_organ_model") ?? "" {
        didSet { UserDefaults.standard.set(memoryOrganModel, forKey: "memory_organ_model") }
    }

    /// Vera-a drives the machine the user is actually looking at.
    ///

    /// The surface the person summoned by name. Nil is the resting
    /// state: chrome is gone, so nothing is on screen that was not
    /// asked for.

    /// LLM バックエンドをこのモードが使うか。
    ///
    /// 2026-08-26 に veraModel / veraBot(turn の中で LLM を一切呼ばない
    /// 2モード: 単体 Vera-a と 設定案内)を削除。残る atelier / localLLM は
    /// どちらも LLM を呼ぶので、この関数は常に true — が、削除の記録として
    /// 残す(呼び出し側 `MainSplitView.onAppear` を変えずに済む)。
    var usesLLMBackend: Bool { true }

    @Published var veraEngineMode: VeraEngineMode = .atelier {
        didSet {
            UserDefaults.standard.set(veraEngineMode.rawValue,
                                      forKey: "vera_engine_mode")
            // shell.openTab の唯一の門がこの値を読む — レール以外の道
            // (エージェントの提案、summon)からモード外のタブが開くのを
            // ここで一緒に塞ぐ。
            shell.currentMode = veraEngineMode
        }
    }

    // ── モードの選択画面 ──────────────────────────────────────────
    //
    // 「選んだ」は起動時の既定値と区別する。既定は常に .atelier だが、
    // それはこのプロパティの初期値であって人の選択ではない —
    // `hasChosenEngineMode` が false のあいだは、その既定値はまだ
    // 「選ばれていない」。選択画面はこれを見て、初回起動(または
    // まだ一度も選んでいない状態)でだけ最初の画面になる。
    @Published var hasChosenEngineMode: Bool =
        UserDefaults.standard.bool(forKey: "vera_engine_mode_chosen")
    /// 選択画面へ戻る、明示的な要求。選んだ後でも消えない — 「後から
    /// 戻れる道」がこの旗そのもの。
    @Published var showModeChooser: Bool = false

    /// モードを選ぶ、唯一の書き口。選択画面からも、チャット内の切替
    /// ピッカーからも、名前で呼ばれた一覧からも、ここを通す — でないと
    /// 「選んだ」が場所ごとに別の意味になる。モードを跨いで存在できない
    /// タブ(服飾タブが LLM 側に残る、等)もここで畳む。
    func selectEngineMode(_ mode: VeraEngineMode) {
        veraEngineMode = mode
        hasChosenEngineMode = true
        UserDefaults.standard.set(true, forKey: "vera_engine_mode_chosen")
        showModeChooser = false
        shell.pruneTabs(incompatibleWith: mode)
        // 選択直後の着地点もモードの契約に含める。初回Atelierで汎用
        // composerへ落ちたり、LLMで服飾タブだけが残ったりさせない。
        switch mode {
        case .atelier:
            selectedFile = nil
            selectedFileContent = ""
            shell.openTab(.garment)
        case .localLLM:
            shell.openTab(.chat)
        }
    }

    // ── VX-Loop: Chat session-level persistent ID for VXTimeline ─────────
    // nano/small モデル使用時、全ターンで同一IDを共有することで
    // VXTimeline内の履歴記録を次のターンで参照できる。
    // newChatSession() でリセットされる。
    var vxChatSessionId: String = String(UUID().uuidString.prefix(8))

    // nano/small モデル選択時に AI Priority を強制するフラグ
    @Published var isNanoSmallModelActive: Bool = false
    
    // Tracking spotlight generation
    var currentGenerationIsSpotlight: Bool = false

    // Talkie-1930 Mode (Blind Commander)
    @Published var isTalkieMode: Bool = false {
        didSet {
            if isTalkieMode {
                let talkieMLX = "kofdai/talkie-1930-13b-it-mlx-8bit"
                if activeMlxModel != talkieMLX {
                    activeMlxModel = talkieMLX
                    loadMLXModel(model: talkieMLX)
                } else if case .mlxReady = modelStatus {
                    // Already ready
                } else {
                    loadMLXModel(model: talkieMLX)
                }
            }
        }
    }

    // MARK: - Gatekeeper Model Sync

    func getOllamaModel() -> String {
        return GatekeeperPipelineState.shared.config.intentOllamaModel
    }

    func setOllamaModel(_ model: String) {
        var config = GatekeeperPipelineState.shared.config
        config.intentOllamaModel = model
        GatekeeperPipelineState.shared.config = config
        config.save()
        
        if activeOllamaModel != model {
            activeOllamaModel = model
        }
    }

    // Active Gatekeeper Local Model
    @Published var activeOllamaModel: String = {
        GatekeeperPipelineState.shared.config.intentOllamaModel.isEmpty ? "gemma4:26b" : GatekeeperPipelineState.shared.config.intentOllamaModel
    }() {
        didSet {
            var config = GatekeeperPipelineState.shared.config
            config.intentOllamaModel = activeOllamaModel
            GatekeeperPipelineState.shared.config = config
            config.save()
        }
    }

    // MARK: - Workspace actions

    /// The model that will actually generate this turn — named by the ACTIVE
    /// backend, not by whatever Ollama model happens to be configured. The
    /// profile banner used to read `activeOllamaModel` unconditionally, so a
    /// selected LM Studio model (muse-glimmer) generated the reply while the
    /// banner — and the tier/token/temperature budgets derived from it —
    /// described gemma4:26b.
    /// The model actually answering, for profile detection.
    ///
    /// Cloud and Agent SDK had no case here and fell through to
    /// `activeOllamaModel` — a leftover local name. So selecting
    /// claude-sonnet-5 profiled as "qwen3.5:4b → Small", and the Small tier
    /// prompt lists ten tools with no USE_APP, OPEN_APP, DESKTOP_ACT, MENU or
    /// KEYS in it. Asked to open Teams, the model correctly answered that it
    /// could not operate desktop applications: nothing had told it otherwise.
    /// It also capped a frontier model at 4096 tokens.
    var effectiveModelName: String {
        switch modelStatus {
        case .lmStudioReady(let m), .mlxReady(let m),
             .bitnetReady(let m), .jcrossReady(let m),
             .ollamaReady(let m), .ready(let m):
            return m
        case .anthropicReady(let m, _), .claudeAgentReady(let m):
            return m
        case .mlxDownloading(let m):
            return m
        case .none, .connecting, .downloading, .error:
            return activeOllamaModel
        }
    }

    func openWorkspace() {
        guard veraEngineMode == .localLLM else {
            ToastManager.shared.show(
                t("Code folders are available in LLM mode",
                  "コードフォルダはLLMモードで利用できます"),
                icon: "folder.badge.questionmark", color: Theme.warn)
            return
        }
        guard let url = workspace.pickFolder() else { return }
        workspaceURL = url
        workspaceFiles = []
        selectedFile = nil
        selectedFileContent = ""
        terminal.workingDirectory = url
        shell.openTab(.folder(path: url.path))
        // 再起動後も最後のワークスペースを復元できるよう保存
        UserDefaults.standard.set(url.path, forKey: "last_workspace_path")
        addSystemMessage("📂 Workspace: \(url.lastPathComponent)")
        SelfEvolutionEngine.shared.setWorkspaceHint(url)
        GatekeeperModeState.shared.configure(workspaceURL: url)
        refreshFiles()
        // ── ワークスペース追加時に L2.5 地図を自動生成 ───────────────────
        // (UI側で確認ダイアログを出すため、自動実行は削除)
        }

    /// Progressive directory scan — yields partial results as they arrive.
    /// First batch appears in ~200ms for most workspaces. Tree shows before scan completes.
    func refreshFiles() {
        guard veraEngineMode == .localLLM else { return }
        guard let root = workspaceURL else { return }

        // Broader extension set so all relevant source/config files appear
        let exts: Set<String> = [
            // Apple
            "swift", "m", "mm", "xib", "storyboard", "plist",
            // Python
            "py", "pyw", "pyi", "ipynb",
            // JS / TS / Web
            "ts", "tsx", "js", "jsx", "mjs", "cjs", "vue", "svelte",
            "html", "htm", "css", "scss", "sass", "less",
            // Rust
            "rs", "toml",
            // Go
            "go",
            // JVM
            "kt", "kts", "java", "scala", "gradle",
            // C family
            "c", "cpp", "cc", "cxx", "h", "hpp",
            // Ruby / PHP
            "rb", "rake", "gemspec", "php",
            // Shell
            "sh", "bash", "zsh", "fish", "ps1",
            // Docs / Config
            "md", "mdx", "markdown", "txt", "rst",
            "json", "jsonc", "yaml", "yml",
            "xml", "csv", "sql", "graphql",
            "env", "lock",
            // Bare filenames (extension-less) — handled by name match in _scanDirectory
            "makefile", "dockerfile", "gitignore", "gitattributes",
            "procfile", "rakefile",
        ]

        // Use non-detached Task so MainActor isolation is inherited and `workspace`
        // (a @MainActor property) can be accessed safely. The async for-await iterator
        // yields control between snapshots so UI rendering is not blocked.
        Task(priority: .userInitiated) { [weak self] in
            guard let self else { return }
            for await snapshot in self.workspace.scanStreaming(in: root, extensions: exts) {
                self.workspaceFiles = snapshot
            }
        }
    }


    /// Helper to safely read and truncate file content for UI preview
    nonisolated private func safePreview(for url: URL) -> String {
        do {
            let attr = try FileManager.default.attributesOfItem(atPath: url.path)
            if let size = attr[.size] as? UInt64, size > 2_000_000 { // >2MB is too big for SwiftUI Text
                return ";;; ⚠️ File is too large to preview (\(size / 1_000_000) MB)"
            }
            let text = try String(contentsOf: url, encoding: .utf8)
            return truncatePreview(text: text)
        } catch {
            if let text = try? String(contentsOf: url, encoding: .isoLatin1) {
                return truncatePreview(text: text)
            }
            return ";;; ⚠️ Unable to read file content (binary or unknown encoding)"
        }
    }

    nonisolated private func truncatePreview(text: String) -> String {
        let maxChars = 100_000 // Safe limit for SwiftUI Text
        if text.count > maxChars {
            return String(text.prefix(maxChars)) + "\n\n... (File truncated for preview limit) ..."
        }
        return text
    }

    @Published var showGatekeeperRawCode: Bool = {
        let raw = UserDefaults.standard.string(forKey: "operation_mode") ?? OperationMode.automatic.rawValue
        let mode = OperationMode(rawValue: raw) ?? .automatic
        return mode != .gatekeeper
    }() {
        didSet {
            if let file = selectedFile { selectFile(file) }
        }
    }

    /// Instant selection — show name immediately, read content async.
    func selectFile(_ url: URL) {
        selectedFile = url          // highlight instantly (no wait)
        selectedFileContent = ""    // clear old content immediately
        shell.openTab(.file(path: url.path))

        // ── Gatekeeper Mode: Vault の JCross IR を表示 ────────────────
        // 有効な場合は実コードの代わりに JCross 変換済みコンテンツを表示する。
        // Vault 未登録ファイルは実コード + 警告バナーで表示。
        let gatekeeperEnabled = GatekeeperModeState.shared.isEnabled
        if gatekeeperEnabled && !showGatekeeperRawCode {
            let relativePath: String
            if let wsPath = workspaceURL?.path,
               url.path.hasPrefix(wsPath + "/") {
                relativePath = String(url.path.dropFirst(wsPath.count + 1))
            } else {
                relativePath = url.lastPathComponent
            }

            Task.detached { [weak self] in
                guard let self else { return }
                let vault = await MainActor.run { GatekeeperModeState.shared.vault }
                let result = await MainActor.run { vault.read(relativePath: relativePath) }

                await MainActor.run {
                    guard self.selectedFile == url else { return }
                    if let vaultResult = result {
                        // JCross IR を表示（先頭にバナーを付ける）
                        let banner = """
                        ;;; 🛡️ GATEKEEPER MODE — JCross IR View
                        ;;; Real identifiers have been replaced with node IDs.
                        ;;; Schema: \(vaultResult.entry.schemaSessionID.prefix(12))
                        ;;; Nodes: \(vaultResult.entry.nodeCount) | Secrets redacted: \(vaultResult.entry.secretCount)
                        ;;; Source: \(relativePath)
                        ;;; 
                        ;;; (To view raw code, toggle "Show Raw Code" above)
                        ;;;
                        """
                        self.selectedFileContent = banner + "\n" + self.truncatePreview(text: vaultResult.jcrossContent)
                    } else {
                        // Vault 未変換: 実コードを読み込み + 警告バナー
                        let raw = self.safePreview(for: url)
                        let warning = """
                        ;;; ⚠️ GATEKEEPER MODE — このファイルはまだ JCross 変換されていません
                        ;;; [Gatekeeper 設定] → [一括変換を開始] でVaultを更新してください
                        ;;; ※ 以下は実コードです。このビューは一時的なものです
                        ;;;
                        
                        """
                        self.selectedFileContent = warning + raw
                    }
                }
            }
            return
        }

        // ── 通常モード: 実ファイルを読み込む ─────────────────────────
        Task.detached { [weak self] in
            guard let self else { return }
            // Read on background thread — never blocks UI
            let content = self.safePreview(for: url)
            await MainActor.run {
                // Only update if this file is still selected
                guard self.selectedFile == url else { return }
                self.selectedFileContent = content
            }
        }
    }

    // MARK: - Session management

    /// Save the current chat to the session store.
    func saveCurrentSession() {
        if sessions.activeSessionId == nil, messages.count > 1 {
            _ = sessions.newSession(messages: messages, workspacePath: workspaceURL?.path)
        } else {
            sessions.updateActiveSession(messages: messages, workspacePath: workspaceURL?.path)
        }
    }

    /// Start a fresh chat  (old session saved automatically).
    func newChatSession() {
        // 新規セッション開始時は常にフォルダ選択ダイアログを開く処理を削除（FileTreeViewのボタンに一本化）

        // Before clearing, archive the current session progressively
        if let currentId = sessions.activeSessionId,
           let current = sessions.sessions.first(where: { $0.id == currentId }),
           !current.messages.filter({ $0.role != .system }).isEmpty {
            SessionMemoryArchiver.shared.archiveProgressively(session: current)
        }

        saveCurrentSession()
        messages.removeAll()
        pendingDiff = nil
        showDiff    = false
        autoApproveDiffs = false
        // 新セッション開始時に VXTimeline ID をリセット
        vxChatSessionId = String(UUID().uuidString.prefix(8))
        let newSession = sessions.newSession(messages: [], workspacePath: workspaceURL?.path)

        // ── Cross-session memory injection ───────────────────────────
        // Inject past sessions' JCross memory at the correct layer depth.
        let currentId = newSession.id
        let layer = sessions.activeSession?.activeLayer ?? .l2
        Task {
            let useNanoStore = self.isNanoSmallModelActive
            let injection = SessionMemoryArchiver.shared.buildZonePriorityInjection(
                layer: layer,
                useNanoStore: useNanoStore
            )
            if !injection.isEmpty {
                await MainActor.run {
                    self.messages.insert(
                        ChatMessage(role: .system, content: injection),
                        at: 0
                    )
                    self.addSystemMessage(self.t("🧠 Injected memory from past session (\(layer.rawValue) layer)", "🧠 過去セッションの記憶を注入しました (\(layer.rawValue) レイヤー)"))
                }
            }
        }
    }

    /// 起動時に、最後に使っていた会話の本文を戻す。
    ///
    /// **これが無いのが「アプリを開き直すと会話履歴が消える」の本体だった。**
    /// `SessionStore.init` はディスクから会話を復号して `sessions` と
    /// `activeSessionId` を戻していたが、**`messages` は空のまま**だった。
    /// 画面は `messages` を見るので履歴は消えたように見え、さらに悪いことに
    /// `activeSessionId` だけが最後の会話に向いているので、次の発言が
    /// その会話の続きとして保存され、1発言だけの本文で JSON が上書き
    /// された — 見えないだけでなく、**実際に消えていた**。
    ///
    /// 復号は `Task.detached` なので、`didLoad` が立つまで待つ。待たずに
    /// 読むと「まだ空」を「会話が無い」と取り違える。
    /// 起動時の復元は一度きり。**`messages.isEmpty` だけでは足りない。**
    ///
    /// `Window` の `.onAppear` は再表示で二度目が走ることがあり、復元した
    /// セッションがまだ空（新規で作って何も書いていない服）だと、二度目の
    /// `messages.isEmpty` も真のままなので復元がもう一度走る。実機では
    /// 「セッションを復元しました」が2〜3行並んだ。旗は本文の中身に依らない。
    /// 走行中と完了は別の旗にする。**片方だけだと、待ちが空振りしたときに
    /// 二度と復元できなくなる。** 走行中の旗は同時起動を止めるためだけの
    /// もので、復元しないまま抜けたら降ろす。
    private var restoreOnLaunchInFlight = false
    private var didRestoreSessionOnLaunch = false

    func restoreLastSessionOnLaunch() {
        guard !didRestoreSessionOnLaunch, !restoreOnLaunchInFlight,
              messages.isEmpty else { return }
        restoreOnLaunchInFlight = true
        Task { @MainActor in
            defer { restoreOnLaunchInFlight = false }
            // 上限つきの待ち。立たないまま抜けたときは**何もしない** —
            // 復元できないことより、空の本文で上書きする方が悪い。
            for _ in 0..<200 {
                if sessions.didLoad { break }
                try? await Task.sleep(nanoseconds: 50_000_000)   // 50ms × 200 = 10s
            }
            guard sessions.didLoad,
                  messages.isEmpty,
                  let id = sessions.activeSessionId else { return }
            didRestoreSessionOnLaunch = true
            restoreSession(id)
        }
    }

    /// Restore a past session by its ID (loads messages + memory injection).
    func restoreSession(_ sessionId: UUID) {
        guard let session = sessions.sessions.first(where: { $0.id == sessionId }) else { return }

        // ── Cancel any in-flight inference from the previous session ────
        // This ensures: (a) isGenerating is reset, (b) no stale onToken
        // callbacks write into the newly-restored messages array.
        inferenceTask?.cancel()
        inferenceTask = nil
        isGenerating  = false
        // ⚠️ MUST nil streamingMsgId BEFORE replacing messages.
        // If it remains non-nil, the next .streamToken will search for the
        // old UUID in the restored session's messages, fail to find it,
        // and create a NEW orphan bubble instead of tracking correctly.
        self.streamingMsgId = nil

        saveCurrentSession()
        sessions.selectSession(sessionId)

        // Restore messages — filter out any empty assistant bubbles that were
        // saved mid-stream before a previous fix (corrupt streaming artifacts).
        messages    = session.messages.filter { msg in
            !(msg.role == .assistant && msg.content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        }
        pendingDiff = nil
        showDiff    = false
        if let path = session.workspacePath {
            let url = URL(fileURLWithPath: path)
            if workspaceURL != url {
                workspaceURL = url
                terminal.workingDirectory = url
                refreshFiles()
            }
        }
        // Inject JCross memory for this session in background
        Task {
            let injection = await sessions.buildMemoryInjection(for: sessionId)
            if !injection.isEmpty {
                await MainActor.run {
                    self.messages.insert(ChatMessage(role: .system, content: injection), at: 0)
                }
            }
        }
        addSystemMessage(self.t("📂 Restored session '\(session.title)'", "📂 セッション「\(session.title)」を復元しました"))
        activeChatTab = 0
    }

    // MARK: - Agent actions

    /// 単体 Vera-a の応答整形: 型付き判定を、型を隠さずに読みやすくする。
    static func formatVeraAnswer(_ raw: String) -> String {
        guard let data = raw.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let verdict = obj["verdict"] as? String else {
            return "⚠️ vera-memory から応答がありません。設定 › MCP を確認してください。\n\(raw.prefix(200))"
        }
        var lines: [String] = []
        if verdict == "ANSWER" {
            lines.append("🧭 **ANSWER**（決定論・出典遡及可能）")
            if let t = obj["text"] as? String, !t.isEmpty { lines.append(t) }
            if let core = obj["core"] as? String { lines.append("コア: \(core)") }
            if let toks = obj["tokens"] as? [String], !toks.isEmpty {
                lines.append("根拠ファセット: " + toks.prefix(8).joined(separator: ", "))
            }
        } else {
            lines.append("🚫 **\(verdict)**")
            if let reason = obj["reason"] as? String { lines.append(reason) }
            lines.append("Vera は知らないことを推測しません。文書を投入するか、LLM モードに切り替えてください。")
        }
        return lines.joined(separator: "\n")
    }

    /// Vera-side search planning: when a short info-seeking question
    /// ("Xとは", "Xについて", "what is X") finds no verified answer, VERA
    /// decides the target and the queries — deterministically, from the
    /// question's structure — and the web runs BEFORE the model ever
    /// thinks. The model reads evidence; it no longer has to remember to
    /// search, and it cannot leak a decision JSON into a query.
    nonisolated static func searchTarget(from text: String) -> String? {
        let t = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard t.count <= 60 else { return nil }
        let patterns: [(suffixes: [String], prefixes: [String])] = [(
            ["とは", "とは?", "とは？", "って何", "って何?", "って何？",
             "について教えて", "について", "を教えて"],
            ["what is ", "what's ", "who is ", "tell me about "]
        )]
        for p in patterns {
            for s in p.suffixes where t.hasSuffix(s) {
                let target = String(t.dropLast(s.count))
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                if !target.isEmpty, target.count <= 40 { return target }
            }
            let lower = t.lowercased()
            for pre in p.prefixes where lower.hasPrefix(pre) {
                let target = String(t.dropFirst(pre.count))
                    .trimmingCharacters(in: CharacterSet(charactersIn: " ?？"))
                if !target.isEmpty, target.count <= 40 { return target }
            }
        }
        return nil
    }

    /// Dynamic web-query planning, invoked by the APP on every Vera-a turn
    /// whose store verdict is UNKNOWN — the model fills in the queries but
    /// never decides whether to be asked (that judgment call is what kept
    /// getting forgotten). Output contract is JSON only; anything
    /// unparseable falls back to the bare pattern-extracted target, and a
    /// {"needs": false} verdict (greetings, file edits, tasks) skips the
    /// web entirely.
    /// Informational questions get searched when the store is UNKNOWN —
    /// REGARDLESS of what the planner model thinks of its own knowledge.
    /// A real run skipped the web on "OpenAI vs Anthropic の AGI 比較"
    /// because a 4B model judged itself sufficiently informed, then
    /// confidently answered with years-stale facts. Self-assessment of
    /// knowledge freshness is exactly the judgment small models get wrong,
    /// so Vera's rule outranks it.
    nonisolated static func looksInformational(_ text: String) -> Bool {
        let t = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard t.count <= 300 else { return false }
        let lower = t.lowercased()
        let markers = ["教えて", "とは", "について", "比較", "説明して", "まとめて",
                       "調べ", "何", "誰", "いつ", "どこ", "なぜ", "どう", "?", "？",
                       "what", "how", "why", "who", "when", "explain", "compare",
                       "tell me", "latest"]
        return markers.contains { lower.contains($0) }
    }

    /// True when the message answers a question this app asked — picking
    /// a candidate rather than posing a new one.
    nonisolated static func looksLikeChoiceReply(_ text: String) -> String? {
        let t = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard t.count <= 12 else { return nil }
        if HierarchicalExploreGate.isAutopilotChoice(t) { return "autopilot" }
        let folded = HierarchicalExploreGate.halfwidthDigits(t)
        if Int(folded) != nil { return "number" }
        if folded.range(of: #"^\d+\s*(番|つめ|つ目|番目)?$"#, options: .regularExpression) != nil {
            return "ordinal"
        }
        return nil
    }


    func sendMessage(with overrideText: String? = nil, forceBypassGatekeeper: Bool = false, isSpotlight: Bool = false) {
        let text = (overrideText ?? inputText).trimmingCharacters(in: .whitespacesAndNewlines)
        let hasAttachments = veraEngineMode == .atelier
            ? AtelierIntake.shared.hasComposerAttachment
            : (!attachedImages.isEmpty || !attachedFiles.isEmpty)
        guard !text.isEmpty || hasAttachments else { return }
        // A send dropped in silence is the worst version of this: the box
        // clears, nothing appears, and there is no way to tell a busy app
        // from a broken one. `isGenerating` is cleared at twenty-eight
        // different exits, so one missed path strands it — say so, and
        // leave what was typed where it was.
        guard !isGenerating else {
            addSystemMessage("⏳ 生成中のため送信していません。停止してから送ってください。")
            return
        }

        // ── Command an app by name ────────────────────────────────────
        // Works in every mode, because this is work rather than UI
        // navigation. Safety comes from the three-part requirement in
        // VeraSummon.resolveDelegation and from the licence, not from
        // which mode happens to be selected.
        if !text.isEmpty,
           let request = VeraSummon.resolveDelegation(text, goal: text) {
            inputText = ""
            messages.append(ChatMessage(role: .user, content: text))
            let pending = ChatMessage(role: .assistant,
                                      content: "▸ \(request.app.displayName) / "
                                             + "\(request.verb.displayName) …")
            messages.append(pending)
            Task { @MainActor in
                let evidence = await AppDelegation.shared.perform(request)
                // What is reported is what the rung could witness. A
                // hand-off says so rather than borrowing the word for a
                // measured success.
                var body = "▸ \(evidence.app.displayName) / \(evidence.verb.displayName)\n"
                    + "\(evidence.payload)\n\(evidence.verdict)"
                if !evidence.head.isEmpty {
                    body += "\n\n" + evidence.head
                }
                if evidence.outcome == .refusedNoLicence {
                    body += "\n\n" + AppLanguage.shared.t(
                        "Say 「licence」 to grant it.",
                        "「免許」と入力すると許可できます。")
                }
                if let i = self.messages.firstIndex(where: { $0.id == pending.id }) {
                    self.messages[i].content = body
                }
            }
            return
        }

        // ── Attached documents: offered, never taken ──────────────────
        // Any mode. An attachment reaches the store only through a yes,
        // and the yes is read from the same kind of closed table the
        // summons use — 「はい」 opens the door, everything else leaves
        // it shut and passes the line on as an ordinary turn.
        if !pendingIngest.isEmpty, !text.isEmpty {
            let answer = VeraSummon.resolveConsent(text)
            if answer == .yes {
                let files = pendingIngest
                pendingIngest = []
                inputText = ""
                messages.append(ChatMessage(role: .user, content: text))
                inferenceTask = Task {
                    var docs: [(source: String, text: String)] = []
                    for url in files {
                        if let body = try? String(contentsOf: url, encoding: .utf8) {
                            docs.append((source: url.lastPathComponent, text: body))
                        }
                    }
                    let reply = docs.isEmpty
                        ? "🚫 読めた文書がありません(テキストとして開けませんでした)。取り込んでいません。"
                        : "📥 " + (await VeraMemoryBridge.ingestDocuments(docs))
                    await MainActor.run {
                        self.messages.append(ChatMessage(
                            role: .assistant, content: reply))
                        self.isGenerating = false
                    }
                }
                return
            }
            if answer == .domain {
                let files = pendingIngest
                pendingIngest = []
                inputText = ""
                messages.append(ChatMessage(role: .user, content: text))
                inferenceTask = Task {
                    var lines: [String] = []
                    for url in files {
                        // The domain name comes from the file, not from a
                        // guess about what the document is about — a table
                        // name that was inferred is a table nobody can find
                        // again.
                        let stem = url.deletingPathExtension().lastPathComponent
                        let name = stem.lowercased().map {
                            $0.isLetter || $0.isNumber ? String($0) : "_"
                        }.joined().prefix(32)
                        lines.append(await VeraMemoryBridge.registerDomain(
                            String(name), path: url.path))
                    }
                    let reply = lines.isEmpty
                        ? "🚫 登録できる文書がありません。"
                        : lines.joined(separator: "\n")
                    await MainActor.run {
                        self.messages.append(ChatMessage(
                            role: .assistant, content: reply))
                        self.isGenerating = false
                    }
                }
                return
            }
            if answer == .no {
                pendingIngest = []
                addSystemMessage("<think>\n▸ 取り込みません。会話の中だけで扱います。\n</think>")
            }
            // An unrelated line clears the offer rather than holding it
            // open: a question waiting three turns for an answer becomes
            // a trap the next 「はい」 falls into.
            pendingIngest = []
        }

        // ── ⟨verantyx⟩ … ⟨/verantyx⟩ pastes a document straight in ──────
        //
        // <verantyx>…</verantyx> のタグ投入は廃止(2026-08-19、ユーザ指示)。
        // 語彙(分野)側にしか入らない片道の入口で、文書側と入れ違う。
        // 投入は OPERATOR の文書/分野画面の共通フォーム一つに集約 —
        // そこは文書・分野・両方をトグルで選べる。

        // ── A new attachment asks first ───────────────────────────────
        if veraEngineMode != .atelier, !attachedFiles.isEmpty {
            pendingIngest = attachedFiles
            let names = attachedFiles.map { $0.lastPathComponent }
                .prefix(3).joined(separator: "・")
            addSystemMessage("<think>\n▸ \(names) をどうしますか?"
                + "「はい」で Vera に取り込み(事実として)、"
                + "「分野」でこの文書の語彙として登録(言葉だけ)、"
                + "それ以外は会話の中だけで扱います。\n</think>")
        }

        // ── Summon by name: removed with Bot mode (2026-08-26) ─────────
        // `VeraSummon.resolve` fired ONLY here, gated on Bot mode by
        // design — the doc comment on `resolve()` said so explicitly:
        // 「設定」 typed in Atelier or LLM mode is a word in a sentence,
        // not a request to open the settings panel, so the match was
        // never meant to run outside the one mode whose subject was the
        // app itself. With that mode gone, so is this gate; a cross-mode
        // summon would need a new, deliberate design (word-collision
        // risk this comment used to guard against), not a silent
        // reinstatement here. Every registry screen this used to reach
        // (記憶, 十字, 設定, 監査…) is still reachable from Settings ›
        // All Screens › Open — see SettingsView.open().
        inputText = ""

        // Snapshot first, then clear the one-turn composer state.  The
        // transcript renders real attachment objects; filename markers in the
        // text made the image invisible and polluted the LLM conversation.
        let snapshotImages = attachedImages
        let snapshotFiles  = attachedFiles
        let atelierComposerClip = veraEngineMode == .atelier
            ? AtelierIntake.shared.composerSelectedClip : nil
        let messageAttachments: [ChatMessage.Attachment]
        if let clip = atelierComposerClip,
           let attachment = AttachmentManager.transcriptAttachment(
                forImagePath: clip.path) {
            messageAttachments = [attachment]
        } else if veraEngineMode == .atelier {
            messageAttachments = []
        } else {
            let images = snapshotImages.compactMap {
                AttachmentManager.transcriptAttachment(for: $0)
            }
            let files = snapshotFiles.map {
                ChatMessage.Attachment(kind: .file,
                                       name: $0.lastPathComponent,
                                       path: $0.path)
            }
            messageAttachments = images + files
        }
        attachedImages.removeAll()
        attachedFiles.removeAll()
        if veraEngineMode == .atelier {
            AtelierIntake.shared.clearComposerSelection()
        }

        messages.append(ChatMessage(role: .user, content: text,
                                    isSpotlight: isSpotlight,
                                    attachments: messageAttachments))
        currentGenerationIsSpotlight = isSpotlight
        isGenerating = true

        // ── Vera bot / Vera model modes: removed 2026-08-26 ────────────
        // Bot answered questions about the app from the settings
        // registry (VeraMemoryBridge.settingsAnswer); Vera model
        // answered with typed verdicts and no LLM in the turn
        // (VeraMemoryBridge.veraModelTurn, veraTrailCore as its visible
        // trail). Both functions still exist but are now uncalled —
        // deleting them was judged out of scope for a mode removal and
        // is flagged separately rather than done silently.

// Auto-create session if there isn't one yet
        if sessions.activeSessionId == nil {
            _ = sessions.newSession(messages: messages, workspacePath: workspaceURL?.path)
        }

        inferenceTask = Task {
            // ── ATELIER BEGINNER CHAT ────────────────────────────────
            // The existing full-screen Chat tab is the beginner UI. Every
            // Atelier turn goes to the selected garment LLM instead of the
            // generic coding AgentLoop. The model owns the natural response
            // and may attach a typed proposal; Vera remains the only controller
            // of validation, tools, transitions and human approval.
            if self.veraEngineMode == .atelier {
                let model = AtelierAnalyst.shared.pick.label
                await MainActor.run {
                    self.messages.append(ChatMessage(
                        role: .system,
                        content: "<think>\n制作モデル: \(model)\n自由応答（AI生成を明示）＋ 任意の型付き提案 → Vera検証\n</think>"))
                }
                let resolution = await AtelierChatRouter.resolveFlexible(text)
                let answer = AtelierChatRouter.transcriptText(for: resolution)
                await MainActor.run {
                    self.messages.append(ChatMessage(
                        role: .assistant, content: answer,
                        isSpotlight: self.currentGenerationIsSpotlight))
                    self.isGenerating = false
                    self.sessions.updateActiveSession(
                        messages: self.messages,
                        workspacePath: self.workspaceURL?.path)
                    AgentActivityCenter.shared.finish()
                }
                return
            }

            // ── BENCHMARK INTEGRATION ────────────────────────────────────────
            if text.starts(with: "/benchmark") {
                let parts = text.split(separator: " ")
                
                if parts.count >= 2 && parts[1] == "status" {
                    await MainActor.run { self.addSystemMessage("📊 取得中: Benchmark Status...") }
                    let result = await MCPEngine.shared.callTool(
                        serverName: "verantyx-compiler",
                        toolName: "benchmark_status",
                        arguments: [:]
                    )
                    await MainActor.run {
                        self.isGenerating = false
                        self.addSystemMessage("✅ Benchmark Complete")
                        self.messages.append(ChatMessage(role: .assistant, content: "📈 Benchmark Status:\n\n\(result)", isSpotlight: self.currentGenerationIsSpotlight))
                        self.saveCurrentSession()
                    }
                    return
                }
                
                await MainActor.run { self.addSystemMessage("🚀 起動中: LongMemEval Benchmark...") }
                
                // Parse arguments like "/benchmark batch=5 total=10"
                var args: [String: Any] = [:]
                for part in parts.dropFirst() {
                    let kv = part.split(separator: "=")
                    if kv.count == 2, let v = Int(String(kv[1])) {
                        args[String(kv[0])] = v
                    }
                }
                
                let result = await MCPEngine.shared.callTool(
                    serverName: "verantyx-compiler",
                    toolName: "solve_all",
                    arguments: args
                )
                
                await MainActor.run {
                    self.isGenerating = false
                    self.addSystemMessage("✅ Benchmark Complete")
                    self.messages.append(ChatMessage(role: .assistant, content: "📈 Benchmark Result:\n\n\(result)", isSpotlight: self.currentGenerationIsSpotlight))
                    self.saveCurrentSession()
                }
                return
            }

            // ── PIPELINE INTENT DETECTION ───────────────────────────────────
            // NOTE: Gatekeeper Mode ON の場合は CommanderOrchestrator が全処理を担うため
            //       ここでの旧フロー (BitNetCommanderLoop) ルーティングは完全に廃止しました。

            // ── SYSTEM STATUS INJECTION ──────────────────────────────────────
            // 状態確認系の質問 or バックグラウンドプロセスが動いているとき、
            // AI の systemPrompt にリアルタイムの状態ブロックを注入する。
            // → AI は「L2.5 が今 45% 完了」などを自律的に答えられる。
            let statusBlock = await MainActor.run {
                SystemStatusProvider.shared.systemStatusBlock()
            }
            if let status = statusBlock {
                await MainActor.run { self.systemPrompt += "\n\n" + status }
                // 返答後にステータスブロックを除去 (永続汚染しない)
                defer {
                    Task { @MainActor in
                        if let range = self.systemPrompt.range(of: "\n\n[SYSTEM STATUS") {
                            self.systemPrompt = String(self.systemPrompt[..<range.lowerBound])
                        }
                    }
                }
            }
            // 状態確認系の質問なら fullStatusReport を先にチャットに挿入
            if SystemStatusProvider.isStatusQuery(text) {
                let report = await MainActor.run {
                    SystemStatusProvider.shared.fullStatusReport()
                }
                await MainActor.run {
                    self.addSystemMessage(AppLanguage.shared.t("📊 System state snapshot:\n\(report)", "📊 システム状態スナップショット:\n\(report)"))
                }
            }
            // ── END STATUS INJECTION ─────────────────────────────────────────

            // Compress context if needed (Cortex anti-Alzheimer's)
            let trimmed = cortex.compressIfNeeded(messages: messages)
            if trimmed.count < messages.count {
                await MainActor.run { self.messages = trimmed }
            }

            // Route: UI-based Router
            let isGatekeeperEnabled = forceBypassGatekeeper ? false : await MainActor.run(body: { GatekeeperModeState.shared.isEnabled })
            // UI determines task type: IDE input -> Programming, Spotlight -> General
            let isProgrammingTask = !isSpotlight

            if isGatekeeperEnabled && isProgrammingTask {
                // Gatekeeper Mode → 新フロー (6軸IR → GraphPatch JSON → Vault復元)
                await GatekeeperChatBridge.shared.run(instruction: text, images: snapshotImages as! [String], appState: self)
            } else if isGatekeeperEnabled && !isProgrammingTask {
                // General Task during Gatekeeper Mode (Spotlight)
                await MainActor.run {
                    let msg = self.t("🧭 Spotlight Agent: Routing general task to \(self.nonCodingTaskEngine.rawValue)",
                                     "🧭 Spotlight Agent: 汎用タスクとして \(self.nonCodingTaskEngine.rawValue) にルーティングします")
                    self.addSystemMessage(msg)
                }
                
                let engine = await MainActor.run { self.nonCodingTaskEngine }
                if engine == .cloudDirect {
                    // Bypass Gatekeeper, send to Cloud Model
                    await runHybrid(instruction: text)
                } else {
                    // Local Agent
                    let history = Array(self.messages.dropLast())
                    await runAgentLoop(instruction: text,
                                       images: snapshotImages,
                                       files: snapshotFiles,
                                       previousMessages: history)
                }
            } else if inferenceMode == .cloudDirect || inferenceMode == .privacyShield || inferenceMode == .paranoiaMode {
                await runHybrid(instruction: text)
            } else if CouncilSettingsStore.shared.useVeraHarnessForChat {
                // Milestone N: Vera-alpha's own Agent.run() drives the turn
                // over HTTP+SSE (vera_server.py) instead of this app's
                // AgentLoop/CouncilOrchestrator -- Vera is the controller
                // here, not a tool this app calls.
                await runVeraHarness(instruction: text, files: snapshotFiles)
            } else if agentLoopEnabled {
                // 4-layer path: explicit `/council <question>`, or every turn
                // when the JGEN options popover has "use the council for
                // normal chat" on. Falls back to the plain loop by itself if
                // no JGEN model is loaded.
                let trimmed = text.trimmingCharacters(in: .whitespaces)
                let isCouncilCommand = trimmed.lowercased().hasPrefix("/council")
                let question = isCouncilCommand
                    ? String(trimmed.dropFirst("/council".count)).trimmingCharacters(in: .whitespaces)
                    : text
                let useLayered = (isCouncilCommand || CouncilSettingsStore.shared.useCouncilForChat)
                    && self.veraEngineMode != .localLLM

                let history = Array(self.messages.dropLast())
                await runAgentLoop(instruction: question.isEmpty ? text : question,
                                   images: snapshotImages,
                                   files: snapshotFiles,
                                   previousMessages: history,
                                   useLayered: useLayered)
            } else {
                await runSinglePass(instruction: text,
                                    images: snapshotImages,
                                    files: snapshotFiles)
            }

            // Persist session after each exchange
            sessions.updateActiveSession(messages: messages, workspacePath: workspaceURL?.path)
        }
    }

    // Pipeline Intent Classifier removed (Routing is now strictly UI-based)

    // (sendMessage本体のクロージングブレースはここに続く)
    // MARK: - Cancel generation
    /// Make a cloud model the active chat model.
    ///
    /// Keys were configurable long before this existed, so a provider could be
    /// fully set up and still unusable — the selector had no row for it and
    /// nothing ever set modelStatus to a cloud value.
    /// Use Claude through the Agent SDK on the existing Claude Code login.
    func selectClaudeAgentModel(_ model: String) {
        UserDefaults.standard.set(model, forKey: "claude_agent_model")
        modelStatus = .claudeAgentReady(model: model)
        addSystemMessage(t("🧩 Agent SDK: \(model)",
                           "🧩 Agent SDK 経由で \(model) を選択しました（Claude Code のログインを使用）"))
    }

    func selectCloudModel(provider: CloudProvider, model: String) {
        UserDefaults.standard.set(model, forKey: provider.modelDefaultsKey)
        activeCloudProvider = provider
        let key = UserDefaults.standard.string(forKey: provider.spec.keyDefaults) ?? ""
        let masked = key.count > 8 ? "…\(key.suffix(4))" : "set"
        modelStatus = .anthropicReady(model: model, maskedKey: masked)
        addSystemMessage(t("☁️ \(provider.rawValue): \(model)",
                           "☁️ \(provider.rawValue): \(model) を選択しました"))
    }

    /// Which provider `.anthropicReady` currently refers to. That case predates
    /// multi-provider support and its name is now historical; this says who is
    /// actually being called.
    @Published var activeCloudProvider: CloudProvider = {
        if let raw = UserDefaults.standard.string(forKey: "active_cloud_provider"),
           let p = CloudProvider(rawValue: raw) { return p }
        return .claude
    }() {
        didSet { UserDefaults.standard.set(activeCloudProvider.rawValue,
                                           forKey: "active_cloud_provider") }
    }

    func cancelGeneration() {
        inferenceTask?.cancel()
        inferenceTask = nil
        isGenerating = false
        addSystemMessage(self.t("⏹ Inference aborted", "⏹ 推論を中断しました"))

        // ── [NEW] INTERRUPT SNAPSHOT ──
        // Capture incomplete state and move origin task to far/
        let currentMessages = self.messages
        let sid = self.vxChatSessionId
        Task.detached {
            let userIntent = currentMessages.last(where: { $0.role == .user })?.content ?? "Unknown task"
            let l2Lines = [
                "OP.FACT(\"status\", \"incomplete_suspended\")",
                "OP.FACT(\"last_intent\", \"\(String(userIntent.prefix(200)).replacingOccurrences(of: "\n", with: " "))\")",
                "OP.FACT(\"origin_task_id\", \"\(sid)\")"
            ]
            let ts = Int(Date().timeIntervalSince1970)
            SessionMemoryArchiver.shared.archiveConversationChunk(
                chunkId: "INTERRUPT_\(sid)_\(ts)",
                taskTitle: "Suspended Task Snapshot",
                l1: "[中断] 未完了スナップショット",
                l2: l2Lines.joined(separator: "\n"),
                l3: ""
            )
            // Move the original PROG/CONV chunks to far/
            SessionMemoryArchiver.shared.moveToFarZone(shortId: sid)
        }
    }

    // MARK: - Hybrid Engine (Privacy Shield / Cloud Direct)

    private func runHybrid(instruction: String) async {
        let context = selectedFileContent.isEmpty ? nil : selectedFileContent
        let contextFile = selectedFile
        await MainActor.run { self.privacySteps = [] }

        let snap_mode     = inferenceMode
        let snap_provider = cloudProvider
        let snap_model    = effectiveModelName
        let snap_status   = modelStatus

        // ── Privacy Shield / Paranoia Mode: PrivacyGateway (Phase 1 + Phase 2 + JCross) ──
        // cloudDirect: HybridEngine (マスキングなし、直接送信)
        // paranoiaMode: PrivacyGateway → ParanoiaEngine (AST-surgical phase 3)
        if (snap_mode == .privacyShield || snap_mode == .paranoiaMode),
           let fileContent = context, let fileName = contextFile?.lastPathComponent {

            let snap_gemma = gemmaSemanticMaskingEnabled

            let gatewayResult = await PrivacyGateway.shared.processWithGateway(
                instruction: instruction,
                fileContent: fileContent,
                fileName: fileName,
                fileURL: contextFile,
                modelStatus: snap_status,
                activeModel: snap_model,
                provider: snap_provider,
                cortex: cortex,
                useGemmaSemanticMasking: snap_gemma
            ) { [weak self] step in
                guard let self else { return }
                await MainActor.run {
                    self.privacySteps.append(step)
                    self.messages.append(ChatMessage(role: .system, content: step))
                }
            }

            await MainActor.run {
                isGenerating = false
                // GatewayStats → MaskingStats 変換 (UI表示用)
                lastMaskingStats = MaskingStats(
                    functions: gatewayResult.maskingStats.phase1RegexMasked,
                    classes:   0,
                    variables: gatewayResult.maskingStats.phase2SemanticMasked,
                    strings:   gatewayResult.maskingStats.secretsBlocked,
                    paths:     gatewayResult.maskingStats.pathsProtected
                )
                messages.append(ChatMessage(role: .assistant, content: gatewayResult.explanation, isSpotlight: currentGenerationIsSpotlight))
                if let code = gatewayResult.restoredCode, !code.isEmpty, let fileURL = contextFile {
                    let diff = FileDiff(
                        fileURL: fileURL,
                        originalContent: selectedFileContent,
                        modifiedContent: code,
                        hunks: DiffEngine.compute(original: selectedFileContent, modified: code)
                    )
                    pendingDiff = diff; showDiff = true
                }
            }
            return
        }

        // ── Cloud Direct (or no file selected in Shield mode): HybridEngine ──
        let result = await HybridEngine.shared.process(
            instruction: instruction,
            fileContent: context,
            fileName: contextFile?.lastPathComponent,
            fileURL: contextFile,
            mode: snap_mode,
            modelStatus: snap_status,
            activeOllamaModel: snap_model,
            cloudProvider: snap_provider,
            cortex: cortex
        ) { [weak self] step in
            guard let self else { return }
            await MainActor.run {
                self.privacySteps.append(step)
                self.messages.append(ChatMessage(role: .system, content: step))
            }
        }

        await MainActor.run {
            isGenerating = false
            lastMaskingStats = result.maskingStats
            let rawContent = result.explanation
            // Strip artifact tags from chat display
            let displayContent = ArtifactParser.stripArtifactTags(from: rawContent)
            messages.append(ChatMessage(role: .assistant, content: displayContent, isSpotlight: currentGenerationIsSpotlight))

            // Artifact detection
            if let artifact = ArtifactParser.extract(from: rawContent) {
                ingestArtifact(artifact)
            }

            if let code = result.modifiedCode, !code.isEmpty, let fileURL = contextFile {
                let diff = FileDiff(
                    fileURL: fileURL,
                    originalContent: selectedFileContent,
                    modifiedContent: code,
                    hunks: DiffEngine.compute(original: selectedFileContent, modified: code)
                )
                pendingDiff = diff
                showDiff = true
            }
        }
    }

    /// Apply a diff immediately (AI Priority mode — no confirmation).
    func autoApplyDiff(_ diff: FileDiff) {
        do {
            try diff.modifiedContent.write(to: diff.fileURL, atomically: true, encoding: .utf8)
            selectedFileContent = diff.modifiedContent
            addSystemMessage(self.t("⚡ [AI Priority] Auto-applied diff: \(diff.fileURL.lastPathComponent)", "⚡ [AI Priority] 差分を自動適用: \(diff.fileURL.lastPathComponent)"))
        } catch {
            addSystemMessage(self.t("❌ Auto-apply failed: \(error.localizedDescription)", "❌ 自動適用失敗: \(error.localizedDescription)"))
        }
        pendingDiff = nil
        showDiff = false
    }

    /// Save artifact and show panel.
    func ingestArtifact(_ artifact: Artifact) {
        currentArtifact = artifact
        artifactHistory.insert(artifact, at: 0)
        showArtifactPanel = true
    }

    // MARK: - Agent Loop (multi-turn, scaffolding)

    /// Milestone N: hands the turn to Vera-alpha's own Agent.run() ReAct
    /// loop over HTTP+SSE (see VeraAgentClient.swift / vera_server.py).
    /// Deliberately minimal compared to runAgentLoop's LoopEvent handler --
    /// Vera's on_step events are its own JSON shapes (action/observation),
    /// not this app's `LoopEvent`, so this renders them as system-message
    /// progress lines rather than trying to unify the two event models.
    ///
    /// Vera harness planner routing must honor the user's Ollama / L2-JGEN
    /// settings — never silently default to `backend: "ollama"` (:11434).
    ///
    /// Settings:
    /// - Ollama "on" ⇔ `modelStatus == .ollamaReady` (active chat backend).
    ///   Selecting JGEN / ejecting Ollama turns it off for harness purposes.
    /// - L2-JGEN ⇔ `CouncilSettingsStore.executionUseJGEN`
    ///   (`UserDefaults` key `council_execution_use_jgen`, checkbox
    ///   "Layer 2もJGENで実行").
    ///
    /// When Ollama is off and/or L2-JGEN is on and a `.jgen` is loaded,
    /// planner uses `backend: "jgen"` via `JGenAgentServer` (:8766).
    /// When Ollama is off and JGEN isn't available, show a clear message
    /// and fall back to the local council/Act path — never POST to :11434.
    private func runVeraHarness(instruction: String, files: [URL] = []) async {
        isGenerating = true
        // Cleared explicitly before fallback so runAgentLoop owns the flag;
        // on the success / hard-fail paths the defer still clears it.
        var handedOffToFallback = false
        defer {
            if !handedOffToFallback { isGenerating = false }
        }

        // Real bug found live: the 📎 attachment chip in the chat input
        // (`attachedFiles`) was silently dropped on this path -- unlike
        // `runAgentLoop`/`runHybrid`, this function never took a `files`
        // parameter at all, so a user who attached a folder and just said
        // "analyze this" got "which file did you mean?" back from Vera,
        // even though something WAS attached. Vera's own tools
        // (list_dir/read_file) expect to actively explore a path, not
        // receive pre-loaded content, so the fix is the same thing the
        // user had to do manually to work around it: put the attached
        // path(s) directly into the task text Vera actually receives.
        var instruction = PromptBudget.truncateForModel(instruction)
        if !files.isEmpty {
            let pathList = files.map { $0.path }.joined(separator: "\n")
            instruction += "\n\n" + t("Attached path(s):", "添付されたパス:") + "\n" + pathList
            // Re-bound after attaching paths so a huge paste + paths cannot
            // explode Vera's planner when the GPU is idle.
            instruction = PromptBudget.truncateForModel(instruction)
        }

        let mode = CouncilSettingsStore.shared.cognitionMode
        if mode != .normal {
            // Milestone O: required warning banner -- shown every time a
            // non-normal mode is active, not just once on toggle, so it
            // can't scroll out of sight and be forgotten mid-session.
            addSystemMessage(t(
                "⚠️ Experimental cognition is enabled.\nVera may: inspect additional local files · create persistent knowledge-gap nodes · run read-only analysis tools · propose new facts and skills.\nVera will not: modify project files without approval · access unapproved sources · treat acquired knowledge as trusted without verification.",
                "⚠️ 実験的な認知モードが有効です。\nVeraは: 追加のローカルファイルを調べる・永続的な知識ギャップノードを作成する・読み取り専用の解析ツールを実行する・新しい事実やスキルを提案する、ことがあります。\nVeraは: 承認なしにプロジェクトファイルを変更する・未承認の情報源へアクセスする・検証なしに取得した知識を信頼済みとして扱う、ことはありません。"
            ))
        }
        addSystemMessage(t("🧭 Vera harness: taking over this turn…", "🧭 Veraハーネス: このターンを引き継ぎます…"))

        // Gap-driven: ensure a GapNode exists before Agent.run so early
        // "couldn't clone" surrender is a GapGraph violation, not the default.
        if mode != .normal {
            let gapId = await VeraMemoryBridge.bootstrapUnknownTask(
                name: "harness:\(String(instruction.prefix(80)))",
                description: "Vera harness mission",
                userGoal: String(instruction.prefix(400)),
                availableTools: "vera_git_clone,vera_code_ingest,web_search,fetch_url,vera_ask",
                successCriteria: "task completed without premature surrender",
                constraints: "identical tool spam blocked; keep trying distinct strategies while gap open",
                cognitionMode: mode.rawValue
            )
            if let gapId {
                addSystemMessage(t(
                    "🕳 [GAP] harness open id=\(gapId) — persist until resolved or strategies exhausted",
                    "🕳 [GAP] ハーネス open id=\(gapId) — 解決か戦略尽くまで継続"
                ))
            }
        }

        let council = CouncilSettingsStore.shared
        let jgenLoaded: Bool = {
            if case .jcrossReady = modelStatus { return true }
            return false
        }()
        // Ollama "on" for harness = Ollama is the selected active chat backend.
        // Selecting JGEN / ejecting Ollama / MLX / BitNet turns it off.
        let ollamaActiveBackend: Bool = {
            if case .ollamaReady = modelStatus { return true }
            return false
        }()
        // Checkbox: "Layer 2もJGENで実行" → UserDefaults `council_execution_use_jgen`
        let l2UseJGEN = council.executionUseJGEN
        // (Ollama off OR L2-JGEN on) + loaded .jgen → must use jgen planner.
        // (With a single modelStatus enum, jcrossReady already implies Ollama
        // off — still read both flags so routing never ignores the checkbox.)
        let mustUseJgenPlanner = jgenLoaded && (l2UseJGEN || !ollamaActiveBackend)
        // Never POST backend=ollama / probe :11434 unless Ollama is active
        // and we are not on the forced-JGEN path.
        let ollamaAllowedForHarness = ollamaActiveBackend && !mustUseJgenPlanner

        var harnessBackend: String? = nil
        var harnessModel = activeOllamaModel
        var jgenEndpoint: String? = nil

        if mustUseJgenPlanner {
            do {
                try await JGenAgentServer.shared.start()
                let port = await JGenAgentServer.shared.port
                let endpoint = "http://127.0.0.1:\(port)"
                jgenEndpoint = endpoint
                harnessBackend = "jgen"
                if case .jcrossReady(let m) = modelStatus { harnessModel = m }
                addSystemMessage(t(
                    "🔗 Vera planner → JGEN bridge (\(endpoint))"
                        + (l2UseJGEN ? " [L2=JGEN]" : "")
                        + (!ollamaActiveBackend ? " [Ollama off]" : ""),
                    "🔗 Veraプランナー → JGENブリッジ (\(endpoint))"
                        + (l2UseJGEN ? " [L2=JGEN]" : "")
                        + (!ollamaActiveBackend ? " [Ollamaオフ]" : "")
                ))
            } catch {
                // Settings forbid Ollama — do NOT fall through to :11434.
                addSystemMessage(t(
                    "⚠️ JGEN bridge failed to start (\(error.localizedDescription)). Ollama is off / L2-JGEN is on — falling back to local JGEN/council Act (not contacting \(ollamaEndpoint)).",
                    "⚠️ JGENブリッジ起動に失敗 (\(error.localizedDescription))。Ollamaオフ / L2=JGENのため \(ollamaEndpoint) には接続せず、ローカルのJGEN/合議Act経路へフォールバックします。"
                ))
                handedOffToFallback = true
                isGenerating = false
                await fallbackVeraHarnessToLocalPath(instruction: instruction, files: files)
                return
            }
        } else if !ollamaAllowedForHarness {
            // Ollama off (or L2-JGEN without a usable loaded .jgen): never hit :11434.
            addSystemMessage(t(
                "⚠️ Ollama is off and no JGEN planner is available (L2-JGEN=\(l2UseJGEN ? "on" : "off"), .jgen loaded=\(jgenLoaded)). Falling back to local council/Act — not contacting \(ollamaEndpoint).",
                "⚠️ Ollamaはオフで、JGENプランナーも使えません（L2=JGEN=\(l2UseJGEN ? "オン" : "オフ")、.jgenロード=\(jgenLoaded)）。\(ollamaEndpoint) には接続せず、ローカルの合議/Act経路へフォールバックします。"
            ))
            handedOffToFallback = true
            isGenerating = false
            await fallbackVeraHarnessToLocalPath(instruction: instruction, files: files)
            return
        } else {
            let ollamaUp = await OllamaClient.shared.isAvailable()
            if !ollamaUp {
                addSystemMessage(t(
                    "⚠️ Vera LLM HTTP unavailable (Ollama not reachable at \(ollamaEndpoint)). Falling back to JGEN/council Act.",
                    "⚠️ VeraのLLM HTTPが使えません（Ollamaが \(ollamaEndpoint) に応答しません）。JGEN/合議のAct経路へフォールバックします。"
                ))
                handedOffToFallback = true
                isGenerating = false
                await fallbackVeraHarnessToLocalPath(instruction: instruction, files: files)
                return
            }
            harnessBackend = "ollama"
            harnessModel = activeOllamaModel
        }

        guard let harnessBackend else {
            handedOffToFallback = true
            isGenerating = false
            await fallbackVeraHarnessToLocalPath(instruction: instruction, files: files)
            return
        }

        // Hard guard: settings said no Ollama — never send backend=ollama.
        if harnessBackend == "ollama" && !ollamaAllowedForHarness {
            addSystemMessage(t(
                "⚠️ Refusing Ollama planner (settings: Ollama off / L2-JGEN). Falling back to local council/Act.",
                "⚠️ 設定によりOllamaプランナーを拒否しました（Ollamaオフ / L2=JGEN）。ローカルの合議/Act経路へフォールバックします。"
            ))
            handedOffToFallback = true
            isGenerating = false
            await fallbackVeraHarnessToLocalPath(instruction: instruction, files: files)
            return
        }

        let ensure = await VeraAgentClient.shared.ensureServerRunning(jgenEndpoint: jgenEndpoint)
        guard ensure.isReady else {
            let detail: String
            switch ensure {
            case .binaryMissing:
                detail = t(
                    "Vera HTTP cannot start — check MCP / bundled vera-memory binary.",
                    "Vera HTTP が起動できません — MCP/同梱バイナリを確認"
                )
            case .launchFailed(let msg):
                detail = t(
                    "Vera HTTP cannot start — \(msg)",
                    "Vera HTTP が起動できません — \(msg)"
                )
            case .notReachable:
                detail = t(
                    "Vera HTTP cannot start — no response on :8765 (check serve.log / bundled vera-memory).",
                    "Vera HTTP が起動できません — :8765 に応答なし（serve.log / 同梱 vera-memory を確認）"
                )
            case .ready:
                detail = "unreachable"
            }
            addSystemMessage("⚠️ \(detail)")
            handedOffToFallback = true
            isGenerating = false
            await fallbackVeraHarnessToLocalPath(instruction: instruction, files: files)
            return
        }

        do {
            let result = try await VeraAgentClient.shared.runAgent(
                task: instruction, model: harnessModel, backend: harnessBackend,
                cognitionMode: mode.rawValue
            ) { [weak self] event in
                guard let self else { return }
                Task { @MainActor in
                    switch event.source {
                    case "react_step":
                        if let action = event.raw["action"] as? [String: Any],
                           let tool = action["tool"] as? String {
                            self.addSystemMessage(self.t("🔧 Vera called: \(tool)", "🔧 Veraが呼び出し: \(tool)"))
                        }
                        if let obs = event.raw["observation"] as? [String: Any],
                           let err = obs["error"] as? String,
                           err == "identical_tool_blocked" || err == "gap_open_surrender_refused" {
                            self.addSystemMessage(self.t(
                                "🕳 [GAP] \(err) — keep exploring distinct approaches (not surrendering)",
                                "🕳 [GAP] \(err) — 別アプローチで探索継続（諦めない）"
                            ))
                        }
                    case "vera_direct":
                        self.addSystemMessage(self.t("🧩 Vera answered directly (no LLM step needed)", "🧩 Veraが直接回答(LLM不要)"))
                    case "llm_error":
                        self.addSystemMessage(self.t("⚠️ Vera's LLM step failed", "⚠️ VeraのLLM手順が失敗しました"))
                    default:
                        break
                    }
                }
            }

            // `result["final"]` is NOT always a dict: agent.py's own ReAct
            // loop returns the LLM's plain-string answer verbatim when it
            // completes via `{"thought": ..., "final": "<answer>"}` (see
            // agent.py:163) -- only the vera_direct/vera_only/llm_error
            // paths wrap it in a dict. Treating it as dict-only silently
            // dropped every successful plain-text answer (confirmed via a
            // real "こんにちは" turn that Vera answered correctly but the
            // IDE rendered as "no final answer returned").
            var connectivityError: String? = nil
            let finalText: String
            if let text = result["final"] as? String {
                finalText = text
            } else if let final = result["final"] as? [String: Any] {
                if let text = final["text"] as? String {
                    finalText = text
                } else if let error = final["error"] as? String {
                    if VeraAgentClient.isLLMConnectivityFailure(error) {
                        connectivityError = error
                        finalText = ""
                    } else {
                        finalText = t("(Vera error: \(error))", "(Veraエラー: \(error))")
                    }
                } else if let data = try? JSONSerialization.data(withJSONObject: final, options: [.prettyPrinted]),
                          let json = String(data: data, encoding: .utf8) {
                    finalText = json
                } else {
                    finalText = String(describing: final)
                }
            } else {
                finalText = t("(no final answer returned)", "(最終回答が返りませんでした)")
            }

            if let connectivityError {
                addSystemMessage(t(
                    "⚠️ Vera LLM HTTP failed (\(connectivityError)). Falling back to JGEN/council Act.",
                    "⚠️ VeraのLLM HTTPが失敗しました（\(connectivityError)）。JGEN/合議のAct経路へフォールバックします。"
                ))
                handedOffToFallback = true
                isGenerating = false
                await fallbackVeraHarnessToLocalPath(instruction: instruction, files: files)
                return
            }

            messages.append(ChatMessage(role: .assistant, content: finalText))
        } catch {
            let msg = error.localizedDescription
            if VeraAgentClient.isLLMConnectivityFailure(msg)
                || (error as? VeraAgentClient.ClientError) != nil {
                addSystemMessage(t(
                    "⚠️ Vera harness connectivity failed: \(msg). Falling back to JGEN/council Act.",
                    "⚠️ Veraハーネス接続に失敗: \(msg)。JGEN/合議のAct経路へフォールバックします。"
                ))
                handedOffToFallback = true
                isGenerating = false
                await fallbackVeraHarnessToLocalPath(instruction: instruction, files: files)
                return
            }
            addSystemMessage(t("❌ Vera harness error: \(msg)",
                               "❌ Veraハーネスエラー: \(msg)"))
        }
    }

    /// After Vera harness cannot reach its HTTP serve or planner LLM,
    /// continue the same user turn on the in-app JGEN/council (or plain
    /// AgentLoop) path — never leave Connection refused as the only outcome.
    private func fallbackVeraHarnessToLocalPath(instruction: String, files: [URL]) async {
        addSystemMessage(t(
            "↩️ Continuing on the local JGEN/council path…",
            "↩️ ローカルのJGEN/合議経路で続行します…"
        ))
        // ローカルLLMモード: 合議もJGENも通さず通常のエージェント経路のみ。
        let useLayered = veraEngineMode != .localLLM
            && (CouncilSettingsStore.shared.useCouncilForChat
            || LayeredRunOrchestrator.isAvailable
            || {
                if case .jcrossReady = modelStatus { return true }
                return false
            }())
        let history = Array(messages.dropLast())
        await runAgentLoop(
            instruction: instruction,
            files: files,
            previousMessages: history,
            useLayered: useLayered
        )
    }

    private func runAgentLoop(instruction: String,
                              images: [AttachedImage] = [],
                              files: [URL] = [],
                              previousMessages: [ChatMessage] = [],
                              useLayered: Bool = false) async {
        let context = selectedFileContent.isEmpty ? nil : selectedFileContent
        let contextFile = selectedFile
        let snap_workspace = workspaceURL
        let snap_model = isTalkieMode ? "kofdai/talkie-1930-13b-it-mlx-8bit" : effectiveModelName
        let snap_status = modelStatus

        // selfFixMode persists until the user explicitly toggles it off.
        // We only snapshot the current value to pass into AgentLoop.
        let snap_selfFix = selfFixMode

        // nano/small モデルはユーザーが operationMode を手動変更していても
        // 常に AI Priority ループで動作させる（VX-Loop + ConfusionDetector が必須なため）
        // ただし、Swarm Mode は特別に維持する
        let snap_operationMode: OperationMode = .gatekeeper

        // Build image context suffix so models that read text still see the filename
        var imageContext = ""
        if !images.isEmpty {
            imageContext = "\n\n[Attached images: " +
                images.map { $0.name }.joined(separator: ", ") + "]"
        }
        let fullInstruction = instruction + imageContext

        // ── Per-turn streaming message tracker ─────────────────────────
        // Reset at the start of each agent loop run so previous sessions'
        // stale UUIDs are never carried forward.
        streamingMsgId = nil

        // One handler, two runners: the layered (4-layer) path and the
        // plain agent loop both report through exactly the same event
        // stream, so chat rendering, streaming and approvals behave
        // identically either way.
        let handler: @Sendable (LoopEvent) async -> Void = { [weak self] event in
            guard let self else { return }
            await MainActor.run {
                // Any event other than streamToken represents (or precedes)
                // a turn boundary -- flush whatever's buffered first so
                // nothing is lost and downstream handling (e.g. .start
                // resetting streamingMsgId) sees the buffer already applied.
                if case .streamToken = event {} else {
                    self.flushStreamTokenBuffer()
                }
                if case .start = event {
                    ReasoningTimelineStore.shared.beginSession()
                }
                ReasoningTimelineStore.shared.ingest(event)
                switch event {
                case .start:
                    // Reset per-turn streaming ID when a new loop turn starts
                    self.streamingMsgId = nil
                    AgentActivityCenter.shared.set(.thinking)

                case .streamToken(let token):
                    // Tokens arriving is the only proof of generation; the
                    // other states are inferred from what the loop is doing.
                    AgentActivityCenter.shared.set(.generating)
                    self.streamTokenBuffer += token
                    if Date().timeIntervalSince(self.lastStreamFlush) >= 0.04 {
                        self.flushStreamTokenBuffer()
                    }

                case .thinking(let t):
                    AgentActivityCenter.shared.set(.thinking)
                    if t > 1 {
                        self.messages.append(ChatMessage(role: .system,
                            content: "<think>\n🔄 Agent loop turn \(t)…\n</think>"))
                    }

                case .aiMessage(let text):
                    // The phone was only ever sent the final answer, so a long
                    // run showed "Task complete." and nothing of how it got
                    // there — no way to comment, and no way to stop it. Every
                    // step goes out now, each with its own input box, so the
                    // relay is a conversation rather than a receipt.
                    if !text.isEmpty, ClipboardChatRelay.shared.isRunning {
                        ClipboardChatRelay.shared.send(text)
                    }
                    if !text.isEmpty {
                        // Detect PATCH_FILE blocks → register in SelfEvolutionEngine
                        let patches = PatchFileParser.extract(from: text)
                        for (relPath, content) in patches {
                            SelfEvolutionEngine.shared.registerPatch(for: relPath, newContent: content)
                        }
                        // Detect <artifact> tags
                        if let artifact = ArtifactParser.extract(from: text) {
                            self.ingestArtifact(artifact)
                        }
                        // Strip patch/artifact markup from display text
                        let stripped = PatchFileParser.strip(
                            from: ArtifactParser.stripArtifactTags(from: text)
                        ).trimmingCharacters(in: .whitespacesAndNewlines)

                        if !stripped.isEmpty {
                            // ── UUID-based anti-duplicate guard ─────────────
                            // Find the exact streaming message by its UUID.
                            // This is safe even when tool/system messages follow
                            // the streaming message ("last role" check would fail).

                            // Snapshot processLog → thinkingLog for post-completion display
                            let logSnapshot = self.logStore.entries.map { e in
                                ChatMessage.ThinkingLogEntry(
                                    timestamp: e.timestamp,
                                    text:      e.text,
                                    kind:      e.kind.rawValue
                                )
                            }

                            if let sid = self.streamingMsgId,
                               let idx = self.messages.firstIndex(where: { $0.id == sid }) {
                                // Finalise in-place with the clean stripped version
                                self.messages[idx].content      = stripped
                                self.messages[idx].thinkingLog  = logSnapshot
                            } else {
                                // No streaming message for this turn → new bubble
                                self.messages.append(ChatMessage(role: .assistant,
                                                               content: stripped,
                                                               isSpotlight: self.currentGenerationIsSpotlight))
                            }
                            // Reset ID after finalising so next turn starts fresh
                            self.streamingMsgId = nil
                        }
                        // Notify if patches detected
                        if !patches.isEmpty {
                            self.addSystemMessage(self.t("🧬 Detected \(patches.count) patches — check Self-Evolution panel", "🧬 \(patches.count) 個のパッチを検出 — Self-Evolution パネルで確認できます"))
                        }
                    }

                case .systemLog(let text):
                    // §TL: markers are timeline-only (ReasoningTimelineStore
                    // above already consumed them) -- they'd be unreadable
                    // noise if shown as a raw chat bubble.
                    if !text.hasPrefix("§TL:") {
                        self.messages.append(ChatMessage(role: .system, content: text))
                    }

                case .toolCall(let call):
                    // The tool the agent picked IS what it is doing — asking
                    // it beats maintaining a separate flag that every call
                    // site has to remember to set and clear.
                    AgentActivityCenter.shared.enter(for: call.tool)
                    self.messages.append(ChatMessage(role: .system,
                        content: "<think>\n⚙️ \(call.displayLabel)\n</think>"))
                    if case .runCommand(let cmd) = call.tool {
                        // The stage follows the work: a command fronts the
                        // terminal so the user watches it run, not a stale
                        // editor. Same rule the diff/artifact APIs follow.
                        self.aiShowTerminal()
                        Task { await self.terminal.run(cmd, in: self.workspaceURL, initiatedByAI: true) }
                    }


                case .toolResult(let call):
                    if !call.result.isEmpty {
                        let icon = call.succeeded ? "✅" : "❌"
                        self.messages.append(ChatMessage(role: .system,
                            content: "<think>\n\(icon) \(call.result.prefix(120))\n</think>"))
                    }

                case .workspaceChanged(let url):
                    self.workspaceURL = url
                    self.terminal.workingDirectory = url
                    self.refreshFiles()
                    self.addSystemMessage("📂 Workspace: \(url.lastPathComponent)")

                case .done(let msg, let ws):
                    self.isGenerating = false
                    ReasoningTimelineStore.shared.endSession()
                    if let ws = ws, self.workspaceURL == nil {
                        self.workspaceURL = ws
                        self.terminal.workingDirectory = ws
                        self.refreshFiles()
                    }
                    // ── Anti-duplicate guard ────────────────────────────────
                    // If a streaming message exists (streamingMsgId != nil),
                    // the content is already displayed — do NOT add another bubble.
                    // Only show .done text when there was no streaming at all
                    // (e.g. non-streaming model or tool-only turns with no text).
                    if !msg.isEmpty && self.streamingMsgId == nil {
                        // Duplicate guard: suffix matching missed the case
                        // where the streamed bubble carried a trailing
                        // SearchGate line the cleaned .done text lacks —
                        // the same essay then appeared twice. Containment
                        // of a healthy prefix is the honest test.
                        let lastContent = self.messages.last?.content ?? ""
                        let probe = String(msg.prefix(160))
                        if !lastContent.contains(probe) {
                            self.messages.append(ChatMessage(role: .assistant,
                                                            content: "✅ \(msg)",
                                                            isSpotlight: self.currentGenerationIsSpotlight))
                        }
                    }
                    self.streamingMsgId = nil  // Always reset at turn end

                    // Hand the finished answer to the phone relay when it is
                    // running. The streamed bubble is the real text when there
                    // was streaming; `msg` is empty in that case.
                    if ClipboardChatRelay.shared.isRunning {
                        let answer = msg.isEmpty
                            ? (self.messages.last?.content ?? "")
                            : msg
                        ClipboardChatRelay.shared.send(answer)
                        // The relay only moves when the user pastes and
                        // copies, so the run is genuinely blocked on them.
                        AgentActivityCenter.shared.set(.waitingUser)
                    } else {
                        // .done also fires when the loop STOPS to ask
                        // something. finish() knows which of the two this is.
                        AgentActivityCenter.shared.finish()
                    }

                case .error(let err):
                    self.isGenerating = false
                    AgentActivityCenter.shared.set(.error(String(err.prefix(80))))
                    self.addSystemMessage("❌ Agent error: \(err)")
                    if ClipboardChatRelay.shared.isRunning {
                        ClipboardChatRelay.shared.send("❌ \(err)")
                    }
                }
            }
        }

        // Layer 1 council -> Layer 2 execution agent -> Layer 3 escalation.
        // Returns false when it can't run (e.g. no JGEN model loaded), in
        // which case we fall through to the normal loop below.
        if useLayered,
           await LayeredRunOrchestrator.run(question: fullInstruction, app: self, onProgress: handler) {
            await MainActor.run { self.isGenerating = false }
            return
        }

        await AgentLoop.shared.run(
            instruction: fullInstruction,
            contextFile: context,
            contextFileName: contextFile?.lastPathComponent,
            workspaceURL: snap_workspace,
            modelStatus: snap_status,
            activeModel: snap_model,
            cortex: cortex,
            selfFixMode: snap_selfFix,
            operationMode: snap_operationMode,
            memoryLayer: sessions.activeSession?.activeLayer ?? .l2,
            chatSessionId: vxChatSessionId,
            previousMessages: previousMessages,
            onProgress: handler
        )

        await MainActor.run { self.isGenerating = false }
    }

    // MARK: - Single pass (original behavior)

    // MARK: - Single pass (streaming)
    // Streams tokens directly into the chat bubble in real-time.
    // Tracks tok/s and emits process log entries.

    private func runSinglePass(instruction: String,
                               images: [AttachedImage] = [],
                               files: [URL] = []) async {
        let context = selectedFileContent.isEmpty ? nil : selectedFileContent
        let contextFile = selectedFile

        let snap_status = modelStatus

        // Build prompt (same as AgentEngine)
        let fileSection = context.map { content in
            let name = contextFile?.lastPathComponent ?? "file"
            return "FILE: \(name)\n```\n\(content.prefix(8000))\n```\n\n"
        } ?? ""

        let prompt = """
        You are Verantyx, an expert AI coding assistant running on Apple Silicon.

        \(fileSection)USER: \(instruction)

        ASSISTANT:
        """

        // Reset streaming state
        streamingText = ""
        tokensPerSecond = 0
        var tokenCount = 0
        let startTime = Date()
        var lastPerfLog = Date()

        logProcess("inference start [", kind: .system)
        logProcess("prompt \(prompt.count) chars", kind: .system)

        // Build the stream based on active model — use live settings
        switch snap_status {

        // ── Ollama path (unchanged) ─────────────────────────────────────────
        case .ollamaReady(let model):
            logProcess("Ollama/\(model)  temp=\(temperature)  maxTok=\(maxTokensOllama)", kind: .system)
            let msgId = UUID()
            messages.append(ChatMessage(id: msgId, role: .assistant, content: ""))
            let simpleMessages: [(role: String, content: String)] = [(role: "user", content: prompt)]
            let stream = OllamaClient.shared.streamGenerate(
                model: model,
                messages: simpleMessages,
                maxTokens: maxTokensOllama,
                temperature: temperature
            )
            do {
                // トークンをバッファして ~25fps (40ms) で UI を更新—※messagesの @Published 発火回数を 1/5 に削減
                var tokenBuffer = ""
                var lastUIFlush = Date.distantPast
                for try await event in stream {
                    guard case .token(let token) = event else { continue }
                    tokenCount += 1; totalTokensGenerated += 1
                    tokenBuffer += token
                    let now = Date()
                    let elapsed = now.timeIntervalSince(startTime)
                    // 40ms ごとにバッチフラッシュ（ポーリング連続で同一スレッドなので Date() で OK）
                    if now.timeIntervalSince(lastUIFlush) >= 0.04 {
                        if let idx = self.messages.firstIndex(where: { $0.id == msgId }) {
                            self.messages[idx].content += tokenBuffer
                        }
                        if elapsed > 0.1 { tokensPerSecond = Double(tokenCount) / elapsed }
                        tokenBuffer = ""
                        lastUIFlush = now
                    }
                    if now.timeIntervalSince(lastPerfLog) > 2 {
                        logProcess(String(format: "%.1f tok/s  │  %d tokens",
                                         Double(tokenCount)/max(elapsed,0.001), tokenCount), kind: .perf)
                        lastPerfLog = now
                    }
                }
                // 末尾バッファをフラッシュ
                if !tokenBuffer.isEmpty,
                   let idx = self.messages.firstIndex(where: { $0.id == msgId }) {
                    self.messages[idx].content += tokenBuffer
                }
            } catch { logProcess("stream error: \(error.localizedDescription)", kind: .system) }

            let elapsed1 = Date().timeIntervalSince(startTime)
            inferenceMs = Int(elapsed1 * 1000); tokensPerSecond = Double(tokenCount)/max(elapsed1,0.001)
            logProcess(String(format: "done  %.1f tok/s  │  %d tok  │  %.1fs",
                              tokensPerSecond, tokenCount, elapsed1), kind: .perf)
            let finalContent1 = messages.first(where: { $0.id == msgId })?.content ?? ""
            if agentLoopEnabled {
                let (toolCalls, _) = AgentToolParser.parse(from: finalContent1)
                let executor = AgentToolExecutor()
                for tool in toolCalls {
                    logProcess("\(tool)", kind: .tool)
                    let result = await executor.execute(tool, workspaceURL: workspaceURL)
                    if case .setWorkspace(let path) = tool {
                        let url = URL(fileURLWithPath: path)
                        workspaceURL = url; terminal.workingDirectory = url; refreshFiles()
                    }
                    addSystemMessage(result)
                }
            }

        // ── MLX direct in-process (new) ─────────────────────────────────────
        case .mlxReady:
            let m = activeMlxModel.components(separatedBy: "/").last ?? activeMlxModel
            logProcess("MLX/\(m) (direct)  temp=\(temperature)  maxTok=\(maxTokensMLX)", kind: .system)
            let msgId = UUID()
            messages.append(ChatMessage(id: msgId, role: .assistant, content: ""))
            // Nonisolated counter captured by ref via class box
            let counter = Counter()

            do {
                // MLX: nonisolated バッファ + 40ms ゲートで MainActor dispatch 回数を削減
                // 毎トークンに Task{@MainActor} を作るのは 40tok/s で 40 Tasks/s が生まれ非効率
                final class TokenBatch: @unchecked Sendable {
                    var buffer = ""
                    var lastFlush = Date.distantPast
                    let lock = NSLock()
                }
                let batch = TokenBatch()

                try await MLXRunner.shared.streamGenerateTokens(
                    prompt: prompt,
                    maxTokens: maxTokensMLX,
                    temperature: temperature,
                    onToken: { @Sendable [weak self] piece in
                        guard let self else { return }
                        counter.increment()
                        batch.lock.lock()
                        batch.buffer += piece
                        let shouldFlush = Date().timeIntervalSince(batch.lastFlush) >= 0.04
                        if shouldFlush { batch.lastFlush = Date() }
                        let flushed = shouldFlush ? batch.buffer : ""
                        if shouldFlush { batch.buffer = "" }
                        batch.lock.unlock()

                        guard shouldFlush, !flushed.isEmpty else { return }
                        Task { @MainActor in
                            if let idx = self.messages.firstIndex(where: { $0.id == msgId }) {
                                self.messages[idx].content += flushed
                            }
                            self.totalTokensGenerated += flushed.count  // approximate
                            let elapsed = Date().timeIntervalSince(startTime)
                            if elapsed > 0.1 {
                                self.tokensPerSecond = Double(counter.value) / elapsed
                            }
                        }
                    },
                    onFinish: { @Sendable [weak self] fullText in
                        guard let self else { return }
                        Task { @MainActor in
                            // 残バッファをフラッシュ
                            // NSLock は async コンテキストで使用不可 (Swift 6)。
                            // onFinish は全 onToken 完了後に呼ばれるため、
                            // この時点で concurrent アクセスは発生しない → lock 不要。
                            let remaining = batch.buffer
                            batch.buffer = ""
                            if !remaining.isEmpty,
                               let idx = self.messages.firstIndex(where: { $0.id == msgId }) {
                                self.messages[idx].content += remaining
                            }
                            let elapsed = Date().timeIntervalSince(startTime)
                            self.inferenceMs = Int(elapsed * 1000)
                            self.tokensPerSecond = Double(counter.value) / max(elapsed, 0.001)
                            self.logProcess(String(format: "done  %.1f tok/s  │  %d tok  │  %.1fs",
                                                   self.tokensPerSecond, counter.value, elapsed), kind: .perf)
                            // Agent tool parsing (same as Ollama path)
                            if self.agentLoopEnabled {
                                let (toolCalls, _) = AgentToolParser.parse(from: fullText)
                                let executor = AgentToolExecutor()
                                for tool in toolCalls {
                                    self.logProcess("\(tool)", kind: .tool)
                                    let result = await executor.execute(tool, workspaceURL: self.workspaceURL)
                                    if case .setWorkspace(let path) = tool {
                                        let url = URL(fileURLWithPath: path)
                                        self.workspaceURL = url
                                        self.terminal.workingDirectory = url
                                        self.refreshFiles()
                                    }
                                    self.addSystemMessage(result)
                                }
                            }
                            self.isGenerating = false
                        }
                    }
                )
            } catch {
                logProcess("MLX error: \(error.localizedDescription)", kind: .system)
                messages.append(ChatMessage(role: .assistant,
                    content: "⚠️ MLX error: \(error.localizedDescription)"))
            }

            isGenerating = false
            return

        default:
            messages.append(ChatMessage(role: .assistant,
                content: "⚠️ No model loaded. Load an MLX model or connect Ollama first."))
            isGenerating = false
            return
        }
        isGenerating = false
    }

    // MARK: - Process log helpers

    func logProcess(_ text: String, kind: ProcessLogEntry.Kind) {
        let entry = ProcessLogEntry(timestamp: Date(), text: text, kind: kind)
        Task { @MainActor in
            if self.logStore.entries.count > 500 { self.logStore.entries.removeFirst(100) }
            self.logStore.entries.append(entry)
        }
    }

    func clearProcessLog() { logStore.entries.removeAll() }

    func applyDiff() {
        guard let diff = pendingDiff else { return }
        do {
            try diff.modifiedContent.write(to: diff.fileURL, atomically: true, encoding: .utf8)
            selectedFileContent = diff.modifiedContent
            addSystemMessage("✅ Applied changes to \(diff.fileURL.lastPathComponent)")
        } catch {
            addSystemMessage("❌ Failed to write: \(error.localizedDescription)")
        }
        pendingDiff = nil
        showDiff = false
    }

    func skipDiff() {
        pendingDiff = nil
        showDiff = false
        addSystemMessage("⏭ Changes discarded.")
    }

    // MARK: - Human Mode: File write approval

    /// User tapped "承認" — resume the AgentLoop continuation so the write executes.
    func approveFileWrite() {
        guard let req = pendingFileApproval else { return }
        pendingFileApproval = nil
        req.approve()
        addSystemMessage(self.t("✅ Approved: \(req.displayFileName)", "✅ 承認しました: \(req.displayFileName)"))
    }

    /// User tapped "拒否" — resume the AgentLoop continuation with false, skip write.
    func rejectFileWrite() {
        guard let req = pendingFileApproval else { return }
        let name = req.displayFileName
        pendingFileApproval = nil
        req.reject()
        addSystemMessage(self.t("⏸ Rejected: \(name)", "⏸ 拒否しました: \(name)"))
    }

    // MARK: - Vera-α: save-preview approval

    /// Adds a request to the review queue. If nothing is currently being
    /// reviewed, it shows immediately (matches the old single-item
    /// behavior in .perTurn mode, where there's normally never more than
    /// one at a time); otherwise it waits behind whatever's already
    /// pending (this is what accumulates in .batched mode, where
    /// VeraMemoryBridge doesn't block the agent loop waiting for each
    /// one to be resolved).
    func enqueueVeraSave(_ req: VeraSaveApprovalRequest) {
        if pendingVeraSave == nil {
            pendingVeraSave = req
        } else {
            pendingVeraSaveQueue.append(req)
        }
    }

    /// User tapped "保存" — resume the continuation so VeraMemoryBridge
    /// actually calls `remember`/`propose_ai_facts`.
    func approveVeraSave() {
        guard let req = pendingVeraSave else { return }
        req.approve()
        advanceVeraSaveQueue()
        addSystemMessage(self.t("✅ Saved to Vera", "✅ Vera に保存しました"))

        // jgen × vera-a: the approved memory becomes a skill proposal,
        // applied where the JGEN harness actually recalls (SkillLibrary /
        // eternal memory). Reported in chat so the loop stays visible.
        if veraProposeSkillsToJGen,
           let proposal = VeraJGenSkillProposer.propose(
               userPrompt: req.userPrompt, aiResponse: req.aiResponse) {
            Task { [weak self] in
                await VeraJGenSkillProposer.apply(proposal)
                await MainActor.run {
                    guard let self else { return }
                    let limb = proposal.limbHint.map { " → \($0.rawValue)" } ?? ""
                    self.addSystemMessage(self.t(
                        "🧬 Vera proposed and applied skill '\(proposal.skill.name)' to JGEN\(limb)",
                        "🧬 Veraがスキル『\(proposal.skill.name)』を提案し、JGENに適用しました\(limb)"))
                }
            }
        }
    }

    /// User tapped "破棄" — resume with false, nothing is written to Vera.
    func rejectVeraSave() {
        guard let req = pendingVeraSave else { return }
        req.reject()
        advanceVeraSaveQueue()
        addSystemMessage(self.t("⏸ Discarded (not saved to Vera)", "⏸ 破棄しました（Vera には保存されません）"))

        // A rejection is supervision too: this prompt↔response pairing is
        // one the human judged NOT to belong together in memory — the
        // negative half of the projector's training signal.
        let prompt = req.userPrompt, response = req.aiResponse
        if !prompt.isEmpty, !response.isEmpty {
            Task {
                await EternalMemoryStore.shared.recordSupervisionPair(
                    kind: "rejected", textA: prompt, textB: response, core: nil)
            }
        }
    }

    private func advanceVeraSaveQueue() {
        pendingVeraSave = pendingVeraSaveQueue.isEmpty ? nil : pendingVeraSaveQueue.removeFirst()
    }



    // MARK: - Model actions

    /// Ollama に繋ぎにいく。
    ///
    /// - Parameter announce: 人が「繋いで」と言ったのか、起動時の下見か。
    ///
    /// **起動時に赤い ERROR と警告を出していたのはここだった。** Ollama は
    /// 11 ある backend の 1 つで、Claude / MLX / LM Studio / JGEN / BitNet
    /// だけを使う人にも `MainSplitView.onAppear` から無条件で走り、
    /// `localhost:11434` が居なければ `.error` と橙のトーストを出していた。
    /// `OllamaClient.listModels()` は接続拒否も空配列で返すので、
    /// **「入れていない」と「入れたがモデルが無い」が区別できない** —
    /// 区別できないものを断定して警告するのは、この製品の規律に反する。
    ///
    /// `announce == false`(起動時の下見)では:
    /// - 見つかれば拾う。ただし**まだ何も選ばれていないときだけ** —
    ///   人が選んだ backend を下見が塗り替えない。
    /// - 見つからなければ**何も言わず、`modelStatus` にも触らない。**
    ///   Ollama を使っていない人にとって、それは異常ではない。
    func connectOllama(announce: Bool = true) {
        // Wire CI/CD error → agent auto-reply loop (once)
        registerCIErrorHook()
        Task {
            if announce { modelStatus = .connecting }
            let models = await OllamaClient.shared.listModels()
            await MainActor.run {
                ollamaModels = models
                // 下見が上書きしてよいのは「まだ何も決まっていない」状態だけ。
                let mayTakeOver: Bool = {
                    if announce { return true }
                    switch modelStatus {
                    case .none, .connecting: return true
                    default:                 return false
                    }
                }()
                var chosen: String? = nil
                if models.contains(activeOllamaModel) {
                    chosen = activeOllamaModel
                } else if models.contains("gemma4:26b") {
                    activeOllamaModel = "gemma4:26b"
                    chosen = "gemma4:26b"
                } else if let first = models.first {
                    activeOllamaModel = first
                    chosen = first
                }
                if let m = chosen {
                    if mayTakeOver {
                        modelStatus = .ollamaReady(model: m)
                        if announce {
                            ToastManager.shared.show("\(m) ready",
                                                    icon: "checkmark.circle.fill", color: .green)
                        }
                    }
                } else if announce {
                    // 人が明示的に繋ぎにきたときだけ報せる。断定はしない —
                    // 空配列は「起動していない」と「モデルが無い」の両方で出る。
                    modelStatus = .error(t("Ollama did not answer",
                                          "Ollama から応答がありません"))
                    ToastManager.shared.show(
                        t("Ollama did not answer on \(ollamaEndpoint). It may not be running, or it may have no models yet.",
                          "\(ollamaEndpoint) の Ollama から応答がありません。起動していないか、モデルがまだ無い可能性があります。"),
                        icon: "exclamationmark.triangle.fill", color: .orange, duration: 4.5)
                }
                // announce == false でモデルが無い場合は、意図的に何もしない。
            }
        }
    }

    // MARK: - Model Eject (from LoadedModelPanel)

    /// Unload the currently active model, freeing all memory.
    ///
    /// • MLX: releases ModelContainer via MLXRunner.unloadModel() → deinit path frees GPU/ANE.
    /// • Ollama: sends DELETE /api/delete or keep-alive=0 to unload from RAM.
    ///
    /// After ejection, modelStatus → .none and a Deep→Front topology alias is persisted
    /// so the cognitive engine remembers which models have been used.
    func ejectModel() {
        let snap = modelStatus
        switch snap {
        case .mlxReady(let m), .mlxDownloading(let m):
            modelStatus = .none
            addSystemMessage(self.t("⏏ Ejected MLX Model: \(m)", "⏏ MLX モデルをリジェクト: \(m)"))
            Task.detached(priority: .userInitiated) {
                await MLXRunner.shared.unloadModel()
                // Write a topology alias into front/ for future reference
                Task.detached(priority: .utility) {
                    SessionMemoryArchiver.shared.writeDeepAlias(
                        modelId: m,
                        backend: "MLX",
                        kanjiTags: "[技:1.0] [速:0.8] [軽:0.7]"
                    )
                }
            }
        case .ollamaReady(let m):
            modelStatus = .none
            addSystemMessage(self.t("⏏ Ejected Ollama Model: \(m)", "⏏ Ollama モデルをリジェクト: \(m)"))
            let endpoint = ollamaEndpoint   // capture on MainActor before detaching
            Task.detached(priority: .userInitiated) {
                // Ollama: unload via generate API with keep_alive=0
                if let url = URL(string: "\(endpoint)/api/generate") {
                    var req = URLRequest(url: url)
                    req.httpMethod = "POST"
                    req.setValue("application/json", forHTTPHeaderField: "Content-Type")
                    req.httpBody = try? JSONSerialization.data(withJSONObject: [
                        "model": m, "keep_alive": 0
                    ])
                    _ = try? await URLSession.shared.data(for: req)
                }
                Task.detached(priority: .utility) {
                    SessionMemoryArchiver.shared.writeDeepAlias(
                        modelId: m,
                        backend: "Ollama",
                        kanjiTags: "[技:1.0] [通:0.8] [外:0.6]"
                    )
                }
            }
        case .jcrossReady(let m):
            modelStatus = .none
            addSystemMessage(self.t(
                "⏏ Ejected JGEN \(m) (purging Metal/CPU caches…)",
                "⏏ JGEN \(m) をリジェクト（Metal/CPU キャッシュ解放中…）"
            ))
            Task {
                await JCrossChatManager.shared.unload()
            }
        default:
            // Nothing loaded — just reset
            modelStatus = .none
        }
        // Toast notification
        ToastManager.shared.show(
            self.t("Model ejected", "モデルをリジェクトしました"),
            icon: "eject.fill",
            color: Theme.warn
        )
    }


    // MARK: - Helpers

    func addSystemMessage(_ text: String) {
        // Only show agent-loop tool events — NOT model load events (those use Toast)
        guard !text.hasPrefix("🟢") && !text.hasPrefix("🔌") else { return }
        messages.append(ChatMessage(role: .system, content: text))
    }

    // MARK: - Settings Persistence (Startup Restore)
    //
    // activeOllamaModel と activeMlxModel は宣言時のデフォルト値として
    // UserDefaults から直接復元される（上記の ={ UserDefaults... }() パターン）。
    // その他の設定も同様に didSet で自動保存されるが、
    // 起動時のデフォルト値が UserDefaults を参照していない項目をここで補完する。

    func loadPersistedSettings() {
        let ud = UserDefaults.standard

        // ── Workspace ──────────────────────────────────────────────────────
        let persistedEngineMode = ud.string(forKey: "vera_engine_mode")
            .flatMap(VeraEngineMode.init(rawValue:)) ?? .atelier
        if persistedEngineMode == .localLLM,
           let path = ud.string(forKey: "last_workspace_path") {
            let url = URL(fileURLWithPath: path)
            var isDir: ObjCBool = false
            if FileManager.default.fileExists(atPath: path, isDirectory: &isDir), isDir.boolValue {
                workspaceURL = url
                terminal.workingDirectory = url
                GatekeeperModeState.shared.configure(workspaceURL: url)
                refreshFiles()
                // ⚠️ L2.5インデックスの起動は VerantyxApp.onAppear (0.3秒後) で一元管理。
                // ここで呼ぶと onAppear 側と二重起動になり MainActor デッドロックが発生する。
            }

        }

        // A returning user lands back where they left off — that means the
        // mode they actually chose, not always Atelier. The stored mode is
        // read first to migrate removed values off disk (a build with the
        // old string still saved would otherwise fail to decode and
        // silently keep whatever the default happened to be, which is the
        // same bug in a quieter form), then restored if it names a mode
        // that still exists.
        //
        // Four names have gone through this: council and standalone
        // (removed earlier), vera_model and vera_bot (removed 2026-08-26).
        // The earlier two land here silently, same as before — but a user
        // who was actually IN Vera or Bot mode when this build replaced
        // theirs deserves to be told why their screen changed on launch,
        // not to just quietly wake up in Atelier. That is the toast below.
        let removedModeNames: Set<String> = ["council", "standalone", "vera_model", "vera_bot"]
        if let raw = ud.string(forKey: "vera_engine_mode"), removedModeNames.contains(raw) {
            ud.set(VeraEngineMode.atelier.rawValue, forKey: "vera_engine_mode")
            if raw == "vera_model" || raw == "vera_bot" {
                let name = raw == "vera_model" ? "Vera" : "Bot"
                ToastManager.shared.show(
                    "\(name) mode was removed — opening Atelier instead",
                    icon: "exclamationmark.triangle.fill", color: .orange, duration: 4)
            }
        }
        hasChosenEngineMode = ud.bool(forKey: "vera_engine_mode_chosen")
        if let raw = ud.string(forKey: "vera_engine_mode"),
           let restored = VeraEngineMode(rawValue: raw) {
            veraEngineMode = restored
        }
        // モードと同居できないタブ(前回の終了時点で持ち越されたもの)を、
        // ここで初めて分かった実際のモードに対して畳む。ShellLayoutState.
        // restore() 自身では出来ない — `shell` は AppState の他のプロパティが
        // まだ既定値のうちに作られるので、そこではまだこのモードを知らない。
        shell.pruneTabs(incompatibleWith: veraEngineMode)
        backfillGarmentProjectDates()
        if garmentProjects.contains(activeGarment) {
            activateGarmentProject(activeGarment)
        } else if let first = garmentProjects.first {
            activateGarmentProject(first)
        }

        // ── Anthropic ──────────────────────────────────────────────────────
        if let key = ud.string(forKey: "anthropic_api_key"), !key.isEmpty {
            anthropicApiKey = key                       // didSet → AnthropicClient.configure
        }
        if let model = ud.string(forKey: "anthropic_model"), !model.isEmpty {
            activeAnthropicModel = model
        }

        // ── Model config ───────────────────────────────────────────────────
        // temperature/maxTokens/systemPrompt 等は宣言時のデフォルトが UD を見ていない
        // ため、ここで上書きする（didSet による二重保存は無害）。
        if let t = ud.object(forKey: "model_temperature") as? Double { temperature = t }
        if let n = ud.object(forKey: "max_tokens_ollama") as? Int    { maxTokensOllama = n }
        if let n = ud.object(forKey: "max_tokens_mlx") as? Int       { maxTokensMLX = n }
        if let n = ud.object(forKey: "context_window_override") as? Int { contextWindowOverride = n }
        if let raw = ud.string(forKey: "vera_save_approval_mode"),
           let mode = VeraSaveApprovalMode(rawValue: raw) { veraSaveApprovalMode = mode }
        if let e = ud.string(forKey: "ollama_endpoint"), !e.isEmpty  { ollamaEndpoint = e }
        if let s = ud.string(forKey: "system_prompt"), !s.isEmpty    { systemPrompt = s }

        // ── Toggles ────────────────────────────────────────────────────────
        if let v = ud.object(forKey: "agent_loop_enabled") as? Bool  { agentLoopEnabled = v }
        if let v = ud.object(forKey: "streaming_enabled")  as? Bool  { streamingEnabled = v }
        if let v = ud.object(forKey: "tool_browser")       as? Bool  { toolBrowserEnabled = v }
        if let v = ud.object(forKey: "tool_web_search")    as? Bool  { toolWebSearchEnabled = v }
        if let v = ud.object(forKey: "tool_terminal")      as? Bool  { toolTerminalEnabled = v }
        if let v = ud.object(forKey: "tool_diff")          as? Bool  { toolDiffEnabled = v }
        if let v = ud.object(forKey: "tool_jcross")        as? Bool  { toolJCrossEnabled = v }
        if let v = ud.object(forKey: "gemma_semantic_masking") as? Bool { gemmaSemanticMaskingEnabled = v }

        // ── Modes ──────────────────────────────────────────────────────────
        if let raw = ud.string(forKey: "inference_mode"),
           let m = InferenceMode(rawValue: raw) { inferenceMode = m }
        if let raw = ud.string(forKey: "cloud_provider"),
           let p = CloudProvider(rawValue: raw) { cloudProvider = p }
        if let raw = ud.string(forKey: "operation_mode"),
           let o = OperationMode(rawValue: raw) {
            // Migrate users whose saved mode is .gatekeeper: it is no longer
            // offered in the mode Picker, and a SwiftUI Picker bound to a
            // selection with no matching tag renders blank and cannot be
            // changed — so restoring it verbatim would strand those users
            // with an unusable control.
            operationMode = (o == .gatekeeper) ? .automatic : o
        }

        // ── Notification ───────────────────────────────────────────────────
        if let v = ud.object(forKey: "notify_diff_apply") as? Bool { notifyOnDiffApply = v }
        if let v = ud.object(forKey: "notify_error")      as? Bool { notifyOnError = v }
    }

    // MARK: - CI/CD Auto-Reply Hook
    //
    // When CIValidationEngine detects a compile error after an AI-generated patch,
    // it broadcasts selfEvolutionCIError. We automatically feed the error digest
    // back to the agent as a new user message, so the agent self-corrects.

    func registerCIErrorHook() {
        NotificationCenter.default.addObserver(
            forName: .selfEvolutionCIError,
            object: nil,
            queue: .main
        ) { [weak self] notification in
            guard let self,
                  let digest = notification.userInfo?["digest"] as? String else { return }

            // Hop to MainActor for all @MainActor-isolated mutations.
            // sendMessage is a sync func that internally spawns a Task — no await needed.
            Task { @MainActor [weak self] in
                guard let self else { return }
                self.messages.append(ChatMessage(
                    role: .system,
                    content: "🔬 CI エラー検出 — AI が自動修正を試みます"
                ))
                self.sendMessage(with: digest)
            }
        }
    }

    /// Subscribe to the [RESTART_IDE] agent event.
    /// Call from VerantyxApp.onAppear once.
    func registerRestartHook() {
        NotificationCenter.default.addObserver(
            forName: .agentRequestsRestart,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            // Wrap in Task { @MainActor } so Swift 6 sees the mutation as actor-safe.
            Task { @MainActor [weak self] in
                self?.showRestartAlert = true
            }
        }
    }

    /// Apply pending patches then quit; rebuild.sh relaunches the app.
    func performRestart() {
        try? SelfEvolutionEngine.shared.applyAllPatches()
        guard let wsPath = cortexWorkspacePath ?? workspaceURL?.path else { return }
        let rebuildScript = wsPath + "/rebuild.sh"
        if FileManager.default.fileExists(atPath: rebuildScript) {
            Task.detached {
                let process = Process()
                process.executableURL = URL(fileURLWithPath: "/bin/zsh")
                process.arguments = ["-c", "sleep 0.5 && bash '\(rebuildScript)'"]
                try? process.run()
            }
        }
        NSApplication.shared.terminate(nil)
    }

    var isReady: Bool {
        switch modelStatus {
        case .ready, .ollamaReady, .mlxReady, .bitnetReady, .lmStudioReady: return true
        default: return false
        }
    }

    var statusLabel: String {
        switch modelStatus {
        case .none:                          return "No model"
        case .connecting:                    return "Connecting…"
        case .downloading(let p):            return "Downloading \(Int(p * 100))%"
        case .ready(let n):                  return n
        case .ollamaReady(let m):            return "Ollama: \(m.components(separatedBy: ":").first ?? m)"
        case .anthropicReady(let m, _):      return "Claude: \(m)"
        case .claudeAgentReady(let m):       return "Agent SDK: \(m)"
        case .mlxReady(let m):              return "MLX: \(m.components(separatedBy: "/").last ?? m)"
        case .mlxDownloading(let m):        return "⏬ \(m.components(separatedBy: "/").last ?? m)"
        case .bitnetReady(let m):           return "BitNet: \(m)"
        case .jcrossReady(let m):           return "JGEN: \(m)"
        case .lmStudioReady(let m):         return "LM Studio: \(m)"
        case .error(let e):                  return "Error: \(e)"
        }
    }

    var statusColor: Color {
        switch modelStatus {
        case .ready, .ollamaReady, .mlxReady, .anthropicReady, .bitnetReady, .jcrossReady,
             .lmStudioReady, .claudeAgentReady: return .green
        case .error:                           return .red
        case .downloading, .connecting,
             .mlxDownloading:                  return .orange
        case .none:                            return .gray
        }
    }


    // MARK: - Architecture template setup

    /// Builds a plan for `template` and queues it for approval. Runs the
    /// planner to completion *before* presenting the sheet, so any web lookup
    /// can't leave a spinner (or a verification puzzle) stuck behind a modal.
    func proposeSetup(template: ArchitectureTemplate, allowWeb: Bool = true) {
        Task { @MainActor in
            let machine = MachineProfile.current()
            let inventory = await ModelInventory.snapshot(app: self)
            let proposal = await TemplateSetupPlanner.shared.plan(
                template: template, machine: machine,
                inventory: inventory,
                hasAnthropicKey: !self.anthropicApiKey.isEmpty,
                allowWeb: allowWeb
            )
            self.pendingSetupProposal = proposal
        }
    }

    /// Applies an approved plan. Deliberately does *not* touch
    /// `activeOllamaModel`: the chat model and the execution model are
    /// different roles, and silently swapping the user's chat model is the
    /// most likely surprise here.
    func applySetupProposal(_ proposal: SetupProposal) {
        let store = CouncilSettingsStore.shared
        store.config = proposal.template.councilConfig
        store.templateId = proposal.template.id

        if let exec = proposal.assignment(.execution), exec.backend != .none {
            store.executionModel = exec.model == "—" ? "" : exec.model
        } else {
            store.executionModel = ""
        }
        // JGEN vector-bus / any template whose execution layer is JGEN:
        // keep Layer 2 on the same engine and skip AgentLoop.
        if let exec = proposal.assignment(.execution), exec.backend == .jgen {
            store.executionUseJGEN = true
        } else if proposal.template.id == "jgen-vector-bus" {
            store.executionUseJGEN = true
        } else if proposal.template.layers.contains(where: { $0.role == .execution && $0.backend == .jgen }) {
            store.executionUseJGEN = true
        } else {
            // Don't force-off: user may have toggled JGEN L2 independently.
        }
        if let esc = proposal.assignment(.escalation), esc.backend != .none, esc.model != "—" {
            store.config.escalationModel = esc.model
        } else {
            store.config.escalationModel = ""
            // Templates that disable L3 must not keep a stale escalate flag
            // from a previous "strongest" config sitting only in escalationModel.
            if proposal.template.layer(.escalation)?.enabled == false {
                store.config.escalateOnLowConfidence = false
            }
        }

        // Layer 1 runs on JGEN; load it if the plan named one that isn't
        // already active.
        if let core = proposal.assignment(.councilCore), core.backend == .jgen, core.model != "—" {
            let alreadyLoaded: Bool
            if case .jcrossReady(let m) = modelStatus { alreadyLoaded = (m == core.model) } else { alreadyLoaded = false }
            if !alreadyLoaded { loadJGenModel(core.model) }
        }

        pendingSetupProposal = nil
        let name = AppLanguage.shared.isJapanese ? proposal.template.nameJA : proposal.template.name
        addSystemMessage(t("🧩 Applied setup: \(name)", "🧩 構成を適用しました: \(name)"))
    }

    // MARK: - JGEN Actions

    /// Loads a converted `.jgen` model into `JCrossChatManager` and flips
    /// `modelStatus` to `.jcrossReady` so `AgentLoop.callModel` routes chat
    /// through the JGEN engine.
    ///
    /// Lives here rather than in `JGenSettingsSection` (where it used to be)
    /// because the model-selector bar above the chat input now loads JGEN
    /// models too -- two copies of this would let the bar and Settings show
    /// contradictory state. Both surfaces observe `jgenLoadingModel` /
    /// `jgenLoadError`.
    func loadJGenModel(_ name: String) {
        jgenLoadingModel = name
        jgenLoadError = nil
        Task {
            do {
                try await JCrossChatManager.shared.load(modelFileName: name)
                let device = await JCrossChatManager.shared.lastLoadDeviceLabel ?? "?"
                let reasonJA = await JCrossChatManager.shared.lastLoadReasonJA
                let reasonEN = await JCrossChatManager.shared.lastLoadReasonEN
                await MainActor.run {
                    self.jgenLoadingModel = nil
                    self.modelStatus = .jcrossReady(model: name)
                    let detail = self.t(
                        reasonEN ?? "device \(device)",
                        reasonJA ?? "デバイス \(device)"
                    )
                    self.addSystemMessage("🧠 JGEN \(name) loaded on \(device) — \(detail)")
                    if device == "CPU" {
                        ToastManager.shared.show(
                            self.t(
                                "JGEN on CPU (safe mode) — Metal skipped to protect WindowServer",
                                "JGEN は CPU（安全モード）— WindowServer 保護のため Metal を回避"
                            ),
                            icon: "thermometer.medium",
                            color: .orange,
                            duration: 5
                        )
                    } else if device == "Metal" {
                        ToastManager.shared.show(
                            self.t(
                                "JGEN loaded on Metal — GPU path active",
                                "JGEN を Metal でロード — GPU パス有効"
                            ),
                            icon: "bolt.fill",
                            color: .green,
                            duration: 4
                        )
                    }
                }
            } catch {
                await MainActor.run {
                    self.jgenLoadingModel = nil
                    self.jgenLoadError = error.localizedDescription
                }
            }
        }
    }

    /// Unload the in-process JGEN engine and purge GPU/CPU weight caches.
    func unloadJGenModel() {
        let name: String? = {
            if case .jcrossReady(let m) = modelStatus { return m }
            return nil
        }()
        Task {
            await JCrossChatManager.shared.unload()
            await MainActor.run {
                if case .jcrossReady = self.modelStatus {
                    self.modelStatus = .none
                }
                if let name {
                    self.addSystemMessage(self.t(
                        "⏏ Ejected JGEN \(name) (Metal/CPU caches purged)",
                        "⏏ JGEN \(name) をリジェクト（Metal/CPU キャッシュ解放）"
                    ))
                }
            }
        }
    }

    // MARK: - MLX Actions (Direct in-process — no HTTP server)

    func loadMLXModel(model: String? = nil) {
        let modelId = model ?? activeMlxModel
        modelStatus = .connecting
        mlxServerLogs.removeAll()

        Task {
            do {
                try await MLXRunner.shared.loadModel(id: modelId) { @Sendable log in
                    Task { @MainActor in
                        self.mlxServerLogs.append(log)
                        self.logProcess(log, kind: .system)
                    }
                }
                await MainActor.run {
                    self.modelStatus = .mlxReady(model: modelId)
                    self.activeMlxModel = modelId
                    ToastManager.shared.show(
                        "MLX: \(modelId.components(separatedBy: "/").last ?? modelId) ready 🚀",
                        icon: "cpu",
                        color: Theme.ok
                    )
                }
            } catch {
                await MainActor.run {
                    self.modelStatus = .error(error.localizedDescription)
                    ToastManager.shared.show(
                        "MLX error: \(error.localizedDescription)",
                        icon: "exclamationmark.triangle.fill",
                        color: .orange, duration: 5
                    )
                }
            }
        }
    }

    /// Legacy alias so old call sites keep compiling.
    @available(*, deprecated, renamed: "loadMLXModel")
    func startMLXServer(model: String? = nil) { loadMLXModel(model: model) }

    func downloadMLXModel(repoId: String) {
        modelStatus = .mlxDownloading(model: repoId)
        mlxServerLogs.removeAll()

        Task {
            do {
                try await MLXRunner.shared.downloadModel(repoId: repoId) { @Sendable log in
                    Task { @MainActor in
                        self.mlxServerLogs.append(log)
                    }
                }
                await MainActor.run {
                    ToastManager.shared.show(
                        "Downloaded: \(repoId.components(separatedBy: "/").last ?? repoId)",
                        icon: "checkmark.circle.fill",
                        color: .green, duration: 4
                    )
                    self.loadMLXModel(model: repoId)
                }
            } catch {
                await MainActor.run {
                    self.modelStatus = .error("Download failed: \(error.localizedDescription)")
                }
            }
        }
    }
}
