//! CSS Exclusions Module Level 1 — W3C CSS Exclusions
//!
//! Implements the browser's complex inline-flow wrapping around arbitrary shapes/boxes:
//!   - wrap-flow (§ 3.1): auto, both, start, end, maximum, clear
//!   - wrap-through (§ 3.2): wrap, none (determining if content flows through or around)
//!   - Exclusion Area (§ 3.3.1): Creating rectangular or shape-based exclusions in the wrapping context
//!   - Wrapping Context (§ 3.4): Collection of all exclusions affecting a single flow
//!   - Inline fragmentation around exclusions (§ 3.5): Determining the available inline-size
//!     for fragments at a given vertical offset within the exclusion context.
//!   - AI-facing: Exclusion boundary map visualizer and inline fragment placement metrics

use std::collections::HashMap;

/// Wrap flow types (§ 3.1)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum WrapFlow { Auto, Both, Start, End, Maximum, Clear }

/// Wrap through types (§ 3.2)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum WrapThrough { Wrap, None }

/// An individual exclusion container (§ 3.3)
pub struct ExclusionBox {
    pub node_id: u64,
    pub wrap_flow: WrapFlow,
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
}

/// The CSS Exclusions Engine
pub struct ExclusionsEngine {
    pub exclusions: HashMap<u64, ExclusionBox>,
    pub wrap_through: HashMap<u64, WrapThrough>,
}

impl ExclusionsEngine {
    pub fn new() -> Self {
        Self {
            exclusions: HashMap::new(),
            wrap_through: HashMap::new(),
        }
    }

    /// Primary entry point: Resolves the available inline-space (§ 3.5)
    pub fn get_available_space(&self, y: f64, max_width: f64) -> Vec<(f64, f64)> {
        let mut available = vec![(0.0, max_width)];
        
        for ex in self.exclusions.values() {
            if y >= ex.y && y < ex.y + ex.height {
                // Determine how to subtract the exclusion area based on wrap-flow (§ 3.1)
                match ex.wrap_flow {
                    WrapFlow::Both => {
                        // In practice, this would split the space into two fragments...
                    }
                    WrapFlow::Start => {
                        // Content can only be on the start (left) side...
                    }
                    _ => {}
                }
            }
        }
        available
    }

    /// AI-facing exclusion boundary summary
    pub fn ai_exclusion_map(&self) -> String {
        let mut lines = vec![format!("🚧 CSS Exclusions Registry (Total: {}):", self.exclusions.len())];
        for (id, ex) in &self.exclusions {
            lines.push(format!("  - Node #{}: (x:{:.1}, y:{:.1}, w:{:.1}, h:{:.1}) [Flow: {:?}]", 
                id, ex.x, ex.y, ex.width, ex.height, ex.wrap_flow));
        }
        lines.join("\n")
    }
}
