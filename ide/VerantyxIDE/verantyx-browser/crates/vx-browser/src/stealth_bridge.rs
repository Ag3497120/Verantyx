use serde::{Deserialize, Serialize};
use std::io::{self, BufRead, Write};
use std::sync::{Arc, Mutex};
use tao::{
    event::{Event, WindowEvent},
    event_loop::{ControlFlow, EventLoopBuilder},
    window::WindowBuilder,
};
use wry::WebViewBuilder;
use std::thread;

/// Command from Swift BrowserBridge → Rust stealth_bridge
#[derive(Debug, Deserialize)]
pub struct BridgeCommand {
    pub cmd:  String,
    pub url:  Option<String>,
    pub id:   Option<u64>,   // リクエスト ID — レスポンスにエコーバック
    pub text: Option<String>,
    pub entropy: Option<Vec<[f64; 2]>>, // Human mouse movements
    pub keyboard_entropy: Option<Vec<f64>>, // Human keystroke timings
    pub target: Option<[f64; 2]>,       // Target coordinates from Vision Model
}

/// Response from Rust stealth_bridge → Swift BrowserBridge
#[derive(Debug, Serialize)]
pub struct BridgeResponse {
    pub id:       Option<u64>,   // ← New: リクエスト ID エコーバック
    pub status:   String,
    pub message:  Option<String>,
    pub url:      Option<String>,
    pub title:    Option<String>,
    pub markdown: Option<String>,
}

// ── JSON 1行出力ヘルパー ────────────────────────────────────────────────────
macro_rules! emit {
    ($resp:expr) => {{
        println!("{}", serde_json::to_string(&$resp).unwrap());
        std::io::stdout().flush().unwrap();
    }};
}

pub fn run_event_loop(visible: bool) -> anyhow::Result<()> {
    let event_loop = EventLoopBuilder::<BridgeCommand>::with_user_event().build();
    let proxy      = event_loop.create_proxy();

    // ── IPC ハンドラーとイベントループ間でリクエスト ID を共有 ─────────────
    let pending_id: Arc<Mutex<Option<u64>>> = Arc::new(Mutex::new(None));
    let pending_id_ipc = Arc::clone(&pending_id);

    // ── stdin リーダースレッド ─────────────────────────────────────────────
    let proxy_for_reader = proxy.clone();
    thread::spawn(move || {
        let stdin  = io::stdin();
        let reader = stdin.lock();
        for line_res in reader.lines() {
            if let Ok(line) = line_res {
                if let Ok(cmd) = serde_json::from_str::<BridgeCommand>(&line) {
                    if proxy_for_reader.send_event(cmd).is_err() { break; }
                }
            }
        }
    });

    // ── ステルスウィンドウ ─────────────────────────────────────────────────
    let window = WindowBuilder::new()
        .with_title("vx-agent-stealth")
        .with_visible(visible)
        .build(&event_loop)?;

    // ── 初期化 JS: readyState + 300ms ネットワーク静止検知 ───────────────
    // 旧: MutationObserver 固定2秒 → 新: document.readyState 完了後 300ms 安定で通知
    let init_js = r#"
        (function() {
            let networkTimer = null;

            const observer = new MutationObserver(() => { scheduleIdleCheck(); });

            function scheduleIdleCheck() {
                if (networkTimer) clearTimeout(networkTimer);
                networkTimer = setTimeout(() => {
                    if (document.readyState === 'complete' || document.readyState === 'interactive') {
                        notifyDone();
                    }
                }, 300);
            }

            function notifyDone() {
                if (window.__vx_notified) return;
                window.__vx_notified = true;
                observer.disconnect();
                window.ipc.postMessage('HITL_DONE:' + document.documentElement.outerHTML);
            }

            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', () => {
                    observer.observe(document.body || document.documentElement,
                        { childList: true, subtree: true, characterData: true });
                    scheduleIdleCheck();
                    window.ipc.postMessage('PAGE_READY:1');
                });
            } else {
                observer.observe(document.body || document.documentElement,
                    { childList: true, subtree: true, characterData: true });
                scheduleIdleCheck();
                window.ipc.postMessage('PAGE_READY:1');
            }

            // フォールバック: 10秒で強制送信
            setTimeout(notifyDone, 10000);
        })();
    "#;

    // ── WebView 構築 ───────────────────────────────────────────────────────
    let webview = WebViewBuilder::new()
        .with_initialization_script(init_js)
        .with_ipc_handler(move |req: wry::http::Request<String>| {
            let body = req.into_body();
            let id   = *pending_id_ipc.lock().unwrap();

            if body.starts_with("DOM:") {
                let md = html2md::parse_html(&body[4..]);
                emit!(BridgeResponse { id, status: "ok".into(), message: None, url: None, title: None, markdown: Some(md) });

            } else if body.starts_with("RAW_DOM:") {
                emit!(BridgeResponse { id, status: "raw_dom".into(), message: Some(body[8..].to_string()), url: None, title: None, markdown: None });

            } else if body.starts_with("HITL_DONE:") {
                let md = html2md::parse_html(&body[10..]);
                emit!(BridgeResponse { id, status: "hitl_done".into(), message: None, url: None, title: None, markdown: Some(md) });

            } else if body.starts_with("PAGE_READY:") {
                emit!(BridgeResponse { id, status: "ok".into(), message: Some("ready".into()), url: None, title: None, markdown: None });

            } else if body.starts_with("EVAL_RES:") {
                emit!(BridgeResponse { id, status: "eval_ok".into(), message: Some(body[9..].to_string()), url: None, title: None, markdown: None });

            } else if body.starts_with("EVAL_ERR:") {
                emit!(BridgeResponse { id, status: "eval_err".into(), message: Some(body[9..].to_string()), url: None, title: None, markdown: None });
            }
        })
        .with_html("<html><body><div id='vx-ready'></div></body></html>")
        .build(&window)?;

    // ── イベントループ ─────────────────────────────────────────────────────
    let proxy_for_typing = proxy.clone();
    event_loop.run(move |event, _, control_flow| {
        *control_flow = ControlFlow::Wait;

        match event {
            Event::UserEvent(cmd) => {
                // pending_id を更新 → 次の IPC レスポンスに付与される
                if let Some(cmd_id) = cmd.id {
                    *pending_id.lock().unwrap() = Some(cmd_id);
                }

                match cmd.cmd.as_str() {
                    "navigate" => {
                        if let Some(url) = cmd.url {
                            let _ = webview.evaluate_script("window.__vx_notified = false;");
                            
                            if let Some(entropy) = cmd.entropy {
                                // Native macOS CoreGraphics Trajectory Playback
                                let target_clone = cmd.target;
                                let url_clone = url.clone();
                                
                                // Launch trajectory thread
                                thread::spawn(move || {
                                    if entropy.len() < 2 { return; }
                                    
                                    use core_graphics::event::{CGEvent, CGEventType, CGMouseButton};
                                    use core_graphics::event_source::{CGEventSource, CGEventSourceStateID};
                                    use core_graphics::geometry::CGPoint;
                                    use core_graphics::event::{CGEventTap, CGEventTapLocation, CGEventTapPlacement, CGEventTapOptions};
                                    use core_foundation::runloop::CFRunLoop;
                                    use std::time::{Duration, SystemTime, UNIX_EPOCH};
                                    use std::sync::mpsc;
                                    
                                    let (tx, rx) = mpsc::channel();
                                    
                                    // Step 1: Tap thread to drop physical HID inputs
                                    thread::spawn(move || {
                                        let tap_res = CGEventTap::new(
                                            CGEventTapLocation::HID,
                                            CGEventTapPlacement::HeadInsertEventTap,
                                            CGEventTapOptions::Default,
                                            vec![
                                                CGEventType::MouseMoved,
                                                CGEventType::LeftMouseDown, CGEventType::LeftMouseUp, CGEventType::LeftMouseDragged,
                                                CGEventType::RightMouseDown, CGEventType::RightMouseUp, CGEventType::RightMouseDragged,
                                                CGEventType::ScrollWheel
                                            ],
                                            |_proxy, _type, _event| {
                                                // Drop the physical hardware event
                                                None
                                            }
                                        );
                                        
                                        if let Ok(tap) = tap_res {
                                            let loop_source = tap.mach_port.create_runloop_source(0).unwrap();
                                            let current_loop = CFRunLoop::get_current();
                                            current_loop.add_source(&loop_source, unsafe { core_foundation::runloop::kCFRunLoopCommonModes });
                                            tap.enable();
                                            
                                            // Send the run_loop instance to the playback thread
                                            let _ = tx.send(Some(current_loop));
                                            
                                            CFRunLoop::run_current();
                                        } else {
                                            let _ = tx.send(None);
                                        }
                                    });
                                    
                                    let tap_run_loop = rx.recv().unwrap_or(None);
                                    
                                    let source = CGEventSource::new(CGEventSourceStateID::HIDSystemState).unwrap();
                                    
                                    let o_start = entropy[0];
                                    let o_end = entropy[entropy.len() - 1];
                                    let dx = o_end[0] - o_start[0];
                                    let dy = o_end[1] - o_start[1];
                                    let mut orig_dist = (dx*dx + dy*dy).sqrt();
                                    if orig_dist < 1.0 { orig_dist = 1.0; }
                                    let orig_angle = dy.atan2(dx);
                                    
                                    // Start from random screen location or near center
                                    let t_start_x = 200.0;
                                    let t_start_y = 200.0;
                                    
                                    // Target (Vision Model) or fallback
                                    let (t_end_x, t_end_y) = if let Some(t) = target_clone {
                                        (t[0], t[1])
                                    } else {
                                        (500.0, 500.0)
                                    };
                                    
                                    let t_dx = t_end_x - t_start_x;
                                    let t_dy = t_end_y - t_start_y;
                                    let target_dist = (t_dx*t_dx + t_dy*t_dy).sqrt();
                                    let target_angle = t_dy.atan2(t_dx);
                                    
                                    let scale = target_dist / orig_dist;
                                    let rotation = target_angle - orig_angle;
                                    let cos_r = rotation.cos();
                                    let sin_r = rotation.sin();
                                    
                                    let mut transformed = Vec::new();
                                    for p in entropy.iter() {
                                        let x = p[0] - o_start[0];
                                        let y = p[1] - o_start[1];
                                        let rx = x * cos_r - y * sin_r;
                                        let ry = x * sin_r + y * cos_r;
                                        transformed.push(CGPoint::new(t_start_x + rx * scale, t_start_y + ry * scale));
                                    }
                                    
                                    for point in transformed.iter() {
                                        if let Ok(event) = CGEvent::new_mouse_event(source.clone(), CGEventType::MouseMoved, *point, CGMouseButton::Left) {
                                            // Post at Session level so our injected events bypass the HID tap
                                            event.post(CGEventTapLocation::Session);
                                        }
                                        
                                        // Random jitter 5-15ms
                                        let nanos = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().subsec_nanos();
                                        let delay = (nanos % 10) + 5;
                                        thread::sleep(Duration::from_millis(delay as u64));
                                    }
                                    
                                    // Step 4: Micro-delay click at the final destination
                                    if let Some(final_point) = transformed.last() {
                                        // MouseDown
                                        if let Ok(event) = CGEvent::new_mouse_event(source.clone(), CGEventType::LeftMouseDown, *final_point, CGMouseButton::Left) {
                                            event.post(CGEventTapLocation::Session);
                                        }
                                        
                                        // Natural click hold duration (50-100ms)
                                        let hold_delay = (SystemTime::now().duration_since(UNIX_EPOCH).unwrap().subsec_nanos() % 50) + 50;
                                        thread::sleep(Duration::from_millis(hold_delay as u64));
                                        
                                        // MouseUp
                                        if let Ok(event) = CGEvent::new_mouse_event(source.clone(), CGEventType::LeftMouseUp, *final_point, CGMouseButton::Left) {
                                            event.post(CGEventTapLocation::Session);
                                        }
                                    }
                                    
                                    // Release the physical input lock
                                    if let Some(rl) = tap_run_loop {
                                        rl.stop();
                                    }
                                });
                                
                                // Navigate immediately - the ghost mouse will move during page load!
                                webview.load_url(&url);
                            } else {
                                webview.load_url(&url);
                            }
                            
                            let id = *pending_id.lock().unwrap();
                            emit!(BridgeResponse { id, status: "navigating".into(), message: Some("started".into()), url: None, title: None, markdown: None });
                        }
                    }
                    "get_page" => {
                        let _ = webview.evaluate_script(
                            "(function(){window.ipc.postMessage('DOM:'+document.documentElement.outerHTML);})();"
                        );
                    }
                    "get_raw_page" => {
                        let _ = webview.evaluate_script(
                            "(function(){window.ipc.postMessage('RAW_DOM:'+document.documentElement.outerHTML);})();"
                        );
                    }
                    "type_text" => {
                        if let Some(text) = cmd.text {
                            let kb_entropy = cmd.keyboard_entropy.clone().unwrap_or_default();
                            let proxy_clone = proxy_for_typing.clone();
                            thread::spawn(move || {
                                use core_graphics::event::{CGEvent, CGEventType, CGMouseButton};
                                use core_graphics::event_source::{CGEventSource, CGEventSourceStateID};
                                use std::time::Duration;
                                
                                let source = CGEventSource::new(CGEventSourceStateID::HIDSystemState).unwrap();
                                let chars: Vec<char> = text.chars().collect();
                                
                                // Create an infinite iterator over the entropy delays, fallback to 50ms
                                let mut delays = kb_entropy.into_iter().chain(std::iter::repeat(0.05));
                                
                                for c in chars {
                                    let mut buf = [0; 4];
                                    let s = c.encode_utf8(&mut buf);
                                    
                                    let delay_secs = delays.next().unwrap_or(0.05);
                                    
                                    // Split the delay: 30% for key down hold duration, 70% for pause before next key
                                    let hold_duration = (delay_secs * 0.3).max(0.01);
                                    let pause_duration = (delay_secs * 0.7).max(0.01);
                                    
                                    // OS-Level Dummy Event (to generate physical keyboard entropy logs for bot detection)
                                    // We use keycode 0 ('a') as a dummy, it is sent to the OS level but may miss the browser
                                    if let Ok(event) = CGEvent::new_keyboard_event(source.clone(), 0, true) {
                                        event.set_string(s);
                                        event.post(core_graphics::event::CGEventTapLocation::Session);
                                    }
                                    
                                    // Hold delay (natural human keystroke dwell time)
                                    thread::sleep(Duration::from_secs_f64(hold_duration));
                                    
                                    // JS Injection (Guarantees the text actually appears in the focused input field)
                                    let js_val = serde_json::to_string(&s).unwrap();
                                    let js = format!(
                                        "var el = document.activeElement; if (el && typeof el.value !== 'undefined') {{ el.value += {}; el.dispatchEvent(new Event('input', {{ bubbles: true }})); }}",
                                        js_val
                                    );
                                    let _ = proxy_clone.send_event(BridgeCommand {
                                        cmd: "eval_js".into(),
                                        url: None,
                                        id: None,
                                        text: Some(js),
                                        entropy: None,
                                        keyboard_entropy: None,
                                        target: None,
                                    });
                                    
                                    // KeyUp
                                    if let Ok(event) = CGEvent::new_keyboard_event(source.clone(), 0, false) {
                                        event.set_string(s);
                                        event.post(core_graphics::event::CGEventTapLocation::Session);
                                    }
                                    
                                    // Pause before next keystroke
                                    thread::sleep(Duration::from_secs_f64(pause_duration));
                                }
                            });
                            
                            let id = *pending_id.lock().unwrap();
                            emit!(BridgeResponse { id, status: "ok".into(), message: Some("typed".into()), url: None, title: None, markdown: None });
                        }
                    }
                    "eval_js" => {
                        if let Some(script) = cmd.text {
                            let wrapped = format!(r#"
                                (function(){{
                                    try{{let r=(function(){{{script}}})();if(r!==undefined)window.ipc.postMessage('EVAL_RES:'+r);}}
                                    catch(e){{window.ipc.postMessage('EVAL_ERR:'+e.toString());}}
                                }})();
                            "#);
                            let _ = webview.evaluate_script(&wrapped);
                        }
                    }
                    "ping" => {
                        let id = *pending_id.lock().unwrap();
                        emit!(BridgeResponse { id, status: "pong".into(), message: Some("alive".into()), url: None, title: None, markdown: None });
                    }
                    "quit" => {
                        *control_flow = ControlFlow::Exit;
                        std::process::exit(0);
                    }
                    _ => {}
                }
            }
            Event::WindowEvent { event: WindowEvent::CloseRequested, .. } => {
                *control_flow = ControlFlow::Exit;
            }
            _ => {}
        }
    });
}
