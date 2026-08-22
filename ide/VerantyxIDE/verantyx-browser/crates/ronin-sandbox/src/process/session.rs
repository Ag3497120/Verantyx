//! Sandbox session lifecycle manager.
//!
//! A SandboxSession encapsulates the full state of a single agent task's
//! interactive OS surface — CWD, environment, process registry, and audit log.
//! Sessions are uniquely identified by UUID and can be serialized to disk
//! for resumption after a crash or handoff between Commander and Worker.

use crate::audit::event_log::{AuditLog, AuditEvent};
use crate::isolation::environment::EnvironmentBuilder;
use crate::isolation::policy::{PolicyDecision, PolicyEngine, SandboxPolicy};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::PathBuf;
use std::time::{Duration, Instant};
use tokio::process::Command;
use tokio::io::AsyncReadExt;
use tracing::{debug, info, warn};
use uuid::Uuid;

// ─────────────────────────────────────────────────────────────────────────────
// Session Metadata
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionMeta {
    pub id: Uuid,
    pub created_at: DateTime<Utc>,
    pub agent_role: String,
    pub cwd: PathBuf,
    pub command_count: usize,
}

// ─────────────────────────────────────────────────────────────────────────────
// Command Output
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExecOutput {
    pub command: String,
    pub stdout: String,
    pub stderr: String,
    pub exit_code: i32,
    pub duration_ms: u64,
    pub timed_out: bool,
    pub blocked: bool,
    pub block_reason: Option<String>,
}

impl ExecOutput {
    pub fn is_success(&self) -> bool {
        self.exit_code == 0 && !self.timed_out && !self.blocked
    }

    /// Formats a compact observation block for ReAct history injection.
    pub fn to_observation(&self) -> String {
        if self.blocked {
            return format!(
                "[OBSERVATION] ⛔ BLOCKED: {}\nReason: {}",
                self.command,
                self.block_reason.as_deref().unwrap_or("Policy violation")
            );
        }

        let status = if self.exit_code == 0 { "✅ EXIT 0" } else { &format!("❌ EXIT {}", self.exit_code) };
        let mut parts = vec![format!("$ {}", self.command), format!("[{}]", status)];

        if !self.stdout.trim().is_empty() {
            let preview = if self.stdout.len() > 4096 {
                format!("{}\n… (truncated {} bytes)", &self.stdout[..4096], self.stdout.len() - 4096)
            } else {
                self.stdout.clone()
            };
            parts.push(format!("STDOUT:\n{}", preview.trim()));
        }
        if !self.stderr.trim().is_empty() {
            parts.push(format!("STDERR:\n{}", self.stderr.trim()));
        }
        if self.timed_out {
            parts.push("⚠️  Command timed out and was killed.".to_string());
        }
        parts.push(format!("Duration: {}ms", self.duration_ms));

        parts.join("\n")
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Sandbox Session
// ─────────────────────────────────────────────────────────────────────────────

pub struct SandboxSession {
    pub meta: SessionMeta,
    policy_engine: PolicyEngine,
    env_builder: EnvironmentBuilder,
    pub audit_log: AuditLog,
    timeout_secs: u64,
    max_output_bytes: usize,
}

impl SandboxSession {
    pub fn new(cwd: PathBuf, agent_role: &str, policy: SandboxPolicy) -> Self {
        let timeout_secs = policy.max_execution_secs;
        let max_output_bytes = policy.max_output_bytes;
        Self {
            meta: SessionMeta {
                id: Uuid::new_v4(),
                created_at: Utc::now(),
                agent_role: agent_role.to_string(),
                cwd,
                command_count: 0,
            },
            policy_engine: PolicyEngine::new(policy),
            env_builder: EnvironmentBuilder::new(Default::default()),
            audit_log: AuditLog::new(1000),
            timeout_secs,
            max_output_bytes,
        }
    }

    /// Executes a command within the sandboxed session.
    pub async fn exec(&mut self, command: &str) -> ExecOutput {
        self.meta.command_count += 1;
        debug!("[Sandbox] Execute #{}: {}", self.meta.command_count, command);

        // Policy evaluation
        match self.policy_engine.evaluate(command) {
            PolicyDecision::Deny(reason) => {
                warn!("[Sandbox] Blocked: {} — {}", command, reason);
                self.audit_log.push(AuditEvent::command_blocked(
                    self.meta.id, command, &reason,
                ));
                return ExecOutput {
                    command: command.to_string(),
                    stdout: String::new(),
                    stderr: reason.clone(),
                    exit_code: -1,
                    duration_ms: 0,
                    timed_out: false,
                    blocked: true,
                    block_reason: Some(reason),
                };
            }
            PolicyDecision::Warn(msg) => {
                warn!("[Sandbox] Warning for command: {} — {}", command, msg);
            }
            PolicyDecision::Allow => {}
        }

        // Build sanitized environment
        let env = self.env_builder.build();

        // Execute with timeout
        let start = Instant::now();
        let timeout_duration = Duration::from_secs(self.timeout_secs);

        let result = tokio::time::timeout(
            timeout_duration,
            self.spawn_and_collect(command, &env),
        )
        .await;

        let duration_ms = start.elapsed().as_millis() as u64;

        match result {
            Ok(Ok((stdout, stderr, exit_code))) => {
                info!(
                    "[Sandbox] Completed in {}ms: exit={} stdout={}b stderr={}b",
                    duration_ms, exit_code, stdout.len(), stderr.len()
                );
                self.audit_log.push(AuditEvent::command_executed(
                    self.meta.id, command, exit_code,
                    stdout.len(), stderr.len(), duration_ms,
                ));
                ExecOutput {
                    command: command.to_string(),
                    stdout: self.truncate_output(&stdout),
                    stderr,
                    exit_code,
                    duration_ms,
                    timed_out: false,
                    blocked: false,
                    block_reason: None,
                }
            }
            Ok(Err(e)) => ExecOutput {
                command: command.to_string(),
                stdout: String::new(),
                stderr: e.to_string(),
                exit_code: -1,
                duration_ms,
                timed_out: false,
                blocked: false,
                block_reason: None,
            },
            Err(_) => {
                warn!("[Sandbox] Timed out after {}s: {}", self.timeout_secs, command);
                ExecOutput {
                    command: command.to_string(),
                    stdout: String::new(),
                    stderr: format!("Command timed out after {}s", self.timeout_secs),
                    exit_code: -1,
                    duration_ms,
                    timed_out: true,
                    blocked: false,
                    block_reason: None,
                }
            }
        }
    }

    async fn spawn_and_collect(
        &self,
        command: &str,
        env: &HashMap<String, String>,
    ) -> anyhow::Result<(String, String, i32)> {
        let mut child = Command::new("bash")
            .arg("-c")
            .arg(command)
            .current_dir(&self.meta.cwd)
            .envs(env)
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::piped())
            .spawn()?;

        let mut stdout_str = String::new();
        let mut stderr_str = String::new();

        if let Some(mut s) = child.stdout.take() {
            s.read_to_string(&mut stdout_str).await?;
        }
        if let Some(mut s) = child.stderr.take() {
            s.read_to_string(&mut stderr_str).await?;
        }

        let exit_code = child.wait().await?.code().unwrap_or(-1);
        Ok((stdout_str, stderr_str, exit_code))
    }

    fn truncate_output(&self, output: &str) -> String {
        if output.len() > self.max_output_bytes {
            format!(
                "{}\n… [TRUNCATED: {} bytes omitted by sandbox policy]",
                &output[..self.max_output_bytes],
                output.len() - self.max_output_bytes
            )
        } else {
            output.to_string()
        }
    }

    pub fn session_id(&self) -> Uuid {
        self.meta.id
    }
}
