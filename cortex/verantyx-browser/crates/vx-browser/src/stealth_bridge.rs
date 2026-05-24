use serde::{Deserialize, Serialize};
use std::io::{self, BufRead, Write};
use tao::{
    event::{Event, WindowEvent},
    event_loop::{ControlFlow, EventLoop, EventLoopBuilder, EventLoopProxy},
    window::WindowBuilder,
};
use wry::{WebViewBuilder};
use crossbeam_channel::{unbounded, Receiver};
use std::thread;

/// Command from Orchestrator (TypeScript) -> Rust Bridge -> JS
#[derive(Debug, Deserialize)]
pub struct BridgeCommand {
    pub cmd: String,
    pub url: Option<String>,
    pub id: Option<u64>,
    pub text: Option<String>,
}

/// Response from Rust Bridge -> Orchestrator (TypeScript)
#[derive(Debug, Serialize)]
pub struct BridgeResponse {
    pub status: String,
    pub message: Option<String>,
    pub url: Option<String>,
    pub title: Option<String>,
    pub markdown: Option<String>,
}

pub fn run_event_loop(visible: bool) -> anyhow::Result<()> {
    // macOS requires EventLoop on the absolute main thread
    let event_loop = EventLoopBuilder::<BridgeCommand>::with_user_event().build();
    let proxy = event_loop.create_proxy();

    // Spawn stdin reader thread so we never block the UI thread waiting for TS Orchestrator commands
    thread::spawn(move || {
        let stdin = io::stdin();
        let reader = stdin.lock();
        
        for line_res in reader.lines() {
            if let Ok(line) = line_res {
                if let Ok(cmd) = serde_json::from_str::<BridgeCommand>(&line) {
                    if proxy.send_event(cmd).is_err() {
                        break;
                    }
                }
            }
        }
    });

    // Stealth Window (now conditionally visible)
    let window = WindowBuilder::new()
        .with_title("vx-agent-stealth")
        .with_visible(visible) // <--- Modified for Fallback Acquisition
        .build(&event_loop)?;

    let init_js = r#"
        window.addEventListener('DOMContentLoaded', () => {
            if (window.ipc && window.ipc.postMessage) {
                window.ipc.postMessage('PAGE_READY:1');
            }
            
            let timeout = null;
            const config = { childList: true, subtree: true, characterData: true };
            const callback = function(mutationsList, observer) {
                if (timeout) clearTimeout(timeout);
                timeout = setTimeout(() => {
                    if (window.ipc && window.ipc.postMessage) {
                        let html = document.documentElement.outerHTML;
                        window.ipc.postMessage('HITL_DONE:' + html);
                    }
                }, 2000);
            };
            const observer = new MutationObserver(callback);
            observer.observe(document.body, config);
        });
    "#;

    let webview = WebViewBuilder::new()
        .with_initialization_script(init_js)
        .with_ipc_handler(|req: wry::http::Request<String>| {
            let body = req.into_body();
            // JS `window.ipc.postMessage(...)` hits this
            if body.starts_with("DOM:") {
                let html = &body[4..];
                let markdown = html2md::parse_html(html);
                
                let resp = BridgeResponse {
                    status: "ok".into(),
                    message: None,
                    url: None,
                    title: None,
                    markdown: Some(markdown),
                };
                println!("{}", serde_json::to_string(&resp).unwrap()); std::io::stdout().flush().unwrap();
            } else if body.starts_with("RAW_DOM:") {
                let html = &body[8..];
                let resp = BridgeResponse {
                    status: "raw_dom".into(),
                    message: Some(html.to_string()),
                    url: None,
                    title: None,
                    markdown: None,
                };
                println!("{}", serde_json::to_string(&resp).unwrap()); std::io::stdout().flush().unwrap();
            } else if body.starts_with("HITL_DONE:") {
                let html = &body[10..];
                let markdown = html2md::parse_html(html);
                
                let resp = BridgeResponse {
                    status: "hitl_done".into(),
                    message: None,
                    url: None,
                    title: None,
                    markdown: Some(markdown),
                };
                println!("{}", serde_json::to_string(&resp).unwrap()); std::io::stdout().flush().unwrap();
            } else if body.starts_with("PAGE_READY:") {
                // Signals that the background blank DOM is fully loaded and ready for javascript evaluation
                println!(r#"{{"status":"ok","message":"ready"}}"#); std::io::stdout().flush().unwrap();
            } else if body.starts_with("EVAL_RES:") {
                let res = &body[9..];
                let resp = BridgeResponse {
                    status: "eval_ok".into(),
                    message: Some(res.to_string()),
                    url: None,
                    title: None,
                    markdown: None,
                };
                println!("{}", serde_json::to_string(&resp).unwrap()); std::io::stdout().flush().unwrap();
            } else if body.starts_with("EVAL_ERR:") {
                let err = &body[9..];
                let resp = BridgeResponse {
                    status: "eval_err".into(),
                    message: Some(err.to_string()),
                    url: None,
                    title: None,
                    markdown: None,
                };
                println!("{}", serde_json::to_string(&resp).unwrap()); std::io::stdout().flush().unwrap();
            }
        })
        .with_html("<html><body><div id='vx-ready'></div></body></html>")
        .build(&window)?;

    // The readiness is now sent via PAGE_READY IPC trigger, NOT here synchronously.

    event_loop.run(move |event, _, control_flow| {
        *control_flow = ControlFlow::Wait;

        match event {
            Event::UserEvent(cmd) => {
                match cmd.cmd.as_str() {
                    "navigate" => {
                        if let Some(url) = cmd.url {
                            webview.load_url(&url);
                            let resp = BridgeResponse { status: "ok".into(), message: Some("Navigated".into()), url: None, title: None, markdown: None };
                            println!("{}", serde_json::to_string(&resp).unwrap()); std::io::stdout().flush().unwrap();
                        }
                    }
                    "get_page" => {
                        // Extract DOM natively and post safely over IPC buffer
                        let js = r#"
                            (function() {
                                let html = document.documentElement.outerHTML;
                                window.ipc.postMessage('DOM:' + html);
                            })();
                        "#;
                        let _ = webview.evaluate_script(js);
                    }
                    "get_raw_page" => {
                        let js = r#"
                            (function() {
                                let html = document.documentElement.outerHTML;
                                window.ipc.postMessage('RAW_DOM:' + html);
                            })();
                        "#;
                        let _ = webview.evaluate_script(js);
                    }
                    "eval_js" => {
                        // Evaluate arbitrary JavaScript for Native Loop Driving
                        if let Some(script) = cmd.text {
                            let wrapped_js = format!(r#"
                                (function() {{
                                    try {{
                                        let res = (function() {{ {} }})();
                                        if (res !== undefined) {{
                                            window.ipc.postMessage('EVAL_RES:' + res);
                                        }}
                                    }} catch(e) {{
                                        window.ipc.postMessage('EVAL_ERR:' + e.toString());
                                    }}
                                }})();
                            "#, script);
                            let _ = webview.evaluate_script(&wrapped_js);
                        }
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
            _ => (),
        }
    });
}
