import Foundation
import SwiftUI

/// 服飾の解析に**どの AI を使うか**を選ぶところ。
///
/// ここが LLM のパイプの行き先です。ローカルで動かしているモデルも、
/// 鍵を入れてあるクラウドのモデルも、同じ一覧に並びます。ただし
/// **選んだ AI が台帳に書ける口はひとつしかありません** —
/// `garment_propose`(提案)だけです。観測欄にも推論欄にも届きません。
/// 提案が事実になる唯一の道は、人が名前を書いて採用することです。
///
/// この境目はUIの飾りではなく、扉の側で閉じています。モデルを
/// 増やしても、別のプロバイダを足しても、事実の欄には届きません。
@MainActor
final class AtelierAnalyst: ObservableObject {

    // AtelierView used to own this as a private @StateObject, once per
    // instance. It needed to be one object once the composer grew its own
    // "Analysis AI" control (UnifiedComposerView, in Atelier mode) — a
    // second AtelierAnalyst would just be a second pick that could disagree
    // with the rail's, which is exactly the "compete instead of agree"
    // shape the owner asked not to build. `pick` was already persisted to
    // UserDefaults so two instances mostly *looked* consistent after a
    // fresh read, but `busy` / `lastRun` / the fetched model lists were
    // not, so a refresh in one place never showed in the other. One
    // instance, like `AtelierIntake.shared`.
    static let shared = AtelierAnalyst()

    /// 解析に使う相手。`vera` は**モデルを呼ばない**選択で、
    /// 構造(立体十字)と台帳だけで、次に何を見るべきかを出します。
    enum Pick: Equatable {
        case vera
        case ollama(String)
        case jgen(String)
        case lmStudio(String)
        case cloud(CloudProvider, String)

        var label: String {
            switch self {
            case .vera: return "Vera (構造のみ・モデルを呼ばない)"
            case .ollama(let m): return "Ollama: \(m)"
            case .jgen(let m): return "JGEN: \(m)"
            case .lmStudio(let m): return "LM Studio: \(m)"
            case .cloud(let p, let m): return "\(p.rawValue): \(m)"
            }
        }

        var stored: String {
            switch self {
            case .vera: return "vera"
            case .ollama(let m): return "ollama:\(m)"
            case .jgen(let m): return "jgen:\(m)"
            case .lmStudio(let m): return "lmstudio:\(m)"
            case .cloud(let p, let m): return "cloud:\(p.rawValue)|\(m)"
            }
        }

        /// 出典に書く名前。**誰が言ったか**が消えると、提案は
        /// 出所の無い事実に化けます。
        var sourceName: String {
            switch self {
            case .vera: return "vera-structure"
            case .ollama(let m): return "ollama:\(m)"
            case .jgen(let m): return "jgen:\(m)"
            case .lmStudio(let m): return "lmstudio:\(m)"
            case .cloud(let p, let m): return "cloud:\(p.rawValue)/\(m)"
            }
        }

        static func from(_ s: String) -> Pick {
            if s.hasPrefix("ollama:") { return .ollama(String(s.dropFirst(7))) }
            if s.hasPrefix("jgen:") { return .jgen(String(s.dropFirst(5))) }
            if s.hasPrefix("lmstudio:") {
                return .lmStudio(String(s.dropFirst(9)))
            }
            if s.hasPrefix("cloud:") {
                let rest = String(s.dropFirst(6)).split(separator: "|",
                                                        maxSplits: 1)
                if rest.count == 2,
                   let p = CloudProvider(rawValue: String(rest[0])) {
                    return .cloud(p, String(rest[1]))
                }
            }
            return .vera
        }
    }

    private static let key = "atelier_analysis_pick"

    @Published var pick: Pick {
        didSet { UserDefaults.standard.set(pick.stored, forKey: Self.key) }
    }
    @Published var ollamaModels: [String] = []
    @Published var jgenModels: [String] = []
    /// LM Studio が今出しているもの。**表を持たない** — 何が入って
    /// いるかは向こうが知っている。別の機体を指していても同じ。
    @Published var lmStudioModels: [String] = []
    @Published var lmStudioEndpoint = ""
    @Published var cloudModels: [CloudProvider: [String]] = [:]
    @Published var busy = false
    @Published var lastRun = ""
    /// 直近の解析が置いた提案の数。0 は失敗ではなく「何も言わなかった」。
    @Published var lastProposals = 0

    init() {
        pick = Pick.from(
            UserDefaults.standard.string(forKey: Self.key) ?? "vera")
    }

    /// 何が使えるかを**訊いて**並べる。表を持たないのは、モデルが
    /// 増えるたびにアプリが間違いになるからです。
    func refresh(app: AppState) async {
        ollamaModels = app.ollamaModels.sorted()
        // 走らせられないもの(骨格が非対応、トークナイザが語彙だけ)は
        // 語彙としては変換できても前向き計算ができない。並べて選ばせてから
        // 落とすのが一番たちが悪いので、ここで落とす。実地で踏んだ:
        // 骨格だけ見ていて noRealTokenizer で落ちた。
        let conv = JGenConverter.shared
        jgenModels = conv.convertedModels
            .filter { conv.canRunForward($0) }.sorted()

        lmStudioModels = await LMStudioClient.shared.listModels()
        lmStudioEndpoint = app.lmStudioEndpoint

        var out: [CloudProvider: [String]] = [:]
        for p in CloudProvider.allCases
        where await CloudAPIClient.shared.hasAPIKey(for: p) {
            let ids = await CloudAPIClient.shared.listModels(for: p)
            // 空は「訊けなかった」であって「無い」ではない。既定値を残す。
            out[p] = ids.isEmpty ? [p.spec.fallbackModel] : ids
        }
        cloudModels = out
        dropStalePick()
    }

    /// 前に選んだ相手が、今も選べるか。走らせられないと判った
    /// モデルや、鍵を外したプロバイダを指したまま残っていると、
    /// 押した瞬間に落ちる。**選択は在庫に従う** — 消えていたら
    /// 構造だけの道に戻し、黙って戻さずに理由を出す。
    private func dropStalePick() {
        let alive: Bool
        switch pick {
        case .vera: alive = true
        case .ollama(let m): alive = ollamaModels.contains(m)
        case .jgen(let m): alive = jgenModels.contains(m)
        case .lmStudio(let m): alive = lmStudioModels.contains(m)
        case .cloud(let p, let m): alive = (cloudModels[p] ?? []).contains(m)
        }
        guard !alive else { return }
        let gone = pick.label
        pick = .vera
        lastRun = "「\(gone)」は今は選べないので、構造のみに戻しました。"
    }

    // MARK: - 解析

    /// 台帳の**空いている側面**について、選んだ AI に心当たりを訊きます。
    /// 返ってきたものは全部 `garment_propose` に入ります。
    ///
    /// 渡すのは既に台帳にあることと、空いている側面の名前だけです。
    /// 「これは何だと思うか」ではなく「どこを見ればいいか」を訊くのが
    /// この画面の仕事なので、値を言ってきても提案の欄に留まります。
    func analyze(model m: AtelierModel, app: AppState) async {
        busy = true
        defer { busy = false }
        lastProposals = 0

        let open = m.states.filter { $0.value.state == "UNKNOWN_NOT_OBSERVED" }
            .keys.sorted()
        guard !open.isEmpty else {
            lastRun = "空いている側面がありません。"
            return
        }

        if case .vera = pick {
            // モデルを呼ばない道。構造が持っている「次に何を見るか」を
            // そのまま出すだけで、値は一切作りません。
            lastRun = "Vera: \(open.count) 件の空欄に、次に見る場所が出ています"
                + "(値は作りません)。"
            return
        }

        let known = m.states.filter { $0.value.state != "UNKNOWN_NOT_OBSERVED" }
            .map { "\($0.key) = \($0.value.value)" }.joined(separator: "\n")
        // こちらの文面はまだ測っていない(絵を見ない経路)。
        // 測った文面と同じ顔をさせない。
        let prompt = AtelierPrompts.askOpenAspects(known: known,
                                                   open: open).text

        var raw: String?
        switch pick {
        case .vera:
            return
        case .ollama(let name):
            raw = await OllamaClient.shared.generate(
                model: name, prompt: prompt, maxTokens: 1200)
        case .jgen(let name):
            // JGEN は積み替えが要る。既に載っていれば載せ直さない。
            let mgr = JCrossChatManager.shared
            if await mgr.loadedModelName != name {
                do { try await mgr.load(modelFileName: name) }
                catch { lastRun = "JGEN を載せられませんでした: \(error)"; return }
            }
            raw = try? await mgr.generate(
                conversation: [("user", prompt)], maxTokens: 1200,
                keepThinking: false)
        case .lmStudio(let name):
            raw = await LMStudioClient.shared.generateConversation(
                model: name, messages: [("user", prompt)],
                maxTokens: 1200, temperature: 0.15)
        case .cloud(let p, let name):
            let r = await CloudAPIClient.shared.send(
                systemPrompt: "服飾解析。JSON 配列のみを返す。",
                userMessage: prompt, provider: p, modelOverride: name)
            if case .success(let text) = r { raw = text }
            if case .failure(let e) = r { lastRun = "失敗: \(e)" }
        }

        guard let text = raw, !text.isEmpty else {
            if lastRun.isEmpty { lastRun = "モデルが答えませんでした。" }
            return
        }
        let items = Self.parse(text)
        guard !items.isEmpty else {
            lastRun = "解釈できる提案がありませんでした(0 件)。"
            return
        }

        for it in items {
            await m.add(part: it.part, aspect: it.aspect, kind: "proposal",
                        value: it.value, source: pick.sourceName,
                        note: it.why)
        }
        lastProposals = items.count
        lastRun = "\(items.count) 件を**提案として**置きました。"
            + "採用するまで設計図には入りません。"
    }

    struct Item { let part: String; let aspect: String
                  let value: String; let why: String }

    /// モデルは JSON の前後に文章を付けます。壊れていたら**捨てる** —
    /// 直して読むと、モデルが言っていないものを置くことになります。
    static func parse(_ text: String) -> [Item] {
        guard let s = text.firstIndex(of: "["),
              let e = text.lastIndex(of: "]"), s < e else { return [] }
        let slice = String(text[s...e])
        guard let d = slice.data(using: .utf8),
              let arr = (try? JSONSerialization.jsonObject(with: d))
                as? [[String: Any]] else { return [] }
        return arr.compactMap { o in
            guard let p = o["part"] as? String, !p.isEmpty,
                  let a = o["aspect"] as? String, !a.isEmpty,
                  let v = o["value"] as? String, !v.isEmpty else { return nil }
            return Item(part: p, aspect: a, value: v,
                        why: (o["why"] as? String) ?? "")
        }
    }
}
