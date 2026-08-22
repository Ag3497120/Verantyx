//! Configuration loader — reads `ronin.toml` from the user's home directory
//! or project root, with full environment variable override support.
//!
//! Priority order (highest → lowest):
//!   1. Environment variables (RONIN_MODEL, RONIN_HITL, …)
//!   2. Project-level `./ronin.toml`
//!   3. User-level `~/.ronin/config.toml`
//!   4. Built-in defaults

use anyhow::{Context, Result};
use ronin_core::domain::config::{
    AgentConfig, CloudFallbackStrategy, MemoryConfig, OllamaConfig,
    ProviderConfig, ProviderMatrix, RoninConfig, SandboxConfig,
    SynapseConfig, SystemLanguage,
};
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use tracing::{debug, info, warn};

// ─────────────────────────────────────────────────────────────────────────────
// Serializable config file shape (mirrors RoninConfig but uses Option<>)
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Default, Deserialize, Serialize)]
struct TomlConfig {
    agent: Option<TomlAgentConfig>,
    ollama: Option<TomlOllamaSection>,
    memory: Option<TomlMemorySection>,
    sandbox: Option<TomlSandboxSection>,
}

#[derive(Debug, Deserialize, Serialize)]
struct TomlAgentConfig {
    model: Option<String>,
    max_steps: Option<u32>,
    hitl: Option<bool>,
    language: Option<String>,
    cloud_fallback: Option<String>,
}

#[derive(Debug, Deserialize, Serialize)]
struct TomlOllamaSection {
    host: Option<String>,
    port: Option<u16>,
}

#[derive(Debug, Deserialize, Serialize)]
struct TomlMemorySection {
    root_dir: Option<PathBuf>,
    front_max_tokens: Option<usize>,
    auto_inject: Option<bool>,
}

#[derive(Debug, Deserialize, Serialize)]
struct TomlSandboxSection {
    cwd: Option<PathBuf>,
    timeout_secs: Option<u64>,
    allow_escape: Option<bool>,
}

// ─────────────────────────────────────────────────────────────────────────────
// Loader
// ─────────────────────────────────────────────────────────────────────────────

pub fn load_config(project_root: Option<&Path>) -> Result<RoninConfig> {
    let mut config = RoninConfig::default();

    // 1. User-level config
    if let Some(user_conf) = user_config_path() {
        if user_conf.exists() {
            debug!("[Config] Loading user config: {}", user_conf.display());
            apply_toml(&mut config, &user_conf)?;
        }
    }

    // 2. Project-level config (wins over user)
    let project_conf = project_root
        .map(|r| r.join("ronin.toml"))
        .or_else(|| Some(PathBuf::from("ronin.toml")))
        .unwrap();

    if project_conf.exists() {
        info!("[Config] Loading project config: {}", project_conf.display());
        apply_toml(&mut config, &project_conf)?;
    }

    // 3. Environment variable overrides (always win)
    apply_env_overrides(&mut config);

    info!(
        "[Config] Active model: {} | HITL: {} | MaxSteps: {}",
        config.agent.primary_model,
        config.agent.hitl_enabled,
        config.agent.max_steps
    );

    Ok(config)
}

fn user_config_path() -> Option<PathBuf> {
    dirs::home_dir().map(|h| h.join(".ronin").join("config.toml"))
}

fn apply_toml(config: &mut RoninConfig, path: &Path) -> Result<()> {
    let raw = std::fs::read_to_string(path)
        .with_context(|| format!("Failed to read config: {}", path.display()))?;

    let toml: TomlConfig = toml::from_str(&raw)
        .with_context(|| format!("Failed to parse TOML: {}", path.display()))?;

    if let Some(agent) = toml.agent {
        if let Some(m) = agent.model { config.agent.primary_model = m; }
        if let Some(s) = agent.max_steps { config.agent.max_steps = s; }
        if let Some(h) = agent.hitl { config.agent.hitl_enabled = h; }
        if let Some(lang) = agent.language {
            config.agent.system_language = match lang.as_str() {
                "en" | "english" => SystemLanguage::English,
                _ => SystemLanguage::Japanese,
            };
        }
        if let Some(fb) = agent.cloud_fallback {
            config.agent.cloud_fallback = match fb.as_str() {
                "anthropic" => CloudFallbackStrategy::AnthropicApi,
                "gemini"    => CloudFallbackStrategy::GeminiApi,
                "disabled"  => CloudFallbackStrategy::Disabled,
                _           => CloudFallbackStrategy::BrowserHitl,
            };
        }
    }

    if let Some(ollama) = toml.ollama {
        if let Some(h) = ollama.host { config.providers.ollama.host = h; }
        if let Some(p) = ollama.port { config.providers.ollama.port = p; }
    }

    if let Some(mem) = toml.memory {
        if let Some(d) = mem.root_dir        { config.memory.root_dir = d; }
        if let Some(t) = mem.front_max_tokens { config.memory.front_max_tokens = t; }
        if let Some(a) = mem.auto_inject      { config.memory.auto_inject = a; }
    }

    if let Some(sb) = toml.sandbox {
        if let Some(c) = sb.cwd          { config.sandbox.cwd = c; }
        if let Some(t) = sb.timeout_secs { config.sandbox.command_timeout_secs = t; }
        if let Some(e) = sb.allow_escape { config.sandbox.allow_filesystem_escape = e; }
    }

    Ok(())
}

fn apply_env_overrides(config: &mut RoninConfig) {
    if let Ok(model) = std::env::var("RONIN_MODEL") {
        debug!("[Config] RONIN_MODEL override: {}", model);
        config.agent.primary_model = model;
    }
    if let Ok(v) = std::env::var("RONIN_MAX_STEPS") {
        if let Ok(n) = v.parse::<u32>() {
            config.agent.max_steps = n;
        }
    }
    if let Ok(v) = std::env::var("RONIN_HITL") {
        config.agent.hitl_enabled = v == "1" || v.to_lowercase() == "true";
    }
    if let Ok(key) = std::env::var("ANTHROPIC_API_KEY") {
        config.providers.anthropic = Some(ronin_core::domain::config::ProviderConfig {
            api_key: key,
            base_url: None,
            timeout_secs: 120,
        });
    }
    if let Ok(key) = std::env::var("GEMINI_API_KEY") {
        config.providers.gemini = Some(ronin_core::domain::config::ProviderConfig {
            api_key: key,
            base_url: None,
            timeout_secs: 120,
        });
    }
}
