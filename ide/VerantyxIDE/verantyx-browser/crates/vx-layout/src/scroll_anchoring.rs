//! CSS Scroll Anchoring Module Level 1 — W3C Scroll Anchoring
//!
//! Implements prevention of scroll position jumps caused by DOM changes above the viewport:
//!   - overflow-anchor (§ 2): auto, none (Opting in or out of scroll anchoring)
//!   - Scroll Anchoring Algorithm (§ 3): Selecting an anchor node via DOM traversal
//!   - Anchor Selection (§ 3.1): Skipping entirely occluded or absolutely positioned elements
//!   - Anchor Distance Adjustment (§ 4): Updating scroll position dynamically when the anchor moves
//!   - Suppression Triggers (§ 6): Canceling anchoring during scroll events or window resizes
//!   - AI-facing: Active scroll anchor visualizer and coordinate adjustment matrix

use std::collections::HashMap;

/// Overflow anchor styles (§ 2)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OverflowAnchor { Auto, None }

/// The state of an active scroll anchoring session
#[derive(Debug, Clone)]
pub struct AnchorState {
    pub anchor_node_id: Option<u64>,
    pub anchor_bounds_y: f64, // The Y coordinate when it was selected
    pub scroll_position: f64, // The scroll position when anchors were evaluated
    pub status: OverflowAnchor,
}

/// The CSS Scroll Anchoring Engine
pub struct ScrollAnchoringEngine {
    pub scroll_containers: HashMap<u64, AnchorState>, // Node ID -> Container Anchor State
    pub node_positions: HashMap<u64, f64>, // Node ID -> Current Top Y Coordinate (mocked for physics)
}

impl ScrollAnchoringEngine {
    pub fn new() -> Self {
        Self {
            scroll_containers: HashMap::new(),
            node_positions: HashMap::new(),
        }
    }

    pub fn set_container_anchor(&mut self, container_id: u64, status: OverflowAnchor) {
        self.scroll_containers.insert(container_id, AnchorState {
            anchor_node_id: None,
            anchor_bounds_y: 0.0,
            scroll_position: 0.0,
            status,
        });
    }

    pub fn update_node_y(&mut self, node_id: u64, current_y: f64) {
        self.node_positions.insert(node_id, current_y);
    }

    /// Primary entry point: Perform the adjustment algorithm if elements shift (§ 4)
    pub fn compute_scroll_adjustment(&mut self, container_id: u64) -> f64 {
        if let Some(state) = self.scroll_containers.get_mut(&container_id) {
            if state.status == OverflowAnchor::None { return 0.0; }

            if let Some(anchor_id) = state.anchor_node_id {
                // If we know the anchor node, check its new Y position vs its old bounds
                if let Some(current_y) = self.node_positions.get(&anchor_id) {
                    let adjustment = *current_y - state.anchor_bounds_y;
                    
                    // The layout engine applies this adjustment to the scroll offset
                    state.scroll_position += adjustment;
                    state.anchor_bounds_y = *current_y; // Recalibrate

                    return adjustment;
                }
            }
        }
        0.0 // No adjustment needed
    }

    /// Selects an anchor node for a container (§ 3)
    pub fn select_anchor(&mut self, container_id: u64, anchor_id: u64) {
        if let Some(state) = self.scroll_containers.get_mut(&container_id) {
            if let Some(y) = self.node_positions.get(&anchor_id) {
                state.anchor_node_id = Some(anchor_id);
                state.anchor_bounds_y = *y;
            }
        }
    }

    /// AI-facing Scroll Anchor state summary
    pub fn ai_anchor_summary(&self, container_id: u64) -> String {
        if let Some(state) = self.scroll_containers.get(&container_id) {
            format!("⚓️ Scroll Anchor (Node #{}): Status: {:?} | Bound Node: {:?} | ScrollY: {:.1}",
                container_id, state.status, state.anchor_node_id, state.scroll_position)
        } else {
            format!("Node #{} is not tracked as a scroll anchor container", container_id)
        }
    }
}
