//! `ronin start` — launches the interactive Synapse REPL session.
//!
//! Boots the full Ronin agent stack and connects it to the local terminal.
//! The user types tasks directly; the agent thinks, acts, and reports back.

use crate::config::loader::load_config;
use crate::display::banner;
use crate::runtime::agent_runner::{AgentRunner, RunnerConfig};
use anyhow::Result;
use clap::Args;
use console::style;
use dialoguer::Confirm;
use ronin_core::domain::config::{SystemLanguage, CloudFallbackStrategy};
use std::io::{BufRead, Write};
use std::path::PathBuf;
use tracing::info;

#[derive(Args, Debug)]
pub struct StartArgs {
    /// Override the model (e.g. --model gemma3:8b)
    #[arg(short, long)]
    pub model: Option<String>,

    /// Working directory for the agent sandbox
    #[arg(short = 'C', long, value_name = "DIR")]
    pub cwd: Option<PathBuf>,

    /// Disable HITL file approval prompts
    #[arg(long = "no-hitl")]
    pub no_hitl: bool,

    /// Override system language (en|ja)
    #[arg(long, value_name = "LANG")]
    pub lang: Option<String>,

    /// Force execution out to the Stealth Web Gemini agent instead of local models
    #[arg(long)]
    pub stealth: bool,

    /// Run the agent in Hybrid API (Qwen-Shield) mode
    #[arg(long)]
    pub api: bool,
}

pub async fn execute(args: StartArgs) -> Result<()> {
    let config = load_config(None)?;
    let runner = AgentRunner::new(config.clone());

    let model = args.model
        .as_deref()
        .unwrap_or(&config.agent.primary_model)
        .to_string();

    let hitl = if args.no_hitl { false } else { config.agent.hitl_enabled };

    let lang = match config.agent.system_language {
        SystemLanguage::Japanese => "日本語",
        SystemLanguage::English  => "English",
    };

    banner::print_banner();
    banner::print_config_summary(&model, hitl, lang, config.agent.max_steps);

    if config.agent.cloud_fallback == CloudFallbackStrategy::BrowserHitl {
        println!();
        let visualize = Confirm::new()
            .with_prompt("Do you want to visualize the free browser agents in a GUI window?")
            .default(true)
            .interact()?;
        if visualize {
            std::env::set_var("RONIN_VIZ_BROWSER", "1");
        }
    }

    info!("[start] Entering interactive REPL mode");

    let stdin = std::io::stdin();
    let cwd = args.cwd
        .unwrap_or_else(|| std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")));

    loop {
        print!("{} {} ", style("[Verantyx] ⚡").cyan().bold(), style("❯").dim());
        std::io::stdout().flush().ok();

        let mut input = String::new();
        match stdin.lock().read_line(&mut input) {
            Ok(0) => break,
            Ok(_) => {}
            Err(_) => break,
        }

        let mut is_stealth = args.stealth;
        let mut is_api = args.api;
        let mut task = input.trim().to_string();
        if task.is_empty() { continue; }

        if task.starts_with("/stealth ") {
            is_stealth = true;
            task = task.strip_prefix("/stealth ").unwrap().trim().to_string();
        } else if task.starts_with("/api ") {
            is_api = true;
            task = task.strip_prefix("/api ").unwrap().trim().to_string();
        }

        if matches!(task.as_str(), "exit" | "quit" | "/exit") {
            println!("{}", style("[SYSTEM] Terminating session. Connection closed.").dim());
            break;
        }

        if task == "/status" {
            print_status(&model, hitl, &cwd);
            continue;
        }

        if matches!(task.as_str(), "/jcross" | "/edit") {
            if let Err(e) = crate::commands::memory::execute(crate::commands::memory::MemoryArgs {
                subcommand: crate::commands::memory::MemorySubcommand::Edit
            }).await {
                eprintln!("{} Failed to launch JCross editor: {}", style("⚠️").yellow(), e);
            }
            continue;
        }

        // Run the task
        let result = runner.run(RunnerConfig {
            task: task.clone(),
            model_override: Some(model.clone()),
            hitl_override: Some(hitl),
            force_stealth: is_stealth,
            api_mode: is_api,
            cwd: cwd.clone(),
            max_steps: None,
        }).await?;

        println!();
        println!("{}", style("─".repeat(60)).dim());
        println!("{}", result.final_response);
        println!("{}", style("─".repeat(60)).dim());
        println!(
            "{} {} steps · {} commands",
            style("◎").cyan(),
            result.steps_taken,
            result.commands_executed
        );
    }

    Ok(())
}

fn print_status(model: &str, hitl: bool, cwd: &PathBuf) {
    println!();
    println!("{}", style("[VERANTYX_STATUS]").bold());
    println!(
        "  {} : {}",
        style("CORE_SLM").dim(),
        style(model).green()
    );
    println!(
        "  {} : {}",
        style("HITL_MODE").dim(),
        if hitl { style("ACTIVE").green() } else { style("DISABLED").red() }
    );
    println!(
        "  {} : {}",
        style("TARGET_DIR").dim(),
        style(cwd.display()).dim()
    );
    println!();
}
