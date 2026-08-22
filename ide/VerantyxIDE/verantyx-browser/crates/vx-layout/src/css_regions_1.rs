//! CSS Regions Module Level 1 — W3C CSS Regions 1
//!
//! Implements discontinuous layout flow topology across arbitrary geometric chains:
//!   - `flow-into` (§ 2): Ripping logical content out of the DOM hierarchy into a Virtual Flow Thread
//!   - `flow-from` (§ 3): Generating fragmentation boundaries pushing content into multiple discrete containers
//!   - Named Flow OM
//!   - AI-facing: CSS DOM Fragmentation and Discontinuous Reading Order extractors

use std::collections::HashMap;

/// Captures a sequence of physical DOM nodes that form a continuous "Region Chain"
#[derive(Debug, Clone)]
pub struct PhysicalRegionChain {
    pub flow_name: String,
    // List of Layout Node IDs acting as receiving containers
    pub receiving_region_ids: Vec<u64>, 
    // List of Content Node IDs representing the Virtual Thread source
    pub source_content_ids: Vec<u64>,
}

/// The global Constraint Resolver governing physical layout breakage across disconnected DOM elements
pub struct CssRegions1Engine {
    // Flow Name -> Topologies
    pub active_flow_threads: HashMap<String, PhysicalRegionChain>,
    pub total_region_fragments_generated: u64,
}

impl CssRegions1Engine {
    pub fn new() -> Self {
        Self {
            active_flow_threads: HashMap::new(),
            total_region_fragments_generated: 0,
        }
    }

    /// Executed during Style Resolution.
    /// Captures `flow-into: "article-thread"` pushing real elements into a staging area.
    pub fn register_content_source(&mut self, node_id: u64, flow_name: &str) {
        let chain = self.active_flow_threads.entry(flow_name.to_string()).or_insert(PhysicalRegionChain {
            flow_name: flow_name.to_string(),
            receiving_region_ids: vec![],
            source_content_ids: vec![],
        });
        
        if !chain.source_content_ids.contains(&node_id) {
            chain.source_content_ids.push(node_id);
        }
    }

    /// Executed during Box Generation.
    /// Captures `flow-from: "article-thread"` defining an empty box waiting for logical rendering elements.
    pub fn register_receiving_region(&mut self, region_node_id: u64, flow_name: &str) {
        let chain = self.active_flow_threads.entry(flow_name.to_string()).or_insert(PhysicalRegionChain {
            flow_name: flow_name.to_string(),
            receiving_region_ids: vec![],
            source_content_ids: vec![],
        });
        
        if !chain.receiving_region_ids.contains(&region_node_id) {
            chain.receiving_region_ids.push(region_node_id);
        }
    }

    /// Invoked by `vx-layout` Engine when attempting to render a Receiving Region box.
    /// Returns the exact list of logical contents assigned to it.
    /// Note: True CSS Regions fragmentation splits lines across boxes, requiring exact coordinate slicing.
    pub fn pull_virtual_flow_thread(&mut self, req_region_id: u64) -> Option<(String, Vec<u64>)> {
        for (name, chain) in self.active_flow_threads.iter() {
            if chain.receiving_region_ids.contains(&req_region_id) {
                // Generates physical fragments (Mocking the slice layout capability)
                self.total_region_fragments_generated += chain.source_content_ids.len() as u64;
                return Some((name.clone(), chain.source_content_ids.clone()));
            }
        }
        None
    }

    /// AI-facing CSS Discontinuous Topologies
    /// Crucial for AI to understand that visually disconnected UI pieces are actually one continuous text loop.
    pub fn ai_regions_summary(&self, node_id: u64) -> String {
        for (name, chain) in self.active_flow_threads.iter() {
            if chain.source_content_ids.contains(&node_id) || chain.receiving_region_ids.contains(&node_id) {
                let is_source = chain.source_content_ids.contains(&node_id);
                return format!("🗺️ CSS Regions 1 (Node #{}): Bound to Virtual Thread '{}' | Role: {} | Total Physical Chains: {}", 
                    node_id, name, if is_source { "Source Thread" } else { "Receiving Container" }, chain.receiving_region_ids.len());
            }
        }
        format!("Node #{} executes under standard continuous static DOM flow logic", node_id)
    }
}
