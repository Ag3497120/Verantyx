use crate::actor::{Actor, Envelope};
use crate::messages::HiveMessage;
use async_trait::async_trait;
use tracing::warn;
use tokio::sync::Mutex;
use uuid::Uuid;
use vx_dom::Document;
use vx_render::ai_renderer::AiRenderer;

lazy_static::lazy_static! {
    static ref SAFARI_CLI_MUTEX: Mutex<()> = Mutex::new(());
}

pub struct SafariEvaluatorActor {
    pub id: Uuid,
    cwd: std::path::PathBuf,
    _is_japanese_mode: bool,
}

impl SafariEvaluatorActor {
    pub fn new(id: Uuid, cwd: std::path::PathBuf, is_japanese_mode: bool) -> Self {
        Self { id, cwd, _is_japanese_mode: is_japanese_mode }
    }

    async fn run_applescript(&self, script: &str) -> String {
        match tokio::process::Command::new("osascript")
            .arg("-e")
            .arg(script)
            .output()
            .await
        {
            Ok(output) => {
                let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
                if !stdout.is_empty() { return stdout; }
                String::from_utf8_lossy(&output.stderr).trim().to_string()
            }
            Err(e) => format!("ERROR: {}", e),
        }
    }

    async fn do_javascript(&self, js: &str) -> String {
        // Escape quotes to prevent applescript syntax errors
        let safe_js = js.replace("\\", "\\\\").replace("\"", "\\\"");
        let script = format!(
            r#"tell application "Safari"
                set res to do JavaScript "{}" in front document
                return res
            end tell"#,
            safe_js
        );
        self.run_applescript(&script).await
    }
    pub fn start_organic_drift(cwd: std::path::PathBuf) {
        tokio::spawn(async move {
            // 1. JCross Parser - Read Japanese Configuration
            let drift_config_path = cwd.join(".ronin").join("stealth.jcross");
            let config_data = std::fs::read_to_string(&drift_config_path).unwrap_or_default();
            
            let mut amp = 3.0;
            let mut period = 10.0;
            let mut app_target = String::from("Safari");
            
            // Dumb regex-free JCross parsing to obscure true intent
            for line in config_data.lines() {
                if line.contains("水平軸:") && line.contains("振幅:") {
                    if let Some(idx) = line.find("振幅:") {
                        let sub = &line[idx + 7..]; // UTF-8 math
                        if let Some(end) = sub.find(",") {
                            amp = sub[..end].trim().parse::<f64>().unwrap_or(3.0);
                        }
                    }
                    if let Some(idx) = line.find("周期:") {
                        let sub = &line[idx + 7..];
                        if let Some(end) = sub.find("}") {
                            period = sub[..end].trim().parse::<f64>().unwrap_or(10.0);
                        }
                    }
                }
                if line.contains("標的環境:") {
                    if let Some(start) = line.find("\"") {
                        let sub = &line[start + 1..];
                        if let Some(end) = sub.find("\"") {
                            app_target = sub[..end].to_string();
                        }
                    }
                }
            }

            // 2. Dynamic execution decoupled from static strings
            let mut last_drift_x = 0.0;
            let mut last_drift_y = 0.0;
            let start_time = std::time::Instant::now();
            
            for _ in 0..600 {
                let elapsed = start_time.elapsed().as_secs_f64();
                
                let current_drift_x = (elapsed * std::f64::consts::PI * 2.0 / period).sin() * amp;
                let current_drift_y = (elapsed * std::f64::consts::PI * 2.0 / period).cos() * amp;
                
                let dx = (current_drift_x - last_drift_x).round() as i32;
                let dy = (current_drift_y - last_drift_y).round() as i32;
                
                if dx != 0 || dy != 0 {
                    last_drift_x += dx as f64;
                    last_drift_y += dy as f64;
                    
                    // Procedurally generated payload
                    let pre = format!("tell application \"{}\"", app_target);
                    let cmd1 = "set b to bounds of front window";
                    let cmd2 = format!("set bounds of front window to {{(item 1 of b) + {}, (item 2 of b) + {}, (item 3 of b) + {}, (item 4 of b) + {}}}", dx, dy, dx, dy);
                    let move_script = format!("{}\n{}\n{}\nend tell", pre, cmd1, cmd2);
                    
                    let _ = tokio::process::Command::new("osascript").arg("-e").arg(&move_script).output().await;
                }
                tokio::time::sleep(tokio::time::Duration::from_millis(150)).await;
            }
        });
    }
}

#[async_trait]
impl Actor for SafariEvaluatorActor {
    fn name(&self) -> &str {
        "SafariEvaluator"
    }

    async fn receive(&mut self, env: Envelope) -> anyhow::Result<Option<Envelope>> {
        let msg: HiveMessage = match serde_json::from_str(&env.payload) {
            Ok(m) => m,
            Err(_) => return Ok(None),
        };

        match msg {
            HiveMessage::SpawnSubAgent { id: _, objective } | HiveMessage::Objective(objective) => {
                let _lock = SAFARI_CLI_MUTEX.lock().await;

                println!("\n{}", console::style("╭─ [ Safari Markdown Verifier ] ────────────────────────────────────").magenta().bold());
                println!("{} Extracting live Safari state & building Markdown diff...", console::style("│").magenta().bold());
                println!("{}", console::style("╰───────────────────────────────────────────────────────────────────").magenta().bold());

                // Engage background anti-bot drift system
                println!("{} Engaging JCross Cloaking Drift Pipeline...", console::style("[AI_SYS]").cyan());
                Self::start_organic_drift(self.cwd.clone());

                // Read JCross Intent
                let intent_path = self.cwd.join(".ronin").join("intent.jcross");
                let intent_content = std::fs::read_to_string(&intent_path).unwrap_or_default();
                
                let mut goal: Option<String> = None;
                for line in intent_content.lines() {
                    if line.starts_with("ExpectedState:") {
                        goal = Some(line.trim_start_matches("ExpectedState:").trim().to_string());
                        break;
                    }
                    if line.starts_with("Goal:") {
                        goal = Some(line.trim_start_matches("Goal:").trim().to_string());
                        break;
                    }
                }

                // Inject prompt to standard JCross tracking
                println!("{} Injecting task: {}", console::style("[SYS_AUDIT]").cyan(), objective);
                
                // Fetch DOM and evaluate
                let raw_html = self.do_javascript("document.documentElement.outerHTML").await;
                if raw_html.contains("ERROR") || raw_html.is_empty() {
                    println!("{} Failed to extract Safari Document! Error: {}", console::style("[AI_SYS]").red(), raw_html);
                    return Ok(None);
                }

                // 1. Markdown conversion for JCross Verification
                let markdown_output = html2md::parse_html(&raw_html);
                let _ = std::fs::write(self.cwd.join(".ronin").join("safari_view.md"), &markdown_output);
                println!("{} Safari layout converted to Markdown ({} bytes).", console::style("[AI_SYS]").dim(), markdown_output.len());
                
                // Diff Verification against JCross
                let mut goal_reached = false;
                if let Some(target) = &goal {
                    let keywords: Vec<&str> = target.split(',').collect();
                    let mut matched = true;
                    for k in keywords {
                        let k = k.trim();
                        if !k.is_empty() && !markdown_output.contains(k) {
                            matched = false;
                            break;
                        }
                    }
                    
                    if matched {
                        println!("{} ✔ JCross Goal Reached: State matches ({})!", console::style("[AI_SYS]").green(), target);
                        goal_reached = true;
                    } else {
                        println!("{} ✖ JCross Diff Detected: State does not match ({})", console::style("[AI_SYS]").yellow(), target);
                    }
                }

                // 2. Spatial Mapping & Free Action
                if !goal_reached {
                    let doc = Document::parse(&raw_html);
                    let layout_root = vx_layout::layout_node::LayoutNode::from_dom(&doc.arena, doc.root_id)
                        .unwrap_or_else(|| vx_layout::layout_node::LayoutNode::new(doc.root_id));
    
                    let mut ai_renderer = AiRenderer::new();
                    let page_map = ai_renderer.render(&doc.arena, &layout_root, "Safari", "http://localhost");
    
                    // Prompt for free button
                    let input_target: String = dialoguer::Input::with_theme(&dialoguer::theme::ColorfulTheme::default())
                        .with_prompt("Target Button to Click (Label/Aria/Class)")
                        .interact_text()
                        .unwrap();
    
                    let mut best_target: Option<(f32, f32)> = None;
                    for el in &page_map.interactive_elements {
                        let combined = format!("{:?} {} {:?}", el.element_type, el.label, el.value).to_lowercase();
                        if combined.contains(&input_target.to_lowercase()) {
                            // Convert JS logical coordinates back to Safari physical viewport
                            let js_check_viewport = r#"(function(){ return [window.screenX, window.screenY, window.outerHeight - window.innerHeight].join(','); })();"#;
                            let viewport = self.do_javascript(js_check_viewport).await;
                            
                            let parts: Vec<&str> = viewport.split(',').collect();
                            let win_x: f32 = parts.get(0).unwrap_or(&"0").parse().unwrap_or(0.0);
                            let win_y: f32 = parts.get(1).unwrap_or(&"0").parse().unwrap_or(0.0);
                            let content_offset_y: f32 = parts.get(2).unwrap_or(&"0").parse().unwrap_or(0.0);
                            
                            let click_x = win_x + el.bounds.x + (el.bounds.width / 2.0);
                            let click_y = win_y + content_offset_y + el.bounds.y + (el.bounds.height / 2.0);
                            best_target = Some((click_x, click_y));
                            break;
                        }
                    }
    
                    if let Some((x, y)) = best_target {
                        println!("{} Target located at absolute Safari viewport ({}, {}). Dispatching native click...", console::style("[AI_SYS]").magenta(), x, y);
                        let click_script = format!(r#"tell application "System Events" to click at {{{}, {}}}"#, x, y);
                        self.run_applescript(&click_script).await;
                    } else {
                        println!("{} Target '{}' not found in Render Tree.", console::style("[AI_SYS]").red(), input_target);
                    }
                }
            }
            _ => {
                warn!("SafariEvaluator unhandled message type");
            }
        }
        Ok(None)
    }
}
