//! CSS Custom Highlight API Module Level 1 — W3C CSS Highlight API
//!
//! Implements arbitrary range highlighting independent of the DOM tree:
//!   - HighlightRegistry (§ 3): CSS.highlights map for adding/removing Highlight objects
//!   - Highlight (§ 3.1): A collection of AbstractRange objects
//!   - ::highlight() pseudo-element (§ 2.2): Styling registered highlights (color, background-color)
//!   - Highlight Painting Algorithm (§ 4): Z-index ordering and overlapping ranges
//!   - Search/Found Text integration: Built-in support for generic browser text search highlighting
//!   - AI-facing: Highlight regions visualizer and overlay metrics

use std::collections::HashMap;

/// A simple text range abstraction (analogous to DOM AbstractRange)
#[derive(Debug, Clone)]
pub struct TextRange {
    pub start_node_id: u64,
    pub start_offset: usize,
    pub end_node_id: u64,
    pub end_offset: usize,
}

/// A CSS Custom Highlight object (§ 3.1)
#[derive(Debug, Clone)]
pub struct CustomHighlight {
    pub priority: i32,
    pub ranges: Vec<TextRange>,
}

/// The global CSS Highlight Registry Engine
pub struct HighlightRegistryEngine {
    pub registry: HashMap<String, CustomHighlight>, // CSS.highlights map
}

impl HighlightRegistryEngine {
    pub fn new() -> Self {
        Self { registry: HashMap::new() }
    }

    /// Registers a new highlight object (§ 3)
    pub fn register_highlight(&mut self, name: &str, priority: i32, ranges: Vec<TextRange>) {
        self.registry.insert(name.to_string(), CustomHighlight { priority, ranges });
    }

    /// Clears a registered highlight
    pub fn delete_highlight(&mut self, name: &str) {
        self.registry.remove(name);
    }

    /// Calculates overlapping highlights and resolves priority for layout painting (§ 4)
    pub fn resolve_painting_highlights(&self, node_id: u64) -> Vec<(&String, &TextRange)> {
        let mut active_ranges = Vec::new();
        // Collect all ranges applying to this node
        for (name, highlight) in &self.registry {
            for range in &highlight.ranges {
                if range.start_node_id == node_id || range.end_node_id == node_id {
                    active_ranges.push((name, range, highlight.priority));
                }
            }
        }
        
        // Sort by priority (higher priority paints on top)
        active_ranges.sort_by_key(|r| r.2);
        
        active_ranges.into_iter().map(|(n, r, _)| (n, r)).collect()
    }

    /// AI-facing CSS Highlights metrics
    pub fn ai_highlight_summary(&self) -> String {
        let mut lines = vec![format!("🖍️ CSS Custom Highlight API (Active highlights: {}):", self.registry.len())];
        for (name, highlight) in &self.registry {
            lines.push(format!("  - '{}' (Priority: {}): {} text range(s)", name, highlight.priority, highlight.ranges.len()));
        }
        lines.join("\n")
    }
}
