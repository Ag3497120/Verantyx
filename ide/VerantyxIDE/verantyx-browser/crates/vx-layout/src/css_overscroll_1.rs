//! CSS Overscroll Behavior Module Level 1 — W3C CSS Overscroll
//!
//! Implements strict scroll-chaining boundary topological definitions:
//!   - `overscroll-behavior: contain` (§ 2): Reversing scroll vectors hitting physical boundary limits
//!   - Mitigating pull-to-refresh UX collisions
//!   - `overscroll-behavior: none` native bounce disabling
//!   - AI-facing: CSS Physical Input Scroll Chain topographies

use std::collections::HashMap;

/// Defines the topological chain resolution rules when scroll energy hits a boundary
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OverscrollConstraint { 
    Auto,     // Pass scroll energy to parent
    Contain,  // Bounce locally, but do NOT pass to parent
    None      // Do not bounce, do NOT pass to parent
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct OverscrollConfiguration {
    pub x_axis: OverscrollConstraint,
    pub y_axis: OverscrollConstraint,
}

impl Default for OverscrollConfiguration {
    fn default() -> Self {
        Self { x_axis: OverscrollConstraint::Auto, y_axis: OverscrollConstraint::Auto }
    }
}

/// Computes the exact physical vector paths of user scroll inertia over nested DOM boxes
pub struct CssOverscrollEngine {
    // Explicit declarations on specific scrolling containers
    pub scroll_container_constraints: HashMap<u64, OverscrollConfiguration>,
    pub total_scroll_chaining_aborted: u64,
}

impl CssOverscrollEngine {
    pub fn new() -> Self {
        Self {
            scroll_container_constraints: HashMap::new(),
            total_scroll_chaining_aborted: 0,
        }
    }

    pub fn set_overscroll_config(&mut self, node_id: u64, config: OverscrollConfiguration) {
        self.scroll_container_constraints.insert(node_id, config);
    }

    /// Evaluated dynamically by the Input Event Thread (e.g. `wheel` or `touchmove`)
    /// Calculates if the remaining scroll energy should logically traverse UP to the Document Root.
    pub fn should_chain_scroll_to_parent(&mut self, node_id: u64, is_vertical_scroll: bool) -> bool {
        if let Some(config) = self.scroll_container_constraints.get(&node_id) {
            let active_constraint = if is_vertical_scroll { config.y_axis } else { config.x_axis };
            
            match active_constraint {
                OverscrollConstraint::Auto => return true,
                OverscrollConstraint::Contain | OverscrollConstraint::None => {
                    self.total_scroll_chaining_aborted += 1;
                    return false;
                }
            }
        }
        true // W3C Default: Scroll chaining propagates to the viewport seamlessly
    }
    
    /// Evaluates if the native OS bounds-bounce UI (Rubber-banding on mac/iOS) should trigger
    pub fn should_trigger_native_hardware_bounce(&self, node_id: u64, is_vertical_scroll: bool) -> bool {
         if let Some(config) = self.scroll_container_constraints.get(&node_id) {
            let active_constraint = if is_vertical_scroll { config.y_axis } else { config.x_axis };
            return active_constraint != OverscrollConstraint::None;
        }
        true
    }

    /// AI-facing CSS Scroll Topography Extraction
    /// Useful for determining if an inner-modal locks scroll away from the underlying body.
    pub fn ai_overscroll_summary(&self, node_id: u64) -> String {
        if let Some(config) = self.scroll_container_constraints.get(&node_id) {
            format!("🛑 CSS Overscroll 1 (Node #{}): Constraint Y: {:?} | Constraint X: {:?} | Global Aborted Chains: {}", 
                node_id, config.y_axis, config.x_axis, self.total_scroll_chaining_aborted)
        } else {
            format!("Node #{} freely propagates un-constrained scroll vectors to the topological parent", node_id)
        }
    }
}
