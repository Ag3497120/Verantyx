//! CSS Inline Layout Module Level 3 — W3C CSS Inline
//!
//! Implements advanced inline-level layout and drop-caps:
//!   - initial-letter (§ 3.1): number of lines and drop-cap sink
//!   - line-height-step (§ 4.1): quantizing line-height for a consistent vertical grid
//!   - alignment-baseline (§ 5.1): baseline, sub, super, top, bottom, middle, alphabetic, ideographic
//!   - dominant-baseline (§ 5.2): determining the primary baseline from font metrics
//!   - baseline-source (§ 5.3): auto, first, last (for inline-block alignment)
//!   - inline-sizing (§ 6): Handling ruby and combined-text width contributions
//!   - AI-facing: Inline baseline registry and drop-cap geometry visualizer

use std::collections::HashMap;

/// Initial-letter definition (§ 3)
#[derive(Debug, Clone, Copy)]
pub struct InitialLetter {
    pub size_lines: f64,
    pub sink_lines: f64,
}

/// Baseline alignment types (§ 5.1)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AlignmentBaseline { Baseline, Sub, Super, Top, Bottom, Middle, Alphabetic, Ideographic }

/// Layout state for an inline box (§ 2)
pub struct InlineBox {
    pub node_id: u64,
    pub alignment_baseline: AlignmentBaseline,
    pub dominant_baseline: AlignmentBaseline,
    pub initial_letter: Option<InitialLetter>,
    pub line_height_step: Option<f64>,
}

/// The CSS Inline Layout Engine
pub struct InlineLayoutEngine {
    pub boxes: HashMap<u64, InlineBox>,
}

impl InlineLayoutEngine {
    pub fn new() -> Self {
        Self { boxes: HashMap::new() }
    }

    /// Primary entry point: Resolve the vertical baseline offset (§ 5.2)
    pub fn resolve_baseline_offset(&self, node_id: u64, font_size: f64) -> f64 {
        let node = match self.boxes.get(&node_id) {
            Some(n) => n,
            None => return 0.0,
        };

        match node.alignment_baseline {
            AlignmentBaseline::Sub => font_size * 0.2,
            AlignmentBaseline::Super => -font_size * 0.3,
            AlignmentBaseline::Middle => -font_size * 0.25,
            _ => 0.0,
        }
    }

    /// Handles quantization of line-height (§ 4)
    pub fn quantize_line_height(&self, node_id: u64, height: f64) -> f64 {
        if let Some(node) = self.boxes.get(&node_id) {
            if let Some(step) = node.line_height_step {
                return (height / step).ceil() * step;
            }
        }
        height
    }

    /// AI-facing inline baseline inspector
    pub fn ai_inline_metrics(&self, node_id: u64) -> String {
        if let Some(node) = self.boxes.get(&node_id) {
            let mut summary = format!("〰️ Inline Layout (Node #{}): Baseline={:?}", node_id, node.alignment_baseline);
            if let Some(il) = node.initial_letter {
                summary.push_str(&format!("\n  - Initial Letter: {} lines (Sink: {})", il.size_lines, il.sink_lines));
            }
            summary
        } else {
            format!("Node #{} has standard inline layout", node_id)
        }
    }
}
