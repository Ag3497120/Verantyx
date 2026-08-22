import Foundation

/// Runtime binding to `libjcross_engine_glm` (the JGEN inference engine).
///
/// Deliberately `dlopen`-based rather than link-time: this project has twice
/// shipped a binary that crashed at launch because the dylib's install name
/// was an absolute build-machine path. Resolving at runtime removes that
/// whole failure class and lets a missing engine produce an actionable
/// message instead of a dyld abort.
///
/// Model-agnostic by design. `ModelCompat` is the only place that has an
/// opinion about which architectures are *validated* — the engine itself
/// loads whatever `jgen_forge` produced, and refuses (in Rust) when the
/// attention config cannot be determined.
public final class JGenBackend {

    public enum BackendError: Error, CustomStringConvertible {
        case engineNotFound(searched: [String])
        case symbolMissing(String)
        case loadFailed(path: String)
        case invalidDimensions
        case ffi(function: String, code: Int32)

        public var description: String {
            switch self {
            case .engineNotFound(let searched):
                return """
                libjcross_engine_glm.dylib not found. Searched:
                \(searched.map { "  - \($0)" }.joined(separator: "\n"))
                Build it with `cargo build --release` in jcross_engine_glm/,
                or set JCROSS_ENGINE_DYLIB to its path.
                """
            case .symbolMissing(let name):
                return "engine is missing symbol \(name) — rebuild the dylib from a matching source tree"
            case .loadFailed(let path):
                return """
                engine refused to load: \(path)
                The Rust side prints the reason on stderr. A common cause is an
                incomplete conversion with a missing/partial <model>.meta.json —
                re-run jgen_forge rather than loading the file as-is.
                """
            case .invalidDimensions:
                return "engine reported a non-positive hidden_dim/num_layers"
            case .ffi(let function, let code):
                return "\(function) failed with code \(code)"
            }
        }
    }

    // MARK: - C ABI function types

    private typealias CreateFn = @convention(c) (UnsafePointer<CChar>?) -> UnsafeMutableRawPointer?
    private typealias DestroyFn = @convention(c) (UnsafeMutableRawPointer?) -> Void
    private typealias ResetFn = @convention(c) (UnsafeMutableRawPointer?) -> Void
    private typealias TrimFn = @convention(c) (UnsafeMutableRawPointer?) -> Void
    private typealias DimFn = @convention(c) (UnsafeMutableRawPointer?) -> Int32
    // Lengths are `size_t` on the C side — declaring them Int32 silently
    // corrupts the argument registers on arm64 and surfaces as a nonsense
    // "dimension mismatch" from Rust.
    private typealias GenerateFn = @convention(c) (
        UnsafeMutableRawPointer?, UnsafePointer<UInt32>?, Int,
        Int,
        UnsafeMutablePointer<UInt32>?, Int
    ) -> Int32
    private typealias EncodeFn = @convention(c) (
        UnsafeMutableRawPointer?, UnsafePointer<UInt32>?, Int,
        UnsafeMutablePointer<Float>?, Int
    ) -> Int32

    // MARK: - Resolved handles

    private let library: UnsafeMutableRawPointer
    private let handle: UnsafeMutableRawPointer

    private let fnDestroy: DestroyFn
    private let fnReset: ResetFn
    private let fnTrim: TrimFn?
    private let fnGenerate: GenerateFn
    private let fnEncode: EncodeFn

    public let hiddenDim: Int
    public let numLayers: Int
    public let modelPath: String

    /// Where the engine dylib was actually loaded from (for provenance in traces).
    public let enginePath: String

    // MARK: - Discovery

    /// Candidate locations, most explicit first. Kept public so `vera compat`
    /// can report exactly what was searched without loading anything.
    public static func engineSearchPaths() -> [String] {
        var out: [String] = []
        if let env = ProcessInfo.processInfo.environment["JCROSS_ENGINE_DYLIB"], !env.isEmpty {
            out.append(env)
        }
        let fm = FileManager.default
        let cwd = fm.currentDirectoryPath
        let home = NSHomeDirectory()
        out.append(contentsOf: [
            "\(cwd)/Vendor/libjcross_engine_glm.dylib",
            "\(cwd)/libjcross_engine_glm.dylib",
            "\(home)/verantyx/cli/VerantyxIDE/Vendor/libjcross_engine_glm.dylib",
            "\(home)/Projects/verantyx-cli/jcross_engine_glm/target/release/libjcross_engine_glm.dylib",
            "/Applications/Verantyx.app/Contents/Frameworks/libjcross_engine_glm.dylib",
        ])
        return out
    }

    public static func locateEngine() -> String? {
        let fm = FileManager.default
        return engineSearchPaths().first { fm.fileExists(atPath: $0) }
    }

    // MARK: - Lifecycle

    public init(modelPath: String) throws {
        let searched = Self.engineSearchPaths()
        guard let dylibPath = Self.locateEngine() else {
            throw BackendError.engineNotFound(searched: searched)
        }
        guard let lib = dlopen(dylibPath, RTLD_NOW | RTLD_LOCAL) else {
            throw BackendError.engineNotFound(searched: searched)
        }
        self.library = lib
        self.enginePath = dylibPath

        func sym<T>(_ name: String, _ type: T.Type) throws -> T {
            guard let raw = dlsym(lib, name) else { throw BackendError.symbolMissing(name) }
            return unsafeBitCast(raw, to: type)
        }

        let create = try sym("jcross_engine_create", CreateFn.self)
        self.fnDestroy = try sym("jcross_engine_destroy", DestroyFn.self)
        self.fnReset = try sym("jcross_engine_reset", ResetFn.self)
        self.fnGenerate = try sym("jcross_engine_generate", GenerateFn.self)
        self.fnEncode = try sym("jcross_engine_encode", EncodeFn.self)
        let hiddenFn = try sym("jcross_engine_hidden_dim", DimFn.self)
        let layersFn = try sym("jcross_engine_num_layers", DimFn.self)
        // trim is an optimisation, not a contract — tolerate older engines.
        self.fnTrim = dlsym(lib, "jcross_engine_trim").map { unsafeBitCast($0, to: TrimFn.self) }

        guard let ptr = modelPath.withCString({ create($0) }) else {
            throw BackendError.loadFailed(path: modelPath)
        }
        self.handle = ptr
        self.modelPath = modelPath

        let dim = hiddenFn(ptr)
        let layers = layersFn(ptr)
        guard dim > 0, layers > 0 else {
            self.fnDestroy(ptr)
            throw BackendError.invalidDimensions
        }
        self.hiddenDim = Int(dim)
        self.numLayers = Int(layers)
    }

    deinit {
        fnDestroy(handle)
        dlclose(library)
    }

    // MARK: - Inference

    /// Clears the KV cache.
    ///
    /// The long-horizon design calls this before **every** forward: each turn
    /// is an independent short pass, and continuity lives in `GapStore` /
    /// `VectorMemory` rather than in accumulated attention state.
    public func reset() {
        fnReset(handle)
    }

    /// Releases composed-weight caches. Best-effort.
    public func trim() {
        fnTrim?(handle)
    }

    /// Greedy generation. Returns the produced token ids.
    public func generate(promptTokens: [UInt32], maxTokens: Int) throws -> [UInt32] {
        guard maxTokens > 0 else { return [] }
        var out = [UInt32](repeating: 0, count: maxTokens)
        let produced: Int32 = promptTokens.withUnsafeBufferPointer { inBuf in
            out.withUnsafeMutableBufferPointer { outBuf in
                fnGenerate(handle, inBuf.baseAddress, inBuf.count,
                           maxTokens,
                           outBuf.baseAddress, outBuf.count)
            }
        }
        guard produced >= 0 else {
            throw BackendError.ffi(function: "jcross_engine_generate", code: produced)
        }
        return Array(out.prefix(Int(produced)))
    }

    /// Hidden-state embedding for a token sequence — the same vector space the
    /// council and `VectorMemory` use. There is no second embedding model:
    /// JGEN's own hidden states are the memory index.
    public func encode(tokens: [UInt32]) throws -> [Float] {
        var out = [Float](repeating: 0, count: hiddenDim)
        let code: Int32 = tokens.withUnsafeBufferPointer { inBuf in
            out.withUnsafeMutableBufferPointer { outBuf in
                fnEncode(handle, inBuf.baseAddress, inBuf.count,
                         outBuf.baseAddress, outBuf.count)
            }
        }
        guard code >= 0 else {
            throw BackendError.ffi(function: "jcross_engine_encode", code: code)
        }
        return out
    }
}
