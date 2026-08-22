//! vx-browser — Main Entry Point
//!
//! Supports two modes:
//! 1. Interactive TUI mode (default)
//! 2. Programmatic Bridge mode (--bridge)

use anyhow::Result;
use clap::Parser;

mod bridge;
mod stealth_bridge;
mod simulator_ui;
mod simulator_bridge;
mod tui;

#[derive(Parser)]
#[command(author, version, about, long_about = None)]
struct Cli {
    /// URL to open initially
    url: Option<String>,

    /// Run in bridge mode (programmatic control via stdin/stdout)
    #[arg(short, long)]
    bridge: bool,

    /// Makes the webview window visible (useful for bypass/visual fallback)
    #[arg(short, long)]
    visible: bool,

    /// Run JCross World Simulator Canvas
    #[arg(long)]
    simulator: bool,

    /// Set user agent string
    #[arg(short, long)]
    user_agent: Option<String>,

    /// Force dark mode
    #[arg(long)]
    dark: bool,
}

fn main() -> Result<()> {
    let cli = Cli::parse();

    if cli.bridge {
        // --- STEALTH WRY WKWEBVIEW BRIDGE ---
        // Invisible OS-native WebKit rendering avoiding Google's Botguard
        stealth_bridge::run_event_loop(cli.visible)?;
        return Ok(());
    }

    if cli.simulator {
        // --- JCROSS CONCEPT TELEPATHY SIMULATOR ---
        simulator_bridge::run_event_loop()?;
        return Ok(());
    }

    // --- TUI MODE (Phase 11 Interactive Browser) ---
    // Ratatui UI requires tokio
    let rt = tokio::runtime::Runtime::new()?;
    rt.block_on(async {
        let mut app = tui::app::TuiApp::new()?;
        if let Some(url) = cli.url {
            app.state.navigate(&url).await?;
        }
        app.run().await
    })
}

