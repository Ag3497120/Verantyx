import Foundation

/// Pre-flight compatibility report for a `.jgen` model.
///
/// This is the *only* component with an opinion about which architectures are
/// "supported". The runtime itself (`JGenBackend`, `LongHorizonRunner`) is
/// model-agnostic by design — the whole claim of this project is that the
/// agent's experience lives outside the model, so hard-coding one model into
/// the runtime would undercut it.
///
/// The report deliberately separates what was **checked** from what was
/// **verified by running**. Parsing a config is not the same as producing a
/// correct token, and saying so is the difference between a preview and a
/// false claim of support.
public struct ModelCompat: Sendable {

    /// How much of this model has actually been exercised, not just parsed.
    public enum Tier: String, Sendable {
        /// Architecture is the headline target and has been run end to end.
        case validated
        /// Engine understands the architecture; this project has not
        /// published an end-to-end run for it.
        case experimental
        /// Parses, but the architecture family is outside what the engine
        /// implements — loading will likely fail in Rust.
        case unsupported
    }

    public struct Check: Sendable {
        public let name: String
        public let passed: Bool
        public let detail: String
        public init(name: String, passed: Bool, detail: String) {
            self.name = name
            self.passed = passed
            self.detail = detail
        }
    }

    public let modelPath: String
    /// True when a sidecar `meta.json` was found and parsed. The raw dictionary
    /// is intentionally not stored — nothing downstream needs it, and holding
    /// `[String: Any]` would make this type only nominally `Sendable`.
    public let hasMeta: Bool
    public let tier: Tier
    public let architecture: String
    public let checks: [Check]
    public let weightBytes: Int64
    public let estimatedResidentGB: Double
    public let machineRAMGB: Double
    public let notes: [String]

    // MARK: - Validated targets

    /// Headline targets. Qwen3.6-27B is the model this runtime is being
    /// published against; Qwen3.8 is the intended second-stage swap test.
    /// Membership here is a claim about *evidence*, not about capability.
    public static let validatedArchitectures: Set<String> = ["qwen35", "qwen35moe", "qwen3next"]

    /// Architectures the Rust engine implements a forward pass for.
    public static let engineArchitectures: Set<String> = [
        "standard", "moe_standard", "hybrid_ssm",
    ]

    // MARK: - Inspection

    public static func inspect(modelPath: String) -> ModelCompat {
        let fm = FileManager.default
        var checks: [Check] = []
        var notes: [String] = []

        let modelExists = fm.fileExists(atPath: modelPath)
        checks.append(Check(
            name: "Model file present",
            passed: modelExists,
            detail: modelExists ? modelPath : "not found: \(modelPath)"
        ))

        let metaPath = modelPath + ".meta.json"
        var meta: [String: Any]? = nil
        if let data = fm.contents(atPath: metaPath),
           let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            meta = obj
        }
        checks.append(Check(
            name: "Sidecar meta.json",
            passed: meta != nil,
            detail: meta != nil ? metaPath : "missing: \(metaPath)"
        ))

        // The engine now refuses to guess an attention config it cannot
        // confirm, so an incomplete meta is a hard blocker rather than a
        // silent source of incoherent output.
        let hasHeads = (meta?["num_heads"] as? Int) != nil
        let hasKV = (meta?["num_kv_heads"] as? Int) != nil
        let hasHeadDim = (meta?["head_dim"] as? Int) != nil
        let attentionOK = hasHeads && hasKV && hasHeadDim
        checks.append(Check(
            name: "Attention config resolvable",
            passed: attentionOK,
            detail: attentionOK
                ? "num_heads/num_kv_heads/head_dim present"
                : "incomplete — engine will refuse to load rather than guess"
        ))
        if !attentionOK && meta != nil {
            notes.append("Re-run jgen_forge: a partial meta.json means the conversion did not finish.")
        }

        let support = (meta?["arch"] as? String) ?? "unknown"
        let modelArch = (meta?["model_arch"] as? String)
            ?? (meta?["hf_arch"] as? String)
            ?? "unknown"
        let engineKnows = engineArchitectures.contains(support)
        checks.append(Check(
            name: "Engine implements architecture",
            passed: engineKnows,
            detail: "arch=\(support) model_arch=\(modelArch)"
        ))

        let isValidatedFamily = validatedArchitectures.contains {
            modelArch.lowercased().contains($0)
        }

        let tier: Tier
        if !engineKnows {
            tier = .unsupported
        } else if isValidatedFamily {
            tier = .validated
        } else {
            tier = .experimental
        }

        // Weight size drives whether this can run locally at all.
        var weightBytes: Int64 = 0
        if let attrs = try? fm.attributesOfItem(atPath: modelPath),
           let size = attrs[.size] as? Int64 {
            weightBytes = size
        }
        if let auxAttrs = try? fm.attributesOfItem(atPath: modelPath + ".aux"),
           let auxSize = auxAttrs[.size] as? Int64 {
            weightBytes += auxSize
        }
        let weightGB = Double(weightBytes) / Double(1 << 30)
        // Weights dominate; leave headroom for KV, activations and the OS.
        let estimatedResidentGB = weightGB * 1.15
        let ramGB = Double(ProcessInfo.processInfo.physicalMemory) / Double(1 << 30)

        let fitsComfortably = estimatedResidentGB <= ramGB * 0.6
        let fitsAtAll = estimatedResidentGB <= ramGB * 0.9
        checks.append(Check(
            name: "Fits in unified memory",
            passed: fitsComfortably,
            detail: String(
                format: "weights %.1f GB → ~%.1f GB resident vs %.0f GB RAM%@",
                weightGB, estimatedResidentGB, ramGB,
                fitsComfortably ? "" : (fitsAtAll ? " (tight — expect swap)" : " (will not fit)")
            )
        ))
        if !fitsComfortably && weightBytes > 0 {
            notes.append("jgen_forge dequantizes GGUF Q4/Q5/Q6 to f16, so a Q4 download does not reduce resident size.")
        }

        let engineFound = JGenBackend.locateEngine()
        checks.append(Check(
            name: "Inference engine available",
            passed: engineFound != nil,
            detail: engineFound ?? "libjcross_engine_glm.dylib not found"
        ))

        return ModelCompat(
            modelPath: modelPath,
            hasMeta: meta != nil,
            tier: tier,
            architecture: modelArch,
            checks: checks,
            weightBytes: weightBytes,
            estimatedResidentGB: estimatedResidentGB,
            machineRAMGB: ramGB,
            notes: notes
        )
    }

    // MARK: - Reporting

    /// Human-readable report. Ends with an explicit statement of what has
    /// *not* been verified, so a passing preflight is never mistaken for a
    /// working end-to-end run.
    public func report() -> String {
        var lines: [String] = []
        lines.append("Model:        \(URL(fileURLWithPath: modelPath).lastPathComponent)")
        lines.append("Architecture: \(architecture)")
        lines.append("Support tier: \(tier.rawValue.uppercased())")
        lines.append("")
        for check in checks {
            lines.append("  \(check.passed ? "PASS" : "FAIL")  \(check.name)")
            lines.append("        \(check.detail)")
        }
        if !notes.isEmpty {
            lines.append("")
            lines.append("Notes:")
            for note in notes { lines.append("  - \(note)") }
        }
        lines.append("")
        switch tier {
        case .validated:
            lines.append("This architecture family is the published target for this runtime.")
        case .experimental:
            lines.append("The engine implements this architecture, but no end-to-end run is published for it.")
            lines.append("Validated target: Qwen3.6-27B (hybrid Gated DeltaNet); Qwen3.8-27B once open weights ship.")
        case .unsupported:
            lines.append("The engine has no forward pass for this architecture — loading is expected to fail.")
        }
        lines.append("")
        lines.append("Preflight only. NOT verified by this command:")
        lines.append("  - full-weight conversion fidelity")
        lines.append("  - generated-token correctness")
        lines.append("  - sustained long-horizon behaviour")
        lines.append("Run `vera run` for those; this command never loads the model.")
        return lines.joined(separator: "\n")
    }

    public var allBlockingChecksPassed: Bool {
        checks.allSatisfy { check in
            // Memory fit is advisory (a tight fit still runs, slowly);
            // everything else blocks.
            check.name == "Fits in unified memory" ? true : check.passed
        }
    }
}
