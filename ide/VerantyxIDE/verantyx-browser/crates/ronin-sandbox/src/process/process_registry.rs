//! Process registry — tracks all child processes spawned by the sandbox.
//!
//! Maintains a live table of running PIDs with their metadata, enabling
//! the Ronin agent to inspect, signal, and kill any subprocess it created.
//! Prevents zombie process accumulation during long ReAct sessions.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use tokio::process::Child;
use tracing::{debug, info, warn};
use uuid::Uuid;

// ─────────────────────────────────────────────────────────────────────────────
// Process Record
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProcessRecord {
    pub handle_id: Uuid,
    pub command: String,
    pub pid: Option<u32>,
    pub started_at: DateTime<Utc>,
    pub status: ProcessStatus,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ProcessStatus {
    Running,
    Completed(i32),
    Killed,
    Unknown,
}

// ─────────────────────────────────────────────────────────────────────────────
// Process Registry
// ─────────────────────────────────────────────────────────────────────────────

pub struct ProcessRegistry {
    records: Arc<Mutex<HashMap<Uuid, ProcessRecord>>>,
}

impl ProcessRegistry {
    pub fn new() -> Self {
        Self { records: Arc::new(Mutex::new(HashMap::new())) }
    }

    /// Registers a newly spawned child process.
    pub fn register(&self, command: &str, pid: Option<u32>) -> Uuid {
        let id = Uuid::new_v4();
        let rec = ProcessRecord {
            handle_id: id,
            command: command.to_string(),
            pid,
            started_at: Utc::now(),
            status: ProcessStatus::Running,
        };
        self.records.lock().unwrap().insert(id, rec);
        debug!("[ProcessRegistry] Registered process {}: PID={:?}", id, pid);
        id
    }

    /// Marks a process as completed with an exit code.
    pub fn mark_completed(&self, handle: Uuid, exit_code: i32) {
        if let Some(rec) = self.records.lock().unwrap().get_mut(&handle) {
            rec.status = ProcessStatus::Completed(exit_code);
        }
    }

    /// Attempts to kill a process by handle ID.
    pub fn kill(&self, handle: Uuid) -> bool {
        let pid = {
            let records = self.records.lock().unwrap();
            records.get(&handle).and_then(|r| r.pid)
        };

        if let Some(pid) = pid {
            #[cfg(unix)]
            {
                use nix::sys::signal::{kill, Signal};
                use nix::unistd::Pid;
                match kill(Pid::from_raw(pid as i32), Signal::SIGKILL) {
                    Ok(_) => {
                        self.records.lock().unwrap()
                            .entry(handle)
                            .and_modify(|r| r.status = ProcessStatus::Killed);
                        info!("[ProcessRegistry] Killed PID {}", pid);
                        true
                    }
                    Err(e) => {
                        warn!("[ProcessRegistry] Failed to kill PID {}: {}", pid, e);
                        false
                    }
                }
            }
            #[cfg(not(unix))]
            false
        } else {
            warn!("[ProcessRegistry] No PID for handle {}", handle);
            false
        }
    }

    /// Returns all currently registered processes.
    pub fn all(&self) -> Vec<ProcessRecord> {
        self.records.lock().unwrap().values().cloned().collect()
    }

    /// Returns only running processes.
    pub fn running(&self) -> Vec<ProcessRecord> {
        self.records.lock().unwrap()
            .values()
            .filter(|r| r.status == ProcessStatus::Running)
            .cloned()
            .collect()
    }

    pub fn count(&self) -> usize {
        self.records.lock().unwrap().len()
    }
}

impl Default for ProcessRegistry {
    fn default() -> Self {
        Self::new()
    }
}
