//! LLM provider abstraction layer.
//! Every inference backend implements this trait and can be swapped at runtime.

use crate::domain::error::Result;
use crate::models::sampling_params::InferenceRequest;
use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use tokio::sync::mpsc;

pub mod ollama;
pub mod anthropic;
pub mod gemini;
pub mod openai;

// ─────────────────────────────────────────────────────────────────────────────
// Core Message Type
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LlmMessage {
    pub role: String,
    pub content: String,
}

impl LlmMessage {
    pub fn user(content: &str) -> Self {
        Self { role: "user".to_string(), content: content.to_string() }
    }
    pub fn assistant(content: &str) -> Self {
        Self { role: "assistant".to_string(), content: content.to_string() }
    }
    pub fn system(content: &str) -> Self {
        Self { role: "system".to_string(), content: content.to_string() }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Provider Trait (async, object-safe via Box<dyn LlmProvider>)
// ─────────────────────────────────────────────────────────────────────────────

#[async_trait]
pub trait LlmProvider: Send + Sync {
    /// Execute a full non-streaming inference call.
    async fn invoke(
        &self,
        request: &InferenceRequest,
        history: &[LlmMessage],
    ) -> Result<String>;

    /// Execute a streaming inference call, returning a channel of text chunks.
    async fn invoke_stream(
        &self,
        request: &InferenceRequest,
        history: &[LlmMessage],
    ) -> Result<mpsc::Receiver<String>>;

    /// Human-readable name for this provider (for logging/tracing).
    fn provider_name(&self) -> &'static str;
}
