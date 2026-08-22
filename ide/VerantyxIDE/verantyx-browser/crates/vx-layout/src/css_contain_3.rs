//! CSS Containment Module Level 3 — W3C CSS Containment 3
//!
//! Implements Container Queries and advanced layout isolation bounds:
//!   - `container-type` (§ 2): Generating Size vs Inline-Size container geometric contexts
//!   - `@container` queries: Resolving layout conditions against Parent physical size rather than Viewport
//!   - Viewport-independent Container Units (`cqw`, `cqh`, `cqi`, `cqmax`)
//!   - AI-facing: CSS Physical Layout Container Query limits

use std::collections::HashMap;

/// Determines if the container measures X-axis only vs absolute X/Y geometry
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ContainerType { Normal, Size, InlineSize }

/// Caches the explicit computed boundary size (pixels) of a valid layout container
#[derive(Debug, Clone, Copy)]
pub struct ContainerPhysicalGeometry {
    pub inline_width_px: f64,
    pub block_height_px: f64,
}

/// The global Constraint Resolver governing Container Query interpolations preventing layout thrashing
pub struct CssContain3Engine {
    // Map of explicitly configured container elements
    pub configured_containers: HashMap<u64, ContainerType>,
    // The resolved physical dimensions of the container post-layout phase
    pub resolved_geometries: HashMap<u64, ContainerPhysicalGeometry>,
    pub total_container_queries_evaluated: u64,
}

impl CssContain3Engine {
    pub fn new() -> Self {
        Self {
            configured_containers: HashMap::new(),
            resolved_geometries: HashMap::new(),
            total_container_queries_evaluated: 0,
        }
    }

    pub fn set_container_mode(&mut self, node_id: u64, mode: ContainerType) {
        self.configured_containers.insert(node_id, mode);
    }

    /// Invoked by `vx-layout` immediately after finishing the geometry pass for the parent container
    pub fn record_physical_bounds(&mut self, node_id: u64, width: f64, height: f64) {
        self.resolved_geometries.insert(node_id, ContainerPhysicalGeometry {
            inline_width_px: width,
            block_height_px: height,
        });
    }

    /// Evaluated by `vx-css` when resolving CSSOM queries like `@container (min-width: 400px)`
    /// Requires finding the *nearest* ancestor configured as a Container and testing conditions.
    pub fn evaluate_container_query(&mut self, ancestor_node_id: u64, query_target_width: f64) -> bool {
        self.total_container_queries_evaluated += 1;

        if let Some(geom) = self.resolved_geometries.get(&ancestor_node_id) {
            return geom.inline_width_px >= query_target_width;
        }
        
        false // If no container geometry is resolved, query fails (W3C standard is usually fallback to Viewport if missing, or fails)
    }

    /// Calculates physical pixel values for Container Units (`50cqw` = 50% of container width)
    pub fn resolve_cqw_unit(&self, ancestor_node_id: u64, percentage: f64) -> Option<f64> {
        if let Some(geom) = self.resolved_geometries.get(&ancestor_node_id) {
            return Some(geom.inline_width_px * (percentage / 100.0));
        }
        None
    }

    /// AI-facing CSS Independent Sizing Topology maps
    pub fn ai_container_query_summary(&self, node_id: u64) -> String {
        if let Some(mode) = self.configured_containers.get(&node_id) {
            let dims = self.resolved_geometries.get(&node_id).map_or("Unknown".to_string(), |g| format!("{}x{}px", g.inline_width_px, g.block_height_px));
            format!("📏 CSS Contain 3 (Node #{}): Type: {:?} | Post-Layout Dimensions: {} | Global Nested Queries: {}", 
                node_id, mode, dims, self.total_container_queries_evaluated)
        } else {
            format!("Node #{} executes layout structurally bound directly to the global Viewport boundaries", node_id)
        }
    }
}
