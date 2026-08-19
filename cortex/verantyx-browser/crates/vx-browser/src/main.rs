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

    /// Run the OWN-ENGINE bridge (vx_dom + vx_layout + AiRenderer) instead
    /// of the WKWebView one.
    ///
    /// `bridge.rs` was declared as a module and called from nowhere: its
    /// click / submit / get_elements / get_spatial_map were implemented and
    /// unreachable, so the only way to drive a page was `eval_js` through
    /// the stealth bridge — OCR-shaped work on a structure that already
    /// exists. Measured 2026-08-19: `mod bridge;` present, zero call sites.
    /// This flag is the boot path; which bridge a caller wants is a
    /// caller's decision, so the stealth one stays the default.
    #[arg(long)]
    own_engine: bool,

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

    if cli.own_engine {
        // --- OWN ENGINE BRIDGE (vx_dom + vx_layout + AiRenderer) ---
        // Structure instead of pixels: get_elements / get_spatial_map /
        // click / submit read and act on the parsed document.
        let rt = tokio::runtime::Runtime::new()?;
        return rt.block_on(async {
            let mut session = bridge::BridgeSession::new()?;
            session.run_loop().await
        });
    }

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

