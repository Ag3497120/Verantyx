//! Git repository inspector.
//!
//! Detects Git context, lists staged/unstaged files, and provides
//! helpers for integrating Ronin's patch workflow with the version control system.

use std::path::{Path, PathBuf};
use std::process::Command;
use tracing::{debug, warn};

// ─────────────────────────────────────────────────────────────────────────────
// Repo Detection
// ─────────────────────────────────────────────────────────────────────────────

pub struct GitInspector {
    pub repo_root: Option<PathBuf>,
}

impl GitInspector {
    /// Discovers the Git repository root from the given directory.
    pub fn detect(from: &Path) -> Self {
        let result = Command::new("git")
            .arg("rev-parse")
            .arg("--show-toplevel")
            .current_dir(from)
            .output();

        match result {
            Ok(out) if out.status.success() => {
                let root = String::from_utf8_lossy(&out.stdout).trim().to_string();
                debug!("[GitInspector] Repo root: {}", root);
                Self { repo_root: Some(PathBuf::from(root)) }
            }
            _ => {
                debug!("[GitInspector] Not a git repo: {}", from.display());
                Self { repo_root: None }
            }
        }
    }

    pub fn is_git_repo(&self) -> bool {
        self.repo_root.is_some()
    }

    /// Returns the list of tracked, modified files.
    pub fn modified_files(&self) -> Vec<PathBuf> {
        self.run_git_list_cmd(&["diff", "--name-only"])
    }

    /// Returns the list of untracked files.
    pub fn untracked_files(&self) -> Vec<PathBuf> {
        self.run_git_list_cmd(&["ls-files", "--others", "--exclude-standard"])
    }

    /// Returns files staged for commit.
    pub fn staged_files(&self) -> Vec<PathBuf> {
        self.run_git_list_cmd(&["diff", "--cached", "--name-only"])
    }

    /// Returns the current branch name.
    pub fn current_branch(&self) -> Option<String> {
        let root = self.repo_root.as_ref()?;
        let out = Command::new("git")
            .args(["rev-parse", "--abbrev-ref", "HEAD"])
            .current_dir(root)
            .output()
            .ok()?;

        if out.status.success() {
            Some(String::from_utf8_lossy(&out.stdout).trim().to_string())
        } else {
            None
        }
    }

    /// Returns the latest commit hash (short form).
    pub fn head_commit(&self) -> Option<String> {
        let root = self.repo_root.as_ref()?;
        let out = Command::new("git")
            .args(["rev-parse", "--short", "HEAD"])
            .current_dir(root)
            .output()
            .ok()?;

        if out.status.success() {
            Some(String::from_utf8_lossy(&out.stdout).trim().to_string())
        } else {
            None
        }
    }

    fn run_git_list_cmd(&self, args: &[&str]) -> Vec<PathBuf> {
        let Some(root) = &self.repo_root else { return vec![] };

        let out = Command::new("git")
            .args(args)
            .current_dir(root)
            .output();

        match out {
            Ok(o) if o.status.success() => {
                String::from_utf8_lossy(&o.stdout)
                    .lines()
                    .filter(|l| !l.is_empty())
                    .map(|l| root.join(l))
                    .collect()
            }
            _ => {
                warn!("[GitInspector] Command {:?} failed", args);
                vec![]
            }
        }
    }
}
