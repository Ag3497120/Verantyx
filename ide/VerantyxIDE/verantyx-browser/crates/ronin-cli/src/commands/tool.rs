//! `ronin tool` — Machine-to-Machine bridge for TypeScript Brain.
//!
//! Subcommands:
//!   `ronin tool shell --cmd="ls -la"` -> Runs safe sandbox shell, emits JSON
//!   `ronin tool patch <file>`         -> Reads new content from STDIN, computes diff, does TUI HITL, emits JSON

use crate::config::loader::load_config;
use anyhow::{Context, Result};
use clap::{Args, Subcommand};
use console::style;
use ronin_diff_ux::{
    diff::engine::{DiffEngine, DiffGranularity},
    patch::applicator::PatchApplicator,
    tui::{
        approval_prompt::{ApprovalDecision, ApprovalSession},
        renderer::{DiffRenderer, RendererConfig},
    },
};
use ronin_sandbox::{
    isolation::policy::SandboxPolicy,
    process::session::SandboxSession,
};
use serde_json::json;
use std::io::{self, Read};
use std::path::PathBuf;

#[derive(Args, Debug)]
pub struct ToolArgs {
    #[command(subcommand)]
    pub subcommand: ToolSubcommand,
}

#[derive(Subcommand, Debug)]
pub enum ToolSubcommand {
    /// Execute a shell command via Ronin Sandbox
    Shell {
        #[arg(short, long)]
        cmd: String,
        #[arg(short = 'C', long)]
        cwd: Option<PathBuf>,
    },
    /// Propose a patch to a file (reads new content from --patch-file)
    Patch {
        #[arg(value_name = "FILE")]
        file: PathBuf,
        #[arg(long)]
        patch_file: PathBuf,
        #[arg(long)]
        no_hitl: bool,
    },
}

pub async fn execute(args: ToolArgs) -> Result<()> {
    match args.subcommand {
        ToolSubcommand::Shell { cmd, cwd } => {
            let config = load_config(None).unwrap_or_default();
            let target_cwd = cwd.unwrap_or(config.sandbox.cwd);

            // Create policy and sandbox
            let mut policy = SandboxPolicy::default();
            policy.max_execution_secs = config.sandbox.command_timeout_secs;
            policy.allow_system_writes = config.sandbox.allow_filesystem_escape;

            let mut session = SandboxSession::new(target_cwd, "TS_Worker", policy);

            // Execute
            let output = session.exec(&cmd).await;
            
            // Output pure JSON for the TS brain
            println!("{}", serde_json::to_string(&output)?);
        }

        ToolSubcommand::Patch { file, patch_file, no_hitl } => {
            // Read new content from patch file
            let new_content = tokio::fs::read_to_string(&patch_file).await.unwrap_or_default();

            let mut old_content = String::new();
            if file.exists() {
                old_content = tokio::fs::read_to_string(&file).await.unwrap_or_default();
            }

            if old_content == new_content {
                println!("{}", json!({ "status": "skipped", "reason": "No changes detected" }));
                return Ok(());
            }

            // 1. Compute Diff
            let engine = DiffEngine::new(DiffGranularity::Line);
            let path_str = file.to_string_lossy();
            let diff_result = engine.compute(&path_str, &old_content, &new_content);

            let mut approved = true;

            // 2. TUI HITL (Unless disabled)
            if !no_hitl {
                let config = load_config(None).unwrap_or_default();
                if config.agent.hitl_enabled {
                    println!("\n{} Proposed changes from TS Brain:", style("⚡").cyan().bold());
                    let config = RendererConfig::default();
                    let mut renderer = DiffRenderer::new(config);
                    renderer.render(&diff_result);

                    let mut prompt = ApprovalSession::new();
                    let decision = prompt.prompt(&diff_result);
                    
                    if decision == ApprovalDecision::Reject || decision == ApprovalDecision::RejectAll {
                        approved = false;
                        println!("{}", json!({ "status": "rejected", "reason": "Human rejected patch" }));
                        return Ok(());
                    }
                }
            }

            if approved {
                // 3. Atomically Apply
                let backup_dir = PathBuf::from(".ronin/backups");
                let applicator = PatchApplicator::new(backup_dir, false);

                match applicator.apply(&file, &new_content) {
                    Ok(_) => {
                        println!("{}", json!({ "status": "success", "file": file.to_string_lossy() }));
                    }
                    Err(e) => {
                        println!("{}", json!({ "status": "error", "error": e.to_string() }));
                    }
                }
            }
        }
    }

    Ok(())
}
