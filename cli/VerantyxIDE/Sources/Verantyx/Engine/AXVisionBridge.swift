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
            } else {
                return "[AX_ERROR] Failed to click \(id) (Error code: \(err.rawValue))."
            }
        } else if action == "type" {
            guard let textToType = text else {
                return "[AX_ERROR] Text is required for type action."
            }
            let err = AXUIElementSetAttributeValue(element, kAXValueAttribute as CFString, textToType as CFTypeRef)
            if err == .success {
                return "Successfully typed into \(id)."
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
