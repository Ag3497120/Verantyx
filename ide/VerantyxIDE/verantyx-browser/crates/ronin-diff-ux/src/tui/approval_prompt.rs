//! Human-in-the-Loop (HITL) approval prompt system.
//!
//! Presents the user with a rich diff view and awaits explicit approval
//! before any file modification is committed to disk. Supports batch
//! approval (accept all), selective rejection, and diff inspection modes.

use crate::diff::engine::FileDiffResult;
use crate::tui::renderer::{DiffRenderer, RendererConfig};
use console::style;
use std::io::{self, BufRead, Write};
use tracing::{info, warn};

// ─────────────────────────────────────────────────────────────────────────────
// Approval Decision
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ApprovalDecision {
    Accept,
    Reject,
    AcceptAll,
    RejectAll,
    ViewFull,
}

// ─────────────────────────────────────────────────────────────────────────────
// Approval Session
// ─────────────────────────────────────────────────────────────────────────────

pub struct ApprovalSession {
    renderer: DiffRenderer,
    batch_accept: bool,
    batch_reject: bool,
}

impl ApprovalSession {
    pub fn new() -> Self {
        Self {
            renderer: DiffRenderer::new(RendererConfig::default()),
            batch_accept: false,
            batch_reject: false,
        }
    }

    /// Presents a diff to the user and returns their decision.
    /// If a batch decision was made earlier in the session, it is applied automatically.
    pub fn prompt(&mut self, diff: &FileDiffResult) -> ApprovalDecision {
        if self.batch_accept {
            info!("[HITL] Auto-accepting (batch mode): {}", diff.path);
            return ApprovalDecision::Accept;
        }
        if self.batch_reject {
            warn!("[HITL] Auto-rejecting (batch mode): {}", diff.path);
            return ApprovalDecision::Reject;
        }

        // Render the diff
        self.renderer.print(diff);

        // Present decision menu
        self.print_menu(&diff.path);

        loop {
            let mut input = String::new();
            print!("> ");
            io::stdout().flush().ok();
            io::stdin().lock().read_line(&mut input).ok();

            match input.trim().to_lowercase().as_str() {
                "y" | "yes" | "a" | "accept" => {
                    info!("[HITL] Accepted: {}", diff.path);
                    return ApprovalDecision::Accept;
                }
                "n" | "no" | "r" | "reject" => {
                    warn!("[HITL] Rejected: {}", diff.path);
                    return ApprovalDecision::Reject;
                }
                "ya" | "accept-all" => {
                    info!("[HITL] Accepted all remaining diffs");
                    self.batch_accept = true;
                    return ApprovalDecision::AcceptAll;
                }
                "nr" | "reject-all" => {
                    warn!("[HITL] Rejected all remaining diffs");
                    self.batch_reject = true;
                    return ApprovalDecision::RejectAll;
                }
                "v" | "view" => {
                    // Re-render with more context
                    self.renderer.print(diff);
                    self.print_menu(&diff.path);
                }
                _ => {
                    println!("{}", style("Invalid input. Please enter y/n/ya/nr/v.").yellow());
                }
            }
        }
    }

    fn print_menu(&self, path: &str) {
        println!();
        println!(
            "{} Apply changes to {}?",
            style("⚡ Ronin:").cyan().bold(),
            style(path).bold()
        );
        println!(
            "  {} Accept | {} Reject | {} Accept All | {} Reject All | {} View Full",
            style("[y]").green(),
            style("[n]").red(),
            style("[ya]").green().dim(),
            style("[nr]").red().dim(),
            style("[v]").cyan().dim(),
        );
    }
}

impl Default for ApprovalSession {
    fn default() -> Self {
        Self::new()
    }
}
