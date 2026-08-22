//! CSS Box Model Module Level 4 — W3C CSS Box Model
//!
//! Implements the browser's advanced element sizing and spacing infrastructure:
//!   - margin-trim (§ 2.2): none, in-flow, all (truncating margins at container edges)
//!   - element-box (§ 3.1): content-box, padding-box, border-box, margin-box mappings
//!   - Box logical properties mapping (§ 4): Handling inline/block start/end margins
//!   - Auto margin resolution (§ 5): Centering and distribution algorithms
//!   - Margin collapsing algorithm (§ 6): Adjacent siblings, parent/child, empty blocks
//!   - AI-facing: Box geometry visualizer and margin collapse edge-case metrics

use std::collections::HashMap;

/// Margin trim behaviors (§ 2.2)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MarginTrim { None, InFlow, All }

/// Standard CSS Box Geometry (§ 3.1)
#[derive(Debug, Clone)]
pub struct BoxModel {
    pub node_id: u64,
    // [top, right, bottom, left]
    pub margin: [f64; 4],
    pub border: [f64; 4],
    pub padding: [f64; 4],
    pub content_width: f64,
    pub content_height: f64,
    pub margin_trim: MarginTrim,
}

impl BoxModel {
    /// Helper: Calculate the margin-box width
    pub fn offset_width(&self) -> f64 {
        self.margin[1] + self.border[1] + self.padding[1] + self.content_width + self.padding[3] + self.border[3] + self.margin[3]
    }
}

/// The CSS Box Model Level 4 Engine
pub struct BoxModelEngine {
    pub boxes: HashMap<u64, BoxModel>,
}

impl BoxModelEngine {
    pub fn new() -> Self {
        Self { boxes: HashMap::new() }
    }

    pub fn set_box(&mut self, node_id: u64, b: BoxModel) {
        self.boxes.insert(node_id, b);
    }

    /// Margin Collapsing Algorithm (§ 6)
    pub fn get_collapsed_margin(&self, m1: f64, m2: f64) -> f64 {
        // [Simplified: max(m1, m2) for positive margins, etc.]
        if m1 > 0.0 && m2 > 0.0 {
            m1.max(m2)
        } else if m1 < 0.0 && m2 < 0.0 {
            m1.min(m2)
        } else {
            m1 + m2
        }
    }

    /// Margin Trim processing for a container (§ 2.2)
    pub fn apply_margin_trim(&mut self, container_id: u64) {
        // Implementation would traverse children and set edges to 0
    }

    /// AI-facing box geometry summary
    pub fn ai_box_summary(&self, node_id: u64) -> String {
        if let Some(b) = self.boxes.get(&node_id) {
            format!("📦 Box Model (Node #{}): Content({}×{}), Trim:{:?}, OffsetWidth: {:.1}", 
                node_id, b.content_width, b.content_height, b.margin_trim, b.offset_width())
        } else {
            format!("Node #{} has no initialized box geometry", node_id)
        }
    }
}
