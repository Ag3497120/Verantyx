//! Anthropic Claude API provider (cloud fallback path).
//! Auto-activates when local capacity is determined to be insufficient.

use crate::domain::error::{Result, RoninError};
use crate::models::sampling_params::InferenceRequest;
use async_trait::async_trait;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::time::Duration;
use tokio::sync::mpsc;
use tracing::{info, warn};

use super::{LlmProvider, LlmMessage};

pub struct AnthropicProvider {
    http: Client,
    api_key: String,
    base_url: String,
}

impl AnthropicProvider {
    pub fn new(api_key: &str) -> Self {
        Self {
            http: Client::builder()
                .timeout(Duration::from_secs(120))
                .build()
                .expect("Failed to build Anthropic HTTP client"),
            api_key: api_key.to_string(),
            base_url: "https://api.anthropic.com/v1".to_string(),
        }
    }
}

#[derive(Debug, Serialize)]
struct AnthropicRequest {
    model: String,
    max_tokens: usize,
    messages: Vec<AnthropicMessage>,
    system: Option<String>,
}

#[derive(Debug, Serialize, Deserialize)]
struct AnthropicMessage {
    role: String,
    content: String,
}

#[derive(Debug, Deserialize)]
struct AnthropicResponse {
    content: Vec<AnthropicContentBlock>,
}

#[derive(Debug, Deserialize)]
struct AnthropicContentBlock {
    #[serde(rename = "type")]
    block_type: String,
    text: Option<String>,
}

#[async_trait]
impl LlmProvider for AnthropicProvider {
    async fn invoke(
        &self,
        request: &InferenceRequest,
        history: &[LlmMessage],
    ) -> Result<String> {
        let (system_prompt, messages): (Option<String>, Vec<AnthropicMessage>) = {
            let mut sys = None;
            let msgs: Vec<AnthropicMessage> = history
                .iter()
                .filter_map(|m| {
                    if m.role == "system" {
                        sys = Some(m.content.clone());
                        None
                    } else {
                        Some(AnthropicMessage {
                            role: m.role.clone(),
                            content: m.content.clone(),
                        })
                    }
                })
                .collect();
            (sys, msgs)
        };

        let body = AnthropicRequest {
            model: request.model.clone(),
            max_tokens: request.sampling.max_tokens,
            messages,
            system: system_prompt,
        };

        let resp = self
            .http
            .post(format!("{}/messages", self.base_url))
            .header("x-api-key", &self.api_key)
            .header("anthropic-version", "2023-06-01")
            .json(&body)
            .send()
            .await
            .map_err(RoninError::Network)?;

        if !resp.status().is_success() {
            let status = resp.status();
            warn!("[Anthropic] HTTP {}", status);
            return Err(RoninError::ModelUnsupported(format!(
                "Anthropic API returned HTTP {}",
                status
            )));
        }

        let parsed: AnthropicResponse = resp.json().await.map_err(RoninError::Network)?;

        let text = parsed
            .content
            .into_iter()
            .filter_map(|b| if b.block_type == "text" { b.text } else { None })
            .collect::<Vec<_>>()
            .join("\n");

        info!("[Anthropic] Generated {} chars", text.len());
        Ok(text)
    }

    async fn invoke_stream(
        &self,
        _request: &InferenceRequest,
        _history: &[LlmMessage],
    ) -> Result<mpsc::Receiver<String>> {
        let (tx, rx) = mpsc::channel(256);
        let _ = tx.send("[Anthropic streaming not yet implemented]".to_string()).await;
        Ok(rx)
    }

    fn provider_name(&self) -> &'static str {
        "Anthropic Claude (Cloud Fallback)"
    }
}
