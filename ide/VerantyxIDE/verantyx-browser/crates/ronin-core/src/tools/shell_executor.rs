//! Sandboxed shell execution layer.
//!
//! Provides safe, timeout-capped execution of arbitrary shell commands
//! within a configurable working directory. Captures stdout, stderr,
//! and exit codes for injection back into the ReAct loop as observations.

use crate::domain::config::SandboxConfig;
use crate::domain::error::{Result, RoninError};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use std::process::Stdio;
use std::time::Duration;
use tokio::io::AsyncReadExt;
use tokio::process::Command;
use tokio::time::timeout;
use tracing::{debug, info, warn};

// ─────────────────────────────────────────────────────────────────────────────
// Execution Output
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ShellOutput {
    pub command: String,
    pub stdout: String,
    pub stderr: String,
    pub exit_code: i32,
    pub timed_out: bool,
}

impl ShellOutput {
    /// True if the command exited with status 0 and did not time out.
    pub fn is_success(&self) -> bool {
        self.exit_code == 0 && !self.timed_out
    }

    /// Builds a compact [OBSERVATION] block for the ReAct history.
    pub fn to_observation(&self) -> String {
        let status = if self.is_success() {
            "EXIT 0 ✅".to_string()
        } else {
            format!("EXIT {} ❌", self.exit_code)
        };
        let timeout_note = if self.timed_out { "\n⚠️  Command timed out." } else { "" };

        let mut parts = vec![
            format!("$ {}", self.command),
            format!("[{}]", status),
        ];
        if !self.stdout.trim().is_empty() {
            parts.push(format!("STDOUT:\n{}", self.stdout.trim()));
        }
        if !self.stderr.trim().is_empty() {
            parts.push(format!("STDERR:\n{}", self.stderr.trim()));
        }
        parts.join("\n") + timeout_note
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Shell Executor
// ─────────────────────────────────────────────────────────────────────────────

pub struct ShellExecutor {
    cwd: PathBuf,
    timeout_secs: u64,
    allow_escape: bool,
}

impl ShellExecutor {
    pub fn new(config: &SandboxConfig) -> Self {
        Self {
            cwd: config.cwd.clone(),
            timeout_secs: config.command_timeout_secs,
            allow_escape: config.allow_filesystem_escape,
        }
    }

    /// Executes a shell command within the sandbox and returns the captured output.
    pub async fn execute(&self, command: &str) -> Result<ShellOutput> {
        debug!("[Sandbox] Executing: {}", command);

        // Safety: reject directory traversal if escaping is disabled
        if !self.allow_escape && command.contains("..") {
            warn!("[Sandbox] Rejected directory escape attempt in: {}", command);
            return Err(RoninError::ToolExecution(
                "Directory traversal ('..') is not permitted in sandboxed mode".to_string(),
            ));
        }

        let mut child = Command::new("bash")
            .arg("-c")
            .arg(command)
            .current_dir(&self.cwd)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(RoninError::Io)?;

        let timeout_duration = Duration::from_secs(self.timeout_secs);

        match timeout(timeout_duration, self.collect_output(&mut child, command)).await {
            Ok(result) => result,
            Err(_) => {
                // Kill the process on timeout
                let _ = child.kill().await;
                warn!("[Sandbox] Command timed out after {}s: {}", self.timeout_secs, command);
                Ok(ShellOutput {
                    command: command.to_string(),
                    stdout: String::new(),
                    stderr: format!("Command exceeded {}s timeout", self.timeout_secs),
                    exit_code: -1,
                    timed_out: true,
                })
            }
        }
    }

    async fn collect_output(
        &self,
        child: &mut tokio::process::Child,
        command: &str,
    ) -> Result<ShellOutput> {
        let mut stdout_str = String::new();
        let mut stderr_str = String::new();

        if let Some(mut stdout) = child.stdout.take() {
            stdout.read_to_string(&mut stdout_str).await.map_err(RoninError::Io)?;
        }
        if let Some(mut stderr) = child.stderr.take() {
            stderr.read_to_string(&mut stderr_str).await.map_err(RoninError::Io)?;
        }

        let exit_code = child
            .wait()
            .await
            .map_err(RoninError::Io)?
            .code()
            .unwrap_or(-1);

        info!(
            "[Sandbox] Command completed: exit={}, stdout={}bytes, stderr={}bytes",
            exit_code,
            stdout_str.len(),
            stderr_str.len()
        );

        Ok(ShellOutput {
            command: command.to_string(),
            stdout: stdout_str,
            stderr: stderr_str,
            exit_code,
            timed_out: false,
        })
    }
}
