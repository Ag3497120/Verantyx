use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;
use std::sync::Arc;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::process::{Child, Command};
use tokio::sync::Mutex;
use std::process::Stdio;

// JSON-RPC 2.0 Message Structures
#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct RpcRequest {
    pub jsonrpc: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub id: Option<i64>,
    pub method: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub params: Option<Value>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct RpcResponse {
    pub jsonrpc: String,
    pub id: i64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub result: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<RpcError>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct RpcError {
    pub code: i64,
    pub message: String,
}

pub struct ExtensionHostManager {
    process: Mutex<Option<Child>>,
    is_running: Mutex<bool>,
    request_id_counter: Mutex<i64>,
    pending_requests: Mutex<HashMap<i64, tokio::sync::oneshot::Sender<Option<Value>>>>,
}

impl ExtensionHostManager {
    pub fn new() -> Self {
        Self {
            process: Mutex::new(None),
            is_running: Mutex::new(false),
            request_id_counter: Mutex::new(0),
            pending_requests: Mutex::new(HashMap::new()),
        }
    }

    pub async fn start(&self, host_path: &str) -> Result<(), Box<dyn std::error::Error>> {
        let mut is_running = self.is_running.lock().await;
        if *is_running {
            return Ok(());
        }

        // On Windows, node.exe is usually in PATH
        let mut child = Command::new("node")
            .arg(host_path)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()?;

        let stdout = child.stdout.take().expect("Failed to open stdout");
        let stderr = child.stderr.take().expect("Failed to open stderr");

        *self.process.lock().await = Some(child);
        *is_running = true;

        // Clone Arc-like references if this struct were Arc'd, but since we are taking &self,
        // we'd typically run the readers in tasks that own an Arc<Self>.
        // For simplicity in this standalone implementation, we'll assume the caller wraps it in Arc.
        
        Ok(())
    }

    pub async fn stop(&self) {
        let mut process_guard = self.process.lock().await;
        if let Some(mut child) = process_guard.take() {
            let _ = child.kill().await;
        }
        *self.is_running.lock().await = false;
    }

    pub async fn handle_incoming_request(&self, request: RpcRequest) -> Option<RpcResponse> {
        let method = request.method.as_str();
        let params = request.params.unwrap_or_default();
        let id = request.id;

        match method {
            "window.showInformationMessage" => {
                if let Some(msg) = params.get("message").and_then(|m| m.as_str()) {
                    println!("ℹ️ [Extension] {}", msg);
                }
                id.map(|i| RpcResponse {
                    jsonrpc: "2.0".to_string(),
                    id: i,
                    result: Some(Value::String("OK".to_string())),
                    error: None,
                })
            }
            "window.showErrorMessage" => {
                if let Some(msg) = params.get("message").and_then(|m| m.as_str()) {
                    eprintln!("❌ [Extension Error] {}", msg);
                }
                id.map(|i| RpcResponse {
                    jsonrpc: "2.0".to_string(),
                    id: i,
                    result: Some(Value::String("OK".to_string())),
                    error: None,
                })
            }
            "window.showQuickPick" => {
                // Windows specific quick pick implementation
                println!("Displaying QuickPick for Windows: {:?}", params.get("items"));
                id.map(|i| RpcResponse {
                    jsonrpc: "2.0".to_string(),
                    id: i,
                    result: Some(Value::Null), // Return actual selection here
                    error: None,
                })
            }
            "window.showInputBox" => {
                // Windows specific input box implementation
                println!("Displaying InputBox for Windows: {:?}", params.get("options"));
                id.map(|i| RpcResponse {
                    jsonrpc: "2.0".to_string(),
                    id: i,
                    result: Some(Value::Null), // Return actual input here
                    error: None,
                })
            }
            "window.createWebviewPanel" => {
                println!("Creating Webview Panel for Windows");
                id.map(|i| RpcResponse {
                    jsonrpc: "2.0".to_string(),
                    id: i,
                    result: Some(Value::String("OK".to_string())),
                    error: None,
                })
            }
            _ => {
                eprintln!("⚠️ Unknown RPC method from host: {}", method);
                id.map(|i| RpcResponse {
                    jsonrpc: "2.0".to_string(),
                    id: i,
                    result: None,
                    error: None,
                })
            }
        }
    }
}
