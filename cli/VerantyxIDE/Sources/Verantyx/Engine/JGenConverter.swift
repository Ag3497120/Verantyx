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

    @Published private(set) var isRunning = false
    @Published private(set) var log: String = ""
    @Published private(set) var convertedModels: [String] = []

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
    /// model store) and converts the first name match -- this is the
    /// one-field, one-button "just give it a name" path.
    func pull(_ name: String) async {
        await run(args: ["pull", name])
        refreshConvertedModelsList()
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
        let repoPath = self.repoPath
        let pythonPath = self.pythonPath
        let output = await Task.detached(priority: .userInitiated) { () -> String in
            let process = Process()
            process.executableURL = URL(fileURLWithPath: pythonPath)
            process.arguments = ["jgen_forge.py"] + args
            process.currentDirectoryURL = URL(fileURLWithPath: repoPath)
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
        log += (log.isEmpty ? "" : "\n---\n") + output
    }
}
