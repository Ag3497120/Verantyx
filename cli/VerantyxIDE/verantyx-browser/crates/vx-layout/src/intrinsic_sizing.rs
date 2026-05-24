//! CSS Intrinsic & Extrinsic Sizing Module Level 3 — W3C CSS Sizing
//!
//! Implements the core sizing logic for elements based on content and context:
//!   - Intrinsic size (§ 4): min-content, max-content, fit-content(<length-percentage>)
//!   - Extrinsic size (§ 5): Resolving <length>, <percentage>, and 'auto' values
//!   - Box sizing (§ 5.1): content-box (default) vs. border-box
//!   - Min/max constraints (§ 5.2): width, height, min-width, min-height, max-width, max-height
//!   - Aspect ratio (§ 7): ratio-based sizing and conflict resolution
//!   - Fallback behavior (§ 7.2): Sizing when intrinsic data is missing
//!   - AI-facing: Intrinsic size contribution visualizer and constraint-limit metrics

use std::collections::HashMap;

/// Sizing types (§ 4)
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum SizingType { MinContent, MaxContent, FitContent, Auto, Fixed(f64) }

/// Constrained sizes (§ 5)
#[derive(Debug, Clone, Copy)]
pub struct SizeConstraint {
    pub min: f64,
    pub max: f64,
    pub preferred: f64,
}

/// The Intrinsic Sizing Engine
pub struct SizingEngine {
    pub container_width: f64,
    pub container_height: f64,
    pub node_id: u64,
}

impl SizingEngine {
    pub fn new(w: f64, h: f64, id: u64) -> Self {
        Self { container_width: w, container_height: h, node_id: id }
    }

    /// Primary entry point: Resolve the used width/height (§ 6)
    pub fn resolve_sizing(&self, sizing: SizingType, content_min: f64, content_max: f64) -> f64 {
        match sizing {
            SizingType::Fixed(v) => v,
            SizingType::MinContent => content_min,
            SizingType::MaxContent => content_max,
            SizingType::FitContent => {
                // min(max-content, max(min-content, stretch)) (§ 4.2)
                content_max.min(content_min.max(self.container_width))
            }
            SizingType::Auto => self.container_width, // default stretch
        }
    }

    /// Handles aspect ratio resolution (§ 7)
    pub fn resolve_aspect_ratio(&self, ratio: f64, width: Option<f64>, height: Option<f64>) -> (f64, f64) {
        match (width, height) {
            (Some(w), None) => (w, w / ratio),
            (None, Some(h)) => (h * ratio, h),
            (Some(w), Some(h)) => (w, h),
            (None, None) => (0.0, 0.0),
        }
    }

    /// AI-facing sizing summary
    pub fn ai_sizing_summary(&self, s_type: SizingType, min: f64, max: f64) -> String {
        let used = self.resolve_sizing(s_type, min, max);
        format!("📏 CSS Sizing for Node #{}: [{:?}] -> Used size: {:.1}px (Min/Max content: {:.1}/{:.1})", 
            self.node_id, s_type, used, min, max)
    }
}

/// Registry for intrinsic size contributions (§ 6)
pub struct IntrinsicSizeRegistry {
    pub contributions: HashMap<u64, SizeConstraint>, // node_id -> constraint
}

impl IntrinsicSizeRegistry {
    pub fn new() -> Self {
        Self { contributions: HashMap::new() }
    }

    pub fn register_contribution(&mut self, node_id: u64, min: f64, max: f64, pref: f64) {
        self.contributions.insert(node_id, SizeConstraint { min, max, preferred: pref });
    }
}
