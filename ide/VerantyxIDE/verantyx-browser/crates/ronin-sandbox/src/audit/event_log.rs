//! Sandbox audit event log.
//!
//! Every command passed through the sandbox is recorded with its metadata,
//! timing, output, and policy decision. This log is the source of truth
//! for post-mortem analysis and JCross memory ingestion.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::VecDeque;
use std::sync::{Arc, Mutex};
use uuid::Uuid;

// ─────────────────────────────────────────────────────────────────────────────
// Audit Event
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AuditEvent {
    pub id: Uuid,
    pub session_id: Uuid,
    pub timestamp: DateTime<Utc>,
    pub kind: AuditKind,
    pub command: Option<String>,
    pub exit_code: Option<i32>,
    pub stdout_bytes: usize,
    pub stderr_bytes: usize,
    pub duration_ms: u64,
    pub policy_action: PolicyAction,
    pub tags: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum AuditKind {
    CommandExecuted,
    CommandBlocked,
    CommandTimedOut,
    FileRead,
    FileWritten,
    FileDenied,
    ProcessSpawned,
    ProcessKilled,
    NetworkBlocked,
    SessionStarted,
    SessionTerminated,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum PolicyAction {
    Allowed,
    Blocked,
    TimedOut,
    Sanitized,
}

impl AuditEvent {
    pub fn command_executed(
        session_id: Uuid,
        command: &str,
        exit_code: i32,
        stdout_bytes: usize,
        stderr_bytes: usize,
        duration_ms: u64,
    ) -> Self {
        Self {
            id: Uuid::new_v4(),
            session_id,
            timestamp: Utc::now(),
            kind: AuditKind::CommandExecuted,
            command: Some(command.to_string()),
            exit_code: Some(exit_code),
            stdout_bytes,
            stderr_bytes,
            duration_ms,
            policy_action: PolicyAction::Allowed,
            tags: vec![],
        }
    }

    pub fn command_blocked(session_id: Uuid, command: &str, reason: &str) -> Self {
        Self {
            id: Uuid::new_v4(),
            session_id,
            timestamp: Utc::now(),
            kind: AuditKind::CommandBlocked,
            command: Some(command.to_string()),
            exit_code: Some(-1),
            stdout_bytes: 0,
            stderr_bytes: reason.len(),
            duration_ms: 0,
            policy_action: PolicyAction::Blocked,
            tags: vec!["blocked".to_string()],
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Event Log (thread-safe ring buffer)
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Clone)]
pub struct AuditLog {
    inner: Arc<Mutex<VecDeque<AuditEvent>>>,
    capacity: usize,
}

impl AuditLog {
    pub fn new(capacity: usize) -> Self {
        Self {
            inner: Arc::new(Mutex::new(VecDeque::with_capacity(capacity))),
            capacity,
        }
    }

    pub fn push(&self, event: AuditEvent) {
        let mut log = self.inner.lock().unwrap();
        if log.len() >= self.capacity {
            log.pop_front();
        }
        log.push_back(event);
    }

    pub fn recent(&self, n: usize) -> Vec<AuditEvent> {
        let log = self.inner.lock().unwrap();
        log.iter().rev().take(n).cloned().collect()
    }

    pub fn total_count(&self) -> usize {
        self.inner.lock().unwrap().len()
    }

    pub fn blocked_commands(&self) -> Vec<AuditEvent> {
        self.inner.lock().unwrap()
            .iter()
            .filter(|e| e.policy_action == PolicyAction::Blocked)
            .cloned()
            .collect()
    }

    pub fn to_json_pretty(&self) -> serde_json::Result<String> {
        let log = self.inner.lock().unwrap();
        let events: Vec<&AuditEvent> = log.iter().collect();
        serde_json::to_string_pretty(&events)
    }
}
