//! File editor with diff generation and HITL (Human-in-the-Loop) approval.
//!
//! This is the Cline-inspired safe modification layer. Before any file is
//! written to disk, a colored unified diff is displayed in the terminal
//! and the user must explicitly approve or reject the change.

use crate::domain::error::{Result, RoninError};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use tracing::{debug, info};

// ─────────────────────────────────────────────────────────────────────────────
// Diff Representation
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileDiff {
    pub path: PathBuf,
    pub original: String,
    pub proposed: String,
    pub unified_diff: String,
}

impl FileDiff {
    /// Renders the diff with ANSI color codes for terminal display.
    pub fn to_colored_terminal_display(&self) -> String {
        self.unified_diff
            .lines()
            .map(|line| {
                if line.starts_with('+') && !line.starts_with("+++") {
                    format!("\x1b[32m{}\x1b[0m", line) // Green
                } else if line.starts_with('-') && !line.starts_with("---") {
                    format!("\x1b[31m{}\x1b[0m", line) // Red
                } else if line.starts_with("@@") {
                    format!("\x1b[36m{}\x1b[0m", line) // Cyan
                } else {
                    line.to_string()
                }
            })
            .collect::<Vec<_>>()
            .join("\n")
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// File Editor
// ─────────────────────────────────────────────────────────────────────────────

pub struct FileEditor {
    hitl_enabled: bool,
}

impl FileEditor {
    pub fn new(hitl_enabled: bool) -> Self {
        Self { hitl_enabled }
    }

    /// Reads a file's current contents.
    pub async fn read(&self, path: &std::path::Path) -> Result<String> {
        tokio::fs::read_to_string(path)
            .await
            .map_err(RoninError::Io)
    }

    /// Proposes a file modification, shows a diff, waits for approval (if HITL enabled),
    /// then writes the new content.
    pub async fn propose_write(
        &self,
        path: &std::path::Path,
        new_content: &str,
    ) -> Result<EditDecision> {
        let original = if path.exists() {
            tokio::fs::read_to_string(path)
                .await
                .map_err(RoninError::Io)?
        } else {
            String::new()
        };

        let unified_diff = self.generate_unified_diff(
            path.to_str().unwrap_or("unknown"),
            &original,
            new_content,
        );

        let diff = FileDiff {
            path: path.to_path_buf(),
            original: original.clone(),
            proposed: new_content.to_string(),
            unified_diff,
        };

        if self.hitl_enabled {
            println!("\n{}", "=".repeat(70));
            println!("📝 Ronin proposes the following change to: {}", path.display());
            println!("{}", "=".repeat(70));
            println!("{}", diff.to_colored_terminal_display());
            println!("{}", "=".repeat(70));
            println!("Apply this change? [y/N]: ");

            let mut input = String::new();
            std::io::stdin().read_line(&mut input).ok();

            if input.trim().to_lowercase() == "y" {
                self.commit_write(path, new_content).await?;
                info!("[FileEditor] Applied: {}", path.display());
                Ok(EditDecision::Accepted(diff))
            } else {
                debug!("[FileEditor] Rejected by user: {}", path.display());
                Ok(EditDecision::Rejected(diff))
            }
        } else {
            // No HITL — apply directly
            self.commit_write(path, new_content).await?;
            info!("[FileEditor] Auto-applied: {}", path.display());
            Ok(EditDecision::AutoApplied(diff))
        }
    }

    async fn commit_write(&self, path: &std::path::Path, content: &str) -> Result<()> {
        if let Some(parent) = path.parent() {
            tokio::fs::create_dir_all(parent).await.map_err(RoninError::Io)?;
        }
        tokio::fs::write(path, content).await.map_err(RoninError::Io)
    }

    fn generate_unified_diff(&self, path: &str, original: &str, proposed: &str) -> String {
        let orig_lines: Vec<&str> = original.lines().collect();
        let new_lines: Vec<&str> = proposed.lines().collect();

        let mut result = vec![
            format!("--- a/{}", path),
            format!("+++ b/{}", path),
        ];

        for (i, (orig, new)) in orig_lines.iter().zip(new_lines.iter()).enumerate() {
            if orig != new {
                result.push(format!("@@ -{i},{} +{i},{} @@", orig_lines.len(), new_lines.len()));
                result.push(format!("-{}", orig));
                result.push(format!("+{}", new));
            }
        }

        if new_lines.len() > orig_lines.len() {
            for line in &new_lines[orig_lines.len()..] {
                result.push(format!("+{}", line));
            }
        }

        result.join("\n")
    }
}

#[derive(Debug)]
pub enum EditDecision {
    Accepted(FileDiff),
    Rejected(FileDiff),
    AutoApplied(FileDiff),
}
