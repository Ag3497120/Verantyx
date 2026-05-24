import Foundation
import MLX
import MLXLLM
import MLXLMCommon
import CoreImage
import Hub

// MARK: - MLXRunner (Direct In-Process Inference)
//
// Loads the MLX model directly into the app process via MLXLMCommon.ModelContainer.
// No subprocess, no HTTP server, no port conflicts.
//
// generate() callback API:
//   ([Int]) -> GenerateDisposition  (.more | .stop)
//   Tokenizer.decode(tokens: [Int]) -> String  for piece decoding

// MARK: - MLX Popular Models

struct MLXModel: Identifiable, Hashable {
    let id: String
    let displayName: String
    let sizeGB: Double
    let tags: [String]

    var isDownloaded: Bool {
        let home  = FileManager.default.homeDirectoryForCurrentUser
        let cache = home.appendingPathComponent(".cache/huggingface/hub")
        let name  = "models--" + id.replacingOccurrences(of: "/", with: "--")
        return FileManager.default.fileExists(atPath: cache.appendingPathComponent(name).path)
    }
}

// MARK: - MLXRunner Actor

actor MLXRunner {

    static let shared = MLXRunner()

    /// Python-style HF Hub cache (pip install huggingface-hub)
    static let cacheDir: URL = {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".cache/huggingface/hub")
    }()

    /// Apple Swift Hub SDK cache (used by ModelConfiguration(id:))
    static let appleCacheDir: URL = {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Caches/models")
    }()

    /// Isolated patch directory — Hub can never overwrite configs here.
    static let patchedCacheDir: URL = {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".cache/verantyx/mlx-patched")
    }()

    static let popularModels: [MLXModel] = [
        MLXModel(id: "mlx-community/gemma-3-27b-it-4bit",
                 displayName: "Gemma 3 27B (4bit) ⭐ 推奨",
                 sizeGB: 18.0, tags: ["thinking", "stable", "recommended"]),
        MLXModel(id: "mlx-community/gemma-3-12b-it-4bit",
                 displayName: "Gemma 3 12B (4bit) — 軽量版",
                 sizeGB: 8.0, tags: ["fast"]),
        MLXModel(id: "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit",
                 displayName: "Qwen 2.5 Coder 7B — コード特化",
                 sizeGB: 4.5, tags: ["code", "fast"]),
        MLXModel(id: "mlx-community/Qwen2.5-Coder-32B-Instruct-4bit",
                 displayName: "Qwen 2.5 Coder 32B — 最高精度",
                 sizeGB: 20.0, tags: ["code", "large"]),
        MLXModel(id: "mlx-community/Mistral-7B-Instruct-v0.3-4bit",
                 displayName: "Mistral 7B Instruct",
                 sizeGB: 4.0, tags: ["fast", "general"]),
        MLXModel(id: "mlx-community/phi-4-4bit",
                 displayName: "Phi-4 (4bit) — Microsoft",
                 sizeGB: 8.5, tags: ["reasoning"]),
    ]

    // MARK: - Private state

    private var container: ModelContainer? = nil
    private(set) var currentModelId: String? = nil
    private(set) var isLoaded: Bool = false

    /// Persisted KV cache to enable zero-prefill generation across multiple turns.
    private var activeKVCache: [KVCache]? = nil
    /// The exact tokens that correspond to the state inside `activeKVCache`.
    private var activePromptTokens: [Int] = []

    /// Pending vocab_size overrides discovered from mismatchedSize errors.
    /// Key: modelId, Value: actual vocab_size from weight tensors.
    /// Applied during buildPatchedDirectory to inject into config.json.
    private var vocabSizeOverrides: [String: Int] = [:]

    // MARK: - KV Cache Guard
    // Tracks estimated tokens consumed in the current ModelContainer session.
    // When this crosses kvFlushThreshold, AgentLoop should aggressively compress
    // the conversation and signal that a new KV context is recommended.
    // Note: we count characters ÷ 4 as a rough token estimate (industry standard).
    private(set) var kvTokensConsumed: Int = 0

    /// Tier-aware KV flush threshold (characters ÷ 4 = tokens).
    /// Safe limits based on empirical M-series memory pressure testing:
    ///   - 16 GB Unified Memory: ~6,000 tokens before swap pressure
    ///   - 32 GB:               ~14,000 tokens
    ///   - 64 GB:               ~28,000 tokens
    /// We use a conservative 8,000-token default (= 32,000 chars) for safety.
    nonisolated var kvFlushThreshold: Int { 8_000 }

    /// Returns true when the KV cache is approaching its safe limit.
    /// AgentLoop should call this after each generation turn and, if true,
    /// aggressively compress then call resetKVCounter() before the next turn.
    func shouldFlushKVCache() -> Bool {
        kvTokensConsumed > kvFlushThreshold
    }

    /// Call after AgentLoop compresses the conversation to reset the KV estimate.
    func resetKVCounter() {
        kvTokensConsumed = 0
    }

    // MARK: - Thinking Budget
    // Maximum tokens allowed inside a <think>...</think> block.
    // Empirically, 600 tokens of thinking is sufficient for most coding tasks.
    // Beyond this the model tends to ruminate without adding value.
    nonisolated var maxThinkingTokens: Int { 600 }

    // MARK: - Load model

    /// Immediately release the model container from Unified Memory.
    /// After this call, isLoaded == false and currentModelId == nil.
    /// The MLX runtime's deinit path frees all GPU/ANE allocations.
    /// Call from a Task on MainActor: `await MLXRunner.shared.unloadModel()`
    func unloadModel() async {
        let name = currentModelId ?? "model"
        container = nil
        isLoaded = false
        currentModelId = nil
        kvTokensConsumed = 0
        activeKVCache = nil
        activePromptTokens = []
        // Notify UI on main thread via Notification (MLXRunner is actor, no SwiftUI import)
        let displayName = name.components(separatedBy: "/").last ?? name
        await MainActor.run {
            NotificationCenter.default.post(
                name: Notification.Name("MLXModelEjected"),
                object: nil,
                userInfo: ["modelName": displayName]
            )
        }
    }

    func loadModel(
        id modelId: String,
        hfToken: String? = nil,
        progressHandler: @escaping @Sendable (String) -> Void
    ) async throws {
        if currentModelId == modelId, isLoaded {
            await MainActor.run { progressHandler("✓ \(modelId) already loaded") }
            return
        }
        container = nil; isLoaded = false; currentModelId = nil
        activeKVCache = nil; activePromptTokens = []
        await MainActor.run { progressHandler("⟳ Loading \(modelId) into Unified Memory…") }

        var hub = defaultHubApi
        if let token = hfToken { hub = HubApi(hfToken: token) }

        // ── Patched-directory strategy ─────────────────────────────────────────
        //
        // PROBLEM: LLMModelFactory.loadContainer with ModelConfiguration(id:)
        // re-validates / re-downloads config.json from HuggingFace Hub on every
        // call, overwriting any blob-level patches we make. The upstream
        // config.json has fields (quantization.mode: "affine", 120+ per-layer
        // nested dicts) that MLXLMCommon's Codable QuantizationConfig cannot parse.
        //
        // SOLUTION: build a separate local directory (~/.cache/verantyx/mlx-patched/)
        // containing:
        //   • A plain-file, sanitized config.json (Hub can never overwrite this)
        //   • Symlinks → all weight blobs (no storage duplication)
        //
        // We then call loadContainer with ModelConfiguration(directory:) which reads
        // entirely from local disk — zero Hub network calls.
        //
        // FALLBACK: if the model is not yet downloaded (no HF cache snapshot exists),
        // we use ModelConfiguration(id:) for the initial download, then
        // immediately rebuild the patched directory for subsequent attempts.

        let maxAttempts = 4
        var attempt     = 0
        var lastError: Error? = nil

        while attempt < maxAttempts {
            let snap = attempt  // capture for closure

            // Build or retrieve patched directory. Returns nil if not cached yet.
            let mlxConfig: ModelConfiguration
            if let patchedDir = buildPatchedDirectory(modelId: modelId, log: progressHandler) {
                if snap == 0 {
                    await MainActor.run { progressHandler("📂 Loading from patched local directory…") }
                }
                mlxConfig = ModelConfiguration(directory: patchedDir)
            } else {
                await MainActor.run { progressHandler("📥 First download — fetching from Hub…") }
                mlxConfig = ModelConfiguration(id: modelId)
            }

            do {
                let loaded = try await LLMModelFactory.shared.loadContainer(
                    hub: hub, configuration: mlxConfig
                ) { progress in
                    let pct = Int(progress.fractionCompleted * 100)
                    Task { @MainActor in
                        progressHandler(snap == 0 ? "↓ \(pct)%" : "↓ Retry \(snap)… \(pct)%")
                    }
                }
                container = loaded; currentModelId = modelId; isLoaded = true
                let tag = snap == 0 ? "" : " (fixed in \(snap) attempt\(snap == 1 ? "" : "s"))"
                await MainActor.run { progressHandler("✅ \(modelId) loaded\(tag)") }
                return  // ── success ──

            } catch {
                let errMsg  = error.localizedDescription
                let debugMsg = String(describing: error)
                lastError  = error
                attempt   += 1

                await MainActor.run {
                    progressHandler("⚠️ Attempt \(snap + 1) failed: \(errMsg.prefix(160))")
                }

                // ── Handle vocab_size / tensor-shape mismatch ─────────────
                // MLX throws mismatchedSize when config.json's vocab_size
                // doesn't match the weight file's actual tensor dimensions.
                // Common with quantized Gemma models (64-token padding).
                //
                // We store the override in actor state so buildPatchedDirectory
                // can inject it on the next retry. Patching Hub-cached files
                // directly is futile because ModelConfiguration(id:) re-downloads
                // config.json from HuggingFace on every call.
                let fullMsg = errMsg + " " + debugMsg
                if let actualVocab = extractMismatchedVocabSize(from: fullMsg) {
                    vocabSizeOverrides[modelId] = actualVocab
                    await MainActor.run {
                        progressHandler("🔧 Detected vocab_size mismatch → will inject \(actualVocab) on retry")
                    }
                }

                // Invalidate patched-dir cache → forces rebuild on next iteration
                let patchedName = modelId.replacingOccurrences(of: "/", with: "--")
                let markerPath  = MLXRunner.patchedCacheDir
                    .appendingPathComponent(patchedName)
                    .appendingPathComponent(".openclaw_snapshot")
                try? FileManager.default.removeItem(at: markerPath)

                // Stop retrying on non-schema errors (network, OOM, etc.)
                let isSchemaError   = extractFailingKeyPath(from: fullMsg) != nil
                let isShapeMismatch = extractMismatchedVocabSize(from: fullMsg) != nil
                if !isSchemaError && !isShapeMismatch && attempt > 1 { break }
            }
        }

        // ── All attempts exhausted ──────────────────────────────────────────────
        let finalMsg = lastError?.localizedDescription ?? "unknown error"
        let debugMsg = lastError.map { String(describing: $0) } ?? ""
        await MainActor.run {
            progressHandler("❌ Load failed after \(attempt) attempt(s): \(finalMsg)")
            if !debugMsg.isEmpty && debugMsg != finalMsg {
                progressHandler("   Debug: \(debugMsg.prefix(400))")
            }
        }
        if let err = lastError { throw err }
    }

    // MARK: - Universal Config.json Sanitizer
    //
    // Philosophy: instead of knowing WHICH keys are problematic, we detect the
    // PATTERN that causes MLXLMCommon decoding failures and neutralize it.
    //
    // MLXLMCommon decodes config.json via Swift Codable. Its internal structs
    // (QuantizationConfig etc.) declare strict scalar types (Int/Double).
    // Any JSON value that contains a non-homogeneous type — e.g. a dict that
    // mixes `{"bits": 4}` with `{"layer.0.weight": {"bits": 8}}` — triggers:
    //   "Type mismatch at 'some_key'"
    //
    // Universal fix: for EVERY top-level key whose value is a dict,
    // isolate non-scalar entries (nested dicts, arrays, strings, bools) into
    // a `{key}_xtra` sibling key, which MLX never touches.
    // Array values for such keys are converted to empty dicts.
    //
    // Error-driven pass: parse "Type mismatch at 'a.b.c'" → fix key path 'a.b.c'.
    // This catches future unknown keys with zero code changes.

    // MARK: - Sanitize all config files for a model

    private func sanitizeAllConfigs(
        modelId: String,
        log: @Sendable (String) -> Void,
        force: Bool = false
    ) {
        let dirName  = "models--" + modelId.replacingOccurrences(of: "/", with: "--")
        let modelDir = MLXRunner.cacheDir.appendingPathComponent(dirName)

        let fm = FileManager.default
        guard fm.fileExists(atPath: modelDir.path) else { return }  // not cached yet — skip

        var configPaths: [URL] = []
        if let enumerator = fm.enumerator(at: modelDir,
                                           includingPropertiesForKeys: [.isRegularFileKey],
                                           options: [.skipsHiddenFiles]) {
            for case let file as URL in enumerator
                where file.lastPathComponent == "config.json" {
                configPaths.append(file)
            }
        }
        for path in configPaths {
            sanitizeSingleConfig(at: path, log: log, targetKeyPath: nil, force: force)
        }
    }

    // MARK: - Repair a specific key path (called after error-driven parsing)

    private func repairKeyPath(
        _ keyPath: [String],
        modelId: String,
        log: @Sendable (String) -> Void
    ) {
        let dirName  = "models--" + modelId.replacingOccurrences(of: "/", with: "--")
        let modelDir = MLXRunner.cacheDir.appendingPathComponent(dirName)

        let fm = FileManager.default
        if let enumerator = fm.enumerator(at: modelDir,
                                           includingPropertiesForKeys: [.isRegularFileKey],
                                           options: [.skipsHiddenFiles]) {
            for case let file as URL in enumerator
                where file.lastPathComponent == "config.json" {
                sanitizeSingleConfig(at: file, log: log, targetKeyPath: keyPath, force: true)
            }
        }
    }

    // MARK: - Model Source Directory Locator
    //
    // Apple's Swift Hub SDK (used by ModelConfiguration(id:)) stores models at:
    //   ~/Library/Caches/models/<org>/<model-name>/
    // Python's huggingface-hub stores at:
    //   ~/.cache/huggingface/hub/models--<org>--<model>/snapshots/<hash>/
    //
    // This method checks both locations and returns the first match.

    private func locateModelSourceDirectory(modelId: String) -> (dir: URL, snapshotId: String)? {
        let fm = FileManager.default

        // ── Strategy 1: Apple Swift Hub SDK cache ─────────────────────────
        // ~/Library/Caches/models/mlx-community/gemma-3-27b-it-4bit/
        let applePath = MLXRunner.appleCacheDir.appendingPathComponent(modelId)
        if fm.fileExists(atPath: applePath.appendingPathComponent("config.json").path) {
            // Use modification date of config.json as pseudo-snapshot ID
            let configURL = applePath.appendingPathComponent("config.json")
            let snapId: String
            if let attrs = try? fm.attributesOfItem(atPath: configURL.path),
               let date = attrs[.modificationDate] as? Date {
                snapId = "apple-\(Int(date.timeIntervalSince1970))"
            } else {
                snapId = "apple-unknown"
            }
            return (applePath, snapId)
        }

        // ── Strategy 2: Python HF Hub cache ───────────────────────────────
        // ~/.cache/huggingface/hub/models--mlx-community--gemma-3-27b-it-4bit/snapshots/<hash>/
        let dirName      = "models--" + modelId.replacingOccurrences(of: "/", with: "--")
        let snapshotsDir = MLXRunner.cacheDir.appendingPathComponent(dirName)
                                              .appendingPathComponent("snapshots")
        if fm.fileExists(atPath: snapshotsDir.path),
           let snaps = try? fm.contentsOfDirectory(at: snapshotsDir,
                                                     includingPropertiesForKeys: nil,
                                                     options: .skipsHiddenFiles),
           let firstSnap = snaps.first {
            return (firstSnap, firstSnap.lastPathComponent)
        }

        return nil  // model not downloaded yet
    }

    // MARK: - Patched Model Directory Builder
    //
    // Creates ~/.cache/verantyx/mlx-patched/<model>/ with:
    //   • Patched plain-file config.json (Hub can't overwrite this)
    //   • Symlinks → all model files (no storage duplication)
    //
    // A .openclaw_snapshot marker file tracks which source was used;
    // if the source changes (model updated), the dir is rebuilt.

    private func buildPatchedDirectory(
        modelId: String,
        log: @Sendable (String) -> Void
    ) -> URL? {
        let fm = FileManager.default

        // ── Locate model source (Apple cache or HF Hub cache) ─────────────
        guard let (sourceDir, currentSnap) = locateModelSourceDirectory(modelId: modelId)
        else { return nil }  // model not downloaded yet

        let patchedName  = modelId.replacingOccurrences(of: "/", with: "--")
        let patchedDir   = MLXRunner.patchedCacheDir.appendingPathComponent(patchedName)
        let markerURL    = patchedDir.appendingPathComponent(".openclaw_snapshot")

        // ── Cache hit: already built for this snapshot ─────────────────────
        if let existing = try? String(contentsOf: markerURL, encoding: .utf8),
           existing == currentSnap,
           fm.fileExists(atPath: patchedDir.appendingPathComponent("config.json").path),
           vocabSizeOverrides[modelId] == nil {  // no pending vocab_size fix
            return patchedDir
        }

        // ── (Re)build ──────────────────────────────────────────────────────
        log("🔧 Building patched model directory (source: \(currentSnap.prefix(12))…)")
        try? fm.removeItem(at: patchedDir)
        do {
            try fm.createDirectory(at: patchedDir, withIntermediateDirectories: true)
        } catch {
            log("⚠️ Cannot create patched dir: \(error.localizedDescription)")
            return nil
        }

        guard let files = try? fm.contentsOfDirectory(at: sourceDir,
                                                       includingPropertiesForKeys: nil,
                                                       options: .skipsHiddenFiles)
        else { return nil }

        // Symlink all files except config.json → real files (no data duplication)
        var configSourceURL: URL? = nil
        for file in files {
            let name = file.lastPathComponent
            if name.hasPrefix(".") { continue }
            if name == "config.json" { configSourceURL = file; continue }
            let dest = patchedDir.appendingPathComponent(name)
            if !fm.fileExists(atPath: dest.path) {
                try? fm.createSymbolicLink(at: dest,
                                           withDestinationURL: file.resolvingSymlinksInPath())
            }
        }

        // ── Read, sanitize, and write config.json as plain file ───────────
        guard let configSrc = configSourceURL,
              let data      = try? Data(contentsOf: configSrc.resolvingSymlinksInPath()),
              var json       = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else {
            log("⚠️ Cannot read source config.json")
            return nil
        }

        // Standard schema sanitization
        for key in json.keys.sorted() {
            sanitizeTopLevelKey(key, in: &json, force: true, log: log)
        }

        // ── Apply pending vocab_size override ─────────────────────────────
        // When a mismatchedSize error was detected in a previous attempt,
        // the actual vocab_size is stored in vocabSizeOverrides. Inject it
        // into BOTH top-level AND text_config to ensure the model architecture
        // matches the actual weight tensor dimensions.
        if let newVocab = vocabSizeOverrides[modelId] {
            log("🔧 Injecting vocab_size: \(newVocab) into config")
            json["vocab_size"] = newVocab
            if var textCfg = json["text_config"] as? [String: Any] {
                textCfg["vocab_size"] = newVocab
                json["text_config"]   = textCfg
            }
            vocabSizeOverrides.removeValue(forKey: modelId)
        }

        guard let patched = try? JSONSerialization.data(withJSONObject: json,
                                                        options: [.prettyPrinted, .sortedKeys])
        else { return nil }

        do {
            try patched.write(to: patchedDir.appendingPathComponent("config.json"))
            try currentSnap.write(to: markerURL, atomically: true, encoding: .utf8)
            log("✅ Patched config.json ready")
        } catch {
            log("⚠️ Cannot write patched config: \(error.localizedDescription)")
            return nil
        }

        return patchedDir
    }

    // MARK: - Core sanitizer (schema-agnostic)

    /// Sanitize one config.json.
    ///
    /// - Parameter targetKeyPath: if non-nil, ONLY fix that specific key path
    ///   (used for error-driven surgical repair). If nil, apply the full pre-pass
    ///   that scans every key.
    private func sanitizeSingleConfig(
        at configPath: URL,
        log: @Sendable (String) -> Void,
        targetKeyPath: [String]?,
        force: Bool
    ) {
        // ── Resolve symlink → patch the blob, not the pointer ─────────────────
        let realPath = configPath.resolvingSymlinksInPath()

        guard let data = try? Data(contentsOf: realPath) else {
            log("⚠️ Cannot read \(realPath.lastPathComponent)"); return
        }
        // Skip Git LFS pointer files
        if let preview = String(data: data.prefix(64), encoding: .utf8),
           preview.hasPrefix("version https://git-lfs") {
            return
        }
        guard var json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            log("⚠️ Cannot parse JSON at \(realPath.lastPathComponent)"); return
        }

        if !force && targetKeyPath == nil {
            let hasXtraResidue = json.keys.contains(where: { $0.hasSuffix("_xtra") })
            let eosIsClean     = !(json["eos_token_id"] is [Any])

            // Check BOTH quantization keys (gemma-4 uses "quantization", others use "quantization_config")
            let qcIsClean: Bool = {
                for qKey in ["quantization", "quantization_config"] {
                    guard let qc = json[qKey] as? [String: Any] else { continue }
                    // Dirty if any value is a nested dict (per-layer records) OR non-numeric scalar
                    if qc.values.contains(where: { v in
                        if v is [String: Any] { return true }
                        if !(v is Int) && !(v is Double) { return true }  // e.g. mode: "affine"
                        return false
                    }) { return false }
                }
                return true
            }()

            if !hasXtraResidue && eosIsClean && qcIsClean {
                return  // already clean — do not touch
            }
        }

        let displayPath = configPath == realPath
            ? configPath.deletingLastPathComponent().lastPathComponent
            : "\(configPath.deletingLastPathComponent().lastPathComponent) → blob"

        var changed = false

        if let kp = targetKeyPath {
            // ── Surgical mode: fix exactly one key path ─────────────────────
            changed = neutralizeAtKeyPath(kp, in: &json, log: log)
        } else {
            // ── Full pre-pass: scan every top-level key ─────────────────────
            for key in json.keys.sorted() {
                if sanitizeTopLevelKey(key, in: &json, force: force, log: log) {
                    changed = true
                }
            }
        }

        guard changed else { return }

        guard let patched = try? JSONSerialization.data(withJSONObject: json,
                                                        options: [.prettyPrinted, .sortedKeys])
        else { return }
        do {
            // HuggingFace Hub キャッシュの blob は read-only (444) で保存される。
            // write する前に書き込み権限を付与しないと無音で失敗する。
            let fm = FileManager.default
            if let attrs = try? fm.attributesOfItem(atPath: realPath.path),
               let perms = attrs[.posixPermissions] as? Int, perms & 0o200 == 0 {
                try? fm.setAttributes([.posixPermissions: perms | 0o200], ofItemAtPath: realPath.path)
            }
            try patched.write(to: realPath, options: [])   // non-atomic → keep inode for other symlinks
            log("🔧 config.json repaired → \(displayPath)")
        } catch {
            log("❌ Cannot write config.json: \(error.localizedDescription)")
        }
    }

    // MARK: - Sanitize a single top-level key (pre-pass logic)

    /// Fix the EXACT set of schema issues that cause MLXLMCommon Codable failures.
    ///
    /// Three transformations — applied in order:
    ///
    ///   0. `model_type` validation: unknown architectures (e.g. "gemma4") are
    ///      logged as warnings but NEVER remapped, because incompatible weight
    ///      shapes (MoE vs dense) cause shape mismatches at load time.
    ///   1. `architectures`: [String] → String  (MLX expects a single string)
    ///   2. `eos_token_id`: [Int] → Int         (first element; full list → _options)
    ///   3. `quantization` / `quantization_config`: nested per-layer dicts are
    ///      moved to a `_per_layer` sibling so the header {bits, group_size}
    ///      becomes a clean Codable QuantizationConfig.
    ///
    /// TEXT MODEL CONFIG BLOCKS (text_config, vision_config, audio_config, etc.)
    /// are NEVER modified — MLXLMCommon has its own typed structs for them.
    @discardableResult
    private func sanitizeTopLevelKey(
        _ key: String,
        in json: inout [String: Any],
        force: Bool,
        log: @Sendable (String) -> Void
    ) -> Bool {
        // ── Guard 1: never touch nested config blocks ────────────────────────
        // Exception: model_type inside text_config IS patched by Transform 0 below,
        // but we handle that inline rather than recursing here.
        let forbidden = ["vision_config", "audio_config",
                         "rope_scaling", "rotary_emb", "rope_parameters"]
        if forbidden.contains(key) { return false }

        // ── Guard 2: skip residue keys we already created ───────────────────
        if key.hasSuffix("_xtra") || key.hasSuffix("_per_layer") || key.hasSuffix("_options") {
            return false
        }

        // ── Transform 0: model_type validation ─────────────────────────────
        // Log a warning if the model_type is not registered in MLXLLM.
        // We intentionally do NOT remap unknown types (e.g. gemma4 → gemma3)
        // because different architectures have incompatible weight shapes
        // (MoE vs dense) that cause shape mismatch errors at load time.
        if key == "model_type", let currentType = json[key] as? String {
            let knownTypes: Set<String> = [
                "gemma3", "gemma3_text", "gemma3n_text",
                "llama", "mistral", "phi", "phi3", "phimoe",
                "qwen2", "qwen2_moe", "qwen2_vl", "qwen3",
                "starcoder2", "cohere", "cohere2",
                "deepseek_v3", "olmo", "olmo2", "olmoe",
                "falcon_h1", "granite_hybrid_moe",
                "internlm2", "openelm",
            ]
            if !knownTypes.contains(currentType) {
                log("⚠️ [pre-pass] Unknown model_type '\(currentType)' — MLXLLM may not support this architecture")
            }
            return false  // never modify model_type
        }


        // ── Transform 1: architectures [String] → String ────────────────────
        if key == "architectures", let arr = json[key] as? [String], !arr.isEmpty {
            json[key] = arr[0]
            log("\u{1F527} [pre-pass] 'architectures': [..] \u{2192} \(arr[0])")
            return true
        }

        // ── Transform 2: eos_token_id [Int] → Int ─────────────────────────
        if key == "eos_token_id", let arr = json[key] as? [Any], !arr.isEmpty {
            let optKey = key + "_options"
            if !force && json[optKey] != nil { return false }  // idempotent
            json[optKey] = arr as AnyObject
            json[key]    = arr[0]
            log("\u{1F527} [pre-pass] 'eos_token_id': [..] \u{2192} \(arr[0])")
            return true
        }

        // ── Transform 3: quantization{,_config} cleanup ────────────────────
        //
        //  MLXLMCommon の QuantizationConfig は Int/Double のスカラーのみ受け付ける。
        //  扱えない値を 2 種類に分離して別キーへ退避する:
        //
        //    a) ネスト dict (per-layer records)  → key_per_layer   (例: "layer.0.weight": {bits:8})
        //    b) 文字列 / bool / 配列             → key_xtra        (例: mode: "affine")
        //
        //  以前は (b) の場合 perLayer が空で return false していたため
        //  mode:"affine" のような文字列フィールドが除去されず
        //  "Type mismatch at 'quantization.mode'" が永続していた。
        let isQuantKey = (key == "quantization" || key == "quantization_config")
        if isQuantKey, let dict = json[key] as? [String: Any] {
            let perLayerKey = key + "_per_layer"
            let xtraKey     = key + "_xtra"
            // idempotent: 両方の退避キーが既存なら force なしではスキップ
            if !force && json[perLayerKey] != nil && json[xtraKey] != nil { return false }

            var header:   [String: Any] = [:]
            var perLayer: [String: Any] = [:]   // ネスト dict (per-layer records)
            var extra:    [String: Any] = [:]   // 文字列 / bool / 配列 (Type mismatch 原因)
            for (k, v) in dict {
                if v is [String: Any]           { perLayer[k] = v }
                else if v is Int || v is Double { header[k]   = v }
                else                            { extra[k]    = v }  // ← ここが今回の修正点
            }

            // 完全にクリーンな場合のみスキップ
            if perLayer.isEmpty && extra.isEmpty { return false }

            var didChange = false
            if !perLayer.isEmpty {
                json[key]         = header
                json[perLayerKey] = perLayer
                log("🔧 [pre-pass] '\(key)': split \(perLayer.count) per-layer entries → '\(perLayerKey)'")
                didChange = true
            }
            if !extra.isEmpty {
                // 文字列/bool フィールドを key_xtra へ退避（例: mode: "affine"）
                var xtra = (json[xtraKey] as? [String: Any]) ?? [:]
                for (k, v) in extra { xtra[k] = v }
                json[xtraKey] = xtra
                if !didChange { json[key] = header }  // perLayer なし時もヘッダーを差し替え
                log("🔧 [pre-pass] '\(key)': quarantined \(extra.count) non-numeric field(s) \(Array(extra.keys).sorted()) → '\(xtraKey)'")
                didChange = true
            }
            return didChange
        }

        return false  // nothing to do for this key
    }

    // MARK: - Surgical key-path neutralizer (error-driven)

    /// Navigate to `keyPath` inside `json` and neutralize the value there.
    /// Returns true if a change was made.
    @discardableResult
    private func neutralizeAtKeyPath(
        _ keyPath: [String],
        in json: inout [String: Any],
        log: @Sendable (String) -> Void
    ) -> Bool {
        guard !keyPath.isEmpty else { return false }

        if keyPath.count == 1 {
            // ── Leaf: neutralize the value directly ───────────────────────────
            let key = keyPath[0]
            guard let value = json[key] else { return false }
            let xtraKey = key + "_xtra"

            if let dict = value as? [String: Any] {
                let numeric    = dict.filter { $0.value is Int || $0.value is Double }
                let nonNumeric = dict.filter { !($0.value is Int) && !($0.value is Double) }
                json[key]     = numeric
                json[xtraKey] = nonNumeric
            } else if let arr = value as? [Any], !arr.isEmpty {
                // ── NEW: scalar array → first element (e.g. eos_token_id: [1,106,50]) ──
                json[xtraKey] = arr as AnyObject
                json[key]     = arr[0]   // expose primary scalar value
                log("🔧 [surgical] '\(keyPath.joined(separator: "."))': array[\(arr.count)] → first element")
                return true
            } else if let arr = value as? [Any] {
                json[key]     = [String: Any]()
                json[xtraKey] = arr
            } else {
                // String / Bool / other scalar in wrong context — quarantine it
                json[xtraKey] = json.removeValue(forKey: key)
            }
            log("🔧 [surgical] neutralized key path: '\(keyPath.joined(separator: "."))'")
            return true
        }

        // ── Interior node: recurse ────────────────────────────────────────────
        let head = keyPath[0]
        let tail  = Array(keyPath.dropFirst())
        guard var nested = json[head] as? [String: Any] else { return false }
        let changed = neutralizeAtKeyPath(tail, in: &nested, log: log)
        if changed { json[head] = nested }
        return changed
    }

    // MARK: - Error message key-path extractor

    /// Parse MLXLMCommon / Swift DecodingError messages to extract the
    /// failing key path as a `[String]` array.
    ///
    /// Handles all known error message formats:
    ///   • MLXLMCommon v0.x : "Type mismatch at 'key'"
    ///   • MLXLMCommon v1.x : "Type mismatch at 'key.subkey'"
    ///   • Swift Codable    : "... CodingKeys(stringValue: \"key\", …)"
    ///   • Generic fallback : first 'single-quoted' token in the message
    private func extractFailingKeyPath(from message: String) -> [String]? {
        // ── Pattern 1: "Type mismatch at 'a.b.c'" ────────────────────────────
        let p1 = #"[Tt]ype mismatch at '([^']+)'"#
        if let kp = firstCapture(pattern: p1, in: message) {
            return kp.components(separatedBy: ".")
        }

        // ── Pattern 2: "No value for key 'a.b'" / "Missing key 'a'" ──────────
        let p2 = #"(?:No value|Missing|Invalid) (?:for )?key '([^']+)'"#
        if let kp = firstCapture(pattern: p2, in: message) {
            return kp.components(separatedBy: ".")
        }

        // ── Pattern 3: Swift CodingKey description ────────────────────────────
        // e.g. "...at path: quantization_config → bits → ..."
        let p3 = #"at path: ([\w. →/_-]+)"#
        if let kp = firstCapture(pattern: p3, in: message) {
            let parts = kp.components(separatedBy: " → ")
                         .map { $0.trimmingCharacters(in: .whitespaces) }
                         .filter { !$0.isEmpty }
            if !parts.isEmpty { return parts }
        }

        // ── Pattern 4: CodingKeys stringValue extraction ──────────────────────
        // e.g. "CodingKeys(stringValue: \"quantization_config\", intValue: nil)"
        let p4 = #"stringValue: "([^"]+)""#
        // collect ALL matches — the last one is typically the deepest failing key
        var allKeys: [String] = []
        if let regex = try? NSRegularExpression(pattern: p4) {
            let range = NSRange(message.startIndex..., in: message)
            for match in regex.matches(in: message, range: range) {
                if let r = Range(match.range(at: 1), in: message) {
                    allKeys.append(String(message[r]))
                }
            }
        }
        if !allKeys.isEmpty { return allKeys }

        // ── Pattern 5: Any single-quoted token (last resort) ──────────────────
        let p5 = #"'([\w._-]+)'"#
        if let kp = firstCapture(pattern: p5, in: message) {
            return [kp]
        }

        return nil  // cannot parse — caller will do a full re-scan instead
    }

    // MARK: - Vocab Size Mismatch Detection

    /// Parse error messages for tensor-shape mismatches caused by vocab_size padding.
    /// Returns the actual vocab_size from the weight file, or nil if unrelated error.
    ///
    /// Handles these formats:
    ///   • "Mismatched parameter lm_head.weight … Actual [262208, 672], expected [262144, 672]"
    ///   • "mismatchedSize(… actualShape: [262208, 84], expectedShape: [262144, 84])"
    private func extractMismatchedVocabSize(from message: String) -> Int? {
        // Pattern: Actual [N, ...] vs expected [M, ...] where N and M differ in dim-0 only
        // MLX error format: "Actual [262208, 672], expected [262144, 672]"
        let p1 = #"[Aa]ctual\s*\[(\d+),\s*\d+\].*expected\s*\[(\d+),\s*\d+\]"#
        if let regex = try? NSRegularExpression(pattern: p1),
           let match = regex.firstMatch(in: message, range: NSRange(message.startIndex..., in: message)),
           match.numberOfRanges > 2,
           let r1 = Range(match.range(at: 1), in: message),
           let r2 = Range(match.range(at: 2), in: message),
           let actual = Int(message[r1]),
           let expected = Int(message[r2]),
           actual != expected {
            return actual
        }

        // Pattern: Swift debug repr: "actualShape: [262208, 84]"
        let p2 = #"actualShape:\s*\[(\d+)"#
        if let match = firstCapture(pattern: p2, in: message),
           let actual = Int(match) {
            // Also check the expected is different
            let p2e = #"expectedShape:\s*\[(\d+)"#
            if let exp = firstCapture(pattern: p2e, in: message),
               let expected = Int(exp), actual != expected {
                return actual
            }
        }

        return nil  // not a vocab_size mismatch
    }

    // MARK: - Vocab Size Patcher

    /// Update vocab_size in BOTH the HF cache config.json AND the patched directory.
    /// This ensures the model architecture matches the actual weight dimensions.
    private func patchVocabSizeInConfig(
        modelId: String,
        newVocabSize: Int,
        log: @Sendable (String) -> Void
    ) {
        let fm = FileManager.default

        // Collect all config.json paths to patch
        var configPaths: [URL] = []

        // 1. HF cache configs
        let dirName  = "models--" + modelId.replacingOccurrences(of: "/", with: "--")
        let modelDir = MLXRunner.cacheDir.appendingPathComponent(dirName)
        if let enumerator = fm.enumerator(at: modelDir,
                                           includingPropertiesForKeys: [.isRegularFileKey],
                                           options: [.skipsHiddenFiles]) {
            for case let file as URL in enumerator
                where file.lastPathComponent == "config.json" {
                configPaths.append(file)
            }
        }

        // 2. Patched directory config
        let patchedName = modelId.replacingOccurrences(of: "/", with: "--")
        let patchedConfig = MLXRunner.patchedCacheDir
            .appendingPathComponent(patchedName)
            .appendingPathComponent("config.json")
        if fm.fileExists(atPath: patchedConfig.path) {
            configPaths.append(patchedConfig)
        }

        for configPath in configPaths {
            let realPath = configPath.resolvingSymlinksInPath()
            guard let data = try? Data(contentsOf: realPath),
                  var json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
            else { continue }

            // Skip LFS pointer files
            if let preview = String(data: data.prefix(64), encoding: .utf8),
               preview.hasPrefix("version https://git-lfs") { continue }

            var changed = false

            // Patch top-level vocab_size
            if let current = json["vocab_size"] as? Int, current != newVocabSize {
                json["vocab_size"] = newVocabSize
                log("🔧 vocab_size: \(current) → \(newVocabSize)")
                changed = true
            }

            // Also patch vocab_size inside text_config (multimodal models)
            if var textCfg = json["text_config"] as? [String: Any],
               let current = textCfg["vocab_size"] as? Int, current != newVocabSize {
                textCfg["vocab_size"] = newVocabSize
                json["text_config"]   = textCfg
                log("🔧 text_config.vocab_size: \(current) → \(newVocabSize)")
                changed = true
            }

            guard changed,
                  let patched = try? JSONSerialization.data(withJSONObject: json,
                                                            options: [.prettyPrinted, .sortedKeys])
            else { continue }

            do {
                // Ensure write permissions on blob files
                if let attrs = try? fm.attributesOfItem(atPath: realPath.path),
                   let perms = attrs[.posixPermissions] as? Int, perms & 0o200 == 0 {
                    try? fm.setAttributes([.posixPermissions: perms | 0o200],
                                          ofItemAtPath: realPath.path)
                }
                try patched.write(to: realPath, options: [])
            } catch {
                log("⚠️ Cannot write vocab_size patch: \(error.localizedDescription)")
            }
        }
    }

    /// Helper: return the first capture group of a regex match, or nil.
    private func firstCapture(pattern: String, in text: String) -> String? {
        guard let regex = try? NSRegularExpression(pattern: pattern),
              let match = regex.firstMatch(in: text,
                                          range: NSRange(text.startIndex..., in: text)),
              match.numberOfRanges > 1,
              let range = Range(match.range(at: 1), in: text)
        else { return nil }
        return String(text[range])
    }


    // MARK: - Token-by-token streaming

    func streamGenerateTokens(
        prompt: String,
        images: [String]? = nil,
        maxTokens: Int = 4096,
        temperature: Double = 0.6,
        onToken: @escaping @Sendable (String) -> Void,
        onFinish: @escaping @Sendable (String) -> Void
    ) async throws {
        guard let box = container else { throw MLXError.notLoaded }

        // ── Anti-repetition GenerateParameters ───────────────────────────────
        // repetitionPenalty:     1.15 — penalises logits of already-seen tokens
        //                        (1.0 = no penalty; 1.1-1.3 is the practical range)
        // repetitionContextSize: 64   — sliding window of past tokens to inspect
        //                        (larger = catches longer phrase loops; default is 20)
        // maxKVSize: 4096 — 削除 (mlx-swift-examples の RotatingKVCache に
        //                   keep > idx 時にクラッシュするバグがあるため使用しない。
        //                   メモリ管理は AgentLoop の kvFlushThreshold で行う)
        // temperature:           caller-provided (default raised to 0.6 from 0.1;
        //                        near-zero temperatures are near-deterministic and
        //                        amplify repetition loops once one starts)
        let params = GenerateParameters(
            temperature: Float(temperature),
            repetitionPenalty: 1.15,
            repetitionContextSize: 64
        )
        var mlxImages: [UserInput.Image] = []
        if let base64Images = images {
            for b64 in base64Images {
                if let data = Data(base64Encoded: b64), let ciImage = CIImage(data: data) {
                    mlxImages.append(.ciImage(ciImage))
                }
            }
        }
        
        let userInput: UserInput
        if mlxImages.isEmpty {
            userInput = UserInput(prompt: prompt)
        } else {
            userInput = UserInput(prompt: prompt, images: mlxImages)
        }

        let currentCache = self.activeKVCache
        let currentPromptTokens = self.activePromptTokens

        let (newCache, newPromptTokens, finishPayload) = try await box.perform { (context: ModelContext) -> ([KVCache]?, [Int], String) in
            let lmInput: LMInput
            do {
                lmInput = try await context.processor.prepare(input: userInput)
            } catch {
                let ids = context.tokenizer.encode(text: prompt)
                lmInput = LMInput(tokens: .init(ids.map { Int32($0) }))
            }

            let fullTokens = lmInput.text.tokens.asArray(Int.self)
            var deltaTokens: [Int] = []
            var cacheToUse: [KVCache]? = nil

            // ── ZERO-PREFILL KV CACHE REUSE ────────────────────────────
            if let existingCache = currentCache, !currentPromptTokens.isEmpty {
                var matchCount = 0
                for i in 0..<min(fullTokens.count, currentPromptTokens.count) {
                    if fullTokens[i] == currentPromptTokens[i] {
                        matchCount += 1
                    } else { break }
                }

                if matchCount > 0 {
                    let trimAmount = currentPromptTokens.count - matchCount
                    if trimAmount > 0 {
                        for cache in existingCache {
                            cache.trim(trimAmount)
                        }
                    }
                    deltaTokens = Array(fullTokens.dropFirst(matchCount))
                    cacheToUse = existingCache
                } else {
                    deltaTokens = fullTokens
                    cacheToUse = context.model.newCache(parameters: params)
                }
            } else {
                deltaTokens = fullTokens
                cacheToUse = context.model.newCache(parameters: params)
            }

            // If deltaTokens is completely empty, we must at least evaluate the last token
            if deltaTokens.isEmpty, let last = fullTokens.last {
                deltaTokens = [last]
                if let cache = cacheToUse {
                    for c in cache { c.trim(1) } // Roll back one token so we can re-evaluate it
                }
            }

            let deltaInput = LMInput(tokens: MLXArray(deltaTokens.map { Int32($0) }))
            let iterator = try TokenIterator(
                input: deltaInput, model: context.model, cache: cacheToUse, parameters: params
            )

            var allTokens: [Int] = []

            // ── NUCLEAR Recompute-and-Diff ────────────────────────────────────
            //
            // PROBLEM HISTORY: Three previous incremental-decode approaches failed
            // because the tokenizer.decode(tokens:) + isValidUTF8 pipeline produced
            // unpredictable chunks. The isValidUTF8 extension was checking contiguous
            // storage (not UTF-8 validity), causing tokens to accumulate in buffers
            // and eventually emit large cumulative chunks.
            //
            // NUCLEAR FIX: Decode ALL tokens from scratch every callback.
            //   1. allTokens += newTokens
            //   2. fullDecode = tokenizer.decode(tokens: allTokens)  // authoritative
            //   3. cleanText  = strip <think>, </assistant>, etc.
            //   4. delta      = cleanText[emittedCharCount...]
            //   5. onToken(delta)
            //
            // Cost: O(n²) total over generation (n decode calls, each O(n) tokens).
            //       For 3K tokens at 40 tok/s: ~4.5M token-decodes ≈ 2-3s overhead
            //       over a 75s generation. NEGLIGIBLE vs inference cost.
            //
            // CORRECTNESS: Trivially correct — fullDecode is always the ground truth,
            //              emittedCharCount monotonically increases, delta is always fresh.
            var emittedCharCount  = 0    // # of clean chars already sent via onToken
            var thinkingChars     = 0
            let thinkBudget       = maxThinkingTokens
            var budgetExceeded    = false

            /// Strip all <think>…</think> blocks AND chat-template tags from `text`.
            /// Returns the clean visible text and whether it ends inside a think block.
            func stripForDisplay(_ text: String) -> (clean: String, insideThink: Bool) {
                // Phase 1: strip chat template close tags
                var s = text
                // Extended EOS list — covers all known model families:
                //   Gemma: <end_of_turn>  Llama-3: <|eot_id|>  ChatML/Qwen: <|im_end|>
                //   Generic: </s>  </assistant>  <eos>  Phi: <|end|>
                let eosTags = [
                    "</assistant>", "<|im_end|>", "<|eot_id|>",
                    "<end_of_turn>", "<eos>", "</s>", "<|end|>"
                ]
                for tag in eosTags {
                    s = s.replacingOccurrences(of: tag, with: "")
                }

                // Phase 2: strip <think>…</think> blocks
                var result = ""
                var remaining = s[s.startIndex...]
                var inThink = false

                while !remaining.isEmpty {
                    if !inThink {
                        if let openRange = remaining.range(of: "<think>") {
                            result += remaining[remaining.startIndex..<openRange.lowerBound]
                            remaining = remaining[openRange.upperBound...]
                            inThink = true
                        } else {
                            result += remaining
                            remaining = remaining[remaining.endIndex...]
                        }
                    } else {
                        if let closeRange = remaining.range(of: "</think>") {
                            remaining = remaining[closeRange.upperBound...]
                            inThink = false
                        } else {
                            // Unclosed think block — suppress everything after <think>
                            remaining = remaining[remaining.endIndex...]
                        }
                    }
                }
                return (result, inThink)
            }

            let result = MLXLMCommon.generate(
                input: deltaInput, context: context, iterator: iterator
            ) { newTokens -> GenerateDisposition in
                // ⚠️ MLXLMCommon delivers the CUMULATIVE token array on every
                // callback — NOT just the newly generated tokens. Using += would
                // double-accumulate each callback, causing exponential text growth
                // (the "snowball" duplicate bug). Use = (assignment) instead.
                allTokens = newTokens

                // ── Decode the authoritative cumulative token sequence ────
                let fullDecode = context.tokenizer.decode(tokens: allTokens)
                guard !fullDecode.isEmpty else {
                    return allTokens.count >= maxTokens ? .stop : .more
                }

                // ── Strip display artifacts ───────────────────────────────
                let (fullClean, currentlyInThink) = stripForDisplay(fullDecode)

                // Count thinking characters for budget enforcement
                thinkingChars = fullDecode.count - fullClean.count

                // ── Hold back tail to guard against partial tag prefixes ──
                let holdBack = currentlyInThink ? 0 : min(9, fullClean.count)
                let safeLen = fullClean.count - holdBack

                // ── Emit only the NEW delta ───────────────────────────────
                if safeLen > emittedCharCount {
                    let startIdx = fullClean.index(
                        fullClean.startIndex, offsetBy: emittedCharCount)
                    let endIdx = fullClean.index(
                        fullClean.startIndex, offsetBy: safeLen)
                    let delta = String(fullClean[startIdx..<endIdx])
                    emittedCharCount = safeLen
                    if !delta.isEmpty {
                        onToken(delta)
                    }
                }

                // ── EOS token early-stop ─────────────────────────────────
                // If the raw decoded text contains an EOS/chat-template sentinel,
                // stop generation immediately — don't wait for the tokenizer's
                // native EOS detection which may miss model-specific variants.
                let eosSignals = [
                    "<end_of_turn>", "<|eot_id|>", "<|im_end|>",
                    "<eos>", "</s>", "<|end|>"
                ]
                if eosSignals.contains(where: { fullDecode.contains($0) }) {
                    return .stop
                }

                // ── Thinking budget enforcement ────────────────────────────
                if thinkingChars > thinkBudget {
                    budgetExceeded = true
                    return .stop
                }

                return allTokens.count >= maxTokens ? .stop : .more
            }

            // ── Post-generation flush ─────────────────────────────────────
            // Emit any held-back tail text (the last ≤9 chars that were withheld).
            let finalDecode = context.tokenizer.decode(tokens: allTokens)
            let (finalClean, _) = stripForDisplay(finalDecode)
            if finalClean.count > emittedCharCount {
                let startIdx = finalClean.index(
                    finalClean.startIndex, offsetBy: emittedCharCount)
                let tail = String(finalClean[startIdx...])
                if !tail.isEmpty { onToken(tail) }
            }

            // Signal completion. onFinish carries the full raw output (including
            // <think> blocks) for artifact/memory parsing — NEVER shown in UI.
            let finishPayload = budgetExceeded
                ? result.output + "\n<!-- 💭 thinking budget reached -->"
                : result.output
            
            return (cacheToUse, fullTokens + result.tokens, finishPayload)
        }
        
        self.activeKVCache = newCache
        self.activePromptTokens = newPromptTokens
        onFinish(finishPayload)

        // ── KV Cache accounting ────────────────────────────────────────────
        // Rough estimate: prompt chars + generated output chars, divided by 4.
        kvTokensConsumed += (prompt.count + 500) / 4
    }

    // MARK: - Single-shot (blocking)

    func generate(
        prompt: String,
        images: [String]? = nil,
        maxTokens: Int = 2048,
        temperature: Double = 0.1
    ) async throws -> String {
        guard let box = container else { throw MLXError.notLoaded }
        // Same anti-repetition params as streamGenerateTokens
        let params = GenerateParameters(
            temperature: Float(temperature),
            repetitionPenalty: 1.15,
            repetitionContextSize: 64
        )
        var mlxImages: [UserInput.Image] = []
        if let base64Images = images {
            for b64 in base64Images {
                if let data = Data(base64Encoded: b64), let ciImage = CIImage(data: data) {
                    mlxImages.append(.ciImage(ciImage))
                }
            }
        }
        
        let userInput: UserInput
        if mlxImages.isEmpty {
            userInput = UserInput(prompt: prompt)
        } else {
            userInput = UserInput(prompt: prompt, images: mlxImages)
        }

        let currentCache = self.activeKVCache
        let currentPromptTokens = self.activePromptTokens

        let (newCache, newPromptTokens, finalOutput) = try await box.perform { (context: ModelContext) -> ([KVCache]?, [Int], String) in
            let lmInput: LMInput
            do {
                lmInput = try await context.processor.prepare(input: userInput)
            } catch {
                let ids = context.tokenizer.encode(text: prompt)
                lmInput = LMInput(tokens: .init(ids.map { Int32($0) }))
            }
            
            let fullTokens = lmInput.text.tokens.asArray(Int.self)
            var deltaTokens: [Int] = []
            var cacheToUse: [KVCache]? = nil

            if let existingCache = currentCache, !currentPromptTokens.isEmpty {
                var matchCount = 0
                for i in 0..<min(fullTokens.count, currentPromptTokens.count) {
                    if fullTokens[i] == currentPromptTokens[i] {
                        matchCount += 1
                    } else { break }
                }

                if matchCount > 0 {
                    let trimAmount = currentPromptTokens.count - matchCount
                    if trimAmount > 0 {
                        for cache in existingCache { cache.trim(trimAmount) }
                    }
                    deltaTokens = Array(fullTokens.dropFirst(matchCount))
                    cacheToUse = existingCache
                } else {
                    deltaTokens = fullTokens
                    cacheToUse = context.model.newCache(parameters: params)
                }
            } else {
                deltaTokens = fullTokens
                cacheToUse = context.model.newCache(parameters: params)
            }

            if deltaTokens.isEmpty, let last = fullTokens.last {
                deltaTokens = [last]
                if let cache = cacheToUse { for c in cache { c.trim(1) } }
            }

            let deltaInput = LMInput(tokens: MLXArray(deltaTokens.map { Int32($0) }))
            let iterator = try TokenIterator(
                input: deltaInput, model: context.model, cache: cacheToUse, parameters: params
            )

            var all: [Int] = []
            let result = MLXLMCommon.generate(
                input: deltaInput, context: context, iterator: iterator
            ) { tokens -> GenerateDisposition in
                all = tokens
                if all.count >= maxTokens { return .stop }
                
                // Decode only the last 20 tokens to prevent O(N^2) slowdown
                let recentTokens = Array(all.suffix(20))
                let text = context.tokenizer.decode(tokens: recentTokens)
                let eosSignals = [
                    "<end_of_turn>", "<|eot_id|>", "<|im_end|>",
                    "<eos>", "</s>", "<|end|>"
                ]
                if eosSignals.contains(where: { text.contains($0) }) {
                    return .stop
                }
                
                return .more
            }
            
            return (cacheToUse, fullTokens + result.tokens, result.output)
        }
        
        self.activeKVCache = newCache
        self.activePromptTokens = newPromptTokens
        return finalOutput
    }

    // MARK: - Download only (no load)

    func downloadModel(
        repoId: String,
        hfToken: String? = nil,
        onProgress: @escaping @Sendable (String) -> Void
    ) async throws {
        var hub = defaultHubApi
        if let token = hfToken { hub = HubApi(hfToken: token) }
        let config = ModelConfiguration(id: repoId)
        await MainActor.run { onProgress("↓ Fetching \(repoId)…") }
        _ = try await LLMModelFactory.shared.loadContainer(hub: hub, configuration: config) { p in
            let pct = Int(p.fractionCompleted * 100)
            Task { @MainActor in onProgress("↓ \(repoId)  \(pct)%") }
        }
        await MainActor.run { onProgress("✅ Download complete: \(repoId)") }
    }
}

// MARK: - Errors

enum MLXError: Error, LocalizedError {
    case notLoaded
    case downloadFailed(String)

    var errorDescription: String? {
        switch self {
        case .notLoaded:             return "MLX model not loaded."
        case .downloadFailed(let m): return "Download failed: \(m)"
        }
    }
}
