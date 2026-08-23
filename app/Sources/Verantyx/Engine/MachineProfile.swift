import Foundation

/// What this Mac can actually run.
///
/// Nothing in the app measured RAM or free disk before this: every
/// "recommended model" string was static text, and model sizing was inferred
/// from the model's *name* (`ModelProfileDetector`), never from the hardware.
/// The setup planner needs real numbers to refuse a plan that would swap or
/// run out of space.
struct MachineProfile: Sendable {
    let totalRAMGB: Double
    let coreCount: Int
    let isAppleSilicon: Bool
    let freeDiskGB: Double

    /// Roughly what a model may occupy before it starts fighting the OS and
    /// the rest of the app for memory. Deliberately conservative: unified
    /// memory on Apple Silicon is shared with the GPU.
    var usableModelRAMGB: Double { totalRAMGB * 0.6 }

    /// Budget for pipeline mode, where the model does not fit on one machine.
    ///
    /// Higher than `usableModelRAMGB` on purpose — see `SplitPlanner.pipelineRAMFactor`
    /// for the arithmetic. Applying the conservative factor here would make the
    /// feature unable to run the models it exists for.
    var usablePipelineRAMGB: Double { totalRAMGB * SplitPlanner.pipelineRAMFactor }

    static func current() -> MachineProfile {
        let ram = Double(ProcessInfo.processInfo.physicalMemory) / Double(1 << 30)

        #if arch(arm64)
        let appleSilicon = true
        #else
        let appleSilicon = false
        #endif

        // Measure the volume that actually receives converted models, not
        // "/" -- on a Mac with a separate data volume those differ, and the
        // one that matters is where .jgen files land.
        var freeGB: Double = 0
        let probe = JGenPaths.convertedModelsDir
        try? FileManager.default.createDirectory(at: probe, withIntermediateDirectories: true)
        if let values = try? probe.resourceValues(forKeys: [.volumeAvailableCapacityForImportantUsageKey]),
           let available = values.volumeAvailableCapacityForImportantUsage {
            freeGB = Double(available) / Double(1 << 30)
        }

        return MachineProfile(
            totalRAMGB: ram,
            coreCount: ProcessInfo.processInfo.activeProcessorCount,
            isAppleSilicon: appleSilicon,
            freeDiskGB: freeGB
        )
    }

    var summary: String {
        String(format: "%.0f GB RAM · %d cores · %@ · %.1f GB free",
               totalRAMGB, coreCount,
               isAppleSilicon ? "Apple Silicon" : "Intel",
               freeDiskGB)
    }
}
