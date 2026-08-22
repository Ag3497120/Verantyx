//! Backup manager — creates timestamped backups before file modifications.
//!
//! All backups are stored in a versioned `.ronin/backups/` directory.
//! Provides restore functionality for rollback scenarios.

use chrono::Utc;
use std::path::{Path, PathBuf};

pub struct BackupManager {
    backup_root: PathBuf,
}

impl BackupManager {
    pub fn new(backup_root: PathBuf) -> Self {
        Self { backup_root }
    }

    fn backup_path_for(&self, original: &Path) -> PathBuf {
        let name = original
            .file_name()
            .map(|n| n.to_string_lossy().to_string())
            .unwrap_or_else(|| "unknown".to_string());

        let timestamp = Utc::now().format("%Y%m%dT%H%M%S%.3f").to_string();
        self.backup_root.join(format!("{}.{}.bak", name, timestamp))
    }

    /// Copies the original file to a timestamped backup path.
    pub fn backup(&self, original: &Path) -> std::io::Result<PathBuf> {
        std::fs::create_dir_all(&self.backup_root)?;
        let dest = self.backup_path_for(original);
        std::fs::copy(original, &dest)?;
        Ok(dest)
    }

    /// Finds the most recent backup for a file and restores it.
    pub fn restore(&self, original: &Path) -> std::io::Result<()> {
        let name = original
            .file_name()
            .map(|n| n.to_string_lossy().to_string())
            .unwrap_or_default();

        let mut backups: Vec<PathBuf> = std::fs::read_dir(&self.backup_root)?
            .filter_map(|e| e.ok().map(|e| e.path()))
            .filter(|p| {
                p.file_name()
                    .map(|n| n.to_string_lossy().starts_with(&name))
                    .unwrap_or(false)
            })
            .collect();

        backups.sort();

        match backups.last() {
            Some(latest) => {
                std::fs::copy(latest, original)?;
                Ok(())
            }
            None => Err(std::io::Error::new(
                std::io::ErrorKind::NotFound,
                format!("No backup found for: {}", original.display()),
            )),
        }
    }
}
