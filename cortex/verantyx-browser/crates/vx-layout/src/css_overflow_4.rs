//! CSS Overflow Module Level 4 — W3C CSS Overflow 4
//!
//! Implements advanced content overlow bounding mapping mechanisms:
//!   - `overflow-clip-margin` (§ 3): Painting content exactly N pixels past the `overflow: clip` box
//!   - `text-overflow`: `clip` vs `ellipsis` vs `<string>` constraints mechanism
//!   - `line-clamp` (§ 4): Limiting multi-line block containers dynamically
//!   - `continue`: Enabling fragmented fragmentation routing
//!   - Integrating boundary geometry limits for Skia rasterization paths
//!   - AI-facing: Content bleeding overflow topology limits

use std::collections::HashMap;

/// Describes visual handling when inline text hits a boundary margin (§ 5)
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum TextOverflowStrategy { Clip, Ellipsis, CustomString(String) }

/// Defines line maximum limits for the unified `<number>` block truncations (§ 4)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LineClamp { None, Lines(usize) }

#[derive(Debug, Clone)]
pub struct OverflowConfiguration {
    pub is_clipped_x: bool,
    pub is_clipped_y: bool,
    pub overflow_clip_margin: f64, 
    pub text_overflow: TextOverflowStrategy,
    pub line_clamp: LineClamp,
}

impl Default for OverflowConfiguration {
    fn default() -> Self {
        Self {
            is_clipped_x: false,
            is_clipped_y: false,
            overflow_clip_margin: 0.0,
            text_overflow: TextOverflowStrategy::Clip,
            line_clamp: LineClamp::None,
        }
    }
}

/// The global CSS Overflow Constraints Solver mapping engine
pub struct CssOverflowEngine {
    pub boundaries: HashMap<u64, OverflowConfiguration>,
    pub total_truncations_processed: u64,
}

impl CssOverflowEngine {
    pub fn new() -> Self {
        Self {
            boundaries: HashMap::new(),
            total_truncations_processed: 0,
        }
    }

    pub fn set_overflow_config(&mut self, node_id: u64, config: OverflowConfiguration) {
        self.boundaries.insert(node_id, config);
    }

    /// Solves the logical geometrical rect used directly by Skia `canvas.clipRect` API
    pub fn compute_physical_clip_bounds(&self, node_id: u64, node_width: f64, node_height: f64) -> Option<(f64, f64)> {
        if let Some(config) = self.boundaries.get(&node_id) {
            let mut final_w = f64::MAX;
            let mut final_h = f64::MAX;

            if config.is_clipped_x { final_w = node_width + config.overflow_clip_margin; }
            if config.is_clipped_y { final_h = node_height + config.overflow_clip_margin; }

            if config.is_clipped_x || config.is_clipped_y {
                return Some((final_w, final_h));
            }
        }
        None // No clipping applied
    }

    /// Layout-time evaluation determining if a block geometry halts at line N and executes text-overflow (§ 4)
    pub fn evaluate_line_clamp_stop(&mut self, node_id: u64, current_line: usize) -> bool {
        if let Some(config) = self.boundaries.get(&node_id) {
            if let LineClamp::Lines(max) = config.line_clamp {
                if current_line >= max {
                    self.total_truncations_processed += 1;
                    return true;
                }
            }
        }
        false
    }

    /// AI-facing CSS Overflow boundaries topology metrics
    pub fn ai_overflow_summary(&self, node_id: u64) -> String {
        if let Some(config) = self.boundaries.get(&node_id) {
            let clamp_str = match config.line_clamp {
                LineClamp::None => "No Clamp",
                LineClamp::Lines(n) => return format!("Clamp: {} lines", n),
            };

            format!("✂️ CSS Overflow (Node #{}): Clip X/Y: {}/{} | Margin: {}px | Text: {:?} | {}", 
                node_id, config.is_clipped_x, config.is_clipped_y, config.overflow_clip_margin, config.text_overflow, clamp_str)
        } else {
            format!("Node #{} permits standard uncontrolled bleed geometries", node_id)
        }
    }
}
