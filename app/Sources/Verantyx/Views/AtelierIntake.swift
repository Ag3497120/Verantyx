import AVFoundation
import AppKit
import Foundation
import SwiftUI
import Vision

/// 素材を入れて、コマに割り、視覚モデルに読ませ、似たものを照らす。
///
/// 事前登録: `experiments/garment/PREREG4_PIPELINE.md`
///
/// **役割を混ぜない。** 割るのは計算(判断ではない)、読むのは視覚モデル
/// (出力は必ず提案)、照らすのは類似検索(返るのは「似ている」であって
/// 「由来」ではない)、記録するのは Vera(内容を読んで格上げしない —
/// どの扉から来たかで決まる)。
///
/// 描かせた絵は `mark_generated` で印が付き、その画像から観測はできない。
/// 一周回って自分の出力を証拠として読み直す経路を、扉の側で閉じてある。
@MainActor
final class AtelierIntake: ObservableObject {

    typealias SelectionInvalidator = @MainActor (_ revision: UInt64,
                                                  _ imagePath: String) -> Void

    // AtelierView used to own this as a private @StateObject. The shell's
    // composer (UnifiedComposerView) needs the SAME intake path for a photo
    // or clip attached in Atelier mode — not a second one that registers
    // material into a ledger AtelierView never reads from — so this is now
    // reachable from both.
    static let shared = AtelierIntake()

    private let selectionInvalidator: SelectionInvalidator

    init(selectionInvalidator: @escaping SelectionInvalidator = { revision, imagePath in
        AtelierChatRouter.consumeSelectionRevision(revision, imagePath: imagePath)
    }) {
        self.selectionInvalidator = selectionInvalidator
    }

    @Published var busy = false
    @Published var stage = ""
    @Published var log: [String] = []
    @Published var clips: [Clip] = []
    @Published var selectedClip: Clip?
    /// Whether the currently selected source is pending in the beginner
    /// composer.  `selectedClip` is also the factory's active image context,
    /// so clearing it immediately after Send used to either leave the chip
    /// visible or race the vision/factory task.  Keep the active source and
    /// the one-turn composer attachment as two explicit pieces of state.
    @Published private(set) var composerAttachmentVisible = false
    /// 同じパスを選び直した場合も、新しい解析要求として識別する番号。
    /// Clip.id は出典の同一性を保つため path のままにし、操作の同一性だけを
    /// この番号で分離する（同じ画像を独立した証拠として水増ししない）。
    @Published private(set) var selectionRevision: UInt64 = 0
    /// RegionPickerで人が確定した服領域。画像パスと対で保持し、別の画像へ
    /// 流用しない。自動の人物マスクはここへ入らない。
    @Published var confirmedClothingOutline: [String: Any]?
    @Published var confirmedOutlineImagePath: String?
    /// A confirmed region is valid for one user selection operation, not for
    /// every future selection of the same path.
    @Published private(set) var confirmedOutlineSelectionRevision: UInt64?
    @Published var matches: [Match] = []
    /// 一本の動画から取り出すコマ数。多ければ良いものではない —
    /// 同じ場面のコマを増やしても、独立した観測は増えない。
    @Published var frameCount = 8

    struct Clip: Identifiable, Hashable {
        var id: String { path }
        let path: String
        let mark: String
        let seconds: Double
        let sourcePath: String
    }

    struct Match: Identifiable {
        var id: String { path }
        let path: String
        let distance: Float
        let mark: String
    }

    struct AnalysisSelection {
        let clip: Clip
        let revision: UInt64
    }

    var analysisSelection: AnalysisSelection? {
        guard let selectedClip, selectionRevision > 0 else { return nil }
        return AnalysisSelection(clip: selectedClip,
                                 revision: selectionRevision)
    }

    /// The attachment shown/sent by the beginner composer.  Follow-up turns
    /// can still refer to `selectedClip` as project context without silently
    /// re-attaching the same file to every message.
    var composerSelectedClip: Clip? {
        composerAttachmentVisible ? selectedClip : nil
    }

    var hasComposerAttachment: Bool { composerSelectedClip != nil }

    func isCurrent(_ selection: AnalysisSelection) -> Bool {
        selectionRevision == selection.revision
            && selectedClip?.path == selection.clip.path
    }

    private func say(_ s: String) {
        log.append(s)
        if log.count > 200 { log.removeFirst(log.count - 200) }
    }

    private func call(_ tool: String,
                      _ args: [String: Any] = [:]) async -> [String: Any] {
        let raw = await MCPEngine.shared.callTool(
            serverName: "vera-memory", toolName: tool, arguments: args)
        guard let d = raw.data(using: .utf8),
              let o = (try? JSONSerialization.jsonObject(with: d))
                as? [String: Any] else {
            say("[engine] \(raw.prefix(160))")
            return [:]
        }
        return o
    }

    /// 素材を置く場所。**元ファイルはコピーしない** — 指すだけ。
    /// 抱え込むと、後から本物と写しの区別がつかなくなる。
    private var workRoot: URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory,
                                            in: .userDomainMask)[0]
            .appendingPathComponent("Verantyx/atelier/clips")
        try? FileManager.default.createDirectory(at: base,
                                                 withIntermediateDirectories: true)
        return base
    }

    /// 取り込み台帳から、前に割ったコマを読み直す。
    ///
    /// **エンジン側は覚えているのに画面が忘れる**、が起きていた。
    /// アプリを再起動すると素材が消えたように見え、三面の左が
    /// 「まだ素材を入れていません」になる — 入れたのに。
    func restore() async {
        let d = await call("intake_report")
        var out: [Clip] = []
        for src in (d["sources"] as? [[String: Any]] ?? []) {
            let path = src["path"] as? String ?? ""
            for c in (src["clips"] as? [[String: Any]] ?? []) {
                let cp = c["path"] as? String ?? ""
                // 手元から消えたコマは並べない。**開けないものを
                // 開けるように見せない。**
                guard FileManager.default.fileExists(atPath: cp) else {
                    continue
                }
                out.append(Clip(path: cp,
                                mark: c["mark"] as? String ?? "",
                                seconds: (c["seconds"] as? Double) ?? 0,
                                sourcePath: path))
            }
        }
        clips = out.sorted { $0.seconds < $1.seconds }
        if selectedClip == nil { selectedClip = clips.first }
        if !clips.isEmpty {
            say("前に割った \(clips.count) コマを読み直しました")
        }
    }

    // MARK: - 入れる

    func pickAndIngest() async {
        // Every macOS photo button enters through this picker. Drag-and-drop
        // already has a URL and joins the same pipeline at `ingest(_:)`.
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = false
        panel.allowedContentTypes = [.movie, .image]
        panel.message = "映像または画像を入れる"
        // `runModal()` blocks the main actor. Besides freezing progress UI, it
        // also breaks assistive/automation clients at the exact moment the
        // native picker opens. Keep the same single picker, but suspend this
        // task while AppKit owns the panel instead of blocking the app loop.
        let url: URL? = await withCheckedContinuation { continuation in
            panel.begin { response in
                continuation.resume(returning: response == .OK ? panel.url : nil)
            }
        }
        guard let url else { return }
        await ingest(url)
    }

    func ingest(_ url: URL) async {
        busy = true
        defer { busy = false; stage = "" }
        let isVideo = ["mp4", "mov", "m4v", "avi", "mkv"]
            .contains(url.pathExtension.lowercased())

        stage = "登録"
        let stamp = ISO8601DateFormatter().string(from: Date())
        let reg = await call("intake_register",
                             ["path": url.path,
                              "kind": isVideo ? "video" : "image",
                              "at": stamp])
        guard (reg["verdict"] as? String) == "ANSWER" else {
            say("素材を登録できませんでした")
            return
        }
        say("素材: \(url.lastPathComponent)")

        if isVideo {
            stage = "コマに割る"
            await split(url)
        } else {
            // 画像はそれ自体が一枚のコマ。割らないが、登録はする。
            _ = await call("intake_add_clip",
                           ["source_path": url.path, "clip_path": url.path,
                            "mark": "still", "seconds": 0])
            clips = [Clip(path: url.path, mark: "still", seconds: 0,
                          sourcePath: url.path)]
            say("画像1枚として登録")
        }
        publishSelection(clips.first)
    }

    /// Publish a user selection as an operation, not merely as a path value.
    ///
    /// `Clip.id` deliberately stays content/source based (`path`) so choosing
    /// the same file twice cannot manufacture two independent observations.
    /// `@Published` emits for an equal assignment, so a nil/yield detour is not
    /// needed and can leave the composer detached after the ledger succeeds.
    /// One main-actor transaction establishes the new operation identity,
    /// invalidates all old analysis, and only then publishes the selected clip.
    func publishSelection(_ clip: Clip?) {
        guard let clip else {
            selectedClip = nil
            composerAttachmentVisible = false
            confirmedClothingOutline = nil
            confirmedOutlineImagePath = nil
            confirmedOutlineSelectionRevision = nil
            matches = []
            return
        }
        selectionRevision &+= 1
        confirmedClothingOutline = nil
        confirmedOutlineImagePath = nil
        confirmedOutlineSelectionRevision = nil
        matches = []
        selectionInvalidator(selectionRevision, clip.path)
        selectedClip = clip
        composerAttachmentVisible = true
    }

    func rememberConfirmedOutline(_ outline: [String: Any], for imagePath: String) {
        guard selectedClip?.path == imagePath, selectionRevision > 0 else {
            return
        }
        confirmedClothingOutline = outline
        confirmedOutlineImagePath = imagePath
        confirmedOutlineSelectionRevision = selectionRevision
    }

    /// Detach only the one-turn composer attachment.  The active factory
    /// selection, intake ledger and source file remain intact, so an in-flight
    /// vision/factory run does not lose its image when the message is sent.
    func clearComposerSelection() {
        composerAttachmentVisible = false
    }

    /// 動画をコマに割る。**これは計算で、判断ではない。**
    private func split(_ url: URL) async {
        let asset = AVURLAsset(url: url)
        let gen = AVAssetImageGenerator(asset: asset)
        gen.appliesPreferredTrackTransform = true
        gen.requestedTimeToleranceBefore = .zero
        gen.requestedTimeToleranceAfter = .zero

        let duration: CMTime
        do { duration = try await asset.load(.duration) } catch {
            say("長さを読めませんでした: \(error.localizedDescription)")
            return
        }
        let total = CMTimeGetSeconds(duration)
        guard total > 0 else { say("長さが 0 です"); return }

        let n = max(1, min(frameCount, 60))
        let folder = workRoot.appendingPathComponent(
            url.deletingPathExtension().lastPathComponent)
        try? FileManager.default.createDirectory(at: folder,
                                                 withIntermediateDirectories: true)

        var out: [Clip] = []
        for i in 0..<n {
            let sec = total * (Double(i) + 0.5) / Double(n)
            let time = CMTime(seconds: sec, preferredTimescale: 600)
            guard let cg = try? await image(gen, at: time) else { continue }
            let mark = String(format: "t%06.2f", sec)
            let dest = folder.appendingPathComponent("\(mark).jpg")
            guard write(cg, to: dest) else { continue }
            _ = await call("intake_add_clip",
                           ["source_path": url.path, "clip_path": dest.path,
                            "mark": mark, "seconds": sec])
            out.append(Clip(path: dest.path, mark: mark, seconds: sec,
                            sourcePath: url.path))
            stage = "コマに割る \(out.count)/\(n)"
        }
        clips = out
        say("\(out.count) コマに割りました（\(String(format: "%.1f", total)) 秒）")
    }

    private func image(_ gen: AVAssetImageGenerator,
                       at t: CMTime) async throws -> CGImage {
        try await withCheckedThrowingContinuation { c in
            gen.generateCGImageAsynchronously(for: t) { img, _, err in
                if let img { c.resume(returning: img) }
                else { c.resume(throwing: err ?? CocoaError(.fileReadUnknown)) }
            }
        }
    }

    private func write(_ cg: CGImage, to url: URL) -> Bool {
        let rep = NSBitmapImageRep(cgImage: cg)
        guard let data = rep.representation(using: .jpeg,
                                            properties: [.compressionFactor: 0.85])
        else { return false }
        return (try? data.write(to: url)) != nil
    }

    // MARK: - 読ませる

    /// 選んだコマを視覚モデルに読ませる。**出力は全部提案。**
    ///
    /// 専用のプロンプトで、空いている側面だけを訊く。値を作れとは
    /// 言わない — 見えないものは飛ばさせる。
    func read(clip: Clip, model: AtelierAnalyst.Pick,
              into m: AtelierModel) async {
        busy = true
        defer { busy = false; stage = "" }
        stage = "読ませる"

        guard let b64 = base64(of: clip.path) else {
            say("コマを読み込めませんでした"); return
        }
        let open = m.states.filter { $0.value.state == "UNKNOWN_NOT_OBSERVED" }
            .keys.sorted()
        // **文面は設定であって文章ではない。** 実測で勝ったものを使う。
        // 直書きすると、誰かが良かれと思って直した瞬間に捏造が戻る。
        let measured = AtelierPrompts.readFrame(openAspects: open)
        let prompt = measured.text

        var raw: String?
        switch model {
        case .vera:
            say("Vera は絵を見ません。モデルを選んでください")
            return
        case .ollama(let name):
            raw = await OllamaClient.shared.generateConversation(
                model: name, messages: [("user", prompt)],
                imagesForLastUserMessage: [b64], maxTokens: 1200)
        case .jgen:
            say("JGEN は画像を受け取りません。Ollama かクラウドを選んでください")
            return
        case .lmStudio(let name):
            raw = await LMStudioClient.shared.generateWithImage(
                model: name,
                systemPrompt: "服飾の視覚解析。JSON 配列のみを返す。",
                userText: prompt, imageBase64: b64)
        case .cloud(let p, let name):
            let r = await CloudAPIClient.shared.send(
                systemPrompt: "服飾の視覚解析。JSON 配列のみを返す。",
                userMessage: prompt, imageBase64: b64,
                provider: p, modelOverride: name)
            if case .success(let t) = r { raw = t }
            if case .failure(let e) = r { say("失敗: \(e)") }
        }

        guard let text = raw, !text.isEmpty else {
            say("モデルが答えませんでした"); return
        }
        let items = AtelierAnalyst.parse(text)
        guard !items.isEmpty else {
            say("解釈できる提案はありませんでした（0 件）"); return
        }
        for it in items {
            _ = await call("garment_propose",
                           ["part": it.part, "aspect": it.aspect,
                            "value": it.value, "source": model.sourceName,
                            "note": it.why,
                            "ref_path": clip.path, "ref_mark": clip.mark])
        }
        await m.load()
        say("\(clip.mark): \(items.count) 件を提案として置きました")
    }

    // MARK: - 照らす

    /// 似ているコマを探す。**返るのは「似ている」であって「由来」ではない。**
    ///
    /// 使うのは macOS の画像特徴量(`VNGenerateImageFeaturePrint`)で、
    /// 服飾に合わせて学習したものではない。近い絵柄を並べるところまでで、
    /// 何かを決めるものではないので、距離は注記にしか入らない。
    func findSimilar(to clip: Clip, among pool: [Clip]) async {
        busy = true
        defer { busy = false; stage = "" }
        stage = "照らす"
        guard let q = featureprint(clip.path) else {
            say("特徴量を取れませんでした"); return
        }
        var out: [Match] = []
        for c in pool where c.path != clip.path {
            guard let v = featureprint(c.path) else { continue }
            out.append(Match(path: c.path, distance: distance(q, v),
                             mark: c.mark))
        }
        matches = out.sorted { $0.distance < $1.distance }
        say("\(matches.count) 件を距離順に並べました（判断ではありません）")
    }

    /// 似ていた一枚を、由来の**申し立て**として置く。実例になるのは
    /// 人が採用したときだけ。
    func proposeSimilarity(_ match: Match, part: String, aspect: String,
                           into m: AtelierModel) async {
        _ = await call("garment_propose",
                       ["part": part, "aspect": aspect,
                        "value": "「\(match.mark)」と似ている",
                        "source": "類似検索 image-featureprint",
                        "note": String(format:
                            "距離 %.3f — 出所の申告であって布の性質ではない",
                            match.distance),
                        "ref_path": match.path, "ref_mark": match.mark])
        await m.load()
        say("類似を提案として置きました（採用は人）")
    }

    private func base64(of path: String) -> String? {
        guard let d = FileManager.default.contents(atPath: path) else {
            return nil
        }
        return d.base64EncodedString()
    }

    private func featureprint(_ path: String) -> VNFeaturePrintObservation? {
        guard let img = NSImage(contentsOfFile: path),
              let cg = img.cgImage(forProposedRect: nil, context: nil,
                                   hints: nil) else { return nil }
        let req = VNGenerateImageFeaturePrintRequest()
        let handler = VNImageRequestHandler(cgImage: cg, options: [:])
        try? handler.perform([req])
        return req.results?.first as? VNFeaturePrintObservation
    }

    private func distance(_ a: VNFeaturePrintObservation,
                          _ b: VNFeaturePrintObservation) -> Float {
        var d = Float(0)
        try? a.computeDistance(&d, to: b)
        return d
    }
}
