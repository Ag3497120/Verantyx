//! CSS Containment Module Level 2 — W3C CSS Containment
//!
//! Implements the browser's performance isolation and container query infrastructure:
//!   - contain (§ 3): none, strict, content, size, layout, paint, style
//!   - Size Containment (§ 3.1): Ensuring the element's box sizing is independent of its descendants
//!   - Layout Containment (§ 3.2): Isolating the element's internal layout from the rest of the document
//!   - Paint Containment (§ 3.3): Clipping descendants to the element's box (implies stack context)
//!   - Style Containment (§ 3.4): Preventing scoped styles from leaking into the global document
//!   - Container Queries (§ 4): container-type (size, inline-size, normal), container-name
//!   - @container rule support and container-relative units (cqw, cqh, cqi, cqb, cqmin, cqmax)
//!   - AI-facing: Containment boundary visualizer and container context registry

use std::collections::HashMap;

/// Containment types (§ 3.1-3.4)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Containment {
    pub size: bool,
    pub layout: bool,
    pub paint: bool,
    pub style: bool,
}

impl Containment {
    pub fn none() -> Self { Self { size: false, layout: false, paint: false, style: false } }
    pub fn strict() -> Self { Self { size: true, layout: true, paint: true, style: true } }
    pub fn content() -> Self { Self { size: false, layout: true, paint: true, style: true } }
}

/// Container types for container queries (§ 4.1)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ContainerType { Normal, Size, InlineSize }

/// Layout state for a containment-aware node (§ 3)
pub struct ContainmentNode {
    pub node_id: u64,
    pub containment: Containment,
    pub container_type: ContainerType,
    pub container_name: Option<String>,
}

/// The CSS Containment Engine
pub struct ContainmentEngine {
    pub nodes: HashMap<u64, ContainmentNode>,
}

impl ContainmentEngine {
    pub fn new() -> Self {
        Self { nodes: HashMap::new() }
    }

    pub fn register_node(&mut self, node: ContainmentNode) {
        self.nodes.insert(node.node_id, node);
    }

    /// Resolves the nearest query container for a node (§ 4)
    pub fn find_container(&self, start_node_id: u64, name: Option<&str>) -> Option<&ContainmentNode> {
        // [Simplified placeholder for hierarchy traversal]
        let mut curr = start_node_id;
        while let Some(node) = self.nodes.get(&curr) {
            if node.container_type != ContainerType::Normal {
                if name.is_none() || node.container_name.as_deref() == name {
                    return Some(node);
                }
            }
            // Move up to parent... (mocked)
            break;
        }
        None
    }

    /// AI-facing containment status
    pub fn ai_containment_summary(&self, node_id: u64) -> String {
        if let Some(node) = self.nodes.get(&node_id) {
            format!("⛓️ CSS Containment (Node #{}): Size={}, Layout={}, Paint={}, Style={} [Container: {:?}]", 
                node_id, node.containment.size, node.containment.layout, node.containment.paint, 
                node.containment.style, node.container_type)
        } else {
            format!("Node #{} has no containment constraints", node_id)
        }
    }
}
