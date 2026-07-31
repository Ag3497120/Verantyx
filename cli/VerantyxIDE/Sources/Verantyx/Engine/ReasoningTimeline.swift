import Foundation
import SwiftUI

/// A running agent turn (especially a Council/L1-L4 run, which can
/// genuinely take 10+ minutes) looks like an opaque hang unless you can
/// see *why* it's taking that long. This turns the existing `LoopEvent`
/// stream — already flowing through `AppState`'s central handler for
/// every agent path — into a semantic, timestamped timeline: not "GPU is
/// busy", but "3 candidates generated, round 2 rejected, robustness
/// check running". Reuses events that already exist; adds no new
/// instrumentation cost beyond a handful of `§TL:` markers in
/// `CouncilOrchestrator.deliberate()` for the steps that would otherwise
/// be a single silent black box (the vector-space deliberation rounds
/// themselves have no other observable step).
enum TimelineCategory: String, Sendable {
    case task, memory, candidates, council, reject, verify, accept
    case app, search, uiRecognition, skillSaved, done, note

    var icon: String {
        switch self {
        case .task: return "flag.checkered"
        case .memory: return "brain"
        case .candidates: return "list.bullet.rectangle"
        case .council: return "arrow.triangle.branch"
        case .reject: return "xmark.circle"
        case .verify: return "checkmark.shield"
        case .accept: return "checkmark.circle.fill"
        case .app: return "macwindow"
        case .search: return "magnifyingglass"
        case .uiRecognition: return "hand.point.up.left"
        case .skillSaved: return "tray.and.arrow.down"
        case .done: return "flag.checkered.2.crossed"
        case .note: return "ellipsis.circle"
        }
    }

    var color: Color {
        switch self {
        case .task: return .primary
        case .memory: return .purple
        case .candidates: return .blue
        case .council: return .indigo
        case .reject: return .red
        case .verify: return .orange
        case .accept: return .green
        case .app: return .teal
        case .search: return .cyan
        case .uiRecognition: return .pink
        case .skillSaved: return .mint
        case .done: return .green
        case .note: return .secondary
        }
    }
}

struct TimelineEvent: Identifiable, Sendable {
    let id = UUID()
    let elapsed: TimeInterval
    let category: TimelineCategory
    let label: String

    var elapsedLabel: String {
        let total = max(0, Int(elapsed))
        return String(format: "%02d:%02d", total / 60, total % 60)
    }
}

@MainActor
final class ReasoningTimelineStore: ObservableObject {
    static let shared = ReasoningTimelineStore()

    @Published private(set) var events: [TimelineEvent] = []
    @Published private(set) var isActive = false
    private var sessionStart: Date?

    private init() {}

    func beginSession() {
        events = []
        sessionStart = Date()
        isActive = true
    }

    func endSession() {
        isActive = false
    }

    func record(_ category: TimelineCategory, _ label: String) {
        let start = sessionStart ?? Date()
        events.append(TimelineEvent(elapsed: Date().timeIntervalSince(start), category: category, label: label))
    }

    /// Feed every `LoopEvent` from the same central handler that already
    /// drives the chat transcript. Silently ignores events that don't map
    /// to a meaningful timeline entry (streaming tokens, thinking markers).
    func ingest(_ event: LoopEvent) {
        guard isActive else { return }
        switch event {
        case .start:
            record(.task, AppLanguage.shared.t("Task received", "タスクを受理"))
        case .systemLog(let text):
            if let parsed = Self.parseMarker(text) {
                record(parsed.category, parsed.label)
            }
        case .toolCall(let call):
            if let (category, label) = Self.classify(call.tool) {
                record(category, label)
            }
        case .done:
            record(.done, AppLanguage.shared.t("Done", "完了"))
        default:
            break
        }
    }

    /// `CouncilOrchestrator.deliberate()` emits `.systemLog("§TL:category:label")`
    /// for milestones that have no corresponding tool call (there's no
    /// "tool" for "round 2 of vector deliberation rejected" -- it's a
    /// step entirely internal to the council loop).
    private static func parseMarker(_ text: String) -> (category: TimelineCategory, label: String)? {
        guard text.hasPrefix("§TL:") else { return nil }
        let rest = text.dropFirst(4)
        guard let sep = rest.firstIndex(of: ":") else { return nil }
        let rawCategory = String(rest[rest.startIndex..<sep])
        let label = String(rest[rest.index(after: sep)...])
        return (TimelineCategory(rawValue: rawCategory) ?? .note, label)
    }

    private static func classify(_ tool: AgentTool) -> (TimelineCategory, String)? {
        switch tool {
        case .openApp(let name):
            return (.app, AppLanguage.shared.t("Open \(name)", "\(name)を開く"))
        case .desktopSnapshot, .visionSnapshot:
            return (.uiRecognition, AppLanguage.shared.t("Analyze screen state", "画面状態を解析"))
        case .desktopAct(let action), .visionAct(let action), .axAct(let action):
            return (.uiRecognition, AppLanguage.shared.t("Operate UI: \(action.prefix(40))", "UI操作: \(action.prefix(40))"))
        case .search(let q):
            return (.search, AppLanguage.shared.t("Search: \(q)", "検索: \(q)"))
        case .searchMulti(let q):
            return (.search, AppLanguage.shared.t("Search (multi-source): \(q)", "検索(複数ソース): \(q)"))
        case .browse(let url), .visionBrowse(let url), .openSafari(let url), .openChrome(let url):
            return (.search, AppLanguage.shared.t("Verify source: \(url.prefix(50))", "情報源を検証: \(url.prefix(50))"))
        case .registerUIElement(let app, let element, _, _):
            return (.uiRecognition, AppLanguage.shared.t("Recognize \"\(element)\" in \(app)", "\(app)の「\(element)」を認識"))
        case .jcrossStore, .forgeSkill:
            return (.skillSaved, AppLanguage.shared.t("Save operation as reusable skill", "操作スキルを保存"))
        default:
            return nil
        }
    }
}
