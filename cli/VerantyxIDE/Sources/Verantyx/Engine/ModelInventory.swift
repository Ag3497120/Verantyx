import Foundation

/// One model that is actually present on this machine.
struct InventoryEntry: Identifiable, Sendable, Hashable {
    let id: String
    let name: String
    let backend: ModelBackend
    /// Estimated weights size. `nil` when the backend doesn't report one.
    let sizeGB: Double?
    /// False for e.g. a `.jgen` whose architecture the Rust engine can't run
    /// forward (converted as a static lexicon only).
    let isLoadable: Bool
    let contextLimit: Int?
}

/// Enumerates locally available models across every backend.
///
/// All sources here are live reads (Ollama's HTTP tag list, files on disk)
/// with one honest exception: MLX has no real inventory, only a one-entry
/// hardcoded catalog, so only entries whose weights are actually downloaded
/// are reported.
enum ModelInventory {

    @MainActor
    static func snapshot(app: AppState) async -> [InventoryEntry] {
        var out: [InventoryEntry] = []

        // ── Ollama (live: GET /api/tags) ──────────────────────────────────
        for model in app.ollamaModels {
            out.append(InventoryEntry(
                id: "ollama:\(model)",
                name: model,
                backend: .ollama,
                sizeGB: estimatedSizeGB(fromName: model),
                isLoadable: true,
                contextLimit: ContextBudgetManager.budget(for: model).maxTokens
            ))
        }

        // ── JGEN (live: converted_models on disk) ─────────────────────────
        let converter = JGenConverter.shared
        converter.refreshConvertedModelsList()
        for name in converter.convertedModels {
            let meta = converter.metaJSON(for: name)
            let bytes = (try? FileManager.default.attributesOfItem(
                atPath: JGenPaths.convertedModelsDir.appendingPathComponent(name).path
            )[.size] as? Int) ?? nil
            out.append(InventoryEntry(
                id: "jgen:\(name)",
                name: name,
                backend: .jgen,
                sizeGB: bytes.map { Double($0) / Double(1 << 30) },
                isLoadable: converter.isArchSupported(name),
                contextLimit: (meta?["context_length"] as? Int)
                    ?? ContextBudgetManager.budget(for: name).maxTokens
            ))
        }

        // ── BitNet (live: sidecar JSON on disk) ───────────────────────────
        for cfg in BitNetConfig.installedConfigs() {
            let bytes = (try? FileManager.default.attributesOfItem(atPath: cfg.modelPath)[.size] as? Int) ?? nil
            out.append(InventoryEntry(
                id: "bitnet:\(cfg.modelName)",
                name: cfg.modelName,
                backend: .bitnet,
                sizeGB: bytes.map { Double($0) / Double(1 << 30) },
                isLoadable: true,
                contextLimit: ContextBudgetManager.budget(for: cfg.modelName).maxTokens
            ))
        }

        // ── MLX (hardcoded catalog; only report what's downloaded) ────────
        for m in MLXRunner.popularModels where m.isDownloaded {
            out.append(InventoryEntry(
                id: "mlx:\(m.id)",
                name: m.displayName,
                backend: .mlx,
                sizeGB: m.sizeGB,
                isLoadable: true,
                contextLimit: ContextBudgetManager.budget(for: m.id).maxTokens
            ))
        }

        return out
    }

    /// Ollama reports no size in the tag list, so fall back to the parameter
    /// count embedded in the tag (":8b", ":27b"). Rough, and only used for
    /// fit-checking against RAM -- never presented as exact.
    static func estimatedSizeGB(fromName name: String) -> Double? {
        let lower = name.lowercased()
        guard let range = lower.range(of: #"(\d+(?:\.\d+)?)\s*b\b"#, options: .regularExpression) else {
            return nil
        }
        let digits = lower[range].replacingOccurrences(of: "b", with: "").trimmingCharacters(in: .whitespaces)
        guard let params = Double(digits) else { return nil }
        // ~0.6 GB per billion params is typical for the 4-bit quantized
        // builds Ollama ships by default.
        return params * 0.6
    }
}
