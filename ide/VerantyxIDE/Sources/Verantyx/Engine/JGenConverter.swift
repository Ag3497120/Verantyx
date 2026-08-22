import Foundation
import AppKit

/// Shared paths for JGEN conversion + load. Everything lives under Application
/// Support — the forge binary ships inside the app (`Contents/MacOS/jgen_forge`).
enum JGenPaths {
    static var appSupportBaseDir: URL {
        let base = (try? FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true))
            ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support")
        return base.appendingPathComponent("Verantyx/jgen", isDirectory: true)
    }

    static var convertedModelsDir: URL {
        appSupportBaseDir.appendingPathComponent("converted_models")
    }
}

/// In-app GGUF/HF → `.jgen` conversion. The converter **is** verantyx-cli's
/// forge, frozen and embedded in the Verantyx app — a general feature for
/// every DMG user, not an optional external-repo hookup.
@MainActor
final class JGenConverter: ObservableObject {
    static let shared = JGenConverter()

    struct DiscoveredSource: Identifiable, Decodable {
        let name: String
        let path: String
        let source: String
        let size_bytes: Int64
        let converted: Bool
        var id: String { name }

        var sizeGB: Double { Double(size_bytes) / Double(1 << 30) }

        var looksHybrid: Bool {
            let n = name.lowercased()
            return n.contains("ornith") || n.contains("qwen3.5") || n.contains("qwen3_5")
                || n.contains("qwen35") || n.contains("qwen3.6") || n.contains("qwen3_6")
        }
    }

    @Published private(set) var isRunning = false
    @Published private(set) var log: String = ""
    @Published private(set) var convertedModels: [String] = []
    @Published private(set) var discoveredSources: [DiscoveredSource] = []
    @Published private(set) var isDiscovering = false

    @Published private(set) var tokenizerSuggestions: [String: String] = [:]
    @Published private(set) var suggestingTokenizerFor: String?

    func needsRealTokenizer(_ modelFileName: String) -> Bool {
        guard let meta = metaJSON(for: modelFileName) else { return false }
        if meta["vocab_sidecar"] != nil { return true }
        if let tok = meta["tokenizer"] as? String, tok.hasSuffix(".vocab.json") { return true }
        return false
    }

    func suggestTokenizerRepo(for modelFileName: String, sourceName: String) {
        guard suggestingTokenizerFor == nil else { return }
        suggestingTokenizerFor = modelFileName
        Task {
            let found = await TokenizerRepoSuggester.shared.suggest(forModelName: sourceName)
            await MainActor.run {
                self.suggestingTokenizerFor = nil
                if let found { self.tokenizerSuggestions[modelFileName] = found }
            }
        }
    }

    private var bundledBinaryURL: URL? {
        guard let exe = Bundle.main.executableURL else { return nil }
        let url = exe.deletingLastPathComponent().appendingPathComponent("jgen_forge")
        return FileManager.default.fileExists(atPath: url.path) ? url : nil
    }

    private var appSupportBaseDir: URL { JGenPaths.appSupportBaseDir }

    private init() {
        refreshConvertedModelsList()
    }

    var dropzoneURL: URL {
        appSupportBaseDir.appendingPathComponent("models_dropzone")
    }

    func revealDropzoneInFinder() {
        try? FileManager.default.createDirectory(at: dropzoneURL, withIntermediateDirectories: true)
        NSWorkspace.shared.open(dropzoneURL)
    }

    /// Always `--dense` for GGUF / hybrid inference-ready converts.
    func pull(_ name: String, tokenizer: String? = nil) async {
        var args = ["pull", name, "--dense"]
        if let tokenizer, !tokenizer.trimmingCharacters(in: .whitespaces).isEmpty {
            args += ["--tokenizer", tokenizer.trimmingCharacters(in: .whitespaces)]
        }
        await run(args: args)
        refreshConvertedModelsList()
        await refreshDiscoveredSources()
    }

    func convert(_ source: DiscoveredSource, tokenizer: String? = nil) async {
        await pull(source.name, tokenizer: tokenizer)
    }

    func refreshDiscoveredSources() async {
        isDiscovering = true
        defer { isDiscovering = false }

        var forgeSources: [DiscoveredSource] = []
        if canRunForge {
            let raw = await runRaw(args: ["sources", "--json"])
            if let data = raw.data(using: .utf8),
               let sources = try? JSONDecoder().decode([DiscoveredSource].self, from: data) {
                forgeSources = sources
            }
        }

        // Ollama is deliberately excluded as a *conversion source*.
        //
        // Its GGUF exports repeatedly produced .jgen files that were subtly wrong
        // rather than obviously broken: qwen3.5 names the linear-attention dt bias
        // `ssm_dt` where the mapping expected `ssm_dt.bias`, so it landed under a
        // passthrough name the engine never looks for and the model died on layer
        // 0; other pulls came through with GDN geometry missing from the sidecar
        // entirely. Those are the ones that were caught. A conversion that loses a
        // tensor and still loads is the failure mode that matters, and there is no
        // general way to detect it from the GGUF alone.
        //
        // LM Studio and the HF cache ship the original safetensors plus a real
        // config, so they convert without this class of guesswork. Ollama remains
        // a first-class *chat* provider — this only removes it as conversion input.
        discoveredSources = forgeSources
            .filter { $0.source != "ollama" }
            .sorted { a, b in
                if a.looksHybrid != b.looksHybrid { return a.looksHybrid && !b.looksHybrid }
                return a.size_bytes > b.size_bytes
            }
    }

    private static func sanitized(_ name: String) -> String {
        name.replacingOccurrences(of: ":", with: "_").replacingOccurrences(of: "/", with: "_")
    }

    // MARK: - Requantization

    /// The standalone requantizer (ships beside jgen_forge in the app bundle;
    /// falls back to the engine workspace build on a dev machine).
    static func requantBinaryURL() -> URL? {
        if let exe = Bundle.main.executableURL {
            let bundled = exe.deletingLastPathComponent().appendingPathComponent("requant_jgen")
            if FileManager.default.isExecutableFile(atPath: bundled.path) { return bundled }
        }
        let dev = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Projects/verantyx-cli/jcross_engine_glm/target/release/requant_jgen")
        return FileManager.default.isExecutableFile(atPath: dev.path) ? dev : nil
    }

    /// Whether this converted model would benefit from requantization: f16
    /// (no `"quantized": true` in the sidecar) and big enough that residency
    /// is at stake. Small f16 models load fine as they are.
    func canRequantize(_ modelFileName: String) -> Bool {
        requantUnavailableReason(modelFileName) == nil
    }

    /// Why the Quantize button is absent — but only for models big enough
    /// that someone would look for it. Small models return nil (no note).
    /// The button used to just silently not exist, which read as "the app
    /// refuses to generate this model" with no way to learn which
    /// precondition failed.
    func requantHint(_ modelFileName: String) -> String? {
        let url = JGenPaths.convertedModelsDir.appendingPathComponent(modelFileName)
        let size = (try? FileManager.default.attributesOfItem(atPath: url.path)[.size] as? UInt64)
            .flatMap { $0 } ?? 0
        guard size > 8 << 30 else { return nil }
        return requantUnavailableReason(modelFileName)
    }

    func requantUnavailableReason(_ modelFileName: String) -> String? {
        guard Self.requantBinaryURL() != nil else {
            return L("requant_jgen binary not bundled in this build",
                     "requant_jgen バイナリがこのビルドに同梱されていません")
        }
        guard let meta = metaJSON(for: modelFileName) else {
            return L("no .meta.json sidecar", ".meta.json サイドカーがありません")
        }
        if (meta["quantized"] as? Bool) == true {
            return L("already quantized — nothing to shrink",
                     "既に量子化済みです — これ以上小さくなりません")
        }
        let url = JGenPaths.convertedModelsDir.appendingPathComponent(modelFileName)
        let size = (try? FileManager.default.attributesOfItem(atPath: url.path)[.size] as? UInt64)
            .flatMap { $0 } ?? 0
        if size <= 8 << 30 {
            return L("f16 under 8 GB loads fine as-is",
                     "8GB未満のf16はそのまま問題なく動きます")
        }
        return nil
    }

    /// f16 JGEN → quantized JGEN (q4_k body, q6_k head), written beside the
    /// original as `<name>-q4k.jgen`. The original is left in place — deleting
    /// a 50 GB source the user may still want is their decision, not this
    /// function's.
    func requantize(_ modelFileName: String) async {
        guard let bin = Self.requantBinaryURL() else {
            log += "\n✗ requant_jgen not found"
            return
        }
        isRunning = true
        beginProtectedWrite()
        defer { isRunning = false; endProtectedWrite() }

        let src = JGenPaths.convertedModelsDir.appendingPathComponent(modelFileName)
        let outName = modelFileName
            .replacingOccurrences(of: "_full.jgen", with: "")
            .replacingOccurrences(of: ".jgen", with: "") + "-q4k.jgen"
        let dst = JGenPaths.convertedModelsDir.appendingPathComponent(outName)

        // Space check up front — the failure mode already happened once: the
        // write died at "No space left on device" two thirds through.
        let free = (try? URL(fileURLWithPath: "/").resourceValues(
            forKeys: [.volumeAvailableCapacityForImportantUsageKey])
            .volumeAvailableCapacityForImportantUsage).flatMap { $0 } ?? 0
        let srcSize = (try? FileManager.default.attributesOfItem(atPath: src.path)[.size] as? UInt64)
            .flatMap { $0 } ?? 0
        let needed = Int64(Double(srcSize) * 0.4)
        if free < needed {
            log += String(format: "\n✗ 空き容量不足: %.1f GB 必要、%.1f GB しかありません",
                          Double(needed) / Double(1 << 30), Double(free) / Double(1 << 30))
            return
        }

        log += "\n⏳ 量子化中: \(modelFileName) → \(outName) (数分〜十数分)"
        let out = await Task.detached(priority: .userInitiated) { () -> String in
            let proc = Process()
            proc.executableURL = bin
            proc.arguments = [src.path, dst.path]
            let pipe = Pipe()
            proc.standardOutput = pipe
            proc.standardError = pipe
            do { try proc.run() } catch { return "✗ \(error.localizedDescription)" }
            proc.waitUntilExit()
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            let text = String(data: data, encoding: .utf8) ?? ""
            return proc.terminationStatus == 0 ? "✓ " + (text.split(separator: "\n").last.map(String.init) ?? "done")
                                              : "✗ " + text
        }.value
        log += "\n" + out
        refreshConvertedModelsList()
    }

    func scanDropzone() async {
        await run(args: ["scan"])
        refreshConvertedModelsList()
    }

    /// Suppresses the delete sweep while something is writing a `.jgen` that
    /// does not have its sidecar yet.
    ///
    /// Counted rather than boolean because a transfer and a conversion can
    /// overlap. Model transfer stages outside this directory precisely so it
    /// never depends on this guard — but `refreshConvertedModelsList` runs on
    /// every inventory refresh, which the model picker triggers routinely, and
    /// the next person to add a write path here should not have to rediscover
    /// that a partial file gets deleted out from under them.
    private var protectedWrites = 0

    func beginProtectedWrite() { protectedWrites += 1 }
    func endProtectedWrite() { protectedWrites = max(0, protectedWrites - 1) }

    func refreshConvertedModelsList() {
        let sweep = !isRunning && protectedWrites == 0
        let dir = appSupportBaseDir.appendingPathComponent("converted_models").path
        var names = Set<String>()
        if let entries = try? FileManager.default.contentsOfDirectory(atPath: dir) {
            names.formUnion(Self.completeJGenFiles(entries, dir: dir, deleteIncomplete: sweep))
        }
        convertedModels = names.sorted()
    }

    private static func completeJGenFiles(_ entries: [String], dir: String, deleteIncomplete: Bool) -> [String] {
        entries.filter { entry in
            guard entry.hasSuffix(".jgen") else { return false }
            let jgenPath = (dir as NSString).appendingPathComponent(entry)
            let metaPath = jgenPath + ".meta.json"
            if FileManager.default.fileExists(atPath: metaPath) { return true }
            if deleteIncomplete {
                try? FileManager.default.removeItem(atPath: jgenPath)
            }
            return false
        }
    }

    private var canRunForge: Bool { bundledBinaryURL != nil }

    private func run(args: [String]) async {
        isRunning = true
        defer { isRunning = false }
        guard canRunForge else {
            log += (log.isEmpty ? "" : "\n---\n")
                + "✗ Built-in converter missing from this app. Reinstall Verantyx."
            return
        }
        let output = await runRaw(args: args)
        log += (log.isEmpty ? "" : "\n---\n") + output

        // Conversion failures feed the same typed-failure ledger builds do.
        // The classifier knows this pipeline's real failure shapes — missing
        // GDN geometry, missing tokenizer, full disk — because its fixtures
        // are this project's own confirmed incidents. Heuristic trigger on
        // purpose: jgen_forge does not return a clean exit code through
        // runRaw, and over-recording a success as a failure is caught
        // downstream by the classifier returning UNCLASSIFIED, which is
        // itself a signal worth counting. Fire-and-forget; recording must
        // never affect the conversion path.
        let lowered = output.lowercased()
        if lowered.contains("error") || lowered.contains("refusing")
            || lowered.contains("traceback") || output.contains("✗") {
            let excerpt = String(output.suffix(4000))
            Task.detached(priority: .utility) {
                _ = await VeraMemoryBridge.recordBuildFailure(
                    source: "jgen_convert", logExcerpt: excerpt)
            }
        }
    }

    private func runRaw(args: [String]) async -> String {
        let bundled = bundledBinaryURL
        let baseDir = appSupportBaseDir
        return await Task.detached(priority: .userInitiated) { () -> String in
            guard let bundled else {
                return "✗ Built-in converter missing from this app."
            }
            let process = Process()
            try? FileManager.default.createDirectory(at: baseDir, withIntermediateDirectories: true)
            process.executableURL = bundled
            process.arguments = args
            process.environment = ProcessInfo.processInfo.environment.merging(
                ["JGEN_BASE_DIR": baseDir.path], uniquingKeysWith: { _, new in new }
            )
            let pipe = Pipe()
            process.standardOutput = pipe
            process.standardError = pipe
            do { try process.run() } catch {
                return "✗ Could not launch converter: \(error.localizedDescription)"
            }
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            process.waitUntilExit()
            let text = String(data: data, encoding: .utf8) ?? ""
            return text.isEmpty ? "(no output, exit \(process.terminationStatus))" : text
        }.value
    }

    func metaJSON(for modelFileName: String) -> [String: Any]? {
        let path = JGenPaths.convertedModelsDir.appendingPathComponent(modelFileName).path + ".meta.json"
        guard let data = FileManager.default.contents(atPath: path),
              let meta = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return nil
        }
        return meta
    }

    func isArchSupported(_ modelFileName: String) -> Bool {
        guard let meta = metaJSON(for: modelFileName) else { return true }
        if let parts = meta["parts"] as? String, parts == "lexicon" { return false }
        guard let arch = meta["arch"] as? String else { return true }
        return ["standard", "moe_standard", "hybrid_ssm"].contains(arch)
    }

    /// 前向きに走らせられるか。骨格だけでなく**トークナイザの実体**まで
    /// 見る。jgen_forge は本物の HF トークナイザが見つからないと GGUF の
    /// 語彙だけを書くので、骨格は通るのに読み込みで落ちる — 選ばせてから
    /// 落とすのが一番たちが悪いので、選択肢を作る側で判る形にしておく。
    /// (JCrossChatManager.load の判定と同じ二つを、同じ順で見ている)
    func canRunForward(_ modelFileName: String) -> Bool {
        guard isArchSupported(modelFileName) else { return false }
        guard let meta = metaJSON(for: modelFileName) else { return true }
        guard let tok = meta["tokenizer"] as? String else { return false }
        let folder = URL(fileURLWithPath: tok).deletingLastPathComponent()
        return FileManager.default.fileExists(
            atPath: folder.appendingPathComponent("config.json").path)
    }

    func archBadge(for modelFileName: String) -> String? {
        guard let meta = metaJSON(for: modelFileName) else { return nil }
        if let parts = meta["parts"] as? String, parts == "lexicon" { return "Lexicon" }
        guard let arch = meta["arch"] as? String else { return nil }
        switch arch {
        case "hybrid_ssm": return "Hybrid"
        case "moe_standard": return "MoE"
        case "standard": return "Dense"
        default: return arch
        }
    }
}
