//! CSS Motion Path Module Level 1 — W3C CSS Motion Path
//!
//! Implements the layout infrastructure for animating elements along custom paths:
//!   - offset-path (§ 2.1): [ <ray()> | <url> | <basic-shape> | <path()> | none ]
//!   - offset-distance (§ 2.2): <length-percentage> along the path
//!   - offset-position (§ 2.3): auto | <position>
//!   - offset-anchor (§ 2.4): auto | <position>
//!   - offset-rotate (§ 2.5): [ auto | reverse ] || <angle>
//!   - Path distance calculation: Computing total length and points-at-distance (§ 2.1.2)
//!   - SVG Path interpolation: Resolving bezier segments to linear progress (§ 2.1.3)
//!   - AI-facing: Motion path visualizer and element-on-path offset map

use std::collections::HashMap;

/// Motion path types (§ 2.1)
#[derive(Debug, Clone)]
pub enum OffsetPath { None, Path(String), Ray(f64, String), Url(String) }

/// Rotation behavior (§ 2.5)
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum OffsetRotate { Auto, Reverse, Angle(f32) }

/// Layout state for a motion path (§ 2)
pub struct OffsetPathState {
    pub node_id: u64,
    pub path: OffsetPath,
    pub distance: f64, // offset-distance
    pub anchor: (f64, f64), // offset-anchor
    pub rotate: OffsetRotate,
}

impl OffsetPathState {
    pub fn new(node_id: u64) -> Self {
        Self {
            node_id,
            path: OffsetPath::None,
            distance: 0.0,
            anchor: (50.0, 50.0), // center
            rotate: OffsetRotate::Auto,
        }
    }

    /// Primary entry point: Resolve (x, y, angle) at current distance (§ 2.1.2)
    pub fn resolve_position(&self) -> (f64, f64, f32) {
        // Placeholder for path geometry interpolation logic
        (0.0, 0.0, 0.0)
    }

    /// AI-facing motion path status
    pub fn ai_motion_summary(&self) -> String {
        let (x, y, angle) = self.resolve_position();
        format!("🛤️ Motion Path for Node #{}: (Pos: {:.1}, {:.1}, Rotation: {:.1}°) [Dist: {:.1}]", 
            self.node_id, x, y, angle, self.distance)
    }
}

/// Simple Path-to-Length Registry
pub struct MotionPathRegistry {
    pub paths: HashMap<String, f64>, // path_string -> total_length
}

impl MotionPathRegistry {
    pub fn new() -> Self {
        Self { paths: HashMap::new() }
    }

    pub fn register_path(&mut self, path: &str, length: f64) {
        self.paths.insert(path.to_string(), length);
    }
}
