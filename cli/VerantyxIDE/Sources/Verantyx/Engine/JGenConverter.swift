import Foundation
import AppKit

/// Shared path logic for JGEN's bundled-binary storage location, used by
/// both `JGenConverter` (writes converted models here) and
/// `JCrossChatManager` (loads them from here) -- a single source of truth
/// so the two can't drift out of sync on where `.jgen` files actually live.
enum JGenPaths {
    /// Persistent storage for the bundled `jgen_forge` binary's own
    /// dropzone/converted models -- the correct location for a bundled
    /// tool's own data (not inside a dev repo). Created lazily on first use.
    static var appSupportBaseDir: URL {
        let base = (try? FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true))
            ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support")
        return base.appendingPathComponent("Verantyx/jgen", isDirectory: true)
    }

    static var convertedModelsDir: URL {
        appSupportBaseDir.appendingPathComponent("converted_models")
    }
}

/// Wraps `jgen_forge.py` (verantyx-cli's model-conversion CLI, not something
/// this session wrote) to give Verantyx an "Ollama pull"-simple way to get a
/// .jgen model ready for JCrossEngine: point at a model already sitting in
/// Ollama/LM Studio/the HF cache by name, or drop a model folder/.gguf into
/// the dropzone, and conversion runs with no manual arguments.
///
/// Milestone F: `jgen_forge.py` is frozen into a self-contained executable
/// (PyInstaller, `--onefile`, numpy statically included, no external Python
/// needed) and embedded straight into the app bundle at `Contents/MacOS/
/// jgen_forge` (`Vendor/jgen_forge`, committed to this repo, copied in by
/// the "Embed jgen_forge into App Bundle" build phase -- same
/// committed-binary pattern as `libjcross_engine_glm.dylib`, so it's present
/// in CI-built releases too, unlike a Run Script that reaches into a sibling
/// checkout). This is the default, zero-setup path on any Mac. An earlier
/// approach shelled out to a python3.11 interpreter + a hardcoded sibling
/// verantyx-cli checkout path -- that only worked on the one machine it was
/// developed on. The old path/interpreter combo is kept as an opt-in
/// "advanced" override (`useCustomRepo`) for anyone who wants a dev checkout
/// instead (bleeding-edge jgen_forge.py, or the torch-dependent legacy
/// `.bin` checkpoint path the bundled binary excludes to stay a reasonable
/// size).
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
    }

    @Published private(set) var isRunning = false
    @Published private(set) var log: String = ""
    @Published private(set) var convertedModels: [String] = []
    /// Models already found in Ollama/LM Studio/the HF cache, refreshed via
    /// `refreshDiscoveredSources()` -- lets Settings show a pick list
    /// instead of requiring the user to type an exact model name.
    @Published private(set) var discoveredSources: [DiscoveredSource] = []
    @Published private(set) var isDiscovering = false

    /// Opt-in advanced override: use a real verantyx-cli checkout (via
    /// system python3.11) instead of the bundled binary. Off by default --
    /// the bundled binary needs no setup and covers Ollama/HF-safetensors
    /// conversion, which is what almost everyone needs.
    @Published var useCustomRepo: Bool = UserDefaults.standard.bool(forKey: "jgen_use_custom_repo") {
        didSet {
            UserDefaults.standard.set(useCustomRepo, forKey: "jgen_use_custom_repo")
            refreshConvertedModelsList()
            Task { await refreshDiscoveredSources() }
        }
    }

    /// Only meaningful when `useCustomRepo` is on -- where that checkout
    /// lives. Persisted so a correct pick only needs to happen once.
    @Published private(set) var repoPath: String =
        UserDefaults.standard.string(forKey: "jgen_repo_path") ?? ""
    private let pythonPath = "/opt/homebrew/bin/python3.11"

    /// True only if `repoPath` actually points at a checkout containing
    /// jgen_forge.py -- gates whether the custom-repo subprocess path is
    /// even attempted, so a wrong/missing path fails with a clear message
    /// instead of a confusing Python traceback.
    var repoPathValid: Bool {
        !repoPath.isEmpty && FileManager.default.fileExists(atPath: "\(repoPath)/jgen_forge.py")
    }

    /// The bundled `jgen_forge` binary, embedded alongside the app's own
    /// executable (see the "Embed jgen_forge into App Bundle" build phase).
    private var bundledBinaryURL: URL? {
        guard let exe = Bundle.main.executableURL else { return nil }
        let url = exe.deletingLastPathComponent().appendingPathComponent("jgen_forge")
        return FileManager.default.fileExists(atPath: url.path) ? url : nil
    }

    private var appSupportBaseDir: URL { JGenPaths.appSupportBaseDir }

    private init() {
        refreshConvertedModelsList()
    }

    /// Lets the user point at a verantyx-cli checkout for the advanced
    /// override, via a folder picker. Validates jgen_forge.py is inside
    /// before accepting the pick, and turns `useCustomRepo` on.
    @MainActor
    func pickRepoFolder() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        panel.prompt = "Select"
        panel.message = "Select the verantyx-cli folder (containing jgen_forge.py)"
        guard panel.runModal() == .OK, let url = panel.url else { return }
        guard FileManager.default.fileExists(atPath: url.appendingPathComponent("jgen_forge.py").path) else {
            log += (log.isEmpty ? "" : "\n---\n") + "✗ \(url.path) doesn't contain jgen_forge.py -- not a verantyx-cli checkout."
            return
        }
        repoPath = url.path
        UserDefaults.standard.set(url.path, forKey: "jgen_repo_path")
        useCustomRepo = true
    }

    var dropzoneURL: URL {
        let base = (useCustomRepo && repoPathValid) ? URL(fileURLWithPath: repoPath) : appSupportBaseDir
        return base.appendingPathComponent("models_dropzone")
    }

    private var convertedModelsDir: URL {
        let base = (useCustomRepo && repoPathValid) ? URL(fileURLWithPath: repoPath) : appSupportBaseDir
        return base.appendingPathComponent("converted_models")
    }

    /// Reveals the dropzone folder in Finder so the user can literally drag
    /// a model folder or .gguf file into it -- the "just put it in" flow.
    func revealDropzoneInFinder() {
        try? FileManager.default.createDirectory(at: dropzoneURL, withIntermediateDirectories: true)
        NSWorkspace.shared.open(dropzoneURL)
    }

    /// Ollama/LM Studio/HF-cache "pull by name" flow: jgen_forge.py's own
    /// `pull` subcommand already scans those locations (including Ollama's
    /// model store) and converts the first name match. Prefer calling this
    /// with an exact name from `discoveredSources` (via `convert(_:)`)
    /// rather than free-typed text, to avoid an ambiguous substring match.
    ///
    /// `tokenizer`, if non-empty, is passed through as jgen_forge's own
    /// `--tokenizer` flag (an HF repo id like "Qwen/Qwen2.5-0.5B-Instruct"
    /// or a local tokenizer folder path). This is the same explicit
    /// override the original verantyx-cli always supported -- Ollama only
    /// ever hands over raw GGUF weights, never a tokenizer, so jgen_forge
    /// resolves one in priority order: explicit --tokenizer (this) > an
    /// HF-cache vocab-size/name match > synthesizing one from the GGUF's
    /// own embedded tokenizer fields > a vocab-only dictionary sidecar (no
    /// chat template). Explicit override is the most reliable tier and the
    /// only one that can route around a GGUF whose own embedded tokenizer
    /// metadata is incomplete (e.g. a "gpt2"-tagged tokenizer with no
    /// merges data, which the auto tiers can't do anything about).
    func pull(_ name: String, tokenizer: String? = nil) async {
        var args = ["pull", name]
        if let tokenizer, !tokenizer.trimmingCharacters(in: .whitespaces).isEmpty {
            args += ["--tokenizer", tokenizer.trimmingCharacters(in: .whitespaces)]
        }
        await run(args: args)
        refreshConvertedModelsList()
        await refreshDiscoveredSources()
    }

    /// Converts one already-discovered source directly -- the no-typing
    /// path: Settings lists what's already in Ollama/LM Studio/HF cache,
    /// the user just clicks Convert on a row. `tokenizer` is an optional
    /// explicit override, see `pull(_:tokenizer:)`.
    func convert(_ source: DiscoveredSource, tokenizer: String? = nil) async {
        await pull(source.name, tokenizer: tokenizer)
    }

    /// Runs `jgen_forge.py sources --json` (LM Studio/HF cache -- these
    /// have no HTTP API, so this needs a working jgen_forge, bundled or
    /// custom) and separately queries Ollama directly over HTTP
    /// (`OllamaClient.listModelsDetailed()`, no filesystem dependency at
    /// all). Merges both, preferring the jgen_forge-sourced entry on a name
    /// collision since it carries the real `converted` flag. This way
    /// Ollama models are always discoverable even in the (now rare) case
    /// jgen_forge itself can't run.
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

        let convertedNames = Set(convertedModels)
        let ollamaModels = await OllamaClient.shared.listModelsDetailed()
        let knownNames = Set(forgeSources.map(\.name))
        let ollamaOnly = ollamaModels
            .filter { !knownNames.contains($0.name) }
            .map { model in
                DiscoveredSource(
                    name: model.name,
                    path: "",
                    source: "ollama",
                    size_bytes: model.sizeBytes,
                    converted: convertedNames.contains { $0.contains(Self.sanitized(model.name)) }
                )
            }

        discoveredSources = (forgeSources + ollamaOnly).sorted { $0.size_bytes > $1.size_bytes }
    }

    private static func sanitized(_ name: String) -> String {
        name.replacingOccurrences(of: ":", with: "_").replacingOccurrences(of: "/", with: "_")
    }

    /// Converts anything new sitting in models_dropzone/ that hasn't been
    /// converted yet -- the "just drop the model in" flow, for models not
    /// already known to Ollama/LM Studio/HF cache (e.g. a manually
    /// downloaded safetensors folder or .gguf file).
    func scanDropzone() async {
        await run(args: ["scan"])
        refreshConvertedModelsList()
    }

    /// Re-reads converted_models/*.jgen directly from disk rather than
    /// parsing `jgen_forge.py list`'s text output -- simpler and doesn't
    /// depend on that command's formatting staying stable. Unions the
    /// bundled-binary storage location with the custom-repo one (if that
    /// override is on and valid) so nothing already converted under either
    /// location silently disappears from the list.
    func refreshConvertedModelsList() {
        var names = Set<String>()
        if let entries = try? FileManager.default.contentsOfDirectory(atPath: appSupportBaseDir.appendingPathComponent("converted_models").path) {
            names.formUnion(entries.filter { $0.hasSuffix(".jgen") })
        }
        if useCustomRepo && repoPathValid,
           let entries = try? FileManager.default.contentsOfDirectory(atPath: "\(repoPath)/converted_models") {
            names.formUnion(entries.filter { $0.hasSuffix(".jgen") })
        }
        convertedModels = names.sorted()
    }

    /// True if either the bundled binary or a valid custom-repo override is
    /// available to actually run jgen_forge commands against.
    private var canRunForge: Bool {
        (useCustomRepo && repoPathValid) || bundledBinaryURL != nil
    }

    private func run(args: [String]) async {
        isRunning = true
        defer { isRunning = false }
        guard canRunForge else {
            let message = useCustomRepo
                ? "✗ verantyx-cli not found at \(repoPath) -- use \"Locate verantyx-cli...\" to point at where it's actually checked out on this Mac, or turn off the custom-repo override to use the bundled binary."
                : "✗ jgen_forge isn't embedded in this build -- rebuild the app, or enable the custom-repo override in Settings and point it at a verantyx-cli checkout."
            log += (log.isEmpty ? "" : "\n---\n") + message
            return
        }
        let output = await runRaw(args: args)
        log += (log.isEmpty ? "" : "\n---\n") + output
    }

    /// Runs jgen_forge and returns raw stdout+stderr, without touching
    /// `log` -- used both by `run` (human-facing log) and by JSON-output
    /// commands like `sources --json` (machine-facing, would just be noise
    /// in the log). Prefers the bundled self-contained binary; falls back
    /// to python3.11 + a custom repo checkout only when that override is
    /// explicitly enabled.
    private func runRaw(args: [String]) async -> String {
        let useCustom = useCustomRepo && repoPathValid
        let repoPath = self.repoPath
        let pythonPath = self.pythonPath
        let bundled = bundledBinaryURL
        let baseDir = appSupportBaseDir
        return await Task.detached(priority: .userInitiated) { () -> String in
            let process = Process()
            if useCustom {
                // Custom-repo mode: BASE resolves from jgen_forge.py's own
                // __file__ (= repoPath), no JGEN_BASE_DIR needed -- matches
                // this mode's own checkout's dropzone/converted_models.
                process.executableURL = URL(fileURLWithPath: pythonPath)
                process.arguments = ["\(repoPath)/jgen_forge.py"] + args
            } else if let bundled {
                try? FileManager.default.createDirectory(at: baseDir, withIntermediateDirectories: true)
                process.executableURL = bundled
                process.arguments = args
                process.environment = (ProcessInfo.processInfo.environment).merging(
                    ["JGEN_BASE_DIR": baseDir.path], uniquingKeysWith: { _, new in new }
                )
            } else {
                return "✗ No jgen_forge available (neither bundled binary nor a valid custom-repo override)."
            }
            let pipe = Pipe()
            process.standardOutput = pipe
            process.standardError = pipe
            do { try process.run() } catch {
                return "✗ Could not launch jgen_forge: \(error.localizedDescription)"
            }
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            process.waitUntilExit()
            let text = String(data: data, encoding: .utf8) ?? ""
            return text.isEmpty ? "(no output, exit \(process.terminationStatus))" : text
        }.value
    }

    /// Reads a converted model's `.meta.json` sidecar, checking both
    /// possible storage locations (matching `JCrossChatManager`'s own
    /// resolution order) -- used by Settings to show which converted
    /// models are actually loadable.
    func metaJSON(for modelFileName: String) -> [String: Any]? {
        let appSupportPath = JGenPaths.convertedModelsDir.appendingPathComponent(modelFileName).path + ".meta.json"
        if let data = FileManager.default.contents(atPath: appSupportPath),
           let meta = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            return meta
        }
        if useCustomRepo && repoPathValid {
            let customPath = "\(repoPath)/converted_models/\(modelFileName).meta.json"
            if let data = FileManager.default.contents(atPath: customPath),
               let meta = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                return meta
            }
        }
        return nil
    }

    /// True if this model's architecture is one JCrossEngine's Rust
    /// forward pass can actually run (chat/encode/council) -- false for
    /// lexicon-only conversions (e.g. hybrid_ssm MoE architectures like
    /// qwen35moe), which jgen_forge still converts but only for
    /// project/resynthesize-style static vector lookups, not inference.
    func isArchSupported(_ modelFileName: String) -> Bool {
        guard let arch = metaJSON(for: modelFileName)?["arch"] as? String else { return true }
        return ["standard", "moe_standard"].contains(arch)
    }
}
