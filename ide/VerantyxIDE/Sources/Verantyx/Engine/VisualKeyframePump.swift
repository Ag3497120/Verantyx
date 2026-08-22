import Foundation
import AppKit
import CoreGraphics

/// ~1Hz keyframe pump for operation-agent “watch while waiting”.
///
/// Gates (all required):
/// 1. `CouncilSettingsStore.allowKeyframeEye`
/// 2. `keyframeEyePrivacyAcknowledged`
/// 3. agent session flagged running via `setAgentRunning`
/// 4. `HiddenWindowAutomation.targetAppName != nil`
///
/// Captures without un-minimizing the target every second (quiet path).
/// Changed frames go to `VeraAVRing` only — not GapGraph / Eternal.
@MainActor
final class VisualKeyframePump: ObservableObject {
    static let shared = VisualKeyframePump()

    @Published private(set) var isActivelyMonitoring = false
    @Published private(set) var monitoredAppName: String?

    private var timer: Timer?
    private var agentRunning = false
    private var sessionId: String = ""
    private var previousImage: NSImage?
    private var previousAXFingerprint: String = ""

    private init() {}

    /// Called from AgentLoop at run start/end.
    func setAgentRunning(_ running: Bool, sessionId: String? = nil) {
        agentRunning = running
        if let sessionId, !sessionId.isEmpty {
            self.sessionId = sessionId
        }
        if !running {
            stopTimer()
            isActivelyMonitoring = false
            monitoredAppName = nil
            previousImage = nil
            previousAXFingerprint = ""
            Task { await VeraAVRing.shared.clearSession() }
        } else {
            reconcile()
        }
    }

    /// Re-evaluate gates after settings / target changes.
    func reconcile() {
        if shouldRun {
            startTimerIfNeeded()
        } else {
            stopTimer()
            isActivelyMonitoring = false
            monitoredAppName = nil
        }
    }

    var shouldRun: Bool {
        let council = CouncilSettingsStore.shared
        guard council.allowKeyframeEye,
              council.keyframeEyePrivacyAcknowledged,
              agentRunning,
              HiddenWindowAutomation.shared.targetAppName != nil
        else { return false }
        return true
    }

    private func startTimerIfNeeded() {
        guard timer == nil else {
            isActivelyMonitoring = true
            monitoredAppName = HiddenWindowAutomation.shared.targetAppName
            return
        }
        // Tolerance keeps RunLoop coalescing cheaper under load.
        let t = Timer(timeInterval: 1.0, repeats: true) { [weak self] _ in
            Task { @MainActor in
                await self?.tick()
            }
        }
        t.tolerance = 0.15
        RunLoop.main.add(t, forMode: .common)
        timer = t
        isActivelyMonitoring = true
        monitoredAppName = HiddenWindowAutomation.shared.targetAppName
    }

    private func stopTimer() {
        timer?.invalidate()
        timer = nil
    }

    private func tick() async {
        guard shouldRun else {
            reconcile()
            return
        }
        let appName = HiddenWindowAutomation.shared.targetAppName ?? ""
        monitoredAppName = appName
        isActivelyMonitoring = true

        await VeraAVRing.shared.noteTickAttempted()

        // Quiet capture: never flash-restore every second.
        guard let base64 = await HiddenWindowAutomation.shared.captureWindowImageQuiet(),
              let data = Data(base64Encoded: base64),
              let after = NSImage(data: data)
        else { return }

        var region: CGRect? = nil
        var changed = false
        if let before = previousImage {
            region = VisualDiffRegion.changedRegion(before: before, after: after)
            changed = region != nil
        } else {
            // First frame: establish baseline only (no ring write).
            previousImage = after
            previousAXFingerprint = await axFingerprint(appName: appName)
            return
        }
        previousImage = after

        if !changed {
            await VeraAVRing.shared.noteTickDroppedUnchanged()
            return
        }

        let axNow = await axFingerprint(appName: appName)
        let axDelta = Self.diffFingerprints(prev: previousAXFingerprint, next: axNow)
        previousAXFingerprint = axNow

        let note = region.map {
            String(format: "screen changed (%.0f,%.0f %.0fx%.0f)",
                   $0.origin.x, $0.origin.y, $0.width, $0.height)
        } ?? "screen changed"

        let obs = VeraAVRing.Observation(
            ts: Date().timeIntervalSince1970,
            sessionId: sessionId.isEmpty ? "keyframe" : sessionId,
            appName: appName,
            changed: true,
            region: VeraAVRing.regionArray(region),
            axDeltaSummary: String(axDelta.prefix(240)),
            note: note
        )
        await VeraAVRing.shared.append(obs)
    }

    private func axFingerprint(appName: String) async -> String {
        (try? await AXVisionBridge.shared.getSemanticSnapshot(appName: appName)) ?? ""
    }

    private static func diffFingerprints(prev: String, next: String) -> String {
        guard !prev.isEmpty else { return "baseline" }
        if prev == next { return "visual-only" }
        let prevTitles = Set(prev.split(separator: "\n").map(String.init).filter { $0.contains("title=") })
        let nextTitles = Set(next.split(separator: "\n").map(String.init).filter { $0.contains("title=") })
        let added = nextTitles.subtracting(prevTitles)
        let removed = prevTitles.subtracting(nextTitles)
        var parts: [String] = []
        if !added.isEmpty {
            parts.append("+\(added.prefix(4).joined(separator: "|"))")
        }
        if !removed.isEmpty {
            parts.append("-\(removed.prefix(4).joined(separator: "|"))")
        }
        if parts.isEmpty { return "ax-structure-changed" }
        return parts.joined(separator: " ")
    }

    /// Block until the ring reports no change for `stableSeconds`, or timeout.
    func waitUntilStable(stableSeconds: TimeInterval = 2.0, timeout: TimeInterval = 30.0) async -> Bool {
        let start = Date()
        // Seed lastChange if empty so we don't succeed immediately without data.
        if await VeraAVRing.shared.secondsSinceLastChange() == nil {
            // Wait at least one tick opportunity.
            try? await Task.sleep(nanoseconds: 1_100_000_000)
        }
        while Date().timeIntervalSince(start) < timeout {
            if let since = await VeraAVRing.shared.secondsSinceLastChange(), since >= stableSeconds {
                return true
            }
            try? await Task.sleep(nanoseconds: 250_000_000)
        }
        return false
    }

    func statusMap() async -> [String: Any] {
        var ring = await VeraAVRing.shared.statusMap()
        ring["actively_monitoring"] = isActivelyMonitoring
        ring["monitored_app"] = monitoredAppName ?? ""
        ring["agent_running_flag"] = agentRunning
        ring["allow"] = CouncilSettingsStore.shared.allowKeyframeEye
        ring["privacy_ack"] = CouncilSettingsStore.shared.keyframeEyePrivacyAcknowledged
        return ring
    }
}
