//! Local terminal REPL adapter for the Ronin Synapse system.
//!
//! Provides a rich interactive CLI experience enabling the user to converse
//! with the Ronin agent directly in their terminal. Supports history, multi-line
//! input, and streaming output display with a spinner progress indicator.

use crate::event::message::{SynapseMessage, SynapseResponse};
use console::style;
use indicatif::{ProgressBar, ProgressStyle};
use std::io::{BufRead, Write};
use std::time::Duration;
use tokio::sync::{broadcast, mpsc};
use tracing::info;

const SESSION_ID: &str = "local-terminal";
const RONIN_PROMPT: &str = "⚡ ronin";

// ─────────────────────────────────────────────────────────────────────────────
// Terminal REPL
// ─────────────────────────────────────────────────────────────────────────────

pub struct TerminalRepl {
    ingress_tx: mpsc::Sender<SynapseMessage>,
    egress_rx: broadcast::Receiver<SynapseResponse>,
}

impl TerminalRepl {
    pub fn new(
        ingress_tx: mpsc::Sender<SynapseMessage>,
        egress_rx: broadcast::Receiver<SynapseResponse>,
    ) -> Self {
        Self { ingress_tx, egress_rx }
    }

    /// Starts the interactive REPL loop. Blocks until the user exits.
    pub async fn run(mut self) {
        Self::print_banner();

        let stdin = std::io::stdin();
        let mut history: Vec<String> = Vec::new();

        loop {
            print!("\n{} {} ", style(RONIN_PROMPT).cyan().bold(), style("›").dim());
            std::io::stdout().flush().ok();

            let mut input = String::new();
            match stdin.lock().read_line(&mut input) {
                Ok(0) => break, // EOF
                Ok(_) => {}
                Err(_) => break,
            }

            let input = input.trim().to_string();
            if input.is_empty() { continue; }

            // Exit commands
            if matches!(input.as_str(), "exit" | "quit" | "/exit" | "/quit") {
                println!("{}", style("Ronin signing off. Stay dangerous.").dim());
                break;
            }

            history.push(input.clone());

            // Build and send message
            let msg = SynapseMessage::new_terminal(SESSION_ID, &input);
            let msg_id = msg.id.clone();

            info!("[TerminalREPL] Sending: {}", &input[..input.len().min(60)]);

            if self.ingress_tx.send(msg).await.is_err() {
                eprintln!("{}", style("Error: Agent channel closed").red());
                break;
            }

            // Show spinner while waiting for response
            let spinner = ProgressBar::new_spinner();
            spinner.set_style(
                ProgressStyle::with_template("{spinner:.cyan} {msg}")
                    .unwrap()
                    .tick_strings(&["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]),
            );
            spinner.set_message("Ronin is thinking...");
            spinner.enable_steady_tick(Duration::from_millis(80));

            // Wait for response matching our message
            let response = loop {
                match self.egress_rx.recv().await {
                    Ok(resp) if resp.reply_to_message_id.as_deref() == Some(&msg_id) => {
                        break Some(resp);
                    }
                    Ok(_) => continue, // Response was for another session
                    Err(_) => break None,
                }
            };

            spinner.finish_and_clear();

            match response {
                Some(resp) => {
                    println!();
                    println!("{}", style("─".repeat(60)).dim());
                    println!("{}", resp.content);
                    println!("{}", style("─".repeat(60)).dim());
                }
                None => {
                    println!("{}", style("(No response received from agent)").yellow());
                }
            }
        }
    }

    fn print_banner() {
        println!();
        println!("{}", style("╔════════════════════════════════════════╗").cyan());
        println!("{}", style("║  🐺  RONIN — Autonomous Agent REPL     ║").cyan().bold());
        println!("{}", style("╚════════════════════════════════════════╝").cyan());
        println!("{}", style("Type your task or command. 'exit' to quit.\n").dim());
    }
}
