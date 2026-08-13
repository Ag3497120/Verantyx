import Foundation
import Cocoa
import ApplicationServices
import Accessibility

class AXVisionBridge {
    static let shared = AXVisionBridge()
    
    // Cache for mapping short IDs to AXUIElements
    private var elementCache: [String: AXUIElement] = [:]
    
    // Check and request accessibility permissions
    func checkAndRequestPermissions() -> Bool {
        let options = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary
        return AXIsProcessTrustedWithOptions(options)
    }
    
    // Generate a Semantic UI Map of the frontmost application
    func getSemanticSnapshot() async throws -> String {
        guard AXIsProcessTrusted() else {
            return "[AX_ERROR] Accessibility permission is missing. Please grant it in System Settings > Privacy & Security > Accessibility."
        }
        
        guard let frontApp = NSWorkspace.shared.frontmostApplication else {
            return "[AX_ERROR] No frontmost application found."
        }
        
        return try await getSemanticSnapshot(appName: frontApp.localizedName ?? "Unknown",
                                             pid: frontApp.processIdentifier)
    }

    /// Snapshot a specific app by localized name (keyframe eye / HiddenWindow target).
    func getSemanticSnapshot(appName: String) async throws -> String {
        guard AXIsProcessTrusted() else {
            return "[AX_ERROR] Accessibility permission is missing. Please grant it in System Settings > Privacy & Security > Accessibility."
        }
        let match = NSWorkspace.shared.runningApplications.first {
            $0.localizedName == appName
        }
        guard let app = match else {
            return "[AX_ERROR] No running application named \(appName)."
        }
        return try await getSemanticSnapshot(appName: appName, pid: app.processIdentifier)
    }

    private func getSemanticSnapshot(appName: String, pid: pid_t) async throws -> String {
        let appElement = AXUIElementCreateApplication(pid)
        
        // Clear previous cache
        elementCache.removeAll()
        
        var focusedWindow: CFTypeRef?
        let err = AXUIElementCopyAttributeValue(appElement, kAXFocusedWindowAttribute as CFString, &focusedWindow)
        
        guard err == .success, let window = focusedWindow else {
            // Fallback to main window if focused window not found
            var mainWindow: CFTypeRef?
            let mainErr = AXUIElementCopyAttributeValue(appElement, kAXMainWindowAttribute as CFString, &mainWindow)
            if mainErr == .success, let main = mainWindow {
                return buildXMLTree(for: main as! AXUIElement, appName: appName)
            }
            return "[AX_ERROR] Could not find focused or main window for \(appName)."
        }
        
        return buildXMLTree(for: window as! AXUIElement, appName: appName)
    }
    
    // Perform an action on an element by its ID
    /// Screen point at the centre of a cached element.
    ///
    /// Exists so a link can be reached the way a person reaches it — the
    /// pointer travels there and clicks — rather than by AXPress, which
    /// activates the element with no cursor motion at all. Motion is what
    /// the multimodal loop reads: without it there are no hover states and
    /// no frame-to-frame delta to attribute the change to.
    func screenPoint(forElementID id: String) -> CGPoint? {
        guard let element = elementCache[id] else { return nil }
        var positionValue: CFTypeRef?
        var sizeValue: CFTypeRef?
        guard AXUIElementCopyAttributeValue(element, kAXPositionAttribute as CFString, &positionValue) == .success,
              AXUIElementCopyAttributeValue(element, kAXSizeAttribute as CFString, &sizeValue) == .success
        else { return nil }
        var origin = CGPoint.zero
        var size = CGSize.zero
        guard let p = positionValue, let s = sizeValue,
              AXValueGetValue(p as! AXValue, .cgPoint, &origin),
              AXValueGetValue(s as! AXValue, .cgSize, &size),
              size.width > 1, size.height > 1
        else { return nil }
        return CGPoint(x: origin.x + size.width / 2, y: origin.y + size.height / 2)
    }

    /// The cached actionable element whose title best matches `text`.
    /// Exact match wins, then containment, then the shortest title that
    /// contains every word — a link is chosen by what it says, the way a
    /// reader picks one.
    func findElementID(matching text: String, preferLinks: Bool = true) -> String? {
        let needle = text.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
        guard !needle.isEmpty else { return nil }
        var titles: [(id: String, title: String)] = []
        for (id, element) in elementCache {
            var value: CFTypeRef?
            for attribute in [kAXTitleAttribute, kAXDescriptionAttribute, kAXValueAttribute] {
                if AXUIElementCopyAttributeValue(element, attribute as CFString, &value) == .success,
                   let t = value as? String, !t.isEmpty {
                    titles.append((id, t.lowercased()))
                    break
                }
            }
        }
        let pool = preferLinks
            ? (titles.filter { $0.id.hasPrefix("#link") }.isEmpty ? titles
               : titles.filter { $0.id.hasPrefix("#link") })
            : titles
        if let exact = pool.first(where: { $0.title == needle }) { return exact.id }
        let contains = pool.filter { $0.title.contains(needle) || needle.contains($0.title) }
        if let best = contains.min(by: { $0.title.count < $1.title.count }) { return best.id }
        let words = needle.split(whereSeparator: { $0.isWhitespace }).map(String.init)
        guard words.count > 1 else { return nil }
        let allWords = pool.filter { entry in words.allSatisfy { entry.title.contains($0) } }
        return allWords.min(by: { $0.title.count < $1.title.count })?.id
    }

    func performAction(id: String, action: String, text: String? = nil) async throws -> String {
        guard let element = elementCache[id] else {
            return "[AX_ERROR] Element ID \(id) not found in the current semantic snapshot."
        }
        
        if action == "click" {
            let err = AXUIElementPerformAction(element, kAXPressAction as CFString)
            if err == .success {
                return "Successfully clicked \(id)."
            }

            // -25206 is kAXErrorActionUnsupported: the element has no press.
            // A text field is the common case — Safari's address bar cannot be
            // "pressed", it is focused and typed into. Reporting the raw code
            // and stopping is what sent a run down a much worse path: the
            // click failed, focus stayed on the page, the follow-up ⌘A
            // selected the entire Wikipedia article, and the URL was typed
            // into nothing.
            if err.rawValue == -25206 || err.rawValue == -25205 {
                // Focus is what "click this field" actually means.
                let focusErr = AXUIElementSetAttributeValue(
                    element, kAXFocusedAttribute as CFString, kCFBooleanTrue)
                if focusErr == .success {
                    return "Focused \(id) (this element has no press action; "
                        + "focus is the equivalent). You can type into it now."
                }
                // Otherwise put a real pointer on it, which works on anything
                // drawn on screen regardless of what actions it publishes.
                if let point = screenPoint(forElementID: id) {
                    try? await DesktopVisionBridge.shared.clickAtScreenPoint(point, label: id)
                    return "Clicked \(id) with the pointer (no press action available)."
                }
                return "[AX_ERROR] \(id) supports neither press nor focus, and its "
                    + "position could not be read. Use [DESKTOP_SNAPSHOT] then "
                    + "[DESKTOP_ACT: click x y]."
            }
            return "[AX_ERROR] Failed to click \(id) (Error code: \(err.rawValue))."
        } else if action == "type" {
            guard let textToType = text else {
                return "[AX_ERROR] Text is required for type action."
            }

            // A newline here is a request to SUBMIT, not to type a character.
            // This path sets the field's value, so `type "\n"` replaced
            // "verantyx" with a newline and searched for nothing — the field
            // read "\n" afterwards, which is exactly what happened in the App
            // Store run. Setting a value is not a keystroke and can never
            // trigger a search; Return has to be a real key event.
            let submitAliases = ["\n", "\\n", "\r", "return", "enter", "\u{23CE}"]
            if submitAliases.contains(textToType.trimmingCharacters(in: .whitespaces).lowercased()) {
                AXUIElementSetAttributeValue(element, kAXFocusedAttribute as CFString, kCFBooleanTrue)
                let app = await MainActor.run {
                    NSWorkspace.shared.frontmostApplication?.localizedName ?? ""
                }
                let sent = await MainActor.run { OSControl.sendShortcut(to: app, combo: "return") }
                if case .ok = sent {
                    return "Pressed Return in \(id). (A newline cannot be typed into a "
                        + "field by value — it is a key, so it was sent as one.)"
                }
                return "[AX_ERROR] Could not send Return to \(app). Use [KEYS: return]."
            }

            let err = AXUIElementSetAttributeValue(element, kAXValueAttribute as CFString, textToType as CFTypeRef)
            if err == .success {
                // Say that it REPLACED, because the model reasonably assumes
                // typing appends and then builds on a field it has emptied.
                return "Set \(id) to \"\(textToType.prefix(40))\" — note this REPLACES the "
                    + "whole field rather than appending. To submit, use [KEYS: return]."
            } else if err.rawValue == -25205 {
                // AttributeUnsupported: the element has no settable value.
                // Focus it and type for real, the way a person would.
                AXUIElementSetAttributeValue(element, kAXFocusedAttribute as CFString, kCFBooleanTrue)
                try? await DesktopVisionBridge.shared.typeText(textToType)
                return "\(id) has no settable value, so it was focused and typed into directly."
            } else {
                // Some elements don't support setting value directly, try focused typing
                AXUIElementSetAttributeValue(element, kAXFocusedAttribute as CFString, true as CFTypeRef)
                return "[AX_WARNING] Attempted to focus \(id) for typing. If text didn't appear, use [VISION_ACT] to type instead."
            }
        }
        
        return "[AX_ERROR] Unknown action: \(action)."
    }
    
    // MARK: - Tree Building
    
    private func buildXMLTree(for rootWindow: AXUIElement, appName: String) -> String {
        var counters: [String: Int] = ["btn": 1, "input": 1, "link": 1, "elem": 1]
        
        func getAttribute<T>(_ element: AXUIElement, _ attribute: String) -> T? {
            var value: CFTypeRef?
            if AXUIElementCopyAttributeValue(element, attribute as CFString, &value) == .success {
                return value as? T
            }
            return nil
        }

        /// Read an attribute as text.
        ///
        /// `getAttribute` was being called with `T == Any`, and casting an
        /// `Optional` to `Any` succeeds by boxing the optional itself — so
        /// `String(describing:)` printed the wrapper. Every value in every
        /// semantic map came out as `Optional(Create Post)`, and an empty
        /// CFString came out as the literal `Optional()`, which reached the
        /// user as a numbered candidate to choose from. Asking for `String`
        /// directly is the whole fix; there is no describing to do.
        func stringAttribute(_ element: AXUIElement, _ attribute: String) -> String {
            guard let s: String = getAttribute(element, attribute) else { return "" }
            return s
        }

        func traverse(_ element: AXUIElement, depth: Int = 0) -> String {
            if depth > 15 { return "" } // Prevent infinite recursion

            let role: String = getAttribute(element, kAXRoleAttribute) ?? "Unknown"
            let title: String = getAttribute(element, kAXTitleAttribute) ?? ""
            let value = stringAttribute(element, kAXValueAttribute)
            let isEnabled: Bool = getAttribute(element, kAXEnabledAttribute) ?? false
            
            var xml = ""
            let indent = String(repeating: "  ", count: depth)
            
            // Check if element is actionable
            var actionableID: String? = nil
            if role == kAXButtonRole as String {
                actionableID = "#btn\(counters["btn"]!)"
                counters["btn"]! += 1
            } else if role == kAXTextFieldRole as String || role == kAXTextAreaRole as String {
                actionableID = "#input\(counters["input"]!)"
                counters["input"]! += 1
            } else if role == "AXLink" {
                actionableID = "#link\(counters["link"]!)"
                counters["link"]! += 1
            } else {
                // Check if it has actions
                var actionNames: CFArray?
                if AXUIElementCopyActionNames(element, &actionNames) == .success, let actions = actionNames as? [String], actions.contains(kAXPressAction as String) {
                    actionableID = "#elem\(counters["elem"]!)"
                    counters["elem"]! += 1
                }
            }
            
            if let id = actionableID {
                elementCache[id] = element
                let titleAttr = title.isEmpty ? "" : " title=\"\(title.replacingOccurrences(of: "\"", with: "'"))\""
                let valAttr = value.isEmpty ? "" : " value=\"\(value.replacingOccurrences(of: "\"", with: "'").prefix(30))\""
                let stateAttr = !isEnabled ? " disabled=\"true\"" : ""
                xml += "\(indent)<\(role.replacingOccurrences(of: "AX", with: "").lowercased()) id=\"\(id)\"\(titleAttr)\(valAttr)\(stateAttr) />\n"
            }
            
            // Traverse children
            if let children: [AXUIElement] = getAttribute(element, kAXChildrenAttribute) {
                var hasValidChildren = false
                var childrenXML = ""
                for child in children {
                    let childXML = traverse(child, depth: depth + 1)
                    if !childXML.isEmpty {
                        hasValidChildren = true
                        childrenXML += childXML
                    }
                }
                
                if actionableID == nil {
                    // Only wrap non-actionable elements if they have meaningful children or a strong role
                    if hasValidChildren {
                        let roleName = role.replacingOccurrences(of: "AX", with: "").lowercased()
                        if roleName == "window" || roleName == "group" || roleName == "scrollarea" || roleName == "webarea" {
                            let titleAttr = title.isEmpty ? "" : " title=\"\(title.replacingOccurrences(of: "\"", with: "'"))\""
                            xml += "\(indent)<\(roleName)\(titleAttr)>\n\(childrenXML)\(indent)</\(roleName)>\n"
                        } else {
                            // Flatten
                            xml += childrenXML
                        }
                    }
                }
            }
            
            return xml
        }
        
        let rootTitle: String = getAttribute(rootWindow, kAXTitleAttribute) ?? "Window"
        return "<desktop_app name=\"\(appName)\" window_title=\"\(rootTitle)\">\n\(traverse(rootWindow, depth: 1))</desktop_app>"
    }
}
