//! Accessibility Tensor Tree Structural Logic
//!
//! Reconstructs a full DOM tree into a multi-dimensional ARIA graph, allowing
//! spatial filtering algorithms (like semantic zooming) to function.

use std::collections::HashMap;
use vx_dom::NodeId;
use crate::role::{A11yRole, A11yState};

#[derive(Debug, Clone)]
pub struct A11yNode {
    pub id: NodeId,
    pub role: A11yRole,
    pub state: A11yState,
    pub name: Option<String>,
    pub value: Option<String>,
    pub description: Option<String>,
    pub bounds: (f32, f32, f32, f32), // Layout bounds proxy [x, y, w, h]
    pub children: Vec<NodeId>,
    pub parent: Option<NodeId>,
}

pub struct A11yTree {
    pub root_id: Option<NodeId>,
    pub nodes: HashMap<NodeId, A11yNode>,
}

impl A11yTree {
    pub fn new() -> Self {
        Self {
            root_id: None,
            nodes: HashMap::new(),
        }
    }

    pub fn insert_node(&mut self, node: A11yNode) {
        if self.nodes.is_empty() {
            self.root_id = Some(node.id);
        }
        self.nodes.insert(node.id, node);
    }

    pub fn unignored_children(&self, parent_id: NodeId) -> Vec<NodeId> {
        let mut results = Vec::new();
        if let Some(parent) = self.nodes.get(&parent_id) {
            for child_id in &parent.children {
                if let Some(child) = self.nodes.get(child_id) {
                    if child.role == A11yRole::GenericContainer && child.name.is_none() {
                        // Skip noisy grouping nodes, pulling up semantic children directly
                        results.extend(self.unignored_children(*child_id));
                    } else {
                        results.push(*child_id);
                    }
                }
            }
        }
        results
    }
}
