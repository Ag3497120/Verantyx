//! `ronin run` — executes a single-shot task and exits.
//!
//! Ideal for scripting, CI pipelines, and batch automation.
//! Outputs a structured JSON result when --json flag is provided.

use crate::config::loader::load_config;
use crate::display::banner;
use crate::runtime::agent_runner::{AgentRunner, RunnerConfig};
use anyhow::Result;
use clap::Args;
use console::style;
use dialoguer::Confirm;
use ronin_core::domain::config::CloudFallbackStrategy;
use std::path::PathBuf;

#[derive(Args, Debug)]
pub struct RunArgs {
    /// The task to execute (natural language instruction)
    #[arg(value_name = "TASK")]
    pub task: String,

    /// Override the model
    #[arg(short, long)]
    pub model: Option<String>,

    /// Working directory for the sandbox
    #[arg(short = 'C', long, value_name = "DIR")]
    pub cwd: Option<PathBuf>,

    /// Disable HITL approval
    #[arg(long = "no-hitl")]
    pub no_hitl: bool,

    /// Override max steps allowed
    #[arg(long, value_name = "N")]
    pub max_steps: Option<u32>,

    /// Output result as JSON (for CI/script integration)
    #[arg(long)]
    pub json: bool,

    /// Force execution out to the Stealth Web Gemini agent instead of local models
    #[arg(long)]
    pub stealth: bool,

    /// Run the agent in Hybrid API (Qwen-Shield) mode
    #[arg(long)]
    pub api: bool,
}

pub async fn execute(args: RunArgs) -> Result<()> {
    let config = load_config(None)?;

    if !args.json {
        banner::print_banner();
        println!(
            "{} {}",
            style("Task:").dim(),
            style(&args.task).bold()
        );
        println!();
        
        if config.agent.cloud_fallback == CloudFallbackStrategy::BrowserHitl {
            let visualize = Confirm::new()
                .with_prompt("Do you want to visualize the free browser agents in a GUI window?")
                .default(true)
                .interact()?;
            if visualize {
                std::env::set_var("RONIN_VIZ_BROWSER", "1");
            }
            println!();
        }
    }

    let runner = AgentRunner::new(config.clone());

    let cwd = args.cwd
        .unwrap_or_else(|| std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")));

    let result = runner.run(RunnerConfig {
        task: args.task,
        model_override: args.model,
        hitl_override: Some(!args.no_hitl),
        force_stealth: args.stealth,
        api_mode: args.api,
        cwd,
        max_steps: args.max_steps,
    }).await?;

    if args.json {
        // Machine-readable output
        let json = serde_json::json!({
            "success": result.success,
            "steps": result.steps_taken,
            "commands": result.commands_executed,
            "response": result.final_response,
        });
        println!("{}", serde_json::to_string_pretty(&json)?);
    } else {
        // Human-readable output
        println!("{}", style("─".repeat(62)).dim());
        println!("{}", result.final_response);
        println!("{}", style("─".repeat(62)).dim());
        println!(
            "\n{} Completed in {} steps ({} commands executed)",
            if result.success {
                style("✅").green().to_string()
            } else {
                style("❌").red().to_string()
            },
            style(result.steps_taken).bold(),
            style(result.commands_executed).bold(),
        );
    }

    Ok(())
}
