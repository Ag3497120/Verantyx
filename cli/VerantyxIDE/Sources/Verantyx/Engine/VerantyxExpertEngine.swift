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

    func sendQuery(_ query: String) async {
        messages.append(ChatMessage(role: .user, content: query))
        isGenerating = true
        defer { isGenerating = false }

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
