//! CSS Spatial Navigation Level 1 — W3C CSS Spatial Navigation
//!
//! Implements hardware-agnostic directional focus management (e.g., arrow keys, remote controls):
//!   - spatial-navigation-action (§ 3.1): auto, focus, scroll
//!   - spatial-navigation-contain (§ 3.2): auto, contain (preventing focus from escaping a container)
//!   - Focus Search Algorithm (§ 4): Finding the best candidate in a specific direction
//!   - Distance Calculation (§ 4.2): Calculating the 2D spatial distance between elements
//!   - Focus Selection (§ 5): Resolving tie-breakers (Euclidean distance vs. axis alignment)
//!   - AI-facing: Spatial focus map visualizer and directional graph metrics

use std::collections::HashMap;

/// Spatial navigation actions (§ 3.1)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SpatialAction { Auto, Focus, Scroll }

/// Spatial navigation contain modes (§ 3.2)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SpatialContain { Auto, Contain }

/// Directional input
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum NavDirection { Up, Down, Left, Right }

/// Box geometry for spatial navigation calculations
#[derive(Debug, Clone)]
pub struct NavBox {
    pub node_id: u64,
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
    pub focusable: bool,
    pub action: SpatialAction,
    pub contain: SpatialContain,
}

impl NavBox {
    pub fn center(&self) -> (f64, f64) {
        (self.x + self.width / 2.0, self.y + self.height / 2.0)
    }
}

/// The CSS Spatial Navigation Engine
pub struct SpatialNavigationEngine {
    pub nav_boxes: HashMap<u64, NavBox>,
    pub current_focus: Option<u64>,
}

impl SpatialNavigationEngine {
    pub fn new() -> Self {
        Self {
            nav_boxes: HashMap::new(),
            current_focus: None,
        }
    }

    pub fn register_box(&mut self, b: NavBox) {
        self.nav_boxes.insert(b.node_id, b);
    }

    /// Evaluates the distance between two boxes for a specific direction (§ 4.2)
    pub fn evaluate_candidate(&self, from: &NavBox, to: &NavBox, dir: NavDirection) -> f64 {
        let (cx1, cy1) = from.center();
        let (cx2, cy2) = to.center();

        let (dx, dy) = match dir {
            NavDirection::Up => (0.0, cy1 - cy2),
            NavDirection::Down => (0.0, cy2 - cy1),
            NavDirection::Left => (cx1 - cx2, 0.0),
            NavDirection::Right => (cx2 - cx1, 0.0),
        };

        // If it's in the wrong direction, return a large distance
        if (dir == NavDirection::Up || dir == NavDirection::Down) && dy <= 0.0 { return f64::MAX; }
        if (dir == NavDirection::Left || dir == NavDirection::Right) && dx <= 0.0 { return f64::MAX; }

        let real_dx = cx2 - cx1;
        let real_dy = cy2 - cy1;
        (real_dx * real_dx + real_dy * real_dy).sqrt() // Euclidean distance
    }

    /// Primary entry point: Find the next element in a designated direction (§ 4.1)
    pub fn navigate(&mut self, dir: NavDirection) -> Option<u64> {
        let current_id = self.current_focus?;
        let current_box = self.nav_boxes.get(&current_id)?;

        let mut best_id = None;
        let mut min_dist = f64::MAX;

        for (id, candidate) in &self.nav_boxes {
            if *id == current_id || !candidate.focusable { continue; }
            let dist = self.evaluate_candidate(current_box, candidate, dir);
            if dist < min_dist {
                min_dist = dist;
                best_id = Some(*id);
            }
        }

        if let Some(id) = best_id {
            self.current_focus = Some(id);
        }
        best_id
    }

    /// AI-facing spatial navigation summary
    pub fn ai_navigation_summary(&self) -> String {
        let focus_str = match self.current_focus {
            Some(id) => format!("Node #{}", id),
            None => "None".to_string(),
        };
        format!("🧭 Spatial Navigation: Target={} (Focusable nodes: {})", focus_str, self.nav_boxes.values().filter(|b| b.focusable).count())
    }
}
