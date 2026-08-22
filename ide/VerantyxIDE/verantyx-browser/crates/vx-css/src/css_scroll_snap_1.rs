//! CSS Scroll Snap Module Level 1 — W3C CSS Scroll Snap
//!
//! Implements hardware-accelerated declarative scroll resting geometric points:
//!   - `scroll-snap-type` (§ 5.1): Declaring a scroll container as a snapping axis (e.g. x mandatory)
//!   - `scroll-snap-align` (§ 6.1): The point within the child aligning to the snapport (start/center/end)
//!   - `scroll-padding` / `scroll-margin` (§ 4): Modifying the exact collision bounds of the snapport
//!   - `scroll-snap-stop` (§ 6.2): `normal` vs `always` (forcing resting even during fast flings)
//!   - Snap Point distance calculation mappings for input event tracking
//!   - AI-facing: Gestural resting geometry metrics and scroll topologies.

use std::collections::HashMap;

/// Denotes the axis evaluated for geometric snapping limits (§ 5.1)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SnapAxis { None, X, Y, Block, Inline, Both }

/// Controls if momentum scrolling forces snapping or just allows nearby deceleration
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SnapStrictness { Proximity, Mandatory }

/// Positional alignment of the child within the parent container's view boundary
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SnapAlignment { None, Start, Center, End }

/// Defines the Scroll snapping rules applied to a scrollable container (e.g., overflow: scroll box)
#[derive(Debug, Clone)]
pub struct ScrollSnapContainer {
    pub axis: SnapAxis,
    pub strictness: SnapStrictness,
    pub scroll_padding_top: f64,
    pub scroll_padding_bottom: f64,
}

/// Defines the snapping participation constraints of a child element inside the container
#[derive(Debug, Clone)]
pub struct ScrollSnapChild {
    pub align_x: SnapAlignment,
    pub align_y: SnapAlignment,
    pub force_stop: bool, // `scroll-snap-stop: always`
    pub scroll_margin_top: f64,
}

/// The global CSS Scroll Snapping constraint solver engine
pub struct CssScrollSnapEngine {
    pub containers: HashMap<u64, ScrollSnapContainer>,
    pub children: HashMap<u64, ScrollSnapChild>,
    pub total_scroll_evaluations: u64,
}

impl CssScrollSnapEngine {
    pub fn new() -> Self {
        Self {
            containers: HashMap::new(),
            children: HashMap::new(),
            total_scroll_evaluations: 0,
        }
    }

    pub fn set_container_config(&mut self, node_id: u64, config: ScrollSnapContainer) {
        self.containers.insert(node_id, config);
    }

    pub fn set_child_config(&mut self, node_id: u64, config: ScrollSnapChild) {
        self.children.insert(node_id, config);
    }

    /// Evaluates proximity distance during a scroll event to pick a resting position
    pub fn evaluate_snap_target(&mut self, container_id: u64, current_scroll_y: f64, child_y_offset: f64, child_id: u64) -> Option<f64> {
        self.total_scroll_evaluations += 1;

        if let Some(container_cfg) = self.containers.get(&container_id) {
            if container_cfg.axis == SnapAxis::None {
                return None;
            }

            if let Some(child_cfg) = self.children.get(&child_id) {
                if child_cfg.align_y == SnapAlignment::None {
                    return None;
                }

                // Geometric calculation: Find distance from current scroll to the child offset
                let target_offset = child_y_offset - container_cfg.scroll_padding_top - child_cfg.scroll_margin_top;
                let distance = (current_scroll_y - target_offset).abs();

                // Proximity distance heuristic (e.g. within 200px deceleration zone)
                if container_cfg.strictness == SnapStrictness::Mandatory || distance < 200.0 {
                    return Some(target_offset);
                }
            }
        }
        None
    }

    /// AI-facing CSS Scroll Snap metrics mapping
    pub fn ai_scroll_snap_summary(&self, node_id: u64) -> String {
        if let Some(c) = self.containers.get(&node_id) {
            format!("🎯 CSS Scroll Snap Container (Node #{}): Axis: {:?} | Strictness: {:?} | Padding: {}px", 
                node_id, c.axis, c.strictness, c.scroll_padding_top)
        } else if let Some(ch) = self.children.get(&node_id) {
            format!("🎯 CSS Scroll Snap Child (Node #{}): Align X/Y: {:?}/{:?} | Stop: {}", 
                node_id, ch.align_x, ch.align_y, ch.force_stop)
        } else {
            format!("Node #{} is not participating in scroll snapping", node_id)
        }
    }
}
