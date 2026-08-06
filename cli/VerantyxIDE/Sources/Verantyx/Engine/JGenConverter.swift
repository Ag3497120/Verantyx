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
