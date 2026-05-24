use crate::domain::error::Result;
use crate::engine::tool_dispatcher::ToolResult;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;
use std::process::Stdio;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::process::{Child, Command};
use tokio::sync::{mpsc, oneshot};
use tracing::{debug, error, info};

// ─────────────────────────────────────────────────────────────────────────────
// MCP Standard Types
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Serialize)]
pub struct JsonRpcRequest {
    pub jsonrpc: String,
    pub id: u64,
    pub method: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub params: Option<Value>,
}

#[derive(Debug, Deserialize)]
pub struct JsonRpcResponse {
    pub jsonrpc: String,
    pub id: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub result: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<Value>,
}

// ─────────────────────────────────────────────────────────────────────────────
// MCP Stdio Client
// ─────────────────────────────────────────────────────────────────────────────

pub struct McpStdioClient {
    server_process: Child,
    request_tx: mpsc::Sender<(JsonRpcRequest, oneshot::Sender<JsonRpcResponse>)>,
    pub tools_cache: Vec<String>,
}

impl McpStdioClient {
    /// Spawns an MCP compliant server using standard I/O streams.
    pub async fn connect(command: &str, args: &[&str]) -> Result<Self> {
        info!("[MCP] Spawning server: {} {:?}", command, args);

        let mut child = Command::new(command)
            .args(args)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|e| crate::domain::error::RoninError::ToolExecution(format!("Failed to spawn MCP server: {}", e)))?;

        let stdin = child.stdin.take().expect("Failed to grab stdin");
        let stdout = child.stdout.take().expect("Failed to grab stdout");

        let (request_tx, mut request_rx) = mpsc::channel::<(JsonRpcRequest, oneshot::Sender<JsonRpcResponse>)>(32);

        // Background Message Loop bridging tokio channels to stdio JSON-RPC
        tokio::spawn(async move {
            let mut stdin = stdin;
            let mut stdout_reader = BufReader::new(stdout).lines();
            let mut pending_requests: HashMap<u64, oneshot::Sender<JsonRpcResponse>> = HashMap::new();

            loop {
                tokio::select! {
                    // Outgoing API Request
                    req_opt = request_rx.recv() => {
                        if let Some((req, resolve_tx)) = req_opt {
                            let id = req.id;
                            pending_requests.insert(id, resolve_tx);
                            if let Ok(mut serialized) = serde_json::to_string(&req) {
                                serialized.push('\n');
                                if stdin.write_all(serialized.as_bytes()).await.is_err() {
                                    error!("[MCP] Failed to write to server stdin");
                                    break;
                                }
                            }
                        } else {
                            break;
                        }
                    }
                    // Incoming API Response
                    line_res = stdout_reader.next_line() => {
                        if let Ok(Some(line)) = line_res {
                            if let Ok(resp) = serde_json::from_str::<JsonRpcResponse>(&line) {
                                if let Some(resolve_tx) = pending_requests.remove(&resp.id) {
                                    let _ = resolve_tx.send(resp);
                                }
                            }
                        } else {
                            break; // EOF or err
                        }
                    }
                }
            }
        });

        // Initialize MCP connection protocol (Simulated implementation here)
        let mut client = Self {
            server_process: child,
            request_tx,
            tools_cache: Vec::new(),
        };

        client.initialize().await?;
        Ok(client)
    }

    async fn invoke(&self, method: &str, params: Option<Value>) -> Result<JsonRpcResponse> {
        let (tx, rx) = oneshot::channel();
        let req_id = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_micros() as u64;
        let req = JsonRpcRequest {
            jsonrpc: "2.0".to_string(),
            id: req_id,
            method: method.to_string(),
            params,
        };

        self.request_tx.send((req, tx)).await.map_err(|_| crate::domain::error::RoninError::ToolExecution("MCP channel closed".to_string()))?;
        rx.await.map_err(|_| crate::domain::error::RoninError::ToolExecution("MCP dropped response".to_string()))
    }

    pub async fn initialize(&mut self) -> Result<()> {
        let res = self.invoke("initialize", Some(serde_json::json!({
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "ronin-cli",
                "version": "1.0.0"
            }
        }))).await?;

        debug!("[MCP] Initialized: {:?}", res);

        let res = self.invoke("tools/list", None).await?;
        if let Some(result) = res.result {
            if let Some(tools) = result.get("tools").and_then(|t| t.as_array()) {
                for tool in tools {
                    if let Some(name) = tool.get("name").and_then(|n| n.as_str()) {
                        self.tools_cache.push(name.to_string());
                    }
                }
            }
        }
        Ok(())
    }

    pub async fn call_tool(&self, name: &str, args: HashMap<String, Value>) -> ToolResult {
        match self.invoke("tools/call", Some(serde_json::json!({
            "name": name,
            "arguments": args
        }))).await {
            Ok(res) => {
                if let Some(err) = res.error {
                    ToolResult::failure(name, err.to_string())
                } else if let Some(result) = res.result {
                    let content = result.get("content")
                        .and_then(|c| c.as_array())
                        .and_then(|a| a.first())
                        .and_then(|f| f.get("text"))
                        .and_then(|t| t.as_str())
                        .unwrap_or("Executed successfully.");
                    ToolResult::success(name, content.to_string())
                } else {
                    ToolResult::success(name, "No content returned.".to_string())
                }
            }
            Err(e) => ToolResult::failure(name, e.to_string()),
        }
    }
}

