import Foundation

/// Decides how the engine runs, and says so out loud.
///
/// The engine reads its device and cache settings from process environment
/// variables. The CLI previously set none of them, which had two consequences
/// that were invisible from the outside:
///
///  1. **Hybrid models always ran on CPU.** `gpu_enabled()` treats the Metal
///     path for Gated DeltaNet as opt-in (`JCROSS_HYBRID_GPU=1`) until it is
///     stable. Unset means off — so the Qwen3.6 family, the published target,
///     silently took the slow path.
///  2. **Large models thrashed the weight cache.** The default budget is 8 GB;
///     composing a 6.3 GB f16 model to f32 needs roughly twice that, so weights
///     were evicted and recomposed continuously. A 3B run produced no output
///     for over half an hour.
///
/// Neither is a crash, and neither is visible unless you go looking — which is
/// exactly why the decision is now made explicitly and emitted into the trace.
public struct DevicePolicy: Sendable {

    public enum Device: String, Sendable { case metal, cpu }

    public let device: Device
    public let cacheGB: Double
    /// Metal for the Gated DeltaNet mixed path. Separate from `device` because
    /// the engine gates it separately.
    public let hybridOnGPU: Bool
    public let reason: String

    /// Filename markers for weights too large to compose comfortably.
    /// Deliberately excludes the small-model markers so "0.5b" is not caught
    /// by a substring match on "5b".
    static func looksLarge(_ name: String) -> Bool {
        let n = name.lowercased()
        for small in ["0.5b", "0_5b", "0.8b", "1.5b", "2b", "3b"] where n.contains(small) {
            return false
        }
        return ["7b", "8b", "9b", "12b", "13b", "14b", "26b", "27b", "32b", "70b", "e4b"]
            .contains { n.contains($0) }
    }

    public static func decide(
        modelPath: String,
        isHybrid: Bool,
        weightBytes: Int64,
        ramGB: Double = Double(ProcessInfo.processInfo.physicalMemory) / Double(1 << 30)
    ) -> DevicePolicy {
        let env = ProcessInfo.processInfo.environment
        let name = URL(fileURLWithPath: modelPath).lastPathComponent
        let weightGB = Double(weightBytes) / Double(1 << 30)

        // Composing f16 weights to f32 roughly doubles them; give the cache
        // enough room to hold the working set instead of evicting every token,
        // but never more than the machine can spare.
        let wanted = max(2.0, weightGB * 2.2)
        let ceiling = max(2.0, ramGB * 0.5)
        var cacheGB = min(wanted, ceiling)
        if let override = env["JCROSS_CACHE_GB"], let g = Double(override), g > 0 {
            cacheGB = g
        }

        // An explicit request wins, and is reported as such — a policy that
        // quietly overrides the operator is its own kind of dishonesty.
        if env["JCROSS_DEVICE"]?.lowercased() == "cpu" || env["JCROSS_GPU"] == "0" {
            return DevicePolicy(device: .cpu, cacheGB: cacheGB, hybridOnGPU: false,
                                reason: "CPU forced by JCROSS_DEVICE/JCROSS_GPU",
                                hybridForcedToCPU: false)
        }
        let forceMetal = env["JCROSS_FORCE_METAL"] == "1"
        let forceHybridGPU = env["JCROSS_HYBRID_GPU"] == "1"

        if isHybrid && !(forceHybridGPU || forceMetal) {
            return DevicePolicy(
                device: .metal, cacheGB: cacheGB, hybridOnGPU: false,
                reason: "hybrid (Gated DeltaNet): engine keeps the Metal path opt-in, so the "
                      + "forward runs on CPU — set JCROSS_HYBRID_GPU=1 to try it",
                hybridForcedToCPU: true
            )
        }

        if Self.looksLarge(name), !forceMetal, weightGB * 2.2 > ramGB * 0.6 {
            return DevicePolicy(
                device: .cpu, cacheGB: cacheGB, hybridOnGPU: false,
                reason: String(format: "%.1f GB weights on %.0f GB RAM — CPU to avoid Metal OOM "
                               + "(JCROSS_FORCE_METAL=1 to override)", weightGB, ramGB),
                hybridForcedToCPU: false
            )
        }

        return DevicePolicy(
            device: .metal, cacheGB: cacheGB, hybridOnGPU: isHybrid,
            reason: String(format: "Metal, weight cache %.1f GB for %.1f GB weights on %.0f GB RAM",
                           cacheGB, weightGB, ramGB),
            hybridForcedToCPU: false
        )
    }

    /// Applies the decision to the environment the engine reads at load time.
    /// Must be called **before** constructing `JGenBackend`.
    public func apply() {
        setenv("JCROSS_DEVICE", device.rawValue, 1)
        setenv("JCROSS_GPU", device == .cpu ? "0" : "1", 1)
        setenv("JCROSS_HYBRID_GPU", hybridOnGPU ? "1" : "0", 1)
        setenv("JCROSS_CACHE_GB", String(format: "%.2f", cacheGB), 1)
    }

    /// True when the model is a hybrid whose Metal path is disabled — the
    /// Metal device is still initialised, but the forward runs on CPU.
    public let hybridForcedToCPU: Bool

    /// Where the forward actually runs.
    ///
    /// Reporting `metal` because a Metal device exists, while the Gated
    /// DeltaNet forward runs on CPU, is precisely the kind of "technically
    /// true" status line that makes a half-hour run inexplicable. This
    /// collapses to what the tokens are computed on.
    public var effectiveDevice: Device {
        hybridForcedToCPU ? .cpu : device
    }

    public var summary: String {
        "\(effectiveDevice.rawValue)\(hybridOnGPU ? "+hybrid-gpu" : "") — \(reason)"
    }
}
