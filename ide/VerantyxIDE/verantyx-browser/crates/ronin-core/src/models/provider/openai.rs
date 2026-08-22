//! Generic OpenAI-compatible API provider.
//! This handles OpenAI, DeepSeek, OpenRouter, Groq, Together AI, Fireworks, etc.

use crate::domain::error::{Result, RoninError};
use crate::models::sampling_params::InferenceRequest;
use async_trait::async_trait;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::time::Duration;
use tokio::sync::mpsc;
use tracing::{info, warn};

use super::{LlmProvider, LlmMessage};

pub struct OpenAiCompatibleProvider {
    http: Client,
    api_key: String,
    base_url: String,
    provider_name: &'static str,
}

impl OpenAiCompatibleProvider {
    pub fn new(api_key: &str, base_url: &str, provider_name: &'static str) -> Self {
        Self {
            http: Client::builder()
                .timeout(Duration::from_secs(180))
                .build()
                .expect("Failed to build OpenAI HTTP client"),
            api_key: api_key.to_string(),
            base_url: base_url.to_string(),
            provider_name,
        }
    }

    pub fn openai(api_key: &str) -> Self {
        Self::new(api_key, "https://api.openai.com/v1", "OpenAI API")
    }

    pub fn deepseek(api_key: &str) -> Self {
        Self::new(api_key, "https://api.deepseek.com", "DeepSeek API")
    }

    pub fn openrouter(api_key: &str) -> Self {
        Self::new(api_key, "https://openrouter.ai/api/v1", "OpenRouter API")
    }

    pub fn groq(api_key: &str) -> Self {
        Self::new(api_key, "https://api.groq.com/openai/v1", "Groq API")
    }

    pub fn together(api_key: &str) -> Self {
        Self::new(api_key, "https://api.together.xyz/v1", "Together AI")
    }
}

#[derive(Debug, Serialize)]
struct OpenAiRequest {
    model: String,
    messages: Vec<OpenAiMessage>,
    #[serde(skip_serializing_if = "Option::is_none")]
    temperature: Option<f32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    top_p: Option<f32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    max_tokens: Option<usize>,
}

#[derive(Debug, Serialize, Deserialize)]
struct OpenAiMessage {
    role: String,
    content: String,
}

#[derive(Debug, Deserialize)]
struct OpenAiResponse {
    choices: Vec<OpenAiChoice>,
}

#[derive(Debug, Deserialize)]
struct OpenAiChoice {
    message: OpenAiMessage,
}

#[async_trait]
impl LlmProvider for OpenAiCompatibleProvider {
    async fn invoke(
        &self,
        request: &InferenceRequest,
        history: &[LlmMessage],
    ) -> Result<String> {
        let messages: Vec<OpenAiMessage> = history
            .iter()
            .map(|m| OpenAiMessage {
                role: m.role.clone(),
                content: m.content.clone(),
            })
            .collect();

        // O1 and o3-mini from OpenAI don't support system prompts or some sampling params well,
        // but for a generic proxy we will pass what the user configures.
        let body = OpenAiRequest {
            model: request.model.clone(),
            messages,
            temperature: Some(request.sampling.temperature),
            top_p: Some(request.sampling.top_p),
            max_tokens: Some(request.sampling.max_tokens),
        };

        let endpoint = format!("{}/chat/completions", self.base_url);
        
        let resp = self
            .http
            .post(&endpoint)
            .header("Authorization", format!("Bearer {}", self.api_key))
            .header("Content-Type", "application/json")
            // Optional OpenRouter Headers
            .header("HTTP-Referer", "https://github.com/verantyx/verantyx-cli")
            .header("X-Title", "Verantyx Engine")
            .json(&body)
            .send()
            .await
            .map_err(RoninError::Network)?;

        if !resp.status().is_success() {
            let status = resp.status();
            let err_body = resp.text().await.unwrap_or_default();
            warn!("[{}] HTTP {} - {}", self.provider_name, status, err_body);
            return Err(RoninError::ModelUnsupported(format!(
                "{} API returned HTTP {}: {}",
                self.provider_name, status, err_body
            )));
        }

        let parsed: OpenAiResponse = resp.json().await.map_err(RoninError::Network)?;
        
        if let Some(choice) = parsed.choices.into_iter().next() {
            let text = choice.message.content;
            info!("[{}] Generated {} chars", self.provider_name, text.len());
            Ok(text)
        } else {
            Err(RoninError::ModelUnsupported("No choices returned from OpenAi compatible endpoint".to_string()))
        }
    }

    async fn invoke_stream(
        &self,
        _request: &InferenceRequest,
        _history: &[LlmMessage],
    ) -> Result<mpsc::Receiver<String>> {
        let (tx, rx) = mpsc::channel(256);
        let _ = tx.send(format!("[{} streaming not yet implemented]", self.provider_name)).await;
        Ok(rx)
    }

    fn provider_name(&self) -> &'static str {
        self.provider_name
    }
}
