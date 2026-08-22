//! Patch applicator — writes approved changes to the filesystem.
//!
//! Handles atomic write operations, backup creation, and rollback
//! in case of filesystem errors. Integrates with the Git staging area
//! when a valid Git repository is detected.

use crate::patch::backup::BackupManager;
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use thiserror::Error;
use tracing::{debug, info, warn};

// ─────────────────────────────────────────────────────────────────────────────
// Errors
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Error, Debug)]
pub enum PatchError {
    #[error("I/O error while writing {path}: {source}")]
    Io { path: PathBuf, source: std::io::Error },
    #[error("Backup failed before patching {path}: {reason}")]
    BackupFailed { path: PathBuf, reason: String },
    #[error("Atomic swap failed for {path}: {reason}")]
    AtomicSwap { path: PathBuf, reason: String },
}

pub type PatchResult<T> = std::result::Result<T, PatchError>;

// ─────────────────────────────────────────────────────────────────────────────
// Apply Result Metadata
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ApplyOutcome {
    pub path: String,
    pub bytes_written: usize,
    pub backup_created: bool,
    pub git_staged: bool,
}

// ─────────────────────────────────────────────────────────────────────────────
// Patch Applicator
// ─────────────────────────────────────────────────────────────────────────────

pub struct PatchApplicator {
    backup_manager: BackupManager,
    auto_git_stage: bool,
}

impl PatchApplicator {
    pub fn new(backup_dir: PathBuf, auto_git_stage: bool) -> Self {
        Self {
            backup_manager: BackupManager::new(backup_dir),
            auto_git_stage,
        }
    }

    /// Applies the full new_content to the given path.
    /// Creates a backup before writing. Performs an atomic write via a temp file.
    pub fn apply(&self, path: &Path, new_content: &str) -> PatchResult<ApplyOutcome> {
        debug!("[PatchApplicator] Applying to: {}", path.display());

        // Create backup of existing file
        let backup_created = if path.exists() {
            match self.backup_manager.backup(path) {
                Ok(_) => {
                    info!("[PatchApplicator] Backup created for: {}", path.display());
                    true
                }
                Err(e) => {
                    warn!("[PatchApplicator] Backup failed: {} — continuing", e);
                    false
                }
            }
        } else {
            false
        };

        // Create parent dirs if needed
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)
                .map_err(|e| PatchError::Io { path: path.to_path_buf(), source: e })?;
        }

        // Atomic write via temp file
        let tmp_path = path.with_extension("ronin.tmp");
        std::fs::write(&tmp_path, new_content)
            .map_err(|e| PatchError::Io { path: tmp_path.clone(), source: e })?;

        std::fs::rename(&tmp_path, path)
            .map_err(|e| PatchError::AtomicSwap {
                path: path.to_path_buf(),
                reason: e.to_string(),
            })?;

        let bytes_written = new_content.len();
        info!("[PatchApplicator] Written {} bytes to: {}", bytes_written, path.display());

        // Optional git staging
        let git_staged = if self.auto_git_stage {
            self.stage_file(path)
        } else {
            false
        };

        Ok(ApplyOutcome {
            path: path.to_string_lossy().to_string(),
            bytes_written,
            backup_created,
            git_staged,
        })
    }

    /// Reverts the file to its backup state (rollback).
    pub fn rollback(&self, path: &Path) -> PatchResult<()> {
        match self.backup_manager.restore(path) {
            Ok(_) => {
                info!("[PatchApplicator] Rolled back: {}", path.display());
                Ok(())
            }
            Err(e) => Err(PatchError::Io {
                path: path.to_path_buf(),
                source: std::io::Error::new(std::io::ErrorKind::Other, e.to_string()),
            }),
        }
    }

    fn stage_file(&self, path: &Path) -> bool {
        let result = std::process::Command::new("git")
            .arg("add")
            .arg(path)
            .status();

        match result {
            Ok(s) if s.success() => {
                debug!("[PatchApplicator] Git staged: {}", path.display());
                true
            }
            _ => false,
        }
    }
}
