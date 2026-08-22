//! Tool dispatch and routing layer.
//!
//! Parses the structured XML output from the LLM, resolves the tool name,
//! validates the parameter schema, and routes execution to the appropriate
//! handler (shell executor, file editor, MCP connector, etc.)

use crate::domain::error::{Result, RoninError};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;
use tracing::{debug, info, warn};

// ─────────────────────────────────────────────────────────────────────────────
// Tool Call Representation
// ─────────────────────────────────────────────────────────────────────────────

/// A parsed and validated tool call extracted from LLM output.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolCall {
    pub tool_name: String,
    pub args: HashMap<String, Value>,
    pub raw_payload: String,
}

/// The result of executing a tool call.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolResult {
    pub tool_name: String,
    pub success: bool,
    pub output: String,
    pub exit_code: Option<i32>,
}

impl ToolResult {
    pub fn success(tool_name: &str, output: String) -> Self {
        Self { tool_name: tool_name.to_string(), success: true, output, exit_code: Some(0) }
    }

    pub fn failure(tool_name: &str, reason: String) -> Self {
        Self { tool_name: tool_name.to_string(), success: false, output: reason, exit_code: Some(1) }
    }

    /// Formats this result as an [OBSERVATION] block to inject into the conversation.
    pub fn to_observation_block(&self) -> String {
        let status = if self.success { "✅ SUCCESS" } else { "❌ FAILURE" };
        format!(
            "[OBSERVATION] Tool `{}` → {}\n---\n{}",
            self.tool_name, status, self.output
        )
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Dispatcher
// ─────────────────────────────────────────────────────────────────────────────

pub type ToolHandler = Box<
    dyn Fn(HashMap<String, Value>) -> std::pin::Pin<
        Box<dyn std::future::Future<Output = Result<ToolResult>> + Send>,
    > + Send + Sync,
>;

pub struct ToolDispatcher {
    /// Registry of tool name → async handler function
    handlers: HashMap<String, ToolHandler>,
}

impl ToolDispatcher {
    pub fn new() -> Self {
        Self { handlers: HashMap::new() }
    }

    /// Registers a typed async handler for a given tool name.
    pub fn register<F, Fut>(&mut self, name: &str, handler: F)
    where
        F: Fn(HashMap<String, Value>) -> Fut + Send + Sync + 'static,
        Fut: std::future::Future<Output = Result<ToolResult>> + Send + 'static,
    {
        self.handlers.insert(
            name.to_string(),
            Box::new(move |args| Box::pin(handler(args))),
        );
    }

    /// Dispatches a parsed ToolCall to the correct handler.
    pub async fn dispatch(&self, call: ToolCall) -> ToolResult {
        debug!("[ToolDispatcher] Dispatching: {}", call.tool_name);

        match self.handlers.get(&call.tool_name) {
            Some(handler) => match handler(call.args).await {
                Ok(result) => {
                    info!("[ToolDispatcher] {} → success", call.tool_name);
                    result
                }
                Err(e) => {
                    warn!("[ToolDispatcher] {} → error: {}", call.tool_name, e);
                    ToolResult::failure(&call.tool_name, e.to_string())
                }
            },
            None => {
                warn!("[ToolDispatcher] Unknown tool: {}", call.tool_name);
                ToolResult::failure(
                    &call.tool_name,
                    format!("Tool '{}' is not registered in this agent context", call.tool_name),
                )
            }
        }
    }

    /// Returns a list of all registered tool names.
    pub fn registered_tool_names(&self) -> Vec<&str> {
        self.handlers.keys().map(|k| k.as_str()).collect()
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Payload Parser
// ─────────────────────────────────────────────────────────────────────────────

/// Parses the raw XML payload into a structured ToolCall.
pub fn parse_tool_call(action: &str, raw_payload: &str) -> Result<ToolCall> {
    let args: HashMap<String, Value> = if raw_payload.trim().is_empty() {
        HashMap::new()
    } else {
        serde_json::from_str(raw_payload).map_err(|e| {
            RoninError::XmlStreamParse(format!(
                "Failed to parse tool payload JSON for '{}': {}",
                action, e
            ))
        })?
    };

    Ok(ToolCall {
        tool_name: action.trim().to_string(),
        args,
        raw_payload: raw_payload.to_string(),
    })
}
