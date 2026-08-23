import Foundation

/// Mitigations for Apple Silicon unified-memory / IOGPU panics.
///
/// Observed failure mode (M1 Pro / AGXG13X): WindowServer kernel panic
/// `pending memory object unexpectedly found in non pending hash`
/// (`IOGPUGroupMemory.cpp`) while Verantyx simultaneously holds a JGEN
/// Metal graph, refreshes the Act mirror via `CGWindowListCreateImage`,
/// and runs Vera-a / council / EternalMemory encodes.
///
/// Strategy:
/// 1. Pause WindowServer-facing capture while JGEN is loading or inferring.
/// 2. Prefer CPU for JGEN on ≤18 GB machines (or when mirror is live) unless
///    the user forces Metal via `JCROSS_FORCE_METAL=1`.
/// 3. Cap composed-weight cache (`JCROSS_CACHE_GB`) and council fan-out.
/// 4. Surface a clear reason string for the load toast / system log.
/// 5. With `CouncilSettingsStore.vectorOnlySense` (default ON), Act/sense
///    tools skip JPEG capture for the model — fewer WindowServer captures
///    compete with Metal (mirror UI may still refresh independently).
enum JGenGPUSafety {

    struct Decision: Sendable {
        enum Device: String, Sendable { case metal, cpu }

        let device: Device
        let cacheGB: Double
        let maxCouncilRoles: Int
        let maxCouncilRounds: Int
        let maxGenTokens: Int
        let allowEternalEncode: Bool
        let reasonEN: String
        let reasonJA: String

        var deviceLabel: String {
            switch device {
            case .metal: return "Metal"
            case .cpu: return "CPU"
            }
        }

        var loadMessageEN: String {
            "JGEN loaded on \(deviceLabel) (\(reasonEN))"
        }

        var loadMessageJA: String {
            "JGEN を \(deviceLabel) でロード（\(reasonJA)）"
        }
    }

    // MARK: - Capture quiet latch (sync; readable from MainActor refresh loops)

    private static let latch = NSLock()
    private static var criticalDepth = 0
    private static var loadInFlight = false

    /// True while JGEN load / forward must not compete with WindowServer IOGPU.
    static var shouldPauseWindowServerCapture: Bool {
        latch.lock()
        defer { latch.unlock() }
        return criticalDepth > 0 || loadInFlight
    }

    static func beginCriticalGPUWork() {
        latch.lock()
        criticalDepth += 1
        latch.unlock()
    }

    static func endCriticalGPUWork() {
        latch.lock()
        criticalDepth = max(0, criticalDepth - 1)
        latch.unlock()
    }

    static func beginModelLoad() {
        latch.lock()
        loadInFlight = true
        latch.unlock()
    }

    static func endModelLoad() {
        latch.lock()
        loadInFlight = false
        latch.unlock()
    }

    // MARK: - Last decision (for UI / council caps)

    private static let decisionLock = NSLock()
    private static var _lastDecision: Decision?
    private static var _lastModelName: String?

    static var lastDecision: Decision? {
        decisionLock.lock(); defer { decisionLock.unlock() }
        return _lastDecision
    }

    static var lastModelName: String? {
        decisionLock.lock(); defer { decisionLock.unlock() }
        return _lastModelName
    }

    static func remember(model: String, decision: Decision) {
        decisionLock.lock()
        _lastModelName = model
        _lastDecision = decision
        decisionLock.unlock()
    }

    static func clearRemembered() {
        decisionLock.lock()
        _lastModelName = nil
        _lastDecision = nil
        decisionLock.unlock()
    }

    // MARK: - Policy

    /// Apply process-wide env the Rust dylib reads at `jcross_engine_create`.
    /// Call **before** constructing `JCrossEngine`.
    @discardableResult
    static func prepareEnvironmentForLoad(
        modelFileName: String,
        mirrorWatching: Bool,
        profile: MachineProfile = .current()
    ) -> Decision {
        let decision = decide(
            modelFileName: modelFileName,
            mirrorWatching: mirrorWatching,
            profile: profile
        )
        apply(decision, modelFileName: modelFileName)
        remember(model: modelFileName, decision: decision)
        return decision
    }

    static func decide(
        modelFileName: String,
        mirrorWatching: Bool,
        profile: MachineProfile
    ) -> Decision {
        let env = ProcessInfo.processInfo.environment
        let forceMetal = env["JCROSS_FORCE_METAL"] == "1"
        let forceCPU = env["JCROSS_DEVICE"]?.lowercased() == "cpu"
            || env["JCROSS_GPU"] == "0"

        let lowRAM = profile.totalRAMGB <= 18.0
        let tightRAM = profile.totalRAMGB <= 24.0
        let looksLarge = Self.modelLooksLarge(modelFileName)

        // Default cache: keep composed f32 weights from pinning the whole Mac.
        // 0.5B fits in ~1–2 GB; larger models stream via FIFO eviction.
        var cacheGB: Double
        if lowRAM {
            cacheGB = looksLarge ? 1.5 : 2.0
        } else if tightRAM {
            // With f16-on-Metal dense weights, mid-size 2B–4B (~6–8 GB) fit
            // without doubling to f32. Keep headroom for KV + activations.
            cacheGB = looksLarge ? 3.0 : 8.0
        } else {
            cacheGB = looksLarge ? 6.0 : min(14.0, max(6.0, profile.usableModelRAMGB * 0.4))
        }
        if let override = env["JCROSS_CACHE_GB"], let g = Double(override), g > 0 {
            cacheGB = g
        }

        let maxRoles: Int
        let maxRounds: Int
        let maxGenTokens: Int
        let allowEternal: Bool
        if lowRAM || (mirrorWatching && tightRAM) {
            maxRoles = 2
            maxRounds = 2
            maxGenTokens = 768
            allowEternal = !looksLarge
        } else if tightRAM {
            maxRoles = 3
            maxRounds = 3
            maxGenTokens = 1_536
            allowEternal = true
        } else {
            maxRoles = 5
            maxRounds = 5
            maxGenTokens = 2_048
            allowEternal = true
        }

        if forceCPU {
            return Decision(
                device: .cpu,
                cacheGB: cacheGB,
                maxCouncilRoles: maxRoles,
                maxCouncilRounds: maxRounds,
                maxGenTokens: maxGenTokens,
                allowEternalEncode: allowEternal,
                reasonEN: "JCROSS_DEVICE/GPU forces CPU — avoids Metal/IOGPU pressure",
                reasonJA: "JCROSS_DEVICE/GPU により CPU 強制（Metal/IOGPU 圧迫を回避）"
            )
        }

        // Quantized model that fits: Metal, no debate. The composed-weight
        // cache is irrelevant to it (QMatMul holds blocks directly), the
        // f16-era OOM classes cannot happen at its size, and the hybrid GDN
        // projections run through the same QMatMul — so the engine's mixed
        // path is enabled rather than suppressed. 0.7 leaves headroom for KV
        // and the window server on unified memory.
        if let facts = modelFacts(fileName: modelFileName), facts.quantized,
           facts.sizeGB <= profile.totalRAMGB * 0.7 {
            return Decision(
                device: .metal,
                cacheGB: max(2.0, cacheGB),
                maxCouncilRoles: maxRoles,
                maxCouncilRounds: maxRounds,
                maxGenTokens: maxGenTokens,
                allowEternalEncode: allowEternal,
                reasonEN: String(format: "quantized %.1f GB fits %.0f GB unified memory — Metal, resident",
                                 facts.sizeGB, profile.totalRAMGB),
                reasonJA: String(format: "量子化 %.1f GB は統合メモリ %.0f GB に常駐可 — Metal",
                                 facts.sizeGB, profile.totalRAMGB)
            )
        }

        if forceMetal {
            return Decision(
                device: .metal,
                cacheGB: cacheGB,
                maxCouncilRoles: maxRoles,
                maxCouncilRounds: maxRounds,
                maxGenTokens: maxGenTokens,
                allowEternalEncode: allowEternal,
                reasonEN: "JCROSS_FORCE_METAL=1 — user override",
                reasonJA: "JCROSS_FORCE_METAL=1 — ユーザー指定"
            )
        }

        // IOGPU panic class was observed on ≤18 GB with live mirror + Metal.
        // Capture is already paused via beginCriticalGPUWork / beginModelLoad —
        // on ample-RAM Macs keep Metal for mid-size models so converted JGENs
        // are not silently stuck on a slow CPU path whenever Act is open.
        if mirrorWatching && (lowRAM || (tightRAM && looksLarge)) {
            return Decision(
                device: .cpu,
                cacheGB: cacheGB,
                maxCouncilRoles: maxRoles,
                maxCouncilRounds: maxRounds,
                maxGenTokens: maxGenTokens,
                allowEternalEncode: allowEternal,
                reasonEN: "Act mirror + tight unified memory — CPU path to avoid WindowServer/IOGPU panic",
                reasonJA: "Actミラー＋統合メモリ逼迫 — WindowServer/IOGPU panic回避のため CPU"
            )
        }

        if lowRAM {
            return Decision(
                device: .cpu,
                cacheGB: cacheGB,
                maxCouncilRoles: maxRoles,
                maxCouncilRounds: maxRounds,
                maxGenTokens: maxGenTokens,
                allowEternalEncode: allowEternal,
                reasonEN: String(format: "%.0f GB unified memory — safe CPU default (set JCROSS_FORCE_METAL=1 to override)", profile.totalRAMGB),
                reasonJA: String(format: "統合メモリ %.0f GB — 安全のため CPU 既定（Metal は JCROSS_FORCE_METAL=1）", profile.totalRAMGB)
            )
        }

        // Large weights on exactly-24 GB machines: prefer CPU unless the user
        // overrides. Mid-size (≤~4B / non-marker names) fall through to Metal.
        if looksLarge && tightRAM {
            return Decision(
                device: .cpu,
                cacheGB: cacheGB,
                maxCouncilRoles: maxRoles,
                maxCouncilRounds: maxRounds,
                maxGenTokens: maxGenTokens,
                allowEternalEncode: false,
                reasonEN: "Large .jgen on ≤24 GB RAM — CPU to avoid Metal OOM / IOGPU panic",
                reasonJA: "大容量 .jgen かつ RAM≤24GB — Metal OOM/IOGPU panic回避のため CPU"
            )
        }

        let mirrorNote = mirrorWatching ? ", Act mirror open (capture paused)" : ""
        let mirrorNoteJA = mirrorWatching ? "、Actミラー開（キャプチャ一時停止）" : ""
        return Decision(
            device: .metal,
            cacheGB: cacheGB,
            maxCouncilRoles: maxRoles,
            maxCouncilRounds: maxRounds,
            maxGenTokens: maxGenTokens,
            allowEternalEncode: allowEternal,
            reasonEN: String(format: "Metal OK (%.0f GB RAM, cache %.1f GB%@)", profile.totalRAMGB, cacheGB, mirrorNote),
            reasonJA: String(format: "Metal 利用（RAM %.0f GB、キャッシュ %.1f GB%@）", profile.totalRAMGB, cacheGB, mirrorNoteJA)
        )
    }

    private static func apply(_ decision: Decision, modelFileName: String) {
        // Respect an explicit JCROSS_DEVICE already set by the developer shell
        // only when it matches the decision; otherwise overwrite for this load.
        setenv("JCROSS_DEVICE", decision.device.rawValue, 1)
        setenv("JCROSS_CACHE_GB", String(format: "%.2f", decision.cacheGB), 1)
        // Hybrid GDN: allow Metal mixed path when the device decision is
        // already Metal and the model is mid-size. Keep it off on CPU loads
        // and for large markers (7B+/e4b) where IOGPU spikes are riskiest.
        // Always set (overwrite) so a prior CPU load cannot leave HYBRID_GPU=0
        // sticky across a subsequent Metal mid-size load in the same process.
        if ProcessInfo.processInfo.environment["JCROSS_HYBRID_GPU_LOCK"] != "1" {
            // Quantized: the engine's own default is correct (mixed path on),
            // and setting "0" here would override it — unset instead of
            // guessing. f16: the old rule stands.
            if modelFacts(fileName: modelFileName)?.quantized == true {
                unsetenv("JCROSS_HYBRID_GPU")
            } else {
                let hybridGPU = decision.device == .metal && !Self.modelLooksLarge(modelFileName)
                setenv("JCROSS_HYBRID_GPU", hybridGPU ? "1" : "0", 1)
            }
        }
        // Never silently thrash Metal→CPU mid-forward on pressure Macs:
        // prefer a visible failure / CPU-from-start over WindowServer death.
        if decision.device == .cpu {
            setenv("JCROSS_GPU", "0", 1)
        } else {
            setenv("JCROSS_GPU", "1", 1)
        }
    }

    /// What the model actually is, read from disk — not guessed from its name.
    ///
    /// The name heuristic ("27b" in the filename → large → CPU) was right for
    /// f16 files and exactly wrong for quantized ones: a requantized 27B is
    /// ~17 GB and belongs on Metal, but its name still says 27b, so it was
    /// sentenced to the CPU path by a substring match. Size and quantization
    /// are both knowable in microseconds; guess neither.
    struct ModelFacts {
        let sizeGB: Double
        let quantized: Bool
    }

    static func modelFacts(fileName: String) -> ModelFacts? {
        let url = JGenPaths.convertedModelsDir.appendingPathComponent(fileName)
        guard let attrs = try? FileManager.default.attributesOfItem(atPath: url.path),
              let bytes = attrs[.size] as? UInt64 else { return nil }
        // The requantizer stamps "quantized": true into the sidecar.
        var quant = false
        if let d = try? Data(contentsOf: URL(fileURLWithPath: url.path + ".meta.json")),
           let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any] {
            quant = (j["quantized"] as? Bool) ?? false
        }
        return ModelFacts(sizeGB: Double(bytes) / Double(1 << 30), quantized: quant)
    }

    /// Heuristic from filename only (no weight I/O).
    static func modelLooksLarge(_ name: String) -> Bool {
        let n = name.lowercased()
        if n.contains("0.5b") || n.contains("0_5b") || n.contains("0.8b") || n.contains("1.5b") {
            return false
        }
        let markers = ["7b", "8b", "9b", "12b", "13b", "14b", "26b", "27b", "32b", "35b", "70b", "e4b", "a3b", "a4b"]
        return markers.contains { n.contains($0) }
    }

    /// Effective council role cap given the last load decision.
    static func cappedCouncilRoles(requested: Int) -> Int {
        let cap = lastDecision?.maxCouncilRoles ?? fallbackMaxRoles
        return min(max(requested, 2), cap)
    }

    /// Cap deliberation rounds under unified-memory pressure.
    static func cappedCouncilRounds(requested: Int) -> Int {
        let cap = lastDecision?.maxCouncilRounds ?? fallbackMaxRounds
        return min(max(requested, 1), cap)
    }

    /// Cap generate maxTokens so Vera harness / AgentLoop cannot ask for a
    /// multi-k decode residency window on tight Macs.
    static func cappedMaxTokens(_ requested: Int) -> Int {
        // An explicit user override outranks the RAM heuristics — the user
        // asked for every ceiling to yield to the manual setting, and a cap
        // that silently shrinks a requested budget is exactly the "manual
        // setting doesn't take" bug.
        if UserDefaults.standard.integer(forKey: "max_tokens_override") > 0 {
            return max(requested, 64)
        }
        let cap = lastDecision?.maxGenTokens ?? fallbackMaxGenTokens
        return min(max(requested, 64), cap)
    }

    static var allowEternalEncode: Bool {
        lastDecision?.allowEternalEncode ?? true
    }

    /// When no model has been loaded yet, derive conservative caps from RAM.
    private static var fallbackMaxRoles: Int {
        let ram = MachineProfile.current().totalRAMGB
        if ram <= 18 { return 2 }
        if ram <= 24 { return 3 }
        return 5
    }

    private static var fallbackMaxRounds: Int {
        let ram = MachineProfile.current().totalRAMGB
        if ram <= 18 { return 2 }
        if ram <= 24 { return 3 }
        return 5
    }

    private static var fallbackMaxGenTokens: Int {
        let ram = MachineProfile.current().totalRAMGB
        if ram <= 18 { return 768 }
        if ram <= 24 { return 1_536 }
        return 2_048
    }
}
