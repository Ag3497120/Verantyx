use crate::box_model::{BoxModel, ComputedBox};
use vx_dom::{NodeId, NodeArena, NodeData};

/// A node in the layout tree.
/// Maps a DOM node to its visual representation.
#[derive(Debug, Clone)]
pub struct LayoutNode {
    pub node_id: NodeId,
    pub box_model: BoxModel,
    pub computed: ComputedBox,
    pub children: Vec<LayoutNode>,
    pub is_stacking_context: bool,
    pub formatting_context: FormattingContext,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FormattingContext {
    Block,
    Inline,
    Flex,
    Grid,
    Table,
}

impl LayoutNode {
    pub fn new(node_id: NodeId) -> Self {
        Self {
            node_id,
            box_model: BoxModel::new(),
            computed: ComputedBox::default(),
            children: Vec::new(),
            is_stacking_context: false,
            formatting_context: FormattingContext::Block,
        }
    }

    /// Build layout tree from DOM tree (simplified version)
    pub fn from_dom(arena: &NodeArena, root_id: NodeId) -> Option<Self> {
        let node = arena.get(root_id)?;
        
        let mut layout_node = Self::new(root_id);

        // Skip non-renderable nodes
        match &node.data {
            NodeData::Element(el) => {
                if matches!(el.tag_name.as_str(), "script" | "style" | "head" | "meta" | "link") {
                    return None;
                }
                // Determine formatting context
                layout_node.formatting_context = match el.tag_name.as_str() {
                    "div" | "p" | "section" | "article" | "nav" | "header" | "footer" | "h1" | "h2" | "h3" => FormattingContext::Block,
                    "span" | "a" | "em" | "strong" | "i" | "b" => FormattingContext::Inline,
                    _ => FormattingContext::Block,
                };
            }
            NodeData::Text(_) => {
                layout_node.formatting_context = FormattingContext::Inline;
            }
            NodeData::Document => {
                layout_node.formatting_context = FormattingContext::Block;
            }
            _ => return None,
        }

        // Recursively build children
        for &child_id in &node.children {
            if let Some(child_layout) = Self::from_dom(arena, child_id) {
                layout_node.add_child(child_layout.clone());
            }
        }

        Some(layout_node)
    }

    pub fn add_child(&mut self, child: LayoutNode) {
        self.children.push(child);
    }
}
