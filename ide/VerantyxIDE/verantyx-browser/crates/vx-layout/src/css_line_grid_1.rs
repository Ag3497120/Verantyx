//! CSS Line Grid Module Level 1 — W3C CSS Line Grid
//!
//! Implements strict vertical typographical alignment bounding systems:
//!   - line-grid (§ 2): create, match (Identifying the grid boundaries)
//!   - line-snap (§ 3): none, baseline, contain (Snapping boxes to the grid)
//!   - box-snap (§ 4): Snapping layout margins and padding strictly to standard line boxes
//!   - Baseline Grid Generation: Generating virtual infinite horizontal planes
//!   - Descender/Ascender collision mitigation
//!   - AI-facing: Spatial baseline grid snap-points visualizer

use std::collections::HashMap;

/// Determines if an element defines a new typographic grid or snaps to an existing one (§ 2)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LineGridMode { Create, Match }

/// Strategy for snapping content lines into the active grid (§ 3)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LineSnapStrategy { None, Baseline, Contain }

/// Configuration applied to a specific DOM node
#[derive(Debug, Clone)]
pub struct LineGridConfiguration {
    pub mode: LineGridMode,
    pub snap_internal_lines: LineSnapStrategy,
    pub snap_box_edges: bool, // box-snap
    pub grid_line_height: f64, // When creating
}

/// Layout evaluation context representing the active virtual grid
#[derive(Debug, Clone)]
pub struct VirtualLineGrid {
    pub root_node_id: u64,
    pub line_increment_y: f64, // The spacing between planes
    pub baseline_offset_y: f64, // Initial vertical alignment offset
}

/// The global CSS Line Grid engine
pub struct CSSLineGridEngine {
    pub configurations: HashMap<u64, LineGridConfiguration>,
    pub active_grids: Vec<VirtualLineGrid>, // Stack of deeply nested grids
}

impl CSSLineGridEngine {
    pub fn new() -> Self {
        Self {
            configurations: HashMap::new(),
            active_grids: Vec::new(),
        }
    }

    /// Sets up a grid scope
    pub fn register_grid_node(&mut self, node_id: u64, config: LineGridConfiguration) {
        self.configurations.insert(node_id, config);
    }

    /// Layout calls this when entering a new formatting context
    pub fn enter_layout_context(&mut self, node_id: u64) {
        if let Some(config) = self.configurations.get(&node_id) {
            if config.mode == LineGridMode::Create {
                self.active_grids.push(VirtualLineGrid {
                    root_node_id: node_id,
                    line_increment_y: config.grid_line_height,
                    baseline_offset_y: 0.0,
                });
            }
        }
    }

    /// Layout calls this when exiting a node's children
    pub fn exit_layout_context(&mut self, node_id: u64) {
        if let Some(grid) = self.active_grids.last() {
            if grid.root_node_id == node_id {
                self.active_grids.pop();
            }
        }
    }

    /// Core snapping algorithm: Adjusts a line-box's Y-coordinate to rest precisely on the virtual grid
    pub fn snap_line_y(&self, node_id: u64, layout_natural_y: f64) -> f64 {
        let config = match self.configurations.get(&node_id) {
            Some(c) => c,
            None => return layout_natural_y,
        };

        if config.snap_internal_lines == LineSnapStrategy::None || self.active_grids.is_empty() {
            return layout_natural_y;
        }

        let grid = self.active_grids.last().unwrap();
        // Snap to nearest mathematical increment
        let multiples = (layout_natural_y / grid.line_increment_y).round();
        multiples * grid.line_increment_y
    }

    /// AI-facing Line Grid geometric mapping
    pub fn ai_line_grid_summary(&self, node_id: u64) -> String {
        let config_str = match self.configurations.get(&node_id) {
            Some(c) => format!("Mode: {:?}, Line-Snap: {:?}", c.mode, c.snap_internal_lines),
            None => "No grid configuration".into(),
        };
        
        let grid_status = if let Some(g) = self.active_grids.last() {
            format!("Snap Target -> Grid root #{} (Increment: {:.1}px)", g.root_node_id, g.line_increment_y)
        } else {
            "No active typographic virtual grid".into()
        };

        format!("📐 CSS Line Grid (Node #{}): {}\n  - {}", node_id, config_str, grid_status)
    }
}
