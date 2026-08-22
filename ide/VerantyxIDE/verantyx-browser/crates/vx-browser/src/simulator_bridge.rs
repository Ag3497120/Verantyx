use serde::{Deserialize, Serialize};
use std::io::{self, BufRead};
use tao::{
    event::{Event, WindowEvent},
    event_loop::{ControlFlow, EventLoopBuilder},
    window::WindowBuilder,
};
use wry::WebViewBuilder;
use std::thread;

/// Command from Orchestrator (TypeScript/Rust Runner) -> Rust Bridge -> JS Canvas
#[derive(Debug, Deserialize)]
pub struct SimCommand {
    pub cmd: String, // "update_graph"
    pub payload: Option<String>, // JSON string of JCross nodes/links
}

pub fn run_event_loop() -> anyhow::Result<()> {
    let event_loop = EventLoopBuilder::<SimCommand>::with_user_event().build();
    let proxy = event_loop.create_proxy();

    // Spawn STDIN listener to pipe JSON payloads into the UI
    thread::spawn(move || {
        let stdin = io::stdin();
        let reader = stdin.lock();
        
        for line_res in reader.lines() {
            if let Ok(line) = line_res {
                if line.starts_with("{") {
                    // Try parsing as raw JSON graph first (for efficiency via direct pipe)
                    let cmd = SimCommand {
                        cmd: "update_graph".to_string(),
                        payload: Some(line),
                    };
                    let _ = proxy.send_event(cmd);
                } else if let Ok(cmd) = serde_json::from_str::<SimCommand>(&line) {
                    let _ = proxy.send_event(cmd);
                }
            }
        }
    });

    let window = WindowBuilder::new()
        .with_title("Verantyx JCross Universe Simulator")
        .with_inner_size(tao::dpi::LogicalSize::new(1024.0, 768.0))
        .with_visible(true)
        .build(&event_loop)?;

    let webview = WebViewBuilder::new()
        .with_html(crate::simulator_ui::HTML_TEMPLATE)
        .with_ipc_handler(|_req: wry::http::Request<String>| {
            // Can be used to sync clicks back to memory later
        })
        .build(&window)?;

    event_loop.run(move |event, _, control_flow| {
        *control_flow = ControlFlow::Wait;

        match event {
            Event::UserEvent(cmd) => {
                if cmd.cmd == "update_graph" {
                    if let Some(payload) = cmd.payload {
                        // Escape single quotes for JS injection
                        let safe_payload = payload.replace('\'', "\\'").replace('\\', "\\\\");
                        let js_call = format!("window.loadJCrossData('{}');", safe_payload);
                        let _ = webview.evaluate_script(&js_call);
                    }
                }
            }
            Event::WindowEvent { event: WindowEvent::CloseRequested, .. } => {
                *control_flow = ControlFlow::Exit;
                std::process::exit(0);
            }
            _ => (),
        }
    });
}
