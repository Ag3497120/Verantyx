//! `ronin status` — shows comprehensive system health and configuration.
//!
//! Checks:
//!   - Ollama connectivity and available models
//!   - JCross memory zone status
//!   - Active configuration
//!   - Sandbox policy summary

use crate::config::loader::load_config;
use anyhow::Result;
use clap::Args;
use console::style;
use reqwest::Client;
use ronin_core::memory_bridge::spatial_index::SpatialIndex;
use serde::Deserialize;
use std::time::Duration;

#[derive(Args, Debug)]
pub struct StatusArgs {
    /// Show verbose details
    #[arg(short, long)]
    pub verbose: bool,
}

#[derive(Deserialize)]
struct OllamaModelsResponse {
    models: Vec<OllamaModelInfo>,
}

#[derive(Deserialize)]
struct OllamaModelInfo {
    name: String,
    size: u64,
}

pub async fn execute(args: StatusArgs) -> Result<()> {
    let config = load_config(None)?;

    header("⚡ Ronin System Status");

    // 1. Ollama connectivity check
    section("Local LLM (Ollama)");
    let ollama_url = format!(
        "http://{}:{}/api/tags",
        config.providers.ollama.host, config.providers.ollama.port
    );
    let client = Client::builder().timeout(Duration::from_secs(3)).build()?;
    match client.get(&ollama_url).send().await {
        Ok(resp) if resp.status().is_success() => {
            let models: OllamaModelsResponse = resp.json::<OllamaModelsResponse>().await.unwrap_or(
                OllamaModelsResponse { models: vec![] }
            );
            ok(&format!("Connected at {}:{}", config.providers.ollama.host, config.providers.ollama.port));
            for m in &models.models {
                let size_gb = m.size as f64 / 1_000_000_000.0;
                let active = if m.name.contains(&config.agent.primary_model) {
                    format!(" {}", style("← active").green())
                } else {
                    String::new()
                };
                detail(&format!("{:<30} {:>6.1} GB{}", m.name, size_gb, active));
            }
            if models.models.is_empty() {
                warn("No models pulled yet. Run: ollama pull gemma3:27b");
            }
        }
        _ => {
            err(&format!(
                "Ollama not reachable at {}:{}",
                config.providers.ollama.host, config.providers.ollama.port
            ));
            detail("Start Ollama: ollama serve");
        }
    }

    // 2. Cloud fallback status
    section("Cloud Fallback");
    match &config.providers.anthropic {
        Some(_) => ok("Anthropic API key configured"),
        None => info_item("Anthropic: not configured (optional)"),
    }
    match &config.providers.gemini {
        Some(_) => ok("Gemini API key configured"),
        None => info_item("Gemini: not configured (optional)"),
    }

    // 3. JCross Memory
    section("JCross Memory");
    let mut index = SpatialIndex::new(config.memory.root_dir.clone());
    match index.hydrate().await {
        Ok(n) => {
            ok(&format!("Memory root: {}", config.memory.root_dir.display()));
            let front_str = index.front_content_string();
            let front_tokens = ronin_core::models::context_budget::estimate_tokens(&front_str);
            detail(&format!("Total nodes  : {}", n));
            detail(&format!("Front tokens : {} / {}", front_tokens, config.memory.front_max_tokens));
            detail(&format!("Auto-inject  : {}", config.memory.auto_inject));
        }
        Err(e) => {
            warn(&format!("Memory not initialized: {}", e));
            detail("Run: ronin init");
        }
    }

    // 4. Agent config
    section("Agent Config");
    detail(&format!("Model         : {}", style(&config.agent.primary_model).cyan()));
    detail(&format!("Max Steps     : {}", config.agent.max_steps));
    detail(&format!("HITL          : {}", if config.agent.hitl_enabled { "enabled" } else { "disabled" }));
    detail(&format!("Cloud Fallback: {:?}", config.agent.cloud_fallback));

    // 5. Sandbox policy
    if args.verbose {
        section("Sandbox Policy");
        detail(&format!("Exec timeout  : {}s", config.sandbox.command_timeout_secs));
        detail(&format!("Allow escape  : {}", config.sandbox.allow_filesystem_escape));
        detail(&format!("Working dir   : {}", config.sandbox.cwd.display()));
    }

    println!();
    Ok(())
}

fn header(msg: &str) {
    println!("\n{}", style(msg).bold().cyan());
    println!("{}", style("═".repeat(54)).dim());
}

fn section(msg: &str) {
    println!("\n  {}", style(msg).bold());
}

fn ok(msg: &str) {
    println!("    {} {}", style("✅").green(), msg);
}

fn err(msg: &str) {
    println!("    {} {}", style("❌").red(), style(msg).red());
}

fn warn(msg: &str) {
    println!("    {} {}", style("⚠️").yellow(), style(msg).yellow());
}

fn info_item(msg: &str) {
    println!("    {} {}", style("ℹ").blue(), style(msg).dim());
}

fn detail(msg: &str) {
    println!("      {}", style(msg).dim());
}
