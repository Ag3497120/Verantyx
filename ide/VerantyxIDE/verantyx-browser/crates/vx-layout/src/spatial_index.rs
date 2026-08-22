use crate::layout_node::LayoutNode;
use crate::box_model::BoxRect;
use vx_dom::NodeId;
use std::collections::HashMap;
use serde::{Serialize, Deserialize};

/// A spatial index for quick lookup of elements by coordinates.
/// Also stores the full visual layout metadata for AI consumption.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SpatialIndex {
    pub elements: HashMap<NodeId, SpatialElement>,
    pub viewport_width: f32,
    pub viewport_height: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SpatialElement {
    pub node_id: NodeId,
    pub tag_name: String,
    pub bounds: BoxRect,
    pub is_interactive: bool,
    pub label: String,
    pub depth: usize,
}

impl SpatialIndex {
    pub fn new(viewport_width: f32, viewport_height: f32) -> Self {
        Self {
            elements: HashMap::new(),
            viewport_width,
            viewport_height,
        }
    }

    /// Build index from layout tree
    pub fn build(&mut self, root: &LayoutNode, arena: &vx_dom::NodeArena) {
        self.elements.clear();
        self.traverse(root, arena, 0);
    }

    fn traverse(&mut self, node: &LayoutNode, arena: &vx_dom::NodeArena, depth: usize) {
        let dom_node = arena.get(node.node_id);
        let tag_name = dom_node.and_then(|n| n.tag_name()).unwrap_or("").to_string();
        
        let label = match dom_node {
            Some(n) => vx_dom::HtmlSerializer::text_content(arena, n.id),
            None => String::new(),
        };

        let is_interactive = match tag_name.as_str() {
            "a" | "button" | "input" | "select" | "textarea" => true,
            _ => false,
        };

        let bounds = node.computed.absolute_border_box();

        self.elements.insert(node.node_id, SpatialElement {
            node_id: node.node_id,
            tag_name,
            bounds,
            is_interactive,
            label,
            depth,
        });

        for child in &node.children {
            self.traverse(child, arena, depth + 1);
        }
    }

    /// Find elements at a specific point (hit testing)
    pub fn elements_at(&self, x: f32, y: f32) -> Vec<NodeId> {
        let mut found = Vec::new();
        for (id, el) in &self.elements {
            if el.bounds.contains(x, y) {
                found.push(*id);
            }
        }
        // Sort by depth (deepest first = front-most in most cases)
        found.sort_by(|a, b| {
            let da = self.elements.get(a).map(|e| e.depth).unwrap_or(0);
            let db = self.elements.get(b).map(|e| e.depth).unwrap_or(0);
            db.cmp(&da)
        });
        found
    }
}
