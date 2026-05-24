//! Output observation and pattern detection layer.
//!
//! The OutputWatcher sits between the raw PTY/process output and the ReAct loop.
//! It applies pattern-based rules to detect prompt readiness, error signals,
//! and completion markers, enabling the agent to know when to read vs. wait.
//!
//! This subsystem is what makes Ronin resilient against interactive programs
//! that don't have clean exit codes (e.g., REPL prompts, package managers).

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use tracing::debug;

// ─────────────────────────────────────────────────────────────────────────────
// Watch Pattern
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WatchPattern {
    pub name: String,
    pub pattern: String,
    pub kind: PatternKind,
    pub priority: u8,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum PatternKind {
    /// Terminal is ready for input (stable prompt detected)
    PromptReady,
    /// A recoverable error occurred (the agent should retry or adapt)
    RecoverableError,
    /// A fatal error occurred (the agent should report back and stop)
    FatalError,
    /// Task completed successfully
    Success,
    /// Waiting for user confirmation (y/N prompts, etc.)
    ConfirmationRequired,
}

impl WatchPattern {
    pub fn shell_prompt() -> Self {
        Self {
            name: "Shell Prompt".to_string(),
            pattern: "$ ".to_string(),
            kind: PatternKind::PromptReady,
            priority: 100,
        }
    }

    pub fn command_not_found() -> Self {
        Self {
            name: "Command Not Found".to_string(),
            pattern: "command not found".to_string(),
            kind: PatternKind::RecoverableError,
            priority: 80,
        }
    }

    pub fn permission_denied() -> Self {
        Self {
            name: "Permission Denied".to_string(),
            pattern: "permission denied".to_string(),
            kind: PatternKind::FatalError,
            priority: 90,
        }
    }

    pub fn confirmation_prompt() -> Self {
        Self {
            name: "Y/N Confirmation".to_string(),
            pattern: "[y/N]".to_string(),
            kind: PatternKind::ConfirmationRequired,
            priority: 95,
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Match Result
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone)]
pub struct WatchMatch {
    pub pattern_name: String,
    pub kind: PatternKind,
    pub matched_text: String,
    pub position: usize,
}

// ─────────────────────────────────────────────────────────────────────────────
// Output Watcher
// ─────────────────────────────────────────────────────────────────────────────

pub struct OutputWatcher {
    patterns: Vec<WatchPattern>,
    accumulated: String,
    max_buffer_bytes: usize,
}

impl OutputWatcher {
    pub fn new() -> Self {
        let patterns = vec![
            WatchPattern::shell_prompt(),
            WatchPattern::command_not_found(),
            WatchPattern::permission_denied(),
            WatchPattern::confirmation_prompt(),
        ];
        Self {
            patterns,
            accumulated: String::new(),
            max_buffer_bytes: 256 * 1024, // 256 KB ring buffer
        }
    }

    /// Adds a custom pattern at runtime.
    pub fn add_pattern(&mut self, pattern: WatchPattern) {
        self.patterns.push(pattern);
        self.patterns.sort_by_key(|p| std::cmp::Reverse(p.priority));
    }

    /// Feeds new bytes into the watcher and evaluates all patterns.
    pub fn feed(&mut self, data: &str) -> Vec<WatchMatch> {
        self.accumulated.push_str(data);

        // Trim buffer if it grows too large
        if self.accumulated.len() > self.max_buffer_bytes {
            let trim_to = self.accumulated.len() - self.max_buffer_bytes;
            self.accumulated = self.accumulated[trim_to..].to_string();
        }

        let mut matches = Vec::new();
        let lower = self.accumulated.to_lowercase();

        for pattern in &self.patterns {
            let pat_lower = pattern.pattern.to_lowercase();
            if let Some(pos) = lower.rfind(&pat_lower) {
                let matched_text = self.accumulated[pos..].chars().take(80).collect();
                debug!("[OutputWatcher] Matched '{}' at position {}", pattern.name, pos);
                matches.push(WatchMatch {
                    pattern_name: pattern.name.clone(),
                    kind: pattern.kind,
                    matched_text,
                    position: pos,
                });
            }
        }

        matches
    }

    pub fn reset(&mut self) {
        self.accumulated.clear();
    }

    pub fn accumulated_text(&self) -> &str {
        &self.accumulated
    }
}

// Allow reverse ordering for sort
struct Reverse<T>(T);
impl<T: PartialOrd> PartialOrd for Reverse<T> {
    fn partial_cmp(&self, other: &Self) -> Option<std::cmp::Ordering> {
        other.0.partial_cmp(&self.0)
    }
}
impl<T: Ord> Ord for Reverse<T> {
    fn cmp(&self, other: &Self) -> std::cmp::Ordering {
        other.0.cmp(&self.0)
    }
}
impl<T: PartialEq> PartialEq for Reverse<T> {
    fn eq(&self, other: &Self) -> bool {
        self.0 == other.0
    }
}
impl<T: Eq> Eq for Reverse<T> {}

impl Default for OutputWatcher {
    fn default() -> Self {
        Self::new()
    }
}
