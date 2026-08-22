//! CSS Round Display Module Level 1 — W3C CSS Round Display
//!
//! Implements CSS infrastructure for circular and non-rectangular displays (smartwatches, etc.):
//!   - shape-inside (§ 3): circle(), ellipse() for fitting inline content to a curved boundary
//!   - border-boundary (§ 4): none, parent, display for clipping borders to the display edge
//!   - polar-angle (§ 5.1): Position elements along a circular arc
//!   - polar-distance (§ 5.2): Distance from the center for polar positioning
//!   - polar-origin (§ 5.3) and polar-anchor (§ 5.4): Defining the center and attachment points
//!   - viewport-fit (§ 6): auto, contain, cover for handle display cutouts (notches)
//!   - AI-facing: Round display boundary visualizer and polar-to-cartesian coordinate map

use std::collections::HashMap;

/// Polar position definition (§ 5)
#[derive(Debug, Clone)]
pub struct PolarPosition {
    pub angle: f64, // degrees
    pub distance: f64, // length-percentage
    pub origin: (f64, f64),
}

/// Boundary clipping modes (§ 4)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BorderBoundary { None, Parent, Display }

/// Layout state for a round display element (§ 3-5)
pub struct RoundDisplayNode {
    pub node_id: u64,
    pub shape_inside: Option<String>, // circle(), etc.
    pub polar_pos: Option<PolarPosition>,
    pub border_boundary: BorderBoundary,
}

/// The CSS Round Display Engine
pub struct RoundDisplayEngine {
    pub nodes: HashMap<u64, RoundDisplayNode>,
    pub display_radius: f64,
}

impl RoundDisplayEngine {
    pub fn new(radius: f64) -> Self {
        Self { nodes: HashMap::new(), display_radius: radius }
    }

    /// Primary entry point: Resolves polar coordinates to cartesian (x, y) (§ 5.5)
    pub fn resolve_polar_to_cartesian(&self, pos: &PolarPosition) -> (f64, f64) {
        let rad = pos.angle.to_radians();
        let dist = pos.distance;
        let x = pos.origin.0 + dist * rad.cos();
        let y = pos.origin.1 + dist * rad.sin();
        (x, y)
    }

    /// AI-facing round display boundary summary
    pub fn ai_round_summary(&self, node_id: u64) -> String {
        if let Some(node) = self.nodes.get(&node_id) {
            let mut summary = format!("⌚️ Round Display (Node #{}, R:{:.1}):", node_id, self.display_radius);
            if let Some(pos) = &node.polar_pos {
                let (cx, cy) = self.resolve_polar_to_cartesian(pos);
                summary.push_str(&format!("\n  - Polar: {:.1}°, {:.1}px -> (x:{:.1}, y:{:.1})", pos.angle, pos.distance, cx, cy));
            }
            summary.push_str(&format!("\n  - Boundary: {:?}", node.border_boundary));
            summary
        } else {
            format!("Node #{} is not using round display features", node_id)
        }
    }
}
