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

    // MARK: - Waking an app's accessibility tree
    //
    // Chromium does not publish its page content to accessibility at all
    // unless it believes an assistive technology is listening. With Safari the
    // tree is simply there; with Chrome, Edge, Brave, Arc, Opera and Vivaldi
    // the window is readable and the page inside it is empty — no links, no
    // buttons, nothing to match a click against.
    //
    // The symptom is not an error. Reading the tree succeeds, it is just
    // barren, so a lookup returns "not found" and the pointer never moves. A
    // run can sit in that state indefinitely, which is exactly what happened
    // to "Chrome で ChatGPT を開いて…": Chrome opened, and then nothing.
    //
    // `AXManualAccessibility` is the documented way to say "publish it
    // anyway". Set once per app, before the first read.

    private static var wokenPIDs = Set<pid_t>()

    static func isChromiumBrowser(_ name: String) -> Bool {
        let n = name.lowercased()
        return ["chrome", "chromium", "edge", "brave", "arc", "opera", "vivaldi"]
            .contains { n.contains($0) }
    }

    /// Ask an app to publish its full accessibility tree. Returns true when a
    /// request was actually made, so callers know to wait for it to build.
    @discardableResult
    static func wakeAccessibility(of appName: String) -> Bool {
        guard let (ax, app) = appElement(appName) else { return false }
        guard !wokenPIDs.contains(app.processIdentifier) else { return false }

        // Only where it is needed. The attribute is harmless elsewhere, but
        // its sibling AXEnhancedUserInterface is not — it makes some apps
        // reposition their own windows — so nothing is set speculatively.
        guard isChromiumBrowser(appName) else { return false }

        AXUIElementSetAttributeValue(ax, "AXManualAccessibility" as CFString, kCFBooleanTrue)
        wokenPIDs.insert(app.processIdentifier)
        return true
    }

    /// Ask again, ignoring the once-per-process guard. Some Chromium builds
    /// drop the request when it arrives before a window exists.
    static func forceWakeAccessibility(of appName: String) {
        guard let (ax, app) = appElement(appName), isChromiumBrowser(appName) else { return }
        AXUIElementSetAttributeValue(ax, "AXManualAccessibility" as CFString, kCFBooleanTrue)
        wokenPIDs.insert(app.processIdentifier)
    }

    /// Whether a snapshot looks like a browser that never woke up: a window,
    /// but nothing inside it worth clicking.
    static func looksUnwoken(_ appName: String, snapshot: String) -> Bool {
        guard isChromiumBrowser(appName) else { return false }
        let links = snapshot.components(separatedBy: "<link").count - 1
        let buttons = snapshot.components(separatedBy: "<button").count - 1
        return links + buttons < 3
    }

    // MARK: - Things in the way
    //
    // A menu the user left open, Safari's downloads popover, a sheet, a
    // notification: all of them sit over the thing the agent is trying to
    // reach, and none of them can be enumerated in advance. Writing "if the
    // downloads popover is open, press Escape" does not converge — there is no
    // end to the list, and every entry is wrong for the next app.
    //
    // What generalizes is that macOS already classifies these. A transient
    // overlay is not "the downloads popup"; it is an AXPopover, an AXMenu, an
    // AXSheet or a dialog window. That is a closed set, published by the
    // system, and it does not grow when an app ships a new panel.
    //
    // So the agent does not learn WHICH overlays exist. It learns, per app and
    // per overlay signature, WHICH DISMISSAL WORKS — from the same act-episode
    // loop that already learns menus-versus-clicks. The knowledge is
    // "Safari のダウンロードポップオーバーは Escape で閉じる", and it is acquired by
    // trying, observing, and recording, not by being told.

    struct Obstruction {
        let role: String
        let title: String
        let element: AXUIElement
        /// What vera-a learns against. Not the app alone — one app has several
        /// overlays and they do not all close the same way.
        let signature: String
    }

    /// Roles macOS uses for things that sit on top of the content. Closed set,
    /// defined by the platform, so it does not need maintaining per app.
    private static let overlayRoles: Set<String> = [
        "AXMenu", "AXPopover", "AXSheet", "AXDrawer", "AXHelpTag"
    ]

    /// Overlays currently covering this app's content.
    static func obstructions(of appName: String) -> [Obstruction] {
        guard AXIsProcessTrusted(), let (ax, _) = appElement(appName) else { return [] }
        var found: [Obstruction] = []

        func scan(_ element: AXUIElement, depth: Int) {
            guard depth <= 4, found.count < 6 else { return }
            guard let children: [AXUIElement] = attr(element, kAXChildrenAttribute as String)
            else { return }
            for child in children {
                let role: String = attr(child, kAXRoleAttribute as String) ?? ""
                let subrole: String = attr(child, kAXSubroleAttribute as String) ?? ""
                let title: String = attr(child, kAXTitleAttribute as String)
                    ?? attr(child, kAXDescriptionAttribute as String) ?? ""

                if overlayRoles.contains(role) || subrole == "AXDialog" || subrole == "AXSystemDialog" {
                    found.append(Obstruction(
                        role: subrole.isEmpty ? role : subrole,
                        title: title,
                        element: child,
                        signature: "\(appName)|\(subrole.isEmpty ? role : subrole)|\(title.prefix(30))"))
                    continue    // do not descend into the overlay itself
                }
                scan(child, depth: depth + 1)
            }
        }
        scan(ax, depth: 1)

        // An open menu hangs off the menu bar rather than off a window.
        if let bar: AXUIElement = attr(ax, kAXMenuBarAttribute as String),
           let tops: [AXUIElement] = attr(bar, kAXChildrenAttribute as String) {
            for top in tops {
                guard let menus: [AXUIElement] = attr(top, kAXChildrenAttribute as String),
                      let menu = menus.first,
                      (attr(menu, "AXVisible") as Bool?) == true
                else { continue }
                let title: String = attr(top, kAXTitleAttribute as String) ?? ""
                found.append(Obstruction(role: "AXMenu", title: title, element: menu,
                                         signature: "\(appName)|AXMenu|\(title)"))
            }
        }
        return found
    }

    /// Ways to make an overlay go away, cheapest and safest first.
    ///
    /// Every move here must be incapable of CONFIRMING anything. Escape and a
    /// cancel button back out; pressing whatever button happens to be in the
    /// panel could accept a dialog the user never saw. That is why there is no
    /// "press the first button" move, even though it would close more things.
    enum Dismissal: String, CaseIterable {
        case escape       // ⎋ — backs out of nearly every transient overlay
        case cancelButton // the overlay's own cancel/close control
        case clickAway    // click empty space outside it

        var ja: String {
            switch self {
            case .escape:       return "Escape キー"
            case .cancelButton: return "閉じる/キャンセルボタン"
            case .clickAway:    return "外側をクリック"
            }
        }
    }

    /// Try one dismissal. Returns whether the overlay is gone afterwards —
    /// measured, not assumed, because "I pressed Escape" is not evidence.
    static func attempt(_ move: Dismissal, on obstruction: Obstruction,
                        in appName: String) -> Bool {
        switch move {
        case .escape:
            _ = sendShortcut(to: appName, combo: "esc")

        case .cancelButton:
            guard let button = findCancelLikeButton(in: obstruction.element) else { return false }
            AXUIElementPerformAction(button, kAXPressAction as CFString)

        case .clickAway:
            // Deliberately not implemented as a synthetic click here: a click
            // at an arbitrary point is the one move that can hit something
            // real. It stays declared so the model can be told it exists and
            // choose it explicitly with coordinates it has actually looked at.
            return false
        }

        usleep(400_000)
        return !obstructions(of: appName).contains { $0.signature == obstruction.signature }
    }

    /// Only controls that back out. Never OK, Delete, Send, Allow.
    private static func findCancelLikeButton(in element: AXUIElement) -> AXUIElement? {
        let safe = ["cancel", "close", "done", "dismiss", "not now",
                    "キャンセル", "閉じる", "完了", "あとで", "今はしない"]
        var result: AXUIElement?

        func walk(_ e: AXUIElement, depth: Int) {
            guard depth <= 3, result == nil else { return }
            guard let kids: [AXUIElement] = attr(e, kAXChildrenAttribute as String) else { return }
            for k in kids {
                if result != nil { return }
                let role: String = attr(k, kAXRoleAttribute as String) ?? ""
                let subrole: String = attr(k, kAXSubroleAttribute as String) ?? ""
                let title: String = attr(k, kAXTitleAttribute as String)
                    ?? attr(k, kAXDescriptionAttribute as String) ?? ""
                if subrole == "AXCloseButton" || subrole == "AXCancelButton" {
                    result = k; return
                }
                if role == kAXButtonRole as String,
                   safe.contains(where: { title.lowercased().contains($0) }) {
                    result = k; return
                }
                walk(k, depth: depth + 1)
            }
        }
        walk(element, depth: 1)
        return result
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
