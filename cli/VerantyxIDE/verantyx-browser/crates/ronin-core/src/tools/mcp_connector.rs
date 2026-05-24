//! MCP (Model Context Protocol) connector.
//!
//! Provides dynamic tool discovery and invocation for external MCP servers.
//! Compatible with any server implementing the MCP specification (GitHub, SQLite,
//! Figma, Vercel, etc.). Tools discovered via MCP are automatically registered
//! in the ToolDispatcher and embedded in the system prompt schema.

use crate::domain::error::{Result, RoninError};
use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::time::Duration;
use tracing::{debug, info, warn};

// ─────────────────────────────────────────────────────────────────────────────
// MCP Server Registration
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct McpServerConfig {
    pub name: String,
    pub url: String,
    pub auth_token: Option<String>,
    pub enabled: bool,
}

// ─────────────────────────────────────────────────────────────────────────────
// MCP Tool Schema (from server capabilities response)
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct McpTool {
    pub name: String,
    pub description: String,
    pub input_schema: serde_json::Value,
}

#[derive(Debug, Deserialize)]
struct McpCapabilitiesResponse {
    tools: Vec<McpTool>,
}

// ─────────────────────────────────────────────────────────────────────────────
// MCP Tool Call / Result
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Serialize)]
struct McpInvokeRequest {
    tool: String,
    arguments: serde_json::Value,
}

#[derive(Debug, Deserialize)]
struct McpInvokeResponse {
    content: Vec<McpContent>,
    is_error: Option<bool>,
}

#[derive(Debug, Deserialize)]
struct McpContent {
    #[serde(rename = "type")]
    content_type: String,
    text: Option<String>,
}

// ─────────────────────────────────────────────────────────────────────────────
// MCP Connector
// ─────────────────────────────────────────────────────────────────────────────

pub struct McpConnector {
    http: Client,
    servers: Vec<McpServerConfig>,
    discovered_tools: HashMap<String, (McpTool, String)>, // tool_name → (tool, server_url)
}

impl McpConnector {
    pub fn new(servers: Vec<McpServerConfig>) -> Self {
        Self {
            http: Client::builder()
                .timeout(Duration::from_secs(30))
                .build()
                .expect("Failed to build MCP HTTP client"),
            servers,
            discovered_tools: HashMap::new(),
        }
    }

    /// Polls all registered MCP servers and discovers their available tools.
    pub async fn discover_all(&mut self) -> Result<usize> {
        let mut total_discovered = 0;

        for server in &self.servers {
            if !server.enabled {
                continue;
            }

            debug!("[MCP] Probing server: {}", server.name);

            match self.fetch_capabilities(server).await {
                Ok(tools) => {
                    let count = tools.len();
                    for tool in tools {
                        let key = format!("{}::{}", server.name, tool.name);
                        self.discovered_tools.insert(key, (tool, server.url.clone()));
                    }
                    info!("[MCP] Server '{}' registered {} tools", server.name, count);
                    total_discovered += count;
                }
                Err(e) => {
                    warn!("[MCP] Failed to probe '{}': {}", server.name, e);
                }
            }
        }

        Ok(total_discovered)
    }

    async fn fetch_capabilities(&self, server: &McpServerConfig) -> Result<Vec<McpTool>> {
        let url = format!("{}/capabilities", server.url);
        let mut req = self.http.get(&url);

        if let Some(token) = &server.auth_token {
            req = req.bearer_auth(token);
        }

        let response: McpCapabilitiesResponse = req
            .send()
            .await
            .map_err(RoninError::Network)?
            .json()
            .await
            .map_err(RoninError::Network)?;

        Ok(response.tools)
    }

    /// Invokes a specific MCP tool on its registered server.
    pub async fn invoke(&self, qualified_tool_name: &str, args: serde_json::Value) -> Result<String> {
        let (tool, server_url) = self
            .discovered_tools
            .get(qualified_tool_name)
            .ok_or_else(|| {
                RoninError::ToolExecution(format!(
                    "MCP tool '{}' not found in discovered registry",
                    qualified_tool_name
                ))
            })?;

        let body = McpInvokeRequest {
            tool: tool.name.clone(),
            arguments: args,
        };

        let response: McpInvokeResponse = self
            .http
            .post(format!("{}/invoke", server_url))
            .json(&body)
            .send()
            .await
            .map_err(RoninError::Network)?
            .json()
            .await
            .map_err(RoninError::Network)?;

        if response.is_error.unwrap_or(false) {
            return Err(RoninError::ToolExecution(format!(
                "MCP tool '{}' returned an error response",
                qualified_tool_name
            )));
        }

        let text = response
            .content
            .into_iter()
            .filter_map(|c| if c.content_type == "text" { c.text } else { None })
            .collect::<Vec<_>>()
            .join("\n");

        Ok(text)
    }

    /// Returns the list of all discovered tool names (for ToolDispatcher registration).
    pub fn discovered_tool_names(&self) -> Vec<&str> {
        self.discovered_tools.keys().map(|k| k.as_str()).collect()
    }

    /// Returns tool metadata for prompt schema embedding.
    pub fn all_tools(&self) -> Vec<&McpTool> {
        self.discovered_tools.values().map(|(t, _)| t).collect()
    }
}
