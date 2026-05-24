//! PTY (Pseudo-Terminal) controller for interactive shell sessions.
//!
//! Provides a fully interactive terminal emulation layer, enabling the Ronin
//! agent to control programs that require a real TTY (e.g. vim, ssh, python REPL,
//! interactive installers). Uses POSIX PTY APIs via the `nix` crate.
//!
//! Architecture:
//!   Master PTY ←→ [Ronin I/O Bridge] ←→ Agent Read/Write Channels
//!   Slave PTY  ←→ spawned bash process (sees a real terminal)

use crate::audit::event_log::{AuditLog, AuditEvent};
use crate::isolation::environment::EnvironmentBuilder;
use serde::{Deserialize, Serialize};
use std::os::unix::io::RawFd;
use std::path::PathBuf;
use thiserror::Error;
use tokio::sync::mpsc;
use tracing::{debug, info, warn};
use uuid::Uuid;

// ─────────────────────────────────────────────────────────────────────────────
// PTY Errors
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Error, Debug)]
pub enum PtyError {
    #[error("Failed to open PTY master: {0}")]
    OpenMaster(String),
    #[error("Fork failed: {0}")]
    ForkFailed(String),
    #[error("I/O error on PTY: {0}")]
    Io(#[from] std::io::Error),
    #[error("PTY session already terminated")]
    AlreadyTerminated,
}

pub type PtyResult<T> = std::result::Result<T, PtyError>;

// ─────────────────────────────────────────────────────────────────────────────
// PTY Session Config
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PtyConfig {
    pub shell: String,
    pub cwd: PathBuf,
    pub cols: u16,
    pub rows: u16,
}

impl Default for PtyConfig {
    fn default() -> Self {
        Self {
            shell: "/bin/bash".to_string(),
            cwd: std::env::current_dir().unwrap_or_else(|_| PathBuf::from("/")),
            cols: 220,
            rows: 50,
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Input/Output Channel Types
// ─────────────────────────────────────────────────────────────────────────────

/// Data written to the PTY slave (keystrokes, commands)
pub type PtyInput = Vec<u8>;
/// Data read from the PTY master (terminal output, prompts)
pub type PtyOutput = Vec<u8>;

// ─────────────────────────────────────────────────────────────────────────────
// PTY Controller
// ─────────────────────────────────────────────────────────────────────────────

pub struct PtyController {
    pub session_id: Uuid,
    config: PtyConfig,
    input_tx: mpsc::Sender<PtyInput>,
    output_rx: mpsc::Receiver<PtyOutput>,
    terminated: bool,
}

impl PtyController {
    /// Creates a new PTY session. The shell is spawned in the background.
    /// Returns the controller and the I/O channel handles.
    pub fn spawn(config: PtyConfig) -> PtyResult<Self> {
        let session_id = Uuid::new_v4();
        info!("[PTY] Spawning session {} — shell={} cwd={}", 
              session_id, config.shell, config.cwd.display());

        let (input_tx, mut input_rx) = mpsc::channel::<PtyInput>(256);
        let (output_tx, output_rx) = mpsc::channel::<PtyOutput>(256);

        let config_clone = config.clone();

        // Spawn the PTY I/O bridge on a dedicated OS thread (blocking I/O)
        std::thread::spawn(move || {
            Self::pty_thread(config_clone, input_rx, output_tx);
        });

        Ok(Self {
            session_id,
            config,
            input_tx,
            output_rx,
            terminated: false,
        })
    }

    /// Writes data to the PTY (simulates keyboard input).
    pub async fn write(&self, data: &[u8]) -> PtyResult<()> {
        if self.terminated {
            return Err(PtyError::AlreadyTerminated);
        }
        self.input_tx.send(data.to_vec()).await
            .map_err(|_| PtyError::AlreadyTerminated)
    }

    /// Sends a command string followed by Enter.
    pub async fn send_line(&self, line: &str) -> PtyResult<()> {
        let mut bytes = line.as_bytes().to_vec();
        bytes.push(b'\n');
        self.write(&bytes).await
    }

    /// Reads available output from the PTY (non-blocking poll).
    pub async fn read(&mut self) -> Option<PtyOutput> {
        self.output_rx.try_recv().ok()
    }

    /// Reads output until the given sentinel string appears or timeout elapses.
    pub async fn read_until(&mut self, sentinel: &str, timeout_ms: u64) -> String {
        let deadline = tokio::time::Instant::now()
            + tokio::time::Duration::from_millis(timeout_ms);

        let mut accumulated = String::new();

        loop {
            if tokio::time::Instant::now() >= deadline {
                break;
            }

            if let Ok(bytes) = self.output_rx.try_recv() {
                accumulated.push_str(&String::from_utf8_lossy(&bytes));
                if accumulated.contains(sentinel) {
                    break;
                }
            }

            tokio::time::sleep(tokio::time::Duration::from_millis(10)).await;
        }

        accumulated
    }

    /// Background thread managing the POSIX PTY file descriptors.
    fn pty_thread(
        config: PtyConfig,
        mut input_rx: mpsc::Receiver<PtyInput>,
        output_tx: mpsc::Sender<PtyOutput>,
    ) {
        use nix::pty::{forkpty, Winsize};
        use nix::unistd::{execvp, ForkResult, read, write};
        use std::ffi::CString;
        use std::os::unix::io::AsRawFd;

        let winsize = Winsize {
            ws_row: config.rows,
            ws_col: config.cols,
            ws_xpixel: 0,
            ws_ypixel: 0,
        };

        // SAFETY: forkpty is unsafe because it drops POSIX threads in the child.
        // It's acceptable here for development/CLI use.
        let fork_res = unsafe { forkpty(Some(&winsize), None) };

        match fork_res {
            Ok(nix::pty::ForkptyResult::Parent { child: _, master }) => {
                let master_fd = master.as_raw_fd();
                debug!("[PTY] Parent thread started, bridging master FD {}", master_fd);

                // Signal ready to caller
                let _ = output_tx.blocking_send(b"$ ".to_vec());

                let mut buf = [0u8; 4096];
                loop {
                    // We use a simple select wrapper or non-blocking loop via libc
                    let mut fd_set = unsafe { std::mem::zeroed::<libc::fd_set>() };
                    unsafe { libc::FD_SET(master_fd, &mut fd_set) };
                    
                    let mut timeout = libc::timeval { tv_sec: 0, tv_usec: 50_000 };
                    
                    let nfds = unsafe { libc::select(master_fd + 1, &mut fd_set, std::ptr::null_mut(), std::ptr::null_mut(), &mut timeout) };

                    if nfds > 0 {
                        match read(&master, &mut buf) {
                            Ok(n) if n > 0 => {
                                if output_tx.blocking_send(buf[..n].to_vec()).is_err() { break; }
                            }
                            _ => break, // EOF or error
                        }
                    }

                    // Poll input channel
                    match input_rx.try_recv() {
                        Ok(bytes) => {
                            let _ = write(&master, &bytes);
                        }
                        Err(mpsc::error::TryRecvError::Disconnected) => break,
                        Err(mpsc::error::TryRecvError::Empty) => {}
                    }
                }
                debug!("[PTY] Background thread terminating");
            }
            Ok(nix::pty::ForkptyResult::Child) => {
                std::env::set_current_dir(&config.cwd).ok();
                let shell = CString::new(config.shell).unwrap();
                let args = [shell.clone()];
                let _ = execvp(&shell, &args);
                std::process::exit(1);
            }
            Err(e) => {
                warn!("[PTY] forkpty failed: {}", e);
            }
        }
    }
}
