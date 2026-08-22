//! # ronin
//!
//! The unified command-line interface for the Ronin autonomous hacker agent.
//!
//! ## Commands
//! - `ronin start`    — interactive REPL session
//! - `ronin run`      — single-shot task execution
//! - `ronin init`     — initialize a Ronin project
//! - `ronin memory`   — manage JCross spatial memory
//! - `ronin status`   — system health and configuration check
//!
//! ## Environment Variables
//! - `RONIN_MODEL`      — override primary model
//! - `RONIN_HITL`       — override HITL setting (1/0)
//! - `RONIN_MAX_STEPS`  — override max agent steps
//! - `ANTHROPIC_API_KEY` — enable Claude cloud fallback
//! - `GEMINI_API_KEY`    — enable Gemini cloud fallback

mod commands;
mod config;
mod display;
mod runtime;

use anyhow::Result;
use clap::{Parser, Subcommand};
use tracing_subscriber::EnvFilter;

// ─────────────────────────────────────────────────────────────────────────────
// CLI Definition (clap derive)
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Parser, Debug)]
#[command(
    name = "ronin",
    about = "Ronin — Autonomous Hacker Agent · Local-First · Memory-Native",
    long_about = None,
    version,
    author,
)]
struct Cli {
    /// Enable verbose debug logging
    #[arg(short, long, global = true, action = clap::ArgAction::Count)]
    verbose: u8,

    /// Suppress all non-essential output
    #[arg(short, long, global = true)]
    quiet: bool,

    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand, Debug)]
enum Commands {
    /// Launch interactive agent REPL session
    Start(commands::start::StartArgs),

    /// Execute a single task and exit
    Run(commands::run::RunArgs),

    /// Initialize a Ronin project in the current directory
    Init(commands::init::InitArgs),

    /// Manage JCross spatial memory (list, show, write, purge, stats)
    Memory(commands::memory::MemoryArgs),

    /// Show system status and configuration
    Status(commands::status::StatusArgs),

    /// M2M Tooling interface for TS Brain (shell, patch)
    Tool(commands::tool::ToolArgs),
}

// ─────────────────────────────────────────────────────────────────────────────
// Entry Point
// ─────────────────────────────────────────────────────────────────────────────

#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();

    // Initialize tracing
    let log_level = match cli.verbose {
        0 => "warn",
        1 => "info",
        2 => "debug",
        _ => "trace",
    };
    let filter = EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| EnvFilter::new(log_level));

    if !cli.quiet {
        // Wire in the new ronin-telemetry enterprise pipeline
        let _ = ronin_telemetry::init_telemetry(cli.verbose > 0);
    }

    // Boot Warden System Monitor in the background for Fault Tolerance & Cgroups
    tokio::spawn(async move {
        let mut warden = ronin_warden::SystemMonitor::default();
        loop {
            let _ = warden.check_health();
            tokio::time::sleep(std::time::Duration::from_secs(10)).await;
        }
    });

    // Dispatch to subcommand
    match cli.command {
        Commands::Start(args)  => commands::start::execute(args).await?,
        Commands::Run(args)    => commands::run::execute(args).await?,
        Commands::Init(args)   => commands::init::execute(args).await?,
        Commands::Memory(args) => commands::memory::execute(args).await?,
        Commands::Status(args) => commands::status::execute(args).await?,
        Commands::Tool(args)   => commands::tool::execute(args).await?,
    }

    Ok(())
}
