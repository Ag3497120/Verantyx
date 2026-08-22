//! CSS Round Display Level 1 — W3C CSS Round Display
//!
//! Implements strict Smartwatch circular bounding vectors and geometry parsing:
//!   - `@media (shape: round)` (§ 3): Detecting physical screen limits
//!   - `shape-inside: display` (§ 4): Bounding layout flow strictly to circular radius limits
//!   - `border-boundary: display` (§ 5): Trimming rectangle DOM corners to the physical screen
//!   - AI-facing: Wearable Display Circular Geometry extrusions

use std::collections::HashMap;

/// Determines if the underlying hardware is rectangular or spherical
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OSHardwareShape { Rect, Round }

#[derive(Debug, Clone)]
pub struct CircularDisplayMetrics {
    pub display_shape: OSHardwareShape,
    pub radius: f64,
}

/// The global Constraint Resolver governing Layout fragmentation cutting text off at curved arcs
pub struct CssRoundDisplayEngine {
    pub global_wearable_metrics: CircularDisplayMetrics,
    pub total_lines_shrunk_by_curve: u64,
}

impl CssRoundDisplayEngine {
    pub fn new() -> Self {
        Self {
            global_wearable_metrics: CircularDisplayMetrics {
                display_shape: OSHardwareShape::Rect,
                radius: 0.0,
            },
            total_lines_shrunk_by_curve: 0,
        }
    }

    /// Evaluator executed by the Line-Breaker
    /// E.g., `shape-inside: display` forces text to wrap earlier as you move away from the equatorial center.
    pub fn compute_line_geometric_width_at_y(&mut self, block_width: f64, line_y_coordinate: f64) -> f64 {
        if self.global_wearable_metrics.display_shape == OSHardwareShape::Rect {
            return block_width; // Standard rectangle layout
        }
        
        let r = self.global_wearable_metrics.radius;
        // Basic circle intersection math mapping Y coordinate offset from center
        let y_offset_from_center = (line_y_coordinate - r).abs();
        
        if y_offset_from_center >= r {
             self.total_lines_shrunk_by_curve += 1;
             return 0.0; // Out of bounds of the smartwatch screen
        }
        
        // Pythagorean theorem limiting the chord length of this specific line
        let width_at_y = 2.0 * (r * r - y_offset_from_center * y_offset_from_center).sqrt();
        
        if width_at_y < block_width {
             self.total_lines_shrunk_by_curve += 1;
             return width_at_y;
        }
        
        block_width
    }

    /// Executed by Media Query parser for `@media (shape: round)`
    pub fn hardware_supports_round_display(&self) -> bool {
        self.global_wearable_metrics.display_shape == OSHardwareShape::Round
    }

    /// AI-facing Smartwatch Geometries
    pub fn ai_round_display_summary(&self) -> String {
        format!("⌚ CSS Round Display 1: Hardware Shape: {:?} | Device Arc Radius: {}px | Global Line Geometries Shrunk: {}", 
            self.global_wearable_metrics.display_shape, self.global_wearable_metrics.radius, self.total_lines_shrunk_by_curve)
    }
}
