//! CSS Shadow Parts — W3C CSS Shadow Parts
//!
//! Implements specific isolation-piercing styling constraints across Shadow DOM boundaries:
//!   - `::part()` pseudo-element (§ 2): Evaluating export limits from shadow encapsulation
//!   - `exportparts` attribute (§ 3): Nested chain forwardings mapping internal logical parts to the host
//!   - AI-facing: CSS Shadow DOM structural transparency limits

use std::collections::HashMap;

/// Records the exact logical exposure boundaries of a Web Component
#[derive(Debug, Clone)]
pub struct ShadowPartDefinition {
    // Physical ID of the element *inside* the Shadow Tree
    pub internal_node_id: u64,
    // The exposed CSS name (e.g., `<div part="thumb">`)
    pub declared_part_name: String,
}

/// The global Constraint Resolver governing Style Specificity across closed Custom Element bounds
pub struct CssShadowPartsEngine {
    // Shadow Host Node ID -> List of exposed internal parts
    pub registered_shadow_bounds: HashMap<u64, Vec<ShadowPartDefinition>>,
    pub total_parts_pierced_by_css: u64,
}

impl CssShadowPartsEngine {
    pub fn new() -> Self {
        Self {
            registered_shadow_bounds: HashMap::new(),
            total_parts_pierced_by_css: 0,
        }
    }

    /// Reconciles HTML parsing of `part="foo"` inside a Shadow Root mapping back to the Host Element
    pub fn register_exposed_part(&mut self, shadow_host_id: u64, internal_node_id: u64, part_names: Vec<&str>) {
        let parts = self.registered_shadow_bounds.entry(shadow_host_id).or_default();
        
        for name in part_names {
            parts.push(ShadowPartDefinition {
                internal_node_id,
                declared_part_name: name.to_string(),
            });
        }
    }

    /// Evaluated by the `vx-css` Cascade when interpreting e.g., `custom-slider::part(thumb) { background: red; }`
    pub fn resolve_pseudo_element_piercing(&mut self, target_host_id: u64, query_part_name: &str) -> Option<Vec<u64>> {
        if let Some(parts) = self.registered_shadow_bounds.get(&target_host_id) {
            let mut matching_internal_nodes = vec![];
            
            for part in parts {
                if part.declared_part_name == query_part_name {
                    matching_internal_nodes.push(part.internal_node_id);
                }
            }

            if !matching_internal_nodes.is_empty() {
                self.total_parts_pierced_by_css += matching_internal_nodes.len() as u64;
                return Some(matching_internal_nodes);
            }
        }
        None // Web Component strictly isolates the node, CSS cannot affect it.
    }

    /// Evaluates the `exportparts` forwarding matrix: `<inner-component exportparts="internal-thumb: main-thumb">`
    pub fn construct_nested_forwarding_map(&mut self, host_id: u64, internal_host_id: u64, export_map: HashMap<String, String>) {
        if let Some(internal_parts) = self.registered_shadow_bounds.get(&internal_host_id).cloned() {
            let host_parts = self.registered_shadow_bounds.entry(host_id).or_default();
            
            // Re-bind internal names to the external Host boundary
            for part in internal_parts {
                if let Some(renamed_export) = export_map.get(&part.declared_part_name) {
                    host_parts.push(ShadowPartDefinition {
                        internal_node_id: part.internal_node_id,
                        declared_part_name: renamed_export.clone(),
                    });
                }
            }
        }
    }

    /// AI-facing Component Isolation Vectors
    pub fn ai_shadow_parts_summary(&self, shadow_host_id: u64) -> String {
        if let Some(parts) = self.registered_shadow_bounds.get(&shadow_host_id) {
            format!("🎭 CSS Shadow Parts (Host #{}): Exposed Logical Boundaries: {} | Global Pierce Isolations: {}", 
                shadow_host_id, parts.len(), self.total_parts_pierced_by_css)
        } else {
            format!("Node #{} encapsulates its logical Shadow DOM completely; no ::part() vectors are surfaced", shadow_host_id)
        }
    }
}
