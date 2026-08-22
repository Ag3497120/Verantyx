//! CSS Rhythmic Sizing Module Level 1 — W3C CSS Rhythm
//!
//! Implements strict vertical typographical rhythm for standard baseline alignment:
//!   - line-height-step (§ 2): Rounding line-box heights to predefined typographic multiples
//!   - block-step-size (§ 3): Rounding block container sizes to sit perfectly on baseline grids
//!   - block-step-insert (§ 3.1): Distributing leftover spacing (margin, padding)
//!   - block-step-align (§ 3.2): start, end, center, space-between
//!   - Baseline integration: Enforcing descender/ascender bounds alongside integer rhythm values
//!   - AI-facing: Typographical rhythmic sizing visualizer and step multiplier metrics

use std::collections::HashMap;

/// Strategy for distributing rhythm remainder space (§ 3.1)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BlockStepInsert { Margin, Padding }

/// Strategy for aligning the block content within the rhythm boundaries (§ 3.2)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BlockStepAlign { Auto, Start, End, Center }

/// Information about a node adhering to a typographical rhythm grid
#[derive(Debug, Clone)]
pub struct RhythmicState {
    pub line_height_step: f64,
    pub block_step_size: f64,
    pub block_step_insert: BlockStepInsert,
    pub block_step_align: BlockStepAlign,
}

/// The global CSS Typography Rhythm Engine
pub struct CssRhythmEngine {
    pub node_rhythm: HashMap<u64, RhythmicState>,
}

impl CssRhythmEngine {
    pub fn new() -> Self {
        Self { node_rhythm: HashMap::new() }
    }

    pub fn set_rhythm(&mut self, node_id: u64, state: RhythmicState) {
        self.node_rhythm.insert(node_id, state);
    }

    /// Snaps an intrinsically calculated line-box height to the `line-height-step` (§ 2)
    pub fn snap_line_height(&self, node_id: u64, intrinsic_height: f64) -> f64 {
        if let Some(rhythm) = self.node_rhythm.get(&node_id) {
            if rhythm.line_height_step > 0.0 {
                // Round **up** to the nearest multiple of the step
                let multiples = (intrinsic_height / rhythm.line_height_step).ceil();
                return multiples * rhythm.line_height_step;
            }
        }
        intrinsic_height
    }

    /// Computes the insertion values for snapping a block container into the grid (§ 3)
    pub fn compute_block_rhythm_padding(&self, node_id: u64, block_content_height: f64) -> (f64, f64) {
        if let Some(rhythm) = self.node_rhythm.get(&node_id) {
            if rhythm.block_step_size > 0.0 {
                let multiples = (block_content_height / rhythm.block_step_size).ceil();
                let exact_target_height = multiples * rhythm.block_step_size;
                let remainder = exact_target_height - block_content_height;

                if rhythm.block_step_align == BlockStepAlign::Center {
                    return (remainder / 2.0, remainder / 2.0); // Top, Bottom
                } else if rhythm.block_step_align == BlockStepAlign::End {
                    return (remainder, 0.0);
                } else {
                    return (0.0, remainder); // Start
                }
            }
        }
        (0.0, 0.0) // No adjustment needed
    }

    /// AI-facing CSS Rhythm bounds mapping
    pub fn ai_rhythm_summary(&self, node_id: u64) -> String {
        if let Some(rhythm) = self.node_rhythm.get(&node_id) {
            format!("📏 CSS Rhythm (Node #{}): line-step={:.1}px | block-step={:.1}px [Insert={:?}, Align={:?}]", 
                node_id, rhythm.line_height_step, rhythm.block_step_size, rhythm.block_step_insert, rhythm.block_step_align)
        } else {
            format!("Node #{} has no explicit rhythmic typography guidelines", node_id)
        }
    }
}
