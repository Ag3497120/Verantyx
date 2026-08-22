//! `ronin memory` — JCross spatial memory management commands.
//!
//! Subcommands:
//!   ronin memory list    — show all memory nodes by zone
//!   ronin memory show    — inspect a specific node
//!   ronin memory write   — write a new Front-zone node
//!   ronin memory purge   — clear a zone or all nodes
//!   ronin memory stats   — token cost summary

use crate::config::loader::load_config;
use anyhow::Result;
use clap::{Args, Subcommand};
use console::style;
use ronin_core::memory_bridge::spatial_index::SpatialIndex;

#[derive(Args, Debug)]
pub struct MemoryArgs {
    #[command(subcommand)]
    pub subcommand: MemorySubcommand,
}

#[derive(Subcommand, Debug)]
pub enum MemorySubcommand {
    /// List all memory nodes grouped by zone
    List,
    /// Show the content of a specific memory node by key
    Show {
        #[arg(value_name = "KEY")]
        key: String,
    },
    /// Write a new Front-zone memory node
    Write {
        #[arg(value_name = "KEY")]
        key: String,
        #[arg(value_name = "CONTENT")]
        content: String,
    },
    /// Purge memory nodes (all zones by default)
    Purge {
        /// Only purge a specific zone: front|near|mid|deep
        #[arg(long)]
        zone: Option<String>,
        /// Skip confirmation prompt
        #[arg(long)]
        yes: bool,
    },
    /// Show token cost statistics for each zone
    Stats,
    /// Launch an interactive system editor to manually edit JCross nodes
    Edit,
}

pub async fn execute(args: MemoryArgs) -> Result<()> {
    let config = load_config(None)?;
    let mut index = SpatialIndex::new(config.memory.root_dir.clone());

    match args.subcommand {
        MemorySubcommand::List => {
            let n = index.hydrate().await?;
            println!("\n{} {} memory nodes\n", style("🧠").bold(), style(n).cyan().bold());
            println!("{:<6} {:<24} {}", style("Zone").dim(), style("Key").dim(), style("Preview").dim());
            println!("{}", style("─".repeat(64)).dim());

            for zone in ["front", "near", "mid", "deep"] {
                let zone_path = config.memory.root_dir.join(zone);
                if !zone_path.exists() { continue; }
                let mut entries = tokio::fs::read_dir(&zone_path).await?;
                while let Some(entry) = entries.next_entry().await? {
                    let path = entry.path();
                    if path.extension().and_then(|e| e.to_str()) == Some("md") {
                        let key = path.file_stem().unwrap().to_string_lossy().to_string();
                        let content = tokio::fs::read_to_string(&path).await.unwrap_or_default();
                        let preview: String = content.lines().next().unwrap_or("").chars().take(48).collect();
                        println!(
                            "{:<6} {:<24} {}",
                            style(zone).cyan(),
                            style(&key).bold(),
                            style(preview).dim()
                        );
                    }
                }
            }
        }

        MemorySubcommand::Show { key } => {
            index.hydrate().await?;
            let node_path = config.memory.root_dir.join("front").join(format!("{}.md", key));
            if node_path.exists() {
                let content = tokio::fs::read_to_string(&node_path).await?;
                println!("\n{} {}", style("🧠 Key:").bold(), style(&key).cyan());
                println!("{}", style("─".repeat(60)).dim());
                println!("{}", content);
            } else {
                println!("{} Key not found: {}", style("⚠️").yellow(), key);
            }
        }

        MemorySubcommand::Write { key, content } => {
            index.hydrate().await.ok();
            index.write_front(&key, &content).await?;
            println!(
                "{} Written to Front zone: {}",
                style("✅").green(),
                style(&key).bold()
            );
        }

        MemorySubcommand::Purge { zone, yes } => {
            let target = zone.as_deref().unwrap_or("ALL");
            if !yes {
                println!("{} Purge zone '{}'? [y/N]: ", style("⚠️").yellow(), target);
                let mut input = String::new();
                std::io::stdin().read_line(&mut input).ok();
                if input.trim().to_lowercase() != "y" {
                    println!("Aborted.");
                    return Ok(());
                }
            }

            let zones_to_purge: Vec<&str> = if let Some(ref z) = zone {
                vec![z.as_str()]
            } else {
                vec!["front", "near", "mid", "deep"]
            };

            for z in zones_to_purge {
                let zone_path = config.memory.root_dir.join(z);
                if zone_path.exists() {
                    tokio::fs::remove_dir_all(&zone_path).await.ok();
                }
            }
            println!("{} Memory zone '{}' purged.", style("✅").green(), target);
        }

        MemorySubcommand::Stats => {
            let n = index.hydrate().await?;
            let front_content = index.front_content_string();
            let tokens = ronin_core::models::context_budget::estimate_tokens(&front_content);

            println!("\n{}", style("🧠 Memory Statistics").bold());
            println!("{}", style("─".repeat(42)).dim());
            println!("  Total nodes  : {}", style(n).cyan());
            println!("  Front token cost : {} tokens", style(tokens).yellow());
            println!("  Memory root  : {}", style(config.memory.root_dir.display()).dim());
        }

        MemorySubcommand::Edit => {
            let n = index.hydrate().await?;
            if n == 0 {
                println!("{} No memory nodes to edit.", style("⚠️").yellow());
                return Ok(());
            }

            let zones = vec!["front", "near", "mid", "deep"];
            let zone_idx = dialoguer::Select::with_theme(&dialoguer::theme::ColorfulTheme::default())
                .with_prompt("Select Spatial Zone to edit")
                .items(&zones)
                .default(0)
                .interact()?;
            
            let zone_str = zones[zone_idx];
            let zone_path = config.memory.root_dir.join(zone_str);
            
            if !zone_path.exists() {
                println!("{} Zone {} is currently empty.", style("⚠️").yellow(), zone_str);
                return Ok(());
            }

            let mut files = vec![];
            let mut entries = tokio::fs::read_dir(&zone_path).await?;
            while let Some(entry) = entries.next_entry().await? {
                if entry.path().extension().and_then(|e| e.to_str()) == Some("md") {
                    files.push(entry.path());
                }
            }

            if files.is_empty() {
                println!("{} No JCross files found in {}.", style("⚠️").yellow(), zone_str);
                return Ok(());
            }

            let file_names: Vec<String> = files.iter()
                .map(|p| p.file_name().unwrap_or_default().to_string_lossy().to_string())
                .collect();

            let file_idx = dialoguer::Select::with_theme(&dialoguer::theme::ColorfulTheme::default())
                .with_prompt("Select JCross memory node to edit")
                .items(&file_names)
                .default(0)
                .interact()?;

            let target_file = &files[file_idx];
            
            // Prefer $EDITOR, fallback to vim, or nano as next fallback.
            let editor = std::env::var("EDITOR").unwrap_or_else(|_| "vim".to_string());
            println!("{} Launching {} for {}...", style("✏️").cyan(), style(&editor).bold(), style(target_file.display()).dim());
            
            let status = std::process::Command::new(&editor)
                .arg(target_file)
                .status()?;

            if status.success() {
                println!("{} JCross spatial memory updated successfully.", style("✅").green());
            } else {
                println!("{} Editor exited with error.", style("❌").red());
            }
        }
    }

    Ok(())
}
