//! Google Gemini API provider (stealth cloud fallback path).
//! Used when local capacity is insufficient and Anthropic is unavailable.
//! Supports the Gemini 2.5 Pro model via REST.

use crate::domain::error::{Result, RoninError};
use crate::models::sampling_params::InferenceRequest;
use async_trait::async_trait;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::time::Duration;
use tokio::sync::mpsc;
use tracing::info;

use super::{LlmProvider, LlmMessage};

pub struct GeminiProvider {
    http: Client,
    api_key: String,
}

impl GeminiProvider {
    pub fn new(api_key: &str) -> Self {
        Self {
            http: Client::builder()
                .timeout(Duration::from_secs(120))
                .build()
                .expect("Failed to build Gemini HTTP client"),
            api_key: api_key.to_string(),
        }
    }

    fn endpoint(&self, model: &str) -> String {
        format!(
            "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent?key={}",
            model, self.api_key
        )
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Gemini Request / Response Types
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Serialize)]
struct GeminiRequest {
    contents: Vec<GeminiContent>,
    #[serde(rename = "generationConfig")]
    generation_config: GeminiGenConfig,
}

#[derive(Debug, Serialize, Deserialize)]
struct GeminiContent {
    role: String,
    parts: Vec<GeminiPart>,
}

#[derive(Debug, Serialize, Deserialize)]
struct GeminiPart {
    text: String,
}

#[derive(Debug, Serialize)]
struct GeminiGenConfig {
    temperature: f32,
    #[serde(rename = "maxOutputTokens")]
    max_output_tokens: u32,
    #[serde(rename = "topP")]
    top_p: f32,
    #[serde(rename = "topK")]
    top_k: u32,
}

#[derive(Debug, Deserialize)]
struct GeminiResponse {
    candidates: Vec<GeminiCandidate>,
}

#[derive(Debug, Deserialize)]
struct GeminiCandidate {
    content: GeminiContent,
}

// ─────────────────────────────────────────────────────────────────────────────
// Provider Implementation
// ─────────────────────────────────────────────────────────────────────────────

#[async_trait]
impl LlmProvider for GeminiProvider {
    async fn invoke(
        &self,
        request: &InferenceRequest,
        history: &[LlmMessage],
    ) -> Result<String> {
        let contents: Vec<GeminiContent> = history
            .iter()
            .filter(|m| m.role != "system") // Gemini doesn't use system role in contents
            .map(|m| GeminiContent {
                role: if m.role == "assistant" { "model".to_string() } else { "user".to_string() },
                parts: vec![GeminiPart { text: m.content.clone() }],
            })
            .collect();

        let body = GeminiRequest {
            contents,
            generation_config: GeminiGenConfig {
                temperature: request.sampling.temperature,
                max_output_tokens: request.sampling.max_tokens as u32,
                top_p: request.sampling.top_p,
                top_k: request.sampling.top_k,
            },
        };

        let resp = self
            .http
            .post(self.endpoint(&request.model))
            .json(&body)
            .send()
            .await
            .map_err(RoninError::Network)?;

        let parsed: GeminiResponse = resp.json().await.map_err(RoninError::Network)?;

        let text = parsed
            .candidates
            .into_iter()
            .flat_map(|c| c.content.parts)
            .map(|p| p.text)
            .collect::<Vec<_>>()
            .join("\n");

        info!("[Gemini] Generated {} chars", text.len());
        Ok(text)
    }

    async fn invoke_stream(
        &self,
        _request: &InferenceRequest,
        _history: &[LlmMessage],
    ) -> Result<mpsc::Receiver<String>> {
        let (tx, rx) = mpsc::channel(256);
        let _ = tx.send("[Gemini streaming not yet implemented]".to_string()).await;
        Ok(rx)
    }

    fn provider_name(&self) -> &'static str {
        "Google Gemini (Stealth Cloud)"
    }
}
