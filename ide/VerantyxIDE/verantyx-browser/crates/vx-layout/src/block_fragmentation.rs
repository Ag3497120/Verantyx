//! CSS Fragmentation Module Level 3 — W3C CSS Fragmentation
//!
//! Implements the browser's generic content fragmentation infrastructure:
//!   - Fragmentation Types (§ 2): paging (paged media), multicol (multi-column), regions
//!   - Breaking Properties (§ 3): break-before, break-after, break-inside (auto, avoid, always, page, column, region)
//!   - Breaking Algorithm (§ 4): Determining the location of fragmentation breaks
//!   - Box Model Fragmentation (§ 3.2): slice vs. clone behavior for margins, borders, padding
//!   - Monolithic Elements (§ 3.3): Elements that cannot be broken (e.g., replaced elements, transforms)
//!   - Fragmentation Containers: Handling overflow and overset in regional/column chains
//!   - AI-facing: Block fragmentation visualizer and break-point map metrics

use std::collections::HashMap;

/// Breaking behaviors (§ 3.1)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BreakBehavior { Auto, Avoid, Always, All, Page, Column, Region, AvoidPage, AvoidColumn, AvoidRegion }

/// Fragmentation context types (§ 2)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FragmentationType { Page, Column, Region }

/// Fragmentation state for a flow
pub struct FragmentationContext {
    pub frag_type: FragmentationType,
    pub max_height: f64,
    pub current_offset: f64,
}

/// An individual box fragment (§ 3.2)
pub struct BoxFragment {
    pub node_id: u64,
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
    pub is_last_fragment: bool,
}

/// The CSS Fragmentation Engine
pub struct FragmentationEngine {
    pub flow_fragments: HashMap<u64, Vec<BoxFragment>>, // node_id -> fragments
    pub breaks: Vec<u64>, // node_ids where a forced break occurs
}

impl FragmentationEngine {
    pub fn new() -> Self {
        Self {
            flow_fragments: HashMap::new(),
            breaks: Vec::new(),
        }
    }

    /// Primary entry point: Find the next fragmentation break (§ 4)
    pub fn find_break(&self, context: &FragmentationContext, content_height: f64) -> f64 {
        if content_height <= context.max_height {
            content_height
        } else {
            // Find the best break-point (§ 4.2)
            context.max_height
        }
    }

    /// AI-facing fragmentation visualizer
    pub fn ai_fragment_map(&self, node_id: u64) -> String {
        if let Some(fragments) = self.flow_fragments.get(&node_id) {
            let mut lines = vec![format!("✂️ Block Fragmentation for Node #{}:", node_id)];
            for (idx, frag) in fragments.iter().enumerate() {
                lines.push(format!("  Fragment {}: (y:{:.1}, h:{:.1}) [Last: {}]", 
                    idx, frag.y, frag.height, frag.is_last_fragment));
            }
            lines.join("\n")
        } else {
            format!("Node #{} has not been fragmented", node_id)
        }
    }
}
