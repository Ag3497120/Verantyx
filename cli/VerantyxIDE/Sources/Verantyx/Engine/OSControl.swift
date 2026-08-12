import Foundation
import Cocoa
import ApplicationServices

// MARK: - Operating an app the way its author intended it to be operated
//
// Until now the agent could only press what happened to be drawn on screen.
// That is the smallest surface a Mac app has. Every app also publishes its
// entire command set through the accessibility menu bar — File ▸ Save,
// Format ▸ Bold, View ▸ Show Sidebar — reachable without the menu being open,
// without hunting for a toolbar button, and without the window even being
// scrolled to the right place.
//
// This matters for the architecture rather than as a convenience: if the plan
// is to use the applications the user already has instead of rebuilding them,
// then the agent has to be able to drive them the way a person does, and a
// person mostly drives a Mac app from its menus and its keyboard shortcuts —
// not by hunting for pixels.
//
// Three routes, in order of how much they can be trusted:
//
//   menu      — the app's own published command. Exact, no coordinates.
//   shortcut  — the same command by key. Exact, but silent when unbound.
//   click     — last resort. Needs the control to be visible and hit.
//
// Which one actually worked for a given app is worth remembering, and is
// recorded to vera-a, so the choice improves rather than being re-guessed.
enum OSControl {

    /// Succeeded with a description, or failed with text meant for the model
    /// to read and act on. Not `Result<_, Error>`: every failure here is a
    /// sentence about what to try instead, not an error to propagate.
    enum Outcome {
        case ok(String)
        case failed(String)
    }

    // MARK: - Reading attributes

    static func attr<T>(_ element: AXUIElement, _ name: String) -> T? {
        var value: CFTypeRef?
        guard AXUIElementCopyAttributeValue(element, name as CFString, &value) == .success
        else { return nil }
        return value as? T
    }

    static func appElement(_ appName: String) -> (AXUIElement, NSRunningApplication)? {
        guard let app = NSWorkspace.shared.runningApplications.first(where: {
            $0.localizedName?.caseInsensitiveCompare(appName) == .orderedSame
        }) else { return nil }
        return (AXUIElementCreateApplication(app.processIdentifier), app)
    }

    // MARK: - Menus

    struct MenuItem {
        let path: [String]          // ["File", "Save"]
        let shortcut: String        // "⌘S" or ""
        let enabled: Bool
        var display: String {
            let p = path.joined(separator: " ▸ ")
            return shortcut.isEmpty ? p : "\(p)   \(shortcut)"
        }
    }

    /// Every menu command the app publishes, flattened to readable paths.
    ///
    /// Menus do not need to be open for this: AX exposes the structure
    /// statically. Some apps populate a submenu only when it is first opened,
    /// which is why `enumerable` in `capabilities` reports what was actually
    /// found rather than assuming a full tree.
    static func menuItems(of appName: String, limit: Int = 200) -> [MenuItem] {
        guard AXIsProcessTrusted(), let (ax, _) = appElement(appName),
              let bar: AXUIElement = attr(ax, kAXMenuBarAttribute as String),
              let tops: [AXUIElement] = attr(bar, kAXChildrenAttribute as String)
        else { return [] }

        var out: [MenuItem] = []

        func walk(_ element: AXUIElement, path: [String], depth: Int) {
            guard depth <= 4, out.count < limit else { return }
            guard let children: [AXUIElement] = attr(element, kAXChildrenAttribute as String)
            else { return }

            for child in children {
                guard out.count < limit else { return }
                let role: String = attr(child, kAXRoleAttribute as String) ?? ""

                // An AXMenu is the container hanging off a menu item; descend
                // through it without adding a level to the path.
                if role == "AXMenu" {
                    walk(child, path: path, depth: depth)
                    continue
                }

                let title: String = attr(child, kAXTitleAttribute as String) ?? ""
                guard !title.isEmpty, title != "Apple" else { continue }
                let here = path + [title]

                let hasSubmenu = (attr(child, kAXChildrenAttribute as String) as [AXUIElement]?)?
                    .isEmpty == false
                if hasSubmenu {
                    walk(child, path: here, depth: depth + 1)
                } else {
                    let cmd: String = attr(child, "AXMenuItemCmdChar") ?? ""
                    let enabled: Bool = attr(child, kAXEnabledAttribute as String) ?? true
                    out.append(MenuItem(path: here,
                                        shortcut: cmd.isEmpty ? "" : "⌘\(cmd)",
                                        enabled: enabled))
                }
            }
        }

        for top in tops { walk(top, path: [], depth: 1) }
        return out
    }

    /// Invoke a menu command by path. Matching is forgiving about case and
    /// the ellipsis Mac menus append ("Save As…"), because the model will
    /// write what it read and menus do not always render what AX reports.
    @discardableResult
    static func invokeMenu(of appName: String, path: [String]) -> Outcome {
        guard AXIsProcessTrusted() else { return .failed("アクセシビリティ権限がありません") }
        guard let (ax, _) = appElement(appName) else { return .failed("\(appName) は起動していません") }
        guard let bar: AXUIElement = attr(ax, kAXMenuBarAttribute as String) else {
            return .failed("\(appName) のメニューを読み取れません")
        }

        func normalize(_ s: String) -> String {
            s.lowercased()
                .replacingOccurrences(of: "…", with: "")
                .replacingOccurrences(of: "...", with: "")
                .trimmingCharacters(in: .whitespaces)
        }

        var current = bar
        for (i, wanted) in path.enumerated() {
            var candidates: [AXUIElement] = attr(current, kAXChildrenAttribute as String) ?? []
            // Step through the AXMenu wrapper.
            if candidates.count == 1,
               (attr(candidates[0], kAXRoleAttribute as String) as String?) == "AXMenu",
               let inner: [AXUIElement] = attr(candidates[0], kAXChildrenAttribute as String) {
                candidates = inner
            }

            let want = normalize(wanted)
            guard let hit = candidates.first(where: {
                normalize(attr($0, kAXTitleAttribute as String) ?? "") == want
            }) ?? candidates.first(where: {
                normalize(attr($0, kAXTitleAttribute as String) ?? "").hasPrefix(want)
            }) else {
                let available = candidates.compactMap {
                    attr($0, kAXTitleAttribute as String) as String?
                }.filter { !$0.isEmpty }.prefix(12).joined(separator: " / ")
                return .failed("「\(wanted)」が見つかりません（\(path.prefix(i).joined(separator: " ▸ "))" +
                                "の中身: \(available)）")
            }
            current = hit
        }

        let enabled: Bool = attr(current, kAXEnabledAttribute as String) ?? true
        guard enabled else {
            return .failed("「\(path.joined(separator: " ▸ "))」は現在無効です（実行できない状態）")
        }

        let err = AXUIElementPerformAction(current, kAXPressAction as CFString)
        return err == .success
            ? .ok(path.joined(separator: " ▸ "))
            : .failed("押せませんでした (AXError \(err.rawValue))")
    }

    // MARK: - Keyboard shortcuts

    /// Send a key combination to a specific app, whether or not it is
    /// frontmost. `typeText` posts unicode to whatever has focus, which is the
    /// wrong tool for ⌘S: the keystroke would land in whichever window the
    /// user happened to click.
    static func sendShortcut(to appName: String, combo: String) -> Outcome {
        guard let (_, app) = appElement(appName) else {
            return .failed("\(appName) は起動していません")
        }
        guard let (keyCode, flags) = parseCombo(combo) else {
            return .failed("キー指定を解釈できません: \(combo)")
        }

        let source = CGEventSource(stateID: .hidSystemState)
        guard let down = CGEvent(keyboardEventSource: source, virtualKey: keyCode, keyDown: true),
              let up = CGEvent(keyboardEventSource: source, virtualKey: keyCode, keyDown: false)
        else { return .failed("イベントを作成できません") }
        down.flags = flags
        up.flags = flags

        // postToPid rather than the HID tap: the shortcut goes to the app we
        // named, not to whatever is in front.
        down.postToPid(app.processIdentifier)
        usleep(30_000)
        up.postToPid(app.processIdentifier)
        return .ok("\(combo) → \(appName)")
    }

    /// "cmd+s", "⌘S", "shift+cmd+4", "esc", "return".
    static func parseCombo(_ raw: String) -> (CGKeyCode, CGEventFlags)? {
        var flags: CGEventFlags = []
        var key = ""

        let normalized = raw
            .replacingOccurrences(of: "⌘", with: "cmd+")
            .replacingOccurrences(of: "⇧", with: "shift+")
            .replacingOccurrences(of: "⌥", with: "opt+")
            .replacingOccurrences(of: "⌃", with: "ctrl+")
            .lowercased()

        for part in normalized.split(whereSeparator: { $0 == "+" || $0 == "-" }) {
            switch part {
            case "cmd", "command": flags.insert(.maskCommand)
            case "shift":          flags.insert(.maskShift)
            case "opt", "option", "alt": flags.insert(.maskAlternate)
            case "ctrl", "control": flags.insert(.maskControl)
            default: key = String(part)
            }
        }
        guard let code = keyCode(for: key) else { return nil }
        return (code, flags)
    }

    private static func keyCode(for key: String) -> CGKeyCode? {
        let letters: [String: CGKeyCode] = [
            "a":0,"s":1,"d":2,"f":3,"h":4,"g":5,"z":6,"x":7,"c":8,"v":9,
            "b":11,"q":12,"w":13,"e":14,"r":15,"y":16,"t":17,
            "1":18,"2":19,"3":20,"4":21,"6":22,"5":23,"9":25,"7":26,"8":28,"0":29,
            "o":31,"u":32,"i":34,"p":35,"l":37,"j":38,"k":40,"n":45,"m":46,
            "return":36,"enter":36,"tab":48,"space":49,"delete":51,"backspace":51,
            "esc":53,"escape":53,"left":123,"right":124,"down":125,"up":126,
            "f1":122,"f2":120,"f3":99,"f4":118,"f5":96,"f6":97,"f11":103,"f12":111
        ]
        return letters[key]
    }

    // MARK: - What this app can actually be driven with

    struct Capabilities {
        let appName: String
        let axAvailable: Bool
        let windowCount: Int
        let menuCount: Int
        let scriptable: Bool

        var summary: String {
            var lines = ["\(appName):"]
            lines.append("  • アクセシビリティ: \(axAvailable ? "読める" : "読めない")")
            lines.append("  • ウィンドウ: \(windowCount)")
            lines.append("  • メニュー項目: \(menuCount == 0 ? "読めない" : "\(menuCount) 件")")
            lines.append("  • AppleScript: \(scriptable ? "対応" : "未対応/不明")")
            var advice: [String] = []
            if menuCount > 0 { advice.append("[MENU: …] が最も確実") }
            if axAvailable { advice.append("[CLICK_LINK: 表示文字] が使える") }
            if scriptable { advice.append("[OSASCRIPT: …] も使える") }
            if advice.isEmpty { advice.append("画面を見て操作する [DESKTOP_ACT] のみ") }
            lines.append("  → 推奨: " + advice.joined(separator: " / "))
            return lines.joined(separator: "\n")
        }
    }

    /// Probe before guessing. An app that publishes 300 menu commands should
    /// be driven through them; one that publishes none has to be clicked.
    static func capabilities(of appName: String) -> Capabilities? {
        guard let (ax, app) = appElement(appName) else { return nil }
        let windows: [AXUIElement] = attr(ax, kAXWindowsAttribute as String) ?? []
        let menus = menuItems(of: appName, limit: 400)

        // The scripting dictionary is the honest test for AppleScript support
        // — asking the app to run something would have side effects.
        var scriptable = false
        if let url = app.bundleURL,
           let bundle = Bundle(url: url),
           let info = bundle.infoDictionary {
            scriptable = info["OSAScriptingDefinition"] != nil
                || info["NSAppleScriptEnabled"] as? Bool == true
                || info["NSAppleScriptEnabled"] as? String == "YES"
        }

        return Capabilities(appName: appName,
                            axAvailable: !windows.isEmpty || !menus.isEmpty,
                            windowCount: windows.count,
                            menuCount: menus.count,
                            scriptable: scriptable)
    }
}
