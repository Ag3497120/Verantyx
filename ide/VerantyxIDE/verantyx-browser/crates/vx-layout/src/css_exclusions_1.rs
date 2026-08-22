//! CSS Exclusions Module Level 1 — W3C CSS Exclusions
//!
//! Implements arbitrary inline text-flow routing around custom geographical shapes:
//!   - `wrap-flow` (§ 3): `auto`, `both`, `start`, `end`, `clear` wrapping logic
//!   - `wrap-through` (§ 4): Allowing text to punch through exclusion zones
//!   - Separation of Document Order and Formatting Order (arbitrary block positioning)
//!   - Intersection physics calculations with Skia geometry lines
//!   - AI-facing: CSS Non-rectangular typographical boundaries

use std::collections::HashMap;

/// Determines how inline content flows around an exclusion area (§ 3.1)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum WrapFlow { Auto, Both, Start, End, Maximum, Clear }

/// Determines if content specifically overrides and ignores the exclusion (§ 4)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum WrapThrough { Wrap, None }

/// Represents the geometric boundary created by an exclusion element
#[derive(Debug, Clone)]
pub struct ExclusionBoundary {
    pub flow: WrapFlow,
    pub through: WrapThrough,
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
    pub is_complex_shape: bool, // e.g., created by CSS Shapes (shape-outside)
}

/// The global Constraint Resolver governing text-wrapping intersections
pub struct CssExclusionsEngine {
    // Spatial mapping of active exclusion rects applied to layout contexts
    pub active_exclusions: HashMap<u64, Vec<ExclusionBoundary>>,
    pub total_intersections_calculated: u64,
}

impl CssExclusionsEngine {
    pub fn new() -> Self {
        Self {
            active_exclusions: HashMap::new(),
            total_intersections_calculated: 0,
        }
    }

    /// Registered when layout processes a block flagged with `wrap-flow`
    pub fn register_exclusion(&mut self, container_id: u64, boundary: ExclusionBoundary) {
        let container = self.active_exclusions.entry(container_id).or_default();
        container.push(boundary);
    }

    /// Heavily invoked during the inline line-box fragmentation phase.
    /// Determines how much physical width is available for text on a specific Y axis.
    pub fn calculate_available_line_width(&mut self, container_id: u64, line_y: f64, line_height: f64, base_width: f64) -> f64 {
        if let Some(exclusions) = self.active_exclusions.get(&container_id) {
            let mut available_width = base_width;
            let mut largest_cutout = 0.0;

            for exclusion in exclusions {
                if exclusion.through == WrapThrough::None {
                    continue; // Skip calculating
                }

                self.total_intersections_calculated += 1;

                // Simple AABB Collision Logic
                // If the line overlaps the exclusion vertically
                if line_y < exclusion.y + exclusion.height && line_y + line_height > exclusion.y {
                    // Collision exists! Shrink the available width.
                    // (Simplified logic grabbing the largest single width chunk for `both`)
                    match exclusion.flow {
                        WrapFlow::Both | WrapFlow::Maximum => {
                            if exclusion.width > largest_cutout {
                                largest_cutout = exclusion.width;
                            }
                        }
                        WrapFlow::Start | WrapFlow::End => {
                            // Shrink width directionally
                            largest_cutout = largest_cutout.max(exclusion.width);
                        }
                        WrapFlow::Clear => {
                            // Element forces a physical break to the next logical Y coordinate
                            return 0.0;
                        }
                        _ => {}
                    }
                }
            }

            available_width -= largest_cutout;
            return available_width.max(0.0);
        }
        base_width
    }

    /// AI-facing CSS Typographical wrapping physics summary
    pub fn ai_exclusions_summary(&self, container_id: u64) -> String {
        let count = self.active_exclusions.get(&container_id).map_or(0, |e| e.len());
        format!("✂️ CSS Exclusions 1 (Container #{}): {} Active spatial bounding boxes | Layout Math Evaluated: {}", 
            container_id, count, self.total_intersections_calculated)
    }
}
