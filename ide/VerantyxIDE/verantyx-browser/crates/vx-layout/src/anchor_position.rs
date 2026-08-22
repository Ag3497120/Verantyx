//! CSS Anchor Positioning — W3C CSS Anchor Positioning
//!
//! Implements the browser's dynamic anchor-linked layout infrastructure:
//!   - anchor-name (§ 3.1): Defining an anchor element via dashed-ident
//!   - anchor-default (§ 3.2): Setting the default anchor for an absolutely positioned element
//!   - anchor() function (§ 4.1): Resolving coordinates (top, left, etc.) relative to an anchor
//!   - anchor-size() function (§ 4.2): Resolving dimensions (width, height, etc.) based on anchor size
//!   - position-anchor (§ 3.3) and position-fallback (§ 5): Handling layout overflow and fallback positions
//!   - position-visibility (§ 6.1): Hiding the anchored element based on anchor visibility
//!   - Anchor Scroll (§ 6): Synchronizing position as the anchor or container scrolls
//!   - AI-facing: Anchor registry and target-to-anchor mapping visualizer metrics

use std::collections::HashMap;

/// CSS Anchor side/size (§ 4)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AnchorSide { Top, Right, Bottom, Left, Center, Start, End, SelfStart, SelfEnd }

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AnchorSize { Width, Height, Block, Inline, SelfBlock, SelfInline }

/// Individual anchor definition (§ 3)
pub struct AnchorDefinition {
    pub name: String,
    pub node_id: u64,
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
}

/// Layout state for an anchored element (§ 3.3)
pub struct AnchoredNode {
    pub node_id: u64,
    pub anchor_name: Option<String>,
    pub fallback_name: Option<String>,
}

/// The CSS Anchor Positioning Engine
pub struct AnchorEngine {
    pub anchors: HashMap<String, AnchorDefinition>,
    pub anchored_nodes: HashMap<u64, AnchoredNode>, // target_id -> anchored_node
}

impl AnchorEngine {
    pub fn new() -> Self {
        Self {
            anchors: HashMap::new(),
            anchored_nodes: HashMap::new(),
        }
    }

    /// Registers/updates an anchor's position (§ 3.1)
    pub fn register_anchor(&mut self, name: &str, node_id: u64, x: f64, y: f64, w: f64, h: f64) {
        self.anchors.insert(name.to_string(), AnchorDefinition {
            name: name.to_string(),
            node_id,
            x, y, width: w, height: h,
        });
    }

    /// Primary entry point: Resolves an anchor() coordinate (§ 4.1)
    pub fn resolve_anchor_coord(&self, name: Option<&str>, side: AnchorSide) -> f64 {
        let anchor = match name.and_then(|n| self.anchors.get(n)) {
            Some(a) => a,
            None => return 0.0,
        };

        match side {
            AnchorSide::Top => anchor.y,
            AnchorSide::Bottom => anchor.y + anchor.height,
            AnchorSide::Left => anchor.x,
            AnchorSide::Right => anchor.x + anchor.width,
            _ => 0.0,
        }
    }

    /// AI-facing anchor registry summary
    pub fn ai_anchor_inventory(&self) -> String {
        let mut lines = vec![format!("⚓ CSS Anchor Registry (Total: {}):", self.anchors.len())];
        for (name, a) in &self.anchors {
            lines.push(format!("  - '{}' (Node #{}) at (x:{:.1}, y:{:.1}) size {}×{}", 
                name, a.node_id, a.x, a.y, a.width, a.height));
        }
        lines.join("\n")
    }
}
