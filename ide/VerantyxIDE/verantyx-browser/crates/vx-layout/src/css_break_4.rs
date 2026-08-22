//! CSS Fragmentation Module Level 4 — W3C CSS Fragmentation 4
//!
//! Implements discrete physical breaks across page mediums and multi-column geometries:
//!   - `margin-break` (§ 4): Handling margin folding at the edge of a slice
//!   - `box-decoration-break` (§ 5): Drawing borders/shadows as `slice` vs `clone`
//!   - Bounding slice layout algorithms for Print/PDF outputs
//!   - AI-facing: CSS Physical Slicing maps

use std::collections::HashMap;

/// Denotes how margin dimensions behave when they fall explicitly on a page/column boundary (§ 4)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MarginBreakState { Auto, Keep, Discard }

/// Denotes if borders and paddings are wrapped identically on both sides of the tear (§ 5)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BoxDecorationBreakState { Slice, Clone }

/// The explicit structural declarations applied to a node's physical configuration
#[derive(Debug, Clone, Copy)]
pub struct Fragmentation4BoxConfig {
    pub margin_break: MarginBreakState,
    pub box_decoration_break: BoxDecorationBreakState,
}

impl Default for Fragmentation4BoxConfig {
    fn default() -> Self {
        Self {
            margin_break: MarginBreakState::Auto,
            box_decoration_break: BoxDecorationBreakState::Slice,
        }
    }
}

/// The global Constraint Resolver governing Print / Multicolumn intersection tears
pub struct CssFragmentation4Engine {
    pub active_configs: HashMap<u64, Fragmentation4BoxConfig>,
    pub total_tears_computed: u64,
}

impl CssFragmentation4Engine {
    pub fn new() -> Self {
        Self {
            active_configs: HashMap::new(),
            total_tears_computed: 0,
        }
    }

    pub fn set_fragment_config(&mut self, node_id: u64, config: Fragmentation4BoxConfig) {
        self.active_configs.insert(node_id, config);
    }

    /// Evaluator executed by the Physical Printer or Page Box when dropping an element
    /// Returns the active dimension limit mapping logic on the tear.
    pub fn compute_margin_tear_persistence(&mut self, node_id: u64, original_margin: f64) -> f64 {
        if let Some(config) = self.active_configs.get(&node_id) {
            self.total_tears_computed += 1;

            match config.margin_break {
                MarginBreakState::Keep => original_margin,
                MarginBreakState::Discard | MarginBreakState::Auto => 0.0,
            }
        } else {
            0.0 // W3C Default is generally to discard truncated margins
        }
    }

    /// Evaluator determining if the Render Tree needs to actively draw `border-top` / `border-bottom` 
    /// at the intersection point where it cut the text in half.
    pub fn evaluate_decoration_cloning(&self, node_id: u64) -> bool {
        if let Some(config) = self.active_configs.get(&node_id) {
            return config.box_decoration_break == BoxDecorationBreakState::Clone;
        }
        false
    }

    /// AI-facing CSS Physical Slicing topology mapped
    pub fn ai_break4_summary(&self, node_id: u64) -> String {
        if let Some(config) = self.active_configs.get(&node_id) {
            format!("✂️ CSS Break 4 (Node #{}): Margin Break: {:?} | Decor Break: {:?} | Global Intersections: {}", 
                node_id, config.margin_break, config.box_decoration_break, self.total_tears_computed)
        } else {
            format!("Node #{} executes native structural tearing logic", node_id)
        }
    }
}
