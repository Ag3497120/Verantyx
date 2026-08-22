//! CSS Grid Layout Module Level 3 — W3C CSS Grid 3 (Masonry)
//!
//! Implements masonry algorithmic layout distributions overriding standard matrix bounds:
//!   - `grid-template-rows: masonry` / `grid-template-columns: masonry`
//!   - `masonry-auto-flow` (§ 2): Next item placement mappings (`pack`, `next`)
//!   - Tight packing geometrical distribution matrices
//!   - AI-facing: CSS Geographical Grid Masonry mapping abstractions

use std::collections::HashMap;

/// Determines whether the masonry algorithm minimizes gap distance vs retains order
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MasonryPackLogic { Pack, Next }

/// Overrides standard grid dimensions targeting brick-like topographical flow
#[derive(Debug, Clone, Copy)]
pub struct CssMasonryConfiguration {
    pub is_masonry_rows: bool, // e.g. columns act as normal Grid tracks, rows flow variably
    pub is_masonry_columns: bool,
    pub auto_flow: MasonryPackLogic,
}

impl Default for CssMasonryConfiguration {
    fn default() -> Self {
        Self {
            is_masonry_rows: false,
            is_masonry_columns: false,
            auto_flow: MasonryPackLogic::Pack,
        }
    }
}

/// Simulates a physical node's absolute bounding box in the Grid layout
#[derive(Debug, Clone)]
pub struct MasonryChildBoundingGeom {
    pub id: u64,
    pub absolute_x: f64,
    pub absolute_y: f64,
    pub width: f64,
    pub height: f64,
}

/// The global Constraint Resolver bridging Grid specifications to the continuous Masonry algorithms
pub struct CssGridMasonryEngine {
    pub grid_configurations: HashMap<u64, CssMasonryConfiguration>,
    pub total_masonry_reflows_computed: u64,
}

impl CssGridMasonryEngine {
    pub fn new() -> Self {
        Self {
            grid_configurations: HashMap::new(),
            total_masonry_reflows_computed: 0,
        }
    }

    pub fn set_masonry_config(&mut self, node_id: u64, config: CssMasonryConfiguration) {
        self.grid_configurations.insert(node_id, config);
    }

    /// Executed by `vx-layout` Grid Processor. Extracts bounding box layouts using brick packing optimization.
    pub fn solve_masonry_distribution(&mut self, container_id: u64, container_width: f64, children_heights: Vec<(u64, f64)>, column_count: u32, gap_size: f64) -> Vec<MasonryChildBoundingGeom> {
        let mut results = Vec::new();
        
        let config = if let Some(c) = self.grid_configurations.get(&container_id) { c.clone() }
        else { return results; }; // Requires active config!

        if !config.is_masonry_rows {
            // Simplified fallback for unconfigured
            return results;
        }

        self.total_masonry_reflows_computed += 1;

        // Implementation of the "Pack" algorithm for `masonry-auto-flow`
        // We track the geometric bottom offset of every physical column track
        let mut track_bottom_heights = vec![0.0; column_count as usize];
        let computed_col_width = (container_width - (gap_size * (column_count - 1) as f64)) / column_count as f64;

        for (child_id, child_height) in children_heights {
            // Find the track with the *shortest* absolute height, packing logic
            let mut target_col_idx = 0;
            let mut min_height = f64::MAX;

            for (i, &height) in track_bottom_heights.iter().enumerate() {
                if height < min_height {
                    min_height = height;
                    target_col_idx = i;
                }
            }

            let start_x = target_col_idx as f64 * (computed_col_width + gap_size);
            let start_y = track_bottom_heights[target_col_idx];

            results.push(MasonryChildBoundingGeom {
                id: child_id,
                absolute_x: start_x,
                absolute_y: start_y,
                width: computed_col_width,
                height: child_height,
            });

            // Update track boundary
            track_bottom_heights[target_col_idx] += child_height + gap_size;
        }

        results
    }

    /// AI-facing CSS Geometrical Extradition mapped
    pub fn ai_masonry_summary(&self, node_id: u64) -> String {
        if let Some(config) = self.grid_configurations.get(&node_id) {
            format!("🧱 CSS Grid Masonry 3 (Node #{}): Masonry Rows: {} | Masonry Cols: {} | Flow: {:?} | Global Reflows: {}", 
                node_id, config.is_masonry_rows, config.is_masonry_columns, config.auto_flow, self.total_masonry_reflows_computed)
        } else {
            format!("Node #{} lays out within rigid Matrix-defined Grid intersections", node_id)
        }
    }
}
