//! Sandboxed environment variable management.
//!
//! Every subprocess spawned by the Ronin sandbox receives a carefully
//! curated environment — not the parent process's raw env. This prevents
//! leaking API keys, auth tokens, and other sensitive variables while
//! ensuring necessary runtime paths are preserved.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

// ─────────────────────────────────────────────────────────────────────────────
// Environment Profile
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EnvironmentProfile {
    /// Variables that are always preserved from the parent process
    pub passthrough_keys: Vec<String>,
    /// Explicit override/injected variables
    pub overrides: HashMap<String, String>,
    /// Variables that are always scrubbed before subprocess execution
    pub scrub_keys: Vec<String>,
}

impl Default for EnvironmentProfile {
    fn default() -> Self {
        Self {
            passthrough_keys: vec![
                "PATH".to_string(),
                "HOME".to_string(),
                "USER".to_string(),
                "LANG".to_string(),
                "TERM".to_string(),
                "EDITOR".to_string(),
            ],
            overrides: HashMap::from([
                ("RONIN_SANDBOX".to_string(), "1".to_string()),
                ("NONINTERACTIVE".to_string(), "1".to_string()),
            ]),
            scrub_keys: vec![
                // Auth tokens — always stripped from subprocess env
                "ANTHROPIC_API_KEY".to_string(),
                "OPENAI_API_KEY".to_string(),
                "GEMINI_API_KEY".to_string(),
                "GITHUB_TOKEN".to_string(),
                "AWS_SECRET_ACCESS_KEY".to_string(),
                "AWS_ACCESS_KEY_ID".to_string(),
                "DISCORD_BOT_TOKEN".to_string(),
                "SLACK_BOT_TOKEN".to_string(),
                "NPM_TOKEN".to_string(),
                "VERCEL_TOKEN".to_string(),
            ],
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Environment Builder
// ─────────────────────────────────────────────────────────────────────────────

pub struct EnvironmentBuilder {
    profile: EnvironmentProfile,
}

impl EnvironmentBuilder {
    pub fn new(profile: EnvironmentProfile) -> Self {
        Self { profile }
    }

    /// Constructs the sanitized environment map for subprocess spawning.
    pub fn build(&self) -> HashMap<String, String> {
        let parent: HashMap<String, String> = std::env::vars().collect();
        let mut env: HashMap<String, String> = HashMap::new();

        // Phase 1: Pass through explicitly allowed parent variables
        for key in &self.profile.passthrough_keys {
            if let Some(val) = parent.get(key) {
                env.insert(key.clone(), val.clone());
            }
        }

        // Phase 2: Apply overrides (these always win)
        for (k, v) in &self.profile.overrides {
            env.insert(k.clone(), v.clone());
        }

        // Phase 3: Scrub sensitive keys that might have slipped through
        for key in &self.profile.scrub_keys {
            env.remove(key);
        }

        env
    }

    /// Adds a single override to the environment for this session.
    pub fn with_override(mut self, key: &str, val: &str) -> Self {
        self.profile.overrides.insert(key.to_string(), val.to_string());
        self
    }

    pub fn profile(&self) -> &EnvironmentProfile {
        &self.profile
    }
}
