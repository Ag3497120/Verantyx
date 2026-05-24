//! CSS Scroll Snap Module Level 1 — W3C CSS Scroll Snap
//!
//! Implements strict scroll rest boundaries replacing custom JS scrolling physics:
//!   - `scroll-snap-type` (§ 3): `x`, `y`, `mandatory`, `proximity` boundaries
//!   - `scroll-snap-align` (§ 4): Node geometry snapping constraints (`start`, `center`, `end`)
//!   - Momentum velocity clamping equations
//!   - AI-facing: CSS Geographical scroll state limitations

use std::collections::HashMap;

/// Declares structural enforcement algorithms resolving after momentum scrolling halts (§ 3.1)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SnapStrictness { None, Mandatory, Proximity }

/// Declares which axis the snapped constraints applies to
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SnapAxis { X, Y, Both }

/// Controls intra-node alignment bounding
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SnapAlign { None, Start, Center, End }

#[derive(Debug, Clone, Copy)]
pub struct ScrollSnapTypeConfig {
    pub axis: SnapAxis,
    pub strictness: SnapStrictness,
}

/// Physical rect corresponding to an inner child the container wants to snap to
#[derive(Debug, Clone, Copy)]
pub struct ChildSnapGeometry {
    pub align_x: SnapAlign,
    pub align_y: SnapAlign,
    pub offset_x: f64,
    pub offset_y: f64,
    pub width: f64,
    pub height: f64,
}

/// The global Constraint Resolver governing inertial OS scrolling physics 
pub struct CssScrollSnapEngine {
    // Parent scroll containers mapped to configurations
    pub snap_containers: HashMap<u64, ScrollSnapTypeConfig>,
    // Parent ID -> List of physical child geometries defined by `scroll-snap-align`
    pub child_geometries: HashMap<u64, Vec<ChildSnapGeometry>>,
    
    pub total_scroll_clamps_executed: u64,
}

impl CssScrollSnapEngine {
    pub fn new() -> Self {
        Self {
            snap_containers: HashMap::new(),
            child_geometries: HashMap::new(),
            total_scroll_clamps_executed: 0,
        }
    }

    pub fn set_container(&mut self, node_id: u64, config: ScrollSnapTypeConfig) {
        self.snap_containers.insert(node_id, config);
    }

    pub fn append_child_geometry(&mut self, parent_id: u64, geom: ChildSnapGeometry) {
        let children = self.child_geometries.entry(parent_id).or_default();
        children.push(geom);
    }

    /// Fired continually as OS kinetic scrolling velocity drops near zero
    /// Computes the exact absolute coordinate to force the scrollbar to halt at.
    pub fn compute_snap_destination(&mut self, parent_id: u64, current_scroll_y: f64, viewport_height: f64) -> Option<f64> {
        if let Some(config) = self.snap_containers.get(&parent_id) {
            if config.strictness == SnapStrictness::None { return None; }

            if let Some(children) = self.child_geometries.get(&parent_id) {
                let mut closest_offset = current_scroll_y;
                let mut min_distance = f64::MAX;

                for child in children {
                    if child.align_y == SnapAlign::None { continue; }

                    // Calculate target line
                    let target_offset = match child.align_y {
                        SnapAlign::Start => child.offset_y,
                        SnapAlign::Center => child.offset_y - (viewport_height / 2.0) + (child.height / 2.0),
                        SnapAlign::End => child.offset_y - viewport_height + child.height,
                        _ => child.offset_y,
                    };

                    let dist = (target_offset - current_scroll_y).abs();
                    
                    if dist < min_distance {
                        min_distance = dist;
                        closest_offset = target_offset;
                    }
                }

                if config.strictness == SnapStrictness::Mandatory {
                    self.total_scroll_clamps_executed += 1;
                    return Some(closest_offset);
                } else if config.strictness == SnapStrictness::Proximity && min_distance < 150.0 {
                    // Only snap if currently idling VERY close to the threshold
                    self.total_scroll_clamps_executed += 1;
                    return Some(closest_offset);
                }
            }
        }
        None
    }

    /// AI-facing Scroll Spatial Limits mappings
    pub fn ai_scroll_snap_summary(&self, parent_id: u64) -> String {
        if let Some(config) = self.snap_containers.get(&parent_id) {
            let count = self.child_geometries.get(&parent_id).map_or(0, |c| c.len());
            format!("🧲 CSS Scroll Snap 1 (Node #{}): Strictness: {:?} | Axis: {:?} | Bound Children: {} | Global Clamps: {}", 
                parent_id, config.strictness, config.axis, count, self.total_scroll_clamps_executed)
        } else {
            format!("Node #{} executes free-form friction scrolling natively", parent_id)
        }
    }
}
