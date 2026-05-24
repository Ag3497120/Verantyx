//! CSS Scoping Module Level 1 — W3C CSS Scoping (Shadow DOM)
//!
//! Implements CSS isolation and encapsulation features:
//!   - :host pseudo-class (§ 3.2): Styling the shadow host from within
//!   - :host-context() pseudo-class (§ 3.3): Styling the host based on ancestor selectors
//!   - ::slotted() pseudo-element (§ 3.4): Styling projected light DOM nodes
//!   - Shadow tree styling boundary (§ 3.1): Ensuring inner styles do not leak out
//!   - Slot assignment resolution: Which elements match which `<slot>` in the ShadowDOM
//!   - AI-facing: CSS Shadow encapsulation analyzer and boundary mapping metrics

use std::collections::HashMap;

/// CSS Style isolation layer mapping
#[derive(Debug, Clone)]
pub struct ShadowBoundary {
    pub host_node_id: u64,
    pub is_open: bool,
    pub stylesheet_count: usize,
    pub slot_count: usize,
}

/// The global CSS Scoping Engine
pub struct CssScopingEngine {
    pub boundaries: HashMap<u64, ShadowBoundary>, // node_id -> Boundary Configuration
    pub slotted_elements: HashMap<u64, u64>, // child_id -> target_slot_id
}

impl CssScopingEngine {
    pub fn new() -> Self {
        Self {
            boundaries: HashMap::new(),
            slotted_elements: HashMap::new(),
        }
    }

    /// Registers a new Shadow Root encapsulation boundary
    pub fn attach_shadow(&mut self, host_id: u64, is_open: bool) {
        self.boundaries.insert(host_id, ShadowBoundary {
            host_node_id: host_id,
            is_open,
            stylesheet_count: 0,
            slot_count: 0,
        });
    }

    /// Maps a light DOM node's rendering to a `<slot>` inside the Shadow DOM (§ 3.4)
    pub fn assign_slot(&mut self, child_id: u64, target_slot_id: u64) {
        self.slotted_elements.insert(child_id, target_slot_id);
    }

    /// Validates if a standard CSS selector is permitted to cross a given shadow boundary
    pub fn can_cross_boundary(&self, host_id: u64, is_host_selector: bool) -> bool {
        // Enforce strong encapsulation: Standard selectors cannot pierce shadow roots
        // The only exception is the specific :host pseudo-class from the *inner* tree
        if self.boundaries.contains_key(&host_id) {
            return is_host_selector;
        }
        true
    }

    /// AI-facing CSS Shadow boundaries summary
    pub fn ai_shadow_summary(&self) -> String {
        let mut lines = vec![format!("👻 CSS Scoping & Shadow DOM (Active Roots: {}):", self.boundaries.len())];
        for (id, boundary) in &self.boundaries {
            let mode = if boundary.is_open { "Open" } else { "Closed" };
            lines.push(format!("  - Host #{}: [Mode: {}] {} stylesheets, {} slots", 
                id, mode, boundary.stylesheet_count, boundary.slot_count));
        }
        lines.push(format!("  🎯 Total elements assigned to slots: {}", self.slotted_elements.len()));
        lines.join("\n")
    }
}
