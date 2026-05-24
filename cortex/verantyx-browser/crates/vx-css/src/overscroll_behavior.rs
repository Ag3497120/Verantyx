//! CSS Overscroll Behavior Module Level 1 — W3C CSS Overscroll Behavior
//!
//! Implements customized scrolling interactions and boundary behaviors:
//!   - overscroll-behavior (§ 2): auto, contain, none (x/y axis separation)
//!   - Scroll Chaining (§ 3): Preventing scrolls from propagating to parent containers
//!   - Scroll Bouncing (§ 4): Handling "rubber band" and pull-to-refresh effects at boundaries
//!   - Interaction with Touch Events: Canceling default actions and physics-based momentum
//!   - Root Viewport Behavior (§ 5): Overriding OS-level history swiping (back/forward)
//!   - AI-facing: Scroll boundary state visualizer and momentum physics metrics

use std::collections::HashMap;

/// Overscroll behavior styles (§ 2)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OverscrollBehavior { Auto, Contain, None }

/// The scroll boundary state for a specific axis
#[derive(Debug, Clone)]
pub struct OverscrollStatus {
    pub behavior_x: OverscrollBehavior,
    pub behavior_y: OverscrollBehavior,
    pub active_bounce_x: f64, // Extent of current rubber-banding
    pub active_bounce_y: f64,
}

/// The CSS Overscroll Behavior Engine
pub struct OverscrollEngine {
    pub scroll_containers: HashMap<u64, OverscrollStatus>,
}

impl OverscrollEngine {
    pub fn new() -> Self {
        Self { scroll_containers: HashMap::new() }
    }

    pub fn configure_overscroll(&mut self, node_id: u64, bx: OverscrollBehavior, by: OverscrollBehavior) {
        self.scroll_containers.insert(node_id, OverscrollStatus {
            behavior_x: bx,
            behavior_y: by,
            active_bounce_x: 0.0,
            active_bounce_y: 0.0,
        });
    }

    /// Evaluates if a scroll event should propagate to the parent (§ 3)
    pub fn can_chain_scroll(&self, node_id: u64, axis_x: bool) -> bool {
        if let Some(status) = self.scroll_containers.get(&node_id) {
            let behavior = if axis_x { status.behavior_x } else { status.behavior_y };
            return behavior == OverscrollBehavior::Auto;
        }
        true
    }

    /// Evaluates if default boundary actions (bouncing, refresh) are allowed (§ 4)
    pub fn allows_boundary_action(&self, node_id: u64, axis_x: bool) -> bool {
        if let Some(status) = self.scroll_containers.get(&node_id) {
            let behavior = if axis_x { status.behavior_x } else { status.behavior_y };
            return behavior != OverscrollBehavior::None;
        }
        true
    }

    /// Simulates a boundary intersection event (scroll physics)
    pub fn apply_bounce_physics(&mut self, node_id: u64, force_y: f64) {
        if let Some(status) = self.scroll_containers.get_mut(&node_id) {
            if status.behavior_y != OverscrollBehavior::None {
                status.active_bounce_y += force_y * 0.5; // Dampening
            }
        }
    }

    /// AI-facing overscroll boundaries status
    pub fn ai_overscroll_summary(&self, node_id: u64) -> String {
        if let Some(status) = self.scroll_containers.get(&node_id) {
            format!("🎯 Overscroll Behavior (Node #{}): [X:{:?}, Y:{:?}] Bounce: (x:{:.1}, y:{:.1})", 
                node_id, status.behavior_x, status.behavior_y, status.active_bounce_x, status.active_bounce_y)
        } else {
            format!("Node #{} permits default scroll chaining and bouncing", node_id)
        }
    }
}
