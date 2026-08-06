import Foundation
import SwiftUI

/// VerantyxExpertEngine — the in-app settings support bot.
///
/// This used to be a local language model (`verantyx-gemma:latest`) holding a
/// system prompt that told it "Do NOT hallucinate commands" and a mapping
/// table with exactly one row in it. Those two facts cannot both be honoured:
/// asked about any of the other settings, a model with nothing to look up
/// produces the most plausible-looking `verantyx ide config set ...` line it
/// can, and a user who follows a command that does not exist loses more time
/// than a refusal would ever have cost them.
///
/// So the bot no longer generates. It queries Vera's settings registry over
/// MCP and reports what comes back, including the refusals:
///
///   ANSWER              the exact Settings tab and field
///   UNKNOWN_AMBIGUOUS   several settings match — offer them, pick none
///   UNKNOWN_NO_SETTING  no such setting exists — say that
///   UNKNOWN_NO_CLI      the setting is real but GUI-only, so no command
///
/// The registry is checked against the Swift sources by
/// `verify_against_source()`, so an answer here names a screen that exists.
/// Nothing in this file calls a language model.
@MainActor
final class VerantyxExpertEngine: ObservableObject {
    public static let shared = VerantyxExpertEngine()

    @Published var messages: [ChatMessage] = []
    @Published var isGenerating = false

    /// The MCP server carrying Vera's tools. Registered by MCPEngine at
    /// launch; if it is unreachable the bot says so rather than falling back
    /// to guessing, because a silent fallback to a model is exactly the
    /// behaviour this rewrite removes.
    private let veraServer = "vera-memory"

    private init() {
        messages.append(ChatMessage(
            role: .assistant,
            content: AppLanguage.shared.t(
                "Verantyx settings support. Ask where a setting lives — "
                + "\"how do I change the Ollama model\". Answers come from the "
                + "verified settings registry, so if something does not exist "
                + "I will say so instead of inventing it.",
                "Verantyx 設定サポートです。「Ollama のモデルはどこで変えますか」の"
                + "ように聞いてください。検証済みの設定レジストリから答えるので、"
                + "存在しないものは捏造せずに「ありません」とお答えします。")))
    }

    /// Steps of the recipe currently being walked, if any. The chat text says
    /// what to do; these drive the buttons that do it.
    @Published var activeRecipe: RecipeDTO? = nil

    func sendQuery(_ query: String) async {
        messages.append(ChatMessage(role: .user, content: query))
        isGenerating = true
        defer { isGenerating = false }

        // Goals first. Someone asking "how do I build my own AI" does not know
        // the thing they want is called `inference_mode`, so a lookup keyed on
        // setting names cannot reach them — it would refuse a question the app
        // has a complete answer for.
        if let recipe = await matchGoal(query) {
            activeRecipe = recipe
            messages.append(ChatMessage(role: .assistant,
                                        content: formatRecipe(recipe)))
            return
        }

        let raw = await MCPEngine.shared.callTool(
            serverName: veraServer, toolName: "settings_lookup",
            arguments: ["question": query])

        guard let data = raw.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let verdict = obj["verdict"] as? String else {
            messages.append(ChatMessage(role: .assistant, content: AppLanguage.shared.t(
                "The settings registry did not answer. Check that the "
                + "`vera-memory` MCP server is connected in Settings › MCP.",
                "設定レジストリから応答がありませんでした。設定 › MCP で "
                + "`vera-memory` サーバーが接続されているか確認してください。")))
            return
        }

        switch verdict {
        case "ANSWER":
            messages.append(ChatMessage(role: .assistant, content: formatAnswer(obj)))
        case "UNKNOWN_AMBIGUOUS":
            messages.append(ChatMessage(role: .assistant,
                                        content: formatAmbiguous(obj)))
        default:
            messages.append(ChatMessage(role: .assistant,
                                        content: await formatNoSetting(query, obj)))
        }
    }

    // MARK: - Goals

    private func matchGoal(_ query: String) async -> RecipeDTO? {
        let raw = await MCPEngine.shared.callTool(
            serverName: veraServer, toolName: "goal_recipe",
            arguments: ["question": query])
        guard let data = raw.data(using: .utf8),
              let recipe = try? JSONDecoder().decode(RecipeDTO.self, from: data),
              recipe.verdict == "ANSWER", !recipe.steps.isEmpty else {
            // UNKNOWN_NO_RECIPE and friends fall through to settings_lookup
            // rather than being reported here: "no goal matches" is not an
            // answer to a question that was about one specific setting.
            return nil
        }
        return recipe
    }

    private func formatRecipe(_ r: RecipeDTO) -> String {
        let ja = AppLanguage.shared.isJapanese
        var lines = ["**\(ja ? r.title.ja : r.title.en)**", r.summary, ""]
        lines.append(ja
            ? "\(r.steps.count) 手順です。各手順の「開く」で画面へ移動でき、"
              + "「設定する」が出ているものはこの場で反映できます。"
            : "\(r.steps.count) steps. Open takes you to the screen; where "
              + "Apply is offered, it takes effect immediately.")
        return lines.joined(separator: "\n")
    }

    /// Take the user to the screen a step names.
    func openScreen(for step: RecipeStepDTO, app: AppState) {
        app.openSettings(tab: step.tab)
    }

    /// Set a step's value, when the app can do it correctly.
    ///
    /// Only routes through SettingsApplier, which mutates the property that
    /// owns each setting. Writing the UserDefaults key directly would leave
    /// the running app on the old value — the change would look done and not
    /// be, which is the failure this whole path exists to avoid.
    func applyStep(_ step: RecipeStepDTO, app: AppState) -> String {
        guard let value = step.value else {
            return AppLanguage.shared.t(
                "This step is a choice, not a fixed value — open the screen "
                + "and pick what fits.",
                "この手順は値が決まっているものではありません。画面を開いて選んでください。")
        }
        guard step.applicable else {
            return AppLanguage.shared.t(
                "This one you enter yourself — nothing else should type it "
                + "for you.",
                "これはご自身で入力してください。他のものが代わりに入力すべきではありません。")
        }
        switch SettingsApplier.apply(key: step.setting, value: value, app: app) {
        case .applied(let what):     return "✓ " + what
        case .notApplicable(let why): return why
        case .badValue(let v):
            return AppLanguage.shared.t("Cannot set '\(v)' here.",
                                        "'\(v)' はここでは設定できません。")
        }
    }

    // MARK: - Rendering the typed verdicts

    private func formatAnswer(_ obj: [String: Any]) -> String {
        let ja = AppLanguage.shared.isJapanese
        let titles = obj["title"] as? [String: String] ?? [:]
        let title = (ja ? titles["ja"] : titles["en"]) ?? (obj["key"] as? String ?? "")
        var lines: [String] = []

        lines.append("**\(title)**")
        if let what = obj["what"] as? String { lines.append(what) }
        if let whereAt = obj["where"] as? String {
            lines.append(ja ? "場所: \(whereAt)" : "Where: \(whereAt)")
        }
        if let values = obj["values"] as? [String], !values.isEmpty {
            lines.append((ja ? "選べる値: " : "Values: ")
                         + values.map { "`\($0)`" }.joined(separator: ", "))
        }
        // The honest half of the answer. Saying "GUI only" is what the
        // previous bot had no way to express, and so invented around.
        if let cli = obj["cli"] as? String {
            lines.append((ja ? "コマンド: " : "CLI: ") + "`\(cli)`")
        } else if obj["cli_verdict"] as? String == "UNKNOWN_NO_CLI" {
            lines.append(ja
                ? "コマンドはありません — この設定は GUI からのみ変更できます。"
                : "No CLI command — this setting is changed in the GUI only.")
        }
        if let note = obj["note"] as? String, !note.isEmpty { lines.append(note) }
        return lines.joined(separator: "\n")
    }

    private func formatAmbiguous(_ obj: [String: Any]) -> String {
        let ja = AppLanguage.shared.isJapanese
        let candidates = obj["candidates"] as? [[String: Any]] ?? []
        var lines = [ja
            ? "候補が \(candidates.count) 件あり、どれか一つに決められません。"
            : "\(candidates.count) settings match equally well — which did you mean?"]
        for c in candidates {
            let title = c["title"] as? String ?? ""
            let tab = c["tab"] as? String ?? ""
            lines.append("- **\(title)** — Settings › \(tab)")
        }
        return lines.joined(separator: "\n")
    }

    private func formatNoSetting(_ query: String,
                                 _ obj: [String: Any]) async -> String {
        let ja = AppLanguage.shared.isJapanese
        var lines = [ja
            ? "そのような設定はありません。"
            : "There is no such setting."]
        if let reason = obj["reason"] as? String { lines.append("(\(reason))") }

        // A dead end is worse than a wrong answer for a user who is stuck, so
        // offer near matches — clearly labelled as guesses at what was meant,
        // never as the answer.
        let raw = await MCPEngine.shared.callTool(
            serverName: veraServer, toolName: "settings_search",
            arguments: ["question": query, "limit": 5])
        if let data = raw.data(using: .utf8),
           let hits = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]],
           !hits.isEmpty {
            lines.append(ja ? "\n近い設定:" : "\nClosest settings:")
            for h in hits {
                let title = (ja ? h["title_ja"] : h["title"]) as? String ?? ""
                let tab = h["tab"] as? String ?? ""
                lines.append("- \(title) — Settings › \(tab)")
            }
        }
        return lines.joined(separator: "\n")
    }
}

// MARK: - Wire format for goal_recipe
//
// Mirrors `render()` in verantyx/task_recipes.py. Decoded rather than
// hand-parsed so a shape change fails at the boundary instead of quietly
// producing steps with blank screens attached.

struct RecipeDTO: Decodable {
    struct Title: Decodable { let en: String; let ja: String }
    let verdict: String
    let goal: String?
    let title: Title
    let summary: String
    let steps: [RecipeStepDTO]
}

struct RecipeStepDTO: Decodable, Identifiable {
    let n: Int
    let kind: String            // "setting" | "mode"
    let setting: String         // registry key, or "mode:<group>"
    let tab: String             // SettingsTab raw value
    let title: String
    let title_ja: String
    let why: String
    let value: String?          // nil = the user chooses
    let applicable: Bool

    var id: Int { n }

    /// Whether an Apply button should appear at all. Both halves have to
    /// agree: Vera says whether it is proper to set this for the user, and
    /// the applier says whether it can do it without leaving the app on a
    /// stale in-memory value.
    @MainActor
    var canApply: Bool {
        value != nil && applicable && SettingsApplier.canApply(key: setting)
    }
}
