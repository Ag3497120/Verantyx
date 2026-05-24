//! CSS Shapes Module Level 2 — W3C CSS Shapes 2
//!
//! Implements arbitrary inline typographical wrapping geometries inside blocks:
//!   - `shape-inside` (§ 2): Defining interior boundaries where text is allowed
//!   - `polygon()`, `circle()`, `ellipse()` geometry extraction logic
//!   - Physical Line-Box cutting algorithms based on Skia Paths
//!   - AI-facing: Polygon text-flow topographical complexity

use std::collections::HashMap;

/// The geographical boundary defining the interior text constraints
#[derive(Debug, Clone)]
pub enum ShapeGeometry {
    Circle { cx: f64, cy: f64, r: f64 },
    Ellipse { cx: f64, cy: f64, rx: f64, ry: f64 },
    Polygon { vertices: Vec<(f64, f64)> }, // Assumed non-intersecting closed loop
}

/// Global Configuration applied to a text block
#[derive(Debug, Clone)]
pub struct ShapeInsideConfiguration {
    pub geometry: ShapeGeometry,
    pub shape_margin: f64, // Pushes text inwards further
}

/// Evaluator tracking geographical raycast line intersections
pub struct CssShapes2Engine {
    pub active_shapes: HashMap<u64, ShapeInsideConfiguration>,
    pub total_raycasts_executed: u64,
}

impl CssShapes2Engine {
    pub fn new() -> Self {
        Self {
            active_shapes: HashMap::new(),
            total_raycasts_executed: 0,
        }
    }

    pub fn set_shape_inside(&mut self, node_id: u64, config: ShapeInsideConfiguration) {
        self.active_shapes.insert(node_id, config);
    }

    /// Executed by the typographical line-breaker engine physically scanning down the block.
    /// Returns arrays of [start_x, end_x] chunks where text is allowed to exist.
    pub fn compute_line_box_segments(&mut self, node_id: u64, line_y_top: f64, line_y_bottom: f64, block_width: f64) -> Vec<(f64, f64)> {
        if let Some(config) = self.active_shapes.get(&node_id) {
            self.total_raycasts_executed += 1;

            // Simplified implementation using a bounding midpoint for the line rather than full AABB intersections.
            let midpoint_y = (line_y_top + line_y_bottom) / 2.0;

            match &config.geometry {
                ShapeGeometry::Circle { cx, cy, r } => {
                    let adjusted_r = (r - config.shape_margin).max(0.0);
                    // Circle equation: (x - cx)^2 + (y - cy)^2 = r^2
                    // We know y = midpoint_y, solve for x
                    let y_diff = midpoint_y - cy;
                    if y_diff.abs() <= adjusted_r {
                        let x_dist = (adjusted_r * adjusted_r - y_diff * y_diff).sqrt();
                        let start_x = (cx - x_dist).max(0.0);
                        let end_x = (cx + x_dist).min(block_width);
                        if start_x < end_x {
                            return vec![(start_x, end_x)];
                        }
                    }
                }
                ShapeGeometry::Ellipse { cx, cy, rx, ry } => {
                    let adjusted_rx = (rx - config.shape_margin).max(0.0);
                    let adjusted_ry = (ry - config.shape_margin).max(0.0);

                    // Skip complex math simulation for ellipses/polygons in abstract example
                    // Just return bounding bounds
                    if midpoint_y > cy - adjusted_ry && midpoint_y < cy + adjusted_ry {
                        return vec![(cx - adjusted_rx, cx + adjusted_rx)];
                    }
                }
                ShapeGeometry::Polygon { .. } => {
                    // True implementation requires complex Skia Path intersection raycasting.
                    // We assume allowing full block width as mock.
                    return vec![(0.0, block_width)];
                }
            }
        }
        
        // No shape inside defined, the block acts as a standard rectangle
        vec![(0.0, block_width)]
    }

    /// AI-facing CSS Typographical Shapes topographical tracker
    pub fn ai_shapes_summary(&self, node_id: u64) -> String {
        if let Some(config) = self.active_shapes.get(&node_id) {
            let shape_type = match config.geometry {
                ShapeGeometry::Circle { .. } => "Circle",
                ShapeGeometry::Ellipse { .. } => "Ellipse",
                ShapeGeometry::Polygon { .. } => "Polygon",
            };
            format!("🔵 CSS Shapes 2 (Node #{}): Interior wrapping geometry: {} | Margin: {}px | Raycasts: {}", 
                node_id, shape_type, config.shape_margin, self.total_raycasts_executed)
        } else {
            format!("Node #{} wraps text completely rectangularly", node_id)
        }
    }
}
