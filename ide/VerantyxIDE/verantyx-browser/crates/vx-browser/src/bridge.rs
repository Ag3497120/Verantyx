//! Verantyx CLI Bridge — JSON IPC for programmatic browser control
//!
//! Allows verantyx-cli (TypeScript) to control vx-browser via JSON commands.
//! Communication happens over stdin/stdout.

use anyhow::{Result, anyhow};
use serde::{Deserialize, Serialize};
use std::io::{self, BufRead};
use vx_render::ai_renderer::{AiRenderer, AiRenderedPage};
use vx_input::{action, FormState};
use vx_net::HttpClient;
use vx_js::VxRuntime;

/// Incoming command from verantyx-cli
#[derive(Debug, Deserialize)]
pub struct BridgeCommand {
    pub cmd: String,
    pub id: Option<u32>,
    pub url: Option<String>,
    pub text: Option<String>,
    pub selector: Option<String>,
    pub timeout: Option<u64>,
}

/// Outgoing response to verantyx-cli
#[derive(Debug, Serialize)]
pub struct BridgeResponse {
    pub status: String,
    pub message: Option<String>,
    pub url: Option<String>,
    pub page: Option<AiPageResponse>,
    pub elements: Option<Vec<ElementInfo>>,
    pub text: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct AiPageResponse {
    pub url: String,
    pub title: String,
    pub content: String,
    pub text: Option<String>,
    pub token_estimate: Option<usize>,
}

#[derive(Debug, Serialize)]
pub struct ElementInfo {
    pub id: u32,
    pub element_type: String,
    pub label: String,
    pub href: Option<String>,
    pub intent: String,
    pub x: f32,
    pub y: f32,
    pub width: f32,
    pub height: f32,
}

impl BridgeResponse {
    pub fn ok(msg: &str) -> Self {
        Self {
            status: "ok".into(),
            message: Some(msg.into()),
            url: None, page: None, elements: None, text: None,
        }
    }
    pub fn error(msg: &str) -> Self {
        Self {
            status: "error".into(),
            message: Some(msg.into()),
            url: None, page: None, elements: None, text: None,
        }
    }
    pub fn page(page: &AiRenderedPage) -> Self {
        Self {
            status: "ok".into(),
            message: None,
            url: Some(page.url.clone()),
            page: Some(AiPageResponse {
                url: page.url.clone(),
                title: page.title.clone(),
                content: page.render_markdown(),
                text: None,
                token_estimate: Some(page.token_estimate),
            }),
            elements: None,
            text: None,
        }
    }
}

/// Bridge session state
pub struct BridgeSession {
    pub client: HttpClient,
    pub js_runtime: VxRuntime,
    pub current_url: String,
    pub current_page: Option<AiRenderedPage>,
    pub form_state: FormState,
    pub history: Vec<String>,
}

impl BridgeSession {
    pub fn new() -> Result<Self> {
        Ok(Self {
            client: HttpClient::new(),
            js_runtime: VxRuntime::new()?,
            current_url: String::new(),
            current_page: None,
            form_state: FormState::new(),
            history: Vec::new(),
        })
    }

    /// Navigate to URL and render
    pub async fn navigate(&mut self, url: &str) -> Result<BridgeResponse> {
        let html_str = if url.starts_with("file://") {
            let path = url.trim_start_matches("file://");
            std::fs::read_to_string(path).map_err(|e| anyhow!("Failed to read local file: {}", e))?
        } else {
            let mut resp = self.client.get(url).await?;
            resp.text().unwrap_or_default()
        };

        self.current_url = url.to_string();
        self.history.push(self.current_url.clone());
        self.form_state.clear();

        // Phase 8: Load and execute scripts
        let _ = self.js_runtime.load_scripts_from_html(&html_str, &self.current_url).await;

        // --- Real 500k-Line Engine Pipeline ---
        // 1. DOM Parsing
        let doc = vx_dom::Document::parse(&html_str);
        
        // 2. Layout Generation
        let layout_root = vx_layout::layout_node::LayoutNode::from_dom(&doc.arena, doc.root_id)
            .unwrap_or_else(|| vx_layout::layout_node::LayoutNode::new(doc.root_id));
        
        // 3. AI Rendering with Spatial data
        let mut ai = AiRenderer::new();
        let page = ai.render(&doc.arena, &layout_root, "Verantyx Page", &self.current_url);
        
        let response = BridgeResponse::page(&page);
        self.current_page = Some(page);

        Ok(response)
    }

    /// Main command loop for programmatic control (Phase 7)
    pub async fn run_loop(&mut self) -> Result<()> {
        let stdin = io::stdin();
        for line in stdin.lock().lines() {
            let line = line?;
            if line.trim().is_empty() { continue; }
            
            let cmd: BridgeCommand = match serde_json::from_str(&line) {
                Ok(c) => c,
                Err(e) => {
                    let err = BridgeResponse::error(&format!("JSON Parse Error: {}", e));
                    println!("{}", serde_json::to_string(&err)?);
                    continue;
                }
            };

            let response = self.execute(cmd).await;
            println!("{}", serde_json::to_string(&response)?);
        }
        Ok(())
    }

    /// Execute a bridge command
    pub async fn execute(&mut self, cmd: BridgeCommand) -> BridgeResponse {
        match cmd.cmd.as_str() {
            "navigate" | "goto" => {
                if let Some(url) = cmd.url {
                    match self.navigate(&url).await {
                        Ok(resp) => resp,
                        Err(e) => BridgeResponse::error(&format!("Navigate failed: {}", e)),
                    }
                } else {
                    BridgeResponse::error("Missing url")
                }
            }

            "click" => {
                if let (Some(id), Some(page)) = (cmd.id, &self.current_page) {
                    // ID conversion for input crate (usize)
                    let result = action::execute_action(
                        &action::BrowserAction::Click(id as usize),
                        &page.interactive_elements,
                        &mut self.form_state,
                        &self.current_url,
                    );
                    if let Some(nav_url) = result.navigate_to {
                        match self.navigate(&nav_url).await {
                            Ok(resp) => resp,
                            Err(e) => BridgeResponse::error(&format!("Navigate failed: {}", e)),
                        }
                    } else {
                        if result.success {
                            BridgeResponse::ok(&result.message)
                        } else {
                            BridgeResponse::error(&result.message)
                        }
                    }
                } else {
                    BridgeResponse::error("Missing id or no page loaded")
                }
            }

            "type" => {
                if let (Some(id), Some(text)) = (cmd.id, cmd.text) {
                    self.form_state.set_value(id as usize, &text);
                    BridgeResponse::ok(&format!("Typed '{}' into [ID:{}]", text, id))
                } else {
                    BridgeResponse::error("Missing id or text")
                }
            }

            "submit" => {
                let data = self.form_state.get_all();
                let mut resp = BridgeResponse::ok(&format!("Submitted form with {} fields", data.len()));
                resp.text = Some(serde_json::to_string(&data).unwrap_or_default());
                resp
            }

            "get_text" => {
                if let (Some(id), Some(page)) = (cmd.id, &self.current_page) {
                    let id_usize = id as usize;
                    if let Some(el) = page.interactive_elements.iter().find(|e| e.id == id_usize) {
                        let mut resp = BridgeResponse::ok("ok");
                        resp.text = Some(el.label.clone());
                        resp
                    } else {
                        BridgeResponse::error(&format!("Element [ID:{}] not found", id))
                    }
                } else {
                    BridgeResponse::error("Missing id or no page loaded")
                }
            }

            "get_elements" => {
                if let Some(page) = &self.current_page {
                    let elements: Vec<ElementInfo> = page.interactive_elements.iter().map(|e| {
                        ElementInfo {
                            id: e.id as u32,
                            element_type: format!("{:?}", e.element_type),
                            label: e.label.clone(),
                            href: e.href.clone(),
                            intent: format!("{:?}", e.css_intent),
                            x: e.bounds.x,
                            y: e.bounds.y,
                            width: e.bounds.width,
                            height: e.bounds.height,
                        }
                    }).collect();
                    BridgeResponse {
                        status: "ok".into(),
                        message: Some(format!("{} elements", elements.len())),
                        url: None, page: None,
                        elements: Some(elements),
                        text: None,
                    }
                } else {
                    BridgeResponse::error("No page loaded")
                }
            }

            "get_spatial_map" => {
                if let Some(page) = &self.current_page {
                    let mut resp = BridgeResponse::ok("Spatial map generated");
                    // Return raw JSON of interactive elements with bounds
                    resp.text = Some(serde_json::to_string(&page.interactive_elements).unwrap_or_default());
                    resp
                } else {
                    BridgeResponse::error("No page loaded")
                }
            }

            "get_page" => {
                if let Some(page) = &self.current_page {
                    BridgeResponse::page(page)
                } else {
                    BridgeResponse::error("No page loaded")
                }
            }

            "quit" => {
                std::process::exit(0);
            }

            _ => BridgeResponse::error(&format!("Unknown command: {}", cmd.cmd)),
        }
    }
}
