//! Symbiotic MacOS Integration Bridge
//! End-Game BotGuard Evasion: Zero-DOM Architecture
//! Implements absolute OS spatial tracking and CoreGraphics biometric mouse drift.

use tokio::process::Command;
use tracing::info;

pub struct SafariBounds {
    pub x: i32,
    pub y: i32,
    pub width: i32,
    pub height: i32,
}

pub struct SymbioticMacOS;

impl SymbioticMacOS {
    /// Zero-DOM Phase 1: Retrieve the exact OS-level bounds of the frontmost Safari Window.
    pub async fn get_safari_bounds() -> Option<SafariBounds> {
        let script = r#"tell application "Safari" to get bounds of front window"#;
        let out = Command::new("osascript").arg("-e").arg(script).output().await.ok()?;
        let res = String::from_utf8_lossy(&out.stdout).trim().to_string();
        Self::parse_bounds(&res)
    }

    /// Zero-DOM Phase 1B: Retrieve the OS-level bounds of the Verantyx custom stealth browser.
    pub async fn get_custom_browser_bounds() -> Option<SafariBounds> {
        let script = r#"
        tell application "System Events"
            repeat with p in (every process)
                try
                    set w to window "vx-agent-stealth" of p
                    if w exists then
                        set pos to position of w
                        set sz to size of w
                        return (item 1 of pos) & "," & (item 2 of pos) & "," & ((item 1 of pos) + (item 1 of sz)) & "," & ((item 2 of pos) + (item 2 of sz))
                    end if
                end try
            end repeat
            return ""
        end tell
        "#;
        let out = Command::new("osascript").arg("-e").arg(script).output().await.ok()?;
        let res = String::from_utf8_lossy(&out.stdout).trim().to_string();
        Self::parse_bounds(&res)
    }

    fn parse_bounds(res: &str) -> Option<SafariBounds> {
        // Output format is typically "0, 25, 1440, 900" (x1, y1, x2, y2)
        let parts: Vec<&str> = res.split(',').collect();
        if parts.len() == 4 {
            let x1 = parts[0].trim().parse::<i32>().unwrap_or(0);
            let y1 = parts[1].trim().parse::<i32>().unwrap_or(0);
            let x2 = parts[2].trim().parse::<i32>().unwrap_or(0);
            let y2 = parts[3].trim().parse::<i32>().unwrap_or(0);
            if x2 > x1 && y2 > y1 {
                return Some(SafariBounds {
                    x: x1,
                    y: y1,
                    width: x2 - x1,
                    height: y2 - y1,
                });
            }
        }
        None
    }

    /// Zero-DOM Phase 2: Anchor Extraction.
    /// Injects a targeted script into Safari to read the exact geometric coordinates of the Blinking Text Cursor (Caret)
    /// representing the user's current spatial position.
    pub async fn get_caret_anchor_coordinates() -> Option<(f32, f32)> {
        let js = r#"
            let sel = window.getSelection();
            if (sel.rangeCount > 0) {
                let rect = sel.getRangeAt(0).getBoundingClientRect();
                rect.right + ',' + rect.bottom;
            } else {
                "0,0"
            }
        "#;
        let script = format!("tell application \"Safari\" to do JavaScript \"{}\" in front document", js);
        let out = Command::new("osascript").arg("-e").arg(script).output().await.ok()?;
        let res = String::from_utf8_lossy(&out.stdout).trim().to_string();
        
        let parts: Vec<&str> = res.split(',').collect();
        if parts.len() == 2 {
             let cx = parts[0].parse::<f32>().unwrap_or(0.0);
             let cy = parts[1].parse::<f32>().unwrap_or(0.0);
             if cx > 0.0 && cy > 0.0 {
                 return Some((cx, cy));
             }
        }
        None
    }

    /// Zero-DOM Phase 3: Biometric CoreGraphics Slide Path.
    /// Utilizes JXA to natively invoke CoreGraphics C-bindings.
    /// Traverses the mouse progressively across multiple waypoints starting securely from its CURRENT physical location.
    pub async fn drift_mouse_through_path(waypoints_str: &str) -> anyhow::Result<()> {
        let jxa_script = format!(
            r#"
            ObjC.import('CoreGraphics');
            ObjC.import('Foundation');
            ObjC.import('stdlib');

            // Eliminate 'teleportation' by starting exactly from the OS physical mouse pointer
            var currentPos = $.CGEventGetLocation($.CGEventCreate(null));
            
            var waypointsRaw = "{}";
            var waypoints = waypointsRaw.split(";").map(function(p) {{
                var coords = p.split(",");
                return {{x: parseFloat(coords[0]), y: parseFloat(coords[1])}};
            }});
            
            waypoints.unshift({{x: currentPos.x, y: currentPos.y}});
            
            var delayMs = 12000;
            var stepsPerSegment = 30;

            for (var w = 0; w < waypoints.length - 1; w++) {{
                var startPt = waypoints[w];
                var endPt = waypoints[w+1];
                
                for (var i = 1; i <= stepsPerSegment; i++) {{
                    var t = i / stepsPerSegment;
                    
                    var ease_t = t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
                    
                    var jitterX = (Math.random() - 0.5) * 3.0;
                    var jitterY = (Math.random() - 0.5) * 3.0;
                    if (i === stepsPerSegment) {{ jitterX = 0; jitterY = 0; }} 
                    
                    var cx = startPt.x + (endPt.x - startPt.x) * ease_t + jitterX;
                    var cy = startPt.y + (endPt.y - startPt.y) * ease_t + jitterY;
                    
                    var point = $.CGPointMake(cx, cy);
                    var event = $.CGEventCreateMouseEvent(
                        null, 
                        $.kCGEventMouseMoved, 
                        point, 
                        0
                    );
                    $.CGEventPost($.kCGHIDEventTap, event);
                    
                    delay((delayMs + (Math.random() * 5000)) / 1000000.0);
                }}
                
                // Human hesitation at node boundaries
                delay((Math.random() * 60000 + 40000) / 1000000.0);
            }}
            
            // Final destination -> Natural tension click
            delay(120000 / 1000000.0); 
            var finalPoint = $.CGPointMake(waypoints[waypoints.length - 1].x, waypoints[waypoints.length - 1].y);
            var clickDown = $.CGEventCreateMouseEvent(null, $.kCGEventLeftMouseDown, finalPoint, $.kCGMouseButtonLeft);
            var clickUp = $.CGEventCreateMouseEvent(null, $.kCGEventLeftMouseUp, finalPoint, $.kCGMouseButtonLeft);
            $.CGEventPost($.kCGHIDEventTap, clickDown);
            delay((Math.random() * 60000 + 30000) / 1000000.0);
            $.CGEventPost($.kCGHIDEventTap, clickUp);
            "#,
            waypoints_str
        );

        let script_path = std::env::temp_dir().join("symbiotic_drift.js");
        std::fs::write(&script_path, jxa_script)?;

        info!("[OS_BRIDGE] Engaging Multi-Waypoint Biometric Slide Path -> [{}]", waypoints_str);
        let out = Command::new("osascript")
            .arg("-l")
            .arg("JavaScript")
            .arg(script_path.to_str().unwrap())
            .output()
            .await?;
            
        if !out.status.success() {
            let err_msg = String::from_utf8_lossy(&out.stderr);
            println!("{} ❌ [FATAL] drift_mouse_through_path OSASCRIPT CRASHED:\n{}", console::style("[AUTO]").red(), err_msg);
            anyhow::bail!("JXA Script crashed: {}", err_msg);
        }
            
        Ok(())
    }

    /// Sets the macOS clipboard content using pbcopy.
    pub async fn set_clipboard(text: &str) -> anyhow::Result<()> {
        use std::process::Stdio;
        use tokio::io::AsyncWriteExt;
        
        let mut child = Command::new("pbcopy")
            .stdin(Stdio::piped())
            .spawn()?;

        if let Some(mut stdin) = child.stdin.take() {
            stdin.write_all(text.as_bytes()).await?;
        }

        child.wait().await?;
        Ok(())
    }

    /// Securely retrieves text from the macOS clipboard.
    pub async fn get_clipboard() -> anyhow::Result<String> {
        let out = Command::new("pbpaste").output().await?;
        Ok(String::from_utf8_lossy(&out.stdout).into_owned())
    }

    /// Zero-DOM Autonomous UI Sandbox: 
    /// Opens Safari in the background, loads a local server URL, bounds it, 
    /// takes a seamless hardware-accelerated Window screenshot to clipboard, and closes it.
    pub async fn capture_safari_viewport_to_clipboard(url: &str) -> anyhow::Result<()> {
        info!("[OS_BRIDGE] Spawning isolated Safari context for {}", url);
        
        let spawn_js = format!(
            r#"
            var safari = Application("Safari");
            var doc = safari.Document().make();
            doc.url = "{}";
            safari.windows[0].bounds = {{"x": 100, "y": 100, "width": 1280, "height": 800}};
            safari.windows[0].id();
            "#, 
            url
        );
        let spawn_path = std::env::temp_dir().join("sim_spawn.js");
        std::fs::write(&spawn_path, spawn_js)?;

        // Boot Safari Isolated Tab and Read Window ID
        let out = Command::new("osascript").arg("-l").arg("JavaScript").arg(spawn_path.to_str().unwrap()).output().await?;
        let win_id = String::from_utf8_lossy(&out.stdout).trim().to_string();
        
        // Ensure web app renders (React/Vue takes ~2-3 seconds usually locally)
        info!("[OS_BRIDGE] Engine rendering WebView...");
        tokio::time::sleep(tokio::time::Duration::from_millis(3500)).await;

        if !win_id.is_empty() {
            info!("[OS_BRIDGE] Capturing hardware window ID {} to clipboard", win_id);
            // -c: Send to clipboard, -x: Disable sound, -l: Capture specific window ID
            let _ = Command::new("screencapture")
                .arg("-c")
                .arg("-x")
                .arg("-l")
                .arg(&win_id)
                .output()
                .await?;
        }

        let cleanup_js = r#"
            var safari = Application("Safari");
            if (safari.windows.length > 0) {
                safari.windows[0].close();
            }
        "#;
        let cleanup_path = std::env::temp_dir().join("sim_cleanup.js");
        std::fs::write(&cleanup_path, cleanup_js)?;
        let _ = Command::new("osascript").arg("-l").arg("JavaScript").arg(cleanup_path.to_str().unwrap()).output().await?;

        Ok(())
    }

    /// Gets the name of the currently active macOS application.
    pub async fn get_active_app() -> Option<String> {
        let script = r#"tell application "System Events" to get name of first application process whose frontmost is true"#;
        let out = Command::new("osascript").arg("-e").arg(script).output().await.ok()?;
        let res = String::from_utf8_lossy(&out.stdout).trim().to_string();
        Some(res)
    }

    /// Forces a specific application to the foreground.
    pub async fn focus_app(app_name: &str) -> anyhow::Result<()> {
        let script = format!(r#"tell application "{}" to activate"#, app_name);
        Command::new("osascript").arg("-e").arg(&script).output().await?;
        Ok(())
    }

    /// Dynamically determines which of the 3 tiled Safari windows to focus based on their spatial bounds.
    pub async fn focus_safari_panel(position: &str) -> anyhow::Result<()> {
        let condition = match position {
            "left"   => "if xPos < 90 then",
            "middle" => "if xPos >= 90 and xPos < 190 then",
            "right"  => "if xPos >= 190 then",
            _        => "if xPos < 90 then",
        };
        
        let script = format!(r#"
            tell application "Safari"
                activate
                set winList to every window
                repeat with w in winList
                    try
                        set bnd to bounds of w
                        set xPos to item 1 of bnd
                        {}
                            set index of w to 1
                            set tabList to every tab of w
                            repeat with t in tabList
                                if URL of t contains "gemini.google.com" then
                                    set current tab of w to t
                                    exit repeat
                                end if
                            end repeat
                            exit repeat
                        end if
                    end try
                end repeat
            end tell
        "#, condition);

        tokio::process::Command::new("osascript").arg("-e").arg(&script).output().await?;
        Ok(())
    }

    /// Autonomously pastes clipboard content handling BotGuard without human intervention.
    /// Uses Legacy Return method (Fallback)
    pub async fn auto_paste_and_send() -> anyhow::Result<()> {
        let script = r#"
        tell application "System Events"
            -- Simulate Cmd+V (Paste)
            keystroke "v" using command down
            delay 0.5
            -- Simulate Return (Send to Gemini / LLM)
            keystroke return
        end tell
        "#;
        Command::new("osascript").arg("-e").arg(script).output().await?;
        Ok(())
    }

    /// Zero-DOM Phase 2: Visual Pointer Drop Calibration (Primary)
    /// Finds the send button by dropping visually from the edge of the active textarea 
    /// and scanning for the first "cursor: pointer" element (Pointing Hand).
    pub async fn auto_visual_calibrated_paste_and_send(_payload: &str) -> anyhow::Result<()> {
        info!("[OS_BRIDGE] Engaging Zero-DOM Visual Pointer-Drop Calibration for Text Input...");
        
        // Google injects hidden 1x1 dummy contenteditables. We find the real chat box by selecting the largest visible area.
        let focus_js = r#"
            (() => {
                let editables = document.querySelectorAll('textarea, [contenteditable="true"], rich-textarea');
                let target = null;
                let maxArea = -1;
                for (let el of editables) {
                    let rect = el.getBoundingClientRect();
                    let area = rect.width * rect.height;
                    // Exclude hidden elements or tiny traps
                    if (area > maxArea && rect.width > 50 && rect.height > 10) {
                        maxArea = area;
                        target = el;
                    }
                }
                if (target) {
                    let r = target.getBoundingClientRect();
                    return (r.left + (r.width / 2)) + "," + (r.top + (r.height / 2)) + "|" + window.innerWidth + "," + window.innerHeight + "|" + window.screenX + "," + window.screenY + "," + window.outerWidth + "," + window.outerHeight;
                } else {
                    return "";
                }
            })();
        "#;
        
        let focus_script = format!(r#"tell application "Safari" to do JavaScript "{}" in front document"#, focus_js.replace("\"", "\\\""));
        let focus_res = match Command::new("osascript").arg("-e").arg(&focus_script).output().await {
            Ok(out) => String::from_utf8_lossy(&out.stdout).trim().to_string(),
            Err(_) => String::new(),
        };

        let parse_coords = |res: &str| -> Option<(f32, f32, f32, f32, f32, f32, f32, f32)> {
            if res.is_empty() { return None; }
            let chunks: Vec<&str> = res.split('|').collect();
            if chunks.len() != 3 { return None; }
            
            let pos: Vec<&str> = chunks[0].split(',').collect();
            let size: Vec<&str> = chunks[1].split(',').collect();
            let bounds: Vec<&str> = chunks[2].split(',').collect();
            
            if pos.len() == 2 && size.len() == 2 && bounds.len() == 4 {
                let vx = pos[0].parse::<f32>().unwrap_or(0.0);
                let vy = pos[1].parse::<f32>().unwrap_or(0.0);
                let iw = size[0].parse::<f32>().unwrap_or(1000.0);
                let ih = size[1].parse::<f32>().unwrap_or(800.0);
                let bx = bounds[0].parse::<f32>().unwrap_or(0.0);
                let by = bounds[1].parse::<f32>().unwrap_or(0.0);
                let bw = bounds[2].parse::<f32>().unwrap_or(1440.0);
                let bh = bounds[3].parse::<f32>().unwrap_or(900.0);
                return Some((vx, vy, iw, ih, bx, by, bw, bh));
            }
            None
        };

        if let Some((vx, vy, iw, ih, bx, by, bw, bh)) = parse_coords(&focus_res) {
            let chrome_y = (bh - ih).max(0.0);
            let chrome_x = (bw - iw).max(0.0) / 2.0; 
            let os_x = bx + chrome_x + vx;
            let os_y = by + chrome_y + vy;

            info!("[OS_BRIDGE] Found Input Text Area semantically. Emulating Physical OS Click at X={}, Y={}", os_x, os_y);

            let ext_dance_script = format!(
                r#"
                ObjC.import('CoreGraphics');
                ObjC.import('stdlib');
                var delay = function(sec) {{ $.usleep(sec * 1000000); }};
                
                var targetPoint = $.CGPointMake({}, {});
                var slideToC = $.CGEventCreateMouseEvent(null, $.kCGEventMouseMoved, targetPoint, $.kCGMouseButtonLeft);
                $.CGEventPost($.kCGHIDEventTap, slideToC);
                delay(0.1); 
                
                var clickDown = $.CGEventCreateMouseEvent(null, $.kCGEventLeftMouseDown, targetPoint, $.kCGMouseButtonLeft);
                var clickUp = $.CGEventCreateMouseEvent(null, $.kCGEventLeftMouseUp, targetPoint, $.kCGMouseButtonLeft);
                $.CGEventPost($.kCGHIDEventTap, clickDown);
                delay(0.05);
                $.CGEventPost($.kCGHIDEventTap, clickUp);
                delay(0.3); // Give OS and Browser time to establish focus
                "#,
                os_x, os_y
            );

            let dance_path = std::env::temp_dir().join("symb_focus_dance.js");
            std::fs::write(&dance_path, ext_dance_script)?;
            
            let _ = Command::new("osascript").arg("-l").arg("JavaScript").arg(dance_path.to_str().unwrap()).output().await;
        } else {
            // Fallback natively to .focus() if not found
            let fallback_js = r#"tell application "Safari" to do JavaScript "let e = document.querySelector('textarea, [contenteditable=\"true\"], rich-textarea'); if(e) { e.focus(); }" in front document"#;
            let _ = Command::new("osascript").arg("-e").arg(fallback_js).output().await;
            tokio::time::sleep(tokio::time::Duration::from_millis(500)).await;
        }

        info!("[OS_BRIDGE] Selected Strategy: Keyboard OS Submission (100% probability for maximum stability)");
        let paste_script = r#"
        tell application "System Events"
            keystroke "v" using command down
            delay 1.5
            keystroke return using command down
            delay 0.5
            keystroke return
        end tell
        "#;
        Command::new("osascript").arg("-e").arg(paste_script).output().await?;
        Ok(())
    }

    /// Primary Extraction Method (User Verified Visual Tracking approach):
    /// 1. Type `========` to mark caret.
    /// 2. Get active Caret coordinates (X, Y).
    /// 3. Move UP from Caret and Click (to focus out of input box). Guarantee blur.
    /// 4. Cmd+Down to scroll to very bottom.
    /// 5. Scan UP from Caret (Y) until CSS 'pointer' becomes active to find the true Copy Button.
    /// 6. Move OS cursor to Copy Button -> Click.
    /// 7. Move OS cursor back to Caret -> Click.
    /// 8. Cmd+A -> Delete.
    /// Zero-DOM Phase 2: Visual Pointer Drop Calibration for Extraction (Copy Button)
    /// Finds the "Copy" button semantically or geometrically and fires an OS click at its physical location.
    pub async fn auto_visual_calibrated_extract_and_cleanup() -> anyhow::Result<()> {
        info!("[OS_BRIDGE] Engaging Zero-DOM Semantic & Geometric Calibration for Extraction...");

        // Unfocus active element to prevent any typing or weird viewport scrolling loops
        let blur_script = r#"tell application "Safari" to do JavaScript "if (document.activeElement) { document.activeElement.blur(); }" in front document"#;
        let _ = Command::new("osascript").arg("-e").arg(blur_script).output().await?;

        // Fast scroll to bottom to ensure the latest AI response copy button is firmly inside the viewport
        let scroll_script = r#"
        tell application "System Events"
            key code 125 using command down
            delay 0.5
        end tell
        "#;
        Command::new("osascript").arg("-e").arg(scroll_script).output().await?;

        // Semantic & Geometric Scan for the "Copy" button - Pass 1 (Identify and Scroll)
        // We find the LAST "Copy" button in the DOM tree (which is the most recent AI response),
        // and scroll it firmly into the center of the viewport so we can physically click it.
        let scan_and_scroll_js = r#"
            (() => {
                let btns = Array.from(document.querySelectorAll('[role="button"], button, [aria-label], [data-tooltip], a'));
                let targetBtn = null;
                let maxTop = -1;
                
                for (let b of btns) {
                    let r = b.getBoundingClientRect();
                    // MUST be visibly rendered and button-sized
                    if (r.width > 0 && r.height > 0 && r.width < 250 && r.height < 150) {
                        let textRep = Array.from(b.attributes).map(a => (a.value || "").toLowerCase()).join(" ") + " " + (b.innerHTML || "").toLowerCase();
                        let isCopy = textRep.includes('コピー') || textRep.includes('copy');
                        
                        if (isCopy) {
                            if (r.top > maxTop) {
                                maxTop = r.top;
                                targetBtn = b;
                            }
                        }
                    }
                }
                
                if (targetBtn) {
                    targetBtn.scrollIntoView({ block: "center", inline: "center", behavior: "instant" });
                    return "FOUND";
                } else {
                    return "NOT_FOUND";
                }
            })();
        "#;

        let measure_script1 = format!(r#"tell application "Safari" to do JavaScript "{}" in front document"#, scan_and_scroll_js.replace("\"", "\\\""));
        let scroll_res = match Command::new("osascript").arg("-e").arg(&measure_script1).output().await {
            Ok(out) => String::from_utf8_lossy(&out.stdout).trim().to_string(),
            Err(_) => String::new(),
        };

        if scroll_res != "FOUND" {
            anyhow::bail!("Semantic Cursor Extraction Failed: Could not locate 'Copy' button via DOM topology.");
        }

        // Wait for the browser's scroll layout to settle
        tokio::time::sleep(tokio::time::Duration::from_millis(500)).await;

        // Semantic & Geometric Scan - Pass 2 (Calculate Viewport Coordinates)
        let get_coords_js = r#"
            (() => {
                let btns = Array.from(document.querySelectorAll('[role="button"], button, [aria-label], [data-tooltip], a'));
                let targetBtn = null;
                let maxTop = -1;
                
                for (let b of btns) {
                    let r = b.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0 && r.width < 250 && r.height < 150) {
                        let textRep = Array.from(b.attributes).map(a => (a.value || "").toLowerCase()).join(" ") + " " + (b.innerHTML || "").toLowerCase();
                        let isCopy = textRep.includes('コピー') || textRep.includes('copy');
                        
                        if (isCopy) {
                            if (r.top > maxTop) {
                                maxTop = r.top;
                                targetBtn = b;
                            }
                        }
                    }
                }
                
                if (targetBtn) {
                    let r = targetBtn.getBoundingClientRect();
                    return (r.left + (r.width / 2)) + "," + (r.top + (r.height / 2)) + "|" + window.innerWidth + "," + window.innerHeight + "|" + window.screenX + "," + window.screenY + "," + window.outerWidth + "," + window.outerHeight;
                } else {
                    return "";
                }
            })();
        "#;

        let measure_script2 = format!(r#"tell application "Safari" to do JavaScript "{}" in front document"#, get_coords_js.replace("\"", "\\\""));
        let copy_res = match Command::new("osascript").arg("-e").arg(&measure_script2).output().await {
            Ok(out) => String::from_utf8_lossy(&out.stdout).trim().to_string(),
            Err(_) => String::new(),
        };

        let parse_coords = |res: &str| -> Option<(f32, f32, f32, f32, f32, f32, f32, f32)> {
            if res.is_empty() { return None; }
            let chunks: Vec<&str> = res.split('|').collect();
            if chunks.len() != 3 { return None; }
            
            let pos: Vec<&str> = chunks[0].split(',').collect();
            let size: Vec<&str> = chunks[1].split(',').collect();
            let bounds: Vec<&str> = chunks[2].split(',').collect();
            
            if pos.len() == 2 && size.len() == 2 && bounds.len() == 4 {
                let vx = pos[0].parse::<f32>().unwrap_or(0.0);
                let vy = pos[1].parse::<f32>().unwrap_or(0.0);
                let iw = size[0].parse::<f32>().unwrap_or(1000.0);
                let ih = size[1].parse::<f32>().unwrap_or(800.0);
                let bx = bounds[0].parse::<f32>().unwrap_or(0.0);
                let by = bounds[1].parse::<f32>().unwrap_or(0.0);
                let bw = bounds[2].parse::<f32>().unwrap_or(1440.0);
                let bh = bounds[3].parse::<f32>().unwrap_or(900.0);
                return Some((vx, vy, iw, ih, bx, by, bw, bh));
            }
            None
        };

        if let Some((vx, vy, iw, ih, bx, by, bw, bh)) = parse_coords(&copy_res) {
            // Calculate Safari Titlebar/Toolbar height and side borders using pure DOM constraints
            let chrome_y = (bh - ih).max(0.0);
            let chrome_x = (bw - iw).max(0.0) / 2.0; 
            
            let os_x = bx + chrome_x + vx;
            let os_y = by + chrome_y + vy;

            info!("[OS_BRIDGE] Found Copy Button Object semantically. Emulating Physical OS Click at X={}, Y={}", os_x, os_y);

            let ext_dance_script = format!(
                r#"
                ObjC.import('CoreGraphics');
                ObjC.import('stdlib');
                
                var delay = function(sec) {{ $.usleep(sec * 1000000); }};
                
                // Move directly to the calculated Copy button point
                var copyPoint = $.CGPointMake({}, {});
                var slideToC = $.CGEventCreateMouseEvent(null, $.kCGEventMouseMoved, copyPoint, $.kCGMouseButtonLeft);
                $.CGEventPost($.kCGHIDEventTap, slideToC);
                delay(0.2); 
                
                // Execute hardware-level left click
                var clickDown = $.CGEventCreateMouseEvent(null, $.kCGEventLeftMouseDown, copyPoint, $.kCGMouseButtonLeft);
                var clickUp = $.CGEventCreateMouseEvent(null, $.kCGEventLeftMouseUp, copyPoint, $.kCGMouseButtonLeft);
                $.CGEventPost($.kCGHIDEventTap, clickDown);
                delay(0.05);
                $.CGEventPost($.kCGHIDEventTap, clickUp);
                
                // Give OS and browser clipboard a moment to sync
                delay(1.0); 

                // Move mouse away to the menu bar area to prevent hover tooltips from obstructing UI
                var safePoint = $.CGPointMake(80, 10);
                var slideAway = $.CGEventCreateMouseEvent(null, $.kCGEventMouseMoved, safePoint, $.kCGMouseButtonLeft);
                $.CGEventPost($.kCGHIDEventTap, slideAway);
                delay(0.2);
                "#,
                os_x, os_y
            );

            let dance_path = std::env::temp_dir().join("symb_dance.js");
            std::fs::write(&dance_path, ext_dance_script)?;
            
            let out = Command::new("osascript").arg("-l").arg("JavaScript").arg(dance_path.to_str().unwrap()).output().await?;
            if !out.status.success() {
                let err_msg = String::from_utf8_lossy(&out.stderr);
                anyhow::bail!("[FATAL] ext_dance_script failed: {}", err_msg);
            }

            info!("[OS_BRIDGE] Geometric Extractor completed successfully.");
            info!("[OS_BRIDGE] Geometric Extractor completed successfully.");
            return Ok(());
        }

        anyhow::bail!("Semantic Cursor Extraction Failed: Could not locate 'Copy' button via DOM topology.");
    }

    /// Focuses a specific Safari Window. Used for Swarm parallelization to bring the window into physical view before Cmd+V.
    pub async fn focus_safari_window(window_index: usize) -> anyhow::Result<()> {
        let script = format!(
            r#"tell application "Safari"
                activate
                set index of window {} to 1
            end tell"#,
            window_index
        );
        let _ = Command::new("osascript").arg("-e").arg(script).output().await?;
        Ok(())
    }

    /// Brings the Terminal application hosting this CLI back to the front to prompt the user.
    pub fn bring_terminal_to_front() {
        let term_prog = std::env::var("TERM_PROGRAM").unwrap_or_else(|_| "Terminal".to_string());
        let app_name = match term_prog.as_str() {
            "iTerm.app" => "iTerm",
            "Apple_Terminal" => "Terminal",
            "vscode" => "Code",
            "Zed" => "Zed",
            "Ghostty" => "Ghostty",
            "Alacritty" => "Alacritty",
            "WezTerm" => "WezTerm",
            _ => "Terminal", // Fallback
        };
        let script = format!("tell application \"{}\" to activate", app_name);
        let _ = std::process::Command::new("osascript").arg("-e").arg(script).spawn();
    }
}
