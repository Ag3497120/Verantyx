//! Core diff computation engine using the `similar` crate.
//!
//! Provides multi-algorithm diff modes, configurable granularity (line/word/char),
//! and rich metadata about each hunk for downstream rendering and patch application.

use similar::{ChangeTag, TextDiff};
use serde::{Deserialize, Serialize};

// ─────────────────────────────────────────────────────────────────────────────
// Granularity
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum DiffGranularity {
    Line,
    Word,
    Char,
}

// ─────────────────────────────────────────────────────────────────────────────
// Diff Output Types
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DiffLine {
    pub kind: LineKind,
    pub line_number_old: Option<usize>,
    pub line_number_new: Option<usize>,
    pub content: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum LineKind {
    Added,
    Removed,
    Unchanged,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DiffHunk {
    pub lines: Vec<DiffLine>,
    pub old_range: (usize, usize),
    pub new_range: (usize, usize),
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileDiffResult {
    pub path: String,
    pub hunks: Vec<DiffHunk>,
    pub total_added: usize,
    pub total_removed: usize,
    pub is_new_file: bool,
    pub is_deleted_file: bool,
}

impl FileDiffResult {
    pub fn has_changes(&self) -> bool {
        self.total_added > 0 || self.total_removed > 0
    }

    pub fn summary(&self) -> String {
        format!(
            "{}: +{} -{} ({} hunks)",
            self.path,
            self.total_added,
            self.total_removed,
            self.hunks.len()
        )
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Diff Engine
// ─────────────────────────────────────────────────────────────────────────────

pub struct DiffEngine {
    pub granularity: DiffGranularity,
    pub context_lines: usize,
}

impl DiffEngine {
    pub fn new(granularity: DiffGranularity) -> Self {
        Self { granularity, context_lines: 3 }
    }

    pub fn with_context(mut self, lines: usize) -> Self {
        self.context_lines = lines;
        self
    }

    /// Compute a rich diff between two text blobs.
    pub fn compute(&self, path: &str, old_text: &str, new_text: &str) -> FileDiffResult {
        let diff = TextDiff::from_lines(old_text, new_text);

        let mut hunks: Vec<DiffHunk> = Vec::new();
        let mut total_added = 0;
        let mut total_removed = 0;

        for group in diff.grouped_ops(self.context_lines) {
            let mut hunk_lines: Vec<DiffLine> = Vec::new();
            let mut old_start = usize::MAX;
            let mut new_start = usize::MAX;
            let mut old_end = 0;
            let mut new_end = 0;

            for op in &group {
                for change in diff.iter_changes(op) {
                    let (old_idx, new_idx) = (change.old_index(), change.new_index());
                    let kind = match change.tag() {
                        ChangeTag::Insert => {
                            total_added += 1;
                            LineKind::Added
                        }
                        ChangeTag::Delete => {
                            total_removed += 1;
                            LineKind::Removed
                        }
                        ChangeTag::Equal => LineKind::Unchanged,
                    };

                    if let Some(i) = old_idx {
                        old_start = old_start.min(i);
                        old_end = old_end.max(i);
                    }
                    if let Some(i) = new_idx {
                        new_start = new_start.min(i);
                        new_end = new_end.max(i);
                    }

                    hunk_lines.push(DiffLine {
                        kind,
                        line_number_old: old_idx.map(|i| i + 1),
                        line_number_new: new_idx.map(|i| i + 1),
                        content: change.value().to_string(),
                    });
                }
            }

            if !hunk_lines.is_empty() {
                hunks.push(DiffHunk {
                    lines: hunk_lines,
                    old_range: (old_start.saturating_add(1), old_end + 1),
                    new_range: (new_start.saturating_add(1), new_end + 1),
                });
            }
        }

        FileDiffResult {
            path: path.to_string(),
            hunks,
            total_added,
            total_removed,
            is_new_file: old_text.is_empty(),
            is_deleted_file: new_text.is_empty(),
        }
    }
}
