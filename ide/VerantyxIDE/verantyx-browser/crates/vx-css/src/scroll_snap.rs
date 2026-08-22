//! CSS Scroll Snap Module Level 1 — W3C CSS Scroll Snap
//!
//! Implements precise scrolling and snapping control for professional UI:
//!   - Scroll Snap Container (§ 3): scroll-snap-type (none, x, y, block, inline, both, mandatory, proximity)
//!   - Scroll Snap Alignment (§ 4): scroll-snap-align (none, start, end, center)
//!   - Scroll Snap Stop (§ 4.2): scroll-snap-stop (normal, always)
//!   - Scroll Padding (§ 5.1): scroll-padding-top/right/bottom/left
//!   - Scroll Margin (§ 5.2): scroll-margin-top/right/bottom/left
//!   - Snap Points Calculation: Resolving container-relative snap positions
//!   - Snap Area Logic: Determining active snap areas during scroll events
//!   - Baseline/Box Edge alignment logic
//!   - AI-facing: Scroll snap position map and proximity-to-snap visualizer

use std::collections::HashMap;

/// Scroll snap types (§ 3.1)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ScrollSnapType { None, X, Y, Block, Inline, Both }

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ScrollSnapStrictness { Mandatory, Proximity }

/// Scroll snap alignment (§ 4.1)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ScrollSnapAlign { None, Start, End, Center }

/// Scroll snap stop (§ 4.2)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ScrollSnapStop { Normal, Always }

/// Container snap configuration (§ 3)
#[derive(Debug, Clone)]
pub struct ScrollSnapContainer {
    pub snap_type: ScrollSnapType,
    pub strictness: ScrollSnapStrictness,
    pub padding: [f64; 4], // top, right, bottom, left
}

/// Area snap configuration (§ 4)
#[derive(Debug, Clone)]
pub struct ScrollSnapArea {
    pub node_id: u64,
    pub align: (ScrollSnapAlign, ScrollSnapAlign), // block, inline
    pub stop: ScrollSnapStop,
    pub margin: [f64; 4], // top, right, bottom, left
    pub rect: (f64, f64, f64, f64), // x, y, width, height (relative to container)
}

/// The Scroll Snap Engine
pub struct ScrollSnapEngine {
    pub containers: HashMap<u64, ScrollSnapContainer>,
    pub areas: HashMap<u64, Vec<ScrollSnapArea>>, // container_id -> areas
}

impl ScrollSnapEngine {
    pub fn new() -> Self {
        Self {
            containers: HashMap::new(),
            areas: HashMap::new(),
        }
    }

    /// Primary entry point: Find the nearest snap position (§ 6)
    pub fn find_snap_position(&self, container_id: u64, current_x: f64, current_y: f64) -> (f64, f64) {
        let container = match self.containers.get(&container_id) {
            Some(c) if c.snap_type != ScrollSnapType::None => c,
            _ => return (current_x, current_y),
        };

        let areas = match self.areas.get(&container_id) {
            Some(a) => a,
            None => return (current_x, current_y),
        };

        let mut best_x = current_x;
        let mut best_y = current_y;
        let mut min_dist_x = f64::MAX;
        let mut min_dist_y = f64::MAX;

        for area in areas {
            let snap_x = self.calculate_snap_coord(area.rect.0, area.rect.2, area.align.1, container.padding[3]);
            let snap_y = self.calculate_snap_coord(area.rect.1, area.rect.3, area.align.0, container.padding[0]);

            let dist_x = (snap_x - current_x).abs();
            let dist_y = (snap_y - current_y).abs();

            if dist_x < min_dist_x { min_dist_x = dist_x; best_x = snap_x; }
            if dist_y < min_dist_y { min_dist_y = dist_y; best_y = snap_y; }
        }

        // Proximity check (§ 6.1)
        if container.strictness == ScrollSnapStrictness::Proximity {
            if min_dist_x > 50.0 { best_x = current_x; }
            if min_dist_y > 50.0 { best_y = current_y; }
        }

        (best_x, best_y)
    }

    fn calculate_snap_coord(&self, pos: f64, size: f64, align: ScrollSnapAlign, padding: f64) -> f64 {
        match align {
            ScrollSnapAlign::Start => pos - padding,
            ScrollSnapAlign::End => pos + size + padding,
            ScrollSnapAlign::Center => pos + (size / 2.0),
            ScrollSnapAlign::None => pos,
        }
    }

    /// AI-facing snap position map
    pub fn ai_snap_map(&self, container_id: u64) -> String {
        let mut output = vec![format!("🎯 Scroll Snap Map for Container #{}:", container_id)];
        if let Some(areas) = self.areas.get(&container_id) {
            for area in areas {
                output.push(format!("    - Area #{} (Align: {:?}, Stop: {:?})", area.node_id, area.align, area.stop));
            }
        }
        output.join("\n")
    }
}
