import Foundation
import AppKit

/// Wraps verantyx-cli's `jgen_forge.py` (a working Python CLI, not something
/// this session wrote) to give Verantyx an "Ollama pull"-simple way to get a
/// .jgen model ready for JCrossEngine: point at a model already sitting in
/// Ollama/LM Studio/the HF cache by name, or drop a model folder/.gguf into
/// the dropzone, and conversion runs with no manual arguments. Matches
/// jgen_forge.py's own stated goal: "store the model and it's immediately
/// usable" (see its module docstring).
///
/// This shells out to a subprocess rather than going through the
/// JCrossEngine FFI bridge -- conversion is an offline, one-time,
/// CPU/IO-bound step (not the hot inference path), so subprocess latency
/// doesn't matter, and reusing jgen_forge.py's already-working conversion
/// logic (HF safetensors + GGUF quant parsing, MoE tensor splitting,
/// streaming for huge models) is far more reliable than reimplementing it.
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

    /// Where verantyx-cli lives -- same repo/path pattern already
    /// established for the vera-memory MCP server setup this session.
    private let repoPath = "/Users/motonishikoudai/Projects/verantyx-cli"
    private let pythonPath = "/opt/homebrew/bin/python3.11"

    private init() {
        refreshConvertedModelsList()
    }

    var dropzoneURL: URL {
        URL(fileURLWithPath: repoPath).appendingPathComponent("models_dropzone")
    }

    private var convertedModelsDir: URL {
        URL(fileURLWithPath: repoPath).appendingPathComponent("converted_models")
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
    func pull(_ name: String) async {
        await run(args: ["pull", name])
        refreshConvertedModelsList()
        await refreshDiscoveredSources()
    }

    /// Converts one already-discovered source directly -- the no-typing
    /// path: Settings lists what's already in Ollama/LM Studio/HF cache,
    /// the user just clicks Convert on a row.
    func convert(_ source: DiscoveredSource) async {
        await pull(source.name)
    }

    /// Runs `jgen_forge.py sources --json` and parses the result --
    /// real structured discovery, not a hand-typed model name. Populates
    /// `discoveredSources`, sorted by size descending (matching
    /// jgen_forge.py's own sources listing order).
    func refreshDiscoveredSources() async {
        isDiscovering = true
        defer { isDiscovering = false }
        let raw = await runRaw(args: ["sources", "--json"])
        guard let data = raw.data(using: .utf8),
              let sources = try? JSONDecoder().decode([DiscoveredSource].self, from: data) else {
            discoveredSources = []
            return
        }
        discoveredSources = sources.sorted { $0.size_bytes > $1.size_bytes }
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
    /// depend on that command's formatting staying stable.
    func refreshConvertedModelsList() {
        guard let entries = try? FileManager.default.contentsOfDirectory(atPath: convertedModelsDir.path) else {
            convertedModels = []
            return
        }
        convertedModels = entries.filter { $0.hasSuffix(".jgen") }.sorted()
    }

    private func run(args: [String]) async {
        isRunning = true
        defer { isRunning = false }
        let output = await runRaw(args: args)
        log += (log.isEmpty ? "" : "\n---\n") + output
    }

    /// Runs jgen_forge.py and returns raw stdout+stderr, without touching
    /// `log` -- used both by `run` (human-facing log) and by JSON-output
    /// commands like `sources --json` (machine-facing, would just be noise
    /// in the log).
    private func runRaw(args: [String]) async -> String {
        let repoPath = self.repoPath
        let pythonPath = self.pythonPath
        return await Task.detached(priority: .userInitiated) { () -> String in
            let process = Process()
            process.executableURL = URL(fileURLWithPath: pythonPath)
            // Pass the script's absolute path rather than relying on
            // currentDirectoryURL: jgen_forge.py resolves its own BASE dir
            // from __file__, not cwd, and setting currentDirectoryURL here
            // was the actual failure point on at least one machine --
            // Process.run() validates it before even touching the
            // executable, and any resolution issue (permissions, sandboxing)
            // surfaces as a misleading "The file '<dir>' doesn't exist"
            // error blamed on the wrong path in the message.
            process.arguments = ["\(repoPath)/jgen_forge.py"] + args
            let pipe = Pipe()
            process.standardOutput = pipe
            process.standardError = pipe
            do { try process.run() } catch {
                return "✗ Could not launch \(pythonPath): \(error.localizedDescription)"
            }
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            process.waitUntilExit()
            let text = String(data: data, encoding: .utf8) ?? ""
            return text.isEmpty ? "(no output, exit \(process.terminationStatus))" : text
        }.value
    }
}
