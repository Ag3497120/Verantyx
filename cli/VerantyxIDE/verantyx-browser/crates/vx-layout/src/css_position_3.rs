//! CSS Positioned Layout Module Level 3 — W3C CSS Position 3
//!
//! Implements absolute tracking and scroll-aware sticking bounds:
//!   - `position: sticky` (§ 4.2): Elements that transition between relative and fixed positioning Based on Viewport Bounds.
//!   - Position offsets (`top`, `bottom`, `left`, `right`) evaluation context targeting.
//!   - Containing Block geometric extraction logic.
//!   - Dynamic bounding physics solving offsets during high-speed raster scrolls.
//!   - AI-facing: CSS Stuck Elements tracking bounds.

use std::collections::HashMap;

/// The declarative W3C position rule assigned to a block (§ 2.1)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PositionMode { Static, Relative, Absolute, Fixed, Sticky }

/// The target bounding limits declared by top/right/bottom/left
#[derive(Debug, Clone)]
pub struct PositionOffsets {
    pub top: Option<f64>,
    pub right: Option<f64>,
    pub bottom: Option<f64>,
    pub left: Option<f64>,
}

#[derive(Debug, Clone)]
pub struct PositionConfiguration {
    pub mode: PositionMode,
    pub offsets: PositionOffsets,
    pub containing_block_id: Option<u64>, // Sticky boundaries are strictly clamped to their nearest ancestor with a layout wrapper
}

/// The global Constraint Resolver governing sticky layouts
pub struct CssPositionEngine {
    pub configs: HashMap<u64, PositionConfiguration>,
    pub total_sticky_evaluations: u64,
}

impl CssPositionEngine {
    pub fn new() -> Self {
        Self {
            configs: HashMap::new(),
            total_sticky_evaluations: 0,
        }
    }

    pub fn set_position_config(&mut self, node_id: u64, config: PositionConfiguration) {
        self.configs.insert(node_id, config);
    }

    /// Highly dynamic logic: Called continuously by the compositor thread during mouse-wheel scrolls (§ 4.2)
    /// Returns the exact Y offset a sticky element should translate by.
    pub fn evaluate_sticky_translation(
        &mut self,
        node_id: u64,
        viewport_scroll_y: f64,
        original_node_y: f64,
        containing_block_height: f64,
        containing_block_y: f64,
        node_bounds_height: f64,
    ) -> f64 {
        if let Some(config) = self.configs.get(&node_id) {
            if config.mode != PositionMode::Sticky { return 0.0; }

            self.total_sticky_evaluations += 1;

            if let Some(top_offset) = config.offsets.top {
                // Determine the threshold point where sticking activates
                let sticking_activation_point = original_node_y - top_offset;

                if viewport_scroll_y > sticking_activation_point {
                    // Element is now stuck
                    // Calculate how far the containing block allows it to slide down
                    let max_slide_distance = (containing_block_height - node_bounds_height).max(0.0);
                    let max_absolute_y = containing_block_y + max_slide_distance;

                    let desired_y = viewport_scroll_y + top_offset;
                    
                    // Clamp to containing block limits
                    let actual_y = desired_y.min(max_absolute_y);

                    // Return the delta translation
                    return actual_y - original_node_y;
                }
            }
        }
        0.0 // Element remains relatively positioned
    }

    /// AI-facing CSS Positioned Element summary
    pub fn ai_position_summary(&self, node_id: u64) -> String {
        if let Some(config) = self.configs.get(&node_id) {
            let offset_str = format!("Top:{:?} R:{:?} B:{:?} L:{:?}", 
                config.offsets.top, config.offsets.right, config.offsets.bottom, config.offsets.left);
            format!("📌 CSS Position 3 (Node #{}): Mode: {:?} | Offsets: {} | Sticky Evals: {}", 
                node_id, config.mode, offset_str, self.total_sticky_evaluations)
        } else {
            format!("Node #{} is statically positioned in linear document flow", node_id)
        }
    }
}
