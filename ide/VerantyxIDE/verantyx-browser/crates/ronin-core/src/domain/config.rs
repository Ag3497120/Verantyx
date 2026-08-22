//! Structured agent configuration — loaded from `ronin.toml` or env vars.
//! This replaces the flat JSON-based config from the OpenClaw legacy system
//! with a strongly-typed, validated, layered configuration architecture.

use serde::{Deserialize, Serialize};
use std::path::PathBuf;

// ─────────────────────────────────────────────────────────────────────────────
// Root Configuration
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RoninConfig {
    pub agent: AgentConfig,
    pub providers: ProviderMatrix,
    pub memory: MemoryConfig,
    pub sandbox: SandboxConfig,
    pub synapse: SynapseConfig,
}

impl Default for RoninConfig {
    fn default() -> Self {
        Self {
            agent: AgentConfig::default(),
            providers: ProviderMatrix::default(),
            memory: MemoryConfig::default(),
            sandbox: SandboxConfig::default(),
            synapse: SynapseConfig::default(),
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Agent Core Configuration
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentConfig {
    /// The primary model to run inference on (e.g. "gemma3:27b")
    pub primary_model: String,
    /// Max number of ReAct loop iterations before forced termination
    pub max_steps: u32,
    /// Whether to enforce human-in-the-loop diff approval
    pub hitl_enabled: bool,
    /// Language for system prompts ("ja" or "en")
    pub system_language: SystemLanguage,
    /// Fallback strategy when local capacity is exceeded
    pub cloud_fallback: CloudFallbackStrategy,
}

impl Default for AgentConfig {
    fn default() -> Self {
        Self {
            primary_model: "gemma3:27b".to_string(),
            max_steps: 12,
            hitl_enabled: true,
            system_language: SystemLanguage::Japanese,
            cloud_fallback: CloudFallbackStrategy::BrowserHitl,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SystemLanguage {
    #[serde(rename = "ja")]
    Japanese,
    #[serde(rename = "en")]
    English,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum CloudFallbackStrategy {
    /// Opens a stealth browser session to Gemini/ChatGPT for inference
    BrowserHitl,
    /// Calls the Anthropic Claude API directly (requires API key)
    AnthropicApi,
    /// Calls the Google Gemini API directly (requires API key)
    GeminiApi,
    /// No cloud fallback — fail loudly
    Disabled,
}

// ─────────────────────────────────────────────────────────────────────────────
// Multi-provider API Key Matrix
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ProviderMatrix {
    pub anthropic: Option<ProviderConfig>,
    pub gemini: Option<ProviderConfig>,
    pub ollama: OllamaConfig,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProviderConfig {
    pub api_key: String,
    pub base_url: Option<String>,
    pub timeout_secs: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OllamaConfig {
    pub host: String,
    pub port: u16,
}

impl Default for OllamaConfig {
    fn default() -> Self {
        Self { host: "127.0.0.1".to_string(), port: 11434 }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// JCross Memory Config
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryConfig {
    /// Root directory for the JCross spatial memory store
    pub root_dir: PathBuf,
    /// Max tokens allowed in the `Front` zone (hot context)
    pub front_max_tokens: usize,
    /// Whether to auto-select relevant context when building prompts
    pub auto_inject: bool,
    /// Freshness threshold before auto-rebuilding Near zone index
    pub freshness_days: u32,
}

impl Default for MemoryConfig {
    fn default() -> Self {
        Self {
            root_dir: dirs::home_dir()
                .unwrap_or_else(|| PathBuf::from("."))
                .join(".ronin")
                .join("memory"),
            front_max_tokens: 4096,
            auto_inject: true,
            freshness_days: 7,
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Sandbox (Shell Execution) Config
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SandboxConfig {
    /// Working directory for all shell operations
    pub cwd: PathBuf,
    /// Hard timeout in seconds for any single shell command
    pub command_timeout_secs: u64,
    /// Allow modifying files outside the cwd?
    pub allow_filesystem_escape: bool,
    /// Environment variables to inject
    pub env_overrides: std::collections::HashMap<String, String>,
}

impl Default for SandboxConfig {
    fn default() -> Self {
        Self {
            cwd: std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")),
            command_timeout_secs: 60,
            allow_filesystem_escape: false,
            env_overrides: Default::default(),
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Synapse (Channel Integrations) Config
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct SynapseConfig {
    pub discord: Option<DiscordSynapseConfig>,
    pub slack: Option<SlackSynapseConfig>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DiscordSynapseConfig {
    pub bot_token: String,
    pub allowed_channel_ids: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SlackSynapseConfig {
    pub bot_token: String,
    pub app_token: String,
}
