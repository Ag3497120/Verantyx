//! Sampling parameter control matrix.
//! Maps LLM model families to their optimal inference hyperparameters.
//! This is the core "tuning knob" system that Ronin uses to make small models
//! behave accurately rather than creatively, and large models behave strategically.

use serde::{Deserialize, Serialize};

// ─────────────────────────────────────────────────────────────────────────────
// Sampling Parameter Set
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SamplingParams {
    /// Controls output randomness. 0.0 = deterministic, 2.0 = chaotic
    pub temperature: f32,
    /// Nucleus sampling probability threshold
    pub top_p: f32,
    /// Top-K token candidates to sample from
    pub top_k: u32,
    /// Penalty applied to repeated token sequences
    pub repetition_penalty: f32,
    /// Maximum generated tokens per step
    pub max_tokens: usize,
    /// Token sequences that force stop (XML closing tags, etc.)
    pub stop_sequences: Vec<String>,
}

impl SamplingParams {
    /// Ultra-conservative sampling for lightweight models (7B-10B).
    /// These models need temperature near 0 to avoid hallucinated tool calls.
    pub fn for_lightweight() -> Self {
        Self {
            temperature: 0.05,
            top_p: 0.8,
            top_k: 20,
            repetition_penalty: 1.05,
            max_tokens: 1024,
            stop_sequences: vec![
                "</action>".to_string(),
                "</payload>".to_string(),
            ],
        }
    }

    /// Balanced sampling for mid-class models (11B-35B).
    pub fn for_midweight() -> Self {
        Self {
            temperature: 0.2,
            top_p: 0.9,
            top_k: 40,
            repetition_penalty: 1.03,
            max_tokens: 4096,
            stop_sequences: vec![],
        }
    }

    /// Generous sampling for large models / cloud (36B+, Gemini, Claude).
    /// These models can handle creative reasoning chains.
    pub fn for_heavyweight() -> Self {
        Self {
            temperature: 0.6,
            top_p: 0.95,
            top_k: 64,
            repetition_penalty: 1.0,
            max_tokens: 16384,
            stop_sequences: vec![],
        }
    }

    /// Override temperature — used when determinism is forced by the operator.
    pub fn with_temperature(mut self, t: f32) -> Self {
        self.temperature = t;
        self
    }

    /// Override max tokens — used to save context budget for shorter tasks.
    pub fn with_max_tokens(mut self, n: usize) -> Self {
        self.max_tokens = n;
        self
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Prompt Format Specification
// ─────────────────────────────────────────────────────────────────────────────

/// Controls how the message list is serialized into the underlying
/// provider's accepted raw format. Different backends have different
/// prompt templates (Ollama chat API, Anthropic messages, raw Llama tokens).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum PromptFormat {
    /// Ollama's OpenAI-compatible `/api/chat` endpoint format
    OllamaChat,
    /// Anthropic's Messages API format
    AnthropicMessages,
    /// Google Gemini's contents format
    GeminiContents,
    /// OpenAI-compatible Chat format (used by OpenAI, DeepSeek, Groq, Together, OpenRouter)
    OpenAiChat,
    /// Raw text prompt (legacy, for models that don't support chat format)
    RawText,
}

/// Full inference request specification — passed to each provider.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InferenceRequest {
    pub model: String,
    pub sampling: SamplingParams,
    pub format: PromptFormat,
    pub stream: bool,
}
