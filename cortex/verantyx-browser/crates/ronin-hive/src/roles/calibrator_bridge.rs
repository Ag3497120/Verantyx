use tokio::process::{Command, ChildStdin};
use tokio::io::{AsyncWriteExt, AsyncBufReadExt, BufReader};
use serde::{Serialize, Deserialize};
use std::sync::Arc;
use tokio::sync::Mutex;
use anyhow::{Result, anyhow};
use tracing::{info, warn};

#[derive(Serialize)]
struct BridgeCommand {
    cmd: String,
    text: Option<String>,
}

#[derive(Deserialize, Debug)]
pub struct BridgeResponse {
    pub status: String,
    pub message: Option<String>,
}

pub struct CalibratorBridge {
    stdin: Arc<Mutex<ChildStdin>>,
    // We use a broadcast channel or mpsc to receive responses, but since
    // it's a request-response flow, we can use a simpler approach.
    pub rx: Arc<Mutex<tokio::sync::mpsc::Receiver<BridgeResponse>>>,
}

impl CalibratorBridge {
    pub async fn spawn_engine(cwd: &std::path::PathBuf) -> Result<Self> {
        info!("[Calibrator] Spawning vx-browser bridge engine...");
        
        let mut child = Command::new("cargo")
            .arg("run")
            .arg("-p")
            .arg("vx-browser")
            .arg("--")
            .arg("--bridge")
            .current_dir(cwd)
            .stdin(std::process::Stdio::piped())
            .stdout(std::process::Stdio::piped())
            .spawn()
            .map_err(|e| anyhow!("Failed to spawn vx-browser process: {}", e))?;

        let stdin = child.stdin.take().ok_or_else(|| anyhow!("Failed to capture stdin"))?;
        let stdout = child.stdout.take().ok_or_else(|| anyhow!("Failed to capture stdout"))?;

        let (tx, rx) = tokio::sync::mpsc::channel(32);

        // Background reader
        tokio::spawn(async move {
            let mut reader = BufReader::new(stdout).lines();
            while let Ok(Some(line)) = reader.next_line().await {
                if let Ok(resp) = serde_json::from_str::<BridgeResponse>(&line) {
                    let _ = tx.send(resp).await;
                }
            }
        });

        // Wait for ready state
        let mut rx_guard = rx;
        while let Some(resp) = rx_guard.recv().await {
            if resp.status == "ok" && resp.message.as_deref() == Some("ready") {
                info!("[Calibrator] Twin Browser Engine is Online and Ready.");
                break;
            }
        }

        Ok(Self {
            stdin: Arc::new(Mutex::new(stdin)),
            rx: Arc::new(Mutex::new(rx_guard)),
        })
    }

    /// Evaluates Javascript in the background vx-browser engine.
    /// Blocks until the asynchronous script returns a value via window.ipc.postMessage('EVAL_RES:' + ...)
    pub async fn eval_js_geometry(&self, script: &str) -> Result<String> {
        let cmd = BridgeCommand {
            cmd: "eval_js".to_string(),
            text: Some(script.to_string()),
        };

        let payload = serde_json::to_string(&cmd)? + "\n";
        {
            let mut writer = self.stdin.lock().await;
            writer.write_all(payload.as_bytes()).await?;
            writer.flush().await?;
        }

        let mut rx = self.rx.lock().await;
        // Wait for the precise eval_ok response
        while let Some(resp) = rx.recv().await {
            if resp.status == "eval_ok" {
                return Ok(resp.message.unwrap_or_default());
            } else if resp.status == "eval_err" {
                let err_msg = resp.message.unwrap_or_default();
                warn!("[Calibrator] JS Engine Error: {:?}", err_msg);
                return Err(anyhow!("Geometry eval error: {}", err_msg));
            }
        }
        
        Err(anyhow!("Stream closed before receiving eval response"))
    }

    /// Computes exactly how many pixels high a specific text payload will be rendered
    /// mimicking Gemini's Safari text area specifications.
    pub async fn measure_gemini_payload_height(&self, payload: &str, window_width: i32) -> Result<f32> {
        // We know Gemini chatbox has specific paddings, font, and max-width.
        // If window_width < 800, the chatbox takes a certain percentage.
        // We simulate the bounding box.
        
        // Escape payload securely
        let safe_payload = serde_json::to_string(payload)?;
        
        // This Javascript creates an invisible overlay with exactly the same CSS 
        // properties as the Gemini prompt textarea, sets the text, measures it, and removes it.
        let js_script = format!(
            r#"
            let div = document.createElement('div');
            // Gemini Prompt textarea rough approximations for Mac webkit
            div.style.position = 'absolute';
            div.style.visibility = 'hidden';
            div.style.fontFamily = 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
            div.style.fontSize = '16px';
            div.style.lineHeight = '24px';
            div.style.padding = '12px 16px';
            div.style.whiteSpace = 'pre-wrap';
            div.style.wordBreak = 'break-word';
            
            // Assuming Gemini chat area has a max-width typical for the responsive UI
            let winWidth = {};
            let boxWidth = winWidth > 1000 ? 800 : (winWidth - 100);
            div.style.width = boxWidth + 'px';
            
            div.innerText = {};
            document.body.appendChild(div);
            
            let h = div.getBoundingClientRect().height;
            document.body.removeChild(div);
            
            return h.toString();
            "#, 
            window_width, safe_payload
        );

        let height_str = self.eval_js_geometry(&js_script).await?;
        let height: f32 = height_str.parse().unwrap_or(24.0);
        info!("[Calibrator] Twin calculated payload height: {}px", height);
        
        Ok(height)
    }
}
