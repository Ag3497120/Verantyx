import AppKit
import CoreGraphics
import Foundation
import Security

/// Screen Recording (TCC) helpers for desktop capture.
///
/// CI/DMG builds are often **ad-hoc signed** (`TeamIdentifier=not set`). On
/// recent macOS, ad-hoc apps frequently show as checked in System Settings
/// while `CGPreflightScreenCaptureAccess()` still returns false — especially
/// when multiple `Verantyx.app` copies (DMG / Applications / DerivedData)
/// share the same bundle id with different code hashes.
enum ScreenCapturePermission {
    nonisolated static var isGranted: Bool {
        if #available(macOS 10.15, *) {
            return CGPreflightScreenCaptureAccess()
        }
        return true
    }

    nonisolated static func request() {
        if #available(macOS 10.15, *) {
            _ = CGRequestScreenCaptureAccess()
        }
    }

    nonisolated static var isAdHocSigned: Bool {
        var code: SecCode?
        guard SecCodeCopySelf([], &code) == errSecSuccess, let code else { return true }
        var staticCode: SecStaticCode?
        guard SecCodeCopyStaticCode(code, [], &staticCode) == errSecSuccess,
              let staticCode else { return true }
        var info: CFDictionary?
        guard SecCodeCopySigningInformation(staticCode, SecCSFlags(rawValue: kSecCSSigningInformation), &info) == errSecSuccess,
              let dict = info as NSDictionary? else { return true }
        let team = dict[kSecCodeInfoTeamIdentifier] as? String
        if team == nil || team?.isEmpty == true { return true }
        // kSecCodeSignatureAdhoc == 0x0002
        if let flags = dict[kSecCodeInfoFlags] as? UInt32, (flags & 0x0002) != 0 {
            return true
        }
        return false
    }

    nonisolated static var recoveryMessage: String {
        let adhoc = isAdHocSigned
        var lines: [String] = [
            "Screen Recording is not active for this Verantyx process.",
            "1) System Settings → Privacy & Security → Screen Recording",
            "2) Remove every Verantyx entry (−), quit Verantyx fully",
            "3) Re-open ONLY /Applications/Verantyx.app and enable the toggle when prompted",
            "4) If it still fails: Terminal → tccutil reset ScreenCapture com.verantyx.ide  then relaunch",
        ]
        if adhoc {
            lines.append(
                "Note: this build is ad-hoc signed (no Developer ID). macOS often drops or mismatches Screen Recording across DMG rebuilds — Developer ID signing is the lasting fix."
            )
        }
        return lines.joined(separator: "\n")
    }

    nonisolated static var shortError: String {
        "Please grant Screen Recording permission. \(recoveryMessage)"
    }

    nonisolated static func openSystemSettings() {
        // Prefer modern Settings deep link; fall back to legacy pane id.
        let urls = [
            "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",
            "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_ScreenCapture",
        ]
        for s in urls {
            if let u = URL(string: s), NSWorkspace.shared.open(u) { return }
        }
    }

    nonisolated static func looksLikeDenied(_ text: String) -> Bool {
        let u = text.lowercased()
        return u.contains("screen recording")
            || u.contains("screencapture")
            || u.contains("cgpreflight")
            || u.contains("画面収録")
            || (u.contains("desktop error") && u.contains("permission"))
    }
}
