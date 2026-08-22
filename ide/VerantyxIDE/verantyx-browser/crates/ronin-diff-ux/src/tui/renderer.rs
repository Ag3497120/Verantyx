//! Terminal UI renderer for diff visualization.
//!
//! Renders FileDiffResult to ANSI-colored terminal output with line numbers,
//! context indicators, and summary statistics. Designed to match the premium
//! visual quality of Aider and Cline-style diff displays.

use crate::diff::engine::{FileDiffResult, DiffHunk, DiffLine, LineKind};
use console::style;

// ─────────────────────────────────────────────────────────────────────────────
// Renderer Config
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone)]
pub struct RendererConfig {
    pub show_line_numbers: bool,
    pub color_enabled: bool,
    pub compact_unchanged: bool,
}

impl Default for RendererConfig {
    fn default() -> Self {
        Self {
            show_line_numbers: true,
            color_enabled: true,
            compact_unchanged: true,
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Diff Renderer
// ─────────────────────────────────────────────────────────────────────────────

pub struct DiffRenderer {
    pub cfg: RendererConfig,
}

impl DiffRenderer {
    pub fn new(cfg: RendererConfig) -> Self {
        Self { cfg }
    }

    /// Renders a full FileDiffResult to a formatted terminal string.
    pub fn render(&self, result: &FileDiffResult) -> String {
        let mut out = String::new();

        // Header
        out.push_str(&self.render_file_header(result));

        if result.hunks.is_empty() {
            out.push_str("  (no changes)\n");
            return out;
        }

        for hunk in &result.hunks {
            out.push_str(&self.render_hunk_header(hunk));
            for line in &hunk.lines {
                out.push_str(&self.render_line(line));
            }
        }

        // Stats footer
        out.push_str(&self.render_stats(result));
        out
    }

    /// Prints the rendered diff to stdout immediately.
    pub fn print(&self, result: &FileDiffResult) {
        print!("{}", self.render(result));
    }

    fn render_file_header(&self, result: &FileDiffResult) -> String {
        let label = if result.is_new_file {
            style("NEW FILE").green().bold().to_string()
        } else if result.is_deleted_file {
            style("DELETED").red().bold().to_string()
        } else {
            style("MODIFIED").yellow().bold().to_string()
        };

        format!(
            "\n╭─ {} {} ─────────────────────────────────\n",
            label,
            style(&result.path).bold()
        )
    }

    fn render_hunk_header(&self, hunk: &DiffHunk) -> String {
        let header = format!(
            "@@ -{},{} +{},{} @@",
            hunk.old_range.0,
            hunk.old_range.1.saturating_sub(hunk.old_range.0) + 1,
            hunk.new_range.0,
            hunk.new_range.1.saturating_sub(hunk.new_range.0) + 1,
        );
        format!("{}\n", style(header).cyan().dim())
    }

    fn render_line(&self, line: &DiffLine) -> String {
        let (prefix, content) = match line.kind {
            LineKind::Added => {
                let prefix = style("+").green().bold().to_string();
                let content = style(&line.content).green().to_string();
                (prefix, content)
            }
            LineKind::Removed => {
                let prefix = style("-").red().bold().to_string();
                let content = style(&line.content).red().to_string();
                (prefix, content)
            }
            LineKind::Unchanged => {
                let prefix = " ".to_string();
                let content = line.content.clone();
                (prefix, content)
            }
        };

        if self.cfg.show_line_numbers {
            let old_num = line.line_number_old
                .map(|n| format!("{:>4}", n))
                .unwrap_or_else(|| "    ".to_string());
            let new_num = line.line_number_new
                .map(|n| format!("{:>4}", n))
                .unwrap_or_else(|| "    ".to_string());

            format!("{} {} {} {}", 
                style(old_num).dim(),
                style(new_num).dim(),
                prefix,
                content.trim_end()
            ) + "\n"
        } else {
            format!("{} {}", prefix, content.trim_end()) + "\n"
        }
    }

    fn render_stats(&self, result: &FileDiffResult) -> String {
        let added = style(format!("+{}", result.total_added)).green().bold();
        let removed = style(format!("-{}", result.total_removed)).red().bold();
        format!("╰─ {} {} lines changed ─────────────────────────────\n", added, removed)
    }
}
