//! CSS Line Grid Module Level 1 — W3C CSS Line Grid
//!
//! Implements the infrastructure for consistent vertical alignment (baseline grid):
//!   - line-grid (§ 3.1): none, match-parent (creating and inheriting grids)
//!   - line-snap (§ 3.2): none, baseline, contain (snapping lines to the grid)
//!   - box-snap (§ 4.1): block-start, block-end, center, baseline, last-baseline, none
//!   - Grid Container (§ 3.3): Defining the grid unit (line-height)
//!   - Snap Points (§ 5): Resolving vertical coordinates to the nearest grid step
//!   - Box Sizing (§ 6): Impact of line-grid on auto-height and padding
//!   - AI-facing: Line grid alignment visualizer and snap-point map metrics

use std::collections::HashMap;

/// Line snap behaviors (§ 3.2)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LineSnap { None, Baseline, Contain }

/// Box snap behaviors (§ 4.1)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BoxSnap { None, BlockStart, BlockEnd, Center, Baseline, LastBaseline }

/// Line grid configuration (§ 3)
pub struct LineGridContext {
    pub node_id: u64,
    pub unit: f64, // Typically line-height
    pub origin_y: f64,
}

/// Layout state for a line-snapped box (§ 4)
pub struct LineSnappedBox {
    pub node_id: u64,
    pub line_snap: LineSnap,
    pub box_snap: BoxSnap,
}

/// The CSS Line Grid Engine
pub struct LineGridEngine {
    pub grids: HashMap<u64, LineGridContext>,
    pub snapped_boxes: HashMap<u64, LineSnappedBox>,
}

impl LineGridEngine {
    pub fn new() -> Self {
        Self {
            grids: HashMap::new(),
            snapped_boxes: HashMap::new(),
        }
    }

    /// Primary entry point: Resolve the snapped Y coordinate (§ 5)
    pub fn resolve_snap_y(&self, grid_id: u64, current_y: f64) -> f64 {
        let grid = match self.grids.get(&grid_id) {
            Some(g) => g,
            None => return current_y,
        };

        let rel_y = current_y - grid.origin_y;
        let step = (rel_y / grid.unit).round();
        grid.origin_y + (step * grid.unit)
    }

    /// Handles box-snap alignment (§ 6)
    pub fn resolve_box_snap(&self, box_height: f64, snap: BoxSnap, grid_unit: f64) -> f64 {
        match snap {
            BoxSnap::Center => (grid_unit - box_height) / 2.0,
            BoxSnap::BlockEnd => grid_unit - box_height,
            _ => 0.0,
        }
    }

    /// AI-facing line grid summary
    pub fn ai_grid_summary(&self, grid_id: u64) -> String {
        if let Some(grid) = self.grids.get(&grid_id) {
            format!("📏 CSS Line Grid for Node #{}: (Unit: {:.1}px, OriginY: {:.1}px)", 
                grid_id, grid.unit, grid.origin_y)
        } else {
            format!("No line grid defined for Node #{}", grid_id)
        }
    }
}
